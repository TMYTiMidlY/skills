# /// script
# requires-python = ">=3.10"
# dependencies = ["beautifulsoup4", "lxml"]
# ///
"""知网查重网页报告 (#detectionResult outerHTML) 转 Markdown.

支持三种报告：简洁报告单、全文标明引文报告单、全文对照报告单。
通过判断 DOM 是否含 .ACertainParagraph / .compareArticlesBox 自动适配。

用法：
    uv run scripts/查重_html_to_md.py <html_file> [-o out.md]

说明：
- 高亮：.Font_Color_Red → **【红】...**（未标引用的复制部分）
- 高亮：.Font_Color_Green → **【绿】...**（已标引用的复制部分）
- 相似来源段中的 .red_font → **...**（高亮匹配字符）
- 自动剥离 base64 内联图片 / SVG 装饰节点。
"""
from __future__ import annotations
import argparse, re, sys
from pathlib import Path
from bs4 import BeautifulSoup, NavigableString, Tag


# ---------- 工具 ----------

def text(node) -> str:
    """取节点纯文本，压缩空白。"""
    if node is None:
        return ""
    s = node.get_text(" ", strip=True) if isinstance(node, Tag) else str(node)
    return re.sub(r"\s+", " ", s).strip()


def render_with_highlight(node: Tag, *, red_token="【红】", green_token="【绿】",
                          source_highlight=False) -> str:
    """递归渲染节点为 Markdown，把高亮 span 转为 **...** 包裹。

    source_highlight=True 时，把相似源段里的 .red_font 也加粗（不打 token）。
    """
    parts: list[str] = []
    for child in node.children:
        if isinstance(child, NavigableString):
            parts.append(str(child))
            continue
        if not isinstance(child, Tag):
            continue
        cls = " ".join(child.get("class") or [])
        inner = render_with_highlight(child, red_token=red_token,
                                       green_token=green_token,
                                       source_highlight=source_highlight)
        if "Font_Color_Red" in cls:
            stripped = inner.strip()
            if stripped:
                parts.append(f"**{red_token}{stripped}**")
        elif "Font_Color_Green" in cls:
            stripped = inner.strip()
            if stripped:
                parts.append(f"**{green_token}{stripped}**")
        elif source_highlight and "red_font" in cls:
            stripped = inner.strip()
            if stripped:
                parts.append(f"**{stripped}**")
        elif child.name in ("p",):
            parts.append(inner)
        elif child.name in ("br",):
            parts.append(" ")
        else:
            parts.append(inner)
    text_out = re.sub(r"\s+", " ", "".join(parts)).strip()
    # 合并相邻同色高亮：**【红】A** **【红】B** → **【红】AB**
    for token in (red_token, green_token):
        pat = re.compile(r"\*\*" + re.escape(token) + r"([^*]*?)\*\*\s*\*\*" + re.escape(token) + r"([^*]*?)\*\*")
        while pat.search(text_out):
            text_out = pat.sub(lambda m: f"**{token}{m.group(1)}{m.group(2)}**", text_out)
    # 合并相邻 source_highlight：**A** **B** → **AB**（仅 source_highlight 下做更激进的合并不安全，跳过）
    return text_out


def first(soup, sel):
    el = soup.select_one(sel)
    return text(el)


# ---------- 各区块解析 ----------

def parse_meta(root) -> dict:
    return {
        "title": first(root, ".nameTitleBox"),
        "author": first(root, ".nameTitle1"),
        "deadline": first(root, ".nameTitle11"),
        "checked_at": first(root, ".nameTitle2"),
    }


def parse_overview(root) -> dict:
    """复制比 + 单篇最大。"""
    out = {}
    out["total"] = first(root, ".d1Center .d1CenterNumber")
    out["exclude_quote"] = first(root, ".quBox .bottom")
    out["quote"] = first(root, ".yinBox .bottom")
    # 去除本人复制比 (左侧大块的 .bi)
    left_bi = root.select_one(".eBoxBottomLeft .bi")
    out["exclude_self"] = text(left_bi)
    # 单篇最大
    box = root.select_one(".eBoxBottomRight")
    if box:
        out["max_single_pct"] = text(box.select_one(".bi"))
        out["max_single_doc"] = text(box.select_one(".tips"))
    return out


def parse_indicators(root) -> dict:
    """基础指标 + 分段指标。"""
    out = {"base": {}, "segment": {}}
    boxes = root.select(".baseBox")
    for box in boxes:
        title = text(box.select_one(".baseTitle")) or text(box.select_one(".baseTitle1"))
        bucket = "base" if "基础" in title else "segment"
        for li in box.select(".baseUl li span"):
            t = text(li)
            if "：" in t:
                k, v = t.split("：", 1)
                out[bucket][k.strip()] = v.strip()
    return out


def parse_distribution(root) -> dict:
    """结果分布图：前后 + 各章节。"""
    out = {"front": {}, "back": {}, "chapters": []}
    left = root.select_one(".left20")
    if left:
        out["front"] = {"pct": text(left.select_one(".top .red")),
                        "chars": text(left.select_one(".words1 .black"))}
    right = root.select_one(".right80")
    if right:
        out["back"] = {"pct": text(right.select_one(".top .red")),
                       "chars": text(right.select_one(".words1 .black"))}
    for w in root.select(".profileTableTwoWords"):
        ln = w.select_one(".lengthNumber")
        if not ln:
            continue
        # lengthNumber 的 textContent 是 "7.6%\n中英文摘要等"，分两块
        pct = ""
        title = ""
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


def parse_segment_table(root) -> list[dict]:
    """分段检测结果表格。"""
    table = root.select_one(".detectionResultTable .el-table__body tbody")
    rows = []
    if not table:
        return rows
    for tr in table.select("tr.el-table__row"):
        tds = [text(td) for td in tr.select("td .cell")]
        if len(tds) >= 6:
            rows.append({
                "no": tds[0], "total": tds[1], "exclude_self": tds[2],
                "exclude_quote": tds[3], "chars": tds[4], "section": tds[5],
            })
    return rows


def parse_section_details(root) -> list[dict]:
    """每个 #detailBox* 的对照详情。"""
    sections = []
    for box in root.select('div[id^="detailBox"]'):
        sec_title = text(box.select_one(".segmentedInfoTitle"))
        nums = [text(n) for n in box.select(".topHeaderLeftLi .number")]
        # nums 顺序：总复制比、去除本人、去除引用、总字符数(单独 class number1)
        n1 = box.select_one(".topHeaderLeftLi .number")
        chars_el = box.select_one(".topHeaderLeftLi1 .number1")
        chars = text(chars_el)
        # 过滤 chars 不在 nums 头三个中
        nums = [n for n in nums if n != chars][:3]
        paragraphs = []
        for para in box.select(".ACertainParagraph"):
            left = para.select_one(".ACertainParagraphLeft")
            if not left:
                continue
            title_el = left.select_one(".title")
            similar_chars = ""
            if title_el:
                m = re.search(r"(\d+)", text(title_el))
                if m:
                    similar_chars = m.group(1)
            content_el = left.select_one(".content")
            content = render_with_highlight(content_el) if content_el else ""
            sources = []
            for src in para.select(".ACertainParagraphRightBox"):
                src_title = text(src.select_one(".articleTitle .title"))
                src_author = text(src.select_one(".articleTitle .author"))
                src_content_el = src.select_one(".articleContent")
                src_content = render_with_highlight(src_content_el,
                                                    source_highlight=True) if src_content_el else ""
                sources.append({"title": src_title, "author": src_author,
                                "content": src_content})
            paragraphs.append({"chars": similar_chars, "content": content,
                               "sources": sources})
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

def to_markdown(meta, overview, indicators, distribution, seg_table, sections) -> str:
    md: list[str] = []
    md.append(f"# 知网个人查重 — 检测结果详情\n")
    md.append(f"## {meta['title']}\n")
    md.append("| 项 | 值 |\n|---|---|")
    md.append(f"| 作者 | {meta['author']} |")
    md.append(f"| 比对截止日期 | {meta['deadline']} |")
    md.append(f"| 检测时间 | {meta['checked_at']} |")
    md.append("")

    md.append("## 复制比结果\n")
    md.append("| 指标 | 数值 |\n|---|---|")
    md.append(f"| **总文字复制比** | **{overview.get('total','')}** |")
    md.append(f"| 去除引用文献复制比 | {overview.get('exclude_quote','')} |")
    md.append(f"| 引用文献复制比 | {overview.get('quote','')} |")
    md.append(f"| 去除本人文献复制比 | {overview.get('exclude_self','')} |")
    if overview.get("max_single_pct"):
        md.append(f"| 单篇最大文字复制比 | {overview['max_single_pct']}（{overview.get('max_single_doc','')}） |")
    md.append("")

    if indicators["base"]:
        md.append("### 基础指标\n")
        md.append("| 项 | 值 |\n|---|---|")
        for k, v in indicators["base"].items():
            md.append(f"| {k} | {v} |")
        md.append("")
    if indicators["segment"]:
        md.append("### 分段指标\n")
        md.append("| 项 | 值 |\n|---|---|")
        for k, v in indicators["segment"].items():
            md.append(f"| {k} | {v} |")
        md.append("")

    if distribution["chapters"]:
        md.append("## 结果分布图\n")
        md.append("| 区段 | 重复占比 | 重复字符数 |\n|---|---|---|")
        md.append(f"| 前部 (20%) | {distribution['front'].get('pct','')} | {distribution['front'].get('chars','')} |")
        md.append(f"| 后部 (80%) | {distribution['back'].get('pct','')} | {distribution['back'].get('chars','')} |")
        md.append("\n各章节复制比：\n")
        md.append("| 章节 | 复制比 |\n|---|---|")
        for pct, title in distribution["chapters"]:
            md.append(f"| {title} | {pct} |")
        md.append("")

    if seg_table:
        md.append("## 分段检测结果\n")
        md.append("| 序号 | 总复制比 | 去除本人 | 去除引用 | 总字符数 | 段落章节 |\n|---|---|---|---|---|---|")
        for r in seg_table:
            md.append(f"| {r['no']} | {r['total']} | {r['exclude_self']} | {r['exclude_quote']} | {r['chars']} | {r['section']} |")
        md.append("")

    if sections:
        md.append("---\n")
        for sec in sections:
            md.append(f"## {sec['title']}\n")
            md.append(f"**总复制比**：{sec['total_pct']} ｜ **去除本人**：{sec['exclude_self_pct']} ｜ **去除引用**：{sec['exclude_quote_pct']} ｜ **总字符数**：{sec['chars']}\n")
            for i, para in enumerate(sec["paragraphs"], 1):
                md.append(f"### 段 {i} — 此处有 {para['chars']} 字相似\n")
                md.append("**原文**：")
                md.append(f"> {para['content']}\n")
                if para["sources"]:
                    md.append("**相似来源**：\n")
                    for src in para["sources"]:
                        head = f"- **{src['title']}** — {src['author']}"
                        md.append(head)
                        if src["content"]:
                            md.append(f"  > {src['content']}")
                    md.append("")
            md.append("---\n")
    return "\n".join(md)


# ---------- 主流程 ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("html_file", type=Path)
    ap.add_argument("-o", "--output", type=Path, default=None)
    args = ap.parse_args()
    html = args.html_file.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "lxml")
    root = soup.select_one("#detectionResult") or soup
    meta = parse_meta(root)
    overview = parse_overview(root)
    indicators = parse_indicators(root)
    distribution = parse_distribution(root)
    seg_table = parse_segment_table(root)
    sections = parse_section_details(root)
    md = to_markdown(meta, overview, indicators, distribution, seg_table, sections)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(md, encoding="utf-8")
        print(f"wrote {args.output} ({len(md)} chars)", file=sys.stderr)
    else:
        sys.stdout.write(md + "\n")


if __name__ == "__main__":
    main()
