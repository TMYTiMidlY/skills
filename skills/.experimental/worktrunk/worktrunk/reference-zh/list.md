> 本文是 `reference/list.md` 的中文翻译副本，随上游同步需重译；行为以英文原文为准。

# wt list

列出 worktree 及其状态。

显示未提交的改动、与默认分支和远端的分歧，以及可选的 CI 状态和 LLM 摘要。

表格会渐进式渲染：分支名、路径和提交哈希会立即出现，随后随着后台 git 操作完成，状态、分歧和其他列会陆续填充。

## 完整模式

`--full` 会添加两个需要访问本机之外资源的列：[CI 状态](#ci-status)（通过网络获取 GitHub/GitLab 流水线的通过/失败状态）以及每个分支改动的 [LLM 生成摘要](#llm-summaries)。`main…±` 行差异由本地 git 计算，因此默认显示。

## 示例

列出所有 worktree：

```
$ wt list
  Branch       Status        HEAD±    main↕     main…±  Remote⇅  Commit   Age   Message
@ feature-api  +   ↕⇡     +54   -5   ↑4  ↓1  +234  -24   ⇡3      6814f02  30m   Add API tests
^ main             ^⇅                                    ⇡1  ⇣1  41ee083  4d    Merge fix-auth: h…
+ fix-auth         ↕|                ↑2  ↓1   +25  -11     |     b772e68  5h    Add secure token…
+ fix-typos        _|                                      |     41ee083  4d    Merge fix-auth: h…

○ Showing 4 worktrees, 1 with changes, 2 ahead, 1 column hidden
```

包含 CI 状态和 LLM 摘要：

```
$ wt list --full
  Branch       Status        HEAD±    main↕     main…±  Summary                                                 Remote⇅  CI    Commit
@ feature-api  +   ↕⇡     +54   -5   ↑4  ↓1  +234  -24  Refactor API to REST architecture with middleware        ⇡3      #412  6814f02
^ main             ^⇅                                                                                            ⇡1  ⇣1  #     41ee083
+ fix-auth         ↕|                ↑2  ↓1   +25  -11  Harden auth with constant-time token validation            |     #408  b772e68
+ fix-typos        _|                                                                                              |     #410  41ee083

○ Showing 4 worktrees, 1 with changes, 2 ahead, 3 columns hidden
```

包含没有 worktree 的分支：

```
$ wt list --branches --full
  Branch       Status        HEAD±    main↕     main…±  Summary                                                 Remote⇅  CI    Commit
@ feature-api  +   ↕⇡     +54   -5   ↑4  ↓1  +234  -24  Refactor API to REST architecture with middleware        ⇡3      #412  6814f02
^ main             ^⇅                                                                                            ⇡1  ⇣1  #     41ee083
+ fix-auth         ↕|                ↑2  ↓1   +25  -11  Harden auth with constant-time token validation            |     #408  b772e68
+ fix-typos        _|                                                                                              |     #410  41ee083
/ exp             /↕                 ↑2  ↓1  +137       Explore GraphQL schema and resolvers                                   9637922
/ wip             /↕                 ↑1  ↓1   +33       Start API documentation                                                b40716d

○ Showing 4 worktrees, 2 branches, 1 with changes, 4 ahead, 3 columns hidden
```

以 JSON 输出，供脚本使用：

```bash
$ wt list --format=json
```

## 列

| 列 | 显示内容 |
|--------|-------|
| Branch | 分支名；分离 HEAD 的 worktree 没有分支名，因此以暗黄色显示其短哈希 |
| Status | 紧凑符号（见下文） |
| HEAD± | 未提交的改动：+新增行数 -删除行数 |
| main↕ | 相对默认分支领先/落后的提交数 |
| main…± | 从与默认分支的 merge-base（三点比较）起算的行差异 |
| Summary | LLM 生成的分支摘要；需要 `--full`、`summary = true` 和 [`commit.generation`](https://worktrunk.dev/config/#commit) [实验性] |
| Remote⇅ | 相对跟踪分支领先/落后的提交数 |
| CI | 按流水线状态着色的 PR/MR 编号；仅限 `--full` |
| Path | worktree 目录 |
| URL | 来自项目配置的开发服务器 URL；如果端口未监听则暗显 |
| *(custom)* | 用户配置中 `[list.custom-columns]` 定义的[自定义列](#custom-columns) [实验性] |
| Commit | 短哈希，按 `core.abbrev` 缩写 |
| Age | 距上次提交的时间 |
| Message | 上次提交消息（截断显示） |

无论默认分支的实际名称是什么，表头都使用 `main` 标签。

当默认分支的本地副本落后于其上游时，`main↕` 和 `main…±` 会以默认分支的上游最新提交为基准——因此，在本地 `main` 落后于 `origin/main` 的 fork 中，一个分支显示的是相对真实主线领先，而不是相对陈旧的本地检出领先。Status 中的 `↑`/`↓`/`↕` 符号由这些计数得出，因此同样跟踪上游最新提交。

### 左侧标记

最左列按物理存在程度从高到低标记每一行：

| 符号 | 含义 |
|--------|---------|
| `@` | 当前 worktree |
| `^` | 主 worktree（仓库的主 worktree） |
| `+` | 其他 worktree |
| `/` | 没有 worktree 的本地分支（`--branches`） |
| `\|` | 远端分支，在 fetch 之前本地不存在（`--remotes`） |

### <a id="ci-status"></a>CI 状态

CI 列显示分支的开放 PR/MR——GitHub、Gitea 和 Azure DevOps 上为 `#3035`，GitLab 上为 `!3035`——并按流水线状态着色；没有可用编号时（例如没有 PR/MR 的分支工作流）显示单独的 `#`。一种颜色综合表达两个 JSON 字段：绿色/蓝色/红色/黄色/灰色对应 `ci.status`；品红色/青色对应 `ci.review_state`。`Value` 列是 `--format=json` 中与之匹配的 JSON 字符串：

| 指示符 | 值 | 含义 |
|-----------|-------|---------|
| `#` 绿色 | `"passed"` | 所有检查均已通过 |
| `#` 蓝色 | `"running"` | 检查正在进行 |
| `#` 红色 | `"failed"` | 一个或多个检查失败 |
| `#` 黄色 | `"conflicts"` | 与目标分支存在合并冲突 |
| `#` 灰色 | `"no-ci"` | 没有 PR/MR，或未配置检查 |
| `⚠` 黄色 | `"error"` | 无法获取 CI 状态（速率限制、网络等） |
| `#` 品红色 | `"changes_requested"` | 审查者要求修改 |
| `#` 青色 | `"pending"` | 需要审查（例如由于分支保护），但尚未给出 |
| （空白） | `ci` 不存在 | 没有上游，或者既无 PR/MR 也无分支工作流 |

其余两个 `ci.review_state` 值没有自己的指示符：`"draft"` 只会让单元格暗显，`"approved"` 则不改变颜色。

颜色优先级解决了这种合并表达：要求修改（品红色）的优先级高于正在运行的检查——等待检查完成不能清除它——而尚未完成的必需审查（青色）只会给原本为绿色或无状态的分支重新着色。冷色表示等待，暖色表示需要行动。已批准的 PR，或完全没有审查信号（没有必需审查者且没有审查）的 PR，会保留普通的 `ci.status` 颜色——此时 `ci.review_state` 分别为 `"approved"` 或不存在。GitLab MR 数据只包含 `"pending"` 和 `"draft"`——没有已批准或要求修改信号。

CI 单元格是指向 PR 或流水线页面的可点击链接；对于草稿 PR/MR（`"draft"`），或者未推送的本地改动使状态过期（`ci.stale`）时，单元格会暗显。系统会先检查 PR/MR，然后对有上游的分支检查分支工作流/流水线。仅本地分支显示为空；仅远端分支——通过 `--remotes` 可见——也会检测 CI 状态。结果缓存 30-60 秒；使用 `wt config state` 查看或清除。

### <a id="llm-summaries"></a>LLM 摘要 [实验性]

复用 [`commit.generation`](https://worktrunk.dev/config/#commit) 命令——也就是生成提交消息的同一个 LLM。在 `[list]` 配置中设置 `summary = true` 启用；需要 `--full`。结果会缓存，直到分支的 diff 发生变化。

### <a id="custom-columns"></a>自定义列 [实验性]

用户配置中的每个 `[list.custom-columns]` 条目都会添加一列：键是表头，模板渲染每一行的单元格。模板读取两个按分支划分的命名空间——通过 [`wt config state vars set`](https://worktrunk.dev/config/#wt-config-state-vars) 存储的 `{{ vars.* }}`，以及分支自身位于 `branch.<name>.*` 下的 git 配置 `{{ git.branch.* }}`（可以自行设置的 `jira` 键，或 git 原生的 `description`）——适合跟踪众多分支（通常由 agent 驱动）各自的用途：

```toml
[list.custom-columns.Ticket]
template = "{{ vars.ticket }}"
```

如果某一列在每一行都渲染为空，该列会从表格中移除。模板、宽度和移除优先级见：[自定义列配置](https://worktrunk.dev/config/#custom-columns)。

## 状态符号

Status 列从左到右压缩了多个子列，每个子列都映射到 `--format=json` 中的一个字段。工作区标志彼此独立且可以同时出现——任意组合都会一起显示。其他子列则互斥：每列只显示一个符号，即下表从上到下优先级最高的状态；没有适用状态时为空。

### <a id="working-tree"></a>工作区

来自 `git status` 的独立标志；多个标志可以同时显示（例如 `+!?`）。每个标志都映射到 `working_tree` 对象中的一个布尔值：

| 符号 | working_tree | 含义 |
|--------|--------------|---------|
| `+` | `staged` | 已暂存的文件 |
| `!` | `modified` | 已修改的文件（未暂存） |
| `?` | `untracked` | 未跟踪的文件 |

`working_tree` 还会报告 `renamed` 和 `deleted`，它们在该列中没有专用符号。

### Worktree

正在进行的 git 操作、worktree 位置属性，或没有 worktree 的分支。只显示一个符号，优先级从高到低为（`✘ > ↻ > ⊟ > ⊞ > ⚑ > /`）：

| 符号 | JSON | 含义 |
|--------|------|---------|
| `✘` | `operation_state` `"conflicts"` | 合并冲突 |
| `↻` | `operation_state` `"rebase"`, `"merge"`, `"cherry_pick"`, `"revert"`, `"bisect"` | 正在进行 git 操作；其名称由 `git status` 给出 |
| `⊟` | `worktree.state` `"prunable"` | 可清理（worktree 目录缺失） |
| `⊞` | `worktree.state` `"locked"` | 已锁定的 worktree |
| `⚑` | `worktree.state` `"duplicate_branch"` | 同一分支在多个 worktree 中检出，因此 `wt` 会解析为 git 最先列出的那个；该分支上的每个 worktree 都会被标记 |
| `⚑` | `worktree.state` `"branch_worktree_mismatch"` | worktree 不在其分支所隐含的路径上——包括分离 HEAD 的 worktree，因为它没有分支可用于推断路径，所以永远不在其归属位置 |
| `/` | `kind` `"branch"` | 没有 worktree 的分支（无 `worktree` 对象） |

### <a id="default-branch"></a>默认分支

描述该分支与默认分支关系的单个最高优先级状态；没有适用状态时（普通且最新的分支）为空。每个符号对应一个 `main_state` 值：

| 符号 | main_state | 含义 |
|--------|------------|---------|
| `^` | `"is_main"` | 主 worktree（仓库的主 worktree） |
| `∅` | `"orphan"` | 与默认分支没有共同祖先 |
| `_` | `"empty"` | 与默认分支位于同一提交，工作区干净——可安全移除；整行暗显 |
| `⊂` | `"integrated"` | 内容已通过不同历史[集成](https://worktrunk.dev/remove/#branch-cleanup)到默认分支或合并目标；匹配到的检查记录在 `integration_reason` 中；整行暗显 |
| `✗` | `"would_conflict"` | 合并到默认分支会发生冲突（用 `git merge-tree` 模拟），且该分支尚未集成；使用 `--full` 时，检查包括未提交的改动 |
| `–` | `"same_commit"` | 与默认分支位于同一提交，但存在未提交的改动 |
| `↕` | `"diverged"` | 相对默认分支既领先又落后 |
| `↑` | `"ahead"` | 含有默认分支没有的提交 |
| `↓` | `"behind"` | 缺少默认分支已有的提交 |

可[安全删除](https://worktrunk.dev/remove/#branch-cleanup)的行会暗显——即 `_`（`"empty"`）或 `⊂`（`"integrated"`）。

### <a id="remote"></a>远端

与跟踪分支的关系，由 `remote.ahead` / `remote.behind` 计数得出；没有上游时为空：

| 符号 | remote | 含义 |
|--------|--------|---------|
| `\|` | `ahead` 0, `behind` 0 | 与远端同步 |
| `⇡` | `ahead` > 0 | 领先远端 |
| `⇣` | `behind` > 0 | 落后远端 |
| `⇅` | `ahead` > 0, `behind` > 0 | 与远端发生分歧 |

### 占位符号

表格加载时，这些符号会出现在所有列中：

| 符号 | 含义 |
|--------|---------|
| `·` | 数据正在加载，或收集超时/分支过于陈旧 |

---

## JSON 输出

在格式迁移期间，`--format=json` 会按两种 schema 之一发出结构化数据：
`[list] json-schema = 2` 选择下述信封格式，`= 1`
选择原始的裸数组格式。未设置时会发出 schema 1 并显示警告
（`wt config update` 会采用 `= 2`）；未来版本会把默认值切换到
schema 2，并在之后移除 schema 1。

### Schema 2

一个信封对象。各条目携带彼此独立的事实；渲染后的字符串
（包括折叠后的 Status 值）位于 `display` 下：

```json
{
  "schema": 2,
  "repo": {
    "default_branch": "main",
    "forge": {"url": "https://github.com/org/repo", "provider": "github",
              "host": "github.com", "owner": "org", "name": "repo", "remote": "origin"}
  },
  "collected": {"ci": false, "summary": false},
  "items": [
    {
      "branch": "feature",
      "head": {"sha": "05a4a45d…", "short_sha": "05a4a45", "subject": "Add login page",
               "committed_at": "2025-01-01T08:00:00Z"},
      "worktree": {"path": "/home/user/repo.feature", "main": false, "current": true,
                   "previous": false, "detached": false, "branch_mismatch": false,
                   "duplicate_branch": false,
                   "changes": {"staged": false, "modified": true, "untracked": false,
                               "renamed": false, "deleted": false, "conflicted": false,
                               "diff": {"added": 10, "deleted": 2}}},
      "default_branch": {"ahead": 3, "behind": 1, "diff": {"added": 50, "deleted": 20},
                         "orphan": false, "integration": null, "merge_conflicts": false},
      "upstream": {"remote": "origin", "branch": "feature", "ahead": 0, "behind": 2},
      "display": {"state": "diverged", "symbols": "!↕", "statusline": "feature …"}
    }
  ]
}
```

“无值”有以下几种表现：

- **不存在**——没有可报告内容：不适用（仅分支行中的 `worktree`）、
  本次运行未请求（信封的 `collected` 会记录请求了哪些内容），
  或已确定为空（没有 PR、没有锁、未集成）。
- **`null`**——已请求但未能确定：任务超时、分支
  过于陈旧而无法执行昂贵的检查，或从 forge 获取失败。这是
  表格中 `·` 占位符的 JSON 形式。

jq 在路径表达式中以相同方式处理不存在和 `null`，因此过滤器
无需检查 null；需要区分两者时可使用 `has()`。

条目字段：

| 字段 | 说明 |
|-------|-------------|
| `branch` | 分支名；对于分离 HEAD 的 worktree 为 null。远端行携带不含远端名的分支名，远端名位于 `remote` 中 |
| `remote` | 远端名称，仅存在于纯远端分支行 |
| `head` | `{sha, short_sha, subject, committed_at}`；未诞生的分支为 null。`committed_at` 是 RFC 3339 UTC |
| `worktree` | `{path, main, current, previous, detached, locked, prunable, branch_mismatch, duplicate_branch, operation, changes}`；仅分支行中不存在。`locked`/`prunable` 是 `{reason}` 对象，且可以同时存在；`operation` 为 `"rebase"` 或 `"merge"`；`changes` 包含五个工作区标志以及 `conflicted` 和 `diff {added, deleted}` |
| `default_branch` | 与默认分支的关系：`{ahead, behind, diff, orphan, integration, merge_conflicts}`；默认分支自身没有此字段。`integration.reason` 是 `same_commit`、`ancestor`、`no_added_changes`、`trees_match`、`merge_adds_nothing`、`patch_id_match` 之一；有未提交改动的工作区会跳过这些检查，使 `integration` 保持 null |
| `upstream` | 跟踪分支：`{remote, branch, ahead, behind}`；未配置时不存在 |
| `pr` | 开放的 PR/MR：`{number, url, review, mergeable, repo}`；使用 `--full` 或列出的 `ci` 列时收集。`review` 使用 schema 1 的 `ci.review_state` 词汇；当 forge 报告冲突时 `mergeable` 为 false，否则为 null |
| `checks` | CI 流水线：`{status, source, stale}`；`status` 为 `passed`、`running` 或 `failed`——当冲突报告将其遮蔽时为 null |
| `dev_server` | 来自项目 `list.url` 模板的 `{url, listening}` |
| `summary` | LLM 分支摘要（需要 `[list] summary = true`） |
| `vars` | 来自 [`wt config state vars`](https://worktrunk.dev/config/#wt-config-state-vars) 的按分支变量 |
| `display` | 渲染后的字符串：`state`（schema 1 的 `main_state` 词汇）、`symbols`、`statusline`（带 ANSI 颜色和 OSC 8 超链接）、`columns`（以表头为键的自定义列单元格） |

Schema 1 名称直接映射如下：`commit` → `head`，`working_tree` →
`worktree.changes`，`main` + `main_state` → `default_branch` +
`display.state`，`remote` → `upstream`，`ci` → `pr` + `checks`，`url` +
`url_active` → `dev_server`，`statusline`/`symbols`/`columns` → `display.*`，
每个条目中的 `repo` 则移至信封的 `repo.forge`。

```bash
# Current worktree path (for scripts)
$ wt list --format=json | jq -r '.items[] | select(.worktree.current) | .worktree.path'

# Branches with uncommitted changes
$ wt list --format=json | jq '.items[] | select(.worktree.changes.modified)'

# Integrated branches (safe to remove)
$ wt list --format=json | jq '.items[] | select(.display.state == "integrated" or .display.state == "empty") | .branch'

# Worktrees ahead of upstream (needs pushing)
$ wt list --format=json | jq '.items[] | select(.upstream.ahead > 0) | .branch'
```

### Schema 1

原始的裸数组格式，也是未设置时的默认格式：

```bash
# Current worktree path (for scripts)
$ wt list --format=json | jq -r '.[] | select(.is_current) | .path'

# Branches with uncommitted changes
$ wt list --format=json | jq '.[] | select(.working_tree.modified)'

# Worktrees with merge conflicts
$ wt list --format=json | jq '.[] | select(.operation_state == "conflicts")'

# Branches ahead of main (needs merging)
$ wt list --format=json | jq '.[] | select(.main.ahead > 0) | .branch'

# Integrated branches (safe to remove)
$ wt list --format=json | jq '.[] | select(.main_state == "integrated" or .main_state == "empty") | .branch'

# Branches without worktrees
$ wt list --format=json --branches | jq '.[] | select(.kind == "branch") | .branch'

# Worktrees ahead of remote (needs pushing)
$ wt list --format=json | jq '.[] | select(.remote.ahead > 0) | {branch, ahead: .remote.ahead}'

# Stale CI (local changes not reflected in CI)
$ wt list --format=json --full | jq '.[] | select(.ci.stale) | .branch'
```

**字段：**

| 字段 | 类型 | 说明 |
|-------|------|-------------|
| `branch` | string/null | 分支名（分离 HEAD 时为 null） |
| `path` | string | worktree 路径（没有 worktree 的分支中不存在） |
| `kind` | string | `"worktree"` 或 `"branch"` |
| `commit` | object | 提交信息（见下文） |
| `working_tree` | object | 工作区状态（见下文） |
| `main_state` | string | 与默认分支的关系（见下文） |
| `integration_reason` | string | 分支为何已集成（见下文） |
| `operation_state` | string | `"conflicts"`、`"rebase"` 或 `"merge"`（见 [Worktree](#worktree)）；干净时不存在 |
| `main` | object | 与默认分支的关系（见下文）；is_main 时不存在 |
| `remote` | object | 跟踪分支信息（见下文）；没有跟踪时不存在 |
| `worktree` | object | worktree 元数据（见下文） |
| `is_main` | boolean | 是否为主 worktree |
| `is_current` | boolean | 是否为当前 worktree |
| `is_previous` | boolean | 是否为 wt switch 的上一个 worktree |
| `ci` | object | CI 状态（见下文）；仅限 `--full`，此时没有 PR/MR 或分支工作流时不存在 |
| `repo_url` | string | 从主要远端推导出的仓库 Web URL；无法解析远端 URL 时不存在 |
| `repo` | object | 结构化仓库元数据（见下文）；包含 `remote` |
| `url` | string | 来自项目配置的开发服务器 URL；未配置时不存在 |
| `url_active` | boolean | URL 的端口是否正在监听；未配置时不存在 |
| `summary` | string | LLM 生成的分支摘要；仅限 `--full`，此时未配置或没有摘要时不存在 |
| `statusline` | string | 带颜色和链接的预格式化状态 |
| `symbols` | string | 不带颜色的原始状态符号（例如 `"!?↓"`） |
| `vars` | object | 来自 [`wt config state vars`](https://worktrunk.dev/config/#wt-config-state-vars) 的按分支变量（为空时不存在） |
| `columns` | object | 以表头为键的已渲染[自定义列](#custom-columns)值；空单元格省略（未配置时不存在） |

### 提交对象

| 字段 | 类型 | 说明 |
|-------|------|-------------|
| `sha` | string | 完整提交 SHA（40 个字符） |
| `short_sha` | string | 短提交 SHA，按 `core.abbrev` 缩写（当前缀有歧义时自动延长） |
| `message` | string | 提交消息（第一行） |
| `timestamp` | number | Unix 时间戳 |

### working_tree 对象

五个改动标志映射到[工作区](#working-tree)符号（`renamed` 和 `deleted` 没有自己的符号）：

| 字段 | 类型 | 说明 |
|-------|------|-------------|
| `staged` | boolean | 是否存在已暂存文件 |
| `modified` | boolean | 是否存在已修改文件（未暂存） |
| `untracked` | boolean | 是否存在未跟踪文件 |
| `renamed` | boolean | 是否存在已重命名文件 |
| `deleted` | boolean | 是否存在已删除文件 |
| `diff` | object | 相对 HEAD 的改动行数：`{added, deleted}` |

### main 对象

| 字段 | 类型 | 说明 |
|-------|------|-------------|
| `ahead` | number | 领先默认分支的提交数 |
| `behind` | number | 落后默认分支的提交数 |
| `diff` | object | 相对默认分支的改动行数：`{added, deleted}` |

### remote 对象

`ahead` / `behind` 决定[远端](#remote)分歧符号：

| 字段 | 类型 | 说明 |
|-------|------|-------------|
| `name` | string | 远端名称（例如 `"origin"`） |
| `branch` | string | 远端分支名 |
| `ahead` | number | 领先远端的提交数 |
| `behind` | number | 落后远端的提交数 |

### worktree 对象

仅存在于 worktree 类型的条目中。`state` 是 worktree 位置属性——其符号见 [Worktree](#worktree)：

| 字段 | 类型 | 说明 |
|-------|------|-------------|
| `state` | string | `"branch_worktree_mismatch"`、`"duplicate_branch"`、`"prunable"` 或 `"locked"`（正常时不存在） |
| `reason` | string | 锁定/可清理状态的原因 |
| `detached` | boolean | HEAD 是否分离 |

### ci 对象

| 字段 | 类型 | 说明 |
|-------|------|-------------|
| `status` | string | CI 状态（见下文） |
| `source` | string | `"pr"`（PR/MR）或 `"branch"`（分支工作流） |
| `number` | integer | PR/MR 编号；分支工作流中不存在 |
| `stale` | boolean | 本地 HEAD 是否与远端不同（有未推送的改动） |
| `url` | string | PR/MR 页面的 URL |
| `repo_url` | string | PR/MR 所针对仓库的 Web URL（对于 fork PR 即上游）；`url` 不存在或无法识别时不存在 |
| `repo` | object | PR/MR 所针对仓库的结构化元数据；绝不包含 `remote` |
| `review_state` | string | 审查状态（见下文）；forge 未报告审查信号时不存在 |

### 仓库对象

顶层 `repo` 描述从主要远端推导出的本地检出仓库。`ci.repo` 描述 `ci.url` 中 PR/MR URL 所针对的仓库（对于 fork PR，这是上游目标）。现有的 `repo_url` 和 `ci.repo_url` 字段仍然可用，并与 `repo.url` / `ci.repo.url` 携带相同 URL。

| 字段 | 类型 | 说明 |
|-------|------|-------------|
| `url` | string | 仓库 Web URL |
| `provider` | string | `"github"`、`"gitlab"`、`"gitea"`、`"azure-devops"` 或 `"unknown"` |
| `host` | string | 仓库 Web 主机 |
| `owner` | string | 所有者、组织或命名空间路径 |
| `name` | string | 仓库名称 |
| `project` | string | Azure DevOps 项目名称；其他提供商中不存在 |
| `remote` | string | 用于顶层仓库元数据的本地远端名称；`ci.repo` 中不存在 |

### main_state 值

描述分支与默认分支关系的单个最高优先级状态；没有适用状态时（普通且最新的分支）不存在。每个值对应一个默认分支符号——各值（`"is_main"`、`"orphan"`、`"empty"`、`"integrated"`、`"would_conflict"`、`"same_commit"`、`"diverged"`、`"ahead"`、`"behind"`）的符号与完整含义见[默认分支](#default-branch)。

### integration_reason 值

仅当 `main_state == "integrated"`（`⊂` 符号）时设置，记录匹配到了哪项检查。检查按开销从低到高运行，首个匹配项胜出。仅在 JSON 中提供——所有原因都渲染为相同的 `⊂`：

| 值 | 含义 |
|-------|---------|
| `"ancestor"` | 分支 HEAD 是默认分支的祖先，默认分支已向前推进 |
| `"no-added-changes"` | 三点 diff（`main...branch`）为空——相对 merge-base 没有文件改动 |
| `"trees-match"` | 历史不同，但分支的树与默认分支完全相同 |
| `"merge-adds-nothing"` | 分支有改动，但合并后默认分支的树保持不变（例如 squash 合并后目标分支又在其他文件上向前推进） |
| `"patch-id-match"` | 分支 squash 后的 diff 与默认分支上的单个提交匹配（例如 GitHub/GitLab squash 合并） |

### ci.status 和 ci.review_state 值

上面的 [CI 状态](#ci-status)一节是这两个字段的唯一来源：表格映射了每个着色值，其后的说明涵盖 `"draft"` 和 `"approved"`。`ci.status` 是 `"passed"`、`"running"`、`"failed"`、`"conflicts"`、`"no-ci"`、`"error"` 之一；`ci.review_state` 是 `"changes_requested"`、`"pending"`、`"draft"`、`"approved"` 之一，forge 未报告审查信号时不存在。该词汇与 Claude Code 状态行的 `pr.review_state` 字段一致。

缺少某个普遍有用的字段？请在 https://github.com/max-sixty/worktrunk 提交 issue。

## 命令参考

```
wt list - List worktrees and their status

Usage: wt list [OPTIONS]
       wt list <COMMAND>

Commands:
  statusline  Single-line status for the current worktree

Options:
      --format <FORMAT>
          Output format

          [default: table]
          [possible values: table, json]

      --branches
          Include branches without worktrees

      --remotes
          Include remote branches

      --full
          Show CI status and LLM summaries

      --progressive
          Show fast info immediately, update with slow info

          Displays local data (branches, paths, status) first, then updates with remote data (CI,
          upstream) as it arrives. Use --no-progressive to force buffered rendering. Auto-enabled
          for TTY.

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

## wt list statusline

当前 worktree 的单行状态。

该行包含与此 worktree 在 `wt list` 中对应行相同的单元格。CI 状态缓存过期时，它会访问网络一两秒，因此更适合宿主在后台渲染的状态行——Claude Code 状态行或 `tmux` 状态栏——而不是会阻塞 shell 的提示词。希望它快到足以用于同步提示词？请在 https://github.com/max-sixty/worktrunk 提交 issue。

### 输出格式

- `table`（默认）：`branch  status  HEAD±  main↕  main…±  Remote⇅  CI  URL`
- `json`：`wt list --format=json` schema 中的单条目数组
- `claude-code`：`table` 单元格，前接 `dir`，后接 `model  context  pace`

没有内容可显示的单元格会被省略，而不是留空，因此多数行会比上述格式更短；如果 `dir` 已以 `.<branch>` 结尾，`claude-code` 还会移除 `branch`。如果一行仍然超过终端宽度，就会从最不重要的单元格开始整格移除，首先移除开发服务器 URL。

CI 标记链接到对应的 PR/MR；带端口的开发服务器 URL 显示为 `:3000` 并链接到完整 URL，在该端口有响应之前暗显。两者都带下划线，以此表示可点击。它们是 OSC 8 链接；不支持该功能的终端会丢弃转义序列，只留下带下划线但不可点击的文本。

### Claude Code 模式

`--format=claude-code` 从 stdin 读取 JSON 上下文（`.workspace.current_dir` 为必需项；其余均可选）：

- `.workspace.current_dir`——工作目录
- `.model.display_name`——模型名称
- `.context_window.used_percentage`——上下文使用量（0–100），渲染为 `🌔 65%`；随着上下文填满，月相从 🌕→🌑 逐渐亏缺
- `.rate_limits.{five_hour,seven_day}.used_percentage`——速率限制窗口使用量（0–100）
- `.rate_limits.{five_hour,seven_day}.resets_at`——窗口重置时间（Unix epoch 秒）

pace 段只会在用量很可能于窗口重置前触及速率限制时出现，并显示风险较高的窗口：`2.9×(Tue–Tue 5pm)` 表示当前 pace 是恰好会用满该窗口之 pace 的 2.9 倍。使用量超过 90% 后，它显示使用量而不是 pace——`93%(Tue–Tue 5pm)`——因为接近上限时，剩余多少比消耗速度更重要。“很可能”来自贝叶斯预测；窗口早期的突发使用不会触发它。随着预测受限时长（窗口中预计会有多少时间因达到上限而不可用）增加，其颜色会逐步加深——暗色、暗黄色、黄色——因此，即使 pace 很快，只要预计到接近重置时才会略微超限，就仍保持暗色而不会报警。使用 `-vv` 时，每个窗口的输入与预测都会记录到 `.git/wt/logs/trace.log`。

[Claude Code 状态行设置](https://worktrunk.dev/claude-code/#statusline-claude-code-only)包含向此模式提供输入的 `~/.claude/settings.json` 条目。

### 命令参考

```
wt list statusline - Single-line status for the current worktree

Usage: wt list statusline [OPTIONS]

Options:
      --format <FORMAT>
          Output format

          Possible values:
          - table
          - json
          - claude-code: Claude Code statusline mode (reads context from stdin)

          [default: table]

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
