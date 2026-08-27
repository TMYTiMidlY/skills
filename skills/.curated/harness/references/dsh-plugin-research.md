# DeepSeek Harness（dsh）Plugin 调研记录

本文件集中维护 DSH 的现成 Plugin 与社区生态，并按日期保存专题检索和源码调研。通用生态部分记录项目形态、安装入口和固定源码快照；日期章节保留当次目标、候选仓库、证据边界、阶段结论和后续验证。运行时对象、配置合成和权限模型见 [DeepSeek Harness 运行时](dsh.md)，可复用的实现、测试与发布方法见 [DeepSeek Harness Plugin 开发](dsh-plugin.md)。

> **来源口径：** 通用生态部分按 2026-08-17 的社区仓库快照整理，后续复核项在对应来源旁标明日期；日期调研各自记录时间和源码版本。项目链接固定到相应 commit，目录收录、stars 和工作流状态只作为发现与维护信号，不代替源码审查或真实验收。

## <a id="packaging-and-community"></a>现成 Plugin 与社区生态

本节汇总已经核实的社区扩展形态、安装入口和项目边界，供后续调研定位候选仓库。它不重新定义 Plugin、Profile、Tool、Provider 或 Host 权限；这些概念分别以运行时篇和开发篇为准。

### <a id="community-discovery"></a>社区项目的发现入口

官方建议 Plugin 仓库添加 [`dsh-plugin`](https://github.com/topics/dsh-plugin) topic（GitHub 仓库话题标签）。本文件把该 topic、社区目录、市场数据和已知项目之间的引用当作候选发现入口，再回到固定 commit 核对源码；被目录或市场收录不表示 package 已通过安全审查或安装验收。Plugin 作者怎样提供 topic、README 和安装信息，见开发篇的[社区发现信息](dsh-plugin.md#plugin-community-discovery)。

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

### Tool、Provider 与业务扩展

下表按开发篇定义的 [Tool 与可替换能力](dsh-plugin.md#tool-and-providers)标记各项目的扩展位置，并另外记录宿主范围、用途和安装入口。

| Plugin | 开发形态 | 宿主范围 | 用途 | 安装 |
|---|---|---|---|---|
| [`dsh-agent-teams`](https://github.com/NanmiCoder/dsh-agent-teams/tree/2b1141248f34ee28870d2e39462c0dbefaa5ffdb) | Subagent / workflow | DSH | 多 Agent team 与 workflow | `dsh plugin --profile web add @nanmicoder/dsh-agent-teams` |
| [`dsh-openpencil`](https://github.com/ZSeven-W/dsh-openpencil/tree/49b0417a6d6fe7a55056bb1a82d4c348a21a6ca6) | 业务 UI / 设计文档 | DSH | 在对话中预览和编辑 `.op` 画布 | `dsh plugin --profile web add @zseven-w/dsh-openpencil` |
| [`hindsight`](https://github.com/vectorize-io/hindsight/tree/396f63aafc9b618f04d446e2465cac95aa1cb426/hindsight-integrations/coding-agents) | 记忆 Provider | 多宿主 | 长期项目记忆、自动 recall / retain | `dsh plugin --profile web add @vectorize-io/hindsight-coding-agents` |
| [`mirage`](https://github.com/strukto-ai/mirage/tree/14f83208abb2b92d9341a10dbaa4cb4786fe7eb2/typescript/packages/dsh) | Filesystem Provider | 多宿主 | 用统一虚拟 filesystem 替换本地 FS / Bash provider | `dsh plugin --profile web add @struktoai/mirage-dsh` |
| [`modlens`](https://github.com/liustack/modlens/tree/2b71582435ff34a548efbefb74178ed133659ccb) | 视觉 Tool / Provider | 多宿主 | 直接粘贴图片，取得 OCR、布局和视觉语义证据 | `dsh plugin --profile web add @liustack/modlens` |
| [`modsearch`](https://github.com/liustack/modsearch/tree/e1dba224b72651dfe7891990dcaf674098100df2) | Web Tool | 多宿主 | Web / X 搜索与结构化引用 | `dsh plugin --profile web add @liustack/modsearch` |

ModLens 在 DSH 中既可以注册 `modlens_read_image` Tool，也可以为已确认的纯文本模型生成视觉包装条目；这项实现同时占据 Tool 与 Provider 两种分类，因此在表中并列标记，也说明视觉能力可以作为扩展接入而不必修改模型核心。

> 来源：[ModLens 的 DSH 安装、粘贴识图和模型包装](https://github.com/liustack/modlens/blob/2b71582435ff34a548efbefb74178ed133659ccb/README.zh-CN.md#L29-L76)。

### 扩展形态与权限边界

阅读上面的生态项目时，按四个维度比较即可：交互入口是桌面、TUI、Web 还是外部协议；能力落在 Tool、Provider 还是业务 UI；package 只服务 DSH 还是同时适配多个宿主；安装内容是否带 Host 入口、构建脚本或子进程。前三项的实现边界见 [DeepSeek Harness Plugin 开发](dsh-plugin.md)，最后一项的完整权限模型见运行时篇的[信任边界](dsh.md#trust-boundaries)。目录热度和安装成功都不能替代这些检查。

Plugin 卸载、热替换和失败状态的语义见开发篇的[实现 Plugin 模块](dsh-plugin.md#plugin-runtime)。

## <a id="2026-08-26-subscription-auth-surfaces"></a>2026-08-26 · 订阅登录与交互界面

本次从 DSH 官方的模型与凭据实现出发，检索社区中提供订阅登录、模型路由以及 Web / TUI 交互界面的 Plugin。本文记录截至本次源码快照已经核实的信息，并给出贴合当前目标的初步路线；最终采用方案仍需真实账号端到端验证后决定。

**调研时间：** 2026-08-26（Asia/Shanghai）

**调研目标：**

- 核对 DSH 官方 Authorization、Credentials 与 `llm-pi-ai` 的现有边界。
- 搜索能让 DSH 使用 Codex、Claude、Copilot、Kimi、OpenRouter、xAI 等订阅或 OAuth 凭据的社区 Plugin。
- 解释 Web 与 TUI 登录入口、Provider 激活、Token 保存与刷新、Adapter 复用和模型目录之间的关系。
- 找到一条尽量复用官方后端、避免重复维护各家 OAuth 的 Web 实现路线。

### <a id="2026-08-26-official-chain"></a>官方登录链路

DSH `0.1.1-rc.2` 已经把 Pi 的 Provider 登录接进官方后端，组件分工如下：

```text
Web / TUI 交互界面
        ↓
@deepseek-ai/dsh-authorization
通用 flow 状态机：list / describe / begin / cancel / prompt
        ↓
@deepseek-ai/dsh-llm-pi-ai
按 Pi catalog 注册 Provider flow，调用 Models.login()
        ↓
Pi OAuth / device-code
        ↓
DSH credential records
保存 grant、串行修改、刷新 Token
        ↓
官方 PiAiAdapter
把凭据用于模型请求
```

官方已经实现通用 Authorization flow、Pi `Models.login()` 调用、OAuth grant 到 credential record 的映射、并发刷新锁，以及凭据到 `PiAiAdapter` 请求路径的衔接。当前固定的 Pi catalog 可注册 `openai-codex`、`anthropic`、`github-copilot`、`kimi-coding`、`openrouter`、`xai` 六类 OAuth flow。

默认 Web 产品缺少最后的交互层：基础 composition 没有完整挂载这套服务，浏览器没有承载 notice、URL、device code、文本、secret、select 和取消的 wire/UI，官方 Models 页面也没有登录按钮与登录后自动激活 keyless profile 的流程。因此“官方只支持 API Key”只适用于默认界面，不适用于已经存在的后端能力。

> 来源：[Pi flow 注册与 `Models.login()`](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/llm/llm-pi-ai/src/login.ts#L120-L159)、[credential record 与刷新](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/llm/llm-pi-ai/src/auth.ts#L117-L160)、[`llm-pi-ai` 对 Authorization 的可选注入](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/llm/llm-pi-ai/src/index.ts#L205-L214)、[官方记录的浏览器 surface 边界](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/.agents/notes/implemented/architecture/2026-08-13-credential-records-and-authorization-flows.md#L52-L60)。

> Radius 属于动态 Provider，不在 DSH 当时遍历的静态 builtin catalog 中，因此不能只补前端就自动出现；这和上述六类静态 Provider 是不同边界。

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
| [ziyou979/dsh-llm-oauth](https://github.com/ziyou979/dsh-llm-oauth/tree/362312e5d01cccb5fc74fda130875d500dbaf78c) | `0.2.0` | 7 | 多 Provider OAuth Plugin | 无 Actions |
| [edge-sky/dsh-oauth-adapter](https://github.com/edge-sky/dsh-oauth-adapter/tree/559a757351093b42b695c36f77d81f8cbfe05a03) | `0.1.1-rc.11` | 3 | 官方 flow 的 Web 交互层 | `Running Copilot cloud agent` success |
| [yhyfhgs/dsh-model-hub](https://github.com/yhyfhgs/dsh-model-hub/tree/f55ac188ef24f9604e77ed127a025962c8a37c2f) | `0.2.2` | 1 | Provider 与模型管理套件 | 无 Actions |
| [ccch1mneyyy/dsh-TUI](https://github.com/ccch1mneyyy/dsh-TUI/tree/5f7d2fb9974d4575953795ced9e7feae2b241d0e) | `0.9.3` | 2573 | 基于 Ink / React 的终端界面与生态 | `Star History` success |
| [ccch1mneyyy/dsh-auth](https://github.com/ccch1mneyyy/dsh-auth/tree/fba02bcf7fb57e3d9885f73882d5835ccdf526c4) | `0.1.0` | 1 | `dsh-TUI` 携带的订阅认证 Plugin | 无 Actions |

> `pi2dsh` 的“最新 CI failure”只记录 GitHub 当时最后一条 workflow 结果，不能单独推导整个项目不可用；`dsh-TUI` 的最新成功任务名是 `Star History`，同样不构成构建与测试通过的证据。

### <a id="2026-08-26-auth-matrix"></a>认证与请求链路

Plugin 之间最重要的差别不是“有没有登录按钮”，而是登录、凭据和模型请求分别由谁维护。下表把这三层拆开：

| 项目 | 交互入口 | OAuth flow | Token 与刷新 | 模型请求 | 与官方链路的关系 |
|---|---|---|---|---|---|
| `dsh-plugin-subscriptions` | 自建 Web Settings | 自行实现 Codex、Claude、Grok、Copilot | 独立 `auth.json`，原子写入并设为 `0600` | 四套自建 Adapter 与协议转换 | 只使用 DSH Plugin 接口 |
| `pi2dsh` | 自带 `/login`，也把登录投影到 Authorization seam | Pi Provider / Extension 自己的 OAuth | pi2dsh 自有 store；DSH record 只写 `managedBy: pi2dsh` 标记 | pi2dsh ABI 兼容层 | 使用官方 Authorization 协议，不使用官方 Token 与 Adapter 链 |
| `dsh-codex` | 自建 Web、CLI、TUI | 直接调用 Pi `Models.login()` | 独立文件，跨进程锁与原子写 | 复用官方 `PiAiAdapter` | 复用请求适配层 |
| `dsh-codex-subscription` | 自建 Web RPC 与 login coordinator | 直接调用 Pi OAuth | 使用 DSH credentials service 的自定义 credential reference | 复用官方 `PiAiAdapter` | 复用凭据服务和请求适配层，不使用官方 flow/record |
| `dsh-llm-oauth` | 自建 Web、HTTP API、`/oauth` | 直接调用 Pi OAuth | 独立 `pi-ai-oauth.json` | 自建 `OAuthPiAiAdapter` | 复用 Pi catalog/OAuth，不使用官方 DSH 登录后端 |
| `dsh-model-hub` | 自建并替换整套 Models UI | 官方 Provider 调用官方 flow；另写 `qwen-code`、`codex` flow | 官方 Provider 用官方 record；自建 Provider 用独立 record scope | 官方 Provider 用官方 Adapter；自建 Provider 用自己的 Adapter | 混合实现 |
| `dsh-oauth-adapter` | 独立 Web Settings 页面与 WebSocket bridge | 直接调用官方 flow | 官方 credential record | 官方 `PiAiAdapter` | 最接近“只补 Web surface” |
| `dsh-pi-tui` | TUI `/login` | 动态读取并调用全部已注册官方 flow | 官方 credential record | 对应 Provider 的官方 Adapter | 通用的官方 TUI surface |
| `dsh-TUI` + `dsh-auth` | Ink TUI `/auth` 与 Provider 向导 | `dsh-auth` 自行提供订阅登录 | 由 `dsh-auth` 管理 | `dsh-auth` 注册自己的 Provider 路由 | 默认不走官方 `dsh-authorization` 登录链 |

从复用深度看，可以分成以下几组：

| 复用层级 | 项目 | 含义 |
|---|---|---|
| 官方全链路，只补交互 | `dsh-oauth-adapter`、`dsh-pi-tui` | Flow、record、刷新和 Adapter 均归官方；Plugin 负责与人交互 |
| 官方与自建混合 | `dsh-model-hub` | 官方 Provider 复用全链路，自带 Provider 另写全链路 |
| 只借官方 Authorization seam | `pi2dsh` | 官方 surface 可以启动它的 flow，但实际 Token 和请求仍归 pi2dsh |
| 复用 Pi 或官方 Adapter | `dsh-codex`、`dsh-codex-subscription`、`dsh-llm-oauth` | 省下一部分协议实现，但登录、存储或 Adapter 仍由 Plugin 自己维护 |
| 自建订阅栈 | `dsh-plugin-subscriptions`、`dsh-TUI` / `dsh-auth` | Provider 登录和产品能力均由社区项目维护 |

### <a id="2026-08-26-plugin-details"></a>社区实现的差异

#### <a id="2026-08-26-multi-provider-web"></a>多订阅 Web Plugin

`dsh-plugin-subscriptions` 覆盖 Codex、Claude、Grok 和 GitHub Copilot，带独立设置页、实时模型目录、额度展示、代理、reasoning effort、Fast Mode、Vision、X Search、图片和视频生成。它的完成度和开箱能力较高，但 OAuth、Token refresh、四套 Adapter 和协议翻译全部由项目自行维护；上游协议变化不会自动由官方 DSH 修复。

`dsh-llm-oauth` 覆盖 `xai`、`github-copilot`、`openai-codex`、`anthropic`、`openrouter`、`kimi-coding`，直接复用 Pi 的 catalog 和 OAuth。它仍然自建 store、HTTP/UI 和 LLM Adapter，并会在与官方 `llm-pi-ai` 同时启用相同 Provider id 时触发重复 Adapter 冲突。其 README 所述“官方只支持 API Key”已经落后于 DSH `0.1.1-rc.2`；源码中的普通 `writeFile` 也没有显式 `0600` 与原子替换，暂不适合作为主账号 Token 的默认存储。

#### <a id="2026-08-26-codex-plugins"></a>Codex 专用 Plugin

`dsh-codex` 与 `dsh-codex-subscription` 都直接调用 Pi OAuth，并复用官方 `PiAiAdapter`，但各自维护登录入口和凭据格式。

| 项目 | 凭据 | 产品能力 |
|---|---|---|
| `dsh-codex` | 独立 `$DSH_HOME/.openai-codex-auth.json`，带锁、原子写和权限检查 | Web / CLI / TUI 登录、模型筛选、Search、Vision、`gpt-image-2`、Fast Mode、额度、Responses compaction、WebSocket context reuse |
| `dsh-codex-subscription` | DSH credential reference，自定义序列化格式与 login coordinator | 浏览器/device-code 登录、额度分类与安全 reset、Search、图片生成/编辑、Fast Mode、模型级上下文、诊断与 Windows 安装流程 |

这两个项目解决的是“Codex 产品体验”，并非“为官方六类 OAuth 补一个通用 surface”。只需要 Codex 时可以单独评估；拿它们扩展到六类 Provider 会把单 Provider 的产品逻辑带进通用层。

#### <a id="2026-08-26-bridges-and-model-hub"></a>Pi 兼容层与模型管理

`pi2dsh` 是 Pi Plugin ABI 到 DSH 的通用兼容层，不只是登录 Plugin。它能运行未修改的 Pi Plugin，并把 Pi Provider 登录注册到 DSH Authorization seam；真实 Token 仍由 pi2dsh 自己的 store 保存，DSH record 只承担“由 pi2dsh 管理”的状态标记。因此它证明官方 surface 可以承载第三方 flow，但不能证明官方 `llm-pi-ai` 的 Token/Adapter 被复用。

`dsh-model-hub` 会对官方 Provider 调用 `authorization.begin()`，使用官方 record key，并写入空的 keyless profile 激活官方路由；同时它替换官方 Models 页面、模型选择器和目录管理，还自建 `qwen-code` 与 `codex` Provider。

`qwen-code` 当时不在 Pi builtin catalog 中，手工 Provider 又只能使用 API Key，因此自建 flow、record 和 Adapter 有明确用途。自建 `codex` 则与官方 `openai-codex` 重复，主要为了自行控制 Fast Mode、模型元数据和 OAuth 错误行为；代价是重复维护 OAuth 常量、刷新、模型表和 Adapter，而且其自建 route 当时只声明文本输入。

> 来源：[Model Hub 为非 catalog OAuth Provider 自建 Adapter 的原因](https://github.com/yhyfhgs/dsh-model-hub/blob/f55ac188ef24f9604e77ed127a025962c8a37c2f/src/provider/native/catalog.ts#L1-L16)、[自建 `codex` 与官方 `openai-codex` 并存](https://github.com/yhyfhgs/dsh-model-hub/blob/f55ac188ef24f9604e77ed127a025962c8a37c2f/src/provider/native/catalog.ts#L220-L280)、[官方 Provider 的 Authorization bridge](https://github.com/yhyfhgs/dsh-model-hub/blob/f55ac188ef24f9604e77ed127a025962c8a37c2f/src/auth/bridge.ts#L337-L366)。

#### <a id="2026-08-26-official-surfaces"></a>官方 flow 的交互界面

`dsh-oauth-adapter` 不保存 Token、不实现刷新，也不注册自己的 LLM Adapter。它挂载缺失的 Authorization 服务，通过 WebSocket 把官方 prompt 搬到独立的 Web Settings 页面，调用 `authorization.begin()`，成功后写入 keyless profile。当前服务端和客户端都只列出 `openai-codex`、`github-copilot`，尚未动态展示官方其余 flow。

> 来源：[Web bridge 调用官方 flow](https://github.com/edge-sky/dsh-oauth-adapter/blob/559a757351093b42b695c36f77d81f8cbfe05a03/src/index.ts#L323-L438)、[缺失服务时挂载官方 Authorization](https://github.com/edge-sky/dsh-oauth-adapter/blob/559a757351093b42b695c36f77d81f8cbfe05a03/src/authorization-fallback.ts#L13-L26)、[硬编码 Provider 表](https://github.com/edge-sky/dsh-oauth-adapter/blob/559a757351093b42b695c36f77d81f8cbfe05a03/src/protocol.ts#L8-L17)。

`dsh-pi-tui` 在终端中动态读取官方 flow，把 reference credential 与 Provider-native OAuth 合并进 `/login`，处理 notice、URL、device code、文本、secret、select、取消和失败，登录成功后创建最小 keyless profile。它不实现任何 Provider OAuth、Token store 或 LLM Adapter，是官方后端可被通用 surface 消费的直接样本。

### <a id="2026-08-26-tui"></a>终端界面

`dsh-pi-tui` 与 `dsh-TUI` 都是 DSH 的第三方终端界面，不是新的 Agent Harness，也不存在 GitHub fork 或共同 commit 历史。两者共用 DSH 的模型、工具和 Session 能力，但 UI 内核、扩展体系和认证路线不同：

| 属性 | `dsh-pi-tui` | `dsh-TUI` |
|---|---|---|
| UI 内核 | vendored Moonshot/Kimi Code `pi-tui` | 自行移植的 Ink / React reconciler |
| npm 包 | `@xmoon76/dsh-pi-tui` | `@deepseek-harness-tui/dsh-tui` |
| Profile | `pi-tui` | `dsh-tui` |
| 登录路线 | DSH 官方 `dsh-authorization` | 捆绑社区 `@deepseek-harness-tui/dsh-auth` |
| Provider 范围 | 随已注册的官方 flow 动态变化 | 由 `dsh-auth` 自己维护 |
| 产品侧重点 | Pi 风格交互、Focus、任务与 lineage、官方 flow | Claude Code 风格、主题与状态栏、VS Code 和自有插件生态 |
| Stars（2026-08-26） | 13 | 2573 |

Moonshot AI 即 Kimi 的开发公司；它维护的 `pi-tui` 源码公开放在 Kimi Code monorepo 内，而非独立公开 package。`dsh-pi-tui` vendored 了这份源码并针对 DSH 修改；项目本身仍是 XMoon 的第三方项目，不属于 Moonshot 官方。

### <a id="2026-08-26-boundaries"></a>风险与未验证项

- 本次结论来自固定 commit 的源码、README、依赖、提交历史和仓库状态；尚未用六类真实账号逐一完成登录、刷新和模型请求 E2E。
- 技术可行不等于供应商允许第三方消费订阅凭据。Codex 社区插件已经明确提示账号限制或封禁风险，真实验证不应默认使用无法承受损失的主账号。
- Claude 在第三方 harness 中可能进入 extra usage，而不是单纯消耗 Pro/Max 固定额度；OpenRouter OAuth 实质上会签发从账户余额扣费的 API Key。两者不能只因出现 OAuth 按钮就归类为固定订阅。
- DSH 当时固定 `@earendil-works/pi-ai 0.82.1`，不会自动追随 Pi 后续 Provider 与模型变化。
- Provider id 同时被官方和社区 Adapter 声明时会产生目录或 Adapter 冲突；安装多个订阅 Plugin 前必须检查 route 所有权。
- 官方 Models 卡片内部没有通用 Plugin slot。最小 Web 方案应新增独立 Settings 页面，直接往官方卡片中插按钮通常意味着替换整页。
- stars、版本和 Actions 结果会变化；它们用于判断关注度与维护信号，不替代源码和真实 E2E。

### <a id="2026-08-26-target-route"></a>目标对应的实现路线

当前目标是用较小改动，让 DSH Web 使用官方已经迁入的 Pi OAuth 后端，并覆盖尽可能多的订阅 Provider，同时避免社区 Plugin 再保存一份 Token、再实现一套刷新和协议转换。

初步推荐以 `dsh-oauth-adapter` 为 Web 基线：

```text
dsh-oauth-adapter 的 Web / WebSocket 交互桥
        +
dsh-pi-tui 的动态 flow 枚举与完整 prompt 处理思路
        +
dsh-model-hub 的 record-key 绑定与 keyless profile 激活
        ↓
官方 dsh-authorization
        ↓
官方 llm-pi-ai + Pi Models.login()
        ↓
官方 credential records / refresh / PiAiAdapter
```

具体改动保持在 surface 层：

- 用 `authorization.list()` / `describe()` 动态读取 flow，不再在服务端和客户端重复硬编码 Codex、Copilot。
- 只展示 record scope 属于 `llm-pi-ai` 且 methods 包含 `oauth` 的条目。
- 浏览器按通用类型渲染 notice、URL、device code、文本、secret、select 和取消。
- 登录成功后写入空 Provider profile `{}`，继续使用官方 route、record、刷新和 Adapter。
- 不复制 Pi OAuth client、client id、Token 文件、刷新函数或模型协议。
- `qwen-code`、Radius 等官方静态 catalog 之外的 Provider 作为独立后续范围，不和六类官方 flow 的 surface 混在第一版。

现成方案按目标区分：

| 使用目标 | 初步候选 |
|---|---|
| 立即使用多订阅 Web 功能，不要求官方后端 | `dsh-plugin-subscriptions` |
| 只需要完整 Codex 产品体验 | `dsh-codex-subscription` 或 `dsh-codex` |
| 在终端验证官方 flow | `dsh-pi-tui` |
| 开发通用官方 Web surface | `dsh-oauth-adapter` 为基线，参考 `dsh-pi-tui` 与 `dsh-model-hub` |
| 运行 Pi Plugin 生态 | `pi2dsh` |
| 使用成熟终端产品与自有生态 | `dsh-TUI` |

这仍是初步推荐，不是最终决定。进入实现前至少需要完成：官方六类 flow 的枚举测试、每种 prompt 的无凭据单元测试、少量非主账号真实登录与刷新 smoke test、登录后模型请求验证，以及供应商条款风险确认。
