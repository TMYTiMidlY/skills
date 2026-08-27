# Agent Skills 官方规范、目录与加载差异

Anthropic「Agent Skills」的可移植 skill bundle 格式：一个 skill 长什么样、官方 frontmatter 有哪些字段、`scripts/` / `references/` / `assets/` 各干什么，以及不同 harness 在规范之外怎样扩展加载行为。评估 skill 是否可跨工具迁移，或排查“为什么这个 skill 在 A 工具能用、B 工具不认”时看这里。

## 标准目录树

一个 skill bundle 的**唯一硬要求**是 `SKILL.md`（带 YAML frontmatter：`name` + `description`）；其余子目录都是**约定、非 loader 强制**。Anthropic 的 Agent Skills 开放规范（[agentskills.io/specification](https://agentskills.io/specification)，2025-12 发布，也镜像在 `anthropics/skills:spec/agent-skills-spec.md`）给的标准树：

```
skill-name/
├── SKILL.md          # 必需：元数据 + 指令
├── scripts/          # 可选：可执行代码
├── references/       # 可选：按需加载的文档
├── assets/           # 可选：模板 / 静态资源
└── ...               # 其它文件 / 目录随意
```

## 官方 frontmatter 只有 6 个字段

Agent Skills 开放规范为 `SKILL.md` 定义 6 个字段：

| 字段 | 必填 | 说明 |
|---|---|---|
| `name` | 是 | ≤64 字符，只用小写字母、数字和连字符，并与所在目录同名 |
| `description` | 是 | ≤1024 字符 |
| `license` | 否 | 许可证名或指向随附许可证文件的路径 |
| `compatibility` | 否 | ≤500 字符，描述环境或产品要求 |
| `metadata` | 否 | string→string map；承载规范外元数据时最可移植 |
| `allowed-tools` | 否 | 实验性字段，空格分隔预先允许的工具 |

规范没有表达 skill 层级的字段：没有 `parent`、`children`、`category` 或 `has-sub-skill`。它还建议让文件引用距 `SKILL.md` 不超过一层，避免深层 reference 链。

## 三个可选目录：分野在「进不进上下文窗口」

- **`scripts/`** — agent 用 bash **执行**的代码；只有**运行结果**回流进上下文，脚本本身不占 context。适合确定性、重复性的活（解析 / 转换 / 校验），省 token 也更可靠。
- **`references/`** — agent **按需读进上下文**的文档（详细 API、schema、workflow）。SKILL.md 点名 `references/foo.md`，用到才加载——渐进式披露（progressive disclosure：细节只在需要时才喂进上下文）的主力。
- **`assets/`** — **静态资源**：模板、图片、数据文件、boilerplate。被**引用 / 拷进产物**用，但**不整体读进上下文**。这是它与 `references/` 的关键区别：references 是「给模型读的」，assets 是「给产物用的」。

## 是 `assets/`（复数），不是 `asset/`（单数）

官方规范、[platform.claude.com Agent Skills 概览](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)、`anthropics/skills` 仓库里的真实 skill（如 `skill-creator` 同时用齐 `scripts/` `references/` `assets/`）**一律小写复数**；`asset/` 单数在官方源里**零出现**。`references/` 同理复数。命名对齐主要为可发现性 + 跟生态一致。

## 坑 / 边界

- 子目录名是**语义约定**、不是 loader 解析项——只有 `SKILL.md` frontmatter 是硬格式。名字写错不会「加载不了」，但会丢可发现性、跟生态不一致。
- 反例：`anthropics/skills` 里 `mcp-builder` 用了 `reference/`（单数），属仓库内个别偏差、**不是第二套约定**——规范与其余所有来源都用复数。
- 小 skill 可把 `reference.md` / `forms.md` 直接平铺在根目录（如官方 `pdf` skill），不建 `references/`；规范明说允许「任意附加文件 / 目录」。

## 分组与层级在 skill 目录之外

官方规范不定义“父 skill / 子 skill”。官方与社区生态常见的分组方式都不改变单个 skill bundle 的平铺结构：

- **平铺目录列表**：一个 skill 对应一个含 `SKILL.md` 的目录，分类只写在 README 等索引里；`anthropics/skills`、`obra/superpowers` 都采用这种结构。
- **插件命名空间**：`plugins/<plugin>/skills/<skill>/`，安装或调用时由插件名提供命名空间；skill 本身仍是独立 bundle。
- **Monorepo 嵌套发现**：仓库子目录各自放 `.claude/skills/` 等发现目录，名称可带目录限定；嵌套的是项目目录，不是 skill 套 skill。

## Harness 的私有扩展

各 harness 可以识别官方 6 字段之外的 frontmatter，但这些字段不自动具备跨工具可移植性：

- **Claude Code**：识别 `argument-hint`、`disable-model-invocation`、`user-invocable`、`model`、`context`、`agent`、`hooks` 等扩展，但没有父子 skill 层级字段。
- **Kimi Code**：识别 `has-sub-skill: true`（也接受 camelCase `hasSubSkill`，并可放在 `metadata` 下）。父 skill 开启后，扫描器才会递归发现嵌套的子 `SKILL.md`；子技能以点分名注册，并带 `metadata.isSubSkill = true`。

### `has-sub-skill` 是 Kimi Code 私有机制

Kimi Code 的实现位于 `packages/agent-core/src/skill/scanner.ts`：`hasSubSkillEnabled()` 控制是否下钻目录。2026-07 用 Sourcegraph 全网检索 `has-sub-skill` 时，该字符串只出现在 MoonshotAI/kimi-code，Anthropic 官方仓库、Agent Skills 规范和核对过的主流社区合集均无匹配。

因此：

- 使用 `has-sub-skill` 父 bundle 后，子技能只保证能被 Kimi Code 的加载器发现；遵循开放规范但不递归扫描的 harness 会看不到它们。
- 想跨工具通用时保持平铺，把分类放在 README、插件命名空间或项目目录层。
- 只面向 Kimi Code 时可以使用层级，但应明确这是宿主绑定，而非 Agent Skills 社区规范。

## 来源

- [agentskills.io/specification](https://agentskills.io/specification) — Anthropic Agent Skills 开放标准（2025-12），目录树 + 各目录定义原文。
- [platform.claude.com — Agent Skills 概览](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview) — 三层内容模型、`references/` 命名。
- [Anthropic Engineering — Equipping agents for the real world with Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills) — 设计动机（bundle 附加文件、脚本即工具）。
- [anthropics/skills](https://github.com/anthropics/skills) — 官方参考仓库；`skill-creator` 三目录齐全（`scripts/` `references/` `assets/`）。
- [Claude Code skills 文档](https://code.claude.com/docs/en/skills) — Claude Code 私有 frontmatter 与加载行为。
- [Kimi Code skill scanner](https://github.com/MoonshotAI/kimi-code/blob/main/packages/agent-core/src/skill/scanner.ts) — `has-sub-skill`、递归扫描和子 skill 注册实现。
- [Sourcegraph](https://sourcegraph.com/search?q=context%3Aglobal+has-sub-skill&patternType=keyword) — `context:global has-sub-skill` 全网检索（2026-07-20 执行）。
- 社区结构核对：[`obra/superpowers`](https://github.com/obra/superpowers)、[`wshobson/agents`](https://github.com/wshobson/agents)。
