# 微信汇报

## 汇报时机

仅在以下节点向用户发送消息：

1. **阶段突破**：某个仓库的某个维度首次完成（PR 成功创建）
2. **需要决策**：遇到需要用户判断的问题（如仓库缺少 autopilot-work 分支、仓库为空、target 仓库不存在）
3. **连续失败**：同一方向连续 3 次失败，标记为 exhausted
4. **任务终态**：status 变为 done 或 stuck
5. **异常告警**：owner 预检失败、Git 操作异常、状态文件格式错误

**不汇报的场景**：正常推进中的每一步、正常的单次失败（下一轮会换方向重试）。

## 消息格式

简洁、结构化，一眼看清状态：

```
[autopilot] <task_id>
状态: <running/done/stuck/paused>
仓库: <repo_name>
动作: <做了什么>
结果: <成功/失败/需要决策>
详情: <一句话>
```

示例——正常推进：

```
[autopilot] github-cleanup
状态: running
仓库: my-tool
动作: README 补充安装说明
结果: PR #3 已创建 (draft)
详情: 补充了 pip install 和基本用法示例
```

示例——需要决策：

```
[autopilot] github-cleanup
状态: running
仓库: my-tool
动作: 检查 autopilot-work 分支
结果: 需要你操作
详情: autopilot-work 分支不存在，请手动创建后 autopilot 会在下一轮继续
```

示例——终态：

```
[autopilot] github-cleanup
状态: done
仓库: 全部
动作: 任务完成
结果: 3 个仓库共提交 7 个 draft PR
详情: 完整报告见 .autopilot 仓库 github-cleanup/report.md
```

## 终态汇报

当 status 变为 done 或 stuck 时，消息附带 report.md 的摘要（不超过 10 行）。完整报告写在状态仓库的 `<task_id>/report.md` 中。
