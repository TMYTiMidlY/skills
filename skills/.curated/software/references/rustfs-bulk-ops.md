# RustFS 大批量 op 的可靠性模式

> 往 RustFS 桶上批量做 list / delete / copy 几万到几百万对象时，光用客户端默认设置经常 hang 或 silent fail。下面是踩过坑后的稳态补丁。主文档（versioning 语义、列举 bug、copy timeout、性能特征）在 [rustfs.md](rustfs.md)。
>
> ⚠️ **前置**：所有"靠 `list_objects_v2` 列源"的步骤，在 `≤ beta.7`（列举截断 bug 未修，见 [rustfs.md §4](rustfs.md)）的服务端上会**静默漏列**。受影响版本上列源改走 `list_object_versions()` / `mc ls --versions` 过滤可见集，或升级到 `1.0.0-beta.8`+（已含修复）。

## (a) 大桶 list 慢 → per-shard 并发 list

`get_paginator('list_objects_v2').paginate(Bucket=X, Prefix=Y/)` 单进程串行扫百万级对象的桶要数小时（HDD seek 限速）。把"按桶级 prefix 列"改成"按 sub-prefix 并发列"，8 worker 同样数据 ~10× 加速：

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def list_shard(shard):
    s3 = make_s3()
    pag = s3.get_paginator('list_objects_v2')
    return shard, [obj['Key'] for page in pag.paginate(Bucket=BUCKET, Prefix=f'{shard}/')
                   for obj in page.get('Contents', [])]

result = {}
with ThreadPoolExecutor(max_workers=8) as p:
    futs = {p.submit(list_shard, s): s for s in shards}
    for fut in as_completed(futs):
        s, keys = fut.result()
        result[s] = keys
```

实测（145 个 sub-prefix / 总 ~140 万对象 / HDD 后端）：单进程串行 ~4.4h vs 8 worker 并发 ~38 min。

## (b) `delete_objects` batch 1000 偶发 hang → batch 200 + retry + fallback per-object

`s3.delete_objects(Delete={'Objects':[...1000 keys...]})` 在 RustFS versioning 桶上偶发触发 boto3 worker 卡死（strace 看到 `close(fd)` 死循环 + 主线程 futex 锁死）。修法：batch 缩到 200 + 重试 + 兜底逐对象删。

```python
BATCH_SIZE = 200    # 不是 1000
for attempt in range(3):
    try:
        s3.delete_objects(Bucket=X, Delete={'Objects': batch, 'Quiet': True})
        break
    except Exception:
        if attempt == 2:
            for o in batch:                       # fallback：逐对象，慢但稳
                s3.delete_object(Bucket=X, Key=o['Key'])
        else:
            time.sleep(5 * (attempt + 1))
```

或干脆改用 `mc rm --recursive --force` 子进程，mc 内部对此场景更稳。

## (c) 长跑脚本写 status.json 偶发 truncate → atomic tempfile + rename

`with open('status.json','w') as f: json.dump(...)` 在多线程 long-run 脚本里偶发 truncate 完后 worker 抢 GIL 卡死，外部进程看到 0 字节文件。改成原子写：

```python
import tempfile, os, json
with tempfile.NamedTemporaryFile('w', dir=DIR, prefix='.status-', delete=False) as f:
    json.dump(state, f, indent=2)
    tmp = f.name
os.replace(tmp, STATUS_PATH)   # POSIX 原子 rename：最坏情况是上一个完整 checkpoint，永不 0 字节
```

## (d) `mc ls` 子进程偶发超时 → timeout 300s + retry，且别让单 shard 炸整个 pool

单 shard 含几十万 delete marker 时 `mc ls` 偶发 > 60s：

```python
def mc_list_shard(shard, attempt=0):
    try:
        r = subprocess.run([MC, 'ls', '--versions', f'{ALIAS}/{BUCKET}/{shard}/'],
                           env=MC_ENV, capture_output=True, text=True, timeout=300)  # 不是 60
        return shard, parse_keys(r.stdout), None
    except Exception as e:
        if attempt < 2:
            time.sleep(5); return mc_list_shard(shard, attempt + 1)
        return shard, set(), str(e)

for fut in as_completed(futs):
    s, val, err = fut.result()     # catch，别直接 raise
    if err: failed.append((s, err))  # 否则单 shard timeout 直接炸整个 pool
```

## (e) `mc mirror` 在 versioning 桶大 prefix silent fail → boto3 per-object copy

`mc mirror src/ dst/` 在 versioning 桶大 prefix 上经常**退码 0 + 0 transferred** 却一个字节没传（mc 内部 list 比对撞列举 bug，误判"src 和 dst 已一致"）。改用 boto3 单对象 server-side copy + 限并发 worker：

```python
def copy_one(src_key):
    s3 = make_s3()
    s3.copy_object(Bucket=DST, Key=f'test/{src_key}',
                   CopySource={'Bucket': SRC, 'Key': src_key})

with ThreadPoolExecutor(max_workers=4) as p:   # 4 worker，别飙太高（见 rustfs.md §5 timeout）
    list(as_completed([p.submit(copy_one, k) for k in keys]))
```

## (f) 断点续传 → `head_object` skip 已存在的 PUT

大批量上传中途死了重启时别重 PUT，先 head 查 dst 存在性（单对象 op 不走列举分页，永远稳）：

```python
def package_one(s3, dst_key, skip_if_exists=True):
    if skip_if_exists:
        try:
            s3.head_object(Bucket=DST, Key=dst_key)
            return True   # 已存在 → skip
        except s3.exceptions.ClientError as e:
            if e.response['Error']['Code'] not in ('NoSuchKey', '404', 'NotFound'):
                raise
    # ... build + put_object
    return False
```

实测：几万个对象已存在的 batch 重启时大部分几十秒内全 skip 跑完。

## 综合：可靠批处理脚本骨架

把上面拼起来 = 能跑几十万对象 + 数小时 + 容忍 host 重启 / partial fail 的稳态：

```
全局: SHARD_WORKERS=2, ITEM_WORKERS=4, MAX_RETRIES=3
列源: per-shard 并发（受影响版本走 list_object_versions）
每对象: head_object skip → GetObject(src) → build → PutObject(dst) → retry on except
每 batch: status.json 原子写当 checkpoint
delete: mc rm --recursive --force 子进程，timeout=300s + retry × 2
finalize: 抽样 sha256 端到端校验 + key set 对比 reconcile
```
