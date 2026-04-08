# 格式转换

## LaTeX → Word

使用 pandoc 转换，支持参考文献和引用样式：

```bash
pandoc --citeproc --bibliography=qham.bib --csl=https://www.zotero.org/styles/chinese-gb7714-1987-numeric qhpmNew.tex -o main.docx
```

- `--citeproc`：处理参考文献引用
- `--bibliography`：指定 BibTeX 文献库
- `--csl`：指定引用格式样式（此处为 GB/T 7714 国标格式）

## Markdown → PDF

通过 pandoc 转 HTML 再用 ebook-convert 生成 PDF，支持 KaTeX 数学公式：

```bash
pandoc input.md -o timidly_temp.html -s --katex
ebook-convert timidly_temp.html output.pdf --embed-all-fonts --pdf-default-font-size 14
rm timidly_temp.html
```

- `--katex`：使用 KaTeX 渲染数学公式
- `--embed-all-fonts`：嵌入所有字体，确保跨平台一致
- `--pdf-default-font-size 14`：设置默认字号

> `ebook-convert` 来自 [Calibre](https://calibre-ebook.com/)，需提前安装。

## PDF → 图片

使用 pdftoppm 将 PDF 每页转为 JPEG：

```bash
pdftoppm -jpeg -r 300 document.pdf output_prefix
```

- `-jpeg`：输出 JPEG 格式（也支持 `-png`）
- `-r 300`：分辨率 300 DPI

> `pdftoppm` 来自 poppler-utils，Debian/Ubuntu 安装：`sudo apt install poppler-utils`。
