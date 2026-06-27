---
description: Camoufox 详解 —— 反指纹 Firefox、包/通道选择、三层依赖与无 sudo 补库、指纹注入、两个 agent CLI
---

# Camoufox 详解

Camoufox = 改过的 Firefox + **Playwright 兼容的 Python API**。页面操作仍按 Playwright 模型写（`page.goto()` / `page.click()` / `page.screenshot()`）——你只需要改"浏览器初始化"那一步。它在 **C++ 层**注入指纹（navigator / 屏幕 / WebGL / 字体 / 语音 / WebRTC IP / GeoIP / 时区 / locale），JS 检测不到；底层用 [BrowserForge](https://github.com/daijro/browserforge) 按真实流量统计分布生成指纹。

适用：目标站有反爬 / 指纹检测，需要隐身 Firefox、指纹注入/轮换、按代理 IP 伪造 GeoIP。

## 包 / 通道：`camoufox` vs `cloverlabs-camoufox`

| | `camoufox`（官方稳定）| `cloverlabs-camoufox`（活跃 alpha）|
|---|---|---|
| PyPI 版本（实测）| 0.4.11 | 0.6.0 |
| 仓库 | github.com/daijro/camoufox | github.com/CloverLabsAI/camoufox |
| 定位 | 稳定，**发布有延迟** | **浏览器开发主线**，每次 release 都更 |
| 额外能力 | 基础指纹注入 | per-context 指纹 + 硬件伪造 + `fingerprint_preset` 真实指纹预设 |
| 何时用 | 求稳 | 要新特性 / 最新 Firefox 补丁 / 真实指纹预设 |

- 两个包**共用 `camoufox` 这个 import 和 CLI 命名空间**（`from camoufox.sync_api import Camoufox`、`python -m camoufox …` 两边都成立）。**装在各自的 venv 里，别混**（官方明示）。
- 官方 README 原话："Browser development is active at CloverLabsAI/camoufox … To make use of the alpha Camoufox releases, use the `cloverlabs-camoufox` pip package."
- **Camoufox 是 Python-only，没有 npm 包，conda-forge 也没有**（实测 `pixi search camoufox` 查无）——第 1 层只能 `uv`/`pip` 装，pixi 装不了（例外见方案 C 的 `[pypi-dependencies]`）。

## 安装与浏览器获取

```bash
# 稳定
pip install -U "camoufox[geoip]"        # 或 uv：uv run --with "camoufox[geoip]" ...
# 活跃 alpha
pip install -U "cloverlabs-camoufox[geoip]"
```

`geoip` extra 可选但**用代理时强烈建议**：下一份数据集，按出口 IP 算经纬度/时区/国家/locale，避免代理露馅。

下载浏览器二进制（不在 PyPI wheel 里，从 GitHub release 拉，缓存在 `~/.cache/camoufox/browsers/...`）：

```bash
python3 -m camoufox fetch        # Linux/macOS
camoufox fetch                   # Windows
```

要最新预发布补丁（cloverlabs 推荐）：

```bash
python -m camoufox sync
python -m camoufox set official/prerelease
python -m camoufox fetch
```

无桌面的新 Linux 还要补 Firefox 系统依赖（有 sudo 时）：

```bash
sudo apt install -y libgtk-3-0 libx11-xcb1 libasound2      # Ubuntu/Debian
sudo pacman -S gtk3 libx11 libxcb cairo libasound alsa-lib  # Arch
```

无 sudo 见下文「补齐系统库」。

### CLI 命令表（两个包**相同**）

实测 daijro 与 cloverlabs 的 `__main__.py` 子命令集一致：

| 命令 | 作用 |
|---|---|
| `fetch` | 下载浏览器二进制 |
| `sync` | 同步可用版本/通道清单 |
| `set <specifier>` | 切换通道/版本（如 `official/prerelease`、`official/stable`）|
| `list` | 列已装版本 |
| `active` | 显示当前激活版本 |
| `path` | 打印浏览器可执行文件路径 |
| `remove` | 删除已下载文件 |
| `version` | 显示版本 |
| `server` | 启动 Playwright server |
| `test` | 打开 Playwright inspector |
| `gui` | Qt 版本/IP库/包管理前端 |

> ⚠️ **修正旧版 skill 的一个说法**：`sync` / `set` **不是 cloverlabs 专属**——daijro 的 `camoufox` 同样有。差别只在**发布节奏**：camoufox.com 上记录的官方 0.4.11 命令面较旧（fetch/path/remove/server/test/version），而 `sync`/`set`/`list`/`active` 等较新命令已在 `cloverlabs-camoufox` 0.6.0 发布、daijro 主线也已合入但 PyPI 发布滞后。

## Camoufox 的三层依赖（先建这个心智模型）

跑通 Camoufox 要同时凑齐三层，缺任一层都起不来，而且三层来源完全不同：

1. **Python 包 / CLI**（`camoufox[geoip]` 或 `cloverlabs-camoufox[geoip]`）—— 只在 PyPI，**conda-forge 没有**。这层只能 `uv`/`pip` 装，pixi 装不了。
2. **浏览器二进制**（改过的 Firefox）—— 不在 PyPI wheel 里，靠 `camoufox fetch` 从 GitHub release 下载，缓存在 `~/.cache/camoufox/browsers/...`。
3. **系统 GTK/X11/ALSA 共享库**（`libgtk-3.so.0`、`libasound.so.2` 等十几个 `.so`）—— OS 层的库，**不在任何 PyPI wheel 里**。有桌面的机器系统自带；纯 headless server / WSL 等缺这层，不补就挂在 `XPCOMGlueLoad`。

> **"既然都用 pixi 了，为什么还要 uv？"** —— pixi（`pixi exec` 或 global env）只能装 **conda 包**，可以补第 3 层系统库，但 camoufox 那个包只在 PyPI、conda-forge 没有，pixi 装不了，第 1 层只能交给 uv。**例外**：pixi **项目**支持 `[pypi-dependencies]`，能让 pixi 连 camoufox 一起包办、彻底不用 uv（见方案 C），代价是要建一个常驻项目目录；若要"临时、不留痕迹、任意仓库可跑"，就还得 pixi（补库）+ uv（装 camoufox）分工（方案 A/B）。

## 跑页面脚本：`uv run --with`

脚本里 `from camoufox.sync_api import Camoufox`，页面操作按 Playwright 模型写。**跑脚本**（不是 CLI 命令）用 `uv run --with` 注入第 1 层依赖——`uv run` **没有 `--from`**（`--from` 是 `uvx`/`uv tool run` 跑命令时才有的），脚本一律用 `--with`：

```bash
uv run --with "cloverlabs-camoufox[geoip]" script.py
```

管浏览器版本（第 2 层）才用 `uvx --from`（跑 CLI 命令）：

```bash
uvx --from "cloverlabs-camoufox[geoip]" camoufox sync
uvx --from "cloverlabs-camoufox[geoip]" camoufox set official/prerelease
uvx --from "cloverlabs-camoufox[geoip]" camoufox fetch
```

⚠️ 上面的 `uv run --with` 在**有桌面环境**的机器直接能跑；在无桌面库、无 sudo 的机器（headless server / WSL）会因缺第 3 层系统库挂掉，要先按下文补好再跑。

## 补齐系统库（无桌面 / 无 sudo 环境）

无桌面库、又没免密 sudo 的机器缺第 3 层，纯按上面的 `uv run --with` 跑会挂：

```text
libgtk-3.so.0: cannot open shared object file
Couldn't load XPCOM.
```

`uv` 只解决两层（Python 包/CLI、浏览器二进制），**不提供 OS 层的 `.so`**。无 sudo 时用 pixi 装一份用户态的库，再用 `LD_LIBRARY_PATH` 指过去。

实测确认的库清单（conda-forge 包名）：

- `gtk3`、`alsa-lib` 是**启动硬依赖**，缺任一启动即失败（连开 `about:blank` 都不行）。装 `gtk3` 会自动拖入它的传递依赖 gdk-pixbuf/cairo/pango/atk/xorg-libX*/libxcb，不用单独列。
- `nss` **不要装**：Camoufox 浏览器目录（`~/.cache/camoufox/browsers/.../`）自带整套 NSS（`libnss3.so`/`libssl3.so`/`libnspr4.so`…），HTTPS/TLS 走它自带的。实测去掉 pixi 的 nss 后真实 HTTPS 抓取仍 200，所以装它纯冗余——只装 `gtk3`+`alsa-lib` 即可。

补库三种装法，**默认用方案 A**；一次性/任意仓库临时跑用方案 B；长期固定项目要最省事用方案 C。

### 方案 A（默认）：全局库 env + uv（库一份全局共享，任意脚本复用）

`pixi global install <pkg>` 默认给每个包单独建一个**同名独立 env**。要把多个包塞进**同一个** env，用 `-e`/`--environment <envname>`：

```bash
# -e 指定共同 env 名，把库装进同一个 env；只装这两个，不装 nss（camoufox 自带）
pixi global install -e camoufox-libs gtk3 alsa-lib
```

这些库包会把 `gtk-launch`/`certutil`/`aserver` 等命令暴露到 `~/.pixi/bin`（纯当库源用不到，且可能与别的 env 撞名）。pixi 没有 `--no-expose` 开关，改在 manifest 里把该 env 的 `exposed` 清空再 sync：

```bash
# 编辑 ~/.pixi/manifests/pixi-global.toml，把 [envs.camoufox-libs] 一段改成 exposed = {}
pixi global sync     # 移除已暴露的命令；env 的 lib/*.so 原样保留
```

`exposed`（软链命令到 `~/.pixi/bin`）和 `LD_LIBRARY_PATH`（动态链接器找 `.so`）正交：清空 `exposed` 只砍 PATH 里的命令，`lib/*.so` 一个不少。

跑脚本时把 env 的 lib 目录 + Camoufox 二进制目录都加进 `LD_LIBRARY_PATH`：

```bash
CFDIR=$(ls -d ~/.cache/camoufox/browsers/official/*/ | tail -1)
export LD_LIBRARY_PATH="$HOME/.pixi/envs/camoufox-libs/lib:$CFDIR"
uv run --with "cloverlabs-camoufox[geoip]" script.py
```

### 方案 B：`pixi exec` 临时跑（不建项目、任意仓库、不留痕迹）

不想预装全局 env 时用 `pixi exec`——它是 pixi 的 uvx 式临时环境：按 spec 把 conda 包装进缓存 env、跑一次性命令，**不在当前目录留任何 `.pixi`/`pixi.toml`**（实测在 git 仓库里跑完 `git status` 无新增）。

临时 env 落在 `~/.cache/rattler/cache/cached-envs-v0/<hash>/`（rattler 是 pixi 底层那套 Rust 写的 conda 包管理库），既不污染当前仓库、又能按"包集合 hash"复用。清理用 `pixi clean cache --exec`。

> 在"不留痕迹"目标下**不要**改用 `pixi run --manifest-path`/`pixi init` + toml：那要 manifest 目录、会落 `.pixi/` env，等于建常驻项目目录（那是方案 C）。`pixi exec` 才是 `uv run --with` 那种"任意位置临时跑"的等价物。

`pixi exec` 只接 conda matchspec（不接 PyPI），所以分工：第 3 层走 `pixi exec -s`，第 1 层 camoufox 包走 `uv run --with`，拼一条命令：

```bash
CFDIR=$(ls -d ~/.cache/camoufox/browsers/official/*/ | tail -1)
pixi exec -s gtk3 -s alsa-lib -- bash -c '
  export LD_LIBRARY_PATH="$CONDA_PREFIX/lib:'"$CFDIR"'"
  uv run --with "cloverlabs-camoufox[geoip]" script.py
'
```

`pixi exec` 把 `CONDA_PREFIX` 指向临时 env（`$CONDA_PREFIX/lib` 即 gtk3/alsa-lib 的 `.so`），`$CFDIR` 提供 Camoufox 自带的 NSS；`uv` 靠 PATH 继承可见。

### 方案 C：pixi 项目（建常驻项目目录，之后 `pixi run` 一条命令）

接受**建一个常驻项目目录**时这是最省事的：三层全塞进一个 pixi 项目，pixi 一手包办 camoufox 包 + 系统库 + LD path，**不用 uv、不用手动 export**。

```bash
pixi init camoufox-runner && cd camoufox-runner
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
# 末尾换成本机 camoufox 浏览器目录
LD_LIBRARY_PATH = "$CONDA_PREFIX/lib:/home/<you>/.cache/camoufox/browsers/official/<ver>"
```

```bash
pixi run python script.py    # 无手动 export、无 uv，pixi 全包办
```

省事关键两点：① pixi **项目**支持 `[pypi-dependencies]`，连第 1 层 camoufox 包都由 pixi 装进项目 env（实测落在 `.pixi/envs/default/.../site-packages/camoufox`，全程不经 uv）；② **裸 `pixi run` 并不会自动设 LD path**（pixi/conda 默认靠 RPATH，而 camoufox 那个独立 Firefox 二进制没有指向 env 的 RPATH），所以 `[activation.env]` 这行正是"不用手动 export"的来源，少了它照样挂 `libgtk`。第 2 层二进制仍要先 `camoufox fetch` 下载一次（缓存全机共享）。

### 三个方案怎么选

- **方案 A（全局库 env + uv）【默认】**：预装一份 `camoufox-libs` 全局 env、库全局共享；跑脚本先 `export LD_LIBRARY_PATH` 再 `uv run --with`。适合多个零散脚本复用同一份库。
- **方案 B（`pixi exec` 临时跑）**：零预装、一条命令临时拉起、当前目录不留痕迹；首次现装 conda 包。适合任意仓库一次性临时跑。
- **方案 C（pixi 项目）**：建常驻项目目录；之后 `pixi run python script.py` 一条命令，pixi 把三层全包了。代价是多一个含 `.pixi/` 的常驻目录。适合长期固定项目。

三个方案都已实测跑通真实 HTTPS（`example.com` 200）；浏览器缓存（`~/.cache/camoufox`）三者共享。

## Python 脚本用法与指纹

页面操作按 Playwright 写，只改浏览器初始化：

```python
from camoufox.sync_api import Camoufox          # 同步
with Camoufox() as browser:
    page = browser.new_page()
    page.goto("https://example.com")
```

```python
from camoufox.async_api import AsyncCamoufox    # 异步
async with AsyncCamoufox() as browser:
    page = await browser.new_page()
    await page.goto("https://example.com")
```

常用初始化参数（实测 `launch_options` 签名）：`headless`、`os`（`"windows"`/`"macos"`/`"linux"` 或列表，随机挑）、`geoip`（`True` 或指定）、`proxy`（`{"server","username","password"}`）、`humanize`（拟人鼠标移动，`True` 或秒数）、`locale`、`block_images`、`block_webrtc`、`addons`、`screen`、`window`、`config`（手动覆盖指纹属性）、`fingerprint`、`enable_cache`、`i_know_what_im_doing`。未指定的指纹属性由 BrowserForge 自动补全。

真实指纹预设（cloverlabs，v149+ 二进制更稳）：

```python
with Camoufox(fingerprint_preset=True, os="macos") as browser:
    ...
```

按二进制版本自动选预设包（Firefox ≥149 用 `fingerprint-presets-v150.json`，312 个预设覆盖 v149–v152）；UA 自动改写匹配当前二进制。传 dict 可钉死某个预设。

## 两个 camoufox agent CLI（要 shell 命令式驱动时）

不想写 Python 脚本、想像 playwright-cli 那样用 shell 子命令驱动 Camoufox 时，有两个第三方项目，niche 不同：

| | `camoufox-browser`（rlgrpe）| `camoufox-cli`（Bin-Huang）|
|---|---|---|
| PyPI/npm | `camoufox-browser`（v0.1.1）| `camoufox-cli`（pip **和** npm 都有）|
| 装法 | `uv tool install camoufox-browser` / `pip` / `pipx`；MCP extra `camoufox-browser[mcp]` | `npm i -g camoufox-cli` 或 `pipx install camoufox-cli`；`camoufox-cli install [--with-deps]` 装浏览器/系统库 |
| ref 风格 | 语义标签 `button:Sign in`、`textbox:Email` | `@e1`（playwright-cli 风格加 `@`）|
| 持久身份 | 基础（daemon + `--persistent`）| **强项**：冻结指纹/OS/canvas seed、`~/.camoufox-cli/config.json` 配置、`--persistent <path>` 多身份并行、按代理 IP 重算 GeoIP |
| MCP | 有（`camoufox-mcp`，`uvx --from "camoufox-browser[mcp]" camoufox-mcp`）| 无（纯 CLI + skill）|
| skill | `npx skills add https://github.com/rlgrpe/camoufox-browser-cli --skill camoufox` | `npx skills add Bin-Huang/camoufox-cli` |
| 平台 | Linux / macOS | 跨平台 |
| 架构 | 共享操作层 + 后台 daemon（仿 vercel-labs/agent-browser）| CLI ─Unix socket→ Python daemon ─Playwright→ Camoufox，daemon 闲置 30min 自停 |
| 依赖 | `cloverlabs-camoufox[geoip]>=0.5.5` | Camoufox |

选择：
- 要**最强的持久指纹身份 / 多身份并行 / 配置文件 / 代理轮换** → `camoufox-cli`（Bin-Huang）。
- 要**自带 MCP**、或更贴近 CloverLabsAI 官方组织 → `camoufox-browser`（rlgrpe）。
- 两者都是年轻第三方项目，按实验工具看待稳定性；本机 `~/projects/readonly-repos` 已各 clone 一份可查源码。

`camoufox-browser` 示例：

```bash
camoufox-browser open https://example.com
camoufox-browser snapshot
camoufox-browser click 'button:Sign in'
camoufox-browser fill 'textbox:Email' me@example.com --submit
camoufox-browser screenshot --output page.png
camoufox-browser close
```

`camoufox-cli` 示例：

```bash
camoufox-cli open https://example.com
camoufox-cli snapshot -i                 # 只列交互元素，带 [ref=e1]
camoufox-cli click @e1
camoufox-cli --session work --persistent ~/.camoufox-cli/profiles/alice open https://...
camoufox-cli close
```

## 反爬实测记录

普通 `urllib` 访问 PyPI 项目页遇到 `Client Challenge`；直接调用裸 Camoufox binary 截图也得到挑战/空白页；用 Python wrapper 启动 Camoufox headless 后，多次访问 `https://pypi.org/project/camoufox/` 和 `https://pypi.org/project/cloverlabs-camoufox/` 成功拿到标题并保存截图。这说明在当时环境下可以通过，但**不要承诺对所有站点、IP 和版本稳定绕过**——反爬是军备竞赛，配合住宅轮换代理（`proxy` + `geoip`）成功率更高。
