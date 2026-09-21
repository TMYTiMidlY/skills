#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""读取 grafted-skills.json，更新 README.md 中 skills-table 标记之间的表格。

--check 只检查同步状态：一致返回 0，过期返回 1，输入或读写错误返回 2。

标记以内联方式放在表格行末尾，不会打断 markdown 表格渲染：
  | 最后一行手动行 |<!-- skills-table:begin -->
  | 脚本生成的行 |
  ...
  | 最后一行生成行 |<!-- skills-table:end -->
"""

import argparse
import json
import os
import stat
import sys
import tempfile
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


def render(readme, grafted):
    """校验输入后生成新正文，保留标记外内容及原有换行格式。"""
    if not isinstance(grafted, dict):
        raise ValueError("grafted-skills.json 必须是 JSON 对象")
    for name, info in grafted.items():
        if not isinstance(info, dict):
            raise ValueError(f"grafted-skills.json 的 {name!r} 必须是对象")
        repo = info.get("repo")
        if not isinstance(repo, str) or not repo.strip():
            raise ValueError(f"grafted-skills.json 的 {name!r}.repo 必须是非空白字符串")
        if not isinstance(info.get("description", ""), str):
            raise ValueError(f"grafted-skills.json 的 {name!r}.description 必须是字符串（可省略）")

    if readme.count(BEGIN) != 1 or readme.count(END) != 1:
        raise ValueError("README.md 必须且只能包含一对 skills-table 标记")
    i, j = readme.index(BEGIN), readme.index(END)
    if i >= j:
        raise ValueError("README.md 的 skills-table:begin 必须位于 skills-table:end 之前")

    newline = "\r\n" if "\r\n" in readme else "\n"
    block = build(grafted).replace("\n", newline)
    return readme[: i + len(BEGIN)] + newline + block + readme[j:]


def atomic_write(path: Path, data: bytes) -> None:
    """先完整写入同目录临时文件，再替换；替换前失败不触碰原文件。

    保留权限位和符号链接；不提供并发写锁或断电持久性保证。
    """
    path = path.resolve(strict=True)
    mode = stat.S_IMODE(path.stat().st_mode)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as stream:
            temporary_path = Path(stream.name)
            if stream.write(data) != len(data):
                raise OSError("临时文件未完整写入")
            stream.flush()
            os.chmod(temporary_path, mode)
            os.fsync(stream.fileno())
        # Windows 上也先关闭临时文件，再替换目标。
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError as error:
                # 清理失败时报告残留位置，不掩盖原始写入错误。
                print(f"update-readme: 无法清理临时文件 {temporary_path}: {error}", file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="只检查同步状态，不修改 README")
    args = parser.parse_args(argv)

    config = ROOT / "grafted-skills.json"
    readme_path = ROOT / "README.md"
    try:
        # 缺失文件必须报错；仅显式的空对象 {} 才表示清空自动表格。
        grafted = json.loads(config.read_text(encoding="utf-8"))
        readme = readme_path.read_bytes().decode("utf-8")
        new = render(readme, grafted)
        if new == readme:
            return 0
        if args.check:
            print("README.md 与 grafted-skills.json 不同步；请不带 --check 重新运行。", file=sys.stderr)
            return 1
        atomic_write(readme_path, new.encode("utf-8"))
    except (OSError, UnicodeError, ValueError) as error:
        print(f"update-readme: {error}", file=sys.stderr)
        return 2

    print("updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
