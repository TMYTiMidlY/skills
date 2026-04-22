---
name: manage-skills
description: 安装、卸载、创建、拆分、重命名、迁移、审查或维护本地 skills 时使用；关注 skill 边界、触发描述、跨 skill 引用规范、渐进式披露三层结构（description → SKILL.md → references），以及个人配置与 skill 正文分离。
---

# Manage Skills

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

**工具目录已有用户自己的内容时**：如果 `<target>/.claude/skills/`（或其它工具目录）已存在、不是 symlink、里面有用户自己装的 skill，说明用户之前按各工具原生方式装过，**不要直接覆盖**。告诉用户"这里有 N 个条目，要不要迁进 `.agents/skills/` 统一管理再建整目录软链？"，等用户点头。

**单 skill 同名 / 同能力冲突时**：遍历目标范围下所有 `.<tool>/skills/*/SKILL.md`，读每份 frontmatter 的 `name` 和 `description`，和准备装的这份比对：

- **name 相同**：告知用户"`<name>` 已在 `<某路径>` 下装过"，问要不要换成本仓库的 symlink；同意就把旧的移回收站再建 symlink。
- **name 不同但 description 在讲同一能力**：告知用户这是同一能力的另一实现，让他决定保留哪份。

**只报告、不自动改**，等用户确认。

### 卸载

删掉软链即可（skill 本体仍在仓库里，其他项目照常可用）。**推荐移至回收站**（`trash-put` / `rmtrash` / `gio trash` / macOS Finder 拖进废纸篓 / Windows 资源管理器右键"删除"等，按系统挑一个）而非直接 `rm`，误删后可恢复：

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

## 拆分与迁移

- 短小高频的规则直接放 `SKILL.md`；长流程、低频细节、可独立维护的主题放 `references/`。
- 迁内容时先确认新位置覆盖完整原文，再删旧正文；别留重复。
- 重命名 skill 后，同步更新 frontmatter `name`、标题、描述和其他 skill 里的纯文本提示。

## 审查现有 skills

用户让"审查 / 检查所有 skill 是否合规"时按本节办。**只审不改**——先向用户确认审查范围（如原创、已适配嫁接、实验性、全部），列出发现交给用户，明确同意后才动手改。

检查项：

- **引用状态**：
  - 同 skill 内引用（`references/`、`assets/`、`scripts/`）都用相对路径，不写绝对或 `~/...`；且目标真实存在（grep 验证）。
  - 跨 skill 不给任何文件路径，只写 skill 名加能力边界。
- **不硬编码仓库 clone 位置**：skill 正文、reference、README 里不要把 skills 仓库位置写死为 `~/skills`、`C:\Users\...\skills`、`/home/.../skills` 等具体路径；需要表达仓库根目录时用 `<repo>` 这类占位符，并说明由当前安装位置决定。
- **脚本运行与依赖声明**：正文或 reference 里提到运行同 skill 自带 Python 脚本时，应要求使用 `uv`，脚本路径保持为当前 skill 根目录下的 `scripts/` 相对路径，不写绝对路径、`~/...`、上层跳转路径或绑定本机仓库位置的路径；脚本的 Python 版本与第三方依赖应放进 PEP 723 内联脚本元数据（inline script metadata），不要把安装命令或临时依赖细节堆进 skill 正文。
- **渐进式披露三层完整、分工清晰**：`frontmatter description` → `SKILL.md` → `references/*.md`。
  - description：只写"何时触发 + 核心思路一句话"。
  - SKILL.md：短规则 + 各主题入口 + 子文档索引；不堆长流程与整段命令。
  - references/：单主题一文件，长流程 / 踩坑 / 模板。
  - 常见病：SKILL.md 堆满命令（该下放）；references 存在但 SKILL.md 没索引（找不到入口）；description 太笼统或太具体。
  - 判定：SKILL.md 读完应当知道"能做什么、哪个 reference 讲什么"，**不应该读完就能完成具体任务**——那说明 references 层缺位。
- **个人配置不入 skill 正文**：凭据 / 域名 / 服务器地址 / 个人样例文件名都不写进 skill 正文。正文只写变量名、占位符和读取位置，真实值放 `~/.env` 或个人笔记。
- **不绑定特定 AI 工具的具体工具名**：skill 正文不写 `AskUserQuestion`、`TodoWrite`、`WebFetch`、`Task` 这类特定宿主（Claude Code / Codex / Cursor / Trae 等）独有的工具名。同一能力在不同宿主里名字不同，硬编码会让 skill 在其它宿主跑不了。改写成能力描述："向用户提问的工具"、"任务清单工具"、"抓网页的工具"，由模型按当前环境自己挑。只有当 skill 明确只服务单一宿主、且在 description 里讲清楚时才可以保留具体名字。
- **README 与 skill 实际状态同步**：README 表格条目的名称 / 来源 / 说明要和 skill 自身的 frontmatter `description` 口径一致；合并 / 拆分 / 重命名 / 删除 skill 后，README 不能留 stale 条目；外部索引按其自身语义核对，例如 `grafted-skills.json` 记录上游来源路径，不按本仓落点判断。
- **所有命名空间内 skill 的 frontmatter `name` 必须全局唯一**（`.curated/` / `.experimental/` / `.legacy/` / 嫁接根目录加起来不能有重名）：Hermes 按 `name` 去重，first-seen wins 后者悄悄丢弃；如果同名 skill 落在同一个 external_dir 的不同子目录下（如 `skills/pdf` 和 `skills/.experimental/pdf`），谁先被扫到取决于文件系统遍历顺序，**行为不确定**。审查时 grep 所有 SKILL.md 的 `name:` 字段，发现重名就报告。
- **其他结构性检查**：frontmatter `name` 与目录名一致；弃用段落删掉别留历史遗迹；任何可疑处照实记下让用户决断。

输出格式：按 skill 分段，每段列命中的检查项（带文件 / 行号）与建议；最后给"全部无问题的 skill 清单"，避免用户误以为全仓都有病。

批量修复前先跟用户敲定**改动策略**：统一用哪种新写法、原位置留空壳还是删、是否同步调其他 skill 的交叉引用。

---

## 为 Hermes 安装 skill

Hermes 有自己的 skill 体系，用 `hermes skills` CLI 单独管理；它不会自动读取其它工具（Claude Code / Cursor / Codex 等）的 skills 目录，想让 Hermes 用上同一个 skill 要单独装一份。

能用 `hermes skills install / uninstall` 搞定的就用命令，别手动摆目录——Hermes 会自己管安全扫描、锁文件和更新追踪。

### 三种 skill 来源

`hermes skills list` 里每条记录都带一个 `Source` 字段：

| 来源 | 含义 | 命令能管吗 |
|------|------|-----------|
| `builtin` | 随 Hermes 发行版打包的 skill | 不能装/卸，只能 `reset`（清除"user-modified"标记） |
| `hub` | 从 registry 拉下来的，走 `install`/`uninstall` 流程 | 可装可卸，有安全扫描与锁文件 |
| `local` | 用户自己放进 Hermes skill 根的 skill | 靠文件系统管理 |

### 从 registry 安装

```bash
hermes skills install <identifier> [--category <category>] [--yes]
```

`<identifier>` 采用 `<registry>/<path>/<name>` 的多级命名，常见形式：

- `skills-sh/<owner>/<repo>/<name>` — skills.sh 第三方索引站（从 GitHub 仓库收录而来；上游是官方仓的条目会标 `trusted`，其余为 `community`）
- `official/<category>/<name>` — Hermes 自带的官方 hub
- 只写 skill 名 — 在所有已知 registry 中搜索

要接入更多来源（如额外的 GitHub 仓库）用 `hermes skills tap add <owner/repo>`。不确定名字时先 `hermes skills search <query>` 找，`hermes skills inspect <identifier>` 预览，再决定是否安装。

### 把本地 skill 装进 Hermes

要让 Hermes 用上某个本地来源（含本仓库）的 skill，按 Hermes 约定的 `<category>/<name>/SKILL.md` 结构，把 skill 放进 Hermes 的 local skill 根——软链（推荐，改动同步）或复制均可。

local 根的具体位置以` 的输出为准；分类按 skill 实际主题选，不匹配时 Hermes 会回落到 `local` 但可能影响加载。

> 想让某个项目目录下的 skill 被 Hermes 发现但不移动文件，可在 `~/.hermes/config.yaml` 的 `skills.external_dirs` 里加入该目录；只读发现，不会改写。SSH / 远程 backend 不需要单独配置 skill，Hermes 会把本地 skill 同步到远端。

### 其他管理命令

| 操作 | 命令 |
|------|------|
| 列出已安装 | `hermes skills list [--source all\|hub\|builtin\|local]` |
| 搜索可装 | `hermes skills search <query>` |
| 预览（不装） | `hermes skills inspect <identifier>` |
| 卸载（仅 hub） | `hermes skills uninstall <name>`（需 y 确认） |
| 检查更新 | `hermes skills check` |
| 更新所有 | `hermes skills update` |
| 管理额外 registry | `hermes skills tap {list,add,remove}` |
