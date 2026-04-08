# 网络与远程连接

## 远程连接方式

- **RDP**：通过异地组网（EasyTier / Tailscale / ZeroTier / 蒲公英等）连接远程桌面。Windows 用 `mstsc`，Linux 用 `xfreerdp` 或 Remmina
- **向日葵**：不需要组网，默认自动判断传输模式——网络条件允许时自动 P2P 直连，否则走服务器中转

### 会话管理

```powershell
tsdiscon        # 断开 RDP 连接，程序继续运行（服务器场景常用）
logoff          # 完全退出登录，关闭所有程序
```

### RDP 缩放不生效

在 PowerShell 中执行 `logoff`，然后重新连接即可。

## WSL Mirror 模式网络

Mirror 模式的 WSL 会同步宿主机所有网卡，包括蒲公英、EasyTier 等虚拟网卡。

正常状态下 `ip route show` 以此开头：

```
default via 10.100.158.254 dev eth1 proto kernel metric 25
```

### Clash Party 代理对路由的影响

#### 系统代理模式

`ip route show` 结果不受影响。需要手动设置环境变量才能让 `curl` 走代理：

```bash
export http_proxy="http://127.0.0.1:7890"
export https_proxy="http://127.0.0.1:7890"
```

注意：`ping` 走 ICMP 协议，不经过 HTTP 代理，始终不通是正常的。

#### 虚拟网卡模式（TUN）

开启后 `ip route show` 会出现大量细分路由，以此开头：

```
0.0.0.0/2 via 198.18.0.2 dev eth8 proto kernel
```

所有流量会被 TUN 网卡接管。

### 异常修复

- **HTTPS 无法访问**：HTTP 正常但 HTTPS 不通，修改 Clash 虚拟网卡的模式（如切换 TUN stack），无需 exit WSL，立即生效
- **轻量修复**：`exit` 退出后重新 `wsl` 进入，刷新路由表
- **完全重启**：在 PowerShell 中执行 `wsl --shutdown`，然后重新 `wsl`

### MTU 问题

曾在 WSL 内部署 EasyTier 时遇到过 MTU 不匹配问题——必须手动降低 EasyTier 的 MTU 以匹配 WSL 网卡的 MTU。

**当前方案**：不再在 WSL 内配置组网，EasyTier 运行在 Windows 宿主机上，避免了此问题。
