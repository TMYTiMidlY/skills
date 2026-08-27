> 本文是 `reference/switch.md` 的中文翻译副本，随上游同步需重译；行为以英文原文为准。

# wt switch

切换到 worktree；需要时创建。

worktree 通过分支名寻址；路径由可配置模板计算。与 `git switch` 不同，此命令在 worktree 之间导航，而不是在原位置切换分支。

## 示例

```bash
$ wt switch feature-auth           # Switch to worktree
$ wt switch -                      # Previous worktree (like cd -)
$ wt switch --create new-feature   # Create new branch and worktree
$ wt switch --create hotfix --base production
$ wt switch pr:123                 # Switch to PR #123's branch
$ wt switch https://github.com/owner/repo/pull/123   # ...or paste the PR's URL
```

## 创建分支

`--create` flag 会从 `--base` 创建新分支；除非另行指定，否则基础分支为默认分支。不使用 `--create` 时，分支必须已经存在。切换到远端分支（例如仅存在 `origin/feature` 时运行 `wt switch feature`）会创建本地跟踪分支。

## 创建 worktree

如果分支已有 worktree，`wt switch` 会将目录切换到该 worktree。否则，它会创建一个：

1. 运行 [pre-switch hook](https://worktrunk.dev/hook/#hook-types)，阻塞直到完成
2. 在配置的路径创建 worktree
3. 切换到新目录
4. 运行 [pre-start hook](https://worktrunk.dev/hook/#hook-types)，阻塞直到完成
5. 在后台启动 [post-start](https://worktrunk.dev/hook/#hook-types) 和 [post-switch hook](https://worktrunk.dev/hook/#hook-types)

```bash
$ wt switch feature                        # Existing branch → creates worktree
$ wt switch --create feature               # New branch and worktree
$ wt switch --create fix --base release    # New branch from release
$ wt switch --create temp --no-hooks       # Skip hooks
```

## 指定 worktree

worktree 通过分支名寻址；任何接受分支名的参数也都接受 worktree 自身的路径——系统会先按分支解析、再按路径解析，因此目录永远不会遮蔽同名分支。路径可以指定分支名无法指定的对象：分离 HEAD 的 worktree，或同一分支两次检出中的某一个。相对路径以 `-C` 为基准解析，前导 `~` 则以主目录为基准，因此可以把 Worktrunk 打印的路径直接粘贴回来。

## 快捷方式

| 快捷方式 | 含义 |
|----------|---------|
| `^` | 默认分支（`main`/`master`） |
| `@` | 当前分支/worktree |
| `-` | 上一个 worktree（类似 `cd -`） |
| `pr:{N}` | GitHub PR #N 的分支 |
| `mr:{N}` | GitLab MR !N 的分支 |

```bash
$ wt switch -                           # Back to previous
$ wt switch ^                           # Default branch worktree
$ wt switch --create fix --base=@       # Branch from current HEAD
$ wt switch --create fix --base=pr:123  # Branch from PR #123's head
$ wt switch pr:123                      # PR #123's branch
$ wt switch mr:101                      # MR !101's branch
```

快捷方式也适用于 `--base`。对于 fork PR/MR，系统会 fetch 头提交，并将其作为基础 SHA 使用，而不会创建跟踪分支。

## 交互式选择器

不带参数调用时，`wt switch` 会打开交互式选择器，通过实时预览浏览并选择 worktree。`--branches`（没有 worktree 的本地分支）、`--remotes`（远端分支）和 `--prs`（开放的 PR/MR——见下文）会扩大候选集合。

CI 列显示每一行的 PR/MR CI 和审查状态，与 [`wt list --full`](https://worktrunk.dev/list/) 相同。

**按键绑定：**

| 按键 | 操作 |
|-----|--------|
| `↑`/`↓` | 在 worktree 列表中导航 |
| (type) | 筛选 worktree |
| `Enter` | 切换到所选 worktree |
| `Alt-c` | 以输入的文本为名称创建新 worktree |
| `Alt-x` | 移除所选 worktree/分支 |
| `Alt-y` | 将所选分支名复制到剪贴板 |
| `Alt-o` | 在浏览器中打开所选行的 PR/MR URL |
| `Alt-r` | 刷新列表（纳入在其他位置创建的 worktree） |
| `Esc` | 取消 |
| `Alt-1`–`Alt-7` | 跳转到预览标签页 |
| `Tab`/`Shift-Tab` | 向前/向后循环切换预览标签页 |
| `Alt-p` | 切换预览面板 |
| `Ctrl-u`/`Ctrl-d` | 向上/向下滚动预览 |

对于没有 PR/MR 的行（或状态尚未加载的行），`Alt-o` 不执行任何操作。

对于当前 worktree（`@` 行），`Alt-x` 不执行任何操作——移除正在使用的 worktree 前必须先切换到别处，因此请先切走，再从那里移除它。

每一行都可按其分支、路径筛选；如果有 PR/MR，还可按 PR/MR 的编号、标题和作者筛选。无论 PR 已检出（worktree 行）还是通过 `--prs` 列出，这些字段都相同。普通数字键会输入筛选器，因此可以直接键入编号；预览标签页的数字快捷键则使用 `Alt`。

输入左侧标记符号可按行类型筛选：`+` 将范围缩小到链接 worktree，`@` 则缩小到当前 worktree。其他符号无法干净地用于筛选——`^` 和 `|` 分别是 skim 的前缀锚定和 OR 查询运算符（所以 `^` 匹配每一行，`|` 一行也不匹配），而 `/` 会匹配大多数行，因为每个 worktree 路径都包含它。

**预览标签页：**

1. **HEAD±**——未提交改动的 diff
2. **log**——最近的提交；默认分支中已有的提交会暗显哈希
3. **main…±**——从与默认分支的 merge-base 起算的改动 diff
4. **remote⇅**——相对上游跟踪分支领先/落后的 diff
5. **summary**——LLM 生成的分支摘要；需要 `[list] summary = true` 和 [`commit.generation`](https://worktrunk.dev/config/#commit)
6. **pr**——所选行的 PR/MR，适用于分支有关联 PR/MR 的任何行
7. **comments**——PR/MR 的评论线程；对于分支有关联 PR/MR 的任何行，均从 forge 获取

预览较窄时，标签栏会压缩为数字——只有活动标签页保留标签——因此每个 `Alt-N` 快捷键始终可见。

**分页器配置：** 预览面板通过 git 的分页器传递 diff 输出。可在用户配置中覆盖：

```toml
[switch.picker]
pager = "delta --paging=never --width=$COLUMNS"
```

## PR 与 MR

`pr:<number>` / `mr:<number>` 快捷方式以及 PR/MR 的 Web URL 都会解析到其分支。对于同仓库 PR/MR，Worktrunk 会直接切换到该分支。对于 fork PR/MR，它会 fetch ref（`refs/pull/N/head` 或 `refs/merge-requests/N/head`），并将 `pushRemote` 配置为 fork URL。

```bash
$ wt switch pr:101                                  # GitHub PR #101
$ wt switch https://github.com/owner/repo/pull/101  # ...the same PR, by URL
$ wt switch mr:101                                  # GitLab MR !101
$ wt switch https://gitlab.com/owner/repo/-/merge_requests/101  # ...the same MR, by URL
$ wt switch --prs                                   # Browse open PRs/MRs in the picker
```

两者在任何接受分支的地方都可使用，包括 `--base`。由于分支已经存在，`--create` flag 不能与 PR/MR 引用一起使用。

如果 PR 或 MR 位于 fork 上，本地分支会直接使用其分支名，因此 `git push` 可以正常工作。如果已有同名本地分支跟踪的是其他对象，则需要先重命名。

`--prs` flag 会把仓库的开放 PR（GitHub）或 MR（GitLab）加入交互式选择器——只加入尚未出现的项目：如果某个 PR 的分支已显示（作为 worktree、本地分支或远端分支），就不会重复列出；因此 `--prs` 只会添加其余项目，两个选择器之间也只相差这些额外行。每个新增行都解析到相同的 `pr:`/`mr:` 快捷方式，因此选择后会 fetch ref 并切换到其分支。`--prs` 行没有本地 worktree，因此其 `pr` 和 `comments` 预览标签页会在后台从 forge 加载 PR/MR 元数据和评论。只要头提交已在对象存储中（例如同仓库 PR 来自已 fetch 的远端），`log` 标签页就会使用本地 `git log`——包括图和 merge-base 暗显；否则回退到从 forge 获取的扁平提交列表。

需要安装并认证 `gh`（GitHub）、`glab`（GitLab）或等效 CLI；有关 Gitea、Azure DevOps 和其他受支持平台，请参阅 [forge 平台](https://worktrunk.dev/config/#forge-platform)。

## wt switch 失败时

- **分支不存在**——使用 `--create`，或检查 `wt list --branches`
- **路径被占用**——另一个 worktree 位于目标路径；切换到该 worktree 或将其移除
- **陈旧目录**——使用 `--clobber` 移除目标路径处不属于 worktree 的目录

要更改某个 worktree 所在的分支，请在该 worktree 内使用 `git switch`。

## 命令参考

```
wt switch - Switch to a worktree; create if needed

Usage: wt switch [OPTIONS] [BRANCH] [-- <EXECUTE_ARGS>...]

Arguments:
  [BRANCH]
          Branch, worktree path, shortcut, or PR/MR URL

          Opens interactive picker if omitted. Shortcuts: ^ (default branch), - (previous), @
          (current), pr:{N} (GitHub PR), mr:{N} (GitLab MR)

  [EXECUTE_ARGS]...
          Additional arguments for --execute command (after --)

          Arguments after -- are appended to the execute command. Each argument is expanded for
          templates, then POSIX shell-escaped.

Options:
  -c, --create
          Create a new branch

  -b, --base <BASE>
          Base branch

          Defaults to default branch. Supports the same shortcuts as the branch argument: ^, @, -,
          pr:{N}, mr:{N}.

  -x, --execute <EXECUTE>
          Command to run after switch

          Replaces the wt process with the command after switching, giving it full terminal control.
          Useful for launching editors, AI agents, or other interactive tools.

          Without a branch argument, the interactive picker opens and the command runs against the
          selected worktree — so wt switch -x claude picks a worktree, then launches Claude Code
          there.

          Supports hook template variables ({{ branch }}, {{ worktree_path }}, etc.) and filters. {{
          base }} and {{ base_worktree_path }} describe the source: the selected base with --create,
          or the invoking worktree when switching to an existing worktree.

          Especially useful with shell aliases:

            alias wsc='wt switch --create -x claude'
            wsc feature-branch -- 'Fix GH #322'

          Then wsc feature-branch creates the worktree and launches Claude Code. Arguments after --
          are passed to the command, so wsc feature -- 'Fix GH #322' runs claude 'Fix GH #322',
          starting Claude with a prompt.

          Template example: -x code -- '{{ worktree_path }}' opens VS Code at the worktree, -x tmux
          -- new -s '{{ branch | sanitize }}' starts a tmux session named after the branch.

      --clobber
          Remove stale paths at target

      --no-cd
          Skip directory change after switching

          Hooks still run normally. Useful when hooks handle navigation (e.g., tmux workflows) or
          for CI/automation. Use --cd to override.

  -h, --help
          Print help (see a summary with '-h')

Picker Options:
      --branches
          Include branches without worktrees

      --remotes
          Include remote branches

      --prs
          Include open PRs/MRs

Automation:
      --no-hooks
          Skip hooks

      --format <FORMAT>
          Output format

          JSON prints structured result to stdout. Designed for tool integration (e.g., Claude Code
          WorktreeCreate hooks).

          [default: text]
          [possible values: text, json]

Global Options:
  -C <path>
          Working directory for this command

      --config <path>
          User config file path

      --config-set <toml>
          Override config with inline TOML, e.g. --config-set list.full=true (repeatable)

  -v, --verbose...
          Verbose output (-v: info logs + hook/alias template variables on stderr; -vv: also debug
          logs and raw subprocess output written to .git/wt/logs/). Set WORKTRUNK_VERBOSE=0|1|2 to
          apply the same level everywhere — including shell completion, which no flag can reach

  -y, --yes
          Skip approval prompts
```
