# Coding-agent SDK：Copilot / Claude / Codex 横向对照

要用代码驱动一个 coding agent，先分清两类截然不同的 SDK——选错类型，再多语言也没用：

- **agent SDK**：把"会自己 plan、调工具、改文件、跑 shell、带 session"的整个 **agent runtime**
  封装成库。你给目标 + 权限，它跑完一轮一轮的循环。能直接替掉手搓 `copilot -p` 子进程。
- **API SDK**：chat/completions 的 HTTP 客户端，给 model 一段输入拿一段输出；plan / 工具 /
  文件编辑 / 循环全得自己搭。名字里也带 "sdk"，但低一层——用它做 agent 等于从头写 harness。

qatlas 这类 daemon 要的是 **agent SDK**；下面也列 API SDK 是为了讲清两者别混。矩阵 + 文档实测于
2026-06-29，版本只佐证"有/无"，会动，写死前重核。

## 接入 / 驱动形态先选

### CLI 子进程一次性（CLI subprocess one-shot）

例子：`subprocess.run(["copilot", "-p", ...])`，或为单条 prompt shell out 调 Codex / Claude / Copilot。

- 优点：最好搭，直接复用现成 CLI，无需对接任何协议。
- 失效模式：每次冷启动；streaming / abort（取消）语义弱；难以观察内部状态；多会话编排别扭。

适合脚本和低频自动化，不适合常驻 orchestrator（编排器）。

### SDK client / app-server 形态

例子：Copilot 的 `CopilotClient` + `RuntimeConnection`，或一个 controller 接管的 app-server 式 runtime。

- 优点：orchestrator 拥有 runtime 生命周期，能创建 / 恢复会话、订阅事件、切换模型、取消当前回合（turn）。
- 失效模式：与 SDK 协议版本耦合更紧；auth、能力隔离、进程清理都要自己负责。

### Extension-host（扩展宿主）形态

例子：VS Code 扩展、Copilot SDK 的 `joinSession()`、Zotero 插件。

- 优点：宿主拥有生命周期与 UI；扩展在宿主的权限模型内贡献命令 / 工具 / hooks / 面板。
- 失效模式：扩展不能假定自己掌握整个进程；API 面被宿主注入的那部分限定。

当用户已经身处某个宿主应用、而这个功能应当"原生地"长在宿主里时用它。

### JSON-RPC 单连接

例子：LSP（Language Server Protocol，语言服务器协议），以及 Copilot SDK 内部经 `vscode-jsonrpc` 的实现。

- 优点：一条双向通道同时承载请求、通知、事件、取消、能力协商（capability negotiation）和版本化。
- 失效模式：schema / 版本兼容性要认真对待；长连接的健康度本身成了可靠性工程的一部分。

当需要宿主 / 插件紧密协作、而"HTTP 端点 + webhook"会把控制流 / 数据流 / 事件流拆到太多机制里时，用它。

### HTTP / webhook 微服务形态

- 优点：好 curl、好部署、好横向扩、用通用工具就能调试。
- 失效模式：对"宿主 / 插件深度协作"往往更差；取消、streaming、背压（backpressure）、能力协商通常都得额外加旁路通道。

适合粗粒度的服务边界，不适合当一个本地 harness 的默认插件 ABI（应用二进制接口）。

## 官方 agent SDK

| agent SDK | 语言覆盖 | 开放度 | 官方文档 / 源码 |
|---|---|---|---|
| **GitHub Copilot SDK** | TS、Python、Go、.NET、Java、Rust（六语言对等，同一 Copilot CLI engine） | 闭源 engine，SDK / docs 公开；SDK 经 JSON-RPC 控制 CLI server | 总入口 [`github/copilot-sdk`](https://github.com/github/copilot-sdk)；README 明确 "same engine behind Copilot CLI"，支持 Python / TypeScript / Go / .NET / Java / Rust；Node 包 `@github/copilot-sdk` 依赖 `@github/copilot` + `vscode-jsonrpc`；会话在 `~/.copilot/session-state/<sessionId>/` |
| **Claude Agent SDK** | TS、Python | SDK 源码公开；Claude Code runtime 闭源 / minified；使用受 Anthropic commercial terms 约束 | [`code.claude.com/docs/en/agent-sdk/overview`](https://code.claude.com/docs/en/agent-sdk/overview)；源码 [`anthropics/claude-agent-sdk-typescript`](https://github.com/anthropics/claude-agent-sdk-typescript)、[`anthropics/claude-agent-sdk-python`](https://github.com/anthropics/claude-agent-sdk-python)；会话存档通常在 `~/.claude/projects/*.jsonl`，也有 SDK session store 选项 |
| **OpenAI Codex SDK** | TS、Python | 真开源 Apache-2.0；CLI / SDK / runtime 都在 `openai/codex` | [`openai/codex` `sdk/`](https://github.com/openai/codex/tree/main/sdk) = `typescript` + `python` + `python-runtime`；TS `Codex.startThread()` / `resumeThread()`；Python 包 `openai-codex` 依赖 `openai-codex-cli-bin`；会话存档 `~/.codex/sessions/` |

Copilot 是唯一把 agent SDK 铺满六语言的，README 定位为 "the same engine behind Copilot CLI… no need
to build your own orchestration"。Claude / Codex 只有 TS、Python；Codex 整仓 Apache-2.0，改 harness 直接读
`sdk/` 源码不必逆向，Claude runtime 闭源行为靠逆向。包名：Copilot `@github/copilot-sdk`、`github-copilot-sdk`、
`GitHub.Copilot.SDK`、`github.com/github/copilot-sdk/go`、`github-copilot-sdk` crate、`com.github:copilot-sdk-java`；
Claude `@anthropic-ai/claude-agent-sdk`、`claude-agent-sdk`；Codex `@openai/codex-sdk`、`openai-codex`。

### 关键 API 形状

| SDK | 最小可用 API | 证明它不是裸 chat SDK 的事件 / 能力 |
|---|---|---|
| **Copilot** | `CopilotClient` 创建 / 恢复 session；`session.send()`、`sendAndWait()`、`abort()`、`disconnect()`；`RuntimeConnection.forStdio/forTcp/forUri` | agent loop 文档明确：SDK 只是 transport，Copilot CLI 执行多 turn tool-use loop；事件含 `assistant.turn_start/end`、`tool.execution_start/complete`、`session.idle`、`session.task_complete`；默认暴露 Copilot CLI first-party tools，permission handler 决定 approve / deny |
| **Claude** | Python `query(prompt=..., options=ClaudeAgentOptions(...))`；`ClaudeSDKClient.connect/query/receive_response/interrupt`；TS `query({ prompt, options })` | `ClaudeAgentOptions` 有 `tools` / `allowed_tools` / `disallowed_tools`、`permission_mode`、`cwd`、`max_turns`、`mcp_servers`、`hooks`、`agents`、`skills`、`can_use_tool`、`session_store`；message stream 有 `AssistantMessage`、`ResultMessage.session_id`、tool-use / tool-result blocks |
| **Codex** | TS `new Codex().startThread().runStreamed(input)` / `resumeThread(id)`；Python `Codex().thread_start()` / `thread_resume()` / `thread.run()` / `thread.turn().stream()` | TS `ThreadEvent` 含 `thread.started`、`turn.started/completed/failed`、`item.started/updated/completed`；`ThreadItem` 含 `command_execution`、`file_change`、`mcp_tool_call`、`web_search`、`todo_list`、`reasoning`、`agent_message` |

## Copilot SDK 详解：client vs extension

下面这些来自公开仓 [`github/copilot-sdk`](https://github.com/github/copilot-sdk)、Copilot CLI `1.0.66-1` 打包 SDK 类型声明以及 npm registry 元数据，是上面"SDK client"与"extension host"两种形态的具体落地。

`@github/copilot-sdk` 和 `@github/copilot-sdk/extension` 是两套不同的面：

| 入口 | 主 API | 用途 | 拥有关系 |
|---|---|---|---|
| `@github/copilot-sdk` | `CopilotClient`、`RuntimeConnection`、`CopilotSession` | daemon / orchestrator 的程序化控制 | 你的进程拥有或连上一个 runtime，再创建 / 发送 / 恢复会话 |
| `@github/copilot-sdk/extension` | `joinSession()` | 写 Copilot CLI 扩展 | 前台那个 Copilot CLI 会话拥有宿主进程，并注入 extension SDK |

别把这俩混成一句"SDK 只能写扩展"。extension 入口才是写扩展用的；根包是程序化控制 runtime 的 API。

### RuntimeConnection 的三种连接方式

`copilot-sdk/types.d.ts` 里观察到的工厂：

```ts
RuntimeConnection.forStdio({ path?: string, args?: readonly string[] })
RuntimeConnection.forTcp({ port?: number, connectionToken?: string, path?: string, args?: readonly string[] })
RuntimeConnection.forUri(url: string, { connectionToken?: string })
```

设计含义：

- `forStdio`：最接近"spawn 一个子 runtime、走 stdio 说 JSON-RPC"。
- `forTcp`：让 SDK spawn 一个监听 TCP socket 的 runtime 再连上去。
- `forUri`：连一个**已经在跑**的 runtime，这种模式下 SDK 不 spawn 进程。

同一份声明里还警告：CLI 式的默认能力对"服务端多用户应用"是不安全的，除非应用显式只开一组很窄的能力。

### 会话控制面（session 方法）

`copilot-sdk/session.d.ts` 暴露的核心编排方法：

```ts
session.send(promptOrOptions)
session.sendAndWait(promptOrOptions, timeout?)
session.on(handler)
session.setModel(model, options?)
session.abort()
session.disconnect()
```

声明注释里有一个重要行为点：`sendAndWait` 的 timeout 只控制"调用方等多久拿响应"，**不会**中止正在进行的 agent 工作。真要取消当前回合用 `abort()`。

### 协议与实现事实

- `SDK_PROTOCOL_VERSION = 3`（见 `copilot-sdk/sdkProtocolVersion.d.ts` 与打包实现）。
- 打包实现内含 `vscode-jsonrpc@8.2.1`，所以 SDK client 与 runtime 之间就是 JSON-RPC 单连接 + 强类型请求 / 事件。
- `@github/copilot-sdk` 的 `nodejs/package.json` 描述是 "programmatic control of GitHub Copilot CLI via JSON-RPC"，并依赖 `@github/copilot` + `vscode-jsonrpc`。
- Node / Python / .NET SDK 会自动带 Copilot CLI runtime；Go / Java / Rust 默认要求 PATH 里已有 `copilot`，或使用各自的 bundling 机制。
- Python SDK 缓存 CLI binary 的默认 Linux 路径是 `~/.cache/github-copilot-sdk/cli/<version>/copilot`；不要把它误写成 `.d.ts` cache。
- Copilot CLI help 暴露 `--acp`（"Start as Agent Client Protocol server"，作为 ACP server 启动）。
- 打包 `app.js` 里有隐藏 / 内部的 server flag：`--server`、`--ui-server`、`--managed-server`；官方文档没说明前当成内部用法。
- Copilot CLI help 暴露 `--extension-sdk-path <directory>`，可覆盖注入给扩展子进程的那份 `@github/copilot-sdk`。
- 本次重构时核对的 npm registry `dist-tags`：`latest` 是 `1.0.4`，另有 `prerelease`、`unstable` 标签。要在面向用户的说明里写死版本前先重新核一次。

### Copilot SDK 路径分清

之前容易把"本地类型声明"和"runtime cache"混在一起。当前可验证事实：

- **公开 SDK 源码 / 文档**：优先看 `github/copilot-sdk`，不要再只靠本地逆向。
- **Node SDK 包类型声明**：`node_modules/@github/copilot-sdk/dist/index.d.ts`。
- **Copilot CLI SEA 自解包 cache**：本机安装的 `copilot` 单文件 CLI 运行后，可能在 `~/.cache/copilot/pkg/<platform>/<version>/copilot-sdk/*.d.ts` 留下 CLI 注入给 extension 的 SDK 声明；这是 CLI cache，不是 SDK package 的安装位置。
- **Python SDK runtime cache**：Python SDK 下载 / 缓存的是 **CLI binary**，默认 Linux 路径是 `~/.cache/github-copilot-sdk/cli/<version>/copilot`；这个 cache 里不是 `.d.ts`。

## 不是"本地 agent SDK"的相邻概念

这些名字里也常出现 "agent" 或 "sdk"，但边界不同：

| 名称 | 分类 | 适合什么 | 不适合什么 |
|---|---|---|---|
| **OpenAI / Anthropic 官方 API SDK** | API SDK（裸 HTTP client） | 你要完全自写工具、loop、history、session、权限与 sandbox | 直接替代 `copilot -p` / Claude Code / Codex CLI |
| **OpenAI Agents SDK / LangGraph / LangChain / Vercel AI SDK** | orchestration SDK（编排框架） | 你愿意自己定义工具函数、状态机、handoff / guardrail | 需要现成 coding-agent 文件编辑 + shell runtime 时仍要补 harness / toolset |
| **GitHub Copilot Cloud Agent API** | cloud agent API | 让 GitHub 托管环境接 issue / prompt 后自己改 branch / PR | 本地 daemon 细粒度接管 tool events、改本机 checkout、跑本机 shell |
| **Copilot Extensions / MCP** | extension / tool protocol | 让 Copilot 或别的 agent 调用你的服务 / 工具 | 从你的 daemon 内部"驱动一个 coding agent runtime" |

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
只想要一次性答案、能接受冷启动 → CLI 子进程最省事。
需要 streaming 事件、取消、会话生命周期、切模型、多会话 → 用 `CopilotClient` + `RuntimeConnection`。
是在给用户**当前活着**的 CLI 会话加能力 → 用 `joinSession()` 写扩展。

对 daemon / orchestrator 的经验法则：

- 只要你想做自己的 TUI / Web UI / bot，但仍要拿到 tool-call、file-change、shell-output、permission-request、session-id 等结构化事件，就用 agent SDK。
- 只需要"给模型一段文本，让它返回一段文本 / JSON"，不让它碰文件和 shell，用 API SDK。
- 想把 qatlas 能力暴露给任意外部 agent，用 MCP / JSON-RPC tool server；想让 qatlas 自己驱动一个 agent，选 agent SDK。
- Cloud Agent API 适合 GitHub PR 自动化，不适合本地 qatlasd 接管工作区，因为它运行在 GitHub infra 里，状态也粗到 task/PR 级。

## 服务端集成模式（把 agent SDK 包成多用户 web 服务）

agent SDK 默认形态是"单进程、单会话、一次性"，而 web 服务要"多用户、多标签页、长生命周期、可恢复"。
下面是几个官方 / 社区开源 demo 收敛出的服务端模式（2026-06 实测可跑），驱动任何 agent SDK 时通用：

- **一个 session 对应一个 runtime 实例，多个浏览器连接 fan-out**：每个 WebSocket（标签页）都去
  `resumeSession` 会注册互相冲突的 tool handler。正确做法是维护 `sessionId → 单个 session` +
  `session → Set<连接>`，事件来了向该集合广播；最后一个连接断开才 `disconnect` + 回收。
- **并发去重存 Promise 而不是实例**：用 `Map<sessionId, Promise<Session>>` 而非 `Map<sessionId, Session>`，
  两个标签页同时连同一个新 session 时，第二个拿到的是同一个 in-flight promise，不会创建两份。
- **会话状态做成可迁移卷**：在 `assistant.turn_end`（或等价 turn 结束事件）时把 session 工作目录
  rsync / 同步到独立 filestore，并 debounce 几秒避免连续 turn 重复同步。配合负载均衡，任一 app server
  都能接管任一 session —— 把"本地 agent"变成可水平扩展的无状态服务。
- **多租户隔离可用"软 bash + 软 FS"而非容器**：用纯软件实现的虚拟文件系统 + 虚拟 bash（如 `just-bash`），
  每 session 独立挂载，再用 SDK 的 `defineTool(..., overridesBuiltInTool: true)` 把内置 bash 工具
  偷换成虚拟版；权限按"减法"配（先只开不碰文件系统的安全工具子集，再单独把文件操作重定向到虚拟 FS）。
  单进程多租户、无需每人一个容器。
- **`canUseTool` / 权限回调可当成"向人类发起的阻塞 RPC"**：在回调里 `await` 一个 Promise，把 resolver
  按请求 id 存进 pending map，经 WebSocket 把问题推给前端；用户在 UI 点选后回传、resolve 该 promise，
  agent 循环才解冻继续。**务必在连接关闭时 reject 该连接名下所有挂起的 promise**，否则 agent 的 await
  永久悬挂、循环泄漏。这是把"人"插进 agent 决策回路的通用手法（审批、澄清、HTML 选项卡）。
- **把"一次性 query"骗成"长连接会话"**：当 SDK 的 `query()` 是一次性流式接口时，给它传一个永不结束的
  async iterator 作为输入（一个单槽 async 队列：有消费者等待就直接投递、否则缓冲），输入流"永不说完"
  就让 agent 循环一直活着，每 `push()` 一条用户消息就唤醒一轮。无需依赖 SDK 自带的 resume 机制。
- **闲置回收**：长连接服务给每个 session 配 idle GC（如 30 分钟无活动回收），并把 transcript 持久化到
  磁盘 / 外部 store，断连后可重连恢复。
- **事件白名单转发**：只向前端转发需要的事件类型（user/assistant message、turn start/end、
  tool execution start/complete、session idle/error 等），`session.error` 在生产要脱敏（会泄露内部信息）。

这些模式在 GitHub `copilot-sdk`、Claude Agent SDK、Codex SDK 上都适用，因为它们要解的是同一道
"单会话 runtime ↔ 多用户长生命周期服务"的鸿沟，与具体哪家 SDK 无关。
