#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["openai-codex>=0.167.1"]
# ///
"""Dispatch a Codex goal, read account limits, or manage an external fleet."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Keep an installed skill read-only even when the caller omitted python -B.
sys.dont_write_bytecode = True

from codex_fleet.policy import DEFAULT, PolicyFile, atomic_json, validate
from codex_fleet.sdk import DEFAULT_EFFORT, DEFAULT_MODEL, Runtime
from codex_fleet.state import FileLock, State
from codex_fleet.worker import Worker, valid_name

SKILL_ROOT = Path(__file__).resolve().parent.parent


def external_path(path: Path, purpose: str) -> Path:
    resolved = path.expanduser().resolve()
    if resolved.is_relative_to(SKILL_ROOT):
        raise ValueError(f"{purpose} must be outside the installed skill directory")
    return resolved


def import_v1(db: State, source: Path, names=None) -> list[str]:
    raw = source.read_bytes()
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("v1 input must be a worker map")
    records = data.get("workers", data)
    if not isinstance(records, dict):
        raise ValueError("invalid v1 worker map")
    selected = names or list(records)
    for name in selected:
        valid_name(name)
        row = records[name]
        if not isinstance(row, dict) or not isinstance(row.get("account"), str) or not row["account"]:
            raise ValueError(f"v1 worker {name} has no account; import refused")
        if row.get("thread_id") is not None and not isinstance(row["thread_id"], str):
            raise ValueError(f"invalid thread_id for {name}")
        if type(row.get("turn_index", 0)) is not int or row.get("turn_index", 0) < 0:
            raise ValueError(f"invalid turn_index for {name}")
    locks = []
    try:
        for name in selected:
            locks.append(FileLock(db.path.parent / "workers" / f"{name}.lock"))
        with db.connect(True) as conn:
            for name in selected:
                if conn.execute("SELECT 1 FROM workers WHERE name=?", (name,)).fetchone():
                    raise ValueError(f"{name} already has a checkpoint; import would risk rollback")
                row = {**records[name], "status": "imported"}
                conn.execute("INSERT INTO workers VALUES(?,?)", (name, json.dumps(row, ensure_ascii=False)))
            conn.execute("INSERT OR IGNORE INTO imports VALUES(?,?,?)",
                         (hashlib.sha256(raw).hexdigest(), str(source.resolve()), raw.decode("utf-8")))
    finally:
        for lock in locks:
            lock.close()
    return selected


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--self-test", action="store_true", help="run the bundled offline contract suite")
    groups = cli.add_subparsers(dest="group")
    run = groups.add_parser("run", help="run or resume one persistent goal without a fleet")
    run.add_argument("--cwd", type=Path, required=True)
    prompt = run.add_mutually_exclusive_group(required=True)
    prompt.add_argument("--prompt")
    prompt.add_argument("--prompt-file", type=Path)
    run.add_argument("--codex-home", type=Path)
    run.add_argument("--codex-bin")
    run.add_argument("--model", default=DEFAULT_MODEL)
    run.add_argument("--effort", default=DEFAULT_EFFORT,
                     choices=("none", "minimal", "low", "medium", "high", "xhigh"))
    run.add_argument("--sandbox", choices=("read-only", "workspace-write", "danger-full-access", "full-access"))
    run.add_argument("--approval-policy", choices=("never", "auto-review", "deny_all", "auto_review"))
    run.add_argument("--subagents", type=int, default=2, help="child count, excluding the root (default: 2)")
    run.add_argument("--developer-instructions")
    run.add_argument("--resume-thread")
    run.add_argument("--rpc-timeout", type=float, default=120)
    run.add_argument("--events-jsonl", type=Path)
    run.add_argument("--receipt-json", type=Path)
    limits = groups.add_parser("limits", help="read current limits; never start a model turn")
    limits.add_argument("--account", action="append", default=[], metavar="NAME=CODEX_HOME")
    limits.add_argument("--codex-bin")
    limits.add_argument("--rpc-timeout", type=float, default=120)
    fleet = groups.add_parser("fleet", help="manage persistent workers and external control state")
    fleet.add_argument("--fleet-dir", type=Path)
    commands = fleet.add_subparsers(dest="command", required=True)
    for command in ("init", "status", "set-policy", "start", "run-worker", "pause", "drain", "resume", "import-v1"):
        child = commands.add_parser(command)
        # Permit both `fleet --fleet-dir DIR status` and `fleet status --fleet-dir DIR`.
        child.add_argument("--fleet-dir", type=Path, default=argparse.SUPPRESS)
        if command == "set-policy":
            child.add_argument("key")
            child.add_argument("value", help="JSON value")
        if command in ("start", "run-worker", "pause", "drain", "resume"):
            child.add_argument("worker")
        if command == "run-worker":
            child.add_argument("--max-turns", type=int)
        if command == "import-v1":
            child.add_argument("source", type=Path)
            child.add_argument("--worker", action="append")
    return cli


async def safe_limits(runtime: Runtime) -> dict:
    try:
        return await runtime.limits()
    except Exception as exc:
        return {"error": str(exc)}


async def run_goal(args) -> tuple[dict, int]:
    cwd = args.cwd.expanduser().resolve()
    if not cwd.is_dir():
        raise ValueError("--cwd must be an existing directory")
    if not 0 <= args.subagents <= 256:
        raise ValueError("--subagents must be in [0, 256]")
    prompt = args.prompt if args.prompt is not None else args.prompt_file.read_text(encoding="utf-8")
    if not prompt.strip():
        raise ValueError("prompt must be nonempty")
    events_path = external_path(args.events_jsonl, "events log") if args.events_jsonl else None
    receipt_path = external_path(args.receipt_json, "receipt") if args.receipt_json else None
    if events_path and receipt_path and events_path == receipt_path:
        raise ValueError("events and receipt paths must differ")
    if args.prompt_file and any(path == args.prompt_file.resolve() for path in (events_path, receipt_path) if path):
        raise ValueError("output paths must differ from the prompt file")
    spec = {key: value for key, value in {
        "cwd": str(cwd), "codex_bin": args.codex_bin, "model": args.model,
        "effort": args.effort, "sandbox": args.sandbox, "approval_policy": args.approval_policy,
        "rpc_timeout": args.rpc_timeout,
    }.items() if value is not None}
    account = {"codex_home": str(args.codex_home)} if args.codex_home is not None else {}
    summary = {"thread_id": args.resume_thread, "turn_id": None, "status": "error", "final_message": "",
               "elapsed_s": 0, "before_limits": None, "after_limits": None, "reconciled_children": []}
    started, runtime, journal = time.monotonic(), None, None
    try:
        if events_path:
            events_path.parent.mkdir(parents=True, exist_ok=True)
            journal = events_path.open("a", encoding="utf-8", buffering=1)
        runtime = Runtime(spec, account, args.subagents)
        await runtime.start()
        summary["before_limits"] = await safe_limits(runtime)
        summary["thread_id"] = await runtime.open_thread(args.resume_thread, args.developer_instructions)

        def observe(event):
            if journal:
                journal.write(json.dumps({"time": time.time(), **event}, ensure_ascii=False) + "\n")

        result = await runtime.run_turn(prompt, on_event=observe)
        summary.update(turn_id=runtime.handle.id, status=result["status"], final_message=result.get("final_message", ""))
        if result.get("error") is not None:
            summary["error"] = result["error"]
    except Exception as exc:
        summary["error"] = str(exc)
        if runtime is not None and runtime.handle is not None:
            summary["turn_id"] = runtime.handle.id
    finally:
        if runtime is not None:
            summary["after_limits"] = await safe_limits(runtime) if runtime.thread is not None else None
            summary["reconciled_children"] = sorted(runtime.reconciled_children)
            try:
                await runtime.close()
            except Exception as exc:
                summary.update(status="error", close_error=str(exc))
        if journal:
            journal.close()
        summary["elapsed_s"] = round(time.monotonic() - started, 3)
    if receipt_path:
        atomic_json(receipt_path, summary)
    return summary, 0 if summary["status"] == "completed" else 1


async def read_limits(args) -> tuple[dict, int]:
    accounts = {}
    for item in args.account:
        name, separator, home = item.partition("=")
        if not separator or not name or not home or name in accounts:
            raise ValueError("--account must be a unique NAME=CODEX_HOME pair")
        accounts[name] = {"codex_home": home}
    accounts = accounts or {"default": {}}

    async def read(name, account):
        runtime, value = None, {}
        try:
            runtime = Runtime({"cwd": str(Path.cwd()), "codex_bin": args.codex_bin,
                               "rpc_timeout": args.rpc_timeout}, account, 0)
            await runtime.start()
            value = await runtime.limits()
        except Exception as exc:
            value = {"error": str(exc)}
        finally:
            if runtime is not None:
                try:
                    await runtime.close()
                except Exception as exc:
                    value = {**value, "error": value.get("error", "runtime cleanup failed"), "close_error": str(exc)}
        return name, value
    result = dict(await asyncio.gather(*(read(name, account) for name, account in accounts.items())))
    return {"accounts": result}, 1 if any("error" in value for value in result.values()) else 0


def fleet_command(args) -> tuple[dict, int]:
    if args.fleet_dir is None:
        raise ValueError("fleet requires --fleet-dir")
    directory = external_path(args.fleet_dir, "fleet directory")
    policy = PolicyFile(directory / "policy.json")
    if args.command == "init":
        directory.mkdir(parents=True, exist_ok=True)
        if not policy.path.exists():
            atomic_json(policy.path, validate(DEFAULT))
        if not (directory / "fleet.json").exists():
            atomic_json(directory / "fleet.json", {"allowed_workspace_roots": [], "accounts": {"default": {}}, "workers": {}})
        State(directory / "state.db")
        return {"fleet_dir": str(directory), "status": "initialized"}, 0
    if not (directory / "fleet.json").is_file() or not (directory / "state.db").is_file():
        raise ValueError("initialize the fleet before using this command")
    db = State(directory / "state.db", readonly=args.command == "status")
    if args.command == "status":
        result = db.snapshot()
        result.update(policy=policy.read(), policy_error=policy.error)
        return result, 1 if policy.error else 0
    if isinstance(getattr(args, "worker", None), str):
        valid_name(args.worker)
    if args.command == "set-policy":
        return policy.update(args.key, json.loads(args.value)), 0
    if args.command in ("drain", "pause", "resume"):
        if args.command == "resume":
            return policy.update(f"workers.{args.worker}", {"drain": False, "pause": False}), 0
        return policy.update(f"workers.{args.worker}.{args.command}", True), 0
    if args.command == "import-v1":
        return {"imported": import_v1(db, args.source, args.worker)}, 0
    if args.command == "run-worker":
        result = asyncio.run(Worker(directory, args.worker).run(args.max_turns))
        return result, 1 if result["status"] in ("needs_review", "faulted") else 0
    # Validate before detaching. The child takes both lifetime locks itself.
    Worker(directory, args.worker).configuration()
    (directory / "logs").mkdir(exist_ok=True)
    log = directory / "logs" / f"{args.worker}.process.log"
    with log.open("a", encoding="utf-8") as out:
        process = subprocess.Popen([sys.executable, "-B", str(Path(__file__).resolve()), "fleet",
                                    "--fleet-dir", str(directory), "run-worker", args.worker],
                                   cwd=directory, stdin=subprocess.DEVNULL, stdout=out, stderr=out,
                                   start_new_session=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    return {"pid": process.pid, "worker": args.worker, "log": str(log)}, 0


def main(argv=None) -> int:
    cli = parser()
    args = cli.parse_args(argv)
    if args.self_test:
        if args.group:
            cli.error("--self-test is used without a command group")
        import unittest
        os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
        suite = unittest.defaultTestLoader.discover(str(Path(__file__).parent / "tests"), pattern="test_codex_fleet.py")
        return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
    if args.group is None:
        cli.error("choose run, limits, fleet, or --self-test")
    try:
        if args.group == "run":
            result, code = asyncio.run(run_goal(args))
        elif args.group == "limits":
            result, code = asyncio.run(read_limits(args))
        else:
            result, code = fleet_command(args)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return code
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
