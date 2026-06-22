# /// script
# requires-python = ">=3.10"
# dependencies = ["beautifulsoup4", "lxml"]
# ///
"""similarity_report_html.py — 知网查重网页报告（#detectionResult outerHTML）→ Markdown。

适用「简洁报告单 / 全文标明引文报告单 / 全文对照报告单」，靠 DOM 是否含
.ACertainParagraph 自动适配。相比 PDF 方案，HTML 天然分开双栏、保留红/绿引用色标
和完整相似源元数据，**全文对照报告单首选本脚本**。

取报告 HTML：浏览器打开报告页 → F12 → 选中 `<div id="detectionResult">` → Copy outerHTML
→ 存为 .html。

色标约定：
- .Font_Color_Red   → **【红】…**（未标引用的复制部分，对应降重里的 U）
- .Font_Color_Green → **【绿】…**（已标引用的复制部分，对应降重里的 Q）
- 相似源段里的 .red_font → **…**（高亮匹配字符，不打 token）

用法：
    uv run similarity_report_html.py <html_file> [-o out.md]   # 省略 -o 则打到 stdout
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

RED_TOKEN = "【红】"
GREEN_TOKEN = "【绿】"


# ---------- 工具 ----------

def text(node) -> str:
    """取节点纯文本并压缩空白。"""
    if node is None:
        return ""
    s = node.get_text(" ", strip=True) if isinstance(node, Tag) else str(node)
    return re.sub(r"\s+", " ", s).strip()


def first(root: Tag, selector: str) -> str:
    return text(root.select_one(selector))


def render_with_highlight(node: Tag | None, *, source_highlight: bool = False) -> str:
    """递归渲染节点为 Markdown，把高亮 span 转成 **…** 包裹。

    source_highlight=True 时，相似源段里的 .red_font 也加粗（不打红/绿 token）。
    末尾合并相邻同色高亮：**【红】A** **【红】B** → **【红】AB**。
    """
    if node is None:
        return ""
    parts: list[str] = []
    for child in node.children:
        if isinstance(child, NavigableString):
            parts.append(str(child))
            continue
        if not isinstance(child, Tag):
            continue
        cls = " ".join(child.get("class") or [])
        inner = render_with_highlight(child, source_highlight=source_highlight).strip()
        if "Font_Color_Red" in cls:
            if inner:
                parts.append(f"**{RED_TOKEN}{inner}**")
        elif "Font_Color_Green" in cls:
            if inner:
                parts.append(f"**{GREEN_TOKEN}{inner}**")
        elif source_highlight and "red_font" in cls:
            if inner:
                parts.append(f"**{inner}**")
        elif child.name == "br":
            parts.append(" ")
        else:
            parts.append(inner)
    out = re.sub(r"\s+", " ", "".join(parts)).strip()
    for token in (RED_TOKEN, GREEN_TOKEN):
        pat = re.compile(r"\*\*" + re.escape(token) + r"([^*]*?)\*\*\s*\*\*" + re.escape(token) + r"([^*]*?)\*\*")
        while pat.search(out):
            out = pat.sub(lambda m: f"**{token}{m.group(1)}{m.group(2)}**", out)
    return out


# ---------- 各区块解析 ----------

def parse_meta(root: Tag) -> dict:
    return {
        "title": first(root, ".nameTitleBox"),
        "author": first(root, ".nameTitle1"),
        "deadline": first(root, ".nameTitle11"),
        "checked_at": first(root, ".nameTitle2"),
    }


def parse_overview(root: Tag) -> dict:
    """复制比 + 单篇最大。"""
    out = {
        "total": first(root, ".d1Center .d1CenterNumber"),
        "exclude_quote": first(root, ".quBox .bottom"),
        "quote": first(root, ".yinBox .bottom"),
        "exclude_self": text(root.select_one(".eBoxBottomLeft .bi")),
    }
    box = root.select_one(".eBoxBottomRight")
    if box:
        out["max_single_pct"] = text(box.select_one(".bi"))
        out["max_single_doc"] = text(box.select_one(".tips"))
    return out


def parse_indicators(root: Tag) -> dict:
    """基础指标 + 分段指标。"""
    out: dict[str, dict] = {"base": {}, "segment": {}}
    for box in root.select(".baseBox"):
        title = text(box.select_one(".baseTitle")) or text(box.select_one(".baseTitle1"))
        bucket = "base" if "基础" in title else "segment"
        for li in box.select(".baseUl li span"):
            t = text(li)
            if "：" in t:
                k, v = t.split("：", 1)
                out[bucket][k.strip()] = v.strip()
    return out


def parse_distribution(root: Tag) -> dict:
    """结果分布图：前 20% / 后 80% + 各章节复制比。"""
    out: dict = {"front": {}, "back": {}, "chapters": []}
    if (left := root.select_one(".left20")):
        out["front"] = {"pct": text(left.select_one(".top .red")),
                        "chars": text(left.select_one(".words1 .black"))}
    if (right := root.select_one(".right80")):
        out["back"] = {"pct": text(right.select_one(".top .red")),
                       "chars": text(right.select_one(".words1 .black"))}
    for w in root.select(".profileTableTwoWords"):
        ln = w.select_one(".lengthNumber")
        if not ln:
            continue
        # lengthNumber 文本形如 "7.6%\n中英文摘要等"，拆成 pct + title 两块
        pct, title = "", ""
        for child in ln.children:
            if isinstance(child, NavigableString):
                t = str(child).strip()
                if t and not pct:
                    pct = t
            elif isinstance(child, Tag) and "showTit" in (child.get("class") or []):
                title = text(child)
        if pct:
            out["chapters"].append((pct, title))
    return out


def parse_segment_table(root: Tag) -> list[dict]:
    """分段检测结果表格。"""
    tbody = root.select_one(".detectionResultTable .el-table__body tbody")
    rows: list[dict] = []
    if not tbody:
        return rows
    for tr in tbody.select("tr.el-table__row"):
        tds = [text(td) for td in tr.select("td .cell")]
        if len(tds) >= 6:
            rows.append({"no": tds[0], "total": tds[1], "exclude_self": tds[2],
                         "exclude_quote": tds[3], "chars": tds[4], "section": tds[5]})
    return rows


def parse_section_details(root: Tag) -> list[dict]:
    """每个 #detailBox* 的对照详情：原文段 + 相似来源。"""
    sections: list[dict] = []
    for box in root.select('div[id^="detailBox"]'):
        sec_title = text(box.select_one(".segmentedInfoTitle"))
        nums = [text(n) for n in box.select(".topHeaderLeftLi .number")]
        chars = text(box.select_one(".topHeaderLeftLi1 .number1"))
        nums = [n for n in nums if n != chars][:3]   # 头三个是 总/去本人/去引用 复制比
        paragraphs: list[dict] = []
        for para in box.select(".ACertainParagraph"):
            left = para.select_one(".ACertainParagraphLeft")
            if not left:
                continue
            similar_chars = ""
            if (title_el := left.select_one(".title")) and (m := re.search(r"(\d+)", text(title_el))):
                similar_chars = m.group(1)
            content = render_with_highlight(left.select_one(".content"))
            sources = []
            for src in para.select(".ACertainParagraphRightBox"):
                sources.append({
                    "title": text(src.select_one(".articleTitle .title")),
                    "author": text(src.select_one(".articleTitle .author")),
                    "content": render_with_highlight(src.select_one(".articleContent"), source_highlight=True),
                })
            paragraphs.append({"chars": similar_chars, "content": content, "sources": sources})
        sections.append({
            "title": sec_title,
            "total_pct": nums[0] if len(nums) > 0 else "",
            "exclude_self_pct": nums[1] if len(nums) > 1 else "",
            "exclude_quote_pct": nums[2] if len(nums) > 2 else "",
            "chars": chars,
            "paragraphs": paragraphs,
        })
    return sections


# ---------- Markdown 生成 ----------

def to_markdown(meta: dict, overview: dict, indicators: dict,
                distribution: dict, seg_table: list[dict], sections: list[dict]) -> str:
    md: list[str] = [
        "# 知网个人查重 — 检测结果详情\n",
        f"## {meta['title']}\n",
        "| 项 | 值 |\n|---|---|",
        f"| 作者 | {meta['author']} |",
        f"| 比对截止日期 | {meta['deadline']} |",
        f"| 检测时间 | {meta['checked_at']} |",
        "",
        "## 复制比结果\n",
        "| 指标 | 数值 |\n|---|---|",
        f"| **总文字复制比** | **{overview.get('total', '')}** |",
        f"| 去除引用文献复制比 | {overview.get('exclude_quote', '')} |",
        f"| 引用文献复制比 | {overview.get('quote', '')} |",
        f"| 去除本人文献复制比 | {overview.get('exclude_self', '')} |",
    ]
    if overview.get("max_single_pct"):
        md.append(f"| 单篇最大文字复制比 | {overview['max_single_pct']}（{overview.get('max_single_doc', '')}） |")
    md.append("")

    for key, label in (("base", "基础指标"), ("segment", "分段指标")):
        if indicators[key]:
            md.append(f"### {label}\n")
            md.append("| 项 | 值 |\n|---|---|")
            md += [f"| {k} | {v} |" for k, v in indicators[key].items()]
            md.append("")

    if distribution["chapters"]:
        md.append("## 结果分布图\n")
        md.append("| 区段 | 重复占比 | 重复字符数 |\n|---|---|---|")
        md.append(f"| 前部 (20%) | {distribution['front'].get('pct', '')} | {distribution['front'].get('chars', '')} |")
        md.append(f"| 后部 (80%) | {distribution['back'].get('pct', '')} | {distribution['back'].get('chars', '')} |")
        md.append("\n各章节复制比：\n")
        md.append("| 章节 | 复制比 |\n|---|---|")
        md += [f"| {title} | {pct} |" for pct, title in distribution["chapters"]]
        md.append("")

    if seg_table:
        md.append("## 分段检测结果\n")
        md.append("| 序号 | 总复制比 | 去除本人 | 去除引用 | 总字符数 | 段落章节 |\n|---|---|---|---|---|---|")
        md += [f"| {r['no']} | {r['total']} | {r['exclude_self']} | {r['exclude_quote']} | {r['chars']} | {r['section']} |"
               for r in seg_table]
        md.append("")

    if sections:
        md.append("---\n")
        for sec in sections:
            md.append(f"## {sec['title']}\n")
            md.append(f"**总复制比**：{sec['total_pct']} ｜ **去除本人**：{sec['exclude_self_pct']} ｜ "
                      f"**去除引用**：{sec['exclude_quote_pct']} ｜ **总字符数**：{sec['chars']}\n")
            for i, para in enumerate(sec["paragraphs"], 1):
                md.append(f"### 段 {i} — 此处有 {para['chars']} 字相似\n")
                md.append("**原文**：")
                md.append(f"> {para['content']}\n")
                if para["sources"]:
                    md.append("**相似来源**：\n")
                    for src in para["sources"]:
                        md.append(f"- **{src['title']}** — {src['author']}")
                        if src["content"]:
                            md.append(f"  > {src['content']}")
                    md.append("")
            md.append("---\n")
    return "\n".join(md)


# ---------- 主流程 ----------

def main() -> None:
    ap = argparse.ArgumentParser(description="知网查重网页报告 outerHTML → Markdown")
    ap.add_argument("html_file", type=Path, help="存下来的 #detectionResult outerHTML")
    ap.add_argument("-o", "--output", type=Path, default=None, help="输出 md；省略则打到 stdout")
    args = ap.parse_args()

    soup = BeautifulSoup(args.html_file.read_text(encoding="utf-8"), "lxml")
    root = soup.select_one("#detectionResult") or soup
    md = to_markdown(
        parse_meta(root),
        parse_overview(root),
        parse_indicators(root),
        parse_distribution(root),
        parse_segment_table(root),
        parse_section_details(root),
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(md, encoding="utf-8")
        print(f"wrote {args.output} ({len(md)} chars)", file=sys.stderr)
    else:
        sys.stdout.write(md + "\n")


if __name__ == "__main__":
    main()
