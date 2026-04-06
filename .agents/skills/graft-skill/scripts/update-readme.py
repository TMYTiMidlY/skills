#!/usr/bin/env python3
"""读取 grafted-skills.json，更新 README.md 中 skills-table 标记之间的表格。

标记以内联方式放在表格行末尾，不会打断 markdown 表格渲染：
  | 最后一行手动行 |<!-- skills-table:begin -->
  | 脚本生成的行 |
  ...
  | 最后一行生成行 |<!-- skills-table:end -->
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BEGIN, END = "<!-- skills-table:begin -->", "<!-- skills-table:end -->"


def grafted_row(name, info):
    repo = info["repo"]
    return f"| `{name}` | [{repo}](https://github.com/{repo}) | {info.get('description', '')} |"


def table_header():
    return "| Skill | 来源 | 说明 |\n| --- | --- | --- |"


def build(grafted):
    stable = {k: v for k, v in grafted.items() if not k.startswith(".experimental/")}
    exp = {k: v for k, v in grafted.items() if k.startswith(".experimental/")}

    parts = []

    # 正式区 grafted skill（接在手动维护的本地 skill 表格后面，不带表头）
    for k, v in stable.items():
        parts.append(grafted_row(k, v))

    # 试验区
    if exp:
        parts.append("\n以下 skill 从外部仓库下载，尚未经过适配和验证，放在 `.experimental/` 目录下：\n")
        parts.append(table_header())
        for k, v in exp.items():
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

    new = readme[: i + len(BEGIN)] + "\n" + block + readme[j:]
    if new != readme:
        readme_path.write_text(new)
        print("updated")


if __name__ == "__main__":
    main()
