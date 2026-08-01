# Copilot CLI app.js 运行时补丁（bundle patch）

Copilot CLI 闭源、只发 minified bundle（为什么闭源、怎么读源码见 [copilot-cli.md「安装方式与看源码」](copilot-cli.md#安装方式与看源码)）。有几处行为**没有任何 settings / flag / env 能改**，只能直接改 `app.js` 打补丁：**重试太少**、**默认档位（effort ＋ context tier）回落**、**`web_fetch` SSRF 拦 fake-ip**（⚠️ 最后这项 1.0.74 起已整体下沉 native，app.js 里再无锚点可打，见[补丁三](#补丁三-web_fetch-ssrf-守卫拦-fake-ip定点放行)）。

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
| `retry-maxretries` | `tmy-retry` | 默认重试对象 `maxRetries` 5→10（GOAWAY / 瞬断更耐抗） | `{maxRetries:5,defaultRetryDelaySeconds:…,backoffFactor:…}`（默认配置对象，独特唯一） |
| `effort-default` | `tmy-max-effort` | 每个模型的「默认 reasoning effort」→ 它**当前有权使用**的最高档（picker `(default)` 顶格；typed `/model` 回落也顶格） | *form B（1.0.78+）*：默认档解析函数的返回尾 `return!<c>\|\|<c>.length===0\|\|<c>.includes(<l>)?<l>:<c>.find(<d>=><d>!==<NONE>)??<NONE>}`；*form A（≤1.0.77）*：`("sweagent-capi",…).clientOptions?.defaultReasoningEffort??"medium"` |
| `tiers-clearpoint` | `tmy-tiers-b` | **context tier 落盘半**：typed `/model <id>` 落盘点别把 `effortLevel`/`contextTier` 抹成空（下次启动不掉档、settings 不被抹） | `<y>.effortLevel=void 0,<y>.contextTier=void 0`（**只用属性名**；1.0.78 有两处，全打） |
| `tiers-live` | `tmy-tiers-live` | **context tier 运行时半**：TUI 应用模型那一步，tier 为空时按模型能力补 `long_context` → **本会话**切模型后即时长上下文（补 clearpoint 只管落盘、live 窗口仍掉 264k 的洞） | `let <vs>=<st>?.type==="success"?<st>.list:void 0,<gc>=(await <s>.model.switchTo({modelId:…,reasoningEffort:…,contextTier:<me>,` + 就近前方的 `,<bi>=<me>;` |
| `webfetch-fakeip` | `tmy-webfetch-fakeip` | `web_fetch` SSRF 放行 fake-ip 段 `198.18/19`（mihomo fake-ip 下可用） | `.hookResolveAndValidateUrl(…)`（形态 B helper）；形态 A 用 `.networkIsBlockedIp`。**1.0.74 起两者都已不在 app.js → 恒 `N/A`** |

**三种状态，含义不同**（脚本逐 patch 打印）：

| 状态 | 含义 | 要不要人管 | 计入 `--strict` 失败？ |
|---|---|---|---|
| `already` / `APPLY` | 已打过 / 本次打上 | 不用 | 否 |
| `N/A` | **特性探针**说上游把这块整个搬走了（如 SSRF 守卫下沉 native）——不是腐坏，是没得打 | 不用（除非你想去啃 `.node`） | **否** |
| `SKIP` | 特性还在，但锚点对不上＝**补丁腐坏** | **要**：按本文对应节重新逆向那一个 | 是 |

这个 `N/A` / `SKIP` 之分是**抗腐坏的关键**：没有它，一个被上游移除的 patch 会让 systemd 服务永远 `failed`，真正的腐坏就淹没在噪声里了（1.0.74→1.0.78 就是这么被拖到 3 个 patch 一起坏才被发现的）。

**跑成功（全 `apply` 或 `already`）就不用往下读**。**开新会话才生效**（运行中的 `copilot` 已把 `app.js` 载进内存）；`copilot update` 拉的新版本目录是干净的，**重跑一次**即可（幂等）。

**实测（1.0.78-2）**：`retry` / `effort-default` / `tiers-clearpoint` / `tiers-live` 四个全命中、`--apply` 后 `node --check` 干净、幂等重跑全 `already`；`webfetch-fakeip` 报 `N/A`（守卫已下沉 native）。同一份脚本对 1.0.74 / 1.0.75 / 1.0.76-3 / 1.0.78-0 / 1.0.78-2 五个版本目录全部 `node --check` 通过（老版本自动回落 form A，1.0.74/75 的 `tiers-live` 因形态更早而 `SKIP`——loader 不跑它们，`--latest-only` 已规避）。⚠️ **别用位序数字比版本**：正式版 `1.0.69` 与预发布 `1.0.69-2` 并存时，`1.0.69-2` 的数字元组 `(1,0,69,2)` 会被误判得比 `1.0.69` 的 `(1,0,69)` 高、和 loader（SemVer：release > prerelease）相反；脚本 `_vkey` 已按 SemVer 优先级排，`--latest-only` 才和 loader 选的是同一份。这也是「auto-update 后要重跑」的典型场景：新掉的正式版目录是干净的，把上一版打好的补丁架空了。

**跑失败时**：脚本会打印是哪个 patch、什么原因（`anchor count=0` / 特性缺失 / 找不到模型对象）。按 patch 名到下面对应节，用「稳定锚点」重新 `view` 当前 `app.js` 定位、据「改什么」重写替换。**每次只修失效的那一个**。

**脚本不覆盖、需手动**的一项（retry 非-API 退避下限，形态已移除）见文末[未覆盖节](#未覆盖需手动逆向)。

---

## 自动重打：`copilot-auto-patch` systemd --user 服务

手动记着「auto-update 后重跑脚本」太容易忘——CLI 默认 `autoUpdate: true`，新掉的版本目录是干净的，会把上一版打好的补丁架空（见上面 `_vkey` 那段的实测场景）。用一个 systemd --user 服务盯着 pkg cache、自动重打，就不用惦记了。前提是目标机跑 systemd --user（WSL2 需另开 linger，否则退出登录服务就停）。

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
- 服务跑的是脚本**副本**，不是 skill 里的原件。**改了 `scripts/patch-copilot-cli.py` 后要重新 `cp` 到每台装了本服务的机器的 `~/.local/share/copilot-auto-patch/`**，否则服务还在跑旧版。
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

### 让补丁少腐坏一点（1.0.74→1.0.78 那次三连坏之后加的规矩）

minified bundle 每版都变，锚点必然会坏——目标不是永不坏，而是**坏得更慢、坏了更容易发现和修**。按收益排序：

1. **锚点优先级：属性名 / native 函数名 ＞ 字符串字面量 ＞ 表达式形状 ＞ 函数签名。** 属性名（`contextTier`、`effortLevel`、`switchTo({modelId,reasoningEffort,`）是 API 契约，改名要动一片；表达式形状和函数签名是压缩器和重构的自由区，说变就变。这次 `tiers-live` 就是因为盯着 `setModel:async(<id>,<ie>,<ee>)=>` 的签名和「第 4 个位置参是 `void 0`」而坏掉的——改成盯 `.model.switchTo({modelId:…,reasoningEffort:…,contextTier:…` 之后，同一份锚点回溯兼容到 1.0.76。
2. **别硬编上游的枚举。** 旧版把 effort 阶梯写死成 `["max","xhigh","high","medium","low"]`，结果上游加了 `minimal` 档、以后再加更高档也不会自动跟上。改成从 bundle 里探 `<X>=<alias>.reasoningEffortLevels(),<Y>=<X>[0]`（native 直出、**升序**、`[0]` 是 `none`），按 `indexOf` 取最大——上游怎么加档位都跟得上。同理，判 long_context 用 native 的 `modelsIsTieredTokenPrices` 而不是自己列模型名。
3. **特性探针（probe）：区分「腐坏」和「上游搬走了」。** 每个 patch 先便宜地判一下「我要改的那个东西还在不在 bundle 里」——不在＝`N/A`（不报警），在但锚点不匹配＝`SKIP`（报警）。少了这层，被移除的 patch 会把 `--strict` 钉死在 `failed`，真腐坏就没人看见了。
4. **能降级就别 SKIP。** 补丁分「必须精确」和「差不多就行」两类：`tiers-clearpoint` 的本质诉求只是「别把我的设置抹了」，那就退化成自赋值 no-op，完全不需要在作用域里找到模型对象——锚点从「两个属性名 + 就近找 `.find(a=>a.id===…)`」缩到「两个属性名」，腐坏面积小一大半。
5. **多形态并存（form A / B / …）。** 新形态放前面、老形态兜底，老版本目录自然回落，也给「上游改一半又改回去」留了余地。
6. **补丁要能被单元测。** 把改完的那个函数从 bundle 里切出来、喂桩跑一遍（见[补丁二的验证节](#验证用真-pty-驱动交互式-tui)），比只看 `node --check` 强得多——语法对不代表语义对。这次就是靠它发现旧 `tiers-clearpoint` 的 effort 守卫读了个**根本不存在的字段**、静默失效了不知道多少版。


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
- **每个模型的「默认档」来自 bundle 解析、用户不可配**：
  - *effort*：**1.0.78 起换了实现**——旧版是静态表（源标签 `"sweagent-capi"`）的 `clientOptions.defaultReasoningEffort`、缺省硬回落 `"medium"`；新版把 `"medium"` 提成模块常量，解析函数改成「先算该模型的 **entitled effort 列表**（native `modelResolverGetEntitledReasoningEfforts`，已按套餐/权限过滤），默认档不在列表里才换成列表里第一个非 `none` 的」。这既是 picker `(default)` 标签来源，也是 typed `/model` 回落目标。
  - *context*：`long_context`（分层定价大窗口档，如 gpt-5.x 的 1.1M）**只在该模型 `billing.token_prices` 带 `long_context` 时才存在**；不支持的模型只有 `default` 一档。
- **两处被 typed `/model` 清空 / 重置**（补丁的靶，**两处现在都补**）：
  - **清空点（落盘半）**：typed `/model <id>` 落盘写 settings 前那句 `<y>.effortLevel=void 0,<y>.contextTier=void 0`（清空 settings）。→ `tiers-clearpoint` 补。**1.0.78 里这样的清空点有两处**（实名 model 分支 ＋ `/model auto` 伪模型分支），都要补。
  - **TUI 应用点（运行时半）**：TUI 应用模型的回调里 `await <sess>.model.switchTo({modelId:…,reasoningEffort:…,contextTier:<me>,…})`，typed `/model` 路径把 `<me>` 传成 `undefined` → **本会话 live 窗口**重置回默认档。→ `tiers-live` 补（`<me>??守卫`；picker 路径显式传了 `"default"`/具体档，`??` 短路、不误伤）。
  - 所以「先用无参 `/model` 两步选择器选好档」扛不住之后任何一次 typed `/model` 切模型（picker 路径两处都传满参、不清；typed 路径两处都靠补丁兜）。
- **⚠️ 交互 TUI 无视 `--context` 开关，只认 `settings.json` 的 `contextTier`**（实测；无头 `-p` 才认开关）。根因：交互 App 有个挂载 effect 只从盘重灌 tier（启动时 runtime 没带 tier → 落到 `settings.contextTier`）。**所以交互启动要长上下文＝改 `settings.json` `contextTier: long_context`，别指望 `--context`。**
- **⚠️ 给不支持 `long_context` 的模型带上该 tier 是安全的**（1.0.78-2 实测：`copilot -p --model gpt-5-mini --context long_context` 正常返回、不报错，只是窗口按该模型的默认档走）。这条是 `tiers-clearpoint` 敢退化成「保留上次设置、不算不清」的前提。
- **context 的完整修复 = 三件套**：① `settings.json` `contextTier: long_context`（管交互**启动**即长上下文）＋ ② 清空点补丁 `tiers-clearpoint`（管 typed `/model` **落盘**不被抹、下次启动对）＋ ③ TUI 应用点补丁 `tiers-live`（管 typed `/model` 后**本会话 live 窗口**即时长上下文）。缺 ③ 实测（1.0.70-0）：typed `/model` 后 `settings.json` 落了 `long_context`、但 `/context` live 窗口仍 **264k**；补 ③ 后 live 变 **1000k**。（这三件套的历史：② + ③ 就是早年 `patch-copilot-cli-longcontext.py` 的 PATCH#1 + PATCH#2；重构时误以为「1.0.69-2 起 setModel 已转发当前 tier」把 ③ 删了，1.0.70-0 实测证伪、遂补回。）

**实测四象限（opus 系；上下文窗口取 `/context` 面板，prompt 上限取 resolved `max_prompt_tokens`）**：

| 场景 | 上下文窗口 | prompt 上限 |
|---|---|---|
| 无头 `-p` ＋ `--context default` | 264k | 200k |
| 无头 `-p` ＋ `--context long_context` | **1,000,000** ✓ | 936,000 |
| 交互 TUI 启动 ＋ `--context long_context` 开关 | 264k ✗ | 200k |
| 交互 TUI 启动 ＋ settings `contextTier=long_context`（不带开关） | **1,000,000** ✓ | 936,000 |

**会话内 typed `/model` 的 live 窗口（PTY 驱动真 TUI + `/context`）**：

| 场景 | live `/context` 窗口 | settings 落盘 |
|---|---|---|
| 只补 `tiers-clearpoint`（落盘半）：typed `/model <大模型>` | 264k ✗（掉档） | `long_context` ✓ |
| 加 `tiers-live`（运行时半）：`/model claude-opus-4.8` | **1,000,000** ✓ | `long_context` ✓ |
| 加 `tiers-live`：`/model gpt-5-mini`（1.0.78 起也支持 long） | **1,050,000** ✓ | `long_context` ✓ |
| 加 `tiers-live`：模型不支持 long 时 | 该模型默认档（守卫回落、不崩） | 保留上次值（无害，见上文） |

### 改什么（两个作用面，effort / context 各管一段）

档位有**两个作用面**，脚本按诉求覆盖：

- **作用面 A「默认解析」**（管 picker `(default)` 标签 + 启动 / 解析回落）：改读「每个模型默认档」的解析函数，让它返回**该模型当前有权使用的最高档**而非静态默认。
  - *effort*（脚本 `effort-default`）——**1.0.78 起换了形态**：解析函数不再以 `??"medium"` 收尾（`"medium"` 被提成模块级常量了），而是长这样：
    ```js
    function <U3>(t,e,n,r,o){ let s=<Gf>(t,void 0,n,r,o), a=o.find(d=>d.id===t)?.capabilities.family,
        l=<每模型覆写>[t] ?? … ?? <默认常量>, c=<Gf>(t,e,n,r,o);
      return !c||c.length===0||c.includes(l) ? l : c.find(d=>d!==<NONE>) ?? <NONE> }
    ```
    其中 `c` 是该模型的 **entitled effort 数组**（native `modelResolverGetEntitledReasoningEfforts` 已按套餐/权限过滤）。补丁就锚这个 `return` 尾巴，改成「**先从 `c` 里按 native 阶梯挑最高档，挑不到再走原逻辑**」。
    比 form A 更准：form A 读的是 bundle 内置**静态表**的 `supportedReasoningEfforts`（可能列出你没权限的档），form B 读的是**你真能用的**。
    阶梯顺序从 `<AX>=<alias>.reasoningEffortLevels(),<NONE>=<AX>[0]` 探（native 直出、升序 `none < minimal < low < medium < high < xhigh < max`），**不硬编**。`<AX>` 与 `<NONE>` 是同一条 top-level `var` 声明的兄弟，`<NONE>` 既然在解析函数里能用，`<AX>` 就一定也在作用域内、也一定已初始化。
  - *context*：理论对称，但 stock 里 context 默认本就是 `default`、没有独立的「默认取 long_context」解析点，故脚本不做 context 的 A 面——**交互启动的长上下文靠 `settings.json` 的 `contextTier`**（见上文四象限）。
- **作用面 B「typed `/model` 切换点」**——**两处代码、两个补丁**：
  - **B-落盘（`tiers-clearpoint`）**：typed `/model <id>` 落盘写 settings 前那句 `<y>.effortLevel=void 0,<y>.contextTier=void 0` 会把持久默认抹掉。**改成自赋值 no-op**（`<y>.effortLevel=<y>.effortLevel,<y>.contextTier=<y>.contextTier`）——这两处前面都是 `<y>={...<刚 load 的 settings>}`，自赋值即「保留上次设置」。
    ⚠️ 1.0.78 有**两处**这样的清空点（实名 model 分支 + `/model auto` 伪模型分支），旧锚点靠三目形式 `<y>.model=<n>===<u>?void 0:<n>,…` 只命中了前者，`/model auto` 一直在偷偷抹设置。现在锚点只认两个属性名，两处全打。
    **为什么不再「按模型能力算出该写什么」**（旧版做法，已废弃）：
    - *effort 侧*：旧守卫读 `<模型对象>.supportedReasoningEfforts`，但该字段**只在 bundle 内置静态表上**，API 模型列表对象根本没有 → 恒为 `undefined`、等价于没打（静默失效了很久，靠单元测才发现）。正确的兜底在作用面 A，这里不该重复。
    - *context 侧*：实测给不支持 `long_context` 的模型留着该 tier 会被**安静忽略**（`copilot -p --model gpt-5-mini --context long_context` 正常返回），既不报错也不掉档，所以不必算、不必清。
    收益：锚点从「属性名 + 就近找模型对象」缩到「只有属性名」，抗腐坏强得多。
  - **B-运行时（`tiers-live`，只 context）**：TUI 里真正应用模型的那个回调，末尾会 `await <sess>.model.switchTo({modelId:<O>,reasoningEffort:<vi>,contextTier:<me>,…})`；typed `/model` 路径把 `<me>` 传成 `undefined` → 本会话 live 窗口重置回默认档（settings 已是 `long_context` 也没用，要重开会话才生效）。
    锚点取那段 `let <vs>=<st>?.type==="success"?<st>.list:void 0,<gc>=(await <sess>.model.switchTo({modelId:…,reasoningEffort:…,contextTier:<me>,`（**全是属性名**），再往前就近找 `,<bi>=<me>;`——`<bi>` 就是同一回调里喂给 UI 页脚 / 记账 / 「档位没变」早退判断的那个 tier 状态。补丁把 `<bi>=<me>` 改成 `<bi>=(<me>??守卫)`，并把 `switchTo` 里的 `contextTier:<me>` 换成 `contextTier:<bi>`，一处改动全对齐。
    `??` 而非无条件覆盖：picker 路径显式选了 `default` 时 `<me>` 是字符串 `"default"`，走不到守卫，**不误伤用户的显式选择**。
- **守卫（不支持的模型必须回落、不能崩）**：照抄 native 能力判定——`<mv>.billing.token_prices` 存在且 `<alias>.modelsIsTieredTokenPrices(JSON.stringify(...))` 为真且 `"long_context" in …`，否则 `void 0`。模块别名 `<alias>` 从 `<x>.modelsIsTieredTokenPrices` 探测、**别硬编**（1.0.70 是 `S`、1.0.76+ 是 `h`）。全 `&&` 短路 + `try/catch` 包住，任何模型对象形态都不会抛、最坏回 `void 0`。
  - **⚠️ 特性前置守卫**（《通用套路》第 4 条的实例）：`long_context` 分层定价靠 native `modelsIsTieredTokenPrices` 判定；老版本没有这个函数，注入引用它的守卫会**运行时崩**、而 `node --check` 查不出。所以打 context 前必须先确认 bundle 里有该字面量，没有就报 `N/A`（脚本两个 `tiers` 都内建此探针）。真踩过：放松锚点后多版本全匹配 + `node --check` 全过，老版本一敲 `/model` 就炸。


**实测结论（1.0.78-2）**：typed `/model claude-opus-4.8` → live `/context` 出 **1000k**（`tiers-live` 生效；不补时 264k）；`/model gpt-5-mini` → **1050k**。**关键教训**：`tiers-clearpoint` 单独存在时 `settings.json` 看着对（`long_context`）、但 live 窗口仍 264k——所以补丁验证一定要读 live `/context`、不能只读 settings。

### 验证：把改完的函数切出来单元测（比 `node --check` 强得多）

`node --check` 只查语法，**查不出「改对了没有」**。对 `effort-default` 这种纯函数式的改动，最快最狠的验证是**把函数从 bundle 里切出来、喂桩、跑一遍**，并且**打补丁前后各跑一次比 diff**：

1. 从 `app.js`（改后）和 `app.js.tmy-patch.bak`（改前）各 `indexOf` 到那个函数的起止，切出函数体。
2. 拼一个小 `.js`：前面放桩（`Gf` 返回你构造的 entitled 数组、`AX`/`NONE`/默认常量/每模型覆写各给一个），后面放几组 case 打印结果。
3. `node run.js` 对比两份输出。

这次就是靠它拿到决定性证据：

| 模型（构造的 entitled 列表） | 改前 | 改后 |
|---|---|---|
| `gpt-5.5`（`none,low,medium,high,xhigh`） | `medium` | **`xhigh`** ✓ |
| `claude-opus-5`（`none,low,medium,high,max`） | `medium` | **`max`** ✓ |
| 只有 `none` | `none` | `none`（不强推、正确回落） |
| 空列表 | `medium` | `medium`（走原逻辑、不崩） |

也是靠它发现旧 `tiers-clearpoint` 的 effort 守卫读的 `supportedReasoningEfforts` **在 API 模型对象上根本不存在**——那个 patch 「命中、`node --check` 通过、marker 齐全」，但语义上一直是空转。**凡是「守卫读某个字段」的补丁，都要单独确认那个字段真在你拿到的那种对象上。**

### 验证：用真 PTY 驱动交互式 TUI

改 bundle 后光 `node --check` + `--version` 不够——得验 typed `/model` 真落到目标档。这类「要驱动交互式 TUI、按键、读屏幕」的验证，用 Python stdlib **`pty.fork()`** 起真 PTY（不必装 `pexpect`）；嫌麻烦也可以 `uv run --with pexpect`（PEP723 脚本头写 `dependencies = ["pexpect"]`）用 `pexpect.spawn(..., dimensions=(50,200))`，省掉手写 ioctl / select，本次验证走的就是这条。

- 子进程 `os.execvp("copilot",…)` 拿到**真控制终端**；`ioctl(fd, TIOCSWINSZ, …)` 设窗口、`TERM=xterm-256color`。
- master fd：`select.select([fd])` 读＝看屏幕；`os.write(fd,ch)` ＝敲键盘（`\r` 提交、`\x03` 退出）。
- **逐字符输入（~60ms/字符）**：一次性灌整行会和 TUI 自动补全竞争、截断命令——踩过。
- **启动先应答「Do you trust the files in this folder?」信任框**（在 `/tmp` 等新目录会弹）：检测到就先发 `1\r`，否则你的 `/model` 会被信任框吃掉——踩过。
- **断言分两层，缺一不可**：① 从磁盘读 `settings.json` 看 `contextTier`/`effortLevel`（落盘半）；② **`/model` 后再发 `/context` 读 live 面板的窗口数**（`opus-4.8 · 70k/1000k tokens` 才是真 1M，264k＝掉档）。**只看 ① 会被 `tiers-clearpoint` 骗过**——它把 settings 写成 `long_context` 了，但没 `tiers-live` 时 live 窗口仍 264k。正则剥 ANSI 后 grep `Model changed from` / `… · Nk/Mk tokens`。**必须换一个和当前不同、且支持目标档的模型**（如 gpt-5.4）强制真切换；`-p "/model"` 一次性喂会走另一条「Already using」路径（不在 app.js 里），测不到。
- **零干扰隔离法**（别动用户真环境）：`COPILOT_HOME=<scratch>` 指到只含小文件（`config.json` 带鉴权 + 自造 `settings.json`）的 scratch 目录（3.4G 的 `logs/`、`session-state/` 不用拷）；要测「补丁版 app.js」而不碰真 pkg cache，就 `cp -a` 版本目录到 `COPILOT_CACHE_HOME=<scratch>/pkg/<platform>/`、目录名改成极高版本号（如 `9.9.9-0`）让 loader 必选它、补丁只打这份。CLI 认 `COPILOT_CACHE_HOME`（实测：只有 scratch 那份带 `tmy-tiers-live` → live 出 1M，反证 CLI 跑的就是它）。

**实测结论（1.0.70-0，历史记录）**：支持的模型（gpt-5.4 / 5.5 / opus-4.8）→ typed `/model` 后 `settings.json` 落 `long_context`（`tiers-clearpoint`）**且** live `/context` 出 `1000k`/`1.1M`（`tiers-live`）；不支持的（gpt-5-mini，当时 192k）→ 两半守卫都回落 default、不崩。**关键教训**：`tiers-clearpoint` 单独存在时 `settings.json` 看着对（`long_context`）、但 live 窗口仍 264k——所以补丁验证一定要读 live `/context`、不能只读 settings。

⚠️ **踩坑：`copilot` 可能不是你以为的那个 `copilot`。** PATH 里可能有 wrapper / shim（如 direnv `PATH_add` 注入的一层）替你补了 `--model` / `--effort` / `--context` 开关。验证「**默认**档位」时必须绕开它、走真正的 CLI 入口（`command -v -a copilot` 看清有几个、挑真的那个绝对路径），否则你测的是命令行开关、不是补丁。同理，起 TUI 时若 cwd 是新目录会先弹「Do you trust the files in this folder?」，脚本要检测到就先发 `1\r`，否则后续按键全被信任框吃掉。

---

## 补丁三 · `web_fetch` SSRF 守卫拦 fake-ip（定点放行）

> 🚫 **1.0.74 起本补丁在 app.js 里已无处可打**：整套「解析 + 判黑」连同 `hookResolveAndValidateUrl` / `networkIsBlockedIp` 都下沉到了 native（`<alias>.toolWebFetchRegisterCallbacks`，实现在 `prebuilds/<platform>/cli-native.node`）。脚本的探针会报 **`N/A`** 而不是 `SKIP`——不是腐坏，是没得打，`--strict` 也不会因此失败。要放行只能改 `.node`（不在本脚本范围）。下面保留机制与形态演化记录，供「上游哪天把它挪回 JS」或「真要啃 native」时参考。

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
| **B · native 判黑，JS 留 helper** | helper 只剩 `return(await <native>.hookResolveAndValidateUrl(t,e.allowLocalhost===!0,e.urlLabel)).map(…)`，**JS 里已无 `networkIsBlockedIp`、连 `node:dns` 都不 import** | 只能重写该 helper 自己解析 |
| **C · 整个 web_fetch 下沉 native**（1.0.74+，当前） | JS 只剩注册回调 `<alias>.toolWebFetchRegisterCallbacks(async n=>{…permissions.request…})`，**连 helper 都没了**——URL 解析、判黑、抓取全在 `.node` 里 | **app.js 无锚点** → 脚本报 `N/A` |

GitHub 把整套「解析 + 判黑」搬进 Rust 绑定了，且这个搬迁是**分两步、跨了好几个版本**完成的（A→B→C）。后果：**每次 `copilot update` 都可能让 patch 失效**（实测 1.0.66→1.0.69 期间 4 次自更新把旧 patch 全打空），最后干脆无处可打。这也是「N/A vs SKIP 要分开」的直接动因——形态 C 落地后，若还把它算作腐坏，systemd 服务会永远红着。

### 改什么（定点放行，最小爆炸半径）

只放行 fake-ip 池 `198.18.0.0/15`（`198.18.x` / `198.19.x`，本就没有合法内网服务），其余仍交给原判黑——`127/10/192.168/169.254/::1/云元数据`照旧全拦，比「让判黑恒 `false`」安全得多：

- **形态 A**：把对 `networkIsBlockedIp(ip)` 的调用包成「命中 `/^198\.1[89]\./` 则返回 `false`（不拦）、否则走原调用」。
- **形态 B**（脚本做的）：重写那个 helper——先自己 `await import("node:dns/promises")` 解析主机名，**全部**解析成 fake-ip 段（`/^198\.1[89]\./`）时直接返回地址（绕过 native）、否则回落 `await <native>.hookResolveAndValidateUrl(...)`（保留真实内网防护）。锚点用 `.hookResolveAndValidateUrl(t,e.allowLocalhost===!0,e.urlLabel)` 整段定位、混淆名反向引用捕获。

### 验证

patch 后**开新会话**让它 `web_fetch` 任意外网 URL；若错误从 `blocked address` 变成连接 / 代理类错误，说明判黑已绕过、但底层 fetch 对 pinned fake-ip 的出站路径有问题（查 `proxyEnv` / `pinnedAddresses` 与 TUN 直连）。

---

## 未覆盖、需手动逆向

脚本刻意不碰的几处（当前形态已变 / 移除，硬做易崩或无收益）。需要时对着当前 `app.js` 手动逆向：

- **retry 非-API 错误的 4 秒退避下限**：旧版本 `retryAfter*(0.8+Math.random()*0.4)` 套 `Math.max(…,4)`。**当前版本已无此 jitter 公式**（`Math.random` 只剩 brace-expansion 占位、temp 文件名等无关用途）。`maxRetries` 翻倍已覆盖主要收益；若未来版本重现该公式，锚点用 `.8+Math.random()*.4`。
- **`web_fetch` fake-ip 放行（1.0.74+）**：整个 web_fetch 下沉 native，app.js 无锚点（见[补丁三](#补丁三-web_fetch-ssrf-守卫拦-fake-ip定点放行)形态 C）。脚本报 `N/A`。真要修得改 `prebuilds/<platform>/cli-native.node`——二进制补丁的维护成本远高于 JS，且每次 `copilot update` 必然被换掉；实用替代是**别用 fake-ip**（mihomo 切 `redir-host`），或需要抓网页时走 `curl`。
- **1.0.74 / 1.0.75 目录的 `tiers-live`**：那两版的 TUI 应用点还是更早的形态，当前锚点匹配不上、报 `SKIP`。loader 只跑最高版本、不会执行它们，`--latest-only`（systemd 服务就用这个）已规避，故不补。

> 📌 **曾经未覆盖、现已补回**：context tier 的「本会话内存半 / setModel」。重构时误判「1.0.69-2 起 setModel 已转发当前 tier、无需补」，1.0.70-0 实测证伪（typed `/model` 后 live `/context` 掉回 264k），已由 `tiers-live`（作用面 B-运行时）补回，见上文补丁二。教训：**「setModel 已转发 tier」不能只看调用点带没带 `contextTier`——得看那个 tier 值的来源；1.0.70-0 里 live 切换认的是第 4 个位置参（`void 0`），不认对象里的 `contextTier`。**

**手动逆向工作流**（脚本报某个 patch `SKIP` 时）：① 按上表「稳定锚点」`grep`/`view` 当前 `app.js` 确认字面量还在、看它现在长什么样；② 用 node 切片（`s.indexOf(锚点)` 前后各切一段、`replace(/\s+/g," ")` 压平）读清结构；③ 数命中数（须唯一）；④ 按「改什么」写替换、混淆名反向引用捕获；⑤ `node --check`；⑥ 按上面的四象限 / PTY / `web_fetch` 各自的验证法确认真生效。改完把新锚点同步回脚本对应的 `p_*` 函数。
