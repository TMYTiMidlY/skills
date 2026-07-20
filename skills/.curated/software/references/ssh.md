# SSH 使用

## 密钥与 passphrase

检查 / 创建 / 改 key：

```bash
ls ~/.ssh/id_*
ssh-keygen -t ed25519 -C "<comment>"     # 没有就建一把，-C 填设备名/邮箱/用途
ssh-keygen -p -f <key_path>              # 给已有 key 加 / 改 / 去 passphrase
```

- 这些命令要**交互式**执行（agent 替不了用户输 passphrase），让用户自己跑。
- 判断一把私钥是否带 passphrase（不暴露私钥内容）：`ssh-keygen -y -f <key> -P ""`——成功打印公钥 = 无 passphrase；报 `incorrect passphrase` = 有。

> 给私钥设 passphrase 是好习惯（私钥文件泄露也不能直接用），代价是每次用都要解锁——这正是 ssh-agent 要解决的：解锁一次，缓存在内存里反复用。**注意**：带 passphrase 的私钥在**没有可用 agent 的环境**（非交互 shell / CI）里会让认证悄悄失败（详见 [非交互 shell 里的 agent 发现与复用](#agent-noninteractive)），所以 agent 不是可选项而是刚需。

## ssh-agent

### 工作原理

ssh-agent 是个**常驻进程**，内存里持有**已解密**的私钥。`ssh` / `git` 做公钥认证签名时**不自己读私钥文件**，而是通过一个 Unix domain socket 把待签数据发给 agent、让 agent 代签。好处：passphrase 只在 `ssh-add` 加载时输一次，之后私钥明文只在 agent 内存里（不落盘、不进子进程环境），多个调用复用同一把已解锁的 key。

### <a id="locate-agent"></a>客户端定位 agent

客户端找 agent 有两条路，**别只会硬编码 socket 路径**：

| 方式 | 怎么用 | 备注 |
|---|---|---|
| 环境变量 `SSH_AUTH_SOCK` | 指向 agent 的 socket | 最常见；登录 session / `.bashrc` 设好后子进程继承 |
| ssh_config `IdentityAgent` | `~/.ssh/config` 里写、可按 Host 配 | 优先级高于环境变量、更稳；支持 `%i`（本地 UID）token 和 `${ENV}` |

（还有 `SSH_AGENT_PID`，只给 `ssh-agent -k`（杀 agent）用，定位 socket 不靠它。）

**socket 路径没有统一标准**——取决于是谁、怎么起的 agent。所以 `export SSH_AUTH_SOCK=/run/user/1000/ssh-agent.socket` 这种写法不可靠：UID 不一定是 1000、agent 也不一定是 systemd 那套。常见实现与位置：

| 谁起的 agent | socket 典型位置 |
|---|---|
| `eval "$(ssh-agent -s)"` | `/tmp/ssh-XXXXXX/agent.<pid>`（每次随机） |
| systemd user service（下面 [systemd user service](#systemd-agent) 那套） | `/run/user/<UID>/ssh-agent.socket` |
| GNOME Keyring | `/run/user/<UID>/keyring/ssh` |
| 新版 gcr-ssh-agent（GNOME 42+） | `/run/user/<UID>/gcr/ssh` |
| macOS（launchd 托管） | 登录时已设好 `SSH_AUTH_SOCK`，形如 `/private/tmp/com.apple.launchd.*/Listeners` |
| Windows OpenSSH | 命名管道 `\\.\pipe\openssh-ssh-agent`，**不是 socket、不读 `SSH_AUTH_SOCK`**（见 [Windows 差异](#windows-agent)） |
| 1Password / KeePassXC / yubikey-agent 等 | 各自路径，查其文档 |

> 上表的具体路径**当线索用、不当真理**——拿不准就用 [`ssh-add -l` 的退出码](#ssh-add-l) 逐个验。

### <a id="ssh-add-l"></a>`ssh-add -l` 的退出码

| exit | 含义 |
|---|---|
| `0` | agent 连上了、**有 key**（会列出指纹）——可用 |
| `1` | agent 连上了、但**没加载任何 key** |
| `2` | **连不上 agent**（`SSH_AUTH_SOCK` 没设 / 指错 / agent 没跑） |

定位 socket 时就靠它：`SSH_AUTH_SOCK=<候选> ssh-add -l`，exit 0 即命中。

### <a id="systemd-agent"></a>Linux/WSL 常驻 agent：systemd user service

密钥缓存在 agent 进程内存，生命周期跟用户登录绑定，不注销 / 不重启就一直可用。`~/.config/systemd/user/ssh-agent.service`：

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

（`%t` = `$XDG_RUNTIME_DIR` = `/run/user/<UID>`，所以 socket 落在 `/run/user/<UID>/ssh-agent.socket`。）

启用，并让 shell / ssh 找到它——**两种写法，UID 都不写死**：

```bash
systemctl --user enable --now ssh-agent

# 法一：环境变量写进 ~/.bashrc（$(id -u) 自动取当前 UID）
echo 'export SSH_AUTH_SOCK=/run/user/$(id -u)/ssh-agent.socket' >> ~/.bashrc
```

```sshconfig
# 法二（更稳，推荐）：~/.ssh/config 里钉死，%i = 本地 UID，不依赖 shell 环境
Host *
    IdentityAgent /run/user/%i/ssh-agent.socket
    AddKeysToAgent yes
    IdentityFile ~/.ssh/id_ed25519
```

- `IdentityAgent` 比环境变量稳：**非交互 / 没 source `.bashrc` 的 shell** 里 `ssh` 也能找到 agent（环境变量法在那种 shell 里会丢，正是 [非交互 shell 里的 agent 发现与复用](#agent-noninteractive) 那个坑）。
- `AddKeysToAgent yes`：首次输 passphrase 后自动缓存进 agent；`IdentityFile`：默认用哪把 key。
- WSL 下可能还要确保 `XDG_RUNTIME_DIR` 有值（pam_systemd 没设时 `%t` 会空）。

### <a id="agent-noninteractive"></a>非交互 shell 里的 agent 发现与复用

**非交互 / 非登录 shell（CI、`bash -c`、各类 agent 远程执行）默认 `SSH_AUTH_SOCK` 为空、不读 `.bashrc`**。典型症状：`git push` / `ssh` 一直 `Permission denied (publickey)`，但人在交互终端连同一台是好的。`ssh -vv` 里会看到迷惑性的 `Server accepts key`（服务器认这把公钥）紧接着 `Permission denied`——**这不是公钥的问题**：公钥不需解密能“亮出来”过预检，但带 passphrase 的私钥在没有已解锁 agent 时**签不了名**。`ssh-add -l` 此时 exit 2（连不上 agent，见 [`ssh-add -l` 的退出码](#ssh-add-l)）。

解决 = 复用宿主上那个用户登录时早已解锁好的常驻 agent，**别猜 socket 路径**（UID 未必 1000、实现也不一定，见 [客户端定位 agent](#locate-agent)），而是先看用户自己怎么配的、再逐个候选用 `ssh-add -l` 验：

```bash
# 1. 优先：用户交互 shell 用的就是这个，直接抄
grep -hoP 'SSH_AUTH_SOCK=\K\S+' ~/.bashrc ~/.profile ~/.zshrc 2>/dev/null   # 可能含 $(id -u) 待展开
systemctl --user show-environment 2>/dev/null | sed -n 's/^SSH_AUTH_SOCK=//p'

# 2. 或自动探测：第一个能被 ssh-add 认（exit 0）的 socket 就用它
uid=$(id -u)
for sock in \
    "$SSH_AUTH_SOCK" \
    "/run/user/$uid/ssh-agent.socket" \
    "/run/user/$uid/keyring/ssh" \
    "/run/user/$uid/gcr/ssh" \
    /tmp/ssh-*/agent.* ; do
  [ -S "$sock" ] && SSH_AUTH_SOCK="$sock" ssh-add -l >/dev/null 2>&1 \
    && { export SSH_AUTH_SOCK="$sock"; break; }
done
ssh-add -l        # 列出 key = 成功；passphrase 全程不经过你 / 不进对话
```

兜底：从运行中的进程扒 socket——`ps -u "$(id -u)" -o args= | grep '[s]sh-agent'` 看有没有 `-a <socket>`。根治：给 `~/.ssh/config` 配 `IdentityAgent`（[systemd user service](#systemd-agent)），非交互 shell 也能命中，从此不用每次找。

> 排错口诀：`Server accepts key` + `Permission denied` = 公钥没问题、私钥签名出了问题，往 passphrase / agent 方向查，别反复重加公钥。`git ls-remote <url>` 是“网络+认证+仓库存在”三合一的最快只读探针。

### <a id="windows-agent"></a>Windows：Git Bash 与 PowerShell 的 ssh-agent 差异

Windows 上最容易踩的是 Git Bash 和 PowerShell 可能调用不同的 `ssh.exe`，因此连到不同的 agent。Windows OpenSSH 的 agent 是**命名管道** `\\.\pipe\openssh-ssh-agent`，不用 `SSH_AUTH_SOCK`。

- Git Bash 常见写法 `eval "$(ssh-agent -s)"`：启动/复用 Git for Windows/MSYS 环境里的 `ssh-agent`，并注入 `SSH_AUTH_SOCK`、`SSH_AGENT_PID`。Git Bash 里的 `ssh-add` 和 Git for Windows 自带 `ssh.exe` 依赖这两个变量找 agent。
- PowerShell 用 Windows OpenSSH 时通常不需要设 `SSH_AUTH_SOCK`/`SSH_AGENT_PID`。启动 Windows 的 `ssh-agent` 服务后，`C:\Windows\System32\OpenSSH\ssh.exe` 通过命名管道访问已缓存的 key。
- Git for Windows 自带 `usr/bin/ssh.exe` / `ssh-agent.exe` / `ssh-add.exe`；`eval "$(ssh-agent -s)"` 起的是这套 MSYS agent。想让 Git 明确走 Windows OpenSSH service：

  ```powershell
  git config --global core.sshCommand "C:/Windows/System32/OpenSSH/ssh.exe"
  ```

  这能让 PowerShell、Git、Git Bash 里的 Git 命令尽量统一到 Windows OpenSSH，避免 `ssh` 不问 passphrase、`git pull` 却反复询问。

- **不要**把 Git Bash 的 `SSH_AUTH_SOCK`/`SSH_AGENT_PID` 直接搬进 PowerShell——Windows OpenSSH 不靠这俩变量定位 agent，设错了反而让不同客户端混用失败。
- Windows PowerShell 下也别依赖 `ControlMaster`/`ControlPath`/`ControlPersist`（面向 Unix socket，Windows OpenSSH 组合下通常不可用）；免重复输 passphrase 优先靠 `ssh-agent`。
- 自动启动参考 [Auto-launching ssh-agent on Git for Windows](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/working-with-ssh-key-passphrases#auto-launching-ssh-agent-on-git-for-windows)。

## 主机密钥校验：known_hosts 与 CheckHostIP

SSH 连接时验证的是服务器的**主机密钥**（host key），不是 IP，也不是域名。`known_hosts` 记录“某主机名 / IP → 哪把 host key”。只有服务器重装、换了密钥才算“key 变了”；**只换 IP、host key 不变，从密码学角度还是同一台机器**。

不同 SSH 实现对“IP”的态度不一样，这会造成同一台主机用一个客户端连得上、换一个客户端却报错：

- **OpenSSH 默认 `CheckHostIP no`**（`man ssh_config`：默认不检查 IP；这是 OpenSSH 8.5 改的默认值，未逐版核证）。它**只按连接用的主机名**去 `known_hosts` 找 key 比对，完全不看 IP。后果：服务器 IP 变了（换 VPS、DNS 改解析），只要 host key 没变、主机名条目命中，OpenSSH 一声不吭就放行；副作用是它**从不写 IP→key 条目**，`known_hosts` 里往往只有主机名的明文条目。
- **纯第三方 SSH 库**（如 [asyncssh](https://github.com/ronf/asyncssh)，纯 Python 实现，被一些 MCP / 自动化工具当底层引擎）没有 `CheckHostIP no` 这种放宽，校验时**把连接解析到的 IP 也纳入 `known_hosts` 匹配**（≈ `CheckHostIP yes` 的行为）。

**典型症状**：同一台主机，`ssh <host>`（OpenSSH）正常，但走 asyncssh 之类的客户端报 `Host key is not trusted for host <host>`。**几乎总是**：主机 host key 没变、但解析 IP 变了，而 `known_hosts` 里只有主机名的明文条目、缺新 IP 的条目——不是真的 key 被篡改。

诊断（确认“是 IP 变了”而非“key 变了”）：

```bash
# 存的 key 和服务器实时 key 是否一致（一致 = 不是 key 变了）
diff <(ssh-keygen -F <host> | awk '/ssh-ed25519/{print $3}') \
     <(ssh-keyscan -t ed25519 <host> 2>/dev/null | awk '{print $3}')
ssh-keygen -F <新IP>     # 输出为空 = known_hosts 缺这个 IP 的条目
```

修复——补上“主机名 + IP”的条目（`-H` 顺带哈希，避免明文主机名/IP 落盘）：

```bash
ssh-keyscan -H <host> <新IP> >> ~/.ssh/known_hosts
```

追加不删旧条目，对 OpenSSH（只看主机名）无影响，同时补齐检查 IP 的客户端所需的 IP→key 映射。

**另一种情况：host key 真的变了**（连接弹 `@@@ WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED @@@` + `Host key verification failed`）——换 IP 后重装了系统、或新 IP 根本是另一台机，host key 跟着换了。这跟上面「IP 变、key 没变」相反：OpenSSH 会**硬拒绝连接**（不再静默放行），必须显式重新信任。

⚠️ 这条警告的正常成因**就是**中间人攻击。**只有你确知变更原因**（自己换了 IP / 重装了这台 / 新 IP 是新机）才重新信任；拿不准先带外核对新 key 指纹，别盲目清。

```bash
# 1)（稳妥）带外核对：ssh-keyscan 拿服务器实时 key 指纹，和 VPS 面板/控制台给的比对
ssh-keyscan -t ed25519 <host> 2>/dev/null | ssh-keygen -lf -

# 2) 删掉旧条目（那条大警告信息里会直接打印这条命令；若还存过 IP→key 条目再删 IP）
ssh-keygen -R <host>
ssh-keygen -R <新IP>          # 可选

# 3) 重连、接受新 key（交互按 yes 自动 re-add，默认 -H 哈希落盘）
ssh <host>
# 自动化 / 非交互：一次性接受首见 key（但仍会拒绝“已存在且不符”的 key，需先做第 2 步）
ssh -o StrictHostKeyChecking=accept-new <host>
```

事后可坐实「是重装不是有人冒充」：重新信任后 `ssh-keygen -F <host>` 存的指纹，应与 `ssh-keyscan` 实时指纹、以及带外拿到的指纹三者一致。

## <a id="controlmaster"></a>ControlMaster 连接复用

裸 `ssh` / `scp` 每次调用都新建 TCP 并重新认证（百毫秒级开销）。`ControlMaster` 让多次 ssh 复用同一条已认证的**主连接**（经一个 Unix domain socket），后续调用只开 channel，省掉重复握手；`ControlPersist` 让主连接在空闲后再保留一段时间。

在 `~/.ssh/config` 的 `Host *` 下：

```sshconfig
Host *
    ControlMaster auto
    ControlPath ~/.ssh/sockets/%r@%h-%p
    ControlPersist 10m
```

- **Windows OpenSSH 不支持** `ControlMaster`（依赖 Unix domain socket，Windows 默认编译不带），复用不可靠；Win 上免重复输 passphrase 优先靠 `ssh-agent`（见 [Windows 差异](#windows-agent)）。
- 改了 config（如新增 `RemoteForward`）后，**已存在的主连接不含新配置**，需 `ssh -O exit <host>` 关掉主连接、重连才生效。

## RemoteForward 代理转发

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

## 在远端连续跑命令 / sudo / 拉日志

没有 hash 校验的远端编辑/执行工具（如 portal MCP）时，纯 OpenSSH 也能干活。前提：agent 起的非交互 shell 里 `SSH_AUTH_SOCK` 可能没设——先按 [非交互 shell 里的 agent 发现与复用](#agent-noninteractive) 找到并复用 agent，否则带 passphrase 的 key 会让下面这些 ssh/scp 全 `Permission denied`。

### 单条 / 连续多条命令

- 单条：`ssh <host> "<command>"`。
- 连续多条：配好 [ControlMaster 连接复用](#controlmaster) 的 `ControlMaster` 后，多次 `ssh <host> "..."` 复用同一条已认证主连接（省握手）；或把多步合进**一个脚本**一次跑（尤其要 sudo 时，避免反复输密码，见下）。

### 交互式 sudo（`ssh -t`）

`sudo` 从 TTY 读密码，普通 `ssh <host> "sudo ..."` 没分配 TTY、读不到密码（或直接报错）。把“用户负责的事”压到极小——只敲一行 `ssh -t`，其余 agent 在本地做：

1. **agent 在本地** `/tmp/` 用编辑器写脚本（不在远端 `cat <<EOF` 手敲）。脚本开头固化 `exec > >(tee /tmp/<name>.log) 2>&1`——日志路径写死在脚本里，别拼到 ssh 命令行的 `>` 重定向上（那是**本地**重定向、不是远端）。
2. **agent 自己 `scp`** 推到远端 `/tmp/`；不要让用户 scp、也不要让用户手敲建脚本。
3. 给用户**唯一一条命令**：`ssh -t <host> "sudo bash /tmp/<name>.sh"`（`-t` 强制分配 TTY，让 sudo 能弹密码）。多步操作合进一个脚本，别拆成多次 `ssh -t` 让用户反复输密码。
4. 用户跑完通知 agent，**agent 自己 `scp` 拉** `/tmp/<name>.log` 回来解读，别让用户复制粘贴终端输出。

### 看 log / 拉文件回本地

远端日志、产物一律 `scp <host>:/tmp/<name>.log /tmp/` 拉回本地读，不要让用户贴终端。

### 非平凡编辑

别用 ssh 内联 `sed`/`awk`（易错、不可审查）：`scp` 拉到本地用编辑器改、再 `scp` 传回；只有简单的单行追加 / 替换才直接 ssh 执行。

## sshd 服务端：进程模型与配置生效

前面几节都是**客户端**（`ssh`/`scp`）视角；这节讲**服务端** `sshd` 两件常被误解的事：它以什么身份跑、改完配置怎么生效而不断线。sshd_config 的加固指令本身（`PasswordAuthentication` / `PermitRootLogin` / `PubkeyAuthentication` 等）见 `vps-maintenance` skill 的 SSH 服务端加固章节。

### <a id="sshd-privsep"></a>进程模型：root 主监听与特权分离

`sshd` 的主监听进程以 **root** 运行——它要绑定特权端口 22、要能校验任意用户口令并切换到目标身份，非 root 做不到：

```bash
ps -eo user,pid,ppid,args | grep '[s]shd'
```

典型是一棵树：一个 root 的 `/usr/sbin/sshd -D [listener]`（`-D` = 不 fork 到后台、独立常驻监听），每来一条连接再拆成两个进程：

```
root    sshd: /usr/sbin/sshd -D [listener]   ← 主监听，root
root    sshd: <user> [priv]                  ← 该连接的 root 特权监控进程
<user>  sshd: <user>@pts/0                    ← 降权到登录用户的实际会话进程
```

这是 OpenSSH 的**特权分离**（privilege separation）：处理网络输入这类高风险逻辑的会话进程**不带 root**，真正需要 root 的操作（写 utmp、切换身份等）隔离在 `[priv]` 监控进程里。所以「sshd 是 root 在跑」是正常且期望的，不是配置错误——每条连接一半 root 一半普通用户，正是它在按设计降权。

### <a id="sshd-reload"></a>应用配置改动：reload 与 restart

改完 sshd 配置让其生效，`reload` 通常比 `restart` 稳。差别在于对**已建立连接**的处理，而这由 service 单元的 `ExecReload` 与 `KillMode` 决定，先查清楚：

```bash
systemctl show ssh -p ExecReload -p KillMode -p MainPID
```

- 服务名因发行版而异：Debian/Ubuntu 多为 `ssh`，RHEL 系多为 `sshd`。
- 较新镜像可能启用 socket 激活 `ssh.socket`（`systemctl is-active ssh.socket` 查）；启用后 `restart` 还牵扯 socket 单元的交接，`reload` 则不碰它。

两种方式的区别：

- **`reload`**：`ExecReload` 一般是「先 `sshd -t` 校验配置，再 `kill -HUP $MAINPID`」。主监听进程收到 SIGHUP 会重读配置并重新监听，**已存在的会话进程不受影响**；配置有语法错时 `sshd -t` 先失败、SIGHUP 不发出，不会把服务改挂。
- **`restart`**：是否踢掉现有会话取决于 `KillMode`。`KillMode=process`（OpenSSH 单元常见）只杀主进程、保留已 fork 的会话；但 restart 仍会中断监听、且启用 `ssh.socket` 时还有 socket 交接。

> 认证类指令（`PasswordAuthentication`、`PermitRootLogin`、`PubkeyAuthentication` 等）是**逐连接**在认证阶段读取的，`reload` 后对**新连接**立即生效、无需 restart。已存在的会话不回溯改变（它们早过了认证阶段），这正合预期——不会把正在用的连接踢下线。

```bash
sudo sshd -t && sudo systemctl reload ssh    # 校验通过才 reload
```

> 实测 Ubuntu 24.04 / OpenSSH 9.6：`ExecReload` 为 `sshd -t` + `kill -HUP`、`KillMode=process`。其他发行版 / 版本以 `systemctl show` 实际输出为准。
