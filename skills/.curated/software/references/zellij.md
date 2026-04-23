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

## login token 与 session token

`zellij web --create-token` 用于生成登录令牌。该令牌只显示一次，Zellij 本地仅保存其 hash。需要在反代中透传认证时，应针对目标端口重新登录并提取对应的 `session_token`，不要复用其他端口或其他实例生成的 token。

以下示例使用本机 HTTP 端口；如果目标端口已启用 HTTPS，将 URL 改为 `https://127.0.0.1:<PORT>`：

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

当前 WSL systemd service：

```ini
[Unit]
Description=Zellij Web Server
After=network.target

[Service]
Type=simple
User=timidly
Environment=TERM=xterm-256color
Environment=COLORTERM=truecolor
ExecStart=/home/timidly/.local/bin/zellij -c /home/timidly/.config/zellij/web.kdl web
ExecStop=/home/timidly/.local/bin/zellij web --stop
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

与默认用法相比，这里的差异点如下：

- 用 `-c /home/timidly/.config/zellij/web.kdl` 指定独立配置，避免污染交互式 Zellij 配置。
- 用系统级 service 常驻，业务进程仍以 `User=timidly` 运行。
- 显式设置 `TERM` / `COLORTERM`。
- `web.kdl` 中启用 `web_server true`、`web_sharing "on"`。
- `web_server_ip "0.0.0.0"` 绑定非 localhost，所以必须配置证书和私钥。
- 未设置 `web_server_port` 时仍用默认 `8082`。

如需新增端口，可使用独立 config，或在配置中显式设置 `web_server_port <PORT>`。反代前应先对该端口重新生成并登录，拿到新的 `session_token` 后再写入 `header_up Cookie`。
