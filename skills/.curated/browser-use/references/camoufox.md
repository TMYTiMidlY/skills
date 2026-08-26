---
description: Camoufox v152.0.4-beta.29 的源码架构、PyPI 分发关系、运行依赖、环境形态、Python API 与命令行入口
---

# Camoufox

Camoufox 是带指纹兼容改造的 Firefox。当前文档以官方完整源码 tag [`v152.0.4-beta.29`](https://github.com/daijro/camoufox/tree/v152.0.4-beta.29)（commit `03b9c81`）为基线：Python 层封装 Playwright 的同步、异步 Firefox API，生成启动配置并管理可并存的浏览器 release；浏览器补丁和 Juggler 改动则位于同一源码树的底层目录。

源码 tag、Python 包和浏览器二进制使用不同版本号。诊断前先分清这三个对象，避免把“升级了 PyPI 包”误当成“浏览器 release 也已经切换”。

## <a id="package-channels"></a>包与发布通道

| 对象 | 当前核验版本 | 与源码的关系 |
|---|---|---|
| 官方源码与浏览器 release | [`v152.0.4-beta.29`](https://github.com/daijro/camoufox/tree/v152.0.4-beta.29) | 2026-08-20 的架构基线；tag 中的 `pythonlib/pyproject.toml` 声明 `camoufox==0.5.5` |
| PyPI `camoufox` | [`0.5.5`](https://pypi.org/project/camoufox/0.5.5/) | 2026-08-18 发布；sdist 的 `camoufox/` 与 2026-08-12 的官方 commit [`cd83f7f`](https://github.com/daijro/camoufox/tree/cd83f7fd2fdf631dfde0c7eb53bd3d30f102ec4a/pythonlib/camoufox) 逐文件一致 |
| PyPI `cloverlabs-camoufox` | [`0.6.0`](https://pypi.org/project/cloverlabs-camoufox/0.6.0/) | 2026-05-13 发布；sdist 的 `camoufox/` 与同日的 CloverLabs commit [`2848aa1`](https://github.com/CloverLabsAI/camoufox/tree/2848aa19fe4fdc011445c62039de1cef79791275/pythonlib/camoufox) 逐文件一致，构建时使用独立的包名和版本元数据 |

> 以上对应关系于 2026-08-26 用两个 PyPI sdist 与完整 clone 逐文件比较。PyPI `camoufox==0.5.5` 保存了 `cd83f7f` 的 Python 包快照；随后形成的官方 tag 又合入了显示环境、启动参数和服务端修复，代表更新的源码检查点。

两个 PyPI 分发都提供 `from camoufox...` 和 `camoufox` CLI。`cloverlabs-camoufox==0.6.0` 对应 CloverLabs 在5月形成的源码快照，`camoufox==0.5.5` 对应官方仓库在8月形成的源码快照；阅读和选择时以分发名、源码 commit、发布日期及所需能力为完整坐标。需要并行对照时放在不同隔离环境，避免同名模块互相覆盖。

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

最新 tag 的包管理 CLI 由 [`pythonlib/camoufox/__main__.py`](https://github.com/daijro/camoufox/blob/v152.0.4-beta.29/pythonlib/camoufox/__main__.py#L218-L255) 定义：

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

最新 tag 还会在 Linux 启动前确认 Firefox 所需的 `~/.camoufox` profile 目录存在；只读 HOME 应在收紧权限前准备该目录。[源码](https://github.com/daijro/camoufox/blob/v152.0.4-beta.29/pythonlib/camoufox/pkgman.py#L82-L114)

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

共享环境适合多份零散脚本复用同一套 GTK/ALSA 库。用一个专用 pixi env 保存系统库，并在运行时把其 `lib` 目录与实际 Camoufox 浏览器目录加入动态库搜索路径。不要把这两个位置写死进 skill。

### 临时环境

一次性任务可以用 `pixi exec` 创建临时系统库环境，同时把 `$CONDA_PREFIX/lib` 传给浏览器进程：

```bash
pixi exec -s gtk3 -s alsa-lib -- bash -lc \
  'LD_LIBRARY_PATH="$CONDA_PREFIX/lib:<camoufox-browser-dir>" <browser-command>'
```

### 项目环境

长期项目可把 Python、GTK/ALSA 和选定的 Camoufox PyPI 分发放进同一个 pixi workspace，并在 activation 环境中声明浏览器动态库路径。这样运行入口固定、便于复现，但会在项目中保留环境与锁文件。

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

`AsyncCamoufox` 提供等价异步入口。最新 tag 默认 `headless=False`；Linux 上 `headless="virtual"` 使用 Xvfb，普通 `headless=True` 使用 Firefox 无头模式。[启动源码](https://github.com/daijro/camoufox/blob/v152.0.4-beta.29/pythonlib/camoufox/sync_api.py#L82-L127) [参数源码](https://github.com/daijro/camoufox/blob/v152.0.4-beta.29/pythonlib/camoufox/utils.py#L466-L605)

常用参数包括 `os`、`geoip`、`proxy`、`locale`、`humanize`、`screen`、`window`、`fingerprint`、`fingerprint_preset`、`addons`、`block_webrtc` 和 `browser`。默认由 BrowserForge 生成指纹，也可选择随包分发的真实指纹预设。

浏览器核心改动在 Firefox/C++/Juggler 层，减少普通 JS 注入留下的痕迹；最新稳定接口同时提供 `NewContext` / `AsyncNewContext`，其中按 context 的部分覆盖通过短生命周期 init script 应用。分析可检测性时，应分别考察浏览器底层改动和 context 初始化脚本这两条实现路径。[context 源码](https://github.com/daijro/camoufox/blob/v152.0.4-beta.29/pythonlib/camoufox/sync_api.py#L153-L180)

## <a id="agent-cli"></a>Agent CLI

不想写 Python 脚本时，可以在 Camoufox 上再加一层命令式操作。这些是独立第三方项目，不属于官方 tag，命令面应按各自固定源码核对：

| 项目 | 操作模型 | 侧重点 |
|---|---|---|
| [`camoufox-browser`](https://github.com/rlgrpe/camoufox-browser-cli/tree/05325f2c01549d049d87c59677b61a29dcadef5b) | 语义 ref、后台 daemon，可选 MCP | CLI 与 MCP 共用操作层 |
| [`camoufox-cli`](https://github.com/Bin-Huang/camoufox-cli/tree/4d86686d8034e93910473671ee34453dee173cb2) | `@e1` ref、命名会话、持久 profile | 固定身份、多会话和配置文件 |

若当前环境已经提供 Playwright CLI/MCP，只有确实需要 Camoufox 浏览器身份时才多套这一层；页面操作思想仍是快照、ref、DOM 和网络内省。

## <a id="access-boundaries"></a>反爬兼容性与访问边界

Camoufox 改善的是浏览器指纹和自动化一致性，不承诺对所有站点、IP、代理、账号或版本稳定通过。官方 tag 自身仍标注项目处于开发中；升级浏览器 release 也可能同时带来兼容修复和新回归。

验证码、交互验证和登录挑战属于页面状态。Playwright 或 Camoufox 可以继续读取页面、保留会话并交给人完成必要步骤；出现验证码时先沿访问状态排查，locator 则继续用于页面元素定位。站点已有稳定公开接口或可复现的 HTTP 请求时，直接 HTTP 与浏览器可以并用。

代理结果由出口信誉、GeoIP、DNS、WebRTC、locale 和会话历史共同决定。一次站点通过记录的是当时浏览器版本、出口和请求路径这组条件的表现；调试时继续记录 headed/headless 与失败响应，再据此调整对应层。
