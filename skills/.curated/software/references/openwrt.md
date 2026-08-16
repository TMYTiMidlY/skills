# OpenWrt 的设备选择、安装与联网

OpenWrt 是面向路由器和嵌入式网络设备的 Linux 发行版。本文先讲通用的硬件选择、官方安装流程、系统管理和网络模式，最后以小米 AX3000T 为实际案例演示实操效果。

## <a id="system"></a>OpenWrt 系统介绍

### Linux 发行版与可扩展能力

[OpenWrt 25.12.5 的项目说明](https://github.com/openwrt/openwrt/blob/v25.12.5/README.md#L3-L10)将其定义为面向嵌入式设备的 Linux 操作系统。SSH 登录后进入的就是路由器上实际运行的 OpenWrt，而不是容器或另一个桌面发行版。

OpenWrt 提供 Linux 内核、可写配置层和软件包管理，可以组合 DHCP、DNS、防火墙、VLAN、多 WAN、VPN、无线 AP、无线客户端和策略路由。相关组件分别由 OpenWrt 自研、官方维护或集成第三方项目：

- [OpenWrt 主项目](https://github.com/openwrt/openwrt)：Linux 发行版、构建系统、目标设备和基础软件包。
- [LuCI](https://github.com/openwrt/luci)：OpenWrt 官方网页管理界面。
- [UCI](https://github.com/openwrt/uci)：OpenWrt 自研的统一配置系统，管理 `/etc/config/*`。
- [ubus](https://github.com/openwrt/ubus)：OpenWrt 自研的进程通信和服务调用总线。
- [Dropbear](https://github.com/mkj/dropbear)：独立的第三方轻量 SSH 项目；OpenWrt 维护自己的[集成配置](https://github.com/openwrt/openwrt/tree/v25.12.5/package/network/services/dropbear)。

UCI、ubus 等部分核心项目以 [git.openwrt.org](https://git.openwrt.org/) 为主仓库，GitHub 仓库是 OpenWrt 官方镜像。

它的自由度来自完整的网络操作系统，而不只是比原厂固件多几个设置页面。实际能用哪些功能，仍取决于 OpenWrt 是否支持该路由器的硬件，以及设备有多少闪存和内存。

### 设备支持

OpenWrt 镜像必须匹配精确型号和硬件版本。相同商品名可能使用不同的 SoC、闪存芯片（NAND）、网口交换芯片或无线芯片；其中一个版本受支持，不代表所有同名机器都能使用相同镜像。

> SoC（System on Chip，系统级芯片）是路由器的主芯片，通常把 CPU、网络处理和部分硬件控制功能集成在一起。它决定 OpenWrt 应使用哪个硬件平台和驱动，但只知道 SoC 仍不够：两台路由器即使使用同一款 SoC，也可能采用不同的闪存、网口交换芯片、无线芯片和分区布局。

选购或安装前至少确认：

- OpenWrt 官方的 [Table of Hardware](https://openwrt.org/toh/start) 或 [Firmware Selector](https://firmware-selector.openwrt.org/) 中存在这款设备的准确条目；
- 当前稳定版支持该硬件修订，而不只是开发分支或论坛补丁；
- 闪存、内存、网口数量和速率满足用途；OpenWrt 的 [8/64 警告](https://openwrt.org/supported_devices/864_warning)明确说明这类设备不足以稳定运行现代版本；
- 设备页提供可执行的首次安装方法和故障恢复入口；
- 无线、网口交换芯片、指示灯、按键和硬件加速等设备功能已有驱动。

确认设备受到支持后，应继续阅读官方设备页的首次安装说明，确定如何取得写入固件所需的权限，以及应该使用哪一种镜像。常见安装入口包括：

- 原厂网页升级：在原厂管理页面的“固件升级”功能中上传该设备的 OpenWrt factory 镜像；
- bootloader 恢复模式：在原厂系统启动前进入恢复网页、TFTP 或其他网络恢复环境，再写入固件；
- 厂商提供的 SSH 或开发模式：通过官方入口启用命令行管理权限，再按照设备页操作；
- 利用原厂固件漏洞取得 SSH：通过命令注入或远程代码执行漏洞启动 SSH，取得 root 权限后备份分区并写入镜像；适用的漏洞和原厂固件版本必须以设备页为准；
- UART 串口安装：拆机连接串口，在启动程序或系统控制台中加载和写入固件；
- 直接写入存储设备：将镜像写入硬盘、SSD、SD 卡或 eMMC，再从该存储设备启动。

如果安装依赖原厂固件漏洞，升级原厂固件可能会修复这个入口。因此安装前还要核对当前原厂固件版本，不要仅凭路由器型号判断操作方法。




## <a id="hardware"></a>适合 OpenWrt 的设备

### 设备选购

先按实际用途决定硬件，而不是先追求最高规格：

- 主路由关注 WAN/LAN 速率、硬件加速、智能队列管理（SQM）和稳定性；
- 无线 AP 关注无线驱动、频段、空间流数量和安装位置；
- 旅行路由器关注用 Wi-Fi 上网、网页认证（Captive Portal）、MAC 地址克隆、便携供电和多个上游网络切换；
- 实验平台关注串口、恢复分区、可更换存储、SFP、M.2 和无线模块；
- x86 软路由关注 CPU、网卡驱动和存储，通常另配无线 AP。

常见硬件路线可以这样理解：

| 路线 | 典型设备 | 主要特点 |
|---|---|---|
| OpenWrt 原生设备 | OpenWrt One | 出厂运行 OpenWrt，带 LuCI、串口和独立恢复系统 |
| 基于 OpenWrt 的成品路由器 | GL.iNet、Turris 等 | 厂商提供消费级 UI，部分型号可较容易切换官方 OpenWrt |
| 旅行路由器 | GL.iNet Beryl AX 等 | 把现有 Wi-Fi 作为 WAN，再提供自己的 LAN 和 AP |
| 开发板型路由器 | Banana Pi BPI-R4 | 接口和扩展性强，但需要自行准备机箱、无线模块、启动盘和安装流程 |
| x86 小主机 | 通用 Intel / AMD 主机 | 性能和存储充足，安装到磁盘，Wi-Fi 通常交给独立 AP |
| 上游支持的消费路由器 | 部分普通家用路由器 | 硬件性价比高，但首次安装与恢复高度依赖具体型号 |

[OpenWrt One](https://openwrt.org/toh/openwrt/one) 出厂即带当前 OpenWrt 和 LuCI，并同时配有正常启动用的 NAND 闪存、独立恢复用的 NOR 闪存和 USB-C 串口；它适合学习和维护 OpenWrt，但只有一个 WAN 和一个 LAN 口。

[GL.iNet Flint 2](https://openwrt.org/toh/gl.inet/gl-mt6000) 的厂商系统基于 OpenWrt 修改，可从厂商网页安装官方 OpenWrt 升级镜像，U-Boot 恢复网页还能在系统损坏时重新安装固件。厂商系统与官方 OpenWrt 使用的内核、驱动和可见功能可能不同，选购时应分别核对。

[Banana Pi BPI-R4](https://openwrt.org/toh/sinovoip/bananapi_bpi-r4) 和 [x86 平台](https://openwrt.org/docs/guide-user/installation/openwrt_x86) 更接近可组装网络主机：前者可选择板载闪存、eMMC、microSD、SFP 网口和无线模块，后者直接把系统镜像写入硬盘或 SSD。它们的安装、驱动和无线方案比消费级成品更需要自行配置。

### 旅行路由器

旅行路由器的核心不是体积，而是连接酒店、校园、公共热点或手机热点，再建立一个自己控制的 LAN 和无线 AP。常见的无线接入上网模式（WISP）会让公共网络和自己的设备处于不同网段，并通过 NAT 和防火墙隔离。

[GL.iNet 的 Repeater 文档](https://docs.gl-inet.com/router/en/4/interface_guide/internet_repeater/)展示了公共热点登录模式、MAC clone、随机 MAC、BSSID 锁定和企业认证入口。这类厂商 UI 把常见旅行场景产品化，但具体型号和固件版本支持的认证方式仍需逐项核对。

官方 OpenWrt 也提供 [Travelmate](https://github.com/openwrt/packages/blob/fc8b2fec0ba9bcda54c0cbb2968a33f6b4637006/net/travelmate/files/README.md)。它可以保存和切换多个上游 Wi-Fi、自动重连、发现开放热点、检测网页认证，并调用外部登录脚本。双频设备最好用一个频段连接上游，另一个频段提供自己的 AP；同一频段同时接收和转发时，两项工作会争用无线传输时间。

## <a id="installation"></a>OpenWrt 的安装

### 不同型号的安装方法

不同型号路由器第一次安装 OpenWrt 的方法不同，没有一套通用命令。先在 OpenWrt 官方 [Table of Hardware](https://openwrt.org/toh/start) 或 [Firmware Selector](https://firmware-selector.openwrt.org/) 找到准确型号，再按照该设备页给出的镜像、网口、IP 地址、按键时序和恢复方法操作。官方文档的[通用安装说明](https://openwrt.org/docs/guide-user/installation/generic.flashing)只能帮助理解常见方法，不能替代具体设备页。

官方文档中的常见安装入口包括：

- 在原厂网页中上传该型号的首次安装镜像（文件名通常带 `factory`）；
- 进入路由器启动程序（bootloader）提供的恢复网页、TFTP 网络恢复或 UART 串口；
- 将镜像写入可移动存储或磁盘，例如开发板和 x86；
- 使用设备页明确记录的厂商接口、SSH 或解锁方法。

不要因为另一款设备使用相同 SoC 就照搬它的闪存分区号、启动变量或恢复文件。除非设备页明确要求，否则不要修改 bootloader。

### 首次安装与升级

多数路由器使用文件名带 `factory` 的镜像完成“从原厂系统换成 OpenWrt”的第一次安装；已经运行 OpenWrt 后，再使用 `sysupgrade` 镜像升级系统。[官方 sysupgrade 文档](https://openwrt.org/docs/guide-user/installation/sysupgrade.cli)明确区分了两者。x86 等平台通常直接写入同时包含启动分区和系统分区的 combined 磁盘镜像，不使用同样的分类。

安装前应完成以下准备：

1. 核对准确设备条目、目标版本和镜像校验值。
2. 阅读设备页的安装与恢复章节，准备稳定电源和有线管理链路。
3. 保存现有配置；如果设备页要求备份启动程序、无线校准数据或原厂分区，先完成并验证备份。
4. 记录当前系统、分区和启动状态，确认准备写入的是正确闪存分区或硬盘。
5. 只执行设备页规定的方法；出现读写错误（I/O）、闪存校验错误（ECC）、镜像校验不一致或兼容性错误时立即停止。

进入 OpenWrt 后，可用下面的关键命令确认设备身份并检查正式升级镜像：

```sh
ubus call system board
sysupgrade -T /tmp/<sysupgrade-image>
sysupgrade -v /tmp/<sysupgrade-image>
```

将升级镜像上传到 OpenWrt 默认位于 RAM 中的临时文件系统  /tmp ，并确认可用内存足够容纳镜像。是否保留配置按版本兼容性和设备说明决定；只有明确要清空设置时才加 `-n`。`sysupgrade` 会主动关闭服务和 SSH；连接断开本身不能证明升级失败，应等待设备重新启动后再检查版本、存储和网络。

### 升级前准备与恢复

sysupgrade 会替换 OpenWrt 系统和 Linux 内核。“保留设置”只会保存指定配置，不会自动保留所有后来安装的软件包或任意数据文件；跨越较大版本时，还要根据升级提示决定是否从空白配置开始。[官方升级说明](https://openwrt.org/docs/guide-user/installation/generic.sysupgrade)要求事先保存当前镜像、配置备份和恢复办法。

不同路由器恢复原厂系统的方法也不同。能否恢复，取决于原厂启动程序、恢复分区、厂商镜像、TFTP/UART 恢复入口和本机无线校准数据是否仍在。安装前就应查清恢复办法；OpenWrt 的“恢复出厂设置”通常只会清空 OpenWrt 配置，不会自动变回厂商系统。

## <a id="management"></a>OpenWrt 的管理

### 系统环境和软件包

OpenWrt 使用 BusyBox 提供精简命令，默认 shell 是 `ash`，服务由 `procd` 管理，因此不能直接照搬 Bash + systemd 的服务器教程。25.12 使用 `apk` 安装软件包；旧教程中的 `opkg` 命令也不能直接照搬。[官方迁移说明](https://openwrt.org/docs/guide-user/additional-software/opkg-to-apk-cheatsheet)还明确警告不要用 `apk upgrade` 盲目升级整机，应通过 sysupgrade、自动构建升级工具（Attended Sysupgrade）或[官方 Firmware Selector](https://firmware-selector.openwrt.org/) 更新系统。

LuCI、UCI 和 ubus 操作同一套系统配置：

```sh
uci show network
uci show wireless
ubus call system board
ubus call network.interface.lan status
```

[UCI 官方文档](https://openwrt.org/docs/guide-user/base-system/uci)说明了 `/etc/config/*` 的集中配置方式，源码见 [OpenWrt 官方 GitHub 镜像](https://github.com/openwrt/uci)。[ubus 技术文档](https://openwrt.org/docs/techref/ubus)说明了不同服务如何登记状态并互相调用，源码见 [openwrt/ubus](https://github.com/openwrt/ubus)。修改 UCI 后要用 `uci commit` 保存，再重新加载或重启对应服务。

### SSH 服务和访问范围

[Dropbear](https://github.com/mkj/dropbear) 是独立的第三方轻量 SSH 服务，OpenWrt 负责把它接入 UCI、服务管理和防火墙。25.12.5 的[默认配置](https://github.com/openwrt/openwrt/blob/v25.12.5/package/network/services/dropbear/files/dropbear.config#L1-L9)启用端口 22 和密码认证；没有限制监听接口时，它会在路由器的所有地址上等待连接。

默认防火墙允许从 LAN 访问路由器本身，阻止从 WAN 或无线 WAN 访问。因此连接有线 LAN 或本地 AP 的设备可以尝试 SSH，而连接同一个上游 Wi-Fi 的其他设备通常进不来。监听范围和防火墙是两道独立限制；完成公钥验证后，还可以让 Dropbear 只监听 LAN，并关闭 SSH 密码认证。

只要无线 AP 绑定在 LAN，成功连接这个 Wi-Fi 的设备就能访问路由器的 22 端口。如果 Dropbear 仍允许 root 密码登录，对方一旦知道或猜中 root 密码，就会直接获得 OpenWrt 的 root 权限，可以读取配置和凭据、修改防火墙与无线设置、安装软件或接管网络。独立 guest 网络是否能访问 SSH，则取决于该防火墙区域是否允许访问路由器本身。

### <a id="ssh-security"></a>只允许 SSH 密钥登录

先分清两类密钥：

- 路由器首次启动时生成的 Dropbear 主机密钥，用于让电脑确认“连接的是这台路由器”，不能拿来当管理员登录密钥。
- 管理员客户端密钥，由管理电脑保存私钥，并把公钥放进路由器的 `/etc/dropbear/authorized_keys`。

[OpenWrt 官方公钥认证说明](https://openwrt.org/docs/guide-user/security/dropbear.public-key.auth)明确表示：如果管理电脑已经有一对准备给这台路由器使用的客户端密钥，可以直接复用；没有时再用 `ssh-keygen` 生成。官方没有要求每台路由器必须使用不同密钥。

从风险隔离看，为路由器或一组网络设备单独生成 Ed25519 密钥更容易撤销，也不会让一个日常通用私钥同时控制太多机器；每台路由器各用一对密钥隔离最强，但管理成本更高。已有密钥若受保护口令或硬件令牌保护、只在可信设备使用且 ssh-agent 可用，复用也合理。无论选择哪种方式，私钥始终留在管理电脑，只向路由器复制公钥。

AX3000T 当前版本可使用 Ed25519；部分闪存很小的旧设备可能裁掉该算法，应先查看设备页或实测。确定密钥后，上传公钥并强制验证一条不允许密码回退的新连接：

```sh
ssh-keygen -t ed25519 -f ~/.ssh/openwrt-router
cat ~/.ssh/openwrt-router.pub | ssh root@openwrt.lan \
  'umask 077; cat >> /etc/dropbear/authorized_keys; chmod 600 /etc/dropbear/authorized_keys'
ssh -i ~/.ssh/openwrt-router -o IdentitiesOnly=yes \
  -o PasswordAuthentication=no -o BatchMode=yes root@openwrt.lan 'echo key-ok'
```

私钥带保护口令（passphrase）时，先把它加载到 ssh-agent；相关边界见 [SSH 的非交互 agent](ssh.md#agent-noninteractive)。只有看到 `key-ok` 后，才在路由器上执行：

```sh
uci set dropbear.main.DirectInterface='lan'
uci set dropbear.main.PasswordAuth='off'
uci set dropbear.main.RootPasswordAuth='off'
uci commit dropbear
/etc/init.d/dropbear restart
```

25.12.5 的 Dropbear 脚本会把 `DirectInterface='lan'` 转成实际 LAN 网卡，见[接口绑定](https://github.com/openwrt/openwrt/blob/v25.12.5/package/network/services/dropbear/files/dropbear.init#L236-L250)和[认证参数](https://github.com/openwrt/openwrt/blob/v25.12.5/package/network/services/dropbear/files/dropbear.init#L302-L326)。已有系统若没有名为 `main` 的配置节，应先用 `uci show dropbear` 查看真实名称。

关闭 SSH 密码认证不等于删除 root 系统密码；LuCI 和本地恢复仍可使用该密码。

### 指示灯、按键等硬件功能

指示灯、按键、网口交换芯片和无线是否可用，取决于 OpenWrt 是否为这款路由器写好了硬件描述和驱动。受支持的 LED 通常出现在 `/sys/class/leds/`，并通过 `/etc/config/system` 或 LuCI 的 LED Configuration 设置为开机、网络或无线状态灯，详见[官方 LED 配置](https://openwrt.org/docs/guide-user/base-system/led_configuration)。

OpenWrt 可以提供标准状态灯，但不保证复刻厂商固件的全部颜色、动画或专有联动。

## <a id="networking"></a>配置 OpenWr 网络

### 网口和无线接口

WAN 是连接外部网络的一侧，LAN 是自己的内部网络。AP 和 station 则表示无线接口正在做什么：

- AP 广播 SSID，供下游客户端接入；
- station（无线客户端）让路由器连接现有 Wi-Fi；
- station 可以建立无线 WAN 接口（WWAN），再通过路由和 NAT 向 LAN/AP 供网；
- AP 也可以接入现有有线 LAN，成为不做路由的普通无线接入点。

“无线 AP”只说明下游设备通过 Wi-Fi 接入；“桥接”则说明上下游设备是否直接处于同一个局域网，两者不能混为一谈。

### 用 Wi-Fi 作为上网入口

旅行路由和 Wi-Fi 转有线通常采用“连接上游 Wi-Fi → 获得地址 → 经过 WAN 防火墙和 NAT → 提供给 LAN/AP”。关键配置是创建通过 DHCP 获取地址的 WWAN，把无线客户端绑定到它，并把 WWAN 加入启用 NAT 地址转换的 WAN 防火墙区域：

```sh
uci set network.wwan=interface
uci set network.wwan.proto='dhcp'
uci set wireless.upstream.mode='sta'
uci set wireless.upstream.network='wwan'
```

无线设备、SSID、认证方式和凭据按上游网络填写，随后保存配置并重新加载网络与无线。双频设备可用一个频段连接上游，另一个频段提供本地 AP；共用同一频段也能工作，但吞吐和重连过程会互相影响。

### <a id="wireless-auth"></a>连接不同类型的 Wi-Fi

| 上游网络 | 认证发生位置 | OpenWrt 侧要求 |
|---|---|---|
| 开放网络或 WPA2/WPA3 Personal | 无认证或预共享密钥 | 默认无线客户端能力 |
| WPA2-Enterprise | 路由器的无线认证程序与 AP/RADIUS 服务器认证 | 完整 EAP 参数和完整版本 wpad |
| Captive Portal（网页认证） | 关联和 DHCP 后，由浏览器或登录脚本完成认证 | HTTP 跳转、登录页面处理和可能的 MAC 策略 |

默认镜像常带精简版 `wpad-basic-mbedtls`，足以处理普通密码网络。PEAP、TTLS、TLS 等企业认证需要完整版本 wpad；25.12.5 的 [hostapd 包定义](https://github.com/openwrt/openwrt/blob/v25.12.5/package/network/services/hostapd/Makefile#L269-L302)显示 `wpad-openssl` 可以让路由器作为完整的 EAP 认证客户端。

先模拟替换事务，再决定是否执行：

```sh
apk add --simulate wpad-openssl
apk add wpad-openssl
```

只有模拟结果显示可以一次替换精简版 wpad 并补齐依赖时，才执行第二条；不要先手工删除当前软件包。

Captive Portal 通常由路由器后面的电脑或手机打开登录网页完成。上游网络看到的往往是路由器 WWAN 的地址和 MAC，因此认证后多个下游设备可能共享连接；具体结果取决于登录系统是否绑定账号、IP、MAC、设备数量或应用特征。Travelmate 可以检测网页认证、管理多个上游 Wi-Fi 并调用外部登录脚本；厂商旅行路由器还可能提供专用登录模式和 MAC 地址克隆。

### 向下游供网：NAT 还是桥接

路由 + NAT 会建立自己的下游子网，对上游要求最低，也能把公共网络与本地设备隔离。它适合旅行路由、Wi-Fi 转有线和大多数不受控上游。

WDS/四地址模式会把两端接成同一个局域网，保留下游设备的 MAC、广播数据和上游 DHCP，但要求上游 AP 与无线客户端的 WDS 实现兼容。官方说明见[无线 WDS 桥接](https://openwrt.org/docs/guide-user/network/wifi/wifiextenders/wds)。

上游不支持 WDS 时，[`relayd` 中继](https://openwrt.org/docs/guide-user/network/wifi/relay_configuration)可以让下游看起来像在同一网段，但它不是真正的透明桥接，配置和排障也更复杂。只有确实需要局域网发现、上游直接分配地址或所有设备处于同一个局域网时，才需要从 NAT 转向桥接。

### 判断无线连接是否稳定

信号格或扫描结果只能说明接收到 AP 周期广播信号的强度。判断上游 Wi-Fi 是否稳定时，还应观察信号强度（RSSI）、噪声、协商速率、重传、上下行吞吐、连续丢包和重启后的自动重连。

建筑玻璃、金属窗框和墙体可能让几十厘米的位置变化产生明显差异。先在安全位置测试不同频段和摆放点；只有普通路由器在最佳位置仍出现上传差、频繁掉线或高重传时，才说明需要定向 CPE 或改变布点。

### 普通路由器信号不够时再考虑定向 CPE

OpenWrt 可以改变网络模式，但不能凭软件产生天线增益。若普通路由器只有在窗边某个位置才能稳定连接，应先用上述指标判断问题来自建筑衰减、干扰还是链路距离。

定向 CPE 是带定向天线的无线终端。远端已有普通 AP 时，本地只需一台能作为 Wi-Fi 客户端的定向 CPE，不必在远端再安装配对设备。天线要朝向 AP 所在方向，并同时改善接收和回传。选择时还要核对频段、企业认证能力、网口速度、PoE 供电电压和恢复方式；CPE 可以运行厂商系统、RouterOS 或 OpenWrt，不必为了改善无线信号强行使用 OpenWrt。

## <a id="ax3000t"></a>小米 AX3000T 案例

本节只记录 AX3000T 独有的硬件差异和一次实际安装结果。首次安装与升级、SSH 安全、无线认证和 NAT/桥接原理分别见[安装 OpenWrt](#installation)、[只允许 SSH 密钥登录](#ssh-security)和[配置 OpenWrt 网络](#networking)。

### 先确认是哪一版 AX3000T

RD03 国行和 RD23 国际版使用 MediaTek MT7981B 主芯片，官方 OpenWrt 支持。RD03v2 改用 Qualcomm 平台，当前不受支持；包装 SKU `DVB4510CN` 或条码结尾 `706330` 可用于识别。不要把 RD03/RD23 镜像写入 RD03v2。[OpenWrt Wiki 的固定修订](https://openwrt.org/toh/xiaomi/ax3000t?rev=1780820319)记录了这组边界。

原厂固件版本决定能否在不拆机的情况下，利用原厂网页接口开启 SSH：

| 机型与固件 | 设备页记录的入口 |
|---|---|
| RD03 1.0.47 | `misystem/arn_switch` |
| RD03 1.0.64、1.0.84、1.0.90、1.0.91、1.0.98 | `xqsystem/start_binding` |
| RD03 1.0.106 | 无已知 API；需降级或 UART |
| RD23 1.0.31、1.0.49、1.0.55、1.0.76 | `xqsystem/start_binding` |
| RD23 1.0.90、1.0.91、1.0.92、1.0.97、1.0.103、1.0.104 | `xqsystem/get_icon` |

25.12.5 已支持设备页列出的 ESMT、Winbond、Foresee 闪存芯片，以及 MT7531AE、AN8855 网口交换芯片。安装前仍应读取机器里的真实硬件信息，不按商品名猜测。

### Windows 只用一根网线如何连接

小米原厂固件会自动判断四个网口是 WAN 还是 LAN。电脑单线直连时，路由器可能把该端口当作 WAN，路由器和电脑都在等待对方分配地址，Windows 最后只得到 `169.254.x.x` 自分配地址。

优先换插其他端口或临时连接原厂 Wi-Fi。必须维持有线连接时，Windows 可临时运行一个只给这台路由器分配地址的 DHCP 服务；有线口不设默认网关，也不启用 Windows 网络共享（ICS）或网络桥接。电脑休眠或 DHCP 程序停止后，临时地址可能失效。

复杂 PowerShell 应落成 `.ps1` 并按 [Windows 命令调用](windows.md#invocation)执行。

### 安装前检查和备份

取得 SSH 后，先确认当前从哪套原厂系统启动、闪存分区编号，以及准备写入的备用槽是否正在使用：

```sh
cat /proc/cmdline
cat /proc/mtd
ubinfo -a
```

实际案例备份了 BL2、Nvram、Bdata、Factory、FIP、两个保存原厂系统的 UBI 槽、保存原厂配置的 overlay、data 和 KF，共十个关键分区，并在路由器与电脑两端交叉校验。`Bdata`、`Factory`、`Nvram` 和无线校准数据只能用于原设备恢复。

正在使用的原厂配置区 overlay/data 连续读取两次，两个文件的校验值一致后才接受。老 Dropbear 或临时 OpenWrt 没有 SFTP 服务时，Windows OpenSSH 使用 `scp -O` 兼容旧式 SCP 传输。

### 保留小米原厂启动程序的安装方法

案例保留小米原厂 bootloader（路由器上电后最先运行的启动程序），采用官方 25.12.5 的 stock-layout 分区方案。第一次先写入临时 OpenWrt 镜像，再安装正式的 squashfs sysupgrade 镜像；没有使用会更换启动布局的 `ubootmod` 镜像。

根据当前活动槽，只写另一槽：

| 当前启动标记 | 临时镜像写入位置 | 下一启动槽的两个变量 |
|---|---|---|
| `firmware=1 mtd=ubi1` | `/dev/mtd8` | `0` / `0` |
| `firmware=0 mtd=ubi` | `/dev/mtd9` | `1` / `1` |

关键写入命令只有：

```sh
ubiformat <未使用的-mtd-分区> -y -f /tmp/<临时-openwrt-镜像.ubi>
```

写入成功后，按官方设备页为目标槽设置 `flag_boot_rootfs` 和 `flag_last_success`。这两个变量告诉原厂启动程序下次进入哪个槽；还要启用等待启动和 UART 恢复相关变量，标记启动成功，并清零两个尝试失败计数。每个变量都回读无误后才重启，不能只修改其中一部分。

临时系统必须确认设备型号正确、系统确实运行在内存中的 initramfs 模式、网口交换芯片正常、三个 LAN、一个 WAN、两张无线电和 LuCI 均存在，再按[安装 OpenWrt](#installation)检查并安装正式系统。

### 正式安装后还能怎样恢复原厂

临时阶段只覆盖没有启动的备用槽，当前原厂系统、原厂配置区 overlay 和 data 仍在。正式安装会把原厂 `mtd8` 改作 OpenWrt 内核区域，并把原厂 `mtd9 + mtd10 + mtd11` 合并成新的持久数据区域，见 [AX3000T DTS](https://github.com/openwrt/openwrt/blob/v25.12.5/target/linux/mediatek/dts/mt7981b-xiaomi-mi-router-ax3000t.dts#L18-L34)和[升级脚本](https://github.com/openwrt/openwrt/blob/v25.12.5/target/linux/mediatek/filogic/base-files/lib/upgrade/platform.sh#L48-L96)。

因此正式安装后，不能只改一个启动槽变量就完整回到原厂系统。恢复依赖这台机器自己的备份，以及 AX3000T 实际可用的 TFTP 网络恢复或 UART 串口恢复。设备页仍有未填写的 TFTP 参数时，不从其他小米型号照搬。

### 这台设备的实测结果

本次设备为 RD03、原厂固件 1.0.64、MT7981 主芯片、MT7531AE 网口交换芯片和 128 MiB NAND 闪存。官方 25.12.5 按保留原厂启动程序的两阶段方式安装后：

- 正式系统使用只读的 squashfs 基础系统，并叠加可写的 UBIFS 配置层，可写空间约 60.7 MiB；
- NAND 没有坏块或读写错误，重启后配置保持；
- 靠近电源的端口为 WAN，三个中间口为 LAN；
- 两张无线电、LuCI、SSH 和端口均正常；
- 已实现个人热点 → 5 GHz 无线客户端 → WWAN/NAT → 有线 LAN，重启后自动恢复；
- 短测信号约 `-51 dBm`，协商速率约 `1200.9 Mbit/s`，公网和 DNS 正常；
- 已设置 root 密码并拒绝空密码 SSH；只允许 SSH 密钥登录的加固尚需按通用章节完成；
- 企业认证和 Captive Portal 尚未在该上游环境实际验收，因此文中的支持结论来自官方功能与软件包，不把它写成案例实测。

AX3000T 的公共设备树定义了蓝色和黄色状态灯：启动、failsafe 和升级使用黄色，正常运行使用蓝色，见[固定版本源码](https://github.com/openwrt/openwrt/blob/v25.12.5/target/linux/mediatek/dts/mt7981b-xiaomi-mi-router-common.dtsi#L9-L16)和[GPIO LED 定义](https://github.com/openwrt/openwrt/blob/v25.12.5/target/linux/mediatek/dts/mt7981b-xiaomi-mi-router-common.dtsi#L44-L57)。这些是标准 Linux 状态灯，不保证复刻小米原厂的全部动画。

这次个人热点短测证明了 Wi-Fi 转有线 NAT 和持久重连，但不能替代目标远距离网络的半小时丢包、上下行吞吐和数小时稳定性测试；是否需要定向 CPE 仍应由目标链路实测决定。
