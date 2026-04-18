# EasyTier 客户端（Windows）

本文档只覆盖 Windows 上的 EasyTier 客户端配置。VPS 服务端配置见 `vps-maintenance` skill。

## 安装

Windows 版从 [GitHub Releases](https://github.com/EasyTier/EasyTier/releases) 下载 `easytier-windows-x86_64` 压缩包，解压后运行即可。

默认路径：`C:\Users\<USER>\easytier-windows-x86_64\`

## 配置模板

配置文件为 TOML 格式，放在安装目录下（如 `<INSTANCE_NAME>.conf`）：

```toml
instance_name = "<INSTANCE_NAME>"
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
network_name = "<NETWORK_NAME>"
network_secret = "<NETWORK_SECRET>"

[[peer]]
uri = "tcp://public.easytier.top:11010"

[[peer]]
uri = "tcp://<PUBLIC_VPS_HOST>:11010"

[[peer]]
uri = "udp://<PUBLIC_VPS_HOST>:11010"

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

## 与 VPS 服务端配置的差异

| 项目 | Windows 客户端 | VPS 服务端 |
|------|---------------|-----------|
| `[[peer]]` | 需要填写所有 VPS 节点的 TCP/UDP 地址 | 通常不需要（作为被连接方） |
| `listeners` | TCP + UDP + WG（3个） | TCP + UDP + WG + WS + WSS（5个） |
| `enable_exit_node` | `false`（客户端） | 可设为 `true`（出口节点） |

> 服务端完整安装、listener 全集、出口节点、中继策略、systemd 单元等见 `vps-maintenance` skill 的 `easytier` reference。

## Peer 配置说明

`[[peer]]` 定义要主动连接的对端节点。每个 peer 一个 `[[peer]]` 块：

```toml
[[peer]]
uri = "<协议>://<地址>:<端口>"
```

- **协议**：`tcp` 或 `udp`，建议同一节点同时配置两种协议以提高连通性
- **地址**：域名或 IP，VPS 节点推荐用域名（方便 IP 变更后只改 DNS）
- **公共中继**：`tcp://public.easytier.top:11010` 是官方公共节点，用于辅助 P2P 打洞
- **端口**：默认 11010

## 关键参数说明

- `dhcp = false` + `ipv4 = "10.144.18.x/24"`：手动指定虚拟 IP，新节点需分配未使用的地址
- `rpc_portal = "127.0.0.1:15888"`：管理 RPC 只监听本地

## 服务名与 NSSM（排障）

- 显示名 `EasyTier` 对应服务名 `EasyTierService`（可用 `sc getkeyname EasyTier` 核对）
- `nssm restart easytier` 可以重启该服务（通过服务控制接口）
- 若 `nssm get easytier Application` 报 *only valid for services managed by NSSM*，说明当前不是 NSSM 参数托管模式；以 `sc qc EasyTierService` 的 `BINARY_PATH_NAME`（或注册表 `ImagePath`）为准

## Windows 防火墙

EasyTier 首次运行时 Windows 会弹窗询问是否允许网络访问，点击允许后自动创建程序级规则（全端口放行），无需手动添加端口规则。
