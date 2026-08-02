# 鸿蒙与 ANCO 容器

在 HarmonyOS 设备上取 Android 应用的私有数据，以及解密宿主导出的外部存储备份。核心矛盾：**目标数据在容器里，宿主的备份和调试通道都够不着它**。

> 实测快照：HarmonyOS DataBackup 6.1.0.110、卓易通 1.0.10.60，正式用户版（非可调试构建）。以下结论均由实机操作与解密验证。

## <a id="anco-boundary"></a>ANCO 容器边界

卓易通一类 ANCO 环境里，鸿蒙应用只是**容器管理器**；Android 应用及其私有数据位于内层 LXC / iSulad 容器。宿主上可能把数据映射为：

```text
/mnt/data/ANCO_APP_DATA/<android-package>/
```

**`mountinfo` 里看得见挂载，只证明路径存在，不证明当前身份读得到。** 这是最容易误判的一步——看到路径就以为拿到数据了。实测的四道墙：

- HDC shell 身份是 `uid=2000(shell)`，即便带上 `file_manager` 组，目录遍历仍被 ANCO / SELinux 拒绝。
- `hdc file recv` 由 daemon 代为读取，仍然撞同一个 `permission denied`——换传输方式绕不过权限。
- 正式用户版拒绝 `hdc smode`，提示设备不是可调试构建。
- 容器网络没有开放常见的 Android ADB 端口。

HDC（HarmonyOS Device Connector）是鸿蒙的设备调试协议，能力类似 Android ADB，定义与命令见 [OpenHarmony HDC README](https://github.com/openharmony/developtools_hdc/blob/5a8e35d0299f19ce9adac8b54756c5b8be58b9ff/README_zh.md)。**TCP 端口可达不代表它讲 ADB**；要匹配 HDC 协议并完成设备侧授权后才能建立 shell。

## <a id="host-backup-scope"></a>宿主备份的覆盖范围

在华为「数据备份 → 外部存储」里勾选卓易通，得到的是**卓易通这个 HarmonyOS bundle 自己的备份**。解密后 TAR 成员只有：

```text
/data/storage/el2/base/files/...
/data/storage/el2/base/haps/<module>/...
```

没有 `/mnt/data/ANCO_APP_DATA/`、没有 Android 包名、没有内层应用的存档文件（本案例要找的 `WUD_Default.bin` 完全不在其中）；对成员内容做全文扫描也搜不到相关引用。

**「备份成功」与「目标数据已进入备份」是两个独立结论。** 看到卓易通出现在备份列表里、看到备份包体积非零，都不能推出后者。唯一可靠的验证是解密备份、列出 TAR 成员、确认目标文件在里面。

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

密码通过环境变量、凭据代理或无回显输入传入，避免进入命令行参数、shell history 和日志；中间派生出的 master text 同样不该打印。

## <a id="migration-options"></a>迁移路径的可行域

当宿主备份不覆盖 ANCO 内层数据时，剩下的方向只有能跨越容器边界的机制：

- 厂商提供、且**明确声明包含 Android 应用数据**的 ANCO 迁移 / 克隆接口；
- 可调试或已授权的系统镜像，能进入容器 namespace 或直接读对应挂载；
- 原签名应用自身提供的导出功能，导出后再由新签名版本导入。

**顺序不能反：没有原签名密钥时，不能先装带导出功能的重签名版本**——重签名包装不上原签名应用的位置，装之前必须卸载，一卸载数据就没了。先解决导出，再动原包。

破坏性操作前，至少满足其一：已实际取得主存档与滚动备份（有大小与哈希），或已在一次性设备 / 克隆环境里验证过 ANCO 专用迁移确实能恢复内层应用数据。
