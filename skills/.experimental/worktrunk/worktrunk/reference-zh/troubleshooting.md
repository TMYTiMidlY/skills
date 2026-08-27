> 本文是 `reference/troubleshooting.md` 的中文翻译副本，随上游同步需重译；行为以英文原文为准。

# 排障

针对常见 Worktrunk 问题的 Claude 专属排障指南。

## 提交消息生成

### 找不到命令

检查配置的工具是否已安装：

```bash
wt config show  # shows the configured command
which claude    # or: which codex, which llm, which aichat
```

如果输出为空，请安装一种受支持的工具。设置说明参见 [LLM 提交文档](https://worktrunk.dev/llm-commits/)。

### 命令返回错误

把提示词通过管道传给配置的命令，直接测试该命令。各工具的确切命令语法参见 `reference/llm-commits.md`。

```bash
echo "say hello" | <your-configured-command>
```

常见问题：
- **未设置 API key**：每种工具都有自己的身份验证机制
- **模型不可用**：通过工具的帮助信息检查模型名称
- **网络问题**：检查互联网连接

### 配置未加载

1. 查看配置路径：`wt config show` 会显示位置
2. 验证文件是否存在：`ls -la ~/.config/worktrunk/config.toml`
3. 检查 TOML 语法：`cat ~/.config/worktrunk/config.toml`
4. 查找验证错误（路径必须是相对路径，不能是绝对路径）

### 模板冲突

检查互斥选项：
- `template` 和 `template-file` 不能同时设置
- `squash-template` 和 `squash-template-file` 不能同时设置

如果使用模板文件，请验证它在指定路径中存在。

## Hook

### Hook 未运行

按顺序检查：
1. 验证 `.config/wt.toml` 是否存在：`ls -la .config/wt.toml`
2. 检查 TOML 语法（使用 `wt hook show` 查看解析后的配置）
3. 验证 hook 类型的拼写与十种类型之一匹配
4. 在 worktree 中手动测试命令

### Hook 失败

调试步骤：
1. 在 worktree 中手动运行命令以查看错误
2. 检查缺失的依赖（npm 包、系统工具）
3. 使用 `wt hook show --expanded` 验证模板变量是否正确展开（会显示每条命令及其代入后的变量）
4. 对于后台 hook，在 `.git/wt/logs/` 中查看输出

### 缓慢的阻塞 hook

把耗时较长的命令移到后台：

```toml
# Before — blocks for minutes
pre-start = "npm run build"

# After — fast setup, build in background
pre-start = "npm install"
post-start = "npm run build"
```

## 别名

### 检查别名

- `wt config alias show <name>` 输出原始模板。
- `wt config alias dry-run <name> [-- args...]` 输出渲染后的命令，但不运行。

### `for-each` 或 `--execute` 别名在每个 worktree 中都使用相同的值

别名主体会在分派时、调用命令的 worktree 中渲染一次，因此 `{{ branch }}` 这类每个 worktree 各异的变量，会在嵌套 `wt` 命令迭代之前就被固化。如果 `wt config alias dry-run <name>` 显示的是一个已经代入的值（例如 `… echo branch=main`），说明它是在第一次渲染时固化的。请用 `{% raw %}{{ branch }}{% endraw %}` 推迟展开；对于 `for-each`，还要把它放在带引号的 `sh -c '...'` 中，以免别名的 shell 按单词拆分它。`{{ default_branch }}` 这类仓库级变量不受影响——它们在每个 worktree 中都相同。参见 `reference/extending.md#deferring-expansion-to-a-nested-wt-command`。

## 列表

### `wt list` 在 120 秒后超时

超时警告会列出未完成的任务：

```
wt list timed out after 120s (170 results received); blocked tasks:
  <branch>: working-tree-diff, working-tree-conflicts
```

这两项任务都会先运行 `git status --porcelain`。当列出的 worktree 设置了 `core.fsmonitor=true`，且其 `git fsmonitor--daemon` 卡死时，`git status` 会一直阻塞，直到 IPC 尝试失败（需要数分钟），而 120 秒的清空等待期限会先到。

在受影响的 worktree 中运行 `git status` 进行确认：

```bash
cd <worktree>
time git --no-optional-locks status --porcelain
# error: could not read IPC response   → hung daemon
```

列出正在运行的守护进程及其 IPC 套接字（可据此识别每个守护进程服务的 worktree）：

```bash
for pid in $(pgrep -f 'git fsmonitor--daemon'); do
  sock=$(lsof -p $pid 2>/dev/null | grep 'fsmonitor--daemon.ipc' | awk '{print $NF}' | head -1)
  printf "%6d  %s\n" "$pid" "$sock"
done
```

仅显示为 `fsmonitor--daemon.ipc`、没有解析后路径的套接字属于已删除的 worktree。任何一次 `wt remove` 都会清理这些进程：它会终止被移除 worktree 自己的守护进程，并清扫其 worktree 已不存在的守护进程，包括因 `git worktree remove` 或 `rm -rf` 而成为孤儿的进程（机制详情参见：[Worktrunk 可以删除什么？](https://worktrunk.dev/faq/#what-can-worktrunk-delete)）。

两条路径都会特意保留的剩余情形，是某个从未被移除的*仍存在* worktree 上有卡死的守护进程：该 worktree 中的 `git status` 会因无响应的 IPC 而阻塞，但守护进程仍服务于真实存在的 worktree，所以隐式回收它不在处理范围内。请手动终止它：kill 掉套接字路径与该 worktree 匹配的守护进程，或者运行 `pkill -9 -f 'git fsmonitor--daemon'`，让下一次 `wt list` 重新生成仍需运行的守护进程。

## Windows 上的 PowerShell

### 未创建 PowerShell profile

在 Windows 上，从 cmd.exe 或 PowerShell 运行时，`wt config shell install` 会自动创建 PowerShell profile。它会同时创建：
- `Documents/PowerShell/Microsoft.PowerShell_profile.ps1`（PowerShell 7+/pwsh）
- `Documents/WindowsPowerShell/Microsoft.PowerShell_profile.ps1`（Windows PowerShell 5.1）

**如果从 Git Bash 或 MSYS2 运行**，则会跳过 PowerShell，因为设置了 `SHELL` 环境变量。要显式创建 PowerShell profile，请运行：

```bash
wt config shell install powershell
```

### 配置了错误的 PowerShell 变体

从 Windows 原生 shell 安装时，会创建两个 profile 文件。这样无论用户之后打开哪一种 PowerShell，shell 集成都可以工作。未使用时，这些 profile 文件很小且无害。

### Shell 集成已配置但未激活

当 `wt config show` 显示 profile 行已配置，但 shell 集成
“未激活”时，请让用户在同一个 PowerShell
会话中运行以下诊断：

1. `Get-Command git-wt -All`——显示包装器 Function 是否已与
   Application（exe）一同加载。如果只出现 Application，说明 profile
   没有定义该 function（请重启 shell，或者 profile 加载失败）。

2. `(Get-Command git-wt -CommandType Function).ScriptBlock | Select-String
   WORKTRUNK`——验证 wrapper function 主体是否设置
   `WORKTRUNK_DIRECTIVE_CD_FILE`。如果没有出现，说明 function
   不完整或已损坏。

3. `Get-Command git-wt -CommandType Application | Select-Object Source`——显示
   包装器将什么解析为 `$wtBin`。如果为空，包装器就找不到
   二进制文件，并会静默失败。

### 检测逻辑

Worktrunk 通过检查是否**未**设置 `SHELL` 环境变量，来检测 Windows 原生 shell（cmd/PowerShell）：
- 未设置 `SHELL` → Windows 原生 shell → 创建两个 PowerShell profile
- 已设置 `SHELL`（例如 `/usr/bin/bash`）→ Git Bash/MSYS2 → 跳过 PowerShell
