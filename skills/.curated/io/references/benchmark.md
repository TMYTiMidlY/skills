# 测法与瓶颈归因

先定义要测的工作负载，再选择指标。顺序吞吐、随机 IOPS、同步延迟和元数据操作回答的是不同问题，不能预先给它们排一个适用于所有数据库的次序。缓存也不是天然的测量错误：要分清测的是应用可见的缓存路径，还是尽量绕过客户端页缓存后的存储路径。

本篇先讲[指标选择](#io-metrics)，再讲 [fio 基线](#fio-baseline)、[队列深度](#queue-depth)、[写缓存](#write-cache-bias)和[小文件元数据](#smallfile-bench)。后端案例见 [backend.md](backend.md)；这里修正测量方法，不把历史数字当成对当前机器的保证。

## <a id="testbed"></a>实测环境

本篇与 [backend.md](backend.md) 的历史数字出自仓库记录的一次迁移：把一个 428 GB、含向量索引的 PostgreSQL 库从网络存储搬到本地 SSD，并比较三套存储。两个占位符指代该环境：

| 占位符 | 指代 |
|---|---|
| `<NAS>` | 千兆以太网接入的商用 NAS，导出一个精简置备 iSCSI LUN（名义 3 TB、实用 435 GB），后端是带校验的机械盘阵列。完整访问链路见[链路的完整构成](backend.md#link-composition) |
| `<多盘服务器>` | 一张 LSI 系硬 RAID 卡下挂 2 片企业级 SATA SSD（RAID1）与 8 片大容量 HDD（RAID50）；125 GiB 内存 / 48 线程 |

复测应记录 fio / 内核版本、文件系统与挂载、测试文件实际写入范围、缓存状态、I/O 引擎、并发、块大小、持续时间和原始输出。历史记录缺少的条件标为未记录，不用新命令反向补造旧测试的条件。

## <a id="io-metrics"></a>数据库敏感的 I/O 指标

指标随任务选择，不从“数据库”三个字直接推导优先级：

| 任务 | 首先观察 | 不能单独推导什么 |
|---|---|---|
| 小事务同步提交慢 | 事务延迟、WAL 写入 / 同步等待、并发和锁等待 | `1 / fsync 延迟` 不是整库 TPS 上限 |
| 索引访问或随机扫描慢 | 缓存命中、实际读取量、随机读延迟和 IOPS | 高随机写 IOPS 不代表随机读一定快 |
| 大表扫描、备份或恢复慢 | 顺序吞吐、读写量、CPU、压缩和网络 | 顺序带宽不是“对数据库没用” |
| 文件遍历、创建、删除慢 | 元数据操作延迟与缓存状态 | 大文件吞吐不能代表元数据性能 |

PostgreSQL 的 WAL 顺序写入，事务提交不要求同步刷出所有被修改的数据页；多个并发事务还可能共享一次 WAL 刷盘。存储微基准用于分解成本，最终需用代表性的数据库负载复核。

> 依据：[PostgreSQL 17 · WAL](https://www.postgresql.org/docs/17/wal-intro.html)及[组提交](https://www.postgresql.org/docs/17/wal-configuration.html)。数据库参数与 pgbench 的使用边界由 `software` skill 负责。

历史案例中，HDD 阵列的顺序读高于 SSD 镜像，而记录的同步延迟更高。这说明两者适合的访问模式可能不同，不构成对所有数据库负载的统一介质排名。

## <a id="fio-baseline"></a>fio 基准命令与参数语义

下面是 Linux 文件系统上的独立微基准，不是 PostgreSQL 事务模拟器。**写测试只允许在获准的专用临时目录运行，不得指向现有业务文件、PGDATA 或裸块设备。** 先确认空间、负载窗口和实际 `fio --version`；同名的其他程序不能代替 Flexible I/O Tester。

先把 `BENCH_ROOT` 设置为已存在、允许测试的目录。样例使用 1 GiB，只用于展示方法；它不保证超过机器或存储端的缓存容量。准备阶段必须成功后，才能单独运行后面的测量：

```bash
bench=$(mktemp -d "${BENCH_ROOT:?请先设置获准的测试目录}/.fio-bench.XXXXXX") || exit 1
fio --name=prepare --filename="$bench/data" --rw=write --bs=1m \
    --size=1G --ioengine=psync --direct=0 --end_fsync=1 || exit 1
```

准备阶段实际写入文件，不能只用 `truncate` / `fallocate` 创建逻辑大小后就拿空洞读数当磁盘读取能力。压缩、去重或精简置备后端还需核对物理分配与数据可压缩性；实际写过不等于已经排除所有服务端缓存。

```bash
# 小块顺序写 + 每次写后 fsync；观察 write 和 sync 各自的延迟
fio --name=sync-write --filename="$bench/sync-data" --size=1G \
    --rw=write --bs=8k --ioengine=psync --direct=0 --fsync=1 \
    --runtime=60 --time_based --output-format=json

# 随机读：单 job，名义最大 32 个在途请求；不允许创建新文件
fio --name=randread --filename="$bench/data" --size=1G \
    --rw=randread --bs=8k --ioengine=libaio --direct=1 --iodepth=32 \
    --numjobs=1 --readonly --allow_file_create=0 \
    --runtime=60 --time_based --output-format=json

# 顺序读：与随机读是不同工作负载，不混为一个“磁盘速度”
fio --name=seqread --filename="$bench/data" --size=1G \
    --rw=read --bs=1m --ioengine=libaio --direct=1 --iodepth=8 \
    --numjobs=1 --readonly --allow_file_create=0 \
    --runtime=60 --time_based --output-format=json
```

需要随机写吞吐时，另在专用测试文件运行 `rw=randwrite`；没有逐次同步的写吞吐不得标为“持久化提交吞吐”。保存各次原始输出，预热后重复运行，并同时比较吞吐、平均延迟和尾延迟。

| 参数 | 含义与边界 |
|---|---|
| `direct=1` | 请求非缓冲 I/O，通常使用 `O_DIRECT`；不等于绕过设备、控制器或服务端所有缓存，也不等于持久化 |
| `direct=0` | 走缓冲 I/O；结果可能包含缓存命中，也可能受实际磁盘、回写或同步限制，不能一概叫“只测内存” |
| `fsync=1` | 请求每次写后同步；fio 文档提醒非缓冲 I/O 下可能不执行该同步，所以同步样例使用 `psync` + `direct=0`，并核对输出中确有 sync 统计 |
| `iodepth` / `numjobs` | 每个 job 的目标在途请求数 / job 数；实际并发需看输出，不是只看命令行 |
| `bs=8k` | 一种小块访问尺寸；与 PostgreSQL 常见页大小相同，不代表复现了 WAL、组提交或查询行为 |

> 参数依据：[fio 3.39 · HOWTO](https://github.com/axboe/fio/blob/fio-3.39/HOWTO.rst)，其中 [fsync 与非缓冲 I/O](https://github.com/axboe/fio/blob/fio-3.39/HOWTO.rst#L1403-L1419)说明了同步边界。`libaio` 或 direct I/O 不受目标平台支持时，报告不适用；不要悄悄换引擎或缓存模式后继续横比。

## <a id="queue-depth"></a>队列深度的语义与瓶颈判读

`iodepth` 是每个 fio job 的目标在途 I/O 数。例如 `iodepth=32,numjobs=4` 的名义总上限是 128，而不是 32；引擎、内核和提交方式可能让实际深度低于目标。同步引擎不会因为把 `iodepth` 调大就变成异步引擎，先看 fio 输出的 I/O depth 分布。

提高深度后吞吐上升，只说明此前并发没有充分利用整条路径；吞吐不再上升，只说明这组条件下出现平台期。平台期可能来自链路带宽、设备 IOPS、CPU、锁、限速或根本没有达到设定深度，要结合带宽、设备和 CPU 计数定位。排队还可能继续抬高尾延迟，因此最高吞吐点不一定适合业务。

`dd` 的同步用户态调用不等于底层设备始终 QD=1：预读、回写和内核拆分请求也会影响设备队列。历史案例里 QD=1 到 QD=8 的顺序读增加约 36%，只能说明那组 fio 条件下增加并发有效，不能把所有 `dd` 测量统一“校正”36%。

> 依据：[fio 3.39 · I/O depth](https://github.com/axboe/fio/blob/fio-3.39/HOWTO.rst)。对应历史数值见[队列深度扫描](backend.md#qd-sweep)。

## <a id="write-cache-bias"></a>写缓存、同步与稳态

这里要分别回答“这次确认是否满足持久化契约”和“持续写入能维持什么吞吐”。具备有效掉电保护、正确处理 flush 的控制器缓存可以合法地使同步写很快；不能因为数据还在缓存中就认定 fsync 是假的。反之，普通易失性缓存忽略或虚假确认 flush 是可靠性问题，增大测试文件也证明不了断电安全。

> 设备缓存、掉电保护与刷盘语义见 [PostgreSQL 17 · Reliability](https://www.postgresql.org/docs/17/wal-reliability.html)。

历史记录中，小量顺序写与大范围随机写的同步读数差约 64 倍，但两者同时改变了访问模式和工作集。它支持“测试条件会显著影响结果”，不单独证明只有缓存容量造成差异，更不能把随机数据文件的同步延迟当作 WAL 提交延迟。

评估稳态时固定读写模式和并发，记录时间序列，再逐项改变工作集和持续时间。写入速率相对于后端回写速率、设备预处理、数据分布及其他负载都会影响结果；“文件大于缓存”既不是充分条件，也不是通用的固定 4 GiB 门槛。

## <a id="smallfile-bench"></a>小文件元数据基准

常规块读写任务不能替代创建、`stat`、遍历和删除测试。元数据操作可能由客户端缓存、服务端缓存或协议批处理完成，不能一概折算为“一次操作一次网络往返”。

下面仅测专用临时目录中的创建耗时。命令失败时不报告成功耗时；GNU `date` 的纳秒格式不适用的平台应换用本机单调时钟计时工具。

```bash
d=$(mktemp -d "${BENCH_ROOT:?请先设置获准的测试目录}/.mount-bench.XXXXXX") || exit 1
start=$(date +%s%N)
for i in $(seq 1 200); do touch "$d/f$i" || exit 1; done
end=$(date +%s%N)
echo "create_ms=$(( (end-start)/1000000 ))"
trash-put "$d"
```

回收站移动不是永久删除基准，不把 `trash-put` 的时间当成 `unlink` 的时间。异常中止遗留的测试目录按输出路径核对后再移至回收站；所有测试结束后，同样用 `trash-put "$bench"` 清理 fio 目录。

仓库保留的一次历史 SMB 对照为：WSL `drvfs/9p` 创建 200 个空文件约 1912 ms、永久删除约 624 ms；CIFS 创建约 613 ms、永久删除约 364 ms。这些删除数来自旧的永久删除测试，不是上面的回收站操作，也不保证在其他挂载或缓存条件下复现。
