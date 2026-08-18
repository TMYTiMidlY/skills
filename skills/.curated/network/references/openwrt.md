# OpenWrt 设备管理

OpenWrt 是面向路由器和嵌入式网络设备的 Linux 发行版。本文说明设备支持、安装与恢复、系统维护和网络配置接口，最后以小米 AX3000T 记录设备专属的刷写与恢复边界。把外部 Wi-Fi 作为上游、经网线连接下游 AP、测量无线链路或选择定向 CPE 时，见 [OpenWrt 无线接入网关](openwrt-wireless-gateway.md)。

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

**旅行路由器。**旅行路由器把外部 Wi-Fi 作为上游，再建立自己控制的 LAN。这个角色要求设备支持 station、WWAN、防火墙和上游认证；若还要向本地广播 Wi-Fi，需要核对无线电数量和并发模式。完整的数据路径、认证和链路测量见 [OpenWrt 无线接入网关](openwrt-wireless-gateway.md)。

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

`/etc/config/network` 定义接口和地址获取方式，`/etc/config/firewall` 决定区域、转发和 NAT。把外部 Wi-Fi 变成网线输出时，完整拓扑见 [搭建无线接入网关](openwrt-wireless-gateway.md#configuration)。

### 无线配置与 wpad

`/etc/config/wireless` 中常见的对象是：

- **radio**：一张物理无线电，例如 2.4 GHz 或 5 GHz；
- **`wifi-iface`**：运行在 radio 上的一条无线配置；
- **AP 模式**：广播 SSID，供其他终端接入；
- **station 模式**：让 OpenWrt 作为 Wi-Fi 客户端连接外部 AP。

AP 和 station 可以运行在不同 radio，也可能共享同一 radio；可用组合取决于驱动和硬件。

**wpad** 是 OpenWrt 打包的无线认证组件，同时包含 hostapd（主要服务 AP 模式）和 wpa_supplicant（主要服务 station 模式）的能力。25.12.5 的 [wpad 包定义](https://github.com/openwrt/openwrt/blob/v25.12.5/package/network/services/hostapd/Makefile)区分 basic 和 full 变体；PEAP、TTLS、TLS、MSCHAPv2 等企业认证方法需要完整变体。

PEAP/MSCHAPv2 的最小 UCI 关系如下，账号和密码应通过受控输入写入，避免进入命令历史：

```sh
uci set wireless.enterprise.encryption='wpa2'
uci set wireless.enterprise.eap_type='peap'
uci set wireless.enterprise.auth='MSCHAPV2'
uci set wireless.enterprise.identity='<identity>'
uci set wireless.enterprise.password='<password>'
```

服务器证书还需要 `ca_cert` 及域名限制，或经过验证的服务器证书 pin。完整认证流程、缓存和漫游边界见 [通过上游认证](openwrt-wireless-gateway.md#authentication)和[理解无线链路](openwrt-wireless-gateway.md#radio-metrics)。

## <a id="ax3000t"></a>小米 AX3000T 案例

本节只记录 AX3000T 独有的硬件差异和一次实际安装结果。通用安装、升级和 SSH 认证分别见[安装、升级与恢复](#installation)和[公钥认证与密码认证](#ssh-security)；无线接入网络见 [OpenWrt 无线接入网关](openwrt-wireless-gateway.md)。

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
- 后续外部 Wi-Fi、企业认证、下游 AP、链路测量和 Dashboard 的实测已移入 [校园无线接入案例](openwrt-wireless-gateway.md#campus-case)，避免把安装验收与长期网络方案混在一起。

AX3000T 的公共设备树定义了蓝色和黄色状态灯：启动、failsafe 和升级使用黄色，正常运行使用蓝色，见[状态灯别名](https://github.com/openwrt/openwrt/blob/v25.12.5/target/linux/mediatek/dts/mt7981b-xiaomi-mi-router-common.dtsi#L9-L16)和[GPIO LED 定义](https://github.com/openwrt/openwrt/blob/v25.12.5/target/linux/mediatek/dts/mt7981b-xiaomi-mi-router-common.dtsi#L44-L57)。这些是标准 Linux 状态灯，不保证复刻小米原厂的全部动画。

这次安装阶段短测只证明了无线客户端、NAT 和持久重连可用；链路质量与定向 CPE 的判断方法见 [测量与排查链路](openwrt-wireless-gateway.md#measurement)和[使用定向 CPE](openwrt-wireless-gateway.md#cpe)。
