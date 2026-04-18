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

## 飞书 / Lark 文档 → Markdown（feishu2md）

[feishu2md](https://github.com/Wsine/feishu2md) 把飞书/Lark 文档导出为 Markdown，内联图片自动下载。已在本机 `~/.config/feishu2md/config.json` 配好 App ID/Secret，个人空间文档可直接拉。

```bash
feishu2md dl "https://my.feishu.cn/docx/<doc-token>"
# 产物：<文档标题>.md + static/ 图片目录
```

**已知坑**：

- **表格一律输出成 HTML `<table>`（带 `<br/>`）**，即使 `use_html_tags=false` 也一样——因为飞书表格允许合并单元格，pipe 语法表达不了。要在 Markdeep/GitHub 上样式统一，上传前手动把 `<table>...</table>` 换成 GitHub pipe 语法。
- 公式块转 `$$...$$`，一般能直接 KaTeX 渲染；长公式偶发漏括号，需人工核。
- 本机 App 凭据：`cli_a96a29dedfb99bb3`（如失效用 `feishu2md config --appId ... --appSecret ...` 重配）。

## WebDAV 上传（自托管分享）

配合 vps-use 里记录的 Caddy 反代 + Markdeep viewer 方案，把本地 Markdown 推到自己的 WebDAV 即得分享链接。凭据从 `~/.env` 读（`WEBDAV_URL / WEBDAV_USER / WEBDAV_PASS` 三件套，写在 skill 里的是模式，不是具体地址）。

```bash
set -a; source ~/.env; set +a
curl -u "$WEBDAV_USER:$WEBDAV_PASS" -T local.md "$WEBDAV_URL/远程文件名.md"
# 返回 201=新建，204=覆盖成功
```

- 中文文件名直接传，Caddy/WebDAV 自动 URL 编码。
- 建目录：`curl -u "$WEBDAV_USER:$WEBDAV_PASS" -X MKCOL "$WEBDAV_URL/subdir"`。
- Markdeep 预览里 FAQ/短问答不要用连续 `### 1. ...` 小标题；默认标题和代码块 margin 偏大。改用有序列表 + 加粗问题会更紧凑。
- 配合 feishu2md：`feishu2md dl <url>` → 手动把 `<table>` 改成 pipe 表 → `curl -T ... "$WEBDAV_URL/..."`，三步完成"飞书文档 → 自托管可分享 MD"。
