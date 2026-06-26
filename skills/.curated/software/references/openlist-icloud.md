# OpenList × iCloud Drive 集成

把 iCloud Drive 接入 [OpenList](https://github.com/OpenListTeam/OpenList) 网盘前台的两条路径——**rclone 直连 iCloud** vs **借道一台常开 Mac 用 SMB 中转**——的选型、专属坑、部署步骤与远程访问测速。

> 这是 [openlist.md](openlist.md) 的姊妹篇。OpenList 本体（REST API 编程接入、任何 backend 都成立的共性坑 C 系列）在 openlist.md；本文只讲 iCloud / Mac 集成这一特定场景。
>
> 沿用 openlist.md 的坑编号体系：**C 系列** = 任何 backend 的共性坑（在 openlist.md）；**R 系列** = rclone 直连 iCloud 专属；**M 系列** = Mac SMB 中转专属。章节号也承接（一为共性坑，故本文从二起）。
>
> 本文很多内容是 macOS 上的 **GUI / 桌面操作**——那是给人照着自己做的部署说明，不是给 agent 读了去执行的，所以写得具体。

## 坑分类速查表（iCloud / Mac 专属）

承接 openlist.md 的共性坑（C 系列），下面是 iCloud 集成的两类专属坑。详解见后面对应章节。

| 编号 | 坑 / 注意点 | 速记 |
|---|---|---|
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
| M2 | “Optimize Mac Storage” 取舍 | 开 = 占位符首读延迟；关 = 全文件常驻本地 |
| M3 | `~/Library/...` 不能直接共享 | Finder 拒 + `sharing -a` 也拒 symlink；用 `sharing -a` 直接传真实路径 |
| M4 | SMB 写入产生 `.DS_Store` | 关 `DSDontWriteNetworkStores` |
| M5 | 加完共享 ≠ 服务起来 | `sharing -a` 只注册 share point，不启动 smbd；要单独起服务（5.3） |
| M6 | `pgrep smbd` 看不到进程 ≠ 没起 | macOS smbd 是 launchd socket activation，看 `lsof :445` 是 launchd 才对 |
| M7 | iCloud 里 `Desktop` / `Documents` 通过 SMB 是 reparse point 不是目录 | macOS D&D Sync 的 firmlink；走真实路径 `~/Desktop` / `~/Documents` 单独 share 即可绕过 |
| M8 | macOS 用户首次 SMB 登录 `LOGON_FAILURE` 即使密码对 | 账号没 SMB-NT hash，需 GUI 勾“Windows 文件共享”或 `dscl . -passwd` 重设密码生成 |
| M9 | GUI 启用文件共享会自动追加默认 share point | 实测开总开关后 `sharing -l` 多出 `Macintosh HD` 和 `<user>` 两个 share；不需要的可在 GUI 删 |

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

**有 @icloud.com.cn 账号的，基本可以排除 rclone 直连这条路**（除非用已合并 / 自编译的 region patch）。

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

VFS 缓存的 fingerprint 依赖 size + mtime（`iclouddrive.go:840-843`）。mtime 不能写入意味着 rclone 在某些场景下**判断“文件是否变化”会不准**——可能短暂服务旧版本内容直到下次目录 poll。

### R4 iWork 文件 size 不一致

通过 iCloud Web 创建/修改的 Pages / Numbers / Keynote 文件，API 报告 size 与实际下载内容不一致：

```
failed with 1 errors and: corrupted on transfer: sizes differ
  src() 10679453 vs dst() 10501687
```

来源：[rclone#8257 评论](https://github.com/rclone/rclone/issues/8257#issuecomment-2661021687)。**不影响 mount**（VFS 实际下载内容确定大小，不依赖 API 报告），但 `rclone copy` / `rclone sync` 会失败。

### R5 没有 `ChangeNotify`，只能轮询

iCloud Drive 没有公开的 push notification 接口——Apple 自家 APNS 只对持有合法设备证书的 iPhone/Mac 推送，第三方拿不到。rclone iclouddrive backend **未实现** `ChangeNotify` 接口（源码确认），目录变化只能靠 `--poll-interval` 周期重新 list。

实际延迟天花板就是分钟级，不适合要求秒级变更可见的场景（OneDrive / Dropbox 有 webhook 推送，iCloud 这条只能轮询）。

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

走“Mac 跑 iCloud 官方客户端 + macOS SMB 共享 + OpenList 加 SMB 存储”路径时，以下事项需注意。

### M1 Mac 必须常启 + 网络稳定

Mac 是这个链路的中转节点：
- Mac 关机 / 重启 / 断网 → OpenList 该存储 503 / 超时
- 无技术解，链路结构要求 Mac 在线

### M2 “Optimize Mac Storage” 取舍

| 状态 | 行为 | OpenList 体验 |
|---|---|---|
| **开（默认）** | 老文件本地保留 placeholder（`*.icloud`），首次访问触发 `cloudd` 下载 | OpenList 通过 SMB 读 placeholder 时 macOS 会自动下载，**首次访问有延迟**；磁盘满时下载失败 → SMB 客户端见 I/O 错误 |
| **关** | 全部文件常驻本地 | OpenList 访问立即 SMB 速度 |

**关闭路径**：系统设置 → Apple ID → iCloud → iCloud Drive → 关 “Optimize Mac Storage”。

> 关闭后 macOS 会逐步把云端所有文件下载到本地。若 Mac 磁盘吃紧，必须先确认本地能装下整个 iCloud Drive，否则会触发“磁盘已满”告警并停止下载。

### M3 `~/Library/...` 不能直接通过 Finder 共享

两条路都有限制：

- **Finder GUI**：拒绝把 `~/Library/...` 路径加到“文件共享”列表（系统隐藏目录）
- **`sharing -a` CLI**：拒绝符号链接（报 `sharing: '<path>' is not a directory`），所以 `ln -s ~/Library/.../CloudDocs ~/iCloud-Share` 后再 `sharing -a ~/iCloud-Share` **不行**

实测可行方案：**`sharing -a` 直接传真实路径 + `-n` 给 share point 一个英文名**，绕过 GUI 限制（CLI 不管 `~/Library` 隐藏属性）也避开 symlink 限制：

```bash
sudo sharing -a "$HOME/Library/Mobile Documents/com~apple~CloudDocs" \
     -n iCloud -S iCloud -s 001 -g 000
sharing -l    # 验证
```

参数详解见 5.3 节。

### M4 SMB 写入产生 `.DS_Store` 噪音

macOS 任何挂的网络共享上都会自动写 `.DS_Store`。如果不希望此行为：

```bash
defaults write com.apple.desktopservices DSDontWriteNetworkStores -bool TRUE
# 注销后生效
```

详见 [macos.md](macos.md) 的对应小节。

### M5 加完共享 ≠ 服务起来

`sharing -a` 只往配置里注册 share point，**不会顺带启动 smbd**。需要单独起服务（5.3.B 的「启动 smbd 服务」）。GUI 路径下打开 File Sharing 总开关时一次做完；CLI 必须分别处理。

### M6 `pgrep smbd` 看不到进程 ≠ 服务没起

macOS smbd 是 launchd 的 **socket activation** 模式：launchd (PID 1) 持有 445 socket，第一个连接到来才 fork smbd 处理。所以验证服务是否就绪应该看 `lsof :445` 是不是 `launchd` 在监听；`pgrep smbd` 在没有活跃 SMB 连接时本来就为空。详见 5.3.B 的「验证」小节。

### M7 iCloud 里 `Desktop` / `Documents` 通过 SMB 是 reparse point

启用了 macOS “Desktop & Documents Folders” 同步到 iCloud 后，iCloud Drive 顶层的 `Desktop` 和 `Documents` 不是普通目录，而是 macOS 系统级 firmlink 重定向。共享 iCloud Drive 顶层后通过 SMB 看：

```
Desktop                           AHr        0  ...   ← r = ReparsePoint，无 D
Documents                         AHr        0  ...   ← 同上
WPS Office                        D          0  ...   ← 普通目录
```

**症状**：
- smbclient `cd Desktop` / `cd Documents` 直接报 `NT_STATUS_INVALID_NETWORK_RESPONSE`
- OpenList 前端把它们当文件渲染（属性里没 D 位）；点开是“下载文件”按钮，但点了下不动

**这不是 OpenList 的 bug**，是 macOS SMB 服务端实现限制 + reparse point 协议本身需要客户端解析。

**关键事实：D&D Sync 启用后 firmlink 是反向的**——真实数据在 `~/Desktop` / `~/Documents`，iCloud Drive 里那俩是带 hidden 标记的 symlink 指向家目录。验证：

```bash
stat -f '%N -> %Y inode=%i flags=%Sf' ~/Desktop \
     "$HOME/Library/Mobile Documents/com~apple~CloudDocs/Desktop"
# /Users/<user>/Desktop ->  inode=268766 flags=-                          ← 普通目录
# /Users/<user>/Library/.../CloudDocs/Desktop -> /Users/<user>/Desktop  flags=hidden  ← symlink
```

**绕过方案：单独 sharing 真实路径**：

```bash
sudo sharing -a "$HOME/Desktop"   -n Desktop   -S Desktop   -s 001 -g 000
sudo sharing -a "$HOME/Documents" -n Documents -S Documents -s 001 -g 000
sharing -l    # 验证多了两条 share point
```

实测在 OpenList 加两个独立 SMB 存储指向 `Desktop` / `Documents` share 后能正常列目录与下载。D&D Sync 不受影响（真实数据仍在 `~/Desktop`，本来就是同步源）。

OpenList 视觉上还原“完整 iCloud 目录”的具体配法见 5.4.1。

**备选方案**（改 macOS 行为或不解决）：

| 方案 | 做法 | 影响 |
|---|---|---|
| 不解决 | 接受这两条目无法访问 | OpenList 上看到两个“假文件”；其他目录正常 |
| 关 D&D Sync | 系统设置 → Apple ID → iCloud → 关 “Desktop & Documents Folders” | 桌面/文档不再上云；改变 macOS 默认行为 |

### M8 macOS 用户首次 SMB 登录必报 `LOGON_FAILURE`，即使密码对

新建的 macOS 账号默认 `AuthenticationAuthority` 的 `;ShadowHash;HASHLIST:<...>` 子字段里**没有 `SMB-NT` 项**（只有 `SALTED-SHA512-PBKDF2`、`SRP-RFC5054-4096-SHA512-PBKDF2`，外加 `Kerberosv5` 段）。SMB 协议层用 NTLMv2 验证时找不到 NT hash，必报：

```
session setup failed: NT_STATUS_LOGON_FAILURE
```

smbd log 同时报：

```
gss_accept_sec_context: minor_status: 0xa2e9a74a
smb2_dispatch_session_setup: status: 0xc000006d
```

**两条修复路**：

1. **GUI**：系统设置 → 通用 → 共享 → 文件共享 → ⓘ → 在 “Windows 文件共享” 列表里勾上账号 + 输密码。macOS 借此把 NT hash 派生进 ShadowHashData。验证：

   ```bash
   dscl . read /Users/<user> AuthenticationAuthority | grep SMB-NT
   ```

   有匹配即生效。实测前后 HASHLIST 变化：

   ```
   勾选前: HASHLIST:<SALTED-SHA512-PBKDF2,SRP-RFC5054-4096-SHA512-PBKDF2>
   勾选后: HASHLIST:<SALTED-SHA512-PBKDF2,SRP-RFC5054-4096-SHA512-PBKDF2,SMB-NT>
   ```

2. **CLI（无 GUI 时）**：重设一次密码，`dscl` 会重新生成所有 hash 派生（含 NT hash）：

   ```bash
   sudo dscl . -passwd /Users/<user>
   # 提示输新密码两次（输跟原来一样的，密码不变但 hash 重生）
   ```

GUI 操作那一勾的实测副作用：
- **会重置 launchd smbd 状态**——勾完测出 `CONNECTION_REFUSED`，按 5.3.B 的「启动 smbd 服务」重跑 enable + bootstrap
- **可能切换“远程登录” (SSH) 开关**——同一面板内开关相邻，确认远程登录仍然开着

**原理：为什么 macOS 用户需要单独勾 Windows File Sharing**

不是 macOS 的怪癖，而是 NTLM 协议算法 × macOS 默认密码存储策略的结构性冲突。

- **NTLM 服务端验证需要 NT hash**——NT hash = `MD4(UTF-16-LE(plaintext))`，无 salt（[MS-NLMP §3.3.1 NTOWFv1](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-nlmp/464551a8-9fc4-428e-b3d3-bc5bfb2e73a5)，[Windows passwords overview](https://learn.microsoft.com/en-us/windows-server/security/kerberos/passwords-technical-overview)）
- **macOS 默认存的是不可逆强 KDF hash**——`SALTED-SHA512-PBKDF2` 是单向且加 salt 的，给定 hash 无法反推 plaintext，自然**事后也无法派生出 NT hash**（[`pwpolicy(8)` man](https://keith.github.io/xcode-man-pages/pwpolicy.8.html) 列出可用 hash 类型，`SMB-NT` 一行注明 “Required for compatibility with Windows NT/XP file sharing”）
- **解决方案是显式补一份“弱 hash”**——只在用户在 Windows File Sharing 列表里**勾选并重新输入密码**那一刻，macOS 借机捕获 plaintext，计算 NT hash 写入 ShadowHashData，并在 `AuthenticationAuthority` 的 HASHLIST 里追加 `SMB-NT` 项（[Apple Support: Share Mac files with Windows users](https://support.apple.com/en-gb/guide/mac-help/mchlp1657/mac) 写明 “stored in a less secure manner”，每用户单独启用）
- **每用户独立**——每个账号 plaintext 不同，必须分别勾选输密码各算一次 NT hash

Apple 的设计取舍：默认不存弱 hash，由用户显式同意才补。等价的旧说法见 Apple Training 资料（[“password is stored in a nonrecoverable form ... give the operating system the user's password to generate the new hash ... enabled only on a per-user basis”](https://flylib.com/books/en/4.395.1.130/1/)）。

绑定 Open Directory / Active Directory 的企业场景下走 Kerberos / NTLMv2 服务，**不依赖**本地 SMB-NT hash（[Apple 企业 SMB 文档](https://support.apple.com/en-au/101659)）；这种场景与本文 OpenList + 单机 macOS 共享无关。

### M9 GUI 启用文件共享会自动追加默认 share point

实测在 macOS 26.2 上从 GUI 打开文件共享总开关后，`sharing -l` 在原有自定 share point 之外多出：

```
name:   Macintosh HD     path: /
name:   <username>       path: /Users/<username>
```

含义：根盘 + 用户家目录被自动暴露为 SMB share，任何能成功登录的用户都可枚举到（实测 `smbclient -L` 能看到）。如果只想暴露指定 share point：

```bash
sudo sharing -r "Macintosh HD"
sudo sharing -r "<username>"
```

或在 GUI“共享文件夹”列表里删除对应条目。

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

**结论**：R1（中国区 Apple ID）+ R5（轮询延迟）+ R2（30 天 token）三个限制叠加时，rclone 直连不可用或代价显著；这种场景下若环境内有常启 macOS 设备，Mac 中转是唯一可行链路。其他场景两条路都成立，按 M1 / R 系列权衡。

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

参考 M2。如果 OpenList 用户访问延迟敏感（流媒体场景），通常需要关闭让全文件常驻本地。

### 5.3 开启 macOS SMB 共享

> **本节的 “CLI” 指 macOS 上的命令行**（`sharing` / `launchctl`），用于在 mac 这一侧把目录暴露为 SMB share。**OpenList 本身没有存储管理 CLI**：加 / 改 / 删 SMB 存储必须走 OpenList Web 后台（5.4），CLI 只覆盖进程级运维（启动、设管理员密码等）。

两件**正交**的事：(1) 注册 share point（哪个目录、共享名、谁能访问）；(2) 启动 smbd 服务。GUI 文件共享开关一次做完两件事；CLI 必须分别处理。

#### 5.3.A GUI 路径（能进 Mac 桌面时）

**系统设置 → 通用 → 共享 → 文件共享**：
1. 打开 File Sharing 总开关
2. 点 Options → 勾 “Share files and folders using SMB”，按 Windows File Sharing 给当前账号打 ✓ 并填密码
3. Shared Folders 列表 → `+` 添加目标目录
4. 用户权限：仅当前 macOS 用户读写

**注意**：GUI 不允许添加 `~/Library/...`（隐藏目录），iCloud Drive 这种只能走 5.3.B 的 CLI 路径加。

CLI 验证：

```bash
sharing -l                                    # share points
sudo lsof -nP -iTCP:445 -sTCP:LISTEN          # 应见 launchd / smbd 监听 445
```

#### 5.3.B CLI 路径（无 GUI 时，如纯 SSH 维护）

Apple 没有官方 CLI wrapper，需要分两步。**测试环境：macOS 26.2 (Tahoe)，2025-Q4 实测可行。**

##### 1. 注册 share point

```bash
sudo sharing -a "<绝对路径>" -n <Name> -S <SmbName> -s 001 -g 000
sharing -l    # 验证
```

`sharing` 命令参数：

| 参数 | 含义 |
|---|---|
| `-a <path>` | 添加 share point；**必须真实目录，不接受 symlink** |
| `-n <name>` | share point 在系统里的全局名（不指定就用目录 basename，含特殊字符的目录会得到丑陋的名字，如 `com~apple~CloudDocs`） |
| `-S <smb>` | SMB 客户端看到 / 挂载用的名字（`\\host\<smb>` 里那个名） |
| `-s <mask>` | 协议位掩码 `AFP/SMB/FTP`：`001`=只 SMB；`011`=SMB+FTP；`111`=全开 |
| `-g <mask>` | 上述协议是否允许 guest 匿名：`000`=全禁；`001`=仅 SMB 允许 guest |

##### 2. 启动 smbd 服务

`sharing -a` 只往配置里注册了 share point，**不会顺带起 smbd**。需要单独跑：

```bash
sudo launchctl enable system/com.apple.smbd
sudo launchctl bootstrap system /System/Library/LaunchDaemons/com.apple.smbd.plist
```

可能的错误及对应做法：

| 报错 | 含义 | 处理 |
|---|---|---|
| `service already bootstrapped` | 服务已 bootstrap，需要重启 | 改用 `sudo launchctl kickstart -k system/com.apple.smbd` |
| `Operation not permitted` | 系统设置里 File Sharing 总开关被关了 | 只能去 GUI / VNC / Screen Sharing 打开，CLI 绕不过 |

##### 3. 验证（关键，跟 Linux 习惯不同）

```bash
sudo lsof -nP -iTCP:445 -sTCP:LISTEN
```

预期看到 `launchd` (PID 1) 在监听 445，**而不是** smbd。这是 launchd 的 **socket activation** 模式：launchd 持有 socket，第一个连接到来时才 fork smbd 进程处理。所以：

- ✅ `lsof :445` 见到 `launchd` = 服务已就绪
- ❌ 用 `pgrep smbd` 是空 ≠ 服务没起（**没有 SMB 连接时本来就不会有 smbd 进程**）

跨机连通性测试有两层：

**层 1：协议握手（不需要密码）**

```bash
# 从客户端跑：
smbclient -L //<mac-ip> -N -t 5
```

返回 `NT_STATUS_LOGON_FAILURE` 而不是 `CONNECTION_REFUSED` / `timeout`，说明：TCP 通 + SMB negotiate 通 + 只是匿名被拒（如果 sharing 时 `-g 000` 禁了 guest，这是预期行为）。三种结果对应不同根因：

| 结果 | 含义 |
|---|---|
| `NT_STATUS_LOGON_FAILURE` | TCP + SMB negotiate 通，匿名被拒（或缺 NT hash，见 M8） |
| `NT_STATUS_CONNECTION_REFUSED` | TCP 端口没监听（smbd 服务没起） |
| `timeout` / 长时间挂起 | 网络层不通 / 防火墙 silent drop |

**层 2：用真实凭据列共享**

```bash
smbclient -L //<mac-ip> -A <creds-file>
smbclient //<mac-ip>/<ShareName> -A <creds-file> -c 'allinfo "<path>"; cd "<path>"; ls'
```

`-A <file>` 是 smbclient 标准凭据文件参数，文件格式 `username=` / `password=` / `domain=` 三行，权限必须 `0600`，否则 smbclient 会拒绝读。

#### 5.3.C 为什么不用 macOS 上常见的旧命令

```bash
sudo launchctl load -w /System/Library/LaunchDaemons/com.apple.smbd.plist     # 旧
```

新版 macOS（13+）SIP 保护下 `load -w` 经常报 `Operation now in progress` / `Operation not permitted`。`enable` + `bootstrap` 的组合是 Apple 在 launchctl v2 推荐的接口。

#### 5.3.D Share point 持久化位置

旧资料常说 share point 存在 `/var/db/dslocal/nodes/Default/sharepoints/<Name>.plist`，新版 macOS（实测 26.2）该目录已不存在，**不要直接读/改 plist**，统一用 CLI 查询与管理：

```bash
sharing -l                # 列所有 share point
sudo sharing -a <path> -n <Name> -S <Smb> -s <mask> -g <mask>   # 添加
sudo sharing -r <Name>    # 删除（按 -n 给的 share point name）
sudo sharing -e <Name> -s <mask>   # 编辑协议位掩码
```

### 5.4 OpenList 加 SMB 存储

OpenList 后台 → 存储 → 添加 → 类型选 **SMB**，关键参数：

| 参数 | 值 | 说明 |
|---|---|---|
| 挂载路径 | `/icloud`（任意） | OpenList 前端展示路径 |
| Address | `<Mac 在组网内的 IP>:445` | EasyTier / Tailscale / 局域网都行 |
| Username / Password | macOS 用户名 + 登录密码 | macOS 用户必须能 SMB 登录（M8） |
| Share Name | 与 `sharing -a -S <smb>` 一致（如 `iCloud`） | 用纯英文 / 短名，避免特殊字符 |
| **DirectorySize** | **关闭 ⚠️** | 见 C2 |
| Thumbnail | 看需求 | 开 → 用户点图会触发 SMB 拉全文件（见 C1） |
| Web Proxy | 开 | 通过 OpenList 转发，避免暴露 SMB 端口给浏览器 |

### 5.4.1 嵌套挂载 + Hide patterns 还原“完整 iCloud 视图”

M7 的反向 share 方案下，原始 iCloud share（顶层）和单独的 Desktop / Documents share 是 3 个独立 SMB share。在 OpenList 里把它们组合成跟 macOS Finder 一致的视图：

1. **加 3 个 SMB 存储**，挂载路径分别：
   - `/icloud` → SMB share `iCloud`
   - `/icloud/Desktop` → SMB share `Desktop`
   - `/icloud/Documents` → SMB share `Documents`

2. **`/icloud` 存储编辑 → 隐藏 / Hide 字段** 填两行（隐藏底层 SMB iCloud share 里那两个 reparse point 假文件，避免与子挂载同名重复显示）：

   ```
   Desktop
   Documents
   ```

   字段语法因 OpenList 版本而异：换行 / 逗号分隔 glob，或正则 `^(Desktop|Documents)$`。UI 上方有提示。

3. 用户访问 `/icloud` 时 OpenList 列出：
   - 底层 SMB iCloud share 的真实条目（`Desktop` / `Documents` 已被 Hide 隐藏）
   - 注入两个子挂载点 `Desktop` / `Documents`（点进去走 `/icloud/Desktop` 与 `/icloud/Documents`，对应 `~/Desktop` / `~/Documents` 真实数据）

大小写敏感：OpenList 子挂载路径与 SMB share name 都用 `Desktop` / `Documents`（首字母大写），与 macOS 显示一致。

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

对照上表，下行 8 MB/s 落在 “2-10 MB/s” 行——文档/图片秒开、SD 视频流畅、HD 边缘、4K 不行。OpenList 主用方向（Mac → OpenList）正好命中这一档。

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

## 八、Issues / 源码索引（iCloud / rclone）

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

> OpenList 本体的源码索引（C 系列）见 [openlist.md](openlist.md)。
