---
name: graft-skill
description: 管理从外部 GitHub 仓库嫁接（引入）的 skill。当用户要添加、移除、修改外部 skill，或提到"检查更新"、"同步上游"、"upstream"时触发。
---

# Graft Skill

从外部 GitHub 仓库嫁接 skill 到本仓库，管理其完整生命周期：引入 → 试验 → 转正 → 修改 → 同步 → 移除。

## 职责边界

- 本 skill 面向仓库维护 / skill 开发流程，不属于普通用户安装与使用场景。
- 本 skill 负责：从外部仓库引入 skill、上游同步、去品牌化适配、落点选择、`grafted-skills.json` 与 README 来源栏维护。
- `manage-skills` 负责：本仓或本地**已经存在**的 skill 的安装、卸载、命名、拆分、重构、审查与 README 口径同步。它是可对外安装的用户 skill，不应依赖本维护区 skill 的存在。

## 仓库内 `.claude/skills` 的语义

仓库里 `.claude/skills` 本身是 symlink，**整体**指向 `.agents/skills`：

```
<repo>/.claude/skills  →  ../.agents/skills
```

所以在仓库工作时，`<repo>/.claude/skills/<x>` 和 `<repo>/.agents/skills/<x>` 是同一实体。两者的**公开区**才是 `<repo>/skills/`（分发给其他项目）。

| 操作（在 `<repo>/` 仓库内） | 落点 | 同步 |
|---|---|---|
| 在 `.claude/skills/` 下 `mkdir myskill` | 穿透 → `.agents/skills/myskill/`（维护区，不在公开分发区） | ✅ |
| 在 `.claude/skills/<x>/` 下新建 `reference/` | 穿透 → `.agents/skills/<x>/reference/` | ✅ |
| 把路径 `.claude/` 换成 `.agents/` | 指向同一目录，**完全等价** | ✅ |
| 直接在 `<repo>/skills/<name>/` 下写 | 公开分发区 | ✅ |

**判断方法**：`readlink -f <path>` 看落点。落在 `.agents/skills/` → 维护区；`skills/` → 公开区；仓库外 → 不进 git。

**新增公开 skill 的正确做法**：在 `<repo>/skills/<name>/` 下建实体，而不是通过 `.claude/skills/` 新建（否则会写到维护区）。

## 配置文件

`grafted-skills.json` 记录所有外部 skill 的来源和同步状态。key 是 skill 名称（试验区带 `.experimental/` 前缀）：

```json
{
  "slidev": {
    "repo": "slidevjs/slidev",
    "path": "skills/slidev",
    "branch": "main",
    "synced_commit": "d76850d",
    "synced_date": "2026-03-11T23:54:58Z",
    "description": "Slidev 官方 skill"
  },
  "ppt-master": {
    "repo": "hugohe3/ppt-master",
    "path": "skills/ppt-master",
    "branch": "main",
    "synced_commit": "f864ec5",
    "synced_date": "2026-05-21T23:29:39Z",
    "description": "..."
  }
}
```

**字段说明：**

- `synced_commit` / `synced_date`：上次同步的上游 commit（短 sha + ISO 时间），同步流程基线。

**本地补丁约定**：是否有本地补丁、补丁顺序与内容都由 `patches/<skill>/series` 文件描述（quilt 原生格式），JSON 不重复记录。约定：`patches/<skill>/series` 存在即代表该 skill 有本地补丁，按 series 顺序应用。详见下文「本地补丁（quilt）」。

**每次修改 `grafted-skills.json` 后，运行 `scripts/update-readme.py` 更新 README。** 脚本只用 `name` / `repo` / `description` 三个字段生成 `<!-- skills-table:begin/end -->` 之间的内容。

## 引入

1. 安装 skill：`bunx skills add {repo} --skill {skill-name} -a github-copilot -y`
   - 列出可用 skill：`bunx skills add {repo} --list`
2. 将 `.agents/skills/{skill-name}/` 移到 `skills/.experimental/{skill-name}/`。
3. 获取上游最新 commit（用于填写 `synced_commit` 和 `synced_date`）：
   ```
   gh api "repos/{repo}/commits?path={path}&sha={branch}&per_page=1" --jq '.[0] | {sha: .sha[0:7], date: .commit.author.date}'
   ```
4. 在 `grafted-skills.json` 中添加条目，key 写 `.experimental/{skill-name}`。
5. 与用户协作审阅和修改（适配本仓库约定、调整描述等）。

## 转正

1. 对 skill 内容做适配修改，使其不绑定特定 AI 产品：
   - **去品牌化 / 去宿主绑定**：重点检查 skill 正文是否依赖某个宿主的专属概念、工具调用、平台链接或运行方式，而不是机械删除所有提供商名称。`Claude`、`Codex`、`OpenAI`、`ChatGPT`、`Copilot` 等名称可以在管理说明、来源说明、兼容性说明或工具目录说明中出现；但在可复用 skill 正文里，若它们被用来规定工作流、调用专属工具、绑定平台能力或引导访问特定产品链接，应改为通用表述（如 `agent`、文件操作、向用户提问的工具），并删除不必要的产品链接（如 `claude.ai`）。
   - **统一依赖管理**：`python scripts/...` 改为 `uv run scripts/...`；`pip install X` 改为 `uv run --with X`。
2. 将 `skills/.experimental/{skill-name}/` 移到 `skills/{skill-name}/`。
3. 更新 `grafted-skills.json` 中的 key，去掉 `.experimental/` 前缀。

## 修改

直接编辑本仓库中的文件。同步时通过 git diff 识别本地改动和冲突。

## 检查更新

对 `grafted-skills.json` 中的每个条目，查询自上次同步以来的 commit：

```
gh api --paginate "repos/{repo}/commits?path={path}&since={synced_date}&sha={branch}&per_page=100" \
  --jq '.[] | {sha: .sha[0:7], date: .commit.author.date, message: .commit.message | split("\n")[0]}'
```

注意 `since` 是包含性的，需排除 `synced_commit` 本身。

## 同步

用户确认要同步后：

1. 逐个查看新 commit 的 diff：
   ```
   gh api "repos/{repo}/commits/{sha}" \
     --jq '.files[] | select(.filename | startswith("{path}/")) | {filename, status, patch}'
   ```
2. 与本地文件对比，无冲突直接应用，有冲突展示给用户决定。
3. 更新 `synced_commit` 和 `synced_date`。
4. **如果 `patches/<skill>/series` 存在**：用 quilt 重新应用本地补丁，详见下面「本地补丁（quilt）」§Re-graft 一节，否则本仓的本地适配会丢。

## 本地补丁（quilt）

对嫁接版本做的本地适配（去品牌化无法覆盖、需要解耦上游硬编码路径等）用 [quilt](https://savannah.nongnu.org/projects/quilt/) 管理，patch 文件统一放在仓库根 `patches/<skill>/`，quilt 工作元数据集中在仓库根 `.quilt-pc/<skill>/`（已 gitignore）。`skills/<skill>/` 始终保持成品工作版（含 patches 应用后的状态），**不含任何 quilt 工件**，可直接分发。

**目录布局**：

```
<repo>/
├── skills/<skill>/          # 成品工作版，分发出去
├── patches/<skill>/
│   ├── series               # quilt 必需，每行一个 patch 文件名
│   ├── 0001-<name>.patch    # quilt 格式 / git format-patch 都兼容
│   └── README.md            # 人类可读说明
└── .quilt-pc/<skill>/       # quilt 元数据，gitignore
```

**调用 quilt 的标准范式**（quilt 处理相对路径有 bug，必须用绝对路径）：

```bash
REPO=$(git rev-parse --show-toplevel)
SKILL=ppt-master
cd "$REPO/skills/$SKILL"
QUILT_PATCHES="$REPO/patches/$SKILL" \
QUILT_PC="$REPO/.quilt-pc/$SKILL" \
  quilt <subcommand>
```

下面所有命令都默认 `cd $REPO/skills/$SKILL` + 设好两个 env var。

### 关键前提：`.quilt-pc/<skill>/` 不存在是常态

`.quilt-pc/` 被 gitignore，**clone 后、新机器上、跨 session、上次清理后** 它都不存在。`quilt push` 会自动创建并接管栈，所以**绝大多数操作直接 `quilt push -a` 起手即可**——quilt 会在 `.quilt-pc/$SKILL/` 不存在时建立栈、push 完成后 working tree 即「成品 + quilt 接管」状态。

唯一例外：**`quilt pop` / `quilt header -e` / `quilt refresh` 这类依赖栈状态的命令**，必须先有 `.quilt-pc/$SKILL/`——下面每个流程会在前提里写清楚。

### 新加补丁

成品状态（`.quilt-pc/` 可有可无）→ 在最末尾叠一个新 patch：

```bash
quilt push -a              # 幂等：.quilt-pc 不存在则建栈，存在则确认全部已 apply
quilt new 0002-<short>.patch
quilt edit some/file.py    # 改文件；quilt 自动把该文件注册进 top patch 的快照
# ... 重复 edit 多个文件 ...
quilt refresh              # 把工作树跟 .pc 快照的差异写入 patch 文件
quilt header -e            # 可选：编辑 patch 的描述头部
```

### 改已有的补丁

```bash
quilt push -a              # 同上幂等起手
quilt pop <patch>          # 回退到目标 patch 之下（更上面的会被 unapply）
quilt push                 # 再 push 一个，让目标 patch 成为 top
quilt edit some/file.py    # 在 top 状态下改文件
quilt refresh              # 写回 patch
quilt push -a              # 把后续 patch 重新应用上
```

### Re-graft（上游有更新后重放本地补丁）

前提：`skills/<skill>/` 是上游 OLD_SYNC + 本地 patches 应用后的成品状态。

```bash
REPO=$(git rev-parse --show-toplevel)
SKILL=ppt-master
NEW_SYNC=<上游新 commit sha>

# 1. reverse 出裸上游 OLD_SYNC
cd "$REPO/skills/$SKILL"
if [ -d "$REPO/.quilt-pc/$SKILL" ]; then
  QUILT_PATCHES="$REPO/patches/$SKILL" QUILT_PC="$REPO/.quilt-pc/$SKILL" quilt pop -a
else
  # .quilt-pc 不存在（首次/clone 后），按 series 倒序手动 patch -R
  tac "$REPO/patches/$SKILL/series" | while read p; do
    patch -p1 -R < "$REPO/patches/$SKILL/$p"
  done
fi
trash-put "$REPO/.quilt-pc/$SKILL" 2>/dev/null || true   # 让下一步从 clean 起手

# 2. rsync 上游 NEW_SYNC 覆盖
rsync -a --delete --exclude='.git' /tmp/upstream-clone/<upstream-path>/ ./

# 3. 重放本地 patch
QUILT_PATCHES="$REPO/patches/$SKILL" QUILT_PC="$REPO/.quilt-pc/$SKILL" quilt push -a
# 全成功：跳到第 5 步
# 部分/全失败：见下面「冲突处理」

# 4. （冲突解完后）quilt refresh，刷新 patch 文件到新 context
QUILT_PATCHES="$REPO/patches/$SKILL" QUILT_PC="$REPO/.quilt-pc/$SKILL" quilt refresh

# 5. 更新 grafted-skills.json 的 synced_commit / synced_date
# 6. 跑 .agents/skills/graft-skill/scripts/update-readme.py
# 7. 清 .quilt-pc/<skill>（可选，本就 gitignore）
trash-put "$REPO/.quilt-pc/$SKILL"
```

**冲突处理**：第 3 步失败时，quilt 默认会写 `.rej` 文件并停在失败的 patch。看 reject 的范围和性质，分两类：

- **Context drift / 局部冲突**（hunk 落点仍能识别，只是上下文飘了）：交给 agent 处理——可以选 `quilt push -af --merge` 让 patch 把冲突以 `<<<<<<<`/`=======`/`>>>>>>>` 标记写进源文件，然后人工/agent 编辑解开，最后 `quilt refresh`。
- **结构性重写**（上游把 patch 触及的文件整个重构了，hunk 找不到落点）：放弃自动 merge，让 agent 在新上游基础上**重新写 patch**——`trash-put .quilt-pc/$SKILL` 清栈、重 rsync、`quilt new` 重命名后重做、删旧 patch 更新 series。

不要让 SKILL.md 写死冲突解决脚本——具体走哪条路需要看 diff 才能判断，是 agent 决策范畴。

### 首次接入 quilt（已有 patch 文件，但 series 未建立）

```bash
cd "$REPO/patches/$SKILL"
ls *.patch | sort > series
# 路径前缀剥离：git format-patch 产物的 +++ b/skills/<skill>/foo 需要变成 +++ b/foo 或 +++ <skill>/foo
sed -i -E 's@(\+\+\+ b/|--- a/)skills/'"$SKILL"'/@\1@g' *.patch
# 端到端验证：从裸上游 quilt push -a 能干净 apply
```

### 注意事项

- patch 文件路径必须相对 `skills/<skill>/` 根，**不能含 `skills/<skill>/` 前缀**。git format-patch 默认带 `a/`/`b/` 前缀，quilt refresh 后会重写成 `<skill>/` 风格——两种都能 push（quilt 默认 `-p1` strip）。
- `quilt refresh` 保留 patch 文件顶部所有非 diff 内容（git format-patch 的 `From/Subject/Date/MIME` 头部不会被吃掉）。
- `.quilt-pc/` 不进 git，是状态文件不是临时文件——push/refresh 中途别删；流程结束后可以删，下次再 `quilt push -a` 重建即可。
- quilt 跨设备时会报 `Invalid cross-device link`——`QUILT_PATCHES` / `QUILT_PC` 必须用绝对路径才能规避。

## 移除

1. 删除 skill 目录。
2. 从 `grafted-skills.json` 中移除条目。

## 注意事项

- 本地修改优先，同步时不能盲目覆盖。
- 用 `gh api` 而非裸 `curl`，自带认证和分页。
- `grafted-skills.json` 记录的是**上游来源路径**，不是本仓落点；核对来源索引时按上游语义判断。
- 来源尚未确认时，宁可留空，也不要猜测补值。
