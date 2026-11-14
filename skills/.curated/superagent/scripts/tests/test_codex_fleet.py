"""Offline contract tests for the dispatcher, SDK adapter and fleet controls.

Run with the dispatcher's uv-resolved interpreter and bytecode disabled. All
runtime data, executable fixtures and plugin sources live in TemporaryDirectory;
the installed skill remains read-only throughout the suite.
"""
from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import multiprocessing
import os
import py_compile
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True
SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from codex_dispatch import import_v1
from codex_fleet.events import DeferredGuidance, Phase, TurnState
from codex_fleet.plugins import Plugin
from codex_fleet.policy import PolicyFile, atomic_json, choose_account, validate
from codex_fleet.sdk import Runtime, native_config
from codex_fleet.state import FileLock, State, identity
from codex_fleet.worker import Worker

MOCK = Path(__file__).with_name("mock_app_server.py")
CLI = SCRIPTS / "codex_dispatch.py"
LINUX = sys.platform.startswith("linux")


def requests(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def command_environment(**changes: str) -> dict:
    env = os.environ.copy()
    env.update(PYTHONDONTWRITEBYTECODE="1", **changes)
    return env


def contender(path: str, name: str, start, release, outcomes) -> None:
    db = State(Path(path))
    start.wait(15)
    lease = db.acquire(name, validate({"max_parallel_workers": 2}))
    outcomes.put((name, bool(lease)))
    if lease:
        try:
            lease.start()
            release.wait(15)
        finally:
            lease.close()


def crash_holder(path: str, ready) -> None:
    db = State(Path(path))
    lease = db.acquire("crash", validate({"max_parallel_workers": 1}))
    lease.start()
    ready.set()
    while True:
        time.sleep(0.1)


class TemporaryWorkspace:
    def setUp(self) -> None:
        super().setUp()
        temporary = tempfile.TemporaryDirectory(prefix="codex-fleet-test-")
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name)

    def runtime_spec(self, **env: str) -> tuple[dict, dict]:
        return {
            "cwd": str(self.path),
            "app_server_command": [sys.executable, "-B", "-u", str(MOCK)],
            "rpc_timeout": 5,
            "child_drain_timeout": 2,
            "tasks": ["task one", "task two"],
            "developer_instructions": "STATIC DEVELOPER",
        }, {
            "codex_home": str(self.path / "primary"),
            "env": {"MOCK_RECORD": str(self.path / "rpc.jsonl"), **env},
        }

    def make_fleet(self, env: dict | None = None, switch: bool = False) -> dict:
        spec, account = self.runtime_spec(**(env or {}))
        config = {
            "allowed_workspace_roots": [str(self.path)],
            "accounts": {"default": account},
            "workers": {"one": spec},
        }
        policy: dict = {"poll_seconds": 0.05}
        if switch:
            account["env"]["MOCK_SWITCH"] = "1"
            config["accounts"] = {"primary": account, "secondary": {**account, "codex_home": str(self.path / "secondary")}}
            spec["account"] = "primary"
            policy.update(account_order=["primary", "secondary"],
                          account_switch={"primary": {"used_percent": 88, "window": "secondary", "to": "secondary"}})
        atomic_json(self.path / "fleet.json", config)
        atomic_json(self.path / "policy.json", validate(policy))
        return config

    def mock_binary(self) -> Path:
        target = self.path / "mock-codex"
        target.write_text(f"#!{sys.executable}\nimport runpy\nrunpy.run_path({str(MOCK)!r}, run_name='__main__')\n")
        target.chmod(0o700)
        return target

    def cli(self, arguments: list[str], **env: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-B", str(CLI), *arguments],
                              text=True, capture_output=True,
                              env=command_environment(**env), timeout=25)


class PolicyAndStateTests(TemporaryWorkspace, unittest.TestCase):
    def test_retry_state_preserves_tools_until_recovery(self) -> None:
        state = TurnState("root", "turn")
        reductions = []
        for index in range(1, 6):
            reductions.append(state.observe({"method": "error", "params": {
                "threadId": "root", "turnId": "turn", "willRetry": True,
                "error": {"message": f"At capacity. Reconnecting... {index}/5"}}}))
        self.assertEqual(reductions, [True, False, False, False, False])
        self.assertEqual((state.phase, state.attempt, state.max_attempts), (Phase.RECONNECTING, 5, 5))
        state.observe({"method": "item/completed", "params": {"threadId": "root", "turnId": "turn", "item": {"id": "a"}}})
        self.assertEqual(state.phase, Phase.RECONNECTING)
        for tool in ("a", "b"):
            state.observe({"method": "item/started", "params": {
                "threadId": "root", "turnId": "turn", "item": {"id": tool, "type": "commandExecution"}}})
        state.observe({"method": "item/agentMessage/delta", "params": {"threadId": "root", "turnId": "turn"}})
        self.assertEqual(state.phase, Phase.TOOL_EXECUTING)
        state.observe({"method": "item/completed", "params": {"threadId": "root", "turnId": "turn", "item": {"id": "a"}}})
        self.assertEqual(state.phase, Phase.TOOL_EXECUTING)
        state.observe({"method": "turn/completed", "params": {"threadId": "root", "turn": {"id": "turn"}}})
        self.assertEqual(state.phase, Phase.IDLE)
        self.assertFalse(state.tools)

    def test_deferred_guidance_coalesces_at_boundary(self) -> None:
        guidance = DeferredGuidance()
        guidance.defer("capacity", "obsolete")
        guidance.defer("capacity", "current limit")
        guidance.defer("integration", "wait for integration")
        prompt = guidance.append("original request", 0)
        self.assertTrue(prompt.startswith("original request"))
        self.assertIn("current limit", prompt)
        self.assertIn("wait for integration", prompt)
        self.assertNotIn("obsolete", prompt)
        self.assertFalse(guidance.pending)
        self.assertNotIn("current limit", guidance.append("next task", 2))

    def test_policy_atomic_update_and_invalid_read(self) -> None:
        path = self.path / "policy.json"
        writer, reader = PolicyFile(path), PolicyFile(path)
        writer.update("max_parallel_workers", 2)
        writer.update("workers.one.pause", True)
        writer.update("max_subagents_per_worker", 0)
        self.assertEqual(reader.read()["max_parallel_workers"], 2)
        self.assertTrue(reader.read()["workers"]["one"]["pause"])
        self.assertEqual(reader.read()["max_subagents_per_worker"], 0)
        self.assertFalse(list(self.path.glob("*.pending-*")))
        for key, value in [("max_parallel_workers", True), ("poll_seconds", float("nan")),
                           ("workers.one.pause", 1), ("unknown", 1)]:
            with self.subTest(key=key), self.assertRaises((ValueError, TypeError)):
                writer.update(key, value)
        path.write_text("{")
        self.assertEqual(reader.read()["max_parallel_workers"], 2)
        self.assertIsNotNone(reader.error)
        with self.assertRaises((ValueError, TypeError)):
            writer.update("max_parallel_workers", 1)

    def test_sticky_accounts_and_static_role_hints(self) -> None:
        default = validate({})
        self.assertEqual(default["account_order"], ["default"])
        self.assertEqual(default["account_switch"], {})
        policy = validate({"account_order": ["primary", "secondary"],
                           "account_switch": {"primary": {"used_percent": 88, "window": "secondary", "to": "secondary"}}})
        self.assertEqual(choose_account("primary", {"secondary": {"usedPercent": 88}}, policy), "secondary")
        self.assertEqual(choose_account("secondary", {"secondary": {"usedPercent": 0}}, policy), "secondary")
        with self.assertRaises(ValueError):
            validate({"account_order": ["primary", "secondary"],
                      "account_switch": {"secondary": {"used_percent": 88, "window": "secondary", "to": "primary"}}})
        no_children, children = native_config(0), native_config(4)
        self.assertEqual(no_children["features.multi_agent_v2.max_concurrent_threads_per_session"], 1)
        for key in ("root_agent_usage_hint_text", "subagent_usage_hint_text"):
            self.assertEqual(no_children["features.multi_agent_v2." + key], children["features.multi_agent_v2." + key])

    def test_overload_persistence_retry_cap_and_gradual_recovery(self) -> None:
        db = State(self.path / "state.db")
        for attempt in range(5):
            self.assertEqual(db.overload("thread", "turn", str(attempt), 2), attempt == 0)
        db = State(self.path / "state.db")
        self.assertEqual(db.snapshot()["overload_count"], 1)
        self.assertEqual(db.snapshot()["capacity"]["level"], 1)
        for index in range(5):
            db.overload("thread", f"turn-{index}", "retry", 2)
        self.assertEqual(db.snapshot()["capacity"]["level"], 2)
        # Long-running repeated retries refresh the unhealthy timestamp, then a
        # full quiet window restores exactly one step, not all capacity at once.
        with db.connect(True) as conn:
            conn.execute("UPDATE capacity SET changed=0,overloaded=0")
        policy = validate({"recovery_seconds": 1})
        self.assertEqual(db.limits(policy)[2], 1)
        self.assertEqual(db.limits(policy)[2], 1)
        with db.connect(True) as conn:
            conn.execute("UPDATE capacity SET changed=0,overloaded=0")
        self.assertEqual(db.limits(policy)[2], 0)

    @unittest.skipUnless(LINUX, "Linux process-incarnation evidence")
    def test_identity_and_pid_reuse_fencing(self) -> None:
        self.assertIsNotNone(identity(os.getpid()))
        self.assertIsNone(identity(2**30))
        boot_id, start = identity(os.getpid()).rsplit(":", 1)
        self.assertTrue(boot_id)
        self.assertTrue(start.isdigit())
        db = State(self.path / "state.db")
        policy = validate({"max_parallel_workers": 1})
        lease = db.acquire("old", policy)
        try:
            with db.connect(True) as conn:
                conn.execute("UPDATE leases SET incarnation='different-process'")
            self.assertIsNone(db.acquire("new", policy))
        finally:
            lease.close()
        replacement = db.acquire("new", policy)
        self.assertIsNotNone(replacement)
        replacement.close()

    def test_expired_owner_cannot_resurrect_and_runtime_fence_holds_slot(self) -> None:
        db = State(self.path / "state.db")
        policy = validate({"max_parallel_workers": 1})
        lease = db.acquire("old", policy)
        fence = FileLock(Path(lease.runtime_fence))
        try:
            with db.connect(True) as conn:
                conn.execute("UPDATE leases SET expires=0")
            self.assertFalse(lease.renew())
            self.assertTrue(lease.lost.is_set())
            self.assertIsNone(db.acquire("new", policy))
            lease.close()
            self.assertIsNone(db.acquire("new", policy))
        finally:
            fence.close()
        replacement = db.acquire("new", policy)
        self.assertIsNotNone(replacement)
        replacement.close()

    def test_heartbeat_independent_of_async_loop(self) -> None:
        db = State(self.path / "state.db")
        lease = db.acquire("one", validate({"lease_seconds": 3})).start()
        try:
            before = lease.expires
            deadline = time.monotonic() + 2
            while lease.expires <= before and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertGreater(lease.expires, before)
            self.assertFalse(lease.lost.is_set())
        finally:
            lease.close()

    @unittest.skipUnless(LINUX, "Linux file locks and process identity")
    def test_atomic_cross_process_leases_and_crash_recovery(self) -> None:
        path = self.path / "state.db"
        db = State(path)
        ctx = multiprocessing.get_context("spawn")
        start, release, outcomes = ctx.Event(), ctx.Event(), ctx.Queue()
        children = [ctx.Process(target=contender, args=(str(path), str(index), start, release, outcomes)) for index in range(6)]
        try:
            for child in children:
                child.start()
            start.set()
            answers = [outcomes.get(timeout=20) for _ in children]
            self.assertEqual(sum(ok for _, ok in answers), 2)
        finally:
            release.set()
            for child in children:
                child.join(10)
                if child.is_alive():
                    child.kill()
                    child.join(5)
            outcomes.close()
            outcomes.join_thread()
        self.assertTrue(all(child.exitcode == 0 for child in children))
        self.assertFalse(db.snapshot()["leases"])
        ready = ctx.Event()
        crashed = ctx.Process(target=crash_holder, args=(str(path), ready))
        crashed.start()
        try:
            self.assertTrue(ready.wait(10))
            self.assertIsNone(db.acquire("blocked", validate({"max_parallel_workers": 1})))
        finally:
            crashed.kill()
            crashed.join(5)
        lease = db.acquire("reclaimed", validate({"max_parallel_workers": 1}))
        self.assertIsNotNone(lease)
        lease.close()

    def test_import_is_lossless_and_rejects_checkpoint_rollback(self) -> None:
        path = self.path / "legacy.json"
        value = {"one": {"account": "default", "thread_id": "legacy-thread", "turn_index": 7,
                         "completed": False, "future_field": {"x": 1}}}
        atomic_json(path, value)
        db = State(self.path / "state.db")
        self.assertEqual(import_v1(db, path), ["one"])
        saved = db.worker("one")
        for key, item in value["one"].items():
            self.assertEqual(saved[key], item)
        with self.assertRaises(ValueError):
            import_v1(db, path)
        with db.connect() as conn:
            self.assertEqual(json.loads(conn.execute("SELECT data FROM imports").fetchone()[0]), value)
        atomic_json(path, {"two": {"thread_id": "missing-account"}})
        with self.assertRaises(ValueError):
            import_v1(db, path)

    def test_persistent_account_order_cannot_be_reordered_or_shrunk(self) -> None:
        db = State(self.path / "state.db")
        db.remember_account_order(["primary", "secondary"])
        State(self.path / "state.db").remember_account_order(["primary", "secondary", "reserve"])
        for order in (["secondary", "primary", "reserve"], ["primary"]):
            with self.subTest(order=order), self.assertRaises(ValueError):
                State(self.path / "state.db").remember_account_order(order)

    def test_readonly_state_never_creates_or_mutates_database(self) -> None:
        path = self.path / "state.db"
        live = State(path)
        live.save("one", status="paused")
        read = State(path, readonly=True)
        self.assertEqual(read.snapshot()["workers"]["one"]["status"], "paused")
        with self.assertRaises((ValueError, RuntimeError, PermissionError)):
            with read.connect(True):
                pass
        with self.assertRaises((OSError, ValueError, RuntimeError)):
            State(self.path / "absent" / "state.db", readonly=True)
        self.assertFalse((self.path / "absent").exists())

    def test_guard_feature_detection_skips_linux_only_calls(self) -> None:
        from codex_fleet import guard
        with patch.object(guard.sys, "platform", "darwin"), patch.object(guard.ctypes, "CDLL") as library:
            guard._linux_parent_signal()
            library.assert_not_called()


class RuntimeTests(TemporaryWorkspace, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        asyncio.get_running_loop().set_debug(False)

    async def collect_turn(self, runtime: Runtime) -> tuple[dict, list[dict]]:
        handle = await runtime.begin("original request")
        seen: list[dict] = []

        async def collect_tap():
            while True:
                event = await runtime.tap.next()
                seen.append(event)
                if event["method"] == "turn/completed" and event["params"].get("threadId") == runtime.thread.id:
                    return

        task = asyncio.create_task(collect_tap())
        result = None
        try:
            async for event in handle.stream():
                if event.method == "turn/completed":
                    result = event.payload.model_dump(mode="json", by_alias=True, warnings=False)["turn"]
            await asyncio.wait_for(task, 5)
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        self.assertIsNotNone(result)
        return result, seen

    async def test_parent_stream_and_tap_receive_early_child_events(self) -> None:
        spec, account = self.runtime_spec()
        runtime = Runtime(spec, account, 1)
        try:
            await runtime.start()
            await runtime.open_thread(None, "STATIC")
            result, seen = await self.collect_turn(runtime)
            self.assertEqual(result["status"], "completed")
            self.assertEqual(sum(bool(event.get("overload")) for event in seen), 1)
            self.assertTrue(any(event["params"].get("delta") == "live child output" for event in seen))
            self.assertIn("child-1", runtime.tap.children)
            self.assertFalse(runtime.tap.active_children())
        finally:
            await runtime.close()
        self.assertNotIn("turn/steer", [row["method"] for row in requests(self.path / "rpc.jsonl")])

    async def test_permissions_omitted_or_consistently_explicit_for_all_entry_points(self) -> None:
        for sandbox, approval, wire_sandbox, wire_approval in [
            (None, None, None, None),
            ("read-only", "never", "read-only", "never"),
            ("danger-full-access", "auto-review", "danger-full-access", "on-request"),
        ]:
            with self.subTest(sandbox=sandbox):
                spec, account = self.runtime_spec(MOCK_RETRY="0")
                spec.update(sandbox=sandbox, approval_policy=approval)
                account["env"]["MOCK_RECORD"] = str(self.path / f"{sandbox}.jsonl")
                runtime = Runtime(spec, account, 0)
                try:
                    await runtime.start()
                    tid = await runtime.open_thread(None, "STATIC")
                    await self.collect_turn(runtime)
                    await runtime.open_thread(tid, "STATIC")
                    await self.collect_turn(runtime)
                finally:
                    await runtime.close()
                recorded = requests(Path(account["env"]["MOCK_RECORD"]))
                opens = [row for row in recorded if row["method"] in ("thread/start", "thread/resume")]
                turns = [row for row in recorded if row["method"] == "turn/start"]
                self.assertEqual(len(opens), 2)
                self.assertEqual(len(turns), 2)
                for row in opens:
                    if sandbox is None:
                        self.assertNotIn("sandbox", row["params"])
                        self.assertNotIn("approvalPolicy", row["params"])
                        self.assertNotIn("approvalsReviewer", row["params"])
                    else:
                        self.assertEqual(row["params"]["sandbox"], wire_sandbox)
                        self.assertEqual(row["params"]["approvalPolicy"], wire_approval)
                        if approval == "auto-review":
                            self.assertEqual(row["params"]["approvalsReviewer"], "auto_review")
                for row in turns:
                    if sandbox is None:
                        self.assertNotIn("sandboxPolicy", row["params"])
                        self.assertNotIn("approvalPolicy", row["params"])
                        self.assertNotIn("approvalsReviewer", row["params"])
                    else:
                        self.assertEqual(row["params"]["sandboxPolicy"]["type"],
                                         "readOnly" if sandbox == "read-only" else "dangerFullAccess")
                        self.assertEqual(row["params"]["approvalPolicy"], wire_approval)
                        if approval == "auto-review":
                            self.assertEqual(row["params"]["approvalsReviewer"], "auto_review")

    async def test_environment_inheritance_override_removal_and_optional_home(self) -> None:
        spec, account = self.runtime_spec(MOCK_RETRY="0")
        account["codex_home"] = None
        account["env"].update(FLEET_TEST_PRECEDENCE="account", FLEET_TEST_REMOVE="account")
        spec["env"] = {"FLEET_TEST_PRECEDENCE": "spec", "FLEET_TEST_REMOVE": None,
                       "MOCK_ENV_KEYS": "FLEET_TEST_PARENT,FLEET_TEST_PRECEDENCE,FLEET_TEST_REMOVE,PATH,HOME"}
        with patch.dict(os.environ, {"FLEET_TEST_PARENT": "inherited", "CODEX_HOME": str(self.path / "inherited-home")}):
            runtime = Runtime(spec, account, 0)
            try:
                await runtime.start()
            finally:
                await runtime.close()
        row = requests(self.path / "rpc.jsonl")[0]
        self.assertEqual(row["account_home"], str(self.path / "inherited-home"))
        self.assertEqual(row["env"]["FLEET_TEST_PARENT"], "inherited")
        self.assertEqual(row["env"]["FLEET_TEST_PRECEDENCE"], "spec")
        self.assertIsNone(row["env"]["FLEET_TEST_REMOVE"])
        self.assertEqual(row["env"]["PATH"], os.environ.get("PATH"))
        self.assertEqual(row["env"]["HOME"], os.environ.get("HOME"))

    async def test_newer_cli_version_passes_but_missing_native_cap_refuses_inference(self) -> None:
        for env, expected in [({"MOCK_VERSION": "0.169.0"}, None),
                              ({"MOCK_VERSION": "0.166.9"}, "version|CLI|older|minimum"),
                              ({"MOCK_BAD_CONFIG": "1"}, "multi_agent_v2")]:
            spec, account = self.runtime_spec(**env)
            runtime = Runtime(spec, account, 0)
            try:
                if expected:
                    with self.assertRaisesRegex(RuntimeError, expected):
                        await runtime.start()
                else:
                    await runtime.start()
            finally:
                await runtime.close()
        self.assertNotIn("turn/start", [row["method"] for row in requests(self.path / "rpc.jsonl")])

    async def test_start_timeout_and_repeated_cancel_wait_for_late_spawn_cleanup(self) -> None:
        for repeated_cancel in (False, True):
            with self.subTest(repeated_cancel=repeated_cancel):
                spec, account = self.runtime_spec(MOCK_RETRY="0")
                spec["rpc_timeout"] = 0.05
                runtime = Runtime(spec, account, 0)
                sync = runtime.codex._client._sync
                original_start = sync.start
                entered, release, spawn_finished = (threading.Event() for _ in range(3))
                spawned: list[subprocess.Popen] = []

                def delayed_start():
                    entered.set()
                    try:
                        if not release.wait(8):
                            raise RuntimeError("test did not release the SDK spawn")
                        original_start()
                        if sync._proc is not None and sync._proc not in spawned:
                            spawned.append(sync._proc)
                    finally:
                        spawn_finished.set()

                with patch.object(sync, "start", delayed_start):
                    task = asyncio.create_task(runtime.start())
                    try:
                        self.assertTrue(await asyncio.to_thread(entered.wait, 3))
                        # The inner RPC deadline expires, but shielded cleanup
                        # must remain pending while the actual spawn is blocked.
                        with self.assertRaises(TimeoutError):
                            await asyncio.wait_for(asyncio.shield(task), timeout=0.15)
                        self.assertFalse(task.done(), "start returned before its pending spawn could be reaped")
                        self.assertFalse(runtime._closed, "runtime claimed closed before SDK start finished")
                        self.assertIsNone(sync._proc)
                        if repeated_cancel:
                            for index in range(2):
                                task.cancel(f"cancel during delayed spawn cleanup {index}")
                                await asyncio.sleep(0.02)
                                self.assertFalse(task.done(), "repeated cancellation escaped spawn cleanup")
                                self.assertFalse(runtime._closed)
                        release.set()
                        expected = asyncio.CancelledError if repeated_cancel else TimeoutError
                        with self.assertRaises(expected):
                            await asyncio.wait_for(task, timeout=8)
                        self.assertTrue(spawn_finished.is_set())
                        self.assertTrue(runtime._closed)
                        self.assertTrue(spawned, "test never exercised a real late Popen")
                        self.assertTrue(sync._proc is None or sync._proc.poll() is not None)
                        for process in spawned:
                            self.assertIsNotNone(process.poll(), "late SDK start leaked a live guardian")
                            for pipe in (process.stdin, process.stdout, process.stderr):
                                self.assertTrue(pipe is None or pipe.closed)
                    finally:
                        # Also safe when run against the buggy implementation:
                        # wait for its real thread and reap only captured peers.
                        release.set()
                        await asyncio.to_thread(spawn_finished.wait, 8)
                        if not task.done():
                            task.cancel()
                        await asyncio.gather(task, return_exceptions=True)
                        await runtime.close()
                        for process in spawned:
                            if process.poll() is None:
                                process.terminate()
                                await asyncio.to_thread(process.wait, 8)
                            for pipe in (process.stdin, process.stdout, process.stderr):
                                if pipe is not None:
                                    pipe.close()

    async def test_missing_child_lifecycle_uses_read_only_reconciliation(self) -> None:
        self.make_fleet({"MOCK_QUIET_CHILD": "1"})
        await Worker(self.path, "one").run(max_turns=1)
        db = State(self.path / "state.db")
        self.assertEqual(db.worker("one")["turn_index"], 1)
        with db.connect() as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM events WHERE kind='subagent_tap_degraded'").fetchone()[0], 1)
        methods = [row["method"] for row in requests(self.path / "rpc.jsonl")]
        self.assertIn("thread/read", methods)
        self.assertNotIn("thread/resume", methods)

    async def test_active_unobserved_child_cannot_be_reported_settled(self) -> None:
        config = self.make_fleet({"MOCK_QUIET_CHILD": "1", "MOCK_CHILD_STATUS": "active"})
        config["workers"]["one"]["child_drain_timeout"] = 0.15
        atomic_json(self.path / "fleet.json", config)
        with self.assertRaisesRegex(RuntimeError, "child|subagent|quiesce"):
            await Worker(self.path, "one").run(max_turns=1)
        saved = State(self.path / "state.db").worker("one")
        self.assertTrue(saved["uncertain"])
        self.assertEqual(saved.get("turn_index", 0), 0)

    async def test_worker_reuses_account_thread_and_hot_capacity_only_at_boundary(self) -> None:
        self.make_fleet()
        await Worker(self.path, "one").run(max_turns=1)
        db = State(self.path / "state.db")
        old = db.worker("one")["thread_id"]
        PolicyFile(self.path / "policy.json").update("max_subagents_per_worker", 0)
        await Worker(self.path, "one").run(max_turns=1)
        saved = db.worker("one")
        self.assertEqual(saved["thread_id"], old)
        self.assertEqual(saved["turn_index"], 2)
        self.assertFalse(saved["uncertain"])
        self.assertEqual(saved["subagents"], 0)
        self.assertEqual(db.snapshot()["overload_count"], 2)
        opens = [row for row in requests(self.path / "rpc.jsonl") if row["method"] in ("thread/start", "thread/resume")]
        self.assertEqual([row["method"] for row in opens], ["thread/start", "thread/resume"])
        self.assertEqual(opens[0]["params"]["developerInstructions"], opens[1]["params"]["developerInstructions"])
        self.assertFalse(db.snapshot()["leases"])

    async def test_account_switch_persists_destination_and_starts_fresh_thread(self) -> None:
        self.make_fleet(switch=True)
        db = State(self.path / "state.db")
        db.save("one", account="primary", thread_id="old-primary-thread", turn_index=0)
        await Worker(self.path, "one").run(max_turns=1)
        self.assertEqual(db.worker("one")["account"], "secondary")
        rows = requests(self.path / "rpc.jsonl")
        self.assertNotIn("thread/resume", [row["method"] for row in rows])
        opens = [row for row in rows if row["method"] == "thread/start"]
        self.assertEqual(len(opens), 1)
        self.assertEqual(Path(opens[0]["account_home"]).name, "secondary")

    async def test_pause_and_drain_preserve_hot_turn(self) -> None:
        self.make_fleet({"MOCK_DELAY": "0.3"})
        policy = PolicyFile(self.path / "policy.json")
        policy.update("workers.one.pause", True)
        worker = Worker(self.path, "one")
        task = asyncio.create_task(worker.run())
        try:
            await asyncio.sleep(0.12)
            self.assertFalse((self.path / "rpc.jsonl").exists())
            policy.update("workers.one.pause", False)
            deadline = time.monotonic() + 8
            while not worker.db.worker("one").get("turn_id"):
                self.assertLess(time.monotonic(), deadline)
                await asyncio.sleep(0.02)
            policy.update("workers.one.drain", True)
            await asyncio.wait_for(task, 10)
            saved = worker.db.worker("one")
            self.assertEqual(saved["turn_index"], 1)
            self.assertEqual(saved["status"], "drained")
            self.assertFalse(saved["uncertain"])
        finally:
            if not task.done():
                worker.request_drain()
                await asyncio.wait_for(task, 10)

    async def test_failed_turn_and_gate_leave_uncertain_until_successful_retry(self) -> None:
        for status, gate_script, expected in [("failed", "pass", 0), ("completed", "raise SystemExit(2)", 0),
                                                ("completed", "import time; time.sleep(2)", 0), ("completed", "pass", 1)]:
            with self.subTest(status=status, gate=gate_script):
                config = self.make_fleet({"MOCK_STATUS": status})
                config["workers"]["one"].update(gate_command=[sys.executable, "-B", "-c", gate_script],
                                                 gate_timeout=0.1 if gate_script.startswith("import time") else 5)
                atomic_json(self.path / "fleet.json", config)
                # Reusing the same checkpoint models a human fixing the failed
                # gate and explicitly retrying the still-uncertain current task.
                await Worker(self.path, "one").run(max_turns=1)
                saved = State(self.path / "state.db").worker("one")
                self.assertEqual(saved.get("turn_index", 0), expected)
                self.assertEqual(saved["uncertain"], not bool(expected))

    @unittest.skipUnless(LINUX, "Linux worker/cwd locks and fenced gate process")
    async def test_repeated_cancellation_retains_locks_and_lease_until_gate_exits(self) -> None:
        entered, release, finished = (self.path / name for name in ("gate-entered", "gate-release", "gate-finished"))
        gate = (
            "import sys,time; from pathlib import Path; "
            "entered,release,finished=map(Path,sys.argv[1:]); entered.write_text('entered')\n"
            "while not release.exists(): time.sleep(.01)\n"
            "time.sleep(.05); finished.write_text('finished')\n"
        )
        config = self.make_fleet({"MOCK_RETRY": "0"})
        config["workers"]["one"].update(
            gate_command=[sys.executable, "-B", "-c", gate, str(entered), str(release), str(finished)],
            gate_timeout=8,
        )
        atomic_json(self.path / "fleet.json", config)
        PolicyFile(self.path / "policy.json").update("max_parallel_workers", 1)
        worker = Worker(self.path, "one")
        task = asyncio.create_task(worker.run(max_turns=1))
        cwd_key = hashlib.sha256(str(self.path.resolve()).encode()).hexdigest()
        locks = [self.path / "workers" / "one.lock", self.path / "repositories" / f"{cwd_key}.lock"]
        try:
            deadline = time.monotonic() + 8
            while not entered.exists():
                self.assertFalse(task.done(), "worker stopped before entering the gate")
                self.assertLess(time.monotonic(), deadline)
                await asyncio.sleep(0.02)
            for attempt in range(2):
                task.cancel(f"gate cancellation {attempt}")
                await asyncio.sleep(0.03)
                self.assertFalse(task.done(), "cancellation escaped while the synchronous gate still owns the workspace")
                self.assertFalse(finished.exists())
                leases = worker.db.snapshot()["leases"]
                self.assertEqual([lease["worker"] for lease in leases], ["one"])
                for lock in locks:
                    with self.assertRaises(BlockingIOError):
                        with FileLock(lock):
                            pass
                self.assertIsNone(worker.db.acquire("replacement", validate({"max_parallel_workers": 1})))
            release.write_text("finish the gate")
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(task, 8)
            self.assertTrue(finished.exists())
            checkpoint = worker.db.worker("one")
            self.assertTrue(checkpoint["uncertain"])
            self.assertEqual(checkpoint.get("turn_index", 0), 0)
            self.assertFalse(worker.db.snapshot()["leases"])
            for lock in locks:
                with FileLock(lock):
                    pass
        finally:
            # Release the test gate even when an assertion detects the original
            # bug; the thread must finish before its temporary files disappear.
            release.write_text("cleanup")
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            deadline = time.monotonic() + 8
            while entered.exists() and not finished.exists() and time.monotonic() < deadline:
                await asyncio.sleep(0.02)

    @unittest.skipUnless(LINUX, "Linux worker and canonical cwd locks")
    async def test_distinct_worker_names_cannot_share_writable_cwd(self) -> None:
        config = self.make_fleet({"MOCK_DELAY": "0.4"})
        config["workers"]["two"] = config["workers"]["one"].copy()
        atomic_json(self.path / "fleet.json", config)
        first = asyncio.create_task(Worker(self.path, "one").run(max_turns=1))
        try:
            deadline = time.monotonic() + 8
            while not State(self.path / "state.db").worker("one").get("turn_id"):
                self.assertLess(time.monotonic(), deadline)
                await asyncio.sleep(0.02)
            with self.assertRaises((BlockingIOError, RuntimeError)):
                await Worker(self.path, "two").run(max_turns=1)
            await asyncio.wait_for(first, 10)
        finally:
            if not first.done():
                first.cancel()
                await asyncio.gather(first, return_exceptions=True)

    @unittest.skipUnless(LINUX, "Linux runtime ownership fences")
    async def test_runtime_owner_fences_block_reentry_even_with_another_free_slot(self) -> None:
        config = self.make_fleet({"MOCK_RETRY": "0"})
        config["workers"]["two"] = config["workers"]["one"].copy()
        atomic_json(self.path / "fleet.json", config)
        PolicyFile(self.path / "policy.json").update("max_parallel_workers", 2)
        db = State(self.path / "state.db")
        cwd_key = hashlib.sha256(str(self.path.resolve()).encode()).hexdigest()
        worker_owner = self.path / "workers" / "one.runtime.lock"
        cwd_owner = self.path / "repositories" / f"{cwd_key}.runtime.lock"
        with FileLock(self.path / "slots" / "0.runtime.lock"):
            # The old runtime owns slot zero, while a different slot can still
            # be allocated. Slot fencing alone therefore cannot protect cwd.
            spare = db.acquire("spare-capacity-probe", validate({"max_parallel_workers": 2}))
            self.assertIsNotNone(spare)
            self.assertEqual(Path(spare.runtime_fence).name, "1.runtime.lock")
            spare.close()
            for name, fence in (("one", worker_owner), ("two", cwd_owner)):
                with self.subTest(worker=name), FileLock(fence):
                    with self.assertRaises((BlockingIOError, RuntimeError)):
                        await Worker(self.path, name).run(max_turns=1)
                    self.assertFalse((self.path / "rpc.jsonl").exists(), "rejected owner started a model runtime")
                    self.assertFalse(db.snapshot()["leases"])
            # Once the old owner's fences release, the same workspace can run
            # on slot one even though slot zero is still being cleaned up.
            await Worker(self.path, "one").run(max_turns=1)
        self.assertEqual(db.worker("one")["turn_index"], 1)
        self.assertFalse(db.snapshot()["leases"])

    async def test_runtime_eof_preserves_uncertain_and_releases_only_own_lease(self) -> None:
        self.make_fleet({"MOCK_EXIT": "1"})
        with self.assertRaises(Exception):
            await Worker(self.path, "one").run(max_turns=1)
        db = State(self.path / "state.db")
        self.assertEqual(db.worker("one")["status"], "faulted")
        self.assertTrue(db.worker("one")["uncertain"])
        self.assertFalse(db.snapshot()["leases"])

    async def test_source_plugin_same_size_same_time_reload_and_sync_nonblocking(self) -> None:
        name = "fleet_test_plugin_" + uuid.uuid4().hex
        file = self.path / (name + ".py")
        file.write_text("import time\ndef prepare(ctx): time.sleep(.1); return 'version one'\ndef complete(ctx, result): return True\n")
        original_stat = file.stat()
        # Deliberately create a timestamp-valid stale cache only inside the
        # disposable fixture, proving reload bypasses it without deleting it.
        bytecode = Path(importlib.util.cache_from_source(str(file)))
        py_compile.compile(str(file), cfile=str(bytecode), doraise=True)
        sys.path.insert(0, str(self.path))
        try:
            plugin = Plugin(name)
            plugin.reload()
            ticking = asyncio.create_task(asyncio.sleep(0.02, result="responsive"))
            prepared = asyncio.create_task(plugin.call("prepare", {}))
            done, _ = await asyncio.wait([ticking, prepared], return_when=asyncio.FIRST_COMPLETED)
            self.assertIn(ticking, done)
            self.assertEqual(await prepared, "version one")
            file.write_text(file.read_text().replace("version one", "version two"))
            os.utime(file, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
            plugin.reload()
            self.assertEqual(await plugin.call("prepare", {}), "version two")
            self.assertTrue(bytecode.is_file())
        finally:
            sys.path.remove(str(self.path))
            sys.modules.pop(name, None)

    async def test_tap_overflow_is_visible(self) -> None:
        spec, account = self.runtime_spec()
        runtime = Runtime(spec, account, 1)
        runtime.tap.max_events = 1
        try:
            await runtime.start()
            await runtime.open_thread(None, "STATIC")
            await runtime.begin("task")
            await asyncio.sleep(0.05)
            with self.assertRaisesRegex(RuntimeError, "overflow"):
                await runtime.tap.next()
        finally:
            await runtime.close()


class CLITests(TemporaryWorkspace, unittest.TestCase):
    def test_run_summary_receipt_events_defaults_and_resume(self) -> None:
        binary = self.mock_binary()
        receipt, events, record = (self.path / filename for filename in ("receipt.json", "events.jsonl", "requests.jsonl"))
        first = self.cli(["run", "--cwd", str(self.path), "--codex-bin", str(binary),
                          "--prompt", "original user request", "--events-jsonl", str(events), "--receipt-json", str(receipt)],
                         MOCK_RECORD=str(record), MOCK_QUIET_CHILD="1")
        self.assertEqual(first.returncode, 0, first.stderr)
        summary = json.loads(first.stdout)
        self.assertEqual(summary, json.loads(receipt.read_text()))
        self.assertTrue({"thread_id", "turn_id", "status", "final_message", "elapsed_s", "before_limits", "after_limits", "reconciled_children"} <= summary.keys())
        self.assertEqual(summary["status"], "completed")
        self.assertEqual(summary["final_message"], "mock result")
        self.assertIn("child-1", summary["reconciled_children"])
        self.assertTrue(events.read_text().strip())
        recorded = requests(record)
        opened = next(row["params"] for row in recorded if row["method"] == "thread/start")
        turned = next(row["params"] for row in recorded if row["method"] == "turn/start")
        self.assertEqual(opened["model"], "gpt-6.1-sol")
        self.assertEqual(turned["effort"], "xhigh")
        self.assertEqual(opened["config"]["features.multi_agent_v2.max_concurrent_threads_per_session"], 3)
        self.assertNotIn("sandbox", opened)
        self.assertNotIn("approvalPolicy", opened)
        self.assertNotIn("sandboxPolicy", turned)
        prompt = self.path / "prompt.txt"
        prompt.write_text("follow up")
        second = self.cli(["run", "--cwd", str(self.path), "--codex-bin", str(binary),
                           "--prompt-file", str(prompt), "--resume-thread", summary["thread_id"], "--subagents", "0"],
                          MOCK_RECORD=str(record))
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(json.loads(second.stdout)["thread_id"], summary["thread_id"])
        self.assertIn("thread/resume", [row["method"] for row in requests(record)])

    def test_run_quota_errors_are_data_not_task_failure(self) -> None:
        result = self.cli(["run", "--cwd", str(self.path), "--prompt", "task", "--codex-bin", str(self.mock_binary())], MOCK_LIMITS_ERROR="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(value["status"], "completed")
        self.assertIn("error", value["before_limits"])
        self.assertIn("error", value["after_limits"])

    def test_run_failed_turn_nonzero_and_prompt_arguments_are_exclusive(self) -> None:
        binary = self.mock_binary()
        result = self.cli(["run", "--cwd", str(self.path), "--prompt", "task", "--codex-bin", str(binary)], MOCK_STATUS="failed")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["status"], "failed")
        invalid = self.cli(["run", "--cwd", str(self.path), "--prompt", "task", "--prompt-file", "unused"])
        self.assertEqual(invalid.returncode, 2)

    def test_limits_reads_named_accounts_and_default_without_starting_turn(self) -> None:
        binary, record = self.mock_binary(), self.path / "limits.jsonl"
        result = self.cli(["limits", "--codex-bin", str(binary), "--account", f"primary={self.path / 'primary'}",
                           "--account", f"secondary={self.path / 'secondary'}"], MOCK_RECORD=str(record), MOCK_SWITCH="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)["accounts"]
        self.assertIn("primary", value)
        self.assertIn("secondary", value)
        self.assertNotEqual(value["primary"], value["secondary"])
        default = self.cli(["limits", "--codex-bin", str(binary)], MOCK_RECORD=str(record))
        self.assertEqual(default.returncode, 0, default.stderr)
        self.assertIn("default", json.loads(default.stdout)["accounts"])
        self.assertNotIn("turn/start", [row["method"] for row in requests(record)])

    def test_fleet_lifecycle_end_to_end_and_status_read_only(self) -> None:
        fleet = self.path / "fleet"
        result = self.cli(["fleet", "--fleet-dir", str(fleet), "init"])
        self.assertEqual(result.returncode, 0, result.stderr)
        spec, account = self.runtime_spec(MOCK_RETRY="0")
        atomic_json(fleet / "fleet.json", {"allowed_workspace_roots": [str(self.path)],
                                          "accounts": {"default": account}, "workers": {"one": spec}})
        for arguments in (["set-policy", "max_parallel_workers", "2"],
                          ["pause", "one"], ["drain", "one"], ["resume", "one"]):
            result = self.cli(["fleet", "--fleet-dir", str(fleet), *arguments])
            self.assertEqual(result.returncode, 0, result.stderr)
        result = self.cli(["fleet", "run-worker", "one", "--max-turns", "1", "--fleet-dir", str(fleet)])
        self.assertEqual(result.returncode, 0, result.stderr)
        status = self.cli(["fleet", "--fleet-dir", str(fleet), "status"])
        self.assertEqual(status.returncode, 0, status.stderr)
        value = json.loads(status.stdout)
        self.assertEqual(value["workers"]["one"]["turn_index"], 1)
        self.assertFalse(value["leases"])
        self.assertFalse(value["policy"]["workers"]["one"]["drain"])
        missing = self.path / "missing"
        absent = self.cli(["fleet", "--fleet-dir", str(missing), "status"])
        self.assertNotEqual(absent.returncode, 0)
        self.assertFalse(missing.exists())

    def test_fleet_rejects_skill_storage_before_creating_files(self) -> None:
        target = SCRIPTS.parent / "forbidden-test-state"
        result = self.cli(["fleet", "--fleet-dir", str(target), "init"])
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(target.exists())

    @unittest.skipUnless(LINUX, "Linux process-incarnation tracking")
    def test_fleet_start_returns_while_detached_worker_completes(self) -> None:
        self.make_fleet({"MOCK_DELAY": "1"})
        config = json.loads((self.path / "fleet.json").read_text())
        config["workers"]["one"]["tasks"] = ["finish a background goal"]
        atomic_json(self.path / "fleet.json", config)
        State(self.path / "state.db")
        result = self.cli(["fleet", "--fleet-dir", str(self.path), "start", "one"])
        self.assertEqual(result.returncode, 0, result.stderr)
        started = json.loads(result.stdout)
        pid = started["pid"]
        incarnation = identity(pid)
        db = State(self.path / "state.db")
        try:
            deadline = time.monotonic() + 12
            while not db.worker("one").get("completed") or (incarnation is not None and identity(pid) == incarnation):
                self.assertLess(time.monotonic(), deadline, Path(started["log"]).read_text())
                time.sleep(0.02)
            self.assertEqual(db.worker("one")["turn_index"], 1)
            self.assertFalse(db.snapshot()["leases"])
        finally:
            if incarnation is not None and identity(pid) == incarnation:
                os.kill(pid, signal.SIGKILL)


@unittest.skipUnless(LINUX, "Linux process groups, parent death and /proc")
class ProcessIsolationTests(TemporaryWorkspace, unittest.TestCase):
    def test_guard_retains_owner_fences_until_stubborn_child_is_reaped(self) -> None:
        entered = self.path / "child-pid"
        child_code = (
            "import os,signal,sys,time; from pathlib import Path; "
            "signal.signal(signal.SIGTERM,signal.SIG_IGN); Path(sys.argv[1]).write_text(str(os.getpid()))\n"
            "while True: time.sleep(.02)\n"
        )
        fences = [self.path / "slot.runtime.lock", self.path / "worker.runtime.lock", self.path / "cwd.runtime.lock"]
        env = command_environment(
            CODEX_FLEET_PARENT_PID=str(os.getpid()),
            CODEX_FLEET_RUNTIME_FENCE=str(fences[0]),
            CODEX_FLEET_OWNER_FENCES=json.dumps([str(path) for path in fences[1:]]),
        )
        with (self.path / "guardian.log").open("w") as output:
            process = subprocess.Popen([sys.executable, "-B", str(SCRIPTS / "codex_fleet" / "guard.py"),
                                        sys.executable, "-B", "-c", child_code, str(entered)],
                                       env=env, stdin=subprocess.DEVNULL, stdout=output, stderr=output)
            child_pid = None
            try:
                deadline = time.monotonic() + 5
                while not entered.exists() or not entered.read_text().strip():
                    self.assertIsNone(process.poll(), (self.path / "guardian.log").read_text())
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(0.02)
                child_pid = int(entered.read_text())
                process.terminate()
                time.sleep(0.05)
                self.assertIsNone(process.poll(), "guardian returned before the stubborn child was reaped")
                self.assertIsNotNone(identity(child_pid))
                for fence in fences:
                    with self.assertRaises(BlockingIOError):
                        with FileLock(fence):
                            pass
                process.wait(5)
                self.assertIsNone(identity(child_pid))
                for fence in fences:
                    with FileLock(fence):
                        pass
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(5)

    def test_worker_crash_reaps_runtime_and_preserves_peer(self) -> None:
        workers = {}
        for name in ("one", "two", "three"):
            workdir = self.path / ("repo-" + name)
            workdir.mkdir()
            workers[name] = {"cwd": str(workdir), "app_server_command": [sys.executable, "-B", "-u", str(MOCK)],
                             "tasks": ["finish task"], "account": "default"}
        atomic_json(self.path / "fleet.json", {"allowed_workspace_roots": [str(self.path)],
                                               "accounts": {"default": {"env": {"MOCK_DELAY": "1.5"}}}, "workers": workers})
        atomic_json(self.path / "policy.json", validate({"max_parallel_workers": 2, "poll_seconds": 0.05}))
        db = State(self.path / "state.db")
        processes: dict[str, subprocess.Popen] = {}
        logs = []
        try:
            def launch(name):
                output = (self.path / f"{name}.log").open("w")
                logs.append(output)
                processes[name] = subprocess.Popen([sys.executable, "-B", str(CLI), "fleet", "--fleet-dir", str(self.path),
                                                    "run-worker", name, "--max-turns", "1"],
                                                   stdout=output, stderr=output, env=command_environment())
            launch("one")
            launch("two")
            deadline = time.monotonic() + 12
            while not all(db.worker(name).get("turn_id") for name in ("one", "two")):
                for name in ("one", "two"):
                    self.assertIsNone(processes[name].poll(), (self.path / f"{name}.log").read_text())
                self.assertLess(time.monotonic(), deadline)
                time.sleep(0.02)
            guards = []
            for children in Path(f"/proc/{processes['one'].pid}/task").glob("*/children"):
                guards.extend(int(value) for value in children.read_text().split())
            self.assertEqual(len(guards), 1)
            guard = guards[0]
            mock = int(Path(f"/proc/{guard}/task/{guard}/children").read_text().split()[0])
            processes["one"].kill()
            processes["one"].wait(5)
            launch("three")
            for name in ("two", "three"):
                self.assertEqual(processes[name].wait(15), 0, (self.path / f"{name}.log").read_text())
                self.assertEqual(db.worker(name)["turn_index"], 1)
            deadline = time.monotonic() + 5
            while identity(mock) is not None:
                self.assertLess(time.monotonic(), deadline, "crashed worker left its runtime alive")
                time.sleep(0.02)
            self.assertFalse(db.snapshot()["leases"])
        finally:
            for process in processes.values():
                if process.poll() is None:
                    process.kill()
                    process.wait(5)
            for output in logs:
                output.close()


if __name__ == "__main__":
    unittest.main()
