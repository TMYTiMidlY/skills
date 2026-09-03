# DeepSeek Harness（dsh）Plugin 调研记录

本文件按日期记录 DSH 社区 Plugin 的检索与源码调研，保留调研时间、目标、候选仓库、证据边界、阶段结论和后续验证。运行 DSH、安装或卸载现成 Plugin 及判断权限边界见 [DeepSeek Harness 运行时](dsh.md)；Cordis 插件框架怎样组织插件、叠加配置、协作和清理，以及可复用的实现、测试与发布方法，见 [DeepSeek Harness Plugin 开发](dsh-dev.md)。这里保留调研过程，避免后来只剩脱离证据的选型结果。

## <a id="packaging-and-community"></a>2026-08-17 · 现成 Plugin 与社区生态

本次从官方发现约定和社区目录出发，汇总已经核实的社区扩展形态、安装入口和项目边界，供后续专题调研定位候选仓库。Cordis 插件框架的结构与扩展方式以开发篇为准，现成 Plugin 的安装使用与 Host 权限以运行时篇为准；本文只记录具体项目证据。

**调研时间：** 2026-08-17（Asia/Shanghai；部分来源于 2026-08-26 复核）

**调研目标：**

- 核对官方 topic、社区目录和插件市场等项目发现入口。
- 汇总桌面应用、终端界面和插件市场，并区分插件为模型增加的操作、替换的底层服务以及新增的界面与协作流程。
- 记录各项目的安装方式、宿主范围和权限边界，为后续专题调研建立候选集合。

> **证据边界：** 社区仓库以 2026-08-17 的快照为基线，后续复核项在对应来源旁标明日期。项目链接固定到相应 commit；目录收录和市场热度只作为发现与维护信号，不代替源码审查或真实验收。

### <a id="community-discovery"></a>社区项目的发现入口

官方建议 Plugin 仓库添加 [`dsh-plugin`](https://github.com/topics/dsh-plugin) topic（GitHub 仓库话题标签）。本文件把该 topic、社区目录、市场数据和已知项目之间的引用当作候选发现入口，再回到固定 commit 核对源码；被目录或市场收录不表示 package 已通过安全审查或安装验收。Plugin 作者怎样提供 topic、README 和安装信息，见开发篇的[社区发现信息](dsh-dev.md#plugin-community-discovery)。

> 来源：[官方 README 的 `dsh-plugin` 发现约定](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/README.md#L37-L45)；[GitHub topic 的分类和发现作用](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/classifying-your-repository-with-topics?apiVersion=2022-11-28)（2026-08-26 查阅）。

### 桌面应用与终端界面

公开 Git 历史能看到生态扩展出现得很快：ModLens 在官方 npm 发布快照当晚加入 [DSH Plugin 接入](https://github.com/liustack/modlens/commit/2860d82e2fb99a3989844dfe6ead0fce2cb14d6f)，dsh-market 在次日留下[首个市场提交](https://github.com/dsh-market/dsh-market/commit/11bb90573c291b356e7ab8cba1b11a0111ddfe6b)，Desktop 工作区随后出现[首个明确提交](https://github.com/anywhere-labs/deepseek-harness-desktop/commit/4e3eb911fdb9df60df61043358818e34c95d2e16)。这些时间只能说明公开提交节奏，不能证明作者实际从何时开始开发。

| 项目 | 形态 | 使用方式 | 环境边界 |
|---|---|---|---|
| [`DeepSeek Harness Desktop`](https://github.com/anywhere-labs/deepseek-harness-desktop/tree/8734c2cd21db2b31e670c24d9361acdaf14b7e3c) | Electron 桌面应用与 DSH Desktop Plugin | 下载 Windows 或 macOS 安装包 | Electron 开启 `runAsNode` 提供 Node 执行环境，并打包 pnpm 与固定 DSH 依赖；无需系统 Node.js、pnpm 或 DSH |
| [`dsh-TUI`](https://github.com/ccch1mneyyy/dsh-TUI/tree/c9d89664a1fc1b3faee6899add0c040b40fdfc2b) | 独立 Profile 上的全屏终端界面 | `dsh plugin --profile dsh-tui add @deepseek-harness-tui/dsh-tui`，再运行 `dsh-tui` | 纯 Plugin 挂载、不修改核心，但仍要求官方 `dsh` CLI、终端 TTY 和 pnpm |

Desktop 把官方 Web UI、后台服务和 Plugin 系统封进原生安装包；dsh-TUI 则只替换操作界面，底层仍由官方 dsh 运行。两者都属于社区项目，不是 DeepSeek 官方产品。订阅登录和两种 TUI 的进一步对照见本文件的[订阅登录与交互界面](#2026-08-26-subscription-auth-surfaces)。

> 来源：[Desktop 的安装入口](https://github.com/anywhere-labs/deepseek-harness-desktop/blob/8734c2cd21db2b31e670c24d9361acdaf14b7e3c/README.md#L1-L38)；[Electron `runAsNode` 与固定 pnpm 依赖](https://github.com/anywhere-labs/deepseek-harness-desktop/blob/8734c2cd21db2b31e670c24d9361acdaf14b7e3c/dsh-plugin-desktop/package.json#L200-L250)；[应用可执行文件与打包 pnpm 的运行入口](https://github.com/anywhere-labs/deepseek-harness-desktop/blob/8734c2cd21db2b31e670c24d9361acdaf14b7e3c/dsh-plugin-desktop/src/main.ts#L190-L202)；[dsh-TUI 的纯 Plugin 形态与前置条件](https://github.com/ccch1mneyyy/dsh-TUI/blob/c9d89664a1fc1b3faee6899add0c040b40fdfc2b/README.md#L17-L73)。

### <a id="plugin-market"></a>插件市场与主题

[`awesome-dsh-plugin`](https://github.com/awesome-dsh-plugin/awesome-dsh-plugin/tree/c5f287967a26213ffdc77450db542e46899573e1) 维护社区目录数据；[`dsh-market`](https://github.com/dsh-market/dsh-market/tree/1696a52ed291b97048112c802d547599de9a5547) 读取这份目录，在 Web Settings 提供浏览、搜索、安装、更新和诊断界面：

```sh
dsh plugin --profile web add dshmarket
```

市场支持主题即时激活、互斥切换并记住选择，也支持通过 Profile 的补充配置 `cordis.patch.yml` 热停用或启用部分 Plugin；其余变更会显示重启入口。Bundle 成员变化仍遵循运行时篇说明的 [Profile 启动边界](dsh.md#runtime-composition)。

目录收录、市场展示和热度用于发现项目；来源、依赖、权限和代码审查负责安全判断。

> 来源：[主题即时切换、热开关与必要时重启](https://github.com/dsh-market/dsh-market/blob/1696a52ed291b97048112c802d547599de9a5547/README.md#L12-L50)。

### 社区插件的功能与接入位置

一个社区 Plugin 可能同时改动 DSH 的多个位置：给模型增加可主动请求执行的操作，替换文件读写、命令执行或记忆等底层服务，也可以增加 Web 界面与协作流程。这些位置不互斥，下表因此分别记录用户得到的功能和插件实际改动的部分；同一项目的“改动位置”可以包含多项。

DSH 源码把“模型可以主动请求执行的单项操作”称为 Tool，把“在同一调用接口后提供某种具体实现”的组件称为 Provider。这两个名称用于对应源码接口；它们的实现关系见开发篇的[模型可调用操作与底层服务](dsh-dev.md#tool-and-providers)。

| Plugin | 用户得到的功能 | 在 DSH 中改动的位置 | 适配范围 | 安装 |
|---|---|---|---|---|
| [`dsh-agent-teams`](https://github.com/NanmiCoder/dsh-agent-teams/tree/2b1141248f34ee28870d2e39462c0dbefaa5ffdb) | 在当前会话组建子 Agent 团队，按角色和任务依赖分工，再汇总成员结果 | 子 Agent 协作、任务状态和 Web 管理界面 | 仅 DSH | `dsh plugin --profile web add @nanmicoder/dsh-agent-teams` |
| [`dsh-openpencil`](https://github.com/ZSeven-W/dsh-openpencil/tree/49b0417a6d6fe7a55056bb1a82d4c348a21a6ca6) | 在对话中创建、预览和编辑 `.op` 设计画布 | 模型可调用的设计操作、对话预览和 Web 编辑器 | 仅 DSH | `dsh plugin --profile web add @zseven-w/dsh-openpencil` |
| [`hindsight`](https://github.com/vectorize-io/hindsight/tree/396f63aafc9b618f04d446e2465cac95aa1cb426/hindsight-integrations/coding-agents) | 跨会话保留项目记忆，并在后续任务中自动召回和追加内容 | 会话前后的记忆读写流程 | DSH 及其他 coding agent | `dsh plugin --profile web add @vectorize-io/hindsight-coding-agents` |
| [`mirage`](https://github.com/strukto-ai/mirage/tree/14f83208abb2b92d9341a10dbaa4cb4786fe7eb2/typescript/packages/dsh) | 通过统一虚拟工作区访问挂载的数据源，不再局限于宿主机本地文件 | 替换文件读写和命令执行的底层实现 | DSH 及其他 agent 运行环境 | `dsh plugin --profile web add @struktoai/mirage-dsh` |
| [`modlens`](https://github.com/liustack/modlens/tree/2b71582435ff34a548efbefb74178ed133659ccb) | 粘贴或提供图片后，取得 OCR、布局和视觉语义证据 | 读图操作、Web 粘贴处理和纯文本模型的视觉包装 | DSH 及其他 agent 运行环境 | `dsh plugin --profile web add @liustack/modlens` |
| [`modsearch`](https://github.com/liustack/modsearch/tree/e1dba224b72651dfe7891990dcaf674098100df2) | Web / X 搜索与带来源的结构化结果 | 模型可调用的联网搜索操作 | DSH 及其他 agent 运行环境 | `dsh plugin --profile web add @liustack/modsearch` |

ModLens 展示了同一个 Plugin 为什么会出现在多个位置：它注册 `modlens_read_image` 读图操作，处理 Web 界面粘贴的图片，还可以为已确认的纯文本模型生成视觉包装条目。这些改动都通过 Plugin 接入，不需要修改模型本身。

> 来源：[ModLens 的 DSH 安装、粘贴识图和模型包装](https://github.com/liustack/modlens/blob/2b71582435ff34a548efbefb74178ed133659ccb/README.zh-CN.md#L29-L76)。

### 社区插件的使用入口、适配范围与运行权限

评估上面的生态项目时，核对四个方面：

- 用户从桌面应用、终端界面、Web 页面还是外部协议进入该功能。
- 插件增加了模型可调用的操作，替换了底层服务，还是增加了界面或协作流程。
- 安装包只用于 DSH，还是同时适配其他 agent 运行环境。
- 安装内容是否包含在 DSH 主进程中运行的 Node 入口、构建脚本或额外子进程。

模型可调用操作和底层服务的实现见开发篇的[模型可调用操作与底层服务](dsh-dev.md#tool-and-providers)，外部协议和 Web 界面见[协议与界面 Plugin](dsh-dev.md#protocol-and-ui-plugins)，完整权限模型见运行时篇的[信任边界](dsh.md#trust-boundaries)。目录热度和安装成功都不能替代这些检查。

Plugin 卸载、热替换和失败状态的语义见开发篇的[实现 Plugin 模块](dsh-dev.md#plugin-runtime)。

## <a id="2026-08-26-subscription-auth-surfaces"></a>2026-08-26 · 订阅登录与交互界面

本次从 DSH 官方的模型与凭据实现出发，检索社区中提供订阅登录、模型路由以及 Web / TUI 交互界面的 Plugin。本文记录截至本次源码快照已经核实的信息，并给出贴合当前目标的初步路线；最终采用方案仍需真实账号端到端验证后决定。

**调研时间：** 2026-08-26（Asia/Shanghai）

**调研目标：**

- 核对 DSH 官方 Authorization、Credentials 与 `llm-pi-ai` 的现有边界。
- 搜索能让 DSH 使用 Codex、Claude、Copilot、Kimi、OpenRouter、xAI 等订阅或 OAuth 凭据的社区 Plugin。
- 解释 Web 与 TUI 登录入口、模型服务激活、凭据保存与刷新、模型适配器复用和模型目录之间的关系。
- 找到一条尽量复用官方后端、避免重复维护各家 OAuth 的 Web 实现路线。

下文保留三个源码名称便于对照实现：“登录流程”对应 flow，“凭据记录”对应 credential record，“模型适配器”对应 Adapter。交互界面只负责向人展示 URL、device code 或输入框；登录、凭据和模型请求分别由后面三层处理。

### <a id="2026-08-26-official-chain"></a>DSH 官方 OAuth 登录链路

DSH `0.1.1-rc.2` 已经把 Pi 的模型服务登录接进官方后端，组件分工如下：

```text
Web / TUI 登录界面
        ↓
@deepseek-ai/dsh-authorization
通用登录流程：列出、说明、开始、取消、等待输入
        ↓
@deepseek-ai/dsh-llm-pi-ai
按 Pi 模型目录注册各服务的登录流程，调用 Models.login()
        ↓
Pi OAuth / device-code
        ↓
DSH 凭据记录
保存 OAuth 授权结果（grant）、串行修改、刷新 Token
        ↓
官方 PiAiAdapter 模型适配器
把凭据用于模型请求
```

官方已经实现通用登录流程、Pi `Models.login()` 调用、OAuth 授权结果到凭据记录的映射、并发刷新锁，以及凭据到 `PiAiAdapter` 模型请求的衔接。当时固定的 Pi 模型目录可为 `openai-codex`、`anthropic`、`github-copilot`、`kimi-coding`、`openrouter`、`xai` 注册 OAuth 登录流程。

默认 Web 产品缺少最后的交互层：基础配置组合（composition）没有完整挂载这套服务，浏览器也没有用于展示提示、URL、device code、文本、敏感信息输入、选项和取消状态的通信协议与界面。官方 Models 页面同样没有登录按钮，也不会在登录后自动激活不含 API Key 的模型服务配置。因此“官方只支持 API Key”只适用于当时的默认界面，不适用于已经存在的后端能力。

> 来源：[Pi 登录流程注册与 `Models.login()`](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/llm/llm-pi-ai/src/login.ts#L120-L159)、[凭据记录与刷新](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/llm/llm-pi-ai/src/auth.ts#L117-L160)、[`llm-pi-ai` 对 Authorization 的可选注入](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/llm/llm-pi-ai/src/index.ts#L205-L214)、[官方记录的浏览器交互边界](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/.agents/notes/implemented/architecture/2026-08-13-credential-records-and-authorization-flows.md#L52-L60)。

> Radius 属于动态模型服务，不在 DSH 当时遍历的内置静态目录中，因此不能只补前端就自动出现；这和上述六类静态模型服务是不同边界。

### <a id="2026-08-26-repository-snapshot"></a>仓库活跃度快照

下表的版本对应本次阅读的源码快照；stars 和最新 GitHub Actions 状态在 2026-08-26 重新查询。stars 只表示关注度，不代表架构质量或安全审计；“无 Actions”也不等于没有本地测试。

| 仓库 | 版本 | Stars | 主要范围 | 最新 GitHub Actions |
|---|---:|---:|---|---|
| [deepseek-ai/deepseek-harness](https://github.com/deepseek-ai/deepseek-harness/tree/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e) | `0.1.1-rc.2` | 196419 | 官方基线 | — |
| [V1ki/dsh-plugin-subscriptions](https://github.com/V1ki/dsh-plugin-subscriptions/tree/08b9b7cc30e72e8eedd559ac01af9fc576157453) | `0.5.2` | 276 | 多订阅 Web Plugin | 无 Actions |
| [weijiafu14/pi2dsh](https://github.com/weijiafu14/pi2dsh/tree/bf8e74fd8146fb6cf74895c536792e086650fa5e) | `0.19.0` | 164 | Pi 生态兼容层 | `CI` failure |
| [Yan-Zero/dsh-codex](https://github.com/Yan-Zero/dsh-codex/tree/e3e54e206f7c829503c7e6eed378643ba0416792) | `0.2.5` | 48 | Codex 专用 Plugin | `Publish to npm` success |
| [WSL043/dsh-codex-subscription](https://github.com/WSL043/dsh-codex-subscription/tree/c8899beac69c40bcfc850c9dc497fd042806f879) | `1.8.0` | 23 | Codex 产品化 Plugin | `Release` success |
| [XMoon/dsh-pi-tui](https://github.com/XMoon/dsh-pi-tui/tree/76c8c96df3457720f59a9e450687f280d875e9f5) | `0.3.4` | 13 | 基于 Pi TUI 的终端界面 | `CI` success |
| [ziyou979/dsh-llm-oauth](https://github.com/ziyou979/dsh-llm-oauth/tree/362312e5d01cccb5fc74fda130875d500dbaf78c) | `0.2.0` | 7 | 多模型服务 OAuth Plugin | 无 Actions |
| [edge-sky/dsh-oauth-adapter](https://github.com/edge-sky/dsh-oauth-adapter/tree/559a757351093b42b695c36f77d81f8cbfe05a03) | `0.1.1-rc.11` | 3 | 官方登录流程的 Web 交互层 | `Running Copilot cloud agent` success |
| [yhyfhgs/dsh-model-hub](https://github.com/yhyfhgs/dsh-model-hub/tree/f55ac188ef24f9604e77ed127a025962c8a37c2f) | `0.2.2` | 1 | 模型服务与模型管理套件 | 无 Actions |
| [ccch1mneyyy/dsh-TUI](https://github.com/ccch1mneyyy/dsh-TUI/tree/5f7d2fb9974d4575953795ced9e7feae2b241d0e) | `0.9.3` | 2573 | 基于 Ink / React 的终端界面与生态 | `Star History` success |
| [ccch1mneyyy/dsh-auth](https://github.com/ccch1mneyyy/dsh-auth/tree/fba02bcf7fb57e3d9885f73882d5835ccdf526c4) | `0.1.0` | 1 | `dsh-TUI` 携带的订阅认证 Plugin | 无 Actions |

> `pi2dsh` 的“最新 CI failure”只记录 GitHub 当时最后一条 workflow 结果，不能单独推导整个项目不可用；`dsh-TUI` 的最新成功任务名是 `Star History`，同样不构成构建与测试通过的证据。

### <a id="2026-08-26-auth-matrix"></a>社区 Plugin 的凭据与模型请求归属

比较登录类 Plugin 时，需要分别确认交互界面、登录流程、凭据保存与刷新、模型请求适配由谁维护。一个项目有登录按钮，不代表它复用了官方的后续链路。

| 项目 | 交互入口 | 登录流程 | 凭据保存与刷新 | 模型请求适配 | 与官方链路的关系 |
|---|---|---|---|---|---|
| `dsh-plugin-subscriptions` | 自建 Web Settings | 自行实现 Codex、Claude、Grok、Copilot | 独立 `auth.json`，原子写入并设为 `0600` | 四套自建模型适配器与协议转换 | 只使用 DSH Plugin 接口 |
| `pi2dsh` | 自带 `/login`，也把登录接入官方 Authorization 接口 | Pi 模型服务 / Extension 自己的 OAuth | pi2dsh 自有存储；DSH 凭据记录只写 `managedBy: pi2dsh` 标记 | pi2dsh 的 Pi Plugin 兼容层 | 使用官方 Authorization 协议，凭据和模型请求仍归 pi2dsh |
| `dsh-codex` | 自建 Web、CLI、TUI | 直接调用 Pi `Models.login()` | 独立文件，跨进程锁与原子写 | 复用官方 `PiAiAdapter` | 复用请求适配层 |
| `dsh-codex-subscription` | 自建 Web RPC 与登录协调器 | 直接调用 Pi OAuth | 使用 DSH 凭据服务的自定义凭据引用 | 复用官方 `PiAiAdapter` | 复用凭据服务和请求适配层，不使用官方登录流程与凭据记录 |
| `dsh-llm-oauth` | 自建 Web、HTTP API、`/oauth` | 直接调用 Pi OAuth | 独立 `pi-ai-oauth.json` | 自建 `OAuthPiAiAdapter` | 复用 Pi 模型目录与 OAuth，不使用 DSH 官方登录后端 |
| `dsh-model-hub` | 自建并替换整套 Models UI | 官方模型服务调用官方流程；另写 `qwen-code`、`codex` 流程 | 官方路由使用官方凭据记录；自建路由使用独立记录范围 | 官方路由使用官方适配器；自建路由使用插件适配器 | 混合使用官方与自建链路 |
| `dsh-oauth-adapter` | 独立 Web Settings 页面与 WebSocket 桥接 | 直接调用官方登录流程 | 官方凭据记录 | 官方 `PiAiAdapter` | 官方链路保持完整，Plugin 只增加 Web 交互界面 |
| `dsh-pi-tui` | TUI `/login` | 动态读取并调用全部已注册官方登录流程 | 官方凭据记录 | 对应模型服务的官方适配器 | 官方链路保持完整，Plugin 只增加 TUI 交互界面 |
| `dsh-TUI` + `dsh-auth` | Ink TUI `/auth` 与模型服务向导 | `dsh-auth` 自行提供订阅登录 | 由 `dsh-auth` 管理 | `dsh-auth` 注册自己的模型路由 | 默认不走官方 `dsh-authorization` 登录链 |

从复用深度看，可以分成以下几组：

| 复用层级 | 项目 | 含义 |
|---|---|---|
| 官方全链路，只增加交互界面 | `dsh-oauth-adapter`、`dsh-pi-tui` | 登录流程、凭据记录、刷新和模型适配器均归官方 |
| 官方与自建链路并存 | `dsh-model-hub` | 官方模型路由复用全链路，插件自带路由另写全链路 |
| 只接入官方 Authorization 接口 | `pi2dsh` | 官方界面可以启动它的登录流程，凭据和模型请求仍归 pi2dsh |
| 只复用 Pi 登录或官方模型适配器 | `dsh-codex`、`dsh-codex-subscription`、`dsh-llm-oauth` | 登录、存储或模型适配仍有部分由 Plugin 自己维护 |
| 自行维护完整订阅链路 | `dsh-plugin-subscriptions`、`dsh-TUI` / `dsh-auth` | 模型服务登录、凭据和请求适配均由社区项目维护 |

### <a id="2026-08-26-plugin-details"></a>社区 OAuth Plugin 的实现方式

下面按具体项目展开上表，重点记录它们复用或自建了哪一层，以及由此产生的凭据存储、路由冲突与维护范围。

#### <a id="2026-08-26-multi-provider-web"></a>`dsh-plugin-subscriptions` 与 `dsh-llm-oauth`

`dsh-plugin-subscriptions` 覆盖 Codex、Claude、Grok 和 GitHub Copilot，带独立设置页、实时模型目录、额度展示、代理、reasoning effort、Fast Mode、Vision、X Search、图片和视频生成。OAuth、Token 刷新、四套模型适配器和协议转换全部由项目自行维护，因此上游协议变化需要社区项目自行跟进。

`dsh-llm-oauth` 覆盖 `xai`、`github-copilot`、`openai-codex`、`anthropic`、`openrouter`、`kimi-coding`，直接复用 Pi 的模型目录和 OAuth。它仍然自建凭据存储、HTTP/UI 和 LLM 适配器；与官方 `llm-pi-ai` 同时启用相同模型服务 id 时，会触发重复适配器冲突。其 README 所述“官方只支持 API Key”已经落后于 DSH `0.1.1-rc.2`；源码使用普通 `writeFile`，没有显式设置 `0600` 权限或原子替换，主账号 Token 会因此面临文件权限与写入中断风险。

#### <a id="2026-08-26-codex-plugins"></a>`dsh-codex` 与 `dsh-codex-subscription`

`dsh-codex` 与 `dsh-codex-subscription` 都直接调用 Pi OAuth，并复用官方 `PiAiAdapter`，但各自维护登录入口和凭据格式。

| 项目 | 凭据 | 产品能力 |
|---|---|---|
| `dsh-codex` | 独立 `$DSH_HOME/.openai-codex-auth.json`，带锁、原子写和权限检查 | Web / CLI / TUI 登录、模型筛选、Search、Vision、`gpt-image-2`、Fast Mode、额度、Responses 上下文压缩、WebSocket 上下文复用 |
| `dsh-codex-subscription` | DSH 凭据引用，自定义序列化格式与登录协调器 | 浏览器/device-code 登录、额度分类与安全重置、Search、图片生成/编辑、Fast Mode、模型级上下文、诊断与 Windows 安装流程 |

这两个项目都围绕 Codex 提供完整产品功能，范围不是为官方全部 OAuth 服务提供通用交互界面。如果扩展到其他模型服务，需要同时扩展凭据格式、模型元数据、额度显示和 Codex 专属功能中与供应方耦合的部分。

#### <a id="2026-08-26-bridges-and-model-hub"></a>`pi2dsh` 与 `dsh-model-hub`

`pi2dsh` 是 Pi Plugin ABI 到 DSH 的通用兼容层，不只是登录 Plugin。它能运行未修改的 Pi Plugin，并把 Pi 模型服务的登录流程注册到 DSH Authorization 接口；真实 Token 仍由 pi2dsh 自己保存，DSH 凭据记录只承担“由 pi2dsh 管理”的状态标记。这说明官方交互界面可以启动第三方登录流程，但登录后的凭据和模型请求并未交给官方 `llm-pi-ai`。

`dsh-model-hub` 会对官方模型服务调用 `authorization.begin()`，使用官方凭据记录 key，并写入空的无 API Key 配置来激活官方路由；同时它替换官方 Models 页面、模型选择器和目录管理，还自建 `qwen-code` 与 `codex` 模型路由。

`qwen-code` 当时不在 Pi 内置模型目录中，手工添加的模型服务又只能使用 API Key，因此需要自建登录流程、凭据记录和模型适配器。自建 `codex` 则与官方 `openai-codex` 重复，用于自行控制 Fast Mode、模型元数据和 OAuth 错误行为；这条路由需要重复维护 OAuth 常量、Token 刷新、模型表和适配器，而且当时只声明文本输入。

> 来源：[Model Hub 为目录外 OAuth 模型服务自建适配器的原因](https://github.com/yhyfhgs/dsh-model-hub/blob/f55ac188ef24f9604e77ed127a025962c8a37c2f/src/provider/native/catalog.ts#L1-L16)、[自建 `codex` 与官方 `openai-codex` 并存](https://github.com/yhyfhgs/dsh-model-hub/blob/f55ac188ef24f9604e77ed127a025962c8a37c2f/src/provider/native/catalog.ts#L220-L280)、[官方模型服务的 Authorization 桥接](https://github.com/yhyfhgs/dsh-model-hub/blob/f55ac188ef24f9604e77ed127a025962c8a37c2f/src/auth/bridge.ts#L337-L366)。

#### <a id="2026-08-26-official-surfaces"></a>`dsh-oauth-adapter` 与 `dsh-pi-tui`

`dsh-oauth-adapter` 不保存 Token、不实现刷新，也不注册自己的 LLM 适配器。它挂载缺失的 Authorization 服务，通过 WebSocket 把官方登录提示传到独立的 Web Settings 页面，调用 `authorization.begin()`，成功后写入不含 API Key 的模型服务配置。当时服务端和客户端都只列出 `openai-codex`、`github-copilot`，尚未动态展示官方其余登录流程。

> 来源：[Web 桥接调用官方登录流程](https://github.com/edge-sky/dsh-oauth-adapter/blob/559a757351093b42b695c36f77d81f8cbfe05a03/src/index.ts#L323-L438)、[缺失服务时挂载官方 Authorization](https://github.com/edge-sky/dsh-oauth-adapter/blob/559a757351093b42b695c36f77d81f8cbfe05a03/src/authorization-fallback.ts#L13-L26)、[硬编码模型服务表](https://github.com/edge-sky/dsh-oauth-adapter/blob/559a757351093b42b695c36f77d81f8cbfe05a03/src/protocol.ts#L8-L17)。

`dsh-pi-tui` 在终端中动态读取官方登录流程，把引用凭据和模型服务原生 OAuth 合并进 `/login`，处理提示、URL、device code、文本、敏感信息输入、选项、取消和失败，登录成功后创建最小的无 API Key 配置。它不实现任何模型服务 OAuth、Token 存储或 LLM 适配器，因此可以直接观察通用交互界面如何复用官方后端。

### <a id="2026-08-26-tui"></a>`dsh-pi-tui` 与 `dsh-TUI`

`dsh-pi-tui` 与 `dsh-TUI` 都是运行在 DSH 之上的第三方终端界面，共用 DSH 的模型、模型可调用操作和 Session 能力。两者是相互独立的社区项目，没有 GitHub fork 或共同 commit 历史；UI 内核、扩展体系和登录路线也不同：

| 属性 | `dsh-pi-tui` | `dsh-TUI` |
|---|---|---|
| UI 内核 | 内置并修改 Moonshot/Kimi Code 的 `pi-tui` 源码 | 自行移植的 Ink / React 界面渲染引擎 |
| npm 包 | `@xmoon76/dsh-pi-tui` | `@deepseek-harness-tui/dsh-tui` |
| Profile | `pi-tui` | `dsh-tui` |
| 登录路线 | DSH 官方 `dsh-authorization` | 捆绑社区 `@deepseek-harness-tui/dsh-auth` |
| 登录服务范围 | 随已注册的官方登录流程动态变化 | 由 `dsh-auth` 自己维护 |
| 产品侧重点 | Pi 风格交互、Focus、任务与 lineage、官方登录流程 | Claude Code 风格、主题与状态栏、VS Code 和自有插件生态 |
| Stars（2026-08-26） | 13 | 2573 |

Moonshot AI 是 Kimi 的开发公司；它维护的 `pi-tui` 源码公开放在 Kimi Code 单一仓库（monorepo）内，没有作为独立 package 公开。`dsh-pi-tui` 把这份源码纳入自己的仓库并针对 DSH 修改；项目本身仍是 XMoon 的第三方项目，不属于 Moonshot 官方。

### <a id="2026-08-26-boundaries"></a>验证范围与使用限制

本轮调研能支持源码归属和实现路线比较，但不能代替真实账号、供应商条款与发布版本兼容性验证。具体限制如下：

- 本次结论来自固定 commit 的源码、README、依赖、提交历史和仓库状态；尚未用六类真实账号逐一完成登录、刷新和模型请求的端到端（E2E）验证。
- 技术可行不等于供应商允许第三方消费订阅凭据。Codex 社区插件已经明确提示账号限制或封禁风险，真实验证不应默认使用无法承受损失的主账号。
- Claude 在第三方 harness 中可能进入 extra usage，而不是单纯消耗 Pro/Max 固定额度；OpenRouter OAuth 实质上会签发从账户余额扣费的 API Key。两者不能只因出现 OAuth 按钮就归类为固定订阅。
- DSH 当时固定 `@earendil-works/pi-ai 0.82.1`，不会自动追随 Pi 后续的模型服务与模型变化。
- 同一模型服务 id 同时被官方和社区适配器声明时，会产生模型目录或适配器冲突；安装多个订阅 Plugin 前需要检查每条模型路由由谁注册。
- 官方 Models 卡片内部没有通用 Plugin 界面插槽。新增独立 Settings 页面可以保留官方 Models 页面；直接往官方卡片中插入按钮，则通常需要替换整页。
- stars、版本和 Actions 结果会变化；它们用于判断关注度与维护信号，不替代源码和真实 E2E。

因此，下面的实现路线只回答“在当时源码上怎样减少重复实现”，账号可用性、计费与合规性仍需要独立验证。

### <a id="2026-08-26-target-route"></a>官方 OAuth Web 界面的实现路线

本轮实现路线以三个条件为约束：DSH Web 使用官方已经迁入的 Pi OAuth 后端，覆盖尽可能多的订阅模型服务，社区 Plugin 不再单独保存 Token、刷新凭据或转换模型协议。

按这些约束，Web 交互层以 `dsh-oauth-adapter` 为基线，再结合其他项目中可复用的部分：

```text
dsh-oauth-adapter 的 Web / WebSocket 交互桥接
        +
dsh-pi-tui 的动态登录流程枚举与完整输入处理
        +
dsh-model-hub 的凭据记录 key 绑定与无 API Key 配置激活
        ↓
官方 dsh-authorization
        ↓
官方 llm-pi-ai + Pi Models.login()
        ↓
官方凭据记录 / Token 刷新 / PiAiAdapter
```

具体改动保持在 Web 交互层：

- 用 `authorization.list()` / `describe()` 动态读取登录流程，不在服务端和客户端重复硬编码 Codex、Copilot。
- 只展示凭据记录范围属于 `llm-pi-ai` 且登录方法包含 `oauth` 的条目。
- 浏览器按通用类型渲染提示、URL、device code、文本、敏感信息输入、选项和取消状态。
- 登录成功后写入空的模型服务配置 `{}`，继续使用官方模型路由、凭据记录、Token 刷新和模型适配器。
- 不复制 Pi OAuth client、client id、Token 文件、刷新函数或模型协议。
- `qwen-code`、Radius 等官方静态目录之外的模型服务作为独立后续范围，不放进第一版官方 OAuth 交互界面。

现成方案按目标区分：

| 使用目标 | 初步候选 |
|---|---|
| 立即使用多订阅 Web 功能，不要求官方后端 | `dsh-plugin-subscriptions` |
| 只需要完整 Codex 产品体验 | `dsh-codex-subscription` 或 `dsh-codex` |
| 在终端验证官方登录流程 | `dsh-pi-tui` |
| 开发通用官方 Web 登录界面 | `dsh-oauth-adapter` 为基线，参考 `dsh-pi-tui` 与 `dsh-model-hub` |
| 运行 Pi Plugin 生态 | `pi2dsh` |
| 使用成熟终端产品与自有生态 | `dsh-TUI` |

这仍是阶段性路线，实现前还需要完成：官方六类登录流程的枚举测试、每种交互输入的无凭据单元测试、少量非主账号的真实登录与刷新基本测试、登录后的模型请求验证，以及供应商条款风险确认。

## <a id="2026-08-27-installed-source-followup"></a>2026-08-27 · Model Hub 安装与源码复核

本轮在 DSH `0.1.1-rc.2` 的 Web Profile 中实际安装 `@fhxgs/dsh-model-hub@0.2.3`，并以仓库 commit `6897374e90b2f383a797e6597c011e076594f3e7` 复核主进程入口、浏览器客户端、OAuth、凭据绑定、适配器注册与基本验证清单。安装、配置合成结果导出和 Web 启动成功；没有使用真实订阅账号完成外部 OAuth 与模型请求，因此下面结论只包含运行时装载验证和源码归属判断，不代表账号端到端验证。

### <a id="model-hub-codex-routes"></a>Model Hub 的 Codex 路由

Model Hub 同时保留 DSH 官方 `openai-codex` 和插件内建 `codex`，页面搜索 `codex` 时会同时显示这两个模型路由：

| 模型路由 key | OAuth 与凭据归属 | 模型请求归属 | 页面含义 |
|---|---|---|---|
| `openai-codex` | DSH 官方 `llm-pi-ai` 注册登录流程，使用 `recordKeyFor()` 对应的官方凭据记录 | 官方 `PiAiAdapter` 与 Pi 模型目录 | DSH 的官方路由；Model Hub 只负责启动 `authorization.begin()`、显示状态与激活无 API Key 配置 |
| `codex` | Model Hub 自己实现 authorization-code + PKCE，写入 `model-hub` 范围的独立凭据记录 | 插件自己的 `NativeOAuthAdapter` 与静态模型表 | 显示名为 **OpenAI Codex** 的内建路由；OAuth 授权结果、凭据、模型表与错误行为均由插件维护 |

内建 `codex` 的 client id、OpenAI OAuth endpoints、scope 和非标准参数取自同版本 pi-ai 的公开实现。实际登录仍由插件自己的 OAuth 骨架执行，`createNativeFlow()` 写入插件凭据记录，`NativeOAuthAdapter` 再使用该记录发起模型请求。因此，常量来自官方依赖，并不改变登录流程、Token 生命周期和模型请求的归属。

> 来源：[内建 `codex` 与官方 `openai-codex` 并存及独立归属](https://github.com/yhyfhgs/dsh-model-hub/blob/6897374e90b2f383a797e6597c011e076594f3e7/src/provider/native/catalog.ts#L269-L410)、[官方与 Model Hub 的两套凭据绑定](https://github.com/yhyfhgs/dsh-model-hub/blob/6897374e90b2f383a797e6597c011e076594f3e7/src/provider/bindings.ts#L69-L82)、[插件自建登录流程与凭据记录范围](https://github.com/yhyfhgs/dsh-model-hub/blob/6897374e90b2f383a797e6597c011e076594f3e7/src/provider/native/flows.ts#L43-L60)、[自建适配器与登录流程注册](https://github.com/yhyfhgs/dsh-model-hub/blob/6897374e90b2f383a797e6597c011e076594f3e7/src/provider/native/registration.ts#L69-L77)、[Codex 路由的人工基本验证清单](https://github.com/yhyfhgs/dsh-model-hub/blob/6897374e90b2f383a797e6597c011e076594f3e7/scripts/smoke-p1.zh.md#L55-L68)。

### Model Hub Web 页面的本机地址限制

Model Hub 的浏览器端在建立连接前读取 `ctx.connection.isLoopback`。页面地址不是 `localhost`、`127/8` 或 `[::1]` 这些本机回环地址时，它只注册说明页，不调用 `/model-hub`。反向代理可以改变发往 DSH 的 HTTP 请求头，但不能改变浏览器地址栏中的公网主机名。这个限制由 Model Hub 客户端自己判断，与 DSH 主进程是否接受代理后的 Host/Origin 是两层独立检查。

> 来源：[非本机回环地址时客户端降级且不建立连接](https://github.com/yhyfhgs/dsh-model-hub/blob/6897374e90b2f383a797e6597c011e076594f3e7/src/client/index.ts#L334-L358)、[DSH 客户端以页面主机名计算 `isLoopback`](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/client/connection/src/client/index.ts#L80-L89)。

### Model Hub 与官方 OAuth 链路的边界

若所有官方 OAuth 模型服务都要共用官方登录流程、凭据记录、Token 刷新与模型适配器，Model Hub 可复用的是模型服务目录、凭据记录 key 绑定、无 API Key 配置激活和 UI 组织。其内建 `codex` 仍是插件自建链路，不能作为官方链路已被复用的证据。判断归属时需要查看模型路由 key，显示名称“OpenAI Codex”不足以区分两条路由。

## <a id="2026-08-27-file-transfer-artifacts"></a>2026-08-27 · 浏览器文件传输与产物交付

本轮从 DSH `0.1.1-rc.2` 的官方文件链路出发，核对“模型能读取工作区文件但 Web 不能拖入普通文件”和“模型生成文件后 Web 没有浏览器下载链接”这两个现象，并对社区中的文件上传、路径定位、工作区浏览、产物预览和聊天下载 Plugin 做源码审计。这里把模型输入模态、Agent 文件工具、浏览器上传和浏览器下载分开记录；四者共享“文件”一词，但不是同一能力。

**调研时间：** 2026-08-27（Asia/Shanghai）

**调研目标：**

- 解释 Sol 能用文件工具读取文件，却不能通过 DSH Web 接收任意文件拖入的原因。
- 核对内置 Produced 文件行和模型回复中的文件引用最终执行什么动作。
- 搜索并固定社区中与文件拖入、工作区读取、原生打开、产物预览和下载有关的仓库。
- 比较每个 Plugin 的字节落点、模型可见形式、会话持久性、下载覆盖、容量边界、路径约束和 `0.1.1-rc.2` 兼容性。

> **证据边界：** 官方 DSH 源码固定到 `deepseek-ai/deepseek-harness@b150a551`，该 checkout 的 lock 解析 pi-ai `0.82.1`；本轮实际运行的 npm 安装树则因依赖范围解析到 pi-ai `0.84.3`。下文 Sol metadata 属于后一个运行时快照，不是前一个源码 checkout 的固定目录。社区仓库固定到下表 commit；十一份仓库均以完整、非 shallow、非 partial clone 复核，HEAD 与远端默认分支一致、对象完整且工作区干净。源码审计不能替代安装后的真实 Web 组合测试；本轮只对少数无需安装依赖的 Host 测试做了本地执行。Stars 是 2026-08-27 的 GitHub API 快照，只表示当时关注度。

### <a id="file-transfer-official-chain"></a>官方文件链路

Sol 的“读取文件”来自 Agent 的文件系统 Tool：文件先存在于 Host 或当前工作区，模型再请求 `read` 等操作。Provider 输入是另一层；本轮运行时解析到的 pi-ai `v0.84.3` 为 `openai-codex/gpt-5.6-sol` 声明的输入只有文本和图片，而 DSH 的浏览器 prompt wire 也只接受 `text` 与 `image`。因此，模型能读工作区文件不等于模型 API 或 Web composer 已实现任意文件传输。

DSH Web 的拖拽入口明确接到图片链路：document drop 把 `DataTransfer.files` 交给 `onAddImages()`，browser draft attachment 固定为 `kind: 'image'`，Host prompt part 只有文本和图片两个分支。普通文件在到达模型或文件工具前就被 composer 的图片 MIME 门禁拒绝。

> 来源：[DSH b150 的 pi-ai `0.82.1` lock](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/pnpm-lock.yaml#L5535-L5543)、[pi-ai `v0.84.3` 中 `openai-codex/gpt-5.6-sol` 的 text/image metadata](https://github.com/earendil-works/pi/blob/v0.84.3/packages/ai/scripts/generate-models.ts#L2680-L2689)、[drop 转入 `onAddImages`](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/client/ui-attachment/src/client/ComposerAttachments.tsx#L60-L66)、[composer 的图片 MIME 门禁](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/client/ui-conversation/src/client/skeleton/InputBar.tsx#L510-L535)、[浏览器 draft 固定为 image](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/client/ui-conversation/src/client/service.ts#L62-L69)、[Host prompt wire 的 text/image union](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/host/apiproxy/src/api/sessions.ts#L90-L94)。

模型回复侧已经有文件引用提示：成功创建或修改文件后，应在最终回复用 Markdown 行内代码写准确路径或唯一 basename。Produced 行不依赖模型是否照做，而是从成功 mutation Tool 的 `locations` 推导路径。两种入口最终都调用 `openFile()`，再转到 Host 的 `workspaces.openPath()`；Produced chip 本身是 `<button>`，不是带 `href` 或 `download` 的链接。

> 来源：[模型文件引用提示](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/client/ui-deliverables/src/index.ts#L14-L27)、[Produced chip 调 `openFile`](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/client/ui-deliverables/src/client/ProducedFiles.tsx#L115-L139)、[对话把路径转给 `workspaces.openPath`](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/client/ui-conversation/src/client/apply.ts#L391-L403)。

`host.openPath` 操作的是运行 DSH 的 Host 桌面；它不是把字节返回浏览器。当前官方 Downloads API 只有 Session 日志 ZIP，没有工作区文件下载。当 Host description 报告 `canOpenPath:false` 时，Produced 行不会显示“在文件夹中显示”，文件 chip 也没有浏览器下载兜底；本轮现场正好命中这个条件。

> 来源：[Downloads API 只有 Session 日志](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/host/apiproxy/src/api/downloads.ts#L10-L24)、[Produced 行按 loopback 与 `canOpenPath` 决定 Host 操作](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/client/ui-deliverables/src/client/ProducedFiles.tsx#L49-L78)。

### <a id="file-transfer-repository-snapshot"></a>仓库快照

下表按本轮源码快照记录版本、Stars 和验证面。“测试”只表示仓库里存在的测试或本轮实际执行结果，不代表真实 DSH Web 组合已经通过。

| 仓库 | 版本 / commit | Stars | 主要范围 | 测试与发布信号 |
|---|---|---:|---|---|
| [`dsh-file-upload`](https://github.com/HongMing-Huang/dsh-file-upload/tree/ce4ca943da592be36a784a5648d36a600aeda136) | `0.5.2` / `ce4ca94` | 20 | 拖入、粘贴、选择、文档转换 | 4 个测试文件；Node 22/24 CI；npm 最新仍是 `0.4.3` |
| [`dsh-drag-and-drop`](https://github.com/akiracod/dsh-drag-and-drop/tree/c20646ad6d4ee4c4a0ef12163a074716e17a7ba5) | `0.2.0` / `c20646a` | 7 | 同机文件路径定位 | 9 个测试文件；无 CI |
| [`dsh-file`](https://github.com/chengzhi43/dsh-file/tree/1a94663da7eb81e31701b342a1e51f58616bd04d) | `0.1.3` / `1a94663` | 6 | 工作区浏览与编辑 | 5 个测试文件；无 CI；源码 clone 不含运行所需 `dist` |
| [`dsh-attachments`](https://github.com/WJZ-P/dsh-attachments/tree/c94ec8b38a126b8ab919dd3849cd88560f0063a6) | package `dsh-attachment@1.0.1` / `c94ec8b` | 5 | 文件与目录拖入、历史附件 | Linux/Windows CI；Host/package 测试 9 项通过 |
| [`dsh-file-uploads`](https://github.com/l541402398/dsh-file-uploads/tree/3ea46e1583eac426cc34e191ea811e71b0c8347e) | `1.0.0` / `3ea46e1` | 4 | 文件选择与全局上传目录 | 无 CI；Host 测试 7 项通过；未发布 npm |
| [`dsh-workspace-files`](https://github.com/sqfcyily/dsh-workspace-files/tree/68a322f9884cfa4ec5552e3116ab769c97ec9c47) | `0.1.1` / `68a322f` | 4 | 工作区文本与 Git diff | 无行为测试；workflow 只负责 Release |
| [`dsh-file-fix`](https://github.com/re-ITRT/dsh-file-fix/tree/64ab40fe6a2bc91ea50ca57d67137ec6a7410d00) | `0.4.0` / `64ab40f` | 2 | 附件库、读取 Tool、输入附件下载 | 无测试、无 CI；npm 与审计 SHA 一致 |
| [`dsh-artifact-library`](https://github.com/wyq183/dsh-artifact-library/tree/ad3c6ee6fadba7a7de7a9eb3e842994259be24c8) | manifest `0.3.0` / `ad3c6ee` | 2 | 产物索引、搜索与管理页 | 无测试、无 CI；`v0.3.1` 至 `v0.3.3` 同指该 SHA |
| [`dsh-rich-artifacts`](https://github.com/Inkotake/dsh-rich-artifacts/tree/44f39793ce383330c781b38893d516e50cfab397) | `0.1.0` / `44f3979` | 1 | 模型发布聊天产物与下载卡 | 1 个 store 测试；无 CI；未发布 npm |
| [`dsh-file-pane`](https://github.com/trungtaottn/dsh-file-pane/tree/f6e211f71e8ddad8cfe8ddf3a738b8831d6310cb) | manifest `0.1.0` / `f6e211f` | 1 | 远程浏览器只读预览 | 4 个测试文件与 CI；README 自称 `v0.3.0`，与 manifest/tag 不一致 |
| [`dsh-reveal-files`](https://github.com/yumm007/dsh-reveal-files/tree/328917ff210ed2ec7f674dda386f2de39fd59bfb) | `0.1.0` / `328917f` | 0 | Host 原生打开、定位与终端 | 无测试、无 CI |

GitHub API 的 `created_at` 显示，这十一份仓库均创建于 2026-08-14 至 2026-08-25；部分项目继承的完整 Git 历史更早。最高 20 Stars 仍只是早期关注度快照，不能替代安全、兼容和持久性审计。

### <a id="file-transfer-input-plugins"></a>浏览器文件输入 Plugin

输入类实现可分成两种：把浏览器 `File` 的字节复制到 Host，或者不复制字节、只尝试恢复原文件路径。模型最终仍要通过路径或额外 Tool 读取内容。

| Plugin | 浏览器入口与字节落点 | 模型如何取得文件 | 下载覆盖 | 关键边界与 rc.2 状态 |
|---|---|---|---|---|
| `dsh-file-uploads` | 只有 picker；raw body 流式写入全局 `$DSH_HOME/uploads` | submit 时把 Host 绝对路径作为普通文本写进用户消息 | Settings 中可下载输入文件；无逐消息附件下载；无产出下载 | Host/Origin/Sec-Fetch-Site fence、100 MiB 单文件、1 GiB 总量、临时文件、fsync、同名编号与流式下载均有实现；所有 Session 共享可枚举目录，且没有 TTL、GC 或 Session 删除联动，手动删除可使旧消息路径失效。`0.1.1-rc.2` 静态接口匹配，但没有真实组合测试 |
| `dsh-attachments` | document capture drop；普通文件和目录流式写入私有 object store，提交时复制到 `.deepseek-harness/attachments/` | 把工作区副本路径和附件 metadata 追加进用户消息 | 历史普通文件可按 Session 下载；目录不能下载；无产出下载 | 无单文件、数量或总容量上限；路由无 Host/Origin fence；工作区复制缺少 realpath/no-follow。rc.2 的 `conversation.input.attachments` 已被官方 single occupant 占用，插件同优先级注册会冲突，组件 props 也不符合当前 Slot owner，静态判定不能直接使用 |
| `dsh-file-fix` | drop、paste、picker；FileReader 转 base64，经 Typert 写入内容寻址附件库 | pre-step 注入 attachment id；`read_attachment` 读文本，`place_attachment` 复制二进制到工作区 | 历史输入附件有下载；无产出下载 | 50 MiB 单文件在 Host 强制，20 文件/200 MiB 批量限制主要靠客户端；上传和下载全量缓冲。下载、Remote 与 Tool 没有 Session ownership；直接 Node 写入有 symlink/TOCTOU；自定义 `filefix/files` 不是官方已知且不能写 `ignorable`，rc.2 恢复会拒绝该事件；无测试/CI |
| `dsh-file-upload` | picker、drop、paste、目录展开；整包缓冲后写入 `<cwd>/.dsh-uploads/<sessionId>` | 发送 Host 绝对路径，并引导调用 `read_document`；图片可走官方 `read_image` 或外部视觉描述 | 无输入下载；无产出下载 | DELETE 只做字符串前缀校验，`<storage>/../../victim` 可越界删除，属于 Critical；route 绕过标准 `/api` fence，只有可伪造 Host regex；无总容量，上传和转换放大内存。text-only 路由可能在没有逐文件确认时把图片发到自动发现的 OpenAI-compatible 视觉端点；`read_document` 的 renderer 只向模型展示两行；client scoped event、错误状态、相对路径和清理器还有确定性缺陷。仓库 0.5.2 无构建产物，npm 0.4.3 又是旧代码，peer rc.6 不覆盖 rc.2 |
| `dsh-drag-and-drop` | 不复制普通文件；从 URI 或 Host 搜索恢复绝对路径，必要时比较 metadata、结构与摘要；纯图片仍走官方图片链 | 发送绝对路径普通文本，模型再自行调用文件 Tool | 无输入或产出下载 | 只适合同一文件系统命名空间；远程浏览器、容器、WSL 或异构 OS 会失配。裸 locator route 无 trust fence，roots、candidates 与 phase 由客户端控制，可做路径 oracle 和 I/O DoS；唯一 name+size/name 候选可能错认，同一 pending 队列还可跨 Session 发送 |

> 来源：[`dsh-file-uploads` 的 trust fence、原子写入和下载](https://github.com/l541402398/dsh-file-uploads/blob/3ea46e1583eac426cc34e191ea811e71b0c8347e/index.js#L109-L221)、[`dsh-file-uploads` 的配额与流式响应](https://github.com/l541402398/dsh-file-uploads/blob/3ea46e1583eac426cc34e191ea811e71b0c8347e/index.js#L304-L425)、[`dsh-attachments` 的上传、工作区复制和下载](https://github.com/WJZ-P/dsh-attachments/blob/c94ec8b38a126b8ab919dd3849cd88560f0063a6/src/index.mjs#L202-L254)、[`dsh-attachments` 的文件 route](https://github.com/WJZ-P/dsh-attachments/blob/c94ec8b38a126b8ab919dd3849cd88560f0063a6/src/index.mjs#L283-L460)、[`dsh-file-fix` 的模型注入](https://github.com/re-ITRT/dsh-file-fix/blob/64ab40fe6a2bc91ea50ca57d67137ec6a7410d00/src/attach.ts#L25-L31)、[`dsh-file-fix` 的无 Session 下载 route](https://github.com/re-ITRT/dsh-file-fix/blob/64ab40fe6a2bc91ea50ca57d67137ec6a7410d00/src/http.ts#L23-L59)、[`dsh-file-upload` 的缓冲上传与落盘](https://github.com/HongMing-Huang/dsh-file-upload/blob/ce4ca943da592be36a784a5648d36a600aeda136/src/upload.ts#L117-L230)、[`dsh-file-upload` 的 DELETE 校验](https://github.com/HongMing-Huang/dsh-file-upload/blob/ce4ca943da592be36a784a5648d36a600aeda136/src/upload.ts#L241-L277)、[`dsh-file-upload` 的视觉端点自动发现与传输](https://github.com/HongMing-Huang/dsh-file-upload/blob/ce4ca943da592be36a784a5648d36a600aeda136/src/vision.ts#L60-L121)、[`dsh-drag-and-drop` 的客户端权威搜索范围](https://github.com/akiracod/dsh-drag-and-drop/blob/c20646ad6d4ee4c4a0ef12163a074716e17a7ba5/src/locator.ts#L79-L109)。

这些项目说明“文件路径进入 prompt”与“附件字节成为持久 Session 输入”仍是两个不同状态。`dsh-file-uploads`、`dsh-file-upload` 和 `dsh-attachments` 主要依赖文件继续存在于 Host；`dsh-file-fix` 另建附件库和读取 Tool，但其自定义事件与官方 Session 格式没有完整扩展面。

### <a id="file-transfer-workspace-plugins"></a>工作区与产物界面 Plugin

工作区浏览器能让人看到文件，不一定提供下载；Host 原生打开动作也不会把字节送到远程浏览器。下表按真实传输动作区分这些界面。

| Plugin | 用户界面与字节通道 | 对模型的影响 | 路径与兼容边界 |
|---|---|---|---|
| `dsh-reveal-files` | 覆盖 Produced 行，提供 Open、Copy、Reveal、Terminal；动作发生在 DSH Host，没有浏览器字节响应 | 不注册 Tool、prompt 或 Session event | exact route 绕过标准 fence，absolute path 无工作区约束；macOS AppleScript 和 Windows cmd 的多层字符串构造形成潜在命令注入链，但本轮未在对应平台验证可用 payload。无桌面或 `canOpenPath:false` 的 Host 上不能构成可靠交付 |
| `dsh-workspace-files` | `conversation.view` 中列目录、预览最多 512 KiB 文本和 Git diff；二进制不返回；没有 download route | 没有模型 Tool、prompt 或 event | `root` 由 query 提供且不与 Session 绑定，`confine()` 只相对调用者声称的 root 做词法前缀检查；传 `/` 或跟随 symlink 可读任意 Host 文本文件。README 的“不跟随 symlink”与实现冲突 |
| `dsh-file` | 工作区树、文本编辑、Markdown 预览；唯一 download 是主题 JSON，不是工作区文件 | 浏览器直接 Node FS 写入，不走 DSH fs policy、approval、`fs/observed` 或 Session log | `setRoot()` 接受任意绝对目录且无 Session 参数，随后可读写删除；最终 symlink 仍会跟随，Markdown 未 sanitize 可形成同源 stored XSS。源码 clone 不含 package 入口所需 `dist` |
| `dsh-artifact-library` | 管理页登记路径，`GET /ext/artifacts/:id/file` 会流式返回原文件，但没有 attachment disposition、下载按钮或可靠文件名 | 注册 12 个模型 Tool 与 system prompt；store 变化本身不是 Session event | 可由 HTTP 或模型登记任意 Host path，再用裸 Node FS 索引或读取，绕过 DSH fs policy；无 root、ownership、Origin 或 MIME active-content 防护。自动采集不识别 rc.2 标准 `file_path`，只看 tool/call 且不核对成功 result |
| `dsh-file-pane` | 远程地址下用 `priority:-1` 接管 Produced chip，跳转 `/browser/?path=...`，提供代码、Markdown、DOCX、PDF 和图片只读预览；`raw=1` 仍以 inline response 返回，没有下载按钮或 attachment response | 不改变模型输入或 Tool | 初次 lexical check 会拒绝 root 外绝对路径和 `..`，但 realpath 后只做裸 `real.startsWith(root)`，缺少路径分隔符边界；指向 prefix-sibling（如 `<root>-secret`）的 symlink 可以逃逸。`/browser` 没有 Host/Origin、身份或 Session ownership，默认 root 为 Host HOME；`raw=1` 在大小判断前仍把完整文件读入内存。只在非 loopback 浏览器接管 Produced；loopback 页面仍走内置 Host opener |

> 来源：[`dsh-reveal-files` 的路径解析和原生命令](https://github.com/yumm007/dsh-reveal-files/blob/328917ff210ed2ec7f674dda386f2de39fd59bfb/lib/index.js#L38-L146)、[`dsh-reveal-files` 的裸 route](https://github.com/yumm007/dsh-reveal-files/blob/328917ff210ed2ec7f674dda386f2de39fd59bfb/lib/index.js#L154-L251)、[`dsh-workspace-files` 的 caller-supplied root](https://github.com/sqfcyily/dsh-workspace-files/blob/68a322f9884cfa4ec5552e3116ab769c97ec9c47/lib/index.js#L206-L230)、[`dsh-file` 的 path 解析与文件操作](https://github.com/chengzhi43/dsh-file/blob/1a94663da7eb81e31701b342a1e51f58616bd04d/src/index.ts#L59-L193)、[`dsh-file` 的无约束 `setRoot`](https://github.com/chengzhi43/dsh-file/blob/1a94663da7eb81e31701b342a1e51f58616bd04d/src/index.ts#L280-L297)、[`dsh-artifact-library` 的任意路径登记与文件流](https://github.com/wyq183/dsh-artifact-library/blob/ad3c6ee6fadba7a7de7a9eb3e842994259be24c8/lib/http.js#L99-L130)、[`dsh-file-pane` 的配置 root 与 inline raw route](https://github.com/trungtaottn/dsh-file-pane/blob/f6e211f71e8ddad8cfe8ddf3a738b8831d6310cb/lib/index.js#L99-L173)、[`dsh-file-pane` 的 realpath 前缀检查与完整文件缓冲](https://github.com/trungtaottn/dsh-file-pane/blob/f6e211f71e8ddad8cfe8ddf3a738b8831d6310cb/lib/view-core.mjs#L92-L127)、[`dsh-file-pane` 的远程 Produced 接管](https://github.com/trungtaottn/dsh-file-pane/blob/f6e211f71e8ddad8cfe8ddf3a738b8831d6310cb/client/index.tsx#L370-L403)。

### <a id="file-transfer-rich-artifacts"></a>聊天产物下载

`dsh-rich-artifacts` 是本轮发现中唯一明确实现“模型发布工作区文件 → 聊天下载卡 → 浏览器 attachment response”的独立仓库。它向模型注册 `publish_artifact` 并加入 system prompt；Tool 使用 `ctx.fs.lstat/resolve/stat/contains` 把路径约束到 Session workspace，拒绝最终 symlink，按 magic bytes 判断 MIME，将文件复制到 SHA-256 内容寻址 blob store，再把 metadata 追加为 `artifact/published` 事件。浏览器对普通文件渲染 `/api/artifacts/:id/download` 链接，对安全栅格图片同时提供 inline preview；Host 下载 route 设置 `Content-Disposition: attachment`、`nosniff` 和长度，并用 `createReadStream` 传输。

> 来源：[workspace 约束与发布存储](https://github.com/Inkotake/dsh-rich-artifacts/blob/44f39793ce383330c781b38893d516e50cfab397/src/index.ts#L353-L459)、[`publish_artifact` Tool 与模型提示](https://github.com/Inkotake/dsh-rich-artifacts/blob/44f39793ce383330c781b38893d516e50cfab397/src/index.ts#L546-L634)、[HTTP content/download route](https://github.com/Inkotake/dsh-rich-artifacts/blob/44f39793ce383330c781b38893d516e50cfab397/src/index.ts#L475-L540)、[图片预览与文件下载卡](https://github.com/Inkotake/dsh-rich-artifacts/blob/44f39793ce383330c781b38893d516e50cfab397/src/client.ts#L102-L147)。

这条链路与内置 Produced 行仍有几处差异和缺口：

- 它不会自动发布所有 `write` / `edit` 产物。模型必须额外调用 `publish_artifact`；system prompt 只能提高调用概率，不能成为执行保证。
- client 在 `conversation.chat.turnTail` 注册时没有指定 priority，内置 `ui-deliverables` 同样使用默认 `0`。rc.2 的 chain 在同优先级下保持注册顺序并取首个非 null selector：若内置行先注册且本轮已有 mutation 产物，下载画廊会被遮蔽；若该 Plugin 先注册，则由它胜出。本轮没有运行真实 Web composition，实际注册顺序未验证；`dsh-file-pane` 显式使用 `priority:-1`，说明该 Slot 需要由 Plugin 自己确定接管顺序。
- `artifact/published` 通过修改内部 `KNOWN_SESSION_EVENT_TYPES` Set 注册，而 `Session.append()` 没有把第三方事件写成 `ignorable` 的公开面。插件安装期间可以识别该事件；插件移除并重启后，持久日志可能因 unknown、non-ignorable event 被拒绝。
- `/api/artifacts` 作为 Plugin 自己注册的更长 prefix route，不经过标准 `/api` fence；handler 不检查 Host、Origin、`Sec-Fetch-Site`、身份或 Session，只验证随机 artifact id。`maxTurnBytes` 尚未强制，blob 没有 GC；发布会先把完整文件读入内存，默认单文件上限 100 MiB，下载本身是流式。
- 仓库只有一个 store 测试、没有 CI，也没有发布到 npm。当前 commit 未提供真实 rc.2 Profile、历史恢复、卸载后重放或 turn-tail 组合测试。

> 来源：[未指定 priority 的画廊注册](https://github.com/Inkotake/dsh-rich-artifacts/blob/44f39793ce383330c781b38893d516e50cfab397/src/client.ts#L191-L217)、[rc.2 chain 的排序与首个非 null 语义](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/client/ui-slots/src/index.ts#L247-L252)、[内置 Produced 的默认优先级注册](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/client/ui-deliverables/src/client/index.ts#L37-L52)、[无请求 fence 的 artifact handler](https://github.com/Inkotake/dsh-rich-artifacts/blob/44f39793ce383330c781b38893d516e50cfab397/src/index.ts#L494-L540)、[直接注册 `/api/artifacts` prefix](https://github.com/Inkotake/dsh-rich-artifacts/blob/44f39793ce383330c781b38893d516e50cfab397/src/index.ts#L636-L642)、[内部事件 Set 修改](https://github.com/Inkotake/dsh-rich-artifacts/blob/44f39793ce383330c781b38893d516e50cfab397/src/index.ts#L22-L30)、[rc.2 恢复拒绝未知非 ignorable 事件](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/session/session-persistence/src/coordinator.ts#L1051-L1065)。

因此，“存在直接下载模型产出的社区仓库”和“已经存在可透明接管所有原生 Produced 文件的成熟 Plugin”是两个不同判断。`dsh-rich-artifacts` 证明前一条链路已经有人实现；当前固定 commit 仍依赖模型显式发布，并存在 Slot 组合、Session 格式、授权和生命周期缺口。`dsh-file-pane` 解决远程预览而非下载，`dsh-artifact-library` 只有不安全且不完整的原文件流，不能替代聊天下载链。

### <a id="file-transfer-security-boundaries"></a>传输与下载的安全边界

DSH 默认 Web bind 是 loopback，且标准 `/api` carrier 对 Host、Origin 和 `Sec-Fetch-Site` 做请求栅栏；这组检查不是用户认证。社区 Plugin 直接向 `webServer` 注册 exact 或更长 prefix route 时会先于标准 `/api` handler 命中，因而不会自动继承该栅栏。只有 Plugin 自己复用官方连接层或实现等价检查时，这些请求边界才存在。

> 来源：[标准 API 的 Host/Origin/Fetch-Metadata 检查](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/client/connection/src/api-request-trust.ts#L90-L123)、[WebServer exact 与 longest-prefix 路由顺序](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/host/webserver/src/index.ts#L256-L265)。

一条完整的工作区上传或下载链需要同时拥有以下边界；其中任一项不能由模型提示或前端隐藏按钮代替：

- Host 根据 `sessionId` 解析 authoritative cwd，不能接受浏览器自行声明根目录。
- 对目标做 canonical realpath、regular-file 与 no-follow 检查，并把 symlink 和 TOCTOU 纳入实现与测试。
- 上传限制单文件、文件数、批量总字节、持久存储总量、并发和速率；写入使用受限临时文件和原子发布，定义重名、取消、失败与清理语义。
- 下载使用安全文件名、`Content-Disposition: attachment`、`X-Content-Type-Options: nosniff` 和流式响应；HTML、SVG 等 active content 不能以内联同源页面交付。
- 浏览器和 Host 共同执行 Host/Origin fence；LAN、反向代理或多用户部署还需要真实身份与 Session ownership，而不是把不可猜 id 当认证。
- 任何进入模型上下文或决定聊天 UI 的附件/产物状态都必须写入可重放 Session 事件，并在 Plugin 卸载、版本升级、fork 和恢复时保持可解释。
- Produced 行在 `canOpenPath:false` 或远程浏览器场景需要明确的浏览器下载或预览动作；Host native opener 只能作为另一种动作，不能冒充下载。

这些边界也解释了为什么“给路径文字加一个 URL”不足以修复问题：URL 背后必须有受限的字节读取、授权、持久身份和响应生命周期。

### <a id="file-transfer-validation-boundary"></a>验证范围

本轮执行了 `dsh-file-uploads` Host 测试 7 项、`dsh-attachments` Host/package 测试 9 项和 `dsh-file` Host-facing 测试 5 项；其余仓库因缺少依赖、构建产物、测试或真实组合入口，只做固定 commit 的静态审计。没有把任何候选安装进当前 Web Profile，也没有用真实浏览器完成上传、刷新、fork、Session 恢复、下载和卸载后的端到端验证。

发布状态还有几处会改变“按 README 安装”得到的实际代码：`dsh-file-upload` 仓库是 0.5.2，npm 最新 0.4.3 对应更早 commit；`dsh-workspace-files` 仓库为 0.1.1，npm 仍是 0.1.0；`dsh-file-fix` 与 `dsh-attachment` 的 npm 版本对应本轮 commit；`dsh-file-uploads`、`@omdsh-dev/dsh-drag-and-drop`、`dsh-reveal-files`、`dsh-file-pane`、`dsh-rich-artifacts` 和 `@dsh-external/dsh-artifact-library` 未发布 npm。`dsh-file-upload` 与 `dsh-file` 的源码 clone 不含运行入口构建物且没有自动 prepare，不能把源码审计直接等同于 Git URL 安装可用。

因此，本章保留的是官方能力边界、固定源码事实、明确故障和未验证项。后续版本若改变 PromptContentPart、通用附件 Session event、Downloads API 或 Produced Slot，需要重新核对本章对官方缺口和社区兼容性的判断。

## <a id="2026-08-28-read-image-quota"></a>2026-08-28 · `read_image` 的请求与额度归属原理

本轮回读同一工作区中一份刚归档的“`read_image` 调用额度归属”会话，再用 DSH `0.1.1-rc.2` 固定源码核对其结论。会话里的核心问题是：当前模型为 Model Hub 中选择的 `gpt-5.6-sol` 时，`read_image` 应计入 DeepSeek 额度、Codex 额度，还是另有独立额度。下面只记录可复用的执行原理；归档 Session id、文件路径和账号信息不进入 skill。

**调研时间：** 2026-08-28（Asia/Shanghai）

> **证据边界：** 归档会话的用户消息粘贴了一张既有 `read_image` Tool card，而不是原始调用所在 Session 的事件流；该会话的 `assistant/message.source` 只能证明解释这件事的会话使用了哪条路由，不能反推被粘贴调用的原始路由。最终回复提供了检索线索，通用事实仍以固定源码为准。本节讨论模型服务的请求归属；供应商如何把图片输入换算成 token、请求次数、订阅配额或金额，仍由对应供应商的实时计费规则决定，DSH 不提供跨 Provider 的统一额度池。

### <a id="read-image-request-hierarchy"></a>模型请求与 Harness Tool 执行

一次成功的 `read_image` 横跨两个模型请求，中间夹着一次 Harness Tool 执行：

```text
模型请求 N（实际 provider/model 路由）
  └─ 模型生成 read_image Tool call
        ↓
Harness 执行 read_image（I/O 由 ctx.fs Provider 提供）
  ├─ 校验扩展名、附件服务、部署图片上限与当前路由的 image 能力
  ├─ 通过 ctx.fs 读取图片字节
  └─ 规范化并写入内容寻址附件存储
        ↓
持久 tool/result = 元数据信封 + ImageBlock 引用
        ↓
模型请求 N+1（再次解析实际 provider/model 路由）
  └─ 携带 ImageBlock，让模型真正看见图片
```

请求 N 本身与普通模型响应一样，会消耗它实际使用的 Provider 额度；模型只是在这次响应中选择了一个 Tool call。中间的 `read_image` 执行只调用 DSH 的文件系统和附件服务，I/O 的实际位置由 `ctx.fs` Provider 决定，但这段执行不发起 LLM 请求，因此没有独立的 DeepSeek、OpenAI 或其他模型额度。图片进入模型发生在请求 N+1；这次请求归属于 N+1 实际解析出的 Provider 路由。

`read_image` 在任何文件 I/O 之前从会话最新 request header、再从 Agent options 解析 provider/model，并要求该精确路由声明 `image` 输入。执行成功后，它先持久保存图片，再返回文本信封和 ImageBlock；Tool 名字本身不决定额度归属。

这道能力门禁证明的是刚生成 Tool call 的请求 N 所用路由可以接收图片，不保证未来的请求 N+1 仍用同一路由。N+1 会重新经过 `agent/request`；若 middleware 把它改成 text-only route，Tool 可以成功持久化 ImageBlock，但后续模型请求仍可能因新路由不接受图片而失败。能力与额度都应按每个 step 的最终路由分别判断。

> 来源：[`read_image` 的精确路由能力校验](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/fs/tool-fs/src/read-image.ts#L79-L99)、[Harness 读取与附件持久化](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/fs/tool-fs/src/read-image.ts#L169-L220)、[持久 ImageBlock 结果](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/fs/tool-fs/src/read-image.ts#L257-L272)、[模型响应后执行 Tool](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/core/agent-loop/src/agent.ts#L332-L418)、[外层循环进入下一 step](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/core/agent-loop/src/agent.ts#L263-L300)。

### <a id="read-image-provider-ownership"></a>Provider 路由、凭据与额度

DSH 在每个模型 step 构造 request 时重新经过 `agent/request` waterfall 和 `llm.prepareCall()`，把最终的 `provider`、`model` 记录到 request header 和 request context，再交给该路由的 Adapter。Middleware 理论上可以在相邻 step 改变路由，因此最准确的口径是“每个真实模型请求按它自己的最终 request config 归属”，而不是假定整个 Turn 永远使用 UI 最初显示的模型名。

Model Hub 管理模型目录、路由和凭据入口，不会把不同供应商的额度合并。相同显示名也可能对应不同 provider key；`gpt-5.6-sol` 只有与 provider key、Adapter 和凭据记录合在一起，才能确定账号归属。

| Provider key 示例 | 请求执行方 | 额度或计费归属 |
|---|---|---|
| `openai-codex` | DSH 官方 `PiAiAdapter` 的 Codex 路由 | 该路由绑定的 OpenAI/Codex 凭据与供应商规则 |
| `codex` | Model Hub 自带 `NativeOAuthAdapter` | Model Hub 该路由绑定的 OpenAI/Codex 凭据与供应商规则 |
| DeepSeek provider key | 对应 DeepSeek Adapter | 该 DeepSeek 路由绑定的 API 凭据与供应商规则 |
| 其他 provider key | 该 key 注册的 Adapter | 该路由自己的凭据、限流与计费规则 |

归档会话的持久 `assistant/message.source` 显示 `provider: openai-codex`、`model: gpt-5.6-sol`，这只能确认解释该问题的模型请求走 `openai-codex`。用户粘贴的 Tool card 不携带原始 `request/header`，所以原始图片调用仍需回到其来源 Session 核对：若相关 step 的 provider 是 `openai-codex`，前后模型请求归该 Codex 路由；若是 DeepSeek provider，则归 DeepSeek。两者之间的 Harness-side `read_image` Tool 执行都不会自行切换 Provider。Model Hub 同时存在的两条 Codex 路由及其凭据归属见 [Model Hub 的 Codex 路由](#model-hub-codex-routes)。

> 来源：[每 step 解析 Adapter 与最终 request config](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/core/agent-loop/src/agent.ts#L426-L489)、[request context 与 Provider 请求](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/core/agent-loop/src/agent.ts#L491-L513)、[assistant message 记录实际 provider/model](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/core/agent-loop/src/agent.ts#L392-L409)。

### <a id="read-image-context-cost"></a>持久图片与后续请求成本

成功结果会把附件引用写进 Session 日志，然后作为原生图片块进入下一次请求。只要这条结果仍在模型上下文中，后续请求会继续携带图片，直到 compaction（上下文压缩）替换这段历史。一次 `read_image` 因而不是只影响紧随其后的一次请求；它会增加之后每次相关 Provider 请求的图片输入成本。

附件存储按内容寻址；重复读取同一图片可以复用磁盘 blob，但每次成功 Tool call 都会新增一条历史结果。存储去重不等于上下文去重，也不消除供应商侧图片 token 或配额成本。工具 schema 本身同样随可见工具列表进入模型请求，其固定 token 成本也归当前请求的 Provider，而不是归 Tool 包。

新结果只追加在既有可复用前缀之后，不会单独使旧 KV Cache 前缀失效；这只描述缓存前缀关系，不表示新增图片输入免费。最终是否命中缓存、图片怎样折算和缓存输入怎样计费，仍由实际 Provider 协议和账号规则决定。

> 来源：[图像结果的持久性与后续请求成本](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/fs/tool-fs/README.zh.md#L126-L138)、[`read_image` schema 的可见性与固定请求成本](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/fs/tool-fs/README.zh.md#L98-L110)。

### <a id="read-image-attribution-check"></a>会话中的归属判定

判断一次图片读取最终消耗哪一方额度时，按下面的证据顺序检查：

1. 对包含 Tool call 和后续图片处理的每个 step，读取其之前最近一条 `request/header.config.provider` 与 `model`；header 只在初始、恢复或配置变化时追加，相邻 step 若出现 `reason: change`，分别计算归属。
2. 用 `assistant/message.source.provider/model` 交叉确认实际完成该 step 的路由；显示名称不足以区分 Model Hub 中同名模型。
3. 把 `tool/call`、Harness-side `tool/result` 和下一次 `assistant/message.usage` 分开：Tool 执行没有供应商 usage，模型请求的 usage 才属于 Provider。
4. 检查图片结果是否仍在未压缩历史中；仍在时，后续请求继续承担图片输入成本。
5. 若某个社区 Plugin 在自己的 Host 处理流程或 Tool 执行中主动调用另一套视觉模型，它产生的是第二条独立 Provider 请求，应按该 Plugin 配置的视觉端点和凭据归属，不能套用官方 `read_image` 不发起 LLM 请求的结论。

最后一项正是官方 `read_image` 与“上传后自动调用外部视觉模型生成描述”之间的边界。后者可在 Plugin 自己的 Host 处理或 Tool 执行阶段消耗另一模型服务的额度；例如本文件前一章记录的 `dsh-file-upload` 在 Host 上传处理阶段调用视觉发现链，并可能请求 OpenAI-compatible endpoint，而官方 `read_image` 不会。

> 来源：[`dsh-file-upload` 在上传处理阶段调用视觉描述](https://github.com/HongMing-Huang/dsh-file-upload/blob/ce4ca943da592be36a784a5648d36a600aeda136/src/upload.ts#L199-L215)、[社区文件上传 Plugin 的外部视觉调用](https://github.com/HongMing-Huang/dsh-file-upload/blob/ce4ca943da592be36a784a5648d36a600aeda136/src/vision.ts#L60-L135)。

## <a id="2026-08-28-session-import"></a>2026-08-28 · 外部会话导入 DSH

本轮专题是：社区 Plugin 如何把**其他产品的聊天记录**写成 DSH 可 resume 的 Session。官方 DSH 没有这条导入面；市场目录（`dsh-market` 快照 `updated: 2026-08-16`）当时只收录 `dsh-chat-import` 与 `dsh-plugin-session-import`，后续 Codex 双向同步、网页版导入等仓库不在那份快照里。

**调研时间：** 2026-08-28（Asia/Shanghai）

**调研目标：**

- 核对官方 Session 日志、已知事件词汇表、token meter 重放和 workspace 归组对导入器的约束。
- 盘点把 Claude Code / Codex / ChatGPT / Cursor / Pi / opencode / DeepSeek 网页等外部记录写入 DSH 的社区仓库。
- 比较写入路径（`sessionPersistence` / `agents.create` / 直接写 `session.jsonl.zstd`）、事件配对、反向导出与 MCP/Skills 附带能力。
- 记录 HTTP 路由、路径范围和进程副作用；不把 README 的「一键续聊」当成已验证的 Web 组合结果。

> **证据边界：** 官方源码固定 `deepseek-ai/deepseek-harness@b150a551`（`0.1.1-rc.2`）。社区仓库均为完整、非 shallow clone，HEAD 与远端默认分支一致。本轮在 `dsh-chat-import` 执行 `npm ci && npm test`（587 项通过）；在 `dsh-codex-sync` 执行 `npm ci && npm test`（38 通过、1 失败，见下文）。没有把候选装进当前 Web Profile，也没有用真实 Claude/Codex/网页账号做端到端导入。

### <a id="session-import-official-constraints"></a>官方 Session 写入与恢复约束

导入器最终要交出一份 DSH 能 `list` / 打开 / 续聊的 Session。官方默认 Profile 把每个 Session 写成 `.jsonl.zstd`；JSONL 后端要求**第一个 zstd 帧只含一行 header**，后面的帧才是事件批次。把整份明文压成单帧会在扫描时报 `first frame is not exactly one header line`。

读路径拒绝词汇表外的事件类型，除非该事件带 `ignorable: true`。`session/imported` 不在官方 `KNOWN_SESSION_EVENT_TYPES` 中；导入器若写入这种标记，必须设 `ignorable`，否则插件卸载或换一套不含该类型的 harness 后，持久日志可能被拒绝。

`assistant/message`、`tool/call`、`tool/result` 必须落在配对的 `step/start`…`step/end` 内。原生会话由 agent-loop 写这些标记；导入器漏写时，换模型或 compaction 的 token meter 冷重放会报 `assistant/message at seq N has no matching step/start event`。

侧边栏归组走 `workspaceRegistry`：只 `create`+`append` 而不 `attachSession` 的会话会进「未分组」。`cwd` 为用户主目录时，DSH 沙箱 ACL 会拒绝后续工具，导入器需要跳过 HOME 归组。

> 来源：[恢复拒绝未知非 ignorable 事件](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/session/session-persistence/src/coordinator.ts#L1051-L1065)、[官方已知事件词汇表（无 `session/imported`）](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/core/session/src/known-event-types.ts#L19-L68)。

### <a id="session-import-repository-snapshot"></a>仓库快照

下表按本轮 clone 的 HEAD。「测试」是仓库内文件或本轮实际执行，不代表已在真实 DSH Web 组合通过。

| 仓库 | 版本 / commit | Stars | 主要范围 | 测试与发布信号 |
|---|---|---:|---|---|
| [`dsh-chat-import`](https://github.com/Nwflower/dsh-chat-import/tree/fc99352bdbcd36a65c04e045f8ebe5f42f754674) | `0.8.0` / `fc99352` | 115 | 18 种来源导入、反向导出、可选双向同步 | 34 个 `*.test.mjs`；本轮 `npm test` 587 通过；CI + headless smoke；npm 与 tag `v0.8.0` 一致 |
| [`dsh-codex-sync`](https://github.com/Walvez/dsh-codex-sync/tree/20f707a76d2a172951932d4b1734f578f6a99dd8) | `1.6.1` / `20f707a` | 25 | Codex 会话双向 + Skills 挂载 + MCP 镜像 | 本轮 38 通过、`client.render` 1 失败（React `useState` 空）；CI Node 20/22 + `dsh-boot-smoke`；npm `v1.6.1` |
| [`dsh-import-agents`](https://github.com/Chang-Tong/dsh-import-agents/tree/d5095df4d3b16594fb0eddd2d10f92b251d087a0) | `0.2.8` / `d5095df` | 13 | pi / opencode / Codex / Claude Code 会话，agent 转 skill | 7 个 vitest 文件；有 CI |
| [`dsh-plugin-session-import`](https://github.com/huguangyu666/dsh-plugin-session-import/tree/13139abe5820ea07bf5a89cef36801ee17987aa0) | `0.1.1` / `13139ab` | 6 | claude / codex / reasonix / zcode | 4 个根目录 `test-*.mjs`；无 CI |
| [`dsh-cc-import`](https://github.com/Mreate/dsh-cc-import/tree/db07df7599c4ac1594b801e56d9f605f52aabba6) | `0.1.0` / `db07df7` | 4 | Claude 会话导入 + CLAUDE.md/`/init` | 有 CI workflow；无本轮执行 |
| [`deepseek-web-import`](https://github.com/wpc0323/deepseek-web-import/tree/8780b8c80addf9f6519a02106f6a28d2ebaedb99) | `0.1.0` / `8780b8c` | 4 | chat.deepseek.com API → DSH Session | 无测试 |
| [`dsh-session-importer`](https://github.com/sunzeJAVA/dsh-session-importer/tree/ff8c042f85f01c951102b17d79010aec69247579) | `0.1.7` / `ff8c042` | 0 | Claude / Codex / JSONL / Markdown | 有 `test/` |
| [`dsh-codex-import`](https://github.com/G1en-114/dsh-codex-import/tree/7ec772883ec610b5d9974d7d6ceccb93131f437d) | `0.1.0` / `7ec7728` | 2 | Codex `/codex-import` | 1 个测试文件 |
| [`dsh-plugin-codex-import`](https://github.com/Gordonynh/dsh-plugin-codex-import/tree/85db489dcc67390d269bcfad6a883941b57366c9) | `1.0.0` / `85db489` | 1 | Codex `/codex-import` | 有 `test/` |
| [`session-import-codex`](https://github.com/xing01l/session-import-codex/tree/5dcc2196becb8be8e983addc5340c95c90af5a8e) | `0.1.1` / `5dcc219` | 0 | 经 `codex app-server --stdio` 导入，不扫 jsonl | vitest + CI |
| [`dsh-codex-session-sync`](https://github.com/linmu115/dsh-codex-session-sync/tree/1797669de0d7540def75bee90a5c9c5b15175455) | `0.3.3` / `1797669` | 0 | 停 DSH 进程后做 Codex 单向同步（Windows/EAC） | 2 个测试文件 |
| [`dsh-plugin-claude-import`](https://github.com/changhang155/dsh-plugin-claude-import/tree/6d3aaff9e5958ce4d323c6247e457d954f190e4a) | `0.1.0` / `6d3aaff` | 1 | 把 Claude 记录渲染成当前对话上下文，不新建 Session | `tests/parse.test.mjs` |
| [`dsh-claude-importer`](https://github.com/LXW419/dsh-claude-importer/tree/5796d073d603795233af851a9eb79f999878e4a9) | 无 npm / `5796d07` | 0 | Inspect 用 `plugin.json` 草稿，不是可安装 Cordis 包 | 无测试 |
| [`dsh-web-import`](https://github.com/Ranz-Feng/dsh-web-import/tree/0a82cf23e0ab13234ce7ce7c71ef28525a0fe17d) | `0.1.0` / `0a82cf2` | 0 | CLI：网页版 `conversations.json` → 直接写 zstd | 3 个测试文件 |
| [`dsh-importer`](https://github.com/PrismScopes/dsh-importer/tree/042181a03d334e7705d270cda01154168af9690a) | `1.0.0` / `042181a` | 0 | 网页版 token 同步到本地 JSON，供模型 `read`，不建 Session | 无测试 |
| [`dsh-chat-import` (Scarlett)](https://github.com/AI-Scarlett/dsh-chat-import/tree/81f1a9785fbae6acd04a6b49a576b237c4f70eae) | `0.4.0` / `81f1a97` | 0 | 上游 fork，停在 0.4.0 | 测试集小于 `fc99352` |

> Stars 为 2026-08-28 GitHub API 快照，只表示当时关注度，不代表架构质量或安全审计。

相邻但不在本轮 clone 集的：`kinyokun/dsh-session-import`（5）等只吃 DSH `/export` zip/jsonl，属于 DSH→DSH 再导入，不是外部 transcript。Skill / 主题 / CCSWITCH 导入也不在本专题。

### <a id="session-import-write-models"></a>写入模型

外部记录变成 DSH Session 只有三条实测路径；「侧边栏能看到一段历史」不等于第三条。

| 写入模型 | 谁用 | 续聊含义 |
|---|---|---|
| `ctx.sessionPersistence.create` + `append`，或 `ctx.agents.create({ seed })` | `dsh-chat-import`、`dsh-codex-sync`、`dsh-import-agents`、多数 Codex/Claude 专用包、`deepseek-web-import` | 官方列表/打开/resume；可挂 preset 与工具 |
| 直接写 `<sessions>/<projectKey>/<id>/session.jsonl.zstd`（头帧+事件帧） | `dsh-web-import` CLI；`dsh-codex-sync` 的 `dsh-writer.mjs` 仍导出但导入热路径已改走 persistence | 不经过内存索引，通常要重启或刷新才出现 |
| 不写 Session：markdown seed、本地 JSON 给 `read`、停进程后改磁盘 | `dsh-plugin-claude-import`、`dsh-importer`、`dsh-codex-session-sync` | 当前回合上下文或文件，不是可独立打开的导入会话 |

`dsh-codex-sync` 的导入服务注明改编自 `dsh-import-agents`，并补了 256 MiB 单文件上限（避免 Node 字符串上限打断整批）和整批 workspace 再挂载。

### <a id="session-import-dsh-chat-import"></a>`dsh-chat-import`

这是本轮覆盖来源最多、测试最密的导入器（115）。插件 `name` 仍是 `import-claude`，bundle id 同名；npm 包与面板已是 18 种格式。默认扫描根在 `defaultRoots()`：`~/.claude/projects`、`~/.codex/sessions`、`~/.cursor/projects`、`~/.gemini/history`、`~/.reasonix/sessions`、opencode/mimocode SQLite、`~/.zcode/cli/db/db.sqlite`、`~/.grok/sessions`、`~/.openclaw/agents`、`~/.pi/agent/sessions`、`~/.hermes`、`~/.kimi{,-code}/sessions`、`~/.qoder/projects`、`~/.workbuddy/projects`、`~/.dsh/sessions`。ChatGPT 没有自动根，必须指向 `conversations.json`。

转换层是零 DSH 依赖的纯函数：各源先收成回合中间结构，再 `synthesizeSession` 写出平衡日志。seq 0 为 `session/imported` 且 `ignorable: true`；随后注入一条 `source.kind='plugin'` 的环境变更 `user/message`；每轮有 `turn/start`、`step/start`…`step/end`、`user/message`、`assistant/message`，工具为 `tool/call` + 带 `sourceEventSeqs` 的 `tool/result`。落盘优先 `agents.create({ seed, setup: agentPresets.mount })`，失败再回退 `sessionPersistence.create`+`append`。`cwd === HOME` 时跳过归组。幂等登记在 `$DSH_HOME/dsh-chat-import`。

入口：模型工具 `import_chat`（`format` 枚举 18 值）、`scan_discover`、`export_chat`（claude/codex/kimi）、bundle 备份/恢复、`verify_session`、识别/撤回；Web 侧边栏面板；`/import`、`/resume-claude`、`/resume-codex`。反向导出写新 UUID 文件，不覆盖已有 Claude transcript。MCP 镜像默认 dry-run，只把 YAML 写到 `$DSH_HOME/dsh-chat-import/mcp-mirror.cordis.yml`，不改 profile。双向同步面板默认关闭。

Web 路由是 exact `/api-import/sessions`、`/api-import/import`、`/api-import/prefs`。注释称与面板同一信任围栏，handler 内没有 Host / Origin / `Sec-Fetch-Site` 检查；路径也不是官方 `/api` 前缀，因此不继承标准 API 栅栏。请求体里的 `sourcePath` 会交给 `ctx.fs.resolve` 再导入。

> 来源：[18 种转换器与 `synthesizeSession`](https://github.com/Nwflower/dsh-chat-import/blob/fc99352bdbcd36a65c04e045f8ebe5f42f754674/lib/convert/core.mjs#L1-L128)、[`session/imported` + `ignorable`](https://github.com/Nwflower/dsh-chat-import/blob/fc99352bdbcd36a65c04e045f8ebe5f42f754674/lib/convert/core.mjs#L97-L114)、[`agents.create` 与 persistence 回退](https://github.com/Nwflower/dsh-chat-import/blob/fc99352bdbcd36a65c04e045f8ebe5f42f754674/lib/import-core.mjs#L140-L184)、[默认扫描根](https://github.com/Nwflower/dsh-chat-import/blob/fc99352bdbcd36a65c04e045f8ebe5f42f754674/lib/discovery.mjs#L68-L98)、[插件名仍为 `import-claude`](https://github.com/Nwflower/dsh-chat-import/blob/fc99352bdbcd36a65c04e045f8ebe5f42f754674/index.mjs#L49-L66)、[`/api-import/import` 按 `sourcePath` 导入](https://github.com/Nwflower/dsh-chat-import/blob/fc99352bdbcd36a65c04e045f8ebe5f42f754674/lib/panel.mjs#L236-L295)。

### <a id="session-import-dsh-codex-sync"></a>`dsh-codex-sync`

范围是 Codex 一家（25），但比「导入会话」宽：`~/.codex/skills` 注册为 DSH skill、`config.toml` 的 `[mcp_servers.*]` 热镜像到 `@deepseek-ai/dsh-mcp-client`、可选把 DSH 插件能力反向装进 Codex MCP。会话导入读 `~/.codex/sessions/**/rollout-*.jsonl`，id 为 `codex-<uuid>`；默认丢掉 `parent_thread_id` 子代理线程。热路径是 `persistence.create`+`append`，已存在则按用户消息文本做增量 `append`。转换器补 `step/start`…`step/end`，因为 v1.6.0 前的日志会在换模型时被 token meter 拒绝；`/repair-sessions --fix` 用系统 `zstd -dc` 读盘、按真实 `@deepseek-ai/dsh-token-meter` 校验后再写回，并留 `.bak`。

`lib/dsh-writer.mjs` 仍实现头帧+事件帧的 zstd 写法，但当前 `importCodex` 不再调用它。MCP 镜像默认开，且永远排除 `dsh-plugins` 以免递归。HTTP 前缀 `/dsh-codex-sync` 同样不走官方 `/api` 栅栏；`POST /open-path` 只允许打开 Codex/DSH 相关路径，但在 Windows 上走 `cmd /c start`。

本轮 `npm test`：导入/修复/host smoke 等 38 项通过；`test/client.render.mjs` 因本机全局 `@deepseek-ai/dsh` 的 React 与仓库 `node_modules/react` 不是同一份，`useState` 读到 null。不能据此判断 UI 在真实 Web Profile 里失败。

> 来源：[改编自 `dsh-import-agents` 与 256 MiB 护栏](https://github.com/Walvez/dsh-codex-sync/blob/20f707a76d2a172951932d4b1734f578f6a99dd8/lib/import-service.js#L1-L29)、[create/append 与增量更新](https://github.com/Walvez/dsh-codex-sync/blob/20f707a76d2a172951932d4b1734f578f6a99dd8/lib/import-service.js#L206-L259)、[step 配对原因](https://github.com/Walvez/dsh-codex-sync/blob/20f707a76d2a172951932d4b1734f578f6a99dd8/lib/convert.mjs#L49-L60)、[修复用系统 zstd](https://github.com/Walvez/dsh-codex-sync/blob/20f707a76d2a172951932d4b1734f578f6a99dd8/lib/session-repair.mjs#L63-L75)、[MCP 镜像职责](https://github.com/Walvez/dsh-codex-sync/blob/20f707a76d2a172951932d4b1734f578f6a99dd8/lib/mcp.js#L1-L21)、[`/open-path` allowlist 与 `cmd /c start`](https://github.com/Walvez/dsh-codex-sync/blob/20f707a76d2a172951932d4b1734f578f6a99dd8/lib/index.js#L615-L664)。

### <a id="session-import-other-plugins"></a>其余项目

**多源、写入 Session**

| 项目 | Stars | 来源 | 写入 | 要点 |
|---|---:|---|---|---|
| `dsh-import-agents` | 13 | `~/.pi/agent/sessions`、opencode db、`~/.codex/sessions`、Claude jsonl | 插件路径 `sessionPersistence`；CLI `--apply` 另走原始 zstd。agent 写 `$DSH_AGENTS_HOME/skills` | `/import-all`、composer Sync、新会话迁移询问；是 `dsh-codex-sync` 导入服务的上游。事件**没有** `step/start`…`step/end`，换模型时会撞 token meter |
| `dsh-plugin-session-import` | 6 | claude / codex / reasonix / zcode | `agents.create` | 侧边栏与 `/api-import/list|batch`，与 `dsh-chat-import` **同前缀冲突**；id 为 `import-${Date.now()}-…`，不幂等；`findJsonlBySessionId` 只读 `USERPROFILE`，Linux 会漏 |
| `dsh-session-importer` | 0 | Claude、Codex、Kimi、generic JSONL、Markdown；扫描还看 `.gemini` / `.cursor` / `.aider` / `.windsurf` 目录 | `sessionPersistence`（可选 inject） | 无 `dsh.bundle`，需手写 patch。硬 `inject` 为 `commands`+`sessions`；persistence 另绑，服务名对不上时可能不写盘。id 为 `import-${source}-${sha1}` |

**单源 Codex**

| 项目 | Stars | 输入 | 写入 | 与 `dsh-codex-sync` 的差别 |
|---|---:|---|---|---|
| `dsh-codex-import` | 2 | `~/.codex/sessions/**/rollout-*.jsonl` | 插件 persistence；CLI 原始 zstd（目录名未 `encodeSegment`） | 随机 `session-${uuid}`；另写 `permission/preset` / `sandbox/mode` |
| `dsh-plugin-codex-import` | 1 | 同上，可 `--archived` | persistence，**沿用 Codex UUID** 作 DSH id | 无 bundle，需手写 patch；会补缺失的 tool/result |
| `session-import-codex` | 0 | **不读 jsonl**：拉起 `codex app-server --stdio` | persistence，id `codex-${threadId}`；自定义 `session-import-codex/source`（`ignorable: true`） | 结构最接近官方事件校验；模型名写死 `codex-import-unknown` |
| `dsh-codex-session-sync` | 0 | 读 Codex home，转换器是 vendored 的 chat-import | 原始 zstd + **停掉官方 DSH 再重启** | Windows/EAC：`cordis.patch.yml` 写死 `D:\AI\DeepSeek-Harness`，需要 `Start-Official-DSH.ps1` |

**Claude**

`dsh-cc-import`（npm 名 `cc-import`，4）方向是 **Claude → DSH**：jsonl 写成 Session（id `cc-<filename>`），并注入 CLAUDE.md/DSH.md、提供 `/init` 写 DSH.md。`turn/end` 的 `reason.kind` 为 `'success'`，官方原生是 `'completed'`，恢复时是否接受未在本轮验证。路由 `/api/cc-import/*`，无测试，CI 只 build。

`dsh-plugin-claude-import`（1）默认把摘要渲染进**当前**对话；`createSession=true` 时走 apiProxy 新建空 Session 再 `sessions.prompt` 一条 seed 文本，仍然不是把 jsonl 重放成事件日志。`dsh-claude-importer`（0）只有 Inspect `plugin.json` 和 `cordis_define` 草稿，不能 `dsh plugin add`。

**DeepSeek 网页版**

| 项目 | Stars | 输入 | 是否 DSH Session |
|---|---:|---|---|
| `deepseek-web-import` | 4 | 设置页粘贴 `userToken`，拉 `chat.deepseek.com` API | 是：文本-only 事件，随机 `session-…`，须选手动工作区。Host HTTP 使用 `rejectUnauthorized = false` |
| `dsh-web-import` | 0 | 开发者工具拷的 `conversations.json` | 是：独立 CLI（不是 Plugin），直接写两帧 zstd；默认若 3080 已占用则拒绝，除非 `--import-only` |
| `dsh-importer` | 0 | 同样要 token，curl 轮询官方导出 | 否：写入 `$DSH_HOME/dsh-importer/` 的 JSON，UI「发送」只把路径填进 composer |

`dsh-importer` 的 Origin 允许列表含 `chat.deepseek.com` 与 `http://127.0.0.1:3080`，但缺 Origin 时仍放行，且 `status` 会把 token 原文返回。`deepseek-web-import` 把浏览器 `userToken` 交给 Host 去拉历史，等于把网页登录态交给 DSH 进程。

**Fork**

`AI-Scarlett/dsh-chat-import@81f1a97` 与 Nwflower 同分叉根 `e791dbe`，停在 `0.4.0`（157 commit），上游已是 `0.8.0`（286 commit）。Scarlett 独有 `project-share`，未合进上游；不是双向同步的现行版本。

> 来源：[import-agents 无 step 标记的 convert](https://github.com/Chang-Tong/dsh-import-agents/blob/d5095df4d3b16594fb0eddd2d10f92b251d087a0/lib/convert.mjs#L31-L132)、[session-importer 的 inject](https://github.com/sunzeJAVA/dsh-session-importer/blob/ff8c042f85f01c951102b17d79010aec69247579/src/index.js#L18-L36)、[claude-import 默认不重放日志](https://github.com/changhang155/dsh-plugin-claude-import/blob/6d3aaff9e5958ce4d323c6247e457d954f190e4a/lib/index.js#L1-L4)、[网页版导入 persistence](https://github.com/wpc0323/deepseek-web-import/blob/8780b8c80addf9f6519a02106f6a28d2ebaedb99/lib/index.js#L225-L255)、[CLI 两帧 zstd](https://github.com/Ranz-Feng/dsh-web-import/blob/0a82cf23e0ab13234ce7ce7c71ef28525a0fe17d/src/dsh.js#L7-L16)。

### <a id="session-import-security"></a>导入器的请求与磁盘范围

和[浏览器文件传输](#file-transfer-security-boundaries)同一条：Plugin 自注册的 exact / 非 `/api` 前缀路由不会自动得到 Host/Origin/`Sec-Fetch-Site` 栅栏。本轮导入器里，`/api-import/*` 与 `/dsh-codex-sync` 都是这种路由；它们能列出本机 agent 目录、按客户端给出的路径导入、开关 MCP 镜像或打开本机文件。默认 Web bind 仍是 loopback，因此风险首先是「本机浏览器里的任意页面」，不是公网匿名。LAN 或反向代理部署时，这些路由没有第二层身份。

另外几条与文件上传不同的范围：

- 导入器按设计读取 `~/.claude`、`~/.codex`、SQLite 库和网页 `userToken`。这是功能，不是越权；把它们挂到可被非 loopback 访问的 Host 上，等于导出这些目录。
- `dsh-chat-import` 的 `export_chat format=claude` 向 `~/.claude/projects` 写新文件（新 UUID，不覆盖）。`dsh-codex-sync` 向 `~/.codex/sessions` 写新 rollout，并改 `config.toml`（`codex-install`）。
- `dsh-codex-sync` 的 MCP 镜像会在 DSH 进程里拉起 Codex 配置的 stdio/HTTP 服务器；`dsh-chat-import` 的 MCP 工具默认只出 YAML 计划。
- `/repair-sessions` 与部分 CLI 用系统 `zstd` 二进制加裸 `writeFileSync` 改 Session 目录；成功路径有 `.bak`，仍绕过 `sessionPersistence` 的追加语义。
- `dsh-codex-session-sync` 会停止官方 DSH 进程。这超出「写一条会话日志」。
- `deepseek-web-import` 的 Node HTTPS 客户端关闭证书校验（`rejectUnauthorized = false`）。
- `dsh-importer` 缺 Origin 时仍允许请求，`status` 回传明文 token。
- `dsh-plugin-session-import` 与 `dsh-cc-import` 的导入 HTTP 同样没有 Host/Origin 栅栏；batch 体里的路径是任意本机读取。

同 Profile 同时安装 `dsh-chat-import` 与 `dsh-plugin-session-import` 会争 `/api-import/*`；再叠加 `dsh-codex-sync` 与 `dsh-import-agents` 会重复扫描同一批 Codex rollout，id 前缀不同（`import-…` vs `codex-…` vs `claude-…`），列表里可能出现同一对话的多份副本。

### <a id="session-import-validation"></a>验证范围

本轮源码结论能回答「谁把外部记录写成哪一种 DSH 产物」。不能代替：真实 Claude/Codex 目录导入后打开、换模型、compaction、fork、插件卸载再恢复；网页版 token 拉取；MCP 镜像在已占用 `openai-codex` 路由的 Profile 上的冲突；Windows 与 Linux 默认根（`APPDATA` / `USERPROFILE` / `.local/share`）是否扫全。

`dsh-chat-import` 的 587 项测试覆盖转换、幂等、预算裁剪、发现缓存和面板 prefs，不启动真实 `dsh web`。`dsh-codex-sync` 的 host smoke 用假 MCP client 装插件并断言命令名，不导入真实 rollout。CI 里的 `dsh plugin add` smoke 只证明当时 npm latest 的 DSH 能激活插件行。

因此：需要立刻从 18 家 transcript 续聊，以 `dsh-chat-import` 为候选；需要 Codex 会话+Skills+MCP 一起迁，以 `dsh-codex-sync` 为候选；两者都还没有本轮的真实 Web 组合验收。

## <a id="2026-09-04-web-search-recheck"></a>2026-09-04 · `web_search` 的搜索提供方与额度归属

`web_search` 的账单跟着 `ctx.web` 当时选中的搜索提供方走，不跟着对话模型走。与 [`read_image`](#2026-08-28-read-image-quota)（Tool 执行阶段不发起模型请求）相反，默认的 DeepSeek 搜索提供方在 Tool 执行阶段自己发起一次独立的 Messages 模型请求，额度归属于这次请求实际使用的提供方。本节由 2026-08-28 的同主题专题在 2026-09-04 全面复核并合并而成，过时结论已就地更新。

**调研时间：** 2026-09-04（Asia/Shanghai；含并入的 2026-08-28 原专题记录）

**调研目标：**

- 说明 `web_search` 的执行链、提供方选择策略与额度归属的判定证据。
- 核对 DSH `0.1.2-rc.1` 的 web 包家族、默认组合与配置面相对 `0.1.1-rc.2` 的变化，并用 DeepSeek 官方 API 文档印证计费机制。
- 盘点把 `web_search` 接到 Codex 订阅、以及直接实现 `WebSearchProvider` seam 的社区插件，归纳接入模式与冲突边界。

> **证据边界：** 官方源码两轮固定——08-28 原记录锚定 `0.1.1-rc.2`（commit [`b150a551`](https://github.com/deepseek-ai/deepseek-harness/tree/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e)，其原有来源链接仍指向该 commit）；09-04 复核锚定 `0.1.2-rc.1`（commit [`a66e470`](https://github.com/deepseek-ai/deepseek-harness/commit/a66e4702047846cdaa10c66c9d3df3951f5ea70d)，2026-09-02 发布提交，未另标 commit 的官方引用均指它）。本机安装树为 0.1.2-rc.1，🔬 常量核对与包内 README 行号定位以它为据（同一 release 的包内 README 与 GitHub blob 行号一致）。DeepSeek API 文档为 2026-09-04 抓取的现行页面。社区插件按各仓库 HEAD 快照固定到来源链接中的 commit，未做逐行全量源码审计；除注明 🔬 的两段归档会话观察外，两轮均未用真实凭据做端到端搜索验证。供应商如何把搜索折算成订阅额度或金额，仍由该供应商的实时规则决定。

### <a id="web-search-provider-selection"></a>web_search 的执行链与提供方选择

`web_search` 由 `@deepseek-ai/dsh-tool-web` 注册，负责面向模型的 schema 与结果卡片；执行路径是 `ctx.web.search()`，由当时选中的 `WebSearchProvider` 发请求。对话里选了 `openai-codex` / `gpt-5.6-sol`，并不改搜索提供方。`dsh-tool-web` 接受必填的 `queries` 数组并扇出为多个独立 seam 请求；`maxResults` 是消费方自有的上限（`searchMaxResults` 配置，默认 8），经 seam 传递并在回程强制截断、置 `truncated`。

`dsh-base` 把 `web` 行的 `searchProvider` 钉为 `deepseek-official`（0.1.2-rc.1 起同一行还新增 `fetchProvider: http`）。选择在每次调用的执行期解析，与注册、加载或 HMR 顺序无关；提供方的 `available()` 是廉价的本地检查（凭据是否存在、配置是否可解析），禁止发起网络调用。`$DSH_WEB_SEARCH_PROVIDER` 与 `$DSH_WEB_FETCH_PROVIDER` 环境变量填充的是同一组配置字段，不构成独立优先链。选择失败抛结构化 `WebError`：

| 情形 | 结果 |
|---|---|
| 配置 id 已注册且可用 | 运行该 provider |
| 配置 id 未注册 | `WEB_PROVIDER_CONFIGURED_MISSING` |
| 配置 id 已注册但不可用 | `WEB_PROVIDER_CONFIGURED_UNAVAILABLE` |
| 未配置 id，恰有一个可用 | 运行它 |
| 未配置 id，无可用 | `WEB_PROVIDER_UNAVAILABLE` |
| 未配置 id，多个可用 | `WEB_PROVIDER_AMBIGUOUS` |

`WebError.code` 是开放式字符串，消费方必须容忍未知码；错误码按所有者划分。`WebRuntime` 持有上表的选择码、`WEB_DUPLICATE_PROVIDER`（注册期重复 id 的编程错误，类似 `LlmRuntime` 的 `DUPLICATE_ADAPTER`）与 `WEB_ABORTED`；`WEB_PROVIDER_ERROR` 是提供方自身故障（DNS、拒连、TLS 等传输失败）经 seam 暴露的兜底码；抓取传输层错误码（`WEB_INVALID_URL`、`WEB_BLOCKED_URL`、`WEB_REDIRECT_BLOCKED`、`WEB_FETCH_TOO_LARGE`、`WEB_FETCH_TIMEOUT`、`WEB_UNSUPPORTED_CONTENT_TYPE`）由 `dsh-web-fetch-http` 持有。

> 来源：[web 子系统文档：queries 扇出、searchMaxResults、错误码归属与抓取网络策略](https://github.com/deepseek-ai/deepseek-harness/blob/a66e4702047846cdaa10c66c9d3df3951f5ea70d/docs/subsystems/web.zh.md)；[seam 的 env 入口与字段表](https://github.com/deepseek-ai/deepseek-harness/blob/a66e4702047846cdaa10c66c9d3df3951f5ea70d/packages/web/web/README.md#L36-L46)、[四态选择表与执行期解析](https://github.com/deepseek-ai/deepseek-harness/blob/a66e4702047846cdaa10c66c9d3df3951f5ea70d/packages/web/web/README.md#L67-L78)；[base patch 的 web / tool-web 行](https://github.com/deepseek-ai/deepseek-harness/blob/a66e4702047846cdaa10c66c9d3df3951f5ea70d/packages/bundle/base/cordis.patch.yml)；[工具只调用 `ctx.web.search()`](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/web/tool-web/README.zh.md#L1-L15)。

### 默认搜索链路：DeepSeek 官方搜索提供方

默认提供方 `deepseek-official` 另开一轮 Anthropic 兼容 Messages 调用：模型默认 `deepseek-v4-flash`，工具为 `web_search_20250305`，凭据复用 `DEEPSEEK_API_KEY`，基址默认 `https://api.deepseek.com/anthropic/v1`（再拼 `/messages`）。这与 chat-completions 使用的 `https://api.deepseek.com` 不是同一基址，因此不复用 `$DEEPSEEK_BASE_URL`。一次搜索消耗一个完整模型轮次的延迟与生成 token，每次请求最多 `maxUses` 次服务端搜索；DeepSeek 不提供专用检索端点。结果只取结构化的 `web_search_tool_result` 块，provider 生成的文本不作为答案受到信任（`content` 始终省略），来源按 URL 去重。

0.1.2-rc.1 的配置面从环境变量为主扩展为完整的 Settings 段，配置表在 `apiKeyEnv` 之外新增：

| 字段 | 默认值 | 说明 |
|---|---|---|
| `baseURL` | `https://api.deepseek.com/anthropic/v1` | 追加 `/messages`；缺省回退 `$DEEPSEEK_SEARCH_BASE_URL` |
| `model` | `deepseek-v4-flash` | Anthropic 格式模型名 |
| `apiVersion` | `2023-06-01` | `anthropic-version` 头 |
| `maxTokens` | `4096` | 生成 token 上限 |
| `maxUses` | `5` | 每次请求服务端搜索次数上限 |
| `apiKey` | 未设置 | 字面量密钥，优先于 `apiKeyEnv` |

三个机制值得单独记：

- **Settings 段逐次投影。** 配置条目构成 provider Settings 段的 base 层，用户层叠加其上并作用于下一次搜索（按次投影而非注册时固化）；Settings > Plugins > Plugin configuration > Web search 页面可改 Endpoint 并保存。
- **凭据逐次解析。** 密钥引用每次搜索经 `ctx.credentials` 解析（Models 页写入的托管凭据文档具有权威性，无该服务时回退进程环境）；在 Models 页存储或轮换 key 无需重启即可用于下一次搜索。
- **错误消息内嵌配置指引。** 请求发出后的失败会指出已解析端点、说明搜索端点独立于聊天端点，并指导会话模型把用户引导到 Settings 页或 `DEEPSEEK_SEARCH_BASE_URL` / `web-search-deepseek.baseURL`；模型不得替用户选择或修改端点。

缺 key 时提供方在发 HTTP 之前失败，错误码 `WEB_PROVIDER_CREDENTIAL_MISSING`，会话里不会出现下面这条 log-only 事件。动态凭据的可用性只能在操作内部解析——同步 `available()` 无法查询异步凭据存储，因此无 key 的提供方仍会注册成功（`web_search` schema 稳定保留），到调用时才失败。凭据就绪并准备发出时，提供方会先 `append` `web/deepseek-search-llm-request`，再 `fetch` 该 Messages 端点。事件正文含 endpoint、`anthropic-version` 和秘密已剥除的 JSON body（`Perform a web search for the query: …` 与 `web_search_20250305`）；发出前发生凭据失败或取消不会创建事件，发出后的 HTTP 或响应失败则保留这次请求尝试的持久记录。

🔬 归档会话观察两则（08-28）：其一，一次实测会话在对应 `web_search` 调用旁留下该事件，字段与默认常量一致——`endpoint` 为 `https://api.deepseek.com/anthropic/v1/messages`、`apiVersion` 为 `2023-06-01`、`model` 为 `deepseek-v4-flash`、`max_tokens` 为 4096、`max_uses` 为 5，据此可判断那一次搜索走了 DeepSeek 搜索提供方；其二，另一份会话里 32 次 `web_search` 均返回 `WEB_PROVIDER_CREDENTIAL_MISSING`、无该事件，说明那一轮没有发出 DeepSeek 搜索 HTTP。返回的网页 URL 不能当判据，DeepSeek 与 Codex 都可能搜到同一页面。

Exa 是另一条账单：环境变量 `EXA_API_KEY`，插件 `@deepseek-ai/dsh-web-search-exa`，端点 `https://api.exa.ai/search`，默认组合不启用。08-28 记为"Perplexity 同类"；09-04 起 Perplexity 已是随官方仓库发布的可选包（见下节）。

> 来源：[DeepSeek 搜索默认基址与模型](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/web/web-search-deepseek/src/provider.ts#L26-L47)、[发出前记录的请求体](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/web/web-search-deepseek/src/provider.ts#L197-L218)、[事件写入会话](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/web/web-search-deepseek/src/index.ts#L117-L121)、[凭据缺失不写该事件](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/web/web-search-deepseek/README.zh.md#L49)、[Exa 的 `apiKey` 与 `$EXA_API_KEY`](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/web/web-search-exa/README.zh.md#L11-L24)；[provider id 与固定方式](https://github.com/deepseek-ai/deepseek-harness/blob/a66e4702047846cdaa10c66c9d3df3951f5ea70d/packages/web/web-search-deepseek/README.zh.md#L28)、[一次搜索=完整模型轮次](https://github.com/deepseek-ai/deepseek-harness/blob/a66e4702047846cdaa10c66c9d3df3951f5ea70d/packages/web/web-search-deepseek/README.zh.md#L32)、[完整配置表与 Settings 段投影](https://github.com/deepseek-ai/deepseek-harness/blob/a66e4702047846cdaa10c66c9d3df3951f5ea70d/packages/web/web-search-deepseek/README.zh.md#L45-L56)、[请求日志事件语义](https://github.com/deepseek-ai/deepseek-harness/blob/a66e4702047846cdaa10c66c9d3df3951f5ea70d/packages/web/web-search-deepseek/README.zh.md#L64)、[失败码与配置指引](https://github.com/deepseek-ai/deepseek-harness/blob/a66e4702047846cdaa10c66c9d3df3951f5ea70d/packages/web/web-search-deepseek/README.zh.md#L68)、[凭据逐次解析](https://github.com/deepseek-ai/deepseek-harness/blob/a66e4702047846cdaa10c66c9d3df3951f5ea70d/packages/web/web-search-deepseek/README.zh.md#L85)。🔬 本机安装树 `dsh-web-search-deepseek/lib/index.js` 的常量（默认基址、默认模型、`web_search_20250305`、`DEEPSEEK_SEARCH_BASE_URL` 回退）与上述 README 逐项一致。

### <a id="web-search-six-packages"></a>官方 web 包家族与 fetch 侧网络策略

`packages/web` 现有六个包，search 与 fetch 共用同一选择策略、取消语义与错误词汇表。提供方注册的是能力（`WebSearchProvider` / `WebFetchProvider`），面向模型的名称、schema 与展示集中在唯一消费方 `dsh-tool-web`：

| 包 | 角色 |
|---|---|
| `dsh-web` | `ctx.web` seam：search/fetch 双 provider 注册表与执行期选择 |
| `dsh-tool-web` | 面向模型的 `web_search` 与 `web_fetch` 工具 |
| `dsh-web-fetch-http` | 匿名 HTTP(S) fetch 后端，provider id `http` |
| `dsh-web-search-deepseek` | DeepSeek 原生搜索，`deepseek-official` |
| `dsh-web-search-exa` | Exa 检索端点（可选，不在默认组合） |
| `dsh-web-search-perplexity` | Perplexity chat-completions 搜索，`perplexity`（可选，不在默认组合） |

🔬 本机 0.1.2-rc.1 安装树的 `node_modules/@deepseek-ai` 里只有上表前四个 web 包——Exa 与 Perplexity 均不随默认组合安装。默认组合的 `tool-web` 行开启 `fetch: true`，并为 DeepSeek 搜索路由设 60 秒超时（provider 无关的通用默认 30 秒，base patch 注释明言搜索是带服务端检索的完整辅助模型请求）；该注释同时说明 Web 应用会停用这条 Host 行、改按 agent preset 组合两个工具。

`web-search-perplexity` 注册 id `perplexity`，走 OpenAI 兼容 `POST {baseURL}/chat/completions`（默认 `https://api.perplexity.ai`），key 回退 `$PERPLEXITY_API_KEY`，model 默认 `sonar`、`maxTokens` 1024，另有 `searchRecency`（day/week/month/year）过滤。与 DeepSeek 提供方有两处刻意差异：Perplexity 的生成答案被信任为 `content`（官方子系统文档明言 "Exa and DeepSeek return none; Perplexity returns a generated answer"）；`search_results[]` 缺失时回退到只含 URL 的 `citations[]`。

fetch 侧自带与 Agent 文件沙箱相互独立的网络边界。已交付的 preset 在所有 sandbox 和审批模式下暴露 `web_fetch`、无逐次确认；文件 sandbox 不管网络访问，需要确认步骤的部署须自加 `tools/pre-execute` 策略或禁用抓取。HTTP 提供方仅接受公开 HTTP(S) 目的地、拒绝凭证式 URL，逐请求解析并拒绝非公开 IPv4/IPv6 及经 DNS64 前缀转换到私有 IPv4 的结果，把连接固定到已验证地址，并在每次同源重定向时复检；跨源重定向需要新的工具调用与新的公开地址校验。这些检查阻止 SSRF 访问非公开目的地，但不阻止模型把数据发送到公开 URL。

> 来源：[web 包家族目录](https://github.com/deepseek-ai/deepseek-harness/tree/a66e4702047846cdaa10c66c9d3df3951f5ea70d/packages/web)；[子系统文档的 content 差异与抓取网络策略](https://github.com/deepseek-ai/deepseek-harness/blob/a66e4702047846cdaa10c66c9d3df3951f5ea70d/docs/subsystems/web.zh.md)；[web-search-perplexity README](https://github.com/deepseek-ai/deepseek-harness/blob/a66e4702047846cdaa10c66c9d3df3951f5ea70d/packages/web/web-search-perplexity/README.zh.md)。

### DeepSeek 官方 API 文档的印证

DeepSeek API 文档独立印证了从源码推出的计费模型：

- **Web Search 官方支持与额外费用**：Claude Code 接入页写明"调用 Web Search 工具会通过 DeepSeek 提供的 API 进行搜索……会产生额外的模型 Token 费用"，与 provider README 的"一次搜索消耗一个完整 Messages 轮次、DeepSeek 不提供专用检索端点"互证。
- **Anthropic 兼容基址**：文档给 Claude Code 的 `ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic`（SDK 追加 `/v1/messages`），DSH 常量 `…/anthropic/v1` 追加 `/messages`，落在同一端点。
- **模型映射**：claude-opus 前缀映射 `deepseek-v4-pro`，claude-haiku/sonnet 映射 `deepseek-v4-flash`；传入不支持的模型名会被后端自动映射到 `deepseek-v4-flash`。更新日志确认 V4-Pro 与 V4-Flash 同时支持 OpenAI 与 Anthropic 接口。
- **协议面**：兼容矩阵中 `server_tool_use` 与 `web_search_tool_result` content 类型受支持——正是 provider 解析 `sources[]` 的数据来源。

> 来源：[Claude Code 接入与 Web Search 说明](https://api-docs.deepseek.com/zh-cn/quick_start/agent_integrations/claude_code/)、[Anthropic API 兼容细节](https://api-docs.deepseek.com/zh-cn/guides/anthropic_api/)、[更新日志](https://api-docs.deepseek.com/zh-cn/updates/)（均 2026-09-04 查阅）。

### <a id="model-hub-and-search"></a>Model Hub 与搜索提供方

Model Hub 的 Host `inject` 是 `connection` 与 `settings`。它注册模型目录、Authorization 与两条 Codex 对话路由，不调用 `ctx.web.registerSearchProvider`。显示名「OpenAI Codex」不能区分下面两行：

| 路由 key | 凭据记录 | 适配器 |
|---|---|---|
| `openai-codex` | `llm-pi-ai` 的 `recordKeyFor()` | 官方 `PiAiAdapter` |
| `codex` | Model Hub 自有 native grant | Hub `NativeOAuthAdapter` |

两条路由的 token 分属不同记录范围，不能交叉刷新。

> 来源：[Model Hub 的两条 Codex 路由](#model-hub-codex-routes)、[Host `inject` 为 `connection` 与 `settings`](https://github.com/yhyfhgs/dsh-model-hub/blob/6897374e90b2f383a797e6597c011e076594f3e7/src/index.ts#L89-L90)。

若在 Model Hub 进程内再注册搜索提供方：搜索 registry 的 id 与 LLM 路由 id 是两套表；搜索 id 写成 `openai-codex` 时，与 [`dsh-codex` 使用同一搜索 id](https://github.com/Yan-Zero/dsh-codex/blob/e3e54e206f7c829503c7e6eed378643ba0416792/src/search.ts#L19-L26) 并存会触发 `WEB_DUPLICATE_PROVIDER`。LLM 侧再注册 `openai-codex` 适配器会与官方 / Hub 已占路由冲突。默认组合已钉 `deepseek-official`，不改 `web.searchProvider` 则新提供方不会被选中。

### <a id="community-codex-search-plugins"></a>把 `web_search` 接到 Codex 订阅的插件

这些插件把现有 `web_search` 接到 ChatGPT Codex 独立搜索，同时各自再注册 `openai-codex` 对话适配器：

| 项目 | 搜索后端 | 搜索提供方 id |
|---|---|---|
| [`dsh-codex`](https://github.com/Yan-Zero/dsh-codex/tree/e3e54e206f7c829503c7e6eed378643ba0416792) | 固定 `https://chatgpt.com/backend-api/codex/alpha/search`，与对话共用 ChatGPT OAuth；bundle 把 `searchProvider` 设为 `openai-codex` | `openai-codex` |
| [`dsh-codex-subscription`](https://github.com/WSL043/dsh-codex-subscription/tree/a738dbaf5a48101c0b153421e4abdd28dddab100) | 同一 Codex 独立搜索；设置可在 DSH 默认搜索、Codex 搜索与按对话路由自动切换之间选择；失败时不改走另一条付费路由 | 自有 Codex 搜索 id，外加自动切换包装 |

`dsh-codex` 的搜索实现还固定：端点不可配置，以免 bearer 被转到其他 origin；`available()` 只做本地检查；只收录 `http:` / `https:` 的 `text_result`；取消为 `WEB_ABORTED`，401/403 为 `WEB_PROVIDER_CREDENTIAL_MISSING`；诊断文本去掉 JWT 形态。

09-04 复核近况：`dsh-codex` 在 08-28 固定的 `e3e54e2`（v0.2.5）之后，09-02 有两笔兼容修复——[为 0.1.1-rc.2+ runtime 补 provider profile 的图片请求预算字段](https://github.com/Yan-Zero/dsh-codex/commit/d68f9c9e3a33505440d6c093323b3df710c8c74e)（缺字段会让带图请求报 "Image request maxPixels must be a positive integer"）与 [Codex 上下文窗口覆盖](https://github.com/Yan-Zero/dsh-codex/commit/f87033b34fe17452cc64daa65ea3a9fcb88a65e8)；最近三笔提交都不触及 `src/search.ts`，上表搜索结论维持。`dsh-codex-subscription` 09-02 提交 [chore: support DSH 0.1.2-alpha.5](https://github.com/WSL043/dsh-codex-subscription/commit/17994051cf3d5680be802039171bceadfe077295)，持续跟进新 runtime，其搜索切换设计未见变更提交。

> 来源：[Codex 独立搜索 URL 与提供方 id](https://github.com/Yan-Zero/dsh-codex/blob/e3e54e206f7c829503c7e6eed378643ba0416792/src/search.ts#L19-L26)、[`dsh-codex` 用现有 `web_search`](https://github.com/Yan-Zero/dsh-codex/blob/e3e54e206f7c829503c7e6eed378643ba0416792/README.zh.md#L12-L13)、[`dsh-codex-subscription` 的搜索切换](https://github.com/WSL043/dsh-codex-subscription/blob/a738dbaf5a48101c0b153421e4abdd28dddab100/README.zh-CN.md#L52)。

[`dsh-plugin-subscriptions`](https://github.com/V1ki/dsh-plugin-subscriptions/tree/08b9b7cc30e72e8eedd559ac01af9fc576157453) 在 Grok 登录后注册 `x_search`，搜的是 X/Twitter，不是网页 `web_search`。它还自建 `codex` / `claude` / `grok` / `copilot` 对话适配器，与 Model Hub、官方 `openai-codex` 占用同一类路由名。

> 来源：[随 Grok 启用的 `x_search`](https://github.com/V1ki/dsh-plugin-subscriptions/blob/08b9b7cc30e72e8eedd559ac01af9fc576157453/README.zh.md#L50-L54)。

### <a id="dsh-tui-search-related"></a>dsh-TUI 与 dsh-auth 的登录范围

[`dsh-auth`](https://github.com/ccch1mneyyy/dsh-TUI/blob/99b8b147a22ba3e3c55a9c909c543331b4e46cae/dsh-auth/README.md) 给对话做 OAuth，路由为 `openai-codex`、`anthropic`、`xai`。README 把 Gemini 列为 M4，并写明 pi-ai 不提供 Google 登录。它不注册 `WebSearchProvider`。

TUI 时间轴等界面有从 grok-pager 借来的交互，那是 UI，不是 Grok 网页搜索。生态规范测试里有按对话 provider 覆盖 `web_search` 执行的夹具，不随 TUI 发布 Gemini 或 Grok 搜索提供方。

同一 Web profile 上再装 `dsh-auth` 或 `dsh-codex`，会与 Model Hub / 官方 `llm-pi-ai` 争夺 `openai-codex` 适配器。`dsh-auth` 对已被占用的路由会拒绝挂载。

> 来源：[dsh-auth 的 OAuth 路由](https://github.com/ccch1mneyyy/dsh-TUI/blob/99b8b147a22ba3e3c55a9c909c543331b4e46cae/dsh-auth/README.md#L43-L47)、[Gemini 列为 M4](https://github.com/ccch1mneyyy/dsh-TUI/blob/99b8b147a22ba3e3c55a9c909c543331b4e46cae/dsh-auth/README.md#L128-L136)、[已被占用的路由拒绝注册](https://github.com/ccch1mneyyy/dsh-TUI/blob/99b8b147a22ba3e3c55a9c909c543331b4e46cae/dsh-auth/README.md#L93-L96)。

### <a id="web-search-community-providers"></a>直接实现 WebSearchProvider 的社区插件

08-28 时社区只有"把 web_search 接到 Codex 订阅"一类；一周内出现了直接实现 `WebSearchProvider` seam 的独立插件类别。`dsh-web-search-brave` 的 README 明言其结构参考官方 `dsh-web-search-deepseek`（MIT）按 seam 规范实现——官方 provider 事实上成了社区模板。

| 插件 | 搜索后端 | 计费 | 关键特征 |
|---|---|---|---|
| [`dsh-web-search-anysearch`](https://github.com/mcxianyujun/dsh-web-search-anysearch/tree/2431cdd8d3294be594340deec09b6b03dd81f65a) | AnySearch `POST /v1/search` 原生 REST | key 额度 | `ANYSEARCH_API_KEY` 走 credentials 服务；Web+Headless 双 profile；卸载只删自己的 `searchProvider: anysearch` 覆盖、不强制改回官方；在[官方仓库 discussions #2671](https://github.com/deepseek-ai/deepseek-harness/discussions/2671) 发布 |
| [`dsh-web-search-brave`](https://github.com/LTctfer/dsh-web-search-brave/tree/9da844e6d768bd6088cc0213cbd17fd34e1167f1) | Brave `/res/v1/web/search` | Brave 订阅 | 纯检索端点（一次 HTTP、无模型轮次）；key 三选一（设置页 / 环境变量 / 凭据文件）；因 settingsScope 白名单只认官方 namespace，自建 loopback settings bridge |
| [`dsh-web-search-searxng`](https://github.com/acdcgz/dsh-web-search-searxng/tree/1b54a6249c2c21d4c5046fde3d779b028f4a53b3) | 自托管 SearXNG JSON API | 自托管 | provider id `searxng-local`；`dsh.bundle.patch` 让一条 `dsh plugin add` 同时装插件并切 provider；仿官方记 `web/searxng-search-request` 日志事件；附 Docker Desktop 限流绕过说明 |
| [`dsh-web-search-zai`](https://github.com/kenny2077/dsh-web-search-zai/tree/8420b3f1c4c27a57b3a7cc02fd8c12db7e7fc9fa) | Z.ai / 智谱双端点 | Coding Plan MCP 点数或 API 余额 | `billingMode` 二选一：coding-plan 走 `web_search_prime` MCP（Z.ai 国际 / 智谱中国双 URL），api 走 REST `/web_search`；0.2.0 起默认从 REST 改为 Coding Plan，旧用户须显式选回 api；key 走 credentials、卡面不回显 |
| [`dsh-free-search`](https://github.com/DDDMUC/dsh-free-search/tree/be190fa6e915116c4575ac7a0b02577f1ca3b7e7) | 多引擎聚合 | 免费+付费混合 | 引擎链 ddg / ddg-lite / bing（默认）/ anysearch / searxng / exa / tavily / keenable / perplexity / deepseek-official，统一自动回退、"搜索永不直接失败"；`/free-search-engine` 弹窗切换、`advanced_search` timeRange、`platform_search`（GitHub/B站/HN 等 8 平台）、5 分钟 LRU 缓存 |

共同模式与边界：

1. **成本叙事成为主要卖点。** brave / searxng / free-search 都以"一次搜索 = 一次 HTTP，而非 DeepSeek 官方的一次模型轮次"定位；免费引擎靠 keyless 匿名额度（Tavily `x-tavily-access-mode: keyless` 头、Exa / Keenable 公开 MCP 端点匿名调用）与回退链维持可用性，DDG / Bing 的反爬限流是主要失效模式。
2. **覆盖 `searchProvider` 的两条途径。** 手写 profile patch 覆盖 `web` 行 config（brave 的 README 示例），或像 searxng 那样在 `dsh.bundle.patch` 里自带切换、装完即生效。
3. **Settings 集成的多种 workaround。** settingsScope 白名单只对官方 namespace 开放（brave README：第三方 namespace 一律"设置段不可用"），社区因此分化出：自建 loopback settings bridge（brave、free-search 的 `/api/dsh-*-settings` 路由）、挂官方 `settings.plugin.item` 插槽自渲染卡片（free-search）、以及跟进新版注册 API——free-search 09-03 的提交专门做了"alpha+ 用 `installSection`、rc.2 回退 `installSettingsSection`"的双兼容，说明 0.1.2 系列改过 settings 注册面。
4. **归属注意。** searxng 仓库的 package.json 使用 `@deepseek-ai/` scope 名（用于本地 link 安装、未发布 npm）；安装第三方包前应核对真实发布者，scope 名不等于官方归属。zai README 也自注"目录收录不意味官方 DSH 或 Z.ai 背书"。
5. **外部印证。** [掘金文章](https://juejin.cn/post/7673816823688003630)实测"主模型切到 opencode 后 `web_search` 仍走 DeepSeek 官方计费"、[DataCamp 教程](https://www.datacamp.com/zh/tutorial/deepseek-harness)写明"默认搜索 provider 与模型共用同一 DeepSeek API key"——与本节源码结论一致。

> free-search 的 README 声称 "`web_fetch` 无 SSRF 防护、agent 理论上可访问内网地址"，与官方子系统文档和 base patch 注释矛盾：官方 fetch 后端逐请求解析并拒绝非公开目的地、pin 连接、同源重定向复检（见[官方 web 包家族与 fetch 侧网络策略](#web-search-six-packages)）。该说法应视为过时或不准确。

> 来源：上表各仓库 README（固定到表内 commit）；[AnySearch 发布讨论](https://github.com/deepseek-ai/deepseek-harness/discussions/2671)；周边文章 [InfoQ 的 anysearch-dsh 安装教程](https://www.infoq.cn/article/bfZzslUtldTMeEgYuVhe)与[博客园的免费搜索插件记录](https://www.cnblogs.com/dqtx33/p/22579950)（2026-09-04 查阅，仅作发现信号）。

### 原专题结论的现状核对

| 原结论（08-28 及更早） | 现状（09-04） |
|---|---|
| 账单跟搜索提供方走，与对话模型无关 | 维持；官方文档与社区文章双向印证 |
| `dsh-base` 钉死 `searchProvider: deepseek-official` | 维持；同一 `web` 行新增 `fetchProvider: http` |
| DeepSeek 搜索走 Anthropic 兼容 Messages + `deepseek-v4-flash` + `DEEPSEEK_API_KEY` | 维持；配置面新增 baseURL / model / apiVersion / maxTokens / maxUses 与 `$DEEPSEEK_SEARCH_BASE_URL` |
| `web/deepseek-search-llm-request` 是判据事件 | 维持；补充"发出前凭据失败或取消不建事件，发出后失败保留记录" |
| Exa 是另一条账单，Perplexity 同类 | 更新：Perplexity 已是官方可选包，默认组合仍不装两者 |
| 多 provider 未钉时抛 `WEB_PROVIDER_AMBIGUOUS` | 维持；选择错误扩为四态，另有 `$DSH_WEB_SEARCH_PROVIDER` 入口与 `WEB_DUPLICATE_PROVIDER` 注册期错误 |
| Model Hub 不注册搜索提供方 | 09-04 未重读 Model Hub 源码，维持原记录 |

### 验证范围

- 未把任何社区搜索插件装进 Profile 做端到端；免费引擎 keyless 额度、回退链行为与 MCP 点数消耗（zai README 自述智谱测试"一次搜索消耗一点"）均为项目自述。
- 🔬 覆盖范围仅为：本机 0.1.2-rc.1 安装树的包清单、provider 常量与 README 行号核对，以及 08-28 的两段归档会话观察；未发真实搜索请求。
- 两份社区 README 对 profile patch 热重载的描述互相矛盾（brave 称"保存即生效"、searxng 称"Web profiles 按设计禁用 HMR、需重启"），与官方 CLI reference 的"运行进程监视 Profile patch"表述也不一致；未实测裁决，列为待验证。
- free-search 的 v0.4.x 迭代很快（README 内嵌的版本截图文字与 HEAD 提交版本号已不同步），引用其细节时以仓库 HEAD 为准。
- 官方包家族与 provider 行为以 0.1.2-rc.1 为快照；DSH 处于 developer preview，settings 注册面等接口在 0.1.2 系列内已经变动（free-search 为此做双兼容），引用本节细节时先确认当前版本。
