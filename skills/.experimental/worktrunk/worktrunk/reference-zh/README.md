> 本文是 `reference/README.md` 的中文翻译副本，随上游同步需重译；行为以英文原文为准。

<!-- markdownlint-disable MD033 -->

<h1>Worktrunk</h1>

<!-- Crates.io badge below disabled while shields.io is rate-limited by crates.io
     (renders "CRATES.IO: INVALID"). Tracking: badges/shields#11879. Restore once fixed.
     [![Crates.io](https://img.shields.io/crates/v/worktrunk?style=for-the-badge&logo=rust)](https://crates.io/crates/worktrunk)
-->
[![Docs](https://img.shields.io/badge/docs-worktrunk.dev-blue?style=for-the-badge&logo=gitbook)](https://worktrunk.dev)
[![License: MIT OR Apache-2.0](https://img.shields.io/badge/license-MIT%20OR%20Apache--2.0-blue?style=for-the-badge)](https://opensource.org/licenses/MIT)
[![CI](https://img.shields.io/github/actions/workflow/status/max-sixty/worktrunk/ci.yaml?event=push&branch=main&style=for-the-badge&logo=github)](https://github.com/max-sixty/worktrunk/actions?query=branch%3Amain+workflow%3Aci)
[![Codecov](https://img.shields.io/codecov/c/github/max-sixty/worktrunk?style=for-the-badge&logo=codecov)](https://codecov.io/gh/max-sixty/worktrunk)
[![Stars](https://img.shields.io/github/stars/max-sixty/worktrunk?style=for-the-badge&logo=github)](https://github.com/max-sixty/worktrunk/stargazers)
[![maintained with tend](https://img.shields.io/badge/maintained_with-tend-bba580?style=for-the-badge&logo=data:image/svg%2bxml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxNiAxNiI+PGcgdHJhbnNmb3JtPSJ0cmFuc2xhdGUoMCwxNikgc2NhbGUoMC4wMTI1LC0wLjAxMjUpIiBmaWxsPSIjZmZmIiBzdHJva2U9Im5vbmUiPjxwYXRoIGQ9Ik02ODAgMTEyOCBjNjIgLTk2IDY5IC0xNzggMjAgLTI0MSAtMTcgLTIyIC0yMCAtNDAgLTIwIC0xMzQgbDEgLTEwOCAyMSAyOCBjMTEgMTYgMzAgNDcgNDIgNzAgMTIgMjIgMzIgNDkgNDYgNTkgMzcgMjcgMTE0IDM4IDE4NCAyNyA5MyAtMTUgOTQgLTE4IDQ0IC03OSAtNzIgLTg4IC0xMDkgLTExMyAtMTc2IC0xMTcgLTMxIC0yIC02NCAxIC03MiA2IC0yMyAxNSAyMSA1NiAxMDcgOTggNDAgMjAgNzEgMzggNjkgNDAgLTYgNyAtODggLTE3IC0xMjYgLTM3IC00OSAtMjUgLTEwMCAtNzggLTEyMSAtMTI1IC0xNSAtMzMgLTE5IC02NiAtMTkgLTE4OCAwIC0xNTcgOCAtMTk1IDUwIC0yMzIgMTcgLTE2IDM2IC0yMCA4NSAtMTkgNjIgMSA2MyAxIDczIC0zMiA5IC0zMiA5IC0zMyAtMjIgLTQwIC01MCAtMTIgLTEzMiAtNyAtMTY0IDEwIC00MCAyMSAtNzkgNjkgLTkyIDExNCAtNSAyMCAtMTAgMTAyIC0xMCAxODIgMCA4MCAtNSAxNjIgLTExIDE4NCAtMjIgNzkgLTEzNSAxNjYgLTIzNCAxODEgLTM3IDYgLTM1IDMgMzAgLTI4IDc4IC0zOSAxNDQgLTkxIDEzMiAtMTA0IC01IC00IC0zNyAtOCAtNzEgLTggLTc3IDAgLTExNyAyNCAtMTgyIDEwOSAtNTIgNjggLTUxIDcwIDQyIDg1IDcxIDExIDE0MyAwIDE4MyAtMjkgMTYgLTExIDQwIC00MyA1NCAtNzMgMTMgLTI5IDMyIC01OSA0MSAtNjYgMTQgLTEyIDE2IC03IDE2IDU4IDAgNTkgNCA3NyAyMyAxMDIgMTkgMjYgMjMgNDYgMjUgMTMwIDMgNjcgMCA5OSAtNyA5OSAtNyAwIC0xMSAtMjMgLTEyIC01NyAwIC0zMiAtNiAtNzYgLTEyIC05NyBsLTEyIC00MCAtMjcgMzIgYy0zNCA0MSAtNDMgOTYgLTI0IDE1MSAxNCA0MSA3NSAxNDEgODYgMTQxIDMgMCAyMSAtMjQgNDAgLTUyeiIvPjwvZz48L3N2Zz4K)](https://github.com/max-sixty/tend)

> **2026 年 8 月**：Worktrunk 于年初[发布](https://x.com/max_sixty/status/2006077845391724739?s=20)，并迅速成为最受欢迎的 git worktree 管理器。它倾注了心血打造（没有粗制滥造！）。遇到任何不便都请告诉我；我正全力持续改善 Worktrunk，而最大的帮助就是大家把自己发现的问题发布出来。

Worktrunk 是用于管理 git worktree 的 CLI，专为并行运行 AI agent 而设计。

Worktrunk 的三个核心命令让 worktree 像分支一样易用。此外，Worktrunk 还提供许多改善使用体验的功能，简化对大量并行更改的处理，其中包括用于自动化本地工作流的 hook。

快速演示：

![Worktrunk Demo](https://cdn.jsdelivr.net/gh/max-sixty/worktrunk-assets@main/assets/docs/light/wt-core.gif)

> ### 📚 完整文档见 [worktrunk.dev](https://worktrunk.dev) 📚

<!-- ⚠️ AUTO-GENERATED from docs/content/worktrunk.md#context-git-worktrees..worktrunk-makes-git-worktrees-as-easy-as-branches — edit source to update -->

## 背景：git worktree

Claude Code 和 Codex 等 AI agent 无需监督也能处理较长的任务，
因此可以同时管理 5–10 个甚至更多 agent。Git 的原生
worktree 功能会为每个 agent 提供独立的工作目录，避免彼此的更改
发生冲突。

但 git worktree 的 UX 很繁琐。即使只是启动一个新的
worktree，也需要输入三次分支名：`git worktree add -b feat
../repo.feat`，然后运行 `cd ../repo.feat`。

## Worktrunk 让 git worktree 像分支一样易用

worktree 通过分支名寻址；路径根据可配置模板计算。接受分支的命令也接受该分支检出所在 worktree 的路径。

> 从核心命令开始

**核心命令：**

<table class="cmd-compare">
  <thead>
    <tr>
      <th>任务</th>
      <th>Worktrunk</th>
      <th>原生 git</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>切换 worktree</td>
      <td><pre>wt switch feat</pre></td>
      <td><pre>cd ../repo.feat</pre></td>
    </tr>
    <tr>
      <td>创建并启动 Claude</td>
      <td><pre>wt switch -c -x claude feat</pre></td>
      <td><pre>git worktree add -b feat ../repo.feat && \
cd ../repo.feat && \
claude</pre></td>
    </tr>
    <tr>
      <td>清理</td>
      <td><pre>wt remove</pre></td>
      <td><pre>cd ../repo && \
git worktree remove ../repo.feat && \
git branch -d feat</pre></td>
    </tr>
    <tr>
      <td>列出并显示状态</td>
      <td><pre>wt list</pre></td>
      <td><pre>git worktree list</pre>（仅路径）</td>
    </tr>
  </tbody>
</table>

> 根据需要逐步使用更高级的命令

**工作流自动化：**

- **[Hook](https://worktrunk.dev/hook/)**——在创建、pre-merge、post-merge 等时机运行命令
- **[LLM 提交消息](https://worktrunk.dev/llm-commits/)**——根据 diff 生成提交消息
- **[合并工作流](https://worktrunk.dev/merge/)**——用一个命令完成 squash、rebase、合并和清理
- **[交互式选择器](https://worktrunk.dev/switch/#interactive-picker)**——浏览 worktree，并实时预览 diff 和日志
- **[复制构建缓存](https://worktrunk.dev/step/#wt-step-copy-ignored)**——在 worktree 之间共享 `target/`、`node_modules/` 等，跳过冷启动
- **[`wt list --full`](https://worktrunk.dev/list/#full-mode)**——每个分支的 [CI 状态](https://worktrunk.dev/list/#ci-status)和[由 AI 生成的摘要](https://worktrunk.dev/list/#llm-summaries)
- **[PR 检出](https://worktrunk.dev/switch/#pull-requests-and-merge-requests)**——使用 `wt switch pr:123` 直接跳转到 PR 的分支
- **[每个 worktree 一个开发服务器](https://worktrunk.dev/tips-patterns/#dev-server-per-worktree)**——`hash_port` 模板过滤器为每个 worktree 提供唯一端口
- **[别名](https://worktrunk.dev/extending/#aliases)与[每分支变量](https://worktrunk.dev/config/#wt-config-state-vars)**——自定义 `wt <name>` 命令，以及供 hook 模板使用的分支作用域状态
- ……以及**[更多功能](#next-steps)**

多个并行 agent，同样简单的命令：

![Worktrunk omnibus demo: multiple Claude agents in Zellij tabs with hooks, LLM commits, and merge workflow](https://raw.githubusercontent.com/max-sixty/worktrunk-assets/main/assets/docs/light/wt-zellij-omnibus.gif)

<!-- END AUTO-GENERATED -->

<!-- ⚠️ AUTO-GENERATED from docs/content/worktrunk.md#install..further-reading — edit source to update -->

## 安装

**Homebrew（macOS 与 Linux）：**

```bash
brew install worktrunk && wt config shell install
```

Shell 集成允许命令更改目录。

**Cargo：**

```bash
cargo install worktrunk && wt config shell install
```

<details>
<summary><strong>Windows 与其他平台</strong></summary>

**Windows。** `wt` 默认是 Windows Terminal 的命令，因此 Winget 还会把 Worktrunk 安装为 `git-wt`，以避免冲突：

```bash
winget install max-sixty.worktrunk
git-wt config shell install
```

也可以禁用 Windows Terminal 的别名（Settings → Apps → Advanced app settings → App execution aliases → "Terminal"/"Terminal Preview"），以直接使用 `wt`。

**Arch Linux：**

```bash
sudo pacman -S worktrunk && wt config shell install
```

**Conda / Pixi**（由社区维护的 [feedstock](https://github.com/conda-forge/worktrunk-feedstock)）：

```bash
conda install -c conda-forge worktrunk && wt config shell install
```

或者使用 [Pixi](https://pixi.sh)：`pixi global install worktrunk && wt config shell install`。

</details>

## 快速开始

为新功能创建 worktree：

```console
$ wt switch --create feature-auth
✓ Created branch feature-auth from main and worktree @ ~/repo.feature-auth

```

这会创建新分支和 worktree，然后切换到其中。完成工作后，使用 [`wt list`](https://worktrunk.dev/list/) 检查所有 worktree：

```console
$ wt list
  Branch        Status        HEAD±    main↕     main…±  Remote⇅  Commit   Age   Message
@ feature-auth  +   ↑      +27   -8   ↑1       +31                4bc72dc  2h    Add authenticati…
^ main              ^⇡                                    ⇡1      0e631ad  1d    Initial commit

○ Showing 2 worktrees, 1 with changes, 1 ahead, 1 column hidden

```

`@` 标记当前 worktree。`+` 表示已暂存的更改，`↑1` 表示领先 main 1 个提交，`⇡` 表示有尚未 push 的提交。

完成后，可选择：

**PR 工作流**——提交、push、发起 PR、通过 GitHub/GitLab 合并，然后清理：

```bash
wt step commit                    # commit staged changes
gh pr create                      # or glab mr create
wt remove                         # after PR is merged
```

**本地合并**——squash、rebase 到 main、快进合并，然后清理：

```console
$ wt merge main
◎ Generating commit message and committing changes... (2 files, +53, no squashing needed)
  Add authentication module
✓ Committed changes @ a1b2c3d
◎ Merging 1 commit to main @ a1b2c3d (no rebase needed)
  * a1b2c3d Add authentication module
   auth.rs | 51 +++++++++++++++++++++++++++++++++++++++++++++++++++
   lib.rs  |  2 ++
   2 files changed, 53 insertions(+)
✓ Merged to main (1 commit, 2 files, +53)
◎ Removing feature-auth worktree & branch in background (same commit as main, _)
○ Switched to worktree for main @ ~/repo

```

对于并行 agent，可以创建多个 worktree，并在每个 worktree 中启动一个 agent：

```bash
wt switch -x claude -c feature-a -- 'Add user authentication'
wt switch -x claude -c feature-b -- 'Fix the pagination bug'
wt switch -x claude -c feature-c -- 'Write tests for the API'
```

`-x` flag 会在切换后运行一条命令；`--` 之后的参数会传给该命令。配置 [post-start hook](https://worktrunk.dev/hook/#hook-types) 可自动执行设置（安装依赖、启动开发服务器）。

## <a id="next-steps"></a>后续步骤

- 学习核心命令：[`wt switch`](https://worktrunk.dev/switch/)、[`wt list`](https://worktrunk.dev/list/)、[`wt merge`](https://worktrunk.dev/merge/)、[`wt remove`](https://worktrunk.dev/remove/)
- 设置 [hook](https://worktrunk.dev/hook/) 以自动完成设置
- 探索 [LLM 提交消息](https://worktrunk.dev/llm-commits/)、[交互式
  选择器](https://worktrunk.dev/switch/#interactive-picker)、[Claude Code 集成](https://worktrunk.dev/claude-code/)、[CI
  状态与 PR 链接](https://worktrunk.dev/list/#ci-status)
- 浏览[技巧与模式](https://worktrunk.dev/tips-patterns/)中的方案：别名、开发服务器、数据库、agent 交接等
- [扩展 Worktrunk](https://worktrunk.dev/extending/)——使用 hook 和别名自定义工作流
- 运行 `wt --help` 或 `wt <command> --help`，快速查看 CLI 参考

## 延伸阅读

- [Claude Code：Agentic coding 最佳实践](https://www.anthropic.com/engineering/claude-code-best-practices)——Anthropic 的官方指南，其中包括 worktree 模式
- [使用 Claude Code 和 Git Worktrees 加快交付](https://incident.io/blog/shipping-faster-with-claude-code-and-git-worktrees)——incident.io 的并行 agent 工作流
- [Git worktree 模式讨论](https://github.com/anthropics/claude-code/issues/1052)——Claude Code 仓库中的社区讨论
- [@DevOpsToolbox 的 Worktrunk 视频](https://youtu.be/WBQiqr6LevQ?t=345)
- [git-worktree 文档](https://git-scm.com/docs/git-worktree)——git 官方参考

<!-- END AUTO-GENERATED -->

## 贡献

- ⭐ 为仓库加 Star
- 向朋友介绍 Worktrunk
- [提交 issue](https://github.com/max-sixty/worktrunk/issues/new?title=&body=%23%23%20Description%0A%0A%3C!--%20Describe%20the%20bug%20or%20feature%20request%20--%3E%0A%0A%23%23%20Context%0A%0A%3C!--%20Any%20relevant%20context%3A%20your%20workflow%2C%20what%20you%20were%20trying%20to%20do%2C%20etc.%20--%3E)——反馈、功能请求，哪怕只是小小的不便或不够理想的用户消息，或[尚未解决的 worktree 痛点](https://github.com/max-sixty/worktrunk/issues/new?title=Worktree%20friction%3A%20&body=%23%23%20The%20friction%0A%0A%3C!--%20What%20worktree-related%20task%20is%20still%20painful%3F%20--%3E%0A%0A%23%23%20Current%20workaround%0A%0A%3C!--%20How%20do%20you%20handle%20this%20today%3F%20--%3E%0A%0A%23%23%20Ideal%20solution%0A%0A%3C!--%20What%20would%20make%20this%20easier%3F%20--%3E)
- 分享：[X](https://twitter.com/intent/tweet?text=Worktrunk%20%E2%80%94%20CLI%20for%20git%20worktree%20management&url=https%3A%2F%2Fworktrunk.dev) · [Reddit](https://www.reddit.com/submit?url=https%3A%2F%2Fworktrunk.dev&title=Worktrunk%20%E2%80%94%20CLI%20for%20git%20worktree%20management) · [LinkedIn](https://www.linkedin.com/sharing/share-offsite/?url=https%3A%2F%2Fworktrunk.dev)

> ### 📚 完整文档见 [worktrunk.dev](https://worktrunk.dev) 📚

### Star 历史

<a href="https://star-history.com/#max-sixty/worktrunk&Date">
  <img src="https://api.star-history.com/svg?repos=max-sixty/worktrunk&type=Date" width="500" alt="Star History Chart">
</a>
