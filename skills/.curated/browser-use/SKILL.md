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

Camoufox CLI 用 `uvx --from`，避免把实验依赖写进当前项目：

```bash
uvx --from "cloverlabs-camoufox[geoip]" camoufox sync
uvx --from "cloverlabs-camoufox[geoip]" camoufox set official/stable
uvx --from "cloverlabs-camoufox[geoip]" camoufox fetch
uvx --from "cloverlabs-camoufox[geoip]" camoufox version
```

本地脚本需要临时依赖时用 `uv run --with`：

```bash
uv run --with "cloverlabs-camoufox[geoip]" script.py
```

包/通道关系：
- `camoufox`：官方稳定 PyPI wrapper，但 release 通常延迟。
- `cloverlabs-camoufox`：更新的实验 wrapper，仍提供 `camoufox` import/CLI 命名空间。
- `camoufox-browser`：第三方 CLI/MCP wrapper，依赖 `cloverlabs-camoufox[geoip]>=0.5.5`，适合 agent 风格的 `open/snapshot/click/fill/screenshot`，但项目还年轻。

浏览器二进制不是放在 PyPI wheel 里；`python -m camoufox fetch` / `camoufox fetch` 会下载对应 Camoufox browser release。实测 `cloverlabs-camoufox` 的 `official/stable` 曾拉取 GitHub release：`daijro/camoufox/releases/download/v135.0.1-beta.24/...zip`。PyPI 只负责安装 Python 包和 CLI。

本机实测记录：普通 `urllib` 访问 PyPI 项目页遇到 `Client Challenge`；直接调用裸 Camoufox binary 截图也得到挑战/空白页；用 Python wrapper 启动 Camoufox headless 后，多次访问 `https://pypi.org/project/camoufox/` 和 `https://pypi.org/project/cloverlabs-camoufox/` 成功拿到标题，并保存截图到 `/tmp/pypi-camoufox-wrapper-js.png`。这说明在当时环境下可以通过，但不要承诺对所有站点、IP 和版本稳定绕过。

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
