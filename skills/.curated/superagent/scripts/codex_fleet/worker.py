"""Persistent single-workspace worker with fenced leases and external gates."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import signal
import time
from pathlib import Path

from .events import DeferredGuidance, Phase
from .plugins import Plugin
from .policy import PolicyFile, choose_account
from .sdk import Runtime
from .state import FileLock, State, identity


def valid_name(name: str) -> None:
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        raise ValueError("worker names may contain only letters, digits, '_' and '-'")


class Worker:
    def __init__(self, directory: Path, name: str):
        valid_name(name)
        self.directory, self.name = directory.resolve(), name
        self.db = State(self.directory / "state.db")
        self.policy = PolicyFile(self.directory / "policy.json")
        self.guidance = DeferredGuidance()
        self.draining = False
        self.plugin: Plugin | None = None

    def configuration(self) -> tuple[dict, dict]:
        config = json.loads((self.directory / "fleet.json").read_text())
        if not isinstance(config, dict) or not isinstance(config.get("workers"), dict):
            raise ValueError("fleet.json requires a workers object")
        if not isinstance(config.get("accounts"), dict):
            raise ValueError("fleet.json requires an accounts object")
        spec = dict(config["workers"][self.name])
        spec["cwd"] = str(Path(spec["cwd"]).expanduser().resolve())
        roots = config.get("allowed_workspace_roots")
        if not isinstance(roots, list) or not roots or any(not isinstance(root, str) for root in roots):
            raise ValueError("allowed_workspace_roots must list explicit workspace roots")
        if not any(Path(spec["cwd"]).is_relative_to(Path(root).expanduser().resolve()) for root in roots):
            raise ValueError("worker cwd is outside allowed_workspace_roots")
        if not Path(spec["cwd"]).is_dir():
            raise ValueError("worker cwd must already exist")
        return config, spec

    def request_drain(self) -> None:
        self.draining = True

    def _alive(self, lease) -> None:
        if lease.lost.is_set():
            raise RuntimeError("lease lost; runtime must be fenced before another turn")

    async def execute(self, runtime: Runtime, lease, prompt: str) -> dict:
        last_phase = None
        journal_path = self.directory / "logs" / f"{self.name}.events.jsonl"
        with journal_path.open("a", encoding="utf-8", buffering=1) as journal:
            def observe(event):
                nonlocal last_phase
                params, method = event["params"], event["method"]
                tid = params.get("threadId")
                turn = params.get("turnId") or (params.get("turn") or {}).get("id")
                state = runtime.tap.states.get((tid, turn))
                if event.get("overload") or (method == "error" and state is not None and state.overloaded):
                    policy = self.policy.read()
                    cap = policy["max_level_on_stream_retry"] if event.get("phase") == Phase.RECONNECTING else 4
                    self.db.overload(tid, turn, json.dumps(params), cap)
                    self.guidance.defer("overload", "上轮遇到服务重连；按本轮容量安排新增子任务，保留已有验证进展。")
                journal.write(json.dumps({"time": time.time(), **event}, ensure_ascii=False) + "\n")
                phase = (event.get("phase"), turn, state.attempt if state else 0)
                if event.get("phase") and tid == runtime.thread.id and phase != last_phase:
                    self.db.save(self.name, phase=phase[0], turn_id=turn, reconnect_attempt=phase[2])
                    last_phase = phase
            result = await runtime.run_turn(prompt, on_event=observe, check_alive=lambda: self._alive(lease))
        if runtime.reconciled_children:
            self.db.event(self.name, "subagent_tap_degraded", {"reconciled_children": sorted(runtime.reconciled_children)})
        return result

    async def run(self, max_turns: int | None = None) -> dict:
        if max_turns is not None and (type(max_turns) is not int or max_turns < 1):
            raise ValueError("max_turns must be positive")
        config, spec = self.configuration()
        self.directory.joinpath("logs").mkdir(parents=True, exist_ok=True)
        cwd_key = hashlib.sha256(spec["cwd"].encode()).hexdigest()
        owner_fences = [self.directory / "workers" / f"{self.name}.runtime.lock",
                        self.directory / "repositories" / f"{cwd_key}.runtime.lock"]
        with FileLock(self.directory / "workers" / f"{self.name}.lock"), FileLock(self.directory / "repositories" / f"{cwd_key}.lock"):
            # A dead worker releases its base locks before its guardian finishes
            # reaping. Owner fences also prevent re-entry via a different slot.
            for path in owner_fences:
                with FileLock(path):
                    pass
            self.db.save(self.name, pid=os.getpid(), process_identity=identity(os.getpid()), status="starting")
            loop = asyncio.get_running_loop()
            installed = []
            for sig in (signal.SIGTERM, signal.SIGINT):
                try:
                    loop.add_signal_handler(sig, self.request_drain)
                    installed.append(sig)
                except (NotImplementedError, RuntimeError):
                    pass
            try:
                return await self._loop(config, spec, cwd_key, max_turns, owner_fences)
            finally:
                for sig in installed:
                    loop.remove_signal_handler(sig)

    async def _loop(self, config, spec, cwd_key, max_turns, owner_fences):
        if self.db.worker(self.name).get("uncertain"):
            self.db.event(self.name, "crash_recovery", self.db.worker(self.name))
        rounds = 0
        while max_turns is None or rounds < max_turns:
            policy = self.policy.read()
            flags = policy["workers"].get(self.name, {})
            if self.draining or flags.get("drain"):
                self.db.save(self.name, status="drained")
                return self.db.worker(self.name)
            if flags.get("pause") or self.policy.error:
                self.db.save(self.name, status="paused", policy_error=self.policy.error)
                await asyncio.sleep(policy["poll_seconds"])
                continue
            self.db.remember_account_order(policy["account_order"])
            lease = self.db.acquire(self.name, policy)
            if lease is None:
                self.db.save(self.name, status="waiting_slot")
                await asyncio.sleep(policy["poll_seconds"])
                continue
            lease.start()
            runtime = None
            try:
                config, spec = self.configuration()
                spec["runtime_fence"] = lease.runtime_fence
                spec["runtime_owner_fences"] = [str(path) for path in owner_fences]
                if hashlib.sha256(spec["cwd"].encode()).hexdigest() != cwd_key:
                    raise RuntimeError("cwd changed; drain and restart to reacquire its workspace lock")
                plugin_name = spec.get("plugin", "codex_fleet.plugins.manual")
                if self.plugin is None or self.plugin.name != plugin_name:
                    self.plugin = Plugin(plugin_name)
                self.plugin.reload()
                checkpoint = self.db.worker(self.name)
                if checkpoint.get("completed"):
                    self.db.save(self.name, status="completed")
                    return self.db.worker(self.name)
                context = {"worker": self.name, "spec": spec, "checkpoint": checkpoint, "policy": policy}
                prompt = await self.plugin.call("prepare", context)
                if prompt is None:
                    self.db.save(self.name, status="completed", completed=True)
                    return self.db.worker(self.name)
                if not isinstance(prompt, str) or not prompt.strip():
                    raise ValueError("plugin.prepare must return a nonempty prompt or None")
                account = checkpoint.get("account") or spec.get("account") or policy["account_order"][0]
                if account not in policy["account_order"]:
                    raise ValueError(f"current account is missing from account_order: {account}")
                if account not in config["accounts"] or not isinstance(config["accounts"][account], dict):
                    raise ValueError(f"missing account configuration: {account}")
                _, subagents, level = self.db.limits(policy)
                runtime = Runtime(spec, config["accounts"][account], subagents)
                await runtime.start()
                try:
                    limits = await runtime.limits()
                    next_account = choose_account(account, limits.get("rateLimits", limits), policy)
                    self.db.save(self.name, quota=limits)
                except Exception as exc:
                    self.db.event(self.name, "quota_unavailable", {"error": str(exc)})
                    next_account = account
                thread_id = checkpoint.get("thread_id")
                if next_account != account:
                    if next_account not in config["accounts"]:
                        raise ValueError(f"switch target has no account configuration: {next_account}")
                    self.db.event(self.name, "account_switch", {"from": account, "to": next_account, "old_thread": thread_id})
                    account, thread_id = next_account, None
                    self.db.save(self.name, account=account, thread_id=None, turn_id=None)
                    await runtime.close()
                    runtime = Runtime(spec, config["accounts"][account], subagents)
                    await runtime.start()
                instructions = spec.get("developer_instructions", "Complete the assigned task and verify its gates.")
                digest = hashlib.sha256(instructions.encode()).hexdigest()
                if checkpoint.get("instructions_sha256") not in (None, digest):
                    thread_id = None
                tid = await runtime.open_thread(thread_id, instructions)
                context["runtime"] = {"account": account, "thread_id": tid, "subagents": subagents,
                                      "capacity_level": level, "runtime_fence": lease.runtime_fence}
                context["account_config"] = config["accounts"][account]
                # Persist BEFORE turn/start; a crash at any later point requires
                # inspecting external effects, even if a response was never seen.
                self.db.save(self.name, account=account, thread_id=tid, instructions_sha256=digest,
                             status="running", uncertain=True, subagents=subagents, capacity_level=level)
                result = await self.execute(runtime, lease, self.guidance.append(prompt, subagents))
                await runtime.close()
                runtime = None
                self.db.save(self.name, status="gate", phase=Phase.IDLE, last_result=result)
                accepted = await self.plugin.call("complete", context, result)
                self._alive(lease)
                if accepted is not True:
                    self.db.save(self.name, status="needs_review", uncertain=True)
                    return self.db.worker(self.name)
                self.db.save(self.name, status="idle", uncertain=False, completed=False,
                             turn_index=checkpoint.get("turn_index", 0) + 1)
                rounds += 1
            except BaseException as exc:
                self.db.save(self.name, status="faulted", error=str(exc), uncertain=True)
                self.db.event(self.name, "worker_fault", {"error": repr(exc)})
                raise
            finally:
                try:
                    if runtime is not None:
                        await runtime.close()
                finally:
                    lease.close()
        self.db.save(self.name, status="stopped_at_boundary")
        return self.db.worker(self.name)
