> 本文是 `reference/step.md` 的中文翻译副本，随上游同步需重译；行为以英文原文为准。

# wt step

运行单项操作。它们是 wt merge 的构建块——commit、squash、rebase、push——另加一些独立工具。

## 示例

使用 LLM 生成的消息提交：

```
$ wt step commit
◎ Generating commit message and committing changes... (2 files, +26)
  feat(validation): add input validation utilities
✓ Committed changes @ a1b2c3d
```

在各步骤之间进行审阅的手动合并工作流：

```bash
$ wt step commit
$ wt step squash
$ wt step rebase
$ wt step push
```

## 操作

- [`commit`](#wt-step-commit)——暂存并使用 [LLM 生成的消息](https://worktrunk.dev/llm-commits/)提交
- [`squash`](#wt-step-squash)——使用 [LLM 生成的消息](https://worktrunk.dev/llm-commits/)将分支的所有提交 squash 为一个
- [`rebase`](#wt-step-rebase)——rebase 到目标分支上
- [`push`](#wt-step-push)——将目标分支 fast-forward 到当前分支
- [`diff`](#wt-step-diff)——显示分支创建以来的所有改动（已提交、已暂存、未暂存、未跟踪）
- [`copy-ignored`](#wt-step-copy-ignored)——在 worktree 之间复制被 gitignore 的文件
- [`eval`](#wt-step-eval)——[experimental] 对模板表达式求值
- [`for-each`](#wt-step-for-each)——[experimental] 在每个 worktree 中运行命令
- [`promote`](#wt-step-promote)——[experimental] 将某个分支换入主 worktree
- [`prune`](#wt-step-prune)——移除已合并进默认分支的 worktree 和分支
- [`relocate`](#wt-step-relocate)——[experimental] 将 worktree 移到预期路径
- [`tether`](#wt-step-tether)——[experimental] 运行命令；当其 worktree 被移除时终止该命令的整个进程树
- [`<alias>`](https://worktrunk.dev/extending/#aliases)——运行已配置的命令别名

## 命令参考

```
wt step - Run individual operations

The building blocks of wt merge — commit, squash, rebase, push — plus standalone utilities.

Usage: wt step [OPTIONS] <COMMAND>

Commands:
  commit        Stage and commit with LLM-generated message
  squash        Squash commits since branching
  rebase        Rebase onto target
  push          Fast-forward target to current branch
  diff          Show all changes since branching
  copy-ignored  Copy gitignored files to another worktree
  eval          [experimental] Evaluate a template expression
  for-each      [experimental] Run command in each worktree
  promote       [experimental] Swap a branch into the main worktree
  prune         [experimental] Remove worktrees merged into the default branch
  relocate      [experimental] Move worktrees to expected paths
  tether        [experimental] Run a command; kill its whole process tree when its worktree is
                removed

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

## wt step commit

暂存并使用 LLM 生成的消息提交。

配置和提示词自定义参见 [LLM 生成的提交消息](https://worktrunk.dev/llm-commits/)。

### 选项

#### 暂存

控制提交前暂存哪些内容：

| 值 | 行为 |
|-------|----------|
| `all` | 暂存所有改动，包括未跟踪文件（默认） |
| `tracked` | 仅暂存已修改的跟踪文件 |
| `none` | 不暂存任何内容，只提交已经暂存的内容 |

```bash
$ wt step commit --stage=tracked
```

在用户配置中设置默认值：

```toml
[commit]
stage = "tracked"
```

#### 试运行

呈现提示词、输出 LLM 命令、生成消息，然后退出，不进行暂存、不运行 hook，也不提交：

```bash
$ wt step commit --dry-run
```

会输出三个部分：呈现后的提示词、原本会调用 LLM 的 shell 命令，以及返回的消息。LLM 调用仍会发生——跳过的只有提交。

### 命令参考

```
wt step commit - Stage and commit with LLM-generated message

Usage: wt step commit [OPTIONS]

Options:
  -b, --branch <BRANCH>
          Branch to operate on (defaults to current worktree)

      --stage <STAGE>
          What to stage before committing [default: all]

          Possible values:
          - all:     Stage everything: untracked files + unstaged tracked changes
          - tracked: Stage tracked changes only (like git add -u)
          - none:    Stage nothing, commit only what's already in the index

      --dry-run
          Preview prompt, command, and generated message without committing

  -h, --help
          Print help (see a summary with '-h')

Automation:
      --no-hooks
          Skip hooks

      --format <FORMAT>
          Output format

          JSON prints structured result to stdout after the commit completes.

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

## wt step squash

Squash 分支创建以来的提交。暂存改动，并使用 LLM 生成消息。

配置和提示词自定义参见 [LLM 生成的提交消息](https://worktrunk.dev/llm-commits/)。

### 选项

#### 暂存

控制 squash 前暂存哪些内容：

| 值 | 行为 |
|-------|----------|
| `all` | 暂存所有改动，包括未跟踪文件（默认） |
| `tracked` | 仅暂存已修改的跟踪文件 |
| `none` | 不暂存任何内容，只 squash 已提交的改动 |

```bash
$ wt step squash --stage=none
```

在用户配置中设置默认值：

```toml
[commit]
stage = "tracked"
```

#### 试运行

呈现提示词、输出 LLM 命令、生成 squash 消息，然后退出，不执行重置、不运行 hook，也不提交：

```bash
$ wt step squash --dry-run
```

会输出三个部分：呈现后的提示词、原本会调用 LLM 的 shell 命令，以及返回的消息。LLM 调用仍会发生——跳过的只有 squash 和提交。

### 命令参考

```
wt step squash - Squash commits since branching

Stages changes and generates message with LLM.

Usage: wt step squash [OPTIONS] [TARGET]

Arguments:
  [TARGET]
          Target branch

          Defaults to default branch.

Options:
      --stage <STAGE>
          What to stage before committing [default: all]

          Possible values:
          - all:     Stage everything: untracked files + unstaged tracked changes
          - tracked: Stage tracked changes only (like git add -u)
          - none:    Stage nothing, commit only what's already in the index

      --dry-run
          Preview prompt, command, and generated message without squashing

  -h, --help
          Print help (see a summary with '-h')

Automation:
      --no-hooks
          Skip hooks

      --format <FORMAT>
          Output format

          JSON prints structured result to stdout after the squash completes.

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

## wt step rebase

Rebase 到目标上。

rebase 会把分支提交放到目标之上，这正是 [`wt step push`](#wt-step-push) 所需要的——只有目标是该分支的祖先时，push 才能 fast-forward。`wt merge` 会把此步骤作为其流水线的一部分运行；单独运行时，它会让分支跟上已经移动的目标，但不会将分支合并进去。

目标可以是任意提交：分支、tag 或 SHA。

### 示例

```bash
$ wt step rebase            # Rebase onto default branch
$ wt step rebase develop    # Rebase onto develop
$ wt step rebase v1.2.0     # Rebase onto a tag
```

### 结果

采用第一个匹配的行：

| 分支和目标 | 结果 |
|-------------------|--------|
| 目标已经是该分支的祖先，且两者之间没有合并提交 | 不运行任何操作——`Already up to date` |
| 该分支是目标的祖先，因此没有自己的提交 | `Fast-forwarded to <target>` |
| 其他情况 | 将该分支的提交重放到目标顶端——如果两者没有共同历史，则直接拒绝 |

把目标合并进自身的分支仍会 rebase：目标是它的祖先，但两者之间的合并提交使第一行不适用。

当目标的本地引用落后于其上游时，上述各行会以上游为基准判断，结果中也会用该上游名称替代参数。[`wt merge`](https://worktrunk.dev/merge/) 解释了原因。

### 冲突

有冲突的提交会让 rebase 保持打开状态，而不是撤销它。worktree 会保留 git 的冲突标记；解决冲突后可执行 `git rebase --continue`，也可执行 `git rebase --skip` 或 `git rebase --abort`。在 rebase 结束之前，`wt step rebase`、`wt step squash`、`wt step push` 和 `wt merge` 都会拒绝运行——当任何其他 git 操作处于打开状态时也一样，包括发生冲突的 `git merge`。

### 命令参考

```
wt step rebase - Rebase onto target

Usage: wt step rebase [OPTIONS] [TARGET]

Arguments:
  [TARGET]
          Target branch, tag, or commit

          Defaults to default branch.

Options:
  -h, --help
          Print help (see a summary with '-h')

Automation:
      --format <FORMAT>
          Output format

          JSON prints structured result to stdout after the rebase completes.

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

## wt step push

将目标 fast-forward 到当前分支。

尽管名为 push，但不会有任何提交离开仓库。目标分支的引用会在本地向前移动，持有该分支的 worktree 也会随之更新。发布需要随后另行对远端执行 `git push`。

目标必须是分支，并且已经是当前分支的祖先。若目标已向前移动，则会拒绝操作，而且没有强制变体——请先用 [`wt step rebase`](#wt-step-rebase) 把当前分支重新放到目标之上。

### 示例

```bash
$ wt step push             # Fast-forward main to current branch
$ wt step push develop     # Fast-forward develop instead
$ wt step push --no-ff     # Merge commit instead of a fast-forward
```

### 目标 worktree

当目标分支有自己的 worktree 时，该 worktree 的文件也会移动到新提交。fast-forward 会通过使用 `receive.denyCurrentBranch=updateInstead` 向此仓库 push，同时完成这两项操作；`--no-ff` 会先移动引用，再同步 worktree，如果该同步无法应用，则发出警告而不是失败。该 worktree 中的未提交改动会在此期间 stash，并于之后恢复；如果某项未提交改动触及 push 也要更改的文件，则会拒绝操作并指出该文件。

如果某个 worktree 仍处于注册状态，但其目录已经消失，同样会拒绝操作，因为无法把任何内容同步进去——`git worktree prune` 可清除此注册项。

### 命令参考

```
wt step push - Fast-forward target to current branch

Usage: wt step push [OPTIONS] [TARGET]

Arguments:
  [TARGET]
          Target branch

          Defaults to default branch.

Options:
      --no-ff
          Create a merge commit (no fast-forward)

  -h, --help
          Print help (see a summary with '-h')

Automation:
      --format <FORMAT>
          Output format

          JSON prints structured result to stdout after the push completes.

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

## wt step diff

显示分支创建以来的所有改动，包括已提交、已暂存、未暂存和未跟踪文件。

这就是 `wt merge` 将包含的内容——一个相对于合并基点的单一 diff。

### 操作另一个 worktree

`--branch` 可在不离开当前 worktree 的情况下，对另一个 worktree 的分支执行 diff：

```bash
$ wt step diff --branch feature
```

该分支必须有已检出的 worktree。

### 额外的 git diff 参数

`--` 后的参数会转发给 `git diff`：

```bash
$ wt step diff -- --stat
$ wt step diff -- --name-only
$ wt step diff -- -- '*.rs'
```

diff 可以通过管道传给 `delta` 等工具：

```bash
$ wt step diff | delta
```

### 工作原理

等价于：

```bash
$ cp "$(git rev-parse --git-dir)/index" /tmp/idx
$ GIT_INDEX_FILE=/tmp/idx git add --intent-to-add .
$ GIT_INDEX_FILE=/tmp/idx git diff $(git merge-base HEAD $(wt config state default-branch))
```

`git diff` 会忽略未跟踪文件。`git add --intent-to-add .` 会在索引中登记这些文件，但不暂存其内容，从而让 `git diff` 可以看到它们。此操作针对真实索引的副本运行，因此原始索引绝不会被修改。

### 命令参考

```
wt step diff - Show all changes since branching

Includes committed, staged, unstaged, and untracked files.

Usage: wt step diff [OPTIONS] [TARGET] [-- <EXTRA_ARGS>...]

Arguments:
  [TARGET]
          Target branch

          Defaults to default branch.

  [EXTRA_ARGS]...
          Extra arguments forwarded to git diff

Options:
  -b, --branch <BRANCH>
          Branch to operate on (defaults to current worktree)

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

## wt step copy-ignored

将被 gitignore 的文件复制到另一个 worktree。通过复制构建缓存和依赖来消除冷启动。

### 设置

添加到项目配置：

```toml
# .config/wt.toml
[post-start]
copy = "wt step copy-ignored"
```

### 复制内容

默认复制所有被 gitignore 的文件，但以下内置目录除外：VCS 元数据（`.bzr/`、`.hg/`、`.jj/`、`.pijul/`、`.sl/`、`.svn/`）、工具状态目录（`.conductor/`、`.entire/`、`.worktrees/`），以及嵌套 worktree。绝不会触碰跟踪文件。发现过程会处理嵌套 `.gitignore` 文件、全局排除项和 `.git/info/exclude`。目标中已有的文件会被跳过，因此可安全地重复运行；`--force` 会覆盖它们。

要进一步限制复制内容，请创建包含 gitignore 风格模式的 `.worktreeinclude`。文件必须**同时**被 gitignore **并且**位于 `.worktreeinclude` 中：

```text
# .worktreeinclude
.env
node_modules/
target/
```

`.worktreeinclude` 选出条目后，还可以在用户配置、每个项目的用户覆盖或项目配置中添加更多 gitignore 风格排除项：

```toml
[step.copy-ignored]
exclude = [".cache/", ".turbo/"]
```

如果希望仅在 `.worktreeinclude` 存在时才复制任何内容——与要求该文件的 Claude Code desktop 一致——请传入 `--require-include`：

```bash
wt step copy-ignored --require-include
```

没有 `.worktreeinclude` 时，该命令不执行任何操作（它会报告未复制任何内容及原因）。存在该文件时，只复制上文所述的匹配文件。要将此行为应用于每个仓库，请把该 flag 放入用户配置 hook：`post-start = "wt step copy-ignored --require-include"`。

### 常见模式

| 类型 | 模式 |
|------|----------|
| 依赖 | `node_modules/`、`.venv/`、`target/`、`vendor/`、`Pods/` |
| 构建缓存 | `.cache/`、`.next/`、`.parcel-cache/`、`.turbo/` |
| 生成的资产 | 对 git 而言过大的图像、ML 模型、二进制文件 |
| 环境文件 | `.env`（如果不是按 worktree 生成） |

### 性能

Reflink 副本在修改前共享磁盘块——实际上不会复制数据。对于 14GB 的 `target/` 目录：

| 命令 | 时间 |
|---------|------|
| `cp -R`（完整复制） | 2m |
| `cp -Rc` / `wt step copy-ignored` | 20s |

使用逐文件 reflink（类似 `cp -Rc`）——复制时间随文件数量增长。

使用 `post-start` hook 可让复制在后台运行。如果后续 hook 或命令立即需要复制出的文件，则改用 `pre-start`；这也适用于 `--execute` 命令。

### 后台 hook 优先级（experimental）

从后台 hook 流水线（`post-*` hook）调用时，`wt step copy-ignored` 会自行降低 CPU 和 I/O 优先级——macOS 上使用 `taskpolicy -b`，Linux 上使用 `nice -n 19` 加 `ionice -c 3`——从而让位于交互式工作。前台调用方（`pre-*` hook、直接交互使用）按正常优先级运行，避免用户等待受限速的复制。

wt 会向每条分离式 hook 流水线导出 `WORKTRUNK_FOREGROUND=-1`，以标示后台 hook 上下文；`copy-ignored` 会在进入时检查该变量。该变量名是 experimental，可能会更改。

### 特定语言说明

#### Rust

`target/` 目录非常大（通常为 1–10GB）。使用 reflink 复制，可以复用已编译依赖，将首次构建从约 68 秒缩短到约 3 秒。

#### Node.js

`node_modules/` 很大，但大部分内容是静态的。如果项目没有原生依赖，symlink 甚至更快：

```toml
[pre-start]
deps = "ln -sf {{ primary_worktree_path }}/node_modules ."
```

#### Python

虚拟环境包含绝对路径，无法复制。请改用 `uv sync`——它足够快，不值得复制。

### 与 Claude Code desktop 的行为对比

`.worktreeinclude` 模式与 [Claude Code desktop](https://code.claude.com/docs/en/desktop) 共享；后者在创建 worktree 时复制匹配文件。差异：

- Worktrunk 默认复制所有被 gitignore 的文件；Claude Code 要求 `.worktreeinclude`。传入 `--require-include` 可匹配 Claude Code 的行为（没有 `.worktreeinclude` 时不复制任何内容）
- Worktrunk 对 `target/` 等大型目录使用 copy-on-write（参见上面的“性能”）
- Worktrunk 在 worktree 生命周期中以可配置 hook 的形式运行

### 命令参考

```
wt step copy-ignored - Copy gitignored files to another worktree

Eliminates cold starts by copying build caches and dependencies.

Usage: wt step copy-ignored [OPTIONS]

Options:
      --from <FROM>
          Source worktree branch

          Defaults to main worktree.

      --to <TO>
          Destination worktree branch

          Defaults to current worktree.

      --dry-run
          Show what would be copied

      --force
          Overwrite existing files in destination

      --require-include
          Require .worktreeinclude to copy anything

  -h, --help
          Print help (see a summary with '-h')

Automation:
      --format <FORMAT>
          Output format

          JSON prints structured result to stdout after the copy completes.

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

## wt step eval

[experimental]

对模板表达式求值。将结果输出到 stdout，供脚本和 shell 命令替换使用。

所有 [hook 模板变量和过滤器](https://worktrunk.dev/hook/#template-variables) 均可用。

### 示例

获取当前分支的端口：

```bash
$ wt step eval '{{ branch | hash_port }}'
16066
```

用于 shell 命令替换：

```bash
$ curl http://localhost:$(wt step eval '{{ branch | hash_port }}')/health
```

组合多个值：

```bash
$ wt step eval '{{ branch | hash_port }},{{ ("supabase-api-" ~ branch) | hash_port }}'
16066,16739
```

使用条件和过滤器：

```bash
$ wt step eval '{{ branch | sanitize_db }}'
feature_auth_oauth2_a1b
```

使用 `-v` 列出可用的模板变量（与展开结果一同输出到 stderr）：

```bash
$ wt step eval -v '{{ branch }}'
○ eval template variables:
  branch        = feature/auth-oauth2
  worktree_path = /home/user/projects/myapp-feature-auth-oauth2
○ eval source
  {{ branch }}
○ eval result
  feature/auth-oauth2

feature/auth-oauth2
```

### 命令参考

```
wt step eval - [experimental] Evaluate a template expression

Prints the result to stdout for use in scripts and shell substitutions.

Usage: wt step eval [OPTIONS] <TEMPLATE>

Arguments:
  <TEMPLATE>
          Template expression to evaluate

Options:
  -h, --help
          Print help (see a summary with '-h')

Automation:
      --format <FORMAT>
          Output format

          JSON prints {name, template, result} to stdout instead of the bare result.

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

## wt step for-each

[experimental]

在每个 worktree 中运行命令。依次执行并实时输出；命令失败后仍继续。

最后会显示成功和失败摘要。模板展开错误（格式错误的 `{{ … }}` 参数）会中止整次运行；只有命令失败会被容忍并报告。对于需要结构化数据的脚本，上下文 JSON——包含每个模板变量的扁平对象——会通过 stdin 传入。

### 参数

`--` 后面的参数是程序及其参数——直接运行，不经过 shell。

```bash
$ wt step for-each -- git status --short
$ wt step for-each -- npm install
```

对于管道、重定向、变量或通配模式，请封装在 `sh -c` 中：

```bash
$ wt step for-each -- sh -c 'git status | wc -l'
$ wt step for-each -- sh -c 'echo $HOME && git pull'
```

### 模板变量

变量会在执行前替换到每个 argv 元素中。完整列表和过滤器参见 [`wt hook` 模板变量](https://worktrunk.dev/hook/#template-variables)。

```bash
$ wt step for-each -- echo 'Branch: {{ branch }}'
```

每个 worktree 中的每个元素都会重新展开，因此 `{{ branch }}` 是该 worktree 的分支。封装 for-each 的别名会更早在调用方 worktree 中呈现模板；[在别名中延迟展开](https://worktrunk.dev/extending/#deferring-expansion-to-a-nested-wt-command)说明了如何让变量按 worktree 求值。

### 示例

在有上游的 worktree 中拉取更新（跳过其他 worktree）：

```bash
$ git fetch --prune && wt step for-each -- sh -c '[ "$(git rev-parse @{u} 2>/dev/null)" ] || exit 0; git pull --autostash'
```

### 命令参考

```
wt step for-each - [experimental] Run command in each worktree

Executes sequentially with real-time output; continues past command failures.

Usage: wt step for-each [OPTIONS] -- <ARGS>...

Arguments:
  <ARGS>...
          Command template (see --help for all variables)

Options:
      --format <FORMAT>
          Output format

          [default: text]
          [possible values: text, json]

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

## wt step promote

[experimental]

将某个分支换入主 worktree。在两个 worktree 之间交换分支和被 gitignore 的文件。

**实验性。** 当主 worktree 具有特殊意义（Docker Compose、IDE 配置、锚定到项目根目录的大型构建产物），并且 hook 和工具尚未设置为可在任意 worktree 上运行时，可使用 promote 进行临时测试。符合 Worktrunk 惯用方式的工作流不使用 `promote`；而是让每个 worktree 都有完整环境。`promote` 是唯一会更改现有 worktree 中分支的 Worktrunk 命令。

### 示例

```bash
# from ~/project (main worktree)
$ wt step promote feature
```

之前：

```
  Branch   Path
@ main     ~/project
+ feature  ~/project.feature
```

之后：

```
  Branch   Path
@ feature  ~/project
+ main     ~/project.feature
```

要恢复：可从任意位置运行 `wt step promote main`，也可直接从主 worktree 运行 `wt step promote`。

不带参数时，promote 当前分支；如果从主 worktree 运行，则恢复默认分支。

### 要求

- 两个 worktree 都必须干净
- 该分支必须已有 worktree

### 被 gitignore 的文件

被 gitignore 的文件（构建产物、`node_modules/`、`.env`）会与分支一同交换，使每个 worktree 保留属于其分支的产物。文件发现使用与 [`copy-ignored`](#wt-step-copy-ignored) 相同的机制，并可通过 `.worktreeinclude` 过滤。

交换会对每个条目使用 `rename()`——无论条目多大都很快，因为只会更改文件系统元数据。如果 worktree 与 `.git/` 位于不同的文件系统，则兜底使用 reflink 复制。

### 命令参考

```
wt step promote - [experimental] Swap a branch into the main worktree

Exchanges branches and gitignored files between two worktrees.

Usage: wt step promote [OPTIONS] [BRANCH]

Arguments:
  [BRANCH]
          Branch to promote to main worktree

          Defaults to current branch, or default branch from main worktree.

Options:
  -h, --help
          Print help (see a summary with '-h')

Automation:
      --format <FORMAT>
          Output format

          JSON prints structured result to stdout after the promote completes. The mismatch warning
          still appears on stderr in JSON mode (safety signal).

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

## wt step prune

[experimental]

移除已合并进默认分支的 worktree。

使用与 `wt remove` 分支清理相同的判定标准，批量移除已经集成进默认分支的 worktree 和分支。过期的 worktree 条目也会被清理。

在 `wt list` 中，候选项显示 `_`（相同提交）或 `⊂`（内容已集成）。运行 `--dry-run` 可预览。完整的集成判定标准参见 `wt remove --help`。

锁定的 worktree 和主 worktree 始终会跳过。当前 worktree 最后移除，并触发切换目录到主 worktree。每次移除都会运行 pre-remove 和 post-remove hook；如果某个候选项的 hook 包含尚未批准的项目命令，则会跳过并显示 `(approval required)`（可使用 `wt config approvals add` 预先批准，或传入 `--yes`）。

### 最小年龄保护

比 `--min-age` 更年轻的 worktree（默认：1 天）会被跳过。这可以防止移除刚从默认分支创建的 worktree——它看起来“已合并”，因为其分支指向同一个提交。

```bash
$ wt step prune --min-age=0s     # no age guard
$ wt step prune --min-age=2d     # skip worktrees younger than 2 days
```

### 示例

预览将移除的内容：

```bash
$ wt step prune --dry-run
```

移除所有已合并的 worktree：

```bash
$ wt step prune
```

### 命令参考

```
wt step prune - [experimental] Remove worktrees merged into the default branch

Usage: wt step prune [OPTIONS]

Options:
      --dry-run
          Show what would be removed

      --min-age <MIN_AGE>
          Skip worktrees younger than this

          [default: 1d]

      --foreground
          Run removal in foreground (block until complete)

      --format <FORMAT>
          Output format

          [default: text]
          [possible values: text, json]

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

## wt step relocate

[experimental]

将 worktree 移到预期路径。重新定位路径不符合 worktree-path 模板的 worktree。

### 示例

预览将移动的内容：

```bash
$ wt step relocate --dry-run
```

移动所有路径不匹配的 worktree：

```bash
$ wt step relocate
```

自动提交并处理阻塞项（绝不失败）：

```bash
$ wt step relocate --commit --clobber
```

移动指定的 worktree：

```bash
$ wt step relocate feature bugfix
```

### 交换处理

当 worktree 位于彼此的预期位置时（例如 `alpha` 位于
`repo.beta`，`beta` 位于 `repo.alpha`），relocate 会使用
临时位置自动解决此问题。

### 处理阻塞项

使用 `--clobber` 时，会在重新定位前把目标位置上不属于 worktree 的路径移到
`<path>.bak.<timestamp>`。如果该名称已被占用，
移动会递增编号（`…-2`、`…-3` 等），直到找到空闲名称，因此
绝不会覆盖已有备份。

### 主 worktree 行为

主 worktree 无法使用 `git worktree move` 移动。因此，relocate
会把它切换到默认分支，并在预期路径创建新的链接式 worktree。
未跟踪文件和被 gitignore 的文件仍留在原位置。

### 有未提交改动的 worktree

链接式 worktree 会按原样重新定位——`git worktree move` 会带着未提交
改动一起移动。只有主 worktree 在有未提交改动时会跳过（其 `git checkout`
会拒绝），除非传入 `--commit`。

### 跳过的 worktree

- **有未提交改动的主 worktree**（未使用 `--commit`）——使用 `--commit` 先自动提交
- **已锁定**——使用 `git worktree unlock` 解锁
- **目标被阻塞**（未使用 `--clobber`）——使用 `--clobber` 备份阻塞项
- **Detached HEAD**——没有分支可用于计算预期路径

### 命令参考

```
wt step relocate - [experimental] Move worktrees to expected paths

Relocates worktrees whose path doesn't match the worktree-path template.

Usage: wt step relocate [OPTIONS] [BRANCHES]...

Arguments:
  [BRANCHES]...
          Worktrees to relocate (defaults to all mismatched)

Options:
      --dry-run
          Show what would be moved

      --commit
          Commit uncommitted changes before relocating

      --clobber
          Backup non-worktree paths at target locations

          Moves blocking paths to <path>.bak.<timestamp>. If that name is taken, counts up (…-2, …-3
          , …) to a free name.

  -h, --help
          Print help (see a summary with '-h')

Automation:
      --format <FORMAT>
          Output format

          JSON prints structured result to stdout after the relocate completes.

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

## wt step tether

[experimental]

运行命令；当其 worktree 被移除时，终止该命令的整个进程树。清理会自动进行，不需要 pre-remove hook；进程组会先收到 SIGTERM，再收到 SIGKILL。

### 原因

使用 `post-start` hook 启动长期运行的进程，再用 `pre-remove` hook
停止它，通常已经足够。但 `pre-remove` 只会在 Worktrunk 移除
worktree 时运行，因此 `git worktree remove`、`rm -rf` 或崩溃的 hook 都会
跳过它。worktree 经过足够多次更替后，难免有进程比其 worktree 存活得更久；
如果不清理，这些泄漏会不断累积（在 macOS 上最终会耗尽
`fseventsd`）。`tether` 消除了对 `pre-remove` 的需要：它会将
命令的生命周期绑定到 worktree，并在 worktree 消失后终止整个
进程组。

### 参数

`--` 后面的参数是程序及其参数，直接运行，不经过 shell。

```bash
$ wt step tether -- npm run dev
```

对于管道、重定向、变量或通配模式，请封装在 `sh -c` 中：

```bash
$ wt step tether -- sh -c 'PORT=$P npm run dev | tee dev.log'
```

要从子目录运行命令，请传入全局 `-C` flag（清理监视的
仍是 worktree 根目录，因此使用相对 `-C` 启动的服务器也会
随 worktree 一起终止）：

```bash
$ wt step tether -C frontend -- npm run dev
```

### 示例

运行开发服务器，并在 worktree 消失时自动清理：

```toml
# .config/wt.toml
[post-start]
server = "wt step tether -- npm run dev -- --port {{ branch | hash_port }}"
```

### 命令参考

```
wt step tether - [experimental] Run a command; kill its whole process tree when its worktree is removed

Teardown is automatic and needs no pre-remove hook; the group gets SIGTERM then SIGKILL.

Usage: wt step tether [OPTIONS] -- <COMMAND>...

Arguments:
  <COMMAND>...
          Command to run (after --, run directly, no shell)

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
