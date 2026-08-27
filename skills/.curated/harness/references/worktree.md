# Worktree 支持横向对照：三家宿主原生能力与第三方 CLI

多 agent 并行开发时常见诉求是"每个 agent 一个隔离 git worktree"。这份笔记核实三家 coding agent 宿主**原生**对 worktree 的支持程度——哪家有专门工具、哪家只是"感知"、哪家完全没有；原生能力不够时的外部补充（跨宿主 skill、[第三方 CLI](#third-party-cli)）另起一节。全部标注一手来源，不转述未核实的说法。

## 结论先行

| 宿主 | 原生 worktree 工具 | worktree 感知（能判断自己在不在 worktree 里）| 并行 agent 隔离方式 | 开源程度 / 验证方式 |
|---|---|---|---|---|
| **Claude Code** | ✅ `--worktree`/`-w` flag + `EnterWorktree` 工具 + `WorktreeCreate`/`WorktreeRemove` hook | ✅ | subagent `isolation: worktree`、`/batch` 每单元一 worktree、桌面 App 每会话自动建 | 闭源，官方文档逐字核实（2026-07 直接 fetch） |
| **Codex** | ❌ 无 | ✅ 有（文件系统探查，不调用 git 命令）| `multi_agents`/`multi_agents_v2` **共享 cwd**，靠进程/上下文隔离而非目录隔离 | 真开源（Apache-2.0），直接读源码核实，见下方 file:line |
| **Copilot CLI**（本 CLI）| ❌ 无 | 未见专门检测逻辑 | `/fleet`、subagent，共享工作区 | 闭源，官方 `/help` 命令清单核实 |

下面按宿主展开。

---

## Claude Code

来源：官方文档 `code.claude.com/docs/en/worktrees.md`、`/sub-agents.md`、`/commands.md`、`/agent-view.md`——**均为 2026-07 直接 `web_fetch` 抓取原文核实，非转述二手信息**。

### 核心机制

```bash
claude --worktree feature-auth   # 建 worktree 并进入；省略名字则自动生成如 "bright-running-fox"
claude --worktree "#1234"        # 从指定 GitHub PR 建 worktree（fetch pull/<n>/head）
```

- worktree 默认建在 `.claude/worktrees/<value>/`，新分支名为 `worktree-<value>`。
- 基准分支默认 `origin/HEAD`（无 remote 或 fetch 失败则回退本地 `HEAD`）；把 `worktree.baseRef` 设成 `"head"`（settings.json）可强制从本地 HEAD 分支——这样新 worktree 会带上尚未 push 的 commit，适合让 subagent 接着干一份进行中的工作。该设置只接受 `"fresh"` 或 `"head"`，不能填任意 git ref。
- `.worktreeinclude`（`.gitignore` 语法）把项目根目录下**同时满足"匹配该文件"且"被 gitignore"**的文件（如 `.env`、`config/secrets.json`）自动复制进每个新 worktree；已被 git 追踪的文件不会被重复复制。这个机制对 `--worktree`、subagent worktree、桌面 App 并行会话都生效。
- 首次在某目录用 `--worktree` 前，得先跑一次 `claude` 通过 workspace trust 弹窗，否则 `--worktree` 会报错并提示先建立信任；非交互模式 `claude -p --worktree` 跳过这个检查。
- v2.1.200 起：从主 checkout 装的 project-scope 插件，在同仓库的 worktree 里自动可用，不用逐个 worktree 重装——无论 worktree 是 `--worktree` 建的还是手动 `git worktree add` 建的。

### `EnterWorktree` 是真实存在的工具

> **更正**：此前判断这是 skill 文档里的"示意性命名"、无法确认是否真实存在。现已用官方文档逐字核实为真。

官方文档原文：

> "You can also ask Claude to 'work in a worktree' during a session, and it will create one with the `EnterWorktree` tool."

即：会话里让 Claude "work in a worktree"，它会调用一个名叫 `EnterWorktree` 的内部工具来创建；也可以用同一个工具切换到 `.claude/worktrees/` 下另一个已存在的 worktree（原 worktree 保留在磁盘上不动）。v2.1.198 起，进出 worktree 还会把会话记录一并搬到对应目录的 project storage（跟 `/cd` 命令行为一致），所以之后 `/desktop`、`--resume` 能在新位置找到会话——但通过 `WorktreeCreate` hook 建的 worktree 不在此列，会话记录仍留在启动目录。

### subagent 隔离：`isolation: worktree`

在自定义 subagent 的 YAML frontmatter 里加一行 `isolation: worktree`，该 subagent 每次运行都会拿到一个临时 worktree（跟 `--worktree` 用同一套基准分支规则），跑完如果没有产生改动会自动删除。也可以直接在会话里说"use worktrees for your agents"临时启用，不用改配置。

### `/batch`：bundled skill，不是纯 CLI 命令

官方文档 `/commands.md` 原文：

> "For a large change that spans the codebase, `/batch` decomposes it into independent units and runs each in its own worktree."

即：跨越整个代码库的大改动，`/batch` 会拆解成若干独立单元，每个单元在自己的 worktree 里跑。这是一个 **bundled skill**（官方文档明确区分 Skill 与内建 Workflow 两类命令），不是写死在二进制里的行为——机制上和用户自己写的 skill 是一回事，只是官方预置。

### 非 git VCS：`WorktreeCreate` / `WorktreeRemove` hook

给 SVN、Perforce、Mercurial 等非 git 版本控制用。这对 hook **完全接管默认的 git worktree 逻辑**，此时 `.worktreeinclude` 不再生效（复制配置文件的逻辑要自己写进 hook 脚本）。官方文档给的示例：`WorktreeCreate` hook 从 stdin 读 worktree 名字、跑 `svn checkout`、把目录路径打印到 stdout 供 Claude Code 用作会话工作目录。

### 清理机制

- agent 运行期间，Claude Code 会对它的 worktree 跑 `git worktree lock`，防止并发的自动清扫把正在用的 worktree 删掉；agent 结束后释放锁。
- 退出一个 worktree 会话时：**无未提交改动/未追踪文件/无新 commit** → 自动删除 worktree 和分支（若会话有名字则改为询问，方便你留着以后用）；**有改动** → 询问保留还是删除。
- **非交互运行**（`-p` + `--worktree`）没有退出时的询问环节，worktree 不会自动清理，得手动 `git worktree remove`。
- 给 subagent/后台会话建的 worktree，超过 settings 里 `cleanupPeriodDays` 设置的天数、且无未提交改动/未追踪文件/未 push commit，会被自动清理扫掉；但**用户自己用 `--worktree` 建的 worktree 不受这个自动清扫影响**。

### 桌面 App

官方文档确认："The desktop app creates a worktree for every new session automatically"——桌面 App 里每个新的并行会话自动建一个 worktree，不用手动传参。

---

## Codex（openai/codex，真开源）

来源：官方仓库 [`openai/codex` @ `bdd282f3bb`](https://github.com/openai/codex/tree/bdd282f3bb)（2026-06-27，`codex-zsh-v0.1.0-55-gbdd282f3bb`）。**直接读源码核实，非转述**。

### 没有创建/进入 worktree 的工具

`codex-rs/core/src/tools/handlers/` 目录下的完整内置工具清单：`shell`/`unified_exec`（跑命令）、`apply_patch`（改文件）、`plan`、`multi_agents` + `multi_agents_v2`（并行子 agent）、`mcp`/`mcp_resource`、`view_image`、`request_user_input`、`request_permissions`、`agent_jobs`、`current_time`、`sleep`、`tool_search`——**没有任何创建或进入 worktree 的工具**。在 `cli`/`exec`/`tui`/`core/src/config` 里搜索（排除测试文件）也找不到面向用户的 `--worktree` flag 或等价配置项。

### 但对 worktree "有感知"

- `codex-rs/git-utils/src/info.rs:808` 注释：

  > "Handles worktrees via filesystem inspection without invoking [git]"

  即：不调用 git 命令，靠探查文件系统判断自己是不是在一个 linked worktree（`git worktree add` 建出的、checkout 在主仓库之外的那种）里。
- 同文件 `:836-841`：向上找 `.git/worktrees/` 目录的父目录来定位 common dir（common dir = 所有 worktree 共享的那个真正的 `.git`）。这跟 obra/superpowers 的 `using-git-worktrees` skill 里 `GIT_DIR != GIT_COMMON` 的判断原理完全一致（见下节），说明"探查文件系统结构判断是否在 worktree 里"是个跨项目的通用套路，不是巧合。
- `codex-rs/core/src/config/mod.rs:1049` 注释：确认 Codex 会判定当前 cwd 是 "(1) part of a git repo, (2) a git worktree, or (3) just using the cwd"——用于计算仓库根路径、baseline diff 等场景。

### 并行 agent：共享 cwd，非目录隔离

`codex-rs/core/src/tools/handlers/multi_agents.rs:5` 注释：spawn 出的子 agent 会继承 provider、approval policy、sandbox 和 **cwd**——即多个子 agent **共享同一个工作目录**，靠上下文/进程隔离而非文件系统隔离。`multi_agents_v2/` 目录（`spawn.rs`/`wait.rs`/`send_message.rs`/`interrupt_agent.rs`/`list_agents.rs`/`followup_task.rs`）是 actor 式消息编排，管的是"跟哪个子 agent 对话、等它、打断它"，不涉及给它分配独立目录。

**含义**：想让多个 Codex 实例各自在独立 worktree 里并行工作，Codex 自己给不了这个能力，得靠外部编排——自己写脚本先 `git worktree add` 再各起一个 `codex` 进程，或者用[第三方 CLI](#third-party-cli) 在顶层管理。

---

## Copilot CLI（本 CLI）

来源：官方 `/help` 命令清单（`fetch_copilot_cli_documentation` 工具返回，2026-07 核实）。

`/help` 输出里没有任何 worktree 相关命令或 flag。相邻的"并行"能力都不做 git worktree 隔离：

| 命令 | 做什么 | 是否 worktree 隔离 |
|---|---|---|
| `/fleet` | 开 fleet 模式并行跑多个 subagent | ❌ 共享工作区 |
| `/delegate` | 把整个会话推到 GitHub 云端，由 Copilot 建 PR | ❌ 云端隔离，非本地 worktree |
| `/tasks`、`ctrl+x→b` | 管理后台 subagent/shell 任务 | ❌ |

要开 worktree，只能走通用 `bash` 工具跑 `git worktree add`，或者装一个项目级 skill 把这套流程固化下来（如本环境里 `git` skill 的隔离工作区章节：自动为隔离分支创建 git worktree、含 submodule 同步）——**这类 skill 底层调用的仍是 `git worktree add`，不是什么 CLI 原生能力**，本质和让我自己敲命令没有区别，只是把步骤和边界条件写成了可复用的固定流程。

---

## 跨宿主兜底模式：obra/superpowers 的 `using-git-worktrees` skill

来源：GitHub 仓库 [obra/superpowers](https://github.com/obra/superpowers)（实时 API 核实：**249,629 ★**，22,149 fork，MIT license，创建于 2025-10-09，最近 push 2026-07-06）；`skills/using-git-worktrees/SKILL.md`（SHA `212c569`，直接读取原文核实）。

这个 skill 设计成"先探测、再找原生工具、最后 git 回退"的三段式，原因正是要跨 Claude Code / Codex / Copilot CLI 等多个宿主——而后两者根本没有原生 worktree 工具：

1. **Step 0 探测已有隔离**：判断 `GIT_DIR != GIT_COMMON`（即是否已在一个 linked worktree 里），并显式排除 submodule 干扰（submodule 也满足这个条件，需要用 `git rev-parse --show-superproject-working-tree` 排除掉，否则会误判）。与 Codex `git-utils/info.rs` 的探查原理相同。
2. **Step 1a 优先用原生工具**：如果宿主提供类似 `EnterWorktree`/`WorktreeCreate`/`--worktree` 的机制就用它，skill 原文把"有原生工具却还去手动 `git worktree add`"列为**头号错误**（会产生宿主看不见、管理不了的"幽灵状态"）——**这一步在 Claude Code 上成立**，因为 `EnterWorktree` 真实存在。
3. **Step 1b git 回退**：没有原生工具时才手动 `git worktree add`，并强制在建之前用 `git check-ignore` 确认目标目录已被 gitignore——**这一步在 Codex 和 Copilot CLI 上都会被触发**，因为两者在 Step 1a 都没有可用的原生工具。

<a id="third-party-cli"></a>

## 第三方 worktree CLI 与 agent 编排器

宿主原生能力不够时的外部补充。**分类依据是"谁拥有 agent 的生命周期"，不是谁功能多**：

- **worktree 的 UX 层**：只管建 / 切 / 删 / 合并 worktree 本身，不持有"哪个 agent 在跑"的状态。传个"建完顺手起某条命令"的参数不等于会话被追踪——换 agent、或压根不跑 agent 只手改代码，对它都一样。
- **agent 编排器**：自己起 tmux 会话、拉起 agent 进程、维护"谁在跑 / 谁在等输入"的 TUI 面板；worktree 只是它隔离每个 agent 的副产物。

| 仓库 | ★ | 语言 / 许可 | 类别 |
|---|---|---|---|
| [`max-sixty/worktrunk`](https://github.com/max-sixty/worktrunk) | 6.2K | Rust，MIT OR Apache-2.0 | worktree UX 层，**首选** |
| [`smtg-ai/claude-squad`](https://github.com/smtg-ai/claude-squad) | 8.2K | Go，AGPL-3.0 | agent 编排器（tmux + worktree + TUI） |
| [`raine/workmux`](https://github.com/raine/workmux) | 2.0K | Rust，MIT | worktree + tmux window |

★ / 许可 / 活跃度为 2026-08-01 GitHub API 读数，三者均在近两天有 push。worktrunk 的 SPDX 被 GitHub 判为 `NOASSERTION`，实际 `LICENSE` 首行写明双许可。

两层不互斥，可以叠着用。反直觉的一点：**编排器在合并上反而更原始**——claude-squad 是手动 push 分支再走 `gh` 建 PR（README 级说法，2026-07 调研，未读源码核实），而"只管 worktree"的 worktrunk 反倒把 squash → rebase → 合并 → 删 worktree 做成了一条命令。优化目标不同，不存在哪层在每个维度都更完备。

### worktrunk

以下核实自本地 clone 的 `v0.71.0`（commit `bfbc2e2`，2026-08-01），非 README 转述。

- **比原生 `git worktree` 多出来、且没法用小脚本轻易复刻的只有一条：建完自动 `cd`。** 外部子进程天然改不了父 shell 的 cwd，所以必须装 shell 集成——往 rc 文件写一行惰性 `eval "$(wt config shell init <shell>)"`，把 `wt` 重定义成"二进制退出后读临时文件里的目标路径、再 `builtin cd`"的 shell 函数。其余（删 worktree 顺带删分支、post-create hook 装依赖 / 复制 `.env`、带 ahead/behind 的状态表、合并后原子清理）自己攒一套脚本也能凑出来，它的价值是坑别人踩过并维护着，不是原理上的黑科技。
- **命令面很小**：`switch` / `list` / `remove` / `merge` / `step` / `hook` / `config`。
- **不绑任何 LLM 厂商、不需要 API key**：`[commit.generation]` 只是把拼好的 prompt 管道传给你配的任意外部命令（`claude -p`、`codex exec`、`llm`、`aichat` 等），读其 stdout 当 commit message。**不配就静默兜底**——普通 commit 用 `WIP: Changes` / `Changes to <文件>`（`src/llm.rs:809-816`），squash 用 `Squash commits from <分支>` + 原 commit 标题列表（`src/llm.rs:939`），只往 stderr 打一行提示，不报错、不阻塞。只有"配了、但那条外部命令执行失败"才报错。
- **`wt merge` 没有 `-m`/`--message`**（`src/cli/mod.rs:531-570` 只有目标分支 + `--[no-]squash` / `--[no-]commit` / `--[no-]rebase` / `--[no-]remove` / `--no-ff`）。要自己写消息是**绕开**而非传参：先 `git commit -m …`（或本来就是 agent 提的）再 `wt merge --no-commit`；或 `--no-squash` 保留原有多条 commit。**没有任何自动解冲突能力**，冲突就是普通 git rebase 冲突，仍需人或 agent 介入。
- **仓库自带 agent 侧接入**：`skills/`（`worktrunk`、`wt-switch-create` 两个 Agent Skill）、`plugins/`（Claude / Codex / OpenCode）、`hooks/hooks.json`、`gemini-extension.json`——"给 agent 用"是它的一等公民场景，而不是事后适配。

安装渠道取舍：官方列表里 Homebrew 与 Cargo 是一等公民，conda-forge / Pixi 那条标注为社区维护 feedstock。GitHub Release 页上的 `curl | sh` 是 cargo-dist 生成的脚本（自带各平台 sha256 校验），但它默认装进 `$CARGO_HOME/bin` 并挨个尝试改 `.profile` / `.bashrc` / `.bash_profile` / `.zshrc` / fish `conf.d` 等 6-7 个 rc 文件，侵入性明显大于走包管理器 + 单独一步 shell 集成。

## 小结对照表

| 能力 | Claude Code | Codex | Copilot CLI |
|---|---|---|---|
| 一条命令/flag 建 worktree 并进入 | ✅ `--worktree` | ❌ 手动 `git worktree add` | ❌ 手动 `git worktree add` |
| agent 自己能调用工具建/切 worktree | ✅ `EnterWorktree` | ❌ | ❌ |
| subagent 自动隔离到独立 worktree | ✅ `isolation: worktree` | ❌（共享 cwd） | ❌ |
| 大改动自动拆分、每单元独立 worktree | ✅ `/batch` | ❌ | ❌ |
| 非 git VCS 的 worktree 逻辑可替换 | ✅ `WorktreeCreate`/`WorktreeRemove` hook | ❌ | ❌ |
| 自己能判断"我在不在 worktree 里" | ✅ | ✅（文件系统探查，不调用 git）| 未见专门逻辑 |
| 开源程度 | 闭源 | 真开源（Apache-2.0）| 闭源 |

**跨宿主统一方案**：装 obra/superpowers（或照抄它 Step 0/1a/1b 的思路自写一个项目级 skill），在 Claude Code 上吃到 `EnterWorktree` 原生加速和自动清理，在 Codex/Copilot CLI 上自动回退到手动 `git worktree add` + `git check-ignore` 校验，行为在三个宿主上保持一致，不用为每个宿主单独维护一套逻辑。若追求更强的"多 agent 编排"（而非单纯"开一个 worktree"），[第三方 CLI](#third-party-cli) 在这三个宿主之上再加一层进程 / tmux 编排，弥补的正是 Codex/Copilot CLI 缺失的"原生并行+隔离"能力；只想把开 worktree 这件事本身变顺手，则用 worktrunk 那类纯 UX 层即可。
