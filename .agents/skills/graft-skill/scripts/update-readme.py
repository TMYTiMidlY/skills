#!/usr/bin/env python3
"""读取 upstream-skills.json，自动更新 README.md 中的外部 skill 表格。"""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
CONFIG = REPO_ROOT / "upstream-skills.json"
README = REPO_ROOT / "README.md"

BEGIN = "<!-- skills-table:begin -->"
END = "<!-- skills-table:end -->"


def build_block(data: dict) -> str:
    stable = {k: v for k, v in data.items() if not k.startswith(".experimental/")}
    experimental = {k: v for k, v in data.items() if k.startswith(".experimental/")}

    lines = []

    if stable:
        lines.append("| Skill | 来源 | 说明 |")
        lines.append("| --- | --- | --- |")
        for name, info in stable.items():
            repo = info["repo"]
            lines.append(
                f"| `{name}` | [{repo}](https://github.com/{repo}) | {info.get('description', '')} |"
            )

    if experimental:
        if lines:
            lines.append("")
        lines.append("试验区（`.experimental/`）：")
        lines.append("")
        lines.append("| Skill | 来源 | 说明 |")
        lines.append("| --- | --- | --- |")
        for key, info in experimental.items():
            name = key.removeprefix(".experimental/")
            repo = info["repo"]
            lines.append(
                f"| `{name}` | [{repo}](https://github.com/{repo}) | {info.get('description', '')} |"
            )

    return "\n".join(lines)


def main():
    if not CONFIG.exists():
        print("upstream-skills.json not found, skipping")
        return

    data = json.loads(CONFIG.read_text())
    block = build_block(data) if data else ""

    readme = README.read_text()
    begin_idx = readme.find(BEGIN)
    end_idx = readme.find(END)

    if begin_idx == -1 or end_idx == -1:
        print("README.md 中未找到标记注释，跳过")
        return

    new_readme = (
        readme[: begin_idx + len(BEGIN)]
        + ("\n" + block + "\n" if block else "\n")
        + readme[end_idx:]
    )

    if new_readme != readme:
        README.write_text(new_readme)
        print("README.md updated")
    else:
        print("README.md already up to date")


if __name__ == "__main__":
    main()
