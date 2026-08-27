# Windows 与 Office 激活

Windows 和 Office 的授权都由同一套 Software Protection Platform（SPP，微软的许可证校验组件）管理，所以绕过它的工具往往同时覆盖两者，但每种机制支持的产品、是否需要联网、能维持多久各不相同。下面先讲安装介质和工具从哪来，再按 Windows、Office 两侧分别说明各机制的原理与边界，最后单列国内网络的可达性和 macOS 的独立路线。

> 第三方激活工具绕过的是微软的许可证校验，使用它们可能违反微软的软件许可条款。KMS 与批量许可（VL）本身是微软面向组织客户的正规授权机制，只有在所属组织确实持有相应批量许可证时，使用它才属于授权范围内的行为。

## <a id="media"></a>安装介质与激活工具

激活之前先得有安装介质。介质来源分微软官方和第三方索引两类，后者的价值在于汇总了微软 CDN 上已经下架或不便检索的历史版本。

微软官方渠道有三个：

- [Windows 10 / 11 下载页](https://www.microsoft.com/en-us/software-download)：面向个人的常规发布通道（GAC）ISO 与介质创建工具。
- [Visual Studio 订阅者下载](https://my.visualstudio.com/Downloads)：订阅者可取企业版、LTSC 等零售页面没有的版本。
- [Microsoft 365 应用配置中心](https://config.office.com/)：生成 Office 部署工具（ODT）的配置文件，据此从微软 CDN 按通道和版本拉取 Office 安装包。

MAS 自己也带一个介质入口：主菜单 `[E] Extras` → `[2] Download Genuine Windows / Office`，会打开官方整理的[正版安装介质页](https://massgrave.dev/genuine-installation-media)。该页说明了一个容易踩的区分：Windows 10/11 常规发布通道的 ISO 分 Consumer 和 Business 两种，Consumer 版含 Home、Pro、Education 但不含 Enterprise，Business 版含除 Home 系列外的全部版本且默认预置一枚（未激活的）KMS 密钥。选错会出现"想装的版本不在镜像里"。

第三方索引有两个：

- [山己几子木](https://msdn.sjjzm.com/)：Windows / Office 原版镜像索引。下载渠道按页面不同——Windows 各版本页提供阿里云盘、腾讯微云、百度网盘、天翼云、移动云、ed2k 和 BT 磁力，而 [Office 页](https://msdn.sjjzm.com/office.html)只有 ed2k、阿里云盘、迅雷和 BT 磁力，没有其余网盘。
- [rg-adguard](https://msdn.rg-adguard.net/) 及其[文件索引](https://files.rg-adguard.net/search)：按产品、版本、语言检索微软 CDN 的原始下载链接。

> 渠道差异为实测 `win11.html` 与 `office.html` 所得，2026-08-26。第三方索引给出的多是指向微软 CDN 的原始链接或其镜像，落地后应核对哈希。

激活工具本身有三个，分属不同平台：

| 工具 | 最新版本 | 支持产品 | 平台 | 机制 | 许可 |
|---|---|---|---|---|---|
| [MAS (Microsoft Activation Scripts)](https://massgrave.dev/) | 3.12（2026-07-04） | Windows、Office、ESU | Windows | HWID、Ohook、TSforge、Online KMS | GPL-3.0 |
| [CMWTAT Digital Edition](https://github.com/TGSAN/CMWTAT_Digital_Edition) | 3.0.1.0（2026-08-03） | 仅 Windows 10/11 | Windows | 数字许可证，与 HWID 同类 | GPL-2.0 |
| [Microsoft Office For MacOS](https://github.com/alsyundawy/Microsoft-Office-For-MacOS/) | 16.112（2026-08-14） | 仅 Office | macOS | VL Serializer（批量许可证序列化） | 仓库未声明 |

> 版本与许可取自各仓库 GitHub API 的 `releases/latest` 及仓库元数据，2026-08-26 核，三者当时均未归档。MAS 版本以 GitHub Release tag 和[官网首页](https://massgrave.dev/)为准——tag 3.12 的 README 内嵌文字仍写着 3.11，是上游未同步的笔误。

## <a id="mas-launch"></a>MAS 的启动与主菜单

MAS 是一个批处理脚本，官方给了在线和离线两条获取路径，拿到的是同一个 `MAS_AIO.cmd`。

在线方式面向 Windows 8.1 / 10 / 11，打开 PowerShell 后执行：

```powershell
irm https://get.activated.win | iex
```

`irm`（Invoke-RestMethod）负责下载，`iex`（Invoke-Expression）负责执行。官方步骤只要求"打开 PowerShell"，并不要求手动选"以管理员身份运行"——脚本内部用 `fltmc` 检测权限，非管理员时自行以 `-verb runas` 触发 UAC 提权，只有提权失败时才提示手动右键管理员运行。

域名被 ISP 或 DNS 拦截时，官方备用命令改走 DNS-over-HTTPS：

```powershell
iex (curl.exe -s --doh-url https://1.1.1.1/dns-query https://get.activated.win | Out-String)
```

较旧的 Windows 8.1 / 10 build 若报 TLS/SSL 错误，官方要求先跑一句再执行主命令：

```powershell
[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
```

`irm` 与 `[ScriptBlock]::Create()` 都是 PowerShell 的东西，CMD 里没有，所以这条命令必须在 PowerShell 窗口里跑。

离线方式适用于 Windows Vista 及以后：从 Azure DevOps 镜像下载 [`MAS_AIO.cmd`](https://dev.azure.com/massgrave/Microsoft-Activation-Scripts/_apis/git/repositories/Microsoft-Activation-Scripts/items?path=/MAS/All-In-One-Version-KL/MAS_AIO.cmd&download=true) 直接运行，浏览器拦截 `.cmd` 时改下 [`MAS_AIO.zip`](https://dev.azure.com/massgrave/Microsoft-Activation-Scripts/_apis/git/repositories/Microsoft-Activation-Scripts/items?$format=zip)。脚本落地之后，Ohook 与 TSforge 的激活过程不再需要网络。

> 命令与链接取自 [tag 3.12 的 README](https://github.com/massgravel/Microsoft-Activation-Scripts/blob/3.12/README.md)。旧命令 `irm https://massgrave.dev/get | iex` 已退役——实测该 URL 现在返回的是一段打印"命令已退役、请访问官网获取新命令"的 PowerShell 代码，不再执行激活（2026-08-26 实测）。

官方认可的入口只有下面几个。README 明确警告有人通过**篡改 PowerShell 命令里的 URL** 传播伪装成 MAS 的恶意软件，执行前核对域名是官方给出的唯一判别手段：

| 入口 | 用途 |
|---|---|
| `https://massgrave.dev/` | 官网与文档 |
| `https://get.activated.win` | PowerShell 方式的脚本下载端点 |
| `https://github.com/massgravel/Microsoft-Activation-Scripts` | GitHub 主仓库 |
| `https://dev.azure.com/massgrave/_git/Microsoft-Activation-Scripts` | Azure DevOps 镜像，离线方式的下载源 |
| `https://git.activated.win/Microsoft-Activation-Scripts` | 自托管 Git 镜像 |

杀毒软件把激活工具判为恶意是常见误报。官方 FAQ 分两种情况处理：使用上述 PowerShell 命令或官方离线下载链接时，**Windows Defender 不会触发告警**；第三方杀软告警则**添加排除项**，或改用手动激活步骤。官方没有建议关闭实时防护。

> 见 [MAS FAQ 中关于杀软误报的条目](https://massgrave.dev/faq)，2026-08-26 读。

脚本启动后进入主菜单，当前系统支持的机制显示为绿色，不支持的显示为普通白色（例如 Server 版不会把 HWID 显示成绿色）：

| 按键 | 选项 | 覆盖范围 |
|---|---|---|
| `[1]` | HWID | Windows |
| `[2]` | Ohook | Office |
| `[3]` | TSforge | Windows / Office / ESU |
| `[4]` | Online KMS | Windows / Office |
| `[5]` | Check Activation Status | 查看激活状态 |
| `[6]` | Change Windows Edition | 切换 Windows 版本 |
| `[7]` | Change Office Edition | 切换 Office 版本 |
| `[8]` | Troubleshoot | 排障 |
| `[E]` | Extras | `$OEM$` 文件夹提取、正版介质下载 |
| `[H]` | Help | 跳转官方文档 |
| `[0]` | Exit | 退出 |

验证结果用 `[5] Check Activation Status`：它是内嵌的 PowerShell 工具，查询 WMI 的 `SoftwareLicensingProduct`，并额外检测 Ohook 的 `sppc.dll` 是否就位，分 Windows 和 Office 两块输出。

> 菜单条目与状态检查的实现读自 [tag 3.12 的 `MAS_AIO.cmd`](https://github.com/massgravel/Microsoft-Activation-Scripts/blob/3.12/MAS/All-In-One-Version-KL/MAS_AIO.cmd) 的 `:MainMenu` 与 `:check_actstatus` 两节，2026-08-26。官方面向用户的文档没有把 `cscript ospp.vbs /dstatus` 或 `slmgr` 当作验证手段推荐，`ospp.vbs` 在脚本里仅用于探测 `OSPPC.DLL` 路径。

需要无人值守时，把开关直接附在一行式调用后面即可，脚本收到任何开关就转入非交互模式：

```powershell
& ([ScriptBlock]::Create((irm https://get.activated.win))) /Ohook
```

末尾的开关可以叠加多个（如 `/HWID /Ohook`），不分大小写、顺序任意，空格分隔：

| 开关 | 作用 |
|---|---|
| `/HWID` | 用 HWID 激活 Windows |
| `/Ohook`、`/Ohook-Uninstall` | 安装 / 卸载 Ohook |
| `/Z-Windows`、`/Z-Office`、`/Z-ESU` | TSforge 只激活对应目标 |
| `/Z-SCID`、`/Z-ZCID`、`/Z-KMS4k` | 强制指定 TSforge 子机制 |
| `/Z-Reset` | 重置 rearm 计数与评估期，清除 tamper 状态和 key lock |
| `/K-Windows`、`/K-Office` | Online KMS 只激活对应目标 |
| `/K-Server-<名称>`、`/K-Port-<端口>` | 指定 KMS 服务器与端口 |
| `/K-NoRenewalTask` | 不安装续期计划任务 |
| `/K-Uninstall` | 卸载 Online KMS 及其续期任务 |
| `/HWID-NoEditionChange`、`/K-NoEditionChange` | 禁止脚本为激活而改动版本 |
| `/S` | 静默运行，但 CMD 窗口仍会出现 |

> 完整开关表见[命令行开关页](https://massgrave.dev/command_line_switches)，2026-08-26 读。`/S` 只在该页 Rules 一节提及，且对 MAS 的分离文件版不适用；同一节还残留着一条关于 KMS38 的说明，属旧文字未清理。

## <a id="windows-methods"></a>Windows 的激活机制

Windows 侧可用 HWID、TSforge、Online KMS 三种，另有 CMWTAT 作为数字许可证机制的独立实现。它们在"许可证存到哪里"这一点上根本不同，这决定了各自的持久性和能否撤销：

| 机制 | 按键 | 适用范围 | 联网 | 持久性 | 移除 |
|---|---|---|---|---|---|
| HWID | `[1]` | Windows 10 / 11 | 需要 | 永久 | 不可移除 |
| TSforge | `[3]` | Windows 8 及以后、ESU | 取决于子机制，build 26100 及以后默认走需联网的 StaticCID | 到重装或大版本功能升级为止 | 子菜单内 |
| Online KMS | `[4]` | 可批量激活的版本 | 需要 | 180 天，装续期任务后可持续 | 子菜单 `[7]` |
| CMWTAT | 不适用 | Windows 10 / 11 | 需要 | 永久 | 不可移除 |

**HWID**（Hardware ID）把设备硬件指纹与一张数字许可证在微软服务器端绑定。因为许可证存在微软那边而不是本机，重装系统后只要硬件没有大改，联网即自动重新激活；同样因为这一点，**HWID 激活无法移除**——微软查到该硬件 ID 名下有许可证就会自动激活。它只适用于 Windows 10 和 11，对 Office 完全无效。

> HWID 与 CMWTAT 的"需要联网"是由机制推出的：许可证在服务器端签发与存放，登记和回查都得联网。官方对比表中 HWID 对 Office 2010 与 Office 2013 及以后两栏均标为不支持（[chart](https://massgrave.dev/chart)，2026-08-26 读）。

一个容易忽略的副作用：**遇到不支持目标机制的版本时，脚本默认会把系统或 Office 的版本（edition）改成最接近的可激活版本**，而不是直接失败。不希望它擅自改版本，就用 `/HWID-NoEditionChange` 或 `/K-NoEditionChange`。

**TSforge** 直接伪造 SPP 的缓存数据，把"已经验证过"的结果写进本机存储，因而不必与微软通信。它含三个子机制：

- **ZeroCID**：向物理存储（`data.dat`）和令牌存储（`tokens.dat`）写入伪造的密钥与确认 ID 缓存，同时把硬件 ID 的变更阈值设为 0 以绕过硬件变化检查。离线可用。
- **KMS4k**：把伪造的 KMS 服务器响应写进可信存储，可将激活到期时间设到最大 2147483640 分钟，约 4083 年。离线可用。
- **StaticCID**：先把安装 ID 设成一个已知可生成合法确认 ID 的值，再通过 VAMT API 联网换取真实确认 ID。需要联网，且在 Windows 7 及更早版本上不可用。

这三者由脚本自动选择：build 低于 26100 用 ZeroCID；build 26100 及以后默认用 StaticCID，检测不到网络时回落 KMS4k。**两个阈值不是一回事**——自动切换的分界是 26100，而 ZeroCID 真正失效的分界是 26100.4188，落在两者之间时 ZeroCID 技术上仍可用、只是已不是默认。要绕过自动选择就用 `/Z-SCID`、`/Z-ZCID`、`/Z-KMS4k` 强制指定。其中 **KMS4k 只对批量许可（Volume）有效**，零售版产品用不了它，这一点在 Office 上尤其要紧。

另有一个 AVMA4k 属于概念验证、限制很多，**MAS 并不包含它**。TSforge 的激活维持到重装系统或大版本功能升级为止，月度累积更新和小的启用包不影响。

> 子机制与自动选择规则取自 [TSforge 文档](https://massgrave.dev/tsforge)与[命令行开关页](https://massgrave.dev/command_line_switches)，2026-08-26 读。此处有一处上游文档自身的不一致：3.12 的 changelog 称纯 Windows 选项的默认已从 StaticCID 改为 KMS4k（理由是 KMS4k 不需联网、换硬件后仍有效），而命令行开关页仍写着 26100 及以后默认 StaticCID。

> 早期版本另有一种叫 KMS38 的方式（把激活期延到 2038 年），已在 MAS 3.8（2025-11-11）从菜单移除：官方 changelog 说自 build 26100.7019 起微软废弃了 clip-based KMS 许可迁移功能，KMS38 随之失效，并建议改用 HWID 或 TSforge。仍在推荐 KMS38 的教程都已过时。

**Online KMS** 让本机冒充企业批量授权客户端去连一台 KMS 主机，只对可批量激活的版本有效。单次有效期 180 天；脚本可安装一个名为 `Activation-Renewal` 的计划任务（落在 `C:\Program Files\Activation-Renewal\`，每周触发），只要能连上 KMS 主机就每 7 天续一次，从而长期维持。加 `/K-NoRenewalTask` 参数可以不装这个任务。卸载走 KMS 子菜单的 `[7] Uninstall Online KMS`。它连的是社区维护的第三方公共 KMS 服务器，清单见[国内直连的可达性](#cn-reachability)。

**CMWTAT** 是数字许可证机制的另一个实现，图形界面，只做 Windows 10 / 11，不涉及 Office。它与 MAS 的 HWID 拿到的是同一类结果，因此同样不可撤销；需要图形界面而非命令行时可以用它。

官方文档没有"不要同时使用多种机制"的警告，反而在 `[E] Extras` 的 `$OEM$` 文件夹提取子菜单里预置了组合方案：`[5]` HWID（Windows）+ Ohook（Office）、`[6]` 在此基础上加 TSforge（ESU）、`[7]` TSforge（Windows / ESU）+ Ohook（Office）。即 Windows 与 Office 各用一种机制，是官方预期的常规搭配。

> `$OEM$` 是 Windows 无人值守安装中存放随系统一起部署文件的目录，这些预置项面向装机时自动激活的场景。组合清单读自 tag 3.12 的 `MAS_AIO.cmd`，2026-08-26。

## <a id="office-methods"></a>Office 的激活机制

Office 侧可用 Ohook、TSforge 和 Online KMS 三种，HWID 与 Office 无关。三者支持的 Office 版本并不重叠，其中商店版（UWP）和 Microsoft 365 订阅版这两类，恰好被 Ohook 和 TSforge 分别排除和覆盖：

| 机制 | 按键 | 支持的 Office 版本 | 商店版（UWP） | 联网 | 持久性 |
|---|---|---|---|---|---|
| Ohook | `[2]` | 2010、2013、2016、2019、2021、2024、Microsoft 365 | 不支持 | 不需要 | 永久，扛得住修复与更新 |
| TSforge | `[3]` | 2013 及以后，需 Windows 8+；不含 Microsoft 365 订阅版 | 支持 | 取决于子机制，KMS4k 另限批量许可 | 到重装或大版本功能升级为止 |
| Online KMS | `[4]` | 可批量激活的版本，零售版由脚本自动转换 | 未明说，按"仅批量许可"推断为否 | 需要 | 180 天，装续期任务后可持续 |

**Ohook** 的做法是在 Office 的安装目录里放一个自定义的 `sppc.dll`，让 Office 查询许可证状态时拿到"已激活"的答复，**系统目录下的 `C:\Windows\System32\sppc.dll` 不被改动**；该 DLL 的源码在 [asdcorp/ohook](https://github.com/asdcorp/ohook)。因为改的是 Office 自己的目录，Ohook 必须**先装好 Office** 才能施加。它同时支持零售版和 MAK 批量版的密钥类型，全程离线，官方明确它能扛住 Office 的修复、更新乃至 Windows 大版本功能升级，无需重新激活。Microsoft 365 也在支持范围内，但依赖服务端的功能（例如 1TB OneDrive 存储）不会因此可用。唯一的例外是从 Microsoft Store 安装的 Office：官方原话是支持"Windows Vista 及以后的所有 Office 版本，Office UWP 应用除外"，这类安装形态需改用 TSforge。移除走 Ohook 子菜单的卸载项。

> 原理与支持范围见 [Ohook 文档](https://massgrave.dev/ohook)与[机制对比表](https://massgrave.dev/chart)，2026-08-26 读。官方保证的范围是修复、更新和 Windows 大版本升级；**完整卸载再装 Office** 会连同 Office 目录里的 `sppc.dll` 一起清掉，因此需要重跑 Ohook——这一条官方未明说，是由机制推出的。

**TSforge** 的原理见 [Windows 的激活机制](#windows-methods)，此处只讲它用在 Office 上的边界：支持 Office 2013 及以后且要求系统为 Windows 8 或更高，**不支持 Office 2010**，但**支持商店版（UWP）Office**——这一点正好与 Ohook 互补。对 Microsoft 365，它并非报错退出，而是**改装一张 Mondo 2016 的电话激活许可**（官方称其功能上等同于 365）来完成激活，官方对这种情形直接建议改用 Ohook。另外它的 KMS4k 子机制只吃批量许可，零售版 Office 走不通。

> 版本限制来自机制对比表中 TSforge 对 Office 2013+ 一栏的脚注："Supported only on Windows 8 and later; subscription editions are not supported."；Mondo 2016 的处理见 [TSforge 文档](https://massgrave.dev/tsforge)的 Unsupported Products 一节（2026-08-26 读）。

**Online KMS** 在官方对比表里写作"仅限可批量激活的版本"。零售版并不会因此直接失败——MAS 的激活流程内置了零售版到批量版的转换，执行时会打印 `Converting Retail To Volume`，无需手动操作。180 天有效期、每 7 天自动续期的计划任务以及卸载入口，与 Windows 侧相同。

> 转换行为读自 tag 3.12 的 `MAS_AIO.cmd` 中 `:KMSActivation` 一节打印 `Converting Retail To Volume [...]` 的分支，2026-08-26。官方文档只写了"Volume activation capable editions only"，没有单独说明这个自动转换，两者的出入以脚本实际行为为准。

## <a id="cn-reachability"></a>国内直连的可达性

MAS 的网络依赖只有两处：下载脚本，以及 Online KMS 激活与续期时连 KMS 主机。Ohook 与 TSforge 的 ZeroCID / KMS4k 在脚本落地后完全离线，不受网络影响。

`massgrave.dev` 与 `get.activated.win` 都指向 GitHub Pages（`185.199.108.153`、`185.199.109.153`、`185.199.110.153`、`185.199.111.153`）。**有设备实测从国内直连可通**，并非必须挂代理；但这组共享 CDN 地址在各地区、各运营商的表现不一致，官方 README 本身也把"部分 ISP / DNS 屏蔽我们的域名"列为已知情况，并为此准备了走 DNS-over-HTTPS 的备用命令，以及"在浏览器里开启 DoH"的建议；主页还进一步建议实在连不上就用 Cloudflare WARP 一类 VPN，不过这条建议针对的是普通 ISP / DNS 屏蔽，WARP 本身在国内是否可用是另一回事，不宜直接当作国内解法。实际操作以在目标机器上试一次为准；不通再考虑 DoH 备用命令、自己可用的代理，或在能联网的机器上下好 `MAS_AIO.cmd` 拷过去。

> 域名解析结果由 DoH 查询取得，可达性为实测，均为 2026-08-26。GitHub Pages 是共享 CDN 地址，可达性随时间和网络环境变化，此处不作长期结论。

Online KMS 的服务器是脚本内置的一份社区维护清单，每次激活随机选一个，并且先把域名解析成 IPv4 再使用——脚本注释给出的理由是直接使用公共 KMS 主机名容易被微软和杀软标记。清单中多数主机在国内，因此 Online KMS 的网络条件通常好于下载环节：

```
kms.03k.org           kms-default.cangshui.net  kms.sixyin.com
kms.moeclub.org       kms.cgtsoft.com           kms.idina.cn
kms.moeyuuko.com      xincheng213618.cn         kms.loli.best
kms.mc06.net          kms.0t.net.cn             win.kms.pub
kms.wxlost.com        kms.moeyuuko.top          kms.ghxi.com
```

另有一个兜底 IP `222.184.9.98`。

> 清单读自 tag 3.12 的 `MAS_AIO.cmd` 中 `srvlist` 变量，源码经混淆需反混淆后阅读，2026-08-26。这些是第三方社区服务器、不受 MAS 控制，随版本更新会变动，使用前应以当时脚本内的清单为准。

## <a id="macos-vl"></a>macOS 上的 Office 批量许可证

macOS 上没有 MAS 这类脚本，走的是另一条路：Office 安装包本身从微软官方 CDN 下载，真正起激活作用的只有一个批量许可证序列化器（VL Serializer）——它是微软给批量授权客户提供的正式组件，作用是把机器标记为批量许可证用户。[alsyundawy/Microsoft-Office-For-MacOS](https://github.com/alsyundawy/Microsoft-Office-For-MacOS/) 做的事情，是把这两类包的官方直链按版本整理出来。

顺序不能颠倒：

1. 下载对应版本的序列化器，`Microsoft_Office_LTSC_2021_VL_Serializer.pkg` 或 `Microsoft_Office_LTSC_2024_VL_Serializer.pkg`。
2. 运行序列化器 pkg，应用批量许可证。
3. 下载与本机 macOS 版本匹配的 Office 套件安装包。
4. 运行套件 pkg 完成安装，此时应用已处于激活状态。

已经装过序列化器的机器再升级 Office 时只需装更新包，不必重复第一步。

套件版本与 macOS 版本有明确对应关系，装错会因最低系统要求不满足而失败：

| Office 套件 | 版本（构建号） | 适用 macOS |
|---|---|---|
| Office LTSC 2021 / 2024 | 16.112（26081010） | macOS 14 (Sonoma) 及以上 |
| Office LTSC 2021 / 2024 | 16.101（25091314） | 至 macOS 13 (Ventura) |
| Office 2019 / LTSC 2021 | 16.89.2（24091630） | 至 macOS 12.7.6 (Monterey) |
| Office 2019 / LTSC 2021 | 16.77（23091003） | 至 macOS 11 (Big Sur) |
| Office 2019 / LTSC 2021 | 16.66（22100900） | 至 macOS 10.15 (Catalina) |
| Office 2019 | 16.54（21101001） | 至 macOS 10.14 (Mojave) |
| Office 2019 | 16.43（20110804） | 至 macOS 10.13 (High Sierra) |
| Office 2016 | 16.16.27 | macOS 10.10 (Yosemite) 及以上 |

> 安装顺序与版本对应取自该仓库 README，对应 release 16.112（2026-08-14），2026-08-26 读。套件安装包链接指向 `officecdn.microsoft.com` 与 `go.microsoft.com`，即微软自己的分发地址；仓库另提供 Microsoft AutoUpdate (MAU) 安装包，以及 Office 2011 等更早的历史版本。
