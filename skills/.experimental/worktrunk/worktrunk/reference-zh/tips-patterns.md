> 本文是 `reference/tips-patterns.md` 的中文翻译副本，随上游同步需重译；行为以英文原文为准。

# 技巧与模式

常见 Worktrunk 工作流的实用配方。

## 新建 worktree 并启动 agent 的 shell 别名

用一条命令创建 worktree 并启动 Claude：

```bash
alias wsc='wt switch --create --execute=claude'
wsc new-feature                       # Creates worktree, runs hooks, launches Claude
wsc feature -- 'Fix GH #322'          # Runs `claude 'Fix GH #322'`
```

## `wt` 别名

结合模板过滤器和 [vars](https://worktrunk.dev/tips-patterns/#per-branch-variables)：

```toml
# .config/wt.toml
[aliases]
# Open this worktree's dev server
open = "open http://localhost:{{ branch | hash_port }}"

# Test with branch-specific features from vars
test = "cargo test --features {{ vars.features | default('default') }}"

# Switch via the interactive picker, print the chosen branch
pick = "wt switch --format=json | jq -r '.branch'"
```

有关作用域、审批和参考信息，请参阅[别名](https://worktrunk.dev/extending/#aliases)。

## 每分支变量

`wt config state vars` 保存每个分支的状态，可从模板（`{{ vars.key }}`）和 CLI 访问。用途包括：

- **在流水线步骤之间协调状态**——完整配方见下文[每个 worktree 一个数据库](https://worktrunk.dev/tips-patterns/#database-per-worktree)
- **将分支固定到某个环境**——运行 `wt config state vars set env=staging`，然后在 hook 中使用 `{{ vars.env | default('dev') }}`
- **按分支参数化别名**——参阅上文的 [`wt` 别名](https://worktrunk.dev/tips-patterns/#wt-aliases)

有关存储格式、JSON 支持和参考信息，请参阅 [`wt config state vars`](https://worktrunk.dev/config/#wt-config-state-vars)。

## 每个 worktree 一个开发服务器

每个 worktree 都在确定性端口上运行自己的开发服务器。`hash_port` 过滤器根据分支名生成稳定端口（10000-19999）：

```toml
# .config/wt.toml
[post-start]
server = "wt step tether -- npm run dev -- --port {{ branch | hash_port }}"

[list]
url = "http://localhost:{{ branch | hash_port }}"
```

[`wt step tether`](https://worktrunk.dev/step/#wt-step-tether) 会在独立进程组中运行服务器，并在移除 worktree 时关闭整个进程组，因此不需要 `pre-remove` hook。完整原理与平台行为请参阅 [`wt step tether`](https://worktrunk.dev/step/#wt-step-tether) 文档。

`wt list` 的 URL 列显示每个 worktree 的开发服务器：

```bash
$ wt list
  <b>Branch</b>       <b>Status</b>        <b>HEAD±</b>    <b>main↕</b>     <b>main…±</b>  <b>Remote⇅</b>  <b>URL</b>                     <b>Commit</b>
@ main           <span class=c>?</span> <span class=d>^</span><span class=d>⇅</span>                                    <span class=g>⇡1</span>  <span class=d><span class=r>⇣1</span></span>  <span class=d>http://localhost:12107</span>  <span class=d>41ee083</span>
+ feature-api  <span class=c>+</span>   <span class=d>↕</span><span class=d>⇡</span>     <span class=g>+54</span>   <span class=r>-5</span>   <span class=g>↑4</span>  <span class=d><span class=r>↓1</span></span>  <span class=g>+234</span>  <span class=r>-24</span>   <span class=g>⇡3</span>      <span class=d>http://localhost:10703</span>  <span class=d>6814f02</span>
+ fix-auth         <span class=d>↕</span><span class=d>|</span>                <span class=g>↑2</span>  <span class=d><span class=r>↓1</span></span>   <span class=g>+25</span>  <span class=r>-11</span>     <span class=d>|</span>     <span class=d>http://localhost:16460</span>  <span class=d>b772e68</span>
+ <span class=d>fix-typos</span>        <span class=d>_</span><span class=d>|</span>                                      <span class=d>|</span>     <span class=d>http://localhost:14301</span>  <span class=d>41ee083</span>

<span class=d>○</span> <span class=d>Showing 4 worktrees, 2 with changes, 2 ahead, 3 columns hidden</span>
```

在任何机器上，`fix-auth` 都会使用端口 16460。服务器未运行时，URL 会暗显。

## 每个 worktree 一个数据库

每个 worktree 都可以拥有自己的隔离数据库。流水线先将名称和端口设置为 [vars](https://worktrunk.dev/config/#wt-config-state-vars)，后续步骤和 hook 再引用它们：

```toml
[[post-start]]
set-vars = """
wt config state vars set \
  container='{{ repo }}-{{ branch | sanitize }}-postgres' \
  port='{{ ('db-' ~ branch) | hash_port }}' \
  db_url='postgres://postgres:dev@localhost:{{ ('db-' ~ branch) | hash_port }}/{{ branch | sanitize_db }}'
"""

[[post-start]]
db = """
docker run -d --rm \
  --name {{ vars.container }} \
  -p {{ vars.port }}:5432 \
  -e POSTGRES_DB={{ branch | sanitize_db }} \
  -e POSTGRES_PASSWORD=dev \
  postgres:16
"""

[pre-remove]
db-stop = "docker stop {{ vars.container }} 2>/dev/null || true"
```

流水线的第一步根据分支推导值并将其存为 vars。第二步引用 `{{ vars.container }}` 和 `{{ vars.port }}`——模板会在每一步运行时渲染，因此届时 vars 已经设置好。`pre-remove` 读取相同的 vars 来停止容器。

`('db-' ~ branch)` 拼接后的哈希不同于单独的 `branch`，因此数据库端口不会与开发服务器端口冲突。`sanitize_db` 过滤器会生成数据库安全的标识符（小写、下划线、不以数字开头，并带有短哈希后缀）。

连接字符串可在任何位置访问——不只限于 hook：

```bash
DATABASE_URL=$(wt config state vars get db_url) npm start
```

## 每个 worktree 的环境变量

要将环境变量限定到某个 worktree——例如工具的软件包路径、配置档或 API 端点——请使用 [direnv](https://direnv.net) 或 [mise](https://mise.jdx.dev) 之类的目录环境管理器。两者都会 hook shell 提示词，因此会在 `wt switch` 已经执行的 `cd` 上激活——无需 Worktrunk 配置。将配置提交到仓库根目录后，每个 worktree 都会获得自己的副本，路径相对于该 worktree 解析。

**direnv**——在仓库根目录提交 `.envrc`：

```sh
export MY_PACKAGES_PATH="$PWD/.packages"
```

每个 worktree 需运行一次 `direnv allow` 以信任该文件（[入门指南](https://direnv.net/#getting-started)）。此后，切换进入 worktree 会加载环境，切换离开则会卸载。

**mise**——在仓库根目录提交 `mise.toml`：

```toml
[env]
MY_PACKAGES_PATH = "{{ config_root }}/.packages"
```

`{{ config_root }}` 是 mise 用来解析相对路径的项目根目录（[环境指令](https://mise.jdx.dev/environments/)）——即 worktree 根目录，而非主 worktree。mise 还支持 Windows / PowerShell，而 direnv 原生不支持。

两者都会在 shell 会话中设置真实环境变量，因此每个子进程——hook、构建工具、子 shell——都会继承，无需使用 `--execute` 变通方案。每个新 worktree 都是一个新路径，因此需要各自执行一次信任步骤（`direnv allow` / `mise trust`）；Worktrunk 刻意不会绕过该提示，这与[在项目别名和 hook 正文中禁用 `--execute`](https://github.com/max-sixty/worktrunk/issues/2101)背后的安全理由相同。

## 消除冷启动

使用 [`wt step copy-ignored`](https://worktrunk.dev/step/#wt-step-copy-ignored) 在 worktree 之间复制被 gitignore 忽略的文件（缓存、依赖、`.env`）：

```toml
[post-start]
copy = "wt step copy-ignored"
```

当另一个 hook 依赖复制结果时——例如先复制 `node_modules/`，再运行 `pnpm install` 以便安装过程复用缓存的软件包——请用 `[[post-start]]` 流水线依次执行：

```toml
[[post-start]]
copy = "wt step copy-ignored"

[[post-start]]
install = "pnpm install"
```

如果某条 `--execute` 命令需要立即使用复制的文件，请改用 `pre-start`。

默认复制所有被 gitignore 忽略的文件。要限制复制内容，请创建带模式的 `.worktreeinclude`——文件必须既被 gitignore 忽略，又列在其中。详情见 [`wt step copy-ignored`](https://worktrunk.dev/step/#wt-step-copy-ignored)。

## 手写提交消息

`commit.generation.command` 从 stdin 接收渲染后的提示词，并将提交消息返回到 stdout。若要手写提交消息而不使用 LLM，请将它指向 `$EDITOR`：

```toml
# ~/.config/worktrunk/config.toml
[commit.generation]
command = '''f=$(mktemp); printf '\n\n' > "$f"; sed 's/^/# /' >> "$f"; ${EDITOR:-vi} "$f" < /dev/tty > /dev/tty; grep -v '^#' "$f"'''
```

这会为渲染后的提示词（diff、分支名、统计信息）添加 `#` 前缀将其注释掉，打开编辑器，并在保存时移除注释行。顶部的两个空行留出输入空间；下方可见提示词上下文以供参考。

若要保留 LLM 作为默认值，但在某次特定合并中使用编辑器，请添加一个 [Worktrunk 别名](https://worktrunk.dev/extending/#aliases)：

```toml
# ~/.config/worktrunk/config.toml
[aliases]
mc = '''WORKTRUNK_COMMIT__GENERATION__COMMAND='f=$(mktemp); printf "\n\n" > "$f"; sed "s/^/# /" >> "$f"; ${EDITOR:-vi} "$f" < /dev/tty > /dev/tty; grep -v "^#" "$f"' wt merge'''
```

之后，`wt mc` 会打开编辑器撰写提交消息，而普通的 `wt merge` 仍继续使用 LLM。

## 跟踪 agent 状态

自定义 emoji 标记会在 `wt list` 中显示 agent 状态。[Claude Code](https://worktrunk.dev/claude-code/) 插件和 [OpenCode 插件](https://github.com/max-sixty/worktrunk/tree/main/dev/opencode-plugin.ts)会自动设置这些标记：

```
+ feature-api      ↑  🤖              ↑1      ./repo.feature-api
+ review-ui      ? ↑  💬              ↑1      ./repo.review-ui
```

- `🤖`——agent 正在工作
- `💬`——agent 正在等待输入

可为任何工作流手动设置状态：

```bash
wt config state marker set "🚧"                   # Current branch
wt config state marker set "✅" --branch feature  # Specific branch
git config worktrunk.state.feature.marker '{"marker":"💬","set_at":0}'  # Direct
```

有关插件安装，请参阅 [Claude Code 集成](https://worktrunk.dev/claude-code/#installation)。

## 跨分支监控 CI

```bash
wt list --full --branches
```

显示所有分支的 PR/CI 状态，包括没有 worktree 的分支。CI 指示符是指向 PR 页面的可点击链接。

## LLM 分支摘要

配置 `summary = true` 和 [`commit.generation`](https://worktrunk.dev/config/#commit) 后，`wt list --full` 会显示每个分支由 LLM 生成的单行摘要。相同摘要也会出现在 `wt switch` 选择器中（第 5 个标签页）。

```toml
# ~/.config/worktrunk/config.toml
[list]
summary = true
```

详情见 [LLM 提交](https://worktrunk.dev/llm-commits/#branch-summaries)。

## JSON API

```bash
wt list --format=json
```

为仪表盘、状态行和脚本提供结构化输出。查询示例见 [`wt list`](https://worktrunk.dev/list/)。

## 复用 `default-branch`

默认分支[检测](https://worktrunk.dev/config/#wt-config-state-default-branch)让脚本可用于任何仓库——无需硬编码 `main` 或 `master`：

```bash
git rebase $(wt config state default-branch)
```

在 hook 和别名中，同一值可通过 `{{ default_branch }}` [模板变量](https://worktrunk.dev/hook/#template-variables)取得；这条命令应留给普通 shell 脚本。

## hook 中的任务运行器

在 hook 中引用 Taskfile/Justfile/Makefile：

```toml
[pre-start]
"setup" = "task install"

[pre-merge]
"validate" = "just test lint"
```

## 渐进式验证

将检查分散到不同 hook 类型——每次提交前快速反馈，合并前执行开销较大的测试套件：

```toml
[[pre-commit]]
lint = "npm run lint"
typecheck = "npm run typecheck"

[[pre-merge]]
test = "npm test"
build = "npm run build"
```

`pre-commit` 在 `wt merge` 期间、squash 提交之前运行；`pre-merge` 在 rebase 之后每次合并运行一次，因此适合放置慢速测试。

## 针对目标的 hook

根据 `{{ target }}` 分支判断，为不同合并目标采用不同行为——例如，从 `main` 部署到生产环境，从发布分支部署到预发布环境：

```toml
post-merge = """
if [ {{ target }} = main ]; then
    npm run deploy:production
elif [ {{ target }} = staging ]; then
    npm run deploy:staging
fi
"""
```

`{{ target }}` 是被合并到的分支。`post-merge` 在目标的 worktree 中运行（如果目标没有 worktree，则在主 worktree 中运行），因此部署命令看到的是合并后的代码。

## 快捷方式

特殊参数适用于所有命令——完整列表见 [`wt switch`](https://worktrunk.dev/switch/#shortcuts)。

```bash
wt switch --create hotfix --base=@       # Branch from current HEAD
wt switch -                              # Switch to previous worktree
wt remove @                              # Remove current worktree
```

## 堆叠分支

从当前 HEAD 而不是默认分支创建分支：

```bash
wt switch --create feature-part2 --base=@
```

## Agent 交接

创建 worktree，并在后台运行一个 agent CLI。以下示例使用 `claude`；对于 OpenCode，请将 `claude` 替换为 `'opencode run'`。

**tmux**（新的分离会话）：
```bash
tmux new-session -d -s fix-auth-bug "wt switch --create fix-auth-bug -x claude -- \
  'The login session expires after 5 minutes. Find the session timeout config and extend it to 24 hours.'"
```

**Zellij**（当前会话中的新窗格）：
```bash
zellij run -- wt switch --create fix-auth-bug -x claude -- \
  'The login session expires after 5 minutes. Find the session timeout config and extend it to 24 hours.'
```

这样，一个 agent 会话就能把工作交给另一个在后台运行的会话。hook 在多路复用器会话/窗格内运行。

[Worktrunk skill](https://worktrunk.dev/claude-code/)包含 Claude Code（以及其他会加载它的 agent CLI）执行此模式的指南。要启用该模式，请明确提出请求（“为……创建并行 worktree”），或将以下内容添加到项目指令（`CLAUDE.md` 或 `AGENTS.md`）：

```markdown
When I ask you to spawn parallel worktrees, use the agent handoff pattern
from the worktrunk skill.
```

## 每个 worktree 一个 tmux 会话

每个 worktree 都有自己的 tmux 会话和多窗格布局。

```toml
# .config/wt.toml
[pre-start]
tmux = """
S={{ branch | sanitize }}
W={{ worktree_path }}
tmux new-session -d -s "$S" -c "$W" -n dev

# Create 4-pane layout: shell | backend / claude | frontend
tmux split-window -h -t "$S:dev" -c "$W"
tmux split-window -v -t "$S:dev.0" -c "$W"
tmux split-window -v -t "$S:dev.2" -c "$W"

# Start services in each pane
tmux send-keys -t "$S:dev.1" 'npm run backend' Enter
tmux send-keys -t "$S:dev.2" 'claude' Enter
tmux send-keys -t "$S:dev.3" 'npm run frontend' Enter

tmux select-pane -t "$S:dev.0"
echo "✓ Session '$S' — attach with: tmux attach -t $S"
"""

[pre-remove]
tmux = "tmux kill-session -t {{ branch | sanitize }} 2>/dev/null || true"
```

创建 worktree 并立即附加到会话：

```bash
$ wt switch --create feature -x tmux -- attach -t '{{ branch | sanitize }}'
```

## 每个 worktree 一个 cmux 工作区

每个 worktree 都有自己的 [cmux](https://cmux.com) 工作区。切换 worktree 会切换工作区；移除 worktree 会关闭其工作区。配置由 [@endigma](https://github.com/endigma) 贡献（[#2796](https://github.com/max-sixty/worktrunk/issues/2796)）。

**前提条件：** [jq](https://jqlang.org)（`brew install jq`）

```toml
# ~/.config/worktrunk/config.toml

# cmux is the navigation primitive; don't also cd the invoking shell.
[switch]
cd = false

[pre-start]
cmux = "cmux new-workspace --name {{ repo | sanitize }}/{{ branch | sanitize }} --cwd {{ worktree_path }} --focus true"

[pre-switch]
cmux = """
WS=$(cmux --json list-workspaces 2>/dev/null \\
  | jq -r --arg t '{{ repo | sanitize }}/{{ branch | sanitize }}' \\
      '.workspaces[] | select(.title == $t) | .ref' | head -1)
[ -n "$WS" ] && cmux select-workspace --workspace "$WS" || true
"""

[pre-remove]
cmux = """
WS=$(cmux --json list-workspaces 2>/dev/null \\
  | jq -r --arg t '{{ repo | sanitize }}/{{ branch | sanitize }}' \\
      '.workspaces[] | select(.title == $t) | .ref' | head -1)
[ -n "$WS" ] && cmux close-workspace --workspace "$WS" || true
"""
```

**为什么使用 `pre-*` 而不是 `post-*`？** cmux 将 socket 访问限制在 cmux 终端内生成的进程。`post-*` hook 作为分离的后台进程运行，会切断进程祖先链。`pre-*` hook 在前台运行，并继承终端的进程谱系。

## 清理 Xcode DerivedData

移除 worktree 时清理 Xcode 的 DerivedData。每个 DerivedData 目录都包含记录其项目路径的 `info.plist`——通过 grep 搜索 worktree 路径，找到并移除匹配的构建缓存：

```toml
# ~/.config/worktrunk/config.toml
[post-remove]
clean-derived = """
  grep -Fl {{ worktree_path }} \
    ~/Library/Developer/Xcode/DerivedData/*/info.plist 2>/dev/null \
  | while read plist; do
      derived_dir=$(dirname "$plist")
      rm -rf "$derived_dir"
      echo "Cleaned DerivedData: $derived_dir"
    done
"""
```

## 使用 Caddy 进行子域名路由
<!-- 2026-03-07 手工测试 -->

使用 `http://feature-auth.myproject.localhost` 这类不含端口号的简洁 URL。适用于 cookie、CORS，以及匹配生产环境的 URL 结构。

**前提条件：** [Caddy](https://caddyserver.com/docs/install)（`brew install caddy`）

```toml
# .config/wt.toml
[post-start]
server = "wt step tether -- npm run dev -- --port {{ branch | hash_port }}"
proxy = """
  curl -sf --max-time 0.5 http://localhost:2019/config/ || caddy start
  curl -sf http://localhost:2019/config/apps/http/servers/wt || \
    curl -sfX PUT http://localhost:2019/config/apps/http/servers/wt -H 'Content-Type: application/json' \
      -d '{"listen":[":8080"],"automatic_https":{"disable":true},"routes":[]}'
  curl -sf -X DELETE http://localhost:2019/id/wt:{{ repo }}:{{ branch | sanitize }} || true
  curl -sfX PUT http://localhost:2019/config/apps/http/servers/wt/routes/0 -H 'Content-Type: application/json' \
    -d '{"@id":"wt:{{ repo }}:{{ branch | sanitize }}","match":[{"host":["{{ branch | sanitize }}.{{ repo }}.localhost"]}],"handle":[{"handler":"reverse_proxy","upstreams":[{"dial":"127.0.0.1:{{ branch | hash_port }}"}]}]}'
"""

[pre-remove]
proxy = "curl -sf -X DELETE http://localhost:2019/id/wt:{{ repo }}:{{ branch | sanitize }} || true"

[list]
url = "http://{{ branch | sanitize }}.{{ repo }}.localhost:8080"
```

**工作原理：**

1. `wt switch --create feature-auth` 运行 `post-start` hook，在确定性端口上启动开发服务器（`{{ branch | hash_port }}` → 16460）
2. hook 在需要时启动 Caddy，并使用同一端口注册路由：`feature-auth.myproject` → `localhost:16460`
3. 操作系统将 `*.localhost` 解析为 `127.0.0.1`
4. 访问 `http://feature-auth.myproject.localhost:8080`：Caddy 匹配子域名并代理到开发服务器

## 监控 hook 日志

跟踪后台 hook 输出：

```bash
tail -f "$(wt config state logs get --hook=user:post-start:server)"
```

`--hook` 格式为 `source:hook-type:name`——例如，项目定义的 hook 使用 `project:post-start:build`。使用 `wt config state logs get` 列出所有可用日志。

为频繁使用创建别名：

```bash
alias wtlog='f() { tail -f "$(wt config state logs get --hook="$1")"; }; f'
```

## 裸仓库布局

[裸仓库](https://git-scm.com/docs/gitrepository-layout)没有工作区，因此所有分支——包括默认分支——都是位于同级路径的[链接 worktree](https://git-scm.com/docs/git-worktree)。没有分支会获得特殊处理。

将裸仓库克隆到 `<project>/.git`，可把所有 worktree 放在同一个目录下：

```bash
git clone --bare <url> myproject/.git
cd myproject
```

使用 `worktree-path = "{{ repo_path }}/../{{ branch | sanitize }}"` 时，worktree 会成为 `myproject/` 的子目录：

```
myproject/
├── .git/       # bare repository
├── main/       # default branch worktree
├── feature/    # feature branch worktree
└── bugfix/     # bugfix branch worktree
```

### 配置 worktree 路径

首次在隐藏路径（`.git`、`.bare`）中的裸仓库运行 `wt switch` 时，Worktrunk 会检测到默认模板将生成 `myproject/.git.main` 这类无效路径，并提出修复建议：

```
▲ Bare repo at myproject/.git — worktrees will be at myproject/.git.main
◎ Configure worktree-path to place worktrees at myproject/main? [y/N/?]
```

接受后会向用户配置写入一个项目作用域的条目：

```toml
# ~/.config/worktrunk/config.toml
[projects."github.com/myorg/myrepo"]
worktree-path = "{{ repo_path }}/../{{ branch | sanitize }}"
```

在任一 worktree 内运行 `wt config show`，可在 PROJECT CONFIG 一节中找到项目标识符（`Identifier: …`）。如果所有裸仓库都偏好此布局，请在顶层设置 `worktree-path = "..."`，使其全局生效。

### 创建第一个 worktree

```bash
wt switch main
```

对于刚克隆的裸仓库，默认分支已存在，因此只需运行 `wt switch main`（不带 `--create`）。新分支则使用 `wt switch --create <branch>`。

此后，`wt switch --create feature` 会创建 `myproject/feature/`。

### 设置项目配置

项目配置（`.config/wt.toml`）必须位于 worktree 内——裸 `.git` 目录中没有被跟踪的文件。第一个 worktree 建好后，从该目录创建配置：

```bash
cd myproject/main
wt config create --project
```

提交该文件后，它会自动出现在每个 worktree 中。
