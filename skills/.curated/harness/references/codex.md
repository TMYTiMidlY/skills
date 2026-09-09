# Codex 运行时笔记

本篇介绍 Codex 的 app-server 启动与生命周期、升级排障、上下文配置、协作模式、内置生图工具和订阅登录凭据。图片生成和编辑的区别、遮罩、外部应用接入及 CLIProxyAPI 调用和并发处理见 [Codex 订阅生图接入](image-gen.md)。

## <a id="app-server-lifecycle"></a>app-server 与客户端启动

app-server 承载会话和模型请求；TUI 是终端交互界面；daemon 管理器负责特定后台进程的启动和停止。这些对象要分别识别：**某个 app-server 可以被 TUI 发现和连接，却不受 daemon 管理器控制**。仅确认 `codex --version` 是新版，不能判断实际处理会话的后台版本。

> 本节以事故时的稳定版 [`0.153.4`](https://github.com/openai/codex/tree/rust-v0.153.4)（提交 `3d2ee51ca2d5db578f328aa75e20aa22c0197c9a`）解释现场，并对照本次抓取的主线 `87cf20ee491a035036f2d905926df4a0d35951cc`。主线代码不代表这些行为都已发布到稳定版；历史结论来自 2026-09-09 Linux 会话及对应 systemd journal 的回读，不是本轮重新关停生产服务的实测。

### <a id="app-server-routing"></a>客户端连接的选择

“有没有开启 app-server”不足以描述启动方式。TUI 可以运行进程内 app-server，也可以连接既有服务；共享模式使多个新终端继续使用同一个后台的版本和启动环境。

| 入口 | 所核版本中的选择 | 排障时的含义 |
|---|---|---|
| 普通 TUI，满足自动复用条件，默认控制 socket 可连接 | 连接本地既有 app-server | 新终端可能继续连旧后台；发现过程不要求有效 daemon PID 记录 |
| TUI 未指定远端，也没有可复用的默认 socket，或启动覆盖项不满足复用条件 | 启动进程内 app-server | 使用当前启动的程序，与共享路径要分开验收 |
| 显式 `--remote` | 使用指定的 app-server 端点 | 应检查该端点，而不是另一个默认本地 daemon |
| `codex exec` | 此处核对的稳定版和主线均启动 `InProcessAppServerClient` | 一次 exec 成功不能证明普通 TUI 所连接的后台已修好 |

> 源码：[0.153.4 的 socket 探测及客户端创建](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/tui/src/lib.rs#L447-L509)、[连接选择与复用条件](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/tui/src/lib.rs#L860-L930)、[稳定版 exec 入口](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/exec/src/lib.rs#L811-L816)、[主线 exec 入口](https://github.com/openai/codex/blob/87cf20ee491a035036f2d905926df4a0d35951cc/codex-rs/exec/src/lib.rs#L973-L979)。不能将这些入口的实现扩展成所有 SDK、IDE 和自定义客户端的统一规则。

0.153.4 常规路径的自动复用检查包括 `-c` 覆盖、配置加载覆盖、strict config 和不可重放的启动项；`-m` 本身并不等于强制启动新后台，`--agents` 的选择路径也有例外。因此比较测试应保持入口和参数一致，不要一边用普通 TUI、一边用额外 `-c` 或 exec，却把差异全归因于模型权限。

> [0.153.4 的启动编排](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/tui/src/startup_orchestration.rs#L138-L190)。主线另加入 `CODEX_EXEC_SERVER_URL` 阻止隐式复用的条件，并在隐式 daemon 初始化连接失败时回退到进程内服务；显式远端失败仍报错，见 [主线目标选择](https://github.com/openai/codex/blob/87cf20ee491a035036f2d905926df4a0d35951cc/codex-rs/tui/src/lib.rs#L926-L953)和 [连接失败分支](https://github.com/openai/codex/blob/87cf20ee491a035036f2d905926df4a0d35951cc/codex-rs/tui/src/lib.rs#L495-L538)。这里没有把“后台较旧但能初始化”自动视为连接失败。

模型菜单沿实际连接取得数据：TUI 向所选 app-server 请求 `model/list`，不是单纯显示新装 CLI 附带的目录。模型管理器请求远端目录时使用自身编译版本，并按版本校验文件缓存。换二进制、清缓存、改默认模型是不同层面的动作，均不能自动替换已经运行的旧进程；目录仍受认证、可见性和刷新结果影响，也不能认为菜单缺一项必定是旧进程。

> 源码：[TUI 取得模型目录](https://github.com/openai/codex/blob/87cf20ee491a035036f2d905926df4a0d35951cc/codex-rs/tui/src/app_server_session.rs#L574-L629)、[稳定版目录请求的版本参数](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/models-manager/src/manager.rs#L412-L434)、[缓存版本检查](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/models-manager/src/manager.rs#L478-L510)、[编译版本来源](https://github.com/openai/codex/blob/87cf20ee491a035036f2d905926df4a0d35951cc/codex-rs/models-manager/src/lib.rs#L18-L26)。

### <a id="app-server-ownership"></a>版本与进程归属

先在获准访问目标宿主的执行环境中，确认命令路径和同一个 `CODEX_HOME` 的状态：

```bash
command -v codex
codex --version
codex app-server daemon version
```

| 输出字段 | 实际含义 | 不足以证明的事情 |
|---|---|---|
| `cliVersion` | 正在执行管理命令的 CLI 版本 | 长期运行的后台已升级 |
| `managedCodexPath` / `managedCodexVersion` | 管理器解析的安装路径及文件版本 | 既有进程正在执行该文件的新内容 |
| `appServerVersion` | 从控制 socket 的 initialize 握手取得的后台版本 | 管理器拥有该进程，或其他 WS 服务版本相同 |
| `backend: "pid"` | 管理器检测到对应 PID backend 状态 | 它是 systemd 服务、具备开机自启，或独立 WS 服务也受它管理 |
| `status: "running"` 但没有 `backend` | socket 可响应，但管理器未识别到有效 PID backend | daemon restart 能接管并替换现有服务 |

> 源码：[可选字段省略规则](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/app-server-daemon/src/lib.rs#L55-L73)、[version 的两路检测](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/app-server-daemon/src/lib.rs#L438-L448)、[握手版本的来源](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/app-server-daemon/src/client.rs#L34-L60)。`pid` 字段在 version / alreadyRunning 中也可能省略，不能把“无 pid”与“无 backend”混同。PID 记录和 socket 响应独立检测，现场仍需把记录与实际监听者、UID、启动时间和可执行文件对应起来。

在 0.153.4 中，start 发现 socket 已能握手，就可以返回 `alreadyRunning`，即使没有 PID backend；restart 和 stop 则显式拒绝这个未受管的服务：

```text
app server is running but is not managed by codex app-server daemon
```

所以“能连上”“start 成功返回”和“能由 daemon 停止”是不同条件。反复调用 start 不会自动接管旧监听者；不能伪造 PID 文件或删除正在使用的 socket 来掩盖归属问题。探测失败也不能证明没有监听者，应继续区分权限、握手失败与服务无响应。

> 源码：[稳定版 start / restart](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/app-server-daemon/src/lib.rs#L297-L359)、[stop](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/app-server-daemon/src/lib.rs#L408-L448)。主线仍保留拒绝条件，见 [restart](https://github.com/openai/codex/blob/87cf20ee491a035036f2d905926df4a0d35951cc/codex-rs/app-server-daemon/src/lib.rs#L372-L390)及 [stop](https://github.com/openai/codex/blob/87cf20ee491a035036f2d905926df4a0d35951cc/codex-rs/app-server-daemon/src/lib.rs#L489-L518)。

> 🔬 本次隔离验证：本机 `codex-cli 0.153.4`、临时 `CODEX_HOME`、仅实现 initialize 的模拟 Unix WebSocket 服务。模拟服务报告 0.149.0，未登记 PID backend；version / start 返回 0 且省略 backend，restart / stop 返回 1 和上述拒绝信息，最后 version 仍可连接。该测试验证管理边界，没有运行真实 0.149.0 后台、发起模型请求或操作既有服务。

### <a id="app-server-upgrades"></a>后台升级与关停

安装升级更新磁盘文件，实际会话使用的进程需要另行换版。对于确认受管、且允许中断其活动工作的实例，可以执行并逐步核验：

```bash
codex app-server daemon restart
codex app-server daemon version
```

检查两条命令各自的退出状态、stderr 和 JSON；重启报错时先解释错误，不能把后面一次探测成功当作重启成功。未受管的监听者应先找到原启动入口或管理者。需要按 PID 停止时，先确认授权范围、宿主 PID、UID、启动时间和可执行文件；不要用宽泛的全用户匹配替代实例识别。

关停信号还要区分管理器与 app-server 自身的处理：

| 核对对象 | 0.153.4 | 主线 `87cf20ee` |
|---|---|---|
| PID backend 的停止 | 向登记的 app-server PID 发 SIGTERM；60 秒后仍活动则 SIGKILL，停止等待总期限 70 秒 | 默认宽限仍为 60 秒，可配置 0–300 秒，之后有 10 秒强制退出检查窗口 |
| app-server 收到第一次终止信号 | 等运行中的 assistant turn 排空；此阶段仍接收请求 | 开始 drain，同时关闭新的 turn 准入，等待运行 turn 和已准入请求排空 |
| app-server 收到第二次可强制的终止信号 | 若还在该信号处理循环中，标记强制退出，跳过正常线程清理 | 保留该强制退出路径；它不同于管理器到期发送 SIGKILL |

> 源码：[稳定版停止时限和循环](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/app-server-daemon/src/backend/pid.rs#L22-L25)、[TERM / 强制停止分支](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/app-server-daemon/src/backend/pid.rs#L240-L283)、[SIGTERM / SIGKILL 实现](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/app-server-daemon/src/backend/pid.rs#L517-L544)、[稳定版信号状态机](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/app-server/src/lib.rs#L205-L283)、[主线宽限设置](https://github.com/openai/codex/blob/87cf20ee491a035036f2d905926df4a0d35951cc/codex-rs/app-server-daemon/src/settings.rs#L14-L15)、[主线停止循环](https://github.com/openai/codex/blob/87cf20ee491a035036f2d905926df4a0d35951cc/codex-rs/app-server-daemon/src/backend/pid.rs#L145-L225)、[主线 drain 准入](https://github.com/openai/codex/blob/87cf20ee491a035036f2d905926df4a0d35951cc/codex-rs/app-server/src/lib.rs#L246-L299)。稳定版 README 的“第二次 termination signal”不能覆盖代码实际使用 SIGKILL 的事实。

正常会话 shutdown 会尝试结束执行任务、code-mode 服务和 MCP 连接；管理器强杀 app-server PID 不等于递归、可靠地清理所有后代进程。强杀不会运行该进程的异步清理逻辑，应另行核对相关子进程和业务连接。长期存在的 code-mode-host 本身也不足以证明 agents 功能发生了进程泄漏。

> [稳定版会话清理](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/core/src/session/handlers.rs#L402-L432)、[强制退出与正常线程清理的区别](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/app-server/src/lib.rs#L1178-L1189)。主线还改进了对 zombie 的识别，见 [PID 活动状态检查](https://github.com/openai/codex/blob/87cf20ee491a035036f2d905926df4a0d35951cc/codex-rs/app-server-daemon/src/backend/pid.rs#L537-L559)；没有现场证据时，不能把该修正倒推为本次事故的原因。

自动更新也随版本和安装渠道变化：0.153.4 单独 start 不启动更新循环，bootstrap 才启动；主线 start / restart / bootstrap 会在自动更新开启、安装器记录 stable latest 渠道且二进制支持时维护更新循环，并另有 `daemon update`。两者都不能概括为“始终监视任意可执行文件变化”，`backend: "pid"` 本身不等于已启用自动更新。

> [稳定版更新行为](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/app-server-daemon/README.md#L47-L82)、[主线更新入口](https://github.com/openai/codex/blob/87cf20ee491a035036f2d905926df4a0d35951cc/codex-rs/app-server-daemon/README.md#L48-L74)及 [渠道与外部更新边界](https://github.com/openai/codex/blob/87cf20ee491a035036f2d905926df4a0d35951cc/codex-rs/app-server-daemon/README.md#L113-L144)。

独立 WebSocket app-server，例如聊天桥使用的专用服务，不会随默认 Unix socket 后台重启而自动换版。应分别核对版本、健康检查、桥接重连和后续业务；停止后台与删除配置、历史会话没有必然关系，不应把删数据当作升级步骤。

> 🔬 2026-09-09 现场同时存在普通 TUI 的共享服务和 Cyberboss 的独立 WS 服务。最终记录验证两个后台均为 0.153.4、桥重新建立连接并排入 check-in。这是当时的恢复证据，不是本轮对其现状的保证，也不能仅由 TCP 连接推导全部业务正常。

### <a id="app-server-maintenance-executor"></a>维护命令的执行环境

会话停止承载自己的后台，确实存在执行器随目标退出、后续恢复和核验失去执行渠道的风险。维护执行器需要同时满足：有目标宿主权限、能识别目标进程、生命周期独立于目标、命令完整传递、会话断开后仍可核对结果。这可以是授权的 SSH 执行器或经验证的服务管理任务，并不要求一定由人手敲命令。

先区分宿主与工具沙箱的视图。若进程列表只显示 PID 1 的 `codex-linux-sandbox`，或控制 socket 返回 EPERM，不能据此断言宿主没有 Codex 进程。需要通过获准的宿主执行途径核对，不得自行绕过权限拒绝。`nohup` 也不能单独证明进程已脱离原任务的进程组、沙箱或清理范围。

> [稳定版 Linux bubblewrap 参数](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/linux-sandbox/src/bwrap.rs#L327-L343)包含 `--die-with-parent`、PID namespace 隔离及条件性的 `/proc` 挂载。历史会话确有受限探测和随后获准的宿主探测，但后述 systemd 任务失败已有脚本传递证据，不能再归因于沙箱看不到进程。

通过 `systemd-run … /bin/bash -c '…'` 调度内联脚本时，调用 shell、systemd 和最终 Bash 分别处理命令；外层单引号不会关闭 systemd 的环境替换。systemd 会展开参数内的 `${FOO}`，未知变量变为空字符串，`$$` 变成一个字面 `$`。Bash 的 `${path##*/}`、`${!array[@]}` 等表达式可能在 Bash 运行前就被破坏。

> [systemd v239 的环境变量替换规则](https://github.com/systemd/systemd/blob/v239/man/systemd.service.xml#L1008-L1067)。裸 `$FOO` 作为独立参数还会进行分词，与嵌在整个 `bash -c` 参数里的形式不同；不能只靠换一层 shell 引号猜测最终 argv。

脚本包含这些表达式时，可以将经审阅的脚本保存为独立文件，让 systemd 只传路径，而不把脚本文本写进 ExecStart 参数：

```bash
systemd-run --user --on-active=30s --unit=codex-refresh \
  /bin/bash /absolute/path/restart-codex.sh
```

该文件需事先准备、语法检查并确认操作范围；上面的调度命令本身不包含关停逻辑。较新 systemd 的关闭环境展开选项要先检查目标版本是否支持，不能无条件用于没有该选项的 239。若仍用内联形式，要核验每层转义及最终脚本语义。通用服务管理与执行环境知识归 `software` skill。

### <a id="app-server-incident-verification"></a>升级事故的证据与验收

2026-09-09 的问题包含后台版本、进程归属、脚本传递和结果报告几个独立错误。将原始对话的承诺与工具输出、历史 journal 对齐后，可作如下判断：

| 现场证据 | 可得结论 | 不能据此声称 |
|---|---|---|
| CLI / managed binary 为 0.153.4，socket 后台为 0.149.0，version JSON 没有 backend | 新客户端连接旧服务，管理器未识别 PID backend | 仅重开终端会换版，或该实例一定能由 daemon restart 停止 |
| 第一次 nohup 延迟 restart 将所有 stdout / stderr 丢到 `/dev/null`，只见发起 shell 返回 0 | 提交过尝试，结果没有保留 | restart 已成功，或已取证到确定的失败原因 |
| 后续定时 refresh 的 journal 返回 alreadyRunning，随后 version 仍为 0.149.0 | 定时任务执行了，但未完成换版 | 定时器没有触发，或任务执行等于升级成功 |
| 全量终止任务的 TERM 目标、KILL 残留列表均为空，却打印“全部终止” | 脚本走过流程，但没有选中目标 | 已杀掉全部 Codex |
| journal 的 `_CMDLINE` 中 `process_pid="${proc_path#/proc/}"`、`process_name="${process_exe##*/}"` 均变成赋空值，数组表达式也消失 | systemd 在 Bash 之前展开了脚本，空进程名使匹配失败 | 此次失败只能由“杀自己”或 PID namespace 解释 |
| 用户外部操作后确认版本一致，后续检查出现 backend: pid | 最终切换为新版，管理器识别到 PID backend | 同样权限、正确传参的独立 agent 执行器不可能完成 |

> 🔬 依据为原始会话工具记录和两个定时任务的历史 journal。“全量终止”任务有被改写的实际 argv 直接证据；前一 refresh 脚本有同类表达式且未换版，但没有保留完整变换后的 shell argv。第一次 nohup 的错误输出已丢失：源码可解释未受管状态会拒绝 restart，不能把推断伪称为当时捕获的 stderr。终止脚本还潜藏双引号 awk 程序把 `$1` / `$2` 交给 Bash 展开的错误，但空目标使该分支未执行，不能将它写成本次已触发的原因。

现场还曾把下面的日志误当成“重启等待子进程退出超时”的直接证据：

```text
codex_models_manager::manager:
failed to refresh available models: timeout waiting for child process to exit
```

它的上下文是**模型目录刷新**。0.153.4 的 `/models` 请求把传输构造和 HTTP 请求包在 5 秒超时中，超时映射到通用 `CodexErr::Timeout`；该错误的显示文本恰好写着 child process。这条代码路径不需要发生子进程等待，更不是 daemon 停止日志。真正的 PID backend 停止超时文本是 `timed out waiting for pid-managed app server {pid} to stop`。

> 源码：[目录刷新 5 秒期限](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/model-provider/src/models_endpoint.rs#L39-L40)、[请求与错误映射](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/model-provider/src/models_endpoint.rs#L103-L116)、[模型管理器记录位置](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/models-manager/src/manager.rs#L339-L370)、[通用 Timeout 文本](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/protocol/src/error.rs#L108-L112)。这是所核源码中的传播路径；并未据此确定现场旧版那次请求的底层网络原因。

维护验收应依次保留：**任务已接收 → 实际执行参数正确 → 目标已退出 → 新实例就绪 → 原客户端路径和所需业务可用**。`systemd-run` 返回 timer 名称只确认调度；计时从调度起算，不是从助手回复送达起算。脚本退出 0 仍需核对目标和版本等后置条件。瞬态 unit 已被 `--collect` 回收时，当前 `LoadState=not-found` 下默认的 `Result=success` 不能替代历史 journal。

未核验后置条件时，只能报告“已安排”或“执行到某一步”。可复用的经验是识别实际后台及管理归属、正确传递独立维护任务、保留端到端证据；把整个事件缩写成“agents 造成进程泄漏”或“必须由用户手工 kill”，都会掩盖已经查明的问题。

## 上下文窗口与自动压缩

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
