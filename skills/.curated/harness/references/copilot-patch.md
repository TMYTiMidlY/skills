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

覆盖 5 个 patch（各带独立幂等 marker）：

| patch 名 | marker | 效果 | 稳定锚点（手动逆向时也用它） |
|---|---|---|---|
| `retry-maxretries` | `tmy-retry` | 默认重试对象 `maxRetries` 5→10（GOAWAY / 瞬断更耐抗） | `maxRetries:5,defaultRetryDelaySeconds:5,backoffFactor:2`（默认配置对象，独特唯一） |
| `effort-default` | `tmy-max-effort` | 每个模型默认 reasoning effort → 它支持的最高档（picker `(default)` 顶格） | `("sweagent-capi",…).clientOptions?.defaultReasoningEffort??"medium"`（默认解析函数） |
| `webfetch-fakeip` | `tmy-webfetch-fakeip` | `web_fetch` SSRF 放行 fake-ip 段 `198.18/19`（mihomo fake-ip 下可用） | `.hookResolveAndValidateUrl(…)`（形态 B helper）；形态 A 用 `.networkIsBlockedIp` |
| `tiers-clearpoint` | `tmy-tiers-b` | **context tier 落盘半**：typed `/model <id>` 落盘点别把 `effortLevel`/`contextTier` 清成默认，支持的模型保成最高 effort / `long_context`（下次启动不掉档、settings 不被抹） | `.effortLevel=void 0,<x>.contextTier=void 0` + 前方就近 `.find(a=>a.id===<id>)` 拿模型对象 |
| `tiers-live` | `tmy-tiers-live` | **context tier 运行时半**：`setModel` 那次 live 切换调用把 tier 位从 `void 0` 换成守卫 → **本会话**切模型后即时长上下文（补 clearpoint 只管落盘、live 窗口仍掉 264k 的洞） | `setModel:async(<id>,…)=>{let <lst>=…?.type==="success"?…list` + 就近 `<fn>(<id>,void 0,{model,effort,contextTier},void 0,…)` 的**第 4 位** `void 0` |

**跑成功（全 `apply` 或 `already`）就不用往下读**。**开新会话才生效**（运行中的 `copilot` 已把 `app.js` 载进内存）；`copilot update` 拉的新版本目录是干净的，**重跑一次**即可（幂等）。

**实测（两台机器 1.0.70-0）**：五个 patch 全命中、`--apply` 后 `node --check` 干净、每处替换语义正确、每 marker 唯一。旧版本目录 loader 不跑，锚点形态不同会各自 `SKIP`（如更早版本无 `long_context` 特性→两个 `tiers` 跳过；2 参 `setModel` 旧形态→`tiers-live` 跳过），不影响当前版本。⚠️ **别用位序数字比版本**：正式版 `1.0.69` 与预发布 `1.0.69-2` 并存时，`1.0.69-2` 的数字元组 `(1,0,69,2)` 会被误判得比 `1.0.69` 的 `(1,0,69)` 高、和 loader（SemVer：release > prerelease）相反；脚本 `_vkey` 已按 SemVer 优先级排，`--latest-only` 才和 loader 选的是同一份。这也是「auto-update 后要重跑」的典型场景：新掉的正式版目录是干净的，把上一版打好的补丁架空了。

**跑失败时**：脚本会打印是哪个 patch、什么原因（`anchor count=0` / 特性缺失 / 找不到模型对象）。按 patch 名到下面对应节，用「稳定锚点」重新 `view` 当前 `app.js` 定位、据「改什么」重写替换。**每次只修失效的那一个**。

**脚本不覆盖、需手动**的一项（retry 非-API 退避下限，形态已移除）见文末[未覆盖节](#未覆盖需手动逆向)。

---

## 自动重打：`copilot-auto-patch` systemd --user 服务

手动记着「auto-update 后重跑脚本」太容易忘——CLI 默认 `autoUpdate: true`，新掉的版本目录是干净的，会把上一版打好的补丁架空（见上面 `_vkey` 那段的实测场景）。用一个 systemd --user 服务盯着 pkg cache、自动重打，就不用惦记了。本机 + AgWorkstation 两台都装了这套（WSL2 + systemd --user + linger 已开）。

**三个 unit**（都在 `~/.config/systemd/user/`，脚本副本在 `~/.local/share/copilot-auto-patch/patch-copilot-cli.py`）：

| unit | 作用 |
|---|---|
| `copilot-auto-patch.service` | oneshot，跑 `python3 <副本> --apply --latest-only --strict`；`ExecStartPre=/bin/sleep 5` 等下载写完；env 只给 `PATH=/usr/bin:/bin`，node 靠脚本 `find_node()` 自己找（nvm/fnm 都行） |
| `copilot-auto-patch.path` | `PathModified=%h/.cache/copilot/pkg/linux-x64`，新版本目录一落就触发 service（inotify，近实时） |
| `copilot-auto-patch.timer` | `OnStartupSec=1min` + `OnUnitActiveSec=30min` 兜底：开机补一次 + 周期重扫（补下载竞态 / 关机期间的更新） |

**为什么用 `--latest-only --strict`**：`--latest-only`（配合修好的 `_vkey`）只补 loader 实际会跑的最高版本；`--strict` 让「锚点在新版本失效 / `node --check` 失败」直接以非零退出 → **单元 `failed` 进 journal**，这样"补丁腐坏"不会静默，能被 agent 发现并逆向修。

**排障**（看到自动 patch 没生效时）：
```bash
systemctl --user status copilot-auto-patch.service      # 是否 failed
journalctl --user -u copilot-auto-patch.service         # 哪个 patch SKIP / 为什么
systemctl --user list-timers copilot-auto-patch.timer   # 下次兜底重扫时间
systemctl --user start copilot-auto-patch.service       # 手动触发一次
```
`failed` 就按脚本打印的 patch 名，到本文对应节用「稳定锚点」重新逆向那一个。

**维护坑**：
- 服务跑的是脚本**副本**，不是 skill 里的原件。**改了 `scripts/patch-copilot-cli.py` 后要重新 `cp` 到两台的 `~/.local/share/copilot-auto-patch/`**，否则服务还在跑旧版。
- 平台目录名 `linux-x64` 写死在 `.path` 里；换架构（如 arm64）要改 `PathModified`。
- 只对**新会话**生效（运行中的 `copilot` 已把 app.js 载进内存）——服务只保证「下次开的会话是打好补丁的」。

**新机器复现**（一次性）：把 `patch-copilot-cli.py` 放到 `~/.local/share/copilot-auto-patch/`，三个 unit 放到 `~/.config/systemd/user/`（unit 用 `%h` 无需改路径），然后：
```bash
systemctl --user daemon-reload
systemctl --user enable --now copilot-auto-patch.path copilot-auto-patch.timer
loginctl enable-linger "$USER"   # 没开 linger 的话，让 user manager 开机自起
```

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
- **两处被 typed `/model` 清空 / 重置**（补丁的靶，**两处现在都补**）：
  - **清空点（落盘半）**：typed `/model <id>` 落盘写 settings 前那行 `effortLevel=void 0,contextTier=void 0`（清空 settings）。→ `tiers-clearpoint` 补。
  - **setModel（运行时半）**：`setModel:async` 里那次 live 切换调用 `<fn>(<id>,void 0,{model,effort,contextTier},void 0,<ee>)` 把 tier 位（**第 4 个位置参**）传成 `void 0` → 内部 `fe.model.switchTo({…,contextTier:第4参})` 把**本会话 live 窗口**重置回默认档。→ `tiers-live` 补（把那个 `void 0` 换成守卫；picker 路径本来就传满第 4 参、不动）。
  - 所以「先用无参 `/model` 两步选择器选好档」扛不住之后任何一次 typed `/model` 切模型（picker 路径两处都传满参、不清；typed 路径两处都靠补丁兜）。
- **⚠️ 交互 TUI 无视 `--context` 开关，只认 `settings.json` 的 `contextTier`**（实测；无头 `-p` 才认开关）。根因：交互 App 有个挂载 effect 只从盘重灌 tier（启动时 runtime 没带 tier → 落到 `settings.contextTier`）。**所以交互启动要长上下文＝改 `settings.json` `contextTier: long_context`，别指望 `--context`。**
- **context 的完整修复 = 三件套**：① `settings.json` `contextTier: long_context`（管交互**启动**即长上下文）＋ ② 清空点补丁 `tiers-clearpoint`（管 typed `/model` **落盘**不被抹、下次启动对）＋ ③ setModel 补丁 `tiers-live`（管 typed `/model` 后**本会话 live 窗口**即时长上下文）。缺 ③ 实测（1.0.70-0，opus-4.8）：typed `/model claude-opus-4.8` 后 `settings.json` 落了 `long_context`、但 `/context` live 窗口仍 **264k**；补 ③ 后 live 变 **1000k**。（这三件套的历史：② + ③ 就是早年 `patch-copilot-cli-longcontext.py` 的 PATCH#1 + PATCH#2；重构时误以为「1.0.69-2 起 setModel 已转发当前 tier」把 ③ 删了，1.0.70-0 实测证伪、遂补回。）

**实测四象限（opus-4.8；上下文窗口取 `/context` 面板，prompt 上限取 resolved `max_prompt_tokens`）**：

| 场景 | 上下文窗口 | prompt 上限 |
|---|---|---|
| 无头 `-p` ＋ `--context default` | 264k | 200k |
| 无头 `-p` ＋ `--context long_context` | **1,000,000** ✓ | 936,000 |
| 交互 TUI 启动 ＋ `--context long_context` 开关 | 264k ✗ | 200k |
| 交互 TUI 启动 ＋ settings `contextTier=long_context`（不带开关） | **1,000,000** ✓ | 936,000 |

**会话内 typed `/model` 的 live 窗口（1.0.70-0 实测，PTY 驱动真 TUI + `/context`）**：

| 场景 | live `/context` 窗口 | settings 落盘 |
|---|---|---|
| 只补 `tiers-clearpoint`（落盘半）：`/model claude-opus-4.8` | 264k ✗（掉档） | `long_context` ✓ |
| 加 `tiers-live`（运行时半）：`/model claude-opus-4.8` | **1,000,000** ✓ | `long_context` ✓ |
| 加 `tiers-live`：`/model gpt-5-mini`（不支持 long） | 192k（默认，守卫回落、不崩） | 无 `contextTier` ✓ |

### 改什么（两个作用面，effort / context 同理）

档位有**两个作用面**，脚本按诉求覆盖了其中稳的部分：

- **作用面 A「默认解析」**（管 picker `(default)` 标签 + 启动 / 解析回落）：改读「每个模型默认档」的解析函数，让它返回**该模型支持的最高档**而非静态默认。
  - *effort*（脚本 `effort-default` 做的就是这面）：解析函数用 `("sweagent-capi",…).clientOptions?.defaultReasoningEffort??"medium"` 这段独特字面量定位；改成先取该模型 `supportedReasoningEfforts` 里最高（`max>xhigh>high>medium>low`）、取不到回落原逻辑。同一模块内有现成的 `("sweagent-capi",…)` 取模型描述符，复用它拿 `supportedReasoningEfforts`。
  - *context*：理论对称，但 stock 里 context 默认本就是 `default`、没有独立的「默认取 long_context」解析点，故脚本不做 context 的 A 面。
- **作用面 B「typed `/model` 切换点」**（管切模型后不掉档）——**两处代码、两个补丁**：
  - **B-落盘（`tiers-clearpoint`，effort/context 共享）**：用稳定属性名串 `effortLevel=void 0,contextTier=void 0` 定位（typed `/model <id>` 落盘写 settings 前那行）。**前方就近有 `<s>=<r>.find(a=>a.id===<model-id>)`**——拿到模型对象喂守卫。把末尾两个 `=void 0` 分别改成守卫三目：effort→最高档、context→`long_context`（支持时）。该锚点的**三目形式** `<l>.model=<n>===<u>?void 0:<n>,…` 天然只命中「实名 model」分支、跳过 `/model auto`（auto 无固定模型 / 无 long_context）。
  - **B-运行时（`tiers-live`，只 context）**：`setModel:async(<id>,<ie>,<ee>)=>{let <lst>=<mn>?.type==="success"?<mn>.list:void 0;` 拿到 id 与模型列表 `<lst>`；就近的 live 切换调用 `<fn>(<id>,void 0,{model,effort,contextTier},void 0,<ee>)` 的**第 4 个位置参**（`void 0`）就是喂给内部 `fe.model.switchTo({…,contextTier:第4参})` 的 live tier。把这个 `void 0` 换成守卫 IIFE：`(()=>{let _m=(<lst>||[]).find(_x=>_x&&_x.id===<id>);return <守卫(_m)>?"long_context":void 0})()`。picker 路径传的是非 `void 0` 的第 4 参、不匹配本锚点（要求 2nd＝`void 0` 且 4th＝`void 0`），天然不误伤。
- **守卫（不支持的模型必须回落、不能崩）**：
  - *effort*：`<mv>.supportedReasoningEfforts` 里按 `["max","xhigh","high","medium","low"]` 取第一个命中的，空则 `void 0`（回落默认）。
  - *context*（B-落盘 / B-运行时共用同一判定）：照抄 native 能力判定——`<mv>.billing.token_prices` 存在且 `<alias>.modelsIsTieredTokenPrices(JSON.stringify(...))` 为真且 `"long_context" in …`，否则 `void 0`。模块别名（`<alias>`，1.0.70-0 里是 `S`）从 `<x>.modelsIsTieredTokenPrices` 探测、别硬编。全 `&&` 短路 + IIFE 局部变量，任何模型对象形态都不会抛、最坏回 `void 0`。
  - **⚠️ 特性前置守卫**（《通用套路》第 4 条的实例）：`long_context` 分层定价是较新特性、靠 native `modelsIsTieredTokenPrices` 判定；老版本没有这个 native 函数，注入引用它的守卫会**运行时崩**、而 `node --check` 查不出。所以打 context 前必须先确认 bundle 里有 `modelsIsTieredTokenPrices` 字面量，没有就跳过（脚本两个 `tiers` 都内建此守卫：无特性→自动 SKIP）。真踩过：放松锚点后多版本全匹配 + `node --check` 全过，老版本一敲 `/model` 就炸。

### 验证：用真 PTY 驱动交互式 TUI

改 bundle 后光 `node --check` + `--version` 不够——得验 typed `/model` 真落到目标档。这类「要驱动交互式 TUI、按键、读屏幕」的验证，用 Python stdlib **`pty.fork()`** 起真 PTY（不必装 `pexpect`）：

- 子进程 `os.execvp("copilot",…)` 拿到**真控制终端**；`ioctl(fd, TIOCSWINSZ, …)` 设窗口、`TERM=xterm-256color`。
- master fd：`select.select([fd])` 读＝看屏幕；`os.write(fd,ch)` ＝敲键盘（`\r` 提交、`\x03` 退出）。
- **逐字符输入（~60ms/字符）**：一次性灌整行会和 TUI 自动补全竞争、截断命令——踩过。
- **启动先应答「Do you trust the files in this folder?」信任框**（在 `/tmp` 等新目录会弹）：检测到就先发 `1\r`，否则你的 `/model` 会被信任框吃掉——踩过。
- **断言分两层，缺一不可**：① 从磁盘读 `settings.json` 看 `contextTier`/`effortLevel`（落盘半）；② **`/model` 后再发 `/context` 读 live 面板的窗口数**（`opus-4.8 · 70k/1000k tokens` 才是真 1M，264k＝掉档）。**只看 ① 会被 `tiers-clearpoint` 骗过**——它把 settings 写成 `long_context` 了，但没 `tiers-live` 时 live 窗口仍 264k。正则剥 ANSI 后 grep `Model changed from` / `… · Nk/Mk tokens`。**必须换一个和当前不同、且支持目标档的模型**（如 gpt-5.4）强制真切换；`-p "/model"` 一次性喂会走另一条「Already using」路径（不在 app.js 里），测不到。
- **零干扰隔离法**（别动用户真环境）：`COPILOT_HOME=<scratch>` 指到只含小文件（`config.json` 带鉴权 + 自造 `settings.json`）的 scratch 目录（3.4G 的 `logs/`、`session-state/` 不用拷）；要测「补丁版 app.js」而不碰真 pkg cache，就 `cp -a` 版本目录到 `COPILOT_CACHE_HOME=<scratch>/pkg/<platform>/`、目录名改成极高版本号（如 `9.9.9-0`）让 loader 必选它、补丁只打这份。CLI 认 `COPILOT_CACHE_HOME`（实测：只有 scratch 那份带 `tmy-tiers-live` → live 出 1M，反证 CLI 跑的就是它）。

**实测结论（1.0.70-0）**：支持的模型（gpt-5.4 / 5.5 / opus-4.8）→ typed `/model` 后 `settings.json` 落 `long_context`（`tiers-clearpoint`）**且** live `/context` 出 `1000k`/`1.1M`（`tiers-live`）；不支持的（gpt-5-mini，192k）→ 两半守卫都回落 default、不崩。**关键教训**：`tiers-clearpoint` 单独存在时 `settings.json` 看着对（`long_context`）、但 live 窗口仍 264k——所以补丁验证一定要读 live `/context`、不能只读 settings。

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

脚本刻意不碰的一处（当前形态已变 / 移除，硬做易崩或无收益）。需要时对着当前 `app.js` 手动逆向：

- **retry 非-API 错误的 4 秒退避下限**：旧版本 `retryAfter*(0.8+Math.random()*0.4)` 套 `Math.max(…,4)`。**当前版本已无此 jitter 公式**（`Math.random` 只剩 brace-expansion 占位、temp 文件名等无关用途）。`maxRetries` 翻倍已覆盖主要收益；若未来版本重现该公式，锚点用 `.8+Math.random()*.4`。

> 📌 **曾经未覆盖、现已补回**：context tier 的「本会话内存半 / setModel」。重构时误判「1.0.69-2 起 setModel 已转发当前 tier、无需补」，1.0.70-0 实测证伪（typed `/model` 后 live `/context` 掉回 264k），已由 `tiers-live`（作用面 B-运行时）补回，见上文补丁二。教训：**「setModel 已转发 tier」不能只看调用点带没带 `contextTier`——得看那个 tier 值的来源；1.0.70-0 里 live 切换认的是第 4 个位置参（`void 0`），不认对象里的 `contextTier`。**

**手动逆向工作流**（脚本报某个 patch `SKIP` 时）：① 按上表「稳定锚点」`grep`/`view` 当前 `app.js` 确认字面量还在、看它现在长什么样；② 用 node 切片（`s.indexOf(锚点)` 前后各切一段、`replace(/\s+/g," ")` 压平）读清结构；③ 数命中数（须唯一）；④ 按「改什么」写替换、混淆名反向引用捕获；⑤ `node --check`；⑥ 按上面的四象限 / PTY / `web_fetch` 各自的验证法确认真生效。改完把新锚点同步回脚本对应的 `p_*` 函数。
