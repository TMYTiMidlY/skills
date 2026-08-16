# DeepSeek Harness（dsh）运行时与插件生态

## 概览

[DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness/tree/47f943859bef60e4160492346772ded9b24f765a)（`dsh`）是 DeepSeek 开源的 agent harness。它建立在 [Cordis](https://github.com/cordiverse/cordis/tree/56b3d4f725681cf4556c1a8695a709cc3b6eed74) 上；Cordis 是 TypeScript 插件运行框架，负责 Plugin 生命周期、服务依赖、事件与 effect、作用域隔离、配置加载和热更新。dsh 借助这些机制，把模型适配、system prompt、工具、agent loop、会话、持久化、沙箱、审批、skills、subagent 与 Web UI 组合成可替换的 Plugin。

> **来源快照：** 源码结论锁定 commit [`47f9438`](https://github.com/deepseek-ai/deepseek-harness/commit/47f943859bef60e4160492346772ded9b24f765a)，其中内置 Cordis `4.0.0-rc.7`。该 checkout 根 `package.json` 的版本是 `0.1.0-rc.5`，同日 npm `latest` 已是 `0.1.0-rc.6`；生态指标日期为 **2026-08-16**。

## 版本、发布与运行方式

DeepSeek Harness 尚处于 developer preview（开发者预览）。[官方 README](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/README.md) 明示未来会有 breaking changes；[仓库约定](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/AGENTS.md) 也说明当前 session 格式没有兼容承诺。

| 项目 | 2026-08-16 状态 |
|---|---|
| 仓库与许可 | `deepseek-ai/deepseek-harness`；MIT |
| Git 历史 | 最早 commit 为 2026-06-10；[GitHub API](https://api.github.com/repos/deepseek-ai/deepseek-harness) 的 `created_at` 为 2026-08-13 |
| 公开发布 | commit `47f9438` 的标题为 `release: dsh@0.1.0-rc.5 & publish the dsh family publicly` |
| npm | [`@deepseek-ai/dsh`](https://registry.npmjs.org/%40deepseek-ai%2Fdsh) 首次发布于 2026-08-10；`latest` / `next` 为 `0.1.0-rc.6` |
| GitHub release / tag | 无 |
| 关注度快照 | 约 11.7 万 stars、1.1 万 forks |
| npm 下载快照 | [2026-08-13 至 08-16 共 81,093 次](https://api.npmjs.org/downloads/range/2026-08-13:2026-08-16/%40deepseek-ai%2Fdsh)，全部记在 08-13 |

GitHub stars 和 npm downloads 都是发布初期的短期信号；后者还存在新包统计延迟和批处理，不能据此推导留存、日活或生产部署量。

运行要求是 Node.js `^22.19.0 || >=24.0.0`。安装版直接启动 Web UI：

```sh
npx @deepseek-ai/dsh web
```

默认地址是 `http://127.0.0.1:3080`。源码 checkout 需先构建：

```sh
pnpm install
pnpm run build
pnpm dsh web
```

无 HTTP 服务的一次性任务使用 headless profile：

```sh
dsh --profile headless "summarize this workspace"
```

## 组合模型

官方 [架构文档](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/architecture.md) 用四个层级描述组合关系。Plugin 是能力实现，Bundle 是可安装配置层，Profile 是可启动运行配置，Agent preset 决定单个智能体看到的 prompt 与工具。

| 层 | 作用 | 物理形态 |
|---|---|---|
| **Plugin（插件模块）** | 实现一项运行时能力 | 由 Cordis 加载的 TypeScript / JavaScript module |
| **Bundle（组合包）** | 向运行时贡献一层 Plugin 配置 | 可通过 npm 或 Git 安装的 package |
| **Profile（运行配置）** | 组合多个 Bundle，形成一套可启动应用 | Harness home 下的 Bundle 清单与用户覆盖 |
| **Agent preset（智能体预设）** | 决定一类 Agent 的 prompt、tools 与工作方式 | 按 Agent 加载的一份 Cordis composition |

### Plugin 生命周期

Cordis 把 Plugin 当作能力和生命周期的共同边界。一个 Plugin 可以提供模型、工具、存储或 UI，也可以只提供审批、重试、压缩等策略；卸载 Plugin 时，它向运行时贡献的能力也应一起撤销。

Plugin 之间主要通过 Cordis 的 services 和 events 协作，而不是彼此写死依赖。这样，同一能力可以更换实现，策略也可以插入模型请求或工具执行流程，而无需修改 agent loop 本身。

最小 Plugin 是一个导出 `apply` 的 module：

```ts
import type { Context } from '@deepseek-ai/cordis'

export const name = 'hello-plugin'

export function apply(ctx: Context) {
  console.log('loaded')
}
```

`apply` 是 Plugin 挂载到运行时的入口，`ctx` 则让它访问 Cordis 提供的 services 和 events。实际 Plugin 会通过 `ctx` 注册工具、服务或监听器；Cordis 在 Plugin 卸载时统一撤销这些贡献。配置校验和显式资源清理等开发细节见[首个 Plugin 教程](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/user/develop/basic/index.md)。

### Bundle 与 profile

Bundle 是可安装的配置层，Profile 则决定一个 `dsh` 进程最终加载哪些 Bundle。官方 `web` 和 `headless` 都是 Profile；用户也可以创建自己的 Profile，把基础能力、界面和第三方扩展组合成另一套产品形态。

配置按“基础 Bundle → Profile / 用户覆盖 → 本次命令临时覆盖”的方向叠加，后面的配置可以替换前面同名的 Plugin 配置。这个模型让用户无需修改上游源码，也能替换模型 provider、工具、存储或 UI。

```sh
dsh plugin --profile web add <npm-package-or-git-spec>
dsh plugin --profile web remove <package>
dsh --profile web --dump-config
```

只有声明 DSH Bundle manifest 的 package 才会成为配置层；普通 dependency 即使安装成功，也不会自动改变运行时。

完整覆盖顺序、配置替换方式和 package 激活条件见 [CLI reference](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/apps/cli/reference/README.md)。

### Agent preset

dsh 内置[四种 Agent preset](https://github.com/deepseek-ai/deepseek-harness/tree/47f943859bef60e4160492346772ded9b24f765a/apps/cli/config/agent-presets)：

- **`standard`**：完整 coding agent，包含 shell、文件、后台 jobs、goal、plan、todo、skills、web search、subagent 与 workflow。
- **`code`**：Code Mode。模型只直接看到 `run_code` 和自动生成的 TypeScript SDK，由代码组合多轮工具调用；其他工具也不能绕过这一入口直接执行。
- **`minimal`**：固定 system prompt，只保留 persistent Bash 与 `str_replace_editor`，不加载 compaction。
- **`cordis`**：在 standard 上增加运行时检查和临时动态 Plugin 工具；定义只保存在当前进程内，重启后消失。

Agent preset 决定模型实际看到的 system prompt、tools 和工作方式。它与 Profile 的区别是：Profile 组装整个应用，preset 只组装某类 Agent。

Session 开始工作后不能随意切换 preset，因为历史中已经出现的工具调用和行为约束属于原来的能力集合；中途更换会让模型历史与当前可执行能力不一致。

## Agent 执行与会话

这一层说明 Agent 如何消费输入、调用模型和工具，以及这些行为如何进入可恢复的会话记录。

### Turn 与 step

一个 **turn** 是 Agent 对一批输入完成一次响应的过程；一个 **step** 是其中的一次模型请求及其后续工具调用。模型拿到工具结果后可能继续请求模型，因此一个 turn 可以包含多个 step。

Cordis Plugin 可以在 prompt 组装、模型请求、工具执行或 turn 结束等阶段增加策略。这里的重点不是某个事件名，而是默认 loop 只负责推进流程，审批、重试、压缩、超时和观测等横切行为可以放在 loop 外组合。

### Session 日志与持久化

[`dsh-session`](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/subsystems/session.md) 采用 event sourcing（事件溯源）：session 是一条只追加的事件日志，模型历史、Trajectory、恢复、分叉和回放都从同一份记录推导。官方原则 **model-visible means logged** 表示，进入模型上下文的信息也应能从日志重建。

默认持久化是每个 session 一份压缩 JSONL，便于保留完整事件流；SQLite backend 则适合把多个 session 集中到一个数据库。两者都处理崩溃后未完整结束的 turn，但当前仍是预发布格式，没有跨版本迁移承诺。

默认 backend 可在 [`dsh-base` composition](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/packages/bundle/base/cordis.patch.yml) 中核对。

## 外部接入

DeepSeek Harness 同时提供人机界面和程序化协议。它们驱动的是同一套 Plugin composition，但会暴露不同的交互能力。

### Web 与 headless

| 接入面 | 行为 | 限制 |
|---|---|---|
| Web UI | 提供会话、设置、trajectory 和 Plugin UI | 默认只监听 loopback |
| headless profile | 接收一个任务，等待 Agent idle，打印最后的 assistant 文本并返回退出码 | 不启动 HTTP server，也不提供交互式 UI |

Web UI 默认由 `dsh web` 启动；headless 则使用 `dsh --profile headless "<task>"`。两者都以调用命令时的目录作为默认 workspace root。

### ACP 与 SDK

| 接入面 | 行为 | 主要限制 |
|---|---|---|
| ACP server | 让编辑器或自动化客户端创建 Agent、发送 prompt、处理 permission 和取消工作 | 只覆盖基础自动化能力，不等同完整 Web UI |
| TypeScript SDK | 由调用者启动并驱动一个完整 runtime subprocess | 调用者负责选择和配置 runtime |
| Python SDK | 提供高层 turns API、低层 client 和可随包分发的 runtime | 仍通过 subprocess 驱动 Harness |

这些接口属于 agent SDK：外部 orchestrator 驱动完整 Harness，而不是直接调用模型 API。TypeScript 侧由调用者指定 runtime，Python 侧则把 client 与可分发 runtime 拆成两个 package。

具体接口分别见 [ACP server](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/packages/acp/acp/README.md)、[TypeScript SDK](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/packages/sdk/client/README.md) 和 [Python SDK](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/python/README.md)。

## 扩展接口

模型、skills、MCP 和 subagent 都通过 Plugin 接入，但分别作用于 provider route、上下文说明、工具目录和任务委派。

### 模型接入

Web Settings 可配置 DeepSeek，也可添加 Anthropic、OpenAI 等 catalog provider。Catalog provider 已经知道 endpoint、API 协议和模型列表，用户主要提供凭据；自定义 provider 则需要填写 provider id、base URL、协议、凭据和模型。

凭据写入 `$DSH_HOME/.credentials.yaml`，Settings 只保存对凭据的引用，因此 Web 页面读回配置时不会拿到明文 key。手工添加的 model 默认按 text-only 处理；如果 endpoint 支持图片，需要在 model metadata 中明确声明。dsh 不会自动探测一个自定义 endpoint 的多模态能力。

Provider 表单、模型能力声明和凭据行为见[模型配置指南](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/user/guide/providers.md)。

### Skills

Skills 为模型提供按需加载的工作方法和领域说明。[`dsh-skill-filesystem`](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/packages/skill/skill-filesystem/README.md) 同时读取项目级和用户级目录，并兼容 `.dsh/skills` 与通用的 `.agents/skills`；项目内容优先于用户内容，因此同一套 Harness 可以随 workspace 切换技能集合。

Skill 可以是 `<name>/SKILL.md` 目录 bundle，也可以是单个 Markdown 文件。Catalog 只把名称和描述暴露给模型，正文等到真正调用时再加载。

### MCP

MCP 用来把外部工具服务接入 dsh。内置 [`dsh-mcp-client`](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/packages/mcp/mcp-client/README.md) 支持本地进程和 HTTP，目前只桥接 **Tools**，不桥接 Resources 或 Prompts。

每个 MCP server 使用自己的命名空间，避免不同服务的同名工具冲突。Server 必须在 Profile 中显式配置，默认 composition 不启动任何 MCP server。

### Subagent

[`dsh-subagent`](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/packages/subagent/subagent/README.md) 统一了任务委派方式：provider 可以在当前 dsh 进程中创建 child，也可以启动另一套 dsh runtime，或把任务交给本机的 Codex / Claude Code。

本地 child 可以加入 dsh 自己的 session tree；外部产品则运行独立上下文，parent 通常只收到最终文本，不会自动获得对方的 reasoning、工具过程或产品会话。Codex / Claude Code 的认证和原生配置仍由各自产品负责。

## 信任边界

Harness 同时包含 Host Plugin、工具执行沙箱、审批和遥测；这些机制约束的主体不同，不能合并理解成一个总沙箱。

### Plugin 与安装脚本

第三方 Plugin 在 Host 进程中运行，拥有启动 `dsh` 的用户权限。Tool approval 只约束 Agent 发起的工具调用，不约束 Plugin 自己的代码。

Git package 的构建脚本也在安装期直接运行于本机。pnpm 要求显式允许构建，只是让这项授权可见，并没有把脚本放入 Agent sandbox。

`cordis` preset 还能创建临时动态 Plugin，但 [tool-cordis 文档](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/packages/extensions/tool-cordis/README.md) 明示其 vm 不是安全边界。无论来自 package 还是模型生成，Plugin 都应按 Host 应用扩展看待。

### Sandbox 与审批

默认 `workspace-write` 主要限制 shell 和 filesystem 工具的写入范围。[CLI reference](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/apps/cli/reference/README.md) 明示读取、网络访问和进程可见性并没有被同样封闭。

Local sandbox 会按操作系统选择可用的隔离机制，并在没有可用 backend 时拒绝无约束执行；部分平台只能提供不完整隔离。审批服务只处理工具提出的权限请求，不能撤销 Plugin 或安装脚本已经拥有的 Host 权限。

MCP stdio server 也是 Host 启动的可执行程序，因此默认 composition 不启用任何 server。

### 遥测

Telemetry 是把 Harness 运行记录导出到 OpenTelemetry collector，供集中观测或分析。默认关闭，不会因为启动 Web UI 或运行 Agent 自动上传会话。

显式启用时有两种范围：

- `FULL`：持续导出 session events；
- `FEEDBACK_ONLY`：只有用户记录反馈时，才上传相关的 session log 后缀。

当前没有通用 redaction rule（脱敏规则），因此导出内容可能包含消息文本、工具参数与结果以及 workspace path。`DSH_TELEMETRY_OTLP_URL` 用来选择 collector，`DSH_TELEMETRY_DISABLED` 可以强制关闭。完整环境变量和行为见 [CLI reference](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/apps/cli/reference/README.md)。

## 插件生态

官方目前提供发现约定和本地 Plugin inventory，社区则维护目录与市场前端。两者都不提供官方审核或真实安装量。

### 官方发现机制

[官方 README](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/README.md) 建议 Plugin 仓库添加 [`dsh-plugin`](https://github.com/topics/dsh-plugin) topic，没有提供官方 catalog、featured list、签名、审核或安装量。2026-08-16 的 [GitHub search](https://api.github.com/search/repositories?q=topic%3Adsh-plugin&sort=stars&order=desc&per_page=100) 返回约 4,182 个仓库，其中包含不具备 DSH Bundle manifest 的项目，因此本文没有直接采用 topic 的原始 star 排行。

Web Settings 的 [Plugin list](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/packages/client/ui-settings-plugin-inventory/README.md) 只显示当前部署已经加载的 Plugin；它不联网搜索或安装，因此不是应用市场。

> **核验备注：** [Plugin 发布教程](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/user/develop/basic/publish.md) 使用 `deepseek-harness/turtle-ui` 演示 Git 安装；2026-08-16 查询该公开仓库和 raw 文件均返回 404，因此它没有进入下面的 Plugin 样本。

### 社区目录与市场

[`awesome-dsh-plugin@c5f2879`](https://github.com/awesome-dsh-plugin/awesome-dsh-plugin/tree/c5f287967a26213ffdc77450db542e46899573e1) 声称只收录可由 `dsh plugin add` 安装并声明 `dsh.bundle` 的 Bundle。其 [2026-08-16 registry](https://awesome-dsh-plugin.com/plugins.json) 有 824 个条目，其中 286 个映射到 npm；数量主要集中在 UI、工具和开发辅助类。

[`dsh-market@0a2959a`](https://github.com/dsh-market/dsh-market/tree/0a2959a7c7809e46f8ce39149f4e4710d2e0a047) 消费这份 registry，在 Web Settings 提供浏览、搜索、安装、更新和主题切换。它明确说明 “This repo is the market app, not the catalog” 和 “Listing ≠ endorsement”，因此目录收录和市场展示都不构成安全审计或 DeepSeek 背书。

> **指标口径：** Stars 来自 `awesome-dsh-plugin.com/plugins.json` 的 2026-08-16 快照；npm downloads 使用 **2026-08-13 至 08-16** 的 point API。`N/A` 表示新包尚未被 downloads endpoint 收录或查询返回 404，不表示 0。社区 registry 没有真实安装量；“范围”是本次调研依据仓库覆盖的 harness 所作的归类，不是 registry 自带字段。发布初期指标只能描述可见度，不能证明兼容性、留存、质量或生产使用。

### 插件指标快照

| Plugin | 范围 | 用途 | Stars | npm downloads | 安装 |
|---|---|---|---:|---:|---|
| [`hindsight#coding-agents`](https://github.com/vectorize-io/hindsight/tree/396f63aafc9b618f04d446e2465cac95aa1cb426/hindsight-integrations/coding-agents) | 多宿主集成 | 长期项目记忆、自动 recall / retain | 20,008 | [371](https://api.npmjs.org/downloads/point/2026-08-13:2026-08-16/%40vectorize-io%2Fhindsight-coding-agents) | `dsh plugin --profile web add @vectorize-io/hindsight-coding-agents` |
| [`mirage#dsh`](https://github.com/strukto-ai/mirage/tree/14f83208abb2b92d9341a10dbaa4cb4786fe7eb2/typescript/packages/dsh) | 多宿主集成 | 用统一虚拟 filesystem 替换本地 FS / Bash provider，可挂 S3、Slack、Notion、Postgres 等 | 3,447 | N/A | `dsh plugin --profile web add @struktoai/mirage-dsh` |
| [`dsh-web-ui-all`](https://github.com/zhu1090093659/dsh-web-ui/tree/91a3ed4b72debf999ab7813de4f8f1320cd00ddc/packages/dsh-web-ui-all) | DSH 专用 | 任务板、Git graph、侧栏、移动端、pet、token 统计和 skin center | 2,775 | [1,203](https://api.npmjs.org/downloads/point/2026-08-13:2026-08-16/%40linxin666%2Fdsh-web-ui-all) | `dsh plugin --profile web add @linxin666/dsh-web-ui-all` |
| [`modlens`](https://github.com/liustack/modlens/tree/b489d7ad51255a8f98086f6ad0534d840505f747) | 多宿主集成 | 为文本模型提供 OCR、布局与视觉语义证据 | 1,963 | [1,717](https://api.npmjs.org/downloads/point/2026-08-13:2026-08-16/%40liustack%2Fmodlens) | `dsh plugin --profile web add @liustack/modlens` |
| [`DSH-better-sidebar`](https://github.com/omdsh-dev/DSH-better-sidebar/tree/ecebc978009362ae90c64d9f07d3c518d4651dd9) | DSH 专用 | 文件预览与编辑、terminal、Git、subagent 侧栏 | 1,305 | [832](https://api.npmjs.org/downloads/point/2026-08-13:2026-08-16/dsh-better-sidebar) | `dsh plugin --profile web add dsh-better-sidebar` |
| [`dsh-TUI`](https://github.com/ccch1mneyyy/dsh-TUI/tree/69f093122458e68515a6c3987898f1817d6beccf) | DSH 专用 | Claude Code 风格全屏 TUI | 1,293 | N/A | `dsh plugin --profile web add @deepseek-harness-tui/dsh-tui` |
| [`dsh-vision-toolkit`](https://github.com/Anionex/dsh-vision-toolkit/tree/29850a83871d4b7a7cc13e251420c5a440e2f69e) | DSH 专用 | 图片问答、长截图 OCR、UI 还原、grounding、pixel diff | 440 | N/A | `dsh plugin --profile web add @anionex/dsh-vision-toolkit` |
| [`dsh-agent-teams`](https://github.com/NanmiCoder/dsh-agent-teams/tree/2b1141248f34ee28870d2e39462c0dbefaa5ffdb) | DSH 专用 | 多 Agent team 与 workflow | 344 | N/A | `dsh plugin --profile web add @nanmicoder/dsh-agent-teams` |
| [`dsh-market`](https://github.com/dsh-market/dsh-market/tree/0a2959a7c7809e46f8ce39149f4e4710d2e0a047) | DSH 专用 | 社区 Plugin market UI | 301 | [86](https://api.npmjs.org/downloads/point/2026-08-13:2026-08-16/dshmarket) | `dsh plugin --profile web add dshmarket` |
| [`dsh-at-file`](https://github.com/omdsh-dev/dsh-at-file/tree/9c71e52c483ae589c7979b6ffc8b3a2cd5d8efa4) | DSH 专用 | Composer 中的 `@file` 搜索与附加 | 225 | Git-only | `dsh plugin --profile web add github:omdsh-dev/dsh-at-file` |
| [`dsh-tianshu-tui`](https://github.com/huiliyi37/dsh-tianshu-tui/tree/650614f992b4fb1d2ca933ad64178dbb7fb0eb51) | DSH 专用 | 完整终端会话工作区，并为视觉桥、TDD / 证据门、记忆和代码检索等 Harness 能力提供交互面 | 174 | [205](https://api.npmjs.org/downloads/point/2026-08-13:2026-08-16/%40huiliyi37%2Fdsh-tianshu-tui) | `dsh plugin --profile web add @huiliyi37/dsh-tianshu-tui` |
| [`dsh-browser`](https://github.com/Lum1104/dsh-browser/tree/06cdc2320f4de16a8e006e5dd4a9257f336401f2) | DSH 专用 | 通过 Chrome sidebar 操作浏览器 | 167 | Git-only | `dsh plugin --profile web add github:Lum1104/dsh-browser` |
| [`dsh-vision-router`](https://github.com/ysr666/dsh-vision-router/tree/ddfa6baf3f70ff9ddb2b5e7ff3a09d5840398d1f) | DSH 专用 | 默认免 Key、无 Python 的视觉链，支持多步 grounding、crop、OCR、pixel diff 和截图验证 | 155 | N/A | `dsh plugin --profile web add dsh-vision-router` |
| [`modsearch`](https://github.com/liustack/modsearch/tree/e1dba224b72651dfe7891990dcaf674098100df2) | 多宿主集成 | Web / X 搜索与抓取，返回结构化证据和引用 | 105 | [141](https://api.npmjs.org/downloads/point/2026-08-13:2026-08-16/%40liustack%2Fmodsearch) | `dsh plugin --profile web add @liustack/modsearch` |
| [`dsh-openpencil`](https://github.com/ZSeven-W/dsh-openpencil/tree/49b0417a6d6fe7a55056bb1a82d4c348a21a6ca6) | DSH 专用 | 在对话中预览、检查和编辑真实 `.op` 文档，提供交互画布、托管编辑器和 Agent 设计工具 | 85 | [154](https://api.npmjs.org/downloads/point/2026-08-13:2026-08-16/%40zseven-w%2Fdsh-openpencil) | `dsh plugin --profile web add @zseven-w/dsh-openpencil` |

### 能力重叠

- **终端界面**：`dsh-TUI` 主要复现 Claude Code 风格的全屏交互；`dsh-tianshu-tui` 更像完整终端工作区，包含会话恢复、分叉 / 回退、审批与提问面板，并承接视觉桥、验证门、记忆和代码检索等 Harness 能力。
- **视觉能力**：`modlens` 偏向把图片转成结构化证据，并可跨多种 Harness 使用；`dsh-vision-toolkit` 提供 UI 还原、长截图 OCR、grounding 等视觉工程 playbooks；`dsh-vision-router` 强调免 Key、无 Python 和自动路由，支持围绕原始像素反复 ground、crop、diff、修正和截图验证。
- **设计画布**：`dsh-openpencil` 不是普通 Web UI 装饰，而是把 OpenPencil 的 `.op` 文档、画布和编辑器接入 Agent 工作流，让模型操作可继续人工编辑的设计文件。

Stars 只能帮助发现候选，不能替代功能差异、Plugin 信任范围和版本兼容性的判断。
