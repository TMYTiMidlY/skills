---
name: browser-use
description: 浏览器自动化操作，包括通过 MCP 插件操控浏览器、提取页面嵌入的 pdf.js 数据、下载受保护文件等。当用户提到浏览器自动化、下载浏览器中预览的 PDF、绕过下载限制、提取嵌入数据时触发。
---

# Browser Use Skill

## 触发条件

当用户提到以下场景时触发：
- 需要通过浏览器自动化执行操作
- 需要下载浏览器中预览的 PDF 或文件
- 需要提取浏览器中嵌入的 pdf.js、pdfjs 数据
- 需要绕过网站的直接下载限制获取资源

## 核心能力

### 1. open-claude-in-chrome MCP 插件

**插件信息**:
- GitHub: https://github.com/noemica-io/open-claude-in-chrome
- 作者: [Noemica (Sebastian Sosa)](https://github.com/CakeCrusher)
- License: MIT
- 功能: 浏览器自动化，支持 18 个 MCP tools

该插件是 Claude 官方 Chrome 扩展的 clean-room 实现，移除了域名黑名单限制，支持任意 Chromium 浏览器。

### 2. 常用操作

#### 获取页面 DOM
```
read_page
```

#### 在 iframe 中执行 JavaScript
```
javascript_tool
```

#### 查找嵌入的 iframe
```javascript
JSON.stringify({iframes: document.querySelectorAll('iframe').length, iframeSrc: document.querySelector('iframe')?.src})
```

### 3. pdf.js 数据提取

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

### 4. 获取 tab 列表

```
tabs_context_mcp
```

## 应用场景

- 下载受保护/需要认证的 PDF 文件
- 提取浏览器中预览的文档
- 自动化网页操作（填表、点击、截图）
- 抓取网页内容或网络请求
