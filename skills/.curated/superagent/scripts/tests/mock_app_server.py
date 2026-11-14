"""Small stdio JSON-RPC peer for deterministic, credential-free SDK tests.

Only methods used by the dispatcher are implemented. Notifications deliberately
precede the turn/start response to exercise the SDK's routing race. MOCK_* env
values configure failures and delays; this process never opens a network socket.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


def send(value: dict) -> None:
    print(json.dumps(value), flush=True)


def notify(method: str, **params) -> None:
    send({"method": method, "params": params})


def turn(turn_id: str, status: str = "inProgress") -> dict:
    items = []
    if status != "inProgress":
        items.append({"id": "answer", "type": "agentMessage", "text": "mock result"})
    return {"id": turn_id, "status": status, "items": items, "error": None}


def configuration(arguments: list[str]) -> dict:
    config: dict = {}
    for index, argument in enumerate(arguments):
        if argument not in ("--config", "-c"):
            continue
        key, value = arguments[index + 1].split("=", 1)
        node = config
        parts = key.split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = json.loads(value)
    return config


def record(request: dict) -> None:
    target = os.environ.get("MOCK_RECORD")
    if not target:
        return
    keys = os.environ.get("MOCK_ENV_KEYS", "").split(",")
    value = {
        "method": request["method"],
        "params": request.get("params") or {},
        "pid": os.getpid(),
        "account_home": os.environ.get("CODEX_HOME"),
        "env": {key: os.environ.get(key) for key in keys if key},
    }
    with Path(target).open("a", encoding="utf-8") as output:
        output.write(json.dumps(value) + "\n")


def main() -> int:
    version = os.environ.get("MOCK_VERSION", "0.169.0")
    if "--version" in sys.argv:
        print(f"codex {version}")
        return 0
    config = configuration(sys.argv[1:])
    root = f"root-{os.getpid()}"
    counter = 0
    limit_reads = 0
    for line in sys.stdin:
        request = json.loads(line)
        record(request)
        if "id" not in request:
            continue
        method = request["method"]
        params = request.get("params") or {}
        if method == "initialize":
            result = {"userAgent": f"codex/{version}", "serverInfo": {"name": "codex", "version": version}}
        elif method == "config/read":
            result = {"config": config}
            if os.environ.get("MOCK_BAD_CONFIG"):
                result = {"config": {"features": {"multi_agent_v2": False}}}
        elif method == "account/rateLimits/read":
            limit_reads += 1
            if os.environ.get("MOCK_LIMITS_ERROR") or (
                os.environ.get("MOCK_FIRST_LIMITS_ERROR") and limit_reads == 1
            ):
                send({"id": request["id"], "error": {"code": -32000, "message": "mock quota endpoint unavailable"}})
                continue
            home = Path(os.environ.get("CODEX_HOME", "default")).name
            used = 90 if os.environ.get("MOCK_SWITCH") and home == "primary" else 10
            result = {
                "rateLimits": {
                    "primary": {"usedPercent": used, "windowDurationMins": 300, "resetsAt": 2000000000},
                    "secondary": {"usedPercent": used, "windowDurationMins": 10080, "resetsAt": 2000000000},
                    "credits": {"hasCredits": True, "unlimited": False, "balance": "10"},
                }
            }
        elif method in ("thread/start", "thread/resume"):
            root = params.get("threadId", root)
            result = {"thread": {"id": root}}
        elif method == "thread/read":
            result = {"thread": {"id": params["threadId"], "status": {"type": os.environ.get("MOCK_CHILD_STATUS", "idle")}}}
        elif method == "turn/start":
            if os.environ.get("MOCK_EXIT"):
                return 4
            counter += 1
            current = f"turn-{os.getpid()}-{counter}"
            child = f"child-{counter}"
            child_turn = f"child-turn-{counter}"
            notify("turn/started", threadId=root, turn=turn(current))
            if not os.environ.get("MOCK_QUIET_CHILD"):
                notify("turn/started", threadId=child, turn=turn(child_turn))
                notify("item/agentMessage/delta", threadId=child, turnId=child_turn,
                       itemId="child-message", delta="live child output")
            notify("item/completed", threadId=root, turnId=current,
                   item={"type": "collabAgentToolCall", "id": "spawn", "receiverThreadIds": [child], "senderThreadId": root})
            send({"id": request["id"], "result": {"turn": turn(current)}})
            if os.environ.get("MOCK_RETRY", "1") == "1":
                for attempt in range(1, 6):
                    notify("error", threadId=root, turnId=current, willRetry=True,
                           error={"message": f"Selected model is at capacity. Reconnecting... {attempt}/5",
                                  "codexErrorInfo": "streamDisconnected"})
            time.sleep(float(os.environ.get("MOCK_DELAY", "0.01")))
            notify("item/agentMessage/delta", threadId=root, turnId=current, itemId="answer", delta="mock result")
            quiet = bool(os.environ.get("MOCK_QUIET_CHILD"))
            child_delay = float(os.environ.get("MOCK_CHILD_DELAY", "0"))
            if not quiet and not child_delay:
                notify("turn/completed", threadId=child, turn=turn(child_turn, "completed"))
            notify("turn/completed", threadId=root, turn=turn(current, os.environ.get("MOCK_STATUS", "completed")))
            if not quiet and child_delay:
                time.sleep(child_delay)
                notify("turn/completed", threadId=child, turn=turn(child_turn, "completed"))
            continue
        elif method == "turn/steer":
            send({"id": request["id"], "error": {"code": -32000, "message": "ActiveTurnNotSteerable"}})
            continue
        else:
            result = {}
        send({"id": request["id"], "result": result})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
