# NAS / Synology 相关已知坑

> 两类坑都记在这：① Synology DSM 自家魔改 docker 的怪异行为，跟上游 docker / docker-compose 不一致的部分；② NAS-backed 存储（iSCSI LUN / NFS / SMB）挂到其他宿主后，性能特征或故障模式跟本地盘不一样、容易被误判的情况。

## DSM Container Manager: `failed to initialize logging driver: database is blocked` (短时间多次 recreate 触发)

### 症状

短时间内（5-10 min 内）对同一个项目做多次 `recreate` / `stop+start` 操作后，再次尝试启动容器报：

```
failed to initialize logging driver: database is blocked
```

容器状态卡在 stopped / 启动失败循环。**单独的 docker 命令、`docker compose ps` 等正常运行。**

### 误导路径

容易误判：
1. ❌ 以为是**自家应用**（如 RustFS / Postgres）的内部数据库 lock —— 去翻应用源码搜 “database is blocked”，0 匹配
2. ❌ 以为是**应用 RocksDB / SQLite metadata** stale lock —— 去找 LOCK 文件清理
3. ❌ 以为是**最近改的 compose 文件**（init container / volume mount / chown）有副作用 —— 回滚 compose 也修不好

### 实际 root cause

`logging driver` 是 **docker daemon 自家术语**，指 docker 用来抓容器 stdout/stderr 的 driver（默认 `json-file`），写到 `/var/lib/docker/containers/<id>/<id>-json.log`。

`database is blocked` 是 **Synology DSM 魔改 docker** 用来跟踪 container 元数据的 SQLite 撞 WAL lock。短时间多次 recreate 让 sqlite WAL 没机会释放就被下一次操作覆盖，最终 daemon 拿不到 lock。

跟应用层（RustFS / Postgres / 任何业务容器）**完全无关**。跟你最近改的 compose / chown / bind mount **也无关**。

### 修法（按代价从轻到重）

1. **等 1-2 分钟后再试启动** —— sqlite WAL 自然释放（绝大多数情况这步搞定）
2. **DSM 控制面板 → 套件中心 → Container Manager → 停用 → 启用** —— 重启 docker daemon，强制释放所有 lock（~30s）
3. **DSM 重启**（不推荐，影响一切）

> ⚠️ **绝对不要 “卸载 Container Manager”**：bind mount (在 `/volume1/docker/` 下) 安全，但 **named volume**（在 `/volume1/@docker/volumes/`，属套件管辖）**有丢的风险**。停用 → 启用 跟卸载不一样，前者绝对安全。

### 预防

短时间内**不要**做密集 recreate 操作。试探性 compose 改动建议：

1. 先把所有候选方案列全（B/D/...）
2. 一次性选定方向
3. 一次 recreate 验证

避免“改 → recreate → 看结果 → 改回 → recreate → 再改 → recreate”这种密集循环触发。

### 关键词

`failed to initialize logging driver`、`database is blocked`、`DSM Container Manager`、`Synology docker`、`json-file driver`、`SQLite WAL lock`、`短时间多次 recreate`、`/var/packages/ContainerManager`、`/volume1/@docker`、`logging driver` (docker daemon 概念,不是应用日志)、`停用启用 Container Manager`

## Postgres 崩溃恢复卡在 checkpoint「像是死了」，其实是 NAS iSCSI LUN 上的 fsync 巨慢（不是真卡死）

> 2026-07-05 | Postgres 17 + pgvector（`qatlas-postgres` 容器）| PGDATA 挂在 NAS（Synology DSM 建 iSCSI Target/LUN）→ Windows iSCSI Initiator → `wsl --mount` 挂进 WSL2 为 `/dev/sdg` → `/mnt/qatlas-pg`（ext4）

> 记录原则：这次判断一度是错的（"卡死"），事后才发现只是慢。如实记录当时凭什么下的判断、以及这个判断方法本身的局限。

### 症状

- 因为处理另一件事（见 [`bug-fix.md`](bug-fix.md) 的 Docker 内置 DNS 案例）被迫 `docker rm -f` 强制移除了这个 Postgres 容器，重建后触发崩溃恢复：WAL redo 阶段正常（约56秒，LSN 持续增长，日志有真实进度），之后进入 `checkpoint starting: end-of-recovery immediate wait`。
- 这一步之后看起来彻底不动了：
  - `docker top qatlas-postgres` 显示 checkpointer 进程长期处于 **`Ds`**（不可中断磁盘睡眠）状态，CPU 恒为 `0.00%`。
  - `docker stats` 的 **BlockIO 字节计数器**在相隔 20 秒、90 秒、10 分钟、直到最终 **21+ 分钟**的多次复测中，数值分毫不变（`153MB / 176kB` 恒定）。
  - `/mnt/qatlas-pg` 挂载本身当时查询（`df -h`、`ls`）响应迅速正常——不支持"整条 iSCSI 链路当前彻底断线"这么简单的解释。

### 排查关键转折（含一个错误判断）

- 基于上面的证据（`Ds` + 0%CPU + 计数器长时间不变），当时**判定为"真卡死"**：Linux 里 D 状态通常意味着进程卡在一个不会超时的内核态 I/O 系统调用上，SIGKILL 对它无效，一般只能等这个具体 I/O 请求最终返回，或用更底层手段（重启 WSL2/Docker Desktop）强制解除。这个推理本身没错，但**推出的结论（"真卡死"）后来被证明是错的**。
- 用户叫停（"不着急，别搞坏那边的东西"）后改为纯观察，不再做任何操作。等待期间去翻了另一个历史 session 的记录，发现这个库的 PGDATA 实际上跑在 NAS 提供的 iSCSI LUN 上，且历史上已经有过明确分析："纯粹卡在写路径 / WAL fsync——每次 commit 都要等网络存储 fsync 落盘，这是硬地板"，当时的库还有一张约 262M 行 / 49GB 的大表。
- 后续复查时，checkpoint **自己跑完了**。真实日志给出了铁证：
  ```
  checkpoint complete: wrote 1514626 buffers (24.1%); ...
  write=675.878 s, sync=727.911 s, total=1406.334 s;
  sync files=79, longest=565.499 s, average=9.186 s
  database system is ready to accept connections
  ```
  单个文件 fsync 最长耗时 **565 秒（9.4 分钟）**，总耗时 **1406 秒（23.4 分钟）**。

### 根因

不是卡死，是真的慢：`end-of-recovery` checkpoint 要把崩溃前的脏页全部刷盘并 fsync，而 PGDATA 落在 NAS-backed iSCSI 网络存储上，单个文件的 fsync 延迟可以长达 9 分钟以上。之前判断"卡死"所依赖的观测窗口（最长 21 分钟）**在统计学上根本不够长**——相对于"单次操作可能耗时 9 分钟"这个真实分布，21 分钟内"看起来没有变化"完全可能只是恰好卡在两次真实进度更新之间的采样间隙，不能反推"没有进展"。

### 解决 / 结果

什么都没做，纯等待。容器最终变回 `healthy`，`pg_isready` 确认 accepting connections，容器内 DNS（`getent hosts qatlas-postgres`）也恢复正常（说明它和 [`bug-fix.md`](bug-fix.md) 的 Docker DNS 故障其实是同时叠加、但彼此独立的两件事）。

### 教训

- **`docker top` 的 `Ds` + `docker stats` 的 BlockIO 计数器不变，这个组合证据本质上无法区分"真卡死"和"单次操作巨慢但仍在推进"**——两种情况在任何有限长度的观测窗口内表现完全一样。唯一能实锤的办法是等它自己给出结果（进程状态变化、日志吐出精确耗时），或者去查更底层的、真正逐次更新的指标（比如 `/proc/<pid>/io` 里的 `rchar`/`wchar` 字节数，如果能拿到真实的容器内 PID 而不是 Docker Desktop VM 里不可见的 PID）。
- **数据库承载了已知的"大表 + 慢速网络存储"组合时，checkpoint/崩溃恢复耗时 20-30 分钟应视为正常范围**，不要看到"进程 D 状态 + 计数器没变"就直接判定故障、贸然二次强杀容器——二次强杀一个正在做 fsync 的 Postgres 只会让它再崩溃一次，进入同样的恢复循环。
- 遇到"看起来卡死"的场景，先查这个存储/数据库过去是否有过"写路径慢"的已知记录（本次是靠翻另一个历史 session 的 checkpoint 记录才想起来的），比自己从零建立假设快得多。
- 观察窗口要和怀疑的"单次操作耗时量级"匹配——怀疑"卡在一次 fsync"，就该敢于等到比"最坏情况下一次 fsync 需要的时间"更长，而不是几分钟就下结论。

### 关键词

`Postgres checkpoint 卡住`、`end-of-recovery checkpoint`、`Ds 状态`、`不可中断磁盘睡眠`、`docker stats BlockIO 不变`、`iSCSI LUN`、`NAS-backed 存储`、`WAL fsync 慢`、`wsl --mount`、`崩溃恢复耗时长`、`checkpoint complete sync=727s`、`误判为死锁`、`pg_isready`、`大表 + 慢速存储 checkpoint 正常耗时`

## <a id="iscsi-ip-change"></a>iSCSI LUN 重连：NAS 换 IP 与初始化器里的陈旧绑定

> 2026-07-25 | 与上一条同一套链路：Synology NAS 建 iSCSI Target/LUN → Windows iSCSI Initiator → `wsl --mount --bare` → WSL2 `/dev/sdX`（整盘 ext4，无分区表）→ docker volume。下文 `<NAS-旧IP>` / `<NAS-新IP>` / `<NAS 主机名>` 为占位符。

> 记录原则：这次中途下过一个错误结论（"NAS 关机了"），下面如实保留当时凭什么这么判断、以及那个判据错在哪。

### 症状

WSL 里 `/dev/sdX` 消失，依赖它的 docker volume（`driver_opts` 写死 `device: /dev/sdX`）起不来。Windows 侧：

- `Get-IscsiSession` 有一条会话，但 `IsConnected=False`
- `Get-IscsiConnection` **返回空**（没有任何真实 TCP 连接）
- `Connect-IscsiTarget` 报 `已经通过 iSCSI 会话登录目标`（`HRESULT 0xefff003f`）而拒绝执行

于是形成死锁：既没连上，也不允许重连。

### 端口探测在 TUN 代理下不可用作存活判据

用 `Test-NetConnection` 和 bash `/dev/tcp` 探已经失效的 `<NAS-旧IP>`，3260 / 5000 / 5001 / 445 **全部报"通"**。实际那个地址上什么都没有——本机跑着 Mihomo/Clash TUN，代理**就地接下了 TCP 握手**，握手成功不代表对端存在。

> 实测：同一时刻 `Test-NetConnection <NAS-旧IP> -Port 3260` → `TcpTestSucceeded=True`，而 .NET `TcpClient.ConnectAsync` 对同一地址端口 → `False`。TUN 拦截的原理见 `network` skill 的 Mihomo TUN / fake-ip 章节。

可靠判据（按可信度）：

| 判据 | 说明 |
|---|---|
| ARP 表（`Get-NetNeighbor`） | 链路层，代理伪造不了 |
| .NET `TcpClient.ConnectAsync` | 实测能把死地址和活地址干净区分开 |
| 真实 HTTP 响应（`Invoke-WebRequest`） | 有响应体才算活 |
| ~~`Test-NetConnection`~~ / ~~`/dev/tcp`~~ | 本环境下会给假阳性 |

```powershell
$c = New-Object System.Net.Sockets.TcpClient
$ok = $c.ConnectAsync('<NAS-IP>', 3260).Wait(4000)
"connected=" + ($ok -and $c.Connected)
$c.Close()
```

### ARP 不可达只说明该地址没人应答

旧地址的 ARP 项是 `00-00-00-00-00-00 / Unreachable`，而同网段上百台设备都有真实 MAC、网关 `Reachable`。据此当时判定"NAS 断电或掉线"——**这个结论是错的**。

ARP 能证明的只是"**这个地址**上没有设备应答"，不能证明"**这台设备**不在了"。设备换了地址，旧地址一样表现为不可达。下判断前应先按主机名解析一次。

### 按主机名与厂商 OUI 定位新地址

Synology 默认注册 mDNS，主机名直接能解析：

```powershell
Resolve-DnsName <NAS 主机名>        # -> <NAS 主机名>.local -> <NAS-新IP>
```

交叉验证：在 ARP 表里按 Synology 的厂商 OUI（MAC 前三段 `00-11-32` / `90-09-D0`，IEEE 公开注册）筛，能独立确认哪台是 NAS。

```powershell
Get-NetNeighbor -AddressFamily IPv4 |
  Where-Object { $_.LinkLayerAddress -match '^(00-11-32|90-09-D0)' } |
  Select-Object IPAddress, LinkLayerAddress, State
```

### 换掉 portal 之后登录仍然超时

把 portal 改到 `<NAS-新IP>` 后，SendTargets 发现**成功**（`iscsicli ListTargets` 能列出 target），但 `Connect-IscsiTarget` 与 `iscsicli QLoginTarget` 双双超时（60s / 90s），每次还留下一条新的僵尸会话。

真凶在持久化目标（persistent target，开机自动重连用的书签）里，它单独记着地址，**不随 portal 更新**：

```
> iscsicli ListPersistentTargets
共 1 个永久目标
    目标名称     : iqn.2000-01.com.synology:<target>
    地址和套接字 : <NAS-旧IP> 3260      <- 仍钉在死地址
```

`iscsicli TargetInfo <iqn>` 也会显示该 target 同时挂着新旧两条 `SendTargets:` 发现机制。登录时走到死地址那条就一路等到超时。

> 诊断上的差别：`Connect-IscsiTarget` 只会静默卡住，不说自己在连哪个 portal；`iscsicli` 系列会把地址、持久化条目、错误码都打出来。cmdlet 查不出原因时换 `iscsicli`。

### PowerShell 数组真值导致的误判

`Get-IscsiTarget -NodeAddress` 匹配 **大小写不敏感**。NAS 上若注册过大小写不同的两个 IQN（例如目标改过名），它会返回**数组**，于是：

```powershell
$t = Get-IscsiTarget -NodeAddress $iqn   # 返回 2 个对象
if ($t.IsConnected) { ... }              # -> @($false, $false)
                                         # 非空数组恒为真 -> 误判"已连接"
```

结果是脚本报告"已经连上了"，实际连接动作从未执行。判断前先确认返回的是单个对象。

### 恢复顺序

清掉所有陈旧绑定，再显式钉住活的 portal 登录：

```powershell
# 1. 拆僵尸会话（无连接、无磁盘暴露时拆除不涉及数据）
Get-IscsiTarget | ForEach-Object {
    Disconnect-IscsiTarget -NodeAddress $_.NodeAddress -Confirm:$false -ErrorAction SilentlyContinue
}

# 2. 清掉钉在旧地址的持久化目标，并重启初始化器刷内存态
iscsicli ClearPersistentTargets
Restart-Service MSiSCSI -Force

# 3. 只保留活着的 portal
Remove-IscsiTargetPortal -TargetPortalAddress '<NAS-旧IP>' -Confirm:$false
New-IscsiTargetPortal    -TargetPortalAddress '<NAS-新IP>'

# 4. 登录时显式指定 portal，避免又被旧地址抢走
Connect-IscsiTarget -NodeAddress '<iqn>' `
                    -TargetPortalAddress '<NAS-新IP>' -TargetPortalPortNumber 3260 `
                    -IsPersistent $true

# 5. 整盘交给 WSL（LUN 是无分区表的整盘 ext4，故用 --bare）
wsl --mount \\.\PHYSICALDRIVE<N> --bare
```

以上都需要管理员权限；从 WSL 侧发起提权的做法见 `software` skill 的 Windows/WSL 宿主侧章节。

> ⚠️ Windows 可能把这块盘识别为"未初始化"。**不要接受初始化 / 分区 / 格式化的提示**（`Initialize-Disk`、`New-Partition`、`Format-Volume`、`Clear-Disk`）——LUN 上是 Linux 侧的整盘文件系统，Windows 不认识它是正常的，一旦写入分区表数据即毁。盘若是 `IsOffline`，只做 `Set-Disk -IsOffline $false` 就够。

### 设备名漂移的风险

docker volume 若把设备写死（`driver_opts: device: /dev/sdg`），而 LUN 重新挂载后被分到别的字母，volume 就会指向错误的设备或失败。本次重连后仍是原字母，**没有触发**该问题。

mount(8) 支持 `LABEL=` / `UUID=`，理论上写成 `device: LABEL=<卷标>` 可以规避漂移，但**未实测**，采用前需自行验证。用 `lsblk -o NAME,SIZE,FSTYPE,LABEL,UUID` 可确认卷标与 UUID。

### 教训

- **"某地址不可达"和"某设备不在了"是两回事**。设备可能只是换了地址；断定硬件故障前先按主机名解析、按厂商 OUI 扫一遍 ARP。
- **代理 / TUN 环境下，端口探测不能当存活判据**——TCP 握手可能由本地代理完成。要么用链路层证据（ARP），要么用能拿到真实响应的探测。
- **iSCSI 的地址记在多个地方**：portal 注册、target 的发现机制列表、持久化目标条目。只改其中一处，其余仍会把登录导向死地址。
- **cmdlet 卡住不给理由时，换更啰嗦的原生 CLI**（`iscsicli`）——它会直接打印地址和错误码。

### 关键词

`NAS 换 IP`、`iSCSI 重连`、`/dev/sdg 消失`、`wsl --mount --bare`、`Get-IscsiSession IsConnected False`、`Get-IscsiConnection 为空`、`已经通过 iSCSI 会话登录目标`、`HRESULT 0xefff003f`、`Connect-IscsiTarget 超时`、`QLoginTarget 超时`、`iscsicli ListPersistentTargets`、`持久化目标钉在旧 IP`、`ClearPersistentTargets`、`Restart-Service MSiSCSI`、`TargetPortalAddress 显式指定`、`僵尸 iSCSI 会话`、`Test-NetConnection 假阳性`、`/dev/tcp 假阳性`、`TUN 接管 TCP 握手`、`TcpClient ConnectAsync 判活`、`ARP Unreachable 误判关机`、`Get-NetNeighbor`、`Synology OUI 00-11-32 90-09-D0`、`Resolve-DnsName mDNS .local`、`Get-IscsiTarget 大小写不敏感`、`PowerShell 数组真值`、`不要 Initialize-Disk`、`docker volume device 设备名漂移`
