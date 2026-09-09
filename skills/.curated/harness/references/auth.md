# Coding agent 登录鉴权：凭据存储与跨机 / 跨客户端复用

**当前范围**：本文目前只覆盖 **GitHub Copilot**（Copilot CLI / Copilot SDK / pi 的 `github-copilot` provider）；文件名 `auth.md` 是通用的，后续其他厂商（Codex / Anthropic 等）的登录鉴权可按厂商分节续写进来。

本文说明 Copilot CLI、Copilot SDK、pi 的登录态怎样保存、读取和跨环境复用。环境变量 token 适合非交互注入，但接入其他客户端时还要分别核对**凭据类型、账号端点和模型请求协议**；仅凭 `gho_` 前缀或一次请求失败，不能判断 token 必须经过交换。

> 置信度：🔬 = 实测，并就近说明版本与覆盖范围；📖 = 读源码，公开代码锁定版本，Copilot CLI 闭源产物用版本和稳定字面量定位。个人主机名、账号与路径使用占位符。

## <a id="cli-storage"></a>Copilot CLI 登录凭据的存储（app.js）

`/login` 成功后的保存逻辑（去混淆后的结构；混淆符号 `jke`/`Uv`/`Ugi` 是 esbuild 产物、随版本漂，用字面量锚点重定位）：

```js
async function saveLogin(client, user, configDir, opts){
  if(!await store.storeToken(user.token, user.host, user.login, configDir)){        // ① 先写系统安全库
    if(!await (opts?.promptForPlaintextConsent ?? promptPlaintext)()) return false; // ② 否则征询明文同意
    await store.storeCurrentTokenInConfig(user.host, user.login, configDir);        // ③ 明文兜底写进 config
  }
  return await client.loginUser(user.host, user.login, user.token), true;
}
```

- **① 主路径 = 原生安全库**：native napi 模块（`tokenStoreCreate()`），UI 文案自证 "recommended secure storage (keychain, keyring, or credential manager)"。Linux 上即 secret-service（libsecret / gnome-keyring）。JS 只调 native、看不到明文，所以 `~/.copilot/config.json` 正常情况下**没有** token。
- **② 明文兜底前提苛刻**：征询函数开头是 `if(!process.stdin.isTTY||!process.stdout.isTTY)return false`——**非 TTY（headless / 服务 / SSH 管道）直接拒绝**，且要用户手选 "Yes, store in plain text (insecure)"。
- **③ 兜底才落文件**：`storeCurrentTokenInConfig` → native `tokenStoreStoreCurrentTokenInConfig(configDir, …)`，configDir = `COPILOT_HOME ?? ~/.copilot`。
- 安全库和明文都没成时报 "Login succeeded, but the token was not saved. Install a system keychain or rerun login and accept plaintext storage."

读取端多来源：环境变量、`store.getToken(host,login)`（安全库 / 明文里存下的登录）、`gh` CLI 登录态。环境变量优先级写死为 `COPILOT_GITHUB_TOKEN` > `GH_TOKEN` > `GITHUB_TOKEN`（native `authFindClassicPatEnvVar`；帮助文案原话 "checked in order of precedence"）。另有一处启动时 `if(!GITHUB_COPILOT_GITHUB_TOKEN && GITHUB_TOKEN) GITHUB_COPILOT_GITHUB_TOKEN=GITHUB_TOKEN`。

📖 app.js `1.0.72-1`（闭源 bundle，无公开源码仓可链）。稳定字面量锚点：`COPILOT_GITHUB_TOKEN`、`storeCurrentTokenInConfig`、`authFindClassicPatEnvVar`、`"System keychain unavailable. Store token in plaintext config file?"`、`"the token was not saved"`。

🔬 一台桌面机上实测：gnome-keyring 守护进程在跑、`org.freedesktop.secrets` 也可达，但从非图形会话（SSH / web 终端）看，`login`（默认）collection 是**锁定**的（`busctl --user get-property org.freedesktop.secrets /org/freedesktop/secrets/collection/login org.freedesktop.Secret.Collection Locked` → `b true`）——非图形登录没有 PAM 自动解锁。往锁定的 keyring 写会失败，copilot 遂走[明文兜底](#cli-storage)（这条还需 TTY + 手动同意），`config.json` 里于是出现：

```jsonc
{ "copilotTokens": { "https://github.com:<login>": "gho_…(40 char 明文)" },
  "loggedInUsers": [ { "host": "https://github.com", "login": "<login>" } ] }
```

## <a id="reuse"></a>跨机 / 跨用户复用 Copilot 登录

- **交互登录的凭据基本搬不动**：桌面上它在**每用户的 secret-service keyring** 里，按该用户登录密码加密；非图形会话（SSH / web 终端）里该 keyring 常处于**锁定**态（🔬 实测 `login` collection `Locked=true`，无 PAM 自动解锁），既读不出也写不进。把 A 用户的 keyring 拷给 B 用户也解不开。
- **`config.json` 里的明文 token 理论可搬**，但它只在[明文兜底](#cli-storage)触发时才存在（有 TTY + 手动同意，或 headless 且 keychain 不可用那条）。
- **可移植正路 = 环境变量 token**：鉴权绑的是 **GitHub 账号 + Copilot 席位**，不绑 Linux 用户 / 机器。给目标环境注入即可非交互登录成同一账号：

  ```bash
  export COPILOT_GITHUB_TOKEN="<token>"   # 或 GH_TOKEN / GITHUB_TOKEN，按此优先级
  ```

  🔬 把上面那个明文 `gho_` 当 `COPILOT_GITHUB_TOKEN` 注入另一台机的 Copilot CLI → 补全成功；env 鉴权**不落盘**（目标机 `config.json` 事后无 `copilotTokens`）。
- **同一席位给不同的人用违反授权**——"复用"仅指复用同一个 GitHub 账号自身。
- token 类型有讲究，不是任意 `gho_` 都行，见 [env 变量接受的 token 类型](#token-type)。

## <a id="sdk-isolation"></a>Copilot SDK 的 home 与凭据 / 会话隔离

`@github/copilot-sdk` 是 spawn 官方 Copilot runtime 来干活；**不设 `baseDirectory` 时，runtime 用 `~/.copilot`**——与 CLI 同一份 `config.json`、`session-store.db`、`session-state/`、trustedFolders、MCP 配置**以及凭据**。

- `baseDirectory` 文档原话 "Sets the COPILOT_HOME … When not set, the runtime defaults to ~/.copilot"；运行时 `env.COPILOT_HOME = this.options.baseDirectory`（仅当设置了才写）。
- 会话状态落 `COPILOT_HOME/session-state/{sessionId}`（multi-tenancy 文档 + 仓库 instructions "Infinite sessions … persist to ~/.copilot/session-state/{sessionId}"）。

隔离开关（源码 + 官方 multi-tenancy 文档）：

| 开关 | 作用 |
|---|---|
| `baseDirectory` | 设 `COPILOT_HOME`，把 config / session-state / 文件凭据整体隔到独立目录；连 `forUri` 外部 runtime 时被忽略，须改在 runtime 进程上设 |
| `mode:"empty"` | 关掉 CLI 式 ambient 工具，并置 `COPILOT_DISABLE_KEYTAR=1`——**不碰进程 / OS 级共享的系统 keychain**，凭据落 `COPILOT_HOME` 下文件；构造时强制要求提供持久化位置（`baseDirectory` 或 `sessionFs`） |
| 每会话 `gitHubToken` | 鉴权钉到请求用户；给了 token 时 `useLoggedInUser` 默认变 `false`，不读 stored / gh 登录态 |
| `sessionFs` | 会话文件 I/O 改道（不落本地盘） |
| 每会话 `configDirectory` | 单会话覆盖 config / state 目录 |

**要点**：光设 `baseDirectory` 还不彻底——默认 `mode:"copilot-cli"` 仍走 OS keychain（跨进程共享）；要连凭据一起隔离必须配 `mode:"empty"`（它才置 `COPILOT_DISABLE_KEYTAR=1`）。

完全不共享的最小配方：

```js
import { CopilotClient, approveAll } from "@github/copilot-sdk";
const client = new CopilotClient({
  mode: "empty",
  baseDirectory: "/var/lib/app/copilot/inst-1",   // COPILOT_HOME → 独立 config/凭据/session-state
  gitHubToken: process.env.COPILOT_GITHUB_TOKEN,   // useLoggedInUser 自动 false
});
await client.start();
const s = await client.createSession({ onPermissionRequest: approveAll });
```

🔬 SDK 不设 `baseDirectory`，注入同一 `gho_` 为 `COPILOT_GITHUB_TOKEN` 后，`claude-sonnet-5` 返回 `AUTH_OK`。这证明该凭据能由官方 runtime 使用；仅凭成功结果不能判定内部是否发生 token 交换。SDK 的接入形态见 [sdk.md](sdk.md)。

📖 copilot-sdk 锁 `0d563bd`：[`types.ts` baseDirectory `:296`](https://github.com/github/copilot-sdk/blob/0d563bdd181fd82b6563f40cefd9f5074f0c0472/nodejs/src/types.ts#L296)、[`gitHubToken`/`useLoggedInUser` `:314-322`](https://github.com/github/copilot-sdk/blob/0d563bdd181fd82b6563f40cefd9f5074f0c0472/nodejs/src/types.ts#L305-L322)、[`configDirectory` `:1954`](https://github.com/github/copilot-sdk/blob/0d563bdd181fd82b6563f40cefd9f5074f0c0472/nodejs/src/types.ts#L1949-L1955)、[`client.ts` COPILOT_HOME + DISABLE_KEYTAR `:2341-2348`](https://github.com/github/copilot-sdk/blob/0d563bdd181fd82b6563f40cefd9f5074f0c0472/nodejs/src/client.ts#L2335-L2350)、[empty-mode 强制持久化校验 `:743`](https://github.com/github/copilot-sdk/blob/0d563bdd181fd82b6563f40cefd9f5074f0c0472/nodejs/src/client.ts#L733-L748)、[multi-tenancy 文档](https://github.com/github/copilot-sdk/blob/0d563bdd181fd82b6563f40cefd9f5074f0c0472/docs/setup/multi-tenancy.md)。clone：`git clone https://github.com/github/copilot-sdk.git`。

## <a id="pi-copilot"></a>pi 的 Copilot 鉴权路径（env apiKey vs /login oauth）

pi 的 `github-copilot` provider 提供 API key 和 OAuth 两种认证处理器；选择哪条路径由实际凭据类型决定：

```ts
apiKey: envApiKeyAuth("GitHub Copilot token", ["COPILOT_GITHUB_TOKEN"]),
oauth:  lazyOAuth({ name: "GitHub Copilot", load: loadGitHubCopilotOAuth }),
```

- **API key / 环境变量**：`envApiKeyAuth.resolve` 返回原值作为 bearer，不交换 token，也不查询账号端点。0.85.1 的 provider 默认主机仍是 `api.individual.githubcopilot.com`。环境变量解析本身不写盘；通过 `/login` 的 API key 选项输入值，则会保存为 `api_key` 凭据。
- **OAuth 登录与刷新**：设备码流程取得 GitHub token，再访问 `copilot_internal/v2/token` 取得短时 Copilot token，并从其中的 `proxy-ep` 推导 API 主机。登录时读取账号模型目录、按需启用模型策略，保存 OAuth 凭据及 `availableModelIds`；以后刷新继续沿 OAuth 路径处理。
- **解析顺序**：请求级 key 覆盖 → 已存凭据 → 环境变量。已存 OAuth 凭据刷新失败不会静默回退到环境变量。

> 📖 [pi 0.85.1 的 provider](https://github.com/earendil-works/pi/blob/v0.85.1/packages/ai/src/providers/github-copilot.ts#L9-L17)、[API key 登录与解析](https://github.com/earendil-works/pi/blob/v0.85.1/packages/ai/src/auth/helpers.ts#L9-L29)、[凭据优先级和刷新](https://github.com/earendil-works/pi/blob/v0.85.1/packages/ai/src/auth/resolve.ts#L35-L112)。pi 的交互与非交互入口见 [pi reference](pi.md#copilot-sub)。

> 非交互实测还曾遇到 `pi -p` 等待 stdin 结束而没有输出；没有管道输入时显式接 `</dev/null`，避免把输入未结束误判成认证失败。

## <a id="copilot-endpoints"></a>Copilot 账号端点

`endpoints.api` 是账号元数据里的 API 根地址，与 `copilot_plan`、账号组织身份、token 前缀分别记录。连接时采用账号返回的地址；不能根据“个人”“企业”或 `internal` 标签拼出主机名。`endpoints.proxy`、`telemetry` 等字段也不能直接当成模型 API 地址。

已知地址不止 individual 和 enterprise。下表区分正式主机、元数据样本、客户端默认值和连接观察，不把它们混成 `/copilot_internal/user` 的完整返回值枚举：

| API 根地址 | 证据与含义 |
|---|---|
| `https://api.individual.githubcopilot.com` | GitHub 正式列出的 Individual 主机；另有[公开 `/user` 响应样本](https://github.com/NousResearch/hermes-agent/issues/27836)包含此 `endpoints.api` |
| `https://api.business.githubcopilot.com` | GitHub 正式列出的 Business 主机；[账号端点发现实现报告](https://github.com/can1357/oh-my-pi/pull/8510)描述 `/user` 返回此地址 |
| `https://api.enterprise.githubcopilot.com` | GitHub 正式列出的 Enterprise 主机；下文 2026-09-09 实测的 `/user` 返回值 |
| `https://api.githubcopilot.com` | 官方客户端底层库的通用默认/回退地址；本次成功访问不证明它就是该账号元数据的返回值 |
| `https://copilot-api.<tenant>.ghe.com` | GHE.com 数据驻留租户的客户端连接地址形式，见[官方 CLI 仓库中的连接日志报告](https://github.com/github/copilot-cli/issues/4527)；该报告不是 `/user` 返回字段的完整规范 |

> 📖 [GitHub 文档列出的三类 API 主机](https://github.com/github/docs/blob/59a4d1dbb271848f66c5bc141b1047950a329f8e/data/reusables/copilot/cloud-agent-required-hosts.md#L3-L5)。通用默认值来自 [`@vscode/copilot-api` 0.2.19](https://unpkg.com/@vscode/copilot-api@0.2.19/dist/index.js)，其 `_getCAPIUrl` 使用元数据中的 `endpoints.api`，缺失时回退到 `https://api.githubcopilot.com`；[VS Code 的接入位置](https://github.com/microsoft/vscode-copilot-chat/blob/5863f5a7088958050792b5dccbe8b46c6e13eccc/src/platform/endpoint/common/capiClient.ts#L6-L20)。表中的第三方响应和实现报告只证明对应样本，不据此推广其其他认证结论。

Business 和 Enterprise 是不同的 Copilot 订阅。一个 GitHub enterprise account 可以同时包含使用两种订阅的组织，因此“属于企业”不唯一决定 API 主机。官方 VS Code 客户端的 `isInternal` 与 `endpoints` 也是分别读取的属性，前者不承担主机选择职责。

> 📖 [GitHub 关于混用 Business/Enterprise 与网络隔离的说明](https://github.com/github/docs/blob/59a4d1dbb271848f66c5bc141b1047950a329f8e/data/reusables/copilot/sku-isolation.md#L13-L34)、[独立的 isInternal 与 endpoints 属性](https://github.com/microsoft/vscode-copilot-chat/blob/5863f5a7088958050792b5dccbe8b46c6e13eccc/src/platform/authentication/common/copilotToken.ts#L117-L130)。

公开客户端将端点的 `api` 建模为字符串，而不是固定枚举；配置覆盖也可能替代元数据地址。扩展需要明确处理字段缺失、无效 URL 和不受信任的主机，不能把“能连接某地址”“防火墙列出了某地址”和“账号实际返回某地址”视为同一事实。

> 📖 [Endpoints 类型](https://github.com/microsoft/vscode-copilot-chat/blob/5863f5a7088958050792b5dccbe8b46c6e13eccc/src/platform/authentication/common/copilotToken.ts#L286-L291)、[字符串校验](https://github.com/microsoft/vscode-copilot-chat/blob/5863f5a7088958050792b5dccbe8b46c6e13eccc/src/platform/authentication/common/copilotToken.ts#L400-L405)、[配置覆盖与元数据的优先级](https://github.com/microsoft/vscode-copilot-chat/blob/5863f5a7088958050792b5dccbe8b46c6e13eccc/src/platform/endpoint/node/domainServiceImpl.ts#L45-L64)。这里的 Endpoints 类型关联 `/copilot_internal/v2/token` 的响应，不是 GitHub 发布的 `/copilot_internal/user` 完整 schema，不能据此声称已证明该接口的所有可能值。

在 github.com 账号场景，可以用现有 GitHub 凭据读取 `https://api.github.com/copilot_internal/user` 的 `endpoints.api`。这次读取是账号元数据发现，不是铸造或交换短时 Copilot token。接入带数据驻留的企业实例时，还需核对其 GitHub API 根地址，不能沿用 github.com 的发现入口。

GHE.com 数据驻留属于 GitHub Enterprise Cloud 的租户域场景。GitHub 文档要求放行 `https://<tenant>.ghe.com` 和 `https://*.<tenant>.ghe.com`，并将其 GitHub API 根地址示例写为 `https://api.<tenant>.ghe.com`；`copilot-proxy.<tenant>.ghe.com` 是另一类服务，不能拿来替代 `endpoints.api`。支持这类实例需要受信任的租户配置、对应的账号发现入口和返回地址校验，不能靠关闭主机校验或退回公共默认地址来实现。

> 📖 [Copilot on GHE.com 的主机范围](https://github.com/github/docs/blob/59a4d1dbb271848f66c5bc141b1047950a329f8e/content/copilot/reference/copilot-allowlist-reference.md#L59-L76)、[数据驻留实例的 GitHub API 根地址](https://github.com/github/docs/blob/59a4d1dbb271848f66c5bc141b1047950a329f8e/content/admin/data-residency/about-github-enterprise-cloud-with-data-residency.md#L87-L99)。这些是租户域约束，不是可以按地区名称自行拼接的模型 API 地址表。

> 🔬 2026-09-09：同一枚由 Copilot CLI 环境变量使用的 `gho_`，账号发现返回 `endpoints.api = https://api.enterprise.githubcopilot.com`。📖 CLI 1.0.83 的 bundle 使用配置覆盖、`COPILOT_API_URL`、`copilotUser.endpoints.api` 选择地址；native 产物包含 `endpoint_refresh.rs` 和 `re-resolved CAPI endpoint after 421`。这些证据说明该版本具有账号端点选择及 421 重发现路径，不是所有账号的地址枚举。

## <a id="token-type"></a>Token 类型与请求失败的判定

`gho_` 只能说明 GitHub OAuth token 的格式，不能单独决定它在哪个 Copilot 主机、哪种客户端流程下可用。排障时分别读取账号端点、模型目录的 `supported_endpoints`、策略状态和原始 HTTP 错误：

| 现象 | 优先核对 |
|---|---|
| `421 Misdirected Request` | 凭据对应的账号端点是否与请求主机一致 |
| `400 unsupported_api_for_model` | 模型要求 `/responses`、`/chat/completions` 还是其他协议 |
| `401` / `403` | 凭据、权限、账号准入及被调用接口；不能只凭状态码判定必须交换 token |
| `model_not_supported` | 模型可用性、策略、客户端和认证上下文；不是单一根因的证明 |

> 🔬 2026-09-09，DSH 0.1.2-rc.1、pi-ai 0.85.1、Copilot CLI 1.0.83：同一凭据请求 individual 主机得到 421；采用账号返回的 enterprise 主机后，Astra 请求 `/chat/completions` 得到 400；改为 `/responses` 后成功。通用主机也可用，但该次账号返回值是 enterprise，不能把通用主机的成功记成账号发现结果。插件实现随后以原凭据、既有请求头和 `xhigh` 完成一次流式工具往返。

> 旧环境中曾观察到不同 `gho_` 的直连结果不同，以及直接请求 `copilot_internal/v2/token` 返回 403。这些样本不足以支持“Copilot CLI 的所有 `gho_` 必须先交换”或“第三方客户端普遍无法调用”的结论；应保留请求条件，而非据此推广认证规则。

真实模型请求只覆盖最小成功路径；凭据错误、端点失配、超时、取消等分支用模拟响应验证，避免轮询多个错误主机或反复制造失败请求。Model Hub 的目录修正、effort 传参和插件实现由该项目的文档维护。

## <a id="matrix"></a>客户端 × 复用方式速查

| | env token（`COPILOT_GITHUB_TOKEN` 等） | 交互登录存哪 | 跨机搬运 |
|---|---|---|---|
| Copilot CLI | ✅ 读，优先级 `COPILOT_GITHUB_TOKEN > GH_TOKEN > GITHUB_TOKEN` | keychain 优先 / 明文 `config.json` 兜底 | env token；keychain 不可搬 |
| Copilot SDK | ✅ 透传给 spawn 的 runtime | 同 CLI（共享 `~/.copilot`，除非 `baseDirectory` + `mode:"empty"`） | env token / 隔离 `COPILOT_HOME` |
| pi（`github-copilot`） | ✅ 但**原样当 bearer**，须是 API 直接接受的 token（见 [token 类型](#token-type)） | `/login` 交换后落 `~/.pi/agent/auth.json` | 拷 `auth.json`，或用 env 给一个 API 直连可用的 token |
