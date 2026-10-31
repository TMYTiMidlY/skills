---
name: mess
description: 遇到疑难杂症、相似报错或想回顾既有排障经验时使用。按症状和关键词检索已记录案例，并把新问题的复现、根因和可靠解法沉淀下来。
---

# Mess — 疑难杂症档案

记录排查过程中走过的弯路、最终定位的根因、以及解决方案。每个案例都是一次完整的排查故事，重点不是答案本身，而是**怎么找到答案的**。

收录标准看问题是否低频、难复现，以及排查路径是否值得复用，不按操作系统、软件类型或技术领域划边界。某个领域即使另有系统知识库，其中偶发而棘手的具体案例仍可收录在这里。

遇到用户报告的问题与已有案例相似时，先回顾对应 reference，避免重复走弯路。

## 案例索引

每条给出「症状 → 根因」一句话与直达该案例的链接；关键词只列判别力最强的几个，命中后进对应 reference 看全貌。

### `code serve-web`

见 [code-serve-web.md](references/code-serve-web.md)。

- **页面空白，Console 报 NLS MISSING** → 服务端按 `Accept-Language` 注入的中文语言包比英文短，覆盖后高位 index 取不到而抛异常；换个 IP 能用只是因为它请求 CDN 恰好失败 → [直达](references/code-serve-web.md#nls-blank)
  - 关键词：`NLS MISSING`、`nls.messages.js`、`_VSCODE_NLS_MESSAGES`、`Accept-Language`、`127.0.0.1 能用但另一个 IP 不行`、`页面空白`
- **workbench 连不上 server，WebSocket 握手后即断** → 1.119 的 CLI launcher 把 hyper 0.14 升到 1.x，反代那段漏改成 `serve_connection_with_upgrades`；`localhost` 直连一样炸，与反代无关 → [直达](references/code-serve-web.md#ws-upgrade-1119)
  - 关键词：`Time limit reached`、`The workbench failed to connect to the server`、`upgrade expected but low level API in use`、`serve_connection_with_upgrades`、`reconnectionToken 死循环`、`1.119 vs 1.115`
- **页面永远卡在 "The latest version of the VS Code Server is downloading"** → serve-web 跟踪 latest，CLI 无续传；2026-09-03 的 CDN 坏对象经播种缓存恢复，9 月 9 日旧缓存仍在却因追新版再现 202（本次未证实坏对象）。可[固定下次启动 commit](references/code-serve-web.md#web-pin-launch)，或[固定旧缓存入口](references/code-serve-web.md#web-pin-entry)避开等待，生效时机与任务风险不同 → [案例](references/code-serve-web.md#web-tarball-cdn-stall)
  - 关键词：`Downloading server`、`HTTP 202 占位页`、`server-linux-x64-web`、`curl -C -`、`--commit-id`、`stable-<commit>`、`KillMode=control-group`、`Caddy 首页 rewrite`、`保留 folder`
- **Codex 扩展报 `command 'chatgpt.openSidebar' not found`，重装无效** → openai.chatgpt 26.917 起硬依赖 `openai.codex-audio`（`extensionKind: ["ui"]`、无 browser 入口），纯 Web 窗口没有 UI 扩展宿主，依赖边连成的整组被静默排除出扩展列表；删掉已装扩展 package.json 里的 `extensionDependencies` 即恢复 → [直达](references/code-serve-web.md#chatgpt-opensidebar-dep)
  - 关键词：`chatgpt.openSidebar`、`command not found`、`openai.codex-audio`、`extensionDependencies`、`extensionKind ui`、`serve-web 扩展不激活`、`无 _doActivateExtension`、`全新浏览器无图标`

### Windows 宿主机

见 [windows.md](references/windows.md)。

- **端口绑定报 10048，但 Windows / WSL 都查不到占用** → WSL/Hyper-V localhost forwarding 层的状态残留，普通进程列表看不见；`wsl --shutdown` 重建网络栈即恢复 → [直达](references/windows.md#bind-10048)
  - 关键词：`os error 10048`、`端口占用但 netstat 查不到`、`Get-NetTCPConnection 查不到`、`excludedportrange 没有`、`wsl --shutdown`
- **固定服务端口绑定报 `WSAEACCES`(10013)，且随开机漂移** → 端口落在 Hyper-V 开机时从动态段（49152–65535）圈走的独占保留块里，块位置每次开机现圈；根治是改用低端口 → [直达](references/windows.md#bind-10013)
  - 关键词：`WSAEACCES`、`os error 10013`、`excludedportrange 里有`、`49694-49793`、`Hyper-V 端口保留`、`保留段每次开机漂移`、`mixed-port 起不来`
- **普通 PowerShell 创建文件 symlink 失败** → 文件 symlink 需要 `SeCreateSymbolicLinkPrivilege`；目录能装只是因为走了 junction，文件没有 junction 可用 → [直达](references/windows.md#symlink-privilege)
  - 关键词：`Administrator privilege required`、`You do not have sufficient privilege`、`SeCreateSymbolicLinkPrivilege`、`secedit 扩展错误`、`*SID`、`Developer Mode`
- **受管客户端在 RDP 中白屏，ToDesk 黑屏且 KimiCU 截图失败** → 客户端分别通过 `SetVisible(false)` 隐藏网页视图、通过 `SetWindowDisplayAffinity` 排除捕获 → [案例](references/windows.md#managed-client-display)
  - 关键词：`RDP 白屏`、`ToDesk 黑屏`、`KimiCU`、`WGC`、`PrintWindow`、`WDA_EXCLUDEFROMCAPTURE`、`SetVisible`

### WSL2

见 [wsl.md](references/wsl.md)。

- **同机 Windows 宿主能连自建服务、内嵌 WSL 连不上** → 两侧都解析到 Mihomo fake-ip，只有 WSL 侧超时；把 TUN off→on 切一遍后 WSL 稳定可通，机制未坐实 → [直达](references/wsl.md#host-ok-wsl-fail)
  - 关键词：`只有 WSL 不通`、`宿主机通 WSL 不通`、`fake-ip`、`198.18.x`、`Connection timed out during banner exchange`、`9090 PATCH /configs tun enable`
- **「总是断网」：断窗恒定 ~5 分钟的周期性中断** → 较可能是 WSL 内跑 EasyTier 在周期性作祟（挪到宿主机后不再犯）；排查中被 `ping 网关` 丢包（CoPP 限速）误导过 → [直达](references/wsl.md#periodic-outage)
  - 关键词：`总是断网`、`ping 网关 100% 丢包但能上网`、`CoPP 控制平面限速`、`断窗时长恒定 ~5 分钟`、`分源 IP 绑定测试`、`WSL 内跑 EasyTier`
- **user session bus 消失，`systemctl --user` 连不上** → `/run/user/1000/bus` 不见了而 manager 还活着；补 bus 无用，须对 manager 发 reexec 信号，代价是 running user services 可能中断 → [直达](references/wsl.md#user-bus-missing)
  - 关键词：`Failed to connect to bus`、`/run/user/1000/bus`、`DBUS_SESSION_BUS_ADDRESS`、`dbus-daemon --session`、`kill -RTMIN+25`、`running user services 断开`
- **Git 引用和对象变成空文件，Zellij 配了 Caddy session token 仍登录失败** → 同次故障中 Windows 宿主 C 盘满，WSL 重启后需恢复 Git 文件并检查 Zellij token 数据库 → [直达](references/wsl.md#host-disk-full-git-zellij)
  - 关键词：`C 盘满`、`WSL df 还有空间`、`Git 空对象`、`零字节引用`、`tokens.db`、`Caddy session_token`
- **「组网正常却入口全断」：WSL 服务握手即断、502 与守护进程成批死亡** → 宿主卷余量饿死动态 VHDX，guest ext4 收 EIO 成批团灭守护进程；干净重启靠 journal 回放自愈。含无密码跨用户修复通道与 vmIdleTimeout 陷阱 → [直达](references/wsl.md#vhdx-host-starvation)
  - 关键词：`kex_exchange_identification`、`Connection closed by remote host`、`portproxy 后端假活`、`wslrelay`、`getpwnam(root) failed 5`、`WSL_E_USER_NOT_FOUND`、`EIO 不是 ENOSPC`、`VHDX 断供`、`fstrim`、`vmIdleTimeout`、`跨用户 WSL CreateProcessAsUser`、`S4U Access denied`

### Linux（服务器 / 容器 / 工具链）

见 [linux.md](references/linux.md)。

- **公网 VPS 做 UDP 端口段转发后，Caddy 的 HTTPS/TCP 中断** → 为一小段 UDP 转发启用了会接管整个 ruleset 的 `nftables.service`；改用 GOST 独立 service 不碰 nft → [直达](references/linux.md#nftables-breaks-caddy)
  - 关键词：`nftables.service`、`nft flush ruleset`、`Caddy HTTPS 断了`、`UDP 端口段转发`、`gost udp://`、`nc -uvz 不可信`
- **容器解析不了 compose 服务名，IP 直连正常** → 存量 bridge 网络的内置 DNS（`127.0.0.11`）状态损坏，新建网络正常；`docker compose down/up` 重建网络即修复 → [直达](references/linux.md#docker-embedded-dns)
  - 关键词：`127.0.0.11`、`hostname resolving error`、`no such host`、`getent hosts 失败但 IP 直连通`、`存量网络 DNS 损坏`、`tried to kill container, but did not receive an exit event`
- **子仓库 `git status` 冒出几十个 untracked 分发软链** → 手动 `source` 工作区 `.envrc` 让 `$PWD` 停在子仓库，链铺深一层；而 `core.excludesFile` 里含斜杠的 pattern 是 anchored、只挡仓库根那层 → [直达](references/linux.md#envrc-subdir-links)
  - 关键词：`.envrc`、`direnv`、`link_into_subdirs`、`core.excludesFile`、`gitignore 含斜杠 anchored`、`check-ignore NOT ignored`、`BASH_SOURCE guard`
- **鉴权静态站子目录全 403，根目录文件正常，登录疑似失效** → 部署脚本 `mkdir` 继承 shell umask 0077 造出 0700 目录，Caddy `file_server` 对 EACCES 返回 403；forward_auth 让匿名探测永远 401，把真凶完全挡住 → [直达](references/linux.md#caddy-forwardauth-403-umask)
  - 关键词：`file_server 403`、`EACCES`、`forward_auth 掩蔽`、`umask 0077`、`子目录 0700`、`namei -l`、`Failed to fetch dynamically imported module`、`错误信息带状态码再排查`

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

- **旧浏览器打开 PDF 全白，报 `hashOriginal.toHex is not a function`（压缩构建里是 `n.toHex is not a function`）** → pdf.js 从 `5.4.624` 起删掉了 `Uint8Array.prototype.toHex` 的手写 fallback，standard build 无条件依赖这个很新的 TC39 API；官方唯一正解是改用 legacy build，不是降级也不是自己写 polyfill → [直达](references/pdfjs-tohex.md#symptom)
  - 关键词：`hashOriginal.toHex is not a function`、`n.toHex is not a function`、`Uint8Array.toHex`、`pdfjs-dist`、`legacy build`、`legacy/build/pdf.worker.min.mjs`、`PDF 预览全白`

### MinerU 转录（VLM）

见 [mineru-vlm.md](references/mineru-vlm.md)。

- **MinerU 转出的 full.md 里 grep 数字/常见单词命中率异常，逐字引用与原文对不上** → VLM 的静默误识四类（均已与 PDF 文本层对照坐实）：ff 连字系统性丢一个 f（全库 `eficient`×1650/`diferent`×1751）、LaTeX 数学环境内数字被空格拆散（`$1 0 2 4 0$`，精确 grep 全失效）、弯引号误认成上标 66/99（PDF 层字节是 U+201C/201D）、游离字符混入行内公式；pdftotext 错得张扬、VLM 错得沉默，两层互补，逐字引用回对 PDF → [直达](references/mineru-vlm.md#症状-fullmd-检索命中率异常逐字引用对不上)
  - 关键词：`full.md grep 不中`、`eficient`、`diferent`、`suficient`、`1 0 2 4 0`、`MinerU 错字`、`引号 66 99`、`ff 连字丢 f`、`VLM 静默错误`、`pdftotext 对照`

### Copilot CLI

见 [copilot-cli.md](references/copilot-cli.md)。

- **会话切换模型后，每轮都报 `400 Missing namespace for function_call`** → Copilot CLI 把 Anthropic 产生的 MCP 调用投影进通用历史时保留了 `mcpServerName` 的事件记录，却没有生成 OpenAI Responses 回放所需的 `functionCallNamespaces` 映射；随后请求在模型响应和 MCP 执行前即被 CAPI 拒绝 → [直达](references/copilot-cli.md#mcp-namespace-roundtrip)
  - 关键词：`Missing namespace for function_call`、`Round-trip the model's function_call item`、`functionCallNamespaces`、`mcpServerName`、`toolu_`、`sessionProjectionRewriteChatHistoryForModelJson`、`切换模型后 400`

### Codex CLI

见 [codex-usage-accounting.md](references/codex-usage-accounting.md)。

- **Terra 一夜的周额度增量高于历史 Sol，怀疑子代理或 500K 计费规则** → 实录显示请求更密、父侧协调负担增加；累计代理数、活动并发、token、账号额度与 API 等价费用需分别核算，子代理附加倍率及订阅扣减机制仍未证实 → [案例](references/codex-usage-accounting.md#overnight-quota-attribution)
  - 关键词：`token_usage_record`、`thread_token_usage`、`response_id 去重`、`Provider Hub quota-history`、`239 累计与 3 并发`、`272K API 与 500K 默认窗口`、`Sol 订阅长上下文豁免`

### DeepSeek Harness（dsh Web GUI）

见 [dsh.md](references/dsh.md)。

- **approval / ask_user_question 弹窗不出现、工具卡在等待，刷新页面才出现** → 重连后 mux 用原 rpcId 重放请求帧并先于 `onConnected` 被重新铸造，随后 `Session.resync()` 的 `pending.clear()` 把它抹掉；叠加无心跳的静默半开 WebSocket 作触发器；0.1.2-alpha.2 起整个机制删除重写 → [直达](references/dsh.md#interaction-card-missing)
  - 关键词：`approval 不弹出`、`ask_user_question 卡住`、`刷新后才出现`、`resync pending.clear`、`onConnected`、`mux 重放`、`PendingWait`、`WebSocket 无心跳`、`0.1.1-rc.2`
- **ask_user_question 等待期间一有用户输入就静默死亡（ASK_ABORTED），弹窗从未出现** → 工具把轮次 AbortController 的 signal 转发进问题，用户输入取消运行中轮次连带杀掉 pending 问题；相邻还有 approval 应答者无超时挂起 → [直达](references/dsh.md#related-failure-family)
  - 关键词：`ASK_ABORTED`、`aborted before the user answered`、`输入即中止`、`时灵时不灵`
- **模型报"密钥无效"，换 key 无效，直接 curl 厂商端点却正常** → Kimi 用 HTTP 403 报配额耗尽，dsh 的 401/403→AUTH 分类把配额错误翻译成认证失败，且其 *"reached your … usage limit"* 语序躲开了通用配额识别器；修复在 403 分支前加配额文案识别 → [直达](references/dsh.md#kimi-403-quota-auth)
- **单条消息并发派发大批量 subagent 后约三成报 failed，其中部分产物已完整落盘（伪失败）** → 上游订阅 key 的账户级 429 吞吐墙（"已达到 Token Plan 速率限制 (2062)"）：失败率随并发数进平台期；重试链 ~15s 短于限流 ~1 分钟恢复窗口，子代理终止在收尾步时产物已送达 → [直达](references/dsh.md#subagent-burst-429)
  - 关键词：`failed before it finished`、`伪失败`、`rate_limit_error`、`已达到 Token Plan 速率限制`、`2062`、`zstdcat 子会话日志`、`失败率平台期`、`落盘对账`

### Lean 4 / Lake 工具链与 CI

见 [lean.md](references/lean.md)。

- **全库公理扫描要 6～13 分钟、`collectAxioms` 却只占 0.1 秒** → Lean 4.30 的 `header.moduleNames` 不是缓存字段，逐常量调用即 O(声明×模块) 重建数组；同索引直接取 `header.modules[idx].module`、模块 membership 改 `Std.HashSet` 后筛选 392+83s → 7+3s → [直达](references/lean.md#lean-module-names-perf)
  - 关键词：`moduleNames`、`modules.map`、`env.getModuleIdxFor?`、环境筛选 392s、审计慢但 collectAxioms≈0、Std.HashSet Name
- **删了"重复 elaborate"后 `example : False := by sorry` 静默漏检** → 匿名 example 在 withoutModifyingEnv 求值、不留 .olean，sorry 只存在于构建诊断流；一次 Lake 图的 stdout+stderr（含 Replayed 缓存重播）必须在 audit 前扫描 → [直达](references/lean.md#lean-example-sorry-diagnostics)
  - 关键词：`example sorry 通过`、`withoutModifyingEnv`、`example 不进 olean`、`Replayed sorry`、`先打印再 check_returncode`、合并 stdout/stderr
- **CI 临时 fixture 报 `base revision ... is not available`，本地复现不了** → job 级 `env:` 的 `QATLAS_CLAIM_BASE=<主仓库 PR base>` 逐层继承进独立小仓库；fixture 显式传自身 HEAD 并故意保留外来变量做回归，本地复现先注入 job env → [直达](references/lean.md#lean-claim-base-env-leak)
  - 关键词：`QATLAS_CLAIM_BASE`、`fetch full history`、环境变量穿透 fixture、CI 绿本地红
- **观测 wrapper 加日志后官方 bootstrap 失败** → Mathlib `Cache/IO.lean` 按首词解析 `curl --version`，wrapper 往 stdout 打 JSON 即污染；观测只写独立 events 文件，长任务前先字节级预检 stdout/stderr/exit code → [直达](references/lean.md#observer-stdout-pollution)
  - 关键词：`curl --version 首词`、MEASURE JSON、wrapper 污染 stdout、第三方解析命令输出文本
- **`--no-build` 报 out-of-date，误以为项目缓存失效** → 缺失 target 是 `QuantumInfo.*` 等上游 Physlib 模块（本机固定依赖缓存不完整），与项目 `.lake/build` 无关；只读依赖下补模块要用私有可写副本；审计 13 分钟单核 100% 是慢不是挂 → [直达](references/lean.md#lake-no-build-upstream-stale)
  - 关键词：`target is out-of-date and needs to be rebuilt`、`QuantumInfo.Channels.Dual`、`--no-cache 不禁增量`、jobs 数是图规模、`docker top 分辨慢/挂`、Replayed 存量 warning 不失败
- **`gh run view --log` 报 read-only file system** → gh 写本地 run-log 缓存被拒；改 `gh api --allow-escape-sequences repos/<owner>/<repo>/actions/jobs/<id>/logs` → [直达](references/lean.md#gh-log-readonly-cache)
  - 关键词：`failed to get run log`、`creating cache entry`、`~/.cache/gh`、actions/jobs logs
- **多 agent 共享工作区，自己的改动"回到未暂存区"** → 交接方提交误卷暂存改动后 reset 重做，改动以未暂存形态回归；提交边界只看 `git diff --cached`，禁全树 add，`A` 是已暂存不是已提交 → [直达](references/lean.md#shared-worktree-stage-mixup)
  - 关键词：`误卷提交 reset`、改动回到 unstaged、`git diff --cached`、共享 gitdir、A 不等于 committed

