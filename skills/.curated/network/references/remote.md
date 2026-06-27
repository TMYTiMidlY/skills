# 远程接入：RDP / 向日葵 / VS Code serve-web

从别的设备接入、控制这台机器，或把这台机器上的开发环境暴露到浏览器。WSL ↔ Windows 的网络管道细节（出站走 Mihomo、portproxy/wslrelay 入站）见 [wsl.md](wsl.md)；独立 Hysteria2 服务端搭建见 [hysteria2.md](hysteria2.md)。

## 远程桌面

- **RDP**：通过异地组网（EasyTier / Tailscale / ZeroTier / 蒲公英等）连接远程桌面。Windows 用 `mstsc`，Linux 用 `xfreerdp` 或 Remmina。
- **向日葵**：不需要组网，默认自动判断传输模式——网络条件允许时自动 P2P 直连，否则走服务器中转。

### 会话管理

```powershell
tsdiscon        # 断开 RDP 连接，程序继续运行（服务器场景常用）
logoff          # 完全退出登录，关闭所有程序
```

### RDP 缩放不生效

在 PowerShell 中执行 `logoff`，然后重新连接即可。

## VS Code serve-web

在当前机器启动一个 VS Code Web 服务，适合临时从浏览器访问这台机器上的开发环境。需要终端一直挂着这个命令；重启或终端关闭后要手动重新执行。

Windows 侧临时服务示例（端口可换，下例用 `18080`）：

```powershell
code serve-web --host 0.0.0.0 --port 18080 --without-connection-token
```

`--without-connection-token` 表示不要求访问 token；**只适合已经有内网、VPN、反代认证等外层保护的场景**——服务直接暴露到公网时务必去掉这个开关或额外加层。

WSL 默认是 NAT 网络，常见的远程访问链路是：

```text
远端 Caddy/Nginx -> Windows EasyTier IP:<port>
Windows portproxy -> 127.0.0.1:<port>
WSL localhost forwarding -> WSL 内服务
```

`portproxy` 配置细节见 [wsl.md](wsl.md)「WSL / Docker 服务暴露（入站：portproxy + wslrelay）」一节；`portproxy` 不会自动唤醒 WSL，建议留一个 WSL 窗口 / 会话挂着，避免发行版被停掉后远端反代直接 502。

排障常用查询：

```powershell
wsl -l -v
wsl -- ip route show
wsl -- ss -ltnp
netsh interface portproxy show all
netstat -ano | Select-String -Pattern ':<port>'
curl.exe -k -I https://127.0.0.1:<port>/
```
