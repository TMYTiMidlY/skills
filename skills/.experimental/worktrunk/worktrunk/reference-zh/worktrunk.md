> 本文是 `reference/worktrunk.md` 的中文翻译副本，随上游同步需重译；行为以英文原文为准。

# Worktrunk

Worktrunk 是用于管理 git worktree 的 CLI，专为并行运行 AI agent
而设计。

Worktrunk 的三个核心命令让 worktree 像分支一样易用。
此外，Worktrunk 还提供许多改善使用体验的功能，简化对大量
并行更改的处理，其中包括用于自动化本地工作流的 hook。

快速演示：

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
      <td>wt switch feat</td>
      <td>cd ../repo.feat</td>
    </tr>
    <tr>
      <td>创建并启动 Claude</td>
      <td>wt switch -c -x claude feat</td>
      <td>git worktree add -b feat ../repo.feat && \
cd ../repo.feat && \
claude</td>
    </tr>
    <tr>
      <td>清理</td>
      <td>wt remove</td>
      <td>cd ../repo && \
git worktree remove ../repo.feat && \
git branch -d feat</td>
    </tr>
    <tr>
      <td>列出并显示状态</td>
      <td>wt list</td>
      <td>git worktree list（仅路径）</td>
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

也可以禁用 Windows Terminal 的别名（Settings → Apps → Advanced app settings → App execution aliases → “Terminal”/“Terminal Preview”），以直接使用 `wt`。

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

```bash
$ wt switch --create feature-auth
<span class=g>✓</span> <span class=g>Created branch <b>feature-auth</b> from <b>main</b> and worktree @ <b>~/repo.feature-auth</b></span>
```

这会创建新分支和 worktree，然后切换到其中。完成工作后，使用 [`wt list`](https://worktrunk.dev/list/) 检查所有 worktree：

```bash
$ wt list
  <b>Branch</b>        <b>Status</b>        <b>HEAD±</b>    <b>main↕</b>     <b>main…±</b>  <b>Remote⇅</b>  <b>Commit</b>   <b>Age</b>   <b>Message</b>
@ feature-auth  <span class=c>+</span>   <span class=d>↑</span>      <span class=g>+27</span>   <span class=r>-8</span>   <span class=g>↑1</span>       <span class=g>+31</span>                <span class=d>4bc72dc</span>  <span class=d>2h</span>    <span class=d>Add authenticati…</span>
^ main              <span class=d>^</span><span class=d>⇡</span>                                    <span class=g>⇡1</span>      <span class=d>0e631ad</span>  <span class=d>1d</span>    <span class=d>Initial commit</span>

<span class=d>○</span> <span class=d>Showing 2 worktrees, 1 with changes, 1 ahead, 1 column hidden</span>
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

```bash
$ wt merge main
<span class=c>◎</span> <span class=c>Generating commit message and committing changes... <span style='color:var(--bright-black,#555)'>(2 files, <span class=g>+53</span></span></span>, no squashing needed<span style='color:var(--bright-black,#555)'>)</span>
<span style='background:var(--bright-white,#fff)'> </span> <b>Add authentication module</b>
<span class=g>✓</span> <span class=g>Committed changes @ <span class=d>a1b2c3d</span></span>
<span class=c>◎</span> <span class=c>Merging 1 commit to <b>main</b> @ <span class=d>a1b2c3d</span> (no rebase needed)</span>
<span style='background:var(--bright-white,#fff)'> </span> * <span style='color:var(--yellow,#a60)'>a1b2c3d</span> Add authentication module
<span style='background:var(--bright-white,#fff)'> </span>  auth.rs | 51 <span class=g>+++++++++++++++++++++++++++++++++++++++++++++++++++</span>
<span style='background:var(--bright-white,#fff)'> </span>  lib.rs  |  2 <span class=g>++</span>
<span style='background:var(--bright-white,#fff)'> </span>  2 files changed, 53 insertions(+)
<span class=g>✓</span> <span class=g>Merged to <b>main</b> <span style='color:var(--bright-black,#555)'>(1 commit, 2 files, <span class=g>+53</span></span></span><span style='color:var(--bright-black,#555)'>)</span>
<span class=c>◎</span> <span class=c>Removing <b>feature-auth</b> worktree &amp; branch in background (same commit as <b>main</b>,</span> <span class=d>_</span><span class=c>)</span>
<span class=d>○</span> Switched to worktree for <b>main</b> @ <b>~/repo</b>
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
