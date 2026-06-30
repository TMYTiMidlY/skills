# /// script
# requires-python = ">=3.10"
# dependencies = ["pymupdf"]
# ///
"""thesis_toc_pages.py — 从论文 PDF 提取「章节标题 → 正文页码」对照表。

靠字号区分标题与正文：用 PyMuPDF 的 get_text("dict") 读每行最大字号，
只有达阈值的「第N章 / X.X / X.X.X / 结语 / 参考文献」才算标题，避免正文里
出现的 "2.1 节…" 被误判为节标题（纯文本正则做不到这一点）。

offset = PDF 物理页与正文页的差（PDF 第 offset+1 页 = 正文第 1 页）；
不给则自动探测（找页首单独是 "1" 的那页）。

用法：
    uv run thesis_toc_pages.py <pdf> [--offset N] [--heading-size 14] [--json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF

CHAPTER_RE = re.compile(r"^第(\d+)\s*章")
SECTION_RE = re.compile(r"^(\d+\.\d+)$")
SUBSECTION_RE = re.compile(r"^(\d+\.\d+\.\d+)")
NAMED_HEADINGS = ("结语", "参考文献")


def detect_offset(doc: fitz.Document) -> int | None:
    """找页首单独是 "1" 的页，作为正文第 1 页（返回其 0-based 物理页号）。"""
    for i in range(doc.page_count):
        first_line = doc[i].get_text().strip().split("\n", 1)[0].strip()
        if first_line == "1":
            return i
    return None


def extract_headings(doc: fitz.Document, offset: int,
                     heading_size: float, sub_size: float) -> dict[str, int]:
    """逐页扫标题级文本，返回 {标题: 正文页码}（同名只记首次出现）。"""
    results: dict[str, int] = {}
    for pno in range(offset, doc.page_count):
        body_page = pno + 1 - offset
        for block in doc[pno].get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                spans = line["spans"]
                text = "".join(s["text"] for s in spans).strip()
                size = max((s["size"] for s in spans), default=0.0)
                if len(text) <= 1:
                    continue
                if size >= heading_size:
                    if (m := CHAPTER_RE.match(text)):
                        results.setdefault(f"第{m.group(1)}章", body_page)
                    elif (m := SECTION_RE.match(text)):
                        results.setdefault(m.group(1), body_page)
                    elif text in NAMED_HEADINGS:
                        results.setdefault(text, body_page)
                if size >= sub_size and (m := SUBSECTION_RE.match(text)):
                    results.setdefault(m.group(1), body_page)
    return results


def main() -> None:
    ap = argparse.ArgumentParser(description="论文 PDF → 章节标题对应正文页码")
    ap.add_argument("pdf", type=Path, help="论文 PDF")
    ap.add_argument("--offset", type=int, default=None, help="PDF 物理页 − 正文页；默认自动探测")
    ap.add_argument("--heading-size", type=float, default=14.0, help="章/节标题最小字号（默认 14）")
    ap.add_argument("--subsection-size", type=float, default=12.0, help="小节标题最小字号（默认 12）")
    ap.add_argument("--json", action="store_true", help="输出 JSON 而非纯文本")
    args = ap.parse_args()

    doc = fitz.open(args.pdf)
    offset = args.offset if args.offset is not None else detect_offset(doc)
    if offset is None:
        sys.exit("无法自动探测 offset，请用 --offset 指定（PDF 第 offset+1 页 = 正文第 1 页）")
    if args.offset is None:
        print(f"自动探测 offset = {offset}（PDF 第 {offset + 1} 页 = 正文第 1 页）\n", file=sys.stderr)

    results = extract_headings(doc, offset, args.heading_size, args.subsection_size)
    doc.close()

    ordered = dict(sorted(results.items(), key=lambda kv: kv[1]))
    if args.json:
        print(json.dumps(ordered, ensure_ascii=False, indent=2))
    else:
        for key, page in ordered.items():
            print(f"{key}: {page}")


if __name__ == "__main__":
    main()
