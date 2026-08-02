# 设备侧取数通道：adb / Shizuku / HDC / ANCO

## <a id="channel-overview"></a>通道概览

把 App 的私有数据（存档、配置）从设备取出，是重打包保存类工作的前置条件。重签名包不能覆盖安装到原签名应用的位置，通常要先卸载；卸载会删除私有数据，因此必须先完成取数。

`无 root 真机` 是最常见、也最受限制的场景：

| 通道 | 能读任意 App 私有目录吗 | 限制 |
|---|---|---|
| `adb shell`（无 root） | **不能** | 进程是 uid=2000(shell)，被 DAC 与 SELinux 拦截 |
| `adb root`（模拟器 / userdebug 构建） | 能 | 正式用户版拒绝，报 `adbd cannot run as root in production builds` |
| Shizuku（ADB 模式） | **不能** | 同样是 uid=2000；官方明确说明不能读取 |
| Shizuku（root 模式） | 取决于 SELinux | 需要已 root 的设备；官方没有给出明确结论 |
| `adb backup` | 受应用清单控制 | 依赖 `allowBackup=true`，且已在新版 Android 上废弃 |
| 鸿蒙 HDC | **不能** | 同为 uid=2000，ANCO 容器还增加了一层隔离 |
| 厂商备份 / 云备份 | 取决于实现 | 实测某鸿蒙壳应用的备份不含内层 Android 应用数据 |

## <a id="private-data-paths"></a>私有数据的位置与权限模型

Android 应用私有目录有两个等价写法，指向同一位置：

```text
/data/user/0/<package>/          # 多用户体系下的规范路径
/data/data/<package>/            # 主用户的传统别名
```

目录中通常包含 `files/`（应用自行写入的文件，存档多在这里）和 `shared_prefs/`（XML 形式的键值偏好）。

无法读取并不只是"没有打开某个权限"，而是两层机制共同作用：

- **DAC（自主访问控制，即 Unix 的属主与权限位）**：每个应用安装后获得专属 uid，私有目录归该 uid 所有，其他 uid 会被直接拒绝。
- **SELinux MAC（强制访问控制，在 DAC 之上再次判断）**：即使 uid 匹配，安全上下文不匹配仍会拒绝访问。

`adb shell` 进程的身份是 **uid=2000(shell)**，两层条件都不满足。因此，打开 USB 调试后仍出现 `permission denied` 并不矛盾：调试授权给的是 shell 身份，不是目标应用的数据访问权。

## <a id="adb-routes"></a>adb 权限、备份与恢复

### <a id="adb-root"></a>`adb root` 的构建限制

`adb root` 只在模拟器和 userdebug / eng 构建中可用。可用时可以在 `adb root` 后直接用 `adb pull` / `adb push` 访问私有目录。正式零售固件在编译 `adbd` 时就禁用了这条路径；执行失败不是权限没有配置好。

### <a id="adb-backup"></a>`adb backup` 的适用范围

`adb backup` 依赖应用自行允许备份。清单中的 `android:allowBackup` 为 `false` 时，框架会直接拒绝；即使为 `true`，`adb backup` 在较新的 Android 上也已标记废弃，不少厂商实现中已经不可用，或只能备份系统数据。

> 来源边界：`allowBackup` 与 `adb backup` 的废弃属于 Android 平台政策，不在 Shizuku 等第三方项目的文档范围内；本条按平台公开行为陈述，具体到某设备某版本是否还能用，需实机验证。

### <a id="restore-ownership"></a>文件恢复的属主与权限

恢复通常比备份更容易出错。把文件放回私有目录时：

- 逐个覆盖文件，不要替换整个应用数据目录。
- 文件属主必须与应用新生成的文件一致，权限通常为 `0600`。**属主错误的典型症状是应用把存档当作不存在**：它不报错、不崩溃，而是直接建立新档，很容易被误判为存档格式不兼容。
- 先启动新安装的应用一次，再强制停止，让应用自行创建私有目录并确定属主；之后再放回文件。

## <a id="shizuku"></a>Shizuku 的能力边界

Shizuku 常被当成"无 root 提权"的通用方案，但在 ADB 模式下，它解决不了读取其他应用私有数据的问题。

### <a id="shizuku-model"></a>身份与调用模型

Shizuku 引导用户以 root（uid=0）或 ADB / shell（uid=2000）身份启动常驻服务，再把该服务的 Binder 句柄分发给集成 Shizuku SDK 的应用。应用通过句柄让高权限进程**代为调用系统 API**，替代"启动 su 子进程并解析文本输出"的旧路径。

> 官方定义："With Shizuku API, you can call your Java/JNI code with root/shell (ADB) identity." —— [Shizuku-API README](https://github.com/RikkaApps/Shizuku-API/blob/a27f6e4151ba7b39965ca47edb2bf0aeed7102e5/README.md)

### <a id="shizuku-adb-limit"></a>ADB 模式的文件访问限制

官方文档在比较 ADB 与 ROOT 权限时明确写道：

> "In the Linux world, the privilege is determined by Shell's uid, capabilities, SELinux context, etc. For example, **Shell (ADB) cannot access other apps' data files `/data/user/0/<package>`**." —— [Shizuku-API README，"Differents of the privilege betweent ADB and ROOT"](https://github.com/RikkaApps/Shizuku-API/blob/a27f6e4151ba7b39965ca47edb2bf0aeed7102e5/README.md)

原因与 `adb shell` 相同：ADB 模式的 Shizuku 服务本身就是 uid=2000，并没有更高的 Linux 文件权限。Shizuku 扩展的是**可调用的系统 API**——shell 身份拥有 `INSTALL_PACKAGES`、`WRITE_SECURE_SETTINGS`、`FORCE_STOP_PACKAGES` 等特殊 Android 权限——而不是**可读取的文件范围**。这两类能力不能混为一谈。

### <a id="shizuku-integration"></a>接入、会话与 root 模式

- **调用方应用必须自行集成 Shizuku SDK**（指想要提权的那个应用，不是被取数的应用）：加入依赖、在清单中声明 `ShizukuProvider`，并完成类似运行时权限的授权流程。不能拿 Shizuku 直接操作没有适配的第三方应用；这也排除了"用 Shizuku 取出一个停服老游戏存档"的设想。
- **通过 ADB 启动的会话重启后失效**，每次开机都要重新启动。Android 11+ 可使用系统无线调试直接在设备上完成，无需连接电脑；root 用户可以改用 Magisk 模块 Sui，使其开机自动生效。
- **root 模式（uid=0）是否能读取私有目录，官方没有给出明确说明**。uid=0 通常能绕过 DAC，但 Android 的 SELinux enforcing 对 root 仍有限制，因此这一项只能标为"未知"，需要实测。

> 版本口径：以上依据 Shizuku [v13.6.0](https://github.com/RikkaApps/Shizuku/releases/tag/v13.6.0)（2025-05-25）及同期 Shizuku-API 文档；要求 Android 6.0+。**本条整节未在本地环境实测**，是照官方文档整理的能力边界。

## <a id="hdc"></a>鸿蒙 HDC 与 ANCO 容器边界

> 实测快照：HarmonyOS DataBackup 6.1.0.110、卓易通 1.0.10.60，正式用户版（非可调试构建）。本节及以下均由实机操作与解密验证。

HDC（HarmonyOS Device Connector）是鸿蒙的设备调试协议，能力类似 Android ADB。定义与命令见[OpenHarmony HDC README](https://github.com/openharmony/developtools_hdc/blob/5a8e35d0299f19ce9adac8b54756c5b8be58b9ff/README_zh.md)。

### <a id="anco-storage"></a>容器数据位置

在卓易通一类 ANCO 环境中，鸿蒙应用只是**容器管理器**；Android 应用及其私有数据位于内层 LXC / iSulad 容器。宿主可能把数据映射到：

```text
/mnt/data/ANCO_APP_DATA/<android-package>/
```

`mountinfo` 中能看到挂载，只能证明路径存在，不能证明当前身份有权读取。看到路径就认为数据已经可取，是最容易发生的误判。

### <a id="hdc-access"></a>HDC 访问限制

实测存在以下访问边界：

- HDC shell 身份是 `uid=2000(shell)`；即使附带 `file_manager` 组，目录遍历仍会被 ANCO / SELinux 拒绝。
- `hdc file recv` 虽由 daemon 代为读取，仍会遇到同一个 `permission denied`；更换传输命令绕不过权限边界。
- 正式用户版拒绝 `hdc smode`，并提示设备不是可调试构建。
- 容器网络没有开放常见的 Android ADB 端口。

### <a id="protocol-identification"></a>协议识别

端口可达不等于协议可用。曾经根据"某内网地址上有端口开放"推断它是 ADB / HDC 服务，事后确认该地址只是虚拟组网分配的地址；端口开放只说明经组网可达，与实际协议无关。只有匹配 HDC 协议并完成设备侧授权，才能建立 shell。

## <a id="host-backup-scope"></a>宿主备份的覆盖范围

在华为「数据备份 → 外部存储」中勾选卓易通，得到的是**卓易通这个 HarmonyOS bundle 自身的备份**。解密后的 TAR 成员只有：

```text
/data/storage/el2/base/files/...
/data/storage/el2/base/haps/<module>/...
```

其中没有 `/mnt/data/ANCO_APP_DATA/`、Android 包名或内层应用存档；本案例需要的 `WUD_Default.bin` 完全不在其中，对成员内容做全文扫描也找不到相关引用。

**"备份成功"与"目标数据已进入备份"是两个独立结论。** 应用出现在备份列表中、备份包体积非零，都不能推出目标数据已经被包含。唯一可靠的验证方式是解密备份、列出 TAR 成员，并确认目标文件确实存在。

## <a id="hmosbackup-crypto"></a>HMOSBackup 6.1 加密格式

外部存储备份会话包含一个顶层 `.info.json`；每个模块有各自的 `.info.json`、`manage.json` 和 `part.0.tar`。以下是 `encryptionType=2` 的完整解密链。

### <a id="outer-key"></a>外层备份密钥

```text
wrapKey = PBKDF2-HMAC-SHA256(
  password   = UTF-8 password,
  salt       = Base64Decode(backupSalt),
  iterations = 10000,
  length     = 32
)
```

`Base64Decode(backupKey)` 共 68 字节，布局如下：

```text
offset  0..11   12-byte header      实测为三个大端整数 0000000c 00000010 00000000
offset 12..27   16-byte IV 字段
offset 28..51   24-byte ciphertext
offset 52..67   16-byte GCM tag
```

取 `body = 解码结果[28:]`，也就是 24 字节密文与 16 字节 tag 共 40 字节，再使用 AES-256-GCM 解密：

```text
key        = wrapKey
nonce      = Base64Decode(backupIv)   # 完整 16 字节，不截断
aad        = empty
ciphertext = body[:-16]
tag        = body[-16:]
```

⚠️ 待验证：nonce 用的是**会话元数据里的 `backupIv` 字段**，而不是内嵌在 `backupKey` 里 offset 12 处的那 16 字节。这两者是否恒等、内嵌字段是否根本不参与解密，当时没有单独对照验证——重做时值得先把两段字节打出来比一比，能省掉一轮排查。

解出的明文是一段 Base64 形式的短文本。派生模块密钥时要使用**这段文本自身的字节**，不要再次 Base64 解码。多解一层会使后续所有 GCM 校验失败，而且失败点离真实原因很远。

### <a id="module-key"></a>模块密钥与文件解密

```text
moduleKey = PBKDF2-HMAC-SHA256(
  password   = masterTextBytes,
  salt       = Base64Decode(encryptionSalt),
  iterations = 10000,
  length     = 32
)
```

模块的 `manage.json` 与 `part.0.tar` 使用同一组参数：

```text
AES-256-GCM
nonce   = Base64Decode(encryptionIv)   # 完整 16 字节
aad     = empty
payload = ciphertext || 16-byte tag
```

### <a id="backup-validation"></a>解密结果验证

按以下顺序逐步验证，前一步不通过就不要继续：

1. GCM 标签必须通过；这一步可以排除绝大多数密钥派生错误。
2. `manage.json` 应解密为合法的 UTF-8 JSON，并能从中读出 TAR 明文的 `st_size`。
3. TAR 明文长度应与 `st_size` 完全一致，且 `tar -tf` 能正常列出成员。
4. 最后检查成员路径和内容是否真正包含目标数据。前三步全部通过，也可能只是成功解出了无关模块，见[宿主备份的覆盖范围](#host-backup-scope)。

### <a id="backup-troubleshooting"></a>解密失败与凭据处理

解密失败时，不要立刻断定密码错误。实测中，同一个失败结果可能来自两类原因：密码输入错误，或密钥派生格式判断错误；仅凭 GCM 失败无法区分。当时的判别办法是把同一密码输入系统「恢复」界面，观察系统是否接受该备份，从而把"密码是否正确"与"实现是否正确"拆成两个独立问题。

密码通过环境变量、凭据代理或无回显输入传入，避免进入命令行参数、shell history 和日志。中间派生出的 master text 同样不应打印。

## <a id="migration-options"></a>跨隔离边界的迁移机制

### <a id="migration-candidates"></a>候选机制

当上述通道都无法读取数据时，剩余方向只能是能够跨越隔离边界的机制：

- 厂商提供、且**明确声明包含目标应用数据**的迁移或克隆接口；在 ANCO 环境中，还要确认它是否进入内层容器。
- 可调试或已授权的系统镜像，可以进入容器 namespace（命名空间）或直接读取对应挂载。
- **原签名应用自身提供的导出功能**，先导出，再由新签名版本导入。

### <a id="migration-prerequisites"></a>迁移前置检查

顺序不能反：没有原签名密钥时，不能先安装带导出功能的重签名版本。重签名包无法覆盖原签名应用；安装前必须卸载，而卸载会删除数据。必须先解决导出，再动原包。

破坏性操作前，至少满足以下条件之一：

- 已实际取得主存档与滚动备份，并记录文件大小和哈希；只确认 `allowBackup=true` 或看到备份工具报告成功，都不等于数据已经到手。
- 已在一次性设备或克隆环境中验证迁移机制确实能恢复目标应用数据。
