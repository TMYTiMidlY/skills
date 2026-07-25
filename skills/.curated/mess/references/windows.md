# Windows 宿主机侧疑难杂症

> Windows 自身机制导致、且在 Linux/WSL 侧看不出所以然的坑：端口被 Hyper-V 悄悄圈占、symlink 需要单独授权。前两条是同一现象的两面，靠**错误码**分流。

## <a id="bind-10048"></a>端口绑定报 10048，但 Windows / WSL 都查不到占用

> 2026-04-20 | Windows | WSL2 | 端口绑定

### 症状

Windows 主机上尝试绑定某些端口（实测曾包括 1544、8090）时报端口已占用，例如：

```text
通常每个套接字地址(协议/网络地址/端口)只允许使用一次
os error 10048
```

但 Windows 和 WSL 常规检查都看不到该端口被占用：

```powershell
netstat -aon | findstr ":<PORT>"
Get-NetTCPConnection -LocalPort <PORT> -ErrorAction SilentlyContinue
netsh interface ipv4 show excludedportrange protocol=tcp
netsh interface ipv6 show excludedportrange protocol=tcp
```

```bash
ss -ltnp | grep ':<PORT>'
```

目标端口不在 `excludedportrange`，Windows 没有 LISTEN 进程，WSL 内也查不到监听。

### 排查关键转折

一开始按普通端口占用查 `netstat`、`Get-NetTCPConnection`、WSL `ss`、`portproxy`、`excludedportrange`，都没有结果。最后执行：

```powershell
wsl --shutdown
```

重启 WSL 后，同一端口可以正常绑定。

### 根因

高度疑似 WSL/Hyper-V localhost forwarding、NAT 或端口代理层状态残留。这个状态不一定表现为普通 Windows 用户态监听进程，也不一定能在 WSL 内看到，所以 `netstat`、`Get-NetTCPConnection`、`ss` 都可能查不到；`wsl --shutdown` 会重建 WSL 网络栈，残留随之消失。

### 解决

遇到 `os error 10048` 但查不到端口占用时，按这个顺序：

```powershell
netstat -aon | findstr ":<PORT>"
Get-NetTCPConnection -LocalPort <PORT> -ErrorAction SilentlyContinue
netsh interface ipv4 show excludedportrange protocol=tcp
netsh interface ipv6 show excludedportrange protocol=tcp
wsl -e sh -lc "ss -ltnp | grep ':<PORT>' || true"
wsl --shutdown
```

如果 `wsl --shutdown` 后立刻恢复，就按 WSL 网络残留处理，不要继续在普通进程列表里找。

> 反过来：若绑定报的是 `10013 AccessDenied`（不是 10048）、且端口**就在** `excludedportrange` 里，那是 Hyper‑V 独占保留、会随开机漂移——见[固定服务端口绑定报 `WSAEACCES`(10013)](#bind-10013)，解法是改用低端口而不是 `wsl --shutdown`。

## <a id="bind-10013"></a>固定服务端口绑定报 `WSAEACCES`(10013)，且随开机漂移

> Windows、WSL2 mirrored、Hyper-V 的一般服务端口案例；具体应用现场另存。

固定服务使用49760时，一次开机后直接bind返回`AccessDenied / WSAEACCES 10013`；49000与50000对照可绑定。`netsh int ipv4 show excludedportrange tcp`中49760位于49694–49793非`*`动态块，而带`*`托管块内的50000仍可绑定。不能只凭排除表推断所有条目都同样拒绝bind。

Windows默认动态端口范围49152–65535。HNS、WinNAT与vmcompute可在开机时从该范围预留块，位置会漂移；固定服务是否先绑定也影响当次结果。维护固定监听时优先选实际动态池外、未被占用和保留的端口，并做真实bind检查；49000只是本次通过的样本，仍须查目标系统当前范围。

`10013`与`10048`分开：前者查独占保留及权限；后者查真实占用和WSL网络残留，现有流程见[端口绑定报10048](#bind-10048)。mirrored模式共享宿主网络边界，WSL侧也可能绑定失败；先用`wslinfo --networking-mode`确认模式，不假设必有独立NAT栈。

PowerShell探针读取native中文输出时注意PS5.1编码；可用ASCII标签或明确转码。`.NET TcpListener`真实bind比只看netsh表更直接。`HttpClient.Result`若只给无信息的`RuntimeException`，改用能保留底层错误的探针。


## <a id="symlink-privilege"></a>普通 PowerShell 创建文件 symlink 失败

> 2026-04-20 | Windows | PowerShell | symlink 权限

### 症状

在普通 PowerShell 里创建文件软链接失败：

```powershell
New-Item -ItemType SymbolicLink -Path "$HOME\AGENTS.md" -Target "$HOME\skills\AGENTS.md"
New-Item -ItemType SymbolicLink -Path "$HOME\CLAUDE.md" -Target "$HOME\AGENTS.md"
```

报错：

```text
Administrator privilege required for this operation.
```

用 `cmd /c mklink` 也失败：

```text
You do not have sufficient privilege to perform this operation.
```

但目录 skill 可以用 junction 成功安装：

```powershell
New-Item -ItemType Junction -Path "$HOME\.agents\skills\manage-skills" -Target "<repo>\skills\.curated\manage-skills"
```

### 排查关键转折

先区分了三类链接：

- `SymbolicLink`：文件和目录都能指向，但 Windows 默认需要 `Create symbolic links` 权限。
- `Junction`：只适用于目录，通常普通用户在有写权限的位置也能建。
- `.lnk` 快捷方式：不是文件系统级链接，工具不会按真实文件读取，不能替代 symlink。

因此目录能装不是因为 symlink 权限正常，而是因为走了 junction；`AGENTS.md` / `CLAUDE.md` 是文件，不能用 junction，只能用文件 symlink。

按微软文档确认权限名是 `SeCreateSymbolicLinkPrivilege`，普通用户需要管理员授予该权限，或者开启 Developer Mode。用户有管理员权限但当前 agent 会话没有管理员 token，所以由用户在管理员 PowerShell 里授权。

第一次用 `DOMAIN\User` 写入 `secedit` 配置后出现：

```text
出现了扩展错误。
任务已结束，但有错误。
有关详细信息，请参阅日志 %windir%\security\logs\scesrv.log。
```

根因是 `secedit` 的用户权限配置更稳的写法是 SID，且 SID 前要带 `*`，并且必须写入 `[Privilege Rights]` 段，不能随便追加到文件末尾。另一个关键点是目标用户要明确：管理员 PowerShell 的当前身份不一定等于需要授权的日常登录用户，脚本应从目标用户的 home 目录解析账号，而不是直接使用管理员窗口的当前 SID。

另一个干扰项：用户复制命令时把 PowerShell 提示符 `PS C:\Users\...>` 和错误输出也粘进去了，导致 `PS` 被当成 `Get-Process` 别名执行，出现大量无关报错。给用户的命令必须明确“不要粘提示符”。

### 解决

在管理员 PowerShell 里执行：

```powershell
$targetHome = [Environment]::GetFolderPath("UserProfile")
$targetUser = Split-Path $targetHome -Leaf
$target = "$env:COMPUTERNAME\$targetUser"
$targetSid = ([System.Security.Principal.NTAccount]$target).Translate([System.Security.Principal.SecurityIdentifier]).Value
$principal = "*$targetSid"

"Granting SeCreateSymbolicLinkPrivilege to $target ($principal)"

$temp = Join-Path $env:TEMP "secpol-symlink"
New-Item -ItemType Directory -Force -Path $temp | Out-Null

$cfg = Join-Path $temp "secpol.cfg"
$db = Join-Path $temp "secpol.sdb"
$log = Join-Path $temp "secpol.log"

Remove-Item $cfg, $db, $log -ErrorAction SilentlyContinue

secedit /export /cfg $cfg | Out-Null

$content = [string[]](Get-Content $cfg)
$sectionIndex = [Array]::IndexOf($content, "[Privilege Rights]")
if ($sectionIndex -lt 0) {
    throw "secedit export 里没有 [Privilege Rights] 段，停止修改。"
}

$lineIndex = [Array]::FindIndex(
    $content,
    [Predicate[string]]{ param($line) $line -match '^SeCreateSymbolicLinkPrivilege\s*=' }
)

if ($lineIndex -ge 0) {
    $current = ($content[$lineIndex] -replace '^SeCreateSymbolicLinkPrivilege\s*=\s*', '').Trim()
    $entries = @()
    if ($current) {
        $entries = $current -split '\s*,\s*'
    }

    if ($entries -notcontains $principal) {
        $entries += $principal
    }

    $content[$lineIndex] = "SeCreateSymbolicLinkPrivilege = " + ($entries -join ",")
} else {
    $list = [System.Collections.ArrayList]::new()
    [void]$list.AddRange($content)
    $list.Insert($sectionIndex + 1, "SeCreateSymbolicLinkPrivilege = $principal")
    $content = [string[]]$list
}

Set-Content -Path $cfg -Value $content -Encoding Unicode

secedit /configure /db $db /cfg $cfg /areas USER_RIGHTS /log $log
gpupdate /force

"Check result:"
secedit /export /cfg $cfg | Out-Null
Select-String -LiteralPath $cfg -Pattern '^SeCreateSymbolicLinkPrivilege\s*='
```

然后 logoff 当前 Windows 用户再登录，让登录 token 重新生成：

```powershell
logoff
```

重新登录后，在普通 PowerShell 测试：

```powershell
Set-Content "$env:TEMP\target-test.txt" "ok"
New-Item -ItemType SymbolicLink -Path "$env:TEMP\symlink-test.txt" -Target "$env:TEMP\target-test.txt"
Get-Item "$env:TEMP\symlink-test.txt" | Select-Object FullName,LinkType,Target
Remove-Item "$env:TEMP\symlink-test.txt","$env:TEMP\target-test.txt"
```

### 教训

- Windows 目录链接成功不代表 symlink 权限正常，先看用的是 junction 还是 symbolic link。
- 文件没有 junction，不能用 `.lnk` 快捷方式代替工具需要读取的配置文件。
- 用 `secedit` 写用户权限时优先用 `*SID`，不要用显示名或 `DOMAIN\User`。
- 修改用户权限后需要 logoff / logon；只重开 PowerShell 通常不够。
