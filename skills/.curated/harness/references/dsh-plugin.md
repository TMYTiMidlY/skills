# DeepSeek Harness（dsh）Plugin 开发

本文先说明如何安装现成 Plugin、判断社区扩展的形态与权限；开发部分区分创造模式中的运行时原型、独立仓库中的源码 Plugin，以及 dsh monorepo 内的 workspace package，再分别讲验证、打包和发布。模块、生命周期和各类扩展接口放在后半篇按需查阅。运行方式、内置扩展的用户行为和完整权限模型见 [DeepSeek Harness 运行时](dsh.md)。

> **来源口径：** 官方实现按 2026-08-16 的[仓库源码状态](https://github.com/deepseek-ai/deepseek-harness/commit/47f943859bef60e4160492346772ded9b24f765a)核对；本次新增和改写的社区项目按 2026-08-17 完整克隆到本地后核对，未改结论的旧条目保留原固定来源。源码和文档链接固定到对应 commit，正文不反复书写 commit hash。

## <a id="packaging-and-community"></a>安装现成 Plugin 与社区生态

dsh 把模型、工具、界面和工作流都做成 Plugin。多个 Plugin 及其默认配置可以打成一个 Bundle（可安装的组合包）；Profile 则是一套可启动的配置，决定启用哪些 Bundle。使用现成扩展时，先确认它会加入哪个 Profile、是否包含与 dsh 主进程同权限运行的代码，以及安装后需要刷新页面还是重启进程。

### 安装现成 Plugin

最常见的安装入口是：

```sh
dsh plugin --profile <name> add <package-or-git-spec>
```

`dsh plugin` 会为目标 Profile 安装依赖，并维护它启用的 Bundle 列表。package 在 `package.json` 中声明 `dsh.bundle` 后，安装命令才会把对应配置加入这个 Profile；没有这项声明时，package 虽然下载成功，却不会自动启用。

npm package 通常已经包含编译后的文件。从 Git 仓库地址安装时拿到的是源码，TypeScript package 可能通过 `prepare` 现场构建，并要求使用者显式授权 pnpm `allowBuilds`。这项授权会在安装期执行 package 代码，不受 Agent 工具沙箱保护。

安装后的生效方式取决于扩展位置：主题和部分浏览器端 Plugin 可以即时切换或刷新页面生效；运行在 dsh 主进程里的 Plugin、原生依赖或无法热加载的组合仍可能要求重启。HMR（热模块替换）不等于所有 Plugin 都能无重启安装。

> 来源：[Bundle 安装、Profile manifest 与 Git 构建授权](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/user/develop/basic/publish.md#L9-L178)。

### 官方发现约定

官方建议 Plugin 仓库添加 [`dsh-plugin`](https://github.com/topics/dsh-plugin) topic（GitHub 仓库话题标签），作用是让项目更容易被社区发现。它不是官方目录、精选名单、签名或安全审核；Web Settings 的 Plugin 列表展示当前部署的 Loader entries，包括 disabled 项，enabled 项另显示 Cordis 运行状态，但不负责联网发现和安装。

因此“能被 topic 或社区目录找到”“能被 `dsh plugin add` 安装”“已经通过安全审计”是三件不同的事。

> 来源：[官方 README 的 `dsh-plugin` 发现约定](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/README.md#L37-L45)；[Web Plugin inventory 的本地边界](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/packages/client/ui-settings-plugin-inventory/README.md#L5-L20)。

### 桌面应用与终端界面

公开 Git 历史能看到生态扩展出现得很快：ModLens 在官方 npm 发布快照当晚加入 [DSH Plugin 接入](https://github.com/liustack/modlens/commit/2860d82e2fb99a3989844dfe6ead0fce2cb14d6f)，dsh-market 在次日留下[首个市场提交](https://github.com/dsh-market/dsh-market/commit/11bb90573c291b356e7ab8cba1b11a0111ddfe6b)，Desktop 工作区随后出现[首个明确提交](https://github.com/anywhere-labs/deepseek-harness-desktop/commit/4e3eb911fdb9df60df61043358818e34c95d2e16)。这些时间只能说明公开提交节奏，不能证明作者实际从何时开始开发。

| 项目 | 形态 | 使用方式 | 环境边界 |
|---|---|---|---|
| [`DeepSeek Harness Desktop`](https://github.com/anywhere-labs/deepseek-harness-desktop/tree/8734c2cd21db2b31e670c24d9361acdaf14b7e3c) | Electron 桌面应用与 DSH Desktop Plugin | 下载 Windows 或 macOS 安装包 | Electron 开启 `runAsNode` 提供 Node 执行环境，并打包 pnpm 与固定 DSH 依赖；无需系统 Node.js、pnpm 或 DSH |
| [`dsh-TUI`](https://github.com/ccch1mneyyy/dsh-TUI/tree/c9d89664a1fc1b3faee6899add0c040b40fdfc2b) | 独立 Profile 上的全屏终端界面 | `dsh plugin --profile dsh-tui add @deepseek-harness-tui/dsh-tui`，再运行 `dsh-tui` | 纯 Plugin 挂载、不修改核心，但仍要求官方 `dsh` CLI、终端 TTY 和 pnpm |

Desktop 把官方 Web UI、后台服务和 Plugin 系统封进原生安装包；dsh-TUI 则只替换操作界面，底层仍由官方 dsh 运行。两者都属于社区项目，不是 DeepSeek 官方产品。

> 来源：[Desktop 的安装入口](https://github.com/anywhere-labs/deepseek-harness-desktop/blob/8734c2cd21db2b31e670c24d9361acdaf14b7e3c/README.md#L1-L38)；[Electron `runAsNode` 与固定 pnpm 依赖](https://github.com/anywhere-labs/deepseek-harness-desktop/blob/8734c2cd21db2b31e670c24d9361acdaf14b7e3c/dsh-plugin-desktop/package.json#L200-L250)；[应用可执行文件与打包 pnpm 的运行入口](https://github.com/anywhere-labs/deepseek-harness-desktop/blob/8734c2cd21db2b31e670c24d9361acdaf14b7e3c/dsh-plugin-desktop/src/main.ts#L190-L202)；[dsh-TUI 的纯 Plugin 形态与前置条件](https://github.com/ccch1mneyyy/dsh-TUI/blob/c9d89664a1fc1b3faee6899add0c040b40fdfc2b/README.md#L17-L73)。

### 插件市场与主题

[`awesome-dsh-plugin`](https://github.com/awesome-dsh-plugin/awesome-dsh-plugin/tree/c5f287967a26213ffdc77450db542e46899573e1) 维护社区目录数据；[`dsh-market`](https://github.com/dsh-market/dsh-market/tree/1696a52ed291b97048112c802d547599de9a5547) 读取这份目录，在 Web Settings 提供浏览、搜索、安装、更新和诊断界面：

```sh
dsh plugin --profile web add dshmarket
```

市场把主题单独列出，安装后可以即时激活、互斥切换并记住选择；普通 Plugin 可以通过 Profile 的补充配置 `cordis.patch.yml` 热停用或启用。无法热加载的变化会明确显示重启入口，因此“主题即时切换”“部分 Plugin 热开关”和“所有安装都无需重启”不能混为一谈。

目录收录、市场展示和热度都不构成 DeepSeek 背书或安全审计。

> 来源：[主题即时切换、热开关与必要时重启](https://github.com/dsh-market/dsh-market/blob/1696a52ed291b97048112c802d547599de9a5547/README.md#L12-L50)。

### Tool、Provider 与业务扩展

下表中的 Tool 是模型可以直接调用的工具，Provider 是某项底层能力的具体实现。

| Plugin | 开发形态 | 宿主范围 | 用途 | 安装 |
|---|---|---|---|---|
| [`dsh-agent-teams`](https://github.com/NanmiCoder/dsh-agent-teams/tree/2b1141248f34ee28870d2e39462c0dbefaa5ffdb) | Subagent / workflow | DSH | 多 Agent team 与 workflow | `dsh plugin --profile web add @nanmicoder/dsh-agent-teams` |
| [`dsh-openpencil`](https://github.com/ZSeven-W/dsh-openpencil/tree/49b0417a6d6fe7a55056bb1a82d4c348a21a6ca6) | 业务 UI / 设计文档 | DSH | 在对话中预览和编辑 `.op` 画布 | `dsh plugin --profile web add @zseven-w/dsh-openpencil` |
| [`hindsight`](https://github.com/vectorize-io/hindsight/tree/396f63aafc9b618f04d446e2465cac95aa1cb426/hindsight-integrations/coding-agents) | 记忆 Provider | 多宿主 | 长期项目记忆、自动 recall / retain | `dsh plugin --profile web add @vectorize-io/hindsight-coding-agents` |
| [`mirage`](https://github.com/strukto-ai/mirage/tree/14f83208abb2b92d9341a10dbaa4cb4786fe7eb2/typescript/packages/dsh) | Filesystem Provider | 多宿主 | 用统一虚拟 filesystem 替换本地 FS / Bash provider | `dsh plugin --profile web add @struktoai/mirage-dsh` |
| [`modlens`](https://github.com/liustack/modlens/tree/2b71582435ff34a548efbefb74178ed133659ccb) | 视觉 Tool / Provider | 多宿主 | 直接粘贴图片，取得 OCR、布局和视觉语义证据 | `dsh plugin --profile web add @liustack/modlens` |
| [`modsearch`](https://github.com/liustack/modsearch/tree/e1dba224b72651dfe7891990dcaf674098100df2) | Web Tool | 多宿主 | Web / X 搜索与结构化引用 | `dsh plugin --profile web add @liustack/modsearch` |

ModLens 在 DSH 中既可以注册 `modlens_read_image` Tool，也可以为已确认的纯文本模型生成视觉包装条目；这说明视觉能力不一定要改模型核心，可以作为 Tool 或 Provider 挂入现有 Profile。

> 来源：[ModLens 的 DSH 安装、粘贴识图和模型包装](https://github.com/liustack/modlens/blob/2b71582435ff34a548efbefb74178ed133659ccb/README.zh-CN.md#L29-L76)。

### 扩展形态与权限边界

开发或安装前先看扩展位置：

- TUI、Web 界面 Plugin 和外部协议都能提供“另一套操作入口”，但前两者负责显示和交互，外部协议还要规定传输的数据格式和 Agent 生命周期。
- 视觉能力可以是一个返回证据的 Tool，也可以由 Provider 替换模型或文件能力；前者接入简单，后者会改变整个产品处理数据的流程。
- 同时支持多个宿主的 package 应把核心能力和接入 dsh 的适配代码分开，避免把 dsh 的 Session、UI 或 Config 概念带进其他宿主。
- 包含主进程入口的社区 Plugin 按启动 dsh 的用户权限运行；目录热度不能替代 package 声明、依赖、构建脚本和权限检查。完整权限模型见运行时篇的 [信任边界](dsh.md#trust-boundaries)。

Plugin 卸载、热替换和失败状态的完整语义见后文的[模块、配置与生命周期](#plugin-runtime)。

## <a id="plugin-basics"></a>创造模式与源码开发

创造模式是一套运行时开发能力，源码开发则是完整的软件工程。两者可以衔接，但没有固定先后关系：需求还不清楚时，可以先在创造模式中试验；目标已经明确，或一开始就需要长期维护、测试和发布时，可以直接编写源码 Plugin。

| 目标 | 合适的做法 |
|---|---|
| 安装、启用或配置现成 Plugin | 使用 `dsh plugin`、Profile 配置或设置页面，不需要切换创造模式 |
| 了解 DSH 当前有哪些扩展点，或排查某个 Plugin 为什么没有工作 | 切换创造模式，让 Agent 检查正在运行的 DSH |
| 快速试做一个小工具、界面入口或行为调整 | 在创造模式中创建临时 Plugin |
| 开发需要依赖、持久数据、完整测试、构建或发布的功能 | 直接编写源码 Plugin |
| 修改 DSH 官方能力并准备向上游贡献 | 在 dsh monorepo 中开发 workspace package |

创造模式中运行的是**临时 Plugin**：它和正式 Plugin 都遵循 Cordis 的加载与生命周期规则，但没有对应的源码工程、构建产物和发布包。它适合回答“这个想法能否工作”，源码开发负责把答案变成长期可用的软件。

> 来源：[创造模式的定位与能力](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/apps/cli/config/agent-presets/cordis/agent.cordis.yml#L1-L27)；[创造模式与源码开发的环境差异](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/apps/cli/config/agent-presets/cordis/skills/cordis-plugin-development/SKILL.md#L10-L80)。

## <a id="creation-mode-plugin-development"></a>创造模式中的 Plugin 开发

切换到 [`cordis` preset（创造模式）](dsh.md#creation-mode)后，Agent 会保留标准模式的编码能力，并获得一组专门面向 DSH 自身的开发上下文。此时加入的是**开发手段**，不是某个现成 Plugin；具体扩展仍由 Agent 根据用户目标现场创建。

### 切换时 Agent 实际获得什么

创造模式通过三层内容指导 Agent：

| 层 | 切换时的状态 | 提供的内容 |
|---|---|---|
| 专用角色提示 | 自动加入 | 告诉 Agent 可以检查和修改当前 DSH，区分 Host 与 Agent preset 的职责，并要求复制后再修改官方 preset |
| 运行时开发提示与工具说明 | 自动加入 | 说明临时 Plugin 的用途、版本和批准规则、检查与修改流程、后台与网页界面的分工，以及常见错误和恢复方式 |
| 两份模式专用 Skill | 先加入名称与摘要，正文按需加载 | `cordis-plugin-development` 负责临时 Plugin 开发；`editing-cordis-compositions` 负责 Agent preset 与 Cordis 组合 |

因此，具体的工具调用顺序、版本处理、浏览器批准、生命周期和故障恢复规则，确实会由创造模式直接提供给 Agent；更长的示例和组合规范则保存在 Skill 正文中，在任务需要时才加载，并不是切换模式时一次性塞入全部提示词。

从用户视角看，这些上下文让 Agent 能够检查正在运行的 DSH、创建和调整临时 Plugin、诊断加载或界面问题，以及创作新的 Agent preset。网页界面的临时扩展需要用户批准后才会加载。创造模式可以接触真实的 DSH 主进程，应视为与直接执行终端命令相近的高权限能力，只在受信任的开发场景中使用。

> 来源：[创造模式自动加入的 persona 与 preset 创作规则](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/apps/cli/config/agent-presets/cordis/agent.cordis.yml#L1-L30)；[动态 Plugin 系统提示词的注册](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/packages/extensions/tool-cordis/src/index.ts#L35-L43)与[提示内容](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/packages/extensions/tool-cordis/src/prompt.ts#L3-L110)；[模式专用 Skill 的挂载](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/apps/cli/config/agent-presets/cordis/agent.cordis.yml#L241-L262)、[动态 Plugin 开发 Skill](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/apps/cli/config/agent-presets/cordis/skills/cordis-plugin-development/SKILL.md#L1-L10)与[组合创作 Skill](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/apps/cli/config/agent-presets/cordis/skills/editing-cordis-compositions/SKILL.md#L1-L10)；[Skill 目录消息只包含摘要、正文按需加载](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/packages/skill/tool-skill/README.md#L5-L31)。

### 临时 Plugin 与正式 Plugin

创造模式创建的临时 Plugin 可以作为正式 Plugin 的原型。两者使用同一套 Cordis Plugin 思路，所以已经确认的行为、扩展位置和部分代码可以继续利用；区别在于临时 Plugin 只存在于当前 DSH 进程，正式 Plugin 则有磁盘上的源码、配置、依赖、测试和发布方式。

创造模式不会一键生成正式 Plugin。确认原型后，需要让 Agent 把实现整理成源码工程，补齐配置、依赖、测试、构建和安装说明，再按正式启动方式验收。最终可以发布为独立社区 Plugin；只有要修改 DSH 官方实现时，才放进 monorepo 成为 workspace package。

### 临时版本的保留与清理

每次修改临时 Plugin 时，创造模式都会保留一份新的代码版本，旧版本仍可用于比较或恢复。上游界面和工具把这种临时代码版本称为 **Package**；这里的 Package 只是“一个版本”，与 npm package 或 workspace package 不是同一概念。

- **临时停用**：撤销 Plugin 当前提供的工具、监听和界面，但保留它及其代码版本，之后可以重新启用；
- **删除实验**：移除这个临时 Plugin 和它的全部版本；
- **重启 DSH**：清空创造模式保存在进程内存中的临时 Plugin。

需要跨重启保留的功能，应在重启前落成源码 Plugin；需要长期保留的 Agent 组合，则写入用户自己的 Agent preset。

> 来源：[创造模式随 preset 提供的运行时工具和开发指导](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/apps/cli/config/agent-presets/cordis/agent.cordis.yml#L241-L258)；[动态 Plugin 的开发范围与版本处理](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/apps/cli/config/agent-presets/cordis/skills/cordis-plugin-development/SKILL.md#L10-L47)；[版本切换、恢复和清理](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/apps/cli/config/agent-presets/cordis/skills/cordis-plugin-development/SKILL.md#L368-L420)；[临时停用并保留版本](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/packages/extensions/cordis-host-runner/src/index.ts#L455-L490)、[删除整个实验](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/packages/extensions/cordis-host-runner/src/index.ts#L202-L235)与[进程重启后的缺失状态](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/packages/extensions/cordis-host-runner/src/index.ts#L1240-L1250)。

## <a id="source-plugin-development"></a>源码 Plugin 的开发与发布

### <a id="monorepo-workspace-terms"></a>Monorepo、workspace 与 package 名称

Monorepo 是一种 Git 仓库组织方式：一个仓库容纳多个分别声明名称、依赖、构建和测试的 package，并统一保存跨 package 的变更历史。DSH 仓库把这些 package 放在 `packages/<group>/<pkg>/`，再用 pnpm workspace 统一管理。

| 层 | DSH 中的对象 | 作用 |
|---|---|---|
| Git 仓库组织 | `deepseek-harness` monorepo | 保存所有 package 的源码与提交历史 |
| Workspace 管理 | 根目录的 `pnpm-workspace.yaml` | 选择成员、统一安装与锁定依赖、连接本地 package |
| Package 身份 | 每个成员的 `package.json` 中的 `name` | 提供依赖声明和 `import` 使用的名称 |
| JavaScript 运行时 | Node.js | 运行构建后的 DSH 与 Plugin 代码 |

DSH 根目录的 `pnpm-workspace.yaml` 用 `packages/*/*` 选择成员，因此 `packages/core/session` 和 `packages/core/agent` 都属于同一个 workspace：

```text
deepseek-harness/
├── pnpm-workspace.yaml
└── packages/
    └── core/
        ├── agent/package.json
        └── session/package.json
```

`packages/core/session/package.json` 声明这个目录中 package 的正式名称：

```json
{
  "name": "@deepseek-ai/dsh-session"
}
```

`packages/core/agent/package.json` 再通过这个正式名称声明依赖：

```json
{
  "peerDependencies": {
    "@deepseek-ai/dsh-session": "workspace:^"
  }
}
```

pnpm 先按成员路径找到各个 `package.json`，再按 `name` 匹配依赖。`packages/core/session` 提供仓库内的物理位置和 `core` 分类，`@deepseek-ai/dsh-session` 提供依赖与导入使用的 package 身份。`workspace:^` 在本地选择同一 workspace 中名称匹配的 package，发布时转成对应的 caret 版本范围；`workspace:*` 使用同样的本地匹配方式，发布时转成该 package 的确切版本。根目录执行 `pnpm install` 会安装整个 workspace，并把依赖解析记录在根目录的 `pnpm-lock.yaml`。

> 来源：[DSH 的 workspace 成员声明](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/pnpm-workspace.yaml#L1-L4)、[`dsh-session` 的 package 名称](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/packages/core/session/package.json#L1-L12)、[`dsh-agent` 对 `dsh-session` 的 workspace 依赖](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/packages/core/agent/package.json#L39-L56)与 [pnpm workspace protocol](https://pnpm.io/workspaces#workspace-protocol-workspace)。

Workspace 由各生态的 package manager 或构建工具提供。JavaScript 生态中的 npm、pnpm、Yarn 和 Bun 都能管理 workspace；pnpm、Yarn 和 Bun 支持 `workspace:` 依赖范围，npm workspace 通常使用 package 的 semver 范围连接本地成员。Rust 的 Cargo workspace、Go 的 `go.work`、Java 的 Maven/Gradle 多项目构建以及 Python 的 uv workspace 承担同类职责。Monorepo 可以容纳这些语言中的任意一种或多种，具体工具决定成员声明和本地依赖语法。

> 参考：[npm workspaces](https://docs.npmjs.com/cli/v11/using-npm/workspaces)、[Yarn workspaces](https://yarnpkg.com/features/workspaces)、[Bun workspaces](https://bun.sh/docs/pm/workspaces)、[Cargo workspaces](https://doc.rust-lang.org/cargo/reference/workspaces.html)、[Go workspaces](https://go.dev/doc/tutorial/workspaces)、[Maven 多模块项目](https://maven.apache.org/guides/mini/guide-multiple-modules.html)、[Gradle 多项目构建](https://docs.gradle.org/current/userguide/multi_project_builds.html)与 [uv workspaces](https://docs.astral.sh/uv/concepts/projects/workspaces/)。

### <a id="code-location"></a>选择代码位置

源码 Plugin 可以作为 workspace package 放进 dsh monorepo，通常位于 `packages/<group>/<pkg>/`；也可以放进独立仓库，作为社区 Plugin 单独构建和分发。这里的 workspace 表示同一多包仓库中的成员关系；Agent 当前操作的项目目录通常称为 working directory（工作目录）。

Workspace package 表示工程归属。其中一部分 package 实现可直接加载的 Plugin，另一部分提供类型、公共接口或基础库。实现 Plugin 的 workspace package 加载后遵循与社区 Plugin 相同的 Cordis 生命周期和权限边界；区别在工程和分发：前者随 dsh 统一编译、类型检查、测试和发布，后者通常独立成仓库，打包后通过 `dsh plugin --profile <name> add` 安装。是否随某个 Profile 默认启用，由 Bundle 配置决定。

#### 独立仓库中的 Plugin 与 Bundle

独立开发的 Plugin 从普通 TypeScript / JavaScript module 开始。本地检查完成后，再把代码与 `cordis.patch.yml` 打成声明 `dsh.bundle` 的 package；使用者不需要把 Plugin 合入官方 monorepo。

#### dsh monorepo 中的 workspace package

这类 package 需要 `package.json`、TypeScript project reference、README、约束声明（invariant）和测试。主进程代码与浏览器代码分别编译，普通 package 只能注册到其中一侧。

新增 package 时应先找相同角色的现有实现作为模板。工具可看 `packages/shell/tool-bash`，能力的具体实现可看 `packages/shell/bash-local`，模型适配器可看 `packages/llm/llm-deepseek`，Web 界面 Plugin 可看 `packages/client/ui-workflow-run`。

> 来源：[workspace package 的文件、角色与注册清单](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/cookbook/adding-a-package.md#L7-L43)；[纯类型 workspace package 示例](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/packages/util/brand/README.md#L1-L5)；[Bundle、Profile 与配置层的关系](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/architecture.md#L17-L29)。

### 通过 `--patch` 加载最小 Plugin

仓库外 Plugin 可以通过 `--patch` 把一份临时配置叠加到现有 Profile。官方开发指南把这层配置称为 overlay（覆盖层）：它只在本次启动中追加或覆盖 Plugin 配置，不会改写 Profile 目录中的配置；下次不传 `--patch` 就不再生效。

```yaml
- insert:
    - id: hello
      name: '/absolute/path/to/my-plugin.ts'
```

```sh
dsh web --patch ./cordis.patch.yml
```

先确认最简单的 module 能成功加载，再逐步加入 Config、service、Tool 或 UI。这样导入路径、配置、依赖和业务逻辑不会同时报错。模块形式和生命周期规则见后文的[模块、配置与生命周期](#plugin-runtime)。

> 来源：[仓库外第一个 Plugin 与 overlay 加载路径](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/user/develop/basic/index.md#L7-L64)。

### <a id="verification-and-debugging"></a>实现与验证

每加一层功能，先运行最贴近改动的检查，再扩展到实际启动、浏览器界面和最终发布包。依赖安装成功只表示 package 可解析，不表示 Plugin 已经进入 `ACTIVE`。

#### 配置层合成检查

```sh
dsh --profile web --dump-config
```

`--dump-config` 展示 Bundle、Profile、Harness home 与 `--patch` overlay 合成后的配置树，并报告未匹配的 patch 目标。它不会启动应用、导入 Plugin、求值 `!!js` 或执行 Config schema，因此只用来确认配置项是否插入、覆盖顺序是否符合预期。

#### 实际启动与 Fiber 状态

通过实际的 Loader 和目标 `cordis.yml` 启动 Plugin，确认 module 入口可导入、Config 校验通过、必需 service 存在，并检查 Fiber 状态。`ACTIVE` 表示加载完成；`PENDING` 通常表示必需 service 尚未提供；`FAILED` 表示导入、配置或 `apply()` 抛出异常。

包含浏览器部分的 Plugin 还要在真实 Web 启动方式中确认 Client package、Slot 注册和渲染行为，不能用配置 dump 代替。

#### 单元测试与资源清理

每项注册到 Cordis 注册表中的能力都应有热更新安全测试：加载 Plugin、确认注册出现，再卸载它并确认注册消失。生命周期测试还要等待异步清理真正结束，不能只断言 abort 或 kill 已被调用。

Tool、Provider 和 event policy 的单元测试覆盖错误路径、顺序、取消和重复注册。只 mock LLM、network、clock 等昂贵或非确定边界，尽量使用真实下游实现。

#### 仓库检查与发布包验收

用户能够看到的 Plugin 要通过 Loader 启动实际使用的 `cordis.yml`，确认整套配置按发布后的方式工作。模型、协议或 UI 输出发生变化时，增加不需要真实 API key 的 snapshot；真实 provider 行为再用带 key 的 smoke test 检查。

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

发布前检查 `npm pack` 或其他实际产物，确认其中包含入口、类型声明、patch、浏览器 bundle 和运行文件，而不是只检查源码目录。

> 来源：[配置 dump 的非启动语义](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/apps/cli/src/dump-config.ts#L1-L52)；[配置层与未匹配 patch 的输出](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/apps/cli/reference/README.md#L32-L43)；[Fiber 状态与缺失依赖诊断](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/cordis-tutorial/06-composition-and-hmr.md#L63-L109)；[测试层级、真实入口与 snapshot 要求](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/testing.md#L7-L49)；[仓库内 package 的验证命令](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/cookbook/adding-a-package.md#L109-L118)。

### <a id="packaging-and-installation"></a>打包与安装

#### Bundle 声明与 Profile 清单

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

Profile 清单保存按顺序应用的 Bundle 列表，由 `dsh plugin` 创建和维护。一个 package 没有 `dsh.bundle` 时仍可作为普通依赖安装，但不会自动启用 Plugin。

#### 配置层与覆盖顺序

有效配置依次应用：

1. Profile 列出的 Bundle patches；
2. Profile 的 `cordis.patch.yml`；
3. Harness home 的 `cordis.patch.yml`；
4. 命令行通过 `--patch` 临时加载的 overlay。

后层按 row id 替换完整 `config`。Bundle author 应提供可直接使用的默认值，并允许部署者在后层覆盖；不要依赖深合并补齐遗漏字段。

#### npm、Git 与发布文件

npm package 应在发布前包含运行产物。Git install 获取的是 source；TypeScript package 需要 `prepare` 自行构建，且 pnpm 要求使用者显式 `allowBuilds`。

`allowBuilds` 是执行 package 代码的授权，不受 Agent sandbox 保护。若不希望要求这项授权，可发布带构建产物的 npm package 或 `pnpm pack` tarball。完整权限关系见运行时篇的 [Plugin 与安装脚本](dsh.md#trust-boundaries)。

> 来源：[Bundle/Profile manifest、安装和配置顺序](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/user/develop/basic/publish.md#L9-L128)；[Git build script 与预构建分发](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/user/develop/basic/publish.md#L153-L178)。

### 发布前检查与社区发现

发布前至少确认：

- `package.json`、入口、类型声明和 `dsh.bundle` / `dsh.client` 指向真实发布文件；
- README 给出安装命令、支持的 dsh 版本范围和目标 Profile；
- 主进程权限、网络或子进程行为、安装脚本和 `allowBuilds` 条件写清楚；
- package、许可证、测试和干净 Profile 安装验收一致；
- 仓库添加 `dsh-plugin` topic，源码与文档引用固定到 release tag 或 commit。

GitHub topic、社区目录或市场只负责帮助人找到 Plugin；发布者和使用者仍需自行审查权限与依赖。

## <a id="plugin-runtime"></a>模块、配置与生命周期

### 模块形式与配置

#### 函数式 Plugin 与 Service 类

普通函数式 Plugin 使用具名导出，不提供 default export：

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

提供 Cordis service 的 package 通常默认导出一个 `Service` 子类：

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

不要同时给函数式 Plugin 增加 default export。Loader 会把 default export 当作 Plugin 本体，导致同一 module 上的 `inject`、`Config` 或 `apply` 不再被识别。

#### 配置 Schema 与加载校验

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

#### Plugin 生命周期与热更新

每个 Plugin 实例都由一个 Fiber 管理。Fiber 是它的生命周期范围：等待必需 service、执行 Plugin，并在卸载时撤销这个 Plugin 注册的监听器、工具和其他资源。

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

`ctx.on()`、registry 的 `register()` 和 `ctx.effect()` 都会把清理函数绑定到当前 Fiber。热更新时，Cordis 先卸载旧 Fiber、完成清理，再加载新代码；新代码抛错时 Fiber 进入 `FAILED`，不会自动恢复旧模块。放在 module 顶层的 singleton、没有登记的 timer，或没有等待退出的子进程会绕过这套清理机制。

> 代码落点：[Cordis Fiber 状态与 effect 实现](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/vendor/cordis/src/fiber.ts#L142-L220)；[启动失败与 `FAILED` 状态](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/vendor/cordis/src/fiber.ts#L646-L667)；[Plugin 清理、dispose 与 HMR 语义](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/user/develop/framework/index.md#L7-L131)。

#### Service 依赖与隔离

Service 是一个 Plugin 提供给其他 Plugin 的具名能力。使用方通过 `inject` 声明自己必须依赖哪些 service：

```ts
export const inject = ['tools', 'metrics']

export function apply(ctx: Context): void {
  ctx.metrics.record('loaded', 1)
}
```

必需 service 尚未出现时，使用方保持 `PENDING`；提供方消失时，使用方自动卸载，并在 service 恢复后重新加载。可选 service 不写进 `inject`，而是在使用点通过 `ctx.get(name)` 查询。

同名 service 可以在不同 Cordis group 中隔离。一个 Agent preset 或子树需要自己的 shell、tools 或 policy 时，应使用 isolate realm，而不是给 service 发明新的全局名称。

> 来源：[Service 提供、消费与依赖消失后的行为](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/user/develop/framework/service.md#L7-L110)；[Service isolation](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/user/develop/framework/service.md#L111-L139)。

#### 事件与拦截点

Event 让 Plugin 在不直接依赖彼此的情况下通信。常见模式：

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

Cordis event 与写入 Session 日志的事件不同。`agent/*`、`tools/*` 等 Cordis event 只描述当前运行过程；`turn/*`、`step/*`、`tool/result` 等 Session event 会持久保存，用于恢复和回放。

> 来源：[Event 模式、typed events 与 effect 清理](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/user/develop/framework/events.md#L23-L138)；[运行时扩展点地图](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/architecture.md#L53-L129)。

## <a id="tool-and-providers"></a>工具与可替换能力

### 工具 Plugin

#### 参数、结构化结果与显示方式

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

`execute()` 返回由 `output.schema` 定义的稳定 JSON 值，`output.render()` 再把它转换成模型能看到的内容。id、状态和其他字段应保留为结构化数据，不要藏进自然语言，也不要为了显示一张 UI 卡片而改写原始返回值。

界面如何显示工具结果是另一层逻辑。以后回放仍需要的信息通过 `presentationMeta` 写入持久化结果，再由 `presentCall` / `presentResult` 选择普通文本、终端、diff、搜索或网页卡片。

#### 执行策略与后台任务

| 扩展点 | 用途 |
|---|---|
| `tools/pre-execute` | 可组合的 allow / ask / deny 策略 |
| `ctx.tools.guard()` | 后续 listener 不能撤销的最终拒绝 |
| `tools/execute` | 包裹真实 dispatch，用于 deadline、retry 或 metrics |
| `tools/post-execute` | 改写 value、模型内容或附加上下文 |
| `tools/result` | 观察不可变的最终结果 |

前台工作必须响应 `exec.signal`。一旦工具返回 job id，后续后台任务就不再由这次工具调用负责；应把它注册进 `ctx.jobs`，由 job 自己处理取消、所属 Plugin 卸载和完成状态。

> 来源：[Tool 最小形态与 execute contract](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/cookbook/adding-a-tool.md#L7-L56)；[执行策略、Code Mode 与 UI presentation](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/cookbook/adding-a-tool.md#L57-L94)。

### 可替换能力接口

#### 接口定义、Provider 与使用方

需要替换实现而不改变调用方式时，把能力拆成三个角色：

| 角色 | 负责什么 | shell 示例 |
|---|---|---|
| 接口定义 | 定义稳定接口和请求 / 返回类型 | `dsh-shell` |
| Provider | 提供一种具体实现 | `dsh-bash-local`、`dsh-pwsh-local` |
| 使用方 | 把能力暴露给模型或其他调用者 | `dsh-tool-bash` |

Provider 和使用方都依赖接口定义，但彼此不直接依赖。替换 Provider 时，Tool schema 和调用方式可以保持不变；修改使用方呈现给模型的内容时，也不要求改执行器。

#### 能力实现的 package 拆分

只有角色确实需要独立演进或替换时才拆成多个 package。一个简单 Tool 同时拥有输入校验和执行逻辑并不违规；过早拆分会增加 manifest、project reference、tests 和版本协调成本。

公共接口应满足所有现有使用方，不把某个 Tool、UI 或传输协议的私有字段塞进 service。Provider 负责把调用请求整理成完整参数，并在入口处应用默认值与上限；不要把默认行为零散地藏在执行函数中。

> 来源：[三角色能力设计与 Bash 示例](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/user/develop/practice/index.md#L7-L155)；[仓库中的 capability seam 清单](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/capability-seams.md#L1-L40)。

### 模型适配器

#### 流式协议与错误处理

模型适配器是 `ctx.llm` 的 Provider，负责把某家模型服务的协议转换成 dsh 的统一接口：

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

适配器必须遵守统一的流式输出顺序：usage 出现在 finish 之前，finish 之后不再输出；工具参数以原始 JSON 字符串逐段传递；block index 第一次出现后不再改变；不支持的 `GenerateOptions` 要明确报错。网络或协议本身失败可以抛异常，模型服务在正常响应里返回的失败则用 error / aborted finish 表达。

适配器需要响应 `options.signal`。模型服务要求保留的 response id、signature 等专用状态，只保存为能够完整还原的最小 JSON，并由同一个适配器实例判断能否用于后续请求。

#### 注册、配置与验证

一个适配器可以服务多个 provider 路由，但同一路由不能重复注册。凭据应通过 Config 和 dsh 的凭据接口解析，不在代码中读取自创 key 文件。

实现时应把协议类型、请求序列化、响应解析、流片段转换和 adapter class 分开。检查至少覆盖片段顺序、usage / finish、工具参数、取消、不支持的字段、模型服务报错，以及一次连接真实服务的 smoke test。

> 来源：[LLM adapter 形态和协议义务](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/cookbook/adding-an-llm-adapter.md#L7-L43)；[DeepSeek adapter 的注册实现](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/packages/llm/llm-deepseek/src/index.ts#L240-L276)。

## <a id="protocol-and-ui-plugins"></a>协议与界面 Plugin

### 接入外部协议

#### Agent 控制与 Session 事件

协议 Plugin 把外部客户端接到 `ctx.agents`。它通常负责：

1. 创建或恢复 Agent；
2. 把外部输入交给 `followup()`、`steer()` 或取消接口；
3. 订阅 `session/event`，把已写入 Session 日志的输出转换回外部协议；
4. 在连接关闭时释放自己创建的 Agent，并等待清理完成。

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

不要把 `followup()` 当成“这个 prompt 对应一个结果 Promise”。排队输入、steering 输入和系统注入内容可能在同一段运行时间里共同产生输出；协议若要提供“一次运行的结果”，必须先定义自己从何时观察到何时。

#### ACP 实现案例

`dsh-acp` 是完整案例。它通过 stdio 通信，为连接创建新 Agent，映射权限请求和取消操作，只发送已经写入日志的 assistant message，并在断开连接时清理该连接创建的全部 Session。

ACP package 也说明“协议接入”与“完整界面”不是一回事：推理过程、工具活动、计划、标题和界面呈现仍留在 Session 日志或 Web 界面中，不应为了协议方便全部塞进传输格式。

> 来源：[协议驱动 Plugin 形态](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/cookbook/extension-cookbook.md#L63-L93)；[ACP Plugin 的连接关闭与 Agent / Session 清理](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/packages/acp/acp/src/index.ts#L348-L414)。

### Web 界面 Plugin

#### 浏览器端 package 与界面插槽

Web 界面 Plugin 分成 Node 侧加载入口和浏览器 `/client` 入口。package 通过 `dsh.client` 声明浏览器代码，并在 `apply(ctx)` 中把组件注册到 slot（预留的界面插槽）；普通业务组件不直接获得 `ctx`。

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

一个新的浏览器端 package 还要加入 `tsconfig.client.json`、Web Bundle 的 Cordis 配置和依赖清单。`dsh.client.inject` 只说明浏览器端依赖哪些 package，不决定加载顺序；是否真正启用仍由 Cordis 的 service 依赖决定。

#### 对话节点与历史回放

“对话节点”（Conversation Node）把一组已经写入 Session 日志的事件按顺序归并成稳定状态，再生成带稳定 key 的界面节点：

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

每个相关 event 都要携带稳定业务 id；`match()` 只检查当前 event，不能扫描整段 Session 历史。State 必须能按日志顺序得到同样结果，renderer 只读取最终节点数据。测试同时覆盖完整回放、只有更新事件的日志尾部、向前补找起始事件，以及实时追加与从头回放结果一致。

> 来源：[Web Client package 与 slot 规则](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/packages/client/AGENTS.md#L1-L83)；[Conversation Node 的事件、State 与测试路径](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/cookbook/adding-a-conversation-node.md#L9-L231)。

## <a id="session-data-plugins"></a>会话数据 Plugin

### 扩展 Session 事件类型

模型能看到、或恢复会话时必须重建的事实，都应写入 Session 日志。Plugin 通过 TypeScript 的 declaration merging（声明合并）扩展 `SessionEventMap`，增加自己的事件类型：

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

新 event 要有稳定 id、可序列化数据和明确的回放方式。只有实时观察价值、无需恢复的过程信号才留在 Cordis event；不要把运行中的对象、callback 或仅主进程可用的 handle 写进 Session。

### 持久状态与回放

不要在 Session 日志之外再维护第二份权威状态。用于查询、界面和遥测的状态都从 Session event 计算；需要缓存时，记录自己处理到日志的哪个位置，并能从剩余日志重新构建。

向模型加入新内容时也要先写入 Session event，再由日志生成请求。绕过日志直接修改 prompt，会让恢复、分叉、遥测和界面回放得到彼此不一致的历史。

> 来源：[Session log 与 model-visible invariant](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/architecture.md#L63-L97)；[Session subsystem 的事件类型与存储语义](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/subsystems/session.md#L1-L120)。
