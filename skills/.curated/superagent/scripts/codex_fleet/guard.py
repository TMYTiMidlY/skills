"""Internal process-group guardian for app-server and external gate commands.

Linux uses parent-death notification and a runtime fence. Other platforms retain
normal child supervision; only Linux supports the full fleet lease guarantee.
"""
from __future__ import annotations

import ctypes
import contextlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

if __package__:
    from .state import FileLock
else:
    from state import FileLock


def terminate_process(process: subprocess.Popen, timeout: float = 2.0) -> int:
    """Ask a guardian to stop and reap its tree; never force-release its fence."""
    if process.poll() is None:
        process.terminate()
    return process.wait(timeout=timeout)


def _linux_parent_signal() -> None:
    if not sys.platform.startswith("linux"):
        return
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGTERM, 0, 0, 0) != 0:  # PR_SET_PDEATHSIG
        raise OSError(ctypes.get_errno(), "prctl(PR_SET_PDEATHSIG)")
    # Reap orphaned descendants inside our process tree as a child subreaper.
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        raise OSError(ctypes.get_errno(), "prctl(PR_SET_CHILD_SUBREAPER)")


def _group_alive(group: int) -> bool:
    if sys.platform.startswith("linux"):
        for directory in Path("/proc").iterdir():
            if directory.name.isdigit():
                try:
                    fields = (directory / "stat").read_text().rsplit(")", 1)[1].split()
                    if int(fields[2]) == group and fields[0] not in ("Z", "X"):
                        return True
                except (OSError, ValueError, IndexError):
                    continue
        return False
    if os.name == "posix":
        try:
            os.killpg(group, 0)
            return True
        except ProcessLookupError:
            return False
    return False


def _reap_adopted() -> None:
    if not hasattr(os, "waitpid"):
        return
    while True:
        try:
            pid, _ = os.waitpid(-1, os.WNOHANG)
            if pid == 0:
                return
        except ChildProcessError:
            return


def _stop_tree(child: subprocess.Popen) -> None:
    if os.name != "posix":
        if child.poll() is None:
            child.terminate()
        try:
            child.wait(timeout=1)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
        return
    try:
        os.killpg(child.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        child.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass
    # Even a normally exited app-server may have left tools in its group.
    try:
        os.killpg(child.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    child.wait()
    _reap_adopted()
    if sys.platform.startswith("linux"):
        # An uninterruptible live descendant keeps the fence: TTL is not proof
        # that an old runtime has stopped and a slot is safe to reuse.
        while _group_alive(child.pid):
            _reap_adopted()
            time.sleep(0.05)
        _reap_adopted()


def main(argv: list[str] | None = None) -> int:
    command = sys.argv[1:] if argv is None else argv
    if not command:
        raise ValueError("guardian requires a child command")
    expected = os.environ.get("CODEX_FLEET_PARENT_PID")
    parent = int(expected) if expected is not None else os.getppid()
    if parent <= 0 or os.getppid() != parent:
        return 125
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    _linux_parent_signal()
    if stopping or os.getppid() != parent:
        return 125
    environment = os.environ.copy()
    unset = json.loads(environment.pop("CODEX_FLEET_UNSET_ENV", "[]"))
    if not isinstance(unset, list) or any(not isinstance(key, str) for key in unset):
        raise ValueError("CODEX_FLEET_UNSET_ENV must contain a JSON list of names")
    environment.pop("CODEX_FLEET_PARENT_PID", None)
    fence_path = environment.pop("CODEX_FLEET_RUNTIME_FENCE", None)
    owner_fences = json.loads(environment.pop("CODEX_FLEET_OWNER_FENCES", "[]"))
    if (not isinstance(owner_fences, list)
            or any(not isinstance(path, str) or not path or "\0" in path for path in owner_fences)):
        raise ValueError("CODEX_FLEET_OWNER_FENCES must contain a JSON list of paths")
    paths = owner_fences + ([fence_path] if fence_path else [])
    # Canonical ordering prevents inconsistent multi-fence acquisition, and
    # deduplication permits a shared owner/slot path without self-deadlocking.
    paths = sorted({str(Path(path).expanduser().resolve()) for path in paths})
    for key in unset:
        environment.pop(key, None)
    with contextlib.ExitStack() as fences:
        # Owner fences outlive worker PID locks, so a different free slot cannot
        # overlap a crashed worker's still-running workspace/gate process tree.
        for path in paths:
            fences.enter_context(FileLock(Path(path)))
        child = None
        try:
            if stopping or os.getppid() != parent:
                return 125
            options = {"start_new_session": True} if os.name == "posix" else {}
            if os.name == "nt":
                options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            child = subprocess.Popen(command, env=environment, **options)
            while child.poll() is None and not stopping and os.getppid() == parent:
                time.sleep(0.05)
            return child.returncode if child.returncode is not None else 143
        finally:
            if child is not None:
                _stop_tree(child)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"codex guardian: {exc}", file=sys.stderr)
        raise SystemExit(125)
