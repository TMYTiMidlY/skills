# EasyTier 客户端（Windows）

本文档只覆盖 Windows 上的 EasyTier 客户端配置。VPS 服务端配置见 `vps-maintenance` skill。

## 安装

推荐官方 Windows 一键脚本 `install.ps1`（**管理员 PowerShell**）：自动从 GitHub Release 拉最新版、解压**整包**到 `C:\Program Files\EasyTier`、并把该目录加进系统 PATH。

```powershell
# 管理员 PowerShell 运行；可选 -Version v2.6.2 / -InstallDir 自定义路径
irm https://raw.githubusercontent.com/EasyTier/EasyTier/main/script/install.ps1 -OutFile "$env:TEMP\et-install.ps1"
& "$env:TEMP\et-install.ps1"
```

装完该目录含 `easytier-core.exe` / `easytier-cli.exe` / `easytier-web.exe` / `easytier-web-embed.exe` / `wintun.dll` 等（`web` 系列做客户端联网用不到，但脚本会整包装下）。脚本**不会**自动注册服务，开机自启按下文「作为系统服务安装」跑 `easytier-cli service install`。

- 脚本源与参数说明：[`script/install.ps1`](https://github.com/EasyTier/EasyTier/blob/main/script/install.ps1)
- 官方安装总览（手动下载 / Docker / Linux 一键 / 源码）：[安装 (命令行程序)](https://easytier.cn/guide/installation.html)；注意 Windows 的 `install.ps1` **未收录**进该文档，只在仓库 `script/` 下

（手动解压 [GitHub Releases](https://github.com/EasyTier/EasyTier/releases) 的 `easytier-windows-x86_64` 压缩包到任意目录其实也能直接跑，只是不挂 PATH、不自动注册服务。）

## 配置模板

配置文件为 TOML 格式，放在安装目录下（如 `<INSTANCE_NAME>.conf`）：

```toml
instance_name = "<INSTANCE_NAME>"
ipv4 = "10.144.18.x/24"
dhcp = false
listeners = [
    "tcp://0.0.0.0:11010",
    "udp://0.0.0.0:11010",
    "wg://0.0.0.0:11011",
]
exit_nodes = []
rpc_portal = "127.0.0.1:15888"

[network_identity]
network_name = "<NETWORK_NAME>"
network_secret = "<NETWORK_SECRET>"

[[peer]]
uri = "tcp://public.easytier.top:11010"

[[peer]]
uri = "tcp://<PUBLIC_VPS_HOST>:11010"

[[peer]]
uri = "udp://<PUBLIC_VPS_HOST>:11010"

[flags]
default_protocol = "udp"
dev_name = ""
enable_encryption = true
enable_ipv6 = true
mtu = 1380
latency_first = false
enable_exit_node = false
no_tun = false
use_smoltcp = false
foreign_network_whitelist = "*"
disable_p2p = false
p2p_only = false
relay_all_peer_rpc = false
disable_tcp_hole_punching = false
disable_udp_hole_punching = false
enable_quic_proxy = false
```

## 与 VPS 服务端配置的差异

| 项目 | Windows 客户端 | VPS 服务端 |
|------|---------------|-----------|
| `[[peer]]` | 需要填写所有 VPS 节点的 TCP/UDP 地址 | 通常不需要（作为被连接方） |
| `listeners` | TCP + UDP + WG（3个） | TCP + UDP + WG + WS + WSS（5个） |
| `enable_exit_node` | `false`（客户端） | 可设为 `true`（出口节点） |

> 服务端完整安装、listener 全集、出口节点、中继策略、systemd 单元等见 `vps-maintenance` skill 的 EasyTier 服务端配置章节。

## Peer 配置说明

`[[peer]]` 定义要主动连接的对端节点。每个 peer 一个 `[[peer]]` 块：

```toml
[[peer]]
uri = "<协议>://<地址>:<端口>"
```

- **协议**：`tcp` 或 `udp`，建议同一节点同时配置两种协议以提高连通性
- **地址**：域名或 IP，VPS 节点推荐用域名（方便 IP 变更后只改 DNS）
- **公共中继**：`tcp://public.easytier.top:11010` 是官方公共节点，用于辅助 P2P 打洞
- **端口**：默认 11010

## 关键参数说明

- `dhcp = false` + `ipv4 = "10.144.18.x/24"`：手动指定虚拟 IP，新节点需分配未使用的地址
- `rpc_portal = "127.0.0.1:15888"`：管理 RPC 只监听本地
- `enable_quic_proxy = false`：不启用 QUIC proxy；需要两端一致修改，避免一端仍走 QUIC

## 作为系统服务安装

EasyTier **自带**服务安装能力，装出来是原生 Windows 服务（无需 NSSM 之类外部包装）。安装入口在 `easytier-cli`，**不是** `easytier-core`（所以 `easytier-core --help` 里看不到 service 子命令）。

> 官方文档：[一键注册服务](https://easytier.cn/guide/network/oneclick-install-as-service.html)（同时覆盖 Linux/Windows，列全可选参数）。

### 初次安装（端到端）

已有 conf 的话，从零做成开机自启服务只多两步（注册 + 启动）：

**1) 下载解压** —— 见上文「安装」，得到同目录下的 `easytier-core.exe` 与 `easytier-cli.exe`（如 `C:\Program Files\EasyTier\`）。

**2) 准备配置** —— 按上文「配置模板」写好 `<INSTANCE>.conf`（填 `instance_name` / `ipv4` / `network_name` / `network_secret` / `[[peer]]`），放到固定路径，建议就放程序目录下。服务化不需要给 conf 加任何特殊字段。

**3) 注册服务** —— 用**管理员权限**的终端（写 SCM 需要提权）：

```text
cd "C:\Program Files\EasyTier"
.\easytier-cli.exe service install -- -c "C:\Program Files\EasyTier\<INSTANCE>.conf"
```

服务名默认 `easytier`（要自定义须写成 `service -n <名字> install …`，`-n` 是 `service` 层参数、不能放 `install` 后）；`--` 之后的参数原样透传给 easytier-core，`-c` 后**写 conf 绝对路径**（服务工作目录和当前 shell 不同，相对路径会找不到）。

**4) 启动并验证**：

```text
.\easytier-cli.exe service start
.\easytier-cli.exe service status     # 期望 Running
```

装好即 `AUTO_START`，此后开机自动拉起、无需任何人登录。

> 卸载 `easytier-cli service uninstall`（会先 stop）。只改了 conf 内容：重启服务即可生效（`service stop` 再 `service start`）；要换 conf 路径/透传参数：`uninstall` 后重新 `install`。

### 原理：Rust `windows-service` / `service-manager`

EasyTier 不借助 NSSM，而是用两个 Rust crate 自己完成服务化：

- **`windows-service`**（Windows 服务控制管理器 SCM 的 Rust 绑定）让 `easytier-core.exe` 本身 **service-aware**：`define_windows_service!` 宏生成服务入口，进程启动时先用 `service_dispatcher::start()` 试连 SCM——被 SCM 拉起就连上、进入服务模式（线程 park 住并响应 SCM 的 start/stop/查询）；在命令行直接敲则连不上 SCM，fallback 当普通 CLI 跑。**同一个 exe「两副面孔」，由"谁启动它"决定**，不需要 `--service` 这类显式开关（所以 `--help` 里也看不到）。
- **`service-manager`**（跨平台服务管理抽象）负责"安装"侧：Windows 上 easytier 用自定义的 `WinServiceManager` 直接调 SCM 的 `create_service`，把 core 注册为 `OWN_PROCESS` + `AutoStart`、依赖 `rpcss`+`dnscache`、账户 `LocalSystem`；同一套抽象在 Linux 生成 systemd unit、macOS 生成 launchd plist。

源码位置：`easytier/src/core.rs`（service_dispatcher 那段）、`easytier/src/service_manager/mod.rs`（`WinServiceManager`）。

**排障核对** —— `sc qc easytier` 或 `Get-CimInstance Win32_Service -Filter "Name='easytier'"` 应看到：

| 字段 | 值 |
|------|----|
| 服务名 | `easytier` |
| BINARY_PATH_NAME | `"\\?\C:\Program Files\EasyTier\easytier-core.exe" -c "...conf"`（`\\?\` 是 canonicalize 产物） |
| DEPENDENCIES | `rpcss` + `dnscache`（install 写死的依赖） |
| START_TYPE / 账户 | `AUTO_START` / `LocalSystem`（session 0 开机即起，不需用户登录，故自启稳定） |

注册表无 `HKLM\SYSTEM\CurrentControlSet\Services\easytier\Parameters` 子键。

## QUIC proxy 坑点

`enable_quic_proxy` 不是稳定通用开关。本次遇到远端 Caddy 访问 Windows EasyTier IP 超时，但 Windows 本机服务和 portproxy 都正常；EasyTier 侧表现为源端代理连接卡在 `SynReceived / Quic`，目标侧 `easytier-cli proxy` 看不到对应连接。

处理方式是源端和目标端都设为：

```toml
enable_quic_proxy = false
```

然后重启两端 EasyTier。只改一端可能仍走 QUIC。

## Windows 防火墙

EasyTier 首次运行时 Windows 会弹窗询问是否允许网络访问，点击允许后自动创建程序级规则（全端口放行），无需手动添加端口规则。
