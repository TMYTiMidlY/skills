> 本文是 `reference/llm-commits.md` 的中文翻译副本，随上游同步需重译；行为以英文原文为准。

# LLM 提交消息

Worktrunk 会构建模板化提示词，并通过管道把它传给外部命令，以此生成提交消息。此机制与 `wt merge`、`wt step commit` 和 `wt step squash` 集成。

## 设置

任何能从 stdin 读取提示词并输出提交消息的命令都可以使用。将以下内容添加到 `~/.config/worktrunk/config.toml`：

### Claude Code

```toml
[commit.generation]
command = "MAX_THINKING_TOKENS=0 claude -p --no-session-persistence --model=haiku --tools='' --safe-mode --setting-sources='user' --system-prompt=''"
```

`--no-session-persistence` 防止提交会话污染 `claude --continue`。`--safe-mode` 使这次运行保持封闭——不使用 hook、插件、MCP、skill 或 CLAUDE.md——同时让身份验证照常工作，因此通过 `apiKeyHelper`（而不只是 OAuth 或 `ANTHROPIC_API_KEY`）进行身份验证的设置仍能取得密钥。`--setting-sources='user'` 将设置范围限定为用户配置，使项目中的 `.claude/settings.json` 无法覆盖身份验证。其余 flag 会禁用工具、系统提示词和思考，以快速获得纯文本输出。`--safe-mode` 要求 Claude Code ≥ 2.1.169。安装方式参见 [Claude Code 文档](https://code.claude.com/docs/en/setup)。

### Codex

```toml
[commit.generation]
command = "codex exec -m gpt-5.6-luna -c model_reasoning_effort='low' -c system_prompt='' --sandbox=read-only --json - | jq -sr '[.[] | select(.item.type? == \"agent_message\")] | last.item.text'"
```

使用快速 mini 模型、较低的推理强度和空系统提示词，以更快得到输出。需要 `jq` 解析 JSON。参见 [Codex CLI 文档](https://developers.openai.com/codex/cli/)。

### 其他工具

```toml
# opencode — use a fast model variant
command = "opencode run -m anthropic/claude-haiku-4.5 --variant fast"

# llm
command = "llm -m claude-haiku-4.5"

# aichat
command = "aichat -m claude:claude-haiku-4.5"
```

## 用法

以下示例假定一个有更改待提交的功能 worktree。

### wt merge

把所有更改（未提交的更改 + 现有提交）squash 为一个由 LLM 生成消息的提交，然后合并到默认分支：

```bash
$ wt merge
<span class=c>◎</span> <span class=c>Squashing 3 commits into a single commit <span style='color:var(--bright-black,#555)'>(5 files, <span class=g>+16</span></span></span><span style='color:var(--bright-black,#555)'>)</span>...
<span class=c>◎</span> <span class=c>Generating squash commit message...</span>
<span style='background:var(--bright-white,#fff)'> </span> <b>feat(auth): Implement JWT authentication system</b>
<span style='background:var(--bright-white,#fff)'> </span>
<span style='background:var(--bright-white,#fff)'> </span> Add comprehensive JWT token handling including validation, refresh
<span style='background:var(--bright-white,#fff)'> </span> logic, and authentication tests.
<span class=g>✓</span> <span class=g>Squashed @ a1b2c3d</span>
<span class=c>◎</span> <span class=c>Merging 1 commit to <b>main</b> @ <span class=d>a1b2c3d</span> (no rebase needed)</span>
<span style='background:var(--bright-white,#fff)'> </span> * <span style='color:var(--yellow,#a60)'>a1b2c3d</span> feat(auth): Implement JWT authentication system
<span style='background:var(--bright-white,#fff)'> </span>  auth.rs             | 2 <span class=g>++</span>
<span style='background:var(--bright-white,#fff)'> </span>  auth_test.rs        | 2 <span class=g>++</span>
<span style='background:var(--bright-white,#fff)'> </span>  integration_test.rs | 6 <span class=g>++++++</span>
<span style='background:var(--bright-white,#fff)'> </span>  jwt.rs              | 3 <span class=g>+++</span>
<span style='background:var(--bright-white,#fff)'> </span>  jwt_test.rs         | 3 <span class=g>+++</span>
<span style='background:var(--bright-white,#fff)'> </span>  5 files changed, 16 insertions(+)
<span class=g>✓</span> <span class=g>Merged to <b>main</b> <span style='color:var(--bright-black,#555)'>(1 commit, 5 files, <span class=g>+16</span></span></span><span style='color:var(--bright-black,#555)'>)</span>
<span class=c>◎</span> <span class=c>Removing <b>feature</b> worktree &amp; branch in background (same commit as <b>main</b>,</span> <span class=d>_</span><span class=c>)</span>
<span class=d>○</span> Switched to worktree for <b>main</b> @ <b>~/repo</b>
```

### wt step commit

暂存并提交，提交消息由 LLM 生成：

```bash
$ wt step commit
<span class=c>◎</span> <span class=c>Generating commit message and committing changes... <span style='color:var(--bright-black,#555)'>(2 files, <span class=g>+26</span></span></span><span style='color:var(--bright-black,#555)'>)</span>
<span style='background:var(--bright-white,#fff)'> </span> <b>feat(validation): add input validation utilities</b>
<span class=g>✓</span> <span class=g>Committed changes @ <span class=d>a1b2c3d</span></span>
```

### wt step squash

把分支提交 squash 为一个由 LLM 生成消息的提交：

```bash
$ wt step squash
<span class=c>◎</span> <span class=c>Squashing 3 commits into a single commit <span style='color:var(--bright-black,#555)'>(5 files, <span class=g>+16</span></span></span><span style='color:var(--bright-black,#555)'>)</span>...
<span class=c>◎</span> <span class=c>Generating squash commit message...</span>
<span style='background:var(--bright-white,#fff)'> </span> <b>feat(auth): Implement JWT authentication system</b>
<span style='background:var(--bright-white,#fff)'> </span>
<span style='background:var(--bright-white,#fff)'> </span> Add comprehensive JWT token handling including validation, refresh
<span style='background:var(--bright-white,#fff)'> </span> logic, and authentication tests.
<span class=g>✓</span> <span class=g>Squashed @ a1b2c3d</span>
```

完整文档参见 [`wt merge`](https://worktrunk.dev/merge/) 和 [`wt step`](https://worktrunk.dev/step/)。

## 分支摘要

[实验性]

配置 `summary = true` 和 `[commit.generation] command` 后，Worktrunk 会生成 LLM 分支摘要——用一行描述每个分支相对默认分支的更改。

摘要会显示在：

- **`wt switch`** [交互式选择器](https://worktrunk.dev/switch/#interactive-picker)——预览标签页 5
- **`wt list --full`**——Summary 列（参见 [`wt list`](https://worktrunk.dev/list/#llm-summaries)）

在用户配置中启用：

```toml
[list]
summary = true
```

摘要会被缓存，且仅在 diff 发生变化时重新生成。

## 提示词模板

Worktrunk 使用 [minijinja](https://docs.rs/minijinja/) 模板（类似 Jinja2 的语法）构建提示词。

### 自定义模板

使用内联模板覆盖默认值：

```toml
[commit.generation]
command = "llm -m claude-haiku-4.5"

template = """
Write a commit message for this diff. One line, under 50 chars.

Branch: {{ branch }}
Diff:
{{ git_diff }}
"""

squash-template = """
Combine these {{ commit_details | length }} commits into one message:
{% for c in commit_details %}
- {{ c.subject }}
{% endfor %}

Diff:
{{ git_diff }}
"""
```

### 模板变量

| 变量 | 说明 |
|----------|-------------|
| `{{ git_diff }}` | diff（已暂存的更改，或 squash 时的组合 diff） |
| `{{ git_diff_stat }}` | diff 统计信息（更改的文件、插入、删除） |
| `{{ branch }}` | 当前分支名称 |
| `{{ repo }}` | 仓库名称 |
| `{{ recent_commits }}` | 最近的提交主题（用于参考风格） |
| `{{ commit_details }}` | 将被 squash 的提交（仅限 squash 模板）；每个对象会渲染为其主题，并公开 `.subject` / `.body` |
| `{{ target_branch }}` | 合并目标分支（仅限 squash 模板） |
| `{{ user_guidance }}` | 渲染后的用户 `template-append` 片段（见下文） |
| `{{ project_guidance }}` | 渲染后的项目 `template-append` 片段（见下文） |

### 模板语法

模板使用 [minijinja](https://docs.rs/minijinja/latest/minijinja/syntax/index.html)，支持：

- **变量**：`{{ branch }}`、`{{ repo | upper }}`
- **过滤器**：`{{ commit_details | length }}`、`{{ repo | upper }}`
- **条件语句**：`{% if recent_commits %}...{% endif %}`
- **循环**：`{% for c in commit_details %}{{ c.subject }}{% endfor %}`
- **循环变量**：`{{ loop.index }}`、`{{ loop.length }}`
- **空白控制**：`{%- ... -%}` 会去除周围的空白

完整的默认模板参见 `wt config create --help`。

## 追加到提示词

[实验性]

`template-append` 会向提交和 squash 提示词追加内容，而不是替换它们。它同时存在于用户配置（个人偏好）和项目配置（`.config/wt.toml`，共享后每位队友的 LLM 都能看到相同的风格指南）中。每个片段本身都是一个 [minijinja](https://docs.rs/minijinja/) 模板——Worktrunk 使用与主模板相同的变量（`{{ branch }}`、`{{ git_diff }}`、……）渲染它，然后把结果追加到 `<style>` 之后。用户片段会渲染到 `<user-guidance>` 块中，项目片段会渲染到 `<project-guidance>` 块中，因此 LLM 能区分个人偏好与共享约定：

```toml
# .config/wt.toml
[commit.generation]
template-append = """
- Use conventional commits (feat:, fix:, docs:, …)
- Reference the related issue ID in the body
"""
```

当用户和项目都设置了 `template-append` 时，`<user-guidance>` 块在前，随后是 `<project-guidance>`。

用户片段不需要批准——它是开发者自己的配置。对于项目片段，渲染后的文本第一次发送给 LLM 时，Worktrunk 会在批准提示中显示原始片段——这与项目定义 hook 使用的是同一种一次性关卡。后续提交不会再次提示，除非片段发生变化。拒绝不会导致失败：LLM 仍会运行，但只带用户片段（如果有）。

未引用 `{{ user_guidance }}` / `{{ project_guidance }}` 的自定义用户模板会选择不使用追加块——渲染后的值只会注入模板放置它们的位置。

## 兜底行为

未配置 LLM 时，Worktrunk 会根据已更改的文件名生成确定性的消息（例如 “Changes to auth.rs & config.rs”）。
