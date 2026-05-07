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

重启 `zellij.service` 会让 Web 配置重新下发；如果该 service cgroup 中已有活跃 session/pane/agent 进程，可能中断现有会话，执行前先提醒用户。

## Zellij Web 浅色主题与 Codex 颜色踩坑

以下是一次 Zellij `0.44.0` Web 浅色化排障中确认过的事实。后续遇到类似问题，先按层级判断，不要直接改 `.bashrc`。

### 用户偏好

- 颜色类持久修复优先放 Zellij KDL：`web.kdl`、layout、theme。
- 不把 OSC 颜色修复永久写进 `.bashrc`。
- `printf`/临时脚本只用于诊断或即时验证。

### 三层主题

1. **Zellij UI theme**：根级 `theme "..."`，管 tab/status/pane frame、Zellij 自己画的鼠标选区、列表/表格选中态等。
2. **Zellij Web xterm theme**：`web_client { theme { ... } }`，管浏览器 xterm.js 的背景、前景、xterm 自己的 selection 等。官方说明它和 Zellij theme 分离，不能写成继承 `pencil-light`，必须写具体 RGB。
3. **pane/终端默认颜色**：程序可通过 OSC 10/11 查询默认前景/背景。Codex 输入框背景走这一层，而不是 Codex `tui.theme`。

因此，单独设置 `theme "pencil-light"` 不会自动改变 Web xterm 的视觉主题；单独设置 `web_client.theme` 也不会改变 pane 的 OSC 11 默认背景。

`pencil-light` 的主色来自内置主题：

- foreground `66 66 66` = `#424242`
- background `241 241 241` = `#f1f1f1`

### 浅色模式设置参考

当前推荐的浅色 Web 主题名为 `pencil-light-select-blue`：整体沿用 `pencil-light` 的浅色背景，鼠标/列表选中态改为蓝底白字，Web 终端使用 VS Code Modern Light 风格的竖线光标。

`web_client.theme` 需要写具体 RGB；`themes { pencil-light-select-blue { ... } }` 应从内置 `pencil-light` 复制完整结构，再重点把 `text_selected`、`table_cell_selected`、`list_selected` 改成蓝底白字。具体改动见下一节的模板差异，不要只抄片段。

浏览器 Console 中 `term.options.theme` 会显示 camelCase 字段，例如 `selectionBackground`。若这里已有 `rgb(0, 120, 215)`，说明 `web_client.theme` 已正确下发。

Codex 在 Zellij 中渲染空输入占位文本时会使用 ANSI `white`，所以浅色模式要显式设置 `white` / `bright_white`，避免占位提示变成白字贴白底。

### 模板差异

不要只写精简版 palette（例如只写 `fg/bg/blue` 这类字段）。Zellij `0.44.x` 的内置主题实际使用 `text_*`、`ribbon_*`、`frame_*` 等完整段落；如果自定义主题只补 `text_selected` 或简单颜色，普通选区可能变好，但 tab/status/compact-bar 等插件栏颜色和状态可能异常。

正确做法：复制完整 `pencil-light` 主题结构，命名为 `pencil-light-select-blue`，其余段落保持 `pencil-light` 模板，只改下面这些差异。

`web.kdl` 根级差异：

```kdl
web_server true
web_server_ip "127.0.0.1"
web_server_port 8082
web_sharing "on"
show_startup_tips false
default_shell "/home/timidly/.local/bin/zellij-light-shell"
theme "pencil-light-select-blue"
default_layout "pencil-light"
```

公网/反代场景按需把 `web_server_ip` 改为 `0.0.0.0` 并补 `web_server_cert` / `web_server_key`；本机 Caddy 反代或 SSH tunnel 场景保持 `127.0.0.1` 即可。

`themes { pencil-light-select-blue { ... } }` 内只改这三段，其余段落沿用 `pencil-light`：

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
        background 241 241 241
        foreground 66 66 66
        white 75 85 99
        bright_white 107 114 128
        cursor 66 66 66
        cursor_accent 241 241 241
        selection_background 0 120 215
        selection_foreground 255 255 255
        selection_inactive_background 153 201 239
    }
}
```

对应 `~/.config/zellij/layouts/pencil-light.kdl`：

```kdl
layout {
    pane default_fg="#424242" default_bg="#f1f1f1"
    pane size=1 borderless=true {
        plugin location="compact-bar"
    }
}
```

对应 `~/.local/bin/zellij-light-shell`：

```bash
#!/usr/bin/env bash

if [ -t 1 ]; then
    printf '\033]10;#424242\007\033]11;#f1f1f1\007'
fi

exec /bin/bash "$@"
```

这个 wrapper 的作用是给新 pane 兜底下发 OSC 10/11 默认前景/背景，再进入真实 bash。它不应该写进 `.bashrc`，因为普通 SSH、非 Zellij 终端、批处理脚本不一定需要这层终端颜色修复。

### Codex 输入框黑底

Codex TUI 源码行为：输入框样式会根据终端默认背景计算；`/theme` 或 `tui.theme` 主要影响语法高亮、diff/code block，不直接决定输入框背景。

诊断 OSC 11：

```bash
printf '\e]11;?\a'
```

简单 `read` 可能读不到响应；需要 raw tty 脚本更可靠。本次确认过的黑底响应：

```text
b'\x1b]11;rgb:0000/0000/0000\x1b\\'
```

临时修复验证：

```bash
printf '\033]10;#424242\007\033]11;#f1f1f1\007'
```

永久修复优先用 layout 的 pane 默认颜色：

```kdl
layout {
    pane default_fg="#424242" default_bg="#f1f1f1"
}
```

可配 `default_layout "pencil-light"` 并在 `~/.config/zellij/layouts/pencil-light.kdl` 中设置顶层 `pane default_fg/default_bg`。如果 layout 对某些新 pane 不生效，`default_shell` wrapper 发 OSC 10/11 只能作为兜底，不是首选。

注意：`web_client.theme.background` 只管浏览器 xterm 视觉背景，不等价于 pane 的 OSC 11 默认背景；`zellij action set-pane-color` 在本环境曾出现无输出且不结束，不作为首选方案。

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
