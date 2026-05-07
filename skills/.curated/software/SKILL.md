---
name: software
description: 本地软件、CLI 工具与自托管服务的配置与排障。涵盖 SSH 与 systemd、Zellij 终端复用与反代、文档格式转换（pandoc/feishu2md/MinerU）、自托管文档分享、WSL 与 Windows 互操作、EasyTier 客户端组网、Hermes agent 部署等。
---

# Software

## SSH

SSH 密钥 passphrase、ssh-agent、RemoteForward 代理转发等通用 SSH 用法见 [references/ssh.md](references/ssh.md)。

## Zellij

Zellij Web client、HTTPS 证书要求、login token/session token、反代注入 Cookie、`default_shell`、Web/xterm 主题分层、Codex 输入框颜色、鼠标选区颜色与 WSL systemd service 写法见 [references/zellij.md](references/zellij.md)。

## Service / systemd

多用户共享服务、systemd 模板单元与按 UID 分配端口见 [references/service.md](references/service.md)。

## 速记

### VS Code serve-web

在当前机器启动一个 VS Code Web 服务，适合临时从浏览器访问这台机器上的开发环境。需要终端一直挂着这个命令；重启或终端关闭后要手动重新执行。

Windows 侧临时服务用 `18080`：

```powershell
code serve-web --host 0.0.0.0 --port 18080 --without-connection-token
```

`--without-connection-token` 表示不要求访问 token；只适合已经有内网、VPN、反代认证等外层保护的场景。

WSL 默认是 NAT 网络，`portproxy` 常用来把 Windows/EasyTier IP 上的端口转到 WSL 服务。常见链路是：

```text
远端 Caddy/Nginx -> Windows EasyTier IP:port
Windows portproxy -> 127.0.0.1:port
WSL localhost forwarding -> WSL 内服务
```

WSL 内配置了很多系统服务，端口按各自服务配置为准。`portproxy` 不会自动唤醒 WSL；建议留一个 WSL 窗口或会话挂着，避免发行版被停掉后远端反代变 502。

常用查询：

```powershell
wsl -l -v
wsl -- ip route show
wsl -- ss -ltnp
netsh interface portproxy show all
netstat -ano | Select-String -Pattern ':8080|:18080|:8082'
curl.exe -k -I https://127.0.0.1:8080/
```

### Mihomo

Mihomo 是 Clash Meta 内核；需要临时启用系统代理、规则代理或 TUN 接管流量时使用。通常要用管理员权限启动，主要是为了创建/管理 TUN 虚拟网卡；也需要终端一直挂着，重启或终端关闭后要手动重新执行。

默认配置文件：

```powershell
%USERPROFILE%\.config\mihomo\config.yaml
```

常用启动：

```powershell
cd "$env:USERPROFILE\mihomo"
.\mihomo.exe
```

## 网络与远程连接

RDP、向日葵、WSL Mirror 模式网络（含 Clash Party / Mihomo 代理与 TUN 对 WSL 路由的影响）、Mihomo / Clash 内核配置与排障、会话管理（tsdiscon / logoff）、MTU 排障见 [references/network.md](references/network.md)。

## 挂载与文件共享

WSL 挂载 Windows 盘、UNC/SMB 共享、`drvfs/9p` 小文件性能、CIFS 凭据与 `mount.cifs` 排障见 [references/mount.md](references/mount.md)。

## EasyTier 客户端（Windows）

EasyTier 组网的 Windows 客户端：安装、TOML 配置模板、Peer 配置、与 VPS 服务端的差异、NSSM 服务排障、Windows 防火墙见 [references/easytier.md](references/easytier.md)。**VPS 服务端完整安装与配置（全 listener、出口节点、中继策略等）见 `vps-maintenance` skill 的 EasyTier reference。**

## Windows / Office 激活

镜像下载（山己几子木）与激活工具（MAS、CMWTAT、Microsoft Office For MacOS）见 [references/activation.md](references/activation.md)。

## macOS 小问题集锦

推荐应用（VMware Fusion、Mounty + macFUSE NTFS 读写）、应用无法打开的权限修复、外置存储隐藏文件（`.DS_Store` / `.Spotlight-V100` / `.Trashes`）阻止与清理见 [references/macos.md](references/macos.md)。

## 格式转换

pandoc 文档转换、Markdown→PDF、PDF→图片、feishu2md 飞书/Lark→Markdown 等见 [references/format-conversion.md](references/format-conversion.md)。

## 自托管 Markdown 文件分享（doc-share）

把本地 Markdown / 文件推到自托管 WebDAV、拿 capability URL 分享链接、以及给 Markdeep viewer 写作的惯例（`[#key]` 引用 vs `[^name]` 脚注可选、GFM 兼容场景反而要避开 `[#key]`、研报长文模板）见 [references/doc-share.md](references/doc-share.md)。上传凭据约定从 `~/.env` 读 `WEBDAV_URL / WEBDAV_USER / WEBDAV_PASS`。

服务端（Caddy site block、WebDAV handler、viewer 实现、目录权限）由 `vps-maintenance` skill 覆盖。如果源文件需要先做格式转换，看 [references/format-conversion.md](references/format-conversion.md)。

## MinerU PDF→Markdown 转换

MinerU（mineru.net）提供 VLM 模型将 PDF 转为 Markdown/JSON，支持公式和表格识别。默认使用云端 API / Open API；未经用户明确允许，不要在本机安装或部署 MinerU。详细流程见 [references/mineru.md](references/mineru.md)。

## Hermes

[NousResearch/hermes-agent](https://github.com/nousresearch/hermes-agent)：Python CLI agent 框架。systemd 常驻服务（gateway / dashboard）配置、`HERMES_HOME` 与身份管理、terminal backend（local / ssh / docker / modal / daytona / singularity）切换、provider 兼容性踩坑、skill 体系（builtin / hub / local 三种来源、install/uninstall、`external_dirs` 挂载外部目录、按项目激活 skill 的缺失与近似解、跨 backend 的 symlink 差异、`--skills` 预加载）见 [references/hermes.md](references/hermes.md)。
