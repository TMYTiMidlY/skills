> 本文是 `reference/extending.md` 的中文翻译副本，随上游同步需重译；行为以英文原文为准。

# 扩展 Worktrunk

Worktrunk 有三种扩展机制。

**[Hook](#hooks)** 是在生命周期事件（切换、启动、提交、合并、移除）发生时自动运行的 shell 命令。在 TOML 中定义。

**[别名](#aliases)** 是以 `wt <name>` 调用的可复用 shell 命令。在 TOML 中定义。

**[自定义子命令](#custom-subcommands)** 是以 `wt <name>` 调用的独立可执行文件。把 `wt-foo` 放到 `PATH` 中，它就会成为 `wt foo`。

| | Hook | 别名 | 自定义子命令 |
|---|---|---|---|
| **触发方式** | 自动（生命周期事件） | 手动（`wt <name>`） | 手动（`wt <name>`） |
| **定义位置** | TOML 配置 | TOML 配置 | `PATH` 中的任意可执行文件 |
| **模板变量** | 有 | 有 | 无 |
| **可通过仓库共享** | `.config/wt.toml` | `.config/wt.toml` | 分发二进制文件 |
| **语言** | Shell 命令 | Shell 命令 | 任意 |

Hook 和别名位于同一个 TOML 配置中，并共享[模板引擎](https://worktrunk.dev/hook/#template-variables)。用户配置受信任；项目配置首次运行时需要批准。当两者定义了相同名称时，两者都会运行（用户配置先运行）。

## <a id="hooks"></a>Hook

十种 hook 覆盖五个生命周期事件——switch、start、commit、merge、remove——每个事件都有阻塞式 `pre-` 变体（失败会中止操作）和后台 `post-` 变体。[`wt hook`](https://worktrunk.dev/hook/#hook-types) 列出了每种 hook 的运行时机和典型用途。

```toml
[pre-start]
deps = "npm ci"

[post-start]
server = "npm run dev -- --port {{ branch | hash_port }}"

[pre-merge]
test = "npm test"
```

完整参考和内置方案（每个 worktree 一个开发服务器、每个 worktree 一个数据库、渐进式验证）参见 [`wt hook`](https://worktrunk.dev/hook/)。[技巧与模式](https://worktrunk.dev/tips-patterns/)还提供了更多内容。

## <a id="aliases"></a>别名

别名在 `[aliases]` 下配置：

```toml
[aliases]
deploy = "fly deploy --config=fly.{{ env }}.toml --app=myapp-{{ branch }}"
open = "open http://localhost:{{ branch | hash_port }}"
since-main = "git log --oneline {{ default_branch }}..HEAD"
```

```bash
wt deploy --env=staging
wt open
```

`wt <name>` 会先解析为内置命令，再解析为别名，最后解析为[自定义子命令](#custom-subcommands)。

### 模板

别名使用与 hook 相同的[模板引擎](https://worktrunk.dev/hook/#template-variables)：变量、[过滤器](https://worktrunk.dev/hook/#worktrunk-filters)、[函数](https://worktrunk.dev/hook/#worktrunk-functions)和 [`--KEY=VALUE` 智能路由](https://worktrunk.dev/hook/#passing-values)（如果模板引用 `KEY`，就绑定该值；否则转发到 `{{ args }}`）。例如，`wt deploy --env=staging` 会设置 `{{ env }}`。

别名模板额外提供 `{{ args }}`，用于接收位置 CLI 参数。操作上下文变量（`target`、`base`、`pr_number`）不会自动填充，但仍可通过 `--KEY=VALUE` 绑定。

### 位置参数

`{{ args }}` 会渲染为以空格连接并经过 shell 转义的字符串，可以直接插入命令：

```toml
[aliases]
s = "wt switch {{ args }}"
```

```bash
wt s some-branch
wt s feature/api
wt s 'has a space'
```

有关索引（`{{ args[0] }}`）、循环和计数，参见[传递值](https://worktrunk.dev/hook/#passing-values)。

`--` 之后的 token 会无条件转发，绕过所有绑定。写成 `wt deploy -- --branch=foo` 会把字面值 `--branch=foo` 转发到 `{{ args }}`，即使模板引用了 `{{ branch }}`。

如果别名把 `{{ args }}` 转发给 `wt` 命令——例如 `co = "wt switch {{ args }}"` 或 `cm = "wt step commit {{ args }}"`——它会继承该命令的参数和 flag 补全，因此 `wt co <Tab>` 会像 `wt switch <Tab>` 一样补全分支。

### 检查与预览

- `wt config alias show <name>` 输出模板。
- `wt config alias dry-run <name> [-- args...]` 输出渲染后的命令。

```bash
wt config alias show deploy
wt config alias dry-run deploy
wt config alias dry-run deploy -- --env=staging
```

### 多步骤流水线

`[[aliases.NAME]]` 使用[与 hook 相同的 `[[block]]` 语义](https://worktrunk.dev/hook/#hook-forms)定义流水线：block 按顺序运行，同一个 block 内的 key 并发运行，任一步骤失败都会中止其余步骤。

```toml
[[aliases.release]]
test = "cargo test"

[[aliases.release]]
build = "cargo build --release"
package = "cargo package --no-verify"

[[aliases.release]]
publish = "cargo publish {{ args }}"
```

每个步骤都会看到相同的 `{{ args }}` 和已绑定变量。`wt release -- --dry-run` 会把 `--dry-run` 转发给 `publish`，而不影响之前的步骤。

### 更改目录

即使从别名中调用，`wt switch`、`wt merge`（离开已移除的源 worktree 时）以及对当前 worktree 执行的 `wt remove` 也会更改父 shell 的目录；Worktrunk shell 集成会把该更改传递出去。其他 shell 状态不会保留：别名在子 shell 中运行，因此 `cd`、`export` 和类似命令只影响该子 shell。

### 推迟到嵌套 `wt` 命令再展开

如果某个 `wt step for-each` 别名在每个 worktree 中都输出相同的分支，说明 `{{ branch }}` 展开得太早。别名主体会在分派时、调用命令的 worktree 中渲染一次，因此裸写的 `{{ branch }}` 会在 for-each 迭代之前就固化为该 worktree 的分支。（`wt config alias dry-run <name>` 会显示渲染后的主体，其中该值已经固化。）

`{% raw %}…{% endraw %}` 会推迟变量展开：它在分派渲染后仍以字面量 `{{ branch }}` 存在，再由 for-each 针对每个 worktree 展开。`for-each` 还有一个注意点：推迟后的 `{{ branch }}` 含有空格，因此别名主体的 `sh -c` 会在 for-each 看到它之前，将其拆成 `{{`、`branch`、`}}`（`Failed to expand for-each argument: syntax error`）。请为 for-each 提供自己的 `sh -c '…'`，让该值保持为一个 token：

```toml
[aliases]
show-branches = "wt step for-each -- sh -c 'echo {% raw %}{{ branch }}{% endraw %}'"
```

`wt show-branches` 会输出每个 worktree 自己的分支。

`wt switch --execute` 以相同方式推迟展开，但不需要额外包装器：它的 `--execute '…'` 参数已经是一个带引号的字符串，因此只需 `{% raw %}`。在这里，`{{ worktree_path }}` 会相对正在创建的 worktree 展开，而不是相对运行别名的 worktree：

```toml
[aliases]
echo-target = "wt switch {{ args }} --no-cd --execute 'echo {% raw %}{{ worktree_path }}{% endraw %}'"
```

`{{ default_branch }}` 这样的仓库级变量不需要推迟：它在每个 worktree 中都相同，因此裸写的 `{{ default_branch }}` 在任何位置都已经正确。

### 方案：把每个 worktree rebase 到各自的上游

```toml
[aliases]
up = '''
git fetch --all --prune && wt step for-each -- sh -c '
  git rev-parse --verify -q @{u} >/dev/null || exit 0
  g=$(git rev-parse --git-dir)
  test -d "$g/rebase-merge" -o -d "$g/rebase-apply" && exit 0
  git update-index --refresh -q >/dev/null || true
  git rebase @{u} --no-autostash || git rebase --abort
''''
```

`wt up` 会 fetch 所有远端，然后迭代每个 worktree：没有上游则跳过，正处于 rebase 中则跳过，刷新索引以清除过期的 stat 条目，然后 rebase，并在冲突时自动中止。它 rebase 到 git 原生的 `@{u}`，而不是 `{{ … }}` 模板，因此 git 会解析每个 worktree 自己的上游，没有任何内容需要推迟展开。

### 方案：把进行中的更改移动或复制到新 worktree

`wt switch --create` 会让你进入一个干净的 worktree。要把已暂存、未暂存和未跟踪的更改一起带过去，请配合使用 `git stash`：

```toml
# .config/wt.toml
[aliases]
move-changes = '''
if git diff --quiet HEAD && test -z "$(git ls-files --others --exclude-standard)"; then
  wt switch --create {{ to }} --execute="{{ args }}"
else
  git stash push --include-untracked --quiet
  wt switch --create {{ to }} --execute="git stash pop --index; {{ args }}"
fi
'''
```

使用 `wt move-changes --to=feature-xyz` 运行。如果没有进行中的更改，前置判断会跳过 stash；否则，`git stash push` 会捕获所有内容，而 `--execute` 会在新 worktree 中 pop，并完整保留已暂存/未暂存的划分。`--` 之后的任何内容都会在 pop 后于新 worktree 中运行。例如，`wt move-changes --to=feature-xyz -- claude` 会在那里打开 Claude。

若要复制而不是移动，请紧接 push 之后添加 `git stash apply --index --quiet`。

### 方案：持续查看指定的 hook 日志

`wt config state logs --format=json` 会输出结构化条目（`branch`、`source`、`hook_type`、`name`、`path`）。通过管道传给 `jq` 以解析一个条目，再将其包装成别名以便快速访问：

```toml
[aliases]
hook-log = '''
tail -f "$(wt config state logs --format=json | jq -r --arg name "{{ name | sanitize_hash }}" --arg kind "{{ kind }}" '
  .hook_output[]
  | select(.branch == "{{ branch | sanitize_hash }}" and .hook_type == $kind and .name == $name)
  | .path
' | head -1)"
'''
```

使用 `wt hook-log --kind=post-start --name=server` 运行，以持续查看当前分支上 `server` hook 的日志。`--kind` 选择 hook 类型；分支通过 `{{ branch }}` 从当前 worktree 取得。`sanitize_hash` 会把 `branch` 和 `name` 改写成文件系统安全的形式，并添加哈希后缀以确保不同原值仍然唯一（与 Worktrunk 在磁盘上应用的变换相同），因此即使任一值包含 `/` 等字符，别名也能解析出正确日志。

## <a id="custom-subcommands"></a>自定义子命令

[实验性]

任何名为 `wt-<name>` 且位于 `PATH` 中的可执行文件都会变成 `wt <name>`，这与 git 为 `git-foo` 使用的模式相同。内置命令和[别名](#aliases)优先。

```bash
wt sync origin              # runs: wt-sync origin
wt -C /tmp/repo sync        # -C is forwarded as the child's working directory
```

参数会逐字传递，继承标准输入输出，子进程的退出码也会原样传播。

### 示例

- [`worktrunk-sync`](https://github.com/pablospe/worktrunk-sync)：按从 git 历史推断出的依赖顺序 rebase 堆叠的 worktree 分支。使用 `cargo install worktrunk-sync` 安装，然后以 `wt sync` 运行。
- [`workz`](https://github.com/rohansx/workz)：为当前 worktree 配置无冲突的端口范围、独立数据库和 Docker Compose 项目，并合并到 `.env.local`，使并行 worktree 互不冲突。使用 `cargo install workz` 安装，把它的 [`wt-workz`](https://github.com/rohansx/workz/blob/main/examples/wt-workz) 适配器放到 `PATH` 中，然后以 `wt workz` 运行。

## 参考：hook 与别名

除以下差异外，hook 和别名的行为相同。

<details>
<summary>接口差异</summary>

| 维度 | Hook | 别名 |
|------|-------|---------|
| 调用方式 | `wt hook <type> [args...]`（嵌套在内置 `hook` 命令下） | `wt <name> [args...]`（顶层） |
| 裸位置参数 | 过滤名称（`wt hook pre-merge test build` 只运行 `test` 和 `build`） | 转发到 `{{ args }}` |
| 从位置参数传入 `{{ args }}` | 必须使用 `--`（`wt hook pre-merge -- extra`） | 任何裸位置参数都会进入其中 |
| 跳过批准的 flag | 支持放在子命令之后的 `--yes` / `-y`（`wt hook pre-merge --yes`） | 只支持全局形式（`wt -y <alias>`）；放在别名之后的 `--yes` 会进入 `{{ args }}` |
| 来源区分 | `user:` / `project:` / `user:name` / `project:name` 过滤语法 | 先运行用户配置，再运行项目配置；无过滤语法 |
| 强制绑定转义方式 | `--var KEY=VALUE`（已弃用，建议改用 `--KEY=VALUE`，但仍会强制绑定） | 无；智能路由是唯一途径 |
| `--help` | `wt hook --help` 列出 hook 类型；`wt hook <type> --help` 显示该类型的 flag 和参数 | 模板主体就是文档：`wt <alias> --help` 会重定向到 `wt config alias show` / `dry-run`。`wt --help` 和 `wt step --help` 会在内置命令旁列出已配置的别名 |
| 检查 | `wt hook show [type] [--expanded]` | `wt config alias show <name>` / `wt config alias dry-run <name>` |
| Stdin | 所有模板变量的 JSON（使用 `json.load(sys.stdin)` 解析） | 继承父进程 stdin（管道会传递；`wt switch` 等交互式 TUI 会保留 tty） |
| 模板上下文额外变量 | `hook_type`、`hook_name`、每种类型的操作变量（`base`、`target`、`pr_number`、……） | 在共享基础变量之上增加 `args` |

</details>
