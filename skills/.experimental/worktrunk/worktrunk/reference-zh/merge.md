> 本文是 `reference/merge.md` 的中文翻译副本，随上游同步需重译；行为以英文原文为准。

# wt merge

将当前分支合并到目标分支。Squash 与 rebase、快进目标分支，然后移除 worktree。

与 `git merge` 不同，此命令会把当前分支合并到目标分支，而不是把目标分支合并到当前分支。它类似于在 GitHub 上点击“Merge pull request”，但操作在本地完成。目标默认为默认分支。

## 示例

合并到默认分支：

```
$ wt merge
◎ Running pre-merge project:test
  cargo nextest run
    Finished `test` profile [unoptimized + debuginfo] target(s) in 0.02s
     Summary [   0.002s] 2 tests run: 2 passed, 0 skipped
◎ Merging 1 commit to main @ a1b2c3d (no commit/squash/rebase needed)
  * a1b2c3d feat: add hook registration
   hook.rs | 31 +++++++++++++++++++++++++++++++
   1 file changed, 31 insertions(+)
✓ Merged to main (1 commit, 1 file, +31)
◎ Removing hooks worktree & branch in background (same commit as main, _)
○ Switched to worktree for main @ ~/repo
```

合并到其他分支：

```bash
$ wt merge develop
```

合并后保留 worktree：

```bash
$ wt merge --no-remove
```

保留提交历史（不 squash）：

```bash
$ wt merge --no-squash
```

创建合并提交——默认生成经过 rebase 的半线性历史：

```bash
$ wt merge --no-ff
```

跳过提交/squash（除非使用 --no-rebase，否则仍会运行 rebase）：

```bash
$ wt merge --no-commit
```

保留完全不变的整洁提交图及 tip：

```bash
$ wt merge --no-commit --no-rebase
```

## 流水线

`wt merge` 会运行以下步骤：

1. **提交**——运行 pre-commit hook，然后提交未提交的更改。post-commit hook 在后台运行。进行 squash（默认行为）时跳过此步骤——更改会在 squash 步骤中暂存。使用 `--no-squash` 时，这是唯一的提交步骤。
2. **Squash**——把从目标分支以来的所有提交合并为一个（类似 GitHub 的“Squash and merge”）。使用 `--stage` 控制暂存内容：`all`（默认）、`tracked` 或 `none`。纳入 squash 的工作区更改会先备份到 `refs/wt-backup/<branch>`。使用 `--no-squash` 时，各个提交会保留。
3. **Rebase**——rebase 到目标分支；无需重放时跳过（[`wt step rebase`](https://worktrunk.dev/step/#wt-step-rebase) 给出了相关条件）。发生冲突时会停止合并，并让 rebase 在 worktree 中保持进行中状态，以供解决或中止。使用 `--no-rebase` 时，会保留先前提交/squash 步骤产生的提交图，且目标分支必须能够快进到其 tip。
4. **pre-merge hook**——hook 在 rebase 之后、合并之前运行。失败会中止操作。参见 [`wt hook`](https://worktrunk.dev/hook/)。
5. **合并**——快进合并到目标分支（[`wt step push`](https://worktrunk.dev/step/#wt-step-push)）。使用 `--no-ff` 时则会创建合并提交——默认 rebase 后得到半线性历史，而显式使用 `--no-rebase` 会在添加合并提交之前保留先前步骤产生的提交图。非快进合并会被拒绝。
6. **pre-remove hook**——hook 在移除 worktree 之前运行。失败会中止操作。
7. **清理**——移除 worktree 和分支。使用 `--no-remove` 可保留 worktree。当已经位于目标分支或主 worktree 中时，会保留该 worktree。
8. **post-remove + post-merge hook**——清理后在后台运行。

使用 `--no-commit` 可跳过提交未提交的更改和 squash；默认仍会运行 rebase，并且除非传入 `--no-rebase`，否则可能改写提交。同时使用这两个 flag 会保留完全不变的源提交图，并要求目标分支是其祖先。适合在使用 `wt step commit` 手动准备提交之后使用。要求工作区干净。

`wt merge` 的目标是*本地*默认分支 ref，且绝不会 fetch。当该 ref 落后于其上游时——例如主检出位置的 `main` 落后于 `origin/main`——如果某分支基于较新的上游 tip，就会相对上游测量、squash 和 rebase（因此已在上游的提交绝不会被折叠进 squash），最终的快进会使用那些已经 fetch 的上游提交的真实 SHA，让本地 ref 一并前进。`wt step squash` 和 `wt step rebase` 采用相同的测量方式。若本地目标分支已与其上游*分叉*——既有自己的提交又落后于上游——它就无法快进，因此在目标分支完成协调之前，合并会被拒绝。

## 本地 CI

对于个人项目，pre-merge hook 带来了一种迭代快得多的工作流——可以完成数量多一个数量级的小改动，而不是较少的大改动。

过去很难在本地强制确保合并前已经运行测试。远程 CI 的价值既在流程，也在检查：它能保证验证确实发生。`wt merge` 把这项保证带到了本地。

完整工作流如下：启动一个 agent（可以同时启动多个）处理任务，自己到别处工作，等它准备好后再回来。审查 diff，运行 `wt merge`，然后继续下一项工作。pre-merge hook 会在合并前验证——如果通过，分支就会进入默认分支，并清理 worktree。

```toml
[[pre-merge]]
test = "cargo test"
lint = "cargo clippy"
```

## 命令参考

```
wt merge - Merge current branch into the target branch

Squash & rebase, fast-forward the target branch, remove the worktree.

Usage: wt merge [OPTIONS] [TARGET]

Arguments:
  [TARGET]
          Target branch

          Defaults to default branch.

Options:
      --no-squash
          Skip commit squashing

      --no-commit
          Skip commit and squash

      --no-rebase
          Skip rebase; require the target to fast-forward to the resulting tip

      --no-remove
          Keep worktree after merge

      --no-ff
          Create a merge commit (no fast-forward)

      --stage <STAGE>
          What to stage before committing [default: all]

          Possible values:
          - all:     Stage everything: untracked files + unstaged tracked changes
          - tracked: Stage tracked changes only (like git add -u)
          - none:    Stage nothing, commit only what's already in the index

  -h, --help
          Print help (see a summary with '-h')

Automation:
      --no-hooks
          Skip hooks

      --format <FORMAT>
          Output format

          JSON prints structured result to stdout after merge completes.

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
