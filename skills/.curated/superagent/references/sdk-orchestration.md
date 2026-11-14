# Codex SDK 编排

直接发起和管理外部 Codex worker 时，默认通过 SDK / `app-server` 编程驱动。本篇说明配套调度脚本、工作区准备、权限继承、多账号资源控制、容量退避与集成门禁；底层 SDK 方法、JSON-RPC 字段、配置键及版本差异以 `harness` skill 为准。

## <a id="dispatcher"></a>配套调度脚本的结构

在当前 skill 根目录下使用 `uv` 运行 [scripts/codex_dispatch.py](../scripts/codex_dispatch.py)。Python 版本与 `openai-codex` 依赖由脚本头部的 PEP 723 内联元数据声明；skill 目录保持只读，运行状态库、事件日志和执行回执一律写入外部指定路径。

| 模块路径 | 核心职责 |
|---|---|
| [scripts/codex_dispatch.py](../scripts/codex_dispatch.py) | 唯一顶层 CLI 入口，提供单目标执行（`run`）、额度查询（`limits`）、持久分片控制（`fleet`）与离线自测 |
| [scripts/codex_fleet/sdk.py](../scripts/codex_fleet/sdk.py) · [events.py](../scripts/codex_fleet/events.py) | 环境变量与权限继承、版本及运行态配置核验、主流与旁路通知并发消费、子线程收束补查、轮间延迟引导 |
| [scripts/codex_fleet/guard.py](../scripts/codex_fleet/guard.py) · [state.py](../scripts/codex_fleet/state.py) · [policy.py](../scripts/codex_fleet/policy.py) | 进程组守卫、SQLite WAL 原子租约与 runtime fence、容量退避阶梯及策略文件原子热更新 |
| [scripts/codex_fleet/worker.py](../scripts/codex_fleet/worker.py) · [plugins/](../scripts/codex_fleet/plugins/__init__.py) | 单分片持久循环、跨账号切换与崩溃恢复、源码直编插件加载及[顺序任务门禁插件](../scripts/codex_fleet/plugins/manual.py) |
| [scripts/templates/fleet.example.json](../scripts/templates/fleet.example.json) · [tests/test_codex_fleet.py](../scripts/tests/test_codex_fleet.py) | 通用分片配置模板与无需真实凭据或网络的协议级离线测试套件 |

## <a id="single-goal"></a>单目标执行与线程续跑

日常派发单个闭环任务时直接调用 `run` 子命令，无需初始化 fleet 目录。将用户的原始请求通过 `--prompt` 或互斥的 `--prompt-file`（UTF-8 编码）传入，目标 `--cwd` 目录须预先存在：

```bash
uv run scripts/codex_dispatch.py run \
  --cwd '<workspace-root>/task-a' --prompt-file '<task-dir>/request.txt' \
  --receipt-json '<task-dir>/receipt.json' --events-jsonl '<task-dir>/events.jsonl'

uv run scripts/codex_dispatch.py run \
  --cwd '<workspace-root>/task-a' --resume-thread '<thread-id>' --prompt '继续原目标并核对验证结果'
```

默认采用模型 `gpt-6.1-sol`、推理档位 `xhigh`、子代理并发数 `2`（不含主线程，传 `0` 则仅用主线程），单次 RPC 默认超时为 120 秒（模型回合本身的运行耗时不受此 RPC 超时截断）。可按需传入 `--model`、`--effort`、`--subagents`、`--codex-bin`、`--codex-home`、`--developer-instructions` 与 `--rpc-timeout`。省略 `--codex-home` 时沿用当前环境的 `CODEX_HOME`；子进程环境变量按“父进程环境 → 账号配置 → worker 配置”依次合并（配置值为 `null` 时剔除对应变量），账号切换只改 `CODEX_HOME` 而不改动系统 `HOME`，确保 Git、SSH、缓存与回收站路径保持正常。

未显式传入 `--sandbox` 或 `--approval-policy` 时，线程创建、恢复与单轮请求均省略相应字段，自然继承账号或项目的 `config.toml`。显式指定时，`--sandbox` 支持 `read-only`、`workspace-write`、`danger-full-access`，`--approval-policy` 支持 `never` 与 `auto-review`（分别映射 SDK 的 `deny_all` 与 `auto_review`）。

> SDK 的 `auto_review` 同时下发 `approvalPolicy=on-request` 与 `approvalsReviewer=auto_review`，行为不同于等待人工交互确认的原始 `on-request`；高权限沙箱与免审模式仅在用户明确授权的目录与任务范围内启用。启动时除校验 CLI 版本不低于 `0.167.0` 外，还会调用 `config/read` 核实 `multi_agent_v2`、并发槽位与固定角色提示确已生效。

命令在标准输出打印结构化 JSON 摘要（含 `thread_id`、`turn_id`、`status`、`final_message`、`elapsed_s`、前后额度快照与 `reconciled_children`），传入 `--receipt-json` 时同步原子落盘。运行期间脚本并发消费主流与旁路通知，主轮完成后等待全部已知子线程收束，对漏收实时结束事件的子线程通过只读 `thread/read` 补查状态；额度接口偶发异常时仅记录到额度字段，不中断主任务。回合正常完成退出 `0`，执行失败退出 `1`，参数或控制面校验错误退出 `2`。

> 返回 `completed` 仅代表本次模型回合及已知子线程收束，最终目标是否达成仍须结合产物与门禁核实。`--events-jsonl` 以追加方式记录事件流（可能包含提示词与工具输出，请保存在受控路径）。`run` 本身是单次同步命令，前台需要异步派发并保持对话响应时，应结合宿主可用的后台运行与完成通知机制调用。

## <a id="limits-command"></a>账号额度查询

`limits` 子命令仅握手建立协议连接并读取 `account/rateLimits/read`，不发起任何模型推理。不带参数时查询当前默认环境；传入多个 `--account` 可一次对比多账号剩余窗口：

```bash
uv run scripts/codex_dispatch.py limits
uv run scripts/codex_dispatch.py limits \
  --account 'primary=<codex-home-primary>' --account 'secondary=<codex-home-secondary>'
```

输出为 `accounts` 字典，保留各账号的完整额度快照；单个账号查询失败时将错误写入该账号条目而不影响其余账号，任一账号失败时进程退出码为 `1`。支持 `--codex-bin` 与 `--rpc-timeout`。

## <a id="fleet-command"></a>持久分片控制面

多工作树并行或长周期无人值守任务使用 `fleet` 子命令组，通过 `--fleet-dir` 指定位于 skill 安装目录之外的状态目录。先执行 `init` 生成默认策略与空配置，再对照[配置模板](../scripts/templates/fleet.example.json)替换真实工作区白名单、账号目录与分片任务后启动：

```bash
uv run scripts/codex_dispatch.py fleet --fleet-dir '<fleet-dir>' init
uv run scripts/codex_dispatch.py fleet --fleet-dir '<fleet-dir>' start task-a
uv run scripts/codex_dispatch.py fleet --fleet-dir '<fleet-dir>' status
uv run scripts/codex_dispatch.py fleet --fleet-dir '<fleet-dir>' set-policy max_parallel_workers 2
uv run scripts/codex_dispatch.py fleet --fleet-dir '<fleet-dir>' set-policy max_subagents_per_worker 0
uv run scripts/codex_dispatch.py fleet --fleet-dir '<fleet-dir>' pause task-a
uv run scripts/codex_dispatch.py fleet --fleet-dir '<fleet-dir>' resume task-a
uv run scripts/codex_dispatch.py fleet --fleet-dir '<fleet-dir>' drain task-a
```

`start` 以独立会话在后台拉起分片进程并将日志写入 `<fleet-dir>/logs/`，返回新进程 PID 后可通过只读的 `status` 随时查看运行态；需要前台直跑或交给外部服务管理器托管时改用 `run-worker task-a`（可加 `--max-turns N` 限制轮数）。`pause` 让分片在当前回合与外部门禁收束后挂起等待，`drain`（以及 `SIGTERM` / `SIGINT` 信号）让分片在同一安全边界干净退出；`resume` 用于解除挂起标志，已退出的分片需重新 `start`。

状态目录内维护 `fleet.json`、`policy.json`、`state.db` 以及分片锁、工作区锁、并发槽位锁和 runtime fence。文件锁仅协调同一 `--fleet-dir` 下的进程，跨控制目录或接手旧调度器工作区前须先确认原进程已退出。完整租约与进程世代保护面向单机 Linux 本地文件系统设计；非 Linux 环境下子进程守卫会降级运行，投产前应在目标平台实测。

任务驱动插件实现 `prepare(context) -> str | None` 与 `complete(context, result) -> bool` 两个入口：每轮边界直接从 `.py` 源码重新编译加载，规避同秒同字节修改命中陈旧 `.pyc` 缓存；同步插件函数自动放入线程池执行，避免慢速门禁阻塞事件循环与租约心跳。默认插件按 `turn_index` 顺序派发 `tasks` 列表，支持可选的 `gate_command`（字符串参数数组，禁止 shell 拼接）与 `gate_timeout`（默认 600 秒）；门禁失败或超时时保留当前任务索引与待核标记，停下等待排查。

> 插件模块与门禁命令均在宿主权限下直接执行，仅可加载受信任代码。热重载只针对入口插件源文件本身；若修改了底层辅助模块或切换了分片 `cwd`，应先 `drain` 原进程再重新启动。主动脱离会话组（`setsid`）的后台常驻服务不受进程组收割覆盖，需由插件自身负责生命周期管理。

## <a id="legacy-import-and-tests"></a>检查点导入与离线验证

迁移旧版调度状态时，可用 `import-v1` 只读导入既有检查点（保留账号、thread ID、任务进度索引、完成状态与扩展字段）；缺少账号归属、目标分片已存在检查点或文件锁正被占用时，导入会直接拒绝以防回滚覆盖：

```bash
uv run scripts/codex_dispatch.py fleet --fleet-dir '<fleet-dir>' \
  import-v1 '<legacy-state.json>' --worker task-a

PYTHONDONTWRITEBYTECODE=1 uv run scripts/codex_dispatch.py --self-test
```

导入前须确认旧控制进程已完全停止且 `tasks` 列表与原 `turn_index` 对齐。`--self-test` 基于临时目录与本地协议 mock 运行全部离线测试，不读取真实账号凭据、不发起网络请求，覆盖权限继承、环境变量增删、旁路事件流、租约抢占、崩溃恢复与门禁收割。

## <a id="worker-setup"></a>工作区环境与控制归属

参照[目标委派与工作区划分](collaboration.md#goals-and-workspaces)为分片准备持久工作树、写入边界与集成负责人，向每个外部线程交付完整的闭环目标：同一工作树内的无冲突子问题交由 Codex 主线程配合原生 `multi_agent_v2` 自行并发；多条分支或需要磁盘写隔离的目标再由外层分配独立工作树和持久线程。

跨轮推进的任务固定使用非临时（持久化）线程，记录目标、账号、工作树与 `thread_id` 的对应关系；同一线程在同一时刻只由一个控制器推进。控制器重启或断连后，先核对持久化的线程、回合与门禁状态，再决定恢复原线程还是重新派发，并将完成事件接回[任务归属与结果回传](collaboration.md#ownership-and-notices)。

为 worker 注入干净的工具环境：仅对模型服务或代码托管域名按需配置出站代理，让本地服务与构建产物缓存保持直连，并在启动后核实子进程实际继承的环境变量。

> 不同语言运行时对代理环境变量的大小写读取规则不一（如 Python `urllib` / `requests` 识别小写 `no_proxy`，而 `curl` 等原生工具读取大写 `NO_PROXY`）。配置直连白名单时应成对写入一致的 `no_proxy` 与 `NO_PROXY`（例如 `localhost,127.0.0.1,::1,<cache-domain>`），并用实际下载命令验证旁路生效；代理排障详见 `network` skill。

## <a id="permission-defaults"></a>权限缺省值与有效配置

分片实际获得的沙箱与审批权限由账号/项目 `config.toml`、线程启动参数与单轮调用参数逐级叠加决定。希望沿用底层 `config.toml` 时，未配置项须保持省略（`None`）；若由调度器统一指定，则在创建线程、恢复线程和发起单轮时使用同一套映射逻辑，核对 JSON-RPC 字符串与 Python SDK 枚举的一致性。

> 2026-11-13 调度器排障记录：多个账号的全局 `config.toml` 虽已设为 `danger-full-access`，但早期分片调度器用 `spec.get("sandbox", "workspace-write")` 为缺省分片填入了默认值，并在创建、恢复与单轮调用中显式下发，导致全局配置被静默覆盖降权（基于调度器与 Python SDK `0.167.1` 源码静态核查）。完整优先级表与枚举映射由 `harness` skill 维护。

修改调度器缺省策略或账号配置后，在新建或恢复后的轮次中实测核对实际生效的模型、推理档位、`cwd`、沙箱与审批模式。安全边界依靠内核沙箱与外部系统授权落实；工作树划分与提示词约束仅用于任务组织，不能替代权限隔离。

## <a id="accounts-and-resources"></a>账号租约、进程围栏与水位切换

多账号并行时按账号维护独立的租约池与容量控制器，使单个账号的限流或服务波动只收缩该账号自身的并发槽位；同时统筹宿主机的 CPU、内存、swap 与本地构建线程预算，避免多路编译叠加拖垮整机。

控制面状态库使用 SQLite WAL 模式配合 `BEGIN IMMEDIATE` 事务原子发放随机 token 租约，依靠独立守护线程维持心跳，并通过 Linux `boot_id + /proc/<pid>/stat starttime` 唯一标识进程世代。租约 TTL 过期仅使数据库记录失效，槽位真正复用前还必须通过内核文件锁与双层 runtime fence 校验：子进程守卫只有在彻底收割完整个 `app-server` 进程组后才会释放槽位与工作区的 runtime fence，从而保证即便原 worker 遭遇 `SIGKILL`，残留的工具子进程也不会与新调度的实例撞车。

策略文件 `policy.json` 采用“同目录临时文件写入 → 文件 `fsync` → `os.replace` 原子替换 → 父目录 `fsync`”更新，写入端加排他锁并做全量 schema 校验。若人工写入了非法配置，读取端自动保留上一份有效快照并记录错误，在跑回合平稳收尾后于下一轮边界暂停等待修复。默认 `account_order` 为 `["default"]` 且不自动换号；配置水位切换规则后，系统在轮次边界读取 `account/rateLimits/read`，达到阈值或捕获配额耗尽错误时单向切往顺序表中的后继账号。

> 配套 `fleet` 在跨账号切换前会先持久化新账号并清空旧 `thread_id`，随后在新账号上开启新线程，避免崩溃重启后误用新账号去恢复旧账号的私有会话。若多个 `CODEX_HOME` 软链共享同一 `sessions/` 与 `thread-writer-locks/` 目录，待原 `app-server` 退出释放写锁后，也可通过 `run --resume-thread` 在备用账号上无损续跑长上下文（2026-11-12/13 在 Linux、Python SDK `0.167.1`、CLI `0.167.0`/`0.167.1` 下实测跨账号恢复耗时约 40–65 秒，RPC 超时宜设为 120 秒；写锁与后台身份核查顺序见 `harness` skill）。

## <a id="capacity-backpressure"></a>重连聚合与容量阶梯退避

通过在底层连接分发前旁路监听通知，将带 `willRetry=true` 或 `Reconnecting... k/n` 的 `error` 事件关联到具体的 `(thread_id, turn_id)`。同一回合内连续发生的多次重连在状态库中按 `(thread_id, turn_id)` 主键幂等聚合成一次过载信号，仅下调一级并发容量；已拿到租约的在跑回合继续执行至安全边界，后续新租约按收缩后的上限发放，待连续稳定满 `recovery_seconds` 后再逐级回升。

配套控制器将“外部并行 worker 数”与“单 worker 内部子代理数”捆绑为容量阶梯：level `0` 严格执行策略文件设定的上限（默认 `(3, 2)`），过载后依次按 `(3, 1) → (2, 1) → (2, 0) → (1, 0)` 与策略上限取较小值收缩。流式重试触发的降档受 `max_level_on_stream_retry` 封顶，持续重试期间不断刷新最近过载时间戳以防提前回升；模型服务端容量波动与本机编译负载分别观测。

> `willRetry=true` 表明底层 runtime 正在自动退避重试；Python SDK 主轮的 `TurnHandle.stream()` 不覆盖子代理轮次的通知，因此需在路由器分发前做非消费旁路监听（底层路由机制见 `harness` skill）。容量升降由后台控制面自动消化，仅在持续受阻影响交付预期时再汇总告知前台。

## <a id="turn-boundaries-and-cache"></a>轮间引导与缓存前缀稳定

当上轮发生服务重连、需要提醒模型收缩新增子任务时，将调度提示按类别合并暂存，等到下一轮 `turn/start` 时追加在用户输入末尾；不在流式重连中途调用 `steer()` 强行插话，以免打断底层退避循环或因远端回合状态切换引发竞态报错。

需要在轮间动态调整内部子代理并发上限时，待当前主轮与全部子线程收束后关闭旧 `app-server`，用新配置拉起实例并在同一账号下 `thread_resume` 原线程，再通过 `config/read` 核实新上限已生效。同时保持 `developer_instructions` 以及 `root_agent_usage_hint_text`、`subagent_usage_hint_text` 两条角色说明固定不变，把随轮次变化的动态提示一律放在用户输入尾部，从而保住高命中率的提示词缓存前缀。

> 所核版本的 Codex runtime 使用 `OnceLock` 在单实例内首次初始化会话执行容量，且未显式覆盖角色说明时会把当前槽位数拼进 developer 消息（2026-11-12/13 在 Linux、Python SDK `0.167.1`、CLI `0.167.0`/`0.167.1` 下经 localhost 抓包实测：默认槽位 `2 → 3` 会改写 developer 前缀，固定两条角色说明后跨槽位前缀字节保持一致，同账号恢复长历史线程的缓存命中率保持在 99.5% 以上；底层源码定位见 `harness` skill）。

## <a id="shard-and-integration-gates"></a>分片门禁与集成门禁

多工作树并行开发时将验证拆成两层：各分片独占目标子集与分支，在轮内仅运行足以验证局部改动的快速增量门禁，并限制单分片本地构建线程数；耗时的全量编译与整包回归收口到集成工作区统一执行，公共生成文件指定唯一写入方。

> 2026-11-12/13 同期负载记录：两个独立账号分别采用独立状态库运行 `4 workers × 2 subagents` 并将重型全量门禁从分片轮内剥离后，8 个工作树并行推进期间过载计数保持为 `0`；具体并发度与加速收益需按目标仓库编译特征实测调整。

集成阶段按模块依赖顺序合入已达标的分片成果，再跑通总入口与全量门禁。若恢复早先的分片主线程来承担最终合入收尾，须先把确定性的合入提交落盘，并在新一轮提示词中明确赋予集成写面、解除早先轮次的“禁改其他分片文件”限制。每次门禁回执均绑定实际 `HEAD` 提交，未通过项退回对应负责人修复。

配套 worker 在发起每轮模型调用前先落盘 `uncertain=true` 检查点，唯有模型回合完成、子线程全部收束、`app-server` 干净退出且外部 `gate_command` 返回成功后，才递增 `turn_index` 并清除 `uncertain`。若中途崩溃重启，恢复逻辑会将带 `uncertain` 标记的检查点交给任务插件，提示执行者先检查工作树实况与已产生的外部副作用，再安全续接当前任务。

> 同步门禁命令与进程启动均可能运行在后台工作线程中：收到取消或启动超时信号时，控制面会先等待正在进行的门禁子进程或进程创建动作收束，再清理 runtime 树与管道并释放工作区锁和租约，防止迟到派生的子进程逃逸成孤儿进程。
