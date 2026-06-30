---
name: harness
description: Agent harness / runtime 架构知识库。调试或设计 Copilot CLI / Copilot SDK / Claude Code / Codex 等 coding agent 的 runtime，处理 MCP / 工具注入、会话存储与导出、配置发现（指令 / hooks / skills），或在 CLI 子进程 / SDK client / extension host / JSON-RPC / HTTP 等集成形态间取舍、用代码编排 coding agent 时使用。
---

# Harness

agent runtime / harness（运行壳）相关问题看这里：一个 coding agent 怎么被启动、控制、扩展、接工具、恢复、取消、观察。

## 名词解释：harness / agent harness

- **harness 本义**：英文指马具 / 挽具、束线束——套在动力源（马、成捆线缆）外面、把它的力**约束并引导**为我所用的那层装置；动词 to harness ＝ 驾驭、为我所用。
- **agent harness（在 AI 里）**：**包在 LLM 外面、把"只会输出 token 的模型"撑成"会 plan、会调工具、会改文件、带 session 的 agent"的那层执行框架 / 基础设施**——agentic loop（一轮轮循环）、prompt 拼装、tool-calling 胶水、上下文 / 记忆管理、sandbox、权限、会话存储都在这层。关键：**harness 不是"在外面驱动 agent 的那层"，它本身就是把模型撑成 agent 的那层**——一个 coding agent ≈ 模型 + 它的 harness。（类比：LLM 是发动机，harness 是底盘 + 传动 + 控制系统，把发动机变成整车。）
- **三个同指的标准词**：`agent scaffolding`（脚手架）/ `harness`（运行壳）/ `elicitation`（把模型能力"引出来"）——指的都是模型外面这层执行框架。用词随圈子：agent 评测圈（METR / Epoch）爱说 scaffolding / elicitation，实践者 / 博客圈说 harness，厂商侧 Anthropic 说 agentic systems / orchestration、GitHub 产品线叫 coding agent。所以 harness 是个**广为理解、但非某家厂商官方**的词。
- **为什么这层重要**：被反复引用的实测——**同一个模型，只换 harness，SWE-bench 分数能差出 20+ 个百分点**（有对比给到 46% vs 80% 这种量级）。故有 "the harness is the real differentiator"、"LLM is the smallest part of an agent system" 的说法：决定一个 agent 好不好用的，往往是这层壳而不是模型本身。（具体数字随评测 / 来源浮动，引用前自己再核。）
- **在本 skill 里**：讲的就是各家 coding agent（Copilot / Claude Code / Codex）的这层壳怎么运转、怎么被程序驱动、怎么调试；以及当你要从**外部**接上 / 驱动它们时，在 CLI 子进程 / SDK client / extension host / JSON-RPC / HTTP 几种**接入形态**间怎么取舍。

## 范围

- Copilot CLI 本体行为、SDK 入口、MCP 配置注入、会话 / 导出、逆向笔记。
- 对照 Claude Code、Codex 的 runtime 模型，做 harness 取舍。
- 设计一个用代码驱动 coding agent 的 daemon / orchestrator（编排器）。
- 在 CLI 子进程、SDK client、extension host、JSON-RPC、HTTP/webhook 几种集成形态间选型。

## References

- [Copilot CLI 运行时笔记](references/copilot-cli.md)：进程模型、bash 工具环境变量、权限、终端、Git 认证、重试 patch、运行中插话，以及会话存储与 `/share html` 导出。
- [Copilot CLI 配置发现](references/copilot-discovery.md)：walk-up（向上查找）机制、Custom Instructions（指令文件）、Hooks、MCP 配置、Skills 发现。
- [Coding-agent SDK：Copilot / Claude / Codex 横向对照](references/sdk.md)：agent SDK vs API SDK 区分、CLI 子进程 / SDK client / extension host / JSON-RPC / HTTP 取舍、三家官方 agent SDK 与官方 API SDK 各自的语言覆盖 / 开放度 / API 形状 / 内联文档源码，`CopilotClient`、`RuntimeConnection`、`joinSession()`、client-vs-extension 区分，以及把 agent SDK 包成多用户 web 服务的服务端集成模式。

## Claude Code / Codex 横向对照

SDK 语言覆盖与官方文档已记于上面的 SDK 横向对照。Claude / Codex 的 runtime / harness 行为先粗粒度记在那份对照里；如果后续把进程模型、扩展 / 插件点、会话存储、工具注入、取消、导出 / 调试流程写成体量，再单独拆 reference 文件。

- **Claude Code**：与 Copilot 一样闭源、minified 分发，行为靠逆向；会话存档在 `~/.claude/projects/*.jsonl`。
- **Codex**：`openai/codex` 真开源（Apache-2.0），优先引官方源码与发布文档，而非本地逆向；会话存档在 `~/.codex/sessions/`。

## 边界

一般的本地软件运维仍归 `software` skill。本 skill 只管 coding agent 的 runtime / harness 内部机制，以及跨厂商 SDK / 接入形态的对照。
