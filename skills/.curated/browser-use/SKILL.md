---
name: browser-use
description: 浏览器自动化操作，包括通过 MCP/Playwright/Camoufox 操控页面、使用已有浏览器登录态、截图、提取页面嵌入的 pdf.js 数据、下载受保护文件等。当用户提到浏览器自动化、网页截图、下载浏览器中预览的 PDF、绕过下载限制、提取嵌入数据时触发。
---

# Browser Use Skill

## 触发条件

当用户提到以下场景时触发：
- 需要通过浏览器自动化执行操作
- 需要用 Playwright、Camoufox 或 MCP 浏览器工具访问网页、截图、填表
- 需要下载浏览器中预览的 PDF 或文件
- 需要提取浏览器中嵌入的 pdf.js、pdfjs 数据
- 需要绕过网站的直接下载限制获取资源

## 方案选择

除非用户已经明确指定工具，或当前环境只有一种可用方案，否则先让用户选择浏览器方案。问题保持简短，例如：

```text
你想用哪种浏览器方案：1. 接管当前 Chrome 登录态 2. Playwright 脚本/MCP 3. Camoufox 4. camoufox-browser CLI/MCP？
```

选择依据：
- 选择 `open-claude-in-chrome` MCP：已有登录态或需要接管当前 Chrome/Chromium 页面。
- 选择 Playwright：需要可复现的脚本、批量截图、填表或自动化测试。
- 选择 Camoufox：需要 Firefox/Camoufox 指纹、GeoIP、版本通道等能力；它是 Playwright 兼容 API，不是另一套页面操作模型。
- 选择 `camoufox-browser`：需要 agent 风格的浏览器 CLI/MCP；它是第三方年轻项目，稳定性按实验工具看。

## open-claude-in-chrome MCP

**插件信息**:
- GitHub: https://github.com/noemica-io/open-claude-in-chrome
- 作者: [Noemica (Sebastian Sosa)](https://github.com/CakeCrusher)
- License: MIT
- 功能: 浏览器自动化，支持 18 个 MCP tools

该插件是 Claude 官方 Chrome 扩展的 clean-room 实现，移除了域名黑名单限制，支持任意 Chromium 浏览器。

常用操作：

```
# 获取页面 DOM
read_page

# 在 iframe 中执行 JavaScript
javascript_tool

# 获取 tab 列表
tabs_context_mcp
```

查找嵌入 iframe：

```javascript
JSON.stringify({iframes: document.querySelectorAll('iframe').length, iframeSrc: document.querySelector('iframe')?.src})
```

## Playwright / Camoufox

Playwright 是通用浏览器自动化方案；如果当前环境已经提供 Playwright MCP 工具，优先用它完成 `snapshot/click/fill/screenshot` 这类动作。没有 MCP 时，用临时脚本执行。

Camoufox 和 Playwright 的关系：Camoufox 提供 Playwright 兼容的 Python API，底层浏览器是改过的 Firefox/Camoufox；页面操作仍按 Playwright 的 `page.goto()`、`page.click()`、`page.screenshot()` 等模型写。官方 `camoufox` CLI 主要管浏览器版本同步、切换和下载，不是完整网页交互 CLI。

### Camoufox 的三层依赖（先建这个心智模型）

跑通 Camoufox 要同时凑齐三层，缺任一层都起不来，而且三层来源完全不同：

1. **Python 包 / CLI**（`cloverlabs-camoufox[geoip]`）—— 只在 PyPI，**conda-forge 没有**（实测 `pixi search camoufox` / `cloverlabs-camoufox` 均查无）。这层只能 `uv`/`pip` 装，pixi 装不了。
2. **浏览器二进制**（改过的 Firefox）—— 不在 PyPI wheel 里，靠 `camoufox fetch` 从 GitHub release 下载，缓存在 `~/.cache/camoufox/browsers/...`。
3. **系统 GTK/X11/ALSA 共享库**（`libgtk-3.so.0`、`libasound.so.2` 等十几个 `.so`）—— OS 层的库，**不在任何 PyPI wheel 里**。有桌面的机器系统自带；纯 headless server / WSL 等缺这层，不补就挂在 `XPCOMGlueLoad`。

> **"既然都用 pixi 了，为什么还要 uv？"** —— pixi（`pixi exec` 或 global env）只能装 **conda 包**，可以补第 3 层系统库，但 camoufox 那个包只在 PyPI、conda-forge 没有，pixi 装不了，第 1 层只能交给 uv。**例外**：pixi **项目**支持 `[pypi-dependencies]`，能让 pixi 连 camoufox 一起包办、彻底不用 uv（见方案 C），代价是要建一个常驻项目目录；若要"临时、不留痕迹、任意仓库可跑"，就还得 pixi（补库）+ uv（装 camoufox）分工（方案 A/B）。

### 包 / 通道与二进制来源

包/通道关系：
- `camoufox`：官方稳定 PyPI wrapper，但 release 通常延迟。
- `cloverlabs-camoufox`：更新的实验 wrapper，仍提供 `camoufox` import/CLI 命名空间。
- `camoufox-browser`：第三方 CLI/MCP wrapper，依赖 `cloverlabs-camoufox[geoip]>=0.5.5`，适合 agent 风格的 `open/snapshot/click/fill/screenshot`，但项目还年轻。

浏览器二进制不是放在 PyPI wheel 里；`python -m camoufox fetch` / `camoufox fetch` 会下载对应 Camoufox browser release。实测 `cloverlabs-camoufox` 的 `official/stable` 曾拉取 GitHub release：`daijro/camoufox/releases/download/v135.0.1-beta.24/...zip`。PyPI 只负责安装 Python 包和 CLI。

### 管浏览器版本：`uvx --from`（跑 CLI 命令）

CLI 只管第 2 层（浏览器二进制的同步/切换/下载）。`uvx`（即 `uv tool run`）的 `--from` 指定"提供这个命令的包"，是**跑 CLI 命令**专用——别和下面跑脚本的 `uv run --with` 混了：

```bash
uvx --from "cloverlabs-camoufox[geoip]" camoufox sync
uvx --from "cloverlabs-camoufox[geoip]" camoufox set official/stable
uvx --from "cloverlabs-camoufox[geoip]" camoufox fetch
uvx --from "cloverlabs-camoufox[geoip]" camoufox version
```

### 跑页面脚本：`uv run --with`

脚本里 `from camoufox.sync_api import Camoufox`，页面操作按 Playwright 模型写。**跑脚本**（不是 CLI 命令）用 `uv run --with` 注入第 1 层依赖——`uv run` **没有 `--from`**（`--from` 是 `uvx`/`uv tool run` 跑命令时才有的），脚本一律用 `--with`：

```bash
uv run --with "cloverlabs-camoufox[geoip]" script.py
```

⚠️ 这条在**有桌面环境**的机器直接能跑；在无桌面库、无 sudo 的机器（headless server / WSL）会因缺第 3 层系统库挂掉，要先按下文「补齐系统库」补好再跑。

### 补齐系统库（无桌面 / 无 sudo 环境）

无桌面库、又没免密 sudo 的机器（纯 headless server、WSL 等）缺第 3 层系统库，纯按上面的 `uv run --with` 跑脚本会挂：

```text
libgtk-3.so.0: cannot open shared object file
Couldn't load XPCOM.
```

注意 `uv` 只解决两层——Python 包/CLI、浏览器二进制——它**不提供 OS 层的 `.so`**，缺的系统库不在任何 PyPI wheel 里，`uv run --with` 装得再对也没用。无 sudo 时用 pixi 装一份用户态的库，再用 `LD_LIBRARY_PATH` 指过去。

实测确认的库清单（conda-forge 包名）：

- `gtk3`、`alsa-lib` 是**启动硬依赖**，缺任一启动即失败（连开 `about:blank` 都不行）。装 `gtk3` 会自动拖入它的传递依赖 gdk-pixbuf/cairo/pango/atk/xorg-libX*/libxcb，不用单独列。
- `nss` **不要装**：Camoufox 浏览器目录（`~/.cache/camoufox/browsers/.../`）自带整套 NSS（`libnss3.so`/`libssl3.so`/`libnspr4.so`…），HTTPS/TLS 走它自带的。实测去掉 pixi 的 nss 后真实 HTTPS 抓取仍 200，所以装它纯冗余——`camoufox-libs` 只装 `gtk3`+`alsa-lib` 即可。

补库有三种装法，**默认用方案 A**（库全局一份、任意脚本复用）；一次性/任意仓库临时跑用方案 B；长期固定项目要最省事用方案 C。

#### 方案 A（默认）：全局库 env + uv（库一份全局共享，任意脚本复用）

`pixi global install <pkg>` 默认给每个包单独建一个**同名独立 env**（这就是平时只见到装单个工具的原因）。要把多个包塞进**同一个** env，得用 `-e`/`--environment <envname>` 指定共同的 env 名：

```bash
# -e 指定共同 env 名，把库装进同一个 env；只装这两个，不装 nss（camoufox 自带，见上）
pixi global install -e camoufox-libs gtk3 alsa-lib
```

这些库包会把 `gtk-launch`/`certutil`/`aserver` 等命令暴露到 `~/.pixi/bin`（纯当库源用不到，且可能与别的 env 撞名）。pixi 0.68 没有 `--no-expose` 开关，改在 manifest 里把该 env 的 `exposed` 清空再 sync：

```bash
# 编辑 ~/.pixi/manifests/pixi-global.toml，把 [envs.camoufox-libs] 一段改成 exposed = {}
#   [envs.camoufox-libs]
#   exposed = {}
pixi global sync     # 移除已暴露的命令；env 的 lib/*.so 原样保留，不受影响
```

`exposed`（软链命令到 `~/.pixi/bin`）和 `LD_LIBRARY_PATH`（动态链接器找 `.so`）是正交的两件事：清空 `exposed` 只砍 PATH 里的命令，`lib/*.so` 一个不少，LD path 照常能用。

跑脚本时把 env 的 lib 目录 + Camoufox 二进制目录都加进 `LD_LIBRARY_PATH`：

```bash
CFDIR=$(ls -d ~/.cache/camoufox/browsers/official/*/ | tail -1)
export LD_LIBRARY_PATH="$HOME/.pixi/envs/camoufox-libs/lib:$CFDIR"
uv run --with "cloverlabs-camoufox[geoip]" script.py
```

#### 方案 B：`pixi exec` 临时跑（不建项目、任意仓库、不留痕迹）

不想预装全局 env 时用 `pixi exec`——它是 pixi 的 uvx 式临时环境：按 spec 把 conda 包装进缓存 env、跑一次性命令，**不在当前目录留任何 `.pixi`/`pixi.toml`**，可在任意仓库目录下直接跑（实测在 git 仓库里跑完 `git status` 无新增）。

这个临时 env 落在 `~/.cache/rattler/cache/cached-envs-v0/<hash>/`，不在 cwd——**rattler 是 pixi 底层那套用 Rust 写的 conda 包管理库**（负责解析/下载/装包），`pixi exec` 的一次性 env 交给它建在它自己的 XDG 缓存目录里，所以既不污染当前仓库、又能按"包集合的 hash"复用同一份。清理用 `pixi clean cache --exec`。

> 在"不留痕迹"这个目标下**不要**改用 `pixi run --manifest-path`/`pixi init` + toml：那要一个 manifest 目录、会在它旁边落 `.pixi/` env，等于建常驻项目目录（那是方案 C 的做法，接受常驻目录时才用）。`pixi exec` 才是 `uv run --with` 那种"任意位置临时跑"的等价物。

`pixi exec` 只接 conda matchspec（不接 PyPI，原因见上「三层依赖」），所以分工：第 3 层系统库走 `pixi exec -s`，第 1 层 camoufox 包仍走 `uv run --with`，两者拼在一条命令里：

```bash
CFDIR=$(ls -d ~/.cache/camoufox/browsers/official/*/ | tail -1)
pixi exec -s gtk3 -s alsa-lib -- bash -c '
  export LD_LIBRARY_PATH="$CONDA_PREFIX/lib:'"$CFDIR"'"
  uv run --with "cloverlabs-camoufox[geoip]" script.py
'
```

`pixi exec` 会把 `CONDA_PREFIX` 指向那个临时 env（`$CONDA_PREFIX/lib` 即 gtk3/alsa-lib 的 `.so`），所以 LD path 用 `$CONDA_PREFIX/lib:$CFDIR` 就够；`$CFDIR`（Camoufox 浏览器二进制目录）提供它自带的 NSS。`uv` 靠 PATH 继承在临时 env 里可见。

#### 方案 C：pixi 项目（建一个常驻项目目录，之后 `pixi run` 一条命令搞定）

如果接受**建一个常驻项目目录**（不要求"任意仓库、不留痕迹"），这是跑起来最省事的：把三层依赖全塞进一个 pixi 项目，pixi 一手包办 camoufox 包 + 系统库 + LD path，跑脚本就一条 `pixi run`，**不用 uv、不用手动 `export`**。

```bash
pixi init camoufox-runner    # 或手动建目录、写 pixi.toml
cd camoufox-runner
```

`pixi.toml`：

```toml
[workspace]
channels = ["conda-forge"]
platforms = ["linux-64"]

[dependencies]            # 第 3 层系统库（conda）
python = "3.12.*"
gtk3 = "*"
alsa-lib = "*"

[pypi-dependencies]       # 第 1 层 camoufox 包（PyPI；pixi 项目支持装 pypi 包）
cloverlabs-camoufox = { version = "*", extras = ["geoip"] }

[activation.env]          # 第 2 层 LD path：声明一次，pixi run 每次自动注入
# 末尾换成本机 camoufox 浏览器目录（camoufox fetch 下载的二进制）
LD_LIBRARY_PATH = "$CONDA_PREFIX/lib:/home/<you>/.cache/camoufox/browsers/official/<ver>"
```

然后把脚本丢进项目目录（或给绝对路径），一条命令跑：

```bash
pixi run python script.py    # 无手动 export、无 uv，pixi 全包办
```

省事的关键有两点：① 和方案 A/B 不同，pixi **项目**支持 `[pypi-dependencies]`，所以连第 1 层 camoufox 包都由 pixi 装进项目 env（实测模块落在 `.pixi/envs/default/.../site-packages/camoufox`，全程不经 uv）；② `[activation.env]` 把 LD path 钉死、`pixi run` 自动注入——注意**裸 `pixi run` 并不会自动设 LD path**（pixi/conda 默认靠 RPATH，而 camoufox 那个独立 Firefox 二进制没有指向 env 的 RPATH），所以这行 `[activation.env]` 声明正是"不用手动 export"的来源，少了它照样挂 `libgtk`。第 2 层浏览器二进制仍要先 `camoufox fetch` 下载一次（缓存全机共享）。

#### 三个方案怎么选

- **方案 A（全局库 env + uv）【默认】**：预装一份 `camoufox-libs` 全局 env、库全局共享；跑脚本要先 `export LD_LIBRARY_PATH` 再 `uv run --with`。适合多个零散脚本复用同一份库，是日常默认选择。
- **方案 B（`pixi exec` 临时跑）**：零预装、一条命令临时拉起、当前目录不留痕迹（env 在 rattler 缓存）；首次要现装 conda 包。适合在任意仓库里一次性临时跑。
- **方案 C（pixi 项目）**：建一个常驻项目目录；之后 `pixi run python script.py` 一条命令，**不用 uv、不用手动 export**，pixi 把三层全包了。代价是多一个常驻目录（含 `.pixi/`）。适合长期固定的 camoufox 项目、要最省事。

三个方案都已实测跑通真实 HTTPS（`example.com` 200）；浏览器二进制缓存（`~/.cache/camoufox`）三者共享。

### 反爬实测记录

普通 `urllib` 访问 PyPI 项目页遇到 `Client Challenge`；直接调用裸 Camoufox binary 截图也得到挑战/空白页；用 Python wrapper 启动 Camoufox headless 后，多次访问 `https://pypi.org/project/camoufox/` 和 `https://pypi.org/project/cloverlabs-camoufox/` 成功拿到标题，并保存截图到 `/tmp/pypi-camoufox-wrapper-js.png`。这说明在当时环境下可以通过，但不要承诺对所有站点、IP 和版本稳定绕过。

## pdf.js 数据提取

当页面嵌入了 pdf.js 阅读器时，可以利用 `PDFViewerApplication.pdfDocument.getData()` 提取 PDF 数据：

```javascript
(async () => {
  const iframe = document.querySelector('iframe');
  const win = iframe.contentWindow;
  const app = win.PDFViewerApplication;
  const doc = app.pdfDocument;
  const data = await doc.getData();
  const blob = new Blob([data], {type: 'application/pdf'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = '文件名.pdf';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
})();
```

## 站点案例

具体站点的工作流单独成文，按需查阅：

- [references/smartedu-pdf-download.md](references/smartedu-pdf-download.md) — 国家中小学智慧教育平台（basic.smartedu.cn）受保护 PDF 的提取
- [references/yuketang-post-comment.md](references/yuketang-post-comment.md) — 雨课堂（yuketang.cn）论坛发评论流程
