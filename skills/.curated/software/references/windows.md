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
- 父进程（WSL 这边）拿不到 admin 子进程的 stdout——它已经在另一个用户上下文里。**结果靠落盘**：在被弹起的命令里 `... | Out-File C:\Temp\<task>\result.txt -Encoding utf8 ; Write-Output DONE | Out-File C:\Temp\<task>\done.txt`，WSL 端轮询 `done.txt` 文件出现即视为完成，再读 `result.txt`。
- `Out-File` 路径不要写 `\\wsl.localhost\Ubuntu\...` —— Windows admin 进程不能用 UNC 当 CWD，也不能很流畅地写 WSL 文件系统。固定写 `C:\Temp\<task>\` 之类的本地路径，WSL 端读 `/mnt/c/Temp/<task>/result.txt`。

## cmd.exe 不接 UNC 路径当 CWD

从 WSL 里 `cd /home/<user>` 然后调 `cmd.exe /c "..."`，cmd 会打印：

> CMD does not support UNC paths as current directories.

并把 CWD 重设到 Windows 目录、附带一行中文/英文警告，污染输出。修复：调 cmd 之前 `cd /` 一下，让 WSL 当前路径不是 `/home/...` 这种被 cmd 当 UNC 看的路径。pwsh 7 没这个限制。

## 资源管理器回收站 vs `trash-put`

Windows 的“回收站”只对 `Shell:RecycleBinFolder` 协议（资源管理器右键删 / `Recycle.Bin` API）有效，对 PowerShell `Remove-Item`、WSL `rm`、WSL `trash-put` 都不生效。

WSL 端要恢复 `/mnt/c/...` 误删，应在 WSL 里用 `trash-put` 而不是 `rm`，事后 `trash-restore` 恢复；Windows 资源管理器看不到这些条目，但从 WSL 视角文件可恢复，比 `rm` 安全得多。

> `trash-put` 在 NTFS 卷根建卷内回收站的通用机制、trash-cli 与 `gio trash` 同规范互通、`trash-rm` 匹配规则、坏 `.trashinfo` 的正确处置等见 [trash.md](trash.md)。
