# Herdr 与 Ovis

官方文档与仓库：

- Herdr 官网与插件文档：<https://herdr.dev/docs/plugins/>
- Ovis 仓库（Web / 手机端客户端）：[devswha/ovis](https://github.com/devswha/ovis/tree/6c78047f40a84759748b7a8f5750a3a592b8123e)

## <a id="product-generations"></a>产品形态与代际划分

Herdr 生态包含两代核心运行时与两类图形界面，安装和排障前先区分目标组件：

| 组件 | 常见命令 / 包名 | 界面与能力边界 |
|---|---|---|
| **Herdr 0.9.x（TUI + 守护进程）** | `herdr`（如 `0.9.5`） | 终端内多窗格 TUI 与后台 `herdr server`；支持 `herdr plugin` 插件生命周期，是 Ovis 服务端接入的宿主运行时 |
| **Herdr Desktop 0.1.x（新一代桌面端）** | `herdr-app` + `hc`（`herdr-core`） | 官方原生桌面端与新一代 CLI；内置 `mods/files`（文件树）、`mods/changes`（Git diff）等模块，窗格内直接运行终端进程，无独立 Web 聊天视图 |
| **Ovis（Web / 手机客户端）** | 插件 `devswha.ovis`、移动端 `sh.ovis.app` | 面向 `herdr 0.9.x` 的浏览器与移动端界面；同时提供结构化 **Chat 视图**（解析 Claude Code、Codex、Antigravity、OpenCode 等会话记录与审批卡片）和实时 **Terminal 视图**，支持 SSH 多机桥接与 Web Push 提醒 |

> Ovis 对 `min_herdr_version = "0.9.0"` 的版本要求与插件声明见 [herdr-plugin.toml](https://github.com/devswha/ovis/blob/6c78047f40a84759748b7a8f5750a3a592b8123e/herdr-plugin.toml#L1-L6)。

Herdr Desktop 中的 `herdr integration`（或 `hc integration`）用于向 Claude Code、Codex、OpenCode、Gemini CLI 等 agent 的配置文件写入 hooks，使宿主侧栏实时显示窗格内 agent 的状态（思考中、等待审批、已完成），不提供额外的聊天 UI 视图。需要结构化聊天视图或手机端远程控制时，使用 `herdr 0.9.x` 配合 Ovis。

## <a id="install-and-paths"></a>安装与目录结构

Linux / macOS 作为无头服务端运行时，先安装 `herdr` 0.9.x，再通过一键脚本或插件命令安装 Ovis：

```bash
curl -fsSL https://ovis.sh/install.sh | sh
# 或通过 herdr 插件管理器安装：
herdr plugin install devswha/ovis
```

Windows 侧两套安装脚本分别对应不同产物：

- `powershell -c "irm https://releases.herdr.dev/app/install.ps1 | iex"`：安装 Herdr Desktop（`herdr-app`）与 `hc` CLI 到 `%LOCALAPPDATA%\Programs\herdr-core`。
- `powershell -c "irm https://ovis.sh/install.ps1 | iex"`：安装 `herdr` 0.9.x 与 Ovis Web 客户端。

### <a id="key-paths"></a>关键路径速查

以下路径以 Linux 默认家目录为例；Ovis 启动脚本先读取插件配置目录中的 `env`，再读取 `.env`（同名变量以 `.env` 为准）：

| 类别 | 路径 | 作用 |
|---|---|---|
| **Herdr 主配置与套接字** | `~/.config/herdr/config.toml`、`~/.config/herdr/herdr.sock` | `herdr server` 的配置与 RPC 套接字 |
| **Ovis 插件源码检出** | `~/.config/herdr/plugins/github-installations/devswha.ovis-<hash>/<rev>/checkout/` | `herdr plugin` 管理的 Ovis 前后端与构建产物 |
| **Ovis 插件环境变量** | `~/.config/herdr/plugins/config/devswha.ovis/env`（或 `.env`） | 存放 `PORT`、`OVIS_TOKEN` 等实例级配置 |
| **Ovis 状态与设备注册表** | `~/.local/state/ovis/` 或 `~/.local/state/herdr/plugins/devswha.ovis/` | 存放 `devices.json`（已配对设备哈希，权限 `0600`）、`server.pid`、`server.log` |

> 插件配置目录与 `env` / `.env` 的加载顺序见 [scripts/plugin.ts](https://github.com/devswha/ovis/blob/6c78047f40a84759748b7a8f5750a3a592b8123e/scripts/plugin.ts#L42-L73)。

## <a id="systemd-service"></a>常驻服务与插件配置

Ovis 注册了 Herdr 的 `[[startup]]` 钩子：`herdr server` 启动时会自动调起 `scripts/plugin.ts start`，拉起 Ovis 的 `managed.ts` / `supervisor.ts` 守护进程；若目标端口已有该实例监听则保持幂等退出。因此 systemd 只需托管 `herdr server`，无需单独为 Ovis 编写第二个 service。

> 启动钩子定义见 [herdr-plugin.toml](https://github.com/devswha/ovis/blob/6c78047f40a84759748b7a8f5750a3a592b8123e/herdr-plugin.toml#L38-L45)，进程托管与热更新切换见 [server/managed.ts](https://github.com/devswha/ovis/blob/6c78047f40a84759748b7a8f5750a3a592b8123e/server/managed.ts#L28-L61)。

多用户共用一台主机时，可使用系统级模板 `/etc/systemd/system/herdr@.service`（或单用户 `~/.config/systemd/user/herdr.service` 配合 `loginctl enable-linger`），在 `PATH` 中包含 `herdr` 与 `bun` 所在目录：

```ini
[Unit]
Description=herdr headless server for %i (agent runtime, Ovis backend)
After=network-online.target

[Service]
Type=simple
User=%i
ExecStart=/home/%i/.local/bin/herdr server
Environment=PATH=/home/%i/.local/bin:/home/%i/.bun/bin:/usr/local/bin:/usr/local/sbin:/usr/bin:/usr/sbin:/bin:/sbin
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

每个用户在各自的 `~/.config/herdr/plugins/config/devswha.ovis/env` 中指定独立端口与访问令牌（默认端口为 `7317`，多用户环境按约定递增或按 [按 UID 分配端口](service.md#uid-ports) 规划）：

```dotenv
OVIS_TOKEN=<64位随机hex令牌>
PORT=<port>
```

修改 `env` 后，可通过 `herdr plugin action run --plugin devswha.ovis --action stop` 与 `--action start`（或重启该用户的 `herdr` 服务）使新端口或令牌生效。

## <a id="auth-and-devices"></a>认证机制与手机 / 设备设置页分工

Ovis 后端在配置了 `OVIS_TOKEN` 时同时支持两套独立的访问凭证，由 `decideAccess` 按固定优先级判定：

1. **访问令牌（`via: "token"`）**：请求携带匹配的 `Authorization: Bearer <OVIS_TOKEN>` 请求头，或携带通过登录框兑换的 `ovis_token` Cookie。
2. **已配对设备凭证（`via: "device"`）**：设备通过一次性 6 位配对码调用 `POST /api/devices/pair` 后，服务端签发长期有效的 `ovis_device` HttpOnly Cookie，并在状态目录的 `devices.json` 中只保存该 token 的 SHA-256 哈希。

> 凭证比对与公开路径豁免见 [server/auth.ts](https://github.com/devswha/ovis/blob/6c78047f40a84759748b7a8f5750a3a592b8123e/server/auth.ts#L94-L117)，访问决策优先级见 [server/access.ts](https://github.com/devswha/ovis/blob/6c78047f40a84759748b7a8f5750a3a592b8123e/server/access.ts#L205-L210)，配对码签发、首次返回确认与设备撤销见 [server/devices.ts](https://github.com/devswha/ovis/blob/6c78047f40a84759748b7a8f5750a3a592b8123e/server/devices.ts#L215-L340)。

### <a id="settings-phone-vs-devices"></a>“手机与设备”设置页的模块分工

打开 Ovis 的 **设置 → 手机与设备（Settings → Phone & devices）** 时，页面上下分为 **手机（Phone）** 和 **设备（Devices）** 两个区域，分别解决“客户端入口形态”和“设备身份授权”两个不同问题：

| 区域 | 二维码 / 按钮内容 | 用途与适用场景 |
|---|---|---|
| **手机（Phone）**（含“安装应用”） | 纯站点地址 `https://<domain>`（**不带** `?pair=` 参数）及“安装应用”按钮 | **入口导航与浏览器 PWA 安装**：供已具备网络直通身份（如本机 Tailscale 账号或外层浏览器 OAuth）的手机用系统相机打开网址，或触发浏览器 `beforeinstallprompt` 将网页添加为桌面 PWA 图标并开启网页通知 |
| **设备（Devices）**（含“配对设备”） | 点“配对设备”后生成 `https://<domain>/?pair=<6位配对码>`（10 分钟有效、单次消费） | **设备级授权与管理**：供原生 **Ovis App（`sh.ovis.app`）** 或未持有 Token 的新浏览器扫码/输入 6 位码，向服务端注册设备并获取专属 `ovis_device` Cookie；支持在列表中查看各设备最后在线时间、单独移除或“撤销所有设备” |

> 两个设置分组的组件实现见 [SettingsDialog.tsx 中的 `DevicesPage`](https://github.com/devswha/ovis/blob/6c78047f40a84759748b7a8f5750a3a592b8123e/src/components/SettingsDialog.tsx#L851-L905) 与 [PhonePanel.tsx](https://github.com/devswha/ovis/blob/6c78047f40a84759748b7a8f5750a3a592b8123e/src/components/PhonePanel.tsx#L22-L49)。

当电脑浏览器通过反向代理代持的 `Authorization: Bearer` 访问时，**设备**区域顶部会提示“你已通过访问 Token 访问”；而在通过扫码配对接入的手机 Ovis App 上打开同一页面时，会提示“这是已配对的设备”，并在对应设备行标注当前设备。

## <a id="proxy-access"></a>反向代理接入约束（OAuth 注入与 App 扫码配对共存）

公网统一认证、Caddy 环境变量文件权限与服务重载流程由 `network` skill 的上游会话代持主题覆盖。将 Ovis 放在 Caddy + `caddy-security`（OAuth）后面，并希望**电脑浏览器走 OAuth 免输 Token 直连、手机原生 Ovis App（`sh.ovis.app`）走扫码配对直连**时，需同时满足以下三项应用侧约束：

1. **保留原始 `Host` 与 `X-Forwarded-Proto: https`**：Ovis 的 `sameOrigin()` 根据请求到达时的 `Host` 和 `X-Forwarded-Proto` 构造预期 Origin，并与浏览器发送的 `Origin` 头比对；缺失任一头会导致 `/ws` WebSocket 升级和所有修改类 `POST`/`PATCH`/`DELETE` 请求返回 `403`。
2. **Ovis 原生 App 首屏与配对请求不跳跨站 OAuth 302**：原生 App（Android `MainActivity.java` / iOS `HerdrBridgeViewController.swift`）在 WebView 首次加载时拦截跨 Origin 的 302 重定向（`followRedirect`），并主动探测重定向目标是否为 Ovis 实例；若被重定向到外部 OAuth 登录页（如 `auth.<example.com>`），App 会直接判定目标不是 Ovis 并报错中止。此外，扫码打开 `/?pair=<code>` 后，前端脚本需先加载静态资源（`/assets/*`）、请求 `/api/health?scope=bridge`，再由 `AccessGate` 自动向 `POST /api/devices/pair` 提交配对码以换取 `ovis_device` Cookie；在 `ovis_device` 落盘前，这些前置请求同样不能被 OAuth 302 拦截。
3. **对携带 `ovis_device` 的配对设备请求不注入 `Authorization: Bearer`**：Ovis 的 `decideAccess()` 先判断 `tokenMatched`（第 1 优先级），再判断 `device !== null`（第 2 优先级）。若反向代理对所有请求无条件注入 `Authorization: Bearer`，已配对手机也会被识别为 `via: "token"` 而非 `via: "device"`，导致当前设备高亮、按设备绑定 Web Push 订阅以及在 PC 端撤销该设备后立即切断连接的能力全部失效；更关键的是，若对绕过 OAuth 的请求仍注入 `Bearer`，任何伪造 `Cookie: ovis_device=fake` 的请求都会被代理直接提权放行。

> Origin 校验见 [server/machine-security.ts](https://github.com/devswha/ovis/blob/6c78047f40a84759748b7a8f5750a3a592b8123e/server/machine-security.ts#L18-L50)，原生 App 跨源重定向探测见 [MainActivity.java](https://github.com/devswha/ovis/blob/6c78047f40a84759748b7a8f5750a3a592b8123e/app/android/app/src/main/java/sh/ovis/app/MainActivity.java#L151-L160) 与 [`followRedirect`](https://github.com/devswha/ovis/blob/6c78047f40a84759748b7a8f5750a3a592b8123e/app/android/app/src/main/java/sh/ovis/app/MainActivity.java#L311-L344)，扫码参数自动提交见 [AccessGate.tsx](https://github.com/devswha/ovis/blob/6c78047f40a84759748b7a8f5750a3a592b8123e/src/components/AccessGate.tsx#L61-L69)，`tokenMatched` 与 `device` 的判定顺序见 [server/access.ts](https://github.com/devswha/ovis/blob/6c78047f40a84759748b7a8f5750a3a592b8123e/server/access.ts#L205-L210)。

### <a id="caddy-config"></a>环境变量注入与 Caddy 路由配置

与 Zellij 将 `session_token` 放在 Caddy 的 `EnvironmentFile` 中通过 `{env.*}` 注入的做法一致，先将目标用户的 `OVIS_TOKEN` 写入 Caddy 服务加载的环境文件（如 `/etc/caddy/<env_file>`），不在 Caddyfile 中硬编码明文令牌：

```dotenv
OVIS_<USER>_TOKEN=<与插件 env 中一致的 OVIS_TOKEN>
```

在 `/etc/caddy/routes.d/` 下的站点路由中，用单条 CEL 表达式分流“Ovis 设备凭证 / 配对引导流”与“浏览器 OAuth 代持流”：

```caddyfile
@herdr_<user> host <herdr.user.example.com>
handle @herdr_<user> {
	@ovis_app `header({'Cookie': '*ovis_device=*'}) || header({'Cookie': '*herdr_web_device=*'}) || (!header({'Cookie': '*<OAUTH_COOKIE>=*'}) && (query({'pair': '*'}) || header({'X-Requested-With': 'sh.ovis.app'}) || !path('/')))`
	handle @ovis_app {
		request_header -Authorization
	}
	handle {
		authorize with <user_access_policy>
		request_header Authorization "Bearer {env.OVIS_<USER>_TOKEN}"
	}
	reverse_proxy 127.0.0.1:<port> {
		header_up Host {host}
		header_up X-Forwarded-Proto https
		stream_timeout 24h
	}
}
```

将 `<herdr.user.example.com>`、`<OAUTH_COOKIE>`（如 `caddy-security` 签发的访问令牌 Cookie 名）、`<user_access_policy>`、`OVIS_<USER>_TOKEN` 和 `<port>` 替换为实际部署值。

> 在 Caddy 的 CEL `expression` 匹配器中，需使用内置匹配函数 `header({'Cookie': '...'})`、`query({'pair': '*'})`、`path('/')`；Caddy 不存在 `{http.request.cookie.<name>}` 这一占位符，误写时未展开的字面量字符串非空，会导致 `!= ""` 恒为真。

两条分支的协作关系如下：

- **普通浏览器访问 `/`**：未携带 `ovis_device` 且无 `?pair=`，落入默认 `handle` 分支，触发 `authorize with <user_access_policy>` 跳转 OAuth 登录；登录成功后浏览器持有 `<OAUTH_COOKIE>`，此后该浏览器的所有请求（`/`、`/assets/*`、`/api/*`、`/ws`）均不命中 `@ovis_app`，全部经 OAuth 校验后由 Caddy 注入 `Authorization: Bearer {env.OVIS_<USER>_TOKEN}` 免密进入。
- **Ovis App 扫码或已配对访问**：首次扫码 `/?pair=<code>`（或在 Android App 内手动输入域名，携带 `X-Requested-With: sh.ovis.app`）及配对完成前的静态资源、`/api/health`、`POST /api/devices/pair` 请求均命中 `@ovis_app`，由 `request_header -Authorization` 剥离外部伪造头后直通 Ovis；配对成功后客户端持有 `ovis_device` Cookie，后续所有请求继续命中 `@ovis_app`，完全由 Ovis 自身的 `devices.json` 校验与管理生命周期。
- **未授权请求防护**：未持有 `<OAUTH_COOKIE>` 的外部请求若直接访问 `/api/session` 或携带伪造的 `Cookie: ovis_device=forged`，虽然命中 `@ovis_app` 绕过 OAuth 302，但因该分支不注入 `Bearer` Token 且剥离了 `Authorization` 头，Ovis 后端会直接返回 `401 Unauthorized`。

### <a id="proxy-verification"></a>配置生效与分流验证

新增环境变量后需重启 `caddy.service`（仅改路由文件则 `systemctl reload caddy`），再用 `curl` 验证四类请求的响应码：

```bash
HOST="<herdr.user.example.com>"
ENTRY="http://127.0.0.1:18080"   # 替换为 Caddy 实际监听地址

# 1. 普通浏览器无 Cookie 访问首页 -> 应返回 302 跳转 OAuth 登录页
curl -s -o /dev/null -w "browser_root=%{http_code}\n" -H "Host: $HOST" -H "Accept: text/html" "$ENTRY/"

# 2. Ovis App 扫码访问 /?pair=123456 -> 应返回 200 直接加载前端页面
curl -s -o /dev/null -w "qr_pair=%{http_code}\n" -H "Host: $HOST" -H "Accept: text/html" "$ENTRY/?pair=123456"

# 3. 未授权访问受保护 API -> 应返回 401（未被错误注入 Bearer）
curl -s -o /dev/null -w "unauth_api=%{http_code}\n" -H "Host: $HOST" "$ENTRY/api/session"

# 4. 伪造 ovis_device Cookie 访问受保护 API -> 应返回 401
curl -s -o /dev/null -w "forged_device=%{http_code}\n" -H "Host: $HOST" -H "Cookie: ovis_device=forged" "$ENTRY/api/session"
```

## <a id="agent-session-binding"></a>终端窗格与 Agent 会话绑定

Herdr `0.9.x` 为每个受管终端窗格注入 `HERDR_ENV=1`、`HERDR_PANE_ID` 与 `HERDR_SOCKET_PATH`（默认 `~/.config/herdr/herdr.sock`）。Ovis 要把窗格终端与结构化 **Chat 视图**关联起来，按目标 coding agent 采用两类发现机制：

| 机制 | 代表工具 | 绑定条件与多账号要点 |
|---|---|---|
| **Hook 上报（`pane.report_agent_session`）** | Codex、Claude Code 等 | 通过 `herdr integration install <target>` 写入启动 hook，在会话创建或恢复时经 `HERDR_SOCKET_PATH` 上报当前 `HERDR_PANE_ID` 与 `agent_session_id`；执行 hook 的进程需保留窗格的 `HERDR_*` 环境，且 Ovis 需能在该工具默认会话目录下读到对应会话文件 |
| **进程存活锁（presence lock）** | Antigravity CLI（`agy`） | 客户端运行期间持有会话目录 `presence/*.lock`，Ovis 直接按锁与会话库关联，不依赖 `herdr integration` hook；多账号隔离时将会话与 `presence` 目录软链接回默认位置即可共享视图 |

使用 `herdr integration status` 可核对当前配置根目录下的集成脚本版本与状态。对支持后台守护进程或多账号独立配置目录的 agent（如 Codex 默认共享 app-server daemon 丢失当前窗格 `HERDR_PANE_ID`、多 `CODEX_HOME` 需分别安装 hook 并预填 `trusted_hash`、以及通过 `sessions` 软链接对齐 Ovis 会话查找路径），具体包装器与运行时配置由 `harness` skill 维护。

