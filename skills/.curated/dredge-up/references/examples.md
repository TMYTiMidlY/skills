# dredge-up 输出范例

下面是从用户过去最满意的几次收尾盘点中提炼的范式。重点看**结构**和**遗漏项怎么写**，不是照抄措辞。

---

## 范例 A：commit 收尾 + 揪出压栈遗忘项

> 用户原话："总结一下本 session 除了做这个 commit 还做过什么事情，并通过回顾本 session 我说过的话，看看还有没有什么聊过但忘记处理的，我要把你关掉了"

这次之所以好，是因为 agent **真的回读了全对话**，抓出了一件早期讨论、后来被新任务压下去的事，并把它列成"需你决策"的具体问题，而不是含糊带过。

```
# 本 Session 全回顾

## 一、做过的事
1. 分支侦察：发现上游 feat 被 force-push 重构 …
2. 代码审查：挖出 4 个 bug + 文档不一致
3. 回答你的架构问题（无交互式 CLI / token 没发挥平台能力）
4. main 分支 2 个 commit（已 commit，未 push）

## 二、聊过但还没处理的（关掉前请你定）
① main 的 2 个 scrub commit 还没 push — 你这次只说推 feat。要不要也 push？
② 备份分支 …-backup-505033b 还在 — 确认无误后可删；safety net 不让我删，请你手动：
   git branch -D feat/agentic-search-backup-505033b
③ 同类拓扑泄露还有 2 个文件没 scrub（超出你当时点名范围，我没动）：
   - docs/deployment/server-config.md（mesh IP ×3）
   - docs/spikes/bulk-data-rustfs-…md（主机名 ×4）
   要不要一并处理？
④ GPU 型号 "RTX 5080" 多处仍在 — 我判断是公开硬件要求，故意保留。你认可吗？

## 三、已确认闭环的
- 早期 review 的 2 个文档项 → 已 moot（config 改 YAML 后新 README 已含）
```

要点：
- 第二节每条都落到**一个可回答的问题** + 具体命令/路径。
- 有副作用的动作（push / 删分支）**列出来让用户拍板**，不自动做。
- 第三节澄清"看着像漏、其实已闭环"的，免得用户重复操心。

---

## 范例 B：带严重度分级 + grep 坐实"没做"

> 用户原话："总结一下本 session 做过什么，还有没有可能有什么问题我忘处理，我准备把你关掉"

这次的杀手锏：用 `grep` 验证了一个"自以为做完"的承诺，发现**文档描述了一整套开关，但代码里一个标识符都不存在**——等于没做。这种只有去查才抓得到。

```
## ⚠️ 关掉我之前强烈建议你处理

### 🔴 严重：未 commit 的 QATLAS_ASSET_DOWNLOADS_ENABLED 是 docs-only，没有后端代码
  grep -rn "QATLAS_ASSET_DOWNLOADS_ENABLED|asset_downloads_enabled" --include=*.go --include=*.py
  → NOTHING
  .env.example + 4 个 doc 描述了开关 + 11 个字段 + 条件 endpoint，但代码里一个标识符都没有。
  你 commit 前需要选一：
  (A) 不要 commit，等代码先 land
  (B) 仍 commit，但 doc 加 "WIP — 见 issue #N" marker
  (C) 当 design proposal 写到 plan.md 而非用户文档

### 🔴 严重：未 commit 的 2 条 mkdocs 锚点链接 broken，mkdocs --strict 会挂
```

要点：把"我以为做完了"和"真的做完了"分开——结论性陈述一律回去 `grep` / 查状态坐实。

---

## 范例 C：未完事项表格 + 交接提示

> 用户原话："我给下一个 agent 这个 plan 他能搞定么…除了这个还有没有什么你漏做我们讨论过的事情？"

漏项用表格列，每条带**严重度 + 来源**（为什么漏）：

```
### 漏做 / 未完事项（要交接的）
| # | 漏的事 | 严重度 | 来源 |
|---|--------|--------|------|
| 1 | RackNerd edge 仍跑 v0.12.0（实测 /api/health 返回旧版） | 🔴 高 | 部署时只 deploy 了 Alibaba，RackNerd 没同步 |
| 2 | Task 1（storage docs 重构） | 🟡 中 | 早就让我做的，被 Task 2/14.1/15.0 三连压栈，没动 |
| 3 | issue #4 修（老格式 claim 失败） | 🟡 中 | 独立 PR，不阻塞 |

### 给下一个 agent 的提示
- plan.md 是唯一交接物，自包含、中文、可直接执行
- plan.md 明确写了"不要 pypdf split" —— 用户两次否决，下一个 agent 别心痒
- 改 server 代码后必须 pixi run swagger 重生，否则 CI 红
```

要点："来源"列暴露**为什么会漏**（多半是"被后续任务压栈"），这正是用户最想知道的盲区。

---

## 通用清单（输出前自检）

- [ ] 我**真的 dump 了原始对话**逐条看，而不是只凭上下文记忆？
- [ ] 每件"做完了"的事都对照 `git status` / 文件系统 / 远端 / grep 坐实了？
- [ ] 遗漏项都给了"严重度 + 来源 + 可决策的具体问题"？
- [ ] 有副作用的动作（commit/push/发布/删除）都留给用户拍板、没自动执行？
- [ ] 涉敏的话交代了密码/secret 接触情况？

---

## 附：这套方法论是怎么挖出来的（5 步）

本 skill 的"多源交叉 + 揪压栈遗漏"范式不是凭空设计的，是从用户历史会话里挖出来的。下次要扩展 / 复刻这套方法（或给别的 agent 套同样的路子），照这条路走：

1. **`/chronicle search` 先试，但别死磕**——云端 store 会连续 `query timed out`，试几次不通就迅速放弃，别在它上面耗。
2. **直接 SQL 本机 `~/.copilot/session-store.db`（`mode=ro` 只读打开）**——这才是可靠信源；注意 live 会话最近 1~2 个 turn 还没 flush，最后一轮可能读不到。
3. **关键词两遍走**：先**宽**（"承诺/遗漏/没做/收尾"）会拿到几百条噪音；再**收严**（"回顾本/我说过的话/聊过但/本 session/关掉你"）收到上百条——**严的这遍是关键**。用户最稳定的高频信号是「我要把你关掉了，还有什么没做的」+「回顾本 session 我说过的话看看漏了什么」。
4. **读代表性会话里 agent 的回答**，找出用户反复点赞的范式（做过 / 聊过但没做 / 踩坑 / 安全交代）——就是上面几个范例的出处。
5. **dump 当前 live session 验证 schema**——会发现 `turns` 表只有 user/assistant 文本，而完整时间线（工具调用 / reasoning / 通知）在 `~/.copilot/session-state/<id>/events.jsonl`。**直接看 events.jsonl，别只读 `turns` 表**——这是花了最久才意识到的一点，可以省掉。
