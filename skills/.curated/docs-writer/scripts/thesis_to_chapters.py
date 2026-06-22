# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""thesis_to_chapters.py — 把学位论文 .doc/.docx 转成「分章 Markdown + 内联脚注」。

流程：.doc →(LibreOffice)→ .docx →(pandoc --wrap=none)→ 原始 md
      → 把 [^N] 脚注展开为正文内「（脚注：…）」→ 去 pandoc 多余转义
      → 按「第N章 / 参考文献」拆分为多个 md，写入 <outdir>/<论文名>/。

外部依赖（非 pip，需自行装好）：libreoffice（仅 .doc 需要）、pandoc。

用法：
    uv run thesis_to_chapters.py <论文.doc|.docx> [-o <输出父目录>]
    # 默认产到输入同级；纳入项目资产管理时用 `-o output` 产到 output/<论文名>/
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CHAPTER_RE = re.compile(r"^第(\d+)章")
TOC_PAGENUM_RE = re.compile(r"\*\*\d+\*\*\s*$")   # 目录行尾的粗体页码
FN_DEF_RE = re.compile(r"^\[\^(\d+)\]:\s*(.*)")   # 脚注定义行
FN_REF_RE = re.compile(r"\[\^(\d+)\](?!:)")       # 正文中的脚注引用


def require(tool: str) -> None:
    if shutil.which(tool) is None:
        sys.exit(f"缺少外部依赖：{tool}（请先安装后重试）")


def to_docx(src: Path, tmp: Path) -> Path:
    """.doc → .docx（LibreOffice headless）；已是 .docx 则原样返回。"""
    if src.suffix.lower() == ".docx":
        return src
    require("libreoffice")
    subprocess.run(
        ["libreoffice", "--headless", "--convert-to", "docx", str(src), "--outdir", str(tmp)],
        check=True,
    )
    return tmp / f"{src.stem}.docx"


def to_markdown(docx: Path, tmp: Path) -> str:
    require("pandoc")
    out = tmp / f"{docx.stem}_raw.md"
    subprocess.run(["pandoc", str(docx), "-o", str(out), "--wrap=none"], check=True)
    return out.read_text(encoding="utf-8")


def strip_escapes(text: str) -> str:
    """去掉 pandoc 产生的 \\[ \\] 转义。"""
    return text.replace(r"\[", "[").replace(r"\]", "]")


def inline_footnotes(lines: list[str]) -> list[str]:
    """收集 [^N] 定义、在正文处展开为「（脚注：…）」，并删掉定义行。"""
    defs = {m.group(1): m.group(2).strip() for ln in lines if (m := FN_DEF_RE.match(ln))}
    out: list[str] = []
    for ln in lines:
        if FN_DEF_RE.match(ln):
            continue
        out.append(FN_REF_RE.sub(lambda m: f"（脚注：{defs.get(m.group(1), m.group(0))}）", ln))
    return out


def find_splits(lines: list[str]) -> tuple[list[tuple[int, int]], int | None]:
    """返回 [(章号, 起始行号)…]（按出现顺序）与 参考文献起始行号（无则 None）。

    目录里的「第N章」行尾带粗体页码，靠 TOC_PAGENUM_RE 找到目录末行，
    只在其之后扫正文标题，避免把目录条目当成正文章首。
    """
    toc_end = max((i for i, ln in enumerate(lines) if TOC_PAGENUM_RE.search(ln.strip())), default=-1)
    chapters: list[tuple[int, int]] = []
    seen: set[int] = set()
    ref_start: int | None = None
    for i, ln in enumerate(lines):
        if i <= toc_end:
            continue
        s = ln.strip()
        if (m := CHAPTER_RE.match(s)):
            num = int(m.group(1))
            if num not in seen:
                seen.add(num)
                chapters.append((num, i))
        elif s == "参考文献" and ref_start is None:
            ref_start = i
    return chapters, ref_start


def chapter_title(first_line: str, num: int) -> str:
    m = re.match(r"第\d+章\s*(.*)", first_line.strip())
    if m and m.group(1).strip():
        return m.group(1).strip()[:20]
    return f"第{num}章"


def write_chapters(lines: list[str], chapters: list[tuple[int, int]],
                   ref_start: int | None, outdir: Path, src: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    tail_start = ref_start if ref_start is not None else len(lines)
    front_end = chapters[0][1] if chapters else tail_start

    def dump(name: str, block: list[str]) -> None:
        text = re.sub(r"\n{3,}", "\n\n", "\n".join(block)).strip() + "\n"
        (outdir / name).write_text(text, encoding="utf-8")
        print(f"  写出 {outdir / name}")

    # 00：正文前内容（封面/摘要/目录）+ 参考文献尾注
    front = lines[:front_end]
    tail = lines[ref_start:] if ref_start is not None else []
    dump("00_前言与参考文献.md", front + (["", *tail] if tail else []))

    # 各章
    for idx, (num, start) in enumerate(chapters):
        end = chapters[idx + 1][1] if idx + 1 < len(chapters) else tail_start
        title = chapter_title(lines[start], num)
        dump(f"{num:02d}_第{num}章_{title}.md", lines[start:end])

    shutil.copy(src, outdir / src.name)
    print(f"  复制原文 {outdir / src.name}")


def main() -> None:
    ap = argparse.ArgumentParser(description="学位论文 .doc/.docx → 分章 Markdown（内联脚注）")
    ap.add_argument("input", type=Path, help="输入论文 .doc 或 .docx")
    ap.add_argument("-o", "--outdir", type=Path, default=None,
                    help="输出父目录（在其下建 <论文名>/）；默认输入同级，纳入项目时用 output")
    args = ap.parse_args()

    src = args.input.resolve()
    if not src.exists():
        sys.exit(f"文件不存在：{src}")
    parent = args.outdir.resolve() if args.outdir else src.parent
    outdir = parent / src.stem
    print(f"输入：{src}\n输出：{outdir}")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        print("1/3 转 docx …")
        docx = to_docx(src, tmp)
        print("2/3 pandoc 转 md …")
        raw = to_markdown(docx, tmp)
        print("3/3 处理脚注 + 拆章 …")
        lines = inline_footnotes(strip_escapes(raw).split("\n"))
        chapters, ref_start = find_splits(lines)
        if not chapters:
            print("  ⚠ 未识别到「第N章」标题，全文写入 00_前言与参考文献.md")
        write_chapters(lines, chapters, ref_start, outdir, src)
    print("完成。")


if __name__ == "__main__":
    main()
