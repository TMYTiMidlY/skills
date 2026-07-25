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

> 2026-07-13 | Windows | WSL2 mirrored | Hyper‑V | 端口保留 | Clash Verge / mihomo

> 与[端口绑定报 10048](#bind-10048) 那条（`excludedportrange` 里**没有**、`wsl --shutdown` 恢复）是**同一 Hyper‑V 端口保留现象的两面**：本案是 `WSAEACCES`(10013) + 端口**就在** `excludedportrange` 里。绑定失败先看错误码分流。

### 症状

Windows 上的 Clash Verge Rev（GUI，核心进程 `verge-mihomo`）配了 `mixed-port: 49760`，但"代理用不了"。且**曾经能用，某次开机后就不行了**（时好时坏）。客观现象串：

- `Get-NetTCPConnection` 看 `verge-mihomo` 只在 `[::]:7892`(redir-port) + `[::]:53`(dns)，**没有 49760**。
- TCP 连 `127.0.0.1:49760` → `ConnectionRefused`；拿它当 HTTP 代理发请求 → 失败。
- Windows 系统代理注册表 `ProxyServer=127.0.0.1:49760` 但 `ProxyEnable=0`。
- 直接 bind 实测（pwsh + `.NET TcpListener`，错误码语言中立）：

```text
WIN bind 49760: FAIL [AccessDenied]   # WSAEACCES / os error 10013
WIN bind 49000: OK                     # 对照：低端口能绑
WIN bind 50000: OK                     # 对照：在 excludedportrange 的 * 托管块里，反而能绑
```

`netsh int ipv4 show excludedportrange tcp` 里 **49760 落在 `49694–49793`** 这个非 `*` 的动态块内。

### 排查关键转折

1. **先分清两个 mihomo**：WSL 里 `mihomo.service`（systemd `--user`，`127.0.0.1:7890`+`:9090`，正常）vs Windows Clash Verge Rev（`verge-mihomo`，配 49760，起不来）。二者**完全独立**。一度把 WSL 的 7890、甚至 Docker Desktop 扯进来当"受害者"，都是干扰项——7890 只是个 WSL user service，Docker 现在是 manual 指 7890、跟 49760 无关。砍掉。
2. **别只靠 `netsh` 文本推断，直接实测 bind**：绑 49760 → `AccessDenied (WSA10013)`，绑低端口 → OK。**10013「被独占保留」区别于 10048「已被占用」**——这是本案与[端口绑定报 10048](#bind-10048) 那条的分水岭。
3. **别想当然 WSL 是独立 NAT 栈**：`wslinfo --networking-mode` = **mirrored**，WSL 与 Windows 共享 localhost，WSL 侧绑 49760 也失败（`EADDRINUSE`）。→ 下结论前先确认 WSL 网络模式，不存在"Windows 不行 WSL 行"的不对称。
4. **"在排除表里"≠"一定绑不上"**：`50000`（带 `*` 的托管块）反而 bind OK，只有 49760 所在的非 `*` 动态块才吃 WSAEACCES。
5. **pwsh 探针两个坑**（详见 `software` skill 的 Windows 宿主侧章节）：① PS 5.1 的 native/中文输出按 GBK，UTF‑8 strict 解码会乱码/炸 channel → 探针标签只用 ASCII，或 native exe 管 `iconv -f gbk`；② `HttpClient.Result` 被 PS 包成无信息的 `RuntimeException` → 改用 `TcpClient` + `Invoke-WebRequest -Proxy` 才拿得到干净结果。

### 根因

- Windows 临时/动态端口段默认 **49152–65535**（`netsh int ipv4 show dynamicportrange tcp`）。这段是给"系统自动分配的短命客户端连接"用的，不适合挂固定服务。
- 跑 WSL2 / Docker / Hyper‑V 时，**HNS + WinNAT + vmcompute**（实测均 Running）为 NAT 记账，在**开机时**从这段里预先圈走几大块、打独占标记 → 进 `excludedportrange`（如 49694–49793）。
- **这些块每次开机现圈、位置会漂**，叠加"谁先绑谁赢"的启动抢占赛：
  - 之前能用 = 某次开机块没盖到 49760，或 `verge-mihomo` 抢在保留之前先绑住了。
  - 这次不行 = 块 49694–49793 圈住 49760 且 mihomo 没抢先 → bind 吃 WSAEACCES → mixed-port 监听起不来，只剩 redir 7892 + dns 53。
- Verge 又把 `127.0.0.1:49760` 写进系统代理注册表（残留）。但 `ProxyEnable=0` 时这是**潜在陷阱、非现行故障**：守规矩的程序见开关关着就直连；只有无视开关、硬读 `ProxyServer` 的程序才会撞死端口（Docker Desktop 的 system-proxy 自动探测是历史典型，也因此当初被迫改成 manual 指 7890）。

### 解决

- **根治**：别把固定服务端口挂在 49152–65535。改到**低端口（< 49152）** 即可永久避开 Hyper‑V 圈占。例：Clash Verge `mixed-port` 49760 → 49000（`49000<49152`，实测 bind OK）或 7888。WSL 那个 `mihomo.service` 用 7890 就从没这毛病。
- **改 Clash Verge Rev 的端口**：GUI 的配置链（`config.yaml`→`clash-verge.yaml`→命名管道）、端口要改基础 `config.yaml` 的 `mixed-port` 而非 `verge.yaml`、核心由 SYSTEM 服务 `clash-verge-service` 托管杀不掉 → 见 `network` skill 的 Mihomo 客户端（Clash Verge Rev）配置章节。
- **诊断口诀（绑定失败先看错误码分流）**：
  - `10013 AccessDenied / WSAEACCES` → 端口被 Hyper‑V **独占保留**，查 `excludedportrange`，改**低端口**（本案）。
  - `10048 已占用但 netstat / Get-NetTCPConnection / ss 都查不到` → WSL 网络栈残留，`wsl --shutdown` 重建（见[端口绑定报 10048](#bind-10048)）。

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

