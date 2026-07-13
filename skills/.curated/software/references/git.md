# Git CLI 精准操作（在有并发/无关改动时只提交、暂存、丢弃、amend 一处）

面向的场景：工作区里同时躺着**你想提交的改动**和**不该由你带走的改动**（并发会话未提交的脏文件、别人已经 `git add` 的 rename、untracked 文件……），你要在**命令行非交互**地只对其中一处做 commit / stage / discard / stash；以及当你的提交后面又被别人叠了新提交时怎么改它。下面结论基于 git 2.43.0。

## 心智模型：三个位置 + "跟谁比"

Git 的所有"部分操作"只围绕三个位置：

- **HEAD** —— 上一次提交的快照（tree）。
- **index / 暂存区** —— 下一次提交的**草稿快照**。它通常落在 `.git/index`，不是一堆散乱文件，而是一张按路径索引的表：每项记录“这个路径下一次提交应指向哪个 blob（文件内容对象）、文件模式和少量状态标记”。同一 worktree 里的多个终端/agent 共享同一个 index；不同 `git worktree` 各有自己的 index。
- **worktree / 工作区** —— 磁盘上的当前文件。

`git add -- <path>` 的本质是把该路径**当前工作区内容**写入/更新 index 条目；`git commit`（不带路径）再把整张 index 快照拍成提交。因为 index 按路径分项，add 一个新文件不会改动其它路径的条目，但同一路径若被多个会话同时 stage/commit，仍会互相影响。

每个 `-p`（interactive patch）命令的行为，完全由两件事决定：**拿哪两个位置做 diff（"基准 floor" ↔ 目标）**，以及**把选中的 hunk 往哪个方向应用**。记住"基准是谁"，就能预测它看得见什么、动得了什么、什么会被当成不可改的底座。

## `git commit` 的本质 = 给 index 拍快照

`git commit`（**不带路径**）把**整个 index** 打成一个提交，跟你这一轮 `git add` 了哪些无关——暂存区里有什么就提交什么。这不是 `-p` 特有的，是 commit 的定义。

```
# 只 add 了 f.txt，但暂存区里别人的 rename 也在
$ git add f.txt
$ git status -s
M  f.txt
R  other.txt -> renamed.txt
$ git commit -m "只想提交 f.txt"
$ git show --stat --oneline HEAD
 f.txt                    | 1 +
 other.txt => renamed.txt | 0        # ← rename 搭车进了 commit
```

结论：`git commit` **不带路径时**，只要东西在 index 里就必然带走。要隔离其它路径，只有两条路——把它们撤出 index（`git restore --staged`），或改用下面的 pathspec 部分提交：提交内容不取其它 index 条目，点名路径之外的暂存内容不会搭车。

## 在有其他改动时只提交一处：`git commit -- <path>`（不带 -p）是最稳的 CLI 方案

`git commit -- <path>...`（**带路径、不带 `-p`**）是"部分提交 / partial commit"。git-commit(1) 原文：以文件为参数（*without --interactive or --patch switch*）时，提交会 **"ignore changes staged in the index, and instead record the current content of the listed files (which must already be known to Git)"**——即忽略整个 index，用 `HEAD + 列出文件的当前工作区内容`临时建一棵树来提交。因此：

- 只提交你点名的路径；
- 别人已暂存的改动（rename、其它文件）、你没点名的 untracked 文件**一个都不搭车**，原封不动留在 index / worktree；
- 对**已跟踪**文件连 `git add` 都省了（工作区改动直接进这一个提交）；但**全新的 untracked 文件必须先让 Git “认识”这个路径**——否则匹配不到、报 `did not match any files known to git`。不必完整暂存内容，优先用下一小节的 `git add -N`。

`--` 是否必需见本节末小节：对 commit 加不加提交结果相同，但推荐带上以防路径被误当成选项。

```
# 工作区: 你改了 AGENTS.md，另有 6 项并发改动(4 modified + 2 untracked)
$ git commit -m "docs: update agent rules" -- AGENTS.md
# 结果: 只动 AGENTS.md；6 项并发改动纹丝不动，其它路径的 index 条目不受影响
# 选项(-m/-F)放 -- 前面；-- 之后一律当路径
```

对照三条命令（工作区: 别人已暂存 rename + 你未暂存的 `f.txt`）：

| 命令 | 机制 | 结果里有 rename 吗 |
|---|---|---|
| `git commit -m …`（无路径） | 提交整个 index | **有**（index 里就有） |
| `git commit -- f.txt`（pathspec，**无 -p**） | 忽略 index，只记 HEAD + f.txt 当前内容 | **没有**（隔离干净） |
| `git commit -p -- f.txt`（pathspec + **-p**） | index 为底座 + 选中 hunk（见下节） | **有**（rename 是底座，搭车） |

> ⚠️ 反直觉点：给 `git commit` 加了 `-p` **反而破坏了 pathspec 提交本来的隔离性**。`commit -p f.txt` 不是"只提交 f.txt 一处"的隔离方案；`commit f.txt`（不带 -p）才是。`commit -p f.txt` 的价值只在"没有别的东西暂存"时——它省的是 `git add`，不是省"清理别人的暂存内容"。

### 全新文件：用 `git add -N` 只登记路径，再精准提交

`git add -N` / `--intent-to-add` 仍然会写 index，但只写一个“这个路径稍后要加入”的标记，不把文件内容暂存进去。git-add(1) 原文：*“An entry for the path is placed in the index with no content.”* 因此更准确的说法是**轻触 index，而不是完全不碰 index**。

```bash
# new.txt 目前是 ??（完全 untracked）
git add -N -- new.txt
# 此时 git status -s 显示 " A new.txt"：
# 右列 A = 工作区内容仍未暂存；git diff --cached 里没有 new.txt 的内容

git commit -m "add new.txt" -- new.txt
```

第二步仍走 pathspec 部分提交：只提交 `new.txt` 的当前工作区内容，别的已暂存文件不搭车、仍留在 index。成功后 `new.txt` 成为普通 tracked 文件。对比完整的 `git add -- new.txt`：后者也不会让其它路径搭车，但会先把 `new.txt` 的全部内容真正放进暂存区；若 commit 中途取消，它会继续保持 staged。

边界：这种隔离保证的是**其它路径**不受影响。若另一会话也在操作 `new.txt` 本身（或已 stage 同一文件的其它 hunk），pathspec 无法区分“同一路径里谁的改动”；应改用独立 worktree，或用临时 index + `commit-tree`。

### `--` 分隔符：加不加提交结果相同，但推荐带上

`--` 是 git 通用的**选项/路径分隔符**（git-commit(1) 的 SYNOPSIS 就写作 `[--] [<pathspec>...]`），本质是 revision 与 path 的消歧符（gitcli(7)）。对 `git commit`：

- **提交结果与是否带 `--` 无关**：普通文件名下 `git commit f.txt` 与 `git commit -- f.txt` 产生完全相同的提交（都走上面的 pathspec 部分提交）。`--` 不改变"提交什么"，只消歧义。
- **`--` 防的是"路径被误当成选项"**：文件名以 `-` 开头时，不带 `--` 会被解析成选项：

  ```
  $ git commit -m c -x      → error: unknown switch `x'    # -x 被当成选项
  $ git commit -m c -- -x   → 正常提交名为 -x 的文件         # -- 之后 -x 是路径
  ```

  `git commit` 不接受 revision 参数，所以"路径名撞分支/标签名"这种歧义**咬不到 commit**（不像 `checkout`/`restore`/`reset`）；但加 `--` 的习惯全 git 一致、无害。
- **选项要放在 `--` 前面**：`-m` / `-F` 等必须在 `--` 之前；`--` 之后的一切都当路径（把 `-m msg` 放到 `--` 后面会报 `pathspec '-m' did not match`）。
- **官方建议**：gitcli(7) —— *"When writing a script that is expected to handle random user-input, it is a good practice to make it explicit which arguments are which by placing disambiguating `--` at appropriate places."* 路径来自变量 / 通配符 / 用户输入时显式加 `--` 更稳，所以把 `git commit -- <path>` 作为默认推荐写法。

同理 `git restore -- <path>`、`git stash push -- <path>`、`git checkout <rev> -- <path>` 等吃路径的命令也建议用 `--` 划清"路径从哪开始"；对同时吃 revision 的命令（checkout/restore/reset）更是刚需。

## `-p` 系列的真相：以某个基准为底座，只能"加"选中的 hunk，减不掉底座

各 `-p` 命令的基准和作用（k.txt 构造：HEAD=`[base]`、index=`[base,STAGED]`、worktree=`[base,STAGED,WORKTREE]`）：

| 命令 | 基准(floor) | 选择器显示 | 选中后干什么 | 已暂存内容的下场 |
|---|---|---|---|---|
| `git add -p` | index | 未暂存(index↔worktree) | 加进 index（stage） | 已在 index，是上下文 |
| `git commit -p [path]` | index | 未暂存 | commit = index + 选中 | **底座，必带走** |
| `git restore -p [path]` | index | 未暂存 | 从 worktree 丢弃（还原到 index） | **地板，够不到、动不了** |
| `git restore --staged -p [path]` | HEAD | 已暂存(HEAD↔index) | 从 index 撤出（unstage） | 正是操作对象 |
| `git restore -SW --source=HEAD -p [path]` | HEAD | 全部(HEAD↔worktree) | index+worktree 都还原到 HEAD | 一起清 |
| `git stash -p` | HEAD | 全部 | 存进 stash、回滚 worktree | **一起卷走**；且不重置 index |

验证基准的办法：`printf 'q\n' | git commit -p` 只看它列出的 diff。`commit -p` 显示 `@@ -1,2 +1,3 @@`、`STAGED` 行是上下文（行首空格）、只有 `WORKTREE` 是可选的 `+`——证明基准是 index、已暂存内容是不可选的底座。`stash -p` 显示 `@@ -1 +1,3 @@`、`STAGED` 和 `WORKTREE` 都可选——证明基准是 HEAD。

几个容易记错、要点名的行为：

- **`git commit -p [path]`**：commit = `当前 index（底座）+ 你选中的 hunk`。`-p` 后面的 path 只**限制选择器给你看哪些文件的 hunk**，挡不住已暂存内容。所以它"加得上、减不掉"。
- **`git restore -p`**（默认 = 从 index 还原 worktree）：基准是 index，**只能丢弃未暂存的改动**；已暂存的对它是不可见的地板，丢不掉。要连已暂存的一起清，得 `git restore --staged --worktree --source=HEAD -p <path>`（等价旧写法 `git checkout -p HEAD -- <path>`，提示语 "Discard this hunk from index and worktree"）。
- **`git stash -p`**：基准是 HEAD，**看得见也能卷走已暂存的内容**；但它**不重置 index**，选走后会留下"index 领先 worktree"的状态（`git status` 里同一文件同时出现在 "Changes to be committed" 和 "Changes not staged"）。这跟裸 `git stash`（会把 index 也一并重置）不同。

一句话总纲：**`commit -p` / `add -p` 往 index 方向加、`restore -p` 从 worktree 方向减、`stash -p` 搬走**；基准=index 的命令只在"未暂存"范围里动，基准=HEAD 的命令（`stash`、`--source=HEAD`）才够得到已暂存内容。

## 子文件（hunk / 行）级的纯 CLI 非交互做法：补丁手术

Git **没有**非交互的 hunk 选择 porcelain——`-p` 系列本质是 TUI。要脚本化 / 非交互地只处理某个 hunk 或某几行，走 `git diff` 导出补丁 → 裁剪 → `git apply` 打回。方向靠 `git apply` 的参数：

| 目的 | 命令 |
|---|---|
| 只**暂存**第 N 个 hunk | `git diff <path> \| filterdiff --hunks=N \| git apply --cached` |
| 精修到**行级**再暂存 | `git diff <path> > p.patch`；编辑 p.patch（删不要的 `+` 行、把要保留的 `-` 行首 `-` 改成空格）；`git apply --cached p.patch` |
| **丢弃**工作区某 hunk | `git apply -R p.patch`（反向打，`-R` = reverse） |
| 从**暂存区撤出**某 hunk | `git apply -R --cached p.patch` |

`filterdiff` 来自 `patchutils` 包（本机 0.4.2）；`--hunks=N` 按序号选 hunk，`--lines` 按行选，`-i/-x` 按文件名筛。一行式例子（把第 25 行那处 hunk 非交互地暂存，第 3 行不动）：

```
$ seq 1 30 > m.txt; git add m.txt; git commit -m init
$ sed -i '3s/.*/THREE/; 25s/.*/TWENTYFIVE/' m.txt      # 两处相隔很远 = 两个 hunk
$ git diff m.txt | filterdiff --hunks=2 | git apply --cached
$ git diff --cached | grep '^+T'      # +TWENTYFIVE  ← 只暂存了第2处
$ git diff        | grep '^+T'         # +THREE       ← 第1处仍未暂存
$ git commit -m "只提交第25行那处"       # 只含 TWENTYFIVE
```

没有 `filterdiff` 时，用 `git diff <path> > p.patch` 手工删掉不要的 `@@` 段（每个 hunk 从 `@@` 开始到下一个 `@@` 或文件尾），保留补丁头四行（`diff --git` / `index` / `---` / `+++`），再 `git apply --cached p.patch`。git diff 每个 `@@` 的行号是相对原文件的绝对值，删掉别的 hunk 不影响保留 hunk 的定位。

## TUI（交互选择器）简述 + 与 CLI 的对应

`git add -p` / `git commit -p` / `git restore -p` / `git stash -p` 都进入逐 hunk 的选择器，主要按键：

- `y` 选 / `n` 不选本 hunk；`a` 选本文件剩余全部 / `d` 全不选；`q` 退出；`?` 帮助。
- `s`（split）：把一个大 hunk 拆成小 hunk——**两处改动之间要有未改动行**才拆得开。能拆时菜单才列出 `s`（`[y,n,q,a,d,s,e,?]`），按下即 "Split into 2 hunks" → 变 (1/2)；紧挨着的改动菜单里**根本没有 `s`**（`[y,n,q,a,d,e,?]`），强按提示 `Sorry, cannot split this hunk`。
- `e`（edit）：手改当前 hunk 的补丁文本，做**行级**精度——不想进去的 `+` 行删掉；想保留成上下文的 `-` 行，把行首 `-` 改成空格。

TUI 按键 ↔ CLI 补丁手术的对应关系：

| TUI 操作 | 效果 | 非交互 CLI 等价 |
|---|---|---|
| `y`/`n` 逐 hunk 取舍 | 选哪些 hunk 进这次操作 | `filterdiff --hunks=…` 或手删补丁里的 `@@` 段 |
| `s` split | 把大 hunk 拆开再单选 | 补丁里本就是分开的 `@@` 块，直接挑 |
| `e` edit | 行级精修 | 直接编辑补丁文本（删 `+` 行 / `-` 改空格） |

**脚本化驱动 TUI**：选择器从 **stdin** 读答案，把单字母答案按顺序喂进去即可，等价于依次敲键：

```
printf 'y\ns\nn\n' | git add -p <path>     # 对第1个hunk: 拆开→留前半→弃后半
```

依赖 hunk 的顺序和数量，脆但可脚本化。要稳，优先用上一节的 `git diff | filterdiff | git apply`。

## 后面已经有别人的提交时，如何 amend 旧提交

场景：你提交后，并发会话在你之上又提交了 `<child>`，你的提交**不再是 HEAD**。`git commit --amend` 只能改 HEAD，够不到你的提交。

**正常办法 —— `git rebase -i` 的 reword / edit**：

```
git rebase -i <你的提交>^     # 打开待办清单，把你那行的 pick 改成:
#   reword  → 只改提交信息（tree 不变）
#   edit    → 停下来改内容（可 git commit --amend 后 git rebase --continue）
```

`reword` 的语义：**保留该提交的 tree（改动）完全不变，只重写 log message**。因为 commit 的 SHA = hash(tree + 父 + 作者 + committer + 消息)，消息一变 SHA 就变，**被 reword 的那条及其上所有子提交都会被重建成新 SHA**（父链变了），但各自的 tree 字节不变：

```
# reword 中间那条 mine 后（theirs 叠在其上）
 提交    SHA              tree           消息
 mine    a8f6a9a→872a6c9  e56ea79 不变   改了 + 加 trailer
 theirs  42598eb→73feb0e  1c0bdcf 不变   没动（仅因父变而重建）
 base    1e20ed8 不变      —             —
```

即 `reword` 是 `--amend` 的推广：`--amend` 只够得到 HEAD，`reword` 能改范围内任意一条的消息，代价是重建其上所有子提交。

### 用 fixup 修正旧提交，稍后再折叠

`git commit --fixup=<target>` **不会立刻改写旧提交**，而是在当前分支顶端新建一条普通提交，标题自动写成 `fixup! <target 的标题>`。等工作告一段落，再由 `git rebase -i --autosquash <target>^` 自动把 fixup 移到目标提交后面并标成 `fixup`：内容并入目标提交，fixup 自己的标题/消息丢弃。

```bash
# 1. 把当前点名路径的修正做成 target 的 fixup；忽略 index 里的其它内容
git commit --fixup=<target> -- <path>...

# 2. 若刚建的 fixup 仍是 HEAD，又要补一点修正：直接更新这条 fixup
git commit --amend --no-edit -- <path>...

# 3. 最后把 fixup 折叠回目标提交（会重写 target 及其后的提交 SHA）
git rebase -i --autosquash <target>^
```

第 2 步的 `--no-edit` 保留 `fixup! ...` 标题，pathspec 只更新点名路径：其它已暂存文件不会搭车、仍留在 index。amend 后 fixup 自己会换一个新 SHA，这是正常的。若 fixup 已经不再是 HEAD，不能直接 amend（会改到当前 HEAD）；通常再建一条指向同一 `<target>` 的 fixup，最后让 autosquash 一并折叠。

**为什么这里 rebase 也可能用不了**：`git rebase -i` 要求 index 和 worktree 干净（会 checkout、移动 HEAD）。工作区若有并发会话**未提交的脏文件**，rebase 直接拒绝启动（`error: cannot rebase: You have unstaged changes.`）；而你又不能 `git stash` 掉别人的改动。

**不碰工作区的 plumbing 等效做法（= reword 的手工版）**：用 `commit-tree` 重建提交、`update-ref` 带 CAS 原子移分支，全程零 checkout、不读不写 index / worktree。

```
# 目标：把 <old-mine> 的消息换成新消息，其上还有 <old-child>
BASE=$(git rev-parse <old-mine>^)                       # 你那条的父
T_MINE=$(git rev-parse <old-mine>^{tree})               # 复用原 tree
NEW_MINE=$(git commit-tree "$T_MINE" -p "$BASE" -m "新消息")   # 重建你的提交→新SHA

T_CHILD=$(git rev-parse <old-child>^{tree})
# 保留 child 原作者/消息，只把父换成 NEW_MINE：
NEW_CHILD=$(git commit-tree "$T_CHILD" -p "$NEW_MINE" \
              -m "$(git log -1 --format=%B <old-child>)")

# CAS 原子移动分支尖：只有当前 tip 仍等于期望旧值才移动
git update-ref refs/heads/<branch> "$NEW_CHILD" <期望旧tip>
```

- **`commit-tree`**：给定 tree + 父 + 消息，直接吐一个提交对象、不碰 index/worktree。复用原 tree = "只换消息/换父，内容不变"，正是 reword 对每条提交做的事。多个子提交就逐层 `commit-tree`（各用自己的原 tree、父指向上一步的新提交）。作者信息可用 `GIT_AUTHOR_*` 环境变量或从原提交 `--format` 取来保留。
- **`update-ref <ref> <new> <old>`** 的第三个参数是 CAS（compare-and-swap）：只有 ref 当前值**仍等于** `<old>` 才更新，否则报错退出。意义：并发会话若在你计算的这一瞬又推了新提交、`<old>` 对不上，命令**失败而非覆盖**，不会把别人的提交冲掉。这就是"原子移动"。

代价：手工重建会漏掉 committer date、GPG 签名、合并提交的第二父等细节，只适合线性、无签名的小改；能跑 `rebase -i` 时优先 rebase。

## 相关

- 官方文档：[git-commit(1)](https://git-scm.com/docs/git-commit)（DESCRIPTION 的 "way 3" = pathspec 部分提交忽略 index）、[gitcli(7)](https://git-scm.com/docs/gitcli)（`--` 消歧、revision/path 顺序、通配符转义规则）。
- 跨设备 git 镜像见 [git-mirror.md](git-mirror.md)；自建 Forgejo / Gitea + MCP 见 [git-server.md](git-server.md)。
- 删除临时文件 / 补丁残留用 `trash-put`，回收站行为见 [trash.md](trash.md)。
