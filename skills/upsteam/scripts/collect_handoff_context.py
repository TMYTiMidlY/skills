#!/usr/bin/env python3
"""Collect a compact workspace snapshot for an external Pro-model handoff."""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable


def run_cmd(cmd: list[str], cwd: Path | None = None) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return 127, f"command not found: {cmd[0]}"
    output = proc.stdout.strip()
    if proc.stderr.strip():
        output = f"{output}\n{proc.stderr.strip()}".strip()
    return proc.returncode, output


def find_clipboard_command() -> tuple[str, list[str]] | None:
    candidates = [
        ("pbcopy", ["pbcopy"]),
        ("wl-copy", ["wl-copy"]),
        ("xclip", ["xclip", "-selection", "clipboard"]),
        ("xsel", ["xsel", "--clipboard", "--input"]),
    ]
    for name, cmd in candidates:
        if shutil.which(cmd[0]):
            return name, cmd
    return None


def copy_via_command(text: str, cmd: list[str]) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            cmd,
            input=text,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        return False, str(exc)
    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout or f"clipboard command failed: {' '.join(cmd)}").strip()
    return True, ""


def copy_via_osc52(text: str) -> tuple[bool, str]:
    if not sys.stdout.isatty():
        return False, "OSC 52 clipboard fallback requires an interactive terminal"
    encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
    sys.stdout.write(f"\033]52;c;{encoded}\a")
    sys.stdout.flush()
    return True, ""


def copy_to_clipboard(text: str) -> tuple[bool, str]:
    command = find_clipboard_command()
    if command is not None:
        name, cmd = command
        ok, message = copy_via_command(text, cmd)
        if ok:
            return True, f"copied to clipboard via {name}"
        return False, message

    ok, message = copy_via_osc52(text)
    if ok:
        return True, "copied to clipboard via OSC 52"
    return (
        False,
        "no clipboard utility found and terminal fallback is unavailable; install xclip/xsel/wl-copy or run from an interactive terminal",
    )


def trim_block(text: str, limit: int = 1200) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 15].rstrip() + "\n...[truncated]"


def list_top_level(root: Path, limit: int = 20) -> list[str]:
    entries = []
    for child in sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        suffix = "/" if child.is_dir() else ""
        entries.append(child.name + suffix)
        if len(entries) >= limit:
            break
    return entries


def infer_common_files(root: Path) -> list[str]:
    candidates = [
        "README.md",
        "pyproject.toml",
        "requirements.txt",
        "package.json",
        "Makefile",
        "setup.py",
        ".python-version",
        ".tool-versions",
        "environment.yml",
        "conda.yml",
    ]
    return [name for name in candidates if (root / name).exists()]


def summarize_path(root: Path, rel_path: str) -> dict[str, object]:
    target = (root / rel_path).resolve()
    result: dict[str, object] = {
        "path": rel_path,
        "exists": target.exists(),
    }
    if not target.exists():
        return result
    if target.is_dir():
        children = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        result["type"] = "directory"
        result["sample_children"] = [
            child.name + ("/" if child.is_dir() else "") for child in children[:10]
        ]
        return result

    result["type"] = "file"
    result["size_bytes"] = target.stat().st_size
    try:
        content = target.read_text(errors="replace")
    except OSError as exc:
        result["preview_error"] = str(exc)
        return result
    lines = content.splitlines()
    result["preview"] = "\n".join(lines[:40])
    return result


def detect_git_root(root: Path) -> Path | None:
    code, out = run_cmd(["git", "rev-parse", "--show-toplevel"], cwd=root)
    if code != 0 or not out:
        return None
    return Path(out.splitlines()[0].strip())


def collect_git(root: Path) -> dict[str, object]:
    git_root = detect_git_root(root)
    if git_root is None:
        return {"available": False}

    branch_code, branch_out = run_cmd(["git", "branch", "--show-current"], cwd=git_root)
    head_code, head_out = run_cmd(["git", "rev-parse", "--short", "HEAD"], cwd=git_root)
    status_code, status_out = run_cmd(["git", "status", "--short"], cwd=git_root)

    return {
        "available": True,
        "git_root": str(git_root),
        "branch": branch_out.splitlines()[0].strip() if branch_code == 0 and branch_out else "",
        "head": head_out.splitlines()[0].strip() if head_code == 0 and head_out else "",
        "status": status_out.splitlines()[:50] if status_code == 0 and status_out else [],
    }


def collect_runtime(root: Path) -> dict[str, object]:
    python = shutil.which("python3") or shutil.which("python")
    python_version = ""
    if python:
        code, out = run_cmd([python, "--version"], cwd=root)
        if code == 0:
            python_version = out.splitlines()[0].strip()

    node = shutil.which("node")
    node_version = ""
    if node:
        code, out = run_cmd([node, "--version"], cwd=root)
        if code == 0:
            node_version = out.splitlines()[0].strip()

    return {
        "cwd": str(root),
        "python": python or "",
        "python_version": python_version,
        "node": node or "",
        "node_version": node_version,
        "conda_default_env": os.environ.get("CONDA_DEFAULT_ENV", ""),
        "virtual_env": os.environ.get("VIRTUAL_ENV", ""),
    }


def format_section(title: str, lines: Iterable[str]) -> str:
    payload = "\n".join(line for line in lines if line.strip())
    return f"## {title}\n{payload}\n"


def render_markdown_report(data: dict[str, object]) -> str:
    top_level = "\n".join(f"- `{entry}`" for entry in data["top_level"])
    common_files = "\n".join(f"- `{entry}`" for entry in data["common_files"]) or "- none detected"

    git = data["git"]
    git_lines = []
    if git["available"]:
        git_lines.extend(
            [
                f"- root: `{git['git_root']}`",
                f"- branch: `{git['branch']}`" if git["branch"] else "- branch: unavailable",
                f"- head: `{git['head']}`" if git["head"] else "- head: unavailable",
            ]
        )
        if git["status"]:
            git_lines.append("- status:")
            git_lines.extend(f"  - `{line}`" for line in git["status"])
        else:
            git_lines.append("- status: clean or unavailable")
    else:
        git_lines.append("- git not detected")

    runtime = data["runtime"]
    runtime_lines = [
        f"- cwd: `{runtime['cwd']}`",
        f"- python: `{runtime['python']}`" if runtime["python"] else "- python: unavailable",
        f"- python version: `{runtime['python_version']}`" if runtime["python_version"] else "",
        f"- node: `{runtime['node']}`" if runtime["node"] else "- node: unavailable",
        f"- node version: `{runtime['node_version']}`" if runtime["node_version"] else "",
        f"- conda env: `{runtime['conda_default_env']}`" if runtime["conda_default_env"] else "",
        f"- virtualenv: `{runtime['virtual_env']}`" if runtime["virtual_env"] else "",
    ]

    focus_blocks = []
    for item in data["focus"]:
        focus_blocks.append(f"### `{item['path']}`")
        if not item["exists"]:
            focus_blocks.append("- missing")
            continue
        focus_blocks.append(f"- type: `{item['type']}`")
        if item["type"] == "directory":
            for child in item.get("sample_children", []):
                focus_blocks.append(f"- child: `{child}`")
        else:
            focus_blocks.append(f"- size: `{item['size_bytes']}` bytes")
            preview = trim_block(str(item.get("preview", "")), limit=1600)
            if preview:
                focus_blocks.append("```text")
                focus_blocks.append(preview)
                focus_blocks.append("```")

    sections = [
        "# Handoff Context Snapshot",
        "",
        format_section("Top Level", [top_level]),
        format_section("Common Files", [common_files]),
        format_section("Git", git_lines),
        format_section("Runtime", runtime_lines),
    ]

    if focus_blocks:
        sections.append("## Focus Paths")
        sections.extend(focus_blocks)
        sections.append("")

    return "\n".join(sections).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Workspace root to inspect.")
    parser.add_argument(
        "--focus",
        action="append",
        default=[],
        help="Relative path to summarize. Repeat for multiple paths.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of Markdown.",
    )
    parser.add_argument(
        "--copy",
        action="store_true",
        help="Copy the rendered output to the clipboard when possible.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress normal stdout output. Useful with --copy.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    if not root.exists() or not root.is_dir():
        print(f"error: root is not a directory: {root}", file=sys.stderr)
        return 1

    focus = args.focus or infer_common_files(root)
    data = {
        "root": str(root),
        "top_level": list_top_level(root),
        "common_files": infer_common_files(root),
        "git": collect_git(root),
        "runtime": collect_runtime(root),
        "focus": [summarize_path(root, rel_path) for rel_path in focus],
    }

    if args.json:
        output_text = json.dumps(data, indent=2)
    else:
        output_text = render_markdown_report(data)

    if not args.quiet:
        print(output_text)

    if args.copy:
        ok, message = copy_to_clipboard(output_text)
        if not ok:
            print(f"error: {message}", file=sys.stderr)
            return 2
        print(message, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
