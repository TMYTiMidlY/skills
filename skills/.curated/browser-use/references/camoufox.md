---
description: Camoufox 的源码架构、PyPI 分发关系、运行依赖、环境形态、Python API 与命令行入口
---

# Camoufox

Camoufox 是带指纹兼容改造的 Firefox。Python 层封装 Playwright 的同步、异步 Firefox API，生成启动配置并管理可并存的浏览器 release；浏览器补丁和 Juggler 改动则位于同一源码树的底层目录。

源码 tag、Python 包和浏览器二进制使用不同版本号。诊断前先分清这三个对象，避免把“升级了 PyPI 包”误当成“浏览器 release 也已经切换”。

## <a id="package-channels"></a>包与发布通道

> 核验快照（2026-08-26）：
>
> | 对象 | 当前核验版本 | 与源码的关系 |
> |---|---|---|
> | 官方源码与浏览器 release | [`v152.0.4-beta.29`](https://github.com/daijro/camoufox/tree/v152.0.4-beta.29) | 2026-08-20 的架构基线；tag 中的 `pythonlib/pyproject.toml` 声明 `camoufox==0.5.5` |
> | PyPI `camoufox` | [`0.5.5`](https://pypi.org/project/camoufox/0.5.5/) | 2026-08-18 发布；sdist 的 `camoufox/` 与 2026-08-12 的官方 commit [`cd83f7f`](https://github.com/daijro/camoufox/tree/cd83f7fd2fdf631dfde0c7eb53bd3d30f102ec4a/pythonlib/camoufox) 逐文件一致 |
> | PyPI `cloverlabs-camoufox` | [`0.6.0`](https://pypi.org/project/cloverlabs-camoufox/0.6.0/) | 2026-05-13 发布；sdist 的 `camoufox/` 与同日的 CloverLabs commit [`2848aa1`](https://github.com/CloverLabsAI/camoufox/tree/2848aa19fe4fdc011445c62039de1cef79791275/pythonlib/camoufox) 逐文件一致，构建时使用独立的包名和版本元数据 |
>
> 以上对应关系用两个 PyPI sdist 与完整 clone 逐文件比较。PyPI `camoufox==0.5.5` 保存了 `cd83f7f` 的 Python 包快照；随后形成的官方 tag 又合入了显示环境、启动参数和服务端修复。版本号大小不能跨分发比较新旧。

两个 PyPI 分发都提供 `from camoufox...` 和 `camoufox` CLI，但各自维护独立的版本序列。阅读和选择时以分发名、源码 commit、发布日期及所需能力为完整坐标；需要并行对照时放在不同隔离环境，避免同名模块互相覆盖。

Python CLI 从 [`repos.yml`](https://github.com/daijro/camoufox/blob/v152.0.4-beta.29/pythonlib/camoufox/repos.yml#L1-L39) 读取浏览器仓库和兼容范围，以 `official/stable`、`official/prerelease` 或固定版本选择浏览器。浏览器 tag 与 Python 包版本因此没有一一同号关系。

## <a id="install-browser"></a>安装与浏览器文件

Camoufox 的 Python 分发不包含 Firefox 二进制。先在隔离环境提供包，再用同一个分发的 CLI 获取浏览器：

```bash
uvx --from "camoufox[geoip]" camoufox version
uvx --from "camoufox[geoip]" camoufox set official/stable
uvx --from "camoufox[geoip]" camoufox fetch
```

`geoip` extra 只在需要根据出口 IP 对齐经纬度、时区和 locale 时使用。浏览器安装目录由 `platformdirs.user_cache_dir("camoufox")` 解析，不应在文档里猜固定路径；用 `camoufox path` 和 `camoufox version` 查看本机实际状态。[源码](https://github.com/daijro/camoufox/blob/v152.0.4-beta.29/pythonlib/camoufox/pkgman.py#L55-L77)

### CLI 命令

包管理 CLI 由 [`pythonlib/camoufox/__main__.py`](https://github.com/daijro/camoufox/blob/v152.0.4-beta.29/pythonlib/camoufox/__main__.py#L218-L255) 定义：

| 命令 | 作用 |
|---|---|
| `sync` | 同步远端可用 release 清单 |
| `set` / `active` | 选择、固定并查看活动 channel 或版本 |
| `fetch` | 下载活动版本或指定版本 |
| `list` | 查看已安装或可用版本 |
| `version` / `path` | 查看包、浏览器、GeoIP 和存储状态 |
| `remove` | 删除选择的浏览器数据；执行前先核对目标 |
| `test` / `server` / `gui` | 调试浏览器、启动 Playwright server 或管理界面 |

## <a id="runtime-layers"></a>运行依赖

Camoufox 能否启动取决于三层彼此独立的内容：

1. **Python 分发**：提供 `camoufox` API、CLI、指纹生成和版本管理。
2. **浏览器二进制**：由 `camoufox fetch` 下载，活动版本记录在用户缓存中。
3. **操作系统运行库**：Firefox 启动所需的 GTK、X11、音频等动态库，不在 PyPI wheel 内。

包能 import 只能证明第一层可用；`CamoufoxNotInstalled` 指向第二层；`libgtk-3.so.0`、`libasound.so.2` 或 `XPCOMGlueLoad` 一类错误指向第三层。先按报错和 `ldd` 的实际缺项补库，不把某台机器的依赖清单当成所有发行版的固定答案。

在 Linux 上，Camoufox 启动前会检查 `~/.camoufox` 目录是否存在。若 HOME 已经只读且该目录不存在，启动会失败；应先创建目录，再收紧 HOME 权限。[源码](https://github.com/daijro/camoufox/blob/v152.0.4-beta.29/pythonlib/camoufox/pkgman.py#L82-L114)

## <a id="python-environments"></a>Python 临时环境

一次性脚本可直接让 uv 注入依赖，浏览器二进制继续复用用户缓存：

```bash
uv run --with "camoufox[geoip]" script.py
uv run --with "cloverlabs-camoufox[geoip]" script.py
```

两条命令应分别运行，不在同一个环境同时安装两个分发。需要固定依赖时，把选定的一个包写入项目环境；管理浏览器 channel 则用同一环境里的 `camoufox sync/set/fetch`。

## <a id="user-system-libs"></a>无管理员权限的系统库

没有 sudo 时，可用 pixi 提供 Firefox 所需的用户态动态库，再让启动命令通过 `LD_LIBRARY_PATH` 看到它们。关键是区分“Python 包环境”和“系统库环境”：uv 负责前者，pixi/conda 负责后者。

### 全局用户环境

共享环境适合多份零散脚本复用同一套 GTK/ALSA 库。用一个专用 pixi env 保存系统库；运行前通过 Camoufox API 找到当前活动浏览器目录，再把两个 `lib` 来源加入动态库搜索路径：

```bash
pixi global install --environment camoufox-libs gtk3 alsa-lib

pixi_root="${PIXI_HOME:-$HOME/.pixi}"
browser_dir=$(uv run --with "camoufox[geoip]" python -c \
  'from pathlib import Path; from camoufox.pkgman import launch_path; print(Path(launch_path()).parent)')
LD_LIBRARY_PATH="$pixi_root/envs/camoufox-libs/lib:$browser_dir" \
  uv run --with "camoufox[geoip]" script.py
```

> `pixi global install` 可能顺带暴露依赖包提供的命令；需要清理时先用 `pixi global list --json` 核对名称，再用 `pixi global expose remove --environment camoufox-libs <name>` 移除暴露项。环境里的动态库不会因此删除。

### 临时环境

一次性任务可以用 `pixi exec` 创建临时系统库环境，同时把 `$CONDA_PREFIX/lib` 传给浏览器进程。浏览器目录作为位置参数传入内部 shell，避免依赖 cache glob：

```bash
browser_dir=$(uv run --with "camoufox[geoip]" python -c \
  'from pathlib import Path; from camoufox.pkgman import launch_path; print(Path(launch_path()).parent)')
pixi exec -s gtk3 -s alsa-lib -- bash -c \
  'LD_LIBRARY_PATH="$CONDA_PREFIX/lib:$1" uv run --with "camoufox[geoip]" script.py' \
  bash "$browser_dir"
```

### 项目环境

长期项目可把 Python、GTK/ALSA 和选定的 Camoufox PyPI 分发放进同一个 pixi workspace，并在 activation 环境中声明浏览器动态库路径。先创建项目：

```bash
pixi init camoufox-runner
cd camoufox-runner
```

保留完整 `pixi.toml`，其中 `<camoufox-browser-dir>` 要替换为当前活动浏览器的实际目录：

```toml
[workspace]
channels = ["conda-forge"]
platforms = ["linux-64"]

[dependencies]
python = "3.12.*"
gtk3 = "*"
alsa-lib = "*"

[pypi-dependencies]
camoufox = { version = "*", extras = ["geoip"] }

[activation.env]
LD_LIBRARY_PATH = "$CONDA_PREFIX/lib:<camoufox-browser-dir>"
```

安装并下载浏览器后，用同一项目环境打印要填入配置的目录：

```bash
pixi install
pixi run camoufox set official/stable
pixi run camoufox fetch
pixi run python -c \
  'from pathlib import Path; from camoufox.pkgman import launch_path; print(Path(launch_path()).parent)'
```

替换占位符后，`pixi run python script.py` 会自动展开 `$CONDA_PREFIX` 并继承完整的动态库路径。若项目选择 CloverLabs 分发，只替换 `[pypi-dependencies]` 中的包名，不要同时安装两个分发。

### 环境形态比较

| 环境形态 | 状态位置 | 适用工作 |
|---|---|---|
| 全局用户环境 | 用户级共享缓存 | 多个脚本复用系统库 |
| 临时环境 | pixi/uv 缓存 | 一次性调查，不在项目落配置 |
| 项目环境 | 项目配置与锁文件 | 长期运行、CI 或团队复现 |

## <a id="python-api"></a>Python API 与指纹

同步入口继续使用 Playwright 的页面模型：

```python
from camoufox.sync_api import Camoufox

with Camoufox(headless=True) as browser:
    page = browser.new_page()
    page.goto("https://example.com")
```

`AsyncCamoufox` 提供等价异步入口。未指定 `headless` 时，Camoufox 以有头模式启动；Linux 上 `headless="virtual"` 使用 Xvfb，`headless=True` 使用 Firefox 无头模式。[启动源码](https://github.com/daijro/camoufox/blob/v152.0.4-beta.29/pythonlib/camoufox/sync_api.py#L82-L127) [参数源码](https://github.com/daijro/camoufox/blob/v152.0.4-beta.29/pythonlib/camoufox/utils.py#L466-L605)

常用参数包括 `os`、`geoip`、`proxy`、`locale`、`humanize`、`screen`、`window`、`fingerprint`、`fingerprint_preset`、`addons`、`block_webrtc` 和 `browser`。默认由 BrowserForge 生成指纹，也可选择随包分发的真实指纹预设。

```python
with Camoufox(fingerprint_preset=True, os="macos") as browser:
    page = browser.new_page()
```

`fingerprint_preset=True` 随机选择随包分发的预设；传入具体 dict 可以固定一个预设。

浏览器核心改动在 Firefox/C++/Juggler 层，减少普通 JS 注入留下的痕迹。Python 接口还提供 `NewContext` / `AsyncNewContext`，其中按 context 的部分覆盖通过短生命周期 init script 应用。分析可检测性时，应分别考察浏览器底层改动和 context 初始化脚本这两条实现路径。[context 源码](https://github.com/daijro/camoufox/blob/v152.0.4-beta.29/pythonlib/camoufox/sync_api.py#L153-L180)

## <a id="agent-cli"></a>Agent CLI

不想写 Python 脚本时，可以在 Camoufox 上再加一层命令式操作。下面两个 CLI 都是独立第三方项目，不是 Camoufox 官方组件；命令面应按各自固定源码核对：

| 项目 | 操作模型 | 侧重点 |
|---|---|---|
| [`camoufox-browser`](https://github.com/rlgrpe/camoufox-browser-cli/tree/05325f2c01549d049d87c59677b61a29dcadef5b) | 语义 ref、后台 daemon，可选 MCP | CLI 与 MCP 共用操作层 |
| [`camoufox-cli`](https://github.com/Bin-Huang/camoufox-cli/tree/4d86686d8034e93910473671ee34453dee173cb2) | `@e1` ref、命名会话、持久 profile | 固定身份、多会话和配置文件 |

`camoufox-browser` 支持 Linux 和 macOS，以独立 uv tool 环境安装；需要 MCP 时一起安装 optional extra：

```bash
uv tool install "camoufox-browser[mcp]"
camoufox-browser install
camoufox-browser open https://example.com
camoufox-browser snapshot
camoufox-browser click 'button:Sign in'
camoufox-browser close
```

> 依赖核验：`camoufox-browser` 当前声明 `cloverlabs-camoufox[geoip]>=0.5.5`，见[固定源码](https://github.com/rlgrpe/camoufox-browser-cli/blob/05325f2c01549d049d87c59677b61a29dcadef5b/pyproject.toml#L24-L31)。它自带的 skill 可用 `npx skills add https://github.com/rlgrpe/camoufox-browser-cli --skill camoufox` 安装。

`camoufox-cli` 同时提供 npm 与 Python 分发；下面使用 npm 入口，安装浏览器后按 `@eN` ref 操作：

```bash
npm install -g camoufox-cli
camoufox-cli install
camoufox-cli open https://example.com
camoufox-cli snapshot -i
camoufox-cli click @e1
camoufox-cli close
```

> 依赖核验：`camoufox-cli` 当前固定 `camoufox[geoip]==0.4.11` 与 `playwright==1.52.0`，见[固定源码](https://github.com/Bin-Huang/camoufox-cli/blob/4d86686d8034e93910473671ee34453dee173cb2/pyproject.toml#L17-L25)。它不会自动跟随官方分发更新；需要其配套 skill 时运行 `npx skills add Bin-Huang/camoufox-cli`。

若当前环境已经提供 Playwright CLI/MCP，只有确实需要 Camoufox 浏览器身份时才多套这一层；页面操作思想仍是快照、ref、DOM 和网络内省。

## <a id="access-boundaries"></a>反爬兼容性与访问边界

Camoufox 改善的是浏览器指纹和自动化一致性，不承诺对所有站点、IP、代理、账号或版本稳定通过。[上游 README](https://github.com/daijro/camoufox/blob/v152.0.4-beta.29/README.md#L14) 明确标注项目仍在开发中；升级浏览器 release 也可能同时带来兼容修复和新回归。

验证码、交互验证和登录挑战属于页面状态。Playwright 或 Camoufox 可以继续读取页面、保留会话并交给人完成必要步骤；出现验证码时先沿访问状态排查，locator 则继续用于页面元素定位。站点已有稳定公开接口或可复现的 HTTP 请求时，直接 HTTP 与浏览器可以并用。

代理结果由出口信誉、GeoIP、DNS、WebRTC、locale 和会话历史共同决定。一次站点通过记录的是当时浏览器版本、出口和请求路径这组条件的表现；调试时继续记录 headed/headless 与失败响应，再据此调整对应层。
