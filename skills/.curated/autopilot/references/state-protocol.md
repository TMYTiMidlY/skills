# 状态协议

## 远程仓库

状态通过 Git 私有仓库持久化。仓库地址从 goal.md 的 `state_repo` 字段读取。

每轮起手：

```bash
gh auth setup-git
git clone "https://x-access-token:${GH_TOKEN}@github.com/${state_repo}.git" /root/state
```

每轮收尾：

```bash
cd /root/state && git add -A && git commit -m "tick <时间戳> | <task_id>" && git push
```

## 目录结构

```
<task_id>/
  goal.md
  constraints.md   (可选)
  progress.md
  attempts.log
  status            (纯文本文件，内容为状态值之一)
  report.md
  logs/
    <YYYYMMDD-HHMM>.md
```

## goal.md 示例

```markdown
# Task: github-cleanup

state_repo: <OWNER>/<STATE_REPO>

## 目标

对以下仓库从多个维度优化，每个维度开 draft PR 到 autopilot-work 分支。

## Targets

- <OWNER>/repo-a
- <OWNER>/repo-b
```

## status 状态机

`pending → running → done | stuck | paused`

- **pending**：Claude 端创建任务后设置
- **running**：Hermes 端正在推进
- **done**：所有维度完成或 exhausted
- **stuck**：穷尽方法，需人工介入
- **paused**：用户手动暂停；Hermes 检测到后直接退出。额度不足时 wrapper 不改 status，只静默跳过并通知一次，额度恢复后自动继续

## attempts.log

每行一条，`|` 分隔：

```
<ISO8601> | repo=<仓库> | dim=<维度> | approach=<做法> | outcome=<success|fail|abort> | detail=<一句话>
```

## logs/<时间戳>.md

每轮一个文件，记录：

- 本轮选择的 target 仓库和维度
- 具体做了什么（对话摘要）
- 文件变更 diff（`git diff --stat` + 关键 diff 片段）
- 结果：成功 / 失败 / abort，PR 链接（如有）
