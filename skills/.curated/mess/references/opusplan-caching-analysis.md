# opusplan 模式：上下文缓存与成本分析

> **注意**：定价数据截止 2026-04，模型版本和价格可能已变化。以下分析侧重方法论（缓存行为与模型切换代价），具体数值仅供参考。

## 背景

Claude Code 的 `opusplan` 模式：plan 阶段用 Opus，exec 阶段用 Sonnet，自动切换。
调研动机：反复切换模型时，上下文缓存（prompt caching）能否被复用？以及为什么 opusplan 下 Opus 被限制为 200k 上下文。

---

## 一、缓存能否跨模型复用

**结论：不能，且这是物理层面的根本限制。**

Anthropic prompt caching 缓存的是 **KV Cache**（Transformer attention 层的中间计算结果）。
KV Cache 与模型架构强绑定：层数、head 数、维度均不同，无法互相填充。

```
Turn 1: model=opus    messages=[A]       → 建立 Opus KV Cache ✓
Turn 2: model=opus    messages=[A,B]     → 命中 Opus 缓存 ✓
Turn 3: model=sonnet  messages=[A,B,C]   → Sonnet 无缓存，冷启动 ✗（全量重算）
Turn 4: model=sonnet  messages=[A,B,C,D] → 命中 Sonnet 缓存 ✓
Turn 5: model=opus    messages=[...]     → Opus 旧缓存已过 5min TTL，冷启动 ✗
```

opusplan 的自动切换与手动 `/model` 切换本质相同——API 调用的 model 参数变了，缓存就失效。
Claude Code changelog 也明确记录（v2.2.x 顶部）：

> Improved `/model` to warn before switching models mid-conversation, since **the next response re-reads the full history uncached**

---

## 二、Opus 在 opusplan 下被限为 200k 的原因

观察：opusplan 模式下 Opus 的上下文窗口与 Sonnet 相同（200k），而非 Opus 的 1M。

推测原因：opusplan 是 session 级配置，两模型共享同一对话历史。若 Opus plan 阶段用 1M，切换到 Sonnet 执行时同样需要处理该长度的上下文，系统可能统一按较低标准（200k）限制，避免 Sonnet 阶段出问题。

相关 changelog：
- v2.1.75：Max/Team/Enterprise 为 Opus 4.6 默认启用 1M 上下文窗口（纯 Opus 模式）
- `CLAUDE_CODE_DISABLE_1M_CONTEXT` 环境变量可禁用 1M 支持

---

## 三、成本分析

### API 定价（$/MTok，2026-04）

| | Opus 4.6 | Sonnet 4.6 |
|---|---|---|
| 输入（常规） | $5.00 | $3.00 |
| 缓存写入（5min） | $6.25 (1.25×) | $3.75 (1.25×) |
| 缓存读取 | $0.50 (0.1×) | $0.30 (0.1×) |
| 输出 | $25.00 | $15.00 |

### 模拟：6 轮对话，上下文 20k→70k，每轮输出 5k

| 方案 | 总成本 | vs 纯 Sonnet |
|------|--------|-------------|
| 纯 Sonnet | **$0.77** | 基准 |
| opusplan（1 次切换） | $1.06 | +37% |
| 纯 Opus | $1.29 | +67% |
| opusplan（2 次切换，含切回 Opus） | **$1.52** | **+97%** |

### 关键发现

1. **切回 Opus 是最贵的操作**：60k tokens × $6.25/M = $0.375，比缓存读取（$0.03）贵 12 倍
2. **Sonnet 输出差价（$10/MTok）救不了缓存惩罚**：每轮输出省 $0.05，一次切换惩罚 $0.15–$0.375
3. **切换越多、上下文越大，opusplan 越亏**；极端情况比纯 Opus 还贵

---

## 四、正确的使用定位

| 目标 | 推荐方案 |
|------|---------|
| 省钱（API 按量付费） | 纯 Sonnet |
| 最高质量 | 纯 Opus |
| Max 订阅 / 省 Opus 配额 | opusplan（Opus 配额紧张时有价值） |
| 混合质量+成本 | opusplan（接受缓存代价，换取 plan 阶段的 Opus 推理质量） |

**opusplan 是质量分层方案，不是省钱方案。** 对 Max 订阅用户，价值在于保留 Opus 配额给真正需要深度推理的 plan 阶段，机械性 exec 工作消耗 Sonnet 配额。

---

## 数据来源

- **Claude Code changelog**：`~/.claude/cache/changelog.md`（本地缓存）
  - 模型切换缓存失效警告：v2.1.108（第 13 行）
  - opusplan 功能引入：v1.0.77（第 2469 行）
  - 1M 上下文窗口启用：v2.1.75（第 760 行）
  - `CLAUDE_CODE_DISABLE_1M_CONTEXT` 环境变量：第 1172 行
- **Anthropic API 定价**：https://platform.claude.com/docs/en/about-claude/pricing
- **Anthropic Prompt Caching 文档**：https://platform.claude.com/docs/en/build-with-claude/prompt-caching
