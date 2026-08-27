---
name: network
description: 配置或排查 Caddy 反向代理与 caddy-security、OpenWrt、外部 Wi-Fi、远程接入及 WSL/远端网络管道时使用。核心是还原 TLS、认证、DNS、路由和隧道的实际数据路径，再分层处理。
---

# Network

本 skill 索引 Caddy、OpenWrt 设备管理、外部 Wi-Fi 接入本地网络、远程接入、组网管道。受限网络下的 Git clone / submodule 获取由 `git` skill 覆盖；VPS 初始化、安全加固和公网节点质量检测由 `vps-maintenance` skill 覆盖。

## Caddy 与 caddy-security

Caddy 安装、域名/IP 站点、共享 listener、反向代理、证书、Caddyfile、caddy-security OAuth/角色/cookie 与运行态排障见 [references/caddy.md](references/caddy.md)；通过 Admin API 修改运行路由或 caddy-security、处理 autosave/ETag/回滚时见 [references/caddy-admin-api.md](references/caddy-admin-api.md)。按当前任务读取对应 reference。

## OpenWrt 设备管理

OpenWrt 的设备支持、首次安装、镜像类型、升级恢复、BusyBox/procd/apk、LuCI/UCI/ubus、Dropbear SSH、station/WWAN上联、wpad企业认证、局域网VPN出口、设备状态、链路诊断、远程日志、外部历史监控和链路面板，以及小米AX3000T保留原厂启动程序的刷写与恢复案例见 [references/openwrt.md](references/openwrt.md)。面板的单文件页面模板位于 [assets/openwrt-link-dashboard.html](assets/openwrt-link-dashboard.html)。

## 外部 Wi-Fi 接入本地网络

把外部Wi-Fi接入本地网络时，AP/station/网关/CPE的角色组合、路由/桥接/伪桥接、NAT与默认网关位置、Captive Portal、Eduroam、无线传播与漫游、分层测量、整网设备可见性、定向CPE选型、主动/被动PoE、户外安装、穿窗布线、无线Mesh及校园接入案例见 [references/external-wifi-access.md](references/external-wifi-access.md)。

## 共享 Linux 节点

EasyTier、双层 Caddy / OAuth 和多用户 Zellij Web / VS Code Serve Web 的组合部署见 [references/setup.md](references/setup.md)。

## 远程接入

RDP、向日葵、会话管理、缩放修复和 VS Code Serve Web 远程访问见 [references/remote.md](references/remote.md)。

## WSL ↔ Windows 网络管道

WSL Mirror / NAT、portproxy / wslrelay 入站服务暴露见 [references/wsl.md](references/wsl.md)。

## EasyTier 客户端

Windows 客户端安装、TOML、Peer、原生服务、QUIC proxy、MTU 与防火墙见 [references/easytier.md](references/easytier.md)。VPS 服务端由 `vps-maintenance` skill 覆盖。
