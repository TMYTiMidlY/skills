# PDF.js `Uint8Array.toHex` 兼容性事故 —— 从旧浏览器崩溃到官方 legacy build 修复

> 首记 2026-04-10（LaTeX-Workshop 10.14.1 fork · pdfjs-dist 5.6.205 · htbrowser Chrome 132）
> 补全 2026-07-22（jujuleaf 个人项目 · pdfjs-dist 6.1.200 · 核对上游官方修复）

一句话：**pdf.js 从某个版本起无条件调用 TC39 的 `Uint8Array.prototype.toHex()`，这个 API 旧浏览器没有；官方唯一正解是"用 legacy build"（Babel+core-js 转译版），不是降级、也不是自己手写 polyfill。** 同一个坑先后砸中 LaTeX-Workshop（VSCode 扩展）和 jujuleaf（自研 LaTeX 编辑器），两者最终都落到 legacy build 上。

---

## 症状

- PDF 预览在新 Chrome 正常，**旧 Chromium 套壳浏览器 / 旧 Electron / 旧 VSCode webview / QtWebEngine** 打开 PDF 全白。
- Console：`TypeError: hashOriginal.toHex is not a function`，位置 `pdf.mjs:428`（BaseException）。
  - LaTeX-Workshop 里外层包着 `viewer.mjs:24251 加载 PDF 时发生错误`。
  - 触发环境示例：`Chrome/132 ... htbrowser/2.0.13`。

## 根因

pdf.js 用 [TC39 `proposal-arraybuffer-base64`](https://github.com/tc39/proposal-arraybuffer-base64) 的 `Uint8Array.prototype.toHex()`（以及 `toBase64`/`fromBase64`）做 fingerprint 的 hex 编码。这 6 个方法的原生落地时间**非常新**：

| 环境 | 原生支持起始 |
|---|---|
| Chrome / V8 | **140**（2025-09） |
| Firefox | 133 |
| Safari | 18.2 |
| Node.js | 25 |
| core-js（polyfill） | **3.38.0**（2024-08-05）起提供 |

低于上述版本的运行时调用 `.toHex()` 必 `throw`。

### 精确的版本边界（比"v5.5+"准）

- **`5.4.530`（2025-12-28）**：最后一个仍带手写 fallback 守卫的发行版，安全。
- **commit [`5b368dd58a39b02f58314ee9e23eddb3c6f01fee`](https://github.com/mozilla/pdf.js/commit/5b368dd58a39b02f58314ee9e23eddb3c6f01fee)**（Jonas Jenwald/Snuffleupagus，committed 2026-01-29）："Remove the `Uint8Array.prototype.toHex()`, `toBase64()`, `fromBase64()` polyfills"。diff 把 `src/shared/util.js` 里的 `toHexUtil()`（内含 `if (Uint8Array.prototype.toHex) {...} else {...}`）整段删掉，`src/core/document.js` 改成直接 `hashOriginal.toHex()`。
- **`5.4.624`（2026-02-01）**：**第一个**包含该 commit、因此在 standard build 中无条件依赖新 API 的发行版。

> 注意：说的是 **standard build 的原生依赖**。legacy build 会由 Babel/core-js 重新注入兼容实现，不受影响。

维护者对旧环境的官方态度（[mozilla/pdf.js#16321](https://github.com/mozilla/pdf.js/issues/16321)）：**"anything not listed [in the FAQ support list] is explicitly unsupported"** —— 删 fallback 是有意为之，旧浏览器请自己用 legacy build 兜。

---

## 完整时间线

| 日期 | 事件 |
|---|---|
| 2026-01-29 | pdf.js commit `5b368dd` 删掉 toHex fallback |
| 2026-02-01 | pdf.js `5.4.624` 发布 = 第一个会崩的版本 |
| 2026-04-10 | **mess 首记**：LaTeX-Workshop fork（10.14.1 / pdfjs 5.6.205）在 htbrowser Chrome 132 上全白。当时**用了降级 workaround**（回退到带 fallback 的 pdfjs 5.4.394），因为官方修复还没出 |
| 2026-04-13 / 04-25 | LaTeX-Workshop issue [#4851](https://github.com/James-Yu/LaTeX-Workshop/issues/4851) / [#4867](https://github.com/James-Yu/LaTeX-Workshop/issues/4867) 报同款错，维护者一开始只回 "Upgrade your vscode"（敷衍答复，非真正修复） |
| 2026-05-07 | **LaTeX-Workshop 官方修复** commit [`a248e2a1`](https://github.com/James-Yu/LaTeX-Workshop/commit/a248e2a1d83393dce9c9dbb8f56fcdbe61a47921) "Fix #4882 Use legacy PDF.js dist build files"，随 **v10.15.2** 发布；用户回报 "10.15.2 works" |
| 2026-07-22 | **jujuleaf**：钉 pdfjs-dist 6.1.200 + 全 legacy + polyfill；commit `b896582` 修构建脚本回归（防止把 legacy worker 覆盖成 standard） |

**读法**：mess 那次降级发生在**官方 legacy 方案出现之前**，当时降级合理；一个月后上游用 legacy build 定案，jujuleaf 又独立走到同一条官方路线上。

---

## 三种做法，只有一种是"官方"

| 做法 | 是什么 | 定性 |
|---|---|---|
| **(a) 用 pdf.js legacy build** | 主线程 + worker 都用 `pdfjs-dist/legacy/build/*`（Babel + core-js 转译，自带 toHex 等 polyfill） | ✅ **官方**（pdf.js 文档 + LaTeX-Workshop 修复都用它） |
| (b) 自己手写 / core-js polyfill | 在 standard build 之前注入 `Uint8Array.prototype.toHex` 等 | ⚠️ workaround（可作保险，但官方不这么推荐） |
| (c) 钉一个旧版 pdfjs（≤5.4.530） | 退回还带 `if(toHex)` fallback 的版本 | ⚠️ workaround（放弃后续修复/特性，不可持续；mess 首记走的就是这条） |

---

## 官方修复证据

### pdf.js：官方立场 = 旧浏览器用 legacy build

- **README**（`mozilla/pdf.js:README.md`）："If you need to support older browsers, run: `npx gulp generic-legacy`"。在线 demo 也分 Modern / Older browsers 两个入口（`.../web/viewer.html` vs `.../legacy/web/viewer.html`）。
- **FAQ wiki**（`Frequently-Asked-Questions#faq-support`）："By default we produce a non-translated/non-polyfilled build, intended for *the latest* browsers. However, we also provide a **translated/polyfilled build for older browsers in a separate bundle (with a `legacy` suffix)**." legacy 官方支持范围：**Firefox ESR+ / Chrome 125+ / Edge / Opera / Safari 18 mostly / Node 22+**。
- **构建配置**（`gulpfile.mjs`）：`generic` 用 `SKIP_BABEL:true`（无 polyfill）；`generic-legacy` 用 `SKIP_BABEL:false` + `babel-plugin-polyfill-corejs3`（core-js **3.49.0**，`shippedProposals:true`），browserslist `Chrome >= 125 / Firefox ESR / Safari >= 18 / Node >= 22`。因此 legacy build 会给 Chrome 125–139 注入 `toHex` polyfill。
- npm 包 `pdfjs-dist` 同时含 `build/`（modern）和 `legacy/build/`（legacy），`package.json` 的 `main` 默认指向 modern。**这就是坑的开关：谁指到 `build/` 谁崩，指到 `legacy/build/` 才安全。**

### LaTeX-Workshop：官方修复就是切 legacy build

- 它把 pdf.js **自带的 stock viewer** 整包，通过本地 Node HTTP server（`src/preview/server.ts`）在 VSCode webview 的 iframe 里加载。
- 修复 commit `a248e2a1`（James Yu，2026-05-07，v10.15.2）只改了 `server.ts` 的路由：

```diff
-    if (request.url.startsWith('/build/') || request.url.startsWith('/cmaps/') || ...) {
-        root = path.resolve(lw.extensionRoot, 'node_modules', 'pdfjs-dist')          // modern，崩
+    if (request.url.startsWith('/build/')) {
+        root = path.resolve(lw.extensionRoot, 'node_modules', 'pdfjs-dist', 'legacy') // legacy，修好
+    } else if (request.url.startsWith('/cmaps/') || ...) {
+        root = path.resolve(lw.extensionRoot, 'node_modules', 'pdfjs-dist')
```

  即：`/build/pdf.mjs`、`/build/pdf.worker.mjs` 的文件系统根从 `pdfjs-dist/` 换到 `pdfjs-dist/legacy/`。相关 issue：#4851 / #4867 / #4882。main 分支 `pdfjs-dist` 为 5.7.284，`engines.vscode` 仅 `^1.114.0`（故意不要求很新的 VSCode）。

### microsoft/vscode：与本事故无关

vscode 核心**不打包 pdf.js、也没有** `Uint8Array.toHex` 相关 polyfill。代码里出现的 `toHex` 只是 `src/vs/base/common/hash.ts` 里 SHA-1/SHA-256 的无关私有 `toHexString()`。所谓"vscode 官方修复"这层是空的——真正的修复在 pdf.js（提供 legacy build）+ LaTeX-Workshop 扩展（切到 legacy build）这两层。

---

## jujuleaf 的落地，以及与 LaTeX-Workshop 的区别

**jujuleaf** = 浏览器端 LaTeX 编辑器（真实 jj 版本控制 + 服务端 latexmk + **自研 PDF.js 连续预览** + 双向 SyncTeX + 双语流水线；Node/express + esbuild 打包的 CodeMirror 6 前端）。关键：它没用 pdf.js 的 stock viewer，而是**把 pdf.js 当库**，自己写了 `src/pdfviewer.js`。

jujuleaf 的兼容做法（三层）：
1. 主线程：`pdfviewer.js` `import "pdfjs-dist/legacy/build/pdf.mjs"` → 被 esbuild 打进 `public/bundle.js`（构建期定死 legacy）。
2. worker：`GlobalWorkerOptions.workerSrc = "/pdf.worker.wrapped.mjs"`；`public/pdf.worker.wrapped.mjs` 先 `import "./pdf-polyfill.mjs"` 再 `import "./pdf.worker.min.mjs"`。后者由 `copy-worker.mjs` 从 `pdfjs-dist/legacy/build/pdf.worker.min.mjs` 拷进 `public/`。
3. 手写 polyfill：主线程 `src/polyfill.js` + worker `public/pdf-polyfill.mjs`（手写 6 个 Uint8Array 方法）。

**jujuleaf commit `b896582`（2026-07-22）修的回归**：原 `package.json` 的 build 第二步是一段内联 `node -e`，从 `build/`（= **standard**）复制 worker 到 `public/`；下一次 `pnpm run build` 会把好的 legacy worker 覆盖成 standard，`toHex` 崩溃复发。改成 `node copy-worker.mjs`（永远复制 `legacy/build/` 的 worker）堵住。

### 区别 / 为什么 / 能否学 LaTeX-Workshop

| 维度 | LaTeX-Workshop | jujuleaf |
|---|---|---|
| 怎么用 pdf.js | 整包托管它**自带的 stock viewer** | 当**库** import，自研 viewer |
| 分发 | Node HTTP server 按 URL 路由，直接从 `node_modules` 提供 | esbuild 打包 app；worker **拷进 `public/`** 静态托管 |
| "选 legacy" 的开关 | **一处**：server 路由 `/build/` → `pdfjs-dist/legacy/` | **两处**：主线程 import legacy + `copy-worker.mjs` 拷 legacy worker |
| 额外 polyfill | 无（全靠 legacy 的 core-js） | 有（手写，基本冗余的双保险） |
| 回归面 | 几乎为零（单一来源） | 拷贝步骤可能拷错版本（= `b896582` 在防的） |

**为什么不同**：根在"消费 pdf.js 的形态"。LaTeX-Workshop 把它当**成品查看器整包**托管，"用哪个 build"只是"server 把 `/build/` 指到哪个目录"——一个路由开关，天然单一来源。jujuleaf 把它当**库** import 进自研 viewer：主线程交给 esbuild 构建期定死 legacy，但 **worker 是独立脚本、只能按 URL 加载，打包器管不到**，只能落成 `public/` 里的文件——于是多出 copy 这一步，"用哪个 build"退化成"拷贝源路径"，也就多了拷错的可能。手写 polyfill 多半是历史顺序（先在 standard 上救急，后切 legacy），legacy 已自带 core-js polyfill，所以现在冗余。

**能否学**：能，更干净，属可选的健壮性重构。jujuleaf 本就常驻 express，可加一条路由直接从 `node_modules/pdfjs-dist/legacy/build` 提供 worker（甚至整个 pdfjs），删掉 `copy-worker.mjs`，**从根上消除"拷错 build"这一类回归**；升级 pdfjs 自动生效。代价：想在 worker 里继续装 polyfill 就保留 wrapper；legacy 已 polyfill，手写 polyfill 变可选保险（要删得在真·旧浏览器上验）；路由要求 server 常驻（jujuleaf 的 API server 本就必须常驻，无损）。当前"拷进 public/"的唯一好处是 public/ 可被任意纯静态托管——没有纯静态部署打算就用不上。

---

## 排查 / 诊断技巧

- **判断某个 pdfjs 是否 broken（最快）**：`grep -A1 'Uint8Array.prototype.toHex' node_modules/pdfjs-dist/build/pdf.worker.mjs`，看不到 `if` 守卫就是 broken。比翻 changelog 快。

  ```js
  // 安全（旧版还有）：            // 不安全（新版拿掉了）：
  if (Uint8Array.prototype.toHex)   xxx.toHex()   // 直接调用
    return arr.toHex()
  return Array.from(arr, ...).join("")
  ```

- **确认自己在发哪个 build**：standard 在 `pdfjs-dist/build/`，legacy 在 `pdfjs-dist/legacy/build/`。托管/拷贝/import 的路径带不带 `legacy/` 就是全部区别。文件大小也能一眼区分（legacy worker 明显更大，因为塞了 core-js）。
- **最新 headless/Electron 会掩盖问题**：Chrome 140+ 原生支持这些方法（145 起还有 `Map.getOrInsertComputed`、147 起 `Math.sumPrecise`），本机新 Chrome/Playwright 跑不出错。**必须在真·旧浏览器上验**。
- **v6 standard 不只依赖 toHex**：还用 `Map.getOrInsertComputed`、`Math.sumPrecise`、`Promise.try` 等更晚落地的 API。所以只补 6 个 Uint8Array 方法**救不了 standard**，legacy build 才是完整解。
- **选型**：目标 Chrome 125+（pdf.js v6 官方支持范围）→ 钉 `pdfjs-dist@6.1.200` + 全 legacy（jujuleaf 现状）。若必须支持 Chrome 103–124 → 钉最后一个 v4 `4.10.38` + legacy。

### 附：旧的"回退式 workaround"（已被官方 legacy 方案取代，保留备查）

mess 首记当时（官方修复未出）走的是**降级 + 成套回退**路线，针对 LaTeX-Workshop 这类"整包 stock viewer"扩展，要点：

1. 找个 pdfjs 安全的旧版扩展（实测 `latex-workshop 10.13.1` 自带 `pdfjs-dist 5.4.394`，有 fallback）。VSCode serve-web "Install from VSIX" 报 `Extension not found` 时，**绕过**：直接 curl marketplace API `https://marketplace.visualstudio.com/_apis/public/gallery/publishers/<pub>/vsextensions/<ext>/<ver>/vspackage`（`curl --compressed` 拿 gzipped vsix，本质 zip，`unzip` 解开）。
2. 成套替换 pdfjs 静态资源：`viewer/{viewer.mjs,viewer.html,viewer.css,locale,images}` + `node_modules/pdfjs-dist/`；**保留** `viewer/latexworkshop.css`。
3. **同步回退 overlay**：`out/viewer/components/{gui,interface,refresh,state}.js` 也要用旧 vsix 覆盖——pdfjs upstream 把 sidebar 改名成 viewsManager（`sidebarToggleButton`→`viewsManagerToggleButton`，commit `ed96911a`），旧 `viewer.html` 配新 overlay 会崩 `Cannot read properties of null (reading 'nextElementSibling') at patchViewerUI`。其余 6 个 components（connection/l10n/synctex/trimming/utils/viewerhistory）别动。
4. Reload Window 验证。

> **这条路线现已过时**：LaTeX-Workshop `a248e2a1` 之后官方直接用 legacy build，不再需要降级。新遇到同类问题**优先切 legacy build**，别再降级。

---

## 教训

- **旧浏览器的官方解永远是 legacy build**（Babel + core-js 转译版），不是降级、也不是自己手写 polyfill。先查上游 README/FAQ 有没有 legacy 版再动手。
- **"托管/打包/import 了哪个 build" 是这类事故的唯一开关**：standard(`build/`) 崩、legacy(`legacy/build/`) 安全。LaTeX-Workshop 用路由切、jujuleaf 用拷贝切，失误点都在这一处。
- **upstream merge / 整包回退类操作不要假设"只动了 X"**：stock viewer 的静态资源、element id rename、overlay 适配是一体的，回退也必须一体（`git log A..B -- path/` 比 `git diff` 更能看出哪些是纯 rename 适配 commit）。
- **本机新浏览器会骗你**：一定在目标旧环境上复现和验证。
