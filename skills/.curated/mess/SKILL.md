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
- **PDF.js `Uint8Array.toHex` 兼容性事故：旧浏览器崩溃 + 官方 legacy build 修复（jujuleaf / LaTeX-Workshop）** → [references/pdfjs-tohex.md](references/pdfjs-tohex.md)
  - 关键词：`hashOriginal.toHex is not a function`、`Uint8Array.toHex`、`Uint8Array.prototype.toHex`、`proposal-arraybuffer-base64`、`pdfjs-dist`、`pdf.mjs:428`、`viewer.mjs:24251`、`Chrome 140`、`Chrome 132`、`Chrome 125+`、`Firefox 133`、`Safari 18.2`、`htbrowser`、`legacy build`、`generic-legacy`、`legacy/build/pdf.worker.min.mjs`、`core-js`、`standard 覆盖 legacy`、`copy-worker.mjs`、`pdfjs-dist@6.1.200`、`5.4.624`、`5.4.530`、`5b368dd`、`LaTeX-Workshop a248e2a1`、`#4851`、`#4867`、`#4882`、`server.ts /build/ → pdfjs-dist/legacy/`、`jujuleaf`、`自研 PDF.js 预览`、`LaTeX-Workshop PDF 预览全白`、`viewsManagerToggleButton`、`sidebarToggleButton`、`patchViewerUI`、`merge upstream 后浏览器打不开 PDF`
- **Windows 端口绑定异常但 Win/WSL 都查不到占用，`wsl --shutdown` 后恢复** → [references/bug-fix.md](references/bug-fix.md)
  - 关键词：`os error 10048`、`端口占用但 netstat 查不到`、`Get-NetTCPConnection 查不到`、`ss 查不到`、`excludedportrange 没有`、`wsl --shutdown`
- **Windows 固定服务端口落在 Hyper‑V 临时端口保留段 → 绑定 `WSAEACCES`(10013)、随开机漂移（Clash Verge mihomo `mixed-port:49760` 起不来）** → [references/bug-fix.md](references/bug-fix.md)
  - 关键词：`WSAEACCES`、`os error 10013`、`AccessDenied`、`bind 失败但不是 10048`、`excludedportrange 里有`、`49694-49793`、`动态端口段 49152-65535`、`ephemeral port`、`dynamicportrange`、`Hyper-V 端口保留`、`HNS`、`WinNAT`、`vmcompute`、`保留段每次开机漂移`、`启动抢占赛`、`时好时坏`、`之前能用现在不行`、`Clash Verge Rev`、`verge-mihomo`、`mixed-port 起不来`、`只剩 redir 7892 + dns 53`、`ProxyServer=127.0.0.1:49760`、`ProxyEnable=0`、`系统代理残留`、`Docker Desktop system proxy`、`WSL2 mirrored`、`wslinfo networking-mode`、`改低端口 <49152`、`49000`、`7888`
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
- **WSL user systemd 的 session bus 突然消失，`systemctl --user` 连不上；临时 bus + manager reexec 可恢复，但会中断 running user services** → [references/bug-fix.md](references/bug-fix.md)
  - 关键词：`systemctl --user`、`Failed to connect to bus`、`/run/user/1000/bus`、`DBUS_SESSION_BUS_ADDRESS`、`dbus-daemon --session`、`kill -RTMIN+25`、`daemon-reexec`、`systemd --user`、`running user services 断开`
- **Docker 内置 DNS（127.0.0.11）对存续已久的网络失效，新建网络正常（forgejo/dmp/qatlas-postgres 三个项目同时中招，根因未坐实）** → [references/bug-fix.md](references/bug-fix.md)
  - 关键词：`Docker 内置 DNS`、`127.0.0.11`、`no such host`、`hostname resolving error`、`lookup db`、`getent hosts` 解析失败但 IP 直连通、`docker network create` 新网络正常、存量网络 DNS 损坏、`docker compose down/up` 重建网络修复、`tried to kill container, but did not receive an exit event`、`docker kill` 被 bash 工具拦截、Forgejo 500 内部错误、Docker Desktop WSL2 睡眠唤醒
- **Postgres 崩溃恢复卡在 checkpoint「像是死了」，其实是 NAS iSCSI LUN 上的 fsync 巨慢（不是真卡死，诊断方法本身有局限）** → [references/nas.md](references/nas.md)
  - 关键词：`Postgres checkpoint 卡住`、`end-of-recovery checkpoint`、`Ds 状态`、`不可中断磁盘睡眠`、`docker stats BlockIO 不变`、`iSCSI LUN`、`NAS-backed 存储`、`WAL fsync 慢`、`wsl --mount`、`崩溃恢复耗时长`、`checkpoint complete sync=727s`、`误判为死锁`、`pg_isready`、`大表 + 慢速存储 checkpoint 正常耗时`
- **手动 `source` 工作区 `.envrc` → symlink 分发钻进子仓库每个子目录；配 anchored `core.excludesFile` 只挡根层而漏进 `git status`** → [references/bug-fix.md](references/bug-fix.md)
  - 关键词：`.envrc`、`direnv`、`手动 source 从子目录`、`link_into_subdirs`、`$PWD 被错设`、`BASH_SOURCE guard`、`pwd -P`、`core.excludesFile`、`gitignore 含斜杠 anchored`、`check-ignore NOT ignored`、`.mcp.json 反而被忽略`、`symlink 分发深一层`、`.agents/skills`、`.github/instructions`、`git status 大量 untracked`、`测试假象 [[ -e "$src" ]] 早退`

> Copilot CLI 相关的调研笔记已迁移到 `harness` skill（包括 bash 工具 env 黑名单、`COPILOT_ALLOW_ALL` vs `--yolo`、`/rewind` 非 git 拒绝、Walk-Up（向上查找）机制总览、Custom Instructions（AGENTS.md / `.github/instructions` 嵌套查找）、Safety Net 双 bug、项目级 hook 不向上查、`.mcp.json` 上溯停在 git root、`.mcp.json` headers `${VAR}` 不展开、Skills 发现、`GIT_CONFIG_COUNT` 注入 credential helper、`gh repo fork` SSH 身份错配、Copilot SDK 与 session export 等）。
