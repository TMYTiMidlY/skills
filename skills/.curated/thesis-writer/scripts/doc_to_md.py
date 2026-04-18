#!/usr/bin/env python3
"""
将 Word .doc/.docx 论文文件转换为带内联脚注的分章 Markdown。

工作流程：
1. .doc → .docx（LibreOffice headless）
2. .docx → raw .md（pandoc --wrap=none）
3. 提取所有 [^N] 脚注定义，展开为正文内 （脚注：…） 格式
4. 去除 pandoc 产生的多余反斜杠转义（\[ \] 等）
5. 按章节拆分为多个 md 文件，存入同名目录
6. 原文档也复制一份进目录

用法：
    python3 doc_to_md.py <input.doc 或 input.docx>

依赖：
    libreoffice（处理 .doc）
    pandoc

输出目录结构：
    <文件名不含扩展名>/
    ├── 00_前言与参考文献.md
    ├── 01_第1章_<标题>.md
    ├── 02_第2章_<标题>.md
    ├── ...
    └── <原始文件名>
"""

import re
import os
import sys
import shutil
import subprocess
import tempfile
from pathlib import Path


def convert_to_docx(src: Path, tmpdir: str) -> Path:
    """如果是 .doc，用 LibreOffice 转为 .docx；如果已经是 .docx 直接返回。"""
    if src.suffix.lower() == '.docx':
        return src
    subprocess.run(
        ['libreoffice', '--headless', '--convert-to', 'docx', str(src), '--outdir', tmpdir],
        check=True
    )
    return Path(tmpdir) / (src.stem + '.docx')


def convert_to_md(docx: Path, tmpdir: str) -> Path:
    out = Path(tmpdir) / (docx.stem + '_raw.md')
    subprocess.run(
        ['pandoc', str(docx), '-o', str(out), '--wrap=none'],
        check=True
    )
    return out


def remove_escapes(content: str) -> str:
    """去除 pandoc 产生的 \[ \] 等多余转义。"""
    content = re.sub(r'\\(\[)', '[', content)
    content = re.sub(r'\\(\])', ']', content)
    return content


def inline_footnotes(lines: list[str]) -> list[str]:
    """将 [^N] 脚注定义提取，并展开到正文中；返回不含脚注定义的行列表。"""
    fn_def = re.compile(r'^\[\^(\d+)\]:\s*(.*)')
    inline_ref = re.compile(r'\[\^(\d+)\](?!:)')

    # 第一遍：收集定义
    defs: dict[str, str] = {}
    for line in lines:
        m = fn_def.match(line)
        if m:
            defs[m.group(1)] = m.group(2).strip()

    # 第二遍：替换并过滤
    result = []
    for line in lines:
        if fn_def.match(line):
            continue
        new_line = inline_ref.sub(lambda m: f'（脚注：{defs.get(m.group(1), m.group(0))}）', line)
        result.append(new_line)
    return result


def find_split_points(lines: list[str]) -> dict:
    """定位各章节和参考文献的起始行号。"""
    chapter_starts: dict[str, int] = {}
    ref_start: int | None = None
    toc_end_hint: int = 0

    for i, line in enumerate(lines):
        s = line.strip()
        # 目录中章标题以 **N** 结尾；正文章标题不以粗体页码结尾
        if re.search(r'\*\*\d+\*\*\s*$', s):
            toc_end_hint = i

    for i, line in enumerate(lines):
        if i <= toc_end_hint:
            continue
        s = line.strip()
        for ch in '1234':
            if s.startswith(f'第{ch}章') and ch not in chapter_starts:
                chapter_starts[ch] = i
        if s == '参考文献' and ref_start is None:
            ref_start = i

    return {'chapters': chapter_starts, 'ref': ref_start}


def split_and_write(lines: list[str], splits: dict, outdir: Path, original_src: Path):
    """按分割点写出各 md 文件，并复制原始文档。"""
    ch = splits['chapters']
    ref = splits['ref']

    ordered = sorted(ch.items(), key=lambda x: x[0])
    bounds: list[tuple[str, int, int]] = []
    for idx, (num, start) in enumerate(ordered):
        end = ordered[idx + 1][1] if idx + 1 < len(ordered) else ref
        bounds.append((num, start, end))

    sections = {
        '00': lines[:bounds[0][1]] + [''] + lines[ref:],
    }
    chapter_titles = {
        '1': '绪论', '2': '历史考察', '3': '逻辑特征和驱动机制', '4': '实践审视和优化进路'
    }
    for num, start, end in bounds:
        sections[f'0{num}'] = lines[start:end]

    outdir.mkdir(parents=True, exist_ok=True)

    filenames = {
        '00': '00_前言与参考文献.md',
    }
    for num, _, _ in bounds:
        title = chapter_titles.get(num, f'第{num}章')
        first_line = lines[ch[num]].strip()
        m = re.match(r'第\d+章\s*(.*)', first_line)
        if m and m.group(1).strip():
            title = m.group(1).strip()[:20]
        filenames[f'0{num}'] = f'0{num}_第{num}章_{title}.md'

    for key, fname in filenames.items():
        text = '\n'.join(sections[key])
        text = re.sub(r'\n{3,}', '\n\n', text)
        (outdir / fname).write_text(text, encoding='utf-8')
        print(f'  写出: {outdir / fname}')

    shutil.copy(original_src, outdir)
    print(f'  复制原文: {outdir / original_src.name}')


def main():
    if len(sys.argv) < 2:
        print('用法: python3 doc_to_md.py <文件.doc 或 文件.docx>')
        sys.exit(1)

    src = Path(sys.argv[1]).resolve()
    if not src.exists():
        print(f'文件不存在: {src}')
        sys.exit(1)

    outdir = src.parent / src.stem
    print(f'输入: {src}')
    print(f'输出目录: {outdir}')

    with tempfile.TemporaryDirectory() as tmpdir:
        print('步骤 1/3: 转换为 docx...')
        docx = convert_to_docx(src, tmpdir)

        print('步骤 2/3: pandoc 转为 markdown...')
        raw_md = convert_to_md(docx, tmpdir)

        print('步骤 3/3: 处理脚注和拆分章节...')
        content = raw_md.read_text(encoding='utf-8')
        content = remove_escapes(content)
        lines = content.split('\n')
        lines = inline_footnotes(lines)
        splits = find_split_points(lines)
        split_and_write(lines, splits, outdir, src)

    print('完成！')


if __name__ == '__main__':
    main()
