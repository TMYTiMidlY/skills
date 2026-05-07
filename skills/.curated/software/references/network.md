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
default via 10.100.158.254 dev eth1 proto kernel metric 25
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

## Mihomo / Clash 内核（Windows）

Mihomo 是 Clash Meta 的 Go 内核。Dashboard/API 只是控制面，代理监听、DNS、规则匹配、TUN、协议 outbound 等后端逻辑都在同一个 Go 可执行文件里。

### 默认配置位置

Mihomo 默认从用户配置目录读取 `config.yaml`。Windows 当前用户下常用路径：

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

### Mihomo TUN 与 EasyTier / WSL NAT

`IP-CIDR,...,DIRECT` 不等于绕过 Mihomo TUN。它只表示流量进入 TUN 后，mihomo 选择 `DIRECT` outbound；运行态 `/connections` 里仍可能看到 `inboundName: DEFAULT-TUN`、`chains: [DIRECT, ...]`。

规则顺序会影响策略选择。宽泛的 `RULE-SET,private-ip`、`RULE-SET,cn-ip` 如果放在显式 `IP-CIDR` 前，会先命中特例地址。需要特例策略时，把特例规则放到宽泛规则前；但即使提前命中 `DIRECT`，它仍不是 TUN bypass。

`route-exclude-address` 有坑，不要把它当成稳定通用方案。它只让 mihomo 不接管这些目的地址，不保证 Windows 自动补出可用的物理网卡路由；排除异地组网依赖的公网服务器 IP 后，可能直接把异地组网服务本身断开。

```powershell
route print <peer-ip>
```

本次排障里，`route-exclude-address + 手动 host route` 没作为最终方案采用。

WSL NAT + Windows EasyTier + 远端 Caddy 的简单稳定方案：

```text
远端 Caddy reverse_proxy -> Windows EasyTier IP:port
Windows portproxy -> 127.0.0.1:port
WSL 服务监听并由 Windows localhost 转发访问
```

`netsh interface portproxy` 是 TCP 转发，不支持 UDP。WSL NAT 下优先尝试 `connectaddress=127.0.0.1`，这样比写 WSL NAT IP 更少受 WSL 重启后地址变化影响。批量检查：

```powershell
netsh interface portproxy show all
```

从云服务器探测 TCP 时，避免用 Bash `/dev/tcp/...` 形式；这类命令容易被云安全产品识别为反弹 shell 特征。HTTP(S) 端口优先用：

```bash
curl -k -I --connect-timeout 5 --max-time 8 https://<target>:<port>/
```

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

### MTU 问题

曾在 WSL 内部署 EasyTier 时遇到过 MTU 不匹配问题——必须手动降低 EasyTier 的 MTU 以匹配 WSL 网卡的 MTU。

**当前方案**：不再在 WSL 内配置组网，EasyTier 运行在 Windows 宿主机上，避免了此问题。
