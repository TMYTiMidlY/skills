# Hysteria2 服务端搭建（落地侧，独立 systemd 服务）

> 这块是**服务端落地**：在一台 VPS 上把 Hysteria2 作为**独立服务**跑起来（不经 3x-ui 面板）。客户端怎么配、怎么测吞吐 / 验证 Brutal、DNS/WebRTC 泄漏排查见 [mihomo.md](mihomo.md)；服务端 `ignoreClientBandwidth`/`bandwidth` 如何影响客户端 Brutal 也在 mihomo.md。想在 **3x-ui 面板里加 Hysteria2 inbound**（而非独立服务），以及带宽 / 丢包质量测试，见 `vps-maintenance` skill。

在已有 `VLESS + WS + TLS + Caddy + 3x-ui/Xray` 节点时，Hysteria2 适合作为差异化备用：它走 QUIC/UDP，和 TCP 443、Caddy 反代、WebSocket 不是同一条链路。不要为了“稳定”把 VLESS 换成 VMess；更优先考虑增加不同协议或不同服务商/地区的备用。

服务端优先按 Hysteria2 官方脚本安装，并让它独立监听 UDP 端口，避免改动现有 Caddy/3x-ui：

```bash
HYSTERIA_USER=root bash <(curl -fsSL https://get.hy2.sh/)
```

如果服务器已由 Caddy 管理证书，不要直接让 systemd 服务读取 Caddy 私有证书目录；`NoNewPrivileges` / capability 限制可能导致 root 服务也报 `tls.cert: permission denied`。更稳的做法是复制当前证书到 `/etc/hysteria/`，配置 Hysteria2 读取 root-owned 副本：

```yaml
listen: :<udp-port>

tls:
  cert: /etc/hysteria/<domain>.crt
  key: /etc/hysteria/<domain>.key

auth:
  type: password
  password: <random-password>

obfs:
  type: salamander
  salamander:
    password: <random-obfs-password>
```

同时放行 UDP 端口，并提醒用户云厂商安全组也要放行：

```bash
sudo ufw allow <udp-port>/udp
sudo systemctl enable --now hysteria-server.service
sudo systemctl status hysteria-server.service
```

验证时看三处：

- `systemctl status hysteria-server.service`
- `ss -lunp | grep <udp-port>`
- 客户端/Mihomo 的节点 delay

若复制 Caddy 证书，后续要补证书同步和重启机制，避免 Caddy 续期后 Hysteria2 继续使用旧副本。
