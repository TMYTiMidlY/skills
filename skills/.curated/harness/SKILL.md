---
name: harness
description: Agent harness / runtime 架构知识库。调试或设计 Copilot CLI / Copilot SDK / Claude Code / Codex 等 coding agent 的 runtime，处理 MCP / 工具注入、会话存储与导出、配置发现（指令 / hooks / skills），或在 CLI 子进程 / SDK client / extension host / JSON-RPC / HTTP 等集成形态间取舍、用代码编排 coding agent 时使用。
---

# Harness

agent runtime / harness（运行壳）相关问题看这里：一个 coding agent 怎么被启动、控制、扩展、接工具、恢复、取消、观察。

## 范围

- Copilot CLI 本体行为、SDK 入口、MCP 配置注入、会话 / 导出、逆向笔记。
- 对照 Claude Code、Codex 的 runtime 模型，做 harness 取舍。
- 设计一个用代码驱动 coding agent 的 daemon / orchestrator（编排器）。
- 在 CLI 子进程、SDK client、extension host、JSON-RPC、HTTP/webhook 几种集成形态间选型。

## References

- [Copilot CLI 运行时笔记](references/copilot-cli.md)：进程模型、bash 工具环境变量、权限、终端、Git 认证、重试 patch、运行中插话，以及会话存储与 `/share html` 导出。
- [Copilot CLI 配置发现](references/copilot-discovery.md)：walk-up（向上查找）机制、Custom Instructions（指令文件）、Hooks、MCP 配置、Skills 发现。
- [Agent harness 架构模式与 Copilot SDK](references/harness-patterns.md)：CLI 子进程 / SDK client / extension host / JSON-RPC / HTTP 取舍，以及 `CopilotClient`、`RuntimeConnection`、`joinSession()`、协议事实与 client-vs-extension 区分。
- [Coding-agent SDK：Copilot / Claude / Codex 横向对照](references/sdk.md)：agent SDK vs API SDK 区分、三家官方 agent SDK 与官方 API SDK 各自的语言覆盖 / 开放度 / 内联文档源码（含 Codex 开源 `sdk/`、会话存档路径）、两者选型。

## 待补充：Claude Code / Codex 横向对照

SDK 语言覆盖与官方文档已记于上面的 SDK 横向对照。后续要补 Claude Code、Codex 的 runtime / harness 行为做横向对照（进程模型、扩展 / 插件点、会话存储、工具注入、取消、导出 / 调试流程）。

- **Claude Code**：与 Copilot 一样闭源、minified 分发，行为靠逆向；会话存档在 `~/.claude/projects/*.jsonl`。
- **Codex**：`openai/codex` 真开源（Apache-2.0），优先引官方源码与发布文档，而非本地逆向；会话存档在 `~/.codex/sessions/`。

补充时如果某产品笔记成体量，再单独拆 reference 文件；篇幅短就先并在本节或 `harness-patterns.md` 的对照里。

## 边界

一般的本地软件运维仍归 `software` skill。本 skill 只管 coding agent 的 runtime / harness 内部机制与跨 harness 架构对照。
