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
- **Windows 端口绑定异常但 Win/WSL 都查不到占用，`wsl --shutdown` 后恢复** → [references/bug-fix.md](references/bug-fix.md)
  - 关键词：`os error 10048`、`端口占用但 netstat 查不到`、`Get-NetTCPConnection 查不到`、`ss 查不到`、`excludedportrange 没有`、`wsl --shutdown`
- **Windows 普通 PowerShell 创建文件 symlink 失败，给用户授予 `SeCreateSymbolicLinkPrivilege` 后恢复** → [references/bug-fix.md](references/bug-fix.md)
  - 关键词：`Administrator privilege required`、`mklink`、`You do not have sufficient privilege`、`SeCreateSymbolicLinkPrivilege`、`Create symbolic links`、`secedit 扩展错误`、`*SID`、`Developer Mode`、`AGENTS.md`、`CLAUDE.md`
- **公网 VPS 做 UDP 端口段转发到内网地址时，启用 `nftables.service` 影响 Caddy HTTPS/TCP 服务** → [references/bug-fix.md](references/bug-fix.md)
  - 关键词：`UDP 转发`、`端口段转发`、`DNAT`、`masquerade`、`nftables.service`、`nft flush ruleset`、`Caddy HTTPS 断了`、`gost udp://`、`11000-11009`

## Copilot CLI

- **`BASH_ENV` 注入只对非交互 bash 生效（agent 直跑命令拿不到 `GH_TOKEN`）** → [references/copilot.md](references/copilot.md)
  - 关键词：`BASH_ENV`、`.copilot.env`、`gh api user`、`错的账号`、`Copilot CLI bash 工具`、`非交互 bash`、`source .copilot.env`、`bash -c`
- **Safety Net plugin 安装后从不触发（plugin schema 是 Claude Code 格式 + marketplace plugin hook 不加载）** → [references/copilot.md](references/copilot.md)
  - 关键词：`Safety Net`、`copilot-safety-net`、`cc-safety-net`、`hooks.json`、`PreToolUse`、`preToolUse`、`matcher Bash`、`COPILOT_ALLOW_ALL`、`--allow-all-tools`、`rm -rf 没拦`、`git reset --hard 没拦`、`Loaded 1 hook(s)`、`copilot-cli#2540`、`.github/hooks/safety-net.json`
- **项目级 hook 不会向上查父目录，多 git repo 工作区里子项目漏装 Safety Net** → [references/copilot.md](references/copilot.md)
  - 关键词：`getHooksDir`、`gitRoot`、`hook 不触发`、`子项目 hook 没加载`、`monorepo`、`.github/hooks 向上查找`、`user-level hook`、`~/.copilot/config/hooks`、`direnv symlink`、`ensure_safety_net_symlinks`、`.git/info/exclude`、`direnv allow`
