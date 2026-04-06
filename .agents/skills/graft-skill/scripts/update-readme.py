#!/usr/bin/env python3
"""读取 grafted-skills.json + 扫描本地 skill，更新 README.md 中 <!-- skills-table --> 标记之间的表格。"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SKILLS_DIR = ROOT / "skills"
BEGIN, END = "<!-- skills-table:begin -->", "<!-- skills-table:end -->"

def grafted_row(name, info):
    repo = info["repo"]
    return f"| `{name}` | [{repo}](https://github.com/{repo}) | {info.get('description', '')} |"


def table_header():
    return "| Skill | 来源 | 说明 |\n| --- | --- | --- |"


def build(grafted):
    stable_grafted = {k: v for k, v in grafted.items() if not k.startswith(".experimental/")}
    exp_grafted = {k: v for k, v in grafted.items() if k.startswith(".experimental/")}

    parts = []

    # 正式区 grafted skill（不带表头，接在手动维护的本地 skill 表格后面）
    for k, v in stable_grafted.items():
        parts.append(grafted_row(k, v))

    # 试验区
    if exp_grafted:
        parts.append("\n以下 skill 从外部仓库下载，尚未经过适配和验证，放在 `.experimental/` 目录下：\n")
        parts.append(table_header())
        for k, v in exp_grafted.items():
            parts.append(grafted_row(k.removeprefix(".experimental/"), v))

    return "\n".join(parts)


def main():
    config = ROOT / "grafted-skills.json"
    readme_path = ROOT / "README.md"

    if not readme_path.exists():
        return

    grafted = json.loads(config.read_text()) if config.exists() else {}
    block = build(grafted)

    readme = readme_path.read_text()
    i, j = readme.find(BEGIN), readme.find(END)
    if i == -1 or j == -1:
        return

    new = readme[: i + len(BEGIN)] + "\n" + block + "\n" + readme[j:]
    if new != readme:
        readme_path.write_text(new)
        print("updated")


if __name__ == "__main__":
    main()
