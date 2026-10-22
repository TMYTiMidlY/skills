# 桌面客户端显示与捕获防护

## <a id="case-scope"></a>问题现象与使用限制

一款基于 Chromium 的受管桌面客户端中，普通页面可见，受保护业务页在 Windows RDP 里全白，在 ToDesk 中显示为黑色，KimiCU 截图则失败。切换到 RDP 时曾短暂看到内容。排障需要保留现有登录和远程访问。

技术工具和接口保留原名：RDP、ToDesk、KimiCU、REA、GNU objdump、PowerShell、Chromium 和 Win32 API。业务平台、站点、账号、凭据及私有部署信息用通用称谓或参数代替。

本案先做网络、前端、桌面捕获对照，再追到客户端自己的原生显示保护，经过明确授权完成当前进程的可回滚调整；随后只读核对录屏、诊断、上报和模块阻止能力。

> 证据来自程序副本、PE 元数据、嵌入接口描述、有界反汇编、运行字段、日志和实际画面。原始材料保存在任务私有目录；知识库采用脱敏后的机制与流程。

## <a id="display-paths"></a>区分 RDP 白屏、ToDesk 黑屏与 KimiCU 截图失败

实际排查顺序是：

1. 用 KimiCU 截普通页和受保护页，对照 ToDesk 与 RDP 中的画面。
2. 用 PowerShell 查询 `GetWindowDisplayAffinity`，确认窗口是否排除捕获。
3. 用 REA 和 objdump 从保护 API 追到具体函数，分别找到捕获设置与网页隐藏逻辑。
4. 读取当前窗口的保护开关、远程检测结果和 `ContentsWebView` 显示状态。
5. 获得授权后修正远程隐藏分支，再独立处理截图参数，分别验收 RDP 画面与 KimiCU 截图。

各项现象对应的排查方向如下：

| 现象或证据 | 排查方向 |
|---|---|
| 首页和启动资源可获取 | 继续检查页面执行、原生视图和业务登录 |
| 匿名代理请求返回认证挑战 | 对照客户端实际认证后的请求结果 |
| 接口返回未登录状态 | 核对前端的容错分支和后续布局 |
| 开发者面板空白，面板参数明确被禁用 | 检查调试界面的管理设置 |
| KimiCU 能截普通页，受保护页的 WGC 捕获失败 | 查询窗口的防截屏设置 |
| ToDesk 黑屏，KimiCU 的 PrintWindow＋DWM 回退也是黑帧 | 对照 `WDA_EXCLUDEFROMCAPTURE` 与实际截图 |
| Windows RDP 中是白屏 | 追踪客户端是否主动隐藏 `ContentsWebView` |
| 重连时内容闪现后消失 | 追踪更改显示状态的回调 |

定点绕行后现象保持一致，结合故障早于透明代理开启的时间线，排查转向客户端显示层。临时测试路由用后撤回。

### <a id="observation-channel"></a>用 KimiCU 对照普通页和受保护页

KimiCU 负责观察和点击现有桌面；ToDesk 和 Windows RDP 提供另外两种观察结果。先确认执行账户、交互会话、窗口归属及进程完整性级别，再用普通页验证取图链。

本案通过 SSH stdio 桥接到 Windows 上的 KimiCU。GUI 子系统程序通过显式创建的子进程管道转发 MCP 协议字节，工具接入配置与目标程序的内存调整分别留档。

窗口 ID 从当前窗口列表取得，读取界面后再选择控件。下面是 KimiCU JS 环境中的按需截图流程：

```js
{
  const cu = (await import('@kimi/cu')).kimiCU;
  const window = await cu.get_window({ id: targetWindowId });
  const state = await cu.get_window_state({
    window, include_screenshot: false
  });
  // 先根据 state.accessibility 确认当前页面和控件。
  const image = await cu.get_window_state({
    window: state.window, include_screenshot: true
  });
}
```

本案 KimiCU 先报告 WGC（Windows Graphics Capture）创建 `GraphicsCaptureItem` 失败，随后 PrintWindow＋DwmFrame 回退得到 100% 近黑帧；普通页可正常截图。这组对照把问题指向页面保护，而不是 KimiCU 整体失效。

RDP 掉线时暂停键鼠输入，重连后重新观察窗口和控件；后台只读检查可以继续。

## <a id="native-evidence"></a>从程序文件定位防截屏和远程隐藏逻辑

### <a id="artifact-identity"></a>用 REA 和 objdump 检查程序副本

取得授权程序副本后，记录文件摘要、格式、架构和版本。本案检查了主程序、Chromium 核心库 `chrome.dll` 和早期启动库 `chrome_elf.dll`。

REA 完成 PE 头、节和资源检查，GNU objdump 用于选定函数的反汇编。下面沿用 REA 6.7.0 的 CLI；`REA_CLI` 指向已安装包的 `scripts/rea.mjs`，`CORE_DLL` 指向程序副本：

```bash
export REA_OBJDUMP_COMMAND="$(command -v objdump)"
node "$REA_CLI" inspect-with-objdump "$CORE_DLL" file_headers --format json
node "$REA_CLI" inspect-with-objdump "$CORE_DLL" section_headers --format json
objdump -p "$CORE_DLL"  # 查看导入、导出和 PE 数据目录
```

先通过字符串引用、注册表项和 PE `.pdata` 确定函数范围，再把首选虚拟地址填入下面的命令：

```bash
objdump -d -Mintel \
  --start-address="$FUNC_START_VA" \
  --stop-address="$FUNC_END_VA" "$CORE_DLL"
```

本案采用 REA 元数据检查与 GNU objdump 反汇编组合，函数语义由引用和指令控制流还原。

### <a id="registration-chain"></a>从扩展 API 追到隐藏网页的函数

用具名接口和错误文案作为锚点，逐段追踪：

```text
接口描述与参数类型
  → 名称对应的注册记录
  → 工厂与对象构造
  → 虚表处理入口
  → 参数解析与策略分支
  → 具体视图方法或系统 API
```

本案找到普通捕获保护和远程会话保护两条路径：

- **捕获保护**：选择传给 `SetWindowDisplayAffinity` 的参数。窗口查询返回 `0x11`，即 `WDA_EXCLUDEFROMCAPTURE`，对应受保护页面的捕获失败或黑帧。
- **远程显示保护**：根据保护状态和远程会话检测结果，对原生内容视图调用 `SetVisible(false)`，再填充主题背景，对应 RDP 中的白色区域。
- **业务页面**：恢复原生视图后，网页自身的登录弹窗继续显示，页面加载和业务登录沿用原有流程。

具体锚点是 `windows.setContentProtection` 与 `windows.setContentProtectionForRdp`。从 API 注册记录找到工厂，沿构造函数写入的虚表找到处理入口，再核对参数如何传给窗口接口。远程保护最终落在 `views::View::SetVisible`，涉及的内容视图类型是 `ContentsWebView`。

下面用 C++ 等价流程表达关键动作，字段名按用途命名：

```cpp
bool SetCaptureProtection(HWND hwnd, bool enabled) {
    return SetWindowDisplayAffinity(
        hwnd, enabled ? WDA_EXCLUDEFROMCAPTURE : WDA_NONE);
}

void ApplyRemoteVisibility(ContentsWebView& view,
                           bool other_hide, bool remote_detected) {
    view.SetVisible(!(other_hide || remote_detected));
    // 后续还会设置主题背景并安排重绘。
}
```

远程保护开关控制远程检测和会话通知；通知更新 `remote_detected` 后，调用上述显示逻辑。进入 RDP 后，保护逻辑可以在通知更新时再隐藏已经显示的页面。

### <a id="address-mapping"></a>把反汇编地址对应到运行进程

区分文件偏移、RVA、首选虚拟地址和运行地址：

```text
RVA = preferred_VA - preferred_image_base
live_address = loaded_module_base + RVA
file_offset = section_raw_offset + (RVA - section_virtual_address)
```

文件偏移公式用于对应节的原始数据范围。运行时重新取得模块基址；字符串、引用表项和函数入口分别标注。

Windows 上可从正在运行的进程取得核心模块基址和构建身份，`TargetPid` 为本次选定的进程：

```powershell
$p = Get-Process -Id $TargetPid
$modules = @($p.Modules | Where-Object ModuleName -eq 'chrome.dll')
if ($modules.Count -ne 1) { throw 'Expected one Chromium core module' }
$m = $modules[0]
[pscustomobject]@{
    ProcessStart = $p.StartTime.ToString('o')
    ModuleBase = ('0x{0:X}' -f $m.BaseAddress.ToInt64())
    ModuleSize = $m.ModuleMemorySize
    Version = $m.FileVersionInfo.FileVersion
    Sha256 = (Get-FileHash -LiteralPath $m.FileName -Algorithm SHA256).Hash
}
```

用 PE `.pdata` 中的异常展开信息约束反汇编范围，再核对尾调用、funclet、间接跳转和数据块。结合接口注册和具体调用点，确定函数的业务语义。

## <a id="bounded-runtime"></a>读取窗口的防截屏和显示状态

这一步回答两个现场问题：**Windows 是否把这个窗口排除在截图之外，以及客户端是否把网页视图隐藏了。**

先查询 Windows 的窗口设置。下面的 PowerShell 可直接作为只读探针：传入当前浏览器的 PID 和顶层窗口句柄，在同一个 Windows 登录会话里运行。

```powershell
param(
    [Parameter(Mandatory)][int]$TargetPid,
    [Parameter(Mandatory)][long]$Hwnd
)
$ErrorActionPreference = 'Stop'
if (-not ('WindowProtectionProbe' -as [type])) {
    Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class WindowProtectionProbe {
    [DllImport("user32.dll", SetLastError=true)]
    public static extern bool GetWindowDisplayAffinity(IntPtr h, out uint value);
    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll")]
    public static extern int GetSystemMetrics(int index);
}
'@
}
$p = Get-Process -Id $TargetPid
if ($p.SessionId -ne (Get-Process -Id $PID).SessionId) {
    throw 'Run this probe in the target desktop session'
}
[uint32]$owner = 0
[void][WindowProtectionProbe]::GetWindowThreadProcessId([IntPtr]$Hwnd, [ref]$owner)
if ($owner -ne $TargetPid) { throw 'Window owner changed' }
[uint32]$affinity = 0
if (-not [WindowProtectionProbe]::GetWindowDisplayAffinity([IntPtr]$Hwnd, [ref]$affinity)) {
    throw [ComponentModel.Win32Exception]::new(
        [Runtime.InteropServices.Marshal]::GetLastWin32Error())
}
[pscustomobject]@{
    Pid = $TargetPid
    SessionId = $p.SessionId
    Affinity = ('0x{0:X}' -f $affinity)
    RemoteSession = ([WindowProtectionProbe]::GetSystemMetrics(0x1000) -ne 0)
}
```

`Affinity=0x11` 表示 `WDA_EXCLUDEFROMCAPTURE`，`0x0` 表示 `WDA_NONE`。`GetSystemMetrics(SM_REMOTESESSION)` 给出当前会话的 RDP 状态，客户端还可能结合 WTS 通知更新自己的检测字段。

然后按静态分析确定的布局读取客户端状态：

```text
WindowControllerList → WindowController → Browser → Window → ContentsWebView
```

从已定位的全局注册容器出发，先匹配窗口 ID、虚表和 getter，再读保护开关、远程检测值及 `View::visible_`。本案读到的状态组合为：捕获保护开启、远程保护开启、远程检测为真、内容视图不可见。

读取进程数据使用 `OpenProcess(0x1010)`：`PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ`。地址由当前模块基址加已分析的 RVA 计算，成员偏移从当前构建的 getter 和构造函数确认。读取范围只覆盖这条对象链及其标量字段。

## <a id="runtime-adjustments"></a>在当前进程中修正远程显示和截图

### <a id="state-writeback"></a>直接改保护开关后的恢复与复发

最初仅调整少量运行字段，正常界面更新后一度恢复显示。客户端随后重新写入保护状态，问题复发，说明处理点需要上移到应用保护状态的控制流。

验证状态变化时，触发正常界面回调，同时检查字段、重绘和远程画面，定位保护重新生效的位置。

### <a id="code-change"></a>修改远程隐藏分支并保存回滚备份

在用户明确允许本地保护调整后，对已确定语义的远程隐藏判断做最小修正，使该条件落到显示路径，保留指令长度、位移、其他隐藏条件和普通捕获路径。

根据前导比较的标志位、输入字段值域和后继控制流选择修正点；每个构建分别定位和验证。

执行过程按事务处理：

1. 校验进程、创建时间、模块身份、对象类型、完整指令上下文和预期原值；不匹配即停止。
2. 写入前保存原字节与原页权限，备份绑定具体进程实例。
3. 临时调整现有映像页权限，以 `WriteProcessMemory` 写最小范围，回读校验并执行 `FlushInstructionCache`。
4. 恢复原页权限，再用 `VirtualQueryEx` 核验。权限恢复属于事务的一部分。
5. 异常时分别恢复并核对原字节和原权限；恢复入口同时支持仅恢复页权限。

调整复用现有代码页，目标进程保持运行，用户实际确认远程页面恢复。原值备份和恢复入口保留，便于按需撤销。

> 调整保存在当前进程中，磁盘程序和服务器策略保持原状；进程重启或更新后，按新实例重新定位和验证。

### <a id="capture-reapply"></a>允许截图并重新应用窗口设置

远程显示恢复后，单独处理普通截图保护。参数选择点的关键指令如下，`BL` 保存保护开关，`RDI` 保存窗口句柄：

```asm
xor    esi, esi
test   bl, bl
mov    eax, 0x11
cmovne esi, eax
mov    rcx, rdi
mov    edx, esi
call   [SetWindowDisplayAffinity]
```

开启保护时，`EDX` 取 `0x11`；关闭时取 `0`。本案调整立即数选择，使后续正常调用传入允许捕获的参数，再切换“普通页 → 受保护页”触发客户端回调，KimiCU 随即取得页面截图。RDP 的视图显示修正保持独立。

实际操作顺序为：保存参数原值 → 应用截图调整 → 切换已有标签 → KimiCU 取图 → 按需恢复原值 → 再切换标签重新应用。这样每一步都对应具体动作。

临时截图完成后，还原字节和页权限，通过正常设置路径重新应用保护，并查询到窗口亲和性恢复为 `0x11`。远程显示修正继续保留。

捕获参数决定后续调用，窗口亲和性保存已应用状态，因此验收覆盖以下对象：

| 层次 | 核对对象 |
|---|---|
| 代码 | 原指令或授权修改值的回读结果 |
| 内存映射 | 现有页的保护属性 |
| 系统状态 | 当前窗口的实际捕获亲和性 |
| 行为 | 对应页面的远控画面或截图 |

随后按使用需求将截图参数调整保留在当前进程中，沿用同一备份和恢复路径，供后续桌面自动化使用。

> 临时恢复脚本采用 ASCII 或带 BOM 的 UTF-8，并在创建任务前检查语法。任务优先按需启动，结束后核对恢复结果并注销，避免重复触发。

## <a id="recording-reporting"></a>检查录屏、诊断日志和上传功能

按能力、配置、执行和接收四个层次整理结果：

| 对象 | 实现与当前观察 |
|---|---|
| Chromium 屏幕采集与媒体编码 | 存在 `desktopCapture`、`tabCapture`、`getDisplayMedia`、`MediaRecorder` 和 WebRTC 相关实现 |
| `hasScreenRecord` 日志字段 | 抽取到的布尔值为假，字段定义和来源待核对 |
| 专用诊断 Capture 接口 | `startCapture`、`stopCapture`、`getStatus` 和 `uploadPackage` 已关联注册、工厂、处理函数和服务调用；场景为 `basic`、`trace`、`network` |
| `runtime.uploadLog` | `logType` 包括 `dmp`、`log`、`system`、`snapshot`；snapshot 分支关联标签与进程／对象调用，具体内容类型待核对 |
| 厂商诊断包 | 用 `SELECT msg FROM Logs WHERE tm >= ? AND tm <= ?` 取时段日志，再组装日志、转储、系统及设备信息 |
| 行为日志 | 现成日志提示“未开启行为日志上报” |
| Crashpad 崩溃报告 | 数据库全局非空，`uploads_enabled` 为真；所检查记录的最近上传尝试早于本次内存调整 |
| Chromium 企业事件报告 | `reportDataMaskingEvent` 经报告设置与 `sensitiveDataEvent` 允许集合门控；检查过 `enterprise_connectors.on_security_event` 等配置位置 |
| `chrome_elf.dll` 模块阻止 | `IsThirdPartyInitialized` 对应状态为真，`GetBlockedModulesCount` 和 `GetUniqueBlockedModulesCount` 对应计数为零 |
| Windows 本地安全事件 | 查询 Code Integrity、Defender 和 Application 日志，所查时段未发现明确关联本次调整的告警 |

Crashpad 使用 `settings.dat` 保存上传设置。对照随附的 `Settings::Data` v1 实现，40 字节结构的前 12 字节是 magic、version、options，`options` 的 bit 0 为上传允许位。下面只读这部分，`SettingsPath` 由调用者传入：

```powershell
param([Parameter(Mandatory)][string]$SettingsPath)
$ErrorActionPreference = 'Stop'
$s = [IO.File]::Open($SettingsPath, [IO.FileMode]::Open,
    [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
try {
    if ($s.Length -ne 40) { throw 'Unexpected Crashpad settings length' }
    $header = New-Object byte[] 12
    if ($s.Read($header, 0, 12) -ne 12) { throw 'Short header read' }
    $magic = [BitConverter]::ToUInt32($header, 0)
    $version = [BitConverter]::ToUInt32($header, 4)
    if ($magic -ne 0x43506473 -or $version -ne 1) {
        throw 'Crashpad settings format mismatch'
    }
    [pscustomobject]@{
        UploadsEnabled = (([BitConverter]::ToUInt32($header, 8) -band 1) -ne 0)
        BytesRead = 12
    }
} finally { $s.Dispose() }
```

> 格式依据：[Crashpad Settings 实现](https://github.com/chromium/chromium/blob/132.0.6834.210/third_party/crashpad/crashpad/client/settings.cc#L119-L144)。文件末尾的客户端标识保持不读；采用原始只读文件句柄，也避开了库 getter 在文件异常时的恢复写盘行为。

日志中的非终止式检查错误早于本次调整，按首见时间和来源归类。系统隐私许可历史记录了自动化工具的一次已结束捕获，本次桌面自动化采用按需单帧截图。

> 这轮确认了诊断和报告机制。当前录像活动、本次修改的检测／上传结果，以及加密扩展、外部安全代理和服务器记录，作为后续专项取证范围保留。

## <a id="rdp-transport"></a>远程连接检查

RDP 连接与客户端页面显示分别检查：

- 核对服务、真实监听、指定来源的 TCP 连接和回程路由。
- 按连接时段查询远程桌面及认证事件。
- 对回环地址发送无凭据的 X.224 协商，完成 TLS 握手后在 NLA 登录前结束。
- 测试自签证书时，校验回调仅用于探针自身，系统信任配置保持原状。

本案服务、监听、回程路由和回环协商检查通过，RDP 重新连接后恢复访问，原客户端进程和登录继续保留。

## <a id="case-results"></a>远程显示与截图的处理结果

- 通过静态调用链、运行字段和远程画面对照，定位到原生视图隐藏保护，恢复了 RDP 中的页面显示。
- 独立调整窗口捕获参数取得目标页面截图，完成原保护的恢复查询，随后按需求保留当前进程的截图参数调整。
- 还原了诊断打包、报告门控、崩溃上传配置及模块阻止实现，并与运行状态对照。
- 临时任务已注销，原始证据、恢复备份和工具桥接配置保留。

知识库保存机制、步骤和结果；目标专用补丁、原始日志与截图留在任务私有材料中。
