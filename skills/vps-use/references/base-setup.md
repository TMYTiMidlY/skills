# VPS 初次配置指南

新购 VPS 后以 root 登录，按以下顺序配置。

## 1. 设置防火墙

```bash
sudo ufw allow 22/tcp        # SSH
sudo ufw allow 80/tcp        # HTTP
sudo ufw allow 443/tcp       # HTTPS
sudo ufw allow in on lo      # 允许 loopback（本地 SSH 转发等需要）
sudo ufw enable
```

## 2. 创建普通用户

```bash
adduser timidly               # 按提示设置密码
usermod -aG sudo timidly
```

## 3. 部署 SSH 密钥

用新创建的普通用户登录：

```bash
ssh timidly@<服务器地址>
mkdir -p ~/.ssh
echo "ssh-ed25519 AAA..." > ~/.ssh/authorized_keys
chmod 700 ~/.ssh
chmod 600 ~/.ssh/authorized_keys
```

> 将 `ssh-ed25519 AAA...` 替换为你的实际公钥，可通过 `cat ~/.ssh/id_ed25519.pub` 查看。

## 4. 加固 SSH 服务端配置

### 4.1 检查 Include 语句

```bash
grep -q "^Include /etc/ssh/sshd_config.d/\*.conf" /etc/ssh/sshd_config || { echo "❌ 缺失 Include 语句，操作取消"; exit 1; }
```

### 4.2 写入配置

```bash
sudo tee /etc/ssh/sshd_config.d/00-custom.conf > /dev/null <<EOF
Port 22
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
EOF
```

> **可选**：如果需要通过远程端口转发将本地服务暴露到公网（`ssh -R`），在配置中加入 `GatewayPorts yes`。默认不开启。

### 4.3 语法检查并重启服务

```bash
sudo sshd -t && sudo sshd -T | grep "permitrootlogin" && sudo systemctl restart ssh && echo "✅ 配置已应用"
```

## 5. 配置 ssh-agent（本地机器）

ssh-agent 由 systemd 用户服务管理，密钥缓存在 agent 进程内存中。**agent 的生命周期与用户登录绑定**——只要不注销用户或重启机器，已加载的密钥一直可用，不受终端会话关闭影响。

### 5.1 创建 systemd 服务

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

### 5.2 启用服务

```bash
systemctl --user enable --now ssh-agent
```

### 5.3 配置 Shell 环境

在 `~/.bashrc` 中添加：

```bash
# SSH Agent
export SSH_AUTH_SOCK=/run/user/$(id -u)/ssh-agent.socket
```

> **WSL 注意**：WSL 环境下可能还需要设置 `XDG_RUNTIME_DIR`，因为 WSL 不一定自动创建。

### 5.4 配置 SSH 客户端

在 `~/.ssh/config` 的 `Host *` 下添加：

```
Host *
    AddKeysToAgent yes
    IdentityFile ~/.ssh/id_ed25519
```

- `AddKeysToAgent yes`：首次连接输入 passphrase 后自动缓存到 agent
- `IdentityFile`：指定默认使用的密钥
