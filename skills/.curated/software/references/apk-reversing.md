# Android APK 逆向与游戏存档

旧手游保存不是简单的“解包再签名”：要同时理解 native 游戏结构、数据资产、失效在线服务、签名边界和存档位置。本文以《爱养成2》与《爱养成3》的 Android 重打包版为实测案例，记录可复用的判断方法。

> 实测快照：《爱养成2》2.9.7.4（`cn.actcap.ayc2`）、《爱养成3》1.7.4（`cn.actcap.ayc3`），HarmonyOS DataBackup 6.1.0.110、卓易通 1.0.10.60。结论均由反汇编、解密认证标签、成品反编译或真机操作验证。

## <a id="application-structure"></a>应用结构

两代游戏的主体是 Cocos2d-x C++：

- 游戏逻辑集中在 `lib/armeabi-v7a/libcocos2dcpp.so` 与对应的 `arm64-v8a` 库。
- native 库没有 strip，保留了 `GameManager`、`Player`、`EventLayer`、`CCSVParse`、`IapStore` 等 C++ 符号；先查符号通常比盲扫汇编快得多。
- Java/Dex 层主要承担 Activity、JNI 桥接、广告、支付和系统能力；`com.catcap.Catcap` 是 C++ → Java 的主要桥。
- APK 同时含 AndroidX、穿山甲广告 SDK 等较新组件，而签名密钥创建于 2014/2015 年；这类组合通常表示“旧游戏本体 + 新发行壳”，分析时应把两层分开。

ARM 反汇编工具不全时，可用 Capstone 加 ELF 符号表：函数地址来自 `nm -DSC`，读取 `PT_LOAD` 段后按 Thumb 位反汇编，再解析 PC-relative 字符串和分支目标。

## <a id="asset-encryption"></a>资源加密

两代 APK 共含 3474 个 CSV 资产：

| 游戏 | CSV 数量 | 常见位置 |
|---|---:|---|
| 爱养成2 | 2172 | `assets/*.csv` |
| 爱养成3 | 1302 | `assets/ios_chs/csv/`、`assets/ios_cht/csv/` |

关键调用链直接保留在符号表中：

```text
CCSVParse::openFile()
  -> rc4_base64_decrypt("dhopNVDUg97ijxDe", data)
```

解密流程：

```text
plaintext = RC4(
  key = "dhopNVDUg97ijxDe",
  data = Base64Decode(assetBytes)
)
```

诊断经验：

- 解码后长度不按 16 字节对齐，可优先排除 AES-CBC/ECB 一类分组模式。
- 固定 RC4 密钥会让相同明文前缀产生相同密文前缀；简体文件通常带 UTF-8 BOM，繁体 `_ft` 文件没有 BOM，因此两组密文从开头就不同。
- 批处理应先尝试 Base64 + RC4，再用 UTF-8 明文作为回退。实测 3469 个文件经过 RC4，另有 5 个文件原本就是明文，全部可恢复。
- 回退必须以 UTF-8 解码成功作为门槛，不能把任意解密失败的数据静默当作明文。

## <a id="game-data-model"></a>游戏数据模型

CSV 不是单纯对白文本，而是一套轻量剧本 VM（虚拟机：用数据行驱动场景和状态变化）：

```text
say emote in out scene music cgin cgout word reward choose fin
```

典型分支：

```text
rewardId||选项文本||跳转行号
```

文本还支持 `$kidname` 一类变量插值，以及用 `|` 表示分页或换段。两代合计约 40270 行剧本指令。

结构化数值表相当于随包附带的设计规则：

- `celebration.csv`、`goout.csv`、`workbook.csv`：地点、时间、前置事件、优先级、课程/打工次数和属性阈值。
- `end.csv`：结局名称与属性、好感度、必要事件、服装等判定条件。
- `reward.csv`：属性、货币、角色好感度和解锁项的增量。
- 《爱养成3》另有 `monster.csv`、`wing.csv`、`piece.csv`，覆盖战斗、翅膀和服装碎片。

两代属性模型不同：

```text
爱养成2：体力 智力 武力 法力 气质 魅力 体贴 道德 感受 叛逆
爱养成3：体力 疲劳 魔力 武力 智力 魅力 体贴 技能 光属性 暗属性
```

分析这类游戏时，应先把脚本文件和规则表分开：脚本文件含 VM opcode，规则表第一行通常是中文字段名。

## <a id="offline-service-repair"></a>失效服务的本地替代

停服后的支付 UI 仍在，但支付 SDK/服务器不可用。两代游戏的商品发放本来就在 native `Java_com_catcap_Base_cpay` 中完成：按商品 ID 更新金币、衣柜和解锁状态，再调用 `Player::saveProfile()`；Java 支付层只是成功回调之前的传输通道。

保留原 UI 和发货逻辑的最小改动：

```text
爱养成2：Fiap.android_pay(productId) -> Base.pay(productId)
爱养成3：Fiap.android_pay(productId) -> Base.pay(productId, 1)
```

其中《爱养成3》的第二个参数 `1` 来自原版购买成功路径。这个改法没有修改 native 库、商品编号、价格文字或存档实现，只把失效的支付传输替换为原版已有的本地成功回调。

验收不能只看 smali：

1. 重建 APK。
2. 重新签名并验证 v2/v3 签名。
3. 从最终 APK 反编译目标类，确认成品里确实调用 `Base.pay(...)`。
4. 真机点击原商城商品，确认奖励实际发放。

本案例四步均已完成：修改版可正常安装运行，点击商品后会直接进入原生发奖逻辑并取得奖励。

重新签名的 APK 不能覆盖原签名安装。它的证书也不再是官方发行证书，系统安装器、安全中心或第三方扫描器可能显示“非官方签名”“来源未知”“存在风险”等不安全提示；具体文案取决于设备和安装器。这类提示本身不能证明 APK 含恶意代码，只说明系统无法用官方签名确认发布者，用户仍需依靠可信来源、哈希和可复现构建判断。

用于保存版的签名密钥应长期保留，否则保存版自己的后续更新仍会再次遇到签名不一致。分发或安装前同时记录：

```text
原版 APK 哈希
修改版 APK 哈希
修改版签名证书指纹
对应源码或补丁版本
```

## <a id="build-verify-loop"></a>构建与成品反编译

多 Dex APK 应先定位目标类实际落在哪个 smali 目录，不能假定总在 `smali/`：

```bash
find <decoded-apk> -path '*/com/catcap/Catcap.smali'
```

本案例使用 [Apktool 2.9.3](https://github.com/iBotPeaches/Apktool/releases/tag/v2.9.3) 解包和重建。只改 smali、不需要重解资源时可用：

```bash
java -jar apktool.jar d -f -r -o <decoded-apk> <input.apk>

# 修改 <decoded-apk>/smali_classes*/com/catcap/Catcap.smali

java -jar apktool.jar b <decoded-apk> -o <unsigned.apk>
unzip -tq <unsigned.apk>
```

改包后原签名失效。可用 [uber-apk-signer 1.3.0](https://github.com/patrickfav/uber-apk-signer/releases/tag/v1.3.0) 同时 zipalign、签 v2/v3 并验证：

```bash
java -jar uber-apk-signer.jar \
  -a <unsigned.apk> \
  -o <signed-output-dir> \
  --allowResign
```

签名工具报告成功只能证明 APK 结构和签名可安装，不能证明修改进入了最终 Dex。最后用 [jadx 1.5.1](https://github.com/skylot/jadx/releases/tag/v1.5.1) 直接反编译**签名后的成品**：

```bash
jadx \
  --single-class com.catcap.Catcap \
  --single-class-output <Catcap.java> \
  <signed.apk>

rg -n 'Base\.pay' <Catcap.java>
```

期望看到：

```java
// 爱养成2
Base.pay(productId);

// 爱养成3
Base.pay(productId, 1);
```

这条“成品反编译”检查能抓住几类常见错误：改错 Dex、构建时复用了旧产物、编辑了未被打包的解码目录，或签名时拿错 APK。

## <a id="save-data"></a>存档文件

游戏自写的 `WhyUserDefault` 默认文件名是：

```text
WUD_Default.bin
WUD_Default.bin.bac
```

`WUD_Default.bin` 含 `playerInfo`、金币、衣柜、事件、结局和照片 ID 等数据；`.bac` 是写入时生成的滚动备份。Cocos2d-x 的 `UserDefault.xml` 只承担附加偏好，不应替代主存档。

Android 内部路径通常为：

```text
/data/user/0/<android-package>/files/WUD_Default.bin
```

卸载原签名 APK 前，必须实际取得主文件和 `.bac`，记录大小与哈希；仅确认应用声明 `allowBackup=true` 不够。

## <a id="anco-data-boundary"></a>ANCO 容器边界

卓易通一类 ANCO 环境中，鸿蒙应用只是容器管理器，Android 应用及其私有数据位于内层 LXC/iSulad 容器。宿主可能把数据映射为：

```text
/mnt/data/ANCO_APP_DATA/<android-package>/
```

`mountinfo` 能看到挂载，只能证明路径存在，不能证明当前身份有权读取。实测中：

- HDC shell 是 `uid=2000(shell)`，即使带 `file_manager` 组，目录遍历仍被 ANCO/SELinux 拒绝。
- `hdc file recv` 由 daemon 处理，仍收到同一 `permission denied`。
- 正式用户版拒绝 `hdc smode`，提示设备不是可调试构建。
- 容器网络没有开放常见 Android ADB 端口。

HDC（HarmonyOS Device Connector）是鸿蒙设备调试协议，能力类似 Android ADB；定义与命令见 [OpenHarmony HDC README](https://github.com/openharmony/developtools_hdc/blob/5a8e35d0299f19ce9adac8b54756c5b8be58b9ff/README_zh.md)。TCP 端口可达不代表它讲 ADB；匹配 HDC 协议并完成设备侧授权后才能建立 shell。

## <a id="host-backup-scope"></a>宿主备份的覆盖范围

华为“数据备份 → 外部存储”里选择卓易通，得到的是卓易通这个 HarmonyOS bundle 的备份。解密后的 TAR 成员只有：

```text
/data/storage/el2/base/files/...
/data/storage/el2/base/haps/<module>/...
```

没有 `/mnt/data/ANCO_APP_DATA/`、Android 包名或 `WUD_Default.bin`；成员内容扫描也没有相关引用。因此“备份成功”和“目标存档已进入备份”是两个独立结论。

破坏性操作前，至少满足其一：

- 已实际取得主存档和滚动备份；
- 已在一次性设备或克隆环境中验证 ANCO 专用迁移能够恢复内层应用数据。

只看到卓易通出现在应用备份列表、或看到备份包大小非零，都不足以证明内层数据已备份。

## <a id="hmosbackup-crypto"></a>HMOSBackup 6.1 加密格式

外部存储备份会话包含顶层 `.info.json`；每个模块有自己的 `.info.json`、`manage.json` 和 `part.0.tar`。`encryptionType=2` 的实测解密链如下。

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
16-byte IV
24-byte ciphertext
16-byte GCM tag
```

头部实测为三个大端整数：

```text
0000000c 00000010 00000000
```

剩余 40 字节使用 AES-256-GCM：

```text
nonce = Base64Decode(backupIv)   # 完整 16 字节
aad = empty
ciphertext = body[:-16]
tag = body[-16:]
```

明文是 Base64 形式的短文本。派生模块密钥时使用它的**文本字节本身**，不要先 Base64 解码。

### 模块密钥与文件

```text
moduleKey = PBKDF2-HMAC-SHA256(
  password = masterTextBytes,
  salt = Base64Decode(encryptionSalt),
  iterations = 10000,
  length = 32
)
```

模块的 `manage.json` 和 `part.0.tar` 都采用：

```text
AES-256-GCM
nonce = Base64Decode(encryptionIv)   # 完整 16 字节
aad = empty
payload = ciphertext || 16-byte tag
```

验证顺序：

1. GCM 标签必须通过。
2. `manage.json` 应解成 UTF-8 JSON，并给出 TAR 明文 `st_size`。
3. TAR 明文长度应与 `st_size` 相同，且 `tar -tf` 能正常列出成员。
4. 再检查成员路径和内容是否真的包含目标数据。

密码应通过环境变量、凭据代理或无回显输入传入，避免出现在参数、shell history 和日志中；中间 master text 同样不应打印。

## <a id="migration-options"></a>迁移路径

当宿主备份不覆盖 ANCO 内层数据时，可行方向只有能跨越容器边界的机制：

- 厂商提供、且明确包含 Android 应用数据的 ANCO 迁移或克隆接口；
- 可调试/已授权的系统镜像，可进入容器 namespace 或读取对应挂载；
- 原签名应用自身提供导出功能，再由新签名版本导入。

若没有原签名密钥，不能先安装带导出功能的重签名版本；应先解决数据导出，再卸载原包。
