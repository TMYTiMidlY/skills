---
name: vps-maintenance
description: 新服务器/VPS 初始化、服务器侧安全配置、网络质量检测、BBR/EasyTier/Caddy/caddy-security/error-pages 等服务安装配置时使用；远程执行规范由 remote 提供。
---

# VPS Maintenance

## 使用范围

当用户要配置新服务器或 VPS、做服务器侧安全配置、安装或调整服务器上的基础服务时使用本 skill。实际远程执行命令仍遵循 `remote` 的 SSH 操作规范。

如果用户没有明确指定任务类型，先确认是：

- **新服务器**：新购服务器的防火墙、用户、SSH 密钥部署与 SSH 服务端配置。
- **服务安装**：按需配置 BBR、EasyTier、Caddy、caddy-security、error-pages。
- **质量检测**：网络、IP、历史服务器质量评估。

## 新服务器

新购服务器后以 root 登录，按以下顺序配置。

### 设置防火墙

如果用户打算完全依赖云服务商的安全组功能，可跳过 ufw 配置。

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

### 创建普通用户

可以先非交互创建用户，最后再提示用户设置密码（sudo 需要）。加固完成前保持 root 登录，避免切换到 `<USERNAME>` 导致 sudo 无法非交互执行。

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

### 部署 SSH 密钥

用新创建的普通用户登录：

```bash
ssh <USERNAME>@<服务器地址>
mkdir -p ~/.ssh
echo "ssh-ed25519 AAA..." > ~/.ssh/authorized_keys
chmod 700 ~/.ssh
chmod 600 ~/.ssh/authorized_keys
```

将 `ssh-ed25519 AAA...` 替换为实际公钥，可通过 `cat ~/.ssh/id_ed25519.pub` 查看。

如果已经在 root 账户配置过 `authorized_keys`，可以直接复制：

```bash
mkdir -p /home/<USERNAME>/.ssh
cp /root/.ssh/authorized_keys /home/<USERNAME>/.ssh/
chown -R <USERNAME>:<USERNAME> /home/<USERNAME>/.ssh
chmod 700 /home/<USERNAME>/.ssh
chmod 600 /home/<USERNAME>/.ssh/authorized_keys
```

### 加固 SSH 服务端配置

先检查 Include 语句：

```bash
grep -q "^Include /etc/ssh/sshd_config.d/\*.conf" /etc/ssh/sshd_config && echo "OK" || echo "MISSING"
```

部分镜像没有 `sshd_config.d/` 目录也没有 `Include` 语句。此时不要创建 `.d/00-custom.conf`，直接编辑 `/etc/ssh/sshd_config`（追加或替换对应行），然后做语法检查。

如果 Include 可用，写入配置：

```bash
sudo tee /etc/ssh/sshd_config.d/00-custom.conf > /dev/null <<EOF
Port 22
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
EOF
```

可选：如果需要通过远程端口转发将本地服务暴露到公网（`ssh -R`），在配置中加入 `GatewayPorts yes`。默认不开启。

上面用 `sudo tee` 写入的文件默认已是 root 所有、644 权限。如果用其他方式写入，需要手动确保权限正确：

```bash
sudo chown root:root /etc/ssh/sshd_config.d/00-custom.conf
sudo chmod 644 /etc/ssh/sshd_config.d/00-custom.conf
```

语法检查并重启服务：

```bash
sudo sshd -t && sudo sshd -T | grep -iE "PermitRootLogin|PasswordAuthentication" && sudo systemctl restart ssh && echo "配置已应用"
```

## 常用服务配置

以下内容无强依赖，除非文档写明前置条件，否则按需配置。

### BBR 拥塞控制

在 LisaHost 服务器上的测试显示，启用 BBR 后可能改善网络体验（GitHub 下载速度、iperf3 重传和丢包等）。

检查：

```bash
sysctl net.ipv4.tcp_available_congestion_control
sysctl net.ipv4.tcp_congestion_control
```

如果不是 `bbr`，写入配置并刷新：

```bash
sudo tee -a /etc/sysctl.conf <<EOF
net.core.default_qdisc=fq
net.ipv4.tcp_congestion_control=bbr
EOF
sudo sysctl -p
```

重启后再验证 `sysctl net.ipv4.tcp_congestion_control`。

### EasyTier

虚拟组网、P2P/中继、出口节点、隐私与转发控制见 [references/easytier.md](references/easytier.md)。

### Caddy 与 caddy-security

Caddy 反向代理、域名/IP 模式、local root CA、Caddyfile 修改流程、caddy-security GitHub OAuth、cookie scope、环境变量见 [references/caddy.md](references/caddy.md)。

尤其是修改 Caddyfile、EasyTier、SSH 转发、systemd 单元、防火墙规则时，不要凭记忆改，先读对应 reference。

### 代理服务

VLESS/3x-ui/Xray 既有节点、Hysteria2 备用节点、Caddy 证书复用与 UDP 端口放行经验见 [references/proxy.md](references/proxy.md)。

### error-pages

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

多用户共享服务、systemd 模板单元与按 UID 分配端口见 `software` skill。

## WebDAV + Markdeep viewer 服务端

**本节只覆盖服务端配置**。客户端上传命令、分享链接用法、Markdeep 写作惯例（引用 vs 脚注、GFM 兼容性、研报模板）见 `software` skill 的 `doc-share` reference。

Caddy 本身（安装、域名/IP 模式、caddy-security 扩展、error-pages）以及无额外认证的 capability URL 文档私链分享（caddy-webdav 扩展安装 + site block + viewer 挂载 + 凭据 + 撤销）全部见 [references/caddy.md](references/caddy.md)；私链分享那节在文件末尾的「无额外认证的文档分享私链（WebDAV + Markdeep viewer）」。viewer 模板在 [assets/md-viewer.html](assets/md-viewer.html)。

## 质量检测

网络与 IP 质量评估、历史服务器配置价格对比见 [references/quality-check.md](references/quality-check.md)。

覆盖范围：

- 带宽测试：iperf3。
- 延迟测试：mtr。
- IP/DNS/WebRTC 泄漏检测。
- IP 风险评估、多节点延迟。
- 大陆云服务器未备案封锁、公网带宽限速丢包。
- DigitalOcean、RackNerd、LisaHost、EdgeNAT、Alibaba Cloud 历史记录。

## 用户名规则

参考文档中的 `<USERNAME>` 替换为实际用户名：

- 用户明确指定时使用指定用户名。
- 用户没有指定时，先询问用户要使用哪个用户名。

## 重要原则

严格按照参考文档中写明的步骤执行。如果文档中没有写某个操作的具体流程，先询问用户意见，不要自行发挥。
