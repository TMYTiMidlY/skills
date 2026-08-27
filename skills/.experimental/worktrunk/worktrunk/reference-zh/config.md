> 本文是 `reference/config.md` 的中文翻译副本，随上游同步需重译；行为以英文原文为准。

# wt config

管理用户配置和项目配置，包括 shell 集成、hook 和已保存状态。

## 示例

安装 shell 集成（切换目录所必需）：

```bash
$ wt config shell install
```

创建包含文档示例的用户配置文件：

```bash
$ wt config create
```

创建用于 hook 的项目配置文件（`.config/wt.toml`）：

```bash
$ wt config create --project
```

显示当前配置及文件位置：

```bash
$ wt config show
```

## 配置文件

| 文件 | 位置 | 内容 | 提交并共享 |
|------|----------|----------|--------------------|
| **用户配置** | `~/.config/worktrunk/config.toml` | worktree 路径模板、LLM 提交配置等 | ✗ |
| **项目配置** | `.config/wt.toml` | 项目 hook、开发服务器 URL | ✓ |

组织可以部署系统级配置文件来共享默认值——运行 `wt config show` 可查看对应平台上的具体位置。

**用户配置**——个人偏好：

```toml
# ~/.config/worktrunk/config.toml
worktree-path = ".worktrees/{{ branch | sanitize }}"

[commit.generation]
command = "MAX_THINKING_TOKENS=0 claude -p --no-session-persistence --model=haiku --tools='' --safe-mode --setting-sources='user' --system-prompt=''"
```

**项目配置**——团队共享设置：

```toml
# .config/wt.toml
[pre-start]
deps = "npm ci"

[pre-merge]
test = "npm test"
```

<!-- USER_CONFIG_START -->
# 用户配置

使用 `wt config create` 创建。除非另有说明，所示值均为默认值。

位置：

- macOS/Linux：`~/.config/worktrunk/config.toml`（若设置了 `$XDG_CONFIG_HOME`，则使用它）
- Windows：`%APPDATA%\worktrunk\config.toml`

## worktree 路径模板

控制新 worktree 的创建位置。

**可用的模板变量：**

- `{{ repo_path }}`——仓库根目录的绝对路径（例如 `/Users/me/code/myproject`；对于裸仓库，则是裸目录本身）
- `{{ repo }}`——仓库目录名（例如 `myproject`）
- `{{ owner }}`——主远端的所有者路径（可能包含 `group/subgroup` 这样的子组）
- `{{ branch }}`——原始分支名（例如 `feature/auth`）
- `{{ branch | sanitize }}`——文件系统安全形式：将 `/` 和 `\` 替换为 `-`（例如 `feature-auth`）
- `{{ branch | sanitize_db }}`——数据库安全形式：小写、下划线、哈希后缀（例如 `feature_auth_x7k`）
- `{{ branch | codename(2) }}`——从约 126 万种组合池中确定性生成的易读名称（例如 `malleable-opah`）

这比 [hook 和别名可用的变量](https://worktrunk.dev/hook/#template-variables)集合更小。

对于位于 `~/code/myproject` 的仓库、分支 `feature/auth`，**示例**如下：

默认——同级目录（`~/code/myproject.feature-auth`）：

```toml
worktree-path = "{{ repo_path }}/../{{ repo }}.{{ branch | sanitize }}"
```

仓库内部（`~/code/myproject/.worktrees/feature-auth`）：

```toml
worktree-path = "{{ repo_path }}/.worktrees/{{ branch | sanitize }}"
```

由分支派生的易读名称（`~/code/myproject.malleable-opah`）：

```toml
worktree-path = "{{ repo_path }}/../{{ repo }}.{{ branch | codename(2) }}"
```

父目录中同时包含分支标识的易读名称（`~/code/worktrees/feature-auth/malleable-opah`）：

```toml
worktree-path = "{{ repo_path }}/../worktrees/{{ branch | sanitize }}/{{ branch | codename(2) }}"
```

集中式 worktree 目录（`~/worktrees/myproject/feature-auth`）：

```toml
worktree-path = "~/worktrees/{{ repo }}/{{ branch | sanitize }}"
```

按远端所有者路径组织（`~/development/max-sixty/myproject/feature/auth`）：

```toml
worktree-path = "~/development/{{ owner }}/{{ repo }}/{{ branch }}"
```

裸仓库（`~/code/myproject/feature-auth`）：

```toml
worktree-path = "{{ repo_path }}/../{{ branch | sanitize }}"
```

`~` 会展开为主目录。相对路径从 `repo_path` 解析。

## LLM 提交消息

在合并期间自动生成提交消息。需要外部 CLI 工具。

### Claude Code

```toml
[commit.generation]
command = "MAX_THINKING_TOKENS=0 claude -p --no-session-persistence --model=haiku --tools='' --safe-mode --setting-sources='user' --system-prompt=''"
```

### Codex

```toml
[commit.generation]
command = "codex exec -m gpt-5.6-luna -c model_reasoning_effort='low' -c system_prompt='' --sandbox=read-only --json - | jq -sr '[.[] | select(.item.type? == \"agent_message\")] | last.item.text'"
```

### OpenCode

```toml
[commit.generation]
command = "opencode run -m anthropic/claude-haiku-4.5 --variant fast"
```

### llm

```toml
[commit.generation]
command = "llm -m claude-haiku-4.5"
```

### aichat

```toml
[commit.generation]
command = "aichat -m claude:claude-haiku-4.5"
```

设置方式参见 [LLM 提交文档](https://worktrunk.dev/llm-commits/)，模板自定义参见[自定义提示词模板](#custom-prompt-templates)。

## 命令配置

### 列表

`wt list` 的持久化 flag 值。可根据需要在命令行中覆盖。

```toml
[list]
summary = false    # Enable LLM branch summaries (requires [commit.generation])

full = false       # Show CI status and LLM summaries (--full)
branches = false   # Include branches without worktrees (--branches)
remotes = false    # Include remote-only branches (--remotes)

json-schema = 2    # JSON output schema: 2 (envelope) or 1 (bare array, the current default); unset emits 1 with a warning

columns = ["branch", "status", "ci", "path"]   # Columns to show, in order — built-ins or custom headers (omit for the default set)

timeout-ms = 0     # Wall-clock budget for the entire collect phase; 0 disables
```

`columns` 选择要呈现的列并确定其顺序；省略它则使用默认列集。
它旨在驱动每次调用的[别名](https://worktrunk.dev/extending/#aliases)
（`wt --config-set 'list.columns=[…]' list`），从而提供命名视图，又不
扰乱默认的 `wt list`。静态设置也能使用，但会把布局固定下来，
而这张表原本会随 `--full` 和终端宽度调整。

有效的内置名称：

- `branch`——分支名
- `status`——Git 状态符号以及任何用户定义的状态
- `working-diff`——相对于 `HEAD` 的未提交行改动（表头 `HEAD±`）
- `ahead-behind`——相对默认分支领先和落后的提交数（表头 `main↕`）
- `branch-diff`——相对于默认分支的行改动（表头 `main…±`）
- `summary`——LLM 生成的分支摘要
- `upstream`——相对上游跟踪分支领先和落后的提交数（表头 `Remote⇅`）
- `ci`——头部提交的 CI 状态
- `path`——worktree 路径
- `url`——来自 `[list] url` 模板的开发服务器 URL
- `commit`——头部提交的短哈希
- `age`——距上次提交经过的时间
- `message`——头部提交的主题

所选列可混合内置列与[自定义列](#custom-columns)；每个自定义列按
其 `[list.custom-columns]` 表头命名（`columns = ["branch", "Ticket", "ci"]`），
并且该选择是穷尽式的：只呈现列出的列。省略 `columns` 可保留
默认列集，此时会自动追加自定义列。若表头冲突，内置名称优先；
边栏类型指示符始终显示。

只要空间允许，列出某列就会强制启用它：`ci` 无需 `--full` 即可显示，
因为 `--full` 只是把各列组合进默认表，而不是限制一个
具名列。数据源缺失的列仍会隐藏——`summary`
需要 LLM 命令（`[commit.generation]`），`url` 需要 `[list] url`
模板——因为列出它无法提供数据。

该选择会驱动表格和 `wt switch` 选择器。`wt list --format
json` 始终发出所有字段，但列出的受限列（`ci`、`summary`）
仍会强制收集其数据，因此 JSON 携带的数据与
表格显示的数据相同。

#### <a id="custom-columns"></a>自定义列 [experimental]

自定义列可向 `wt list` 表格添加每个分支的上下文。每个
`[list.custom-columns]` 条目都是一列：键为表头，模板
呈现每一行的单元格。

```toml
[list.custom-columns.Ticket]
template = "{{ vars.ticket }}"   # Required; the result is the cell text
width = 20                       # Optional max display width (default: 40)
priority = 9                     # Optional drop order when the terminal narrows;
                                 # lower = kept longer (default: 9, the URL band)
```

模板可以引用 `{{ branch }}`、`{{ worktree_path }}`、
`{{ worktree_name }}`（仅分支行中为空），以及两个按分支划分的
命名空间：

- `{{ vars.* }}`——通过
  [`wt config state vars set`](https://worktrunk.dev/config/#wt-config-state-vars) 存储的值。
- `{{ git.branch.* }}`——该分支自身在 `branch.<name>.*` 下的 git config，
  直接从 `git config` 读取（例如，你自行设置的键可用 `{{ git.branch.jira }}`，
  或使用 git 原生的 `description`）。Git 会把配置变量
  名称转为小写，因此 `branch.<name>.nvciShelf` 应读取为 `{{ git.branch.nvcishelf }}`。

所有标准过滤器都可用（`sanitize`、`hash_port`、`codename` 等）。模板
呈现为空的行（例如没有该键的分支）会显示
空单元格；如果某列的每一行都为空，则会从表格中移除该列。
`wt list --format json` 会在 `columns` 下包含呈现后的值。

下面的 `Jira` 列读取 git config 中保存的键，`Summary` 列
仅显示 git 原生分支描述的第一行：

```toml
[list.custom-columns.Jira]
template = "{{ git.branch.jira }}"

[list.custom-columns.Summary]
template = "{{ git.branch.description | lines | first }}"
```

### 提交

由 `wt step commit`、`wt step squash` 和 `wt merge` 共用。

```toml
[commit]
stage = "all"      # What to stage before commit: "all", "tracked", or "none"
```

### 合并

大多数 flag 默认启用。设为 false 可更改默认行为。

```toml
[merge]
squash = true      # Squash commits into one (--no-squash to preserve history)
commit = true      # Commit uncommitted changes first (--no-commit to skip)
rebase = true      # Rebase onto target before merge (--no-rebase to skip)
remove = true      # Remove worktree after merge (--no-remove to keep)
verify = true      # Run project hooks (--no-hooks to skip)
ff = true          # Fast-forward merge (--no-ff to create a merge commit instead)
```

### 移除

`wt remove` 的持久化 flag 值。可根据需要在命令行中覆盖。

```toml
[remove]
delete-branch = true   # Delete branch after removal (--no-delete-branch to keep)
```

### 切换

```toml
[switch]
cd = true          # Change directory after switching (--no-cd to skip)

[switch.picker]
pager = "delta --paging=never"   # Example: override git's core.pager for diff preview
```

### Step

```toml
[step.copy-ignored]
exclude = []   # Additional excludes (e.g., [".cache/", ".turbo/"])
```

内置排除项（VCS 元数据和工具状态目录）始终生效；[这份 `wt step copy-ignored` 文档](https://worktrunk.dev/step/#wt-step-copy-ignored)列出了它们。用户配置与项目配置中的排除项会合并。

### 别名

以 `wt <name>` 形式运行的命令模板。用法和 flag 参见[扩展 Worktrunk 指南](https://worktrunk.dev/extending/#aliases)。

```toml
[aliases]
greet = "echo Hello from {{ branch }}"
url = "echo http://localhost:{{ branch | hash_port }}"
```

此处定义的别名适用于所有项目。项目专用别名应改用[项目配置](https://worktrunk.dev/config/#project-configuration)的 `[aliases]` 部分。

### 用户的项目专用设置

用户配置可以包含 `[projects]` 表，用于项目专用设置——worktree 布局、设置覆盖以及其他任何内容——它独立于与团队成员共享的[项目配置](https://worktrunk.dev/config/#project-configuration)。

条目以项目标识符为键——从主远端 URL 派生的 `<host>/<owner>/<repo>`（不含 `.git` 后缀），或者在没有远端时使用仓库的规范路径。在仓库内运行 `wt config show` 可查看当前项目的标识符；它会在 `PROJECT CONFIG` 部分显示为 `Identifier: …`。

标量值（如 `worktree-path`）会替换全局值；其他所有内容（hook、别名等）都会追加，且全局内容在前。

```toml
[projects."github.com/user/repo"]
worktree-path = ".worktrees/{{ branch | sanitize }}"
list.full = true
merge.squash = false
remove.delete-branch = false
pre-start.env = "cp .env.example .env"
step.copy-ignored.exclude = [".repo-local-cache/"]
aliases.deploy = "make deploy BRANCH={{ branch }}"
```

hook 支持全部三种 [hook 形式](https://worktrunk.dev/hook/#hook-forms)。表会并发运行多条命令；表数组流水线会依次运行各步骤。下面的点号键示例与表形式等价——TOML 会以相同方式处理 `projects."github.com/user/repo".post-start.server = "..."` 和 `[projects."github.com/user/repo".post-start]` 表：

```toml
# Single command
[projects."github.com/user/repo"]
post-start = "mise trust"

# Multiple commands, running concurrently
[projects."github.com/user/repo".post-start]
mise = "mise trust"
server = "npm run dev"

# Pipeline: steps run in sequence
[[projects."github.com/user/repo".post-start]]
install = "npm ci"

[[projects."github.com/user/repo".post-start]]
build = "npm run build"
server = "npm run dev"
```

### <a id="custom-prompt-templates"></a>自定义提示词模板

模板使用 [minijinja](https://docs.rs/minijinja/) 语法。

#### 提交模板

可用变量：

- `{{ git_diff }}`、`{{ git_diff_stat }}`——diff 内容
- `{{ branch }}`、`{{ repo }}`——上下文
- `{{ recent_commits }}`——近期提交消息
- `{{ user_guidance }}`、`{{ project_guidance }}`——呈现后的追加片段（参见[追加到提示词](https://worktrunk.dev/config/#appending-to-the-prompt)）

默认模板：

<!-- DEFAULT_TEMPLATE_START -->
```toml
[commit.generation]
template = """
<task>Write a commit message for the staged changes below.</task>

<format>
- Subject line under 50 chars
- For material changes, add a blank line then a body paragraph explaining the change
- Output only the commit message, no quotes or code blocks
</format>

<style>
- Imperative mood: "Add feature" not "Added feature"
- Match recent commit style (conventional commits if used)
- Describe the change, not the intent or benefit
</style>
{% if user_guidance %}
<user-guidance>
{{ user_guidance }}
</user-guidance>
{% endif %}{% if project_guidance %}
<project-guidance>
{{ project_guidance }}
</project-guidance>
{% endif %}
<diffstat>
{{ git_diff_stat }}
</diffstat>

<diff>
{{ git_diff }}
</diff>

<context>
Branch: {{ branch }}
{% if recent_commits %}<recent_commits>
{% for commit in recent_commits %}- {{ commit }}
{% endfor %}</recent_commits>{% endif %}
</context>

"""
```
<!-- DEFAULT_TEMPLATE_END -->

#### Squash 模板

除提交模板变量外，还可使用：

- `{{ commit_details }}`——正在 squash 的提交列表；每项呈现为其主题，并公开 `.subject` / `.body`
- `{{ target_branch }}`——合并目标分支

默认模板：

<!-- DEFAULT_SQUASH_TEMPLATE_START -->
```toml
[commit.generation]
squash-template = """
<task>Write a commit message for the combined effect of these commits.</task>

<format>
- Subject line under 50 chars
- For material changes, add a blank line then a body paragraph explaining the change
- Output only the commit message, no quotes or code blocks
</format>

<style>
- Imperative mood: "Add feature" not "Added feature"
- Match the style of commits being squashed (conventional commits if used)
- Describe the change, not the intent or benefit
</style>
{% if user_guidance %}
<user-guidance>
{{ user_guidance }}
</user-guidance>
{% endif %}{% if project_guidance %}
<project-guidance>
{{ project_guidance }}
</project-guidance>
{% endif %}
<commits branch="{{ branch }}" target="{{ target_branch }}">
{% for detail in commit_details %}- {{ detail.subject }}
{% endfor %}</commits>

<diffstat>
{{ git_diff_stat }}
</diffstat>

<diff>
{{ git_diff }}
</diff>

"""
```
<!-- DEFAULT_SQUASH_TEMPLATE_END -->

#### 追加到提示词 [experimental]

`template-append` 可将个人约定添加到提交和 squash 提示词中，无需重述整个模板：

```toml
[commit.generation]
template-append = """
- Explain the rationale in the body, not just the change
"""
```

片段的呈现方式以及项目配置中的对应设置，参见 [LLM 提交指南](https://worktrunk.dev/llm-commits/#appending-to-the-prompt)。

## Hook

hook 类型、执行顺序、模板变量和示例参见 [`wt hook`](https://worktrunk.dev/hook/)。用户 hook 适用于所有项目；[项目 hook](https://worktrunk.dev/config/#project-configuration) 仅适用于对应仓库。
<!-- USER_CONFIG_END -->
<!-- PROJECT_CONFIG_START -->
# 项目配置

项目配置让团队能够共享仓库专用设置——hook、开发服务器 URL 及其他默认值。该文件位于 `.config/wt.toml`，通常会提交到版本控制。

要创建带有已注释示例的起始文件，请运行 `wt config create --project`。

## Hook

项目 hook 仅适用于此仓库。hook 类型、执行顺序和示例参见 [`wt hook`](https://worktrunk.dev/hook/)。

```toml
pre-start = "npm ci"
post-start = "npm run dev"
pre-merge = "npm test"
```

## 开发服务器 URL

`wt list` 中的 URL 列（端口未监听时会变暗）：

```toml
[list]
url = "http://localhost:{{ branch | hash_port }}"
```

## Forge 平台

forge 根据远端的主机名判定：主机名中任意位置含有 `github`、`gitlab` 或 `gitea` 的主机，以及 Azure DevOps 服务域名。对于名称中完全不含这些字样的主机，例如位于 `forge.example.com` 的 Forgejo 实例，请显式指定 forge：

```toml
[forge]
platform = "github"  # or "gitlab", "gitea" (experimental), "azure-devops" (experimental)
hostname = "github.example.com"  # Example: API host (GHE / self-hosted GitLab)
```

## 提交消息追加内容 [experimental]

`template-append` 可向 LLM 提交和 squash 提示词添加项目范围的约定；这些约定会共享，使每位团队成员的 LLM 都能看到同一份风格指南：

```toml
[commit.generation]
template-append = """
- Use conventional commits (feat:, fix:, docs:, …)
- Reference the relevant issue ID in the body
"""
```

片段首次使用时（以及每次发生变化时），`wt` 会提示用户批准它——这与项目定义 hook 使用相同的一次性批准关卡。项目文件中只有 `template-append` 会生效；LLM 命令和主提示词模板仍保留在[用户配置](https://worktrunk.dev/config/)中，因为它们描述每位开发者自己的环境（安装了哪个 CLI、开发者偏好哪个智能体）。片段的呈现方式参见 [LLM 提交指南](https://worktrunk.dev/llm-commits/#appending-to-the-prompt)。

## copy-ignored 排除项

`wt step copy-ignored` 的额外排除项：

```toml
[step.copy-ignored]
exclude = [".cache/", ".turbo/"]
```

内置排除项（VCS 元数据和工具状态目录）始终生效；[这份 `wt step copy-ignored` 文档](https://worktrunk.dev/step/#wt-step-copy-ignored)列出了它们。用户配置与项目配置中的排除项会合并。

## 别名

以 `wt <name>` 形式运行的命令模板。用法和 flag 参见[扩展 Worktrunk 指南](https://worktrunk.dev/extending/#aliases)。

```toml
[aliases]
deploy = "make deploy BRANCH={{ branch }}"
url = "echo http://localhost:{{ branch | hash_port }}"
```

此处定义的别名会与团队成员共享。个人别名应改用[用户配置](https://worktrunk.dev/config/#aliases)的 `[aliases]` 部分。
<!-- PROJECT_CONFIG_END -->

# Shell 集成

Worktrunk 需要 shell 集成，才能在切换 worktree 时更改目录。使用以下命令安装：

```bash
$ wt config shell install
```

手动设置方式参见 `wt config shell init --help`。

没有 shell 集成时，`wt switch` 会输出目标目录，但无法 `cd` 进入该目录。

### 首次运行提示

首次运行且没有 shell 集成时，Worktrunk 会提议安装它。首次提交且没有 LLM 配置时，它会提议配置检测到的工具（`claude`、`codex`）。拒绝后会自动设置 `skip-shell-integration-prompt` 或 `skip-commit-generation-prompt`。

# 其他

## 环境变量

所有用户配置选项均可使用带 `WORKTRUNK_` 前缀的环境变量覆盖。

### 命名约定

配置键使用 kebab-case（`worktree-path`），环境变量使用 SCREAMING_SNAKE_CASE（`WORKTRUNK_WORKTREE_PATH`）。转换会自动进行。

对于嵌套配置部分，使用双下划线分隔层级：

| 配置 | 环境变量 |
|--------|---------------------|
| `worktree-path` | `WORKTRUNK_WORKTREE_PATH` |
| `commit.generation.command` | `WORKTRUNK_COMMIT__GENERATION__COMMAND` |
| `commit.stage` | `WORKTRUNK_COMMIT__STAGE` |

### 示例：CI/测试覆盖

在 CI 中覆盖 LLM 命令以使用模拟命令：

```bash
$ WORKTRUNK_COMMIT__GENERATION__COMMAND="echo 'test: automated commit'" wt merge
```

### 其他环境变量

| 变量 | 用途 |
|----------|---------|
| `WORKTRUNK_BIN` | 覆盖 shell 包装器使用的二进制路径；适合测试开发构建 |
| `WORKTRUNK_CONFIG_PATH` | 覆盖用户配置文件位置 |
| `WORKTRUNK_SYSTEM_CONFIG_PATH` | 覆盖系统配置文件位置 |
| `WORKTRUNK_PROJECT_CONFIG_PATH` | 覆盖项目配置文件位置（默认为 `.config/wt.toml`）；相对路径从 worktree 根目录解析 |
| `XDG_CONFIG_DIRS` | 以冒号分隔的系统配置目录（默认：`/etc/xdg`） |
| `WORKTRUNK_DIRECTIVE_CD_FILE` | 内部使用：由 shell 包装器设置。wt 写入原始路径；包装器对其执行 `cd` |
| `WORKTRUNK_DIRECTIVE_EXEC_FILE` | 内部使用：由 shell 包装器设置。wt 写入 shell 命令；包装器加载该文件 |
| `WORKTRUNK_SHELL` | 内部使用：由 shell 包装器设置，以指示 shell 类型（例如 `powershell`） |
| `WORKTRUNK_MAX_CONCURRENT_COMMANDS` | 并行 git 命令的最大数量（默认：32）。遇到文件描述符限制时调低。 |
| `WORKTRUNK_VERBOSE` | 详细程度（`0`/`1`/`2`），类似 `-v`/`-vv`，但应用于所有位置——包括任何 flag 都无法触及的 shell 补全 |
| `RUST_LOG` | 日志指令（例如 `worktrunk=debug`）；会覆盖到达 stderr 的详细程度基线 |
| `NO_COLOR` | 禁用彩色输出（[标准](https://no-color.org/)） |
| `CLICOLOR_FORCE` | 即使不是 TTY 也强制彩色输出 |

## 行内配置覆盖（`--config-set`）

`--config-set <toml>` 为单次调用覆盖任意用户配置键，优先级高于两个配置文件和 `WORKTRUNK_` 环境变量。其值是 TOML 片段，因此可直接使用数组和表；该 flag 是全局 flag（可放在子命令之前或之后）、可重复使用，并且对同一个键，后出现的 `--config-set` 会替换先出现的值。

```bash
$ wt --config-set list.full=true list
$ wt step copy-ignored --config-set 'step.copy-ignored.exclude=["target", "dist"]'
```

它可以与别名组合使用——别名主体可调用 `wt --config-set … <command>`，在不更改已保存配置的情况下呈现命名视图。

## 命令参考

```
wt config - Manage user & project configs

Includes shell integration, hooks, and saved state.

Usage: wt config [OPTIONS] <COMMAND>

Commands:
  shell      Shell integration setup
  create     Create configuration file
  show       Show configuration files & locations
  update     Update deprecated config settings
  approvals  Manage command approvals
  alias      Inspect and preview aliases
  plugins    Plugin management
  state      Manage internal data and cache

Options:
  -h, --help
          Print help (see a summary with '-h')

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

# 子命令

## wt config show

显示配置文件及其位置。

显示用户配置（`~/.config/worktrunk/config.toml`）
和项目配置（`.config/wt.toml`）的位置与内容。如果存在系统配置，也会显示。

如果配置文件不存在，则显示将会使用的默认值。

### 完整诊断

使用 `--full` 运行诊断检查：

```bash
$ wt config show --full
```

这会测试：
- **CI 工具状态**——`gh`（GitHub）或 `glab`（GitLab）是否已安装并通过身份验证
- **提交生成**——LLM 命令能否生成提交消息
- **版本检查**——GitHub 上是否有更新版本

### 命令参考

```
wt config show - Show configuration files & locations

Usage: wt config show [OPTIONS]

Options:
      --full
          Run diagnostic checks (CI tools, commit generation, version)

  -h, --help
          Print help (see a summary with '-h')

Output:
      --format <FORMAT>
          Output format

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

## wt config approvals

管理命令审批。

项目 hook 和项目别名首次运行时会提示审批，以防止不受信任的项目运行任意命令。这两条流程产生的审批会存储在一起。

### 示例

列出当前项目的命令及其审批状态：
```bash
$ wt config approvals list
```

预先批准当前项目的所有 hook 和别名命令：
```bash
$ wt config approvals add
```

清除当前项目的审批：
```bash
$ wt config approvals clear
```

仅清除项目配置中已不存在命令的审批：
```bash
$ wt config approvals clear --stale
```

清除全局审批：
```bash
$ wt config approvals clear --global
```

### 审批工作方式

已批准的命令会保存到 `~/.config/worktrunk/approvals.toml`。命令模板发生变化或项目移动后，需要重新审批。在 CI 中可使用 `--yes` 跳过提示。

### 命令参考

```
wt config approvals - Manage command approvals

Usage: wt config approvals [OPTIONS] <COMMAND>

Commands:
  list   List project commands and their approval status
  add    Store approvals in approvals.toml
  clear  Clear approved commands from approvals.toml

Options:
  -h, --help
          Print help (see a summary with '-h')

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

## wt config alias

检查和预览别名。

别名是用户配置（`~/.config/worktrunk/config.toml`）或项目配置（`.config/wt.toml`）中配置的命令模板，以 `wt <name>` 形式运行。配置格式参见[扩展 Worktrunk 指南](https://worktrunk.dev/extending/#aliases)。

### 示例

显示每个已配置别名的模板：
```bash
$ wt config alias show
```

显示 `deploy` 的模板：
```bash
$ wt config alias show deploy
```

预览调用而不运行：
```bash
$ wt config alias dry-run deploy
$ wt config alias dry-run deploy -- --env=staging
```

### 命令参考

```
wt config alias - Inspect and preview aliases

Usage: wt config alias [OPTIONS] <COMMAND>

Commands:
  show     Show an alias's template, or all aliases' templates
  dry-run  Preview an alias invocation with template expansion

Options:
  -h, --help
          Print help (see a summary with '-h')

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

## wt config state

管理内部数据和缓存。

状态存储在 `.git/` 中（配置条目和日志文件），与配置文件分离。

### 键

- **cache**：[可重新生成的缓存——CI 状态、摘要、git 命令、提示以及 `wt switch -` 目标](https://worktrunk.dev/config/#wt-config-state-cache)
- **default-branch**：[仓库的默认分支（`main`、`master` 等）](https://worktrunk.dev/config/#wt-config-state-default-branch)
- **marker**：[分支的自定义状态标记（显示在 `wt list` 中）](https://worktrunk.dev/config/#wt-config-state-marker)
- **vars**：[experimental] [每个分支的自定义变量](https://worktrunk.dev/config/#wt-config-state-vars)
- **logs**：[操作日志和调试日志](https://worktrunk.dev/config/#wt-config-state-logs)

### 示例

获取默认分支：
```bash
$ wt config state default-branch
```

手动设置默认分支：
```bash
$ wt config state default-branch set main
```

为当前分支设置标记：
```bash
$ wt config state marker set 🚧
```

存储任意数据：
```bash
$ wt config state vars set env=staging
```

丢弃可重新生成的缓存：
```bash
$ wt config state cache clear
```

显示所有已存储状态：
```bash
$ wt config state get
```

清除所有已存储状态：
```bash
$ wt config state clear
```

### 命令参考

```
wt config state - Manage internal data and cache

Usage: wt config state [OPTIONS] <COMMAND>

Commands:
  get             Get all stored state
  clear           Clear all stored state
  cache           Regenerable caches
  default-branch  Default branch detection and override
  logs            Operation and debug logs
  marker          Branch markers
  vars            [experimental] Custom variables per branch

Options:
  -h, --help
          Print help (see a summary with '-h')

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

## wt config state cache

可重新生成的缓存。

集中查看或丢弃 Worktrunk 的可重新生成缓存。这里的所有内容都会按需重建——清除只会强制重新计算，绝不会导致数据丢失。

### 缓存内容

- **CI 状态**——每个分支的 GitHub/GitLab CI（TTL 为 30–60 秒），显示在 [`wt list`](https://worktrunk.dev/list/#ci-status) 中；还包括见过的最大 PR/MR 编号（用于确定 CI 列宽）
- **摘要**——LLM 生成的分支摘要（`wt list --full`、`wt switch` 预览）
- **Git 命令**——以 SHA 为键的磁盘缓存：merge-tree、祖先关系、diff 统计以及 `wt switch` 预览呈现结果
- **提示**——此仓库中已经显示过的一次性提示
- **上一分支**——`wt switch -` 的目标，会在下一次切换时重新记录

`cache clear` 会在不提示的情况下丢弃上述所有内容。它会重新显示一次性提示，并忘记 `wt switch -` 目标，直到下一次切换——两者都会自行重新填充。

不带子命令时，运行 `get`。

### 示例

显示缓存内容：
```bash
$ wt config state cache
```

丢弃所有缓存：
```bash
$ wt config state cache clear
```

### 命令参考

```
wt config state cache - Regenerable caches

Usage: wt config state cache [OPTIONS] [COMMAND]

Commands:
  get    Show cache contents
  clear  Drop all caches

Options:
  -h, --help
          Print help (see a summary with '-h')

Output:
      --format <FORMAT>
          Output format (text, json) [default: text]

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

## wt config state default-branch

默认分支检测与覆盖。

在脚本中很有用，可以避免硬编码 `main` 或 `master`：

```bash
$ git rebase $(wt config state default-branch)
```

在 hook 或别名模板中，优先使用 `{{ default_branch }}` [模板变量](https://worktrunk.dev/hook/#template-variables)；`$(wt config state default-branch)` 用于普通 shell 脚本。

不带子命令时，运行 `get`。使用 `set` 覆盖，或先 `clear` 再 `get` 以重新检测。

`default-branch get` 会解析该值，并在未命中缓存时将其缓存；聚合命令 `wt config state get` 只报告缓存（只读），因此在有命令填充它之前可能显示 `(none)`。

### 检测

Worktrunk 会自动检测默认分支：

1. **Worktrunk 缓存**——检查 `git config worktrunk.default-branch`
2. **Git 缓存**——检测主远端并检查其 HEAD（例如 `origin/HEAD`）
3. **远端查询**——如果未缓存，则查询 `git ls-remote`——通常耗时 100ms–2s，10 秒后放弃
4. **本地推断**——如果没有远端，或查询已被放弃，则根据本地分支推断

检测完成后，结果会缓存在 `worktrunk.default-branch` 中，以便快速访问。缓存不会在每条命令上重新验证，因此之后对 `origin/HEAD` 的更改——重命名默认分支后执行 `git remote set-head origin -a`——不会自动被采用。当缓存值与远端的本地 HEAD 不同时，`wt config state` 会标记这种偏移；`set` 会采用新分支，`clear` 会重新检测。

被放弃的远端查询是唯一不会缓存的情况：本地推断出的分支会用于响应当前命令，但如果把远端不可达时猜测的值永久保存，会造成问题，因此下一条命令会再次查询。

本地推断兜底会依次使用以下启发式规则：
- 如果只有一个本地分支，则使用它
- 对于裸仓库或空仓库，检查 `symbolic-ref HEAD`
- 检查 `git config init.defaultBranch`
- 查找常见名称：`main`、`master`、`develop`、`trunk`

如果均不匹配，检测失败；请使用 `wt config state default-branch set BRANCH` 显式设置。

### 命令参考

```
wt config state default-branch - Default branch detection and override

Usage: wt config state default-branch [OPTIONS] [COMMAND]

Commands:
  get    Get the default branch
  set    Set the default branch
  clear  Clear the default branch cache

Options:
  -h, --help
          Print help (see a summary with '-h')

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

## wt config state logs

操作日志和调试日志。

查看和管理日志文件——hook 输出、命令审计轨迹和调试诊断。

### 记录的内容

`.git/wt/logs/` 中有三类日志：

#### 命令日志（`commands.jsonl`）

所有 hook 执行和 LLM 命令都会自动记录——每行一个 JSON 对象。达到 1MB 时轮转为 `commands.jsonl.old`（总计约 2MB）。字段：

| 字段 | 说明 |
|-------|-------------|
| `ts` | ISO 8601 时间戳 |
| `wt` | 触发此次运行的 `wt` 命令（例如 `wt hook pre-merge --yes`） |
| `label` | 运行的内容（例如 `pre-merge user:lint`、`commit.generation`） |
| `cmd` | 执行的 shell 命令 |
| `exit` | 退出码（后台命令为 `null`） |
| `dur_ms` | 以毫秒为单位的持续时间（后台命令为 `null`） |

命令日志会追加条目，并且不针对特定分支——它记录所有 worktree 中的全部活动。

#### Hook 输出日志

hook 输出位于 `.git/wt/logs/{branch}/` 下按分支划分的子树中：

| 操作 | 日志路径 |
|-----------|----------|
| 后台 hook | `{branch}/{source}/{hook-type}/{name}.log` |
| 后台移除 | `{branch}/internal/remove.log` |

所有 `post-*` hook（post-start、post-switch、post-commit、post-merge）都在后台运行并生成日志文件。来源为 `user` 或 `project`。分支和 hook 名会经过处理以确保文件系统安全（无效字符 → `-`；追加短哈希以避免冲突）。同一分支上的同一操作会覆盖之前的日志。移除分支会清除其子树；已删除分支留下的孤立内容可使用 `wt config state logs clear` 清扫。

#### 诊断文件

| 文件 | 创建时机 |
|------|-------------|
| `trace.log` | 使用 `-vv` 运行时 |
| `trace.jsonl` | 使用 `-vv` 运行时 |
| `subprocess.log` | 使用 `-vv` 运行时 |
| `diagnostic.md` | 使用 `-vv` 运行时 |

`trace.log` 是 `-vv` 级别下供人阅读的跟踪记录——包括每条命令的开始（`$ …`）和完成（`✓`/`✗ … 12.3ms`）、进程内区段、里程碑以及有界的子进程预览。`trace.jsonl` 是同一事件流，每行一个 JSON 对象，供机器使用（`jq`、chrome://tracing）；`wt config state logs profile` 会读取它以汇总性能报告（时间花在哪里、并行度、冗余命令）。`subprocess.log` 保存未经截断的原始子进程 stdout/stderr 正文。`diagnostic.md` 是一个 Markdown 缺陷报告包，开头为同一份性能报告，并内嵌 `trace.log`；`wt` 会输出一条指向它的 `gh gist create` 命令。每次使用 `-vv` 运行时，四个文件都会被覆盖。

### 位置

所有日志都存储在 `.git/wt/logs/` 中（位于主 worktree 的 git 目录内）。所有 worktree 都写入同一目录。顶层文件是共享日志（命令审计 + 诊断）；顶层目录是每个分支的日志树。

### 结构化输出

`wt config state logs --format=json` 会发出三个数组——`command_log`、`hook_output`、`diagnostic`。每个条目都包含 `file`（相对路径）、`path`（绝对路径）、`size` 和 `modified_at`（Unix 秒数）。hook 输出条目还会公开 `branch`、`source`（`user` / `project` / `internal`）、`hook_type`（`post-*` 类型；内部操作为 `null`）和 `name`。可用 `jq` 筛选特定条目。

### 示例

列出所有日志文件：
```bash
$ wt config state logs
```

查询命令日志：
```bash
$ tail -5 .git/wt/logs/commands.jsonl | jq .
```

获取某个 hook 日志的路径（例如当前分支的 `post-start` `server` hook）：
```bash
$ wt config state logs --format=json | jq -r '.hook_output[] | select(.source == "user" and .hook_type == "post-start" and (.name | startswith("server"))) | .path'
```

特定分支的日志：
```bash
$ wt config state logs --format=json | jq '.hook_output[] | select(.branch | startswith("feature"))'
```

清除所有日志：
```bash
$ wt config state logs clear
```

### 命令参考

```
wt config state logs - Operation and debug logs

Usage: wt config state logs [OPTIONS] [COMMAND]

Commands:
  get      List all log file paths
  profile  Performance profile from a trace
  clear    Clear all log files

Options:
  -h, --help
          Print help (see a summary with '-h')

Output:
      --format <FORMAT>
          Output format (text, json) [default: text]

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

## wt config state ci-status

CI 状态缓存。

**已弃用**——CI 状态缓存现已成为 [`wt config state cache`](https://worktrunk.dev/config/#wt-config-state-cache) 的一部分。此子命令仍可工作，但会输出弃用通知。

状态值、显示符号和获取行为参见：[`wt list` CI 状态](https://worktrunk.dev/list/#ci-status)。

不带子命令时，对当前分支运行 `get`。使用 `clear` 重置某个分支的缓存，或使用 `clear --all` 重置全部缓存。

### 命令参考

```
wt config state ci-status - CI status cache

Usage: wt config state ci-status [OPTIONS] [COMMAND]

Commands:
  get    Get CI status for a branch
  clear  Clear CI status cache

Options:
  -h, --help
          Print help (see a summary with '-h')

Output:
      --format <FORMAT>
          Output format (text, json) [default: text]

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

## wt config state marker

分支标记。

显示在 `wt list` Status 列中的自定义状态文本或 emoji。

### 显示

标记出现在 Status 列末尾、git 符号之后：

```
$ wt list
  Branch       Status        HEAD±    main↕     main…±  Remote⇅  Commit   Age   Message
@ main             ^⇡                                    ⇡1      33323bc  1d    Initial commit
+ feature-api      ↑ 🤖              ↑1        +1                70343f0  1d    Add REST API endp…
+ review-ui      ? ↑ 💬              ↑1        +1                a585d6e  1d    Add dashboard com…
+ wip-docs       ? –                                             33323bc  1d    Initial commit

○ Showing 4 worktrees, 2 with changes, 2 ahead, 1 column hidden
```

### 使用场景

- **工作状态**——`🚧` WIP、`✅` 已准备好审阅、`🔥` 紧急
- **智能体跟踪**——[Claude Code](https://worktrunk.dev/claude-code/) 插件会自动设置标记
- **备注**——任意短文本：`"blocked"`、`"needs tests"`

### 存储

以 `worktrunk.state.<branch>.marker` 形式存储在 git config 中。可直接使用以下命令设置：

```bash
$ git config worktrunk.state.feature.marker '{"marker":"🚧","set_at":0}'
```

不带子命令时，对当前分支运行 `get`。与 `--branch` 一起使用时，执行 `get --branch=NAME`。

### 命令参考

```
wt config state marker - Branch markers

Usage: wt config state marker [OPTIONS] [COMMAND]

Commands:
  get    Get marker for a branch
  set    Set marker for a branch
  clear  Clear marker for a branch

Options:
  -h, --help
          Print help (see a summary with '-h')

Output:
      --format <FORMAT>
          Output format (text, json) [default: text]

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

## wt config state vars

[experimental]

每个分支的自定义变量。

为每个分支存储自定义变量。值会原样存储——可以是普通字符串或 JSON。

### 示例

设置和获取值：
```bash
$ wt config state vars set env=staging
$ wt config state vars get env
```

存储 JSON：
```bash
$ wt config state vars set config='{"port": 3000, "debug": true}'
```

列出所有键：
```bash
$ wt config state vars list
```

操作另一个分支：
```bash
$ wt config state vars set env=production --branch=main
```

### 模板访问

变量可在 [hook 模板](https://worktrunk.dev/hook/#template-variables)中以 `{{ vars.<key> }}` 访问。对于可能未设置的键，请使用 `default` 过滤器：

```toml
[post-start]
dev = "ENV={{ vars.env | default('development') }} npm start -- --port {{ vars.port | default('3000') }}"
```

JSON 对象和数组值支持点号访问：

```bash
$ wt config state vars set config='{"port": 3000, "debug": true}'
```
```toml
[post-start]
dev = "npm start -- --port {{ vars.config.port }}"
```

### 存储格式

以 `worktrunk.state.<branch>.vars.<key>` 形式存储在 git config 中。键只能包含字母、数字和连字符——点号会与 git config 的节分隔符冲突，下划线会与其变量名格式冲突。

### 命令参考

```
wt config state vars - [experimental] Custom variables per branch

Usage: wt config state vars [OPTIONS] <COMMAND>

Commands:
  get    Get a value
  list   List all keys
  set    Set a value
  clear  Clear a key or all keys

Options:
  -h, --help
          Print help (see a summary with '-h')

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
