# Lark / Feishu CLI 作为 Agent Tool

本 reference 用 `lark-cli` 说明一个现成 CLI 怎样进入 agent 系统。主线是 executable、tool adapter、AI Skill 与外部授权之间的分工；命令全集仍以对应版本的官方文档和已安装 Lark Skills 为准。

## Lark Tool 的分层

Lark 的一键安装把 CLI 与 Agent Skills 一起交付，但二者承担不同职责。官方 v1.0.90 README 分别列出安装流程、Agent Skills 和 OAuth 登录入口。[lark-cli v1.0.90：安装、Skills 与认证](https://github.com/larksuite/cli/blob/v1.0.90/README.zh.md#L55-L196)

| 层 | Lark 实例 | 提供什么 |
|---|---|---|
| Tool implementation | `lark-cli` 原生可执行文件 | 调用飞书 OpenAPI，处理命令参数、身份、输出和 CLI 风险门禁 |
| Tool adapter | harness 的 shell tool，或包装 `lark-cli` 的 typed tool | 把具体能力暴露给 agent，承担 schema、进程执行、超时和结果转换 |
| AI Skill | `lark-*` 的 `SKILL.md`、references 与可选 scripts | 告诉 agent 何时选哪个命令、怎样处理身份、权限和易错点 |
| Authority | 开放平台应用配置、user/bot identity、OAuth scopes | 决定 CLI 最终能访问或修改哪些飞书资源 |

授权界面中的 `application`、`base`、`calendar`、`docs`、`drive` 等是 scope domain（权限集合），不是 npm 模块或 Skill 安装开关。安装 Skill 只增加说明层；是否存在可执行文件、harness 是否暴露执行能力、当前身份是否获授权，仍需分别确认。

```text
用户目标
   ▼
Agent ──读取 lark-* Skill──提出调用
   ▼
Harness ──policy / approval / cwd / timeout / output handling
   ▼
shell tool 或 typed adapter
   ▼
lark-cli ──user / bot identity + app/OAuth scopes
   ▼
Feishu / Lark OpenAPI
```

经通用 shell tool 调 CLI 时，Skill 承担较多命令路由知识；包装成 typed tool 时，常用操作可以有更窄的 schema 和更明确的风险标记。两种接法都以 `lark-cli` 为执行实现，整个 runtime 与 agent-as-tool 关系见 `harness` skill。

## 一键安装

```bash
npx @larksuite/cli@latest install
```

以 v1.0.90 为实现快照，交互式向导依次检查/升级全局 npm 包、安装 Lark Skills、配置应用并发起授权；非交互环境只完成 CLI 与 Skills 安装并打印后续配置提示。[install-wizard.js v1.0.90](https://github.com/larksuite/cli/blob/v1.0.90/scripts/install-wizard.js#L223-L356)

全局 npm 包的 postinstall 会下载对应平台 archive、校验 SHA-256、解压并把原生 binary 写进包内 `bin/`，临时目录在结束时清理。[install.js v1.0.90](https://github.com/larksuite/cli/blob/v1.0.90/scripts/install.js#L212-L255)

| 路径 | 作用 |
|---|---|
| npm cache | `npx` 包装器和下载缓存；具体目录由 npm 配置决定，不是最终命令入口 |
| `<npm-prefix>/lib/node_modules/@larksuite/cli/` | Unix-like 系统常见的全局 npm 包位置；实际前缀由 `npm prefix -g` 决定 |
| `<npm-prefix>/bin/lark-cli` | npm 创建的命令入口，通常指向包内 launcher |
| `~/.agents/skills/lark-*` | `skills` CLI 使用的规范副本 |
| `$XDG_STATE_HOME/skills/.skill-lock.json`，未设置时 `~/.agents/.skill-lock.json` | Skills 的来源、摘要和安装/更新时间 |
| Agent 自有 skills 目录 | 需要专用目录的客户端可链接到规范副本；通用客户端直接读取 `.agents/skills` |

`skills@1.5.23` 把全局规范副本放在 home 下的 `.agents/skills`，lock 文件路径受 `XDG_STATE_HOME` 覆盖。[installer.ts v1.5.23：canonical 路径](https://github.com/vercel-labs/skills/blob/v1.5.23/src/installer.ts#L90-L137) [skill-lock.ts v1.5.23](https://github.com/vercel-labs/skills/blob/v1.5.23/src/skill-lock.ts#L58-L68)

当前环境的 global npm 位置以 `npm prefix -g` 和 `command -v lark-cli` 的实测输出为准。

## Skills 的 Agent 探测

`skills@1.5.23` 会遍历已知 Agent 定义并调用各自的 `detectInstalled()`，然后保留返回 true 的类型。[agents.ts v1.5.23：探测循环](https://github.com/vercel-labs/skills/blob/v1.5.23/src/agents.ts#L785-L793)

常见 Agent 的判断主要是配置目录是否存在：

| Agent | v1.5.23 默认信号 |
|---|---|
| Claude Code | `$CLAUDE_CONFIG_DIR`，未设置时 `~/.claude` |
| Codex | `$CODEX_HOME`，未设置时 `~/.codex`；另检查 `/etc/codex` |
| Grok Build | `$GROK_HOME`，未设置时 `~/.grok` |
| GitHub Copilot | `~/.copilot` |
| Kimi Code CLI | `~/.kimi-code` 或 `~/.kimi` |

这些条件见 [home 覆盖变量](https://github.com/vercel-labs/skills/blob/v1.5.23/src/agents.ts#L6-L14)、[Claude 与 Codex](https://github.com/vercel-labs/skills/blob/v1.5.23/src/agents.ts#L145-L218) 和 [Copilot、Grok、Kimi](https://github.com/vercel-labs/skills/blob/v1.5.23/src/agents.ts#L343-L438)。它们属于存在性探测，不是 binary、版本或登录态健康检查；残留空目录也会命中。

带 `-y` 的自动路径会在已探测类型之外追加所有被定义为 universal 的 Agent；universal 的判据是项目 skills 目录为 `.agents/skills`。[add.ts v1.5.23：自动目标](https://github.com/vercel-labs/skills/blob/v1.5.23/src/add.ts#L323-L338) [agents.ts v1.5.23：universal 判据](https://github.com/vercel-labs/skills/blob/v1.5.23/src/agents.ts#L827-L865)

全局安装时，universal Agent 直接使用 `~/.agents/skills`，不会再创建其专用全局链接；非 universal Agent 使用自己的目录，链接失败时安装器回退为复制。[installer.ts v1.5.23](https://github.com/vercel-labs/skills/blob/v1.5.23/src/installer.ts#L790-L823)

因此某个 Agent 出现在安装摘要里，只能说明目录探测或 universal 规则命中；不能据此断言对应程序仍能运行。

## 身份与权限

Lark CLI 把应用配置、OAuth 登录、scope 和运行时身份分开。v1.0.90 提供按 domain、具体 scope 或推荐集合登录，也支持显式 `--as user` / `--as bot`。[lark-cli v1.0.90：认证与身份](https://github.com/larksuite/cli/blob/v1.0.90/README.zh.md#L165-L196)

Tool adapter 不静默切换身份或扩大 scope。缺少权限时，把缺失 scope、身份和可操作提示作为错误返回给 harness，由上层决定是否向用户请求授权。

## 输出与副作用

v1.0.90 的 JSON 成功 envelope 写入 stdout、退出码为 0，并以 `ok: true` 表示；错误写入 stderr、退出码非 0，顶层 `code` 不能用作成功判断。[lark-cli v1.0.90：JSON 输出契约](https://github.com/larksuite/cli/blob/v1.0.90/README.zh.md#L233-L267)

自动化 wrapper 同时保留 stdout、stderr 与退出码。写操作超时后先查询真实状态再决定是否重试；第一次请求可能已经成功，直接重放会造成重复创建。能 dry-run 的操作把预览和提交拆成不同阶段，高风险确认回到 harness 临近执行时处理。

## 诊断

诊断时分别核对 executable、Skill discovery、应用配置、identity 与 scopes，不从其中一层推断另一层：

```bash
command -v lark-cli
lark-cli --version
npm prefix -g
npx -y skills ls -g
```

- executable 缺失或版本错，处理 CLI 安装。
- `lark-*` 不可发现，检查规范副本、软链接和目标 harness 的 discovery 规则。
- CLI 能运行但资源为空或权限报错，检查实际 identity、应用权限与用户授权。

“Skill 能被看见”不证明 CLI 已安装；“CLI 能运行”也不证明当前身份有权访问目标资源。
