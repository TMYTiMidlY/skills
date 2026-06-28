# Copilot CLI sessions and exports

Session-state and export notes: local resume IDs, live-vs-offline conversation data, and `/share html` reverse-engineering details.

## Chronicle 搜索给 resume ID：必须给本地 ID

`/chronicle search` 用 `session_store_sql` 查的是**云端 + 本地两套 session store 合并**的结果（每行带 `_query_source` = `cloud` / `local`）。同一个会话在两套库里 **session ID 不一样**：云端是一份同步副本，本地是 `~/.copilot/session-state/<id>/` 下真正能 resume 的那份。

**`copilot --resume=<id>` 只认本地 ID**——拿云端 ID 去 resume 会直接报 `No session, task, or name matched`。

所以 chronicle 给用户用来 resume 的 ID 时：

- **只给本地 ID**，即 `_query_source = 'local'` 且 `~/.copilot/session-state/<id>/` 目录存在的那个。
- 搜索结果里如果同名会话既有 cloud 又有 local，**优先取 local 行的 ID**，别取 cloud 的。
- 不确定时本地核一下：`ls ~/.copilot/session-state/<id>` 有目录才是可 resume 的。
- 纯 cloud-only（本地无目录）的会话：明说「本机不可 resume，状态在另一台机器上」，别给一个 resume 不了的 ID。

---
## `/share html` 对话导出（逆向）

把 live 会话导出为一份**单文件、可交互**的 HTML 报告——暗色 Primer 主题、按类型筛选、搜索、可折叠条目、侧栏 map、上下条用户消息跳转。下面是想离线复刻同款产物时必须看懂的几件事。

### `/share` 与 `/export`

同一条命令的两个名字——`/export` 是 `/share` 的纯别名（同一个 command 对象、同一份 `args` 解析器、同一份 execute 路径），行为完全一致。子命令 `file` / `html` / `gist` / `research` 都共享。

### 真实数据源 = `~/.copilot/session-state/<id>/events.jsonl`

`/share html` 在 live 会话里从内存 timeline 取条目；写盘的同一份事实就是这份 NDJSON。**离线复刻只读这一份即可**。每行 `{type, data, id, timestamp, parentId}`，时间戳是 ISO+UTC（末尾 `Z`），离线端要自己 `astimezone()` 转本地——share 在浏览器里走 `Date.toLocaleString()`，默认 en-US locale 用 **12 小时制 AM/PM**（"6/26 11:04:21 PM" 其实就是 23:04:21，曾经误导）。

### events → entries 映射

一条事件可能产出**多条** timeline-entry。最反直觉的是 `assistant.message`：它**同时**携带 `reasoningText` + `content` + `toolRequests[]`，要按顺序拆成 reasoning 条目 + copilot 条目，tool 调用则交给后续 `tool.execution_start/complete` 配对。其余几类的常用映射：

| 事件 | 产出 | 备注 |
|---|---|---|
| `user.message.content` | user 条目 | 渲染用 `content`，不是 `transformedContent`（后者注入了 system_reminder）|
| `tool.execution_start` + `tool.execution_complete`（同 `toolCallId`） | **一个** merged-tool 条目 | 不配对的孤儿 complete 也独立产出，详见下"合并"小节 |
| `system.notification` | notification 条目 | 渲染时 `data-type` 是 `notification`（不是 `system_notification`，注意命名）|
| `session.info` (`infoType=model`) | info 条目，text = `data.message` | "Model changed from X to Y" 就是这个 |
| `abort` | info 条目，text = `"Operation cancelled by user"` | bundle 用 `emitEphemeral` 同步发了一条 `session.info(infoType=cancellation)`，**ephemeral 不写盘**——离线只能从 `abort` 自己合成同款文案 |
| `hook.*` / `assistant.turn_*` / `system.message`（system prompt） / `session.start` | 跳过 | UI 噪音 / 巨大无用 |

dispatcher 还能接受这些类型（live 会话偶尔出现，离线 events.jsonl 极少）：`error / warning / handoff / compaction / task_complete / group_tool_call_*`——形状已知，离线复刻可以兜底渲染。

### live-only 条目：离线复刻**注定**少几条

share 输出里有几类 info 是 bundle 直接 `addTimelineEntry()` 进**内存** timeline、从不写盘，离线无法重建：

- `Tip: /cwd`（mascot 启动横幅；bundle 里的 "Tip: " 字面量只在终端 React-Ink UI 里）
- `Session shared successfully to: ...`（`/share` 命令自己的回执；离线场景本就无意义）
- `Response was interrupted ... Retrying...`（重试机制 ephemeral）
- `Operation cancelled by user` 的源头（`session.info` cancellation）也是 ephemeral；离线靠 `abort` 重造文案

对照过真 share HTML：`Tip:` 那条字符串在 events.jsonl 里 **0 次实命中**（任何"命中"都来自 hook.start 把我们自己的 bash 命令文本完整存了进去）。**接受这缺口比硬造一条更诚实**。

### Tool 条目合并

渲染层看到的"每个工具调用一条卡片"是经过合并的结果——bundle 在装配前把 `tool_call_requested` 和它的 `tool_call_completed`（按 `callId`）**配对成单条**：`{kind:"merged-tool", entry:{name, args, intentionSummary, result, …}}`。result 上的 `type ∈ {success, failure, rejected, denied, pending}` 决定边框色 + 图标 + 是否加 `entry-error-bg`。

### Tool 参数的"单行摘要"

`grep`/`glob`/`bash`/`view`/`edit`/`create` 这几个 known 工具有专门的紧凑摘要规则（如 `bash → "$ <command>"`、`grep → "<pattern> in <glob>"`、`view → "<path> (lines N-M)"`），渲染成 inline code。其它工具回退到完整 JSON pretty-print。结果 log 渲染分三档：`result.markdown===true` 用 markdown 渲染；不是 markdown 但看着是 diff（含 `diff --git` 或同时含 `@@`/`+++`/`---`）用 `<pre data-lang="diff">`；其它就是普通 `<pre><code>`。

### 文档壳与每条 entry 的 DOM 契约

整页是**纯字符串模板**装配，没用任何前端框架：

- 文档壳 = doctype + `<html data-color-mode="dark" data-light-theme="light" data-dark-theme="dark">` + 内联 Primer light/dark CSS + sticky header（search box + filter-pills + Compact/Collapse all/Expand all/Map/Theme 按钮）+ `.scroll-container`（sidebar + main + jump-prev/jump-next 浮动按钮）+ 内联 vanilla JS。
- 每条 entry = `<div class="entry [collapsed] border-{type}" data-type="…" data-index="N" id="entry-N">` + `entry-header` + `entry-body`。**`data-type` 是英文且 JS 只读 data-* 属性、不读 label 文字**——所以离线版本汉化标签是安全的，改 `data-type` 才会破。
- 各类型默认折叠态遵循 bundle：`copilot / user / error / task_complete` 默认展开；`reasoning / info / warning / tool / group / handoff / compaction / notification` 默认折叠。

### CSS / JS 资产

CSS 由三段拼成：Primer light + Primer dark + share 自家壳（sticky-header / filter-pills / sidebar / entry / tool 等专属规则）。JS 是一个 vanilla IIFE，负责折叠展开 / 主题切换（`localStorage("copilot-share-theme")`）/ 类型筛选 + 搜索（`/` 聚焦）/ sidebar map / 上下条用户消息跳转 / compact mode / mini 语法高亮 / hash deeplink——0 依赖、0 外网请求。

### 离线复刻的关键陷阱：JS 模板字符串的"双反斜杠"

CSS 和 JS 在 bundle 里都是模板字符串字面量。源码层每个反斜杠都是双写的（`\\u2600`、正则 `\\b`、`\\n`、…），bundle **运行时**模板字符串引擎把 `\\` → `\` 再写进页面。

如果离线抽取**按原始字节复制**这些字面量直接落盘，所有真反斜杠都是双的——**主题按钮看着不响应**（textContent 拿到字面量 `\u2600` 不是 ☀），**搜索/语法高亮的正则全坏**（`\\b` 在正则里=匹配字面反斜杠），`split('\\n')` 不分行。

正确做法：把模板字符串体当作 JS 模板字面量**求值一次**再落盘——拿任何 JS 运行时跑 `\`...\`` 就行，让引擎自己折叠转义。另一个细节：`pFs` 自身的 mini-highlighter 包含一个**字面反引号**（源码里用反斜杠转义），所以"下一个反引号定界"会切错——边界要靠下一个相邻函数（不是下一个反引号）。

### 离线复刻参考实现

`dredge-up` skill（`skills/.curated/dredge-up/`）已经基于上述逆向做了一份**离线**复刻——从 `events.jsonl` 重建时间线、复刻同款 entry DOM、复用 share 抽出的 CSS/JS，并加了 agent 总结注入。要做"离线把会话存档成 HTML"这件事直接用它，不要重新逆向。
