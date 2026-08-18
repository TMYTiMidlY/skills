# OpenWrt 设备管理

OpenWrt 是面向路由器和嵌入式网络设备的 Linux 发行版。本文说明设备支持、安装与恢复、系统维护、网络配置、无线链路测量和监控，最后以小米 AX3000T 记录设备专属的刷写与恢复边界。把外部 Wi-Fi 作为上游、经网线连接下游 AP、理解通用无线链路或选择定向 CPE 时，见 [外部 Wi-Fi 接入本地网络](external-wifi-access.md)。

## <a id="system"></a>系统组成与设备支持

本节先说明 OpenWrt 的系统边界和主要组件，再说明设备支持为什么必须落实到精确型号和硬件版本。

### 系统组件

[OpenWrt 25.12.5 的项目说明](https://github.com/openwrt/openwrt/blob/v25.12.5/README.md#L3-L10)将其定义为面向嵌入式设备的 Linux 操作系统。通过 SSH 登录路由器时，管理的是设备上直接运行的 OpenWrt 系统。

OpenWrt 提供 Linux 内核、可写配置层和软件包管理，可以组合 DHCP、DNS、防火墙、VLAN、多 WAN、VPN、无线 AP、无线客户端和策略路由。常见组件的分工如下：

- [OpenWrt 主项目](https://git.openwrt.org/openwrt/openwrt/tree/?h=v25.12.5)：Linux 发行版、构建系统、目标设备和基础软件包。
- [LuCI](https://git.openwrt.org/project/luci/tree/?id=128a7812f4be233c5dd7f7466f534fd888785caf)：OpenWrt 的网页管理界面。
- [UCI](https://git.openwrt.org/project/uci/tree/?id=66127cd76c5d0bd46d5a90302cc6110f53a4e2f8)：OpenWrt 的统一配置系统，持久配置通常位于 `/etc/config/*`。
- [ubus](https://git.openwrt.org/project/ubus/tree/?id=24864e7840b3a02a9ef76284a373f6b2f00b8a9b)：OpenWrt 的进程通信和服务调用总线。
- [Dropbear 2025.89](https://github.com/mkj/dropbear/tree/DROPBEAR_2025.89)：第三方轻量 SSH 项目；OpenWrt 维护自己的[集成配置](https://github.com/openwrt/openwrt/tree/v25.12.5/package/network/services/dropbear)。

OpenWrt 的自由度来自完整的网络操作系统。设备实际能使用哪些功能，仍取决于硬件支持状态、驱动、闪存和内存。

### 设备支持范围

OpenWrt 镜像必须匹配精确型号和硬件版本。相同商品名可能使用不同的 SoC、闪存芯片、网口交换芯片或无线芯片；其中一个版本受支持，不代表所有同名机器都能使用相同镜像。

> SoC（System on Chip，系统级芯片）是路由器的主芯片，通常集成 CPU、网络处理和部分硬件控制功能。SoC 决定基础硬件平台，但不能单独确定镜像：使用同一 SoC 的设备仍可能采用不同的闪存、交换芯片、无线芯片和分区布局。

选购或安装前至少确认：

- OpenWrt 官方的 [Table of Hardware](https://openwrt.org/toh/start) 或 [Firmware Selector](https://firmware-selector.openwrt.org/) 中存在这款设备的准确条目；
- 当前稳定版支持该硬件版本，而不只是开发分支或论坛补丁；
- 闪存、内存、网口数量和速率满足用途；OpenWrt 的 [8/64 警告](https://openwrt.org/supported_devices/864_warning?rev=1766225423)将 16 MiB 闪存和 64 MiB 内存视为不自行裁剪镜像时的最低参考，并指出更低配置可能不稳定或失去后续支持；
- 设备页给出可执行的首次安装方法和故障恢复入口；
- 无线、网口交换芯片、指示灯、按键和硬件加速等设备功能已有相应驱动。

确认支持状态后，还要阅读设备页的安装与恢复说明。若安装依赖原厂固件漏洞，升级原厂固件可能会关闭该入口，因此操作方法必须同时匹配设备型号和原厂固件版本。具体入口统一见[安装、升级与恢复](#installation)。

### <a id="hardware"></a>设备角色与硬件条件

设备选择由角色、接口、驱动支持和恢复能力共同决定；规格高低本身不能替代这些边界。

不同角色关注的硬件条件不同：

- 主路由涉及 WAN/LAN 速率、硬件加速、智能队列管理（SQM）和长期稳定性；
- 无线 AP 涉及无线驱动、频段、空间流数量和安装位置；
- 旅行路由器涉及无线 WAN、网页认证（Captive Portal）、MAC 地址克隆、便携供电和多个上游网络切换；
- 实验平台涉及串口、恢复分区、可更换存储、SFP、M.2 和无线模块；
- x86 软路由涉及 CPU、网卡驱动和存储，无线功能可由独立 AP 提供。

**设备形态。**常见设备可以按出厂系统和硬件形态区分：

| 形态 | 例子 | 安装与维护边界 | 来源 |
|---|---|---|---|
| OpenWrt 原生设备 | OpenWrt One | 出厂预装 OpenWrt 和 LuCI；NAND 用于正常系统，NOR 用于独立恢复，并带 USB-C 串口；物理网口为一个 WAN 和一个 LAN | [OpenWrt One 设备页](https://openwrt.org/toh/openwrt/one?rev=1785956951) |
| 厂商维护的 OpenWrt 分支 | GL.iNet Flint 2 | 原厂系统是 OpenWrt 分支；可从原厂网页写入官方 sysupgrade 镜像，U-Boot 恢复网页不依赖当前系统 | [Flint 2 设备页](https://openwrt.org/toh/gl.inet/gl-mt6000?rev=1784246533) |
| 旅行路由器 | GL.iNet Beryl AX 等 | 把现有 Wi-Fi 作为上游，再提供自己的 LAN 和 AP；网页认证、企业认证和 MAC 策略随型号与固件变化 | [固件 4 Repeater 文档](https://docs.gl-inet.com/router/en/4/interface_guide/internet_repeater/) |
| 开发板型路由器 | Banana Pi BPI-R4 | 可从 SPI-NAND、eMMC 或 microSD 启动，并提供 SFP 和可选无线模块；机箱、模块和安装流程需要自行组合 | [BPI-R4 设备页](https://openwrt.org/toh/sinovoip/bananapi_bpi-r4?rev=1786132584) |
| x86 主机 | 通用 Intel / AMD 主机 | 将 combined 磁盘镜像写入硬盘或 SSD；需要自行核对网卡、存储和其他驱动 | [x86 安装文档](https://openwrt.org/docs/guide-user/installation/openwrt_x86?rev=1763692173) |
| 上游支持的消费路由器 | Table of Hardware 中的具体型号 | 硬件版本、首次安装和恢复方法都以设备页为准 | [Table of Hardware](https://openwrt.org/toh/start) |

厂商系统和官方 OpenWrt 即使共享代码基础，也可能使用不同内核、驱动和功能界面，不能把一方的功能状态直接套到另一方。

**旅行路由器。**旅行路由器把外部 Wi-Fi 作为上游，再建立自己控制的 LAN。这个角色要求设备支持 station、WWAN、防火墙和上游认证；若还要向本地广播 Wi-Fi，需要核对无线电数量和并发模式。完整的数据路径、认证和链路测量见 [外部 Wi-Fi 接入本地网络](external-wifi-access.md)。

## <a id="installation"></a>安装、升级与恢复

首次安装、系统升级和故障恢复属于同一固件生命周期，但使用的镜像、前置条件和失败边界不同。

### 首次安装方法

不同型号第一次安装 OpenWrt 的方法不同，没有一套通用命令。先在 [Table of Hardware](https://openwrt.org/toh/start) 或 [Firmware Selector](https://firmware-selector.openwrt.org/) 找到准确型号，再按照设备页给出的镜像、网口、IP 地址、按键时序和恢复方法操作。[通用安装说明](https://openwrt.org/docs/guide-user/installation/generic.flashing?rev=1631788605)只用于理解常见入口，不能替代设备页。

常见入口包括：

- 在原厂网页中上传设备页指定的首次安装镜像；
- 进入 bootloader（启动程序）提供的恢复网页、TFTP、串口或其他恢复环境；
- 通过厂商提供的 SSH、开发模式或解锁接口取得写入权限；
- 利用设备页明确记录的原厂固件漏洞取得 SSH，再备份分区并写入镜像；
- 通过 UART 串口加载临时系统或直接写入闪存；
- 将镜像写入硬盘、SSD、SD 卡或 eMMC，再从该存储设备启动。

不要因为另一款设备使用相同 SoC 就照搬分区号、启动变量或恢复文件。除非设备页明确要求，否则不要修改 bootloader；出现读写错误、闪存纠错（ECC）错误、镜像校验不一致或兼容性错误时应立即停止。

### 镜像类型

镜像名称表示构建时预定的用途，但设备页始终具有最终决定权：

| 镜像类型 | 通常用途 | 例外与边界 | 来源 |
|---|---|---|---|
| `factory` | 从厂商系统第一次安装 OpenWrt | 只有设备页明确要求时使用；并非所有设备都按此命名 | [sysupgrade 命令行文档](https://openwrt.org/docs/guide-user/installation/sysupgrade.cli?rev=1786636501) |
| `sysupgrade` | 升级已经运行的 OpenWrt | 部分设备也用它完成首次安装，例如 Flint 2 | [sysupgrade 命令行文档](https://openwrt.org/docs/guide-user/installation/sysupgrade.cli?rev=1786636501)、[Flint 2 设备页](https://openwrt.org/toh/gl.inet/gl-mt6000?rev=1784246533) |
| `combined` | x86 等平台的整盘镜像，包含启动和系统分区 | 首次安装与升级通常使用同一文件系统类型和启动方式的 combined 镜像 | [sysupgrade 命令行文档](https://openwrt.org/docs/guide-user/installation/sysupgrade.cli?rev=1786636501) |

镜像文件名是设备构建流程的结果，不应仅根据“第一次安装”或“升级”自行推断。

### <a id="system-upgrade"></a>系统升级

sysupgrade 会替换 OpenWrt 系统和 Linux 内核。升级前应完成：

1. 用 `ubus call system board` 核对设备 profile（官方构建条目）、当前版本、目标平台和根文件系统类型。
2. 阅读目标版本的发行说明和设备页，确认能否保留现有配置。
3. 保存配置备份、已安装软件包清单，以及当前版本的可重新安装镜像。
4. 将目标镜像放入 `/tmp`，确认 RAM 足够，并把镜像散列与官方 `sha256sums` 对照。

下面的命令只读取状态或验证镜像，不会执行升级：

```sh
ubus call system board
free
sha256sum /tmp/<sysupgrade-image>
sysupgrade -T /tmp/<sysupgrade-image>
```

确认设备、散列和 `sysupgrade -T` 都无误后，下面的命令才会真正写入固件：

```sh
sysupgrade -v /tmp/<sysupgrade-image>
```

`-T` 是只验证不写入的选项，`-v` 只是增加输出详细度；没有 `-T` 时，命令会继续执行升级，见 [25.12.5 的 sysupgrade 参数](https://github.com/openwrt/openwrt/blob/v25.12.5/package/base-files/files/sbin/sysupgrade#L39-L60)。只有明确要丢弃旧配置时才加 `-n`。

“保留设置”只会保存 sysupgrade 选定的配置文件，不会保留所有后来安装的软件包或任意数据文件。[sysupgrade 升级说明](https://openwrt.org/docs/guide-user/installation/generic.sysupgrade?rev=1786216890)记录了配置、软件包和数据文件的边界。执行升级时，sysupgrade 会[关闭现有 shell 会话](https://github.com/openwrt/openwrt/blob/v25.12.5/package/base-files/files/sbin/sysupgrade#L428-L444)；连接断开本身不能证明失败，应等待设备重新启动后再检查版本、存储和网络。

### 配置与恢复资料

升级和风险操作前应保存配置备份、已安装软件包清单、当前可重新安装镜像，以及设备页中的恢复入口。需要保留原厂系统的设备还应备份 bootloader、无线校准数据和设备专属分区，并在另一台机器上验证文件长度与散列。

### 故障恢复

“恢复出厂设置”、重新安装 OpenWrt 和恢复厂商系统是三件不同的事：

- OpenWrt 的恢复出厂设置通常只清空 OpenWrt 配置；
- 重新安装 OpenWrt 需要设备支持的 sysupgrade、failsafe（故障安全模式）、bootloader 恢复或串口路径；
- 恢复厂商系统取决于原厂 bootloader、恢复分区、厂商镜像、本机校准数据和设备专属恢复入口是否仍可用。

安装或升级前应保存配置备份、当前可用镜像和设备恢复方法。需要备份 bootloader、无线校准数据或原厂分区的设备，还应在写入前完成备份并验证可读性。

## <a id="management"></a>系统配置与维护

本节区分命令环境、持久配置、运行时服务和远程访问，避免把 LuCI、UCI、ubus 和 SSH 当成同一层能力。

### 命令环境与软件包

OpenWrt 25.12.5 的 [root 登录 shell](https://github.com/openwrt/openwrt/blob/v25.12.5/package/base-files/files/etc/passwd#L1)是 `/bin/ash`，[BusyBox](https://github.com/openwrt/openwrt/blob/v25.12.5/package/utils/busybox/Makefile#L8-L15)提供精简的核心命令，[procd](https://github.com/openwrt/openwrt/blob/v25.12.5/package/system/procd/Makefile#L40-L53)负责系统进程管理，因此不能直接照搬 Bash + systemd 的服务器教程。

25.12 使用 `apk` 管理软件包；旧教程中的 `opkg` 命令不能直接照搬。[apk 迁移说明](https://openwrt.org/docs/guide-user/additional-software/opkg-to-apk-cheatsheet?rev=1774185420)明确警告不要用 `apk upgrade` 批量升级整机，安全的整机升级路径是 LuCI Attended Sysupgrade、`owut` 或 [Firmware Selector](https://firmware-selector.openwrt.org/)。

安装附加包时，应使用与当前 OpenWrt 版本和架构匹配的签名仓库或定制镜像；软件包 revision、依赖和签名不一致时应停止，而不是强制安装。

### LuCI、UCI 与 ubus

LuCI 是网页管理界面，通常通过 UCI 写入持久配置；UCI 管理 `/etc/config/*`；ubus 则让服务注册对象、查询运行状态并调用方法。三者相互配合，但不是同一层接口：

```sh
uci show network
uci show wireless
ubus call system board
ubus call network.interface.lan status
```

[UCI 文档](https://openwrt.org/docs/guide-user/base-system/uci?rev=1781542470)说明了集中配置和 `uci commit` 的语义；25.12.5 的[软件包定义](https://github.com/openwrt/openwrt/blob/v25.12.5/package/system/uci/Makefile#L14-L17)锁定官方 Git 服务器中的 [UCI `66127cd`](https://git.openwrt.org/project/uci/tree/?id=66127cd76c5d0bd46d5a90302cc6110f53a4e2f8)。[ubus 文档](https://openwrt.org/docs/techref/ubus?rev=1734385933)说明了服务注册、状态查询和方法调用；25.12.5 的[软件包定义](https://github.com/openwrt/openwrt/blob/v25.12.5/package/system/ubus/Makefile#L6-L12)锁定 [ubus `24864e7`](https://git.openwrt.org/project/ubus/tree/?id=24864e7840b3a02a9ef76284a373f6b2f00b8a9b)。

用 `uci set` 等命令修改配置后，要用 `uci commit <package>` 写入持久配置，再通过对应 init 脚本重新加载或重启服务。

### Dropbear SSH

OpenWrt 默认使用 Dropbear 提供 SSH。访问范围同时受 Dropbear 监听位置和防火墙区域控制。

#### 监听范围与防火墙

[Dropbear 2025.89](https://github.com/mkj/dropbear/tree/DROPBEAR_2025.89)是独立的第三方轻量 SSH 服务，OpenWrt 负责把它接入 UCI、procd 和防火墙。25.12.5 的[默认配置](https://github.com/openwrt/openwrt/blob/v25.12.5/package/network/services/dropbear/files/dropbear.config#L1-L9)启用端口 22、普通密码认证和 root 密码认证；没有限制接口时，Dropbear 会监听设备上的可用地址。

25.12.5 的[默认防火墙](https://github.com/openwrt/openwrt/blob/v25.12.5/package/network/config/firewall/files/firewall.config#L1-L24)允许 LAN 访问路由器本身，并拒绝 WAN 入站。无线 WAN 只有在归入 WAN 防火墙区域后才遵循这组规则。监听范围和防火墙是两道独立限制。

绑定到 LAN 的无线 AP 客户端与有线 LAN 客户端处于同一管理边界，默认可以尝试连接 22 端口。如果 Dropbear 仍允许 root 密码登录，知道 root 密码的 LAN 客户端就能取得系统管理权限。guest（访客）网络能否访问 SSH，取决于其防火墙区域是否允许访问路由器本身。

#### <a id="ssh-security"></a>公钥认证与密码认证

SSH 涉及两类不同密钥：

- 路由器首次启动时生成的 Dropbear 主机密钥，用于让客户端确认服务器身份；
- 管理电脑持有的客户端私钥及其公钥，其中私钥留在管理电脑，公钥写入路由器的 `/etc/dropbear/authorized_keys`。

[OpenWrt 公钥认证文档](https://openwrt.org/docs/guide-user/security/dropbear.public-key.auth?rev=1771861590)允许复用管理电脑上已有、准备给该路由器使用的密钥，也可以新建密钥。复用同一密钥的管理成本较低，但密钥泄露会影响更多设备；按设备或设备组拆分密钥可以缩小影响范围，但需要维护更多密钥。

25.12.5 的 Dropbear 配置在非 `SMALL_FLASH` 构建中[默认启用 Ed25519](https://github.com/openwrt/openwrt/blob/v25.12.5/package/network/services/dropbear/Config.in#L879-L889)；小闪存构建应先确认实际支持的算法。确定密钥类型后，上传公钥并强制验证一条不允许密码回退的新连接：

```sh
ssh-keygen -t ed25519 -f ~/.ssh/openwrt-router
cat ~/.ssh/openwrt-router.pub | ssh root@openwrt.lan \
  'umask 077; cat >> /etc/dropbear/authorized_keys; chmod 600 /etc/dropbear/authorized_keys'
ssh -i ~/.ssh/openwrt-router -o IdentitiesOnly=yes \
  -o PasswordAuthentication=no -o BatchMode=yes root@openwrt.lan 'echo key-ok'
```

私钥带保护口令（passphrase）时，先把它加载到 ssh-agent；常驻 agent 和非交互解锁由 `software` skill 的 SSH 能力覆盖。只有看到 `key-ok` 后，才在路由器上执行：

```sh
uci set dropbear.main.DirectInterface='lan'
uci set dropbear.main.PasswordAuth='off'
uci set dropbear.main.RootPasswordAuth='off'
uci commit dropbear
/etc/init.d/dropbear restart
```

25.12.5 的 Dropbear 脚本会把 `DirectInterface='lan'` 转成实际 LAN 网卡，见[接口绑定](https://github.com/openwrt/openwrt/blob/v25.12.5/package/network/services/dropbear/files/dropbear.init#L197-L250)和[认证参数](https://github.com/openwrt/openwrt/blob/v25.12.5/package/network/services/dropbear/files/dropbear.init#L302-L326)。已有系统若没有名为 `main` 的配置节，应先用 `uci show dropbear` 查看真实名称。

关闭 Dropbear 密码认证不会删除 `/etc/shadow` 中的 root 密码，LuCI 等使用系统密码的入口仍可继续使用它。

### 指示灯与硬件功能

指示灯是否可用，取决于设备树和驱动是否描述了对应硬件。受支持的 LED 通常出现在 `/sys/class/leds/`，并通过 `/etc/config/system` 或 LuCI 的 LED Configuration 绑定启动、网络和无线触发器，详见 [LED 配置文档](https://openwrt.org/docs/guide-user/base-system/led_configuration?rev=1765317685)。

OpenWrt 可以提供标准状态灯，但不保证复刻厂商固件的全部颜色、动画或专有联动。

## <a id="network-surfaces"></a>网络配置接口

OpenWrt 把物理接口、逻辑网络、防火墙区域和无线配置分开管理。理解这几层可以避免把“无线客户端”“WAN 角色”和“某个物理网口”当成同一个对象。

### LAN、WAN、WWAN 与防火墙区域

OpenWrt 把网络对象拆成几个层次：

- **LAN**（local area network，本地网络）是终端接入的一侧，通常由 OpenWrt 提供 DHCP 和默认网关。
- **WAN**（wide area network，上游网络）是通往外部网络的一侧；它是逻辑角色，不等于固定的物理网口。
- **WWAN**（wireless WAN，无线 WAN）是由 Wi-Fi 客户端连接承载的 WAN 接口。
- **防火墙区域**把一个或多个接口归为同一安全边界，并决定入站、转发和 NAT。

`/etc/config/network` 定义接口和地址获取方式，`/etc/config/firewall` 决定区域、转发和 NAT。把外部 Wi-Fi 变成网线输出时，通用数据路径见 [设备角色与数据路径](external-wifi-access.md#architecture)，OpenWrt 配置流程见 [OpenWrt 上的链路配置](external-wifi-access.md#configuration)。

### <a id="lan-egress"></a>局域网流量的统一出口

OpenWrt 可以让整个局域网共用 VPN 或代理出口，因为终端通常已经把它当作默认网关；路由器可以在转发过程中选择出口、修改路由或把流量交给本机代理程序。这不是一个单独的“全局代理”开关，而是软件包、隧道接口、防火墙和策略路由共同实现的能力。

需要先区分三种做法：

| 做法 | 终端是否配置代理 | 路由器承担的工作 | 主要边界 |
|---|---|---|---|
| VPN 隧道出口 | 不需要 | 把全部或选定终端的 IP 流量路由到 WireGuard、OpenVPN 等隧道 | 上游必须提供 VPN；是否覆盖 IPv6、DNS 和故障回退取决于完整配置 |
| 显式 HTTP/SOCKS 代理 | 需要 | 在路由器上提供代理监听端口 | 未配置代理的应用仍走普通 WAN，不等于整个局域网已被接管 |
| 透明代理或 TUN | 通常不需要 | 用防火墙、策略路由或 TUN 把转发流量交给本机代理核心 | 必须分别处理 TCP、UDP、DNS、IPv4、IPv6、本地网段绕行和代理失效行为 |

[OpenWrt 的 WireGuard 客户端文档](https://openwrt.org/docs/guide-user/services/vpn/wireguard/client?rev=1780858975)使用 `0.0.0.0/0` 和 `::/0` 建立全流量路由；[PBR 文档](https://openwrt.org/docs/guide-user/network/routing/pbr_app?rev=1765197438)则示范把整个 LAN 子网送到指定 VPN。官方 packages 仓库中的 [`pbr`](https://github.com/openwrt/packages/blob/af41897f31a4b5405acb0ca9d7ecdd357d193a9d/net/pbr/README.md#L7-L15)还可以按 IP、MAC、端口、协议或域名选择 WAN、VPN 或隧道。

透明代理需要额外的代理核心和接管规则。OpenWrt 的官方 packages 仓库包含依赖 `kmod-tun` 的 [`sing-box`](https://github.com/openwrt/packages/blob/af41897f31a4b5405acb0ca9d7ecdd357d193a9d/net/sing-box/Makefile#L28-L46)，而 OpenWrt 自身的 [`fw4`/nftables](https://openwrt.org/docs/guide-user/firewall/overview?rev=1755099165)负责包分类、NAT 和转发规则；安装代理程序本身并不会自动完成整网接管。Mihomo 的显式代理、TUN 路由、DNS 和泄漏边界见 [TUN 与系统路由](mihomo.md#tun-routing)。

其他路由器能否提供同样能力，主要取决于固件，不只取决于硬件。厂商固件若没有可安装软件包、TUN 设备、自定义防火墙规则、策略路由和服务管理入口，通常只能使用厂商预置的 VPN 或代理功能；支持 VPN client 或策略路由的型号则可能覆盖其中一部分。OpenWrt 的[软件包管理](https://openwrt.org/docs/guide-user/additional-software/managing_packages?rev=1769013285)和可配置网络栈，正是它与这类封闭固件的主要差别。

### <a id="wireless-wpad"></a>无线配置与 wpad

`/etc/config/wireless` 中常见的对象是：

- **radio**：一张物理无线电，例如 2.4 GHz 或 5 GHz；
- **`wifi-iface`**：运行在 radio 上的一条无线配置；
- **`mode='ap'`**：把这条 `wifi-iface` 映射为 AP 角色；
- **`mode='sta'`**：把这条 `wifi-iface` 映射为 station 角色。

AP、station、路由和桥接的通用关系，以及共享同一无线电时的影响，见 [设备角色与数据路径](external-wifi-access.md#architecture)。OpenWrt 能否在同一 radio 上并发这些模式，取决于驱动和硬件。

**wpad** 是 OpenWrt 打包的无线认证组件，同时包含 hostapd（主要服务 AP 模式）和 wpa_supplicant（主要服务 station 模式）的能力。25.12.5 的 [wpad 包定义](https://github.com/openwrt/openwrt/blob/v25.12.5/package/network/services/hostapd/Makefile#L269-L320)区分 basic 和 full 变体：`wpad-basic-mbedtls` 等精简变体覆盖普通 Personal 网络；PEAP、TTLS、TLS、MSCHAPv2 等企业认证方法需要 `wpad-openssl`、`wpad-mbedtls` 或 `wpad-wolfssl` 等完整变体。

替换 wpad 前先模拟软件包事务。下面以 `wpad-openssl` 为例：

```sh
apk add --simulate wpad-openssl
apk add wpad-openssl
```

只有模拟结果显示当前 wpad 变体、依赖和 `hostapd-common` 能在同一事务中形成匹配版本时，才执行第二条命令；不要先手工删除当前 wpad。若事务牵涉无关核心包或版本不一致，应停止并改用匹配当前 OpenWrt 版本的签名仓库或定制镜像。

PEAP/MSCHAPv2 的最小 UCI 关系如下，账号和密码应通过受控输入写入，避免进入命令历史：

```sh
uci set wireless.enterprise.encryption='wpa2'
uci set wireless.enterprise.eap_type='peap'
uci set wireless.enterprise.auth='MSCHAPV2'
uci set wireless.enterprise.identity='<identity>'
uci set wireless.enterprise.password='<password>'
```

服务器证书还需要 `ca_cert` 及域名限制，或经过验证的服务器证书 pin。完整认证流程、缓存和漫游边界见 [通过上游认证](external-wifi-access.md#authentication)和[理解无线链路](external-wifi-access.md#radio-metrics)。

## <a id="link-measurement"></a>无线链路测量与排查

无线指标的含义和漫游机制见 [理解无线链路](external-wifi-access.md#radio-metrics)。本节使用 OpenWrt 的状态接口和命令，沿实际数据路径定位无线、内部网络和公共出口的瓶颈。

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

### 事件、当前状态与时间序列

排障时要区分几类不会自动互相替代的数据：

| 数据类型 | 回答的问题 | 常见边界 |
|---|---|---|
| 事件日志 | 为什么发生关联、认证、DHCP 或断开事件 | 通常只保留近期记录，重启或缓冲覆盖后消失 |
| 当前状态 | 现在连接哪个 AP、使用什么速率和信号 | 只表示查询时刻，不能还原之前的变化 |
| 周期采样 | 断开前 signal、MCS、重传、流量和延迟怎样变化 | 必须主动保存，采样频率和存储位置需要单独设计 |
| 基准测试历史 | 某次测试的下载、上传和负载延迟 | 只代表测试时段，不等于持续可用带宽 |

OpenWrt 的具体日志命令、历史边界和远程保存方法见 [链路日志与监控面板](#link-dashboard)。

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

## <a id="link-dashboard"></a>链路日志与监控面板

本节说明把上一节的测量对象接入 OpenWrt 路由器上的持续采集和 HTML 面板。它依赖 OpenWrt 的 Web 服务、`ubus`、`iw/iwinfo`、Linux 网卡计数器和后台脚本；原厂固件、RouterOS 或其他系统需要使用各自的 API、脚本或外部采集机，不能直接照搬这套实现。

### <a id="openwrt-logs"></a>OpenWrt 日志与历史数据

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

### 面板运行位置与访问地址

链路面板运行在 OpenWrt 设备本机：HTML 页面由路由器的轻量 Web 服务（例如 uhttpd）提供，状态接口在路由器上读取 `ubus`、`iw` 和网卡计数器。浏览器只是显示这些数据，管理电脑关机不会让路由器端面板消失。

OpenWrt 链路面板模板见 [openwrt-link-dashboard.html](../assets/openwrt-link-dashboard.html)。模板不包含真实 SSID、设备名、Portal 地址或采集后端；页面顶部配置对象定义 API 路径、网络标签、延迟目标和过期时间。

终端要先接入 OpenWrt 的 LAN，或接入已经桥到该 LAN 的下游 AP。随后在浏览器打开：

```text
http://<openwrt-lan-ip>:<dashboard-port>/
```

`<openwrt-lan-ip>` 通常是终端网络详情中的默认网关，也是 LuCI 管理地址；`<dashboard-port>` 是部署面板时为 uhttpd 或其他 Web 服务设置的端口。

下游设备仍处于路由模式时，双重 NAT 和防火墙可能阻止访问上一级 OpenWrt；切为 AP 模式后，终端与 OpenWrt 位于同一 LAN，访问最直接。需要从 LAN 之外访问时，可以另建受控代理或隧道，但那属于部署环境，不是模板默认组成。

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

完整日志边界见 [OpenWrt 日志与历史数据](#openwrt-logs)。Dashboard 可能暴露 SSID、BSSID、内网地址和链路状态，默认应绑定管理 LAN 或指定接口，并用防火墙限制访问；需要跨不可信网络访问时增加认证和 TLS。不要把无认证的 `0.0.0.0` 监听作为通用默认值。

### HTML 模板与数据接口

[openwrt-link-dashboard.html](../assets/openwrt-link-dashboard.html) 内置演示数据，可以直接打开检查布局；配置真实 API（Application Programming Interface，供页面读取数据的接口）后才进入实时模式。适配时只需要实现状态、延迟和基准测试三类 JSON（结构化数据格式），不必复制现场专用的后端脚本或 SSH 代理。

页面采用低噪声深色布局，以当前信号、链路档位、实时流量和基准测试为主，不使用与操作无关的装饰卡片。模板中的 0–100 信号分数只是可配置的展示映射，不是行业标准；数值变化有平滑过渡，STALE 与测试暂停使用明确状态，不让动画掩盖数据含义。

## <a id="ax3000t"></a>小米 AX3000T 案例

本节只记录 AX3000T 独有的硬件差异和一次实际安装结果。通用安装、升级和 SSH 认证分别见[安装、升级与恢复](#installation)和[公钥认证与密码认证](#ssh-security)；无线接入网络见 [外部 Wi-Fi 接入本地网络](external-wifi-access.md)。

### 硬件版本与原厂固件

RD03 国行和 RD23 国际版使用 MediaTek MT7981B 主芯片，官方 OpenWrt 支持。RD03v2 改用 Qualcomm 平台，当前不受支持；包装 SKU `DVB4510CN` 或条码结尾 `706330` 可用于识别。不要把 RD03/RD23 镜像写入 RD03v2。[AX3000T 设备页](https://openwrt.org/toh/xiaomi/ax3000t?rev=1780820319)记录了这组边界。

原厂固件版本决定能否在不拆机的情况下，利用原厂网页接口开启 SSH：

| 机型与固件 | 设备页记录的入口 |
|---|---|
| RD03 1.0.47 | `misystem/arn_switch` |
| RD03 1.0.64、1.0.84、1.0.90、1.0.91、1.0.98 | `xqsystem/start_binding` |
| RD03 1.0.106 | 无已知 API；需降级或 UART |
| RD23 1.0.31、1.0.49、1.0.55、1.0.76 | `xqsystem/start_binding` |
| RD23 1.0.90、1.0.91、1.0.92、1.0.97、1.0.103、1.0.104 | `xqsystem/get_icon` |

表中的固件版本与 API 对应关系来自 [AX3000T 设备页](https://openwrt.org/toh/xiaomi/ax3000t?rev=1780820319)。

25.12.5 已支持设备页列出的 ESMT、Winbond、Foresee 闪存芯片，以及 MT7531AE、AN8855 网口交换芯片。安装前仍应读取机器里的真实硬件信息，不按商品名猜测。

### Windows 单网线管理

[AX3000T 设备页](https://openwrt.org/toh/xiaomi/ax3000t?rev=1780820319)说明原厂固件会动态分配网口的 WAN/LAN 角色。电脑单线直连时，路由器可能把该端口当作 WAN，路由器和电脑都在等待对方分配地址，Windows 最后只得到 `169.254.x.x` 自分配地址。

优先换插其他端口或临时连接原厂 Wi-Fi。必须维持有线连接时，Windows 可临时运行一个只给这台路由器分配地址的 DHCP 服务；有线口不设默认网关，也不启用 Windows 网络共享（ICS）或网络桥接。电脑休眠或 DHCP 程序停止后，临时地址可能失效。

复杂 PowerShell 应落成 `.ps1` 并用 `-File -NonInteractive` 执行；Windows 参数、编码和提权边界由 `software` skill 覆盖。

### 原厂系统盘点与备份

取得 SSH 后，先确认当前从哪套原厂系统启动、闪存分区编号，以及准备写入的备用槽是否正在使用：

```sh
cat /proc/cmdline
cat /proc/mtd
ubinfo -a
```

实际案例备份了 BL2、Nvram、Bdata、Factory、FIP、两个保存原厂系统的 UBI 槽、保存原厂配置的 overlay、data 和 KF，共十个关键分区，并在路由器与电脑两端交叉校验。`Bdata`、`Factory`、`Nvram` 和无线校准数据只能用于原设备恢复。

正在使用的原厂配置区 overlay/data 连续读取两次，两个文件的校验值一致后才接受。老 Dropbear 或临时 OpenWrt 没有 SFTP 服务时，Windows OpenSSH 使用 `scp -O` 兼容旧式 SCP 传输。

### 保留原厂启动程序的安装

案例保留小米原厂 bootloader（路由器上电后最先运行的启动程序），使用官方 25.12.5 中不带 `ubootmod` 的 AX3000T 镜像。安装分两步：先写入 initramfs factory 临时镜像，再从临时系统安装 squashfs sysupgrade 正式镜像。

根据当前活动槽，只写另一槽：

| 当前启动标记 | 临时镜像写入位置 | 下一启动槽的两个变量 |
|---|---|---|
| `firmware=1 mtd=ubi1` | `/dev/mtd8` | `0` / `0` |
| `firmware=0 mtd=ubi` | `/dev/mtd9` | `1` / `1` |

这组槽位与变量对应关系来自 [AX3000T 设备页](https://openwrt.org/toh/xiaomi/ax3000t?rev=1780820319)；写入前仍要以本机 `/proc/cmdline` 和 `/proc/mtd` 为准。

关键写入命令只有：

```sh
ubiformat <未使用的-mtd-分区> -y -f /tmp/<临时-openwrt-镜像.ubi>
```

写入成功后，按官方设备页为目标槽设置 `flag_boot_rootfs` 和 `flag_last_success`。这两个变量告诉原厂启动程序下次进入哪个槽；还要启用等待启动和 UART 恢复相关变量，标记启动成功，并清零两个尝试失败计数。每个变量都回读无误后才重启，不能只修改其中一部分。

临时系统必须确认设备型号正确、系统确实运行在内存中的 initramfs 模式、网口交换芯片正常、三个 LAN、一个 WAN、两张无线电和 LuCI 均存在，再按[系统升级](#system-upgrade)中的验证步骤检查并安装正式系统。

### 正式安装后的原厂恢复

临时阶段只覆盖没有启动的备用槽，当前原厂系统、原厂配置区 overlay 和 data 仍在。正式安装会把原厂 `mtd8` 改作 OpenWrt 内核区域，并把原厂 `mtd9 + mtd10 + mtd11` 合并成新的持久数据区域，见 [AX3000T DTS](https://github.com/openwrt/openwrt/blob/v25.12.5/target/linux/mediatek/dts/mt7981b-xiaomi-mi-router-ax3000t.dts#L18-L34)和[升级脚本](https://github.com/openwrt/openwrt/blob/v25.12.5/target/linux/mediatek/filogic/base-files/lib/upgrade/platform.sh#L48-L96)。

因此正式安装后，不能只改一个启动槽变量就完整回到原厂系统。恢复依赖这台机器自己的备份，以及 AX3000T 设备页记录的 TFTP 或 UART 路径；恢复地址、文件名和分区参数不能从其他小米型号推断。

### 安装后的功能验收

本次设备为 RD03、原厂固件 1.0.64、MT7981 主芯片、MT7531AE 网口交换芯片和 128 MiB NAND 闪存。官方 25.12.5 按保留原厂启动程序的两阶段方式安装后：

- 正式系统使用只读的 squashfs 基础系统，并叠加可写的 UBIFS 配置层，可写空间约 60.7 MiB；
- NAND 没有坏块或读写错误，重启后配置保持；
- 靠近电源的端口为 WAN，三个中间口为 LAN；
- 两张无线电、LuCI、SSH 和端口均正常；
- 已用个人热点完成 5 GHz station → WWAN/NAT → 有线 LAN 的安装阶段验收，并确认重启后自动恢复；
- 已设置 root 密码并拒绝空密码 SSH；关闭密码认证并只保留公钥登录尚需按[公钥认证与密码认证](#ssh-security)完成；
- 后续外部 Wi-Fi、企业认证、下游 AP、链路测量和 Dashboard 的实测已移入 [校园无线接入案例](external-wifi-access.md#campus-case)，避免把安装验收与长期网络方案混在一起。

AX3000T 的公共设备树定义了蓝色和黄色状态灯：启动、failsafe 和升级使用黄色，正常运行使用蓝色，见[状态灯别名](https://github.com/openwrt/openwrt/blob/v25.12.5/target/linux/mediatek/dts/mt7981b-xiaomi-mi-router-common.dtsi#L9-L16)和[GPIO LED 定义](https://github.com/openwrt/openwrt/blob/v25.12.5/target/linux/mediatek/dts/mt7981b-xiaomi-mi-router-common.dtsi#L44-L57)。这些是标准 Linux 状态灯，不保证复刻小米原厂的全部动画。

这次安装阶段短测只证明了无线客户端、NAT 和持久重连可用；链路质量与定向 CPE 的判断方法见 [无线链路测量与排查](#link-measurement)和[使用定向 CPE](external-wifi-access.md#cpe)。
