# Windows 服务器配置

## EasyTier 组网

### 安装

Windows 版从 [GitHub Releases](https://github.com/EasyTier/EasyTier/releases) 下载 `easytier-windows-x86_64` 压缩包，解压后运行即可。

默认路径：`C:\Users\<USER>\easytier-windows-x86_64\`

### 配置模板

配置文件为 TOML 格式，放在安装目录下（如 `TiMidlY.conf`）：

```toml
instance_name = "TiMidlY"
ipv4 = "10.144.18.x/24"
dhcp = false
listeners = [
    "tcp://0.0.0.0:11010",
    "udp://0.0.0.0:11010",
    "wg://0.0.0.0:11011",
]
exit_nodes = []
rpc_portal = "127.0.0.1:15888"

[network_identity]
network_name = "TiMidlY"
network_secret = "<询问用户>"

[[peer]]
uri = "tcp://public.easytier.top:11010"

[[peer]]
uri = "tcp://lisahost.tmytimidly.com:11010"

[[peer]]
uri = "udp://lisahost.tmytimidly.com:11010"

[[peer]]
uri = "tcp://racknerd.tmytimidly.com:11010"

[[peer]]
uri = "udp://racknerd.tmytimidly.com:11010"

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

### 与 VPS 配置的差异

| 项目 | Windows 客户端 | VPS 服务端 |
|------|---------------|-----------|
| `[[peer]]` | 需要填写所有 VPS 节点的 TCP/UDP 地址 | 通常不需要（作为被连接方） |
| `listeners` | TCP + UDP + WG（3个） | TCP + UDP + WG + WS + WSS（5个） |
| `enable_exit_node` | `false`（客户端） | 可设为 `true`（出口节点） |

### Peer 配置说明

`[[peer]]` 定义要主动连接的对端节点。每个 peer 一个 `[[peer]]` 块：

```toml
[[peer]]
uri = "<协议>://<地址>:<端口>"
```

- **协议**：`tcp` 或 `udp`，建议同一节点同时配置两种协议以提高连通性
- **地址**：域名或 IP，VPS 节点推荐用域名（方便 IP 变更后只改 DNS）
- **公共中继**：`tcp://public.easytier.top:11010` 是官方公共节点，用于辅助 P2P 打洞
- **端口**：默认 11010

### 关键参数说明

- `dhcp = false` + `ipv4 = "10.144.18.x/24"`：手动指定虚拟 IP，新节点需分配未使用的地址
- `rpc_portal = "127.0.0.1:15888"`：管理 RPC 只监听本地

### Windows 防火墙

EasyTier 首次运行时 Windows 会弹窗询问是否允许网络访问，点击允许后自动创建程序级规则（全端口放行），无需手动添加端口规则。

