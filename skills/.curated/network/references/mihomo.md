# Mihomo 代理：配置与泄漏控制

> 本文把 Mihomo 的**配置用法**和**泄漏控制（DNS / WebRTC）**结合着讲，目标是读完能自己搭一套“不漏、分流准、能排障”的代理，并理解每个开关到底在做什么。全文分两部分：前半是**配置与使用**，后半是**泄漏控制**。WSL ↔ Windows ↔ 远端的网络管道是另一回事——WSL 出站怎么进 Mihomo、portproxy/wslrelay 入站见 [wsl.md](wsl.md)，RDP / serve-web 等远程接入见 [remote.md](remote.md)。

**源码基准与 clone**：下文凡讲到内部行为，都对照官方仓库 `MetaCubeX/mihomo` 的 **`Meta` 分支**（稳定线；开发线是 `Alpha`）。要 Go 源码（`module github.com/metacubex/mihomo`）：`git clone -b Meta`；已经 clone 停在默认的 `main` 上，直接 `git checkout Meta`（或 `git switch Meta`）即可——单 remote + 全量 refspec 下 Git 的 DWIM 会自动基于 `origin/Meta` 建同名跟踪分支（实测 exit 0）。

> **⚠️ 为什么 clone 出来像个星铁 Python 包（是伪装，不是仓库被劫持）**
> 这仓库**默认分支就是 `main`、装的是一个同名的 Honkai: Star Rail Python 包（`pyproject.toml`），不是代理内核**——`git clone` 不带分支就落到 `main`。这是维护者**故意的伪装**：把默认分支和仓库元数据设成一个真实存在的星铁 pydantic 包，以规避审查 / 下架 / 爬虫扫描。实测 `gh api` 与 GitHub MCP 双通道一致：`default_branch=main`、`language:Python`、`topics:[honkai-star-rail,…]`，而 3.2 万 star、`wiki.metacubex.one` 主页仍是内核的、`Meta`/`Alpha` 等内核分支原封未动——**只换门面、核心没动，所以是伪装不是劫持**。

> **背景：Clash 系为何在 2023-11-02 集体删库伪装**
> 2023-11-02，Clash 内核 `Dreamacro/clash`（Go 核心引擎，mihomo 即由它 fork 而来）与最流行的 GUI 客户端 Clash for Windows（`Fndroid/clash_for_windows_pkg`，作者 Fndroid）在**同一天各自删库**；此后 Clash 系普遍把仓库门面伪装成无关项目以规避审查 / 下架 / 爬虫扫描。
> - **是作者自行删库、非版权 / DMCA 处置**：实测二者今均为**纯 404** 而非 451 DMCA 下架页，GitHub 官方 `github/dmca` 存档亦零命中，加之作者当日公开自宣停更删库。
> - **Wayback 取证**：Wayback（Wayback Machine，互联网档案馆 Internet Archive 运营的“网页时光机”`web.archive.org`，定期抓取并永久保存网页快照、可回看某 URL 过去某时点的样子，原页删了也能看）显示，这两个仓库最后一张能正常打开的快照都止于 **2023-11-02**——把删库时点钉在那天。
> - **停更原因**：作者仅称“不可抗力”；社区普遍推测系其**推特自曝的个人信息被顺藤定位、遭约谈“请喝茶”**，援引线索包括推特照片暴露的所在城市（湖南/长沙）、部分车牌 + 车型、购物 / 充电记录、京东订单截图等，但**官方从未证实**，各版本均属社区推测。参见中国数字时代存档 `chinadigitaltimes.net/chinese/701751`。

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
- **设了 `HTTPS_PROXY` ≠ 流量一定走代理节点**。env 只决定“流量送进 Mihomo 哪个入口端口”，**出口走哪个节点完全由 `rules` + `proxy-groups` 决定**（见[第 3 节](#3-流量链路入口规则与节点组)）。

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
- **从源码构建**：见[第 8 节](#8-从源码构建windows)。

> 很多 GUI 客户端（Clash Verge Rev、FlClash 等）**内置了 mihomo 内核**，装它们就不用单独装内核；只有要纯内核 / 做服务端常驻时才手动装上面这些。
>
> **但 GUI 捆绑的内核 ≠ 你自装的 CLI——是多套各自独立、可共存的二进制**。每个 GUI 把自己的 mihomo（常改名）放在各自程序目录：实测同一台 Windows，Clash Verge → `Program Files\Clash Verge\verge-mihomo.exe`、Clash Party（mihomo-party）→ `...\Clash Party\resources\sidecar\mihomo.exe`；你自装的 CLI 又是独立第三套（如 `C:\Users\<user>\mihomo\mihomo.exe`，靠 `-d` 指向 `~/.config/mihomo`）。**谁在实际跑，看进程的 `-d`/`-f` 启动参数**（[§6](#6-运行态控制rest-api-与-web-面板)；Windows 上内核可能高权限跑、需 UAC 提权才读得到命令行）。推论：删某个 GUI 的**用户数据**（`AppData\Roaming|Local` 里的 profile / 订阅 / 缓存）既不动它程序目录里的内核、也不影响另一套独立跑着的 CLI——所以清 GUI 数据不会断掉一个单独常驻的 mihomo。

### 2.2 配置目录是运行时算出来的（不是安装决定的）

容易误解的一点：`~/.config/mihomo` 这个路径**和二进制装在哪无关**，是 mihomo 启动时按“当前用户的主目录”现算的。源码见 [`constant/path.go` 的路径解析逻辑](https://github.com/MetaCubeX/mihomo/blob/24b6de71fc1c4ea282dcbc7b65a8bcbcc0c75e6c/constant/path.go#L29-L40)（pin 到与 [§6](#6-运行态控制rest-api-与-web-面板) 同一 commit `24b6de71`、行号锁死不漂移；下方为节选）：

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
- 命令行覆盖：`-d <dir>` 改配置目录（源码 [`SetHomeDir`](https://github.com/MetaCubeX/mihomo/blob/24b6de71fc1c4ea282dcbc7b65a8bcbcc0c75e6c/constant/path.go#L62)），`-f <file>` 改配置文件名（[`SetConfig`](https://github.com/MetaCubeX/mihomo/blob/24b6de71fc1c4ea282dcbc7b65a8bcbcc0c75e6c/constant/path.go#L67)）。
- **“安全路径”**：REST API 用 `path` 方式热重载（见[第 6 节](#6-运行态控制rest-api-与-web-面板)）默认只允许 home 的子路径；要放别处可用环境变量 `SAFE_PATHS` 加白名单，或 `SKIP_SAFE_PATH_CHECK=1` 整个关掉检查（源码 [`IsSafePath`](https://github.com/MetaCubeX/mihomo/blob/24b6de71fc1c4ea282dcbc7b65a8bcbcc0c75e6c/constant/path.go#L88)）。

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

### 2.4 GUI 客户端（Clash Verge Rev）：配置链与改端口

GUI 客户端不直接用 mihomo 的 `config.yaml`，而是自己生成一份运行时配置喂给内嵌内核——直接改底层文件会被覆盖或不重载。以 Clash Verge Rev（核心进程 `verge-mihomo`）为例：

- **配置链**：基础 `config.yaml` + 当前 profile/merge/script → 生成 `clash-verge.yaml` → GUI 经命名管道 `\\.\pipe\verge-mihomo` 推给核心热重载。
- **改端口**：`verge.yaml` 的 `verge_mixed_port` 普通启动时并不驱动运行时端口；真正生效的是**基础 `config.yaml` 的 `mixed-port`**（`clash-verge.yaml` 启动时会被从 `config.yaml` 重新生成覆盖，单改无效）。先完全退出 GUI 再改，重启后核心日志出现 `Mixed(http+socks) proxy listening at: [::]:<port>` 即成功。
- **系统代理端口与核心端口错位**：实测 Windows 上 `verge_mixed_port` 可能仍被 Verge 用作系统代理的目标端口，而核心实际监听的是基础 `config.yaml` / 生成配置里的另一个 `mixed-port`。两者不一致时，Windows 系统代理会指向无人监听的旧端口；表现为所有 profile 都无法联网，很容易误判成订阅或节点故障。先用 `curl.exe -x http://127.0.0.1:<核心端口> https://www.gstatic.com/generate_204` 直测核心：若返回 `204`，再对照 `verge.yaml` 的 `verge_mixed_port`、`clash-verge.yaml` 的 `mixed-port`、`Get-NetTCPConnection -State Listen` 的实际监听端口，以及注册表 `HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings` 的 `ProxyEnable` / `ProxyServer`。修复时完全退出 GUI，把 `verge_mixed_port` 与核心端口对齐后重启；若系统代理原本关闭，旧 `ProxyServer` 只是残留值，要重新打开系统代理才会生效。
- **核心由 SYSTEM 服务托管**：`verge-mihomo` 归 `clash-verge-service` 管，非提权 shell 杀不掉（`Stop-Process` 报拒绝访问）；靠重启 GUI 让服务重拉核心。

## 3. 流量链路：入口、规则与节点组

### 3.1 入口方式

- **`mixed-port`（显式代理）**：应用主动把流量发到这个端口（HTTP/SOCKS 混合）。适合“只想让特定程序走代理”。
  ```yaml
  mixed-port: 7890
  allow-lan: true        # 总开关：关(默认)→ 只听 127.0.0.1，外面进不来；开 → 才允许超出回环
  bind-address: '*'      # 仅 allow-lan 开时才读：* = 所有网卡(0.0.0.0)，填具体 IP = 只听那张网卡
  ```
  两者是「开关 + 过滤器」不是两种等效写法：**开不开 LAN 看 `allow-lan`，开了之后听哪儿才看 `bind-address`**。所以单写 `bind-address` 而不开 `allow-lan` 没用，照样只听回环。要对外时**别绑某个具体虚拟网卡地址**——网卡重连/地址变化/启动顺序变了，就会间歇连不上代理端口。
  > **源码** `listener/listener.go` 的 `genAddr(host, port, allowLan)`：`allow-lan` 关时直接返回 `127.0.0.1:port`（无视 `bind-address`），开时 `bind-address=*` → `:port`（全听）、否则 `host:port`。

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

- **`mode: rule` 下的兜底是规则表最后一条 `MATCH`，不是 GLOBAL**。规则**从上往下、首条命中即止**；最后那条 `MATCH,<某组>` 把“前面规则都没命中的流量”兜走——订阅里这个组常被命名为 `🐟 漏网之鱼`。`GLOBAL` 是另一个东西：内置的“装了所有节点和分组”的选择器，**只有切到 `mode: global` 时才用它接管一切**。所以 rule 模式下改 GLOBAL 没用——要改就找命中目标的那条 rule、定位到它指向的组。
  > **源码**：`tunnel/tunnel.go` 的 `match()` 循环里 `return` 首个命中的 rule、一条都没命中才落到 `DIRECT`；`mode: global` 时才走 `case Global: proxy = proxies["GLOBAL"]`。
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
- **切节点只对新建连接生效**。长跑的下载/上传/WebSocket 要重连才走新节点；单独启动一个新的 `curl` 进程即可得到新连接。`--no-keepalive` 只关闭 TCP keepalive 探针，并不等于禁止 HTTP 连接复用，别把它当“强制换节点”开关。

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

## 4. 协议、性能与客户端配置

### 4.1 协议选型与性能

**经验法则**：跨国（高延迟、可能丢包）链路优先 QUIC 系（Hysteria2 / TUIC）；vless+ws+TCP 适合穿 CDN/反代，但传输层受 TCP 拥塞控制限制。

实测（2026-06-27，两个节点落地在同一台海外 VPS：Hysteria2=UDP 443 直连，vless+ws=TCP 443 经 Caddy→xray 多一跳；本机 mihomo 经 7890 拉 Cloudflare 50MB，延迟取 8 次采样）：

| 协议 | 实测吞吐 | 延迟抖动(min/max) |
|---|---|---|
| vless + ws over TCP | ~9.0–9.4 MB/s | 199 / 215 ms（抖动 ~16ms）|
| Hysteria2 / QUIC | ~15.9–18.5 MB/s | 197 / 239 ms（抖动 ~42ms）|

结论：**同落地下吞吐 Hysteria2 ≈ 2× vless+ws**，主要来自 QUIC 的拥塞控制 + 少一跳反代；延迟与抖动两者无明显差距。

拥塞控制（核对自 [Hysteria2 官方文档](https://hysteria.network/docs/advanced/Full-Server-Config/)）：

- **系统级 BBR（`net.ipv4.tcp_congestion_control=bbr`）只对 TCP**：它加速的是 vless+ws / trojan 这类走 TCP 的协议；Hysteria2 是 QUIC over UDP、绕过内核 TCP 栈，拥塞控制在**用户态**自己实现，和 sysctl 那个 BBR 同名也无关。
- **Hysteria2 两种控制器**：BBR（默认，自适应）vs **Brutal**（按设定带宽定速发包、基本无视丢包，高丢包跨国链路上能压过 TCP）。选哪个在握手时协商，规则就两条：
  - 客户端节点填了 `up`/`down` **且**服务端没开 `ignoreClientBandwidth` → **两个方向都 Brutal**（下载用 `down`、上传用 `up`；服务端没配 `bandwidth` 就直接用客户端的值）。
  - 客户端没填、或服务端 `ignoreClientBandwidth: true` → 回退 BBR。
  - 源码：客户端 `metacubex/sing-quic` 的 `hysteria2/client.go` 判 `if !RxAuto && actualTx>0 → Brutal`；服务端 `apernet/hysteria` 的 `core/server/server.go` 里 **`RxAuto = ignoreClientBandwidth`**（就这一个开关，跟服务端有没有设带宽无关）。回退的 BBR 是 mihomo 用户态 `congestion_v2.NewBbrSender`（其内部记作 v2），不是内核 BBR。
  - 想吃满 Brutal 抗丢包：按真实带宽填 `up`/`down`（**别填超真实容量**，过冲只会多发→无谓重传），服务端别开 `ignoreClientBandwidth`——个人自用，服务端 `bandwidth`/`ignoreClientBandwidth` 都别配。
- **vless+ws 的吞吐**取决于服务端 TCP 拥塞控制（落地机开系统 BBR 会好很多）+ 反代多一跳；跨国高 BDP（带宽延迟积大）下 TCP cubic 慢启动/退避更吃亏。QUIC 单连接多 stream 还消除了 TCP 的跨流队头阻塞（但单条大文件下载里这不是主因，主因是上面的拥塞控制差异）。

> 稳定性：节点抖动大会触发 URLTest 反复横跳、打断长连接，挑节点别只看平均延迟，自己 `/delay` 多采样看。vless+ws 若落在海外反代后面多一跳，日志里可能偶发 `dial ... :443 connect error: i/o timeout`（前置反代瞬时抖动）。

### 4.2 VLESS + WS + TLS 客户端配置

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

### 4.3 实测吞吐与验证（客户端排障）

节点 `/delay` 只测 1KB 级 RTT（见[第 6 节](#6-运行态控制rest-api-与-web-面板)），拥塞控制有没有真生效得自己测吞吐。经 `mixed-port` 用 curl 的 `-w` 直接拿 speed、不落盘：

```bash
P=http://127.0.0.1:7890
# 下载
curl -s -o /dev/null --max-time 45 --proxy $P \
  -w 'dl=%{speed_download}B/s code=%{http_code}\n' "https://ash-speed.hetzner.com/100MB.bin"
# 上传
head -c 31457280 /dev/urandom > /tmp/up.bin
curl -s -o /dev/null --max-time 45 --proxy $P \
  -w 'ul=%{speed_upload}B/s\n' --data-binary @/tmp/up.bin "https://speed.cloudflare.com/__up"
```

测速源踩坑：`speed.cloudflare.com/__down` 经某些落地 IP 回 **403**（节点 IP 命中 Cloudflare 风控），但同站 `__up` 上传能用；Hetzner `ash-speed.hetzner.com/100MB.bin` 稳，OVH `proof.ovh.net` 能用但跨洲偏慢。多换源交叉看、文件 ≥50–100MB（前几 MB 慢启动偏小）。换算：1 MB/s ≈ 8 Mbps。

> **验证 Brutal 有没有接管**：mihomo 不暴露 `brutal-debug`，客户端日志看不到 Brutal 速率，唯一办法是 sudo 读服务端 `/etc/hysteria/config.yaml` 看 `ignoreClientBandwidth`/`bandwidth`（机制见 [§4.1](#41-协议选型与性能)）。服务端那套：独立 Hysteria2 搭建见 [hysteria2.md](hysteria2.md)，3x-ui 面板配置见 [3x-ui.md](3x-ui.md)，带宽/iperf3 丢包质量测试见 `vps-maintenance` skill，客户端、服务端两边配合看。

海外 VPS 上实测：给 Hysteria2 节点加 `up: "80 Mbps"`/`down: "120 Mbps"`（格式正则 `^(\d+)\s*[KMGT]?[Bb]ps$`，小写 `b`=bit）后，下载上传两向都进 Brutal——但当时链路 ~16 MB/s 下载、~9 MB/s 上传、**几乎无丢包**，加 `up`/`down` 前后吞吐无差异，印证「Brutal 收益要丢包才显现」。

## 5. 订阅与覆写：内核只封装「节点级」，没有「配置级」

常被问“mihomo 内核有没有替订阅 URL 封装覆写功能”。**分两层看，答案不一样**：

- **配置级订阅覆写——内核没有**。“拉一个订阅 URL → 改写整份 clash 配置（`rules` / `proxy-groups` / `dns` …）”这种能力不在内核里；内核只从本地文件 / bytes 读一份**已经组装好**的配置。整份配置级的 merge / script 覆写是**外部工具**的事——Clash Verge Rev / mihomo-party 这类 GUI 的 profile override，或 Sub-Store / subconverter 这类订阅转换器。⚠️ 别被 `config/config.go` 里的 `override` 带偏：那里唯一的 `override` 是 `override-destination`（嗅探器 sniffer 改写目标地址），**跟订阅无关**。
- **节点级订阅覆写——内核封装得很完整**，全挂在 **proxy-provider（订阅节点源，`type: http` + `url` 就是“URL 订阅”）** 上，源码在 `adapter/provider/`：
  - **改字段** `override.go` 的 `overrideSchema.Apply()`：对订阅里**每个节点**改 `tfo/mptcp/udp/udp-over-tcp/up/down/dialer-proxy/skip-cert-verify/interface-name/routing-mark/ip-version`；改名类 `additional-prefix`/`additional-suffix` 和 `proxy-name`（正则 `pattern`→`target` 批量重命名，用 regexp2 即 .NET 风格正则，比 Go 原生正则语法更全）。
  - **筛选** `parser.go` 的 schema：`filter` / `exclude-filter`（正则，多组用反引号 `` ` `` 分隔）/ `exclude-type`（按节点类型排除，`|` 分隔）。
  - **拉取流程** `provider.go` 的 `NewProxiesParser`：HTTP 拉取（`header` 自定义请求头 / `proxy` 借某代理去拉 / `size-limit` / `age-secret-key` 解密）→ YAML 解析（失败回退 `ConvertsV2Ray`，兼容机场那种 base64 / `vmess://` 订阅）→ exclude/filter 过滤 → 去重 → `override.Apply` 覆写 → `ParseProxy`。
- 另有 **rule-provider**（`rules/provider/`）远程规则集，也算“远程覆写”，但覆的是**规则**不是节点。

**心智模型：节点级 override「覆写之后给谁」？——内核自用、没有下游。** 这是“覆写”这词最容易带偏的地方，单独说清。别把它理解成“改完转交下游”：节点级 override 的覆写对象，是**从订阅 URL 拉下来的那份原始节点清单**（机场给的、源头你改不动）；覆写发生在“**外部订阅数据 → 内核内部节点对象**”这个**装载 / 入口边界**上——内核在把别人给的数据收进自己肚子前，先按你的 `override` / `filter` 清洗一遍，然后**内核自用**（供 proxy-group 选择、被规则命中后建连接）。字段名 `override` 是“覆盖每个节点原本的字段值 / 补上它没有的字段”，不含“转交”义。

两层的数据流方向正好相反，对照就不会混：

| | 谁改的 | 内核的角色 | 有没有下游 |
|---|---|---|---|
| **配置级覆写** | 外部工具改好**整份配置** → 喂给内核 | 内核是**下游**（接收方） | —— |
| **节点级 override** | 内核自己在入口清洗拉进来的节点 | 内核是**发起方 + 使用方** | **没有**——你直觉里那个“给谁”在这层不存在 |

一句话：**节点级（proxy-provider 的 `override` + `filter`）有且完整；整份配置级订阅覆写内核不管，交给外部管理程序 / 订阅转换器。**

## 6. 运行态控制：REST API 与 Web 面板

控制面 = REST API（本节）+ 可选 Web Dashboard（[§6.1](#61-web-面板external-ui--ui-路径)）。它是“遥控器”：**只查运行态、改运行态（切节点 / 模式 / 热重载 / 改单项），既不碰也不回吐配置文件**。配置里开：

```yaml
external-controller: 127.0.0.1:9090   # 绑回环自用；要被 mesh/LAN 访问才绑 0.0.0.0（那时必设 secret）
secret: ''                            # 非空 = 所有 REST 调用都要带 token
```

> **`secret` 非空 = 所有 REST 调用要带 `Authorization: Bearer <secret>`**（websocket 方式访问的流式端点如 `/logs`、`/traffic` 改用 URL 参数 `?token=<secret>`）。缺失或不匹配一律 HTTP 401 `{"message":"Unauthorized"}`——见 [`authentication` 中间件源码](https://github.com/MetaCubeX/mihomo/blob/24b6de71fc1c4ea282dcbc7b65a8bcbcc0c75e6c/hub/route/server.go#L336)（`safeEqual` 常数时间比较 token）。所以裸 `curl http://127.0.0.1:9090/` 回 `{"message":"Unauthorized"}` 只说明**这个实例设了 secret**、不代表 mihomo 挂了——加 `-H "Authorization: Bearer <secret>"` 即通。绑回环自用可留 `secret: ''` 免认证。**真实 secret 不入库，占位即可。**

**读运行态**——常用端点（适合脚本/AI 监控，CLI 默认不写日志文件，靠这些 API 看运行态）：

```bash
curl http://127.0.0.1:9090/            # {"hello":"mihomo"} —— 确认这个端口是不是 mihomo 的最快探针
curl http://127.0.0.1:9090/version      # {"meta":true,"version":"v1.19.x"} —— meta 内核标志 + 版本
curl http://127.0.0.1:9090/configs      # 运行态通用配置(tun/端口/日志级别)；不显示配置文件路径
curl http://127.0.0.1:9090/proxies      # 节点组、testUrl、当前选择(.now)、健康
curl http://127.0.0.1:9090/connections  # 每条连接命中的规则/链路/网络/端口
curl --max-time 3 "http://127.0.0.1:9090/logs?format=structured&level=info"
curl --max-time 3 http://127.0.0.1:9090/traffic
```

> **源码实证：没有任何端点回吐"当前配置文件路径"**（链接 pin 到 `MetaCubeX/mihomo` 的 `Alpha` 分支 commit [`24b6de71`](https://github.com/MetaCubeX/mihomo/tree/24b6de71fc1c4ea282dcbc7b65a8bcbcc0c75e6c)——真实源码在 `Alpha`/`Meta` 等分支，`main` 只有 release/CI 元数据、连 `hub/route/` 都没有）。[全表路由注册](https://github.com/MetaCubeX/mihomo/blob/24b6de71fc1c4ea282dcbc7b65a8bcbcc0c75e6c/hub/route/server.go#L105)共 18 个（`/ /logs /traffic /memory /version /configs /proxies /group /rules /connections /providers/* /cache /dns /storage /restart /upgrade /ui` + doh），其中 `C.Path.Config()` 只出现一次——在 [`updateConfigs`（`PUT /configs`）](https://github.com/MetaCubeX/mihomo/blob/24b6de71fc1c4ea282dcbc7b65a8bcbcc0c75e6c/hub/route/configs.go#L415)里当热重载的**默认输入**（请求没带 `path` 时兜底），从不写进任何响应。`GET /configs` 返回的是 [`executor.GetGeneral()`](https://github.com/MetaCubeX/mihomo/blob/24b6de71fc1c4ea282dcbc7b65a8bcbcc0c75e6c/hub/executor/executor.go#L129)：纯运行态设置（端口/tun/mode/log/geo/keepalive…），无路径字段。内核**自己知道**路径（[`constant/path.go` 的 `Path.Config()`](https://github.com/MetaCubeX/mihomo/blob/24b6de71fc1c4ea282dcbc7b65a8bcbcc0c75e6c/constant/path.go#L75)），只是不经 API 暴露。**要定位 active 配置只能看进程 `-d`/`-f` 启动参数**（Windows 上 mihomo 可能高权限跑、需 UAC 提权才读得到命令行），或按 [§2.2](#22-配置目录是运行时算出来的不是安装决定的) 规则 + `/configs` 与 `/proxies` 运行态内容比对推断。

**改运行态**——三种改法：`PUT /configs`（换整份配置）、`PATCH /configs`（改单项运行态）、`PUT /proxies/<组>`（切节点）。

**① 整份热重载 `PUT /configs`**（配置在安全路径内时用 `path`）：

```powershell
$body = @{ path = "$env:USERPROFILE\.config\mihomo\config.yaml" } | ConvertTo-Json -Compress
Invoke-WebRequest -Uri 'http://127.0.0.1:9090/configs?force=true' -Method Put -ContentType 'application/json' -Body $body
```

配置不在安全路径内会报 `path is not subpath of home directory or SAFE_PATHS`——临时可用 `payload` 提交完整 YAML，但日常应直接维护默认位置的 `config.yaml`。

**② 增量改单项 `PATCH /configs`**：只改你 body 里带的字段、其余保留（base = 当前运行态）。`mode` / 端口 / `log-level` / `ipv6` 这类改一行就行；`tun` 也能这么改，但它**特殊**（改 tun 要重建网卡、有额外坑，见下）：

```bash
# 只切模式，其它不动
curl -H "Authorization: Bearer <secret>" -X PATCH http://127.0.0.1:9090/configs -d '{"mode":"global"}'
# 改 TUN：base=当前 tun，只覆盖你传的字段（auto-route/dns-hijack/inet4/route-exclude 等都保留）
curl -H "Authorization: Bearer <secret>" -X PATCH http://127.0.0.1:9090/configs -d '{"tun":{"enable":true,"strict-route":false}}'
```

> **源码**：`hub/route/configs.go` 的 `patchConfigs`——各段 base 取当前运行态（如 tun 的 base=`listener.LastTunConf`），只覆盖请求里出现的字段。

**改 `tun` 段的四个额外坑**（改 `mode`/端口那些一般没这些）：

1. `tun.enable` 是**非指针 bool**——一旦发 `tun` 对象就**必须带 `"enable":true`**，漏了会被当 `false`、直接把 TUN 关掉。
2. **`enable` OFF→ON = 新建 TUN/Wintun 设备，要 mihomo 进程本身有管理员 / root 权限**。注意提权的是**核心进程**、**不是**调 9090 的 curl（调用方只要 `secret`、不要 admin）。所以：**只要那个带 TUN 的 mihomo 本来是提权跑的（正常都是），就能用 9090 把 TUN 关了再开**；若核心没提权，`enable:true` 会**静默失败**、`GET /configs` 读回 `enable=false`。这也是"驱动已提权的核心原地重建 TUN"能行、而"kill 核心再从普通上下文裸起"不行（新进程拿不到 TUN 提权、还撞下面的竞态，本机实测 4/4 次 TUN 起不来）的根因。
3. **（Windows）改任何 `tun` 参数都触发 `ReCreateTun` = close + 立刻重建 → 撞 Wintun 竞态 → TUN 静默掉**（见 [§6.2](#62-tun-模式下别用-post-restartwindows-会静默丢-tun)）。所以切 tun 参数要**两段式**：先 `{"tun":{"enable":false}}` 关掉 → 等 ~12s 让 Meta 适配器 PnP 删净 → 再 `{"tun":{"enable":true, ...目标...}}` 建新的（此时不再撞）。
4. **读回坑**：`strict-route:false`（及其它零值 bool）因 `json:",omitempty"`，`GET /configs` 会**省略该字段**——读到 `None`/缺失 ≠ 没生效。

**③ 改节点 / 测延迟 `PUT /proxies/<组>`**（group 名常含 emoji/中文，URL path 必须 `EscapeDataString`）：

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

### 6.1 Web 面板（external-ui / `/ui` 路径）

控制面除了裸 REST API，还能让 mihomo **自己托管一个 Web Dashboard**，不用另起 web 服务——配 `external-ui` 即可，浏览器开 `http://<controller>/ui/`：

```yaml
external-controller: 0.0.0.0:9090   # 要被别的机器 / mesh 访问就绑 0.0.0.0；仅本机用 127.0.0.1
secret: '<random-secret>'           # 控制面出回环必须设 token（同 §3.1 的逻辑，控制面也一样）
external-ui: ui                     # dashboard 静态文件目录：绝对路径，或相对 mihomo home(~/.config/mihomo/ui)
external-ui-url: "https://github.com/MetaCubeX/metacubexd/archive/refs/heads/gh-pages.zip"  # 目录为空时自动拉这个 zip
```

- **服务路径**：mihomo 把 `external-ui` 目录挂在控制面的 `/ui` 下（源码 `hub/route/server.go`：`/ui` → `FileServer(external-ui 目录)`，裸 `/ui` 自动 302 到 `/ui/`）。所以 `http://127.0.0.1:9090/ui/` 就是面板，和 REST API 同端口。
- **自动下载**：启动时若 `external-ui` 目录为空，mihomo 按 `external-ui-url` 下载并解压 dashboard（源码 `hub/executor/executor.go` 的 `AutoDownloadUI()`）；想手动更新打 `POST /upgrade/ui`（`hub/route/upgrade.go`）。上面这个 URL 是 **MetaCubeXD**（常见 mihomo 面板，另有 yacd / zashboard 等，换 URL 即可）。
- **暴露到网络要 secret**：`external-controller` 绑 `0.0.0.0`（让 mesh / LAN 上别的机器也能开面板）时**必须设 `secret`**——它是 REST API 的 Bearer token，面板首屏要填"后端地址 + 这个 secret"才连得上；绑回环自用可留空。**真实 secret 不入库，占位即可。**
- **面板默认连哪个后端**：dashboard 是纯静态 SPA，得知道连哪个控制面 API。MetaCubeXD 默认让你首屏手填后端 URL + secret；在 `external-ui` 目录里放一个 `config.js` 把它钉成同源就免手填：

  ```js
  // <external-ui>/config.js
  window.__METACUBEXD_CONFIG__ = { defaultBackendURL: window.location.origin }
  ```

  这样从 `http://<host>:9090/ui/` 打开就自动连同源的 `http://<host>:9090` 控制面，不必每次手填 backend（secret 仍需在面板里填一次）。

### 6.2 TUN 模式下别用 `POST /restart`（Windows 会静默丢 TUN）

REST API 有个 `POST /restart`：让 mihomo **重启自己、用原启动参数重载配置**。但在 **Windows + TUN** 下它有硬伤——调用返回 `{"status":"ok"}`，核心却死了、不再起来（`:9090` 监听直接消失），得手动拉起。**改 `external-controller` / `secret` / `external-ui` 这类只有重启才生效的项时最容易踩**（想省一次手动重启 → 用 `/restart` → 反而把核心整没了）。

**先排除一个错误归因：不是权限问题。** Windows 上重启是 `exec.Command(exe, args).Start()` + `os.Exit(0)`（spawn 新子进程、父进程退出），子进程经 `CreateProcess` **继承父进程的管理员 token**（代码没设 `SysProcAttr` 去降权），UAC 不参与。对比 Unix 走 `syscall.Exec`（execve，原地替换、同 PID）——两条路本质不同，但**都不掉权**。

**真因是 Wintun 适配器的 PnP 删除竞态：**

1. 重启前 `executor.Shutdown()` → 关 TUN → `WintunCloseAdapter()` **请求删除**网卡设备。Windows 的 PnP 设备删除是**异步**的：函数立刻返回，内核还没删完。
2. 新子进程紧接着 `tun.New()` → `WintunCreateAdapter()` 撞 `ERROR_ALREADY_EXISTS`（"Cannot create a file when that file already exists"），fallback `OpenAdapter()` 也失败（设备在删除中间态）。
3. 这个失败 **<1 秒**返回，正好命中 `tunNew()`（`listener/sing_tun/server_windows.go`）的**快失败早退分支——不重试**（只有 ≥1s 的超时才重试 3 次）。
4. 于是 TUN 静默禁用（`ReCreateTun` 的 defer 把 `tunConf.Enable=false`，**不 crash**），核心沦为没有 TUN 的裸代理：网卡消失、透明路由停摆，用户看着就是"核心死了"。

> 叠加坑：`Shutdown()` **只关 TUN、不关控制器端口**（`:9090` 要等老进程 `os.Exit` 才释放）。而子进程是在老进程退出**前**就 spawn 的——若你同时又改了控制器绑定（`127.0.0.1` → `0.0.0.0`），子进程去 bind 时老进程还占着端口 → 撞端口 → `:9090` 彻底起不来。这解释了为什么"改 controller + `/restart`"会让控制器整个消失，而不只是 TUN 没了。

**源码锚点**（`MetaCubeX/mihomo`，真实源码在 `Alpha`/`Meta` 分支）：`hub/route/restart.go` 的 `restartExecutable`（`runtime.GOOS==="windows"` 分支 spawn+`os.Exit`，else 走 `syscall.Exec`）；`MetaCubeX/sing-tun` 的 `tun_windows.go` `NativeTun.Close → adapter.Close → WintunCloseAdapter`；`server_windows.go` `tunNew` 的 `<1*time.Second` 不重试。相关 [PR #709](https://github.com/MetaCubeX/mihomo/pull/709)（"call shutdown() before restart"）是修 **Linux iptables 重复规则**、与 Windows TUN 无关；issue 区**没有**记录这个 Windows+TUN 失败模式。

**教训 / 做法**：TUN 模式**别用 `/restart`**，改成**外部 kill → 等一下（让 Wintun 适配器删干净、端口释放）→ 按原启动参数重新拉起**（或重启对应服务）。要在 Windows 上脚本化这套 kill+relaunch、且 mihomo 高权限跑需要 UAC 提权时，`Start-Process -Verb RunAs` + 落盘取结果的手法见 `software` skill 的 Windows/WSL 提权章节。

### 6.3 某些域名打不开、别的正常：多半是某个节点死了

**现象**：`curl google.com` 通、但 `curl 某域名` 不通（502 / 连接超时 / SSH `banner exchange timeout`）；同一个代理、同一台机器，就这批域名坏。**别急着判远端服务器故障**——最常见的真因是：这批域名被某条规则单独导进一个 Selector 组，而该组当前**钉死**在一个已挂的节点上（节点被墙 / 落地 IP 被封 / 上游死了）。google 走的是另一个自动挑活节点的组，所以没事。

**为什么会"我没动过却突然坏"**：规则和节点选择一直没变（选择器的当前选择记在 mihomo 的 `cache.db`，重启也扛）。变的是**那个节点的落地 IP 被墙了**——服务器和你都没动，是这条出口的路被掐了。

**诊断链**（全程用 REST API + DoH，几条命令定位；`<域>` 换成打不开的域名）：

```bash
# 1) 该域名命中哪条规则、导进哪个组
curl -s -H "Authorization: Bearer <secret>" http://127.0.0.1:9090/rules \
  | python3 -c "import sys,json;[print(r) for r in json.load(sys.stdin)['rules'] if '<域根>' in json.dumps(r)]"
# 2) 那个组当前选中(now)哪个节点、候选(all)有哪些
curl -s -H "Authorization: Bearer <secret>" "http://127.0.0.1:9090/proxies/<组名URL编码>" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('now=',d['now'],'| all=',d['all'],'| last=',d.get('history',[])[-1:])"
# 3) 实测这个节点还活不活（/delay 对真实目标；delay=0 或 Timeout = 死）
curl -s -H "Authorization: Bearer <secret>" \
  "http://127.0.0.1:9090/proxies/<节点URL编码>/delay?url=http%3A%2F%2Fwww.gstatic.com%2Fgenerate_204&timeout=5000"
# 4) DoH 拿域名真实公网 IP（绕过 fake-ip），验证服务器本身还在
curl -s --proxy socks5h://<gw>:7890 "https://1.1.1.1/dns-query?name=<域>&type=A" -H "accept: application/dns-json"
# 5) 用健康节点直连「真实 IP:端口」抓 banner，确认是"节点死"不是"服务器死"
#    （连 IP 绕过域名规则，走默认健康组）
sleep 9 | nc -x <gw>:7890 -X 5 <真实IP> 22    # 期望立刻回 SSH-2.0-...；回得来=服务器活、是节点的锅
```

**判决**：若组 `now` 那个节点 `/delay` 超时/为 0、而候选里别的节点 delay 正常、且真实 IP 直连能拿到 banner → **服务器没事，是选择器钉的节点死了**。修复：把该 Selector 切到活节点（`PUT /proxies/<组>` body `{"name":"<活节点>"}`，见 §6 的改节点示例；只影响新连接、可随时切回）。**注意别切 DIRECT**——若该域名的落地 IP 已被墙，直连反而不通。

**要点提炼**：① "入口通 ≠ 出口节点活"（`HTTPS_PROXY` 只决定进 mihomo，出口由 rule+group 链决定，见 §3.2）；② fake-ip 下裸连报 502/超时先查 TUN/节点、别怪远端；③ 选择器当前选择在 `cache.db`、config 改默认项不一定生效（要在面板/API 里切）。

> 上面是「某批域名突然打不开、别的正常」这个高频场景的速查；连不上时更一般的「从近到远逐层排查」（含 CONNECT `200` 不等于连通、`--resolve` 直接测入口、多地外部探针）见 §6.4。

### 6.4 节点连不上时逐层排查（CONNECT 200 不等于连通）

> 这是「连不上」的通用逐层排查方法。一个高频具体场景——某批域名突然打不开、别的正常、多半是选择器钉死了已挂节点——的速查见 §6.3。

遇到下面这种输出，**不能**据第一行判断节点或目标网站已经连通：

```text
HTTP/1.1 200 Connection established

curl: (35) ... SSL routines::unexpected eof while reading
```

显式 HTTP 代理下，`curl` 先向本地 mixed-port 发送 `CONNECT <target>:443`。Mihomo v1.19.27 的 [`listener/http/proxy.go`](https://github.com/MetaCubeX/mihomo/blob/5184081ac327394d9e15fa5d5f9f4a61e723fd94/listener/http/proxy.go#L68-L75) 会先向客户端写 `200 Connection established`，然后才调用 `tunnel.HandleTCPConn(...)`；后者完成规则/节点解析后，才在 [`tunnel/tunnel.go`](https://github.com/MetaCubeX/mihomo/blob/5184081ac327394d9e15fa5d5f9f4a61e723fd94/tunnel/tunnel.go#L552-L576) 调用真正的 `proxy.DialContext(...)`。

**因此，即使最终出站节点是全球完全不可达（服务停机、防火墙全丢、TCP 一直超时），客户端仍会先收到这个 `200`**；节点是“部分源网络不通”还是“所有网络都不通”，对这个已经写出的状态码没有区别。前提只是客户端连得上本地 Mihomo、代理认证/CONNECT 解析通过，而且 Mihomo 能把响应写回客户端。出站立即失败时，后续常见 EOF/reset；拨号等到超时时，后续也可能直接表现为 `curl` timeout。这个 `200` 只能表示**本地代理接受了隧道请求**，不能作为任何节点健康证据；`curl -I` 的 HEAD 请求此时也尚未抵达目标站。

这个结论特指 **HTTP 代理的 CONNECT 路径**：本地 mixed-port 自身不可达、代理认证失败或 CONNECT 请求未通过时不会得到这个 `200`；普通明文 HTTP 代理请求（非 CONNECT）可在出站失败后返回 `502`，SOCKS 入口则根本没有 HTTP 状态行。

按数据面从近到远分层，不要一上来把所有超时都归为“节点 down”或“被墙”：

1. **确认实际规则链与旧连接**：查 `/proxies` 的逐层 `.now`，再查 `/connections` 的 `host`、`start`、`chains`、`rule`。selector 的 PUT 只改变后续新连接，不会把已有 TCP/WebSocket 迁移到新节点。
2. **不切主选择器，直接测具体节点**：调用 `/proxies/<urlencoded-node>/delay?url=<urlencoded-real-target>&timeout=10000`，分别用普通连通性目标和实际业务目标。两个都失败才继续向落地入口排查；单一目标失败可能只是目标站风控或分流差异。
3. **拿落地真实 IP，绕开本机代理测入口**：DNS 必须走 DoH（见 §12.1），避免 fake-ip；随后清除 proxy env、加 `--noproxy '*'`，并用 `--resolve` 同时钉真实 IP、保留正确 Host/SNI：

   ```bash
   env -u http_proxy -u https_proxy -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
     curl --noproxy '*' -v --connect-timeout 5 \
     --resolve '<node-domain>:443:<real-ip>' 'https://<node-domain>/<ws-path>'
   ```

   能完成 TCP/TLS 并收到普通 HTTP `403`，通常只证明 443/TLS/反代前端在线（普通 GET 没带 WebSocket Upgrade 时被拒很正常），**不等于完整 VLESS/WS 鉴权已经验证**。若这里连 TCP 都超时，故障发生在 TLS、WebSocket path 和代理协议之前。
4. **同 IP 多端口 + 路由对照**：对 22/80/443 等已知监听做短超时 TCP 测试；再用一个已知正常节点作控制组。需要看路径时用 `mtr -T -P 443 <real-ip>`。MTR 没回 hop 不自动等于“本地第一跳丢弃”——中间设备也可能不回 TTL exceeded；要结合控制目标和外部探针判断。
5. **用真正独立的外部视角**：Check-Host 等多地探针可测 `IP:443` TCP，再测节点域名 HTTPS。若当前网络全超时、境外/邻近地区多点 TCP 与 TLS 都成功，说明 VPS/入口并非全局 down，而是**源网络相关**的出程、回程、ACL、抗 DDoS 或 peering 问题。反过来，多地也全失败才优先查 VPS 电源、服务和防火墙。

Check-Host API 的最小用法（首个请求返回 `request_id`，稍后轮询结果）：

```bash
curl -sS -H 'Accept: application/json' \
  'https://check-host.net/check-tcp?host=<real-ip>%3A443&max_nodes=10'
curl -sS -H 'Accept: application/json' \
  'https://check-host.net/check-result/<request_id>'
```

远端机器也可能跑 Mihomo TUN，**不要看到“远端 curl 成功”就当独立旁路**：若 `remote_ip` 或路由落在 `198.18.0.0/16`，那是 fake-ip/TUN；即使用 `--resolve` 钉了真实 IP，TUN 仍可能接管。先在远端看 `ip route get <real-ip>`，确认没有走 Meta/TUN/本机代理，才算独立视角。

快速判读：

| 现象 | 优先结论 |
|---|---|
| 当前网络和多地探针都无法 TCP 连接 | VPS、监听、机房防火墙或全局路由故障 |
| 当前网络所有端口超时，多地 TCP/TLS 正常 | 源网络相关的出程/回程黑洞、ACL、DDoS 策略或 peering；不是 WS path 本身 |
| TCP/TLS 正常，只有正确 WebSocket/VLESS 失败 | 再查 SNI、证书、Host、path、Upgrade、反代与 UUID |
| 切节点后旧应用仍工作，新 `curl` 失败 | 旧长连接还钉在切换前的节点；不代表新节点可用 |

最后一行在 Codex/流式 API 上尤其常见。OpenAI 的 [Responses WebSocket mode](https://developers.openai.com/api/docs/guides/websocket-mode) 会复用持久连接；Mihomo selector 改的是**未来连接的选择结果**，不会在线迁移这条 socket。验证时用一个新进程/新连接，并在 `/connections` 里核对它的 `start` 与 `chains`。删除单条或全部 `/connections` 会打断用户业务，只在明确获准时做；诊断阶段优先重启目标应用或另开短连接。

## 7. TUN 路由的边界

几条容易踩、值得先知道的事实：

- **`IP-CIDR,...,DIRECT` 不等于绕过 TUN**：它只是“流量进了 TUN 后，mihomo 选 `DIRECT` 这个 outbound”；`/connections` 里仍会看到 `inboundName: DEFAULT-TUN`、`chains:[DIRECT,...]`。真要某个目的地完全不进 TUN，是另一回事。
  > **源码**：TUN 入站固定打标 `listener/sing_tun/server.go` 的 `inbound.WithInName("DEFAULT-TUN")`；而 `rules/common/ipcidr.go` 的 `IPCIDR.Match()` 只返回出站 adapter 名，决定 outbound、不碰 inbound 拦截。
- **规则顺序决定命中**：宽泛的 `RULE-SET,cn-ip`/`private-ip` 放在显式 `IP-CIDR` 前会先命中特例地址。需要特例策略就把特例规则提前——但提前命中 `DIRECT` 仍不是 TUN bypass。
  > **源码**：`tunnel/tunnel.go` 的 `match()` 从上往下首条命中即 `return`。
- **`route-exclude-address` 不是稳定通用方案**：它只让 mihomo 不接管这些目的地址，**不保证** Windows 自动补出可用的物理网卡路由；排除异地组网依赖的公网 IP 后，可能把组网本身断开。需要对照时 `route print <peer-ip>` 看实际路由。
  > **源码**：`listener/sing_tun/server.go` 的 `RouteExcludeAddress`/`Inet4RouteExcludeAddress` 传给 tun 栈，作用是把这些地址从 TUN 的 auto-route 里排除；OS 有没有可用物理路由是系统路由表的事，mihomo 不补。
- **`route-exclude-address`（TUN 层）与 `IP-CIDR,...,DIRECT`（规则层）是两道机制、作用在不同路径，可并用也可能覆盖不齐**：前者管“被路由进 TUN 的裸包”（宿主自身、或经 NAT 转发进来的路由流量——直接不接管、不进引擎）；后者管“已进 mihomo 引擎的流量”（TUN 抓进来的、或下游以 socks/http 递进来的请求——判 `DIRECT`）。所以**对把流量当 socks 请求交给 mixed-port 的下游客户端（如 WSL tun2socks→7890），`route-exclude-address` 完全不生效**（那是路由层的事，socks 请求早已绕过路由），只有 `DIRECT` 规则兜得住；反之宿主自身到组网的裸路由流量靠 route-exclude 不进 TUN。
  > **两层覆盖常不一致的例子**：`route-exclude-address:[10.144.0.0/16]` 只覆盖 `10.144.x`，而规则 `IP-CIDR,10.144.18.0/24,DIRECT`+`IP-CIDR,10.100.158.0/24,DIRECT` 还覆盖 `10.100.158.x`——于是 `10.100.158.x` 缺 route-exclude 那层、会被 TUN 抓进引擎再由规则放直连，`10.144.x` 则两层都在。
- **`auto-route` 决定「被路由/转发的流量进不进 TUN」、Windows 的 `strict-route` 不决定**：`auto-route` 在宿主装 `0.0.0.0/1`+`128.0.0.0/1`（metric 0）指向 TUN 的路由 + 开 tun 网卡 `ForwardingEnabled`——**凡被宿主路由表处理的包**（宿主自身的、以及经 NAT 转发进来的下游流量，例如 WSL NAT VM 的裸出站）都落进 TUN → 引擎，连自建域名解析成的 fake-ip 也闭环通。Windows 的 `strict-route` **只加 WFP 防火墙过滤器**（挡 IPv6 + 挡明文 DNS `:53` 泄漏），不动任何路由、也不拦通用 IPv4——是**防泄漏**、不是抓取开关。所以「宿主开 TUN 后下游/转发流量被不被接管」由 `auto-route` 决定、与 `strict-route` 无关。
  > **源码 + 实测坐实（2026-07，mihomo v1.19.24 / sing-tun v0.4.17）**：`tun_windows.go` 的 `AutoRoute` 分支装那套路由 + `ForwardingEnabled=true`；`StrictRoute` 分支只 `FwpmFilterAdd0` 加 WFP、**IPv4 block 段是注释掉的 `/* */`**、不碰路由（Linux 的 strict-route 也只在某地址族没配 TUN 地址时补 `unreachable` 兜底，正常非抓取机制）。A/B：固定 `auto-route:true`、把 `strict-route` 切 `false→true→false` 三态（改它会被 `listener/config/tun.go` 的 `Equal()` diff 到 → 触发 `ReCreateTun`；Windows 上 close+立刻重建撞 Wintun 竞态、见 [§6.2](#62-tun-模式下别用-post-restartwindows-会静默丢-tun)，切它要 `enable:false`→等 Meta 删净→`enable:true` 两段式），每态让一个 NAT 下游（WSL）剥 proxy 后 raw-IP 裸连——**三态出口 IP 恒 = 代理节点、外网恒通** ⇒ strict-route 不改变接管。踩坑：`strict-route` 是 `json:",omitempty"`，`false` 时 `GET /configs` **省略该字段**（读到 `None` 不代表没生效）。
  > **⚠ Windows 实测坑：接管是真的、但不持久。** 先记**肯定**的一面：tun2socks 停着、WSL 无任何代理配置时，WSL NAT 裸连**确实成功**被宿主 TUN 接管、从宿主代理节点出口过（出口 IP == 代理节点、非本地 ISP；A/B 3 轮 + 重建后 11 连采 + durability 新鲜态多次复现，**绝不是"从不接管"**）。问题只在**持久性**：这层对「转发进来的下游流量」（WSL NAT VM 这类）的接管**会随时间退化（实测分钟级）**——路由一直在（`Find-NetRoute <目标>` 仍指 TUN）、宿主自身上网也一直正常，但「把转发包收进 Wintun 设备」那条数据路径会失效、下游裸包进了 TUN 却被**黑洞丢弃**（超时、**不是**漏直连）。**两段式重建 TUN（`enable:false`→等 Meta 删净→`enable:true`）~4s 内即恢复**（实测：陈旧 TUN 连测 60s 全超时、换多个目标也全超时；重建后 4s 即接管并稳定）。诊断：停掉下游自己的代理后、下游 raw-IP 裸连超时，但 `Find-NetRoute` 仍指 TUN、宿主自身在线 ⇒ 就是这个退化。所以要让 WSL / 下游**稳定**走宿主，别裸靠宿主 TUN 接管——用 tun2socks 之类**显式代理**（[wsl.md 方案 B](wsl.md#wsl-nat-下出站走-mihomo)：走 mixed-port、不碰这条会退化的转发路径）。**别误读成"不用 tun2socks 也许还能接管"**："放着不重建的宿主 TUN 会退化到不接管转发流量"是**确认的**（陈旧态连测 60s 全超时）；未坐实的只是退化的**触发原因**（时间 / 空闲 / 被旁路"变冷"），**不是"会不会退化"**。而两条"翻盘"路已被实测封死：① `strict-route:false` 也照样退化（新鲜接管约 3min 后就掉、t=4~7min 连续超时）⇒ 退化**与 strict-route 无关**；② 每 90s 定期使用"保持热"也拦不住。所以"不装 tun2socks 还能稳定接管"**不成立**——auto-route 对 WSL-NAT 的接管是**分钟级就掉的**、本质不可靠，tun2socks 必留。（注：早前以为"小时级"是误判——那只是 TUN 已开了很久，不是接管撑了很久；实测新鲜接管 3min 就退。退化的正向触发机制仍未坐实，但 strict-route 与"保持热"两个候选已排除。）

排障先分清“远端节点不通”还是“本机 TUN/入口没接管”：

```powershell
curl.exe -v -I --max-time 12 <test-url>                               # 裸连(走 TUN/系统路由)
curl.exe -v -I --max-time 12 --proxy http://127.0.0.1:7890 <test-url> # 显式走 mixed-port
```

显式 `--proxy` 稳定成功、而裸 `curl` 失败或命中 fake-ip 后报连接错误 → 优先查 TUN/系统路由/DNS 劫持/权限环境，别一上来就怪远端节点。

### 7.1 WSL ssh 借道宿主 mihomo（没开 TUN 时才需要）

**宿主 mihomo 开了 TUN（且 `auto-route: true`）时，WSL 里直连即被透明接管**——`auto-route` 把整机路由（含经 NAT 转发出去的 WSL 出站）都劫进 mihomo，连解析成 fake-ip 的自建域名也直接通，WSL 内 ssh / curl 无需任何代理配置（**为什么是 `auto-route` 决定接管、`strict-route` 只防泄漏不影响，见上 [§7](#7-tun-路由的边界)**）。**⚠ 但 NAT 模式下这层接管不持久、会随时间退化**（宿主 TUN 挂久了 WSL 转发流量被黑洞丢弃、要重建宿主 TUN 才恢复，见 [§7](#7-tun-路由的边界)）；要 WSL 稳定走宿主，建议用 tun2socks（wsl.md 方案 B）。只有“没开 TUN、或 `auto-route` 关、或目标没被 TUN/规则覆盖、直连出不去”时，才需要让 WSL 流量**显式借道**宿主 mihomo：HTTP 类工具设 `HTTPS_PROXY`，ssh 走 SOCKS 配 `ProxyCommand`，且 NAT 下宿主在 WSL 网段的网关 IP 每次启动可能变、得动态取。具体 `ProxyCommand` / 动态网关 / 代理环境变量配方（方案 A），以及 WSL 内自建 TUN 透明代理 tun2socks（方案 B），见 [wsl.md](wsl.md#wsl-nat-下出站走-mihomo)「WSL NAT 下出站走 Mihomo」；Mirror 模式下 WSL 与宿主共享 `127.0.0.1`，可直接 `127.0.0.1:7890`、不必取网关。

## 8. 从源码构建（Windows）

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

## 9. 泄漏控制总览：泄漏是什么 + DNS / WebRTC 要不要开 TUN

**先说“泄漏”是什么。** 你挂上代理，以为流量都从节点出、真实身份藏好了；但有些信息会从**代理没兜住的旁路**漏回去，暴露你真实所在。最常见两类：**DNS 泄漏**（谁在替你查域名、你查了哪些站，落到本地 ISP / 运营商手里）和 **WebRTC 泄漏**（浏览器把你**真实公网 IP** 直接吐出来）。泄漏控制就是把这两条旁路也堵上。

**最常被一起问的：“是不是都得开 TUN 才不漏？”** 两类答案不一样，根源是**这两类流量和代理的关系根本不同**：

- **DNS：域名解析本来就是“建立连接”的一部分，代理协议自带。** 只要 app 把解析交给代理——HTTP CONNECT / SOCKS5h 把**域名**（而非 IP）发给代理、在**远端**解析——乖乖走代理的 app（如浏览器）**没 TUN 也不漏**（[§12.1](#121-dns-泄漏怎么测browserleaks--bashws--排障) 那次 mixed-port 实测就是零 ISP 解析器）。`dns-hijack`（TUN 的功能）只是为了兜住**另一类**：不走代理、自己硬解 DNS 的程序（硬编码 `8.8.8.8` 之类）。
- **WebRTC：正相反，它为 STUN 探测另起一条独立 UDP。** 这条 UDP 与代理那条连接无关，HTTP / SOCKS 代理**搬不动**它，所以**必须**靠 TUN（网络层连 UDP 一起接管）或浏览器策略来堵。

一句话——**域名解析是建连的一部分、代理协议自带；WebRTC 的 UDP 是另起炉灶、代理管不着。** 所以 DNS 泄漏能靠“让 app 走代理”解决，WebRTC 泄漏则非 TUN / 浏览器策略不可。

> 下面 [§10](#10-dns-泄漏原理与-mihomo-配置)（DNS）、[§11](#11-webrtc-泄漏原理与-mihomo-配置)（WebRTC）各自只讲**原理 + mihomo 配置**；两类泄漏**怎么探测验证**统一放 [§12](#12-探测与验证-dns--webrtc-泄漏)。

## 10. DNS 泄漏：原理与 mihomo 配置

这一节是理解代理“干不干净”的关键，配置和原理必须一起讲。

### 10.1 原理：三方模型 · 两个正交开关 · 行为对照表

#### 三方模型：DNS 泄漏泄给了谁

解析一个域名牵涉**三方**，不是两方：

1. **你**（客户端）。
2. **递归解析器（recursive resolver）**：你系统里配的那个“查号台”，家用网络下通常是**运营商（ISP，Internet Service Provider，互联网服务提供商）**的。它知道**你查过哪些域名**——一份完整的访问清单，哪怕你后续连的是 HTTPS、内容它看不到，“你去了哪些站”它有。
3. **权威服务器（authoritative server）**：被查域名主人自己开的“总台”，最终答案从这儿出。它能看到**是哪个递归解析器来问的**（来问者的出口 IP）。

所以 **DNS 泄漏 = 你的查询跑去了一个你不想让它知道的解析器（通常是 ISP 的）**，于是运营商攒下了你的域名清单，还能据此**按域名封锁 / 投毒**（故意回错 IP，就是 GFW 的 DNS 污染）。代理的目标因此不只是“内容走代理”，还要“DNS 也别落到 ISP 解析器手里”。

#### 两个正交的开关：dns-hijack 与 enhanced-mode

防不防泄漏、返回真 IP 还是假 IP，是**两个独立的开关**：

**开关 A：`dns-hijack`（TUN 的功能）——决定“查询进不进 mihomo”**

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

**开关 B：`enhanced-mode`（DNS 的功能）——决定“进来后 mihomo 回什么”，三选一**

源码 `dns/enhancer.go` 里 mode 只有三种：`DNSNormal` / `DNSMapping`(=redir-host) / `DNSFakeIP`。对应 `dns/middleware.go` 三个中间件：

- **`fake-ip`**（`withFakeIP`）：
  ```go
  if skipper.ShouldSkipped(host) { return next(ctx, r) } // fake-ip-filter 命中才放行去真解析
  ip := fakePool.Lookup(host)   // 直接给一个池子里的 198.18.x，不 call next（当场不做真解析）
  ```
  应用瞬间拿到假 IP，**真解析推迟到连接时、在远端做**。最快、分流最准、最防污染。代价：少数按 IP 工作的程序会坏（见 [10.2](#102-mihomo-配置防泄漏--分流准--防污染) 的 `fake-ip-filter`）。
- **`redir-host`**（`withMapping`）：
  ```go
  msg, err := next(ctx, r)             // 先做真解析，拿真 IP
  mapping.SetWithExpire(ip, host, ...) // 再记下 ip→域名 映射
  ```
  回**真 IP**，但记住“这个 IP 是哪个域名的”，连接时还能按域名分流。代价：每次要等真实解析、上游被污染会拿到污染结果。
- **`normal`**：啥都不加，回真 IP、也不记映射。**分流退化**为只能按 IP（域名信息丢了，按域名的规则可能判错）。

#### 行为对照表

| dns-hijack | enhanced-mode | 普通查询(`getent`)拿到 | 分流准度 | DNS 泄漏风险 |
|---|---|---|---|---|
| **关** | 任意 | 真 IP（走系统 resolv.conf 的 DNS） | 看 app | **高** ← 泄漏就这儿来 |
| 开 | fake-ip | `198.18.x` 假 IP | 最准（按域名） | 低 |
| 开 | redir-host | 真 IP | 准（靠 ip→域名 映射） | 低 |
| 开 | normal | 真 IP | 退化（只有 IP） | 低（但分流变差） |

一句话：**泄漏由 A（hijack）决定**（查询进不进 mihomo），**真假 IP 与分流准度由 B（enhanced-mode）决定**——两者无关。把“返回 198.18.x”算在 hijack 头上是常见误解：返回假 IP 是 fake-ip 干的，hijack 只负责“把你抓进来”。

**补充维度：enhanced-mode 还决定“真解析在哪发生”，间接影响解析元数据落谁手里。** 实测坐实（同一 `curl` 触发、唯一变量 enhanced-mode，DNS-leak 权威台看到的解析器出口一个在境内、一个在境外）：

- **`redir-host`**：DNS 查询时**本机**用 `nameserver-policy` 立即解析。**未命中 geosite 分类的冷门域名**会 fallback 到默认 `nameserver`——若默认配的是国内 DoH，这类域名的解析就落到**国内 DoH 商**手里。
- **`fake-ip`**：真解析**推迟到连接时、走代理链路**，冷门境外域名的解析在**境外**完成。
- 两者都**不暴露本地 ISP 明文解析器**（dns-hijack + DoH 该拦的都拦了）；差别只在“未分类冷门域名的解析交给境内还是境外 DoH”。想让 `redir-host` 也走境外，把域名纳入 `geosite:geolocation-!cn` 或调 `nameserver-policy`。

### <a id="linux-dns"></a>10.2 mihomo 配置：防泄漏 + 分流准 + 防污染

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

> **Linux 宿主的 `systemd-resolved` 边界（实测）**：应用默认查询 `127.0.0.53`，resolved 再自行访问上游；loopback stub 这段不一定进入 Mihomo TUN，因此只写 `dns-hijack: any:53` 仍可能得到污染记录。需要让 Mihomo 显式监听本机 DNS 端口，再把 resolved 的全局上游指向该 listener。配置形态与验证方法见 [共享 Linux 节点的 DNS 接入](setup.md#dns)。

> **注·与 WSL 的边界**：这个 `198.18.0.1/16` 是宿主自己的 fake-ip 段（TUN 默认网关 IP 也取自此值）。**WSL 内自建 TUN（tun2socks）要避开 `198.18.x`**，否则和宿主 fake-ip / TUN 网关撞——见 [wsl.md](wsl.md#方案-bwsl-内自建-tun-透明代理tun2socks)「方案 B：WSL 内自建 TUN 透明代理」。

> **注·对 agent 工具的副作用**：fake-ip 会让某些**自己解析 DNS + 做 SSRF 判黑**的 agent 工具误伤——典型是 GitHub Copilot CLI 的 `web_fetch`：它抓任何域名都先解析成 `198.18.x`，而这段属 RFC 保留段、被判为"blocked address"直接拒（换 `redir-host` 就没事）。绕过要改源码（定点放行 `198.18.0.0/15`），机制与补丁思路见 `harness` skill 的 `web_fetch` SSRF 章节。

## 11. WebRTC 泄漏：原理与 mihomo 配置

WebRTC 泄漏和 DNS 泄漏**是两回事**，很多人混在一起。

### 11.1 原理：浏览器自己把公网 IP 暴露出来

网页里的 `RTCPeerConnection`（WebRTC 用于音视频/P2P）建连前要“收集 ICE 候选地址”，其中一步是**向 STUN 服务器发 UDP 探测**问“我的公网 IP 是多少”。STUN 服务器照实回它看到的来源 IP——**如果这个 UDP 没走代理，它看到的就是你真实出口 IP**。然后网页用 JS（`onicecandidate`）读到这些候选，直接显示出来。

所以和 DNS 泄漏的检测方式正好相反：

- **DNS 泄漏**：服务端（权威台）侧识破“替你查的解析器”。
- **WebRTC 泄漏**：**你自己浏览器**里就能读到 STUN 探测回来的公网 IP——`browserleaks.com/webrtc` 就是读这些 ICE 候选，比对“WebRTC Public IP”和你的代理出口是否一致；不一致（露出真实 ISP IP）= 泄漏。

### 11.2 mihomo 配置 / 浏览器策略：让 STUN 的 UDP 别走真实出口

核心思路是正向的：**保证这些 STUN/TURN 的 UDP 探测要么走代理、要么直接拒掉**，让它们拿不到你的真实 IP。在规则里精准处理常见 STUN/TURN 端口：

```yaml
rules:
  # 直接拒绝常见 STUN/TURN 探测（最稳，浏览器拿不到公网 candidate）
  - AND,((NETWORK,UDP),(DST-PORT,19302)),REJECT       # 19302 常见于 Google STUN
  - AND,((NETWORK,UDP),(DST-PORT,3478-3481)),REJECT    # 3478-3481 常见 STUN/TURN
  # …这些要放在 RULE-SET(cn)/GEOIP,CN/MATCH 等宽泛规则【前面】
```

这些端口只是**常见**探测端口、不是“所有 WebRTC 端口”。先精准拒这几个；若 `/connections` 里还看到新的 UDP STUN/TURN 出口，再按日志补规则。若你需要 WebRTC 能用（如开会），则改成把这些 UDP 指向代理 group 而不是 REJECT。

> **关键前提：REJECT 只在流量进了 mihomo 时才拦得住。** 开了 TUN，浏览器的 STUN UDP 被透明接管进 mihomo，上面的 REJECT 才生效；**只用 mixed-port（HTTP/SOCKS 代理）、没开 TUN 时，浏览器默认直接发 STUN 的 UDP、根本不经过 mihomo**，这些 REJECT 形同虚设、WebRTC 照样泄漏真实 IP（实测见 [§12.2](#122-webrtc-泄漏怎么测)）。no-TUN 场景只能靠浏览器侧堵：Chromium 加 `--force-webrtc-ip-handling-policy=disable_non_proxied_udp`，Firefox 设 `media.peerconnection.ice.proxy_only=true`（或干脆 `media.peerconnection.enabled=false` 关掉 WebRTC）。

## 12. 探测与验证 DNS / WebRTC 泄漏

两类泄漏的**探测方法**集中放这儿（探测时顺带大致回顾原理）：DNS 靠“独一随机子域逼查询走到权威台”识破替你查的解析器，WebRTC 靠读 ICE 候选里的 `srflx` 看 STUN 拿到的出口 IP。

### 12.1 DNS 泄漏怎么测：browserleaks / bash.ws + 排障

**`browserleaks.com/dns` 凭什么知道你 DNS 泄漏？** 它把自己设成了“被查域名的权威总台”：

1. 给你一个**独一无二的随机子域**，如 `7f3a9k2.dnsleaktest.browserleaks.com`（每个访客不同）。
2. 你的浏览器解析它 → 世界上只有 browserleaks 的权威服务器知道这个怪名字 → 查询**一定层层转到它的总台**。
3. 总台看到“`7f3a9k2` 是从 IP=202.x（某 ISP 的解析器）来问的” → 于是知道你**实际用的解析器是谁、在哪个运营商/国家**，并靠那个专属随机名跟你这次会话对上号。
4. 判定：你挂着境外节点、却被发现解析器在“中国电信·杭州” → DNS 漏在了本地。

对照“是谁看到了什么”：**ISP 解析器看到「你要去哪」；域名权威台看到「是谁在替你问」**。browserleaks 故意当后者，所以能识破 DNS 出口。

**可脚本化自测（`bash.ws`，给 agent / CI 跑、不用手点网页）**：`bash.ws` 是 `macvk/dnsleaktest` 那套 DNS-leak 测试的 API，同样靠"独一随机子域逼查询走到它权威台"的原理。经代理（mixed-port）跑一遍：

```bash
P=http://127.0.0.1:7890
id=$(curl -s --proxy $P https://bash.ws/id)          # 拿一次性测试 id
for i in $(seq 0 6); do curl -s --proxy $P "https://$i.$id.bash.ws/" >/dev/null; done   # 触发权威台
curl -s --proxy $P "https://bash.ws/dnsleak/test/$id?json"   # 读结果：权威台看到哪些解析器
```

判读：返回里 `type:"dns"` 的条目就是权威台看到的解析器。**全是你 `nameserver` 配的 DoH 提供商（如 Google/AS15169）、零个本地 ISP/校园解析器 = 不漏**；冒出一个中国 ISP 解析器 = 漏。（注：bash.ws 自带的 "may be leaking" 结论是"解析器 IP≠出口 IP 就报漏"的朴素启发式，会误报；按"有没有暴露 ISP 解析器"自己判更准。）

**也可直接访问 `browserleaks.com/dns` 页面交叉验证**（经代理加载、读页面的 "Found N Servers, M ISP" + 解析器列表）——实测和上面 bash.ws 结论一致：解析器全 Google DoH、ISP 标成代理落地的那家，无本地解析器。

**排障时怎么看单条真实记录**（绕开本机 fake-ip/hijack 的两招）：

```bash
# DoH：走 443 不碰 :53，hijack 拦不到，拿到真公网解析
curl -s "https://223.5.5.5/resolve?name=<域名>&type=A"
# --resolve：根本不查 DNS，直接把域名钉到指定 IP（验某个后端时用）
curl --resolve <域名>:443:<IP> https://<域名>/
```

> `dns-hijack any:53` 会把普通 `dig`/`nslookup`/`getent`/`host` 的查询都劫进 mihomo——**但回不回假 `198.18.x` 取决于 `enhanced-mode`**：只有 `fake-ip` 才回占位 IP（此时才需要上面两招绕开拿真实记录）；`redir-host`/`normal` 下劫持仍在、回的却是**真实 IP**（本机 redir-host 实测 `www.google.com`→`142.251.x`，`getent` 就是真记录、两招用不着）。所以这两招是 **fake-ip 专属**的排障手段，别默认 hijack 机器一定回 198.18.x。

### 12.2 WebRTC 泄漏怎么测

**用运行态连接验证**

排查时别只看网页上的数字，对照 mihomo 运行态：

```bash
curl -s http://127.0.0.1:9090/connections
curl -s --max-time 3 "http://127.0.0.1:9090/logs?format=structured&level=info"
```

重点字段：`host`（访问的域名/STUN 域名）、`network`（tcp/udp）、`destinationPort`（STUN 常见 19302、3478-3481）、`chains`（最终是代理节点 / `DIRECT` / `REJECT`）、`rule`/`rulePayload`（是否被 `cn`/`GEOIP,CN`/`MATCH` 误命中）。看到 STUN 的 UDP 命中 `DIRECT` 就是泄漏源。

**用无头浏览器实测 WebRTC 泄漏**

`browserleaks.com/webrtc` 要手点；想可复现 / 给 agent 跑，用无头浏览器（Playwright/camoufox 之类）起一个、经 mixed-port 代理、收 ICE candidate，看 `srflx`（server-reflexive=STUN 看到的公网 IP）是不是你的代理出口。核心就一段页面内 JS：

```js
// 浏览器经 proxy 起（launch proxy=http://127.0.0.1:7890），页面里：
pc = new RTCPeerConnection({iceServers:[{urls:'stun:stun.l.google.com:19302'}]})
pc.createDataChannel('x')
pc.onicecandidate = e => collect(e.candidate && e.candidate.candidate)
await pc.setLocalDescription(await pc.createOffer())   // 等几秒收集完
// 候选串里 "typ srflx" 那条的 IP = STUN 看到的出口
```

判读：`host` 候选如今多是 mDNS `.local`（浏览器已混淆本地 IP、不漏内网）；**关键看 `srflx`**——等于代理出口=没漏，等于另一个真实公网 IP=漏了。

> **实测对照（同一段 STUN 探测，`srflx`=STUN 看到的出口）**：
>
> | 浏览器 | 机器 / 模式 | `srflx` | 漏？ |
> |---|---|---|---|
> | Chromium 默认 | mixed-port、TUN 关 | **真实公网 IP** | 漏 |
> | Chromium `--force-webrtc-ip-handling-policy=disable_non_proxied_udp` | mixed-port、TUN 关 | 空 | 不漏 |
> | Chromium | TUN 开 | 空 | 不漏 |
> | Camoufox（反检测）+ proxy | mixed-port、TUN 关 | **代理出口 IP（spoof）** | 不漏 |
> | Camoufox | TUN 开 | 空 | 不漏 |
>
> 坐实 [§11.2](#112-mihomo-配置--浏览器策略让-stun-的-udp-别走真实出口)：no-TUN 下 mihomo 的 UDP-REJECT 拦不到浏览器 STUN（那条 UDP 压根不进 mihomo）。防泄漏三条路任选其一：① **TUN** 网络层兜底；② **浏览器策略**（Chromium flag / Firefox `media.peerconnection.ice.proxy_only`）；③ **反检测浏览器**（camoufox 默认把 WebRTC 出口 spoof 成代理 IP，连 flag 都不用——这正是 browser-use 之类用 camoufox 做 stealth 的原因）。OS 防火墙禁非代理 UDP 也算。**TUN 不是唯一解。**

也可经代理**直接访问 `browserleaks.com/webrtc` 页面交叉验证**：默认 Chromium + no-TUN 下，该页 "Public IP Address" 显示的就是 srflx 那个真实公网 IP，并直接标 `WebRTC IP doesn't match your Remote IP` 判为漏——与上面自写 STUN 探针结论一致。

---

# 附录：实测封锁记录（field observations，归因多未坐实）

> **本附录只放“梯子 / 技术侧”**：被墙**现象** + **协议 / 技术归因**（未坐实）+ **对照实验与缓解**。每台机器的**规格 / IP / 延迟 / 被墙时间线 / 换 IP 操作与费用**属运营事实，见 `vps-maintenance` skill 的 `vps-quality`「历史服务器信息」（A=RackNerd、B=LisaHost）。样本都很小，归因一律标“未坐实”，只作下次对照。

## A. 落地 IP 被大陆精准屏蔽（RackNerd，长期跑 Hysteria2，2026-06-08）

RackNerd（海外 VPS）的 Hysteria2 主节点跑一段时间后，某天起从**大陆任何出口**对这台 IP 的任何端口（22/443/ICMP）全 timeout，而**同 /24 邻居 IP 正常**、境外多地探测全通、VPS 本机服务健康——形态像“大陆精准屏蔽这一个 IP”。

> **可能原因（未验证）**：QUIC over UDP 单 IP 持续大流量是 GFW 主动探测的特征之一；落地 IP 注册了公开域名长期暴露；也可能是机房 IP 段整体波及、与协议无关。

**后续（2026-06-27 更新）**：没迁协议、没换机器，只**付费给这台 VPS 换了一个 IP**（换 IP、Hysteria2 照跑）。换 IP 后短期内（截至更新日）未再复现被墙，至今仍在日常使用该 Hysteria2 节点。→ 单 IP 换干净就恢复、协议没动也没事，**更像“那个具体 IP 被点名”而非“Hysteria2/QUIC 协议特征触发”**；但样本只一次、观察窗口短，归因仍未坐实。（这台机器的规格 / IP / 延迟明细见 `vps-maintenance` skill 的「历史服务器信息」。）

## B. 长期稳定的 vless 节点被墙（LisaHost，2026-06-25）

LisaHost（海外住宅 IP VPS）上**长期稳定使用**的 vless(+ws+TLS) 节点，于 2026-06-25 起被墙。值得注意：这是 **TCP 系 vless、不是 QUIC/Hysteria2**，且已长期暴露使用——说明封锁不限于 QUIC/UDP 那一类特征，长期暴露的 TCP+TLS 节点同样会中招。

> **归因（未坐实）**：长期固定的域名 / 落地 IP / vless+ws-over-TLS 的流量指纹长期暴露都可能是诱因。

## C. RackNerd 新 IP 仅部分源网络不可达（2026-07-13）

现象：主选择器切到 RackNerd 的 vless+ws 节点后，新建的 `curl -I https://api.github.com` 先收到本地 Mihomo 的 `200 Connection established`，随后报 TLS `unexpected eof`；同一落地的 Hysteria2 节点也失败。与此同时，已经运行的 Codex 仍能继续交互。

分层实测：

- DoH 得到落地真实 IP；当前网络绕开代理直连该 IP 的 22/80/443 全部 TCP timeout，vless/ws 的 443 与 Hysteria2/QUIC 都不可用；控制组 LisaHost 可完成 TCP/TLS。
- 当前机器存在正常默认路由，但到 RackNerd 的 TCP/ICMP MTR 不返回 hop；到控制节点的 TCP MTR 可完整到达。单凭零 hop 不能定位具体丢弃设备。
- Check-Host 的 [10 地 TCP:443 探测](https://check-host.net/check-report/444f3075k71) 全部成功；[10 地 HTTPS 探测](https://check-host.net/check-report/444f3f86kffa) 全部完成 TLS/HTTP 并返回普通请求的 `403`。这证明当时 VPS、443 与 TLS/HTTP 前端并未全局 down，但没有单独验证完整 VLESS 鉴权。
- Codex 连接表显示，其 `responses_websocket` 在切节点前已通过 LisaHost 建立；selector 切到 RackNerd 后，这条既有 socket 的 `chains` 没变，所以它继续工作。针对 RackNerd 新建的 GitHub/ChatGPT delay 都失败。

结论：这次不是“WebSocket 协议能穿过坏节点”，也不能简单归为落地全局被墙；证据只支持**当前源网络到 RackNerd 的双向路径或源地址策略有问题**。要继续区分“客户端/中间上游没把 SYN 送到”与“RackNerd/抗 DDoS 收到后按源丢弃”，决定性实验是在落地同时抓 `tcpdump`：看当前公网源 IP 的 SYN 是否到达、SYN-ACK 是否发出。没有服务端抓包前，归因保持未坐实。

## 通用对照实验与缓解

- **对照实验**：停掉对应监听等 24~72h 看 IP 是否恢复（恢复=支持“代理流量触发”假设）。
- **缓解**：从大陆侧 ssh 改 `ProxyJump` 经境外不受影响的跳板；彻底解决换 IP（A 已验证有效）+ 换域名，或把协议迁到 Reality 这类更强 fingerprint masking 的方案。
