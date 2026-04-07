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

## 安装 error-pages

自定义错误页面服务，用于反向代理后端不可用时展示友好的错误页。

```bash
wget https://github.com/tarampampam/error-pages/releases/download/v3.8.1/error-pages-linux-amd64
sudo mv ./error-pages-linux-amd64 /usr/local/bin/error-pages
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

从 [Caddy Download API](https://caddyserver.com/api/download?os=linux&arch=amd64&p=github.com%2Fgreenpau%2Fcaddy-security&idempotency=2974294453198) 下载含 caddy-security 扩展的可执行文件，替换原有 caddy：

```bash
sudo chmod 755 /usr/bin/caddy
sudo chown root:root /usr/bin/caddy
```

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
