# 隔离工作区（worktree 与共享 clone）

给「可能出错或需要并行的改动」开一个隔离工作区，避免 stash / reset 频繁切换。典型用途：
尝试有失败风险的大改动、并行跑多个实验分支、用户明确说"在 worktree 里做"。

通用骨架在此，项目特定的构建 / 依赖同步由上层 `AGENTS.md` 或项目自身的 skill 接管。

## 选型

两个判据互相独立：**有没有 submodule** 决定用哪套机制，**要不要编译** 决定要不要把 submodule 拉下来。

### <a id="mechanism-compare"></a>两套机制共享的层级不同

它们不是「同一件事的两种写法」——省盘的效果相似，但共享的层级不一样：

| | [`git worktree`](#git-worktree) | [共享 clone](#shared-clone) |
|---|---|---|
| 本质 | **1 个仓库，N 个工作树** | **N 个独立仓库** |
| objects | 共享（同一 gitdir） | 共享（alternates + 硬链接） |
| refs / 分支 | 共享 | [各自独立](#branch-flow) |
| config | **共享** | 各自独立 |
| HEAD / index | 各自独立 | 各自独立 |
| 同一分支两处 checkout | 拒绝（`already used by worktree at …`） | 可以 |
| 适用 | 无 submodule 的仓库 | 有 submodule 的仓库 |

worktree 共享**整个仓库**，clone 只共享**对象库**。`config` 那一行就是分水岭：submodule 的定位
字段 `core.worktree` 正住在 config 里，是个**单值**字段，表达不了 N 个工作区——谁最后写谁赢。
在 worktree 里跑一次 `git submodule update`，**主工作区**的 submodule 当场变成不可访问；
共享 clone 里 `core.worktree` 是 per-clone 的，这场冲突在结构上不可能发生。
所以不是「小心点就能绕过」的行为问题，选对机制才是解。

`refs / 分支` 那一行是共享 clone 的代价：分支不会自动同步，得手动搬一次（见[分支流转](#branch-flow)）；
换来的是两边能同时 checkout 同一分支。

### 仓库有没有 submodule

```bash
[ -s .gitmodules ] && echo "有 submodule → 共享 clone" || echo "无 submodule → git worktree"
```

有 submodule 就别用 worktree——git 官方把这件事写进了 `git worktree` 文档的
[BUGS 一节](https://github.com/git/git/blob/v2.43.0/Documentation/git-worktree.txt#L513-L517)：

> Multiple checkout in general is still experimental, and the support for submodules is
> **incomplete**. It is **NOT recommended** to make multiple checkouts of a superproject.

无 submodule 时 `git worktree` 是它本来的用途，没有任何坑。

> 机理、实测现场、五个坑、诊断与恢复流程见
> [submodule 与 worktree 的冲突](submodule-hazards.md)。
> 已有 worktree 必须就地修好时，那里也给了权宜之计。

### 这次任务要不要 build

**判据只有一条：要不要编译。** 要就带上 submodule，不要就整个跳过。

| 任务类型 | 要 submodule 吗 |
|---|---|
| 改文档 / 配置 / 脚本 / CI / Markdown | **不要** |
| 只跑 Python 测试、只读代码、只改注释 | **不要** |
| 要 `make` / `ninja` / `cmake` / 链接依赖库 | 要 |

SU2-Quantum 实测的成本差距：

| | 耗时 | 真实增量占盘 |
|---|---|---|
| 带 `--recurse-submodules` | 1 分 37 秒 | +122 MB |
| **不带**（docs 类任务） | **1.17 秒** | **+1 MB** |

**83 倍时间、122 倍空间。** 而且不带 submodule 的 clone 完全够用——实测在其中
`mkdocs build` 成功产出 62 个页面、git 操作正常。

> 真实教训：本文记录的那次事故，起因是为一次**纯 markdown 的 cherry-pick**
> 无条件给 27 个 submodule 建了工作区并跑了 `git submodule update`，导致主工作区的
> `externals/eigen` 被指向别的目录、`git submodule status` 报错。按需触发本可以完全避免。

## <a id="shared-clone"></a>共享 clone（有 submodule 的仓库）

### 建立

```bash
MAIN_REPO=$(git rev-parse --show-toplevel)          # 或见「动态推导主仓库路径」
TIMESTAMP=$(date +%Y-%m-%dT%H-%M-%S)
# 目录名用 .clones/ 而非 .worktrees/（见下方「命名约定」）
NEW="$(dirname "$MAIN_REPO")/$(basename "$MAIN_REPO").clones/cli-clone-$TIMESTAMP"
BRANCH_NAME="cli/clone-$TIMESTAMP"
BASE=$(git -C "$MAIN_REPO" rev-parse --abbrev-ref HEAD)

# 按需：要 build 才加 --recurse-submodules（见「这次任务要不要 build」）
NEED_BUILD=0
[ "$NEED_BUILD" = 1 ] && RECURSE=(--recurse-submodules) || RECURSE=()

mkdir -p "$(dirname "$NEW")"
git -c submodule.alternateLocation=superproject \
    -c submodule.alternateErrorStrategy=info \
    clone --reference "$MAIN_REPO" "${RECURSE[@]}" \
          --branch "$BASE" "$MAIN_REPO" "$NEW"

cd "$NEW"
git checkout -b "$BRANCH_NAME"
# 别让 origin 指着本地仓库（主仓库没有 origin 时跳过）
UP=$(git -C "$MAIN_REPO" remote get-url origin 2>/dev/null) && [ -n "$UP" ] && git remote set-url origin "$UP"
# 再留一条指回主仓库的 remote——origin 改指上游后就够不着主仓库了（见「分支流转」）
git remote add local "$MAIN_REPO"
```

要点：

- `--reference "$MAIN_REPO"` 让超项目借用主仓库的 object store，几乎不复制
- [`submodule.alternateLocation=superproject`](https://github.com/git/git/blob/v2.43.0/Documentation/config/submodule.txt#L96-L102)
  让**每个 submodule**（含任意深度嵌套）自动把 alternates 指到
  `$MAIN_REPO/.git/modules/<path>/objects`，省掉重新下载
- [`alternateErrorStrategy=info`](https://github.com/git/git/blob/v2.43.0/Documentation/config/submodule.txt#L103-L110)
  让个别 submodule 算不出 alternate 时退化成正常 clone 而不是整体失败
- 之后**一切照常**：`git submodule update`、`git checkout`、`git pull` 想怎么用怎么用，
  不需要任何特殊姿势，也不会影响主仓库

命名约定（与 worktree 同构，只换容器目录名和前缀）：

- 时间戳格式 `YYYY-MM-DDTHH-MM-SS`（用 `-` 不用 `:`，跨文件系统兼容）
- clone 目录 `{主仓库父目录}/{仓库名}.clones/cli-clone-{时间戳}`，与主仓库**同级**——
  放进主仓库内部会被 git 看见、污染 `status`
- 容器目录用 `.clones/` 而非 `.worktrees/`：它们不是 worktree，`git worktree list` 看不到、
  `git worktree remove` 也删不掉，同名会误导
- 分支名 `cli/clone-{时间戳}`；`cli-` / `cli/` 前缀标识 agent 创建的，便于和人工开的区分、
  定期批量清理

分支要**单独建一步**，这是和 worktree 的一处操作差异：`git worktree add -b` 建目录和建分支
一条命令就完成，而 `git clone` 只能 checkout 已有分支——所以先用 `--branch "$BASE"` 落在
主仓库当前所在的分支上当起点，再 `git checkout -b "$BRANCH_NAME"` 开专属分支。

clone 的 refs 独立，你**可以**直接在 `main` 上提交（worktree 会拒绝），但那样两边各有一条
`main` 分头前进，[搬回主仓库](#branch-flow)时就撞车；开带时间戳的专属分支，`fetch` 回去
永远是干净的 `[new branch]`。

### <a id="branch-flow"></a>分支流转

共享 clone 的 refs 独立，分支不会自动同步，成果得手动搬一次（为什么见
[两套机制共享的层级不同](#mechanism-compare)）。因为对象早已共享，两个方向的 `fetch`
都**不传输对象**，只更新 ref。

```bash
# 主仓库 → clone：clone 时只带到了当时的分支，之后主仓库新建的要靠 local 取
git fetch local

# clone → 主仓库：把成果送回去
git -C "$MAIN_REPO" fetch "$NEW" "$BRANCH_NAME":"$BRANCH_NAME"
```

⚠️ 目标分支正被对方 checkout 时 fetch 会被拒绝
（`fatal: refusing to fetch into branch 'refs/heads/…' checked out at …`），先切走再 fetch。

成果要长期保留时，直接 `git push origin "$BRANCH_NAME"` 推上游比搬回主仓库更省事。

### 事后补 submodule

事后才发现要 build？补一条即可，不用重来：

```bash
cd "$NEW"
git -c submodule.alternateLocation=superproject \
    -c submodule.alternateErrorStrategy=info \
    submodule update --init --recursive
```

实测补做耗时 2 分 40 秒（比一开始就带 `--recurse-submodules` 的 1 分 37 秒略慢），
终态完全一致：24 条 alternates、异常 0、增量 +122 MB、主仓库零污染。
所以**默认不带是划算的**——大多数任务根本走不到补做这一步。

### 占盘与共享机制

SU2-Quantum 实测（11 个顶层 + 16 个嵌套 submodule，主仓库 `.git` = 3.4G）：

| 指标 | 结果 |
|---|---|
| **真实增量占盘** | **+122 MB**（3535 MB → 3657 MB，约 3.4%） |
| 建立的 alternates | 24 条，含四层嵌套的 `CoolProp/.../pymcx/externals/pybind11` |
| `submodule status --recursive` | 24 个全绿，异常 0 |

> ⚠️ **别用 `du -sh <新clone>/.git` 量占盘**，它会把硬链接重复计数（这里报 2.9G，实际只多占
> 122 MB）。正确的测量方式：`du -cs <主>/.git <新>/.git` 的合计减去 `du -s <主>/.git`。

共享机制分两层，**保护级别不同**：

| 层 | 机制 | 主仓库被删会怎样 |
|---|---|---|
| 超项目 | alternates **＋** pack 硬链接（8/8 个 pack `st_nlink=2`） | 硬链接保命，**不受影响** |
| submodule | **仅** alternates（24 条，0 个硬链接） | **会坏** |

所以 submodule 的 objects 是纯借用，主仓库**不能删**、也不能 `git gc --prune` 掉被借用的对象；
主仓库常规使用（commit / repack）没问题。要彻底断开这层依赖：

```bash
cd "$NEW"
git repack -a -d && rm -f .git/objects/info/alternates
git submodule foreach --recursive 'git repack -a -d && rm -f "$(git rev-parse --git-dir)/objects/info/alternates"'
```

代价是占回全量空间（本例约 3.4G）。

### 拆除

```bash
rm -rf "$NEW"        # 独立 clone，直接删就行，没有注册残留要清
```

分支活在这个 clone 自己的仓库里，删目录即一并消失——先按[分支流转](#branch-flow)把成果搬走或推上游。

## <a id="git-worktree"></a>git worktree（无 submodule 的仓库）

### 建立

**不要硬编码主仓库路径。** 当前已在 git 仓库里（无论主仓库还是已有 worktree）就用
`git rev-parse --git-common-dir` 找共享 `.git`，其上一级即主仓库；不在任何 git 仓库里
就认为 cwd 是主仓库（用于 agent 从项目根调起 skill 的场景）。

linked worktree 的 `.git` 是**文件**（指向主仓库 `.git/worktrees/xxx`），所以它的 `git-dir`
和 `git-common-dir` 不相等；主仓库两者相同。据此判断当前是否已在 worktree 里——
已经在就直接沿用当前目录，不必再建。

```bash
get_main_repo() {
    if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        local common_dir
        common_dir=$(git rev-parse --git-common-dir)
        [ "$common_dir" = ".git" ] && echo "$PWD" || dirname "$common_dir"
    else
        echo "$PWD"
    fi
}

is_linked_worktree() {
    git rev-parse --is-inside-work-tree >/dev/null 2>&1 || return 1
    [ "$(git rev-parse --git-dir)" != "$(git rev-parse --git-common-dir)" ]
}

if is_linked_worktree; then
    NEW="$PWD"                                   # 已在 worktree 里，沿用
else
    MAIN_REPO=$(get_main_repo)
    REPO_NAME=$(basename "$MAIN_REPO")
    TIMESTAMP=$(date +%Y-%m-%dT%H-%M-%S)
    WORKTREES_BASE="$(dirname "$MAIN_REPO")/${REPO_NAME}.worktrees"
    NEW="$WORKTREES_BASE/cli-worktree-$TIMESTAMP"
    BRANCH_NAME="cli/worktree-$TIMESTAMP"

    mkdir -p "$WORKTREES_BASE"
    git -C "$MAIN_REPO" worktree add -b "$BRANCH_NAME" "$NEW"
    cd "$NEW"
fi
```

命名约定：

- 时间戳格式 `YYYY-MM-DDTHH-MM-SS`（用 `-` 不用 `:`，跨文件系统兼容）
- worktree 目录 `{主仓库父目录}/{仓库名}.worktrees/cli-worktree-{时间戳}`，
  统一放同级的 `<repo>.worktrees/` 下避免散落
- 分支名 `cli/worktree-{时间戳}`；`cli-` / `cli/` 前缀标识 agent 创建的，
  便于和人工开的 worktree 区分、定期批量清理

### 拆除

```bash
git worktree remove "$NEW"                   # 有未提交改动时会拒绝——这是保护，别急着加 --force
git branch -d "$BRANCH_NAME"                 # 分支要单独删
```

**不要 `rm -rf` worktree 目录**。目录没了但注册还在（主仓库 `.git/worktrees/` 和每个
submodule 的 `.git/modules/**/worktrees/` 里都有一份），只能靠事后 `prune` 收尾。
已经 `rm -rf` 过的，补跑[恢复流程](submodule-hazards.md#recover)里的 `worktree prune`。

## 项目特定的初始化

构建 / 依赖同步 / 环境激活由项目 `AGENTS.md` 或项目自身的 skill 决定，本文不覆盖。常见步骤：

- 包管理器：`uv sync` / `poetry install` / `npm install`
- 构建：`poe setup && poe build` / `cmake` / `make`
- 环境：`source .venv/bin/activate` / `conda activate`

如果项目需要"一次性 worktree + 构建"的工作流，写一个薄壳 skill 先按本文建工作区、
再跑项目自己的构建命令即可。

## 易错命令对照

碰上 submodule 时容易踩的几条，右列点进去是机理与现场：

| 你想干什么 | 用这个 | 别用这个 |
|---|---|---|
| 在 worktree 里对齐 submodule 版本 | `ls-tree` + `git -C <path> checkout --detach` | `git submodule update`（[会劫持主工作区](submodule-hazards.md#core-worktree-hijack)） |
| 删掉**失效**的 worktree 注册 | `git worktree prune` | [手删 `worktrees/*`](submodule-hazards.md#manual-delete) |
| 撤掉被劫持的 `core.worktree` | `git config -f <gitdir>/config --unset core.worktree` | 手改 config 文本 |
| 批量撤 `core.worktree`（含嵌套） | 递归 `find .git/modules -name config`（见[恢复流程](submodule-hazards.md#recover)） | 单层通配 `.git/modules/*/config` |
| 遍历所有 submodule 的 gitdir | `find .git/modules -type d -name worktrees` | `git submodule foreach --recursive`（[有盲区](submodule-hazards.md#foreach-blind-spot)） |
| 看清当前状态 | `git worktree list` / `prune --dry-run -v`（见[动手前的诊断](submodule-hazards.md#diagnose)） | 直接跑破坏性命令 |
