# 隔离工作区（worktree 与独立 clone）

给「可能出错或需要并行的改动」开一个隔离工作区，避免 stash / reset 频繁切换。典型用途：
尝试有失败风险的大改动、并行跑多个实验分支、用户明确说"在 worktree 里做"。

通用骨架在此，项目特定的构建 / 依赖同步由上层 `AGENTS.md` 或项目自身的 skill 接管。

## 选型

是否需要独立的仓库配置影响工作区机制，任务是否实际依赖子模块内容决定初始化范围；两者分别判断。

### <a id="mechanism-compare"></a>两套机制共享的层级不同

它们不是「同一件事的两种写法」——省盘的效果相似，但共享的层级不一样：

| | [`git worktree`](#git-worktree) | [独立 clone](#shared-clone) |
|---|---|---|
| 本质 | **1 个仓库，N 个工作树** | **各自维护 refs / config；对象是否独立另看借用方式** |
| objects | 共享（同一对象库） | 可借用 alternates / 本地硬链接，也可用 `--dissociate` 结束借用 |
| refs / 分支 | 共享 | [各自独立](#branch-flow) |
| config | 默认共享；另有 worktree-specific 配置扩展 | 各自独立 |
| HEAD / index | 各自独立 | 各自独立 |
| 同一分支两处 checkout | 拒绝（`already used by worktree at …`） | 可以 |
| 适用 | 无 submodule 的仓库 | 有 submodule 的仓库 |

worktree 默认共享仓库配置和对象库，clone 则有自己的 refs / config。独立 config 能避免
下述共享 submodule gitdir 的 `core.worktree` 冲突，但**配置独立不等于对象独立**：
`--reference` / `--shared` 会留下对源对象库的依赖。

源仓库不会考虑借用方独有的 refs；源端删除分支、改写历史后，后续自动维护可能回收
借用方仍需要的对象。因此默认用 `--reference ... --dissociate`：复制时利用参考仓库，
完成后补齐所需对象、结束借用。只有明确管理源仓库生命周期和对象保留策略的短期工作区，
才选择持续借用以省空间。

> 依据：[Git 2.43 · clone 的 shared / reference / dissociate](https://git-scm.com/docs/git-clone/2.43.0)。
> 本地 clone 还可能与源端并发修改发生竞争；`--dissociate` 不是并发备份或独立备份介质保证。

`refs / 分支` 那一行是独立 clone 的代价：分支不会自动同步，得手动搬一次（见[分支流转](#branch-flow)）；
换来的是两边能同时 checkout 同一分支。

### 仓库有没有 submodule

```bash
[ -s .gitmodules ] && echo "有 submodule → 独立 clone" || echo "无 submodule → git worktree"
```

有 submodule 默认走独立 clone——git 官方把这件事写进了 `git worktree` 文档的
[BUGS 一节](https://github.com/git/git/blob/v2.43.0/Documentation/git-worktree.txt#L513-L517)：

> Multiple checkout in general is still experimental, and the support for submodules is
> **incomplete**. It is **NOT recommended** to make multiple checkouts of a superproject.

无 submodule 时 `git worktree` 是它本来的用途，没有任何坑。

**边界（git 2.43.0 实测）**：有 submodule 也不是"一碰就炸"——在 worktree 里**从零**
`git submodule update --init` 会走 worktree 私有的 submodule gitdir，主仓库不受影响；
真正劫持主工作区的是"先给 submodule `git worktree add` 挂上共享 gitdir、再 `submodule update`"
那条路。用 `worktrunk` 之类第三方 worktree CLI 建 worktree 不改变这个结论（底层就是
`git worktree add`）。**默认仍选独立 clone**：私有 gitdir 让每个 worktree 各存一份 submodule 对象，
且并发 session 里有人走上述共享 gitdir 的路径，可能波及其他工作区。独立 clone 避开的是
这类配置冲突；其对象借用风险仍需按[对象依赖](#object-lifetime)处理。实测矩阵见
[worktree 私有的 submodule gitdir](submodule-hazards.md#private-gitdir)。

> 机理、实测现场、五个坑、诊断与恢复流程见
> [submodule 与 worktree 的冲突](submodule-hazards.md)。
> 已有 worktree 必须就地修好时，那里也给了权宜之计。

### 任务依赖的 submodule 范围

按任务实际会读取、测试或构建的内容决定初始化范围，而不是只看是否编译。文档主题、Python 测试数据和 CI 脚本也可能位于 submodule 中。

| 任务类型 | 要 submodule 吗 |
|---|---|
| 改文档 / 配置 / 脚本 / CI / Markdown | 仅在依赖子模块内容时初始化相关路径 |
| 只跑 Python 测试、只读代码、只改注释 | 检查导入、测试数据和所读代码的位置 |
| 要 `make` / `ninja` / `cmake` / 链接依赖库 | 初始化构建实际依赖的路径 |

SU2-Quantum 原先采用持续借用对象的 clone 时，记录的成本差距：

| | 耗时 | 真实增量占盘 |
|---|---|---|
| 带 `--recurse-submodules` | 1 分 37 秒 | +122 MB |
| **不带**（docs 类任务） | **1.17 秒** | **+1 MB** |

这次记录相差约 **83 倍时间、122 倍空间**；其中 `mkdocs build` 成功产出 62 个页面。
这些是该项目和原先借用模式的结果，不能作为改用 `--dissociate` 后的耗时 / 占盘保证。

> 真实教训：本文记录的那次事故，起因是为一次**纯 markdown 的 cherry-pick**
> 无条件给 27 个 submodule 建了工作区并跑了 `git submodule update`，导致主工作区的
> `externals/eigen` 被指向别的目录、`git submodule status` 报错。按需触发本可以完全避免。

## <a id="shared-clone"></a>独立 clone 与对象借用

### 建立

以下示例假定主仓库当前位于一个已提交的分支；detached HEAD 或未出生分支需先明确基准提交，不把 `HEAD` 当作分支名。

```bash
MAIN_REPO=$(git rev-parse --show-toplevel)          # 或见「动态推导主仓库路径」
TIMESTAMP=$(date +%Y-%m-%dT%H-%M-%S)
# 目录名用 .clones/ 而非 .worktrees/（见下方「命名约定」）
NEW="$(dirname "$MAIN_REPO")/$(basename "$MAIN_REPO").clones/cli-clone-$TIMESTAMP"
BRANCH_NAME="cli/clone-$TIMESTAMP"
BASE=$(git -C "$MAIN_REPO" rev-parse --abbrev-ref HEAD)

# 按需：任务依赖子模块内容时才递归初始化；也可之后按路径初始化
NEED_SUBMODULES=0
[ "$NEED_SUBMODULES" = 1 ] && RECURSE=(--recurse-submodules) || RECURSE=()

mkdir -p "$(dirname "$NEW")"
git -c submodule.alternateLocation=superproject \
    -c submodule.alternateErrorStrategy=info \
    clone --reference "$MAIN_REPO" --dissociate "${RECURSE[@]}" \
          --branch "$BASE" "$MAIN_REPO" "$NEW" || exit 1

cd "$NEW" || exit 1
git checkout -b "$BRANCH_NAME" || exit 1
# 别让 origin 指着本地仓库（主仓库没有 origin 时跳过）
UP=$(git -C "$MAIN_REPO" remote get-url origin 2>/dev/null) && [ -n "$UP" ] && git remote set-url origin "$UP"
# 再留一条指回主仓库的 remote——origin 改指上游后就够不着主仓库了（见「分支流转」）
git remote add local "$MAIN_REPO"
```

要点：

- `--reference` 利用参考仓库减少获取成本，`--dissociate` 在 clone 完成时复制所需的借用对象。
  代价是占用本地空间，不能继续承诺“几乎不复制”。
- `submodule.alternateLocation=superproject` 允许 submodule 初始化时根据超项目的 alternates
  推导参考位置；`alternateErrorStrategy=info` 允许推导失败时提示并退回正常 clone。
  它们不负责保留源对象，也不是备份策略。
- 每个 submodule 都是另一个仓库。完成递归初始化后，以及以后补初始化时，都应逐个检查
  `git rev-parse --git-path objects/info/alternates` 指出的文件；仍有借用时按
  [解除依赖](#detach-objects)处理，不凭超项目的一个 flag 推定所有子仓库都已独立。

> submodule 参数见 [Git 2.43 · alternateLocation / alternateErrorStrategy](https://github.com/git/git/blob/v2.43.0/Documentation/config/submodule.txt#L96-L110)。
> Git 2.47.3 的隔离样例中，上述递归 clone 完成后超项目与已初始化子仓库均没有活动 alternates，
> 且 `git fsck --full` 通过；这是该版本样例，不替代其他版本和后续初始化的检查。

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

clone 的 refs 独立，在 clone 的 `main` 上提交会使两边同名分支分别前进。worktree 的默认限制
是不能在两处同时 checkout 同一分支，并非禁止在 `main` 上提交。使用专属分支可减少命名冲突，
但[搬回主仓库](#branch-flow)前仍应检查目标分支是否已经存在。

### <a id="branch-flow"></a>分支流转

独立 clone 的 refs 不会自动同步，成果需要显式传递（见[共享的层级](#mechanism-compare)）。
alternates 是单向的对象查找依赖：借用方可能从源端读到已有对象，但借用方新建的对象不自动
出现在源端。`fetch` 是否传对象取决于接收方缺什么，不能保证两个方向都只更新 ref。
使用 `--dissociate` 后，同样按正常独立仓库的缺失对象进行传输。

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

任务后来需要 submodule 时可以补初始化；完成后同样检查新子仓库的对象依赖：

```bash
cd "$NEW"
git -c submodule.alternateLocation=superproject \
    -c submodule.alternateErrorStrategy=info \
    submodule update --init --recursive
```

原先持续借用模式下补做的记录为 2 分 40 秒（初始递归 clone 为 1 分 37 秒），
24 条 alternates、异常 0、增量 +122 MB，未观察到主工作区配置变化。
这并不证明借用方能承受源对象被回收；新初始化的子仓库有活动 alternates 时，继续执行
[解除依赖](#detach-objects)。

### <a id="object-lifetime"></a>占盘与对象依赖

SU2-Quantum 实测（11 个顶层 + 16 个嵌套 submodule，主仓库 `.git` = 3.4G）：

| 指标 | 结果 |
|---|---|
| **真实增量占盘** | **+122 MB**（3535 MB → 3657 MB，约 3.4%） |
| 建立的 alternates | 24 条，含四层嵌套的 `CoolProp/.../pymcx/externals/pybind11` |
| `submodule status --recursive` | 24 个全绿，异常 0 |

> ⚠️ **别用 `du -sh <新clone>/.git` 量占盘**，它会把硬链接重复计数（这里报 2.9G，实际只多占
> 122 MB）。正确的测量方式：`du -cs <主>/.git <新>/.git` 的合计减去 `du -s <主>/.git`。

原先实测的共享方式及其边界如下：

| 层 | 当时观察 | 能保留什么 |
|---|---|---|
| 超项目 | alternates ＋ pack 硬链接（8/8 个 pack `st_nlink=2`） | 已有硬链接对应的文件不会因源路径删除而消失；不保证后续借用的新对象也有本地副本 |
| submodule | 仅 alternates（24 条，0 个硬链接） | 未复制的对象依赖源对象库持续可达且不被回收 |

“源仓库常规使用没问题”不是可靠保证：在源端变成不可达的对象，可能在后续正常命令触发的
自动维护中被移除，源端不会检查其他 clone 的分支。源端已有 pack 的硬链接不能保护未来的
所有对象；也不能把普通 clone 的配置隔离称为完整备份隔离。

> Git 2.47.3 的隔离回归：按原 `clone --reference` 方式建副本，再从源端获取后续提交；
> 源端移除该提交的引用、过期 reflog 并回收对象后，借用副本读取该提交失败。
> 提前 `--dissociate` 的副本及先补齐对象再解除 alternates 的副本仍可读取。
> 回收操作只用于一次性测试仓库，不应照搬到实际主仓库来“验证安全”。

### <a id="detach-objects"></a>解除已有对象借用

在源对象仍完整可读、没有并发回收且本地空间充足时，先复制当前仓库需要的对象，
再移走 alternates，最后在没有该依赖的情况下检查完整性。不要先移走 alternates，也不要
用 `repack --local` 代替这里的 `repack -a`。

```bash
cd "$NEW" || exit 1
git repack -a || exit 1
alt=$(git rev-parse --git-path objects/info/alternates) || exit 1
if [ -f "$alt" ]; then trash-put "$alt" || exit 1; fi
git fsck --full || exit 1

git submodule foreach --recursive '
    git repack -a &&
    alt=$(git rev-parse --git-path objects/info/alternates) &&
    { [ ! -f "$alt" ] || trash-put "$alt"; } &&
    git fsck --full
' || exit 1
```

`foreach` 只访问已 checkout 的子模块，不覆盖未初始化或失效注册的仓库；以后初始化仍需检查。
这里也只解除 alternates 依赖，不承诺恢复已经丢失的对象、保存不可达历史，或取消 partial clone
的 promisor 远端依赖。某一步失败就停止，不继续清理源端；保留日志以便从其他完整副本恢复。

> `repack -a` 解除借用的依据见 [Git 2.43 · git-clone](https://git-scm.com/docs/git-clone/2.43.0)。
> 空间会随实际复制的对象增加；历史案例的全量对象约 3.4G，仅作该环境的容量参考。

### 拆除

```bash
trash-put "$NEW"     # 核对未提交内容和未传出的分支后，移至回收站
```

分支保存在这个 clone 自己的仓库里。移走目录前，检查未提交内容、未传出的分支，
并按[分支流转](#branch-flow)转移成果；不要依赖别的仓库“已经共享对象”来保证这些成果存在。

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

## <a id="worktrunk"></a>worktrunk：worktree 生命周期的 UX 层

[worktrunk](https://github.com/max-sixty/worktrunk)（`wt` 命令）是个第三方 CLI，装了它可以少敲上面那些命令。
**它不改变本文的选型判据**——建 worktree 这步与 `git worktree add` 等价，官方 FAQ 自己也把对比
框在"手动生命周期管理"上，并写明 *"Worktrunk runs `git` commands internally"*；读 v0.71.0 源码，
建 worktree 那条命令就是 `git worktree add [-b <分支>] -- <路径> [<基准>]`，没有任何 submodule 处理。

它省掉的是重复劳动（下列除注明外为 v0.71.0 实测）：

| 手动做 | `wt` 里 |
|---|---|
| 建完还得自己 `cd` 过去 | `wt switch` 真能改当前 shell 的 cwd——外部子进程改不了父 shell，靠往 rc 文件注入 shell 函数实现 |
| `git worktree remove` + `git branch -d` 两步 | `wt remove` 一步；**含已初始化 submodule 的 worktree 原生 git 直接拒绝**（`fatal: working trees containing submodules cannot be moved or removed`），`wt remove` 能删干净 |
| 每建一个都手动装依赖 / 复制 `.env` | 10 种生命周期 hook（`pre-start`/`post-start`/`pre-merge`…）写进项目级 `.config/wt.toml`；`wt step copy-ignored` 直接从别的 worktree 复制 gitignored 文件（依赖目录、缓存、`.env`），可用 `.worktreeinclude` 限定范围 |
| `git worktree list` 只给路径 + HEAD | `wt list` 带 ahead/behind、暂存、最后提交的状态表 |
| checkout 主干 → merge → push → 删 worktree | `wt merge` 一条命令走完 squash → rebase → 合并 → 清理 |

它**不**改变的：

- **选型不变**：有 submodule 仍默认[独立 clone](#shared-clone)。它的官方 reference 全文**零次**提到 submodule，
  实测也确认它对 submodule 不做任何处理，[劫持](submodule-hazards.md#core-worktree-hijack)照样发生。
- **省下载靠的仍是 alternates**：worktree 那条路每个工作区各存一份 submodule 对象，与用不用 `wt` 无关。
- **命名约定不同**：默认路径模板是兄弟目录 `<仓库名>.<分支名>`，与本文的
  `<仓库名>.worktrees/cli-worktree-<时间戳>` 不一致；要对齐得改它的路径模板配置。

所以定位是"可选加速层"：装了就用，没装照走上面的流程，本文的步骤不依赖它。
它自己的配置、hook 选型与排障有官方配套的 `worktrunk` skill（本仓已嫁接），本文不重复。

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