# 挂载与文件共享

## WSL 中 UNC/SMB 共享性能差

现象：WSL 中把 Windows/UNC 共享挂到 `/mnt/...` 后，读写大文件尚可，但创建、遍历、删除海量小文件极慢，`rm -rf`、`du`、`find` 长时间无输出。

先确认挂载类型：

```bash
findmnt -T <mount-point> -o TARGET,SOURCE,FSTYPE,OPTIONS
df -Th <mount-point>
stat -f -c 'type=%T block_size=%s' <mount-point>
```

如果看到 `FSTYPE=9p`、`aname=drvfs;path=UNC\...` 或 `path=T:`，这是 WSL 的 `drvfs/9p` 路径。它对小文件元数据操作通常很慢。把 `\\server\share` 先映射成 Windows 盘符再挂为 `T:` 可能略有改善，但底层仍是 `9p`，不会有质变。

更好的方案是在 WSL 内直接用 Linux CIFS 挂 SMB：

```bash
sudo apt-get update
sudo apt-get install -y cifs-utils smbclient
sudo mkdir -p /etc/samba/credentials
sudo chmod 700 /etc/samba/credentials
```

凭据文件示例，注意不要把真实密码写进聊天、日志或 repo：

```ini
username=<smb-user>
password=...
domain=<domain>
```

权限：

```bash
sudo chmod 600 /etc/samba/credentials/<remote>
```

先用 `smbclient` 验证认证和 share 名：

```bash
sudo smbclient -L //<smb-host> -A /etc/samba/credentials/<remote> -m SMB3
```

能列出目标 share 后，再用 `mount.cifs`，不要只依赖裸 `mount -t cifs`：

```bash
sudo mkdir -p <mount-point>
sudo mount.cifs //<smb-host>/<share> <mount-point> \
  -o credentials=/etc/samba/credentials/<remote>,uid=<UID>,gid=<GID>,iocharset=utf8,vers=3.1.1,noperm,sec=ntlmssp,domain=<domain>
```

持久化 `/etc/fstab` 示例（将 `<UID>`、`<GID>` 替换为实际用户 ID，可通过 `id -u`、`id -g` 查看）：

```fstab
//<smb-host>/<share> <mount-point> cifs credentials=/etc/samba/credentials/<remote>,uid=<UID>,gid=<GID>,iocharset=utf8,vers=3.1.1,noperm,sec=ntlmssp,domain=<domain>,noauto,x-systemd.automount 0 0
```

`noauto,x-systemd.automount` 可以避免开机时网络或凭据暂不可用导致启动卡住；访问 `<mount-point>` 时再自动挂载。

## 排障经验

- `No route to host` 或 `Unable to determine destination address`：WSL/Linux 侧解析不到 Windows 可访问的 NetBIOS/局域网名字。用 Windows 侧 `ping -4 server` 或 `Resolve-DnsName server` 拿 IP，然后在 Linux CIFS 中使用 IP。
- `Host is down`：IP 或路由不是 SMB 服务实际可用路径，或 445 端口不可达。可用 `timeout 3 bash -lc '</dev/tcp/IP/445'` 粗测端口。
- `SessSetup = -13`：SMB 认证阶段被拒。检查用户名、密码、`domain=`、`sec=`、SMB 版本；也可以用 `smbclient -L` 验证凭据。
- `smbclient` 能列出 share，但 `mount -t cifs` 失败：安装 `cifs-utils` 后使用 `mount.cifs` 再试；`mount.cifs` 会走更完整的 helper 逻辑。
- Windows 已经能访问 `\\server\share` 不等于 Linux CIFS 一定能复用 Windows 会话；Linux CIFS 需要自己的凭据文件。
- 切换正式挂载前先查占用者：`sudo fuser -vm <mount-point>`。如有残留 `rm`、`cp`、`du`、`find`，先停掉再 `umount`。

## 性能验证

小文件基准可以用固定数量文件做相对比较：

```bash
base=<mount-point>/<sub-path>
d="$base/.mount-bench-$$"
mkdir -p "$d"
start=$(date +%s%N)
i=1; while [ $i -le 200 ]; do touch "$d/f$i"; i=$((i+1)); done
mid=$(date +%s%N)
rm -rf "$d"
end=$(date +%s%N)
echo "create_ms=$(( (mid-start)/1000000 )) delete_ms=$(( (end-mid)/1000000 ))"
```

一次实际案例：同一 SMB share 在 WSL `drvfs/9p` 下创建 200 个空文件约 1912ms、删除约 624ms；改成 CIFS 后创建约 613ms、删除约 364ms。

## 无 sudo / 容器场景：rclone SMB FUSE + systemd user service

适用：本机没有 root 权限、装不了 `cifs-utils`、`mount.cifs` 用不了，但 `/dev/fuse` 可读写、有 pixi/conda-forge 可用、systemd user 已启用。典型环境是 WSL2 普通用户、受限开发容器。

为什么是 rclone：调研过其它 userspace FUSE SMB 方案——smbnetfs 已死 (2018 起未维护，且没有 conda-forge 包)、gvfs 在 headless WSL 无 D-Bus session 跑不起来、sshfs 经过跳板机会多一跳 RTT 损耗。**rclone smb 后端（CloudSoda/go-smb2）是 2024-2025 唯一活跃的、可纯 userspace 安装的、支持 SMB 3.1.1 + NTLMSSP domain auth 的 FUSE 方案。**

### 安装 + 配置

rclone 是单文件 Go 二进制，pixi 装最干净：

```bash
pixi global install rclone   # → ~/.pixi/bin/rclone（实际位置在 ~/.pixi/envs/rclone/bin/）
```

> 不用 pixi 时（如 `apt install rclone` 在 `/usr/bin/rclone`、官方一键脚本在 `/usr/local/bin/rclone`），需要把后文 systemd 模板里所有 `%h/.pixi/bin/rclone` 改成实际绝对路径。**`ExecStart=` 第一项不展开 `$VAR`**（见后文坑），所以不能用 `Environment=` 注入，只能写绝对路径或 `%h` 这种 specifier。

remote 配置文件 `~/.config/rclone/rclone.conf`：按 [rclone smb 后端文档](https://rclone.org/smb/) 配，最少需要 `host` / `user` / `domain` / `pass` 四项。下文统一把这个 remote 叫 `<remote>`，实际命名自取。**`pass` 不要手写明文**，用下面的密码填法之一。

密码填法（rclone ≥1.39 `config password/update` 都是非交互的 key/value 模式，没有内置交互提示，**容易踩坑**）；菜单式 `rclone config` 走官方文档，下面只列两种 stdin 套路：

```bash
# A. 一行 stdin（最快但密码会短暂出现在 argv 里）：
read -rs PW && rclone config password <remote> pass "$PW" && unset PW

# B. 严格 stdin，密码永不进 argv：
stty -echo; read -r PW; stty echo; echo
obs="$(printf '%s' "$PW" | rclone obscure -)"
unset PW
rclone config update <remote> pass "$obs" --no-obscure
unset obs
```

### 连通性预探（不依赖 smbclient）

环境没 smbclient 也能验证 SMB 层是否打通——用 rclone 故意配错密码，看错误类型：

```bash
# 注意 env 变量名规则：RCLONE_CONFIG_<REMOTE-大写>_PASS，下面以 remote 名 "team" 为例
RCLONE_CONFIG_TEAM_PASS="$(rclone obscure 'wrong-probe')" \
  rclone lsd team: --timeout=8s --contimeout=5s --low-level-retries=1 --retries=1
```

- 报 `The attempted logon is invalid`（`STATUS_LOGON_FAILURE`） → ✅ TCP+SMB negotiate+NTLMSSP 全通，只差密码
- 报 `STATUS_NO_SUCH_DOMAIN` / `NO_LOGON_SERVERS` → ❌ `domain=` 不对
- 报 `connection refused` / `i/o timeout` / `no route to host` → ❌ 网络层就断了

### systemd user service（基于 rclone wiki 模板）

来源：<https://github.com/rclone/rclone/wiki/Systemd-rclone-mount>（ncw 维护，社区共识模板）。原模板有一堆 `--cache-*` / `--max-read-ahead` / `--drive-use-trash` / `--bwlimit` 老旗子是旧 cache backend 时代的产物（pre-VFS，~v1.50 前），rclone ≥1.52 已弃用，必须删掉。落 `~/.config/systemd/user/rclone@.service`：

```ini
[Unit]
Description=rclone mount of remote %i
Documentation=https://rclone.org/commands/rclone_mount/

[Service]
Type=notify

Environment=REMOTE_NAME=%i
Environment=REMOTE_PATH=/
Environment=MOUNT_DIR=%h/%i
Environment=RCLONE_CONF=%h/.config/rclone/rclone.conf

EnvironmentFile=-%h/.config/rclone/%i.env

ExecStartPre=/usr/bin/test -x %h/.pixi/bin/rclone
ExecStartPre=/usr/bin/test -d ${MOUNT_DIR}
ExecStartPre=/usr/bin/test -w ${MOUNT_DIR}
ExecStartPre=/usr/bin/test -r ${RCLONE_CONF}

ExecStart=%h/.pixi/bin/rclone mount \
    --config=${RCLONE_CONF} \
    ${REMOTE_NAME}:${REMOTE_PATH} ${MOUNT_DIR}

ExecStop=/usr/bin/fusermount3 -uz ${MOUNT_DIR}

Restart=always
RestartSec=10

[Install]
WantedBy=default.target
```

每个 remote/挂载点的差异化用 `~/.config/rclone/<remote>.env` 覆盖：

```ini
# ~/.config/rclone/<remote>.env
REMOTE_PATH=/<share>/<sub-path>      # rclone.conf 里 [<remote>] 上层 share 内的子路径
MOUNT_DIR=<absolute-local-mount>     # 例如 /mnt/<remote> 或 $HOME/mounts/<remote>
```

之后：

```bash
mkdir -p <absolute-local-mount>
systemctl --user daemon-reload
systemctl --user enable --now rclone@<remote>
systemctl --user status rclone@<remote>
findmnt <absolute-local-mount>
# 改 env 后只需 systemctl --user restart rclone@<remote>
```

### 关键坑

- **`ExecStart=` 的第一项（可执行文件路径）systemd 不展开 `$VAR`，只展开 `%` specifier。** 写 `ExecStart=${RCLONE_BIN} ...` 会直接 `status=203/EXEC: Failed to locate executable ${RCLONE_BIN}: No such file or directory`，即使 ExecStartPre 用同一个变量 `test -x` 是过的。`Environment=` 定义的 var 只在后续 args 里能展开。修法：用 `%h/.pixi/bin/rclone` 这种 specifier，或者写绝对路径。
- **Ubuntu 22.04 / 24.04 默认是 fuse3**，要用 `fusermount3 -uz` 而不是 `fusermount -u`，否则 ExecStop 找不到。
- **wiki 模板的 `After=network-online.target` 在 user unit 里无效**——user 单元不能依赖 system target。WSL2 网络一直在，删掉无影响。
- **`loginctl enable-linger <user>` 需要 sudo**，没 sudo 就只能在用户 session 活着时跑（WSL 关掉，service 也停；重开 WSL 进 session 后 service 跟 `default.target` 自动起）。

### 性能预期（重要）

直连 SMB、RTT ~1ms 的典型表现（不要拿去比内核 CIFS，rclone 没 SMB compound，每个目录列举都是一次独立 RTT）：

| 操作 | 实测耗时 | 备注 |
|---|---|---|
| 单层 `ls` (110-377 子目录, cold) | 6.5-12s | 与目录条目数线性相关 |
| 同一目录 5 分钟内重 `ls` (warm) | <10ms | `--dir-cache-time` 默认 5min 命中 |
| 单 `ls -la <file>` (cold stat) | 4-5s | 单 stat 偏慢 |
| `cat` 222 MB 顺序读 | 8s ≈ 28 MB/s | 千兆内网约 1/4 |
| 深层 `find . -type f`（7 万文件树） | **>10 分钟未完成，必须放弃** | rclone SMB 后端无 SMB compound |

**核心结论：rclone SMB FUSE 适合"浅层 ls + 顺序读单大文件 + 简单写"，不适合 `find` / `du -sh` / `rg --no-ignore` / `git status` / 在挂载点上跑 IDE 索引等深层 metadata 操作。** 这类操作要么在挂载点外做（本地 cache 一份），要么换内核 `mount.cifs`（要 root）。

### VFS cache 模式与磁盘占用

默认 `--vfs-cache-mode off`：**本地磁盘占用 ≈ 0**，所有读/写都流式过 SMB。少数场景会因此失败：

- 以 `O_RDWR` 打开已存在文件并随机写中间一段（vim 直接编辑挂载点里的文件、SQLite 数据库、git rebase、`fallocate`）
- `O_APPEND` 追加大文件
- 报错形如 `Input/output error` / `Function not implemented` 时考虑切到 `writes`

切 `writes`/`full` 时在 env 文件加：

```ini
RCLONE_VFS_CACHE_MODE=writes
RCLONE_VFS_CACHE_MAX_SIZE=2G   # 上限可控
RCLONE_VFS_CACHE_MAX_AGE=1h
```

并在 service 的 `ExecStart` 里把对应 `--vfs-cache-mode` / `--vfs-cache-max-size` / `--vfs-cache-max-age` / `--cache-dir=%h/.cache/rclone/%i` 也加上。缓存落在 `~/.cache/rclone/<remote>/`，不会无界长大。

### 备选：SSHFS 跳板

如果直连 SMB 不通但有 SSH 到一台已经内核 `mount.cifs` 挂上同一 share 的机器，可以 `sshfs <hop>:<remote-mount> <local-mount>` 间接挂上。代价是每个 FUSE 操作多一跳 SSH RTT，对 metadata 密集操作更慢；优势是热路径文件会命中跳板机的内核 dentry/page cache，**读密集且热数据场景反而可能比 rclone 直连快**。sshfs 在 conda-forge 上只有 Python fsspec 版本（非 FUSE 二进制），原生 FUSE 二进制要自己 `apt download sshfs && dpkg -x` 解包到 `~/.local/bin`。

### SMB server 地址漂移：用 hostname 不用 IP literal

**`rclone.conf` 的 `host =` 字段写 NetBIOS/DNS hostname，不要写 IP literal。** 现场 SMB server 经常被运维迁机器、换网段、改 DHCP 池——一旦 IP 漂移，写 IP literal 的 rclone 直接连不上，service 进入"`Type=notify` 90s 超时 → `Restart=always` 每 ~100s 重试"的循环（看 `systemctl --user status` 里 restart counter 一路涨就是它）。同 share 上跑内核 `mount.cifs` 的机器（如 1810）通常是写 `//Quantum/Team`，因为 hostname 路径只需要本机 `/etc/hosts` 改一行就跟得上。

**hostname 解析的权威来源是"已经 work 的那台机器"。** 多机部署同一 share 时，新机器直接抄那台 work 机的 `/etc/hosts` 里关于这个 SMB host 的映射（例：`10.100.158.91  Quantum`），别去自己探/猜/写错的别名。本机能 ping 通 hostname + 445 端口 reachable 后，`rclone.conf` 的 `host =` 改成 hostname，重启 service 即可。

```bash
# 1. 抄已 work 机的 hosts 条目（在该机上 grep）
ssh <work-host> "getent hosts <smb-server-hostname>"
# 2. 本机加 sudo（需要 root）
echo "<ip>  <hostname>" | sudo tee -a /etc/hosts
# 3. 把 rclone.conf 的 host = <ip> 改成 host = <hostname>
# 4. systemctl --user restart rclone@<remote>
```

### `find` / `grep -r` / `git status` 进 rclone 挂载点会卡死

> 本工作区实例：`QuantumAtlas/raw/` 就是 rclone SMB FUSE 挂载（→ `team:Team/QuantumAtlas/raw`），下文 `*/raw` / `!**/raw/**` / `--exclude=raw` 模板都以它为例。

承接上面性能表里 "深层 `find` >10 分钟未完成"——任何在仓库根/家目录跑全量 walk 的工具（`find`、`fd`、`rg --no-ignore`、`git status` 当 mount 在仓库子目录内、IDE 索引、`du -sh`、备份工具、**`go vet ./...` / `go list ./...` / `go build ./...` 等 Go 工具链的 `./...` glob**——Go 不识别 fstype，又默认递归所有子目录 stat `.go`）都会一头扎进挂载点，因为 rclone SMB 后端无 SMB compound、metadata 走每目录一次 RTT，几万条目就是几十分钟级别，并且其它工具会同时被这条 stuck 进程拖住（FUSE 串行 + dir-cache miss 雪崩）。

对策：**在 walk 命令上明确 `-prune` 排除挂载点 / FUSE 路径**：

```bash
# find 模板
find ~ \
    \( -path '*/raw' -o -path '*/.cache/rclone/*' -o -path '*/node_modules' -o -fstype fuse \) -prune \
    -o -name '<pat>' -print

# rg 模板（rg 不识别 fstype，靠 ignore-file 或 --glob '!path')
rg --glob '!**/raw/**' --glob '!**/.cache/rclone/**' '<pat>'

# du 模板（du 不识别 fstype，要手动 --exclude）
du -sh --exclude=raw --exclude=.cache/rclone .

# Go 工具链模板（go 不识别 fstype，也不识别 ignore 文件；只能显式列包路径）
go vet ./internal/... ./cmd/...        # 而不是 go vet ./...
go test ./internal/... ./cmd/...
# 单 binary build 永远指定具体路径，不用 './...':
go build -o build/quantumatlas ./cmd/server
```

ripgrep 默认遵守 `.gitignore` / `.rgignore`——当挂载子目录已经在仓库 ignore 文件里时（推荐做法），普通 `rg` / `git status` 不会扎进去；**只有 `rg --no-ignore` / `rg -uu` / `grep -r` 才需要手动加 `--glob '!path'`**。

仓库级保险：在仓库根 `.gitignore` / `.rgignore` / `.fdignore` / IDE 的 file-watch 排除里把 mount 子目录加进去（即使 mount 目录是仓库内的子目录，git 不会自己识别 FUSE）。

### 挂载点的删除：trash-put 而不是 rm

挂载目录里删除文件**仍然用 `trash-put`**，不要 `rm`——trash-cli 会在挂载点根目录自动建 `.Trash-<UID>/`，文件留在同一 filesystem 可恢复（而不是被搬到 `~/.local/share/Trash`、跨 filesystem 触发完整数据传输）。这条对 FUSE 和内核挂载（CIFS / NFS 等）都成立。也意味着挂载点本身的 `.Trash-<UID>/` 不会消耗本地盘，但会占远端 share 配额，按需 `trash-empty` 清理。

