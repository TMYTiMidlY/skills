# DeepSeek Harness（dsh）Plugin 开发

本文面向要编写或维护 dsh Plugin 的开发者，使用 TypeScript、Cordis 配置和仓库中的真实 package 说明扩展点。运行方式、内置扩展的用户行为和完整权限模型见 [DeepSeek Harness 运行时](deepseek.md)。

> **来源口径：** 本文按 2026-08-16 的[官方仓库源码状态](https://github.com/deepseek-ai/deepseek-harness/commit/47f943859bef60e4160492346772ded9b24f765a)核对。代码和文档链接固定到该状态，但可读文字不展示内部 ref。

## <a id="plugin-basics"></a>Plugin 基础

### 开发路径

先分清代码最终放在哪里。仓库外 Plugin 面向社区安装，仓库内 workspace package 则参与 dsh 自身的构建、类型图、测试和文档约束；两者共享 Cordis 运行模型，但工程规则不同。

#### 仓库外 Plugin 与 Bundle

仓库外开发从一个普通 TypeScript / JavaScript module 开始，通过 `--patch` overlay 挂到现有 Profile：

```yaml
- insert:
    - id: hello
      name: '/absolute/path/to/my-plugin.ts'
```

```sh
dsh web --patch ./cordis.patch.yml
```

本地验证完成后，再把代码与 `cordis.patch.yml` 打成声明 `dsh.bundle` 的 package。使用者通过 `dsh plugin --profile <name> add <package>` 安装，Profile 负责依赖和配置层，不要求 Plugin 进入官方 monorepo。

#### 仓库内 workspace package

仓库内 package 位于 `packages/<group>/<pkg>/`，需要 package manifest、TypeScript project reference、README、invariant 和 tests。Host package 与 Client package 属于不同 TypeScript aggregate；普通 package 只能注册进其中一侧。

新增 package 时应先找相同角色的现有实现作为模板。Tool 可看 `packages/shell/tool-bash`，能力 Provider 可看 `packages/shell/bash-local`，LLM adapter 可看 `packages/llm/llm-deepseek`，Web Client Plugin 可看 `packages/client/ui-workflow-run`。

> 来源：[仓库外第一个 Plugin 的加载路径](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/user/develop/basic/index.md#L7-L64)；[仓库内 package 的文件与注册清单](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/cookbook/adding-a-package.md#L7-L43)。

### 模块形式与配置

#### Function Plugin 与 Service class

普通 function Plugin 使用具名导出，不提供 default export：

```ts
import type { Context } from '@deepseek-ai/cordis'
import Schema from '@deepseek-ai/schemastery'

export const name = 'greet-plugin'
export const inject = ['tools']

export interface Config {
  greeting: string
}

export const Config: Schema<Config> = Schema.object({
  greeting: Schema.string().default('Hello'),
})

export function apply(ctx: Context, config: Config): void {
  // Register effects through ctx.
}
```

提供 Cordis service 的 package 通常 default-export 一个 `Service` subclass：

```ts
import { Service, type Context } from '@deepseek-ai/cordis'

declare module '@deepseek-ai/cordis' {
  interface Context {
    metrics: MetricsService
  }
}

export default class MetricsService extends Service {
  static inject = ['llm']

  constructor(ctx: Context) {
    super(ctx, 'metrics')
  }

  record(name: string, value: number): void {
    // ...
  }
}
```

不要同时给 function Plugin 增加 default export。Loader 会把 default export 当作 Plugin 本体，导致同一 module 上的 `inject`、`Config` 或 `apply` namespace 被丢失。

#### Config Schema 与加载校验

所有部署可能调整的值都应进入 `Config`，由 Schemastery 在加载时验证并填充默认值：

```ts
export interface Config {
  timeoutMs: number
  mode: 'fast' | 'accurate'
}

export const Config = Schema.object({
  timeoutMs: Schema.number().default(30_000),
  mode: Schema.union(['fast', 'accurate']).default('fast'),
})
```

Schema 无法表达的跨字段或数值约束，应在 Plugin 加载时显式检查。无效配置要让 Fiber 进入失败状态并报告原因，不要静默跳过 Plugin，也不要在第一次真实请求时才暴露本可提前发现的问题。

> 来源：[Plugin 的 module 形式、依赖和 class form](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/user/develop/basic/index.md#L15-L138)；[Config schema、默认值和失败策略](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/user/develop/basic/config.md#L7-L100)；[Function Plugin 与 Service class 的 export 规则](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/packages/AGENTS.md#L3-L17)。

### 生命周期与协作

#### Context、Fiber、effect 与 HMR

每个 Plugin instance 都由 Fiber 管理。Fiber 等待必需 service，执行 Plugin，记录其 effects，并在卸载时撤销注册和等待异步清理完成。

```ts
export function apply(ctx: Context): void {
  ctx.on('session/event', handler)

  ctx.effect(() => {
    const socket = openSocket()
    return async () => {
      await socket.close()
    }
  })
}
```

`ctx.on()`、registry 的 `register()` 和 `ctx.effect()` 都应把 disposer 绑定到当前 Fiber。HMR 的工作方式是卸载旧 Fiber、清理 effects、加载新代码；模块级 singleton、未登记的 timer 或未等待的 child process 会绕过这套生命周期。

> 代码落点：[Cordis Fiber 状态与 effect 实现](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/vendor/cordis/src/fiber.ts#L142-L220)；[Plugin 清理、dispose 与 HMR 语义](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/user/develop/framework/index.md#L7-L131)。

#### Services、依赖与隔离

Service 是一个 Plugin 提供给其他 Plugin 的具名能力。Consumer 通过 `inject` 声明必需依赖：

```ts
export const inject = ['tools', 'metrics']

export function apply(ctx: Context): void {
  ctx.metrics.record('loaded', 1)
}
```

必需 service 尚未出现时，Consumer Fiber 保持 pending；Provider 消失时，Consumer 自动卸载，并在 service 恢复后重新加载。可选 service 不写进 `inject`，而是在使用点通过 `ctx.get(name)` 查询。

同名 service 可以在不同 Cordis group 中隔离。一个 Agent preset 或子树需要自己的 shell、tools 或 policy 时，应使用 isolate realm，而不是给 service 发明新的全局名称。

> 来源：[Service 提供、消费与依赖消失后的行为](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/user/develop/framework/service.md#L7-L110)；[Service isolation](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/user/develop/framework/service.md#L111-L139)。

#### Events 与拦截点

Event 用于 Plugin 间松耦合通信。常见模式：

| 模式 | 行为 | 适合 |
|---|---|---|
| `emit` | 广播给全部 listener | 通知和观察 |
| `bail` | 第一个有效返回值结束分发 | 查询或短路选择 |
| `serial` | 按顺序 await，首个有效值停止 | 顺序决策 |
| `waterfall` | listener 包裹下游结果 | 可组合的拦截与策略 |

Waterfall listener 必须调用 `next()` 才会把控制权交给下游；不调用表示有意截断：

```ts
ctx.on('tools/pre-execute', async (exec, next) => {
  if (!isAllowed(exec)) {
    return { kind: 'deny', reason: 'Denied by policy.' }
  }
  return next()
})
```

Cordis event 与 durable Session event 不同。`agent/*`、`tools/*` 等 Cordis event 描述活着的运行过程；`turn/*`、`step/*`、`tool/result` 等 Session event 写入日志并参与恢复与回放。

> 来源：[Event 模式、typed events 与 effect 清理](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/user/develop/framework/events.md#L23-L138)；[运行时扩展点地图](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/architecture.md#L53-L129)。

## <a id="tool-and-providers"></a>工具与能力 Provider

### Tool Plugin

#### 参数、规范化结果与呈现

Tool Plugin 注入 `ctx.tools`，用 `defineTool()` 声明模型看到的参数和程序化返回值：

```ts
import { defineTool } from '@deepseek-ai/dsh-tools'

export const name = 'tool-greet'
export const inject = ['tools']

export function apply(ctx: Context): void {
  ctx.tools.register(defineTool({
    name: 'greet',
    description: 'Greet someone by name.',
    parameters: {
      name: { type: 'string', required: true },
    },
    output: {
      schema: { type: 'string' },
      render: (_args, value) => [{ type: 'text', text: value }],
    },
    async execute(args, exec) {
      exec.signal.throwIfAborted()
      return `Hello, ${args.name}!`
    },
  }))
}
```

`execute()` 返回由 `output.schema` 定义的 canonical JSON value；`output.render()` 再把它转换成模型上下文。不要让调用者从自然语言中解析 id、状态或字段，也不要为了 UI card 改写 canonical value。

UI presentation 是另一层纯函数。需要 replay 的 result-time 信息通过 `presentationMeta` 进入 durable tool result，再由 `presentCall` / `presentResult` 选择 generic、terminal、diff、search 或 web card。

#### 执行策略与后台任务

| 扩展点 | 用途 |
|---|---|
| `tools/pre-execute` | 可组合的 allow / ask / deny 策略 |
| `ctx.tools.guard()` | 后续 listener 不能撤销的最终拒绝 |
| `tools/execute` | 包裹真实 dispatch，用于 deadline、retry 或 metrics |
| `tools/post-execute` | 改写 value、模型内容或附加上下文 |
| `tools/result` | 观察不可变的最终结果 |

前台工作必须响应 `exec.signal`。已经返回 job id 的后台工作不再属于外层 tool call；把它注册进 `ctx.jobs`，由 job 自己的 cancellation、owner disposal 和 `done` promise 管理生命周期。

> 来源：[Tool 最小形态与 execute contract](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/cookbook/adding-a-tool.md#L7-L56)；[执行策略、Code Mode 与 UI presentation](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/cookbook/adding-a-tool.md#L57-L94)。

### Capability seam

#### Service Definition、Provider 与 Consumer

可替换能力由三个角色组成：

| 角色 | 负责什么 | shell 示例 |
|---|---|---|
| Service Definition | 定义稳定接口和 request/result types | `dsh-shell` |
| Provider | 实现一种执行机制 | `dsh-bash-local`、`dsh-pwsh-local` |
| Consumer | 把能力暴露给模型或其他调用者 | `dsh-tool-bash` |

Provider 和 Consumer 都依赖 Definition，但彼此不依赖。替换 Provider 时，Tool schema 和调用方式可以保持不变；修改 Consumer 的模型呈现时，也不要求改执行器。

#### Package 拆分与 Provider 替换

只有角色确实需要独立演进或替换时才拆成多个 package。一个简单 Tool 同时拥有输入校验和执行逻辑并不违规；过早拆分会增加 manifest、project reference、tests 和版本协调成本。

Definition 应为所有现有 Consumer 设计，不把某个 Tool、UI 或 transport 的私有字段塞进公共 service。Provider 负责把 caller request 解析成完整 spec，并在边界处应用默认值与上限；不要把默认行为散落在执行函数中的 `??` 表达式。

> 来源：[三角色能力设计与 Bash 示例](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/user/develop/practice/index.md#L7-L155)；[仓库中的 capability seam 清单](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/capability-seams.md#L1-L40)。

### LLM adapter

#### 流式协议与错误处理

LLM adapter 是 `ctx.llm` 的 Provider：

```ts
class MyAdapter extends LlmAdapter {
  async *stream(options: GenerateOptions): AsyncIterable<StreamChunk> {
    // Translate provider wire events into StreamChunk.
  }
}

export const name = 'llm-my-provider'
export const inject = ['llm']

export function apply(ctx: Context, config: Config): void {
  ctx.llm.registerAdapter(['my-provider'], new MyAdapter(config))
}
```

Adapter 必须保持统一流协议：usage 在 finish 之前；finish 之后不再输出；tool arguments 以原始 JSON 字符串增量传递；block index 在首次出现时确定；不支持的 `GenerateOptions` 显式报错；transport 和协议失败可以 throw，provider 的带内失败用 error/aborted finish 表达。

Adapter 需要响应 `options.signal`。Provider 要求的 response id、signature 等 native state 只能以最小 lossless JSON 放进 replay state，并由同一个 adapter instance 判断能否用于后续请求。

#### 注册、配置与验证

一个 adapter 可以拥有多个 provider route，但同一路由不能重复注册。Credential 应通过 Config 和 credentials seam 解析，不在代码中读取自创 key 文件。

实现应把 wire types、request serialization、transport parsing、chunk translation 和 adapter class 分开。验证至少覆盖 chunk 顺序、usage/finish、tool-call arguments、abort、unsupported fields、provider errors，以及一次真实 provider smoke。

> 来源：[LLM adapter 形态和协议义务](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/cookbook/adding-an-llm-adapter.md#L7-L43)；[DeepSeek adapter 的注册实现](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/packages/llm/llm-deepseek/src/index.ts#L240-L276)。

## <a id="protocol-and-ui-plugins"></a>协议与界面 Plugin

### 外部协议驱动

#### Agent 控制与 Session 事件

协议驱动把 wire peer 适配到 `ctx.agents`。它通常负责：

1. 创建或恢复 Agent；
2. 把外部输入交给 `followup()`、`steer()` 或 cancel；
3. 订阅 `session/event`，把 durable output 映射回协议；
4. 在连接关闭时 dispose 自己拥有的 Agent，并等待 teardown 完成。

```ts
export const inject = ['agents']

export function apply(ctx: Context): void {
  ctx.on('session/event', (session, event) => {
    if (event.type === 'assistant/message') {
      sendCommittedText(session.id, event.data.message)
    }
  })

  // Wire handlers create agents and feed input through ctx.agents.
}
```

不要把 `followup()` 当成“这个 prompt 的 result promise”。多个 queued、steering 或 injected inputs 可能共享一个 running interval；协议若需要高层 run result，必须清楚定义自己拥有的观察区间。

#### ACP 实现案例

`dsh-acp` 是自动化协议驱动的完整案例。它占用 stdio、创建 fresh Agent、映射 permission request 和 cancellation，只发送 committed assistant message，并在 disconnect 时清理连接拥有的全部 Session。

ACP package 说明“协议驱动”与“完整 UI”不是同一层：reasoning、tool activity、plans、titles 和 presentation 留在 Session log 或 Web Client，不应为了协议方便硬塞进模型或 wire contract。

> 来源：[协议驱动 Plugin 形态](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/cookbook/extension-cookbook.md#L63-L93)；[ACP Plugin 的 Agent 与 Session 生命周期](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/packages/acp/acp/src/index.ts#L1-L120)。

### Web Client Plugin

#### Client package 与 slot 组合

Web Client Plugin 有 Node loader half 和 browser `/client` entry。Client package 通过 `dsh.client` manifest 进入 bundle，并在 `apply(ctx)` 中通过 slot system 组合 UI；业务组件不直接获得 `ctx`。

```ts
export const inject = ['conversationEvents', 'slots']

export function apply(ctx: ClientContext): void {
  ctx.conversationEvents.register(reviewDefinition)
  ctx.slots.inject('conversation.chat.node', () =>
    ctx.slots.register({
      name: 'conversation.chat.node',
      key: 'review-job',
    }, ReviewNodeView))
}
```

一个新 Client package 还要进入 `tsconfig.client.json`、Web Bundle 的 Cordis composition 和依赖 manifest。`dsh.client.inject` 只描述 package graph，不决定 apply 顺序；真实激活仍由 Cordis service injection 控制。

#### Conversation Node 与回放

Conversation Node 把一组 durable Session events fold 成稳定 State，再构造 keyed UI node：

```ts
const reviewDefinition: ConversationNodeDefinition<ReviewState> = {
  kind: 'review-job',
  target: 'chat',
  match: event => event.type === 'review/start'
    ? { id: String(event.data.reviewId), role: 'start' }
    : event.type === 'review/progress'
      ? { id: String(event.data.reviewId), role: 'update' }
      : null,
  start: (_context, match) => initialState(match.event),
  update: (context, match) => reduceState(context.state, match.event),
  buildViewNode: context => buildNode(context),
}
```

每个相关 event 都要携带稳定业务 id；`match()` 只检查当前 event，不能扫描整个 Session window。State 必须能按 log sequence 确定性重放，renderer 只消费最终 node data。测试同时覆盖完整 replay、只有 update 的 tail、prepend 找回 start，以及 live append 与完整 replay 的等价性。

> 来源：[Web Client package 与 slot 规则](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/packages/client/AGENTS.md#L1-L83)；[Conversation Node 的事件、State 与测试路径](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/cookbook/adding-a-conversation-node.md#L9-L231)。

## <a id="session-data-plugins"></a>会话数据 Plugin

### SessionEventMap

模型可见或需要恢复的事实应进入 Session log。Plugin 通过 declaration merging 扩展 event vocabulary：

```ts
declare module '@deepseek-ai/dsh-session/types' {
  interface SessionEventMap {
    'review/start': {
      reviewId: ReviewId
      title: string
    }
    'review/end': {
      reviewId: ReviewId
      summary: string
    }
  }
}
```

新 event 要有稳定 identity、可序列化 payload 和明确 replay 语义。只有实时观察价值、无需恢复的过程信号留在 Cordis event；不要把 live object、callback 或 Host-only handle 写进 Session。

### 持久状态与回放

State 不应另建第二份权威记录。Projection、UI、query 和 telemetry 从 Session events fold；需要缓存时，缓存记录 watermark 并能从持久化 tail 重建。

向模型注入新内容也要先写入 Session event，再从日志派生 request。绕过日志直接改 prompt 会让恢复、fork、telemetry 和 UI replay 看见不同世界。

> 来源：[Session log 与 model-visible invariant](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/architecture.md#L63-L97)；[Session subsystem 的事件类型与存储语义](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/subsystems/session.md#L1-L120)。

## <a id="verification-and-debugging"></a>验证与调试

### 本地 overlay 与组合检查

仓库外 Plugin 先用 overlay 验证：

```sh
dsh web --patch ./cordis.patch.yml
dsh --profile web --dump-config
```

`--dump-config` 用来确认 package 是否解析、row 是否插入、后层是否覆盖目标 id。Plugin 没激活时先看缺失 service、schema failure 和 module resolution，不要把“安装成功”误判成“Bundle 已进入 Profile”。

### 单元测试与资源清理

每个 registry contribution 都应有 HMR-safety test：挂载 Plugin、观察注册存在、dispose Fiber、确认注册消失。生命周期测试还要等待 async cleanup 到 quiescence，不能只断言 abort 或 kill 被调用。

Tool、Provider 和 event policy 的单元测试覆盖错误路径、顺序、取消和重复注册。只 mock LLM、network、clock 等昂贵或非确定边界，尽量使用真实下游实现。

### 真实组合与快照

产品可见 Plugin 还要通过 Loader 启动真实 `cordis.yml`，证明 package export、Config、依赖和 composition 都能按发布入口工作。模型、协议或 UI 输出发生变化时，增加 keyless snapshot；真实 provider 行为再由带 key 的 smoke 验证。

仓库内新增 package 先注册 workspace、同步文档，再运行基础检查：

```sh
pnpm install
pnpm run doc-sync
pnpm run constraints
pnpm run typecheck
pnpm run lint
pnpm run build
pnpm run hygiene
```

实际开发先运行覆盖改动面的最小 test，再根据是否改变 model、protocol、UI 或发布产物升级到 snapshot、browser 或 built-artifact checks。

> 来源：[测试层级、真实入口与 snapshot 要求](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/testing.md#L7-L49)；[仓库内 package 的验证命令](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/cookbook/adding-a-package.md#L109-L118)。

## <a id="packaging-and-community"></a>打包、安装与社区生态

### 打包与安装

#### Bundle 与 Profile manifest

可安装 Plugin package 用 `dsh.bundle` 指向 patch：

```json
{
  "name": "dsh-hello-plugin",
  "type": "module",
  "main": "index.js",
  "dsh": {
    "bundle": {
      "patch": "./cordis.patch.yml"
    }
  }
}
```

```yaml
- insert:
    - id: hello
      name: dsh-hello-plugin
```

Profile manifest 则保存按顺序应用的 Bundle 列表，由 `dsh plugin` 创建和维护。一个 package 没有 `dsh.bundle` 时仍可作为普通 dependency 安装，但不会自动改变 Plugin tree。

#### 配置层与覆盖顺序

有效配置依次应用：

1. Profile 列出的 Bundle patches；
2. Profile 的 `cordis.patch.yml`；
3. Harness home 的 `cordis.patch.yml`；
4. 命令行 `--patch` overlays。

后层按 row id 替换完整 `config`。Bundle author 应提供可直接使用的默认值，并允许部署者在后层覆盖；不要依赖深合并补齐遗漏字段。

#### npm、Git 与构建产物

npm package 应在发布前包含运行产物。Git install 获取的是 source；TypeScript package 需要 `prepare` 自行构建，且 pnpm 要求使用者显式 `allowBuilds`。

`allowBuilds` 是执行 package 代码的授权，不受 Agent sandbox 保护。若不希望要求这项授权，可发布带构建产物的 npm package 或 `pnpm pack` tarball。完整权限关系见运行时篇的 [Plugin 与安装脚本](deepseek.md#trust-boundaries)。

> 来源：[Bundle/Profile manifest、安装和配置顺序](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/user/develop/basic/publish.md#L9-L128)；[Git build script 与预构建分发](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/user/develop/basic/publish.md#L153-L178)。

### 官方发现约定

官方建议 Plugin 仓库添加 [`dsh-plugin`](https://github.com/topics/dsh-plugin) topic，但不提供 catalog、featured list、签名、审核或安装量。Web Settings 的 Plugin inventory 只展示当前部署已经加载的 Plugin，不负责联网发现或安装。

因此“能被 topic 或社区目录找到”“能被 `dsh plugin add` 安装”“已经通过安全审计”是三件不同的事。发布者至少应提供 Bundle manifest、安装命令、支持的 dsh 范围、Host 权限说明和构建脚本边界。

> 来源：[Plugin 仓库的社区发现约定](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/README.md#L37-L45)；[Web Plugin inventory 的本地边界](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/packages/client/ui-settings-plugin-inventory/README.md#L5-L20)。

### 社区插件调研

[`awesome-dsh-plugin`](https://github.com/awesome-dsh-plugin/awesome-dsh-plugin/tree/c5f287967a26213ffdc77450db542e46899573e1) 维护社区 registry；[`dsh-market`](https://github.com/dsh-market/dsh-market/tree/0a2959a7c7809e46f8ce39149f4e4710d2e0a047) 消费该 registry，在 Web Settings 提供浏览、搜索和安装界面。目录收录与市场展示都不构成 DeepSeek 背书或安全审计。

#### DSH 专用扩展

| Plugin | 开发形态 | 用途 | 安装 |
|---|---|---|---|
| [`dsh-TUI`](https://github.com/ccch1mneyyy/dsh-TUI/tree/69f093122458e68515a6c3987898f1817d6beccf) | 独立交互界面 | Claude Code 风格全屏 TUI | `dsh plugin --profile dsh-tui add @deepseek-harness-tui/dsh-tui` |
| [`dsh-agent-teams`](https://github.com/NanmiCoder/dsh-agent-teams/tree/2b1141248f34ee28870d2e39462c0dbefaa5ffdb) | Subagent / workflow | 多 Agent team 与 workflow | `dsh plugin --profile web add @nanmicoder/dsh-agent-teams` |
| [`dsh-market`](https://github.com/dsh-market/dsh-market/tree/0a2959a7c7809e46f8ce39149f4e4710d2e0a047) | Web Client / 安装面 | 社区 Plugin market UI | `dsh plugin --profile web add dshmarket` |
| [`dsh-openpencil`](https://github.com/ZSeven-W/dsh-openpencil/tree/49b0417a6d6fe7a55056bb1a82d4c348a21a6ca6) | 业务 UI / 设计文档 | 在对话中预览和编辑 `.op` 画布 | `dsh plugin --profile web add @zseven-w/dsh-openpencil` |

> dsh-TUI 使用独立的 `dsh-tui` Profile；安装后可运行 `dsh --profile dsh-tui`，也可使用 package 提供的 `dsh-tui` 启动命令。来源：[dsh-TUI 安装与启动](https://github.com/ccch1mneyyy/dsh-TUI/blob/69f093122458e68515a6c3987898f1817d6beccf/README.md#L56-L75)。

#### 多宿主能力

| Plugin | 开发形态 | 用途 | 安装 |
|---|---|---|---|
| [`hindsight`](https://github.com/vectorize-io/hindsight/tree/396f63aafc9b618f04d446e2465cac95aa1cb426/hindsight-integrations/coding-agents) | 记忆 Provider | 长期项目记忆、自动 recall / retain | `dsh plugin --profile web add @vectorize-io/hindsight-coding-agents` |
| [`mirage`](https://github.com/strukto-ai/mirage/tree/14f83208abb2b92d9341a10dbaa4cb4786fe7eb2/typescript/packages/dsh) | Filesystem Provider | 用统一虚拟 filesystem 替换本地 FS / Bash provider | `dsh plugin --profile web add @struktoai/mirage-dsh` |
| [`modlens`](https://github.com/liustack/modlens/tree/b489d7ad51255a8f98086f6ad0534d840505f747) | 视觉 Tool / Provider | OCR、布局和视觉语义证据 | `dsh plugin --profile web add @liustack/modlens` |
| [`modsearch`](https://github.com/liustack/modsearch/tree/e1dba224b72651dfe7891990dcaf674098100df2) | Web Tool | Web / X 搜索与结构化引用 | `dsh plugin --profile web add @liustack/modsearch` |

#### 插件功能重叠

开发选型先看扩展位置：

- TUI、Web Client Plugin 和协议驱动都能提供“另一套交互面”，但前两者处理呈现，协议驱动处理 wire contract 和 Agent 生命周期。
- 视觉能力可以是一个返回证据的 Tool，也可以是替换模型或文件能力的 Provider；前者接入简单，后者能改变整个产品的数据路径。
- 多宿主 package 要把 dsh adapter 与核心能力分开，避免把 dsh 的 Session、UI 或 Config 概念泄漏进其他宿主。
- 社区 Plugin 全部按 Host 代码审查；目录热度不能替代 package manifest、依赖、构建脚本和权限检查。
