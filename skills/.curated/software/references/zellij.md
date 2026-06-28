# Zellij

官方文档：

- Web client: <https://zellij.dev/documentation/web-client.html>
- Options: <https://zellij.dev/documentation/options.html>

## Web client

Zellij 内置 Web server，默认关闭。手动启动：

```bash
zellij web
```

默认监听 `http://127.0.0.1:8082`。如果改为绑定非 localhost 地址，则必须同时配置 `web_server_cert` 和 `web_server_key`，由 Zellij 自己提供 HTTPS。对公网或不可信网络暴露时，外层仍应使用 Caddy/nginx 等反向代理并增加独立认证；获得 Zellij Web 访问权，基本等同于获得该系统用户的 shell 访问能力。

常用配置：

```kdl
web_server true
web_server_ip "0.0.0.0"
web_server_port <PORT>
web_server_cert "/home/<USER>/.config/zellij/certs/cert.pem"
web_server_key "/home/<USER>/.config/zellij/certs/key.pem"
web_sharing "on"
show_startup_tips false
default_shell "/bin/bash"
```

`default_shell` 控制新 pane 使用的 shell，默认取 `$SHELL`。在 systemd、sudo、service 等环境下，`$SHELL` 往往不可靠，服务化时建议显式写成 `/bin/bash`、`/usr/bin/fish`、`/usr/bin/zsh` 这类绝对路径。

`web_sharing "on"` 表示新建 session 默认通过 Web server 共享；只想在需要时显式共享可用 `"off"`，完全禁用共享可用 `"disabled"`。

## 普通启动与 Web 共享前提

输入 `zellij` 会启动普通 Zellij session；session 会持续存在，后续可用 `zellij attach` 恢复。这个命令本身不等同于打开 Web client。

如果希望普通 `zellij` 启动的新 session 可被 Web client 看到，前提是默认配置文件中启用了 Web 相关开关，至少包括：

```kdl
web_server true
web_sharing "on"
```

如果 Web server 使用独立配置（例如 systemd service 通过 `zellij -c ~/.config/zellij/web.kdl web` 启动），而普通交互式 `zellij` 读取的是默认配置，则要分别确认两份配置。否则可能出现 Web server 已运行，但普通 `zellij` 新建的 session 没有自动共享、Web 页面看不到的情况。

## 配置选项的几个反直觉点

审查 zellij 配置时几个名字和行为不一致的点（均基于 `0.44.x` 源码）：

- **`keybinds clear-defaults=true { ... }` 会把键位冻结在生成时的版本**。`clear-defaults=true` 表示丢弃全部内置默认键位、只用列出的；而 `zellij setup --dump-config` 导出的配置正是当时版本默认键位的全量快照。升级 zellij 后，上游新增/改动的默认键位不会自动出现，需要重新 dump 或手动合并。表现是静默的——不报错，只是用不到新键位。

- **`default_cwd` 只有在同时设了 `default_shell` 时才改变新 pane 的工作目录**。新 pane 默认继承当前 pane 的 cwd；`default_cwd` 只作为“无法确定 cwd 时”的兜底，唯一强制生效的路径是经过 `default_shell`（`pty.rs` 的 `fill_cwd` 仅在 cwd 为 None 时回填）。所以 `default_shell` 注释掉时，`default_cwd` 对交互式新 pane 基本不起作用，只影响 Web 新建 session 的首个 pane。反过来：一旦取消注释 `default_shell`（例如启用某个 shell wrapper），`default_cwd` 会随之激活，把“继承父 pane 目录”的行为改成固定打开 `default_cwd`。

- **`web_client { ... }` 只被 Web server 读**。普通交互式 `zellij`（读 `config.kdl`）不使用这一段，只有 `zellij web`（读 web.kdl）才生效。写在交互 `config.kdl` 里的 `web_client` 块不起作用，调浏览器端外观应改 web.kdl。

## login token 与 session token

zellij web 的认证是**两层 token**：

| 层 | 怎么拿到 | 存储 | 有效期 |
|---|---|---|---|
| **login token**（管理员侧） | `zellij web --create-token`，输出 `token_<N>: <uuid>` | sqlite `tokens` 表，**只存 sha256 hash**；明文只返回一次，事后**无法找回** | **永久**（`tokens` 表没有 `expires_at` 列，`validate_token` 也不查时间） |
| **session_token**（反代/浏览器侧） | `POST /command/login` 后 `Set-Cookie` 返回的 `session_token=<uuid>` | sqlite `session_tokens` 表，与 login token 多对一关联 | **硬编码**：`remember_me=true` 4 周 / `remember_me=false` 5 分钟（源码 `zellij-utils/src/web_authentication_tokens.rs::create_session_token`） |

login token 丢了**只能 revoke 后重建**——管理工具只剩 `--list-tokens`（看名字 + 创建时间，没值）、`--revoke-token <name>` / `--revoke-all-tokens`。反代注入 Cookie 时要**针对目标端口重新登录并提取对应的 `session_token`**，不要复用其它端口或其它实例的 token。

以下示例使用本机 HTTP 端口；目标端口走 HTTPS 时把 URL 改为 `https://127.0.0.1:<PORT>`：

```bash
PORT=<PORT>
ZELLIJ_WEB_BASE_URL="http://127.0.0.1:${PORT}"

TOKEN_OUTPUT=$(zellij web --create-token)
AUTH_TOKEN=$(echo "$TOKEN_OUTPUT" | tail -1 | awk -F': ' '{print $2}')
echo "登录令牌: $AUTH_TOKEN"

RESPONSE=$(curl -sk "${ZELLIJ_WEB_BASE_URL}/command/login" \
  -H "Content-Type: application/json" \
  -d "{\"auth_token\":\"$AUTH_TOKEN\",\"remember_me\":true}" \
  -i)

SESSION_TOKEN=$(echo "$RESPONSE" | grep -oP 'session_token=\K[^;]+')
echo "会话令牌: $SESSION_TOKEN"
```

### session_token 为什么会过期、谁说了算

- **真理由是 server 端 sqlite 那一行 `expires_at`**：`validate_session_token` 的 SQL 就是 `SELECT COUNT(*) FROM session_tokens WHERE session_token_hash='<hash>' AND expires_at > datetime('now')`，过期立刻 401。
- **cookie 的 `Max-Age=2419200`（28 天）只是同一个数往浏览器抄了一份**：Caddy 注入固定 Cookie 跳过浏览器的反代场景里它**完全不起作用**，过期完全由 DB 决定。
- `create_session_token` 每次进入还会顺手调 `cleanup_expired_sessions()` 把所有 `expires_at <= now` 的行**物理 DELETE**。所以过期的 session_token 在 DB 里**会消失**，不是只是被打无效标记。
- CLI 和配置文件**都没暴露这个 TTL**——不重编译 / 不改 DB 没法改有效期。

### 判断是不是 session_token 过期

直接打 zellij 自己的 `/ws/control`（WebSocket 升级端点），对照伪造 token：

```bash
ZELLIJ=http://127.0.0.1:8082   # 或 https://...
TOKEN=<可疑的 session_token>

curl --noproxy '*' -sk -o /dev/null -m 4 -w "real=%{http_code}\n" \
  -H "Connection: Upgrade" -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Version: 13" -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
  -H "Cookie: session_token=$TOKEN" "$ZELLIJ/ws/control"
curl --noproxy '*' -sk -o /dev/null -m 4 -w "fake=%{http_code}\n" \
  -H "Connection: Upgrade" -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Version: 13" -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
  -H "Cookie: session_token=00000000-0000-0000-0000-000000000000" "$ZELLIJ/ws/control"
```

读法：

- `real=401` 且 `fake=401` → 你这个 token 已无效（过期 / 已 revoke / 拼错）。
- `real=101`（WebSocket 升级成功）或 `real=405`（method/upgrade 后续校验挑剔，但**认证已过**），而 `fake=401` → token 有效。

`--noproxy '*'` 不可省：很多 dev 机 shell 环境里有 `http_proxy=http://127.0.0.1:7890`，curl 默认会把 `localhost` 也送进 proxy 导致请求被吃掉，必须强制绕开。`curl < 7.86` 还会把 zellij WebSocket 后续帧当 “HTTP/0.9” 报错，把测试机 curl 升一下（或换 Python `socket` 直连）就稳。

### 让 session_token 永不过期：直接改 DB

CLI 没暴露 TTL，要彻底免维护就改 DB 里那行 `expires_at`。**保留 hash 即可，session_token 明文继续用**，不需要重新生成：

```bash
DB=~/.local/share/zellij/tokens.db                                                # Linux
# DB="$HOME/Library/Application Support/org.Zellij Contributors.Zellij/tokens.db" # macOS
# Windows: %APPDATA%\Zellij\data\tokens.db （从 WSL 走 /mnt/c/Users/<USER>/AppData/Roaming/Zellij/data/tokens.db）
cp -a "$DB" "$DB.bak-$(date +%Y%m%d-%H%M%S)"     # 必做：先备份

TOKEN=<session_token 明文>
HASH=$(printf '%s' "$TOKEN" | sha256sum | awk '{print $1}')

sqlite3 "$DB" "UPDATE session_tokens SET expires_at='2099-12-31 00:00:00' WHERE session_token_hash='$HASH'"
sqlite3 -header -column "$DB" "SELECT id, remember_me, created_at, expires_at FROM session_tokens WHERE session_token_hash='$HASH'"
```

要点：

- **不用重启 zellij**：`validate_session_token` 每个请求都现查 DB，UPDATE 立即生效。
- `cleanup_expired_sessions()` 的 WHERE 是 `expires_at <= datetime('now')`，**未来时间的行不会被清**，所以 2099 这条永远活着。
- **zellij schema 升级的话这个 hack 就废**——`session_tokens` 表结构改了或加严格迁移可能直接清表。语义上 zellij 设计 session_token 就该轮换，改 DB 是绕设计意图，**不要批量用、也不要对生产无人值守服务依赖**；本工作区把它用在自用 zellij web 反代 Cookie 这种“我自己一个人用 + Caddy 还有外层 OAuth 兜底”的场景。
- 没装 `sqlite3` 的环境（干净 WSL / Windows pwsh）用 Python stdlib 等价做：

```python
import sqlite3, hashlib
db = '<path/to/tokens.db>'
tok = '<session_token>'
h = hashlib.sha256(tok.encode()).hexdigest()
c = sqlite3.connect(db); c.execute(
  "UPDATE session_tokens SET expires_at=? WHERE session_token_hash=?",
  ('2099-12-31 00:00:00', h)); c.commit(); c.close()
```

### 长期替代方案：systemd timer 自动续期

如果不想动 DB schema 直接挂死，正路是定期用还活着的 login token 重新跑 `/command/login` 拿新 `session_token` → 写回 Caddy（或其它反代）→ reload。login token 永久有效是这套方案的前提。坑：reload Caddy 通常要 sudo / root 写 Caddyfile，得给 timer 一条窄 sudoers 口子（`NOPASSWD: /bin/systemctl reload caddy, /usr/bin/sed …`），或把这条 Cookie 拆到非 root 的 include 文件里再让 timer 自己改。

## Caddyfile 示例
Caddy 反代 Zellij Web 时，常见场景分为两类：本机部署和远程部署。`header_up Cookie "session_token=..."` 仅用于把登录后得到的 `session_token` 透传给 Zellij，本身不决定反代拓扑。

本机部署：Caddy 与 Zellij 在同一台机器上。此时通常保持 `zellij web` 的默认本地监听方式，即仅监听 `127.0.0.1:8082`，由本机 Caddy 负责外层 HTTPS 与访问控制。`LisaHost`、`RackNerd` 这类部署适合使用以下配置：

```caddyfile
zellij.<HOST> {
	authorize with admin

	reverse_proxy localhost:8082 {
		header_up Cookie "session_token=<SESSION_TOKEN>"
	}

	import error_pages
}
```

远程部署：Zellij 在另一台机器上，当前这台 Caddy 仅作为对外入口。此时 upstream 指向远程主机；如果远程 Zellij 自己已经启用 HTTPS，可使用以下配置：

```caddyfile
reverse_proxy https://<REMOTE_ZELLIJ_HOST>:<PORT> {
	transport http {
		tls_insecure_skip_verify
	}
	header_up Cookie "session_token=<SESSION_TOKEN>"
}
```

如果远程 Zellij 暴露的是普通 HTTP，则将 upstream 改为 `http://<REMOTE_ZELLIJ_HOST>:<PORT>`，并删除 `transport http { tls_insecure_skip_verify }`。该配置仅适用于上游本身就是 HTTPS 的场景；如果上游实际是 `localhost:8082` 这类 HTTP 服务却仍保留该段，Caddy 会报 `upstream address scheme is HTTP but transport is configured for HTTP+TLS`。无论采用哪种写法，`session_token` 都只用于通过 Zellij 自身认证，外层反代仍应保留独立访问控制，例如 caddy-security OAuth。

## remote attach

从本地终端 attach 到远端 Web server：

```bash
zellij attach https://<HOST>:<PORT>/<SESSION_NAME> --token <LOGIN_TOKEN>
zellij attach https://<HOST>:<PORT>/<SESSION_NAME> --token <LOGIN_TOKEN> --remember
```

内网或自签证书环境，优先显式传入 CA：

```bash
zellij attach https://<HOST>:<PORT>/<SESSION_NAME> --ca-cert /path/to/ca.pem
```

`--insecure` 只用于可信开发网络。

## WSL service 写法

当前 WSL systemd service（`<USERNAME>` 替换为实际系统用户名）：

```ini
[Unit]
Description=Zellij Web Server
After=network.target

[Service]
Type=simple
User=<USERNAME>
Environment=TERM=xterm-256color
Environment=COLORTERM=truecolor
ExecStart=/home/<USERNAME>/.local/bin/zellij -c /home/<USERNAME>/.config/zellij/web.kdl web
ExecStop=/home/<USERNAME>/.local/bin/zellij web --stop
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

与默认用法相比，这里的差异点如下：

- 用 `-c /home/<USERNAME>/.config/zellij/web.kdl` 指定独立配置，避免污染交互式 Zellij 配置。
- 用系统级 service 常驻，业务进程仍以 `User=<USERNAME>` 运行。
- 显式设置 `TERM` / `COLORTERM`。
- `web.kdl` 中启用 `web_server true`、`web_sharing "on"`。
- `web_server_ip "0.0.0.0"` 绑定非 localhost，所以必须配置证书和私钥。
- 未设置 `web_server_port` 时仍用默认 `8082`。

如需新增端口，可使用独立 config，或在配置中显式设置 `web_server_port <PORT>`。反代前应先对该端口重新生成并登录，拿到新的 `session_token` 后再写入 `header_up Cookie`。

重启 `zellij.service` 会让 Web 配置重新下发；如果该 service cgroup 中已有活跃 session/pane/agent 进程，可能中断现有会话，执行前先提醒用户。

## Windows 安装与数据目录

官方在 [zellij.dev/documentation/installation](https://zellij.dev/documentation/installation) 对 Windows 只说一句“从 release 页下载 binary，解压后运行 `zellij.exe`”，没规定安装路径。但每个 release 实际同时提供 4 个 Windows asset：

| 文件名（`<ver>` 为版本号，如 `0.44.3`） | 含 web client | 形态 |
|---|---|---|
| `zellij-x86_64-pc-windows-msvc.zip` | 是 | 便携 zip |
| `zellij-x86_64-pc-windows-msvc-installer.msi` | 是 | **MSI 安装包** |
| `zellij-no-web-x86_64-pc-windows-msvc.zip` | 否 | 便携 zip |
| `zellij-no-web-x86_64-pc-windows-msvc-installer.msi` | 否 | **MSI 安装包** |

推荐用 **MSI**：装完会进“添加/删除程序”、per-user 独立、卸载干净；比 zip 便于排查、比 `cargo install --locked zellij` 省事（后者要 perl/strawberry/MSVC build tools，zellij 0.43 之前 Windows 还标 experimental）。MSI 不会写 PATH，要么用绝对路径调用，要么手动把安装目录加进用户 PATH。

### 关键路径速查

| 类别 | 路径 | 备注 |
|---|---|---|
| **可执行文件**（MSI 默认） | `%LOCALAPPDATA%\Zellij\zellij.exe`，即 `C:\Users\<USER>\AppData\Local\Zellij\zellij.exe` | MSI per-user 安装的默认位置 |
| **数据目录**（含 `tokens.db`、配置等） | `%APPDATA%\Zellij\`，即 `C:\Users\<USER>\AppData\Roaming\Zellij\` | 由 [`directories` crate](https://docs.rs/directories) 的 `ProjectDirs::from("", "", "Zellij")` 决定，与是否走 MSI 无关；`tokens.db` 具体在 `%APPDATA%\Zellij\data\tokens.db` |
| 自编译产物（参考） | `<repo>\target\release\zellij.exe` | `cargo install --locked zellij` 或源码 `cargo build` 出来的位置；MSI 与之独立 |

可执行文件落在 `Local`、数据目录在 `Roaming`——**两个分散在不同根目录**，不要假设它们同父。这一点和 Linux/macOS 不一样：

| 平台 | 数据目录（`tokens.db` 在 `<data>/tokens.db`） |
|---|---|
| Linux | `~/.local/share/zellij/` |
| macOS | `~/Library/Application Support/org.Zellij Contributors.Zellij/` |
| Windows | `%APPDATA%\Zellij\data\` |

### 第三方 Windows 包管理器

`docs/THIRD_PARTY_INSTALL.md` **不列任何 Windows 渠道**（只列 Arch / Fedora / macOS Homebrew / MacPorts / Void）。winget / scoop / chocolatey 上的 zellij 都是社区维护，zellij 团队不背书。要稳定就 MSI。

### Windows 上做后台 service

Windows 上没有 systemd 对等物。常见做法：

- **NSSM** 把 `zellij.exe web` 包成 Windows Service（推荐，跟登录 session 解耦）。
- 用户登录脚本 `Start-Process -WindowStyle Hidden zellij.exe web`（不解耦，注销/锁屏可能受影响）。
- `zellij.exe web --daemonize` 直接后台化：Unix 走 pipe 信号，**Windows 走 TCP 探测启动完成**，所以 `--server-startup-timeout`（默认 10s）只在 Windows 起作用，慢机/冷启动可能要调大。

## Zellij Web 浅色主题与终端颜色

以下是 Zellij Web 浅色化中确认过的事实（最初在 `0.44.0` 排障，背景色那部分已在 `0.44.3` 由官方修复，见末尾「终端默认背景（OSC 11）」一节）。遇到类似问题先按层级判断，不要直接改 `.bashrc`。

### 用户偏好

- 颜色类持久修复优先放 Zellij KDL：`web.kdl`、layout、theme。
- 不把 OSC 颜色修复永久写进 `.bashrc`。
- 只针对某个 TUI 程序的颜色问题，优先写该程序自己的 wrapper；不要为了一个程序把 `default_shell` 改成全局 wrapper。
- `printf`/临时脚本只用于诊断或即时验证。

### 三层主题

1. **Zellij UI theme**：根级 `theme "..."`，管 tab/status/pane frame、Zellij 自己画的鼠标选区、列表/表格选中态等。
2. **Zellij Web xterm theme**：`web_client { theme { ... } }`，管浏览器 xterm.js 的背景、前景、xterm 自己的 selection 等。官方说明它和 Zellij theme 分离，不能写成继承 `pencil-light`，必须写具体 RGB。
3. **pane/终端默认颜色**：程序可通过 OSC 10/11 查询默认前景/背景。Codex 输入框背景走这一层，而不是 Codex `tui.theme`。

因此，单独设置 `theme "pencil-light"` 不会自动改变 Web xterm 的视觉主题。`web_client.theme` 与 pane 的 OSC 11 默认背景的关系按版本不同：`≤0.44.2` 两者独立，`≥0.44.3` 起 `web_client.theme.background` 会被 seed 到 OSC 11（见下面「终端默认背景（OSC 11）」一节）。

`pencil-light` 的主色来自内置主题：

- foreground `66 66 66` = `#424242`
- background `241 241 241` = `#f1f1f1`（官方值；本模板把这一“白/底色”统一提到 `255 255 255` = `#ffffff`，对齐 Copilot CLI `github` 浅色主题，详见「模板差异」）

### 浅色模式设置参考

当前推荐的浅色 Web 主题名为 `pencil-light-select-blue`：整体沿用 `pencil-light` 的浅色背景，鼠标/列表选中态改为蓝底白字，Web 终端使用 VS Code Modern Light 风格的竖线光标。

`web_client.theme` 需要写具体 RGB；`themes { pencil-light-select-blue { ... } }` 应从内置 `pencil-light` 复制完整结构，再重点把 `text_selected`、`table_cell_selected`、`list_selected` 改成蓝底白字。具体改动见下一节的模板差异，不要只抄片段。

浏览器 Console 中 `term.options.theme` 会显示 camelCase 字段，例如 `selectionBackground`。若这里已有 `rgb(0, 120, 215)`，说明 `web_client.theme` 已正确下发。

Codex 在 Zellij 中渲染空输入占位文本时会使用 ANSI `white`，所以浅色模式要显式设置 `white` / `bright_white`，避免占位提示变成白字贴白底。

### 模板差异

不要只写精简版 palette（例如只写 `fg/bg/blue` 这类字段）。Zellij `0.44.x` 的内置主题实际使用 `text_*`、`ribbon_*`、`frame_*` 等完整段落；如果自定义主题只补 `text_selected` 或简单颜色，普通选区可能变好，但 tab/status/compact-bar 等插件栏颜色和状态可能异常。

正确做法：复制完整 `pencil-light` 主题结构，命名为 `pencil-light-select-blue`，只在两个维度上改，其余段落原样沿用官方：

1. **白/底色 → 纯白**：把官方当“白/底色”用的 `241 241 241`（`#f1f1f1`）全部替换为 `255 255 255`（`#ffffff`）。原因：Copilot CLI `github` 浅色主题的 `backgroundPrimary` = `#ffffff`（纯白），官方 pencil-light 的 `#f1f1f1` 略暗，Copilot pane 与 Zellij 画布/状态栏并排时有可见色差；统一纯白即消除接缝。注意 `web_client.theme.background` 同时是 `≥0.44.3` 回给 pane 的 OSC 11 背景种子，变纯白后明暗探测仍判浅色。
2. **选中态 → 蓝底白字**：仅 `text_selected` / `table_cell_selected` / `list_selected` 三段，让鼠标拖选可见。

下面只列差异。

`web.kdl` 根级差异：

```kdl
web_server true
web_server_ip "127.0.0.1"
web_server_port 8082
web_sharing "on"
show_startup_tips false
theme "pencil-light-select-blue"
default_layout "pencil-light"
```

公网/反代场景按需把 `web_server_ip` 改为 `0.0.0.0` 并补 `web_server_cert` / `web_server_key`；本机 Caddy 反代或 SSH tunnel 场景保持 `127.0.0.1` 即可。

`themes { pencil-light-select-blue { ... } }`：先把复制来的官方结构里所有 `241 241 241` 改成 `255 255 255`，再把下面三段选中态改成蓝底白字，其余沿用 `pencil-light`：

```kdl
text_selected {
    base 255 255 255
    background 0 120 215
    emphasis_0 215 95 95
    emphasis_1 32 165 186
    emphasis_2 16 167 120
    emphasis_3 0 142 196
}

table_cell_selected {
    base 255 255 255
    background 0 120 215
    emphasis_0 215 95 95
    emphasis_1 32 165 186
    emphasis_2 16 167 120
    emphasis_3 182 214 253
}

list_selected {
    base 255 255 255
    background 0 120 215
    emphasis_0 215 95 95
    emphasis_1 32 165 186
    emphasis_2 16 167 120
    emphasis_3 182 214 253
}
```

`web_client.theme` 差异：

```kdl
web_client {
    font "monospace"
    cursor_blink true
    cursor_style "bar"
    theme {
        background 255 255 255
        foreground 66 66 66
        white 75 85 99
        bright_white 107 114 128
        cursor 66 66 66
        cursor_accent 255 255 255
        selection_background 0 120 215
        selection_foreground 255 255 255
        selection_inactive_background 153 201 239
    }
}
```

对应 `~/.config/zellij/layouts/pencil-light.kdl`：

```kdl
layout {
    pane default_fg="#424242" default_bg="#ffffff"
    pane size=1 borderless=true {
        plugin location="compact-bar"
    }
}
```

### 终端默认背景（OSC 11）：Web 模式黑底，v0.44.3 已修复

**问题**：靠 OSC 11（查询终端默认背景）判明暗的 TUI——Codex 输入框、Copilot CLI 主题——在 Zellij `≤0.44.2` 的 Web 浅色主题下会把背景误判成黑，于是用深色模式配色（浅色文字）贴在浅底上，表现为输入框黑块、正文字发淡。深色 zellij 主题时碰巧“对”，只有浅色主题才暴露。

根因：Web 模式没有可转发的真实宿主终端，pane 发 OSC 11 查询时 Zellij 回的是 `terminal_emulator_colors.bg`，这个值停在 `Palette::default()` 的黑色。当时 `web_client.theme.background` 只改 xterm.js 的视觉背景，不影响 OSC 11 的回答；只能靠 layout `default_bg` / `set-pane-color` / 程序 wrapper 兜底，且 split 出的新 pane、复活恢复的 pane 都会漏掉。

**官方修复（`v0.44.3` 对比 `v0.44.0`）**：一整套 host-query 转发 + seed 机制（`git diff v0.44.0 v0.44.3` 关键文件）：

| 文件 | 改了什么 |
|---|---|
| `zellij-client/src/web_client/host_query_seed.rs`（新增 ~452 行） | `build_host_query_seed_msgs()` 从 `web_client.theme.background/foreground` 生成 `BackgroundColor`/`ForegroundColor` seed 消息（未设则回退到主题 `text_unselected`） |
| `zellij-client/src/web_client/server_listener.rs`（+34） | attach 时、以及每次配置重载（`new_config`）时都调 `build_host_query_seed_msgs` 并 `send_to_server`，把浅背景播种进服务端 host-query 缓存 |
| `zellij-server/src/host_query.rs`（新增 ~180 行） | 新增 host-query 模块：pane 的 OSC 10/11/4 查询走“用 seeded 缓存应答，否则转发宿主”的路径 |
| `zellij-server/src/panes/grid.rs`（±587） | OSC 查询分支重构，新增 `pending_forwarded_queries`，OSC 11 query 命中 seeded 背景即回浅色 |

效果：升级到 `≥0.44.3` 后，只要 `web_client.theme.background` 设了浅色（见上面的浅色模式配置），OSC 11 就会返回该背景，**所有 pane（含 split / 复活）统一生效**，不再必须依赖 layout `default_bg`、`set-pane-color` 或 Codex OSC wrapper 这些兜底（保留也无害）。升级后已存在的会话要重新 attach 一次，让 seed 重新下发。

### 终端能力响应漏到 shell

命令行里突然出现 `62;4;52c` 这类文本时，通常是终端对 ANSI Device Attributes 查询的响应，完整控制序列类似 `ESC [ ? 62 ; 4 ; 52 c`，前缀被终端解释或复制时丢掉后只剩尾部可见。它不是 bash 代码，也不是 `.bashrc` 字符串。

在 Zellij Web / xterm.js / 终端程序互相探测能力时，如果查询方退出或没有读取响应，响应可能落进 shell 输入行。先用 `Ctrl+C` 或 `Ctrl+U` 清掉当前输入；后续排查不要优先改 `.bashrc`，应先检查 Zellij Web、xterm theme、shell wrapper、以及是否有程序在发 `CSI c` / `OSC 10/11` 查询。

### 鼠标拖选颜色

不要把两种 selection 混淆：

- `web_client.theme.selection_background` 管 xterm.js 自己的 selection。`term.select(0, 0, 20)` 变蓝，说明这一层正常。
- 普通鼠标拖选在 `mouse_mode true` 时走 Zellij 自己的鼠标选择/复制路径，颜色来自 Zellij theme 的 `text_selected`，不是 `web_client.theme.selection_background`。

如果浏览器端 `term.options.theme` 已正确、`term.select(...)` 也是蓝色，但普通鼠标拖选颜色仍不对，问题不在配置下发，而在 Zellij 鼠标选择层。

源码确认 Zellij terminal pane 鼠标选区使用：

```kdl
text_selected {
    base ...
    background ...
}
```

内置 `pencil-light` 的 `text_selected.background` 也是 `241 241 241`，和普通背景一样，因此鼠标拖选会像白底贴白底。解决方式：复制 `pencil-light` 为自定义主题，只改 Zellij 选中态，例如：

具体改动见“模板差异”。重点是 `text_selected`、`list_selected`、`table_cell_selected` 都要改为蓝底白字，同时保留 `pencil-light` 的其余完整 theme 段落。

官方 mouse 兼容建议：`mouse_mode true` 时 Zellij 接管鼠标；按住 `Shift` 可让终端处理选择/链接/复制/滚动。也可设置：

```kdl
mouse_mode false
```

但这会减少 Zellij 鼠标能力，例如点击 pane 聚焦、拖边框 resize、滚轮 scrollback、链接/路径点击、hover 效果等。用户倾向保留 `mouse_mode`，通过自定义 Zellij theme 修正 Zellij 自己的选区颜色。
