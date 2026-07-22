---
name: harness
description: Agent harness / runtime 架构知识库。调试或设计 Copilot CLI / Copilot SDK / Claude Code / Codex / Hermes / pi / Kimi Code 等 coding agent 的 runtime，处理 MCP / 工具注入、会话存储与导出、配置发现（指令 / hooks / skills）与 Agent Skills 官方目录规范（`assets/` 等），或在 CLI 子进程 / SDK client / extension host / JSON-RPC / HTTP 等集成形态间取舍、用代码编排 coding agent 时使用；Hermes agent 的常驻服务 / 多后端 / provider 接入 / skill 体系整体在此。
---

# Harness

agent runtime / harness（运行壳）相关问题看这里：一个 coding agent 怎么被启动、控制、扩展、接工具、恢复、取消、观察。

## 名词解释：harness / agent harness

"harness" 在 agent 语境下被重载成两种指向不同层的用法，先分清；**本 skill 讲的是 ① agent harness**，② 只为消歧。

- **harness 本义**：英文指马具 / 挽具、束线束——套在动力源外面、把它的力**约束并引导**为我所用的那层装置；动词义即"驾驭、为我所用"（to harness ＝ to put to use）。下面两种引申都由此而来。
- **① agent harness / coding harness（向内，本 skill 主要用这个义）**：把模型撑成 agent 的那层执行框架——agentic loop（多轮工具循环）、prompt 拼装、tool-calling 胶水与参数校验、上下文 / 记忆管理、sandbox、权限、会话存储。一句话 **模型 + harness ＝ agent**，"没有 harness 只有建议，有 harness 才有执行"（OpenAI DevEx 的 [Codex = Model + Harness + Surfaces](https://www.linkedin.com/pulse/how-i-think-codex-gabriel-chua-ukhic)；Pi 作者 Armin 称 Pi / Claude Code 为 "coding harness"，说 harness ["校验参数、执行编辑、把结果喂回模型"](https://lucumr.pocoo.org/2026/7/4/better-models-worse-tools/)）。
- **② test / evaluation harness（向外，经典软件义）**：从外部驱动、运行被测物的 runner。经典软件工程里 [test harness](https://en.wikipedia.org/wiki/Test_harness) 即"stubs + drivers 组成、模拟运行环境、自身不含测试内容"的外层基础设施；用在 LLM 上就是 EleutherAI 的 [`lm-evaluation-harness`](https://github.com/EleutherAI/lm-evaluation-harness/tree/f4d4b3de3ee6741a7151a9fe74945ee515262f4c)、SWE-bench 的 [`swebench.harness.run_evaluation`](https://github.com/SWE-bench/SWE-bench/tree/f7bbbb2ccdf479001d6467c9e34af59e44a840f9)——**拿 agent 产物评分、把 agent 当黑盒外部件**；SEC-bench 更直接命名 ["Evaluation harness for OpenCode agent"](https://github.com/SEC-bench/SEC-bench-Pro/blob/f497600d25b300c3e81db6fc0e570dc754a8f20f/harness/eval_opencode.py)（起容器、跑 agent、收结果）。
- **两义靠限定词分**：几乎没人在一篇里明说二者之别，全靠限定词——带 "evaluation / test" 的指向外 runner，不带限定或说 "agent / coding harness" 的指向内 scaffolding。所以"从外面驱动一个 agent 的那层"是真概念，但准确叫法是 **orchestrator / runner**（评测场景叫 evaluation harness），不叫 "agent harness"。本 skill 的 [sdk.md](references/sdk.md) 讲的 CLI 子进程 / SDK client / extension host 等**接入形态**，就是你的 orchestrator 从外部接上一个自带 ①义 harness 的 agent；而用 API SDK 自写循环时，你是在造一个自定义的 ①义 harness——如 [CompileBench](https://simonwillison.net/2025/Sep/22/compilebench/) 在 OpenAI Go 库上写 agentic loop + 一个工具。
- **近义词**：`scaffolding`（脚手架，研究 / 评测圈如 METR 常用）≈ ①义 harness（实践者常用）；`ACI`（agent-computer interface，SWE-agent 提出）特指 ①义里"工具接口"那块；`elicitation`（METR）是"不断调 scaffolding 把模型能力引出来"的**过程**、非 scaffolding 本身。厂商侧：Anthropic 说 "agentic systems / orchestration"、GitHub 叫 "coding agent"。harness 广为理解、但非厂商官方词。
- **为什么这层重要**：同一模型只换 ①义 harness，agent 实测能力能差出一大截——工具 schema、编辑工具、循环设计都影响成败（见上文 Armin 分析与 METR 的 elicitation 研究）。决定 agent 好不好用的，往往是这层壳而非模型本身。
- **在本 skill 里**：讲各家 coding agent（Copilot / Claude Code / Codex）这层壳（①义）怎么运转、怎么被程序驱动、怎么调试；以及从外部接上 / 驱动它们时，在 CLI 子进程 / SDK client / extension host / JSON-RPC / HTTP 几种**接入形态**间怎么取舍。

## 范围

- Copilot CLI 本体行为、SDK 入口、MCP 配置注入、会话 / 导出、逆向笔记。
- 对照 Claude Code、Codex 的 runtime 模型，做 harness 取舍。
- 设计一个用代码驱动 coding agent 的 daemon / orchestrator（编排器）。
- 在 CLI 子进程、SDK client、extension host、JSON-RPC、HTTP/webhook 几种集成形态间选型。

## References

- [Copilot CLI 运行时笔记](references/copilot-cli.md)：进程模型、bash 工具环境变量、权限、终端、Git 认证、运行中插话（steer / queue），以及会话存储与 `/share html` 导出。
- [会话跨机迁移与备份（Copilot / Claude / Codex）](references/migrate.md)：把**可 resume**的会话搬到另一台机（换 home / cwd / 用户名）要搬什么、改什么——三家磁盘形态与每行 jsonl 形状对照；DB/目录并集枚举（完整、空壳、dir-only、DB-only）与整目录 session files，含 `rewind-snapshots` 排除/冷归档/恢复语义的现场取舍；Copilot 的 db/yaml/**文件 mtime** 分工实测（名字来自 workspace.yaml、时间/排序/prune 全看文件 mtime、DB 只管 `/chronicle`、DB 无 `name` 列）；resume 解析（Copilot 目录驱动不查 sqlite / Codex sqlite 可选、扫文件名兜底）；cwd 三处 + `git_root` 的结构化改写、历史正文旧路径不应全文替换、`resume-auto-cd` 告警与 `COPILOT_DISABLE_RESUME_AUTO_CD`；可读 JS `pruneOldSessions` RPC 与另一次未归因的命名会话目录消失实测、`cp -p` 雷区；btime 不可改、不可变时间清单；**云端同步副本**（`mc_*` 挂钩、`/session delete --remote` 连删云端 vs `--local-only` 只删本地、逐字搬 yaml 致源/目标共享同一云端 task、批量删务必 `--local-only`）；`COPILOT_HOME`/`--config-dir` 隔离测试但不代替 cwd 映射；项目树与会话状态的独立边界、两阶段 rsync cutover、软链接分类、DB 增量合并、六层验收矩阵、quarantine→trash-put→独立核验→trash-rm 的源端彻底清理、临时 SSH key 去重语义、NVM 非交互 PATH 假阴性；归档≠迁移；`pexpect`/`TIOCSCTTY` 无头驱动 TUI 实测法。含 🔬实测 / 📖锁版本源码 / 🧭现场三档置信标注。
- [Copilot CLI app.js 运行时补丁](references/copilot-patch.md)：stock 无配置可改、只能改 bundle 的几处行为 + **一键补丁脚本** `scripts/patch-copilot-cli.py`——重试 `maxRetries` 5→10、默认档位（effort 最高档 ＋ context `long_context`、typed `/model` 不掉档）、`web_fetch` SSRF 放行 fake-ip；含通用套路、稳定锚点、四象限实测、PTY 验证法与脚本失效时的手动逆向工作流。
- [Copilot CLI 配置发现](references/copilot-discovery.md)：walk-up（向上查找）机制、Custom Instructions（指令文件）、Hooks、MCP 配置、Skills 发现。
- [MCP 工具名跨客户端命名 / 前缀对照](references/mcp.md)：一个 MCP server 的工具 `foo` 暴露给模型时是裸名还是加 server 前缀——五家（Copilot CLI / Claude Code / Codex / Gemini CLI / Cursor）逐一核实：**全部**加前缀，且前缀一律取**客户端配置里的 server key**（非 server 握手声明名），故工具名再自带 server 名即冗余 stutter（`portal` server 的 `portal_exec`→`portal-portal_exec`）；分隔符各异（Copilot/Cursor `-`、Gemini `mcp_…_`、Claude/Codex `mcp__…__`）、config-key vs 声明名、净化 / 64 字符截断规则；Codex/Gemini 读源码 file:line 核实，Copilot/Claude/Cursor 闭源标 live 实测 / 官方文档。
- [Coding-agent SDK：Copilot / Claude / Codex 横向对照](references/sdk.md)：agent SDK vs API SDK 区分、CLI 子进程 / SDK client / extension host / JSON-RPC / HTTP 取舍、三家官方 agent SDK 与官方 API SDK 各自的语言覆盖 / 开放度 / API 形状 / 内联文档源码，`CopilotClient`、`RuntimeConnection`、`joinSession()`、client-vs-extension 区分，以及把 agent SDK 包成多用户 web 服务的服务端集成模式。
- [Agent Skills 官方结构与目录规范](references/agent-skills.md)：可移植 skill bundle 格式——`SKILL.md`（唯一硬要求）+ `scripts/`（执行、只回结果）/ `references/`（按需读进上下文）/ `assets/`（静态资源，不整体进上下文）的分野，及「是 `assets/` 复数、不是 `asset/`」等约定与边界。
- [Worktree 支持横向对照](references/worktree.md)：Copilot CLI / Codex / Claude Code 三家谁有原生 git worktree 工具、谁只是"感知"、谁完全没有——`--worktree`/`EnterWorktree`/`isolation: worktree`/`/batch`（Claude Code 官方文档逐字核实）、Codex 的 worktree 探测与 `multi_agents` 共享 cwd（读源码 file:line 核实）、以及 obra/superpowers `using-git-worktrees` skill 的跨宿主兜底三段式。
- [三家安装与分发形态](references/install.md)：Codex / Claude Code / Copilot CLI 的"壳包 + 平台二进制子包"打包普查——各家壳包 `bin`/体积、平台子包命名与个数（Codex 6 个无 musl vs 另两家 8 个含 musl）、真身工具链（Codex=Rust / Claude=Bun `--compile` / Copilot=Node SEA，含下载二进制实测判据）、libc 分叉判据与"静态 musl 单二进制通吃"反例、curl/brew/winget/npm 四路安装方案（照官方 README 核对）、npm "软弃用"（README 标 deprecated 但 registry 无标记、照装照用）与"编成单文件⇒才敢弃 npm"的因果、source-map 泄露旁证、agent 侧采用度快照（周下载量名次周周变）。通用打包模式本身见 software 的 [package-managers.md 第八节](../software/references/package-managers.md)。
- [pi：极简可扩展编码 agent（harness / runtime 参考）](references/pi.md)：Mario Zechner 的 pi（`earendil-works/pi`，原 `badlogic/pi-mono`）——"primitives, not features" 的终端 agent。runtime 架构（agent loop、JSONL 会话**树** `id`/`parentId`、配置/指令发现只认 `AGENTS.md`/`CLAUDE.md` 走 **FS 根**、**无 `PI.md`**、信任≠沙箱）；五种调用形态 TUI/print/JSON/**RPC**（31 条命令）/**SDK** `createAgentSession`（OpenClaw 即嵌 SDK，核心无内置 Web）；接入 **Codex / Copilot 官方订阅**（pi 自跑 OAuth 不复用官方 CLI 凭据）；切模型 / 上下文 / effort / 自定义模型接入均见下条 `pi-custom-model.md`；扩展系统（jiti 加载、Bun `virtualModules` vs Node alias、**33 事件其中 15 可拦截/改写**、`ToolDefinition`、发布到 npm `pi-package` keyword + `pi.dev/packages` 画廊）、skill/prompt/theme（`name` 可选 `description` 必需、`{baseDir}` 已移除、跨 harness 复用 `~/.claude`/`~/.codex/skills`）；多 agent（🟨 `pi-orchestrator` / 🟦 subagent 示例扩展 spawn `pi --mode json` / ⬜ `pi-subagents`·`pi-dynamic-workflows` / tmux）；手机远控（🟧 `pi-telegram`、`pi-chat` + Gondolin 微 VM + 两套密钥系统、Termux `--ignore-scripts`、⬜ pocket-pi 走 `--mode rpc`）；含容器化三模式（Gondolin/Docker/OpenShell）与生态热门插件下载排行。全文源码引用锚定本地 clone `earendil-works/pi@8479bd8`。
- [给 pi 接自定义模型：配置 + 验证](references/pi-custom-model.md)：把任意 OpenAI/Anthropic 兼容端点接进 pi（`~/.pi/agent/models.json`，不走 `/login`）的一站式——provider/model 全字段与默认值、在 pi 里选/切模型（`Ctrl+L`/`--model`/scoped）、上下文长度与压缩（`contextWindow`/`compaction`/`PI_CACHE_RETENTION`）、**两入口 openai-completions ↔ anthropic-messages 对照**（`api` 选型、baseUrl 带不带 `/v1` 及 `…/v1/v1/messages` 404 坑、thinking 路径、cache/image/tool 字段差异）、effort/thinking **三层**（`reasoning` 能力声明 / `thinkingLevelMap` 档位 / `compat.thinkingFormat` 线格式方言 `deepseek`/`zai`/`qwen`…）、`cost` 每百万费率 + **缓存命中靠服务端 `usage` 自报**（openai `cached_tokens` / anthropic `cache_read/creation_input_tokens`）的计费机制、以及接入前的**端点真伪探针**（非法值探针辨校验层、`system_fingerprint` vs LiteLLM `provider_specific_fields` 指纹、枚举集合比对、随机多色图 / 工具闭环 / 缓存）；含 USTC LiteLLM 网关 2026-07 实测快照（别名↔后端路由、5 模型规格·图片·¥ 费率、图/工具/缓存/thinking 端到端、两协议各 5 模型最终配置、5 种之外别名）。每项标来源【pi 文档/源码 · 厂商 · 平台转贴 · 实测】、就近用 `>` 给出处、无脚注。
- [Hermes（NousResearch/hermes-agent）运行时](references/hermes.md)：Python CLI 的 coding agent 框架，把**多后端命令执行**与**常驻服务化**做进核心——systemd 常驻服务（`gateway` 消息平台 / `dashboard` Web UI、`HERMES_HOME` 决定身份与读写位置、systemd 不继承交互 shell PATH 的坑）、terminal backend（`local`/`ssh`/`docker`/`modal`/`daytona`/`singularity`，`config.yaml` vs `.env` 优先级、session 级隔离走 profile 而非环境变量、`SSH_AUTH_SOCK` 继承坑、编程调用 / 后台子会话的关键 flag）、provider 接入实测（MiniMax `minimax-cn` 的 base_url 坑、Gemini AI Studio OpenAI 兼容端点与 `AQ.` 前缀 key、`hermes auth` 重置速查）、以及自成一套的 skill 体系（`builtin`/`hub`/`local` 三种来源、`install`/`uninstall` 装前安全扫描 verdict、其余 `hermes skills` 子命令面、`external_dirs` 只读挂外部目录、无 walk-up 发现下按项目激活的近似解、跨 backend 的 symlink 处理差异、`--skills` 预加载与渐进式披露）。整份从 harness 视角写，源码引用锚定 `nousresearch/hermes-agent`。
- [Kimi Code CLI（Moonshot 官方编码 agent：runtime / 鉴权 / 额度 / 审批模式）](references/kimi.md)：MIT 开源 `MoonshotAI/kimi-code`（Node SEA 单文件、TUI 建在 pi-tui 上）。`~/.kimi-code` 数据目录与 `config.toml`（provider `managed:kimi-code` / models / services）；两套鉴权——Kimi Code 托管 **OAuth**（设备码 `auth.kimi.com`、token 存 `credentials/kimi-code.json`（0600、access ~15 分钟靠 refresh 续）、`oauth/kimi-code` 只是 proper-lockfile 并发锁**不是 token**、失效写 tombstone）vs **静态 API key** 直连 `api.kimi.com/coding/v1`（`type=kimi`、凭证优先级 `api_key 字段 > [providers.<n>.env] 子表 > 报错`、**不读 shell env**、`KIMI_MODEL_*` 家族除外；官方支持"分发 key"自建 provider）；两个 base_url 别混（`KIMI_CODE_BASE_URL`→coding vs `KIMI_BASE_URL`→moonshot.ai，Coding key 走 "Kimi Platform (API key)" 档会被拒）；**额度 / 余额用 key 也能查**——`GET /coding/v1/usages`（认 `METHOD_API_KEY`，字段 `usage`/`limits`/`parallel`/`boosterWallet`；`/meta`、`/usage` 单数是 404 坑），但 **TUI 余额面板走 `ensureFresh` 的 OAuth token 且只认 `managed:` provider，静态 key 进不去面板**。审批模式：YOLO 自动批常规调用但敏感文件 / Plan 退出 / 提问仍停，Auto 全无人值守（含敏感文件、Plan 退出自动批、不提问）。源码锚定 tag `@0.27.0`（commit `5cc1949`）、标 🔬 为本机实测。

## Claude Code / Codex 横向对照

SDK 语言覆盖与官方文档已记于上面的 SDK 横向对照。Claude / Codex 的 runtime / harness 行为先粗粒度记在那份对照里；如果后续把进程模型、扩展 / 插件点、会话存储、工具注入、取消、导出 / 调试流程写成体量，再单独拆 reference 文件。

- **Claude Code**：与 Copilot 一样闭源、minified 分发，行为靠逆向；会话存档在 `~/.claude/projects/*.jsonl`。
- **Codex**：`openai/codex` 真开源（Apache-2.0），优先引官方源码与发布文档，而非本地逆向；会话存档在 `~/.codex/sessions/`。
- 三家原生 worktree / 并行隔离支持的详细对照见 [worktree.md](references/worktree.md)。

## 边界

一般的本地软件运维仍归 `software` skill。本 skill 只管 coding agent 的 runtime / harness 内部机制，以及跨厂商 SDK / 接入形态的对照。

- **安装 / 分发的划分**：通用的"包管理器 / npm 壳包 + 平台二进制"打包模式属包管理器话题，在 `software` 的 [package-managers.md 第八节](../software/references/package-managers.md)；**三家 coding agent 具体怎么打包 / 安装 / 用什么工具链编**（Codex / Claude / Copilot 普查）在本 skill 的 [install.md](references/install.md)。
- **Hermes 的归属**：Hermes 是 coding agent runtime，它的常驻服务 / terminal backend / provider 接入 / skill 体系虽然看着像"本地软件运维"，但整体归本 skill（见上 References 的 hermes.md）；`software` 不再保留任何 Hermes 内容。
