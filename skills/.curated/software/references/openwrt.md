# OpenWrt 安装与使用

本文覆盖五个连续主题：确认设备是否受支持、接入原厂系统、安装 OpenWrt、管理 OpenWrt 系统，以及把无线网络作为上游向有线或无线客户端供网。小米 AX3000T RD03 / RD23 是完整案例；其他型号只能复用判断方法，不能复用镜像、分区号或启动变量。

## <a id="compatibility"></a>设备兼容性

### 硬件型号

商品名相同不代表内部硬件相同。先从包装、SKU 和芯片平台确认具体型号，再选择镜像。

| 型号 | 芯片平台 | OpenWrt 状态 | 本文适用性 |
|---|---|---|---|
| RD03 国行 | MediaTek MT7981B | 支持 | 适用 |
| RD23 国际版 | MediaTek MT7981B | 支持 | 适用 |
| RD03v2 国行 | Qualcomm 平台 | 当前不受支持 | 不适用；不要使用 RD03 / RD23 镜像 |

RD03v2 可通过包装识别：SKU 为 `DVB4510CN`，条码结尾为 `706330`。OpenWrt 设备页当前明确标记该型号不受支持，因此只能保留原厂系统，或等待专用适配；这不是更换刷写命令就能解决的问题。[OpenWrt Wiki 的 2026-06-07 修订版](https://openwrt.org/toh/xiaomi/ax3000t?rev=1780820319)记录了型号和支持边界。

### 原厂固件版本

确认硬件受支持后，再检查原厂固件版本。它决定能否通过网页 API 免拆机开启 SSH，以及应使用哪个入口；它不决定 RD03 / RD23 能否运行 OpenWrt。

| 机型 | 原厂固件 | 免拆机 SSH 入口 | 处理方式 |
|---|---|---|---|
| RD03 国行 | 1.0.47 | `misystem/arn_switch` | 使用对应 API |
| RD03 国行 | 1.0.64、1.0.84、1.0.90、1.0.91、1.0.98 | `xqsystem/start_binding` | 使用对应 API |
| RD03 国行 | 1.0.106 | 无已知 API 入口 | 降级，或改用 UART |
| RD23 国际版 | 1.0.31、1.0.49、1.0.55、1.0.76 | `xqsystem/start_binding` | 使用对应 API |
| RD23 国际版 | 1.0.90、1.0.91、1.0.92、1.0.97、1.0.103、1.0.104 | `xqsystem/get_icon` | 使用对应 API |

UART 不依赖原厂网页漏洞，但需要拆机、串口工具和可靠的恢复准备。它是另一种进入设备的方法，不是“高版本 API 刷写”的变体。

### OpenWrt 版本与硬件支持

RD03 / RD23 还可能使用不同的 NAND 和交换芯片。官方 25.12.5 已覆盖设备页列出的已知变体：

| 组件 | 型号 | 首次支持 | 后续修复 |
|---|---|---|---|
| NAND | ESMT F50L1G41LB | 23.05.4 | — |
| NAND | Winbond W25N01KV | 24.10.0-rc1 | 24.10.1 |
| NAND | Foresee F35SQA001G | 24.10.0-rc3 | 24.10.3 |
| 交换芯片 | MediaTek MT7531AE | 23.05.4 | — |
| 交换芯片 | Airoha AN8855 | 24.10.0-rc7 | — |

新装时仍应以当前设备页和 Firmware Selector 为准，不要因为商品名相同就使用旧教程的镜像。[25.12.5 设备定义](https://github.com/openwrt/openwrt/blob/v25.12.5/target/linux/mediatek/image/filogic.mk#L3271-L3288)同时生成临时启动和正式安装镜像。

## <a id="stock-access"></a>原厂系统接入

### Windows 单网线连接

小米原厂固件和 OpenWrt 对网口的默认处理不同：

| 系统 | 网口分工 | Windows 侧配置 | 默认管理入口 |
|---|---|---|---|
| 小米原厂固件 | 四口动态判断 WAN/LAN | 取决于被识别的端口 | 原厂地址或临时租约地址 |
| OpenWrt | 靠近电源的口为 WAN，三个中间口为 LAN | LAN 侧使用 DHCP | `192.168.1.1` |

只有一根网线连接 Windows PC 时，原厂固件可能把该端口判为 WAN，并主动向电脑索要 DHCP 地址。典型现象：

- 物理链路协商到 1 Gbit/s；
- Windows 只得到 `169.254.x.x`（APIPA，自分配地址），没有网关；
- 抓包看到路由器从 UDP 68 向 `255.255.255.255:67` 发送 DHCP Discover；
- 常见管理地址没有 ARP 响应。

此时路由器和电脑都在等待对方提供 DHCP。按成本从低到高处理：

1. 换插另一个路由器网口，或临时连接原厂 Wi-Fi。
2. 若必须维持单线有线管理，让 Windows 临时充当严格限域的 DHCP server：
   - 有线口使用独立静态地址，不配置默认网关；
   - 只响应已核对的路由器 MAC；
   - 只租出一个隔离子网地址；
   - 不启用 ICS、网络桥接，也不向 WLAN 广播 DHCP；
   - 获得管理地址后立即核对 ARP 中的 MAC。

原厂固件是否允许从 WAN 侧访问管理页取决于具体版本。临时 DHCP 进程停止或电脑休眠后，租约也可能失效；应恢复续租服务，而不是盲目更改路由器地址。

Windows 上的多行 PowerShell 应落成 `.ps1`，用 `-NoLogo -NoProfile -NonInteractive -File` 运行；路径与编码规则见 [Windows 命令调用](windows.md#invocation)。

### SSH 入口

按[原厂固件版本表](#compatibility)选择对应 API 并开启 Dropbear。短期 `stok`、管理密码和后续无线密码都应通过带外 secret 注入，不进入脚本、命令参数或对话。

取得 SSH 只代表获得了原厂 Linux 系统的管理入口。开始写入前仍要确认设备型号、活动槽、分区布局、硬件变体和备份完整性。

### 设备状态盘点

先读取原厂系统状态：

```sh
cat /proc/cmdline
cat /proc/mtd
mount
ubinfo -a

for key in \
  flag_boot_rootfs flag_last_success flag_boot_success \
  flag_try_sys1_failed flag_try_sys2_failed; do
  printf '%s=' "$key"
  nvram get "$key"
done
```

| 检查项 | 用途 | 停止条件 |
|---|---|---|
| `/proc/cmdline` | 确认当前 `firmware=0|1` 和活动 UBI | 与预期槽位不符 |
| `/proc/mtd` | 确认分区名称、编号和大小 | 名称或大小与设备页不符 |
| `mount` / `ubinfo -a` | 确认目标槽未被使用 | 准备写入的槽仍挂载 |
| 启动变量 | 确认下一启动槽和失败计数 | 变量缺失或语义不明 |
| NAND / 交换芯片日志 | 确认硬件变体 | 当前 OpenWrt 版本不支持 |

不能只按网上教程猜 mtd 号；必须让当前设备的真实输出证明写入目标。

## <a id="install"></a>OpenWrt 安装

### 安装流程

官方文档把整体过程称为安装；“写入”或“刷写”只描述其中把镜像写进闪存的步骤。

| 阶段 | 使用内容 | 写入范围 | 通过条件 |
|---|---|---|---|
| 原厂准备 | 分区备份、散列清单 | 不写 NAND | 备份与镜像均已校验 |
| 临时系统 | `initramfs-factory.ubi` | 仅非活动槽 | 正确设备以 initramfs 启动 |
| 正式系统 | `squashfs-sysupgrade.bin` | 重建 OpenWrt 内核和数据区 | `sysupgrade -T` 通过 |
| 安装验收 | 正式系统和持久 overlay | 不重复写镜像 | 重启后配置与存储正常 |

使用原装电源，保持管理电脑接电且不休眠。任何写入命令出现非零退出、I/O、ECC 或无法解释的坏块错误，都应停止，不继续切换启动槽。

### 原厂分区备份

AX3000T 常见原厂布局中至少保留：

| 分区 | 内容 |
|---|---|
| BL2、FIP | 原厂启动链 |
| Nvram | 启动变量 |
| Bdata、Factory、KF | 板级数据、MAC、无线校准及厂商数据 |
| ubi、ubi1 | 两个原厂固件槽 |
| overlay、data | 原厂配置与数据 |

该布局同时记录在 OpenWrt 25.12.5 [AX3000T 升级脚本的 `mtdparts`](https://github.com/openwrt/openwrt/blob/v25.12.5/target/linux/mediatek/filogic/base-files/lib/upgrade/platform.sh#L86-L95) 中。

`Bdata`、`Factory` 和 `KF` 含设备专属的 MAC、板级参数或无线校准数据，只能用于原设备恢复，不能使用其他路由器的备份替代。

按 `/proc/mtd` 解析实际编号，再用 `nanddump --bb=padbad` 读取，避免跳过坏块后改变镜像的逻辑长度：

```sh
nanddump -q --bb=padbad -f /tmp/<partition>.bin /dev/mtd<N>
```

备份流程：

1. 保存 `/proc/mtd`、`/proc/cmdline` 和启动变量。
2. 把分区读取到路由器 `/tmp`；这里是内存盘，重启即丢。
3. 复制到电脑；老 Dropbear 或 initramfs 没有 SFTP server 时，Windows OpenSSH 使用 `scp -O` 强制 legacy SCP。
4. 比较路由器与电脑两端的长度和散列；MD5 只用于传输交叉检查，长期清单使用 SHA-256。
5. 将备份、散列清单、固件和说明放入一个专属目录，避免临时目录里出现多个无法区分的副本。

运行中的 overlay 可能变化。备份这类分区时连续读取两次，原始散列一致才接受；不一致就更换备份窗口。

### 分区布局与镜像类型

AX3000T 有两套不能混用的 OpenWrt 布局：

| 布局 | bootloader | 镜像名称 | 恢复方式 | 本文范围 |
|---|---|---|---|---|
| stock-layout | 保留原厂 bootloader | 名称不含 `ubootmod` | 依赖原厂启动链和备份 | 本文采用 |
| ubootmod | 替换为 OpenWrt U-Boot | 名称包含 `ubootmod` | 分区和恢复流程均不同 | 不在本文展开 |

从[官方 Firmware Selector](https://firmware-selector.openwrt.org/?target=mediatek%2Ffilogic&id=xiaomi_mi-router-ax3000t)取得同一版本的两类镜像：

| 镜像 | 用途 | 运行时配置 | 使用阶段 |
|---|---|---|---|
| `*-initramfs-factory.ubi` | 从非活动槽启动临时 OpenWrt | 位于内存，重启后丢失 | 硬件与布局验收 |
| `*-squashfs-sysupgrade.bin` | 安装正式 squashfs 与可写 overlay | 写入持久 overlay | 临时系统验收后 |

下载后对照官方 `sha256sums`。stock-layout 流程不能使用任何带 `ubootmod` 的文件。

### 临时系统

#### 写入目标

上传 factory 镜像到路由器 `/tmp` 并再次核对散列。根据当前活动槽选择另一槽：

| 当前 `/proc/cmdline` | 写入目标 | `flag_boot_rootfs` | `flag_last_success` |
|---|---|---:|---:|
| `firmware=1 mtd=ubi1` | `/dev/mtd8` | 0 | 0 |
| `firmware=0 mtd=ubi` | `/dev/mtd9` | 1 | 1 |

当前为槽 1 时：

```sh
ubiformat /dev/mtd8 -y \
  -f /tmp/openwrt-25.12.5-mediatek-filogic-xiaomi_mi-router-ax3000t-initramfs-factory.ubi

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

当前为槽 0 时：

```sh
ubiformat /dev/mtd9 -y \
  -f /tmp/openwrt-25.12.5-mediatek-filogic-xiaomi_mi-router-ax3000t-initramfs-factory.ubi

nvram set boot_wait=on
nvram set uart_en=1
nvram set flag_boot_rootfs=1
nvram set flag_last_success=1
nvram set flag_boot_success=1
nvram set flag_try_sys1_failed=0
nvram set flag_try_sys2_failed=0
nvram commit
sync
```

两个代码块只能选择与当前 cmdline 完全匹配的一组。先单独执行 `ubiformat`，确认退出码为 0、进度到 100% 且没有 I/O / ECC 错误；随后设置启动变量并逐项回读，所有值准确后才重启。

#### 临时系统验收

重启后将网线插入三个中间 LAN 口之一，Windows 有线口改回 DHCP，再访问 `192.168.1.1`：

```sh
ubus call system board
cat /etc/openwrt_release
cat /proc/mtd
iw phy | grep Wiphy
ip -o link show
```

必须看到正确型号、目标平台、`rootfs_type: initramfs`、交换芯片端口和两张无线电，才进入正式安装。

### 正式系统

上传 sysupgrade 镜像并核对 SHA-256：

```sh
sha256sum /tmp/openwrt-25.12.5-mediatek-filogic-xiaomi_mi-router-ax3000t-squashfs-sysupgrade.bin

sysupgrade -T \
  /tmp/openwrt-25.12.5-mediatek-filogic-xiaomi_mi-router-ax3000t-squashfs-sysupgrade.bin
```

兼容性检查通过后才执行：

```sh
sysupgrade -n \
  /tmp/openwrt-25.12.5-mediatek-filogic-xiaomi_mi-router-ax3000t-squashfs-sysupgrade.bin
```

`sysupgrade` 会主动关闭 shell。客户端在打印 `Commencing upgrade. Closing all shell sessions.` 后可能收到 ubus connection failed 或非零退出；这不能证明升级失败，也不能立刻重跑。等待路由器重新出现，再检查正式系统状态。

### 安装验收

正式启动后检查：

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

| 检查项 | 通过条件 |
|---|---|
| 根文件系统 | `rootfs_type=squashfs` |
| 持久存储 | UBIFS overlay 可写且容量正常 |
| NAND | 没有无法解释的 I/O、ECC 或 UBI 错误 |
| 启动环境 | 启动变量可读，目标槽正确 |
| 网络与无线 | LAN DHCP、端口、两张无线电和 LuCI 正常 |

OpenWrt 25.12.5 的升级脚本会把两个失败计数设为 8，以绕开原厂 bootloader 的计数逻辑；看到 8 或继续增长时，先对照版本源码和实际启动结果，不要擅自改回 0。

完成一次正式重启，确认配置没有被清空、overlay 仍可写、管理入口和网络接口均恢复。

### 回退与故障恢复

正式安装会改变恢复条件：

| 所处阶段 | 原厂内容状态 | 回退方式 |
|---|---|---|
| 尚未写入 | 全部原样保留 | 停止操作 |
| 临时系统 | 原厂活动槽、overlay 和 data 通常仍在 | 切回原厂活动槽 |
| 正式系统 | 原厂 `mtd9 + mtd10 + mtd11` 已被重建 | 使用本机备份配合 TFTP / UART |

OpenWrt 25.12.5 的 [AX3000T DTS](https://github.com/openwrt/openwrt/blob/v25.12.5/target/linux/mediatek/dts/mt7981b-xiaomi-mi-router-ax3000t.dts#L18-L34)把原厂 `mtd8` 映射为 `ubi_kernel`，并把连续的原厂 `mtd9 + mtd10 + mtd11` 合并成新的 `ubi`。[升级脚本](https://github.com/openwrt/openwrt/blob/v25.12.5/target/linux/mediatek/filogic/base-files/lib/upgrade/platform.sh#L48-L96)会格式化这两个 OpenWrt 区域并设置启动环境。因此正式安装后不能靠修改一个启动标志恢复原厂系统。

原厂设备页的 TFTP 参数仍有未填写项时，不要从其他小米型号照搬。bootloader 损坏后的高级恢复可参考固定提交的 [`mtk_uartboot`](https://github.com/981213/mtk_uartboot/tree/b0ec7bdf1bab7089df948e745e17d206f3426dc1)，但需要拆机和 UART。

可选的 [`XMiR-Patcher`](https://github.com/openwrt-xiaomi/xmir-patcher/tree/16a46e350e3de2cb3415ab2cb652df53783998dc)能自动化部分小米设备操作；工具可以减少手工步骤，但不能代替机型、版本、目标分区和最终命令的人工核对。

## <a id="management"></a>OpenWrt 系统管理

### Linux 系统环境

[OpenWrt 25.12.5 的项目说明](https://github.com/openwrt/openwrt/blob/v25.12.5/README.md#L3-L10)将 OpenWrt 定义为面向嵌入式设备的 Linux 操作系统。OpenWrt 本身就是路由器运行的 Linux 发行版；SSH 登录后直接进入这个系统。它使用自己的 BusyBox、`ash`、`procd` 和软件包体系，命令与 Ubuntu / Debian 不完全相同。

| 组件 | 作用 | 与常见服务器发行版的区别 |
|---|---|---|
| Linux 内核 | 驱动硬件、网络协议栈和防火墙 | 针对嵌入式设备裁剪 |
| BusyBox + `ash` | 提供 shell 和常用命令 | 默认不是 Bash，命令选项较少 |
| squashfs + overlay | 只读基础系统叠加可写配置层 | 恢复出厂配置时可丢弃 overlay |
| `procd` | 管理服务和进程 | 不使用 systemd |
| UCI | 集中管理 `/etc/config/*` | 代替各服务分散配置 |
| `ubus` | 进程间通信和状态查询 | LuCI、网络服务和脚本共用 |
| `apk` | OpenWrt 25.12 的包管理器 | 不使用 `apt`；旧版教程常写 `opkg` |

[OpenWrt 25.12 的 apk 迁移说明](https://openwrt.org/docs/guide-user/additional-software/opkg-to-apk-cheatsheet)同时说明该版本使用 BusyBox `ash`，并明确禁止用 `apk upgrade` 盲目升级全系统。

### LuCI、UCI 与 ubus

三者操作的是同一套 OpenWrt 系统：

| 入口 | 运行位置 | 用途 |
|---|---|---|
| LuCI | 路由器上的 Web 服务，Windows 只运行浏览器 | 日常图形化配置 |
| UCI | 路由器命令行和 `/etc/config/*` | 读取、修改并持久化配置 |
| ubus | 路由器内部消息总线 | 查询运行状态、调用服务方法 |
| SSH | Dropbear 提供的远程 shell | 高级配置、排障和自动化 |

[UCI 官方说明](https://openwrt.org/docs/guide-user/base-system/uci)将其定义为 OpenWrt 服务的统一配置接口；LuCI 也通过相同配置层修改 `/etc/config/*`。[ubus 技术说明](https://openwrt.org/docs/techref/ubus)说明了服务注册、状态查询和 JSON 调用模型。

常用只读命令：

```sh
uci show network
uci show wireless
ubus call system board
ubus call network.interface.lan status
```

修改 UCI 后通常需要 `uci commit <package>`，再 reload 或 restart 对应服务；只改文件但不重载服务，不代表运行状态已经更新。

### SSH 与 Dropbear

OpenWrt 使用 Dropbear 提供 SSH。25.12.5 的[默认配置](https://github.com/openwrt/openwrt/blob/v25.12.5/package/network/services/dropbear/files/dropbear.config#L1-L9)启用服务、端口 22、密码认证和 root 密码认证。未设置监听接口时，启动脚本会监听所有地址；防火墙再决定哪些网络能够访问。

| 来源网络 | 默认能否连接 22 端口 | 原因 |
|---|---|---|
| 有线 LAN | 能 | LAN zone 默认 `input ACCEPT` |
| 挂在 LAN 上的无线 AP | 能 | 与有线 LAN 属于同一防火墙区 |
| WAN / WWAN 上游 | 不能 | WAN zone 默认 `input REJECT` |
| 独立 guest zone | 取决于配置 | 应明确限制管理端口 |

默认防火墙规则可在 25.12.5 [firewall 配置](https://github.com/openwrt/openwrt/blob/v25.12.5/package/network/config/firewall/files/firewall.config#L1-L28)中核对。监听地址和防火墙是两层控制：即使 WAN 防火墙当前阻止访问，仍可把 Dropbear 直接限制在 LAN。

### <a id="ssh-security"></a>SSH 访问控制

安全顺序是“先安装并验证公钥，再关闭密码认证”。不要先关闭密码，也不要因为公钥文件已经存在就假设私钥端一定能登录。

在管理电脑创建专用 Ed25519 密钥：

```sh
ssh-keygen -t ed25519 -f ~/.ssh/openwrt-router
```

仍使用现有密码登录，把公钥加入路由器：

```sh
cat ~/.ssh/openwrt-router.pub | \
  ssh root@192.168.1.1 \
  'umask 077; mkdir -p /etc/dropbear; cat >> /etc/dropbear/authorized_keys; chmod 600 /etc/dropbear/authorized_keys'
```

若私钥带 passphrase，先加载到可用的 ssh-agent，相关边界见 [SSH 的非交互 agent](ssh.md#agent-noninteractive)。随后强制禁用密码回退，验证一条全新连接：

```sh
ssh -i ~/.ssh/openwrt-router \
  -o IdentitiesOnly=yes \
  -o PasswordAuthentication=no \
  -o BatchMode=yes \
  root@192.168.1.1 'echo key-ok'
```

只有看到 `key-ok`，才在路由器上限制监听并关闭 SSH 密码认证：

```sh
uci show dropbear

uci set dropbear.main.DirectInterface='lan'
uci set dropbear.main.PasswordAuth='off'
uci set dropbear.main.RootPasswordAuth='off'
uci commit dropbear
/etc/init.d/dropbear restart
```

25.12.5 的 Dropbear 启动脚本将 `DirectInterface='lan'` 解析为实际的 `br-lan` 并直接绑定接口，同时把两个密码开关转换为 Dropbear 的禁用参数，见[接口绑定](https://github.com/openwrt/openwrt/blob/v25.12.5/package/network/services/dropbear/files/dropbear.init#L236-L250)和[认证参数](https://github.com/openwrt/openwrt/blob/v25.12.5/package/network/services/dropbear/files/dropbear.init#L302-L326)。

默认配置节名是 `main`；已有系统若使用其他节名，应以 `uci show dropbear` 的真实结果为准。重启 Dropbear 后再开一个新终端测试，并完成一次路由器重启。不要删除 root 系统密码：关闭的是 SSH 密码认证，LuCI 登录和本地恢复仍可使用该密码。

## <a id="networking"></a>OpenWrt 网络配置

### WAN 与 LAN

AX3000T 首次启动后的默认端口分工：

| 端口 | 默认角色 | 所属网络 |
|---|---|---|
| 靠近电源、标作 Internet 的端口 | WAN | `wan` |
| 三个中间端口 | LAN | `br-lan` |

LAN 默认地址为 `192.168.1.1/24`，并向客户端提供 DHCP。WAN/LAN 是交换芯片、DSA 和 VLAN 的软件配置，不是端口的物理能力；系统稳定后可以重新分配，但安装阶段应保持默认拓扑。

### 无线网络作为上游

目标拓扑：

```text
上游 Wi-Fi
    ↓ station
OpenWrt 的 wwan（DHCP）
    ↓ WAN 防火墙区：NAT
br-lan / LAN 端口 / 本地 AP
    ↓
下游客户端
```

配置步骤：

1. 新建 `wwan` DHCP 接口。
2. 在一张无线电上新建 station，并绑定到 `wwan`。
3. 将 `wwan` 加入启用 masquerading 的 WAN zone。
4. 重载网络，验证关联、地址、默认路由、DNS 和下游 NAT。

UCI 骨架：

```sh
uci set network.wwan=interface
uci set network.wwan.proto='dhcp'

# 新系统默认 @zone[1] 是 wan；已有配置必须先核对 name。
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

`sae` 适用于 WPA3-Personal；其他认证方式按下节调整。SSID、密码、企业账号和证书应通过 secret 侧信道传入，不在脚本中硬编码。

### <a id="wireless-auth"></a>无线认证方式

| 网络类型 | 无线关联方式 | 是否需要完整 wpad | 后续登录 |
|---|---|---|---|
| WPA2/WPA3 Personal | 预共享密钥 | 通常不需要 | 无 |
| WPA2-Enterprise | 802.1X + PEAP / TTLS / TLS | 需要 | 在无线配置中提交身份或证书 |
| Captive Portal | 常见为开放网络，也可能叠加其他加密 | 取决于底层无线认证 | 关联和 DHCP 后在网页完成 |

默认镜像常带 `wpad-basic-mbedtls`，可处理普通 WPA2/WPA3 Personal。完整 PEAP、TTLS 和 TLS 客户端应使用 full wpad；OpenWrt 25.12.5 的 [hostapd 包定义](https://github.com/openwrt/openwrt/blob/v25.12.5/package/network/services/hostapd/Makefile#L269-L302)显示各 wpad provider 互相冲突，而 `wpad-openssl` 提供完整 EAP supplicant。

先模拟替换事务：

```sh
apk add --simulate wpad-openssl
```

只有确认事务会一次性替换 basic provider 并补齐依赖后，才执行：

```sh
apk add wpad-openssl
```

若无法原子完成，先缓存完整包集，或通过 Firmware Selector 构建已包含 full wpad 的镜像。不要先手动删除当前 provider，也不要运行 `apk upgrade`。

Captive Portal 的流程与企业无线认证不同：先完成无线关联和 DHCP，再由下游客户端打开网页认证。Portal 可能按账号、客户端 MAC、IP 或设备策略记账；经过 NAT 的多个客户端能否共享一次登录取决于上游实现。

### 向下游设备提供网络

有线 LAN、无线 AP 和无线桥接不是同一个概念：

| 方式 | 作用 | 下游地址 | 上游要求 |
|---|---|---|---|
| 有线 LAN | 通过网线接入 OpenWrt 的 LAN | 由 OpenWrt 或上游分配 | 无无线要求 |
| 无线 AP | OpenWrt 广播本地 SSID | 取决于 AP 绑定的网络 | 无；AP 只是下游接入方式 |
| 路由 + NAT | 在上游和下游之间路由并转换地址 | 与上游不同网段 | 普通 Wi-Fi 客户端能力即可 |
| WDS / 四地址桥接 | 建立真实二层无线桥 | 与上游同网段 | 上游 AP 和客户端都支持兼容 WDS |
| `relayd` | 在不支持 WDS 时模拟同网段中继 | 表面上与上游同网段 | 安装额外包，行为不等同真实二层桥 |

无线 AP 可以连接到 NAT 后的 LAN，也可以成为桥接网络的一部分；“开启 AP”不等于“已经桥接”。WDS 会保留两侧客户端 MAC 和广播流量，官方说明见[无线 WDS 桥接](https://openwrt.org/docs/guide-user/network/wifi/wifiextenders/wds)。上游无法配合 WDS 时可使用 [`relayd` 中继](https://openwrt.org/docs/guide-user/network/wifi/relay_configuration)，但配置和排障成本更高。

同一张无线电同时承担 station 和 AP 时，AP 通常必须跟随上游信道。双频设备可让一张无线电连接上游，另一张承担本地 AP，减少信道耦合。

任何绑定到 LAN 的无线 AP 客户端默认都能访问路由器的 LAN 管理服务，包括 LuCI 和 SSH。需要访客网络时，应创建独立防火墙区并明确拒绝管理入口，而不是只换一个 SSID。

### 网络验收

不要只确认“无线已关联”。至少检查：

```sh
ubus call network.interface.wwan status
iw dev <station-interface> link
ip -4 route
ping -c 3 <upstream-gateway>
ping -c 3 <public-ip>
nslookup downloads.openwrt.org
```

| 层次 | 通过条件 |
|---|---|
| 无线 | 已关联，信号和协商速率稳定 |
| 接口 | `wwan` 获得地址和上游网关 |
| 路由 | 默认路由指向上游 |
| 公网 | 公网 IP 可达 |
| DNS | 域名解析成功 |
| 下游 | 有线 LAN 或本地 AP 客户端能经 OpenWrt 上网 |
| 持久性 | 重启后自动重连，配置未丢失 |

Windows 同时连接其他 Wi-Fi 时，默认路由不能证明有线 NAT 可用。可临时添加一条 `/32` 主机路由，让一个探测 IP 强制经过 OpenWrt LAN 网关，并在测试结束后移除。

需要评估远距离无线链路时，再记录 RSSI、SNR、重传、半小时丢包、上下行吞吐和数小时稳定性；短暂 ping 成功不能代表长期链路质量。
