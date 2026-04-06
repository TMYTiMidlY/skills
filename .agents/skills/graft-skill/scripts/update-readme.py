#!/usr/bin/env python3
"""读取 grafted-skills.json，更新 README.md 中 <!-- skills-table --> 标记之间的表格。"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BEGIN, END = "<!-- skills-table:begin -->", "<!-- skills-table:end -->"


def row(name, info):
    repo = info["repo"]
    return f"| `{name}` | [{repo}](https://github.com/{repo}) | {info.get('description', '')} |"


def table_header():
    return "| Skill | 来源 | 说明 |\n| --- | --- | --- |"


def build(data):
    stable = {k: v for k, v in data.items() if not k.startswith(".experimental/")}
    exp = {k: v for k, v in data.items() if k.startswith(".experimental/")}
    parts = []

    if stable:
        parts.append(table_header())
        parts.extend(row(k, v) for k, v in stable.items())

    if exp:
        parts.append("\n试验区（`.experimental/`）：\n")
        parts.append(table_header())
        parts.extend(row(k.removeprefix(".experimental/"), v) for k, v in exp.items())

    return "\n".join(parts)


def main():
    config = ROOT / "grafted-skills.json"
    readme_path = ROOT / "README.md"

    if not config.exists() or not readme_path.exists():
        return

    data = json.loads(config.read_text())
    block = build(data) if data else ""

    readme = readme_path.read_text()
    i, j = readme.find(BEGIN), readme.find(END)
    if i == -1 or j == -1:
        return

    new = readme[:i + len(BEGIN)] + ("\n" + block + "\n" if block else "\n") + readme[j:]
    if new != readme:
        readme_path.write_text(new)
        print("updated")


if __name__ == "__main__":
    main()
