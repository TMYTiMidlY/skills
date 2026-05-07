## 安装 EasyTier

### 组网方案

所有公网 VPS 按下方模板配置，开启 `private_mode`，可选两种模式：
- **加入模式**：分配虚拟 IP，正常参与组网
- **仅中继模式**：`no_tun = true`，不分配虚拟 IP，为其他节点提供发现和流量转发

NAT 下的设备（PC、平板等）在 `[[peer]]` 中添加所有公网 VPS 的地址（优先 UDP，TCP 备选），通过它们加入网络后互相发现，能 P2P 就 P2P，不能就走 VPS 中继。

> 依赖 unzip，需提前安装。

```bash
wget -O /tmp/easytier.sh "https://raw.githubusercontent.com/EasyTier/EasyTier/main/script/install.sh" && sudo bash /tmp/easytier.sh install --gh-proxy https://ghfast.top/
```

> `--gh-proxy` 可选，默认使用。如果网络可直连 GitHub 可去掉。

安装后二进制在 `/opt/easytier`，配置文件目录在 `/opt/easytier/config/`。

参考配置（配置项含义见 https://easytier.cn/guide/network/configurations.html ）：

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
rpc_portal = "127.0.0.1:15888"

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
foreign_network_whitelist = "*"
disable_p2p = false
p2p_only = false
relay_all_peer_rpc = false
disable_tcp_hole_punching = false
disable_udp_hole_punching = false
private_mode = true
enable_quic_proxy = true
multi_thread = true
```

相对 default.conf 改动的关键参数：

- `dhcp = false` + `ipv4 = "10.144.18.x"`：关闭 DHCP，手动指定虚拟 IP，需要分配一个未使用的地址，询问用户。也可以设置 `dhcp = true` 并将 `ipv4` 写为 `10.144.18.0/24` 自动分配。
- `rpc_portal = "127.0.0.1:15888"`：管理 RPC 只监听本地，不暴露到公网。default 用 `0.0.0.0:0` 会监听所有网卡。
- `network_name` / `network_secret`：组网凭证，只有相同 name + secret 的节点才能互相发现和通信。
- `private_mode = true`：只允许相同 network_name + network_secret 的节点接入。开启后外部节点在密码验证阶段就会被拒绝，`foreign_network_whitelist` 和 `relay_all_peer_rpc` 不再生效。不开的话，白名单内的其他网络可以借用你的节点做中继。
- `enable_quic_proxy = true`：让 EasyTier 用 QUIC 代理虚拟网内的 TCP 流。适合公网或 NAT 链路有丢包、抖动时的 Caddy 反代、code-server、zellij、WebDAV 等 TCP 服务。生效时可在 `easytier-cli proxy` 中看到 `transport_type = Quic`。
- `multi_thread = true`：使用多线程运行时。它不是修复丢包的核心参数，但在多连接转发、加密和代理并发时可能提高吞吐稳定性。官方还提供 `multi_thread_count`，不默认写入；需要固定线程数时再按机器 CPU 和实际压测结果添加。

### 启动服务与防火墙

安装完成后将配置文件写入该目录，然后以配置文件名启动服务：

```bash
systemctl start easytier@<配置文件名>
```

如果启用了 ufw，需要开放 11010 端口（TCP + UDP）：

```bash
sudo ufw status | grep -q "^Status: active" || exit 0
sudo ufw allow 11010/tcp
sudo ufw allow 11010/udp
```

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

### 隐私与转发控制

三个参数配合控制外部网络（不同 network_name/secret 的节点）能否利用你的节点：

- `foreign_network_whitelist`：控制允许哪些外部网络通过此节点转发流量。`"*"` 允许所有，`""` 禁止所有，也支持通配符如 `"net1 net2*"`。
- `relay_all_peer_rpc`：当外部网络不在白名单内时，是否仍然帮它转发 RPC 包（仅用于节点发现和 P2P 建连，不转发数据流量）。
- `private_mode`：如果为 true，外部节点必须通过密码验证才能接入，否则直接拒绝连接。这是最严格的一道门。

### Alibaba ↔ DESKTOP 慢速排查记录（2026-05）

现象：`iperf3 -c 10.144.18.66 -p 5201` 一度只有 1-2 Mbit/s，TCP 重传很高，`easytier-cli peer` 显示 DESKTOP peer loss 约 9%。Caddy 本身只是反代到 `10.144.18.10`，不是瓶颈。

消融测试结论：

- 重启 EasyTier 后重新建链 / 重新打洞是从 1-2 Mbit/s 恢复到几十 Mbit/s 的主因；回到原始配置后仍有约 25.9 Mbit/s，没有再掉回 1-2 Mbit/s。
- `enable_quic_proxy = true` 对 Caddy 反代方向有明确意义，`easytier-cli proxy` 能看到 `Quic` 连接，适合保留。
- `multi_thread = true` 不是决定项，但完整配置组在测试中跑到约 93.3 Mbit/s，去掉后约 37.0 Mbit/s；考虑到 Alibaba 有多路 Caddy 反代和远控连接，默认保留。
- `mtu` 从 1380 改 1360 不是关键；`mtu = 1380 + enable_quic_proxy = true` 仍可跑到约 53.2 Mbit/s。因此模板不为这次问题额外改 MTU。
- `enable_kcp_proxy = false` 只是显式默认值，不写入模板。
