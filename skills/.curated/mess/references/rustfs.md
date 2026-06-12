# mc/RustFS 跨桶迁移：CopyObject 行为 + HTTP 500 `Io error: timeout`

> S3 `CopyObject` API 在 mc / RustFS 里到底跑在哪一侧、有没有"快路径"、谁会撞 timeout 限制；以及大批量 `mc cp/mirror` 跨桶 server-side copy 在 RustFS 上单 prefix 内部分 object 成功、整 prefix 被标 fail 的全程排查。

## 元教训（最先抓）

**别凭印象判 root cause——这条 case 我连续错判 3 次，每次都是脑补 + 没去翻源码。**

| 凭印象 | 实际 | 怎么 verify |
|---|---|---|
| "client 网卡跑了几 GB → mc 是 client-relay" | mc 默认 server-side CopyObject / ComposeObject（client 不传字节） | `mc --debug cp src dst` 看 PUT 请求是否带 `x-amz-copy-source` header；或 `rg "CopyObject\|ComposeObject" mc/cmd/client-s3.go` |
| "RustFS 报 500 = RustFS 不支持 CopyObject" | RustFS 完整支持 `handle_copy_object` + multipart `handle_copy_object_part` | `rg "handle_copy_object" rustfs/crates/`；再用 boto3 `s3.copy_object()` smoke 一个 obj 走通 200 |
| "P99 慢 = 网络 RTT bound" | HTTP keep-alive 摊销 RTT 到 ms 级，真 bound 是后端 HDD IOPS | 对同 prefix 里的 obj 跑 HEAD × 10 看延迟分布；看 server 机器 `uptime` load average |

**反射**：S3 一类协议的复杂行为，**先 grep 客户端 + 服务端源码 + 跑 smoke test verify**，再决定"哪一层是 root cause"。凭网络监控的间接观察很容易被并发任务 / 其它流量误导。

## 症状

- `mc mirror src-bucket/prefix/ dst-bucket/prefix/` 跑一会儿后某些 prefix 标 fail
- 同一个 mirror log 显示**大部分 obj 在同 prefix 内成功 transfer**（一行行 `src/obj -> dst/obj`），但少数 obj 触发 mc 退出码非零 → 整 prefix 被脚本标 fail（如果脚本按 prefix 粒度判 success）
- `mc --debug` 看到 server 返回：

```
HTTP/1.1 500 Internal Server Error
<Error><Code>InternalError</Code><Message>Io error: timeout</Message></Error>
Response Time: 5.19s
```

## 排查走过的弯路

### 弯路 1：以为 mc cp/mirror 是 client-relay（client 下载 + client 上传）

观察现象：mc 跑期间 client host 网卡 RX/TX 几 GB → 直觉判定 client-relay。

**实际错**：测时 client host 上还跑着别的并发任务（其他 mirror / sync）占网卡。

**verify 方法**：`mc --debug cp src dst` 看 PUT request header 是否含 `x-amz-copy-source` —— 含 = server-side CopyObject API call（client 不传字节）。也可以从 mc 源码 `cmd/client-s3.go:986` 看 default 走 `CopyObject` (< 64MB) 或 `ComposeObject` (≥ 64MB, multipart server-side copy)，**两个都是 server-side**。

```go
// mc/cmd/client-s3.go:986-991
if opts.disableMultipart || opts.size < 64*1024*1024 {
    _, e = c.api.CopyObject(ctx, destOpts, srcOpts)
} else {
    _, e = c.api.ComposeObject(ctx, destOpts, srcOpts)
}
```

mc cp 和 mc mirror 都默认 server-side。**误判 client-relay 多半是别的并发任务占网卡误导**。

### 弯路 2：以为 RustFS 不支持 CopyObject

`grep -rn "copy_object\|CopyObject" rustfs/crates/` 验证 RustFS 端有 `handle_copy_object`（`crates/ecstore/src/store/object.rs:270`）+ multipart `handle_copy_object_part`。

再用 boto3 直调 `s3.copy_object()` smoke 一个 obj → 99ms 完成 HTTP 200 → CopyObject API **完全支持**。

### 弯路 3：以为是稳定坏 obj 或网络 RTT bottleneck

对一个持续 fail prefix 里的 obj 做 boto3 HEAD × 10 次：**全 OK 9-174ms**。obj 没物理坏，单 op 也快。

也排除 RTT bound — HTTP keep-alive 在 mc 内部摊销 RTT，per-obj overhead 几十 ms。

## 根因

1. **mc 用 `ParallelManager` auto-scale 并发**（`mc/cmd/parallel-manager.go`）：从少 worker 开始，每 4 秒看带宽决定是否加 worker，上限 `maxParallelWorkers = 128`。
2. 后端 S3 server 跑在物理 HDD 上（SATA HDD 100-200 IOPS）+ CPU 弱（嵌入式 / 多 container 抢资源）→ 高并发瞬时 disk op 队列堆积 → 单 disk op 等待时间超过 RustFS 内部 adaptive timeout 下限 → server 返 500 `Io error: timeout`。
3. RustFS adaptive timeout 配置在 `crates/io-core/src/timeout_wrapper.rs`：

```rust
// 默认 base_timeout 5s + per-MB 100ms，clamp [min_timeout, max_timeout]
// 实际 RustFS 启动时从 env 读 GetObject timeout policy:
//   rustfs/src/storage/timeout_wrapper.rs::GetObjectTimeoutPolicy::from_env()
//   RUSTFS_OBJECT_MIN_TIMEOUT default 5s  ← 这是 adaptive 下限
//   RUSTFS_OBJECT_DISK_READ_TIMEOUT default 10s
//   RUSTFS_OBJECT_GET_TIMEOUT default 30s
```

NAS HDD 在高并发瞬间排队 → 单 op 撞 5s 下限 → 500。

CopyObject 在 RustFS 内部不是 server-side disk linking，而是 `read src + put_object to dst`（`crates/ecstore/src/store/object.rs:319` 走标准 put_object pipeline），所以受 GetObject 端 timeout 影响。

含义：

- 对 client 看是一次 PUT（带 `x-amz-copy-source`），不传字节
- 对 RustFS server 看是**一次 Get + 一次 Put 都打在自家 disk 上**
- 受 GetObject 端 + PutObject 端的**所有 timeout / 限流逻辑**约束

所以"server-side"≠"零成本"。底层 HDD IOPS 撑不住时，CopyObject 跟普通 Put 一样会撞 timeout 返 500。

## 解

按从轻到重：

1. **mc 加 `--max-workers 4`（或 8 / 16）限制并发**。default auto-scale 到 128 太多，限到 NAS IOPS 撑得住的并发数。trade-off：速度慢但稳。需要 smoke 找 NAS 上的 sweet spot。

2. **包外层 retry-per-prefix loop**（脚本层）：单 prefix mc mirror fail → sleep 30s → 重试 3 次。对偶发 timeout 收敛率好；对持续撞 timeout 的大 prefix 救不回（仍 3-fail）。

3. **调高 RustFS server timeout env**（需要改 docker compose + restart RustFS container）：

```yaml
environment:
  RUSTFS_OBJECT_MIN_TIMEOUT: "60"        # adaptive timeout 下限 5s → 60s
  RUSTFS_OBJECT_DISK_READ_TIMEOUT: "60"  # 10s → 60s
  RUSTFS_OBJECT_GET_TIMEOUT: "120"       # 30s → 120s
```

注意：`RUSTFS_OBJECT_MIN_TIMEOUT` 在 `GetObjectTimeoutPolicy::from_env()` 用，**只覆盖 GetObject 路径**；CopyObject 内部走 GetObject + PutObject，PutObject 端是否有对应 env 没验证（grep 没找到 `RUSTFS_OBJECT_PUT_*` 类似 env），可能要看 PutObject path 自己的 timeout 源。

4. **根本解 = 后端硬件升级**：HDD → SSD / NVMe，更高 IOPS；或拆多 storage pool 分散 IO；或加 RAM cache。

## smoke：CopyObject 本身有没有坏

诊断时最快的"是不是 server 端 CopyObject API 坏了"判定：

```python
import boto3
s3 = boto3.client('s3', endpoint_url=..., aws_access_key_id=..., aws_secret_access_key=...)
s3.copy_object(
    CopySource={'Bucket': 'src', 'Key': 'path/obj'},
    Bucket='dst', Key='path/obj',
)  # 99ms 完成 200 = API 通；如果 500 = server 端 CopyObject 真坏
```

直接调 API 一次，几十~几百 ms 返回，分离掉"是 mc / 高并发 / timeout 引发的失败"还是"server 端真不支持 / obj 真坏"。

## 工具行为速查

| 行为 | 真实情况 |
|---|---|
| mc cp/mirror 跨桶 = client-relay? | ❌ Server-side（CopyObject < 64MB / ComposeObject ≥ 64MB） |
| mc 默认并发 | auto-scale up to 128 worker (ParallelManager) |
| `mc --max-workers N` | 显式限并发，对慢后端必需 |
| mc mirror per-prefix 失败粒度 | 单 obj fail 让 mc 退出码非零，需要外层脚本拦截判断 |
| RustFS CopyObject 实现 | server-side，但内部 = read src + put_object (不是 disk linking) |
| RustFS CopyObject 受 timeout env？ | 部分受：read 侧受 `RUSTFS_OBJECT_*_TIMEOUT`，write 侧没找到对应 env |
| `mc --debug cp` 看是否真 server-side | PUT 带 `x-amz-copy-source` header 即 server-side |
| boto3 直调 `copy_object()` | 也走 server-side CopyObject API |

## 排查 checklist

- [ ] mc 退出码非零时是不是 RustFS 返 500，看 `mc --debug` HTTP response
- [ ] 500 内容含 "Io error: timeout"? → adaptive timeout 撞
- [ ] 后端 server 所在机器 load average 是否长期超载（`uptime` 看 1m/5m/15m，对比 CPU core 数）
- [ ] 同一个 fail prefix 里的 obj 单独 HEAD 是否稳定 OK？稳定 OK = 不是坏 obj，是高并发 timeout
- [ ] 试 `--max-workers 4` smoke 1 个失败 prefix，能跑通 = 并发问题；仍 fail = 别的原因（看 RustFS 内部日志，需要 bind mount /logs 出来）

## 关键引用

- `mc/cmd/client-s3.go:986-991` — mc cp/mirror server-side copy 实现（CopyObject vs ComposeObject 决策）
- `mc/cmd/parallel-manager.go:34` — `maxParallelWorkers = 128` 上限
- `rustfs/crates/ecstore/src/store/object.rs:270` — `handle_copy_object`
- `rustfs/crates/ecstore/src/store/object.rs:319` — CopyObject = read src + put_object 走 standard pipeline
- `rustfs/crates/io-core/src/timeout_wrapper.rs` — TimeoutConfig + adaptive timeout
- `rustfs/rustfs/src/storage/timeout_wrapper.rs:96` — `GetObjectTimeoutPolicy::from_env()` 从 env 读 RUSTFS_OBJECT_MIN_TIMEOUT
- `rustfs/crates/config/src/constants/object.rs` — `ENV_OBJECT_MIN_TIMEOUT` / `ENV_OBJECT_GET_TIMEOUT` 等 env 名定义
