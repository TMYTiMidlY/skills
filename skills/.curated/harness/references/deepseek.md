# DeepSeek Harness（dsh）运行时与插件生态

## 概览

[DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness/tree/47f943859bef60e4160492346772ded9b24f765a)（`dsh`）是 DeepSeek 开源的 agent harness。它内置并固定了 [`Cordis 4.0.0-rc.7`](https://github.com/cordiverse/cordis/tree/56b3d4f725681cf4556c1a8695a709cc3b6eed74)：模型适配、system prompt、工具、agent loop、会话、持久化、沙箱、审批、skills、subagent 与 Web UI 都由 Plugin 提供，并可通过配置组合或替换。

这套设计把扩展粒度推进到运行时各层；锁定源码的 [`packages/`](https://github.com/deepseek-ai/deepseek-harness/tree/47f943859bef60e4160492346772ded9b24f765a/packages) 下共有 226 个 `package.json`。与小核心、少量扩展事件的 harness 相比，它提供更完整的产品面和可替换接口，也带来更大的代码、配置和 Host（宿主进程）信任面。

本文的源码结论锁定 commit [`47f9438`](https://github.com/deepseek-ai/deepseek-harness/commit/47f943859bef60e4160492346772ded9b24f765a)，生态指标日期为 **2026-08-16**。该 checkout 根 `package.json` 的版本是 `0.1.0-rc.5`，同日 npm `latest` 已是 `0.1.0-rc.6`。

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
| **Plugin（插件模块）** | 实现一项运行时能力 | TypeScript / JavaScript module，导出 `apply(ctx, config)`，也可使用 object / class form |
| **Bundle（组合包）** | 向配置树贡献一层 Plugin 配置项 | npm / Git package；`package.json` 的 `dsh.bundle.patch` 指向 `cordis.patch.yml` |
| **Profile（运行配置）** | 按顺序组合多个 Bundle | `$DSH_HOME/profiles/<name>/package.json` 的 `dsh.profile.bundles`，再叠加本地 patch |
| **Agent preset（智能体预设）** | 决定一类 session 的 prompt、tools 与按 Agent 隔离的 services | 一个目录中的 `agent.cordis.yml` |

### Plugin 生命周期

[首个 Plugin 教程](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/user/develop/basic/index.md) 给出的最小形式是一个导出 `apply` 的 module：

```ts
import type { Context } from '@deepseek-ai/cordis'

export const name = 'hello-plugin'

export function apply(ctx: Context) {
  console.log('loaded')
}
```

消费 service 时通过 `inject` 声明依赖，Cordis 会在依赖可用后调用 `apply`。监听器、工具、计时器和其他注册应成为 `ctx.effect()` / `ctx.on()` 管理的 effect；Plugin 卸载或 HMR 替换时，框架会撤销这些注册。需要显式释放的资源由 effect 返回 disposer，配置则用 `@deepseek-ai/schemastery` schema 在加载期校验。

Waterfall event 允许 Plugin 观察、改写或截断请求和工具执行链。监听者必须调用 `next()` 才会继续分派；直接返回会终止后续 listener。

### Bundle 与 profile

[CLI reference](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/apps/cli/reference/README.md) 规定 Profile 从空树开始，按以下顺序叠加配置：

1. `dsh.profile.bundles` 中的 Bundle，按数组顺序；
2. Profile 自己的 `cordis.patch.yml`；
3. `$DSH_HOME/cordis.patch.yml`；
4. 命令行依次给出的 `--patch`。

后层覆盖前层；同一 row 的 `config` 是整块替换，不做 deep merge（深度合并）。

`dsh plugin --profile <name> <pnpm args...>` 在 Profile 目录中转发 pnpm 命令。依赖安装成功后，CLI 只会把声明 `dsh.bundle.patch` 的 package 加入 Bundle 栈；其他 package 保持普通 dependency，并提示它没有激活配置层。

```sh
dsh plugin --profile web add <npm-package-or-git-spec>
dsh plugin --profile web remove <package>
dsh --profile web --dump-config
```

Git source package 可以用 `prepare` 生成构建产物；pnpm 10+ 会先要求 Profile 的 `pnpm-workspace.yaml` 明确允许该构建脚本。该脚本的执行权限属于 Plugin 的安装期信任边界。

### Agent preset

内置预设位于锁定源码的 [`apps/cli/config/agent-presets/`](https://github.com/deepseek-ai/deepseek-harness/tree/47f943859bef60e4160492346772ded9b24f765a/apps/cli/config/agent-presets)：

- **`standard`**：完整 coding agent，包含 shell、文件、后台 jobs、goal、plan、todo、skills、web search、subagent 与 workflow。
- **`code`**：Code Mode。模型只直接看到 `run_code` 和自动生成的 TypeScript SDK，由代码组合多轮工具调用；其他工具也不能绕过这一入口直接执行。
- **`minimal`**：固定 system prompt，只保留 persistent Bash 与 `str_replace_editor`，不加载 compaction。
- **`cordis`**：在 standard 上增加运行时检查和临时动态 Plugin 工具；定义只保存在当前进程内，重启后消失。

四个预设共享 Host 进程，prompt 和 tool registrations 则落在各自的 preset scope。Agent 的解析链是 `agent → preset → global`。运行中的 session 继续使用启动时绑定的 preset generation（配置代次）；已经产生输出的 session 不能切换 preset，以免历史中的工具调用与新组合不一致。

## Agent 执行与会话

这一层说明 Agent 如何消费输入、调用模型和工具，以及这些行为如何进入可恢复的会话记录。

### Turn 与 step

一个 **step** 是一次模型请求及其触发的工具执行；一个 **turn** 可以包含多个 step。默认 loop 的主干是：

```text
turn/start
  claim inbox
  agent/pre-step
  step/start
  assemble prompt + tool schemas
  agent/request -> llm/stream
  assistant/chunk* -> assistant/message
  tool/call* -> tools/pre-execute -> tools/execute -> tools/post-execute -> tool/result*
  step/end
turn/end
```

`agent/pre-step`、`agent/request`、`llm/stream` 和三段 `tools/*` 是 waterfall extension points。新行为通过这些 seam 观察、改写或拦截执行路径；修改默认 agent loop 则会改变所有组合的主控制流。

### Session 日志与持久化

[`dsh-session`](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/subsystems/session.md) 把 session 定义为 typed `SessionEvent` 的 append-only log。模型历史从日志推导，不另存一份；system prompt、tool schemas 和模型 route 通过 `request/header` / `request/context` 记录。官方原则 **model-visible means logged** 要求进入模型请求的内容可以由日志重建。

默认 [`dsh-base` composition](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/packages/bundle/base/cordis.patch.yml) 使用 JSONL 持久化：

- 每个 session 一份 `.jsonl.zstd`，也可配置为 raw `.jsonl`；
- raw stream chunks 与连续 `seq` 都会保留；
- 当前 persistence seam 没有删除 API，文件会持续累积。

可替换的 SQLite backend 把每个 event 存为一行，默认使用 WAL，同样没有 session delete API。两个 backend 都会在加载时修复可判定的中断 turn，并拒绝无法安全解释或版本不兼容的日志；当前 pre-release 格式没有 migration 承诺。

Base Bundle 还挂载了默认 `:memory:` 的 SQLite **session query index**，但内容搜索默认关闭。它负责查询投影，不是默认的 session persistence backend。

## 外部接入

DeepSeek Harness 同时提供人机界面和程序化协议。它们驱动的是同一套 Plugin composition，但会暴露不同的交互能力。

### Web 与 headless

| 接入面 | 行为 | 限制 |
|---|---|---|
| Web UI | 提供会话、设置、trajectory 和 Plugin UI | 默认只监听 loopback |
| headless profile | 接收一个任务，等待 Agent idle，打印最后的 assistant 文本并返回退出码 | 不启动 HTTP server，也不提供交互式 UI |

Web UI 默认由 `dsh web` 启动；headless 则使用 `dsh --profile headless "<task>"`。两者都以调用命令时的目录作为默认 workspace root。

### ACP 与 SDK

接口细节分别见锁定版本的 [ACP server](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/packages/acp/acp/README.md)、[TypeScript SDK](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/packages/sdk/client/README.md) 和 [Python SDK](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/python/README.md)。

| 接入面 | 行为 | 主要限制 |
|---|---|---|
| ACP server | 通过 stdio JSON-RPC 创建新 Agent、发送文本 prompt、处理 permission、取消当前工作 | 单 workspace；不支持 resume、图片和完整 progress |
| TypeScript SDK | 由调用者指定命令，启动并驱动一个完整 runtime subprocess | 不负责定位随包 runtime；wire 无 per-prompt / mid-turn cancel |
| Python SDK | 提供高层 turns API、低层 JSON-RPC client 和可随包分发的 runtime carrier | 仍是 subprocess 架构，不把 loop 嵌入 Python 进程 |

TypeScript 高层类是 `DeepSeekHarness`，低层类是 `HarnessClient`。Python 发行包分为 `deepseek-harness-sdk` 和 `deepseek-harness-runtime-bin`。这些接口属于 agent SDK：外部 orchestrator 驱动完整 Harness，而不是直接调用模型 API。

## 扩展接口

模型、skills、MCP 和 subagent 都通过 Plugin 接入，但分别作用于 provider route、上下文说明、工具目录和任务委派。

### 模型接入

[模型配置指南](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/user/guide/providers.md)说明，Web Settings 可配置 DeepSeek，也可添加 Anthropic、OpenAI 等 catalog provider，或手填 OpenAI-compatible endpoint。

手工添加的 model 默认按 text-only 处理。视觉 model 需要在 `$DSH_HOME/settings.yaml` 为该 model 声明 `input: [text, image]`；该字段表达运维方对 endpoint 能力的判断，不会主动探测远端是否真的支持图片。

### Skills

[`dsh-skill-filesystem`](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/packages/skill/skill-filesystem/README.md) 的默认发现顺序：

1. `<projectRoot>/.dsh/skills`
2. `<projectRoot>/.agents/skills`
3. `customSkillDirs`
4. `<DSH_HOME>/skills`
5. `<DSH_AGENTS_HOME>/skills`，默认 `~/.agents/skills`

支持 `<name>/SKILL.md` 和单文件 `<name>.md`，只扫描一层，不递归发现嵌套 bundle。Frontmatter 的 `name`、`description` 必需，另认 `whenToUse`、`metadata`、`disable-model-invocation` 和 `user-invocable`。目录 watcher 负责 catalog 变化，skill body 则在每次加载时重新读取。

### MCP

内置 [`dsh-mcp-client`](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/packages/mcp/mcp-client/README.md) 支持 stdio 与 Streamable HTTP，只桥接 MCP **Tools**，不桥接 Resources 或 Prompts。模型侧命名：

```text
mcp__<serverName>__<rawName>
```

名字会规范化到 64 字符，并用确定性 hash 防碰撞。MCP server 由 Profile patch 显式挂载；默认 composition 不启动任何 server。

### Subagent

[`dsh-subagent`](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/packages/subagent/subagent/README.md) seam 可以同时注册多个 provider：

- `spawn` / `fork`：同进程 DSH child；
- `dsh-sdk` / ACP：另一个 DSH runtime；
- `codex`：启动 `codex app-server --stdio`，一 task 一临时 thread；
- `claude-code`：通过官方 Claude Agent SDK 启动本机 `claude`，一 task 一 query。

Codex / Claude Code provider 默认已装在 Host composition，但对应的 model-facing tool row 保持 disabled；只有启用该 row 的 Agent preset 才会暴露工具。两个 provider 都运行独立 child，只把最终文本带回 parent，不复制 parent 对话，也不传 reasoning、tool traffic、usage 或 diff。认证和原生配置仍由本机对应产品负责。

## 信任边界

Harness 同时包含 Host Plugin、工具执行沙箱、审批和遥测；这些机制约束的主体不同，不能合并理解成一个总沙箱。

### Plugin 与安装脚本

第三方 Plugin 在 Host 进程中运行，拥有启动 `dsh` 的用户权限。Tool approval 只参与工具执行，不约束 Plugin code。

Git dependency 的 `prepare` 同样是安装期本机代码。pnpm 的 `allowBuilds` 是对具体 package 执行构建脚本的授权；它发生在 Agent sandbox 之外。

`cordis` preset 创建的动态 Plugin 使用 vm 隔离 globals，但 [tool-cordis 文档](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/packages/extensions/tool-cordis/README.md) 明示 host-realm helper 可以造成逃逸，因此该 vm 不是安全边界。外部 Plugin 和动态 Plugin 都属于 Host 应用扩展，不是受工具审批约束的调用。

### Sandbox 与审批

默认 `workspace-write` 主要约束 shell / filesystem 的写入范围到 workspace 和 temp。[CLI reference](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/apps/cli/reference/README.md) 明示 reads、network access 和 process visibility 不受该策略封闭。

[Local sandbox](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/packages/sandbox/sandbox-local/README.md) 在 Linux 优先使用 bwrap，再尝试 Landlock；macOS 使用 Seatbelt；Windows 使用 restricted token 与 ACL。不可用时会 fail closed，但 Landlock 和 Windows backend 可能只报告 partial enforcement。

审批服务处理工具调用提出的权限请求。它不能撤销 Plugin 已经拥有的 Host 权限，也不约束 Plugin 安装脚本。MCP stdio server command 也是 sandbox 外的受信任可执行代码，因此默认 composition 不启用 MCP server。

### 遥测

Telemetry 默认关闭。[CLI reference](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/apps/cli/reference/README.md) 记录了 `FULL` 与 `FEEDBACK_ONLY` 两种显式启用模式；当前没有通用 redaction rule，导出内容可能包含消息文本、工具参数与结果以及 workspace path。

## 插件生态

官方目前提供发现约定和本地 Plugin inventory，社区则维护目录与市场前端。两者都不提供官方审核或真实安装量。

### 官方发现机制

[官方 README](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/README.md) 建议 Plugin 仓库添加 [`dsh-plugin`](https://github.com/topics/dsh-plugin) topic，没有提供官方 catalog、featured list、签名、审核或安装量。2026-08-16 的 [GitHub search](https://api.github.com/search/repositories?q=topic%3Adsh-plugin&sort=stars&order=desc&per_page=100) 返回约 4,182 个仓库，其中包含不具备 DSH Bundle manifest 的项目，因此本文没有直接采用 topic 的原始 star 排行。

Web Settings 的 [Plugin list](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/packages/client/ui-settings-plugin-inventory/README.md) 只读取当前 Loader tree，展示已安装 entry 的 module、config、enablement 和 Fiber phase；它不联网搜索、不安装，也不记录来源或历史。

[Plugin 发布教程](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/user/develop/basic/publish.md) 使用 `deepseek-harness/turtle-ui` 演示 Git 安装。2026-08-16 查询该公开仓库和 raw 文件均返回 404，因此它没有进入下面的 Plugin 样本。

### 社区目录与市场

[`awesome-dsh-plugin@c5f2879`](https://github.com/awesome-dsh-plugin/awesome-dsh-plugin/tree/c5f287967a26213ffdc77450db542e46899573e1) 声称只收录可由 `dsh plugin add` 安装并声明 `dsh.bundle` 的 Bundle。其 [2026-08-16 registry](https://awesome-dsh-plugin.com/plugins.json) 包含：

- 824 个条目，其中 286 个映射到 npm；
- UI 193、Tools 176、Development 101；
- Session 59、Notification 56、Workflow 52、Memory 43；
- Theme 35、Fun 33、Model 28、Skill 27、Market 21。

[`dsh-market@0a2959a`](https://github.com/dsh-market/dsh-market/tree/0a2959a7c7809e46f8ce39149f4e4710d2e0a047) 消费这份 registry，在 Web Settings 提供浏览、搜索、安装、更新和主题切换。它明确说明 “This repo is the market app, not the catalog” 和 “Listing ≠ endorsement”，因此目录收录和市场展示都不构成安全审计或 DeepSeek 背书。

### 指标口径与数据局限

下面的 stars 来自 `awesome-dsh-plugin.com/plugins.json` 的 2026-08-16 快照；npm downloads 使用 **2026-08-13 至 08-16** 的 point API。`N/A` 表示新包尚未被 downloads endpoint 收录或查询返回 404，不表示 0。

社区 registry 没有真实安装量。GitHub stars 会把上游项目既有关注度计入新增加的 DSH adapter，因此表格用“范围”区分 DSH 专用项目和多宿主集成；这是本次调研依据各仓库覆盖的 harness 所作的归类，不是 registry 自带字段。发布初期的 stars 与下载量只能描述当时的可见度，不能证明兼容性、留存、质量或生产使用。

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
| [`dsh-tianshu-tui`](https://github.com/huiliyi37/dsh-tianshu-tui/tree/650614f992b4fb1d2ca933ad64178dbb7fb0eb51) | DSH 专用 | 另一套 DSH terminal UI | 174 | [205](https://api.npmjs.org/downloads/point/2026-08-13:2026-08-16/%40huiliyi37%2Fdsh-tianshu-tui) | `dsh plugin --profile web add @huiliyi37/dsh-tianshu-tui` |
| [`dsh-browser`](https://github.com/Lum1104/dsh-browser/tree/06cdc2320f4de16a8e006e5dd4a9257f336401f2) | DSH 专用 | 通过 Chrome sidebar 操作浏览器 | 167 | Git-only | `dsh plugin --profile web add github:Lum1104/dsh-browser` |
| [`dsh-vision-router`](https://github.com/ysr666/dsh-vision-router/tree/ddfa6baf3f70ff9ddb2b5e7ff3a09d5840398d1f) | DSH 专用 | Keyless vision chain 与 OCR、crop、grounding、pixel tools | 155 | N/A | `dsh plugin --profile web add dsh-vision-router` |
| [`modsearch`](https://github.com/liustack/modsearch/tree/e1dba224b72651dfe7891990dcaf674098100df2) | 多宿主集成 | Web / X 搜索与抓取，返回结构化证据和引用 | 105 | [141](https://api.npmjs.org/downloads/point/2026-08-13:2026-08-16/%40liustack%2Fmodsearch) | `dsh plugin --profile web add @liustack/modsearch` |
| [`dsh-openpencil`](https://github.com/ZSeven-W/dsh-openpencil/tree/49b0417a6d6fe7a55056bb1a82d4c348a21a6ca6) | DSH 专用 | OpenPencil 设计预览与编辑 | 85 | [154](https://api.npmjs.org/downloads/point/2026-08-13:2026-08-16/%40zseven-w%2Fdsh-openpencil) | `dsh plugin --profile web add @zseven-w/dsh-openpencil` |

### 能力重叠

样本中有几组功能范围重叠：

- `dsh-web-ui-all` 与 `DSH-better-sidebar` 都扩展 Web 工作台；前者覆盖任务板、Git graph、移动端、pet 与 skin，后者集中在文件、terminal、Git 与 subagent。
- `modlens`、`dsh-vision-toolkit`、`dsh-vision-router` 都为文本模型增加视觉能力，但 provider、keyless 路径和工具粒度不同。
- `dsh-TUI` 与 `dsh-tianshu-tui` 都提供终端交互面。
- Hindsight 增加跨 session memory，`dsh-agent-teams` 增加多 Agent 编排；它们会改变运行时能力和 Host 代码面，不属于纯 UI 扩展。

从组合模型可以推得，同类 Plugin 叠加可能增加或争用 UI slots、tool schemas、prompt、watchers 和 Host code；具体结果取决于各 Bundle 插入或覆盖的配置项。当前仍是 developer preview，兼容性需要按具体 Plugin 版本和组合验证，不能由 stars 直接判断。
