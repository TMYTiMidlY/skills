# HarmonyOS ANCO 容器中的 Android 应用数据

卓易通一类 ANCO 运行环境不是普通 HarmonyOS 应用目录：鸿蒙应用只是容器管理器，Android 应用及其私有数据位于内层容器。宿主能备份、调试或读取容器管理器，不等于能递归进入每个 Android 应用的数据目录。

> 本文结论来自 HarmonyOS DataBackup 6.1.0.110、卓易通 1.0.10.60 的实测。目录和加密格式已通过 GCM 标签、JSON 与 TAR 结构三重验证；其他版本仍应重新验证。

## <a id="data-boundary"></a>数据边界

传统 Android/Cocos2d-x 应用通常把可写数据放在 `Context.getFilesDir()`。逆向时可从 `CCFileUtilsAndroid::getWritablePath`、`getCocos2dxWritablePath`、保存函数和文件名字符串交叉确认；某些旧游戏的主存档是：

```text
/data/user/0/<android-package>/files/WUD_Default.bin
/data/user/0/<android-package>/files/WUD_Default.bin.bac
```

ANCO 在鸿蒙宿主侧可能把同一数据映射为：

```text
/mnt/data/ANCO_APP_DATA/<android-package>/
```

`mountinfo` 能看到该挂载，只能证明路径存在，不能证明当前身份有权读取。实测中：

- HDC shell 是 `uid=2000(shell)`，即使带 `file_manager` 组，目录遍历仍被 ANCO/SELinux 拒绝。
- `hdc file recv` 由 daemon 处理，仍可能收到同一 `permission denied`。
- 正式用户版拒绝 `hdc smode`，提示设备不是可调试构建；这不是客户端故障。
- `/Android/data` 不是应用内部 `files/` 的替代路径。

HDC（HarmonyOS Device Connector）是鸿蒙设备调试协议，能力类似 Android 的 ADB；定义与命令见 [OpenHarmony HDC README](https://github.com/openharmony/developtools_hdc/blob/5a8e35d0299f19ce9adac8b54756c5b8be58b9ff/README_zh.md)。TCP 端口可达不代表它讲 ADB：新版本 HDC daemon 可能会直接断开 ADB 或旧 HDC 客户端的握手，只有匹配协议并完成设备侧授权后才能建立 shell。

## <a id="host-backup-scope"></a>宿主备份的覆盖范围

华为“数据备份 → 外部存储”里选择卓易通，得到的是卓易通这个 HarmonyOS bundle 的备份。解密后，其 TAR 成员位于：

```text
/data/storage/el2/base/files/...
/data/storage/el2/base/haps/<module>/...
```

实测成员只有鸿蒙侧日志、数据库和 preferences，没有：

```text
/mnt/data/ANCO_APP_DATA/...
WUD_Default.bin
<android-package>
```

因此“备份成功”不能作为卸载 Android 原包的安全依据。破坏性操作前，至少满足其一：

- 已实际拿到主存档和滚动备份文件，并记录大小与哈希；
- 已在一次性设备或克隆环境中验证 ANCO 专用迁移能够恢复内层应用数据。

只看到卓易通出现在应用备份列表、或看到备份包大小非零，都不足以证明内层数据已进入备份。

## <a id="hmosbackup-crypto"></a>HMOSBackup 6.1 加密格式

外部存储备份的会话目录包含顶层 `.info.json`，每个应用模块下有自己的 `.info.json`、`manage.json` 和 `part.0.tar`。`encryptionType=2` 的实测解密链如下。

### 外层备份密钥

```text
wrapKey = PBKDF2-HMAC-SHA256(
  password = UTF-8 password,
  salt = Base64Decode(backupSalt),
  iterations = 10000,
  length = 32
)
```

`Base64Decode(backupKey)` 的布局：

```text
12-byte header
16-byte IV                 # 与 backupIv 相同
24-byte ciphertext
16-byte GCM tag
```

头部实测为三个大端整数：

```text
0000000c 00000010 00000000
```

用 AES-256-GCM 解密剩余 40 字节：

```text
nonce = Base64Decode(backupIv)   # 完整 16 字节
aad = empty
ciphertext = body[:-16]
tag = body[-16:]
```

明文是一个 Base64 形式的短文本。派生模块密钥时使用它的**文本字节本身**，不要先 Base64 解码；用解码后的原始字节会导致模块 GCM 标签校验失败。

### 模块密钥与文件

```text
moduleKey = PBKDF2-HMAC-SHA256(
  password = masterTextBytes,
  salt = Base64Decode(encryptionSalt),
  iterations = 10000,
  length = 32
)
```

模块内的 `manage.json` 和 `part.0.tar` 都采用：

```text
AES-256-GCM
nonce = Base64Decode(encryptionIv)   # 完整 16 字节
aad = empty
payload = ciphertext || 16-byte tag
```

验证顺序：

1. GCM 标签必须通过；失败时不要把随机输出当明文。
2. `manage.json` 应解成 UTF-8 JSON，并给出 `part.0.tar` 的明文 `st_size`。
3. TAR 解密结果长度应与 `st_size` 相同。
4. `tar -tf <decrypted-tar>` 应能正常列出成员。
5. 再检查成员路径和内容是否真的包含目标数据；“成功解密”与“目标数据被备份”是两个独立结论。

密码应通过环境变量、凭据代理或无回显输入传入，避免出现在命令参数、shell history 和日志中；中间 master text 同样不应打印。

## <a id="migration-options"></a>迁移路径

当宿主备份不覆盖 ANCO 内层数据时，可行方向只有能跨越容器边界的机制：

- 厂商提供、且明确包含 Android 应用数据的 ANCO 迁移或克隆接口；
- 可调试/已授权的系统镜像，可进入容器 namespace 或读取对应挂载；
- 原签名应用自身提供导出功能，再由新签名版本导入。

重新签名的 APK 不能覆盖原签名安装，因此“先装一个带导出按钮的改版”通常不可行：Android 会在更新校验阶段拒绝它。若没有原签名密钥，先解决数据导出，再卸载原包。
