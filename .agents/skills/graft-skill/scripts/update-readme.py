#!/usr/bin/env python3
"""读取 grafted-skills.json + 本地 skill 定义，更新 README.md 中 <!-- skills-table --> 标记之间的表格。"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BEGIN, END = "<!-- skills-table:begin -->", "<!-- skills-table:end -->"

# 本地 skill（不在 grafted-skills.json 中，手动维护）
LOCAL_SKILLS = [
    ("vps-use", "*原创*", "通过 SSH 远程操作 VPS，完成服务器配置和运维任务"),
    ("qiuzhi-skill-creator", "[秋芝2046](https://space.bilibili.com/385670211)", "交互式引导创建新的 skill"),
]


def row(name, source, desc):
    return f"| `{name}` | {source} | {desc} |"


def grafted_row(name, info):
    repo = info["repo"]
    return row(name, f"[{repo}](https://github.com/{repo})", info.get("description", ""))


def table_header():
    return "| Skill | 来源 | 说明 |\n| --- | --- | --- |"


def build(grafted):
    stable = {k: v for k, v in grafted.items() if not k.startswith(".experimental/")}
    exp = {k: v for k, v in grafted.items() if k.startswith(".experimental/")}

    parts = [table_header()]

    # 本地 skill
    for name, source, desc in LOCAL_SKILLS:
        parts.append(row(name, source, desc))

    # 正式区 grafted skill
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

    new = readme[: i + len(BEGIN)] + "\n" + block + "\n" + readme[j:]
    if new != readme:
        readme_path.write_text(new)
        print("updated")


if __name__ == "__main__":
    main()
