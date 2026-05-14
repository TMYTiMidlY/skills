# OpenList

[OpenList](https://github.com/OpenListTeam/OpenList) 是 AList 的活跃 fork，用 Go 编写的多云盘聚合面板：把 SMB / WebDAV / 各种云盘统一挂到一个 Web 界面下统一浏览、下载、预览。常作为家庭/团队的"网盘前台"。本文档关注 OpenList 自身的行为坑、与 iCloud Drive 集成的两条路径选型、以及配套的网络测速方法。

## 坑分类速查表

按"是否借助 Mac 设备"分三类。详解见后面对应章节。

| 编号 | 坑 / 注意点 | 速记 |
|---|---|---|
| **共性 — 任何方案都要避免** | | |
| C1 | 缩略图懒加载，但点开会读完整文件 | 不预扫，但点击触发整文件 |
| C2 | `DirectorySize` 开关会全目录 stat | 加存储时阻塞，默认关 |
| C3 | 搜索索引完全手动 | 不点"更新"就不会全扫 |
| **R — 不借助 Mac（rclone 直连 iCloud）专属** | | |
| R1 | ⚠️ 中国区 Apple ID 完全连不上 | 端点硬编码，PR 久未合 |
| R2 | trust token 30 天过期 | 过期需 reconnect + 2FA |
| R3 | iCloud 不支持 `SetModTime` | VFS 缓存判断不可靠 |
| R4 | iWork 文件 size 报告与实际不一致 | `rclone copy` 报 corrupted |
| R5 | 无 `ChangeNotify`，只能轮询 | Apple 协议限制，无解 |
| R6 | WSL2 + FUSE + `\\wsl$` 9P 跨边界性能差 | WSL 通用问题 |
| R7 | Ubuntu 24.04 AppArmor 阻 `fusermount3` | 需 `aa-disable` |
| **M — 借助 Mac (SMB) 中转专属** | | |
| M1 | Mac 必须常启 + 网络稳定 | Mac 离线 → 该存储 503 |
| M2 | "Optimize Mac Storage" 取舍 | 开 = 占位符首读延迟；关 = 全文件常驻本地 |
| M3 | `~/Library/...` 不能直接共享 | Finder 拒；用 symlink 出来 |
| M4 | SMB 写入产生 `.DS_Store` | 关 `DSDontWriteNetworkStores` |

## 一、共性坑详解（任何 backend 都成立）

### C1 缩略图是懒加载，但点开就是整文件读

加 SMB / 本地 / WebDAV / rclone mount 等任何存储时**不会**预扫描全库生成缩略图；只有用户在前端**点开图片/视频时**才走 HTTP `?type=thumb` 触发一次。

来源：`OpenListTeam/OpenList:drivers/local/util.go`（[源](https://github.com/OpenListTeam/OpenList/blob/main/drivers/local/util.go)）

```go
// 图片缩略图（约第 88 行）
imgData, err := os.ReadFile(fullPath)   // 触发时整文件读

// 视频缩略图（约第 65 行）
ffmpeg.Input(videoPath, ...).Output("pipe:", ...)   // ffprobe + ffmpeg
```

含义：每次有人点开一个新图片/视频，文件就会被完整读一遍走过 backend——
- SMB 场景：直接拉走，按网络带宽消耗一次（之后 OpenList 缩略图缓存命中就不再读）
- rclone mount 场景：会把整文件下载并塞入 vfs 缓存

缓解：存储配置里**禁用 Thumbnail** 完全规避；或者全局配 `ThumbCacheFolder` 让缩略图复用磁盘缓存避免重复读。

### C2 `DirectorySize` 开关会全目录 stat

来源：`OpenListTeam/OpenList:drivers/local/driver.go:47-56` 的 `Init()`：

```go
if d.DirectorySize {
    d.directoryMap.root = d.GetRootPath()
    _, err := d.directoryMap.CalculateDirSize(d.GetRootPath())  // 全量遍历 stat
}
```

加存储时立刻递归 `readDir + stat`——**只查元数据不下载文件内容**，但对 10 万级文件量的库会卡几分钟。

> 本地 backend 上述行为已源码验证；其他 backend (SMB / WebDAV / rclone) 大概率类似——加存储时按需 stat，不会主动拉全文件内容。

缓解：**默认关闭**；只在需要"前端显示目录总大小"时才开。

### C3 搜索索引完全手动

OpenList 的 Meilisearch / 本地索引**不会自动触发**，必须管理员后台主动点"更新索引"或调 `/api/admin/scan/start`。换言之：只要不点这个按钮，OpenList 不会"在你不注意时"全量遍历库。

参考：[OpenList/OpenList#1991](https://github.com/OpenList/OpenList/issues/1991)

## 二、不借助 Mac（rclone 直连 iCloud）专属坑

走 rclone v1.69+ 内置的 `iclouddrive` backend 直连 iCloud 时，以下问题需要预期。**Mac 中转方案下这些都不存在。**

### R1 ⚠️ 中国区 Apple ID（@icloud.com.cn）完全连不上

rclone 把 API 端点硬编码（`backend/iclouddrive/api/client.go`）：

```go
const (
    baseEndpoint  = "https://www.icloud.com"
    setupEndpoint = "https://setup.icloud.com/setup/ws/1"
    authEndpoint  = "https://idmsa.apple.com/appleauth/auth"
)
```

中国大陆 iCloud 实际是 `*.icloud.com.cn`，认证返回：

```
NOTICE: Fatal error: HTTP error 302 (302 Found) returned body:
  "{\"domainToUse\":\"iCloud.com.cn\"}"
CRITICAL: Failed to create file system for "iCloud:": missing icloud trust token
```

修复 PR [rclone#8818](https://github.com/rclone/rclone/pull/8818)（添加 `region` 配置项）状态 **OPEN（dirty）**，原 issue [rclone#8257](https://github.com/rclone/rclone/issues/8257) 同样 **OPEN**。截至文档时间未合并。变通办法是切到带 patch 的 fork 自己编译。

**有 @icloud.com.cn 账号的，rclone 这条路直接放弃。**

### R2 trust token 30 天过期

rclone 通过 SRP 认证拿到的 trust token 30 天后失效，需要：

```bash
rclone config reconnect iCloud:
```

并重新走 2FA（物理设备确认或 SMS）。

历史问题：2025-06 Apple 弃用旧版 `/appleauth/auth/signin` 明文登录端点，导致所有用户 token 过期后无法重新认证（[rclone#8587](https://github.com/rclone/rclone/issues/8587)，144 👍）。已由 [PR rclone#9209](https://github.com/rclone/rclone/pull/9209)（SRP 重写）在 v1.74.0 修复。

### R3 iCloud 不支持 `SetModTime`

源码 `backend/iclouddrive/iclouddrive.go:901`：

```go
func (o *Object) SetModTime(...) error {
    return fs.ErrorCantSetModTime
}
```

VFS 缓存的 fingerprint 依赖 size + mtime（`iclouddrive.go:840-843`）。mtime 不能写入意味着 rclone 在某些场景下**判断"文件是否变化"会不准**——可能短暂服务旧版本内容直到下次目录 poll。

### R4 iWork 文件 size 不一致

通过 iCloud Web 创建/修改的 Pages / Numbers / Keynote 文件，API 报告 size 与实际下载内容不一致：

```
failed with 1 errors and: corrupted on transfer: sizes differ
  src() 10679453 vs dst() 10501687
```

来源：[rclone#8257 评论](https://github.com/rclone/rclone/issues/8257#issuecomment-2661021687)。**不影响 mount**（VFS 实际下载内容确定大小，不依赖 API 报告），但 `rclone copy` / `rclone sync` 会失败。

### R5 没有 `ChangeNotify`，只能轮询

iCloud Drive 没有公开的 push notification 接口——Apple 自家 APNS 只对持有合法设备证书的 iPhone/Mac 推送，第三方拿不到。rclone iclouddrive backend **未实现** `ChangeNotify` 接口（源码确认），目录变化只能靠 `--poll-interval` 周期重新 list。

实际延迟天花板就是分钟级，跟 OneDrive / Dropbox（这俩有 webhook）没法比。

### R6 WSL2 + FUSE + `\\wsl$` 9P 跨边界性能差

如果 OpenList 跑在 Windows 侧，rclone mount 在 WSL2 内，OpenList 通过 `\\wsl$\<distro>\...` UNC 路径访问 mount——跨 WSL/Windows 边界要走 9P 协议，目录列举操作会有显著延迟。参考 [rclone#8408](https://github.com/rclone/rclone/issues/8408)。

变通：让 OpenList 也跑在 WSL2 内，或改用 `rclone serve webdav` 让 OpenList 走 HTTP。

### R7 Ubuntu 24.04 AppArmor 阻 `fusermount3`

新版 Ubuntu 的 AppArmor 默认 profile 会拦 `fusermount3`：

```
fusermount3: mount failed: Permission denied
```

来源：[rclone 官方文档](https://rclone.org/commands/rclone_mount/#mounting-on-linux)。处理：

```bash
sudo apt install apparmor-utils
sudo aa-disable /usr/bin/fusermount3
```

## 三、借助 Mac (SMB) 中转专属注意点

走"Mac 跑 iCloud 官方客户端 + macOS SMB 共享 + OpenList 加 SMB 存储"路径时，以下事项需注意。

### M1 Mac 必须常启 + 网络稳定

Mac 是这个链路的中转节点：
- Mac 关机 / 重启 / 断网 → OpenList 该存储 503 / 超时（不会数据丢失，但暂时不可用）
- 适合"常启的 Mac mini / iMac"，不适合"笔记本经常带出门"

接受这个依赖就行，没有技术解。

### M2 "Optimize Mac Storage" 取舍

| 状态 | 行为 | OpenList 体验 |
|---|---|---|
| **开（默认）** | 老文件本地保留 placeholder（`*.icloud`），首次访问触发 `cloudd` 下载 | OpenList 通过 SMB 读 placeholder 时 macOS 会自动下载，**首次访问有延迟**；磁盘满时下载失败 → SMB 客户端见 I/O 错误 |
| **关** | 全部文件常驻本地 | OpenList 访问立即 SMB 速度 |

**关闭路径**：系统设置 → Apple ID → iCloud → iCloud Drive → 关 "Optimize Mac Storage"。

> 关闭后 macOS 会逐步把云端所有文件下载到本地。若 Mac 磁盘吃紧，必须先确认本地能装下整个 iCloud Drive，否则会触发"磁盘已满"告警并停止下载。

### M3 `~/Library/...` 不能直接通过 Finder 共享

macOS Finder 拒绝把 `~/Library/...` 路径加到"文件共享"列表（系统隐藏目录）。变通办法是 symlink 出来：

```bash
ln -s "$HOME/Library/Mobile Documents/com~apple~CloudDocs" "$HOME/iCloud-Share"
# 然后系统设置共享 ~/iCloud-Share
```

`sharing -l` 命令查看当前所有共享点。

### M4 SMB 写入产生 `.DS_Store` 噪音

macOS 任何挂的网络共享上都会自动写 `.DS_Store`。建议在 macOS 上：

```bash
defaults write com.apple.desktopservices DSDontWriteNetworkStores -bool TRUE
# 注销后生效
```

详见 [macos.md](macos.md) 的对应小节。

## 四、iCloud 集成方案对比（选型）

```
┌─ rclone 直连 ─┐                    ┌─ Mac 中转 ─┐
iCloud 云                            iCloud 云
   │                                    │
   │ 私有 API（轮询）                    │ APNS 推送（秒级）
   │                                    ▼
rclone (WSL/Linux)              macOS 设备（官方 client，全文件本地）
   │ FUSE / WebDAV                      │ SMB
   ▼                                    ▼
OpenList 加 backend             OpenList 加 SMB 存储
```

| 维度 | rclone 直连 | Mac 中转 + SMB |
|---|---|---|
| 中国区 Apple ID | ❌ 不可用（R1） | ✅ 原生支持 |
| 同步延迟 | 1–5 分钟（轮询，R5） | **秒级**（APNS） |
| 认证维护 | 30 天重做 2FA（R2） | 一次设好永久 |
| Apple 改协议 | 立刻坏 | 不影响 |
| 文件兼容性 | iWork / mtime / 编码偶有 bug（R3、R4） | 100% |
| 性能上限 | iCloud 直连下载速度 | LAN/组网带宽 |
| 风控 | 第三方 client 有触发风险 | 官方协议 |
| 依赖组件 | rclone + fuse + systemd + 维护脚本 | 仅 macOS 文件共享开关 |
| 单点故障 | rclone 进程 / token 过期 | Mac 离线（M1） |

**默认推荐 Mac 中转**。只有"环境里没有任何常启 macOS 设备" + "账号是国际区 Apple ID" + "能接受延迟和维护成本"时才考虑 rclone 直连。

## 五、Mac SMB 中转部署步骤

### 5.1 评估 Mac 磁盘空间

```bash
# iCloud 当前占用（含未下载的占位符元数据）
ICLOUD="$HOME/Library/Mobile Documents/com~apple~CloudDocs"
du -sh "$ICLOUD"

# 已下载文件 vs 云占位符
find "$ICLOUD" -type f ! -name "*.icloud" | wc -l   # 已下载
find "$ICLOUD" -type f -name "*.icloud" | wc -l     # 占位符
```

占位符为 0 或库较小（< 10 GB） → 不动 Optimize Storage 也行。否则按 M2 决策。

### 5.2 决策 Optimize Storage

见 M2。建议关闭，确保 OpenList 体验稳定。

### 5.3 开启 macOS SMB 共享

GUI 路径：**系统设置 → 通用 → 共享 → 文件共享 → 开 + 添加共享文件夹**：
- 路径选 `~/iCloud-Share`（M3 的 symlink 目标）
- 用户权限：仅当前 macOS 用户读写
- 协议：勾上 SMB

CLI 验证：

```bash
sharing -l    # 看 List of Share Points
```

### 5.4 OpenList 加 SMB 存储

OpenList 后台 → 存储 → 添加 → 类型选 **SMB**，关键参数：

| 参数 | 值 | 说明 |
|---|---|---|
| 挂载路径 | `/icloud`（任意） | OpenList 前端展示路径 |
| Address | `<Mac 在组网内的 IP>:445` | EasyTier / Tailscale / 局域网都行 |
| Username / Password | macOS 用户名 + 登录密码 | macOS 用户必须能 SMB 登录 |
| Share Name | iCloud-Share（与 5.3 一致） | |
| **DirectorySize** | **关闭 ⚠️** | 见 C2 |
| Thumbnail | 看需求 | 开 → 用户点图会触发 SMB 拉全文件（见 C1） |
| Web Proxy | 开 | 通过 OpenList 转发，避免暴露 SMB 端口给浏览器 |

## 六、网络测速方法 + 体验对照

EasyTier / Tailscale / 自建组网下 Mac 与 OpenList 主机不一定在同一物理 LAN，实测带宽决定是否能支撑视频预览等场景。**不需要装 iperf3**——`dd over ssh` 一行命令就能跑：

```bash
# 上行：本机 → 远端
time dd if=/dev/zero bs=1M count=200 status=none | \
  ssh <remote> 'dd of=/dev/null bs=1M status=none'

# 下行：远端 → 本机
time ssh <remote> 'dd if=/dev/zero bs=1M count=200 status=none' | \
  dd of=/dev/null bs=1M status=none
```

注意：
- SSH 加密本身有 CPU 开销，比裸 TCP 略低（~10-20%），但量级正确
- 200 MB 是经验值，弱网换 50 MB；千兆 LAN 换 1000 MB
- 上下行可能严重不对称（家宽典型 100/30 Mbps，组网 relay 路径也常不对称）

### 实测体验对照

| 测得带宽 | 文档/图片 | 音频 | SD 视频 (1-2 Mbps) | HD 视频 (5-10 Mbps) | 4K (25+ Mbps) |
|---|---|---|---|---|---|
| <2 MB/s (16 Mbps) | OK | 流畅 | 边缘 | ❌ | ❌ |
| 2-10 MB/s | 秒开 | 流畅 | 流畅 | 边缘 | ❌ |
| 10-50 MB/s | 秒开 | 流畅 | 流畅 | 流畅 | 边缘 |
| >50 MB/s | LAN 体验 | LAN 体验 | LAN 体验 | LAN 体验 | 流畅 |

OpenList 主要流量方向：**SMB 主机 → OpenList 服务端**（拉文件出去），所以**这一方向**的带宽决定体验。如果走 EasyTier relay，两个方向常严重非对称，必须分别测。

### 实测样例

一次实测记录，给体验对照表标个锚点：

- **链路**：WSL2 (Ubuntu) ↔ macOS，跨家宽 NAT 经 EasyTier `relay(2)` 中继
- **NAT 类型**：PortRestricted ↔ Symmetric（无法直连打洞）
- **延迟**：~38 ms (ICMP)
- **吞吐**（200 MB dd over SSH）：
  - WSL → macOS：4 分 13 秒 → **0.79 MB/s ≈ 6.3 Mbps**
  - macOS → WSL：24 秒 → **8.23 MB/s ≈ 66 Mbps**

对照上表，下行 8 MB/s 落在 "2-10 MB/s" 行——文档/图片秒开、SD 视频流畅、HD 边缘、4K 不行。OpenList 主用方向（Mac → OpenList）正好命中这一档。

## 七、EasyTier 下双向不对称的常见原因

观察过的现象：同一对节点 A↔B，跑 dd 测得 A→B 8 MB/s 而 B→A 仅 0.8 MB/s，相差 10x。

可能原因：
- **NAT 类型组合**：Symmetric × PortRestricted 之间打洞失败，走 relay；不同方向命中不同 relay 节点，relay 上下行带宽不一致
- **家宽上下行非对称**：典型 100/30 Mbps，发起 relay 的一端上行受限
- **MTU 不一致**：链路上某段 MTU 较小导致分片，慢方向的反向 ACK 延迟放大问题

排查思路：
1. `easytier-cli peer` 看每个 peer 的 `tunnel` 列是 `tcp/udp/p2p` 还是 `relay(N)`
2. 若是 relay，记录 N（relay 跳数），尝试调整 `[[peer]]` 让两端能直连
3. 关 `enable_quic_proxy`（双方都改）排除 QUIC 链路问题（详见 [easytier.md](easytier.md)）

## 八、Issues / 源码索引

| Issue / PR | 状态 | 关注点 |
|---|---|---|
| [rclone#8257](https://github.com/rclone/rclone/issues/8257) | OPEN | 中国区 Apple ID 端点支持（R1） |
| [PR rclone#8818](https://github.com/rclone/rclone/pull/8818) | OPEN (dirty) | 添加 `region` 配置项（R1 修复 PR） |
| [rclone#8587](https://github.com/rclone/rclone/issues/8587) | CLOSED ✅ | trust token 失效（R2 历史问题） |
| [PR rclone#9209](https://github.com/rclone/rclone/pull/9209) | MERGED ✅ | SRP 认证重写（v1.74.0） |
| [rclone#7982](https://github.com/rclone/rclone/issues/7982) | CLOSED ✅ | 文件创建后只读（v1.74.0 修复） |
| [rclone#8211](https://github.com/rclone/rclone/issues/8211) | CLOSED ✅ | mount iCloud 驱动 SIGSEGV |
| [rclone#8408](https://github.com/rclone/rclone/issues/8408) | — | WSL2 FUSE mount 通用问题（R6） |
| `rclone:backend/iclouddrive/iclouddrive.go` | — | iCloud 后端实现，无 ChangeNotify（R5） |
| `rclone:backend/iclouddrive/api/client.go` | — | 端点硬编码（R1） |
| `OpenListTeam/OpenList:drivers/local/util.go` | — | 缩略图懒加载逻辑（C1） |
| `OpenListTeam/OpenList:drivers/local/driver.go` | — | DirectorySize 全 stat 行为（C2） |
| [OpenList#1991](https://github.com/OpenList/OpenList/issues/1991) | OPEN | 搜索索引相关参考（C3） |
