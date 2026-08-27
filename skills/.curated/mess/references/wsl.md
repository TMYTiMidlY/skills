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

