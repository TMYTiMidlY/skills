---
name: network
description: 处理本机与远端的网络互通、WSL网络、远程接入与私网组网。按实际文档中的主题入口分层排障。
---

# Network

本 skill 索引本机与远端的网络互通、远程接入及私网组网。

## 共享 Linux 节点部署

在共享 Linux 节点上组合 EasyTier、双层 Caddy/caddy-security，以及按 UID 分配端口的多用户 Zellij Web / VS Code Serve Web；包含 OAuth Cookie 隔离、Zellij token 注入、systemd 模板与黑屏排障，见 [references/setup.md](references/setup.md)。

## 远程接入（RDP / 向日葵 / serve-web）

从别的设备接入控制本机、或把本机开发环境暴露到浏览器：RDP / 向日葵远程桌面、会话管理（tsdiscon / logoff）、RDP 缩放修复、VS Code serve-web（浏览器访问本机开发环境，含 WSL NAT 下的远程访问链路）见 [references/remote.md](references/remote.md)。WSL 入站 portproxy 链路细节在 wsl.md。

## WSL ↔ Windows 网络管道

WSL2 与 Windows 宿主、远端之间的互通与排障：WSL Mirror / NAT、Docker Desktop 与 wsl --shutdown、portproxy / wslrelay 入站服务、IPv6 dual-stack #14154、全双工 wslrelay #10688，见 [references/wsl.md](references/wsl.md)。

## EasyTier 客户端（Windows）

EasyTier 组网的 Windows 客户端：安装、TOML 配置模板、Peer 配置、与 VPS 服务端的差异、原生 Windows 服务安装（`easytier-cli service`，非 NSSM）、QUIC proxy 坑、不在 WSL 内跑 EasyTier（用宿主机、MTU 坑）、Windows 防火墙见 [references/easytier.md](references/easytier.md)。VPS 服务端完整安装与配置（全 listener、出口节点、中继策略等）由 `vps-maintenance` skill 覆盖。
