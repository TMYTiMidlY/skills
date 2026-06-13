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

`portproxy` 配置细节见下文「WSL NAT + Mihomo TUN / fake-ip」一节；`portproxy` 不会自动唤醒 WSL，建议留一个 WSL 窗口 / 会话挂着，避免发行版被停掉后远端反代直接 502。

排障常用查询：

```powershell
wsl -l -v
wsl -- ip route show
wsl -- ss -ltnp
netsh interface portproxy show all
netstat -ano | Select-String -Pattern ':<port>'
curl.exe -k -I https://127.0.0.1:<port>/
```

## Mihomo / Clash 内核

Mihomo 是 Clash Meta 的 Go 内核。Dashboard/API 只是控制面，代理监听、DNS、规则匹配、TUN、协议 outbound 等后端逻辑都在同一个 Go 可执行文件里。需要临时启用系统代理、规则代理或 TUN 接管流量时使用：**TUN 模式下通常要管理员权限启动**（创建/管理虚拟网卡），并且 mihomo 本身**需要终端一直挂着**，重启或终端关闭后要手动重新执行（要常驻则做成 service）。

### 默认配置位置

Mihomo 默认从运行用户的配置目录读取 `config.yaml`。Windows 当前用户下常用路径：

- `%USERPROFILE%\.config\mihomo\config.yaml`：默认运行配置。这个目录在 mihomo 的安全路径内，REST API 可以用 `path` 方式热重载。
- `%USERPROFILE%\mihomo`：mihomo 源码仓库，当前可切到 release tag 构建；`mihomo.exe` 放在这里用于运行/验证。

检查版本：

```powershell
cd "$env:USERPROFILE\mihomo"
.\mihomo.exe -v
```

默认配置启动：

```powershell
cd "$env:USERPROFILE\mihomo"
.\mihomo.exe
```

显式指定配置目录：

```powershell
cd "$env:USERPROFILE\mihomo"
.\mihomo.exe -d "$env:USERPROFILE\.config\mihomo"
```

校验默认配置：

```powershell
cd "$env:USERPROFILE\mihomo"
.\mihomo.exe -t -d "$env:USERPROFILE\.config\mihomo"
```

Linux 下如果用 `sudo` 启动 mihomo，默认配置目录会从当前用户的 `~/.config/mihomo` 变成 `/root/.config/mihomo`；这时要么显式 `-d /home/<user>/.config/mihomo`，要么按 root 的默认目录放配置。TUN 需要网络管理权限，Linux 直接运行 TUN 时通常要 `sudo`。

### REST API 运行态排障

当前配置使用：

```yaml
external-controller: 127.0.0.1:9090
secret: ''
```

常用检查：

```powershell
curl.exe http://127.0.0.1:9090/configs
curl.exe http://127.0.0.1:9090/proxies
curl.exe http://127.0.0.1:9090/connections
curl.exe --max-time 3 "http://127.0.0.1:9090/logs?format=structured&level=info"
curl.exe --max-time 3 http://127.0.0.1:9090/traffic
```

`/configs` 只展示运行态通用配置，不展示当前配置文件路径。核对加载是否正确时，结合 `/configs` 的 TUN、端口、日志级别和 `/proxies` 的节点组、`testUrl`、当前选择一起看。

用安全路径内的默认配置热重载：

```powershell
$body = @{ path = "$env:USERPROFILE\.config\mihomo\config.yaml" } | ConvertTo-Json -Compress
Invoke-WebRequest -Uri 'http://127.0.0.1:9090/configs?force=true' -Method Put -ContentType 'application/json' -Body $body
```

如果配置不在安全路径内，`path` 方式会报 `path is not subpath of home directory or SAFE_PATHS`。这种情况下可以临时用 `payload` 方式提交完整 YAML；日常使用应直接维护默认位置的 `.config\mihomo\config.yaml`。

CLI 默认日志输出到 stdout，不默认写日志文件。适合 AI 监控的是内置 API：`/logs?format=structured` 看结构化日志，`/traffic` 看速率，`/connections` 看连接命中规则，`/proxies` 看节点健康和选择状态。

### BrowserLeaks / DNS / WebRTC 泄露排障

排查 BrowserLeaks 这类站点时，不要只看浏览器页面上的 Remote IP。要同时看 mihomo 的运行态连接：

```powershell
curl.exe http://127.0.0.1:9090/connections
curl.exe --max-time 3 "http://127.0.0.1:9090/logs?format=structured&level=info"
```

重点看：

- `host`：访问的域名，例如 `browserleaks.com`、`tls.browserleaks.com`、STUN 域名。
- `network`：`tcp` 还是 `udp`。
- `destinationPort`：WebRTC/STUN 常见是 `19302`，TURN/STUN 常见范围是 `3478-3481`。
- `chains`：最终是代理节点、`DIRECT` 还是 `REJECT`。
- `rule` / `rulePayload`：是否被 `cn`、`cn-ip`、`Match` 等规则误命中。

DNS 泄露测试出现本地 ISP DNS 或学校/运营商 DNS 时，先确认 TUN 和 DNS 劫持是否开启：

```yaml
tun:
  enable: true
  stack: mixed
  auto-route: true
  auto-detect-interface: true
  strict-route: true
  dns-hijack:
    - any:53
```

DNS 配置建议使用 `fake-ip`，并让 DNS 查询尊重规则：

```yaml
dns:
  enable: true
  enhanced-mode: fake-ip
  respect-rules: true
```

如果 BrowserLeaks 相关域名被规则集误判为国内或直连，给它们加高优先级显式代理规则，放在通用规则前：

```yaml
rules:
  - DOMAIN-SUFFIX,browserleaks.com,🚀 节点选择
  - DOMAIN-SUFFIX,browserleaks.org,🚀 节点选择
  - DOMAIN-SUFFIX,browserleaks.net,🚀 节点选择
```

WebRTC 泄露通常不是普通 TCP 页面请求泄露，而是浏览器向 STUN/TURN 服务器发 UDP 探测。若 BrowserLeaks 显示 Remote IP 是代理，但 WebRTC Public IP 还是本地出口，去 `/connections` 或结构化日志里找 UDP STUN 连接。常见修法是直接拒绝这些 UDP 端口：

```yaml
rules:
  - AND,((NETWORK,UDP),(DST-PORT,19302)),REJECT
  - AND,((NETWORK,UDP),(DST-PORT,3478-3481)),REJECT
```

这些端口不是“所有 WebRTC 端口”，只是常见 STUN/TURN 探测端口：`19302` 常见于 Google STUN，`3478-3481` 常见于 STUN/TURN 服务。先精准拒绝这些端口；如果后续日志里还能看到新的 UDP STUN/TURN 泄露，再按日志补规则。

注意规则顺序：这些 `REJECT` 和 BrowserLeaks 显式代理规则应放在 `RuleSet(cn)`、`GEOIP,CN`、`MATCH` 等宽泛规则前面。修改后用默认配置目录校验并热重载：

```powershell
cd "$env:USERPROFILE\mihomo"
.\mihomo.exe -t -d "$env:USERPROFILE\.config\mihomo"
$body = @{ path = "$env:USERPROFILE\.config\mihomo\config.yaml" } | ConvertTo-Json -Compress
Invoke-WebRequest -Uri 'http://127.0.0.1:9090/configs?force=true' -Method Put -ContentType 'application/json' -Body $body
```

### HTTPS_PROXY 只决定入口、不决定出口（rule + group 链路）

新手常见误解：在 WSL 里设了 `HTTPS_PROXY=http://<gw>:7890`，curl 就一定走代理节点出去。**错**。env 只告诉 client "把流量送到 Mihomo 这个端口"，**实际出口节点由 Mihomo 自己的 `rules` + `proxy-groups` 链决定**。链路上任何一层选了 `DIRECT`，流量就回到本机直连——HTTPS_PROXY 显示设了也照样被 GFW RST。

典型链路（按 `config.yaml` 走）：

```
TCP from client → Mihomo mixed-port
  → rules:  DOMAIN-SUFFIX,xxx,☁️ 云服务      (rule 命中决定走哪个 group)
  → ☁️ 云服务 (Selector) now=🚀 节点选择     (group 当前选哪一项)
  → 🚀 节点选择 (Selector) now=Hysteria2-Node
  → 真实 outbound：Hysteria2 协议 → proxy.example.com
```

排障时**每一层都要看 `.now`**，而不是只看 GLOBAL 或某一个 group。常见踩坑：

1. **改 GLOBAL 没效果** —— GLOBAL 只在没有 rule 命中时兜底。如果 `rules` 段有 `RULE-SET,aws,☁️ 云服务`，AWS 流量根本不到 GLOBAL，改 GLOBAL 白改。先 `cat config.yaml` 找命中目标域名的 rule，定位到具体 group。
2. **改外层 group 报 "proxy not exist"** —— `.all` 里没有目标 proxy 就 PUT 失败。比如 `☁️ 云服务.all = [🚀 节点选择, vless-ws-Node, DIRECT, REJECT]`，想切到 `Hysteria2-Node` 必须先 PUT `🚀 节点选择` → `Hysteria2-Node`，再 PUT `☁️ 云服务` → `🚀 节点选择`。**两层都要改**。
3. **PUT 后老连接不切** —— Mihomo 切节点只对**新建连接**生效。`curl --no-keepalive` 强制每次重连；长跑的下载/上传进程要重启才走新节点。

### REST API 改节点 + 测延迟（PowerShell + emoji group 名）

group 名常含 emoji 或中文，URL path 必须 `EscapeDataString`：

```powershell
# 写到 .ps1 文件后 pwsh -ExecutionPolicy Bypass -File 跑
# （bash -c "pwsh -Command @\"...\"@" 引号嵌套地狱，强烈不推荐）
$h = @{ "Content-Type" = "application/json" }
$enc = [uri]::EscapeDataString("🚀 节点选择")
# 切节点
Invoke-RestMethod -Method Put -Uri "http://127.0.0.1:9090/proxies/$enc" `
  -Headers $h -Body '{"name":"Hysteria2-Node"}' -TimeoutSec 5
# 查当前
(Invoke-RestMethod -Uri "http://127.0.0.1:9090/proxies/$enc").now
# 列可选
(Invoke-RestMethod -Uri "http://127.0.0.1:9090/proxies/$enc").all
```

测节点对**真实目标**的 delay（比 curl 测 throughput 快几十倍，几秒拿结果）：

```powershell
$target = "https://<公共大文件-test-url>"
foreach ($n in @("vless-ws-Node","vless-ws-Node2","Hysteria2-Node")) {
    $r = Invoke-RestMethod -Uri "http://127.0.0.1:9090/proxies/$([uri]::EscapeDataString($n))/delay?url=$([uri]::EscapeDataString($target))&timeout=10000"
    Write-Host "$n delay=$($r.delay)ms"
}
# 失败的节点会抛 504 Gateway Timeout
```

**WSL 跨边界调 Windows pwsh 的固定套路**：

```bash
PSEXE="/mnt/c/Program Files/PowerShell/7/pwsh.exe"   # pwsh 7 路径，不是 powershell.exe
# 在 WSL 写 ps1 → Windows 侧通过 \\wsl.localhost\<distro>\... 读
# 默认 ExecutionPolicy 拦未签名脚本：
"$PSEXE" -NoProfile -ExecutionPolicy Bypass -File /tmp/foo.ps1
```

### 协议选错可以慢 100×（vless+ws vs hysteria2）

实测：同一台落地服务器，同一国内 ISP 出口，拉 AWS S3 公共 bucket 的 1 MB part：

| 节点 / 协议 | throughput | 备注 |
|---|---|---|
| vless + WS over TCP | **8.4 KB/s** | TCP 拥塞控制 + WS handshake/帧头开销；同服务器但跑不起来 |
| Hysteria2 / QUIC + BBR | **14.6 MB/s** | 实测，1 GB part 78s |

> Hysteria2：基于 QUIC 的代理协议，自带 BBR 拥塞控制，单连接多 stream 不受 TCP head-of-line blocking。WebSocket-vless：vless 协议套在 WebSocket 上（穿 CDN/反代友好），但传输层还是 TCP cubic，长肥管道（high BDP，跨国 GFW 后大延迟）下吞吐被拥塞算法压死。

排障思路：

1. **节点 delay 通 ≠ 节点能跑全速**。`/delay` 只测 1 KB 级请求 RTT，遇到大文件可能崩。换协议（Hysteria2 / 直连 QUIC / TUIC 都比 ws over TCP 稳）。
2. **测吞吐别用 KB 级文件**。前几 MB 在 TCP 慢启动阶段，speed 数字偏小；要测真实带宽至少 50 MB 以上。
3. **看进度别看 "MiB/s"，看 "part/s"**。如果 mirror 跑大量 KB 级小文件，per-part RTT 主导，整体 MiB/s 显示很低但实际**带宽没饱和**——继续跑到大文件阶段会爆发。

#### 健康检查 jitter & 上层调用稳定性（vless+ws → Hysteria2 切换）

吞吐之外，**节点稳定性**（延迟波动 + 上层 agent 调用的成功率）也呈现明显差异。某段长期观测 (`/proxies` API 拉 history) 数据：每 5min 一次 `cp.cloudflare.com/generate_204` 健康检查，10 个采样窗口里——

| 协议 | 平均 delay | jitter (max - min) | 节点报错次数 |
|---|---|---|---|
| vless + WebSocket (多节点 URLTest 群组) | ~355 ms | **250+ ms** | 0（但偶发 dial timeout，见下） |
| Hysteria2 / QUIC | ~378 ms | **~150 ms** | 同窗口 0 |

> 平均 delay Hysteria2 略高，但 jitter 小一半左右。**对长连接 / 大文件 / agent 流式 API 而言，jitter 远比绝对 delay 重要**——抖动大会触发 URLTest 在多个 vless 节点之间反复横跳，每次切换都打断已建立的 TCP 长连接。

链路拓扑差异是关键：vless+ws 节点群常常落在某海外 HTTPS 反代后面（多一跳），日志里可观察到形如 `dial xxx error: <反代-host>:443 connect error: i/o timeout` 的偶发 warning——表面是节点超时，根因是**前置反代瞬时抖动**。Hysteria2 直连落地服务器时少一跳，规避了这个失败模式。

操作建议：

1. **不要盲信"自动选择"**。若节点群里 2~3 个候选 delay 接近，URLTest 默认 tolerance 容易让它在小幅波动时来回切，体感就是"偶尔掉线"。要么手动钉死到稳定节点，要么给 URLTest 加 `tolerance: 150`（差距小于 150ms 不切）。
2. **节点名带 "Fast" 不一定快**。同协议同链路的两个节点常常实测差不多甚至更慢，**只能用 history / `/delay` 实测决定**。
3. **挑节点的优先级**：`协议（QUIC/Hysteria2 > vless+TCP+WS）> 链路跳数（直连落地 > 经反代）> 平均 delay`，平均 delay 排最后。

**预设结论（待长期验证）**：从 vless+ws URLTest 自动组切到手动钉死 Hysteria2 节点后，agent 调用（Copilot CLI / Claude Code 之类的第三方 API 长连接）不再出现偶发 `API error`。如果后续观察到反例，回来订正这一段。

#### 已知风险：长期跑 Hysteria2 落地 IP 疑似被针对性屏蔽（待长期验证）

> 2026-06-08 单次事件，**根因尚未坐实**，记录现象供下次出现时对照。

现象：长期把某海外 VPS 上的 Hysteria2 节点钉死成主节点跑了一段时间后，某天起从**大陆**任何出口（家里 ISP 出口、阿里云大陆区域绕开 TUN 走真实国际出口）对这台 VPS 的 IP 任何端口（22 / 443 / ICMP）全部 timeout；**同机房同 /24 子网邻居 IP** 一切正常；第三方多地探测站（含越南 / 印尼等近大陆地区节点）全部 ping 通；VPS 本机上 sshd / Caddy / ufw 全部健康，日志里能看到其它源 IP 正常进来。**症状形态 = 大陆精准屏蔽这一个 IP**，机房 / 主机 / 防火墙都可以排除。

可能原因（**未验证**）：
- Hysteria2 跑 QUIC over UDP，单 IP 持续大流量 UDP 是 GFW 主动探测的明显特征之一
- 落地 IP 注册了公开域名长期暴露，扫描器易识别
- 也可能是机房 IP 段被整体波及，跟 Hysteria2 无关——这就是为什么标"待验证"

下次再撞上需要确认的对照实验：
1. 临时停掉该 VPS 上 Hysteria2 监听，等 24~72 小时看 IP 是否恢复（恢复 = 强证据支持"代理流量触发"假设）
2. 同时观察新换的 IP 在不跑 Hysteria2 / 跑别的协议时多久会被屏蔽，作横向对照

短期可用的缓解：
- **进入仍可达**：从大陆侧 ssh 改走 `ProxyJump` 经另一台**境外不受影响**的 VPS 跳板；Caddy 上的网页同理可经境外节点访问
- **彻底解决**：换 IP（一般机房很快生效），并把代理协议迁离这台（或换成 Reality / 强 fingerprint masking 的 vless），降低同样路径被复现的概率

### Windows TUN / 代理端口稳定性排障

先区分是远端节点不通，还是本机 TUN / 代理入口没有正确接管。常用对照：

```powershell
curl.exe -v -I --max-time 12 <test-url>
curl.exe -v -I --max-time 12 --proxy http://127.0.0.1:7890 <test-url>
curl.exe -v -I --max-time 12 --proxy http://<lan-or-vpn-ip>:7890 <test-url>
```

如果显式 `--proxy` 稳定成功，而裸 `curl` 失败或命中 fake-ip 后报连接错误，优先查 TUN、系统路由、DNS 劫持和沙箱/权限环境；不要直接判断为远端节点问题。

`mixed-port` 不建议只绑定到某个虚拟网卡或临时地址。只给本机用时优先绑定回环地址；需要给局域网、虚拟网或其他设备用时可绑定全部地址，并结合防火墙控制访问：

```yaml
mixed-port: 7890
allow-lan: true
bind-address: '*'
```

如果绑定到某个具体虚拟网卡地址，网卡重连、地址变化、服务启动顺序变化都可能导致本机工具或其他设备间歇性连不上代理端口。

### WSL NAT 下出站走 Mihomo / fake-ip

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

### Mihomo TUN 路由规则（IP-CIDR / route-exclude）

`IP-CIDR,...,DIRECT` 不等于绕过 Mihomo TUN。它只表示流量进入 TUN 后，mihomo 选择 `DIRECT` outbound；运行态 `/connections` 里仍可能看到 `inboundName: DEFAULT-TUN`、`chains: [DIRECT, ...]`。

规则顺序会影响策略选择。宽泛的 `RULE-SET,private-ip`、`RULE-SET,cn-ip` 如果放在显式 `IP-CIDR` 前，会先命中特例地址。需要特例策略时，把特例规则放到宽泛规则前；但即使提前命中 `DIRECT`，它仍不是 TUN bypass。

`route-exclude-address` 有坑，不要把它当成稳定通用方案。它只让 mihomo 不接管这些目的地址，不保证 Windows 自动补出可用的物理网卡路由；排除异地组网依赖的公网服务器 IP 后，可能直接把异地组网服务本身断开。

```powershell
route print <peer-ip>
```

本次排障里，`route-exclude-address + 手动 host route` 没作为最终方案采用。

### VLESS + ws + TLS 客户端配置（DNS / 节点组 / MTU 默认值 / 延迟判断）

VLESS + WebSocket + TLS 放在 Caddy/Nginx 后面不是错误方案，适合已有 HTTPS 站点、证书自动维护、端口复用和反代隐藏。但客户端配置要补齐 TLS 侧信息：

```yaml
proxies:
  - name: <node-name>
    type: vless
    server: <proxy-domain>
    port: 443
    uuid: <uuid>
    tls: true
    servername: <proxy-domain>
    client-fingerprint: chrome
    network: ws
    ws-opts:
      path: <websocket-path>
```

`servername` 不要留空；它应和证书、反代站点、客户端访问域名一致。`client-fingerprint` 建议写在具体 proxy 上。

DNS 的 IPv6 设置应和全局 IPv6 策略一致。若全局关闭 IPv6，DNS 也保持关闭，避免解析出不可用地址或连接路径不一致：

```yaml
ipv6: false
dns:
  enable: true
  ipv6: false
  respect-rules: true
  enhanced-mode: fake-ip
```

节点组选择上，`fallback` 是按顺序优先使用第一个可用节点；`url-test` 才是按延迟选择。两台或多台同类节点需要自动选低延迟时，用 `url-test`，并设置 `tolerance` 避免延迟差很小时频繁切换：

```yaml
proxy-groups:
  - name: <auto-group>
    type: url-test
    proxies:
      - <node-a>
      - <node-b>
    url: <latency-test-url>
    interval: 300
    tolerance: 50
    lazy: false
```

不要把探测间隔设得过短。短间隔会增加远端和反代连接压力，也可能让选择器看起来频繁抖动。

MTU 不要为了“稳定”而默认显式写入。只有出现大包相关症状时再测试，例如大文件下载中断、网页加载一半停住、TLS 握手偶发超时、小请求能通但大响应卡住。需要测试时可临时从 `1400` 或 `1380` 开始；没有这些症状时让 mihomo 使用默认值。

延迟判断不要只看面板或 API 的单次 delay。API delay 可用于节点间相对比较，真实体感还要看代理后的实际请求总耗时和稳定性：

```powershell
$node = [uri]::EscapeDataString('<node-name>')
curl.exe "http://127.0.0.1:9090/proxies/$node/delay?timeout=8000&url=<encoded-test-url>"

1..10 | ForEach-Object {
  curl.exe --silent --show-error --output NUL `
    --write-out '%{http_code} connect=%{time_connect} start=%{time_starttransfer} total=%{time_total}\n' `
    --max-time 12 --proxy http://127.0.0.1:7890 <test-url>
}
```

如果 API delay 较低但真实 `total` 明显更高，说明节点 TCP/TLS 探测和完整 HTTP 请求体感不同。此时应关注是否稳定、是否丢请求、是否存在反代/目标站差异，而不是只追求面板数字。

### 从源码构建 mihomo（Windows）

#### 切换到 release tag

构建指定 release 前先切 tag：

```powershell
cd "$env:USERPROFILE\mihomo"
git checkout v1.19.24
git describe --tags --exact-match
```

如果工作区有本地配置文件、脚本或生成物，它们会显示为 untracked；不要因为切 tag 或构建而清理这些文件，除非用户明确要求。

#### 官方 workflow 的 windows-amd64 构建

GitHub Actions 里无 `v1/v2/v3` 文件名后缀的 `mihomo-windows-amd64` 对应：

- `GOOS=windows`
- `GOARCH=amd64`
- `GOAMD64=v3`
- build tag：`with_gvisor`
- 输出中间文件：默认 `mihomo.exe`
- 后处理才复制为 `mihomo-windows-amd64.exe` 并打 zip

PowerShell 复现核心 `go build`：

```powershell
cd "$env:USERPROFILE\mihomo"
$env:GOOS = "windows"
$env:GOARCH = "amd64"
$env:GOAMD64 = "v3"

go build -v -tags "with_gvisor" -trimpath -ldflags "-X 'github.com/metacubex/mihomo/constant.Version=v1.19.24' -X 'github.com/metacubex/mihomo/constant.BuildTime=$(Get-Date -Format r)' -w -s -buildid="
```

这条命令不指定 `-o`，所以会在当前目录生成或覆盖 `mihomo.exe`。如果 `mihomo.exe` 正在运行，Windows 会因为文件占用导致构建失败，需要先停掉 mihomo。

#### 不覆盖 release exe 的构建

需要保留现有 `mihomo.exe` 时，显式输出到其他文件：

```powershell
cd "$env:USERPROFILE\mihomo"
$env:GOOS = "windows"
$env:GOARCH = "amd64"
$env:GOAMD64 = "v3"

go build -v -tags "with_gvisor" -trimpath -ldflags "-X 'github.com/metacubex/mihomo/constant.Version=v1.19.24' -X 'github.com/metacubex/mihomo/constant.BuildTime=$(Get-Date -Format r)' -w -s -buildid=" -o mihomo-windows-amd64.exe .
```

#### zip 不是 go build 默认产物

`go build` 只生成 exe。Release 包里的 `mihomo-windows-amd64-v1.19.24.zip` 是 workflow 在构建后额外压缩出来的，逻辑相当于：

```powershell
Copy-Item .\mihomo.exe .\mihomo-windows-amd64.exe -Force
Compress-Archive -LiteralPath .\mihomo-windows-amd64.exe -DestinationPath .\mihomo-windows-amd64-v1.19.24.zip -Force
```

#### 验证

构建后用：

```powershell
.\mihomo.exe -v
```

期望包含：

```text
Mihomo Meta v1.19.24 windows amd64
Use tags: with_gvisor
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

