# Codex 上下文窗口与自动压缩

Codex 需要分别知道模型可用的上下文窗口，以及历史增长到多少 tokens 时开始自动压缩。前者是客户端的预算上限，后者是提前收缩历史的触发线；只改其中一个，不能完整表达长上下文策略。

> [Codex Configuration Reference](https://developers.openai.com/codex/config-reference/) 将 `model_context_window` 定义为当前模型可用的上下文窗口，将 `model_auto_compact_token_limit` 定义为自动压缩历史的 token 阈值；后者不设置时使用模型默认值。

## `config.toml` 配置

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

## 加载验证

编辑完成后启动新的 Codex 进程，让它重新读取配置。先运行一个不发起模型任务的命令，可检查 TOML 是否能被当前 CLI 正常解析：

```bash
codex features list
```

该检查只能证明配置文件成功加载，不能证明账户已经获得模型权限，也不能证明一次端到端请求实际占用了 1M tokens。模型可用性仍由当前账户和服务端决定。

> 🔬 2026-08-20 在 `codex-cli 0.148.0` 上实测：上述三项写入用户级配置后，`codex features list` 返回成功；这是配置解析检查，不是 1M 请求压力测试。
