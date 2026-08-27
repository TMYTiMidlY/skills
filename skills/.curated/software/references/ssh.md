# SSH

SSH 同时涉及客户端身份认证、服务端主机身份校验、连接管理、远端操作和 `sshd` 服务端。本文件按这几条边界组织通用配置与排障方法；服务端认证策略与公网加固由 `vps-maintenance` skill 处理。

## 客户端密钥认证

客户端用私钥证明自己的身份。passphrase 保护的是落盘私钥，agent 则提供一个可复用的签名入口；两者解决的问题不同。

### 私钥与 passphrase

下面依次展示查看密钥文件、创建密钥，以及修改私钥 passphrase 的命令；执行 `ssh-keygen -p -f` 时，`-f` 必须指向私钥文件（如 `~/.ssh/id_ed25519`），不要指向 `.pub` 公钥：

```bash
ls -l ~/.ssh/id_*
ssh-keygen -t ed25519 -C "device-or-purpose"
ssh-keygen -p -f /path/to/private_key
```

创建密钥和修改 passphrase 都需要用户交互输入。判断一把可读私钥是否接受空 passphrase 时，不必显示其派生公钥：

```bash
ssh-keygen -y -P '' -f /path/to/private_key >/dev/null
```

返回 0 表示空 passphrase 可用；错误明确写着 passphrase 不正确，才说明私钥受 passphrase 保护。权限、格式或文件损坏也会让命令失败，不能一律归为“有 passphrase”。

passphrase 能降低私钥文件泄漏后被直接使用的风险；代价是签名前需要解锁。无 passphrase 的私钥可以由 `ssh` 直接读取，因此 agent 是可选的。受保护私钥若要在无人交互环境中签名，则需要一个已能签名的 agent、硬件密钥或其他签名提供方。

### ssh-agent 的职责

`ssh-agent` 实现一套本地签名协议。`ssh` 选中 agent 后，通过本地 socket 发送签名请求；没有可用 agent 时，`ssh` 仍可直接读取配置的私钥文件。原生 OpenSSH agent 启动时没有身份，密钥由 `ssh-add` 加入，或由 `ssh` 在启用 `AddKeysToAgent` 时加入。[OpenSSH `ssh-agent(1)`](https://man.openbsd.org/OpenBSD-7.5/ssh-agent.1)给出了这套生命周期。

agent 通常不允许客户端导出私钥，但能访问 socket 的同一用户进程可以请求 agent 代签；root 也能绕过普通文件权限。保护 agent socket 等同于保护密钥的签名能力，转发 agent 时也适用这一边界。

### <a id="systemd-agent"></a>Linux systemd user agent

桌面和发行版常把 agent 包装为 systemd user unit。这里的“系统 service”指由系统软件包安装到 `/usr/lib/systemd/user/`、由 `systemctl --user` 管理的用户服务，不是由 PID 1 直接持有密钥的 system service。

先查实际 unit 来源和状态，再决定启用方式：

```bash
systemctl --user show gcr-ssh-agent.socket \
  -p LoadState -p FragmentPath -p UnitFileState -p ActiveState
systemctl --user show ssh-agent.service \
  -p LoadState -p FragmentPath -p UnitFileState -p ActiveState
```

`FragmentPath` 能看出当前生效的是发行版 unit，还是 `~/.config/systemd/user/` 下的同名用户覆盖。

#### user unit 的 enable 作用域

user unit 的“全局”仍然是用户服务配置，不是 system service：`systemctl --global enable` 通常把 wants symlink 放到 `/etc/systemd/user/`，对所有用户今后的 user manager 生效；`systemctl --user enable` 则把 symlink 放到当前用户的 `~/.config/systemd/user/`。

`systemctl --user disable` 只删除当前用户作用域中的 enable symlink。systemd 没有一个名为“disabled”的负向记录去遮蔽 `/etc/systemd/user/*target.wants/` 中的全局链接，所以 unit 仍可能被全局依赖自动拉起；命令会对此给出 “still enabled in global scope” 警告。[systemctl 对 `--user` / `--global` 与 `disable` 的定义](https://github.com/systemd/systemd/blob/v255/man/systemctl.xml)明确区分了这几个作用域。

只让当前用户改用另一种 agent 时，user-level mask 是作用域最小的覆盖：

```bash
systemctl --user mask --now \
  gcr-ssh-agent.service \
  gcr-ssh-agent.socket
```

mask 会在当前用户的高优先级 unit 目录建立指向 `/dev/null` 的同名链接，使该用户的手动启动、依赖拉起和 socket activation 都被拒绝，同时不影响其他用户。[systemd.unit 对 masked load state 的定义](https://github.com/systemd/systemd/blob/v255/man/systemd.unit.xml)也说明了空文件或 `/dev/null` symlink 的语义。

只有整台机器的策略是“所有用户都不自动启用 GCR”时，才修改全局 enable 链接：

```bash
sudo systemctl --global disable \
  gcr-ssh-agent.service \
  gcr-ssh-agent.socket
```

`--global disable` 只改变今后所有用户的 enablement，不会自动停止已经运行在各 user manager 中的实例；现有实例仍需在对应用户会话中 stop/mask，或等该 user manager 结束。只切换当前用户时无需 sudo，也无需改动全局配置。恢复当前用户的覆盖使用 `systemctl --user unmask ...`。

#### `systemctl --user` 的控制总线

`systemctl --user` 通过用户 D-Bus 控制 user manager，它不通过 agent socket。由非登录 shell、远端执行器或某些终端启动的进程可能没有 `XDG_RUNTIME_DIR` / `DBUS_SESSION_BUS_ADDRESS`，此时会报 `Failed to connect to bus: No medium found`（本地化后也可能显示“找不到介质”）。

先区分“环境没有指向 bus”和“user manager 根本不存在”：

```bash
runtime_dir=/run/user/"$(id -u)"
test -S "$runtime_dir/bus"
pgrep -a -u "$(id -u)" -x systemd
```

若 bus socket 和 `systemd --user` 都存在，可以只给当前命令显式指定入口：

```bash
XDG_RUNTIME_DIR="$runtime_dir" \
DBUS_SESSION_BUS_ADDRESS="unix:path=$runtime_dir/bus" \
systemctl --user status ssh-agent.service
```

这种前缀赋值只对该命令生效；同一 shell 需要连续管理 user unit 时可以 export。它们只帮助 `systemctl` 找到控制总线，不会设置 `SSH_AUTH_SOCK`、不会选择 agent，也不会解锁私钥。若 bus socket 或 user manager 不存在，单纯补变量无效，应检查登录会话、PAM/systemd 集成或 linger 状态。

#### GCR `gcr-ssh-agent`

GNOME 的 `gcr4` 包可提供 `gcr-ssh-agent.service` 和 `gcr-ssh-agent.socket`，对外 socket 通常是 `%t/gcr/ssh`。`%t` 在 systemd user unit 中展开为用户 runtime 目录，通常即 `/run/user/<UID>`。[Ubuntu 24.04 `gcr4` 文件清单](https://packages.ubuntu.com/noble/amd64/gcr4/filelist)列出了这两个 unit。

GCR 是 OpenSSH agent 协议的包装层：它可以列出 `~/.ssh` 中已知身份，并在真正收到签名请求时从 GNOME Secret Service 取已保存的 passphrase，或弹出图形提示，再交给内部 OpenSSH agent 完成签名。因此 `ssh-add -l` 看见身份，不一定表示对应私钥已经解密。[GNOME 维护者对加载流程的说明](https://discourse.gnome.org/t/gdm-gnome-keyring-and-gcr-ssh-agent-service/23498/3)记录了这一行为。

GCR 使用 socket activation；启用 socket 后，首次连接可以按需启动 service：

```bash
systemctl --user enable --now gcr-ssh-agent.socket
systemctl --user status gcr-ssh-agent.socket gcr-ssh-agent.service
```

socket 已存在而进程尚未运行是正常状态，单看 `pgrep` 会把这种状态误判为 agent 不可用。

无图形界面时，GCR 的“按需解锁”还有一层限制：它可以先广告 `~/.ssh` 中的公钥，但私钥需要 passphrase 且 Secret Service 没有已保存秘密时，会尝试启动 `org.gnome.keyring.SystemPrompter`。没有可用的 `DISPLAY` / `WAYLAND_DISPLAY` 或图形 prompter 启动失败时，签名请求会返回 `agent refused operation`，journal 常见：

```text
couldn't prompt for password: ... SystemPrompter exited with status 1
the /usr/bin/ssh-add command failed
```

此时 `ssh-add -l` 仍可能列出身份，因为它只查询 GCR 广告的公钥；用签名探针才能复现真正故障：

```bash
agent_socket=/run/user/"$(id -u)"/gcr/ssh
SSH_AUTH_SOCK="$agent_socket" ssh-add -T ~/.ssh/id_ed25519.pub
journalctl --user -u gcr-ssh-agent.service -n 50 --no-pager
```

GCR 已向 OpenSSH 声明拥有该身份后，OpenSSH 会走 agent 签名分支；agent 拒绝签名时，不会进入“直接读取 `IdentityFile`、终端询问 passphrase、再执行 `AddKeysToAgent`”的路径。因此 `AddKeysToAgent yes` 不能修复这个故障。

无图形环境可以从交互式 TTY 手动把私钥加入 GCR 的内部 agent：

```bash
SSH_AUTH_SOCK="$agent_socket" ssh-add ~/.ssh/id_ed25519
```

这会在终端读取 passphrase，并缓存到 agent 生命周期结束。重启 GCR service 会清空该内存缓存；无需为普通 SSH 连接反复 restart。若期望“首次交互式 SSH 在终端解锁，随后由 `AddKeysToAgent` 缓存”，原生 OpenSSH agent 比依赖图形 prompter 的 GCR 更符合这条调用链。

#### OpenSSH `ssh-agent`

一些发行版在 `openssh-client` 包中提供 `ssh-agent.service`。Debian/Ubuntu 的包清单包含该 user unit 和 `/usr/lib/openssh/agent-launch`；这属于发行版集成，不是所有 Linux 发行版都采用相同 unit。[Ubuntu 24.04 `openssh-client` 文件清单](https://packages.ubuntu.com/noble-updates/amd64/openssh-client/filelist)可作为一个版本化实例。

Ubuntu 24.04 的 vendor unit 是 `static`，由 `graphical-session-pre.target` 的系统级 wants 链接拉起，不能用 `systemctl --user enable ssh-agent.service` 启用。其 `agent-launch` 还会检查图形会话条件、已有的 `SSH_AUTH_SOCK` 和 `/etc/X11/Xsession.options`；条件满足时常见 socket 为 `%t/openssh_agent`。其他发行版或更新版本可能提供可启用的 `ssh-agent.socket`，应以本机 unit 为准：

```bash
systemctl --user cat ssh-agent.service
systemctl --user is-enabled ssh-agent.service
systemctl --user start ssh-agent.service
systemctl --user status ssh-agent.service
```

原生 OpenSSH agent 把已加入身份保存在进程内存中。service 或系统重启后需要重新加入受保护密钥；`ssh-add -t` 或 `AddKeysToAgent` 的时间参数可以限制身份寿命。

#### Agent 选择与启用

GCR、OpenSSH、GPG agent 和第三方 agent 可以同时运行在不同 socket 上，但客户端一次只选中一个。选择时看所需行为，而不是只看哪个进程存在：

| 行为 | GCR | 原生 OpenSSH agent |
|---|---|---|
| 桌面集成 | GNOME Secret Service 和图形提示 | 取决于 `SSH_ASKPASS` 与会话环境 |
| 身份发现 | 可枚举 `~/.ssh` 中的身份并按需解锁 | 初始为空，需 `ssh-add` 或 `AddKeysToAgent` |
| 常见发行版入口 | `gcr-ssh-agent.socket` | `ssh-agent.service` 或 `ssh-agent.socket`，随发行版变化 |
| 重启后的状态 | 可再次从 keyring 取已保存秘密 | 内存身份消失，需要重新加入 |

同名用户 unit 会覆盖系统 unit。若 `FragmentPath` 指向 `~/.config/systemd/user/ssh-agent.service`，当前使用的是本地覆盖，不是软件包原件。

只有在发行版没有可用 unit、且确实需要固定 socket 的常驻原生 agent 时，才需要自建 user unit：

```ini
[Unit]
Description=OpenSSH authentication agent

[Service]
Type=simple
Environment=SSH_AUTH_SOCK=%t/ssh-agent.socket
ExecStart=/usr/bin/ssh-agent -D -a $SSH_AUTH_SOCK

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now ssh-agent.service
```

`loginctl enable-linger` 会让 user manager 在没有登录会话时仍可运行，并可能在开机时启动；没有 linger 时，生命周期通常跟用户会话走。是否启用 linger 是独立的常驻策略，不是 agent 本身的要求。

### <a id="locate-agent"></a>客户端定位 agent 与选择身份

OpenSSH 可以从环境变量或 `ssh_config` 取得 agent socket；`ssh_config` 里的其他字段再决定尝试哪些身份、是否把刚解锁的私钥加入 agent。只有 `SSH_AUTH_SOCK` 和 `IdentityAgent` 负责定位 agent：

| 入口或字段 | 谁读取 | 作用 |
|---|---|---|
| `SSH_AUTH_SOCK` | OpenSSH、`ssh-add` 及许多兼容库 | 从进程环境取得 agent socket |
| `IdentityAgent` | OpenSSH 客户端 | 在 `ssh_config` 中指定 socket；设置后覆盖 `SSH_AUTH_SOCK` |
| `IdentityFile` | OpenSSH 客户端 | 指定可直接读取的身份文件，也可用于筛选 agent 中的对应身份 |
| `AddKeysToAgent` | OpenSSH 客户端 | 从文件成功解锁私钥后，把它加入已经找到的 agent |
| `IdentitiesOnly` | OpenSSH 客户端 | 限制实际尝试的文件身份和对应 agent 身份 |

`AddKeysToAgent` 不会启动或定位 agent，也不能替用户解锁私钥；它只是在“socket 已找到、私钥已成功读取”之后增加缓存这一步。agent 已经提供匹配身份时，`ssh` 会直接请求 agent 签名，不需要再次从文件加载。

OpenSSH 的选择过程可以概括为：

```text
ssh 启动
  ↓
读取命令行、用户 ssh_config、系统 ssh_config
  ↓
IdentityAgent 已配置？── 是 → 使用该 socket
          │
          否
          ↓
读取 SSH_AUTH_SOCK
  ↓
agent 提供允许使用的身份？── 是 → 请求 agent 签名
          │
          否
          ↓
读取 IdentityFile → 必要时提示解锁
          ↓
AddKeysToAgent 启用且 agent 可达？── 是 → 把已解锁身份加入 agent
```

交互式和非交互式 OpenSSH 都读取 `ssh_config`。因此配置了有效的 `IdentityAgent` 后，即使进程没有 `SSH_AUTH_SOCK`，`ssh`、`scp` 及通常由 Git 调用的 OpenSSH 仍能找到 agent。Unix 下的 `ssh-add` 不读取 `ssh_config`，它仍依赖 `SSH_AUTH_SOCK`；这解释了为什么 `ssh` 可以成功，而同一环境里的 `ssh-add -l` 可能返回 2。

`SSH_AGENT_PID` 记录部分原生 agent 的 PID，供 `ssh-agent -k` 等管理操作使用；客户端通信只需要 socket。

`IdentityAgent` 支持 OpenSSH token，`%i` 表示本地 UID；systemd 的 `%t` 不能写进 `ssh_config`。例如：

```sshconfig
Host host.example
    IdentityAgent /run/user/%i/gcr/ssh
    IdentityFile ~/.ssh/id_ed25519
    AddKeysToAgent yes
```

使用 Ubuntu/Debian 的 OpenSSH vendor agent 时，路径可能改为 `/run/user/%i/openssh_agent`；自建固定 socket unit 则可能是 `/run/user/%i/ssh-agent.socket`。先从 unit 和实际 socket 确认，不能凭实现名称猜路径。[`IdentityAgent`、`IdentityFile` 与 `AddKeysToAgent`](https://man.openbsd.org/OpenBSD-7.5/ssh_config.5)的含义由 OpenSSH 配置手册定义。

其他常见入口只作为排查线索：

| 实现 | 常见入口 |
|---|---|
| 直接运行 `ssh-agent` | 读取它输出的 `SSH_AUTH_SOCK`；默认路径随 OpenSSH 版本变化 |
| 旧版 GNOME Keyring | `/run/user/<UID>/keyring/ssh` |
| macOS launchd | 登录环境提供的 `/private/tmp/com.apple.launchd.<random>/Listeners` |
| Windows OpenSSH | `\\.\pipe\openssh-ssh-agent`，不是 Unix socket |
| 1Password、KeePassXC、硬件 agent | 以相应产品文档和实际配置为准 |

### <a id="ssh-add-l"></a>Agent 状态与密钥加载

`ssh-add -l` 的退出状态能区分“socket 不通”和“agent 没身份”：

| exit | 含义 |
|---|---|
| `0` | agent 可达，并广告至少一个身份 |
| `1` | agent 可达，但没有身份，或查询命令失败 |
| `2` | 无法联系 agent |

这是 [`ssh-add(1)` 定义的退出状态](https://man.openbsd.org/OpenBSD-7.5/ssh-add.1)。显式验证某个 socket：

```bash
agent_socket=/run/user/"$(id -u)"/gcr/ssh
SSH_AUTH_SOCK="$agent_socket" ssh-add -l
```

比较公钥指纹可以确认 agent 广告的是否为目标身份：

```bash
ssh-keygen -lf ~/.ssh/id_ed25519.pub
SSH_AUTH_SOCK="$agent_socket" ssh-add -l
```

`ssh-add -T` 会执行一次签名与验签，比“列得出来”更接近可用性验证；GCR 可能在此时提示解锁：

```bash
SSH_AUTH_SOCK="$agent_socket" ssh-add -T ~/.ssh/id_ed25519.pub
```

进程列表用于追查 provider，而不是判定 socket 是否可用：

```bash
systemctl --user status gcr-ssh-agent.socket gcr-ssh-agent.service
ps -u "$(id -u)" -o pid,comm,args | grep -E '[s]sh-agent|[g]cr-ssh-agent'
```

### <a id="agent-noninteractive"></a>非交互 shell 的 agent

非交互模式不会让 OpenSSH 跳过 `ssh_config`。差异通常来自进程环境和解锁通道：非交互 shell 会继承父进程已有环境，但可能不执行负责 export 的交互式启动文件；CI、systemd service 或 `BatchMode=yes` 也往往没有可用的 TTY/askpass 来输入 passphrase。

只要 `IdentityAgent` 指向可达 socket，且该 agent 已能用目标身份签名，非交互 OpenSSH 即使没有 `SSH_AUTH_SOCK` 也能认证。失败通常发生在以下链路：

```text
没有 IdentityAgent
  + 父进程没有 SSH_AUTH_SOCK
  → ssh 找不到 agent

或

agent 可达但没有目标身份
  + IdentityFile 受 passphrase 保护
  + 当前环境不能交互解锁
  → 公钥可能被服务器接受，但客户端无法完成签名
```

`AddKeysToAgent yes` 不能修复这两种失败：前一种没有可加入的 agent，后一种尚未成功解锁私钥。

先看 OpenSSH 的生效配置和当前环境，不根据“交互终端能连”推断自动化环境也能连：

```bash
ssh -G host.example |
  awk '$1 ~ /^(identityagent|identityfile|addkeystoagent|identitiesonly|batchmode)$/'
printf 'SSH_AUTH_SOCK=%s\n' "${SSH_AUTH_SOCK:-<absent>}"
ssh-add -l
```

这里 `ssh-add -l` 只验证环境变量指向的默认入口；它失败不等于配置了 `IdentityAgent` 的 OpenSSH 也找不到 agent。需要验证某个显式 socket 时：

```bash
agent_socket=/path/to/agent.socket
SSH_AUTH_SOCK="$agent_socket" ssh-add -l
```

若 `ssh -vv` 显示服务器接受了某个公钥，随后仍然 `Permission denied (publickey)`，说明服务器认可该公钥，但客户端没有完成签名。受保护私钥找不到已解锁 agent 是常见原因；私钥权限、文件格式、签名算法和 provider 选择也可能导致同样现象。

排查顺序如下：

1. 查 `ssh -G` 的 `IdentityAgent`、`IdentityFile`、`AddKeysToAgent`、`IdentitiesOnly` 和 `BatchMode`。
2. 查当前进程实际继承的 `SSH_AUTH_SOCK`。
3. 分别验证 `IdentityAgent` 指向的 socket 和环境变量指向的默认 socket。
4. 从 `systemctl --user show ... -p FragmentPath -p Environment` 和 unit 内容确认 socket 来源。
5. 最后看进程参数和 journal，确认是谁创建或接管了 socket。

只读取 `SSH_AUTH_SOCK`、要求显式 `agent_path` 或不完整实现 OpenSSH 配置的库，需要按各自接口传入 agent。无 passphrase 的私钥可以直接读取，因此没有 agent 不必然导致认证失败。

只读端到端探针应禁用交互提示：

```bash
ssh -o BatchMode=yes -o ConnectTimeout=10 host.example true
GIT_SSH_COMMAND='ssh -o BatchMode=yes' git ls-remote git@host.example:owner/repo.git
```

### <a id="windows-agent"></a>Windows agent

Windows OpenSSH 使用 Windows service 和命名管道 `\\.\pipe\openssh-ssh-agent`，不依赖 Unix 的 `SSH_AUTH_SOCK`。管理员 PowerShell 可以启用并启动系统自带服务：

```powershell
Get-Service ssh-agent | Set-Service -StartupType Automatic
Start-Service ssh-agent
Get-Service ssh-agent
ssh-add $env:USERPROFILE\.ssh\id_ed25519
```

这是 [Microsoft 的 OpenSSH 密钥管理流程](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_keymanagement)。

Git Bash 的 `eval "$(ssh-agent -s)"` 启动的是 Git for Windows/MSYS agent，并设置该 Bash 进程树使用的 `SSH_AUTH_SOCK`。PowerShell、Windows OpenSSH 和 Git Bash 可能调用不同的 `ssh.exe`，所以“终端里的 ssh 不再询问，Git 却仍询问”通常是客户端实现没有统一。

分别确认实际二进制和 Git 配置：

```powershell
Get-Command ssh
git config --show-origin --get core.sshCommand
```

```bash
type -a ssh
git config --show-origin --get core.sshCommand
```

需要让 Git 明确使用 Windows OpenSSH 时，可以设置：

```powershell
git config --global core.sshCommand "C:/Windows/System32/OpenSSH/ssh.exe"
```

这只改变 Git 的 SSH 客户端选择，不会改变独立运行的 `ssh.exe`。不要把 Git Bash 的 `SSH_AUTH_SOCK` 或 `SSH_AGENT_PID` 复制到 PowerShell。Windows OpenSSH 的连接复用限制见 [ControlMaster 连接复用](#controlmaster)。

## 主机密钥校验

用户私钥证明“客户端是谁”，服务器 host key 则证明“连到的是哪台服务器”。`known_hosts` 保存后者；修改记录前必须先建立对新 host key 的独立信任。

### `known_hosts` 与 `CheckHostIP`

host key 的查找对象不仅是裸域名，还可能包含连接使用的 hostname、地址、端口和 `HostKeyAlias`。先查看 OpenSSH 的生效配置与已有记录：

```bash
ssh -G host.example | awk '$1 ~ /^(hostname|port|hostkeyalias|checkhostip|userknownhostsfile)$/'
ssh-keygen -F host.example
ssh-keygen -F '[host.example]:2222'
```

`CheckHostIP yes` 会额外按目标 IP 检查和记录 host key；当前 OpenSSH 默认是 `no`，因此默认只按连接使用的主机标识完成校验。[`CheckHostIP`](https://man.openbsd.org/OpenBSD-7.5/ssh_config.5)的定义以客户端版本为准。

第三方客户端未必完整实现 OpenSSH 配置，但不能据此推断它们都要求 hostname 和 IP 同时命中。AsyncSSH 2.24.0 会把目标 hostname 和 address 的匹配结果合并，任一匹配即可；见[版本锁定源码](https://github.com/ronf/asyncssh/blob/v2.24.0/asyncssh/known_hosts.py#L181-L199)。出现 `Host key is not trusted` 时，应核对该客户端实际传入的 hostname、address、port、known_hosts 文件和别名支持情况。

### 服务器地址变化

域名解析到新地址而 host key 不变时，`CheckHostIP no` 的 OpenSSH 客户端若仍由 hostname 条目命中，通常不需要补 IP 记录。只有实际按地址查找的客户端，才需要相应的地址条目。

`ssh-keyscan` 可以采集网络端当前提供的公钥和指纹：

```bash
ssh-keyscan -t ed25519 host.example 2>/dev/null | ssh-keygen -lf -
```

它不能证明该 key 真实属于目标服务器；能截获网络的攻击者也能替换扫描结果。通过云控制台、服务器本地控制台或另一条可信渠道核对指纹后，才能把这次采集到的同一 key 写入 `known_hosts`。[`ssh-keyscan(1)`](https://man.openbsd.org/OpenBSD-7.5/ssh-keyscan.1)明确要求带外核验，或仅在已信任网络中直接使用其输出。

### 主机密钥变化

`REMOTE HOST IDENTIFICATION HAS CHANGED` 表示现有记录与本次服务器 key 不同。服务器重装、主动轮换 host key、域名切到另一台机器都可能触发；中间人攻击产生相同现象。

处理顺序是：

1. 从可信带外渠道取得新 key 指纹并核对变更原因。
2. 删除确认已失效的 hostname 条目；只有确实存在地址条目时才一并删除。
3. 重新连接并接受已核验的新 key。

```bash
ssh-keygen -R host.example
ssh-keygen -R 192.0.2.10
ssh -o StrictHostKeyChecking=accept-new host.example
```

`accept-new` 只自动接受首次出现的 key，仍会拒绝已存在但不匹配的 key。重新信任后，再用 `ssh-keygen -F` 和带外指纹核对最终记录。

## 连接复用与转发

连接复用减少重复握手，端口转发则在一条 SSH 连接上承载额外流量。两者共享连接生命周期；已有 master 不会自动吸收后来修改的配置。

### <a id="controlmaster"></a>ControlMaster 连接复用

ControlMaster 让多个会话共享同一条已认证的网络连接。`ControlPersist` 可以在初始会话退出后保留 master 一段时间。

控制 socket 的目录应只允许当前用户写入，路径用 `%C` 避免不同目标冲突并缩短文件名：

```bash
mkdir -p -m 700 ~/.ssh/control
```

```sshconfig
Host host.example
    ControlMaster auto
    ControlPath ~/.ssh/control/%C
    ControlPersist 10m
```

[`ControlMaster`、`ControlPath` 和 `ControlPersist`](https://man.openbsd.org/OpenBSD-7.5/ssh_config.5)的完整语义由 OpenSSH 定义。查看或关闭现有 master：

```bash
ssh -O check host.example
ssh -O exit host.example
```

master 建立时已经固化了认证、转发和 agent forwarding 等连接级配置。修改 `RemoteForward` 或其他连接级选项后，应关闭旧 master 再重新连接。

Windows OpenSSH 当前没有实现 ControlMaster；相关功能请求仍在 [Win32-OpenSSH #1328](https://github.com/PowerShell/Win32-OpenSSH/issues/1328)。在 Windows 上不应照搬依赖 Unix control socket 的配置。

### RemoteForward 反向转发

`RemoteForward` 在远端创建监听入口，并把收到的连接通过 SSH 隧道送到本地目标。例如把本地代理只暴露给远端回环地址：

```sshconfig
Host host.example
    RemoteForward 127.0.0.1:<remote-port> 127.0.0.1:<local-proxy-port>
    ExitOnForwardFailure yes
```

`ExitOnForwardFailure yes` 让初始监听建立失败直接导致 SSH 连接失败，避免隧道失效而主连接仍表面成功。远端交互 shell 可以指向该入口：

```bash
export http_proxy=http://127.0.0.1:<remote-port>
export https_proxy=http://127.0.0.1:<remote-port>
```

systemd service 和其他非交互进程不读取交互式 `.bashrc`，应从自己的 unit 或受控环境来源取得代理变量。代理需要凭据时，凭据应来自受限的 secret/environment 机制，不能写进共享文档、仓库或命令输出。

隧道随承载它的 SSH 连接结束；ControlPersist 可以延长 master 的存活时间。修改转发配置后，先按 [ControlMaster 连接复用](#controlmaster)关闭旧 master。远端端口占用会导致 bind 失败，可用 `ss -ltnp` 查监听者。

两端监听地址需要与实际地址族一致。显式写 `127.0.0.1` 可避免 `localhost` 解析为 `::1`、而目标服务只监听 IPv4 时的歧义。

## 远端命令与文件操作

普通 SSH 足以完成命令执行和文件传输。若环境已有带哈希冲突检测的远端编辑能力，直接使用该能力；否则用 SSH/SFTP 拉取、修改和回传，保持每一步可检查。

### 命令执行

单条命令可以直接执行：

```bash
ssh host.example '<command>'
```

多个彼此独立、需要逐步判断结果的命令应分开运行；固定且不可分割的多步流程可写成本地脚本后一次传入远端。频繁调用可以复用 [ControlMaster](#controlmaster)，无人值守探针则配合 `BatchMode=yes`，避免卡在密码、passphrase 或 host key 提示上。

### 需要 TTY 的 sudo

`sudo` 常从 TTY 读取密码，普通非交互 SSH 命令无法完成这类提示。简单操作可以分配伪终端：

```bash
ssh -t host.example 'sudo <command>'
```

复杂操作可在本地准备一份可审阅脚本，并让脚本把输出写入固定日志：

```bash
exec > >(tee /tmp/remote-job.log) 2>&1
```

随后传输、用一次 TTY 执行，并拉回日志：

```bash
scp /tmp/remote-job.sh host.example:/tmp/
ssh -t host.example 'sudo bash /tmp/remote-job.sh'
scp host.example:/tmp/remote-job.log /tmp/
```

密码和 passphrase 不应放进命令参数、脚本正文或对话日志；需要自动化提权时，应使用环境已有的受控凭据通道。

### 日志与文件传输

日志和产物可以用 `scp` 或 SFTP 拉回本地分析：

```bash
scp host.example:/var/log/example.log /tmp/
```

大文件或易中断链路使用支持断点续传、校验或增量同步的传输方式，并在传输后核对大小或哈希。

### 复杂文件编辑

远端已有哈希保护的 patch 能力时，用它检测并发修改。否则先下载文件，在本地用可审查的编辑工具修改，再上传回原位置；上传前后核对权限、所有者和内容哈希。简单且明确的单行追加或替换才适合直接通过 SSH 执行，复杂变换不要埋进难以审查的内联 `sed`/`awk`。

## sshd 服务端

这一部分只解释 `sshd` 的进程模型和配置生效方式。`PasswordAuthentication`、`PermitRootLogin`、`PubkeyAuthentication` 等服务端加固策略由 `vps-maintenance` skill 处理。

### <a id="sshd-privsep"></a>进程模型与特权分离

普通系统服务形态下，主监听 `sshd` 通常以 root 运行，以便读取 host key、认证并切换到登录用户。每条连接会派生独立进程，认证前后的高风险网络处理和特权操作被拆到不同权限边界；登录会话最终以目标用户运行。[OpenSSH `sshd(8)`](https://man.openbsd.org/OpenBSD-7.5/sshd.8)说明了每连接派生进程及 SIGHUP 重载行为。

```bash
ps -eo user,pid,ppid,args | grep '[s]shd'
```

常见进程树形态如下，具体标签随版本变化：

```text
root    sshd: /usr/sbin/sshd -D [listener]
root    sshd: <user> [priv]
<user>  sshd: <user>@pts/0
```

systemd socket activation 会把监听 socket 的创建交给 systemd，调试模式或特定单用户部署也可能改变树形；是否正常应结合 unit、启动参数和实际权限判断，不能只套进程名模板。

### <a id="sshd-reload"></a>配置重载与服务重启

改配置前先确认发行版服务名、reload 实现和进程杀伤范围：

```bash
systemctl show ssh -p ExecReload -p KillMode -p MainPID
systemctl is-active ssh.socket
```

Debian/Ubuntu 常用服务名 `ssh`，RHEL 系常用 `sshd`。较新系统可能启用 `ssh.socket`；此时监听 socket 的生命周期还涉及 socket unit。

| 操作 | 常见行为 | 需要核对 |
|---|---|---|
| `reload` | 校验配置后向主进程发送 SIGHUP；新连接读取新配置 | `ExecReload` 是否包含 `sshd -t` |
| `restart` | 停止并重新启动 service | `KillMode`、socket activation 以及是否保留已派生会话 |

OpenSSH 收到 SIGHUP 会重新执行主 daemon 并重读配置，已建立连接由各自进程继续处理。认证选项在新连接的认证阶段生效，不会回溯改变已建立会话。

先校验再 reload：

```bash
sudo sshd -t
sudo systemctl reload ssh
```

> 实测 Ubuntu 24.04 / OpenSSH 9.6 的 `ssh.service`，`ExecReload` 会先运行 `sshd -t` 再发送 HUP，`KillMode=process`。这只是该发行版 unit 的行为；其他系统以 `systemctl show` 输出为准。
