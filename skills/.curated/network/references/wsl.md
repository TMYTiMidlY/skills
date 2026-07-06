# WSL ↔ Windows 网络管道

WSL2 与 Windows 宿主、远端之间的网络互通与排障：Mirror / NAT 网络、WSL 出站怎么进宿主 Mihomo、WSL/Docker 服务入站（portproxy + wslrelay）。**分工**：本文只管「WSL 流量怎么进出宿主那个 Mihomo」这条管道；**Mihomo 内核自己怎么跑**（DNS 语义 / `fake-ip-range` 取值 / TUN 路由规则 / REST / 协议选型）都在 [mihomo.md](mihomo.md)，下文引用会指到具体小节。远程桌面 / VS Code serve-web 等远程接入见 [remote.md](remote.md)；独立 systemd 版 Hysteria2 服务端见 [hysteria2.md](hysteria2.md)。

## WSL Mirror 模式网络

Mirror 模式的 WSL 会同步宿主机所有网卡，包括蒲公英、EasyTier 等虚拟网卡。

正常状态下 `ip route show` 以此开头：

```
default via <gateway-ip> dev eth1 proto kernel metric 25
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

## WSL NAT 下出站走 Mihomo

> 本节只讲 WSL NAT 流量怎么进 Windows 宿主的 Mihomo。**内核侧**：DNS 模式（fake-ip / redir-host / normal）见 [mihomo.md](mihomo.md) §9、TUN 路由规则（IP-CIDR / route-exclude）见 §7、REST 控制见 §6、节点 / 协议选型见 §3·§4。

在无法使用 WSL Mirror / mirrored networking、必须继续使用 WSL NAT 时，不要假设 Windows 宿主能走 Mihomo TUN 就等于 WSL 裸 TCP 也会被接管。更稳的做法是：WSL 内的 HTTP 类工具显式走 Windows 宿主 `mixed-port`，SSH 等不读代理环境变量的工具单独配置 `ProxyCommand`。

**现象**：Windows PowerShell `Test-NetConnection <ip> -Port <port>` 成功（`InterfaceAlias` 显示 `Meta`），但 WSL 里 `curl` / `ssh` / `nc` 对同一目标超时，卡在 TCP connect 阶段、还没到 TLS/SSH 握手。

**根因**（与 DNS `enhanced-mode` 无关，也与目标墙不墙无关）：**NAT 模式下** WSL 是独立 VM——`ip addr` 里只有自己的 `eth0`，**根本看不到宿主的 Meta / TUN 网卡**，自然用不了宿主 mihomo 的透明接管（`ip route` 里也没有 `0.0.0.0/2 via 198.18.x`）。出站裸流量只按默认路由丢给 NAT 网关、从宿主物理网卡直出，**全程不经宿主 mihomo**（mirrored 模式共享宿主栈、或 WSL 内自建 tun2socks，才补上这层）。两种 DNS 模式差别只在 WSL 拿到什么地址：

- `fake-ip`：WSL 拿到 `198.18.x` 占位 IP——宿主 TUN 内部才有意义的地址，WSL 侧没有对应网卡 / 路由，裸连无人应答。
- `redir-host` / `normal`：WSL 拿到**真实 IP**，但裸流量同样不经 mihomo，需要代理才通的目标照样到不了。

别凭“是否 198.18.x”判断，也别一律归到“fake-ip 映射不稳”——两种模式殊途同归，都是 WSL 出站没走宿主代理，不是远端服务故障。DNS 模式取值见 [mihomo.md](mihomo.md) §9。

快速判断：

```bash
# WSL 看到的 Windows 宿主网关
ip route get <target-ip>

# WSL 直连目标
nc -vz -w 6 <target-ip> <port>

# WSL 是否能访问 Windows 宿主上的 mixed-port
nc -vz -w 4 <wsl-gateway-ip> 7890

# WSL 显式走 Windows 宿主 Mihomo SOCKS
nc -vz -w 8 -x <wsl-gateway-ip>:7890 -X 5 <target-ip> <port>
curl -I --connect-timeout 5 --max-time 8 --proxy socks5h://<wsl-gateway-ip>:7890 https://www.google.com
```

Windows 宿主侧对照：

```powershell
Test-NetConnection <target-ip> -Port <port>
```

如果 Windows 成功、WSL 直连超时、WSL 走 `<wsl-gateway-ip>:7890` 成功，说明问题在 **WSL NAT 裸流量进入 Windows TUN 的透明接管路径**，不是远端目标或节点不可用。

### 方案 A：逐工具显式设代理（`*_proxy` 环境变量 + ssh `ProxyCommand`）

`<wsl-gateway-ip>` 通常是 WSL 默认路由的网关，例如：

```text
<target-ip> via 172.28.80.1 dev eth0 src 172.28.94.43
```

这里 `172.28.80.1` 是 WSL NAT 网络里 Windows 宿主的地址。它可能在 `wsl --shutdown`、网络重置、虚拟网卡重建后变化；需要写入 shell 配置时，优先动态读取：

```bash
if command -v ip >/dev/null 2>&1; then
    WSL_HOST_IP="$(ip route show default 2>/dev/null | awk '{print $3; exit}')"
    if [ -n "$WSL_HOST_IP" ]; then
        export ALL_PROXY="socks5h://${WSL_HOST_IP}:7890"
        export all_proxy="socks5h://${WSL_HOST_IP}:7890"
        export HTTPS_PROXY="http://${WSL_HOST_IP}:7890"
        export https_proxy="http://${WSL_HOST_IP}:7890"
        export HTTP_PROXY="http://${WSL_HOST_IP}:7890"
        export http_proxy="http://${WSL_HOST_IP}:7890"
    fi
    unset WSL_HOST_IP
fi
```

这些代理环境变量能稳定覆盖 `curl`、`git` HTTPS、`npm`、`pip`、`uv` 等大量 HTTP 客户端，但不是透明全局代理。`ssh` 默认不读 `ALL_PROXY`，需要单独配：

```sshconfig
Host <name>
  HostName <target-ip-or-domain>
  User <user>
  ProxyCommand nc -x <wsl-gateway-ip>:7890 -X 5 %h %p
```

### 方案 B：WSL 内自建 TUN 透明代理（tun2socks）

上面是**方案 A**：逐工具显式指代理（`*_proxy` 环境变量 + ssh `ProxyCommand`）。**方案 B** 用 [`xjasonlyu/tun2socks`](https://github.com/xjasonlyu/tun2socks)（开源 Go 单文件）在 WSL 内建一块 TUN 网卡，把**全部**出站裸流量透明导进宿主 mihomo，免逐工具设代理。它**只补“透明网卡”这一层**，分流 / 选节点仍交给宿主已有的 mihomo——所以 WSL 内**不必再开第二个完整 mihomo**（除非要 WSL 独立订阅 / 规则）。

**为什么需要方案 B（初衷）**：方案 A 只覆盖**读 `*_proxy` 的工具**（curl / git / pip…）。有一类工具不读任何代理环境变量、自己解析 DNS、把解析到的 IP **钉死直连**——典型是 **agent 内置抓取工具（如 Copilot CLI 的 `web_fetch`）**。它在 WSL NAT 下必失败：① `fake-ip` 解析到 `198.18.x` 撞其 SSRF 保留地址闸，连都不连；② 宿主改 `redir-host` 让它拿到真实 IP，但 NAT 模式下 WSL 裸流量又不被宿主 TUN 稳定接管（见上节），真实（被墙）IP 裸连照样超时。既设不了代理、又走不了宿主 TUN，方案 A 对它无效——只有方案 B 在 WSL 内建 TUN、把裸流量透明导进宿主 mihomo 才救得回。

**装（`/usr/local/bin`，要 sudo）**：取对应 arch 的二进制（`uname -m` → amd64 / arm64），`sudo install -m0755 <binary> /usr/local/bin/tun2socks` 装到 `/usr/local/bin/`，`tun2socks --version` 自检；GitHub 下载本身可先经宿主 `--proxy http://<gw>:7890`。选 `/usr/local/bin` 三重有据：① tun2socks **官方推荐位置**——官方 wiki *Install-from-Source* 的 Build 段原文即 `make tun2socks && sudo cp ./build/tun2socks /usr/local/bin`；② 下面 systemd unit 的 `ExecStart` **写死**了这个路径；③ 它在 root（`sudo` / 服务）默认 `PATH` 内。tun2socks 建 TUN + 改路由本就要 root，把二进制留在用户目录（`~/.local/bin` 等）对 root 服务没意义——直接装系统位置，别在用户目录中转。

> ⚠️ **`go install github.com/xjasonlyu/tun2socks/v2@latest` 是另一条路、落点不同**：按 Go 工具链默认装到 `$(go env GOPATH)/bin`（默认 `~/go/bin`），既非系统级位置、也不是 unit 写死的 `/usr/local/bin`。走这条装完还得再 `sudo install ~/go/bin/tun2socks /usr/local/bin/tun2socks`（或建 symlink），否则 service 找不到二进制——**装 service 时这个落点差异务必核对**。

**跑（要 root / `CAP_NET_ADMIN`——建 TUN + 改路由是特权操作；非免密 sudo 无法非交互代跑）**，核心三步：

```bash
GW=$(ip route show default | awk '{print $3}')                     # 宿主网关(NAT下会变,动态取)
tun2socks -device tun0 -proxy socks5://$GW:7890 -interface eth0 &   # -interface eth0: 出站socket绑真实网卡,防绕回tun
ip addr add 198.19.0.1/24 dev tun0; ip link set tun0 up
ip route replace default dev tun0                                   # 默认路由改走tun → 全流量透明进mihomo
```

> **TUN 设备地址得自己 `ip addr add`（tun2socks 不给默认值）。** 官方 Examples 示例用的是 `198.18.0.1/15`——整个 RFC2544 基准段（`198.18.0.0/15`，含 `198.18.x` + `198.19.x`），选它是因为这段非真实互联网、不会撞公网目标。**本文故意偏离、改用 `198.19.0.1/24`**：官方那个 `/15` 把 `198.18.x` 也纳进来，而本机宿主已占用 `198.18.x`——mihomo 默认 `fake-ip-range: 198.18.0.1/16`（只含 198.18.x，定义见 [mihomo.md](mihomo.md) §9.4）+ 官方 wiki 注明「tun 默认 IPv4 地址也取自此值」，即宿主 fake-ip 段与其 TUN 网关都落在 `198.18.x`，直接套官方 `/15` 会和宿主撞。改用 `198.19.0.1/24` 既仍在安全的 RFC2544 段内、又避开 `198.18.x`，也不撞 mesh `10.x` / WSL NAT `172.28.x` / docker `172.17–172.31`。它是**合理选择、非唯一解**（任何不与 fake-ip / mesh / docker 冲突的保留段都行）；`198.19` 在默认 `/16` 下**不是** fake-ip，⚠️ 仅当你手动把 `fake-ip-range` 改成 `/15`（才会含 198.19）时需另换。

到宿主网关 `$GW` 本身仍走 eth0 的 `/20` 子网路由（比 `default` 更具体、不会被吞进 tun），加上 `-interface eth0` 绑定出站，两重保证 socks 连接不绕回 tun 死循环。首测务必包一层 `trap 'ip route del default dev tun0; ip link del tun0' EXIT INT TERM` 自动回滚——配错也不会把 WSL 网络卡死。验证：不带任何 `*_proxy` 跑 `curl https://www.google.com/generate_204` 得 `204` 即生效。

**转 systemd 持久化**：unit `../assets/tun2socks.service` 随 skill 附带，**自包含**——`ExecStart`/`ExecStopPost` 直接内联 `/bin/sh -c '…'`，不依赖外部脚本（脚本不入 skill）。它做的事：

- `ExecStart`（一条 sh）：从 `ip route show default` 取宿主网关（`via` IP，缓存到 `/run/tun2socks-gw`）→ 建 `tun0` + 地址 `198.19.0.1/24` + up → 私有/组网段 `10.0.0.0/8`+`172.16.0.0/12`+`192.168.0.0/16` 加 `via <网关> dev eth0` 排除路由（含 mesh、只代理公网）→ 默认路由改 `tun0` → `exec tun2socks -device tun0 -proxy socks5://<网关>:7890 -interface eth0`。
- `ExecStopPost`（一条 sh）：读 `/run` 缓存网关 → 删默认路由、还原 `default via <网关> dev eth0`、删 `tun0`。
- 网关**动态取、不写死**：`ip route show default` 的 `via` IP；若 default 已是 tun0（重启态）则读 `/run` 缓存兜底。`-interface eth0` + 网关命中 eth0 子网 on-link，双重防绕回 tun。systemd 里 shell 变量写 `$$VAR`（`$$`→`$`），`$(…)` 命令替换保持单 `$`。

安装（`<skill>` = 本 skill 目录，如 `~/.agents/skills/network`；只需二进制 + unit，无脚本）：

```bash
# 二进制须已在 /usr/local/bin/tun2socks（见上「装」；unit ExecStart 写死此路径，go install 落 ~/go/bin 的先补装到位）
sudo install -m0644 <skill>/assets/tun2socks.service /etc/systemd/system/tun2socks.service
sudo systemctl daemon-reload && sudo systemctl enable --now tun2socks
# 验证 systemctl status tun2socks；ip route show default(=tun0)；curl -so/dev/null -w '%{http_code}' https://www.google.com/generate_204(=204)
```

⚠️ 装前先停掉手动/测试脚本残留的 tun2socks——两个实例抢同一 tun0，且测试脚本退出时 `trap` 会 `ip link del tun0` 打断服务。

**副作用 / 坑**：

- 默认路由变成 `default dev tun0`（**无 `via`**）→ 任何 `ip route show default | awk '{print $3}'` 取网关的脚本会把 `tun0` 当成网关 IP 而坏（见下面 ssh）。健壮写法用 `ip route get 1.1.1.1`。
- **mesh（`10.144.x` / `10.100.x`）出站不受影响**：包被 tun0 吞进 mihomo 后，靠宿主 mihomo 的 `IP-CIDR,10.x,DIRECT` 规则兜底仍直连可达（实测通）。想让 mesh 彻底不经 mihomo，加排除路由 `ip route add 10.0.0.0/8 via $GW dev eth0`。
- 只治**出站**；入站（mesh → WSL 服务）的 portproxy 一条不少（见下节），要连入站一起免掉只有切 mirrored。

**ssh 在两种方案下的差异**：

- **方案 A（ProxyCommand）**：上面 sshconfig 里 `ProxyCommand nc -x <gw>:7890 ...` 让 ssh 走宿主 mihomo；动态取网关版常写 `gw=$(ip route show default | awk '{print $3}')`。
- **方案 B（tun2socks）**：tun0 已透明接管，ssh 直连即被捞进宿主 mihomo，**必须删 / 注释掉 `ProxyCommand`**——两者并存会打架。
- **典型翻车**：tun2socks 开着又留着动态取网关的 `ProxyCommand` → `ssh -T git@github.com` 报 `Connection closed by UNKNOWN port 65535`。根因：默认路由变 `default dev tun0`（无 `via`），`awk '{print $3}'` 取出 `tun0` 当网关，执行 `nc -x tun0:7890` 解析不了主机名秒退。`UNKNOWN port 65535` 是 ProxyCommand 管道拿不到对端 `getpeername` 的通用指纹，任何 ProxyCommand 子进程异常退出都长这样，不特指本 bug。修法：删 ProxyCommand（走方案 B），或把取网关改成 `ip route get 1.1.1.1`（走方案 A）。

## WSL / Docker 服务暴露（入站：portproxy + wslrelay）

> 方向区分：本节是 **Windows / EasyTier / 远端入口 -> WSL 内服务**（入站）。反方向的 WSL 出站走 Mihomo 见上面的 [WSL NAT 下出站走 Mihomo](#wsl-nat-下出站走-mihomo)。注意 **WSL 出站访问 mesh（`10.144.x`）本来就通、无需 portproxy**（NAT 下出站全交给宿主，宿主已有 mesh 路由）；portproxy 只解决**入站**（让 mesh / 远端访问 WSL 内服务）。要**少 / 免**逐服务配 portproxy，见下面「少 / 免逐服务 portproxy 的两条路」。

### 少 / 免逐服务 portproxy 的两条路（A mirrored / B 单反代兜底）

`netsh portproxy` 无端口段 / 通配，一端口一条规则——服务一多就是几十条 toil（本机实测曾积到 23 条）。比"每服务一条"更省的两条路：

- **A. mirrored 网络模式**（`.wslconfig` 加 `networkingMode=mirrored`，Win11 22H2 / build 22621+）：WSL 共享宿主网络栈，WSL 服务监听 `0.0.0.0:N` 即被宿主各 IP（含 EasyTier mesh IP）的 `:N` 直达，**portproxy 一条不用、也没 wslrelay / #14154**。代价是一次性迁移：`wsl --shutdown`、删掉现有 portproxy、**重估 EasyTier wintun 路由优先级**（mirrored 最大的不确定点）、Docker Desktop 会重启一次。要"以后永久零转发配置"选这条。
- **B. WSL 内单反代兜底 + 1 条 portproxy**（保持 NAT、不碰 EasyTier）：WSL 里跑一个反代（Caddy / nginx / Traefik）监听单个端口，**只配 1 条** portproxy（`宿主 mesh-IP:443 → 127.0.0.1:<反代端口>`），反代按 Host / 子域 / 路径分流到各 WSL 服务。**新增服务 = 加一段反代 site 配置 + reload，`netsh` 一条不加**；#14154 的纯 v4 坑只剩那 1 个端口要管。链路：远端 Caddy → 宿主 mesh IP:443 →（1 条 portproxy）→ WSL 反代 → 各服务。想保持 NAT 现状、避免动 EasyTier 选这条；**已在 WSL 跑反代（如 Caddy）时几乎零成本**。

取舍：**A** 是终极零配置但要停机 + 担 EasyTier 重估风险；**B** 不停机、不碰 EasyTier，把 N 条 portproxy 收敛成 1 条、新服务只动反代配置。另有 **C**（定时脚本扫 `ss -tln` 自动同步 netsh 规则）只是把手动 toil 自动化、治标不治本，#14154 仍每服务要防，一般不推荐。

WSL NAT 下，要把 WSL 内服务暴露给 Windows / EasyTier / 远端反代，需要 Windows `netsh interface portproxy` 做 TCP 转发：它把 Windows 宿主某个监听地址和端口转到 WSL 内服务。`portproxy` 不负责让 WSL 出站走 Mihomo，也**不支持 UDP**。

```powershell
# 示例：Windows 在 <windows-listen-ip>:18080 监听，转发到 WSL localhost:18080
netsh interface portproxy add v4tov4 `
  listenaddress=<windows-listen-ip> listenport=18080 `
  connectaddress=127.0.0.1 connectport=18080

netsh interface portproxy show all
```

**推荐 `connectaddress=127.0.0.1`**（靠 wslrelay 的 localhost forwarding），而非 WSL NAT IP——NAT IP 会随 WSL 重启变化、不稳。配套：WSL 内服务也监听 `127.0.0.1`（纯 v4）——docker 写 `127.0.0.1:N:N`、native 服务 listen `127.0.0.1`，别用 `::`（避免 #14154 的 dual-stack v6 形态，见下）。

### wslrelay / IPv6 dual-stack 坑（#14154）

**症状**：portproxy 表正确建立，从 Windows 或 EasyTier 远端 TCP 能 connect，但请求一发出立刻 `Connection reset by peer` / `Recv failure: Connection was reset`（TCP **RST**，下文同——对方在 TCP 层主动拆掉连接），或直接 `Failed to connect`。

**根因（坐实）**：[microsoft/WSL#14154](https://github.com/microsoft/WSL/issues/14154) — “Dual-mode IPv6 sockets do not accept IPv4 connections via localhost”，**open** 状态、`network` label、2026-02 提交、2026-05 仍在更新（数月未修）。issue 里 distro 内部 `curl -4 http://localhost:N` 就已经 refused，跨 wslrelay 到 Windows 必然继承同样症状。

**和 Docker Desktop 无关、native dockerd 一样踩**：实测一台 WSL 内 systemd 起的 native dockerd（非 Docker Desktop），bare `ports: 9000:9000` 时 docker-proxy 默认开 dual-stack v6 socket，照样 RST。原文档把这段写成“Docker Desktop 容器端口的 wslrelay/IPv6 坑”是窄了。

#### WSL 里的 socket 形态 → wslrelay 实际行为

| WSL 里 `ss -tlnp` 显示 | family | `IPV6_V6ONLY` | wslrelay 在 Windows 这边建 | 实测结果 |
|---|---|---|---|---|
| `127.0.0.1:N` 纯 v4 | AF_INET | n/a | `127.0.0.1:N` (v4) | ✅ 通（**推荐**） |
| `0.0.0.0:N` 纯 v4 | AF_INET | n/a | `127.0.0.1:N` (v4) | ✅ 通 |
| `[::]:N` 纯 v6 | AF_INET6 | 1 | `[::1]:N` (v6) | 一致；v4 client refused |
| `*:N` dual-stack v6 | AF_INET6 | **0** | **只建 `[::1]:N`，不补 v4** | ❌ portproxy `connectaddress=127.0.0.1` → RST |

第三行就是 #14154 的形态。原因（这部分是推测）：wslrelay 看 socket family 为 v6 就照镜子建一个 v6 listener，没读 `IPV6_V6ONLY=0` 这个 bit，所以漏掉了对应的 v4 listener。

#### 端到端链路（NAT 模式 + EasyTier + WSL distro）

```
[EasyTier peer (e.g. <mesh peer> <mesh-peer-IP>)]
            ↓ TCP
[Windows host kernel + EasyTier wintun]                受 <mesh 子网> 路由
            ↓
[svchost.exe / iphlpsvc] LISTEN <Windows机 mesh IP>:9000    ← netsh portproxy 这条
            ↓ connectaddress=127.0.0.1 connectport=9000
[wslrelay.exe]           LISTEN 127.0.0.1:9000        ← Microsoft 官方进程，NAT 模式触发
            ↓ Hyper-V vsock
[WSL distro socket]      0.0.0.0:9000 / *:9000        ← 必须是纯 v4 才不触发 #14154
            ↓
[Docker bridge / process]
```

两个组件都不能省、互不感知：

- `netsh portproxy` 由 Windows `iphlpsvc` 承载，只是个通用 TCP 转发表，**不知道 WSL 存在**；它需要 connectaddress 那端有人接，正好 `127.0.0.1` 那端是 wslrelay 在 listen。
- `wslrelay.exe` 是 WSL2 NAT 模式的 localhost forwarding 实现，**只在 Windows host 的 `127.0.0.1` / `[::1]` 上 listen**，不会 listen 任意 host IP（如 EasyTier 的 `<Windows机 mesh IP>`）。
- `.wslconfig` 里 `hostAddressLoopback=true` 容易让人误以为是“让 host IP 也能 forward 进 WSL”——**不是**。它的方向是反的：让 WSL 进程能通过 host IP 访问 host loopback service。见下面实测。

#### 实测：删掉 portproxy、靠 wslrelay 单独扛行不行（结论：不行）

测试机 `.wslconfig`：`hostAddressLoopback=true`（已开）、`networkingMode` 默认 NAT。删 portproxy `<Windows机 mesh IP>:9000 → 127.0.0.1:9000` 那一条，其他 14 条保留。

| 测试 | baseline | 删 portproxy 后 |
|---|---|---|
| netsh portproxy 表里 9000 | ✅ 在 | ❌ 已删 |
| Windows 这边 listen 127.0.0.1:9000 | wslrelay | wslrelay（不变） |
| Windows 这边 listen <Windows机 mesh IP>:9000 | svchost | ❌ 无人 listen |
| Windows → 127.0.0.1:9000 | 200 | **200** |
| Windows → <Windows机 mesh IP>:9000 | 200 | ❌ refused 2s 立刻 |
| mesh peer A → <Windows机 mesh IP>:9000 | 200 | ❌ timeout 5s |
| mesh peer B → <Windows机 mesh IP>:9000 | 200 | ❌ timeout 5s |

结论：

- wslrelay **始终只在 `127.0.0.1` listen**，不会自动 listen mesh IP；`hostAddressLoopback=true` 不改变这件事。
- NAT 模式下，要让 host 网卡 / 虚拟网卡 (EasyTier wintun) 的 IP 上某个端口能进 WSL distro，**netsh portproxy 这一跳无法省**。
- 删 portproxy 后立即 `Could not connect`（不是 RST、不是 timeout-after-handshake），印证那个 IP 上根本没有 listener。

#### 辨识与修复

辨识：

```bash
# WSL 里
ss -tlnp | grep :<port>
#  127.0.0.1:<port> / 0.0.0.0:<port>  → 纯 v4，没问题（推荐用 127.0.0.1）
#  *:<port>        → dual-stack v6（#14154 形态）
#  [::]:<port>     → 纯 v6（v4 client 也会 refused，但形态不同）
```

```powershell
# Windows
Get-NetTCPConnection -State Listen -LocalPort <port> | Format-Table LocalAddress,LocalPort,OwningProcess
# 看 127.0.0.1 那一行进程是不是 wslrelay；如果只有 [::1] 没有 127.0.0.1
# 而且 listenaddress=<host-ip> 的 portproxy 配过了仍 RST，几乎可以确认 #14154

# 直接验证 Windows 侧 [::1] 是否能接连接（#14154 形态下通常 RST）：
curl.exe --noproxy * -v --max-time 5 "http://[::1]:<port>/"
```

修复（按推荐度）：

1. **显式 v4 监听地址**（首选，零代价）：
   - Docker / docker-compose：**推荐写 `ports: ["127.0.0.1:9000:9000"]`**，不要 bare `"9000:9000"`（bare 让 docker-proxy 选 dual-stack v6 socket，触发 #14154）。显式写 v4 host IP `127.0.0.1` 即纯 v4，不踩坑。
   - 服务直接 listen：**推荐 listen `127.0.0.1`**，不要用 `::`。Python `http.server` 默认 v4，Go `net.Listen("tcp", ":N")` 默认 dual-stack v6，要写 `net.Listen("tcp4", "127.0.0.1:N")`。
   - **Java / JVM 服务**（Neo4j / Elasticsearch / Kafka / Spark 等）：JVM 默认开 dual-stack v6，**即使配置文件写 `listen_address=0.0.0.0` 也会落到 `*:N` 形态**（socket 是 AF_INET6 + V6ONLY=0，恰好是 #14154 触发点）。fix 是加 JVM flag `-Djava.net.preferIPv4Stack=true` 强制纯 v4 socket。
     > **Neo4j 5.x apt 包实测**：编辑 `/etc/neo4j/neo4j.conf`，把 `#server.bolt.listen_address=:7687` 取消注释改成 `server.bolt.listen_address=0.0.0.0:7687`，再追加一行 `server.jvm.additional=-Djava.net.preferIPv4Stack=true`，`systemctl restart neo4j` 之后 `ss -tlnp` 从 `*:7687` 变 `0.0.0.0:7687`，wslrelay 看到纯 v4 listener 才会在 Windows 端补 `127.0.0.1:7687` 的 v4 listener，portproxy `connectaddress=127.0.0.1` 这条才不会 RST。**单改 `listen_address=0.0.0.0` 一行不够**，必须同时给 JVM 加 preferIPv4Stack=true。（listen 用 `127.0.0.1` 或 `0.0.0.0` 都是纯 v4、等效；上面是当时实测的 `0.0.0.0` 原值，关键是 `preferIPv4Stack`。）
2. **portproxy `connectaddress` 指 WSL eth0 IP**（跳过 wslrelay 走 NAT）——**不推荐**：eth0 IP 随 WSL 重启变化、不稳；优先第 1 条（服务监听 `127.0.0.1` + `connectaddress=127.0.0.1`）。
3. **portproxy 改用 `v4tov6` 转 `::1`**：理论可行，但实测在不少 WSL 版本上 wslrelay 的 `[::1]` listener 也 RST，所以不一定通。作为快速试探可用，长期不推荐。
4. **切 `networkingMode=mirrored`**（Win11 22H2+）：彻底没 wslrelay。代价是重排所有 portproxy + 评估对 EasyTier wintun 路由优先级的影响。
5. **WSL 内补 socat v4 relay**：`socat TCP4-LISTEN:<port>,reuseaddr,fork,bind=0.0.0.0 TCP:[::1]:<port>`，让 wslrelay 看到的是纯 v4 listener。多一跳进程，仅作 fallback。

### 全双工大流量下 wslrelay 死锁（#10688）

[microsoft/WSL#10688](https://github.com/microsoft/WSL/issues/10688)（open，与上面 #14154 不同）：WSL 本地转发（Linux 侧转发进程 + `wslrelay.exe`）用**单个阻塞线程同时拷贝一条连接的两个方向**（半双工逻辑）；双向同时大流量时两端缓冲填满、relay 卡在 `write()` 上不再读另一边 → 永久死锁。诊断特征（`ss -tn`，卡死的 socket 对收发队列堆住、流量永久冻结）：

```
State  Recv-Q   Send-Q     Local Address:Port     Peer Address:Port
ESTAB  0        2914479    127.0.0.1:<svc>        127.0.0.1:<relay>
ESTAB  3176712  0          127.0.0.1:<relay>      127.0.0.1:<svc>
```

本机实测（NAT 模式，Windows `127.0.0.1` → wslrelay → WSL；原生 + docker、bind `0.0.0.0` + `127.0.0.1` 共四种发布形态）：

| 流量模式 | 结果 |
|---|---|
| 单向下行 / 单向上行（任意大小） | 不卡 |
| 严格乒乓请求/应答（半双工，HTTP/1.1 形态） | 不卡 |
| HTTP/1.1 下载 100MB（`curl.exe`） | 不卡 |
| 真 SSH 全双工 ↓200MB + ↑100MB（`ssh.exe`） | 不卡 |
| 合成程序双向并发 blast（不积极收 socket，本机 ~0.65MB 起） | **卡死** |

- **只有全双工双向大流量才可能触发**；任何半双工（单向 / 乒乓 / HTTP 下载）都不触发。
- **真实程序（SSH、HTTP）实测不中招**，无论多大；只有"不积极收 socket"的朴素 blast（如 issue 的合成 reproducer）才稳定复现。
- **与发布地址无关**：四种发布形态阈值完全一致（本机 `route_localnet=0`，两种 docker 形态都经 docker-proxy，回环路径相同）。
- 彻底规避：切 `networkingMode=mirrored`（无 wslrelay）。`connectaddress=127.0.0.1` 仍按上文推荐（理由是不漂移，与本坑无关）。

历史背景与 issue：[microsoft/WSL#14154](https://github.com/microsoft/WSL/issues/14154) (open)、[#10688](https://github.com/microsoft/WSL/issues/10688) (open，wslrelay 全双工 hang)；类似 v4/v6 困扰在 WSL repo 里有十几个独立 issue，labels 多数 `network`。

### EasyTier + 远端 Caddy 的入站稳定方案

WSL NAT + Windows EasyTier + 远端 Caddy 的简单稳定方案：

```text
远端 Caddy reverse_proxy -> Windows EasyTier IP:port
Windows portproxy -> 127.0.0.1:port
WSL 服务监听 127.0.0.1，由 Windows localhost forwarding (wslrelay) 转发访问
```

`netsh interface portproxy` 是 TCP 转发，不支持 UDP。WSL NAT 下**推荐 `connectaddress=127.0.0.1`**（配套服务监听 `127.0.0.1`），而非 WSL NAT IP——NAT IP 会随 WSL 重启变化。批量检查：

```powershell
netsh interface portproxy show all
```

从云服务器探测 TCP 时，避免用 Bash `/dev/tcp/...` 形式；这类命令容易被云安全产品识别为反弹 shell 特征。HTTP(S) 端口优先用：

```bash
curl -k -I --connect-timeout 5 --max-time 8 https://<target>:<port>/
```


