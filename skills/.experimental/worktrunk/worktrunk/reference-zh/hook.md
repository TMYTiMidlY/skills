> 本文是 `reference/hook.md` 的中文翻译副本，随上游同步需重译；行为以英文原文为准。

# wt hook

运行已配置的 hook。

hook 是在 worktree 生命周期关键节点运行的 shell 命令——可在 `wt switch`、`wt merge` 和 `wt remove` 期间自动运行，也可通过 `wt hook <type>` 按需运行。用户 hook 和项目 hook 均受支持。

# Hook 类型

| 事件 | `pre-`——阻塞 | `post-`——后台 |
|-------|-------------------|---------------------|
| **switch** | `pre-switch` | `post-switch` |
| **create** | `pre-start` | `post-start` |
| **commit** | `pre-commit` | `post-commit` |
| **merge** | `pre-merge` | `post-merge` |
| **remove** | `pre-remove` | `post-remove` |

`pre-*` hook 会阻塞——失败会中止操作。`post-*` hook 在后台运行，输出会写入日志（使用 [`wt config state logs`](https://worktrunk.dev/config/#wt-config-state-logs) 查找和管理日志文件）。使用 `-v` 查看后台 hook 的模板变量；`wt hook <type> --dry-run` 可预览命令。

最常用的创建 hook 是 `post-start`——它会运行后台任务（开发服务器、文件复制、构建），而不阻塞 worktree 创建。除非后续步骤必须先等工作完成，否则优先使用 `post-start`，而不是 `pre-start`。

| Hook | 用途 |
|------|---------|
| `pre-switch` | 切换前在源 worktree 中运行——无论是创建、切换到现有 worktree，还是停留在当前 worktree |
| `post-switch` | 对所有切换结果触发：创建、切换到现有 worktree，或停留在当前 worktree |
| `pre-start` | 创建新 worktree 时运行一次，并阻塞 `post-start`/`--execute`，直到完成：安装依赖、生成环境文件 |
| `post-start` | 创建新 worktree 时在后台运行一次：开发服务器、长时间构建、文件监视器、复制缓存 |
| `pre-commit` | 格式化工具、linter、类型检查——在 `wt merge` 期间、squash 提交之前运行 |
| `post-commit` | 触发 CI、发送通知、后台 lint |
| `pre-merge` | 测试、安全扫描、构建验证——在 rebase 之后、合并到目标之前运行 |
| `post-merge` | 部署、通知、安装更新后的二进制文件。如果目标分支有 worktree，则在其中运行；否则在主 worktree 中运行 |
| `pre-remove` | 删除 worktree 前清理：保存测试产物、备份状态。在正被移除的 worktree 中运行 |
| `post-remove` | 停止开发服务器、移除容器、通知外部系统。模板变量引用已移除的 worktree |

在 `wt merge` 期间，hook 按以下顺序运行：pre-commit → post-commit → pre-merge → pre-remove → post-remove + post-merge。完整流水线见 [`wt merge`](https://worktrunk.dev/merge/#pipeline)。

# 安全

项目命令首次运行时需要批准：

```
▲ repo needs approval to execute 3 commands:

○ pre-start install:
   npm ci
○ pre-start build:
   cargo build --release
○ pre-start env:
   echo 'PORT={{ branch | hash_port }}' > .env.local

❯ Allow and remember? [y/N]
```

- 批准记录保存在 `~/.config/worktrunk/approvals.toml`
- 命令发生变化后需要重新批准
- 拒绝会跳过本次操作的所有项目命令——包括任何已批准的命令——然后在不运行它们的情况下继续；已保存的批准记录不受影响
- 使用 `--yes` 绕过提示——适用于 CI 和自动化
- 使用 `--no-hooks` 跳过 hook

使用 `wt config approvals add` 和 `wt config approvals clear` 管理批准记录。

# 配置

hook 可在项目配置（`.config/wt.toml`）或用户配置（`~/.config/worktrunk/config.toml`）中定义。两者使用相同格式。项目配置从运行命令的 worktree 中读取。

## Hook 形式

hook 有三种形式，由其 TOML 结构决定。

字符串表示单条命令：

```toml
pre-start = "npm install"
```

表表示并发运行的多条命令：

```toml
[post-start]
server = "npm run dev"
watch = "npm run watch"
```

流水线是依次运行的一系列 `[[hook]]` 块。每个块是一个步骤；块内的多个键并发运行。某一步失败会中止流水线的其余部分：

```toml
[[post-start]]
install = "npm ci"

[[post-start]]
build = "npm run build"
server = "npm run dev"
```

这里先运行 `install`，然后同时运行 `build` 和 `server`。

模板会在流水线开始前接受语法检查，并在每一步运行时渲染，因此某一步可以存储[每分支 vars](https://worktrunk.dev/config/#wt-config-state-vars)，供后续步骤通过 `{{ vars.<key> }}` 读取。由于较早的步骤仍可能更改这些值，预览会保持它们不变：`wt hook <type> --dry-run` 和 `wt hook show --expanded` 会将 `{{ vars.<key> }}` 渲染为其自身，其他所有变量则正常展开。

大多数 hook 不需要 `[[hook]]` 块。只有存在依赖链时才使用它们——通常是某项设置必须先完成，后续步骤才能开始，例如先安装依赖，再并发运行构建和开发服务器。

## 项目 hook 与用户 hook

| 方面 | 项目 hook | 用户 hook |
|--------|--------------|------------|
| 位置 | `.config/wt.toml` | `~/.config/worktrunk/config.toml` |
| 作用域 | 单个仓库 | 所有仓库（或[按项目](https://worktrunk.dev/config/#user-project-specific-settings)） |
| 批准 | 需要 | 不需要 |
| 执行顺序 | 在用户 hook 之后 | 最先 |

使用 `--no-hooks` 跳过所有 hook。如果用户和项目都定义了同名 hook，要运行其中一个指定 hook，请使用 `user:name` 或 `project:name` 语法。

## 模板变量

hook 可使用在运行时展开的模板变量：

| 类别 | 变量 | 说明 |
|------|----------|-------------|
| 活动对象  | `{{ branch }}`                | 分支名 |
|           | `{{ worktree_path }}`         | worktree 路径 |
|           | `{{ worktree_name }}`         | worktree 目录名 |
|           | `{{ commit }}`                | 分支 HEAD SHA |
|           | `{{ short_commit }}`          | 分支 HEAD SHA，按 `core.abbrev` 缩写 |
|           | `{{ upstream }}`              | 分支上游（如果跟踪远端） |
| 操作      | `{{ base }}`                  | 基础分支名（仅限 switch/create） |
|           | `{{ base_worktree_path }}`    | 基础 worktree 路径 |
|           | `{{ target }}`                | 目标分支名 |
|           | `{{ target_worktree_path }}`  | 目标 worktree 路径（当目标有 worktree 时） |
|           | `{{ pr_number }}`             | PR/MR 编号（post-switch、pre-start、post-start；通过 `pr:N` / `mr:N` 创建时） |
|           | `{{ pr_url }}`                | PR/MR Web URL（post-switch、pre-start、post-start；通过 `pr:N` / `mr:N` 创建时） |
| 仓库      | `{{ repo }}`                  | 仓库目录名 |
|           | `{{ repo_path }}`             | 仓库根目录的绝对路径 |
|           | `{{ owner }}`                 | 主要远端的所有者路径（可能包含子组） |
|           | `{{ primary_worktree_path }}` | 主 worktree 路径 |
|           | `{{ default_branch }}`        | 默认分支名 |
|           | `{{ remote }}`                | 主要远端名称 |
|           | `{{ remote_url }}`            | 远端 URL |
| 执行      | `{{ cwd }}`                   | hook 命令的运行目录 |
|           | `{{ hook_type }}`             | 正在运行的 hook 类型（例如 `pre-start`、`pre-merge`） |
|           | `{{ hook_name }}`             | hook 命令名称（如果有名称） |
|           | `{{ args }}`                  | 从 CLI 转发的 token——见[手动运行 Hook](#running-hooks-manually) |
| 用户      | `{{ vars.<key> }}`            | 来自 [`wt config state vars`](https://worktrunk.dev/config/#wt-config-state-vars) 的每分支变量 |

`repo` 变量（`repo`、`repo_path`、`owner`、`primary_worktree_path`、`default_branch`、`remote`、`remote_url`）在整个仓库中保持不变——每个 worktree 的 `default_branch` 都相同。`active` 变量（`branch`、`worktree_path`、`worktree_name`、`commit`、`short_commit`、`upstream`）则随 worktree 而变化。

裸变量（`branch`、`worktree_path`、`commit`）指向操作所作用的分支：switch/create 时为目标，merge/remove 时为源。`base` 和 `target` 表示另一侧：

| 操作 | 裸变量 | `base` | `target` |
|-----------|-----------|--------|----------|
| switch/create | 目标 | 来源位置 | = 裸变量 |
| commit（merge/squash 期间） | 正在被 squash 的 worktree | = 裸变量 | 集成目标 |
| merge | 正在合并的功能分支 | = 裸变量 | 合并目标 |
| remove | 正在移除的分支 | = 裸变量 | 最终到达位置 |

所有 hook 都采用相同视角——`{{ branch | hash_port }}` 在 `post-start` 和 `post-remove` 中生成相同端口。

`cwd` 是 hook 命令运行时所在的 worktree 根目录。除以下三种情况外，它等于 `worktree_path`：

- `pre-switch`：hook 在源 worktree 中运行；`worktree_path` 是目标
- `post-remove`：活动 worktree 已不存在，因此 hook 在主 worktree 中运行
- 伴随移除的 `post-merge`：活动 worktree 已不存在，因此 hook 在目标 worktree 中运行

未定义变量会报错——可使用条件语句或默认值实现可选行为：

```toml
[pre-start]
# Rebase onto upstream if tracking a remote branch (e.g., wt switch --create feature origin/feature)
sync = "{% if upstream %}git fetch && git rebase {{ upstream }}{% endif %}"
```

对任何会触发 hook 的命令使用 `-v`，即可查看实际调用中解析出的变量——每个 hook 都会打印一个 `template variables:` 块，显示作用域内每个变量及其值（未填充的条件变量显示 `(unset)`，例如执行 `wt switch -` 时的 `target_worktree_path`）。别名在 `-v` 下也相同：`wt -v <alias>` 会在流水线运行前打印别名作用域内的变量。

变量支持点访问，并可对缺失键使用 `default` 过滤器。JSON 对象/数组值会自动解析，因此当值为 `{"port": 3000}` 时，`{{ vars.config.port }}` 可以正常工作：

```toml
[post-start]
dev = "ENV={{ vars.env | default('development') }} npm start -- --port {{ vars.config.port | default('3000') }}"
```

## Worktrunk 过滤器

模板支持使用 Jinja2 过滤器转换值：

| 过滤器 | 示例 | 说明 |
|--------|---------|-------------|
| `sanitize` | `{{ branch \| sanitize }}` | 将 `/` 和 `\` 替换为 `-` |
| `sanitize_db` | `{{ branch \| sanitize_db }}` | 带哈希后缀的数据库安全标识符（`[a-z0-9_]`，最长 48 个字符） |
| `sanitize_hash` | `{{ branch \| sanitize_hash }}` | 带哈希后缀、用于确保唯一性的文件系统安全名称 |
| `hash` | `{{ branch \| hash }}` | 输入值的 3 字符 base36 摘要 |
| `hash_port` | `{{ branch \| hash_port }}` | 哈希到端口 10000-19999 |
| `dirname` | `{{ repo_path \| dirname }}` | 移除最后一个路径组成部分（`/a/b/c` → `/a/b`） |
| `basename` | `{{ repo_path \| basename }}` | 仅保留最后一个路径组成部分（`/a/b/c` → `c`） |
| `codename(n)` | `{{ branch \| codename(2) }}` | 确定性的友好单词 |

`sanitize_db` 过滤器会生成数据库安全标识符——小写字母数字和下划线、不以数字开头，并带有 3 字符哈希后缀，以避免冲突和保留字。`sanitize_hash` 过滤器会生成文件系统安全名称；如果净化改变了输入，则追加 3 字符哈希后缀，因此不同的原始值绝不会冲突——本身已经安全的名称会原样通过。`codename(n)` 过滤器根据输入字符串生成确定性的友好名称：`codename(1)` 返回一个名词，`codename(2)` 返回 `adjective-noun`，更高的数量会添加更多形容词。候选池很大（`codename(2)` 约有 126 万种组合），因此它通常可以单独作为 worktree 的末级目录名：

```toml
# Friendly branch-derived worktree names, e.g. myproject.malleable-opah
worktree-path = "{{ repo_path }}/../{{ repo }}.{{ branch | codename(2) }}"
```

如果既希望路径中有友好名称，又要保留原始分支身份，请将分支名放在父目录中：

```toml
worktree-path = "{{ repo_path }}/../worktrees/{{ branch | sanitize }}/{{ branch | codename(2) }}"
```

`hash` 过滤器是裸的 3 字符 base36 摘要，适合在输出预算紧张时组合自己的“截断并避免冲突”配方（例如 Unix socket 路径上限为 107 字节）：

```toml
# Truncated branch slug + hash: collisions remain disambiguated even when prefixes match
worktree-path = "/tmp/{{ (branch | sanitize)[:20] }}_{{ branch | sanitize | hash }}"
```

`dirname` 和 `basename` 过滤器用于遍历路径。对于位于 `myproject/.git` 这类隐藏目录中的裸仓库，它们很有用；此时 `{{ repo }}` 解析为 `.git`：

```toml
# Place worktrees as siblings of the bare repo, named `<wrapper>.<branch>`
worktree-path = "{{ repo_path }}/../{{ repo_path | dirname | basename }}.{{ branch | sanitize }}"
```

`hash_port` 过滤器适合让每个 worktree 的开发服务器运行在唯一端口上：

```toml
[post-start]
dev = "npm run dev -- --host {{ branch }}.localhost --port {{ branch | hash_port }}"
```

可以对任何字符串做哈希，包括拼接结果：

```toml
# Unique port per repo+branch combination
dev = "npm run dev --port {{ (repo ~ '-' ~ branch) | hash_port }}"
```

变量会自动进行 shell 转义——无需给 `{{ ... }}` 加引号；加引号反而可能在包含特殊字符时引发问题。

## Worktrunk 函数

模板还支持用于动态查找的函数：

| 函数 | 示例 | 说明 |
|----------|---------|-------------|
| `worktree_path_of_branch(branch)` | `{{ worktree_path_of_branch("main") }}` | 查找某分支的 worktree 路径 |

`worktree_path_of_branch` 函数接收分支名，返回该分支 worktree 的文件系统路径；如果该分支没有 worktree，则返回空字符串。它适合用来引用其他 worktree 中的文件：

```toml
[pre-start]
# Copy config from main worktree
setup = "cp {{ worktree_path_of_branch('main') }}/config.local {{ worktree_path }}"
```

## JSON 上下文

hook 会通过 stdin 接收包含所有模板变量的 JSON，从而能够实现模板无法表达的复杂逻辑：

```toml
[pre-start]
setup = "python3 scripts/pre-start-setup.py"
```

```python
import json, sys, subprocess
ctx = json.load(sys.stdin)
if ctx['branch'].startswith('feature/') and 'backend' in ctx['repo']:
    subprocess.run(['make', 'seed-db'])
```

## 复制未跟踪文件

有一条命令尤其值得单独说明：[`wt step copy-ignored`](https://worktrunk.dev/step/#wt-step-copy-ignored)。Git worktree 共享仓库，但不共享未跟踪文件；此命令会在 worktree 之间复制被 gitignore 忽略的文件：

```toml
[post-start]
copy = "wt step copy-ignored"
```

# <a id="running-hooks-manually"></a>手动运行 Hook

`wt hook <type>` 按需运行 hook——适合开发期间测试、在 CI 流水线中运行，或失败后重新运行。

```bash
$ wt hook pre-merge              # Run all pre-merge hooks
$ wt hook pre-merge test         # Run hooks named "test" from both sources
$ wt hook pre-merge test build   # Run hooks named "test" and "build"
$ wt hook pre-merge user:        # Run all user hooks
$ wt hook pre-merge project:     # Run all project hooks
$ wt hook pre-merge user:test    # Run only user's "test" hook
$ wt hook pre-merge --yes        # Skip approval prompts (for CI)
$ wt hook pre-start --branch=feature/test    # Override a template variable
$ wt hook pre-merge -- --extra args     # Forward tokens into {{ args }}
```

`user:` 和 `project:` 前缀按来源筛选。单独使用 `user:` 或 `project:` 可运行该来源的所有 hook；使用 `user:name` / `project:name` 可运行特定 hook。

```
$ wt hook pre-merge
◎ Running pre-merge project:test
  cargo test
    Finished test [unoptimized + debuginfo] target(s) in 0.12s
     Running unittests src/lib.rs (target/debug/deps/worktrunk-abc123)

running 18 tests
test auth::tests::test_jwt_decode ... ok
test auth::tests::test_jwt_encode ... ok
test auth::tests::test_token_refresh ... ok
test auth::tests::test_token_validation ... ok

test result: ok. 18 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.08s
◎ Running pre-merge project:lint
  cargo clippy
    Checking worktrunk v0.1.0
    Finished dev [unoptimized + debuginfo] target(s) in 1.23s
```

```bash
$ wt hook post-start
◎ Running post-start: project @ ~/acme
```

## 传递值

只要 hook 的任一命令中出现 `{{ KEY }}`，`--KEY=VALUE` 就会绑定 `KEY`——与 `wt <alias>` 使用相同的智能路由规则。内置变量也可以覆盖：`--branch=foo` 会在 hook 模板内设置 `{{ branch }}`（worktree 的实际分支不会移动）。键中的连字符会变成下划线：`--my-var=x` 设置 `{{ my_var }}`。

如果某个 `--KEY=VALUE` 的键未被 hook 模板引用，它会作为字面量 `--KEY=VALUE` token 转发到 `{{ args }}`。`--` 之后的 token 也会逐字转发到 `{{ args }}`。`{{ args }}` 渲染为用空格连接且经过 shell 转义的字符串；用 `{{ args[0] }}` 索引，用 `{% for a in args %}…{% endfor %}` 循环，用 `{{ args | length }}` 计数。

长形式 `--var KEY=VALUE` 已弃用，但仍受支持。无论 hook 模板是否引用 `KEY`，它都会强制绑定——当模板只在条件中引用该键时（例如 `{% if override %}…{% endif %}`），这一点很有用。

# 配方

- [消除冷启动](https://worktrunk.dev/tips-patterns/#eliminate-cold-starts)：在 `post-start` 中使用 `wt step copy-ignored` 共享构建缓存和依赖；当后续 hook 依赖复制结果时，使用 `[[post-start]]` 流水线
- [每个 worktree 一个开发服务器](https://worktrunk.dev/tips-patterns/#dev-server-per-worktree)：在 `post-start` 中使用 `wt step tether` 运行开发服务器，并在移除 worktree 时终止其整个进程组，还可选择配置子域名路由
- [每个 worktree 一个数据库](https://worktrunk.dev/tips-patterns/#database-per-worktree)：`post-start` 流水线将容器名、端口和连接字符串存为[每分支 vars](https://worktrunk.dev/config/#wt-config-state-vars)，供后续 hook 引用
- [渐进式验证](https://worktrunk.dev/tips-patterns/#progressive-validation)：在 `pre-commit` 中快速 lint/类型检查，在 `pre-merge` 中执行开销较大的测试和构建
- [针对目标的 hook](https://worktrunk.dev/tips-patterns/#target-specific-hooks)：在 `post-merge` 中根据 `{{ target }}` 分支判断，以便按环境部署

## 命令参考

```
wt hook - Run configured hooks

Usage: wt hook [OPTIONS] <COMMAND>

Commands:
  show         Show configured hooks
  pre-switch   Run pre-switch hooks
  post-switch  Run post-switch hooks
  pre-start    Run pre-start hooks
  post-start   Run post-start hooks
  pre-commit   Run pre-commit hooks
  post-commit  Run post-commit hooks
  pre-merge    Run pre-merge hooks
  post-merge   Run post-merge hooks
  pre-remove   Run pre-remove hooks
  post-remove  Run post-remove hooks

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
