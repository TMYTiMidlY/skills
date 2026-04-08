---
name: desktop-use
description: 操作桌面系统（Windows / macOS）。用户提到 Windows、macOS、RDP、向日葵、WSL 网络、Clash、系统安装激活、Mac 应用、文件格式转换、pandoc、LaTeX、PDF 处理等桌面相关操作时触发。
---

# 桌面系统操作

## 快速命令参考

### 关闭 Clash

```powershell
Get-Process | Where-Object { $_.Name -like "Clash*" } | Stop-Process -Force
```

## 网络与远程连接

RDP、向日葵、WSL 网络排障、Clash 代理 → [references/network.md](references/network.md)

## Windows 系统与 Office

镜像下载与激活指南 → [references/activation.md](references/activation.md)

## Windows 服务器配置

EasyTier 组网、防火墙配置 → [references/server.md](references/server.md)

## macOS

推荐应用（VMware Fusion、Mounty）、权限问题、DS_Store 清理 → [references/macos.md](references/macos.md)

## 格式转换

pandoc 文档转换（LaTeX→Word、Markdown→PDF）、PDF→图片 → [references/format-conversion.md](references/format-conversion.md)
