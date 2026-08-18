# OpenWrt 无线接入网关

OpenWrt 无线接入网关把外部 Wi-Fi 当作上游网络，在路由器上完成连接、认证、地址获取和流量转发，再从有线 LAN 输出网络。下游可以直接接电脑，也可以接一台 AP（access point，无线接入点）提供本地 Wi-Fi。这个结构不同于消费级“无线放大器”：它把上游连接、本地网络、认证和链路观测拆成可独立配置和验证的部分。

本文按实际搭建顺序展开：理解系统、接线配置、通过认证、理解无线链路、测量排障、评估定向 CPE，最后部署监控面板并回看现场案例。OpenWrt 的安装、升级、SSH 和专属配置对象见 [OpenWrt 设备管理](openwrt.md)。

## <a id="architecture"></a>无线接入网关的组成

无线接入网关由上游 Wi-Fi、OpenWrt 网关、有线 LAN 和下游终端组成。下游 AP 只负责本地无线覆盖时，应工作在 AP 模式，不再承担第二层 DHCP 和 NAT。

```mermaid
flowchart LR
    upstream[外部 Wi-Fi AP]
    gateway[OpenWrt 无线接入网关]
    downstream[下游 AP / 交换机]
    clients[本地终端]

    upstream -->|Wi-Fi 客户端连接| gateway
    gateway -->|路由/NAT| downstream
    downstream --> clients
```

### 系统职责与数据路径

四类对象的职责如下：

| 对象 | 主要职责 | 不应承担的职责 |
|---|---|---|
| 外部 AP | 提供上游 Wi-Fi 和网络地址 | 不需要为本地网部署配套设备 |
| OpenWrt 网关 | 作为 Wi-Fi 客户端连接上游，完成认证、路由、NAT 和链路观测 | 默认不需要广播本地 Wi-Fi |
| 下游 AP | 把网关的有线 LAN 转成室内 Wi-Fi，并扩展网口 | AP 模式下不再运行独立 DHCP/NAT |
| 本地终端 | 从 OpenWrt LAN 获取地址并访问上游 | 不直接保存每个上游网络的配置 |

OpenWrt 中把“作为 Wi-Fi 客户端连接上游”称为 station，把这条 Wi-Fi 承载的 WAN 接口称为 WWAN；详细对象关系见 [网络配置接口](openwrt.md#network-surfaces)。上游与本地覆盖使用不同无线电或不同设备时，不会因同一无线电轮流收发而直接争用信道时间。

下游 AP 可以放在适合室内覆盖的位置，OpenWrt 网关或定向 CPE（Customer Premises Equipment，带定向天线、用于连接远端 AP 的用户侧无线终端）则可以放在上游信号最好的位置，两者用网线连接。

### 路由、WDS 与 relayd

普通 Wi-Fi 客户端帧只能稳定表达客户端、AP 和流量目的地，不能自动把网线后方多个终端的 MAC 透明送给上游。OpenWrt 官方的[无线客户端配置](https://openwrt.org/docs/guide-user/network/wifi/connect_client_wifi?rev=1705097879)因此默认建立独立子网并路由转发。

WDS/四地址桥接是在无线帧中保留下游终端身份的透明桥接方式，需要两端兼容；`relayd` 则用代理 ARP 等三层机制模拟同一网段。只有确实需要上游 DHCP、广播发现或原始客户端 MAC 时，才考虑这两类方案。

| 模式 | 上游看到的身份 | 下游地址 | 上游要求 | 适用边界 |
|---|---|---|---|---|
| 路由 + NAT | OpenWrt 的 WWAN 地址和无线 MAC | OpenWrt LAN 子网 | 标准 AP | 公共网络、企业网络、Wi-Fi 转网线 |
| WDS / 四地址桥接 | 下游终端原始 MAC | 上游网段 | AP 与 station 双方兼容四地址 | 自己管理两端设备的桥接链路 |
| `relayd` | 由代理 ARP 等机制模拟 | 通常为上游网段 | 不要求 WDS | 必须保留上游地址、且能接受复杂排障 |

> Linux wireless 文档要求 AP 和客户端双方都启用四地址帧才能透明桥接；厂商的 proprietary bridge 模式也可能无法跨品牌工作。OpenWrt 的 [WDS](https://openwrt.org/docs/guide-user/network/wifi/wifiextenders/wds?rev=1746783203)和 [`relayd`](https://openwrt.org/docs/guide-user/network/wifi/relay_configuration?rev=1752850857)文档分别说明了这两条路径。

### 双重 NAT 与 AP 模式

若 OpenWrt 已在 WWAN 与 LAN 之间做 NAT，下游路由器继续以 WAN 路由模式接入，就会形成双重 NAT。普通网页访问通常仍能工作，但端口映射、P2P、部分游戏和跨网段设备发现会变复杂。

下游设备进入 AP 模式后的目标状态是：

- DHCP 由 OpenWrt 提供；
- 所有终端位于 OpenWrt LAN 子网；
- 下游设备只做 Wi-Fi AP 和交换机；
- OpenWrt 管理地址可从下游 Wi-Fi 直接访问；
- 网线接法按下游设备的 AP 模式说明决定，不能假设一定使用 WAN 或 LAN 口。

切换后应分别检查终端地址、默认网关、DNS、OpenWrt 管理页和公网访问。只看到下游 SSID 不代表 AP 模式已经正确完成。

## <a id="configuration"></a>搭建无线接入网关

### 准备管理路径与配置备份

配置无线接入网关时，始终保留一条不会随上游无线切换而消失的管理路径。最稳妥的是电脑直接连接 OpenWrt LAN，确认管理地址和 SSH 可用，再保存配置备份。

开始前还要确认：

- LAN 与上游网络不使用同一子网；
- 当前配置可以恢复；
- 电脑不会因默认路由切换而失去远程管理；
- 无线切换期间，下游短暂断网是预期现象。

### 配置上游 Wi-Fi 与网络出口

OpenWrt 需要同时完成三件事：让无线电作为 Wi-Fi 客户端连接上游；让 WWAN 从上游取得地址；让 LAN 流量通过防火墙转发并做 NAT（把多个下游设备的地址转换成一个上游身份）。

| 配置层 | 必要关系 |
|---|---|
| 无线 | `wifi-iface` 使用 `mode='sta'`，绑定 `network='wwan'` |
| 网络 | `network.wwan` 使用 DHCP 或上游要求的协议 |
| 防火墙 | `wwan` 属于启用地址伪装（masquerading，即 NAT）的 WAN 区，允许 LAN 转发到 WAN |

这些 OpenWrt 专属对象和最小 UCI 关系见 [LAN、WAN、WWAN 与防火墙区域](openwrt.md#network-surfaces)。完成配置后，用下面一段命令确认无线、WWAN 和路由同时存在：

```sh
ubus call network.wireless status
ubus call network.interface.wwan status
ip route
```

WWAN 取得地址只证明无线连接和 DHCP（自动分配网络地址）成功；Captive Portal 或企业认证还需要按[通过上游认证](#authentication)继续验证。

### 连接下游 AP

OpenWrt LAN 应使用与上游不同的子网，并运行 DHCP。网线连接下游 AP 后，终端应直接从 OpenWrt 获取地址。若终端仍拿到下游设备自己的网段，说明下游仍在路由模式。

验证顺序是：

1. 电脑直接连接 OpenWrt LAN，确认 WWAN、NAT 和 Portal/企业认证。
2. 连接下游设备，但暂不改变 OpenWrt。
3. 将下游设备切为 AP 模式。
4. 从下游 Wi-Fi 检查地址、网关、DNS、OpenWrt 管理页和公网。
5. 重启两台设备，确认上游自动关联和下游 AP 自动恢复。

### 切换、回退与重启验收

测试新的 SSID、频段、企业认证或 BSSID 时，不要立刻覆盖已知可用配置。可以先保留原无线配置条目（profile），临时启用新条目，验证成功后再提交；失败时 `uci revert wireless` 或恢复备份。

每次最终配置都应经过：

- `wifi reload` 后自动重连；
- 完整重启后自动重连；
- 下游终端重新取得地址；
- 认证状态、DNS 和公网访问；
- 至少一段与业务时长相称的连续丢包和延迟测试。

## <a id="authentication"></a>通过上游认证

外部 Wi-Fi 的链路层关联、网络层地址和上层认证是三个阶段。排障时应先判断失败发生在哪一层，不能把“拿不到 DHCP”误判成 Portal 问题。

### Captive Portal

Captive Portal 是“连上 Wi-Fi 后，再由网页完成的强制认证门户”。开放热点通常先完成无线连接和 DHCP，再通过 HTTP 重定向进入 Portal。路由 + NAT 后，上游通常只看到 OpenWrt 的 WWAN 地址和无线 MAC，因此一次认证可能供多个下游终端共享。

这个行为取决于 Portal 是否绑定 MAC、IP、Cookie、账号、设备数或其他特征，必须现场验证。稳妥流程是：

1. 从下游终端访问一个纯 HTTP 页面；
2. 完成 Portal 认证；
3. 用另一台终端验证是否共享；
4. 重连和会话过期后再次验证。

直接打开某个已知 Portal IP 可能进入错误的认证系统，或因系统无法反查当前 MAC 而失败。应优先让目标网络自己的 HTTP 重定向给出入口。

### WPA2-Enterprise 与服务器证书

WPA2-Enterprise 是基于 802.1X（端口接入控制框架）的企业 Wi-Fi 认证，由账号、证书和 EAP（Extensible Authentication Protocol，可扩展认证协议）共同完成。PEAP 是把账号认证放进 TLS（Transport Layer Security，加密通道）的 EAP 方法，MSCHAPv2 则常作为隧道内的用户名/密码认证。

OpenWrt 需要包含这些方法的完整 wpad 变体；包能力和 UCI 字段见 [无线配置与 wpad](openwrt.md#network-surfaces)。Gateway 侧重点是确认三个结果：EAP 成功、WWAN 取得地址、服务器证书被正确验证。

服务器证书校验不能省略。OpenWrt 25.12.5 的 station 脚本会传递 `ca_cert`、`domain_match` 和 `domain_suffix_match`；上游 [wpa_supplicant 配置](https://w1.fi/cgit/hostap/plain/wpa_supplicant/wpa_supplicant.conf?id=ca266cc24d8705eb1a2a0857ad326e48b1408b20)明确指出，不设置 CA 时服务器证书不会被验证。优先使用受信 CA 加服务器域名限制；无法部署私有 CA 时，可以按该版本支持的格式固定服务器证书：

```text
ca_cert="hash://server/sha256/<certificate-sha256>"
```

证书 pin 会在服务器换证后失效，因此恢复资料中要记录 pin 的来源和更新方法。不要用关闭验证来换取短期连通。

### 凭据保存与备用上游

企业账号、热点密码和证书配置最终会存在 root 可读的 OpenWrt 配置中。写入时避免让凭据进入 shell 历史、命令参数或调试日志；使用受控输入，并确认备份文件的访问权限。

可以保存一条禁用的备用上游配置，主上游失败时手动切换。禁用配置条目只表示内容已保存，**不是自动故障切换**；自动切换还需要优先级、健康检查、认证状态和回切条件。

## <a id="radio-metrics"></a>理解无线链路

无线信号不能只看一个 RSSI（Received Signal Strength Indicator，接收信号强度指标）数字。OpenWrt 25.12.5 锁定的 [iwinfo `f5dd57a`](https://github.com/openwrt/iwinfo/blob/f5dd57a84cc31a403a1383dd14944fa2e2b5824a/iwinfo_cli.c)分别报告 signal、noise、MCS、NSS 和信道宽度，并按 `signal - noise` 显示 SNR（Signal-to-Noise Ratio，信噪比）。

### RSSI、噪声与信噪比

| 指标 | 含义 | 使用方式 |
|---|---|---|
| signal / RSSI | 接收信号强度，单位 dBm（相对 1 mW 的对数功率单位） | 越接近 0 通常越强，但不能单独判断双向质量 |
| noise | 接收机看到的噪声底，同样使用 dBm | 越低代表背景噪声越弱 |
| SNR | `signal - noise`，单位 dB | 决定可用调制余量，需和重传、MCS 一起看 |

例如某次现场状态为 `signal=-79 dBm`、`noise=-91 dBm`，按 iwinfo 口径 SNR 约为 12 dB；同时上行降到较低 MCS 并出现大量重传。这个例子说明弱信噪比与降速同时发生，不构成所有设备通用的阈值表。

### 信道宽度、空间流与 MCS

- **信道宽度**表示一次使用多少频谱，例如 20、40 或 80 MHz。更宽可以提高容量，也更容易受到同频资源和监管范围限制。
- **NSS（空间流数）**表示并行发送的独立数据流数量。NSS 1 与 NSS 2 的可用容量不同，但能否使用多流取决于双方天线、信道和链路条件。
- **MCS（调制编码方案索引）**表示每个符号承载的数据量和纠错强度。较低 MCS 更稳健、速率更低；较高 MCS 需要更好的信噪比。

现场曾观察到 `40 MHz / NSS 1 / VHT-MCS 0–2`，驱动报告的 PHY 上行在十几到数十 Mbps 间变化。这个组合描述的是当时协商档位，不是可直接套用到其他标准、GI（guard interval，保护间隔）或设备的固定换算表。

### PHY 速率、实际吞吐与重传

PHY（physical layer，物理层）速率是无线设备当前使用的底层传输档位，`iw` 会把它显示为 `tx bitrate` / `rx bitrate`。Linux `iwconfig` 文档指出，应用可用速度会因介质共享和协议开销而更低。驱动的 `expected throughput` 也是估计值，不是测速结果。

重传指标解释链路为什么“协商速率不低，实际网速却很差”：

- `tx retries`：发送需要重试的次数；
- `tx failed`：最终未被确认的发送；
- packet loss：在更上层测到的丢包；
- latency/jitter：排队、退避和重传造成的时延与波动。

累计重试计数必须比较一段时间内的增量，不能只看开机以来的绝对值。

### Legacy、HT、VHT 与 HE

OpenWrt/hostapd 使用以下名称描述不同代际能力：

| 名称 | 对应标准 | 常见能力范围 |
|---|---|---|
| legacy | 802.11a/b/g 等 pre-HT 速率 | 不使用 HT/VHT/HE 的旧式速率与能力表示 |
| HT | 802.11n | 20/40 MHz、MCS 与多空间流 |
| VHT | 802.11ac | 更宽信道和更高阶调制 |
| HE | 802.11ax | 更高效率的多用户和调度能力 |

legacy 不是 HT/VHT/HE 同一命名体系里的新一代标准，而是驱动对“不带这些高吞吐能力”的旧模式的统称。日志写 `VHT -> legacy` 时，只能确定客户端当时不再看到 VHT/HT 能力；它不自动证明 AP永久降级，也可能来自瞬时 beacon 不一致、信道切换或驱动解析结果。

模式名称本身不是质量分。若同一 BSSID 的能力广播在 VHT、HT 或 legacy 间异常变化，客户端驱动可能重建关联；是否断开取决于 AP、驱动和实现。

### WNM 漫游通知

WNM（Wireless Network Management，无线网络管理）允许 AP 或网络控制器（controller，集中管理多台 AP 的系统）向客户端发送管理建议。BSS Transition Management 是其中用于引导客户端选择其他 AP 的机制；`Disassociation Imminent` 则表示当前 AP预告即将断开。

完整 wpa_supplicant 构建会处理这类通知。上游 [WNM 实现](https://w1.fi/cgit/hostap/plain/wpa_supplicant/wnm_sta.c?id=ca266cc24d8705eb1a2a0857ad326e48b1408b20)记录了相应事件。客户端可以选择候选 AP或拒绝部分请求，但不能阻止上游发送通知。

### PMKSA、OKC 与 802.11r

企业网络每次漫游都重新完成完整 EAP 会增加中断时间。下面几种机制尝试复用或提前准备认证结果：

| 机制 | 人话解释 | 依赖 |
|---|---|---|
| PMKSA caching | 记住已经和某个 AP协商出的主密钥 | 客户端与 AP都保留缓存 |
| RSN preauthentication | 还没切换 AP前，先完成下一台 AP的 802.1X/EAP | 同一 ESS、网络和 RADIUS 认证服务器支持 |
| OKC | 把同一组网络里的其他 AP也视为可复用密钥的候选 | 客户端与 AP/网络控制器兼容 |
| 802.11r FT | 使用专门的 Fast Transition 流程快速换 AP | AP/网络控制器广播并配置 FT |

PMKSA 是 Pairwise Master Key Security Association（成对主密钥安全关联）；RSN 是 Robust Security Network（WPA2 使用的安全网络框架）；OKC 是 Opportunistic Key Caching（机会式密钥缓存）；FT 是 Fast Transition（快速切换）。这些机制只可能缩短兼容网络中的重认证，不能阻止 WNM 通知或 AP主动断开。

OpenWrt 25.12.5 的 station 配置接受 `ieee80211r` 并生成 FT key management，但启用前应确认目标网络广播 FT。上游 wpa_supplicant 还支持 `proactive_key_caching=1`，但标准 station UCI 映射中没有同名字段；不要假设未知 UCI option 会自动生效。

### BSSID 锁定与 HT20

BSSID 是一台具体 AP无线接口的 MAC 地址。同一 SSID（网络名称）可能由多台 BSSID共同提供。固定 BSSID 可以阻止客户端自动换到同名 AP，但目标 AP故障时也失去自动回退；wpa_supplicant 对固定 BSSID 的漫游请求可能直接拒绝。

HT20 表示把 802.11n 高吞吐模式限制在 20 MHz 信道。它可以作为排查宽信道干扰或 VHT/HT 能力变化的 A/B 变量，但会降低 PHY 上限。本次案例没有完成 HT20 长测，因此不能把它写成通用修复。

## <a id="measurement"></a>测量与排查链路

### 建立可比较的测试条件

测量目标是沿实际数据路径逐层缩小瓶颈范围，而不是先假定网络属于校园、企业或公共热点。先区分无线第一跳、同一管理域内的服务、公共互联网和测速服务器，再根据现场拓扑选择具体目标。一次只改变一个变量，并保留相同设备、认证、目标和样本大小。

### 被动状态与主动扫描

先读取不改变关联的状态：

```sh
ubus call network.interface.wwan status
iw dev
iw dev <station-iface> link
iw dev <station-iface> station dump
iw dev <station-iface> survey dump
iwinfo <station-iface> info
```

这些命令分别给出地址、路由、SSID/BSSID、频率、信号、MCS/NSS、重传和噪声。连续采样时，从 `/sys/class/net/<station-iface>/statistics/{rx,tx}_bytes` 读取相邻差值，换算当前接口流量。

主动扫描会占用无线电资源并增加延迟，具体影响依驱动而异。业务运行时默认不扫描当前关联的 radio；若有独立闲置 radio，只扫描闲置 radio，并设置硬超时。扫描结果只表示是否听到 beacon（AP 周期广播帧）以及其中的 SSID/BSSID/信道，不能证明双向关联、DHCP 或吞吐可用。

### <a id="logs"></a>OpenWrt 日志与历史数据

OpenWrt 会记录近期系统事件，但不会默认保存完整的信号和流量时间序列。官方[系统日志说明](https://openwrt.org/docs/guide-user/base-system/log.essentials)指出，默认 `logd` 把固定大小的记录保存在 RAM 环形缓冲中，`logread` 可以读取、写文件或转发到远端。排障前先分清“事件日志”“当前状态”和“额外采样”：

| 数据 | 默认历史 | 查看位置 | 主要边界 |
|---|---|---|---|
| 系统、网络管理服务（netifd）、无线认证程序（wpa_supplicant）、EAP、DHCP、WNM | 近期事件 | `logread` | 内存环形缓冲，覆盖或重启后消失 |
| 内核和无线驱动 | 近期事件 | `dmesg`、`logread` | 可见 beacon loss、能力变化和断开 |
| 接口、SSID、BSSID、地址 | 无 | `ubus`、`iw` | 只表示查询时的当前状态 |
| signal、MCS/NSS、PHY、重传 | 无时序历史 | `iw station dump`、Linux 网卡计数文件 | 必须周期采样才能画曲线 |
| DHCP lease | 当前租约 | `/tmp/dhcp.leases` | 不是完整连接历史 |
| Dashboard 曲线 | 页面打开期间 | 浏览器内存 | 页面关闭后默认丢失 |
| 最近测速结果 | 取决于面板实现 | 面板缓存 | 不是 OpenWrt 内建日志 |

实时跟踪和筛选无线相关日志只需要一段命令：

```sh
logread -f
logread | grep -E 'wpa_supplicant|netifd|EAP|DHCP|WNM'
```

需要保存数小时或数天时，可以把系统事件发往远程 syslog，并把 signal、MCS、重传、字节计数和延迟写入独立时序存储。持续写入路由器内置闪存会增加磨损，存储位置和采样周期应单独设计。

### 分层延迟、抖动与丢包

按路径逐层选择目标：

| 层次 | 目标 | 回答的问题 |
|---|---|---|
| 无线第一跳 | WWAN 默认网关 | 无线一跳是否丢包或抖动 |
| 内部网络 | 组织内部稳定服务 | 接入层和内部路由是否正常 |
| 公共互联网 | 稳定公共 IP | 完整上网路径是否正常 |

第一跳地址应从当前路由读取，不能硬编码旧 DHCP 网关。分别测试小包和接近 MTU 的大包，并记录丢包、最小/平均/最大延迟和样本时段。BusyBox `ping` 的参数能力随构建变化，先看本机帮助，不假设支持小数间隔。

### 分层内容下载

ping 能观察时延和丢包，却不能回答持续传输容量在哪一层下降；NDT7 又会直接测完整公网路径，无法单独定位内部接入。为此可以在路径上选择由近到远的内容源：

| 内容源 | 例子 | 主要排查范围 |
|---|---|---|
| 本地 LAN | 同一局域网内的 HTTP server | 终端、网线、下游 AP 与 LAN |
| 同一管理域 | 运营方、学校或企业内部镜像 | 无线接入、认证后网络和内部路由 |
| 公共互联网 | 外部镜像或对象存储 | 公共出口与外部路径 |

不是每个现场都有内部镜像；缺少某一层时就跳过，但要明确剩余测试无法区分哪些路径。选择目标时尽量使用大小相同或同源的静态文件，用 HTTP Range（只下载指定字节段）固定样本长度，并在相近时段连续测试：

```sh
curl --interface <lan-address> \
  --resolve <internal-host>:80:<verified-ip> \
  --range 0-4999999 \
  -o /dev/null \
  http://<internal-host>/<large-file>
```

其余层次使用相同 Range、文件大小和协议。若 LAN 内容已经慢，先处理本地链路；LAN 快而内部服务慢时，瓶颈进入无线或接入层；内部快、公共目标慢时，再检查公共出口和外部路径。

校园网只是这套方法的一个特例：校内镜像充当“同一管理域”目标，校外镜像充当“公共互联网”目标。企业网可以换成内网制品库与公共镜像，酒店或公共热点若没有内部服务，就只能比较第一跳、公共目标和 NDT7。

运行 mihomo fake-IP（DNS 返回占位地址）或 TUN（虚拟网卡隧道）的环境，不能用普通 53 端口查询判断真实地址。先用 DoH（DNS over HTTPS，通过 HTTPS 查询 DNS）获取真实地址，或使用已核验 IP 配合 `curl --resolve`；完整 DNS 流向见 [Mihomo / Clash](mihomo.md)。

总平均速度会掩盖掉线和令牌桶形状。下载期间每秒读取 station 的 `rx_bytes`，把差值画成时间序列：无线不稳通常伴随波动、重传和 RSSI/MCS 变化；平坦贴近固定值才值得继续验证策略限速。

### M-Lab NDT7 基准测试

[M-Lab NDT](https://www.measurementlab.net/tests/ndt/)是主动的大流量容量测试。NDT7 使用一条加密测试连接测量应用层有效吞吐，并报告下载、上传、负载延迟和 TCP 重传相关指标。

NDT7 会主动占满链路，不能当作“实时流量”持续运行。适合的流程是：

1. 由用户手动触发；
2. 暂停其他主动延迟和扫描任务；
3. 使用官方 reference client，通过 M-Lab Locate 选择服务器；
4. 设置总超时；
5. 只有同时得到服务器、下载和上传结果时才写入历史；
6. Locate 超时或全零摘要应显示失败，不得塑造成成功。

```sh
<ndt7-client> -format=json -timeout=60s
```

NDT7 的 loaded latency（负载延迟）是测速占满链路时的延迟，不能替代空闲公网 RTT（Round-Trip Time，往返时延）。高带宽链路一次 NDT7 会传输大量数据，因此默认只按需运行。

### 频段、位置、SSID 与 BSSID 的 A/B 测试

A/B 测试每轮只改变一个变量：

- 2.4 GHz 与 5 GHz；
- 室内与窗边/室外；
- 不同上游 SSID；
- 自动 BSSID 与固定 BSSID；
- VHT/HE 与 HT20；
- 普通路由器与定向 CPE。

每轮至少记录 signal、noise、SNR、信道宽度、NSS、MCS、重传增量、第一跳丢包、内部下载、外部下载和 NDT7。先检查是否取得 DHCP 和通过认证，再运行吞吐测试。

## <a id="cpe"></a>使用定向 CPE

定向 CPE 是带定向天线、用于连接远端 AP的无线客户端设备。它把接收和发射集中到目标方向，并通常支持 PoE（Power over Ethernet，通过网线供电）和室外部署。它适合改善长距离、遮挡或干扰造成的链路预算，但不能改变上游认证策略或 AP/网络控制器行为。

### 天线增益、EIRP 与安装位置

EIRP（Equivalent Isotropically Radiated Power，等效全向辐射功率）把发射功率和天线增益合并表示。定向天线可以提高目标方向的接收增益，并抑制其他方向的干扰；发射侧则受设备和监管配置约束。OpenWrt 也会按天线增益与监管上限限制发射功率，不能把标称天线增益简单等同于上行增加同样 dB。

PoE 允许把设备放到视线、朝向和遮挡更合适的位置，再用网线把数据送回室内。室外安装还涉及设备自身的防护等级、接地、防雷和供电规范，应按产品和建筑条件单独设计。

### 频段、信道与企业认证能力

“5 GHz CPE”不保证覆盖所有 5 GHz 信道。不同地区和 SKU（具体销售型号/地区版本）可能只开放部分 5.2/5.8 GHz 范围；购买前先扫描现场 AP 的信道，再核对设备的精确频率范围和监管区域。

企业网络还要求 CPE固件具备 station 模式的无线客户端认证程序、目标 EAP 方法、证书校验和必要的漫游能力。只写“支持 WPA2”不足以证明支持 WPA2-Enterprise PEAP/MSCHAPv2。

### 单台 station 与成对桥接

| 目标 | 本地设备数量 | 对端要求 |
|---|---:|---|
| 连接现有标准 AP，再本地路由/NAT | 一台 CPE | 对端提供标准 Wi-Fi |
| 建立自己管理的透明点对点桥 | 通常两台配套设备 | 双方兼容桥接/四地址或厂商协议 |

单台 CPE 的 station 模式适合本文网关结构；“必须买一对”只适用于自己建设两端链路的场景。

### 购买前验证与预期边界

购买前核对：

- 现场信道是否在设备频率范围内；
- station/WISP（以 Wi-Fi 作为 WAN）模式是否可用；
- WPA2-Enterprise/EAP 与证书验证是否满足上游；
- 网口速率、PoE电压和供电方式；
- 天线增益、波束宽度和安装方向；
- 是否能固定 BSSID、导出日志和恢复配置；
- 是否保留可退换或现场试用条件。

CPE 更可能改善弱信号、低 SNR、高重传和方向性干扰。它不能保证消除 AP发出的 WNM通知、AP能力广播异常、账号限速或公共出口拥塞。应使用[测量与排查链路](#measurement)中的同目标 A/B 测试判断收益。

## <a id="dashboard"></a>部署与使用监控面板

链路面板运行在 OpenWrt 设备本机：HTML 页面由路由器的轻量 Web 服务（例如 uhttpd）提供，状态接口在路由器上读取 `ubus`、`iw` 和网卡计数器。浏览器只是显示这些数据，管理电脑关机不会让路由器端面板消失。

通用单文件模板见 [openwrt-link-dashboard.html](../assets/openwrt-link-dashboard.html)。模板不包含真实 SSID、设备名、Portal 地址或采集后端；页面顶部配置对象定义 API 路径、网络标签、延迟目标和过期时间。

### 面板运行位置与访问地址

终端要先接入 OpenWrt 的 LAN，或接入已经桥到该 LAN 的下游 AP。随后在浏览器打开：

```text
http://<openwrt-lan-ip>:<dashboard-port>/
```

`<openwrt-lan-ip>` 通常是终端网络详情中的默认网关，也是 LuCI 管理地址；`<dashboard-port>` 是部署面板时为 uhttpd 或其他 Web 服务设置的端口。

下游设备仍处于路由模式时，双重 NAT 和防火墙可能阻止访问上一级 OpenWrt；切为 AP 模式后，终端与 OpenWrt 位于同一 LAN，访问最直接。需要从 LAN 之外访问时，可以另建受控代理或隧道，但那属于部署环境，不是模板默认组成。

### 信号、当前流量、延迟与基准测速

面板应区分：

| 展示项 | 数据来源 | 语义 |
|---|---|---|
| signal/noise/SNR | `iw` / `iwinfo` | 当前接收与噪声 |
| TX/RX PHY | `iw link` | 当前协商档位 |
| 当前流量 | 相邻 `rx_bytes` / `tx_bytes` 差值 | 接口当前占用，不是可用带宽 |
| 实时 RTT（往返时延）/loss（丢包率） | 小样本 ping | 当前公网路径状态 |
| NDT7 | 主动基准测试 | 按需测下载、上传、负载延迟和重传 |
| 最近扫描 | 非活动 radio 的缓存 | 候选网络可见性，不代表可用性 |

0–100 信号分数只能作为可配置的展示映射。模板默认使用线性映射帮助快速观察，但会明确标记为启发式评分（便于展示的经验映射），不把它当成行业标准。

### 路由器实时数据来源

状态接口在 OpenWrt 本机按需读取：

| 数据 | OpenWrt 来源 |
|---|---|
| WWAN 地址和连接状态 | `ubus call network.interface.wwan status` |
| SSID、BSSID、信号和 PHY | `iw link` / `iw station dump` |
| 当前流量 | `/sys/class/net/<iface>/statistics/` |
| 候选网络 | 非活动 radio 的扫描缓存 |
| 实时延迟 | 路由器主动发出的小样本 ping |
| NDT7 | 用户手动触发的主动基准 |

这些是实时查询，不是从 `logread` 回放出来的历史。字段缺失或状态接口超时时，前端应显示不可用，不用 `0` 伪装测量结果。

### 活动频段扫描与任务互斥

默认调度原则：

- 被动状态可以每秒读取；
- 活动 radio 不做周期扫描；
- 闲置 radio 扫描使用较长间隔、硬超时和缓存；
- 延迟精测与 NDT7 互斥；
- NDT7 运行时暂停实时轮询和其他主动任务；
- 任务结束或失败后自动恢复被动采集；
- 所有后台任务有进程锁和总时限。

扫描接口卡住时，应终止具体进程并重新检查无线运行态；不要用不带范围的进程名杀法，也不要直接重载配置掩盖原因。

### STALE 状态与扫描滞回

STALE 表示实时数据已经过期；扫描滞回则表示一次漏扫不会立刻把网络判定为消失。超过可配置时间没有新状态时，面板必须：

- 显示 OFFLINE/STALE；
- 清空信号、流量、实时延迟和连接详情；
- 标出最后更新时间；
- 保留明确标记为历史的 NDT7 结果；
- 数据恢复后自动重新填充。

扫描偶尔漏掉 beacon 时，不应立刻把网络显示为消失。对每个 SSID/频段保留可配置的最近可见时间（last-seen TTL，TTL 表示保留时长），并显示“最近看到”；连续过期后才清空。

### 实时数据、设备日志与长期历史

面板的实时曲线通常只存在于当前浏览器内存；页面关闭后，过去的 signal、MCS 和流量曲线默认丢失。OpenWrt 的 `logread` 仍可能保留同一时段的断开、WNM、EAP 和 DHCP 事件，但不能重建每秒曲线。

三类历史应分别处理：

- **事件历史**：由 OpenWrt 日志提供，适合解释“为什么断开”；
- **实时曲线**：由 Dashboard 周期采样，适合观察“断开前数值怎样变化”；
- **长期历史**：需要额外时序存储或远程采集，OpenWrt 默认不提供。

完整日志边界见 [OpenWrt 日志与历史数据](#logs)。Dashboard 可能暴露 SSID、BSSID、内网地址和链路状态，默认应绑定管理 LAN 或指定接口，并用防火墙限制访问；需要跨不可信网络访问时增加认证和 TLS。不要把无认证的 `0.0.0.0` 监听作为通用默认值。

### HTML 模板与数据接口

模板内置演示数据，可以直接打开检查布局；配置真实 API（Application Programming Interface，供页面读取数据的接口）后才进入实时模式。适配时只需要实现状态、延迟和基准测试三类 JSON（结构化数据格式），不必复制现场专用的后端脚本或 SSH 代理。

页面采用低噪声深色布局，以当前信号、链路档位、实时流量和基准测试为主，不使用与操作无关的装饰卡片。数值变化有平滑过渡，STALE 与测试暂停使用明确状态，不让动画掩盖数据含义。

## <a id="campus-case"></a>校园无线接入案例

本案例记录一次实际部署，用于展示测量方法怎样改变配置选择。设备、位置、AP负载和测试服务器都只代表当时条件。

### OpenWrt 网关与下游 AP

部署使用一台刷入 OpenWrt 25.12.5 的小米 AX3000T 作为无线接入网关：5 GHz station 连接校园上游，WWAN 加入 WAN 防火墙并做 NAT，三个 LAN 输出独立子网。小米 BE3600 后来成功切为 AP 模式，把网线转换成室内 Wi-Fi并扩展网口，终端直接从 AX3000T 获取地址。

AX3000T 自身不广播本地 SSID。这样无线接入和室内覆盖由两台设备分别承担，不需要同一 radio 同时做上游 station 和下游 AP。

### 2.4 GHz 与 5 GHz 的双向链路

同一位置的受控实连曾得到：

| 频段 | signal | 第一跳大包 | 平均延迟 | 驱动 expected throughput |
|---|---:|---:|---:|---:|
| 2.4 GHz | 约 −54 dBm | 10% 丢包 | 163.6 ms | 约 5.7 Mbps |
| 5 GHz | 约 −65 dBm | 0% 丢包 | 7.0 ms | 约 187.7 Mbps |

2.4 GHz 扫描看起来更强，却有低上行档位和高重传；5 GHz RSSI更弱但双向链路明显更好。后来在另一位置测试两个 2.4 GHz 开放 SSID时，也曾看到约 −65 dBm beacon，却只能关联约一秒，随后 beacon loss、认证超时且拿不到 DHCP。

这些结果说明扫描 RSSI不能替代实连、DHCP、重传和第一跳测试。

### 访客认证、企业认证与上游选择

开放访客网经下游终端完成 Portal 后，单次 NDT7 曾测得约 14.49 Mbps 下载、18.86 Mbps 上传。这个结果证明 Portal 后的数据路径可用，不代表长期稳定值。

5 GHz eduroam 使用 PEAP/MSCHAPv2和服务器证书 pin 后，实测约为：

| 指标 | 结果 |
|---|---:|
| signal | 约 −74 至 −77 dBm |
| NDT7 下载 / 上传 | 13.14 / 6.57 Mbps |
| 第一跳平均延迟 | 11.5 ms |
| 公网平均延迟 | 48.3 ms |
| 30 包公网丢包 | 0% |

另一开放校园网无需再次 Portal 即可访问公网，但同一时段 NDT7 只有约 0.42/1.01 Mbps，第一跳和公网延迟也更高，因此没有被选为主上游。不同上游测试发生在不同连接阶段，不能把这些数字当作严格实验室横评。

### 延迟尖峰、重传与漫游

eduroam 运行期间，日志出现 AP发出的 WNM `Disassociation Imminent`。真正断线的两次事件分别表现为同一 AP能力从 VHT 变为 HT，以及从 VHT 变为 legacy；本机 mac80211 驱动随后断开、重新选 AP、完成 EAP 和 DHCP。两次完整恢复约需 5–6 秒；没有真正断线的 WNM 事件也伴随 150–220 ms 延迟尖峰和高重传。

因此故障不是单一“认证慢”：

- 弱信号和重传造成持续抖动；
- AP/网络控制器的漫游引导造成候选扫描；
- AP能力广播变化触发客户端重建关联；
- EAP 与 DHCP 决定完整断线后的恢复时长。

活动 5 GHz radio 的周期扫描后来被关闭，NDT7 改为手动运行，避免监控工具本身制造游戏卡顿。

### CPE 的预期收益与未验证边界

本案例尚未购买 CPE。根据现有数据，定向 CPE有机会改善弱 SNR、上行档位、重传和方向性干扰；它不能保证消除学校 AP的 WNM通知或能力广播变化。

实际购买前仍需核对现场信道、企业认证、频率范围、PoE和 station 能力，并用相同上游、相同测试目标做 A/B。没有 CPE实测前，不给出成功概率或承诺网速。
