# /// script
# dependencies = ["pdfplumber", "pandas", "tabulate"]
# ///
"""Convert CNKI 查重 report PDFs to Markdown.

策略：
- 用 pdfplumber 按字符重建行，过滤水印（non_stroking_color == (2.0,) 或字号极大）。
- 字号 == 16 的行为 h1 (# ), 字号 == 12 且非页码的为 h2 (## )。
- 其余为段落。
- 首页的检测结果柱状图数值行 (xx.xx%(nnn) xx.xx%(nnn) 章节名) 识别后输出为 Markdown 表。
"""
import argparse
import os
import re

import pdfplumber
from itertools import groupby

def clean_page(page):
    """返回去水印后的字符列表。"""
    out = []
    for ch in page.chars:
        col = ch.get('non_stroking_color')
        size = ch.get('size', 0)
        # 水印：颜色编码为 (2.0,) 灰度；字号超过 20 也基本是水印或大标题装饰
        if col == (2.0,):
            continue
        if size and size > 20:
            continue
        out.append(ch)
    return out

def group_lines(chars, y_tol=2.5):
    """按 y 坐标聚类成行，每行按 x 排序。"""
    # pdfplumber 里 top 表示从上边距离
    chars = sorted(chars, key=lambda c: (round(c['top'] / y_tol), c['x0']))
    lines = []
    for k, grp in groupby(chars, key=lambda c: round(c['top'] / y_tol)):
        grp = sorted(grp, key=lambda c: c['x0'])
        text = ''
        prev_x1 = None
        sizes = []
        for c in grp:
            if prev_x1 is not None and c['x0'] - prev_x1 > c.get('size', 10) * 0.5:
                text += ' '
            text += c['text']
            prev_x1 = c['x1']
            sizes.append(c.get('size', 10))
        text = re.sub(r'[ \t]+', ' ', text).strip()
        if text:
            avg_size = sum(sizes) / len(sizes)
            lines.append((avg_size, text))
    return lines

# 首页柱状图行模式：  x.x%(nnn) x.x%(nnn) 章节名（总nnnn字）
BAR_RE = re.compile(r'^(\d+(?:\.\d+)?%)\((\d+)\)\s+(\d+(?:\.\d+)?%)\((\d+)\)\s+(.+?)（总(\d+)字）$')
# 每章节头："N. 章节名 总字符数：nnnn"
SEC_HDR_RE = re.compile(r'^(\d+)\.\s+(.+?)\s+总字符数：(\d+)$')
# 相似文献表格行头 "N 标题 x.x%（nnn）"
SIM_LINE_RE = re.compile(r'^(\d+)\s+(.+?)\s+(\d+(?:\.\d+)?%)（(\d+)）$')
# 继续行 "作者;导师 - 《来源》- 日期 是否引证：X"
CITE_RE = re.compile(r'^(.*?)\s*-\s*《(.+?)》\s*-\s*(\S+)\s+是否引证：(.+)$')
PAGE_NUM_RE = re.compile(r'^-?\s*\d+\s*-?$')

def is_pagenum(text):
    return bool(re.fullmatch(r'-\s*\d+\s*-', text))

def process_pdf(pdf_path, out_path):
    md_lines = []
    bar_rows = []  # (part_pct, part_count, total_pct, total_count, section, total_chars)
    with pdfplumber.open(pdf_path) as pdf:
        for pi, page in enumerate(pdf.pages):
            chars = clean_page(page)
            lines = group_lines(chars)
            for size, text in lines:
                # 柱状图行
                m = BAR_RE.match(text)
                if m:
                    bar_rows.append(m.groups())
                    continue
                if is_pagenum(text):
                    continue
                if size >= 15:
                    md_lines.append(f'# {text}')
                elif 11.5 <= size < 15:
                    md_lines.append(f'## {text}')
                else:
                    md_lines.append(text)
    # 在"检测结果"段之后插入 bar table
    if bar_rows:
        table = ['', '| 去除本人复制比 | 总文字复制比 | 章节 | 总字符数 |', '|---|---|---|---|']
        for p1, c1, p2, c2, sec, tot in bar_rows:
            table.append(f'| {p1} ({c1}) | {p2} ({c2}) | {sec} | {tot} |')
        table.append('')
        # 插在第一次出现 "检测结果" 之后
        for i, ln in enumerate(md_lines):
            if ln and '检测结果' in ln:
                md_lines = md_lines[:i+1] + table + md_lines[i+1:]
                break
        else:
            md_lines = md_lines + table

    # 后处理：数字. 章节名 总字符数：nnnn 统一升级为 ##
    sec_re = re.compile(r'^(\d+)\.\s+(.+?)\s+总字符数：(\d+)$')
    fixed = []
    for ln in md_lines:
        if ln is None:
            continue
        body = ln
        # 去掉已存在的 ## 前缀以便统一
        if body.startswith('## '):
            body_body = body[3:]
        else:
            body_body = body
        m = sec_re.match(body_body)
        if m:
            fixed.append(f'## {m.group(1)}. {m.group(2)} 总字符数：{m.group(3)}')
        else:
            fixed.append(ln)
    out_lines = []
    in_table = False
    for ln in fixed:
        is_table_row = ln.startswith('|')
        if is_table_row:
            if not in_table:
                if out_lines and out_lines[-1] != '':
                    out_lines.append('')
                in_table = True
            out_lines.append(ln)
        else:
            if in_table:
                out_lines.append('')
                in_table = False
            # 段落之间保留空行
            if out_lines and out_lines[-1] != '':
                out_lines.append('')
            out_lines.append(ln)
    out = '\n'.join(out_lines)
    out = re.sub(r'\n{3,}', '\n\n', out)
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(out + '\n')
    print(f'wrote {out_path} ({len(out)} chars)')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Convert a CNKI 查重 report PDF to Markdown.')
    parser.add_argument('pdf_path', help='输入查重报告 PDF 路径')
    parser.add_argument('out_path', help='输出 Markdown 路径')
    args = parser.parse_args()
    process_pdf(args.pdf_path, args.out_path)
