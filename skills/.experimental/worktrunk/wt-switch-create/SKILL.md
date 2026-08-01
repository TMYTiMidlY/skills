---
name: wt-switch-create
description: 创建新的 Worktrunk worktree（可选在另一个仓库中创建），并将本会话的工作目录切入其中。启动应在独立 worktree 中工作的会话时使用。
argument-hint: "[<branch>] [<repo>] [-- <task>]"
license: MIT OR Apache-2.0
compatibility: Requires the `wt` CLI (https://worktrunk.dev)
---

参数：`$ARGUMENTS`。语法：`[<branch>] [<repo>] [-- <task>]`。

- **branch**——可选；新 worktree 的分支名。省略时，选择一个名称
  （见下文第 1 步）。
- **repo**——可选路径；在此仓库而非会话当前仓库中创建 worktree。
- **task**——可选；进入新 worktree 后要做的事。没有任务时，进入
  worktree 并等待。

`--` 之前的 token 表示分支和/或仓库：形似路径的 token（以 `/`、`~`、
`./` 或 `../` 开头）是仓库；其他 token 都是分支（`docs` 是分支名，
绝不是 `docs/` 目录）。`--` 前出现多个形似分支的 token 不符合语法——
应询问用户。没有 `--` 时，判断任务从哪里开始：开头看起来像分支名
（`fix-auth`）或仓库路径的 token 会被解析为相应参数，剩余内容是任务；
否则整段输入都是任务（`fix the parser bug` 开头没有形似分支的内容——
全部都是任务）。

```
/wt-switch-create my-feature -- fix the parser bug
/wt-switch-create -- fix the parser bug
/wt-switch-create my-feature ~/workspace/other-repo -- fix the parser bug
/wt-switch-create my-feature
```

## 操作流程

每次调用都必须先创建 worktree，再做任何其他工作。调用本身就是创建
worktree 的明确请求；即使任务只是调研或只读，也照样创建。

<!-- 维护者：同目录的 rationale.md 说明了这套流程背后的宿主运行框架规则和
设计选择——重新加入前置检查或处理路径前，请先阅读。 -->

1. **选择分支名**（如果没有给出）：名称要简短，从任务中提炼，并与现有
   worktree 名称风格一致；如果是在会话中途，则根据要迁移的工作命名；
   没有任何依据时，询问用户。

2. **没有 repo 参数时，一次调用完成创建和进入：**
   `EnterWorktree({name: "<branch>"})`。Worktrunk 的 `WorktreeCreate` hook 会运行
   `wt switch --create`，因此结果是采用默认布局的普通 `wt` worktree，
   用户不会看到确认提示。成功后，执行任务（如果没有任务文本，则确认
   已准备就绪并等待）。

   在会话中途，要把未提交改动一并带过去：调用 `EnterWorktree` 前运行
   `git stash push -u`，之后再运行 `git stash pop`——该调用会把会话重定根
   到新 worktree，而 stash 在各 worktree 之间共享。

3. **其他情况用 `wt` 创建，再按路径进入。** 两种情况会走到这里：一是给了
   repo 参数，而第 2 步无法指定目标仓库；二是第 2 步失败，其错误会说明原因——
   `✗ Branch <branch> already exists` 或 `Already in a worktree
   session`。通过一次 `Bash` 调用创建（当前仓库应省略 `-C <repo>`）：

   ```
   wt -C <repo> switch --create <branch> --no-cd --format=json
   ```

   stdout 是 JSON，其中 `path` 字段为 worktree 的绝对路径（状态行写入
   stderr）。遇到 `Branch <branch> already exists` 时：如果分支名由用户
   指定，去掉 `--create` 后重试（这会进入该分支；若其 worktree 不存在，
   则创建一个）；如果名称由第 1 步选择，则换一个名称后重试。任何其他失败
   （不是 git 仓库、名称无效）：报告错误并停止。

   然后调用 `EnterWorktree({path: "<path from the JSON>"})`。

   - **已接受** → 会话重定根到该 worktree。执行任务（如果没有任务文本，
     则确认已准备就绪并等待）。
   - **工具错误**——工具已经运行并返回错误（`Cannot enter
     worktree: …`）→ 这是可控失败；没有发生目录移动，一套恢复方式即可处理
     全部情况。常见原因：cwd 解析不到 git 仓库（例如后台任务从
     `~/workspace` 这类只用于容纳仓库、但自身并非 git 仓库的父目录启动），
     或解析到的仓库与目标不同；也可能是会话已重定根到某个 worktree（或属于
     固定的 agent），此时只能进入当前仓库的 `.claude/worktrees/`，连同仓库的
     `wt` 兄弟 worktree 也被排除。恢复测试是能否 `cd` 进入该 worktree；
     如果它位于允许的目录内，就能进入。因此运行 `cd <path>` 并查看结果：
     - 没有 `Shell cwd was reset` 提示 → 目录切换保持住了，worktree 可达。
       在那里工作，但单独的 `cd` 不属于受跟踪的重定根，因此跨轮次（以及在
       派生的子 agent 中）cwd 可能恢复到会话启动时的 worktree；命令应使用
       `git -C <path>` / `wt -C <path>` 固定路径，不要假定 `cd` 会持续生效。
     - 出现 `Shell cwd was reset` → 不可达。停止并请用户开放访问：把该仓库
       或 `~/workspace` 这样的父目录加入 `permissions.additionalDirectories`
       （持久生效，覆盖每个会话），或运行 `/add-dir <path>`（仅本会话）。
       然后继续。不要在每条命令的 `cd` 都会重置时靠绝对路径硬撑。
   - **已拒绝**——调用本身被拒绝，且没有工具错误 → 无论拒绝如何措辞，只要
     不是因为没有用户可询问（拒绝信息会说明会话无法弹出提示；这种情况没有
     形成任何决定，应采用上述恢复方式），它就是用户对 Claude Code 确认提示
     的回答；该提示会在进入 `.claude/worktrees/` 外的 worktree 时出现。若是
     用户作出的回答：`wt` 刚创建的 worktree 仍然存在，只是没有进入。报告其
     路径并询问下一步，因为通过 `cd` 进入会推翻这个回答。

## 清理

这个 worktree 是普通的 Worktrunk worktree：它会出现在 `wt list` 中，并像
其他 worktree 一样通过 `wt merge` / `wt remove <branch>` 合并或删除。不要
未经请求就删除。

如果会话从未触碰第 2 步创建的 worktree——没有改动文件，也没有提交——
会话结束时会连同分支一起清理；只要向其中写入过内容，就会保留。第 3 步
创建的 worktree 始终保留。如果用户要求在会话中途离开，
`ExitWorktree({action: "keep"})` 会让会话返回原目录；
`ExitWorktree` 无法删除通过 `path` 进入的 worktree，因此删除这类 worktree
始终使用 `wt remove <branch>`。

## 范围

本命令只负责一个 worktree（如果指定了仓库，就在该仓库中）及其中请求的
任务。创建提交、推送和合并仍各自需要用户明确许可。
