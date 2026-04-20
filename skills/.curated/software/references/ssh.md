# SSH 使用

## SSH 密钥 passphrase 与 ssh-agent

检查密钥：

```bash
ls ~/.ssh/id_*
```

- 不存在：`ssh-keygen -t ed25519 -C "<comment>"`，`-C` 填设备名、邮箱或用途。
- 已存在但无 passphrase：`ssh-keygen -p -f <key_path>`。

以上命令都需要交互式执行，agent 无法代替用户输入密码，应提示用户手动运行。

Windows 用户参考 [Auto-launching ssh-agent on Git for Windows](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/working-with-ssh-key-passphrases#auto-launching-ssh-agent-on-git-for-windows)。Linux/WSL 下 ssh-agent 可由 systemd 用户服务管理，密钥缓存在 agent 进程内存中，生命周期与用户登录绑定，不注销、不重启就一直可用。

### Windows: Git Bash 与 PowerShell 的 ssh-agent 差异

Windows 上最容易踩坑的是 Git Bash 和 PowerShell 可能调用不同的 `ssh.exe`，因此也可能连到不同的 agent。

- Git Bash 常见写法是 `eval "$(ssh-agent -s)"`，它会启动/复用 Git for Windows/MSYS 环境里的 `ssh-agent`，并向当前 shell 注入 `SSH_AUTH_SOCK`、`SSH_AGENT_PID` 两个环境变量。Git Bash 里的 `ssh-add` 和 Git for Windows 自带 `ssh.exe` 依赖这些变量找到 agent。
- PowerShell 使用 Windows OpenSSH 时通常不需要设置 `SSH_AUTH_SOCK`、`SSH_AGENT_PID`。启动 Windows 的 `ssh-agent` 服务后，`C:\Windows\System32\OpenSSH\ssh.exe` 会通过 Windows OpenSSH 的 agent 通道访问已缓存的 key。
- Git for Windows 自带 `usr/bin/ssh.exe`、`usr/bin/ssh-agent.exe`、`usr/bin/ssh-add.exe`；`eval "$(ssh-agent -s)"` 通常启动的是这套 MSYS/Git Bash 环境里的 agent 进程，并通过注入的环境变量让同一环境里的 `ssh` 找到它。若希望 Git 明确使用 Windows OpenSSH service，最直接的做法是显式设置：

```powershell
git config --global core.sshCommand "C:/Windows/System32/OpenSSH/ssh.exe"
```

这能让 PowerShell、Git，以及 Git Bash 中的 Git 命令尽量使用同一套 Windows OpenSSH 行为，避免 `ssh` 不问 passphrase、`git pull` 却反复询问的情况。

不要把 Git Bash 里的 `SSH_AUTH_SOCK`、`SSH_AGENT_PID` 直接搬到 PowerShell 里作为通用解法。PowerShell 当然可以设置环境变量，但 Windows OpenSSH 通常不靠这两个变量定位 agent；设置错了反而容易让不同 SSH 客户端混用失败。

Windows PowerShell 下也不要依赖 OpenSSH 的 `ControlMaster`/`ControlPath`/`ControlPersist` 做连接复用。该机制主要面向 Unix socket 场景，在 Windows OpenSSH/PowerShell 组合中通常不可用或不可靠；需要免重复输入 passphrase 时优先使用 `ssh-agent`。

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

启用并在 shell 中固定 socket：

```bash
systemctl --user enable --now ssh-agent
echo 'export SSH_AUTH_SOCK=/run/user/$(id -u)/ssh-agent.socket' >> ~/.bashrc
```

WSL 环境下可能还需要设置 `XDG_RUNTIME_DIR`。

在 `~/.ssh/config` 的 `Host *` 下确保有：

```sshconfig
Host *
    AddKeysToAgent yes
    IdentityFile ~/.ssh/id_ed25519
```

`AddKeysToAgent yes` 表示首次连接输入 passphrase 后自动缓存到 agent；`IdentityFile` 指定默认使用的密钥。

## SSH RemoteForward 代理转发

把本地代理端口通过 SSH 反向隧道提供给远程机器。先在本地 `~/.ssh/config` 对应 Host 下添加：

```sshconfig
Host <远程机器名>
  RemoteForward 127.0.0.1:10131 127.0.0.1:7890
```

在远程机器的 `~/.bashrc` 中添加：

```bash
export http_proxy=http://<用户名>:<密码>@127.0.0.1:10131
export https_proxy=http://<用户名>:<密码>@127.0.0.1:10131
```

如果本地代理不需要认证，去掉 `<用户名>:<密码>@`。认证凭据需要和本地代理配置一致。

注意事项：

- 隧道依赖 SSH 连接；SSH 断开后隧道自动关闭。配合 `ControlPersist` 可以保持连接。
- 如果远程机器上 10131 已被占用，SSH 会报 `bind: Address already in use`，转发不生效但连接本身可能仍然建立。换端口，或检查 `ss -tlnp | grep 10131`。
- 修改 SSH config 添加 RemoteForward 后，已有 ControlMaster 连接不含新配置，需要先执行 `ssh -O exit <远程机器名>`，重新连接才会生效。
- 两边都显式写 `127.0.0.1` 更清晰；本地端写 `127.0.0.1` 比 `localhost` 可靠，可避免 `localhost` 解析到 IPv6 `::1` 而代理只听 IPv4。
