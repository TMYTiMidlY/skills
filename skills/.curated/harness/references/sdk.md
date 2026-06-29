# Coding-agent SDK：Copilot / Claude / Codex 横向对照

要用代码驱动一个 coding agent，先分清两类截然不同的 SDK——选错类型，再多语言也没用：

- **agent SDK**：把"会自己 plan、调工具、改文件、跑 shell、带 session"的整个 **agent runtime**
  封装成库。你给目标 + 权限，它跑完一轮一轮的循环。能直接替掉手搓 `copilot -p` 子进程。
- **API SDK**：chat/completions 的 HTTP 客户端，给 model 一段输入拿一段输出；plan / 工具 /
  文件编辑 / 循环全得自己搭。名字里也带 "sdk"，但低一层——用它做 agent 等于从头写 harness。

qatlas 这类 daemon 要的是 **agent SDK**；下面也列 API SDK 是为了讲清两者别混。矩阵 + 文档实测于
2026-06-29，版本只佐证"有/无"，会动，写死前重核。

## 官方 agent SDK

| agent SDK | 语言覆盖 | 开放度 | 官方文档 / 源码 |
|---|---|---|---|
| **GitHub Copilot** | TS、Python、Go、.NET、Java、Rust（六语言对等，同一引擎）| 闭源引擎，SDK 薄封装 | 总入口 [`github/copilot-sdk`](https://github.com/github/copilot-sdk)；本地打包类型声明 `~/.cache/copilot/pkg/<plat>/<ver>/copilot-sdk/*.d.ts` |
| **Claude Agent SDK** | TS、Python | 闭源（minified），靠逆向 | [`code.claude.com/docs/en/agent-sdk/overview`](https://code.claude.com/docs/en/agent-sdk/overview)；TS 源仓 [`anthropics/claude-agent-sdk-typescript`](https://github.com/anthropics/claude-agent-sdk-typescript)；会话存档 `~/.claude/projects/*.jsonl` |
| **OpenAI Codex SDK** | TS、Python | 真开源 Apache-2.0 | [`platform.openai.com/docs/codex/sdk`](https://platform.openai.com/docs/codex/sdk)；源码 [`openai/codex` `sdk/`](https://github.com/openai/codex/tree/main/sdk) = `typescript`+`python`+`python-runtime`；会话存档 `~/.codex/sessions/` |

Copilot 是唯一把 agent SDK 铺满六语言的，README 定位为 "the same engine behind Copilot CLI… no need
to build your own orchestration"。Claude / Codex 只有 TS、Python；Codex 整仓 Apache-2.0，改 harness 直接读
`sdk/` 源码不必逆向，Claude 闭源行为靠逆向。包名：Copilot `@github/copilot-sdk`、`github-copilot-sdk`、
`GitHub.Copilot.SDK`、`copilot-sdk/go`；Claude `@anthropic-ai/claude-agent-sdk`、`claude-agent-sdk`；
Codex `@openai/codex-sdk`、`openai-codex`。

## 官方 API SDK（裸调模型，不是 agent runtime）

跨语言比 agent SDK 全得多，但只负责"发请求拿回复"；要 agent 行为得自己写编排，别误当 agent SDK 用。

| 厂商 | 文档 | 主要语言 + 包 |
|---|---|---|
| **OpenAI** | [`platform.openai.com/docs/api-reference`](https://platform.openai.com/docs/api-reference) | Node [`openai`](https://github.com/openai/openai-node)、Python [`openai`](https://github.com/openai/openai-python)、Go [`openai/openai-go`](https://github.com/openai/openai-go)（主版本带 major：`/v3`）、Java [`openai-java`](https://github.com/openai/openai-java)、.NET [`openai-dotnet`](https://github.com/openai/openai-dotnet) |
| **Anthropic** | [`docs.claude.com/en/api`](https://docs.claude.com/en/api) | Node `@anthropic-ai/sdk`、Python `anthropic`、Go [`anthropic-sdk-go`](https://github.com/anthropics/anthropic-sdk-go)；官方亦列 Java/Ruby/PHP |

社区非官方封装另算，例如 [`picatz/openai`](https://github.com/picatz/openai)（`codex/` 有 exec/events/items.go，
包 Codex CLI 的 Go 壳）——用前确认维护状态与署名。

## 选 agent SDK 还是 API SDK

需要现成的 plan/工具/文件/会话循环、最少自写代码 → agent SDK（语言不限三家可选，TS/Py 以外只有 Copilot）。
要完全自控编排、或目标语言无对应 agent SDK → API SDK 自搭 harness，或包对方 CLI 子进程。
