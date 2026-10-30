#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["websockets==15.0.1"]
# ///
"""One-shot external Codex maintenance; never starts a daemon or resumes work.

Default: inspect only. Mutations require --apply and a private --audit-dir.
release additionally requires --reviewed-idle, an operator acknowledgement that
all clients, child tasks and detached work were checked/stopped. Public listings
are incomplete: this is supervised maintenance, NOT automatic safe handoff.

After maintenance close the old TUI and reopen the original UUID. Choose Leave
paused if prompted. Never automate R/retry: it was observed to reactivate a
paused goal; the exact trigger was not established.
"""
from __future__ import annotations

import argparse
import asyncio
import fcntl
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import socket
import sqlite3
import stat
import struct
import sys
import time
import tomllib
from urllib.parse import quote
import uuid

from websockets.asyncio.client import unix_connect

SUPPORTED = {"0.165.0", "0.166.0"}
STATES = {"active", "paused", "blocked", "usageLimited", "budgetLimited", "complete"}
KINDS = ["cli", "vscode", "exec", "appServer", "subAgent", "subAgentReview", "subAgentCompact", "subAgentThreadSpawn", "subAgentOther", "unknown"]
QUIET = logging.Logger("codex_session_maintenance.private")
QUIET.addHandler(logging.NullHandler())
QUIET.disabled = True
QUIET.propagate = False


class Refused(RuntimeError):
    pass


class NativeError(Refused):
    def __init__(self, method, code):
        self.code = code
        super().__init__(f"Native {method} failed (code {code}); raw details withheld.")


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", value):
        raise Refused("Use the original complete lowercase thread UUID.")
    return value


def parse_version(agent):
    match = re.fullmatch(
        r"(?:[A-Za-z0-9][A-Za-z0-9_.-]{0,127}|Codex Desktop)/"
        r"(?P<version>[0-9]+\.[0-9]+\.[0-9]+) \([^()\r\n]+; [^()\r\n]+\) [\x20-\x7e]+",
        agent if isinstance(agent, str) else "",
    )
    if match is None or match["version"] not in SUPPORTED:
        raise Refused("Native version is unsupported or ambiguous; only 0.165.0/0.166.0 are verified.")
    return match["version"]


class Native:
    def __init__(self, home):
        self.home = Path(home).expanduser().resolve(strict=True)
        self.ws = None
        self.sequence = 0
        self.pid = None
        self.version = None
        self.archived_notifications = set()

    async def __aenter__(self):
        endpoint = (self.home / "app-server-control/app-server-control.sock").resolve(strict=True)
        before = endpoint.stat()
        if not stat.S_ISSOCK(before.st_mode) or before.st_uid != os.getuid() or before.st_mode & 0o077:
            raise Refused("Native endpoint must be an existing owned private socket. No backend was started.")
        raw = socket.socket(socket.AF_UNIX)
        raw.setblocking(False)
        try:
            async with asyncio.timeout(10):
                await asyncio.get_running_loop().sock_connect(raw, str(endpoint))
                self.pid, uid, _gid = struct.unpack("3i", raw.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                if uid != os.getuid() or self.pid <= 0:
                    raise Refused("Native peer identity is unknown.")
                self.ws = await unix_connect(sock=raw, compression=None, max_size=64 * 1024 * 1024, open_timeout=10, close_timeout=3, logger=QUIET)
                now = endpoint.stat()
                if (before.st_dev, before.st_ino) != (now.st_dev, now.st_ino):
                    raise Refused("Native endpoint changed during connection.")
                info = await self.call("initialize", {"clientInfo": {"name": "session-maintenance", "version": "1"}, "capabilities": {"experimentalApi": True}})
                self.version = parse_version(info.get("userAgent"))
                reported_home = info.get("codexHome")
                if not isinstance(reported_home, str) or not Path(reported_home).is_absolute() or Path(reported_home).resolve() != self.home:
                    raise Refused("Connected backend home does not match --home.")
                await self.ws.send(json.dumps({"method": "initialized"}))
            return self
        except BaseException as error:
            try:
                if self.ws is not None:
                    await self.ws.close()
                else:
                    raw.close()
            except Exception:
                raw.close()
            if isinstance(error, (Refused, asyncio.CancelledError)):
                raise
            raise Refused("Native connection/initialization failed; details withheld. No daemon was started.") from None

    async def __aexit__(self, *_):
        if self.ws is not None:
            try:
                await self.ws.close()
            except Exception:
                raise Refused("Native connection cleanup is uncertain; details withheld.") from None

    async def call(self, method, params):
        try:
            return await self._call(method, params)
        except (Refused, asyncio.CancelledError):
            raise
        except Exception:
            raise Refused(f"Native {method} transport failed; outcome uncertain, no retry. Details withheld.") from None

    async def _call(self, method, params):
        self.sequence += 1
        request = self.sequence
        async with asyncio.timeout(20):
            await self.ws.send(json.dumps({"id": request, "method": method, "params": params}))
            while True:
                response = json.loads(await self.ws.recv())
                if not isinstance(response, dict):
                    raise Refused("Native response has an unknown shape.")
                if "method" in response:
                    if response["method"] == "thread/archived":
                        self.archived_notifications.add(response.get("params", {}).get("threadId"))
                    if "id" in response:
                        await self.ws.send(json.dumps({"id": response["id"], "error": {"code": -32601, "message": "Maintenance never grants approvals."}}))
                    continue
                if type(response.get("id")) is not int or response["id"] != request:
                    raise Refused("Unexpected RPC response; stop instead of retrying.")
                if "error" in response:
                    error = response["error"]
                    code = error.get("code") if isinstance(error, dict) else None
                    raise NativeError(method, code if type(code) is int else "unknown")
                if not isinstance(response.get("result"), dict):
                    raise Refused("Native result is unavailable.")
                return response["result"]


def writer_pid(home, thread):
    """Observe the native kernel lock; never remove it or write a PID payload."""
    path = Path(home) / "thread-writer-locks" / (identifier(thread) + ".lock")
    if path.is_symlink():
        raise Refused("Native lock must not be a symlink.")
    if not path.exists():
        return None
    directory = path.parent.stat()
    if not stat.S_ISDIR(directory.st_mode) or directory.st_uid != os.getuid() or directory.st_mode & 0o022:
        raise Refused("Native lock directory is not an owned, protected directory.")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        # Native OpenOptions + umask 0002 legitimately creates 0664 locks.
        # Payload permissions are not writer identity: only kernel flock/PID is
        # used. Keep the name protected by its owned non-writable directory.
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o002:
            raise Refused("Native lock file is not a trusted regular file.")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            owners = []
            for line in Path("/proc/locks").read_text().splitlines():
                fields = line.split()
                if len(fields) < 6 or fields[1:4] != ["FLOCK", "ADVISORY", "WRITE"]:
                    continue
                major, minor, inode = fields[5].split(":")
                if (int(major, 16), int(minor, 16), int(inode)) == (os.major(info.st_dev), os.minor(info.st_dev), info.st_ino):
                    owners.append(int(fields[4]))
            if len(owners) != 1 or owners[0] <= 0:
                raise Refused("Native writer is unknown; do not guess another account.")
            result = owners[0]
        else:
            fcntl.flock(fd, fcntl.LOCK_UN)
            result = None
        now = path.stat()
        if (now.st_dev, now.st_ino) != (info.st_dev, info.st_ino):
            raise Refused("Native lock changed while being observed.")
        return result
    finally:
        os.close(fd)


def goal_id(home, thread):
    """Optional read-only internal ID evidence; no credential files are opened."""
    try:
        home = Path(home)
        settings = tomllib.loads((home / "config.toml").read_text())
        store = Path(settings.get("sqlite_home", str(home)))
        if not store.is_absolute():
            return None
        path = store / "goals_1.sqlite"
        if not path.is_file() or path.is_symlink():
            return None
        with path.open("rb") as stream:
            wal = stream.read(20)[18:20] == b"\x02\x02"
        if wal and any(not Path(str(path) + suffix).exists() for suffix in ("-wal", "-shm")):
            return None  # Do not create missing WAL sidecars for an audit.
        connection = sqlite3.connect("file:" + quote(str(path), safe="/") + "?mode=ro", uri=True)
        try:
            connection.execute("PRAGMA query_only=ON")
            connection.execute("PRAGMA trusted_schema=OFF")
            row = connection.execute("SELECT goal_id FROM thread_goals WHERE thread_id=?", (thread,)).fetchone()
            return str(row[0]) if row else None
        finally:
            connection.close()
    except (OSError, ValueError, sqlite3.Error):
        return None


async def pages(native, method, params):
    result, seen, cursor = [], set(), None
    for _ in range(100):
        reply = await native.call(method, {**params, "cursor": cursor, "limit": 100})
        if not isinstance(reply.get("data"), list) or "nextCursor" not in reply:
            raise Refused(f"Incomplete {method} observation.")
        result.extend(reply["data"])
        cursor = reply["nextCursor"]
        if cursor is None:
            return result
        if not isinstance(cursor, str) or cursor in seen:
            break
        seen.add(cursor)
    raise Refused("Incomplete or repeated pagination; stop for manual inspection.")


async def snapshot(native, thread, *, with_queue=True):
    thread = identifier(thread)
    value = (await native.call("thread/read", {"threadId": thread, "includeTurns": True})).get("thread")
    if not isinstance(value, dict) or value.get("id") != thread or not isinstance(value.get("turns"), list):
        raise Refused("Thread or full turn history is unavailable.")
    goal = (await native.call("thread/goal/get", {"threadId": thread})).get("goal", "missing")
    if goal is not None:
        if not isinstance(goal, dict) or goal.get("status") not in STATES or not isinstance(goal.get("objective"), str) or "tokenBudget" not in goal:
            raise Refused("Goal observation is unknown, not an empty goal.")
        if any(type(goal.get(field)) is not int or goal[field] < 0 for field in ("tokensUsed", "timeUsedSeconds")) or (goal.get("tokenBudget") is not None and (type(goal["tokenBudget"]) is not int or goal["tokenBudget"] < 0)):
            raise Refused("Goal budget/accounting is unavailable.")
        goal = {"status": goal["status"], "objectiveHash": hashlib.sha256(goal["objective"].encode()).hexdigest(),
                "budget": goal.get("tokenBudget"), "tokens": goal.get("tokensUsed"), "seconds": goal.get("timeUsedSeconds"),
                "internalId": goal_id(native.home, thread)}
    queue = await pages(native, "thread/queue/list", {"threadId": thread}) if with_queue else None
    children = []
    for archived in (False, True):
        children.extend(await pages(native, "thread/list", {"ancestorThreadId": thread, "archived": archived, "modelProviders": [], "sourceKinds": KINDS, "useStateDbOnly": True}))
    status = value.get("status")
    if not isinstance(status, dict) or status.get("type") not in {"idle", "notLoaded", "active", "systemError"}:
        raise Refused("Thread runtime status is unknown.")
    owner = writer_pid(native.home, thread)
    terminals, terminal_error = None, None
    if status["type"] in {"idle", "active"} and owner == native.pid:
        try:
            terminals = len(await pages(native, "thread/backgroundTerminals/list", {"threadId": thread}))
        except NativeError as error:
            terminal_error = error.code  # Unknown, never converted to zero.
    archived = None
    if isinstance(value.get("path"), str) and Path(value["path"]).is_absolute():
        stored = Path(value["path"]).resolve()
        if stored.is_relative_to((native.home / "archived_sessions").resolve()):
            archived = True
        elif stored.is_relative_to((native.home / "sessions").resolve()):
            archived = False
    turns = value["turns"]
    last = turns[-1] if turns else {}
    if turns and (not isinstance(last, dict) or not isinstance(last.get("id"), str) or not last["id"] or last.get("status") not in {"completed", "interrupted", "failed", "inProgress"}):
        raise Refused("Latest turn state is unknown; no maintenance writes were sent.")
    return {"thread": thread, "home": str(native.home), "backendPid": native.pid, "version": native.version,
            "writerPid": owner, "status": status["type"], "goal": goal,
            "queued": None if queue is None else len(queue), "backgroundTerminals": terminals, "backgroundObservationError": terminal_error,
            "children": sorted({identifier(item.get("id")) for item in children}), "archived": archived,
            "source": value.get("source"), "forkedFrom": value.get("forkedFromId"),
            "turnCount": len(turns), "lastTurn": {"id": last.get("id"), "status": last.get("status")},
            "cwd": value.get("cwd"), "path": value.get("path"), "model": value.get("model"),
            "modelProvider": value.get("modelProvider"), "reasoningEffort": value.get("reasoningEffort"),
            "ephemeral": value.get("ephemeral"), "parent": value.get("parentThreadId"),
            "listingCoverage": "exposed persistent descendants only; custom/internal/ephemeral tasks may be missing"}


def preserve(before, after):
    if before["thread"] != after["thread"] or before["children"] != after["children"]:
        raise Refused("Thread identity or exposed descendants changed; inspect the audit.")
    for field in ("cwd", "model", "modelProvider", "reasoningEffort"):
        if before.get(field) is not None and before[field] != after.get(field):
            raise Refused("Working directory or model configuration changed; inspect the audit.")
    a, b = before["goal"], after["goal"]
    if (a is None) != (b is None):
        raise Refused("Goal appeared or disappeared.")
    if a is not None:
        for field in ("objectiveHash", "budget", "internalId"):
            if a[field] is not None and a[field] != b[field]:
                raise Refused("Goal identity, objective or budget changed.")
        if a["budget"] != b["budget"] or b["tokens"] < a["tokens"] or b["seconds"] < a["seconds"]:
            raise Refused("Goal budget/accounting changed unexpectedly.")
        expected = a["status"] if a["status"] in {"complete", "budgetLimited"} else "paused"
        if b["status"] != expected:
            raise Refused("Goal is not paused or in its original terminal state.")


class Audit:
    def __init__(self, directory):
        path = Path(directory).expanduser().absolute()
        if path.is_symlink():
            raise Refused("Audit directory must not be a symlink.")
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = path.stat()
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise Refused("Use an owned private 0700 audit directory.")
        self.path = path / ("maintenance-" + uuid.uuid4().hex + ".jsonl")
        self.stream = self.path.open("x", encoding="utf-8")
        self.path.chmod(0o600)

    def add(self, stage, value):
        self.stream.write(json.dumps({"time": time.time(), "stage": stage, "data": value}, ensure_ascii=False) + "\n")
        self.stream.flush()
        os.fsync(self.stream.fileno())

    def close(self):
        self.stream.close()


def require_idle(value, native):
    if value["status"] not in {"idle", "notLoaded"} or value["lastTurn"]["status"] == "inProgress":
        raise Refused("Thread is active, unfinished or unknown. Pause/interrupt explicitly; no archive was sent.")
    if value["queued"] != 0 or value["children"] or value["ephemeral"] is not False or value["parent"] is not None:
        raise Refused("Queued/unknown work, children, ephemeral or child-thread scope requires individual manual review; no archive was sent.")
    if not isinstance(value["source"], str) or value["source"] not in {"cli", "vscode", "exec", "appServer"} or value["forkedFrom"] is not None or value["archived"] is not False:
        raise Refused("Automatic lifecycle steps are limited to an unarchived standard root, not a custom source or fork.")
    if value["goal"] and not value["goal"]["internalId"]:
        raise Refused("Internal GoalID could not be verified; pause only, then inspect before archiving.")
    if value["backgroundTerminals"] or (value["writerPid"] == native.pid and value["backgroundTerminals"] is None):
        raise Refused("Background terminals are active or unavailable; no archive was sent.")
    if value["writerPid"] not in (None, native.pid):
        raise Refused("A different backend owns the writer; select its actual --home, not another account.")
    if value["writerPid"] == native.pid and value["status"] != "idle":
        raise Refused("Source runtime is not positively observed idle.")


async def maintain(native, thread, action, *, apply=False, reviewed_idle=False, interrupt=False, audit=None):
    if action not in {"inspect", "pause", "release", "restore"}:
        raise Refused("Unknown maintenance action.")
    before = await snapshot(native, thread, with_queue=action != "restore")
    if audit:
        audit.add("before", before)
    if not apply or action == "inspect":
        return {"changed": False, "plannedAction": action, "snapshot": before}
    if audit is None:
        raise Refused("Mutations require --audit-dir.")
    if before["writerPid"] is not None and before["writerPid"] != native.pid:
        raise Refused("A different backend owns this UUID. Inspect its actual --home; no mutation was sent to the wrong backend.")
    if action in {"release", "restore"} and not reviewed_idle:
        raise Refused("release/restore require --reviewed-idle: inspect/stop all old clients and hidden/detached work first.")
    if action == "release":
        require_idle(before, native)
    if action == "restore" and (before["archived"] is not True or before["writerPid"] is not None or before["status"] != "notLoaded"):
        raise Refused("restore is only for the explicitly selected archived, unloaded, writer-free UUID.")
    if before["goal"] is not None and before["goal"]["status"] not in {"paused", "budgetLimited", "complete"}:
        audit.add("pausing", {"thread": thread})
        await native.call("thread/goal/set", {"threadId": thread, "status": "paused", "origin": "user"})
    current = await snapshot(native, thread, with_queue=action != "restore")
    preserve(before, current)
    if current["lastTurn"]["id"] != before["lastTurn"]["id"]:
        raise Refused("A new turn appeared before lifecycle changes; no archive/unarchive was sent.")
    if action == "restore":
        if current["archived"] is not True or current["writerPid"] is not None or current["status"] != "notLoaded":
            raise Refused("Archived root changed during preparation; no unarchive was sent.")
        audit.add("unarchiving-selected-id", {"thread": thread})
        await native.call("thread/unarchive", {"threadId": thread})
        current = await snapshot(native, thread)
        preserve(before, current)
        if current["archived"] is not False or current["status"] == "active":
            raise Refused("Restore is not verified; do not resume or retry it automatically.")
    if interrupt and current["status"] == "active":
        turn = current["lastTurn"]
        if turn["status"] != "inProgress" or not isinstance(turn["id"], str):
            raise Refused("Current turn ID is unknown; no interrupt was sent.")
        audit.add("interrupting", {"thread": thread, "turn": turn["id"]})
        await native.call("turn/interrupt", {"threadId": thread, "turnId": turn["id"]})
        for attempt in range(10):
            current = await snapshot(native, thread)
            preserve(before, current)
            if current["status"] != "active":
                break
            await asyncio.sleep(0.1)
        if current["status"] == "active":
            raise Refused("Interrupt was acknowledged but idle state is not yet verified. Inspect; do not resend writes blindly.")
    if action == "release":
        require_idle(current, native)
        if current["writerPid"] is not None:
            audit.add("archiving", current)
            await native.call("thread/archive", {"threadId": thread})
            # Root-only scope, manually reviewed. No automatic recursive unarchive
            # or blind rollback if a lifecycle request fails or its reply is lost.
            audit.add("archived", {"thread": thread})
            # Collect already queued lifecycle notifications through a read. A
            # reply alone is not proof that the whole recursive operation worked.
            archived = await snapshot(native, thread, with_queue=False)
            audit.add("archive-readback", archived)
            preserve(before, archived)
            if archived["archived"] is not True or archived["writerPid"] is not None or archived["status"] != "notLoaded":
                raise Refused("Archive location and writer release are not verified; inspect before restoring.")
            if archived["lastTurn"]["id"] != before["lastTurn"]["id"]:
                raise Refused("A new turn appeared while archiving; inspect before restoring.")
            if native.archived_notifications - {thread}:
                raise Refused("Unexpected descendant archive notification; stop and inspect the audit.")
            audit.add("unarchiving", {"thread": thread})
            await native.call("thread/unarchive", {"threadId": thread})
            audit.add("unarchived", {"thread": thread})
            current = await snapshot(native, thread)
            preserve(before, current)
            require_idle(current, native)
            if current["writerPid"] is not None:
                raise Refused("A backend reacquired the writer; no resume or retry was sent.")
            if native.archived_notifications - {thread}:
                raise Refused("Unexpected descendant was archived; inspect the partial lifecycle record.")
    if current["lastTurn"]["id"] != before["lastTurn"]["id"]:
        raise Refused("A new turn appeared during maintenance; inspect other clients instead of retrying.")
    if current["goal"] and current["goal"]["status"] == "active":
        raise Refused("Goal unexpectedly became active; inspect and pause it, do not retry recovery.")
    audit.add("verified", current)
    return {"changed": current != before, "snapshot": current,
            "internalGoalIdVerified": bool(before["goal"] and before["goal"]["internalId"] and current["goal"]["internalId"] == before["goal"]["internalId"]),
            "note": "No thread/resume, turn/start, goal activation or TUI keys were sent. Close the old TUI, reopen the original UUID, and choose Leave paused; do not use its old R/retry action."}


async def run(options):
    audit = Audit(options.audit_dir) if options.audit_dir else None
    try:
        async with Native(options.home) as native:
            result = await maintain(native, identifier(options.thread), options.action, apply=options.apply,
                                    reviewed_idle=options.reviewed_idle, interrupt=options.interrupt, audit=audit)
            if audit:
                result["audit"] = str(audit.path)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except BaseException as error:
        if audit:
            audit.add("stopped", {"errorType": type(error).__name__, "outcome": "May be partial after a write; inspect before retrying. No automatic rollback."})
        raise
    finally:
        if audit:
            audit.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("inspect", "pause", "release", "restore"), nargs="?", default="inspect")
    parser.add_argument("--home", type=Path, default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")))
    parser.add_argument("--thread", required=True)
    parser.add_argument("--apply", action="store_true", help="Explicitly permit the selected mutation; otherwise inspect/dry-run only.")
    parser.add_argument("--audit-dir", type=Path)
    parser.add_argument("--reviewed-idle", action="store_true", help="Operator checked/stopped all clients, children and detached work; public lists are incomplete.")
    parser.add_argument("--interrupt", action="store_true", help="Also interrupt the selected current turn; never a whole daemon.")
    options = parser.parse_args()
    if options.apply and options.action != "inspect" and options.audit_dir is None:
        parser.error("--apply requires a private --audit-dir")
    if options.interrupt and (not options.apply or options.action != "pause"):
        parser.error("--interrupt is only supported with pause --apply")
    os.umask(0o077)
    asyncio.run(run(options))


if __name__ == "__main__":
    try:
        main()
    except Refused as error:
        print(f"Maintenance stopped: {error} Inspect the private audit; no automatic retry or rollback.", file=sys.stderr)
        raise SystemExit(1)
    except (OSError, TimeoutError, ValueError, sqlite3.Error):
        print("Maintenance stopped on an unavailable or uncertain local/native operation. Inspect the private audit; no automatic retry, rollback or daemon restart.", file=sys.stderr)
        raise SystemExit(1)
