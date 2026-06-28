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
- **VS Code 1.119 CLI launcher 拒绝 WebSocket upgrade（hyper 0.14→1.x 漏改 `with_upgrades`，`localhost` 直连也炸）** → [references/bug-fix.md](references/bug-fix.md)
  - 关键词：`code serve-web`、`Time limit reached`、`The workbench failed to connect to the server`、`upgrade expected but low level API in use`、`websocket upgrade failed`、`hyper`、`hyper-util`、`serve_connection_with_upgrades`、`localhost 也不行`、`reverse proxy ws 卡死`、`reconnectionToken 死循环`、`1.119 vs 1.115`、`commit 8b640eef`、`commit 41dd792b`、`code-tunnel`、`pin 旧版 cli`、`Microsoft VS Code Issue #315448`、`#315003`
- **PDF.js v5.5+ 在 Chrome < 140 上崩溃 (`Uint8Array.toHex` polyfill 缺失)** → [references/bug-fix.md](references/bug-fix.md)
  - 关键词：`hashOriginal.toHex is not a function`、`Uint8Array.toHex`、`pdfjs-dist`、`PDF.js v5.6.205`、`htbrowser`、`Chrome 132`、`viewer.mjs:24251`、`pdf.mjs:428`、`patchViewerUI`、`viewsManagerToggleButton`、`sidebarToggleButton`、`LaTeX-Workshop PDF 预览全白`、`merge upstream 后浏览器打不开 PDF`
- **Windows 端口绑定异常但 Win/WSL 都查不到占用，`wsl --shutdown` 后恢复** → [references/bug-fix.md](references/bug-fix.md)
  - 关键词：`os error 10048`、`端口占用但 netstat 查不到`、`Get-NetTCPConnection 查不到`、`ss 查不到`、`excludedportrange 没有`、`wsl --shutdown`
- **Windows 普通 PowerShell 创建文件 symlink 失败，给用户授予 `SeCreateSymbolicLinkPrivilege` 后恢复** → [references/bug-fix.md](references/bug-fix.md)
  - 关键词：`Administrator privilege required`、`mklink`、`You do not have sufficient privilege`、`SeCreateSymbolicLinkPrivilege`、`Create symbolic links`、`secedit 扩展错误`、`*SID`、`Developer Mode`、`AGENTS.md`、`CLAUDE.md`
- **公网 VPS 做 UDP 端口段转发到内网地址时，启用 `nftables.service` 影响 Caddy HTTPS/TCP 服务** → [references/bug-fix.md](references/bug-fix.md)
  - 关键词：`UDP 转发`、`端口段转发`、`DNAT`、`masquerade`、`nftables.service`、`nft flush ruleset`、`Caddy HTTPS 断了`、`gost udp://`、`11000-11009`
- **WSL2 NAT：同机宿主机能连自建服务、内嵌 WSL 连不上（fake-ip），切 Mihomo TUN off→on 后 WSL 恢复（根因未坐实）** → [references/bug-fix.md](references/bug-fix.md)
  - 关键词：`只有 WSL 不通`、`宿主机通 WSL 不通`、`fake-ip`、`198.18.x`、`Mihomo TUN`、`dns-hijack`、`Connection timed out during banner exchange`、`getent 解析 fake-ip`、`route-exclude-address`、`DomainSuffix 直连`、`9090 PATCH /configs tun enable`、`切 TUN 后 mesh 抖动`、`EasyTier mesh 短断`、`portal/ssh 长连接僵尸`、`自建 Forgejo ssh.git`、`git fetch 超时 rc=124`
- **Synology DSM Container Manager：短时间多次 recreate 触发 `failed to initialize logging driver: database is blocked`（DSM 魔改 docker 的 sqlite WAL lock）** → [references/nas.md](references/nas.md)
  - 关键词：`failed to initialize logging driver`、`database is blocked`、`DSM Container Manager`、`Synology docker`、`json-file driver`、`SQLite WAL lock`、`短时间多次 recreate`、`/var/packages/ContainerManager`、`/volume1/@docker`、`logging driver` (docker daemon 概念,不是应用日志)、`停用启用 Container Manager`、`卸载 named volume 风险`
- **「总是断网」：很可能是 WSL 内 EasyTier 节律性搞坏整网（挪宿主机后解决）；附 ping 网关 ≠ 断网（CoPP）、分源 IP 绑定分链路排查** → [references/bug-fix.md](references/bug-fix.md)
  - 关键词：`总是断网`、`WSL 内 EasyTier 节律性搞坏整网`、`挪宿主机解决`、`ping 网关 100% 丢包但能上网`、`CoPP 控制平面限速`、`ICMP rate limit`、`ping 网关不是断网指标`、`WSL2 mirrored networking`、`分源 IP 绑定测试`、`TcpClient Bind 源地址`、`strong host model`、`ping -I / curl --interface 分链路`、`断窗时长恒定 ~5 分钟`、`EasyTier peer removed 反推通断`

> Copilot CLI 相关的调研笔记已迁移到 `harness` skill（包括 bash 工具 env 黑名单、`COPILOT_ALLOW_ALL` vs `--yolo`、`/rewind` 非 git 拒绝、Walk-Up（向上查找）机制总览、Custom Instructions（AGENTS.md / `.github/instructions` 嵌套查找）、Safety Net 双 bug、项目级 hook 不向上查、`.mcp.json` 上溯停在 git root、`.mcp.json` headers `${VAR}` 不展开、Skills 发现、`GIT_CONFIG_COUNT` 注入 credential helper、`gh repo fork` SSH 身份错配、Copilot SDK 与 session export 等）。
