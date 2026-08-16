# OpenWrt 路由器刷写与无线客户端

本文覆盖两类连续任务：从原厂固件安全安装 OpenWrt，以及让 OpenWrt 把无线网络作为上游、经有线 LAN 向客户端提供 NAT。小米 AX3000T 是完整案例；其他型号只能复用方法，不能复用镜像、分区号或启动变量。

## <a id="identity"></a>设备身份与版本边界

刷写前先分清三个彼此独立的“版本”：

- **商品名与硬件版本**决定能否使用目标设备镜像。AX3000T 的 RD03 / RD23 是 MediaTek MT7981；RD03v2 是另一套 Qualcomm 硬件，不能刷前两者的镜像。
- **原厂固件版本**决定能否用 API 漏洞开启 SSH，以及该用哪个入口。
- **OpenWrt 版本**决定是否支持设备实际使用的 NAND 和交换芯片。

[OpenWrt Wiki 的 2026-06-07 修订版](https://openwrt.org/toh/xiaomi/ax3000t?rev=1780820319)记录了 AX3000T 的边界：

| 机型 | 原厂固件 | SSH 入口 |
|---|---|---|
| RD03 国行 | 1.0.47 | `misystem/arn_switch` |
| RD03 国行 | 1.0.64、1.0.84、1.0.90、1.0.91、1.0.98 | `xqsystem/start_binding` |
| RD03 国行 | 1.0.106 | 无已知 API 入口；API 路线需要降级 |
| RD23 国际版 | 1.0.31、1.0.49、1.0.55、1.0.76 | `xqsystem/start_binding` |
| RD23 国际版 | 1.0.90、1.0.91、1.0.92、1.0.97、1.0.103、1.0.104 | `xqsystem/get_icon` |

“版本太高不能刷”通常指**当前原厂固件已经封住适用的 SSH 入口**，不表示硬件永远不能运行 OpenWrt。不要把这个问题与 RD03v2 的硬件不兼容混为一谈。

UART 是不依赖原厂 API 漏洞的另一条通用安装路线，需要拆机和串口工具，不属于“高版本 API 直接刷写”。

同名硬件也可能换 NAND 或交换芯片。AX3000T 新装应先按设备页核对硬件支持表；2026-08 的实操选择官方 25.12.5 stock-layout 镜像，覆盖了已知 NAND 和 MT7531AE / AN8855 交换芯片变体。[25.12.5 设备定义](https://github.com/openwrt/openwrt/blob/v25.12.5/target/linux/mediatek/image/filogic.mk#L3271-L3288)同时生成 initramfs factory 和 sysupgrade 两类镜像。

## <a id="one-cable"></a>Windows 与单根网线

### 原厂自适应网口

小米原厂固件会动态判断 WAN/LAN。只有一根线连接 Windows PC 时，路由器可能把该口当作 WAN，并主动向电脑索要 DHCP 地址。典型现象：

- 物理链路协商到 1 Gbit/s；
- Windows 只得到 `169.254.x.x`（APIPA，自分配地址），没有网关；
- 抓包看到路由器从 UDP 68 向 `255.255.255.255:67` 发送 DHCP Discover；
- 常见管理地址没有 ARP 响应。

这不是“Windows DHCP 坏了”，而是路由器和电脑都把自己当客户端。按成本从低到高处理：

1. 换插另一个路由器网口，或临时连接原厂 Wi-Fi 管理。
2. 若必须维持单线有线管理，可让 Windows 临时充当**严格限域的 DHCP server**：
   - 有线口设置独立静态地址，不配置默认网关；
   - 只响应路由器的已核对 MAC；
   - 只租一个隔离子网地址；
   - 不启用 ICS、网络桥接或向 WLAN 广播 DHCP；
   - 获取管理地址后立即验证 ARP 中的 MAC。

实操中，给被判为 WAN 的 AX3000T 租出地址后，原厂管理页和 SSH 都能通过该地址访问。此行为取决于原厂固件，不能假设所有路由器都开放 WAN 侧管理。临时 DHCP 进程停止或电脑休眠后，租约可能失效；需要续租，而不是盲目改路由器地址。

Windows 上的多行 PowerShell 应落成 `.ps1`，用 `-NoLogo -NoProfile -NonInteractive -File` 运行；路径与编码规则见 [Windows 命令调用](windows.md#invocation)。

### OpenWrt 固定端口

OpenWrt 默认不沿用原厂的动态判定。AX3000T 首次启动后的分工是：

- 靠近电源、标作 Internet 的一个口：WAN；
- 其余三个中间口：LAN，桥接进 `br-lan`；
- LAN 管理地址：`192.168.1.1/24`，向电脑提供 DHCP。

所以从 initramfs 第一次启动后，网线应插中间 LAN 口，Windows 有线口改回 DHCP。WAN/LAN 是交换芯片与 DSA/VLAN 的**软件配置**，不是端口的物理能力；系统稳定后可以重配，但首次安装不要同时改端口拓扑。

## <a id="stock-flash"></a>AX3000T 原厂 bootloader 安装

本节只适用于 RD03 / RD23 的 stock layout。`ubootmod` 是另一套分区布局，镜像和恢复方法都不同，不能混用。

### 进入 SSH 与盘点

根据原厂固件版本，从[官方设备页修订版](https://openwrt.org/toh/xiaomi/ax3000t?rev=1780820319#api_rce_support_status)选择 API 入口并开启 Dropbear。短期 `stok`、管理密码和后续 Wi-Fi 密码都应走带外 secret 注入，不进入脚本、命令参数或对话。

SSH 可用后先只读盘点：

```sh
cat /proc/cmdline
cat /proc/mtd
for key in \
  flag_boot_rootfs flag_last_success flag_boot_success \
  flag_try_sys1_failed flag_try_sys2_failed; do
  printf '%s=' "$key"
  nvram get "$key"
done
```

`/proc/cmdline` 的 `firmware=0|1` 是当前活动槽。不能只看网上教程猜 mtd 号；必须让当前设备的 `/proc/mtd` 同时证明分区名称、大小和编号。

### 原厂分区备份

AX3000T 常见原厂布局中，至少保留：

| 分区 | 内容 |
|---|---|
| BL2、FIP | 原厂启动链 |
| Nvram | 启动变量 |
| Bdata、Factory、KF | 板级数据、MAC、无线校准及厂商数据 |
| ubi、ubi1 | 两个原厂固件槽 |
| overlay、data | 原厂配置与数据 |

该布局同时记录在 OpenWrt 25.12.5 [AX3000T 升级脚本的 `mtdparts`](https://github.com/openwrt/openwrt/blob/v25.12.5/target/linux/mediatek/filogic/base-files/lib/upgrade/platform.sh#L86-L95) 中。

先按 `/proc/mtd` 解析名称，再用 `nanddump --bb=padbad` 读取，避免跳过坏块后改变镜像的逻辑长度：

```sh
nanddump -q --bb=padbad -f /tmp/<partition>.bin /dev/mtd<N>
```

备份完整流程：

1. 记录 `/proc/mtd`、`/proc/cmdline` 和启动变量。
2. 把各分区读到路由器 `/tmp`；这里是内存盘，重启即丢。
3. 复制到电脑；老 Dropbear 或 initramfs 没有 SFTP server 时，Windows OpenSSH 要用 `scp -O` 强制 legacy SCP。
4. 路由器与电脑交叉比较长度和散列；MD5 只用作传输交叉检查，长期清单使用 SHA-256。
5. 把备份、散列清单、固件和说明放入一个专属目录，避免 Downloads 与临时目录里出现多个“看起来一样”的副本。

运行中的 overlay 可能变化。需要备份这类分区时连续读取两次，原始散列一致才接受；不一致就停止并选择更稳定的备份窗口。

### 两类镜像

从[官方 Firmware Selector](https://firmware-selector.openwrt.org/?target=mediatek%2Ffilogic&id=xiaomi_mi-router-ax3000t)取得同一正式版本的：

- `*-initramfs-factory.ubi`：第一阶段写入非活动槽，只用于启动临时 OpenWrt；
- `*-squashfs-sysupgrade.bin`：临时系统验收后安装正式持久系统。

下载后必须对照官方 `sha256sums`。不要选名称包含 `ubootmod` 的文件。

### 写入非活动槽

先把 factory 镜像复制到路由器 `/tmp` 并再次核对散列。根据 `firmware=` 选择**另一槽**：

| 当前 cmdline | 写入目标 | 下一启动槽 |
|---|---|---|
| `firmware=1 mtd=ubi1` | `/dev/mtd8` | 0 |
| `firmware=0 mtd=ubi` | `/dev/mtd9` | 1 |

执行顺序必须拆开：

1. 单独运行 `ubiformat`。
2. 确认退出码为 0、进度到 100%，且没有 I/O / ECC / 坏块异常。
3. 再设置启动变量并回读。
4. 所有值准确后才重启。

以当前槽 1、目标槽 0 为例：

```sh
ubiformat /dev/mtd8 -y \
  -f /tmp/openwrt-*-mediatek-filogic-xiaomi_mi-router-ax3000t-initramfs-factory.ubi

nvram set boot_wait=on
nvram set uart_en=1
nvram set flag_boot_rootfs=0
nvram set flag_last_success=0
nvram set flag_boot_success=1
nvram set flag_try_sys1_failed=0
nvram set flag_try_sys2_failed=0
nvram commit
sync
```

当前槽 0 时，目标和两个槽值按官方设备页反向设置；不要机械替换一半参数。

### 临时系统与正式安装

重启后把网线换到中间 LAN 口，Windows 改 DHCP，再访问 `192.168.1.1`。先确认临时系统身份：

```sh
ubus call system board
cat /etc/openwrt_release
cat /proc/mtd
iw phy | grep Wiphy
ip -o link show
```

必须看到正确型号、目标、`rootfs_type: initramfs`、交换芯片端口和两张无线电，才进入正式安装。

上传 sysupgrade 镜像后先做只读兼容性检查：

```sh
sha256sum /tmp/openwrt-*-squashfs-sysupgrade.bin
sysupgrade -T /tmp/openwrt-*-squashfs-sysupgrade.bin
```

通过后才执行：

```sh
sysupgrade -n /tmp/openwrt-*-squashfs-sysupgrade.bin
```

`sysupgrade` 会主动关闭 shell。客户端在打印 `Commencing upgrade. Closing all shell sessions.` 后可能收到 ubus connection failed 或非零退出；这**不能证明升级失败**，也不能立刻重跑。等待路由器重新出现，再以 `ubus call system board` 的 `rootfs_type=squashfs`、可写 UBIFS overlay 和正常 UBI 卷为准。

### 正式安装的回退边界

临时阶段只覆盖非活动槽，原厂活动槽、overlay 和 data 仍在；正式 sysupgrade 则不同。OpenWrt 25.12.5 的 [AX3000T DTS](https://github.com/openwrt/openwrt/blob/v25.12.5/target/linux/mediatek/dts/mt7981b-xiaomi-mi-router-ax3000t.dts#L18-L34)把原厂 `mtd8` 映射为 `ubi_kernel`，并把连续的原厂 `mtd9 + mtd10 + mtd11` 合并成新的 `ubi`。[升级脚本](https://github.com/openwrt/openwrt/blob/v25.12.5/target/linux/mediatek/filogic/base-files/lib/upgrade/platform.sh#L48-L96)会格式化这两个 OpenWrt 区域并设置 boot environment。

因此：

- 临时系统阶段通常仍有切回原厂槽的余地；
- 正式 sysupgrade 后不能承诺“改一个启动标志就回原厂”；
- 正式恢复依赖本机备份，以及设备实际可用的 TFTP / UART 路径；
- 原厂设备页的 TFTP 参数仍有未填写项时，不要从其他小米型号照搬；
- bootloader 损坏的高级恢复可参考固定提交的 [`mtk_uartboot`](https://github.com/981213/mtk_uartboot/tree/b0ec7bdf1bab7089df948e745e17d206f3426dc1)，但需要拆机与 UART。

可选的 [`XMiR-Patcher`](https://github.com/openwrt-xiaomi/xmir-patcher/tree/16a46e350e3de2cb3415ab2cb652df53783998dc)能自动化部分小米设备流程；使用前仍要人工核对机型、版本、目标分区和最终命令，不能把工具成功启动当成兼容性证明。

## <a id="post-install"></a>正式系统验收

正式启动后至少检查：

```sh
ubus call system board
mount
df -h
ubinfo -a
fw_printenv \
  boot_wait uart_en flag_boot_rootfs flag_last_success \
  flag_boot_success flag_try_sys1_failed flag_try_sys2_failed
dmesg | grep -Ei 'I/O error|uncorrectable|bad block|UBI error'
```

OpenWrt 25.12.5 的升级脚本会把两个失败计数设为 8，以绕开原厂 bootloader 的计数逻辑；后续看到 8 或继续增长，先对照版本源码和实际启动结果，不要擅自“修回 0”。

还要完成一次重启，确认：

- `rootfs_type=squashfs`，UBIFS overlay 仍可写；
- 配置没有被清空；
- LAN DHCP、SSH/LuCI、端口和无线电恢复；
- boot environment 仍可读。

立即设置 root 强密码并验证空密码登录被拒绝。安装公钥后，必须先用非交互公钥认证实测成功，再考虑关闭密码认证；带 passphrase 的私钥若没有可用 ssh-agent，会造成“公钥已装但自动化仍进不去”，详见 [SSH 的非交互 agent](ssh.md#agent-noninteractive)。

## <a id="wwan"></a>无线作为上游、有线作为 LAN

目标拓扑：

```text
上游 Wi-Fi
    ↓ station
OpenWrt 的 wwan（DHCP）
    ↓ WAN 防火墙区：NAT
br-lan / 中间 LAN 口
    ↓
有线电脑或交换机
```

在新系统上：

1. 新建 `wwan` DHCP 接口。
2. 在一张无线电上新建 station，把它绑定到 `wwan`。
3. 把 `wwan` 加入现有 WAN zone；先确认该 zone 已启用 masquerading。
4. 重载网络后验证关联、地址、默认路由、DNS 和客户端 NAT。

UCI 骨架如下；SSID 与密码应从 secret 侧信道传入，不在脚本中硬编码：

```sh
uci set network.wwan=interface
uci set network.wwan.proto='dhcp'

# 新系统默认 @zone[1] 是 wan；已有配置上必须先核对 name。
test "$(uci get firewall.@zone[1].name)" = wan
uci add_list firewall.@zone[1].network='wwan'

uci set wireless.upstream=wifi-iface
uci set wireless.upstream.device='radio1'
uci set wireless.upstream.mode='sta'
uci set wireless.upstream.network='wwan'
uci set wireless.upstream.ssid="$UPSTREAM_SSID"
uci set wireless.upstream.encryption='sae'
uci set wireless.upstream.key="$UPSTREAM_KEY"
uci set wireless.upstream.ieee80211w='2'

uci commit network
uci commit firewall
uci commit wireless
wifi reload
ifup wwan
```

`sae` 适用于 WPA3-Personal；WPA2-Personal、开放网络和企业认证要按实际 AP 修改。验收不要只看“已关联”：

```sh
ubus call network.interface.wwan status
iw dev <station-interface> link
ip -4 route
ping -c 3 <upstream-gateway>
ping -c 3 <public-ip>
nslookup downloads.openwrt.org
```

Windows 同时连着别的 Wi-Fi 时，默认路由不能证明有线 NAT 可用。可临时增加一条 `/32` 主机路由，让一个探测 IP 强制经 OpenWrt LAN 网关，再在 `finally` 中移除；这样不打断远程管理和现有默认路由。

### WPA2-Enterprise 与 Captive Portal

默认镜像常带 `wpad-basic-mbedtls`，可处理普通 WPA2/WPA3-Personal，但完整 PEAP / TTLS / TLS 客户端应使用 full wpad。OpenWrt 25.12 改用 `apk`；[25.12.5 的 hostapd 包定义](https://github.com/openwrt/openwrt/blob/v25.12.5/package/network/services/hostapd/Makefile#L269-L302)表明各 wpad provider 互相冲突，而 `wpad-openssl` 是完整 EAP supplicant。

先模拟事务：

```sh
apk add --simulate wpad-openssl
```

只有确认它能在同一事务中替换 basic provider 并补齐依赖后才执行；否则先缓存离线包，或通过 Firmware Selector 构建已经包含 full wpad 的镜像。不要为了换 wpad 先手动删除当前 provider，也不要运行 `apk upgrade`。

开放 SSID + 网页认证属于 Captive Portal：先完成 802.11 关联和 DHCP，再由 LAN 客户端打开 Portal。Portal 是按账号、MAC、IP 还是设备策略记账由上游决定，不能假设一次登录必然让所有 NAT 客户端共享。

同一张无线电同时做 station 和 AP 时，AP 通常必须跟随上游信道；需要更稳定的本地 AP 时，优先让另一频段承担 AP。先验证“Wi-Fi → 有线”，再逐步增加无线 AP、企业认证和 Portal，避免多类故障叠在一起。
