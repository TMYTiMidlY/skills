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

### Model Hub 的 Codex 路由

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
