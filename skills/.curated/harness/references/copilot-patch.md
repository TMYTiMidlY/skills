# Copilot CLI app.js 运行时补丁（bundle patch）

Copilot CLI 闭源、只发 minified bundle（为什么闭源、怎么读源码见 [copilot-cli.md「安装方式与看源码」](copilot-cli.md#安装方式与看源码)）。有几处行为**没有任何 settings / flag / env 能改**，只能直接改 `app.js` 打补丁：**重试太少**、**默认档位（effort ＋ context tier）回落**、**`web_fetch` SSRF 拦 fake-ip**。

**打补丁只改运行时真正跑的那份 `app.js`**——pkg cache 里的最高版本（`~/.cache/copilot/pkg/<platform>/<version>/app.js`），不是 npm 的 `node_modules` 种子、也不是 SEA 的 ELF（机制见 [copilot-cli.md「运行时到底跑哪份 app.js」](copilot-cli.md#运行时到底跑哪份-appjs打补丁改这份)）。

> ⚠️ **补丁是逆向产物、会随版本腐坏。** 本文的做法是「先跑脚本，跑成功就不用读细节；跑失败再对着当前 `app.js` 手动逆向那一个 patch」。所以下文既给脚本，也给每个 patch 的**改动意图 + 稳定字面量锚点**，供脚本失效时重建。锚点一律用跨版本不变的字面量（env 名 / 错误文案 / 配置键 / native 函数名），混淆符号名用正则反向引用捕获、**绝不硬编**。

---

## 一键脚本：`scripts/patch-copilot-cli.py`（先跑这个）

纯 Python stdlib、无第三方依赖（带 PEP723 头，`python3` 或 `uv run` 直接跑）。幂等、自动备份、`node --check` 失败即整档回滚、扫所有版本目录。**每个 patch 相互独立**：某个锚点在新版本失效只会单独 `SKIP` 并打印原因，不影响其余、也不破坏文件。

```bash
python3 <skills>/harness/scripts/patch-copilot-cli.py            # dry-run：只报告命中 / skip，不写
python3 <skills>/harness/scripts/patch-copilot-cli.py --apply    # 落盘（备份 + node --check + 失败回滚）
python3 <skills>/harness/scripts/patch-copilot-cli.py --revert   # 从 .tmy-patch.bak 恢复所有版本目录
```

覆盖 4 个 patch（各带独立幂等 marker）：

| patch 名 | marker | 效果 | 稳定锚点（手动逆向时也用它） |
|---|---|---|---|
| `retry-maxretries` | `tmy-retry` | 默认重试对象 `maxRetries` 5→10（GOAWAY / 瞬断更耐抗） | `maxRetries:5,defaultRetryDelaySeconds:5,backoffFactor:2`（默认配置对象，独特唯一） |
| `effort-default` | `tmy-max-effort` | 每个模型默认 reasoning effort → 它支持的最高档（picker `(default)` 顶格） | `("sweagent-capi",…).clientOptions?.defaultReasoningEffort??"medium"`（默认解析函数） |
| `webfetch-fakeip` | `tmy-webfetch-fakeip` | `web_fetch` SSRF 放行 fake-ip 段 `198.18/19`（mihomo fake-ip 下可用） | `.hookResolveAndValidateUrl(…)`（形态 B helper）；形态 A 用 `.networkIsBlockedIp` |
| `tiers-clearpoint` | `tmy-tiers-b` | typed `/model <id>` 落盘点别把 `effortLevel`/`contextTier` 清成默认，支持的模型保成最高 effort / `long_context` | `.effortLevel=void 0,<x>.contextTier=void 0` + 前方就近 `.find(a=>a.id===<id>)` 拿模型对象 |

**跑成功（全 `apply` 或 `already`）就不用往下读**。**开新会话才生效**（运行中的 `copilot` 已把 `app.js` 载进内存）；`copilot update` 拉的新版本目录是干净的，**重跑一次**即可（幂等）。

**实测（两台机器各 5 个版本目录 1.0.68→1.0.69）**：auto-update 后 pkg cache 里**正式版 `1.0.69` 与预发布版 `1.0.69-2` 并存**，loader 跑的是正式版 `1.0.69`（SemVer：release > prerelease，`copilot --version` 报 `1.0.69` 印证）——四个 patch 对它全命中、`--apply` 后 `node --check` 干净、每处替换语义正确、每 marker 唯一。旧版本目录 loader 不跑，锚点形态不同会各自 `SKIP`（如更早版本无 `long_context` 特性→`tiers` 跳过），不影响当前版本。⚠️ **别用位序数字比版本**：`1.0.69-2` 的数字元组 `(1,0,69,2)` 会被误判得比 `1.0.69` 的 `(1,0,69)` 高、和 loader 相反；脚本 `_vkey` 已按 SemVer 优先级排（正式版 > 其预发布），`--latest-only` 才和 loader 选的是同一份。这也是「auto-update 后要重跑」的典型场景：新掉的正式版目录是干净的，把上一版打好的补丁架空了。

**跑失败时**：脚本会打印是哪个 patch、什么原因（`anchor count=0` / 特性缺失 / 找不到模型对象）。按 patch 名到下面对应节，用「稳定锚点」重新 `view` 当前 `app.js` 定位、据「改什么」重写替换。**每次只修失效的那一个**。

**脚本不覆盖、需手动**的两项（形态在 1.0.69-2 已变 / 移除）见文末[未覆盖节](#未覆盖需手动逆向)。

---

## 通用套路（脚本内建，也是手动逆向的规矩）

1. **只改 `app.js`**（CLI 实际跑的那份），不动 `sdk/index.js`（programmatic SDK，CLI 不走它）。
2. **锚点选稳定字面量**：env 名 / 错误文案 / 配置键 / native 函数名（如 `maxRetries:5,defaultRetryDelaySeconds`、`sweagent-capi`、`modelsIsTieredTokenPrices`、`hookResolveAndValidateUrl`）这类跨版本不变的串。minified 符号名每版都变，**只能用正则反向引用捕获、绝不硬编**；含 `$` 的混淆名要用 `[\w$]` 而非 `\w` 匹配。
3. **先数命中数**：写回前确认锚点在当前 bundle 命中次数 = 预期（通常 1）。命中 0 或多于预期就停下重新逆向，别硬写。
4. **特性存在性守卫**：补丁若引用某 native 能力，先确认该字面量在 bundle 里存在；老版本没有该特性时**直接跳过**——注入引用不存在符号的代码会**运行时崩**，而 `node --check` 只查语法、查不出来。
5. **幂等 marker + 备份**：每个改动点带自定义 marker 注释（如 `/*tmy-xxx*/`），已含 marker 的跳过；写回前把原文件备份到同目录（脚本用 `app.js.tmy-patch.bak`），回滚直接 `cp` 回来。
6. **写回后 `node --check`**：语法坏了立刻用备份回滚。
7. **扫所有版本目录**：pkg cache 有多个版本目录（`$COPILOT_CACHE_HOME/pkg`、`$XDG_CACHE_HOME/copilot/pkg`、macOS `~/Library/Caches/copilot/pkg`、`$COPILOT_HOME/pkg`、`~/.copilot/pkg`；平台子目录形如 `linux-x64/<version>/app.js`），逐个打。
8. **只对新会话生效**：运行中的 `copilot` 已把 `app.js` 载入内存，补丁要**开新会话**才生效。
9. **auto-update 后要重跑**：CLI 默认 `autoUpdate: true`，新版本目录是干净的。判断哪些没打过：`grep -L '<marker>' ~/.cache/copilot/pkg/*/*/app.js`（列空＝都打过了）。旧备份 / 旧版本目录不自动回收，loader 只跑最高版本、留着无害，要清手动清。

---

## 补丁一 · 重试：transient API error 重试太少

### 症状与根因

网络抖动 / HTTP/2 GOAWAY / 模型上游瞬时不可用时，以此错误中断当前 turn：

```
✗ Execution failed: Error: Failed to get response from the AI model;
  retried 5 times (total retry wait time: 6.00 seconds)
  Last error: CAPIError: Connection error.
```

5 次重试才等 6 秒，对真实网络问题完全不够（跟 [github/copilot-cli#2421](https://github.com/github/copilot-cli/issues/2421) 等一堆 issue 同类）。**没有任何 `settings.json` / flag / env 能改**——实测过完整 `cli-config-dir-reference` 和 `cli-command-reference`，只有 `--timeout`（作用于工具调用、不是模型 API 请求）和 `continueOnAutoMode`（rate-limit 切 auto、跟连接错误无关）。只能 patch。

### 改什么

**重试次数**：默认重试配置对象里 `maxRetries` 5→10。稳定锚点是那个默认对象字面量 `{maxRetries:5,defaultRetryDelaySeconds:5,backoffFactor:2,…}`（唯一，其它 `{maxRetries:2}`/`{maxRetries:0}` 是 MCP registry policy 专用、不带这个组合，天然不误伤）。改成 `maxRetries:10` 即可。

> 早期版本还改过「非-API 错误退避的 4 秒下限」（`retryAfter*(0.8+random*0.4)` 套 `Math.max(…,4)`），但**该 jitter 公式在 1.0.69-2 已不在 bundle**（`Math.random` 只剩无关用途），故脚本不做、也不必做——`maxRetries` 翻倍已是主体。若未来版本重新出现该公式，锚点用 `.8+Math.random()*.4` 定位、周围混淆名反向引用捕获。

### 验证

`grep -l tmy-retry ~/.cache/copilot/pkg/*/*/app.js` 确认已打；开新会话，遇瞬断应重试更久才放弃。

---

## 补丁二 · 默认档位：effort ＋ context tier

**这俩是同一类问题**：typed `/model <id>` 切模型时，用**同一行**把 `effortLevel` 和 `contextTier` 一起清空（`<state>.effortLevel=void 0,<state>.contextTier=void 0`，落盘 + 本会话内存都清）→ 两档位一起回落该模型「默认档」。想让它们默认停在想要的档（effort→模型支持的最高档、context→`long_context`），纯改 settings 都扛不住 typed `/model`，只能 patch。（曾错误以为「effort 要 hack、context 改 settings 就够」，是假的不对称——两者机制同构。）

### 机制（两档位同构）

- **优先级（都一样）**：命令行开关（`--effort <none/low/medium/high/xhigh/max>`＝`--reasoning-effort`；`--context <default/long_context>`，均会话级不落盘）> `settings.json`（`effortLevel` / `contextTier`，合法持久键；`contextTier` 的 `inherit` 只给子代理）> 内置默认。model 另有 `COPILOT_MODEL` env，但 **effort / context 都没有对应 env**。持久默认只在全局 `~/.copilot/settings.json`（无目录级 settings，`$COPILOT_HOME` 可整体挪位）；TUI 里选档写回这里，故「上次选择」＝「默认」。
- **每个模型的「默认档」来自 bundle 静态解析、用户不可配**：
  - *effort*：静态表（源标签 `"sweagent-capi"`）的 `clientOptions.defaultReasoningEffort`，按 model→family→vendor 匹配、缺省硬回落 `"medium"`，再过 native 用该模型 `supportedReasoningEfforts` 校验。这既是 picker `(default)` 标签来源，也是 typed `/model` 回落目标。
  - *context*：`long_context`（分层定价大窗口档，如 gpt-5.x 的 1.1M）**只在该模型 `billing.token_prices` 带 `long_context` 时才存在**；不支持的模型只有 `default` 一档。
- **两处被 typed `/model` 清空 / 重置**（补丁的靶）：
  - **清空点**：typed `/model <id>` 执行时那行 `effortLevel=void 0,contextTier=void 0`（落盘清空 settings + 本会话内存）。
  - **setModel 重置**：native `setModel` 的 switch 调用少传 tier 参 → 把本会话内存 state 重置回 default。⚠️ **1.0.69-2 起该 setModel 已改为转发当前 tier**（`<fn>(U,void 0,{…contextTier:<当前值>})`），形态与旧版不同，见[未覆盖节](#未覆盖需手动逆向)。
  - 所以「先用无参 `/model` 两步选择器选好档」扛不住之后任何一次 typed `/model` 切模型（picker 路径传满参、不清；typed 路径走清空）。
- **⚠️ 交互 TUI 无视 `--context` 开关，只认 `settings.json` 的 `contextTier`**（实测；无头 `-p` 才认开关）。根因：交互 App 有个挂载 effect 只从盘重灌 tier（启动时 runtime 没带 tier → 落到 `settings.contextTier`）。**所以交互启动要长上下文＝改 `settings.json` `contextTier: long_context`，别指望 `--context`。**
- **context 的完整修复 = 两件套**：① `settings.json` `contextTier: long_context`（管交互启动即长上下文）＋ ② 清空点补丁（管 typed `/model` 切换后不掉档、settings 不被抹）。缺 ② 实测：启动 1M，但 typed `/model` 切走再切回 → `/context` 从 1M 掉回 264k，且 `settings.json` 的 `contextTier` 被物理删掉。

**实测四象限（opus-4.8；上下文窗口取 `/context` 面板，prompt 上限取 resolved `max_prompt_tokens`）**：

| 场景 | 上下文窗口 | prompt 上限 |
|---|---|---|
| 无头 `-p` ＋ `--context default` | 264k | 200k |
| 无头 `-p` ＋ `--context long_context` | **1,000,000** ✓ | 936,000 |
| 交互 TUI ＋ `--context long_context` | 264k ✗ | 200k |
| 交互 TUI ＋ settings `contextTier=long_context`（不带开关） | **1,000,000** ✓ | 936,000 |

### 改什么（两个作用面，effort / context 同理）

档位有**两个作用面**，脚本按诉求覆盖了其中稳的部分：

- **作用面 A「默认解析」**（管 picker `(default)` 标签 + 启动 / 解析回落）：改读「每个模型默认档」的解析函数，让它返回**该模型支持的最高档**而非静态默认。
  - *effort*（脚本 `effort-default` 做的就是这面）：解析函数用 `("sweagent-capi",…).clientOptions?.defaultReasoningEffort??"medium"` 这段独特字面量定位；改成先取该模型 `supportedReasoningEfforts` 里最高（`max>xhigh>high>medium>low`）、取不到回落原逻辑。同一模块内有现成的 `("sweagent-capi",…)` 取模型描述符，复用它拿 `supportedReasoningEfforts`。
  - *context*：理论对称，但 stock 里 context 默认本就是 `default`、没有独立的「默认取 long_context」解析点，故脚本不做 context 的 A 面。
- **作用面 B「typed `/model` 清空点」**（管切模型后不掉档，**effort/context 共享同一处代码**；脚本 `tiers-clearpoint` 做这面）：
  - 用稳定属性名串 `effortLevel=void 0,contextTier=void 0` 定位（这是 typed `/model <id>` 落盘写 settings 前那行）。**前方就近有 `<s>=<r>.find(a=>a.id===<model-id>)`**——拿到模型对象喂守卫。把末尾两个 `=void 0` 分别改成守卫三目：effort→最高档、context→`long_context`（支持时）。
  - 该锚点的**三目形式** `<l>.model=<n>===<u>?void 0:<n>,…` 天然只命中「实名 model」分支、跳过 `/model auto` 分支（auto 无固定模型 / 无 long_context，本就该回默认）。
- **守卫（不支持的模型必须回落、不能崩）**：
  - *effort*：`<mv>.supportedReasoningEfforts` 里按 `["max","xhigh","high","medium","low"]` 取第一个命中的，空则 `void 0`（回落默认）。
  - *context*：照抄 native 能力判定——`<mv>.billing.token_prices` 存在且 `<alias>.modelsIsTieredTokenPrices(JSON.stringify(...))` 为真且 `"long_context" in …`，否则 `void 0`。模块别名（`<alias>`，形如 `v`）从 `<x>.modelsIsTieredTokenPrices` 探测、别硬编。
  - **⚠️ 特性前置守卫**（《通用套路》第 4 条的实例）：`long_context` 分层定价是较新特性、靠 native `modelsIsTieredTokenPrices` 判定；老版本没有这个 native 函数，注入引用它的守卫会**运行时崩**、而 `node --check` 查不出。所以打 context 前必须先确认 bundle 里有 `modelsIsTieredTokenPrices` 字面量，没有就跳过（脚本 `tiers-clearpoint` 已内建此守卫：1.0.67 无特性→自动 SKIP）。真踩过：放松锚点后多版本全匹配 + `node --check` 全过，老版本一敲 `/model` 就炸。

### 验证：用真 PTY 驱动交互式 TUI

改 bundle 后光 `node --check` + `--version` 不够——得验 typed `/model` 真落到目标档。这类「要驱动交互式 TUI、按键、读屏幕」的验证，用 Python stdlib **`pty.fork()`** 起真 PTY（不必装 `pexpect`）：

- 子进程 `os.execvp("copilot",…)` 拿到**真控制终端**；`ioctl(fd, TIOCSWINSZ, …)` 设窗口、`TERM=xterm-256color`。
- master fd：`select.select([fd])` 读＝看屏幕；`os.write(fd,ch)` ＝敲键盘（`\r` 提交、`\x03` 退出）。
- **逐字符输入（~60ms/字符）**：一次性灌整行会和 TUI 自动补全竞争、截断命令——踩过。
- 断言：从磁盘读 `settings.json` 看 `contextTier` / `effortLevel`；正则剥 ANSI 后 grep 稳定串（`Model changed from`、footer 的 `1.1M context`）。**必须换一个和当前不同、且支持目标档的模型**（如 gpt-5.4）强制真切换——切同款＝没切，区分不出「hack 没生效」vs「本就同档」；`-p "/model"` 一次性喂会走另一条「Already using」路径（不在 app.js 里），测不到。

**实测结论**：支持的模型（gpt-5.4 / 5.5 / opus-4.8）→ typed `/model` 后 footer 显 `(1M context)`/`(1.1M context)` + settings 落 `long_context`；不支持的（gpt-5-mini）→ 守卫回落 default、不崩。opus-4.8 切走再切回，`/context` 从补丁前 264k 变 **1000k**、`settings.json` `contextTier` 不再被抹。

---

## 补丁三 · `web_fetch` SSRF 守卫拦 fake-ip（定点放行）

### 现象

Mihomo 开 `enhanced-mode: fake-ip` 时，`web_fetch` 抓**任何**外网域名都报：

```
WebFetchBlockedUrlError: ... resolves to blocked address 198.18.x.x.
URLs must not target loopback, private, or link-local addresses.
```

不是网络不通——是 `web_fetch` **发请求前的一道安全预检**撞上了 fake-ip。对照组：同环境 `curl` 抓同一 URL 正常（`curl` 没这道检查、且会把域名交给代理或经 TUN 走 fake-ip）。

### 机制：SSRF 守卫在联网前先判黑

SSRF（Server-Side Request Forgery，服务端请求伪造——诱导服务端去请求它本不该碰的内网 / 云元数据地址如 `169.254.169.254`、`127.x`、内网面板）。`web_fetch` 的防线是：**先用系统 DNS 解析目标主机名，再把每个解析到的 IP 逐个判黑，命中就在发请求前抛错**。fake-ip 模式下 Mihomo 给每个域名都回 `198.18.x.x`（RFC2544 基准测试保留段），**必落黑名单** → 每个外网域名都被拒。**这是 fake-ip 专属坑**：切 `redir-host`（回真实公网 IP）就不触发；原理见 `network` skill 的 mihomo fake-ip 章节。

### 没有可用的配置开关

唯一相关 env 是 `COPILOT_WEB_FETCH_ALLOW_LOCALHOST=1`，但它**只放行 `127.x` / `::1`**，fake-ip 段不在其列；也没有 `allowPrivate` 之类。所以想让 fake-ip 下的 `web_fetch` 可用**只能改源码**（curl 只是并行手段，不能让 `web_fetch` 本身可用）。

### 关键：判黑逻辑正在从 JS 迁往 native（移动靶）

同一个检查在版本间**换过形态**，patch 前先 grep `networkIsBlockedIp` 是否还在 JS 里辨形：

| 形态 | JS 里长什么样 | 可 patch 点 |
|---|---|---|
| **A · JS 判黑** | 一个小函数 `return <native>.networkIsBlockedIp(<ip>)`，被 resolve+validate helper 调用 | 直接包 `networkIsBlockedIp` |
| **B · native 判黑** | helper 只剩 `return(await <native>.hookResolveAndValidateUrl(t,e.allowLocalhost===!0,e.urlLabel)).map(…)`，**JS 里已无 `networkIsBlockedIp`、连 `node:dns` 都不 import** | 只能重写该 helper 自己解析 |

GitHub 把整套「解析 + 判黑」搬进 Rust 绑定了。后果：**每次 `copilot update` 都可能让 patch 失效**、甚至要重新逆向定位（实测 1.0.66→1.0.69 期间 4 次自更新把旧 patch 全打空）。**本机 5 个版本目录（1.0.67→1.0.69-2）实测全是形态 B**——脚本 `webfetch-fakeip` 针对形态 B 的 helper。

### 改什么（定点放行，最小爆炸半径）

只放行 fake-ip 池 `198.18.0.0/15`（`198.18.x` / `198.19.x`，本就没有合法内网服务），其余仍交给原判黑——`127/10/192.168/169.254/::1/云元数据`照旧全拦，比「让判黑恒 `false`」安全得多：

- **形态 A**：把对 `networkIsBlockedIp(ip)` 的调用包成「命中 `/^198\.1[89]\./` 则返回 `false`（不拦）、否则走原调用」。
- **形态 B**（脚本做的）：重写那个 helper——先自己 `await import("node:dns/promises")` 解析主机名，**全部**解析成 fake-ip 段（`/^198\.1[89]\./`）时直接返回地址（绕过 native）、否则回落 `await <native>.hookResolveAndValidateUrl(...)`（保留真实内网防护）。锚点用 `.hookResolveAndValidateUrl(t,e.allowLocalhost===!0,e.urlLabel)` 整段定位、混淆名反向引用捕获。

### 验证

patch 后**开新会话**让它 `web_fetch` 任意外网 URL；若错误从 `blocked address` 变成连接 / 代理类错误，说明判黑已绕过、但底层 fetch 对 pinned fake-ip 的出站路径有问题（查 `proxyEnv` / `pinnedAddresses` 与 TUN 直连）。

---

## 未覆盖、需手动逆向

脚本刻意不碰的两处（1.0.69-2 形态已变 / 移除，硬做易崩或无收益）。需要时对着当前 `app.js` 手动逆向：

- **retry 非-API 错误的 4 秒退避下限**：旧版本 `retryAfter*(0.8+Math.random()*0.4)` 套 `Math.max(…,4)`。**1.0.69-2 已无此 jitter 公式**（`Math.random` 只剩 brace-expansion 占位、temp 文件名等无关用途）。`maxRetries` 翻倍已覆盖主要收益；若未来版本重现该公式，锚点用 `.8+Math.random()*.4`。
- **默认档位「作用面 B 的本会话内存半」（setModel）**：旧版本 setModel 的 switch 调用「少传 tier 参 → 重置 default」，补第 4 参即可。但 **1.0.69-2 起该调用已改为 `<fn>(U,void 0,{model:…,effort:…,contextTier:<当前 state 值>})`——已经转发当前 tier**，不再是「缺参重置」。这意味着：清空点补丁（`tiers-clearpoint`，脚本已做）保住 settings 落盘半 → 下次启动正确；本会话内存半是否还需要补，取决于该 state 值怎么流转，得逐版本核 `setModel` 上下文。若实测**同一会话内**切模型仍瞬时掉档，再手动逆向 `setModel:async` 附近、把它读的 tier state 源头也守卫住。

**手动逆向工作流**（脚本报某个 patch `SKIP` 时）：① 按上表「稳定锚点」`grep`/`view` 当前 `app.js` 确认字面量还在、看它现在长什么样；② 用 node 切片（`s.indexOf(锚点)` 前后各切一段、`replace(/\s+/g," ")` 压平）读清结构；③ 数命中数（须唯一）；④ 按「改什么」写替换、混淆名反向引用捕获；⑤ `node --check`；⑥ 按上面的四象限 / PTY / `web_fetch` 各自的验证法确认真生效。改完把新锚点同步回脚本对应的 `p_*` 函数。
