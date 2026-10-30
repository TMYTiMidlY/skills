# Codex 会话监控与远程推进

无人值守的 Codex 会话（TUI 挂着、daemon 托管或 `exec` 拉起的长任务）从外部可以**观察** rollout 与后台状态，也可以在获准后通过 queue、resume 或应用服务 API **干预**。本篇整理 rollout 判读、queue 语义、resume 边界、[多账号恢复与 goal 生命周期](#account-resume)、限流退避和监控守则。原有 queue／exec 部分按 `rust-v0.162.1`，🔬 为 2026-10-12 同版本隔离环境实测，🧭 为未复现的现场观察；多账号恢复专题另按 `rust-v0.165.0` 核对源码，不能用旧版或单一入口的行为概括所有客户端。app-server 与 daemon 的进程模型见 [Codex 运行时笔记](codex.md#app-server-lifecycle)。

## <a id="rollout-signals"></a>rollout 存档的判读

会话存档是 `$CODEX_HOME/sessions/YYYY/MM/DD/rollout-<时间戳>-<会话UUID>.jsonl`，每行一个 JSON 事件。初步判断回合进展看文件 **mtime**（最后写入时间）和**尾部事件类型**；判断能否停止或跨账号接管，还要核对后台、工具、队列与 goal。客户端 UI 的显示、进程是否存在都不能替代磁盘记录，存档静默也不能独自证明会话已经空闲或释放写锁。

### <a id="rollout-tail-events"></a>尾部事件的类型与含义

| 尾部事件 | 结构 | 判读 |
|---|---|---|
| `event_msg` · `task_complete` | v1 序列化名，即协议的 `TurnComplete` | 一个回合正常结束；`last_agent_message` 带最终回复全文 |
| `event_msg` · `turn_aborted` | `reason`: `interrupted` / `replaced` / `review_ended` / `budget_limited` 之一 | 回合被中断；比正常结束多一层原因 |
| `event_msg` · `token_count` | `info` 用量 + `rate_limits` | 用量与额度遥测，见 [限流的判读](#rate-limit) |
| `response_item` · `reasoning` / `custom_tool_call` / `message` | 模型推理、工具调用、消息记录 | 停在这类半截事件上 = 回合没有收尾（进程被杀、假死） |
| `token_usage_record` | 每 response 的 token 明细 | 计费级明细，无状态语义 |

> 事件名与含义按 [协议定义](https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/protocol/src/protocol.rs#L1420-L1440)（`task_started`/`task_complete` 是 v1 序列化名、`turn_started`/`turn_complete` 为 v2 别名）与 [TurnAbortReason 枚举](https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/protocol/src/protocol.rs#L4274-L4282)。🔬 实测杀掉进行中的 `exec` 进程：rollout 尾部停在 `reasoning` → `custom_tool_call` → `token_usage_record`，**没有** `task_complete` 也没有 `turn_aborted`——进程非正常死亡来不及写收尾事件，半截事件流本身就是"卡住"的信号。

判读之外的操作坑：

- **别用消息回执 ID 验证 queue 投递**。`codex queue` 返回的是排队记录 ID（存 SQLite），投递进会话后 rollout 里记的是派生的 `msg_…` 用户消息 ID。🔬 实测：回执 ID 在 rollout 中出现 0 次，消息**文本**出现 2 次。核对投递要 grep 消息文本。
- **管道方向别接反**。`tail -n 40 | head -12` 取的是最后 40 行的**前** 12 行，最新事件（在尾部）恰好被截掉，会误判"文件没写入"。取最新事件只用 `tail`。
- **mtime 静默 ≠ 死了**。长工具调用（构建、证明器、长 sleep）执行期间 rollout 不写新事件。🔬 实测 `sleep 90` 期间 rollout 完全静默。判"停下"前先查该会话拉起的长时进程还在不在跑。

### <a id="rollout-encrypted"></a>多代理消息的密文形态

多代理（multi-agent）会话里子代理间 `agent_message` 正文是端到端加密的：rollout 里 `content` 数组只有消息头明文（`Message Type: NEW_TASK` / 任务名 / 发送者），正文是 `encrypted_content` 密文块。🔬 本机订阅会话的 rollout 实测如此；协议结构同时留有明文 `content` 与 `encrypted_content` 两个字段，是否加密取决于运行配置。

> 源码：[InterAgentCommunication 定义](https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/protocol/src/protocol.rs#L820-L877)。想知道子代理在想什么，最有效的办法是让它把状态写进普通文件（如会话目录下的 `*-status.md`），明文一读全明白。

## <a id="queue-semantics"></a>codex queue 的排队语义

```bash
codex queue --thread <会话UUID或精确会话名> --message '继续'
# 输出：Queued message <回执UUID> for thread <会话UUID>.
```

这是官方的"按会话 ID 发消息"入口：消息进服务端队列，**入队本身不启动回合、永不打断进行中的回合**。三类场景的行为（🔬 实测 + 源码一致）：

| 场景 | 行为 |
|---|---|
| 线程空闲且无客户端持有 | 接受并持久挂起（落 SQLite），rollout 纹丝不动；直到有线程被 resume 才投递 |
| 回合进行中 | 排队等待，不打断当前回合；回合一结束自动投递、开启新回合 |
| 回合卡死 / 客户端死掉 | 消息滞留队列（不会凭空投递）；下次 resume 时冲入 |

🔬 实测细节：给空闲无客户端的线程 queue 后 8 秒 rollout mtime 不变；给进行中回合 queue 后 rollout 不因入队前进；杀掉持有回合的进程后 20 秒消息仍未投递；随后 `exec resume` 一并冲入，队列消息与 resume 提示词同轮处理。

> 踩坑：消息没有立即投递 ≠ queue 不能用。queue 的设计就是"挂着等"，把它当"发出去没回音就换野路子"会错过正确的用法。

### <a id="queue-mechanism"></a>投递机制

入队持久化在 `$CODEX_HOME` 的 SQLite 队列库（🔬 实测生成 `queue_1.sqlite`），每线程上限 100 条。投递只发生在**持有该线程 live writer 的服务进程**里，全部走 `start_turn_if_idle`（只在空闲时起回合，触发标记 `queue`）：

- 入队后若线程已在该进程加载且空闲 → 立即投递；正忙则等回合结束的 idle 生命周期回调投递。
- resume、新线程加载、其他服务实例写库，都由一个 **10 秒轮询** SQLite 变更版本的 watcher 兜底发现并派发。

> 源码：[CLI 入口](https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/cli/src/queue_cmd.rs#L29-L62)、[add 只入队不起回合](https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/app-server/src/request_processors/thread_queue_processor.rs#L77-L95)、[start 要求线程已加载且空闲](https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/app-server/src/request_processors/thread_queue_processor.rs#L186-L228)、[enqueue 与 wake_if_loaded](https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/ext/queue/src/service.rs#L265-L280)、[idle 回合结束派发](https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/ext/queue/src/service.rs#L549-L566)、[10 秒 watcher](https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/ext/queue/src/service.rs#L89-L99)、[上限 100](https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/state/src/lib.rs#L109)。

queue 必须经过共享 app-server：本地 daemon 在运行时不允许走内嵌服务（报 `cannot queue through an embedded app server while a local app-server daemon is running`），`--no-daemon` 也被拒绝——这是为了避免消息写进另一个服务实例的内存态。另注意 queue 不支持图片附件；ephemeral 线程不接受排队。

## <a id="exec-resume"></a>codex exec resume 的无头恢复

```bash
codex exec resume <会话UUID> '继续'
```

无头恢复线程并把挂起的 queue 消息一起冲入（🔬 实测：resume 提示词与滞留队列消息在同一轮处理，模型可一并响应）。它走 `thread/resume` 应用服务 API，与 TUI 的 resume 同一条生命周期。

### <a id="resume-conflict"></a>thread-store conflict

每个线程有跨进程文件写锁 `$CODEX_HOME/thread-writer-locks/<会话UUID>.lock`。另一个进程持有该线程的 live writer（例如 daemon 正在跑这个线程的回合）时，`exec resume` 抢不到锁直接失败（🔬 实测原文，退出码 1）：

```text
Error: thread/resume: thread/resume failed: thread <UUID> already has an active writer (code -32600)
```

此时先定位持有线程的服务。已获准让原后台继续执行时，可以向它 queue 消息或通过 TUI 附加；**要换账号或只查看、保持暂停时，这两种做法不能代替交接**，排队消息还可能开启新回合。持有进程死亡后文件锁随进程释放（🔬 实测：杀掉进行中回合的进程后 resume 成功），但这不是常规恢复步骤：同一后台可能承载其他任务，强制终止也不保证工具清理完成。空闲后台仍持有写者的情况，见[多账号恢复与 goal 生命周期](#account-resume)。

> 源码：[写锁的 WouldBlock 判定与报错文案](https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/rollout/src/writer_lock.rs#L42-L79)、[锁冲突映射为 thread-store conflict](https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/thread-store/src/local/mod.rs#L341-L360)。

### <a id="resume-exit-codes"></a>git 检查与退出码

`exec` 默认要求在 git 仓库内运行（沿目录向上找仓库根）；非 git 目录要加 `--skip-git-repo-check`。缺 flag 时（🔬 实测原文，退出码 1）：

```text
Not inside a trusted directory and --skip-git-repo-check was not specified.
```

退出码语义：`1` 是常规错误（上述两种都是），`2` 是用法错误（🔬 实测：给 `exec resume` 传 `-s read-only` 即报 Usage 错误退出 2），`101` 是 Rust 惯例的 **panic** 退出码。panic 不回滚已完成的磁盘写入——文件改动、git 提交是否落盘以仓库实际状态为准，别被 101 吓到；rollout 里表现为回合没有收尾事件，进度按尾部事件判断。

## <a id="account-resume"></a>多账号恢复与 goal 生命周期

本节按 Codex `0.165.0` 源码核对，适用于账号分别使用独立 `CODEX_HOME` 和后台、但共享会话及写锁的部署。要分别核对**后台是否持有会话、是否有执行中的回合、goal 是否允许自主继续、模型请求使用什么身份**；任一项不能替代其他项。

### <a id="account-writer"></a>会话写锁与后台占用

一条会话在同一时间只允许一个后台持有 live writer。按 Interrupt 结束当前回合，并不要求后台卸载该会话；退出 TUI 也只断开这个客户端，后台和其他订阅者可以继续存在。因此“已经不输出了”与“另一个账号能够接手”是不同状态。原生 TUI 在中断正在执行的 Active goal 回合时还有额外的暂停动作，单独调用 `turn/interrupt` 则只提交中断；两种入口都应读回最终 goal 和回合状态，不能用按键成功代替验证。锁文件存在本身也不能证明锁仍被持有，删除锁文件更不能作为释放活跃写者的办法。

`0.165.0` 的默认空闲卸载延迟是 1800 秒，且还需满足没有订阅、没有运行任务等条件，不是按 Interrupt 后固定等待一段时间就一定解锁。临时建立另一个连接调用 `thread/unsubscribe`，只能解除该连接的订阅，不能让其他窗口退出。恢复前应核对实际后台和客户端，而不是按窗口名、PID 记录文件或 rollout 静默时间猜测。

> 源码：[interrupt 请求](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/app-server/src/request_processors/turn_processor.rs#L1622-L1665)、[TUI 额外暂停 goal](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/tui/src/chatwidget/interaction.rs#L713-L731)、[默认延迟](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/core/src/config/mod.rs#L4100-L4101)、[空闲候选计时](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/app-server/src/request_processors/thread_lifecycle.rs#L58-L83)、[连接级 unsubscribe](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/app-server/src/request_processors/thread_processor.rs#L1079-L1104)。原生后台的连接和进程管理归属见[进程的管理归属](codex.md#app-server-ownership)。

公开应用服务 API 没有可直接调用的 `thread/unload` 或 `thread/close`；`thread/closed` 是通知。`thread/archive` 会关闭线程并执行归档，`thread/unarchive` 再恢复归档状态。这是有磁盘与索引副作用的生命周期操作，不是无副作用的“解锁按钮”，也不是一次不可分割的账号交接。

> 源码：[请求方法](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/app-server-protocol/src/protocol/common.rs#L583-L597)、[关闭通知](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/app-server-protocol/src/protocol/common.rs#L1983)、[归档前关闭](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/app-server/src/request_processors/thread_processor.rs#L1107-L1139)、[归档处理](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/app-server/src/request_processors/thread_processor.rs#L1757-L1848)、[取消归档](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/app-server/src/request_processors/thread_processor.rs#L2161-L2189)。

### <a id="resume-goal"></a>打开会话与启动 goal

**恢复聊天上下文不等于授权 goal 继续研究。** 服务端恢复 goal runtime 时只接续 Active 状态，但完整 TUI 流程还会询问是否恢复暂停的 goal。命令行直接 resume、TUI 历史选择和 agents 总览都有相关调用路径；只检查启动参数里有没有 UUID，覆盖不了界面里后选中的会话。

> 源码：[服务端恢复](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/ext/goal/src/runtime.rs#L412-L433)、[启动恢复](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/tui/src/app/startup.rs#L1138-L1148)、[历史选择](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/tui/src/app/session_lifecycle.rs#L1477-L1486)、[agents 总览](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/tui/src/app/agents_overview.rs#L903-L907)。

该版本的 `Resume paused goal?` 弹窗对 `paused`（暂停）、`blocked`（阻塞）和 `usageLimited`（用量受限）状态开放，默认选项是 **Resume goal**。确认它会发送把 goal 改成 Active 的请求。因此只读回“当前没有 Active goal”，不足以保证随后打开 TUI 不启动研究；也不能凭额度受限状态认定以后不会执行。批量模拟按键时，空闲输入、默认选项和旧画面尤其需要逐步核实。

> 源码：[提示条件与启动动作](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/tui/src/app/thread_goal_actions.rs#L54-L85)、[菜单默认选项](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/tui/src/chatwidget/goal_menu.rs#L39-L70)。这些代码证明存在启动路径，不能单凭它们断言某次历史事件究竟由哪个客户端或按键触发。

获准“只恢复会话、保持暂停”时，对可接受直接输入的既有 goal，使用仅修改状态的请求，保留目标、预算与累计记录；先读状态，已经完成的 goal 保持完成，不删除或重建：

```json
{"method":"thread/goal/set","params":{"threadId":"<thread-id>","status":"paused","origin":"user"}}
```

这是按用户明确指令暂停的 API 消息示意，`origin` 记录本次操作来源；执行前需完成原生协议初始化并配置请求 ID。若当前有执行中的回合，暂停 goal 之外还需单独处理该回合并验证工具确实停止。旧状态为 `budgetLimited`（goal 预算耗尽）时，请求改为 `paused` 或 `blocked` 会保留原状态，即使同次传入新预算也是如此；只改预算而省略状态也不会把它恢复为 Active。不应为了让界面字面显示 Paused 而清空预算、重建 goal 或重置累计用量。

> v2 API 的状态拼写为 `active`、`paused`、`blocked`、`usageLimited`、`budgetLimited`、`complete`，见[状态枚举](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/app-server-protocol/src/protocol/v2/thread.rs#L820-L828)与[序列化宏](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/app-server-protocol/src/protocol/v2/shared.rs#L24-L39)；SQLite 内部的 snake_case 拼写不能直接拿来构造请求。用户来源字段见[请求结构](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/app-server-protocol/src/protocol/v2/thread.rs#L867-L894)。状态更新与保留规则见[既有 goal 的状态更新](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/ext/goal/src/api.rs#L257-L279)、[预算限制状态的保留](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/state/src/runtime/goals.rs#L293-L364)。公开 goal 响应不包含内部 GoalID，见[响应结构](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/app-server-protocol/src/protocol/v2/thread.rs#L834-L848)；若验收要求核对内部 ID，需另有获准的只读证据，不能把目标文字相同当作 ID 未变。

### <a id="account-handoff-checks"></a>跨账号接管的检查顺序

对指定会话的接管，应在已授权范围内依次进行；其中任一步无法证实，就停在当前状态并报告，而不是试着 resume 看会不会开始运行。

1. **定位会话与后台**：确认共享存储、原会话 ID、实际 cwd／分支／未保存成果，以及旧后台和目标账号后台。保存可取得的会话树、goal 状态、目标、预算和累计记录，核对持久队列、活动回合与工具进程。
2. **核查完整子树**：根线程空闲不能替代子任务空闲。默认 `thread/list` 来源过滤会遗漏子代理，`loaded/list` 也不能证明列出了全部内部节点；持久子树与当前后台的 live 子树还可能不同。存在隐藏、临时、分散持有或无法解释的节点时，停止自动接管。
3. **落实暂停**：按用户指令处理可直接控制的 goal 和当前回合，读回确认没有新回合或后台工具仍在执行。已完成状态和预算限制保持原有约束。V2 ThreadSpawn 子任务可能不接受公开 `goal/set`，遇到这种情况不能绕过 API 写数据库。
4. **释放旧写者**：优先协调旧客户端退出并确认原生后台卸载。若考虑归档／取消归档，需要另行确认对目标 thread-spawn 子树的影响和授权；其范围合并持久 agent graph 与所调用后台的 live 子树，不等于任意 fork 历史或外部编排的完整任务树。遇到超时、断连或中途失败，先只读核对实际归档与写者状态，不能盲重试、伪称回滚成功。
5. **在目标后台恢复并验收**：通过已准备好的禁止意外启动机制恢复原会话，核对真正接手的后台身份、原 ID／树／goal／预算、模型／provider／强度／权限，以及没有意外开启回合。不能偷偷转连旧后台以消除占用报错，否则实际执行仍可能消耗旧账号额度。

> 源码：[线程来源与祖先过滤](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/app-server-protocol/src/protocol/v2/thread.rs#L1437-L1440)、[祖先条件](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/app-server-protocol/src/protocol/v2/thread.rs#L1487-L1491)、[内部线程的列表过滤](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/app-server/src/request_processors/thread_processor.rs#L2977-L2982)、[持久与 live 子树](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/core/src/thread_manager.rs#L1085-L1117)、[子任务直接输入限制](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/app-server/src/request_processors/thread_input.rs#L11-L33)、[goal 请求的门禁](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/app-server/src/request_processors/thread_goal_processor.rs#L326-L380)。

### <a id="resume-accounting"></a>执行身份与额度

额度归属看**实际发出上游模型请求的后台身份和 provider**，不是会话创建者、窗口标题或启动函数名。账号 B 的窗口连接着账号 A 的后台时，窗口名不会把 B 的凭据传给 A；真正转交给 B 的后台后，后续请求才采用 B 的执行身份。第三方 provider 还要分别核实其端点与认证，不能一律按订阅账号推断。

单纯读取历史不等于发出模型请求，但恢复会话可能触发已有 queue 或 Active goal；“打开界面”不能作为零模型用量保证。goal 的 token 累计量参与 token 预算，耗时用于 goal 进度记账；二者不直接等于订阅账单或账号剩余额度。报告时分别记录后台身份、是否实际开启回合、goal 累计量和账号额度遥测，避免混为一个数字。

> 源码：[后台建立 AuthManager](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/app-server/src/lib.rs#L596-L605)、[按 provider 与当前认证解析请求](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/core/src/client.rs#L1161-L1184)。后台与客户端的认证边界见[账号与存储边界](codex.md#cc-switch-storage)，订阅统计与第三方本地统计见[账号活动与额度](codex.md#usage-accounting)。模型容量不足、网络超时和账号额度耗尽应分别取证，不能只凭 `high demand` 或 `Reconnecting` 认定额度耗尽。

### <a id="manual-session-maintenance"></a>按需运行的外部维护脚本

需要人工处理某一次占用、而不更改 Codex 本体或启动入口时，可使用[按需维护脚本](../scripts/codex-session-maintenance.py)。控制接口已核对 `0.165.0`／`0.166.0`；脚本只连接指定账号**已经运行**的后台，不登录、不启动／重启后台、不发 `thread/resume`、`turn/start`、goal Active 或 TUI 按键。

先从原会话的 `/status` 取得 UUID，核对实际持有它的后台及 `CODEX_HOME`；`--home` 是本次连接的源账号目录，不会自动换成另一个账号。以下命令从本 skill 根目录运行，替换占位符：

```bash
uv run scripts/codex-session-maintenance.py inspect \
  --home '<account-home>' --thread '<thread-id>'

uv run scripts/codex-session-maintenance.py pause \
  --home '<account-home>' --thread '<thread-id>' \
  --apply --audit-dir '<private-audit-dir>'
```

默认和缺少 `--apply` 的调用只检查。`pause` 只修改既有 goal 的状态，保留目标、预算、累计记录与终态；当前回合可能仍在运行，**明确要中断这一轮时**，在 `pause --apply` 后加 `--interrupt`。脚本不会新建 goal、清空队列或中断其他后台。审计目录必须本人所有且为 `0700`；记录只含元数据和目标摘要，不保存历史正文、账号邮箱或凭据。内部 GoalID 能从已有 goal 库只读取得时会直接比较；不能取得时明确标为未核验，`release` 会停止，不用文字相同代替 ID 证据。

若原后台仍持有一个空闲的标准根会话，先人工检查并停止旧窗口、子任务和脱离终端的工具，再显式执行：

```bash
uv run scripts/codex-session-maintenance.py release \
  --home '<source-account-home>' --thread '<thread-id>' \
  --apply --reviewed-idle --audit-dir '<private-audit-dir>'
```

`--reviewed-idle` 是操作者对人工检查的确认，**不是程序证明了完整子树**。脚本仍拒绝已发现的活动回合、排队、子会话、分散写者、不明后台终端、custom 来源、fork 和已归档成员；复杂任务按[跨账号接管的检查顺序](#account-handoff-checks)逐项人工处理。原写者已经释放时只暂停 goal，不归档；确需释放时才通过归档／取消归档处理所选单根会话，不删除锁文件、不写原生数据库，也不自动接管或继续工作。

原生归档有副作用且可能部分成功。脚本在每次写入前留审计，超时或出错后停止，不盲重试、不假称回滚。若审计确认所选 UUID 留在归档中，可在再次核对空闲状态后，用同样的 `--apply --reviewed-idle --audit-dir` 参数执行 `restore`；它只取消该 UUID 的归档，不递归恢复孩子、不加载运行时。无法确认的情况保留现场再处理。

完成后**退出旧 TUI，再用目标账号入口重新打开原 UUID**；出现 `Resume paused goal?` 时明确选 **Leave paused**。不要把旧只读页的 **R / retry** 当作“只恢复显示”：2026-10-30 的一次现场中，TUI `0.165.0`、后台 `0.166.0`，外部已读回 Paused 后，仅发送一次 `r`（未发 Enter），随后仍观察到 Active 和一个新回合，之后再次暂停并中断。只确认这一现场顺序，尚未证明是缓存动作重放、默认确认或其他客户端触发。

> `0.166.0` 的[goal 请求](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/app-server-protocol/src/protocol/v2/thread.rs#L867-L916)、[队列读取](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/app-server-protocol/src/protocol/v2/thread.rs#L935-L980)、[后台终端读取](https://github.com/openai/codex/blob/rust-v0.166.0/codex-rs/app-server-protocol/src/protocol/v2/thread.rs#L1246-L1277)与所查 `0.165.0` 对应定义一致；这不表示所有运行语义均相同。只读页重附着及恢复后的提示见[恢复路径](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/tui/src/app/session_lifecycle.rs#L1477-L1486)，默认选项见[goal 菜单](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/tui/src/chatwidget/goal_menu.rs#L39-L70)。

### <a id="resume-guard"></a>恢复入口的保护范围

若用本地中转程序保护原生 TUI，应在它实际发送 `thread/resume` 时检查具体会话，而不是只匹配 `resume <UUID>` 的命令参数。中转还需在转发恢复前落实暂停，并独立约束随后把 goal 改成 Active 的请求；原生弹窗确认与手动 `/goal resume` 会使用同一种启动请求，并都可标记为用户来源，单看方法或 `origin:"user"` 无法证明用户是否另行明确授权。需要单独的、有会话与当前接管身份约束的启动授权；不能把省略状态的新 goal 请求当作无害写入直接放行。

这种保护只覆盖经过它的客户端。旧窗口、直接连接原生 socket 的程序，以及后台内部 goal 工具和自动恢复路径，仍须分别协调；同一用户下的普通中转不是安全隔离，不能承诺所有进程永不启动 goal。客户端间还需防止旧连接在接管后重新写入；一把只在操作期间持有的外部锁，不能独自禁止原生后台继续运行。

自定义 Unix 中转端点在原生 TUI 中按 Remote 路径处理，不等同于验证过的 LocalDaemon：需明确传递 cwd，并测试权限、配置与 executor；该路径会拒绝 `--add-dir`。传输是 Unix socket 上的 WebSocket，需要保留请求／响应、审批、通知和连接关闭语义。安装前说明这些交互差异，不能把它包装成已与原生完全等价的永久修复。

> 源码：[显式远端分支](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/tui/src/lib.rs#L1056-L1092)、[本地后台验证](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/tui/src/startup_orchestration.rs#L109-L134)、[远端 add-dir 限制](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/tui/src/startup_orchestration.rs#L21-L25)、[Unix WebSocket 客户端](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/app-server-client/src/remote.rs#L782-L838)。

## <a id="rate-limit"></a>限流的判读与退避

rollout 的 `token_count` 事件自带权威限流遥测：`rate_limits` 含 `used_percent`、`window_minutes`、`resets_at`、credits 余额与套餐类型（🔬 本机会话实测可见 `used_percent: 33.0`、`window_minutes: 10080`）。监控脚本直接从 rollout 尾部读这份数据，比盯 UI 弹窗可靠。

`high demand`、`Reconnecting`、`stream disconnected`、远端 compact 失败或很快结束的空回合，都需要结合实际服务错误和账号遥测判断：可能是模型容量、网络、认证或额度问题，单凭提示词不能归因为额度耗尽。已证实额度受限时按窗口退避；恢复期间仍按[多账号恢复检查](#account-handoff-checks)处理执行账号与 goal。只有明确授权继续时才 queue 消息；queue 不是按额度重置时间触发的定时器，也不保证卸载的线程自行恢复，投递前提见[投递机制](#queue-mechanism)。

## <a id="monitoring-rules"></a>无人值守会话的监控守则

🧭 以下阈值与判据来自多日监控长研究会话的现场沉淀（Codex 0.15x–0.162），数字是采用值不是普适规律：

- **活跃**：rollout 5 分钟内有写入 → 不打扰。
- **停下**：超 10 分钟无写入 → 先查该会话拉起的长时工具进程（构建、证明器等）是否在跑——长调用期间 rollout 静默是正常的（见 [mtime 静默](#rollout-signals)），别误推。
- **`task_complete` 只是回合结束**：可能是限流暂停后的自然收尾，也可能是委派死锁——父线程给子代理发完消息就收工、子代理"暂停等重验"，双方互等，这种假待命从 rollout 最难认。按 monitor 语义 `task_complete` 就算正常回合结束、不推，只推半截事件流等真正异常形态。
- **裸"继续"失灵时改明确指令**：如"不要委派、自己提交+验证+推送"，把动作说全，效果完全不同。
- **tmux 只是 PTY 宿主，非必需**：daemon 托管的会话在 TUI 进程死后照样跑，随时 `codex resume <id>` 或 `codex agents`（浏览共享 daemon 上的全部会话）附加；queue 排队与用户在 TUI 里的操作天然不冲突（不抢占）。
- **给会话安排的监控命令轮换写法**（if/case/显式路径交替）：完全相同的命令反复执行，会被工具侧的"无进展"判定拦下（🧭 现场经验，未在源码定位到该判定的具体实现）。

> 最大的教训：别把保守当免费。TUI 挂着 ≠ 有人在操作；有明确授权指令时"不执行才需要理由"。自设"再等等"的豁免可能白白耗掉一整晚的窗口。
