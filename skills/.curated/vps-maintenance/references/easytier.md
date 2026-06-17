# 在 VPS 上部署 EasyTier

EasyTier 是一个去中心化的组网工具（类似 Tailscale / ZeroTier）：把分散在不同 NAT、不同机房的机器拉进同一个虚拟局域网，能直连就 P2P 直连，不能就找一个有公网 IP 的节点中继。本文覆盖在公网 VPS 上把它装起来、配好、避开默认配置的坑。

## 装之前先知道：默认配置的几个坑

EasyTier 官方安装脚本（`wget ... install.sh`）装完会写一份 `/opt/easytier/config/default.conf` 并**自动 `systemctl enable --now easytier@default`**，这份默认配置有几个坑，正式部署前必须知道：

1. **默认网络是公开的。** `default.conf` 里 `network_name` 和 `network_secret` 都是字面量 `"default"`，还带了公共种子节点 `public.easytier.top`。任何照官方脚本装的人都用同一组凭证，于是**所有人都在同一个公开虚拟网里**，能互相发现、P2P、互相中继。正式用必须改掉这两个值。

2. **光改 `network_secret` 还不够。** 这是最容易踩的点：就算你把 secret 改成强随机、把自己从公开网里摘出来，只要 `default.conf` 其余部分原样，**别人只要知道你的公网 IP，仍能白嫖你的节点做数据中继**——不需要猜你的 secret。原因是 `default.conf` 没写 `private_mode`（默认 `false`），而中继白名单默认放行所有外部网络（`relay_network_whitelist` 默认 `"*"`）：攻击者把你的 IP 配成**他们自己**网络的 peer，握手时带的是他们的凭证，你这边一看"白名单是 `*`，放行"，就给他们转发数据了。要堵死这条路，必须显式加 **`private_mode = true`**（机制详见下文「隐私与转发控制」）。

3. **装完默认就在跑、且没问过你。** 安装脚本结尾的 `systemctl enable --now easytier@default` 不会征求确认。装完先 `systemctl list-units 'easytier@*'` 看一眼 `easytier@default` 是不是在跑，不需要就 `systemctl disable --now easytier@default`，或干脆删掉/`mask` 掉这份 `default.conf` 防手滑。

4. **节点会主动连第三方 STUN（含芒果 TV / B 站）。** 这是正常行为不是漏洞：EasyTier 启动时作为 STUN **客户端**，向内置的一组公共 STUN 服务器（`stun.miwifi.com`、`stun.chat.bilibili.com`、`stun.hitv.com` 等，见源码 `easytier/src/common/stun.rs` 的 `DEFAULT_UDP_STUN_SERVERS`）询问自己的公网地址、判断 NAT 类型。是"你在白嫖芒果 TV/B 站的 STUN"，不是别人在用你。介意这些目标（比如公司网络会告警）可在配置里用 `stun_servers` 覆盖成自己信任的列表。

> 本文下面的配置模板已经把坑 1、2 堵上了（改凭证 + `private_mode = true`），照着配即可。

## 部署

### 组网思路

所有公网 VPS 按下方模板配置，开启 `private_mode`，可选两种角色：

- **加入模式**：分配虚拟 IP，正常参与组网。
- **仅中继模式**：`no_tun = true`，不分配虚拟 IP，只为其他节点提供发现和流量转发。

NAT 下的设备（PC、平板等）在 `[[peer]]` 中添加所有公网 VPS 的地址（优先 UDP，TCP 备选），通过它们加入网络后互相发现，能 P2P 就 P2P，不能就走 VPS 中继。

### 安装

> 依赖 unzip，需提前安装。

```bash
wget -O /tmp/easytier.sh "https://raw.githubusercontent.com/EasyTier/EasyTier/main/script/install.sh" && sudo bash /tmp/easytier.sh install --gh-proxy https://ghfast.top/
```

> `--gh-proxy` 可选，默认使用。如果网络可直连 GitHub 可去掉。

安装后二进制在 `/opt/easytier`，配置文件目录在 `/opt/easytier/config/`。

### 配置文件模板

配置项含义见 https://easytier.cn/guide/network/configurations.html 。

```toml
instance_name = "<INSTANCE_NAME>"
ipv4 = "10.144.18.x"
dhcp = false
listeners = [
    "tcp://0.0.0.0:11010",
    "udp://0.0.0.0:11010",
    "wg://0.0.0.0:11011",
    "ws://0.0.0.0:11011/",
    "wss://0.0.0.0:11012/",
]
exit_nodes = []

[network_identity]
network_name = "<NETWORK_NAME>"
network_secret = "<NETWORK_SECRET>"

[flags]
default_protocol = "udp"
dev_name = ""
enable_encryption = true
enable_ipv6 = true
mtu = 1380
latency_first = false
enable_exit_node = false
no_tun = false
use_smoltcp = false
relay_network_whitelist = "*"
disable_p2p = false
p2p_only = false
relay_all_peer_rpc = false
disable_tcp_hole_punching = false
disable_udp_hole_punching = false
private_mode = true
enable_quic_proxy = true
multi_thread = true
```

相对 `default.conf` 改动的关键参数：

- `dhcp = false` + `ipv4 = "10.144.18.x"`：关闭 DHCP，手动指定虚拟 IP，需要分配一个未使用的地址，询问用户。也可以设置 `dhcp = true` 并将 `ipv4` 写为 `10.144.18.0/24` 自动分配。
- `network_name` / `network_secret`：组网凭证，只有相同 name + secret 的节点才能互相发现和通信。**`network_secret` 必须用强随机值**（如 `head -c 32 /dev/urandom | base64`），不要用域名、项目名等可猜的字符串——`private_mode` 这道门的强度全靠它。
- `private_mode = true`：只允许相同 network_name + network_secret 的节点接入（程序默认 `false`）。这是堵掉「坑 2」（被陌生网络白嫖中继）的关键，机制见「隐私与转发控制」。
- `enable_quic_proxy = true`：让 EasyTier 用 QUIC 代理虚拟网内的 TCP 流。适合公网或 NAT 链路有丢包、抖动时的 Caddy 反代、code-server、zellij、WebDAV 等 TCP 服务。生效时可在 `easytier-cli proxy` 中看到 `transport_type = Quic`。
- `multi_thread = true`：使用多线程运行时。它不是修复丢包的核心参数，但在多连接转发、加密和代理并发时可能提高吞吐稳定性。**程序默认本来就是 `true`**，所以模板写 `true` 只是显式声明、不算改动。官方还提供 `multi_thread_count`（程序默认 `2`），不默认写入；需要固定线程数时再按机器 CPU 和实际压测结果添加。

> 模板里**不写** `rpc_portal`：这个键在配置文件里是失效的（被静默忽略），写了也没用，原因见「失效键说明」。

### 启动服务

将配置文件写入 `/opt/easytier/config/`，然后以配置文件名（不含 `.conf`）启动服务：

```bash
systemctl start easytier@<配置文件名>
```

### 防火墙

如果启用了 ufw，需要开放 11010 端口（TCP + UDP）：

```bash
sudo ufw status | grep -q "^Status: active" || exit 0
sudo ufw allow 11010/tcp
sudo ufw allow 11010/udp
```

## 配置项详解

### 隐私与转发控制

EasyTier 节点对**外部网络**（network_name/secret 与自己不同的节点）做不做转发，由两道独立的门决定，源码里按先后顺序检查：

1. **`private_mode`（第一道门，`peer_manager.rs`）**：为 `true` 时，任何外部网络的连接在握手阶段就被拒（`SecretKeyError`），后面的白名单逻辑根本不会走到。这是最严的一道门。
2. **`relay_network_whitelist` + `relay_all_peer_rpc`（第二道门，`foreign_network_manager.rs`，仅在 `private_mode = false` 时才到达）**：
   - `relay_network_whitelist` 控制**数据中继**——`"*"` 放行所有外部网络，`""` 全部禁止，也支持通配符如 `"net1 net2*"`。在白名单里 → 转发它的数据流量。
   - `relay_all_peer_rpc` 只在某外部网络**不在**白名单时才起作用，决定是「整条连接拒掉」还是「只放它的 RPC 包进来帮它打洞、但不转发数据」。

四种组合下，你的节点对陌生网络的实际行为：

| `private_mode` | `relay_network_whitelist` | `relay_all_peer_rpc` | 对陌生网络的行为 |
|---|---|---|---|
| `true` | （忽略） | （忽略） | 握手即拒，什么都不做 |
| `false` | `"*"`（含 `default.conf` 默认） | （忽略） | **数据 + RPC 全转发**（门户大开） |
| `false` | `""` | `true` | 只放 RPC 帮对方打洞，不转发数据 |
| `false` | `""` | `false` | 握手即拒，什么都不做 |

注意第二行就是 `default.conf` 改了 secret、但没加 `private_mode` 的状态——白名单默认 `"*"`，所以陌生网络的数据照样转发，`relay_all_peer_rpc = false` 在这里**完全不起作用**（它只在白名单不覆盖时才被检查）。这正是「坑 2」的根因。本文模板用 `private_mode = true` 直接锁死第一道门。

> 顺带澄清一个常见混淆：上面说的「转发 / 中继」和节点去连 STUN 是两回事。STUN 是节点**自己出门**向第三方服务器问"我的公网地址是什么"（client 角色，见「坑 4」）；这里的转发是节点**帮别的节点**传数据或传 RPC（facilitator 角色）。前者跟"别人能否利用你"无关。

### 默认值对照

> 「默认值」要分两类，二者经常不同：
> 1. **安装脚本写进 `default.conf` 的值**——wget 装完后 `/opt/easytier/config/default.conf` 里实际写死的初值（来自 `script/install.sh`）。
> 2. **程序内置默认值**——配置文件里**不写**该项时程序回退的值（flags 来自 `easytier/src/common/config.rs` 的 `gen_default_flags()`）。
>
> 例如 `default_protocol`：安装脚本写 `"udp"`，但程序内置默认是 `"tcp"`。
>
> （以下默认值与"失效"说明均按 EasyTier 源码核对，核对版本 v2.6.4；这不是 2.6.4 才出现的变化——更高版本如有出入请重新核对源码。）

**安装脚本写入的 `default.conf` 原文：**

```toml
instance_name = "default"
dhcp = true
listeners = [
    "tcp://0.0.0.0:11010",
    "udp://0.0.0.0:11010",
    "wg://0.0.0.0:11011",
    "ws://0.0.0.0:11011/",
    "wss://0.0.0.0:11012/",
]
exit_nodes = []
rpc_portal = "0.0.0.0:0"

[[peer]]
uri = "tcp://public.easytier.top:11010"

[network_identity]
network_name = "default"
network_secret = "default"

[flags]
default_protocol = "udp"
dev_name = ""
enable_encryption = true
enable_ipv6 = true
mtu = 1380
latency_first = false
enable_exit_node = false
no_tun = false
use_smoltcp = false
foreign_network_whitelist = "*"
disable_p2p = false
p2p_only = false
relay_all_peer_rpc = false
disable_tcp_hole_punching = false
disable_udp_hole_punching = false
```

这份 `default.conf` 要点：① 用 `dhcp = true` 自动分配，不写静态 `ipv4`；② 带一个公共种子节点 `tcp://public.easytier.top:11010`；③ `network_name`/`network_secret` 都是 `"default"`（**任何人都能进这个默认网络，正式部署必须改**）；④ 不含 `private_mode`、`enable_quic_proxy`、`multi_thread`、`multi_thread_count`、`enable_kcp_proxy`——这些靠程序内置默认值；⑤ 里面的 `rpc_portal` 和 `foreign_network_whitelist` 两个键其实已失效（见「失效键说明」）。

**本文模板涉及的配置项，两类默认值对照：**

| 配置项 | 安装脚本 default.conf | 程序内置默认值（conf 不写时） | 备注 |
|---|---|---|---|
| `instance_name` | `"default"` | `"default"` | |
| `dhcp` | `true` | `false` | |
| `ipv4` | 不写（靠 dhcp） | 无 | |
| `listeners` | 见上（5 个） | 省略时按端口 `11010` 自动展开同一组 | |
| `exit_nodes` | `[]` | `[]` | |
| `rpc_portal` | `"0.0.0.0:0"` | **配置文件中此键不生效**（见「失效键说明」①） | |
| `network_name` | `"default"` | `"default"` | |
| `network_secret` | `"default"` | `""`（空） | |
| `default_protocol` | `"udp"` | **`"tcp"`** | 安装脚本显式改成 udp |
| `dev_name` | `""` | `""` | |
| `enable_encryption` | `true` | `true` | |
| `enable_ipv6` | `true` | `true` | |
| `mtu` | `1380` | `1380` | |
| `latency_first` | `false` | `false` | |
| `enable_exit_node` | `false` | `false` | |
| `no_tun` | `false` | `false` | |
| `use_smoltcp` | `false` | `false` | |
| `relay_network_whitelist` | `"*"`（写成旧名 `foreign_network_whitelist`，已失效，见「失效键说明」②） | `"*"` | |
| `disable_p2p` | `false` | `false` | |
| `p2p_only` | `false` | `false` | |
| `relay_all_peer_rpc` | `false` | `false` | |
| `disable_tcp_hole_punching` | `false` | `false` | |
| `disable_udp_hole_punching` | `false` | `false` | |
| `private_mode` | 不写 | **`false`** | 模板设 `true` 才生效 |
| `enable_quic_proxy` | 不写 | **`false`** | 模板设 `true` 才生效 |
| `multi_thread` | 不写 | **`true`** | 模板写 `true` 与默认一致，不算改动 |
| `multi_thread_count` | 不写 | **`2`** | 需固定线程数再显式写 |
| `enable_kcp_proxy` | 不写 | `false` | |

### 失效键说明

`default.conf` 和一些老文档里有两个键其实不生效，写了会被静默忽略：

1. **`rpc_portal` 在配置文件里不生效。** `easytier-core` 用 `NetworkInstanceManager` 架构：管理 RPC 端口由命令行 `--rpc-portal`（或环境变量 `ET_RPC_PORTAL`）决定，进程级、全局只有一个；配置文件被加载成"网络实例"，而实例配置结构体里**没有 `rpc_portal` 字段**——所以 `default.conf` 的 `rpc_portal = "0.0.0.0:0"` 会被 serde 当未知键静默忽略。systemd unit（`easytier-core -c %i.conf`）不带 `--rpc-portal`，于是 RPC 端口回退为：绑 `0.0.0.0`、端口取 `15888..15900` 第一个空闲端口（通常 15888）。但**默认带 IP 白名单 `127.0.0.0/8` + `::1/128`**，非环回来源会被直接拒绝——所以虽然 bind 在 `0.0.0.0`，默认仍只有本机能连，并未真正"暴露到公网"。要改绑定地址得用 `--rpc-portal`（可仿照下面 `ET_HOSTNAME` 的 systemd override 写法，设 `ET_RPC_PORTAL`），改不动的是配置文件那行。所以本文模板干脆不写它。

2. **白名单字段真名是 `relay_network_whitelist`，不是 `foreign_network_whitelist`。** 源码里这个 flag 叫 `relay_network_whitelist`（CLI `--relay-network-whitelist`，环境变量 `ET_RELAY_NETWORK_WHITELIST`，默认 `"*"`）。安装脚本和老文档用的 `foreign_network_whitelist` 不是合法键、会被静默忽略。因为默认就是 `"*"`（全放行），写成旧名时"恰好"和默认行为一致所以没人察觉；但若想写 `foreign_network_whitelist = ""` 来禁止外部网络转发，**这写法不会生效**，必须写 `relay_network_whitelist = ""`。本文模板已改用真名。

## 可选功能

### 自定义节点显示名称

EasyTier 在 peer list 中默认显示系统主机名（`hostname`）。如需自定义显示名称，通过 systemd override 设置 `ET_HOSTNAME` 环境变量：

```bash
sudo systemctl edit easytier@<配置文件名>
```

添加：

```ini
[Service]
Environment="ET_HOSTNAME=自定义名称"
```

保存后 `systemctl daemon-reload && systemctl restart easytier@<配置文件名>` 生效。

### 出口节点（Exit Node）

出口节点功能相当于搭建 VPN：让客户端的所有非虚拟网络流量通过指定的服务器出去。需要两端配合：

- **服务端**：设置 `enable_exit_node = true`，允许自己接收并转发出口流量。
- **客户端**：在 `exit_nodes` 中填入服务端的虚拟 IP（如 `exit_nodes = ["10.144.18.1"]`），访问非虚拟网络 IP 时流量会被路由到该出口节点。

此功能不影响节点发现和组网，只控制流量转发行为。

## 排障记录

### Alibaba ↔ DESKTOP 慢速（2026-05）

现象：`iperf3 -c 10.144.18.66 -p 5201` 一度只有 1-2 Mbit/s，TCP 重传很高，`easytier-cli peer` 显示 DESKTOP peer loss 约 9%。Caddy 本身只是反代到 `10.144.18.10`，不是瓶颈。

消融测试结论：

- 重启 EasyTier 后重新建链 / 重新打洞是从 1-2 Mbit/s 恢复到几十 Mbit/s 的主因；回到原始配置后仍有约 25.9 Mbit/s，没有再掉回 1-2 Mbit/s。
- `enable_quic_proxy = true` 对 Caddy 反代方向有明确意义，`easytier-cli proxy` 能看到 `Quic` 连接，适合保留。
- `multi_thread = true` 不是决定项，但完整配置组在测试中跑到约 93.3 Mbit/s，去掉后约 37.0 Mbit/s；考虑到 Alibaba 有多路 Caddy 反代和远控连接，默认保留。
- `mtu` 从 1380 改 1360 不是关键；`mtu = 1380 + enable_quic_proxy = true` 仍可跑到约 53.2 Mbit/s。因此模板不为这次问题额外改 MTU。
- `enable_kcp_proxy = false` 只是显式默认值，不写入模板。
