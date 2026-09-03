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

## <a id="diagnostics-env-pitfalls"></a>诊断工具链的坑

排查这台机器时顺带撞上的环境故障，与 dsh 本身无关但会挡住验证路径：

- **pnpm 版本切换 ENOENT**：全局 pnpm 启动器尝试切换到 `.pnpm-store/v11/links/@/pnpm/<版本>/.../bin` 下不存在的 CLI，所有 pnpm 命令直接失败。需要跑仓库脚本时先修 pnpm store 或在配置里关掉版本管理，别误判成仓库坏了。
- **npm 缓存所有权**：`~/.npm/_cacache` 里有 root 属主文件时 npm 报 EACCES；`npm_config_cache=/tmp/<目录>` 重定向即可绕过。
