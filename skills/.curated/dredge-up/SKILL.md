---
name: dredge-up
description: 会话收尾盘点——把你聊过/承诺过、却被后续任务压栈沉底的事，从上下文里逐条捞回来，核对到底做没做。不只回顾本 session 做过什么，更要揪出"说过却漏做"的遗漏项。当用户说"我要把你关掉了，还有没有什么没做的""总结一下本 session 做了什么还有什么没做""回顾本 session 我说过的话看看漏了什么""收尾/交接前盘点"之类时触发。
---

# dredge-up — 会话收尾盘点

用户准备关掉这个会话前，让你回头清点：**做过了什么** + **聊过/承诺过但还没做的是什么**。

核心不是复述你记得的事，而是**把被你自己上下文丢掉的遗漏项捞回来**——长会话里早期的 turn 会被压缩/截断，用户随口提的小事最容易漏，而那恰恰是他最怕忘的。

## 为什么不能只凭记忆

你当前的上下文是**有损**的：长会话早期对话被压缩，用户某句"顺便把 X 也改了"可能已经不在你视野里。所以单一信源都不够，必须**多源交叉**：

1. **本 session 的原始 turns / 事件流**（最重要）——回读本机 session 状态目录里的存档，逐条看用户**实际说过的每一句话**，而不是你记得的版本。这是唯一能抓出"压栈遗忘"项的办法。
   - 用 `recall show <id> --format text` 通读全部条目（`recall` = `agent-session-exporter` 仓库的 CLI，见下「可选输出」）。
   - **session id 永远用 system prompt 给的 session 文件夹名**（即 `~/.copilot/session-state/<id>/` 里的 `<id>`），**不要追着对话里出现的别的 id 跑**——对话里经常会出现历史会话 id、文件名里的 id 等，那些不是当前会话。这是高频踩坑点。
   - ⚠️ live store 滞后最近一两个 turn，最新一轮可能还没落库——这部分用你自己的上下文补。
2. **plan.md 与 todos**——session 文件夹下的 plan.md、SQL `todos` 表里没标 done 的项。
3. **真实世界状态**，别凭印象：
   - `git status` / `git log`：有没有改了没 commit、commit 了没 push 的。
   - 文件系统 / 远端实况：服务真起了吗、远端真部署了吗（走 portal）。
   - **grep 验证承诺**：用户要的功能，代码里真有对应实现吗？（典型坑：文档/配置描述了一个开关，但 `grep` 发现代码里一个标识符都没有——等于没做。）

## 工作流程

1. **先 dump 原始对话**：跑 `recall show <id> --format text` 通读用户的每一条消息。逐条问自己："这件事最后做了吗？做完整了吗？还是被后面的任务压下去忘了？"
2. **交叉核对状态**：对照 plan.md / todos / `git status` / 文件系统 / 远端，确认每件"自以为做完"的事**真的**落地了。
3. **grep 验证关键承诺**：凡是"实现了某功能"的结论，回去 `grep` 确认代码/配置真的存在、真的生效，不要只凭你说过"我改好了"。
4. **按下面的范式输出盘点报告**。
5. **可选交付物**：用户要交接 / 要留档时，写 handoff 或导出 HTML（见下"可选输出"）。

## 输出范式

参考用户过去最满意的几次收尾盘点提炼（详见 [references/examples.md](references/examples.md)）。结构：

### 一、做过的事
按编号或时间列，每条带状态标记（✅ 已落地 / 🟡 做了一半 / 本地未推 等）。简洁，要点即可。

### 二、聊过/承诺过但**还没做**的（重点）
这一节是用户真正要的。每条必须给齐：
- **是什么**（一句话）
- **严重度**：🔴 高 / 🟡 中 / 🟢 低
- **来源**：用户哪次说的、为什么漏了（如"被后续任务压栈"）
- **需要你决策的具体问题**：给出可选项（A/B/C）或具体命令，不要含糊地"建议看看"。
  - 凡涉及 `git add/commit`、push、发布、删分支、删文件等**有副作用**的动作，列出来让用户拍板，**不要自动执行**（遵守工作区 Git/发布/删除规则）。

### 三、值得记下的踩坑 / 经验（可选）
本 session 踩过但还没记进任何文档的坑。若有价值，提示用户是否要补记（如交给 `mess` skill 归档）。

### 四、给下一个 agent 的提示（仅交接时）
下一个 agent 看不到本会话上下文，列出：唯一交接物路径、用户已钉死的决策（"两次否决了 X，别再碰"）、易踩的坑。

### 五、安全交代（涉敏时）
若本 session 碰过密码 / secret / 凭据，简短说明你是否接触过明文、敏感文件落在哪、是否需要清理。

## 可选输出

- **报告式存档（导出 HTML / Markdown / 文本 / JSON）**：用户要可视化留档 / 把会话交给别人时，用 **`recall`**（`agent-session-exporter` 仓库的 CLI）导出。本 skill **不再自带渲染器**——同一套解析+渲染逻辑只在 `recall` 里维护一份。
  - 首次在本机准备：clone `TMYTiMidlY/agent-session-exporter`，`pnpm install && pnpm build`（要全局命令就再 `pnpm --filter @agent-session-exporter/cli exec npm link` 装出 `recall`；否则用 `node packages/cli/dist/index.js …`）。之后直接调。
  - **单文件 HTML**（复刻 Copilot `/share html`：暗色 Primer 主题、sticky header、按类型筛选 pill、搜索（`/` 聚焦）、折叠/展开、侧栏目录、上一条/下一条用户消息跳转，外加 Shiki 高亮、KaTeX 数学、紧凑密度切换、24h 时间戳）：
    `recall html <session-id> -o out.html`
    从任意 events.jsonl（如 restic 备份 restore 出来的）导：`recall html --file <路径> -o out.html`。
  - **Markdown**（字节级复刻 `/share file`）：`recall md <session-id> -o out.md`。
  - **纯文本通读 / 结构化 JSON**：`recall show <id> --format text|json`。text 已含工具参数+结果、子代理/技能/计划/压缩统计，适合上面「先 dump 原始对话」逐条通读。
  - **顶部钉 agent 总结**：把盘点写成片段文件用 `-s` 注入——`recall html <id> -s 总结.html`（HTML 片段）/ `recall md <id> -s 总结.md`（Markdown）。⚠️ 两种格式**不能混用同一文件**（html 要 HTML、md 要 Markdown），必要时看 `--summary-format`。总结条目钉在编号之外（`data-index="summary"`），真实 #1 仍是真实第一条事件。
  - **覆盖的 entry 类型**：user / assistant / reasoning / tool（按 callId 合并 start+complete） / notification / info / warning / error / compaction（含注入摘要 + token/消息/耗时统计） / task_complete / **subagent / skill / plan**（后三类超出官方 `/share html`，是 recall 额外从 events.jsonl 补的）。`events.jsonl` 缺失（老会话被 prune）时用 `--copilot-db <session-store.db>` 从 `turns` 表回退（lossy，header 标警告）。
  - **为什么导出 = 离线复刻**：官方 `/share html` 渲染的是 live 会话的**内存 timeline**、不是 `events.jsonl`；离线只能从 `events.jsonl` 把 event→entry 映射**重跑一遍**——**漏一个映射分支＝那类条目被静默丢掉**。完整逆向笔记见 exporter 仓库 `docs/copilot-timeline.md`。**session-id 永远用 `~/.copilot/session-state/<id>/` 的文件夹名**，别追对话里出现的其它 id（高频踩坑）。
- **正式交接文档**：若用户明确要"交接给下一个 agent / 写 handoff"，结合 `plan` skill（写给实施者的自包含正式文档）或仓库自带的 handoff 流程，不要在本 skill 里重造。

## 关于导出工具

导出（HTML / Markdown / 文本 / JSON）已全部交给 `agent-session-exporter` 仓库的 `recall` CLI，本 skill 只负责盘点方法论 + 调用它。多 agent 支持（Claude Code / Codex）、从 restic 备份缓存搜索等能力都在那个仓库里演进，见其 README 与 `docs/`。

## 边界

- 本 skill 只**盘点和报告**，不替用户做有副作用的动作。所有 commit / push / 发布 / 删除都列成待办让用户决策。
- 不臆造"做过的事"——拿不准就标"待验证"，并去 grep / 查状态坐实。
