# jj（Jujutsu）：模型、分支、操作日志、一等冲突与 Git 互操作

[jj（Jujutsu）](https://github.com/jj-vcs/jj) 是一个 **Git 兼容**的版本控制器：用 Git 仓库当后端存对象，协作者甚至不知道你没在用 `git`。本文从 jj 自己的模型讲起，按"概念 → 分支 / 日常操作 → 与 Git 的关系 → 文件安全"的顺序展开，力求读完能自洽地回答"这东西怎么用、跟 git 差在哪、我的东西会不会丢"。

本文与本 skill [git-surgery.md 的 jj 小节](git-surgery.md#jj-no-index) 同源但侧重不同：那边把 jj 当作"git 精准手术做不到时的另一条路"来对照；这里是 jj 模型的完整介绍。**下文标"实测"的行为均在 jj 0.43.0 上验证**；官方文档 / 源码链接锁到 v0.43.0。

## <a id="overview"></a>概述：jj 是什么、和 Git 的关系

jj 不是"git 的皮肤"，是另一套工作模型，只是**借 Git 仓库当存储后端**：它造的 commit 就是普通 git commit，能推到任意 git 远端，队友用纯 `git` 也照常协作。

> [git-compatibility](https://github.com/jj-vcs/jj/blob/v0.43.0/docs/git-compatibility.md) 开篇：*"One of them uses a regular Git repo, which means that you can collaborate with Git users without them even knowing that you're not using the `git` CLI."*

相对 Git，四个要先建立的心智转变（后面各有专节）：

1. **没有暂存区（index）**：工作副本本身就是一个自动提交的 commit，记作 `@`（见 [工作副本 `@` 与暂存区](#model)）。
2. **change ≠ commit**：每个 commit 带一个**稳定的 change-id**；重写（rebase / describe / squash…）产生新 commit-id，但 change-id 不变（见 [change 与 commit](#change-commit)）。
3. **分支叫 bookmark**，且行为和 git 分支有关键差异——**不随新 commit 自动前进**（见 [分支操作](#bookmarks)）。
4. **两条历史**：提交图（`jj log`）之外，还有**操作日志**（`jj op log`）记录你敲的几乎每一条命令，可整仓 `jj undo`（见 [两条历史](#op-log)）。

外加一个和 Git 差别很大的特性：**冲突是"一等公民"**，能存进 commit、延迟解决，rebase 不阻塞（见 [一等冲突](#conflicts)）。

## <a id="terms"></a>核心术语速查

后文要用的词，先一次性摆清（定义取自官方 [glossary](https://github.com/jj-vcs/jj/blob/v0.43.0/docs/glossary.md)）：

- **commit / revision**：某时刻文件快照（一棵 tree）+ 元数据（作者、时间、父指针）。两词同义。
- **change / change-id**：*change* = 一个 commit 跨"重写"演化的身份；change 本身在数据模型里不是对象，只有 **change-id** 是——它是 commit 的一个属性，`jj log` 里显示为行首那串 z–k 字母。
- **commit-id**：commit 的哈希（用 Git 后端时就是 git commit id），`jj log` 里显示在行尾。
- **`@`（working-copy commit，工作副本 commit）**：对应工作副本当前状态的 commit，每个 workspace 一个。
- **rewrite（重写）**：造一个内容 / 元数据 / 父不同的新版本 → **新 commit-id、同 change-id**。改工作副本、`describe`、`rebase`、`squash` 都是重写。
- **可见 / 隐藏 commit**：`jj log` 默认只显示可见 commit；被 abandon 或被重写的旧版变"隐藏"，仍可用 commit-id、或 change-id + 偏移（`xyz/1`）访问。
- **bookmark（书签）**：指向某 commit 的命名指针，类似 Git 分支。**无"当前 bookmark"，不随新 commit 移动**；被指 commit 被重写时才跟随。
- **匿名分支（anonymous branch）**：没有 bookmark 指着的 commit 链。与 Git 不同，jj 会保留它们直到你显式 `abandon`。
- **operation / op log / view**：一次 *operation* = 某命令结束时整仓（可见 commit + bookmark + 各 `@`）的快照 *view* + 元数据；*op log* = 这些 operation 组成的 DAG。
- **root commit**：每个仓库虚拟的根，commit-id 全 `0`、change-id 全 `z`，revset 里是 `root()`。
- **workspace**：一个工作副本 + 关联仓库，相当于 Git 的 worktree。

## <a id="model"></a>工作副本 `@` 与暂存区

jj **没有暂存区（index）**。工作副本本身就是一个**自动提交**的 commit，记作 `@`；每跑一条 jj 命令，它先把当前文件系统状态快照进 `@` 再干活。

> [git-comparison](https://github.com/jj-vcs/jj/blob/v0.43.0/docs/git-comparison.md#the-index) 原文：*"There's no index (staging area). Because the working copy is automatically committed…"*

后果：

- **下一条 jj 命令会先把工作副本快照进 `@`**——不用 `git add`。改动一旦被快照就进了版本控制（不是游离在工作区外的"未跟踪脏改动"）；但快照是**懒的**：从你编辑到下一条 jj 命令跑起来之前，改动只在文件系统里、还没进 `@`（实测：编辑后 `jj --ignore-working-copy file show -r @` 仍是旧内容，跑一条 `jj status` 才更新）。`.gitignore` 忽略的、以及超大新文件不会被自动纳入。对"不丢失"的意义见 [持久性与恢复](#durability)。
- **`jj diff` 默认比的是父 commit → `@`**（合并提交则以各父树自动合并的结果为基线）；`jj split` / `jj squash -i` 从"父→`@`"的全量改动里挑子集，选中的**就是提交的全部**，没有第三方对象藏预暂存内容。
- colocated（`.jj` 与 `.git` 并存于同一目录、共享工作副本，`jj git init` 默认如此）下 jj **无视 `.git/index`**（Git 的暂存区被忽略）。

> [git-compatibility](https://github.com/jj-vcs/jj/blob/v0.43.0/docs/git-compatibility.md) 原文：*"Staging area: Kind of. The staging area will be ignored."*、*"Hooks: No."*（[issue #405](https://github.com/jj-vcs/jj/issues/405)）——靠 pre-commit / commit-msg 框架的团队用 jj 提交会被静默绕过。

## <a id="change-commit"></a>change 与 commit：change-id 稳定、commit-id 随重写变

每个 commit 同时有**两个 ID**，`jj log` 一行的头尾各一个：

- **change-id**（行首，z–k 字母）：这个"改动"的稳定身份。
- **commit-id**（行尾，十六进制）：具体这一版对象的哈希，就是 git commit id。

**重写（rewrite）= 造一个新 commit**：改内容、改消息（`describe`）、换父（`rebase`）、`squash`、乃至改工作副本，都会生成**新的 commit-id**，但 **change-id 保持不变**。

> [glossary#rewrite](https://github.com/jj-vcs/jj/blob/v0.43.0/docs/glossary.md#rewrite) 原文：*"Rewriting a commit results in a new commit, and thus a new commit ID, but the change ID generally remains the same."*

为什么这对 jj 很关键：你可以一直用 **change-id 指代"这个改动的最新版"**，哪怕它被 rebase 了十次、commit-id 换了十次。[bookmark 跟随重写](#bookmarks)、[一等冲突的 auto-rebase](#conflicts) 都建立在这条上。实测：`jj describe -r <rev>` 改条消息后，该 commit 的 change-id 不变、commit-id 变（例如 `8812c0f7 → a31dd20c`）。

**隐藏 commit 不等于消失**：被 abandon 或被重写掉的旧版会变"隐藏"，`jj log` 默认不显示，但仍可用它的 commit-id、或 `change-id + 偏移`（最新版是 `xyz/0`、上一版 `xyz/1`……）访问和恢复。

> [glossary#visible-commits](https://github.com/jj-vcs/jj/blob/v0.43.0/docs/glossary.md#visible-commits)：隐藏 commit *"is still accessible by its commit ID or the combination of its change ID and a change offset."*

## <a id="bookmarks"></a>分支操作：bookmark 与匿名分支

jj 里"分支"分两种：有名字的 **bookmark**（≈ git 分支）和**匿名分支**（没名字的 commit 链）。日常"开分支、切换、推分支"都落在这一节。

### bookmark 与 git branch 的关键差异

bookmark 是指向某 commit 的**命名指针**，可以拿它当 revision 用——`jj new main` 就是在 `main` 上开新 commit。

> [bookmarks](https://github.com/jj-vcs/jj/blob/v0.43.0/docs/bookmarks.md) 原文：*"Bookmarks are named pointers to revisions (just like branches are in Git)."*

git 用户最容易栽的三点差异（均实测）：

- **没有"当前 / 检出的 bookmark"**：jj 没有"我在 X 分支上"这个状态。
  > [glossary#bookmark](https://github.com/jj-vcs/jj/blob/v0.43.0/docs/glossary.md#bookmark)：*"there is no concept of a 'current bookmark'; bookmarks do not move when you create a new commit."*
- **新建 commit 不会推进 bookmark**：实测 `jj bookmark create feat`（默认落在 `@`）后再 `jj new` 造新 commit，`feat` 仍停在原处、**不前进**——要动它得手动 `jj bookmark set` / `move`。这跟 git「在分支上 commit、分支尖自动前移」完全相反。
- **被指 commit 被重写时 bookmark 跟随；被 abandon 时 bookmark 删除**：实测 `jj describe -r feat` 重写后 `feat` 跟到新 commit（change-id 不变、commit-id 变）；`jj abandon` 掉它所指 commit 后，`feat` 直接从列表消失。
  > [bookmarks#bookmark-updates](https://github.com/jj-vcs/jj/blob/v0.43.0/docs/bookmarks.md#bookmark-updates)：重写 → *"bookmarks and the working-copy will move along with it"*；abandon → *"all associated bookmarks will be deleted"*。

### 常用命令

- `jj bookmark create <名字> [-r <rev>]`：创建，**默认 `-r @`**（落在当前工作副本 commit）。
- `jj bookmark set <名字> -r <rev>` / `jj bookmark move`：手动移动到某 commit（往回移加 `--allow-backwards`）。
- `jj bookmark delete` / `rename` / `list`（`--all` 连远端、`--tracked` 只看已跟踪）。
- 简写：`jj b` + 子命令首字母，如 `jj b c <名字> -r@`（实测可用）。
  > [bookmarks#ease-of-use](https://github.com/jj-vcs/jj/blob/v0.43.0/docs/bookmarks.md#ease-of-use)。

### 在一条线上干活 / 匿名分支

- 典型流：`jj new <起点>` 开新工作 → 编辑（自动进 `@`）→ `jj describe -m "..."` 写描述 → 需要个名字时再 `jj bookmark set <名字> -r @`。**先干活、后命名**是 jj 的常态。
- 不打 bookmark 也完全能用——这就是**匿名分支**：jj 保留所有 head，`jj log` 都看得到，不像 git 会被 GC 掉。
  > [glossary#anonymous-branch](https://github.com/jj-vcs/jj/blob/v0.43.0/docs/glossary.md#anonymous-branch)：*"Jujutsu keeps commits on anonymous branches around until they are explicitly abandoned."*
- 导航：`@` = 当前工作副本、`@-` = 其父；`jj new <rev>` 在某 commit 上开新的、`jj edit <rev>` 直接跳去编辑某个已存在 commit。

### 映射到 Git 分支、远端与 tracked bookmark

- **映射**：`jj git push --bookmark foo` 把 `foo` 推成远端的 `foo` 分支；colocated 下 git 分支 ↔ jj bookmark 每条命令自动 import / export。
- **远端位置**：`<bookmark>@<remote>`（如 `main@origin`）是 jj 记住的该 bookmark 在远端的最后位置，等价于 git 的 remote-tracking branch。
- **tracked（跟踪）vs 非 tracked**：`jj git clone` 会自动把默认远端 bookmark 设为 tracked；你 push 出去新建的 bookmark 也自动 tracked；但其余 `jj git fetch` 拉到的远端 bookmark **默认不 track**，得 `jj bookmark track <名字>@<remote>` 之后，本地 bookmark 才会随 fetch 更新。
  > [bookmarks#remotes-and-tracked-bookmarks](https://github.com/jj-vcs/jj/blob/v0.43.0/docs/bookmarks.md#remotes-and-tracked-bookmarks)。
- **更新远端 = 先本地移 bookmark 再 push**。本地 bookmark 与某远端指向不同时，`jj log` 会在名字后加 `*`（如 `main*`）提醒你可能要 push。

### push 安全检查与 bookmark 冲突

- **push 前的安全检查**（≈ `git push --force-with-lease`）：远端实际位置须匹配 jj 记录的最后位置，否则拒推（要先 `jj git fetch` 解冲突）；本地 bookmark 不能是 conflicted；远端已存在的 bookmark 须是 tracked。
  > [bookmarks#pushing-bookmarks-safety-checks](https://github.com/jj-vcs/jj/blob/v0.43.0/docs/bookmarks.md#pushing-bookmarks-safety-checks)。
- **bookmark 冲突**：本地和远端都移动了同一 bookmark，fetch 后本地 bookmark 进入 conflicted 态，`jj log` 显示成 `main??`，此时 `jj new main` 会因"解析到多个 revision"报错。解法：`jj bookmark set` 到你想要的目标，或 `jj git fetch` 让远端侧的解决传播过来。
  > [bookmarks#conflicts](https://github.com/jj-vcs/jj/blob/v0.43.0/docs/bookmarks.md#conflicts)。注意这是**bookmark 指针的冲突**，与下文[文件内容的一等冲突](#conflicts)是两回事。

## <a id="op-log"></a>两条历史：操作日志（op log）与提交图（jj log）

jj 有两条互相独立的历史，别混：

| | 提交图 `jj log` | 操作日志 `jj op log` |
|---|---|---|
| 记的是 | change/commit 的 DAG（内容历史，和 Git 一样） | **每一条改动仓库的命令**（元历史） |
| 一个节点 | 一个 commit | 一次操作，含当时整仓的快照视图（view：各 bookmark/tag/Git ref 指向、heads、各 workspace 的 `@`） |
| 长出新节点 | `jj commit` / `jj new` 等显式建 commit 时 | 修改仓库、或把工作副本改动快照进 `@` 的操作；**纯只读、无改动的命令不新增**（实测连跑两次 `jj log`，op ID 不变） |
| 随 `git push` 走? | 推送的 bookmark/tag 可达的 commit 会走（见 [传播边界](#local-vs-pushed)） | **不会，纯本地** |

`jj op log` 里典型能看到 `snapshot working copy`、`commit …`、`describe commit …`、`abandon commit …`、`rebase …` 这些条目——你编辑文件但还没 `jj commit`，也会留下一串 `snapshot working copy`。

操作日志给你三件事（[operation-log](https://github.com/jj-vcs/jj/blob/v0.43.0/docs/operation-log.md)）：

- `jj undo`：撤销上一条操作。
- `jj op restore <op>`：把整仓恢复到某次操作结束时的样子（新建一次操作，不改写历史）。
- `jj --at-op=<op> <命令>`：把仓库**当成停在那次操作**来跑（一般配只读命令如 `jj log` / `jj diff` / `jj file show`）。`--at-op` 下**不做自动快照**；跑变更命令也允许，等价于从那点发起一次并发操作。

> jj 0.43.0 的 `jj op` 子命令：`log` / `restore` / `revert` / `show` / `diff` / `abandon` / `integrate`。

### 命名一个版本：op log 上贴标签 vs 建一个 commit

想"标记 / 命名当前状态"时，有两个落点，代价不同——这也解释了为什么"命名"这个动作在 jj 里没有唯一答案：

- **贴在 op log 上**（比如上层应用自存一份 名字 → op-id 映射）：op log 本就是一条连续时间线，命名只是给某个 operation 贴星标；心智简单、一条线到底，回退统一 `jj op restore`。代价：命名点是 *operation* 不是 commit，`jj diff` 不认 op（要用 `jj op diff`）。
- **建成真 commit**（`jj commit -m "名字"`）：命名版本进 `jj log`，是一等 commit、原生可 `jj diff`、持久。代价：时间线出现**两条轴**——提交图（只含你显式建的里程碑 commit）与 op log（含其间每次自动快照）；且每次 commit 划出一道**提交边界**，之后编辑落到新 commit，回头改那个命名版本就属于"改历史 commit"（其后代 auto-rebase、commit-id 全换、change-id 不变）。

### 编辑→commit 循环里能 diff / 回退到哪

顺着"编辑→快照→`commit` 里程碑→再编辑→再 `commit`"走一圈，会看到两轴的直接后果：里程碑（你 `commit` 的那几个）进 `jj log`，里程碑**之间的中间态只在 op log**。于是：

- **命名里程碑之间**：`jj diff --from <里程碑A> --to <里程碑B>` 干净直接（都是 commit）。
- **到一个没建成 commit 的中间态**（两次 `jj commit` 之间某次自动快照）：它不在 `jj log`——`jj diff --from <op-id>` 会报 `Revision doesn't exist`（op 不是 commit）。只能走操作日志：`jj --at-op=<op> file show <path>` 看内容、`jj op diff --from A --to B -p` 或 `jj op show -p` 看某操作的文件级改动，或 `jj op restore <op>` 整仓倒回去。

> 附带好处：操作日志给了**无锁并发**——多个 jj 命令（甚至跨机器经分布式文件系统）同时跑不会损坏仓库，冲突会在随后的 `jj st` / `jj log` 里以 divergent 提示出来。见 [operation-log](https://github.com/jj-vcs/jj/blob/v0.43.0/docs/operation-log.md)。

## <a id="conflicts"></a>一等冲突（first-class conflicts）

Git 撞冲突会**当场阻塞**：`git rebase` 停在半途、进入模态 `rebase in progress`、退出码非 0，逼你 `git add` + `git rebase --continue` 或 `--abort`，否则寸步难行。

jj 把冲突**当数据存进 commit**，rebase **不阻塞**：

> [conflicts](https://github.com/jj-vcs/jj/blob/v0.43.0/docs/conflicts.md) 原文：*"if you rebase a commit and it results in a conflict, the conflict will be recorded in the rebased commit and the rebase operation will succeed. You can then resolve the conflict whenever you want."*

实测：改一个已提交里程碑、其后代自动 rebase 撞冲突时——

```
$ jj status          # 触发对被改 commit 的重写 + 后代 auto-rebase
Rebased 1 descendant commits onto updated working copy   # 退出码 0，不阻塞
$ jj log
×  kyvlmzqt … (conflict)   # 冲突"停"在这个 commit 里，人可以在别处继续
```

- **冲突进 commit、不打断流程**：`jj log` 里该 commit 标 `×  (conflict)`，你（`@`）照样能造新 commit、干别的活（实测退出码 0），想解的时候再 `jj edit <该 commit>` 手动改掉标记 → 冲突消失。等于把解冲突**延迟到你自己定的时刻**。
- **auto-rebase**：重写某 commit 后，其后代自动跟着重写（change-id 稳定、commit hash 变，见 [change 与 commit](#change-commit)）。一等冲突正是它的地基——后代 rebase 撞冲突也不会中断。
- **省掉 `--continue` 那套**：jj 的解冲突就一个套路——checkout 冲突 commit、改、amend；没有 `rebase/merge/cherry-pick --continue` 的状态机。

> conflicts.md 的 Advantages 里明确列了 *"Allows you to postpone conflict resolution until you're ready for it."*

存进 commit 的是冲突的**逻辑表示**（多棵 tree 的加减），不是文本 `<<<<<` 标记；只有在工作副本 materialize（`jj new`/`jj edit` 到该 commit、或 `jj show` 它）时才渲染成标记。

## <a id="conflict-in-git"></a>冲突与 change-id 在 Git 层的表示

jj 的 rebase 走**它自己的引擎、不经过 git**，这正是它能不阻塞的根。那这些 jj 专有的东西**落到 Git 对象里长什么样**、纯 git 的协作者看到啥——实测（colocated 仓库、纯 `git` 查看）：

**冲突 commit**。`git ls-tree` 一个冲突 commit 的顶层树：

```
040000 tree …   .jjconflict-base-0
040000 tree …   .jjconflict-side-0
040000 tree …   .jjconflict-side-1
100644 blob …   JJ-CONFLICT-README
100644 blob …   f.txt          # 冲突文件被 materialize 成"其中一侧"的干净内容
```

- 普通 `git show <commit>:f.txt` 看到的是**单边内容、没有冲突标记**（冲突标记只在 jj 侧 materialize——把逻辑冲突渲染成 `<<<<<` 文本——或 jj 的 diff 输出里出现）；不过同一 commit 用 `git ls-tree` / 读 `JJ-CONFLICT-README` / `git cat-file` 仍能认出这是 jj 的特殊表示。
- 权威的冲突信息在一个**非标准 commit header** `jj:trees`（列出那几棵 tree）里；`.jjconflict-*/` 目录只是为了防 Git GC 掉这些 tree。
- `JJ-CONFLICT-README` 明说：*"This commit was made by jj … contains file conflicts, and therefore looks wrong when used with plain Git … Use `jj abandon` to recover."*

> [git-compatibility#format-mapping-details](https://github.com/jj-vcs/jj/blob/v0.43.0/docs/git-compatibility.md#format-mapping-details)：*"Commits with conflicts cannot be represented in Git. They appear in the Git commit as root directories called `.jjconflict-base-*/` and `.jjconflict-side-*/` … the authoritative information is in a non-standard `jj:trees` commit header."*

**change-id 的 git 层表示**（概念见 [change 与 commit](#change-commit)）。它写进 Git commit 的**非标准 header**（reverse-hex）：

```
$ git cat-file -p <commit>
tree …
parent …
author …  committer …
change-id nslxztpwoutwxsztmuowltmpvkokuyxp   ← jj 盖的指纹
<空行>
C2
```

- 默认写入（自 jj 0.30.0），可用 `git.write-change-id-header` 关掉。
- **`git show` / `git log` 不显示这个 header**，只有 `git cat-file -p` 看得到——但它在对象里、被算进 commit hash，随对象进每个 clone。所以用纯 git 的协作者**能查出你用了 jj**。
- 它**过一次普通 `git rebase` 就没了**（rebase 不保留非标准 header）；`git commit --amend` 会保留；GitHub 等大平台大多保留。

> 出处同上 [git-compatibility#format-mapping-details](https://github.com/jj-vcs/jj/blob/v0.43.0/docs/git-compatibility.md#format-mapping-details)。

**`refs/jj/keep/*`**：jj 创建的 commit 都挂一条 `refs/jj/` 下的 ref 防 GC（实测 `git for-each-ref` 能看到一堆 `refs/jj/keep/<hash>`）。

**别把冲突交给 Git 用户**。conflicts.md 自己提醒：一等冲突可以共享，但*"you probably shouldn't do if some people interact with your project using Git"*——而且 `jj git push` 直接不让推冲突 commit（见 [传播边界](#local-vs-pushed)）。

## <a id="local-vs-pushed"></a>留在本地的数据与随 `jj git push` 传播的数据

**只有 `jj git push` / `jj git fetch` / `jj git clone` 碰远端。** 别的操作全留在本地，直到你显式 push。下表按操作分类（实测）：

| 操作 | 作用 | 进 git（随 push）? |
|---|---|---|
| `jj op log` / `op restore` / `undo` | 操作时间线 & 时光机 | ❌ 纯本地，永不 push |
| 工作副本自动快照 | 每条命令 snapshot `@` | ❌ 本地 |
| `new` / `describe` / `commit` / `split` / `squash` / `rebase` / `edit` / `abandon` | 改提交图、重写、抛弃实验 | ❌ 本地，直到 push |
| 一等冲突 | 冲突存进 commit | ❌ 本地；`jj git push` 还会**拒推**（但纯 `git push` 不拦，见下） |
| `bookmark create` / `set` / `move` | 命名指针 | ❌ 本地，直到 push |
| `jj git push` / `fetch` / `clone` | 和远端交换 | ✅ 只有这三个碰 git |

**`jj git push` 的拒推校验**：遇到不满足条件的 commit 直接拒推。实测两种：

```
Error: Won't push commit <id> since it has conflicts
Error: Won't push commit <id> since it has no description
```

> 校验器完整拒推理由在源码 [`cli/src/commands/git/push.rs#L737-L752`](https://github.com/jj-vcs/jj/blob/v0.43.0/cli/src/commands/git/push.rs#L737-L752) 的 `CommitsValidator`：`has no description`（除非 `--allow-empty-description`）、`has conflicts`、`is private`（按 `git.private-commits`，除非 `--allow-private`）、`has no author and/or committer set`。注意这只是 `jj git push` 的**客户端**校验——colocated 下用**纯 `git push`** 推同一个冲突 commit **不受此拦**（实测 `git push` 退出 0、远端收到了，带着 `.jjconflict-*` 那套表示）。

**跨机复制两条路，差别巨大（实测）：**

- **走 git（`jj git clone` / fetch）**：搬 commit + bookmark + tags（+ 对象里那条 change-id header）。**操作日志不跟着走**——clone 出来的仓 `jj op log` 是全新的几条（add workspace / fetch / checkout），你原来那串快照 / 实验**拿不到**。change-id 倒是两边一致，即"内容身份"随 commit 走、"操作历史"不走。
- **拷贝整个仓库目录（rsync / tar）**：**操作日志一起带走**——`cp -r` 后 `jj op log` 原样完整。⚠️ 但 colocated（默认）下 git 对象在同级 `.git`、**不在** `.jj` 里，只拷 `.jj` 会因缺 `.git` 打不开（实测报 `repository appears broken`）——要拷就拷**整个仓库目录**。而且 jj 的**无锁并发**让不同机器的副本经 rsync / NFS / Dropbox 合并时**不丢改动**（新增 commit、移动的 bookmark 都在；分歧的 bookmark 以 `??` divergent 形式出现在 `jj log`），并非"互相覆盖"。已知坑：Git 后端非完全无锁、可能损坏仓库（[issue #2193](https://github.com/jj-vcs/jj/issues/2193)，`jj debug reindex` 可恢复），colocated 尤其未充分测试、可能丢 bookmark 指针（丢指针不丢 commit）。

  > 出处：[technical/concurrency.md](https://github.com/jj-vcs/jj/blob/v0.43.0/docs/technical/concurrency.md)。

**远端只能是 Git 远端**：`jj git remote add <name> <url>`，url 可 https / ssh / file，和 git 一样——因为底层就是 git 传输。**没有 jj 原生协议**把操作日志 / 快照同步出去；那层在设计上就是本地的。

## <a id="durability"></a>改动的持久性与恢复

这里说的"安全"是**文件 / 改动不丢失**，不是保密。jj 在"不丢"上比 Git 更难丢，但也有明确边界。

**为什么难丢：**

- **工作副本的改动会被快照进 `@`**（由下一条 jj 命令触发，不是实时）。Git 里"未 commit 的工作区改动"不受 reflog 保护，一发 `git reset --hard` / `git checkout` 就没；jj 里一旦被快照，它就是 `@` 这个 commit、进了 op 历史。注意快照前的编辑（还没跑任何 jj 命令）仍只在文件系统里、没被 jj 兜住。
- **每次操作都进操作日志**，连"破坏性"操作（`abandon` / `rebase` / `restore` / 改写）都能回退：`jj undo` 撤上一步、`jj op restore <op>` 整仓倒回、`jj --at-op=<op>` 先看清再决定。colocated 下**连误用的 `git` 命令都能撤**。

  > [git-compatibility](https://github.com/jj-vcs/jj/blob/v0.43.0/docs/git-compatibility.md) 原文：*"You can undo the results of mutating `git` commands using `jj undo` and `jj op restore`."*

- **被抛弃 / 重写掉的 commit 由 `refs/jj/` 钉住**，不会被 Git GC 顺手收走；仍可用 commit-id 或 change-id + 偏移找回（见 [change 与 commit](#change-commit)）。
- **操作日志默认保留、随时可 `jj undo` / `jj op restore`**，"事后捞回"很容易——但**不是永久**：要清旧历史，先 `jj op abandon ..<op>` 让旧操作不可达，再 `jj util gc`（默认修剪两周前的 obsolete 操作与对象；实测 abandon+gc 后 op log 从 11 条降到 2 条）。

**边界（别当备份用）：**

- 操作日志和 `.jj` 都是**本地、明文**的 jj 自有格式，**不加密**。谁能读你的文件系统就能读全你的完整过程——"不进远端" ≠ "对人保密"。
- **它不随 `git push` 走**（见上）。远端 / 别人的 clone 只有你 curate 后推出去的那些 commit；`.jj` 里的操作日志、失败实验、中间快照**不在异地**。真要抗"整台机器没了"，要么把 commit push 到远端（只有干净、带描述、非冲突的 commit 活下来），要么把**整个仓库目录**（含 `.jj` 与同级 `.git`）一起备份 / 拷走。
- `git gc`（对后端 Git 仓）据官方"应该安全但未充分测试，建议先整仓备份"；`jj util gc` 会修剪两周前的 obsolete 操作 / 对象并打包 refs，被 abandon、过期的旧态之后就没了。

## <a id="git-interop-limits"></a>与纯 Git 工具混用的限制

colocated（`.jj` + `.git` 并存）很方便让 build 工具照常认 Git 仓，但混用有代价（多数来自 [git-compatibility](https://github.com/jj-vcs/jj/blob/v0.43.0/docs/git-compatibility.md)，部分实测）：

- **不跑 Git hooks**（`Hooks: No.`）；**忽略 Git 暂存区**（`Staging area … will be ignored.`）。
- jj 命令常把底层 Git 置于 **detached HEAD**（jj 没有"当前跟踪分支"概念）；做变更型 `git` 命令前可能得先 `git switch` 告诉 Git 当前分支。建议混用时 `git` 只跑只读命令、变更交给 jj。
- **Git 工具看冲突 commit 会错乱**：看到 `.jjconflict-*/` 目录 + 单边文件（见 [Git 层表示](#conflict-in-git)）；误用 `git switch` 检出冲突 commit 后，`jj abandon` 可回到未解冲突态。
- **change-id 过普通 `git rebase` 会丢**（见上）。
- 不支持 LFS / submodule；shallow / partial clone 支持有限。pre-1.0，on-disk 格式在 1.0 前可能有破坏性变更。
