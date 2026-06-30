---
description: Playwright 详解 —— uv/npm 安装差异、CLI/MCP/脚本三种入口、CLI vs MCP 选型
---

# Playwright 详解

涵盖：架构心智模型、uv vs npm 安装差异与推荐、三种入口（CLI / MCP / 库脚本）、CLI vs MCP 该用哪个。

## 架构：为什么说"Playwright 本体是 Node"

Playwright 的浏览器由一个 **Node driver**（`playwright-core` npm 包）驱动；各语言绑定（Python / .NET / Java）都只是这个 driver 的 **RPC 客户端**，本身不直接开浏览器。

实测证据（microsoft/playwright-python）：

- `pyproject.toml` 里 `[project.scripts] playwright = "playwright.__main__:main"` —— Python wheel 装上后会提供一个 `playwright` 命令。
- 仓库根有 `NODE_VERSION`（实测 `24.17.0`）和 `DRIVER_VERSION`（实测 `1.61.1-beta-…`）。`setup.py` 注释写明："driver is assembled … from the playwright-core npm package … and the official Node.js binaries"。
- 即：**Python wheel 里自带一份 Node.js 运行时 + playwright-core driver**，解包进 `playwright/driver/`。Python 调 `page.click()` 实际是把请求发给这个内置 Node driver。

> 结论：用 Python 还是 Node，只决定你**写脚本 / 调命令的语言**；底层都是同一套 Node driver 开同一批浏览器（Chromium / Firefox / WebKit，版本随 Playwright 版本走，例如 Chromium 149 / Firefox 151 / WebKit 26.5）。**"用 uv 就能彻底摆脱 Node"是个误解**——Python wheel 内部照样捆了 Node，你只是不用自己管它。

## 安装：uv（Python）vs npm（Node）

| | npm / Node（一等公民）| uv / Python（语言绑定）|
|---|---|---|
| 装库 | `npm i -D playwright`（库）<br>`npm init playwright@latest`（测试脚手架，注意是 **init** 不是 install）| `uv add playwright`（项目）<br>`uv run --with playwright script.py`（临时）|
| 装浏览器 | `npx playwright install chromium` | `playwright install chromium`（wheel 自带 CLI）<br>或 `uv run --with playwright playwright install chromium` |
| Linux 系统依赖 | `npx playwright install-deps`（**需 root**）| `playwright install-deps`（**需 root**）|
| 你能拿到 | 库 + `playwright` CLI + **Test Runner**(`@playwright/test`) + **agent CLI**(`@playwright/cli`) + **MCP**(`@playwright/mcp`) | 库 + `playwright` 管理 CLI（`install` / `install-deps` / `codegen` / `open` / `screenshot` / `pdf` …）|
| 你拿不到 | —— | **Test Runner、agent CLI、MCP 全都没有** |

**关键差异**：`@playwright/test`、`@playwright/cli`、`@playwright/mcp` 是**三个独立的 npm 包，只能 npx/npm 跑**（实测 `@playwright/cli` v0.1.14、`@playwright/mcp` v0.0.76）。`pip/uv install playwright` 只给 Python 库 + 一个 `playwright` 管理 CLI，**不含**测试运行器 / agent CLI / MCP。

### 无 sudo 机器的系统依赖

`install-deps` 要 root。无 sudo 的 headless / WSL 机器装不了系统库，浏览器起不来（缺 `libgtk` 等）。两条路：

- 用官方 Docker 镜像 `mcr.microsoft.com/playwright`（自带浏览器 + 系统库），脚本/MCP 都能跑进去。
- 或用与 Camoufox 相同的 pixi 用户态补库套路（`pixi` 装 `gtk3` 等 + `LD_LIBRARY_PATH`），见 [camoufox.md](camoufox.md) 的「补齐系统库 方案 A/B/C」——同样适用于 Playwright 的 Chromium/Firefox。

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

### 给 Copilot CLI 配置

写 `~/.copilot/mcp-config.json`：

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

无显示器要跑 headed，或要长驻服务，改用 HTTP 传输：`npx @playwright/mcp@latest --port 8931`，客户端配 `"url": "http://localhost:8931/mcp"`。也有官方 Docker 镜像（仅 headless chromium）。

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

官方 README（playwright-cli / playwright-mcp）给的原话结论：

- **CLI（`@playwright/cli` + SKILLS）= coding agent 首选**。CLI 调用 **token 更省**：不往上下文里塞庞大的工具 schema 和冗长的无障碍树，agent 用简洁、专用命令直接动作 —— 适合要同时兼顾大代码库、测试、推理、还要省上下文窗口的高吞吐 agent。
- **MCP** 适合需要**持久状态 + 富内省 + 对页面结构反复推理**的专门 agentic loop（探索式自动化、自愈测试、长程自治），此时"维持连续浏览器上下文"的价值盖过 token 成本。

**对 Copilot CLI（本身就是 coding agent）→ 默认用 CLI**（`@playwright/cli` + `playwright-cli install --skills`）。只有当任务是"跨很多轮维持同一个浏览器上下文做探索 / 自愈"时，才考虑 MCP。
