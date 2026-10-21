# MiniMax Code CLI（mcode）

MiniMax 官方终端编码 agent（包名 `@minimax-ai/code`，内部代号 `mavis`）。采用预打包的 ESM JavaScript 分发，随附独立 Node.js 运行时与原生 addon。

> 以下源码定位锚定 `@minimax-ai/code@0.6.12` 安装目录下的 `chunks/*.js`；标 🔬 为本机同版本实测。

## <a id="cli-capabilities"></a>安装形态与 CLI 能力

独立安装器部署在 `~/.minimax-code/`，通过 `~/.local/bin/` 暴露三个命令入口：

| 入口 | 指向 | 作用 |
|---|---|---|
| `mcode` | `~/.minimax-code/bin/mcode` → `releases/<ver>/bin/mcode` | 主 TUI 与非交互 CLI（设置 `MINIMAX_STANDALONE_INSTALL=1` 并以自带 Node 启动 `cli.js`） |
| `mcode-tools` | `embedded/mcode-tools/cli.mjs` | 模型侧受管工具子进程（通过父进程注入的 Unix socket 租用 OAuth token） |
| `mavis-trash` | `embedded/trash/cli.mjs` | 内置安全删除工具 |

**常用子命令与旗标**：

| 命令 / 旗标 | 作用 |
|---|---|
| `mcode [prompt]` | 启动交互式 TUI |
| `-c, --continue` | 恢复当前工作区最近一次会话 |
| `--session [id]` / `--resume <id>` | 按会话 ID 恢复，省略 ID 时打开会话选择器 |
| `-m, --model <provider/model>` | 指定本次会话使用的模型（如 `minimax/MiniMax-M2.7`） |
| `--mode <standard\|lightweight>` | 选择上下文模式 |
| `mcode exec [prompt]` | 单次非交互执行（支持 `--effort`、`--permission <smart\|full\|off>`、`--output-format <text\|json\|stream-json>`） |
| `mcode exec review` | 对当前工作区变更执行非交互代码审查 |
| `mcode login [--region cn\|global]` | OAuth 登录（默认拉起浏览器，可配 `--no-browser`） |
| `mcode logout` | 登出当前账号并向服务端发起 `/oauth2/revoke` 吊销 |
| `mcode provider list / use / add` | 查看或切换模型鉴权源（`token-plan` 或 `api-key`）及自定义 provider |

**关键斜杠命令**：`/login` 登录、`/logout` 登出、`/status` 查看账号与套餐额度、`/provider` 切换模型源、`/session` 切换会话、`/compact` 压缩上下文、`/plan` 规划模式。

## <a id="auth-storage"></a>鉴权存储与多进程行为

`mcode` 支持两类模型鉴权源，由 `<dataDir>/config.yaml` 中的 `minimaxModelSource` 字段控制：

| `minimaxModelSource` 值 | 凭据位置 | 适用场景 |
|---|---|---|
| `token_plan`（默认） | `<dataDir>/auth/<env>/<region>/mcode-public/auth.json` | MiniMax Token Plan 订阅 OAuth 登录（生产环境 `<env>` 为 `prod`，`<region>` 为 `cn` 或 `en`） |
| `minimax_api_key` / `custom_provider` | `<dataDir>/config.yaml` | 静态 API Key 直连 Anthropic 兼容端点（CN：`https://api.minimaxi.com/anthropic`，Global：`https://api.minimax.io/anthropic`） |

### <a id="oauth-files"></a>OAuth 凭据文件结构

Token Plan 登录态保存在 `<dataDir>/auth/prod/<region>/mcode-public/` 目录下（权限强制要求目录 `0700`、文件 `0600`，`assertPrivatePermissions` 校验 `(mode & 0o077) === 0` 且拒绝符号链接）：

- `auth.json`：存储 `accessToken`（`mmoat_*`，有效期约 1 小时）、`refreshToken`（`mmort_*`）、`expiresAtMs`、`generation` 与 `loginEpoch`。
- `auth-state.json`：存储非敏感协调状态（`status`、`generation`、`expiresAtMs`、`region`）。
- `auth.lock`：跨进程刷新与登录的互斥锁文件。
- `<dataDir>/preferences/mcode-region.json`：记录当前账号所属区域（`cn` 或 `en`）。

> `chunk-QJ2FEPC2.js` 在读写 `auth.json` 的 `records` 字典时，键名由当前 `<dataDir>/auth` 的绝对路径实时计算：`"com.minimax.mcode.oauth.prod.<region>\0" + base64url(sha256(path.resolve(dataDir, "auth") + "\0mcode-public"))`。因此将 `auth.json` 直接复制到不同路径的数据目录后，必须同步按目标路径重算键名，否则 `getStatus()` 会因查不到匹配键而返回 `"error"`（未登录）🔬。

### <a id="oauth-rotation"></a>并发刷新、单次滚动轮换与登出吊销

- **同目录多进程协同**：同一 `MINIMAX_DATA_DIR` 下的多个 `mcode` 进程通过 `auth.lock` 文件锁与 `auth-state.json` 的 `generation` 计数协同。当 `accessToken` 过期时，首个拿到锁的进程调用 `/oauth2/token` 刷新并递增 `generation`，其余等待锁的进程重读磁盘即可直接使用新 token。
- **跨目录克隆凭据的刷新冲突（Refresh Token Rotation）**：MiniMax OAuth 每次使用 `refresh_token` 换取新 `access_token` 时，服务端都会签发新的 `refresh_token` 并使旧 `refresh_token` 作废。若两个不同数据目录各自持有一份相同的初始 `auth.json`，先触发刷新的目录会使另一目录的 `refresh_token` 在服务端失效（后续刷新报 HTTP 400 `invalid_grant`）。因此每个账号应固定归属单一数据目录。
- **`mcode logout` 的服务端吊销范围**：`chunk-QXUSWEWV.js` 中的 `logout()` 固定传入 `{ revoke: true }`，向 `https://account.minimax.cn/oauth2/revoke`（或 `.io`）发送 `POST token=<refreshToken>&token_type_hint=refresh_token`，并拉起浏览器打开 `/auth/logout`。**若已将默认目录 `~/.minimax` 的登录态迁移到隔离目录，清空原目录时严禁执行 `mcode logout`**（否则服务端会整条吊销该授权链，导致隔离目录内的凭据一并失效）；正确做法是直接将原目录 `auth/prod/<region>/mcode-public/` 下的 `auth.json` 与 `auth-state.json` 移入回收站，使原目录在本地无副作用地回到未登录态（`status: "anonymous"`）📖🔬。
- **工具子进程租约（OAuth Lease Broker）**：主进程在 `<dataDir>/run/mt-<hash>/` 下创建权限 `0700` 的 Unix domain socket（`mcode-auth-lease-v1.sock`）与一次性 capability 文件（`mcode-auth-lease-v1.cap`），通过 `MCODE_AUTH_BROKER_SOCKET` 等环境变量向 `mcode-tools` 子进程下发短期 `access_token`，子进程不直接接触 `refresh_token`。

## <a id="multi-account-isolation"></a>多账号并行隔离

### <a id="data-dir-env"></a>数据目录重定向机制

与 Codex 的 `CODEX_HOME` 类似、而不同于 Antigravity（`agy`）必须替换整个 `HOME`，`mcode` 在 `cli.js` 启动最早期通过 `chunks/chunk-IO46JRII.js` 的 `getTuiDataDirPath()` 读取环境变量 **`MINIMAX_DATA_DIR`**（兼容旧别名 `MAVIS_DATA_DIR`），只重定向 `mcode` 自身的数据目录，不影响 `$HOME`、Git、SSH 或外部工具配置 🔬。

| 机制 | 行为与适用性 |
|---|---|
| `MINIMAX_DATA_DIR=<path>` | 公开 CLI 全子命令（TUI、`exec`、`login`、`logout`、`provider`、`plugin`）及 `mcode-tools` 子进程一致生效；可将多账号目录统一收纳在 `~/.minimax-homes/<account>` 下 |
| `--profile <name>` | 仅 `chunk-X3PES5WL.js` 底层 daemon 代码保留了解析逻辑（会在 `$HOME` 顶层同时创建 `~/.minimax-<name>` 与 `~/.mavis-<name>` 两个隐藏项），但公开 CLI 入口 `main-JXKRTY5N.js` 的 `commander` 未注册该选项，直接传参会报 `error: unknown option '--profile'` 退出 🔬 |
| 默认回退 | `~/.minimax` |

### <a id="isolated-layout"></a>隔离目录结构与共享策略

在 `.bashrc` 中为每个额外账号定义包装函数：

```bash
mcode-<account>() {
    MINIMAX_DATA_DIR="$HOME/.minimax-homes/<account>" command mcode "$@"
}
```

隔离目录 `~/.minimax-homes/<account>/` 采用“凭据与运行时锁独立、历史会话与扩展配置软链回 `~/.minimax`”的布局：

| 路径 | 类型 | 说明 |
|---|---|---|
| `auth/` | 真实目录（`0700`） | 独立保存该账号的 `auth.json`、`auth-state.json`、`auth.lock` |
| `preferences/` | 真实目录（`0700`） | 独立保存 `mcode-region.json`（`0600`） |
| `run/` | 真实目录（`0700`） | 独立保存该进程的 OAuth Lease Broker socket |
| `config.yaml` | 独立文件（`0600`） | 独立保有配置文件（TUI 修改配置时通过 `.config-tmp-*` + `rename` 原子覆盖，软链会被替换成普通文件） |
| `v2/` 及 `v2/{migration,observability,plugin-hook-cache,runtime-owner-leases}` | 真实目录（`0700`） | 保持为真实目录以通过启动校验 |
| `v2/{sqlite,sessions,mcode,plugin-cache}` | 软链 → `~/.minimax/v2/*` | 共享全部 v2 会话历史、SQLite 状态库与工作区记录 |
| `skills` / `.builtin-skills` / `agents` / `plans` / `plugins` / `cache` / `sessions` 等 | 软链 → `~/.minimax/*` | 共享 Skills、计划、插件与旧版会话 |

> `chunk-5ADYFF2U.js` 在打开 v2 存储前会对 `<dataDir>`、`<dataDir>/v2` 和 `<dataDir>/v2/migration` 逐级调用 `fs.lstatSync(p).isSymbolicLink()`，若直接将 `v2/` 整目录软链到 `~/.minimax/v2`，启动即报 `Unsafe migration lock symlink path: <dataDir>/v2` 退出 🔬。将 `v2/` 及其锁目录建为真实目录、仅软链 `v2/{sqlite,sessions,mcode,plugin-cache}` 即可正常通过校验并共享会话。此外，数据库 schema 迁移备份逻辑同样检查 `v2/sqlite` 是否为软链；`mcode` 版本升级后，先运行一次默认 `mcode`（其 `~/.minimax/v2/sqlite` 为真实目录）完成迁移，再启动从属账号入口。

### <a id="isolated-init"></a>初始化新账号目录

前置状态：默认目录 `~/.minimax` 已初始化过一次。执行以下脚本创建 `~/.minimax-homes/<account>`，随后运行 `mcode-<account> login` 完成该账号登录：

```bash
acct="<account>"
base="$HOME/.minimax"
dest="$HOME/.minimax-homes/$acct"

mkdir -p -m 700 \
  "$dest/auth/prod/cn/mcode-public" \
  "$dest/preferences" \
  "$dest/run" \
  "$dest/v2/migration" \
  "$dest/v2/observability" \
  "$dest/v2/plugin-hook-cache" \
  "$dest/v2/runtime-owner-leases"

cp -p "$base/config.yaml" "$dest/config.yaml" && chmod 600 "$dest/config.yaml"
cp -p "$base/preferences/mcode-region.json" "$dest/preferences/mcode-region.json" && chmod 600 "$dest/preferences/mcode-region.json"

for item in .builtin-skills agents background-tasks bin business-telemetry.identity.json cache integrations plans plugins sessions shims skills; do
  [ -e "$base/$item" ] && ln -sfn "$base/$item" "$dest/$item"
done

for v2item in mcode plugin-cache sessions sqlite; do
  [ -e "$base/v2/$v2item" ] && ln -sfn "$base/v2/$v2item" "$dest/v2/$v2item"
done
```

> 若需要将 `~/.minimax` 当前已登录的账号无缝迁入 `$dest` 而不重新扫码：复制 `auth-state.json` 后，读取原 `auth.json` 中的记录对象，以 `node -e 'console.log("com.minimax.mcode.oauth.prod.cn\0" + require("crypto").createHash("sha256").update(require("path").resolve(process.argv[1], "auth") + "\0mcode-public").digest("base64url"))' "$dest"` 算出新键名写入 `$dest/auth/prod/cn/mcode-public/auth.json`（权限 `0600`），最后将原 `~/.minimax/auth/prod/cn/mcode-public/{auth.json,auth-state.json}` 移入回收站即可 🔬。

## <a id="account-and-quota-api"></a>账号身份与套餐额度接口

TUI 的 `/status` 与状态栏展示的用户名、套餐等级及 5 小时 / 周额度窗口，由 `chunk-47KWM23C.js` 请求以下接口获取（均携带 `Authorization: Bearer <accessToken>`）：

| 接口路径 | 主机（CN / Global） | 方法 | 返回内容 |
|---|---|---|---|
| `/v1/api/user/info` | `agent.minimaxi.com` / `agent.minimax.io` | `GET` | `data.userInfo`（含主账号名 `name`、子账号/显示昵称 `subUserName`、`realUserID`、`phone`） |
| `/matrix/api/v1/user/get_user_extra_info` | 同上 | `POST` `{}` | `workspaces` 数组（含 `workspace_id`、`op_group_id`、`token_plan_tier`、`token_plan_expires_at`、`opcredit_balance`） |
| `/matrix/api/v1/commerce/get_membership_info` | 同上 | `POST` | 订阅套餐详情与到期时间 |
| `/v1/api/openplatform/coding_plan/remains` | `www.minimaxi.com` / `platform.minimax.io` | `GET` | `model_remains` 数组：5 小时窗口（`current_interval_total_count` / `current_interval_usage_count`、`end_time`）与周窗口（`current_weekly_total_count` / `current_weekly_usage_count`、`weekly_end_time`） |

> `coding_plan/remains` 返回的 `current_interval_usage_count` 与 `current_weekly_usage_count` 虽然字段名为 `usage_count`，实际含义是**当前窗口剩余可用次数（remaining）**（见 `chunk-47KWM23C.js` 的 `h0e()`：`remainingPercent = usage_count / total_count * 100`）。前三个接口需附带 `buildUrl()` 生成的查询参数（含 `unix=<nowMs>`）及签名头：`yy = md5(encodeURIComponent(pathAndQuery) + "_" + body + md5(String(nowMs)) + "ooui")`、`x-timestamp = String(Math.floor(nowMs / 1000))`、`x-signature = md5(xTimestamp + "I*7Cf%WZ#S&%1RlZJ&C2" + body)` 📖🔬。

## <a id="session-and-skills"></a>会话数据与 Skills 发现

### <a id="session-storage"></a>会话数据位置

| 路径 | 内容 |
|---|---|
| `<dataDir>/v2/sqlite/runtime-state.sqlite` | 会话元数据索引、工作区归属与 schema 迁移记录（SQLite WAL 模式） |
| `<dataDir>/v2/sessions/YYYY/MM/DD/<HHMMSS>-session_<id>/` | 单条会话目录，含 `session.json`、`messages.jsonl`、`events.jsonl`、`wire.jsonl`、`artifacts/` |
| `<dataDir>/v2/mcode/recent-workspaces.json` | 最近打开的工作区列表 |

### <a id="skills-discovery"></a>Skills 自动发现路径

`mcode` 启动时合并两类 Skills 目录（见 `chunk-X3PES5WL.js`）：

1. **数据目录内**：`<dataDir>/skills` 与 `<dataDir>/.builtin-skills`。
2. **真实主目录与工作区向上查找（不受 `MINIMAX_DATA_DIR` 影响）**：按优先级扫描工作区 `.minimax/skills`、`.claude/skills`、`.agents/skills` 以及个人级 `~/.claude/skills`、`~/.codex/skills`、`~/.agents/skills`。
