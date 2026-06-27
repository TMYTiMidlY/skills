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
   - 用 `scripts/` 里的 dump 脚本（按需 `--format text` 通读、`--format html` 留档）拉出全部条目。
   - **session id 永远用 system prompt 给的 session 文件夹名**（即 `~/.copilot/session-state/<id>/` 里的 `<id>`），**不要追着对话里出现的别的 id 跑**——对话里经常会出现历史会话 id、文件名里的 id 等，那些不是当前会话。这是高频踩坑点。
   - ⚠️ live store 滞后最近一两个 turn，最新一轮可能还没落库——这部分用你自己的上下文补。
2. **plan.md 与 todos**——session 文件夹下的 plan.md、SQL `todos` 表里没标 done 的项。
3. **真实世界状态**，别凭印象：
   - `git status` / `git log`：有没有改了没 commit、commit 了没 push 的。
   - 文件系统 / 远端实况：服务真起了吗、远端真部署了吗（走 portal）。
   - **grep 验证承诺**：用户要的功能，代码里真有对应实现吗？（典型坑：文档/配置描述了一个开关，但 `grep` 发现代码里一个标识符都没有——等于没做。）

## 工作流程

1. **先 dump 原始对话**：跑 `scripts/` 里的 dump 脚本通读用户的每一条消息。逐条问自己："这件事最后做了吗？做完整了吗？还是被后面的任务压下去忘了？"
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

- **报告式 HTML 存档**：用户想要可视化留档 / 把会话过程交给别人时，用 `scripts/` 里的 dump 脚本（自身用 `uv run` 跑、PEP723 内联依赖）生成单文件 HTML。
  - 数据源是 `~/.copilot/session-state/<id>/events.jsonl`（缺失时回退到 `session-store.db` 的 `turns` 表，header 显示警告）——这就是 Copilot CLI 自带 `/share html`（别名 `/export`）消费的同一份事实。所以能还原**完整时间线**：用户消息 / 助手回答 / 推理（reasoning） / 工具调用（按 `callId` 合并 start+complete） / 通知 / 信息 / 错误等全部 entry 类型。
  - 视觉**照搬 `/share html`**：暗色 GitHub(Primer) 主题、sticky header、按类型筛选 pill、搜索（`/` 聚焦）、折叠/展开、侧栏目录、上一条/下一条用户消息跳转。CSS/JS 来自从 `@github/copilot` 包里抽出的资产；标签汉化但 `data-type` 保持英文（JS 过滤靠它）。助手消息按 markdown 渲染、用户消息转义。
  - **想在报告顶部钉 agent 总结**：把"做过的事 / 承诺未做"等盘点写成 HTML 片段文件（`<h3>`/`<ul>` 等简单标签即可，精炼别太详），用 `--summary <片段.html>` 注入。总结条目**钉在编号之外**（`data-index="summary"`），真实 #1 仍是真实第一条事件；同时多一个 `总结` 筛选 pill。
  - **两条渲染路径并存**（视觉不同，按场景选）：
    - **vanilla**（`scripts/dump_session.py <sid> [--summary 片段.html] [out.html]`）：纯 Python 拼字符串、复刻 `/share html` 视觉、~1MB、**零构建**（只需 `uv`）。要快、要轻、要和 share 一致时用。
    - **React**（`scripts/build_react_report.sh <sid> [out.html] [--summary 片段.html]`）：Vite 打包成单文件、shadcn 风卡片 + lucide 图标 + Shiki 高亮，外加 vanilla 没有的三样：**紧凑密度切换**（header 按钮，状态存 localStorage）、**LaTeX**（KaTeX，行内 `$x$` + 块级 `$$…$$`，仅作用于助手 markdown 消息）、**summary 按 HTML 原样渲染**。代价：需 `pnpm build`（首次自动 `pnpm install`），产物 ~3MB / gzip ~1.4MB（KaTeX 字体 base64 内联占大头）。要精致视觉 / 会话里有数学公式时用。
    - 两条**共用同一数据层**：React 端只消费 `export_session_json.py` 出的 agent-neutral JSON，**绝不**自己解析 events.jsonl（解析只在 `dump_session.py` 里做一次）。`--summary` 注入的总结条目两边都**钉在编号之外**（`data-index="summary"`），真实 #1 仍是真实事件。
  - **离线注定补不到的几类**：mascot 启动 banner（`Tip: /cwd` 这类）、`/share` 命令自产回执（`Session shared successfully to: ...`）、ephemeral retry 提示——它们**只活在 live session 内存**里、从不写盘。share 在 live 时能有，离线 dump 没有，这是事实差。
  - **维护责任**：`assets/share-export.{css,js}` 是从 `@github/copilot` 包里抽出来的资产，会随 Copilot CLI 升级**过期**（GitHub 团队加新 entry 类型 / 改 Primer 主题色 / 调按钮 ID 之类）。每次 Copilot CLI 出明显的视觉或 `/share html` 行为升级，要跑一次 `scripts/` 内的资产抽取脚本重抽，diff `assets/` 看变化——具体怎么用见 `assets/README.md`。
- **正式交接文档**：若用户明确要"交接给下一个 agent / 写 handoff"，结合 `plan` skill（写给实施者的自包含正式文档）或仓库自带的 handoff 流程，不要在本 skill 里重造。

## 待办（后续扩展）

- **支持 Claude Code 和 Codex 的会话导出**：当前数据层硬绑 Copilot CLI（`~/.copilot/session-state/<id>/events.jsonl` 的 schema）。Claude Code 存档在 `~/.claude/projects/*.jsonl`、Codex 在 `~/.codex/sessions/` 各有各的格式。下一步是把 events.jsonl 解析抽象成"数据源接口"，再补两个 adapter（claude-code / codex），让 recap 三家通吃。**渲染层两条路都已 agent-neutral**：vanilla 的 CSS/JS + entry DOM + 筛选 pill、React 的组件层都只消费中间形态（events.jsonl 解析结果 / `export_session_json.py` 出的 JSON），所以做完数据源抽象后**两条渲染路径都不用动**。

## 边界

- 本 skill 只**盘点和报告**，不替用户做有副作用的动作。所有 commit / push / 发布 / 删除都列成待办让用户决策。
- 不臆造"做过的事"——拿不准就标"待验证"，并去 grep / 查状态坐实。
