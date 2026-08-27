---
name: worktrunk
description: Worktrunk（`wt` CLI）使用指南，涵盖 git worktree 管理、hook 与配置。编辑 .config/wt.toml 或 ~/.config/worktrunk/config.toml，新增、修改或调试 hook（post-merge、post-start、pre-commit、pre-merge、post-switch 等），配置提交信息生成或命令别名，或排查 wt 行为时加载。也用于回答一般的 Worktrunk/wt 问题。
license: MIT OR Apache-2.0
compatibility: Requires the `wt` CLI (https://worktrunk.dev)
---

# Worktrunk

帮助用户用 Worktrunk 这个 CLI 工具管理 git worktree。

## 可用文档

参考文件与 [worktrunk.dev](https://worktrunk.dev) 文档保持同步：

- **reference-zh/config.md**：用户配置与项目配置（LLM、hook、命令默认值）
- **reference-zh/hook.md**：hook 类型、运行时机与执行顺序
- **reference-zh/switch.md**、**merge.md**、**list.md** 等：命令文档
- **reference-zh/extending.md**：别名、多步流水线、自定义子命令，以及模板展开的易错点（两阶段 `{% raw %}` 延迟展开、for-each 用法）
- **reference-zh/llm-commits.md**：用 LLM 生成提交信息
- **reference-zh/tips-patterns.md**：实用方案——别名、按分支变量、每个 worktree 的开发服务器、并行 agent 模式
- **reference-zh/shell-integration.md**：shell 集成排障
- **reference-zh/troubleshooting.md**：LLM 与 hook 排障（Claude 专用）

命令专属选项请运行 `wt <command> --help`；配置则按下述流程处理。

## 两类配置

Worktrunk 使用两份作用域和权限模型不同的配置文件：

**用户配置**（`~/.config/worktrunk/config.toml`，不纳入 git）存放个人偏好：LLM 集成、worktree 路径模板、命令设置、用户 hook。修改时要谨慎——先提出方案并征得同意后再编辑，不要代用户安装工具，并保留文件现有的结构和注释。参见 `reference-zh/config.md`。

**项目配置**（`<repo>/.config/wt.toml`，纳入 git）存放团队共用的自动化设置：覆盖 worktree 生命周期的 hook（pre-start、pre-merge 等）。可以主动编辑——改动由 git 记录版本，也能撤销。为每个 hook 注明存在原因；加入破坏性命令（`rm -rf`、`DROP TABLE`）、通过管道交给 shell 的网络下载命令或 `sudo` 前，先提醒用户。参见 `reference-zh/hook.md`。

有些请求会同时涉及二者：提交信息生成属于用户配置，团队质量检查则属于项目配置。

## 核心流程

### 配置提交信息生成（用户配置）

先检测已安装的工具（`which claude codex llm aichat`）；如果都没有，推荐 Claude Code。从 `reference-zh/llm-commits.md` 取得所选工具的准确命令，提出 `[commit.generation]` 修改方案，获批后再应用（若配置不存在，先运行 `wt config create`）。验证时，`wt step commit --dry-run` 会渲染提示词、运行 LLM，并打印提交信息而不创建提交。

### 配置项目 hook

根据命令的运行时机及是否可以阻断流程选择 hook 类型（共 10 种：5 个事件 × pre/post——完整说明见 `reference-zh/hook.md`）：

- 后续步骤需要的依赖和环境文件 → `pre-start`（阻断创建）
- 开发服务器、耗时构建、复制缓存 → `post-start`（后台运行）
- 格式化工具、linter、类型检查 → `pre-commit`
- 合并前必须通过的测试 → `pre-merge`
- 触发 CI、发送通知 → `post-commit`
- 部署 → `post-merge`
- 解析分支前的准备 / 更新终端与 IDE → `pre-switch` / `post-switch`
- 删除前后的清理（保存产物；停止服务器、删除容器）→ `pre-remove` / `post-remove`

命令应从项目本身推导（`package.json` scripts、`Cargo.toml`、`pyproject.toml`），加入前先验证能够运行。

当新 hook 必须等待现有 hook 时，把条目改成流水线；同一个具名表中的独立命令会并发运行：

```toml
# 流水线：install 完成后再启动 migrate
[[pre-start]]
install = "npm install"

[[pre-start]]
migrate = "npm run db:migrate"

# 并发：同一个表中的独立命令
[pre-start]
install = "npm install"
env = "cp .env.example .env"
```

使用 `wt switch --create test-hooks` 测试。

## 常见任务索引

### 用户配置任务
- 配置提交信息生成 → `reference-zh/llm-commits.md`
- 自定义 worktree 路径 → `reference-zh/config.md#worktree-path-template`
- 自定义提交模板 → `reference-zh/llm-commits.md#prompt-templates`
- 配置命令默认值 → `reference-zh/config.md#command-config`
- 设置个人 hook → `reference-zh/config.md#hooks`

### 项目配置任务
- 为新项目设置 hook → `reference-zh/hook.md`
- 向现有配置添加 hook → `reference-zh/hook.md#hook-forms`
- 使用模板变量 → `reference-zh/hook.md#template-variables`
- 向列表添加开发服务器 URL → `reference-zh/config.md#dev-server-url`

### 别名与多 worktree 任务
- 创建 `wt` 别名 → `reference-zh/extending.md#aliases`
- 在每个 worktree 中运行命令 → `reference-zh/step.md#wt-step-for-each`
- 按 up 风格对每个 worktree 执行 rebase → `reference-zh/extending.md#recipe-rebase-every-worktree-onto-its-upstream`
- 让嵌套的 `wt` 命令延迟展开模板变量 → `reference-zh/extending.md#deferring-expansion-to-a-nested-wt-command`

## 关键命令

```bash
# 查看全部配置
wt config show

# 创建初始用户配置（LLM/提交设置：见 reference-zh/llm-commits.md）
wt config create

# 完整配置参考（子命令、模板、环境变量）
wt config --help
```

## 非交互式会话中的 hook 审批

在用户明确批准前，Worktrunk 绝不会运行项目的 hook 或别名。`.config/wt.toml` 中的命令是随仓库分发的任意 shell 代码，而用户可能刚刚克隆这个仓库；因此首次运行时，Worktrunk 会展示每条命令并等待用户批准——不受信任的 `.config/wt.toml` 无法静默执行任何内容。审批按项目存储在 `~/.config/worktrunk/approvals.toml` 中；命令模板每次变化都会再次请求批准，因此不能在 hook 获批后悄悄换成另一条命令。

agent 运行 `wt merge`、`wt switch` 或其他会触发 hook 的命令时，会遇到类似错误：

```
▲ cargo-difftest needs approval to execute 1 command:
○ post-merge install:
  cargo install --path .
✗ Cannot prompt for approval in non-interactive environment
↳ To skip prompts in CI/CD, add --yes; to pre-approve commands, run wt config approvals add
```

解决办法是让用户亲自作出信任决定：

- **`wt config approvals add`**——通过交互式提示让用户逐条审阅命令，再将审批存入 `~/.config/worktrunk/approvals.toml`。每个项目运行一次；只要命令模板没有变化、项目没有移动，审批就会在后续调用中保持有效。应推荐这条路径——用户能准确审阅并同意将要运行的命令。

**作为 agent 执行时，应停下并交由用户处理。** 批准项目 hook 是一项安全决策：是否信任这个仓库在用户机器上运行任意命令。这个决定应由用户而非 agent 作出。告诉用户运行 `wt config approvals add` 并自行审阅命令。不要代用户运行 `--yes`：它会跳过本次调用的审批关卡，用它来解除命令阻塞等于绕过这项保护。`--yes` 用于已经自行控制 hook 内容的 CI/CD 流水线，不是交互式 agent 消除审批提示的捷径。

## 高级用法：agent 交接

当用户要求在后台会话中启动带 agent 的 worktree（“为……启动一个 worktree”“交接给另一个 agent”）时，按其终端复用器选择相应模式。将 `<agent-cli>` 替换为当前运行的 CLI：Claude Code 用 `claude`，OpenCode 用 `'opencode run'`。

**tmux**（检查 `$TMUX` 环境变量）：
```bash
tmux new-session -d -s <branch-name> "wt switch --create <branch-name> -x <agent-cli> -- '<task description>'"
```

**Zellij**（检查 `$ZELLIJ` 环境变量）：
```bash
zellij run -- wt switch --create <branch-name> -x <agent-cli> -- '<task description>'
```

**前提**（必须全部满足）：
- 用户明确要求启动/交接
- 用户正在使用受支持的终端复用器（tmux 或 Zellij）
- 用户的项目指令（`CLAUDE.md` 或 `AGENTS.md`）或明确的提示词授权使用此模式

普通 worktree 操作**不要使用此模式**。

示例（tmux、Claude Code）：
```bash
tmux new-session -d -s fix-auth-bug "wt switch --create fix-auth-bug -x claude -- \
  'The login session expires after 5 minutes. Find the session timeout config and extend it to 24 hours.'"
```

示例（Zellij、OpenCode）：
```bash
zellij run -- wt switch --create fix-auth-bug -x 'opencode run' -- \
  'The login session expires after 5 minutes. Find the session timeout config and extend it to 24 hours.'
```

### 并行子 agent（单个 Claude Code 会话）

要从一个 Claude Code 会话启动多个各自在独立 worktree 中工作的子 agent——无需终端复用器，也无需人在另一个窗格中操作——先由父会话预先创建每个 worktree，再把路径写入子 agent 的提示词：

```bash
wt switch --create <branch> --no-cd --no-hooks
```

然后调用 `Agent` 工具，**不要**设置 `isolation: "worktree"`，并在提示词中写明路径：

```
You are working in `/abs/path/to/worktrunk.<branch>` on branch `<branch>`.
All edits must stay in that worktree.
```

`--no-cd` 会跳过父会话无法消费的 shell 集成 cd 脚本；如果每个子 agent 都会自行运行构建/测试步骤（例如 `cargo run -- hook pre-merge --yes`），而且无需为每个 worktree 重复 post-start 设置，则适合使用 `--no-hooks`。

此处**不要**使用 `Agent { isolation: "worktree" }`。Claude Code 会把内部 agent ID 作为 `name` 传给 `WorktreeCreate` hook，因此 `wt` 会在一个临时分支上创建名为 `worktrunk.agent-<id>` 的 worktree。如果子 agent 随后又从其上创建功能分支，就会产生非规范路径、孤儿分支，并让 post-start hook 针对错误的分支触发。预先使用 `wt switch --create` 创建，能让路径、分支和 hook 目标保持一致。
