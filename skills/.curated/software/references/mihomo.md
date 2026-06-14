# Mihomo / Clash 内核

> 本文聚焦 Mihomo/Clash 代理本身的运维：配置、REST API 排障、节点/协议选型与性能、TUN 路由规则、VLESS 客户端配置、从源码构建。WSL ↔ Windows ↔ 远端的网络管道（WSL 出站怎么进 Mihomo、portproxy/wslrelay 入站、RDP 等）见 [network.md](network.md)。

Mihomo 是 Clash Meta 的 Go 内核。Dashboard/API 只是控制面，代理监听、DNS、规则匹配、TUN、协议 outbound 等后端逻辑都在同一个 Go 可执行文件里。需要临时启用系统代理、规则代理或 TUN 接管流量时使用：**TUN 模式下通常要管理员权限启动**（创建/管理虚拟网卡），并且 mihomo 本身**需要终端一直挂着**，重启或终端关闭后要手动重新执行（要常驻则做成 service）。

## 默认配置位置

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

## REST API 运行态排障

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

## BrowserLeaks / DNS / WebRTC 泄露排障

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

## HTTPS_PROXY 只决定入口、不决定出口（rule + group 链路）

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

## WSL ssh 借道宿主 mihomo（ProxyCommand + 动态网关）

WSL2（NAT 模式）里 ssh 要走宿主 Windows 上的 mihomo：HTTP 客户端设 `HTTPS_PROXY` 即可，但 ssh 走 SOCKS、得用 `ProxyCommand`。难点：mihomo 监听宿主 `127.0.0.1:7890`，而 WSL 里的 `127.0.0.1` 是 WSL 自己；要用**宿主在 WSL 网段的 IP = WSL 默认网关**，且 NAT 下这个网关 IP **每次启动可能变**、不能写死。于是在 `ProxyCommand` 里现取网关再走它的 SOCKS5：

```sshconfig
Host <要走代理的远端>
    # WSL2 NAT：动态取默认网关(=宿主)，经其 mihomo :7890 SOCKS5 出站
    ProxyCommand sh -c 'gw=$(ip route show default 2>/dev/null | awk "{print \$3; exit}"); exec nc -x "${gw:-172.28.80.1}:7890" -X 5 "$0" "$1"' %h %p
```

- `%h %p` → ssh 替换成目标主机/端口（脚本里的 `$0`/`$1`）；`ip route show default | awk '{print $3}'` → 默认网关（NAT 下=宿主），`${gw:-…}` 是取不到时的兜底；`nc -x <网关>:7890 -X 5` → `-X 5`=SOCKS5，经网关的 mihomo 端口连目标。
- **何时不需要**：宿主 mihomo 开 **TUN 模式**时透明路由（连 fake-IP 都接管），WSL 里 ssh 直连目标即被接管，这条 ProxyCommand 多余——解析成 fake-IP 的域名（自建服务等）直接通。只有**没被 TUN/规则覆盖、直连出不去**的目标才需要它：同一台 WSL 上 `github.com:443` 去掉 ProxyCommand 直连 `Connection timed out`，加上才通。Mirror 模式下 WSL 与宿主共享 `127.0.0.1`，可直接用 `127.0.0.1:7890`、不必取网关（见 [network.md](network.md)）。

## REST API 改节点 + 测延迟（PowerShell + emoji group 名）

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

## 协议选错可以慢 100×（vless+ws vs hysteria2）

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

### 健康检查 jitter & 上层调用稳定性（vless+ws → Hysteria2 切换）

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

### 已知风险：长期跑 Hysteria2 落地 IP 疑似被针对性屏蔽（待长期验证）

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

## Windows TUN / 代理端口稳定性排障

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

## Mihomo TUN 路由规则（IP-CIDR / route-exclude）

`IP-CIDR,...,DIRECT` 不等于绕过 Mihomo TUN。它只表示流量进入 TUN 后，mihomo 选择 `DIRECT` outbound；运行态 `/connections` 里仍可能看到 `inboundName: DEFAULT-TUN`、`chains: [DIRECT, ...]`。

规则顺序会影响策略选择。宽泛的 `RULE-SET,private-ip`、`RULE-SET,cn-ip` 如果放在显式 `IP-CIDR` 前，会先命中特例地址。需要特例策略时，把特例规则放到宽泛规则前；但即使提前命中 `DIRECT`，它仍不是 TUN bypass。

`route-exclude-address` 有坑，不要把它当成稳定通用方案。它只让 mihomo 不接管这些目的地址，不保证 Windows 自动补出可用的物理网卡路由；排除异地组网依赖的公网服务器 IP 后，可能直接把异地组网服务本身断开。

```powershell
route print <peer-ip>
```

本次排障里，`route-exclude-address + 手动 host route` 没作为最终方案采用。

## VLESS + ws + TLS 客户端配置（DNS / 节点组 / MTU 默认值 / 延迟判断）

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

## 从源码构建 mihomo（Windows）

### 切换到 release tag

构建指定 release 前先切 tag：

```powershell
cd "$env:USERPROFILE\mihomo"
git checkout v1.19.24
git describe --tags --exact-match
```

如果工作区有本地配置文件、脚本或生成物，它们会显示为 untracked；不要因为切 tag 或构建而清理这些文件，除非用户明确要求。

### 官方 workflow 的 windows-amd64 构建

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

### 不覆盖 release exe 的构建

需要保留现有 `mihomo.exe` 时，显式输出到其他文件：

```powershell
cd "$env:USERPROFILE\mihomo"
$env:GOOS = "windows"
$env:GOARCH = "amd64"
$env:GOAMD64 = "v3"

go build -v -tags "with_gvisor" -trimpath -ldflags "-X 'github.com/metacubex/mihomo/constant.Version=v1.19.24' -X 'github.com/metacubex/mihomo/constant.BuildTime=$(Get-Date -Format r)' -w -s -buildid=" -o mihomo-windows-amd64.exe .
```

### zip 不是 go build 默认产物

`go build` 只生成 exe。Release 包里的 `mihomo-windows-amd64-v1.19.24.zip` 是 workflow 在构建后额外压缩出来的，逻辑相当于：

```powershell
Copy-Item .\mihomo.exe .\mihomo-windows-amd64.exe -Force
Compress-Archive -LiteralPath .\mihomo-windows-amd64.exe -DestinationPath .\mihomo-windows-amd64-v1.19.24.zip -Force
```

### 验证

构建后用：

```powershell
.\mihomo.exe -v
```

期望包含：

```text
Mihomo Meta v1.19.24 windows amd64
Use tags: with_gvisor
```

