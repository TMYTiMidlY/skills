# Mihomo 代理：配置与泄漏控制

> 本文把 Mihomo 的**配置用法**和**泄漏控制（DNS / WebRTC）**结合着讲，目标是读完能自己搭一套“不漏、分流准、能排障”的代理，并理解每个开关到底在做什么。全文分两部分：前半是**配置与使用**，后半是**泄漏控制**。WSL ↔ Windows ↔ 远端的网络管道（WSL 出站怎么进 Mihomo、portproxy/wslrelay 入站、RDP 等）是另一回事，见 [network.md](network.md)。
>
> **源码出处**：下文凡是讲到内部行为，都对照官方仓库 **`MetaCubeX/mihomo`** 的 **`Meta` 分支**（稳定线；开发线是 `Alpha`）。⚠️ 这个仓库的**默认分支 `main` 装的是一个同名的 Honkai: Star Rail Python 包，不是代理内核**——`git clone` 要带 `-b Meta` 才拿到 Go 源码（`module github.com/metacubex/mihomo`），否则会拿到一个 `pyproject.toml`。

---

# 第一部分：配置与使用

## 1. 整体架构：控制面与数据面

Mihomo 是 Clash Meta 的 Go 内核，**一个可执行文件**里同时跑两套东西：

- **控制面**：REST API（`external-controller`，默认 `127.0.0.1:9090`）+ Dashboard。只是“遥控器”，用来查状态、切节点、热重载。
- **数据面**：代理入口监听、DNS、规则匹配、TUN、各协议 outbound。真正搬运流量的是这一层。

一段流量的旅程（记住这条链，后面所有配置都挂在它上面）：

```
应用流量
  → 入口：mixed-port(显式代理) 或 TUN(透明接管)
  → DNS：要不要解析 / 解析成真 IP 还是 fake-ip（见第二部分）
  → rules：按域名/IP/端口/网络匹配，决定交给哪个 proxy-group
  → proxy-group：Selector/URLTest 选出当前用哪个节点（.now）
  → outbound：具体协议(VLESS/Hysteria2/…) → 落地服务器 → 目标网站
```

两个最常见的认知纠正，先打预防针：

- **TUN 模式通常要管理员/sudo 启动**（要创建管理虚拟网卡）。CLI 跑起来要**终端一直挂着**，关了就停；要常驻就做成 service。
- **设了 `HTTPS_PROXY` ≠ 流量一定走代理节点**。env 只决定“流量送进 Mihomo 哪个入口端口”，**出口走哪个节点完全由 `rules` + `proxy-groups` 决定**（见第 3 节）。

## 2. 安装、配置目录与启动

### 2.1 安装

mihomo 内核是一个**单文件静态二进制**，没有复杂依赖，“安装”本质就是把这个可执行文件放到某处。官方文档（[wiki.metacubex.one](https://wiki.metacubex.one/en/startup/)）给两条主路：

- **预编译二进制（推荐）**：从 [GitHub Releases](https://github.com/MetaCubeX/mihomo/releases) 按操作系统/架构下载。Windows 是 `.zip`、其它平台是 `.gz`，解压出来就是单个可执行文件。
  - amd64 有 `compatible` / `v1` / `v2` / `v3` 四个变体，对应 `GOAMD64` 微架构等级（越高用越新的 CPU 指令、越快）。**拿不准选 `compatible`**（最大兼容），较新的 CPU 用 `v3`。
  ```bash
  # Linux amd64 示例：下载、解压、放进 PATH
  ver=v1.19.27
  curl -L -o mihomo.gz "https://github.com/MetaCubeX/mihomo/releases/download/$ver/mihomo-linux-amd64-compatible-$ver.gz"
  gzip -d mihomo.gz && chmod +x mihomo && sudo mv mihomo /usr/local/bin/mihomo
  mihomo -v
  ```
- **Docker**：官方镜像 `metacubex/mihomo`（仓库 `Dockerfile` 自带 geoip/geosite 数据、声明 `VOLUME /root/.config/mihomo`、`ENTRYPOINT /mihomo`）。挂一个配置目录进容器即可：
  ```bash
  docker run -d --name mihomo --restart=always \
    -v /path/to/config:/root/.config/mihomo \
    -p 7890:7890 -p 9090:9090 \
    metacubex/mihomo   # TUN 还需 --cap-add NET_ADMIN --device /dev/net/tun 等
  ```
- **从源码构建**：见第 6 节。

> 很多 GUI 客户端（Clash Verge Rev、FlClash 等）**内置了 mihomo 内核**，装它们就不用单独装内核；只有要纯内核 / 做服务端常驻时才手动装上面这些。

### 2.2 配置目录是运行时算出来的（不是安装决定的）

容易误解的一点：`~/.config/mihomo` 这个路径**和二进制装在哪无关**，是 mihomo 启动时按“当前用户的主目录”现算的。源码 `constant/path.go`（`MetaCubeX/mihomo` 的 `Meta` 分支）：

```go
const Name = "mihomo"
homeDir, _ := os.UserHomeDir()        // Unix=$HOME，Windows=%USERPROFILE%
homeDir = path.Join(homeDir, ".config", Name)   // <home>/.config/mihomo
if _, err := os.Stat(homeDir); err != nil {     // 若该目录不存在
    if configHome, ok := os.LookupEnv("XDG_CONFIG_HOME"); ok {
        homeDir = path.Join(configHome, Name)   // 才回退到 $XDG_CONFIG_HOME/mihomo
    }
}
// configFile 默认 "config.yaml"
```

由此推出全部行为：

- 默认配置文件：Linux/macOS `~/.config/mihomo/config.yaml`，Windows `%USERPROFILE%\.config\mihomo\config.yaml`。
- **`$XDG_CONFIG_HOME` 只在 `~/.config/mihomo` 不存在时才生效**（注意这个先后顺序）。
- **`sudo` 启动**：`$HOME` 变 `/root`，目录就变 `/root/.config/mihomo`——所以 Linux 跑 TUN（要 `sudo`）时，要么显式 `-d /home/<user>/.config/mihomo`，要么把配置放到 root 的目录下。
- 命令行覆盖：`-d <dir>` 改配置目录（源码 `SetHomeDir`），`-f <file>` 改配置文件名（`SetConfig`）。
- **“安全路径”**：REST API 用 `path` 方式热重载（见第 4 节）默认只允许 home 的子路径；要放别处可用环境变量 `SAFE_PATHS` 加白名单，或 `SKIP_SAFE_PATH_CHECK=1` 整个关掉检查（源码 `IsSafePath`）。

### 2.3 启动与校验

```bash
# Linux/macOS
mihomo -v                              # 看版本
mihomo                                 # 用默认目录 ~/.config/mihomo 启动
mihomo -d ~/.config/mihomo             # 显式指定目录
mihomo -t -d ~/.config/mihomo          # 只校验配置不启动(-t = test)
```

```powershell
# Windows，假设 mihomo.exe 在 %USERPROFILE%\mihomo
cd "$env:USERPROFILE\mihomo"
.\mihomo.exe -v
.\mihomo.exe -t -d "$env:USERPROFILE\.config\mihomo"   # 校验
.\mihomo.exe -d "$env:USERPROFILE\.config\mihomo"      # 启动
```

CLI 跑起来要**终端一直挂着**，关了就停；要常驻就做成 service（Linux systemd / Windows 服务）。TUN 模式通常要管理员/sudo 启动（创建管理虚拟网卡）。

## 3. 流量链路：入口、规则与节点组

### 3.1 入口方式

- **`mixed-port`（显式代理）**：应用主动把流量发到这个端口（HTTP/SOCKS 混合）。适合“只想让特定程序走代理”。
  ```yaml
  mixed-port: 7890
  allow-lan: true        # 要给局域网/虚拟网/别的设备用时开
  bind-address: '*'      # 只给本机用就别写，默认回环即可
  ```
  绑定优先回环或 `*`，**别绑某个具体虚拟网卡地址**——网卡重连/地址变化/启动顺序变了，就会间歇连不上代理端口。

- **TUN（透明接管）**：创建一张虚拟网卡，把**整机路由**劫进 mihomo，应用无感。适合“全局接管 + 想按域名分流 + 防 DNS 泄漏”。TUN 怎么配见第二部分（它和 DNS 强相关）。

### 3.2 出口由规则与节点组决定

出口节点 = **`rules` 命中的那个 group，一路顺着 `.now` 解析到最终 outbound**。排障时**每一层都看 `.now`**，别只盯 GLOBAL 或某一个 group。

```
TCP from client → mixed-port / TUN
  → rules:  DOMAIN-SUFFIX,xxx,☁️ 云服务        # 命中决定走哪个 group
  → ☁️ 云服务 (Selector) .now = 🚀 节点选择     # 这一层当前选谁
  → 🚀 节点选择 (Selector) .now = Hysteria2-Node
  → outbound: Hysteria2 → proxy.example.com    # 真正出网
```

几个直接能用的判断：

- **`mode: rule` 下的兜底是规则表最后一条 `MATCH`，不是 GLOBAL**。规则**从上往下、首条命中即止**（源码 `tunnel/tunnel.go` 的 `match()`，循环里 `return` 首个命中的 rule；一条都没命中才落到 `DIRECT`）。最后那条 `MATCH,<某组>` 把“前面规则都没命中的流量”兜走——订阅里这个组常被命名为 `🐟 漏网之鱼`。`GLOBAL` 是另一个东西：内置的“装了所有节点和分组”的选择器，**只有切到 `mode: global` 时才用它接管一切**（源码 `case Global: proxy = proxies["GLOBAL"]`）。所以 rule 模式下改 GLOBAL 没用——要改就找命中目标的那条 rule、定位到它指向的组。
- **切节点常常要改两层（嵌套 Selector）**。真实订阅里常是“分类组 → 主选择器 → 真实节点”两层嵌套：分类组（如 `☁️ 云服务`）的 `.now` 指向主选择器（如 `🚀 节点选择`），主选择器再指向真实节点。关键约束在源码 `adapter/outboundgroup/selector.go` 的 `Set()`：**一个 Selector 只能被切到它自己 `.all` 里有的名字**，否则报 `proxy not exist`。
  ```go
  func (s *Selector) Set(name string) error {
      for _, proxy := range s.GetProxies(false) {   // 只在【本组 .all】里找
          if proxy.Name() == name { s.selected = name; return nil }
      }
      return errors.New("proxy not exist")
  }
  ```
  于是看你想要的节点在不在外层组的 `.all` 里：① 在 → 直接 PUT 外层组到该节点，一层即可、只影响这一类；② 不在 → 先 PUT 外层组 → 内层主选择器（在它 .all 里），再 PUT 内层主选择器 → 目标节点（在主选择器 .all 里），这就是“改两层”（副作用：改主选择器会牵动所有指向它的分类组）。③ 想让所有分类一起换 → 因为它们多半都指向同一个主选择器，**只改主选择器一层**即可。
- **切节点只对新建连接生效**。长跑的下载/上传/长连接要重连才走新节点（`curl --no-keepalive` 可强制每次重连验证）。

### 3.3 节点组类型

```yaml
proxy-groups:
  - name: <auto-group>
    type: url-test          # 按延迟自动选最低；fallback 则是“按顺序选第一个可用”
    proxies: [<node-a>, <node-b>]
    url: <latency-test-url>
    interval: 300           # 探测间隔，别设太短(增加落地/反代压力 + 看着抖)
    tolerance: 150          # 差距 < 150ms 不切，避免在相近节点间反复横跳
    lazy: false
```

经验：`url-test` 的默认 tolerance 太小，几个延迟相近的节点会“小幅波动就来回切”，体感像偶尔掉线。**要么手动钉死稳定节点，要么把 `tolerance` 调大**。挑节点优先级建议：**协议（QUIC/Hysteria2 > vless+TCP+WS）> 链路跳数（直连落地 > 经反代）> 平均 delay**——平均 delay 排最后，jitter（抖动）比绝对延迟更影响长连接/流式 API。

### 3.4 协议选型与性能

**经验法则**：跨国（高延迟、可能丢包）链路优先 QUIC 系（Hysteria2 / TUIC）；vless+ws+TCP 适合穿 CDN/反代，但传输层受 TCP 拥塞控制限制。

实测（2026-06-27，两个节点都落地在同一台 RackNerd：Hysteria2=UDP 443 直连，vless+ws=TCP 443 经 Caddy→xray 多一跳；本机 mihomo 经 7890 拉 Cloudflare 50MB，延迟取 8 次采样）：

| 协议 | 实测吞吐 | 延迟抖动(min/max) |
|---|---|---|
| vless + ws over TCP | ~9.0–9.4 MB/s | 199 / 215 ms（抖动 ~16ms）|
| Hysteria2 / QUIC | ~15.9–18.5 MB/s | 197 / 239 ms（抖动 ~42ms）|

结论：**同落地下吞吐 Hysteria2 ≈ 2× vless+ws**，主要来自 QUIC 的拥塞控制 + 少一跳反代；延迟与抖动两者无明显差距。

拥塞控制要点（核对自 [Hysteria2 官方文档](https://hysteria.network/docs/advanced/Full-Server-Config/)）：

- **系统级 BBR（`net.ipv4.tcp_congestion_control=bbr`）只对 TCP 生效，Hysteria2 走 UDP/QUIC 完全不碰它**。这是个高频误区：在 VPS 上开了 BBR（属于内核 TCP 栈），加速的只是走 TCP 的协议（vless+ws、trojan、ss-over-tcp 等）；Hysteria2 是 QUIC over UDP、绕过整个内核 TCP 栈，它的拥塞控制由 Hysteria 程序在**用户态**自己实现，与 sysctl 那个 BBR 同名也无关。
- **Hysteria2 的拥塞控制按“客户端是否配带宽”协商**：客户端节点配了 `up`/`down`（且服务端没开 `ignoreClientBandwidth`）→ 用招牌的 **`Brutal`**（按设定带宽定速发包、基本无视丢包，高丢包跨国链路上能压过 TCP）；**没配 `up`/`down` → 回退到 Hysteria 内置的用户态 BBR v1**（仍是用户态实现，不是内核那个）。想吃满 Brutal 的抗丢包优势，要在客户端节点按真实带宽填 `up`/`down`。
- **vless+ws 的吞吐取决于服务端 TCP 拥塞控制**（落地机开系统 BBR 会好很多）+ 多一层反代开销（这里 Caddy→xray）；跨国高 BDP（带宽延迟积大）下 TCP cubic 慢启动/退避更吃亏。
- QUIC 单连接多 stream 消除了 TCP 那种跨流队头阻塞，但对“单条大文件下载”这不是主因，主因是上面的拥塞控制差异。

> 稳定性：节点抖动大会触发 URLTest 反复横跳、打断长连接，挑节点别只看平均延迟，自己 `/delay` 多采样看。vless+ws 若落在海外反代后面多一跳，日志里可能偶发 `dial ... :443 connect error: i/o timeout`（前置反代瞬时抖动）。

### 3.5 VLESS + WS + TLS 客户端配置

VLESS+WS+TLS 放在 Caddy/Nginx 后面是常见正经方案（复用已有 HTTPS 站点、证书自动续、端口复用、反代隐藏）。客户端要补齐 TLS 侧信息：

```yaml
proxies:
  - name: <node-name>
    type: vless
    server: <proxy-domain>
    port: 443
    uuid: <uuid>
    tls: true
    servername: <proxy-domain>      # 别留空，要和证书/反代站点/访问域名一致
    client-fingerprint: chrome      # 建议写在具体 proxy 上
    network: ws
    ws-opts:
      path: <websocket-path>
```

**MTU 默认就好**，别为“求稳”显式写死。只有出现大包症状（大文件下载中断、网页加载一半卡住、TLS 握手偶发超时、小请求通但大响应卡）才去测，从 `1400`/`1380` 起试。

## 4. 运行态管理：REST API

```yaml
external-controller: 127.0.0.1:9090
secret: ''
```

常用端点（适合脚本/AI 监控，CLI 默认不写日志文件，靠这些 API 看运行态）：

```bash
curl http://127.0.0.1:9090/configs      # 运行态通用配置(tun/端口/日志级别)；不显示配置文件路径
curl http://127.0.0.1:9090/proxies      # 节点组、testUrl、当前选择(.now)、健康
curl http://127.0.0.1:9090/connections  # 每条连接命中的规则/链路/网络/端口
curl --max-time 3 "http://127.0.0.1:9090/logs?format=structured&level=info"
curl --max-time 3 http://127.0.0.1:9090/traffic
```

**热重载**（配置在安全路径内时用 `path`）：

```powershell
$body = @{ path = "$env:USERPROFILE\.config\mihomo\config.yaml" } | ConvertTo-Json -Compress
Invoke-WebRequest -Uri 'http://127.0.0.1:9090/configs?force=true' -Method Put -ContentType 'application/json' -Body $body
```

配置不在安全路径内会报 `path is not subpath of home directory or SAFE_PATHS`——临时可用 `payload` 提交完整 YAML，但日常应直接维护默认位置的 `config.yaml`。

**改节点 / 测延迟**（group 名常含 emoji/中文，URL path 必须 `EscapeDataString`）：

```powershell
$enc = [uri]::EscapeDataString("🚀 节点选择")
Invoke-RestMethod -Method Put -Uri "http://127.0.0.1:9090/proxies/$enc" `
  -Headers @{ "Content-Type"="application/json" } -Body '{"name":"Hysteria2-Node"}' -TimeoutSec 5
(Invoke-RestMethod -Uri "http://127.0.0.1:9090/proxies/$enc").now   # 查当前
(Invoke-RestMethod -Uri "http://127.0.0.1:9090/proxies/$enc").all   # 列可选

# 测节点对真实目标的 delay（比 curl 测吞吐快几十倍，几秒出结果；失败节点抛 504）
$t = [uri]::EscapeDataString("https://<test-url>")
foreach ($n in @("vless-ws-Node","Hysteria2-Node")) {
  $r = Invoke-RestMethod -Uri "http://127.0.0.1:9090/proxies/$([uri]::EscapeDataString($n))/delay?url=$t&timeout=10000"
  Write-Host "$n delay=$($r.delay)ms"
}
```

> **`/delay` 通 ≠ 节点能跑全速**：它只测 1KB 级 RTT。真实吞吐要用 ≥50MB 文件测（前几 MB 在 TCP 慢启动，speed 偏小）；跑大量 KB 级小文件时看 `part/s` 而不是 `MiB/s`。

## 5. TUN 路由的边界

几条容易踩、值得先知道的事实：

- **`IP-CIDR,...,DIRECT` 不等于绕过 TUN**。它只是“流量进了 TUN 后，mihomo 选 `DIRECT` 这个 outbound”；`/connections` 里仍会看到 `inboundName: DEFAULT-TUN`、`chains:[DIRECT,...]`。真要某个目的地完全不进 TUN，是另一回事。（源码：TUN 入站固定打标 `listener/sing_tun/server.go` 的 `inbound.WithInName("DEFAULT-TUN")`；而 `rules/common/ipcidr.go` 的 `IPCIDR.Match()` 只返回出站 adapter 名，决定 outbound、不碰 inbound 拦截。）
- **规则顺序决定命中**：宽泛的 `RULE-SET,cn-ip`/`private-ip` 放在显式 `IP-CIDR` 前会先命中特例地址。需要特例策略就把特例规则提前——但提前命中 `DIRECT` 仍不是 TUN bypass。（源码 `tunnel/tunnel.go` 的 `match()` 从上往下首条命中即 `return`。）
- **`route-exclude-address` 不是稳定通用方案**：它只让 mihomo 不接管这些目的地址，**不保证** Windows 自动补出可用的物理网卡路由；排除异地组网依赖的公网 IP 后，可能把组网本身断开。需要对照时 `route print <peer-ip>` 看实际路由。（源码 `listener/sing_tun/server.go` 的 `RouteExcludeAddress`/`Inet4RouteExcludeAddress` 传给 tun 栈，作用是把这些地址从 TUN 的 auto-route 里排除；OS 有没有可用物理路由是系统路由表的事，mihomo 不补。）

排障先分清“远端节点不通”还是“本机 TUN/入口没接管”：

```powershell
curl.exe -v -I --max-time 12 <test-url>                               # 裸连(走 TUN/系统路由)
curl.exe -v -I --max-time 12 --proxy http://127.0.0.1:7890 <test-url> # 显式走 mixed-port
```

显式 `--proxy` 稳定成功、而裸 `curl` 失败或命中 fake-ip 后报连接错误 → 优先查 TUN/系统路由/DNS 劫持/权限环境，别一上来就怪远端节点。

### 5.1 WSL ssh 借道宿主 mihomo（没开 TUN 时才需要）

WSL2（NAT 模式）里 ssh 走宿主 mihomo：HTTP 客户端设 `HTTPS_PROXY` 即可，但 ssh 走 SOCKS、要 `ProxyCommand`，且 NAT 下宿主在 WSL 网段的 IP（=默认网关）每次启动可能变，得现取：

```sshconfig
Host <要走代理的远端>
    ProxyCommand sh -c 'gw=$(ip route show default 2>/dev/null | awk "{print \$3; exit}"); exec nc -x "${gw:-172.28.80.1}:7890" -X 5 "$0" "$1"' %h %p
```

**宿主 mihomo 开了 TUN 时这条多余**——TUN 透明接管，WSL 里 ssh 直连目标即被接管，连解析成 fake-ip 的自建域名也直接通。只有“没被 TUN/规则覆盖、直连出不去”的目标才需要它。Mirror 模式下 WSL 与宿主共享 `127.0.0.1`，可直接 `127.0.0.1:7890`、不必取网关（见 [network.md](network.md)）。

## 6. 从源码构建（Windows）

`MetaCubeX/mihomo` 的 `Meta` 分支。切到 release tag 再构建：

```powershell
cd "$env:USERPROFILE\mihomo"
git checkout v1.19.24
git describe --tags --exact-match
```

官方 `mihomo-windows-amd64`（无 v1/v2/v3 后缀那个）对应 `GOOS=windows GOARCH=amd64 GOAMD64=v3` + build tag `with_gvisor`，中间产物默认 `mihomo.exe`：

```powershell
$env:GOOS="windows"; $env:GOARCH="amd64"; $env:GOAMD64="v3"
go build -v -tags "with_gvisor" -trimpath `
  -ldflags "-X 'github.com/metacubex/mihomo/constant.Version=v1.19.24' -X 'github.com/metacubex/mihomo/constant.BuildTime=$(Get-Date -Format r)' -w -s -buildid=" `
  -o mihomo-windows-amd64.exe .   # 不写 -o 会覆盖当前目录 mihomo.exe；exe 正在运行会因占用构建失败
```

`go build` 只产 exe，release 里的 `.zip` 是 workflow 额外 `Compress-Archive` 出来的。验证：

```powershell
.\mihomo.exe -v
# 期望: Mihomo Meta v1.19.24 windows amd64 / Use tags: with_gvisor
```

---

# 第二部分：泄漏控制

## 7. DNS 泄漏：原理、劫持与 enhanced-mode

这一节是理解代理“干不干净”的关键，配置和原理必须一起讲。

### 7.1 三方模型：DNS 泄漏泄给了谁

解析一个域名牵涉**三方**，不是两方：

1. **你**（客户端）。
2. **递归解析器（recursive resolver）**：你系统里配的那个“查号台”，家用网络下通常是**运营商（ISP，Internet Service Provider，互联网服务提供商）**的。它知道**你查过哪些域名**——一份完整的访问清单，哪怕你后续连的是 HTTPS、内容它看不到，“你去了哪些站”它有。
3. **权威服务器（authoritative server）**：被查域名主人自己开的“总台”，最终答案从这儿出。它能看到**是哪个递归解析器来问的**（来问者的出口 IP）。

所以 **DNS 泄漏 = 你的查询跑去了一个你不想让它知道的解析器（通常是 ISP 的）**，于是运营商攒下了你的域名清单，还能据此**按域名封锁 / 投毒**（故意回错 IP，就是 GFW 的 DNS 污染）。代理的目标因此不只是“内容走代理”，还要“DNS 也别落到 ISP 解析器手里”。

### 7.2 两个正交的开关：dns-hijack 与 enhanced-mode

防不防泄漏、返回真 IP 还是假 IP，是**两个独立的开关**：

#### 开关 A：`dns-hijack`（TUN 的功能）——决定“查询进不进 mihomo”

TUN 把流量劫进来后，判断是不是 DNS 包、要不要转给 mihomo 自己的 DNS。源码 `listener/sing_tun/dns.go` 的 `ShouldHijackDns`：

```go
func (h *ListenerHandler) ShouldHijackDns(targetAddr netip.AddrPort) bool {
    for _, addrPort := range h.DnsAddrPorts {
        if addrPort == targetAddr ||
           (addrPort.Addr().IsUnspecified() && targetAddr.Port() == 53) { // any:53
            return true
        }
    }
    return false
}
```

`any:53` 的语义就是这行 `IsUnspecified() && Port()==53`：**发往任意 IP 的 53 端口包全部命中**，命中就 `RelayDnsConn`/`RelayDnsPacket` 交给 mihomo 内置 DNS。这是防泄漏的**闸门**——哪怕某个 app 硬编码了 `8.8.8.8`，:53 包也照样被拦下，逃不掉。

> 漏网之鱼：hijack 只盯明文 :53。应用要是自己走 **DoH(443) / DoT(853)** 查，这道闸拦不住——这也是为什么排障时用 DoH 能“绕过”mihomo 看到真实 DNS 记录。

#### 开关 B：`enhanced-mode`（DNS 的功能）——决定“进来后 mihomo 回什么”，三选一

源码 `dns/enhancer.go` 里 mode 只有三种：`DNSNormal` / `DNSMapping`(=redir-host) / `DNSFakeIP`。对应 `dns/middleware.go` 三个中间件：

- **`fake-ip`**（`withFakeIP`）：
  ```go
  if skipper.ShouldSkipped(host) { return next(ctx, r) } // fake-ip-filter 命中才放行去真解析
  ip := fakePool.Lookup(host)   // 直接给一个池子里的 198.18.x，不 call next（当场不做真解析）
  ```
  应用瞬间拿到假 IP，**真解析推迟到连接时、在远端做**。最快、分流最准、最防污染。代价：少数按 IP 工作的程序会坏（见 7.4 的 `fake-ip-filter`）。
- **`redir-host`**（`withMapping`）：
  ```go
  msg, err := next(ctx, r)             // 先做真解析，拿真 IP
  mapping.SetWithExpire(ip, host, ...) // 再记下 ip→域名 映射
  ```
  回**真 IP**，但记住“这个 IP 是哪个域名的”，连接时还能按域名分流。代价：每次要等真实解析、上游被污染会拿到污染结果。
- **`normal`**：啥都不加，回真 IP、也不记映射。**分流退化**为只能按 IP（域名信息丢了，按域名的规则可能判错）。

### 7.3 行为对照表

| dns-hijack | enhanced-mode | 普通查询(`getent`)拿到 | 分流准度 | DNS 泄漏风险 |
|---|---|---|---|---|
| **关** | 任意 | 真 IP（走系统 resolv.conf 的 DNS） | 看 app | **高** ← 泄漏就这儿来 |
| 开 | fake-ip | `198.18.x` 假 IP | 最准（按域名） | 低 |
| 开 | redir-host | 真 IP | 准（靠 ip→域名 映射） | 低 |
| 开 | normal | 真 IP | 退化（只有 IP） | 低（但分流变差） |

一句话：**泄漏由 A（hijack）决定**（查询进不进 mihomo），**真假 IP 与分流准度由 B（enhanced-mode）决定**——两者无关。把“返回 198.18.x”算在 hijack 头上是常见误解：返回假 IP 是 fake-ip 干的，hijack 只负责“把你抓进来”。

### 7.4 推荐配置

防泄漏 + 分流准 + 防污染的一套：

```yaml
ipv6: false                 # 关 IPv6 时，DNS 的 ipv6 也保持一致，免得解析出不可用地址
tun:
  enable: true
  stack: mixed
  auto-route: true
  auto-detect-interface: true
  strict-route: true
  dns-hijack:
    - any:53                 # 闸门：拦下所有明文 :53
dns:
  enable: true
  ipv6: false
  enhanced-mode: fake-ip     # 真假 IP/分流：fake-ip 最优
  respect-rules: true        # 让 DNS 查询也尊重 rules（决定上游 nameserver 走代理还是直连）
  fake-ip-range: 198.18.0.1/16
  fake-ip-filter:            # 这些域名回退真解析（按 IP 工作的、局域网的、NTP 等）
    - '*.lan'
    - '*.local'
    - 'time.*.com'
  nameserver:                # 真正的上游解析器；配 DoH/DoT 让上游解析也加密、不落 ISP
    - https://223.5.5.5/dns-query
    - https://1.1.1.1/dns-query
```

要点：`dns-hijack any:53` 堵住泄漏闸门；`fake-ip` 给快且准的分流；`nameserver` 用 **DoH/DoT** 让“上游解析”这步也加密、并配合 `respect-rules` 走代理出去——这样 ISP 既看不到你的明文查询，也截不到上游往哪查。`fake-ip-filter` 里的 `skipper`（源码 `component/fakeip/skipper.go`）让排除的域名走真解析，避免坏掉 ping、局域网设备、按 IP 比对的软件。

### 7.5 验证与排查：browserleaks/dns 原理

**`browserleaks.com/dns` 凭什么知道你 DNS 泄漏？** 它把自己设成了“被查域名的权威总台”：

1. 给你一个**独一无二的随机子域**，如 `7f3a9k2.dnsleaktest.browserleaks.com`（每个访客不同）。
2. 你的浏览器解析它 → 世界上只有 browserleaks 的权威服务器知道这个怪名字 → 查询**一定层层转到它的总台**。
3. 总台看到“`7f3a9k2` 是从 IP=202.x（某 ISP 的解析器）来问的” → 于是知道你**实际用的解析器是谁、在哪个运营商/国家**，并靠那个专属随机名跟你这次会话对上号。
4. 判定：你挂着境外节点、却被发现解析器在“中国电信·杭州” → DNS 漏在了本地。

对照“是谁看到了什么”：**ISP 解析器看到「你要去哪」；域名权威台看到「是谁在替你问」**。browserleaks 故意当后者，所以能识破 DNS 出口。

**排障时怎么看真实记录**（绕开本机 fake-ip/hijack 的两招）：

```bash
# DoH：走 443 不碰 :53，hijack 拦不到，拿到真公网解析
curl -s "https://223.5.5.5/resolve?name=<域名>&type=A"
# --resolve：根本不查 DNS，直接把域名钉到指定 IP（验某个后端时用）
curl --resolve <域名>:443:<IP> https://<域名>/
```

> 普通 `dig`/`nslookup`/`getent`/`host` 在开了 `dns-hijack any:53` 的机器上会被劫持、回 `198.18.x`，不是真记录——别拿它们当 DNS 真相。

## 8. WebRTC 泄漏：原理与处理

WebRTC 泄漏和 DNS 泄漏**是两回事**，很多人混在一起。

### 8.1 原理：浏览器自己把公网 IP 暴露出来

网页里的 `RTCPeerConnection`（WebRTC 用于音视频/P2P）建连前要“收集 ICE 候选地址”，其中一步是**向 STUN 服务器发 UDP 探测**问“我的公网 IP 是多少”。STUN 服务器照实回它看到的来源 IP——**如果这个 UDP 没走代理，它看到的就是你真实出口 IP**。然后网页用 JS（`onicecandidate`）读到这些候选，直接显示出来。

所以和 DNS 泄漏的检测方式正好相反：

- **DNS 泄漏**：服务端（权威台）侧识破“替你查的解析器”。
- **WebRTC 泄漏**：**你自己浏览器**里就能读到 STUN 探测回来的公网 IP——`browserleaks.com/webrtc` 就是读这些 ICE 候选，比对“WebRTC Public IP”和你的代理出口是否一致；不一致（露出真实 ISP IP）= 泄漏。

### 8.2 处理：让 STUN 的 UDP 别走真实出口

核心思路是正向的：**保证这些 STUN/TURN 的 UDP 探测要么走代理、要么直接拒掉**，让它们拿不到你的真实 IP。在规则里精准处理常见 STUN/TURN 端口：

```yaml
rules:
  # 直接拒绝常见 STUN/TURN 探测（最稳，浏览器拿不到公网 candidate）
  - AND,((NETWORK,UDP),(DST-PORT,19302)),REJECT       # 19302 常见于 Google STUN
  - AND,((NETWORK,UDP),(DST-PORT,3478-3481)),REJECT    # 3478-3481 常见 STUN/TURN
  # …这些要放在 RULE-SET(cn)/GEOIP,CN/MATCH 等宽泛规则【前面】
```

这些端口只是**常见**探测端口、不是“所有 WebRTC 端口”。先精准拒这几个；若 `/connections` 里还看到新的 UDP STUN/TURN 出口，再按日志补规则。若你需要 WebRTC 能用（如开会），则改成把这些 UDP 指向代理 group 而不是 REJECT。

### 8.3 用运行态连接验证

排查时别只看网页上的数字，对照 mihomo 运行态：

```bash
curl -s http://127.0.0.1:9090/connections
curl -s --max-time 3 "http://127.0.0.1:9090/logs?format=structured&level=info"
```

重点字段：`host`（访问的域名/STUN 域名）、`network`（tcp/udp）、`destinationPort`（STUN 常见 19302、3478-3481）、`chains`（最终是代理节点 / `DIRECT` / `REJECT`）、`rule`/`rulePayload`（是否被 `cn`/`GEOIP,CN`/`MATCH` 误命中）。看到 STUN 的 UDP 命中 `DIRECT` 就是泄漏源。

---

# 附录：已知风险记录（待长期验证）

**长期跑 Hysteria2，落地 IP 疑似被大陆精准屏蔽**（2026-06-08 单次事件，根因未坐实，记录供下次对照）：某海外 VPS 的 Hysteria2 主节点跑一段时间后，某天起从**大陆任何出口**对这台 IP 的任何端口（22/443/ICMP）全 timeout，而**同 /24 邻居 IP 正常**、境外多地探测全通、VPS 本机服务健康——形态像“大陆精准屏蔽这一个 IP”。

可能原因（未验证）：QUIC over UDP 单 IP 持续大流量是 GFW 主动探测的特征之一；落地 IP 注册了公开域名长期暴露；也可能是机房 IP 段整体波及、与协议无关。

对照实验：停掉 Hysteria2 监听等 24~72h 看 IP 是否恢复（恢复=支持“代理流量触发”假设）。缓解：从大陆侧 ssh 改 `ProxyJump` 经境外不受影响的跳板；彻底解决换 IP + 把协议迁离这台（或换 Reality / 强 fingerprint masking 的 vless）。
