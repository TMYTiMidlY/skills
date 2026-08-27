# Lark / Feishu CLI 作为 Agent Tool

`lark-cli` 是飞书/Lark 官方命令行工具，提供面向人和 Agent 的飞书开放平台操作入口。Agent 可以通过通用 shell tool 调用它，也可以由 adapter 包装成参数更窄的 typed tool。`lark-*` Skills 提供按业务域组织的命令路由、身份权限规则和操作流程。

本 reference 介绍 CLI 的能力、身份模型、一键安装、Skills 安装与 Agent 发现。日历、消息、文档等具体业务流程直接进入对应官方 Skill。

## 飞书 CLI 能做什么

`lark-cli` 覆盖即时通讯、文档、云空间、多维表格、电子表格、幻灯片、日历、邮箱、任务、审批、会议、知识库、考勤、OKR 和妙搭应用等业务域。[lark-cli v1.0.90：功能](https://github.com/larksuite/cli/blob/v1.0.90/README.zh.md#L32-L53)

| 能力域 | 典型操作 |
|---|---|
| 消息与组织 | 发送和搜索消息、管理群聊、查询联系人、处理邮箱 |
| 内容与存储 | 创建和编辑文档、管理云空间文件、原生 Markdown、知识库和画板 |
| 结构化数据 | 操作多维表格、电子表格、字段、记录、公式、图表和视图 |
| 协作流程 | 管理日程、会议室、任务、审批、OKR 和考勤记录 |
| 会议 | 查询视频会议、妙记、会议纪要、逐字稿和录制产物 |
| 应用平台 | 管理开放平台应用能力，开发和部署妙搭/Spark 应用 |

CLI 提供三层命令入口：[lark-cli v1.0.90：命令层级](https://github.com/larksuite/cli/blob/v1.0.90/README.zh.md#L199-L230)

- **快捷命令**：以 `+` 开头，为常见任务提供面向人和 Agent 的参数与默认值。
- **API 命令**：与精选飞书 OpenAPI 端点一一对应。
- **通用 API 调用**：通过 HTTP method 与 OpenAPI path 调用其他开放平台端点。

## Agent 如何调用飞书 CLI

调用链把业务知识、运行控制、CLI 执行和飞书资源连在一起：

```text
用户目标
   ▼
Agent 读取对应 lark-* Skill
   ▼
Harness 暴露 shell tool 或 typed adapter
   ▼
lark-cli 选择身份并调用飞书 OpenAPI
   ▼
飞书/Lark 资源
```

通用 shell tool 直接执行 `lark-cli` 命令，适合复用完整 CLI 能力。Typed adapter 为高频操作定义固定 schema，并处理进程退出码、stdout/stderr、timeout 和结构化结果。单个 adapter 的契约设计见 `tool` skill；整个运行时怎样装载 Skill、注册工具和管理会话见 `harness` skill。

`lark-cli --format json` 的成功 envelope 使用 `ok: true`，错误 envelope 写入 stderr 并配合非零退出码。完整字段和判断规则见 [`lark-shared` 的 JSON 输出契约](https://github.com/larksuite/cli/blob/84f9414311ee315671ecceb7bd964e87874bf96c/skills/lark-shared/references/lark-shared-output-contract.md#L1-L17)。

## 用户态、Bot 态与授权

CLI 支持 user 与 bot 两种身份，调用时可显式使用 `--as user` 或 `--as bot`：

| 身份 | 代表对象 | 凭据与权限 | 典型资源 |
|---|---|---|---|
| user | 完成 OAuth 登录的飞书用户 | 开放平台应用已开通相关 scope，并由用户完成授权 | 用户自己的日历、云空间、邮箱及可见协作资源 |
| bot | 当前绑定的开放平台应用 | 应用配置与 bot scope | 机器人自己的资源，以及平台授予应用身份的能力 |

`lark-cli auth login` 支持按 domain、具体 scope 或推荐集合申请用户授权；`auth status`、`auth check` 和 `auth scopes` 用于核对当前状态。[lark-cli v1.0.90：认证命令](https://github.com/larksuite/cli/blob/v1.0.90/README.zh.md#L165-L196)

授权界面的 `application`、`base`、`calendar`、`docs`、`drive` 等名称用于组织 OAuth scope 集合。Skills 的安装由 `skills` CLI 管理，授权由 `lark-cli auth` 管理。

身份自动选择、user/bot 资源边界、增量授权和缺少 scope 的处理见 [`lark-shared` 的身份与权限说明](https://github.com/larksuite/cli/blob/84f9414311ee315671ecceb7bd964e87874bf96c/skills/lark-shared/references/lark-shared-identity-and-permissions.md#L23-L90)。

## 一键安装

```bash
npx @larksuite/cli@latest install
```

以 v1.0.90 为实现快照，一键安装按下面的顺序工作：[install-wizard.js v1.0.90](https://github.com/larksuite/cli/blob/v1.0.90/scripts/install-wizard.js#L223-L356)

### npm 包与 CLI

`npx` 下载并运行 `@larksuite/cli` 提供的安装入口。安装程序读取 npm registry 的最新版本，并在全局包缺失或版本较旧时执行：

```bash
npm install -g @larksuite/cli
```

全局 npm 包的 `postinstall` 下载当前操作系统和 CPU 架构对应的 `lark-cli` archive，校验 SHA-256，解压到包内 `bin/` 并设置执行权限。[install.js v1.0.90](https://github.com/larksuite/cli/blob/v1.0.90/scripts/install.js#L212-L255)

### AI Skills

安装程序先读取全局 Skills 清单：

```bash
npx -y skills ls -g
```

需要安装时，安装程序调用生产 Skills 源：

```bash
npx -y skills add https://open.feishu.cn/lark-cli/skills/regular -y -g
```

生产源不可用时使用 GitHub 仓库来源：

```bash
npx -y skills add larksuite/cli -y -g
```

`-g` 表示个人级全局安装，`-y` 表示使用自动选择并跳过交互确认。v1.0.90 的具体命令见 [install-wizard.js：Skills 安装](https://github.com/larksuite/cli/blob/v1.0.90/scripts/install-wizard.js#L247-L278)。

### 应用配置与用户授权

交互式终端继续执行应用配置和用户授权：

```text
lark-cli config init --new
lark-cli auth login
```

非交互环境完成 CLI 与 Skills 安装后输出这两个后续入口。配置应用和 OAuth 的完整流程由 `lark-shared` Skill 维护。

### 文件系统布局

| 路径 | 内容 |
|---|---|
| npm cache | `npx` 下载的安装入口和依赖缓存，具体目录由 npm 配置决定 |
| `<npm-prefix>/lib/node_modules/@larksuite/cli/` | Unix-like 系统常见的全局 npm 包位置 |
| `<npm-prefix>/bin/lark-cli` | npm 创建的命令入口 |
| `~/.agents/skills/lark-*` | `skills` CLI 写入的规范 Skills 副本 |
| `$XDG_STATE_HOME/skills/.skill-lock.json`，未设置时 `~/.agents/.skill-lock.json` | Skills 来源、摘要和安装/更新时间 |
| Agent 自有 skills 目录 | 需要专用目录的客户端使用指向规范副本的链接 |

全局规范目录与 lock 路径见 [`skills@1.5.23` 的 installer](https://github.com/vercel-labs/skills/blob/v1.5.23/src/installer.ts#L90-L137) 和 [skill-lock](https://github.com/vercel-labs/skills/blob/v1.5.23/src/skill-lock.ts#L58-L68)。当前环境的 npm 安装位置通过 `npm prefix -g` 与 `command -v lark-cli` 核对。

## Skills 安装与 Agent 发现

`skills@1.5.23` 遍历已知 Agent 定义并调用各自的 `detectInstalled()`，再把命中的 Agent 交给安装流程。[agents.ts v1.5.23：探测循环](https://github.com/vercel-labs/skills/blob/v1.5.23/src/agents.ts#L785-L793)

| Agent | v1.5.23 使用的发现信号 |
|---|---|
| Claude Code | `$CLAUDE_CONFIG_DIR`，未设置时 `~/.claude` |
| Codex | `$CODEX_HOME`，未设置时 `~/.codex`；同时检查 `/etc/codex` |
| Grok Build | `$GROK_HOME`，未设置时 `~/.grok` |
| GitHub Copilot | `~/.copilot` |
| Kimi Code CLI | `~/.kimi-code` 或 `~/.kimi` |

目录条件见 [home 覆盖变量](https://github.com/vercel-labs/skills/blob/v1.5.23/src/agents.ts#L6-L14)、[Claude 与 Codex](https://github.com/vercel-labs/skills/blob/v1.5.23/src/agents.ts#L145-L218) 和 [Copilot、Grok、Kimi](https://github.com/vercel-labs/skills/blob/v1.5.23/src/agents.ts#L343-L438)。这些信号描述配置目录的存在状态；程序版本和登录状态通过各自 CLI 命令继续核对。

带 `-y` 的自动安装会加入所有被定义为 universal 的 Agent；universal Agent 使用 `.agents/skills` 作为项目级 Skills 目录。[add.ts v1.5.23：自动目标](https://github.com/vercel-labs/skills/blob/v1.5.23/src/add.ts#L323-L338) [agents.ts v1.5.23：universal Agent](https://github.com/vercel-labs/skills/blob/v1.5.23/src/agents.ts#L827-L865)

全局安装把规范副本写入 `~/.agents/skills`。Universal Agent 直接读取该目录；其他已发现 Agent 使用自己的 Skills 目录，symlink 不可用时安装器写入一份副本。[installer.ts v1.5.23：写入与链接](https://github.com/vercel-labs/skills/blob/v1.5.23/src/installer.ts#L790-L823)

## 按业务进入官方 Lark Skills

具体命令、参数、权限和写入流程由对应 `lark-*` Skill 维护。下面链接固定到官方仓库 commit `84f9414311ee315671ecceb7bd964e87874bf96c`：

| 主题 | 官方 Skill |
|---|---|
| 应用配置、身份、授权、输出契约与安全规则 | [`lark-shared`](https://github.com/larksuite/cli/blob/84f9414311ee315671ecceb7bd964e87874bf96c/skills/lark-shared/SKILL.md#L1-L40) |
| 日历、忙闲、会议室与参会人 | [`lark-calendar`](https://github.com/larksuite/cli/blob/84f9414311ee315671ecceb7bd964e87874bf96c/skills/lark-calendar/SKILL.md#L1-L30) |
| 消息、群聊、卡片与聊天文件 | [`lark-im`](https://github.com/larksuite/cli/blob/84f9414311ee315671ecceb7bd964e87874bf96c/skills/lark-im/SKILL.md#L1-L30) |
| 在线文档正文 | [`lark-doc`](https://github.com/larksuite/cli/blob/84f9414311ee315671ecceb7bd964e87874bf96c/skills/lark-doc/SKILL.md#L1-L30) |
| 云空间文件、评论、版本与权限 | [`lark-drive`](https://github.com/larksuite/cli/blob/84f9414311ee315671ecceb7bd964e87874bf96c/skills/lark-drive/SKILL.md#L1-L30) |
| 原生 Markdown 文件 | [`lark-markdown`](https://github.com/larksuite/cli/blob/84f9414311ee315671ecceb7bd964e87874bf96c/skills/lark-markdown/SKILL.md#L1-L30) |
| 多维表格与电子表格 | [`lark-base`](https://github.com/larksuite/cli/blob/84f9414311ee315671ecceb7bd964e87874bf96c/skills/lark-base/SKILL.md#L1-L30)、[`lark-sheets`](https://github.com/larksuite/cli/blob/84f9414311ee315671ecceb7bd964e87874bf96c/skills/lark-sheets/SKILL.md#L1-L30) |
| 任务、审批与 OKR | [`lark-task`](https://github.com/larksuite/cli/blob/84f9414311ee315671ecceb7bd964e87874bf96c/skills/lark-task/SKILL.md#L1-L30)、[`lark-approval`](https://github.com/larksuite/cli/blob/84f9414311ee315671ecceb7bd964e87874bf96c/skills/lark-approval/SKILL.md#L1-L30)、[`lark-okr`](https://github.com/larksuite/cli/blob/84f9414311ee315671ecceb7bd964e87874bf96c/skills/lark-okr/SKILL.md#L1-L30) |
| 邮箱 | [`lark-mail`](https://github.com/larksuite/cli/blob/84f9414311ee315671ecceb7bd964e87874bf96c/skills/lark-mail/SKILL.md#L1-L30) |
| 视频会议、妙记、会议纪要与逐字稿 | [`lark-meeting`](https://github.com/larksuite/cli/blob/84f9414311ee315671ecceb7bd964e87874bf96c/skills/lark-meeting/SKILL.md#L1-L30) |
| 知识库与画板 | [`lark-wiki`](https://github.com/larksuite/cli/blob/84f9414311ee315671ecceb7bd964e87874bf96c/skills/lark-wiki/SKILL.md#L1-L30)、[`lark-whiteboard`](https://github.com/larksuite/cli/blob/84f9414311ee315671ecceb7bd964e87874bf96c/skills/lark-whiteboard/SKILL.md#L1-L30) |
| 妙搭/Spark 应用开发与部署 | [`lark-apps`](https://github.com/larksuite/cli/blob/84f9414311ee315671ecceb7bd964e87874bf96c/skills/lark-apps/SKILL.md#L1-L30) |

[官方 Skills 目录](https://github.com/larksuite/cli/tree/84f9414311ee315671ecceb7bd964e87874bf96c/skills)提供其余业务域和组合工作流。

## 诊断入口

```bash
command -v lark-cli
lark-cli --version
npm prefix -g
npx -y skills ls -g
```

- executable 和版本信息来自前两条命令。
- npm global prefix 来自 `npm prefix -g`。
- Skills 规范副本、来源和 Agent 发现结果来自 `skills ls -g`。
- 应用配置、identity 与 scopes 由 `lark-shared` Skill 的诊断流程继续核对。
