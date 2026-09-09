# Copilot CLI app.js 运行时补丁（bundle patch）

Copilot CLI 闭源、只发 minified bundle（为什么闭源、怎么读源码见 [copilot-cli.md「安装方式与看源码」](copilot-cli.md#安装方式与看源码)）。本文记录默认档位与重试行为的运行时补丁。固定默认模型、固定 effort 和 context tier 可以用配置；“每个模型自动选择最高可用 effort、切模型默认使用长上下文”还涉及选择器与会话切换逻辑，需要按版本适配。

1.0.83 的默认档位计算已经迁入 native，脚本通过 [CLI 调用边界](#native-defaults) 适配；旧版的 JavaScript 锚点与重试补丁保留在[旧版适配](#legacy-js)。`web_fetch` fake-ip 补丁已退役，见[对应说明](#webfetch-fakeip)。

**打补丁只改运行时真正跑的那份 `app.js`**——pkg cache 里的最高版本（`~/.cache/copilot/pkg/<platform>/<version>/app.js`），不是 npm 的 `node_modules` 种子、也不是 SEA 的 ELF（机制见 [copilot-cli.md「运行时到底跑哪份 app.js」](copilot-cli.md#运行时到底跑哪份-appjs打补丁改这份)）。

> ⚠️ **补丁是逆向产物、会随版本腐坏。** 本文的做法是「先跑脚本，跑成功就不用读细节；跑失败再对着当前 `app.js` 手动逆向那一个 patch」。所以下文既给脚本，也给每个 patch 的**改动意图 + 稳定字面量锚点**，供脚本失效时重建。锚点一律用跨版本不变的字面量（env 名 / 错误文案 / 配置键 / native 函数名），混淆符号名用正则反向引用捕获、**绝不硬编**。

---

## 一键脚本：`scripts/patch-copilot-cli.py`（先跑这个）

纯 Python stdlib、无第三方依赖，带 PEP 723 元数据。以下命令在 harness skill 根目录执行。脚本默认只预览；落盘前要求 Node 完成语法校验，再备份到同目录的 `app.js.tmy-patch.bak` 并原子替换文件。`--revert` 恢复运行时但保留备份，不修改用户设置。

```bash
uv run scripts/patch-copilot-cli.py --latest-only --strict
uv run scripts/patch-copilot-cli.py --apply --latest-only --strict
uv run scripts/patch-copilot-cli.py --revert --latest-only
```

### <a id="native-defaults"></a>Native 默认档位适配

检测到 `CliModelPickerHandle` 时，脚本选择 `native-model-defaults` 组，不再尝试旧版的 effort/context 正则，也不夹带已经下沉 native 的重试补丁。所有必需入口必须一起命中；任一入口失配就整组 `SKIP`，不写入部分改动。已打补丁时同时核对 helper 内容与调用点；已知 v1 可按内容摘要校验后原子升级到 v2，其他不一致版本需先恢复备份再重打。

| 路径 | 适配位置 | 行为 |
|---|---|---|
| 启动 | `modelCliStartupConfiguration`、`CliSessionEnvironmentHandle.initialize` | 避免把 native 自动填出的 medium 当成显式命令行选择；模型列表就绪后计算最高可用 effort 和长上下文 |
| `/model` 选择器 | `CliModelPickerHandle` 的 CLI 局部适配对象 | 同步处理预选值、effort 默认标记、初始光标和默认模型标记；窗口显示仍由 native setter 计算 |
| 会话内切换 | 选择器与直接输入命令各自的 `model.switchTo` 调用点 | 只补未给定的档位；保留同一模型当前已选的档位与显式参数 |
| 非交互主会话 | `modelCliHeadlessConfiguration` 及其 options 更新点 | 默认 effort 按当前模型能力计算，支持时补长上下文，不改显式参数 |

默认模型仍写在用户 `settings.json` 的 `model` 字段，脚本不把某个模型 ID 写死进 bundle。选择器有可用的用户默认模型时，用它显示默认标记；模型不可用时保留 native 的可用性判断与回退。配置示例：

```json
{
  "model": "<model-id>",
  "contextTier": "long_context"
}
```

要使用动态最高 effort，不设置全局 `effortLevel`；有效的显式 effort 配置或命令行参数仍优先。恢复会话已有的档位不应为了“默认”被顶掉。选择器中手动改过的 effort/context 单独记录，刷新不会重新覆盖；计划模型、子代理、仓库级选择器、远程与自定义提供方不强套这套默认策略。

`long_context` 是模型提供的档位，不是硬写 `1000000` token。补丁只对 native 返回长档的模型选择它；窗口大小、输入预算和输出预留继续取模型元数据。

> 入口依据：CLI 1.0.83，构建标识 `e6a98f1` 的 `app.js` 与 `runtime.node`。离线覆盖使用同版 native 模块的临时内存会话，包括有权限的 effort 数组、长档/无长档模型、显式低档、恢复选择和非交互默认值；它不等价于带真实账号的完整 TUI 覆盖。

> 新版 native 会给非当前模型预填 medium/default，同时把两者标成 `Explicit: true`，因此不能用这些初始标志判断用户是否操作过。`setReasoningEffort()` 只改变实际选择，不改变 reasoning picker 的默认标记；只补 setter 或只改标签都会漏掉另一半。直接输入 `/model` 与选择器也不是同一个切换调用点。

> 远程会话必须在选择器构造时就排除，并把远程状态纳入 memo 依赖；仅在切换函数中放行原参数不够，因为选择器可能已把默认参数改成最高 effort / 长上下文。

### <a id="legacy-js"></a>旧版 JavaScript 适配

未检测到 native 选择器的旧版继续使用下表；各 patch 独立，锚点失配只跳过对应项。下文旧版“清空 settings”与四处 context 锚点的记录不能直接套用到 1.0.83。

| patch 名 | marker | 效果 | 稳定锚点（手动逆向时也用它） |
|---|---|---|---|
| `retry-maxretries` | `tmy-retry` | 默认重试对象 `maxRetries` 5→10（GOAWAY / 瞬断更耐抗） | `{maxRetries:5,defaultRetryDelaySeconds:…,backoffFactor:…}`（默认配置对象，独特唯一） |
| `effort-default` | `tmy-max-effort` | 每个模型的「默认 reasoning effort」→ 它**当前有权使用**的最高档（picker `(default)` 顶格；typed `/model` 回落也顶格） | *form B（1.0.78+）*：默认档解析函数的返回尾 `return!<c>\|\|<c>.length===0\|\|<c>.includes(<l>)?<l>:<c>.find(<d>=><d>!==<NONE>)??<NONE>}`；*form A（≤1.0.77）*：`("sweagent-capi",…).clientOptions?.defaultReasoningEffort??"medium"` |
| `tiers-clearpoint` | `tmy-tiers-b` | **context tier 落盘半**：typed `/model <id>` 落盘点别把 `effortLevel`/`contextTier` 抹成空（下次启动不掉档、settings 不被抹） | `<y>.effortLevel=void 0,<y>.contextTier=void 0`（**只用属性名**；1.0.78 有两处，全打） |
| `tiers-live` | `tmy-tiers-live` | **context tier 运行时半**：TUI 应用模型那一步，tier 为空时按模型能力补 `long_context` → **本会话**切模型后即时长上下文 | `let <vs>=<st>?.type==="success"?<st>.list:void 0,<gc>=(await <s>.model.switchTo({modelId:…,reasoningEffort:…,contextTier:<me>,` + 就近前方的 `,<bi>=<me>;` |
| `tiers-picker` | `tmy-tiers-picker` | **context tier picker 半**：无参 `/model` 选择器里，非当前模型的 tier 默认值从硬编 `"default"` 改成 `long_context`（否则列表里显示的窗口是小的那个，选中后还把 `tiers-live` 的守卫短路掉） | `contextTier:<je>,contextTiers:<Hn>?.map(` + 就近前方的 `<je>=<Hn>?…:void 0` 里的 `"default"` 字面量 |
| `tiers-startup` | `tmy-tiers-startup` | **context tier 启动半**：把「内置默认档」从 default 改成 `long_context`，`settings.json` 里没写过 / 被抹过也不掉档 | `<Br>=<opts>.context??<settings>.contextTier`（开关 ?? settings 的优先级链，链尾接兜底） |

**三种状态，含义不同**（脚本逐 patch 打印）：

| 状态 | 含义 | 要不要人管 | 计入 `--strict` 失败？ |
|---|---|---|---|
| `already` / `APPLY` | 已打过 / 本次打上 | 不用 | 否 |
| `N/A` | 旧版探针未找到对应特性；不证明其他调用层也无法适配 | 需区分真正退役与实现迁移；新版默认档位组不使用这个状态 | **否** |
| `SKIP` | 特性还在，但锚点对不上＝**补丁腐坏** | **要**：按本文对应节重新逆向那一个 | 是 |

这个 `N/A` / `SKIP` 之分是**抗腐坏的关键**：没有它，一个被上游移除的 patch 会让 systemd 服务永远 `failed`，真正的腐坏就淹没在噪声里了（1.0.74→1.0.78 就是这么被拖到 3 个 patch 一起坏才被发现的）。

**需要重新启动 Copilot 进程才生效**：运行中的进程已经把 `app.js` 载入内存，仅 `/new` 不会重载补丁。恢复旧会话会保留其显式档位，要观察启动默认值应另开全新会话。`copilot update` 拉的新版本目录是干净的，需要再次运行脚本；新版本入口失配时先适配，不能强行写入。

> 要固定加载刚打补丁的缓存版本，可用 `copilot --prefer-version <version>`。不要把 `COPILOT_AUTO_UPDATE=false` 当成同义选项：1.0.83 loader 在没有 `--prefer-version` 时可能改用安装器内嵌的种子版本，而不再选择最新缓存。

**实测（1.0.78-2）**：六个 patch 全命中、`--apply` 后 `node --check` 干净、幂等重跑全 `already`。同一份脚本对 1.0.74 / 1.0.75 / 1.0.76-3 / 1.0.78-0 / 1.0.78-2 五个版本目录全部 `node --check` 通过（老版本自动回落 form A，1.0.74/75 的 `tiers-live` 因形态更早而 `SKIP`——loader 不跑它们，`--latest-only` 已规避）。⚠️ **别用位序数字比版本**：正式版 `1.0.69` 与预发布 `1.0.69-2` 并存时，`1.0.69-2` 的数字元组 `(1,0,69,2)` 会被误判得比 `1.0.69` 的 `(1,0,69)` 高、和 loader（SemVer：release > prerelease）相反；脚本 `_vkey` 已按 SemVer 优先级排，`--latest-only` 才和 loader 选的是同一份。这也是「auto-update 后要重跑」的典型场景：新掉的正式版目录是干净的，把上一版打好的补丁架空了。

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
6. **写回前 `node --check`**：先校验内存中的完整补丁结果，通过后再备份与原子替换。
7. **扫所有版本目录**：pkg cache 有多个版本目录（`$COPILOT_PKG_CACHE_HOME/pkg`、`$COPILOT_CACHE_HOME/pkg`、`$XDG_CACHE_HOME/copilot/pkg`、macOS `~/Library/Caches/copilot/pkg`、`$COPILOT_HOME/pkg`、`~/.copilot/pkg`；平台子目录形如 `linux-x64/<version>/app.js`），逐个打。
8. **只对新进程生效**：运行中的 `copilot` 已把 `app.js` 载入内存，补丁需要重新启动进程。
9. **auto-update 后要重跑**：CLI 默认 `autoUpdate: true`，新版本目录是干净的。判断哪些没打过：`grep -L '<marker>' ~/.cache/copilot/pkg/*/*/app.js`（列空＝都打过了）。旧备份 / 旧版本目录不自动回收，loader 只跑最高版本、留着无害，要清手动清。

### 让补丁少腐坏一点（1.0.74→1.0.78 那次三连坏之后加的规矩）

minified bundle 每版都变，锚点必然会坏——目标不是永不坏，而是**坏得更慢、坏了更容易发现和修**。按收益排序：

1. **锚点优先级：属性名 / native 函数名 ＞ 字符串字面量 ＞ 表达式形状 ＞ 函数签名。** 属性名（`contextTier`、`effortLevel`、`switchTo({modelId,reasoningEffort,`）是 API 契约，改名要动一片；表达式形状和函数签名是压缩器和重构的自由区，说变就变。这次 `tiers-live` 就是因为盯着 `setModel:async(<id>,<ie>,<ee>)=>` 的签名和「第 4 个位置参是 `void 0`」而坏掉的——改成盯 `.model.switchTo({modelId:…,reasoningEffort:…,contextTier:…` 之后，同一份锚点回溯兼容到 1.0.76。
2. **别硬编上游的枚举。** 旧版把 effort 阶梯写死成 `["max","xhigh","high","medium","low"]`，结果上游加了 `minimal` 档、以后再加更高档也不会自动跟上。改成从 bundle 里探 `<X>=<alias>.reasoningEffortLevels(),<Y>=<X>[0]`（native 直出、**升序**、`[0]` 是 `none`），按 `indexOf` 取最大——上游怎么加档位都跟得上。同理，判 long_context 用 native 的 `modelsIsTieredTokenPrices` 而不是自己列模型名。
3. **特性探针（probe）：区分「腐坏」和「上游搬走了」。** 每个 patch 先便宜地判一下「我要改的那个东西还在不在 bundle 里」——不在＝`N/A`（不报警），在但锚点不匹配＝`SKIP`（报警）。少了这层，被移除的 patch 会把 `--strict` 钉死在 `failed`，真腐坏就没人看见了。
4. **能降级就别 SKIP。** 补丁分「必须精确」和「差不多就行」两类：`tiers-clearpoint` 的本质诉求只是「别把我的设置抹了」，那就退化成自赋值 no-op，完全不需要在作用域里找到模型对象——锚点从「两个属性名 + 就近找 `.find(a=>a.id===…)`」缩到「两个属性名」，腐坏面积小一大半。
5. **多形态并存（form A / B / …）。** 新形态放前面、老形态兜底，老版本目录自然回落，也给「上游改一半又改回去」留了余地。
6. **补丁要能被单元测。** 把改完的那个函数从 bundle 里切出来、喂桩跑一遍（见[补丁二的验证节](#验证用真-pty-驱动交互式-tui)），比只看 `node --check` 强得多——语法对不代表语义对。这次就是靠它发现旧 `tiers-clearpoint` 的 effort 守卫读了个**根本不存在的字段**、静默失效了不知道多少版。
7. **同一个设置键会有好几个读取点，别打错。** `contextTier` 在 bundle 里有 80 多处出现，其中「喂 UI 状态」「resume 从盘重灌」「启动优先级链」长得都很像，但只有最后一个对全新会话有效——改错了照样 `node --check` 干净、marker 齐全、实测毫无变化（踩过）。**判据要找「语义唯一的邻居」**：启动链认 `<opts>.context`（命令行开关）和 `.contextTier`（settings 键）同时出现，因为只有解析优先级的地方才会把开关和配置放在一个 `??` 里。
8. **一个诉求可能横跨多条用户路径。** 「默认长上下文」在 UI 上是一件事，代码里却是四处独立逻辑（启动默认 / typed 落盘 / typed live / picker 默认），补丁只覆盖一部分时，症状是「有时行有时不行」而不是「不行」——最难查。**验证要按用户路径枚举，不是按补丁枚举。**


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

> 本节是旧版 JavaScript 实现的定位记录。1.0.83 的配置作用域、选择器和切换入口见 [native 适配](#native-defaults)，不要为恢复旧锚点而重建已删除的全局设置清空逻辑。

**这俩是同一类问题**：typed `/model <id>` 切模型时，用**同一行**把 `effortLevel` 和 `contextTier` 一起清空（`<state>.effortLevel=void 0,<state>.contextTier=void 0`，落盘 + 本会话内存都清）→ 两档位一起回落该模型「默认档」。想让它们默认停在想要的档（effort→模型支持的最高档、context→`long_context`），纯改 settings 都扛不住 typed `/model`，只能 patch。（曾错误以为「effort 要 hack、context 改 settings 就够」，是假的不对称——两者机制同构。）

### 机制（两档位同构）

- **优先级（都一样）**：命令行开关（`--effort <none/low/medium/high/xhigh/max>`＝`--reasoning-effort`；`--context <default/long_context>`，均会话级不落盘）> `settings.json`（`effortLevel` / `contextTier`，合法持久键；`contextTier` 的 `inherit` 只给子代理）> 内置默认。model 另有 `COPILOT_MODEL` env，但 **effort / context 都没有对应 env**。持久默认只在全局 `~/.copilot/settings.json`（无目录级 settings，`$COPILOT_HOME` 可整体挪位）；TUI 里选档写回这里，故「上次选择」＝「默认」。
- **每个模型的「默认档」来自 bundle 解析、用户不可配**：
  - *effort*：**1.0.78 起换了实现**——旧版是静态表（源标签 `"sweagent-capi"`）的 `clientOptions.defaultReasoningEffort`、缺省硬回落 `"medium"`；新版把 `"medium"` 提成模块常量，解析函数改成「先算该模型的 **entitled effort 列表**（native `modelResolverGetEntitledReasoningEfforts`，已按套餐/权限过滤），默认档不在列表里才换成列表里第一个非 `none` 的」。这既是 picker `(default)` 标签来源，也是 typed `/model` 回落目标。
  - *context*：`long_context`（分层定价大窗口档，如 gpt-5.x 的 1.1M）**只在该模型 `billing.token_prices` 带 `long_context` 时才存在**；不支持的模型只有 `default` 一档。
- **context tier 有四处要补，缺一处就在某条路径上掉档**（这是踩出来的：以为「改 settings 就够」「补两处就完」，都不够）：

| # | 补丁 | 管哪条路径 | 不补的症状 |
|---|---|---|---|
| ① | `tiers-startup` | **全新会话的内置默认档** | `settings.json` 没写过 / 被抹过 → 新会话 264k |
| ② | `tiers-clearpoint` | typed `/model <id>` **落盘** | 切完模型 settings 里的 tier 被抹 → 下次启动掉档 |
| ③ | `tiers-live` | typed `/model <id>` **本会话 live 窗口** | settings 看着对，但当前会话仍 264k，要重开才生效 |
| ④ | `tiers-picker` | 无参 `/model` **选择器** | 列表里显示小窗口；选中后传显式 `"default"`，把 ③ 的守卫短路掉 |

  ①②③④ 各自独立：①管「没配过」，②③管 typed 路径的盘/内存两半，④管 picker 路径。
  历史：②③ 就是早年 `patch-copilot-cli-longcontext.py` 的 PATCH#1 + PATCH#2；①④ 是 1.0.78 期间实测补上的——当时误判「context 没有独立的默认解析点、不需要 A 面」，实际 ① 就是 A 面、④ 是 picker 的 A 面。

- **⚠️ 交互 TUI 无视 `--context` 开关，只认 `settings.json` 的 `contextTier`**（实测；无头 `-p` 才认开关）。根因：交互 App 有个挂载流程只从盘重灌 tier。**所以补 ① 之前，交互启动要长上下文＝改 `settings.json` `contextTier: long_context`，别指望 `--context`；补 ① 之后 settings 可以不写。**
- **⚠️ 给不支持 `long_context` 的模型带上该 tier 是安全的**（实测：`copilot -p --model gpt-5-mini --context long_context` 正常返回；picker 里 `Claude Haiku 4.5` 这类没有分层档的模型选中后照常按自己的窗口走、不报错）。这条是 ①④ 敢无条件兜底、②敢「不算不清」的前提。

**实测四象限（opus 系；上下文窗口取 `/context` 面板，prompt 上限取 resolved `max_prompt_tokens`）**：

| 场景 | 上下文窗口 | prompt 上限 |
|---|---|---|
| 无头 `-p` ＋ `--context default` | 264k | 200k |
| 无头 `-p` ＋ `--context long_context` | **1,000,000** ✓ | 936,000 |
| 交互 TUI 启动 ＋ `--context long_context` 开关 | 264k ✗ | 200k |
| 交互 TUI 启动 ＋ settings `contextTier=long_context`（不带开关） | **1,000,000** ✓ | 936,000 |

**会话内切模型的 live 窗口（PTY 驱动真 TUI + `/context`；1.0.78-2 实测）**：

| 场景 | live `/context` 窗口 | 说明 |
|---|---|---|
| 全新会话，`settings.json` **不含** `contextTier` —— 不补 ① | 264k ✗ | 「没配过 / 被抹过」就掉档 |
| 全新会话，`settings.json` **不含** `contextTier` —— 补 ① | **1,000,000** ✓ | 内置默认已改，settings 可以不写 |
| 只补 ②（落盘半）：typed `/model <大模型>` | 264k ✗ | settings 落了 `long_context`、live 仍掉档 |
| 补 ③：typed `/model claude-opus-4.6` | **1,000,000** ✓ | 切换提示带 `(1M context)` |
| 不补 ④：picker 选 `Claude Opus 4.8` | 264k ✗ | 列表里那一列也显示小窗口 |
| 补 ④：picker 选 `Claude Opus 4.8` | **1,000,000** ✓ | 列表显示 1M / 1.1M |
| 补 ④：picker 选 `Claude Haiku 4.5`（无分层档） | 200k | 该模型固有窗口，守卫回落、不崩 |

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
  - *context*：**有 A 面，别被「默认就是 default」骗了**。启动时的优先级链是
    `--context 开关 ?? settings.contextTier ?? 内置默认`，bundle 里就是一句
    `<Br>=<opts>.context??<settings>.contextTier`——**链尾是空的**，两者都没有就得到
    undefined、落回小窗口。`tiers-startup` 就是在这条链尾接 `??"long_context"`，
    只改「内置默认」这一档，开关和 settings 的显式值靠 `??` 短路仍然优先。
    picker 另有一份自己的默认（见下面 ④），要单独补。
    ⚠️ **别打错地方**：bundle 里还有两处也在读 `contextTier`——一处只喂 UI 状态、一处是
    resume / 远程会话的「从盘重灌」（条件是**盘上有值**才生效）。改那两处对全新会话
    完全无效（踩过：打上去 `node --check` 干净、marker 齐全，实测仍 264k）。
    认准这条链的判据：它同时出现 `<opts>.context`（命令行开关）和 `.contextTier`（settings 键）。
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
  - **B-picker（`tiers-picker`，只 context）**：无参 `/model` 打开的选择器，构建列表项时给每个模型算一个默认 tier：
    `<je>=<Hn>?<fe>[<m>.id]??(<m>.id===<cur>?<C>??"default":"default"):void 0`
    —— `<Hn>` 是该模型的 tier 选项（模型没有 long_context 档时为 undefined），`<cur>` 是当前模型。
    也就是**只有当前模型沿用现有 tier，切到任何其它模型一律硬编 `"default"`**。
    这个值既决定列表里那一列显示的窗口大小，也作为**显式** tier 传给应用函数——于是
    `tiers-live` 的 `??` 守卫被短路（`"default"` 不是 nullish），**picker 路径拿不到长上下文，
    而 typed 路径能拿到**（typed 传 undefined）。两条路径行为不一致就是这么来的。
    改法：把那句赋值 RHS 里的 `"default"` 字面量换成 `"long_context"`。`<Hn>` 为真 ⟺ 该模型
    确实有 long_context 档，所以换了不会造出非法档位；`<fe>[<m>.id]`（用户在 picker 里明确
    选过的档）仍在最前、不覆盖显式选择。锚点走列表项上的属性名 `contextTier:…,contextTiers:…?.map(`。
- **守卫（不支持的模型必须回落、不能崩）**：照抄 native 能力判定——`<mv>.billing.token_prices` 存在且 `<alias>.modelsIsTieredTokenPrices(JSON.stringify(...))` 为真且 `"long_context" in …`，否则 `void 0`。模块别名 `<alias>` 从 `<x>.modelsIsTieredTokenPrices` 探测、**别硬编**（1.0.70 是 `S`、1.0.76+ 是 `h`）。全 `&&` 短路 + `try/catch` 包住，任何模型对象形态都不会抛、最坏回 `void 0`。
  - **⚠️ 特性前置守卫**（《通用套路》第 4 条的实例）：`long_context` 分层定价靠 native `modelsIsTieredTokenPrices` 判定；老版本没有这个函数，注入引用它的守卫会**运行时崩**、而 `node --check` 查不出。所以打 context 前必须先确认 bundle 里有该字面量，没有就报 `N/A`（脚本两个 `tiers` 都内建此探针）。真踩过：放松锚点后多版本全匹配 + `node --check` 全过，老版本一敲 `/model` 就炸。


**实测结论（1.0.78-2）**：四处 context 补丁齐了之后，「全新会话 / typed `/model` / picker 选择」三条路径都拿到 1M（各自的对照见上表）。**关键教训**：`tiers-clearpoint` 单独存在时 `settings.json` 看着对（`long_context`）、但 live 窗口仍 264k——所以补丁验证一定要读 live `/context`、不能只读 settings；同理，**只测 typed `/model` 会漏掉 picker 路径**（两条路径喂给应用函数的 tier 不是同一个值）。

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

## <a id="webfetch-fakeip"></a>补丁三 · `web_fetch` SSRF 守卫拦 fake-ip（已退役）

> 🚫 **已退役、脚本不再覆盖。** 1.0.74 起整套「URL 解析 + SSRF 判黑 + 抓取」下沉到 native，app.js 里再无锚点可打，故已从 `patch-copilot-cli.py` 移除（留着只会每次报一行 `N/A` 噪声）。
>
> **实证**（1.0.78-2）：`app.js` 里 `hookResolveAndValidateUrl` / `networkIsBlockedIp` / `WebFetchBlockedUrlError` / 错误文案 `URLs must not target loopback, private, or link-local addresses` **全部 0 命中**；同一段文案与 `resolves to blocked address` 出现在 `prebuilds/<platform>/runtime.node` 里。JS 侧只剩注册权限回调（`<alias>.toolWebFetchRegisterCallbacks`）。
>
> **现在怎么办**：① 别用 fake-ip（mihomo 换 `redir-host`，回真实公网 IP 就不触发）；② 要抓网页时用 `curl`（没有这道预检）。改 `.node` 二进制理论可行但不划算——每次 `copilot update` 必被换掉，且二进制补丁没法像 JS 那样靠字面量锚点自愈。
>
> 下面保留机制与形态演化记录，供「上游哪天把它挪回 JS」时快速重建。

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
- **形态 B**（脚本曾经做的）：重写那个 helper——先自己 `await import("node:dns/promises")` 解析主机名，**全部**解析成 fake-ip 段（`/^198\.1[89]\./`）时直接返回地址（绕过 native）、否则回落 `await <native>.hookResolveAndValidateUrl(...)`（保留真实内网防护）。锚点用 `.hookResolveAndValidateUrl(t,e.allowLocalhost===!0,e.urlLabel)` 整段定位、混淆名反向引用捕获。
- **形态 C**（当前）：无 JS 落点，上面两条都用不上。

### 判断当前是哪种形态

重建前先辨形，一条命令即可（`0 / 0` 就是形态 C、别再往下折腾 JS）：

```bash
grep -c 'networkIsBlockedIp' <app.js>          # >0 → 形态 A
grep -c 'hookResolveAndValidateUrl' <app.js>   # >0 → 形态 B
```

真打上了再验：**开新会话**让它 `web_fetch` 任意外网 URL；若错误从 `blocked address` 变成连接 / 代理类错误，说明判黑已绕过、但底层 fetch 对 pinned fake-ip 的出站路径有问题（查 `proxyEnv` / `pinnedAddresses` 与 TUN 直连）。

---

## 未覆盖、需手动逆向

脚本刻意不碰的几处（当前形态已变 / 移除，硬做易崩或无收益）。需要时对着当前 `app.js` 手动逆向：

- **retry 非-API 错误的 4 秒退避下限**：旧版本 `retryAfter*(0.8+Math.random()*0.4)` 套 `Math.max(…,4)`。**当前版本已无此 jitter 公式**（`Math.random` 只剩 brace-expansion 占位、temp 文件名等无关用途）。`maxRetries` 翻倍已覆盖主要收益；若未来版本重现该公式，锚点用 `.8+Math.random()*.4`。
- **`web_fetch` fake-ip 放行（1.0.74+）**：已退役——整个 web_fetch 下沉 native，app.js 无锚点，脚本已移除该 patch（见[补丁三](#webfetch-fakeip)）。真要修得改 `prebuilds/<platform>/runtime.node`——二进制补丁的维护成本远高于 JS，且每次 `copilot update` 必然被换掉；实用替代是**别用 fake-ip**（mihomo 切 `redir-host`），或需要抓网页时走 `curl`。
- **1.0.74 / 1.0.75 目录的 `tiers-live`**：那两版的 TUI 应用点还是更早的形态，当前锚点匹配不上、报 `SKIP`。loader 只跑最高版本、不会执行它们，`--latest-only`（systemd 服务就用这个）已规避，故不补。

> 📌 **曾经未覆盖、现已补回**：context tier 的「本会话内存半 / setModel」。重构时误判「1.0.69-2 起 setModel 已转发当前 tier、无需补」，1.0.70-0 实测证伪（typed `/model` 后 live `/context` 掉回 264k），已由 `tiers-live`（作用面 B-运行时）补回，见上文补丁二。教训：**「setModel 已转发 tier」不能只看调用点带没带 `contextTier`——得看那个 tier 值的来源；1.0.70-0 里 live 切换认的是第 4 个位置参（`void 0`），不认对象里的 `contextTier`。**

**手动逆向工作流**（脚本报某个 patch `SKIP` 时）：① 按上表「稳定锚点」`grep`/`view` 当前 `app.js` 确认字面量还在、看它现在长什么样；② 用 node 切片（`s.indexOf(锚点)` 前后各切一段、`replace(/\s+/g," ")` 压平）读清结构；③ 数命中数（须唯一）；④ 按「改什么」写替换、混淆名反向引用捕获；⑤ `node --check`；⑥ 按上面的实测对照表 / 切函数单元测 / PTY 驱动 TUI 各自的验证法确认真生效——**context 类补丁必须把「全新会话 / typed `/model` / picker 选择」三条路径都跑一遍**，只测其中一条会漏（踩过）。改完把新锚点同步回脚本对应的 `p_*` 函数。
