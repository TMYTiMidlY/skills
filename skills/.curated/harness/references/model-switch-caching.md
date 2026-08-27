# 模型切换与上下文缓存

对话中途换模型（`opusplan` 自动切换或手动切）时，上下文缓存会发生什么、代价有多大。结论对任何会切模型的 harness 都成立，`opusplan` 只是最常见的触发场景。

> 定价与 changelog 条目为 **2026-04 快照**，模型版本和价格可能已变。下面的方法论（缓存失效机制、切换代价的构成）不随价格变化，具体数值仅供参考。

## 背景

Claude Code 的 `opusplan` 模式：plan 阶段用 Opus，exec 阶段用 Sonnet，自动切换。两个问题：反复切换时上下文缓存（prompt caching）能否被复用？以及为什么 `opusplan` 下 Opus 被限制为 200k 上下文。

## 缓存跨模型复用的可能性

**不能，且这是物理层面的根本限制。**

Anthropic prompt caching 缓存的是 **KV Cache**（Transformer attention 层的中间计算结果）。KV Cache 与模型架构强绑定：层数、head 数、维度均不同，无法互相填充。

```
Turn 1: model=opus    messages=[A]       → 建立 Opus KV Cache ✓
Turn 2: model=opus    messages=[A,B]     → 命中 Opus 缓存 ✓
Turn 3: model=sonnet  messages=[A,B,C]   → Sonnet 无缓存，冷启动 ✗（全量重算）
Turn 4: model=sonnet  messages=[A,B,C,D] → 命中 Sonnet 缓存 ✓
Turn 5: model=opus    messages=[...]     → Opus 旧缓存已过 5min TTL，冷启动 ✗
```

`opusplan` 的自动切换与手动 `/model` 切换本质相同——API 调用的 model 参数变了，缓存就失效。

> 上游佐证：Claude Code changelog **v2.1.108** 条目——"Improved `/model` to warn before switching models mid-conversation, since **the next response re-reads the full history uncached**"。changelog 随 Claude Code 分发（安装后本地留有缓存副本），按版本号检索即可复核。
> 机制说明见 [Anthropic Prompt Caching 文档（2026-03-31 快照）](https://web.archive.org/web/20260331172750/https://platform.claude.com/docs/en/build-with-claude/prompt-caching)——官方文档只有滚动 URL，故引存档快照。

## `opusplan` 下 Opus 的上下文窗口

观察：`opusplan` 模式下 Opus 的上下文窗口与 Sonnet 相同（200k），而非 Opus 的 1M。

推测原因：`opusplan` 是 session 级配置，两模型共享同一对话历史。若 Opus plan 阶段用 1M，切换到 Sonnet 执行时同样需要处理该长度的上下文，系统可能统一按较低标准（200k）限制，避免 Sonnet 阶段出问题。**这是推测，未从官方文档或源码坐实。**

> 相关 changelog 条目：**v2.1.75** 为 Max/Team/Enterprise 的 Opus 4.6 默认启用 1M 上下文窗口（纯 Opus 模式）；`CLAUDE_CODE_DISABLE_1M_CONTEXT` 环境变量可禁用 1M 支持；`opusplan` 功能引入于 **v1.0.77**。

## 成本

### API 定价（$/MTok，2026-04）

| | Opus 4.6 | Sonnet 4.6 |
|---|---|---|
| 输入（常规） | $5.00 | $3.00 |
| 缓存写入（5min） | $6.25 (1.25×) | $3.75 (1.25×) |
| 缓存读取 | $0.50 (0.1×) | $0.30 (0.1×) |
| 输出 | $25.00 | $15.00 |

> 抄录自 [Anthropic API 定价（2026-04-01 快照）](https://web.archive.org/web/20260401185808/https://platform.claude.com/docs/en/about-claude/pricing)——官方定价页只有滚动 URL，故引存档快照以对齐本表数值。

### 模拟：6 轮对话，上下文 20k→70k，每轮输出 5k

| 方案 | 总成本 | vs 纯 Sonnet |
|------|--------|-------------|
| 纯 Sonnet | **$0.77** | 基准 |
| `opusplan`（1 次切换） | $1.06 | +37% |
| 纯 Opus | $1.29 | +67% |
| `opusplan`（2 次切换，含切回 Opus） | **$1.52** | **+97%** |

> 本表为按上面定价自行推算，非厂商公布数据。

### 切换代价的构成

1. **切回 Opus 是最贵的操作**：60k tokens × $6.25/M = $0.375，比缓存读取（$0.03）贵 12 倍。
2. **Sonnet 输出差价（$10/MTok）救不了缓存惩罚**：每轮输出省 $0.05，一次切换惩罚 $0.15–$0.375。
3. **切换越多、上下文越大，`opusplan` 越亏**；极端情况比纯 Opus 还贵。

## 使用定位

| 目标 | 推荐方案 |
|------|---------|
| 省钱（API 按量付费） | 纯 Sonnet |
| 最高质量 | 纯 Opus |
| Max 订阅 / 省 Opus 配额 | `opusplan`（Opus 配额紧张时有价值） |
| 混合质量+成本 | `opusplan`（接受缓存代价，换取 plan 阶段的 Opus 推理质量） |

`opusplan` 是质量分层方案，不是省钱方案。对 Max 订阅用户，价值在于保留 Opus 配额给真正需要深度推理的 plan 阶段，机械性 exec 工作消耗 Sonnet 配额。
