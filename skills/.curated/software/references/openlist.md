# OpenList

[OpenList](https://github.com/OpenListTeam/OpenList) 是 AList 的活跃 fork，用 Go 编写的多云盘聚合面板：把 SMB / WebDAV / 各种云盘统一挂到一个 Web 界面下统一浏览、下载、预览。常作为家庭/团队的“网盘前台”。本文档关注 OpenList 本体：REST API 编程接入，以及任何 backend 都成立的通用行为坑。

> **范围**：本文讲 OpenList 本体——REST API 编程接入（让 agent / 脚本操作网盘，比操控网页可靠）+ 任何 backend 都成立的通用行为坑（C 系列）。**接入 iCloud Drive / Mac SMB 中转**（rclone 直连 vs Mac 中转选型、R/M 专属坑、部署步骤、远程访问测速）单独在 [openlist-icloud.md](openlist-icloud.md)。

## REST API 与 admin token（agent 编程接入）

OpenList 除网页前台外，还有一套完整 **REST API**（`/api/*`，JSON）和 **WebDAV**（`/dav/`）—— 两条独立的路、同一份文件。要让 agent / 脚本稳定操作网盘（ls / mv / cp / 上传 / 加减存储后端 / 看任务进度），走 REST API 远比操控网页可靠。官方文档站 <https://doc.oplist.org/>（API 章节路径随版本调整）；端点的权威来源是源码路由表 [`server/router.go`](https://github.com/OpenListTeam/OpenList/blob/main/server/router.go)。

### 鉴权：两种 token，agent 该用哪种

| | 登录 JWT | 固定 admin token |
|---|---|---|
| 来源 | `POST /api/auth/login` 登录换取 | 数据库 setting 里的固定值 |
| 有效期 | ~48h，且**改密码即失效**（JWT 带 `pwd_ts`，与用户密码时间戳比对） | **永不过期**（除非 reset） |
| 怎么拿 | 走完整登录流程（**2FA / 第三方 OAuth 都要过**） | CLI `openlist admin token` 一行，**绕过登录 / 2FA / OAuth** |
| 吊销 | 等过期 / 改密码 | `POST /api/admin/setting/reset_token` |
| 用法 | `Authorization: <token>` header（**无** `Bearer` 前缀） | 同样 `Authorization: <token>` |

源码依据：鉴权中间件 `Auth` 第一步就把请求头与固定 admin token 做常量时间比对，命中即挂 admin 身份、**不解析 JWT、不查过期 / 密码**（[`server/middlewares/auth.go`](https://github.com/OpenListTeam/OpenList/blob/main/server/middlewares/auth.go)）；CLI 取值见 [`cmd/admin.go`](https://github.com/OpenListTeam/OpenList/blob/main/cmd/admin.go) 的 `admin token` 子命令（直接打印 `setting.GetStr(conf.Token)`）。

→ **结论**：开了 2FA / 第三方 OAuth 时，登录 JWT 对 agent 极不友好（最多 48h 就要再过一遍人机验证，改密码还会立即失效）。**给 agent 用固定 admin token**：CLI 取一次、长期可用。代价是它是一把“永久全权限万能钥匙”（OpenList 没有限权限的 scoped API key），泄露后到 reset 前一直有效 —— 所以它的值要走 side-channel 注入，不落进对话 / 日志 / argv（见下）。

### CLI 取固定 admin token

```bash
<openlist-exe> --data <data-dir> admin token
# 输出: Admin token: <token>
```

`--data` 指向 OpenList 的数据目录（含 `data.db` + `config.json`）。该子命令只读 setting 表，与运行中的 server 并发安全（SQLite WAL 支持并发读，实测不干扰在跑的 server）。

⚠️ **桌面版（OpenList-Desktop）的 session / 盘符隔离坑**：用 OpenList-Desktop（Tauri 写的 GUI 启动器）在某个 Windows 交互桌面 session 拉起 server 时，进程信息里看到的工作目录（如 `D:\openlist`）往往是**那个登录 session 私有的盘符映射**（subst / `net use`），别的 session（WSL interop、服务账号、另一个登录用户）**根本够不到这个盘符**。真实数据目录在拉起它的那个用户的 AppData 下：

```
C:\Users\<user>\AppData\Roaming\OpenList Desktop\data\
```

定位思路：从进程拿真实 exe 路径与属主（PowerShell `Get-CimInstance Win32_Process` 的 `ExecutablePath` + `GetOwner` / `SessionId`），再去那个用户的 `AppData\Roaming\OpenList Desktop\` 找 `data\`。（具体 exe 路径 / data 目录 / 访问入口随部署而异，由各自的部署环境记录，不在本 reference 里固化。）

### 安全：固定 admin token 不要落进对话 / 日志

固定 admin token 是长期全权限凭据，取它时别让明文经过会留痕的地方（聊天上下文、工具输出、命令行 argv、shell history）。通用做法：在能跑 CLI 的机器上取到值后，直接交给一个 secret 管理器 / 密钥注入机制，调用方只按名字引用、拿不到明文，请求回显里把 token 串 redact 掉。两个有普适价值的实操提示：

- 经 SSH 在远端取值时，让 token 直接管道进密钥库，别先 `echo` 到终端再复制；
- 远端用 PowerShell 调 Windows 上的 `openlist.exe` 时，`-EncodedCommand`（参数是 base64 的 UTF-16LE）能规避多层引号转义。

### REST API 速用

- **base url**：`http://<host>:5244`（OpenList 默认端口 5244）。
- **鉴权**：除 guest 可匿名只读的端点外，带 `Authorization: <token>` header。
- **响应约定（关键）**：HTTP 状态码**恒为 200**，真正的业务码在 **body 的 `code` 字段**（200=成功，401=未登录，403=无权限 / 非 admin，500=后端错）。判断成败要看 `body.code`，不是 HTTP code —— 这点不知道会把“全是 200”误读成“全成功”。

核心端点（按权限分层；`fs` 写操作各有独立权限位，admin 端点需 admin token）：

| 操作 | 端点 | 备注 |
|---|---|---|
| ls | `POST /api/fs/list` `{path,page,per_page,refresh}` | 返回 `content[]`：name / size / is_dir / modified / sign… |
| stat + 直链 | `POST /api/fs/get` `{path}` | 返回 `raw_url`（`/p/...` 直链）、provider 等 |
| mkdir | `POST /api/fs/mkdir` `{path}` | |
| 上传 | `PUT /api/fs/put` + header `File-Path:` | 流式 body |
| rename | `POST /api/fs/rename` `{path,name}` | name 不含 `/` |
| mv | `POST /api/fs/move` `{src_dir,dst_dir,names[]}` | 跨存储 = **异步 task**；同存储 = 即时 rename |
| cp | `POST /api/fs/copy` `{src_dir,dst_dir,names[]}` | 返回创建的 task 列表 |
| rm | `POST /api/fs/remove` `{dir,names[]}` | |
| 列存储后端 | `GET /api/admin/storage/list` | |
| 加 / 删后端 | `POST /api/admin/storage/{create, delete?id=}` | create body 的 `addition` 是 driver 专属配置的**嵌套 JSON 字符串**（JSON 套 JSON） |
| 启 / 禁后端 | `POST /api/admin/storage/{enable, disable}?id=` | |
| **任务进度** | `GET /api/admin/task/{copy,move,upload,…}/{undone,done,info,cancel}` | 每条带 `state` + `progress(%)` + name |

> 🎯 **“大文件移动 / 复制看不到进度”** 的真相：跨存储 mv / cp 是**异步任务**，网页前台不显进度条，但 `/api/admin/task/{copy,move}/{undone,done}` 一直在记每个任务的 `state` 和 `progress` —— 轮询它就能自己做进度。同存储 move 是秒级 rename，本就不产生任务。

> WebDAV（`/dav/`）是与 REST API 平行的另一条路：标准协议、适合 rclone / 文件管理器直接挂载，但**只有文件操作**，加减存储后端、看任务进度这类管理能力只有 REST API 有。

## 坑分类速查表（OpenList 通用）

任何 backend 都要注意的共性坑（C 系列）。与 iCloud / Mac SMB 集成相关的 R（rclone 直连）/ M（Mac 中转）专属坑见 [openlist-icloud.md](openlist-icloud.md)。

| 编号 | 坑 / 注意点 | 速记 |
|---|---|---|
| C1 | 缩略图懒加载，但点开会读完整文件 | 不预扫，但点击触发整文件 |
| C2 | `DirectorySize` 开关会全目录 stat | 加存储时阻塞，默认关 |
| C3 | 搜索索引完全手动 | 不点“更新”就不会全扫 |

## 共性坑详解（任何 backend 都成立）

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

缓解：**默认关闭**；只在需要“前端显示目录总大小”时才开。

### C3 搜索索引完全手动

OpenList 的 Meilisearch / 本地索引**不会自动触发**，必须管理员后台主动点“更新索引”或调 `/api/admin/scan/start`。换言之：只要不点这个按钮，OpenList 不会“在你不注意时”全量遍历库。

参考：[OpenList/OpenList#1991](https://github.com/OpenList/OpenList/issues/1991)

## Issues / 源码索引（OpenList 通用）

| Issue / PR | 状态 | 关注点 |
|---|---|---|
| `OpenListTeam/OpenList:drivers/local/util.go` | — | 缩略图懒加载逻辑（C1） |
| `OpenListTeam/OpenList:drivers/local/driver.go` | — | DirectorySize 全 stat 行为（C2） |
| [OpenList#1991](https://github.com/OpenList/OpenList/issues/1991) | OPEN | 搜索索引相关参考（C3） |

> iCloud / rclone 相关的 Issue / 源码索引见 [openlist-icloud.md](openlist-icloud.md)。
