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

## 非交互环境 `Server accepts key` 却 `Permission denied`：私钥有 passphrase，但没有已解锁的 agent

### 症状

在**非交互 SSH**（CI / `bash -c` / 各类 agent 远程执行，不 source `~/.bashrc`）里 `git push` / `git ls-remote` 到一台 Forgejo（或裸 git-over-sshd），始终 `git@HOST: Permission denied (publickey,...)`。但公钥明明加对了——服务端（如 Forgejo web 的 SSH keys 页）能看到这把 key、且"上次使用"为空（＝从没认证成功过），而且**人在交互终端 `ssh git@HOST` 是成功的**。

### 排查关键转折

1. **先排除网络**：一旦出现 `Permission denied`（而不是 `Connection timed out`），就说明 TCP+SSH 握手已成功，是**认证**问题、不是网络。
2. **`Server accepts key` 是关键迷雾**：`ssh -vv -o IdentitiesOnly=yes -i ~/.ssh/id_ed25519 git@HOST true` 看握手，关键几行：
   ```
   Offering public key: .../id_ed25519 ED25519 SHA256:xxxx
   Server accepts key:  .../id_ed25519 ED25519 SHA256:xxxx   ← 服务器认这把公钥
   ...
   No more authentication methods to try.
   Permission denied (publickey).
   ```
   `Server accepts key` 证明**公钥确实在 authorized_keys 里** → 问题转到客户端**私钥签名**这一步。
3. **判断私钥是不是加密的**（不暴露私钥内容）：`ssh-keygen -y -f ~/.ssh/id_ed25519 -P ""` → `Load key ...: incorrect passphrase supplied to decrypt private key`，说明私钥**带 passphrase**。再 `ssh-add -l` → `Could not open a connection to your authentication agent`（当前环境没 agent）。

### 根因

私钥有 passphrase；非交互环境（`BatchMode` / `bash -c`，`SSH_AUTH_SOCK` 为空、又无法交互输 passphrase）拿不到一个已解锁该私钥的 ssh-agent。公钥不需解密所以能"亮出来"让服务器回 `Server accepts key`，但真正用私钥**签名**时无法解密 → 失败。人在自己终端能连，是因为那个交互 session 里有解锁好的 agent。**`Server accepts key`（公钥预检通过）≠ 认证成功**，极具迷惑性。

### 解决

宿主上通常已有一个**固定路径的常驻 ssh-agent**（如上面那个 systemd user agent），用户登录时早已 `ssh-add` 解锁。直接复用它，不必去 passphrase、也不必把 passphrase 交给 agent / 对话：

```bash
ps -u "$(id -u)" -o pid,cmd | grep [s]sh-agent
# /usr/bin/ssh-agent -D -a /run/user/1000/ssh-agent.socket   ← 固定 socket

export SSH_AUTH_SOCK=/run/user/1000/ssh-agent.socket
ssh-add -l          # 确认里面有那把解锁的 key
git push ...        # 用它认证，passphrase 全程不经过 agent / 对话
```

### 教训

- **`Server accepts key` + `Permission denied` 的组合 = 公钥没问题、私钥签名出了问题**。别再反复查 authorized_keys / 重加公钥；往 passphrase、agent、私钥文件不可用方向查。
- **非交互 SSH（`BatchMode` / CI）默认 `SSH_AUTH_SOCK` 为空、不读 `.bashrc`**。找可复用 agent 别只 `ls /tmp/ssh-*`，要 `ps … | grep ssh-agent` 看有没有 `-a <固定socket>` 的常驻 agent（systemd user 的在 `/run/user/<UID>/ssh-agent.socket`），`export` 它即可白嫖已解锁的 key。
- 判断私钥是否加密：`ssh-keygen -y -f <key> -P ""`（成功输出公钥＝无 passphrase；报 `incorrect passphrase`＝有），不泄漏私钥材料。
- `git ls-remote <url>` 是"网络+认证+仓库存在"三合一的最快只读探针，改 remote / push 前先用它探。

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

## 主机密钥校验：known_hosts、CheckHostIP 与不同 SSH 实现的差异

SSH 连接时验证的是服务器的**主机密钥**（host key），不是 IP，也不是域名。`known_hosts` 记录"某主机名 / IP → 哪把 host key"。只有服务器重装、换了密钥才算"key 变了"；**只换 IP、host key 不变，从密码学角度还是同一台机器**。

不同 SSH 实现对"IP"的态度不一样，这会造成同一台主机用一个客户端连得上、换一个客户端却报错：

- **OpenSSH 默认 `CheckHostIP no`**（`man ssh_config`：默认不检查 IP；这是 OpenSSH 8.5 改的默认值，未逐版核证）。它**只按连接用的主机名**去 `known_hosts` 找 key 比对，完全不看 IP。后果：服务器 IP 变了（换 VPS、DNS 改解析），只要 host key 没变、主机名条目命中，OpenSSH 一声不吭就放行；副作用是它**从不写 IP→key 条目**，`known_hosts` 里往往只有主机名的明文条目。
- **纯第三方 SSH 库**（如 [asyncssh](https://github.com/ronf/asyncssh)，纯 Python 实现，被一些 MCP / 自动化工具当底层引擎）没有 `CheckHostIP no` 这种放宽，校验时**把连接解析到的 IP 也纳入 `known_hosts` 匹配**（≈ `CheckHostIP yes` 的行为）。

**典型症状**：同一台主机，`ssh <host>`（OpenSSH）正常，但走 asyncssh 之类的客户端报 `Host key is not trusted for host <host>`。**几乎总是**：主机 host key 没变、但解析 IP 变了，而 `known_hosts` 里只有主机名的明文条目、缺新 IP 的条目——不是真的 key 被篡改。

诊断（确认"是 IP 变了"而非"key 变了"）：

```bash
# 存的 key 和服务器实时 key 是否一致（一致 = 不是 key 变了）
diff <(ssh-keygen -F <host> | awk '/ssh-ed25519/{print $3}') \
     <(ssh-keyscan -t ed25519 <host> 2>/dev/null | awk '{print $3}')
ssh-keygen -F <新IP>     # 输出为空 = known_hosts 缺这个 IP 的条目
```

修复——补上"主机名 + IP"的条目（`-H` 顺带哈希，避免明文主机名/IP 落盘）：

```bash
ssh-keyscan -H <host> <新IP> >> ~/.ssh/known_hosts
```

追加不删旧条目，对 OpenSSH（只看主机名）无影响，同时补齐检查 IP 的客户端所需的 IP→key 映射。

## ControlMaster 连接复用

裸 `ssh` / `scp` 每次调用都新建 TCP 并重新认证（百毫秒级开销）。`ControlMaster` 让多次 ssh 复用同一条已认证的**主连接**（经一个 Unix domain socket），后续调用只开 channel，省掉重复握手；`ControlPersist` 让主连接在空闲后再保留一段时间。

在 `~/.ssh/config` 的 `Host *` 下：

```sshconfig
Host *
    ControlMaster auto
    ControlPath ~/.ssh/sockets/%r@%h-%p
    ControlPersist 10m
```

- **Windows OpenSSH 不支持** `ControlMaster`（依赖 Unix domain socket，Windows 默认编译不带），复用不可靠；Win 上免重复输 passphrase 优先靠 `ssh-agent`（见上文）。
- 改了 config（如新增 `RemoteForward`）后，**已存在的主连接不含新配置**，需 `ssh -O exit <host>` 关掉主连接、重连才生效。

## 裸 ssh / scp：跑命令、交互式 sudo、编辑远端文件

没有 hash 校验的远端编辑工具（如 portal MCP）时，纯 OpenSSH 也能干活，但有几个点要注意：

- **`SSH_AUTH_SOCK` 可能缺失**：非交互 / 非登录 shell 不一定 source 过 `~/.bashrc`，agent 起的 shell 里 ssh-agent 的 socket 变量可能没设。先确保它指向 agent，例如 `export SSH_AUTH_SOCK=/run/user/$(id -u)/ssh-agent.socket`。
- **跑一次性命令**：`ssh <host> "<command>"`。
- **交互式 sudo 要 `ssh -t`**：`sudo` 从 TTY 读密码，普通 `ssh <host> "sudo ..."` 没分配 TTY，sudo 读不到输入（或直接报错）。用 `ssh -t <host> "sudo ..."`（`-t` 强制分配 TTY）。多步 sudo 操作合进一个脚本，`scp` 到远端 `/tmp/`，再 `ssh -t <host> "sudo bash /tmp/<script>.sh"`，避免反复输密码。脚本内部把日志重定向到固定文件（如开头 `exec > >(tee /tmp/<name>.log) 2>&1`），跑完再 `scp` 拉日志——别把重定向写在本地 ssh 命令行上（那是本地重定向，不是远端）。
- **非平凡编辑别用 ssh 内联 `sed`/`awk`**（易错、不可审查）：`scp` 拉到本地用编辑器改、再 `scp` 传回；只有简单的单行追加 / 替换才直接 ssh 执行。
