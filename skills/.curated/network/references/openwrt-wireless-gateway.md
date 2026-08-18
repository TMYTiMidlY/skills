# OpenWrt 无线接入网关

OpenWrt 无线接入网关把外部 Wi-Fi 当作上游网络，在路由器上完成关联、认证、地址获取、防火墙和 NAT，再从有线 LAN 输出网络；下游可以直接接电脑，也可以接一台 AP 扩展本地 Wi-Fi。这个结构不同于消费级“无线放大器”：它把无线接入、路由、认证和链路观测拆成可独立配置和验证的层。

本文先说明系统角色和配置流程，再解释认证、无线指标、链路测量、定向 CPE 和监控面板。OpenWrt 的安装、升级、SSH 和设备支持边界见 [OpenWrt 设备管理](openwrt.md)。

## <a id="architecture"></a>系统角色与数据路径

无线接入网关由上游 Wi-Fi、OpenWrt 网关、有线 LAN 和下游终端组成。下游 AP 只负责本地无线覆盖时，应工作在 AP 模式，不再承担第二层 DHCP 和 NAT。

```mermaid
flowchart LR
    upstream[外部 Wi-Fi AP]
    gateway[OpenWrt 无线接入网关]
    downstream[下游 AP / 交换机]
    clients[本地终端]

    upstream -->|station| gateway
    gateway -->|WWAN + 路由/NAT| downstream
    downstream --> clients
```

### 上游 Wi-Fi、OpenWrt 网关与下游 AP

四类对象的职责如下：

| 对象 | 主要职责 | 不应承担的职责 |
|---|---|---|
| 外部 AP | 提供 802.11 接入和上游地址 | 不需要为本地网部署配套设备 |
| OpenWrt 网关 | station、认证、WWAN、DHCP、NAT、防火墙、链路观测 | 默认不需要广播本地 Wi-Fi |
| 下游 AP | 把网关的有线 LAN 转成室内 Wi-Fi，并扩展网口 | AP 模式下不再运行独立 DHCP/NAT |
| 本地终端 | 从 OpenWrt LAN 获取地址并访问上游 | 不直接保存每个上游网络的配置 |

上游与本地覆盖使用不同无线电或不同设备时，不会因同一无线电轮流收发而直接争用信道时间。下游 AP 可以放在适合室内覆盖的位置，OpenWrt 网关或 CPE 则可以放在上游信号最好的位置，两者用网线连接。

### 路由、WDS 与 relayd

普通 Wi-Fi station 使用三地址帧，不能自动把网线后方多个终端的 MAC 透明送给上游 AP。OpenWrt 官方的[无线客户端配置](https://openwrt.org/docs/guide-user/network/wifi/connect_client_wifi?rev=1705097879)因此默认建立独立子网并路由转发。需要保留同一二层广播域时，才考虑 WDS/四地址桥接或 `relayd`。

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

## <a id="configuration"></a>网关配置流程

配置无线接入网关时，始终保留一条不会随上游无线切换而消失的管理路径。最稳妥的是电脑直接连接 OpenWrt LAN，先备份，再修改 station、WWAN 和防火墙。

### station、WWAN、DHCP 与防火墙 NAT

完整数据路径需要三组配置同时成立：

| 配置层 | 必要关系 |
|---|---|
| 无线 | `wifi-iface` 使用 `mode='sta'`，绑定 `network='wwan'` |
| 网络 | `network.wwan` 使用 DHCP 或上游要求的协议 |
| 防火墙 | `wwan` 属于启用 masquerading 的 WAN 区，允许 LAN 转发到 WAN |

下面只展示关系，不假设 WAN 区的 UCI section 名称。修改前先用 `uci show firewall` 找到实际 section：

```sh
uci set network.wwan='interface'
uci set network.wwan.proto='dhcp'

uci set wireless.upstream='wifi-iface'
uci set wireless.upstream.device='<radio>'
uci set wireless.upstream.mode='sta'
uci set wireless.upstream.network='wwan'
uci set wireless.upstream.ssid='<upstream-ssid>'
uci set wireless.upstream.encryption='<encryption>'

uci add_list firewall.<wan-zone-section>.network='wwan'
```

先用 `uci changes` 审核待提交内容，再按 package 分别 `uci commit`，最后重载对应服务。不要在未知配置上照抄 `firewall.@zone[1]` 之类的匿名下标。

应用后至少验证：

```sh
ubus call network.wireless status
ubus call network.interface.wwan status
iw dev
ip route
```

WWAN 取得地址只证明关联和 DHCP 成功；Captive Portal 或企业认证还需要按[上游认证与漫游](#authentication)继续验证。

### 网线输出与下游 AP

OpenWrt LAN 应使用与上游不同的子网，并运行 DHCP。网线连接下游 AP 后，终端应直接从 OpenWrt 获取地址。若终端仍拿到下游设备自己的网段，说明下游仍在路由模式。

验证顺序是：

1. 电脑直接连接 OpenWrt LAN，确认 WWAN、NAT 和 Portal/企业认证。
2. 连接下游设备，但暂不改变 OpenWrt。
3. 将下游设备切为 AP 模式。
4. 从下游 Wi-Fi 检查地址、网关、DNS、OpenWrt 管理页和公网。
5. 重启两台设备，确认上游自动关联和下游 AP 自动恢复。

### 上游配置切换、回退与重启验收

测试新的 SSID、频段、企业认证或 BSSID 时，不要立刻覆盖已知可用配置。可以先保留原 profile，临时启用新 profile，验证成功后再提交；失败时 `uci revert wireless` 或恢复备份。

一个禁用的备用 profile 只表示配置已保存，**不是自动故障切换**。自动切换还需要定义优先级、健康检查、认证状态和回切条件；没有这些规则时，保持手动切换更容易解释和恢复。

每次最终配置都应经过：

- `wifi reload` 后自动重连；
- 完整重启后自动重连；
- 下游终端重新取得地址；
- 认证状态、DNS 和公网访问；
- 至少一段与业务时长相称的连续丢包和延迟测试。

## <a id="authentication"></a>上游认证与漫游

外部 Wi-Fi 的链路层关联、网络层地址和上层认证是三个阶段。排障时应先判断失败发生在哪一层，不能把“拿不到 DHCP”误判成 Portal 问题。

### Captive Portal 与共享网络身份

开放热点通常先完成关联和 DHCP，再通过 HTTP 重定向进入 Portal。路由 + NAT 后，上游通常只看到 OpenWrt 的 WWAN 地址和无线 MAC，因此一次认证可能供多个下游终端共享。

这个行为取决于 Portal 是否绑定 MAC、IP、Cookie、账号、设备数或其他特征，必须现场验证。稳妥流程是：

1. 从下游终端访问一个纯 HTTP 页面；
2. 完成 Portal 认证；
3. 用另一台终端验证是否共享；
4. 重连和会话过期后再次验证。

直接打开某个已知 Portal IP 可能进入错误的认证系统，或因系统无法反查当前 MAC 而失败。应优先让目标网络自己的 HTTP 重定向给出入口。

### WPA2-Enterprise、PEAP 与证书校验

OpenWrt 25.12.5 的 [`wpa_supplicant-full.config`](https://github.com/openwrt/openwrt/blob/v25.12.5/package/network/services/hostapd/files/wpa_supplicant-full.config)启用 PEAP、TTLS、TLS 和 MSCHAPv2；basic/mini 变体没有完整 EAP 方法。各 wpad 变体在[包定义](https://github.com/openwrt/openwrt/blob/v25.12.5/package/network/services/hostapd/Makefile)中互相提供和冲突，因此替换前必须检查版本和事务。

安全替换流程是：

1. 保留有线管理和配置备份。
2. `apk update` 后检查已安装 `hostapd-common` 与 wpad 版本。
3. 用 `apk add --simulate <full-wpad-variant>` 审核替换和依赖。
4. 若模拟牵涉无关核心包、版本不一致或不能形成可信事务，停止并改用匹配仓库或定制镜像。
5. 安装后确认常驻 wpa_supplicant 进程已加载新二进制，再配置企业网络。

PEAP/MSCHAPv2 的 UCI 字段在 25.12.5 中会映射到 wpa_supplicant network block：

```sh
uci set wireless.enterprise.encryption='wpa2'
uci set wireless.enterprise.eap_type='peap'
uci set wireless.enterprise.auth='MSCHAPV2'
uci set wireless.enterprise.identity='<identity>'
uci set wireless.enterprise.password='<password>'
```

凭据最终会存在 root 可读的配置中。注入时避免把值写进命令参数、shell 历史或日志；使用受控标准输入或短期权限文件，并在完成后清理。

服务器证书校验不能省略。OpenWrt 25.12.5 的 station 脚本会传递 `ca_cert`、`domain_match` 和 `domain_suffix_match`；上游 [wpa_supplicant 配置](https://w1.fi/cgit/hostap/plain/wpa_supplicant/wpa_supplicant.conf?id=ca266cc24d8705eb1a2a0857ad326e48b1408b20)明确指出，不设置 CA 时服务器证书不会被验证。优先使用受信 CA 加服务器域名限制；无法部署私有 CA 时，可以按该版本支持的格式固定服务器证书：

```text
ca_cert="hash://server/sha256/<certificate-sha256>"
```

证书 pin 会在服务器换证后失效，因此恢复资料中要记录 pin 的来源和更新方法。不要用关闭验证来换取短期连通。

### PMKSA 缓存、OKC 与 802.11r

这些机制都能减少企业网络漫游时的认证工作，但含义和前提不同：

| 机制 | 作用 | 依赖 |
|---|---|---|
| PMKSA caching | 复用曾经与某 AP 建立的 PMKSA | 客户端与 AP 保留缓存 |
| RSN preauthentication | 关联新 AP 前提前完成 802.1X/EAP | 同一 ESS、AP/网络/RADIUS 支持 |
| OKC / proactive key caching | 把同一 ESS 的 AP 作为可复用密钥候选 | 客户端和 AP/controller 兼容 |
| 802.11r FT | 使用 Fast Transition key management 缩短切换 | AP/controller 广播并配置 FT |

PMKSA caching 默认可用时不要主动禁用。OpenWrt 25.12.5 的 station 配置接受 `ieee80211r` 并生成 FT key management，但启用前应确认目标网络确实广播 FT；否则只增加无效变量。

上游 wpa_supplicant 支持 `proactive_key_caching=1`，但在 OpenWrt 25.12.5 的标准 station UCI 映射中没有找到同名字段。不要假设写一个未知 UCI option 就会生效；需要 OKC 时，应检查实际生成的 wpa_supplicant 配置和目标网络能力，再决定是否使用平台支持的透传或定制配置。

认证缓存只能缩短可兼容的重认证流程，不能阻止 AP/controller 发送 WNM 漫游或断开通知。

### WNM 漫游通知、BSSID 锁定与 HT20

完整 wpa_supplicant 构建包含 WNM/BSS Transition Management。上游 [WNM 实现](https://w1.fi/cgit/hostap/plain/wpa_supplicant/wnm_sta.c?id=ca266cc24d8705eb1a2a0857ad326e48b1408b20)会处理 `Disassociation Imminent`；这是 AP/controller 的网络引导，和 PMKSA、OKC、FT 是不同层面。

固定 BSSID 可以让 station 只关联一个 AP，OpenWrt 25.12.5 会把 `bssid` 写进 wpa_supplicant network block。代价是正常漫游被关闭，目标 AP 真正故障或退服时无法自动换台；wpa_supplicant 对固定 BSSID 的 BTM 请求也可能直接拒绝。

把 5 GHz radio 限制为 HT20 可以作为排查“VHT/HT 能力变化”或宽信道干扰的 A/B 变量，但它会降低 PHY 上限。本次案例没有完成 HT20 长测，因此不能把它写成通用修复。正确做法是记录基线，只改 `htmode`，再比较断线、重传、延迟和吞吐。

## <a id="radio-metrics"></a>无线链路指标

无线信号不能只看一个 RSSI 数字。OpenWrt 25.12.5 锁定的 [iwinfo `f5dd57a`](https://github.com/openwrt/iwinfo/blob/f5dd57a84cc31a403a1383dd14944fa2e2b5824a/iwinfo_cli.c)分别报告 signal、noise、MCS、NSS 和信道宽度，并按 `signal - noise` 显示 SNR。

### RSSI、噪声与信噪比

| 指标 | 含义 | 使用方式 |
|---|---|---|
| signal / RSSI | 接收信号强度，单位 dBm | 越接近 0 通常越强，但不能单独判断双向质量 |
| noise | 接收机看到的噪声底，单位 dBm | 越低代表背景噪声越弱 |
| SNR | `signal - noise`，单位 dB | 决定可用调制余量，需和重传、MCS 一起看 |

例如某次现场状态为 `signal=-79 dBm`、`noise=-91 dBm`，按 iwinfo 口径 SNR 约为 12 dB；同时上行降到较低 MCS 并出现大量重传。这个例子说明弱信噪比与降速同时发生，不构成所有设备通用的阈值表。

### 信道宽度、空间流与 MCS

- **信道宽度**表示一次使用多少频谱，例如 20、40 或 80 MHz。更宽可以提高容量，也更容易受到同频资源和监管范围限制。
- **NSS（空间流数）**表示并行发送的独立数据流数量。NSS 1 与 NSS 2 的可用容量不同，但能否使用多流取决于双方天线、信道和链路条件。
- **MCS（调制编码方案索引）**表示每个符号承载的数据量和纠错强度。较低 MCS 更稳健、速率更低；较高 MCS 需要更好的信噪比。

现场曾观察到 `40 MHz / NSS 1 / VHT-MCS 0–2`，驱动报告的 PHY 上行在十几到数十 Mbps 间变化。这个组合描述的是当时协商档位，不是可直接套用到其他标准、GI 或设备的固定换算表。

### PHY 速率、实际吞吐与重传

`iw` 显示的 `tx bitrate` / `rx bitrate` 是无线 PHY 速率。Linux `iwconfig` 文档指出，应用可用速度会因介质共享和协议开销而更低。驱动的 `expected throughput` 也是估计值，不是测速结果。

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

## <a id="measurement"></a>链路测量与瓶颈定位

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

主动扫描会占用无线电资源并增加延迟，具体影响依驱动而异。业务运行时默认不扫描当前关联的 radio；若有独立闲置 radio，只扫描闲置 radio，并设置硬超时。扫描结果只用于发现 SSID/BSSID/信道，不能证明双向关联、DHCP 或吞吐可用。

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

不是每个现场都有内部镜像；缺少某一层时就跳过，但要明确剩余测试无法区分哪些路径。选择目标时尽量使用大小相同或同源的静态文件，固定样本长度，并在相近时段连续测试：

```sh
curl --interface <lan-address> \
  --resolve <internal-host>:80:<verified-ip> \
  --range 0-4999999 \
  -o /dev/null \
  http://<internal-host>/<large-file>
```

其余层次使用相同 Range、文件大小和协议。若 LAN 内容已经慢，先处理本地链路；LAN 快而内部服务慢时，瓶颈进入无线或接入层；内部快、公共目标慢时，再检查公共出口和外部路径。

校园网只是这套方法的一个特例：校内镜像充当“同一管理域”目标，校外镜像充当“公共互联网”目标。企业网可以换成内网制品库与公共镜像，酒店或公共热点若没有内部服务，就只能比较第一跳、公共目标和 NDT7。

运行 mihomo fake-IP/TUN 的环境不能用普通 53 端口查询判断真实地址。先用 DoH 获取真实地址，或使用已核验 IP 配合 `curl --resolve`；完整 DNS 流向见 [Mihomo / Clash](mihomo.md)。

总平均速度会掩盖掉线和令牌桶形状。下载期间每秒读取 station 的 `rx_bytes`，把差值画成时间序列：无线不稳通常伴随波动、重传和 RSSI/MCS 变化；平坦贴近固定值才值得继续验证策略限速。

### M-Lab NDT7 下载、上传与负载延迟

[M-Lab NDT](https://www.measurementlab.net/tests/ndt/)是主动 bulk-transport 容量测试。NDT7 使用单条 TCP/WebSocket TLS 连接测量应用层 goodput，并报告下载、上传、延迟和 TCP 重传相关指标。

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

NDT7 的 loaded latency 是测速负载下的延迟，不能替代空闲公网 RTT。高带宽链路一次 NDT7 会传输大量数据，因此默认只按需运行。

### 频段、位置、SSID 与 BSSID 的 A/B 测试

A/B 测试每轮只改变一个变量：

- 2.4 GHz 与 5 GHz；
- 室内与窗边/室外；
- 不同上游 SSID；
- 自动 BSSID 与固定 BSSID；
- VHT/HE 与 HT20；
- 普通路由器与定向 CPE。

每轮至少记录 signal、noise、SNR、信道宽度、NSS、MCS、重传增量、第一跳丢包、内部下载、外部下载和 NDT7。先检查是否取得 DHCP 和通过认证，再运行吞吐测试。

### 断连日志与历史记录

`logread` 可以看到关联、WNM、EAP 和 DHCP 事件，但默认日志位于内存，重启或覆盖后无法追溯。接口累计字节也不能重建过去的时间序列。

需要长期判断漫游或掉线时，应把下列信息写入持久存储或远程日志：

- 时间戳、SSID、BSSID、频率和信号；
- MCS/NSS/宽度和重传增量；
- WWAN 地址与关联 uptime；
- WNM、能力变化、EAP 和 DHCP 事件；
- 延迟、丢包和业务侧断流时间。

记录频率要低于业务可接受开销；不要为了诊断而在活动 radio 上持续扫描。

## <a id="cpe"></a>定向 CPE

定向 CPE 把天线能量集中到目标方向，并通常支持 PoE 和室外部署。它适合改善长距离、遮挡或干扰造成的链路预算，但不能改变上游认证策略或 AP/controller 行为。

### 天线增益、EIRP 与安装位置

定向天线可以提高目标方向的接收增益，并抑制其他方向的干扰。发射侧则受设备和监管 profile 约束；OpenWrt 的无线配置也会按天线增益与监管上限限制发射功率，不能把标称天线增益简单等同于上行增加同样 dB。

PoE 允许把设备放到视线、朝向和遮挡更合适的位置，再用网线把数据送回室内。室外安装还涉及设备自身的防护等级、接地、防雷和供电规范，应按产品和建筑条件单独设计。

### 频段、信道与企业认证能力

“5 GHz CPE”不保证覆盖所有 5 GHz 信道。不同地区和 SKU 可能只开放部分 5.2/5.8 GHz 范围；购买前先扫描现场 AP 的信道，再核对设备的精确频率范围和监管区域。

企业网络还要求 CPE固件具备 station supplicant、目标 EAP 方法、证书校验和必要的漫游能力。只写“支持 WPA2”不足以证明支持 WPA2-Enterprise PEAP/MSCHAPv2。

### 单台 station 与成对桥接

| 目标 | 本地设备数量 | 对端要求 |
|---|---:|---|
| 连接现有标准 AP，再本地路由/NAT | 一台 CPE | 对端提供标准 Wi-Fi |
| 建立自己管理的透明点对点桥 | 通常两台配套设备 | 双方兼容桥接/四地址或厂商协议 |

单台 CPE 的 station 模式适合本文网关结构；“必须买一对”只适用于自己建设两端链路的场景。

### 购买前验证与预期边界

购买前核对：

- 现场信道是否在设备频率范围内；
- station/WISP 模式是否可用；
- WPA2-Enterprise/EAP 与证书验证是否满足上游；
- 网口速率、PoE电压和供电方式；
- 天线增益、波束宽度和安装方向；
- 是否能固定 BSSID、导出日志和恢复配置；
- 是否保留可退换或现场试用条件。

CPE更可能改善弱信号、低 SNR、高重传和方向性干扰。它不能保证消除 AP发出的 WNM通知、AP能力广播异常、账号限速或公共出口拥塞。应使用[链路测量](#measurement)中的同目标 A/B 测试判断收益。

## <a id="dashboard"></a>链路监控面板

链路面板的任务是把“当前状态”“主动基准”和“历史结果”分开，避免断线后仍展示旧信号，或把接口当前流量误称为网速。

通用单文件模板见 [openwrt-link-dashboard.html](../assets/openwrt-link-dashboard.html)。模板不包含真实 SSID、设备名、Portal 地址或采集后端；页面顶部配置对象定义 API 路径、网络标签、延迟目标和过期时间。

### 信号、当前流量、延迟与基准测速

面板应区分：

| 展示项 | 数据来源 | 语义 |
|---|---|---|
| signal/noise/SNR | `iw` / `iwinfo` | 当前接收与噪声 |
| TX/RX PHY | `iw link` | 当前协商档位 |
| 当前流量 | 相邻 `rx_bytes` / `tx_bytes` 差值 | 接口当前占用，不是可用带宽 |
| 实时 RTT/loss | 小样本 ping | 当前公网路径状态 |
| NDT7 | 主动 benchmark | 按需测下载、上传、负载延迟和重传 |
| 最近扫描 | 非活动 radio 的缓存 | 候选网络可见性，不代表可用性 |

0–100 信号分数只能作为可配置的展示映射。模板默认使用线性映射帮助快速观察，但会明确标记为 heuristic，不把它当成行业标准。

### 路由器采集与局域网访问

推荐把被动采集放在 OpenWrt 本机，通过 uhttpd 或其他轻量 HTTP 服务提供 JSON；下游设备直接经 LAN 访问。若管理电脑不在同一 LAN，可以另建代理或隧道，但代理属于部署环境，不写进通用模板。

最小状态接口应提供：

```json
{
  "timestamp": 1710000000,
  "wwan": {
    "up": true,
    "active_ssid": "upstream-a",
    "active_band": "5",
    "address": "192.0.2.10"
  },
  "link": {
    "signal_dbm": -68,
    "noise_dbm": -92,
    "rx_rate": "240 MBit/s",
    "tx_rate": "180 MBit/s",
    "rx_bytes": 1200000,
    "tx_bytes": 340000,
    "tx_retries": 20,
    "tx_failed": 1
  },
  "latency": {
    "ok": true,
    "avg_ms": 24.1,
    "jitter_ms": 2.8,
    "loss_percent": 0,
    "timestamp": 1710000000
  },
  "benchmark": null
}
```

字段缺失时前端应显示不可用，不用 `0` 伪装测量结果。

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

超过可配置时间没有新状态时，面板必须：

- 显示 OFFLINE/STALE；
- 清空信号、流量、实时延迟和连接详情；
- 标出最后更新时间；
- 保留明确标记为历史的 NDT7 结果；
- 数据恢复后自动重新填充。

扫描偶尔漏掉 beacon 时，不应立刻把网络显示为消失。对每个 SSID/频段保留可配置的 last-seen TTL，并显示“最近看到”；连续过期后才清空。

### 历史记录与访问控制

浏览器内存曲线只适合当前页面，不是持久记录。需要分析数小时掉线时，把状态和日志发送到持久后端，并控制保留周期。

Dashboard 可能暴露 SSID、BSSID、内网地址和链路状态。默认绑定管理 LAN 或指定接口，并用防火墙限制访问；需要跨不可信网络访问时增加认证和 TLS。不要把无认证的 `0.0.0.0` 监听作为通用默认值。

### HTML 模板与数据接口

模板内置演示数据，可以直接打开检查布局；配置真实 API 后才进入实时模式。适配时只需要实现状态、延迟和 benchmark 三类 JSON，不必复制现场的 CGI 或 SSH 代理。

页面采用低噪声深色布局，以当前信号、链路档位、实时流量和 benchmark 为主，不使用与操作无关的装饰卡片。数值变化有平滑过渡，STALE 与测试暂停使用明确状态，不让动画掩盖数据含义。

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
- AP/controller 漫游引导造成候选扫描；
- AP能力广播变化触发客户端重建关联；
- EAP 与 DHCP 决定完整断线后的恢复时长。

活动 5 GHz radio 的周期扫描后来被关闭，NDT7 改为手动运行，避免监控工具本身制造游戏卡顿。

### CPE 的预期收益与未验证边界

本案例尚未购买 CPE。根据现有数据，定向 CPE有机会改善弱 SNR、上行档位、重传和方向性干扰；它不能保证消除学校 AP的 WNM通知或能力广播变化。

实际购买前仍需核对现场信道、企业认证、频率范围、PoE和 station 能力，并用相同上游、相同测试目标做 A/B。没有 CPE实测前，不给出成功概率或承诺网速。
