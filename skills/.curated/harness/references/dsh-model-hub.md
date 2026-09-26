# DSH Model Hub：订阅登录、版本边界与额度查询

用于核对 Model Hub 到底复用了哪一层官方能力，以及为 DSH 增加订阅额度显示时应该复用、替换或补齐什么。社区发现与早期比较见 [Plugin 调研记录](dsh-research.md#2026-08-26-subscription-auth-surfaces)；一般插件开发见 [dsh-dev.md](dsh-dev.md)，Codex 进程与账号活动统计见 [codex.md](codex.md)。本专题补充 2026-08-26 的订阅登录快照，以本次复核说明当前的 UI 扩展条件。

> **核对口径：2026-09-27（Asia/Tokyo）。** 以下结论来自固定提交的 manifest、实现、协议类型和厂商文档。版本表是源码与发布记录口径，不代表 npm dist-tag、锁文件最终解析值或用户当前安装版本。没有安装、升级或启动 DSH，没有登录账号、读取个人凭据或请求真实额度；源码存在、上游测试存在与本次端到端通过分别看待。

## <a id="snapshot"></a>版本与证据范围

| 对象 | 本次固定快照 | 与本题相关的事实 | 依据 |
|---|---|---|---|
| `yhyfhgs/dsh-model-hub` | `0.2.4`，`2bb54c6543c8faac05d2b54162b33f1c80915e1a`；版本记录日期 2026-08-29 | DSH 开发/兼容基线仍为 `0.1.1-rc.2`；Pi peer 为 `~0.82.1`，由 Host 提供 | [版本](https://github.com/yhyfhgs/dsh-model-hub/blob/2bb54c6543c8faac05d2b54162b33f1c80915e1a/CHANGELOG.md#L10-L30)、[兼容](https://github.com/yhyfhgs/dsh-model-hub/blob/2bb54c6543c8faac05d2b54162b33f1c80915e1a/README.md#L157-L167) |
| `deepseek-ai/deepseek-harness` | `0.1.7-rc.2`，`477b4f420553e8a52c2fbccc464d7561b239c443` | 官方 `dsh-llm-pi-ai` 依赖声明已到 `^0.85.1`；Models 页面有扩展插槽 | [manifest](https://github.com/deepseek-ai/deepseek-harness/blob/477b4f420553e8a52c2fbccc464d7561b239c443/packages/llm/llm-pi-ai/package.json#L1-L70) |
| `earendil-works/pi` | `2b0a123de98318c2ff8069661721ce0c3794c34e`；CHANGELOG 最新版本条目为 `0.87.1`（2026-09-22） | `0.86.0` 有 provider-facing context 破坏性变更；其上的 Unreleased 不算已发布能力 | [CHANGELOG](https://github.com/earendil-works/pi/blob/2b0a123de98318c2ff8069661721ce0c3794c34e/packages/ai/CHANGELOG.md#L1-L115) |
| `openai/codex` | `7f6c0f9387a0a60f396f61cc58f6b38bc98f2473` | 账号额度 RPC、按额度池返回的类型及其后端 usage 请求有公开源码 | [额度类型](https://github.com/openai/codex/blob/7f6c0f9387a0a60f396f61cc58f6b38bc98f2473/codex-rs/app-server-protocol/schema/typescript/v2/GetAccountRateLimitsResponse.ts#L8-L30) |
| `WSL043/dsh-codex-subscription` | `2.2.2`，`6e55f21da9fade22f6edd1f9e789184426c83281` | 当前已有 Host 侧额度读取与 Web 显示；使用独立的凭据约定，接入时需要身份适配 | [manifest](https://github.com/WSL043/dsh-codex-subscription/blob/6e55f21da9fade22f6edd1f9e789184426c83281/package.json#L1-L100) |

## <a id="ownership"></a>后端归属与登录链路

“Model Hub 给官方已引入的 Pi 后端补前端”**对官方 adapter 路由成立；原生路由另有归属**。它同时维护官方路由的交互桥和自己的原生 provider 域。

| 路由/层 | 登录与凭据的归属 | Model Hub 做什么 | 依据 |
|---|---|---|---|
| 官方 `openai-codex` 等 `llm-pi-ai` 路由 | 官方 `registerPiAiFlows` → Pi `Models.login` → DSH `llm-pi-ai` scope 的 credential record；推理时由官方 adapter/Pi 消费 | 解析官方绑定，调用 `ctx.authorization.begin`，把 notice/prompt/取消与结果投影到浏览器；提供激活、目录和选择界面 | [官方 flow](https://github.com/deepseek-ai/deepseek-harness/blob/477b4f420553e8a52c2fbccc464d7561b239c443/packages/llm/llm-pi-ai/src/login.ts#L111-L170)、[桥](https://github.com/yhyfhgs/dsh-model-hub/blob/2bb54c6543c8faac05d2b54162b33f1c80915e1a/src/auth/bridge.ts#L397-L440) |
| 插件内建 `codex` | Model Hub 自己的 OAuth flow、record 与 native adapter；复用 Pi 的 Codex Responses 协议，认证链仍由 native 域负责 | 自己维护授权常量、固定 callback、模型表、生命周期和请求适配 | [native Codex](https://github.com/yhyfhgs/dsh-model-hub/blob/2bb54c6543c8faac05d2b54162b33f1c80915e1a/src/provider/native/catalog.ts#L291-L369) |
| 插件内建 `qwen-code` | 同属 Model Hub native 域；设备码 OAuth 与 grant 由该域维护 | 补上这条路由及其登录界面，应按 native 域维护 | [native Qwen](https://github.com/yhyfhgs/dsh-model-hub/blob/2bb54c6543c8faac05d2b54162b33f1c80915e1a/src/provider/native/catalog.ts#L213-L254) |

`codex → openai-codex` 的 alias 用于把重复供应商行折叠展示，**仅改变显示；两条路由各自保留 grant 与凭据归属**。查问题时同时记录 provider ID、adapter、settings namespace 和 credential owner，卡片显示名仅作为辅助信息。登录成功与路由激活也分开：官方 flow 可以在没有 provider profile 时注册；激活不能随手加一个缺失的 `apiKeyEnv`，否则会挡住本来可用的 OAuth record。

> 来源：[原生与官方 Codex 并存及显示 alias 的说明](https://github.com/yhyfhgs/dsh-model-hub/blob/2bb54c6543c8faac05d2b54162b33f1c80915e1a/src/provider/native/catalog.ts#L291-L309)、[空 activation profile 与凭据优先级原因](https://github.com/yhyfhgs/dsh-model-hub/blob/2bb54c6543c8faac05d2b54162b33f1c80915e1a/src/provider/bindings.ts#L38-L83)。

## <a id="official-ui"></a>官方界面的当前扩展面

官方当前的 Models 页面已有 API-key 配置、自定义 Pi 路由、模型目录和 DeepSeek Account 相关界面。缺口应收窄为：**本次检查的 Models 页面与 Authorization 调用方中，未见面向所有已注册第三方 Pi 登录 flow 的通用 Web 交互桥**。官方 DeepSeek 账号登录服务于自身账号，应与 Codex/Copilot 等 provider 的登录交互分别核对。

更重要的变化是，官方 Models 页面已声明以下插槽，旧快照中“只能替换整页才能加内容”的判断不再适用：

| 插槽 | 当前契约 | 登录/额度组件的使用边界 |
|---|---|---|
| `settings.models.provider-card` | `keyed`，按 `settingsNs` 分发，owner 含 provider、configured、keyConfigured | 官方 Pi 家族应按其 settings namespace 注册，再从 owner 区分具体路由；entry key 使用 namespace，OAuth 状态另行读取脱敏的凭据描述 |
| `settings.models.footer` | `list`，不提供 provider owner 数据 | 可放动态 flow 列表或没有现成卡片的账号入口，但需要自己获取脱敏状态 |
| `settings.models.sign-in` | `single`，提供完成/转 API key 回调 | 是账号 onboarding 选择位，宜保留现有账号 onboarding 的归属 |

> 来源：[当前 Models 功能与 Extension slots](https://github.com/deepseek-ai/deepseek-harness/blob/477b4f420553e8a52c2fbccc464d7561b239c443/packages/client/ui-settings-models/README.md#L10-L76)、[插槽的真实类型契约](https://github.com/deepseek-ai/deepseek-harness/blob/477b4f420553e8a52c2fbccc464d7561b239c443/packages/client/ui-settings-models/src/client/slot-contract.ts#L1-L56)、[官方 Pi 登录 flow 实现](https://github.com/deepseek-ai/deepseek-harness/blob/477b4f420553e8a52c2fbccc464d7561b239c443/packages/llm/llm-pi-ai/src/login.ts#L111-L170)。通用 Web 桥的缺口是本次源码检查范围内的判断，不是对所有第三方发行包的断言。

**方案推论：** 只为补登录和额度，优先做官方 Models 页的 companion 插件，不必连官方设置页、onboarding 与模型选择器一起替换。仍然要补 Host RPC、交互尝试生命周期和额度读取器；插槽只解决“界面放哪里”，不自动提供认证或查询权限。Model Hub 自身仍禁用官方 Models UI，因此 companion 的这些官方插槽仅适用于仍启用官方页面的组合；继续使用 Model Hub 时，要另做其页面集成或独立设置区。

> 来源：[Model Hub 对官方 UI 的替换及已知限制](https://github.com/yhyfhgs/dsh-model-hub/blob/2bb54c6543c8faac05d2b54162b33f1c80915e1a/README.md#L157-L185)。

## <a id="version-drift"></a>版本差距与维护风险

**依赖声明与实际运行版本分别记录。** Model Hub 声明 Pi `~0.82.1`，当前官方 adapter 声明 `^0.85.1`，两者范围不相交。Model Hub 的 Pi 是 Host 提供的 peer，不是它私带的冻结副本，因此在新版 DSH 中必须验证实际 Host 模块表、导出、类型与运行行为。optional 只描述 peer 约定；兼容性需要实际验收，范围差异在这里记为风险而非启动失败记录。官方 `^0.85.1` 也不会自动覆盖 `0.86` 或 `0.87`；实际部署以 Host 解析结果为准。

**模型目录已有可定位的过期项。** 原生 `codex` 的表仍来自 Pi `0.82.1`，列出 `gpt-5.4` 与 `gpt-5.4-mini`。OpenAI 已明确它们从 **2026-08-31** 起不再供 ChatGPT 账号登录的 Codex 使用；Pi `0.86.0` 也记录了相应移除。这个结论适用于订阅路由，自带 OpenAI API key 的使用范围应另查。更新 Host Pi 目录不会自动改写插件的 native 静态表。

> 来源：[Model Hub 兼容性与 Host-supplied peer](https://github.com/yhyfhgs/dsh-model-hub/blob/2bb54c6543c8faac05d2b54162b33f1c80915e1a/README.md#L65-L83)、[兼容矩阵](https://github.com/yhyfhgs/dsh-model-hub/blob/2bb54c6543c8faac05d2b54162b33f1c80915e1a/README.md#L157-L167)、[官方依赖声明](https://github.com/deepseek-ai/deepseek-harness/blob/477b4f420553e8a52c2fbccc464d7561b239c443/packages/llm/llm-pi-ai/package.json#L1-L70)、[仍存在的静态模型项](https://github.com/yhyfhgs/dsh-model-hub/blob/2bb54c6543c8faac05d2b54162b33f1c80915e1a/src/provider/native/catalog.ts#L256-L369)、[Pi 移除记录](https://github.com/earendil-works/pi/blob/2b0a123de98318c2ff8069661721ce0c3794c34e/packages/ai/CHANGELOG.md#L57-L110)、[OpenAI 订阅说明的 GPT-5.4/mini FAQ](https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan)（查询于 2026-09-27）。

**升级按 API 变化验收。** Pi `0.86.0` 把 provider-facing `Context` 改为 `TranscriptContext`，system prompt 与 tools 的读取方式也变了；应分开验收 DSH 当前受支持的 Pi 线与未来的 Pi 大步升级。Model Hub 还公开记录了自己的 session selection 与 Core admission/ACP/SDK `session.selectModel` 的双重归属。额度组件保持只读；图片准入、选择持久化与模型选择权属于独立验收面。

> 来源：[Pi 破坏性变更](https://github.com/earendil-works/pi/blob/2b0a123de98318c2ff8069661721ce0c3794c34e/packages/ai/CHANGELOG.md#L59-L75)、[Model Hub selection 边界](https://github.com/yhyfhgs/dsh-model-hub/blob/2bb54c6543c8faac05d2b54162b33f1c80915e1a/README.md#L168-L185)。这些是维护风险与待验收面，不是本次运行失败的观测。

## <a id="quota-surface"></a>额度与其他用量数据

本次检查的 Model Hub Host 入口组装了认证、认证状态、provider、catalog 和 selection 服务，未发现独立的账号额度读取服务。README 的功能表也未声明剩余额度查询。它已有的 `QUOTA` 错误转换处理耗尽后的错误分类，主动额度查询属于另一服务；Codex token cost 显示为零则是订阅计价处理，应与账号剩余额度分别显示。

> 来源：[Host 实际服务组装](https://github.com/yhyfhgs/dsh-model-hub/blob/2bb54c6543c8faac05d2b54162b33f1c80915e1a/src/index.ts#L100-L141)、[功能列表](https://github.com/yhyfhgs/dsh-model-hub/blob/2bb54c6543c8faac05d2b54162b33f1c80915e1a/README.md#L24-L40)、[QUOTA 分类的版本记录](https://github.com/yhyfhgs/dsh-model-hub/blob/2bb54c6543c8faac05d2b54162b33f1c80915e1a/CHANGELOG.md#L82-L101)、[订阅 token cost 边界](https://github.com/yhyfhgs/dsh-model-hub/blob/2bb54c6543c8faac05d2b54162b33f1c80915e1a/README.md#L168-L180)。否定结论限定在上述固定版本及已检查的公开服务面。

界面与协议应分别命名以下数据，让读者从名称直接识别统计范围：

| 数据 | 能回答的问题 | 不能替代的东西 |
|---|---|---|
| 本地 session token/cost | 本客户端记录了多少输入、输出、估算成本 | 账号在其他客户端消费后的剩余额度 |
| 账号 token activity | 云端统计的活动与每日 token 分布 | 额度窗口是否准许继续用、何时重置 |
| subscription rate limits | 当前额度池、使用比例、窗口、重置时间与服务端限制状态 | 绝对剩余请求数或 API 账单 |
| credits / spend control | 服务端明确返回的 credit 余额与支出控制 | 未返回的数据；也不能直接换算为剩余 token |

> 来源：[Codex App Server 官方文档中的 rateLimits 与 account/usage/read 两节](https://developers.openai.com/codex/app-server)（查询于 2026-09-27）、[额度响应类型](https://github.com/openai/codex/blob/7f6c0f9387a0a60f396f61cc58f6b38bc98f2473/codex-rs/app-server-protocol/schema/typescript/v2/GetAccountRateLimitsResponse.ts#L8-L30)、[订阅插件分别解析 windows、credits 与 spend control](https://github.com/WSL043/dsh-codex-subscription/blob/6e55f21da9fade22f6edd1f9e789184426c83281/src/usage.js#L11-L156)。

## <a id="codex-quota"></a>Codex 额度的数据入口

### <a id="app-server"></a>官方 App Server

官方已提供 `account/rateLimits/read` 和 `account/rateLimits/updated`。快照中的 `rateLimits` 是兼容的单池视图，`rateLimitsByLimitId` 才能保留多个额度池；窗口的 `usedPercent`、`windowDurationMins`、`resetsAt` 分别表示已用百分比、分钟数和 Unix 秒。窗口长度及额度池数量均按响应读取。当前源码还返回 `ordinaryUsageAllowed`：空值表示未知，不能从百分比回落或重置时间已过推断已恢复使用。

这条 RPC 属于 **Codex App Server**；DSH 的 `/api` 和 Pi `Models` 是其他接口层。接入需要管理 Codex 进程与协议初始化，并确认查询的账号/workspace 与 DSH 推理使用的账号一致；直接读用户另一份 Codex 登录状态，会得到真实但属于错误账号的数字。

外部 token 模式 `chatgptAuthTokens` 可以由 Host 提供 access token 和 `chatgptAccountId`，官方文档仍标为 experimental，刷新通过反向请求交还 Host。它为保持原凭据 owner 提供了集成方向，Host 仍负责刷新与 DSH 集成。

> 来源：[官方 App Server 文档](https://developers.openai.com/codex/app-server)、[固定快照的额度/account 类型](https://github.com/openai/codex/blob/7f6c0f9387a0a60f396f61cc58f6b38bc98f2473/codex-rs/app-server-protocol/schema/typescript/v2/GetAccountRateLimitsResponse.ts#L8-L30)、[外部 token 登录参数](https://github.com/openai/codex/blob/7f6c0f9387a0a60f396f61cc58f6b38bc98f2473/codex-rs/app-server-protocol/schema/typescript/v2/LoginAccountParams.ts#L6-L22)。文档方法与字段描述已核对；没有启动 App Server 验证 DSH 集成。

### <a id="direct-usage"></a>Host 直接读取服务端 usage

当前官方 Codex backend client 仍有 `GET` usage：ChatGPT 路径形态为基址后的 `/wham/usage`，另一种 Codex API 路径形态为 `/api/codex/usage`。现成 DSH 订阅插件使用 `https://chatgpt.com/backend-api/wham/usage`，在 Host 添加 bearer 与 `chatgpt-account-id`，拒绝重定向，并只返回解析后的额度投影。**这说明存在可复核的实现，不说明它是对第三方承诺长期稳定的公共 billing API。** 不要把浏览器 Cookie、HTML 抓取或任意可配 URL 作为默认查询方式。

直接查询少一个 Codex 进程，适合轻量 DSH companion；代价是自行跟进认证、字段与内部端点变化。固定来源与账号校验必须放在 Host，不能把 bearer 发到浏览器，也不能把普通推理 `baseURL` 自动拼接成 usage URL 后带上凭据。

> 来源：[官方后端 GET 与两种 path style](https://github.com/openai/codex/blob/7f6c0f9387a0a60f396f61cc58f6b38bc98f2473/codex-rs/backend-client/src/client/rate_limit_resets.rs#L22-L130)、[现成插件的 endpoint 和解析器](https://github.com/WSL043/dsh-codex-subscription/blob/6e55f21da9fade22f6edd1f9e789184426c83281/src/usage.js#L1-L156)、[Host headers、超时、拒绝重定向与错误处理](https://github.com/WSL043/dsh-codex-subscription/blob/6e55f21da9fade22f6edd1f9e789184426c83281/src/usage.js#L185-L223)。

### <a id="existing-option"></a>现成插件与复用边界

`dsh-codex-subscription@2.2.2` 是值得单独验收的现成 Codex 方案：manifest 已列出 DSH `0.1.7-rc.2`，额度 reader 包含多池解析、60 秒缓存、15 秒超时、失败退避、同请求合并及 generation 失效处理。这里只确认实现与兼容声明，没有复跑其测试或实际安装。

它自己的 `openai-codex` 路由使用 `OPENAI_CODEX_SUBSCRIPTION_OAUTH` credential ref，并有 `codex-subscription/accounts` vault；这与官方 `llm-pi-ai` record 不是同一身份契约。复用 DSH credential service 与复用同一登录记录是两个条件；叠装前先验证身份映射和路由冲突。可借鉴其 parser、缓存与 UI 状态测试思路，而不是为了一个额度组件复制整套 OAuth、切号或模型路由。

> 来源：[版本与兼容声明](https://github.com/WSL043/dsh-codex-subscription/blob/6e55f21da9fade22f6edd1f9e789184426c83281/package.json#L1-L100)、[额度 reader](https://github.com/WSL043/dsh-codex-subscription/blob/6e55f21da9fade22f6edd1f9e789184426c83281/src/usage.js#L1-L7)、[请求合并与失效](https://github.com/WSL043/dsh-codex-subscription/blob/6e55f21da9fade22f6edd1f9e789184426c83281/src/usage.js#L225-L269)、[插件自身的 credential ref 与 vault](https://github.com/WSL043/dsh-codex-subscription/blob/6e55f21da9fade22f6edd1f9e789184426c83281/src/index.js#L41-L50)。

## <a id="integration"></a>建议的 DSH 集成边界

**默认方向：保留官方 adapter 和凭据，补一个登录/额度 companion；额度先实现 Codex。** 登录 flow 按已安装的官方注册表枚举，额度能力另外按 provider/credential owner 注册。Codex 可查询不能推出 Anthropic、Copilot、Kimi、Qwen 都有相同接口；其他 provider 未核实的数据源显示“尚未接入”，不要静默调用 Codex 端点，也不要把 API-key 账号误报成订阅 OAuth。

```text
官方 Models provider-card / footer
          │ 仅交互消息与脱敏快照
          ▼
Companion Host：登录尝试桥 / 额度缓存与 provider reader
          ├─ ctx.authorization → 官方 Pi flow → 官方 credential record
          └─ 同一 credential owner 的有效访问凭据
                    ├─ Codex usage reader（轻量，跟进内部端点）
                    └─ Codex App Server（可选，需进程和身份桥）
```

这里存在一个必须显式完成的接口工作：官方当前顶层导出 `recordKeyFor`，但内部 `credentialStoreFrom`、`authContextFrom` 并没有作为同一顶层公共刷新接口导出。找到 record 之后，还需要 owner 解析出可供额度请求使用、已刷新的 bearer。应先在凭据 owner 一侧设计并验证窄的 Host-only resolver，或提供由 owner 执行受限查询的服务；**这是一项建议新增的契约；当前实现没有提供这里所需的公共刷新接口**。

官方 Pi credential store 把 refresh 的网络过程放在 `credentials.modifyRecord` 的互斥范围内。额度查询必须复用这条生命周期，不能另存 `auth.json`、另起轮询刷新，或仅复制 grant 后自行写回。保留 native `codex` 的部署则要接其 native owner，不能用官方 `recordKeyFor('openai-codex')` 去读取它。

> 来源：[官方顶层导出与内部 auth imports](https://github.com/deepseek-ai/deepseek-harness/blob/477b4f420553e8a52c2fbccc464d7561b239c443/packages/llm/llm-pi-ai/src/index.ts#L64-L95)、[credential record 转换、scope 与刷新互斥](https://github.com/deepseek-ai/deepseek-harness/blob/477b4f420553e8a52c2fbccc464d7561b239c443/packages/llm/llm-pi-ai/src/auth.ts#L23-L185)。实现窄服务时仍需审查实际注入、取消和刷新导出方式；不建议依赖未发布的源码私有路径。

建议的只读额度契约至少保留：provider/owner、脱敏账号标识、数据来源、采集时间、状态、按 limit ID 分组的窗口，以及服务端明确返回的限制许可/credit 信息。以下为设计要求，不是声称现有插件已经满足：

| 方面 | 要求 |
|---|---|
| 状态语义 | 分开 `ok`、`stale`、`auth-required`、`unsupported`、`unavailable`；缺失字段不是 0，不可把“未接入”伪装成额度耗尽 |
| 额度池 | 保留 limit ID 与名称；无可靠模型到池映射时展示全部池，不把普通池强套到 Spark/Reserve 等路线；滚动通知只合并已给出的信息或重新读取完整快照 |
| 时间与数值 | 明确秒/毫秒；不把窗口固定成 5 小时/7 天；仅对合法已知的 usedPercent 派生剩余比例；保留采集时间，不用倒计时归零宣称恢复 |
| 并发与缓存 | 以 owner、账号/workspace、凭据 generation 隔离；同账号查询合并；注销、切号、Host 重连失效，迟到响应不得复活旧账号数据 |
| 网络与错误 | 限制来源、超时、大小与重试；429 尊重 Retry-After；401/403 返回重新认证提示，不把原始响应、token 或账号详情塞进错误日志 |
| UI 与权限 | 手动刷新加可见时低频刷新；陈旧数据标时间；沿用本地授权边界。远程访问另设计权限，不通过删除 loopback 检查“兼容” |
| 只读边界 | 查询不能自动换模型、换账号、消费 earned reset、加购 credits、发送额度邮件或触发付费推理 |

> 参考：[官方 rolling notification 的稀疏更新语义](https://github.com/openai/codex/blob/7f6c0f9387a0a60f396f61cc58f6b38bc98f2473/codex-rs/app-server-protocol/schema/typescript/v2/AccountRateLimitsUpdatedNotification.ts#L1-L24)、[普通用量许可与账号字段](https://github.com/openai/codex/blob/7f6c0f9387a0a60f396f61cc58f6b38bc98f2473/codex-rs/app-server-protocol/schema/typescript/v2/GetAccountRateLimitsResponse.ts#L8-L30)、[Model Hub loopback 通道](https://github.com/yhyfhgs/dsh-model-hub/blob/2bb54c6543c8faac05d2b54162b33f1c80915e1a/src/rpc/router.ts#L93-L111)。

## <a id="adoption"></a>采用方式与验收

| 使用目标 | 建议路线 | 必须先验证的代价 |
|---|---|---|
| 保留官方路由，只缺登录和额度 | 官方插槽 companion，Codex reader 先行 | Host 凭据 resolver/刷新接口与端点策略尚需实现；不是现成可安装的承诺 |
| 已依赖 Model Hub 的目录整理、选择器或子代理策略 | 先保留现有能力，在隔离 profile 验证新版 Host，再增加同 owner 的额度服务及 Model Hub UI 集成 | 不能只注入官方页面插槽；要处理 peer 差距、native 目录和双重 selection 边界 |
| 主要需要完整 Codex 订阅体验 | 独立评估 `dsh-codex-subscription@2.2.2` | 独立凭据约定、路由占用与迁移；不得把 manifest 声明当作本机已验证 |
| 不希望承担内部 usage 端点变化 | Codex App Server 或官方账号用量界面 | App Server 多一层进程/身份桥；官方界面可核对数字，但不能自动给 DSH 卡片供数 |

实现顺序宜是：锁定目标 DSH/Pi 组合与真实路由 owner；完成只读 reader 和离线 fixtures；接官方卡片/页尾；最后才讨论迁移 native `codex` 或调整 Model Hub 替换策略。迁移应逐项映射默认模型、会话选择、picker、子代理与模型覆盖，先备份配置并核对新登录账号，不以 alias 或复制 grant 代替迁移，也不自动删除旧凭据。

验收至少覆盖下面几组，执行结果必须另记，不能把这张表当成已通过：

| 验收面 | 场景与通过条件 |
|---|---|
| 契约与打包 | 用目标 DSH/Pi 组合编译/加载 Host 与 Client；确认真实版本、导出、插槽 key、启用/停用后官方界面恢复；不运行生产 profile 的升级 |
| 额度 fixtures | 单池/多池、缺窗口、未知池、0/100%、缺 reset、秒/毫秒、credits、普通用量许可未知/拒绝；缺值不会显示为满额或无限 |
| 生命周期 | 注销、切号、凭据刷新、Host 重连、并发读取和取消；迟到请求不回填旧身份；推理与查询并发时只有 owner 执行刷新 |
| 错误与安全 | 401/403/429、超时、非 JSON、畸形字段、重定向、非许可 URL；浏览器/RPC/日志/缓存均无 bearer、refresh token、Cookie 或原始 grant |
| 集成与语义 | 官方 openai-codex 与 native codex 分开；未支持 provider 有明确状态；Model Hub 存在时不误用已被禁用的官方槽位；额度组件不改 Core selection |
| 经单独授权的真人账号验收 | 在隔离环境核对同一账号/workspace 的官方额度页与查询结果、缓存时间、刷新和注销；无须通过一次付费生成来证明额度可读 |

**本专题的证据范围是上述固定版本的源码调研与设计判断。** 已核实官方后端复用的适用范围、Models 插槽、具体目录/依赖差距、现成额度实现和官方协议；未验证真实账号可用性、插件在 DSH `0.1.7-rc.2` 的运行兼容性、其他 provider 的额度端点或 npm 最新发布状态。
