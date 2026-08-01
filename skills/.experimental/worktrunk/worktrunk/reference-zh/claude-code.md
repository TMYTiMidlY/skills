> 本文是 `reference/claude-code.md` 的中文翻译副本，随上游同步需重译；行为以英文原文为准。

# Agent 集成

Worktrunk 为每个受支持的 agent CLI 提供一个插件。插件能提供什么，取决于该 CLI 暴露的 hook：

| 能力 | Claude Code | Codex | OpenCode | Gemini CLI |
|---|:-:|:-:|:-:|:-:|
| 配置 skill | ✓ | ✓ |  | ✓ |
| 活动跟踪（`wt list` 中的 🤖/💬） | ✓ | ✓ | ✓ | ✓ |
| worktree 隔离 | ✓ |  |  |  |
| `/wt-switch-create` 命令 | ✓ |  |  |  |

配置 skill 是供 agent 阅读的文档，帮助其设置 LLM 提交、hook 和排障。活动跟踪会显示哪些 worktree 中有正在运行的会话。worktree 隔离需要 worktree 生命周期 hook，而 `/wt-switch-create` 需要切换会话工作目录——这两项都仅由 Claude Code 支持，因此 Codex、OpenCode 和 Gemini 用户需直接调用 `wt switch --create` 和 `wt remove`。Codex 通过自身的 `Stop` 和 `SessionEnd` hook 跟踪活动。

## 安装

### Claude Code

```bash
wt config plugins claude install
```

等效的手动操作：

```bash
claude plugin marketplace add max-sixty/worktrunk
claude plugin install worktrunk@worktrunk
```

### Codex

```bash
wt config plugins codex install
```

这会在 Codex 中配置 Worktrunk marketplace。然后在 Codex 中运行 `/plugins`，并从 marketplace 安装 Worktrunk。等效的手动操作：

```bash
codex plugin marketplace add max-sixty/worktrunk
```

要移除 marketplace 条目，请运行 `wt config plugins codex uninstall`。已经安装的插件不会更改。

### OpenCode

```bash
wt config plugins opencode install
```

这会把活动跟踪插件写入 OpenCode 的全局插件目录 `~/.config/opencode/plugins/worktrunk.ts`（遵循 `$OPENCODE_CONFIG_DIR` 和 `$XDG_CONFIG_HOME`）。`wt config plugins opencode uninstall` 会移除它。

### Gemini CLI

```bash
gemini extensions install https://github.com/max-sixty/worktrunk
```

Gemini 会直接从仓库原生加载扩展，因此没有 `wt` 包装器。`gemini extensions uninstall worktrunk` 会移除它。

## 配置 skill

借助 `/worktrunk` skill，agent 可以协助：

- 设置由 LLM 生成的提交消息
- 添加项目 hook（pre-start、pre-merge、pre-commit）
- 配置 worktree 路径模板
- 修复 shell 集成问题

Claude Code 被设计为在检测到 Worktrunk 相关问题时自动加载该 skill。

## 活动跟踪

Claude Code、Codex、OpenCode 和 Gemini 插件会跟踪 agent 会话，并在 `wt list` 中显示状态标记：

```bash
$ wt list
  <b>Branch</b>       <b>Status</b>        <b>HEAD±</b>    <b>main↕</b>     <b>main…±</b>  <b>Remote⇅</b>  <b>Path</b>                 <b>Commit</b>   <b>Age</b>   <b>Message</b>
@ main             <span class=d>^</span><span class=d>⇡</span>                                    <span class=g>⇡1</span>      .                    <span class=d>33323bc</span>  <span class=d>1d</span>    <span class=d>Initial commit</span>
+ feature-api      <span class=d>↑</span> 🤖              <span class=g>↑1</span>        <span class=g>+1</span>                ../repo.feature-api  <span class=d>70343f0</span>  <span class=d>1d</span>    <span class=d>Add REST API endpoints</span>
+ review-ui      <span class=c>?</span> <span class=d>↑</span> 💬              <span class=g>↑1</span>        <span class=g>+1</span>                ../repo.review-ui    <span class=d>a585d6e</span>  <span class=d>1d</span>    <span class=d>Add dashboard component</span>
+ wip-docs       <span class=c>?</span> <span class=d>–</span>                                             ../repo.wip-docs     <span class=d>33323bc</span>  <span class=d>1d</span>    <span class=d>Initial commit</span>

<span class=d>○</span> <span class=d>Showing 4 worktrees, 2 with changes, 2 ahead</span>
```

- 🤖——agent 正在工作
- 💬——agent 正在等待或空闲

所有四个插件都会在会话结束时清除标记。如果 agent 进程在其会话结束 hook 运行前被终止，可能会留下过期标记。无论哪种情况，`wt config state marker clear` 都可以手动移除标记。

### 手动状态标记

可为任意工作流手动设置状态标记：

```bash
$ wt config state marker set "🚧"                   # Current branch
$ wt config state marker set "✅" --branch feature  # Specific branch
$ git config worktrunk.state.feature.marker '{"marker":"💬","set_at":0}'  # Direct
```

## worktree 隔离（仅 Claude Code）

Claude Code agent 可以在隔离的 worktree（`isolation: "worktree"`）中运行。默认情况下，Claude Code 使用 `git worktree add` 创建这些 worktree。插件的 `WorktreeCreate` 和 `WorktreeRemove` hook 会把此过程改为通过 `wt switch --create` 和 `wt remove` 完成，因此由 agent 创建的 worktree 会采用 Worktrunk 的命名约定、hook 和生命周期管理。

## `/wt-switch-create` 命令（仅 Claude Code）

`/wt-switch-create [<branch>] [<repo>] [-- <task>]` 会在不离开会话的情况下，于全新 worktree 中启动任务：它会创建 worktree、切换到其中并运行任务（所有参数均可选）。该 worktree 会显示在 `wt list` 中；使用 `wt merge` / `wt remove` 合并或移除它。

## 状态栏（仅 Claude Code）

`wt list statusline --format=claude-code` 会为 Claude Code 状态栏输出单行状态。Claude Code 在后台运行它，因此偶尔需要 1–2 秒的 CI 获取过程不会被察觉。

<code>~/w/myproject.feature-auth  !🤖  @<span style='color:#0a0'>+42</span> <span style='color:#a00'>-8</span>  <span style='color:#0a0'>↑3</span>  <span style='color:#0a0'>⇡1</span>  <span style='color:#0a0'>#3035</span>  Opus  🌔 65%  <span style='color:#a70'>1.4×(10am–3pm)</span></code>

worktree 状态来自 [`wt list`](https://worktrunk.dev/list/) 渲染的同一组单元格；Claude Code 的标准输入 JSON 会加入模型、`🌔 65%` 上下文用量指示和速率限制进度提示。[`wt list statusline`](https://worktrunk.dev/list/#wt-list-statusline) 记录了每一段、链接行为及其背后的 JSON 字段。

添加到 `~/.claude/settings.json`：

```json
{
  "statusLine": {
    "type": "command",
    "command": "wt list statusline --format=claude-code"
  }
}
```
