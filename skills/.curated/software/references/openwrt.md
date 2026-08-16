# OpenWrt 硬件、安装与网络使用

OpenWrt 是面向路由器和嵌入式网络设备的 Linux 发行版。本文先讲通用的硬件选择、官方安装流程、系统管理和网络模式，最后以小米 AX3000T 为实际案例。

通用安装章节只采用 OpenWrt 官方文档规定的流程；设备案例只补充该型号独有的分区、入口和实测结果，并引用前面的通用概念，不重复把个案写成普遍规则。

## <a id="system"></a>OpenWrt 系统

### Linux 发行版与可扩展能力

[OpenWrt 25.12.5 的项目说明](https://github.com/openwrt/openwrt/blob/v25.12.5/README.md#L3-L10)将其定义为面向嵌入式设备的 Linux 操作系统。SSH 登录后进入的就是路由器上实际运行的 OpenWrt，而不是容器或另一个桌面发行版。

OpenWrt 提供 Linux 内核、可写配置层和软件包管理，可以组合 DHCP、DNS、防火墙、VLAN、多 WAN、VPN、无线 AP、无线客户端和策略路由。LuCI 是网页管理入口；UCI 管理 `/etc/config/*`；ubus 提供服务间通信和状态查询；Dropbear 提供 SSH。

它的自由度来自完整的网络操作系统，而不只是比原厂固件多几个设置页面。实际能用哪些功能仍取决于硬件驱动、闪存和内存容量，以及目标设备的 OpenWrt 支持状态。

### 设备支持

OpenWrt 镜像必须匹配精确型号和硬件修订版。相同商品名可能对应不同 SoC、NAND、交换芯片或无线芯片；一个修订版受支持，不代表所有同名机器都能使用相同镜像。

选购或安装前至少确认：

- [Table of Hardware](https://openwrt.org/toh/start) 或 [Firmware Selector](https://firmware-selector.openwrt.org/) 中存在精确设备 profile；
- 当前稳定版支持该硬件修订，而不只是开发分支或论坛补丁；
- 闪存、内存、网口数量和速率满足用途；OpenWrt 的 [8/64 警告](https://openwrt.org/supported_devices/864_warning)明确说明这类设备不足以稳定运行现代版本；
- 设备页提供可执行的首次安装方法和故障恢复入口；
- 无线电、交换芯片、LED、按键和硬件加速等板级功能已有驱动。

“OpenWrt 上游支持硬件”和“厂商允许从后台安装 OpenWrt”是两件事。部分设备有官方升级入口；部分设备虽然已有上游 profile，首次安装仍需要厂商恢复模式或设备专属权限入口。

## <a id="hardware"></a>OpenWrt 硬件选择

### 选购条件

先按实际用途决定硬件，而不是先追求最高规格：

- 主路由关注 WAN/LAN 速率、硬件卸载、SQM 和稳定性；
- 无线 AP 关注无线驱动、频段、空间流和布点；
- 旅行路由器关注 Wi-Fi 作为 WAN、Captive Portal、MAC clone、便携供电和多上游切换；
- 实验平台关注串口、恢复分区、可更换存储、SFP、M.2 和无线模块；
- x86 软路由关注 CPU、网卡驱动和存储，通常另配无线 AP。

常见硬件路线可以这样理解：

| 路线 | 典型设备 | 主要特点 |
|---|---|---|
| OpenWrt 原生设备 | OpenWrt One | 出厂运行 OpenWrt，带 LuCI、串口和独立恢复设计 |
| 基于 OpenWrt 的成品路由器 | GL.iNet、Turris 等 | 厂商提供消费级 UI，部分型号可较容易切换官方 OpenWrt |
| 旅行路由器 | GL.iNet Beryl AX 等 | 把现有 Wi-Fi 作为 WAN，再提供自己的 LAN 和 AP |
| 开发板型路由器 | Banana Pi BPI-R4 | 接口和扩展性强，但需要自行处理机箱、模块、启动介质和安装 |
| x86 小主机 | 通用 Intel / AMD 主机 | 性能和存储充足，安装到磁盘，Wi-Fi 通常交给独立 AP |
| 上游支持的消费路由器 | 部分普通家用路由器 | 硬件性价比高，但首次安装与恢复高度依赖具体型号 |

[OpenWrt One](https://openwrt.org/toh/openwrt/one) 出厂即带当前 OpenWrt 和 LuCI，并提供 NAND/NOR 双启动、USB-C 串口和恢复路径；它适合学习和维护 OpenWrt，但只有一个 WAN 和一个 LAN 口。

[GL.iNet Flint 2](https://openwrt.org/toh/gl.inet/gl-mt6000) 的厂商系统是 OpenWrt fork，可从厂商 Web UI 安装官方 sysupgrade 镜像，U-Boot Web UI 还能独立恢复。厂商分支与上游 OpenWrt 的内核、驱动和功能暴露可能不同，选购时应分别核对。

[Banana Pi BPI-R4](https://openwrt.org/toh/sinovoip/bananapi_bpi-r4) 和 [x86 平台](https://openwrt.org/docs/guide-user/installation/openwrt_x86) 更接近可组装网络主机：前者可选 NAND、eMMC、microSD、SFP 和无线模块，后者直接把系统镜像写入磁盘。它们的安装、驱动和无线方案比消费级成品更需要自行集成。

### 旅行路由器

旅行路由器的核心不是体积，而是把酒店、校园、热点或手机共享网络作为上游，再建立一个自己控制的 LAN 和无线 AP。典型的 WISP 模式会让上下游处于不同子网，并通过 NAT 和防火墙隔离公共网络。

[GL.iNet 的 Repeater 文档](https://docs.gl-inet.com/router/en/4/interface_guide/internet_repeater/)展示了公共热点登录模式、MAC clone、随机 MAC、BSSID 锁定和企业认证入口。这类厂商 UI 把常见旅行场景产品化，但具体型号和固件版本支持的认证方式仍需逐项核对。

上游 OpenWrt 也提供 [Travelmate](https://github.com/openwrt/packages/blob/fc8b2fec0ba9bcda54c0cbb2968a33f6b4637006/net/travelmate/files/README.md)。它管理多个无线 uplink、自动重连、开放热点、Captive Portal 检测和外部登录脚本。双频设备最好用一张无线电连接上游，另一张提供本地 AP；同一无线电同时收发会共享 airtime。

### 定向 CPE 与远距离链路

OpenWrt 可以改变网络模式，但不能凭软件产生天线增益。若普通路由器只有在窗边某个位置才能稳定连接，应先测量 RSSI、噪声、重传、上下行吞吐和长时间丢包，再判断问题来自建筑衰减、干扰还是链路距离。

远端已有普通 AP 时，本地只需一台能作为标准 Wi-Fi station 的定向 CPE，不必在远端再安装配对设备。定向天线需要朝向 AP 所在方向，并同时改善接收和回传。选择 CPE 时还要核对频段、企业认证能力、网口速度、PoE 电压和恢复方式；CPE 可以运行厂商系统、RouterOS 或 OpenWrt，不必为了单纯的射频链路强行使用 OpenWrt。

## <a id="installation"></a>OpenWrt 安装

### 设备专属说明

OpenWrt 官方明确说明：首次安装是设备专属流程，通用教程不能替代具体设备页。先在 Table of Hardware 或 Firmware Selector 找到精确型号，再按该页面给出的镜像、端口、IP、按钮时序和恢复方法操作。[通用安装说明](https://openwrt.org/docs/guide-user/installation/generic.flashing)只用于理解常见路径。

官方文档中的常见安装入口包括：

- 在原厂 Web UI 上传设备专用的 factory 镜像；
- 进入 bootloader 的 Web、TFTP、串口或其他恢复模式；
- 将镜像写入可移动存储或磁盘，例如开发板和 x86；
- 使用设备页明确记录的厂商接口或权限入口。

不要因为另一款设备使用相同 SoC 就照搬分区号、启动变量或恢复文件；也不要修改 bootloader，除非设备页明确要求。

### 镜像和安装阶段

多数嵌入式设备使用 factory 镜像完成从原厂系统到 OpenWrt 的首次安装，之后使用 sysupgrade 镜像升级已有 OpenWrt。[官方 sysupgrade 文档](https://openwrt.org/docs/guide-user/installation/sysupgrade.cli)明确区分了两者。x86 等平台通常使用 combined 磁盘镜像，没有相同的 factory/sysupgrade 划分。

安装前应完成以下准备：

1. 核对精确设备 profile、目标版本和镜像散列。
2. 阅读设备页的安装与恢复章节，准备稳定电源和有线管理链路。
3. 保存现有配置；设备页要求备份 bootloader、校准数据或原厂分区时，先完成并验证备份。
4. 记录当前系统、分区和启动状态，确认目标存储没有选错。
5. 只执行设备页规定的首次安装方法，出现 I/O、ECC、散列或兼容性错误立即停止。

进入 OpenWrt 后，可用下面的关键命令确认设备身份并检查正式升级镜像：

```sh
ubus call system board
sysupgrade -T /tmp/<sysupgrade-image>
sysupgrade -v /tmp/<sysupgrade-image>
```

升级镜像应放在 RAM 中的 `/tmp` 并先验证 SHA-256。是否保留配置按版本兼容性和设备说明决定；只有明确要清空设置时才加 `-n`。`sysupgrade` 会主动关闭服务和 shell；连接断开本身不能证明升级失败，应等待设备重新启动后再检查版本、存储和网络。

### 升级与恢复

sysupgrade 会替换 OpenWrt 系统和内核。保留设置只会保存指定配置，不会自动保留所有手工安装的软件包或任意数据文件；跨越较大版本时还要遵循升级提示决定是否清空配置。[官方升级说明](https://openwrt.org/docs/guide-user/installation/generic.sysupgrade)要求事先保留当前镜像、配置备份和恢复方案。

恢复原厂系统不是 OpenWrt 的统一能力。它取决于设备是否保留原厂 bootloader、恢复分区、厂商镜像、TFTP/UART 入口和本机校准数据。安装前应先知道恢复路径，而不是安装后再假设 factory reset 能还原厂商系统。

## <a id="management"></a>OpenWrt 系统管理

### 系统环境和软件包

OpenWrt 使用 BusyBox、`ash` 和 `procd`，不是 Bash + systemd 的服务器环境。25.12 使用 `apk` 管理软件包；旧教程中的 `opkg` 命令不能直接照搬。[官方迁移说明](https://openwrt.org/docs/guide-user/additional-software/opkg-to-apk-cheatsheet)还明确警告不要用 `apk upgrade` 盲目升级整机，应通过 sysupgrade、Attended Sysupgrade 或 Firmware Selector 更新系统。

LuCI、UCI 和 ubus 操作同一套系统配置：

```sh
uci show network
uci show wireless
ubus call system board
ubus call network.interface.lan status
```

[UCI](https://openwrt.org/docs/guide-user/base-system/uci) 集中管理 `/etc/config/*`；[ubus](https://openwrt.org/docs/techref/ubus)负责服务注册、状态查询和方法调用。修改 UCI 后要 commit，并 reload 或 restart 对应服务。

### SSH 与 Dropbear

OpenWrt 默认使用 Dropbear。25.12.5 的[默认配置](https://github.com/openwrt/openwrt/blob/v25.12.5/package/network/services/dropbear/files/dropbear.config#L1-L9)启用端口 22 和密码认证；未指定接口时会监听所有地址。默认防火墙允许 LAN 入站、拒绝 WAN 入站，因此 LAN 或绑定到 LAN 的 AP 客户端可以尝试连接 SSH，而 WWAN/WAN 客户端通常被阻止。

监听接口和防火墙是两层控制。完成公钥验证后，可把 Dropbear 直接绑定到 LAN 并关闭 SSH 密码认证。

### <a id="ssh-security"></a>SSH key-only

先创建并上传公钥，再强制验证一条不允许密码回退的新连接：

```sh
ssh-keygen -t ed25519 -f ~/.ssh/openwrt-router
cat ~/.ssh/openwrt-router.pub | ssh root@openwrt.lan \
  'umask 077; cat >> /etc/dropbear/authorized_keys; chmod 600 /etc/dropbear/authorized_keys'
ssh -i ~/.ssh/openwrt-router -o IdentitiesOnly=yes \
  -o PasswordAuthentication=no -o BatchMode=yes root@openwrt.lan 'echo key-ok'
```

私钥带 passphrase 时先加载到 ssh-agent，相关边界见 [SSH 的非交互 agent](ssh.md#agent-noninteractive)。只有看到 `key-ok` 后，才在路由器上执行：

```sh
uci set dropbear.main.DirectInterface='lan'
uci set dropbear.main.PasswordAuth='off'
uci set dropbear.main.RootPasswordAuth='off'
uci commit dropbear
/etc/init.d/dropbear restart
```

25.12.5 的 Dropbear 脚本会把 `DirectInterface='lan'` 解析到实际 LAN 设备，见[接口绑定](https://github.com/openwrt/openwrt/blob/v25.12.5/package/network/services/dropbear/files/dropbear.init#L236-L250)和[认证参数](https://github.com/openwrt/openwrt/blob/v25.12.5/package/network/services/dropbear/files/dropbear.init#L302-L326)。已有系统若没有名为 `main` 的配置节，应先以 `uci show dropbear` 核对真实名称。

关闭 SSH 密码认证不等于删除 root 系统密码；LuCI 和本地恢复仍可使用该密码。

### 指示灯和板级功能

LED、按键、交换芯片和无线电是否可用，取决于设备树和驱动支持。受支持的 LED 通常出现在 `/sys/class/leds/`，并通过 `/etc/config/system` 或 LuCI 的 LED Configuration 绑定启动、网络和无线触发器，详见[官方 LED 配置](https://openwrt.org/docs/guide-user/base-system/led_configuration)。

OpenWrt 可以提供标准状态灯，但不保证复刻厂商固件的全部颜色、动画或专有联动。

## <a id="networking"></a>OpenWrt 网络配置

### WAN、LAN、AP 与 station

WAN 和 LAN 是三层网络与防火墙角色；AP 和 station 是无线接口角色：

- AP 广播 SSID，供下游客户端接入；
- station 让路由器作为客户端连接上游 Wi-Fi；
- station 可以作为 WWAN，再经路由和 NAT 向 LAN/AP 供网；
- AP 也可以接入现有有线 LAN，成为不做路由的普通无线接入点。

“无线 AP”只说明下游如何接入；“桥接”说明上下游是否处于同一二层网络，两者不能混为一谈。

### 无线网络作为 WAN

旅行路由和 Wi-Fi 转有线通常采用 station → WWAN → WAN firewall → NAT → LAN/AP。关键配置只包括创建 DHCP 型 WWAN、把无线 station 绑定到它，并把 WWAN 加入启用 masquerading 的 WAN zone：

```sh
uci set network.wwan=interface
uci set network.wwan.proto='dhcp'
uci set wireless.upstream.mode='sta'
uci set wireless.upstream.network='wwan'
```

设备、SSID、认证参数和凭据按上游网络填写，随后 commit 并 reload 网络与无线。双频设备可把一张无线电用于上游，另一张用于本地 AP；共用同一无线电也能工作，但吞吐和重连过程会互相影响。

### <a id="wireless-auth"></a>无线认证

| 上游网络 | 认证发生位置 | OpenWrt 侧要求 |
|---|---|---|
| 开放网络或 WPA2/WPA3 Personal | 无认证或预共享密钥 | 默认无线客户端能力 |
| WPA2-Enterprise | 路由器的 wpa_supplicant/wpad 与 AP/RADIUS 认证 | 完整 EAP 参数和 full wpad |
| Captive Portal | 关联和 DHCP 后，由浏览器或登录脚本完成网页认证 | HTTP 重定向、Portal 处理和可能的 MAC 策略 |

默认镜像常带 `wpad-basic-mbedtls`，足以处理普通 Personal 网络。PEAP、TTLS、TLS 等企业认证需要 full wpad；25.12.5 的 [hostapd 包定义](https://github.com/openwrt/openwrt/blob/v25.12.5/package/network/services/hostapd/Makefile#L269-L302)显示 `wpad-openssl` 提供完整 EAP supplicant。

先模拟替换事务，再决定是否执行：

```sh
apk add --simulate wpad-openssl
apk add wpad-openssl
```

只有模拟结果能在同一事务中替换 basic provider 并补齐依赖时才执行第二条；不要先手工删除当前 provider。

Captive Portal 通常由 NAT 后面的电脑或手机打开网页完成。上游看到的往往是路由器 WWAN 的地址和 MAC，因此认证后多个下游设备可能共享连接，但具体结果取决于 Portal 是否绑定账号、IP、MAC、设备数量或应用指纹。Travelmate 可检测 Portal、管理多个 uplink 和调用外部登录脚本；厂商旅行路由器还可能提供登录模式和 MAC clone。

### AP、NAT 与无线桥接

路由 + NAT 会建立自己的下游子网，对上游要求最低，也能把公共网络与本地设备隔离。它适合旅行路由、Wi-Fi 转有线和大多数不受控上游。

WDS/四地址模式是真正的二层无线桥接，会保留客户端 MAC、广播和上游 DHCP，但需要上游 AP 与 station 的实现兼容。官方说明见[无线 WDS 桥接](https://openwrt.org/docs/guide-user/network/wifi/wifiextenders/wds)。

上游不支持 WDS 时，[`relayd` 中继](https://openwrt.org/docs/guide-user/network/wifi/relay_configuration)可以模拟同网段体验，但它不等同真实二层桥接，配置和排障也更复杂。只有确实需要同一广播域、局域网发现或上游 DHCP 时，才需要从 NAT 转向桥接。

### 链路质量

信号格或扫描结果只能说明接收到 AP Beacon 的强度。验收无线 uplink 时还应观察 RSSI、噪声、协商速率、重传、上下行吞吐、连续丢包和重启后的自动重连。

建筑玻璃、金属窗框和墙体可能让几十厘米的位置变化产生明显差异。先在安全位置测试不同频段和摆放点；只有普通路由器在最佳位置仍出现上传差、频繁掉线或高重传时，才说明需要定向 CPE 或改变布点。

## <a id="ax3000t"></a>小米 AX3000T 案例

本节只记录 AX3000T 的设备差异和一次实际安装结果。factory/sysupgrade、SSH 安全、无线认证和 NAT/桥接原理分别引用[官方安装流程](#installation)、[SSH key-only](#ssh-security)和[网络配置](#networking)。

### 硬件版本与原厂固件

RD03 国行和 RD23 国际版使用 MediaTek MT7981B，官方 OpenWrt 支持。RD03v2 改用 Qualcomm 平台，当前不受支持；包装 SKU `DVB4510CN` 或条码结尾 `706330` 可用于识别。不要把 RD03/RD23 镜像写入 RD03v2。[OpenWrt Wiki 的固定修订](https://openwrt.org/toh/xiaomi/ax3000t?rev=1780820319)记录了这组边界。

原厂固件版本只影响免拆机 SSH 入口：

| 机型与固件 | 设备页记录的入口 |
|---|---|
| RD03 1.0.47 | `misystem/arn_switch` |
| RD03 1.0.64、1.0.84、1.0.90、1.0.91、1.0.98 | `xqsystem/start_binding` |
| RD03 1.0.106 | 无已知 API；需降级或 UART |
| RD23 1.0.31、1.0.49、1.0.55、1.0.76 | `xqsystem/start_binding` |
| RD23 1.0.90、1.0.91、1.0.92、1.0.97、1.0.103、1.0.104 | `xqsystem/get_icon` |

25.12.5 已覆盖设备页列出的 ESMT、Winbond、Foresee NAND，以及 MT7531AE、AN8855 交换芯片变体。新装仍应先读取真实硬件信息，不按商品名猜测。

### Windows 单网线接入

小米原厂固件会动态判断四个网口的 WAN/LAN 角色。电脑单线直连时，端口可能被识别成 WAN，双方都等待 DHCP，Windows 只得到 `169.254.x.x`。

优先换插其他端口或临时连接原厂 Wi-Fi。必须维持有线连接时，Windows 可临时充当只响应目标 MAC 的限域 DHCP server；有线口不设默认网关，不启用 ICS 或桥接。临时租约会随进程停止或电脑休眠而失效。

复杂 PowerShell 应落成 `.ps1` 并按 [Windows 命令调用](windows.md#invocation)执行。

### 原厂盘点与备份

取得 SSH 后先确认活动槽、分区编号和目标槽是否挂载：

```sh
cat /proc/cmdline
cat /proc/mtd
ubinfo -a
```

实际案例备份了 BL2、Nvram、Bdata、Factory、FIP、两个原厂 UBI 槽、overlay、data 和 KF，共十个关键分区，并在路由器与电脑两端交叉校验。`Bdata`、`Factory`、`Nvram` 和无线校准数据只能用于原设备恢复。

运行中的 overlay/data 连续读取两次，原始散列一致后才接受。老 Dropbear 或 initramfs 没有 SFTP server 时，Windows OpenSSH 使用 `scp -O`。

### stock-layout 安装

案例保留原厂 bootloader，使用官方 25.12.5 stock-layout 的 initramfs factory 和 squashfs sysupgrade 镜像；没有使用名称带 `ubootmod` 的镜像。

根据当前活动槽，只写另一槽：

| 当前 cmdline | factory 写入目标 | `flag_boot_rootfs` / `flag_last_success` |
|---|---|---|
| `firmware=1 mtd=ubi1` | `/dev/mtd8` | `0` / `0` |
| `firmware=0 mtd=ubi` | `/dev/mtd9` | `1` / `1` |

关键写入命令只有：

```sh
ubiformat <inactive-mtd> -y -f /tmp/<initramfs-factory.ubi>
```

写入成功后，按官方设备页为目标槽设置 `flag_boot_rootfs` 和 `flag_last_success`，同时启用 `boot_wait`、`uart_en`、`flag_boot_success`，并清零两个尝试失败计数。每个变量都回读无误后才重启；不能只替换部分槽位参数。

临时系统必须确认型号、`rootfs_type=initramfs`、交换芯片、三个 LAN、一个 WAN、两张无线电和 LuCI，再按[通用安装章节](#installation)检查并执行正式 sysupgrade。

### 安装后的恢复边界

临时阶段只覆盖非活动槽，原厂活动槽、overlay 和 data 仍在。正式 sysupgrade 会把原厂 `mtd8` 用作 OpenWrt `ubi_kernel`，并把原厂 `mtd9 + mtd10 + mtd11` 合并重建为持久 `ubi`，见 [AX3000T DTS](https://github.com/openwrt/openwrt/blob/v25.12.5/target/linux/mediatek/dts/mt7981b-xiaomi-mi-router-ax3000t.dts#L18-L34)和[升级脚本](https://github.com/openwrt/openwrt/blob/v25.12.5/target/linux/mediatek/filogic/base-files/lib/upgrade/platform.sh#L48-L96)。

因此正式安装后不能靠切换启动槽完整回到原厂系统；恢复依赖本机备份和该设备实际可用的 TFTP/UART 路径。设备页仍有未填写的 TFTP 参数时，不从其他小米型号照搬。

### 实测结果

本次设备为 RD03、原厂固件 1.0.64、MT7981 + MT7531AE、128 MiB NAND。官方 25.12.5 stock-layout 经两阶段安装后：

- 正式系统以 squashfs + UBIFS overlay 启动，可写空间约 60.7 MiB；
- NAND 没有坏块或 I/O 错误，重启后配置保持；
- 靠近电源的端口为 WAN，三个中间口为 LAN；
- 两张无线电、LuCI、SSH 和端口均正常；
- 已实现个人热点 → 5 GHz station → WWAN/NAT → 有线 LAN，重启后自动恢复；
- 短测信号约 `-51 dBm`，协商速率约 `1200.9 Mbit/s`，公网和 DNS 正常；
- 已设置 root 密码并拒绝空密码 SSH；SSH key-only 尚需按通用章节完成；
- 企业认证和 Captive Portal 尚未在该上游环境实际验收，因此文中的支持结论来自官方功能与软件包，不把它写成案例实测。

AX3000T 的公共设备树定义了蓝色和黄色状态灯：启动、failsafe 和升级使用黄色，正常运行使用蓝色，见[固定版本源码](https://github.com/openwrt/openwrt/blob/v25.12.5/target/linux/mediatek/dts/mt7981b-xiaomi-mi-router-common.dtsi#L9-L16)和[GPIO LED 定义](https://github.com/openwrt/openwrt/blob/v25.12.5/target/linux/mediatek/dts/mt7981b-xiaomi-mi-router-common.dtsi#L44-L57)。这些是标准 Linux 状态灯，不保证复刻小米原厂的全部动画。

这次个人热点短测证明了 Wi-Fi 转有线 NAT 和持久重连，但不能替代目标远距离网络的半小时丢包、上下行吞吐和数小时稳定性测试；是否需要定向 CPE 仍应由目标链路实测决定。
