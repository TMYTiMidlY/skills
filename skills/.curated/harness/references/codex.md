# Codex 运行时笔记

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
