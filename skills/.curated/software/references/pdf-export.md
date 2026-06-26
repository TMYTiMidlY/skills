# Markdown → PDF 导出（CSS Paged Media 路线）

把自托管 doc-share / 任何本地 Markdown 研报导出为可打印 PDF。核心链路：`Markdown → pandoc → HTML → CSS Paged Media 引擎 → PDF`。

> 服务端 / WebDAV / Markdeep 写作惯例见 [doc-share.md](doc-share.md)；如果源文件需要先做格式转换（例如先从飞书 / Word 转 Markdown），见 [format-conversion.md](format-conversion.md)。

## 工具生态定位

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

## Prince XML 无 sudo 安装（pixi 方案）

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

## Markdown → Prince PDF 流水线

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

## Typst 路线

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

## 通用预处理：手写序号去重 + tag/citation 转 chip

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

## Vivliostyle 自定义 CSS 要点

**默认主题（theme-techbook 等）视觉很 plain**，看起来跟普通技术文档站没差；想做出杂志感 / 印刷品质，必须自己写 CSS Paged Media。pandoc 转 HTML 后塞自定义 `theme.css`，关键招数清单：

- **`@page` 命名页**：`@page cover { ... }` / `@page chapter-open { ... }` / `@page toc { ... }` 让封面、章扉、目录有各自版心和装饰；元素上用 `page: cover` 指定归属
- **跑动页眉**：`@top-left { content: string(chapter-title); }` + `h1 { string-set: chapter-title content(); }` 让页眉自动跟随当前章节
- **章节自动编号**：`body { counter-reset: chapter; }` + `h1 { counter-increment: chapter; }` + `h1::before { content: counter(chapter, decimal-leading-zero); }`，配合超大字号 / 半透明色 / 绝对定位可做出“杂志大背景数字”效果
- **封面纯 CSS 装饰**：`.cover::before` / `::after` 做顶/底彩条；`::before { content: ""; position: absolute; ... }` 拼几何块
- **行内 code → 红色药丸 chip**：`code { background: rgba(185,28,28,.07); border: .5px solid ...; padding: .1em .45em; border-radius: 3px; color: #7f1d1d; }`
- **粗体加荧光底**：`strong { background: linear-gradient(180deg, transparent 60%, rgba(185,28,28,.18) 60%); }`
- **首字下沉**：`h1 + p::first-letter { float: left; font-size: 4.5em; ... }`
- **TOC 引线点**：用 `flex: 1; border-bottom: 1px dotted ...` 占位（pandoc 自动生成的 nav 改造或自己用 anchor list 拼）

## 工作流小坑

- **中间文件多份拷贝会改了旧版没生效**：md → typst 流水线里如果有 `body.typ` 在根目录、又有一份 `tpl/body.typ`，更新转换脚本时只动了一份很容易看不出来。**统一直接写到最终位置**（如直接 `pandoc -o tpl/body.typ`），不要中间 cp
- **无 poppler 时验证 PDF 视觉**：`pdfinfo` / `pdf2image` 都依赖 poppler 系统包；最轻量是 `uv run --with pymupdf python -c "import fitz; doc=fitz.open('x.pdf'); print(len(doc)); doc[0].get_pixmap(dpi=120).save('/tmp/p1.png')"`，渲染单页 PNG 直接 view 看
- **TinyTeX 用 Fandol 中文字体缺异体字**：会出现“煙/會/召開”这种繁体异体字字面缺失（fc-list 显示有但渲染缺）。预处理时把已知缺字用 sed 转简体，或者在模板里给二级字体 fallback 到 Noto CJK
