# 测法与瓶颈归因

量存储的第一个陷阱是**量错了维度**：一般人测盘只看顺序读写速度（`hdparm -t`、`dd` 跑出来的 MB/s），而那恰好是数据库最不在乎的那个数。第二个陷阱是**量到了缓存**：不绕过页缓存、随机范围不够大，读数会漂亮两个数量级。

本篇给出一套能把各层单独量出来的方法：先讲[该看哪些指标](#io-metrics)，再讲 [fio 基线命令](#fio-baseline)与两个最容易读错的变量（[队列深度](#queue-depth)、[写缓存](#write-cache-bias)），最后是 fio 量不到的[小文件元数据](#smallfile-bench)。把结果落到具体后端上见 [backend.md](backend.md)。

## <a id="testbed"></a>实测环境

本篇与 [backend.md](backend.md) 的实测数字出自同一次迁移：把一个 428 GB、含向量索引的 PostgreSQL 库从网络存储搬到本地 SSD，顺带把三套存储横着量了一遍。两个占位符指代该环境：

| 占位符 | 指代 |
|---|---|
| `<NAS>` | 千兆以太网接入的商用 NAS，导出一个精简置备 iSCSI LUN（名义 3 TB、实用 435 GB），后端是带校验的机械盘阵列。**它不是直连块设备**，完整访问链路见 [链路的完整构成](backend.md#link-composition) |
| `<多盘服务器>` | 迁移目标机：一张 LSI 系硬 RAID 卡下挂 2 片企业级 SATA SSD（RAID1）与 8 片大容量 HDD（RAID50）；125 GiB 内存 / 48 线程 |

## <a id="io-metrics"></a>数据库敏感的 I/O 指标

一般人测盘只看一个数：顺序读写速度（`hdparm -t`、`dd` 跑出来的 MB/s）。**对数据库来说这个数几乎没用。**

数据库真正吃的是另外三个：

| 指标 | 通俗解释 | 影响什么 |
|---|---|---|
| **fsync 延迟** | 「确认这笔数据真落盘了」要等多久 | 每次事务提交，**最关键** |
| **随机 IOPS** | 每秒能处理多少个零散的小块读写 | 索引查找、随机扫描 |
| 顺序带宽 | 连续大块数据的传输速度 | 全表扫描、备份、恢复 |

fsync 延迟排第一，是因为**每提交一次事务都要等一次 fsync**——这个延迟直接乘在每秒事务数上。顺序带宽排最后，是因为数据库很少真在做纯顺序 I/O。

这个排序不是修辞：本次实测里，8 盘 HDD 阵列的顺序读比 SSD 镜像还快一倍，fsync 却慢 83 倍（数据见[后端横向实测](backend.md#media-benchmark)）。只看带宽会直接得出「用 HDD 阵列」的错误结论。

> 也因此 `hdparm -t` 和 `dd` 这类工具不适合给数据库选盘——它们量的正好是数据库最不在乎的那个维度。

## <a id="fio-baseline"></a>fio 基准命令与参数语义

`fio` 是唯一能把上面三个数分开量的常用工具。三条命令覆盖全部。

测试会在目标文件系统上写入并持续读写一个最大 4 GiB 的测试文件，先确认用户授权在该文件系统上做写入测试，并核对可用空间。测试文件放在目标文件系统上专门为测试新建的目录里：

```bash
test_dir="<目标文件系统上新建的测试目录>"
mkdir -p "$test_dir"

# ① fsync 延迟（最重要）：单线程 8K 随机写，每写一笔就 fsync
#    模拟的就是数据库提交事务
fio --name=commit --filename="$test_dir/testfile" --size=2G \
    --bs=8k --rw=randwrite --ioengine=libaio \
    --iodepth=1 --fsync=1 --direct=1 \
    --runtime=25 --time_based

# ② 随机写 IOPS：深队列并发
fio --name=wiops --filename="$test_dir/testfile" --size=4G \
    --bs=8k --rw=randwrite --ioengine=libaio \
    --iodepth=32 --numjobs=4 --direct=1 \
    --runtime=25 --time_based --group_reporting

# ③ 随机读 IOPS
fio --name=riops --filename="$test_dir/testfile" --size=4G \
    --bs=8k --rw=randread --ioengine=libaio \
    --iodepth=32 --numjobs=4 --direct=1 \
    --runtime=25 --time_based --group_reporting
```

几个参数的意思，因为选错了结果会完全不同：

- `--direct=1`：绕过操作系统的页缓存。**不加这个测的就是内存速度**，数字漂亮但没意义。
- `--iodepth`：同时压多少个请求，见[队列深度的语义与瓶颈判读](#queue-depth)。
- `--fsync=1`：每写一笔就强制落盘，这才是数据库提交的真实行为。
- `--bs=8k`：对齐 PostgreSQL 的默认页大小，量出来的数才和数据库行为对得上。
- 测试文件测完默认保留，报告路径与占用；清理由用户决定。

## <a id="queue-depth"></a>队列深度的语义与瓶颈判读

`--iodepth` 是「同时在飞的请求数」。`dd` 和 `hdparm` 默认都是发一个等一个（相当于 QD=1），所以它们的读数在高延迟设备上会被严重低估——同一套网络存储，QD 从 1 提到 8，顺序读涨了 36%（数据见[队列深度扫描下的顺序读](backend.md#qd-sweep)）。

反过来，扫一遍队列深度也能告诉你瓶颈在哪：

- **提高 QD 速度明显上升** → 之前卡在**延迟**上（在等往返，不是带宽不够）
- **提高 QD 速度几乎不变** → 已经**撞到带宽天花板**

## <a id="write-cache-bias"></a>写缓存对 fsync 读数的干扰

存储设备（RAID 卡、NAS 控制器）都有写缓存。数据量小又是顺序的时候，缓存全吃下，立刻回一句「写好了」，fsync 看起来飞快；一旦进入持续随机写，缓存被打穿，每一笔都得真等磁盘，性能直接塌方。本次实测里同样是「8K 写 + fsync」，两种测法差了 64 倍（数据与事故见[写缓存打穿与 checkpoint 停滞](backend.md#write-cache-breakdown)）。

规避办法只有两条：

- 随机写的范围要**大到打穿缓存**（远超缓存容量，比如上面命令里的 `--size=4G` 起步，缓存大就再加）
- 或者干脆在真实负载下观察，别在空闲时随手测一发就下结论

## <a id="smallfile-bench"></a>小文件元数据基准

fio 量的是数据面。**远端接入层真正的瓶颈通常在元数据面**——创建、`stat`、遍历、删除，每个操作一次网络往返，fio 一个字都不告诉你。用固定数量的空文件做相对比较即可：

同样先确认用户授权在目标范围创建测试文件：

```bash
d="<目标文件系统上新建的测试目录>"
mkdir -p "$d"
start=$(date +%s%N)
i=1; while [ $i -le 200 ]; do touch "$d/f$i"; i=$((i+1)); done
mid=$(date +%s%N)
# 删除的只是上面创建的这 200 个测试文件，先取得用户本轮的明确批准
rm "$d"/f{1..200}
end=$(date +%s%N)
echo "create_ms=$(( (mid-start)/1000000 )) delete_ms=$(( (end-mid)/1000000 ))"
```

删除这一步删的就是本次创建的 200 个测试文件，动手前先取得用户本轮的明确批准；只测创建就去掉 `rm` 那行。

一次实际案例：同一 SMB share 在 WSL `drvfs/9p` 下创建 200 个空文件约 1912ms、删除约 624ms；改成 CIFS 后创建约 613ms、删除约 364ms。
