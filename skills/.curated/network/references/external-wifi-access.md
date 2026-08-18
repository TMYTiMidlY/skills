# 外部 Wi-Fi 接入本地网络

把外部 Wi-Fi 接入本地网络时，由 station（无线客户端）连接上游 AP，再把网络交给本地有线 LAN、下游 AP 或终端。中间的上游接入设备可以做路由与 NAT，也可以在两端支持时做桥接；它可以运行厂商系统、RouterOS、OpenWrt 或其他具备相应无线客户端能力的系统。

这个结构不同于只强调扩大覆盖范围的消费级“无线放大器”：它把上游连接、本地网络、认证、无线电位置和链路观测拆成可独立配置和验证的部分。本文先讲通用的数据路径、认证、无线指标、链路测量和 CPE 选型，再以 OpenWrt 配置和校园部署作为具体实现。OpenWrt 的安装、升级、SSH、专属配置对象和路由器端监控面板见 [OpenWrt 设备管理](openwrt.md)。

## <a id="architecture"></a>设备角色与数据路径

链路由上游 Wi-Fi AP、上游接入设备、本地有线网络和下游终端组成。下游 AP 只负责本地无线覆盖时，应工作在 AP 模式，不再承担第二层 DHCP 和 NAT。

```mermaid
flowchart LR
    upstream[外部 Wi-Fi AP]
    gateway[上游接入设备 / CPE]
    downstream[下游 AP / 交换机]
    clients[本地终端]

    upstream -->|Wi-Fi 客户端连接| gateway
    gateway -->|路由/NAT 或桥接| downstream
    downstream --> clients
```

### 系统职责与数据路径

四类对象的职责如下：

| 对象 | 主要职责 | 不应承担的职责 |
|---|---|---|
| 外部 AP | 提供上游 Wi-Fi 和网络地址 | 不需要为本地网部署配套设备 |
| 上游接入设备 | 作为 station 连接上游，完成认证、地址获取、转发和链路观测 | 不必同时承担本地无线覆盖 |
| 下游 AP | 把本地有线 LAN 转成室内 Wi-Fi，并扩展网口 | AP 模式下不再运行独立 DHCP/NAT |
| 本地终端 | 从本地网络取得地址并访问上游 | 不直接保存每个上游网络的配置 |

AP 与 station 描述无线接口两端的角色：

- AP 广播无线网络并接受 station 接入；
- station 连接已有 AP，并可把这条上游连接交给本地路由、网线或另一个 AP；
- AP 也可以只桥接已有有线 LAN，不承担路由。

AP 与 station 说明无线连接的方向；路由、NAT 或桥接则说明上下游怎样交换数据。同一设备可以同时承担上游 station 和下游 AP，但若两者共用同一无线电，就会共享信道时间，扫描和重连也会影响本地覆盖。使用不同无线电或独立设备可以避免这种直接争用；实际能否并发仍取决于硬件、驱动和固件。

在 OpenWrt 中，station 对应 `wifi-iface` 的 `mode='sta'`，承载无线 WAN 的逻辑接口通常称为 WWAN；具体对象见 [网络配置接口](openwrt.md#network-surfaces)。

下游 AP 可以放在适合室内覆盖的位置，上游接入设备或定向 CPE（Customer Premises Equipment，带定向天线、用于连接远端 AP 的用户侧无线终端）则可以放在上游信号最好的位置，两者用网线连接。玻璃、金属窗框和墙体会改变衰减与反射，几十厘米的位置变化也可能明显改变实际链路；扫描信号强度只能作为选点线索，最终仍要通过关联、DHCP、重传、上下行吞吐和连续延迟验证。

### 路由、WDS 与 relayd

普通 Wi-Fi station 的客户端帧不能自动把网线后方多个终端的 MAC 透明送给上游，因此最通用的实现是建立独立子网并路由转发。OpenWrt 的[无线客户端配置](https://openwrt.org/docs/guide-user/network/wifi/connect_client_wifi?rev=1705097879)是这一路径的一个具体实现。

WDS/四地址桥接是在无线帧中保留下游终端身份的透明桥接方式，需要两端兼容；`relayd` 则用代理 ARP 等三层机制模拟同一网段。只有确实需要上游 DHCP、广播发现或原始客户端 MAC 时，才考虑这两类方案。

| 模式 | 上游看到的身份 | 下游地址 | 上游要求 | 适用边界 |
|---|---|---|---|---|
| 路由 + NAT | 上游接入设备的无线地址和 MAC | 本地独立子网 | 标准 AP | 公共网络、企业网络、Wi-Fi 转网线 |
| WDS / 四地址桥接 | 下游终端原始 MAC | 上游网段 | AP 与 station 双方兼容四地址 | 自己管理两端设备的桥接链路 |
| `relayd` | 由代理 ARP 等机制模拟 | 通常为上游网段 | 不要求 WDS | 必须保留上游地址、且能接受复杂排障 |

> Linux wireless 文档要求 AP 和客户端双方都启用四地址帧才能透明桥接；厂商的 proprietary bridge 模式也可能无法跨品牌工作。OpenWrt 的 [WDS](https://openwrt.org/docs/guide-user/network/wifi/wifiextenders/wds?rev=1746783203)和 [`relayd`](https://openwrt.org/docs/guide-user/network/wifi/relay_configuration?rev=1752850857)文档分别说明了这两条路径。

### 双重 NAT 与 AP 模式

若上游接入设备已经在无线 WAN 与本地 LAN 之间做 NAT，下游路由器继续以 WAN 路由模式接入，就会形成双重 NAT。普通网页访问通常仍能工作，但端口映射、P2P、部分游戏和跨网段设备发现会变复杂。

下游设备进入 AP 模式后的目标状态是：

- DHCP 由上游接入设备提供；
- 所有终端位于同一本地 LAN 子网；
- 下游设备只做 Wi-Fi AP 和交换机；
- 上游接入设备的管理地址可从下游 Wi-Fi 直接访问；
- 网线接法按下游设备的 AP 模式说明决定，不能假设一定使用 WAN 或 LAN 口。

切换后应分别检查终端地址、默认网关、DNS、上游接入设备的管理页和公网访问。只看到下游 SSID 不代表 AP 模式已经正确完成。

## <a id="configuration"></a>OpenWrt 上的链路配置

本节以 OpenWrt 实现上述数据路径。其他系统只要能提供 station、地址获取、路由或桥接、下游 DHCP 和防火墙，也可以实现同一链路。

### 准备管理路径与配置备份

在 OpenWrt 上配置这条链路时，始终保留一条不会随上游无线切换而消失的管理路径。最稳妥的是电脑直接连接 OpenWrt LAN，确认管理地址和 SSH 可用，再保存配置备份。

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

上游网络可能组合多种认证方式，它们不是互斥的产品类型：

| 认证位置 | 常见方案 | 链路设备需要的能力 | 成功标志 |
|---|---|---|---|
| 无线关联与加密 | 开放网络、WPA2/WPA3 Personal | station 与相应密码套件 | 已关联到目标 AP |
| 无线接入控制 | WPA2-Enterprise、PEAP、TTLS、TLS | EAP supplicant（无线客户端认证程序）、账号或客户端证书、服务器证书校验 | EAP 成功并进入可获取地址的状态 |
| 取得地址之后 | Captive Portal | DHCP、HTTP 跳转以及浏览器或登录脚本 | Portal 会话放行实际流量 |

例如开放网络可以在关联后再要求 Portal，Personal 网络也可能叠加网页认证。仅看到 Wi-Fi 已连接，不能证明 DHCP、Portal 或公网访问已经成功。

### Captive Portal

Captive Portal 是“连上 Wi-Fi 后，再由网页完成的强制认证门户”。开放热点通常先完成无线连接和 DHCP，再通过 HTTP 重定向进入 Portal。路由 + NAT 后，上游通常只看到上游接入设备的无线地址和 MAC，因此一次认证可能供多个下游终端共享。

这个行为取决于 Portal 是否绑定 MAC、IP、Cookie、账号、设备数或其他特征，必须现场验证。稳妥流程是：

1. 从下游终端访问一个纯 HTTP 页面；
2. 完成 Portal 认证；
3. 用另一台终端验证是否共享；
4. 重连和会话过期后再次验证。

直接打开某个已知 Portal IP 可能进入错误的认证系统，或因系统无法反查当前 MAC 而失败。应优先让目标网络自己的 HTTP 重定向给出入口。

若 Portal 把无线 MAC 当作设备身份，随机 MAC、MAC clone 或更换无线接口都会影响会话。需要稳定复用会话时应保持上游 MAC 稳定；只有网络策略允许且原设备已经离线时才考虑克隆，避免两个在线设备使用同一 MAC。

### WPA2-Enterprise 与服务器证书

WPA2-Enterprise 是基于 802.1X（端口接入控制框架）的企业 Wi-Fi 认证，由账号、证书和 EAP（Extensible Authentication Protocol，可扩展认证协议）共同完成。PEAP 是把账号认证放进 TLS（Transport Layer Security，加密通道）的 EAP 方法，MSCHAPv2 则常作为隧道内的用户名/密码认证。

链路设备需要具备目标 EAP 方法和服务器证书校验能力。OpenWrt 的完整 wpad 变体、具体包名和 UCI 字段见 [无线配置与 wpad](openwrt.md#wireless-wpad)。本节只确认三个结果：EAP 成功、上游接口取得地址、服务器证书被正确验证。

服务器证书校验不能省略。OpenWrt 25.12.5 的 station 脚本会传递 `ca_cert`、`domain_match` 和 `domain_suffix_match`；上游 [wpa_supplicant 配置](https://w1.fi/cgit/hostap/plain/wpa_supplicant/wpa_supplicant.conf?id=ca266cc24d8705eb1a2a0857ad326e48b1408b20)明确指出，不设置 CA 时服务器证书不会被验证。优先使用受信 CA 加服务器域名限制；无法部署私有 CA 时，可以按该版本支持的格式固定服务器证书：

```text
ca_cert="hash://server/sha256/<certificate-sha256>"
```

证书 pin 会在服务器换证后失效，因此恢复资料中要记录 pin 的来源和更新方法。不要用关闭验证来换取短期连通。

### 凭据保存与备用上游

企业账号、热点密码和证书通常会保存在上游接入设备中；OpenWrt 会把相应配置保存为 root 可读。写入时避免让凭据进入 shell 历史、命令参数或调试日志；使用受控输入，并确认备份文件的访问权限。

可以保存一条禁用的备用上游配置，主上游失败时手动切换。禁用配置条目只表示内容已保存，**不是自动故障切换**；自动切换还需要优先级、健康检查、认证状态和回切条件。

## <a id="radio-metrics"></a>理解无线链路

无线信号不能只看一个 RSSI（Received Signal Strength Indicator，接收信号强度指标）数字。不同系统可以提供相同类别的链路指标；OpenWrt 25.12.5 锁定的 [iwinfo `f5dd57a`](https://github.com/openwrt/iwinfo/blob/f5dd57a84cc31a403a1383dd14944fa2e2b5824a/iwinfo_cli.c)分别报告 signal、noise、MCS、NSS 和信道宽度，并按 `signal - noise` 显示 SNR（Signal-to-Noise Ratio，信噪比）。

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

本文件保留 RSSI、SNR、MCS、漫游和 CPE 等通用无线原理。OpenWrt 上的状态命令、主动扫描、分层延迟与下载、NDT7、时间序列和 A/B 测试见 [无线链路测量与排查](openwrt.md#link-measurement)。

### <a id="logs"></a>OpenWrt 日志入口

OpenWrt 的事件日志、当前状态和长期历史边界见 [链路日志与监控面板](openwrt.md#link-dashboard)。

## <a id="cpe"></a>使用定向 CPE

定向 CPE 是带定向天线、用于连接远端 AP的无线客户端设备。它把接收和发射集中到目标方向，并通常支持 PoE（Power over Ethernet，通过网线供电）和室外部署。它适合改善长距离、遮挡或干扰造成的链路预算，但不能改变上游认证策略或 AP/网络控制器行为。

### 天线增益、EIRP 与安装位置

EIRP（Equivalent Isotropically Radiated Power，等效全向辐射功率）把发射功率和天线增益合并表示。定向天线可以提高目标方向的接收增益，并抑制其他方向的干扰；发射侧则受设备、固件和监管配置约束，不能把标称天线增益简单等同于上行增加同样 dB。

PoE 允许把设备放到视线、朝向和遮挡更合适的位置，再用网线把数据送回室内。室外安装还涉及设备自身的防护等级、接地、防雷和供电规范，应按产品和建筑条件单独设计。

### 频段、信道与企业认证能力

“5 GHz CPE”不保证覆盖所有 5 GHz 信道。不同地区和 SKU（具体销售型号/地区版本）可能只开放部分 5.2/5.8 GHz 范围；购买前先扫描现场 AP 的信道，再核对设备的精确频率范围和监管区域。

企业网络还要求 CPE固件具备 station 模式的无线客户端认证程序、目标 EAP 方法、证书校验和必要的漫游能力。只写“支持 WPA2”不足以证明支持 WPA2-Enterprise PEAP/MSCHAPv2。

CPE 可以运行厂商系统、RouterOS、OpenWrt 或其他专用固件；无线链路需求本身不决定必须使用哪一种系统。选型应落实到 station、频段、EAP、证书校验、日志、配置备份和故障恢复能力，而不是只看操作系统名称。

### 单台 station 与成对桥接

| 目标 | 本地设备数量 | 对端要求 |
|---|---:|---|
| 连接现有标准 AP，再本地路由/NAT | 一台 CPE | 对端提供标准 Wi-Fi |
| 建立自己管理的透明点对点桥 | 通常两台配套设备 | 双方兼容桥接/四地址或厂商协议 |

单台 CPE 的 station 模式适合本文链路结构；“必须买一对”只适用于自己建设两端链路的场景。

### 购买前验证与预期边界

购买前核对：

- 现场信道是否在设备频率范围内；
- station/WISP（以 Wi-Fi 作为 WAN）模式是否可用；
- WPA2-Enterprise/EAP 与证书验证是否满足上游；
- 网口速率、PoE电压和供电方式；
- 天线增益、波束宽度和安装方向；
- 是否能固定 BSSID、导出日志、备份配置，并通过恢复网页、备用分区或其他明确入口从错误配置和升级失败中恢复；
- 是否保留可退换或现场试用条件。

CPE 更可能改善弱信号、低 SNR、高重传和方向性干扰。它不能保证消除 AP发出的 WNM通知、AP能力广播异常、账号限速或公共出口拥塞。应使用 [OpenWrt 无线链路测量与排查](openwrt.md#link-measurement)中的同目标 A/B 测试判断收益。

## <a id="dashboard"></a>OpenWrt 监控面板

OpenWrt 路由器端的信号、PHY、当前流量、延迟、NDT7、扫描缓存、过期状态和 HTML 面板实现见 [链路日志与监控面板](openwrt.md#link-dashboard)。

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
