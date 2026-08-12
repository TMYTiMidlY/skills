---
name: mess
description: 遇到疑难杂症、相似报错或想回顾既有排障经验时使用。按症状和关键词检索已记录案例，并把新问题的复现、根因和可靠解法沉淀下来。
---

# Mess — 疑难杂症档案

记录排查过程中走过的弯路、最终定位的根因、以及解决方案。每个案例都是一次完整的排查故事，重点不是答案本身，而是**怎么找到答案的**。

遇到用户报告的问题与已有案例相似时，先回顾对应 reference，避免重复走弯路。

## 案例索引

每条给出「症状 → 根因」一句话与直达该案例的链接；关键词只列判别力最强的几个，命中后进对应 reference 看全貌。

### `code serve-web`

见 [code-serve-web.md](references/code-serve-web.md)。

- **页面空白，Console 报 NLS MISSING** → 服务端按 `Accept-Language` 注入的中文语言包比英文短，覆盖后高位 index 取不到而抛异常；换个 IP 能用只是因为它请求 CDN 恰好失败 → [直达](references/code-serve-web.md#nls-blank)
  - 关键词：`NLS MISSING`、`nls.messages.js`、`_VSCODE_NLS_MESSAGES`、`Accept-Language`、`127.0.0.1 能用但另一个 IP 不行`、`页面空白`
- **workbench 连不上 server，WebSocket 握手后即断** → 1.119 的 CLI launcher 把 hyper 0.14 升到 1.x，反代那段漏改成 `serve_connection_with_upgrades`；`localhost` 直连一样炸，与反代无关 → [直达](references/code-serve-web.md#ws-upgrade-1119)
  - 关键词：`Time limit reached`、`The workbench failed to connect to the server`、`upgrade expected but low level API in use`、`serve_connection_with_upgrades`、`reconnectionToken 死循环`、`1.119 vs 1.115`

### Windows 宿主机

见 [windows.md](references/windows.md)。

- **端口绑定报 10048，但 Windows / WSL 都查不到占用** → WSL/Hyper-V localhost forwarding 层的状态残留，普通进程列表看不见；`wsl --shutdown` 重建网络栈即恢复 → [直达](references/windows.md#bind-10048)
  - 关键词：`os error 10048`、`端口占用但 netstat 查不到`、`Get-NetTCPConnection 查不到`、`excludedportrange 没有`、`wsl --shutdown`
- **固定服务端口绑定报 `WSAEACCES`(10013)，且随开机漂移** → 端口落在 Hyper-V 开机时从动态段（49152–65535）圈走的独占保留块里，块位置每次开机现圈；根治是改用低端口 → [直达](references/windows.md#bind-10013)
  - 关键词：`WSAEACCES`、`os error 10013`、`excludedportrange 里有`、`49694-49793`、`Hyper-V 端口保留`、`保留段每次开机漂移`、`mixed-port 起不来`
- **普通 PowerShell 创建文件 symlink 失败** → 文件 symlink 需要 `SeCreateSymbolicLinkPrivilege`；目录能装只是因为走了 junction，文件没有 junction 可用 → [直达](references/windows.md#symlink-privilege)
  - 关键词：`Administrator privilege required`、`You do not have sufficient privilege`、`SeCreateSymbolicLinkPrivilege`、`secedit 扩展错误`、`*SID`、`Developer Mode`

### WSL2

见 [wsl.md](references/wsl.md)。

- **同机 Windows 宿主能连自建服务、内嵌 WSL 连不上** → 两侧都解析到 Mihomo fake-ip，只有 WSL 侧超时；把 TUN off→on 切一遍后 WSL 稳定可通，机制未坐实 → [直达](references/wsl.md#host-ok-wsl-fail)
  - 关键词：`只有 WSL 不通`、`宿主机通 WSL 不通`、`fake-ip`、`198.18.x`、`Connection timed out during banner exchange`、`9090 PATCH /configs tun enable`
- **「总是断网」：断窗恒定 ~5 分钟的周期性中断** → 较可能是 WSL 内跑 EasyTier 在周期性作祟（挪到宿主机后不再犯）；排查中被 `ping 网关` 丢包（CoPP 限速）误导过 → [直达](references/wsl.md#periodic-outage)
  - 关键词：`总是断网`、`ping 网关 100% 丢包但能上网`、`CoPP 控制平面限速`、`断窗时长恒定 ~5 分钟`、`分源 IP 绑定测试`、`WSL 内跑 EasyTier`
- **user session bus 消失，`systemctl --user` 连不上** → `/run/user/1000/bus` 不见了而 manager 还活着；补 bus 无用，须对 manager 发 reexec 信号，代价是 running user services 可能中断 → [直达](references/wsl.md#user-bus-missing)
  - 关键词：`Failed to connect to bus`、`/run/user/1000/bus`、`DBUS_SESSION_BUS_ADDRESS`、`dbus-daemon --session`、`kill -RTMIN+25`、`running user services 断开`

### Linux（服务器 / 容器 / 工具链）

见 [linux.md](references/linux.md)。

- **公网 VPS 做 UDP 端口段转发后，Caddy 的 HTTPS/TCP 中断** → 为一小段 UDP 转发启用了会接管整个 ruleset 的 `nftables.service`；改用 GOST 独立 service 不碰 nft → [直达](references/linux.md#nftables-breaks-caddy)
  - 关键词：`nftables.service`、`nft flush ruleset`、`Caddy HTTPS 断了`、`UDP 端口段转发`、`gost udp://`、`nc -uvz 不可信`
- **容器解析不了 compose 服务名，IP 直连正常** → 存量 bridge 网络的内置 DNS（`127.0.0.11`）状态损坏，新建网络正常；`docker compose down/up` 重建网络即修复 → [直达](references/linux.md#docker-embedded-dns)
  - 关键词：`127.0.0.11`、`hostname resolving error`、`no such host`、`getent hosts 失败但 IP 直连通`、`存量网络 DNS 损坏`、`tried to kill container, but did not receive an exit event`
- **子仓库 `git status` 冒出几十个 untracked 分发软链** → 手动 `source` 工作区 `.envrc` 让 `$PWD` 停在子仓库，链铺深一层；而 `core.excludesFile` 里含斜杠的 pattern 是 anchored、只挡仓库根那层 → [直达](references/linux.md#envrc-subdir-links)
  - 关键词：`.envrc`、`direnv`、`link_into_subdirs`、`core.excludesFile`、`gitignore 含斜杠 anchored`、`check-ignore NOT ignored`、`BASH_SOURCE guard`

### NAS / Synology

见 [nas.md](references/nas.md)。

- **DSM Container Manager 报 `failed to initialize logging driver: database is blocked`** → DSM 魔改 docker 用来跟踪容器元数据的 SQLite 撞 WAL lock，跟应用层和你改的 compose 都无关；等一两分钟或停用再启用套件 → [直达](references/nas.md#dsm-logging-driver)
  - 关键词：`failed to initialize logging driver`、`database is blocked`、`DSM Container Manager`、`SQLite WAL lock`、`短时间多次 recreate`、`卸载 named volume 风险`
- **Postgres 崩溃恢复卡在 end-of-recovery checkpoint 不动** → 不是卡死，是 NAS iSCSI LUN 上单个文件 fsync 能耗时 9 分钟；`Ds` 状态 + BlockIO 计数器不变无法区分"卡死"与"巨慢" → [直达](references/nas.md#pg-checkpoint-slow)
  - 关键词：`end-of-recovery checkpoint`、`Ds 状态`、`docker stats BlockIO 不变`、`checkpoint complete sync=727s`、`WAL fsync 慢`、`误判为死锁`
- **NAS 换 IP 后 iSCSI LUN 连不上** → portal 改了仍超时，因为持久化目标条目单独记着旧地址、不随 portal 更新；附端口探测在 TUN 下的假阳性、ARP 不可达被误判成设备关机 → [直达](references/nas.md#iscsi-ip-change)
  - 关键词：`已经通过 iSCSI 会话登录目标`、`HRESULT 0xefff003f`、`iscsicli ListPersistentTargets`、`ClearPersistentTargets`、`Test-NetConnection 假阳性`、`ARP Unreachable 误判关机`、`不要 Initialize-Disk`

### 浏览器端 PDF 预览

见 [pdfjs-tohex.md](references/pdfjs-tohex.md)。

- **旧浏览器打开 PDF 全白，报 `hashOriginal.toHex is not a function`** → pdf.js 从 `5.4.624` 起删掉了 `Uint8Array.prototype.toHex` 的手写 fallback，standard build 无条件依赖这个很新的 TC39 API；官方唯一正解是改用 legacy build，不是降级也不是自己写 polyfill → [直达](references/pdfjs-tohex.md#symptom)
  - 关键词：`hashOriginal.toHex is not a function`、`Uint8Array.toHex`、`pdfjs-dist`、`legacy build`、`legacy/build/pdf.worker.min.mjs`、`PDF 预览全白`

> Copilot CLI 相关的调研笔记已迁到 `harness` skill（bash 工具 env 黑名单、`COPILOT_ALLOW_ALL` vs `--yolo`、`/rewind` 非 git 拒绝、Walk-Up（向上查找）机制、Custom Instructions、Safety Net 双 bug、项目级 hook 不向上查、`.mcp.json` 上溯与 `${VAR}` 不展开、Skills 发现、`GIT_CONFIG_COUNT` 注入 credential helper、`gh repo fork` SSH 身份错配、Copilot SDK 与 session export 等）。opusplan 模式的模型切换与上下文缓存分析同样已迁往 `harness` skill。
