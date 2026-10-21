# WSL2 疑难杂症

> WSL2 与 Windows 宿主共享或代理网络栈时产生的怪现象，以及 WSL 里 `systemd --user` 的故障。共同点是：在 WSL 内部单看查不出原因，必须把宿主机侧一起纳入观测。

## <a id="host-ok-wsl-fail"></a>同机 Windows 宿主能连自建服务、内嵌 WSL 连不上

> 2026-06-20 | Mihomo TUN（fake-ip，跑在 Windows 宿主）| WSL2 NAT (Ubuntu) | 自建 Forgejo 内置 SSH `:222`，公网经阿里云 socat 中转 + EasyTier mesh

> 记录原则：只记客观现象与实测值，**根因未坐实，不强行归因**。

### 症状

- 目标 `ssh.git.<自建域名>:222`（自建 Forgejo 内置 SSH）。该域名 DNS：外部机器解析真实 IP `<公网 IP>`；**1810 这台（Windows 宿主 + 内嵌 WSL）解析为 Mihomo fake-ip `198.18.x`**。
- 多设备 `ssh -T git@…:222` / `git fetch` 实测：
  - 本机 Ag-Workstation（也有 Mihomo，但解析真实 IP）✅；RackNerd / BSCC-M9 / Mac-mini（外部）✅
  - **1810 Windows 宿主机（解析 fake-ip）✅** —— `ssh.exe -T` 回 `Permission denied (publickey)`，即端点已连通
  - **1810 WSL 本体（解析同一 fake-ip）❌** —— `Connection timed out during banner exchange`；`git fetch` 约 3/5、或 rc=124 超时
- 即「同一台物理机，Windows 宿主机连得上、内嵌 WSL 连不上」。

### 排查中的实测值

- WSL 内绕开公网的路径都正常：`ssh -p222 git@127.0.0.1`（docker-proxy→容器）3/3；`git@10.144.18.10`（mesh，被 TUN `route-exclude` 覆盖）3/3 且 0.6s → 服务端/容器本身没问题。
- WSL 强制真实 IP `git@<公网 IP>`（TUN 仍开）：1/3，仍偶发超时。
- Mihomo 运行态（宿主机 interop `curl http://127.0.0.1:9090/configs` 与 `/rules`）：
  - `tun.enable=true`、`dns-hijack:["any:53"]`、fake-ip 段在用、`route-exclude-address:["10.144.0.0/16"]`
  - 规则含 `DomainSuffix <自建域名> → 直连`（hitCount 47953）、`IPCIDR <公网 IP>/32 → 直连` —— 该域名/IP 配置即直连
- `PATCH /configs {"tun":{"enable":false}}` 关 TUN 后：WSL DNS 解析变回**真实 IP** `<公网 IP>`，WSL `ssh -T` ✅、`git fetch` rc=0。
- `PATCH … {"tun":{"enable":true}}` 重新开 TUN 后：WSL `ssh -T` **6/6**、`git fetch` rc=0（此时 DNS 仍解析 fake-ip `198.18.x`）。即开回 TUN，WSL 也通了。

### 现象小结

- 某时刻出现「WSL 不通 / 宿主机通」；把 Mihomo TUN `off→on` 切一遍后，WSL 变为稳定可通（6/6），**期间未改任何配置**（`*.<自建域名>` 自始至终是直连规则）。
- **未能坐实**「切换前为何不通、切换后为何通」的机制，仅记录这一可复现的相关性。

### 让它恢复的动作

- 经 9090 把 TUN 切一次：`curl.exe -X PATCH http://127.0.0.1:9090/configs -d '{"tun":{"enable":false}}'` 再 `-d '{"tun":{"enable":true}}'`（或在 Mihomo GUI 切 TUN 开关）。之后 1810 WSL 经 fake-ip 访问该自建服务恢复。
- TUN 无关的稳定备选（本次未采用）：把该 remote 指向 mesh `10.144.18.10:222`（被 `route-exclude` 覆盖，开不开 TUN 都 0.6s 稳）。

## <a id="periodic-outage"></a>「总是断网」：断窗恒定 ~5 分钟的周期性中断

> 2026-06-22 | WSL2 mirrored networking（eth0 直接是宿主机 LAN 段）+ 宿主机 Mihomo（系统代理，非 TUN）+ EasyTier mesh | 校园网：有线接入（认证网关是「身份认证系统」门户）+ WiFi 接入（另一网段）
>
> **较可能的根因：WSL 内跑 EasyTier**——疑似把整机网络**节律性**搞坏（断窗恒定 ~5min、标准差极小，像软件定时器而非随机弱网），且 **EasyTier 挪到 Windows 宿主机后就好了**。下面排查当时被 CoPP / 分链路假象带过弯路；机制没逐拍对死，姑且把账先记在 EasyTier 头上。

### 症状

- 体感「总是断网」。
- EasyTier 某 TCP peer 全天频繁 removed/added（一天 25+ 次），**断窗时长恒定 ~5 分钟（实测 293–337s，标准差极小）**，通期长短不一（4–11 分钟）。
- `ping 默认网关` 周期性 100% 丢包约 5 分钟；宿主机原生 `Test-Connection 网关` 同样丢。

### 做了哪些排查

1. **弯路**：一开始拿 `ping 网关` / Windows `Test-Connection 网关` 当断网指标，看到周期性 100% 丢 5 分钟就误判「整机断网」，甚至把「宿主机原生 ping 也丢」当铁证——其实那也是 ICMP。
2. 断窗时长**恒定 ~5 分钟**（标准差极小）→ 判断是定时器/超时机制，不是随机弱网（随机弱网的中断时长会从几秒到几十分钟乱分布）。
3. 排除硬件：Windows 事件日志全天有线网卡（I225-V / `e2fnexpress`）**无对应 link down/up（事件 27/32）**、网卡统计丢包/错误=0 → 物理 link 一直 UP。排除 IP 冲突（无 `Tcpip` 4198/4199）、DHCP（租约数天，非 5 分钟）。
4. **关键反转**：在 ping 网关 100% 丢包的**同一刻**，直连公网 TCP、直连校内 TCP、走代理出网**全部 OK**。→ ping 网关丢包是**网关对「发给自己的」ICMP 做控制平面限速（CoPP, Control Plane Policing）**的假象，转发平面一直正常。**`ping 网关` 根本不是可靠的断网指标**。
5. 但历史上某些断窗（WiFi 断开期）TCP 也真全断（含网关 `:80` 门户）→ 确有真实断网，只是被 ICMP 假象混淆了。
6. **决定性实测——分源 IP 绑定**：宿主机用 .NET `TcpClient` 分别 `Client.Bind(有线源IP)` 与 `Bind(WiFi源IP)`，连同一公网目标做 TCP，连续 87 次：`wired=FAIL ×87 / wifi=OK ×87`。当时据此以为**有线链路本身坏**——但这跟「WSL 内 EasyTier」并不矛盾（见下研判）。（Windows strong host model 下绑源 IP 会强制走对应接口，所以这能区分两条物理链路；Linux 等价物是 `ping -I` / `curl --interface`。）
7. 时间线：只剩有线时周期断（25 次）、**WiFi 一连上 EasyTier 立即稳**——当时读成「有线坏、WiFi 兜底」；但结合「断窗恒定 ~5min」「挪 EasyTier 出 WSL 后好」，现在更倾向是 WSL 内 EasyTier 在周期性作祟（见下研判）。

### 根因研判与残留疑点

- **较可能的元凶：WSL 内跑 EasyTier**。断窗恒定 ~5min（标准差极小）像某个周期动作/重连定时器，不像随机弱网；而且**把 EasyTier 从 WSL 挪到 Windows 宿主机后就不犯了**——这两点让它嫌疑最大。
- **那个「有线 FAIL」不构成反证**：分源 bind 在宿主机裸 TCP 测出 `wired FAIL / wifi OK`，一度让人以为「有线接入本身坏」。但 WSL2 mirrored 模式下 WSL 与宿主机共享网络栈，WSL 内 EasyTier 动路由/虚拟网卡是可能波及宿主机有线那一跳的——所以这结果跟「WSL 内 EasyTier」并不冲突，只是当时没往这想。
- **没对死的部分**：没把「EasyTier 周期动作」与「断窗」做时间对齐，这次也没试过降 EasyTier MTU——所以是倾向性判断，不是铁证。
- **相关旧坑（另一次、独立事件）**：之前在 WSL 内部署 EasyTier 还踩过 **MTU 不匹配**、要手动降 MTU 才好；后来干脆不在 WSL 内组网、EasyTier 跑宿主机。详见 `network` skill 的 EasyTier 客户端「不在 WSL 内跑 EasyTier」记录。

### 教训

1. **`ping 网关` 丢包 ≠ 断网**。网关/路由器普遍对「发给自己的」ICMP 做 CoPP 限速，忙时优先丢 ping；判断通断要用 **TCP 打真实目标**（多目标：公网 + 内网 + 代理），别只 ping 网关、更别凭「ping 网关丢」这一条下结论。
2. **多链路（有线+WiFi）会互相兜底、掩盖单链路故障**。定位「哪条链路坏」要**绑定源 IP 分别测每条链路**：Windows 用 `TcpClient.Client.Bind(源IP)`；Linux 用 `ping -I <src/iface>` / `curl --interface`。strong host model 下绑源 IP 强制走对应接口。
3. **WSL2 mirrored 模式**：WSL 网络 == 宿主机网络，WSL 内的 ICMP 假象同样会误导；要在宿主机原生侧、并用 TCP/分源去验证，别用 WSL 的 ping 下结论。
4. **断窗时长恒定（标准差小）= 定时器/超时机制**的强信号，区别于随机弱网（时长乱分布）。用 EasyTier 这类长连接服务的 peer removed/added 日志反推链路通断窗口很省事。

## <a id="user-bus-missing"></a>user session bus 消失，`systemctl --user` 连不上

> 2026-06-30 | WSL2 + `systemd --user` | 用户无 sudo | 影响 user service 管理
>
> 这条记录的重点：**恢复 bus 的方法有效，但不是无损热修**。`systemd --user` manager reexec 后，已经运行的 user services 可能会断开或重启，交互式 Web 终端一类服务需要重新打开。

### 症状

- `systemctl --user ...` 报：

```text
Failed to connect to bus: No such file or directory
```

- `XDG_RUNTIME_DIR=/run/user/1000` 正常，但 `/run/user/1000/bus` 不存在。
- `DBUS_SESSION_BUS_ADDRESS` 为空。
- `/run/user/1000/systemd/{private,notify}` 仍存在，`systemd --user` manager 仍在跑（本次为 pid `305`）。
- user services 本身还可能继续运行；因此不要只看业务端口正常就误判 user bus 正常。

### 失败路径

直接补一个 bus：

```bash
dbus-daemon --session --address=unix:path=/run/user/1000/bus --fork --print-pid
DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus systemctl --user is-system-running
```

现象：

```text
Failed to query system state: Process org.freedesktop.systemd1 exited with status 1
unknown
```

原因：新起的 bus 上没有正在运行的 `org.freedesktop.systemd1`。`systemctl` 通过 D-Bus 请求时，bus 会尝试激活一个新的 user systemd；但旧的 `systemd --user` manager 已经存在，所以新进程退出。**单独补 bus 不会让已经运行的 manager 自动接入这个 bus**。

### 恢复动作

用户在自己的终端执行以下命令（不需要 sudo）后，`systemctl --user` 恢复：

```bash
dbus-daemon --session --address=unix:path=/run/user/1000/bus --fork --print-pid
kill -RTMIN+25 305
DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus systemctl --user is-system-running
pgrep -af '<critical-user-service>'
ss -ltnp | grep -E ':<critical-port>'
```

含义：

- 第一行在 canonical path 补回 session bus socket。
- `kill -RTMIN+25 305` 对 user systemd manager 发 reexec 信号，让 manager 重执行并接入新的 bus。
- 后两行是业务服务复查示例；按现场替换成需要保护的 user services。

### 代价与恢复后观察

- `systemctl --user` 恢复成功。
- 但运行中的 user services 可能被重启 / 消失，交互式会话需要重新打开。
- 所以这不是“只补 bus、所有服务无感”的修复；它更接近一次 user manager reexec，可能影响所有 running user services。

### 操作前建议

先记录关键服务状态：

```bash
pgrep -af '<critical-user-service>'
ss -ltnp | grep -E ':<critical-port>'
ps -o pid,etimes,cmd -p 305
ls -l /run/user/1000/bus
```

如果有不能断的 Web terminal / 长连接会话，先保存现场；恢复 bus 后准备重新打开。

### 教训

- `systemctl --user` 依赖 session bus；`systemd --user` manager 还活着不代表 CLI 一定可连。
- fresh bus + `systemctl --user daemon-reexec` 不一定能修，因为它可能激活一个新的 `systemd1` 而不是让旧 manager 接入。
- 真正让旧 manager 接入 bus 的关键是 manager reexec（本次用 `SIGRTMIN+25`），但它可能让 running user services 中断。

## <a id="host-disk-full-git-zellij"></a>宿主机 C 盘满：WSL Git 空文件与 Zellij 登录异常

> 2026-10-09 | Windows 宿主 + WSL2 | Git | Zellij Web | Caddy
>
> 同环境 2026-10-17 同病复发（症状换成入口服务握手即断、502 与 ext4 EIO 团灭），见 [「组网正常却入口全断」](#vhdx-host-starvation)。

### 发生了什么

当时 Windows 宿主机的 C 盘满了，WSL 里的开发和 Web 终端接连出问题。

Git 已经把任务认领提交推到远端，本地却出现零字节的分支引用和对象文件，读不到正常的 HEAD。具体涉及 `doing/task-fa-jordan-full-range-227` 的本地引用、远端跟踪引用和一个新提交对象，HEAD reflog 尾部也出现了零字节内容。

同一时期 Zellij 的数据库出了问题。Caddy 中已经配置了 Zellij 的 session token，访问 Web 终端仍然失败。Zellij 的登录依赖应用侧 token 数据库；排查需要沿着宿主机空间、数据库状态和代理持有的会话值逐层看。

### 排查时的线索

任务认领提交的时间是 **08:39:21**，上一轮系统日志停在 **08:39:19**。到 **09:34** 再启动时，系统日志出现：

```text
EXT4-fs (sdd): recovery complete
system.journal corrupted or uncleanly shut down, renaming and replacing.
```

这些时间点与最近写入的 Git 文件损坏吻合。远端提交仍完整，后续可以从远端或健康的 clone 补回本地对象和引用。

事后复查磁盘时，WSL 的 `/` 显示约 **895 GB** 可用，而 Windows C 盘使用率仍有 **98%**，剩余约 **39 GB**。这很容易让只看 Linux 空间的排查绕远。

WSL2 的 Linux 文件系统保存在宿主卷上的 `ext4.vhdx` 中，Linux 看到的是虚拟磁盘容量；还要检查 Windows C 盘以及 VHDX 实际所在的卷。Microsoft 的 [WSL 磁盘空间说明](https://learn.microsoft.com/en-us/windows/wsl/disk-space#how-to-check-your-available-disk-space)解释了这两层容量的关系。

```bash
df -h / /mnt/c
```

### 恢复顺序

先在 Windows 侧腾出空间，确认宿主卷和 WSL 的写入恢复正常，再处理留下的文件损坏。

Git 这次有两条恢复路径：solver 用健康仓库建了独立 clone，继续远端已经认领的任务；随后另一个 agent 修复原仓库的空对象和引用，把本地状态 stash 保存后切回 main。修复后 HEAD 可以正常读取，任务分支也与已交付的远端版本一致。stash 是恢复后的保存步骤，时间为 **10:35:52**。

遇到同类 Git 故障时，先保存工作区和损坏文件，再核对远端完整 SHA，从健康来源补回对象、恢复引用。最后检查 HEAD、分支和本地改动，保留还需要继续工作的 stash。

Zellij 按同样的顺序恢复：先检查和备份 `tokens.db`，让数据库正常读写，再确认对应实例的 session token。需要更新会话时，通过该实例的登录流程取得新的 session token，更新 Caddy 使用的凭据，并按实际环境变量加载方式使其生效。最后检查 `/ws/control` 的认证和 WebSocket 升级，再打开 Web 终端。

具体操作沿用已有主题：`software` skill 的 Zellij「login token 与 session token」、`network` skill 的 Caddy「服务凭据与环境变量」。

### 留下的经验

宿主机磁盘满时，Git、应用数据库和日志可能同时出现异常。看到多个服务一起出问题，先查 Windows 宿主卷，再查 WSL 文件和应用状态。Caddy 的 session token 配置还要配合 Zellij 数据库中的有效会话记录；恢复存储后，把整条登录链路走通。

## <a id="vhdx-host-starvation"></a>「组网正常却入口全断」：WSL 服务握手即断、502 与守护进程成批死亡

> 2026-10-17 | Windows 多用户共享机 1810（EasyTier 节点 10.144.18.10）| WSL2 Ubuntu-24.04，注册在另一个 Windows 用户名下（无该用户密码）| 对外链路：入口 VPS Caddy → EasyTier mesh → Windows portproxy 10.144.18.10:6100/61000 → wslrelay → guest 内 sshd / caddy 网关
>
> 记录原则：机制链有两处（宿主盘是否瞬时见底、进程段错误与内存峰值的关系）没拿到直接证据，按事实 / 研判分开写。
>
> 同环境更早的一次同病发作（2026-10-09，症状为 Git 空对象与 Zellij token 库损坏）见 [宿主机 C 盘满：WSL Git 空文件与 Zellij 登录异常](#host-disk-full-git-zellij)。
>
> 2026-10-19 后续：常驻做法已改为属主用户 `.wslconfig` 写 `[general]` `instanceIdleTimeout=-1` + 一次性开机任务，不再挂 keepalive；做法与实测见 `software` skill 的 windows.md「对外提供服务的 WSL 常驻」。下文恢复动作第 3 条保留当时的处置原貌。

### 症状

- `ssh <wsl-别名>`（10.144.18.10:6100）：TCP 能建连，随即 `kex_exchange_identification: Connection closed by remote host`。
- 该 WSL 承载的 `*.<user>.<zone>` 域名全部 502（入口 Caddy 上游不可达）；第一反应是「它从 easytier 掉线了」。
- mesh 层正常：peer 表 p2p 直连 0% 丢包、ping 通、宿主 Windows 自己的 SSH 也正常。

### 排查与实测

1. 一条命令排除「掉线」：`easytier-cli peer` 里宿主节点在网 → 问题不在组网层。
2. portproxy 假象：`/dev/tcp` 探 6100/61000 显示「open」，但 `netstat -ano` 按 PID 看监听者全是 svchost（portproxy 本体）；portproxy 先无条件 accept 再连后端，后端拒绝就表现为握手阶段断开。**TCP 探活对 portproxy 后端没有鉴别力，要打到 banner / 应用层。**
3. 后端定位：Windows `127.0.0.1:6100/61000` 无任何监听 → wslrelay 的 localhost 转发未建立 → guest 里 sshd / caddy 已死；其余转发（Zellij Web ×3、FastAPI 等）还在，且两次探测间隔里另外两个后端陆续死——「持续阵亡」形态，指向 guest 侧系统性故障。
4. 发行版归属：`wsl --list` 只显示当前 Windows 用户的发行版（WSL 发行版按用户注册）；枚举 `Registry::HKEY_USERS\<SID>\Software\Microsoft\Windows\CurrentVersion\Lxss` 才看到全部用户的发行版 → 目标属于另一个本地用户。
5. 关键报错：以属主身份 `wsl -d <distro> -u root` 报 `getpwnam(root) failed 5`（`WSL_E_USER_NOT_FOUND`）——errno 5 = EIO，连 `/etc/passwd` 都读不出 → 文件系统层故障，不是服务没自启。
6. 法证（崩溃 boot 的 journal 尾部 + Windows 侧）：
   - 最后的内核消息：18:49 `lean` 进程 SIGSEGV → WSL 写 crash dump 失败（err 32，写路径已断）→ 19:38:40 journald 沉默；全程无 ext4 介质错误。
   - 资源形态：vmmemWSL 峰值工作集 423 GB（`.wslconfig` 上限 448 GB）；ext4.vhdx 986 GB；宿主 C: 仅剩 ~20 GB；两块物理盘 SMART Healthy、系统日志无磁盘 / NTFS 错误。

### 根因研判

三层空间模型——guest 的 df 空闲不代表有地方写：

```text
guest ext4：df 还剩 18G ─── 文件系统层，有余量
      ↓ 每写一个未分配块，VHDX 都要在宿主卷上扩张
ext4.vhdx：动态盘，按需增长、从不自动收缩
      ↓ 宿主 C: 拿不出新块时，块设备对 guest 返回 EIO（不是 ENOSPC）
ext4 进入错误态 → 正在写盘的守护进程接连死亡；纯内存服务存活
```

- 坐实：写路径先断（dump 写失败）、无介质错误、`wsl --terminate` 后重启经 journal 回放完全自愈——「后端断供」形态而非数据损坏。
- 未坐实：宿主 C: 是否瞬时见底（无直接日志证据，事后看到 22 GB）；`lean` 段错误与 423 GB 内存峰值是伴生压力，因果未分。

### 恢复动作

1. `wsl --terminate <distro>` 后重新 `wsl -d` → ext4 journal 回放 → 文件系统自愈；`systemctl reset-failed && systemctl restart ssh caddy && systemctl enable ssh caddy`。
2. 跨用户执行（拿不到属主密码时的修复通道）：
   - 走不通：给别的用户注册 S4U 计划任务——管理员直接注册、SYSTEM 代注册、XML 导入三条路全部 Access denied；`runas /savecred` 无缓存凭据。
   - 走得通：`schtasks /RU SYSTEM` 计划任务（管理员可建）→ SYSTEM 持 SeDebugPrivilege / SeAssignPrimaryTokenPrivilege，取属主用户任一常驻进程（断开会话里总有 sihost / ApplicationFrameHost 之类）的令牌，DuplicateTokenEx 后 CreateProcessAsUser 执行 `wsl -d <distro> -u root -- …`。
   - 细节：lpDesktop 不指 `winsta0\default` 时 CreateProcessAsUser 报 err=3；远端输出要么在 bash 内重定向到 `/mnt/c/...`、要么用 cmd 包一层统一落盘，否则 wsl.exe 自身的报错看不见。
3. VM 空闲自停陷阱：最后一个 wsl 客户端退出约 60 s（vmIdleTimeout 默认）后整个 VM 停机，wslrelay 转发随之消失、所有入口断——此前靠属主用户断开会话里的常驻 shell 撑着 VM，被 `--terminate` 波及。修复：以属主身份挂 detached `wsl -d <distro> -- bash -c "sleep 86400"` 当 keepalive；治本要属主用户真实登录一次。
4. 空间回收链：guest 内删冷文件（本次 30 GB）→ 属主身份 root 执行 `fstrim -v /`（trim 68 GiB）→ 宿主 C: 22 GB→54.6 GB；VHDX 文件逻辑大小不变，缩小的是 NTFS 实际占用。fstrim 只还空闲块，先删后 trim 顺序才有意义。

### 教训

- 「掉线」怀疑先用 `easytier-cli peer` 定性；portproxy 的 LISTENING 不代表后端活着，探活要打应用层。
- WSL 发行版按 Windows 用户隔离：`wsl --list` 看不到别人的，`HKU\<SID>\…\Lxss` 注册表能枚举全部。
- guest 报 EIO（errno 5）而非 ENOSPC 时，优先怀疑虚拟盘后端（宿主卷余量 / 存储栈）而不是 guest 满；`getpwnam(root) failed 5` 是文件系统层坏的信号，别去折腾用户与权限。
- 动态 VHDX 只涨不缩：删文件只改 guest 的 df；要还宿主空间必须 `fstrim`（改文件逻辑大小还需 sparse VHD 或 compact）。宿主卷余量是持续消耗品，fstrim 还回去的空间会被后续写入再吃掉。
- 对外提供服务的 WSL 发行版受 vmIdleTimeout 支配：没有常驻 wsl 客户端会话就会整体停机，需要 keepalive 会话或属主常驻登录。

