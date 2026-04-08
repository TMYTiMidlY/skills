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
