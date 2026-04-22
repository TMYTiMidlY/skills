---
name: autopilot
description: 自动推进式任务系统。通过 cron 定时触发 Hermes session，在 Docker 容器内自主推进任务、开 PR、汇报进度。Claude Code 负责规划和写目标，Hermes 负责执行。
---

# Autopilot

两个角色，一套状态仓库：

- **Claude 端（规划者）**：分析需求、拆分 targets、写 goal.md / constraints.md，推到状态仓库。确保 targets 仓库的 autopilot-work 分支存在。设 status=pending。
- **Hermes 端（执行者）**：cron tick 触发，每轮在新 Docker 容器里推进一步。状态全部通过 Git 远程仓库跨 session 传递，容器是一次性的。

## 执行骨架（Hermes 端）

1. **拉状态**：clone 状态仓库，读 goal / progress / attempts.log 最近 20 行 / status
2. **选方向**：根据历史挑下一个维度；上轮失败就换方向
3. **动手**：clone 目标仓库，切 feature 分支，做一件事
4. **验证**：跑仓库已有的 lint / test
5. **收尾**：push + 开 draft PR；写 `logs/<时间戳>.md`（本轮对话摘要 + 文件变更 diff）；更新 progress / attempts.log / status；push 状态仓库；按需微信汇报

## 状态文件

| 文件 | 写入方 | 说明 |
|---|---|---|
| goal.md | Claude | 目标 + targets 列表 + 状态仓库地址 |
| constraints.md | Claude（可选） | 特殊约束，不写则 agent 自由发挥 |
| progress.md | Hermes | 当前进度 |
| attempts.log | Hermes | 每次尝试一行 |
| status | 双方 | pending → running → done / stuck / paused |
| report.md | Hermes | 终态报告 |
| logs/*.md | Hermes | 每轮对话摘要 + diff |

这些全是本 skill 的设计，不是 Hermes 内置的。详细格式见 [references/state-protocol.md](references/state-protocol.md)。

## 额度检查

wrapper 脚本在派发 Hermes 前查 API 剩余额度，区分 5H 额度和 weekly 额度：5H 不足时 sleep 等 reset；weekly 耗尽时通知用户等下周。脚本见 [scripts/](scripts/)。

## 参考

- PR 流程：[references/pr-workflow.md](references/pr-workflow.md)
- 优化维度：[references/dimensions.md](references/dimensions.md)
- 微信汇报：[references/messaging.md](references/messaging.md)
