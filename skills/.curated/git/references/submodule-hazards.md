# submodule 与 worktree 的冲突

`git worktree` 让 N 个工作区共享一份 gitdir，而 submodule 的定位字段 `core.worktree` 是那份共享
config 里的**单值**字段，表达不了 N 个——两者装不到一起，这是 git 官方
[把 superproject 多工作区列进 BUGS](https://github.com/git/git/blob/v2.43.0/Documentation/git-worktree.txt#L513-L517)
的根因。

正常情况下你**不该读到这里**：有 submodule 就用共享 clone（见 [workspace.md](workspace.md#shared-clone)），
问题在结构上就不存在。以下几种情况才需要：

- 已经存在一个建好的 superproject worktree、必须就地修好
- git 已经报错、submodule 状态错乱，要做诊断和恢复
- 想知道"为什么不能靠小心点绕过"的完整现场

## <a id="core-worktree-hijack"></a>core.worktree 劫持

**最危险的一条，元凶是 `git submodule update`，不是 `git worktree add`。**

submodule 全仓库**只有一份 gitdir**（`.git/modules/<sub>`）——但这份 gitdir 是否被某个 worktree
共用，取决于你怎么在那个 worktree 里准备 submodule。**共用发生时**（先用 `git worktree add` 把
`.git/modules/<sub>` 挂到 worktree 的 submodule 路径上，[遗留场景](#legacy-fix)与下表第三步都是这么干的），
`core.worktree` 这个写在共享 config 里的**单值**字段要同时表达主工作区和 worktree 两个位置——
**谁最后写谁赢**，`git submodule update` 就把它改写成**自己所在 worktree** 的路径。

反过来，在 worktree 里**从零** `git submodule update --init`（此前没给该 submodule 建过 worktree）
不触发劫持，git 会另建一份[worktree 私有的 gitdir](#private-gitdir)。

git 2.43.0 实测（main + 嵌套 submodule，另建 worktree `mainwt`）：

| 步骤 | `.git/modules/sub/config` 的 `core.worktree` |
|---|---|
| 基线 | `../../../sub` ✅ |
| `git worktree add`（主仓库） | `../../../sub` ✅ 不变 |
| `submodule foreach 'git worktree add --force'` | `../../../sub` ✅ **不变** |
| `cd mainwt && git submodule update --recursive` | `../../../../../../mainwt/sub` ❌ **被改写** |

后果不止是「串目录」——git 写的还是一条**算错的相对路径**（相对共享 gitdir 多退了两级），
主仓库的 submodule 直接不可访问：

```
$ git -C main/sub rev-parse --show-toplevel
fatal: cannot chdir to '../../../../../../mainwt/sub': No such file or directory
$ git -C main submodule status --recursive
fatal: failed to recurse into submodule 'mid'
```

嵌套 submodule 会**逐层**被改写，层数越深路径错得越多。

### 别指望靠「小心点」绕过

危险的根源不是哪条命令用错了，而是 **worktree 方案下 submodule 的 config 被多个工作区共用**。
同一条 `git submodule update --recursive`：

| 在哪跑 | 它往哪写 `core.worktree` | 后果 |
|---|---|---|
| worktree 里 | **主仓库**共享的 `.git/modules/<sub>/config` | 主工作区的 submodule 变成不可访问：`fatal: cannot chdir to ...` |
| 共享 clone 里 | **这个 clone 自己**的 `.git/modules/<sub>/config` | 主仓库完全不受影响 |

实测共享 clone：在 clone 里跑完这条命令，clone 自己产生了 24 条 `core.worktree`（正常，它有自己的
gitdir），而**主仓库污染 0、`submodule status` 异常 0、`externals/eigen` 照常可读**。

区别不在「有没有小心」，在于**两份 config 到底是不是同一份**。共享 clone 把「共用」这个前提直接
拆掉了——所以不是「这次没出事」，是**结构上出不了事**。这很重要，因为你管得住自己，
管不住别的 session。

多 session 并发时这条尤其阴险：A 建 worktree 顺手跑了 `submodule update`，B 的主工作区
当场失去所有 submodule，而 B 完全无感——直到 build 挂了才发现，且错误信息指向别处。

现代 git 靠 submodule 目录下 `.git` 文件里的 `gitdir:` 指针定位，多 worktree 场景下
`core.worktree` **不需要存在**，出现即污染，删掉即可（见[恢复流程](#recover)）。

## <a id="private-gitdir"></a>worktree 私有的 submodule gitdir

在 worktree 里**从零**跑 `git submodule update --init`（此前没给该 submodule 建过 worktree）时，
git 不复用 `.git/modules/<sub>`，而是新建一份 **worktree 私有的 gitdir**：

```
.git/worktrees/<worktree名>/modules/<submodule路径>
```

worktree 里该 submodule 的 `.git` 文件就指向这里，主仓库的 `.git/modules/<sub>/config` 全程不被写，
`core.worktree` 保持原值——两边互不相干。

实测矩阵（2026-08-01，git 2.43.0，SU2-Quantum 本地副本，11 个 submodule，主工作区先已 init）：

| worktree 由谁建 | worktree 里怎么准备 submodule | 主仓库 `core.worktree` |
|---|---|---|
| `git worktree add` | 直接 `git submodule update --init` | 不变 |
| 第三方 worktree CLI（worktrunk `wt switch -c`） | 直接 `git submodule update --init` | 不变 |
| `git worktree add` | 先 `submodule foreach git worktree add --force`，再 `submodule update --recursive` | **被改写** |
| 第三方 worktree CLI | 同上 | **被改写** |

两条结论：

- **劫持与"谁建 worktree"无关**，只与"worktree 里怎么准备 submodule"有关。第三方 worktree CLI
  底层就是 `git worktree add [-b <分支>] -- <路径>`（读 worktrunk v0.71.0 源码确认），
  既不提供额外保护，也不引入额外风险。
- 被改写那两行的现场与[劫持](#core-worktree-hijack)一节记录的一致：错误相对路径、
  `git -C <sub> rev-parse --show-toplevel` 报 `fatal: cannot chdir to ...`；按[恢复流程](#recover)
  第 1 步递归清 `core.worktree` 后，11 条劫持归零、submodule 全部复活（同批实测）。

代价与边界：

- 私有 gitdir 让**每个 worktree 各存一份 submodule 对象**。submodule 的 URL 指向本地路径时
  git 会硬链接（实测 pack 文件链接数 = 3，几乎不占额外空间）；**指向远程时是真的各下一份**。
- 只实测了 git 2.43.0 + 非嵌套 submodule 的这条路径。更旧的 git、嵌套 submodule 未验证，
  别据此推广到所有版本。
- 这条路径能用，不等于"有 submodule 就可以放心用 worktree"：并发 session 里任何人在任一
  worktree 跑一次上表第三、四行那种准备方式，全体工作区照样中招——[选型](workspace.md#mechanism-compare)
  推荐共享 clone 的理由是"结构上出不了事"，不是"这条命令这次没出事"。



## <a id="force-piles-up"></a>`--force` 累积失效注册

`git worktree add --force` 每跑一次就**新增**一条注册，编号递增（`medi`、`medi1`…`medi6`），
不会复用旧条目。跨 session 反复建 worktree 会一直堆积。

实测某仓库积到 **168 条注册，其中 120 条是失效的**，最老的来自四个月前早已删除的目录。
所以[遗留场景](#legacy-fix)跑完要顺手 `prune`，别攒。

## <a id="foreach-blind-spot"></a>`git submodule foreach --recursive` 的遍历盲区

它只访问**已初始化**的 submodule。深层嵌套 submodule（三、四级）如果在当前工作区没被 `--init`，
`foreach --recursive` 就走不到，基于它的清理会留下盲区。

实测：用 `git submodule foreach --recursive 'git worktree prune'` 清完，仍有 **15 条**失效注册
残留在 3 个未初始化的深层 submodule 里（`CoolProp/externals/msgpack-c/external/boost/predef`
之类）。**清理一律走 `find .git/modules -type d -name worktrees` + `git --git-dir=`**，
它按磁盘上真实存在的 gitdir 遍历，没有盲区。

## <a id="manual-delete"></a>手删 `worktrees/` 会连活注册一起删

见过这样的写法：

```bash
for d in $(find .git/modules -type d -name "worktrees"); do
  trash-put "$d"/* 2>/dev/null || true      # ❌ 无差别删除
done
```

注释写「清失效条目」，实际 `"$d"/*` 把**活的注册一起删了**——正在用的 worktree 当场失去 git 关联。
`git worktree prune` 才做死活判断：它只删「`gitdir` 文件指向的路径已不存在」的注册，活的一个都不碰；
手删做不到这个区分。**能用 `git worktree` 子命令就别手删文件。**

## <a id="no-auto-submodule"></a>worktree 不会自动带上 submodule

主仓库的 worktree **不会**自动为 submodule 建立对应 worktree。不处理的话，submodule 在
worktree 里回退到主仓库的 submodule 路径，读写会串到主仓库；目录也可能是空的，构建会失败
而且错误信息通常指向别处。建完 worktree 先 `git submodule status` 确认，别等到 build 报错。

要在 worktree 里填上 submodule，两条路差别很大：**从零** `git submodule update --init`
走[私有 gitdir](#private-gitdir)、不碰主仓库；而对**已经 `git worktree add` 挂过共享 gitdir**
的 submodule 再跑 `git submodule update`，就是[劫持](#core-worktree-hijack)现场。
后者已发生时用[遗留场景](#legacy-fix)那套 `ls-tree` + `checkout --detach` 收拾。

## <a id="legacy-fix"></a>遗留场景：给已有 submodule worktree 对齐版本

> ⚠️ 下面的写法能规避[劫持](#core-worktree-hijack)，但规避不了 `--force` 累积等其余问题——治标不治本。
> 只在「worktree 已经建好、必须就地修好」时用；能重来就换共享 clone。
>
> **先问「这次要 build 吗」**：docs / 配置 / 脚本类改动不需要任何 submodule，整节跳过即零风险。
>
> **再问「非得共用主仓库那份 gitdir 吗」**：只要 submodule 在这个 worktree 里还没被
> `git worktree add` 挂过，直接 `git submodule update --init` 就够了，走[私有 gitdir](#private-gitdir)、
> 不需要下面这套。下面这套是给「共享 gitdir 已经挂上去了」的既成事实收尾的。

```bash
NEW="$PWD"
cd "$MAIN_REPO"
git submodule foreach --recursive '[ -e "'"$NEW"'/$displaypath/.git" ] || git worktree add --detach --force "'"$NEW"'/$displaypath" HEAD'

# 把每个 submodule 对齐到【新 worktree 的 HEAD】所记录的 commit。
# ⚠️ 这里绝对不能用 `git submodule update`——它会劫持主工作区
sync_submodules() {
    git -C "$1" ls-tree HEAD | awk '$2=="commit"{print $3" "$4}' | while read -r sha path; do
        git -C "$1/$path" cat-file -e "$sha^{commit}" 2>/dev/null || git -C "$1/$path" fetch -q
        git -C "$1/$path" checkout -q --detach "$sha"
        sync_submodules "$1/$path"
    done
}
sync_submodules "$NEW"

# 收尾：清掉本次 --force 新增的失效注册
find .git/modules -type d -name worktrees | while read -r d; do
    git --git-dir="$(dirname "$d")" worktree prune
done
```

关键点：

- `$displaypath` 由 `git submodule foreach` 注入，是 submodule 相对主仓库的路径
- 已存在的 submodule worktree 跳过创建（`[ -e ... ] ||`）
- `--detach` 避免分支冲突
- `--force` 容忍旧元数据残留，但会[累积注册](#force-piles-up)，所以末尾要 `prune`
- `sync_submodules` 递归走 `ls-tree`，只对本 worktree 的目录做 `checkout --detach`，
  全程不碰共享 config——这是替代 `git submodule update --recursive` 的关键。
  实测递归两层跑完，两层的 `core.worktree` 都纹丝不动
- `worktree add --detach … HEAD` 用的是**主仓库**当前的 submodule SHA；若新 worktree
  基于别的分支，SHA 可能不同，`sync_submodules` 负责纠正（必要时先 `fetch`）
- **这套只保护你自己这一次操作。** 任何人（别的 session、你自己手滑）在任一 worktree 里
  跑一次 `git submodule update`，主工作区的 submodule 照样立刻变成不可访问——这正是该换共享 clone 的理由

## <a id="diagnose"></a>动手前的诊断

```bash
cd "$MAIN_REPO"

# 有哪些 worktree、哪些是活的
git worktree list

# 有没有 core.worktree 劫持（含嵌套 submodule，必须递归 find）
find .git/modules -name config -exec grep -Hn "^[[:space:]]*worktree[[:space:]]*=" {} +

# 失效注册有多少、分别是谁（--dry-run 只报不删）
find .git/modules -type d -name worktrees | while read -r d; do
    git --git-dir="$(dirname "$d")" worktree prune --dry-run -v
done

# 某个 submodule 的注册各指向哪、死活如何（SUB 填 submodule 路径）
SUB=externals/foo
for e in ".git/modules/$SUB/worktrees"/*/; do
    g=$(cat "$e/gitdir"); [ -e "$g" ] && s=存活 || s=失效
    echo "$(basename "$e") -> $g [$s]"
done
```

## <a id="recover"></a>恢复流程

症状：`git` 报 worktree 相关错误、submodule 状态错乱、或某个 worktree 的 submodule 读写串到了
别的目录。按顺序做，每步都先看诊断输出再执行：

```bash
cd "$MAIN_REPO"

# 1. 撤掉 core.worktree 劫持。必须递归 find，嵌套 submodule 的 config
#    藏在 .git/modules/<a>/modules/<b>/... 里，单层通配会漏掉
find .git/modules -name config -print0 \
  | xargs -0 grep -l "^[[:space:]]*worktree[[:space:]]*=" 2>/dev/null \
  | xargs -r sed -i '/^[[:space:]]*worktree[[:space:]]*=/d'

# 2. 清掉失效的 worktree 注册。逐 gitdir 调 prune，不要用 submodule foreach（有盲区）
find .git/modules -type d -name worktrees | while read -r d; do
    git --git-dir="$(dirname "$d")" worktree prune -v
done
git worktree prune -v          # 主仓库自己也要清一次

# 3. 复查：前两条应为 0，第三条应只剩你确实还在用的 worktree
find .git/modules -name config -exec grep -l "^[[:space:]]*worktree[[:space:]]*=" {} + | wc -l
git submodule status | grep -c '^[+-]'
git worktree list
```

上面用 `sed` 批量撤 `core.worktree` 是兜底写法；只修一个已知 submodule 时更精确的是
`git config -f .git/modules/<sub>/config --unset core.worktree`。

清完若 submodule 仍错乱，再从头走一遍建工作区的流程。
