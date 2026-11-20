# DeepSeek Harness（dsh）Plugin 调研记录

本文件按日期记录 DSH 社区 Plugin 的检索与源码调研，保留调研时间、目标、候选仓库、证据边界、阶段结论和后续验证。运行 DSH、安装或卸载现成 Plugin 及判断权限边界见 [DeepSeek Harness 运行时](dsh.md)；Cordis 插件框架怎样组织插件、叠加配置、协作和清理，以及可复用的实现、测试与发布方法，见 [DeepSeek Harness Plugin 开发](dsh-dev.md)。这里保留调研过程，避免后来只剩脱离证据的选型结果。

直接远程访问官方 Web 的部署参数、认证、反代与客户端兼容统一见 [dsh-public-web README](https://github.com/TMYTiMidlY/dsh-public-web)。本篇的社区客户端与中继协议调研保留各自日期和版本边界。

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

`dsh-model-hub` 的实现可以分成两类：

| 实现 | 代表路由 | 登录、凭据与请求归属 | Model Hub 的职责 |
|---|---|---|---|
| **官方 pi-ai 路由** | `openai-codex` | 使用 DSH 官方 `llm-pi-ai` 的登录流程、凭据记录、Token 刷新和 `PiAiAdapter` | 替换 Models 页面，调用 `authorization.begin()`，展示交互状态，并写入空的无 API Key 配置激活官方路由 |
| **插件 native 路由** | `qwen-code`；当时快照还包括内建 `codex` | Model Hub 自己实现 OAuth、凭据记录和 Native Adapter | 维护官方 Pi 目录之外的模型服务，或对特定路由自行控制模型目录和错误行为 |

两类路由可以共用同一个 UI，但不能混淆归属：第一类主要复用官方链路，第二类需要由插件维护登录流程、Token 生命周期和模型适配器。`qwen-code` 不在当时的 Pi 内置目录中，因此属于第二类；内建 `codex` 则与官方 `openai-codex` 并存，属于另写链路的历史例子。

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

## <a id="2026-08-27-file-transfer-artifacts"></a>浏览器文件传输与产物交付

本章区分浏览器上传、模型按需读取、会话内文件交付和浏览器下载，结合官方版本演进与社区 Plugin 源码确定采用方式。目标是普通文件只附加引用、由模型随后自行读取；上传阶段不自动提取正文、OCR 或请求外部视觉服务。图片作为原生模型输入时另有能力检查，不能用“支持任意文件”概括两条不同流程。

> **核对口径：** 首次调研于 2026-08-27，复核于 2026-09-10（Asia/Shanghai）。本章官方能力说明以 2026-09-10 发布的 `dsh-v0.1.5-rc.1` 为源码依据，commit `183f08e9c6dde7e36cd2318eaee70b0da08fb35e`；功能引入时间另按对应 Release 标注。

**最终决策：** 上传采用官方通用附件；输出采用官方 `present` 文件交付，不再把 Plik 上传后返回 URL 作为默认方案，也不额外安装社区上传或产物插件。这个选择以“在会话中收到文件交付卡并打开或预览”为交付目标；`present` 不提供浏览器下载链接、不保存文件副本，不能据此宣称已替代所有跨设备下载或外部分发需求。若后续明确要求下载到访问端设备，需单独确认传输方式；下文社区项目保留为比较证据，不作为最终决策。

> **证据边界：** 官方参考仓库已 fetch 并检出上述 tag，工作区干净、非 shallow；未升级运行中的 `0.1.2-rc.1` 服务。2026-09-10 的候选发现使用 xAI、Z.AI、Codex 三路搜索，关键结论回到固定源码和 npm 元数据复核，未安装插件或进行真实浏览器上传验收。旧审计以 `0.1.1-rc.2@b150a551` 为基线；旧 Stars、测试次数与兼容性判断仍按 2026-08-27 标注，不推及其他版本。来源：[0.1.5-rc.1 发布说明](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.1.5-rc.1)。

### <a id="file-transfer-official-chain"></a>官方文件链路

官方自 2026-09-04 发布的 `0.1.3-alpha.1` 起支持通用文件上传：浏览器拖拽、粘贴或选择文件，后台上传支持进度、取消和会话切换续显；文件保存完成后，发送消息引用该 Session 的上传回执，再形成持久 `FileBlock`。文件正文不会因为上传而进入模型请求，所有模型路由都把 `FileBlock` 转为文件名、字节数、哈希摘要和只读路径的一行文字，模型需要时才调用文件工具。这里的“摘要”是 SHA-256 内容摘要，不是自动生成的内容总结。

> 来源：[通用上传的发布说明](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.1.3-alpha.1)、[上传服务与回执生命周期](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.5-rc.1/packages/client/file-upload/README.md#L10-L52)、[文件回执随消息提交](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.5-rc.1/packages/client/ui-conversation/src/client/service.ts#L240-L295)、[所有模型统一接收路径文字](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.5-rc.1/packages/llm/llm/src/content.ts#L146-L204)。

TXT、PDF、Office、ZIP、音视频及未知二进制均可原样保存，通用文件没有类型白名单或应用层大小上限，零字节文件也被存储实现接受。对象按内容寻址并设为只读，保留原文件名的安全形式；会话恢复与 fork 可引用相同对象。存储实现不自动清理文件，实际上传受磁盘容量、网络、代理和运行环境限制；“可附加”不承诺模型能解析所有格式。执行环境不能映射附件路径时，模型收到明确的不可读取提示；只共享 Host 的附件库不等于远程沙箱自动获得文件。

> 来源：[通用文件的存储与保留说明](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.5-rc.1/packages/attachment/attachment/README.md#L38-L71)、[原样流式保存和安全文件名](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.5-rc.1/packages/attachment/attachment-local/src/file-store.ts#L35-L137)、[零字节文件用例](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.5-rc.1/packages/attachment/attachment-local/tests/file-store.spec.ts#L73-L95)、[无法映射读取路径时的提示](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.5-rc.1/packages/llm/llm/src/content.ts#L154-L160)。

PNG/JPEG/WebP/GIF 按浏览器 MIME 自动进入原生图片流程，而不是通用文件流程。图片会规范化后直接进入模型请求；发送时仍拒绝明确不支持图片的模型。普通文件没有这个视觉能力门禁，因此文本模型可以附加 TXT、PDF 等，但默认 UI 不提供“把这张图片仅作为普通文件附加”的选择。这个例外不构成继续安装通用上传插件的理由；若需要所有图片也延迟读取，应单独设计明确的文件输入模式。

> 来源：[按 MIME 创建图片或文件草稿](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.5-rc.1/packages/client/ui-conversation/src/client/service.ts#L298-L325)、[仅对图片检查模型能力](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.5-rc.1/packages/api/session-controller/src/commands.ts#L335-L375)。

官方自 2026-09-09 发布的 `0.1.5-alpha.2` 起提供 `present` 文件交付，Web `standard`、`ptc`、`cordis` preset 挂载该工具。模型创建文件后调用它，普通文件不按扩展名筛选，默认每次最多八个；路径必须存在、是会话文件系统可访问的普通文件，目录、最终符号链接和被文件策略拒绝的路径不能交付。示例调用：

```json
{"files":[{"path":"out/report.pdf","description":"报告"},{"path":"out/data.xlsx","description":"数据表"}]}
```

成功调用记录 `deliverables/presented`，聊天显示文件卡；支持的格式可在右侧 Sidebar 预览，也可请求在 Host 默认应用中打开或定位文件。`present` 只记录路径和说明，不读取或复制正文，不生成公网 URL，也不触发浏览器下载。修改源文件会改变后来打开的内容；删除源文件会让交付失效；Session ZIP 只带交付声明，不带源文件字节。文件工具产生的“Files changed”行与显式交付不同，Bash 创建的最终产物也应调用 `present`。

> 来源：[文件交付的发布说明](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.1.5-alpha.2)、[`present` 参数、文件门禁与默认数量](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.5-rc.1/packages/fs/tool-present/src/index.ts#L38-L106)、[preset 与交付内容保留范围](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.5-rc.1/packages/fs/tool-present/README.md#L25-L92)、[文件卡、Sidebar 和 Host 打开动作](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.5-rc.1/packages/client/ui-deliverables/README.md#L28-L55)。

> **旧版本对照：** `0.1.1-rc.2` 和本次检查的安装版 `0.1.2-rc.1` 仍只有图片上传，旧 Produced 行主要交给 Host opener；这些限制适用于上述两个版本，不能据此判断 `0.1.3` 及后续版本的上传能力。`0.1.3-alpha.1` 有 GitHub Release，2026-09-10 查询 npm 时没有该版本条目，不能把“首次写入发布说明”当成可安装包已存在；部署前应核对选定版本实际发布状态、Session 格式迁移和现有 Plugin 兼容性。

### <a id="file-transfer-repository-snapshot"></a>仓库快照

下表记录社区项目的源码版本、功能范围和发布情况，供比较实现方式；最终采用方案仍是官方上传与文件交付。

> **表格口径：** 版本、Stars 和测试信息采集于 2026-08-27。2026-09-10 复查时，`l541402398/dsh-file-uploads` 与 `WJZ-P/dsh-attachments` 的仓库 HEAD 仍是表中 SHA，未发现修复旧审计问题的后续提交；其余行保留原快照。测试文件或 CI 的存在不代表插件已通过真实 DSH Web 组合验收。

| 仓库 | 版本 / commit | Stars | 主要范围 | 测试与发布信号 |
|---|---|---:|---|---|
| [`dsh-file-upload`](https://github.com/HongMing-Huang/dsh-file-upload/tree/ce4ca943da592be36a784a5648d36a600aeda136) | `0.5.2` / `ce4ca94` | 20 | 拖入、粘贴、选择、文档转换 | 4 个测试文件；Node 22/24 CI；当时 npm 版本为 `0.4.3` |
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

旧表十一份仓库的 GitHub `created_at` 均在 2026-08-14 至 2026-08-25；部分项目继承的完整 Git 历史更早。Stars 只是早期关注度快照，不能替代安全、兼容和持久性审计。

补充候选覆盖仅附加路径、原生图片分流和文档读取工具等不同路线，功能与适用场景见[浏览器文件输入 Plugin](#file-transfer-input-plugins)。

> **补充候选口径：** 下表于 2026-09-10 核对。版本列分别记录源码包声明和 npm 发布元数据；仓库版本、README 安装示例或搜索目录的“可安装”标记均不等于实际安装验收。

| 候选与源码 | manifest 版本 | 发布与适配证据 |
|---|---|---|
| [`Johnny-xuan/dsh-paste-to-path`](https://github.com/Johnny-xuan/dsh-paste-to-path/tree/5c831284cb4474a7d942dd09eaabdabb228c701d) | `0.0.6` | npm `dsh-paste-to-path@0.0.6`；声明 DSH peers `>=0.1.2-rc.1 <0.2.0`，发布包未逐字节比对 |
| [`CocoSgt/dsh-attachments`](https://github.com/CocoSgt/dsh-attachments/tree/70c0b7e81d7d6a2707e282457bd92f2577bd6629) | `0.1.1` | npm `dsh-attachments@0.1.1` 的 `gitHead` 为 `a293f9f`，与仓库 HEAD 不同；两个提交的 intake 均为全部文件落盘，旧 DSH 依赖仍需组合验证 |
| [`demacia1314/dsh-airdrop`](https://github.com/demacia1314/dsh-airdrop/tree/08e40f217ef80ceb96ead9e22d09499e8c0d5f69) | `0.2.1` | 源码声明适配 rc.1；npm `dsh-airdrop` 返回 404，旧包 `dsh-universal-attachments@0.1.2` 的 peers 不覆盖 `0.1.2-rc.1` |
| [`loudMore/dsh-drop-to-path`](https://github.com/loudMore/dsh-drop-to-path/tree/a00a5a2e18fd89e829b1c96f2f2e85af67366e10) | `0.1.0`，private | 只确认源码；发送包装与 rc.1 返回值不兼容 |
| [`Mooling0602/dsh-web-file-uploader`](https://github.com/Mooling0602/dsh-web-file-uploader/tree/eafb06649a540f8292e230738ac2179f87acd48e) | `0.3.2` | 只确认该源码的模型分流与 HTTP 入口 |
| [`GLFzr/dsh-file-upload`](https://github.com/GLFzr/dsh-file-upload/tree/dc23ac42271fd93814924cd5822992501f7fb654) | `2.1.0` | 原 `dsh-drop-file-to-path` 地址重定向到此；npm `dsh-file-upload@0.4.3` 属于 HongMing-Huang，不能按同名包安装本项目 |
| [`hyper-dsh-plugins/dsh-open-file`](https://github.com/hyper-dsh-plugins/dsh-open-file/tree/39636d198993c5980da0091056d307bb5a8a48c5) | `0.1.2-rc.1` | npm 同版本存在，DSH peers 精确匹配该版本；未在运行中的 Profile 验收 |
| [`xzyonline/dsh-file-attachments`](https://github.com/xzyonline/dsh-file-attachments/tree/7a0f0f47358366ed084de7a065d892fe6206e434) | `0.3.0`，private | 仓库更名为 `dsh-chat-files`，内部包名仍为 `@dsh-external/dsh-file-attachments`；旧 peers 不证明 rc.1 兼容 |
| [`liznee/dsh-file-resource`](https://github.com/liznee/dsh-file-resource/tree/17650ab1b7ceb08b19338f81ff8f7f9b4f5cf86f) | `0.4.9` | npm 同版本；本轮核对 README 与发布信息，未重做完整源码审计 |
| [`sharkymew/dsh-utility-tools`](https://github.com/sharkymew/dsh-utility-tools/tree/d8ee3a77aed2c5446942073470faaa9de9ecd98a) | `1.0.5` | npm 同版本与 `gitHead`；核对 README 和 Host 实现 |

> **安装名不能混用：** `CocoSgt/dsh-attachments` 的 npm 包名是 `dsh-attachments`，`WJZ-P/dsh-attachments` 的包名是 `dsh-attachment`；`l541402398/dsh-file-uploads` 是第三个独立项目。2026-09-10 查询 registry 时，前两个包分别发布为 `0.1.1`、`1.0.1`，第三个同名包返回 404。版本元数据不替代发布包与真实会话验收；`dsh-attachments@0.1.1` 对应提交的[文件接收实现](https://github.com/CocoSgt/dsh-attachments/blob/a293f9fff1b808aa4644f7ef1a1b9ec51ae4d4b5/src/client/intake.ts#L118-L139)也将图片作为普通文件暂存。

### <a id="file-transfer-input-plugins"></a>浏览器文件输入 Plugin

输入插件主要采用两种方式：把浏览器文件真正上传到 Host，或寻找 Host 上已经存在的文件并引用其路径。只有前者能接收远程浏览器所在设备上的新文件。比较时还要看图片是否直接发送给模型、文档是否自动解析，以及附件能否随会话恢复。

> 下表依据 2026-08-27 的源码审计，兼容性基线为 DSH `0.1.1-rc.2`。

| Plugin | 浏览器入口与字节落点 | 模型如何取得文件 | 下载覆盖 | 关键边界与 rc.2 状态 |
|---|---|---|---|---|
| `l541402398/dsh-file-uploads` | 只有文件选择器；raw body 流式写入全局 `$DSH_HOME/uploads` | submit 时把 Host 绝对路径作为普通文本写进用户消息 | Settings 中可下载输入文件；无逐消息附件下载；无产出下载 | Host/Origin/Sec-Fetch-Site fence、100 MiB 单文件、1 GiB 总量、临时文件、fsync、同名编号与流式下载均有实现；所有 Session 共享可枚举目录，且没有 TTL、GC 或 Session 删除联动，手动删除可使旧消息路径失效。`0.1.1-rc.2` 静态接口匹配，但没有真实组合测试 |
| `WJZ-P/dsh-attachments` | 页面级拖拽；普通文件和目录流式写入私有 object store，提交时复制到 `.deepseek-harness/attachments/` | 把工作区副本路径和附件 metadata 追加进用户消息 | 历史普通文件可按 Session 下载；目录不能下载；无产出下载 | 无单文件、数量或总容量上限；路由无 Host/Origin fence；工作区复制缺少 realpath/no-follow。rc.2 的 `conversation.input.attachments` 已被官方 single occupant 占用，插件同优先级注册会冲突，组件 props 也不符合当前 Slot owner，静态判定不能直接使用 |
| `re-ITRT/dsh-file-fix` | 拖拽、粘贴、文件选择器；FileReader 转 base64，经 Typert 写入内容寻址附件库 | pre-step 注入 attachment id；`read_attachment` 读文本，`place_attachment` 复制二进制到工作区 | 历史输入附件有下载；无产出下载 | 50 MiB 单文件在 Host 强制，20 文件/200 MiB 批量限制主要靠客户端；上传和下载全量缓冲。下载、Remote 与 Tool 没有 Session ownership；直接 Node 写入有 symlink/TOCTOU；自定义 `filefix/files` 不是官方已知且不能写 `ignorable`，rc.2 恢复会拒绝该事件；无测试/CI |
| `HongMing-Huang/dsh-file-upload` | 文件选择器、拖拽、粘贴、目录展开；整包缓冲后写入 `<cwd>/.dsh-uploads/<sessionId>` | 发送 Host 绝对路径，并引导调用 `read_document`；图片可走官方 `read_image` 或外部视觉描述 | 无输入下载；无产出下载 | DELETE 只做字符串前缀校验，`<storage>/../../victim` 可越界删除，属于 Critical；route 绕过标准 `/api` fence，只有可伪造 Host regex；无总容量，上传和转换放大内存。text-only 路由可能在没有逐文件确认时把图片发到自动发现的 OpenAI-compatible 视觉端点；`read_document` 的 renderer 只向模型展示两行；client scoped event、错误状态、相对路径和清理器还有确定性缺陷。仓库 0.5.2 无构建产物，npm 0.4.3 又是旧代码，peer rc.6 不覆盖 rc.2 |
| `akiracod/dsh-drag-and-drop` | 不复制普通文件；从 URI 或 Host 搜索恢复绝对路径，必要时比较 metadata、结构与摘要；纯图片仍走官方图片链 | 发送绝对路径普通文本，模型再自行调用文件 Tool | 无输入或产出下载 | 只适合同一文件系统命名空间；远程浏览器、容器、WSL 或异构 OS 会失配。裸 locator route 无 trust fence，roots、candidates 与 phase 由客户端控制，可做路径 oracle 和 I/O DoS；唯一 name+size/name 候选可能错认，同一 pending 队列还可跨 Session 发送 |

> 来源：[`dsh-file-uploads` 的 trust fence、原子写入和下载](https://github.com/l541402398/dsh-file-uploads/blob/3ea46e1583eac426cc34e191ea811e71b0c8347e/index.js#L109-L221)、[`dsh-file-uploads` 的配额与流式响应](https://github.com/l541402398/dsh-file-uploads/blob/3ea46e1583eac426cc34e191ea811e71b0c8347e/index.js#L304-L425)、[`dsh-attachments` 的上传、工作区复制和下载](https://github.com/WJZ-P/dsh-attachments/blob/c94ec8b38a126b8ab919dd3849cd88560f0063a6/src/index.mjs#L202-L254)、[`dsh-attachments` 的文件 route](https://github.com/WJZ-P/dsh-attachments/blob/c94ec8b38a126b8ab919dd3849cd88560f0063a6/src/index.mjs#L283-L460)、[`dsh-file-fix` 的模型注入](https://github.com/re-ITRT/dsh-file-fix/blob/64ab40fe6a2bc91ea50ca57d67137ec6a7410d00/src/attach.ts#L25-L31)、[`dsh-file-fix` 的无 Session 下载 route](https://github.com/re-ITRT/dsh-file-fix/blob/64ab40fe6a2bc91ea50ca57d67137ec6a7410d00/src/http.ts#L23-L59)、[`dsh-file-upload` 的缓冲上传与落盘](https://github.com/HongMing-Huang/dsh-file-upload/blob/ce4ca943da592be36a784a5648d36a600aeda136/src/upload.ts#L117-L230)、[`dsh-file-upload` 的 DELETE 校验](https://github.com/HongMing-Huang/dsh-file-upload/blob/ce4ca943da592be36a784a5648d36a600aeda136/src/upload.ts#L241-L277)、[`dsh-file-upload` 的视觉端点自动发现与传输](https://github.com/HongMing-Huang/dsh-file-upload/blob/ce4ca943da592be36a784a5648d36a600aeda136/src/vision.ts#L60-L121)、[`dsh-drag-and-drop` 的客户端权威搜索范围](https://github.com/akiracod/dsh-drag-and-drop/blob/c20646ad6d4ee4c4a0ef12163a074716e17a7ba5/src/locator.ts#L79-L109)。

**社区方案的取舍：** 如果能够使用官方通用附件和 `present`，优先采用官方方案，减少重复的存储、会话恢复和界面适配。必须保留 DSH `0.1.2-rc.1`，或要求图片也仅按文件附加时，社区候选才值得进一步验证：

- **仅附加路径：优先验证 `dsh-paste-to-path`。** 拖拽、粘贴和选择器齐全，图片也只生成路径引用，且声明适配 `0.1.2-rc.1`，与目标最接近。图片预览接口、目录授权和待发送状态恢复仍有缺口，应先修正并验证，不能直接视为可靠的生产方案。
- **同类备选：`CocoSgt/dsh-attachments`。** 同样把所有类型当作文件，功能方向合适；旧依赖、写入保护和状态恢复需要更多适配。它可作为全类型接收流程的参考，优先级低于 `dsh-paste-to-path`。
- **只需文件选择器：考虑 `dsh-file-uploads`。** 功能较少，但上传大小与总量限制、避免覆盖的写入方式较明确。适合简单上传需求；缺少拖拽和会话级存储隔离，不作为完整交互方案。
- **大文件和文件夹：`dsh-airdrop` 的传输管理较完整。** 分块上传、续传、目录处理、配额和待发送状态恢复覆盖较多，适合研究这类能力；但它会自动发送图片块，因此不适合“所有文件只附加路径”的严格要求。
- **按需文档处理：`dsh-open-file` 的工具范围较完整。** 提供检查、读取、本地 OCR 和页面渲染，并有工作区与资源限制，适合另外需要这些工具的场景；常见图片走原生输入、部分格式被拒绝，不能替代纯粹的任意文件暂存。

> **比较口径：** 以下依据 2026-09-10 的源码审计，兼容性重点为 DSH `0.1.2-rc.1`。这些倾向用于选择后续验证对象，不改变本章采用官方方案的决策；未安装候选或完成浏览器验收，安全问题也未对运行服务作利用测试。

| Plugin | 上传与模型可见内容 | 关键限制或不采用原因 |
|---|---|---|
| `Johnny-xuan/dsh-paste-to-path` | 拖拽、粘贴、无类型限制的文件选择器；所有文件原样上传，引用 codec 只生成路径文字，图片预览仅在浏览器，不自动解析或请求模型 | 默认 25 MiB/文件，路由复用 `connection.requestRejection`，文件 `0600`；但目录仍取客户端参数，缺少完整 Session-cwd 和符号链接防护，无总量配额或磁盘 GC，索引主要在内存。图片预览引用 rc.1 未导出的 `ImageLightbox`，静态判断点击预览可能失败；未做浏览器复现 |
| `CocoSgt/dsh-attachments` | 拖拽、粘贴、文件选择器；所有类型含图片均 `stashFile`，在 pre-step 追加标准文本消息中的路径和元数据，无图片块或自动解析 | 32 MiB/文件、30 个待发送项；通过 DSH Typert 通道传输。客户端提供的目录未与真实 Session 绑定，写入缺少充分的原子发布和 no-follow 防护；重启丢待发送状态，无配额/GC，旧依赖及 DOM 假设需验收 |
| `demacia1314/dsh-airdrop` | 文件和目录分块直传会话工作区，普通文档保留路径；**pre-step 会自动验证、保存常见栅格图片并追加 `ImageBlock`**，没有发现仅按文件附加的开关 | 图片分支没有模型能力检查，不符合全部类型延迟读取。路径保护、文件权限、流式配额和待发送状态恢复覆盖较多；图片输入方式与只附加目标不同，源码与 npm 发布状态也不一致 |
| `loudMore/dsh-drop-to-path` | 图片与普通附件通常转为工作区路径，但存在扩展名白名单；图片上传失败会回退原生图片发送 | 不支持所有格式，上传失败还可能改为直接发送图片；修改 `sendSession` 后成功分支返回 `undefined`，rc.1 输入机需要 `SubmitOutcome.kind`，静态确认不兼容；全局文件队列、客户端目录和裸路由还有隔离问题 |
| `Mooling0602/dsh-web-file-uploader` | 文件选择器上传；文本模型得到路径，视觉模型在 pre-step 自动得到原生图片块 | 不满足统一的延迟读取；48 MiB 且拒绝空文件；自定义删除入口把调用者路径传给 `unlinkSync`，未见约束到登记附件的检查，未作利用测试 |
| `GLFzr/dsh-file-upload` | 只有拖拽；文本按扩展名解码，二进制保留成 `.b64`，全局暂存和队列 | 不是原样文件路径交付；无 Session 绑定，路由仅检查可缺省的 Origin，拒绝零字节，存在同名 npm 项目混淆 |
| `hyper-dsh-plugins/dsh-open-file` | 普通文件按原始字节上传，发送时附带插件文件引用；上传时做类型识别和容器校验，`file_read`、`file_ocr`、`file_render` 由模型显式调用 | 读取和 OCR 是按需工具；常见图片仍走原生链路，旧 OLE Office 在提交校验中被拒绝，因此不满足严格的所有类型只附加。已有会话工作区、路径与资源限制，仍未作运行组合验收 |
| `xzyonline/dsh-chat-files` | 普通文件保存到内容寻址库，上传只做类型检测；pre-step 通知文件 ID，模型再调受限读取/压缩包工具 | 没有自动正文提取或 OCR；图片被交还原生入口或拒绝，不满足所有类型统一附加；旧依赖与 DSH `0.1.2-rc.1` 的兼容性未验收 |
| `liznee/dsh-file-resource` | README 声明文档上传时本地解析成资源，正文按需由工具读取；图片仍原生 | “不立即把正文给模型”与“不进行任何预处理”不同；本次只核对文档和 registry，不据此确认完整安全性 |
| `sharkymew/dsh-utility-tools` | 普通文件发送时写入系统临时目录后给路径；图片仍原生 | 临时目录可能被系统清理；Host 把字节数组传给 `writeText` 后以异常和文件大小兜底，且请求体无服务端大小上限、未见统一请求检查，不作为可靠上传基础 |

> 来源：[`dsh-paste-to-path` 的上传/引用与 Host 路由](https://github.com/Johnny-xuan/dsh-paste-to-path/tree/5c831284cb4474a7d942dd09eaabdabb228c701d)、[CocoSgt 全类型 intake](https://github.com/CocoSgt/dsh-attachments/blob/70c0b7e81d7d6a2707e282457bd92f2577bd6629/src/client/intake.ts#L118-L139)、[CocoSgt 目录与存储参数](https://github.com/CocoSgt/dsh-attachments/blob/70c0b7e81d7d6a2707e282457bd92f2577bd6629/src/index.ts#L311-L353)、[AirDrop 图片保存与注入](https://github.com/demacia1314/dsh-airdrop/blob/08e40f217ef80ceb96ead9e22d09499e8c0d5f69/src/index.ts)、[AirDrop 人类消息附件组装](https://github.com/demacia1314/dsh-airdrop/blob/08e40f217ef80ceb96ead9e22d09499e8c0d5f69/src/server/injection.ts)、[loudMore 的发送包装与失败回退](https://github.com/loudMore/dsh-drop-to-path/blob/a00a5a2e18fd89e829b1c96f2f2e85af67366e10/lib/client.js#L329-L377)、[Mooling 原生图片分流](https://github.com/Mooling0602/dsh-web-file-uploader/blob/eafb06649a540f8292e230738ac2179f87acd48e/src/core/host-core.js#L467-L502)、[Mooling 删除入口](https://github.com/Mooling0602/dsh-web-file-uploader/blob/eafb06649a540f8292e230738ac2179f87acd48e/lib/index.js#L203-L226)、[GLFzr 字节与暂存实现](https://github.com/GLFzr/dsh-file-upload/blob/dc23ac42271fd93814924cd5822992501f7fb654/lib/index.js)。

> 来源：[Open File 提交只带引用](https://github.com/hyper-dsh-plugins/dsh-open-file/blob/39636d198993c5980da0091056d307bb5a8a48c5/src/client/submit-adapter.ts#L34-L77)、[Open File 图片走原生入口](https://github.com/hyper-dsh-plugins/dsh-open-file/blob/39636d198993c5980da0091056d307bb5a8a48c5/src/client/file-intake.ts#L23-L63)、[Chat Files 的按需工具](https://github.com/xzyonline/dsh-file-attachments/blob/7a0f0f47358366ed084de7a065d892fe6206e434/src/tools.ts#L79-L105)、[Chat Files 的图片过滤](https://github.com/xzyonline/dsh-file-attachments/blob/7a0f0f47358366ed084de7a065d892fe6206e434/src/client/store.ts#L55-L65)、[File Resource 文档](https://github.com/liznee/dsh-file-resource/blob/17650ab1b7ceb08b19338f81ff8f7f9b4f5cf86f/README.md)、[Utility Tools Host 实现](https://github.com/sharkymew/dsh-utility-tools/blob/d8ee3a77aed2c5446942073470faaa9de9ecd98a/lib/index.js)。

这些实现中的路径文字能随普通消息保留，但文件和附件索引是否恢复、fork 是否可读、清理是否误删仍需分别验证。采用官方通用附件可以复用持久文件引用和统一请求投影，因此不再额外安装社区上传插件；只有“图片也必须仅作为普通文件附加”等独立差异值得另行处理。

### <a id="file-transfer-workspace-plugins"></a>工作区与产物界面 Plugin

工作区浏览器能让人看到文件，不一定提供下载；Host 原生打开动作也不会把字节送到远程浏览器。下表保留 2026-08-27 的社区界面审计，不把它们列为官方 Sidebar 和 `present` 之外必须安装的组件。

| Plugin | 用户界面与字节通道 | 对模型的影响 | 路径与兼容边界 |
|---|---|---|---|
| `dsh-reveal-files` | 覆盖 Produced 行，提供 Open、Copy、Reveal、Terminal；动作发生在 DSH Host，没有浏览器字节响应 | 不注册 Tool、prompt 或 Session event | exact route 绕过标准 fence，absolute path 无工作区约束；macOS AppleScript 和 Windows cmd 的多层字符串构造形成潜在命令注入链，但本轮未在对应平台验证可用 payload。无桌面或 `canOpenPath:false` 的 Host 上不能构成可靠交付 |
| `dsh-workspace-files` | `conversation.view` 中列目录、预览最多 512 KiB 文本和 Git diff；二进制不返回；没有 download route | 没有模型 Tool、prompt 或 event | `root` 由 query 提供且不与 Session 绑定，`confine()` 只相对调用者声称的 root 做词法前缀检查；传 `/` 或跟随 symlink 可读任意 Host 文本文件。README 的“不跟随 symlink”与实现冲突 |
| `dsh-file` | 工作区树、文本编辑、Markdown 预览；唯一 download 是主题 JSON，不是工作区文件 | 浏览器直接 Node FS 写入，不走 DSH fs policy、approval、`fs/observed` 或 Session log | `setRoot()` 接受任意绝对目录且无 Session 参数，随后可读写删除；最终 symlink 仍会跟随，Markdown 未 sanitize 可形成同源 stored XSS。源码 clone 不含 package 入口所需 `dist` |
| `dsh-artifact-library` | 管理页登记路径，`GET /ext/artifacts/:id/file` 会流式返回原文件，但没有 attachment disposition、下载按钮或可靠文件名 | 注册 12 个模型 Tool 与 system prompt；store 变化本身不是 Session event | 可由 HTTP 或模型登记任意 Host path，再用裸 Node FS 索引或读取，绕过 DSH fs policy；无 root、ownership、Origin 或 MIME active-content 防护。自动采集不识别 rc.2 标准 `file_path`，只看 tool/call 且不核对成功 result |
| `dsh-file-pane` | 远程地址下用 `priority:-1` 接管 Produced chip，跳转 `/browser/?path=...`，提供代码、Markdown、DOCX、PDF 和图片只读预览；`raw=1` 仍以 inline response 返回，没有下载按钮或 attachment response | 不改变模型输入或 Tool | 初次 lexical check 会拒绝 root 外绝对路径和 `..`，但 realpath 后只做裸 `real.startsWith(root)`，缺少路径分隔符边界；指向 prefix-sibling（如 `<root>-secret`）的 symlink 可以逃逸。`/browser` 没有 Host/Origin、身份或 Session ownership，默认 root 为 Host HOME；`raw=1` 在大小判断前仍把完整文件读入内存。只在非 loopback 浏览器接管 Produced；loopback 页面仍走内置 Host opener |

> 来源：[`dsh-reveal-files` 的路径解析和原生命令](https://github.com/yumm007/dsh-reveal-files/blob/328917ff210ed2ec7f674dda386f2de39fd59bfb/lib/index.js#L38-L146)、[`dsh-reveal-files` 的裸 route](https://github.com/yumm007/dsh-reveal-files/blob/328917ff210ed2ec7f674dda386f2de39fd59bfb/lib/index.js#L154-L251)、[`dsh-workspace-files` 的 caller-supplied root](https://github.com/sqfcyily/dsh-workspace-files/blob/68a322f9884cfa4ec5552e3116ab769c97ec9c47/lib/index.js#L206-L230)、[`dsh-file` 的 path 解析与文件操作](https://github.com/chengzhi43/dsh-file/blob/1a94663da7eb81e31701b342a1e51f58616bd04d/src/index.ts#L59-L193)、[`dsh-file` 的无约束 `setRoot`](https://github.com/chengzhi43/dsh-file/blob/1a94663da7eb81e31701b342a1e51f58616bd04d/src/index.ts#L280-L297)、[`dsh-artifact-library` 的任意路径登记与文件流](https://github.com/wyq183/dsh-artifact-library/blob/ad3c6ee6fadba7a7de7a9eb3e842994259be24c8/lib/http.js#L99-L130)、[`dsh-file-pane` 的配置 root 与 inline raw route](https://github.com/trungtaottn/dsh-file-pane/blob/f6e211f71e8ddad8cfe8ddf3a738b8831d6310cb/lib/index.js#L99-L173)、[`dsh-file-pane` 的 realpath 前缀检查与完整文件缓冲](https://github.com/trungtaottn/dsh-file-pane/blob/f6e211f71e8ddad8cfe8ddf3a738b8831d6310cb/lib/view-core.mjs#L92-L127)、[`dsh-file-pane` 的远程 Produced 接管](https://github.com/trungtaottn/dsh-file-pane/blob/f6e211f71e8ddad8cfe8ddf3a738b8831d6310cb/client/index.tsx#L370-L403)。

### <a id="file-transfer-rich-artifacts"></a>聊天产物交付与下载

输出端最终采用[官方 `present`](#file-transfer-official-chain)：任意格式的可访问普通文件可成为交付卡，具体格式是否能预览由 Sidebar 读取器决定。早期的 Plik 工具上传文件再返回 URL 可以解决浏览器下载，Markdown 图片 URL 也可以直接显示；确认官方文件交付可满足本次目标后，不再把 Plik 作为默认步骤，不为了展示文件自动外发副本。这不等于 `present` 已生成下载 URL；源文件存续、访问端下载和对外分享仍是不同需求。

`dsh-rich-artifacts` 是 2026-08-27 候选集合中唯一明确实现“模型发布工作区文件 → 聊天下载卡 → 浏览器 attachment response”的独立仓库，下面保留其旧审计，不再作为选型建议。它向模型注册 `publish_artifact` 并加入 system prompt；Tool 使用 `ctx.fs.lstat/resolve/stat/contains` 把路径约束到 Session workspace，拒绝最终 symlink，按 magic bytes 判断 MIME，将文件复制到 SHA-256 内容寻址 blob store，再把 metadata 追加为 `artifact/published` 事件。浏览器对普通文件渲染 `/api/artifacts/:id/download` 链接，对安全栅格图片同时提供 inline preview；Host 下载 route 设置 `Content-Disposition: attachment`、`nosniff` 和长度，并用 `createReadStream` 传输。

> 来源：[workspace 约束与发布存储](https://github.com/Inkotake/dsh-rich-artifacts/blob/44f39793ce383330c781b38893d516e50cfab397/src/index.ts#L353-L459)、[`publish_artifact` Tool 与模型提示](https://github.com/Inkotake/dsh-rich-artifacts/blob/44f39793ce383330c781b38893d516e50cfab397/src/index.ts#L546-L634)、[HTTP content/download route](https://github.com/Inkotake/dsh-rich-artifacts/blob/44f39793ce383330c781b38893d516e50cfab397/src/index.ts#L475-L540)、[图片预览与文件下载卡](https://github.com/Inkotake/dsh-rich-artifacts/blob/44f39793ce383330c781b38893d516e50cfab397/src/client.ts#L102-L147)。

这条社区链路在 `0.1.1-rc.2` 基线下有以下差异和缺口：

- 它不会自动发布所有 `write` / `edit` 产物。模型必须额外调用 `publish_artifact`；system prompt 只能提高调用概率，不能成为执行保证。
- client 在 `conversation.chat.turnTail` 注册时没有指定 priority，内置 `ui-deliverables` 同样使用默认 `0`。rc.2 的 chain 在同优先级下保持注册顺序并取首个非 null selector：若内置行先注册且本轮已有 mutation 产物，下载画廊会被遮蔽；若该 Plugin 先注册，则由它胜出。本轮没有运行真实 Web composition，实际注册顺序未验证；`dsh-file-pane` 显式使用 `priority:-1`，说明该 Slot 需要由 Plugin 自己确定接管顺序。
- `artifact/published` 通过修改内部 `KNOWN_SESSION_EVENT_TYPES` Set 注册，而 `Session.append()` 没有把第三方事件写成 `ignorable` 的公开面。插件安装期间可以识别该事件；插件移除并重启后，持久日志可能因 unknown、non-ignorable event 被拒绝。
- `/api/artifacts` 作为 Plugin 自己注册的更长 prefix route，不经过标准 `/api` fence；handler 不检查 Host、Origin、`Sec-Fetch-Site`、身份或 Session，只验证随机 artifact id。`maxTurnBytes` 尚未强制，blob 没有 GC；发布会先把完整文件读入内存，默认单文件上限 100 MiB，下载本身是流式。
- 仓库只有一个 store 测试、没有 CI，也没有发布到 npm。所审提交未提供真实 rc.2 Profile、历史恢复、卸载后重放或 turn-tail 组合测试。

> 来源：[未指定 priority 的画廊注册](https://github.com/Inkotake/dsh-rich-artifacts/blob/44f39793ce383330c781b38893d516e50cfab397/src/client.ts#L191-L217)、[rc.2 chain 的排序与首个非 null 语义](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/client/ui-slots/src/index.ts#L247-L252)、[内置 Produced 的默认优先级注册](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/client/ui-deliverables/src/client/index.ts#L37-L52)、[无请求 fence 的 artifact handler](https://github.com/Inkotake/dsh-rich-artifacts/blob/44f39793ce383330c781b38893d516e50cfab397/src/index.ts#L494-L540)、[直接注册 `/api/artifacts` prefix](https://github.com/Inkotake/dsh-rich-artifacts/blob/44f39793ce383330c781b38893d516e50cfab397/src/index.ts#L636-L642)、[内部事件 Set 修改](https://github.com/Inkotake/dsh-rich-artifacts/blob/44f39793ce383330c781b38893d516e50cfab397/src/index.ts#L22-L30)、[rc.2 恢复拒绝未知非 ignorable 事件](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/session/session-persistence/src/coordinator.ts#L1051-L1065)。

这份旧审计只能证明当时已有社区下载实现，不能证明其可安全接管所有 Produced 文件。所审 `dsh-rich-artifacts` 仍依赖显式发布，并存在 Slot 组合、Session 格式、授权和生命周期缺口；`dsh-file-pane` 面向预览，`dsh-artifact-library` 的原文件流也不构成完整下载方案。这些差异用于解释未采用原因，不能据此判断官方 `present` 的能力。

### <a id="file-transfer-security-boundaries"></a>传输与下载的安全边界

Host、Origin 和 `Sec-Fetch-Site` 请求检查与用户身份认证承担不同职责；社区 Plugin 自注册路由不会自动获得官方连接层的检查。官方通用上传通过 Connection 注册经过身份验证的流式入口，并将上传回执绑定到真实 Session。评估社区插件时，应核对路由实际使用的认证和授权方式，不能仅凭 `/api` 前缀或“同源请求”的描述判断安全性。

> **版本对照：** `0.1.1-rc.2` 的标准 `/api` carrier 用于核对旧插件的请求栅栏，`0.1.5-rc.1` 的 Connection 上传入口用于核对官方通用上传；两者不能混用。来源：[0.1.1-rc.2 API 的请求检查](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/client/connection/src/api-request-trust.ts#L90-L123)、[旧 WebServer 路由顺序](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/host/webserver/src/index.ts#L256-L265)、[Connection 上传入口](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.5-rc.1/packages/client/file-upload/src/http-route.ts#L16-L66)、[Session 回执与投递事务](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.5-rc.1/packages/client/file-upload/README.md#L44-L52)。

评估上传或下载实现时，按下列项目检查；这些是审计标准，不表示官方或任一候选已经全部具备。通用文件的大小配额、保留周期和磁盘容量应由部署明确控制，访问权限也须单独核对：

- Host 根据 `sessionId` 解析 authoritative cwd，不能接受浏览器自行声明根目录。
- 对目标做 canonical realpath、regular-file 与 no-follow 检查，并把 symlink 和 TOCTOU 纳入实现与测试。
- 上传限制单文件、文件数、批量总字节、持久存储总量、并发和速率；写入使用受限临时文件和原子发布，定义重名、取消、失败与清理语义。
- 下载使用安全文件名、`Content-Disposition: attachment`、`X-Content-Type-Options: nosniff` 和流式响应；HTML、SVG 等 active content 不能以内联同源页面交付。
- 浏览器和 Host 共同执行 Host/Origin fence；LAN、反向代理或多用户部署还需要真实身份与 Session ownership，而不是把不可猜 id 当认证。
- 任何进入模型上下文或决定聊天 UI 的附件/产物状态都必须写入可重放 Session 事件，并在 Plugin 卸载、版本升级、fork 和恢复时保持可解释。
- Produced 行在 `canOpenPath:false` 或远程浏览器场景需要明确的浏览器下载或预览动作；Host native opener 只能作为另一种动作，不能冒充下载。

这些边界也解释了为什么“给路径文字加一个 URL”不足以修复问题：URL 背后必须有受限的字节读取、授权、持久身份和响应生命周期。

### <a id="file-transfer-validation-boundary"></a>验证范围

> **测试记录：** 2026-08-27 执行了 `l541402398/dsh-file-uploads` 的 7 项 Host 测试、`WJZ-P/dsh-attachments` 的 9 项 Host/package 测试和 `chengzhi43/dsh-file` 的 5 项 Host-facing 测试；2026-09-10 没有重跑这些测试。旧表其他仓库只做源码审计。

> **源码验证范围：** 2026-09-10 对官方 `dsh-v0.1.5-rc.1` 回读了 composer 分流、Session 接收、文件存储、请求投影、`present` 和文件卡源码；还读取了零字节文件等测试用例，但未执行这些测试。增量候选检查了固定提交、npm 元数据和部分已安装 rc.1 模块导出；`ImageLightbox` 缺失及发送返回值不匹配属于静态兼容性发现，未进行浏览器复现。部分候选仅达到 README 和发布信息核对，已在表内标明；没有全面比较 npm tarball 与仓库字节。

> **发布信息范围：** 2026-08-27，`HongMing-Huang/dsh-file-upload` 的源码版本为 `0.5.2`、npm 包为 `0.4.3`，`sqfcyily/dsh-workspace-files` 的源码版本为 `0.1.1`、npm 包为 `0.1.0`；部分候选未发布 npm 或缺少构建产物。2026-09-10 另核对了两个 `dsh-attachments` 仓库的不同 npm 包名、`GLFzr/dsh-file-upload` 的同名包冲突、`dsh-airdrop` 更名后的发布差异，以及 `dsh-file-uploads` 的 registry 404。安装前仍应核对明确的仓库、版本和产物，不能把快照表格或搜索目录当作实时安装清单。

> **部署验证范围：** 2026-09-10 的复核未安装社区候选或升级运行服务，也未对 `dsh-v0.1.5-rc.1` 完成上传、刷新、fork、恢复、文件交付和访问端下载的端到端验收。采用官方上传与 `present` 是选型决策，不代表部署已经完成。

使用或继续评估这些方案时，始终区分原样输入副本、模型路径引用、输出源文件声明和浏览器下载。

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

归档会话的持久 `assistant/message.source` 显示 `provider: openai-codex`、`model: gpt-5.6-sol`，这只能确认解释该问题的模型请求走 `openai-codex`。用户粘贴的 Tool card 不携带原始 `request/header`，所以原始图片调用仍需回到其来源 Session 核对：若相关 step 的 provider 是 `openai-codex`，前后模型请求归该 Codex 路由；若是 DeepSeek provider，则归 DeepSeek。两者之间的 Harness-side `read_image` Tool 执行都不会自行切换 Provider。Model Hub 同时存在的两条 Codex 路由及其凭据归属见 [Model Hub 的 Codex 路由](#2026-08-26-bridges-and-model-hub)。

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

> **证据边界：** 官方源码两轮固定——08-28 原记录锚定 `0.1.1-rc.2`（commit [`b150a551`](https://github.com/deepseek-ai/deepseek-harness/tree/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e)，其原有来源链接仍指向该 commit）；09-04 复核锚定 `0.1.2-rc.1`（commit [`a66e470`](https://github.com/deepseek-ai/deepseek-harness/commit/a66e4702047846cdaa10c66c9d3df3951f5ea70d)，2026-09-02 发布提交，未另标 commit 的官方引用均指它）。本机安装树为 0.1.2-rc.1，🔬 常量核对与包内 README 行号定位以它为据（同一 release 的包内 README 与 GitHub blob 行号一致）。DeepSeek API 文档为 2026-09-04 抓取的现行页面。社区插件按各仓库 HEAD 快照固定到来源链接中的 commit；本节点名插件至少核对过 README，其中新增四项（anysearch-dsh、dsh-web-tools、dsh-tavily、modsearch）已完整 clone 后复核 README 与关键源码，均未做逐行全量源码审计；插件商店快照中未点名的条目仅作发现信号；除注明 🔬 的两段归档会话观察外，两轮均未用真实凭据做端到端搜索验证。供应商如何把搜索折算成订阅额度或金额，仍由该供应商的实时规则决定。

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

> 来源：[web 子系统文档：queries 扇出、searchMaxResults、错误码归属与抓取网络策略](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/docs/subsystems/web.zh.md)；[seam 的 env 入口与字段表](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/web/web/README.md#L36-L46)、[四态选择表与执行期解析](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/web/web/README.md#L67-L78)；[base patch 的 web / tool-web 行](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/bundle/base/cordis.patch.yml#L447-L466)；[工具只调用 `ctx.web.search()`](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/web/tool-web/README.zh.md#L1-L15)。

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

Exa 是官方可选搜索包（provider id `exa`，默认组合不启用）：密钥回退 `$EXA_API_KEY`，端点 `https://api.exa.ai/search`，支持 `searchType`（auto / keyword / neural）、`numResults` 与 `highlightsPerResult`。Exa 不返回生成答案（结果无 `content`），没有非空白高亮的来源会被整个丢弃，返回来源可能少于请求数。08-28 记为"Perplexity 同类"；本轮确认 Perplexity 已随官方仓库发布为可选包（见下节）。

> 来源：[DeepSeek 搜索默认基址与模型](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/web/web-search-deepseek/src/provider.ts#L26-L47)、[发出前记录的请求体](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/web/web-search-deepseek/src/provider.ts#L197-L218)、[事件写入会话](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/web/web-search-deepseek/src/index.ts#L117-L121)、[凭据缺失不写该事件](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/web/web-search-deepseek/README.zh.md#L49)、[Exa 可选包的配置表与来源映射](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/web/web-search-exa/README.zh.md)；[provider id 与固定方式](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/web/web-search-deepseek/README.zh.md#L28)、[一次搜索=完整模型轮次](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/web/web-search-deepseek/README.zh.md#L32)、[完整配置表与 Settings 段投影](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/web/web-search-deepseek/README.zh.md#L45-L56)、[请求日志事件语义](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/web/web-search-deepseek/README.zh.md#L64)、[失败码与配置指引](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/web/web-search-deepseek/README.zh.md#L68)、[凭据逐次解析](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/web/web-search-deepseek/README.zh.md#L85)。🔬 本机安装树 `dsh-web-search-deepseek/lib/index.js` 的常量（默认基址、默认模型、`web_search_20250305`、`DEEPSEEK_SEARCH_BASE_URL` 回退）与上述 README 逐项一致。

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

安装面与能力边界（2026-09-04 核对 npm registry）：该包自 2026-08-10 起由官方维护者发布（MIT），最新 `0.1.2-rc.1`（2026-09-03），并非 0.1.2 才出现的新包；但 **dist-tag `latest` 仍指向首日 `0.0.1-rc.1`、`next` 才是 `0.1.2-rc.1`——安装必须显式钉版本**，否则解析到远古版本。Perplexity 侧的学术检索能力（产品端 Academic focus、Sonar API 的 academic 搜索过滤参数）**未接入本 provider**：配置面只有 model / maxTokens / searchRecency；Perplexity 文档现把 Sonar 归为 Legacy API，本 provider 走的正是这条 chat-completions 路径。另核对 Perplexity 自家 API 面：它另有独立的 **Search API**（返回实时排序的结构化网页条目、无生成答案，附域名/语言/地区过滤）与配套 Search SDK——即"Perplexity 纯条目检索"在其产品线上存在，只是不在本 provider 的路径上，要用需另行实现 provider。

fetch 侧自带与 Agent 文件沙箱相互独立的网络边界。已交付的 preset 在所有 sandbox 和审批模式下暴露 `web_fetch`、无逐次确认；文件 sandbox 不管网络访问，需要确认步骤的部署须自加 `tools/pre-execute` 策略或禁用抓取。HTTP 提供方仅接受公开 HTTP(S) 目的地、拒绝凭证式 URL，逐请求解析并拒绝非公开 IPv4/IPv6 及经 DNS64 前缀转换到私有 IPv4 的结果，把连接固定到已验证地址，并在每次同源重定向时复检；跨源重定向需要新的工具调用与新的公开地址校验。这些检查阻止 SSRF 访问非公开目的地，但不阻止模型把数据发送到公开 URL。

> 来源：[web 包家族目录](https://github.com/deepseek-ai/deepseek-harness/tree/dsh-v0.1.2-rc.1/packages/web)；[子系统文档的 content 差异与抓取网络策略](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/docs/subsystems/web.zh.md)；[web-search-perplexity README](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/web/web-search-perplexity/README.zh.md)；[npm registry 的版本时间线与 dist-tags](https://registry.npmjs.org/@deepseek-ai/dsh-web-search-perplexity)、[Sonar API 存在 academic 搜索过滤的旁证](https://community.perplexity.ai/t/date-filtering-not-working-for-academic-search-mode-sonar-api/539)、[Search Filters 文档（Sonar 属 Legacy API）](https://docs.perplexity.ai/docs/sonar/filters)、[Perplexity Search API 快速开始（纯结构化网页条目）](https://docs.perplexity.ai/docs/search/quickstart)（后四条 2026-09-04 查阅）。

### DeepSeek 官方 API 文档的印证

DeepSeek API 文档独立印证了从源码推出的计费模型：

- **Web Search 官方支持与额外费用**：Claude Code 接入页写明"调用 Web Search 工具会通过 DeepSeek 提供的 API 进行搜索……会产生额外的模型 Token 费用"，与 provider README 的"一次搜索消耗一个完整 Messages 轮次、DeepSeek 不提供专用检索端点"互证。
- **Anthropic 兼容基址**：文档给 Claude Code 的 `ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic`（SDK 追加 `/v1/messages`），DSH 常量 `…/anthropic/v1` 追加 `/messages`，落在同一端点。
- **模型映射**：claude-opus 前缀映射 `deepseek-v4-pro`，claude-haiku/sonnet 映射 `deepseek-v4-flash`；传入不支持的模型名会被后端自动映射到 `deepseek-v4-flash`。更新日志确认 V4-Pro 与 V4-Flash 同时支持 OpenAI 与 Anthropic 接口。
- **协议面**：兼容矩阵中 `server_tool_use` 与 `web_search_tool_result` content 类型受支持——正是 provider 解析 `sources[]` 的数据来源。

> 来源：[Claude Code 接入与 Web Search 说明](https://api-docs.deepseek.com/zh-cn/quick_start/agent_integrations/claude_code/)、[Anthropic API 兼容细节](https://api-docs.deepseek.com/zh-cn/guides/anthropic_api/)、[更新日志](https://api-docs.deepseek.com/zh-cn/updates/)（均 2026-09-04 查阅）。

### <a id="model-hub-and-search"></a>Model Hub 与搜索提供方

[`dsh-model-hub`](https://github.com/yhyfhgs/dsh-model-hub)（`yhyfhgs/dsh-model-hub`，社区 Plugin）替换官方 Models 页面与模型选择器，为官方模型服务桥接 OAuth 并写入无 API Key 配置，同时提供官方 pi-ai 路由与插件 native 路由两类实现；其登录、凭据和适配器归属见[订阅登录调研](#2026-08-26-subscription-auth-surfaces)。本节只看它与搜索的关系。

Model Hub 的 Host `inject` 是 `connection` 与 `settings`。它注册模型目录、Authorization 与两条 Codex 对话路由，不调用 `ctx.web.registerSearchProvider`。显示名「OpenAI Codex」不能区分下面两行：

| 路由 key | 凭据记录 | 适配器 |
|---|---|---|
| `openai-codex` | `llm-pi-ai` 的 `recordKeyFor()` | 官方 `PiAiAdapter` |
| `codex` | Model Hub 自有 native grant | Hub `NativeOAuthAdapter` |

两条路由的 token 分属不同记录范围，不能交叉刷新。

> 来源：[Model Hub 的两条 Codex 路由](#2026-08-26-bridges-and-model-hub)、[Host `inject` 为 `connection` 与 `settings`](https://github.com/yhyfhgs/dsh-model-hub/blob/6897374e90b2f383a797e6597c011e076594f3e7/src/index.ts#L89-L90)。

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
5. **外部印证。** [掘金文章](https://juejin.cn/post/7673816823688003630)实测"主模型切到 opencode 后 `web_search` 仍走 DeepSeek 官方计费"、[DataCamp 教程](https://www.datacamp.com/zh/tutorial/deepseek-harness)写明"默认搜索 provider 与模型共用同一 DeepSeek API key"、[官方讨论 #779](https://github.com/deepseek-ai/deepseek-harness/discussions/779)（"联网搜索能否兼容其他模型"）的回复确认 `web_search` 是可插拔 provider 架构、更换 provider 即可兼容——三条口径与本节源码结论一致。

插件商店聚合目录（2026-09-04 快照收录 6465 个插件，`web-search` 匹配 75 项）显示该类别规模已远超上表核心样本。快照中值得注意、已完整 clone 并固定 commit 复核 README 与关键源码的条目：

| 插件 | 固定 commit | 接入方式 | 要点 |
|---|---|---|---|
| [`@anysearch/anysearch-dsh`](https://github.com/anysearch-team/anysearch-dsh/tree/3ccdef05e2b502509415b023e206a4c9f6afb038) | `3ccdef05`（08-26，v0.1.4） | provider：patch 钉 `searchProvider: anysearch`，源码调用 `ctx.web.registerSearchProvider` | AnySearch 官方团队（`@anysearch` npm scope）出品的实时网页与垂直搜索；InfoQ / CSDN 教程安装的即此包，与 `mcxianyujun/dsh-web-search-anysearch` 是两个仓库 |
| [`dsh-web-tools`](https://github.com/A3Boy/dsh-web-tools/tree/9b45045ac8a011429d494399a49846ae907c07d3) | `9b45045a`（09-03，v0.3.3） | provider：bundle patch 把 `web` 行覆写为 `searchProvider: dsh-web-tools` | 8 个提供方原生适配、SearchHints 语义编译、多源回退、X / 小红书检索 |
| [`@moguiyu/dsh-tavily`](https://github.com/moguiyu/dsh-tavily/tree/8f2784af3d89754acdd9baf58bdd21353ae9c00e) | `8f2784af`（09-02，v0.2.1） | 独立工具：不注册 provider、不改 `web.searchProvider`，内置 `web_search` 原样保留 | 可选 Tavily 搜索工具，多 key 轮换 / 故障转移、用量仪表盘、`extract` / `map` / `crawl` 直连工具 |
| [`@liustack/modsearch`](https://github.com/liustack/modsearch/tree/81ed4d16fbdec19d078f7bfbeac11b6c5ceb1e80) | `81ed4d16`（08-28，v5.10.0） | skill / 工具为主，兼注册 provider（id `modsearch`） | 见 [2026-08-17 生态调研](#packaging-and-community)；引擎 Firecrawl（keyless 默认）/ Antigravity CLI / Tavily / Exa / Grok(X) / local 自动回退，免费免 key |

"接入方式"一列把社区接入 `web_search` 的途径分成三类：换 provider（anysearch-dsh、dsh-web-tools 及上表五个）、加独立工具不动内置链路（dsh-tavily）、skill / 工具附带 provider（modsearch）。商店其余 Tavily、SearXNG、TinyFish、zero-key Bing / Baidu 聚合等同构条目未复核，仅作发现信号；商店条目由 GitHub 公开项目自动聚合，未经人工审核。

> 来源：[插件商店 `web-search` 类目快照](https://dsh.deepseek404.com/index.php?q=web-search)（2026-09-04 查阅，仅作发现信号）。

> free-search 的 README 声称 "`web_fetch` 无 SSRF 防护、agent 理论上可访问内网地址"，与官方子系统文档和 base patch 注释矛盾：官方 fetch 后端逐请求解析并拒绝非公开目的地、pin 连接、同源重定向复检（见[官方 web 包家族与 fetch 侧网络策略](#web-search-six-packages)）。该说法应视为过时或不准确。

> 来源：上表各仓库 README（固定到表内 commit）；[AnySearch 发布讨论](https://github.com/deepseek-ai/deepseek-harness/discussions/2671)；周边文章 [InfoQ 的 anysearch-dsh 安装教程](https://www.infoq.cn/article/bfZzslUtldTMeEgYuVhe)与[博客园的免费搜索插件记录](https://www.cnblogs.com/dqtx33/p/22579950)（2026-09-04 查阅，仅作发现信号）。

### 验证范围

- 未把任何社区搜索插件装进 Profile 做端到端；免费引擎 keyless 额度、回退链行为与 MCP 点数消耗（zai README 自述智谱测试"一次搜索消耗一点"）均为项目自述。
- 🔬 覆盖范围仅为：本机 0.1.2-rc.1 安装树的包清单、provider 常量与 README 行号核对，以及 08-28 的两段归档会话观察；未发真实搜索请求。
- 两份社区 README 对 profile patch 热重载的描述互相矛盾（brave 称"保存即生效"、searxng 称"Web profiles 按设计禁用 HMR、需重启"），与官方 CLI reference 的"运行进程监视 Profile patch"表述也不一致。🔬 2026-10-08 已实测裁决：**无需重启，保存即生效**——web Profile（DSH `0.2.0-rc.2`，Profile 未声明 `patchReload`、走默认 `live`）的 `profiles/web/cordis.patch.yml` 写入 `llm-pi-ai` → `openai-codex` → `modelOverrides` 的 `contextWindow` 后，不重启的运行实例直接按新预算工作，运行中的会话也无需重开。brave 与官方 CLI reference 的口径成立，searxng 的"Web profiles 按设计禁用 HMR、需重启"不成立；机制见运行时篇 [Patch 热更新的生效机制](dsh.md#mcp-patch-hot-reload)。
- free-search 的 v0.4.x 迭代很快（README 内嵌的版本截图文字与 HEAD 提交版本号已不同步），引用其细节时以仓库 HEAD 为准。
- 官方包家族与 provider 行为以 0.1.2-rc.1 为快照；DSH 处于 developer preview，settings 注册面等接口在 0.1.2 系列内已经变动（free-search 为此做双兼容），引用本节细节时先确认当前版本。

## <a id="2026-09-15-quota-display-plugins"></a>2026-09-15 · MiniMax 与 Z.ai 的剩余额度显示插件

本轮专题是"在 DSH 界面显示 MiniMax、Z.ai（智谱 GLM）等订阅套餐剩余额度"的社区插件。[2026-08-26 的订阅登录调研](#2026-08-26-subscription-auth-surfaces)里，额度展示只作为 `dsh-plugin-subscriptions` 的附属功能出现，且其覆盖的 Codex / Claude / Grok / Copilot 不含 MiniMax 与 Z.ai；本轮把额度显示单独作为选题，按 stars 与提交节奏记录关注度与维护信号，并核对每家实际请求的官方端点。额度归属的判定原理见 [`read_image` 的请求与额度归属](#2026-08-28-read-image-quota)；消耗 Z.ai Coding Plan 点数的搜索插件见 [`web_search` 调研](#web-search-community-providers)。

**调研时间：** 2026-09-15（Asia/Shanghai）

**调研目标：**

- 盘点在 DSH 界面显示 MiniMax Token Plan、Z.ai / 智谱 Coding Plan 剩余额度的社区插件。
- 记录各仓库 stars、创建时间、最近提交、近期提交数与 npm 发布状态，作为关注度与维护信号。
- 核对取数端点、凭据解析位置与界面接入 slot。
- 标记同名仓库与相近 npm 包名，避免安装时混淆。

> **证据边界：** stars 与仓库创建时间为 2026-09-15 的 GitHub API 快照；npm 版本同日查询 registry.npmjs.org；提交日期与提交数取自本轮浅克隆（`--depth=60`）固定 HEAD 的 git log，浅克隆下总提交数为下界。下列 12 个仓库读取了 README 并核对了端点常量、slot 注册与凭据解析等关键源码，未做逐行全量审计；未把候选装进运行中的 Profile，未用真实 MiniMax / Z.ai 凭据发请求，各插件的显示能力均为源码与 README 自述。候选发现使用 Z.AI 网页搜索、GitHub 仓库搜索与插件商店快照；商店收录与热度只作发现信号。

### <a id="quota-discovery-entries"></a>候选的发现入口

本轮从四个入口汇出候选集合，再回到固定 commit 核对：

- GitHub 仓库搜索与 [`dsh-plugin` topic](https://github.com/topics/dsh-plugin)（各插件商店从该 topic 自动聚合）。
- 插件商店类目与详情：[dshmk.com 的 minimax 标签](https://dshmk.com/topics/minimax)、[DSH 插件商店的 ds-balance-card 详情页](https://dsh.deepseek404.com/detail.php?id=jasonsun29%25252Fds-balance-card)（均 2026-09-15 查阅）。
- DSH 官方仓库 discussions：[ds-balance-card 发布帖 #448](https://github.com/deepseek-ai/deepseek-harness/discussions/448)、[实时 Token 花费与账户余额显示讨论 #1878](https://github.com/deepseek-ai/deepseek-harness/discussions/1878)。
- Z.AI 搜索命中的导航站与教程，如[鱼皮 AI 导航收录的 dsh-spend](https://ai.codefather.cn/dsh-plugin/2093235979832823823)。

未点名的同构条目只作发现信号；安装判断以固定 commit 的源码与真实发布包为准。

### <a id="quota-repo-snapshot"></a>仓库快照与维护信号

下表 12 个仓库都完成了克隆与关键源码核对。"09-01 以来提交"按固定 HEAD 的 git log 统计，与 stars 一样只表示关注度与提交节奏，不代表质量或安全审计。

| 仓库 | Stars | 创建 | 最近提交 | 09-01 以来提交 | npm 包 |
|---|---:|---|---|---:|---|
| [`Han-1413141/dsh-cost-meter`](https://github.com/Han-1413141/dsh-cost-meter/tree/50cfcacded9e25cd4a3a21f8d247dce4bf76b353) | 301 | 2026-08-13 | 2026-09-15 | 78 | `dsh-cost-meter@1.7.25` |
| [`Ychris12138/dsh-usage-stats`](https://github.com/Ychris12138/dsh-usage-stats/tree/9bbb6d5cbc23f74327b979dd6650b7194cec8f3b) | 154 | 2026-08-14 | 2026-09-12 | 7 | `@ychris12138/dsh-usage-stats@0.3.3` |
| [`Aisland-SJL/dsh-usage`](https://github.com/Aisland-SJL/dsh-usage/tree/008fe9dcd3165e851857b60166113b428068cdec) | 94 | 2026-08-16 | 2026-08-31 | 0 | `dsh-usage@0.2.5` |
| [`wenzetan/dsh-quota-panel`](https://github.com/wenzetan/dsh-quota-panel/tree/d7efeee726aca6a5379e9fe756d33233860d88ca) | 10 | 2026-08-14 | 2026-09-11 | 4 | `dsh-quota-panel@0.9.1` |
| [`welsione/dsh-mmx-bridge`](https://github.com/welsione/dsh-mmx-bridge/tree/64499d43ad5ad7d30db3c9dd1602dccbb320b37e) | 10 | 2026-08-14 | 2026-09-11 | 2 | `dsh-mmx-bridge@1.0.9` |
| [`Thedeergod666/dsh-musage`](https://github.com/Thedeergod666/dsh-musage/tree/9a05ddfc9bbc4c80c541511cc6604a11b22b4f24) | 6 | 2026-08-17 | 2026-08-31 | 0 | 未发布 npm |
| [`jasonsun29/ds-balance-card`](https://github.com/jasonsun29/ds-balance-card/tree/acc2d63371fd1314259839c093c318e42006ffbc) | 2 | 2026-08-13 | 2026-08-14 | 0 | 未发布 npm |
| [`Floating-Dreaming/dsh-minimax-usage`](https://github.com/Floating-Dreaming/dsh-minimax-usage/tree/9a6e2987eb825a8915fa9561e3348e6fe832a3da) | 2 | 2026-08-15 | 2026-08-16 | 0 | 未发布 npm（`trusted-plugin/` 声明 bundle） |
| [`wannanbigpig/dsh-usage-stats`](https://github.com/wannanbigpig/dsh-usage-stats/tree/eda4a27734878d5839854c2834b50e61005388dd) | 1 | 2026-08-19 | 2026-09-12 | 18 | `@wannanbigpig/dsh-usage-stats@0.5.1` |
| [`ovensi/dsh-plugin-minimax-usage`](https://github.com/ovensi/dsh-plugin-minimax-usage/tree/16af76b37a2c17293b0e0cff996ab75962296380) | 1 | 2026-08-15 | 2026-08-15 | 0 | 未发布 npm |
| [`jasper-zsh/dsh-plugin-provider-quota`](https://github.com/jasper-zsh/dsh-plugin-provider-quota/tree/757affff17bae5dabd4a434e51d2bf0ef0345c4a) | 0 | 2026-08-13 | 2026-08-18 | 0 | 未发布 npm |
| [`grishworld-007/dsh-quota-panel`](https://github.com/grishworld-007/dsh-quota-panel/tree/46658e924a087fd1d50f8acd82fdcd968fe57002) | 0 | 2026-08-28 | 2026-08-29 | 0 | 未发布 npm（package 名为 `quota-panel`） |

> **同名仓库与相近包名：** `dsh-quota-panel` 有三个同名仓库——wenzetan（npm `dsh-quota-panel`）、`brittanistrehlowll-oss`（3 星）、`grishworld-007`（package 名又不同，叫 `quota-panel`）；`dsh-usage-stats` 有两个同名仓库——Ychris12138 与 wannanbigpig，npm 分别发在 `@ychris12138` 与 `@wannanbigpig` 两个 scope；`dsh-minimax-usage` 另有 `pan17` 的同名浮窗实现，`dsh-mmx-bridge` 另有 `barryzhang-cn` 的 mmx-cli 包装版。安装与引用时必须带 owner，不能只写仓库短名。

本轮未克隆、只确认到 README 或搜索快照的同题小仓库：`pan17/dsh-minimax-usage`（浮窗气泡）、`andyfan1094/dsh-minimax-usage-pro`（其 README 记录了 trusted bundle plugin 在当时宿主上拿不到 `host.call`、改走 webServer 路由的适配过程）、`jooey/dsh-usage-minimax-cn`（`/usage-minimax-cn` 命令）、`barryzhang-cn/dsh-mmx-bridge`（`mmx_quota` 工具）、`brittanistrehlowll-oss/dsh-quota-panel`、`nonewind/dsh-spend`（8 星，token 用量与费用悬浮窗，README 自述可识别计费计划）。这些条目未复核源码，仅作发现记录。

### <a id="quota-minimax-zai-coverage"></a>MiniMax 与 Z.ai 的覆盖与界面接入

各插件对两家目标平台的覆盖和接入位置如下。UI 位置一列的 slot / 面板名称来自各仓库源码或 README 自述；"服务端解析凭据"指 API Key 不进浏览器。

| 插件 | MiniMax | Z.ai / 智谱 | 界面接入 | 凭据 |
|---|---|---|---|---|
| `dsh-cost-meter` | 5h + 周窗口 | 5h / 周 / 工具额度 + 套餐档位 | 侧边栏卡片、设置页、输入框上方额度横条 | 各家独立凭据，服务端解析 |
| `Ychris12138/dsh-usage-stats` | 5h + 周窗口 | 5h / 周窗口 | 设置页面板与侧栏，一次只呈现当前供应商 | 服务端解析，浏览器不收 key |
| `wannanbigpig/dsh-usage-stats` | 5h + 周比例窗口 | 5h / 周剩余比例与重置时间 | 宿主原生右侧 Sidebar，无会话时主面板 / Modal 回退 | 复用模型设置中的 Key |
| `wenzetan/dsh-quota-panel` | global / CN 双站 | `zhipu` / `zai` / `zai-coding-cn` 三路由 | 右下角胶囊 + 卡片 + 设置面板；v0.5 起内置 provider 目录自动发现，零配置 | 凭据解析后自动上卡 |
| `jasonsun29/ds-balance-card` | 5h + 周窗口剩余 % | 5h / 周 / 工具额度剩余 % + 档位 | `shell.overlay` 常驻卡片，可拖拽折叠 | credentials 服务解析后经环境变量传给查询进程 |
| `Thedeergod666/dsh-musage` | 5h + 周双窗口 | `zai-coding-cn` 套餐 | `conversation.input.right`，跟随当前模型自动切换 | 复用 DSH 已配 API Key |
| `Aisland-SJL/dsh-usage` | 不支持 | 仅账户余额（`/api/paas/v4/balance`） | 常驻 dock + 详情面板 | 服务端解析 |
| `Floating-Dreaming/dsh-minimax-usage` | 5h + 周窗口 + 视频赠送次数 | 不支持 | 设置页「用量」section；无 Key 时整段隐藏 | trusted plugin 持有 key，60s 缓存 + 10s 限流 |
| `ovensi/dsh-plugin-minimax-usage` | 5h + 周进度条 | 不支持 | `sidebar.footer.action` | 服务端 60s 缓存 |
| `jasper-zsh/dsh-plugin-provider-quota` | 不支持 | `zai` 与 `zai-coding-cn` 双站窗口 | `sidebar.footer.action` 读数行 + `shell.overlay` 详情浮层 | apiKeyEnv 引用，原始凭据不进浏览器 |
| `grishworld-007/dsh-quota-panel` | general 通道区间与周剩余（过滤 video） | `zai-coding-cn` 5h / 周 | 右上角悬浮面板；动态 Cordis 插件形态，另提供会话内试用 | 从 `llm-pi-ai` 设置动态读取 |
| `welsione/dsh-mmx-bridge` | `mmx_bridge` 工具的 `quota` 子能力 | 不支持 | 模型可调用的工具，无常驻 UI | MiniMax 凭据 |

> 来源：[cost-meter 的 Coding Plan 功能行](https://github.com/Han-1413141/dsh-cost-meter/blob/50cfcacded9e25cd4a3a21f8d247dce4bf76b353/README.md#L30-L40)；[Ychris 的订阅端点常量](https://github.com/Ychris12138/dsh-usage-stats/blob/9bbb6d5cbc23f74327b979dd6650b7194cec8f3b/lib/subscriptions.js#L24-L40)；[wannan 的 Provider 支持表](https://github.com/wannanbigpig/dsh-usage-stats/blob/eda4a27734878d5839854c2834b50e61005388dd/README.md#L39-L40)；[wenzetan 的 provider 目录](https://github.com/wenzetan/dsh-quota-panel/blob/d7efeee726aca6a5379e9fe756d33233860d88ca/lib/index.js#L845-L851)；[ds-balance-card 的平台矩阵](https://github.com/jasonsun29/ds-balance-card/blob/acc2d63371fd1314259839c093c318e42006ffbc/README.md#L28-L29)；[musage 的凭据到端点映射](https://github.com/Thedeergod666/dsh-musage/blob/9a05ddfc9bbc4c80c541511cc6604a11b22b4f24/dsh/index.js#L51-L83)、[自动跟随当前模型](https://github.com/Thedeergod666/dsh-musage/blob/9a05ddfc9bbc4c80c541511cc6604a11b22b4f24/README.md#L32)；[dsh-usage 的 zai 余额路由](https://github.com/Aisland-SJL/dsh-usage/blob/008fe9dcd3165e851857b60166113b428068cdec/lib/index.js#L62)；[Floating-Dreaming 的端点与缓存](https://github.com/Floating-Dreaming/dsh-minimax-usage/blob/9a6e2987eb825a8915fa9561e3348e6fe832a3da/README.md#L14)；[ovensi 的 sidebar 与缓存](https://github.com/ovensi/dsh-plugin-minimax-usage/blob/16af76b37a2c17293b0e0cff996ab75962296380/README.md#L1-L25)；[jasper-zsh 的 Provider 表](https://github.com/jasper-zsh/dsh-plugin-provider-quota/blob/757affff17bae5dabd4a434e51d2bf0ef0345c4a/README.md#L3)、[Z.AI 双站端点](https://github.com/jasper-zsh/dsh-plugin-provider-quota/blob/757affff17bae5dabd4a434e51d2bf0ef0345c4a/README.md#L20-L21)；[grish 的四家覆盖](https://github.com/grishworld-007/dsh-quota-panel/blob/46658e924a087fd1d50f8acd82fdcd968fe57002/README.md#L9-L14)；[mmx-bridge 的 quota 子能力](https://github.com/welsione/dsh-mmx-bridge/blob/64499d43ad5ad7d30db3c9dd1602dccbb320b37e/README.md#L86)。

覆盖面上的分野：多平台聚合插件把 MiniMax 与 Z.ai 作为若干家 Coding Plan 中的两家；`wenzetan/dsh-quota-panel` 与 `jasper-zsh/dsh-plugin-provider-quota` 额外区分了 Z.ai 国际站（`api.z.ai`）与大陆站（`open.bigmodel.cn`）的独立凭据和路由 id。单平台插件只做 MiniMax 一家；`dsh-mmx-bridge` 反过来把额度查询做成模型可调用的工具子能力，不是常驻显示。

### <a id="quota-endpoints"></a>取数端点与上游接口演变

尽管实现各自独立，本轮候选在两家平台的取数端点上已经收敛：

- **Z.ai / 智谱**：`GET /api/monitor/usage/quota/limit`，国际站 `api.z.ai`、大陆站 `open.bigmodel.cn`；`dsh-cost-meter` 在 monitor 端点不可达时回退旧的 `/api/coding/paas/v3|v4/dashboard/billing/coding_plan/usage`。响应里 `data.limits[]` 的 `TOKENS_LIMIT` 条目即订阅 token 窗口（5 小时 session 与 7 天 weekly，`percentage` 为已用百分比，`nextResetTime` 为重置时间）；`TIME_LIMIT` 是月度工具调用次数额度。两家域名共用路径与响应形态，但 Key 不互通，401 时换域重试；大陆站 biz/monitor 网关只认裸 API Key（无 `Bearer` 前缀）。
- **MiniMax**：Token Plan `GET /v1/token_plan/remains`（国内 `www.minimaxi.com`、国际 `www.minimax.io`），`model_remains[]` 按 `model_name` 取 `general`（或 `MiniMax-M*`）一行的 5 小时 / 周剩余百分比；旧 Coding Plan 计数制端点为 `/v1/api/openplatform/coding_plan/remains`。`dsh-cost-meter` 的解析函数兼容四种响应形态：现行 `model_remains`、issue #20 的平铺结构、旧窗口数组与旧计数制。

> 来源：[cost-meter 的端点白名单与换域重试注释（issue #42 记录 2026-08 的 monitor 端点迁移）](https://github.com/Han-1413141/dsh-cost-meter/blob/50cfcacded9e25cd4a3a21f8d247dce4bf76b353/lib/coding-plans.js#L965-L995)、[MiniMax 四形态解析](https://github.com/Han-1413141/dsh-cost-meter/blob/50cfcacded9e25cd4a3a21f8d247dce4bf76b353/lib/coding-plans.js#L310-L330)；[Ychris 的 ZAI / MiniMax 路径常量](https://github.com/Ychris12138/dsh-usage-stats/blob/9bbb6d5cbc23f74327b979dd6650b7194cec8f3b/lib/subscriptions.js#L24-L40)；[musage 的 Key→端点映射](https://github.com/Thedeergod666/dsh-musage/blob/9a05ddfc9bbc4c80c541511cc6604a11b22b4f24/dsh/index.js#L51-L83)；[wenzetan 的 minimax / zai 目录项](https://github.com/wenzetan/dsh-quota-panel/blob/d7efeee726aca6a5379e9fe756d33233860d88ca/lib/index.js#L845-L851)；[jasper-zsh 对 TOKENS_LIMIT / TIME_LIMIT 与裸 Key 的记录](https://github.com/jasper-zsh/dsh-plugin-provider-quota/blob/757affff17bae5dabd4a434e51d2bf0ef0345c4a/README.md#L20-L21)；[Floating-Dreaming 的 REMAINS_URL 常量](https://github.com/Floating-Dreaming/dsh-minimax-usage/blob/9a6e2987eb825a8915fa9561e3348e6fe832a3da/trusted-plugin/index.js#L13)。

端点收敛的直接原因可见于源码注释：这两家的查询接口在 2026-08 内都发生过变动——Z.ai 把额度查询迁到 monitor 端点（cost-meter issue #42），MiniMax 的 Token Plan 响应换过结构（issue #20）。这类插件的主要维护成本来自上游接口演变，而不是 DSH 的插件接口；`dsh-cost-meter` 把每次变更的 issue 编号写进端点注释，`andyfan1094/dsh-minimax-usage-pro` 的 README 则记录了宿主侧 trusted bundle plugin 权限变化的适配。评估维护信号时，提交是否在追这类变更比提交总数更说明问题。

### <a id="quota-adjacent-scope"></a>相邻但不属于本轮范围的项目

- [`MeteorNOX/DeepSeek-Balance-Whale-Widget`](https://github.com/MeteorNOX/DeepSeek-Balance-Whale-Widget)（2408 星，2026-09-15 快照）是本轮发现里 stars 最高的余额类插件，但只盯 DeepSeek 账户余额，不覆盖 MiniMax / Z.ai；stars 高不等于覆盖目标平台。
- [`dsh-plugin-subscriptions`](#2026-08-26-plugin-details) 带额度展示，但四家 Provider 为 Codex / Claude / Grok / Copilot。
- [`dsh-web-search-zai`](#web-search-community-providers) 消耗 Z.ai Coding Plan 的 MCP 点数（自述一次搜索一点），属于"花额度"而非"显示额度"。
- 同需求存在于其他宿主：`JochenYang/minimax-status`（VSCode 状态栏 / OpenClaw / Claude Code statusline）、`Safphere/glm-usage-vscode`（VSCode）、智谱官方 [`zai-coding-plugins`](https://github.com/zai-org/zai-coding-plugins) 的 `glm-plan-usage`（Claude Code 用量查询插件）。它们的取数端点与本轮 DSH 插件收敛的端点一致，但接入方式绑定各自宿主，不能照搬安装。

### <a id="quota-stars-maintenance"></a>stars 与维护节奏的对照

把两个维度放在一起看，本轮样本呈三类分布：

- **stars 与维护同时领先：** `dsh-cost-meter`（301 星，09-01 以来 78 次提交，最近提交即调研当日）是唯一同时进入 stars 前列且持续追上游接口变更的仓库；它的定位是"费用 + 额度"复合面板，MiniMax 与 Z.ai 是九家 Coding Plan 中的两家。
- **stars 中等、维护分化：** 两个 `dsh-usage-stats`（154 / 1 星）与 `dsh-usage`（94 星）同为用量面板；wannanbigpig 版 09-01 以来 18 次提交、Ychris 版 7 次，`dsh-usage` 停在 08-31。stars 排名与提交节奏在这里已经不同序。
- **单平台小插件集中在 8 月中旬：** MiniMax 专用与 provider-quota 类仓库的 stars 都不超过 10，多数最后一次提交落在 08-14 至 08-31；其中 `wenzetan/dsh-quota-panel`（4 次）与 `dsh-mmx-bridge`（2 次）9 月仍有提交，其余归零。

单平台插件代码量小、阅读成本低，但同样依赖上游接口稳定；聚合插件覆盖面宽，停更一个月就可能对某家平台显示失效。同名仓库问题在本类目尤其密集（见[仓库快照](#quota-repo-snapshot)的同名提醒），比对 stars 或安装时都应先确认 owner。

### <a id="quota-validation-boundary"></a>验证范围

- 未把任何候选装进运行中的 Profile，未用真实 MiniMax / Z.ai 凭据发起请求；上表"能显示"均为源码与 README 自述，含端点返回结构的字段名。
- 未核对 npm 发布包与仓库字节的一致性；`jasonsun29/ds-balance-card`、`Thedeergod666/dsh-musage`、`ovensi/dsh-plugin-minimax-usage`、`jasper-zsh/dsh-plugin-provider-quota`、`grishworld-007/dsh-quota-panel` 未发布 npm，安装只能走 Git 源或本地目录，Git 安装的构建自包含性未验证。
- 未评估各插件自注册 HTTP 路由的请求栅栏（Host / Origin fence）与写入范围；安装前应按[传输与下载的安全边界](#file-transfer-security-boundaries)的口径单独审计。
- stars、npm 版本与提交节奏均为 2026-09-15 快照，会随时间变化；上游查询接口（MiniMax / Z.ai 的额度端点与响应形态）也可能再次调整，引用本节端点时先回仓库确认。

## <a id="2026-09-16-desktop-remote-clients"></a>2026-09-16 · 桌面客户端与远程 dsh 连接

本轮专题是"DSH 的桌面客户端有哪些、哪些支持把 dsh 进程放在另一台机器上、本机桌面只作为客户端使用"。官方仓库 master 已新增 `apps/desktop`，但进程模型仍是"桌面自带本地后端、不开 Web 端口"；社区生态中真正意义上的"客户端连远程 dsh"分散在插件 Host + 中继、手机附加端与 SSH 类插件三个方向，且多个仓库在 [2026-08-17 快照](#packaging-and-community)之后更名或转向。官方 Web 的访问控制模型与三条远程接入路径是本轮的判定基线，见 [DSH Web 的访问控制](dsh.md#web-trusted-host)与[远程接入 DSH Web 的方式](dsh.md#remote-access-methods)。

**调研时间：** 2026-09-16（Asia/Shanghai）

**调研目标：**

- 核对官方 `apps/desktop` 的传输与进程模型，确认是否存在"连接远程 dsh URL"模式。
- 盘点社区桌面与多端客户端，按"后端归属"与"远程方向"分类。
- 区分远程连接的四种拓扑，并判定"附加到 systemd 托管的既有 `dsh web`、不重启进程"这一严格条件下的可行路径。
- 更正本轮之前资料中的仓库名与能力描述。

> **证据边界：** stars、创建与推送时间为 2026-09-16 的 GitHub API 快照；官方仓库固定 master `0d1f5000`（2026-09-15），社区仓库各固定 HEAD SHA。所有能力描述来自固定版本的 README 与仓库元数据；未安装任何客户端，未对任何组合做真实远程连接验收。`plutoczm/deepseek-harness-vscode` 只做 README 与文件树扫描，未逐行审计源码。候选发现使用 Z.AI 网页搜索、GitHub 仓库搜索、DSH 插件商店快照与官方 discussions（[#76](https://github.com/deepseek-ai/deepseek-harness/discussions/76)、[#995](https://github.com/deepseek-ai/deepseek-harness/discussions/995)、[#2177](https://github.com/deepseek-ai/deepseek-harness/discussions/2177)、[#5530](https://github.com/deepseek-ai/deepseek-harness/discussions/5530)、[#6410](https://github.com/deepseek-ai/deepseek-harness/discussions/6410)）。

### <a id="desktop-remote-official"></a>官方桌面的进程模型

master 的 `apps/` 下新增了 `apps/desktop`（Electron 壳）与 `apps/desktop-host`（私有 Desktop Host 包，无独立 README）。官方桌面的开篇定义就排除了远程模式：它**不打开任何监听端口**，由捆绑的上游 Node.js 子进程启动 dsh，Fetch 请求与流式响应走带版本的分帧字节管道，生命周期走 Node IPC，客户端资产由 `dsh-app://` 自定义协议提供。Transport 决策行把理由写明：监听式 Web 服务会引入端口归属、认证、CORS 与暴露面问题。平台覆盖 Windows x64 与 macOS（arm64/x64），Linux 不是发布目标；桌面独占 `$DSH_HOME/profiles/desktop`，与 CLI 不共享可执行包与插件激活。

因此官方桌面没有"填写远程 dsh URL"的入口，也不提供 `webServer`——连依赖 HTTP 路由的 Web "Open In..." 动作都被禁用。官方口径下的远程使用仍是把浏览器接到远端 Web：SSH 本地隧道、受控 TCP relay 或反向代理，配合启动 token 兑换会话 cookie；`dsh web` 默认只监听 `127.0.0.1:3080`，CLI 把 `--host 0.0.0.0` 作为安全错误拒绝。给第三方远程客户端留的官方承载面是 v0.1.2 起的 Typert Remote Gateway（rc.2 为 legacy ApiProxy），下文 `ds-harness-remote` 的会话流量即经由它传输。

> 来源：[官方桌面不开端口的定义](https://github.com/deepseek-ai/deepseek-harness/blob/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/apps/desktop/README.md#L5)、[Transport 决策行](https://github.com/deepseek-ai/deepseek-harness/blob/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/apps/desktop/README.md#L16)、[Linux 非发布目标](https://github.com/deepseek-ai/deepseek-harness/blob/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/apps/desktop/README.md#L91)、[无 webServer 导致 Open In... 禁用](https://github.com/deepseek-ai/deepseek-harness/blob/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/apps/desktop/README.md#L199)、[`--host 0.0.0.0` 拒绝与信任校验](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-alpha.5/packages/bundle/web-app/src/startup.ts#L74-L75)、[官方远程接入三条路径](dsh.md#remote-access-methods)。

### <a id="desktop-remote-client-snapshot"></a>桌面与多端客户端总览

"支持远程"先要分清方向：桌面壳把本地 dsh 暴露给别人（反向），还是桌面壳作为客户端连接别处正在运行的 dsh（正向）。下表按此分类；Stars 为 2026-09-16 快照。

| 客户端 | Stars | 平台 | DSH 后端归属 | 连接另一台机器上的 dsh |
|---|---:|---|---|---|
| 官方 `apps/desktop` | — | Win / macOS | 捆绑 Node 子进程 + `dsh-app://` 私有协议 | 无远程模式 |
| [`anywhere-labs/dsh-desktop`](https://github.com/anywhere-labs/dsh-desktop/tree/5510cb1203838f2d55f9bbd52cdcfaae1cad5eac) | 26926 | Win / macOS | 本地 Host，桌面壳本身是 DSH 插件 | 无客户端模式；可选局域网暴露（**无鉴权**）；≥2.0.9 内置手机远程（方向相反） |
| [`liguobao/dsh-desktop`](https://github.com/liguobao/dsh-desktop/tree/f4f85cb7d67a773b6cc74ac3774b50db76ba40fd) | 38 | Win / macOS / Linux | 本地捆绑 Harness（加固 Electron 窗口） | **有**：内置 `ds-harness-remote` 客户端，可连另一台装了插件 Host 的机器 |
| [`tscodeplus/dsh-desktop`](https://github.com/tscodeplus/dsh-desktop/tree/843a8d097cdc25bdd02cf63afee9acdb4476ec2e) | 1 | Win / macOS | Tauri 2 + Node sidecar 拉起本地 `127.0.0.1:3080` | 无，README 明示 local-only、不做远程访问 |
| [`Dinis0214/dsh-desktop-lite`](https://github.com/Dinis0214/dsh-desktop-lite/tree/3220892aacd71102f8a5fe0b25aef6d8f99077da) | 0 | macOS / Linux / Win | 原生壳自管理本地 3080（常驻/随窗双模式） | 无远程 URL 配置（配置项仅 port/dshPath/nodePath） |
| [`fufankeji/deepseek-harness-studio`](https://github.com/fufankeji/deepseek-harness-studio)（`plutoczm` 仓库当前形态） | 641 / 0 | macOS / Win | 桌面主进程启动本地 `dsh web` | 无；"手机远程与消息通道"在路线图中未实现 |
| [`sunkeycn/dsh-desktop`](https://github.com/sunkeycn/dsh-desktop/tree/17fee13b5618b9ed8c467be15f79a446e162db22) | 1 | macOS | 本地 Host + 捆绑 `frpc 0.71.0` | 反向：FRP 隧道把本机 3080 转发到自建 `frps` 供手机访问 |
| 浏览器（任意） | — | 任意 | 任意远端 | 官方远程路径：SSH 隧道 / relay / 反代 + token 兑换 |

> 来源：[官方桌面定义](https://github.com/deepseek-ai/deepseek-harness/blob/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720/apps/desktop/README.md#L5)；[anywhere-labs 默认仅回环监听](https://github.com/anywhere-labs/dsh-desktop/blob/5510cb1203838f2d55f9bbd52cdcfaae1cad5eac/README.md#L116)、[局域网开放无鉴权的危险提示](https://github.com/anywhere-labs/dsh-desktop/blob/5510cb1203838f2d55f9bbd52cdcfaae1cad5eac/README.md#L118)、[手机远程 2.0.9 起内置](https://github.com/anywhere-labs/dsh-desktop/blob/5510cb1203838f2d55f9bbd52cdcfaae1cad5eac/README.md#L97)；[liguobao 本地运行定义](https://github.com/liguobao/dsh-desktop/blob/f4f85cb7d67a773b6cc74ac3774b50db76ba40fd/README.md#L5)、[远程会话访问特性](https://github.com/liguobao/dsh-desktop/blob/f4f85cb7d67a773b6cc74ac3774b50db76ba40fd/README.md#L14)、[Linux AppImage](https://github.com/liguobao/dsh-desktop/blob/f4f85cb7d67a773b6cc74ac3774b50db76ba40fd/README.md#L32)；[tscodeplus local-only 设计](https://github.com/tscodeplus/dsh-desktop/blob/843a8d097cdc25bdd02cf63afee9acdb4476ec2e/README.md#L26)、[不做远程访问](https://github.com/tscodeplus/dsh-desktop/blob/843a8d097cdc25bdd02cf63afee9acdb4476ec2e/README.md#L57)；[lite 的配置项仅 port 等](https://github.com/Dinis0214/dsh-desktop-lite/blob/3220892aacd71102f8a5fe0b25aef6d8f99077da/README.md#L162)、[随窗模式启停后端](https://github.com/Dinis0214/dsh-desktop-lite/blob/3220892aacd71102f8a5fe0b25aef6d8f99077da/README.md#L36)；[Studio 由桌面主进程启动本地 dsh web](https://github.com/plutoczm/deepseek-harness-vscode/blob/a8ea02c4390ccea851da6e30b3236a7b5aa0d877/README.md#L60-L66)；[sunkeycn 捆绑 frpc 供手机访问](https://github.com/sunkeycn/dsh-desktop/blob/17fee13b5618b9ed8c467be15f79a446e162db22/README.md#L34)、[只允许转发本机 3080](https://github.com/sunkeycn/dsh-desktop/blob/17fee13b5618b9ed8c467be15f79a446e162db22/README.md#L97)、[自动加入 --trusted-host](https://github.com/sunkeycn/dsh-desktop/blob/17fee13b5618b9ed8c467be15f79a446e162db22/README.md#L100)。

没有任何桌面壳提供"填一个 URL 连到裸 `dsh web`"的通用入口：官方桌面走私有协议，tscodeplus 明示拒绝，lite 只管理本地进程，anywhere-labs 与 Studio 只暴露自己拉起的本地服务。桌面形态下唯一的正向远程连接来自 liguobao DSH Desktop 内置的 Remote 组件，它连的是装了 Remote 插件的 Host，而非裸 Web 端口。

### <a id="desktop-remote-multi-device"></a>多端远程客户端与插件 Host

正向远程连接目前最完整的方案是 [`liguobao/ds-harness-remote`](https://github.com/liguobao/ds-harness-remote/tree/d3a9dc92883cf25e78bd3e9cb303e99fc1d57add)（195 星，更名自 `deepseek-harness-remote`）。分工是"远端 dsh 装 Host 插件，任意设备做客户端"：

- **Host 侧**：`dsh plugin --profile web add ds-harness-remote@0.4.13` 后重启 Harness；纯终端的 [dsh-TUI](#2026-08-26-tui) profile 也可作 Host（`/remote login` 二维码授权）。Host 只建立出站连接，不监听公网端口。
- **Client 侧**：DSH Desktop（默认集成）、Remote Web（`dsh.r2049.cn/app`）或 Android App。客户端选择在线 Host → Workspace，复用 Harness 原生界面，工作区、工具与权限流程都留在 Host 上。
- **传输**：`Noise_IK_25519_ChaChaPoly_SHA256` 双向端到端加密，按 `LAN -> P2P -> TURN -> Relay` 协商，WebRTC 失败时降级加密 WebSocket Relay；连接需同账号 membership 与设备 identity key 双重校验。会话流量经由官方 rc.2 ApiProxy 或 v0.1.2+ Typert Remote Gateway 承载（兼容 `dsh-v0.1.1-rc.2`、`v0.1.2-alpha.1`–`rc.1`、`v0.1.5-rc.1`）。
- **边界**：公开服务使用托管中继，尚无受支持的自建中继；服务端可见网络元数据但不能读会话明文。

> 来源：[Host 无需开放公网监听端口](https://github.com/liguobao/ds-harness-remote/blob/d3a9dc92883cf25e78bd3e9cb303e99fc1d57add/README.zh.md#L47)、[web profile 安装命令](https://github.com/liguobao/ds-harness-remote/blob/d3a9dc92883cf25e78bd3e9cb303e99fc1d57add/README.zh.md#L61)、[DSH Desktop 默认集成](https://github.com/liguobao/ds-harness-remote/blob/d3a9dc92883cf25e78bd3e9cb303e99fc1d57add/README.zh.md#L54)、[dsh-TUI 作 Host](https://github.com/liguobao/ds-harness-remote/blob/d3a9dc92883cf25e78bd3e9cb303e99fc1d57add/README.zh.md#L68-L70)、[Noise 协议与双重校验](https://github.com/liguobao/ds-harness-remote/blob/d3a9dc92883cf25e78bd3e9cb303e99fc1d57add/README.zh.md#L171)、[路径协商与降级](https://github.com/liguobao/ds-harness-remote/blob/d3a9dc92883cf25e78bd3e9cb303e99fc1d57add/README.zh.md#L179)、[官方 ApiProxy / Typert Remote Gateway 承载](https://github.com/liguobao/ds-harness-remote/blob/d3a9dc92883cf25e78bd3e9cb303e99fc1d57add/README.zh.md#L198-L203)、[无自建中继](https://github.com/liguobao/ds-harness-remote/blob/d3a9dc92883cf25e78bd3e9cb303e99fc1d57add/README.zh.md#L105)。

手机侧的附加型客户端是 [`Hyna-hla/dsh-remote`](https://github.com/Hyna-hla/dsh-remote/tree/3ae5f26e5df9b5f43fc35ff7d892c23c0bef119d)（12 星，Android App）。它连接的是**电脑上正在运行的 DSH 服务**，不自己拉起后端：局域网模式直接填电脑地址，公网模式自备内网穿透（cpolar / cloudflared / ZeroTier 等）。协议逆向自 `dsh-client-connection`：上行 `POST /api/<method>`，事件流 WebSocket `ws://host/api/events.mux`（SSE 回退）。PC 端配套 `dsh-remote-access` 插件做配对码互信与通道 token；公网域名必须写入 `client-connection.trustedHosts` 白名单（**重启 DSH 生效**），否则核心 Host 围栏 403。

> 来源：[连接正在运行的 DSH 服务](https://github.com/Hyna-hla/dsh-remote/blob/3ae5f26e5df9b5f43fc35ff7d892c23c0bef119d/README.md#L8)、[局域网/公网两种模式](https://github.com/Hyna-hla/dsh-remote/blob/3ae5f26e5df9b5f43fc35ff7d892c23c0bef119d/README.md#L45)、[trustedHosts 白名单重启生效](https://github.com/Hyna-hla/dsh-remote/blob/3ae5f26e5df9b5f43fc35ff7d892c23c0bef119d/README.md#L61)、[事件流协议](https://github.com/Hyna-hla/dsh-remote/blob/3ae5f26e5df9b5f43fc35ff7d892c23c0bef119d/README.md#L71)。

相邻但未复核源码的移动入口：`anywhere-labs/Agents-Anywhere`（901 星，跨设备 Agent 工作台，DSH Desktop ≥2.0.9 内置的手机远程即基于它）、`dsh-remote-mobile`（扫码接入的设置面板插件）、`tongwoojun/dsh-ntfy-remote`（ntfy 通知式手机交互，官方 discussion #6410）。

### <a id="desktop-remote-ssh-plugins"></a>SSH 远程工作区插件：后端仍在本地

`dsh-plugin` topic 下的 "remote" 命名多数属于另一类拓扑：Harness 进程留在本地，Agent 的文件与命令工具经 SSH 落到远端机器。[`flymysql/dsh-remote`](https://github.com/flymysql/dsh-remote/tree/34082745105be446252556d0d5e04bdf27fa0fc0)（81 星）的定位即"**you connect out**"——多机 SSH 注册表 + 远程工作区选择器，远端目录镜像为本地 workspace 对象，20 个 `rw_*` 模型工具经 SFTP/SSH 操作远端。它有一个实验性的官方 Desktop 兼容分支：路由经 `ctx.connection.fetch` 走 Desktop 的 `dsh-app:` carrier，这从侧面证明官方桌面虽无 `webServer`，仍向插件暴露了带鉴权的 Fetch 通道。同类的还有 `hehehe1234567894/dsh-ssh-remote`（纯远程模式工具集）与 `weisiren000/dsh-remote-ssh-ops`（远程运维，含 JumpServer）。

[`Yan-Zero/dsh-remote-ssh`](https://github.com/Yan-Zero/dsh-remote-ssh/tree/21d727cbe24fbae283196e5101adb3de2bdd9157)（9 星，最后提交 2026-08-16）提供两种模式：**透明远程工作区**（本地 AI runtime + 工具经 VS Code Agent Host Protocol 路由到 SSH 主机，无第二套 `remote_*` 工具）；**Full Backend 模式**经 SSH 上传版本匹配的 `dsh-host` bundle 安装到远端 `~/.dsh-host`，重连时发现已注册 PID 与随机 loopback 端口，经 OpenSSH 动态 SOCKS 通道接回——本地 Web/TUI 只作协议客户端，"Open Backend in Web" 再加本地同源代理供浏览器访问。注意它连接的是**自己部署的 dsh-host backend**，不是远端已有的 systemd `dsh web`。该插件的兼容面停在 DSH `0.1.0-rc.6`（当前官方已到 `0.1.5-rc.2`），且 bundle 选 `danger-full-access` + 审批 `never`，安全姿态需按其 README 的隔离建议评估。

> 来源：[flymysql 的 connect-out 定位](https://github.com/flymysql/dsh-remote/blob/34082745105be446252556d0d5e04bdf27fa0fc0/README.md#L15)、[官方 Desktop 兼容实验分支](https://github.com/flymysql/dsh-remote/blob/34082745105be446252556d0d5e04bdf27fa0fc0/README.md#L61-L69)；[Yan-Zero 两种模式定义](https://github.com/Yan-Zero/dsh-remote-ssh/blob/21d727cbe24fbae283196e5101adb3de2bdd9157/README.md#L7)、[Full Backend 上传 dsh-host](https://github.com/Yan-Zero/dsh-remote-ssh/blob/21d727cbe24fbae283196e5101adb3de2bdd9157/README.md#L109)、[Open Backend in Web](https://github.com/Yan-Zero/dsh-remote-ssh/blob/21d727cbe24fbae283196e5101adb3de2bdd9157/README.md#L116)、[danger-full-access + never](https://github.com/Yan-Zero/dsh-remote-ssh/blob/21d727cbe24fbae283196e5101adb3de2bdd9157/README.md#L159)、[兼容面 0.1.0-rc.6](https://github.com/Yan-Zero/dsh-remote-ssh/blob/21d727cbe24fbae283196e5101adb3de2bdd9157/README.md#L165)。

### <a id="desktop-remote-topologies"></a>远程连接的四种拓扑与"附加既有进程"判定

把上面的项目放回拓扑维度，"桌面连远程 dsh"实际是四种不同的事：

| 拓扑 | 代表 | 远端需要什么 | 对既有进程的影响 |
|---|---|---|---|
| 附加既有 `dsh web`（attach） | 浏览器 + SSH 隧道；`Hyna-hla/dsh-remote` 手机 App | 已运行的服务 + 可达的 authority | SSH 隧道下零改动；公网/局域网域名需进 `trustedHosts`（重启生效） |
| 插件 Host + 中继 | `ds-harness-remote`（Desktop/Web/Android 客户端） | 装插件的一次性重启，此后 Host 常驻出站 | 之后客户端随时接入，无需公网端口 |
| 本地 Agent + 远程工具执行 | `flymysql/dsh-remote` 等 SSH 工作区插件 | 仅 SSH 账户 | 与远端 dsh 进程无关（远端可以根本没有 dsh） |
| 远端专属 backend | `Yan-Zero/dsh-remote-ssh` Full Backend | 插件上传并维护的 `~/.dsh-host` | 连接对象不是既有 systemd `dsh web` |

对"远端 `dsh web` 由 systemd 托管、客户端不能重启它"这一严格条件的判定：**免重启且免改动的路径只有浏览器经 SSH 本地隧道**（loopback authority 直接过信任校验，token 兑换一次即得会话 cookie）；手机附加端走公网域名时 `trustedHosts` 写入需重启一次才生效，不满足零重启；`ds-harness-remote` 需要装插件的一次性重启，此后才是不碰进程的随时接入；SSH 工具类与 Full Backend 类则与既有进程无关。桌面壳形态下没有满足该条件的方案——唯一具备正向远程能力的 liguobao DSH Desktop 也只连 Remote 插件 Host。

### <a id="desktop-remote-corrections"></a>对本轮之前资料的勘误

- **仓库名变更**：`liguobao/deepseek-harness-remote` → `liguobao/ds-harness-remote`；`tscodeplus/deepseek-harness-desktop` → `tscodeplus/dsh-desktop`；`anywhere-labs/deepseek-harness-desktop` → `anywhere-labs/dsh-desktop`。旧链接经 301 跳转仍可解析，[2026-08-17 快照](#packaging-and-community)中 anywhere-labs 的固定 commit 引用不受影响，但新引用应使用新名。
- **`plutoczm` 项目的能力描述**：此前资料称其为"读取 `~/.ssh/config`、SSH 到远程 Linux 启动官方 dsh 并建立本地端口转发的 Remote Desktop"。本轮快照（HEAD `a8ea02c4`）的 README 描述的是 Studio 桌面端——Electron 承载、桌面主进程启动并管理**本地** `dsh web`、手机远程列为规划项；文件树扫描（8756 个文件）中的 ssh/remote 命中全部来自其 fork 的官方仓库内部结构（Typert remote、`packages/api/remotes` 等），未发现 SSH 远程桌面特性。旧说法在本快照中无依据。
- **`Yan-Zero/dsh-remote-ssh` 的维护状态**：最后提交停在 2026-08-16，兼容面为 DSH `0.1.0-rc.6`；引用其 Full Backend 能力时应注明版本距离。
- **官方桌面**：此前"默认启动内置本地 dsh、经 Electron IPC 通信、不开放 Web 端口、无文档化远程模式"的概括与 master `0d1f5000` 一致；本轮补充的证据是它连插件 HTTP 路由（`webServer`）都不提供。

### <a id="desktop-remote-validation-boundary"></a>验证范围

- 未安装任何桌面客户端或插件，未在两台机器间完成真实远程连接、审批或文件预览验收；上表能力均为固定版本 README 与仓库元数据自述。
- `Hyna-hla/dsh-remote` 局域网模式是否也需要 `trustedHosts` 信任条目，README 未说明，未实测；其协议为逆向实现，对 DSH 后续版本的兼容性无承诺。
- `ds-harness-remote` 的托管中继信任模型（服务端可见元数据、设备 identity、重放保护）依其自述文档，未独立审计；自建中继尚不可用。
- `plutoczm` 仓库未做逐行源码审计，勘误结论基于 README 与文件树扫描。
- stars 与推送时间为 2026-09-16 快照；官方 `apps/desktop` 与 `apps/desktop-host` 处于快速演进期，引用前先回仓库确认现状。

## <a id="2026-09-18-ppt-master-plugins"></a>2026-09-18 · PPT 生成插件与 PPT Master 封装

本轮专题是"是否已有把 PPT Master 封装成 DSH 插件的项目，以及 DSH 的 PPT 生成插件类目概况"。上游 PPT Master 是独立的跨 harness Agent Skill，DSH 插件生态中已有两个互不相关的封装；类目整体沿原生 PPTX 编译、HTML 放映、DSL + 本地可视化编辑器、工作流辅驾四条路线分化。结论记录在本章末尾。

**调研时间：** 2026-09-18（Asia/Shanghai）

**调研目标：**

- 确认是否存在把 PPT Master（`hugohe3/ppt-master`）封装成 DSH 插件的仓库，并核对封装方式、安装路径与运行时依赖。
- 以 GitHub `dsh-ppt in:name` 检索为线索盘点 PPT 插件类目，按路线归类并记录维护信号。
- 标记各封装的离线部署边界与 npm 发布状态。

> **证据边界：** stars、创建与更新时间为 2026-09-18 的 GitHub API 快照。四个核心仓库固定到本轮 HEAD：`pn1024/dsh-ppt-master` `3c95646`、`per1x/dsh-plugin-ppt-master` `abab5fa`、`STARDUSTLC666/dsh-ppt` `ffb3036`、`z953218350/dsh-np-ppt` `2594d90`；能力描述均来自固定 commit 的 README，未克隆仓库、未逐行审计源码，未把任何候选装进运行中的 Profile 做验收。候选发现使用 Z.AI 网页搜索与 GitHub 仓库搜索（`dsh-ppt in:name`，命中 21 项）；OpenAI Codex 搜索两次请求失败，本轮未采用其结果。DSH 插件商店（dsh.deepseek404.com）的类目页与详情页本轮直连均失败（网络错误），商店收录仅以搜索快照作发现信号。

### <a id="ppt-master-upstream"></a>上游 PPT Master 本体

[`hugohe3/ppt-master`](https://github.com/hugohe3/ppt-master)（55,002 星、4,359 fork，Python，创建于 2025-12-10，快照时最近更新 2026-09-17）定位为把文档或主题转成原生 PowerPoint——原生形状、转场动画、按需的数据图表、从演讲备注生成旁白、支持自有 `.pptx` 模板。它本身是跨 harness 的 Agent Skill：腾讯新闻 2026-08-21 的上手教程显示，不装任何插件、把 PPT Master 作为 Skill 放进 DSH 即可运行，DSH 会遵照 skill 要求打开浏览器标签页确认设计方案。插件封装的增量因此不在生成能力本身，而在安装、Python 依赖与离线部署管理。

> 来源：[上游仓库元数据](https://github.com/hugohe3/ppt-master)（2026-09-18 快照）；[腾讯新闻的 DSH + PPT Master Skill 上手记录](https://view.inews.qq.com/a/20260821A03P3M00)（2026-08-21，媒体教程信号）；[V2code 的 PPT Master 教程](https://www.v2code.ai/post/ppt-master-tutorial-native-editable-pptx-guide)（第三方教程信号）。

### <a id="ppt-master-wrappers"></a>PPT Master 的两个 DSH 封装

两个仓库创建时间相隔五天、无 fork 关系，各自独立封装同一上游：

| 封装 | 固定 commit | Stars | 创建 | 安装 | 封装方式 |
|---|---|---:|---|---|---|
| [`pn1024/dsh-ppt-master`](https://github.com/pn1024/dsh-ppt-master/tree/3c956467cd053fec36816cb7d2ca973729a5d4d1) | `3c95646`（2026-09-01） | 1 | 2026-08-31 | `dsh plugin --profile web add link:<path>` 本地 link；装后另需 `pip install -r requirements.txt` | 把上游 skill 树收进 `skills/ppt-master/`（SKILL.md + references + scripts + templates + workflows），`index.js` 注册 dsh 原生 skill provider；README 未见 npm 发布 |
| [`per1x/dsh-plugin-ppt-master`](https://github.com/per1x/dsh-plugin-ppt-master/tree/abab5fa6adb83a3cbc7da4825b99847145cc9cf3) | `abab5fa`（2026-08-26） | 0 | 2026-08-26 | Releases 下载约 51 MB tgz，离线 `npm install <tgz>` + `npx ppt-master-setup`；零运行时依赖，安装不触达 registry | 逐字节 vendor 上游 skill 树挂到 `ctx.skills`，行为与上游一致；更新即用 `scripts/sync-upstream.mjs --ref v5.1.0` 重新 vendor |

`per1x` 版自述为离线 / 内网部署设计，README 完成度明显高于 stars 反馈：setup 脚本装 Python 依赖并脚手架 `~/.ppt-master/.env`（可重跑，卸载带 `--purge-env` 选项）；skill provider 以 `includeDefaultRoots: false` 只服务自己的根、按自定义 rank 注册，项目 `.agents/skills/` 中的同名 skill 仍优先；上游带 fail-closed 的 `attribution_guard.py`，任何 skill CLI 检测到 vendor 树漂移即 exit 78。其离线能力矩阵：生成 / 美化 / 建模板 / 填充 / 增强原生 PPTX，PDF / DOCX / PPTX / Markdown / XLSX / EPUB / notebook 源转换，公式编译为可编辑 Office Math，确认 UI 与 `127.0.0.1` 实时预览编辑器全部离线可用；`edge-tts` 旁白需微软端点，旁白视频仅 Windows（驱动 PowerPoint 2016+），AI 插图需内网图像服务，题目研究与网图搜索离线不可用，`visual-review` 与模板图片参考需视觉模型，image-to-PPTX 不支持（上游限定 Codex）。README 同时注明 DeepSeek 主模型为纯文本，配视觉模型（举例通过 ModLens）可恢复视觉门控阶段——ModLens 的模型包装能力见 [2026-08-17 生态调研](#packaging-and-community)。

`pn1024` 版是更薄的直转发：`package.json` / `cordis.patch.yml` / `index.js` 加整棵 skill 树，Python 3.10+、Python 包与可选 `.env` 图像后端由用户手工安装。两者的能力差异来自上游版本与依赖管理方式，而非封装思路。

> 来源：[pn1024 的 Overview、安装与前置依赖](https://github.com/pn1024/dsh-ppt-master/blob/3c956467cd053fec36816cb7d2ca973729a5d4d1/README.md)；[per1x 的 vendor 外壳定义、离线安装、插件配置与离线能力矩阵](https://github.com/per1x/dsh-plugin-ppt-master/blob/abab5fa6adb83a3cbc7da4825b99847145cc9cf3/README.md)。

### <a id="ppt-plugins-category"></a>类目概况与其余路线

`dsh-ppt in:name` 在 2026-09-18 快照命中 21 个仓库，创建时间全部落在 2026-08-14 至 09-17，stars 最高 7。除 ppt-master 封装外，两条已核对 README 的代表路线：

| 插件 | 路线 | 要点 |
|---|---|---|
| [`STARDUSTLC666/dsh-ppt`](https://github.com/STARDUSTLC666/dsh-ppt/tree/ffb30361e1cb14b6acee58045fa5ebbc208fec21)（`ffb3036`，2026-09-12，7 星，npm `dsh-ppt`） | 工具 + 技能，纯 Node | `ppt_create` / `ppt_themes` 把一句话或 Markdown 变成 HTML + PPTX + JSON 三件套；5 主题、7 页型、转场与要点动效、演讲者备注；零运行时依赖（OOXML 与 zip 全手写，仅用 `node:fs` / `node:path` / `node:zlib`）；裸 `SKILL.md` 可跨 harness；已在 `dsh@0.1.5-rc.1` 与 18 个组件、Modlens 同载验证。已知限制：PPTX 为空白版式 + 文本框，不生成智能母版占位符 |
| [`z953218350/dsh-np-ppt`](https://github.com/z953218350/dsh-np-ppt/tree/2594d90999ec13de1e3d45b98a77ea940bf78c97)（`2594d90`，2026-08-14，2 星） | DSL + 本地编辑器 + Python 编译 | PPTD YAML DSL（每页一个 `.page` 文件）；`127.0.0.1:55173` 所见即所得编辑器（File System Access API 授权本地目录）；Python-PPTX 离线编译内核（嵌套 HTML 富文本解析、字体锁定、DrawingML 渐变）；注册「PPT 演示文稿专家」Agent preset；link 安装，未见 npm 发布 |

其余条目只作发现信号（描述来自仓库元数据，未复核源码）：`EZ118/dsh-ppt-composer`（对话生成幻灯片）、`chiang21fcb/dsh-ppt-guider`（六步工作流、SVG 中间态 + PPT-safe 约束的 dsh-preset）、`unStone/dsh-plugin-web-ppt`（读取 / 导出 `.pptx` 的纯 JS 工具）、`LeoChen98/dsh-worktable-notebook-to-ppt`（Jupyter Notebook → PPTX 工作流）、`yunfeizhu/dsh-pptx-editor` 与 `njutcm2004-cloud/dsh-pptx-preview`（编辑 / 预览）、`tjxj/dsh-wanghong-handwritten-ppt`（手写风 HTML 幻灯 + PNG 导出）、`SuperstructureJH/dsh-workbuddy-ppt`（附创作技能与 PPTD 确定性校验）、`kitterfast/dsh-ppt-maker`（composer 菜单入口）、`boe1900/dsh-ppt`、`yejiming/dsh-ppt`、`zbsph/dsh-ppt-studio`、`Huauauaa/dsh-ppt-studio`、`kkutysllb/dsh-super-ppts`、`uckkk/dsh-ppt-pages` 等。

四条路线与官方能力无交叠：DSH 官方没有 PPT 生成面，产物交付仍走通用文件交付（见[官方文件链路](#file-transfer-official-chain)）；生成类插件自带的本地编辑器 / 预览服务（`dsh-np-ppt` 的 55173、ppt-master 的确认 UI）是插件自注册的本地 HTTP 服务，不经过官方 Web 栅栏。

> 来源：[dsh-ppt 的工具面、零依赖实现与已知限制](https://github.com/STARDUSTLC666/dsh-ppt/blob/ffb30361e1cb14b6acee58045fa5ebbc208fec21/README.md)；[dsh-np-ppt 的 PPTD 架构、55173 编辑器与编译内核](https://github.com/z953218350/dsh-np-ppt/blob/2594d90999ec13de1e3d45b98a77ea940bf78c97/README.md)；[dsh-ppt 的第三方评测](https://blog.yeyupiaoling.cn/article/1789371938931)（发现信号）。

### <a id="ppt-plugins-validation"></a>验证范围

- 四个核心仓库未克隆、未逐行审计；`per1x` 的离线能力矩阵、51 MB tgz、wheelhouse 流程与 fail-closed 守卫均为 README 自述。
- 未安装任何候选进运行中的 Profile；未做真实的 PPTX 生成、编辑器联动或导出验收。
- 插件商店类目页与详情页直连失败，商店收录仅以 Z.AI 搜索快照为证；商店条目由 GitHub 公开项目自动聚合，不含人工审核。
- 上游 ppt-master 迭代快（`per1x` 的再 vendor 流程已引用 v5.1.0 tag），stars 与更新时间为当日快照；引用本节细节前先回仓库确认。
- OpenAI Codex 搜索两次失败未采用；核心候选由 Z.AI 搜索与 GitHub 仓库搜索两路独立命中，不依赖单一发现入口。

### <a id="ppt-plugins-conclusion"></a>结论

1. **有人做，且有两个互不相关的封装。** PPT Master（55k 星上游）已有 `pn1024/dsh-ppt-master`（薄转发，本地 link 安装）与 `per1x/dsh-plugin-ppt-master`（离线内网导向的逐字节 vendor 外壳）两个 DSH 插件；后者工程化程度明显更高——离线安装、setup / uninstall 脚本、上游同步脚本、漂移守卫俱全——但两者 stars 均接近零（1 / 0），属个人项目早期状态，采用前需自行验收。
2. **不装插件也能用。** PPT Master 本体是跨 harness 的 Agent Skill，直接放进 DSH 即可运行（含浏览器确认 UI）；封装的增量价值在 Python 依赖与离线部署管理，不在生成能力本身。
3. **类目已分化出四条路线**（原生 PPTX 编译 / HTML 放映 / DSL + 本地编辑器 / 工作流辅驾），全部为社区项目，stars 普遍个位数，官方无对应能力。
4. 对"真母版 / 版式 / 占位符"的原生可编辑要求，Python-PPTX 路线（两个 ppt-master 封装、`dsh-np-ppt`）覆盖；纯 Node 的 `dsh-ppt` 明言空白版式 + 文本框、不生成智能母版占位符。本轮检索由一次自制「SVG 实时预览 + python-pptx 真占位符导出」工作流触发，对照结果显示该组合落在生态现有的空档上。

## <a id="2026-09-20-sidebar-files-git-diff"></a>2026-09-20 · 右侧文件资源管理器与 git diff

本轮专题是"官方右侧文件资源管理器（文件树 + 预览）能不能看 git diff，社区插件是否补齐"。官方答案分两半：文件树与文档预览本身不感知 git；`0.1.6-alpha.2` 另在会话尾部提供每轮 changed-files 卡与右侧栏 `changes-review` 对比 tab，但那是本轮窗口的工作树快照 diff，不是任意 git diff。社区插件已经把"资源管理器内看 diff"的空档填满，且分成接管官方右侧栏、中央标签、自绘抽屉、替换工具 diff 卡、审查回注五种接入位置。

**调研时间：** 2026-09-20（Asia/Shanghai）

**调研目标：**

- 核对官方右侧栏与文件资源管理器在 `0.1.6-alpha.2` 的能力边界，确认文件树与预览是否感知 git。
- 核对官方已有的两处 diff 展示——会话内工具调用 diff 卡与每轮 changed-files 卡——的实现方式、语义边界与引入版本。
- 检索在 Web 界面提供 git diff / git 状态查看的社区插件，固定 commit 核对挂载位置与 git 执行方式。

> **证据边界：** 官方源码固定在 `ddefc45fbc`（`0.1.6-alpha.2`，2026-09-17 发布），功能引入时间按 git tag 判定：文件树 tab 随 `0.1.5-alpha.1`（2026-09-08，引入 commit `b24ebc8c`）发布，changed-files 卡与 review tab 随 `0.1.6-alpha.2`（引入 commit `f937f4e23b`，2026-09-11）发布。六个插件仓库已浅克隆并核对源码（commit 见下文各表）；stars 与推送时间为当日 GitHub API 快照。候选发现走 GitHub topic 搜索（`topic:dsh-plugin git`）、官方 Discussions 检索（issues 已关闭，`has_issues: false`）、`awesome-dsh-plugin` 目录（`5706797`，2026-09-19）与 OpenAI / Z.AI 网页搜索四路；未把任何候选装进运行中的 Profile 做验收。官方仓库 discussions #7138 的归属缺陷为报告者实测，本轮未本地复现。

### <a id="sidebar-files-official-explorer"></a>官方文件资源管理器：只列表、不感知 git

右侧栏（`dsh-client-ui-sidebar-right`）是每个会话一份的停靠面，官方实现按 `ctx.sidebarRightTabs` 注册表组织 tab 类型；`docs/subsystems/sidebar-right.md` 列出的出厂类型只有 `guide`、`text`（文档预览）、`files`（文件树）、`browser`、`subagentchat`，没有 git 相关类型。文件树 tab（`dsh-client-ui-sidebar-files`，kind `files`，band `builtin`）以会话工作目录为根，每层展开时经 `remote.workspaceFiles.list` 懒加载，点击文件用 `dsh-resource://file/session/...` 地址在预览器打开；其 README 的 Known Limitations 第一条即"Listing only. No search, artifact filter, drag-and-drop, rename, context menu, current-file highlight, or filesystem watching"。文档预览（`dsh-client-ui-sidebar-documentpreview`，kind `text`，pattern `dsh-resource://file/**`）渲染 Markdown、代码、图片、PDF、Office、HTML 与纯文本回退，没有 diff 模式。服务层 `dsh-api-workspace-files` 只暴露 `stat` / `read` / `readBytes` / `readAll` / `readRelated` / `list` / `changes`（观测流），README 明言"The service exposes no mutation operation"——整条链路没有 git 子进程、没有状态徽标、没有版本概念。

> 来源：[出厂类型清单与 kinds](https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/docs/subsystems/sidebar-right.md#L134-L141)；[文件树 tab 的注册与懒加载](https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/client/ui-sidebar-files/README.md#L27)；[Listing only 限制](https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/client/ui-sidebar-files/README.md#L57-L61)；[workspace-files 服务无 mutation](https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/api/workspace-files/README.md#L12)；[预览器渲染格式](https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/client/ui-sidebar-documentpreview/README.md#L2)。

### <a id="sidebar-files-official-diffs"></a>官方已有的两处 diff 展示

会话转录里第一处是工具调用的 `DiffBlock`：`edit` / `write` 类工具卡按 render intent 展示 before/after，数据来自工具参数，与 git 无关。第二处是 `0.1.6-alpha.2` 的每轮 changed-files 卡：Host 侧 `dsh-workspace-changes` 在 `turn/start` 与 turn 结束各做一次工作树快照（`git add --all --ignore-errors` 进临时 index、`write-tree`，对象写入会话私有临时目录并以仓库对象库为只读 alternate，不动仓库 index / objects / refs），turn 内 `diff-tree -r -M --numstat` 得到文件与行数，文件工具改过的路径另做整文件捕获以覆盖 git 不覆盖的场景；`workspace/changes` 事件入会话日志，摘要与对比留在 Host 内存。Web 侧 `ui-deliverables` 在收尾消息后渲染卡片，点击行经 `ctx.sidebarRight.openResource('dsh-resource://changes-review/session/<id>/<seq>/<turn>')` 打开右侧栏 review tab——支持 unified 与 side-by-side 双视图、换行开关、行号与增删配色、打开整个文件或调本地应用。

这条官方链路的语义边界决定它不能当作"git diff 浏览器"：对比的是该轮起止两次快照，不是当前文件内容；不能选 HEAD、暂存区、任意提交或分支对比；没有暂存 / 提交 / 还原操作；摘要与对比随 Session 与 Host 进程消亡，重启后旧轮次无卡；归属按时间窗——同一工作区的并发写入者（另一会话、IDE 构建）会落进本会话的卡（discussions #7138 报告并给出复现，维护方向是"标注本会话触碰过的路径"或 shadow repository）。

> 来源：[workspace-changes 的快照机制与覆盖规则](https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/deliverables/workspace-changes/README.md#L12)；[临时 index / write-tree / diff-tree 实现细节](https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/deliverables/workspace-changes/README.md#L58)；[review tab 的双视图与交互](https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/client/ui-deliverables/README.md#L43)；[归属缺陷报告 #7138](https://github.com/deepseek-ai/deepseek-harness/discussions/7138)。

### <a id="sidebar-files-official-seams"></a>右侧栏的扩展点

插件补 git 能力不需要改核心：`ctx.sidebarRightTabs.register({ id, kind, patterns?, priority?, canOpen?, title?, guide? })` 注册 tab 类型，`extension` band 高于 `builtin`，同一 kind 的 extension 在力时接管、卸载后 builtin 恢复；`ctx.documentPreviews.register` 给预览器加渲染器；`sidebar.right.tab.guide`（链）换 guide 体、`sidebar.right.tab.menu.item`（列表）给 tab 菜单加动作。`dsh-resource://` 资源协议经 `ResourceProtocolMap` 扩展——官方 `changes-review` 地址本身就是走这条路注册的内置示范。插件也可以完全绕开右侧栏：`conversation.view` 插槽（"对话 / 轨迹"旁的中央标签）与 `ctx.webServer` 前缀路由 + iframe 是另外两条实测在用的路。

> 来源：[tab 类型注册与优先级 band](https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/docs/subsystems/sidebar-right.md#L34-L50)；[扩展点两段注册与 guide/menu seat](https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/client/ui-sidebar-right/README.md)；[changes-review 地址注册为内置示范](https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/client/ui-deliverables/README.md#L57)。

### <a id="sidebar-files-plugin-matrix"></a>社区插件矩阵：五种接入位置

2026-09-20 的快照里，"在 DSH 界面看 git diff / git 状态"的插件按接入位置分五类。stars 只表示关注度，不替代源码审查：

| 接入位置 | 项目 | 固定 commit | Stars | git diff 能力（README + 源码核实） |
|---|---|---|---:|---|
| 接管 / 注册官方右侧栏 tab | [`omdsh-dev/DSH-better-sidebar`](https://github.com/omdsh-dev/DSH-better-sidebar/tree/1fcf43ccbedd6e66370b7fb81df2b4dd0ef2604e) | `1fcf43c`（2026-09-11） | 3677 | 工作台套件：接管内置「文件」页，另设「文件变动」tab——Git 视角（真 diff / 历史 / 暂存·提交·还原 / worktree·子仓库选择）+ 本轮文件视角双视角；统一 diff 渲染（字符级行内高亮 + 语法着色 + 上下文折叠），可展开为独立 diff tab |
| 同上 | [`2002XiaoYu/dsh-session-diff`](https://github.com/2002XiaoYu/dsh-session-diff/tree/f5b20d0001bb9955c4eebe0f2037507769e55197) | `f5b20d0`（2026-09-18） | 1 | `extension` band 接管 `dsh-resource://file/**` 文件查看器：本会话改过的文件原位渲染 git 风格 diff（增删底色、双行号、+/− 计数、「仅看改动 / 整个文件」切换），另注册改动文件清单 tab；未改动文件保持官方查看器 |
| 中央标签（`conversation.view`，"轨迹"旁） | [`1841220388zzzcccxxx-star/dsh-git-graph`](https://github.com/1841220388zzzcccxxx-star/dsh-git-graph/tree/54790c6a4cf8644b08f460d98fcda800d5224df7) | `54790c6`（2026-09-05） | 14 | 「Git 图谱」标签：GitHub 风格提交历史图、分支过滤、单文件 diff、两次提交对比；VSCode 风格未提交改动面板（staged / changes / untracked 三组、numstat、逐文件 diff 展开），支持暂存 / 取消暂存 / 还原 / 提交 / push / pull、AI 提交信息 |
| 同上 | [`sqfcyily/dsh-workspace-files`](https://github.com/sqfcyily/dsh-workspace-files/tree/9416837cea5c3451f18c9fdc7577e28dd5e32855) | `9416837`（2026-09-03） | 6 | 「文件」标签：目录树 + 预览，git 仓库时文件名带状态角标、打开后可切「内容 / 改动」看 diff；无 git 时自动降级为纯浏览 |
| 自绘抽屉（不依赖官方右侧栏） | [`No-PRM/dsh-explorer`](https://github.com/No-PRM/dsh-explorer/tree/f0835e20914d1db9cd9f3a558b5977d678c84e47) | `f0835e2`（2026-08-16） | 7 | 蓝色圆钮开自绘文件树抽屉：M/A/U/D/R 徽标、脏目录点、gitignore 变暗；改动文件预览默认进 git diff 视图（HEAD vs 工作树，side-by-side） |
| 同上 | [`Wongzexu/dsh-git-status`](https://github.com/Wongzexu/dsh-git-status) | —（2026-08-26 推送） | 3 | 右缘 git 状态抽屉：提交 DAG 车道、未提交与 stash 行、行内 diff、右键分支 / tag 操作、一键 fetch 全部远程（目录描述，未克隆核实） |
| 替换会话内工具 diff 卡 | [`lehhair/dsh-diff-viewer`](https://github.com/lehhair/dsh-diff-viewer) | —（2026-09-06 推送） | 27 | PiUI 风格 diff 查看器替换 `write` / `edit` 工具卡自带的 DiffBlock（目录描述，未克隆核实） |
| 审查-回注工作流 | [`9087/dsh-diff-approval`](https://github.com/9087/dsh-diff-approval) | —（2026-09-18 推送） | 6 | 侧栏待审列表收集每次 `edit` / `write` / `str_replace_editor` 改动，整文件 diff 上按文件 / 块 / 拖选行 Keep 或 Revert，操作原子可撤销（discussions #6069） |
| 同上 | [`BrambleXu/dsh-revdiff`](https://github.com/BrambleXu/dsh-revdiff/tree/90e7f41040ede308314395b06c51c218e18e4d47) | `90e7f41`（2026-08-14） | 2 | 解析 git unified diff 成文件 / hunk / 行位，审查界面上批注并排队回注当前 Agent 会话（Reddit "Codex-style diff review" 同项目） |

模型侧 git 工具（给模型调、不画 UI diff）是相邻类目：`gxinxing/dsh-tool-git`（`git_ops` 五模式，#3826）、`lxj808624/dsh-tool-git`（八个 `git_status` / `git_diff` 类工具，#411）、`Shyboy0499/dsh-git-tools`、`omdsh-dev/dsh-tool-diff`（结构化比较）、`sakthiveltofficial/dsh-git-plugins`。

### <a id="sidebar-files-plugin-details"></a>重点插件的源码核实

`DSH-better-sidebar` 是该类目热度与完成度最高的项目。v0.19.0 起适配官方侧边栏 API（要求 DSH `0.1.5-rc.1+`，v0.19.1 自述已在 `0.1.5-rc.2` 真机验证）：右列就是 DSH 原生右侧栏，每个 tab 类型经 `ctx.sidebarRightTabs` / `ctx.sidebarRight` 注册，文件打开统一走 `openResource('dsh-resource://file/…')`，不再自绘面板；同时接管内置「文件」页与文件树。git 能力在 Host 侧 `src/git.ts` 成套实现（本轮核实：`status` / `diff(staged)` / `stage` / `unstage` / `commit` / `branches` / `checkout` / `log` / `show(rev:path)` / `commitDiff` / `discard` / `worktrees`，解析 porcelain -z、worktree list、log），客户端 `src/client/diff/rows.ts` 解析 `git diff --no-color` 并把 hunks 转成渲染段。README 另述敏感内容脱敏（凭据形态遮罩）与 `.md` / `.html` / `.pdf` 操作的特殊预览。

`1841220388zzzcccxxx-star/dsh-git-graph` 走中央标签 + iframe 路线：Host 侧 `ctx.webServer.register({ kind: 'prefix', path: '/git-graph' })` 提供 `/git-graph/api` JSON 接口，git 全部经 `execFile`（无 shell、固定参数表）；客户端在 `conversation.view` 插槽注册「Git 图谱」标签，内容是指向 `/git-graph/index.html` 的 iframe。diff 数据来自 `git diff --cached --numstat` / `git diff --numstat` 与逐文件 `git diff --no-color`（带截断上限）。

`No-PRM/dsh-explorer` 出现于官方文件树发布之前（2026-08-16，官方 `0.1.5-alpha.1` 为 09-08）：Host 侧 `/filetree/gitdiff?path=` 路由先 `rev-parse --show-toplevel` 定仓，再 `git show HEAD:<rel>` 取基线、直读工作树文件取现状，两侧各限 512 KiB、含 NUL 判二进制置空；客户端 `GitDiff` 组件用 `@codemirror/merge` 渲染 side-by-side，`canDiff` 时预览默认落在 diff 视图。安装是 monorepo 双包（`dsh-explorer` Host + `dsh-client-ui-explorer` 客户端），各走一条 `dsh plugin add github:` 命令。

`2002XiaoYu/dsh-session-diff` 是"接管官方查看器"的最小实现样本：`ctx.sidebarRightTabs` 注册两个类型——file tab（`extension` band，pattern `dsh-resource://file/**`，只对本会话改动过的文件生效）与改动清单 tab；内容读取复用官方 `remote.workspaceFiles`，diff 在客户端计算。`sqfcyily/dsh-workspace-files` 则完全不动右侧栏，在 `conversation.view` 加「文件」标签（与「对话 / 轨迹」并列），Host 经 `execFile`（带超时与僵尸进程防护）跑 git，甚至内置按 diff 生成提交信息的提示词调用。

> 来源：[better-sidebar 的原生侧边栏适配声明与文件变动双视角](https://github.com/omdsh-dev/DSH-better-sidebar/blob/1fcf43ccbedd6e66370b7fb81df2b4dd0ef2604e/README.md)、[git.ts 全套操作](https://github.com/omdsh-dev/DSH-better-sidebar/blob/1fcf43ccbedd6e66370b7fb81df2b4dd0ef2604e/src/git.ts#L300-L450)、[统一 diff 解析](https://github.com/omdsh-dev/DSH-better-sidebar/blob/1fcf43ccbedd6e66370b7fb81df2b4dd0ef2604e/src/client/diff/rows.ts#L310-L330)；[dsh-git-graph 的 `/git-graph` 前缀路由](https://github.com/1841220388zzzcccxxx-star/dsh-git-graph/blob/54790c6a4cf8644b08f460d98fcda800d5224df7/index.js#L354-L370)、[execFile 无 shell 约定](https://github.com/1841220388zzzcccxxx-star/dsh-git-graph/blob/54790c6a4cf8644b08f460d98fcda800d5224df7/index.js#L26)、[conversation.view 标签注册](https://github.com/1841220388zzzcccxxx-star/dsh-git-graph/blob/54790c6a4cf8644b08f460d98fcda800d5224df7/client.js#L44-L53)；[dsh-explorer 的 `/filetree/gitdiff` 路由](https://github.com/No-PRM/dsh-explorer/blob/f0835e20914d1db9cd9f3a558b5977d678c84e47/dsh-plugins/dsh-explorer/lib/index.js#L404-L443)、[@codemirror/merge 的 GitDiff 组件](https://github.com/No-PRM/dsh-explorer/blob/f0835e20914d1db9cd9f3a558b5977d678c84e47/dsh-plugins/dsh-client-ui-explorer/src/client/preview.tsx#L105-L148)；[dsh-session-diff 的两个 tab 类型注册](https://github.com/2002XiaoYu/dsh-session-diff/blob/f5b20d0001bb9955c4eebe0f2037507769e55197/lib/client.js#L1645-L1699)；[dsh-workspace-files 的 conversation.view 注册与 execFile](https://github.com/sqfcyily/dsh-workspace-files/blob/9416837cea5c3451f18c9fdc7577e28dd5e32855/lib/client.js#L1517-L1527)。

### <a id="sidebar-files-adjacent"></a>相邻但不属于本轮范围

- **改仓库本体的 fork**：`vaxilicaihouxian/deepseek-harness` 的 `feat/git-gui` 分支（commit `f2294b5`）给 Web profile 加 SourceTree 风格 Git GUI（历史 / 分支面板、暂存列、提交合并分支、可拖拽 Diff 窗格），是 fork 而非插件，官方更新需自行合并（discussions #5783）。
- **worktree / 快照 / 回滚**：`wloops/dsh-git-worktree`（worktree 会话目标 + 人工确认交付）、`HeathHe/dsh-worktree-panel`（worktree 管理面板）、`PerryLink/dsh-checkpoint-rewind`（Claude Code 式 `/rewind`，git 快照 + turn 边界分叉）、`dsh-file-undo`（#5738）。核心是隔离与回滚，不是 diff 浏览。
- **官方方向的社区诉求**：discussions #5073（composer 旁 git 工作区状态，点名 Claude Desktop 对齐）、#5092（workspace 行 git 徽标）说明"官方原生 git 面板"仍是被请求状态；官方 issues 关闭，诉求都走 Discussions。
- **桌面 / IDE 集成**：`See-Sol-Lab/DeepSeekGUI`（桌面端集成 Git）、`NEXTINDIE/DeepSeek-Harness-for-VS-Code`（VS Code 扩展，turn 级 git 回滚）把 diff 查看放回本地 IDE 侧。

### <a id="sidebar-files-validation"></a>验证范围

- 官方结论固定在 `ddefc45fbc`（`0.1.6-alpha.2`）；`0.1.7` 及之后的变更未跟进，changed-files 卡的归属缺陷（#7138）是否修复未复核。
- 六个已克隆仓库只读了 README 与关键源码路径，未运行其测试；其余条目（`Wongzexu/dsh-git-status`、`lehhair/dsh-diff-viewer`、`9087/dsh-diff-approval` 等）仅有目录 / Discussions / 商店页描述，未克隆核实。
- 未把任何插件装进运行中的 Profile；各项目锚定的 DSH 版本不一——`DSH-better-sidebar` v0.19.1 自述在 `0.1.5-rc.2` 验证、`dsh-explorer` 停留在官方右侧栏出现之前（其自绘抽屉与官方右侧栏的并存关系未验证）、`dsh-git-graph` 依赖 `window.__ModuleLoader__` 与 `conversation.view` 插槽的持续存在。
- 社区插件均在 Host 主进程跑 git 子进程或注册 HTTP 路由，权限边界与凭据风险按运行时篇[信任边界](dsh.md#trust-boundaries)评估；stars 与推送时间为 2026-09-20 快照。
- 发现入口的覆盖度：GitHub topic 搜索、官方 Discussions、awesome 目录与两路网页搜索（OpenAI 命中 dshbase / dshfind / dsh.pub 等目录站；Z.AI 命中知乎 / B 站评测）互有独立命中，但长尾小项目仍可能漏检。

### <a id="sidebar-files-conclusion"></a>结论

1. **官方文件资源管理器本身不看 git diff。** 文件树"listing only"、预览器无 diff 模式、`workspace-files` 服务连 git 都不执行——这不是缺功能，而是该包的既定边界。
2. **官方在另外两个位置给了 diff。** 会话内工具卡的 `DiffBlock` 展示编辑工具的 before/after；`0.1.6-alpha.2` 的每轮 changed-files 卡点击后可在右侧栏打开 `changes-review` tab（unified / side-by-side）。后者是本轮起止工作树快照的 diff：不能选 HEAD / 暂存区 / 任意提交，没有暂存提交操作，内容是快照而非当前文件，且并发写入者会落进卡片（#7138）。把它理解为"官方的 git diff 视图"时要带上这四个限定。
3. **插件生态已覆盖这个空档，且多数走官方扩展点。** 要"资源管理器里直接看 diff"：首选 `DSH-better-sidebar`（3677★，v0.19+ 走原生 `ctx.sidebarRightTabs`，接管内置文件页，真 git diff / 历史 / 暂存提交还原），轻量替代 `dsh-session-diff`（extension band 只接管本会话改动过的文件的查看器）。要看提交历史与分支：`dsh-git-graph`（中央标签，功能最全）或 `sqfcyily/dsh-workspace-files`。要审批 / 回注工作流：`dsh-diff-approval`（按文件 / 块 / 行 Keep 或 Revert）或 `dsh-revdiff`（批注回注 Agent）。要的只是工具卡 diff 更好看：`lehhair/dsh-diff-viewer`。
4. **选型注意**：这些插件都在 Host 主进程执行 git 或注册本地 HTTP 路由，等于把 git 读写面暴露给 Web UI 会话；安装前按信任边界审查源码，固定 commit 安装，不要与官方 changed-files 卡的语义混用（两者对"改动"的口径不同：官方按 turn 时间窗，插件按 git 实际状态）。
