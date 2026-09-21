---
name: manage-skills
description: 创建、安装、重构、审查或合并本地 skill 时使用。核心是维护清晰的能力边界、渐进式文档结构、可追踪的安装链接与一致的仓库规范。
---

# Manage Skills

按任务选择入口：写改 skill 先读 [写作规范](references/conventions.md)，审查读 [审查流程](references/review.md)，单篇深度重构读 [重构流程](references/refactor.md)，合并分叉读 [合并流程](references/merge.md)。安装或卸载才执行下面的安装流程；解释和审查本身不授权安装、覆盖或清理。

## 安装 / 卸载 skill

前提：skills 仓库已克隆到本机某个目录；下文用 `<repo>` 表示该仓库根目录，不假定具体安装路径。

### 路径

skill 在仓库里分三处，按实际位置链：

| 位置 | 含义 | 源路径 |
|---|---|---|
| `skills/.curated/` | 原创（MIT） | `<repo>/skills/.curated/<name>` |
| `skills/` | 嫁接（已人工审核过） | `<repo>/skills/<name>` |
| `skills/.experimental/` | 实验（未人工审核） | `<repo>/skills/.experimental/<name>` |

### 安装（两层软链）

**第 1 层·skill 级**：把要用的 skill 从仓库软链进 `<target>/.agents/skills/<name>`（`<target>` 是 `~/` 全局或 `<project>/` 项目级）：

```bash
mkdir -p <target>/.agents/skills
ln -s <源路径> <target>/.agents/skills/<name>
```

Windows 下如果创建目录 symlink 提示需要管理员权限，而源和目标都在本地 NTFS 目录，可以用 junction 代替：

```powershell
New-Item -ItemType Junction -Path "<target>\.agents\skills\<name>" -Target "<源路径>"
```

Junction 是文件系统级目录链接，不是 `.lnk` 快捷方式；工具按 `<target>/.agents/skills/<name>/SKILL.md` 读取时会直接落到仓库实体。仅链接本地目录时 junction 足够；需要链接文件、网络路径、WSL 路径或相对路径时仍优先使用 symlink。

**第 2 层·工具级**：Claude Code / Cursor / Amp / Junie 等都有各自的 skills 目录（`.claude/skills/`、`.cursor/skills/` …）。把**整个**工具目录软链到 `.agents/skills/`，让所有工具共享同一份：

```bash
ln -s ../.agents/skills <target>/.claude/skills
ln -s ../.agents/skills <target>/.cursor/skills
ln -s ../../.agents/skills <target>/.config/agents/skills
# 其他工具按目标目录层级调整相对路径，完整表见仓库 README
```

**原生扫 `.agents/skills/` 的 CLI 不需要第 2 层**：GitHub Copilot CLI、Gemini CLI、Codex、Cline、Warp、Windsurf、Roo Code 等直接读 `.agents/skills/`（项目级，沿 cwd→git root 收录）和 `~/.agents/skills/`（个人级），软链 hub 即被发现，无需再建工具专属目录。

⚠️ 易踩坑：**项目级**的 skill 约定目录只有 `.github/skills`、`.agents/skills`、`.claude/skills` 三种，**没有** `.copilot/skills`。`~/.copilot/skills` 只在 home（个人级）下有效；别照着"个人级 `~/.copilot/skills`"在项目里建 `<project>/.copilot/skills` 软链——没有 CLI 会把它当项目级 skill 读。

注意：symlink 的目标相对路径是按**链接所在目录**解析的；不确定层级时用绝对路径更稳。

好处：

- **统一修改**：任一处编辑都落到仓库实体，所有工具同步可见
- **git 追踪**：改动走仓库 git，有历史、可回滚、便于协作

### AGENTS.md / CLAUDE.md

全局安装或维护 skill 完成后，顺便检查 `~/AGENTS.md` 和 `~/CLAUDE.md`。只有当其中任一文件不存在时，才询问用户是否要补装仓库根目录的 `AGENTS.md` / `CLAUDE.md`。

用户同意后，把 `~/AGENTS.md` 做成指向 `<repo>/AGENTS.md` 的软链接，再把 `~/CLAUDE.md` 做成指向 `~/AGENTS.md` 的软链接；`CLAUDE.md` 不单独维护内容。已有的文件不替换、不覆盖。Windows 下创建文件 symlink 需要权限时，按当前环境请求授权；不要用 `.lnk` 快捷方式代替。

### 安装前先扫环境、冲突就问不自动改

**工具目录已有用户自己的内容时**：如果 `<target>/.claude/skills/`（或其它工具目录）已存在、不是 symlink、里面有用户自己装的 skill，说明用户之前按各工具原生方式装过，**不要直接覆盖**。告诉用户“这里有 N 个条目，要不要迁进 `.agents/skills/` 统一管理再建整目录软链？”，等用户点头。

**单 skill 同名 / 同能力冲突时**：遍历目标范围下所有 `.<tool>/skills/*/SKILL.md`，读每份 frontmatter 的 `name` 和 `description`，和准备装的这份比对：

- **name 相同**：告知用户“`<name>` 已在 `<某路径>` 下装过”，问要不要换成本仓库的 symlink；同意就把旧的移回收站再建 symlink。
- **name 不同但 description 在讲同一能力**：告知用户这是同一能力的另一实现，让他决定保留哪份。

**只报告、不自动改**，等用户确认。

### 卸载

卸载只移除目标安装位置的软链，不删除仓库里的 skill 本体，其他安装位置仍可使用。遵循当前环境的删除规则；本仓 `AGENTS.md` 指定使用 `trash-put`，不能因为只是软链而自动改用永久删除。工具不可用或平台不同，先确认获准的处理方式，不自行放宽限制：

```bash
# 确认这是目标安装软链，并已获准卸载后执行
trash-put <target>/.agents/skills/<name>
```

### 重构后死链排查

skill 在仓库里改过路径（重命名、迁进 `.curated/` 等）会让旧 symlink 变成死链：

```bash
for link in <target>/.agents/skills/*; do
  [ -L "$link" ] && [ ! -e "$link" ] && printf '%s\n' "$link"
done
```

找到断的 → 移回收站 → 按新源路径重链。

## 写 / 改 skill 的规范

写、改、审查、重构任何 skill 都按 [references/conventions.md](references/conventions.md) 的要求来——那是唯一出处，含完整理由与正反例。**别在这里或别的 skill 里重抄规则，要提就写条目名链过去。** 速览（点进 conventions 看细节）：

- **内容**：清楚地表达内容｜不说废话｜命令 / 配置简洁准确｜操作前提与边界明确｜图形界面流程具体｜事实、推断与建议分开｜自然穿插踩坑 / 排障｜个人配置不入正文
- **引用**：补充来源、限制和例外用 `>` 紧跟正文｜来源与置信度就近｜引用做成可点击 Markdown 链接｜同 skill 使用相对路径和显式 `<a id>` 锚点｜跨 skill 只写 skill 名 + 能力边界｜上游链接锁定版本
- **标题**：命名"这节是什么"、不预告结论 / 计数 / 排名｜不编号、不用 §N 交叉引用｜并列小节靠客观属性区分｜改带 `<a id>` 的标题只改文字
- **结构**：渐进式披露三层按需加载、分工清楚｜单文件长度不是拆分理由｜脚本用 `uv` + PEP 723 内联依赖｜不绑定特定 AI 工具名｜frontmatter `name` 与目录名一致｜README 与 skill 状态同步

## 重构已有文档

把一篇已成型的文档（SKILL.md 或 reference）做深度重构：核验事实，理顺标题树、章节归属和来源组织，做到语义不漏、重复不留。核心：**先分别提交标题方案和内容迁移表供审阅，两轮批准后才动手**，全程对照 [references/conventions.md](references/conventions.md) 逐条核对。完整流程与审阅格式见 [references/refactor.md](references/refactor.md)。

## 审查现有 skills

先采用用户已明确的对象、维度和深度，只确认影响工作量或结论的缺口。表达与结构、指令与执行边界、技术事实、许可证与上游状态可以分别审查；完整合规审查才逐条核对 [references/conventions.md](references/conventions.md) 的适用要求并覆盖相关专项检查。默认**只审不改**，报告说明全文 / 抽样覆盖及未核验部分，不把专题审查扩成全量审计。流程与输出要求见 [references/review.md](references/review.md)。

## 解决合并冲突

把两条分叉的 skill 文档分支合到一起（双向分叉、两边各自重构同一大文件、术语 / 定义分歧）时，别当成机械删冲突标记——核心是**理解两边意图后，重建一份一致、不丢信息、无重复的知识**。要点：动手前勘定环境 + 无损预演冲突清单；三方溯源看意图（别急着否掉一侧）；给冲突分类套手法（纯并集 / 干净超集 / 结构分叉选底本 splice / 术语分叉查一手来源）；通读结构抓自动合并在冲突标记之外制造的静默重复；splice 后修交叉引用；只收本次合并该带的、隔离并发 / 脏改动；reference 先于 SKILL.md；大改走重构流程；解决即验。完整方法见 [references/merge.md](references/merge.md)。

## Hermes

Hermes 的 skill 发现机制和本仓这套 `.agents/skills` 软链不一样（走它自己的 `hermes skills` CLI），给 Hermes 装 / 卸 skill 时去 `harness` skill 的 Hermes 运行时章节参考一下。
