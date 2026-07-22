# 共享 Linux 节点的网络与 Web 服务栈

## <a id="scope"></a>适用范围

这是一套经过实际部署验证的共享 Linux 节点配置：专用普通用户运行 Mihomo TUN，公网入口机负责 TLS，内网节点上的 Caddy 负责独立 OAuth 和本机服务路由，再用 systemd 模板为多个 Unix 用户启动 Zellij Web 与 VS Code Serve Web。

适用前提：

- 公网入口机与内网节点之间已有 EasyTier 一类的加密三层网络。
- 内网节点本身没有公网入口，或不希望直接暴露公网端口。
- 多个 Unix 用户需要各自独立的浏览器终端与编辑器。
- 公网只暴露 Caddy；Mihomo、Zellij、VS Code 和 Caddy Admin API 都留在本机或组网内部。

具体的 Caddy 指令、OAuth provider 选项和更新流程仍以 `vps-maintenance` skill 的 Caddy 主题为准；Zellij token 的完整生命周期见 `software` skill 的 Zellij 主题。

## <a id="topology"></a>链路与信任边界

```text
浏览器
  │ HTTPS（公网证书）
  ▼
公网入口 Caddy
  │ HTTP，封装在 EasyTier 加密隧道内
  ▼
内网节点 Caddy
  ├─ caddy-security OAuth / authorization policy
  ├─ HTTP → Zellij Web（localhost）
  └─ HTTP → VS Code Serve Web（localhost）
```

### <a id="tls-boundary"></a>TLS 终止与内部 HTTP

公网证书由入口 Caddy 申请和续期。内网 Caddy 只监听组网地址上的高位 HTTP 端口，不参与公网 ACME。

入口到内网节点使用 HTTP，但链路字节仍由 EasyTier 加密。代价是入口机终止 TLS，因此能看到请求正文和 Cookie；只有把入口机纳入信任边界时，才适合采用这种结构。

多层反代必须保留公网的 `X-Forwarded-Proto: https`。缺失时，OAuth 回跳可能被生成成 HTTP；依赖 forwarded scheme 生成绝对 URL 的上游也会得到错误地址。

### <a id="sni-passthrough"></a>TCP/SNI 透传的替代架构

如果入口机不应看到请求正文或 Cookie，应让内网 Caddy 终止 TLS。普通 DNAT 或 TCP 转发无法按域名分流，因为 TCP 层只有目标 IP 和端口；按域名透传 TLS 需要 `caddy-l4`、HAProxy `ssl_preread` 一类能读取 ClientHello SNI 的四层代理。

## <a id="identity"></a>用户身份与目录权限

将网络代理放在专用普通用户下，而不是 root：

```text
/home/<proxy-user>/.local/bin/mihomo
/home/<proxy-user>/.config/mihomo/
```

systemd 服务显式设置：

```ini
User=<proxy-user>
Group=<proxy-user>
Environment=HOME=/home/<proxy-user>
```

如果 root 先创建了 `/home/<proxy-user>/.config/<child>`，中间的 `.config` 可能意外变成 `root:root`，导致用户无法创建其他配置目录。除了检查最终子目录，也要检查父目录：

```bash
stat -c '%U:%G %a %n' \
  /home/<proxy-user>/.config \
  /home/<proxy-user>/.config/<child>
```

不要为了让端口顺序好看而交换已有 UID。修改 UID 会牵连文件属主、ACL、systemd user runtime、subuid/subgid 和运行中进程；端口按 UID 公式推导即可。

## <a id="egress-dns"></a>出站代理与 DNS

### <a id="mihomo"></a>Mihomo 安装与配置迁移

实测使用 [Mihomo v1.19.29](https://github.com/MetaCubeX/mihomo/releases/tag/v1.19.29) 的 `linux-amd64-compatible` 单文件二进制。拿不准 CPU 指令集时选择 `compatible`，不为少量性能冒险使用过高的 GOAMD64 等级。

从另一台机器迁移时，复制 Mihomo 自己的配置目录：

```text
%USERPROFILE%\.config\mihomo        # Windows
~/.config/mihomo                    # Linux
```

GUI 自己生成的 `clash-verge.yaml` 不应成为独立 Mihomo 的长期配置源；GUI 配置链和独立 CLI 配置属于两套生命周期。

推荐复制：

```text
config.yaml
GeoSite.dat
cache.db
providers/
ruleset/
ui/
```

历史备份文件不必同步到服务端。传输后收紧权限：

```bash
chmod 700 /home/<proxy-user>/.config/mihomo
chmod 600 /home/<proxy-user>/.config/mihomo/config.yaml
```

远端只供本机使用时，把代理入口和控制口限制在 loopback：

```yaml
mixed-port: <proxy-port>
allow-lan: false
bind-address: 127.0.0.1
external-controller: 127.0.0.1:<controller-port>
```

### <a id="mesh-routing"></a>TUN 与组网路由排除

TUN 要保留组网网段，避免 Mihomo 接管 SSH 或运维链路：

```yaml
tun:
  enable: true
  stack: mixed
  auto-route: true
  auto-detect-interface: true
  strict-route: true
  dns-hijack:
    - any:53
  route-exclude-address:
    - <mesh-cidr>
```

`route-exclude-address` 只负责让目标网段不进入 Mihomo TUN；仍需确认系统路由表中存在可用的 EasyTier 路由。Mihomo 的 `DIRECT`、TUN bypass 与组网转发边界见 [Mihomo 的 TUN 与系统路由](mihomo.md#tun-routing)。

### <a id="systemd-capabilities"></a>systemd 服务能力

systemd 服务的目标形态：

```ini
[Unit]
Description=Mihomo Proxy Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=<proxy-user>
Group=<proxy-user>
WorkingDirectory=/home/<proxy-user>
Environment=HOME=/home/<proxy-user>
ExecStartPre=/home/<proxy-user>/.local/bin/mihomo -t -d /home/<proxy-user>/.config/mihomo
ExecStart=/home/<proxy-user>/.local/bin/mihomo -d /home/<proxy-user>/.config/mihomo
Restart=on-failure
RestartSec=5
LimitNOFILE=1048576
AmbientCapabilities=CAP_NET_ADMIN CAP_NET_RAW
CapabilityBoundingSet=CAP_NET_ADMIN CAP_NET_RAW

[Install]
WantedBy=multi-user.target
```

`/dev/net/tun` 通常可由普通用户打开，创建接口和路由仍需要 `CAP_NET_ADMIN`。

### <a id="dns"></a>systemd-resolved 接入

DNS 劫持、DoH、`fake-ip` 与 `redir-host` 的机制见 [Mihomo 的 DNS 泄漏与配置](mihomo.md#dns-leak)。这里只描述 Linux 宿主接入 `systemd-resolved` 的部署形态。

只写 `tun.dns-hijack: any:53` 不一定能接管 Linux 宿主 DNS。`systemd-resolved` 默认让应用查询 `127.0.0.53`，再由 resolved 自己访问上游；这条链可能绕过预期的 TUN DNS 路径，继续得到污染记录。

一种稳定做法是让 Mihomo 显式监听非特权 DNS 端口：

```yaml
dns:
  enable: true
  listen: 127.0.0.1:<dns-port>
  ipv6: false
  respect-rules: true
  enhanced-mode: redir-host
  default-nameserver:
    - 223.5.5.5
    - 1.1.1.1
  nameserver:
    - https://<domestic-doh-ip>/dns-query
    - https://<domestic-doh-host>/dns-query
  nameserver-policy:
    geosite:cn,private:
      - https://<domestic-doh>/dns-query
    geosite:geolocation-!cn:
      - https://<overseas-doh>/dns-query
```

再通过 `/etc/systemd/resolved.conf.d/` 把全局上游指向 Mihomo：

```ini
[Resolve]
DNS=127.0.0.1:<dns-port>
FallbackDNS=223.5.5.5 1.1.1.1
Domains=~.
```

这里保留 `redir-host`，是为了让本机 coding agent、SSRF 防护和普通网络工具看到真实 IP。`fake-ip` 分流更直接，但会把域名解析成 `198.18.0.0/15`，某些工具会把保留地址误判为 SSRF。

## <a id="caddy"></a>公网入口与内网网关

为减少 Caddyfile 语法、默认值和排障口径的差异，实测部署让入口与内网 Caddy 使用同一构建。独立 OAuth portal 并不要求两端共享 Cookie 或 JWT，但统一版本更易维护。实测组合：

- [Caddy v2.11.2](https://github.com/caddyserver/caddy/releases/tag/v2.11.2)
- [caddy-security v1.1.61](https://github.com/greenpau/caddy-security/releases/tag/v1.1.61)
- go-authcrunch v1.1.38

### <a id="ingress-caddy"></a>入口 Caddy

入口 Caddy 只负责：

- 公网 TLS 和 on-demand 证书；
- 把匹配域名转到内网 Caddy 的固定组网地址；
- 明确传递原始 Host 和公网 HTTPS scheme；
- 给 WebSocket 设置有界 `stream_timeout`。

```caddyfile
*.<zone>, *.<user-a>.<zone>, *.<user-b>.<zone> {
	tls {
		on_demand
	}
	reverse_proxy <mesh-node-ip>:<internal-caddy-port> {
		header_up Host {host}
		header_up X-Forwarded-Proto https
		stream_timeout 24h
	}
}
```

### <a id="internal-caddy"></a>内网 Caddy

内网 Caddy：

- 只绑定组网 IP；
- 只允许入口机和本机地址访问；
- 关闭自动 HTTPS；
- 使用独立 OAuth portal 和独立 JWT key；
- 导入显式 route 文件，不把 secret 写进 route。

```caddyfile
{
	auto_https off
	order authenticate before respond
	order authorize before basicauth

	security {
		# provider / portal / explicit policies
	}
}

:<internal-caddy-port> {
	bind <mesh-node-ip>

	@blocked {
		not remote_ip <ingress-mesh-ip> <mesh-node-ip> 127.0.0.1 ::1
	}
	respond @blocked 403

	import /etc/caddy/routes.d/*.caddy
	respond 404
}
```

### <a id="domain-matching"></a>多层域名匹配

Caddy 的 `*.<zone>` host matcher 只匹配一层。`zellij.<user>.<zone>` 有两层，因此入口站点还要列出 `*.<user>.<zone>`。DNS 能解析嵌套名称，不代表 Caddy 的 host matcher 会接收它。

## <a id="auth"></a>OAuth 与路由

### <a id="cookie-jwt"></a>Cookie 与 JWT 隔离

如果入口机已经对父域签发 caddy-security Cookie，内网 portal 不应继续使用默认 Cookie 名。父域 Cookie 会发送到更深的子域；两套 JWT key 不同却同名时，gatekeeper 可能先读到入口机 token，出现：

```text
keystore: failed to parse token
登录成功后反复跳转
```

内网 portal 与 policy 应显式固定一个独立名称：

```caddyfile
authentication portal <portal> {
	cookie domain <internal-zone>
	set access_token cookie name <unique-cookie-name>
	crypto key sign-verify {env.JWT_SHARED_KEY}
	# ...
}

authorization policy <policy> {
	set access_token cookie name <unique-cookie-name>
	set token sources cookie
	crypto key verify {env.JWT_SHARED_KEY}
	# ...
}
```

### <a id="provider-realm"></a>Provider、realm 与角色

OAuth provider 的 callback URL 由 portal host、handle 前缀和 provider `realm` 共同决定。创建 GitHub OAuth App 时，callback 必须逐字匹配：

```text
https://<auth-host>/oauth2/<realm>/authorization-code-callback
```

`transform user` 的 `match realm` 也必须使用同一个 realm。Caddyfile 正则只需要一层转义：

```caddyfile
regex match sub "(?i)^github\.com/<account>$"
```

写成 `github\\.com` 会匹配失败，用户能登录却拿不到目标角色。

### <a id="authorization"></a>显式授权策略

共享入口与个人入口使用显式 policy，不依赖模板推导：

```text
network_admin  → 两位指定管理员
user_a_access  → 只允许用户 A
user_b_access  → 只允许用户 B
```

角色规则变更后，旧 JWT 不会自动刷新。轮换内网 JWT key，或让用户清理独立 Cookie 并重新登录，才能获得新角色。

### <a id="routes"></a>路由片段与 secret

推荐域名：

```text
zellij.<user>.<zone>
code.<user>.<zone>
```

路由片段由内网 Caddy 显式导入，并通过 `{env.*}` 引用 secret；不要把 token 或 JWT key 写进 route。环境文件或 systemd credential 应限制为服务账号可读。

### <a id="zellij-token"></a>Zellij token 迁移

Zellij login token 是长期凭据，session token 默认只有数周。无人值守反代可定期兑换新 session token；自用场景也可以在备份 SQLite 后延长相应记录的 `expires_at`，但这是绕过上游设计的维护性取舍。

旧配置中可能存在：

```caddyfile
header_up Cookie "session_token=<literal-token>"
```

这种配置把 Zellij token 直接写入 Caddyfile，并会随文件复制进入历史备份。只要 token 仍有效，能读取当前配置或旧备份的人就能以浏览器身份访问 Zellij。

迁移时先生成新 token，把它放入 root-only 环境文件或 systemd credential，再把 route 改为 `{env.ZELLIJ_USER_SESSION_TOKEN}` 一类引用。验证新 token 后撤销旧 token；由于历史备份仍含旧值，只改当前 Caddyfile 不够，旧 token 也必须轮换。

## <a id="multi-user"></a>多用户 Web 服务

### <a id="uid-ports"></a>UID 端口映射

多用户服务按 UID 推导端口：

```text
port = base_port + user_uid - base_uid
```

UID 公式和 system manager specifier 的完整语义见 `software` skill 的 Service / systemd 主题。这里保留这套网络栈中的实例形态。

### <a id="zellij-web"></a>Zellij Web

Zellij 只绑定 localhost，外层 OAuth 通过后，Caddy 向上游注入每用户独立的 `session_token`：

```caddyfile
@zellij_user host zellij.<user>.<zone>
handle @zellij_user {
	authorize with <user-policy>
	reverse_proxy 127.0.0.1:<zellij-port> {
		header_up Cookie "session_token={env.ZELLIJ_USER_SESSION_TOKEN}"
		stream_timeout 24h
	}
}
```

Zellij 绑定 `127.0.0.1` 时不需要自己的 HTTPS 证书，公网 HTTPS 由 Caddy 提供；只有 Zellij 自己监听非 loopback 时才强制配置证书。

### <a id="code-web"></a>VS Code Serve Web

VS Code Serve Web 同样只绑定 localhost，并依赖外层 OAuth：

```caddyfile
@code_user host code.<user>.<zone>
handle @code_user {
	authorize with <user-policy>
	reverse_proxy 127.0.0.1:<code-port> {
		stream_timeout 24h
	}
}
```

内部企业网络部署 VS Code Server 时仍应阅读并遵守 [Microsoft VS Code Server License](https://code.visualstudio.com/license/server)。`--without-connection-token` 仅适合 localhost 加外层鉴权的结构。

### <a id="templates"></a>systemd 模板

`zellij@.service` 的关键部分：

```ini
[Service]
User=%i
Group=%i
WorkingDirectory=/home/%i
Environment=HOME=/home/%i
Environment=TERM=xterm-256color
Environment=COLORTERM=truecolor
ExecStart=/bin/sh -c 'uid=$(id -u %i); port=$((<zellij-base-port> + uid - <base-uid>)); exec /usr/bin/zellij -c /home/%i/.config/zellij/web.kdl web --ip 127.0.0.1 --port "$port"'
ExecStop=/usr/bin/zellij web --stop
Restart=on-failure
```

system-level template 中不要用 `%U` 推导实例用户目录。它会解析成 system manager 的 UID `0`；若多个实例因此访问 root 的 `0700` socket 目录，日志会出现 `Permission denied` / `Server not ready`，浏览器表现为登录后黑屏。删掉手工设置的 `ZELLIJ_SOCKET_DIR`，让 Zellij 按实际进程 UID 选择 `/tmp/zellij-<uid>` 即可。详细 specifier 语义见 `software` skill 的 Service / systemd 主题。

`code-serve-web@.service` 的关键部分：

```ini
[Service]
User=%i
Group=%i
WorkingDirectory=/home/%i
Environment=HOME=/home/%i
Environment=VSCODE_CLI_DATA_DIR=/home/%i/.vscode/cli
ExecStart=/bin/sh -c 'uid=$(id -u %i); port=$((<code-base-port> + uid - <base-uid>)); exec /usr/bin/code serve-web --host 127.0.0.1 --port "$port" --without-connection-token --accept-server-license-terms --disable-telemetry --server-data-dir /home/%i/.vscode-server/serve-web'
Restart=on-failure
```

每个实例使用自己的 HOME、扩展目录、用户数据和进程权限。

## <a id="verification"></a>验证矩阵

部署完成后按层验证，不只检查 `LISTEN`：

| 层 | 检查 |
|---|---|
| systemd | unit 为 `enabled` + `active`，`User=` 与实例名一致 |
| 端口 | localhost 端口与 UID 公式一致 |
| Mihomo | 显式 HTTP/SOCKS 代理能访问目标站点 |
| TUN | 清除代理环境变量后，普通请求仍能访问目标站点 |
| 组网 | 运维地址仍走 EasyTier 接口，没有进入 Mihomo TUN |
| DNS | systemd-resolved 全局上游指向 Mihomo DNS listener |
| 内网 Caddy | 入口机带 Host + `X-Forwarded-Proto: https` 时得到正确 OAuth 跳转 |
| 公网 Caddy | 首次 TLS 握手能申请证书，未登录请求跳独立 portal |
| OAuth | callback、realm、角色和独立 Cookie 名一致 |
| Zellij | 真 session token 的 `/ws/control` 返回 `101`，伪 token 返回 `401` |
| VS Code | 根页面返回 HTML，WebSocket 经过外层 Caddy 可建立 |

验证透明 TUN 时清除所有代理环境变量：

```bash
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
    -u http_proxy -u https_proxy -u all_proxy \
    curl --noproxy '*' -I https://<blocked-site>
```

## <a id="pitfalls"></a>故障诊断

### <a id="ssh-reuse"></a>SSH 连接复用

**症状**：一次 SSH 命令看起来像已成功改用公钥认证，重新连接却仍要求密码。

OpenSSH `ControlMaster` 可能复用旧的密码会话。排查认证时禁用连接复用并重新握手，避免把旧会话误判为新认证成功。

### <a id="dns-pollution"></a>DNS 污染

**症状**：Mihomo TUN 已开启，Linux 宿主仍解析出污染记录。

确认 `systemd-resolved` 的全局上游确实指向 Mihomo DNS listener，而不是只配置了 `dns-hijack: any:53`。另一个常见误测是：

```bash
curl -x <proxy> --noproxy '*' ...
```

`--noproxy '*'` 会抵消显式代理，不能用来证明代理入口可用。

### <a id="oauth-loop"></a>OAuth 登录循环

**症状**：登录成功后反复跳转，日志出现 `keystore: failed to parse token`，或用户能登录却没有预期角色。

依次核对独立 Cookie 名与 JWT key、callback URL、provider realm、`transform user` 的 realm 和正则转义。若回跳被生成成 HTTP，再核对入口是否传递 `X-Forwarded-Proto: https`。角色刚变更时还要刷新旧 JWT。

### <a id="zellij-black-screen"></a>Zellij 黑屏

**症状**：OAuth 已通过，浏览器进入 Zellij 后黑屏。

先检查 system-level template 是否把 `%U` 当作实例用户 UID；删掉由此生成的 `ZELLIJ_SOCKET_DIR` 覆盖。Zellij system service 的详细错误不一定进入 journal，通常位于：

```text
/tmp/zellij-<uid>/zellij-log/zellij.log
```

再核对 `/ws/control`：有效 session token 应返回 `101`，无效 token 返回 `401`。

### <a id="caddy-reload"></a>Caddy reload 与长连接

- Caddyfile 驱动的 `caddy.service` 与 Admin API 动态配置不能同时作为真源；下一次 Caddyfile reload 会覆盖只存在于 API 的改动。
- `caddy validate` 不继承 systemd 注入的环境变量。校验含 `{env.*}` 的配置时，在校验进程中提供占位值或安全加载环境文件。
- reload 可能已成功加载新配置，却因关闭旧 Admin API 或等待长连接超时，让 systemd 长时间停在 `reloading`。确认新配置已经生效后，可用 restart 解卡。
- `servers { grace_period ... }` 在实测 Caddy 2.11.2 的 Caddyfile adapter 中不被接受，不应只凭文档片段加入。
- `stream_timeout` 用于限制半死 WebSocket 的寿命；未设置时，静默断网的连接可能长期占用 copier，并阻碍旧 server drain。
