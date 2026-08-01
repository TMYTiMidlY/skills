---
name: network
description: 处理本机与远端的网络互通、WSL网络、远程接入与私网组网。按实际文档中的主题入口分层排障。
---

# Network

本 skill 索引受限网络下的 Git 获取、远程接入、组网管道。Caddy 反代和网络质量检测由 `vps-maintenance` skill 覆盖。

## 共享 Linux 节点

EasyTier、双层 Caddy / OAuth 和多用户 Zellij Web / VS Code Serve Web 的组合部署见 [references/setup.md](references/setup.md)。

## 受限网络下的 Git 获取

GitHub 的 ghfast 临时改写、GitLab 镜像分流、递归 submodule、完全离线的 bare mirror / bundle，以及只缺目标提交时的对象导入见 [references/git-clone.md](references/git-clone.md)。

## 远程接入

RDP、向日葵、会话管理、缩放修复和 VS Code Serve Web 远程访问见 [references/remote.md](references/remote.md)。

## WSL ↔ Windows 网络管道

WSL Mirror / NAT、portproxy / wslrelay 入站服务暴露见 [references/wsl.md](references/wsl.md)。

## EasyTier 客户端

Windows 客户端安装、TOML、Peer、原生服务、QUIC proxy、MTU 与防火墙见 [references/easytier.md](references/easytier.md)。VPS 服务端由 `vps-maintenance` skill 覆盖。
