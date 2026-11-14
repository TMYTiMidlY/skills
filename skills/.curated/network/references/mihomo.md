# Mihomo 内核、系统接管与出站链路

本文说明内核如何接收、解析和选择出站流量，以及 TUN、系统代理和应用之间的边界。安装托管、订阅生命周期与 shell 环境见 [clashctl](clashctl.md)，WSL 网络管道的实施见 [WSL](wsl.md)，远程桌面与服务接入见 [远程接入](remote.md)。先读取实际进程、监听、配置输入与路由；改配置、切节点、重建网卡或重启前确认影响范围和授权。

## <a id="architecture"></a>架构与流量路径

Mihomo 是 Clash Meta 的 Go 内核，一个进程同时包含控制面和数据面。REST API 与 Dashboard 用来查询和调整运行态；代理监听、DNS、规则、TUN 和各协议出站承担实际流量。

```text
应用 → mixed-port 显式入口 / TUN 接管
     → 域名与地址处理 → rules → proxy-group 的当前选择 → outbound → 目标
```

应用的代理环境变量只决定请求送到哪个入口；出口仍由内核模式、规则和组的选择决定。系统代理设置、shell 环境与 TUN 路由是不同接入机制，需按实际应用逐层核对。控制器地址与端口由配置启用，`127.0.0.1:9090` 是本文示例。

## <a id="installation"></a>安装与配置发现

### <a id="distribution"></a>分发方式

官方提供预编译二进制、容器镜像和源码。按操作系统、CPU 架构及指令集选择发行产物；所核对构建矩阵中的 amd64-compatible、v1、v2、v3 对应不同兼容目标，较高等级要求 CPU 支持相应指令。拿不准 CPU 能力时先选兼容目标。

获得安装授权后，可在已授权工作目录下载并保留压缩包，再安装到约定位置；替换已有二进制前核对服务归属并保存恢复材料。例如 Linux amd64：

```bash
ver=v1.19.27
curl -fL -o mihomo.gz "https://github.com/MetaCubeX/mihomo/releases/download/$ver/mihomo-linux-amd64-compatible-$ver.gz"
gzip -dc mihomo.gz > mihomo
chmod +x mihomo
./mihomo -v
# 确认目标位置与替换范围后：sudo install -m 0755 mihomo /usr/local/bin/mihomo
```

官方容器镜像 `metacubex/mihomo` 使用 `/mihomo` 为入口，将配置挂到 `/root/.config/mihomo`。部署时选定镜像版本或 digest；例如只发布本机显式代理与控制器：

```bash
docker run -d --name mihomo --restart=always \
  -v '<配置目录>:/root/.config/mihomo' \
  -p 127.0.0.1:7890:7890 -p 127.0.0.1:9090:9090 \
  'metacubex/mihomo:<版本>'
```

端口发布还要求容器内监听匹配容器网络地址；回环只发布宿主访问面。容器 TUN 另需网络命名空间、`NET_ADMIN`、`/dev/net/tun` 与路由配置配合。镜像自带的地理规则数据及挂载覆盖也须核对。

GUI 客户端可内置独立内核，例如 Clash Verge Rev 的 `verge-mihomo.exe`、Clash Party 程序目录中的 `mihomo.exe`；手动 CLI 又可能是另一份。按实际进程路径、`-d`/`-f` 和服务参数区分实例。程序目录、用户 profile 和缓存是不同对象；清理前确认没有共享配置或其他进程引用，避免用“删 GUI 数据”推断独立内核必定不受影响。

> 分发与命名依据：[构建矩阵](https://github.com/MetaCubeX/mihomo/blob/a84724665eb7f989809abe463c05f5723bd24975/.github/workflows/build.yml#L31-L71)、[容器入口与数据目录](https://github.com/MetaCubeX/mihomo/blob/24b6de71fc1c4ea282dcbc7b65a8bcbcc0c75e6c/Dockerfile#L1-L30)。源码构建见[源码构建](#source-build)。

### <a id="config-directory"></a>配置目录

配置目录与二进制所在目录独立。所核对版本先取运行用户 home 下的 `.config/mihomo`；该路径不存在时才使用 `XDG_CONFIG_HOME/mihomo`。默认配置名为 `config.yaml`。Windows 对应 `%USERPROFILE%\.config\mihomo`。sudo 或服务可能改变身份与 HOME，应查看实际上下文，或显式传参：

```text
-d <目录>       配置及资源 home
-f <文件路径>   配置文件
```

托管环境可把资源目录和运行配置分开，例如 `-d <安装目录>/resources -f <安装目录>/data/runtime.yaml`。查实际进程命令行、service 的 ExecStart 与启动器，而非从安装位置猜配置。Windows 的高权限进程参数可能需要相应读取权限；读不到不等于不存在。

`GET /configs` 返回运行态通用设置，不返回当前配置文件路径；可以结合 `/proxies` 核对实例内容，但有效配置来源仍由启动参数、默认路径和管理程序确定。API 的显式 `path` 重载受安全路径检查：默认 home 内路径，额外目录可列入 `SAFE_PATHS`。`SKIP_SAFE_PATH_CHECK` 会扩大输入边界，常规维护优先使用允许目录。

> 依据：[配置路径与安全路径](https://github.com/MetaCubeX/mihomo/blob/24b6de71fc1c4ea282dcbc7b65a8bcbcc0c75e6c/constant/path.go#L24-L104)、[重载输入](https://github.com/MetaCubeX/mihomo/blob/24b6de71fc1c4ea282dcbc7b65a8bcbcc0c75e6c/hub/route/configs.go#L391-L442)、[运行态输出](https://github.com/MetaCubeX/mihomo/blob/24b6de71fc1c4ea282dcbc7b65a8bcbcc0c75e6c/hub/executor/executor.go#L129-L210)。

### <a id="startup-validation"></a>启动与校验

```bash
mihomo -v
mihomo -t -d '<配置目录>' -f '<配置文件>'
# 已获准启动时去掉 -t，沿用同一 -d/-f。
```

```powershell
& '<内核路径>\mihomo.exe' -t -d '<配置目录>' -f '<配置文件>'
```

`-t` 验证配置，不能代替监听、节点和目标业务验证。前台启动的进程生存期由终端或启动器决定；长期运行应交给明确的服务管理者。TUN 创建和路由修改需要内核进程具备平台所需权限，通常是管理员、root 或相应能力；调用控制 API 的客户端只需控制器允许的访问权限。

### <a id="gui-config-chain"></a>GUI 配置链

GUI 通常维护自己的 profile、合并/脚本和生成配置，再把结果传给捆绑内核。直接改生成文件可能在下次生成时被覆盖。一次 Clash Verge 部署观测到：基础 `config.yaml` 加当前 profile/merge/script 生成 `clash-verge.yaml`，再通过命名管道 `\\.\pipe\verge-mihomo` 交给核心；`verge.yaml` 中的界面端口字段与核心实际端口可能不同。

定位时读取该版本的输入、生成物、进程参数和日志。需要修改时完整退出 GUI，修改其受支持的持久输入，再启动并确认 `Mixed(http+socks) proxy listening at:` 日志及实际监听。核心可能由 SYSTEM 服务托管，普通 shell 无权停止；按对应 GUI/服务的维护方式处理。系统代理目标与核心端口错位的完整排查见 [Windows 代理目标与内核监听](#windows-proxy-target)。

> 上述文件名与行为是特定部署的观测，原记录缺 GUI 版本，不能替代目标版本的配置文档。确认实际生成链后再操作。

<a id="3-流量链路入口规则与节点组"></a>
## <a id="traffic-selection"></a>流量入口与出站选择

### <a id="mixed-port-tun"></a>mixed-port 与 TUN

`mixed-port` 接受主动递交的 HTTP/SOCKS 请求，适合选择性代理；TUN 通过虚拟网卡和路由接管网络包，适合需要透明处理的流量。示例默认只服务本机：

```yaml
mixed-port: 7890
allow-lan: false
```

`allow-lan: false` 时，所核对监听实现返回回环地址；启用 LAN 后才由 `bind-address` 选择地址，`'*'` 表示所有接口。需要远程访问时，按预期访问面、地址稳定性、认证和防火墙选监听地址。绑定虚拟网卡地址要处理其未就绪、重连和地址变化；全接口监听则会扩大暴露面。

> 依据：[监听地址生成](https://github.com/MetaCubeX/mihomo/blob/24b6de71fc1c4ea282dcbc7b65a8bcbcc0c75e6c/listener/listener.go#L709-L718)。客户端代理 URL 与环境变量见 [clashctl 入口协议](clashctl.md#proxy-url-schemes)。

### <a id="rule-matching"></a>规则匹配

`mode: rule` 按规则表从上到下首条匹配；常用末尾 `MATCH,<组>` 承接未命中的流量。该版本实现未命中任何规则时回到 DIRECT。`GLOBAL` 是 global 模式使用的选择器，修改它不等于改变 rule 模式的分类组。

排查出口要沿每层 `.now` 到最终 outbound：`分类组 → 主选择器 → 具体节点`。Selector 只能选择自己 `.all` 中的成员，否则返回 `proxy not exist`。目标节点若在外层 `.all`，可直接切外层；否则先选内层组再切其成员。修改主选择器会影响所有引用它的分类组。

切组改变后续连接选择，已有 TCP、WebSocket 或下载连接不会在线迁移。使用新进程/新连接验证，并在 `/connections` 检查 `start`、`chains` 和 `rule`。curl 的 `--no-keepalive` 关闭 TCP keepalive 探针，并非禁止 HTTP 复用。选择器选择可由 profile 的持久化设置写入 `cache.db`，只改配置默认项可能仍看到缓存选择。

> 机制依据：[模式选择](https://github.com/MetaCubeX/mihomo/blob/24b6de71fc1c4ea282dcbc7b65a8bcbcc0c75e6c/tunnel/tunnel.go#L390-L415)、[规则匹配](https://github.com/MetaCubeX/mihomo/blob/24b6de71fc1c4ea282dcbc7b65a8bcbcc0c75e6c/tunnel/tunnel.go#L654-L712)、[Selector 成员检查](https://github.com/MetaCubeX/mihomo/blob/24b6de71fc1c4ea282dcbc7b65a8bcbcc0c75e6c/adapter/outboundgroup/selector.go#L79-L92)。

### <a id="proxy-groups"></a>节点组

`url-test` 根据测试延迟选择节点；`fallback` 按候选顺序使用可用节点。根据真实工作负载调整探测间隔和切换容忍度，避免把探测噪声当业务改善：

```yaml
proxy-groups:
  - name: <auto-group>
    type: url-test
    proxies: [<node-a>, <node-b>]
    url: <探测URL>
    interval: 300
    tolerance: 150
    lazy: false
```

这里的数值是示例。延迟相近时可提高 tolerance 或手选稳定节点；同时比较目标可达性、吞吐、抖动、丢包和路径跳数。探测结果变化会影响后续选择；已有连接的中断还需查节点、路径或应用重连，不能单凭自动切组解释。协议选择见[协议与性能](#protocol-performance)。

## <a id="providers"></a>Provider 与内核配置边界

### <a id="provider-loading"></a>Provider 装载与规则集

`proxy-provider` 是内核装载的节点源，HTTP 类型通过 URL 获取节点。所核对实现支持请求头、获取时使用的代理、大小限制与 age 解密；解析 YAML，失败时尝试兼容的 V2Ray 订阅转换，再过滤、去重、覆写并生成内核节点对象。`rule-provider` 则提供规则集，装载对象不同。

> 依据：[Provider 解析链](https://github.com/MetaCubeX/mihomo/blob/24b6de71fc1c4ea282dcbc7b65a8bcbcc0c75e6c/adapter/provider/provider.go#L343-L450)。

### <a id="provider-overrides"></a>节点筛选与覆写

节点级 `override` 在装载边界调整字段，结果供内核自身建连使用，不是导出一份供其他程序使用的新订阅。该版本字段包括 `tfo`、`mptcp`、`udp`、`udp-over-tcp`、`up`、`down`、`dialer-proxy`、`skip-cert-verify`、`interface-name`、`routing-mark`、`ip-version`，以及名称前后缀和正则改名 `proxy-name`。正则改名使用 regexp2，不能直接按 Go 原生正则能力推断。

筛选使用 `filter`、`exclude-filter`、`exclude-type`；前两者支持以反引号分组的正则，类型排除以 `|` 分隔。按对应 schema 检查实际语义。该版本的 overrideSchema 不含任意 `server`/`port` 替换能力，中转端点改写应由外部受控配置变换完成。

> 依据：[覆写字段与执行](https://github.com/MetaCubeX/mihomo/blob/24b6de71fc1c4ea282dcbc7b65a8bcbcc0c75e6c/adapter/provider/override.go#L10-L101)、[Provider schema](https://github.com/MetaCubeX/mihomo/blob/24b6de71fc1c4ea282dcbc7b65a8bcbcc0c75e6c/adapter/provider/parser.go#L1-L160)。

### <a id="config-generation-boundary"></a>整份配置的生成边界

内核读取已经组装好的配置；把完整订阅的 rules、proxy-groups、DNS 等合并成配置，是外部管理程序或订阅转换器的工作。GUI 生成链见 [GUI 配置链](#gui-config-chain)，clashctl 的原始订阅、Mixin、运行文件和刷新关系见[配置生命周期](clashctl.md#config-lifecycle)。嗅探字段 `override-destination` 处理连接目标，属于另一机制。

<a id="7-tun-路由的边界"></a>
## <a id="tun-routing"></a>TUN 与系统路由

### <a id="auto-strict-route"></a>auto-route 与 strict-route

`auto-route` 配置系统路由，将符合条件的包送往 TUN；具体前缀取决于包含、排除与平台实现。Windows 原观测出现过 `0.0.0.0/1` 与 `128.0.0.0/1`，带排除集时也会拆成更细前缀。宿主路由处理的 NAT 下游流量可以一并进入 TUN。

Windows 的 `strict-route` 在所核对 sing-tun v0.4.17 中属于 WFP 过滤逻辑：存在 TUN 接口放行、未配置 IPv6 地址时的阻断及 DNS 过滤条件，普通 IPv4 全阻断分支被注释。路由创建与 ForwardingEnabled 在其他分支处理。Linux 的严格路由和策略路由实现有平台差异，不能从 Windows 的过滤分支推出所有平台行为。

> 源码：[Windows 自动路由](https://github.com/MetaCubeX/sing-tun/blob/v0.4.17/tun_windows.go#L119-L157)、[WFP 严格路由](https://github.com/MetaCubeX/sing-tun/blob/v0.4.17/tun_windows.go#L180-L340)。原记录在 Mihomo v1.19.24 下固定 auto-route，切换 strict-route 的 A/B 中，WSL NAT 新鲜态仍从代理出口出网；该条件下 strict-route 不是接管开关。更改 TUN 配置会涉及[网卡重建](#tun-recreate)。

### <a id="direct-bypass"></a>TUN 路由排除与 DIRECT 出站

`IP-CIDR,...,DIRECT` 决定包进入内核后的出站，路径仍可为 `应用 → TUN → Mihomo → DIRECT → 目标`。连接表可能看到 `inboundName: DEFAULT-TUN` 与 DIRECT 链。完全不进 TUN 则需要系统路由与接管排除形成直达路径。

特例规则放在可能抢先命中的宽泛规则前；首条匹配机制见[规则匹配](#rule-matching)。路由排除参数及显式入口边界见下一节。

### <a id="route-exclude"></a>route-exclude-address

`route-exclude-address` 将目标排除出 TUN 自动路由。它不负责保证系统存在可用的物理路由；排除中转或私网通道依赖的公网目的地前，要核对实际路由、下一跳与回程，避免切断自身通道。

路由层排除影响裸包是否进入 TUN；规则层 DIRECT 影响已经进入引擎的连接，两者可以并用。下游若经 tun2socks 把流量作为 SOCKS 请求递交到 mixed-port，该请求不会再受宿主 TUN 的目的地址排除控制，需由规则选择出站。多个私网的排除集和 DIRECT 集可能不一致，应逐一核对。

```text
Windows：route print <目标IP>
Linux：  ip route get <目标IP>
```

> 字段传递依据：[TUN listener 的路由选项](https://github.com/MetaCubeX/mihomo/blob/24b6de71fc1c4ea282dcbc7b65a8bcbcc0c75e6c/listener/sing_tun/server.go#L1-L260)。

### <a id="tun-tcp-false-open"></a>TUN 接管下的 TCP 端口探测

TUN 前端与目标侧拨号分离时，应用侧 TCP 握手可以先完成。System 栈先 Accept 再交给连接处理器，gVisor 栈创建端点并完成前端连接后交给处理器；Mihomo 此后才匹配规则、选出站和拨目标。因此 `nc -z` 的成功可能只覆盖应用到 TUN 前端，随后才出现 EOF、reset 或 timeout。

已知服务用完整协议验证，例如 SSH 收到版本串并进入密钥交换、HTTP 收到状态/响应头、TLS 完成握手。未知端口扫描宜在目标路径未被 TUN 接管的独立环境执行：

```bash
ssh -vvv -o ConnectTimeout=6 '<user>@<目标IP>'
curl --noproxy '*' -v --max-time 8 'http://<目标IP>:<端口>/'
timeout 8 openssl s_client -connect '<目标IP>:<端口>' -brief
# 在已确认未被 TUN 接管的环境：
nmap -Pn -sT --reason -p '<端口列表>' '<目标IP>'
```

同机有物理直达路径时，先核对 `ip route get <目标IP> from <源IP> oif <物理网卡>`，再以相同目标、端口和超时对照 `nc -s <源IP>`、`ssh -B <物理网卡>` 或 `curl --interface <物理网卡>`。绑定接口仍需核对策略路由；DIRECT 规则本身不消除 TUN 前端握手。

> 依据：[System acceptLoop](https://github.com/MetaCubeX/sing-tun/blob/dfc71de64aed159d9a09a5df43077bab0671db1f/stack_system.go#L335-L352)、[gVisor Forward](https://github.com/MetaCubeX/sing-tun/blob/dfc71de64aed159d9a09a5df43077bab0671db1f/stack_gvisor_tcp.go#L80-L115)。2026-08-21 Linux 对照中，目标路由为 Meta、TUN 地址有本地 TCP listener，抽样26个端口（含1、12345、54321、65534）均立即 connect 成功，但 SSH 在 banner 前关闭、HTTP 空响应、TLS 无握手；同目标绑定物理出口后22/139拒绝、445超时。该观测定位了前端握手假阳性，不能据此推断目标真实开放全部端口。

### <a id="wsl-forwarding"></a>WSL NAT 转发与宿主 TUN

Windows 宿主 TUN 可接管 WSL NAT 裸出站，但其可靠性需在实际版本和路径验证。原部署 v1.19.24 的新鲜 TUN 多次成功接管，宿主路由与 fake-ip 也能闭环；早期连续测试还出现过几分钟后下游超时、宿主自身在线、路由仍指 TUN的情况。关闭 strict-route、每90秒保活都未在那些测试中消除异常；两段式重建后曾约4秒恢复。异常触发机制没有由这些对照唯一确定。

2026-09-23 的同版本复测进一步显示间歇异常和自愈，应将两次证据一起使用：

| 条件或观察 | 记录 |
|---|---|
| 宿主状态 | 独立配置，进程自07-07未重启；auto-route、strict-route、私网 route-exclude、dns-hijack any:53，DNS 为 redir-host 返回真 IP。 |
| 路由 | 为私网排除拆分覆盖，未见单条 `0.0.0.0/1`；经排除私网的 SSH 全程正常。 |
| 下游与探针 | WSL NAT 无本地代理；公网出口查询与 generate_204 双探针，约15秒间隔，共30轮、约10.5分钟。 |
| 结果 | 前约6.5分钟20轮通过；约6.5–10分钟有5轮异常，其中3轮双探针超时；末2轮无需重建自行恢复。 |
| 归因限制 | 异常分布时窗约3.5分钟，不等于精确连续停机时长；没有完全排除节点侧抖动，交叉成功/失败只支持路径可能间歇异常。 |
| 源地址 | 此部署的 TUN 捕获转发在 connections 中显示为 TUN 自身地址 `198.18.0.1`，而 SOCKS/mixed 入口保留下游来源。用 SRC-IP-CIDR 区分该路径下各发行版前必须看实际 metadata，不能假设原 NAT 源地址仍存在。 |

该部署的可靠性不足以支撑稳定下游单靠宿主透明接管；可选择显式 mixed-port 或下游 tun2socks 路径。NAT 网关可能变化，动态发现、SSH ProxyCommand 和 tun2socks 配置由 [WSL 出站接入](wsl.md)说明；mirrored 的回环互通也按实际模式验证。宿主自身可做裸请求与显式 `--proxy http://127.0.0.1:<端口>` 对照：显式成功而裸请求失败时，先查 TUN、系统路由、DNS 与权限，不立即归因远端节点。

## <a id="system-proxy"></a>Windows 系统代理

### <a id="windows-proxy-scope"></a>Windows 系统代理的用户作用域

Windows 用户 Internet Settings 中的手动代理通常由 GUI 或用户设置，核心是否运行不会自动保证这些设置正确。`HKCU` 表示调用上下文的当前用户；跨用户检查可查看已加载的 `HKU\<SID>\Software\Microsoft\Windows\CurrentVersion\Internet Settings`，先将 SID 对应到受影响用户。

用户 Internet 代理、WinHTTP 配置、应用自己的代理和 shell 环境作用域不同。管理员会话的 HKCU 正常，不足以说明另一个登录/RDP 用户正常；未加载的用户 hive 应在对应用户上下文检查，或在另获授权的维护流程中处理。

> 官方依据：[HKCU 与 HKU 映射](https://learn.microsoft.com/en-us/windows/win32/sysinfo/predefined-keys)、[当前用户与连接代理配置](https://learn.microsoft.com/en-us/windows/win32/api/winhttp/nf-winhttp-winhttpgetieproxyconfigforcurrentuser)。检索日期2026-11-14；这里核对的是 Win32 用户/连接作用域，不将其外推为所有应用都使用同一代理。

### <a id="windows-proxy-target"></a>Windows 代理目标与内核监听

先用显式代理直测核心，再对照 GUI 配置、生成配置、监听与用户设置：

```powershell
curl.exe --proxy 'http://127.0.0.1:<核心端口>' --max-time 12 'https://www.gstatic.com/generate_204'
Get-NetTCPConnection -State Listen
$key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
Get-ItemProperty -LiteralPath $key -Name ProxyEnable,ProxyServer,AutoConfigURL -ErrorAction SilentlyContinue
```

显式请求成功而系统代理应用失败时，核对 ProxyServer 是否指向该 listener；GUI 的 `verge_mixed_port`、基础 `mixed-port` 和生成配置曾在同一部署中错位。按 [GUI 配置链](#gui-config-chain)修持久输入，再由 GUI 重设正确目标。`ProxyEnable=0` 时旧 ProxyServer 可能只是未启用的记录；PAC、自动发现及应用独立设置仍需另查。

### <a id="windows-proxy-residue"></a>Windows 多用户代理残留排查

强杀或禁用 GUI/服务可能跳过退出复位。历史案例中，同机一个用户 `ProxyEnable=0`，另一个用户却为 `ProxyEnable=1` 且 ProxyServer 为空，后者采用该设置的应用失去连接。应逐用户确认，而非只检查执行维护命令的管理员。

```powershell
# 当前用户先确认身份；跨用户只读取已加载且已确认归属的 SID。
whoami /user
$key = 'Registry::HKEY_USERS\<SID>\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
Get-ItemProperty -LiteralPath $key -Name ProxyEnable,ProxyServer,AutoConfigURL -ErrorAction SilentlyContinue
```

记录旧开关、目标、PAC 与策略后，确定受影响用户是恢复直连还是恢复有效代理。获得相应修改授权后，在该用户上下文关闭失效手动代理（ProxyEnable 置0），或通过受支持的系统/GUI设置写入正确目标；需要清理残留地址时保留恢复记录。刷新系统设置或重开受影响应用/会话后，用该用户的实际应用验收。代理进程停止与注册表修复分别确认；不要据一次空目标案例断言所有 Windows 网络栈都会同样失败。

<a id="10-dns-泄漏原理与-mihomo-配置"></a>
## <a id="dns-leak"></a>DNS 解析与泄漏控制

DNS 控制关注查询由谁处理、上游连接如何传输，以及应用是否另走旁路。HTTP CONNECT 或 SOCKS5h 传递域名可以把解析交给代理链，但最终解析位置仍取决于内核与出站协议。浏览器独立 UDP 地址探测另见 [WebRTC](#webrtc-leak)。

### <a id="dns-parties"></a>DNS 参与方与查询可见性

客户端向递归解析器查询，递归解析器再访问权威服务器。递归侧能关联查询及客户端信息；权威侧通常看见递归解析器出口，额外可见信息还受 ECS 等机制影响。DNS 泄漏是查询经过非预期路径或解析方，不能单凭解析器与代理出口 IP 不相等、或服务商地域判定。

### <a id="dns-modes"></a>dns-hijack 与 enhanced-mode

`dns-hijack` 决定已进入 TUN 的 DNS 目标是否转交内置解析器；`any:53` 匹配任意目标地址的53端口。`enhanced-mode` 决定内置 DNS 的响应和域名关联方式：

| 模式 | 响应与连接关联 |
|---|---|
| fake-ip | 未命中排除时从地址池返回占位地址，保留域名关联；真实解析可延后至建连路径。 |
| redir-host | 先真实解析，保存 IP→域名映射，供后续关联与分流。 |
| normal | 不附加上述映射/假地址处理；显式入口域名、嗅探等仍可能提供域名信息。 |

假地址来自 fake-ip，不是 hijack 本身。接管开关与返回模式也不足以单独保证隐私：需同时检查接管覆盖、IPv6、内核上游和应用自带 DNS。DoH/DoT 不匹配普通53端口劫持规则，但其传输仍可能经 TUN。

> 依据：[DNS 中间件](https://github.com/MetaCubeX/mihomo/blob/24b6de71fc1c4ea282dcbc7b65a8bcbcc0c75e6c/dns/middleware.go#L99-L185)、[DNS 劫持判定](https://github.com/MetaCubeX/mihomo/blob/24b6de71fc1c4ea282dcbc7b65a8bcbcc0c75e6c/listener/sing_tun/dns.go#L1-L120)。历史同配置对照中，redir-host 未分类域名使用默认境内 DoH，而 fake-ip 建连后权威侧看到境外解析出口；这是该规则、上游和节点组合的结果，不是 fake-ip 内置的境外解析保证。

<a id="102-mihomo-配置防泄漏--分流准--防污染"></a>
### <a id="linux-dns"></a>Mihomo DNS 与 TUN 配置

以下展示透明接管与加密上游的组合。按实际 IPv6 可达性、私网域名和解析策略修改；尊重规则的 DNS 还需要独立解析节点域名，防止建立代理时出现解析依赖环：

```yaml
ipv6: false
tun:
  enable: true
  stack: mixed
  auto-route: true
  auto-detect-interface: true
  strict-route: true
  dns-hijack: [any:53]
dns:
  enable: true
  ipv6: false
  enhanced-mode: fake-ip
  fake-ip-range: 198.18.0.1/16
  fake-ip-filter: ['*.lan', '*.local', 'time.*.com']
  respect-rules: true
  proxy-server-nameserver: [https://223.5.5.5/dns-query]
  nameserver: [https://223.5.5.5/dns-query, https://1.1.1.1/dns-query]
```

`fake-ip-filter` 给局域网、授时或依赖真实 IP 的对象回真实解析；名单按软件行为确定。`nameserver-policy`、规则和节点解析器共同决定 DNS 上游路径。DoH/DoT 加密查询内容，但仍有目的地址等网络元数据；以上配置不能被视为所有应用均无泄漏的证明。

> 所核对版本对 `respect-rules: true` 明确要求 `proxy-server-nameserver` 非空，见[DNS 配置校验](https://github.com/MetaCubeX/mihomo/blob/24b6de71fc1c4ea282dcbc7b65a8bcbcc0c75e6c/config/config.go#L1403-L1445)。下游自建 TUN 的地址应避开宿主 fake-ip/TUN 网段，实施见 [WSL](wsl.md)。fake-ip 还可能触发某些工具解析后的 SSRF 特殊地址检查；先核对来源与信任边界，具体工具处理交 `harness` skill，不全局放行保留地址。

### <a id="linux-resolved"></a>Linux systemd-resolved

应用查询回环 stub `127.0.0.53` 后由 resolved 查询上游，stub 路径可能未进入 TUN。只设 any:53 不足以覆盖所有解析路径；需要时让 Mihomo 监听本机 DNS，再将 resolved 上游指向该 listener。完整组合配置与验证见 [systemd-resolved 接入](setup.md#dns)。

### <a id="dns-probing"></a>DNS 出口与真实记录探测

权威侧测试为访客生成随机子域，使查询到达测试方权威服务器，再关联递归解析器出口。可用 [BrowserLeaks DNS](https://browserleaks.com/dns)核对解析器名单；`bash.ws` 历史脚本接口同样通过随机子域触发权威观察：

```bash
P=http://127.0.0.1:7890
id=$(curl -fsS --proxy "$P" https://bash.ws/id) || exit
for i in $(seq 0 6); do
  curl -sS --max-time 8 --proxy "$P" "https://$i.$id.bash.ws/" >/dev/null
done
curl -fsS --proxy "$P" "https://bash.ws/dnsleak/test/$id?json"
```

该接口示例来自历史观测，使用时先确认服务响应契约；失败先查服务状态，不把 API 失败当泄漏。返回中 `type:"dns"` 代表被观察解析器。原测试中解析器全属预期 DoH 网络，与 BrowserLeaks 一致；这只覆盖该客户端与测试路径。测试站按“解析器 IP 不等于出口”给出的警告可能误报，应同预期解析方、系统旁路和应用行为对照。

排障查询真实记录始终走 DoH；检查已知后端可跳过 DNS：

```bash
curl -fsS 'https://223.5.5.5/resolve?name=<域名>&type=A'
curl --resolve '<域名>:443:<真实IP>' 'https://<域名>/'
```

DoH 绕开53端口劫持，`--resolve` 固定该请求的地址；二者都不保证传输绕开 TUN。redir-host/normal 返回真地址也不改变接管规则，避免把普通53端口查询作为独立 DNS 旁路证据。

## <a id="webrtc-leak"></a>WebRTC 地址暴露与控制

### <a id="webrtc-mechanism"></a>ICE 与 STUN 地址探测

浏览器 `RTCPeerConnection` 收集 ICE 候选时可向 STUN 服务另发 UDP，获得 server-reflexive（srflx）地址。若这条流量直接出网，页面可能读到真实网络出口，即使网页 HTTP 已经走代理。HTTP 代理通常不承载浏览器这条独立 UDP；SOCKS 协议的 UDP 能力也不代表目标浏览器会采用它。

DNS 测试由权威侧辨认查询方；WebRTC 页面读取的是浏览器候选。两者应分别按实际路径验证。

### <a id="webrtc-policy"></a>TUN 与浏览器策略

先保证需控制的 UDP 确实进入 Mihomo，再让它通过支持 UDP 的代理或明确拒绝。常见端口示例：

```yaml
rules:
  - AND,((NETWORK,UDP),(DST-PORT,19302)),REJECT
  - AND,((NETWORK,UDP),(DST-PORT,3478-3481)),REJECT
  # 放在可能先命中的宽泛规则之前；其余规则接在后面。
```

这些端口不是穷尽清单；结合连接表补查其他 STUN/TURN 目标。会议等功能需要 WebRTC 时，改用合适的代理组并验证 UDP。只用显式 mixed-port 而浏览器 STUN 未进入内核时，规则无法处理该旁路。

浏览器侧可按版本核对 Chromium 的 `--force-webrtc-ip-handling-policy=disable_non_proxied_udp`，或 Firefox 的 `media.peerconnection.ice.proxy_only`；完全不用 WebRTC 时可关闭 `media.peerconnection.enabled`。这些是历史对照使用的配置入口，实施时核对目标浏览器的当前支持和功能影响。OS 防火墙限制非代理 UDP 也是网络层选项，需协调已有业务。

### <a id="webrtc-probing"></a>WebRTC 连接与候选地址验证

在 `/connections` 和日志中核对 `host`、`network`、`destinationPort`、`chains`、`rule`、`rulePayload`，看 STUN 是否走 DIRECT、代理或 REJECT。经 mixed-port 启动的浏览器可在页面中收集候选：

```js
const candidates = []
const pc = new RTCPeerConnection({iceServers: [{urls: 'stun:stun.l.google.com:19302'}]})
pc.createDataChannel('probe')
pc.onicecandidate = e => { if (e.candidate) candidates.push(e.candidate.candidate) }
await pc.setLocalDescription(await pc.createOffer())
// 等待 gathering 完成后检查 candidates，并 pc.close()。
```

`host` 候选可经 mDNS 混淆；重点检查 srflx 与实际 UDP 路径。无 srflx 可能因策略、拒绝或测试失败；显示代理地址也可能是页面值被伪装，需独立验证网络流量。

> 原无头浏览器对照：默认 Chromium 在 mixed-port/no-TUN 时显示真实公网 srflx；加上述 Chromium 策略后为空；开启 TUN 时为空。Camoufox 在 no-TUN 时显示经伪装的代理出口，TUN 开启时为空。前者仅证明页面展示变化，不能据此认定 UDP 已代理或网络无泄漏。原记录未给浏览器完整版本，保留为该环境观测；可再用 [BrowserLeaks WebRTC](https://browserleaks.com/webrtc)和独立网络证据交叉检查。

<a id="4-协议性能与客户端配置"></a>
## <a id="protocol-performance"></a>协议与性能

### <a id="protocol-selection"></a>协议选择

跨高延迟或丢包链路，要结合 TCP/UDP 可达性、拥塞控制、反代跳数和目标业务选择协议。VLESS+WS+TLS 可复用 HTTPS 反代；Hysteria2/TUIC 等使用 QUIC，但没有脱离路径条件的统一速度排名。

系统 `net.ipv4.tcp_congestion_control=bbr` 作用于内核 TCP，不直接控制用户态 QUIC。Hysteria2 的发送拥塞控制需分别看两方向协商：服务端按客户端接收带宽及自身上限决定发送速率；`ignoreClientBandwidth` 会改变带宽协商。所核对客户端在 `!RxAuto && actualTx > 0` 时选 Brutal，否则走其自适应控制器路径；服务端的 RxAuto 来自 IgnoreClientBandwidth。

在对应实现中，客户端配置有效 up/down、服务端允许客户端带宽时可在两个方向使用 Brutal，服务端限制仍可能降低实际速率。按真实容量设置，避免过量发包；未配置带宽或启用忽略开关时按该方向实现确认回退。用户态 BBR 与内核 BBR 的版本、参数也不能混称。

> 依据：[客户端协商](https://github.com/MetaCubeX/sing-quic/blob/68e10a6afdc3f42c9377d0ca0f7259c2b85a9a43/hysteria2/client.go#L461-L471)、[服务端协商](https://github.com/apernet/hysteria/blob/app/v2.6.1/core/server/server.go#L132-L162)。QUIC 多流可减少跨流队头阻塞，但不能用它单独解释一次单文件吞吐差异。配置意图、协商实现与受控测试应合并核对，不能仅读一份服务端配置就断言客户端已启用某控制器。

### <a id="vless-websocket"></a>VLESS WebSocket 配置

反代后的 VLESS+WS+TLS 节点要保持地址、TLS 验证名、Host 和 WS 路径对应：

```yaml
proxies:
  - name: <node-name>
    type: vless
    server: <代理域名>
    port: 443
    uuid: <uuid>
    tls: true
    servername: <证书域名>
    client-fingerprint: chrome
    network: ws
    ws-opts:
      path: <WebSocket路径>
```

指纹等字段依目标版本和服务端配置使用。MTU 先采用平台正常值；仅在小请求正常而大响应、TLS 或大文件异常时测试路径 MTU，再比较如1400/1380等诊断值。服务端反代与面板分别见 [Caddy](caddy.md)、[3x-ui](3x-ui.md)。

### <a id="throughput"></a>吞吐验证

`/delay` 是轻量目标请求的时延，不证明全速传输。下载用足够持续的样本，例如50–100MB；上传可从标准输入发送已知大小测试数据，先确认目标允许和测试流量范围：

```bash
P=http://127.0.0.1:7890
curl -f -o /dev/null --max-time 45 --proxy "$P" \
  -w 'dl=%{speed_download}B/s code=%{http_code}\n' '<下载测试URL>'
head -c 31457280 /dev/urandom | \
  curl -f -o /dev/null --max-time 45 --proxy "$P" \
    --data-binary @- -w 'ul=%{speed_upload}B/s\n' '<上传测试URL>'
```

多测源交叉检查 HTTP 返回码；历史测试中 Cloudflare 下载端曾403而上传正常，Hetzner/OVH可作其他样本，但站点当前可用性需现场验证。前段慢启动会影响短测；小文件批量业务还要看每秒完成数。1 MB/s约等于8 Mbps。

> 2026-06-27 同落地对照：VLESS+WS经TCP443反代，50MB下载约9.0–9.4 MB/s、8次延迟范围199–215ms；Hysteria2经UDP443直达，约15.9–18.5 MB/s、197–239ms。路径与协议同时改变，不能推成协议普遍倍速结论。另次设 up=80 Mbps、down=120 Mbps，在下载约16 MB/s、上传约9 MB/s且低丢包的链路中未见吞吐改善；只能说明该测试条件下收益未显现。带宽单位按版本语法核对，避免 bit/byte 混淆。

协商检查应结合客户端与服务端版本、up/down、服务端限制/忽略开关、可用日志及对照吞吐。独立服务端见 [Hysteria2](hysteria2.md)，面板内节点见 [3x-ui](3x-ui.md)；线路丢包、带宽和服务器质量测量由 `vps-maintenance` skill 负责。

## <a id="private-relay"></a>受限网络下的私网中转

### <a id="relay-architecture"></a>出站链路与本机规则分流

当本机到订阅节点入口不可达，而已有私网可达的中转主机能到该入口时，可只改变这批节点的连接路径：

```text
应用 → 本机 Mihomo → 本机规则/节点选择
                    ├→ 直连或其他节点
                    └→ <私网IP>:<监听端口> → 四层中转 → <上游IP>:<目标端口>
```

本机继续承担域名规则、分类组与备选节点，应用保留原本的本地代理入口。中转机只搬运被选中节点的流量；相较迁走整机默认出口或把分流放到远端，这种做法作用范围较小，但新增一跳的时延、带宽成本、可用性和维护责任。先证明故障属于本机到入口的路径差异，方法见[分层连接诊断](#layered-diagnosis)。

### <a id="relay-listeners"></a>私网监听与端口分配

转发入口仅监听 `<私网IP>`，并限制到预期私网客户端。无额外鉴权的四层转发若监听公网，会把上游入口及流量消耗面向非预期来源开放；私网地址未就绪时应等待或启动失败，不退回通配地址。

先查中转机实际临时端口池、预留端口与已有占用：

```bash
sysctl net.ipv4.ip_local_port_range net.ipv4.ip_local_reserved_ports
ss -lntup
```

Linux 默认临时端口范围32768–60999。监听段优先选在实际临时池外且未被占用的非特权范围；历史中转部署曾因池内出站 socket 先占用目标监听端口而 bind 失败。端口已成功监听后，不能反过来说临时分配必定抢占它。若必须使用池内监听段，需按维护授权评估并保留已有 `ip_local_reserved_ports`，而不是覆盖原保留集。

> 官方依据：[Linux v6.12 IP sysctl](https://www.kernel.org/doc/html/v6.12/networking/ip-sysctl.html)。预留配置排除自动分配，不改变显式 bind；实际内核命名空间、端口池和冲突以现场为准。

### <a id="relay-port-mapping"></a>四层端口段映射

监听段和目标段按相同偏移对应，例如 `监听起点+i → 上游起点+i`。GOST 可作为实现载体：

```bash
gost -L 'tcp://<私网IP>:<监听起点>-<监听终点>/<上游IP>:<上游起点>-<上游终点>'
```

使用等长端口段并验证边界节点；不同入口、特殊节点或无对应端口的节点分开处理。TCP 转发不自动承载 UDP/QUIC，需要时为相应协议另设计和验证。四层中转不终止上层 TLS，连接地址改变后仍保留原证书验证名/SNI、WS Host/path、鉴权等字段。原节点若省略验证名、由 server 域名推导，改成私网 IP 前须按协议显式补回原验证名，不能默认关闭证书校验。

> [GOST 端口段映射](https://gost.run/en/tutorials/port-forwarding/)于2026-11-14核对，原部署使用v3.3.2；官方说明按序一一映射，目标段多余部分会被忽略。这里使用等长映射明确意图，实际版本先核对语法与TCP/UDP支持。订阅字段变换和更新由 [clashctl 中转订阅](clashctl.md#relay-profile)完整说明。

### <a id="relay-validation"></a>中转链路验证与回退

依次确认私网地址可达、所选监听段完整启动、中转机到上游入口可达，再用完整代理协议和新业务连接验证。查看本机 `/connections` 的 rule/chains，确认只有预期节点流量走中转，直连和备选节点仍符合本机策略。仅 TCP connect 成功不能代替上层验证。

服务管理需要等待私网地址就绪、记录监听与目标映射、配置有界重试并保留日志；按实际启动器实现，不依赖某个特定组网服务名。中转异常或原入口恢复时，通过保留的原始/备选 profile 回退；派生、刷新防覆盖与切换步骤集中在 [clashctl](clashctl.md#relay-profile)。

<a id="6-运行态控制rest-api-与-web-面板"></a>
## <a id="runtime"></a>运行态控制

### <a id="rest-api"></a>REST API

控制面查询和改变运行态；与托管程序维护的磁盘输入分别核对：

```yaml
external-controller: 127.0.0.1:9090
secret: '<控制器密钥>'
```

出回环访问时限定地址、访问控制并设置 secret。常规 HTTP 使用 `Authorization: Bearer <secret>`；浏览器 WebSocket 在该实现中支持 `?token=`，仅因 WebSocket 认证方式差异使用，避免将令牌落进 URL 日志。无认证请求返回401只说明有鉴权端点，不能单独证明内核身份或健康。

从受保护的实际配置以可靠 YAML 解析器读取密钥，避免输出、命令跟踪或打印完整环境。例如已安装 yq 时：

```bash
sec=$(yq -r '.secret // ""' '<实际配置文件>') || exit
curl -fsS -H "Authorization: Bearer $sec" http://127.0.0.1:9090/version
```

| 读取端点 | 可获得的证据 |
|---|---|
| `/`、`/version` | 内核响应与版本；须结合正确凭据和进程归属。 |
| `/configs` | 当前通用运行设置，非完整源文件或文件路径。 |
| `/proxies`、`/rules` | 组的 now/all、候选、规则表。 |
| `/connections` | 已有连接的目标、开始时间、链路、规则和网络。 |
| `/logs?format=structured&level=info`、`/traffic` | 流式日志/流量；脚本给出有限 max-time。 |

组名和目标 URL 必须正确编码。例如在已建立认证头 `$h` 的 PowerShell 中：

```powershell
$group = [uri]::EscapeDataString('<组名>')
$body = @{name='<候选节点名>'} | ConvertTo-Json -Compress
# 已获准切换后：
Invoke-RestMethod -Method Put -Uri "http://127.0.0.1:9090/proxies/$group" -Headers $h -ContentType 'application/json' -Body $body
$target = [uri]::EscapeDataString('https://www.gstatic.com/generate_204')
Invoke-RestMethod -Uri "http://127.0.0.1:9090/proxies/$group/delay?url=$target&timeout=10000" -Headers $h
```

测具体节点时将 path 中对象换成该节点，而不先切主选择器；失败看 HTTP 状态、错误内容和超时，不以延迟值0作为统一死亡标准。吞吐验证见[吞吐验证](#throughput)。

> 鉴权依据：[authentication](https://github.com/MetaCubeX/mihomo/blob/24b6de71fc1c4ea282dcbc7b65a8bcbcc0c75e6c/hub/route/server.go#L336-L371)。控制端点与配置来源见[配置目录](#config-directory)。

### <a id="web-ui"></a>Web 面板

Mihomo 可把 `external-ui` 静态目录挂到控制器的 `/ui/`，裸 `/ui` 重定向到 `/ui/`；目录相对内核 home 或使用绝对路径。`external-ui-url` 可在目录为空时下载所选面板产物，手动更新入口为 `POST /upgrade/ui`；下载与升级是写操作，需维护授权和可信来源。

```yaml
external-ui: ui
external-ui-url: '<已核对的面板发行压缩包URL>'
```

面板需要后端 URL 与 secret。API 访问面和静态文件是否同源、是否经反代，须按部署填写；secret 不写入公开静态文件。对明确支持下列对象、且在启动前加载 config.js 的 MetaCubeXD 构建，可设置默认同源后端：

```js
window.__METACUBEXD_CONFIG__ = { defaultBackendURL: window.location.origin }
```

这只适合页面源地址就是控制器 API 的部署；运行时 `defaultBackendURL` 配置优先时，上面对象不会覆盖它。具有服务端动态 config.js 路由的部署按其环境配置入口维护；其他版本按其文档核对。

> 内核静态UI：[路由挂载](https://github.com/MetaCubeX/mihomo/blob/24b6de71fc1c4ea282dcbc7b65a8bcbcc0c75e6c/hub/route/server.go#L105-L250)。面板依据：[默认后端优先级](https://github.com/MetaCubeX/metacubexd/blob/9978e3286f95393ed514b673f0cdcd22e982238a/packages/ui/composables/useConnect.ts#L21-L34)、[config.js 加载](https://github.com/MetaCubeX/metacubexd/blob/9978e3286f95393ed514b673f0cdcd22e982238a/packages/ui/nuxt.config.ts#L210-L224)、[服务端配置输出](https://github.com/MetaCubeX/metacubexd/blob/9978e3286f95393ed514b673f0cdcd22e982238a/apps/server/routes/config.js.ts#L1-L25)。

### <a id="config-reload"></a>配置热重载

`PUT /configs` 从绝对 path 或 payload 解析完整配置后应用；显式路径受[安全路径](#config-directory)检查，省略 path 时使用内核原配置。`PATCH /configs` 以当前运行态为基底修改提交的字段；`PUT /proxies/<组>` 是另一个节点选择操作。

```bash
# 已获准修改运行模式时：
curl -fsS -H "Authorization: Bearer $sec" -H 'Content-Type: application/json' \
  -X PATCH http://127.0.0.1:9090/configs -d '{"mode":"global"}'
```

完整重载会重新应用规则、节点、DNS及监听等配置，影响取决于变更与实现，不能承诺保留或必断所有既有连接。PATCH 不写回持久输入，之后全量重载可覆盖它；持久文件按裸内核、GUI 或 [clashctl 配置生成](clashctl.md#config-lifecycle)的归属同步维护。

> 依据：[PATCH/PUT 实现](https://github.com/MetaCubeX/mihomo/blob/24b6de71fc1c4ea282dcbc7b65a8bcbcc0c75e6c/hub/route/configs.go#L320-L442)、[配置应用](https://github.com/MetaCubeX/mihomo/blob/24b6de71fc1c4ea282dcbc7b65a8bcbcc0c75e6c/hub/executor/executor.go#L83-L125)。

### <a id="tun-recreate"></a>TUN 重建

TUN PATCH 保留未提交的指针字段，但该版本 `tun.enable` 是非指针 bool，提交 tun 对象时必须明确 enable，避免缺省值把 TUN 关掉：

```bash
curl -fsS -H "Authorization: Bearer $sec" -H 'Content-Type: application/json' \
  -X PATCH http://127.0.0.1:9090/configs \
  -d '{"tun":{"enable":true,"strict-route":false}}'
```

执行前确认内核进程有建网卡权限，调用者拥有 API 凭据不会给内核增加系统权限。Windows 上变更 TUN 参数可能触发 close/recreate；历史部署出现适配器删除竞态时，采用关闭→等设备与路由清理→带目标参数开启的分步维护，等待有界且以实际状态为准，不能把原约12秒样例当固定平台保证。

每步查 `/configs` 的 tun.enable、网卡和路由。零值字段可能因 omitempty 缺省，缺少 strict-route 字段不直接表示修改失败。完成后同步受支持的持久输入并 `mihomo -t` 校验，避免额外无关重载。建/删 TUN 本身就可能影响流量，不宣称零中断。Windows 提权上下文用实际令牌/权限核查，SSH 管理员账户也不代替检查。

> 依据：[TUN 请求字段](https://github.com/MetaCubeX/mihomo/blob/24b6de71fc1c4ea282dcbc7b65a8bcbcc0c75e6c/hub/route/configs.go#L62-L86)、[PATCH 重建调用](https://github.com/MetaCubeX/mihomo/blob/24b6de71fc1c4ea282dcbc7b65a8bcbcc0c75e6c/hub/route/configs.go#L355-L375)。

<a id="62-tun-模式下别用-post-restartwindows-会静默丢-tun"></a>
### <a id="process-restart"></a>进程重启

`POST /restart` 是改变进程生命周期的操作。所核对 Windows 实现先 Shutdown，再以原参数 spawn 子进程，随后退出父进程；Unix 用 exec 替换进程。源码没有刻意降权步骤，重启失败不能直接归因 UAC。

历史 Windows+TUN 部署在该路径出现过控制器消失或 TUN 未重建。可疑机制包括异步删除中的 Wintun 设备与立即创建冲突，以及新进程绑定时老进程仍占控制器端口。相应 `tunNew` 实现对小于1秒的快失败直接返回，对较慢失败才有限重试；这支持竞态的解释路径，但不证明每个错误都有同一根因。

需要修改控制器、secret、UI 等启动期配置时，先核对目标版本支持哪些重载。维护时优先通过已有服务管理者 stop→确认旧进程/网卡/监听释放→按原参数 start，并保留恢复入口；不要在诊断中反复自重启或杀裸进程与 supervisor 竞争。Linux 托管控制见 [clashctl](clashctl.md#service-control)，Windows 提权与结果回收由 `software` skill 负责。

> 依据：[重启实现](https://github.com/MetaCubeX/mihomo/blob/24b6de71fc1c4ea282dcbc7b65a8bcbcc0c75e6c/hub/route/restart.go#L46-L69)、[Windows TUN 重试](https://github.com/MetaCubeX/mihomo/blob/24b6de71fc1c4ea282dcbc7b65a8bcbcc0c75e6c/listener/sing_tun/server_windows.go#L12-L26)。旧 PR709 涉及 shutdown 顺序，不能据此宣布已修复 Windows PnP 竞态；具体故障仍看该版本日志与设备状态。

## <a id="connection-diagnosis"></a>连接诊断

### <a id="layered-diagnosis"></a>分层连接诊断

显式 HTTP 代理返回 `HTTP/1.1 200 Connection established` 后仍可能 TLS EOF、reset 或 timeout。Mihomo v1.19.27 的 CONNECT 路径先回复接受隧道，再进入规则选择与真正的目标拨号；这个200只证明本地代理接受请求。普通明文 HTTP 代理可在出站失败后返回502，SOCKS 不使用该 HTTP 状态行。

> 依据：[CONNECT 响应](https://github.com/MetaCubeX/mihomo/blob/5184081ac327394d9e15fa5d5f9f4a61e723fd94/listener/http/proxy.go#L68-L75)、[后续 outbound 拨号](https://github.com/MetaCubeX/mihomo/blob/5184081ac327394d9e15fa5d5f9f4a61e723fd94/tunnel/tunnel.go#L552-L576)。

按实际数据路径从近到远收集证据：

1. 查当前模式、逐层 now，以及实际连接的 start/chains/rule；用新连接排除旧 socket 仍使用旧节点的干扰。
2. 对具体节点分别测普通目标与业务目标 delay，不先改全局主选择器；单目标失败还可能是业务端策略。
3. 经 DoH 取节点真 IP；清除显式代理变量，`--noproxy '*'` 与 `--resolve` 保留 Host/SNI 验入口，并核对 TUN 是否仍接管。

   ```bash
   env -u http_proxy -u https_proxy -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
     curl --noproxy '*' -v --connect-timeout 5 \
       --resolve '<节点域名>:443:<真实IP>' 'https://<节点域名>/<WS路径>'
   ```

4. 用已知监听的多端口及健康控制目标对照；TCP MTR（如 `mtr -T -P 443 <真实IP>`）不回 hop 不等于已定位丢包设备。
5. 使用真正独立的外部视角。远端也运行 TUN 时，即使 `--resolve` 钉真 IP，仍可能经该内核；核对 `ip route get`、来源和规则后再当旁路证据。

TCP/TLS 成功并收到403通常只证明该前端在线，普通 GET 未带 Upgrade 时被拒不能验证完整 VLESS/WS 鉴权。Check-Host 历史 API 可发 `check-tcp?host=<真实IP>%3A443&max_nodes=10`，用返回 request_id 查询 `check-result/<request_id>`；调用前按 [官方 API 说明](https://check-host.net/about/api)核对接口与返回结构。

| 对照结果 | 下一步 |
|---|---|
| 本地与独立多地均 TCP 失败 | 查监听、防火墙、服务和全局路径。 |
| 本地多端口失败而外部 TCP/TLS 正常 | 查源网络相关出程、回程、ACL、抗DDoS或互联路径，服务端抓包可进一步定位。 |
| TCP/TLS 正常，完整代理协议失败 | 查证书、SNI、Host、path、Upgrade 与鉴权字段。 |
| 旧业务连接可用，新连接失败 | 查旧连接的建立时间和原 chains，验证新选节点。 |

已有长连接可跨切组继续工作。另开短连接优先于打断业务；删除 `/connections` 或重启应用也属于中断操作，需相应授权。

### <a id="single-domain"></a>单域名故障

部分域名失败而其他域名正常时，先查是否命中不同规则或仍持有失效 Selector。按该域名的实际连接查 rule/chains，再沿 now/all 找到真实节点；配置没有改动也可能因为节点路径失效而出现新故障。

比较具体节点对业务目标与控制目标的探测；用 DoH 真 IP、正确 SNI 的入口测试，必要时查看完整协议响应。SSH banner 成功只覆盖该端口和链路，IP 请求也可能受 IP 规则或嗅探影响，不能自动当作绕过域名分流。

若确认当前候选失效而其他候选正常，可在获得切换授权后修改对应 Selector。注意分类组引用主组的联动范围、缓存选择与旧连接；核心机制见[规则匹配](#rule-matching)，更一般证据链见[分层连接诊断](#layered-diagnosis)。

## <a id="field-observations"></a>现场观察

以下保留带日期、路径和对照条件的代理技术观测；机器身份、真实地址、费用、运营时间线由个人记录维护。服务器质量测量由 `vps-maintenance` skill 负责。封锁主体与协议触发原因未由这些小样本唯一确定。

### <a id="single-ip-block"></a>单 IP 屏蔽

2026-06-08 起的一次 Hysteria2 节点观测：已测境内出口到同一 IP 的22/443/ICMP超时，同 /24 控制地址正常，境外多地可达且服务端健康。2026-06-27 更换该实例 IP、协议保持不变后，在短观察窗口内恢复。结果支持具体 IP/路径差异，不能证明 QUIC 大流量、域名暴露或某个封锁系统是唯一原因。

### <a id="long-lived-node-block"></a>长期节点屏蔽

2026-06-25 的另一次观测中，长期运行的 VLESS+WS+TLS 节点也不可达。它说明所见故障不限于该样本中的 QUIC 节点；固定域名、IP、流量特征或机房路径仍是假设，未由此实验区分。

### <a id="source-network-failure"></a>源网络相关不可达

2026-07-13 一次切组后，新 HTTP 请求先收到本地 CONNECT 200，随后 TLS EOF，同落地 TCP/WS 与 QUIC 都失败；已有流式业务仍能工作。DoH 真 IP 的22/80/443在当前网络超时，健康控制节点正常；MTR 到失败目标无 hop，而控制路径有响应。

独立10地 TCP443均成功，HTTPS均完成 TLS/HTTP 并返回普通 GET 的403，证明当时前端没有全局失效，但未单独验证完整代理鉴权。连接表显示旧流式 socket 在切组前通过另一节点建立，chains未变。原报告地址可能含现场目标信息，这里保留匿名测试条件与结果。

归因到源网络相关路径或策略即可。进一步区分 SYN 未到达与服务端/防护按源丢弃，需要在服务端同步抓包，核对 SYN 到达、SYN-ACK 发出与回程；没有这些证据不指定中间丢弃设备。

### <a id="field-mitigation"></a>对照实验与缓解

可在获准窗口暂停监听，比较如24–72小时后的路径变化，但恢复也可能伴随同期网络或策略变化，不能独立证明代理流量触发。SSH 可借已验证健康的 ProxyJump；换地址/域名或调整协议是有成本的缓解选择，均需重新验收。原单 IP 案例只支持该次换 IP 的短期结果；私网中转方案见[受限网络下的私网中转](#private-relay)。

## <a id="source-build"></a>源码构建

先确认目标 tag/commit 包含完整 Go 模块源码（`module github.com/metacubex/mihomo`、构建入口和依赖），再切到该版本构建。原记录使用 Meta/Alpha 内核分支；默认分支名称或仓库外观不代替内容核对。Git 获取和跟踪分支操作交 `git` skill；单 remote、完整 refspec 时的自动跟踪行为不推广到其他仓库布局。

以下以所核对 v1.19.24 构建矩阵的 Windows amd64 无等级后缀目标为例，它使用 GOAMD64=v3 和 with_gvisor。确保 CPU 支持，使用独立输出名避免覆盖运行中的 exe：

```powershell
git checkout v1.19.24
git describe --tags --exact-match
$env:GOOS='windows'; $env:GOARCH='amd64'; $env:GOAMD64='v3'
go build -v -tags 'with_gvisor' -trimpath `
  -ldflags "-X 'github.com/metacubex/mihomo/constant.Version=v1.19.24' -X 'github.com/metacubex/mihomo/constant.BuildTime=$(Get-Date -Format r)' -w -s -buildid=" `
  -o mihomo-windows-amd64.exe .
.\mihomo-windows-amd64.exe -v
```

`go build` 产生可执行文件，release 压缩包由 workflow 另行打包；版本输出与 `Use tags: with_gvisor` 用来核对构建结果，不证明 TUN 与网络已验收。

> 依据：[Windows 目标矩阵](https://github.com/MetaCubeX/mihomo/blob/a84724665eb7f989809abe463c05f5723bd24975/.github/workflows/build.yml#L64-L71)、[编译与打包](https://github.com/MetaCubeX/mihomo/blob/a84724665eb7f989809abe463c05f5723bd24975/.github/workflows/build.yml#L242-L255)。
