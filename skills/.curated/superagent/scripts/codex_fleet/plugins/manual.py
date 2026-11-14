"""Explicit sequential tasks, optional fenced external validation."""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path

from ..guard import terminate_process
from ..sdk import merged_environment


def prepare(context: dict) -> str | None:
    tasks = context["spec"].get("tasks", [])
    if not isinstance(tasks, list) or any(not isinstance(task, str) or not task.strip() for task in tasks):
        raise ValueError("tasks must be an array of nonempty prompts")
    index = context["checkpoint"].get("turn_index", 0)
    if type(index) is not int or index < 0:
        raise ValueError("turn_index must be a nonnegative integer")
    if index >= len(tasks):
        if context["checkpoint"].get("uncertain"):
            raise ValueError("uncertain checkpoint has no matching task; review imported progress")
        return None
    recovery = ""
    if context["checkpoint"].get("uncertain"):
        recovery = "上轮异常结束。先检查实际工作区、外部副作用与门禁状态，再继续当前目标，避免重复执行已完成的动作。\n"
    return recovery + tasks[index]


def complete(context: dict, result: dict) -> bool:
    if result.get("status") != "completed":
        return False
    command = context["spec"].get("gate_command")
    if command is None:
        return True
    if not isinstance(command, list) or not command or any(not isinstance(arg, str) for arg in command):
        raise ValueError("gate_command must be a nonempty argv array")
    timeout = context["spec"].get("gate_timeout", 600)
    if type(timeout) not in (float, int) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("gate_timeout must be a finite positive number")
    env, removed = merged_environment(context.get("account_config", {}), context["spec"])
    env["CODEX_FLEET_UNSET_ENV"] = json.dumps(sorted(removed))
    env["CODEX_FLEET_PARENT_PID"] = str(os.getpid())
    env["CODEX_FLEET_OWNER_FENCES"] = json.dumps(context["spec"].get("runtime_owner_fences", []))
    if fence := context.get("runtime", {}).get("runtime_fence"):
        env["CODEX_FLEET_RUNTIME_FENCE"] = fence
    guard = Path(__file__).resolve().parents[1] / "guard.py"
    # Gate output belongs in process logs, keeping CLI stdout machine-readable.
    process = subprocess.Popen([sys.executable, "-B", str(guard), *command],
                               cwd=context["spec"]["cwd"], env=env, shell=False,
                               stdin=subprocess.DEVNULL, stdout=sys.stderr, stderr=sys.stderr)
    try:
        return process.wait(timeout=timeout) == 0
    except subprocess.TimeoutExpired:
        terminate_process(process, timeout=10)
        return False
