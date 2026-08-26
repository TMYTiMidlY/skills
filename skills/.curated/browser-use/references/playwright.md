---
description: Playwright 的运行架构、安装入口、CLI/MCP/库脚本差异，以及无头模式、浏览器选择和受限环境诊断
---

# Playwright 详解

涵盖：架构心智模型、uv vs npm 安装差异与推荐、三种入口（CLI / MCP / 库脚本）、CLI vs MCP 该用哪个。

## 架构：为什么说"Playwright 本体是 Node"

Playwright 的浏览器由一个 **Node driver**（`playwright-core` npm 包）驱动；各语言绑定（Python / .NET / Java）都只是这个 driver 的 **RPC 客户端**，本身不直接开浏览器。

从 Playwright Python 包的构建方式可以看到：

- [`pyproject.toml`](https://github.com/microsoft/playwright-python/blob/154f67ced51ada646b0fcf8574897d96c9712aa3/pyproject.toml#L39-L40) 以 `playwright.__main__:main` 暴露 `playwright` 命令。
- 仓库根的 `NODE_VERSION`、`DRIVER_VERSION` 与 [`setup.py`](https://github.com/microsoft/playwright-python/blob/154f67ced51ada646b0fcf8574897d96c9712aa3/setup.py#L25-L32) 共同定义随 wheel 打包的 Node 运行时和 `playwright-core` driver；具体版本随发布变化。
- 即：**Python wheel 里自带一份 Node.js 运行时 + playwright-core driver**，解包进 `playwright/driver/`。Python 调 `page.click()` 实际是把请求发给这个内置 Node driver。

> 用 Python 还是 Node，主要决定脚本与命令入口；Python wheel 内仍携带 Node driver，并不等于浏览器驱动脱离了 Node。

## 安装：uv（Python）vs npm（Node）

| | npm / Node（一等公民）| uv / Python（语言绑定）|
|---|---|---|
| 装库 | `npm i -D playwright`（库）<br>`npm init playwright@latest`（测试脚手架，注意是 **init** 不是 install）| `uv add playwright`（项目）<br>`uv run --with playwright script.py`（临时）|
| 装浏览器 | `npx playwright install chromium` | `playwright install chromium`（wheel 自带 CLI）<br>或 `uv run --with playwright playwright install chromium` |
| Linux 系统依赖 | `npx playwright install-deps`（**需 root**）| `playwright install-deps`（**需 root**）|
| 你能拿到 | 库 + `playwright` CLI + **Test Runner**(`@playwright/test`) + **agent CLI**(`@playwright/cli`) + **MCP**(`@playwright/mcp`) | 库 + `playwright` 管理 CLI（`install` / `install-deps` / `codegen` / `open` / `screenshot` / `pdf` …）|
| 你拿不到 | —— | **Test Runner、agent CLI、MCP 全都没有** |

**关键差异**：`@playwright/test`、`@playwright/cli`、`@playwright/mcp` 是三个独立 npm 包；`pip`/`uv` 安装的 `playwright` 提供 Python 库和浏览器管理 CLI，不包含这些 Node 入口。具体版本用各自的 `--version` 或包管理器查询，不在文档中维护“最新版”数字。

### 无 sudo 机器的系统依赖

`install-deps` 要 root。无 sudo 的 headless / WSL 机器装不了系统库，浏览器起不来（缺 `libgtk` 等）。两条路：

- 用官方 Docker 镜像 `mcr.microsoft.com/playwright`（自带浏览器 + 系统库），脚本/MCP 都能跑进去。
- 或用与 Camoufox 相同的 pixi 用户态补库思路（`pixi` 提供 GTK/ALSA 等库，再设置动态库搜索路径），见 [Camoufox 的无管理员权限环境](camoufox.md#user-system-libs)。同样的分层诊断也适用于 Playwright 浏览器。

### 安装方式推荐

- **你（coding agent）要驱动浏览器做事** → 走 **npm**，用 `@playwright/cli`（见下「入口 1」）。这是官方对 coding agent 的首选，token 最省。
- **要交付可复现的 Python 自动化脚本**，或要接 **Camoufox**（Python-only，见 camoufox.md） → 走 **uv**：`uv run --with playwright script.py`，依赖写进脚本 PEP 723 元数据或 `uv add`。
- **要跑 Playwright 测试套件**（`@playwright/test`，含 fixtures / web-first 断言 / trace viewer） → 只能走 **npm**（`npm init playwright@latest`）。

## 入口 1：Playwright CLI（`@playwright/cli`）—— coding agent 默认

`@playwright/cli` 提供 `playwright-cli` 命令，把浏览器操作做成一串简洁子命令；配套一个官方 **skill** 教 agent 怎么用。这是 Microsoft 对 coding agent 的明确首选。

### 安装

```bash
# 全局
npm install -g @playwright/cli@latest
playwright-cli --help

# 或免装、用本地版本（探测 + 调用）
npx --no-install playwright-cli --version
```

把官方 skill 落进当前项目（让 agent 自动读到完整命令面）：

```bash
playwright-cli install --skills
```

> 这会安装一个 `playwright-cli` skill（含 SKILL.md + 十个 references：playwright-tests / request-mocking / running-code / session-management / spec-driven-testing / storage-state / test-generation / tracing / video-recording / element-attributes）。需要 Playwright 完整命令面时**优先装它、读它**，不要在本 skill 里重抄。

### 运行形态与诊断

Playwright CLI 默认无头运行，不会出现用户可见窗口；需要观察或人工接管时，在 `open` 上加 `--headed`。`show` 打开的监控面板同样属于可见界面。该行为可在 [`@playwright/cli` v0.1.18 README](https://github.com/microsoft/playwright-cli/blob/v0.1.18/README.md#L47-L79) 中核对。Playwright MCP 则默认有头，需显式使用 `--headless`；库脚本由 `headless` launch option 决定。

启动前不要假定某个浏览器一定存在。先看 `playwright-cli --help open`、配置文件和已安装浏览器；默认 channel 缺失时，显式选择现有的 Firefox、WebKit、Chrome 或 Edge，或安装所需浏览器。浏览器进程在受限沙箱内还可能需要额外运行权限。

CLI 的守护进程状态目录必须可写，浏览器二进制可能位于另一缓存。若把通用缓存改到临时目录，原有浏览器也可能随之“消失”；此时应分别确认守护进程缓存和浏览器安装路径，而不是反复重装。

页面取证不只依赖无障碍快照。快照为空或地图、canvas、虚拟列表等组件难以读取时，继续检查 DOM、隐藏表单、内嵌脚本、console 和网络请求。定位到稳定的公开请求后，可以同时用直接 HTTP 复现和解析；二者不是互斥方案。验证码、账号权限以及源站根本没有提供的数据，则不是增加点击或换 locator 能解决的问题。

### ref 快照模型（核心交互范式）

每条命令执行后，CLI 会回一份**无障碍快照**（accessibility snapshot），交互元素带 `eN` ref。用 ref 去点/填，比 CSS 选择器稳：

```bash
playwright-cli open https://example.com/login
playwright-cli snapshot                 # 拿到 e1 e2 e3 … refs
playwright-cli fill e1 "user@example.com"
playwright-cli fill e2 "secret" --submit # --submit = 填完按 Enter
playwright-cli click e3
playwright-cli snapshot                  # 看结果
playwright-cli close
```

定位元素三选一：ref（`e15`，首选）/ CSS（`"#main > button.submit"`）/ Playwright locator（`"getByRole('button', { name: 'Submit' })"`、`"getByTestId('submit-button')"`）。

快照可瘦身：`snapshot --depth=4`（限深度）、`snapshot e34`（只看子树）、`snapshot "#main"`（限元素）、`snapshot --boxes`（带 bounding box）。

### 会话（多浏览器、持久 profile）

CLI 默认把 profile 放内存，**同一会话内** cookie/storage 跨命令保留、浏览器关掉即丢。`--persistent` 落盘持久，`-s=<name>` 开独立命名会话：

```bash
playwright-cli -s=work open https://example.com --persistent
playwright-cli -s=work click e6
playwright-cli list                      # 列所有会话
playwright-cli -s=work close             # 关这个
playwright-cli close-all                 # 关全部
```

也可给 agent 设 `PLAYWRIGHT_CLI_SESSION=<name>` 环境变量统一会话。

### 接管现有 Chrome / Edge（attach）

```bash
playwright-cli attach --cdp=chrome           # 按 channel 连本地正在跑的 Chrome
playwright-cli attach --cdp=http://localhost:9222   # 连 CDP endpoint
playwright-cli attach --extension=chrome     # 经 Playwright 扩展连
playwright-cli detach                        # 脱离，外部浏览器继续跑
```

### 省 token 的输出控制

- `--raw`：剥掉页面状态/生成代码/快照，只回结果值，方便管道：
  ```bash
  playwright-cli --raw eval "JSON.stringify(performance.timing)" | jq '.loadEventEnd - .navigationStart'
  TOKEN=$(playwright-cli --raw cookie-get session_id)
  ```
- `--json`：把每条回复包成 JSON（`playwright-cli list --json`）。

### 常用命令面（速记，完整看官方 skill）

- 核心：`open/goto/click/dblclick/fill/type/press/hover/select/check/uncheck/drag/drop/upload/eval/snapshot/screenshot/pdf/resize/close`
- 导航：`go-back/go-forward/reload`；标签：`tab-list/tab-new/tab-close/tab-select`
- 存储：`state-save/state-load`、`cookie-*`、`localstorage-*`、`sessionstorage-*`
- 网络：`route/route-list/unroute`（mock）；DevTools：`console/requests/request/run-code/tracing-*/video-*/generate-locator/highlight`
- 可视化看板：`playwright-cli show`（实时看/接管后台所有会话）；`show --annotate`（让用户在页面上画框批注，你收到截图+快照+备注，适合"UI review / 设计反馈"）

> Windows 上 URL 带 `&` 会被 shell 截断：`cmd.exe` 用 `^&`，PowerShell 用 `--%`。

## 入口 2：Playwright MCP（`@playwright/mcp`）

MCP server，把 Playwright 暴露成 MCP 工具，基于**无障碍树**而非截图（不需要视觉模型、确定性高）。

### MCP 客户端配置

不同 MCP 客户端的配置文件位置不同，核心都是声明本地命令和参数。例如：

```json
{
  "mcpServers": {
    "playwright": {
      "type": "local",
      "command": "npx",
      "args": ["@playwright/mcp@latest"],
      "tools": ["*"]
    }
  }
}
```

无显示器时使用 headless；是否改用 HTTP 传输取决于 MCP 服务要不要长驻或跨进程连接，与浏览器是否显示窗口是两个独立选择：`npx @playwright/mcp@latest --headless --port 8931`，客户端连接 `http://localhost:8931/mcp`。官方 Docker 镜像也使用 headless Chromium。[参数与HTTP传输](https://github.com/microsoft/playwright-mcp/blob/7e0457a7cbf88823bf0146d12c46ae12c6818247/README.md#L420-L444)

### 关键工具与能力

- 操作：`browser_navigate / browser_click / browser_type / browser_fill_form / browser_select_option / browser_hover / browser_press_key / browser_snapshot / browser_take_screenshot / browser_evaluate / browser_file_upload / browser_handle_dialog`
- 内省：`browser_console_messages / browser_network_requests / browser_network_request`
- `browser_snapshot`（无障碍快照）是主交互面，优于截图；`browser_run_code_unsafe` 等价 RCE，慎用。

### profile 与初始状态（常用 flag）

- `--headless`（默认 headed）、`--browser chrome|firefox|webkit|msedge`、`--device "iPhone 15"`、`--viewport-size 1280x720`、`--user-agent ...`
- `--isolated`：profile 只在内存；配 `--storage-state auth.json` 注入登录态。
- `--user-data-dir <path>`：持久 profile（默认每个 workspace 一份）。**同一 profile 同时只能一个浏览器用**，并发要么 `--isolated` 要么各自 `--user-data-dir`。
- `--caps vision,pdf,devtools`：开额外能力（坐标点击 / PDF / DevTools）。
- `--proxy-server`、`--ignore-https-errors`、`--init-script`、`--secrets`（dotenv，回包里把明文替换成占位，**只是便利不是安全边界**）。

> MCP **不是安全边界**，`allowUnrestrictedFileAccess` 等只是护栏。

## 入口 3：库脚本（Node 或 Python）

要可复现脚本 / 批量 / 接 CI 时直接写库代码。和 `@playwright/test` 的区别：库要你**自己** launch 浏览器、建 context、建 page、收尾 close（test runner 用 fixture 自动给 `page`/`context`、自带 web-first 断言、自动收尾）。

### Node（库）

```js
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch();           // headless 默认；headless:false 看界面，slowMo:50 放慢
  const page = await browser.newPage();
  await page.goto('https://playwright.dev/');
  await page.screenshot({ path: 'example.png' });
  await browser.close();
})();
```

### Python（uv）

`uv run --with playwright script.py`（首次还要 `playwright install chromium`）。同步 / 异步两套 API：

```python
# 同步
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto("https://playwright.dev")
    page.screenshot(path="example.png")
    browser.close()
```

```python
# 异步
import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto("https://playwright.dev")
        await page.screenshot(path="example.png")
        await browser.close()
asyncio.run(main())
```

> 想要 Python 自动生成脚本：`playwright codegen <url>`（录制操作成代码）。

## CLI vs MCP：到底用哪个

[`@playwright/cli` v0.1.18 README](https://github.com/microsoft/playwright-cli/blob/v0.1.18/README.md#L5-L19) 对两个入口的定位是：

- **CLI（`@playwright/cli` + SKILLS）= coding agent 首选**。CLI 调用 **token 更省**：不往上下文里塞庞大的工具 schema 和冗长的无障碍树，agent 用简洁、专用命令直接动作 —— 适合要同时兼顾大代码库、测试、推理、还要省上下文窗口的高吞吐 agent。
- **MCP** 适合需要**持久状态 + 富内省 + 对页面结构反复推理**的专门 agentic loop（探索式自动化、自愈测试、长程自治），此时"维持连续浏览器上下文"的价值盖过 token 成本。

命令式 coding agent 通常适合 CLI；跨多轮维持浏览器上下文、持续检查页面结构时，MCP 的状态和内省更有价值。它们也可以同时存在：CLI 做短操作，MCP 承担长会话。
