"""Validated capacity policy and serialized, atomic JSON file updates."""
from __future__ import annotations

import copy
import json
import math
import os
import re
import tempfile
from pathlib import Path

from .state import FileLock

DEFAULT = {
    "max_parallel_workers": 3,
    "max_subagents_per_worker": 2,
    "max_level_on_stream_retry": 2,
    "lease_seconds": 30,
    "poll_seconds": 1,
    "recovery_seconds": 1500,
    "account_order": ["default"],
    "account_switch": {},
    "workers": {},
}
NAME = re.compile(r"[A-Za-z0-9_-]+\Z")


def _name(value: object) -> bool:
    return isinstance(value, str) and NAME.fullmatch(value) is not None


def _finite(value: object) -> bool:
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def validate(data: dict) -> dict:
    """Return an independent complete policy, rejecting ambiguous inputs."""
    if not isinstance(data, dict) or set(data) - set(DEFAULT):
        raise ValueError("unknown policy fields or non-object policy")
    policy = copy.deepcopy(DEFAULT)
    policy.update(copy.deepcopy(data))
    for key, low, high in (
        ("max_parallel_workers", 1, 256),
        ("max_subagents_per_worker", 0, 256),
        ("max_level_on_stream_retry", 0, 4),
    ):
        if type(policy[key]) is not int or not low <= policy[key] <= high:
            raise ValueError(f"{key} must be an integer in [{low}, {high}]")
    for key, low in (("lease_seconds", 3), ("poll_seconds", 0.05), ("recovery_seconds", 1)):
        value = policy[key]
        if not _finite(value) or value < low:
            raise ValueError(f"{key} must be finite and at least {low}")
    order = policy["account_order"]
    if not isinstance(order, list) or not order or any(not _name(name) for name in order):
        raise ValueError("account_order must be a nonempty list of valid account names")
    if len(set(order)) != len(order):
        raise ValueError("account_order must contain unique account names")
    if not isinstance(policy["account_switch"], dict):
        raise ValueError("account_switch must be an object")
    for account, rule in policy["account_switch"].items():
        if not isinstance(rule, dict) or set(rule) != {"used_percent", "window", "to"}:
            raise ValueError("account switch rules require used_percent, window and to")
        target = rule["to"]
        if account not in order or target not in order or order.index(target) <= order.index(account):
            raise ValueError("account switches must move forward in account_order")
        threshold = rule["used_percent"]
        if (not _finite(threshold)
                or not 0 <= threshold <= 100 or rule["window"] not in ("primary", "secondary")):
            raise ValueError("invalid quota threshold/window")
    if not isinstance(policy["workers"], dict):
        raise ValueError("workers must be an object")
    for name, flags in policy["workers"].items():
        if (not _name(name) or not isinstance(flags, dict) or set(flags) - {"pause", "drain"}
                or any(type(value) is not bool for value in flags.values())):
            raise ValueError(f"invalid worker flags for {name!r}")
    return policy


def atomic_json(path: Path, data: dict) -> None:
    """Replace a JSON document using a same-directory temporary file and fsync."""
    path = Path(path)
    payload = json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    pending: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", prefix=f".{path.name}.pending-", dir=path.parent,
            delete=False,
        ) as output:
            pending = Path(output.name)
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.replace(pending, path)
        pending = None
        # POSIX directory fsync makes the rename durable. Windows lacks this API.
        if os.name == "posix":
            descriptor = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    finally:
        if pending is not None:
            pending.unlink(missing_ok=True)


class PolicyFile:
    """Hot reader retaining its last valid value; writers validate the whole file."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.last = validate({})
        self.error: str | None = None

    def read(self) -> dict:
        try:
            self.last = validate(json.loads(self.path.read_text(encoding="utf-8")))
            self.error = None
        except (OSError, ValueError, TypeError) as exc:
            self.error = str(exc)
        return copy.deepcopy(self.last)

    def update(self, dotted: str, value: object) -> dict:
        if not isinstance(dotted, str) or not dotted or any(not part for part in dotted.split(".")):
            raise ValueError("policy key must be a nonempty dotted path")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(self.path.with_suffix(".lock"), blocking=True):
            # Existing malformed files are never replaced with guessed defaults.
            policy = (validate(json.loads(self.path.read_text(encoding="utf-8")))
                      if self.path.exists() else validate({}))
            parts = dotted.split(".")
            node = policy
            for part in parts[:-1]:
                node = node.setdefault(part, {})
                if not isinstance(node, dict):
                    raise ValueError("policy path traverses a scalar")
            node[parts[-1]] = value
            policy = validate(policy)
            atomic_json(self.path, policy)
            self.last, self.error = copy.deepcopy(policy), None
            return copy.deepcopy(policy)


def choose_account(current: str, limits: dict, policy: dict) -> str:
    """Apply a configured waterline only in the persisted forward account order."""
    if current not in policy["account_order"]:
        raise ValueError(f"current account {current!r} missing from account_order")
    rule = policy["account_switch"].get(current)
    if rule:
        window = limits.get(rule["window"]) or {}
        used = window.get("usedPercent") if isinstance(window, dict) else None
        if _finite(used) and used >= rule["used_percent"]:
            return rule["to"]
    return current
