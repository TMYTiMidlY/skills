# WireGuard 组网（Ubuntu 中心节点与客户端）

用公网 Ubuntu 服务器连接分散设备，作为 EasyTier 的一种替代方案：`设备 A ↔ 公网服务器 ↔ 设备 B`。这里的 relay 是服务器通过 Linux 内核转发设备流量，不需要另装中继程序。

## <a id="comparison"></a>与 EasyTier 的比较

| 维度 | 本文的 WireGuard 方案 | EasyTier |
| --- | --- | --- |
| 数据路径 | 固定经过公网中心节点 | 自动尝试 P2P 打洞，不能直连时中继 |
| 新增设备 | 独立密钥与 IP，服务器增加 Peer | 使用网络身份加入，支持自动组网和地址分配 |
| 运行与传输 | Ubuntu 内核数据面、官方工具与服务；原生 UDP | 独立组网程序，支持 UDP、TCP 等传输 |
| 运维取舍 | 路径明确、配置精简；依赖中心节点带宽与可用性 | 自动选路；需要核对实际直连或中继状态 |

有稳定公网 UDP 入口、希望手工管理少量设备时可选本方案；需要自动打洞或多协议连接时评估 EasyTier。性能按实际链路测试，不预设谁更快。中心节点会解密再加密转发，应信任其管理者；敏感应用仍使用 SSH、TLS。

> 这是本文拓扑的比较，WireGuard 也可以手工配置设备直连。协议与 Peer 语义见 [WireGuard 手册](https://git.zx2c4.com/wireguard-tools/tree/src/man/wg.8?h=v1.0.20210914#n19)，EasyTier 能力见 [项目说明](https://github.com/EasyTier/EasyTier/blob/v2.6.4/README_CN.md#L23-L100)。Windows EasyTier 配置见 [easytier.md](easytier.md)，其 VPS 部署由 `vps-maintenance` skill 覆盖。

## <a id="delivery"></a>执行与交付方式

- 先确认目标机器、现有配置和用户选定的网段，再生成两端配置。
- 安装、备份、写配置、启动和验证分开，每段成功后再执行下一段。
- 用直接的 `sudo` 命令和 `sudo tee <<'EOF'` 写配置，保持短而完整，不套长篇提权 shell 或临时文件流程。
- 下面的 `<占位符>` 仅供模板说明，交付用户执行前填成已确认的实际内容；私钥通过安全渠道交付，不提交到 Git。
- 已连通的机器复用现状，不重新安装、换密钥或重启承载当前 SSH 的隧道。

## <a id="preflight"></a>机器与现状核对

在每台目标 Ubuntu 上核对：

```bash
hostnamectl
ip -br address
ip -4 route show table all
```

确认软件包、`wg0`、现有配置、`wg-quick@wg0` 服务和防火墙状态。已有接口先查明管理归属；Windows 宿主、WSL 和不同发行版分别识别，避免操作错机器。

## <a id="install"></a>Ubuntu 官方软件包

公网服务器与 Ubuntu 客户端分别执行。先更新软件包索引：

```bash
sudo apt update
```

成功后安装：

```bash
sudo apt install -y wireguard
```

已有安装满足要求时跳过。使用包自带的 `wg-quick@wg0`，不另写服务单元。

## <a id="keys"></a>密钥与地址规划

先询问用户要用哪个 IPv4 组网网段、服务器和各设备分别使用哪个地址；核对与 LAN、Docker、WSL、EasyTier 及其他 VPN 不冲突后再生成配置。已有组网则沿用已确认的网段。地址不必连续，不替用户固定为某个网段或预留某个尾号。

下文 `<组网CIDR>` 表示用户选定的完整网段，`<前缀长度>` 与它一致。各设备地址必须属于该网段、互不重复，且可用于主机。

每台设备独立生成密钥对。可由操作者在受信任环境提前生成；需要自行生成时，在私有目录中确认以下文件尚不存在，再执行：

```bash
umask 077
wg genkey > device-private.key
wg pubkey < device-private.key > device-public.key
```

> 密钥命令见 [`wg genkey` / `wg pubkey`](https://git.zx2c4.com/wireguard-tools/tree/src/man/wg.8?h=v1.0.20210914#n133)。服务器的 Peer 表只保存设备公钥，不保存设备私钥。

## <a id="server-config"></a>公网服务器配置

确认正在操作中心节点。**已有配置时先备份**，备份成功再继续；全新部署跳过这一步：

```bash
sudo cp -p /etc/wireguard/wg0.conf "/etc/wireguard/wg0.conf.bak.$(date +%Y%m%d-%H%M%S)"
```

准备目录和文件权限；`touch` 不会清空已有内容：

```bash
sudo install -d -m 700 /etc/wireguard
sudo touch /etc/wireguard/wg0.conf
sudo chmod 600 /etc/wireguard/wg0.conf
```

核对填好的完整配置后直接写入。已有服务器必须保留所有旧 Peer，不能用下面的示例列表替换掉它们：

```bash
sudo tee /etc/wireguard/wg0.conf >/dev/null <<'EOF'
[Interface]
Address = <服务器组网IP>/<前缀长度>
ListenPort = 51820
PrivateKey = <服务器私钥>

[Peer]
PublicKey = <设备A公钥>
AllowedIPs = <设备A组网IP>/32

[Peer]
PublicKey = <设备B公钥>
AllowedIPs = <设备B组网IP>/32
EOF
```

每台设备一个 Peer，服务器只为它分配独立的 `/32`；客户端主动连接后，服务器学习它的公网 Endpoint，无需预填。

> `Address` 是本机接口地址；`AllowedIPs` 用于出站 Peer 选择和入站源地址校验，见 [Peer 配置字段](https://git.zx2c4.com/wireguard-tools/tree/src/man/wg.8?h=v1.0.20210914#n155)。

## <a id="relay"></a>服务器 relay 与防火墙

设备只访问服务器自身时无需转发。需要设备互访时，在服务器开启 IPv4 转发；已开启则复用现状。下面文件若已存在，先备份并核对原有内容，再写入：

```bash
sudo tee /etc/sysctl.d/90-wireguard-forward.conf >/dev/null <<'EOF'
net.ipv4.ip_forward = 1
EOF
```

写入成功后应用：

```bash
sudo sysctl -p /etc/sysctl.d/90-wireguard-forward.conf
```

> 这是整台主机的设置，变更前核对现有转发用途，见 [Linux IPv4 sysctl](https://www.kernel.org/doc/html/v6.8/networking/ip-sysctl.html#proc-sys-net-ipv4-variables)。

云安全组放行 UDP `51820`，本机防火墙放行该端口和 `wg0 → wg0` 的设备流量。若 UFW 已启用且负责过滤，可执行填好网段的命令：

```bash
sudo ufw allow 51820/udp
sudo ufw route allow in on wg0 out on wg0 from '<组网CIDR>' to '<组网CIDR>'
```

其他防火墙沿用现有规则体系精确放行，不清空规则，也不临时启用另一套防火墙。目的设备自身还须允许所需的 Ping 或应用访问。

纯设备互访不需要 MASQUERADE / SNAT。公网出口、访问其他 LAN 和 IPv6 不包含在这套配置中。

## <a id="client-config"></a>Ubuntu 客户端配置

已有配置先按[服务器配置](#server-config)中的命令备份。每台客户端分别准备权限：

```bash
sudo install -d -m 700 /etc/wireguard
sudo touch /etc/wireguard/wg0.conf
sudo chmod 600 /etc/wireguard/wg0.conf
```

写入该设备自己的地址、私钥和服务器信息：

```bash
sudo tee /etc/wireguard/wg0.conf >/dev/null <<'EOF'
[Interface]
Address = <本设备组网IP>/32
PrivateKey = <本设备私钥>

[Peer]
PublicKey = <服务器公钥>
Endpoint = <服务器公网IP或域名>:51820
AllowedIPs = <组网CIDR>
PersistentKeepalive = 25
EOF
```

客户端把整个选定的组网网段交给服务器，设备互访也走这个 Peer；不改默认出口，不加无关 DNS。NAT 后客户端用 25 秒保活维持映射，服务器不必对称添加。

## <a id="service"></a>启动与配置生效

两端配置核对完成后，在各自机器首次启动并设置开机启动：

```bash
sudo systemctl enable --now wg-quick@wg0
```

`systemctl status wg-quick@wg0 --no-pager` 显示 `active (exited)` 属于正常状态。已有服务运行时，`enable --now` 不会重读配置。

> 官方 [wg-quick 单元](https://git.zx2c4.com/wireguard-tools/tree/src/systemd/wg-quick@.service?h=v1.0.20210914#n13)的 reload 只同步 WireGuard 参数，不更新接口地址、系统路由、MTU、DNS 或钩子。修改这些内容需另行规划生效步骤。手工维护配置时不设 `SaveConfig = true`，以免停止接口时覆盖磁盘修改。

## <a id="add-device"></a>后续增加设备

给新设备独立密钥和用户确认的未占用 IP，准备它自己的客户端配置。服务器先备份，确认公钥和 IP 尚未存在后，只追加一次：

```bash
sudo tee -a /etc/wireguard/wg0.conf >/dev/null <<'EOF'

[Peer]
PublicKey = <新设备公钥>
AllowedIPs = <新设备组网IP>/32
EOF
```

核对后在服务器执行：

```bash
sudo systemctl reload wg-quick@wg0
```

新设备位于原有组网网段、服务器已有覆盖它的路由时，这样即可；原设备已配置整个组网网段，无需修改。扩展新网段则另配路由，不能只依靠 reload。服务器配置须保留全部旧 Peer，`syncconf` 会移除文件中缺失的 Peer。

## <a id="verification"></a>连通性验收

发起通信后，两端检查近期握手与收发计数：

```bash
sudo env WG_HIDE_KEYS=always wg show wg0
```

再依次检查客户端到服务器、服务器到客户端、设备 A 与 B 双向 Ping，以及实际需要的 SSH 或应用访问。

无握手查密钥、Endpoint、UDP 和安全组；有握手但不能互访，查 AllowedIPs、路由、服务器转发和目的端防火墙。小包通而大传输卡住时再检查 MTU。
