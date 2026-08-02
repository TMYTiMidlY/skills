# 设备侧取数通道：adb / Shizuku / HDC / ANCO

要把一个 App 的私有数据（存档、配置）从设备上取出来，走哪条通道、各自卡在哪。这是重打包保存类工作的**前置条件**——重签名包装不上原签名应用的位置，必须先卸载，一卸载数据就没了，所以取数必须排在改包之前。

先给结论表，`无 root 真机` 是最常见也最难的一格：

| 通道 | 能读任意 App 私有目录吗 | 卡在哪 |
|---|---|---|
| `adb shell`（无 root） | **不能** | 进程是 uid=2000(shell)，被 DAC + SELinux 拦住 |
| `adb root`（模拟器 / userdebug 构建） | 能 | 正式用户版拒绝，`adbd cannot run as root in production builds` |
| Shizuku（ADB 模式） | **不能** | 同样是 uid=2000，官方明文说了读不了 |
| Shizuku（root 模式） | 取决于 SELinux | 需要已 root 的设备；官方未就此给出明确说明 |
| `adb backup` | 受应用清单控制 | 依赖 `allowBackup=true`，且已在新版 Android 上废弃 |
| 鸿蒙 HDC | **不能** | 同为 uid=2000，且 ANCO 容器另有一层隔离 |
| 厂商备份 / 云备份 | 看实现 | 实测某鸿蒙壳应用的备份不含内层 Android 应用数据 |

## <a id="private-data-paths"></a>私有数据的位置与权限模型

Android 应用的私有目录有两个等价写法，指的是同一个位置：

```text
/data/user/0/<package>/          # 多用户体系下的规范路径
/data/data/<package>/            # 主用户的传统别名
```

里面通常分成 `files/`（应用自己写的文件，存档多在这）和 `shared_prefs/`（键值偏好，XML）。

**读不到不是因为"没开权限"，是两层机制叠加：**

- **DAC（自主访问控制，就是 Unix 的属主 / 权限位）**：每个应用装上后拿到一个专属 uid，私有目录归它所有，别的 uid 直接被拒。
- **SELinux MAC（强制访问控制，在 DAC 之上再判一次）**：即使 uid 对得上，安全上下文不匹配照样拒绝。

`adb shell` 拿到的进程是 **uid=2000(shell)**，两层都不满足。这就是为什么"我明明开了 USB 调试却还是 permission denied"——调试授权给的是 shell 身份，不是数据访问权。

## <a id="adb-routes"></a>adb 的可行与不可行路径

**`adb root` 只在模拟器和 userdebug / eng 构建上可用。** 可用时最省事：`adb root` 之后直接 `adb pull` / `adb push` 私有目录。正式零售固件的 `adbd` 编译时就禁掉了这条路，执行会直接报错，不是权限没配对。

**`adb backup` 依赖应用自己允许，且已被废弃。** 应用清单里的 `android:allowBackup` 为 `false` 时框架直接拒绝。即使为 `true`，`adb backup` 在较新的 Android 上已标记废弃，不少厂商实现里实际已经不可用或只备份系统数据。

> 来源边界：`allowBackup` 与 `adb backup` 的废弃属于 Android 平台政策，不在 Shizuku 等第三方项目的文档范围内；本条按平台公开行为陈述，具体到某设备某版本是否还能用，需实机验证。

**恢复比备份更容易翻车，属主和权限位必须对。** 把文件贴回私有目录时：

- 覆盖单个文件，不要整个替换应用数据目录。
- 文件属主必须与应用新生成的文件一致，权限通常是 `0600`。**属主错了的典型症状是"应用把存档当作不存在"**——不报错、不崩溃，直接当新档开始，很容易误判成存档格式不兼容。
- 先让新装的应用**启动一次再强制停止**，让它自己把私有目录和属主建好，再往里贴文件。

## <a id="shizuku"></a>Shizuku 的能力边界

Shizuku 常被当成"无 root 提权"的银弹，但它**解决不了取私有数据这件事**，值得先说清楚免得白折腾。

**它是什么**：引导用户以 root（uid=0）或 ADB/shell（uid=2000）身份启动一个常驻服务进程，再把该进程的 Binder 句柄分发给集成了 Shizuku SDK 的应用；应用通过这个句柄让高权限进程**代为调用系统 API**，省掉"起 su 子进程执行命令再解析文本输出"的旧路子。

> 官方定义："With Shizuku API, you can call your Java/JNI code with root/shell (ADB) identity." —— [Shizuku-API README](https://github.com/RikkaApps/Shizuku-API/blob/a27f6e4151ba7b39965ca47edb2bf0aeed7102e5/README.md)

**关键限制——ADB 模式读不了别的应用的数据目录。** 官方文档在对比 ADB 与 ROOT 权限差异时明文写道：

> "In the Linux world, the privilege is determined by Shell's uid, capabilities, SELinux context, etc. For example, **Shell (ADB) cannot access other apps' data files `/data/user/0/<package>`**." —— [Shizuku-API README，"Differents of the privilege betweent ADB and ROOT"](https://github.com/RikkaApps/Shizuku-API/blob/a27f6e4151ba7b39965ca47edb2bf0aeed7102e5/README.md)

道理和上一节一样：ADB 模式下 Shizuku 服务进程本身就是 uid=2000，它没有比 `adb shell` 更高的 Linux 权限。Shizuku 提升的是**能调哪些系统 API**（shell 身份被授予了 `INSTALL_PACKAGES`、`WRITE_SECURE_SETTINGS`、`FORCE_STOP_PACKAGES` 等一批特殊 Android 权限），不是**能读哪些文件**。这两件事常被混为一谈。

**还有三条会影响可行性判断的事实：**

- **目标应用必须自己集成 Shizuku SDK**（加依赖、在清单里声明 `ShizukuProvider`、走一套类似运行时权限的授权流程）。不能拿它去操作一个没适配过的第三方应用——这直接排除了"用 Shizuku 掏一个停服老游戏的存档"这类想法。
- **ADB 方式启动的会话重启即失效**，每次开机要重新用 adb 拉起来。Android 11+ 可以用系统内置的无线调试在设备上直接完成、不用连 PC；root 用户则改用 Magisk 模块 Sui，开机自动生效。
- **root 模式（uid=0）下能不能读私有目录，官方没给明确说法**。uid=0 一般能绕过 DAC，但 Android 的 SELinux enforcing 对 root 同样有约束。这一格标"未知"，要用得实测。

> 版本口径：以上依据 Shizuku [v13.6.0](https://github.com/RikkaApps/Shizuku/releases/tag/v13.6.0)（2025-05-25）及同期 Shizuku-API 文档；要求 Android 6.0+。**本条整节未在本地环境实测**，是照官方文档整理的能力边界。

## <a id="hdc"></a>鸿蒙 HDC 与 ANCO 容器边界

> 实测快照：HarmonyOS DataBackup 6.1.0.110、卓易通 1.0.10.60，正式用户版（非可调试构建）。本节及以下均由实机操作与解密验证。

HDC（HarmonyOS Device Connector）是鸿蒙的设备调试协议，能力类似 Android ADB，定义与命令见 [OpenHarmony HDC README](https://github.com/openharmony/developtools_hdc/blob/5a8e35d0299f19ce9adac8b54756c5b8be58b9ff/README_zh.md)。

卓易通一类 ANCO 环境里，鸿蒙应用只是**容器管理器**；Android 应用及其私有数据位于内层 LXC / iSulad 容器。宿主上可能把数据映射为：

```text
/mnt/data/ANCO_APP_DATA/<android-package>/
```

**`mountinfo` 里看得见挂载，只证明路径存在，不证明当前身份读得到。** 这是最容易误判的一步——看到路径就以为拿到数据了。实测的四道墙：

- HDC shell 身份是 `uid=2000(shell)`，即便带上 `file_manager` 组，目录遍历仍被 ANCO / SELinux 拒绝。
- `hdc file recv` 由 daemon 代为读取，仍然撞同一个 `permission denied`——换传输方式绕不过权限。
- 正式用户版拒绝 `hdc smode`，提示设备不是可调试构建。
- 容器网络没有开放常见的 Android ADB 端口。

**端口可达不等于协议可用。** 曾据"某内网地址上有端口开着"推断那是 ADB/HDC 服务，事后证明该地址只是虚拟组网分配的，端口开着仅说明经组网可达，与协议无关。要匹配 HDC 协议并完成设备侧授权后才能建立 shell。

## <a id="host-backup-scope"></a>宿主备份的覆盖范围

在华为「数据备份 → 外部存储」里勾选卓易通，得到的是**卓易通这个 HarmonyOS bundle 自己的备份**。解密后 TAR 成员只有：

```text
/data/storage/el2/base/files/...
/data/storage/el2/base/haps/<module>/...
```

没有 `/mnt/data/ANCO_APP_DATA/`、没有 Android 包名、没有内层应用的存档文件（本案例要找的 `WUD_Default.bin` 完全不在其中）；对成员内容做全文扫描也搜不到相关引用。

**「备份成功」与「目标数据已进入备份」是两个独立结论。** 看到应用出现在备份列表里、看到备份包体积非零，都不能推出后者。唯一可靠的验证是解密备份、列出 TAR 成员、确认目标文件在里面。

## <a id="hmosbackup-crypto"></a>HMOSBackup 6.1 加密格式

外部存储备份会话含一个顶层 `.info.json`；每个模块有自己的 `.info.json`、`manage.json` 和 `part.0.tar`。以下是 `encryptionType=2` 的完整解密链。

### <a id="outer-key"></a>外层备份密钥

```text
wrapKey = PBKDF2-HMAC-SHA256(
  password   = UTF-8 password,
  salt       = Base64Decode(backupSalt),
  iterations = 10000,
  length     = 32
)
```

`Base64Decode(backupKey)` 共 68 字节，布局：

```text
offset  0..11   12-byte header      实测为三个大端整数 0000000c 00000010 00000000
offset 12..27   16-byte IV 字段
offset 28..51   24-byte ciphertext
offset 52..67   16-byte GCM tag
```

解密时取 `body = 解码结果[28:]`（即 24 字节密文 + 16 字节 tag 共 40 字节），用 AES-256-GCM：

```text
key        = wrapKey
nonce      = Base64Decode(backupIv)   # 完整 16 字节，不截断
aad        = empty
ciphertext = body[:-16]
tag        = body[-16:]
```

⚠️ 待验证：nonce 用的是**会话元数据里的 `backupIv` 字段**，而不是内嵌在 `backupKey` 里 offset 12 处的那 16 字节。这两者是否恒等、内嵌字段是否根本不参与解密，当时没有单独对照验证——重做时值得先把两段字节打出来比一比，能省掉一轮排查。

解出的明文是一段 Base64 形式的短文本。**派生模块密钥时用它的文本字节本身，不要再做一次 Base64 解码**——这里最容易多解一层，之后所有 GCM 校验都会失败，且失败点离真正的原因很远。

### <a id="module-key"></a>模块密钥与文件

```text
moduleKey = PBKDF2-HMAC-SHA256(
  password   = masterTextBytes,
  salt       = Base64Decode(encryptionSalt),
  iterations = 10000,
  length     = 32
)
```

模块的 `manage.json` 和 `part.0.tar` 用同一套：

```text
AES-256-GCM
nonce   = Base64Decode(encryptionIv)   # 完整 16 字节
aad     = empty
payload = ciphertext || 16-byte tag
```

**按顺序验证，每步都卡死再进下一步：**

1. GCM 标签必须通过（这一步就能否掉绝大多数密钥派生错误）。
2. `manage.json` 应解成合法 UTF-8 JSON，并从中读出 TAR 明文的 `st_size`。
3. TAR 明文长度应与 `st_size` 完全相同，且 `tar -tf` 能正常列出成员。
4. 再检查成员路径与内容是否真的包含目标数据——前三步全过也可能只是备份了无关模块，见上一节。

**解密失败时先别断定密码错。** 实测中一次失败同时存在两种可能（密码给错、或密钥派生格式判断有误），单看失败结果无法区分。当时的判别办法是拿同一个密码去系统「恢复」界面试，看它认不认这个备份——把"密码对不对"和"我的实现对不对"拆成两个独立问题。

密码通过环境变量、凭据代理或无回显输入传入，避免进入命令行参数、shell history 和日志；中间派生出的 master text 同样不该打印。

## <a id="migration-options"></a>迁移路径的可行域

当上述通道都取不到数据时，剩下的方向只有能跨越隔离边界的机制：

- 厂商提供、且**明确声明包含目标应用数据**的迁移 / 克隆接口（ANCO 环境下要特别确认它进不进内层容器）；
- 可调试或已授权的系统镜像，能进入容器 namespace 或直接读对应挂载；
- **原签名应用自身提供的导出功能**，导出后再由新签名版本导入。

**顺序不能反：没有原签名密钥时，不能先装带导出功能的重签名版本**——重签名包装不上原签名应用的位置，装之前必须卸载，一卸载数据就没了。先解决导出，再动原包。

破坏性操作前，至少满足其一：已实际取得主存档与滚动备份（有大小与哈希），或已在一次性设备 / 克隆环境里验证过迁移机制确实能恢复目标应用的数据。
