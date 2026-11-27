"""Codex SDK transport, effective settings, and child-turn reconciliation."""
from __future__ import annotations

import asyncio
import inspect
import json
import math
import os
import re
import shutil
import sys
import time
from pathlib import Path

from openai_codex import ApprovalMode, AsyncCodex, CodexConfig, Sandbox
from openai_codex.api import AsyncThread
from openai_codex.generated.v2_all import ReasoningEffort
from pydantic import RootModel

from .events import Phase, SubagentTap, unpack
from .guard import terminate_process

DEFAULT_EFFORT = "xhigh"
ROOT_HINT = (
    "You are the primary agent. Complete the assigned task, verify repository gates, "
    "and report evidence. Delegate independent work when useful and permitted. "
    "This is a single-run execution. Do not end a turn while spawned agents are "
    "still running in expectation of interactive mailbox wake-ups. Loop "
    "wait_agent(timeout_ms=300000) until all needed delegated work finishes, including "
    "after sending a message. Call close_agent on any subagent whose remaining work is no longer "
    "needed before finishing the turn. All agents share a workspace; "
    "coordinate file ownership. Respect runtime capacity errors. Follow-up tasks reuse "
    "existing agents. Keep task instructions and authorization boundaries intact."
)
CHILD_HINT = (
    "You are a delegated agent in a shared workspace. Complete the assigned scope, "
    "coordinate file ownership, verify changes, and report evidence to your parent. "
    "Respect runtime capacity errors and task authorization boundaries."
)


class Raw(RootModel[dict]):
    pass


def version_tuple(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:[-+][\w.-]+)?", value.split()[0])
    if not match:
        raise ValueError(f"invalid semantic version: {value!r}")
    return tuple(map(int, match.groups()))


def native_config(subagents: int) -> dict:
    if type(subagents) is not int or not 0 <= subagents <= 256:
        raise ValueError("subagents must be an integer in [0, 256]")
    return {
        "features.multi_agent": True,
        "features.multi_agent_v2.enabled": True,
        "agents.max_concurrent_threads_per_session": max(1, subagents),
        "features.multi_agent_v2.max_concurrent_threads_per_session": subagents + 1,
        "features.multi_agent_v2.root_agent_usage_hint_text": ROOT_HINT,
        "features.multi_agent_v2.subagent_usage_hint_text": CHILD_HINT,
    }


def merged_environment(account: dict, spec: dict) -> tuple[dict, set[str]]:
    env, removed = os.environ.copy(), set()
    for layer in (account.get("env") or {}, spec.get("env") or {}):
        if not isinstance(layer, dict):
            raise ValueError("env must be an object of strings or null")
        for key, value in layer.items():
            if not isinstance(key, str) or not key or "=" in key or "\0" in key:
                raise ValueError("invalid environment variable name")
            if value is None:
                env.pop(key, None)
                removed.add(key)
            elif isinstance(value, str) and "\0" not in value:
                env[key] = value
                removed.discard(key)
            else:
                raise ValueError(f"env[{key!r}] must be a string or null")
    if account.get("codex_home") is not None:
        env["CODEX_HOME"] = str(Path(account["codex_home"]).expanduser().resolve())
        removed.discard("CODEX_HOME")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    removed.discard("PYTHONDONTWRITEBYTECODE")
    return env, removed


def sandbox_pair(value) -> tuple[str, Sandbox] | None:
    if value is None:
        return None
    mapping = {
        "read-only": ("read-only", Sandbox.read_only),
        "workspace-write": ("workspace-write", Sandbox.workspace_write),
        "danger-full-access": ("danger-full-access", Sandbox.full_access),
        "full-access": ("danger-full-access", Sandbox.full_access),
    }
    if value not in mapping:
        raise ValueError(f"unsupported sandbox: {value!r}")
    return mapping[value]


def approval_pair(value) -> tuple[dict, ApprovalMode] | None:
    if value is None:
        return None
    if value in ("never", "deny_all"):
        return {"approvalPolicy": "never"}, ApprovalMode.deny_all
    if value in ("auto-review", "auto_review"):
        return {"approvalPolicy": "on-request", "approvalsReviewer": "auto_review"}, ApprovalMode.auto_review
    raise ValueError("approval_policy must be never or auto-review (SDK ApprovalMode semantics)")


class Runtime:
    """One private app-server per worker/turn, with persistent native threads."""

    def __init__(self, spec: dict, account: dict, subagents: int):
        self.spec = dict(spec)
        self.native = native_config(subagents)
        self.sandbox = sandbox_pair(spec.get("sandbox"))
        self.approval = approval_pair(spec.get("approval_policy"))
        timeouts = {"rpc_timeout": 120, "child_drain_timeout": 120, "child_active_timeout": 3600,
                    "max_child_drain_timeout": spec.get("child_active_timeout", 3600)}
        for key, default in timeouts.items():
            value = self.spec.setdefault(key, default)
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{key} must be a finite positive number")
        env, removed = merged_environment(account, spec)
        env["CODEX_FLEET_UNSET_ENV"] = json.dumps(sorted(removed))
        env["CODEX_FLEET_PARENT_PID"] = str(os.getpid())
        env["CODEX_FLEET_OWNER_FENCES"] = json.dumps(spec.get("runtime_owner_fences", []))
        if spec.get("runtime_fence"):
            env["CODEX_FLEET_RUNTIME_FENCE"] = str(spec["runtime_fence"])
        else:
            env.pop("CODEX_FLEET_RUNTIME_FENCE", None)
            removed.add("CODEX_FLEET_RUNTIME_FENCE")
            env["CODEX_FLEET_UNSET_ENV"] = json.dumps(sorted(removed))
        command = spec.get("app_server_command")
        if command is None:
            command = [spec.get("codex_bin") or shutil.which("codex") or "codex"]
        if not isinstance(command, (list, tuple)) or not command or any(not isinstance(arg, str) for arg in command):
            raise ValueError("app_server_command must be a nonempty argv array")
        command = list(command)
        for key, value in self.native.items():
            command += ["--config", f"{key}={json.dumps(value, ensure_ascii=False)}"]
        if spec.get("app_server_command") is None:
            command += ["app-server", "--listen", "stdio://"]
        guarded = (sys.executable, "-B", str(Path(__file__).with_name("guard.py")), *command)
        self.codex = AsyncCodex(CodexConfig(cwd=spec["cwd"], env=env, launch_args_override=guarded))
        self.tap = SubagentTap(self.codex)
        self.thread = self.handle = None
        self.reconciled_children: set[str] = set()
        self._closed = False
        self._spawn_task = self._close_task = None

    async def start(self):
        if self._closed or self._close_task is not None:
            raise RuntimeError("a closed Runtime cannot be restarted")
        try:
            # SDK start offloads Popen to a thread. Timing out that await does
            # not stop the thread: keep its task until close can reap its result.
            self._spawn_task = asyncio.create_task(self.codex._client.start())
            await asyncio.wait_for(asyncio.shield(self._spawn_task), self.spec.get("rpc_timeout", 120))
            await asyncio.wait_for(self.codex.__aenter__(), self.spec.get("rpc_timeout", 120))
            metadata = self.codex.metadata
            server = getattr(metadata, "serverInfo", None)
            version = getattr(server, "version", None)
            minimum = self.spec.get("min_cli_version", "0.167.0")
            if not version or version_tuple(version) < version_tuple(minimum):
                raise RuntimeError(f"Codex CLI {version!r} is below required {minimum}")
            config = (await self.rpc("config/read", {"includeLayers": False}))["config"]
            if not self.spec.get("model"):
                self.spec["model"] = config.get("model")
            if self.spec.get("effort") is None:
                self.spec["effort"] = config.get("model_reasoning_effort") or DEFAULT_EFFORT
            v2 = config.get("features", {}).get("multi_agent_v2", {})
            if not isinstance(v2, dict) or v2.get("enabled") is not True:
                raise RuntimeError("runtime did not enable multi_agent_v2")
            for key in ("max_concurrent_threads_per_session", "root_agent_usage_hint_text", "subagent_usage_hint_text"):
                if v2.get(key) != self.native["features.multi_agent_v2." + key]:
                    raise RuntimeError(f"runtime ignored native config {key}; refusing inference")
            return self
        except BaseException:
            await self.close()
            raise

    async def rpc(self, method: str, params: dict) -> dict:
        result = await asyncio.wait_for(
            self.codex._client.request(method, params, response_model=Raw),
            self.spec.get("rpc_timeout", 120),
        )
        return result.root

    async def limits(self) -> dict:
        return await self.rpc("account/rateLimits/read", {})

    async def open_thread(self, thread_id: str | None, instructions: str | None):
        params = {"cwd": self.spec["cwd"], "config": self.native}
        model = self.spec.get("model")
        if model:
            params["model"] = model
        if instructions is not None:
            params["developerInstructions"] = instructions
        if self.sandbox is not None:
            params["sandbox"] = self.sandbox[0]
        if self.approval is not None:
            params.update(self.approval[0])
        if thread_id:
            params["threadId"] = thread_id
        response = await self.rpc("thread/resume" if thread_id else "thread/start", params)
        self.thread = AsyncThread(self.codex, response["thread"]["id"])
        self.tap.root = self.thread.id
        return self.thread.id

    async def begin(self, prompt: str):
        if self.thread is None:
            raise RuntimeError("open a thread before starting a turn")
        options = {"effort": ReasoningEffort(self.spec.get("effort", DEFAULT_EFFORT))}
        if self.sandbox is not None:
            options["sandbox"] = self.sandbox[1]
        if self.approval is not None:
            options["approval_mode"] = self.approval[1]
        self.handle = await asyncio.wait_for(self.thread.turn(prompt, **options), self.spec.get("rpc_timeout", 120))
        return self.handle

    async def reconcile_children(self, rpc_active: set[str]) -> None:
        """Read status for known receivers missing terminal events; never resume."""
        for child in tuple(self.tap.children):
            states = [state for state in self.tap.states.values() if state.thread_id == child]
            if child in self.tap.settled_children or (states and all(state.completed for state in states)):
                rpc_active.discard(child)
                continue
            response = await self.rpc("thread/read", {"threadId": child, "includeTurns": False})
            status = (response.get("thread", {}).get("status") or {}).get("type")
            if status in ("idle", "notLoaded", "systemError"):
                rpc_active.discard(child)
                if states and all(state.completed for state in states):
                    continue
                for state in states:
                    state.phase = Phase.IDLE
                    state.tools.clear()
                    state.completed = True
                if all(state.completed for state in self.tap.states.values() if state.thread_id == child):
                    self.tap.settled_children.add(child)
                self.reconciled_children.add(child)
            elif status == "active":
                rpc_active.add(child)
            else:
                raise RuntimeError(f"unknown child thread status {status!r}: {child}")

    async def run_turn(self, prompt: str, on_event=None, check_alive=None) -> dict:
        """Drain known children and any root turns they wake in the same app-server."""
        active_root, completed = set(), {}
        root_items, root_deltas = {}, {}
        processing_event = False
        last_event = last_progress = 0.0

        async def observe():
            nonlocal processing_event, last_event, last_progress
            async for event in self.tap:
                params = event["params"]
                method, tid = event["method"], params.get("threadId")
                turn_id = params.get("turnId") or (params.get("turn") or {}).get("id")
                if tid == self.thread.id and turn_id:
                    if method == "turn/started" and turn_id not in completed:
                        active_root.add(turn_id)
                    elif method == "turn/completed":
                        active_root.discard(turn_id)
                        completed[turn_id] = dict(params["turn"])
                    elif method == "item/completed":
                        item = params["item"]
                        root_items.setdefault(turn_id, {})[item["id"]] = item
                    elif method == "item/agentMessage/delta":
                        messages = root_deltas.setdefault(turn_id, {})
                        item_id = params.get("itemId", "answer")
                        messages[item_id] = messages.get(item_id, "") + params.get("delta", "")
                last_event = time.monotonic()
                if (tid in self.tap.children or turn_id in active_root) and event.get("phase", Phase.IDLE) != Phase.IDLE:
                    last_progress = last_event
                processing_event = True
                if on_event is not None:
                    outcome = on_event(event)
                    if inspect.isawaitable(outcome):
                        await outcome
                processing_event = False

        async def collect():
            # The SDK subscription ends at the initial turn's terminal event.
            # The tap keeps consuming through later turns on the same thread.
            terminal = False
            async for notification in self.handle.stream():
                if notification.method == "turn/completed" and unpack(notification)["params"]["turn"]["id"] == self.handle.id:
                    terminal = True
            if not terminal:
                raise RuntimeError("turn stream ended without turn/completed")

        def result():
            items, final_message = [], ""
            for turn_id, turn in completed.items():
                turn_items = dict(root_items.get(turn_id, {}))
                for item in turn.get("items", []):
                    turn_items.setdefault(item["id"], item)
                items.extend(turn_items.values())
                answers = [item for item in turn_items.values() if item.get("type") == "agentMessage"]
                final = next((item.get("text", "") for item in reversed(answers) if item.get("phase") == "final_answer"), "")
                messages = root_deltas.get(turn_id, {})
                final_message = final or (answers[-1].get("text", "") if answers else
                                          next(reversed(messages.values()), "")) or final_message
            return {**next(reversed(completed.values())), "items": items, "final_message": final_message}

        async def watch():
            while True:
                if check_alive is not None:
                    check_alive()
                await asyncio.sleep(.1)

        observer = asyncio.create_task(observe())
        collector = watcher = reconciliation = None
        try:
            await self.begin(prompt)
            collector = asyncio.create_task(collect())
            watcher = asyncio.create_task(watch())
            done, _ = await asyncio.wait((observer, collector, watcher), return_when=asyncio.FIRST_COMPLETED)
            for task in (observer, watcher):
                if task in done:
                    task.result()
                    raise RuntimeError("runtime observer stopped unexpectedly")
            collector.result()
            grace = self.spec["child_drain_timeout"]
            active_timeout = self.spec["child_active_timeout"]
            drain_started = idle_since = time.monotonic()
            settle_delay = min(.25, grace / 2)
            hard_deadline = drain_started + self.spec["max_child_drain_timeout"]
            active_since = None
            next_reconcile = drain_started
            rpc_active: set[str] = set()
            while True:
                for task in (observer, watcher):
                    if task.done():
                        task.result()
                        raise RuntimeError("runtime observer stopped during child drain")
                proc = self.codex._client._sync._proc
                if proc is not None and proc.poll() is not None:
                    raise RuntimeError("app-server exited during child drain")
                now = time.monotonic()
                if reconciliation is not None and reconciliation.done():
                    reconciliation.result()
                    reconciliation = None
                    next_reconcile = now + 1
                active_children = self.tap.active_children()
                unresolved = self.tap.unresolved_children()
                if active_children or unresolved & rpc_active or active_root:
                    if active_since is None:
                        active_since = now
                    idle_since = now
                    deadline = min(hard_deadline, max(active_since, last_progress) + active_timeout)
                else:
                    active_since = None
                    deadline = idle_since + grace
                    # Child completion can reach the tap just before the mailbox
                    # starts a follow-up root turn. Allow the notifications to settle.
                    if (self.handle.id in completed and not unresolved and not processing_event
                            and not self.tap.pending()
                            and now - max(idle_since, last_event) >= settle_delay):
                        if check_alive is not None:
                            check_alive()
                        return result()
                if now >= deadline:
                    raise RuntimeError("subagents failed to quiesce; execution remains uncertain")
                if (reconciliation is None and now >= next_reconcile and self.handle.id in completed
                        and (active_children or unresolved) and not self.tap.pending()):
                    reconciliation = asyncio.create_task(self.reconcile_children(rpc_active))
                await asyncio.sleep(min(.05, deadline - now))
        finally:
            tasks = [task for task in (observer, collector, watcher, reconciliation) if task is not None]
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def close(self) -> None:
        if self._closed:
            return
        if self._close_task is None:
            self._close_task = asyncio.create_task(self._close_transport())
        cancelled = None
        while True:
            try:
                await asyncio.shield(self._close_task)
                break
            except asyncio.CancelledError as exc:
                if self._close_task.cancelled():
                    raise
                cancelled = exc
        if cancelled is not None:
            raise cancelled

    async def _close_transport(self) -> None:
        if self._spawn_task is not None:
            try:
                await self._spawn_task
            except Exception:
                pass  # A failed spawn still needs its partial transport closed.
        proc = self.codex._client._sync._proc
        try:
            if proc is not None and proc.poll() is None:
                await asyncio.to_thread(terminate_process, proc, timeout=10)
            await self.codex.close()
        finally:
            self.tap.close()
            if proc is None or proc.poll() is not None:
                if proc is not None:
                    for pipe in (proc.stdin, proc.stdout, proc.stderr):
                        if pipe is not None:
                            pipe.close()
                self._closed = True
