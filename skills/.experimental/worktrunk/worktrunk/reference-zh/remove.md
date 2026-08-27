> 本文是 `reference/remove.md` 的中文翻译副本，随上游同步需重译；行为以英文原文为准。

# wt remove

移除 worktree；如果分支已合并，则删除分支。默认为当前 worktree。

## 示例

移除当前 worktree：

```
$ wt remove
◎ Running pre-remove project:cleanup
  flyctl scale count 0
Scaling app to 0 machines
◎ Removing api worktree & branch in background (same commit as main, _)
○ Switched to worktree for main @ ~/repo
```

移除指定的 worktree / 分支：

```bash
$ wt remove feature-branch
$ wt remove old-feature another-branch
```

保留分支：

```bash
$ wt remove --no-delete-branch feature-branch
```

强制删除未合并的分支：

```bash
$ wt remove -D experimental
```

## 分支清理

默认情况下，如果分支合并后不会给默认分支增加任何更改，就会删除该分支。这既适用于 git 历史未经改变的情况，也适用于提交历史不同但文件更改相同的 squash 合并或 rebase 工作流。

Worktrunk 会检查六个条件（按成本从低到高排列）：

1. **相同提交**——分支 HEAD 与默认分支相同。显示 `_`，见 `wt list`。
2. **祖先**——分支位于目标分支的历史中（快进或 rebase 情形）。显示 `⊂`。
3. **没有新增更改**——三点 diff（`target...branch`）为空。显示 `⊂`。
4. **树匹配**——分支 tree SHA 与目标分支 tree SHA 相同。显示 `⊂`。
5. **合并不增加内容**——模拟合并生成的 tree 与目标分支相同。这能处理已通过 squash 合并、且目标分支后来又对其他文件有所推进的分支。显示 `⊂`。
6. **Patch-id 匹配**——分支的完整 diff 与目标分支上的某个 squash 合并提交相匹配。这是模拟合并发生冲突时的兜底方案；冲突是因为目标分支后来修改了该分支曾改动的相同文件。显示 `⊂`。

对默认分支历史的遍历设有上限，以确保单次检查保持快速；如果 squash 合并之后从合并点算起又落地了数百个提交，就会超出上限，需要使用 `-D` 才能移除。

“相同提交”检查使用本地默认分支；对于其他检查，“目标”指默认分支，或者在其上游（例如 `origin/main`）严格领先时指该上游。

符合这些条件且工作区为空的分支，会在 `wt list` 中以暗色显示，表示可安全删除。

这六项检查判断删除是否会丢失工作成果。在第二个 worktree 中检出的分支（只有通过 `git worktree add --force` 才可能出现）会无法通过另一项检查：删除该 ref 会使那个 worktree 无法解析 `HEAD`，这也是 `git branch -d` 会拒绝同一删除操作的原因。无论 `-D` 提出什么要求，这种分支都会保留，并会指出仍保留的检出位置。

## Force flag

Worktrunk 针对不同情况提供两个 force flag：

| Flag | 作用范围 | 使用时机 |
|------|-------|-------------|
| `--force` (`-f`) | worktree | worktree 有未提交的更改 |
| `--force-delete` (`-D`) | 分支 | 分支有未合并的提交 |

```bash
$ wt remove feature --force       # Remove dirty worktree
$ wt remove feature -D            # Delete unmerged branch
$ wt remove feature --force -D    # Both
```

无论合并状态如何，都可使用 `--no-delete-branch` 保留分支。

## 后台移除

默认情况下，移除操作在后台运行——命令会立即返回。worktree 会被重命名到 `.git/wt/trash/` 中（同一文件系统内的即时重命名），git 元数据会被清理，分支会被删除，最后由脱离当前进程的 `rm -rf` 完成清理。跨文件系统的 worktree 会兜底改用 `git worktree remove`。日志：`.git/wt/logs/{branch}/internal/remove.log`。使用 `--foreground` 可在前台运行。

每次 `wt remove` 之后，`.git/wt/trash/` 中超过 24 小时的条目都会由脱离当前进程的 `rm -rf` 清扫——这为先前后台移除因中断（SIGKILL、重启、磁盘已满）而留下的孤儿目录提供最终清理。

## 回收进程 [实验性]

`--reap` 会在移除 worktree 之前终止其中仍在运行的进程——例如 `post-start` 开发服务器、文件监视器、语言服务器——从而释放它们占用的端口和文件句柄。进程按工作目录发现：当前目录位于 worktree 路径处或其下的任何进程都会被处理（先发送 `SIGTERM`，再对存活进程发送 `SIGKILL`）。

```bash
$ wt remove --reap feature
◎ Reaping 2 processes under feature worktree
   ┃ 51234 node
   ┃ 51240 esbuild
✓ Reaped 2 processes
◎ Removing feature worktree & branch in background (same commit as main, _)
```

为避免终止用户无意终止的工作，以下两项防护使 `--reap` 保持保守：

- **交互式进程会被保留。** 持有控制终端的进程——交互式 shell，或有未保存缓冲区的 `vim` 等终端编辑器——绝不会被回收。只有脱离终端的进程仍是候选项。
- **仅按工作目录发现进程。** 如果进程从 worktree 中启动后改变了目录，或守护进程被重新设定父进程为 `init`，它就不再报告 worktree 下的目录，因此无法被发现。要可靠地回收这些进程，请通过 [`wt step tether`](https://worktrunk.dev/step/#wt-step-tether) 启动它们；移除 worktree 时，该命令会终止整个进程组。

进程回收会在触碰 worktree 目录之前运行，因此不受前台/后台移除方式和 `--force` flag 影响。仅支持 Unix；在 Windows 上会拒绝 `--reap`。

## Hook

`pre-remove` hook 在删除 worktree 之前运行（此时可以访问 worktree 文件）。`post-remove` hook 在移除后运行。配置方式参见 [`wt hook`](https://worktrunk.dev/hook/)。

## 分离 HEAD 的 worktree

Detached worktree 没有分支名。请改为传入 worktree 路径：`wt remove /path/to/worktree`。

## 命令参考

```
wt remove - Remove worktree; delete branch if merged

Defaults to the current worktree.

Usage: wt remove [OPTIONS] [BRANCHES]...

Arguments:
  [BRANCHES]...
          Branch name or worktree path [default: current]

Options:
      --no-delete-branch
          Keep branch after removal

  -D, --force-delete
          Delete unmerged branches

      --foreground
          Run removal in foreground (block until complete)

      --reap
          Kill processes started in the worktree [experimental]

          Before removal, terminate processes whose working directory is under the worktree — dev
          servers, watchers, language servers. Processes holding a controlling terminal (interactive
          shells, terminal editors) are left alone. Unix only.

  -f, --force
          Force worktree removal

          Remove a dirty worktree, including staged, modified, and untracked files. Without this
          flag, removal fails if the worktree has any uncommitted changes.

  -h, --help
          Print help (see a summary with '-h')

Automation:
      --no-hooks
          Skip hooks

      --format <FORMAT>
          Output format

          JSON prints structured result to stdout after removal completes.

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
