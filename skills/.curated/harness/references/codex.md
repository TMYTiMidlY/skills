# Codex 运行时笔记

本篇介绍 Codex app-server 的运行形态、CLI 启动行为、进程管理、终端显示与复制、桌面端 projectless 会话的目录与提示词、用量与额度统计、上下文配置、协作模式、内置生图工具、cc-switch 多账号与共享会话，以及订阅登录凭据。图片生成和编辑的区别、遮罩、外部应用接入及 CLIProxyAPI 调用和并发处理见 [Codex 订阅生图接入](image-gen.md)。

## <a id="app-server-lifecycle"></a>Codex app-server

app-server 是 Codex 的应用服务端组件，提供会话管理、认证、审批，以及模型和工具调用的组织能力。终端界面、IDE 等客户端通过它使用 Codex。它可以嵌入客户端进程，也可以作为独立进程运行；常驻后台只是其中一种运行形态。主机、容器、沙箱描述的是代码执行环境，和 app-server 的职责属于不同层面。

> 源码：[进程内客户端的接口设计](https://github.com/openai/codex/blob/73a1148c9c775c2a4616ce5096291740a00ed68a/codex-rs/app-server-client/src/lib.rs#L293-L330)。进程内调用保留服务端的请求和事件模型，但不需要跨进程通信。

### <a id="app-server-routing"></a>普通启动的连接方式

交互式 `codex` 和 `codex resume` 都通过 app-server 使用会话。在 `0.165.0` 中，`daemon_auto_start` 默认启用：满足共享后台条件的普通本地启动，会创建或复用当前 `CODEX_HOME` 的原生 daemon。旧版“没有后台就嵌入运行”的行为不能直接外推到这个默认入口。

| 启动方式或条件 | 服务端在哪里 | 后续启动 |
|---|---|---|
| 普通本地 TUI，自动 daemon 开启且配置允许共享 | 原生管理器创建或复用独立 daemon | 同一账号目录的客户端复用它 |
| `--no-daemon` | 当前 CLI 进程内的 app-server | CLI 退出后该实例结束，下次重建 |
| 非白名单 `-c`，例如 `model_provider`，或 `--profile` 等排除条件，且没有显式远端 | 不走普通隐式共享路线，使用进程内服务 | 先核实际进程，不能仅凭机器已有 daemon 判断 |
| 显式 `--remote unix://` | 当前 `CODEX_HOME` 的默认控制端点 | 需先有后台；连接失败报错，不悄悄回落到嵌入模式 |
| `codex agents` | 连接共享后台的总览界面 | 本地无显式远端时会确保后台启动；不支持 `--no-daemon` |

> `0.165.0` 源码：[自动启动默认值](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/features/src/lib.rs#L1068-L1073)、[自动启动条件](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/tui/src/startup_orchestration.rs#L548-L624)、[配置排除项](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/tui/src/daemon_startup.rs#L61-L125)、[显式端点优先](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/tui/src/lib.rs#L1056-L1092)、[agents 启动后台](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/cli/src/main.rs#L2536-L2553)。平台限制、显式 feature 设置和自定义 executor 也会影响路线，按实际版本核对。

`codex agents` 是客户端，不是模型请求的转发服务；共享模式由 daemon 承载会话并组织上游请求。一个后台可以管理多条会话，不为每条会话渲染一套 TUI。磁盘上的大量历史、已加载的空闲会话与同时执行的会话有不同资源成本，复用后台不构成并发量或内存容量保证。退出界面也不等于后台释放了所有会话，原生写锁边界见[会话监控与恢复](codex-monitoring.md)。

进程内模式使用当前启动的 CLI 程序；连接独立服务时，会话由那个服务进程处理，服务继续使用自身的程序和启动环境。模型菜单也从实际连接的服务取得，所以更新 CLI 文件或重开终端，不一定刷新所用服务。`-m` 只选择模型，本身不表示创建新服务实例。

> 源码：[客户端取得模型目录](https://github.com/openai/codex/blob/87cf20ee491a035036f2d905926df4a0d35951cc/codex-rs/tui/src/app_server_session.rs#L574-L629)。`codex exec` 是另一条入口，所引实现使用进程内服务，不能由它的行为直接推断交互式启动的连接方式，见 [exec 启动入口](https://github.com/openai/codex/blob/87cf20ee491a035036f2d905926df4a0d35951cc/codex-rs/exec/src/lib.rs#L973-L979)。

### <a id="daemon-auth-cache"></a>共享 daemon 的登录态缓存与新会话登录向导排查

daemon 复用意味着**新会话的登录态来自后台的内存缓存，不是磁盘 `auth.json`**。后台在未登录状态下启动、随后另一个进程完成 `/login` 只写磁盘时，后台不会自动重载：此后每个连它的客户端都被报告「未登录」，新开 TUI 命中首跑登录向导；而 `codex login status` 只读本地文件、已在跑的会话自带进程内登录态——三者可以合法地互相矛盾。凭据本身可能完全健康。

> 🔬 2026-10-29 实测（多 home 布局：launcher 导出 `CODEX_HOME` + per-home daemon，`0.165.0`）：daemon 19:09 在尚无 `auth.json` 的 home 上启动；22:08 在另一个进程内完成 ChatGPT 登录并写盘（token 直连后端验证 200、`login status` 显示 Logged in、旧会话正常）；随后新开 TUI 全部跳登录向导。`codex-<name> app-server daemon restart` 让后台从磁盘重读凭据后，PTY 实测新 TUI 直接进主界面（模型与 weekly 额度正常渲染），向导消失。

- 判别「新会话问谁要登录态」：默认控制 socket 可连接即问 daemon（见上表共享行）；`login status` 只读文件。两者不一致时先怀疑后台缓存陈旧，不要急着怀疑凭据损坏或被轮换。
- 经验规则：凡在 daemon 存活期间做了 `/login`、`logout` 或手工替换 `auth.json`，随后 restart 对应 home 的后台；多 home 布局下每个 home 各有 daemon 与 socket，重启的必须是实际承载会话的那个。
- 认证内存缓存与「改磁盘登录材料不等于既有后台立即换号」的源码依据见[用量与额度](#usage-accounting)所引 AuthManager 缓存读取及外部身份重载链接。

> **排查视角陷阱**：从受限沙箱（容器、agent 工具沙箱）观测 daemon 会双重失真——进程表看不到宿主进程；home 内控制 socket 是指向 `/tmp` 的软链而沙箱 `/tmp` 独立，`daemon version` 报 ENOENT，制造「后台已死」的假象。结论必须回到实际宿主上下文（用户终端、完整 shell）复核。判断在跑 TUI 属于哪个 home 可查 `/proc/<pid>/environ` 的 `CODEX_HOME`（同用户也可能被 ptrace 策略拒绝，此时按启动命令行与启动时间对照 launcher 推断）。

### <a id="app-server-launch"></a>独立服务的启动方式

`codex app-server` 启动的是供程序调用的服务端，不会打开普通 Codex 的聊天界面。监听方式决定客户端如何连接，是否常驻则取决于进程由谁启动和管理。

| 命令 | 作用 |
|---|---|
| `codex app-server` | 在当前终端前台运行服务，默认通过标准输入输出交换协议消息，适合由其他程序启动并连接 |
| `codex app-server --listen unix://` | 前台运行独立服务，监听当前 `CODEX_HOME` 的默认 Unix socket，供满足复用条件的本地客户端连接 |
| `codex app-server daemon start` | 通过 daemon 管理器启动或复用服务；新建实例作为受管后台进程运行 |

`--listen` 也支持指定其他 socket 路径或 WebSocket 地址；这些非默认端点需由客户端显式连接。daemon 管理器负责进程生命周期，并不是另一套模型或执行环境。

> 源码：[服务命令](https://github.com/openai/codex/blob/73a1148c9c775c2a4616ce5096291740a00ed68a/codex-rs/cli/src/main.rs#L550-L574)、[监听地址的解析](https://github.com/openai/codex/blob/73a1148c9c775c2a4616ce5096291740a00ed68a/codex-rs/app-server-transport/src/transport/mod.rs#L114-L155)、[服务启动和管理子命令的分流](https://github.com/openai/codex/blob/73a1148c9c775c2a4616ce5096291740a00ed68a/codex-rs/cli/src/main.rs#L1332-L1402)、[受管服务的启动](https://github.com/openai/codex/blob/87cf20ee491a035036f2d905926df4a0d35951cc/codex-rs/app-server-daemon/src/lib.rs#L335-L369)。

### <a id="app-server-environment"></a>启动环境与后台托管

进程内 app-server 使用本次 CLI 的环境；共享 daemon 使用创建它时启动链提供的环境。通过账号入口先导出代理、再启动 Codex，可以让首次自动创建的后台继承代理。复用已有后台时，新终端的变量不会更新旧进程；由 systemd 创建的后台则从 unit 或其启动脚本取得环境，而不是从随后连接的 TUI 取得。代理变量、clashctl 的 shell 集成、监听就绪与环境文件写法由 `network` skill 的 clashctl 与代理启动环境主题维护。

> 原生 daemon 的启动没有清空父环境，但会删除内部 telemetry handoff 并规范化部分路径；这不是环境继承白名单，见[创建后台进程](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/app-server-daemon/src/backend/pid_start.rs#L98-L158)和[后台命令环境处理](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/app-server-daemon/src/background_command.rs#L16-L99)。子工具是否采用代理仍取决于其环境策略、程序支持及旁路配置。

原生 PID 管理和 systemd 是两种托管选择。前者可由首次 CLI 按需启动，`backend: "pid"` 不表示创建了 user service，也不证明开机自启。若要 systemd 监管，unit 应直接运行前台 `codex app-server --listen unix://`，让 manager 跟踪真实服务进程；一般 unit、linger 与启动顺序归 `software` skill 的 Service / systemd 主题。两种方式都需明确谁负责停启、升级和后台环境，避免让两个管理器竞争同一账号端点。

`codex app-server daemon start` 不会把任意顶层 `-c` 透传给后台。后台的长期配置应先落在它自己的用户级配置中，再启动或在协调任务后刷新实例；客户端某次请求的显式覆盖是另一层。

> 来源：[Start 命令的分流](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/cli/src/main.rs#L1320-L1355)、[原生后台的固定启动参数](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/app-server-daemon/src/backend/pid.rs#L389-L424)。

Linux 上可用 `/proc/<pid>/environ` 白名单核对后台的启动环境；配置文件、当前 shell 与进程观测分别记录，代理 URI 的用户信息应脱敏。先验证账号和界面 bootstrap，再在获准后验证模型请求。一次成功启动没有证明间歇网络超时已消失，也没有验收重启后的代理就绪顺序。

### <a id="app-server-ownership"></a>进程的管理归属

独立运行不等于已经纳入 daemon 管理。识别服务时，需要区分正在调用的 CLI、磁盘上的受管程序和实际响应请求的进程。在目标宿主上使用同一个 `CODEX_HOME` 检查：

```bash
command -v codex
codex --version
codex app-server daemon version
```

| 字段 | 含义 |
|---|---|
| `cliVersion` | 当前管理命令的程序版本 |
| `managedCodexPath` / `managedCodexVersion` | 管理器使用的安装路径及磁盘程序版本 |
| `appServerVersion` | 控制 socket 握手返回的后台版本 |
| `backend: "pid"` | 管理器识别到 PID 管理状态，不表示 systemd 托管或开机自启 |

连接状态和进程管理归属是独立的。`status: "running"` 但没有 `backend`，表示服务可响应，管理器却未识别到受管进程。此时 start 可以返回 `alreadyRunning`，restart 和 stop 会拒绝直接接管该服务，需要先找到原启动入口或管理者。

> 源码：[状态字段](https://github.com/openai/codex/blob/87cf20ee491a035036f2d905926df4a0d35951cc/codex-rs/app-server-daemon/src/lib.rs#L63-L78)、[启动和重启的管理边界](https://github.com/openai/codex/blob/87cf20ee491a035036f2d905926df4a0d35951cc/codex-rs/app-server-daemon/src/lib.rs#L335-L390)、[停止和状态查询](https://github.com/openai/codex/blob/87cf20ee491a035036f2d905926df4a0d35951cc/codex-rs/app-server-daemon/src/lib.rs#L489-L531)。`pid` 字段也可能省略，不能仅凭它判断归属；PID 记录还需同实际监听进程对应。

### <a id="app-server-upgrades"></a>程序升级

更新磁盘程序后，进程内模式会在下次启动 CLI 时使用新程序；独立服务则需要另行刷新运行进程。自动更新是否完成这一步，取决于安装渠道、更新设置和更新进程的运行状态。

> 来源：[独立服务的更新机制](https://github.com/openai/codex/blob/87cf20ee491a035036f2d905926df4a0d35951cc/codex-rs/app-server-daemon/README.md#L113-L144)。

`0.155.0` 起 daemon 管理器提供 `update` 子命令，把选取最新稳定版、替换受管安装和重启运行中的服务合成一步。CLI 在会话启动时对比后台服务与自身版本，落后时提示执行该命令：

```bash
codex app-server daemon update
```

> 🔬 2026-09-23 实测（standalone 安装、daemon 受管的 Linux 宿主）：CLI 0.155.1 启动时提示后台服务 0.153.4 落后，按提示执行上述命令一次成功，提示消失；随后 `codex app-server daemon version` 显示 `cliVersion`、`managedCodexVersion`、`appServerVersion` 对齐且 `backend: "pid"`。提示原文：
>
> ```text
> ⚠ A background Codex service is running v0.153.4, older than your Codex CLI v0.155.1.
>   To update the service, run:
>     codex app-server daemon update
>   Updating may interrupt active or queued work.
> ```
>
> 来源：[update 子命令定义](https://github.com/openai/codex/blob/rust-v0.155.1/codex-rs/cli/src/main.rs#L794)（`rust-v0.154.0` 同文件无此子命令）、[update 的选取规则与重启行为](https://github.com/openai/codex/blob/rust-v0.155.1/codex-rs/app-server-daemon/README.md#L61-L68)、同款提示在其他安装渠道的独立报告 [issue #46468](https://github.com/openai/codex/issues/46468)。

`update` 要求 Codex 安装器管理的 latest 渠道 standalone 安装：npm 等其他渠道安装返回 `unsupported`，且 `restart` 会拒绝接管非受管进程（对应下方排查实例中无 `backend` 的情形）。`restart` 不拉取新版本，只把运行进程刷新到受管安装的当前版本；确认目标受管、且允许中断其活动任务后执行，再查询实际状态：

```bash
codex app-server daemon restart
codex app-server daemon version
```

管理器通常先请求正常退出，给任务收尾留出宽限时间，必要时再强制终止。正常退出可以执行会话和工具清理；强制结束主进程并不保证所有子进程都完成清理。按 PID 操作前，需要核对用户、启动时间和可执行文件，确保目标仍是预期实例。

> 源码：[停止流程](https://github.com/openai/codex/blob/87cf20ee491a035036f2d905926df4a0d35951cc/codex-rs/app-server-daemon/src/backend/pid.rs#L145-L225)、[正常退出和强制退出的清理分支](https://github.com/openai/codex/blob/87cf20ee491a035036f2d905926df4a0d35951cc/codex-rs/app-server/src/lib.rs#L1261-L1272)。

独立应用使用的专用服务需要按自己的启动方式更新，不能由默认共享服务的状态推断其状态。配置和历史会话可以保留，无需作为升级步骤删除。

> **排查实例**：一次 Astra 无法使用的问题中，CLI 升级后，新终端仍提示模型需要更新的 Codex。对比 `codex --version` 和 `codex app-server daemon version`，发现磁盘程序已经更新，实际响应的服务仍是旧程序。用户回贴的关键字段如下：
>
> ```json
> {"status":"running","managedCodexVersion":"0.153.4","cliVersion":"0.153.4","appServerVersion":"0.149.0"}
> ```
>
> 随后在宿主上检查进程列表和可执行文件路径，确认新终端连接的是持续运行的旧 app-server。输出中没有 `backend`，也表明 daemon 管理器未识别到受管进程；仅重新安装 CLI 或打开新终端不能替换它。
>
> 最终经明确授权，用户在独立 SSH shell 中终止当前用户的全部 Codex 相关进程，包括终端客户端、共享及专用 app-server、code-mode-host，再启动受管服务。重新执行 `codex app-server daemon version` 后，用户确认恢复正常，并回贴：
>
> ```json
> {"status":"running","backend":"pid","managedCodexVersion":"0.153.4","cliVersion":"0.153.4","appServerVersion":"0.153.4"}
> ```
>
> 这时客户端、磁盘程序和运行服务的版本一致，服务也已纳入 PID 管理。随后单独恢复了受影响的聊天桥专用服务；配置和会话历史没有删除。全量终止是该次获准的处理范围，不是常规升级的默认步骤。

### <a id="app-server-maintenance-executor"></a>管理命令的执行环境

`codex app-server daemon …` 等管理命令需要在能够访问目标 app-server 进程的环境中执行，工具沙箱里的进程视图可能不同于宿主。若在 Codex 会话中重启承载该会话的 app-server，执行命令的进程也可能随之结束；通过获准的独立 SSH 连接或服务管理任务执行，可以让重启过程不依赖该会话。

> 来源：[Linux 工具沙箱的进程隔离](https://github.com/openai/codex/blob/3d2ee51ca2d5db578f328aa75e20aa22c0197c9a/codex-rs/linux-sandbox/src/bwrap.rs#L327-L343)。`nohup` 只处理部分终端退出行为，不能单独保证任务脱离沙箱和进程清理范围。

使用 systemd 通过 `bash -c` 执行 app-server 管理脚本时，脚本文本会先经过 systemd 的参数处理，再交给 Bash。启用环境替换时，`${…}` 可能被提前展开；调用方加单引号不能阻止这一层处理。把复杂脚本放进独立文件、只向服务管理器传递文件路径，可以减少多层展开的干扰。

> 来源：[systemd 命令参数的环境替换](https://github.com/systemd/systemd/blob/v239/man/systemd.service.xml#L1008-L1067)。内联脚本需要核对每层转义，关闭展开的选项也应先确认可用性。通用服务管理知识归 `software` skill。

## <a id="terminal-clipboard"></a>终端界面与 Zellij Web 复制

WSL2 中使用 Codex 0.162.1、Zellij 0.44.3 Web client 时，曾出现 Codex 显示 `Copied`，浏览器剪贴板却没有更新：Codex 捕获拖选后，调用 PowerShell 复制到 Windows 宿主；宿主复制成功、且未检测到 SSH / tmux 环境时，就结束复制。Zellij 自己的拖选复制仍可用。

> 源码：[复制路由与 SSH 检测](https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/tui/src/clipboard_copy.rs#L167-L247)、[WSL PowerShell 复制](https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/tui/src/clipboard_copy.rs#L277-L326)。以下方法在上述环境中以独立 Chromium 会话实测，含中文复制。

**普通终端界面**：在实际使用的 `$CODEX_HOME/config.toml`（默认 `~/.codex/config.toml`）已有的 `[tui]` 段中设置，重开 Codex：

```toml
[tui]
alternate_screen = "never"
```

备用屏幕用于全屏重绘、退出后恢复 shell 画面；该版本 Codex 将全屏界面与主界面鼠标捕获关联。设为 `never` 后，普通终端滚动输出的拖选交给 Zellij，浏览器复制恢复；`/copy` 仍使用 Codex 的复制后端。使用独立 `CODEX_HOME` 的启动入口需分别配置。

> 来源：[备用屏幕配置](https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/core/config.schema.json#L4547-L4554)、[全屏状态与鼠标捕获](https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/tui/src/tui.rs#L761-L806)。

**翻页取舍**：按 Codex 0.163.0 源码，`alternate_screen = "never"` 会关闭主界面由 Codex 管理的历史视图，即使 `fullscreen_transcript = true` 也一样；主聊天的 PageUp/PageDown 历史滚动处理随之停用。Zellij 用 `Write` 将 `Alt u`/`Alt d` 映射成 PageUp/PageDown 时，只是在向 Codex 发送按键，不会改为滚动 Zellij 的终端历史。保留 `never` 时，可用 Zellij 自身的滚动操作，或先按 `Ctrl+T` 打开独立的历史查看界面再翻页。

> 来源：[备用屏幕策略](https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/tui/src/lib.rs#L2172-L2193)、[启动时选择历史视图](https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/tui/src/lib.rs#L1952-L1967)、[历史视图归属条件](https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/tui/src/transcript_mode.rs#L12-L23)。这是源码核验；Ctrl+T 的查看界面与主聊天使用不同的输入路径，禁用备用屏幕不等于所有界面都不能翻页。

**保留全屏界面**：若还要主聊天的 PageUp/PageDown 翻页，移除 `alternate_screen = "never"` 恢复默认，再让 Codex 启动时继承 `SSH_TTY=/dev/tty`。该版本只检查 `SSH_TTY` 是否存在，随后即使宿主复制成功，也会通过 OSC 52 向终端转发复制请求；Zellij Web 再写入浏览器所在设备的剪贴板。实测拖选与 `/copy` 菜单均可用。这里借用 SSH 环境检测，设置变量本身不会建立 SSH 连接；`/dev/tty` 是当前控制终端的设备路径。

变量可仅在启动 Codex 时设置，也可通过 Zellij 的 `env` 块统一注入；配置位置及作用范围见 `software` skill 的 Zellij 章节。

## <a id="desktop-projectless"></a>桌面端 projectless 会话的目录与提示词

ChatGPT 桌面端的 Codex projectless 会话（不依附已有项目的聊天）有一套生成工作目录、指定交付目录并注入提示词的机制。下面记录的是 **2026-09-07 桌面端提取样本**：提示词把会话目录描述为用户 `Documents/Codex` 下的生成目录；配置了独立交付目录时，要求把中间文件放在 `work/`，把交付物放在指定路径，并只链接该路径下的交付文件。

这套目录约定属于闭源桌面客户端的行为，不能当成开源 Codex CLI 在任意工作目录中都会注入的默认提示词。提示词表达文件组织要求，本身不等于文件系统沙箱或写权限强制限制。

> 来源：历史会话记录将下列函数定位到桌面应用的 `resources/app.asar`。留存提取文件的 SHA-256 为 `90a7ba29257f8c3253b0977fa2efe40cf5742dc2c8896ed8d94c07df96dbe55b`，本次读回校验一致。这里保存的是历史提取证据，没有据此确认所有桌面端版本均使用同一函数；开源侧的相关概念另见[开源 Codex 中的 projectless](#projectless-open-source)。

### <a id="desktop-projectless-source"></a>模板函数原文

下面保留提取文件中的原样函数，包括压缩后的变量名和 `.join()` 中的实际换行；函数返回一段按行拼接的提示词。

```js
function et({cwd:e,projectlessOutputDirectory:t,projectlessWorkspaceBrowserRoot:n}){let r=t??n??e;return[`### Projectless Chat`,`This projectless thread starts in a generated directory under the user's Documents/Codex folder.`,`The generated directory name is only a filesystem identifier. Do not infer the user's language, locale, or preferences from its name or path, even if it resembles a language code such as 'ru'.`,`Prefer answering inline in chat unless using local files would make the result more useful.`,...t!=null&&t!==e?[`Use work/ for intermediate files, scratch analysis, scripts, drafts, and temporary assets. Use ${r} only for user-facing deliverables that should appear as outputs.`,`When referring to saved deliverables in the final response, link only files from ${r}.`]:[`When using local files for this projectless thread, write scratch files, drafts, generated assets, and other outputs under ${r}.`],`Do not write directly in the home directory unless the user explicitly asks.`].join(`
`)}
```

`r` 是最终插入提示词的路径，取值逻辑用完整参数名表示为：

```js
r = projectlessOutputDirectory ?? projectlessWorkspaceBrowserRoot ?? cwd
```

`??` 只在左侧为 `null` 或 `undefined` 时回退，不会跳过空字符串：先用独立交付目录，再用 projectless 工作区的文件浏览根目录，最后用当前工作目录 `cwd`。原函数的 `t`、`n`、`e` 分别对应这三个参数；它不检查路径是否存在，也不自行拼接 `outputs`。

函数还按 `t != null && t !== e` 选择目录提示。这里比较的是传入值，不是解析后的文件系统路径是否指向同一位置。

| 参数条件 | 返回的目录约定 |
|---|---|
| `projectlessOutputDirectory` 既非 `null` 也非 `undefined`，且不等于 `cwd` | 中间文件用 `work/`；交付物和最终回复的交付链接只用 `${r}` |
| `projectlessOutputDirectory` 为 `null` / `undefined`，或等于 `cwd` | 中间文件、草稿、生成资产及其他输出统一写入 `${r}`；不注入 `work/` 与交付目录分离的那两句 |

> 历史桌面端取证还记录了由应用固定创建 `outputs` 目录，当时 `r` 指向生成会话目录下的 `outputs`。这一创建行为的依据是桌面端检查记录，**不是该模板函数，也不是开源仓库未匹配到 `outputs` 的搜索结果**；留存函数本身没有创建目录的调用。复核具体建目录实现需另查相应桌面端构建。

### <a id="desktop-projectless-prompt"></a>独立交付目录分支的提示词原文

满足 `t != null && t !== e` 时，函数返回以下完整文本。这里按模板保留 `${r}`，实际注入时替换成上面选出的路径。

```text
### Projectless Chat
This projectless thread starts in a generated directory under the user's Documents/Codex folder.
The generated directory name is only a filesystem identifier. Do not infer the user's language, locale, or preferences from its name or path, even if it resembles a language code such as 'ru'.
Prefer answering inline in chat unless using local files would make the result more useful.
Use work/ for intermediate files, scratch analysis, scripts, drafts, and temporary assets. Use ${r} only for user-facing deliverables that should appear as outputs.
When referring to saved deliverables in the final response, link only files from ${r}.
Do not write directly in the home directory unless the user explicitly asks.
```

### <a id="desktop-projectless-fallback"></a>统一写入目录分支的提示词原文

不满足上述条件时，函数用一条统一写入要求替换中间的两条目录约定，完整文本如下：

```text
### Projectless Chat
This projectless thread starts in a generated directory under the user's Documents/Codex folder.
The generated directory name is only a filesystem identifier. Do not infer the user's language, locale, or preferences from its name or path, even if it resembles a language code such as 'ru'.
Prefer answering inline in chat unless using local files would make the result more useful.
When using local files for this projectless thread, write scratch files, drafts, generated assets, and other outputs under ${r}.
Do not write directly in the home directory unless the user explicitly asks.
```

### <a id="projectless-open-source"></a>开源 Codex 中的 projectless

开源 Codex 也使用 `projectless` 一词，但项目识别、信任处理和遥测元数据与桌面端模板是不同机制。以下源码核对锁定到 2026-09-21 的提交 `f747d23d4bc8a167207fb1c411e221022391fdbb`，不把它称为持续有效的“最新 HEAD”。

**项目识别与信任**：配置加载器在未忽略项目配置且存在 `cwd` 时，检查其发现范围内没有项目根标记、没有 Git checkout 根、没有项目级 `.codex` 配置层，三者同时满足才标为 `is_projectless`。跳过这一发现过程时，标志仍为初始的 `false`。app-server 在 `thread/start` 中据此排除隐式项目信任的持久化；这不负责选择 `work/` 或 `outputs/`，也不表示撤销显式信任或绕过权限检查。

> 源码：[发现条件与初值](https://github.com/openai/codex/blob/f747d23d4bc8a167207fb1c411e221022391fdbb/codex-rs/config/src/loader/mod.rs#L332-L333)、[projectless 判定](https://github.com/openai/codex/blob/f747d23d4bc8a167207fb1c411e221022391fdbb/codex-rs/config/src/loader/mod.rs#L404-L406)、[隐式授信分支](https://github.com/openai/codex/blob/f747d23d4bc8a167207fb1c411e221022391fdbb/codex-rs/app-server/src/request_processors/thread_processor.rs#L1361-L1376)。没有项目配置层与缺少 `config.toml` 不等价：发现项目级 `.codex` 目录但没有配置文件时，也会[加入空配置层](https://github.com/openai/codex/blob/f747d23d4bc8a167207fb1c411e221022391fdbb/codex-rs/config/src/loader/mod.rs#L1740-L1750)。

> 引入这组改动的提交为 [Avoid persisting project trust for projectless directories (#46328)](https://github.com/openai/codex/commit/608e4cc9a132c2aa7754b10585d88ca34182d741)，提交日期为 2026-09-18。目的在于避免先在无项目目录启动任务、保存信任后，自动预先批准以后新加入的项目配置。它晚于 9 月 7 日的桌面端样本，只能作为后续开源旁证，不能倒推为当时桌面端的实现。

**客户端遥测标签**：`workspace_kind()` 从 `responsesapi_client_metadata` 读取 `workspace_kind`；这里消费客户端传入的值，不根据 `cwd` 自行判定是否为 projectless。**不要把它写成从 `responses_api_metadata` 读取**，后者在该实现中是另一路透传配置。

> 源码：[客户端元数据、另一组透传元数据及标签读取器](https://github.com/openai/codex/blob/f747d23d4bc8a167207fb1c411e221022391fdbb/codex-rs/core/src/turn_metadata.rs#L363-L391)、[`workspace_kind` 键常量](https://github.com/openai/codex/blob/f747d23d4bc8a167207fb1c411e221022391fdbb/codex-rs/core/src/turn_metadata.rs#L51)。读取通道的存在不能单独证明 9 月 7 日桌面端确实发送了该标签或经过该通道。

> 此前的全仓及历史检索记录以 `f747d23d4b` 为快照，报告未匹配到 `### Projectless Chat`、`projectlessOutputDirectory`、`projectlessWorkspaceBrowserRoot` 及模板特征句；本轮未重跑这项全历史搜索。该记录说明未找到这段桌面端模板的开源出处，不意味着开源 Codex 完全没有 projectless 概念，也不能仅由搜索未命中推断目录由谁创建。

因此，目录约定与提示词的直接依据是留存的桌面端提取样本；开源侧的信任判定和客户端标签应独立引用，不能代替模板与建目录代码的出处。

## <a id="usage-accounting"></a>用量与额度

Codex 的账号 token 活动图、剩余额度窗口和各客户端的本地会话统计是不同读数。本节以 `codex-cli 0.153.4` 为基线；DSH 输入区的轮／步数、计时、缓存和输入输出口径见 [DSH 会话统计条](dsh.md#session-statistics)。

### <a id="usage-profile"></a>账号活动图

裸 `/usage` 先打开菜单；选择 **Show usage**，或直接输入 `/usage daily`、`/usage weekly`、`/usage cumulative`，才显示 Token activity。图表通过 `account/usage/read` 请求所连接的 app-server，服务使用自己的 `AuthManager` 身份向 ChatGPT 后端查询 profile；通常是 `GET https://chatgpt.com/backend-api/wham/profiles/me`，另一种后端路径为 `/api/codex/profiles/me`。

图中的 lifetime 和每日 token 桶来自服务端响应，**不是扫描当前系统用户的本地会话目录或 SQLite 得出的总数**。这里的“账号”是上游认证身份及所选账号／工作区上下文；切换 Linux 用户、`CODEX_HOME` 或客户端实例，不会自动获得另一份 ChatGPT 身份。同一上游身份可以在不同本地用户下看到相同统计。

> 源码：[Usage 菜单](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/tui/src/chatwidget/usage.rs#L48-L72)、[用量和额度的 RPC](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/tui/src/app/background_requests.rs#L799-L823)、[app-server 选择认证身份并取得 profile](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/app-server/src/request_processors/account_processor.rs#L1216-L1308)、[profile HTTP 路径](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/backend-client/src/client.rs#L351-L363)。

每次打开活动图会发起查询，但认证另有内存缓存；改磁盘上的登录材料不等于既有后台立即换号。图表按服务端日期字符串合并 token 桶，前端不按模型价格或缓存折扣加权；前端使用 UTC 判断“今天”，不能据此推定服务端每日桶的完整划分规则、更新延迟或计数公式。

> 源码：[认证缓存读取及外部身份重载](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/login/src/auth/manager.rs#L2341-L2361)、[日期桶求和](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/tui/src/chatwidget/tokens/chart.rs#L384-L420)、[前端日期基准](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/tui/src/chatwidget/tokens.rs#L74-L75)。本地日志与云端数字不一致时，还需对齐时间范围、缓存是否已含在输入中、继承／重试去重，以及其他客户端和设备的调用范围。

`/status` 中的**账号额度窗口**另走 `account/rateLimits/read` → `/wham/usage`，返回已用比例、窗口长度和重置时间；`/usage` 菜单中的额度重置功能也不是 token 活动图。不能用活动图的累计 token 直接换算某档订阅还剩百分之几，更不能把 API 价格权重当成已公开的订阅扣额公式。

> 源码：[额度查询分支](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/tui/src/app/background_requests.rs#L799-L810)、[额度 HTTP 路径](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/backend-client/src/client/rate_limit_resets.rs#L83-L88)。这里限定 `/status` 的额度字段，不把它同时展示的会话配置和会话 token 数都归为账号统计。

### <a id="usage-third-party"></a>第三方客户端调用

第三方客户端调用订阅后端时，额度归属取决于实际使用的上游账号；它维护的本地统计与 OpenAI 的账号活动图是两套记录。客户端名称、本地系统用户或代理访问 key，都不能单独证明最终使用哪个账号。

**第三方调用是否完整显示在 `/usage` 活动图中，公开客户端源码不足以确定。** 使用相同后端和账号不能证明每笔都被收录；活动图未显示或尚未更新，也不能当作请求不消耗订阅额度的证据。

> 源码：[Codex 读取云端 profile](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/backend-client/src/client.rs#L351-L363)。客户端只取得聚合结果，未给出服务端的入账、去重和第三方覆盖规则，因此不能将 `/usage` 概括为“只统计官方客户端”，也不能保证它完整覆盖所有第三方调用。

## <a id="context-compaction"></a>上下文窗口与自动压缩

Codex 需要分别知道模型可用的上下文窗口，以及历史增长到多少 tokens 时开始自动压缩。前者是客户端的预算上限，后者是提前收缩历史的触发线；只改其中一个，不能完整表达长上下文策略。

> [Codex Configuration Reference](https://developers.openai.com/codex/config-reference/) 将 `model_context_window` 定义为当前模型可用的上下文窗口，将 `model_auto_compact_token_limit` 定义为自动压缩历史的 token 阈值；后者不设置时使用模型默认值。

### `config.toml` 配置

用户级配置写在 `~/.codex/config.toml`。下面这组配置选择 GPT-5.6 Sol，把 Codex 的上下文预算设为 1,000,000 tokens，并在 800,000 tokens 时触发自动压缩：

```toml
model = "gpt-5.6-sol"
model_context_window = 1000000
model_auto_compact_token_limit = 800000
```

这三个键必须位于 TOML 顶层；最稳妥的放法是写在第一个 `[projects.…]`、`[profiles.…]` 或其他表头之前。否则它们会归入前一个 TOML table，而不再是全局模型配置。

GPT-5.6 Sol 的模型 ID 是 `gpt-5.6-sol`，`gpt-5.6` 是指向它的别名。该模型的官方上下文窗口是 1,050,000 tokens，因此上面的 1,000,000 是低于模型规格的保守预算；800,000 的压缩线在配置窗口内留下 200,000 tokens 缓冲。

> 模型 ID、别名、1,050,000-token 上下文窗口与 128,000-token 最大输出见 [GPT-5.6 Sol model page](https://developers.openai.com/api/docs/models/gpt-5.6-sol)。`model_context_window` 只告诉 Codex 如何预算已有能力，不能把后端不支持的模型扩成更大的上下文。

`model_auto_compact_token_limit_scope` 控制阈值的计数范围：默认值 `total` 统计全部活动上下文；`body_after_prefix` 只统计压缩后保留前缀之外继续增长的正文。没有反复压缩后的特殊计数需求时，不必显式设置。

### 加载验证

编辑完成后启动新的 Codex 进程，让它重新读取配置。先运行一个不发起模型任务的命令，可检查 TOML 是否能被当前 CLI 正常解析：

```bash
codex features list
```

该检查只能证明配置文件成功加载，不能证明账户已经获得模型权限，也不能证明一次端到端请求实际占用了 1M tokens。模型可用性仍由当前账户和服务端决定。

> 🔬 2026-08-20 在 `codex-cli 0.148.0` 上实测：上述三项写入用户级配置后，`codex features list` 返回成功；这是配置解析检查，不是 1M 请求压力测试。

### <a id="compaction-runtime"></a>压缩触发与运行路径

自动压缩由 Codex harness 管理活动历史、判断阈值并发起；压缩状态可以由 OpenAI 后端生成，随后由 harness 安装为下一轮上下文。判断某次压缩使用什么机制，要同时核对客户端版本、provider、请求内容和会话存档。

在下述 `0.162.0` 实测路径中，harness 把当前模型指令和历史消息送到 OpenAI，在输入末尾加入 `compaction_trigger`。后端返回保留的消息和带 `encrypted_content` 的 `compaction` item；存档中的 `compacted.message` 为空，`replacement_history` 保存新的活动历史。后续推理携带这份压缩状态继续执行，具体保留内容通过后续回忆测试核验。

> 🔬 2026-10-09，Codex app-server `0.162.0`、ChatGPT 订阅登录、OpenAI provider、`gpt-6.1-sol` / `xhigh`：独立进程的请求 trace 与 rollout 对照确认上述结构。加密 item 是不透明状态，JSONL 中的空 `message` 应结合 `replacement_history` 解读。

Codex 当前远端路径可通过 Responses 流执行压缩；定位 HTTP 接口时应检查实际传输日志。公开 API 另提供独立的 `/responses/compact`，以及在普通 `/responses` 中用 `context_management.compact_threshold` 启用的服务端自动压缩。后者由服务端判断阈值，和 Codex 本地阈值触发请求属于不同的控制方式。

> 本节所述 Codex 路径以实测为准。公开 API 的用法阅读入口为 [Compaction](https://developers.openai.com/api/docs/guides/compaction)，2026-10-09 查阅；API 文档只说明接口能力，Codex 是否采用某个接口仍需运行时证据。

压缩频率取决于活动上下文增长和阈值计数范围。文件读取、工具输出、模型输出和新增指令都会影响增长；统计频率时应按同一版本、同一角色、实际工作时段记录压缩事件，空闲时间单列。增大上下文预算并提高压缩线，可以延后达到阈值的时刻；一次求解能否在两次压缩之间完成，仍取决于任务规模和历史增长速度。

### <a id="compact-prompt"></a>自定义压缩提示词

`compact_prompt` 是用户级 `config.toml` 的顶层字符串配置，例如：

```toml
compact_prompt = "保留当前目标、关键决策、失败尝试、约束和下一步。"
```

配置文档还提供 `experimental_compact_prompt_file`，用于从文件读取覆盖提示词。核验时分别确认配置被解析、当前会话采用该配置、提示词进入压缩请求，以及压缩后的实际行为。

> 配置项阅读入口：[Configuration Reference](https://learn.chatgpt.com/docs/config-file/config-reference)，2026-10-09 查阅。文档将这些键描述为压缩提示词覆盖入口；具体运行路径是否使用覆盖值，按下述实测条件判断。文件覆盖入口未在本次实验中测试。

**在本次 `0.162.0` 的 OpenAI 远端压缩路径上，`compact_prompt` 成功读取，但未进入记录的压缩请求，修改它未显示出对压缩行为的影响。** 这个结论同时覆盖会话配置覆盖和隔离的用户级配置。其他版本、provider 或文字交接摘要路径需要另测；二进制包含默认摘要提示词，只能说明存在该文本，实际采用哪条路径仍看运行证据。

### <a id="compaction-experiment"></a>压缩提示词对照实测

2026-10-09，用独立 `CODEX_HOME` 和 stdio app-server `0.162.0`，以 `gpt-6.1-sol` / `xhigh`、OpenAI provider、ChatGPT 订阅登录执行实验。固定合成会话包含 12 个任务事实、一个已废弃的旧值、下一步和约束，并混入无关观察；事实放在 assistant 历史中，压缩后保留的明文消息不含这些事实。各组从同一份完成的历史 fork，使用同一回忆问题。实验提示词要求 JSON 摘要、保留任务事实，并加入一个仅存在于配置中的识别标记。

| 配置组 | 触发方式与次数 | 请求中出现自定义提示词标记 | 压缩后事实回忆 |
|---|---|---|---|
| 默认配置，未覆盖提示词 | 手动 2 次、自动 1 次 | 无 | 均为 12/12；旧值、下一步与约束也正确 |
| 会话覆盖 `compact_prompt` | 手动 2 次、自动 1 次 | 无 | 均为 12/12；旧值、下一步与约束也正确 |
| 用户级 `compact_prompt` | 新进程手动 1 次 | 无 | 12/12；旧值、下一步与约束也正确 |

用户级实验先通过 `config/read` 确认解析出的字符串与实验提示词完全一致。7 次压缩的 trace 中，`compaction_request` payload 逐字段相同；各组压缩后的回忆均未报告配置专用标记。默认组自身也出现输出排版和数值类型差异，因此输出文本、密文或 token 数不同，应与重复对照一起判断。

自动组仅在测试配置中把触发线降到 16,000 tokens；每组都在下一次推理前完成一次压缩，采用与手动组相同的请求结构。实验的 `model_context_window` 为 272,000，推理事件报告的有效窗口始终为 258,400。压缩后自动组的客户端计数约 7.9–8.0k，所有组随后完整推理请求的输入约 16.3–18.3k；这两个计数应分别记录。压缩缩减的是已占用历史，窗口容量保持不变，压缩后的占用也随输入内容与保留项变化。

> 🔬 本实验结论来自配置读取结果、请求 trace、压缩安装事件、rollout 和后续回忆答案。合成事实在历史中重复出现；这是配置是否进入当前压缩路径的对照，覆盖有限的事实回忆，尚未测量真实 solver / reviewer 的完成率、长程证明推理或 512k 满窗口表现。原始测试材料不收录于本 skill。

复测时在隔离进程中固定模型、effort、指令和源历史，先重复默认组，再只修改压缩提示词。手动调用 `thread/compact/start` 后等待 `contextCompaction` 完成及对应 `turn/completed`，再执行共同回忆问题；自动组降低测试阈值，并从事件确认实际发生压缩。使用 `CODEX_ROLLOUT_TRACE_ROOT` 可记录本版本的请求和安装过程，核对提示词标记是否进入请求、两组源历史是否一致。验证该环境变量与 trace 格式时仍以被测版本为准。

> `thread/fork`、`thread/inject_items` 和 `thread/compact/start` 的协议阅读入口：[Codex App Server](https://learn.chatgpt.com/docs/app-server)，2026-10-09 查阅。压缩 RPC 即时返回 `{}`，后续事件才表明压缩完成。使用 `thread/inject_items` 等实验接口需启用 `experimentalApi`。

对证明和审阅任务，建议把目标合同、实际受测版本、已验证结果、失败路线和下一步放在可重新读取的任务材料中。压缩后重新读取这些材料：solver 可恢复具体证明路线，reviewer 可继续依据实际代码和验证证据审查。调大窗口主要改变压缩间隔；对信息恢复质量的判断，需要真实任务的对照测试。

## <a id="config-layering"></a>配置层栈与项目级 `.codex` 发现

`~/.codex/config.toml` 只是层栈中的一层。生效配置由多层**深合并**而成：表递归合并、逐键覆盖，上层未写的键保留低层的值。优先级从低到高为：包默认值 → 管理偏好（仅 macOS MDM）→ 系统 `/etc/codex/config.toml` → 企业托管云端片段 → 用户 `${CODEX_HOME}/config.toml`（选定 profile 再叠一层）→ **项目层**（见下）→ 会话标志（`-c` / `--config`、UI 选择器）。组织 `requirements.toml` 以约束形式压在整个层栈之上；legacy `managed_config.toml` 仍以最高配置层兼容加载。

**项目层发现规则**（回答“这份 `.codex/config.toml` 到底管不管这个会话”）：

1. `project_root` = 离 `cwd` 最近的、带项目根标记的祖先目录。默认标记只有 `.git`，且必须是含 `HEAD` 的合法 git 目录（普通同名目录不命中）；向上找不到标记时回落为 `cwd` 本身。标记列表可由配置键 `project_root_markers` 改写，空数组表示禁用根检测。
2. 从 `cwd` 沿祖先向上**到 `project_root`（含）为止**，每级目录若有 `.codex/` 就收集一层（`config.toml` 缺失也记空层）；**离 `cwd` 越近优先级越高**。
3. 目录未受信任时该层“加载但禁用”（`disabled_reason`），只在 UI 展示、不参与生效配置。
4. 项目层有一份 denylist——仓库内容不能决定凭据去向或执行哪些本地命令：`openai_base_url`、`chatgpt_base_url`、`apps_mcp_product_sku`、`responses_api_metadata`、`model_provider`、`model_providers`、`notify`、`profile`、`profiles`、`experimental_realtime_webrtc_call_base_url`、`experimental_realtime_ws_base_url`、`otel` 只能来自用户／系统／托管／运行时层。

**git 根截断推论**：祖先遍历止于最近的 `.git`，所以子目录一旦是独立 git 仓库，仓库外层父目录的 `.codex/config.toml` 对它**不生效**。想给一组平行的 agent 工作克隆共享项目配置，提升到公共父目录做不到，必须每个 git 仓库各放一份；改 `project_root_markers` 也绕不过——命中的永远是最内层标记祖先。反向用法：`sandbox_mode`、`approval_policy` 不在 denylist 里，项目层可写，给单个仓库放宽／收紧沙箱比改用户全局影响面小。

**守护进程的读取时机**：app-server 的 `ConfigManager` 不长期缓存层栈——每个新 thread 启动都现读磁盘；已在运行的 thread 保留其启动时配置（"Existing threads retain their session route"），只有托管 requirements 变化能作废它。显式重载入口 `reload_user_config` / `reload_mcp_config` 由客户端在写完配置后调用，外部工具改文件不会自动触发。因此**外部编辑 `config.toml` 对新会话即刻生效，无需重启 daemon**；旧会话只能 `/permissions` 临时切换或开新对话。

> 源码（锁定 2026-10-06 master `80e0b51c9e44853471fae105032fa000c77d3e4a`，不视为持续有效的最新 HEAD）：[层栈顺序文档注释](https://github.com/openai/codex/blob/80e0b51c9e44853471fae105032fa000c77d3e4a/codex-rs/config/src/loader/mod.rs#L120-L144)、[项目层 denylist](https://github.com/openai/codex/blob/80e0b51c9e44853471fae105032fa000c77d3e4a/codex-rs/config/src/loader/mod.rs#L89-L102)、[根标记向上查找与 `.git`/HEAD 校验](https://github.com/openai/codex/blob/80e0b51c9e44853471fae105032fa000c77d3e4a/codex-rs/config/src/loader/mod.rs#L1514-L1529)、[遍历范围与优先级注释](https://github.com/openai/codex/blob/80e0b51c9e44853471fae105032fa000c77d3e4a/codex-rs/config/src/loader/mod.rs#L1601-L1611)、[discover_project_layers 实现](https://github.com/openai/codex/blob/80e0b51c9e44853471fae105032fa000c77d3e4a/codex-rs/config/src/loader/mod.rs#L1653)、[默认标记列表](https://github.com/openai/codex/blob/80e0b51c9e44853471fae105032fa000c77d3e4a/codex-rs/config/src/project_root_markers.rs#L5)、[每次现读的 load_latest_config](https://github.com/openai/codex/blob/80e0b51c9e44853471fae105032fa000c77d3e4a/codex-rs/app-server/src/config_manager.rs#L191)、[旧会话保留注释](https://github.com/openai/codex/blob/80e0b51c9e44853471fae105032fa000c77d3e4a/codex-rs/app-server/src/config_manager.rs#L267)、[重载入口 reload_user_config](https://github.com/openai/codex/blob/80e0b51c9e44853471fae105032fa000c77d3e4a/codex-rs/app-server/src/request_processors/config_processor.rs#L356)。

> 🔬 2026-10-06 宿主实测（daemon 0.160.1、CLI 0.160.x）：`workers/` 下四个各自带 `.git` 的平行工作克隆，父级 `workers/.codex/config.toml` 对克隆内会话无效（源码推演 + 目录标记核对）；逐克隆放置 `.codex/config.toml`（512K/440K 上下文、禁两个本地 MCP、`sandbox_mode = "danger-full-access"`）后，新开对话按新层栈生效，TOML 经 `tomllib` 校验。未逐会话抓取生效快照，生效结论以新会话行为为准。

## 协作模式与结构化提问

Codex 会话可使用不同的协作预设，也提供面向长期任务的 Goal 工作流。这里把 Goal 一并列出是为了消歧：Default 与 Plan 是当前 harness 的协作模式，Goal 则是可暂停、恢复和调整的长期任务状态，并非与前两者同层的模式枚举。

| 模式 | 用途 | `ask user` 类工具 |
|---|---|---|
| **Default** | 直接调查、改代码、运行命令和测试 | 当前不可用，只能普通文本提问 |
| **Plan** | 先收集背景、结构化追问、形成实施计划 | 可用 |
| **Goal** | 持续执行明确目标，可暂停、恢复和调整 | 属于长任务机制，不是同层协作模式 |

> [Codex Best practices](https://learn.chatgpt.com/guides/best-practices) 说明 Plan mode 会先收集上下文、提出澄清问题并形成实施计划，可通过 `/plan` 或 Shift+Tab 切换；[Long-running work](https://learn.chatgpt.com/docs/long-running-work) 说明 `/goal` 所启动目标的暂停、恢复、编辑与清除语义。

### `request_user_input` 实测

> 🔬 2026-08-21 在当前 Codex 会话中实测：Default 模式调用 `request_user_input` 被 harness 拒绝，返回：
>
> ```text
> request_user_input is unavailable in Default mode
> ```

切换到 Plan 模式后，以相同工具展示结构化问题成功。用户通过客户端自动附加的自由输入选项回答 `hello`，工具返回：

```json
{"answers":{"next_task":{"answers":["None of the above","user_note: hello"]}}}
```

这组结果只证明当前会话所用 Codex harness 的实际行为；其他 Codex 版本、客户端或第三方 harness 是否提供相同模式与工具约束，应分别实测，不能由本记录外推。

## <a id="image-runtime"></a>生图工具的执行过程

Codex 的主模型负责理解任务、组织提示词和选择工具，内置 `image_gen.imagegen` 再请求图片后端。通过 MCP 或 SDK 驱动整个 Codex 时，外层调用还包含 Codex 自己的运行过程；直接请求订阅图片接口则是另一种接入方式，见 [调用路径](image-gen.md#routes)。

> 本节原始源码依据为 `openai/codex` 提交 `73a1148c9c775c2a4616ce5096291740a00ed68a`；图片模型和请求字段已按 2026-09-10 的稳定版、近期预发布版及主线补核，具体范围见[图片请求的构造](#image-request)。其他行为仍以各段所引版本为准。源码不能单独证明当前账户权限、线上模型映射或每次请求的实际效果。

### <a id="image-availability"></a>内置生图工具的启用条件

在 Codex 中找不到图片工具时，先检查工具注册条件，再检查上游权限。注册条件决定工具是否进入模型可见列表；它们通过之后，上游仍可能因为身份、额度或服务状态拒绝请求。

| 检查对象 | 所核版本的条件 | 排查时的含义 |
|---|---|---|
| 功能开关 | `Feature::ImageGeneration` 开启 | 单独开启开关不能越过后续条件 |
| 账户计划 | 缓存认证信息的计划不为显式 `Free` | 代码只说明这一客户端检查，不能据此概括所有订阅入口 |
| Provider 能力 | 同时声明 `image_generation` 和 `namespace_tools` | 能调用普通文本模型不代表已暴露图片工具 |
| 主模型输入能力 | `input_modalities` 包含 `Image` | 这里检查的是主模型能否接收图片，不是在选择图片模型 |
| 认证路径 | 使用 OpenAI actor authorization，或要求 OpenAI 认证且当前身份使用 Codex backend | 普通 API-key 认证本身不满足后一条路径 |

不满足上述条件时，注册过程跳过 `image_gen.imagegen`。认证条件也不能简化成“仅允许 ChatGPT OAuth”：`Chatgpt`、`ChatgptAuthTokens`、`Headers`、`AgentIdentity`、`PersonalAccessToken` 都被归为 Codex backend 身份，普通 `ApiKey` 和所列 Bedrock 身份不属于这一组。

> 源码：[可用性检查](https://github.com/openai/codex/blob/73a1148c9c775c2a4616ce5096291740a00ed68a/codex-rs/core/src/tools/spec_plan.rs#L699-L735)、[注册过滤](https://github.com/openai/codex/blob/73a1148c9c775c2a4616ce5096291740a00ed68a/codex-rs/core/src/tools/spec_plan.rs#L1435-L1445)、[认证类型的 backend 分类](https://github.com/openai/codex/blob/73a1148c9c775c2a4616ce5096291740a00ed68a/codex-rs/protocol/src/auth.rs#L53-L63)。actor 分支另检查 provider 不要求普通 OpenAI 认证，且其 `http_headers` 中存在非空的 `x-openai-actor-authorization`；这是客户端的识别条件，不表示任意填写该 header 就能获得服务端授权，见 [actor helper](https://github.com/openai/codex/blob/73a1148c9c775c2a4616ce5096291740a00ed68a/codex-rs/model-provider-info/src/lib.rs#L539-L547)。

> OpenAI 在 [2026-09-08 的 Images 2.5 公告](https://openai.com/index/introducing-chatgpt-images-2-5/)中说明覆盖 ChatGPT、ChatGPT Work 和 Codex 的所有档位，而上述客户端快照仍保留显式 Free plan 排除条件。公告的产品覆盖范围与这份客户端实现之间的差异尚未解释；不能由其中一条推断所有当前 Free 用户在任意客户端都可用或都不可用。

确定本机工具是否实际注册后，再进行有授权的功能验证；工具列表和配置解析都不能代替真实图片请求的验收。

### <a id="image-request"></a>图片请求的构造

需要控制参考图、尺寸或质量时，应分清两个步骤：主模型先把文字要求和参考图选择交给内置工具，Codex 再替它组装发往图片服务的 HTTP 请求。工具没有让主模型填写的字段，也可能由 Codex 自动补入；下表描述的是客户端行为，不是当前最新图片模型列表。

截至 2026-09-10，公共 API 已提供 GPT Image 2.5，但以下 Codex 版本的内置工具仍填写 `gpt-image-2`，并将 `size`、`quality`、`background` 设为 `auto`：

| 核对对象 | 版本或提交 | 图片请求字段的核对结果 |
|---|---|---|
| 最新稳定版 | `0.153.4`，提交 `3d2ee51ca2d5db578f328aa75e20aa22c0197c9a` | 模型常量、工具参数及生成／编辑请求构造与原记录一致 |
| 近期预发布版 | `0.154.0-alpha.6.1`、`0.154.0-alpha.11` | 上述内容一致；alpha 标签不等于稳定版 |
| 当日主线 | `9caddc5cf5bf4df5f114498e23bece90eaedb37b` | 上述内容一致；没有改为发送 2.5 模型名称 |

> 版本与源码：[稳定版发布](https://github.com/openai/codex/releases/tag/rust-v0.153.4)、[稳定版请求构造](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/ext/image-generation/src/tool.rs#L409-L477)、[alpha.6.1 请求构造](https://github.com/openai/codex/blob/rust-v0.154.0-alpha.6.1/codex-rs/ext/image-generation/src/tool.rs#L409-L477)、[alpha.11 请求构造](https://github.com/openai/codex/blob/rust-v0.154.0-alpha.11/codex-rs/ext/image-generation/src/tool.rs#L419-L487)、[主线请求构造](https://github.com/openai/codex/blob/9caddc5cf5bf4df5f114498e23bece90eaedb37b/codex-rs/ext/image-generation/src/tool.rs#L419-L487)。这是源码片段对比，不是这些版本逐一进行过线上生图实测。公共 2.5 的实际模型名称见[公共 API 模型标识](image-gen.md#model-identifiers)。

主模型调用内置工具时，只能填写下面这些参数；图片请求中的其他字段由 Codex 补入。

| 工具参数 | 作用 | 所核版本的限制 |
|---|---|---|
| `prompt` | 图片生成或编辑要求 | 字符串；画面、比例、目标像素等意图在这里表达 |
| `referenced_image_paths` | 显式选择本地参考图片 | 最多五条绝对路径；通过当前 `ToolEnvironment` 的文件接口读取 |
| `num_last_images_to_include` | 从对话历史选择最近的图片 | 取值 1–5；不能与显式路径同时使用 |

参数结构拒绝未知字段，没有独立的 `model`、`size`、`quality`、`background` 或 `reasoning_effort` 参数。显式参考图路径受执行环境的访问能力约束，不等于可以读取任意本地文件；从历史中按最近张数选择时，也要核对图片身份，不能将它当作稳定的图片标识。

> 源码：[工具参数定义](https://github.com/openai/codex/blob/73a1148c9c775c2a4616ce5096291740a00ed68a/codex-rs/ext/image-generation/src/tool.rs#L87-L95)、[参考图解析及互斥条件](https://github.com/openai/codex/blob/73a1148c9c775c2a4616ce5096291740a00ed68a/codex-rs/ext/image-generation/src/tool.rs#L419-L487)。代码对无稳定引用的历史图片选择明确保留 best-effort 限制。

执行器根据是否带参考图片选择下游请求：无参考图时构造生成请求，带参考图时构造编辑请求。用户可以把任务描述为“参考这张图生成新画面”，但这个意图分类不会改变该实现带图时走编辑分支的事实。

以下是上述版本的 Codex **实际发给图片服务的字段**。生成请求不带参考图，编辑请求带参考图；两者的自动参数设置相同。

| 请求字段 | 字段的含义 | 生成请求填写什么 | 编辑请求填写什么 |
|---|---|---|---|
| `model` | 向后端请求的图片模型名称 | `gpt-image-2` | `gpt-image-2` |
| `prompt` | 画图或改图的文字要求 | 工具收到的文字 | 工具收到的文字 |
| `size` | 输出图片的像素尺寸 | `auto`，由图片服务选择 | `auto`，由图片服务选择 |
| `quality` | 图片生成的质量档位 | `auto`，未指定具体档位 | `auto`，未指定具体档位 |
| `background` | 透明或不透明等背景设置 | `auto`，由图片服务选择 | `auto`，由图片服务选择 |
| `n` | 希望返回的图片张数 | 不发送这个字段 | 不发送这个字段 |
| `images` | 提供给图片服务的参考图 | 不发送这个字段 | 发送参考图列表，每项使用 `image_url` 字段 |

`auto` 不是“最高质量”或“保证透明”，而是将对应选项交给图片服务决定。`n` 不发送也不是填了 0，不能仅据此断言服务端必定返回几张。`image_url` 是字段名，不一定是网上的图片链接；内置工具也会用 data URL 在这个字段中携带编码后的完整图片内容。

例如“把这张照片里的蓝色汽车改成橙色”，会成为一条带参考图和修改要求的编辑请求。Codex 会填写上述自动选项，但不会因为文字里写了“高清”就把独立的 `quality` 字段改成 `high`。

> 源码：[模型常量及工具参数](https://github.com/openai/codex/blob/9caddc5cf5bf4df5f114498e23bece90eaedb37b/codex-rs/ext/image-generation/src/tool.rs#L58-L95)、[生成和编辑请求构造](https://github.com/openai/codex/blob/9caddc5cf5bf4df5f114498e23bece90eaedb37b/codex-rs/ext/image-generation/src/tool.rs#L430-L487)、[请求字段的序列化](https://github.com/openai/codex/blob/9caddc5cf5bf4df5f114498e23bece90eaedb37b/codex-rs/codex-api/src/images.rs#L4-L36)。`n: None` 配合 `skip_serializing_if` 表示发出的 JSON 中省略该字段；这张表不适用于所有 CPA 配置或公共 API 客户端。

因此，“内置工具通过 prompt 表达尺寸意图”是这一工具入口的控制方式，不是图片模型的尺寸上限，也不是所有订阅 HTTP 客户端的规则。不要把下游带有 `size:"auto"` 的 JSON 当成模型可直接填写的工具参数；严格像素要求和实际输出的核对见 [图片参数对照](image-gen.md#model-parameters)。

同样，`gpt-image-2` 常量只能证明客户端发送了这个模型字符串。仅凭它不能判断服务端是否进行了别名映射、实际使用哪个模型快照，或是否已经承接某次产品升级。

> 主线的[图片响应结构](https://github.com/openai/codex/blob/9caddc5cf5bf4df5f114498e23bece90eaedb37b/codex-rs/codex-api/src/images.rs#L55-L72)包含图片数据、部分输出元数据及可选 `generation_id`。相比稳定版 0.153.4，主线新增了将生成 ID 保留到图片事件和分析记录的处理，见[对应提交](https://github.com/openai/codex/commit/929389f59696171f494e3105e56853ad2ec26c98)；这没有改变模型名称、尺寸或质量请求字段。生成 ID 用于关联图片，不是能够单独确认底层模型版本的证明。

### <a id="image-reasoning"></a>思考程度的作用范围

Codex 的思考程度控制主模型的推理过程。分析它对生图的影响时，要把主模型准备、选择和检查图片任务的工作，与图片请求自身的参数分开。

公共 Responses API 中，GPT-5.6 支持 `standard` 和 `pro` 两种 reasoning mode（推理模式），默认 `standard`。官方将 `pro` 用于需要更多模型计算、能够接受更高延迟和 token 用量的困难任务；`reasoning.effort` 独立控制所选模式中的推理强度。这是语言模型的 API 配置，Codex 或 ChatGPT 的选项仍需按各自客户端核对。

> 来源：[官方推理模式说明](https://developers.openai.com/api/docs/guides/reasoning)。图像输出档位见 [图片质量参数](image-gen.md#public-quality)。

在上述实现中，图片请求结构没有 `reasoning_effort`；`model_reasoning_effort=max` 不会被自动转换为 `quality=high`，也不是发给图片模型的计算档位。

| 情况 | 可以判断的影响 | 不能直接得出的结论 |
|---|---|---|
| 提示词、参考图和图片参数不变，只调整 Codex effort | 调整的是工具外的主模型推理配置 | 图片模型获得了更高计算预算 |
| 主模型改写了提示词 | 图片服务收到的输入发生变化，可能间接改变生成行为或耗时 | 提示词更长就一定更慢或画质更好 |
| 主模型检查结果后再次调用工具 | 图片请求次数增加，可能增加时间和额度消耗 | 每次新请求都是对上一张图的无成本优化 |
| 图片请求已经发出，再修改主模型配置 | 不会改写已经发出的这份图片请求 | 正在执行的图片任务会继承新的 effort |

> 此处是由 [内置请求构造](https://github.com/openai/codex/blob/73a1148c9c775c2a4616ce5096291740a00ed68a/codex-rs/ext/image-generation/src/tool.rs#L430-L487)和 [请求字段](https://github.com/openai/codex/blob/73a1148c9c775c2a4616ce5096291740a00ed68a/codex-rs/codex-api/src/images.rs#L4-L31)得出的客户端实现判断，不是 low/max 的画质对照实验。图片服务内部如何推理、调度和分配计算量，不能从这些字段反推。

判断某个任务是否需要更多前置推理，可以检查约束是否清楚、参考图角色是否明确、主模型是否在重复已有设计工作。需要量化收益时，应分别记录工具调用次数、最终发送的提示词、图片参数和结果；不要把这些同时变化的实验称为仅比较 effort。

### <a id="image-timing"></a>生图耗时的统计边界

“生图用了多久”取决于计时从哪里开始、在哪里结束。通过 MCP 驱动 Codex 时，外层工具耗时通常大于某一次内部图片请求，不能直接拿两者比较图片模型速度。

```text
上层调用方开始等待
  └─ MCP / SDK 驱动 Codex
       ├─ 启动或恢复、认证及任务准备（若发生）
       ├─ 主模型组织提示词、选择参考图
       ├─ image_gen.imagegen
       │    ├─ 参考图准备
       │    ├─ 图片 HTTP 请求与响应读取
       │    └─ 结果处理及产物保存
       ├─ 主模型检查、决定是否再调用、组织回复
       └─ 外层调用返回
```

| 测量位置 | 一般覆盖范围 | 比较时要注意什么 |
|---|---|---|
| 外层 MCP／SDK 调用 | 该次 Codex 任务中的准备、推理、工具调用和回复 | 一个外层调用可能包含多次图片请求；启动成本也可能因进程复用而不同 |
| 内部工具的完整执行 | 参数处理、参考图准备、图片请求及结果处理 | 不包含工具外的前后主模型推理，但仍不等于服务端纯生成时间 |
| 图片工具的开始／结束事件 | 由具体事件发出位置界定 | 不能不看实现就假定与完整工具执行窗口相同 |
| 图片 HTTP 请求 | 网络传输、上游等待、生成和响应接收等 | 没有服务端阶段数据时，无法可靠拆出纯模型计算时间 |

> 所核实现先执行 `request_for_call_args(...).await`，随后才发出图片开始事件并请求后端。因此从该开始事件计时，不包含此前的参考图准备，见 [事件发出位置](https://github.com/openai/codex/blob/73a1148c9c775c2a4616ce5096291740a00ed68a/codex-rs/ext/image-generation/src/tool.rs#L141-L171)。

记录耗时时应同时说明入口、计时点、图片请求次数和实际发送参数。网络中断、上游排队以及结果丢失的处理见 [图片请求的运行管理](image-gen.md#lifecycle)；本地停止计时不能证明上游任务已经停止。

### <a id="image-api-fallback"></a>API-key fallback 入口

Codex 随附的 `imagegen` skill 还包含公共 API 调用脚本。这个 fallback 是另一条执行路径，必须与内置 `image_gen.imagegen` 分开理解，不能因为内置工具没有某个参数就认为官方脚本也没有。

| 项目 | 内置图片工具 | API-key fallback 脚本 |
|---|---|---|
| 入口 | `image_gen.imagegen` | 随附 imagegen skill 的 `scripts/image_gen.py` |
| 认证 | 满足内置工具门控的 Codex 身份／provider 路径 | `OPENAI_API_KEY`，实际目标还受 SDK 和环境配置影响 |
| 图片模型 | 所核执行器固定为 `gpt-image-2` | 独立 `--model`；所核默认值为 `gpt-image-2` |
| 尺寸 | 执行器发送 `auto` | 独立 `--size`；所核默认值为 `auto` |
| 质量 | 执行器发送 `auto` | 独立 `--quality`；所核默认值为 `medium` |
| 操作 | 根据参考图选择生成或编辑请求 | `generate`、`edit`、`generate-batch` |

脚本的 `--model` 是图片请求参数，不是 Codex 主模型的选择参数。脚本创建 `OpenAI()`／`AsyncOpenAI()` 客户端，把模型、尺寸和质量分别装入 payload，最后调用 `images.generate` 或 `images.edit`。这不证明订阅 Responses 端点或 CPA 接受完全相同的参数组合。

> 源码：[fallback 模式定义](https://github.com/openai/codex/blob/73a1148c9c775c2a4616ce5096291740a00ed68a/codex-rs/skills/src/assets/samples/imagegen/SKILL.md#L12-L30)、[默认值](https://github.com/openai/codex/blob/73a1148c9c775c2a4616ce5096291740a00ed68a/codex-rs/skills/src/assets/samples/imagegen/scripts/image_gen.py#L25-L35)、[CLI 参数及分发](https://github.com/openai/codex/blob/73a1148c9c775c2a4616ce5096291740a00ed68a/codex-rs/skills/src/assets/samples/imagegen/scripts/image_gen.py#L928-L1025)、[生成和编辑调用](https://github.com/openai/codex/blob/73a1148c9c775c2a4616ce5096291740a00ed68a/codex-rs/skills/src/assets/samples/imagegen/scripts/image_gen.py#L734-L859)。

该随附 skill 要求用户明确选择或确认 CLI／API 路径；普通尺寸、质量和保存位置要求，以及内置工具失败，都不意味着自动切换。切换时应说明身份、请求目标及计费路径发生变化，不能悄悄从订阅调用转成公共 API。

脚本的校验也可能落后于公共 API。所核版本对 `model == "gpt-image-2"` 且 `background == "transparent"` 的组合直接报错，并建议另选 `gpt-image-1.5`；它不会自动替换模型。这是这一脚本版本的本地限制，不是所有内置工具、公共 API 或底层图片模型的统一限制。

> [模型特定校验](https://github.com/openai/codex/blob/73a1148c9c775c2a4616ce5096291740a00ed68a/codex-rs/skills/src/assets/samples/imagegen/scripts/image_gen.py#L181-L202)与 [显式切换要求](https://github.com/openai/codex/blob/73a1148c9c775c2a4616ce5096291740a00ed68a/codex-rs/skills/src/assets/samples/imagegen/SKILL.md#L23-L30)需同时阅读。公共 Image 2／2.5 参数及其版本范围另见 [公共 API 对照](image-gen.md#model-parameters)，不能用旧脚本的拒绝信息代替当前接口规范。

## <a id="cc-switch-multi-account"></a>多账号目录与共享会话

不同账号使用独立 `CODEX_HOME`、认证和后台；设置及本地历史是否共享另行决定。Codex 原生支持这种隔离，不需要像只支持整个 `HOME` 隔离的程序那样同时改变 Git、SSH 等工具的家目录。账号可以直接维护原生目录，也可以用 cc-switch 初始化后采用原生入口，或从既有目录迁移，见[原生目录迁移](#native-account-migration)。

下列 cc-switch 初始化流程使用 [SaladDay/cc-switch-cli](https://github.com/SaladDay/cc-switch-cli/tree/v5.11.1)，不是同名桌面客户端；于 2026-10-22 在 Linux / WSL、cc-switch `5.11.1`、Codex `0.163.0` 下实测，其他版本先核对 `--help`。后台选择与兼容恢复另按本文 `0.165.0` 的版本说明。

> `--shared-sessions` 自 5.11 起提供，5.10.1 报 `unexpected argument '--shared-sessions' found`。升级走官方自更新 `cc-switch update`（下载 release 资产并校验 updater 签名，2026-10-28 实测 5.10.1 → 5.11.3），或 install.sh（目标已存在时非交互覆盖需 `CC_SWITCH_FORCE=1`，Linux 自动选 musl 静态构建）。

> 新版首次写数据库时会把 `~/.cc-switch/cc-switch.db` 迁移到新 schema；有其他 cc-switch 进程（TUI / proxy worker）开着库时迁移拒绝执行并报出占用 PID，先退出这些进程再升级。旧版二进制打不开迁移后的库，回退前先备份整个 `~/.cc-switch/`。

### <a id="cc-switch-storage"></a>账号与存储边界

`CODEX_HOME` 只重定向 Codex 自身的数据，不替换整个 `HOME`。这里隔离的是文件式认证；环境变量或外部宿主另行注入的身份仍须核对，不能仅凭目录不同判定账号不同，见 [凭据的存储形式](#auth-storage)。cc-switch 的 `start codex … --shared-sessions` 为每个 provider 建立持久目录，默认形态为 `<source-home>/.cc-switch-launches/<SHA256(provider-id)>`；实际位置以 `--dry-run` 返回值为准。

| 对象 | `--shared-sessions` 的处理 |
|---|---|
| `config.toml`、`auth.json`、`.auth-source` | 留在各 provider 的独立目录；生成配置指定 `cli_auth_credentials_store = "file"` |
| 会话、归档、线程写锁、rollout 迁移目录 | 分别软链接到源目录的 `sessions`、`archived_sessions`、`thread-writer-locks`、`rollout-migrations` |
| `.tmp/rollout-maintenance.lock` | 链接到源目录的维护锁 |
| SQLite 会话索引 | 用 `sqlite_home` 指向按源配置解析出的共享目录，不必等于源 `CODEX_HOME` |
| `session_index.jsonl` | 各目录保留本地缓存，不做软链接；Codex 会原子替换它 |
| 用户级主指令 | 共享目录清单未包含 `AGENTS.md` 或 `AGENTS.override.md`；按实际 `CODEX_HOME` 单独配置 |

共享历史意味着不同账号入口可访问同一批本地会话内容，归档、删除等操作也会影响这批共享数据。它适用于已获准共享历史的账号，不是用户间的数据隔离。创建新账号入口时保持凭据为空，由用户在新入口独立登录；不要复制或链接已有账号的认证文件，也不要把整个源目录复制一遍。

共享设置或数据库不等于共享后台。官方订阅请求的额度由后台实际采用的上游身份及工作区规则决定；把名为账号 B 的客户端强制连接到已登录账号 A 的后台，单改客户端 `CODEX_HOME` 不会自动把 B 的认证交给远端。多账号方案应逐个核对后台读回的身份与所属目录，而不只看函数名或独立文件。相同授权分散到多个后台仍不会增加上游额度，代理入口也不是额度池。跨账号恢复还要分别处理旧后台的写锁与 goal 的继续状态：Interrupt 不等于释放会话，打开历史也不等于授权 goal 继续，具体检查顺序见[多账号恢复与 goal 生命周期](codex-monitoring.md#account-resume)。

> 账号用量与第三方本地统计的边界见[账号活动与额度](#usage-accounting)。一个账号后台承载多条会话，与每条会话各建一套后台是不同的资源组织方式，见[普通启动的连接方式](#app-server-routing)。

> 源码：[目录命名与共享配置](https://github.com/SaladDay/cc-switch-cli/blob/v5.11.1/src-tauri/src/cli/codex_shared_launch.rs#L98-L165)、[共享目录、索引与维护锁](https://github.com/SaladDay/cc-switch-cli/blob/v5.11.1/src-tauri/src/cli/codex_shared_launch.rs#L217-L253)。同一授权被复制到不同目录仍可能竞争刷新，见 [访问令牌的刷新](#auth-refresh)。

### <a id="cc-switch-initialize"></a>创建与初始化

先确认当前 shell 的 `CODEX_HOME`、已有启动函数及 cc-switch 的默认 provider，记录现有配置状态；确认账号隔离和历史共享范围后，再执行创建。下面的 `<provider-id>`、`<account-label>` 都需替换，ID 应选尚不存在的值：

```bash
cc-switch -a codex provider list
cc-switch -a codex provider current
cc-switch -a codex provider add --template openai-official \
  --id '<provider-id>' --name '<account-label>'
cc-switch start codex '<provider-id>' --shared-sessions --dry-run
cc-switch start codex '<provider-id>' --shared-sessions -- --help
```

`--dry-run` 只预览，不生成启动目录；最后一条才初始化持久目录、共享链接和空凭据来源标记，并运行原生 Codex 帮助后退出，不执行登录或模型任务。这两条启动命令不切换全局当前 provider。若只需要完全独立的历史，可以直接使用专用 `CODEX_HOME`，无需引入共享目录结构。

`--dry-run` 会打印解析出的 `CODEX_HOME` 与 `Shared history:` 源目录；5.11.3 生成的 launch `config.toml` 也会显式写入解析出的 `sqlite_home`。初始化后把这两处与源配置、[账号与存储边界](#cc-switch-storage)的表格互相核对，即可确认共享范围符合预期。

通常各账号共用同一套设置时，可以在初始化后，把各自的 `$CODEX_HOME/config.toml` 软链接到默认配置。先核对配置差异，确认共用的权限策略，备份并移走已有配置，再建立链接；下面两个目录都替换为实际绝对路径，源目录通常是 `~/.codex`：

```bash
ln -s '<source-codex-home>/config.toml' '<isolated-codex-home>/config.toml'
```

以后统一维护源配置，修改会影响所有使用它的入口；`auth.json` 继续各自独立。沿用本节的共享历史方案时，建立配置软链接前，须在源配置的顶层显式保留同一个数据库目录，或由各入口通过启动参数指定；下面替换为已有共享数据库的实际绝对路径，通常为源 `CODEX_HOME`，以原配置为准：

```toml
sqlite_home = "<shared-sqlite-home>"
```

仅有 `sessions` 软链接不足以共享历史数据库。丢失 `sqlite_home` 后，新进程会改用各自 `CODEX_HOME` 下的数据库并补建会话索引，可能在启动时提示 `state db backfill is running`、等待或超时。恢复时先核对新库是否有原共享库没有的会话，再把配置指回已有共享数据库；切换路径本身不迁移或合并数据，保留新库供核对。完成后验证新进程实际解析出的数据库路径和交互式启动，不能只检查配置语法或已有进程。

每个独立 `CODEX_HOME` 还需要用户级主指令入口。共用本仓规则时，将主文件链接到 `<repo>/AGENTS.md`；`<repo>` 是实际的 skills 仓库根目录。先核对源文件与目标入口，保留已有内容，并检查非空 `AGENTS.override.md` 是否会优先生效。确认目标入口不存在后执行：

```bash
ln -s '<repo>/AGENTS.md' '<isolated-codex-home>/AGENTS.md'
```

共享 `config.toml` 与用户级指令是两条独立的加载路径。Codex `0.165.0` 内部记录文件来源，但模型可见消息会合并指令正文；单个项目环境的外层目录来自该环境的 cwd，仅有全局指令时可省略目录。本仓共享主文件明确要求读取固定的 `~/.agents/AGENTS.local.md`，各账号共用这份普通文件；本地补充的位置由当前用户家目录确定。这样保留“主文件要求继续读取本地补充”的约定，并明确补充文件的查找依据。

> 源码：[用户级读取与来源记录](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/codex-home/src/instructions/mod.rs#L40-L83)、[模型可见正文拼接](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/core/src/agents_md.rs#L377-L419)、[外层目录与内部来源列表](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/core/src/agents_md.rs#L473-L498)。完整安装约定见[共享指令与发现入口](../../../../README.md#agent-instructions)。

官方订阅入口使用 `openai-official` 模板，它以空 `auth` 和配置创建 provider；这里不需要填写 API key 或 Base URL。`5.11.1` 的官方模板不接受 `--config` / `--config-file` 或模型、API 字段覆盖，模型等本地设置在初始化后单独配置。默认的 `custom` 创建路径按第三方端点校验，把只含原生官方设置的 `{"auth": {}, "config": "…"}` 直接传给它会因缺少有效 Base URL 被拒绝；应改选官方模板，而不是给订阅入口编造端点。

> 源码：[官方模板的空初始配置](https://github.com/SaladDay/cc-switch-cli/blob/v5.11.1/src-tauri/src/cli/commands/provider_input.rs#L519-L529)、[凭据与配置的构造](https://github.com/SaladDay/cc-switch-cli/blob/v5.11.1/src-tauri/src/cli/commands/provider_input.rs#L2744-L2759)、[官方模板的字段限制](https://github.com/SaladDay/cc-switch-cli/blob/v5.11.1/src-tauri/src/cli/commands/provider.rs#L1620-L1650)。上述 `custom` 校验错误也在本次初始化中实测。

### <a id="cc-switch-launch"></a>启动入口与多开

两种入口的管理职责不同：

| 入口 | 启动与退出时的处理 | 同 provider 多开 |
|---|---|---|
| `cc-switch start codex '<provider-id>' --shared-sessions` | 从 provider 重新生成配置，持有目录级 `.lock`；原生进程退出时将登录状态回写到该 provider | `5.11.1` 对同目录第二个此类启动直接报已有活动实例 |
| 包装函数指定已初始化的 `CODEX_HOME`，直接运行 `codex` | 使用目录现有配置与凭据；不经过 cc-switch 的配置生成、目录级启动锁和退出回写 | 可沿用原生 Codex 的多实例机制，但同一线程仍受共享写锁约束 |

如果需要原生多开，可给每个账号建立直接入口。下面仅示意已完成登录、确认使用官方 provider 的账号目录；文件式认证在该目录的用户级配置中设置 `cli_auth_credentials_store = "file"`，新会话可使用原生默认 `openai`：

```bash
codex-account() {
    CODEX_HOME='<isolated-codex-home>' command codex "$@"
}
```

实际入口若依赖显式代理，应在调用 `codex` 前准备环境，见[启动环境与后台托管](#app-server-environment)。函数只在加载过它的 shell 中可用；需要让非交互 SSH、Agent 等调用时，可以把同样的入口放入 PATH 内的可执行脚本。两种形态都不依赖 cc-switch 运行时。只有继续使用 cc-switch 初始化或同步的部署，才需要用 provider id 对应其哈希目录；原生目录可以使用自己的稳定名称。

旧 cc-switch 历史可能保存 `custom` provider。`0.165.0` 中，普通用户配置文件内的 `model_provider = "openai"` 不等于恢复请求的显式覆盖，服务端可能继续采用线程持久化的 provider。对已确认应恢复为官方入口的旧线程，可使用以下兼容路线：

```bash
CODEX_HOME='<account-home>' codex app-server daemon start &&
CODEX_HOME='<account-home>' codex --remote unix:// \
    -c 'model_provider="openai"' resume '<thread-id>'
```

先启动后台再显式连接，才能同时保留覆盖与共享后台；仅保留 `-c` 会触发[隐式路线排除](#app-server-routing)。已有入口若一直依赖该覆盖，可在 `resume`／`fork` 兼容分支中应用它；恢复按 UUID 查找可避开名称／列表的 provider 过滤。这个覆盖还会采用当前配置的模型和强度，因此需要保留各线程原设定的部署，应只对确认需要兼容的历史启用。第三方端点保留其原路由，不能统一强制为 `openai`。

> 来源：[显式 provider 的来源判定](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/tui/src/app_server_session/provider_selection.rs#L8-L37)、[恢复请求携带 provider](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/tui/src/app_server_session/rollout_history.rs#L167-L222)、[模型组覆盖](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/tui/src/app_server_session.rs#L2258-L2291)。活动或仍有订阅者的已加载线程可能忽略不兼容覆盖，见[重连与重载条件](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/app-server/src/request_processors/thread_processor.rs#L4691-L4745)；不能靠改标题或客户端参数认定它已经换了路由。

> 源码：[目录级启动锁](https://github.com/SaladDay/cc-switch-cli/blob/v5.11.1/src-tauri/src/cli/codex_shared_launch.rs#L186-L215)、[受管启动的退出回写、provider 与存储覆盖](https://github.com/SaladDay/cc-switch-cli/blob/v5.11.1/src-tauri/src/cli/codex_shared_launch.rs#L283-L309)。共享模式还拒绝透传 `-c` / `--config`、`--profile` 和 `--oss`，见 [参数门禁](https://github.com/SaladDay/cc-switch-cli/blob/v5.11.1/src-tauri/src/cli/codex_shared_launch.rs#L25-L40)；需要这些覆盖时先选择并理解直接启动方式。

模型、思考强度和 `[tui]` 等非凭据设置可以按需单独配置；终端显示见 [终端界面与 Zellij Web 复制](#terminal-clipboard)。权限策略也应单独确认：`--sandbox danger-full-access --ask-for-approval never` 会授予全权限并关闭确认，不是多账号隔离的前提，不能从旧账号默认照搬。不同入口使用同一账号时，不要同时让 cc-switch 重新生成目录配置；同一共享线程也只允许一个活动写者。

### <a id="cc-switch-sync"></a>配置与凭据同步

cc-switch 的 provider 数据和持久目录是两个维护位置。直接启动后，Codex 的登录与刷新留在该目录，**不会自动执行 cc-switch 的退出回写，也不等于进入了 `cc-switch auth` 管理的账号库**。判断此入口是否登录，应执行同一包装函数的 `login status`。

再次经过 cc-switch 启动时，`config.toml` 会按 provider 配置重新生成，仅保存在持久目录的模型或界面修改可能被覆盖。认证另用 `.auth-source` 记录 provider 凭据的摘要：摘要未变时保留目录内的刷新 / 退出登录结果；provider 侧凭据显式变化时重新同步，变为空时会移除原认证文件。因此维护时应先确认实际入口、配置来源和活动进程，保留非凭据配置差异，再决定同步方向；不要用“重新启动”代替这一步判断。

若 `config.toml` 已软链接到共享配置，重新生成前还应核对链接及其目标，防止覆盖共享源文件；重建后复核链接是否保留。

> 源码：[配置重建与凭据来源检测](https://github.com/SaladDay/cc-switch-cli/blob/v5.11.1/src-tauri/src/cli/codex_shared_launch.rs#L253-L279)、[退出时仅回写认证](https://github.com/SaladDay/cc-switch-cli/blob/v5.11.1/src-tauri/src/cli/codex_shared_launch.rs#L283-L309)。本节不提供直接改写 cc-switch 数据库的流程。

### <a id="native-account-migration"></a>既有账号迁到原生目录

已初始化的账号目录可以脱离 cc-switch 使用。先定位实际入口、认证存储、共享配置与 SQLite、后台进程和会话树，再迁到稳定的独立目录，例如 `$HOME/.codex-homes/<account>`；迁移目录本身不创建新授权，也不改变上游额度。

1. **协调使用者**：检查该账号所有 CLI、后台、子会话、工具进程、持久队列和 goal。运行任务继续保留；确认空闲后通过原生退出关闭旧使用者，验证旧进程与写者已释放，再移动。不要复制活跃认证后让两份实例并行刷新同一授权。
2. **保留状态**：文件式认证可随原目录迁移，保持所有权、权限和内容；有效授权通常无需重新登录，过期／吊销或 keyring 存储另行处理。保留历史链接、维护锁、SQLite 设置、主指令和 override，不能只搬认证文件。数据库仍有使用者时，不把单独复制主文件当成完整 WAL 快照。
3. **兼容历史路径**：检查共享索引是否记录旧目录前缀。需要时在旧位置保留用于旧路径读取兼容的历史链接，使已记录 rollout 路径继续可读；软链接仍按共享目标权限读写，不提供只读隔离。旧入口退出使用，不把整个旧目录软链到新账号家目录而继续让 cc-switch 改写。不要为了搬家批量重写历史正文或 SQLite 路径。
4. **切换入口**：更新函数／脚本到新 `CODEX_HOME`，由该账号创建自己的后台。原子替换脚本后重新核对所有者与可执行位，配置和凭据维持私有权限；不要假定文本写入工具保留了文件模式。已有交互 shell 需重新加载函数，非交互调用核对实际脚本；默认账号和无关后台保持不动。共享数据库和写锁仍只允许同一线程一个后台写者，跨账号续聊前需通过原生生命周期释放旧后台的占用。
5. **分层验证**：先核认证与共享路径，再从实际终端环境验证新后台身份、代理和历史读取，使用确认已空闲的持久会话测试恢复，最后在获准后单独验证模型请求。空白 TUI 尚未产生持久 rollout 时，退出提示中的 UUID 不足以构成有效 resume 测试。

> 🔬 2026-10-28，Linux／WSL、Codex `0.165.0`：三个账号目录以保持认证文件内容与 inode 的方式迁移，共享设置和历史保留；新后台身份与代理读回匹配，TUI 启动和一条既有会话恢复通过，默认后台未重启。未提交新模型任务，未逐条启动所有历史，也未做系统冷启动或大规模会话压力测试。曾遇到空白诊断线程没有持久 rollout，改用刚完成且无队列／goal 的既有会话验收。

共享默认配置时还要核对文件的加载层级。以用户家目录为 cwd、将默认目录的配置链接给另一个 `CODEX_HOME` 时，同一文件也可能被发现为项目层；该环境曾对冗余 `model_provider` 报 `Ignored unsupported project-local config keys`。新官方会话沿用原生默认值即可，需要选择其他 provider 时按实际用户配置与来源验证，不靠忽略警告判断生效。

> `0.165.0` 的 Unix 控制 socket 在账号目录中公布别名，实际绑定路径在受保护的临时目录中按规范化路径哈希生成，因此“账号目录长就一定无法启动 daemon”不适用于该版本。短目录便于管理，但不应把软链改名或缩短路径当成已证实的路由超时解法，见[绑定与别名](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/app-server-transport/src/transport/unix_socket.rs#L101-L142)及[物理端点生成](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/app-server-transport/src/transport/unix_socket.rs#L354-L367)。

### <a id="cc-switch-verification"></a>验收

把配置完成、用户登录和真实模型请求分开验收：

- **配置完成**：shell 语法检查通过，实际终端能解析包装函数，`--version` / `login --help` 正常；独立目录和认证路径不是指向其他账号的软链接，共享链接与 `sqlite_home` 均指向预期位置；原启动函数、配置及全局当前 provider 不变。
- **指令加载**：核对每个实际 `CODEX_HOME` 的主文件与 override，确认链接有效且内容可读；有本地补充时，核对固定路径 `~/.agents/AGENTS.local.md`，并从仓库外核对主文件注入与补充文件的读取。将主文件自动注入、本地补充由模型继续读取、已实际完成读取分别报告，文件存在本身只证明入口已配置。
- **登录前**：在空凭据、文件存储且无其他认证注入的方案下，初始化后没有认证文件，`codex-account login status` 返回 `Not logged in` 和退出码 1。此时还没有验证账号或模型可用性。
- **用户登录后**：用户通过 `codex-account` 内的登录入口或 `codex-account login --device-auth` 独立授权，再检查同入口的登录状态和账号；不让用户把 token 粘贴进对话。
- **实际使用**：在获准后做最小模型请求，并分别核对所需历史可见性、resume 和不同线程并行使用；初始化、帮助命令及配置文件存在都不能替代这些测试。

> 2026-10-22 的实测范围包括空凭据初始化、共享链接 / 配置检查、shell 入口和原生帮助、未登录状态，以及既有配置和默认 provider 未变化的核验；未代用户登录，也未验证登录后的模型请求或所有 resume / 并行场景。

## <a id="subscription-auth"></a>订阅登录凭据

复用 Codex 订阅生图时，先确认身份从哪里取得、谁负责更新以及调用方会写回什么。能读取一份登录材料，只说明取得了凭据，不等于它适用于任意 OpenAI 端点，也不等于可以让多个程序独立刷新同一授权。

### <a id="auth-storage"></a>凭据的存储形式

Codex 的身份可能来自文件、系统凭据存储或外部宿主。先检查所用客户端的认证来源，再设计适配；不要把“没有某个本地文件”直接判成未登录。

文件式认证使用 `$CODEX_HOME/auth.json`。所核 `AuthDotJson` 可以表示 API key、ChatGPT tokens、Agent Identity、Personal Access Token 等不同形态；`tokens` 是可选字段，不能要求所有合法登录文件都包含同一套 OAuth 字段。

| 文件式 ChatGPT 登录字段 | 含义 | 图片接入时的处理 |
|---|---|---|
| `auth_mode` | 认证模式 | 用于识别当前身份形态，不能仅靠文件名判断 |
| `tokens.access_token` | 访问令牌，供上游验证请求身份 | 只发往预期且被授权的服务目标，不写入提示词或普通日志 |
| `tokens.refresh_token` | 刷新访问令牌的凭据 | 由明确的刷新组件持有，不因另一个程序需要生图就整份复制 |
| `tokens.id_token` | 登录身份声明 | 不能当作访问图片接口的 bearer token 随意替换 |
| `tokens.account_id` | 可选的账户／工作区标识 | 使用经核实的当前账户；字段缺失时由认证组件按支持的方式解析，不猜测 |
| `last_refresh` | 最近刷新记录 | 是维护信息，不独立证明访问令牌当前有效 |

> 源码：[认证文件结构](https://github.com/openai/codex/blob/73a1148c9c775c2a4616ce5096291740a00ed68a/codex-rs/login/src/auth/storage.rs#L39-L65)、[嵌套 TokenData](https://github.com/openai/codex/blob/73a1148c9c775c2a4616ce5096291740a00ed68a/codex-rs/login/src/token_data.rs#L10-L25)。这些是该文件式登录结构，不是对所有外部认证来源的字段要求。

解析凭据时应检查 JSON 是否为对象、所需字段的类型是否正确，并区分格式错误、缺少身份和上游认证失败。读取 JWT 的 `exp` 可用于本地到期诊断，但解码 payload 不等于校验签名或证明权限；其他合法身份形态也不应被一个只支持 JWT 的适配器误判为无效。

共享文件的更新还涉及缓存。所核 `AuthManager` 不会在任意外部文件变化后立即更新全部内存状态，调用方需要使用其重载机制；不能因为文件已换成新令牌，就假定所有常驻客户端已经采用它。

> [AuthManager 的缓存说明](https://github.com/openai/codex/blob/73a1148c9c775c2a4616ce5096291740a00ed68a/codex-rs/login/src/auth/manager.rs#L2045-L2068)将外部变化的观察与显式 `reload()` 区分开来。文件格式、缓存更新和网络请求是不同失败位置，应分别给出诊断。

### <a id="auth-refresh"></a>访问令牌的刷新

访问令牌用于发请求，刷新令牌用于向授权服务申请新的访问令牌。这里的“刷新”维护的是登录状态，不是订阅续费，也不是重新提交图片任务。

刷新服务可能同时发回新的 refresh token。若多个程序持有同一份旧刷新凭据并各自刷新，它们可能互相竞争；某个程序得到新凭据后，另一个程序仍使用旧值，可能遭遇刷新失败或需要重新认证。不同本地文件路径不会改变这些凭据来自同一授权的事实。

> OAuth 对刷新令牌的用途和刷新请求定义见 [RFC 6749](https://www.rfc-editor.org/info/rfc6749/#section-6)；刷新令牌轮转及重用检测的安全背景见 [RFC 9700](https://www.rfc-editor.org/info/rfc9700/#section-4.14.2)。是否轮转以及失效范围由具体授权服务决定，不能写成每次并发刷新必然导致所有客户端掉线。

所核 Codex 的刷新流程有实例内协调：先取得 `AuthManager` 的刷新许可，再从当前认证来源进行账户匹配的重载。若重载发现凭据已变化，就跳过一次重复刷新；未变化时才请求认证来源刷新。外部宿主提供的认证通过对应外部机制更新，不应被图片适配层一律改成直接发送 OAuth 刷新请求。

> 源码：[实例内 `refresh_lock`](https://github.com/openai/codex/blob/73a1148c9c775c2a4616ce5096291740a00ed68a/codex-rs/login/src/auth/manager.rs#L2049-L2067)、[重载后再决定刷新](https://github.com/openai/codex/blob/73a1148c9c775c2a4616ce5096291740a00ed68a/codex-rs/login/src/auth/manager.rs#L2799-L2836)、[认证来源分流](https://github.com/openai/codex/blob/73a1148c9c775c2a4616ce5096291740a00ed68a/codex-rs/login/src/auth/manager.rs#L2852-L2887)。这里的信号量属于一个 `AuthManager` 实例，不能据此宣称其他独立进程都遵守同一把刷新锁。

评估长期运行能力时，应检查刷新失败如何暴露、旧凭据如何失效、新凭据怎样保存和被其他调用方重新读取。原子写文件可以减少半写状态，但不能单独解决服务端刷新令牌轮转的竞争；“支持自动刷新”和“能够安全共享同一授权”需要分别验证。

### <a id="auth-sharing"></a>跨程序复用凭据

给其他工具或 CPA 等代理接入 Codex 身份时，可以按凭据所有权区分方案。下面是接入条件的比较，不表示任意组件都提供了全部方式。

| 方式 | 谁维护登录和刷新 | 新组件得到什么 | 需要核对的条件 |
|---|---|---|---|
| 由宿主提供认证 | 已有宿主或认证服务 | 当前可用身份，必要时通过宿主请求刷新 | 宿主接口、授权范围、取消和错误传播是否清楚 |
| 只读现有登录，提取短期访问令牌 | 原登录环境 | 所需 access token 和经核实的账户信息 | 不回写原文件；过期后由原持有者刷新，并让新组件重新读取或同步 |
| 新组件独立完成授权 | 各组件维护各自取得的授权 | 各自的凭据和保存位置 | 确认是新的授权流程，而非复制同一个 refresh token；同时遵守上游会话政策 |

只读短期令牌可以避免新组件争抢刷新，但它本身不是永久无人值守续期方案。需要适配格式时，应只提取必要字段，并为输出凭据设置独立、受限的存储位置；不要让另一套程序直接写回不兼容的原始文件。

CLIProxyAPI v7.2.155 是格式差异的一个例子：其 Codex 文件认证采用顶层字段，不直接消费 Codex 原文件的 `tokens.*` 结构。

| 含义 | Codex 文件式登录 | CPA 扁平凭据 |
|---|---|---|
| Provider 类型 | 由认证模式及运行配置识别 | `type: "codex"` |
| 访问令牌 | `tokens.access_token` | `access_token` |
| 账户信息 | `tokens.account_id`，或由认证组件核实 | `account_id` |
| 刷新令牌 | `tokens.refresh_token` | 仅在 CPA 拥有该授权的刷新责任时提供 `refresh_token` |

不提供刷新令牌的独立扁平凭据，其最小结构可以表示为：

```json
{
  "type": "codex",
  "access_token": "<ACCESS_TOKEN>",
  "account_id": "<ACCOUNT_ID>"
}
```

`expired`、`last_refresh`、`request_retry` 等字段属于时效或策略信息，不应与上表的身份字段混为一谈。在未配置其他刷新来源的扁平凭据分支中，无 refresh token 的 CPA 刷新调用会返回原认证对象，不会替它取得新访问令牌；令牌到期后仍需由既有持有者刷新并重新同步。

> CPA 源码：[访问令牌读取及刷新分支](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/internal/runtime/executor/codex_executor_auth.go#L15-L69)。该函数先尝试其他认证来源的刷新入口，再处理扁平 `refresh_token`，所以“没有顶层 RT”不能概括所有 CPA 认证接入方式。上述最小结构只讨论独立扁平凭据；没有在此承诺后台自动续期。

不能把 CPA 的 `auth-dir` 指向或软链接到 Codex 原登录目录来代替适配。格式不同，而且拥有刷新能力的组件还可能写回令牌。复制 RT 到新目录只隔开了文件，不会把原授权变成两个独立授权。

> CPA 有 RT 时更新访问令牌、刷新令牌和到期等信息，并由其认证存储落盘，见 [刷新后的元数据](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/internal/runtime/executor/codex_executor_auth.go#L23-L54)及 [文件存储写回](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/sdk/auth/filestore.go#L123-L149)。单一刷新所有者是协调这种接入的设计方式，不是 CPA 自动强制建立的跨进程独占关系。

凭据准备完成后，再进入 [CPA 配置和图片接口调用](image-gen.md#cpa)。CPA 的调用方 key 只保护本机代理入口，应与上游订阅凭据分别管理；参数转换成功、登录文件未被改动和真实图片请求成功，也应作为不同验收项记录，见 [接入验证](image-gen.md#verification)。
