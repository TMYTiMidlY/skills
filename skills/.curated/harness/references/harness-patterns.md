# Agent harness 架构模式与 Copilot SDK

harness（运行壳）= 拥有 agent runtime 的那一层：它启动或接管 agent、注入上下文 / 工具、订阅事件、处理取消、持久化状态。选哪种形态看控制需求，不要按"哪种传输时髦"来选。

本文前半讲五种通用 harness 形态及取舍，后半把 Copilot SDK 当作"SDK client + extension host"两种形态的具体实例详解。

## 五种 harness 形态

### CLI 子进程一次性（CLI subprocess one-shot）

例子：`subprocess.run(["copilot", "-p", ...])`，或为单条 prompt shell out 调 Codex / Claude / Copilot。

- 优点：最好搭，直接复用现成 CLI，无需对接任何协议。
- 失效模式：每次冷启动；streaming / abort（取消）语义弱；难以观察内部状态；多会话编排别扭。

适合脚本和低频自动化，不适合常驻 orchestrator（编排器）。

### SDK client / app-server 形态

例子：Copilot 的 `CopilotClient` + `RuntimeConnection`，或一个 controller 接管的 app-server 式 runtime。

- 优点：orchestrator 拥有 runtime 生命周期，能创建 / 恢复会话、订阅事件、切换模型、取消当前回合（turn）。
- 失效模式：与 SDK 协议版本耦合更紧；auth、能力隔离、进程清理都要自己负责。

当 harness 是产品的一个组件、而不是一个 shell 包装时用它。

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

## Copilot SDK 详解

下面这些来自 Copilot CLI `1.0.66-1` 自带的 SDK 类型声明（`copilot-sdk/*.d.ts` 与打包实现）以及 npm registry 元数据，是上面"SDK client"与"extension host"两种形态的具体落地。

### 两个入口：client vs extension

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
- Copilot CLI help 暴露 `--acp`（"Start as Agent Client Protocol server"，作为 ACP server 启动）。
- 打包 `app.js` 里有隐藏 / 内部的 server flag：`--server`、`--ui-server`、`--managed-server`；官方文档没说明前当成内部用法。
- Copilot CLI help 暴露 `--extension-sdk-path <directory>`，可覆盖注入给扩展子进程的那份 `@github/copilot-sdk`。
- 本次重构时核对的 npm registry `dist-tags`：`latest` 是 `1.0.4`，另有 `prerelease`、`unstable` 标签。要在面向用户的说明里写死版本前先重新核一次。

### 选型经验法则

- 只想要一次性答案、能接受冷启动 → CLI 子进程最省事。
- 需要 streaming 事件、取消、会话生命周期、切模型、多会话 → 用 `CopilotClient` + `RuntimeConnection`。
- 是在给用户**当前活着**的 CLI 会话加能力 → 用 `joinSession()` 写扩展。

## Case study：QA ↔ qatlas-lean

最近一版 QA ↔ qatlas-lean 的设计选了"全 JSON-RPC 单连接、插件零 HTTP、浏览器内容经 host/core relay 中转"。这是个有用的 case study：它把"宿主 / 插件紧密控制"做到最优、避开了 HTTP 旁路通道。但它**不是**普适规则——对更小、更松的集成，一个简单的 CLI 子进程或 HTTP 边界仍然可能是对的。
