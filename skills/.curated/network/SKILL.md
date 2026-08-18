---
name: network
description: 配置或排查 OpenWrt 路由器、外部 Wi-Fi 接入本地网络、客户端代理、泄漏防护、远程接入及 WSL/远端网络管道时使用。核心是先还原设备角色、认证、DNS、路由和隧道的实际数据路径，再分层处理无线链路或代理与组网配置。
---

# Network

本 skill 索引 OpenWrt 设备管理、外部 Wi-Fi 接入本地网络、客户端代理、远程接入、组网管道与服务端节点入口。受限网络下的 Git clone / submodule 获取由 `git` skill 覆盖，Caddy 反代和公网节点质量检测由 `vps-maintenance` skill 覆盖。

## OpenWrt 设备管理

OpenWrt 的设备支持、首次安装、镜像类型、升级恢复、BusyBox/procd/apk、LuCI/UCI/ubus、Dropbear SSH、网络配置与状态接口、局域网 VPN/代理出口、设备与客户端统计、无线链路分层测量、远程日志、外部历史监控和链路面板，以及小米 AX3000T 保留原厂启动程序的刷写案例见 [references/openwrt.md](references/openwrt.md)。面板的单文件页面模板位于 [assets/openwrt-link-dashboard.html](assets/openwrt-link-dashboard.html)。

## 外部 Wi-Fi 接入本地网络

把外部 Wi-Fi 转为受控 LAN，再经下游 AP 覆盖本地网络时，网关/AP/station 的角色组合、AP 模式下的设备可见性、WWAN/NAT、Captive Portal、企业认证、漫游缓存、RSSI/SNR/MCS/NSS、整网设备统计、定向 CPE 和校园接入案例见 [references/external-wifi-access.md](references/external-wifi-access.md)。

## Mihomo / Clash 客户端与泄漏控制

Mihomo 产品与配置发现、GUI 配置链、流量选择、协议性能、REST API、TUN 路由，以及 DNS / WebRTC 泄漏原理和探测见 [references/mihomo.md](references/mihomo.md)。

## 共享 Linux 节点

Mihomo TUN、systemd-resolved、EasyTier、双层 Caddy / OAuth 和多用户 Zellij Web / VS Code Serve Web 的组合部署见 [references/setup.md](references/setup.md)。该文描述整套共享节点；Mihomo 本身的配置、运行态和泄漏理论仍以 [mihomo.md](references/mihomo.md) 为准。

## 远程接入

RDP、向日葵、会话管理、缩放修复和 VS Code Serve Web 远程访问见 [references/remote.md](references/remote.md)。

## WSL ↔ Windows 网络管道

WSL Mirror / NAT、宿主 Mihomo 出站、portproxy / wslrelay 入站和 tun2socks 方案见 [references/wsl.md](references/wsl.md)。

## 3x-ui 面板

3x-ui / Xray 的直连端口与 Caddy 前置两类部署、REALITY、WS / gRPC、Hysteria2 inbound 和面板生效链路见 [references/3x-ui.md](references/3x-ui.md)。

## Hysteria2 服务端

独立 systemd 服务、证书复用和 UDP 放行见 [references/hysteria2.md](references/hysteria2.md)；面板内 Hysteria2 inbound 见 [3x-ui.md](references/3x-ui.md)，客户端参数与 Brutal 验证见 [mihomo.md](references/mihomo.md)。

## EasyTier 客户端

Windows 客户端安装、TOML、Peer、原生服务、QUIC proxy、MTU 与防火墙见 [references/easytier.md](references/easytier.md)。VPS 服务端由 `vps-maintenance` skill 覆盖。
