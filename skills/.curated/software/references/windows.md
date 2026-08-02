# Windows / WSL 主机侧速记

> 跑在 Windows 上的命令行、终端、PowerShell 版本选择、UAC 弹出方式等“宿主 OS 层面”的小经验。
> WSL 内 Linux 服务的网络坑（wslrelay、portproxy、Mihomo TUN、Docker IPv6 dual-stack）见 `network` skill，不在这里重复。

## PowerShell 5.1 vs PowerShell 7（pwsh）

两个不是版本号那么简单——是**完全不同的两套运行时**：

| | Windows PowerShell **5.1** | PowerShell **7** (pwsh) |
|---|---|---|
| 运行时 | .NET Framework 4.x（Windows-only） | .NET Core / .NET 6+（cross-platform） |
| 安装来源 | Windows 自带，不可卸载 | 独立装：`winget install Microsoft.PowerShell` |
| 可执行文件 | `/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe` | `/mnt/c/Program Files/PowerShell/7/pwsh.exe` |
| 默认 `[Console]::OutputEncoding` | 系统 codepage（中文 Windows = `gb2312` / CP936） | **同样**系统 codepage（实测 `gb2312`，与 5.1 一致） |
| **.NET cmdlet 输出 encoding** | 系统 codepage | **UTF-8** ✅ |
| **native exe 子进程 stdout** | 系统 codepage | 同上，**系统 codepage**（pwsh 不转码） |
| 大多数 cmdlet 互通 | ✅ | ✅ |
| `Get-NetTCPConnection` / `Get-NetFirewallRule` 等 NetTCPIP 模块 | ✅ | ✅ |

> 路径不依赖用户名（`Program Files`、`Windows\System32` 都是系统常量），跨 Windows 主机可直接照抄。

### 实测：5.1 与 7 的真实差异点

WSL 端跑了对照实验：

| 命令 | 5.1 stdout | 7 stdout | portal_bash UTF-8 strict 解码 |
|---|---|---|---|
| `Get-NetTCPConnection ...` (cmdlet) | GBK | **UTF-8** | 5.1 → 炸；7 → ✅ |
| `netsh interface portproxy show all` (native exe) | GBK | **GBK**（一样） | 两版都 → 炸 |
| `[Console]::OutputEncoding` 自报 | `gb2312/936` | `gb2312/936` | 自报没区别 |

结论：**pwsh 7 只在调用 .NET cmdlet 时输出 UTF-8；一旦穿过 pwsh 调系统的 native exe (`netsh.exe`/`reg.exe`/`ipconfig.exe` 等)，stdout 仍按系统 codepage**（中文 Windows 是 GBK），pwsh 不做转码。所以 “用 pwsh 7 就能避开 GBK 坑” 这种笼统说法是错的——只对 cmdlet 成立。

### 受害场景与修复（按调用类型）

WSL 端 / portal_bash / MCP server 这类按 UTF-8 strict 解码 stdout 的调用方，遇到 `0xd3 0xd5` 等中文常用字节会抛 `'utf-8' codec can't decode byte ...`，重则把整个 channel 拆掉。修复路径要按 **被调命令是 cmdlet 还是 native exe** 分两种：

1. **调 cmdlet（`Get-Net*`、`Get-Process`、`Get-ChildItem` 等）**：用 pwsh 7。
   ```bash
   /mnt/c/Program\ Files/PowerShell/7/pwsh.exe -NoProfile -Command \
     "Get-NetTCPConnection -State Listen -LocalPort 9000 | Format-Table"
   ```
2. **调 native exe（`netsh`、`reg`、`sc`、`bcdedit` 等）**：pwsh 5.1 / 7 都炸，必须二选一：
   - **a. 管 iconv 真转码**（推荐，保留可读中文）：
     ```bash
     /mnt/c/Program\ Files/PowerShell/7/pwsh.exe -NoProfile -Command \
       "netsh interface portproxy show all" 2>&1 | iconv -f gbk -t utf-8
     ```
   - **b. 强制 chcp 65001 + UTF-8 encoding**（部分命令仍有 stderr 走系统 codepage）：
     ```bash
     /mnt/c/Program\ Files/PowerShell/7/pwsh.exe -NoProfile -Command \
       "chcp 65001 > \$null; [Console]::OutputEncoding=[Text.Encoding]::UTF8; netsh interface portproxy show all"
     ```
   - **c. 让 pwsh 把 native exe 输出收进字符串后再 Out-String 转 UTF-8**（pwsh 自动处理）：
     ```powershell
     # 这种 pipe 进 cmdlet 的形式，pwsh 7 会按其内部 OutputEncoding 输出
     netsh interface portproxy show all | Out-String -Stream
     ```
     但实测 pwsh 7 此时仍按系统 codepage 收 native exe 字节，没真的转码——所以这条**只是看起来干净，并不真解决**。靠管 `iconv` 才稳。
3. **用 cmdlet 替代 native exe**（当存在等价 cmdlet 时最干净）：
   - `netsh interface portproxy show all` → `Get-NetTCPConnection -State Listen | ...`（**不完全等价**，portproxy 表 cmdlet 不直接暴露；用 `netsh int portproxy dump` + iconv 仍是最可靠的）
   - `netstat -ano | findstr :<port>` → `Get-NetTCPConnection -LocalPort <port>` ✅ 完美替代
   - `ipconfig` → `Get-NetIPAddress` ✅
   - `sc query` → `Get-Service` ✅

通用兜底脚本（先 pwsh 7 / 后 5.1，遇 native exe 一律管 iconv）：

```bash
PWSH="/mnt/c/Program Files/PowerShell/7/pwsh.exe"
[ -x "$PWSH" ] || PWSH="/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"

# cmdlet 调用：可以不管 iconv
"$PWSH" -NoProfile -Command 'Get-NetTCPConnection -State Listen -LocalPort 9000 | Format-Table'

# native exe 调用：必须管 iconv
"$PWSH" -NoProfile -Command 'netsh interface portproxy show all' 2>&1 | iconv -f gbk -t utf-8
```

**脚本稍复杂就写 `.ps1` 文件用 `-File` 跑，别堆 `-Command`**：从 bash 里 `bash -c "pwsh -Command @\"...\"@"` 嵌引号是引号地狱（bash、pwsh、here-string 三层转义打架）。固定套路是先把脚本写成 `.ps1`，再 `-File` 执行——默认 ExecutionPolicy 会拦未签名脚本，所以带 `-ExecutionPolicy Bypass`：

```bash
PWSH="/mnt/c/Program Files/PowerShell/7/pwsh.exe"
cat > /tmp/foo.ps1 <<'PS1'
$enc = [uri]::EscapeDataString("🚀 节点选择")
Invoke-RestMethod -Uri "http://127.0.0.1:9090/proxies/$enc"
PS1
"$PWSH" -NoProfile -ExecutionPolicy Bypass -File /tmp/foo.ps1
```

### 其他可移植性差异（影响极少，记一笔）

- pwsh 7 默认 `Invoke-WebRequest` 不走 IE 引擎，跨平台；5.1 还吃 IE 设置（兼容性差）。
- pwsh 7 支持 `&&` / `||` 链式（与 bash 一致），5.1 不支持。
- pwsh 7 在 .NET 6+ 上跑 `Get-Process` 等的速度通常比 5.1 快一倍。

## 从 WSL 弹 UAC 拿管理员权限

WSL 里直接调 `powershell.exe` 起的是**当前用户态非 admin** PowerShell。要跑 `netsh interface portproxy add` 等需要管理员的命令，最不打扰的做法是用 `Start-Process -Verb RunAs`：

```bash
# Windows 桌面会弹 UAC 提示，点"是"后命令以 admin 跑
/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe -NoProfile -Command \
  "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile','-Command','<admin command here>'"
```

注意：

- 触发 UAC 的是 `Start-Process -Verb RunAs`，与 5.1 / pwsh 无关；外层用 5.1 调 pwsh 7 也可以。
- **多行命令不要硬塞进 `Start-Process ... -Command`**：Bash、外层 PowerShell、`ArgumentList` 和内层 PowerShell 会连续解释引号、换行与 here-string，稍复杂就会在内层报 `ParserError`。把命令写成 `C:\Temp\<task>\run.ps1`，再用 `Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile','-File','C:\Temp\<task>\run.ps1'`；脚本本身仍按下一条约定写 `result.txt` / `done.txt`。代价只是多一个临时文件，但可审查、可复跑，远比堆转义稳定。
- 父进程（WSL 这边）拿不到 admin 子进程的 stdout——它已经在另一个用户上下文里。**结果靠落盘**：在被弹起的命令里 `... | Out-File C:\Temp\<task>\result.txt -Encoding utf8 ; Write-Output DONE | Out-File C:\Temp\<task>\done.txt`，WSL 端轮询 `done.txt` 文件出现即视为完成，再读 `result.txt`。
- `Out-File` 路径不要写 `\\wsl.localhost\Ubuntu\...` —— Windows admin 进程不能用 UNC 当 CWD，也不能很流畅地写 WSL 文件系统。固定写 `C:\Temp\<task>\` 之类的本地路径，WSL 端读 `/mnt/c/Temp/<task>/result.txt`。

## 判断“某软件最后被谁用过”：别信 `%USERPROFILE%` 根目录的 LastWriteTime

想在一台多用户 Windows 机上判断“某软件最后一次被哪个用户用过”时，**`%USERPROFILE%`（每个用户的 profile 根目录）的 `LastWriteTime` 不是可靠指标**——它不随登录/使用刷新。实测一台批量建号的机器，除本人外 10 个账号的根目录 `LastWriteTime` 全部冻在建号那一刻（同一分钟），据此会误判成“这些人从没登录、从没用过”。

真正的“最后使用”痕迹在**各用户自己的 `AppData` 内部**：软件的 `cache.db`、`logs\*.log`、`window_state.json` 等文件的 mtime 才反映真实活动。但从 WSL 以普通用户 token 读 `/mnt/c/Users/<别人>/AppData` 会被 NTFS ACL 挡（`Permission denied`）——`AppData\Roaming` / `Local` 默认只有本人 + SYSTEM + Administrators 可读。

所以要跨用户判断，得**提权**（见上一节「从 WSL 弹 UAC」），在 admin 上下文里遍历各用户 `AppData`、读软件数据文件的 mtime。踩过的坑：先拿各用户 `%USERPROFILE%` 根目录的 `LastWriteTime` 下过“只有某人用过”的结论，提权读 `AppData` 内部后被直接推翻（实际有 8 个用户用过）。

## cmd.exe 不接 UNC 路径当 CWD

从 WSL 里 `cd /home/<user>` 然后调 `cmd.exe /c "..."`，cmd 会打印：

> CMD does not support UNC paths as current directories.

并把 CWD 重设到 Windows 目录、附带一行中文/英文警告，污染输出。修复：调 cmd 之前 `cd /` 一下，让 WSL 当前路径不是 `/home/...` 这种被 cmd 当 UNC 看的路径。pwsh 7 没这个限制。

## 资源管理器回收站 vs `trash-put`

Windows 的“回收站”只对 `Shell:RecycleBinFolder` 协议（资源管理器右键删 / `Recycle.Bin` API）有效，对 PowerShell `Remove-Item`、WSL `rm`、WSL `trash-put` 都不生效。

WSL 端要恢复 `/mnt/c/...` 误删，应在 WSL 里用 `trash-put` 而不是 `rm`，事后 `trash-restore` 恢复；Windows 资源管理器看不到这些条目，但从 WSL 视角文件可恢复，比 `rm` 安全得多。

> `trash-put` 在 NTFS 卷根建卷内回收站的通用机制、trash-cli 与 `gio trash` 同规范互通、`trash-rm` 匹配规则、坏 `.trashinfo` 的正确处置等见 [trash.md](trash.md)。

## WSL `/tmp` 每次 `wsl --shutdown` 后清空 —— 是 systemd-tmpfiles 的 `D` 规则，不是 tmpfs

**现象**：往 `/tmp`（如 `/tmp/clipboard`）放文件，`wsl --shutdown` 再进去就空了。

**容易猜错的原因**：以为 `/tmp` 是 tmpfs（内存盘）所以重启丢。**不一定**。实测这台 WSL 的 `/tmp` 根本不是独立挂载，就是持久 ext4 根盘 `/dev/sdd` 上的普通目录（`/tmp`、`$HOME`、仓库同一 device id，`fstab` 里无 `/tmp` 项）：

```bash
findmnt -no SOURCE,FSTYPE,TARGET /tmp   # 无输出 = /tmp 不是单独挂载点，归属 /
stat -c%d /tmp "$HOME"                    # 两个 device id 相同 = 同一文件系统
```

**真正的机制是 systemd-tmpfiles 在每次 boot 主动清空 `/tmp`**，跟底层是不是 tmpfs 无关：

1. 规则用的是**大写 `D`**：`/usr/lib/tmpfiles.d/tmp.conf` → `D /tmp 1777 root root 30d`
2. boot 服务带 `--remove`：`systemctl cat systemd-tmpfiles-setup.service` → `ExecStart=systemd-tmpfiles --create --remove --boot --exclude-prefix=/dev`（`static`，由 `sysinit.target` 拉起）
3. `man 5 tmpfiles.d`：**`D` — Similar to d, but in addition the contents of the directory will be removed when `--remove` is used.**

`wsl --shutdown` 终止整个 WSL2 VM，下次启动 systemd 冷启 → `systemd-tmpfiles-setup.service` 跑 `--remove` → `D /tmp` 把 `/tmp` 内容清掉。这就是「重启后 `/tmp` 空了」的根因。

- **`30d` 是给周期清理的、跟 boot 清空无关**：age 字段只对 `systemd-tmpfiles-clean.timer` 的 `--clean`（按 mtime 删超 30 天的）生效；boot 时的 `--remove` 是**全量清**，不看年龄。所以别指望「放 29 天还在」。
- **判据别看 tmpfs**：`/tmp` 在磁盘上 ≠ 重启保命。决定清不清的是有没有 `D`/`R` 规则 + boot `--remove`，而不是挂载类型。查规则：`grep -rE '^\s*[a-zA-Z]+\s+/tmp\b' /usr/lib/tmpfiles.d/ /etc/tmpfiles.d/`。
- **例外**：`tmp.conf` 里 `x`/`X` 前缀排除的子目录（`/tmp/systemd-private-*`、`/tmp/snap-private-tmp` 等）不被清。
- **区分 `wsl --shutdown` 与关终端窗口**：只关窗口 distro 没停（除非 `vmIdleTimeout` 到点），`/tmp` 还在；只有整机 shutdown / distro 重启才触发 tmpfiles 清空。

**实践结论**：

- 要跨 `wsl --shutdown` 保命的东西**别放 `/tmp`**，放 `$HOME` 下（家目录在持久盘、无 `D` 清空规则）。
- `trash-put /tmp/xxx` 能"救"文件：回收站在 `~/.local/share/Trash/`（家目录），不受 `/tmp` 的 `D` 规则影响、也不自动过期（要手动 `trash-empty`）。且因 `/tmp` 与 `$HOME` 同一文件系统，trash 是**瞬时 rename 不拷贝**，几百 MB 也秒删。相关见 [trash.md](trash.md)。

## <a id="wsl-boot-time"></a>WSL 的开机时刻与重启判定

判断一台 WSL2 发行版什么时候启动、上次跑到什么时候，常用来源在 WSL 下会互相矛盾：

| 来源 | 读的是什么 | WSL2 下是否可信 |
|---|---|---|
| `uptime -s`、`/proc/stat` 的 `btime` | 内核记录的启动时刻 | 可能是上次**关机**的时刻 |
| `who -b`（读 `/var/log/wtmp`） | systemd 启动时写下的登录记录 | 反映真实启动，但依赖 wtmp 完好 |
| `journalctl --list-boots` | 每个 boot 的首末条日志时间 | 以此为准 |

`btime` 不是直接记下来的，而是内核在启动时用「当前墙钟时间 − 已运行时间」算出来的。WSL2 的虚拟 RTC 以**上次关机前后的时刻**做种子，等时间同步把钟拨正，`btime` 早已算完并固定，于是它保留的是上一次关机的时刻。

**误差恰好等于虚拟机的停机时长**，这让它格外有迷惑性：`wsl --shutdown` 后立刻重启，三个来源看起来完全一致；停了一天再开，`uptime -s` 就差出一整天，而且给出的是一个**看起来很合理的过去时刻**，没有任何异常提示。实测过的一次分歧：虚拟机某日 06:28 停止、次日 11:28 才重新启动，重启后 `uptime -s` 报的是前一日 06:29——正是上次停止的时刻。

```bash
journalctl --list-boots        # 排查重启时间点一律以它为准
```

宿主 Windows 的开机时刻是另一套来源，与 guest 无关：

```powershell
(Get-CimInstance Win32_OperatingSystem).LastBootUpTime
```

> 三个来源的分歧与 `journalctl --list-boots` 的可靠性为实测。"虚拟 RTC 以上次关机时刻做种子"是由 `btime` 恰好落在上次关机时刻这一现象反推的机制解释，未在官方文档中核实。

## <a id="misc-diff"></a>5.1 与 7 的其余差异

除了 [文本编码](#encoding) 那三个开关，剩下这些差异影响面小，记一笔备查：

- 〔7〕`Invoke-WebRequest` 不走 IE 引擎，跨平台；〔5.1〕还吃 IE 设置（兼容性差）。
- 〔7〕支持 `&&` / `||` 链式（与 bash 一致）；〔5.1〕不支持。
- 〔7〕在 .NET 6+ 上跑 `Get-Process` 等的速度通常比 5.1 快一倍。
- 同名命令的参数集可能不同，用前先查而不是凭记忆：`Get-Command <cmdlet> -Syntax`。例如 `Format-Hex -Count` 只有〔7〕有，〔5.1〕要改用 `... | Select-Object -First N` 限制管道。

