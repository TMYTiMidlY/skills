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

## 4. SSH RemoteForward 服务转发

把本地回环Web服务通过SSH反向隧道提供给远端回环地址。在本地对应Host中配置：

```sshconfig
Host <远程机器名>
  RemoteForward 127.0.0.1:10131 127.0.0.1:<local-web-port>
  ExitOnForwardFailure yes
```

在远端用 `curl http://127.0.0.1:10131/` 验证服务。认证方式、监听地址与可访问范围按实际Web服务设置，凭据从受限来源读取。

- 隧道依赖SSH连接，断开后自动关闭；ControlPersist可按实际平台保持连接。
- 远端10131被占用时转发失败；ExitOnForwardFailure使初次监听失败直接结束连接，避免主会话看似成功。核对 `ss -tlnp` 或选择其他已批准端口。
- 已有ControlMaster不会采用新加的转发配置，需在允许中断的窗口退出旧master并重连。
- 两端显式使用127.0.0.1可固定IPv4；localhost可能解析到IPv6，而服务仅监听IPv4。
