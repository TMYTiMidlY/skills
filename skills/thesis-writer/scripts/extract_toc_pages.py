"""
从论文 PDF 中提取各章节标题对应的正文页码。

原理：
1. 先确定偏移量（PDF 物理页码 vs 正文页码），通过检查正文首页的页眉/页脚数字。
2. 用 pymupdf 的 get_text("dict") 获取每个文本块的字体大小。
   - 章标题（第X章）和节标题（X.X）的字号 >= 14pt
   - 小节标题（X.X.X）的字号 >= 12pt
   这样就能把标题和正文区分开，避免正文中出现的 "2.1" 等编号被误匹配。
3. 结语、参考文献同样按字号 >= 14pt 匹配。

之前匹配失败的原因：
- 第一版用 get_text() 纯文本 + 正则搜索，无法区分标题和正文中的相同文字。
  比如正文里提到 "2.1 节的内容..."，纯文本正则会把它当成 2.1 节标题。
- 第二版用关键词搜索（如搜 "历史分期"），但这些词在引言等处也会出现，
  导致过早匹配到错误的页面。
- 最终版改用 get_text("dict") 读取字体元信息，按字号筛选标题级文本，
  彻底解决了误匹配问题。

用法：
    python3 extract_toc_pages.py <pdf_path> [offset]

    offset: PDF物理页码与正文页码的差值，默认自动检测。
            例如 PDF 第8页 = 正文第1页，则 offset=7。
"""

import sys
import re
import fitz


def detect_offset(doc):
    """自动检测偏移量：找到第一个页面首行是纯数字的页面"""
    for page_num in range(doc.page_count):
        text = doc[page_num].get_text().strip()
        first_line = text.split("\n")[0].strip() if text else ""
        if first_line == "1":
            return page_num  # PDF page (0-indexed) that is body page 1
    return None


def extract_headings(doc, offset):
    results = {}

    for page_num in range(offset, doc.page_count):
        page = doc[page_num]
        body_page = page_num + 1 - offset
        blocks = page.get_text("dict")["blocks"]

        for block in blocks:
            if "lines" not in block:
                continue
            for line_data in block["lines"]:
                text = ""
                max_size = 0
                for span in line_data["spans"]:
                    text += span["text"]
                    max_size = max(max_size, span["size"])
                text = text.strip()

                if not text or len(text) <= 1:
                    continue

                # 章标题和 X.X 级节标题：字号 >= 14pt
                if max_size >= 14:
                    m = re.match(r"^第([1-9])\s*章", text)
                    if m:
                        key = f"第{m.group(1)}章"
                        if key not in results:
                            results[key] = body_page

                    m = re.match(r"^([1-9]\.[1-9])$", text)
                    if m:
                        if m.group(1) not in results:
                            results[m.group(1)] = body_page

                    if text == "结语" and "结语" not in results:
                        results["结语"] = body_page
                    if text == "参考文献" and "参考文献" not in results:
                        results["参考文献"] = body_page

                # X.X.X 级小节标题：字号 >= 12pt
                if max_size >= 12:
                    m = re.match(r"^([1-9]\.[1-9]\.[1-9])", text)
                    if m and m.group(1) not in results:
                        results[m.group(1)] = body_page

    return results


def main():
    if len(sys.argv) < 2:
        print(f"用法: python3 {sys.argv[0]} <pdf_path> [offset]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    doc = fitz.open(pdf_path)

    if len(sys.argv) >= 3:
        offset = int(sys.argv[2])
    else:
        offset = detect_offset(doc)
        if offset is None:
            print("无法自动检测偏移量，请手动指定。")
            sys.exit(1)
        print(f"自动检测偏移量: {offset} (PDF第{offset+1}页 = 正文第1页)\n")

    results = extract_headings(doc, offset)
    doc.close()

    # 按页码排序输出
    for key, page in sorted(results.items(), key=lambda x: x[1]):
        print(f"{key}: {page}")


if __name__ == "__main__":
    main()
