# 疑难杂症案例

## VS Code Web 中文语言包 NLS 覆盖 Bug

> 2026-04-08 | VS Code 1.115.0 | WSL2 Mirrored Networking | Chrome

## 症状

- `code serve-web` 通过 `10.144.18.10:8080` 正常，`127.0.0.1:8080` 页面空白
- Console：`Uncaught Error: !!! NLS MISSING: 17116 !!!`
- Ctrl+Shift+R / 无痕模式均无效

## 排查关键转折

服务端文件完整（17287 条 NLS 消息），curl 验证无误。缓存、Service Worker、CSP、模块加载顺序全部排除。

**突破点**：让用户在 Console 执行 `globalThis._VSCODE_NLS_MESSAGES?.length` → 返回 **17109**（不是 undefined 也不是 17287）。说明数组被加载了，但被替换成了更短的版本。

随后用 `curl -H "Accept-Language: zh-CN"` 请求页面 → 发现服务器根据 Accept-Language 注入了中文 NLS CDN URL → 下载验证中文 NLS 恰好 17109 条。

## 根因

1. Chrome `Accept-Language` 含 `zh-CN` → 服务器注入 `https://www.vscode-unpkg.net/.../zh-cn/nls.messages.js`
2. HTML 先加载英文 NLS（17287 条），再加载中文 NLS（17109 条）→ 中文直接覆盖 `globalThis._VSCODE_NLS_MESSAGES`
3. 中文语言包翻译不完整，缺少 index 17109-17286 → `d(17116, null)` 抛出异常 → 页面崩溃
4. 10.144.18.10 能用是因为该 IP 到 CDN 的请求失败，英文 NLS 保持不变 — "能用"不是因为它做对了什么，而是因为它恰好失败了

## 解决

- VS Code Web 里 `Ctrl+Shift+P` → "Configure Display Language" → `en`
- 或 Chrome 语言设置把 English 排到中文前面
- 或等上游中文语言包补全

## PDF.js v5.5+ 在 Chrome < 140 上崩溃 (`Uint8Array.toHex` polyfill 缺失)

> 2026-04-10 | LaTeX-Workshop 10.14.1 (fork) | pdfjs-dist 5.6.205 | htbrowser Chrome 132

## 症状

- LaTeX-Workshop PDF 预览在新 Chrome 正常，老 Chromium 套壳浏览器（`Chrome/132 ... htbrowser/2.0.13`）打开 PDF 全白
- Console: `TypeError: hashOriginal.toHex is not a function` at `pdf.mjs:428` (BaseExceptionClosure)，外层包装在 `viewer.mjs:24251 加载 PDF 时发生错误`

## 排查关键转折

**第一层**直接 grep dev 仓库 `node_modules/pdfjs-dist/build/pdf.worker.mjs` 找 `\.toHex(`，看上下文有没有 if 守卫：

```js
// 安全（5.4.394 还有）：
if (Uint8Array.prototype.toHex) { return arr.toHex() }
return Array.from(arr, n => hexNumbers[n]).join("")

// 不安全（5.6.205 拿掉了）：
xxx.toHex()  // 直接调用
```

**判断 pdfjs 版本是否 broken 的一句话脚本**：`grep -A1 'Uint8Array.prototype.toHex' node_modules/pdfjs-dist/build/pdf.worker.mjs`，没看到 if 就是 broken。

**第二层**才是真坑：cp 完旧 pdfjs 后还报 `Cannot read properties of null (reading 'nextElementSibling') at patchViewerUI gui.ts:103`。原因是 pdfjs upstream 把 sidebar 改名成 viewsManager（element id `sidebarToggleButton` → `viewsManagerToggleButton`），latex-workshop 用 `ed96911a Fix new PDF.js viewer renames` 适配过。**回退 pdfjs 静态资源时必须把这几个 overlay 组件一起回退**，否则旧 viewer.html 配新 overlay 必崩。

## 根因

PDF.js 升级版本后无条件调用 TC39 提案 `Uint8Array.prototype.toHex()`（[proposal-arraybuffer-base64](https://github.com/tc39/proposal-arraybuffer-base64)）做 hex 编码。这个 API V8 直到 Chrome 140 才 ship（2025 年 9 月），Firefox 133 / Safari 18.2 早就有。低于 V8 140 的环境（国内套壳浏览器、老 Electron、老 VSCode webview、QtWebEngine 等）调用必 throw。

## 解决（保留扩展现有代码 + 只回退 pdfjs 相关）

1. **找一个 pdfjs 安全的旧版扩展**。实测 `latex-workshop 10.13.1` 自带 `pdfjs-dist 5.4.394`，有 fallback 守卫。VS Code marketplace 在 serve-web 里 "Install from VSIX" 报 `Extension not found`，**绕过办法**是直接 curl marketplace API：`https://marketplace.visualstudio.com/_apis/public/gallery/publishers/<pub>/vsextensions/<ext>/<ver>/vspackage`，返回的是 gzipped vsix（用 `curl --compressed`）。vsix 本质 zip，`unzip` 直接解开。

2. **替换已安装扩展的 pdfjs 静态资源**（成套）：
   - `viewer/{viewer.mjs,viewer.html,viewer.css,locale,images}`
   - `node_modules/pdfjs-dist/`
   - **保留** `viewer/latexworkshop.css`（差异只是新增 hide selector，对旧 html 是 no-op）

3. **同步回退 latex-workshop overlay**：把 `out/viewer/components/{gui,interface,refresh,state}.js` 也用旧 vsix 里的版本覆盖。这 4 个文件是 `ed96911a` 改名适配过的，跟旧 viewer.html 不兼容，必须配套。其他 6 个 components（`connection,l10n,synctex,trimming,utils,viewerhistory`）不动 — `git log <pre-merge>..HEAD -- viewer/components/` 显示 user fork 没改过它们。

4. Reload Window 验证。

## 教训

- **upstream merge 类 bug 不要假设"只动了 X"**。一次 merge 带几十个 commit，pdfjs viewer 静态资源、对应 element id rename、latex-workshop overlay 适配是**一体的**，回退也必须一体。
- **`git log A..B -- path/` 比 `git diff A B -- path/` 更精准**。前者告诉你 commit 历史和动机，后者只看终态。先 log 看 commit 主题挑出"只是 rename"的纯适配 commit，能省一半判断时间。
- **判断 JS 库版本是否受 polyfill 缺失影响，最快的办法是 grep 关键 API 看有没有 if 守卫**，比查 changelog 快。
- **VS Code serve-web 装老版扩展报 "Extension not found"**：走 marketplace API URL 直接 curl 即可。

## Windows 端口绑定异常但 Win/WSL 都查不到占用

> 2026-04-20 | Windows | WSL2 | 端口绑定

## 症状

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

## 排查关键转折

一开始按普通端口占用查 `netstat`、`Get-NetTCPConnection`、WSL `ss`、`portproxy`、`excludedportrange`，都没有结果。最后执行：

```powershell
wsl --shutdown
```

重启 WSL 后，同一端口可以正常绑定。

## 根因

高度疑似 WSL/Hyper-V localhost forwarding、NAT 或端口代理层状态残留。这个状态不一定表现为普通 Windows 用户态监听进程，也不一定能在 WSL 内看到，所以 `netstat`、`Get-NetTCPConnection`、`ss` 都可能查不到；`wsl --shutdown` 会重建 WSL 网络栈，残留随之消失。

## 解决

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

## Windows 普通 PowerShell 创建文件 symlink 失败

> 2026-04-20 | Windows | PowerShell | symlink 权限

## 症状

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

## 排查关键转折

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

## 解决

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

## 教训

- Windows 目录链接成功不代表 symlink 权限正常，先看用的是 junction 还是 symbolic link。
- 文件没有 junction，不能用 `.lnk` 快捷方式代替工具需要读取的配置文件。
- 用 `secedit` 写用户权限时优先用 `*SID`，不要用显示名或 `DOMAIN\User`。
- 修改用户权限后需要 logoff / logon；只重开 PowerShell 通常不够。

## 公网 VPS 做 UDP 端口段转发到内网地址时，启用 nftables.service 影响 Caddy HTTPS/TCP 服务

> 2026-04-26 | Linux VPS | Caddy | nftables | GOST | UDP 端口段转发

## 场景

需要在一台有公网 IP 的 VPS 上，把外部访问的 UDP 端口段转发到内网/隧道里的另一台机器，例如：

```text
VPS_PUBLIC_IP:11000-11009/udp -> 10.144.18.10:11000-11009/udp
```

远端机器已有 Caddy 承载 80/443/TCP，目标内网地址通过 `tun0` 可达。起初选择内核 NAT：`prerouting dnat` + `postrouting masquerade`。

## 症状

- UDP NAT 规则看起来成功安装。
- 但开启相关 nftables 配置后，VPS 上的 HTTPS/TCP 服务异常，外部连接 443/80 不可用。
- 不需要 reload 才坏；实测直接 `stop nftables.service` 后 HTTPS/TCP 立刻恢复，因为 `ExecStop=/sbin/nft flush ruleset` 把这次加载的问题规则清掉了。
- UDP 探测也容易误判：`nc -uvz` 对 UDP 没有握手语义，甚至未配置端口也可能显示 succeeded；普通网卡/UDP 计数还会被背景流量污染。

## 排查关键转折

先检查 `nftables.service` 的 unit：

```ini
ExecStart=/sbin/nft -f /etc/sysconfig/nftables.conf
ExecReload=/sbin/nft 'flush ruleset; include "/etc/sysconfig/nftables.conf";'
ExecStop=/sbin/nft flush ruleset
```

这就是关键：为了一个很小的 UDP 转发启用系统级 `nftables.service`，会把“谁在运行时维护了哪些 netfilter 规则”这件事变得不可控。即使转发规则本身只匹配 UDP，服务启动时加载的规则也可能影响同机已有的 HTTPS/TCP 服务链路、NAT 或防火墙状态；而 stop/reload/restart 的 `flush ruleset` 又会清空整套 nft ruleset。

另一个排查坑是 UDP 测试方式：

- `nc -uvz host port` 对 UDP 不可靠，不能当作“服务可用”的证据。
- 看 `/proc/net/snmp` 的 `Udp/InDatagrams` 或网卡 RX 计数，也可能被背景流量干扰。
- 没有 root 抓包权限时，很难证明某个测试 UDP 包确实到了目标应用；最干净还是在 VPS 或目标机上 `tcpdump udp portrange ...`。

## 根因

问题不是 DNAT 规则匹配了 TCP 443，而是为了安装一小段 UDP 转发，启用了会接管整个规则集的 `nftables.service`。这套 service 启动后加载的 ruleset 可能扰动同机已有的防火墙/NAT 状态，于是 Caddy 承载的 HTTPS/TCP 跟着异常；停止 service 后 `nft flush ruleset` 清掉问题规则，反而让连接恢复。

## 解决

先恢复现有 HTTPS 服务链路；如果问题来自刚启用的 `nftables.service`，停止它通常能立刻清掉问题规则：

```bash
sudo systemctl stop nftables
```

如果 Caddy 自身仍在监听但外部不可达，再重启 Caddy 以及相关网络/反代依赖：

```bash
sudo systemctl restart caddy
```

然后不要继续用系统 `nftables.service` 承载这种小转发：

```bash
sudo systemctl disable nftables
```

如果仍想用内核 NAT，推荐创建自己的独立 nft 表，并通过自定义 systemd oneshot 只做 `nft add table/add chain/add rule`，绝对不要 `flush ruleset`，也不要启用会加载 `/etc/sysconfig/nftables.conf` 的 `nftables.service`。

更简单、容易回滚的方案是用 GOST 做用户态 UDP 端口段转发，独立 systemd 服务，不碰 Caddy/nft/iptables：

```ini
[Unit]
Description=GOST UDP forward 11000-11009
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/gost -L udp://:11000-11009/10.144.18.10:11000-11009
Restart=always
RestartSec=3s

[Install]
WantedBy=multi-user.target
```

常用操作：

```bash
sudo systemctl enable --now gost-dst-udp
sudo systemctl status gost-dst-udp
sudo systemctl restart gost-dst-udp
sudo systemctl disable --now gost-dst-udp
```

## 最终验证

改用 GOST 独立 service 后，实测达到目标效果：

- `gost-dst-udp.service` 为 `active` / `enabled`
- VPS 上 `11000-11009/udp` 全部处于监听状态
- 从另一台公网机器向 `VPS_PUBLIC_IP:11000-11009/udp` 发测试包后，GOST 日志显示每个端口都建立了到目标内网地址的转发：

```text
CLIENT_IP:CLIENT_PORT <-> 10.144.18.10:11000
...
CLIENT_IP:CLIENT_PORT <-> 10.144.18.10:11009
```

日志里出现 `inputBytes`，说明公网 UDP 包确实进入 GOST 并被转发到内网目标。测试包没有业务协议语义，目标服务不回包时可能看到 `outputBytes=0`，这不影响“公网 UDP 端口段已经转发到内网地址”的结论。

## 清理注意

如果之前已经写过 nft 配置，清理时只删/移动自己命名的文件和表：

```text
/etc/sysctl.d/99-udp-forward.conf
/etc/nftables/udp-forward-*.nft
/etc/systemd/system/<custom-forward>.service
```

从 `/etc/sysconfig/nftables.conf` 去掉自己追加的 include 行即可。不要执行 `nft flush ruleset`。

写清理脚本时注意 `set -e` + 不存在的文件会直接中断。移动可选文件要用函数包一层：

```bash
move_if_exists() {
  local path="$1"
  if [[ -e "$path" ]]; then
    mv "$path" "$BACKUP_DIR/"
  fi
}
```

## 教训

- 只转发几个 UDP 端口时，别为了省事启用会接管全局 ruleset 的 `nftables.service`。
- 已有 HTTPS/TCP 服务和防火墙/NAT 状态可能互相依赖，任何 `flush ruleset` 都可能制造看似无关的断流。
- UDP 连通性测试不要相信 `nc -uvz` 的 succeeded；需要抓包或应用层协议响应。
- 对“少量端口段转发、优先易恢复”的场景，GOST 独立 service 往往比 nft/iptables 更好维护。
