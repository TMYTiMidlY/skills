---
name: harness
description: Agent harness / runtime 架构知识库。调试或设计 Copilot CLI / Copilot SDK / Claude Code / Codex 等 coding agent 的 runtime，处理 MCP / 工具注入、会话存储与导出、配置发现（指令 / hooks / skills）与 Agent Skills 官方目录规范（`assets/` 等），或在 CLI 子进程 / SDK client / extension host / JSON-RPC / HTTP 等集成形态间取舍、用代码编排 coding agent 时使用。
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

- [Copilot CLI 运行时笔记](references/copilot-cli.md)：进程模型、bash 工具环境变量、权限、终端、Git 认证、运行中插话（steer / queue），以及会话存储与 `/share html` 导出。
- [Copilot CLI app.js 运行时补丁](references/copilot-patch.md)：stock 无配置可改、只能改 bundle 的几处行为 + **一键补丁脚本** `scripts/patch-copilot-cli.py`——重试 `maxRetries` 5→10、默认档位（effort 最高档 ＋ context `long_context`、typed `/model` 不掉档）、`web_fetch` SSRF 放行 fake-ip；含通用套路、稳定锚点、四象限实测、PTY 验证法与脚本失效时的手动逆向工作流。
- [Copilot CLI 配置发现](references/copilot-discovery.md)：walk-up（向上查找）机制、Custom Instructions（指令文件）、Hooks、MCP 配置、Skills 发现。
- [MCP 工具名跨客户端命名 / 前缀对照](references/mcp.md)：一个 MCP server 的工具 `foo` 暴露给模型时是裸名还是加 server 前缀——五家（Copilot CLI / Claude Code / Codex / Gemini CLI / Cursor）逐一核实：**全部**加前缀，且前缀一律取**客户端配置里的 server key**（非 server 握手声明名），故工具名再自带 server 名即冗余 stutter（`portal` server 的 `portal_exec`→`portal-portal_exec`）；分隔符各异（Copilot/Cursor `-`、Gemini `mcp_…_`、Claude/Codex `mcp__…__`）、config-key vs 声明名、净化 / 64 字符截断规则；Codex/Gemini 读源码 file:line 核实，Copilot/Claude/Cursor 闭源标 live 实测 / 官方文档。
- [Coding-agent SDK：Copilot / Claude / Codex 横向对照](references/sdk.md)：agent SDK vs API SDK 区分、CLI 子进程 / SDK client / extension host / JSON-RPC / HTTP 取舍、三家官方 agent SDK 与官方 API SDK 各自的语言覆盖 / 开放度 / API 形状 / 内联文档源码，`CopilotClient`、`RuntimeConnection`、`joinSession()`、client-vs-extension 区分，以及把 agent SDK 包成多用户 web 服务的服务端集成模式。
- [Agent Skills 官方结构与目录规范](references/agent-skills.md)：可移植 skill bundle 格式——`SKILL.md`（唯一硬要求）+ `scripts/`（执行、只回结果）/ `references/`（按需读进上下文）/ `assets/`（静态资源，不整体进上下文）的分野，及「是 `assets/` 复数、不是 `asset/`」等约定与边界。
- [Worktree 支持横向对照](references/worktree.md)：Copilot CLI / Codex / Claude Code 三家谁有原生 git worktree 工具、谁只是"感知"、谁完全没有——`--worktree`/`EnterWorktree`/`isolation: worktree`/`/batch`（Claude Code 官方文档逐字核实）、Codex 的 worktree 探测与 `multi_agents` 共享 cwd（读源码 file:line 核实）、以及 obra/superpowers `using-git-worktrees` skill 的跨宿主兜底三段式。
- [三家安装与分发形态](references/install.md)：Codex / Claude Code / Copilot CLI 的"壳包 + 平台二进制子包"打包普查——各家壳包 `bin`/体积、平台子包命名与个数（Codex 6 个无 musl vs 另两家 8 个含 musl）、真身工具链（Codex=Rust / Claude=Bun `--compile` / Copilot=Node SEA，含下载二进制实测判据）、libc 分叉判据与"静态 musl 单二进制通吃"反例、curl/brew/winget/npm 四路安装方案（照官方 README 核对）、npm "软弃用"（README 标 deprecated 但 registry 无标记、照装照用）与"编成单文件⇒才敢弃 npm"的因果、source-map 泄露旁证、agent 侧采用度快照（周下载量名次周周变）。通用打包模式本身见 software 的 [package-managers.md 第八节](../software/references/package-managers.md)。
- [pi：极简可扩展编码 agent（harness / runtime 参考）](references/pi.md)：Mario Zechner 的 pi（`earendil-works/pi`，原 `badlogic/pi-mono`）——"primitives, not features" 的终端 agent。runtime 架构（agent loop、JSONL 会话**树** `id`/`parentId`、配置/指令发现只认 `AGENTS.md`/`CLAUDE.md` 走 **FS 根**、**无 `PI.md`**、信任≠沙箱）；五种调用形态 TUI/print/JSON/**RPC**（31 条命令）/**SDK** `createAgentSession`（OpenClaw 即嵌 SDK，核心无内置 Web）；接入 **Codex / Copilot 官方订阅**（pi 自跑 OAuth 不复用官方 CLI 凭据）；切模型 / 上下文 / effort / 自定义模型接入均见下条 `pi-custom-model.md`；扩展系统（jiti 加载、Bun `virtualModules` vs Node alias、**33 事件其中 15 可拦截/改写**、`ToolDefinition`、发布到 npm `pi-package` keyword + `pi.dev/packages` 画廊）、skill/prompt/theme（`name` 可选 `description` 必需、`{baseDir}` 已移除、跨 harness 复用 `~/.claude`/`~/.codex/skills`）；多 agent（🟨 `pi-orchestrator` / 🟦 subagent 示例扩展 spawn `pi --mode json` / ⬜ `pi-subagents`·`pi-dynamic-workflows` / tmux）；手机远控（🟧 `pi-telegram`、`pi-chat` + Gondolin 微 VM + 两套密钥系统、Termux `--ignore-scripts`、⬜ pocket-pi 走 `--mode rpc`）；含容器化三模式（Gondolin/Docker/OpenShell）与生态热门插件下载排行。全文源码引用锚定本地 clone `earendil-works/pi@8479bd8`。
- [给 pi 接自定义模型：配置 + 验证](references/pi-custom-model.md)：把任意 OpenAI/Anthropic 兼容端点接进 pi（`~/.pi/agent/models.json`，不走 `/login`）的一站式——provider/model 全字段与默认值、在 pi 里选/切模型（`Ctrl+L`/`--model`/scoped）、上下文长度与压缩（`contextWindow`/`compaction`/`PI_CACHE_RETENTION`）、**两入口 openai-completions ↔ anthropic-messages 对照**（`api` 选型、baseUrl 带不带 `/v1` 及 `…/v1/v1/messages` 404 坑、thinking 路径、cache/image/tool 字段差异）、effort/thinking **三层**（`reasoning` 能力声明 / `thinkingLevelMap` 档位 / `compat.thinkingFormat` 线格式方言 `deepseek`/`zai`/`qwen`…）、`cost` 每百万费率 + **缓存命中靠服务端 `usage` 自报**（openai `cached_tokens` / anthropic `cache_read/creation_input_tokens`）的计费机制、以及接入前的**端点真伪探针**（非法值探针辨校验层、`system_fingerprint` vs LiteLLM `provider_specific_fields` 指纹、枚举集合比对、随机多色图 / 工具闭环 / 缓存）；含 USTC LiteLLM 网关 2026-07 实测快照（别名↔后端路由、5 模型规格·图片·¥ 费率、图/工具/缓存/thinking 端到端、两协议各 5 模型最终配置、5 种之外别名）。每项标来源【pi 文档/源码 · 厂商 · 平台转贴 · 实测】、就近用 `>` 给出处、无脚注。

## Claude Code / Codex 横向对照

SDK 语言覆盖与官方文档已记于上面的 SDK 横向对照。Claude / Codex 的 runtime / harness 行为先粗粒度记在那份对照里；如果后续把进程模型、扩展 / 插件点、会话存储、工具注入、取消、导出 / 调试流程写成体量，再单独拆 reference 文件。

- **Claude Code**：与 Copilot 一样闭源、minified 分发，行为靠逆向；会话存档在 `~/.claude/projects/*.jsonl`。
- **Codex**：`openai/codex` 真开源（Apache-2.0），优先引官方源码与发布文档，而非本地逆向；会话存档在 `~/.codex/sessions/`。
- 三家原生 worktree / 并行隔离支持的详细对照见 [worktree.md](references/worktree.md)。

## 边界

一般的本地软件运维仍归 `software` skill。本 skill 只管 coding agent 的 runtime / harness 内部机制，以及跨厂商 SDK / 接入形态的对照。

- **安装 / 分发的划分**：通用的"包管理器 / npm 壳包 + 平台二进制"打包模式属包管理器话题，在 `software` 的 [package-managers.md 第八节](../software/references/package-managers.md)；**三家 coding agent 具体怎么打包 / 安装 / 用什么工具链编**（Codex / Claude / Copilot 普查）在本 skill 的 [install.md](references/install.md)。
