# Agent Skills 规范与各 harness 的 skills 加载对照

skills 的"标准格式"到底规定了什么、各家 harness（Claude Code / Kimi Code 等）在规范之外加了哪些私有扩展、跨工具迁移时什么结构最兼容——评估某个 skill 写法是否可移植、或排查"为什么这个 skill 在 A 工具能用、B 工具不认"时看这里。

调研时间：2026-07。主要依据官方规范原文与全网代码搜索，来源列在文末。

## 官方规范只有 6 个 frontmatter 字段

Agent Skills 开放规范（agentskills.io，与 anthropics/skills 仓库的 `/spec` 同步）为 SKILL.md 定义的字段**只有这 6 个**：

| 字段 | 必填 | 说明 |
|---|---|---|
| `name` | 是 | ≤64 字符，小写字母/数字/连字符，必须与所在目录同名 |
| `description` | 是 | ≤1024 字符 |
| `license` | 否 | |
| `compatibility` | 否 | ≤500 字符，环境要求 |
| `metadata` | 否 | 任意 string→string map，规范外属性唯一合法的容身之处 |
| `allowed-tools` | 否 | 实验性，空格分隔 |

规范里**没有任何表达层级/嵌套/分组的字段**——没有 `parent`、`children`、`category`，也没有 `has-sub-skill`。规范甚至明确建议避免深层嵌套："Keep file references one level deep from SKILL.md. Avoid deeply nested reference chains."

## 官方生态的"分组"全是平铺式的

规范没有层级机制，社区实际用的分组方式也都在技能目录之外：

- **平铺目录列表**：一个 skill = 一个含 SKILL.md 的目录，平铺在 `skills/` 下。anthropics/skills（17 个全平铺）、obra/superpowers 均如此；"分类"只存在于 README 散文里。
- **插件命名空间**：`plugins/<plugin>/skills/<skill>/`，调用形如 `/plugin:skill`。wshobson/agents（94 插件 / 175 技能）走这条路；anthropics/skills 也以 plugin 为安装单元。
- **Claude Code monorepo 发现**：仓库子目录里嵌套的 `.claude/skills/` 按需发现，名字带目录限定（`apps/web:deploy`）。这是**仓库目录**嵌套，不是技能套技能。

## 各 harness 的私有扩展字段

规范之外，各家自己加字段，互不通用：

- **Claude Code**：`when_to_use`、`argument-hint`、`arguments`、`disable-model-invocation`、`user-invocable`、`disallowed-tools`、`model`、`effort`、`context`、`agent`、`hooks`、`paths`、`shell` 等——但同样**没有**任何层级字段。
- **Kimi Code（MoonshotAI）**：`has-sub-skill: true`（源码里也接受 camelCase `hasSubSkill`，可嵌在 `metadata` 下）。父 skill 标了它，扫描器才会下钻该目录发现嵌套的子 SKILL.md；子技能以**点分名**注册（`parent.child`）并打 `metadata.isSubSkill = true`。实现见 `packages/agent-core/src/skill/scanner.ts`（`hasSubSkillEnabled()` 才递归）；另内置一组 `sub-skill.*` 技能（review/consolidate 等）专门做这种层级重组。

## `has-sub-skill` 是 Kimi Code 私有扩展，不是社区规范

2026-07 用 Sourcegraph 全网代码搜索（`context:global has-sub-skill`）：该字符串只出现在 **MoonshotAI/kimi-code** 一个项目中（约 16 个文件）。Anthropic 各仓库、agentskills.io、主流社区 skill 合集均无匹配。

**可移植性结论**：

- 合并成 `has-sub-skill` 父 bundle 后，子技能只在 Kimi Code 的加载器下可见；按官方规范实现的加载器（Claude Code 等）不会下钻，子技能会"消失"。
- 想跨工具通用 → 保持平铺；分组交给 README 分类或 plugin 层。
- 只在 Kimi Code 里用 → 层级可用，但属于绑定单一 harness 的写法。

## 来源

- 官方规范：https://agentskills.io/specification （镜像：https://github.com/anthropics/skills 的 `/spec`）
- Claude Code skills 文档：https://code.claude.com/docs/en/skills
- Kimi Code 扫描器实现：https://github.com/MoonshotAI/kimi-code （`packages/agent-core/src/skill/scanner.ts`）
- 全网检索：Sourcegraph `context:global has-sub-skill count:all`（2026-07-20 执行）
- 社区合集核对：anthropics/skills、obra/superpowers、wshobson/agents
