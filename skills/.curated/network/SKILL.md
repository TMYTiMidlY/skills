---
name: network
description: 本机/客户端的网络与代理配置、泄漏控制，以及 WSL ↔ Windows ↔ 远端的网络管道配置与排障。涵盖 Mihomo/Clash 客户端（配置目录与热重载、REST API 运行态排障、规则与节点组、协议选型与性能、Hysteria2 Brutal/拥塞控制、TUN 路由、DNS/WebRTC 泄漏原理与浏览器实测）、WSL Mirror/NAT 网络（portproxy/wslrelay 入站、出站走宿主 Mihomo、VS Code serve-web、RDP、EasyTier 组网）、以及 Hysteria2 服务端独立搭建。遇到代理不通/漏真实 IP/分流不准、WSL↔Windows 互通、组网这类问题来这里。服务端经 3x-ui 面板的配置在 vps-maintenance skill。
---

# Network

本机 / 客户端的网络与代理配置、泄漏控制，以及 WSL ↔ Windows ↔ 远端的网络管道。服务端落地（3x-ui 面板、Caddy、质量检测）由 `vps-maintenance` skill 覆盖。

## Mihomo / Clash 客户端与泄漏控制

Mihomo / Clash 内核本身的客户端运维：默认配置位置与热重载、REST API 运行态排障、`HTTPS_PROXY` 只决定入口不决定出口（rule+group 链路 `.now` 排障）、REST API 改节点 + 测延迟（emoji group 名 EscapeDataString）、协议选型与性能（vless+ws vs Hysteria2、jitter、落地 IP 疑似被屏蔽）、Hysteria2 的 Brutal/BBR 拥塞控制（`up`/`down` + 服务端 `ignoreClientBandwidth` 协商、源码出处）、实测吞吐方法、TUN 路由规则（IP-CIDR/route-exclude 不等于 bypass）、VLESS+ws+TLS 客户端配置、从源码构建 mihomo（Windows）；第二部分是泄漏控制：DNS 泄漏原理与 `dns-hijack`/`enhanced-mode`、WebRTC 泄漏原理与处理、用 bash.ws / browserleaks / 自写 STUN 探针**直接实测** DNS 与 WebRTC 泄漏（含 TUN vs no-TUN、浏览器策略、反检测浏览器对照）见 [references/mihomo.md](references/mihomo.md)。

## WSL / Windows 网络管道、组网与 Hysteria2 服务端

RDP / 向日葵、WSL Mirror 模式网络（含 Clash/Mihomo 代理与 TUN 对 WSL 路由的影响）、VS Code serve-web（浏览器访问本机开发环境 + WSL portproxy 链路）、WSL NAT 出站怎么进 Windows 宿主 Mihomo、WSL/Docker 服务入站（`netsh portproxy` + wslrelay 的 IPv6 dual-stack #14154 坑：纯 v4 监听才不 RST）、EasyTier/WSL 组网杂项、会话管理（tsdiscon / logoff），以及**独立 systemd 版 Hysteria2 服务端搭建**（官方脚本安装、复用 Caddy 证书、放行 UDP 端口；想经 3x-ui 面板加 Hysteria2 inbound 则见 `vps-maintenance` skill 的 `references/proxy.md`）见 [references/network.md](references/network.md)。
