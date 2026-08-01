> 本文是 `reference/faq.md` 的中文翻译副本，随上游同步需重译；行为以英文原文为准。

# FAQ

## Worktrunk 与其他方案相比如何？

### 与切换分支相比

切换分支只使用一个目录：一个 agent 的未提交更改会与下一个 agent 的工作混在一起，或者直接阻止切换。worktree 为每个 agent 提供独立目录，文件和索引彼此独立。

### 与原生 `git worktree` 相比

Git 内置的 worktree 命令能用，但需要手动管理生命周期：

```bash
# Plain git worktree workflow
$ git worktree add -b feature-branch ../myapp-feature main
$ cd ../myapp-feature
# ...work, commit, push...
$ cd ../myapp
$ git merge feature-branch
$ git worktree remove ../myapp-feature
$ git branch -d feature-branch
```

Worktrunk 会自动完成整个生命周期：

```bash
$ wt switch --create feature-branch  # Creates worktree, runs setup hooks
# ...work...
$ wt merge                            # Merges into default branch, cleans up
```

无需先 cd 回 main——`wt merge` 从功能 worktree 中运行，并像 GitHub 的合并按钮一样合并到目标分支。

`git worktree` 不提供的功能：

- 一致的目录命名和清理验证
- 项目专属自动化（安装依赖、启动服务）
- 所有 worktree 的统一状态（提交、CI、冲突、更改）

### 与 git-machete / git-town 相比

作用范围不同：

- **git-machete**：在单个目录中管理分支栈
- **git-town**：在单个目录中自动化 Git 工作流
- **Worktrunk**：使用 hook 和状态聚合管理多个 worktree

这些工具可以组合使用——在各个 worktree 中运行 git-machete 或 git-town 即可。

### 与 Git TUI（lazygit、gh-dash 等）相比

Git TUI 操作单个仓库。Worktrunk 管理多个 worktree、运行自动化 hook，并聚合各分支的状态。TUI 可在每个 worktree 目录中使用。

## Worktrunk 支持堆叠分支吗？

不原生支持——堆叠分支工作流涉及很大的设计空间，因此 Worktrunk 把它视为扩展，而不是内置功能。[`worktrunk-sync`](https://github.com/pablospe/worktrunk-sync) 是一个社区工具，它会根据 git 历史自动检测分支依赖树，并按拓扑顺序把每个分支 rebase 到其父分支。使用 `cargo install worktrunk-sync` 安装，然后以 `wt sync` 运行（通过[自定义子命令](https://worktrunk.dev/extending/#custom-subcommands)）。

## 如何把未提交的更改移动到新 worktree？

Stash 更改，创建 worktree，然后 pop：

```bash
$ git stash push -u           # -u also stashes untracked files
$ wt switch --create feature  # new branch off the default branch
$ git stash pop               # changes reappear in the new worktree
```

stash 位于共享的 `.git` 目录中，因此可以从新 worktree 访问。原分支会保持干净。

`wt switch --create` 会让新分支基于默认分支。若要改为基于当前提交，请传入 `--base=@`（当前分支拥有默认分支之外的提交时需要这样做）。

## 我的 shell 设置有问题

如果 shell 集成不工作（没有自动 cd、缺少补全、未把 `wt` 识别为函数），最快的修复方式是使用装有 Worktrunk 插件的 Claude Code：

1. 在 Claude Code 中安装 [Worktrunk plugin](https://worktrunk.dev/claude-code/)
2. 请 Claude 调试 Worktrunk shell 集成

Claude 会运行 `wt config show`、检查 shell 配置文件并找出问题。

如果 Claude 无法修复，请[提交 issue](https://github.com/max-sixty/worktrunk/issues/new?title=Shell%20setup%20issue&body=%23%23%20Shell%20and%20OS%0A%0A-%20Shell%3A%20%0A-%20OS%3A%20%0A%0A%23%23%20Output%20of%20%60wt%20config%20show%60%0A%0A%60%60%60%0A%0A%60%60%60%0A%0A%23%23%20What%20Claude%20found%20%28if%20available%29%0A%0A)，并附上 `wt config show` 的输出、shell（bash/zsh/fish）和操作系统。（即使问题得以修复，也欢迎提交 issue：非标准的成功案例有助于确保其他人也能轻松设置 Worktrunk。）

## `-v` / `-vv` 有什么作用？

共有三个详细程度级别。每一级都包含前一级的全部内容。

| 级别 | Stderr | 文件（`.git/wt/logs/`） | 使用场景 |
|-------|--------|-------------------------|----------|
| （无） | 仅警告 | — | 正常使用 |
| `-v` | + 信息：hook 输出、别名模板变量解析 | — | 调试 hook/别名 |
| `-vv` | 与 `-v` 相同 | + `trace.log`、`trace.jsonl`、`subprocess.log`、`diagnostic.md` | 提交缺陷报告 |

使用 `-vv` 时，调试级别记录（命令行、进程内 span、有界的子进程预览）会写入 `trace.log`，而不是 stderr——这样终端仍保持可读，深度跟踪记录则落到磁盘。stderr 上的一行提示会指出文件的保存位置。

这些 `-vv` 文件面向不同对象：`trace.log` 是供人阅读的跟踪记录（有界、适合放到 gist），`trace.jsonl` 是供机器处理的相同记录，`subprocess.log` 是不设上限的原始子进程输出，`diagnostic.md` 是缺陷报告包。每一项都在 [`wt config state logs`](https://worktrunk.dev/config/#wt-config-state-logs) 中说明。

设置后，`RUST_LOG` 会覆盖 flag 的基准级别（`RUST_LOG=debug wt -v` 会把 `-v` 提升为在 stderr 输出 debug）。

这些 flag 只能传给你手动输入的命令；shell 补全作为独立进程运行，没有地方传入 flag。设置 `WORKTRUNK_VERBOSE=0|1|2` 可把级别应用到*每一次*调用，包括补全——它相当于 `-v`/`-vv` 的环境变量形式，因此级别 2 会写入同样的 `trace.log`/`trace.jsonl`/`subprocess.log`/`diagnostic.md` 文件。命令中显式的 `-v`/`-vv` 可以进一步提高级别，但绝不会降低这一基准。要分析缓慢的 Tab 补全，请按 shell 的调用方式运行——例如 `WORKTRUNK_VERBOSE=2 COMPLETE=fish wt -- wt switch ''`——然后使用 `wt config state logs profile` 渲染结果。

## <a id="what-files-does-worktrunk-create"></a>Worktrunk 会创建哪些文件？

### 1. worktree 目录

当 `wt switch <branch>` 切换到尚无 worktree 的分支时创建。使用 `wt switch --create <branch>` 创建新分支。默认位置是 `../<repo>.<branch>`（与主仓库同级），可通过用户配置中的 `worktree-path` 配置。

**移除方式：** `wt remove <branch>` 会移除 worktree 目录并删除分支。

### 2. 配置文件

| 文件 | 创建方式 | 用途 |
|------|------------|---------|
| `~/.config/worktrunk/config.toml` | `wt config create` | 用户偏好 |
| `~/.config/worktrunk/approvals.toml` | 批准项目命令 | 已批准的 hook 和别名命令 |
| `.config/wt.toml` | `wt config create --project` | 项目 hook（提交到仓库中） |

用户配置位置：Linux/macOS 上为 `$XDG_CONFIG_HOME/worktrunk/`（或 `~/.config/worktrunk/`），Windows 上为 `%APPDATA%\worktrunk\`。

**移除方式：** 直接删除。用户配置：`rm ~/.config/worktrunk/config.toml`。项目配置：`rm .config/wt.toml`（并提交）。

### 3. Shell 集成

由 `wt config shell install` 创建：

- **Bash**：向 `~/.bashrc` 添加一行
- **Zsh**：向 `~/.zshrc`（或 `$ZDOTDIR/.zshrc`）添加一行
- **Fish**：创建 `~/.config/fish/functions/wt.fish` 和 `~/.config/fish/completions/wt.fish`
- **Nushell** [实验性]：在 Nushell 的用户 vendor-autoload 目录中创建 `wt.nu`——该目录是 `$nu.vendor-autoload-dirs` 的最后一项，位于 `$nu.data-dir` 下（Linux 上通常为 `~/.local/share/nushell/vendor/autoload`，macOS 上通常为 `~/Library/Application Support/nushell/vendor/autoload`）
- **PowerShell**（Windows）：如果以下两个 profile 文件不存在，则同时创建：
  - `Documents/PowerShell/Microsoft.PowerShell_profile.ps1`（PowerShell 7+）
  - `Documents/WindowsPowerShell/Microsoft.PowerShell_profile.ps1`（Windows PowerShell 5.1）

**Windows 上的 PowerShell 检测：** 从 cmd.exe 或 PowerShell 运行时，会自动创建两个 PowerShell profile 文件。从 Git Bash 或 MSYS2 运行时会跳过 PowerShell（使用 `wt config shell install powershell` 显式创建这些 profile）。

**移除方式：** `wt config shell uninstall`。

### 4. `.git/` 中的元数据（自动）

Worktrunk 会在仓库的 `.git/` 目录中存储少量缓存和日志数据：

| 位置 | 用途 | 创建方式 |
|----------|---------|------------|
| `git config worktrunk.*` | 缓存的默认分支、切换历史、分支标记、自定义变量 | 多种命令 |
| `.git/wt/cache/{kind}/*.json` | 缓存的 CI 状态、见过的最大 PR/MR 编号（用于确定 `wt list` CI 列的宽度），以及 git 命令结果（merge-tree、集成探测、diff 统计、祖先检查、领先/落后计数、merge base） | `wt list`、`wt merge`、`wt remove` |
| `.git/wt/cache/summary/{branch}/{hash}.json` | 按 diff hash 进行内容寻址的 LLM 分支摘要缓存 | `wt list --full`、`wt switch`（当 `[list] summary = true` 时） |
| `.git/wt/logs/{branch}/**/*.log` | 后台 hook 输出（按分支嵌套） | Hook、后台 `wt remove` |
| `.git/wt/logs/commands.jsonl` | 命令审计日志（最大约 2MB） | Hook、LLM 命令 |
| `.git/wt/logs/trace.log` | 用于报告 issue、供人阅读的调试跟踪记录 | 使用 `-vv` 运行 |
| `.git/wt/logs/trace.jsonl` | 机器跟踪记录（每条记录一个 JSON 对象） | 使用 `-vv` 运行 |
| `.git/wt/logs/subprocess.log` | 不设上限的原始子进程 stdout/stderr（可能有数 MB） | 使用 `-vv` 运行 |
| `.git/wt/logs/diagnostic.md` | 用于报告 issue 的诊断报告（以性能剖析开头） | 使用 `-vv` 运行 |
| `.git/wt/trash/<name>-<timestamp>` | 等待后台删除的已暂存 worktree 内容 | `wt remove` |

这些内容都不会被 git 追踪，也不会 push 到 remote。

**移除方式：** `wt config state clear` 会移除所有 Worktrunk 数据——配置 key、缓存、标记、提示、变量、日志和过期 trash。

### Worktrunk 不会创建什么

- 不会在 `.git/`、配置目录或 worktree 目录之外创建文件
- 不会创建全局 git hook
- 不会修改 `~/.gitconfig`
- 不会创建长期运行的后台进程或守护进程

## Worktrunk 可以删除什么？

Worktrunk 可以删除 **worktree** 和**分支**。两者都有安全防护。

### 移除 worktree

`wt remove` 与 `git worktree remove` 的行为一致：它拒绝移除含有未提交更改（已暂存、已修改或未跟踪文件）的 worktree。`--force` flag 会无视这一点移除 worktree，并丢弃所有这些更改。

要彻底防止某个 worktree 被移除（例如其中存放本地数据库），请将其锁定：

```bash
git worktree lock ../myproject.feature --reason "Contains local database"
```

锁定的 worktree 会显示 `⊞`，见 `wt list`。无论是 `git worktree remove` 还是 `wt remove`（即使带 `--force`）都不会删除它们。使用 `git worktree unlock` 解锁。

### 删除分支

默认情况下，`wt remove` 只删除其内容已经存在于默认分支中的分支。显示 `_`（相同提交）或 `⊂`（已集成）的分支可以安全删除，见 `wt list`。

完整算法参见[分支清理](https://worktrunk.dev/remove/#branch-cleanup)——它会处理提交历史不同但文件更改相同的 squash 合并和 rebase 工作流。

使用 `-D` 强制删除含有未合并更改的分支。使用 `--no-delete-branch` 可无论状态如何都保留分支。

在第二个 worktree 中检出的分支无论如何都会保留，包括使用 `-D` 时。删除它会使该 worktree 无法解析 `HEAD`；只有 `git worktree add --force` 会产生这种状态。

### 其他清理

- `wt remove`——除目标 worktree 外，还会运行两种清理机制。被移除 worktree 自己的 `git fsmonitor--daemon`（git 在 `core.fsmonitor=true` 下为每个 worktree 运行的文件系统监视器；其 worktree 消失后该进程会泄漏）会收到 `git fsmonitor--daemon stop`；如果未退出，还会通过从其 IPC 套接字解析出的 PID 强制终止（先 `SIGTERM`，再 `SIGKILL`）。随后，后台清扫会删除 `.git/wt/trash/` 中超过 24 小时的条目（先前后台移除中断时遗留的孤儿目录），并终止其 worktree 已不存在的 fsmonitor 守护进程（因 `git worktree remove`、`rm -rf` 或崩溃的 `wt` 而成为孤儿）
- `wt config state clear`——从 `.git/` 中移除所有 Worktrunk 数据（配置 key、缓存、标记、提示、变量、日志、过期 trash）
- `wt config shell install`——把集成迁移到新位置时，会移除旧位置留下的文件：fish `conf.d/wt.fish`（现为 `functions/wt.fish`），以及滞留在 `<config-dir>/vendor/autoload` 下的 nushell 包装器（现为 `<data-dir>/vendor/autoload`）。旧路径曾存放 Worktrunk 自己的包装器，而且文件以正在安装的命令命名，因此无需读取便会完整收回——如果 `conf.d/wt.fish` 留在原处，它仍会在启动时被加载，并遮蔽新包装器。只会触及这个确切文件名，每次移除都会输出
- `wt config shell uninstall`——从 bash/zsh/PowerShell rc 文件中移除集成行，并删除 Worktrunk 的包装器和补全文件（fish 的 `functions/`、`conf.d/` 和 `completions/`；nushell 的 `vendor/autoload`）。卸载命令不接受命令名，因此它会列出这些目录，并通过 Worktrunk 自身的内容标记识别文件，无论文件安装时使用了什么二进制名称；没有这些标记的文件会保留。rc 文件属于用户，因此只有实际运行 init 命令的行才符合条件：仅在注释、`echo` 或别名主体中提到它的行都会保留。卸载命令取走的每一行，都会在移除前输出一次，并在移除后再次输出

详情参见 [Worktrunk 会创建哪些文件？](#what-files-does-worktrunk-create)。

## Worktrunk 会执行哪些命令？

Worktrunk 会在内部运行 `git` 命令，并可选择运行 `gh`（GitHub）或 `glab`（GitLab）以获取 CI 状态。除此之外，用户定义的命令会在四种上下文中执行：

1. **用户 hook**（`~/.config/worktrunk/config.toml`）——适用于所有仓库的个人自动化
2. **项目 hook**（`.config/wt.toml`）——仓库专属自动化
3. **LLM 命令**（`~/.config/worktrunk/config.toml`）——生成提交消息和[分支摘要](https://worktrunk.dev/llm-commits/#branch-summaries)
4. **--execute flag**——显式提供的命令

用户 hook 和用户别名不需要批准（因为由你定义）。项目 hook 和项目别名中的命令首次运行时需要批准。已批准的命令会保存到审批文件（`approvals.toml`）。如果命令发生变化，Worktrunk 会要求重新批准。

### 批准提示示例

▲ repo needs approval to execute 3 commands:

○ pre-start install:
  npm ci
○ pre-start build:
  cargo build --release
○ pre-start env:
  echo 'PORT={{ branch | hash_port }}' > .env.local

❯ Allow and remember? [y/N]

使用 `--yes` 可绕过提示（适合 CI/自动化）。

### 命令日志

所有 hook 执行和 LLM 命令都会记录在 `.git/wt/logs/commands.jsonl` 中——每行一个 JSON 对象。字段：`ts`（时间戳）、`wt`（触发执行的 wt 命令）、`label`（运行内容，例如 `pre-merge user:lint`）、`cmd`（shell 命令）、`exit`（退出码，后台任务为 `null`）、`dur_ms`（时长，后台任务为 `null`）。文件达到 1MB 时会轮转为 `commands.jsonl.old`，因此存储上限约为 2MB。

使用 `wt config state logs get` 查看日志，或直接查询：

```bash
# Recent commands
$ tail -5 .git/wt/logs/commands.jsonl | jq .

# Failed commands
$ jq 'select(.exit != 0 and .exit != null)' .git/wt/logs/commands.jsonl
```

使用 `wt config state logs clear` 清除。

## Worktrunk 能在 Windows 上运行吗？

能。核心命令、shell 集成和 Tab 补全在 Git Bash 与 PowerShell 中都能工作。设置详情参见[安装](https://worktrunk.dev/worktrunk/#install)，其中包括如何避免与 Windows Terminal 的 `wt` 冲突。

**需要 Git for Windows**——Hook 使用 bash 语法并通过 Git Bash 执行，因此即使交互式 shell 是 PowerShell，也必须安装 [Git for Windows](https://gitforwindows.org/)。

`wt switch` 交互式选择器也能在 Windows 上运行，使用 [skim](https://github.com/skim-rs/skim) 的 crossterm 后端。

## Worktrunk 如何确定默认分支？

Worktrunk 会先检查本地 git 缓存，需要时查询远端；没有远端时，兜底使用本地推断。

如果远端的默认分支已更改（例如从 master 重命名为 main），请使用 `wt config state default-branch clear` 清除缓存。

检测机制的完整详情参见 `wt config state default-branch --help`。

## 我的 `for-each` 或 `--execute` 别名在每个 worktree 中输出相同的值

别名主体会在分派时、调用命令的 worktree 上下文中渲染一次，因此 `{{ branch }}` 这类每个 worktree 各异的变量，会在嵌套 `wt` 命令迭代之前就固化为该 worktree 的值。之后每个 worktree 看到的都是同一个值。

使用 `wt config alias dry-run <name>` 确认：如果值已经被代入（例如 `… echo branch=main`），说明它在分派时就已固化。

要把变量推迟到嵌套命令再展开，请将其包装为 `{% raw %}{{ branch }}{% endraw %}`；对于 `wt step for-each`，还要把它放在带引号的 `sh -c '…'` 中，以免别名的 shell 按单词拆分它。参见[在别名中推迟展开](https://worktrunk.dev/extending/#deferring-expansion-to-a-nested-wt-command)。`{{ default_branch }}` 这类仓库级变量不受影响——它在每个 worktree 中都相同。

## 安装因 C 编译错误而失败

与 tree-sitter 或 C 编译有关的错误（C99 模式、未定义 `le16toh`）可以通过安装时不启用语法高亮来避免：

```bash
cargo install worktrunk --no-default-features --features cli
```

这会禁用命令输出中的 bash 语法高亮，但保留所有核心功能。语法高亮功能需要 C99 编译器支持，在较旧的系统或精简 Docker 镜像上可能失败。

## 运行测试（贡献者）

### 快速测试

```bash
cargo test
```

### 完整集成测试

Shell 集成测试需要 bash、zsh、fish 和 nushell：

```bash
cargo test --test integration --features shell-integration-tests
```

## 如何贡献？

- 为仓库加 Star
- 试用并[提交 issue](https://github.com/max-sixty/worktrunk/issues) 反馈——哪怕只是小麻烦
- Worktrunk 还有哪些 worktree 摩擦尚未解决？[告诉我们](https://github.com/max-sixty/worktrunk/issues)
- 分享给朋友
- 在 [X](https://twitter.com/intent/tweet?text=Worktrunk%20%E2%80%94%20CLI%20for%20git%20worktree%20management&url=https%3A%2F%2Fworktrunk.dev)、[Reddit](https://www.reddit.com/submit?url=https%3A%2F%2Fworktrunk.dev&title=Worktrunk%20%E2%80%94%20CLI%20for%20git%20worktree%20management) 或 [LinkedIn](https://www.linkedin.com/sharing/share-offsite/?url=https%3A%2F%2Fworktrunk.dev) 上发布
