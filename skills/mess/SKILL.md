---
name: mess
description: 记录排查过的疑难杂症和踩坑经历。当用户遇到类似问题、提到相关关键词、或想回顾之前解决过的问题时触发。
---

# Mess — 疑难杂症档案

记录排查过程中走过的弯路、最终定位的根因、以及解决方案。每个案例都是一次完整的排查故事，重点不是答案本身，而是**怎么找到答案的**。

遇到用户报告的问题与已有案例相似时，先回顾对应 reference，避免重复走弯路。

## 案例索引

- **VS Code Web 中文语言包 NLS 覆盖 bug** → [references/bug-fix.md](references/bug-fix.md)
  - 关键词：`code serve-web`、`NLS MISSING`、`nls.messages.js`、`127.0.0.1 能用但另一个 IP 不行`（或反过来）、`workbench.js 报错`、`页面空白`、`语言包`、`Accept-Language`
- **PDF.js v5.5+ 在 Chrome < 140 上崩溃 (`Uint8Array.toHex` polyfill 缺失)** → [references/bug-fix.md](references/bug-fix.md)
  - 关键词：`hashOriginal.toHex is not a function`、`Uint8Array.toHex`、`pdfjs-dist`、`PDF.js v5.6.205`、`htbrowser`、`Chrome 132`、`viewer.mjs:24251`、`pdf.mjs:428`、`patchViewerUI`、`viewsManagerToggleButton`、`sidebarToggleButton`、`LaTeX-Workshop PDF 预览全白`、`merge upstream 后浏览器打不开 PDF`
