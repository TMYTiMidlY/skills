---
name: manage-skills
description: 安装、卸载、创建、拆分、重命名、迁移、审查或维护本地 skills 时使用；关注 skill 边界、触发描述、跨 skill 引用规范、渐进式披露三层结构（description → SKILL.md → references），以及个人配置与 skill 正文分离。
---

# Manage Skills

## 安装 / 卸载 skill

前提：仓库已克隆到 `~/skills`。

**安装 = 软链到 `.agents/skills/`**（`~/` 全局或 `<project>/` 项目级皆可）。skill 在仓库里分三处，按实际位置链：

| 位置 | 含义 | 源路径 |
|---|---|---|
| `skills/.curated/` | 原创（`MIT TiMidlY`） | `~/skills/skills/.curated/<name>` |
| `skills/` | 嫁接（已适配的外部 skill） | `~/skills/skills/<name>` |
| `skills/.experimental/` | 实验（未适配） | `~/skills/skills/.experimental/<name>` |

```bash
mkdir -p <target>/.agents/skills && ln -s <源路径> <target>/.agents/skills/
```

Claude Code / Cursor 等工具只需对 `.agents/skills/` 做一次整目录软链（README 有具体表），不用逐 skill 重链。

**卸载 = `trash-put` 软链**。skill 本体还在仓库里，其他项目照常可用：

```bash
trash-put <target>/.agents/skills/<name>
```

**重构后死链排查**：skill 重命名 / 换目录（比如迁进 `.curated/`）会让旧 symlink 断。批量找断链 → `trash-put` 掉 → 按新路径重链：

```bash
find <target>/.agents/skills -maxdepth 1 -type l ! -exec test -e {} \; -print
```

## 跨 skill 引用

不要在 skill 正文里写依赖本机目录结构的跨 skill 文件路径。用户安装路径、目录名、打包方式都可能不同，硬编码容易失效。需要提示另一个 skill 的能力时，只写 skill 名加能力边界。

同一 skill 内部引用自己的 `references/`、`assets/`、`scripts/` 用相对路径。

## 拆分与迁移

- 短小高频的规则直接放 `SKILL.md`；长流程、低频细节、可独立维护的主题放 `references/`。
- 迁内容时先确认新位置覆盖完整原文，再删旧正文；别留重复。
- 重命名 skill 后，同步更新 frontmatter `name`、标题、描述和其他 skill 里的纯文本提示。

## 审查现有 skills

用户让"审查 / 检查所有 skill 是否合规"时按本节办。**只审不改**——列出发现交给用户，明确同意后才动手改。

检查项：

- **引用状态**：
  - 同 skill 内引用（`references/`、`assets/`、`scripts/`）都用相对路径，不写绝对或 `~/...`；且目标真实存在（grep 验证）。
  - 跨 skill 不给任何文件路径，只写 skill 名加能力边界。
- **渐进式披露三层完整、分工清晰**：`frontmatter description` → `SKILL.md` → `references/*.md`。
  - description：只写"何时触发 + 核心思路一句话"。
  - SKILL.md：短规则 + 各主题入口 + 子文档索引；不堆长流程与整段命令。
  - references/：单主题一文件，长流程 / 踩坑 / 模板。
  - 常见病：SKILL.md 堆满命令（该下放）；references 存在但 SKILL.md 没索引（找不到入口）；description 太笼统或太具体。
  - 判定：SKILL.md 读完应当知道"能做什么、哪个 reference 讲什么"，**不应该读完就能完成具体任务**——那说明 references 层缺位。
- **个人配置不入 skill 正文**：凭据 / 域名 / 服务器地址 / 个人样例文件名都不写进 skill 正文。正文只写变量名、占位符和读取位置，真实值放 `~/.env` 或个人笔记。
- **不绑定特定 AI 工具的具体工具名**：skill 正文不写 `AskUserQuestion`、`TodoWrite`、`WebFetch`、`Task` 这类特定宿主（Claude Code / Codex / Cursor / Trae 等）独有的工具名。同一能力在不同宿主里名字不同，硬编码会让 skill 在其它宿主跑不了。改写成能力描述："向用户提问的工具"、"任务清单工具"、"抓网页的工具"，由模型按当前环境自己挑。只有当 skill 明确只服务单一宿主、且在 description 里讲清楚时才可以保留具体名字。
- **README 与 skill 实际状态同步**：README 表格条目的名称 / 来源 / 说明要和 skill 自身的 frontmatter `description` 口径一致；合并 / 拆分 / 重命名 / 删除 skill 后，README 不能留 stale 条目；外部索引（如 `grafted-skills.json`）里的 `path` 要和实际目录一致。
- **`.` 开头子目录内的 skill 名不能与主目录或其他 `.` 目录内的 skill 同名**：按 skill name 加载时会歧义，必须全局唯一。
- **其他结构性检查**：frontmatter `name` 与目录名一致；弃用段落删掉别留历史遗迹；任何可疑处照实记下让用户决断。

输出格式：按 skill 分段，每段列命中的检查项（带文件 / 行号）与建议；最后给"全部无问题的 skill 清单"，避免用户误以为全仓都有病。

批量修复前先跟用户敲定**改动策略**：统一用哪种新写法、原位置留空壳还是删、是否同步调其他 skill 的交叉引用。
