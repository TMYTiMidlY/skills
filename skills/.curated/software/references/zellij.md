# Zellij

官方文档：

- Web client: <https://zellij.dev/documentation/web-client.html>
- Options: <https://zellij.dev/documentation/options.html>

## Web client

Zellij 内置 Web server，默认关闭。手动启动：

```bash
zellij web
```

默认监听 `http://127.0.0.1:8082`。如果绑定到非 localhost，HTTPS 证书是硬要求，必须配置 `web_server_cert` 和 `web_server_key`。对公网或不可信网络暴露时，外层仍应放 Caddy/nginx 并加认证；拿到 Zellij Web 访问权基本等同拿到运行该服务的系统用户 shell。

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

`default_shell` 控制新 pane 使用的 shell，默认取 `$SHELL`。systemd/sudo/service 环境下 `$SHELL` 可能不符合预期，服务化时显式写 `/bin/bash`、`/usr/bin/fish`、`/usr/bin/zsh` 这类绝对路径。

`web_sharing "on"` 表示终端启动的新 session 默认通过 Web server 共享；只想显式共享时用 `"off"`，完全禁用共享时用 `"disabled"`。

## login token 与 session token

`zellij web --create-token` 生成登录令牌，令牌只显示一次，Zellij 本地只存 hash。反代需要给 upstream 注入 Cookie 时，应针对目标端口重新登录并提取 `session_token`，不要复用别的端口或实例的 token。

本机 HTTP 示例；如果该端口启用了 HTTPS，把 URL 改成 `https://127.0.0.1:<PORT>`：

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

Caddy upstream 注入示例：

```caddyfile
reverse_proxy https://<ZELLIJ_HOST>:<PORT> {
    transport http {
        tls_insecure_skip_verify
    }
    header_up Cookie "session_token=<SESSION_TOKEN>"
}
```

这个 Cookie 只用于通过 Zellij 自身认证；外层反代仍要有独立访问控制，例如 caddy-security OAuth。

## remote attach

从本地终端 attach 到远端 Web server：

```bash
zellij attach https://<HOST>:<PORT>/<SESSION_NAME> --token <LOGIN_TOKEN>
zellij attach https://<HOST>:<PORT>/<SESSION_NAME> --token <LOGIN_TOKEN> --remember
```

内网/自签证书优先传 CA：

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

相对官方默认用法的差异：

- 用 `-c /home/timidly/.config/zellij/web.kdl` 指定独立配置，避免污染交互式 Zellij 配置。
- 用系统级 service 常驻，业务进程仍以 `User=timidly` 运行。
- 显式设置 `TERM` / `COLORTERM`。
- `web.kdl` 中启用 `web_server true`、`web_sharing "on"`。
- `web_server_ip "0.0.0.0"` 绑定非 localhost，所以必须配置证书和私钥。
- 未设置 `web_server_port` 时仍用默认 `8082`。

新增端口时，用独立 config 或在 config 中设置 `web_server_port <PORT>`；反代前先对该端口生成新的 `session_token`，再写 `header_up Cookie`。
