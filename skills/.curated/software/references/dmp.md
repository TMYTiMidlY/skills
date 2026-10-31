# DMP（饥荒联机版管理平台）容器化部署与运维

> 上游仓库：[`miracleEverywhere/dst-management-platform-api`](https://github.com/miracleEverywhere/dst-management-platform-api) | 官方镜像：`ghcr.io/miracleeverywhere/dst-management-platform-api`（及 Docker Hub `hujinbo23/dst-admin-go`）

---

<a id="overview"></a>
## 架构概览与目录边界

DMP（Don't Starve Together Management Platform）是单二进制 Go Web 服务（通过 `embedFS/dist/` 内嵌预构建的前端静态产物，并通过 `embedFS/shell/` 内嵌运维脚本），在容器内调用 `/root/steamcmd` 下载和更新饥荒联机版专用服务端（AppID `343050`）及创意工坊模组（AppID `322330`），并通过 `screen` 会话（形如 `DMP_Cluster_2_Master`、`DMP_Cluster_2_Caves`）拉起地面与洞穴进程。

<a id="volume-layout"></a>
### 容器挂载卷与源码树共存

典型 `docker-compose.yml` 将宿主机项目目录下的 `./app/*` 绑定挂载（bind mount）到容器 `/root/*`：

| 宿主机路径（相对项目根） | 容器内路径 | 用途 |
|---|---|---|
| `./app/klei` | `/root/.klei` | 集群存档（`DoNotStarveTogether/Cluster_*/`）、世界配置、`cluster_token.txt`、`server_log.txt` |
| `./app/dst` | `/root/dst` | 饥荒联机版服务端本体（`bin64/dontstarve_dedicated_server_nullrenderer_x64`）与集群工坊模组目录（`ugc_mods/Cluster_*/`） |
| `./app/steamcmd` | `/root/steamcmd` | SteamCMD 客户端与运行时库（`linux32/`、`linux64/`、`package/`） |
| `./app/Steam` | `/root/Steam` | Steam 客户端配置、缓存（`appcache/`、`depotcache/`）与日志（`/root/Steam/logs/{content_log,connection_log,appinfo_log,stderr}.txt`） |
| `./app/data` | `/root/data` | DMP 自身 SQLite 数据库（`dmp.db`）与平台配置 |
| `./app/dmp_files` | `/root/dmp_files` | 模组 UGC 下载暂存（`mods/ugc/`）、备份归档等平台管理文件 |
| `./app/logs` | `/root/logs` | DMP 平台运行日志 |

> 源码与运行数据分离设计：上游源码树虽然同样有名为 `app/` 的包目录（存放 `app/room`、`app/mod` 等 Go 业务包），但其下各子目录与上述挂载卷子目录（`Steam`、`data`、`dmp_files`、`dst`、`klei`、`logs`、`steamcmd`）**完全无路径交集**，且上游官方 Dockerfile 位于 `docker/Dockerfile` 而非仓库根目录。若现场部署目录最初仅拷入了定制 `Dockerfile`、`docker-compose.yml` 和运行期 `app/` 数据，可直接在原目录初始化 Git 并检出上游分支，把完整源码树就地补齐而不覆盖任何运行数据或定制编排文件。

<a id="custom-port-base"></a>
### 端口基准定制与两阶段构建

上游在 `app/room/handler.go` 中将新建世界的默认端口基准写死为 `11000` / `31000` / `41000`（前端静态产物 `embedFS/dist/assets/*.js` 中对应写为 `serverPort:11e3`、`masterServerPort:31e3`、`authenticationPort:41e3`）：

- `ServerPort`（游戏通信 UDP）：`11000 + int(worldCount) + index + 1`
- `MasterServerPort`（主从世界互联 UDP）：`31000 + int(worldCount) + index + 1`
- `AuthenticationPort`（Steam 认证 UDP）：`41000 + int(worldCount) + index + 1`

由于上游仓库已在 `embedFS/dist/` 中直接提交了前端构建产物，定制端口基准（例如改为 `12000` / `32000` / `42000`）只需**两阶段 `Dockerfile`**（无需单独跑 Node 前端构建）：

1. **构建阶段（`dmp-build`）**：选用与上游 `go.mod` 匹配的 `golang` 镜像拉取指定版本源码，用 `sed -i` 将 `app/room/handler.go` 中的 `11000 / 31000 / 41000` 与 `embedFS/dist/assets/*.js`（用通配符匹配，避免前端拆包后文件名变化）中的 `11e3 / 31e3 / 41e3` 替换为 `12000 / 32000 / 42000`（`12e3 / 32e3 / 42e3`）；若做前置 `grep` 计数自检，使用 `-ge 1` 而非固定 `-eq 1`。随后执行 `CGO_ENABLED=0 go build -ldflags '-s -w' -o dmp main.go` 将替换后的前端静态资源一并编入二进制。
2. **运行阶段（`FROM ghcr.io/miracleeverywhere/dst-management-platform-api:<tag>`）**：直接复用官方镜像环境，`COPY --from=dmp-build /src/dmp /root/dmp` 覆盖二进制，补齐 32 位运行库（`libcurl3-gnutls`、`libc6:i386`、`libgcc-s1:i386`、`libstdc++6:i386`），并将下文 `#steamcmd-update` 中的 `entry-point.sh` 幂等守卫与 `/usr/local/bin/bash` SteamCMD 垫片一并固化进镜像层。

---

<a id="wsl-docker-desktop"></a>
## WSL2 + Docker Desktop 存储与守护进程边界

<a id="vhdx-vs-bind-mount"></a>
### 发行版 VHDX 迁移与挂载卷实际落盘位置

在 Windows + WSL2 + Docker Desktop 架构下，系统存在两个独立的 WSL2 发行版存储空间（参见 [network `references/wsl.md` 中 Docker Desktop 与 WSL 的关系](../../network/references/wsl.md#docker-desktop-与-wsl---shutdown)）：

- **Docker 引擎与镜像层**：位于 Docker Desktop 专用的 `docker-desktop` / `docker-desktop-data` 发行版 VHDX（默认在系统盘 `C:\Users\<user>\AppData\Local\Docker\wsl\`）。
- **用户 WSL 发行版（如 `Ubuntu`）**：位于用户发行版自己的 `ext4.vhdx`。

若将 `Ubuntu` 发行版的 `ext4.vhdx` 迁移到了机械硬盘（HDD），而 DMP 项目目录放在 `Ubuntu` 的 `/home/<user>/dst-management-platform-api/` 下并使用相对路径 `./app/*` 做 bind mount：

- 容器根文件系统（`/`）的读写走 `docker-desktop` 所在的 SSD；
- **所有挂载卷（`/root/dst`、`/root/.klei`、`/root/steamcmd` 等）的实际磁盘 I/O 均穿透 9p/drvfs 落在 `Ubuntu` VHDX 所在的机械硬盘上**。
- **性能影响边界**：饥荒服务端进程启动并把地图、模组与实体状态加载进内存后，日常高频 tick 与网络同步纯走内存，不受机械盘拖累；但**世界首次启动加载、SteamCMD 解压覆盖几千个小文件、每日定时存盘与备份归档**会直接受机械盘随机 I/O 限制。若需将热数据迁回 SSD，应将宿主侧挂载源目录放到 SSD 路径而非仅看 Docker Desktop 安装盘。

<a id="ssh-start-docker-desktop"></a>
### 非交互 SSH 会话下拉起 Docker Desktop 与凭据陷阱

当宿主机重启或 Docker Desktop 退出后，通过 SSH 连入 Windows 或 WSL2 恢复服务时有两个常见陷阱：

1. **直接执行 `Docker Desktop.exe` 会随 SSH 会话结束被杀**：GUI 进程需要附着在 Windows 交互式桌面会话（Session 1+）中。在非交互 SSH 会话里，应通过 Windows 计划任务（`schtasks` 或 PowerShell `Register-ScheduledTask`）以当前登录用户的交互式令牌（`Interactive` LogonType）注册一次性立即执行任务来拉起 `C:\Program Files\Docker\Docker\Docker Desktop.exe`，再轮询 `docker info` 等待引擎就绪。
2. **非交互 SSH 下 `docker pull` / `docker compose build` 报凭据错误**：
   - **症状**：执行拉取镜像时报错：
     ```text
     error getting credentials - err: exit status 1, out: `A specified logon session does not exist. It may already have been terminated.`
     ```
   - **根因**：Docker Desktop 默认在 `~/.docker/config.json` 中写入 `"credsStore": "desktop"`，调用 `docker-credential-desktop.exe` 读取 Windows Credential Manager；而 Win32 凭据管理 API 要求调用方处于交互式登录会话，纯 SSH 会话无此安全令牌。
   - **处理**：拉取公开镜像无需凭据，临时将 `~/.docker/config.json` 中的 `"credsStore": "desktop"` 移除（或改名备份该字段）即可正常 `docker pull` / `docker build`。

---

<a id="network-forwarding"></a>
## 公网暴露与双机端口转发

当 DMP 运行在无公网 IP 的内网/家庭宿主机（通过 WireGuard / EasyTier 组网接入公网 VPS）时，通常将 TCP WebUI 与 UDP 游戏流量分开转发。

<a id="webui-tcp-portproxy"></a>
### WebUI 仅绑 127.0.0.1 时的跨机反代

若 `docker-compose.yml` 将管理端口映射写为 `127.0.0.1:10000:10000`（防止宿主机局域网裸露），容器端口仅监听在宿主环回地址上，组网网卡（如 `<组网IP>:10000`）直接连会 `Connection refused`。

若不想改 `docker-compose.yml` 重建容器，可在 Windows 宿主机上用 `netsh interface portproxy` 将组网 IP 的 TCP `10000` 转发至环回口，并限定仅放行组网网段：

```powershell
# 在 Windows 管理员 PowerShell 中绑定组网 IP -> 127.0.0.1
netsh interface portproxy add v4tov4 listenaddress=<宿主机组网IP> listenport=10000 connectaddress=127.0.0.1 connectport=10000

# 防火墙仅允许组网对端访问 TCP 10000
New-NetFirewallRule -DisplayName "DMP-WebUI-Mesh" -Direction Inbound -Protocol TCP -LocalPort 10000 -RemoteAddress <组网网段> -Action Allow
```

随后在公网反代 VPS 的 Caddy 中 `reverse_proxy <宿主机组网IP>:10000` 即可对外提供 HTTPS 访问。

<a id="udp-range-forwarding"></a>
### UDP 游戏端口段转发与双向抓包验收

饥荒联机版每个世界实例占用三组 UDP 端口（按上文定制基准为例：游戏端口 `12000-12099`、主从互联 `32000-32099`、认证端口 `42000-42099`；若仅公网玩家直连，核心是暴露游戏端口段 `12000-12099/udp`）。

1. **公网入口转发方式**：
   - **内核态 `iptables` / `nftables` DNAT+SNAT**：适合整段端口映射，但在跑有 Docker + Caddy 的 VPS 上**切勿启用开机冲刷全表的 `nftables.service`**（会把 Docker/Caddy 依赖的规则一并清空导致全站断联；详见 [mess `references/linux.md` 中启用 `nftables.service` 冲掉规则的案例](../../mess/references/linux.md#nftables-breaks-caddy)）。
   - **用户态 GOST 端口段转发**：在公网转发机上用 `gost -L udp://:12000-12099/<宿主机组网IP>:12000-12099` 转发，不触碰内核防火墙表。
2. **回程路由检查**：若采用透明 DNAT（保留客户端源 IP），宿主机侧必须把回包路由指回转发机所在的隧道口，否则回包会走宿主默认网关丢包；若在转发机侧对转入隧道的流量做 `MASQUERADE`（SNAT 为转发机自己的组网 IP），则宿主机天然沿原隧道回包，无需改宿主默认路由。
3. **连通性验收陷阱**：
   - **不要用 `nc -uvz` 判死刑**：UDP 无握手，饥荒专用服务端对非 Klei 协议格式的空包/乱包直接静默丢弃，`nc -uvz` 不回包不能说明链路不通。
   - **不要被 Windows `pktmon` 实时模式报错误导**：在 Windows 宿主机跑 `pktmon start --etw -m real-time` 时若弹出“内存资源不足，无法处理此命令”，这是 Windows ETW 实时缓冲会话配额限制，**不是宿主机或容器发生了 OOM**。
   - **可靠验收法**：直接在公网转发机的组网接口（如 `wg0`）上运行 `tcpdump -ni wg0 udp portrange 12000-12010`，从外部客户端实际发起游戏房间连接，观察是否有 `转发机 -> 宿主机` 与 `宿主机 -> 转发机` 的双向 UDP 报文交互（例如 54 字节请求与 35 字节响应）。

---

<a id="steamcmd-update"></a>
## 容器内 SteamCMD 与饥荒服务端更新排障

DMP 面板点击“更新游戏”或触发定时更新时，后台固定执行（见 [`app/dashboard/handler.go`](https://github.com/miracleEverywhere/dst-management-platform-api/blob/9fe5c55955b15fa70e3273ba29c41c9a37a140e8/app/dashboard/handler.go#L111) 与 [`scheduler/global.go`](https://github.com/miracleEverywhere/dst-management-platform-api/blob/9fe5c55955b15fa70e3273ba29c41c9a37a140e8/scheduler/global.go#L187)）：

```bash
cd ~/steamcmd && ./steamcmd.sh +login anonymous +force_install_dir ~/dst +app_update 343050 validate +quit
```

当遇到游戏版本落后、面板点更新无反应或长时间卡住时，按以下四层链路逐一排查。

<a id="entrypoint-overwrite-steamcmd"></a>
### 容器重启把已更新的 SteamCMD 覆盖回 2018 旧版

- **症状**：容器内手动修好或更新过 `/root/steamcmd` 后，一旦容器重启，`steamcmd.sh` 又退回 2018 年的初始版本，且因 `/root/steamcmd/package/` 下残留新版 manifest 导致启动即卡在自更新或校验。
- **根因**：上游 [`docker/entry-point.sh`](https://github.com/miracleEverywhere/dst-management-platform-api/blob/9fe5c55955b15fa70e3273ba29c41c9a37a140e8/docker/entry-point.sh#L20-L34) 中的 `install_steamcmd()` **没有任何存在性判断**：
  ```bash
  install_steamcmd() {
      wget https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz
      mkdir -p "$STEAM_DIR"
      tar -zxvf steamcmd_linux.tar.gz -C "$STEAM_DIR"
  }
  ```
  `steamcmd_linux.tar.gz` 是 Valve 打包于 2018 年的初始引导包（仅含 32 位 `linux32/steamcmd`）。因为 `/root/steamcmd` 挂了宿主卷，每次容器启动都会无条件重下并解压该引导包，把卷内已自更新好的二进制覆盖回 2018 版。
- **修法**：修改容器内（及镜像构建所用）的 `/root/entry-point.sh`，仅在首次未安装时解压引导包：
  ```bash
  install_steamcmd() {
      if [ ! -f "$STEAM_DIR/steamcmd.sh" ]; then
          wget https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz
          mkdir -p "$STEAM_DIR"
          tar -zxvf steamcmd_linux.tar.gz -C "$STEAM_DIR"
          rm -f steamcmd_linux.tar.gz
      fi
  }
  ```

<a id="steam-cdn-and-proxychains"></a>
### Steam 自更新域名变迁与 proxychains4 配置细节

- **旧版自更新死锁**：2018 版 `steamcmd` 引导程序默认请求旧域名 `client-download.steampowered.com` 拉取客户端自更新，该域名现已无有效 A 记录；现役更新源为 `client-update.steamstatic.com`（及 `steamcdn-a.akamaihd.net`）。若旧版 `steamcmd` 卡在 `[  0%] Checking for available updates...`，可直接从 `https://client-update.steamstatic.com/` 下载 manifest（如 `steam_cmd_linux`）指明的各组件 zip 包解压到 `/root/steamcmd/` 完成离线自举。
- **容器内用 `proxychains4` 走宿主代理的坑**：
  1. **镜像默认清空了 apt 索引且启用了 `i386` 双架构**：上游 [`docker/Dockerfile`](https://github.com/miracleEverywhere/dst-management-platform-api/blob/9fe5c55955b15fa70e3273ba29c41c9a37a140e8/docker/Dockerfile#L29-L36) 执行了 `dpkg --add-architecture i386` 并在末尾 `rm -rf /var/lib/apt/lists/*`。进容器首次装 `proxychains4` 或 `strace` 时必须先跑 `apt-get update`，且因为要同时拉取 `amd64` + `i386` 两个架构的索引（约 50 MB），走默认源耗时较长。
  2. **`proxychains4` 配置文件只接受数字 IPv4 地址**：在 `/etc/proxychains4.conf` 的 `[ProxyList]` 中不能写域名 `host.docker.internal`。同时要注意在 Docker Desktop 中执行 `getent hosts host.docker.internal` 时，首行可能返回 IPv6 地址；必须使用 `getent ahostsv4 host.docker.internal | awk 'NR==1{print $1}'` 提取纯 IPv4 地址（如 `192.168.65.254`）写入 `http <IP> <PORT>`。
  3. **代理分流建议**：Steam 内容 CDN（`*.steamcontent.com`、`akamaihd.net`）在国内通常可高速直连，只有初始握手或特定 API 受阻时才需代理；大体积 `app_update 343050` 优先测试直连，避免把几 GB 游戏本体流量灌入代理隧道。

<a id="seccomp-socketcall-enosys"></a>
### 新版 SteamCMD 报 `CreateBoundSocket: ... (38)`、`BVerifyInstalledFiles` 校验回滚与 `proxychains4` 冲突

- **症状 1（32 位 `linux32/steamcmd` 报 `ENOSYS = 38`）**：将 SteamCMD 升级到新版（`steamrt` 构建，如 version `1792617903`）后，运行默认的 `/root/steamcmd/steamcmd.sh`（内部默认 `: "${STEAM_PLATFORM:=linux32}"`）立即循环报错：
  ```text
  Loading Steam API...Process 9158 failed to shm_open /u0-ValveIPCSharedObj-Steam
  CreateBoundSocket: failed to create socket, error [no name available] (38)
  Connecting anonymously to Steam Public...CreateBoundSocket: failed to create socket, error [no name available] (38)
  ```
- **根因 1**：错误码 `38` 即 Linux `errno` 的 `ENOSYS`（`Function not implemented`）。因 Linux 内核漏洞 `CVE-2026-31431`，新版 Docker（含 Docker Desktop 29.x）在默认 `seccomp` 配置中屏蔽了 32 位 x86 多路复用套接字系统调用 `socketcall`（被 seccomp 拦截时返回 `ENOSYS = 38`）。`linux32/steamcmd` 依赖 `socketcall` 创建网络套接字，因此全线报错（详见 [`CM2Walki/steamcmd#78`](https://github.com/CM2Walki/steamcmd/issues/78)）。
- **症状 2（直接修改 `steamcmd.sh` 被自校验瞬间打回原形）**：
  若直接用 `sed -i` 将 `/root/steamcmd/steamcmd.sh` 中的 `STEAM_PLATFORM:=linux32` 改为 `linux64`，首次执行 `steamcmd.sh` 时 `linux64/steamcmd` 的内置引导器会校验 `/root/steamcmd/package/steam_cmd_steamrt64.installed` 中记录的 CRC32，在 `/root/Steam/logs/bootstrap_log.txt` 中报：
  ```text
  BVerifyInstalledFiles: bad CRC on steamcmd.sh (a80dc9df expected, 7fd3daee actual)
  Extracting package...
  Installing update...
  ```
  随后立即重新解压 `steamcmd_steamrt64.zip.vz` 把 `steamcmd.sh` 覆盖回 `STEAM_PLATFORM:=linux32`，并以退出码 `42`（`MAGIC_RESTART_EXITCODE=42`）触发 `exec "$0" "$@"` 重启回 32 位 `linux32/steamcmd`，表面上看起来仍报 `CreateBoundSocket (38)`。
- **症状 3（改调 64 位 `linux64/steamcmd` 但套了 `proxychains4` 报 `epoll_ctl` 断言失败）**：
  新版 SteamCMD 更新包自带原生 64 位 `/root/steamcmd/linux64/steamcmd`（使用独立的 64 位 `socket` / `bind` 系统调用，不走 `socketcall`，天然绕开上述 seccomp 限制）。但若在 `proxychains4` 下运行 `linux64/steamcmd`，会刷屏报错并卡死在登录阶段：
  ```text
  ../common/completionportmanager_posix.cpp (558) : Assertion Failed: epoll_ctl finalize MOD failed with error 2
  ```
  原因是 `proxychains4` 通过 `LD_PRELOAD` 替换套接字 fd，破坏了新版 `steamrt` POSIX 完成端口管理器对内部 `epoll` 实例中 fd 的跟踪。
- **根治解法（零侵入 `/usr/local/bin/bash` 垫片 + 裸跑 64 位 `linux64/steamcmd`）**：
  1. **直接裸跑 64 位 `/root/steamcmd/linux64/steamcmd`（不套 `proxychains4`）**：
     Steam CM 登录（自动选路至可用 WebSocket CM 节点如 `cmp1-sea1.steamserver.net:443`）与国内内容 CDN 节点（`st.dl.eccdnx.com`、`dl.steam.clngaa.com`、`xz.pphimalayanrt.com` 等，直连可达 80–95 Mbps）均可直连工作，完全无需代理。
  2. **不改 `/root/steamcmd/steamcmd.sh` 文件本身，利用其 `#!/usr/bin/env bash` 与 `: "${STEAM_PLATFORM:=linux32}"` 在 `/usr/local/bin/bash` 注入环境变量并重排参数**：
     因为容器 `PATH` 中 `/usr/local/bin` 排在 `/bin` 之前，且 DMP 后端统一通过 `/bin/bash -c "steamcmd/steamcmd.sh ..."` 调起 `steamcmd.sh`（触发 shebang `#!/usr/bin/env bash`），在容器内放置 `/usr/local/bin/bash` 即可同时解决 **64 位切换** 与 **参数顺序倒置（`+force_install_dir` 必须在 `+login` 之前）** 两大问题，且保持 `steamcmd.sh` 磁盘文件 CRC 原封不动、无需重启线上正在运行的 `dmp` 或饥荒进程：
     ```bash
     cat << 'EOF' > /usr/local/bin/bash
     #!/bin/bash
     if [[ "${1:-}" == *steamcmd.sh ]]; then
       export STEAM_PLATFORM=linux64
       script="$1"
       shift
       force_args=()
       other_args=()
       while (($# > 0)); do
         if [[ "$1" == "+force_install_dir" && $# -ge 2 ]]; then
           force_args+=("$1" "$2")
           shift 2
         else
           other_args+=("$1")
           shift
         fi
       done
       exec /bin/bash "$script" "${force_args[@]}" "${other_args[@]}"
     fi
     exec /bin/bash "$@"
     EOF
     chmod +x /usr/local/bin/bash
     ```

<a id="app-update-state-0x6"></a>
### 新版 SteamCMD 更新游戏秒败 `Error! App '343050' state is 0x6 after update job.` 的两层根因

切到 `/root/steamcmd/linux64/steamcmd` 直连并成功匿名登录后，对现有 `/root/dst` 执行 `app_update 343050` 仍可能在几十秒内报 `Error! App '343050' state is 0x6 after update job.`（无下载进度）。这由两层原因叠加造成：

1. **第一层：命令行参数顺序变严（`+force_install_dir` 必须在 `+login` 之前）**
   - **现象**：按上游 DMP 硬编码顺序执行 `+login anonymous +force_install_dir /root/dst +app_update 343050 validate +quit` 时，输出：
     ```text
     Please use force_install_dir before logon!
     Update state (0x3) reconfiguring, progress: 0.00 (0 / 0)
     Error! App '343050' state is 0x6 after update job.
     ```
   - **原因与修法**：2018 旧版容忍登录后再设目录，而新版 `steamrt` SteamCMD 严格要求先指定安装目录再登录（配置上文 `/usr/local/bin/bash` 垫片后可自动重排）。

2. **第二层：旧版 `appmanifest_343050.acf` 触发历史 manifest 匿名请求被拒（`Access Denied`）**
   - **现象**：把 `+force_install_dir /root/dst` 移到 `+login anonymous` 之前后，`Please use force_install_dir before logon!` 警告消失，但对已有旧版安装的 `/root/dst` 执行更新仍在约 20 秒后秒败 `state is 0x6`；与此同时，换一个空目录（如 `+force_install_dir /tmp/dsttest`）却能以 ~12 MB/s 正常满速下载。
   - **根因**：查看 `/root/Steam/logs/content_log.txt` 可见真实报错：
     ```text
     CDepotDownloadMgr::BYldRequestDepotManifest(App: 343050, Depot: 343052, Manifest: <旧版manifest>, branch: ): Failed to get manifest request code, 'Access Denied'
     AppID 343050 update canceled : Failed downloading 1 manifests (No connection)
     ```
     当 `/root/dst/steamapps/appmanifest_343050.acf` 中记录了旧版本的 `InstalledDepots` manifest ID，且 `/root/Steam/depotcache/` 下没有缓存该旧 `.manifest` 文件时，SteamCMD 会向内容服务器请求下载**旧版本 manifest** 以计算增量差分（delta）；而 Steam 服务端禁止 `anonymous` 匿名账号获取已下线的历史 manifestRequestCode（返回 `'Access Denied'`），只允许匿名账号拉取当前最新（head）manifest。
   - **注意下载期与提交后的目录形态差异**：
     在 `0x61 downloading` 与 `0x81 verifying` 阶段，目标目录下**只有 `steamapps/{appmanifest_343050.acf,downloading,temp}`**（容易被误判为变成了客户端式的 `steamapps/common/` 布局）；等到 `0x101 committing` 跑完并输出 `Success! App '343050' fully installed.` 后，SteamCMD 会将 `bin/`、`bin64/`、`data/`、`linux64/`、`mods/`、`version.txt` 等全部平铺提交到 `<install_dir>` 根下，与 DMP 期望的平铺布局完全一致。
   - **两种可靠的更新操作流程**：
     - **方案 A（原地移走旧 acf 后更新）**：先移走或备份 `/root/dst/steamapps/appmanifest_343050.acf`（保留游戏文件），再执行 `+force_install_dir /root/dst +login anonymous +app_update 343050 validate +quit`，迫使 SteamCMD 只请求最新 head manifest 并就地校验复用已有文件。
     - **方案 B（先在容器 `/tmp` 独立拉取，再合并回 `/root/dst`，适合 `/root/dst` 挂在机械盘的场景）**：
       因为容器 `/tmp` 位于 Docker Desktop 的 SSD overlay 层，在 `/tmp/dsttest` 中完成 4.6 GB 分片下载、校验与提交比在机械盘 bind mount 上更快，且完全不影响存档（集群存档位于 `/root/.klei/DoNotStarveTogether/Cluster_*`，创意工坊模组位于 `/root/dst/ugc_mods/Cluster_*`，均不在 Steam depot 覆盖范围内）：
       ```bash
       # 1. 在容器 SSD 层完成全新下载与校验提交
       /root/steamcmd/linux64/steamcmd \
         +force_install_dir /tmp/dsttest \
         +login anonymous \
         +app_update 343050 validate \
         +quit

       # 2. 合并覆盖回 /root/dst（自动保留 /root/dst/ugc_mods/）
       cp -a /tmp/dsttest/. /root/dst/
       rm -rf /tmp/dsttest

       # 3. 补齐 entry-point.sh 的 libcurl-gnutls 软链与 steamclient.so
       ln -sf /usr/lib/x86_64-linux-gnu/libcurl-gnutls.so.4 /root/dst/bin64/lib64/libcurl-gnutls.so.4
       ln -sf /usr/lib/i386-linux-gnu/libcurl-gnutls.so.4 /root/dst/bin/lib32/libcurl-gnutls.so.4
       cp -f /root/steamcmd/linux32/steamclient.so /root/dst/bin/lib32/steamclient.so
       cp -f /root/steamcmd/linux64/steamclient.so /root/dst/bin64/lib64/steamclient.so

       # 4. 核对最新构建号（如 753392）后在 DMP 面板或通过 screen 启动世界
       cat /root/dst/version.txt
       ```

---

<a id="mod-installation"></a>
## 创意工坊模组（Mod）下载与安装机制

<a id="mod-pipeline-and-ssot"></a>
### DMP 模组管理的三阶段链路与数据库单一事实源

DMP（见 `app/mod/handler.go`、`app/mod/utils.go`、`dst/mod.go`）管理模组分为三个严格耦合的阶段，且**以 SQLite 数据库 `/root/data/dmp.db` 中的 `rooms.mod_data`（勾选“统一模组配置” `mod_in_one = 1` 时）或 `worlds.mod_data` 为单一事实源（Single Source of Truth）**：

1. **检索与元数据获取（`GET /v3/mod/search`）**：
   - 后端直连请求 `http://api.steampowered.com/IPublishedFileService/{QueryFiles,GetDetails}/v1/`。
   - 根据返回详情中的 `file_url` 是否为空区分两类模组：
     - **UGC 模组（`file_url == ""`，现代绝大多数模组）**：走 SteamCMD Workshop 通道下载。
     - **非 UGC 旧版模组（`file_url != ""`，形如 `https://cdn.steamusercontent.com/ugc/...`）**：由 Go HTTP 客户端直接下载 ZIP 并解压到 `/root/dst/mods/workshop-<modID>`。
2. **模组下载与分世界落盘（`POST /v3/mod/download`）**：
   - 对 UGC 模组，DMP 先调用：
     ```bash
     steamcmd/steamcmd.sh +force_install_dir /root/dmp_files/mods/ugc/Cluster_<id> +login anonymous +workshop_download_item 322330 <modID> +quit
     ```
     下载到 `/root/dmp_files/mods/ugc/Cluster_<id>/steamapps/workshop/content/322330/<modID>`。
   - 下载完成后，DMP 将该目录复制到当前房间下所有分世界（如 `Master`、`Caves`）的 `/root/dst/ugc_mods/Cluster_<id>/<WorldName>/content/322330/<modID>`，并解析暂存区的 `appworkshop_322330.acf`，将该模组的 `WorkshopItemsInstalled` 与 `WorkshopItemDetails` 节点合并写入各分世界的 `/root/dst/ugc_mods/Cluster_<id>/<WorldName>/appworkshop_322330.acf`，最后校验本地目录字节数与 Steam API 返回的 `size` 一致。
3. **模组启用与配置持久化（`POST /v3/mod/add/enable` / `PUT /v3/mod/setting/config_value`）**：
   - DMP 使用沙箱化 Lua 虚拟机（`gopher-lua`）解析模组目录下的 `modinfo.lua`，提取 `configuration_options` 的默认值，将 `["workshop-<modID>"]={ configuration_options={...}, enabled=true }` 合并进数据库 `rooms.mod_data`（或 `worlds.mod_data`），随后截断覆写各分世界的 `/root/.klei/DoNotStarveTogether/Cluster_<id>/<WorldName>/modoverrides.lua`。
   - 每次通过面板启动或重启世界（`startWorld` / `startAllWorld`）时，`dsModsSetup()` 都会从数据库的 `mod_data` 重新提取所有 `workshop-<modID>` 键，截断覆写 `/root/dst/mods/dedicated_server_mods_setup.lua`。

> **切勿绕过 DMP 数据库手改磁盘文件**：
> 若仅手动把模组目录拷入 `ugc_mods/Cluster_<id>/` 并手改 `modoverrides.lua` 与 `dedicated_server_mods_setup.lua`，虽然直接用命令行 `screen` 拉起世界时能暂时加载，但存在两个严重隐患：
> 1. **面板操作会静默抹除手改配置**：因为 `dmp.db` 的 `rooms.mod_data` 中没有该模组，下次在 WebUI 面板中修改房间设置、启停任意模组或点击启动/重启世界时，DMP 会用数据库里的旧 `mod_data` 直接截断覆写 `modoverrides.lua` 和 `dedicated_server_mods_setup.lua`，导致手动添加的模组丢失。
> 2. **手工拼接 Lua 易破坏相邻模组**：用正则或文本追加修改 `modoverrides.lua` 极易误删相邻模组尾部的 `enabled=true`。

<a id="mod-install-workflows"></a>
### WebUI 面板安装与 Agent 本地 API 快速安装流程

只要宿主机直连出网正常（无失效的 `tun2socks` 默认路由劫持）且容器内已部署上文 `#seccomp-socketcall-enosys` 中的 `/usr/local/bin/bash` 垫片，面板安装与 Agent 自动化安装均走同一套原生链路：

1. **WebUI 面板安装**：
   在 DMP 面板进入目标房间 → **模组 → 下载模组** → 搜索模组名称或 Workshop ID 并点击下载 → 切到 **模组设置** 点击启用并调整参数 → 在合适时机重启该房间世界使模组生效。
2. **Agent 本地 API 快速安装（零停机、自动同步 `dmp.db` 与 `modoverrides.lua`）**：
   Agent 在宿主机上无需明文账号密码，可直接读取 `./app/data/dmp.db` 中 `system` 表的 `jwt_secret` 与 `users` 表的管理员记录在内存中签发短期 `X-DMP-TOKEN`，顺序调用本地 `http://127.0.0.1:10000` 接口完成搜索、同步下载与启用（全程不影响线上运行中的世界进程）：
   ```bash
   python3 - <ROOM_ID> <WORLD_ID> <MOD_ID> << 'PYEOF'
   import sys, sqlite3, hmac, hashlib, base64, json, time, urllib.request

   room_id, world_id, mod_id = map(int, sys.argv[1:4])
   conn = sqlite3.connect("app/data/dmp.db")
   cur = conn.cursor()
   secret = cur.execute("SELECT value FROM system WHERE key='jwt_secret'").fetchone()[0].encode()
   u, nick, role, tv = cur.execute("SELECT username, nickname, role, token_version FROM users WHERE role='admin' LIMIT 1").fetchone()

   b64u = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()
   now = int(time.time())
   hdr = b64u(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
   pld = b64u(json.dumps({
       "username": u, "nickname": nick, "role": role, "tokenVersion": tv,
       "iss": "https://github.com/miracleEverywhere/dst-management-platform-api",
       "sub": u, "exp": now + 600, "nbf": now - 10, "iat": now - 10,
   }, separators=(",", ":")).encode())
   tok = f"{hdr}.{pld}.{b64u(hmac.new(secret, f'{hdr}.{pld}'.encode(), hashlib.sha256).digest())}"

   def call(method, path, body=None):
       req = urllib.request.Request(
           f"http://127.0.0.1:10000{path}",
           data=json.dumps(body).encode() if body else None,
           headers={"X-DMP-TOKEN": tok, "X-I18n-Lang": "zh", "Content-Type": "application/json"},
           method=method,
       )
       with urllib.request.urlopen(req, timeout=120) as r:
           return json.loads(r.read().decode())

   info = call("GET", f"/v3/mod/search?searchType=id&searchText={mod_id}&page=1&pageSize=10")["data"]["rows"][0]
   print("1. Search:", info["id"], info["name"], info["size"])
   print("2. Download:", call("POST", "/v3/mod/download", {
       "roomID": room_id, "id": mod_id, "file_url": info["file_url"],
       "size": str(info["size"]), "name": info["name"], "update": False, "sync": True,
   }))
   print("3. Enable:", call("POST", "/v3/mod/add/enable", {
       "roomID": room_id, "worldID": world_id, "id": mod_id, "file_url": info["file_url"],
   }))
   PYEOF
   ```
