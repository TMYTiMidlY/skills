---
name: browser-use
description: 需要自动操作网页、复用浏览器登录态、截图填表、下载当前身份可访问的文件或提取嵌入数据时使用。Playwright、直接 HTTP 与文件格式解析工具可以按任务组合；需要浏览器指纹兼容时再考虑 Camoufox。
---

# Browser Use Skill

## 触发条件

- 需要通过浏览器自动化执行操作（导航、点击、填表、截图、下载）
- 用 Playwright、Camoufox 或浏览器 MCP 访问网页
- 下载浏览器中预览的 PDF / 文件，或提取嵌入的 pdf.js / pdfjs 数据
- 获取当前登录身份有权访问、但需要浏览器会话才能取得的资源
- 需要反指纹 / 反爬 / 按代理伪造 GeoIP 的隐身浏览器
- 询问 Playwright 用 uv 还是 npm 安装、用 MCP 还是 CLI

## 访问思路

浏览器和直接 HTTP 是两条可以并行、串联或互相替换的数据路径，没有固定先后。浏览器擅长 JavaScript 状态、登录会话、用户交互和真实网络请求；直接 HTTP 擅长静态页面、公开接口、原始响应和可复现的批量处理。常见组合是先从浏览器定位真实请求，再用 HTTP 客户端复现；也可以先抓页面，遇到会话或脚本依赖后再打开浏览器。

页面界面只是证据面之一。无障碍快照没有内容时，继续看 DOM、隐藏字段、内嵌脚本和网络响应；浏览器取得文件链接或会话后，Word、Excel、PDF、音视频等内容交给对应解析工具。验证码表示访问流程需要额外处理，不等于自动化代码本身出错；源站没有提供的更新时间或身份信息，则要通过其他来源交叉核验。

## 浏览器方案

确实需要浏览器时，Node + Playwright CLI（`@playwright/cli`）是轻量入口；CLI、MCP、库脚本、现有浏览器会话和 Camoufox 各自解决不同问题，可以按任务组合。装好后用 `playwright-cli open/snapshot/click/...` 驱动浏览器：

```bash
# 全局装；或免装直接用 npx（两者都行）
npm install -g @playwright/cli@latest        # 或：npx @playwright/cli@latest --help
playwright-cli install --skills              # 落地官方 skill，拿到完整命令面
playwright-cli open https://example.com
playwright-cli snapshot                      # 拿 eN refs
playwright-cli click e15
```

> `npx @playwright/cli@latest <cmd>`（免全局安装）和 `npm i -g` 后直接 `playwright-cli <cmd>` 等价。完整命令、运行形态、会话和启动诊断见 [references/playwright.md](references/playwright.md)。

| 入口 | 适用场景 |
|---|---|
| **Playwright CLI** | 命令式操作、快速取证、希望控制上下文输出量 |
| **Playwright MCP** | 需要持续状态、丰富页面内省或长程探索 |
| **Playwright 库** | 需要交付脚本、批量处理或接入 CI |
| **现有浏览器会话** | 需要复用用户已登录的页面和浏览器身份 |
| **Camoufox** | 需要 Firefox 指纹兼容、代理 GeoIP 或普通浏览器被指纹风控时 |

## Playwright 运行入口

Playwright 的 Node 与 Python 入口共享同一套浏览器驱动模型，但提供的命令面不同：`@playwright/cli`、测试运行器和 MCP 属于 Node 生态；Python 包适合脚本和 Camoufox。CLI 默认无头运行，只有显式使用 `--headed` 才显示窗口。安装差异、CLI/MCP/库脚本选择和受限环境诊断见 [references/playwright.md](references/playwright.md)。

## Camoufox

Camoufox 是经过指纹兼容改造的 Firefox，Python 接口继续使用 Playwright 的页面模型。当前文档以官方源码 tag [`v152.0.4-beta.29`](https://github.com/daijro/camoufox/tree/v152.0.4-beta.29) 为架构基线；Python 包、浏览器二进制和系统运行库是彼此独立的三层。它能减少常见自动化与指纹不一致，不保证所有站点、验证码、账号权限或代理组合都可用。

官方分发 `camoufox` 和 CloverLabs 分发 `cloverlabs-camoufox` 都安装 `camoufox` import/CLI 命名空间，应放在不同隔离环境中。它们与源码 tag、浏览器 release 的对应关系，以及安装和无管理员权限环境见 [references/camoufox.md](references/camoufox.md)。

## 现有浏览器会话

**插件信息**：
- GitHub: [open-claude-in-chrome](https://github.com/noemica-io/open-claude-in-chrome/tree/12b0654e71731675bfc1ef10e96334e93df71f5e)
- 作者: [Noemica (Sebastian Sosa)](https://github.com/CakeCrusher) · License: MIT

该插件是 Chrome 扩展的第三方 clean-room 实现，适合“已有登录态、要接管当前页”。不需要扩展时，也可直接使用 Playwright CLI 的 CDP 或 extension attach。

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

> 想用 Playwright 接管已有 Chrome 而非装这个扩展？用 `playwright-cli attach --cdp=chrome` 或 MCP 的 `--cdp-endpoint`，详见 [Playwright](references/playwright.md)。

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
