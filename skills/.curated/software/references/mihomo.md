# Mihomo / Clash 内核（Windows）

Mihomo 是 Clash Meta 的 Go 内核。Dashboard/API 只是控制面，代理监听、DNS、规则匹配、TUN、协议 outbound 等后端逻辑都在同一个 Go 可执行文件里。

## 默认配置位置

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

## 切换到 release tag

构建指定 release 前先切 tag：

```powershell
cd "$env:USERPROFILE\mihomo"
git checkout v1.19.24
git describe --tags --exact-match
```

如果工作区有本地配置文件、脚本或生成物，它们会显示为 untracked；不要因为切 tag 或构建而清理这些文件，除非用户明确要求。

## 官方 workflow 的 windows-amd64 构建

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

## 不覆盖 release exe 的构建

需要保留现有 `mihomo.exe` 时，显式输出到其他文件：

```powershell
cd "$env:USERPROFILE\mihomo"
$env:GOOS = "windows"
$env:GOARCH = "amd64"
$env:GOAMD64 = "v3"

go build -v -tags "with_gvisor" -trimpath -ldflags "-X 'github.com/metacubex/mihomo/constant.Version=v1.19.24' -X 'github.com/metacubex/mihomo/constant.BuildTime=$(Get-Date -Format r)' -w -s -buildid=" -o mihomo-windows-amd64.exe .
```

## zip 不是 go build 默认产物

`go build` 只生成 exe。Release 包里的 `mihomo-windows-amd64-v1.19.24.zip` 是 workflow 在构建后额外压缩出来的，逻辑相当于：

```powershell
Copy-Item .\mihomo.exe .\mihomo-windows-amd64.exe -Force
Compress-Archive -LiteralPath .\mihomo-windows-amd64.exe -DestinationPath .\mihomo-windows-amd64-v1.19.24.zip -Force
```

## 验证

构建后用：

```powershell
.\mihomo.exe -v
```

期望包含：

```text
Mihomo Meta v1.19.24 windows amd64
Use tags: with_gvisor
```
