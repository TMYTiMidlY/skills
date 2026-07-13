# Coding-agent SDK：Copilot / Claude / Codex 横向对照

要用代码驱动 coding agent，先分清接入的是**模型 API**，还是已经包含规划、工具调用、文件编辑、
shell、权限与会话循环的 **agent runtime**（agent 运行时）。这不是语言覆盖问题：类型选错后，
即使 SDK 支持再多语言，也仍要自己补齐缺失的 harness。

本文把容易混在一起的三件事拆开：接入层级、运行时所有权、传输协议；再对照 Copilot、
Claude、Codex 的官方 agent SDK。事实快照更新于 **2026-07-14**；上游源码链接锁到 tag 或 commit，
滚动版本在写入产品文档前仍应重新核对。

## <a id="integration-layers"></a>接入层级

### <a id="runtime-layers"></a>模型 API、编排框架与 agent runtime

| 层 | 接到的对象 | 已提供 | 仍需调用方负责 |
|---|---|---|---|
| **API SDK** | 模型的 HTTP API | 鉴权、请求类型、流式 token、重试等客户端能力 | 规划循环、工具、文件系统、shell、权限、会话与 sandbox |
| **编排框架** | 自定义 agent workflow | 状态机、handoff、guardrail、工具注册等编排原语 | coding-agent 工具集与具体 runtime；例如 LangGraph / OpenAI Agents SDK 本身不等于 Codex CLI |
| **agent SDK** | 完整 coding-agent runtime | 多轮工具循环、文件与命令执行、结构化事件、会话控制 | runtime 生命周期、权限策略、隔离、持久化与产品 UI |
| **托管 cloud agent API** | 厂商托管的远程任务 | 远程环境、branch / PR 级自动化 | 本机工作区、细粒度 tool event、本地 shell 控制 |
| **扩展或工具协议** | 已存在宿主的扩展点 | 给宿主增加工具、命令、面板或外部服务 | 从外部拥有并驱动整个 agent runtime；MCP 属于工具协议，不是 agent SDK |

Agent SDK 不是“API SDK 再加几个工具函数”。它绑定的是一套具体 harness：模型之外还有 loop、
工具实现、权限模型、上下文管理和会话存储。

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
| **stdio + JSONL** | Codex SDK、Pi RPC | 子进程可长期存活；逐行消息便于流式读取，不等于 one-shot |
| **stdio / TCP + JSON-RPC** | Copilot SDK runtime connection | 一条双向连接承载请求、通知、事件和取消；schema 与版本协商是兼容性边界 |
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
| **OpenAI Codex SDK** | TypeScript、Python | TypeScript SDK spawn `codex` CLI 并经 stdio 交换 JSONL；Python 包依赖 CLI binary 包 | CLI、SDK 与 Rust runtime 同仓，整仓 Apache-2.0 |

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
| **Codex** | TypeScript `startThread().run()` / `runStreamed()` / `resumeThread()`；Python `thread_start()` / `thread_resume()` / `thread.run()` / `thread.turn().stream()` | `ThreadEvent` 包含 thread / turn / item 生命周期与 fatal `error`；`ThreadItem` 包含命令执行、文件修改、MCP、Web 搜索、todo、reasoning、agent message 与 non-fatal `error` |

> 来源：Copilot [Node quick start](https://github.com/github/copilot-sdk/blob/7e2900416b1ac835785fa26e0eb5f634ff24adf9/nodejs/README.md#L30-L61)、[session API](https://github.com/github/copilot-sdk/blob/7e2900416b1ac835785fa26e0eb5f634ff24adf9/nodejs/src/session.ts#L254-L337) 与 [session event types](https://github.com/github/copilot-sdk/blob/7e2900416b1ac835785fa26e0eb5f634ff24adf9/nodejs/src/generated/session-events.ts#L3054-L3081)；Claude [Python README](https://github.com/anthropics/claude-agent-sdk-python/blob/528265fa09da954f0a0da1bf31e16db32b510138/README.md#L33-L132) 与 [`ClaudeAgentOptions`](https://github.com/anthropics/claude-agent-sdk-python/blob/528265fa09da954f0a0da1bf31e16db32b510138/src/claude_agent_sdk/types.py#L1726-L2067)；Codex [`ThreadEvent`](https://github.com/openai/codex/blob/bc8222b8d9e44377a3d7c7b7970e32e7c29ec34f/sdk/typescript/src/events.ts#L68-L82)、[`ThreadItem`](https://github.com/openai/codex/blob/bc8222b8d9e44377a3d7c7b7970e32e7c29ec34f/sdk/typescript/src/items.ts#L97-L128) 与 [Python SDK README](https://github.com/openai/codex/blob/bc8222b8d9e44377a3d7c7b7970e32e7c29ec34f/sdk/python/README.md).

会话持久化不是三家共享的统一接口：

- Copilot runtime 的 `baseDirectory` 默认是 `~/.copilot`，包含 session state、配置等；精确磁盘布局属于 runtime 实现细节。
- Claude 从 `ResultMessage.session_id` 恢复会话；底层 CLI 使用本地 JSONL，Python SDK 另有 `session_store` 协议可接外部存储。
- Codex 明确把 thread 持久化到 `~/.codex/sessions`，通过 `resumeThread(id)` / `thread_resume(id)` 恢复。

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

### <a id="copilot-files"></a>源码、类型声明与缓存位置

| 位置 | 内容 | 稳定性 |
|---|---|---|
| [`github/copilot-sdk`](https://github.com/github/copilot-sdk/tree/7e2900416b1ac835785fa26e0eb5f634ff24adf9) | 公开 SDK 源码与文档 | 首选依据 |
| `node_modules/@github/copilot-sdk/dist/index.d.ts` | Node 根包类型声明 | 随安装版本变化 |
| `~/.cache/github-copilot-sdk/cli/<version>/copilot` | Python SDK 在 Linux 的 CLI binary cache | 公开源码可核；macOS / Windows 路径不同 |
| `~/.cache/copilot/pkg/<platform>/<version>/copilot-sdk/*.d.ts` | 某些 Copilot CLI SEA 构建解包给 extension 的声明 | 本地实现 cache，不是 SDK 安装位置，也不是公开稳定契约 |

> 来源：Python SDK 的跨平台 cache 规则见 [`_cli_download.py`](https://github.com/github/copilot-sdk/blob/7e2900416b1ac835785fa26e0eb5f634ff24adf9/python/copilot/_cli_download.py#L1-L9).

## <a id="server-integration"></a>多用户服务化

SDK 已经解决“如何驱动一个 agent runtime”，但 Web 服务还要解决多用户、多标签页、长生命周期、
可恢复与隔离。下面是服务层模式，不是三家 SDK 共享的 API。

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
  维持双向会话；这是一项 provider-specific 能力，不应假定所有 `query()` 都可这样使用。
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
