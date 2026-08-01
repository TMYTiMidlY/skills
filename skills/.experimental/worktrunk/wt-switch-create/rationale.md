# wt-switch-create 设计依据

本文说明该 skill 的创建并进入流程，以及支撑这套流程、经过验证的宿主运行
框架（harness）行为。流程由错误驱动；预判式前置检查和额外处理路径都试过，
随后删掉了。

本文每项说法都已对照一手来源验证（2026-06-11 至 2026-06-17）：Claude Code
2.1.173，其中路径进入和工作目录逻辑又通过实时测试及 2.1.177 二进制文件
重新确认，另参考 code.claude.com/docs 的官方文档；以及 wt
v0.57.0-16-g371d28662（在临时仓库中实时运行）。进入流程——确认提示、
`EnterWorktree` 的两条路径，以及各自在退出后留下什么——又于 2026-07-28
针对 Claude Code 2.1.220 和 wt v0.69.2 做了实时复测。依赖某项具体行为前，
请用当前版本重新验证；论证的*框架*应比细节更耐久。本文有意省略二进制
符号名——每次构建重新压缩时，这些名称都会变化。

## 设计

1. 对本仓库中的新分支使用 `EnterWorktree({name})`。它通过 Worktrunk 的
   `WorktreeCreate` hook（`wt switch --create`）创建，因此结果是普通的 `wt`
   worktree；调用不传 `path`，正因如此不会触发 M2 的确认提示。分支已存在、
   会话已经进入某个 worktree 时都会失败，而且无法指定目标仓库。
2. 其他情况先在 Bash 中运行
   `wt -C <repo> switch --create <branch> --no-cd --format=json`，再调用
   `EnterWorktree({path})`。`wt` 负责指定仓库（`-C` 可从任意位置使用）、
   处理现有分支（去掉 `--create` 后重试）和输出机器可读结果（stdout 中的
   `.path`，stderr 中的状态）。在另一个仓库中创建没有问题，受限制的只有
   *进入*结果。如果用户拒绝进入，流程到此结束，worktree 留下但未进入（M2）。
3. 发生工具错误（或拒绝背后没有可询问的用户）时，只要路径位于会话获准
   访问的目录内（即某个 `additionalDirectories` 条目），会话仍能在那里
   工作。一次 `cd <path>` 就能判断：可达时目录切换会保持，不可达时会重置。
   可达 → 原地工作。不可达 → 交由用户处理，因为 agent 无法自行扩大该集合：
   请用户把仓库或其父目录（例如 `~/workspace`）加入
   `additionalDirectories`，或运行 `/add-dir <path>`。这是一行配置、设置
   一次即可长期生效的交还，而不是静默降级。

这背后有两项相互独立的宿主运行框架事实——重定根受仓库范围约束，`cd` 是否
持久则取决于路径是否属于工作目录集合——下文会详细说明。

## 为什么无条件创建

反复出现的失败是：收到调研或只读任务后，模型判断不需要隔离，于是跳过
创建。两种措辞助长了这种判断。范围章节中的“授权”容易被理解为许可，
引出“该不该做”的判断（如果用户级规则要求必须有明确请求才能创建
worktree，答案就会是“不该”）；只强调顺序的开头（“先执行第 1–3 步”）
也约束不了已经认定这些步骤不适用的模型。因此，开头把调用本身定义为明确
请求，而范围章节只陈述边界，不再授予权限。不要重新引入这两种措辞。

## wt CLI 与 git 行为（均经实时测试）

- 只要分支已存在，无论是否已有 worktree，
  `wt switch --create <branch>` 都会以状态码 1 退出，并显示
  `✗ Branch <branch> already exists`。它自己的提示给出了修复方法：去掉
  `--create` 后重试。
- 对现有分支运行 `wt switch <branch>`（不带 `--create`）会以状态码 0
  退出：缺少 worktree 时创建一个
  （`"action":"created","created_branch":false`），否则重新进入现有
  worktree（`"action":"existing"`）。`wt switch --help` 原文为：
  "Without --create, the branch must already exist."
- 每种 `--format=json` 变体都包含 `path`（绝对路径）。只有 JSON 写入
  stdout；所有供人阅读的状态信息（包括 hook 输出）都写入 stderr——因此
  可以安全提取 `.path`。
- `wt remove`：worktree 有未提交改动 → 拒绝（状态码 1，提示 `--force`）；
  worktree 干净但有未合并提交 → 删除 worktree、保留分支，并提示
  `wt remove -D`；干净且已合并 → 同时删除 worktree 和分支。
- git stash 按仓库存储，在各 worktree 之间共享：在一个 worktree 中运行
  `git stash push -u`，可以在另一个 worktree 中通过
  `git -C <path> stash pop` 干净地弹出，其中也包括未跟踪文件——这就是
  skill 创建步骤在会话中途迁移改动的依据。

## Claude Code 行为

会话可以在 cwd 所在的位置工作。两种机制都能移动会话，而且会*组合生效*：
`cd` 移动 cwd（也就改变 `EnterWorktree` 看到的仓库）；`EnterWorktree`
则在 cwd 所属仓库内重定根。以上行为均通过实时测试和 2.1.177 二进制文件
验证。

### M1——`cd`（shell cwd）

移动 shell 的 cwd；状态栏和工具路径的相对解析（`Write(foo/bar.py)`）
会随之变化。

- **关卡：**路径必须位于已配置的工作目录内——即会话的基础 cwd，加上
  `permissions.additionalDirectories`（settings.json）、启动参数
  `--add-dir` 或会话中途执行的 `/add-dir` 中的每个条目。
- 位于集合内 → `cd` 可跨 Bash 调用保持。位于集合外 → 宿主运行框架会将其弹回，
  并在结果末尾附加 `Shell cwd was reset to <original>`。
- **不识别仓库：**它只检查路径位置是否属于该集合，从不检查路径归哪个 git
  仓库所有。配置了 `/tmp` 后，位于 `/tmp` 下、属于另一个仓库的 worktree
  也可达。
- 在*单次* Bash 调用内，`cd X && cmd` 始终有效；重置只发生在两次调用
  *之间*。（子 agent 线程会在每次调用之间重置。）

### M2——`EnterWorktree({path})`（重定根）

执行正式的重定根：设置会话的 worktree 主目录（供退出时追踪）和 cwd。

- **关卡：**目标必须是**当前 cwd 所解析到的仓库**的 worktree，具体规则取决于
  会话状态：
  - **普通会话 / 首次进入** → 磁盘上任意*已注册到该仓库*的 worktree
    （`git worktree list`）；在多仓库工作区中，也可以是注册到其内部嵌套
    仓库的 worktree。
  - **已经处于 worktree 会话中，或属于固定的 agent** → 只能进入该仓库的
    `.claude/worktrees/`；同仓库的兄弟 worktree 也会被拒绝。
  - **cwd 不在任何 git 仓库内** → 完全拒绝。
- **确认提示：**安全检查依据调用携带的两个事实——传入了 `path` 参数，且目标
  位于项目的 `.claude/worktrees/` 外——并在其他任何操作运行前询问。对话框
  文字为 "permission-root relocation to `<path>` — a model-supplied
  worktree outside .claude/worktrees/"。只能选 yes/no：没有“始终允许”，选择
  yes 后不会持久保存任何设置，而针对 `EnterWorktree` 的
  `permissions.allow` 条目（裸名称、`(*)` 或路径 glob）也无法消除提示。
  只要会话能弹出提示（`default`、`acceptEdits`、`auto`），就会询问；
  `bypassPermissions` 会直接允许而不询问，无法弹出提示的会话则会直接拒绝。
  `EnterWorktree({name})` 不传 `path`，因此永远不会询问。
- **判读失败：**第 3 步按结构区分工具错误和调用拒绝，而不是解析拒绝措辞。
  工具自身的拒绝信息保持原样且属于可控失败（`Cannot enter …`），因此可据此
  触发恢复；调用被拒绝时，默认视为用户的回答，只有拒绝信息明确表示会话
  无法弹出提示时，才作为“没有用户可询问”的例外。这个默认值偏向安全一侧，
  因为拒绝文本无法可靠分类：用户手动输入“no”后，收到的是通用信息
  `The user doesn't want to proceed with this tool use`，既不指明工具，也不
  指明确认提示。盲测中，任何要求 agent 识别这种拒绝的措辞——按拒绝者身份
  划分分支、声称“拒绝信息表明了一项决定”，甚至把该字符串原样列为示例——
  都会让 agent 走恢复路径，进入用户刚刚拒绝的 worktree。在拒绝之后安排
  恢复会诱发这种路由，因此拒绝分支以停止为首要动作。能走到第 3 步的决定
  只有这个回答——如果为 `EnterWorktree` 设置了 `permissions.deny` 条目，
  无论是否带参数模式，该工具都会直接从会话中移除，根本不会发生可供拒绝的
  调用。
- 拒绝属于可控失败且没有副作用（不会创建任何内容）。该 skill 自身流程会
  原样产生以下三种拒绝（此外还有其他情况——worktree 被另一个运行中的会话
  锁定、目标是主 worktree、注册项可清理）：
  - 注册检查：`Cannot enter worktree: <path> is not a registered
    worktree of <repo>. Run 'git -C <repo> worktree list' …`
  - 托管位置：`Cannot enter worktree: <path> is not under
    <repo>/.claude/worktrees. Switching from this session is limited to
    worktrees managed by Claude Code …`
  - 无仓库：`Cannot enter an existing worktree: the current directory is not in
    a git repository.`

仓库从 cwd 读取，因此 `EnterWorktree` 自身绝不会把会话移到另一个仓库——
它只会在当前所在仓库内重定根。要重定根到*另一个*仓库，先 `cd` 进入该
仓库，再调用 `EnterWorktree`。验证结果：从一个 Worktrunk 会话出发，先
`cd` 进入 `/tmp` 下的 prql worktree，再调用 `EnterWorktree`，即可在 prql
内部重定根。

### 如何组合

能否在某个仓库中工作或重定根，最终取决于 cwd 能否位于其中，也就是能否
通过 `cd` 的关卡：

| 目标 | cwd 是否可达？ | 结果 |
|---|---|---|
| 同一仓库（包括其兄弟 worktree） | 始终可达 | `EnterWorktree` 直接重定根 |
| 已配置目录（`~/workspace`、`/tmp`）下的另一个仓库 | 是 | `cd` 进入 → 在其中工作；普通会话还可用 `EnterWorktree` 在其中重定根 |
| 位于所有已配置目录之外的另一个仓库 | 否 | 不可达——将其（或父目录）加入 `additionalDirectories`，或运行 `/add-dir` |
| 不属于任何仓库的位置 | 不适用 | 无法重定根 |

`additionalDirectories` 是唯一的总关卡：只要某个仓库或 `~/workspace` 这样的
父目录位于其中，会话就能 `cd` 进入该仓库的 worktree，在其中工作并重定根。
这对同仓库路径同样关键：兄弟 worktree 已注册到该仓库，因此普通会话中的
`EnterWorktree` 可以重定根到 `wt` 创建的兄弟 worktree。agent **无法**自行
扩大这个集合（`/add-dir` 必须由用户输入；唯一的自动加入只是一个范围很窄的
修正，用于解析指向同一 cwd 的符号链接），因此，如果 cwd 和配置都无法触达
某个仓库，就确实必须交还给用户处理。

### 为什么使用 `--no-cd`

Bash 工具不是裸 shell：Claude Code 会根据快照重放用户的 shell 启动过程，
因此，安装过 wt shell 集成的用户会在工具内运行 `wt` 包装函数。此时 wt 在
集成已启用的环境中运行，普通的 `wt switch` 会向包装函数交付一条 cd 指令，
移动工具的 cwd——这相当于第二次、不受追踪的重定根，与 `EnterWorktree`
竞争。`--no-cd` 会跳过这条指令，让 `EnterWorktree` 保持为唯一的重定根。
验证结果：不带 `--no-cd` 时，`wt switch <branch>` 会移动会话，新 cwd 还会
保持到下一次 Bash 调用。用户从未安装集成时（全新 shell、CI），包装函数
不存在，wt 无论如何都不能执行 cd；因此 `--no-cd` 在已集成的机器上不可少，
在其他环境中则不产生作用。不要删除它。

### `EnterWorktree({name})` 的代价与适用边界

`name` 路径值得保留，因为它能完全跳过 M2 的确认提示，而任何配置都无法让
按路径进入做到这一点。`isolation: "worktree"` agent 也由同一个插件 hook
支持，因此它生成的 worktree 仍然是 `wt` 本来就会创建的那个。使用这条路径
会带来以下三个特性，均经实时验证：

1. **未触碰的 worktree 会在退出时连同分支一起清理。** 如果没有改动文件、
   没有提交，而且用户没有设置会话标题，退出中的会话会通过插件的
   `WorktreeRemove` hook 删除它；该 hook 运行 `wt remove`，因此干净且完全
   合并的分支也会一并删除。端到端验证：
   `EnterWorktree({name: "probe"})` 后执行 `/exit`，`repo.probe` 和 `probe`
   分支都不会留下；只需一个未跟踪文件，退出时就会报告
   "Keeping worktree…" 并同时保留二者。在这个使用场景中，这是优点——没有
   写入任何内容的调研任务不会留下待清理对象——也是第 2 步没有把 worktree
   描述为持久对象的原因。按路径进入的 worktree 始终会留在原处
   （"worktree at <path> left in place"）。
2. **遇到现有分支时直接失败。** hook 会运行 `wt switch --create`，而 hook
   以非零状态退出会让创建立即失败，不会回退到 git（二进制文件：
   "Other exit codes - worktree creation failed"；文档："the hook
   replaces the default git behavior"）。失败过程很干净：只会显示 `wt`
   自己的 `✗ Branch <branch> already exists`，不会创建任何内容。
3. **只适用于会话的首次进入，而且只能在会话自己的仓库中使用。** 已经位于
   worktree 中的会话会收到 "Already in a worktree session. Pass `path` to
   switch into another existing worktree"，并且这条路径不支持 `-C`。

每种失败都会指出后续路径，因此第 3 步不需要预检查：先尝试成本较低的调用，
读取错误，再回退。hook 契约（stdout 最后一个非空行必须是现有目录）仍由
hook 自身负责，因为该 skill 只读取工具结果。

### 为什么交由用户处理，而不是靠绝对路径硬撑

最初的问题发生在一个重定根到别处的会话中：它通过绝对路径完成跨仓库任务。
每次 `cd` 进入 worktree 都会重置，因此每条命令都要加绝对路径前缀，会话也
始终没有获得该 worktree 的 cwd。输出虽然正确，整个过程看起来却像失败。
文件工具（绝对路径）和 `git -C` 不依赖 cwd，因此这种方式*能够*完成工作——
但既然一行配置就能修复，不应让用户承受这份额外摩擦。

因此，worktree 不可达时，该 skill 会带着具体修复方法交由用户处理，而不是
静默降级。这不是预判式前置检查：skill 不会拒绝跨仓库创建，也不会猜测路径
是否可达。它先创建、尝试进入，再让一次 `cd` 显示可达性——只有实际发生
重置时才会上交。尝试成本很低，而交还方案既可执行又持久（只需设置一次
`~/workspace` 条目，就能覆盖今后的每个跨仓库任务）。

## hooks.json 的 pipefail 包装（agent 隔离路径，不属于此 skill）

`WorktreeCreate` 使用管道 `jq | xargs wt | jq`；如果没有 `pipefail`，末尾的
`jq` 会在输入为空时以状态码 0 退出，吞掉 `wt` 的失败，因此 Claude Code
看到的是一个没有路径却“成功”的 hook。hook 命令以空参数数组和
`shell: true`（二进制文件）启动，也就是 Unix 上的 `/bin/sh -c`——macOS
使用 bash 3.2，许多 Linux 则使用 dash。dash 会把 `set -o pipefail` 当作
致命错误（`set` 是 POSIX 特殊内建命令；截至 0.5.12 的 dash 发行版都不支持
pipefail——只有 0.5.12 之后的上游 git 代码和 Debian 0.5.12-7 之类的发行版
回移补丁支持）。而且 `/bin/sh -c` 显然并不普遍：一位用户的 hook 在 fish
下运行（Worktrunk PR #2962），fish 完全没有 shell 选项。因此需要显式使用
`bash -c 'set -o pipefail; …'` 包装。端到端验证结果：成功时打印路径并以
状态码 0 退出；现有分支导致的失败以状态码 1 退出，stdout 为空。

## 已知限制（有意保留）

- 另一个仓库只能通过 `additionalDirectories` 到达（见上文“如何组合”）；
  位于该范围外时，skill 会要求用户添加一行配置，而不会降级成绝对路径模式。
- 固定的 agent 或已经进入 worktree 的会话，连*同仓库*的兄弟 worktree 都
  无法重新进入（因为 `.claude/worktrees/` 检查更严格）；它会走同一套可达性
  测试和同一条上交路径。
- 在任何能够弹出提示的会话中，落到第 3 步的调用仍会逐次请求用户确认
  （M2）：另一个仓库、现有分支、同一会话中的第二个 worktree。skill 能触及
  的范围内没有办法消除这一点——该检查会忽略 `permissions.allow`；把项目的
  `worktree-path` 指向 `.claude/worktrees/` 虽能满足检查，却必须放弃
  Worktrunk 的默认布局，并让 `wt` 与 Claude Code 共用一个目录，而这种组合
  尚未运行验证。要消除提示，只能由上游改为每个仓库询问一次，而不是每次
  调用都询问。
- `wt switch --create` 不具备幂等性。如果上游将来改成“存在即进入”，第 3 步
  针对现有分支的重试就会化为无操作，hook 也不再因现有分支而失败，从而消除
  第 3 步存在的两个原因之一。
