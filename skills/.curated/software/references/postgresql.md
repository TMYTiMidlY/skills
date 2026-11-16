# PostgreSQL 读写性能的影响因素：容器、存储介质与网络链路

本篇把「影响 PG 读写性能」的变量拆成三层，每层都给机理、测法和实测数：

- [容器](#container)：Docker 与原生部署的 I/O 路径差异，以及 SSD + HDD 混用时冷热分层在两种部署下的落地成本
- [存储介质](#media)：本地 SSD 镜像、本地 HDD 阵列、网络 LUN 三种后端拉开的差距
- [网络链路](#network)：千兆 iSCSI 在其中占多少

数据来自一次真实迁移：把一个 428 GB、含向量索引的 PostgreSQL 库从网络存储搬到本地 SSD，顺带把三套存储横着量了一遍。全文用两个占位符指代环境：

| 占位符 | 指代 |
|---|---|
| `<NAS>` | 千兆以太网接入的商用 NAS，导出一个精简置备 iSCSI LUN（名义 3 TB、实用 435 GB），后端是带校验的机械盘阵列。**它不是直连块设备**，完整访问链路见[链路的完整构成](#link-composition) |
| `<多盘服务器>` | 迁移目标机：一张 LSI 系硬 RAID 卡下挂 2 片企业级 SATA SSD（RAID1）与 8 片大容量 HDD（RAID50）；125 GiB 内存 / 48 线程 |

## <a id="metrics"></a>指标与测量方法

先识别工作负载，再选择存储指标。这里采用 PostgreSQL 17 的机制说明；历史数值是前述迁移环境的记录，不是本次重新跑出的基准。缺少原始输出或配置时，应保留“不足以归因”的结论。

### <a id="io-metrics"></a>工作负载与 I/O 指标

| 工作负载 | 重点观察 | 不能直接得出的结论 |
|---|---|---|
| 单连接小事务，同步提交 | 完整事务延迟、WAL 写入与同步、网络往返 | 事务延迟不等于单次文件 fsync 延迟 |
| 高并发小事务 | TPS、尾延迟、组提交、CPU 和锁等待 | `1 / fsync 延迟` 不是整库吞吐上限 |
| 索引访问、随机扫描 | 缓存命中、实际读量、随机读延迟与 IOPS | 随机写结果不能代替随机读结果 |
| 大表扫描、备份、恢复 | 顺序吞吐、CPU / 压缩与网络 | 顺序带宽不能被一概排到最后 |

正常的持久化写事务先保证相关 WAL（预写日志）满足提交时的同步要求，不必在每次提交时把该事务修改的所有数据页刷盘。WAL 是顺序写入；组提交允许多个事务共享一次 WAL 刷盘。因此，“8 KiB 随机写一次、同步一次”只是一个存储访问模式，不是完整的 PostgreSQL 提交路径。

> 依据：[PostgreSQL 17 · WAL](https://www.postgresql.org/docs/17/wal-intro.html)与[组提交](https://www.postgresql.org/docs/17/wal-configuration.html)。

对比前记录 `fsync`、`synchronous_commit`、`wal_sync_method` 以及同步复制配置。异步提交可以在日志持久化前返回，配置了同步复制时提交等待还可能包含备库；不同持久性要求的结果不能直接排名。不要为了提高基准成绩关闭 `fsync`，也不要把异步提交与关闭 `fsync` 的风险混为一谈。

> 配置语义见 [PostgreSQL 17 · WAL 参数](https://www.postgresql.org/docs/17/runtime-config-wal.html)及[异步提交](https://www.postgresql.org/docs/17/wal-async-commit.html)。

### <a id="fio-baseline"></a>存储微基准与 WAL 同步测试

`fio` 测量的是所选文件或设备的访问模式；它不包含 SQL、锁、WAL 组提交和查询执行。8 KiB 只是一个块大小，不因它接近默认数据页大小就自动等价于数据库行为。通用 fio 准备、随机 / 顺序读写与安全边界由 `io` skill 负责。

比较 WAL 所在文件系统的同步方法，可以使用 `pg_test_fsync`。先把 `BENCH_ROOT` 指向**已获准、位于相同文件系统但不属于 PGDATA / pg_wal 的独立测试目录**，确认负载窗口和可用空间；不能拿现有数据库文件充当测试文件：

```bash
bench=$(mktemp -d "${BENCH_ROOT:?请先设置获准的独立测试目录}/.pg-fsync.XXXXXX") || exit 1
pg_test_fsync -f "$bench/test.out" || exit 1
trash-put "$bench"
```

这给出不同 WAL 同步方法的相对成本，不给出数据库 TPS，也不验证设备的断电可靠性。测试失败时保留诊断，确认残留路径后再移至回收站。

> 用途与限制见 [PostgreSQL 17 · pg_test_fsync](https://www.postgresql.org/docs/17/pgtestfsync.html)。实际 WAL 同步方式可能使用显式同步调用或同步写选项，不能把所有方法都当作同一种 `fsync()` 调用。

使用 fio 补测时，明确区分缓冲 I/O、direct I/O 与持久化同步。`direct=1` 不等于绕过所有设备缓存或保证持久化；缓冲模式也不一定只测内存。原文的 `libaio + direct=1 + fsync=1` 参数组合不能单凭命令行证明每次写都执行了预想的同步，应核对原始 sync 统计。测显式同步成本时可用 `psync + direct=0 + fsync=1` 的独立文件微基准，但仍不将其命名为事务提交测试。

> [fio 3.39 · fsync 参数](https://github.com/axboe/fio/blob/fio-3.39/HOWTO.rst#L1403-L1419)明确提醒，非缓冲 I/O 下可能不执行该同步。历史数字保留在后文，不能用新的参数说明反向补造旧测量的条件。

### <a id="queue-depth"></a>队列深度与并发

fio 的 `iodepth` 是每个 job 的目标在途请求数，实际深度还受引擎、内核和提交方式影响，必须核对输出中的深度分布。提高深度后吞吐上升说明此前并发未充分利用路径；出现平台期可能是设备、链路、CPU、锁或限速所致，不能只凭曲线断定带宽耗尽。排队还可能增加尾延迟。

`dd` 的同步用户态调用不能直接等同于底层设备始终 QD=1，预读和回写也会形成设备请求。后文记录的约 36% 差异只属于那组测量条件，不是所有工具读数的修正系数。

> 参数语义见 [fio 3.39 · HOWTO](https://github.com/axboe/fio/blob/fio-3.39/HOWTO.rst)。历史数值见[队列深度扫描](#qd-sweep)。

### <a id="write-cache-bias"></a>写缓存、同步与稳态

具备有效掉电保护且正确处理 flush 的控制器缓存可以合法地加速同步写；“还在缓存中”不等于持久化失败。易失性缓存虚假确认 flush 则是可靠性问题，不能靠扩大文件来证明安全。

原案例的小量顺序写与大范围随机写同时改变了工作集和访问模式，读数相差约 64 倍不能单独归因为缓存容量，更不能把随机数据文件同步成本换算为 WAL 提交延迟。评估持续负载应固定模式和并发、记录时间序列，再逐项改变工作集及持续时间；“大于缓存”或“至少 4 GiB”都不是充分条件。

> 设备缓存与刷盘契约见 [PostgreSQL 17 · Reliability](https://www.postgresql.org/docs/17/wal-reliability.html)。原数字及 checkpoint 日志见[历史同步测试](#write-cache-breakdown)。

### <a id="pgbench"></a>pgbench 端到端复核

先确认目标是**已建立、允许破坏性初始化的独立测试数据库**。`pgbench -i` 会删除并重建同名 `pgbench_*` 表，不能在业务库里随手运行。按可用空间和所需缓存状态选择规模，不仅与 `shared_buffers` 比较，还要考虑操作系统页缓存及工作集访问分布。

下面分组展示命令，不表示应在未确认数据库身份时整段执行。先设定 `TEST_DB` 和 `SCALE`，核对连接的主机、端口、用户及数据库：

```bash
: "${TEST_DB:?请先设置并核对独立测试数据库名}"
: "${SCALE:?请按测试目标与可用空间设置规模因子}"
pgbench -i -s "$SCALE" "$TEST_DB" || exit 1

# 单连接读写：观察完整事务路径
pgbench -c 1 -j 1 -T 300 -P 10 -r "$TEST_DB" || exit 1
# 并发读写：同时观察吞吐、延迟、锁与 CPU，不只看同步次数
pgbench -c 16 -j 8 -T 300 -P 10 -r "$TEST_DB" || exit 1
# 只读点查：可能命中缓存，也可能产生实际数据读取；不是大表扫描测试
pgbench -c 32 -j 8 -T 300 -P 10 -r -S "$TEST_DB" || exit 1
```

每组保持可比的初始化与预热条件并重复运行，记录失败事务；需要尾延迟时保存事务日志。`-c` 是客户端会话数，`-j` 是压测客户端线程数，不是 PostgreSQL 并行查询进程数。默认脚本只是 TPC-B-like 工作负载，并非正式 TPC-B 结果；大表扫描或业务 SQL 应另用代表性自定义脚本，不从 `-S` 点查推断。

> 初始化风险、参数和自定义脚本见 [PostgreSQL 17 · pgbench](https://www.postgresql.org/docs/17/pgbench.html)。

`<多盘服务器>` 的 SSD 镜像上，原记录在[该组配置](#pg-tuning)下得到：

```
读写（TPC-B-like，16 连接）:  11,523 TPS，延迟 1.39 ms
只读（32 连接）:             331,931 TPS，延迟 0.096 ms
```

这些数字描述该次负载，不是单次 fsync 的倒数。16 个并发会话与 1.39 ms 平均延迟约对应 1.15 万 TPS，体现的是并发事务的完成速率；不能据此认定事务只花 0.089 ms。类似地，不能从 NAS 的 143 ms 随机写同步读数推导整库“最多 7 TPS”，也不能据此证明容器零开销。定位提交瓶颈还需同时核对 WAL、锁、CPU、数据读取和复制等待。

## <a id="container"></a>容器：Docker 与原生部署的 I/O 路径

部署方式与存储路径应分别验证。把数据库数据放到持久卷上可以避开容器可写层，但“没有经过某一层”不足以证明整体性能与原生相同。

### <a id="volume-vs-overlay"></a>数据卷与容器可写层

采用 OverlayFS 的容器可写层可能带来写时复制开销；Docker 也有其他存储后端。普通本地 volume / bind mount 可以让数据不经过该可写层，但实际路径仍取决于宿主文件系统、卷驱动、资源限制，以及是否经过虚拟机或远端存储。named volume 与 bind mount 的管理方式不同，不能不看后端就宣称性能相同。

先核对 PGDATA、WAL 和 tablespace 的实际挂载，再在相同版本、存储、数据和资源限制下做对照。

> [Docker · Volumes](https://docs.docker.com/engine/storage/volumes/)说明了卷与可写层的区别；这是非版本化说明，具体后端与默认值仍需核对实际 Docker 版本和部署配置。

### <a id="container-costs"></a>容器化的代价清单

除实际 I/O 路径外，还需要核对这些运行条件：

| 项目 | 情况 |
|---|---|
| 磁盘 I/O | 相同本地挂载可避开可写层；是否等同原生需要对照测量 |
| 网络 | bridge、host、虚拟机及远端链路各有路径差异，不能统一忽略 |
| 共享内存 | 核对 `/dev/shm` 容量和并行操作需求；原案例 64 MB 不足，不代表所有数据库操作都会失败 |
| 内核级调优 | HugePages 之类在容器里配置更麻烦（不是做不到） |
| 大版本升级 | 换镜像 tag **不会**自动升级数据目录，仍需 `pg_upgrade` 或 dump/restore |
| 关闭时限 | 核对停止信号、宽限时间与实测关闭耗时；超过时限被强杀会影响下次启动 |

前两条里那个 64 MB 的 `/dev/shm` 是真会咬人的——本次实测中建向量索引时直接报 `could not resize shared memory segment`，索引没建成。这两项在 compose 里各一行就好：

```yaml
shm_size: "2gb"           # 本例取值，仍需按并行工作负载核对
stop_grace_period: 2m     # 本例宽限时间，不保证任何负载都能在 2 分钟内关闭
```

### <a id="tiering-design"></a>SSD 与 HDD 混用的分层设计

`<多盘服务器>` 同时有 2 片 SSD（快、容量小）和 8 片 HDD（慢、容量大）。想「容量吃 HDD、速度吃 SSD」，PostgreSQL 侧的抓手是 **tablespace**——把不同的表 / 索引落到不同的挂载点上。

针对本案例低延迟目标可评估以下分层；操作前另行安排迁移、锁等待、备份和容量检查：

- **本案例将 PGDATA 放在 SSD**，以改善随机访问和同步延迟；不能把其中的 WAL、表页和临时文件统称为同一种随机写负载。其他部署仍按延迟目标、容量、耐久性和成本判断。
- **HDD 上开一个 tablespace，只收冷数据**——只读的、靠大块顺序扫描的历史表：

  ```sql
  CREATE TABLESPACE cold_data LOCATION '/srv/pg_cold';
  ALTER TABLE big_archive SET TABLESPACE cold_data;
  ```

- **表体和索引可以分开放**。但索引扫描仍可能回表，索引单独加速并不保证查询加速；结合缓存命中、执行计划和实际访问量验证：

  ```sql
  CREATE INDEX idx_archive_ts ON big_archive (created_at) TABLESPACE pg_default;
  ```

- **每个 tablespace 单独告诉规划器介质代价**，否则规划器会拿 SSD 的假设去规划 HDD 上的表：

  ```sql
  ALTER TABLESPACE cold_data SET (random_page_cost = 4, effective_io_concurrency = 2);
  ```

- **临时文件按溢出工作负载选盘**。外部排序和哈希溢出包含批量写入、归并或分批读取，不全是随机块；同时测量吞吐、并发争用与查询延迟，再决定 `temp_tablespaces`。

机制上必须知道的一点：tablespace 在磁盘上就是 `PGDATA/pg_tblspc/<oid>` 下的一个**符号链接**，指向 `LOCATION`。由此带来三个连锁后果：

- 复制 / 打包 PGDATA **不会**自动带上 tablespace 里的数据
- `pg_basebackup` 需要 `--tablespace-mapping=旧路径=新路径` 重映射
- 恢复到另一台机器时，那个 LOCATION 路径必须**存在、为空、且属主正确**

> 依据：[PostgreSQL 17 文档 · Tablespaces](https://www.postgresql.org/docs/17/manage-ag-tablespaces.html)。置信度说明：本次迁移最终把整库放进了 SSD，**这套分层没有在生产上跑过**，形态是按上述机制推演出来的。

### <a id="tiering-deployment"></a>分层在两种部署下的落地差异

**原生安装**：分层完全发生在文件系统层，没有额外抽象。

```bash
mkdir -p /srv/pg_cold                       # 该路径需落在 HDD 阵列的挂载点内，且目录为空
chown postgres:postgres /srv/pg_cold
chmod 700 /srv/pg_cold
```

之后 `CREATE TABLESPACE` 即可。启用 SELinux 的发行版还得给目录打上 PostgreSQL 的类型标签，否则守护进程读不到。

**Docker**：多挂一个 bind mount，把**容器内**路径当作 LOCATION。

```yaml
services:
  db:
    image: postgres:17
    shm_size: "2gb"
    stop_grace_period: 2m
    volumes:
      - /srv/ssd/pgdata:/var/lib/postgresql/data   # SSD 镜像
      - /srv/hdd/pg_cold:/mnt/cold                 # HDD 阵列
```

```sql
CREATE TABLESPACE cold_data LOCATION '/mnt/cold';
```

三个必须处理的点：

- **宿主目录属主要对齐镜像里的 postgres UID**：官方镜像把它固定成 `uid=999` / `gid=999`，所以宿主侧得 `chown 999:999 /srv/hdd/pg_cold`。若目录事先不存在，Docker 会以 root 属主替你创建，PG 直接起不来。
  > 依据：[docker-library/postgres · `17/bookworm/Dockerfile#L11-L13`](https://github.com/docker-library/postgres/blob/f7201e8ed65eb83a8a9b33ba6669f23cf814bf5d/17/bookworm/Dockerfile#L11-L13)
- **挂载点别落在 `/var/lib/postgresql/data` 里面**。tablespace 目录嵌进 PGDATA 会被备份工具重复计入，PG 自己也会警告。
- **强制访问控制环境给 bind mount 加 `:Z`**（`- /srv/hdd/pg_cold:/mnt/cold:Z`），作用等价于原生那边打标签。

两种部署的成本对照：

| 环节 | 原生安装 | Docker |
|---|---|---|
| 加一块盘做冷层 | 挂载 + `chown postgres` + `CREATE TABLESPACE` | 挂载 + `chown 999:999` + 改 compose 一行 + 重建容器 + `CREATE TABLESPACE` |
| 目录属主 | 包管理器已建好系统 postgres 用户，直接用 | 需手工对齐镜像 UID |
| LOCATION 路径的稳定性 | 库里写死宿主真实路径；换盘 / 改挂载点要停库改符号链接 | 容器内路径固定（`/mnt/cold`），换宿主盘只改 bind mount 左半边，库里的 tablespace 定义不动 |
| 搬到另一台机器 | 新机必须重建同名路径 | 新机 compose 里映射到任意宿主路径即可，容器内路径不变 |
| `pg_basebackup` | 需 `--tablespace-mapping` | 容器内路径一致时可省掉重映射 |
| 强制访问控制 | SELinux 标签 / AppArmor 规则 | bind mount 加 `:Z` |

净结论：**一次性配置 Docker 略麻烦**（UID 对齐、改 compose 要重建容器）；**长期维护 Docker 更省事**，因为容器内路径是一层稳定抽象，换盘、换机器都不用碰数据库里的 tablespace 定义。这是分层场景下容器化唯一实打实的加分项，而且和 I/O 性能无关。

> 「路径稳定」这条有个例外：如果 volume 不走 bind mount，而是用 `driver_opts` 直接绑一块裸设备（`device: /dev/sdX`），抽象层就没了——设备字母在重新挂载后可能漂移，volume 随即指向错的盘或直接起不来。`mount(8)` 支持 `LABEL=` / `UUID=`，理论上写成 `device: LABEL=<卷标>` 能规避，但**未实测**；`lsblk -o NAME,SIZE,FSTYPE,LABEL,UUID` 可确认卷标与 UUID。挂网络 LUN 时尤其要留意，因为它本来就[比本地盘多好几层](#link-composition)。

### <a id="container-measured"></a>部署方式的实测差异

本次**没有做同机 Docker vs 原生的 A/B 对照**，因此容器开销尚未在该环境中量化。11,523 TPS 与 0.089 ms 同步读数不能作为“两者相同”的侧面证明，它们来自不同测量对象。

复测时保持 PostgreSQL 版本、数据、实际存储路径、CPU / 内存额度、同步设置和并发一致，分别采集吞吐及延迟。卷绕过可写层只是机制线索，不排除资源限制、虚拟机、卷驱动和网络带来的其他成本。

> 原文引用的 [ISPASS 2015 容器与虚拟机性能论文](https://doi.org/10.1109/ISPASS.2015.7095802)保留为历史阅读材料，不能替代当前环境的配对测试。该篇论文的结果不在本次修订中重新复现。

## <a id="media"></a>存储介质：本地 SSD 镜像、HDD 阵列与网络 LUN

### <a id="identify-media"></a>介质与阵列状态的识别

在测之前得先知道手上是什么盘，这一步比想象中容易搞错。

Linux 有个 `rotational` 标志（`lsblk` 里的 `ROTA` 列），1 表示机械盘、0 表示固态盘。但**盘接在硬 RAID 卡后面时这个值不可信**：RAID 卡把物理介质挡住了，内核只看到一个虚拟磁盘，一律标成 rotational。

`<多盘服务器>` 上两个阵列都报 `ROTA=1`，看起来全是机械盘，问 RAID 卡才知道其中一个是**两片企业级 SATA SSD 做的镜像**：

```bash
# LSI / Broadcom / AVAGO 系列 RAID 卡（storcli 需 root）
storcli64 /c0/vall show          # 虚拟盘：RAID 级别、缓存策略
storcli64 /c0/eall/sall show     # 物理盘：Med 列才是真的介质类型（SSD / HDD）
```

`storcli` 顺带会告诉你两件对数据库很关键的事：

- **写缓存策略**（WriteBack / WriteThrough）
- **缓存保护模块的健康状况**（CacheVault / BBU）

实测中 HDD 阵列配置的是 WriteBack，但**保护模块已损坏**，于是控制器自动降级成 WriteThrough——没有掉电保护就不敢开回写。结果是随机写和 fsync 慢得像裸盘。这种降级不会有任何报警，只能主动去查。

> 一个别人常踩的坑：保护模块坏了，有人会强行把策略改回 WriteBack 来「恢复性能」。**别这么干**——那等于拿掉电时的数据完整性换速度，对数据库是致命的。

### <a id="raid-write-penalty"></a>校验型 RAID 的写惩罚

`<NAS>` 上读写速度差得很多：

| | 读 | 写 | 比值 |
|---|---|---|---|
| 顺序 | 106 MB/s | **34 MB/s** | 3.1× |
| 随机（QD=32） | 1,462 IOPS | **646 IOPS** | 2.3× |

链路是全双工千兆，上下行对称，[网络本身解释不了这个差距](#link-ceiling)。所以不对称指向**磁盘阵列的写惩罚**。

带校验的 RAID（RAID5 / RAID6，以及各家 NAS 的混合 RAID 变体）每写一小块数据，实际要做四件事：读旧数据、读旧校验、算新校验、写回两份。所以随机写天然比读慢好几倍。不带校验的 RAID10 没有这个问题，代价是容量减半。

`<多盘服务器>` 的 8 盘 RAID50 是同一类结构（条带套 RAID5），叠加上一节那个降级成 WriteThrough 的缓存，就是它 fsync 慢到 7.4 ms 的来源。

### <a id="write-cache-breakdown"></a>写缓存打穿与 checkpoint 停滞

按[写缓存对 fsync 读数的干扰](#write-cache-bias)那节的两种测法，在 `<NAS>` 上同样跑「8K 写 + fsync」，结果差 **64 倍**：

| 测法 | 单次 fsync |
|---|---|
| 小量**顺序**写（总共 2.4 MB） | **2.22 ms** |
| 8 GB 范围内**随机**写 | **143 ms** |

**另一次真实事故记录了恢复检查点的长延迟**：这个库的容器被强制移除后触发崩溃恢复，WAL redo 阶段约 56 秒正常跑完，随后进入 `checkpoint starting: end-of-recovery immediate wait`，二十多分钟看起来像死机。它最终自己跑完了，日志给出精确耗时：

```
checkpoint complete: wrote 1514626 buffers (24.1%); ...
write=675.878 s, sync=727.911 s, total=1406.334 s;
sync files=79, longest=565.499 s, average=9.186 s
```

日志记录了约 150 万个缓冲区的写出、**单个文件同步最长约 565 秒**、整个 checkpoint 约 **1406 秒**。它证明该次恢复的写出和同步耗时很长，但不能仅凭这些字段断定每次写都在等待物理盘，也不能将检查点耗时当作普通事务提交延迟。

事故里更值钱的是诊断层面的教训——**当时判定为「卡死」，这个判断是错的**：

- checkpointer 进程长期处于 `Ds`（不可中断磁盘睡眠）、CPU 恒 0%，`docker stats` 的 BlockIO 字节计数器连续 21 分钟分毫不变。**这组证据无法区分「真卡死」和「单次操作巨慢但仍在推进」**——在任何有限长的观测窗口里，两者表现完全一样。
- 观察窗口必须和怀疑的**单次操作耗时量级**匹配。怀疑卡在一次 fsync，而这套存储单次 fsync 可以要 9 分钟，那 21 分钟的窗口在统计上根本不够长。
- 所以**别去二次强杀正在 fsync 的 PostgreSQL**——只会让它再崩一次，进入同样的恢复循环。要实锤，去看逐次更新的底层计数（如 `/proc/<pid>/io` 的 `rchar` / `wchar`），或者干脆等日志吐出精确耗时。

> 完整排查过程与当时的错误推理记录见 `mess` skill 的 NAS / iSCSI 已知坑章节。

2.22 ms 与 143 ms 属于不同条件的存储微基准，不是两种真实事务延迟。原始测试与恢复日志都应保留，但需要分别解释。

### <a id="media-benchmark"></a>后端横向实测

下表保留原文汇总的三套存储读数。本文未附全部原始 fio 输出，解释前应核对引擎、缓存模式、同步统计及并发；不能把不同指标互相代入。

| 指标 | 企业级 SATA SSD<br>（2 片 RAID1） | 大容量 HDD 阵列<br>（8 片 RAID50） | `<NAS>` iSCSI<br>（千兆网） |
|---|---|---|---|
| **fsync 延迟** | **0.089 ms** | 7.4 ms | **143 ms**（随机写下） |
| 原记录的同步测试吞吐（非 pgbench TPS） | 3,550 /s | 109 /s | ~7 /s |
| 随机写 IOPS | 39,448 | 1,446 | 646 |
| 随机读 IOPS | 89,285 | —（缓存污染） | 1,462 |
| 顺序读 | 572 MB/s | **1,214 MB/s** | 106 MB/s |
| 顺序写 | — | — | 34 MB/s |

0.089 / 7.4 / 143 ms 的记录相差约 83 倍和 1600 倍，但这个比例不等于数据库整体加速比，也不能量化[容器开销](#container-measured)。

HDD 阵列的顺序读 1,214 MB/s 高于 SSD 镜像的 572 MB/s，可能对大扫描、备份等任务有价值；事务工作负载则还需看同步、随机访问和等待。另一个原文比较存在口径错误：NAS 的 1,462 是**随机读** IOPS，而 HDD 的 1,446 是**随机写** IOPS，不能据此比较两者随机读性能。HDD 随机读仍保留为缺失，不能补猜。

## <a id="network"></a>网络链路：千兆 iSCSI

`<NAS>` 的数难看，多少要归网络？这一章把网络的贡献单独摘出来。

### <a id="link-composition"></a>链路的完整构成

`<NAS>` 不是直连宿主的块设备，中间隔了好几层，量出来的每个数都含这一整串的开销：

```
NAS 后端阵列 → iSCSI Target/LUN → 千兆以太网 → Windows iSCSI Initiator
  → wsl --mount --bare → WSL2 里的 /dev/sdX（整盘 ext4、无分区表）→ 容器数据卷
```

本篇针对 `<NAS>` 的 fio 全部在最右端（WSL2 里的 `/dev/sdX` 及其上的文件系统）跑，所以：

- 「网络往返 0.95 ms」严格说是**以太网加 iSCSI 协议栈加 Windows 初始化器加 WSL2 虚拟块设备**的合计往返，是纯网络延迟的**上界**。
- 这反而让结论更硬：整串中间层加起来才 0.95 ms，而磁盘要 23.5 ms，[瓶颈归属](#bottleneck-attribution)不会因为分层没拆干净而翻转。

链路长还带来一类与性能无关、却容易被当成性能问题的故障：中间任何一层的地址或设备名变了，块设备直接从 WSL 里消失，看起来像"存储挂了"。这类排查（NAS 换 IP 后 iSCSI 登录死锁、TUN 代理让端口探测出假阳性、Windows 持久化目标钉死旧地址）见 `mess` skill 的 NAS / iSCSI 已知坑章节。

### <a id="link-ceiling"></a>链路的理论上限与延迟构成

千兆以太网理论 125 MB/s，扣掉以太网 / IP / TCP / iSCSI 各层封装，实际上限约 112 MB/s。它同时给出两个约束：

- **带宽上限**：单条千兆链路的顺序吞吐不可能超过约 112 MB/s
- **每次往返的延迟**：请求发出到响应回来的固定开销，与传输量无关；QD=1 的小块随机 I/O 完全被它支配

而链路是**全双工**的，上下行各跑各的——所以读写速度不对称时，[不能赖网络](#raid-write-penalty)。

要判断「网慢还是盘慢」，得有办法把这两段拆开，就是下一节。

### <a id="hole-read"></a>精简置备空洞读法

前提是 LUN 用了**精简置备**（thin provisioning，声明 3 TB 但只按实际用量占空间）。这时：

- **读已经写过的区域** → 数据要从物理盘取出来 → 走完整链路（网络 + 磁盘）
- **读从没写过的区域** → 存储端直接返回一堆零，压根不碰盘 → **只测网络和协议**

两者一减，磁盘的贡献就浮出来了：

```bash
# 已分配区（含磁盘）
fio --name=a --filename=/dev/sdX --rw=randread --bs=4k \
    --iodepth=1 --direct=1 --offset=0 --runtime=15 --time_based

# 未分配区（纯网络往返）—— offset 挑一个远超已用量的位置
fio --name=b --filename=/dev/sdX --rw=randread --bs=4k \
    --iodepth=1 --direct=1 --offset=2500G --runtime=15 --time_based
```

### <a id="bottleneck-attribution"></a>分离结果与瓶颈归属

`<NAS>` 上的结果（LUN 名义 3 TB、实用 435 GB）：

| 4K 随机读 | 已分配区 | 未分配区 | 差值的含义 |
|---|---|---|---|
| 单次延迟 | **24.46 ms** | **0.95 ms** | **磁盘寻道约 23.5 ms** |
| QD=32 时的 IOPS | **1,462** | **21,994** | 磁盘比网络慢 **15 倍** |

一眼就清楚了：

- 网络往返只要 0.95 ms（含 [Windows 初始化器与 WSL2 那几层](#link-composition)），对千兆网来说非常正常，**网络延迟不是问题**
- 磁盘寻道 23.5 ms，比典型 7200 转硬盘（8–12 ms）还慢，**这才是瓶颈**
- 网络加协议能扛 22,000 IOPS，实际负载峰值才 1,462——**存储设备的 CPU 也有 15 倍余量，同样不是瓶颈**

> 关于 CPU 那条的置信度：零填充读在存储端可能走了捷径，所以 22,000 是「协议处理能力上限」而不是「满负载 CPU 实测」。但余量这么大，足以排除 CPU。

顺序读那边是另一个故事：未分配区跑到 112.5 MB/s，已分配区 106.1 MB/s，两者只差 6%——**顺序读几乎跑满了千兆网，磁盘没拖后腿**，且 112.5 MB/s 正好贴在[上面算的链路上限](#link-ceiling)上。

所以同一套存储，**顺序读卡在网络，随机读卡在磁盘**。想提顺序吞吐得换万兆或多路径；想提随机性能得换介质，网络怎么升都没用。

### <a id="qd-sweep"></a>队列深度扫描下的顺序读

同一套 `<NAS>` 存储，只改队列深度，顺序读的结果是：

| 队列深度 | 顺序读速度 |
|---|---|
| QD=1 | 78 MB/s |
| QD=8 | 105 MB/s |
| QD=32 | 106 MB/s |

**差了 36%。** 早期用 `dd` 测出 76 MB/s（相当于 QD=1），据此以为这套存储只有这个水平——实际上给足并发能跑到 106 MB/s。

按[队列深度的语义与瓶颈判读](#queue-depth)的判读规则：这组数在 QD=8 之后就不涨了，说明 QD≥8 时瓶颈已经从**网络往返延迟**转成了**链路带宽**。这和上一节顺序读贴顶千兆的结论互相印证。

## <a id="pg-tuning"></a>PostgreSQL 的数据布局与参数

把上面三层的测量落到具体决策上。

**数据放哪：**

先用代表性负载确认 WAL 同步、随机访问、扫描还是并发争用占主导，再做[分层](#tiering-design)。本案例将数据库放到 SSD；这不是“所有索引必须 SSD、所有 HDD 阵列都不能存数据库”的通用规则。

WAL 与数据可以共用 SSD，也可能因带宽、排队或同步延迟相互影响。是否使用独立设备要做对照；“SSD 没有机械寻道”并不意味着独立 WAL 存储永远无益。无论选择何种介质，都不能用失效的缓存保护或关闭持久性要求来换取漂亮结果。

> WAL 所在设备与同步方法的关系见 [PostgreSQL 17 · WAL Configuration](https://www.postgresql.org/docs/17/wal-configuration.html)。

**参数怎么跟着负载调：**

下面保留原案例的起点，不把存储介质名称直接映射成固定参数：

```
# 原案例的候选取值，需用实际查询和并发验证
random_page_cost = 1.1
effective_io_concurrency = 200
```

`random_page_cost` 是规划器对非顺序页读取的成本估计，要相对 `seq_page_cost` 及 CPU 成本理解；默认 4.0 已包含缓存命中假设，不是机械盘延迟的直接倍数。1.1 不是所有 SSD 的标准答案，顺序扫描也不天然是错误计划。结合统计信息和代表性查询的执行计划验证，混合介质可以按 tablespace 覆盖。

> 依据：[PostgreSQL 17 · Planner Cost Constants](https://www.postgresql.org/docs/17/runtime-config-query.html#RUNTIME-CONFIG-QUERY-CONSTANTS)。

**内存参数按机器实配，别照抄。** `<多盘服务器>`（125 GiB 内存 / 48 线程）上实测跑得不错的一组：

```
shared_buffers = 32GB              # 约 1/4 内存
effective_cache_size = 96GB        # 不是真分配，是告诉规划器「系统大概能缓存多少」
maintenance_work_mem = 4GB         # 建索引、VACUUM 用；建大索引时临时调大
work_mem = 128MB                   # ⚠️ 这是每个排序/哈希节点的量
max_wal_size = 32GB
```

`work_mem` 不是每个连接的总内存上限：一条查询可以有多个同时活动的内存操作，多个会话和并行执行会进一步放大用量；哈希操作还受 `hash_mem_multiplier` 影响。原先 16–32 MB 的全局建议也只可作为候选值，需按并发和实际查询预算；需要时对受控事务使用 `SET LOCAL`，不要把 128 MB 直接乘连接数当成精确峰值。

> 参数语义以 [PostgreSQL 17 文档 · Resource Consumption](https://www.postgresql.org/docs/17/runtime-config-resource.html) 为准；上面这组数值是本次实测的可用配置，不是普适推荐。

容器部署还要补上 `shm_size` 与 `stop_grace_period`，见[容器化的代价清单](#container-costs)。这套配置跑出的 TPS 见 [pgbench 端到端复核](#pgbench)。

## <a id="migration"></a>跨机迁移的吞吐与压缩

搬 428 GB 数据库的过程中，几个和存储 / 吞吐有关的实测结论。

**先量清楚三条链路的速度，最慢的那条才是瓶颈：**

| 环节 | 实测 |
|---|---|
| 源存储读取（`<NAS>` iSCSI） | 106 MB/s（要给足队列深度） |
| 中转盘写入（本地盘） | 157 MB/s |
| 跨机网络传输 | **19 MB/s** ← 全局瓶颈 |

网络最慢，所以中转位置应该选**读写分离**的盘——别把 dump 写回正在读的那块存储上，读写互相抢带宽。

**压缩算法选 zstd，不要用默认的 gzip：**

同一份 10 万行样本（原始 843 MB）：

| 算法 | 压缩后 | 耗时 | 吞吐 |
|---|---|---|---|
| gzip -6 | 133 MB | 18.4 s | 46 MB/s |
| **zstd -3** | **115 MB** | **5.1 s** | **165 MB/s** |
| lz4 -1 | 207 MB | 5.3 s | 159 MB/s |

zstd **又小又快 3.6 倍**。这不是锦上添花——`pg_dump` 的并行是**按表切分**的，单张大表内部只有一个压缩线程。实测那张表有 666 GB 未压缩数据，用 gzip 光压缩就要 4.6 小时，成了隐藏瓶颈；换 zstd 后压缩速度（165 MB/s）超过存储读取速度（106 MB/s），瓶颈就回到读取上了。

PostgreSQL 16 及以后的 `pg_dump` 支持 `-Z zstd:3`。

**一个必须知道的坑：`pg_restore` 出错也返回成功。**

```
pg_restore: error: ... violates foreign key constraint
pg_restore: warning: errors ignored on restore: 1
pg_restore exit=0            ← 退出码仍然是 0
```

默认行为是**遇错继续、最后返回成功**。也就是说恢复了半个库，脚本看起来是成功的。**务必加 `--exit-on-error`**，并且恢复进一个全新的空库，失败就整个删掉重来。

**还有一个和存储容量有关的提醒**：`pg_dump` 导出的是逻辑数据，不是磁盘上的字节。实测那张表在磁盘上占 353 GB，导出成文本却有 666 GB——因为磁盘上的大字段是压缩存的（TOAST），导出时会先解压成文本再重新压缩。估算中转空间时按解压后的量算，别按磁盘占用算。
