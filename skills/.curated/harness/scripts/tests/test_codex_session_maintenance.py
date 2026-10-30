#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["websockets==15.0.1"]
# ///
"""Synthetic safety contract for the frozen, hyphen-named maintenance script.

Run with ``uv run --script <this-file> --fixtures <existing-owned-private-task-dir>``.
The fixture root MUST already exist, belong to the caller, and have no group or
other permissions. Every run creates a random private child and retains ALL
fixtures, including Unix sockets and partial audits. No /tmp fallback, deletion,
real Codex endpoint, real goal DB, backend process, model or daemon is used.

Failures are deliberately NOT expectedFailure/xfail: a fail-open implementation
must fail this contract. FakeNative models public protocol state, not a claim
that hidden/custom descendants or a real internal GoalID have been verified.
The Unix WS cases exercise Native.call only, not production endpoint discovery,
SO_PEERCRED, production writer locks or real SQLite. Kernel-lock tests use only
retained synthetic files. Socket paths must fit AF_UNIX; only the three Unix WS
tests skip when the explicitly supplied root is too long.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import ExitStack, redirect_stderr, redirect_stdout
import copy
import fcntl
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
import traceback
import unittest
from unittest.mock import AsyncMock, patch

sys.dont_write_bytecode = True

SCRIPT = Path(__file__).resolve().parents[1] / "codex-session-maintenance.py"
SPEC = importlib.util.spec_from_file_location("_codex_session_maintenance_contract", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Cannot load sibling maintenance script")
M = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = M  # Required for decorators/introspection in dynamic modules.
SPEC.loader.exec_module(M)

ROOT = "11111111-1111-4111-8111-111111111111"
CHILD = "22222222-2222-4222-8222-222222222222"
READS = {"thread/read", "thread/goal/get", "thread/queue/list", "thread/list",
         "thread/backgroundTerminals/list"}
WRITES = {"thread/goal/set", "turn/interrupt", "thread/archive", "thread/unarchive"}
FIXTURES: Path | None = None


def checked_root(value: str) -> Path:
    candidate = Path(value).expanduser().absolute()
    try:
        info = candidate.lstat()
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise argparse.ArgumentTypeError("--fixtures must already exist") from error
    if (not stat.S_ISDIR(info.st_mode) or candidate != resolved
            or info.st_uid != os.getuid() or info.st_mode & 0o077):
        raise argparse.ArgumentTypeError("--fixtures must be an owned private non-symlink directory")
    return resolved


def fresh_directory(prefix: str = "c") -> Path:
    if FIXTURES is None:
        raise RuntimeError("Run this test file with mandatory --fixtures; no temporary-directory fallback")
    # mkdtemp, unlike TemporaryDirectory, never removes retained evidence.
    return Path(tempfile.mkdtemp(prefix=prefix, dir=FIXTURES))


class FakeNative:
    """Strict in-memory protocol state machine; no socket, DB or subprocess."""

    def __init__(self, home: Path):
        self.home = home
        self.pid = 424242  # Merely a label; never passed to the operating system.
        self.version = "0.166.0"
        self.writer = self.pid
        self.archived_notifications: set[str] = set()
        self.calls: list[tuple[str, dict]] = []
        self.goal = {"status": "active", "objective": "Synthetic maintenance objective",
                     "tokenBudget": 500, "tokensUsed": 19, "timeUsedSeconds": 7}
        self.internal_id: str | None = "synthetic-internal-goal-id"
        self.thread = {"id": ROOT, "status": {"type": "idle"},
                       "turns": [{"id": "historical", "status": "inProgress"},
                                 {"id": "last", "status": "completed"}],
                       "path": str(home / "sessions" / "synthetic.jsonl"),
                       "source": "cli", "forkedFromId": None, "parentThreadId": None,
                       "ephemeral": False, "cwd": str(home), "model": "synthetic-model",
                       "modelProvider": "synthetic-provider", "reasoningEffort": "medium"}
        self.queue: list[dict] = []
        self.children: list[dict] = []
        self.terminals: list[dict] = []
        self.failures: dict[str, tuple[int, bool]] = {}
        self.seen: dict[str, int] = {}
        self.after_pause = None
        self.after_archive = None
        self.after_unarchive = None
        self.delayed_child = False
        self.stubborn_interrupt = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    def fail(self, method: str, *, occurrence: int = 1, after: bool = False):
        self.failures[method] = (occurrence, after)

    async def call(self, method: str, params: dict):
        if method not in READS | WRITES:
            raise AssertionError(f"Forbidden/unmodelled native call: {method}")
        self.calls.append((method, copy.deepcopy(params)))
        self.seen[method] = self.seen.get(method, 0) + 1
        failure = self.failures.get(method)
        failing = failure is not None and failure[0] == self.seen[method]
        if failing and not failure[1]:
            raise M.Refused("Synthetic uncertain operation; no raw payload")
        if method == "thread/read":
            if self.delayed_child and self.seen.get("thread/unarchive", 0):
                self.archived_notifications.add(CHILD)
            result = {"thread": copy.deepcopy(self.thread)}
        elif method == "thread/goal/get":
            result = {"goal": copy.deepcopy(self.goal)}
        elif method == "thread/queue/list":
            result = {"data": copy.deepcopy(self.queue), "nextCursor": None}
        elif method == "thread/list":
            result = {"data": copy.deepcopy(self.children) if not params["archived"] else [], "nextCursor": None}
        elif method == "thread/backgroundTerminals/list":
            result = {"data": copy.deepcopy(self.terminals), "nextCursor": None}
        elif method == "thread/goal/set":
            if params != {"threadId": ROOT, "status": "paused", "origin": "user"}:
                raise AssertionError("Goal mutation must be status-only, never create/reset/activate")
            if self.goal is None:
                raise AssertionError("A missing goal must not be created")
            self.goal["status"] = "paused"
            if self.after_pause:
                self.after_pause(self)
            result = {"goal": copy.deepcopy(self.goal)}
        elif method == "turn/interrupt":
            if params != {"threadId": ROOT, "turnId": self.thread["turns"][-1]["id"]}:
                raise AssertionError("Only the current last turn may be interrupted")
            if not self.stubborn_interrupt:
                self.thread["turns"][-1]["status"] = "interrupted"
                self.thread["status"] = {"type": "idle"}
            result = {}
        elif method == "thread/archive":
            self.writer = None
            self.thread["status"] = {"type": "notLoaded"}
            self.thread["path"] = str(self.home / "archived_sessions" / "synthetic.jsonl")
            self.archived_notifications.add(ROOT)
            if self.after_archive:
                self.after_archive(self)
            result = {}
        else:  # thread/unarchive does NOT load the thread or resume its goal.
            self.thread["path"] = str(self.home / "sessions" / "synthetic.jsonl")
            if self.after_unarchive:
                self.after_unarchive(self)
            result = {}
        if failing and failure[1]:
            raise M.Refused("Synthetic lost reply after mutation; outcome uncertain")
        return result


class FixtureCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = fresh_directory()
        self.home = self.directory / "home"
        self.home.mkdir(mode=0o700)
        self.native = FakeNative(self.home)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(M, "writer_pid", side_effect=lambda *_: self.native.writer))
        self.stack.enter_context(patch.object(M, "goal_id", side_effect=lambda *_: self.native.internal_id))
        self.stack.enter_context(patch.object(M, "unix_connect", side_effect=AssertionError("No real native socket")))
        self.stack.enter_context(patch.object(M.sqlite3, "connect", side_effect=AssertionError("No real DB")))
        self.stack.enter_context(patch.object(subprocess, "Popen", side_effect=AssertionError("No subprocess/daemon/UI")))
        self.stack.enter_context(patch.object(os, "system", side_effect=AssertionError("No shell/UI")))
        self.audit = M.Audit(self.directory / "audit")
        self.addCleanup(self.audit.close)

    async def asyncTearDown(self):
        for method, params in self.native.calls:
            self.assertIn(method, READS | WRITES)
            if method == "thread/goal/set":
                self.assertEqual(params, {"threadId": ROOT, "status": "paused", "origin": "user"})
        self.assertFalse(any(method in {"thread/resume", "root.resume", "turn/start", "turn.start"}
                             for method, _ in self.native.calls))

    def mutations(self):
        return [(method, params) for method, params in self.native.calls if method not in READS]

    def lifecycle(self):
        return [method for method, _ in self.native.calls if method in {"thread/archive", "thread/unarchive"}]

    async def invoke(self, action="pause", **options):
        return await M.maintain(self.native, ROOT, action, audit=self.audit, **options)

    async def invoke_run(self, action="release"):
        options = argparse.Namespace(home=self.home, thread=ROOT, action=action, apply=True,
                                     reviewed_idle=True, interrupt=False, audit_dir=self.directory / "run-audit")
        with patch.object(M, "Native", return_value=self.native), redirect_stdout(io.StringIO()):
            return await M.run(options)

    def run_audit(self):
        paths = list((self.directory / "run-audit").glob("maintenance-*.jsonl"))
        self.assertEqual(len(paths), 1)
        self.assertEqual(stat.S_IMODE(paths[0].stat().st_mode), 0o600)
        return [json.loads(line) for line in paths[0].read_text().splitlines()]


class ReadOnlyAndPauseTests(FixtureCase):
    async def test_inspect_and_all_non_apply_actions_are_read_only(self):
        for action in ("inspect", "pause", "release", "restore"):
            with self.subTest(action=action):
                self.native.calls.clear()
                before = copy.deepcopy((self.native.thread, self.native.goal, self.native.writer))
                result = await self.invoke(action)
                self.assertFalse(result["changed"])
                self.assertEqual(result["plannedAction"], action)
                self.assertEqual(self.mutations(), [])
                self.assertEqual(before, (self.native.thread, self.native.goal, self.native.writer))

    async def test_inspect_with_apply_still_never_writes(self):
        await self.invoke("inspect", apply=True)
        self.assertEqual(self.mutations(), [])

    async def test_apply_requires_audit_for_every_mutating_action(self):
        for action in ("pause", "release", "restore"):
            with self.subTest(action=action), self.assertRaises(M.Refused):
                await M.maintain(self.native, ROOT, action, apply=True, reviewed_idle=True)
        self.assertEqual(self.mutations(), [])

    async def test_release_and_restore_require_reviewed_idle(self):
        for action in ("release", "restore"):
            with self.subTest(action=action), self.assertRaises(M.Refused):
                await self.invoke(action, apply=True)
        self.assertEqual(self.mutations(), [])

    async def test_status_only_pause_preserves_objective_budget_identity_and_usage(self):
        original = copy.deepcopy(self.native.goal)
        result = await self.invoke(apply=True)
        self.assertEqual(self.native.goal, {**original, "status": "paused"})
        self.assertEqual(self.mutations(), [("thread/goal/set", {"threadId": ROOT, "status": "paused", "origin": "user"})])
        self.assertTrue(result["internalGoalIdVerified"])
        self.assertEqual(result["snapshot"]["goal"]["internalId"], self.native.internal_id)

    async def test_pause_never_creates_missing_goal(self):
        self.native.goal = None
        result = await self.invoke(apply=True)
        self.assertIsNone(result["snapshot"]["goal"])
        self.assertFalse(result["internalGoalIdVerified"])
        self.assertEqual(self.mutations(), [])

    async def test_release_without_goal_does_not_create_one(self):
        self.native.goal = None
        await self.invoke("release", apply=True, reviewed_idle=True)
        self.assertIsNone(self.native.goal)
        self.assertNotIn("thread/goal/set", [method for method, _ in self.mutations()])

    async def test_terminal_and_already_paused_goals_remain_unchanged(self):
        for status in ("complete", "budgetLimited", "paused"):
            with self.subTest(status=status):
                self.native.goal["status"] = status
                original = copy.deepcopy(self.native.goal)
                self.native.calls.clear()
                await self.invoke(apply=True)
                self.assertEqual(self.native.goal, original)
                self.assertEqual(self.mutations(), [])

    async def test_blocked_and_usage_limited_goals_can_be_paused(self):
        for status in ("blocked", "usageLimited"):
            with self.subTest(status=status):
                self.native.goal["status"] = status
                await self.invoke(apply=True)
                self.assertEqual(self.native.goal["status"], "paused")

    async def test_unknown_internal_id_is_not_claimed_verified(self):
        self.native.internal_id = None
        result = await self.invoke(apply=True)
        self.assertFalse(result["internalGoalIdVerified"])
        self.assertIsNone(result["snapshot"]["goal"]["internalId"])

    async def test_unknown_internal_id_refuses_archive(self):
        self.native.internal_id = None
        with self.assertRaises(M.Refused):
            await self.invoke("release", apply=True, reviewed_idle=True)
        self.assertEqual(self.lifecycle(), [])

    async def test_none_budget_is_preserved(self):
        self.native.goal["tokenBudget"] = None
        await self.invoke(apply=True)
        self.assertIsNone(self.native.goal["tokenBudget"])

    async def test_none_budget_becoming_non_none_is_refused(self):
        self.native.goal["tokenBudget"] = None
        self.native.after_pause = lambda n: n.goal.update(tokenBudget=1)
        with self.assertRaises(M.Refused):
            await self.invoke(apply=True)

    async def test_goal_identity_objective_budget_and_usage_regressions_are_refused(self):
        cases = {
            "objective": lambda n: n.goal.update(objective="Replaced objective"),
            "budget": lambda n: n.goal.update(tokenBudget=501),
            "id": lambda n: setattr(n, "internal_id", "different-id"),
            "tokens": lambda n: n.goal.update(tokensUsed=0),
            "seconds": lambda n: n.goal.update(timeUsedSeconds=0),
            "active": lambda n: n.goal.update(status="active"),
            "disappeared": lambda n: setattr(n, "goal", None),
        }
        original = copy.deepcopy(self.native.goal)
        for label, mutate in cases.items():
            with self.subTest(invariant=label):
                self.native.goal = copy.deepcopy(original)
                self.native.internal_id = "synthetic-internal-goal-id"
                self.native.after_pause = mutate
                with self.assertRaises(M.Refused):
                    await self.invoke(apply=True)
                self.assertEqual(self.lifecycle(), [])

    async def test_cumulative_usage_may_increase_but_is_never_reset(self):
        self.native.after_pause = lambda n: n.goal.update(tokensUsed=20, timeUsedSeconds=8)
        result = await self.invoke(apply=True)
        self.assertEqual((result["snapshot"]["goal"]["tokens"], result["snapshot"]["goal"]["seconds"]), (20, 8))

    async def test_pause_without_explicit_interrupt_does_not_touch_turns(self):
        self.native.thread["status"] = {"type": "active"}
        self.native.thread["turns"][-1]["status"] = "inProgress"
        original = copy.deepcopy(self.native.thread["turns"])
        await self.invoke(apply=True)
        self.assertEqual(self.native.thread["turns"], original)
        self.assertNotIn("turn/interrupt", [method for method, _ in self.mutations()])

    async def test_explicit_interrupt_targets_only_current_last_turn_once(self):
        self.native.thread["status"] = {"type": "active"}
        self.native.thread["turns"][-1]["status"] = "inProgress"
        historical = copy.deepcopy(self.native.thread["turns"][0])
        await self.invoke(apply=True, interrupt=True)
        interruptions = [params for method, params in self.mutations() if method == "turn/interrupt"]
        self.assertEqual(interruptions, [{"threadId": ROOT, "turnId": "last"}])
        self.assertEqual(self.native.thread["turns"][0], historical)
        self.assertEqual(self.native.thread["turns"][-1]["status"], "interrupted")

    async def test_interrupt_never_chooses_a_historical_in_progress_turn(self):
        self.native.thread["status"] = {"type": "active"}
        with self.assertRaises(M.Refused):
            await self.invoke(apply=True, interrupt=True)
        self.assertNotIn("turn/interrupt", [method for method, _ in self.mutations()])

    async def test_wrong_backend_cannot_even_pause_or_interrupt(self):
        for interrupt in (False, True):
            with self.subTest(interrupt=interrupt):
                self.native.calls.clear()
                self.native.writer = self.native.pid + 1
                self.native.thread["status"] = {"type": "active"}
                self.native.thread["turns"][-1]["status"] = "inProgress"
                with self.assertRaises(M.Refused):
                    await self.invoke(apply=True, interrupt=interrupt)
                self.assertEqual(self.mutations(), [])
                self.assertEqual(self.native.goal["status"], "active")

    async def test_unconfirmed_interrupt_is_not_resent(self):
        self.native.thread["status"] = {"type": "active"}
        self.native.thread["turns"][-1]["status"] = "inProgress"
        self.native.stubborn_interrupt = True
        with patch.object(M.asyncio, "sleep", new=AsyncMock()), self.assertRaises(M.Refused):
            await self.invoke(apply=True, interrupt=True)
        self.assertEqual(self.native.seen.get("turn/interrupt"), 1)
        self.assertEqual(self.lifecycle(), [])


class ReleaseTests(FixtureCase):
    async def test_reviewed_single_root_archive_unarchive_never_resumes(self):
        original = copy.deepcopy(self.native.goal)
        result = await self.invoke("release", apply=True, reviewed_idle=True)
        self.assertEqual(self.lifecycle(), ["thread/archive", "thread/unarchive"])
        self.assertIsNone(self.native.writer)
        self.assertEqual(self.native.goal, {**original, "status": "paused"})
        self.assertEqual(result["snapshot"]["status"], "notLoaded")
        self.assertFalse(result["snapshot"]["archived"])
        self.assertEqual(result["snapshot"]["thread"], ROOT)

    async def test_writer_free_release_only_pauses_no_archive_or_unarchive(self):
        for status in ("idle", "notLoaded"):
            with self.subTest(status=status):
                self.native.calls.clear()
                self.native.writer = None
                self.native.thread["status"] = {"type": status}
                self.native.goal["status"] = "active"
                result = await self.invoke("release", apply=True, reviewed_idle=True)
                self.assertEqual(self.lifecycle(), [])
                self.assertEqual(self.native.goal["status"], "paused")
                self.assertIsNone(result["snapshot"]["writerPid"])

    async def test_unsafe_or_unknown_states_refuse_archive(self):
        cases = {
            "busy": lambda n: n.thread.update(status={"type": "active"}),
            "unfinished": lambda n: n.thread["turns"][-1].update(status="inProgress"),
            "queued": lambda n: n.queue.append({"id": "queued"}),
            "children": lambda n: n.children.append({"id": CHILD}),
            "custom": lambda n: n.thread.update(source={"custom": "synthetic"}),
            "unknown-source": lambda n: n.thread.update(source="unknown"),
            "fork": lambda n: n.thread.update(forkedFromId=CHILD),
            "archived": lambda n: n.thread.update(path=str(n.home / "archived_sessions" / "x")),
            "unknown-status": lambda n: n.thread.update(status={"type": "future-state"}),
            "system-error": lambda n: n.thread.update(status={"type": "systemError"}),
            "unknown-archive-path": lambda n: n.thread.update(path=None),
            "background": lambda n: n.terminals.append({"id": "terminal"}),
            "wrongowner": lambda n: setattr(n, "writer", n.pid + 1),
            "ephemeral": lambda n: n.thread.update(ephemeral=True),
            "unknown-ephemeral": lambda n: n.thread.pop("ephemeral"),
            "child-root": lambda n: n.thread.update(parentThreadId=CHILD),
            "unloaded-writer": lambda n: n.thread.update(status={"type": "notLoaded"}),
        }
        for label, mutate in cases.items():
            with self.subTest(state=label):
                self.native = FakeNative(self.home)
                mutate(self.native)
                with self.assertRaises(M.Refused):
                    await self.invoke("release", apply=True, reviewed_idle=True)
                self.assertEqual(self.lifecycle(), [])

    async def test_unknown_last_turn_status_refuses_archive(self):
        # Contract, not a description of current implementation: fail closed.
        self.native.thread["turns"][-1]["status"] = "future-turn-state"
        with self.assertRaises(M.Refused):
            await self.invoke("release", apply=True, reviewed_idle=True)
        self.assertEqual(self.lifecycle(), [])

    async def test_background_listing_native_error_does_not_mean_zero(self):
        original = self.native.call

        async def unavailable(method, params):
            if method == "thread/backgroundTerminals/list":
                raise M.NativeError(method, -32601)
            return await original(method, params)

        with patch.object(self.native, "call", side_effect=unavailable), self.assertRaises(M.Refused):
            await self.invoke("release", apply=True, reviewed_idle=True)
        self.assertEqual(self.lifecycle(), [])

    async def test_new_last_turn_after_pause_stops_before_any_lifecycle_write(self):
        for action in ("pause", "release", "restore"):
            with self.subTest(action=action):
                self.native = FakeNative(self.home)
                if action == "restore":
                    self.native.writer = None
                    self.native.thread["status"] = {"type": "notLoaded"}
                    self.native.thread["path"] = str(self.home / "archived_sessions" / "synthetic.jsonl")
                self.native.after_pause = lambda n: n.thread["turns"][-1].update(id="new", status="completed")
                with self.assertRaises(M.Refused):
                    await self.invoke(action, apply=True, reviewed_idle=True)
                self.assertEqual(self.lifecycle(), [])
                self.assertEqual(self.mutations(), [("thread/goal/set", {
                    "threadId": ROOT, "status": "paused", "origin": "user"})])
                self.assertEqual(self.native.goal["status"], "paused")

    async def test_restore_rechecks_archived_writer_free_unloaded_before_unarchive(self):
        cases = {
            "archive-location": lambda n: n.thread.update(path=str(n.home / "sessions" / "synthetic.jsonl")),
            "writer": lambda n: setattr(n, "writer", n.pid),
            "runtime": lambda n: n.thread.update(status={"type": "idle"}),
        }
        for label, mutate in cases.items():
            with self.subTest(changed=label):
                self.native = FakeNative(self.home)
                self.native.writer = None
                self.native.thread["status"] = {"type": "notLoaded"}
                self.native.thread["path"] = str(self.home / "archived_sessions" / "synthetic.jsonl")
                self.native.after_pause = mutate
                with self.assertRaises(M.Refused):
                    await self.invoke("restore", apply=True, reviewed_idle=True)
                self.assertEqual(self.lifecycle(), [])
                self.assertEqual([method for method, _ in self.mutations()], ["thread/goal/set"])

    async def test_archive_readback_must_confirm_archived_root_before_unarchive(self):
        # A released writer alone is not evidence that archive actually happened.
        self.native.after_archive = lambda n: n.thread.update(path=str(n.home / "sessions" / "synthetic.jsonl"))
        with self.assertRaises(M.Refused):
            await self.invoke_run()
        self.assertEqual(self.lifecycle(), ["thread/archive"])
        self.assertEqual(self.run_audit()[-1]["stage"], "stopped")

    async def test_archive_readback_rejects_new_turn_before_unarchive(self):
        self.native.after_archive = lambda n: n.thread["turns"].append({"id": "unexpected", "status": "completed"})
        with self.assertRaises(M.Refused):
            await self.invoke_run()
        self.assertEqual(self.lifecycle(), ["thread/archive"])
        self.assertEqual(self.run_audit()[-1]["stage"], "stopped")

    async def test_archive_that_keeps_writer_is_not_blindly_unarchived(self):
        self.native.after_archive = lambda n: setattr(n, "writer", n.pid)
        with self.assertRaises(M.Refused):
            await self.invoke_run()
        self.assertEqual(self.lifecycle(), ["thread/archive"])
        self.assertEqual(self.run_audit()[-1]["stage"], "stopped")

    async def test_observed_child_archive_before_unarchive_is_partial_not_success(self):
        self.native.after_archive = lambda n: n.archived_notifications.add(CHILD)
        with self.assertRaises(M.Refused):
            await self.invoke_run()
        self.assertEqual(self.lifecycle(), ["thread/archive"])
        self.assertEqual(self.run_audit()[-1]["stage"], "stopped")

    async def test_final_readback_rejects_goal_activation_and_new_turn(self):
        for label in ("goal-active", "new-turn", "writer-reacquired"):
            with self.subTest(race=label):
                self.native = FakeNative(self.home)
                if label == "goal-active":
                    self.native.after_unarchive = lambda n: n.goal.update(status="active")
                elif label == "new-turn":
                    self.native.after_unarchive = lambda n: n.thread["turns"].append({"id": "new", "status": "completed"})
                else:
                    self.native.after_unarchive = lambda n: setattr(n, "writer", n.pid)
                with self.assertRaises(M.Refused):
                    await self.invoke("release", apply=True, reviewed_idle=True)
                self.assertEqual(self.lifecycle(), ["thread/archive", "thread/unarchive"])

    async def test_delayed_child_archive_notification_is_not_tree_success(self):
        self.native.delayed_child = True
        with self.assertRaises(M.Refused):
            await self.invoke_run()
        self.assertIn(CHILD, self.native.archived_notifications)
        records = self.run_audit()
        self.assertEqual(records[-1]["stage"], "stopped")
        self.assertNotIn("verified", [record["stage"] for record in records])
        self.assertEqual(self.lifecycle(), ["thread/archive", "thread/unarchive"])

    async def test_partial_archive_unarchive_and_read_failures_keep_audit_no_retry(self):
        cases = (("thread/archive", 1, False), ("thread/archive", 1, True),
                 ("thread/read", 3, False), ("thread/unarchive", 1, False),
                 ("thread/unarchive", 1, True), ("thread/read", 4, False))
        for method, occurrence, after in cases:
            with self.subTest(method=method, occurrence=occurrence, lost_reply=after):
                # Each subcase gets its own retained run directory and audit.
                self.directory = fresh_directory(prefix="p")
                self.home = self.directory / "home"
                self.home.mkdir(mode=0o700)
                self.native = FakeNative(self.home)
                self.native.fail(method, occurrence=occurrence, after=after)
                with self.assertRaises(M.Refused):
                    await self.invoke_run()
                records = self.run_audit()
                stages = [record["stage"] for record in records]
                self.assertEqual(stages[-1], "stopped")
                self.assertNotIn("verified", stages)
                self.assertIn("before", stages)
                self.assertIn("partial", records[-1]["data"]["outcome"])
                self.assertEqual(self.native.seen[method], occurrence)
                self.assertLessEqual(self.native.seen.get("thread/archive", 0), 1)
                self.assertLessEqual(self.native.seen.get("thread/unarchive", 0), 1)
                if method == "thread/archive" or (method == "thread/read" and occurrence == 3):
                    self.assertNotIn("thread/unarchive", self.lifecycle())
                if method == "thread/archive" and after:
                    self.assertIsNone(self.native.writer)
                    self.assertIn("archived_sessions", self.native.thread["path"])

    async def test_goal_set_lost_reply_is_partial_not_retried(self):
        self.native.fail("thread/goal/set", after=True)
        with self.assertRaises(M.Refused):
            await self.invoke_run(action="pause")
        self.assertEqual(self.native.goal["status"], "paused")
        self.assertEqual(self.native.seen["thread/goal/set"], 1)
        self.assertEqual(self.lifecycle(), [])
        self.assertEqual(self.run_audit()[-1]["stage"], "stopped")

    async def test_explicit_restore_only_unarchives_selected_uuid_never_resumes(self):
        self.native.writer = None
        self.native.thread["status"] = {"type": "notLoaded"}
        self.native.thread["path"] = str(self.home / "archived_sessions" / "synthetic.jsonl")
        result = await self.invoke("restore", apply=True, reviewed_idle=True)
        self.assertEqual(self.lifecycle(), ["thread/unarchive"])
        self.assertEqual(self.native.goal["status"], "paused")
        self.assertEqual(result["snapshot"]["thread"], ROOT)
        self.assertFalse(result["snapshot"]["archived"])


class ObservationTests(FixtureCase):
    async def test_pagination_incomplete_and_repeated_cursor_refuse(self):
        for reply in ({"data": []}, {"nextCursor": None}, {"data": [], "nextCursor": "same"}):
            with self.subTest(reply=reply):
                fake = AsyncMock()
                fake.call.return_value = reply
                with self.assertRaises(M.Refused):
                    await M.pages(fake, "thread/queue/list", {})
                self.assertLessEqual(fake.call.await_count, 2)

    async def test_both_archived_and_unarchived_descendant_lists_are_requested(self):
        await self.invoke("inspect")
        params = [params for method, params in self.native.calls if method == "thread/list"]
        self.assertEqual([item["archived"] for item in params], [False, True])
        self.assertTrue(all(item["ancestorThreadId"] == ROOT and item["useStateDbOnly"] for item in params))

    async def test_unknown_latest_turn_shape_or_id_refuses_before_any_write(self):
        for latest in (None, {}, {"status": "completed"}, {"id": "", "status": "completed"},
                       {"id": 1, "status": "completed"}, {"id": "last"},
                       {"id": "last", "status": "future-state"}):
            with self.subTest(latest=latest):
                self.native.thread["turns"][-1] = latest
                with self.assertRaises(M.Refused):
                    await self.invoke("release", apply=True, reviewed_idle=True)
                self.assertEqual(self.mutations(), [])

    async def test_missing_budget_key_is_unknown_not_an_unlimited_budget(self):
        for action in ("pause", "release", "restore"):
            with self.subTest(action=action):
                self.native = FakeNative(self.home)
                self.native.goal.pop("tokenBudget")
                with self.assertRaises(M.Refused):
                    await self.invoke(action, apply=True, reviewed_idle=True)
                self.assertEqual(self.mutations(), [])
                self.assertEqual(self.native.goal["status"], "active")

    async def test_unknown_goal_is_not_treated_as_missing(self):
        original = copy.deepcopy(self.native.goal)
        for goal in ({}, {**original, "status": "future"}, {**original, "tokensUsed": -1},
                     {**original, "timeUsedSeconds": True}, {**original, "tokenBudget": "500"}):
            with self.subTest(goal=goal):
                self.native.goal = goal
                with self.assertRaises(M.Refused):
                    await self.invoke("release", apply=True, reviewed_idle=True)
                self.assertEqual(self.mutations(), [])


class CliAndFixtureTests(unittest.TestCase):
    def test_default_cli_action_is_inspect_without_apply(self):
        with patch.object(sys, "argv", [str(SCRIPT), "--thread", ROOT]), \
                patch.object(M, "run", new=AsyncMock()) as run, patch.object(M.os, "umask"):
            M.main()
        options = run.await_args.args[0]
        self.assertEqual(options.action, "inspect")
        self.assertFalse(options.apply)

    def test_cli_apply_without_audit_refuses_before_native_connection(self):
        for action in ("pause", "release", "restore"):
            with self.subTest(action=action), patch.object(sys, "argv", [str(SCRIPT), action, "--thread", ROOT, "--apply"]), \
                    patch.object(M, "run", new=AsyncMock()) as run, redirect_stderr(io.StringIO()), \
                    self.assertRaises(SystemExit) as stopped:
                M.main()
            self.assertEqual(stopped.exception.code, 2)
            run.assert_not_awaited()

    def test_cli_interrupt_requires_pause_apply(self):
        for arguments in (("pause",), ("inspect", "--apply"), ("release", "--apply"), ("restore", "--apply")):
            with self.subTest(arguments=arguments), patch.object(sys, "argv", [str(SCRIPT), *arguments, "--thread", ROOT,
                                                                            "--audit-dir", str(FIXTURES), "--interrupt"]), \
                    patch.object(M, "run", new=AsyncMock()) as run, redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                M.main()
            run.assert_not_awaited()

    def test_fixture_root_must_exist_be_owned_private_and_not_symlink(self):
        directory = fresh_directory()
        self.assertEqual(checked_root(str(directory)), directory)
        with self.assertRaises(argparse.ArgumentTypeError):
            checked_root(str(directory / "absent"))
        public = directory / "public"
        public.mkdir(mode=0o755)
        public.chmod(0o755)
        with self.assertRaises(argparse.ArgumentTypeError):
            checked_root(str(public))
        link = directory / "link"
        link.symlink_to(directory, target_is_directory=True)
        with self.assertRaises(argparse.ArgumentTypeError):
            checked_root(str(link))
        with patch.object(os, "getuid", return_value=os.getuid() + 1), self.assertRaises(argparse.ArgumentTypeError):
            checked_root(str(directory))

    def test_runner_requires_explicit_fixtures_no_fallback(self):
        with patch.object(sys, "argv", [str(Path(__file__))]), redirect_stderr(io.StringIO()), \
                self.assertRaises(SystemExit) as stopped:
            main()
        self.assertEqual(stopped.exception.code, 2)

    def test_audit_rejects_public_symlink_and_wrong_owner_directories(self):
        directory = fresh_directory()
        public = directory / "public-audit"
        public.mkdir(mode=0o755)
        public.chmod(0o755)
        with self.assertRaises(M.Refused):
            M.Audit(public)
        link = directory / "audit-link"
        link.symlink_to(directory, target_is_directory=True)
        with self.assertRaises(M.Refused):
            M.Audit(link)
        with patch.object(os, "getuid", return_value=os.getuid() + 1), self.assertRaises(M.Refused):
            M.Audit(directory)

    def test_dynamic_import_registered_without_bytecode(self):
        self.assertIs(sys.modules[SPEC.name], M)
        self.assertTrue(sys.dont_write_bytecode)

    def test_native_version_parser_accepts_exact_supported_native_agents(self):
        for version in ("0.165.0", "0.166.0"):
            for originator, platform, terminal in (
                    ("codex_cli_rs", "Ubuntu 24.04; x86_64", "unknown"),
                    ("Codex Desktop", "Mac OS 15.5; arm64", "Apple_Terminal/455.1")):
                agent = f"{originator}/{version} ({platform}) {terminal}"
                with self.subTest(agent=agent):
                    self.assertEqual(M.parse_version(agent), version)

    def test_native_version_parser_rejects_ambiguous_prerelease_or_missing_agent(self):
        for agent in (
                "custom/0.165.0 note/0.999.0 (Ubuntu 24.04; x86_64) unknown",
                "codex_cli_rs/0.165.0-beta.1 (Ubuntu 24.04; x86_64) unknown",
                "codex_cli_rs/0.166.0+build.1 (Ubuntu 24.04; x86_64) unknown",
                "codex_cli_rs/0.999.0 (Ubuntu 24.04; x86_64) unknown",
                "codex_cli_rs/0.165.0", "0.165.0", "", None,
                "codex_cli_rs/0.165.0 (Ubuntu 24.04; x86_64) unknown\n",
                "unsafe originator/0.165.0 (Ubuntu 24.04; x86_64) unknown"):
            with self.subTest(agent=agent), self.assertRaises(M.Refused):
                M.parse_version(agent)

    def test_identifier_requires_original_lowercase_full_uuid(self):
        self.assertEqual(M.identifier(ROOT), ROOT)
        for value in (ROOT[:8], ROOT.upper().replace("1", "A", 1), None, "../thread", "thread"):
            with self.subTest(value=value), self.assertRaises(M.Refused):
                M.identifier(value)


class WriterKernelFixtureTests(unittest.TestCase):
    """Real Linux flock/proc identity on retained fixtures, never Codex files."""

    def setUp(self):
        self.directory = fresh_directory(prefix="k")
        self.home = self.directory / "home"
        self.home.mkdir(mode=0o700)
        self.locks = self.home / "thread-writer-locks"
        self.locks.mkdir(mode=0o755)
        self.locks.chmod(0o755)
        self.path = self.locks / (ROOT + ".lock")
        self.path.write_bytes(b"synthetic-untrusted-pid-payload=987654321\n")
        self.path.chmod(0o664)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(M, "unix_connect", side_effect=AssertionError("No Codex endpoint")))
        self.stack.enter_context(patch.object(M.sqlite3, "connect", side_effect=AssertionError("No DB")))
        self.stack.enter_context(patch.object(subprocess, "Popen", side_effect=AssertionError("No daemon")))

    def evidence(self):
        info = self.path.stat()
        return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
                info.st_size, info.st_mtime_ns, info.st_ctime_ns,
                self.path.read_bytes(), self.locks.stat().st_mode)

    def test_owned_0664_unlocked_file_is_read_only_and_returns_none(self):
        before = self.evidence()
        original_open = os.open
        with patch.object(M.os, "open", wraps=original_open) as opened:
            self.assertIsNone(M.writer_pid(self.home, ROOT))
        opened.assert_called_once()
        self.assertEqual(Path(opened.call_args.args[0]), self.path)
        flags = opened.call_args.args[1]
        self.assertEqual(flags & os.O_ACCMODE, os.O_RDONLY)
        self.assertTrue(flags & os.O_NOFOLLOW)
        self.assertEqual(self.evidence(), before)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o664)
        self.assertEqual(stat.S_IMODE(self.locks.stat().st_mode), 0o755)

    def test_kernel_owner_is_current_pid_not_payload_and_lock_is_untouched(self):
        before = self.evidence()
        with self.path.open("rb") as holder:
            fcntl.flock(holder.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                self.assertEqual(M.writer_pid(self.home, ROOT), os.getpid())
                self.assertEqual(self.evidence(), before)
                with self.path.open("rb") as probe:
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(probe.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                fcntl.flock(holder.fileno(), fcntl.LOCK_UN)
        self.assertIsNone(M.writer_pid(self.home, ROOT))
        self.assertEqual(self.evidence(), before)

    def test_world_writable_lock_file_is_refused_without_repair(self):
        self.path.chmod(0o666)
        before = self.evidence()
        with self.assertRaises(M.Refused):
            M.writer_pid(self.home, ROOT)
        self.assertEqual(self.evidence(), before)

    def test_group_or_world_writable_lock_directory_is_refused_without_repair(self):
        for mode in (0o775, 0o777):
            with self.subTest(mode=oct(mode)):
                self.locks.chmod(mode)
                before = self.evidence()
                with self.assertRaises(M.Refused):
                    M.writer_pid(self.home, ROOT)
                self.assertEqual(self.evidence(), before)

    def test_symlink_lock_file_is_refused_and_target_is_untouched(self):
        link = self.locks / (CHILD + ".lock")
        link.symlink_to(self.path)
        before = self.evidence()
        link_inode = link.lstat().st_ino
        with self.assertRaises(M.Refused):
            M.writer_pid(self.home, CHILD)
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.lstat().st_ino, link_inode)
        self.assertEqual(self.evidence(), before)


class NativeUnixWebSocketTests(unittest.IsolatedAsyncioTestCase):
    """Real loopback Unix WS peers, always synthetic; sockets are retained."""

    async def asyncSetUp(self):
        self.directory = fresh_directory(prefix="w")
        self.counter = 0
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(M.sqlite3, "connect", side_effect=AssertionError("No DB")))
        self.stack.enter_context(patch.object(subprocess, "Popen", side_effect=AssertionError("No daemon")))

    async def exchange(self, handler, operation):
        from websockets.asyncio.client import unix_connect
        from websockets.asyncio.server import unix_serve

        self.counter += 1
        path = self.directory / ("s" + str(self.counter))
        if len(os.fsencode(path)) >= 108:
            self.skipTest("Explicit --fixtures path too long for synthetic AF_UNIX; use a shorter owned private task directory")
        listener = socket.socket(socket.AF_UNIX)
        listener.bind(str(path))
        path.chmod(0o600)
        listener.listen(4)
        listener.setblocking(False)
        options = {"cleanup_socket": False} if sys.version_info >= (3, 13) else {}
        try:
            async with unix_serve(handler, sock=listener, close_timeout=0.2, logger=M.QUIET, **options):
                async with unix_connect(path=str(path), open_timeout=2, close_timeout=0.2, logger=M.QUIET) as ws:
                    native = M.Native(self.directory)
                    native.ws = ws
                    async with asyncio.timeout(3):
                        return await operation(native)
        finally:
            listener.close()  # Closing a descriptor does not delete its fixture socket.
            self.assertTrue(path.exists(), "Synthetic socket evidence must not be auto-deleted")
        # No unlink/rmtree/TemporaryDirectory/automatic cleanup anywhere.

    def assert_private_exception(self, error, secrets):
        public = str(error) + "".join(traceback.format_exception(error))
        for secret in secrets:
            self.assertNotIn(secret, public)
        self.assertIsInstance(error, M.Refused)

    async def test_notifications_and_approval_requests_do_not_trigger_work(self):
        received = []

        async def server(ws):
            request = json.loads(await ws.recv())
            received.append(request)
            await ws.send(json.dumps({"method": "thread/archived", "params": {"threadId": CHILD}}))
            await ws.send(json.dumps({"id": "approval-1", "method": "item/commandExecution/requestApproval", "params": {}}))
            received.append(json.loads(await ws.recv()))
            await ws.send(json.dumps({"id": request["id"], "result": {"synthetic": True}}))

        async def operation(native):
            result = await native.call("thread/read", {"threadId": ROOT})
            self.assertEqual(result, {"synthetic": True})
            self.assertEqual(native.archived_notifications, {CHILD})

        await self.exchange(server, operation)
        self.assertEqual(received[0]["method"], "thread/read")
        self.assertEqual(received[1], {"id": "approval-1", "error": {"code": -32601, "message": "Maintenance never grants approvals."}})
        self.assertEqual(len(received), 2)

    async def test_native_error_message_data_and_noninteger_code_are_redacted(self):
        for code in (-32000, "CODE_PRIVATE_SENTINEL"):
            secrets = ["MESSAGE_PRIVATE_SENTINEL", "DATA_PRIVATE_SENTINEL", "CODE_PRIVATE_SENTINEL"]

            async def server(ws):
                request = json.loads(await ws.recv())
                await ws.send(json.dumps({"id": request["id"], "error": {
                    "code": code, "message": secrets[0], "data": {"token": secrets[1]}}}))

            async def operation(native):
                with self.assertRaises(M.NativeError) as raised:
                    await native.call("thread/archive", {"threadId": ROOT})
                self.assert_private_exception(raised.exception, secrets)
                self.assertEqual(raised.exception.code, code if type(code) is int else "unknown")

            with self.subTest(code=code):
                await self.exchange(server, operation)

    async def test_close_reason_and_malformed_transport_are_redacted_no_retry(self):
        for malformed in (False, True):
            received = []
            secret = "CLOSE_REASON_PRIVATE_SENTINEL" if not malformed else "MALFORMED_PRIVATE_SENTINEL"

            async def server(ws):
                received.append(json.loads(await ws.recv()))
                if malformed:
                    await ws.send("not-json-" + secret)
                else:
                    await ws.close(code=1011, reason=secret)

            async def operation(native):
                with self.assertRaises(M.Refused) as raised:
                    await native.call("thread/unarchive", {"threadId": ROOT})
                self.assert_private_exception(raised.exception, [secret])
                self.assertIn("uncertain", str(raised.exception))

            with self.subTest(malformed=malformed):
                await self.exchange(server, operation)
                self.assertEqual(len(received), 1)


def main():
    global FIXTURES
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", required=True, type=checked_root,
                        help="Existing caller-owned private task directory; all evidence is retained")
    options, unittest_arguments = parser.parse_known_args()
    FIXTURES = Path(tempfile.mkdtemp(prefix="m", dir=options.fixtures))
    print(f"Retained synthetic fixtures: {FIXTURES}", file=sys.stderr)
    original_hash = hashlib.sha256(SCRIPT.read_bytes()).digest()
    try:
        unittest.main(argv=[sys.argv[0], *unittest_arguments])
    finally:
        if hashlib.sha256(SCRIPT.read_bytes()).digest() != original_hash:
            raise RuntimeError("Frozen maintenance script changed during synthetic tests")


if __name__ == "__main__":
    main()
