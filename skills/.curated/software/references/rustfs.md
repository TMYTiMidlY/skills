# RustFS + MinIO mc 客户端

> RustFS 是 Rust 写的 S3 兼容对象存储（Apache 2.0，[github.com/rustfs/rustfs](https://github.com/rustfs/rustfs)），协议层照搬 MinIO 行为。本文是对接 RustFS 时踩过坑后的稳态结论：客户端怎么选、versioning 桶的软删/硬删/恢复语义、列举数可疑时怎么交叉验证、跨桶 copy 的 timeout 调参、以及 HDD 后端"对象数 ≫ 字节数"的性能特征。
>
> 大批量（几万~几百万对象）op 的可靠性模式（并发 list / delete / copy / 断点续传脚本骨架）单独放在 [rustfs-bulk-ops.md](rustfs-bulk-ops.md)。

## 1. 客户端选型：mc + boto3 互为补集，别只信一个

| 用途 | 选 | 理由 |
|---|---|---|
| CLI / 运维 / 一次性任务 | **mc**（MinIO Client，Go 单二进制） | `cp / mirror / rm / rb / undo / ilm` 等高层批量命令开箱即用 |
| Python 应用 | **boto3**（AWS 官方 SDK） | 单对象 op（Get/Put/Head/Copy）最稳；批量自己拼 worker pool |
| Go 应用 | **minio-go/v7**（mc 内核同源） | 对 MinIO/RustFS 体系原生 |

要点：

- **mc 是 CLI 二进制，不是 Python 库**。Python 想"调 mc"只能 `subprocess.run(['mc', ...])`；想纯 Python 就用 boto3（或 PyPI 的 `minio`）。所以"Python 上 mc vs boto3"不是对立——**实战 pattern = boto3 干 80% + subprocess(mc) 干 mc 独有的高层命令**。
- 其它语言用各家 AWS SDK（`@aws-sdk/client-s3` / `aws-sdk-java-v2` / `aws-sdk-go-v2` / `aws-sdk-s3`(rust)…）或对应 MinIO SDK 即可，都受 RustFS 官方背书（[docs.rustfs.com/developer/sdk](https://docs.rustfs.com/developer/sdk/)）。**没有跨语言的"mc 等价物"**：`mc cp/mirror/rb --force/undo` 这些高层批量命令是 mc 自己用 minio-go 拼的，各语言 SDK 都不直接提供，要自己拼 worker pool（见 [rustfs-bulk-ops.md](rustfs-bulk-ops.md)）。
- **mc 和 boto3 在不同 API 路径上各有坑**（尤其 §4 列举的交叉验证、§5 的 copy timeout），建议**混用 + crosscheck**，速查见 §7。

RustFS 官方把 mc 当 first-class CLI（[docs.rustfs.com/developer/mc](https://docs.rustfs.com/developer/mc.html)）。

## 2. Bucket versioning：是桶级开关，不是新桶类型

`versioning` 是每个 bucket 上的一个 ON/OFF 属性（跟 encryption / quota / lifecycle 并列）：

| 状态 | `PutObject(K)` | `DeleteObject(K)`（不带 versionId） |
|---|---|---|
| **(默认/未设)** | 直接覆盖旧的 | 真删 |
| **Enabled** | 每次造新 version，旧版保留 | 不真删，写一个 *delete marker*（特殊版本） |
| **Suspended** | 新写以 `VersionId=null` 写入，覆盖已有 null-version；旧 enabled 时代的多版本保留 | 同上 |

```bash
mc version info <alias>/<bucket>     # 看状态
mc version enable <alias>/<bucket>   # 开
mc version suspend <alias>/<bucket>  # 暂停（不删旧版本）
```

S3 层对应 `GetBucketVersioning` / `PutBucketVersioning`；boto3 `s3.get_bucket_versioning()` / `s3.put_bucket_versioning(VersioningConfiguration={'Status':'Enabled'})`。

**关键**：`Suspended` 不删旧版本，只是把新写改回单版本模式。要彻底回收旧版本只能靠 lifecycle 或手动硬删（见 §3）。

## 3. 三种"删"：软删 / 硬删 / 恢复 / GC

在 versioning=Enabled 的桶上，"删"有三种粒度，对应不同命令和可恢复性：

| 操作 | mc | boto3 | 服务端行为 | 可恢复 |
|---|---|---|---|---|
| **软删（推荐）** | `mc rm <key>` | `delete_object(Bucket,Key)` 不带 VersionId | 写一个 delete marker；历史 PUT version 全部物理保留 | ✅ `mc undo` 一键复活 |
| **硬删单个 version** | `mc rm --version-id <vid> <key>` | `delete_object(Bucket,Key,VersionId=X)` | 物理删该 version，不生成 marker | ❌ |
| **硬删全部 versions** | `mc rm --versions --force <key>` | 自己列 versions 再逐个 `delete_object(...,VersionId)` | 物理删所有 PUT version + 所有 marker | ❌ 一去不复返 |

- `--versions` / `--recursive` / 从 stdin 删时 mc **强制要 `--force`**（会打 `Removal requires --force flag. This operation is *IRREVERSIBLE*.`）。
- 软删时 mc 会显式打 `Created delete marker <key> (versionId=<dm-vid>).`。

### 撤销最近一次软删：`mc undo`

```bash
mc undo <alias>/<bucket>/<key>                  # 撤销最近 1 次（默认 --last 1）
mc undo <alias>/<bucket>/<key> --last 3         # 撤销最近 3 次
mc undo <alias>/<bucket>/<prefix>/ --recursive  # prefix 下每个 key 各撤销 1 次
```

原理：列出该 key 所有版本按时间倒序，删掉最新的那个（通常是 delete marker）→ 下面那条 PUT version 重新变成 latest → `GetObject` 又能拿回数据。

caveat：

- **只能用于 versioning=Enabled 的桶**（否则 `Undo command works only with S3 versioned-enabled buckets.` 退出）。
- `--last 2+` 是"按倒序删 N 个版本"，不区分 marker 还是 PUT，会把 marker 下面的真数据也连带删——通常不是想要的，**默认 `--last 1` 最稳**。

boto3 手动恢复：

```python
s3.delete_object(Bucket='X', Key='K', VersionId='<dm_vid>')   # 删 delete marker = 复活上一版
# 或不删 marker，直接把旧版本 copy 成当前
s3.copy_object(Bucket='X', Key='K',
    CopySource={'Bucket':'X','Key':'K','VersionId':'<old_put_vid>'})
```

### 让 noncurrent 版本真正消失（GC）

软删后旧 PUT version 变成 *noncurrent*，**永久保留**，除非：

| 触发 | 怎么做 |
|---|---|
| **`NoncurrentVersionExpiration` lifecycle 规则**（推荐，自动 GC） | `mc ilm rule add --noncurrentversion-expire-days N <alias>/<bucket>` |
| **手动硬删全版本** | `mc rm --versions --force`（见上） |

```bash
mc ilm ls <alias>/<bucket>
# 没设规则会显式报：Unable to get lifecycle. ... NoSuchLifecycleConfiguration.
```

设了规则后，RustFS 后台 scanner 周期跑，遇到符合条件的 noncurrent 就物理删；**没设规则 = scanner 不删任何东西 = 旧版本永久攒着**（delete marker 也会一直累积）。

## 4. 列举数对不上时：boto3 + mc 交叉验证

S3 列举（`ListObjectsV2`）在边界场景下，**单个客户端不一定是可靠的"真相来源"**——拿到 HTTP 200 + `IsTruncated=false` 不代表真的列完了。所以一旦"列出来的数跟预期、或跟另一个客户端对不上"，别只信一个：

- **换第二个客户端交叉验证**：mc 和 boto3 是各自独立的实现，同一个桶 / prefix 两边数对不上，基本能把问题从"我 API 用错了"收敛到"服务端 / 版本的问题"。
- **拿 `ListObjectVersions` 当兜底 oracle**：它和 `ListObjectsV2` 是两条不同的服务端代码路径，`mc ls --versions` / boto3 `list_object_versions()` 能独立确认"东西到底在不在、有多少"。
- 已知具体 key 时，`head_object` / `mc stat` 单对象探测不走列举分页，永远准。

```python
# 交叉验证骨架：V2 列举数 vs 版本端点真值，差距异常就别信 V2、再换 mc 复核
v2 = len(s3.list_objects_v2(Bucket=b, Prefix=p).get('Contents', []))
truth = sum(len(pg.get('Versions', []))
            for pg in s3.get_paginator('list_object_versions').paginate(Bucket=b, Prefix=p))
```

> 这个"对结果存疑就用两个独立客户端互证"的习惯，曾帮我们定位并上报过一个上游已修复的服务端列举问题——重点不在那个具体问题，而在这套交叉验证方法本身，对任何 S3 兼容存储都通用。

## 5. 跨桶 server-side copy 与 `Io error: timeout`（HDD 后端高并发）

> 把小文件跨桶搬运时（`mc cp/mirror` 或 boto3 `copy_object`）会撞到的故障。

### 先纠一个直觉：copy 是 server-side，但不是"零成本"

- **mc `cp`/`mirror` 默认走 server-side copy**（`< 64MB` 用 CopyObject、`≥ 64MB` 用 ComposeObject 分段 server-side copy），client **不传字节**。验证：`mc --debug cp ...` 看 PUT 请求是否带 `x-amz-copy-source` header——带 = server-side。（曾误判成"client 下载再上传"，其实是当时机器上还有别的任务在占网卡。）
- **RustFS 内部实现 CopyObject = read src + put_object 到 dst**，不是磁盘层 link。所以对 client 看是一次 PUT（不传字节），对 server 看是**一次 Get + 一次 Put 都打在自家盘上**，受 Get/Put 两端所有 timeout / 限流约束。"server-side"省的是网络往返，**不省后端 disk seek**。

### 症状与根因

```
HTTP/1.1 500 Internal Server Error
<Error><Code>InternalError</Code><Message>Io error: timeout</Message></Error>
```

`mc mirror` 跑一会儿后某些 prefix 标 fail；同 prefix 内大部分对象其实传成功了，少数撞 500。根因：

- **mc 默认把并发 auto-scale 到上限 128 个 worker**（每几秒看带宽决定加不加 worker）。
- 后端是物理 HDD（SATA HDD ~100-200 IOPS）+ 弱 CPU（嵌入式 / NAS / 多容器抢资源）→ 高并发瞬时 disk op 排队 → 单个 op 等待超过 RustFS 内部自适应 timeout 的**下限（默认 5s）** → server 回 500 `Io error: timeout`。

### 解（从轻到重）

1. **`mc cp/mirror --max-workers 4`（或 8/16）限并发**。default 128 对慢后端太猛，限到 NAS IOPS 撑得住的数；慢但稳，需 smoke 找 sweet spot。
2. **脚本层 per-prefix retry**：单 prefix fail → sleep 30s → 重试 ≤3 次。对偶发 timeout 收敛好；对持续超时的大 prefix 救不回。
3. **调高 RustFS server 端 timeout**（改 compose env 后重启 RustFS 容器）：
   ```yaml
   environment:
     RUSTFS_OBJECT_MIN_TIMEOUT: "60"        # 自适应 timeout 下限 5s → 60s
     RUSTFS_OBJECT_DISK_READ_TIMEOUT: "60"  # 10s → 60s
     RUSTFS_OBJECT_GET_TIMEOUT: "120"       # 30s → 120s
   ```
   注意这几个 env 主要覆盖 GetObject 侧；CopyObject 内部的 PutObject 侧是否有对应 env 没验证过。
4. **根治 = 后端硬件**：HDD → SSD/NVMe 提 IOPS；或拆多 storage pool 分散 IO；或加 RAM cache。

### 快速判定"是 API 坏了还是并发太猛"

```python
import boto3
s3 = boto3.client('s3', endpoint_url=..., aws_access_key_id=..., aws_secret_access_key=...)
s3.copy_object(CopySource={'Bucket':'src','Key':'path/obj'}, Bucket='dst', Key='path/obj')
# 单次几十~几百 ms 返回 200 = CopyObject API 本身没问题，500 是高并发撞 timeout
```

> 元教训：S3 这类协议的"复杂行为"别凭网络监控的间接观察脑补 root cause——先 smoke test（单次 API 调用）+ 必要时翻官方行为，再下结论。并发任务 / 其它流量很容易误导间接观察。

## 6. 性能特征：bucket 操作 wall-clock ∝ 对象数，不是字节数

RustFS 跑 HDD 后端时（典型 baremetal / NAS / edge），bucket 级 list / mirror / scanner / copy 的瓶颈是**后端 HDD 随机 IOPS（~100-200/s）**，不是网络带宽。每个对象的 metadata op（HEAD / COPY / DELETE / list 一行）至少 1 个 disk seek，所以 wall-clock 跟**对象数**成正比、跟**字节数**基本无关。

实测（boto3 `copy_object`，4 worker，server-side，HDD 后端）：

| 任务 | 对象数 | 总字节 | wall-clock |
|---|---|---|---|
| A：~25600 个小对象跨桶 mirror | 25,620 | 298 MB | **427s**（~60 obj/s） |
| B：把同一组数据先打成 zip 再跨桶 copy | 495 | 304 MB | **35.4s**（~14 obj/s） |

字节量几乎相同（差 2%），对象数差 52×，B 比 A 快约 **8–15×**。

工程含义：对"每个逻辑单位几十~几百个小文件"的工作负载，**把小文件聚合成中等大小对象（打 zip / pack）对 HDD 后端是近乎免费的 ~10× 加速**——因为 server-side copy 不省 disk seek（§5），少对象 = 少 seek。后台 scanner 跑完一轮的时间也按对象数缩比例，间接影响 `mc admin info` 用量统计的更新延迟。

## 7. mc vs boto3 行为速查

| 操作 | mc | boto3 / AWS SDK | 优选 |
|---|---|---|---|
| `ListObjectsV2`（列对象） | 边界场景下结果可能与真值不符 | 同左 | 数可疑时交叉验证 + `ListObjectVersions` 兜底（§4） |
| `ListObjectVersions`（列版本历史） | `mc ls --versions`，分页正确 | `list_object_versions()`，分页正确 | 任意（§4 旧版本枚举唯一可靠路径） |
| `GetObject`/`HeadObject`/`PutObject` 单对象 | OK | OK | 任意 |
| 软删 | `mc rm K` | `delete_object(Bucket,Key)` | 任意 |
| 硬删单 vid / 全版本 | `mc rm --version-id` / `--versions --force` | 自己列 versions 逐个删 | mc 简洁 |
| 撤销最近软删 | `mc undo K` | `delete_object(...,VersionId=<dm_vid>)` | mc |
| 跨桶 server-side copy | `mc cp/mirror`（默认 server-side） | `copy_object()` | 高并发慎用 mc（auto-scale 128 worker 易撞 §5 timeout），改 boto3 限并发 |
| `mc mirror` 批量复制 | 大批量 / versioning 桶复制结果不易校验 | — | 改 boto3 单对象 copy + 限并发 + 事后 key set 比对 |

## 8. 清空 / 删桶：`mc rb --force` 与 `x-minio-force-delete`

### `mc rb --force` 真相（最容易踩的坑）

很多人以为 `mc rb --force` = "桶里对象软删 + 删桶，versions 还在能 undo"。**完全错**。它内部用 `WithOlderVersions + WithDeleteMarkers` 列出**所有版本**逐个 `DeleteObject(VersionId=X)` 物理硬删，再删空桶。MinIO 官方文档也明说：`mc rb` _permanently deletes bucket(s), **including any and all object versions** and bucket configurations_。

**结论**：`mc rb --force` 在 versioning 桶上 ≡ 硬删所有 version + 删桶，**100% 不可恢复**。"既软删又删桶又保留可恢复"在 versioning 桶上逻辑不可能（桶非空删不掉；要空就得硬删 versions）。

- 想"桶看着空但保留 versions" → `mc rm --recursive --force <bucket>`（不带 `--versions`，桶保留）
- 想"彻底删桶 + 回收磁盘" → `mc rb --force <bucket>`（不可逆）

### 大 versioning 桶清空：用 `x-minio-force-delete` header

`mc rb --force` 在**大 versioning 桶 + 海量 delete marker** 上会卡死——它先 client 端 `ListObjectVersions`，server 在大桶上这一步 hang 30+ min 不返，**不可用**。

MinIO 协议族有个非标准 header `x-minio-force-delete: true`，发给 `DELETE /<bucket>` 让 **server 端内部一键清桶**（所有 version + marker + 元数据），绕过 client 列举。实测（RustFS v1.0.0-beta.5）：

| 项 | 行为 |
|---|---|
| RustFS 是否接受 | ✅ HTTP 200（不是 400 拒绝），但很慢 |
| client 断开后 | ✅ server 端继续跑（异步 server-side job，不依赖 client 连接） |
| 实测耗时（145 万 current + 几百万 noncurrent/marker，HDD） | **~4 小时**（client 5min timeout 早断；server 几小时后桶才消失） |

**用法**：发完请求别守着，让 server 慢慢跑，过几小时 `mc ls <alias>/` 看桶是否消失。boto3 不直接支持这个 header（要手拼 sigv4），现成脚本见 [`scripts/rustfs_force_delete_bucket.py`](../scripts/rustfs_force_delete_bucket.py)：

```bash
uv run scripts/rustfs_force_delete_bucket.py \
  --endpoint http://rustfs:9000 --bucket my-big-bucket \
  --access-key AK --secret-key SK   # 发完即返回，不等 server 跑完
```

## 9. 常用诊断命令

```bash
mc version info <alias>/<bucket>                 # 桶 versioning 状态
mc ls --versions <alias>/<bucket>/<prefix>/      # 列所有版本（列举数可疑时的兜底枚举，见 §4）
mc rm <alias>/<bucket>/<key>                     # 软删（写 delete marker）
mc undo <alias>/<bucket>/<key>                   # 撤销最近软删
mc ilm ls <alias>/<bucket>                       # 看 lifecycle（没设报 NoSuchLifecycleConfiguration）
mc ilm rule add --noncurrentversion-expire-days 30 <alias>/<bucket>   # noncurrent 30 天自动 GC
mc rm --recursive --versions --force <alias>/<bucket>/<prefix>/       # 硬删全版本（IRREVERSIBLE）
```

## 参考

- 背景：交叉验证时上报的一个列举问题 [rustfs/rustfs#3217](https://github.com/rustfs/rustfs/issues/3217)（官方已在新版本修复）
- RustFS 官方：[mc 用法](https://docs.rustfs.com/developer/mc.html)、[SDK 列表](https://docs.rustfs.com/developer/sdk/)
- AWS S3 spec：[Object versioning](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Versioning.html)、[Working with delete markers](https://docs.aws.amazon.com/AmazonS3/latest/userguide/DeleteMarker.html)、[Lifecycle 配置](https://docs.aws.amazon.com/AmazonS3/latest/userguide/intro-lifecycle-rules.html)
- 大批量 op 可靠性模式：[rustfs-bulk-ops.md](rustfs-bulk-ops.md)
