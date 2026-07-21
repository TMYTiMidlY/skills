# jj（Jujutsu）：working copy 即 commit、操作日志、一等冲突、与 Git 互操作

[jj（Jujutsu）](https://github.com/jj-vcs/jj) 是个 Git 兼容的版本控制器：用 Git 仓库当后端存对象，协作者甚至不知道你没在用 `git`。本文讲 jj **自身的模型**，以及几个容易踩错认知的点——操作日志、一等冲突、冲突与 change-id **在 Git 层怎么落地**、哪些数据留在本地不出机器、以及"改动不丢失"到底靠什么、边界在哪。

本文与本 skill [git-surgery.md 的 jj 小节](git-surgery.md#jj-no-index) 同源但侧重不同：那边把 jj 当作"当 git 精准手术做不到时的另一条路"来对照；这里从 jj 自己的模型讲起，偏重操作日志、冲突表示与文件持久性。**下文 jj 行为均在 jj 0.43.0 实测**；官方文档链接锁到 v0.43.0。

## <a id="model"></a>工作副本即 commit：`@` 与没有暂存区

jj **没有暂存区（index）**。工作副本本身就是一个**自动提交**的 commit，记作 `@`；每跑一条 jj 命令，它先把当前文件系统状态快照进 `@` 再干活。

> [git-comparison](https://github.com/jj-vcs/jj/blob/v0.43.0/docs/git-comparison.md#the-index) 原文：*"There's no index (staging area). Because the working copy is automatically committed…"*

后果：

- **改动一产生就在版本控制里**——不用 `git add`。你正在编辑的内容已经是 `@` 这个 commit 的一部分，不是游离在工作区外的"未跟踪脏改动"。这对"不丢失"很关键（见 [持久性与恢复](#durability)）。
- **`jj diff` 默认比的是父 commit → `@`**；`jj split` / `jj squash -i` 从"父→`@`"的全量改动里挑子集，选中的**就是提交的全部**，没有第三方对象藏预暂存内容。
- colocated 模式下 jj **无视 `.git/index`**（Git 的暂存区被忽略）。

> [git-compatibility](https://github.com/jj-vcs/jj/blob/v0.43.0/docs/git-compatibility.md) 原文：*"Staging area: Kind of. The staging area will be ignored."*、*"Hooks: No."*（[issue #405](https://github.com/jj-vcs/jj/issues/405)）——靠 pre-commit / commit-msg 框架的团队用 jj 提交会被静默绕过。

## <a id="op-log"></a>操作日志（op log）与提交图（jj log）

jj 有两条互相独立的历史，别混：

| | 提交图 `jj log` | 操作日志 `jj op log` |
|---|---|---|
| 记的是 | change/commit 的 DAG（内容历史，和 Git 一样） | **每一条改动仓库的命令**（元历史） |
| 一个节点 | 一个 commit | 一次操作，含当时整仓的快照视图（view：各 bookmark/tag/Git ref 指向、heads、各 workspace 的 `@`） |
| 长出新节点 | `jj commit` / `jj new` 等显式建 commit 时 | **几乎每条命令**（含自动快照 `@`） |
| 随 `git push` 走? | 会（见 [传播边界](#local-vs-pushed)） | **不会，纯本地** |

`jj op log` 里典型能看到 `snapshot working copy`、`commit …`、`describe commit …`、`abandon commit …`、`rebase …` 这些条目——你编辑文件但还没 `jj commit`，也会留下一串 `snapshot working copy`。

操作日志给你三件事（[operation-log](https://github.com/jj-vcs/jj/blob/v0.43.0/docs/operation-log.md)）：

- `jj undo`：撤销上一条操作。
- `jj op restore <op>`：把整仓恢复到某次操作结束时的样子（新建一次操作，不改写历史）。
- `jj --at-op=<op> <只读命令>`：把仓库**当成停在那次操作**来看（`jj log` / `jj diff` / `jj file show` 等）。`--at-op` 下**不做自动快照**。

> jj 0.43.0 的 `jj op` 子命令：`log` / `restore` / `revert` / `show` / `diff` / `abandon` / `integrate`。

一个直接推论：想 diff / 回退到一个**没建成 commit 的中间态**（比如两次 `jj commit` 之间某次自动快照），它不在 `jj log` 里——`jj diff --from <op-id>` 会报 `Revision doesn't exist`（op 不是 commit）。只能走操作日志：`jj --at-op=<op> file show <path>` 看内容，或 `jj op restore <op>` 整仓倒回去。

> 附带好处：操作日志给了**无锁并发**——多个 jj 命令（甚至跨机器经分布式文件系统）同时跑不会损坏仓库，冲突会在随后的 `jj st` / `jj log` 里以 divergent 提示出来。见 [operation-log](https://github.com/jj-vcs/jj/blob/v0.43.0/docs/operation-log.md)。

## <a id="conflicts"></a>一等冲突与延迟解决

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
- **auto-rebase**：重写某 commit 后，其后代自动跟着重写（change-id 稳定、commit hash 变）。一等冲突正是它的地基——后代 rebase 撞冲突也不会中断。
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

- 普通 `git show <commit>:f.txt` 看到的是**单边内容、没有冲突标记**——纯 git 工具看不出这是冲突 commit。
- 权威的冲突信息在一个**非标准 commit header** `jj:trees`（列出那几棵 tree）里；`.jjconflict-*/` 目录只是为了防 Git GC 掉这些 tree。
- `JJ-CONFLICT-README` 明说：*"This commit was made by jj … contains file conflicts, and therefore looks wrong when used with plain Git … Use `jj abandon` to recover."*

> [git-compatibility#format-mapping-details](https://github.com/jj-vcs/jj/blob/v0.43.0/docs/git-compatibility.md#format-mapping-details)：*"Commits with conflicts cannot be represented in Git. They appear in the Git commit as root directories called `.jjconflict-base-*/` and `.jjconflict-side-*/` … the authoritative information is in a non-standard `jj:trees` commit header."*；又：冲突分支在 Git 里的位置会被标成属于一个名为 `git` 的 remote，形如 `branch@git`（实测 `jj bookmark list --all-remotes` 能看到 `@git`）。

**change-id**。jj 的 change-id 也写进 Git commit 的**非标准 header**（reverse-hex）：

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

## <a id="local-vs-pushed"></a>留在 `.jj` 的数据与随 `jj git push` 传播的数据

**只有 `jj git push` / `jj git fetch` / `jj git clone` 碰远端。** 其余全是本地涂改板，一个字节不出机器，直到你显式 push：

- 操作日志、工作副本自动快照、被 `jj abandon` 的实验、`jj new/describe/split/squash/rebase/edit` 的每一步重写、bookmark 的增删——push 之前全在本地。
- **一等冲突根本推不出去**：`jj git push` 有一道校验，遇到不满足条件的 commit 直接拒推。实测两种：

  ```
  Error: Won't push commit <id> since it has conflicts
  Error: Won't push commit <id> since it has no description
  ```

  > 校验器完整拒推理由在源码 [`cli/src/commands/git/push.rs`](https://github.com/jj-vcs/jj/blob/v0.43.0/cli/src/commands/git/push.rs) 的 `CommitsValidator`：`has no description`（除非 `--allow-empty-description`）、`has conflicts`、`is private`（按 `git.private-commits`，除非 `--allow-private`）、`has no author and/or committer set`。

**跨机复制两条路，差别巨大（实测）：**

- **走 git（`jj git clone` / fetch）**：只搬 commit + bookmark（+ 对象里那条 change-id header）。**操作日志不跟着走**——clone 出来的仓 `jj op log` 是全新的几条（add workspace / fetch / checkout），你原来那串快照/实验**拿不到**。change-id 倒是两边一致，即"内容身份"随 commit 走、"操作历史"不走。
- **直接拷贝整个仓库目录（含 `.jj`，rsync / tar）**：**全都在**——`cp -r` 后 `jj op log` 原样完整。但这是**裸目录拷贝、不是同步协议**：没有合并、会互相覆盖，并发 / 锁自负。适合"把私有状态整体搬到另一台机"，不适合协作。

**远端只能是 Git 远端**：`jj git remote add <name> <url>`，url 可 https / ssh / file，和 git 一样——因为底层就是 git 传输。**没有 jj 原生协议**把操作日志 / 快照同步出去；那层在设计上就是本地的。

## <a id="durability"></a>改动的持久性与恢复

这里说的"安全"是**文件 / 改动不丢失**，不是保密。jj 在"不丢"上比 Git 更难丢，但也有明确边界。

**为什么难丢：**

- **正在编辑的内容一直被快照进 `@`**。Git 里"未 commit 的工作区改动"不受 reflog 保护，一发 `git reset --hard` / `git checkout` 就没；jj 里它已经是 `@` 这个 commit，几乎每条命令都快照它。
- **每次操作都进操作日志**，连"破坏性"操作（`abandon` / `rebase` / `restore` / 改写）都能回退：`jj undo` 撤上一步、`jj op restore <op>` 整仓倒回、`jj --at-op=<op>` 先看清再决定。colocated 下**连误用的 `git` 命令都能撤**。

  > [git-compatibility](https://github.com/jj-vcs/jj/blob/v0.43.0/docs/git-compatibility.md) 原文：*"You can undo the results of mutating `git` commands using `jj undo` and `jj op restore`."*

- **被抛弃 / 重写掉的 commit 由 `refs/jj/` 钉住**，不会被 Git GC 顺手收走。
- **jj 目前不 GC 自己的数据结构**（[issue #12](https://github.com/jj-vcs/jj/issues/12)），所以操作日志只增不减——对"事后捞回"很友好（代价是会一直变大）。

**边界（别当备份用）：**

- 操作日志和 `.jj` 都是**本地、明文**的 jj 自有格式，**不加密**。谁能读你的文件系统就能读全你的完整过程——"不进远端" ≠ "对人保密"。
- **它不随 `git push` 走**（见上）。远端 / 别人的 clone 只有你 curate 后推出去的那些 commit；`.jj` 里的操作日志、失败实验、中间快照**不在异地**。真要抗"整台机器没了"，要么把 commit push 到远端（只有干净、带描述、非冲突的 commit 活下来），要么把整个 `.jj` 目录一起备份 / 拷走。
- `git gc`（对后端 Git 仓）据官方"应该安全但未充分测试，建议先整仓备份"；`jj util gc` 会打包 refs、清理，之后不再被引用的旧态可能就没了。

## <a id="git-interop-limits"></a>与纯 Git 工具混用的限制

colocated（`.jj` + `.git` 并存）很方便让 build 工具照常认 Git 仓，但混用有代价（多数来自 [git-compatibility](https://github.com/jj-vcs/jj/blob/v0.43.0/docs/git-compatibility.md)，部分实测）：

- **不跑 Git hooks**（`Hooks: No.`）；**忽略 Git 暂存区**（`Staging area … will be ignored.`）。
- jj 命令常把底层 Git 置于 **detached HEAD**（jj 没有"当前跟踪分支"概念）；做变更型 `git` 命令前可能得先 `git switch` 告诉 Git 当前分支。建议混用时 `git` 只跑只读命令、变更交给 jj。
- **Git 工具看冲突 commit 会错乱**：看到 `.jjconflict-*/` 目录 + 单边文件（见 [Git 层表示](#conflict-in-git)）；误用 `git switch` 检出冲突 commit 后，`jj abandon` 可回到未解冲突态。
- **change-id 过普通 `git rebase` 会丢**（见上）。
- 不支持 LFS / submodule；shallow / partial clone 支持有限。pre-1.0，on-disk 格式在 1.0 前可能有破坏性变更。
