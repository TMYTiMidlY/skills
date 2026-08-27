# Coding agent 登录鉴权：凭据存储与跨机 / 跨客户端复用

**当前范围**：本文目前只覆盖 **GitHub Copilot**（Copilot CLI / Copilot SDK / pi 的 `github-copilot` provider）；文件名 `auth.md` 是通用的，后续其他厂商（Codex / Anthropic 等）的登录鉴权可按厂商分节续写进来。

Copilot 订阅的登录态在 Copilot CLI、Copilot SDK、pi（`github-copilot` provider）三处各自怎么存、怎么读，以及能不能把一台机上的 Copilot 登录搬到另一台机 / 另一个系统用户 / 另一个客户端。一句话结论：**环境变量 token 是唯一干净的可移植方式**；但"哪个 token 直接喂进去能用"取决于 token 类型——标准 GitHub OAuth token（如 `gh auth token` 给的）能被 Copilot API 直接接受，而 Copilot CLI 自己存的那个 `gho_` 必须先经内部交换才可用（见 [env 变量接受的 token 类型](#token-type)）。

> 置信度：🔬 = 跨机实测（独立 `COPILOT_HOME` / 全新客户端状态）｜ 📖 = 读源码（pi / copilot-sdk 锁 commit；Copilot CLI 闭源、锁 bundle 版本并用字面量锚点）。个人主机名 / 账号已隐去为 `<login>` 等占位符。

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

🔬 SDK 不设 `baseDirectory` + 注入 `COPILOT_GITHUB_TOKEN`（同一 `gho_`）→ `claude-sonnet-5` 回 `AUTH_OK`（官方 runtime 内部完成 github→copilot 交换）。SDK 的接入形态、API 形状本身见 [sdk.md](sdk.md)。

📖 copilot-sdk 锁 `0d563bd`：[`types.ts` baseDirectory `:296`](https://github.com/github/copilot-sdk/blob/0d563bdd181fd82b6563f40cefd9f5074f0c0472/nodejs/src/types.ts#L296)、[`gitHubToken`/`useLoggedInUser` `:314-322`](https://github.com/github/copilot-sdk/blob/0d563bdd181fd82b6563f40cefd9f5074f0c0472/nodejs/src/types.ts#L305-L322)、[`configDirectory` `:1954`](https://github.com/github/copilot-sdk/blob/0d563bdd181fd82b6563f40cefd9f5074f0c0472/nodejs/src/types.ts#L1949-L1955)、[`client.ts` COPILOT_HOME + DISABLE_KEYTAR `:2341-2348`](https://github.com/github/copilot-sdk/blob/0d563bdd181fd82b6563f40cefd9f5074f0c0472/nodejs/src/client.ts#L2335-L2350)、[empty-mode 强制持久化校验 `:743`](https://github.com/github/copilot-sdk/blob/0d563bdd181fd82b6563f40cefd9f5074f0c0472/nodejs/src/client.ts#L733-L748)、[multi-tenancy 文档](https://github.com/github/copilot-sdk/blob/0d563bdd181fd82b6563f40cefd9f5074f0c0472/docs/setup/multi-tenancy.md)。clone：`git clone https://github.com/github/copilot-sdk.git`。

## <a id="pi-copilot"></a>pi 的 Copilot 鉴权路径（env apiKey vs /login oauth）

pi 的 `github-copilot` provider 有**两个互不相干的 auth 成员**：

```ts
apiKey: envApiKeyAuth("GitHub Copilot token", ["COPILOT_GITHUB_TOKEN"]),
oauth:  lazyOAuth({ name: "GitHub Copilot", load: loadGitHubCopilotOAuth }),
```

- **env / apiKey 路径**：`envApiKeyAuth.resolve` 只返回 `{ apiKey: <env值> }`——**原样当 bearer 打 `baseUrl: https://api.individual.githubcopilot.com`，不做任何交换、不落盘**（`copilot_internal` 只出现在 oauth 路径）。所以"pi 会换凭据、写 auth.json 盖过 env"是**错的**：env 路径既不交换也不持久化。
- **oauth `/login` 路径**：设备码（CLIENT_ID 是 base64 解出的 **VSCode Copilot client_id** `Iv1.b507a08c87ecfe98`，scope `read:user`）→ `refreshGitHubCopilotAccessToken` 打 `api.github.com/copilot_internal/v2/token` 换 **Copilot token**（`tid=…;exp=…;proxy-ep=…`）→ `getBaseUrlFromToken` 取每账号 proxy 端点 → `enableAllGitHubCopilotModels`（逐模型 POST `/models/{id}/policy {state:"enabled"}`，注释 "required for some models (like Claude, Grok)"）→ 落 `~/.pi/agent/auth.json`。
- **解析顺序**：stored `auth.json` 凭据 > 环境变量（已存凭据盖过 env）。
- 坑：`pi -p`（非交互）不接 `</dev/null` 会**挂起等 stdin**，表现为无输出的假死。

📖 pi 锁 `8479bd8`：[provider 两个 auth 成员 `providers/github-copilot.ts:13-17`](https://github.com/earendil-works/pi/blob/8479bd84743e8889f728acb21a62794102db0529/packages/ai/src/providers/github-copilot.ts#L13-L17)、[`envApiKeyAuth` 只回 `{apiKey}` `auth/helpers.ts:9-26`](https://github.com/earendil-works/pi/blob/8479bd84743e8889f728acb21a62794102db0529/packages/ai/src/auth/helpers.ts#L9-L26)、[CLIENT_ID `:17` / copilotTokenUrl `:66` / getBaseUrlFromToken `:75-92` / 换取 `:251-286` / enableGitHubCopilotModel（Claude·Grok 注释）`:301-327`](https://github.com/earendil-works/pi/blob/8479bd84743e8889f728acb21a62794102db0529/packages/ai/src/utils/oauth/github-copilot.ts#L251-L327)。pi runtime 全貌见 [pi.md](pi.md)。

## <a id="token-type"></a>env 变量接受的 token 类型

同一账号、同为 40 字符 `gho_`，喂给依赖 env 的客户端（pi 的 apiKey 路径 / 任何直连 Copilot API 的调用）结果却相反：

| token 来源 | 直接当 `COPILOT_GITHUB_TOKEN` | 结果 🔬 |
|---|---|---|
| `gh auth token`（gh CLI 的 GitHub OAuth token，scopes `repo/read:org/gist/admin:public_key`） | 直连 bearer | ✅ pi 补全通（`claude-haiku-4.5` → AUTH_OK） |
| Copilot CLI 存的 `gho_` | 直连 bearer | ❌ 全模型 `model_not_supported` |

- `api.individual.githubcopilot.com` **直接接受标准 GitHub OAuth token**（无需 copilot 专属 scope，服务端按用户身份判 Copilot 权益）；Copilot CLI 存的那个 token 设计上**要先经 `copilot_internal/v2/token` 交换**（官方 CLI / SDK 内部就是这么做，所以它们能用同一个 token），直接当 bearer 不被接受。
- `gh api copilot_internal/v2/token`、以及用任一 `gho_` 裸 `curl` 打该端点，都返回 **403 Forbidden（ToS / scraping）**——GitHub 挡非官方客户端直接访问内部换取端点；gh 的 OAuth app token 也无权换。所以**没有干净的 gh / curl 一行命令能在官方客户端之外 mint 出那个短时 Copilot token**，别在这上面绕。
- 实用：`gh auth token` 给的是**相对长期有效**的会话 token（不像 `tid=…` 那种约 30 分钟过期），因此 "`gh auth login` 后取 `gh auth token` → 设 `COPILOT_GITHUB_TOKEN`" 是让 pi 用上 Copilot 的可持续姿势，无需在 pi 里跑 `/login`。它是广权限 GitHub token，当机密对待、别进世界可读文件。
- `model_not_supported` 有两种成因，别混：① token 类型不对（需交换 / 非直接可用，如上）；② 该模型账号没开（Claude / Grok 需 policy enable，pi 仅在 `/login` 路径做，env 路径不做）。

## <a id="matrix"></a>客户端 × 复用方式速查

| | env token（`COPILOT_GITHUB_TOKEN` 等） | 交互登录存哪 | 跨机搬运 |
|---|---|---|---|
| Copilot CLI | ✅ 读，优先级 `COPILOT_GITHUB_TOKEN > GH_TOKEN > GITHUB_TOKEN` | keychain 优先 / 明文 `config.json` 兜底 | env token；keychain 不可搬 |
| Copilot SDK | ✅ 透传给 spawn 的 runtime | 同 CLI（共享 `~/.copilot`，除非 `baseDirectory` + `mode:"empty"`） | env token / 隔离 `COPILOT_HOME` |
| pi（`github-copilot`） | ✅ 但**原样当 bearer**，须是 API 直接接受的 token（见 [token 类型](#token-type)） | `/login` 交换后落 `~/.pi/agent/auth.json` | 拷 `auth.json`，或用 env 给一个 API 直连可用的 token |
