# Coding Agent 程序化接入

要用代码驱动 coding agent，先分清接入的是**模型 API**，还是已经包含规划、工具调用、文件编辑、
shell、权限与会话循环的 **agent runtime**（agent 运行时）。这不是语言覆盖问题：类型选错后，
即使 SDK 支持再多语言，也仍要自己补齐缺失的 harness。

接入前先确定由谁持有运行时、要用哪种传输，以及需要哪些会话能力。Copilot、Claude Code、Codex 用于对照官方 Agent SDK，OpenCode、Pi 和 Paseo 展示其他接入形态。实际模型由运行时的 provider、配置默认值或本次显式请求决定。横向对照基线为 **2026-07-14**，Codex SDK 运行入口与 MCP server 迁移补核于 **2026-11-11**。非交互适配和外部执行器的版本证据见各节。

## <a id="integration-layers"></a>接入层级

### <a id="runtime-layers"></a>模型 API、编排框架与 agent runtime

| 层 | 接到的对象 | 已提供 | 仍需调用方负责 |
|---|---|---|---|
| **API SDK** | 模型的 HTTP API | 鉴权、请求类型、流式 token、重试等客户端能力 | 规划循环、工具、文件系统、shell、权限、会话与 sandbox |
| **编排框架** | 自定义 agent workflow | 状态机、handoff、guardrail、工具注册等编排原语 | coding-agent 工具集与具体 runtime；编排框架本身不等于某个 coding-agent CLI（具体产品见下方[相邻概念表](#adjacent-concepts)） |
| **agent SDK** | 完整 coding-agent runtime | 多轮工具循环、文件与命令执行、结构化事件、会话控制 | runtime 生命周期、权限策略、隔离、持久化与产品 UI |
| **托管 cloud agent API** | 厂商托管的远程任务 | 远程环境、branch / PR 级自动化 | 本机工作区、细粒度 tool event、本地 shell 控制 |
| **扩展或工具协议** | 已存在宿主的扩展点 | 给宿主增加工具、命令、面板或外部服务 | 从外部拥有并驱动整个 agent runtime；MCP 属于工具协议，不是 agent SDK |

Agent SDK 不是“API SDK 再加几个工具函数”。它绑定的是一套具体 harness：模型之外还有 loop、
工具实现、权限模型、上下文管理和会话存储。

### <a id="adjacent-concepts"></a>相邻但不是本地 agent runtime 的东西

上表是分层视角；下面把最常被误当成“本地 agent SDK”的具体产品点名，标清各自适合与不适合，选型时对号入座。

| 名称 | 分类 | 适合 | 不适合 |
|---|---|---|---|
| OpenAI / Anthropic 官方 API SDK | API SDK（裸 HTTP client） | 完全自写工具、loop、history、session、权限与 sandbox | 直接替代 `copilot -p` / Claude Code / Codex CLI |
| OpenAI Agents SDK / LangGraph / LangChain / Vercel AI SDK | 编排框架（orchestration SDK） | 自定义工具函数、状态机、handoff / guardrail | 需要现成 coding-agent 文件编辑 + shell runtime 时仍要另补 harness 与 toolset |
| GitHub Copilot Cloud Agent API | 托管 cloud agent API | 让 GitHub 托管环境接 issue / prompt 后自动改 branch / PR | 本地 daemon 细粒度接管 tool event、改本机 checkout、跑本机 shell |
| Copilot Extensions / MCP | 扩展 / 工具协议 | 让 Copilot 或别的 agent 调用你的服务 / 工具 | 从你的 daemon 内部驱动一个 coding-agent runtime |

### <a id="runtime-ownership"></a>运行时所有权

| 形态 | 谁拥有进程与会话 | 优点 | 主要代价 |
|---|---|---|---|
| **一次性 CLI 子进程** | 调用方为每次任务 spawn CLI，结束后回收 | 接入最快，直接复用现成 CLI | 冷启动；结构化 streaming、取消和多会话编排较弱 |
| **SDK client / app-server** | 调用方长期持有 runtime client 与 session | 能订阅事件、恢复会话、切模型、取消 turn、管理多 session | 协议兼容、鉴权、能力隔离和进程清理由调用方承担 |
| **扩展宿主** | 前台应用或 CLI 宿主拥有 runtime；扩展加入已有会话 | UI、生命周期和权限模型由宿主提供 | 扩展不能假定自己拥有整个进程，API 面受宿主注入能力限制 |

一次性 CLI 适合脚本和低频自动化；常驻 daemon / orchestrator 通常需要 SDK client、
app-server 或 ACP 这类可持续交互入口。扩展入口则适合“功能长在当前宿主里”，而不是另起一个 agent。

### <a id="transport-protocols"></a>传输与协议

运行时所有权与 wire protocol（线协议）是两个维度，不能把“SDK client”“扩展宿主”
与“JSON-RPC”“HTTP”并列成互斥方案。

| 传输 / 协议 | 典型形态 | 特点 |
|---|---|---|
| **stdio + JSONL** | Codex TypeScript SDK 的 exec 入口、Pi RPC | 按行交换消息；Codex exec 输出运行事件，会话续接通过 thread ID 交给后续调用 |
| **stdio / TCP + JSON-RPC** | Codex Python SDK 的 app-server 入口、Copilot SDK runtime connection | 一条双向连接承载请求、通知、事件和取消；JSONL 可作为消息分帧方式，schema 与版本协商另行核对 |
| **ACP** | `copilot --acp`、通用 ACP agent | 定义 client ↔ agent 的会话、prompt、权限和更新语义；通常仍需选定 stdio 等底层传输 |
| **HTTP + SSE / WebSocket / webhook** | OpenCode helper server、远程 daemon | 易部署和横向扩展；取消、背压、双向权限交互通常要额外设计 |

HTTP 适合粗粒度服务边界；进程内扩展 ABI 或紧密的双向 agent 控制通常更适合长连接协议。

### <a id="selection-guide"></a>选择依据

| 需求 | 优先选择 |
|---|---|
| 低频单次任务，能接受冷启动 | 一次性 CLI 子进程 |
| 需要 tool / file / shell 事件、取消、恢复、模型切换 | agent SDK、app-server 或 ACP |
| 给用户当前正在使用的 CLI / IDE 会话增加能力 | extension-host 入口 |
| 只需文本或结构化模型输出，不允许碰文件和 shell | API SDK |
| 把自有能力暴露给任意外部 agent | MCP / tool server |
| 让 GitHub 托管环境围绕 issue / branch / PR 执行任务 | cloud agent API |

协议选择随后再做：同一个 SDK client 可以经 stdio、TCP 或 URI 连接；同一个 stdio 子进程也可以
说 JSONL、JSON-RPC 或 ACP。

## <a id="official-sdks"></a>官方 SDK 对照

### <a id="agent-sdk-matrix"></a>Agent SDK 的语言、开放度与运行时关系

| Agent SDK | 语言覆盖 | 运行时关系 | 开放度 |
|---|---|---|---|
| **GitHub Copilot SDK** | TypeScript、Python、Go、.NET、Java、Rust | 六种 SDK 控制 “the same engine behind Copilot CLI”；Node / Python / .NET 默认带 runtime，Go / Java / Rust 默认从 PATH 找 CLI | SDK 仓库 MIT；Copilot CLI engine 不在该开源仓库中 |
| **Claude Agent SDK** | TypeScript、Python | SDK 驱动 Claude Code runtime | Python SDK 源码 MIT；TypeScript SDK 为 All Rights Reserved；Claude Code runtime 闭源；两者使用受 Anthropic Commercial Terms 约束 |
| **OpenAI Codex SDK** | TypeScript、Python | TypeScript SDK 启动 `codex exec --experimental-json`；Python SDK 启动专用 app-server 并经 stdio 交换 JSON-RPC，发布包依赖配套 CLI binary | CLI、SDK 与 Rust runtime 同仓，整仓 Apache-2.0 |

> Codex `0.167.1` 的运行入口分别见 [TypeScript exec](https://github.com/openai/codex/blob/rust-v0.167.1/sdk/typescript/src/exec.ts#L94-L106)与 [Python app-server](https://github.com/openai/codex/blob/rust-v0.167.1/sdk/python/src/openai_codex/client.py#L242-L281)。Python 最小调用、登录态复用与多账号 `CODEX_HOME` 选择统一维护在 [Codex 程序化调用](codex.md#programmatic-control)；旧官方 MCP server 的状态见 [迁移说明](codex.md#codex-mcp-migration)。

包名：Copilot 为 `@github/copilot-sdk`、`github-copilot-sdk`、`GitHub.Copilot.SDK`、
`github.com/github/copilot-sdk/go`、`com.github:copilot-sdk-java`、`github-copilot-sdk` crate；
Claude 为 `@anthropic-ai/claude-agent-sdk`、`claude-agent-sdk`；Codex 为
`@openai/codex-sdk`、`openai-codex`；Codex 仓库的 `sdk/` 同时包含 `typescript`、`python`
与负责分发 CLI binary 的 `python-runtime`。

> 来源：Copilot SDK [v1.0.6 README](https://github.com/github/copilot-sdk/blob/7e2900416b1ac835785fa26e0eb5f634ff24adf9/README.md#L16-L40) 与 [MIT LICENSE](https://github.com/github/copilot-sdk/blob/7e2900416b1ac835785fa26e0eb5f634ff24adf9/LICENSE)；Claude [Python LICENSE](https://github.com/anthropics/claude-agent-sdk-python/blob/528265fa09da954f0a0da1bf31e16db32b510138/LICENSE#L1) 与 [TypeScript LICENSE](https://github.com/anthropics/claude-agent-sdk-typescript/blob/79b6350e13cf24af94a8d2e696a0883fd8cc55fe/LICENSE.md#L1)；Codex [SDK README](https://github.com/openai/codex/blob/bc8222b8d9e44377a3d7c7b7970e32e7c29ec34f/sdk/typescript/README.md#L1-L40)、[Python 包声明](https://github.com/openai/codex/blob/bc8222b8d9e44377a3d7c7b7970e32e7c29ec34f/sdk/python/pyproject.toml#L1-L20) 与 [Apache-2.0 LICENSE](https://github.com/openai/codex/blob/bc8222b8d9e44377a3d7c7b7970e32e7c29ec34f/LICENSE#L1).

### <a id="agent-sdk-apis"></a>Agent SDK 的核心 API 与事件模型

| SDK | 最小可用 API | Agent 能力证据 |
|---|---|---|
| **Copilot** | `CopilotClient.start/createSession/resumeSession`；`session.send()`、`sendAndWait()`、`on()`、`abort()`、`disconnect()`、`setModel()` | `assistant.turn_start/end`、`tool.execution_start/complete`、`session.idle/task_complete` 等事件；内置 coding tools、permission handler 与可恢复 session |
| **Claude** | Python `query()`；交互式 `ClaudeSDKClient.connect/query/receive_response/interrupt`；TypeScript `query({ prompt, options })` | `ClaudeAgentOptions` 覆盖工具、权限、`cwd`、`max_turns`、MCP、hooks、agents、skills、plugins、`can_use_tool` 与 `session_store`；`ResultMessage.session_id` 可恢复会话 |
| **Codex** | TypeScript `startThread().run()` / `runStreamed()` / `resumeThread()`；Python `thread_start()` / `thread_resume()` / `thread.run()` / `thread.turn().stream()` | TypeScript 的 `ThreadEvent` / `ThreadItem` 描述生命周期、工具和消息；Python 消费 app-server 通知，由 `TurnHandle` 提供流式事件、steer / interrupt 和最终结果收集 |

> Python `0.167.1` 的 [turn handle 与事件收集](https://github.com/openai/codex/blob/rust-v0.167.1/sdk/python/src/openai_codex/api.py#L810-L843)与 TypeScript JSONL 事件分别理解；运行任务时保留各 SDK 自身的事件类型。

> 来源：Copilot [Node quick start](https://github.com/github/copilot-sdk/blob/7e2900416b1ac835785fa26e0eb5f634ff24adf9/nodejs/README.md#L30-L61)、[session API](https://github.com/github/copilot-sdk/blob/7e2900416b1ac835785fa26e0eb5f634ff24adf9/nodejs/src/session.ts#L254-L337) 与 [session event types](https://github.com/github/copilot-sdk/blob/7e2900416b1ac835785fa26e0eb5f634ff24adf9/nodejs/src/generated/session-events.ts#L3054-L3081)；Claude [Python README](https://github.com/anthropics/claude-agent-sdk-python/blob/528265fa09da954f0a0da1bf31e16db32b510138/README.md#L33-L132) 与 [`ClaudeAgentOptions`](https://github.com/anthropics/claude-agent-sdk-python/blob/528265fa09da954f0a0da1bf31e16db32b510138/src/claude_agent_sdk/types.py#L1726-L2067)；Codex [`ThreadEvent`](https://github.com/openai/codex/blob/bc8222b8d9e44377a3d7c7b7970e32e7c29ec34f/sdk/typescript/src/events.ts#L68-L82)、[`ThreadItem`](https://github.com/openai/codex/blob/bc8222b8d9e44377a3d7c7b7970e32e7c29ec34f/sdk/typescript/src/items.ts#L97-L128) 与 [Python SDK README](https://github.com/openai/codex/blob/bc8222b8d9e44377a3d7c7b7970e32e7c29ec34f/sdk/python/README.md).

会话持久化不是三家共享的统一接口：

- Copilot runtime 的 `baseDirectory` 默认是 `~/.copilot`，包含 session state、配置等；精确磁盘布局属于 runtime 实现细节。
- Claude 从 `ResultMessage.session_id` 恢复会话；底层 CLI 使用本地 JSONL，Python SDK 另有 `session_store` 协议可接外部存储。
- Codex 的持久化线程使用其配置根下的会话存储，默认 `~/.codex/sessions`，通过 `resumeThread(id)` / `thread_resume(id)` 恢复；Python 的 `ephemeral=True` 用于内存线程。多账号目录、历史共享与 provider 的条件见 [Codex 登录态复用](codex.md#sdk-auth)。

> 来源：Copilot [`baseDirectory`](https://github.com/github/copilot-sdk/blob/7e2900416b1ac835785fa26e0eb5f634ff24adf9/nodejs/src/types.ts#L214-L247)；Codex [thread persistence](https://github.com/openai/codex/blob/bc8222b8d9e44377a3d7c7b7970e32e7c29ec34f/sdk/typescript/README.md#L100-L104)；Claude `session_store` 见上方类型定义。

### <a id="api-sdk-matrix"></a>API SDK 的语言覆盖

API SDK 只负责模型请求，不携带 coding-agent runtime。官方语言覆盖比 agent SDK 更广：

| 厂商 | 官方包与固定源码快照 |
|---|---|
| **OpenAI** | Node [`openai`](https://github.com/openai/openai-node/tree/1cdc0196b4341ee641ec6839e08744b2771250e4)、Python [`openai`](https://github.com/openai/openai-python/tree/v2.45.0)、Go [`github.com/openai/openai-go/v3`](https://github.com/openai/openai-go/tree/v3.42.0)、Java [`com.openai:openai-java`](https://github.com/openai/openai-java/tree/c28e73d4390d51626add76ff000984a4d46d6b0e)、.NET [`OpenAI`](https://github.com/openai/openai-dotnet/tree/319d66db3281309b2af9471d838865a0ee35a0a6) |
| **Anthropic** | Node [`@anthropic-ai/sdk`](https://github.com/anthropics/anthropic-sdk-typescript/tree/9e46760688a2af71b50581a301b2819d29d28c66)、Python [`anthropic`](https://github.com/anthropics/anthropic-sdk-python/tree/d2f6543ee7995adcae74666a5d37b3d9743debfe)、Go [`anthropic-sdk-go`](https://github.com/anthropics/anthropic-sdk-go/tree/v1.57.0)、Java [`anthropic-java`](https://github.com/anthropics/anthropic-sdk-java/tree/db3e617c03e4e697a0508a352047aca1ef7da5f5)、.NET [`Anthropic`](https://github.com/anthropics/anthropic-sdk-csharp/tree/15116485ea585908a6e32aeba3a36497dbbb29a6)、Ruby [`anthropic`](https://github.com/anthropics/anthropic-sdk-ruby/tree/820c9c0d588d92b158430688175cf6027a5d5bc6)、PHP [`anthropic-ai/sdk`](https://github.com/anthropics/anthropic-sdk-php/tree/a731fd19d9a11e865cdad6363e8545ead1f0658d) |

社区封装另算。例如 [`picatz/openai` 的 `codex` 包](https://github.com/picatz/openai/tree/02ace0a229c75a724ede668ab405ae71405e406d/codex)
是 Codex CLI 的非官方 Go wrapper；采用前要单独判断维护状态、许可证与 API 稳定性。

## <a id="copilot-sdk"></a>Copilot SDK

以下以公开稳定版 **v1.0.6** 为基线；npm `latest` 在 2026-07-14 也是 `1.0.6`，不再沿用旧文的 `1.0.4`。

> 来源：[v1.0.6 release](https://github.com/github/copilot-sdk/releases/tag/v1.0.6) 与 [`@github/copilot-sdk@1.0.6` manifest](https://registry.npmjs.org/@github/copilot-sdk/1.0.6).

### <a id="copilot-entrypoints"></a>客户端入口与扩展入口

`@github/copilot-sdk` 和 `@github/copilot-sdk/extension` 是两套不同的所有权模型：

| 入口 | 主 API | 用途 | 拥有关系 |
|---|---|---|---|
| `@github/copilot-sdk` | `CopilotClient`、`RuntimeConnection`、`CopilotSession` | daemon / orchestrator 的程序化控制 | 你的进程拥有或连上一个 runtime，再创建 / 发送 / 恢复会话 |
| `@github/copilot-sdk/extension` | `joinSession()` | 写 Copilot CLI 扩展 | 前台那个 Copilot CLI 会话拥有宿主进程，并注入 extension SDK |

根包不是“只能写扩展”的 API。`joinSession()` 会读取宿主注入的 `SESSION_ID`，通过 parent-process
连接加入当前会话；扩展进程不负责 spawn runtime。

```ts
import { CopilotClient, approveAll } from "@github/copilot-sdk";

const client = new CopilotClient();
await client.start();
const session = await client.createSession({ onPermissionRequest: approveAll });
const answer = await session.sendAndWait("检查当前仓库并解释失败的测试");
console.log(answer?.data.content);
await session.disconnect();
await client.stop();
```

> 来源：根包 [quick start](https://github.com/github/copilot-sdk/blob/7e2900416b1ac835785fa26e0eb5f634ff24adf9/nodejs/README.md#L30-L61)；扩展入口 [`joinSession()`](https://github.com/github/copilot-sdk/blob/7e2900416b1ac835785fa26e0eb5f634ff24adf9/nodejs/src/extension.ts#L42-L60).

### <a id="runtime-connections"></a>`RuntimeConnection` 的连接方式

```ts
RuntimeConnection.forStdio({ path?, args? })
RuntimeConnection.forTcp({ port?, connectionToken?, path?, args? })
RuntimeConnection.forUri(url, { connectionToken? })
```

| 工厂 | 进程所有权 | 连接语义 |
|---|---|---|
| `forStdio` | SDK spawn runtime 子进程 | 通过 stdin/stdout 通信；未指定 `path` 时用 bundled runtime |
| `forTcp` | SDK spawn runtime 子进程 | runtime 监听 TCP；端口与 token 可自动生成 |
| `forUri` | 外部系统拥有已运行 runtime | SDK 只连接 URL，不 spawn 进程 |

稳定版 v1.0.6 的公开 union 是上述三种。若采用 preview / unstable 版本，应重新检查是否出现
`forInProcess()` 等实验入口，不要把预览 API 写成稳定契约。

> 来源：[`RuntimeConnection` 类型与工厂](https://github.com/github/copilot-sdk/blob/7e2900416b1ac835785fa26e0eb5f634ff24adf9/nodejs/src/types.ts#L93-L186).

### <a id="session-control"></a>会话生命周期与取消

核心控制面：

```ts
session.send(promptOrOptions)
session.sendAndWait(promptOrOptions, timeout?)
session.on(handler)
session.setModel(model, options?)
session.abort()
session.disconnect()
```

`sendAndWait()` 默认等待 60 秒；timeout 只结束调用方的等待，**不会**停止正在运行的 agent turn。
取消当前 turn 要调用 `abort()`。`disconnect()` 释放内存中的 handler，但保留磁盘会话，之后仍可
`resumeSession()`；若要永久删除会话数据，应使用 client 的删除 API。

> 来源：[`sendAndWait()` timeout 语义](https://github.com/github/copilot-sdk/blob/7e2900416b1ac835785fa26e0eb5f634ff24adf9/nodejs/src/session.ts#L254-L337) 与 [`disconnect()` / `abort()` / `setModel()`](https://github.com/github/copilot-sdk/blob/7e2900416b1ac835785fa26e0eb5f634ff24adf9/nodejs/src/session.ts#L1280-L1365).

### <a id="copilot-protocol"></a>协议与运行时分发

| 事实 | 边界 |
|---|---|
| `SDK_PROTOCOL_VERSION = 3` | 公开仓库中的协议版本常量 |
| Node SDK 依赖 `vscode-jsonrpc@^8.2.1` 与 `@github/copilot@^1.0.69` | SDK client 经 JSON-RPC 控制 Copilot CLI runtime |
| Node / Python / .NET 默认带 runtime | 无需另装 `copilot` |
| Go / Java / Rust 默认从 PATH 找 runtime | Go / Rust 另有应用级 bundling 机制 |
| `--acp`、`--extension-sdk-path` | 本地 Copilot CLI `1.0.71-0 --help` 可见，属于公开 CLI surface |
| `--server`、`--ui-server`、`--managed-server` | 曾在 Copilot CLI `1.0.66-1` bundle 中观察到，但不在当前公开 help；只当内部实现细节 |

多用户服务不要沿用 CLI 式 ambient defaults。v1.0.6 的公开类型明确提供
`CopilotClient({ mode: "empty" })`，要求应用显式给出 session filesystem / base directory 与
可用工具集合；这才是服务端 deny-by-default（默认拒绝）配置的起点。

> 来源：[`SDK_PROTOCOL_VERSION`](https://github.com/github/copilot-sdk/blob/7e2900416b1ac835785fa26e0eb5f634ff24adf9/nodejs/src/sdkProtocolVersion.ts#L5-L18)、[v1.0.6 npm manifest](https://registry.npmjs.org/@github/copilot-sdk/1.0.6)、[runtime bundling](https://github.com/github/copilot-sdk/blob/7e2900416b1ac835785fa26e0eb5f634ff24adf9/README.md#L39-L40) 与 [`mode: "empty"`](https://github.com/github/copilot-sdk/blob/7e2900416b1ac835785fa26e0eb5f634ff24adf9/nodejs/src/types.ts#L205-L233).

### <a id="copilot-model-catalog"></a>模型目录与 CLI 入口

程序化查询模型目录用 SDK 的 `client.models.list()`，保留返回的模型 ID、可用性及采样时间。CLI 的 `--model` 接受模型名或 `auto`。`1.0.114 --help` 核对了 `-p/--prompt`、`--output-format json` 和 `--resume`。CLI 的 resume 还可接受 ID 前缀或会话名，自动恢复时传入完整原生 ID 并回读绑定。

### <a id="copilot-files"></a>源码、类型声明与缓存位置

| 位置 | 内容 | 稳定性 |
|---|---|---|
| [`github/copilot-sdk`](https://github.com/github/copilot-sdk/tree/7e2900416b1ac835785fa26e0eb5f634ff24adf9) | 公开 SDK 源码与文档 | 首选依据 |
| `node_modules/@github/copilot-sdk/dist/index.d.ts` | Node 根包类型声明 | 随安装版本变化 |
| `~/.cache/github-copilot-sdk/cli/<version>/copilot` | Python SDK 在 Linux 的 CLI binary cache | 公开源码可核；macOS / Windows 路径不同 |
| `~/.cache/copilot/pkg/<platform>/<version>/copilot-sdk/*.d.ts` | 某些 Copilot CLI SEA 构建解包给 extension 的声明 | 本地实现 cache，不是 SDK 安装位置，也不是公开稳定契约 |

> 来源：Python SDK 的跨平台 cache 规则见 [`_cli_download.py`](https://github.com/github/copilot-sdk/blob/7e2900416b1ac835785fa26e0eb5f634ff24adf9/python/copilot/_cli_download.py#L1-L9).

## <a id="headless-cli"></a>非交互 CLI 接入

每次调用保留独立 invocation，关联原生 session/turn、进程、完整日志和退出结果。双向输入与持久控制按[接入层级](#integration-layers)选择 SDK 或原生协议。

### <a id="capability-checks"></a>能力声明与启动预检

按产品、接口模式与版本声明启动、观察、精确恢复、同回合追加、后续排队与取消。分别记录能力声明、参数构造或假 CLI 回归、实际二进制预检、端到端实机验收。启动前核对可执行文件、版本、配置、必需能力和实验开关。所选入口缺能力时，由调用者明确选择替代接口。

| 入口 | 原生输入、身份与恢复 |
| --- | --- |
| Codex | [`exec --json` 与精确恢复](codex.md#exec-resume)，或 [app-server 原生控制](codex.md#native-session-control)。 |
| MiniMax Code | [`mcode exec` 与会话](mcode.md#exec-streaming)，[实验性同轮追加](mcode.md#live-steer)。 |
| Claude Code | `-p` 支持 stdin，`--output-format stream-json --verbose` 的 `system/init` 提供 `session_id`，用 `--resume <id>` 精确指定。单轮 print 与 `--input-format stream-json` 的双向入口分别验收。 |
| Kimi Code | [`--prompt`、`--session` 与输出信号](kimi.md#headless-cli)。 |
| MiMo | Swarm 的 `run` 样例以受控 cwd 和 argv 启动，用 `--session` 组装恢复请求。已有构造和读取测试，原生身份与恢复须另作部署验证。 |
| Antigravity | [`--print`、`--conversation` 与流式 JSON](antigravity.md#headless-cli)。 |
| Pi | [JSON print、原生终态与恢复](pi.md#json-print)。 |
| OpenCode | `2.3.2` 的 `opencode run --format json --session <id>` 支持 JSON 输出。help 明示目标缺失时可能新建会话，严格恢复须先核实目标。 |

目录查询与实际模型调用分别验证。优先使用原生 ID 或 alias，例如 [Codex 分页目录](codex.md#server-binding)、[Kimi 配置目录](kimi.md#headless-cli)、Claude 双向控制初始化的 `models`、[Copilot SDK 目录](#copilot-model-catalog)或 Pi `--list-models`。记录来源是服务端、本机配置还是缓存，同时保存采样时间、默认标记和缺失字段。备用入口分别核对模型、effort、上下文、权限和输出控制，参数缺映射时报告失败。外层规则经原生 system/developer 通道传入，入口缺少所需通道时明确失败。

> Swarm 样例对各入口有参数构造和读取测试。2026-11-19 实机以 `--help`、认证状态和目录读取核对各产品的可见入口，Claude Code `2.1.327` 核对了 print、resume 与双向事件参数，未新建模型回合。产品章节各自记录历史完整回合的版本。

### <a id="run-evidence"></a>输入、终态与恢复证据

私有运行记录保存实际 argv、cwd、二进制身份、配置版本、输入摘要及字节数、配置模型/effort、原生可核实模型和会话 ID。用受控 stdin 或 argv 传入。argv 即便绕过 shell，仍可能被进程查看工具读到并受系统长度限制。输入快照及 stdout/stderr 完整日志只保存在运行者可读的目录，对外仅给必要元数据。模型自述作为正文保存，身份依据来自结构化原生字段。

逐个解析完整协议帧，保留退出码、watchdog、取消回执和最后一轮的终态。收到新回合起始就清除旧终态，预览缺终态时查完整日志。原生自动重试后按最后一轮判定。具体事件见 [Codex JSON 终态](codex.md#exec-json-terminal)与 [Pi JSON print](pi.md#json-print)。

恢复使用精确原生 ID，并核对 cwd、服务身份与账号目录、实际权限、模型和输出约束。先查可能存活的子进程与外部状态，新 invocation 关联原调用和回读身份。若目标缺失时入口可能静默创建会话，先只读验证目标存在与严格恢复语义，再放行有副作用的 prompt。早取消或输出截断可能缺原生 ID，保留身份未知状态，见 [Kimi 的退出提示](kimi.md#headless-cli)。

### <a id="profiles-and-quota"></a>账号目录与只读额度

登记实际存在的规范化 profile 根目录，通过受控环境选择原生方案，例如 `CODEX_HOME`、`MINIMAX_DATA_DIR`、`KIMI_CODE_HOME`、`MIMOCODE_HOME`、`CLAUDE_CONFIG_DIR`。同时核对外部 key、Keychain、环境覆盖、代理与原生服务身份。目录绑定和认证绑定分别验证。私有 manifest 维护完整映射，对外只显示脱敏 profile、隔离范围及检查结果。复用已有凭据生命周期。共享可变会话存储时额外核对[运行时所有权](mcode.md#shared-runtime-ownership)。

额度限定为所选账号在受信第一方 API 上的只读查询。认证输入来自限长常规文件，HTTP 设超时、响应上限和重定向边界。快照留采样时刻、缓存状态、窗口和重置时间，区分不支持、认证失效、超时、过期、异常响应和缺窗口。模型支持、真实调用、使用量与账号并发各自取证。额度重置券由用户另行授权。

### <a id="quota-fallback"></a>限流与备用入口

从完整事件流中的原生错误、重试事件或明确传输错误识别 429。模型和工具输出引用的错误文字、截断预览只作为正文。需要接管 CLI 内部重试时，对本次调用按[进程归属](#workspace-ownership)有界停止，再核对限流、超时、取消和账号状态。

按已核验的服务及账号键更新共享退避期限，同时区分单次调用 429 与账号停止准入。查询失败保留未知，并绕过失败缓存重查。短窗重置后实际复查，长窗耗尽按政策停派，两窗仍有剩余时有界退避。健康账号可继续运行，等待能被停止请求唤醒。

备用池使用已授权的有序候选，每项明确账号、适配器、模型与权限，跳过证实不可用者并保存选择理由。工作区内串行派发。先明确是用兼容接口接续原生会话，还是从持久工作区状态新开会话。缺可信会话 ID 或绑定改变时停下核对。轮换时同步预算、检查点和在途状态，授权的轮换规则只用于后续派发。任务调度和跨账号容量分配归 `superagent` skill。

## <a id="external-runner"></a>外部执行器

监督进程管理一次运行，worker 管理一个工作区的循环，原生会话管理对话和回合。任务认领、阶段和验收由业务流程定义。

### <a id="run-manifest"></a>预检与运行快照

固定工作区、入口、子流程、账号、模型、权限、必需能力、预算、停止方式和写入范围。规范化路径并检查缺失、重复、嵌套和共享 Git common-dir，按每种传输做[能力预检](#capability-checks)。认领、写入和发布以该次授权为准。

可执行子流程用异步函数表达循环与并行时，先解析静态子流程路径、检查循环依赖并审阅可执行块，所执行的代码持有解释器的 OS 权限。将入口、依赖图、源码和辅助脚本、驱动、参数、权限、解释器及摘要冻结到业务工作区外的新建私有运行目录。长期后台所需文件和依赖须在监督进程退出后仍可用，新源文件通过新运行或明确迁移生效。

### <a id="workspace-ownership"></a>工作区、进程与账号并发

每个工作区仅一个活跃写者。用共享锁域按固定顺序获取工作区与 Git common-dir 锁，持锁重读记录，后台跨客户端持续执行时保留持久占用。旧快照和第三方客户端可能在锁域之外，交接时另查实际写者。最后一个使用者释放共享 Git 锁。检查 Git 锁、未完成的 rebase/merge、分支和未推送内容。

以明确的 argv、cwd 与独立进程组启动受控 CLI，记录 PID、组和进程启动标识，区分僵尸、PID 复用和无法读取 `/proc`。取消只向确认为本次调用的组发 TERM，等待后按需 KILL，并检查 CLI 遗留的工具与后代进程。共享 daemon 使用其原生精确中断接口。

独立工作区可异步推进，对出错工作区单独保留结果。按账号计算原生子会话及顶层调用的并发。需要限制创建子会话时，在有效工具清单和子任务事件中验收范围。Codex 的实际线程写锁与接管见[会话恢复](codex.md#account-writer)。

### <a id="worker-loop"></a>任务循环、预算与验收

循环按现场检查、任务认领、执行或续接、结果读取、工作区交回推进。新任务从获准基线进入，已有任务先保全工作树并沿用原分支、任务身份、反馈和检查点。认领须由业务端原子处理，回执不明先对账。业务读取失败时退避，只重试读取，确认现状后再派发。

按稳定任务身份加锁累计轮次、墙钟时间、运行总预算和连续基础设施失败，单次调用另设 watchdog。明确派发、失败、取消、限流与预检如何计数。换账号、工作区和 run 时沿用预算，导入历史按派发 ID 去重。预算耗尽在允许的边界保存完成度、受测版本、检查点和余项。

分别验证回合终态、原生 goal、进程退出、PR Ready、独立审查、检查及合并。审查绑定仓库、PR 与确切 head，同一 head 仍可能出现新反馈。冲突评审保留原文、身份、条件和具体主张，交独立复核或按政策阻塞。结构化结果校验身份、重复键与结论。通过原生终态事件恢复格式失败的评审时，验明完整日志、执行身份、事件顺序及明确失败原因，并保留原回执。

### <a id="run-recovery"></a>停止、接管与故障恢复

原子持久化 run、worker、进程、会话与控制请求，追加事件记录状态变化。写入前记录请求 ID 和未决状态，回执核验后再更新；结果不明时由获准操作者据持久状态对账。区分已受理、已消费、已完成、已停止和未知。优雅停止先停止新派发，在已验证支持的入口按授权追加当前轮收口指令；立即停止按实际归属取消并收齐回执。两种方式都保留实际工作树和日志。 [Codex 原生写入恢复](codex.md#mutation-recovery)

接管前比对权威计划和冻结 manifest、工作区、身份、权限、真实进程及停止请求。单独更换监视器时核对 runner 与子进程身份持续存在。真正接管时先确认旧 runner 退出且工作区可交回，然后精确恢复已验证的原生会话，新增指令时另建 invocation。遇到锁或进程不明、配置漂移或权限变化，保留现场。

外部 API、网络和解析故障先在原 job 环境对同一请求做小范围只读探针，分别核对超时、TLS、认证、状态码、UTF-8 和 JSON。保留私有、有界的原始字节、长度和哈希。恢复后单独试一个受影响 worker，验证读取及现场，再按原并发限制逐一恢复。若修复涉及新快照，核对实际 run 目录。健康 worker 继续工作。

### <a id="worker-patrol"></a>运行巡检与回执

巡检核对计划、实际 run、原生会话、完整事件、工具进程、工作区分支与 head，以及 PR 的真实 head 和检查状态。流式 `item.updated` 等有效事件计入最近活动。进程存活、模型活动与业务进度各自取证。匹配 PR 时区分读取失败、无匹配、多候选与采证间发生变化。

定时投递用请求 ID 关联触发、入口受理或排队、实际消费、报告送达与应答。已有请求 pending 或结果不明时先查原请求。运行收口后逐一停止并核对关联调度。旁路监控、经授权收口及向用户汇报归 `superagent` skill。

## <a id="server-integration"></a>多用户服务化

SDK 已经解决“如何驱动一个 agent runtime”，但 Web 服务还要解决多用户、多标签页、长生命周期、
可恢复与隔离。下面是服务层模式，不是三家 SDK 共享的 API。

批量驱动多个独立工作区见[外部执行器](#external-runner)。重连 Codex 的持久会话见[服务端与线程绑定](codex.md#server-binding)。

### <a id="session-ownership"></a>会话与连接所有权

- **一个逻辑 session 只保留一个活跃 runtime session。** 多个 WebSocket / 标签页订阅同一对象，
  事件向 `Set<Connection>` fan-out；不要让每个标签页各自 `resumeSession()` 后重复注册 tool /
  permission handler。
- **并发创建缓存 Promise。** 用 `Map<sessionId, Promise<Session>>`，而不是等创建完成后才写入
  `Map<sessionId, Session>`；并发连接会共享同一个 in-flight 创建过程。
- **浏览器连接与 agent 生命周期分离。** 最后一个标签页断开后，是立即回收、进入 grace period，
  还是继续后台运行，应由 session policy 决定，不能把 socket 生命周期直接当成 turn 生命周期。

### <a id="state-lifecycle"></a>状态持久化与回收

- 在 turn 完成事件后把工作目录、provider-native session state 与产品侧 transcript 同步到独立
  filestore；连续事件用 debounce 合并，避免每个 token / tool event 都触发复制。
- 负载均衡接管时同时恢复工作目录和 provider handle。只保存聊天文本，不足以恢复文件改动、
  pending permission 与 runtime-native session。
- 给 session 配 idle GC，并在回收前持久化 transcript 与 workspace。超时值是产品策略，不是 SDK 常量。
- 存储接口按 provider 区分：Copilot 有 `sessionFs` / `baseDirectory`，Claude Python 有
  `session_store`，Codex 当前主要依赖 `~/.codex/sessions`。

### <a id="permission-isolation"></a>权限交互与租户隔离

- permission callback 可以实现成阻塞 RPC：按 request id 保存 pending Promise，经 WebSocket 发给前端，
  用户选择后 resolve。连接关闭、请求超时或 session 回收时必须 reject 对应 Promise，避免 agent
  永久等待。
- 服务端从最小能力开始。Copilot 使用 `mode: "empty"` + 明确 `availableTools`；需要替换内置工具时，
  `overridesBuiltInTool: true` 可以注册同名实现。
- 虚拟文件系统与用户态 shell（例如
  [`just-bash`](https://github.com/vercel-labs/just-bash/tree/6130334f0ed013771bbe39f32a249bdaf762c488)）
  能缩小可信应用的能力面，但**不等价于 OS / 容器 / VM 安全边界**。若 agent 可执行任意本机进程或面对
  对抗性租户，仍需进程、容器或虚拟机隔离。

> 来源：Copilot 的 [`mode: "empty"`](https://github.com/github/copilot-sdk/blob/7e2900416b1ac835785fa26e0eb5f634ff24adf9/nodejs/src/types.ts#L205-L233) 与 [built-in tool override](https://github.com/github/copilot-sdk/blob/7e2900416b1ac835785fa26e0eb5f634ff24adf9/nodejs/README.md#L461-L474).

### <a id="streaming-events"></a>流式输入与事件转发

- 优先用 SDK 原生的长期 session API。Claude `query()` 也接受 `AsyncIterable` prompt，可用持续输入流
  维持双向会话；这是一项 provider-specific 能力，不应假定所有 `query()` 都可这样使用。当 SDK 只给一次性
  流式 `query()` 时，可传一个永不结束的 async iterator 把它“骗”成长连接：用一个单槽 async 队列（有消费者
  在等就直接投递、否则缓冲一条），输入流永不说完、agent 循环就一直活着，每 `push()` 一条用户消息唤醒
  一轮，无需依赖 SDK 自带的 resume 机制。
- 对前端只转发产品需要的事件：user / assistant message、turn start / end、tool start / complete、
  permission、idle、error。原始 `session.error`、stack 与 tool output 可能泄露内部路径或凭据，
  应在服务边界脱敏。
- 给流式通道设计背压、断线重连和事件序号。只靠“不断推 WebSocket”会在慢客户端下积压内存，
  也无法判断补发边界。

> 来源：Claude Python `query()` 的 prompt 类型支持 `AsyncIterable`，见 [`query.py`](https://github.com/anthropics/claude-agent-sdk-python/blob/528265fa09da954f0a0da1bf31e16db32b510138/src/claude_agent_sdk/query.py).

## <a id="paseo"></a>Paseo 的 provider 适配层

Paseo `0.1.107`（源码快照
[`b4ab0d9`](https://github.com/getpaseo/paseo/tree/b4ab0d9db6e5668218e5aaa34f15ef3dd133e3ec)，
`AGPL-3.0-or-later`）的 README 主推 Claude Code、Codex、Copilot、OpenCode、Pi 五个 provider。
它是“统一产品接口覆盖异构 runtime”的案例，但不是“底层只有两种驱动”的案例。

> 来源：[README 的 provider 与 daemon 定位](https://github.com/getpaseo/paseo/blob/b4ab0d9db6e5668218e5aaa34f15ef3dd133e3ec/README.md#L42-L67) 与 [package license](https://github.com/getpaseo/paseo/blob/b4ab0d9db6e5668218e5aaa34f15ef3dd133e3ec/package.json#L1-L15).

### <a id="paseo-abstraction"></a>统一接口

旧文所说的“同一套 `AgentProvider` 抽象”不准确：`AgentProvider` 在源码里只是 `string` type。
真正统一 provider 的是 `AgentClient` + `AgentSession`：

```ts
interface AgentClient {
  createSession(...)
  resumeSession(...)
  fetchCatalog(...)
}

interface AgentSession {
  run(...)
  startTurn(...)
  subscribe(...)
  interrupt()
  close()
}
```

各 adapter 把原生 runtime 的事件、权限、模式、模型和持久化 handle 归一到这两个接口，再交给
`AgentManager`、WebSocket API、CLI 与 UI。当前 registry 还包含 Cursor、Pi-compatible OMP 和
custom ACP provider 路径；“五家”是 README 的主推产品面，不是类型系统上限。

> 来源：[`AgentProvider = string`](https://github.com/getpaseo/paseo/blob/b4ab0d9db6e5668218e5aaa34f15ef3dd133e3ec/packages/server/src/server/agent/agent-sdk-types.ts#L1-L10)、[`AgentSession`](https://github.com/getpaseo/paseo/blob/b4ab0d9db6e5668218e5aaa34f15ef3dd133e3ec/packages/server/src/server/agent/agent-sdk-types.ts#L612-L650)、[`AgentClient`](https://github.com/getpaseo/paseo/blob/b4ab0d9db6e5668218e5aaa34f15ef3dd133e3ec/packages/server/src/server/agent/agent-sdk-types.ts#L671-L699) 与 [provider registry](https://github.com/getpaseo/paseo/blob/b4ab0d9db6e5668218e5aaa34f15ef3dd133e3ec/packages/server/src/server/agent/provider-registry.ts#L114-L177).

### <a id="paseo-adapters"></a>Provider 连接方式

| Provider | Paseo adapter | 原生连接方式 |
|---|---|---|
| **Claude Code** | direct `AgentClient` | 调 `@anthropic-ai/claude-agent-sdk` 的 `query()`，并接管 Claude Code 子进程 spawn |
| **Codex** | direct `AgentClient` | spawn `codex app-server`，经 stdio 交换 JSON-RPC request / notification |
| **Copilot** | `ACPAgentClient` | spawn `copilot --acp`，通过 `@agentclientprotocol/sdk` 管 session、prompt、permission 与 update |
| **OpenCode** | direct `AgentClient` | spawn `opencode serve --port ...`，再用 `@opencode-ai/sdk/v2/client` 连接本地 HTTP server 与事件流 |
| **Pi** | direct `AgentClient` | spawn `pi --mode rpc`，stdin 写 JSONL request，stdout 逐行读 response / event |

因此，Paseo 的共同点是**归一化接口**，不是共同 wire protocol。Claude SDK、Codex app-server、
ACP、HTTP helper server、Pi JSONL RPC 都可以落到同一个 `AgentSession` surface。
ACP adapter 还会把原生 `stopReason` 归一为 Paseo 的 `turn_completed` / `turn_canceled` 事件，
例如 `end_turn`、`max_tokens` 与 `refusal` 都结束当前 turn。

> 来源：Claude [SDK query adapter](https://github.com/getpaseo/paseo/blob/b4ab0d9db6e5668218e5aaa34f15ef3dd133e3ec/packages/server/src/server/agent/providers/claude/query.ts#L1-L117)；Codex [app-server launch](https://github.com/getpaseo/paseo/blob/b4ab0d9db6e5668218e5aaa34f15ef3dd133e3ec/packages/server/src/server/agent/providers/codex-app-server-agent.ts#L6199-L6239) 与 [stdio JSON-RPC transport](https://github.com/getpaseo/paseo/blob/b4ab0d9db6e5668218e5aaa34f15ef3dd133e3ec/packages/server/src/server/agent/providers/codex/app-server-transport.ts#L218-L338)；Copilot [`defaultCommand`](https://github.com/getpaseo/paseo/blob/b4ab0d9db6e5668218e5aaa34f15ef3dd133e3ec/packages/server/src/server/agent/providers/copilot-acp-agent.ts#L81-L90) 与 [ACP stop-reason mapping](https://github.com/getpaseo/paseo/blob/b4ab0d9db6e5668218e5aaa34f15ef3dd133e3ec/packages/server/src/server/agent/providers/acp-agent.ts#L2633-L2657)；OpenCode [helper server](https://github.com/getpaseo/paseo/blob/b4ab0d9db6e5668218e5aaa34f15ef3dd133e3ec/packages/server/src/server/agent/providers/opencode/server-manager.ts#L277-L301) 与 [SDK client](https://github.com/getpaseo/paseo/blob/b4ab0d9db6e5668218e5aaa34f15ef3dd133e3ec/packages/server/src/server/agent/providers/opencode-agent.ts#L1266-L1274)；Pi [RPC launch](https://github.com/getpaseo/paseo/blob/b4ab0d9db6e5668218e5aaa34f15ef3dd133e3ec/packages/server/src/server/agent/providers/pi/runtime.ts#L67-L116) 与 [JSONL request / event loop](https://github.com/getpaseo/paseo/blob/b4ab0d9db6e5668218e5aaa34f15ef3dd133e3ec/packages/server/src/server/agent/providers/pi/cli-runtime.ts#L136-L155).

### <a id="paseo-orchestration"></a>编排策略的位置

| 层 | 责任 |
|---|---|
| **daemon** | agent 进程、workspace、session、WebSocket API、MCP server 与 provider adapter |
| **CLI** | `run`、`attach`、`send`，以及 `paseo loop run` 等可执行 primitive |
| **skills** | 教当前调用 agent 如何组合 primitive：committee、handoff、advisor，以及 loop 的参数与验证策略 |

所以“peer 逻辑全在 skills、不在 daemon”也过于绝对：

- `/paseo-committee`、`/paseo-handoff`、`/paseo-advisor` 的**编排政策**主要在 skill；
- `/paseo-loop` 明确把 loop 定义为 CLI primitive，skill 负责生成 worker / verifier prompt 与停止条件；
- committee 里的 “You are the middleman” 指**调用该 skill 的 agent**，不是让人类逐条转发。只有重大分歧才交给用户决断。

> 来源：[README 的 daemon / skills 分工](https://github.com/getpaseo/paseo/blob/b4ab0d9db6e5668218e5aaa34f15ef3dd133e3ec/README.md#L126-L143)、[`paseo-committee`](https://github.com/getpaseo/paseo/blob/b4ab0d9db6e5668218e5aaa34f15ef3dd133e3ec/skills/paseo-committee/SKILL.md#L33-L77) 与 [`paseo-loop`](https://github.com/getpaseo/paseo/blob/b4ab0d9db6e5668218e5aaa34f15ef3dd133e3ec/skills/paseo-loop/SKILL.md#L13-L31).

### <a id="copilot-pi-bridge"></a>Copilot 与 Pi 的桥接

`copilot --acp` 暴露的是完整 Copilot agent：它仍由自己的 harness 规划、调工具、改文件和跑多轮。
这与把 Copilot 模型接成 **model provider** 不同；后者只借模型，loop 与工具仍归调用方。

本地 `pi 0.80.6 --help` 只列 `--mode text|json|rpc`，没有 ACP server 入口。若保留 Pi 为编排方、
又要把 Copilot 当完整对等 agent，一条直接链路是：

```text
Pi extension / RPC / SDK
        ↕
      bridge
        ↕ ACP client
   copilot --acp
```

也可以跳过 ACP，在 bridge 内直接使用 [Copilot SDK client](#copilot-entrypoints)；
选择取决于要对接标准 ACP agent，还是只对接 Copilot。这里的关键不是“必须用某一座桥”，而是
不要把 full-agent route 与 model-provider route 混成一层。

### <a id="bridge-implementations"></a>现成桥接实现

| 项目 | 作用 | 2026-07 快照 |
|---|---|---|
| [`oijkn/copilot-acp-mcp-bridge`](https://github.com/oijkn/copilot-acp-mcp-bridge/blob/6868dedd7b2bc39696a9c61810b5630c273d6ff4/README.md) | 把 MCP tool call 转成对 `copilot --acp` 的请求 | Node、Apache-2.0 |
| [`bsmi021/mcp-copilot-acp`](https://github.com/bsmi021/mcp-copilot-acp/blob/8207e04fa6acc489521fec54e8e2c84f05661d55/README.md) | MCP server 管理 Copilot ACP session | TypeScript、MIT |
| [`huanyingtianhe/agents-chat`](https://github.com/huanyingtianhe/agents-chat/blob/43ac219dfb505805a18e7eddef05c7f33599867a/README.md) | 面向 ACP-compatible CLI 的多 agent chat UI | TypeScript |
| [`ZebLawrence/agent-team`](https://github.com/ZebLawrence/agent-team/blob/df2f14b1bff74a50fc06bcf68a385c7c749e21f0/agent-team.md) | 基于 Copilot ACP 的 agent-team wrapper | TypeScript |
| [`@buihongduc132/pi-acp-agents`](https://github.com/buihongduc132/pi-acp-agents/blob/f9fc0551d558de99938615f16de4602a1b28b8a0/README.md) | Pi extension，用 ACP spawn / message / status、fan-out、task 与 DAG 等工具控制外部 agent | npm `0.5.0`，依赖 ACP SDK `^0.21.0` |

Paseo `0.1.107` 仍依赖 `@agentclientprotocol/sdk@^0.17.1`。ACP TypeScript SDK 的 app-builder
迁移发生在 **0.26 → 0.27**：旧的 `ClientSideConnection` 转向
`client({ name }).connectWith(...)`；不是“0.x → 1.x 才换 API”。当前 `1.2.1` 仍保留旧 class，
但已标 deprecated compatibility wrapper。

> 来源：Paseo [server dependencies](https://github.com/getpaseo/paseo/blob/b4ab0d9db6e5668218e5aaa34f15ef3dd133e3ec/packages/server/package.json#L66-L76)；ACP SDK [0.26 → 0.27 migration](https://github.com/agentclientprotocol/typescript-sdk/blob/26da1ae7ab66fae0f5e77272dee3e5d562d24aee/MIGRATION_0.26_0.27.md#L5-L42) 与 [`ClientSideConnection` deprecation](https://github.com/agentclientprotocol/typescript-sdk/blob/26da1ae7ab66fae0f5e77272dee3e5d562d24aee/src/acp.ts#L3053-L3075)；npm stable 为 [`1.2.1`](https://registry.npmjs.org/@agentclientprotocol/sdk/1.2.1).
