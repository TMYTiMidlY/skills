# DeepSeek Harness（dsh Web GUI）疑难杂症

> 本页记录 DeepSeek Harness（`dsh`）Web GUI 中低频、依赖特定连接历史才会出现的问题。这里的"交互弹窗"指 approval 面板和 ask_user_question 问题卡：它们都是输入框区域的接管组件，只在当前会话视图渲染，没有全局对话框——这也是症状容易被误认为"弹窗没弹出来"的原因。

## <a id="interaction-card-missing"></a>交互弹窗缺失（approval 与 ask_user_question 卡住直到刷新）

> 2026-09-03 | `@deepseek-ai/dsh` 0.1.1-rc.2（npm `latest`，全局安装后 `dsh web` 启动）| Linux + 桌面 Chrome | 无头 Playwright 监控页、zstd 会话日志取证、git 历史考古、GitHub Discussions 检索

### 症状

- agent 调用 ask_user_question 或触发沙箱升级审批后，工具调用停在"等待应答"，输入区不出现接管面板，会话看起来就卡在那里。
- 手动刷新页面后弹窗立刻出现——刷新触发重连和待处理请求的重放。
- 侧边栏会话行可能亮着琥珀色"等待交互"圆点，而输入区没有面板。manager 层的交互状态还活着、Session 层的可应答等待已被清掉，这个错位是本 bug 的指纹，30 秒就能把范围缩到这两层。
- 触发与断连循环强相关：桌面标签页长时间后台放置（WebSocket 静默死亡）、网络抖动、休眠恢复、反向代理闲置超时。桌面标签页能把 socket 保持数小时，所以罕见；手机上每次锁屏或 Wi-Fi↔蜂窝切换都会断一次，几乎每次必触发——同一个 bug 在不同平台的报告频率由连接稳定性决定。

### 探测手段

页面没有任何报错、console 干净、新会话一切正常，所以定位靠的是"在无错的系统里找时序证据"。按出力的顺序记录四种手段。

#### 无头浏览器监控页

用 Playwright 起一个监控页，选中与用户相同的会话，同时监听 WebSocket 帧到达和弹窗 DOM 出现，取两个时刻之差：

```js
// playwright 从 .pnpm 里显式导入；浏览器缓存版本与包不匹配时，
// launch() 会报 Executable doesn't exist，用 executablePath 指向
// ~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome
const { chromium } = await import('<repo>/node_modules/.pnpm/playwright@<ver>/node_modules/playwright/index.mjs')
const browser = await chromium.launch({
  headless: true,
  executablePath: '<ms-playwright 缓存>/chromium-*/chrome-linux64/chrome',
})
const context = await browser.newContext()
// GUI 把当前会话存在 localStorage；注入后监控页与用户页面看同一会话
await context.addInitScript(
  id => localStorage.setItem('dsh.sessions.current', JSON.stringify({ sessionId: id })),
  process.env.DSH_SESSION_ID,
)
const page = await context.newPage()
page.on('websocket', ws => {
  if (!ws.url().endsWith('/api/events.mux')) return
  ws.on('framereceived', e => {
    const m = JSON.parse(e.payload)
    if (m?.payload?.type === 'question/requested' || m?.payload?.type === 'approval/requested') {
      /* 记录帧到达时刻 */
    }
  })
})
await page.goto('http://127.0.0.1:3080/')
// 轮询 [data-question-key] / [data-approval-key] 的出现时刻，与帧到达时刻相减
```

实测结论：新鲜页面里 `question/requested` 帧到达后 57ms 弹窗就渲染出来，console 无错误。链路本身是通的——测试通过不等于没有 bug，缺的是触发前提（一次断连循环）。

#### 会话日志时间取证

dsh 的会话日志是 zstd 压缩的 JSONL，按事件类型过滤可以直接量出"卡住"的空洞：

```sh
zstd -dc ~/.dsh/sessions/<会话目录>/session.jsonl.zstd \
  | jq -c 'select(.type=="approval/asked" or .type=="approval/decided"
    or (.type=="tool/call" and .data.name=="ask_user_question")) | {seq, time, type}'
```

`ask_user_question` 的 tool/call 之后长时间没有 tool/result，且期间没有 `approval/decided`，就说明应答从未到达 Host。注意待处理请求本身走 WebSocket 通道、不落日志，所以日志只能证明"等待存在"，不能证明"帧是否送达浏览器"。

#### mux 帧流量画像

同一路 `framereceived` 监听按帧类型计数，10 秒窗口画像：约 1,279 帧（128 帧/秒），`session/projection` 与 `session/event` 占九成；mux 打开基线一次性推送 48 个 `session/subscribed`——页面订阅了 Host 上**所有**附着会话，跑着大量子代理时流量主要来自它们。高流量是放大器（长时间运行的页面负担越来越重），但不是本 bug 的根因；`ss -tinp` 看发送队列全空，也排除了网络瓶颈。

#### git 历史考古与上游检索

版本固定后先考古再尝试复现：

```sh
git log --all --oneline --grep='pending wait' --grep='reconnect' -i   # 找修复 commit
git show <fix-sha> -- <相关文件>                                       # 看它改了什么
git merge-base --is-ancestor <sha> HEAD && echo 在当前版本内           # 分类归属
```

本案考古直接命中：`3a54694d28` 修复过同名的重连竞争，同日稍晚的 `e2049910d5` 把关键 hunk 精确退回——同日 fix→revert 是回归的铁证形态。最后去社区对答案（见[修复版本与用户侧恢复](#fix-and-recovery)一节）：讨论区检索用通用搜索引擎加网页阅读器抓正文。

> zread 只索引从仓库代码生成的文档，**不索引 GitHub Discussions**；查社区讨论不要走它。

### 根因

两层独立故障叠加出同一症状，社区在 [#3102](https://github.com/deepseek-ai/deepseek-harness/discussions/3102) 里对两层的归纳与我们从源码独立推出的结论一致：

**第一层：resync 竞争（主因）。** 重连时序是——mux 流先打开，Host 用同一 rpcId 把仍待处理的 `question/requested` / `approval/requested` 帧重放给新代次，客户端重新铸造出 `PendingWait`；这些帧允许先于 `onConnected` 到达，因为就绪握手还要求 `host.describe` 成功（[connection.ts](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/client/connection/src/client/connection.ts#L123-L155) 先起泵、后握手）。随后 `onConnected` 驱动 `Session.resync()`，它无条件执行 `pending.clear()`（[session.ts](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/client/runtime/src/client/sessions/session.ts#L416-L437)），把刚重放进来的等待抹掉；该代次内不会再补发，Host 侧永远阻塞，前端没有可应答的面板。刷新之所以有效：新页面没有已实例化的 Session，重放帧进 manager 的预实例化缓冲，等 Session 建立后才回放，正好避开清除时机。上游历史：[3a54694d28](https://github.com/deepseek-ai/deepseek-harness/commit/3a54694d28) 曾把清除移到断连时刻修掉这个竞争，[e2049910d5](https://github.com/deepseek-ai/deepseek-harness/commit/e2049910d5) 把这些 hunk 退了回去，0.1.1-rc.2 携带的正是回退后的形态。

**第二层：静默半开连接（触发器）。** rc.2 的 WebSocket 下行没有 Ping 心跳，浏览器客户端又不允许在这两条 socket 上发应用数据，闲置的代理/NAT 可以让 socket 半开而双方无感。待处理的请求帧成为第一个牺牲品。上游在 [af562d3649](https://github.com/deepseek-ai/deepseek-harness/commit/af562d3649) 补了 30 秒 Ping（社区讨论 [#3020](https://github.com/deepseek-ai/deepseek-harness/discussions/3020)）。

复现要点（来自 #3102 中 panin1990 的实测）：`context.setOffline(true)` **不能**复现——它不关闭已建立的 WebSocket；必须真实关掉 socket：

```js
for (const s of sockets) if (s.readyState === WebSocket.OPEN) s.close()
```

帧轨迹：`question/requested` 正常渲染 → WS-CLOSE → WS-OPEN → 同 rpcId 重放 → 面板仍然缺失（重放之后 pending 才被清）。

### <a id="fix-and-recovery"></a>修复版本与用户侧恢复

- **0.1.2-alpha.2 起结构性消除。** panin1990 检查了 tag：`PendingWait`、`pendingQuestions`、`pending.clear()` 整个机制在新架构里不存在，交互状态移入 ui-session 包的 `PendingInteractionDomain`，`resync()` 只负责历史窗口，代次死亡时按投递中止过期等待——竞争在新设计下无法构造。之后的 0.1.2-rc 系（npm `next` tag）自然包含该修复。
- 升级前注意：0.1.2 是约 948 个文件的大迁移，自定义 client 插件可能需要适配新包结构。
- 卡住时的恢复（#3102 中 denial123789 的建议）：硬刷新一次，让重连重放拿回真实请求；刷新后仍不出现就取消本轮重新提问，不要伪造应答破坏审批语义。

### 教训

- **新鲜页面受控测试通过 ≠ 无 bug。** 要继续找触发前提；本案的前提是一次断连循环，而平台差异（桌面长连 vs 手机锁屏）决定了谁先撞见。
- **时序 bug 的证据藏在"两个时刻的差"里**：帧到达 vs DOM 出现、tool/call vs tool/result 的空洞。监听一对事件比翻代码先猜更快收敛。
- **git 考古先于复现尝试。** 同日 fix→revert 的历史直接把根因钉死；先跑 `git log --grep` 常常比搭复现环境便宜一个数量级。
- **症状指纹能省掉大半排查**：侧边栏圆点在而面板不在，说明两层状态错位，直接锁定清除时机问题。
- **独立定位后要去社区对答案。** 本案独立推出的根因与 #3102 逐字吻合，社区还补上了桌面/iPhone 双端实证和修复版本验证；反过来，社区也确认了"两层故障"的完整图景。
- **确认根因不等于授权修改。** 用户报障的语境下，动手改仓库前先复述方案取得同意；本案曾在未确认时开始移植修复，被叫停后回退。

## <a id="related-failure-family"></a>同症状的相邻故障

弹窗"时灵时不灵"还有两个独立根因，排查时注意区分：

- **[#3854](https://github.com/deepseek-ai/deepseek-harness/discussions/3854)（0.1.1-rc.1）**：ask_user_question 工具把轮次 AbortController 的 `signal: exec.signal` 转发进问题，等待期间用户在输入框发任何消息都会取消运行中的轮次，连带把 pending 问题以 `ASK_ABORTED` 静默杀掉——UI 从未渲染，工具结果直接报错。与重连竞争的区别：日志里能看到 `turn/end {kind:"aborted", reason:{kind:"user"}}` 且紧跟 ASK_ABORTED。
- **[#1471](https://github.com/deepseek-ai/deepseek-harness/discussions/1471)**：approval 应答者没有超时，弹窗丢失时工具调用无限挂起；报告者附了 fail-closed 超时的修复分支（未读正文，细节以讨论原文为准）。

## <a id="subagent-burst-429"></a>大批量并发 subagent 的部分失败与伪失败信号

> 2026-09-23 | `@deepseek-ai/dsh` 0.1.5-rc.3（Linux，spawn in-process 子代理，模型经 MiniMax Token Plan 订阅 key）| 批次落盘对账、zstdcat 子会话日志尸检、官方文档对照

### 症状

- 单条消息并发派发 N 个后台 subagent：N≤20 时全部正常返回、产物齐全；N=25 与 N=31 各有约三成子代理报 `Background subagent ... failed before it finished`。
- 被报失败的子代理分两类：**真失败**（产物文件缺失）与**伪失败**（产物已完整落盘、结果消息也已发给父会话，终态仍是 failed）。
- 失败率在 N=25 和 N=31 持平（约 30%），随并发数增加进入平台期。
- 父会话全程存活。

### 探测手段

先按批次做落盘对账（派发清单 vs 产物文件），把"报了 failed"和"真没产物"分成两个集合——两者只部分重叠，这一步直接暴露伪失败的存在。再对子会话日志做尸检：

```sh
# 每个子代理一个目录，日志是 zstd 压缩的 JSONL
zstdcat ~/.dsh/sessions/<workspace>--/<child-id>/session.v3.jsonl.zstd \
  | jq -c 'select(.type=="llm/retry" or .type=="turn/end")
    | {seq, type, code: .data.failure.code, kind: .data.reason.kind}'
```

- **真失败者**：`llm/retry` 连续 5 次 `RATE_LIMIT`（429 原文："已达到 Token Plan 速率限制：请升级 Token Plan 套餐或切换为按量付费 API 使用。(2062)"）→ `turn/end {kind:"error"}`。16 个真失败样本全部同一形态。
- **伪失败者**：时间线是 `write`（产物落盘）→ `send_message`（结果已发父会话）→ `RATE_LIMIT ×5` → `turn/end error`——工作已完成，终止在收尾生成最终回复的那一步。
- **对照组**（正常完成者）：`retries=0`、`turn/end completed`，一次瞬时 429 都没有。

> 落盘对账阶段曾把根因暂记为"harness 队列稳定性"；子会话日志尸检给出上游 429 后随即翻案。两步都做才闭环：对账发现"信号与产物解耦"，尸检回答"死因是什么"。

### 根因

**上游 provider 的账户级速率限制（吞吐墙），harness 调度本身工作正常。**

- dsh 的 agent-loop 按滚动池调度并行调用（同时 in-flight 默认至多 10 条，超出排队），N=31 时排队机制依然把每个子代理都送到了执行。
- 一次 burst 的全部子代理共享同一个上游账户的速率预算；每个子代理每步重发完整上下文（系统提示 + 各自读入的文件），峰值 token 吞吐在 N≈20 附近顶到订阅限额，恰在峰值窗口调 LLM 的子代理收到 429。
- 失败率平台期正是吞吐墙的指纹：限额约束的是每分钟 token 总量，超额瞬间谁在调用谁失败，加更多并发只会把撞墙比例抬高到一个稳定分数；并发槽位墙则会随 N 陡增。
- 官方口径对照（[MiniMax Token Plan 页](https://platform.minimax.io/subscribe/token-plan)）：并发指引 Plus 3–4 / Max 4–5 / Ultra 6–7 个 agent，工作日 15:00–17:30 高峰动态收紧，并明示对"超高并发自动化批量任务"做账户级速率调控；限流"通常约 1 分钟恢复"。实测 ~20 能全过靠三重缓冲：池宽 10 削峰、短命 burst 任务（每个只发几次请求）、深夜错峰。
- 重试链长度是第二重因素：`dsh-llm-retry` 整条退避链约 15 秒（5 次、逐次翻倍、单次上限 10s），上游限流窗口约 1 分钟——重试在恢复窗口到期前就耗尽。

### 修复与缓解

按性价比排序：

1. 把重试退避上限调到 60s+，让重试链覆盖限流恢复窗口——瞬时 429 大概率大部分自愈。
2. burst 规模控制在实测安全线内（本案环境 ≤20），高峰时段再收紧。
3. 给子代理任务做 prompt 瘦身：契约内联进任务描述，替代每个子代理各自读入同一份大文件（N 路 burst 下是 N 倍重复 token）。
4. 稳定的大规模并发换按量付费 key（429 报错原文即此建议）。

### 教训

- **落盘产物是 ground truth**：子代理终止在收尾步时，产物和结果消息都已送达，failed 信号与实际工作完成度解耦。评估批量 subagent 结果以对账产物为准。
- **失败率平台期 = 吞吐墙指纹**，槽位墙随 N 线性恶化——失败曲线的形态先于归因。
- subagent 大批量失败时，先查上游 provider 限流再看 harness 自身；子会话日志（zstdcat + 事件直方图）是最快的尸检通道。
- 官方并发数字要读口径：3–7 指持续运行的交互式 agent，短命 burst + 队列削峰 + 错峰能撑到更高，代价是贴着限流边缘运行。
- DSH 侧的机制事实（滚动池常量、重试策略形状、子会话日志通道）沉淀在 harness skill 的 dsh reference，与本案例按"机制 / 案例"分工。
- 给并发 burst 配 watchdog 时，由父会话主动刷新的心跳会把"忙"误报成"死"（本案 31 路时父会话忙于处理通知，心跳 121s 未刷新触发一次误报）；改盯会话日志文件的 mtime 这类非自愿信号——忙时它更新得更频繁。

## <a id="diagnostics-env-pitfalls"></a>诊断工具链的坑

排查这台机器时顺带撞上的环境故障，与 dsh 本身无关但会挡住验证路径：

- **pnpm 版本切换 ENOENT**：全局 pnpm 启动器尝试切换到 `.pnpm-store/v11/links/@/pnpm/<版本>/.../bin` 下不存在的 CLI，所有 pnpm 命令直接失败。需要跑仓库脚本时先修 pnpm store 或在配置里关掉版本管理，别误判成仓库坏了。
- **npm 缓存所有权**：`~/.npm/_cacache` 里有 root 属主文件时 npm 报 EACCES；`npm_config_cache=/tmp/<目录>` 重定向即可绕过。
