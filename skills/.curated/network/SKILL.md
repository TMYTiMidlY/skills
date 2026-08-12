---
name: network
description: 配置或排查客户端代理、远程接入及 WSL/远端网络管道时使用。核心是先还原 DNS、路由和隧道的实际流向，再处理代理或组网工具配置。
---

# Network

本 skill 索引远程接入、组网管道。受限网络下的 Git clone / submodule 获取由 `git` skill 覆盖，Caddy 反代和网络质量检测由 `vps-maintenance` skill 覆盖。

## 共享 Linux 节点

EasyTier、双层 Caddy / OAuth 和多用户 Zellij Web / VS Code Serve Web 的组合部署见 [references/setup.md](references/setup.md)。

## 远程接入

RDP、向日葵、会话管理、缩放修复和 VS Code Serve Web 远程访问见 [references/remote.md](references/remote.md)。

## WSL ↔ Windows 网络管道

WSL Mirror / NAT、portproxy / wslrelay 入站服务暴露见 [references/wsl.md](references/wsl.md)。

## EasyTier 客户端

Windows 客户端安装、TOML、Peer、原生服务、QUIC proxy、MTU 与防火墙见 [references/easytier.md](references/easytier.md)。VPS 服务端由 `vps-maintenance` skill 覆盖。
