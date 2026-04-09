# VS Code Web 中文语言包 NLS 覆盖 Bug

> 2026-04-08 | VS Code 1.115.0 | WSL2 Mirrored Networking | Chrome

## 症状

- `code serve-web` 通过 `10.144.18.10:8080` 正常，`127.0.0.1:8080` 页面空白
- Console：`Uncaught Error: !!! NLS MISSING: 17116 !!!`
- Ctrl+Shift+R / 无痕模式均无效

## 排查关键转折

服务端文件完整（17287 条 NLS 消息），curl 验证无误。缓存、Service Worker、CSP、模块加载顺序全部排除。

**突破点**：让用户在 Console 执行 `globalThis._VSCODE_NLS_MESSAGES?.length` → 返回 **17109**（不是 undefined 也不是 17287）。说明数组被加载了，但被替换成了更短的版本。

随后用 `curl -H "Accept-Language: zh-CN"` 请求页面 → 发现服务器根据 Accept-Language 注入了中文 NLS CDN URL → 下载验证中文 NLS 恰好 17109 条。

## 根因

1. Chrome `Accept-Language` 含 `zh-CN` → 服务器注入 `https://www.vscode-unpkg.net/.../zh-cn/nls.messages.js`
2. HTML 先加载英文 NLS（17287 条），再加载中文 NLS（17109 条）→ 中文直接覆盖 `globalThis._VSCODE_NLS_MESSAGES`
3. 中文语言包翻译不完整，缺少 index 17109-17286 → `d(17116, null)` 抛出异常 → 页面崩溃
4. 10.144.18.10 能用是因为该 IP 到 CDN 的请求失败，英文 NLS 保持不变 — "能用"不是因为它做对了什么，而是因为它恰好失败了

## 解决

- VS Code Web 里 `Ctrl+Shift+P` → "Configure Display Language" → `en`
- 或 Chrome 语言设置把 English 排到中文前面
- 或等上游中文语言包补全

# PDF.js v5.5+ 在 Chrome < 140 上崩溃 (`Uint8Array.toHex` polyfill 缺失)

> 2026-04-10 | LaTeX-Workshop 10.14.1 (fork) | pdfjs-dist 5.6.205 | htbrowser Chrome 132

## 症状

- LaTeX-Workshop PDF 预览在新 Chrome 正常，老 Chromium 套壳浏览器（`Chrome/132 ... htbrowser/2.0.13`）打开 PDF 全白
- Console: `TypeError: hashOriginal.toHex is not a function` at `pdf.mjs:428` (BaseExceptionClosure)，外层包装在 `viewer.mjs:24251 加载 PDF 时发生错误`

## 排查关键转折

**第一层**直接 grep dev 仓库 `node_modules/pdfjs-dist/build/pdf.worker.mjs` 找 `\.toHex(`，看上下文有没有 if 守卫：

```js
// 安全（5.4.394 还有）：
if (Uint8Array.prototype.toHex) { return arr.toHex() }
return Array.from(arr, n => hexNumbers[n]).join("")

// 不安全（5.6.205 拿掉了）：
xxx.toHex()  // 直接调用
```

**判断 pdfjs 版本是否 broken 的一句话脚本**：`grep -A1 'Uint8Array.prototype.toHex' node_modules/pdfjs-dist/build/pdf.worker.mjs`，没看到 if 就是 broken。

**第二层**才是真坑：cp 完旧 pdfjs 后还报 `Cannot read properties of null (reading 'nextElementSibling') at patchViewerUI gui.ts:103`。原因是 pdfjs upstream 把 sidebar 改名成 viewsManager（element id `sidebarToggleButton` → `viewsManagerToggleButton`），latex-workshop 用 `ed96911a Fix new PDF.js viewer renames` 适配过。**回退 pdfjs 静态资源时必须把这几个 overlay 组件一起回退**，否则旧 viewer.html 配新 overlay 必崩。

## 根因

PDF.js 升级版本后无条件调用 TC39 提案 `Uint8Array.prototype.toHex()`（[proposal-arraybuffer-base64](https://github.com/tc39/proposal-arraybuffer-base64)）做 hex 编码。这个 API V8 直到 Chrome 140 才 ship（2025 年 9 月），Firefox 133 / Safari 18.2 早就有。低于 V8 140 的环境（国内套壳浏览器、老 Electron、老 VSCode webview、QtWebEngine 等）调用必 throw。

## 解决（保留扩展现有代码 + 只回退 pdfjs 相关）

1. **找一个 pdfjs 安全的旧版扩展**。实测 `latex-workshop 10.13.1` 自带 `pdfjs-dist 5.4.394`，有 fallback 守卫。VS Code marketplace 在 serve-web 里 "Install from VSIX" 报 `Extension not found`，**绕过办法**是直接 curl marketplace API：`https://marketplace.visualstudio.com/_apis/public/gallery/publishers/<pub>/vsextensions/<ext>/<ver>/vspackage`，返回的是 gzipped vsix（用 `curl --compressed`）。vsix 本质 zip，`unzip` 直接解开。

2. **替换已安装扩展的 pdfjs 静态资源**（成套）：
   - `viewer/{viewer.mjs,viewer.html,viewer.css,locale,images}`
   - `node_modules/pdfjs-dist/`
   - **保留** `viewer/latexworkshop.css`（差异只是新增 hide selector，对旧 html 是 no-op）

3. **同步回退 latex-workshop overlay**：把 `out/viewer/components/{gui,interface,refresh,state}.js` 也用旧 vsix 里的版本覆盖。这 4 个文件是 `ed96911a` 改名适配过的，跟旧 viewer.html 不兼容，必须配套。其他 6 个 components（`connection,l10n,synctex,trimming,utils,viewerhistory`）不动 — `git log <pre-merge>..HEAD -- viewer/components/` 显示 user fork 没改过它们。

4. Reload Window 验证。

## 教训

- **upstream merge 类 bug 不要假设"只动了 X"**。一次 merge 带几十个 commit，pdfjs viewer 静态资源、对应 element id rename、latex-workshop overlay 适配是**一体的**，回退也必须一体。
- **`git log A..B -- path/` 比 `git diff A B -- path/` 更精准**。前者告诉你 commit 历史和动机，后者只看终态。先 log 看 commit 主题挑出"只是 rename"的纯适配 commit，能省一半判断时间。
- **判断 JS 库版本是否受 polyfill 缺失影响，最快的办法是 grep 关键 API 看有没有 if 守卫**，比查 changelog 快。
- **VS Code serve-web 装老版扩展报 "Extension not found"**：走 marketplace API URL 直接 curl 即可。
