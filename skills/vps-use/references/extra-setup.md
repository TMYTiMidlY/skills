# 额外安装

> 必须先完成 [base-setup.md](base-setup.md) 再执行以下步骤。

## 配置 ssh-agent（本地机器）

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
