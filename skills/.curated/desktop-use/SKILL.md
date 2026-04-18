---
name: desktop-use
description: Windows / macOS 桌面系统操作。用户遇到桌面端的软件使用、系统配置、网络连接、远程桌面等问题时触发。
---

# 桌面系统操作

## 快速命令参考

### 关闭 Clash

```powershell
Get-Process | Where-Object { $_.Name -like "Clash*" } | Stop-Process -Force
```

## 网络与远程连接

RDP、向日葵、WSL Mirror 模式网络（含 Clash Party 代理对 WSL 路由的影响）、会话管理（tsdiscon/logoff）、MTU 排障 → [references/network.md](references/network.md)

## Windows 系统与 Office

镜像下载与激活指南 → [references/activation.md](references/activation.md)

## Windows 服务器配置

EasyTier 组网（安装、TOML 配置模板、Peer 配置、与 VPS 差异）、Windows 防火墙 → [references/server.md](references/server.md)

## Hermes

Gateway / Dashboard systemd 服务、profile 与 `HERMES_HOME`、开机自启、反代暴露、npm/bun 构建限制；terminal.backend（local / ssh / docker / modal / daytona / singularity）切换与数据流、SSH_AUTH_SOCK 继承坑；`hermes auth` 重置命令；provider 实测（MiniMax Coding Plan `/anthropic` 路径坑、Gemini `AQ.` 前缀 key 与 OpenAI 兼容端点不兼容） → [references/hermes.md](references/hermes.md)

## macOS

推荐应用（VMware Fusion、Mounty + macFUSE NTFS 读写）、应用无法打开的权限修复、外置存储隐藏文件（DS_Store/Spotlight/Trashes）阻止与清理 → [references/macos.md](references/macos.md)
