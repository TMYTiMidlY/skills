# Proxy Services（3x-ui 服务端侧）

3x-ui 是管理 Xray inbound 的面板（VLESS / VMess / Trojan / Shadowsocks，以及 Hysteria2 等）。本篇只覆盖**服务端经 3x-ui 面板做的配置**。其余分工：

- 客户端节点配置、协议选型 / 性能、Brutal / 拥塞控制、DNS / WebRTC 泄漏排查 → `network` skill 的 `references/mihomo.md`。
- WSL / 宿主网络管道，以及**独立 systemd 版 Hysteria2 服务端搭建**（官方脚本、不经面板）→ `network` skill 的 `references/network.md`。
- 带宽 / 丢包质量测试 → [quality-check.md](quality-check.md)。

## 主节点：VLESS + WS + TLS（3x-ui/Xray + Caddy）

> 骨架占位。要点是：3x-ui 面板建 VLESS inbound → 套 WS + TLS → 由 Caddy 反代复用已有 443 站点（隐藏 + 证书自动续）。具体面板点选步骤随版本变化，按概念照做即可，不在此固化。

## 在 3x-ui 面板里加 Hysteria2 inbound

3x-ui 也能直接管理 Hysteria2 inbound，**和独立 systemd 版二选一**：

- **走 3x-ui**：在面板「入站」里新增一个 Hysteria2 类型 inbound，要处理的就三件事——① 监听 **UDP** 端口；② 证书来源（可复用 Caddy 证书的 root-owned 副本，理由同独立版的 cert 权限坑）；③ 密码 + obfs(salamander)。好处是和现有 VLESS 节点统一在一个面板管、共享客户端 / 流量统计。**端口仍要在防火墙 + 云安全组放行 UDP**。
- **走独立 systemd**（隔离、独立升级、不碰面板）：搭法见 `network` skill 的 `references/network.md`「Hysteria2 服务端搭建」。

> 概念为主：3x-ui 面板版面随版本变，具体点选步骤不在此固化；记住「同一面板加 Hysteria2 inbound + UDP 端口放行 + 证书来源」这三点即可。
