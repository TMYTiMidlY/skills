# /// script
# requires-python = ">=3.10"
# dependencies = ["pdfplumber"]
# ///
"""similarity_report_pdf.py — 知网（CNKI）查重报告 PDF → Markdown（pdfplumber 方案）。

适用「简洁报告单 / 全文标明引文报告单」。**全文对照报告单请改用
similarity_report_html.py** —— 双栏对照页用 PDF 按 y 聚行会把左右两栏粘成一行
（详见 references/similarity-report-parsing.md「已知问题：双栏页文本错行」）。

做法：按字符重建行 → 过滤水印（灰度 (2.0,) 或字号 >20）→ 按字号定标题层级
      → 首页柱状图数值行转 GFM 表 → 「N. 章节名 总字符数：…」统一升为 ##。

用法：
    uv run similarity_report_pdf.py <report.pdf> [-o out.md]   # 省略 -o 则打到 stdout
"""
from __future__ import annotations

import argparse
import re
import sys
from itertools import groupby
from pathlib import Path

import pdfplumber

# 首页柱状图行： x.x%(nnn) x.x%(nnn) 章节名（总nnnn字）
BAR_RE = re.compile(r"^(\d+(?:\.\d+)?%)\((\d+)\)\s+(\d+(?:\.\d+)?%)\((\d+)\)\s+(.+?)（总(\d+)字）$")
# 章节头： "N. 章节名 总字符数：nnnn"
SECTION_RE = re.compile(r"^(\d+)\.\s+(.+?)\s+总字符数：(\d+)$")
PAGENUM_RE = re.compile(r"^-?\s*\d+\s*-?$")

WATERMARK_COLOR = (2.0,)   # 灰度水印字符的颜色编码
MAX_BODY_SIZE = 20         # 字号 > 此值基本是水印 / 装饰大字
H1_SIZE = 15
H2_SIZE = 11.5


def visible_chars(page: pdfplumber.page.Page) -> list[dict]:
    """去掉水印 / 装饰大字后的字符。"""
    return [
        c for c in page.chars
        if c.get("non_stroking_color") != WATERMARK_COLOR
        and (c.get("size") or 0) <= MAX_BODY_SIZE
    ]


def group_lines(chars: list[dict], y_tol: float = 2.5) -> list[tuple[float, str]]:
    """按 top 聚成行，行内按 x 排序、字距大于半个字号处补空格；返回 (平均字号, 文本)。"""
    chars = sorted(chars, key=lambda c: (round(c["top"] / y_tol), c["x0"]))
    lines: list[tuple[float, str]] = []
    for _, grp in groupby(chars, key=lambda c: round(c["top"] / y_tol)):
        grp = sorted(grp, key=lambda c: c["x0"])
        text, prev_x1, sizes = "", None, []
        for c in grp:
            size = c.get("size", 10)
            if prev_x1 is not None and c["x0"] - prev_x1 > size * 0.5:
                text += " "
            text += c["text"]
            prev_x1 = c["x1"]
            sizes.append(size)
        text = re.sub(r"[ \t]+", " ", text).strip()
        if text:
            lines.append((sum(sizes) / len(sizes), text))
    return lines


def classify(size: float, text: str) -> str:
    """按字号给一行定 Markdown 层级。"""
    if size >= H1_SIZE:
        return f"# {text}"
    if size >= H2_SIZE:
        return f"## {text}"
    return text


def promote_section_headers(lines: list[str]) -> list[str]:
    """「N. 章节名 总字符数：…」无论原层级一律规范为 ##。"""
    out = []
    for ln in lines:
        body = ln[3:] if ln.startswith("## ") else ln
        if (m := SECTION_RE.match(body)):
            out.append(f"## {m.group(1)}. {m.group(2)} 总字符数：{m.group(3)}")
        else:
            out.append(ln)
    return out


def insert_bar_table(lines: list[str], bars: list[tuple]) -> list[str]:
    """把首页柱状图数据插成 GFM 表，放在首个「检测结果」行之后（找不到则追加到末尾）。"""
    if not bars:
        return lines
    table = ["", "| 去除本人复制比 | 总文字复制比 | 章节 | 总字符数 |", "|---|---|---|---|"]
    table += [f"| {p1} ({c1}) | {p2} ({c2}) | {sec} | {tot} |" for p1, c1, p2, c2, sec, tot in bars]
    table.append("")
    for i, ln in enumerate(lines):
        if "检测结果" in ln:
            return lines[:i + 1] + table + lines[i + 1:]
    return lines + table


def normalize_blocks(lines: list[str]) -> str:
    """表格行连成块、段落间留空行，最后压掉多余空行。"""
    out: list[str] = []
    in_table = False
    for ln in lines:
        if ln.startswith("|"):
            if not in_table and out and out[-1] != "":
                out.append("")
            in_table = True
            out.append(ln)
        else:
            if in_table:
                out.append("")
                in_table = False
            if out and out[-1] != "":
                out.append("")
            out.append(ln)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip() + "\n"


def build_markdown(pdf_path: Path) -> str:
    body: list[str] = []
    bars: list[tuple] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for size, text in group_lines(visible_chars(page)):
                if (m := BAR_RE.match(text)):
                    bars.append(m.groups())
                elif PAGENUM_RE.fullmatch(text):
                    continue
                else:
                    body.append(classify(size, text))
    body = promote_section_headers(body)
    body = insert_bar_table(body, bars)
    return normalize_blocks(body)


def main() -> None:
    ap = argparse.ArgumentParser(description="CNKI 查重报告 PDF → Markdown（pdfplumber）")
    ap.add_argument("pdf", type=Path, help="查重报告 PDF")
    ap.add_argument("-o", "--output", type=Path, default=None, help="输出 md；省略则打到 stdout")
    args = ap.parse_args()

    md = build_markdown(args.pdf)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(md, encoding="utf-8")
        print(f"wrote {args.output} ({len(md)} chars)", file=sys.stderr)
    else:
        sys.stdout.write(md)


if __name__ == "__main__":
    main()
