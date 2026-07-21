# Kimi Code CLI（Moonshot 官方编码 agent：runtime / 鉴权 / 额度）

> **harness skill 的 reference。** 面向要在服务器上跑、或不想走官方 OAuth、直接用 API key 驱动 Kimi Code CLI 的工程师。覆盖：它是什么与分发形态、`~/.kimi-code` 数据目录与 `config.toml`、两套鉴权（Kimi Code 托管 **OAuth** vs 静态 **API key**）与 provider 选型、`/login` 后落地的文件状态、**不登录只用 key 直连**的配置、**用 key 查额度 / 余额**（`/usages` 端点）与"为什么 TUI 余额面板必须 OAuth"，以及**审批 / 权限模式**（默认 / YOLO / Auto / Plan）的差别。
>
> 源码引用锚定 [`MoonshotAI/kimi-code`](https://github.com/MoonshotAI/kimi-code) tag `@moonshot-ai/kimi-code@0.27.0`（commit [`5cc1949`](https://github.com/MoonshotAI/kimi-code/tree/5cc194956f6f9752d172aa4994385d2d2e7a066f)，与本文实测的二进制同版本）；标 🔬 的是本机实测结论、标 📄 的引官方文档。

## <a id="what"></a>是什么 / 分发形态

Moonshot 官方的终端编码 agent，**MIT 开源**，TypeScript monorepo（pnpm），TUI 建在 pi 的 `pi-tui` 之上（见同 skill 的 [pi.md](pi.md)）。开箱接 Kimi 模型，也能配任意 OpenAI/Anthropic 兼容 provider。

- **分发是 Node SEA 单文件二进制**（single executable application）：`<KIMI_CODE_HOME>/bin/kimi`，约 160MB、`file` 认成 ELF（not stripped、带 debug_info），自带 `rg`/`fd`。装法 `curl -fsSL https://code.kimi.com/kimi-code/install.sh | bash`（302 跳 `cdn.kimi.com/binaries/...`），也发 npm 包 `@moonshot-ai/kimi-code`。分发形态本身与 Codex/Claude/Copilot 的对照见同 skill 的 [install.md](install.md)。
- 命令面（`kimi --help`）：裸 `kimi` 进 TUI，`-p <prompt>` 一次性非交互，子命令 `provider`（非交互增删 provider）/`login`/`doctor`（校验配置）/`acp`（Agent Client Protocol over stdio）/`server`/`web`/`export`/`vis`。

## <a id="home"></a>数据目录 `~/.kimi-code` 与 config.toml

根目录默认 `~/.kimi-code`，`KIMI_CODE_HOME` 可整体重定向（config、sessions、logs、OAuth 凭证全落新路径）📄。

```
~/.kimi-code/
├── bin/kimi           # SEA 二进制（+ rg / fd）
├── config.toml        # provider / model / services / thinking
├── tui.toml           # 主题 / 编辑器等 UI 偏好
├── credentials/
│   └── kimi-code.json # OAuth token 本体（见 oauth-files 一节）
├── oauth/
│   └── kimi-code      # ← 只是并发锁（proper-lockfile），常见 0 字节，不是 token
├── device_id          # 设备标识，mode 0600
├── sessions/  logs/  telemetry/  updates/  user-history/
```

`config.toml` 骨架速览如下；`/login` 写出的**完整** OAuth 版见 [OAuth 登录后的文件状态](#oauth-files)、不登录的**静态 key 自建**版见 [不登录：静态 API key 直连](#no-oauth)：

```toml
default_model = "kimi-code/k3"

[providers."managed:kimi-code"]
type     = "kimi"
api_key  = ""                                  # 空 → 走 oauth
base_url = "https://api.kimi.com/coding/v1"
[providers."managed:kimi-code".oauth]
storage = "file"
key     = "oauth/kimi-code"

[models."kimi-code/k3"]                          # provider 之上声明模型别名
provider = "managed:kimi-code"
model    = "k3"
# ...

[services.moonshot_search]                       # 内置 web 搜索 / 抓取，也挂 oauth
base_url = "https://api.kimi.com/coding/v1/search"
api_key  = ""
[services.moonshot_search.oauth]
key = "oauth/kimi-code"
```

## <a id="auth-modes"></a>两套鉴权与 provider 类型

`providers.<name>.type` 决定协议实现；`type = "kimi"` 是 **OpenAI 兼容**协议，同时用于「Kimi Code 托管服务」与「Kimi 开放平台 API key」📄。

- **凭证优先级**：`api_key` 直接字段 > `[providers.<name>.env]` 子表里的 key > 两者都无则启动报错。**CLI 不读 shell 环境变量当凭证**——`export KIMI_API_KEY=…` 不会被任何 provider 认领，必须写进 `config.toml`。唯一例外是 `KIMI_MODEL_*` 家族（见 [no-oauth](#no-oauth)）📄。
  > 📄 [providers.md](https://moonshotai.github.io/kimi-code/en/configuration/providers.md) "Credential priority"、[env-vars.md](https://moonshotai.github.io/kimi-code/en/configuration/env-vars.md)（docs 站为滚动 `en/`，此处记其口径）。

- **两个 base_url 千万别混**（同名相近、账号体系不同）📄：
  | 变量 | 默认值 | 用途 |
  |---|---|---|
  | `KIMI_CODE_BASE_URL` | `https://api.kimi.com/coding/v1` | OAuth 托管服务 / Kimi Code（Coding）key，落 `kimi.com` |
  | `KIMI_BASE_URL` | `https://api.moonshot.ai/v1` | 开放平台 API key，落 `moonshot.ai` |

- **典型坑**🔬：`/login` 菜单里选 "Kimi Platform (API key · platform.kimi.com/.ai)" 会拿 key 去开放平台验证；一把 **Kimi Code（Coding）key 在那条路会被拒**，报 `Invalid Authentication` + 提示 `If your API key was obtained from Kimi Code, please select "Kimi Code" instead`。Coding key 只在 `api.kimi.com/coding` 这条端点有效（本机 `/coding/v1/models`、`/chat/completions` 用该 key 均 200 🔬）。

## <a id="oauth-files"></a>OAuth 登录后的文件状态

设备码（RFC 8628）流程与端点：`{oauthHost}/api/oauth/device_authorization` 换设备码 → 轮询 `{oauthHost}/api/oauth/token`（`grant_type=device_code`）→ 续期 `{oauthHost}/api/oauth/token`（`grant_type=refresh_token`）。`oauthHost` 默认 `https://auth.kimi.com`（`KIMI_CODE_OAUTH_HOST` → `KIMI_OAUTH_HOST` 覆盖），`client_id = 17e5f671-d194-4dfb-9706-5516cb48c098`。
> 端点 [oauth.ts#L5-L7](https://github.com/MoonshotAI/kimi-code/blob/5cc194956f6f9752d172aa4994385d2d2e7a066f/packages/oauth/src/oauth.ts#L5-L7)、host/clientId [constants.ts](https://github.com/MoonshotAI/kimi-code/blob/5cc194956f6f9752d172aa4994385d2d2e7a066f/packages/oauth/src/constants.ts)。

登录后落盘的东西，按"是什么"分清：

- **`credentials/kimi-code.json` —— token 本体**。wire 格式 snake_case：`{ access_token, refresh_token, expires_at, scope:"kimi-code", token_type:"Bearer", expires_in:900 }`；文件 mode `0600`、父目录 `0700`；原子写（`tmp.<pid>.<rand>` → fsync → rename）。access token 寿命约 **15 分钟**，靠 refresh_token 续。
  > [storage.ts](https://github.com/MoonshotAI/kimi-code/blob/5cc194956f6f9752d172aa4994385d2d2e7a066f/packages/oauth/src/storage.ts)（位置/格式/权限/原子写）。存储目录 = `<home>/credentials`、home = `~/.kimi-code`：[toolkit.ts#L122](https://github.com/MoonshotAI/kimi-code/blob/5cc194956f6f9752d172aa4994385d2d2e7a066f/packages/oauth/src/toolkit.ts#L122) / [#L459](https://github.com/MoonshotAI/kimi-code/blob/5cc194956f6f9752d172aa4994385d2d2e7a066f/packages/oauth/src/toolkit.ts#L459)。

- **`oauth/kimi-code` —— 不是 token，是并发锁**。config 里 `[providers…oauth] key = "oauth/kimi-code"` 是这把 token 的 ref key（常量 `KIMI_CODE_OAUTH_KEY`）；刷新时用 `proper-lockfile` 在 `{configDir}/oauth/{name}(.lock)` 加锁，所以这个文件常是 **0 字节**。存储名由 ref key 去掉 `oauth/` 前缀得到 → 落成 `credentials/kimi-code.json`（不是 `oauth/kimi-code.json`）。
  > 锁路径 [oauth-manager.ts#L186](https://github.com/MoonshotAI/kimi-code/blob/5cc194956f6f9752d172aa4994385d2d2e7a066f/packages/oauth/src/oauth-manager.ts#L186)；ref key 常量 [managed-kimi-code.ts#L13](https://github.com/MoonshotAI/kimi-code/blob/5cc194956f6f9752d172aa4994385d2d2e7a066f/packages/oauth/src/managed-kimi-code.ts#L13)；前缀剥离 [toolkit.ts#L444-L447](https://github.com/MoonshotAI/kimi-code/blob/5cc194956f6f9752d172aa4994385d2d2e7a066f/packages/oauth/src/toolkit.ts#L444-L447)。

- **`config.toml` —— provider/model/services 写入**。`/login` 调 `applyManagedKimiCodeConfig` 写 `providers."managed:kimi-code" = { type:"kimi", base_url, api_key:"", oauth }`，合并 `/models` 得到的模型别名，写 `services.moonshot_search|moonshot_fetch`（`base_url + /search|/fetch`，同样 `api_key:"" + oauth`）、`default_model`、`thinking`。
  > [managed-kimi-code.ts `applyManagedKimiCodeConfig`](https://github.com/MoonshotAI/kimi-code/blob/5cc194956f6f9752d172aa4994385d2d2e7a066f/packages/oauth/src/managed-kimi-code.ts#L563-L642)。

- **`device_id`** —— 设备标识，首次生成、mode `0600`。
  > [identity.ts#L36-L56](https://github.com/MoonshotAI/kimi-code/blob/5cc194956f6f9752d172aa4994385d2d2e7a066f/packages/oauth/src/identity.ts#L36-L56)。

- **登出 / 失效不删文件，写 tombstone**：refresh_token 被 401/403 拒后，凭证文件仍在但字段清空（`access_token:"" , refresh_token:"", expires_at:0`），用来区分"登录过、需重登" vs "从没登录"。
  > [token-state.ts](https://github.com/MoonshotAI/kimi-code/blob/5cc194956f6f9752d172aa4994385d2d2e7a066f/packages/oauth/src/token-state.ts)。

**`/login`（默认 host）实际写出的 `config.toml`** 🔬——拿它跟 [不登录：静态 API key 直连](#no-oauth) 那份逐字段对比就能看出两套鉴权差在哪：

```toml
# ~/.kimi-code/config.toml —— /login（Kimi Code OAuth）自动写出
default_model = "kimi-code/k3"

[providers."managed:kimi-code"]            # provider key 固定 managed:kimi-code
type     = "kimi"
api_key  = ""                              # 空 → 用下面的 oauth 块取 token
base_url = "https://api.kimi.com/coding/v1"
[providers."managed:kimi-code".oauth]      # 默认 host 时就这两行
storage  = "file"
key      = "oauth/kimi-code"

[models."kimi-code/k3"]                     # 别名前缀固定 kimi-code/
provider = "managed:kimi-code"
model    = "k3"
max_context_size = 1048576
capabilities     = [ "thinking", "always_thinking", "image_in", "video_in", "tool_use" ]
display_name     = "K3"
support_efforts  = [ "low", "high", "max" ]
default_effort   = "high"
# 另有 kimi-code/kimi-for-coding、kimi-code/kimi-for-coding-highspeed 两个别名，结构同

[thinking]
enabled = true
effort  = "high"

[services.moonshot_search]                  # 内置 web 搜索，同样挂 oauth
base_url = "https://api.kimi.com/coding/v1/search"
api_key  = ""
[services.moonshot_search.oauth]
storage  = "file"
key      = "oauth/kimi-code"

[services.moonshot_fetch]                   # 内置网页抓取，同上
base_url = "https://api.kimi.com/coding/v1/fetch"
api_key  = ""
[services.moonshot_fetch.oauth]
storage  = "file"
key      = "oauth/kimi-code"
```

**与自建静态 key 版的字段差异**：

| 维度 | OAuth 托管（`/login` 写出） | 静态 key 自建（手写，见 [下节](#no-oauth)） |
|---|---|---|
| provider key | 固定 `managed:kimi-code` | 任意，如 `kimi-key` |
| `api_key` | `""`（空，走 oauth 块） | `"sk-..."` |
| `[….oauth]` 块 | 有 | 无 |
| 模型别名前缀 | `kimi-code/*` | `<provider>/*`（如 `kimi-key/*`） |
| `[services.*]`（搜索/抓取） | 有，挂 oauth | 一般不写 |
| 凭证来源 | `credentials/kimi-code.json` 的 OAuth token（15 分钟刷新） | config 里明文 `api_key`（不过期） |
| `kimi provider list` | `source=oauth` | `source=inline` |
| TUI 余额面板 | 有 | 无（见 [面板取数路径](#tui-usage-oauth)） |

> `oauth` 块的 `oauthHost` 只在 host 非默认时才写：`key` 是默认 `oauth/kimi-code` 且 host 是默认 `auth.kimi.com` 时 `persistedOAuthHost` 返回 `undefined`、这行省略；用 `KIMI_CODE_OAUTH_HOST` 覆盖后会多一行 `oauthHost = "…"`。[managed-kimi-code.ts `persistedOAuthHost` / `managedOAuthRef`](https://github.com/MoonshotAI/kimi-code/blob/5cc194956f6f9752d172aa4994385d2d2e7a066f/packages/oauth/src/managed-kimi-code.ts#L265-L291)。

## <a id="no-oauth"></a>不登录：静态 API key 直连

官方**明确支持**"分发 API key"直连托管端点，不走 OAuth——源码把这种叫 "a hand-configured provider using a distributed API key instead of OAuth"，并为它单独留了刷新模型目录的路径。
> [managed-kimi-code.ts `applyManagedApiKeyProviderModels`](https://github.com/MoonshotAI/kimi-code/blob/5cc194956f6f9752d172aa4994385d2d2e7a066f/packages/oauth/src/managed-kimi-code.ts#L644-L665)。

**做法（持久）**：加一个 `type="kimi"` 的自建 provider，base_url 钉死 Coding 端点、api_key 填 `sk-...`，挂模型别名并设 default。OAuth 托管 provider 可原样保留、随时切回。

```toml
default_model = "kimi-key/k3"

[providers.kimi-key]
type     = "kimi"
base_url = "https://api.kimi.com/coding/v1"
api_key  = "sk-..."                              # Kimi Code（Coding）key

[models."kimi-key/k3"]
provider = "kimi-key"
model    = "k3"
max_context_size = 1048576
capabilities = [ "thinking", "always_thinking", "image_in", "video_in", "tool_use" ]
support_efforts = [ "low", "high", "max" ]
default_effort  = "high"
```

`provider list` 会显示该 provider `source=inline`（静态 key），托管那个仍 `source=oauth`。`doctor` 校验通过、无 env 覆盖的 `kimi -p` 能跑通即生效 🔬。key 是明文存 `config.toml`，建议 `chmod 600`。

**做法（临时、不落 config）**：`KIMI_MODEL_*` 环境变量家族是**唯一从 shell 读凭证**的通道，内存合成一个临时 provider/model、优先于 `default_model`📄：

```sh
KIMI_MODEL_NAME=k3 KIMI_MODEL_PROVIDER_TYPE=kimi \
KIMI_MODEL_BASE_URL=https://api.kimi.com/coding/v1 \
KIMI_MODEL_API_KEY=sk-... \
KIMI_MODEL_MAX_CONTEXT_SIZE=1048576 kimi -p "hi"
```

⚠️ 别指望把 key 塞进 `managed:kimi-code` 那个 provider 来"顺带"恢复余额面板——原因见下。

## <a id="usages"></a>额度 / 余额查询（`/usages` 端点）

余额 / 额度端点是 **`GET {base}/usages`** = `https://api.kimi.com/coding/v1/usages`（注意**复数**）。它**同时认 OAuth token 和 API key**——用 key 打返回体里 `authentication.method` 回 `METHOD_API_KEY` 🔬。所以**不登录、不开网页**，一条命令即可查：
> 端点 [managed-usage.ts#L41-L43 `kimiCodeUsageUrl`](https://github.com/MoonshotAI/kimi-code/blob/5cc194956f6f9752d172aa4994385d2d2e7a066f/packages/oauth/src/managed-usage.ts#L41-L43)、fetch [#L291](https://github.com/MoonshotAI/kimi-code/blob/5cc194956f6f9752d172aa4994385d2d2e7a066f/packages/oauth/src/managed-usage.ts#L291)。

```sh
key=$(grep -E '^api_key = "sk-' ~/.kimi-code/config.toml | sed -E 's/.*"(sk-[^"]+)".*/\1/')
curl -s -H "Authorization: Bearer $key" https://api.kimi.com/coding/v1/usages | jq
```

响应字段（解析器对拼写/大小写很宽容）：

- `user.membership.level`（如 `LEVEL_ADVANCED`）、`user.region`、`subType`（如 `TYPE_PURCHASE`）。
- `usage`：主窗口（周）`{ limit, used, remaining, resetTime }`——`used + remaining = limit`，两字段都给。
- `limits[]`：更短的滚动窗口，各自 `{ window:{duration,timeUnit}, detail:{limit,remaining,resetTime} }`。`duration` 的单位由 `timeUnit` 定：`duration:300` + `TIME_UNIT_MINUTE` = **300 分钟 = 5 小时**（不是 5 分钟；源码 `limitLabel` 把它显示成 `5h limit`）。此窗口**只给 `remaining`、无 `used`**——`toUsageRow` 缺 `used` 时按 `used = limit − remaining` 推。
- `parallel.limit`：并发上限。
- `boosterWallet.balance`：有充值钱包时的现金余额，`amount`/`amountLeft` 是 **1e6 定点数**（÷1e6 → 分）；无钱包则不返回（订阅账号的"余额"就是上面各窗口的 `remaining`）。
  > 载荷形状与解析 [managed-usage.ts 顶部注释 + `parseManagedUsagePayload`/`parseBoosterWallet`](https://github.com/MoonshotAI/kimi-code/blob/5cc194956f6f9752d172aa4994385d2d2e7a066f/packages/oauth/src/managed-usage.ts#L1-L160)。

**探测踩坑** 🔬：只有 `/usages`（复数）对；`/coding/v1/meta`、`/coding/v1/usage`（单数）、`/coding/v1/{me,account,subscription,user_profiles}` 全 404；`/chat/completions` 的**响应头不含**任何额度字段（`x-get-balance` 只是二进制里的无关字符串）。所以查额度只能打 `/usages`。

**`used` / `remaining` 的方向与计量** 🔬（往账号打请求消耗额度、连续 poll `/usages` 实测）：

- **方向一致、不反向**：消耗时周 `used` **↑**、周 `remaining` **↓**、5h `remaining` **↓**——`used`=已用、`remaining`=剩余。周窗返 `used`+`remaining` 两个字段、5h 只返 `remaining`，是**字段子集不同、不是含义相反**（若反向，消耗该让 `remaining` 变大，实测没有）。
- **按用量取整计，不是"每请求 +1"**：4 个小请求（各 ~30–40 token）→ 两窗零变化；2 个重请求（输出 766 + 1481 token）→ 两窗各 **−1**。那个 `limit`（如 100）是**用量额度点**（与 token/算力挂钩、取整），小请求四舍五入≈0（精确 token↔点比例未标定）。
- **结算有延迟且两窗不同步**：5h 窗 ~数秒即扣、周窗 ~1–2 分钟才动。所以打完请求立刻查 `used` 常常看不到变化，别据此以为"不计费"。

## <a id="tui-usage-oauth"></a>TUI 余额面板的取数路径

端点认 key，但 CLI 那个 `/usage` 面板取 token 的路径写死了 OAuth：`auth.getManagedUsage`（SDK）→ `toolkit.getManagedUsage` → `ensureFresh`（**取 OAuth access token**）→ `fetchManagedUsage`；且 `isManagedKimiCode(providerKey)` 只认 `managed:kimi-code` 这一个 provider。
> [node-sdk/auth.ts#L170-L176](https://github.com/MoonshotAI/kimi-code/blob/5cc194956f6f9752d172aa4994385d2d2e7a066f/packages/node-sdk/src/auth.ts#L170-L176) → [toolkit.ts#L286-L289](https://github.com/MoonshotAI/kimi-code/blob/5cc194956f6f9752d172aa4994385d2d2e7a066f/packages/oauth/src/toolkit.ts#L286-L289)；provider 门控 [managed-usage.ts#L27-L31](https://github.com/MoonshotAI/kimi-code/blob/5cc194956f6f9752d172aa4994385d2d2e7a066f/packages/oauth/src/managed-usage.ts#L27-L31)。

后果：

- 用静态 key 的自建 provider（非 `managed:` 前缀）→ TUI **不显示**余额面板（`isManagedKimiCode` 返回 false，压根不 fetch）。
- 就算把 key 塞进 `managed:kimi-code` 的 `api_key` → `/usage` 仍走 `ensureFresh` 取 OAuth token（**不 fallback 到 api_key**），没登录就报错。

一句话：**面板依赖 OAuth（用 key 恢复不了），但余额本身可用 key 通过 `/usages` REST 查**。要 TUI 面板就 OAuth 登录该账号；只想知道数字就用上面那条 curl。

## <a id="approval-modes"></a>审批 / 权限模式：默认 / YOLO / Auto / Plan

📄 官方交互文档口径（docs 站为滚动 `en/`，2026-07 核）：

- **默认模式**：有副作用的工具调用（改文件、跑命令）弹审批面板；方向键或 `1`/`2`/`3` 选择，`Esc` / `Ctrl-C` / `Ctrl-D` 均视为拒绝。面板带 "Approve for this session"（本会话内同类调用自动放行）；永久规则写 `config.toml` 的 allow/deny 条目。
- **YOLO（`/yolo`）**：自动批准**常规**工具调用，但三处仍会停——① 访问敏感文件（`.env`、SSH 私钥等）仍要确认；② 退出 Plan 模式仍需确认；③ agent 仍可向你提问。
- **Auto（`/auto`）**：完全无人值守——所有审批自动通过（**含敏感文件**），Plan 退出也自动批准（转录里标 "Auto-approved"），agent **不向你提任何问题**、全部自行决定。
- **Plan（`Shift-Tab` / `/plan`）**：先出计划、批准后动手；`/plan clear` 清空（仅空闲时）。注意与上面两个模式的叠加关系：YOLO 下退出 Plan 仍要确认，Auto 下才自动。

⚠️ 官方警告：YOLO 跳过文件写入与命令执行的确认，只在信任的工作目录用；Auto 更激进（连 `.env` / SSH key 这类敏感访问也不拦），在服务器上跑批量任务时掂量。

**未验证点**：`config.toml` 的 allow/deny 永久规则与各模式的优先级（deny 能否压住 YOLO/Auto 的自动批准），官方交互页未写明。
> 📄 [Interaction and input](https://www.kimi.com/code/docs/en/kimi-code-cli/guides/interaction.html)（"Approval flow" / "Mode switching" 节）。
