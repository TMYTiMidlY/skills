---
name: browser-use
description: 浏览器自动化操作 —— 用 Playwright（CLI / MCP / Python·Node 脚本）、Camoufox（反指纹 Firefox）或接管已有 Chrome 登录态来操控页面、截图、填表、下载受保护文件、提取 pdf.js 嵌入数据。当用户提到浏览器自动化、网页截图、下载浏览器预览的 PDF、绕过下载限制、提取嵌入数据、反爬/指纹，或问 Playwright 该用 uv 还是 npm 装、该用 MCP 还是 CLI 时触发。
---

# Browser Use Skill

## 触发条件

- 需要通过浏览器自动化执行操作（导航、点击、填表、截图、下载）
- 用 Playwright、Camoufox 或浏览器 MCP 访问网页
- 下载浏览器中预览的 PDF / 文件，或提取嵌入的 pdf.js / pdfjs 数据
- 绕过网站的直接下载限制获取资源
- 需要反指纹 / 反爬 / 按代理伪造 GeoIP 的隐身浏览器
- 询问 Playwright 用 uv 还是 npm 安装、用 MCP 还是 CLI

## 方案选择：默认 Node + Playwright CLI

**默认直接用 Node + Playwright CLI（`@playwright/cli`），不要再问用户用哪个方案。** 这是官方对 coding agent 的首选（token 最省）。装好后用 `playwright-cli open/snapshot/click/...` 驱动浏览器：

```bash
# 全局装；或免装直接用 npx（两者都行）
npm install -g @playwright/cli@latest        # 或：npx @playwright/cli@latest --help
playwright-cli install --skills              # 落地官方 skill，拿到完整命令面
playwright-cli open https://example.com
playwright-cli snapshot                      # 拿 eN refs
playwright-cli click e15
```

> `npx @playwright/cli@latest <cmd>`（免全局安装）和 `npm i -g` 后直接 `playwright-cli <cmd>` 等价，按手感选。完整命令、会话、attach 现有 Chrome 等见 [references/playwright.md](references/playwright.md)。

**只有以下情况才偏离这个默认**（用户明示，或场景明确需要）：

| 改用 | 触发条件 |
|---|---|
| **接管现有 Chrome**（open-claude-in-chrome MCP）| 用户要在**已登录的当前浏览器会话**里直接操作（复用登录态） |
| **Playwright MCP**（`@playwright/mcp`）| 用户明确要 MCP，或要跨多轮维持同一浏览器上下文做探索式 / 自愈式长程自动化 |
| **Playwright 脚本（库）** | 用户要交付**可复现的 Python/Node 脚本**、批量任务或接 CI |
| **Camoufox**（Python，+ 其 agent CLI）| 目标站有反爬 / 指纹检测，需要隐身 Firefox、指纹注入、按代理 IP 伪造 GeoIP/时区/locale。详见 [references/camoufox.md](references/camoufox.md) |

其余一律走默认（Node + Playwright CLI）。用户若直接点名某方案，按用户来，不用再确认。

## Playwright：uv/npm 与 MCP/CLI 怎么选（核心结论）

**心智模型**：Playwright 本体是 **Node 项目**。浏览器由一个 Node driver（`playwright-core`）驱动，各语言绑定只是这个 driver 的 RPC 客户端。实测 playwright-python 的 wheel 里**自带一份 Node.js 运行时 + driver**，所以"用 Python 还是 Node"只决定你写脚本 / 调命令的语言，底层都是同一套 Node driver。

**uv vs npm**（详见 [references/playwright.md](references/playwright.md)）：
- **npm / Node 是一等公民**：装上能拿到库 + `playwright` CLI + 测试运行器(`@playwright/test`) + agent CLI(`@playwright/cli`) + MCP(`@playwright/mcp`)。
- **uv / Python 是语言绑定**：`uv add playwright` / `uv run --with playwright …` 只给 Python 库 + 一个 `playwright` 管理 CLI（install/codegen/…），**没有测试运行器 / agent CLI / MCP**（那三个是 Node-only 的独立 npm 包）。
- 推荐：**要驱动浏览器做事 → npm + `@playwright/cli`**；**要写 Python 自动化脚本或接 Camoufox → uv**。别"为省 Node 用 uv"——Python wheel 内部照样捆了 Node。

**MCP vs CLI**（官方原话结论）：
- **CLI（`@playwright/cli` + SKILLS）= coding agent 首选**：调用 token 更省，不往上下文塞庞大工具 schema 和冗长无障碍树。
- **MCP** 适合需要持久状态 + 富内省 + 反复推理页面结构的长程 agentic loop（探索 / 自愈 / 自治）。
- **对 Copilot CLI（就是个 coding agent）→ 默认用 CLI**：`npm i -g @playwright/cli@latest` 后 `playwright-cli install --skills` 落地官方 skill，再 `playwright-cli open/snapshot/click/...`。

## Camoufox：反指纹 Firefox（概览）

Camoufox = 改过的 Firefox + **Playwright 兼容的 Python API**；页面操作仍按 Playwright 模型写（`page.goto()/click()/screenshot()`）。它在 C++ 层注入指纹（navigator/屏幕/WebGL/字体/WebRTC/GeoIP），JS 检测不到。

**包二选一**：`camoufox`（官方稳定 0.4.11，发布延迟）vs `cloverlabs-camoufox`（活跃 alpha 0.6.0，浏览器开发主线，带 per-context 指纹 + `fingerprint_preset` 真实预设）。两者共用 `camoufox` import/CLI 命名空间，**装在各自 venv 里别混**。

Camoufox 是 **Python-only、无 npm 包、conda-forge 也没有**，只能 `uv`/`pip` 装；无桌面/无 sudo 的机器还要补 GTK/ALSA 系统库才能启动。完整的包/通道选择、CLI 命令、三层依赖心智模型、无 sudo 补库方案 A/B/C、指纹与 `fingerprint_preset`、两个 agent CLI（camoufox-browser / camoufox-cli）对比、反爬实测，全在 [references/camoufox.md](references/camoufox.md)。

## open-claude-in-chrome MCP（接管现有 Chrome）

**插件信息**：
- GitHub: https://github.com/noemica-io/open-claude-in-chrome
- 作者: [Noemica (Sebastian Sosa)](https://github.com/CakeCrusher) · License: MIT · 18 个 MCP tools

该插件是 Claude 官方 Chrome 扩展的 clean-room 实现，移除了域名黑名单限制，支持任意 Chromium 浏览器。适合"已有登录态、要接管当前页"。

常用操作：

```text
read_page          # 获取页面 DOM
javascript_tool    # 在 iframe 中执行 JavaScript
tabs_context_mcp   # 获取 tab 列表
```

查找嵌入 iframe：

```javascript
JSON.stringify({iframes: document.querySelectorAll('iframe').length, iframeSrc: document.querySelector('iframe')?.src})
```

> 想用 Playwright 接管已有 Chrome 而非装这个扩展？用 `playwright-cli attach --cdp=chrome` 或 MCP 的 `--cdp-endpoint`（见 references/playwright.md）。

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

提取前先在 Console 执行 `PDFViewerApplication.pagesCount` 确认 PDF 已加载完。该方法利用的是用户在浏览器中已合法访问的资源。

## 站点案例

具体站点的工作流单独成文，按需查阅：

- [references/smartedu-pdf-download.md](references/smartedu-pdf-download.md) — 国家中小学智慧教育平台（basic.smartedu.cn）受保护 PDF 的提取
- [references/yuketang-post-comment.md](references/yuketang-post-comment.md) — 雨课堂（yuketang.cn）论坛发评论流程
