# 网络与远程连接

## 远程连接方式

- **RDP**：通过异地组网（EasyTier / Tailscale / ZeroTier / 蒲公英等）连接远程桌面。Windows 用 `mstsc`，Linux 用 `xfreerdp` 或 Remmina
- **向日葵**：不需要组网，默认自动判断传输模式——网络条件允许时自动 P2P 直连，否则走服务器中转

### 会话管理

```powershell
tsdiscon        # 断开 RDP 连接，程序继续运行（服务器场景常用）
logoff          # 完全退出登录，关闭所有程序
```

### RDP 缩放不生效

在 PowerShell 中执行 `logoff`，然后重新连接即可。

## WSL Mirror 模式网络

Mirror 模式的 WSL 会同步宿主机所有网卡，包括蒲公英、EasyTier 等虚拟网卡。

正常状态下 `ip route show` 以此开头：

```
default via <gateway-ip> dev eth1 proto kernel metric 25
```

### Clash Party 代理对路由的影响

#### 系统代理模式

`ip route show` 结果不受影响。需要手动设置环境变量才能让 `curl` 走代理：

```bash
export http_proxy="http://127.0.0.1:7890"
export https_proxy="http://127.0.0.1:7890"
```

注意：`ping` 走 ICMP 协议，不经过 HTTP 代理，始终不通是正常的。

#### 虚拟网卡模式（TUN）

开启后 `ip route show` 会出现大量细分路由，以此开头：

```
0.0.0.0/2 via 198.18.0.2 dev eth8 proto kernel
```

所有流量会被 TUN 网卡接管。

### 异常修复

- **HTTPS 无法访问**：HTTP 正常但 HTTPS 不通，修改 Clash 虚拟网卡的模式（如切换 TUN stack），无需 exit WSL，立即生效
- **轻量修复**：`exit` 退出后重新 `wsl` 进入，刷新路由表
- **完全重启**：在 PowerShell 中执行 `wsl --shutdown`，然后重新 `wsl`

如果 WSL 内只剩 `lo` 网卡、`ip route` 没有默认路由、`/etc/resolv.conf` 缺失或 DNS 报 `Temporary failure in name resolution`，通常是 WSL VM 网络层异常；本机实测 `wsl --terminate Ubuntu` 后仍只有 `lo`，`wsl --shutdown` 后才恢复 eth 网卡、默认路由和 DNS。遇到这种状态时，明确告知会影响 Docker Desktop / 其他 WSL 发行版，然后用 `wsl --shutdown` 重建整个 WSL2 VM 网络。

### Docker Desktop 与 `wsl --shutdown`

`wsl --shutdown` 的语义是立即终止所有运行中的 WSL 发行版并关闭 WSL2 lightweight VM，不是只重启默认发行版。因此 Docker Desktop 使用 WSL2 backend 时，`docker-desktop` 发行版也会被停止，正在运行的容器可能中断。

Docker Desktop 的 WSL2 backend 使用自己的 `docker-desktop` WSL 发行版运行 Docker Engine，并可为用户发行版开启 WSL integration。Docker Desktop GUI 或后台服务仍在运行时，可能在 `wsl --shutdown` 后很快重新拉起 `docker-desktop` 或集成的发行版，所以观察 `wsl -l -v` 时会感觉“shutdown 没生效”或“Docker 没停”。需要判断 WSL VM 是否真的重启过时，可在重启前后对比 Linux boot id：

```powershell
wsl -d Ubuntu -- cat /proc/sys/kernel/random/boot_id
wsl --shutdown
wsl -d Ubuntu -- cat /proc/sys/kernel/random/boot_id
```

两次 boot id 不同说明 WSL VM 已重启；相同则说明没有发生同一次 Linux 内核实例的重启。排障顺序：

1. 只修某个发行版的普通进程/挂载/用户态异常时，可先用 `wsl --terminate Ubuntu`，避免影响 Docker Desktop。
2. 发行版内只有 `lo`、没有 eth 网卡和默认路由时，使用 `wsl --shutdown`；执行前提醒 Docker/容器会被停一次。
3. 若不希望 Docker Desktop 自动重新拉起 WSL，先退出 Docker Desktop，再执行 `wsl --shutdown`。

参考：

- Microsoft WSL basic commands: `wsl --shutdown` terminates all running distributions and the WSL2 VM.
- Docker Desktop WSL2 backend: Docker Desktop uses a `docker-desktop` WSL distribution for the Docker engine.
- Docker Resource Saver on WSL: Resource Saver does not stop the whole WSL VM because it is shared by all WSL distributions.

## VS Code serve-web

在当前机器启动一个 VS Code Web 服务，适合临时从浏览器访问这台机器上的开发环境。需要终端一直挂着这个命令；重启或终端关闭后要手动重新执行。

Windows 侧临时服务示例（端口可换，下例用 `18080`）：

```powershell
code serve-web --host 0.0.0.0 --port 18080 --without-connection-token
```

`--without-connection-token` 表示不要求访问 token；**只适合已经有内网、VPN、反代认证等外层保护的场景**——服务直接暴露到公网时务必去掉这个开关或额外加层。

WSL 默认是 NAT 网络，常见的远程访问链路是：

```text
远端 Caddy/Nginx -> Windows EasyTier IP:<port>
Windows portproxy -> 127.0.0.1:<port>
WSL localhost forwarding -> WSL 内服务
```

`portproxy` 配置细节见下文「WSL / Docker 服务暴露（入站：portproxy + wslrelay）」一节；`portproxy` 不会自动唤醒 WSL，建议留一个 WSL 窗口 / 会话挂着，避免发行版被停掉后远端反代直接 502。

排障常用查询：

```powershell
wsl -l -v
wsl -- ip route show
wsl -- ss -ltnp
netsh interface portproxy show all
netstat -ano | Select-String -Pattern ':<port>'
curl.exe -k -I https://127.0.0.1:<port>/
```

## WSL NAT 下出站走 Mihomo / fake-ip

> Mihomo / Clash 本身的配置、REST API、节点/协议选型、TUN 路由规则见 [mihomo.md](mihomo.md)；本节只讲 WSL NAT 流量怎么进 Windows 宿主的 Mihomo。

在无法使用 WSL Mirror / mirrored networking、必须继续使用 WSL NAT 时，不要假设 Windows 宿主能走 Mihomo TUN 就等于 WSL 裸 TCP 也会被稳定接管。更稳的做法是：WSL 内的 HTTP 类工具显式走 Windows 宿主 `mixed-port`，SSH 等不读代理环境变量的工具单独配置 `ProxyCommand`。

典型现象：

- Windows PowerShell `Test-NetConnection <ip> -Port <port>` 成功，`InterfaceAlias` 显示 `Meta`。
- WSL 里 `curl`、`ssh`、`nc` 对同一目标超时，卡在 TCP connect 阶段，还没到 TLS/SSH 握手。
- WSL DNS 解析域名得到 `198.18.x.x`，说明 Mihomo `fake-ip` 已生效；但 WSL 到这些 fake-ip 的 TCP 流量可能没有稳定进入 TUN 映射。
- 同一域名或目标有时成功、有时超时，通常是 fake-ip/TUN 映射链路不稳定，不要直接判断为远端服务故障。

快速判断：

```bash
# WSL 看到的 Windows 宿主网关
ip route get <target-ip>

# WSL 直连目标
nc -vz -w 6 <target-ip> <port>

# WSL 是否能访问 Windows 宿主上的 mixed-port
nc -vz -w 4 <wsl-gateway-ip> 7890

# WSL 显式走 Windows 宿主 Mihomo SOCKS
nc -vz -w 8 -x <wsl-gateway-ip>:7890 -X 5 <target-ip> <port>
curl -I --connect-timeout 5 --max-time 8 --proxy socks5h://<wsl-gateway-ip>:7890 https://www.google.com
```

Windows 宿主侧对照：

```powershell
Test-NetConnection <target-ip> -Port <port>
```

如果 Windows 成功、WSL 直连超时、WSL 走 `<wsl-gateway-ip>:7890` 成功，说明问题在 **WSL NAT 裸流量进入 Windows TUN 的透明接管路径**，不是远端目标或节点不可用。

`<wsl-gateway-ip>` 通常是 WSL 默认路由的网关，例如：

```text
<target-ip> via 172.28.80.1 dev eth0 src 172.28.94.43
```

这里 `172.28.80.1` 是 WSL NAT 网络里 Windows 宿主的地址。它可能在 `wsl --shutdown`、网络重置、虚拟网卡重建后变化；需要写入 shell 配置时，优先动态读取：

```bash
if command -v ip >/dev/null 2>&1; then
    WSL_HOST_IP="$(ip route show default 2>/dev/null | awk '{print $3; exit}')"
    if [ -n "$WSL_HOST_IP" ]; then
        export ALL_PROXY="socks5h://${WSL_HOST_IP}:7890"
        export all_proxy="socks5h://${WSL_HOST_IP}:7890"
        export HTTPS_PROXY="http://${WSL_HOST_IP}:7890"
        export https_proxy="http://${WSL_HOST_IP}:7890"
        export HTTP_PROXY="http://${WSL_HOST_IP}:7890"
        export http_proxy="http://${WSL_HOST_IP}:7890"
    fi
    unset WSL_HOST_IP
fi
```

这些代理环境变量能稳定覆盖 `curl`、`git` HTTPS、`npm`、`pip`、`uv` 等大量 HTTP 客户端，但不是透明全局代理。`ssh` 默认不读 `ALL_PROXY`，需要单独配：

```sshconfig
Host <name>
  HostName <target-ip-or-domain>
  User <user>
  ProxyCommand nc -x <wsl-gateway-ip>:7890 -X 5 %h %p
```

## WSL / Docker 服务暴露（入站：portproxy + wslrelay）

> 方向区分：本节是 **Windows / EasyTier / 远端入口 -> WSL 内服务**（入站）。WSL 出站流量走 Mihomo 的部分在上面的 [WSL NAT 下出站走 Mihomo / fake-ip](#wsl-nat-下出站走-mihomo--fake-ip)，两者互不相干。

WSL NAT 下，要把 WSL 内服务暴露给 Windows / EasyTier / 远端反代，需要 Windows `netsh interface portproxy` 做 TCP 转发：它把 Windows 宿主某个监听地址和端口转到 WSL 内服务。`portproxy` 不负责让 WSL 出站走 Mihomo，也**不支持 UDP**。

```powershell
# 示例：Windows 在 <windows-listen-ip>:18080 监听，转发到 WSL localhost:18080
netsh interface portproxy add v4tov4 `
  listenaddress=<windows-listen-ip> listenport=18080 `
  connectaddress=127.0.0.1 connectport=18080

netsh interface portproxy show all
```

**推荐 `connectaddress=127.0.0.1`**（靠 wslrelay 的 localhost forwarding），而非 WSL NAT IP——NAT IP 会随 WSL 重启变化、不稳。配套：WSL 内服务也监听 `127.0.0.1`（纯 v4）——docker 写 `127.0.0.1:N:N`、native 服务 listen `127.0.0.1`，别用 `::`（避免 #14154 的 dual-stack v6 形态，见下）。

### wslrelay / IPv6 dual-stack 坑（#14154）

**症状**：portproxy 表正确建立，从 Windows 或 EasyTier 远端 TCP 能 connect，但请求一发出立刻 `Connection reset by peer` / `Recv failure: Connection was reset`（TCP **RST**，下文同——对方在 TCP 层主动拆掉连接），或直接 `Failed to connect`。

**根因（坐实）**：[microsoft/WSL#14154](https://github.com/microsoft/WSL/issues/14154) — "Dual-mode IPv6 sockets do not accept IPv4 connections via localhost"，**open** 状态、`network` label、2026-02 提交、2026-05 仍在更新（数月未修）。issue 里 distro 内部 `curl -4 http://localhost:N` 就已经 refused，跨 wslrelay 到 Windows 必然继承同样症状。

**和 Docker Desktop 无关、native dockerd 一样踩**：实测一台 WSL 内 systemd 起的 native dockerd（非 Docker Desktop），bare `ports: 9000:9000` 时 docker-proxy 默认开 dual-stack v6 socket，照样 RST。原文档把这段写成"Docker Desktop 容器端口的 wslrelay/IPv6 坑"是窄了。

#### WSL 里的 socket 形态 → wslrelay 实际行为

| WSL 里 `ss -tlnp` 显示 | family | `IPV6_V6ONLY` | wslrelay 在 Windows 这边建 | 实测结果 |
|---|---|---|---|---|
| `127.0.0.1:N` 纯 v4 | AF_INET | n/a | `127.0.0.1:N` (v4) | ✅ 通（**推荐**） |
| `0.0.0.0:N` 纯 v4 | AF_INET | n/a | `127.0.0.1:N` (v4) | ✅ 通 |
| `[::]:N` 纯 v6 | AF_INET6 | 1 | `[::1]:N` (v6) | 一致；v4 client refused |
| `*:N` dual-stack v6 | AF_INET6 | **0** | **只建 `[::1]:N`，不补 v4** | ❌ portproxy `connectaddress=127.0.0.1` → RST |

第三行就是 #14154 的形态。原因（这部分是推测）：wslrelay 看 socket family 为 v6 就照镜子建一个 v6 listener，没读 `IPV6_V6ONLY=0` 这个 bit，所以漏掉了对应的 v4 listener。

#### 端到端链路（NAT 模式 + EasyTier + WSL distro）

```
[EasyTier peer (e.g. <mesh peer> <mesh-peer-IP>)]
            ↓ TCP
[Windows host kernel + EasyTier wintun]                受 <mesh 子网> 路由
            ↓
[svchost.exe / iphlpsvc] LISTEN <Windows机 mesh IP>:9000    ← netsh portproxy 这条
            ↓ connectaddress=127.0.0.1 connectport=9000
[wslrelay.exe]           LISTEN 127.0.0.1:9000        ← Microsoft 官方进程，NAT 模式触发
            ↓ Hyper-V vsock
[WSL distro socket]      0.0.0.0:9000 / *:9000        ← 必须是纯 v4 才不触发 #14154
            ↓
[Docker bridge / process]
```

两个组件都不能省、互不感知：

- `netsh portproxy` 由 Windows `iphlpsvc` 承载，只是个通用 TCP 转发表，**不知道 WSL 存在**；它需要 connectaddress 那端有人接，正好 `127.0.0.1` 那端是 wslrelay 在 listen。
- `wslrelay.exe` 是 WSL2 NAT 模式的 localhost forwarding 实现，**只在 Windows host 的 `127.0.0.1` / `[::1]` 上 listen**，不会 listen 任意 host IP（如 EasyTier 的 `<Windows机 mesh IP>`）。
- `.wslconfig` 里 `hostAddressLoopback=true` 容易让人误以为是"让 host IP 也能 forward 进 WSL"——**不是**。它的方向是反的：让 WSL 进程能通过 host IP 访问 host loopback service。见下面实测。

#### 实测：删掉 portproxy、靠 wslrelay 单独扛行不行（结论：不行）

测试机 `.wslconfig`：`hostAddressLoopback=true`（已开）、`networkingMode` 默认 NAT。删 portproxy `<Windows机 mesh IP>:9000 → 127.0.0.1:9000` 那一条，其他 14 条保留。

| 测试 | baseline | 删 portproxy 后 |
|---|---|---|
| netsh portproxy 表里 9000 | ✅ 在 | ❌ 已删 |
| Windows 这边 listen 127.0.0.1:9000 | wslrelay | wslrelay（不变） |
| Windows 这边 listen <Windows机 mesh IP>:9000 | svchost | ❌ 无人 listen |
| Windows → 127.0.0.1:9000 | 200 | **200** |
| Windows → <Windows机 mesh IP>:9000 | 200 | ❌ refused 2s 立刻 |
| mesh peer A → <Windows机 mesh IP>:9000 | 200 | ❌ timeout 5s |
| mesh peer B → <Windows机 mesh IP>:9000 | 200 | ❌ timeout 5s |

结论：

- wslrelay **始终只在 `127.0.0.1` listen**，不会自动 listen mesh IP；`hostAddressLoopback=true` 不改变这件事。
- NAT 模式下，要让 host 网卡 / 虚拟网卡 (EasyTier wintun) 的 IP 上某个端口能进 WSL distro，**netsh portproxy 这一跳无法省**。
- 删 portproxy 后立即 `Could not connect`（不是 RST、不是 timeout-after-handshake），印证那个 IP 上根本没有 listener。

#### 辨识与修复

辨识：

```bash
# WSL 里
ss -tlnp | grep :<port>
#  127.0.0.1:<port> / 0.0.0.0:<port>  → 纯 v4，没问题（推荐用 127.0.0.1）
#  *:<port>        → dual-stack v6（#14154 形态）
#  [::]:<port>     → 纯 v6（v4 client 也会 refused，但形态不同）
```

```powershell
# Windows
Get-NetTCPConnection -State Listen -LocalPort <port> | Format-Table LocalAddress,LocalPort,OwningProcess
# 看 127.0.0.1 那一行进程是不是 wslrelay；如果只有 [::1] 没有 127.0.0.1
# 而且 listenaddress=<host-ip> 的 portproxy 配过了仍 RST，几乎可以确认 #14154

# 直接验证 Windows 侧 [::1] 是否能接连接（#14154 形态下通常 RST）：
curl.exe --noproxy * -v --max-time 5 "http://[::1]:<port>/"
```

修复（按推荐度）：

1. **显式 v4 监听地址**（首选，零代价）：
   - Docker / docker-compose：**推荐写 `ports: ["127.0.0.1:9000:9000"]`**，不要 bare `"9000:9000"`（bare 让 docker-proxy 选 dual-stack v6 socket，触发 #14154）。显式写 v4 host IP `127.0.0.1` 即纯 v4，不踩坑。
   - 服务直接 listen：**推荐 listen `127.0.0.1`**，不要用 `::`。Python `http.server` 默认 v4，Go `net.Listen("tcp", ":N")` 默认 dual-stack v6，要写 `net.Listen("tcp4", "127.0.0.1:N")`。
   - **Java / JVM 服务**（Neo4j / Elasticsearch / Kafka / Spark 等）：JVM 默认开 dual-stack v6，**即使配置文件写 `listen_address=0.0.0.0` 也会落到 `*:N` 形态**（socket 是 AF_INET6 + V6ONLY=0，恰好是 #14154 触发点）。fix 是加 JVM flag `-Djava.net.preferIPv4Stack=true` 强制纯 v4 socket。**Neo4j 5.x apt 包实测**：编辑 `/etc/neo4j/neo4j.conf`，把 `#server.bolt.listen_address=:7687` 取消注释改成 `server.bolt.listen_address=0.0.0.0:7687`，再追加一行 `server.jvm.additional=-Djava.net.preferIPv4Stack=true`，`systemctl restart neo4j` 之后 `ss -tlnp` 从 `*:7687` 变 `0.0.0.0:7687`，wslrelay 看到纯 v4 listener 才会在 Windows 端补 `127.0.0.1:7687` 的 v4 listener，portproxy `connectaddress=127.0.0.1` 这条才不会 RST。**单改 `listen_address=0.0.0.0` 一行不够**，必须同时给 JVM 加 preferIPv4Stack=true。（listen 用 `127.0.0.1` 或 `0.0.0.0` 都是纯 v4、等效；上面是当时实测的 `0.0.0.0` 原值，关键是 `preferIPv4Stack`。）
2. **portproxy `connectaddress` 指 WSL eth0 IP**（跳过 wslrelay 走 NAT）——**不推荐**：eth0 IP 随 WSL 重启变化、不稳；优先第 1 条（服务监听 `127.0.0.1` + `connectaddress=127.0.0.1`）。
3. **portproxy 改用 `v4tov6` 转 `::1`**：理论可行，但实测在不少 WSL 版本上 wslrelay 的 `[::1]` listener 也 RST，所以不一定通。作为快速试探可用，长期不推荐。
4. **切 `networkingMode=mirrored`**（Win11 22H2+）：彻底没 wslrelay。代价是重排所有 portproxy + 评估对 EasyTier wintun 路由优先级的影响。
5. **WSL 内补 socat v4 relay**：`socat TCP4-LISTEN:<port>,reuseaddr,fork,bind=0.0.0.0 TCP:[::1]:<port>`，让 wslrelay 看到的是纯 v4 listener。多一跳进程，仅作 fallback。

#### 全双工大流量下 wslrelay 死锁（#10688）

[microsoft/WSL#10688](https://github.com/microsoft/WSL/issues/10688)（open，与上面 #14154 不同）：WSL 本地转发（Linux 侧转发进程 + `wslrelay.exe`）用**单个阻塞线程同时拷贝一条连接的两个方向**（半双工逻辑）；双向同时大流量时两端缓冲填满、relay 卡在 `write()` 上不再读另一边 → 永久死锁。诊断特征（`ss -tn`，卡死的 socket 对收发队列堆住、流量永久冻结）：

```
State  Recv-Q   Send-Q     Local Address:Port     Peer Address:Port
ESTAB  0        2914479    127.0.0.1:<svc>        127.0.0.1:<relay>
ESTAB  3176712  0          127.0.0.1:<relay>      127.0.0.1:<svc>
```

本机实测（NAT 模式，Windows `127.0.0.1` → wslrelay → WSL；原生 + docker、bind `0.0.0.0` + `127.0.0.1` 共四种发布形态）：

| 流量模式 | 结果 |
|---|---|
| 单向下行 / 单向上行（任意大小） | 不卡 |
| 严格乒乓请求/应答（半双工，HTTP/1.1 形态） | 不卡 |
| HTTP/1.1 下载 100MB（`curl.exe`） | 不卡 |
| 真 SSH 全双工 ↓200MB + ↑100MB（`ssh.exe`） | 不卡 |
| 合成程序双向并发 blast（不积极收 socket，本机 ~0.65MB 起） | **卡死** |

- **只有全双工双向大流量才可能触发**；任何半双工（单向 / 乒乓 / HTTP 下载）都不触发。
- **真实程序（SSH、HTTP）实测不中招**，无论多大；只有"不积极收 socket"的朴素 blast（如 issue 的合成 reproducer）才稳定复现。
- **与发布地址无关**：四种发布形态阈值完全一致（本机 `route_localnet=0`，两种 docker 形态都经 docker-proxy，回环路径相同）。
- 彻底规避：切 `networkingMode=mirrored`（无 wslrelay）。`connectaddress=127.0.0.1` 仍按上文推荐（理由是不漂移，与本坑无关）。

历史背景与 issue：[microsoft/WSL#14154](https://github.com/microsoft/WSL/issues/14154) (open)、[#10688](https://github.com/microsoft/WSL/issues/10688) (open，wslrelay 全双工 hang)；类似 v4/v6 困扰在 WSL repo 里有十几个独立 issue，labels 多数 `network`。

#### EasyTier + 远端 Caddy 的入站稳定方案

WSL NAT + Windows EasyTier + 远端 Caddy 的简单稳定方案：

```text
远端 Caddy reverse_proxy -> Windows EasyTier IP:port
Windows portproxy -> 127.0.0.1:port
WSL 服务监听 127.0.0.1，由 Windows localhost forwarding (wslrelay) 转发访问
```

`netsh interface portproxy` 是 TCP 转发，不支持 UDP。WSL NAT 下**推荐 `connectaddress=127.0.0.1`**（配套服务监听 `127.0.0.1`），而非 WSL NAT IP——NAT IP 会随 WSL 重启变化。批量检查：

```powershell
netsh interface portproxy show all
```

从云服务器探测 TCP 时，避免用 Bash `/dev/tcp/...` 形式；这类命令容易被云安全产品识别为反弹 shell 特征。HTTP(S) 端口优先用：

```bash
curl -k -I --connect-timeout 5 --max-time 8 https://<target>:<port>/
```

## EasyTier / WSL 组网杂项

### MTU 问题（WSL 内组网，已弃用）

曾在 WSL 内部署 EasyTier 时遇到过 MTU 不匹配问题——必须手动降低 EasyTier 的 MTU 以匹配 WSL 网卡的 MTU。

**当前方案**：不再在 WSL 内配置组网，EasyTier 运行在 Windows 宿主机上，避免了此问题。

## Hysteria2 服务端搭建（落地侧，独立 systemd 服务）

> 这块是**服务端落地**：在一台 VPS 上把 Hysteria2 作为**独立服务**跑起来（不经 3x-ui 面板）。客户端怎么配、怎么测吞吐 / 验证 Brutal、DNS/WebRTC 泄漏排查见 [mihomo.md](mihomo.md)；服务端 `ignoreClientBandwidth`/`bandwidth` 如何影响客户端 Brutal 也在 mihomo.md。想在 **3x-ui 面板里加 Hysteria2 inbound**（而非独立服务），以及带宽 / 丢包质量测试，见 `vps-maintenance` skill。

在已有 `VLESS + WS + TLS + Caddy + 3x-ui/Xray` 节点时，Hysteria2 适合作为差异化备用：它走 QUIC/UDP，和 TCP 443、Caddy 反代、WebSocket 不是同一条链路。不要为了“稳定”把 VLESS 换成 VMess；更优先考虑增加不同协议或不同服务商/地区的备用。

服务端优先按 Hysteria2 官方脚本安装，并让它独立监听 UDP 端口，避免改动现有 Caddy/3x-ui：

```bash
HYSTERIA_USER=root bash <(curl -fsSL https://get.hy2.sh/)
```

如果服务器已由 Caddy 管理证书，不要直接让 systemd 服务读取 Caddy 私有证书目录；`NoNewPrivileges` / capability 限制可能导致 root 服务也报 `tls.cert: permission denied`。更稳的做法是复制当前证书到 `/etc/hysteria/`，配置 Hysteria2 读取 root-owned 副本：

```yaml
listen: :<udp-port>

tls:
  cert: /etc/hysteria/<domain>.crt
  key: /etc/hysteria/<domain>.key

auth:
  type: password
  password: <random-password>

obfs:
  type: salamander
  salamander:
    password: <random-obfs-password>
```

同时放行 UDP 端口，并提醒用户云厂商安全组也要放行：

```bash
sudo ufw allow <udp-port>/udp
sudo systemctl enable --now hysteria-server.service
sudo systemctl status hysteria-server.service
```

验证时看三处：

- `systemctl status hysteria-server.service`
- `ss -lunp | grep <udp-port>`
- 客户端/Mihomo 的节点 delay

若复制 Caddy 证书，后续要补证书同步和重启机制，避免 Caddy 续期后 Hysteria2 继续使用旧副本。

