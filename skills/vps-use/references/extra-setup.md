# 额外安装

> 必须先完成 [base-setup.md](base-setup.md) 再执行以下步骤。

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

### 配置 Caddyfile

```bash
sudo nano /etc/caddy/Caddyfile
```

修改域名，配置反向代理等，改完后：

```bash
sudo systemctl reload caddy
```

> **注意**：修改 Caddyfile 用 `reload`，其他情况（如替换二进制、改环境变量）用 `restart`。

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

GitHub OAuth 的 Caddyfile 配置参考 [authcrunch 示例](https://github.com/authcrunch/authcrunch.github.io/blob/main/assets/conf/oauth/github/Caddyfile)。

### 配置 OAuth 环境变量

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

> `JWT_SHARED_KEY` 是对称密钥，填入任意足够长的随机字符串即可。不配置时插件会自动生成密钥对（适合单机），但每次重启会变化，旧 token 失效；多实例部署或想避免重启后重新登录则需要手动配置。参考 [AuthCrunch 文档](https://docs.authcrunch.com/docs/authenticate/auth-cookie)。

然后重载并重启：

```bash
sudo systemctl daemon-reload
sudo systemctl restart caddy
# 验证变量是否加载成功
sudo systemctl show caddy --property=Environment
```
