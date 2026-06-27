---
name: network
description: 处理本机与远端的网络互通、WSL网络、远程接入与私网组网。按实际文档中的主题入口分层排障。
---

# Network

本 skill 索引本机与远端的网络互通、远程接入及私网组网。

## WSL / Windows 网络管道与组网

RDP / 向日葵、WSL Mirror / NAT、VS Code serve-web、WSL / Docker 入站 portproxy / wslrelay、EasyTier 组网与会话管理见 [references/network.md](references/network.md)。

## EasyTier 客户端（Windows）

EasyTier 组网的 Windows 客户端：安装、TOML 配置模板、Peer 配置、与 VPS 服务端的差异、NSSM 服务排障、Windows 防火墙见 [references/easytier.md](references/easytier.md)。VPS 服务端完整安装与配置（全 listener、出口节点、中继策略等）由 `vps-maintenance` skill 覆盖。
