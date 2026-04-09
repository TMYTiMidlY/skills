# 额外安装

> 必须先完成 [base-setup.md](base-setup.md) 再执行以下步骤。

## 启用 BBR 拥塞控制

经过在 LisaHost 服务器上的测试，启用 BBR 后很可能能改善网络体验（GitHub 下载速度、iperf3 重传和丢包等）。

检查系统是否已启用 BBR：

```bash
sysctl net.ipv4.tcp_available_congestion_control
# 示例输出: net.ipv4.tcp_available_congestion_control = reno cubic
```

另一种检查方式：

```bash
sysctl net.ipv4.tcp_congestion_control
# 示例输出: net.ipv4.tcp_congestion_control = cubic
```

如果不是 `bbr`，启用它：

```bash
sudo tee -a /etc/sysctl.conf <<EOF
net.core.default_qdisc=fq
net.ipv4.tcp_congestion_control=bbr
EOF
```

刷新配置：

```bash
sudo sysctl -p
```

重启服务器后验证：

```bash
sysctl net.ipv4.tcp_congestion_control
# 预期输出: net.ipv4.tcp_congestion_control = bbr
```

## 安装 EasyTier

### 组网方案

所有公网 VPS 按下方模板配置，开启 `private_mode`，可选两种模式：
- **加入模式**：分配虚拟 IP，正常参与组网
- **仅中继模式**：`no_tun = true`，不分配虚拟 IP，为其他节点提供发现和流量转发

NAT 下的设备（PC、平板等）在 `[[peer]]` 中添加所有公网 VPS 的地址（优先 UDP，TCP 备选），通过它们加入网络后互相发现，能 P2P 就 P2P，不能就走 VPS 中继。

> 依赖 unzip，需提前安装。

```bash
wget -O /tmp/easytier.sh "https://raw.githubusercontent.com/EasyTier/EasyTier/main/script/install.sh" && sudo bash /tmp/easytier.sh install --gh-proxy https://ghfast.top/
```

> `--gh-proxy` 可选，默认使用。如果网络可直连 GitHub 可去掉。

安装后二进制在 `/opt/easytier`，配置文件目录在 `/opt/easytier/config/`。

参考配置（配置项含义见 https://easytier.cn/guide/network/configurations.html ）：

```toml
instance_name = "TiMidlY"
ipv4 = "10.144.18.x"
dhcp = false
listeners = [
    "tcp://0.0.0.0:11010",
    "udp://0.0.0.0:11010",
    "wg://0.0.0.0:11011",
    "ws://0.0.0.0:11011/",
    "wss://0.0.0.0:11012/",
]
exit_nodes = []
rpc_portal = "127.0.0.1:15888"

[network_identity]
network_name = "TiMidlY"
network_secret = "<询问用户>"

[flags]
default_protocol = "udp"
dev_name = ""
enable_encryption = true
enable_ipv6 = true
mtu = 1380
latency_first = false
enable_exit_node = false
no_tun = false
use_smoltcp = false
foreign_network_whitelist = "*"
disable_p2p = false
p2p_only = false
relay_all_peer_rpc = false
disable_tcp_hole_punching = false
disable_udp_hole_punching = false
private_mode = true
```

相对 default.conf 改动的关键参数：

- `dhcp = false` + `ipv4 = "10.144.18.x"`：关闭 DHCP，手动指定虚拟 IP，需要分配一个未使用的地址，询问用户。也可以设置 `dhcp = true` 并将 `ipv4` 写为 `10.144.18.0/24` 自动分配。
- `rpc_portal = "127.0.0.1:15888"`：管理 RPC 只监听本地，不暴露到公网。default 用 `0.0.0.0:0` 会监听所有网卡。
- `network_name` / `network_secret`：组网凭证，只有相同 name + secret 的节点才能互相发现和通信。
- `private_mode = true`：只允许相同 network_name + network_secret 的节点接入。开启后外部节点在密码验证阶段就会被拒绝，`foreign_network_whitelist` 和 `relay_all_peer_rpc` 不再生效。不开的话，白名单内的其他网络可以借用你的节点做中继。

### 启动服务与防火墙

安装完成后将配置文件写入该目录，然后以配置文件名启动服务：

```bash
systemctl start easytier@<配置文件名>
```

如果启用了 ufw，需要开放 11010 端口（TCP + UDP）：

```bash
sudo ufw status | grep -q "^Status: active" || exit 0
sudo ufw allow 11010/tcp
sudo ufw allow 11010/udp
```

### 自定义节点显示名称

EasyTier 在 peer list 中默认显示系统主机名（`hostname`）。如需自定义显示名称，通过 systemd override 设置 `ET_HOSTNAME` 环境变量：

```bash
sudo systemctl edit easytier@<配置文件名>
```

添加：

```ini
[Service]
Environment="ET_HOSTNAME=自定义名称"
```

保存后 `systemctl daemon-reload && systemctl restart easytier@<配置文件名>` 生效。

### 出口节点（Exit Node）

出口节点功能相当于搭建 VPN：让客户端的所有非虚拟网络流量通过指定的服务器出去。需要两端配合：

- **服务端**：设置 `enable_exit_node = true`，允许自己接收并转发出口流量。
- **客户端**：在 `exit_nodes` 中填入服务端的虚拟 IP（如 `exit_nodes = ["10.144.18.1"]`），访问非虚拟网络 IP 时流量会被路由到该出口节点。

此功能不影响节点发现和组网，只控制流量转发行为。

### 隐私与转发控制

三个参数配合控制外部网络（不同 network_name/secret 的节点）能否利用你的节点：

- `foreign_network_whitelist`：控制允许哪些外部网络通过此节点转发流量。`"*"` 允许所有，`""` 禁止所有，也支持通配符如 `"net1 net2*"`。
- `relay_all_peer_rpc`：当外部网络不在白名单内时，是否仍然帮它转发 RPC 包（仅用于节点发现和 P2P 建连，不转发数据流量）。
- `private_mode`：如果为 true，外部节点必须通过密码验证才能接入，否则直接拒绝连接。这是最严格的一道门。

## 安装 Caddy

### 通过 APT 安装

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg
chmod o+r /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install caddy
```

### Caddyfile 配置：两种模式

#### 域名模式（推荐）

```caddyfile
example.com {
    reverse_proxy localhost:8000
}
```

ACME 自动签 Let's Encrypt 证书，**80 端口必须从公网可达**（HTTP-01 challenge）。多域名平铺，每个 site block 独立。

#### IP 模式（无域名 / 未备案）

```caddyfile
{
    auto_https disable_redirects
    default_sni <主 IP>
}

https://<主 IP>:8000 {
    tls internal
    reverse_proxy localhost:8000
}
```

注意事项：

1. **`auto_https disable_redirects`**：Caddy 默认会为每个 https 站点在 80 端口起 HTTP→HTTPS 重定向，多端口配置下产生"不知该跳哪个端口"的歧义；`tls internal` 也不需要 80 端口做 ACME 验证，关掉省事。
2. **`default_sni`**：客户端通过 IP 直连时 SNI 为空（RFC 6066 规定 SNI 只能是 hostname），Caddy 找不到匹配 connection policy 会回 TLS alert 80，default_sni 是兜底。([caddyserver/caddy#6344](https://github.com/caddyserver/caddy/issues/6344))
3. **非标端口建议写 `https://` 前缀**：技术上不必需（带 hostname/IP 的 `host:port` 会自动开 HTTPS），但显式写 https 提高可读性、避免误读。
4. **`tls internal`** + 客户端装 Caddy local root CA，见下文。

### 安装 Caddy local root CA（tls internal 场景）

使用 Caddy 时，本机 PKI 三层证书都在 `/var/lib/caddy/.local/share/caddy/` 下，默认 lifetime（[官方文档](https://caddyserver.com/docs/caddyfile/directives/tls) / [#3427](https://github.com/caddyserver/caddy/issues/3427)）：

| 层级 | lifetime | 文件 |
|---|---|---|
| Root | 10 年 | `pki/authorities/local/root.crt` ← **客户端装这个** |
| Intermediate | 7 天 | `pki/authorities/local/intermediate.crt` |
| Leaf | 12 小时 | `certificates/local/<host>/<host>.crt` |

intermediate 和 leaf 都自动续签覆盖，装它们意味着持续重导。装 root 后整条链（含未来续签的 intermediate、新增 host 的叶子）一次性都信任；TLS 握手时 Caddy 会把 intermediate 一起发给客户端，无需单独导入。

服务端从上表 root 路径导出到家目录：

```bash
sudo cp /var/lib/caddy/.local/share/caddy/pki/authorities/local/root.crt ~/caddy-root.crt
sudo chown $USER ~/caddy-root.crt
```

`scp` 拉回客户端，按客户端 OS 导入到系统/浏览器证书库。

> **校验是不是 root**：`openssl x509 -in caddy-root.crt -noout -subject -issuer`，**Subject == Issuer** 就是自签 root。

### Caddyfile 修改流程

```bash
sudo nano /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile
sudo caddy fmt --overwrite /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

> 改 Caddyfile 用 `reload`；换二进制或环境变量用 `restart`。**失败的 reload 会让 systemd 卡在 reloading，下一次 reload 也跟着 fail**——遇到这种情况直接 `restart`。

### error_pages snippet 用法

`error-pages` 服务跑在 `localhost:4040`（安装见 [安装 error-pages](#安装-error-pages)），在 Caddyfile 里用 snippet 集中定义，再 `import` 到需要的站点：

```caddyfile
(error_pages) {
    handle_errors 4xx 5xx {
        rewrite * /{err.status_code}
        reverse_proxy localhost:4040
    }
}

example.com {
    reverse_proxy localhost:8000
    import error_pages
}
```

`handle_errors` 是 Caddy 内置的错误捕获指令，`{err.status_code}` 是 placeholder，`error-pages` 按路径返回对应错误页。snippet 名外面套小括号 `(name)`，引用时 `import name`。

### 常见坑

- **一个服务一个端口** 比合并到 443 子路径更省心，能避开 caddy-security 的 `/assets/*` 跟后端 `/assets/*` 类静态资源路径的冲突。
- **端口被本机进程占用**（典型场景：Docker 在 `127.0.0.1:port`）给该 site 显式 `bind <eth0 ip> <tun0 ip>`，而不是默认 `0.0.0.0`，否则 Caddy 整个 reload 因 `address already in use` 失败。
- **`caddy validate` 在 sudo shell 下 env placeholder 展开失败**：跑 validate 前 `export` 占位字符串即可，值随便填，validate 只检查能否解析。
- **公网端口要在 Aliyun/腾讯云安全组放行**：本机监听 + 直连内网 IP 都能通，只有走公网回不来 → 一定是云平台安全组没开。云盾还会对未备案的 80/443 主动拦截。

### 安装 caddy-security 扩展

从 [Caddy Download Page](https://caddyserver.com/download) 下载含 caddy-security 扩展的可执行文件（勾选 `github.com/greenpau/caddy-security`），然后按[官方文档](https://caddyserver.com/docs/build#package-support-files-for-custom-builds-for-debianubunturaspbian)替换系统自带的 caddy：

```bash
sudo dpkg-divert --divert /usr/bin/caddy.default --rename /usr/bin/caddy
sudo mv ./caddy /usr/bin/caddy.custom
sudo update-alternatives --install /usr/bin/caddy caddy /usr/bin/caddy.default 10
sudo update-alternatives --install /usr/bin/caddy caddy /usr/bin/caddy.custom 50
sudo systemctl restart caddy
```

- `dpkg-divert`：将原始 `/usr/bin/caddy` 移至 `/usr/bin/caddy.default`，防止 APT 升级时覆盖自定义二进制。
- `update-alternatives`：通过优先级管理多版本，custom（50）优先于 default（10）。以后可用 `update-alternatives --config caddy` 切换版本。

官方完整示例：[authcrunch GitHub OAuth Caddyfile](https://github.com/authcrunch/authcrunch.github.io/blob/main/assets/conf/oauth/github/Caddyfile)。

#### Cookie scoping 机制（理解配置的前提）

caddy-security 用 cookie 在浏览器和 portal 之间携带 JWT。Cookie 作用域由 `Domain` 属性决定：

| `Domain` 设置 | 浏览器行为 |
|---|---|
| **不设** | host-only，只发回设它的精确 host，子域名拿不到 |
| `Domain=example.com` | 发回给 `example.com` 及所有子域名 |

**关键反直觉点：cookie 不区分端口**（RFC 6265 明确不把端口算进 scope）。`host:443` 设的 host-only cookie，浏览器**也会**发到 `host:8080`、`host:9220`。

由此 caddy-security 的 `cookie domain` 在两种模式下行为相反：

- **域名模式必写** `cookie domain example.com`：否则子域名收不到 cookie，登录后访问 `app.example.com` 拿不到 JWT，死循环。
- **IP 模式必须不写**：RFC 6265 不允许 `Domain=<IP>`。host-only + 忽略端口的特性刚好让同一 IP 的所有端口共享 cookie。

由此 **IP 访问的认证体系和域名访问的认证体系彼此独立**：cookie scope 互不相通（域名 cookie 进不到 IP host，反之亦然），且 GitHub OAuth App 的 callback URL 是固定的——所以每个体系各用一套独立的 GitHub OAuth App，不要试图跨复用。

#### Caddyfile 模板：域名模式

```caddyfile
{
    order authenticate before respond
    order authorize before basicauth

    security {
        oauth identity provider github {env.GITHUB_CLIENT_ID} {env.GITHUB_CLIENT_SECRET}

        authentication portal myportal {
            crypto default token lifetime 604800
            cookie lifetime 604800
            cookie domain example.com
            crypto key sign-verify {env.JWT_SHARED_KEY}
            enable identity provider github
            trust login redirect uri domain suffix example.com path prefix /

            transform user {
                match realm github
                regex match sub "github.com/(yourname|otheruser)"
                action add role authp/admin
            }
        }

        authorization policy admin_policy {
            set auth url https://auth.example.com/login
            crypto key verify {env.JWT_SHARED_KEY}
            allow roles authp/admin
        }
    }
}

auth.example.com {
    handle /forbidden {
        error "Unauthorized" 401
    }
    authenticate with myportal
}

app.example.com {
    authorize with admin_policy
    reverse_proxy localhost:8000
}
```

#### IP 模式差异片段

只列出和域名模式不一样的部分（global options 的 `auto_https disable_redirects` / `default_sni` / `tls internal` 见 [IP 模式](#ip-模式无域名--未备案)）：

```caddyfile
authentication portal myportal {
    ...
    # 不要写 cookie domain（RFC 6265 不允许 Domain=IP）
    trust login redirect uri domain regex ^<主 IP>(:[0-9]+)?$ path prefix /
    ...
}

authorization policy admin_policy {
    set auth url https://<主 IP>/login
    ...
}

https://<主 IP> {
    tls internal
    handle /forbidden {
        error "Unauthorized" 401
    }
    authenticate with myportal
}

https://<主 IP>:8080 {
    tls internal
    authorize with admin_policy
    reverse_proxy localhost:8000
}
```

#### 概念速查

- **`crypto default token lifetime` / `cookie lifetime`**：分别是 JWT exp 和浏览器 cookie Max-Age，**必须设成一样**。默认 token 是 900 秒（15 分钟），太短，登录后很快过期。
- **`crypto key sign-verify <key>`**：JWT 签名密钥。**不显式配置时插件每次启动生成临时新密钥，重启等于全员强制重登**；用 `{env.JWT_SHARED_KEY}` 绑定固定 env 才能跨重启保留 token。authorization policy 里用 `crypto key verify` 引用同一个 key 只验签。详见 [AuthCrunch auth-cookie 文档](https://docs.authcrunch.com/docs/authenticate/auth-cookie)。
- **`transform user` + `allow roles`**：前者给登录用户打角色（`authp/` 只是命名约定，字符串随便起），后者 `allow roles A B` 是 **OR**——任一角色满足即放行。
- **`trust login redirect uri`**：白名单"哪些 redirect_url 允许写入回跳 cookie"。**IP 模式关键坑**：Go 的 `url.Host` 把端口包含在内，匹配非标端口必须写 `(:[0-9]+)?` 让正则吃掉端口，否则登录后回不到原页面。不配置 = 全部静默丢弃。([caddy-security#455](https://github.com/greenpau/caddy-security/issues/455))

#### 配置 OAuth 环境变量

```bash
sudo systemctl edit caddy
```

添加以下内容：

```ini
[Service]
Environment="GITHUB_CLIENT_ID=你的ID"
Environment="GITHUB_CLIENT_SECRET=你的密钥"
Environment="JWT_SHARED_KEY=你的JWT密钥"
```

> `JWT_SHARED_KEY` 填一串足够长的随机字符串即可，为什么必须显式配置见前面概念速查。

然后重载并重启：

```bash
sudo systemctl daemon-reload
sudo systemctl restart caddy
# 验证变量是否加载成功
sudo systemctl show caddy --property=Environment
```

## 安装 error-pages

自定义错误页面服务，用于反向代理后端不可用时展示友好的错误页。

```bash
wget https://github.com/tarampampam/error-pages/releases/download/v3.8.1/error-pages-linux-amd64
sudo mv ./error-pages-linux-amd64 /usr/local/bin/error-pages
sudo chmod 755 /usr/local/bin/error-pages
sudo chown root:root /usr/local/bin/error-pages
```

创建 `/etc/systemd/system/error-pages.service`：

```ini
[Unit]
Description=Error Pages Service
After=network.target
Documentation=https://github.com/tarampampam/error-pages

[Service]
Type=simple
User=nobody
Group=nogroup
ExecStart=/usr/local/bin/error-pages serve --template-name connection --port 4040 --listen 127.0.0.1 --send-same-http-code
Restart=always
RestartSec=5s
StandardOutput=journal
StandardError=journal
SyslogIdentifier=error-pages

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now error-pages
```

## 配置 SSH 密钥 passphrase（本地机器）

检查是否已有密钥：

```bash
ls ~/.ssh/id_*
```

- **如果不存在**：提示用户生成密钥（交互式，需要用户输入 passphrase）：

  ```bash
  ssh-keygen -t ed25519 -C "<comment>"
  ```

  > `-C` 是密钥注释，用于区分不同密钥，填设备名、邮箱、用途等均可。

- **如果已存在但没有 passphrase**：提示用户为已有密钥添加 passphrase（将 `<key_path>` 替换为实际私钥路径）：

  ```bash
  ssh-keygen -p -f <key_path>
  ```

> 以上命令都需要交互式执行，agent 无法代替用户输入密码，应提示用户手动运行。

## 配置 ssh-agent（本地机器）

> **Windows 用户**：参考 [Auto-launching ssh-agent on Git for Windows](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/working-with-ssh-key-passphrases#auto-launching-ssh-agent-on-git-for-windows)，以下步骤适用于 Linux/WSL。

ssh-agent 由 systemd 用户服务管理，密钥缓存在 agent 进程内存中。**agent 的生命周期与用户登录绑定**——只要不注销用户或重启机器，已加载的密钥一直可用，不受终端会话关闭影响。

### 创建 systemd 服务

创建 `~/.config/systemd/user/ssh-agent.service`：

```ini
[Unit]
Description=SSH key agent

[Service]
Type=simple
Environment=SSH_AUTH_SOCK=%t/ssh-agent.socket
ExecStart=/usr/bin/ssh-agent -D -a $SSH_AUTH_SOCK

[Install]
WantedBy=default.target
```

### 启用服务

```bash
systemctl --user enable --now ssh-agent
```

### 配置 Shell 环境

在 `~/.bashrc` 中添加：

```bash
# SSH Agent
export SSH_AUTH_SOCK=/run/user/$(id -u)/ssh-agent.socket
```

> **WSL 注意**：WSL 环境下可能还需要设置 `XDG_RUNTIME_DIR`，因为 WSL 不一定自动创建。

### 配置 SSH 客户端

在 `~/.ssh/config` 的 `Host *` 下添加：

```
Host *
    AddKeysToAgent yes
    IdentityFile ~/.ssh/id_ed25519
```

- `AddKeysToAgent yes`：首次连接输入 passphrase 后自动缓存到 agent
- `IdentityFile`：指定默认使用的密钥
