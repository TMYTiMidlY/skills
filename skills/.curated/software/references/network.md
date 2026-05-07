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
default via <gateway-ip> dev eth1 proto kernel metric 25
```

### 异常修复

- **轻量修复**：`exit` 退出后重新 `wsl` 进入，刷新路由表
- **完全重启**：在 PowerShell 中执行 `wsl --shutdown`，然后重新 `wsl`

如果 WSL 内只剩 `lo` 网卡、`ip route` 没有默认路由、`/etc/resolv.conf` 缺失或 DNS 报 `Temporary failure in name resolution`，通常是 WSL VM 网络层异常；本机实测 `wsl --terminate Ubuntu` 后仍只有 `lo`，`wsl --shutdown` 后才恢复 eth 网卡、默认路由和 DNS。遇到这种状态时，明确告知会影响 Docker Desktop / 其他 WSL 发行版，然后用 `wsl --shutdown` 重建整个 WSL2 VM 网络。

### Docker Desktop 与 `wsl --shutdown`

`wsl --shutdown` 的语义是立即终止所有运行中的 WSL 发行版并关闭 WSL2 lightweight VM，不是只重启默认发行版。因此 Docker Desktop 使用 WSL2 backend 时，`docker-desktop` 发行版也会被停止，正在运行的容器可能中断。

Docker Desktop 的 WSL2 backend 使用自己的 `docker-desktop` WSL 发行版运行 Docker Engine，并可为用户发行版开启 WSL integration。Docker Desktop GUI 或后台服务仍在运行时，可能在 `wsl --shutdown` 后很快重新拉起 `docker-desktop` 或集成的发行版，所以观察 `wsl -l -v` 时会感觉“shutdown 没生效”或“Docker 没停”。需要判断 WSL VM 是否真的重启过时，可在重启前后对比 Linux boot id：

```powershell
wsl -d Ubuntu -- cat /proc/sys/kernel/random/boot_id
wsl --shutdown
wsl -d Ubuntu -- cat /proc/sys/kernel/random/boot_id
```

两次 boot id 不同说明 WSL VM 已重启；相同则说明没有发生同一次 Linux 内核实例的重启。排障顺序：

1. 只修某个发行版的普通进程/挂载/用户态异常时，可先用 `wsl --terminate Ubuntu`，避免影响 Docker Desktop。
2. 发行版内只有 `lo`、没有 eth 网卡和默认路由时，使用 `wsl --shutdown`；执行前提醒 Docker/容器会被停一次。
3. 若不希望 Docker Desktop 自动重新拉起 WSL，先退出 Docker Desktop，再执行 `wsl --shutdown`。

参考：

- Microsoft WSL basic commands: `wsl --shutdown` terminates all running distributions and the WSL2 VM.
- Docker Desktop WSL2 backend: Docker Desktop uses a `docker-desktop` WSL distribution for the Docker engine.
- Docker Resource Saver on WSL: Resource Saver does not stop the whole WSL VM because it is shared by all WSL distributions.
