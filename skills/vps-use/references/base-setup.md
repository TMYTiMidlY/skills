# VPS 初次配置指南

新购 VPS 后以 root 登录，按以下顺序配置。

## 1. 设置防火墙

> 如果用户打算完全依赖云服务商的安全组功能，可跳过 ufw 配置。

```bash
sudo ufw allow 22/tcp        # SSH
sudo ufw allow 80/tcp        # HTTP
sudo ufw allow 443/tcp       # HTTPS
sudo ufw allow in on lo      # 允许 loopback（本地 SSH 转发等需要）
sudo ufw enable
```

如需移除规则：

```bash
sudo ufw delete allow 80/tcp
sudo ufw delete allow 443/tcp
```

## 2. 创建普通用户

可以先非交互创建用户，最后再提示用户设置密码（sudo 需要）。加固完成前保持 root 登录，避免切换到 <USERNAME> 导致 sudo 无法非交互执行。

```bash
useradd -m <USERNAME>
# Debian 系用 sudo 组，RHEL 系用 wheel 组
usermod -aG sudo <USERNAME>   # Debian/Ubuntu
usermod -aG wheel <USERNAME>  # RHEL/CentOS
```

所有步骤完成后，提示用户手动设置密码：

```bash
passwd <USERNAME>
```

## 3. 部署 SSH 密钥

用新创建的普通用户登录：

```bash
ssh <USERNAME>@<服务器地址>
mkdir -p ~/.ssh
echo "ssh-ed25519 AAA..." > ~/.ssh/authorized_keys
chmod 700 ~/.ssh
chmod 600 ~/.ssh/authorized_keys
```

> 将 `ssh-ed25519 AAA...` 替换为你的实际公钥，可通过 `cat ~/.ssh/id_ed25519.pub` 查看。

如果已经在 root 账户配置过 `authorized_keys`，可以直接复制：

```bash
mkdir -p /home/<USERNAME>/.ssh
cp /root/.ssh/authorized_keys /home/<USERNAME>/.ssh/
chown -R <USERNAME>:<USERNAME> /home/<USERNAME>/.ssh
chmod 700 /home/<USERNAME>/.ssh
chmod 600 /home/<USERNAME>/.ssh/authorized_keys
```

## 4. 加固 SSH 服务端配置

### 4.1 检查 Include 语句

```bash
grep -q "^Include /etc/ssh/sshd_config.d/\*.conf" /etc/ssh/sshd_config && echo "OK" || echo "MISSING"
```

> 部分镜像没有 `sshd_config.d/` 目录也没有 `Include` 语句。此时不要创建 `.d/00-custom.conf`，直接编辑 `/etc/ssh/sshd_config`（追加或替换对应行），然后跳到 4.3 做语法检查。

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

> 上面用 `sudo tee` 写入的文件默认已是 root 所有、644 权限。如果用其他方式写入，需要手动确保权限正确：
>
> ```bash
> sudo chown root:root /etc/ssh/sshd_config.d/00-custom.conf
> sudo chmod 644 /etc/ssh/sshd_config.d/00-custom.conf
> ```

### 4.3 语法检查并重启服务

```bash
sudo sshd -t && sudo sshd -T | grep -iE "PermitRootLogin|PasswordAuthentication" && sudo systemctl restart ssh && echo "✅ 配置已应用"
```

