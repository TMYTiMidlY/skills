# Codex 会话监控与远程推进

无人值守的 Codex 会话（TUI 挂着、daemon 托管或 `exec` 拉起的长任务）从外部只有两条主线：**观察**看 rollout 会话存档，**推进**用 `codex queue` 排队消息或 `codex exec resume` 无头恢复。本篇整理 rollout 判读、queue 语义、resume 边界、限流退避和监控守则；源码引用锁定 `rust-v0.162.1`（本机实测 CLI 同版本），🔬 标注 2026-10-12 在隔离 `CODEX_HOME`、非 git 目录下的实测，🧭 标注一次性现场观察、未复现验证。app-server 与 daemon 的进程模型见 [Codex 运行时笔记](codex.md#app-server-lifecycle)。

## <a id="rollout-signals"></a>rollout 存档的判读

会话存档是 `$CODEX_HOME/sessions/YYYY/MM/DD/rollout-<时间戳>-<会话UUID>.jsonl`，每行一个 JSON 事件。判断会话状态看两样就够：文件 **mtime**（最后写入时间）和**尾部事件类型**。客户端 UI 的显示、进程是否存在都不能替代这份磁盘记录。

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

此时不要反复重试抢锁——用 queue 排队（回合结束自动投递）或 TUI 附加。持有进程死亡后文件锁随进程释放，resume 即可接管（🔬 实测：杀掉进行中回合的进程后 resume 成功）。

> 源码：[写锁的 WouldBlock 判定与报错文案](https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/rollout/src/writer_lock.rs#L42-L79)、[锁冲突映射为 thread-store conflict](https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/thread-store/src/local/mod.rs#L341-L360)。

### <a id="resume-exit-codes"></a>git 检查与退出码

`exec` 默认要求在 git 仓库内运行（沿目录向上找仓库根）；非 git 目录要加 `--skip-git-repo-check`。缺 flag 时（🔬 实测原文，退出码 1）：

```text
Not inside a trusted directory and --skip-git-repo-check was not specified.
```

退出码语义：`1` 是常规错误（上述两种都是），`2` 是用法错误（🔬 实测：给 `exec resume` 传 `-s read-only` 即报 Usage 错误退出 2），`101` 是 Rust 惯例的 **panic** 退出码。panic 不回滚已完成的磁盘写入——文件改动、git 提交是否落盘以仓库实际状态为准，别被 101 吓到；rollout 里表现为回合没有收尾事件，进度按尾部事件判断。

## <a id="rate-limit"></a>限流的判读与退避

rollout 的 `token_count` 事件自带权威限流遥测：`rate_limits` 含 `used_percent`、`window_minutes`、`resets_at`、credits 余额与套餐类型（🔬 本机会话实测可见 `used_percent: 33.0`、`window_minutes: 10080`）。监控脚本直接从 rollout 尾部读这份数据，比盯 UI 弹窗可靠。

🧭 现场经验（未逐一复现，供归因排序）：`high demand` / `Reconnecting` / `stream disconnected` 提示、远端压缩（compact）失败、一分钟左右快速空转的 `task_complete`，背后多半都是限流；上下文打满后的远端压缩同样会被限流拖死，表现为 resume 立刻退出。对策只有退避一条路：queue 排上消息，额度窗口放行后自动续跑；连续重试只是烧配额。

## <a id="monitoring-rules"></a>无人值守会话的监控守则

🧭 以下阈值与判据来自多日监控长研究会话的现场沉淀（Codex 0.15x–0.162），数字是采用值不是普适规律：

- **活跃**：rollout 5 分钟内有写入 → 不打扰。
- **停下**：超 10 分钟无写入 → 先查该会话拉起的长时工具进程（构建、证明器等）是否在跑——长调用期间 rollout 静默是正常的（见 [mtime 静默](#rollout-signals)），别误推。
- **`task_complete` 只是回合结束**：可能是限流暂停后的自然收尾，也可能是委派死锁——父线程给子代理发完消息就收工、子代理"暂停等重验"，双方互等，这种假待命从 rollout 最难认。按 monitor 语义 `task_complete` 就算正常回合结束、不推，只推半截事件流等真正异常形态。
- **裸"继续"失灵时改明确指令**：如"不要委派、自己提交+验证+推送"，把动作说全，效果完全不同。
- **tmux 只是 PTY 宿主，非必需**：daemon 托管的会话在 TUI 进程死后照样跑，随时 `codex resume <id>` 或 `codex agents`（浏览共享 daemon 上的全部会话）附加；queue 排队与用户在 TUI 里的操作天然不冲突（不抢占）。
- **给会话安排的监控命令轮换写法**（if/case/显式路径交替）：完全相同的命令反复执行，会被工具侧的"无进展"判定拦下（🧭 现场经验，未在源码定位到该判定的具体实现）。

> 最大的教训：别把保守当免费。TUI 挂着 ≠ 有人在操作；有明确授权指令时"不执行才需要理由"。自设"再等等"的豁免可能白白耗掉一整晚的窗口。
