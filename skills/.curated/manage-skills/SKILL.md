---
name: manage-skills
description: 安装、卸载、创建、拆分、重命名、审查或维护本地 skills 时使用；关注 skill 边界、触发描述、跨 skill 引用规范、渐进式披露三层结构（description → SKILL.md → references），以及个人配置与 skill 正文分离。仅处理当前仓库或本地已存在 skill 的组织与维护，不负责外部来源迁入、上游同步或来源索引维护。
---

# Manage Skills

## 职责边界

- 本 skill 负责：本仓或本地**已经存在**的 skill 的安装、卸载、命名、拆分、重构、审查与 README 口径同步。
- `migrate-skills` 负责：从外部仓库引入 skill、上游同步、去品牌化适配、落点选择、`grafted-skills.json` 与来源栏维护。
- `migrate-skills` 是维护者内部 skill，放在 `skills/.internal/`，**不对最终用户展示，也不应写进 README 的用户安装清单**。

## 安装 / 卸载 skill

前提：skills 仓库已克隆到本机某个目录；下文用 `<repo>` 表示该仓库根目录，不假定具体安装路径。

### 路径

skill 在仓库里分五处，按实际位置链：

| 位置 | 含义 | 源路径 |
|---|---|---|
| `skills/.curated/` | 原创（MIT） | `<repo>/skills/.curated/<name>` |
| `skills/` | 嫁接（已人工审核过） | `<repo>/skills/<name>` |
| `skills/.experimental/` | 实验（未人工审核） | `<repo>/skills/.experimental/<name>` |
| `skills/.internal/` | 维护者内部 skill（不对用户暴露） | `<repo>/skills/.internal/<name>` |
| `skills/.legacy/` | 已弃用归档 | `<repo>/skills/.legacy/<name>` |

`skills/.internal/` 只供仓库维护者自用；普通用户安装时不要把这类 skill 链接进 `.agents/skills/` 或写进 README 的技能表。

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
ln -s .agents/skills <target>/.claude/skills
ln -s .agents/skills <target>/.cursor/skills
# 其他工具同理，完整表见仓库 README
```

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

删掉软链即可（skill 本体仍在仓库里，其他项目照常可用）。**推荐移至回收站**（`trash-put` / `rmtrash` / `gio trash` / macOS Finder 拖进废纸篓 / Windows 资源管理器右键“删除”等，按系统挑一个）而非直接 `rm`，误删后可恢复：

```bash
# 下面命令视系统等价替换
trash-put <target>/.agents/skills/<name>
```

### 重构后死链排查

skill 在仓库里改过路径（重命名、迁进 `.curated/` 等）会让旧 symlink 变成死链：

```bash
find <target>/.agents/skills -maxdepth 1 -type l ! -exec test -e {} \; -print
```

找到断的 → 移回收站 → 按新源路径重链。

## 引用

不要在 skill 正文里写依赖本机目录结构的跨 skill 文件路径。用户安装路径、目录名、打包方式都可能不同，硬编码容易失效。需要提示另一个 skill 的能力时，只写 skill 名加能力边界。

同一 skill 内部引用自己的 `references/`、`assets/`、`scripts/` 用相对路径。

## 拆分与整理

- 短小高频的规则直接放 `SKILL.md`；长流程、低频细节、可独立维护的主题放 `references/`。
- 挪内容时先确认新位置覆盖完整原文，再删旧正文；别留重复。
- 重命名 skill 后，同步更新 frontmatter `name`、标题、描述和其他 skill 里的纯文本提示。
- **外部来源迁入、上游同步、来源索引维护不属于本 skill 范围**，统一交给 `migrate-skills`。

## 审查现有 skills

用户让“审查 / 检查所有 skill 是否合规”时，先向用户确认审查范围（如原创、已适配嫁接、实验性、全部），然后按 [references/audit-checklist.md](references/audit-checklist.md) 执行。默认**只审不改**：先列出发现交给用户，明确同意后才动手改。

输出时按 skill 分段，列命中的检查项（带文件 / 行号）与建议；最后附“全部无问题的 skill 清单”，避免用户误以为全仓都有病。

批量修复前先跟用户敲定**改动策略**：统一用哪种新写法、原位置留空壳还是删、是否同步调其他 skill 的交叉引用。

## Hermes

Hermes 有独立的 skill 体系。涉及 `hermes skills install / uninstall / search / inspect / tap / external_dirs` 这类操作时，不要把长流程直接堆在这里，转去看 [references/hermes.md](references/hermes.md)。

该 reference 只负责 Hermes 自己的安装与来源管理；如果是在**本仓**整理已有 skill 的边界、命名、引用和 README，同样还是回到本 skill。
