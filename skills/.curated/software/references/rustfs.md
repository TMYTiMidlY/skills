# RustFS + MinIO mc 客户端：versioning 桶语义与 ListObjectsV2 paginator bug

> RustFS 是 Rust 实现的 S3 兼容对象存储（Apache 2.0，github.com/rustfs/rustfs），协议层照搬 MinIO 行为。本文聚焦两块容易被坑的地方：**versioning 桶上的软删 vs 硬删语义**，以及 **ListObjectsV2 在 versioning 桶 + 大量 delete marker 时提前截断的服务端 bug**。
>
> 配套客户端 `mc`（MinIO CLI）的行为也一并梳理 —— 它与 boto3 / aws-cli 在某些边界（特别是 `ListObjectsV2` 的 paginator 实现）行为不一致，盲信单一客户端会被误导。
>
> 配套的故障排查经验（CopyObject 跨桶 server-side 行为、`Io error: timeout` 调参、并发上限等）在 `mess/references/rustfs.md`，本文只描述工具本身的稳定行为。

## 1. Bucket versioning：是桶级开关，不是新桶类型

`versioning` 是每个 bucket 上的**一个 ON/OFF 属性**（跟 encryption / quota / lifecycle 并列）。开关只有 3 个状态：

| 状态 | 行为 |
|---|---|
| **(默认 / 未设)** | `PutObject(K)` 直接覆盖旧的；`DeleteObject(K)` 真删 |
| **Enabled** | `PutObject(K)` 每次造新 version、旧版保留；`DeleteObject(K)` 不真删，写一个 *delete marker*（一种特殊版本） |
| **Suspended** | 新写以 `VersionId=null` 写入，覆盖任何已有的 null-version；旧 enabled 时代的多版本保留 |

查/改：

```bash
mc version info <alias>/<bucket>     # 看状态
mc version enable <alias>/<bucket>   # 开
mc version suspend <alias>/<bucket>  # 暂停（不删旧版本）
```

S3 层 API 对应 `GetBucketVersioning` / `PutBucketVersioning`。boto3：

```python
s3.get_bucket_versioning(Bucket='X')        # → {'Status': 'Enabled'}
s3.put_bucket_versioning(Bucket='X',
    VersioningConfiguration={'Status': 'Enabled'})
```

**关键：**`Suspended` 不删旧版本，只是把新写改回单版本模式。要彻底回收旧版本只能靠 `NoncurrentVersionExpiration` lifecycle 或手动 `mc rm --versions`（见后文）。

## 2. 三种"删"：软删 / 硬删 / 桶级 versioning 关闭

在 versioning=Enabled 的桶上，"删"有三种粒度，**对应不同 mc 命令、不同 S3 调用、不同可恢复性**：

| 操作 | mc 命令 | S3 调用 | 服务端行为 | 可恢复 |
|---|---|---|---|---|
| **软删（推荐）** | `mc rm <key>` | `DeleteObject(K)` 不带 versionId | 写一个 DEL marker；所有历史 PUT version 全部物理保留 | ✅ `mc undo` 一键复活最近一次软删 |
| **硬删单个 version** | `mc rm --version-id <vid> <key>` | `DeleteObject(K, VersionId=X)` | 物理 delete 该 version 行；不生成 marker | ❌ 该 version 不可恢复 |
| **硬删全部 versions** | `mc rm --versions --force <key>` | `ListObjectVersions(Prefix)` + 每个 vid 都发一次 `DeleteObject(K, VersionId=X)` | 物理 delete 所有 PUT version + 所有 DEL marker | ❌ 一去不复返 |

### mc rm 源码验证

`mc/cmd/rm-main.go`（[c652022](https://github.com/minio/mc/blob/c652022dab9d18387d8f5f37e69033c5f351da54/cmd/rm-main.go#L714-L752)）：

```go
withVersions := cliCtx.Bool("versions")
versionID    := cliCtx.String("version-id")
rewind       := parseRewindFlag(cliCtx.String("rewind"))

if withVersions && rewind.IsZero() {
    rewind = time.Now().UTC()       // ← --versions 强制 rewind=now
}
...
if isRecursive || withVersions {    // 分支 1: 列所有版本逐个 hard delete
    e = listAndRemove(url, removeOpts{
        timeRef:      rewind,
        withVersions: withVersions,
        ...
    })
} else {
    e = removeSingle(url, versionID, ...)   // 分支 2: 单个 delete，可能空 versionId
}
```

不带 `--versions` → 走 `removeSingle`，`versionID=""` → server 看到 `DELETE /bucket/key` 无 `versionId` 参数 → 在 versioning 桶上**生成 delete marker**。mc 输出会显式打：

```
Created delete marker `<key>` (versionId=<dm-vid>).
```

带 `--versions` → `listOpts.WithOlderVersions=true, WithDeleteMarkers=true` → `ListObjectVersions` 拿全所有 vid → 每个 vid 都送 `DeleteObject(Key, VersionId=X)` → 物理 hard delete。

`--force` 是必需的（[`rm-main.go:275-279`](https://github.com/minio/mc/blob/c652022dab9d18387d8f5f37e69033c5f351da54/cmd/rm-main.go#L275-L279)）：

```go
if (isVersions || isRecursive || isStdin) && !isForce {
    fatalIf(errDummy().Trace(),
        "Removal requires --force flag. This operation is *IRREVERSIBLE*.")
}
```

### RustFS 服务端行为验证

`rustfs/crates/ecstore/src/set_disk.rs::resolve_delete_version_state` ([20bb5dc](https://github.com/rustfs/rustfs/blob/20bb5dc4a2bd82d30c7699a3898924b10f091952/crates/ecstore/src/set_disk.rs#L2632-L2679))：

```rust
fn resolve_delete_version_state(opts: &ObjectOptions, ...) -> (bool, bool) {
    let mut mark_delete  = goi.version_id.is_some();
    let mut delete_marker = opts.versioned;     // 不带 versionId & 桶是 versioned → 生成 marker
    if opts.version_id.is_some() {              // 带了 versionId → hard delete 路径
        mark_delete = false;
        delete_marker = false;                  // 不生成 marker
    }
    (mark_delete, delete_marker)
}
```

E2E 测试 `delete_objects_versioning_test.rs` 直接验证：删完原 PUT version 仍 `is_latest=False` 存活、`mc ls --versions` / `ListObjectVersions` 仍能拿到 vid → 可 GET 恢复。

## 3. mc undo：撤销最近一次软删

```bash
mc undo <alias>/<bucket>/<key>                  # 撤销 1 次（default --last 1）
mc undo <alias>/<bucket>/<key> --last 3         # 撤销最近 3 次
mc undo <alias>/<bucket>/<prefix>/ --recursive  # prefix 下所有 key 各撤销 1 次
```

机制（[`mc/cmd/undo-main.go`](https://github.com/minio/mc/blob/c652022dab9d18387d8f5f37e69033c5f351da54/cmd/undo-main.go)）：

1. `ListObjectVersions(Prefix, WithOlderVersions=true, WithDeleteMarkers=true)` 列所有版本，**按 mod_time 倒序**
2. 取前 N 条（默认 N=1）
3. 对每条调 `DeleteObject(Key, VersionId=X)`，X 通常是最新的 DEL marker vid
4. DEL marker 被物理删除 → 下面那条 PUT version 重新成为 `IsLatest=True` → `GetObject(Key)` 又能拿回数据

**caveat**：`mc undo` 只能操作**versioning=Enabled** 的桶（否则 `Undo command works only with S3 versioned-enabled buckets.` 直接退出）。`--last 2` 之类的"撤销多次"会把 DEL marker 下面的 PUT version 也连带删（因为 mc 只按倒序取 N，不区分类型）—— 通常不是想要的，**默认 `--last 1` 最稳**。

如果用 boto3 手动恢：

```python
s3.delete_object(Bucket='X', Key='K', VersionId='<dm_vid>')  # 删 DEL marker = 复活上一版
# 或者，不删 marker, 直接 copy 旧版本到当前
s3.copy_object(Bucket='X', Key='K',
    CopySource={'Bucket': 'X', 'Key': 'K', 'VersionId': '<old_put_vid>'})
```

## 4. lifecycle / prune：唯一能让 noncurrent 真消失的两条路径

软删后旧 PUT version 变成 *noncurrent*。这些 noncurrent 永远保留，**除非**：

| 触发 | 配置位置 |
|---|---|
| **`NoncurrentVersionExpiration` lifecycle 规则** | `mc ilm rule add <alias>/<bucket> --noncurrentversion-expire-days N` |
| **手动 mc rm --versions --force** | 见 §2 |
| **MinIO 风格 admin prune** | RustFS 不直接提供，但上层应用代码（如 S3-compatible 服务自带的 `storage prune` / `cleanup` 子命令，或者自写脚本枚举 `ListObjectVersions` + `DeleteObject(VersionId=X)`）可绕开手动硬删 |

### 查 lifecycle

```bash
mc ilm ls <alias>/<bucket>
# 没设规则会返:
# mc: <ERROR> Unable to get lifecycle. Error response code NoSuchLifecycleConfiguration.
```

`NoSuchLifecycleConfiguration` 就是"没配规则"。

### RustFS lifecycle 实现

`rustfs/crates/ecstore/src/bucket/lifecycle/core.rs::noncurrent_versions_expiration_limit` ([20bb5dc](https://github.com/rustfs/rustfs/blob/20bb5dc4a2bd82d30c7699a3898924b10f091952/crates/ecstore/src/bucket/lifecycle/core.rs#L705-L735))：

```rust
if let Some(ref nve) = rule.noncurrent_version_expiration {
    return Event {
        action: IlmAction::DeleteVersionAction,   // ← 物理 delete noncurrent
        noncurrent_days: nve.noncurrent_days.unwrap_or(0) as u32,
        ...
    };
}
```

后台 scanner 周期跑，遇到符合条件的 noncurrent → 物理 delete。**没设规则 → scanner 不触发任何 delete → 旧版本永久保留**（验证：integration test `lifecycle_integration_test.rs:1795` 显式断言 "rule 应用前 count=2，应用后 count=1"）。

## 5. ListObjectsV2 paginator bug（versioning + 大量 delete marker）

RustFS 服务端在 versioning 桶 + 大量 delete marker 时，`ListObjectsV2` 会**错误地返回 `IsTruncated=false`**，骗客户端"已经列完"，实际上还有大量对象没列。

### 症状

```python
import boto3
s3 = boto3.client('s3', endpoint_url='http://<rustfs>:9000', ...)
resp = s3.list_objects_v2(Bucket='<versioned-bucket>', Prefix='X/', MaxKeys=1000)
# resp['Contents']: 26 个    ← 远少于真实
# resp['IsTruncated']: False  ← server 谎称列完
# resp['NextContinuationToken']: ''
```

底层数学（详见根因部分）：service 给的 `per_disk_limit = max_keys + 4 + max_keys/16 = 1067`。如果该 prefix 下平均每个 sub-prefix（4 层路径中的第 3 层 key 族）有 40 个 delete marker，1067 / (1+40) ≈ 26 个 sub-prefix → 实际只列出 26 个用户可见对象，walker 撞内部 budget 提前 return → `disk_has_more=false` → `IsTruncated=false`。

### 根因（已读源码确诊）

`rustfs/crates/ecstore/src/disk/local.rs::scan_dir` 内有两处 `objs_returned += 1`，**包在被注释掉的 `all_hidden` guard 内**：

```rust
// crates/ecstore/src/disk/local.rs:1453-1458
// if opts.limit > 0
//     && let Ok(meta) = FileMeta::load(&metadata)
//     && !meta.all_hidden(true)
// {
*objs_returned += 1;   // ← 应该只对"可见对象"计数, 现在对每个 xl.meta 都计
// }
```

后果：delete marker 也占 `per_disk_limit` budget → walker 误以为列完 → server 回 `IsTruncated=false`。

下游 `store_list_objects.rs:482-501` 还有第二个 bug —— `delimiter` 不为空时 `is_truncated` 重判条件错（`visible_count >= max_keys` 而不是 `> 0`），无法 rescue 第一处的误判。

### 客户端差异：boto3 vs mc

| 客户端 | 行为 | 在该 bug 下结果 |
|---|---|---|
| boto3 / aws-cli `ListObjectsV2` paginator | 严格遵守 `IsTruncated=false`，看到就停 | **只看到 26 个**（符合 spec，client 没错） |
| mc `mc ls` | **不信任 IsTruncated** —— 拿最后一个 Key 当 `StartAfter` 强制接力 | **看到全部 246 个**（用 workaround 绕过 server 的谎言） |

反过来到 `ListObjectVersions` API 上，mc 没实现同样 workaround，所以 `mc ls --versions` 又会被同款 RustFS bug 截断；而 boto3 `list_object_versions()` 是另一套 endpoint，能正确列。两个客户端**互为补集**，盲信单一客户端会被误导。

### 诊断 IsTruncated 是否被服务端骗

直接手写一次 paginator 调用看原始字段：

```python
resp = s3.list_objects_v2(Bucket='X', Prefix='Y/', MaxKeys=1000)
print(f"Contents: {len(resp.get('Contents', []))}")
print(f"IsTruncated: {resp.get('IsTruncated')}")
print(f"NextToken: {resp.get('NextContinuationToken', '(none)')}")
```

- `IsTruncated=False` 但 `len(Contents) < 真实数`（用 `mc ls` 复核）→ **服务端 bug 中招**

### 不依赖 paginator 的稳定 list workaround（boto3）

```python
def list_with_start_after(s3, bucket, prefix, page_size=1000):
    """模仿 mc 的实现: 用 StartAfter 强制接力, 忽略 IsTruncated"""
    last_key = None
    while True:
        kwargs = {'Bucket': bucket, 'Prefix': prefix, 'MaxKeys': page_size}
        if last_key:
            kwargs['StartAfter'] = last_key
        resp = s3.list_objects_v2(**kwargs)
        contents = resp.get('Contents', [])
        if not contents:
            break
        for obj in contents:
            yield obj
        new_last = contents[-1]['Key']
        if new_last == last_key:   # 防死循环
            break
        last_key = new_last
```

### 不依赖 paginator 的其他通路

- `head_object(Bucket, Key)` 单对象探测 —— 不走 paginator，可靠
- `list_object_versions(Bucket, Prefix)` —— 不同 endpoint，paginator 路径不同（但在某些桶状态下也有截断 bug，需 case-by-case 验证）
- `mc ls` 子进程 —— 借用 mc 的 StartAfter workaround
- `mc rm --recursive` —— 内部一样用 mc 自己的 list 实现，**软删**操作可信
- `mc cp` / `mc mirror` —— 同上

## 6. 性能特征：bucket 操作 wall-clock ∝ 对象数，不是字节数

RustFS 跑在 HDD 后端时（典型 baremetal / NAS / edge 部署），bucket 级 list / mirror / scanner / copy 的性能瓶颈是**后端 HDD 随机 IOPS（~100-200/秒）**，而不是网络带宽。每个对象的 metadata op（HEAD / COPY / DELETE / list 一行）至少消耗 1 个 disk seek，所以 wall-clock 跟 **对象数** 成正比，跟 **字节数** 基本无关。

### 实测数据点（boto3 `copy_object` 4 worker, server-side, HDD 后端）

| 任务 | 对象数 | 总字节 | 平均对象 | wall-clock | 速率 |
|---|---|---|---|---|---|
| A: ~25600 个小对象 跨桶 mirror（mc mirror, 含 1 次 silent fail + retry） | 25,620 | 298 MB | 11.6 KiB | **427s** | ~60 obj/s |
| B: 把同一组数据预先打成 zip 后跨桶 copy（boto3 copy_object server-side） | 495 | 304 MB | 614 KiB | **35.4s** | ~14 obj/s |

字节量几乎相同（A 298 MB / B 304 MB，差 2%），但对象数差 52×，**B 比 A wall-clock 快约 12×**（严谨区间 8-15×：A 含 retry 偏慢，B 在 server 还在抢资源时跑偏慢，两边偏差方向相反）。

### 工程含义

对预期对象数大的工作负载（每个逻辑单位几十到几百个小文件之类）：

- **批量 list / mirror / scanner 性能**：对象数从 N → N/50 = wall-clock ≈ 10× 加速
- **RustFS 后台 scanner 跑完一轮的时间**也按对象数缩比例，间接影响 `mc admin info` per-bucket 用量统计的更新延迟
- **server-side copy 不省 disk seek**：mc cp / boto3 copy_object 走 server-side（不传字节），但 server 自己还要做 read+put_object（详见 `mess/references/rustfs.md` §CopyObject 段），HDD seek 一样吃；所以"打成 zip" 这种把小文件聚合成中等大小对象的设计模式，对 RustFS HDD 后端是几乎免费的 10× 加速

### 测速方法（reproducible）

```python
# 同 shard 同字节量两种打包方式各跑一次, 对比 wall-clock
from concurrent.futures import ThreadPoolExecutor, as_completed
import boto3, time

s3_factory = lambda: boto3.client('s3', endpoint_url=..., ...)

def copy_one(src_key):
    s3 = s3_factory()
    s3.copy_object(
        Bucket='dst-bucket', Key=f'test/{src_key}',
        CopySource={'Bucket': 'src-bucket', 'Key': src_key},
    )

# 列源（如果 src 桶有 paginator bug, 用 mc ls 替代）
keys = [...]  # N 个 obj
start = time.time()
with ThreadPoolExecutor(max_workers=4) as pool:
    list(as_completed([pool.submit(copy_one, k) for k in keys]))
print(f'{len(keys)} obj / {(time.time()-start):.1f}s = {len(keys)/(time.time()-start):.1f} obj/s')
```

**注意 caveats**：

- 测试时若有别的 worker 在抢 RustFS IOPS，结果偏慢；要严谨的 head-to-head 应该在 idle window 跑
- 不要用 `mc mirror` 测速 —— 它在 versioning 桶 + 大 prefix 上经常 silent fail（退码 0 / 0 transferred）；改用 boto3 单对象 `copy_object` 拼 4 worker
- 跨桶 server-side copy 受 RustFS 内部 GetObject 限速；高并发会触发 `Io error: timeout` 500（调参见 `mess/references/rustfs.md` §3）

## 7. mc 和 boto3 行为速查

| 操作 | mc | boto3 / aws-cli | 备注 |
|---|---|---|---|
| `ListObjectsV2` paginator | 不信 `IsTruncated`，用 `StartAfter` 接力（对 RustFS bug 抗性强） | 严格信 `IsTruncated`（spec 合规，但被 server bug 骗） | 列 versioning 桶优先 mc 或自写 StartAfter loop |
| `ListObjectVersions` | 同 ListObjectsV2 bug 但无 workaround | 正确（不同 endpoint） | 列版本历史优先 boto3 |
| `DeleteObject` 软删 | `mc rm K`（不带 `--versions`） | `s3.delete_object(Bucket, Key)`（不传 `VersionId`） | 在 versioning 桶上生成 DEL marker |
| `DeleteObject` 硬删单 vid | `mc rm --version-id <vid> K` | `s3.delete_object(Bucket, Key, VersionId=vid)` | 物理删该 version |
| `DeleteObject` 硬删全 | `mc rm --versions --force K` | 自己 `list_object_versions` + 每条 `delete_object(Bucket, Key, VersionId)` | irreversible，须 `--force` |
| 撤销最近软删 | `mc undo K` | `s3.delete_object(Bucket, Key, VersionId=<dm_vid>)` | mc 自动找最新 DEL marker vid |
| `head_object` 单对象探测 | `mc stat K` | `s3.head_object(Bucket, Key)` | 不走 paginator，永远稳 |
| 跨桶 server-side copy | `mc cp/mirror` 默认 server-side（CopyObject < 64MB / ComposeObject ≥ 64MB） | `s3.copy_object()` | 受后端 IOPS 限速；详见 mess 笔记 |

## 8. 常用诊断命令

```bash
# 桶级 versioning 状态
mc version info <alias>/<bucket>

# 单个 key 的所有版本（如果命中 paginator bug 输出可能截断,用 boto3 复核）
mc ls --versions <alias>/<bucket>/<key>

# 软删一个 key（生成 DEL marker, 不真删）
mc rm <alias>/<bucket>/<key>

# 撤销最近软删
mc undo <alias>/<bucket>/<key>

# 看 lifecycle 规则（没设会显式报 NoSuchLifecycleConfiguration）
mc ilm ls <alias>/<bucket>

# 让特定 prefix 的 noncurrent 30 天后自动 GC
mc ilm rule add --noncurrentversion-expire-days 30 <alias>/<bucket>

# 硬删一个 key 全部 versions（仔细看 IRREVERSIBLE 提示）
mc rm --recursive --versions --force <alias>/<bucket>/<prefix>/
```

## 9. 关键引用

- mc 源码：[`cmd/rm-main.go:42-44`](https://github.com/minio/mc/blob/c652022dab9d18387d8f5f37e69033c5f351da54/cmd/rm-main.go#L42-L44) `--versions` flag 定义；[`cmd/rm-main.go:275-279`](https://github.com/minio/mc/blob/c652022dab9d18387d8f5f37e69033c5f351da54/cmd/rm-main.go#L275-L279) `--force` IRREVERSIBLE warning；[`cmd/rm-main.go:714-752`](https://github.com/minio/mc/blob/c652022dab9d18387d8f5f37e69033c5f351da54/cmd/rm-main.go#L714-L752) 软删 vs 硬删路由；[`cmd/undo-main.go`](https://github.com/minio/mc/blob/c652022dab9d18387d8f5f37e69033c5f351da54/cmd/undo-main.go) undo 实现
- RustFS 源码：[`crates/ecstore/src/set_disk.rs:2632-2679`](https://github.com/rustfs/rustfs/blob/20bb5dc4a2bd82d30c7699a3898924b10f091952/crates/ecstore/src/set_disk.rs#L2632-L2679) `resolve_delete_version_state` 软删/硬删分支；[`crates/ecstore/src/disk/local.rs:1453-1458`](https://github.com/rustfs/rustfs/blob/20bb5dc4a2bd82d30c7699a3898924b10f091952/crates/ecstore/src/disk/local.rs#L1453-L1458) paginator bug 被注释掉的 `all_hidden` guard；[`crates/ecstore/src/store_list_objects.rs:482-501`](https://github.com/rustfs/rustfs/blob/20bb5dc4a2bd82d30c7699a3898924b10f091952/crates/ecstore/src/store_list_objects.rs#L482-L501) 第二处 truncation 重判 bug；[`crates/ecstore/src/bucket/lifecycle/core.rs:705-735`](https://github.com/rustfs/rustfs/blob/20bb5dc4a2bd82d30c7699a3898924b10f091952/crates/ecstore/src/bucket/lifecycle/core.rs#L705-L735) NoncurrentVersionExpiration 引擎；[`crates/e2e_test/src/delete_objects_versioning_test.rs`](https://github.com/rustfs/rustfs/blob/20bb5dc4a2bd82d30c7699a3898924b10f091952/crates/e2e_test/src/delete_objects_versioning_test.rs) E2E 测试
- AWS S3 spec：[Lifecycle 配置元素](https://docs.aws.amazon.com/AmazonS3/latest/userguide/intro-lifecycle-rules.html)、[Object versioning](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Versioning.html)、[Working with delete markers](https://docs.aws.amazon.com/AmazonS3/latest/userguide/DeleteMarker.html)

## 10. 客户端选型：mc + boto3 是 RustFS 首选搭配（互为补集，不要只信一个）

### TL;DR — 推荐组合

**绝大多数对接 RustFS 的场景**：

- **CLI / 运维 / 一次性任务** → `mc`（MinIO Client，CLI 二进制）：交互式管理、shell 脚本里直接调、`cp / mirror / rm / rb / undo / ilm` 等"开箱即用"高层批量命令
- **Python 应用** → `boto3`（AWS 官方 Python SDK）：单对象 op (GetObject / PutObject / HeadObject / CopyObject) 最稳；可自写 worker pool 替代 mc
- **Go 应用** → `minio-go/v7`（MinIO 官方 Go SDK，**mc 内核同源**）：对 MinIO/RustFS 体系原生；写法简洁

注：**mc CLI 本身是 Go 单二进制**，不是 Python/Java 等其他语言的库。Python 想直接调 mc 只能 `subprocess.run(['mc', ...])` 子进程；想纯 Python = boto3 或 `minio` (PyPI 上 MinIO 官方 Python SDK，备选)。Go 应用想要 mc 等价能力 = import `minio-go/v7` + 自己拼 worker pool（mc 自己就是这么干的）。

**Python 上 mc vs boto3 没有"对立"** —— mc 不是 Python 库，是子进程；boto3 是 in-process SDK。**典型实战 pattern = boto3 处理 80% 工作 + subprocess(mc) 处理 mc 独有的高层命令 + 抗 paginator bug 的 list 操作**。

mc 与 boto3（以及对应 SDK）在不同 API 路径上各有 bug 表现不同，建议**混用 + crosscheck**（见下文表格）。

### "mc 是 Go 写的, boto3 是 Python 写的, 别的语言怎么办?"

**mc 是 Go 单一实现的 CLI 二进制**，没有别语言的"mc"。但 mc 的**内核**是 `github.com/minio/minio-go/v7` SDK，可以直接 import 到 Go 应用里用（mc 自己就是这么拼的）。

**boto3 是 Python 单一实现**（AWS 官方 SDK），名字独占 Python 生态。"boto" 是 Python 的命名传统。各语言 AWS SDK 名字都不同（`aws-sdk-go-v2` / `aws-sdk-java-v2` / `@aws-sdk/client-s3` 等），但功能等价。

各语言对接 RustFS 的 SDK 实情：

| 语言 | 主流 SDK | 备选（MinIO 官方） |
|---|---|---|
| **Python** | `boto3` | `minio` (PyPI 上的 MinIO 官方 SDK，写法更简洁) |
| **Go** | `minio-go/v7` (推荐，mc 内核同源，对 MinIO/RustFS 体系原生) | `aws-sdk-go-v2` (AWS 官方) |
| **JavaScript / TypeScript** | `@aws-sdk/client-s3` v3 (模块化) | `minio` (npm) |
| **Java** | `aws-sdk-java-v2` | `minio-java` |
| **Rust** | `aws-sdk-s3` (AWS 官方) | `minio-rs` (社区，较新) |
| **C++ / .NET / Ruby / PHP** | `aws-sdk-cpp` / `aws-sdk-net` / `aws-sdk-ruby` / `aws-sdk-php` | MinIO 各语言 SDK 大多都有 |

**没有跨语言"mc 等价物"**：`mc cp / mirror / rb --force / undo / rm --recursive` 这些高层批量命令全是 mc 自己用 minio-go 拼出来的（如 mc 的 `ParallelManager` / `listAndRemove`），各语言 SDK 都**不**直接提供 — 各家应用要自己拼 30-100 行 worker pool 实现（pattern 见 §11）。直接 `os/exec` 调 mc binary 是最快上手的兜底方案，但生产应用一般还是自己拼 SDK + worker pool 干净。

### RustFS 官方推荐

[docs.rustfs.com/developer/mc.html](https://docs.rustfs.com/developer/mc.html) 把 MinIO Client (`mc`) 当作 first-class CLI（"RustFS is S3-compatible, you can use mc to manage RustFS objects"）。SDK 层 [developer/sdk/](https://docs.rustfs.com/developer/sdk/) 列了 Go / Java / JavaScript / TypeScript / Python / Rust + other —— 即任何 S3-compatible SDK（MinIO SDK 或 AWS SDK 系）都受官方背书。

### mc vs boto3 API 行为差异（实战速查）

| API / 操作 | mc 行为 | boto3 / AWS SDK 行为 | 优选 |
|---|---|---|---|
| `ListObjectsV2`（普通列对象）| 不信 IsTruncated，用 StartAfter 接力（versioning 桶上抗 bug）| 严格遵守 IsTruncated（被 RustFS server bug 骗）| **mc**（versioning 桶）<br>boto3（普通桶）|
| `ListObjectVersions`（列版本历史）| 同 paginator bug 但**无 StartAfter workaround** | 不同 endpoint，正确返回 | **boto3** |
| `GetObject` / `HeadObject` 单对象 | OK | OK | 任意 |
| `PutObject` 单对象 | OK | OK | 任意 |
| `CopyObject` 跨桶 server-side | `mc cp/mirror` 默认走 server-side（< 64MB CopyObject / ≥ 64MB ComposeObject）| `s3.copy_object()` 显式走 server-side | 任意；高并发追求慎用 mc（auto-scale 到 128 worker 易撞 RustFS timeout，见 `mess/references/rustfs.md`）|
| `mc mirror` 批量复制 | versioning 桶 + 大 prefix 偶发 silent fail（退码 0 + 0 transferred）| — | 改用 boto3 单对象 copy_object + 4 worker |
| `mc rm --recursive --force` 软删 prefix | OK | — | mc（简洁） |
| `mc rm --recursive --versions --force` 硬删全版本 | OK，按 vid 逐个 DeleteObject | — | mc |

### `mc rb --force` 真相（最容易踩的坑）

很多人直觉以为 `mc rb --force` = "桶里 obj 软删 + 桶元数据置删，反正 versions 还在能 mc undo"。**完全错**。看 [mc/cmd/rb-main.go::deleteBucket](https://github.com/minio/mc/blob/master/cmd/rb-main.go) 源码 50 行：

```go
opts := ListOptions{
    Recursive:         true,
    WithOlderVersions: true,    // ← 列所有 noncurrent versions
    WithDeleteMarkers: true,    // ← 列所有 DEL markers
}
for content := range clnt.List(ctx, opts) {
    contentCh <- content        // ← 每个 version 都送到 Remove
}
resultCh := clnt.Remove(...)    // ← DeleteObject(Key, VersionId=X) 逐个硬删
// 然后 clnt.RemoveBucket(ctx, true) 删空桶
```

MinIO 官方 docs 也明说："`mc rb` _permanently deletes bucket(s)_, **including any and all object versions** and bucket configurations such as lifecycle management or replication."

**结论**：`mc rb --force` 在 versioning 桶上 ≡ `mc rm --recursive --versions --force <bucket>` + `RemoveBucket()`，**100% 不可恢复**。"既软删 + 又删桶 + 保留可恢复" 在 versioning 桶上**逻辑不可能**（桶非空就删不了；桶要空就必须硬删 versions）。

想"看着桶里空但保留 versions" → `mc rm --recursive --force <bucket>` (不带 --versions, 桶保留)；想"彻底删桶 + 回收磁盘" → `mc rb --force <bucket>` (不可逆)。

### `x-minio-force-delete` header 在 RustFS 上的实际行为（实测）

MinIO 协议族有一个非标准 HTTP header `x-minio-force-delete: true`，发给 `DELETE /<bucket>` 让 server 端**一键清桶 + 所有 versions + DEL markers + 桶元数据**，不需要 client 先逐对象删。`minio-go` SDK 的 `RemoveBucket(ctx, forceDelete=true)` 第二参就是这条；mc 内部 fallback 路径也用它（看到 `BucketNotEmpty` 时调一次 force-delete 兜底）。

实测在 RustFS v1.0.0-beta.5 上：

```python
# 手拼 sigv4 直接打 RustFS HTTP
import requests, hashlib, hmac, datetime
# ...sigv4 签名省略...
headers = {'x-minio-force-delete': 'true', 'Authorization': ..., 'x-amz-date': ...}
resp = requests.delete('http://rustfs:9000/<bucket>', headers=headers, timeout=300)
```

行为观察：

| 项 | 行为 |
|---|---|
| RustFS 是否接受 header | ✅ 返回正常处理（不是 400 拒绝），HTTP 200 OK 待返但**很慢** |
| 操作粒度 | server 端遍历**所有** noncurrent versions + DEL markers + current obj + 桶元数据，全部删 |
| client 网络断开后 | ✅ **server 端继续执行**（异步 server-side job，不依赖 client 持续连接）|
| client read timeout | client 设 timeout=300s 就 timeout 出错，但**对 server 端 cleanup 进度无影响** |
| 实测耗时（145 万 current obj + ~几百万 noncurrent + DEL markers，HDD 后端）| **~4 小时**（client 22:50 发请求 5 min timeout 断；server 02:41 完成桶消失）|
| 速率 vs `mc rb --force` | mc rb 走 client-side list + 逐 obj delete (RustFS server ListObjectVersions 在大 versioning 桶上会 hang)；**force-delete header 是 server 内部直接清，绕过 list paginator bug，唯一能跑通的路径** |

**使用建议**：

- **`mc rb --force` 在大 versioning 桶 + 多 delete marker 上**：实测 `mc rb` 在 server 端 ListObjectVersions 阶段 hang（30+ min 不返），**不可用**
- **`x-minio-force-delete` header 直击 RustFS**：唯一稳态方式，但 client 别守，发完请求 disown 让 server 慢慢跑（小时级），过几小时检查 `mc ls <alias>/` 看桶是否消失
- **手写 boto3 worker pool 逐 obj 硬删**：能跑但速率受 HDD IOPS 限速，跟 server-side force-delete 同时跑实测 force-delete 先完成（race）；如果想 client 看进度可以同时跑作"心理慰藉"，但实际是浪费 IOPS（server 端 force-delete 一个人就够了）

**手写 force-delete 请求骨架（boto3 不直接支持这个 header，得手拼 sigv4）**：

```python
import requests, hashlib, hmac, datetime

def sigv4_delete_bucket(endpoint, ak, sk, bucket, headers=None):
    """对 RustFS/MinIO 发 DELETE /<bucket> 带任意 extra header (如 x-minio-force-delete)."""
    headers = dict(headers or {})
    t = datetime.datetime.now(datetime.UTC)
    amz_date = t.strftime('%Y%m%dT%H%M%SZ')
    date_stamp = t.strftime('%Y%m%d')
    payload_hash = hashlib.sha256(b'').hexdigest()
    headers['host'] = endpoint.split('//')[-1]
    headers['x-amz-content-sha256'] = payload_hash
    headers['x-amz-date'] = amz_date

    sorted_h = sorted(headers.items())
    canonical_headers = ''.join(f'{k}:{v}\n' for k, v in sorted_h)
    signed_headers = ';'.join(k for k, _ in sorted_h)
    canonical_request = f'DELETE\n/{bucket}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}'
    cred_scope = f'{date_stamp}/us-east-1/s3/aws4_request'
    string_to_sign = f'AWS4-HMAC-SHA256\n{amz_date}\n{cred_scope}\n{hashlib.sha256(canonical_request.encode()).hexdigest()}'

    k_date = hmac.new(f'AWS4{sk}'.encode(), date_stamp.encode(), hashlib.sha256).digest()
    k_region = hmac.new(k_date, b'us-east-1', hashlib.sha256).digest()
    k_service = hmac.new(k_region, b's3', hashlib.sha256).digest()
    k_signing = hmac.new(k_service, b'aws4_request', hashlib.sha256).digest()
    sig = hmac.new(k_signing, string_to_sign.encode(), hashlib.sha256).hexdigest()
    headers['Authorization'] = f'AWS4-HMAC-SHA256 Credential={ak}/{cred_scope}, SignedHeaders={signed_headers}, Signature={sig}'

    sess = requests.Session()
    sess.trust_env = False    # 跳过 OS proxy env (e.g. Mihomo/Clash)
    return sess.delete(f'{endpoint}/{bucket}', headers=headers, timeout=60, proxies={})

# 用法 - 一次性发, 不等返回, 让 server 端慢慢跑
try:
    sigv4_delete_bucket('http://rustfs:9000', 'AK', 'SK', 'my-big-bucket',
                        headers={'x-minio-force-delete': 'true'})
except requests.Timeout:
    pass    # server 端继续, 过几小时 mc ls 看桶是否还在
```


## 11. 大批量 op 的可靠性模式（实战补丁）

往 RustFS 桶上批量做 list/delete/copy 几万到几百万对象时，光用客户端默认设置经常 hang 或 silent fail。下面 6 个补丁是踩过坑后的稳态：

### (a) boto3 paginator 大桶慢 → per-shard 并发 list

`get_paginator('list_objects_v2').paginate(Bucket=X, Prefix=Y/)` 单进程串行扫一个百万级对象的桶要数小时（受 HDD seek 限速）。把"按桶级 prefix 列"改成"按 sub-prefix 并发列"，8 worker 同样数据可获 ~10× 加速：

```python
def list_shard(shard):
    local_s3 = make_s3()
    return shard, {(shard, parts[-2]) for page in paginate(Bucket=X, Prefix=f'{shard}/')
                    for obj in page['Contents']
                    for parts in [obj['Key'].split('/')] if len(parts) >= 3}

with ThreadPoolExecutor(max_workers=8) as p:
    futs = {p.submit(list_shard, s): s for s in shards}
    for fut in as_completed(futs):
        s, shard_set = fut.result()
        result |= shard_set
```

实测数据点（145 个 sub-prefix / 总 ~140 万对象 / HDD 后端）：单进程串行 ~4.4h vs 8 worker 并发 ~38 min。

### (b) `delete_objects` batch 1000 偶发 boto3 close-loop hang → batch 200 + retry + fallback per-object

`s3.delete_objects(Bucket=X, Delete={'Objects': [...1000 keys...]})` 在 RustFS versioning 桶上偶发触发 boto3 worker 进 `close(fd)` 死循环、主线程 futex 锁死（实测 strace 看到）。修法：

```python
BATCH_SIZE = 200    # 不是 1000
for attempt in range(3):
    try:
        resp = s3.delete_objects(Bucket=X, Delete={'Objects': batch, 'Quiet': True})
        break
    except Exception:
        if attempt == 2:
            # fallback: per-object delete (慢但稳)
            for o in batch:
                s3.delete_object(Bucket=X, Key=o['Key'])
        else:
            time.sleep(5 * (attempt + 1))
```

或者干脆**改用 `mc rm --recursive --force` 子进程**，mc 内部对此场景更稳。

### (c) 长跑脚本写 status.json 偶发 truncate + 死锁 → atomic tempfile + rename

`with open('status.json', 'w') as f: json.dump(...)` 在多线程 long-run 脚本里偶发 truncate 完后 boto3 worker 抢 GIL 卡死，外部进程看到 0 字节文件。修法：

```python
import tempfile
with tempfile.NamedTemporaryFile('w', dir=DIR, prefix='.status-', delete=False) as f:
    json.dump(state, f, indent=2)
    tmp = f.name
os.replace(tmp, STATUS_PATH)   # POSIX 原子 rename
```

这样最坏情况是 status.json 是某个 checkpoint 完整版本，永远不会 0 字节。

### (d) `mc ls` 子进程在 versioning 桶单 shard 偶发超时 → timeout 300s + retry × 2

单 shard 含几十万 delete marker 时 `mc ls <alias>/<bucket>/<shard>/` 偶发 > 60s，需要：

```python
def mc_list_shard(shard, attempt=0):
    try:
        r = subprocess.run([MC, 'ls', f'{ALIAS}/{BUCKET}/{shard}/'], env=MC_ENV,
            capture_output=True, text=True, timeout=300)  # 不是 60
        return shard, parse_zip_keys(r.stdout), None
    except Exception as e:
        if attempt < 2:
            time.sleep(5); return mc_list_shard(shard, attempt + 1)
        return shard, set(), str(e)
```

`as_completed` 收 future 时不要直接抛——要 catch 一下：

```python
for fut in as_completed(futs):
    s, val, err = fut.result()       # err is not None 时记录但不抛
    if err: failed.append((s, err))
```

否则单 shard timeout 直接炸整个 pool。

### (e) `mc mirror` 在 versioning 桶大 prefix silent fail → 用 boto3 + per-object copy_object

`mc mirror src/ dst/` 在 RustFS versioning 桶大 prefix 上经常**退码 0 + 0 transferred** 但实际 RX/TX 一点字节都没传（mc 内部 list comparison 撞 paginator bug → 提早判"src 和 dst 一样"了）。改用 boto3 单对象 server-side copy + 4 worker：

```python
def copy_one(src_key):
    s3 = make_s3()
    s3.copy_object(Bucket=DST, Key=f'test/{src_key}',
                   CopySource={'Bucket': SRC, 'Key': src_key})

with ThreadPoolExecutor(max_workers=4) as p:
    list(as_completed([p.submit(copy_one, k) for k in keys]))
```

### (f) 长跑脚本要 resume — 用 `head_object` skip 已存在 PUT

big batch upload 中途死了重启时不要重 PUT，先 head 查 dst 存在性（单对象 op 不走 paginator，永远稳）：

```python
def package_one(s3, src_bucket, src_items, dst_key, skip_if_exists=True):
    if skip_if_exists:
        try:
            s3.head_object(Bucket=DST, Key=dst_key)
            return existing_size, count, sha_from_existing, True   # skipped
        except s3.exceptions.ClientError as e:
            if e.response['Error']['Code'] not in ('NoSuchKey', '404', 'NotFound'):
                raise
    # ... build + put_object
```

实测：几万个对象已存在的 batch 重启时大部分 sub-prefix 几十秒内全 skip 跑完。

### 综合：可靠批处理脚本骨架

把上面 6 点拼起来 = 一个能跑几十万对象 + 数小时 + 容忍 host 重启 / partial fail 的稳态脚本：

```
全局: SHARD_WORKERS=2, ITEM_WORKERS=4, MAX_RETRIES=3
每对象: head_object skip → GetObject (src) → build → PutObject (dst) → retry on except
每 batch: status.json atomic write 当 checkpoint
delete: mc rm --recursive --force 子进程，timeout=300s + retry × 2
finalize: 独立 verify 抽样 (sha256 端到端) + reconcile (key set 对比)
```

