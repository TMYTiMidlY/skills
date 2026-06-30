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

把任何本地 Markdown（研报 / 论文 / 笔记，也含自托管 docs-share 内容）导出为可打印 PDF。按质量与复杂度从轻到重大致三档，按需挑：

- **最轻量（pandoc + Calibre `ebook-convert`）**：装个 Calibre 就行，支持 KaTeX 公式、嵌字体；质量一般，适合临时看，见「快速路线」。
- **印刷级（CSS Paged Media 引擎）**：核心链路 `Markdown → pandoc → HTML → CSS Paged Media 引擎 → PDF`，同一份 HTML + CSS 可喂 Prince / Vivliostyle / Paged.js / WeasyPrint 不同引擎对比，见「工具生态定位」起的各节。
- **学术 / 中文友好（Typst）**：不走 HTML/CSS，自成语言与引擎，安装最轻、中文模板生态成熟，见「Typst 路线」。

> 自托管 docs-share 的服务端 / Markdeep 写作惯例见 [docs-share.md](docs-share.md)。

### 快速路线（pandoc → Calibre ebook-convert）

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

### 工具生态定位

四个 CSS Paged Media 引擎都吃**同一份 HTML + CSS**（`@page`、`break-*`、`running()`、`string-set`、`target-counter` 等 W3C CSS Paged Media 规范），可以用同一个 CSS 让不同引擎渲染对比。

| 引擎 | 架构 | 开源 | PDF 质量 | 活跃度 | 适合场景 |
|---|---|---|---|---|---|
| **Prince XML** | 自研 C++ 引擎 | ❌ 闭源（个人非商用免费，PDF 第一页右上角有水印；桌面版 $495、服务器 $3,800） | 天花板 | 商业维护，20 年积累 | 要求极致印刷质量的商业出版 |
| **Vivliostyle** | 自己跑 Chromium，渲染层实现 CSS Paged Media | ✅ AGPL v3 | 好 | 🔥 每日 commit，maintainer MurakamiShinyu 很活跃 | 日本出版圈；CSS Paged Media 规范实现最完整（多栏脚注、竖排、Ruby） |
| **Paged.js** | 纯 JS polyfill 注入普通 Chromium | ✅ MIT | 中上（受 Chromium 限制） | 慢（2026 年几乎停滞） | 在线阅读 / 浏览器内预览分页排版（polyfill 优势：用户打开网页直接看到排版效果，不需要后端） |
| **WeasyPrint** | Python，自研渲染 | ✅ LGPL | 中 | 活跃 | Python 生态、发票类简单文档 |

**另一条路线**——**Typst**：不走 HTML/CSS，自成语言自成引擎，53k+ GitHub stars，学术/论文方向性价比最高（语法比 LaTeX 友好一个数量级，编译速度快 3-4 倍）。已知短板：CJK 标点挤压/竖排/Ruby 仍有 open issue；微排版不如 LaTeX；顶会投稿不接受。

**选型建议**：
- 自己打印看、研报级别 → Prince（免费版水印无所谓）或 Typst
- 视觉上限要拉满 / 杂志感封面 → Vivliostyle 自定义 CSS（默认 theme-techbook 很 plain，真本事靠手写 CSS Paged Media，见下文「Vivliostyle 自定义 CSS 要点」）
- 在线浏览器内预览 → Paged.js（polyfill，纯前端）
- Python 链路、简单文档 → WeasyPrint
- 中文友好、安装最轻、想用现成模板 → Typst（见下文「Typst 路线」）

### Prince XML 无 sudo 安装（pixi 方案）

Prince 官方 tar.gz 解压后 vendor 进项目目录，用 pixi (conda-forge) 补齐缺失动态库。参考实现见 `book-ahzy/pixi.toml` + `scripts/activate.sh`。

**关键步骤**：

1. 下载 `prince-<ver>-ubuntu<ver>-amd64.tar.gz`，解压后整个 `lib/prince/` 拷贝到项目的 `vendor/prince/`
2. `pixi init`，添加 `giflib`、`libwebp`、`aom`、`lcms2` 等 Prince 依赖的动态库
3. 如果 conda-forge 版本号对不上（如 `libavif.so.13` vs `.so.16`），从 Ubuntu archive 手动下载 `.deb` 解压 `.so` 到 `vendor/prince/extra-lib/`
4. `scripts/activate.sh` 注入 `LD_LIBRARY_PATH` 指向 pixi env lib + extra-lib
5. `pixi.toml` 写 task：`prince = "vendor/prince/bin/prince --prefix=vendor/prince"`

**CJK 字体大坑**：

- Prince 能通过 fontconfig 发现 **Variable Font (VF)** 的字体名，但**无法从 VF 中提取 CJK glyph 渲染**——静默失败，报 `no font for CJK character` 但实际已经 `used font: Noto Sans CJK SC`
- Noto Sans CJK 的 **SubsetOTF**（8M）字数不全，会缺字
- **正解**：下载**完整静态 OTF**（`noto-cjk/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf`，~16M）+ Bold 版，放到 `vendor/prince/fonts/`
- **fontconfig 隔离**：pixi 环境的 fontconfig 会把 VF 推给 Prince 导致渲染失败。必须用 `FONTCONFIG_FILE` 指向自定义 `fonts.conf`，只包含 `vendor/prince/fonts/` + `/usr/share/fonts`，在 `activate.sh` 中 `export FONTCONFIG_FILE="${PIXI_PROJECT_ROOT}/vendor/prince/fonts.conf"`

**Paged.js (pagedjs-cli) Chromium 依赖**：

pagedjs-cli 需要 Chromium，而 headless Chromium 缺大量系统库。pixi 可装：`nss`、`libcups`、`atk`、`at-spi2-atk`、`libxkbcommon`、`xorg-libxcomposite`、`xorg-libxdamage`、`xorg-libxrandr`、`xorg-libxfixes`、`libgbm`、`pango`、`cairo`、`alsa-lib`。conda-forge 没有 chromium 本身，但 `~/.cache/puppeteer/` 里已有的 chrome 二进制在 pixi env 内就能跑。调用时加 `--browserArgs "--no-sandbox"`。

**Vivliostyle 复用同一份 chromium 依赖**：vivliostyle-cli 也走 puppeteer 拉 chrome（`~/.cache/vivliostyle/browsers/chrome/linux-*/`），缺库表跟 Paged.js 完全一致，**直接复用上面那份 pixi 包列表**即可，不用重新摸一遍。

**无 pixi 兜底（apt-get download + LD_LIBRARY_PATH）**：当本机连 pixi 都没有、又没 sudo 时的 userland 兜底：

```bash
mkdir -p <work-dir>/.chromium-libs && cd <work-dir>/.chromium-libs
apt-get download libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libasound2 \
  libatk1.0-0 libatk-bridge2.0-0 libatspi2.0-0 libcairo2 libcups2 libgbm1 \
  libnspr4 libnss3 libpango-1.0-0 libxkbcommon0 libxi6 libxrender1 \
  libavahi-client3 libavahi-common3 libharfbuzz0b libpixman-1-0 libthai0 \
  libwayland-server0 libxcb-randr0 libxcb-render0 libxcb-shm0 libdatrie1 libgraphite2-3
for d in *.deb; do dpkg-deb -x "$d" extracted/; done
export LD_LIBRARY_PATH="$PWD/extracted/usr/lib/x86_64-linux-gnu"
```

调 chrome 前注入这个 `LD_LIBRARY_PATH` 即可。**摸依赖的方法**：`ldd <chrome-path> | grep "not found"`，一轮一轮补，最后再 `ldd` 一次确认 “ALL RESOLVED”。

### Markdown → Prince PDF 流水线

标准三步：**预处理引用标签 → pandoc 转 HTML → Prince 渲染**。

**1. 引用标签预处理**（`scripts/process_citations.py`）

把 Markdeep 的 `[#tag]` 引用转为上标编号 `<sup>[1,2,3]</sup>`，文末 `**Bibliography**` 转为有序参考文献列表。这一步在 pandoc 之前跑，因为 pandoc 不认 `[#key]` 语法。

**2. pandoc 转 HTML**

用自定义模板（不用 pandoc 默认样式，否则会干扰 Prince 字体声明）。模板要点：
- `* { font-family: "Noto Sans CJK SC", sans-serif; }` 确保全覆盖
- `@page` 声明纸张、页边距、页码
- `h1` 设 `page-break-before: always` 实现章节分页
- TOC 用 `--toc --toc-depth=3` 自动生成

```bash
pandoc input.md -f markdown -t html5 --standalone --toc --toc-depth=3 \
  --metadata title="..." -V lang=zh-CN \
  --template=scripts/prince-template.html \
  -o output.html
```

**3. Prince 渲染**

```bash
pixi run prince output.html -o output.pdf
```

整条链路封装为一个 shell 脚本一键执行，最后 `scp` 到分享目标。

### Typst 路线

Typst 是非 HTML/CSS 链路里**安装最轻、中文最友好、模板生态正在快速长大**的选项。适合：自用研报、笔记、面试材料这种“挑个现成模板就出 PDF”的场景。

**无 sudo 安装**：

```bash
# 1. typst 二进制（单文件）
curl -fsSL -o /tmp/typst.tar.xz \
  "https://github.com/typst/typst/releases/latest/download/typst-x86_64-unknown-linux-musl.tar.xz"
mkdir -p ~/.local/bin && tar -xJf /tmp/typst.tar.xz -C /tmp
cp /tmp/typst-x86_64-unknown-linux-musl/typst ~/.local/bin/

# 2. 中文字体（Noto Serif SC 完整 OTF；典型场景够用，缺字再补 Bold/Sans）
mkdir -p ~/.local/share/fonts/cjk && cd ~/.local/share/fonts/cjk
BASE="https://raw.githubusercontent.com/notofonts/noto-cjk/main"
curl -fsSL -o NotoSerifSC-Regular.otf "$BASE/Serif/SubsetOTF/SC/NotoSerifSC-Regular.otf"
curl -fsSL -o NotoSerifSC-Bold.otf    "$BASE/Serif/SubsetOTF/SC/NotoSerifSC-Bold.otf"
curl -fsSL -o NotoSansSC-Regular.otf  "$BASE/Sans/SubsetOTF/SC/NotoSansSC-Regular.otf"
curl -fsSL -o NotoSansSC-Bold.otf     "$BASE/Sans/SubsetOTF/SC/NotoSansSC-Bold.otf"
# 编译时用 --font-path 喂给 typst，无需走 fontconfig
typst compile main.typ out.pdf --font-path ~/.local/share/fonts/cjk
```

**现成模板**（按 CJK 友好度排序）：

| 模板 | 路线 | 适合 |
|---|---|---|
| `inelegant-note` | 中文作者，照搬 LaTeX Elegant Book/Note 风 | **首选**：中文研报、教科书、笔记，“第N章 …”自动编号、目录带点引线、罗马/阿拉伯分前后页码全都开箱即用 |
| `ilm` | 极简非小说书 / 笔记 | 想要极简留白派、左对齐封面 + abstract |
| `classicthesis` | 仿 LaTeX ClassicThesis | 文人书味、学位论文 |
| `bookly` | 通用 “Book template” | 偏小说 / 故事书 |

一键拉取：`typst init @preview/<name> <target-dir>`，模板源也会落到 `~/.cache/typst/packages/preview/<name>/<ver>/`，可直接翻它的 `library/template.typ` / `template/custom/parameter.typ` 看暴露的配置项（字体、章节前缀、页边距等）。

**md → typst 转换**：

```bash
pandoc input.md -o body.typ --to typst --shift-heading-level-by=-1
# pandoc 把水平线转成未定义符号 `#horizontalrule`，必须替换
sed -i 's|^#horizontalrule$|#line(length: 30%, stroke: 0.6pt + luma(85%))|' body.typ
```

`--shift-heading-level-by=-1` 把源 md 的 `## 一、…` 提升成 typst 的 `=`（一级章），让模板的“章扉页 / 第N章”机制生效。

**关键坑**：

- **`#include` 不共享父 scope**。在 `main.typ` 里 `#let helper = …` 然后 `#include "body.typ"`，body.typ 里看不到 `helper`。两种解法：
  - **prepend 进 body.typ**：转换流水线最后把 helper 定义注入到 body.typ 头部（推荐，body.typ 自包含可独立编译）
  - 改用 `#import` 模块化，但 import 不能动态拼字符串路径，不灵活
- **`#set heading(numbering: none)` 会让 counter 也不递增**，自定义编号显示要保留 `numbering: "1."` 再用 show rule 控制呈现
- **页眉跟随章节标题**用 `query(selector(heading.where(level:1)).before(here())).at(0, default: none)`，**必须判空**（前辅助页之前没有章节）

### 通用预处理：手写序号去重 + tag/citation 转 chip

不论后续走 Typst 还是 Prince HTML 模板，都有两个**复用率极高的源 md 预处理步骤**：

**1. 剥源 md 里的手写序号**（防止跟模板自动编号重复）

源 md 常用 `## 一、…` / `### 1.1 …` 这种手写序号，套到自动编号模板里会显示成“第二章 二、…” / “2.1 2.1 …”。转换前用 Python regex 剥掉：

```python
import re
src = open('input.md', encoding='utf-8').read()
# 剥 "## 一、" / "## 廿、" 等中文数字序号
chinese_nums = '零一二三四五六七八九十廿百千'
src = re.sub(r'(?m)^(## )[' + chinese_nums + r']+、\s*', r'\1', src)
# 剥 "### 1.1" / "#### 1.2.3" 等阿拉伯多级序号
src = re.sub(r'(?m)^(#{3,4} )(\d+(?:\.\d+)+)\s+', r'\1', src)
open('input-clean.md', 'w', encoding='utf-8').write(src)
```

**2. Markdeep `[#tag]` 引用 → 模板的灰底 chip + 红底参考文献**

源 md 用 `[#talent2026, #ustc_lab]` 行内引用、`[#talent2026]: 来源描述` 列参考文献。Pandoc 转 typst 后会变成 `\[\#talent2026, \#ustc\_lab\]` 这种带反斜杠转义的字面量，要 regex 改写成模板自定义函数调用：

```python
def normalize_tag(s): return s.replace('\\_', '_').strip()

def tags_inline(m):
    items = [normalize_tag(x.lstrip(' \\#')) for x in m.group(1).split(',') if x.strip()]
    return '#tag([' + ' · '.join(items) + '])'

# 行内 [#a, #b]（注意：负前瞻 (?!:) 排除参考文献行；字符类必须含 - 否则 tc-yao 这种漏匹配）
src = re.sub(r'\\\[(\\#[a-zA-Z0-9_\-,\s\\#]+?)\\\](?!:)', tags_inline, src)

# 参考文献行 [#name]: source -> #bibitem([name]) source
src = re.sub(r'(?m)^\\\[\\#([a-zA-Z0-9_\-\\]+?)\\\]:\s*',
             lambda m: f'#bibitem([{normalize_tag(m.group(1))}])', src)

# 第一条 bibitem 前自动插入 "= 参考文献" 章节
first = src.find('#bibitem(')
if first > 0:
    line_start = src.rfind('\n\n', 0, first)
    if line_start > 0:
        src = src[:line_start] + '\n\n= 参考文献\n\n' + src[line_start:]
```

在 body.typ 头部 prepend 配套的 `#let tag(body) = box(...)` 和 `#let bibitem(body) = {box(...); h(0.4em)}`，行内 tag 渲染成灰底小药丸（`#F1F5F9` 底 / `#475569` 字），参考文献条目用红底（`#FEE2E2` 底 / `#7F1D1D` 字 + bold）。

**收尾审计**（必做）：转换完用 `grep -E '\\\\\[\\\\#' body.typ | head` 看是否还有漏网的 `\[\#...\]` 字面量；正则字符类漏 `-` / `:` 后逗号、空格容错不全等都会留尾巴。

### Vivliostyle 自定义 CSS 要点

**默认主题（theme-techbook 等）视觉很 plain**，看起来跟普通技术文档站没差；想做出杂志感 / 印刷品质，必须自己写 CSS Paged Media。pandoc 转 HTML 后塞自定义 `theme.css`，关键招数清单：

- **`@page` 命名页**：`@page cover { ... }` / `@page chapter-open { ... }` / `@page toc { ... }` 让封面、章扉、目录有各自版心和装饰；元素上用 `page: cover` 指定归属
- **跑动页眉**：`@top-left { content: string(chapter-title); }` + `h1 { string-set: chapter-title content(); }` 让页眉自动跟随当前章节
- **章节自动编号**：`body { counter-reset: chapter; }` + `h1 { counter-increment: chapter; }` + `h1::before { content: counter(chapter, decimal-leading-zero); }`，配合超大字号 / 半透明色 / 绝对定位可做出“杂志大背景数字”效果
- **封面纯 CSS 装饰**：`.cover::before` / `::after` 做顶/底彩条；`::before { content: ""; position: absolute; ... }` 拼几何块
- **行内 code → 红色药丸 chip**：`code { background: rgba(185,28,28,.07); border: .5px solid ...; padding: .1em .45em; border-radius: 3px; color: #7f1d1d; }`
- **粗体加荧光底**：`strong { background: linear-gradient(180deg, transparent 60%, rgba(185,28,28,.18) 60%); }`
- **首字下沉**：`h1 + p::first-letter { float: left; font-size: 4.5em; ... }`
- **TOC 引线点**：用 `flex: 1; border-bottom: 1px dotted ...` 占位（pandoc 自动生成的 nav 改造或自己用 anchor list 拼）

### 工作流小坑

- **中间文件多份拷贝会改了旧版没生效**：md → typst 流水线里如果有 `body.typ` 在根目录、又有一份 `tpl/body.typ`，更新转换脚本时只动了一份很容易看不出来。**统一直接写到最终位置**（如直接 `pandoc -o tpl/body.typ`），不要中间 cp
- **无 poppler 时验证 PDF 视觉**：`pdfinfo` / `pdf2image` 都依赖 poppler 系统包；最轻量是 `uv run --with pymupdf python -c "import fitz; doc=fitz.open('x.pdf'); print(len(doc)); doc[0].get_pixmap(dpi=120).save('/tmp/p1.png')"`，渲染单页 PNG 直接 view 看
- **TinyTeX 用 Fandol 中文字体缺异体字**：会出现“煙/會/召開”这种繁体异体字字面缺失（fc-list 显示有但渲染缺）。预处理时把已知缺字用 sed 转简体，或者在模板里给二级字体 fallback 到 Noto CJK

## PDF → 图片

使用 pdftoppm 将 PDF 每页转为 JPEG：

```bash
pdftoppm -jpeg -r 300 document.pdf output_prefix
```

- `-jpeg`：输出 JPEG 格式（也支持 `-png`）
- `-r 300`：分辨率 300 DPI

> `pdftoppm` 来自 poppler-utils，Debian/Ubuntu 安装：`sudo apt install poppler-utils`。

> ⚠️ **poppler 会“静默”把合法的 CJK PDF 渲染成空白——`pdftoppm`/`pdffonts` 不能单独当验收**。
> 实测本机 pixi 版 poppler **26.02.0** 对 **ctex / XeLaTeX 默认 Fandol** 这类 **Adobe-GB1 CID-keyed CFF** 字体渲染失败：`pdftoppm` 转出的图里中文**整页空白**、`pdffonts` 也**不列**该字体，但**退出码 0**，同一份 PDF 在 MuPDF / pdfium / Adobe / Chrome 里中文都正常。
>
> - **别拿 pdftoppm 当“渲染真相”**：转图前用独立引擎交叉验证一句话——能抽出中文＝字形都在，问题出在 poppler 这道渲染：
>   ```bash
>   uv run --with pymupdf python -c "import fitz;d=fitz.open('x.pdf');print(repr(d[0].get_text()[:60]))"
>   ```
> - **要图就换引擎**：`mutool draw -o p%d.png x.pdf`（MuPDF）或 Ghostscript；或降级 pixi 的 poppler；或从源头改 `fontset=ubuntu`（Noto，Identity ROS，poppler 认）。
>
> **结构与触发条件（两层并存）**：
> - **xdvipdfmx 侧**：`fontmap.c` 给**所有 XeTeX 原生字体硬编码 `Identity-H` 编码**；而 Fandol 是 **Adobe-GB1** CID-keyed CFF（已证实 `ROS=(Adobe,GB1,5)`）。于是产出「`Identity-H` 编码 + `GB1` 的 `CIDSystemInfo`」这种不太常规的结构。旁证：ctex 的 **pdfLaTeX 路径**专门加 `cmap=UniGB-UTF16-H`（GB1 的 CMap）正因 Fandol 是 GB1，而 **XeLaTeX 路径没加**。
> - **poppler 侧**：26.02.0 严格按 `GB1` ROS 解码 → 取错/空白；MuPDF / pdfium / Adobe 宽容处理（按 code=GID 直接出字）→ 正常。
> - **诊断验证**：用 pikepdf 把该字体 `CIDSystemInfo /Ordering` 改 `GB1→Identity`，poppler 立刻出字（仅验证用，别真改 PDF）。绕过仍以“换引擎看图 / 源头 `fontset=ubuntu`”为准。

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

- **企业版**：权限范围、应用功能等变更后需要“创建新版本 → 企业管理员审核”，审核通过后才真正生效。
- **个人版**（feishu2md README 明确推荐的类型）：开发者即使用者，权限勾选后立即生效，免版本审核。

所以跟着 README 走个人版路线，不会遇到“权限加了但没发版所以 API 报权限不足”的问题；企业版则必须走审批。

#### 应用身份 vs 用户身份（决定能看到哪些文档）

飞书 OpenAPI 有两套身份凭证，资源可见范围不同：

| 凭证 | 身份 | 授权方式 | 资源范围 |
|---|---|---|---|
| `tenant_access_token` | 应用身份 | 用 `app_id` + `app_secret` 直接换取，无需用户登录 | 应用自身权限范围内的资源 |
| `user_access_token` | 用户身份 | 需要用户走 OAuth 授权流程 | 该登录用户本人能读写的资源 |

feishu2md 走**应用身份**路线（配置里只有 `app_id`/`app_secret`，没有 OAuth 回调）。由此可以推出文档共享的硬性前提：应用本身不是任何文档的成员，`docx:document:readonly` 授予的只是**调用 API 的能力**，并不等于自动能读到你的某一篇文档。

所以 README 给出的办法是：**“分享 → 开启链接分享 → 互联网上获得链接的人可阅读 → 复制链接”**——开了这档分享后，链接本身就是访问凭据，`tenant_access_token` 带上就能读。单文档/文件夹下载都按这个流程取 URL。知识库批量下载用知识库设置页 URL，同样要求该知识库对链接可见。

如果以后要读“只对自己可见、不想开公开链接”的文档，就得切到 `user_access_token` 路线——feishu2md 不支持这条。

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
