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
trash-put timidly_temp.html
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

[feishu2md](https://github.com/Wsine/feishu2md) 把飞书/Lark 新版文档导出为 Markdown，支持单文档、文件夹批量和知识库批量下载，并可下载文档内图片。

### API Token 与权限

配置文件需要 App ID 和 App Secret。项目 README 推荐在飞书开发者后台创建企业自建应用（个人版），并列出这些权限：

- `docx:document:readonly`：获取文档基本信息、获取文档所有块；单个新版文档转 Markdown 的核心权限
- `docs:document.media:download`：下载云文档中的图片和附件；文档含图片且需要落本地时需要
- `drive:file:readonly`：获取文件夹中的文件清单；`--batch` 批量下载文件夹时需要
- `wiki:wiki:readonly`：获取知识空间节点信息；`--wiki` 批量下载知识库时需要

#### 个人版 vs 企业版：权限何时生效

企业自建应用有两种形态，发布流程不一样：

- **企业版**：权限范围、应用功能等变更后需要"创建新版本 → 企业管理员审核"，审核通过后才真正生效。
- **个人版**（feishu2md README 明确推荐的类型）：开发者即使用者，权限勾选后立即生效，免版本审核。

所以跟着 README 走个人版路线，不会遇到"权限加了但没发版所以 API 报权限不足"的问题；企业版则必须走审批。

#### 应用身份 vs 用户身份（决定能看到哪些文档）

飞书 OpenAPI 有两套身份凭证，资源可见范围不同：

| 凭证 | 身份 | 授权方式 | 资源范围 |
|---|---|---|---|
| `tenant_access_token` | 应用身份 | 用 `app_id` + `app_secret` 直接换取，无需用户登录 | 应用自身权限范围内的资源 |
| `user_access_token` | 用户身份 | 需要用户走 OAuth 授权流程 | 该登录用户本人能读写的资源 |

feishu2md 走**应用身份**路线（配置里只有 `app_id`/`app_secret`，没有 OAuth 回调）。由此可以推出文档共享的硬性前提：应用本身不是任何文档的成员，`docx:document:readonly` 授予的只是**调用 API 的能力**，并不等于自动能读到你的某一篇文档。

所以 README 给出的办法是：**"分享 → 开启链接分享 → 互联网上获得链接的人可阅读 → 复制链接"**——开了这档分享后，链接本身就是访问凭据，`tenant_access_token` 带上就能读。单文档/文件夹下载都按这个流程取 URL。知识库批量下载用知识库设置页 URL，同样要求该知识库对链接可见。

如果以后要读"只对自己可见、不想开公开链接"的文档，就得切到 `user_access_token` 路线——feishu2md 不支持这条。

### 配置

```bash
feishu2md config --appId <your_id> --appSecret <your_secret>
feishu2md config
```

`feishu2md config` 会打印配置文件路径和当前配置。当前项目源码里的配置结构为：

```json
{
  "feishu": {
    "app_id": "<your_id>",
    "app_secret": "<your_secret>"
  },
  "output": {
    "image_dir": "static",
    "title_as_filename": false,
    "use_html_tags": false,
    "skip_img_download": false
  }
}
```

- `image_dir`：图片下载目录，默认 `static`
- `title_as_filename`：是否用文档标题作为 Markdown 文件名；默认用文档 token
- `use_html_tags`：是否在输出中使用 HTML 标签表达部分结构
- `skip_img_download`：是否跳过图片下载

Docker 版本也支持环境变量：

```bash
FEISHU_APP_ID=<your_id>
FEISHU_APP_SECRET=<your_secret>
GIN_MODE=release
```

### 命令

如果你没有明确指定 `output_directory`，我默认把这类临时产物放到 `/tmp/feishu2md`。

单文档：

```bash
feishu2md dl "https://my.feishu.cn/docx/<doc-token>"
# 产物：<文档标题>.md + static/ 图片目录
```

指定输出目录：

```bash
feishu2md dl -o output_directory "https://domain.feishu.cn/docx/<doc-token>"
```

批量下载文件夹：

```bash
feishu2md dl --batch -o output_directory "https://domain.feishu.cn/drive/folder/<folder-token>"
```

批量下载知识库：

```bash
feishu2md dl --wiki -o output_directory "https://domain.feishu.cn/wiki/settings/<space-id>"
```

调试 API 返回：

```bash
feishu2md dl --dump "https://domain.feishu.cn/docx/<doc-token>"
```

### 表格后处理

`feishu2md` 会把很多表格输出成 HTML `<table>`，即使 `use_html_tags=false` 也一样——因为飞书表格允许合并单元格，pipe 语法表达不了。如果你要发到 GitHub、Markdown wiki 或其他更偏 CommonMark 的地方，可以再跑一遍 [scripts/feishu_html_table_to_gfm.py](../scripts/feishu_html_table_to_gfm.py)：

```bash
uv run scripts/feishu_html_table_to_gfm.py /tmp/feishu2md/output.md --in-place
```

如果不想覆盖原文件，改用 `-o` 输出到新文件。
