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

三层变量共用同一套指标和同一套 fio 基线，先在这里讲清楚，后面三章只给各自的机理与实测。

### <a id="io-metrics"></a>数据库敏感的 I/O 指标

一般人测盘只看一个数：顺序读写速度（`hdparm -t`、`dd` 跑出来的 MB/s）。**对数据库来说这个数几乎没用。**

数据库真正吃的是另外三个：

| 指标 | 通俗解释 | 影响什么 |
|---|---|---|
| **fsync 延迟** | 「确认这笔数据真落盘了」要等多久 | 每次事务提交，**最关键** |
| **随机 IOPS** | 每秒能处理多少个零散的小块读写 | 索引查找、随机扫描 |
| 顺序带宽 | 连续大块数据的传输速度 | 全表扫描、备份、恢复 |

fsync 延迟排第一，是因为**每提交一次事务都要等一次 fsync**——这个延迟直接乘在每秒事务数上。顺序带宽排最后，是因为数据库很少真在做纯顺序 I/O。

这个排序不是修辞：本次实测里，8 盘 HDD 阵列的顺序读比 SSD 镜像还快一倍，fsync 却慢 83 倍（数据见[后端横向实测](#media-benchmark)）。只看带宽会直接得出「用 HDD 阵列」的错误结论。

> 也因此 `hdparm -t` 和 `dd` 这类工具不适合给数据库选盘——它们量的正好是数据库最不在乎的那个维度。

### <a id="fio-baseline"></a>fio 基准命令与参数语义

`fio` 是唯一能把上面三个数分开量的常用工具。三条命令覆盖全部：

```bash
# ① fsync 延迟（最重要）：单线程 8K 随机写，每写一笔就 fsync
#    模拟的就是数据库提交事务
fio --name=commit --filename=/path/testfile --size=2G \
    --bs=8k --rw=randwrite --ioengine=libaio \
    --iodepth=1 --fsync=1 --direct=1 \
    --runtime=25 --time_based

# ② 随机写 IOPS：深队列并发
fio --name=wiops --filename=/path/testfile --size=4G \
    --bs=8k --rw=randwrite --ioengine=libaio \
    --iodepth=32 --numjobs=4 --direct=1 \
    --runtime=25 --time_based --group_reporting

# ③ 随机读 IOPS
fio --name=riops --filename=/path/testfile --size=4G \
    --bs=8k --rw=randread --ioengine=libaio \
    --iodepth=32 --numjobs=4 --direct=1 \
    --runtime=25 --time_based --group_reporting
```

几个参数的意思，因为选错了结果会完全不同：

- `--direct=1`：绕过操作系统的页缓存。**不加这个测的就是内存速度**，数字漂亮但没意义。
- `--iodepth`：同时压多少个请求，见[队列深度的语义与瓶颈判读](#queue-depth)。
- `--fsync=1`：每写一笔就强制落盘，这才是数据库提交的真实行为。
- `--bs=8k`：对齐 PostgreSQL 的默认页大小，量出来的数才和数据库行为对得上。
- 测试文件写在要评估的那个文件系统上，测完记得删。

### <a id="queue-depth"></a>队列深度的语义与瓶颈判读

`--iodepth` 是「同时在飞的请求数」。`dd` 和 `hdparm` 默认都是发一个等一个（相当于 QD=1），所以它们的读数在高延迟设备上会被严重低估——同一套网络存储，QD 从 1 提到 8，顺序读涨了 36%（数据见[队列深度扫描下的顺序读](#qd-sweep)）。

反过来，扫一遍队列深度也能告诉你瓶颈在哪：

- **提高 QD 速度明显上升** → 之前卡在**延迟**上（在等往返，不是带宽不够）
- **提高 QD 速度几乎不变** → 已经**撞到带宽天花板**

### <a id="write-cache-bias"></a>写缓存对 fsync 读数的干扰

存储设备（RAID 卡、NAS 控制器）都有写缓存。数据量小又是顺序的时候，缓存全吃下，立刻回一句「写好了」，fsync 看起来飞快；一旦进入持续随机写，缓存被打穿，每一笔都得真等磁盘，性能直接塌方。本次实测里同样是「8K 写 + fsync」，两种测法差了 64 倍（数据与事故见[写缓存打穿与 checkpoint 停滞](#write-cache-breakdown)）。

规避办法只有两条：

- 随机写的范围要**大到打穿缓存**（远超缓存容量，比如上面命令里的 `--size=4G` 起步，缓存大就再加）
- 或者干脆在真实负载下观察，别在空闲时随手测一发就下结论

### <a id="pgbench"></a>pgbench 端到端复核

fio 量的是块设备，最终还得看 PostgreSQL 自己跑出什么数。`pgbench` 是随 PG 发行的标准压测工具：

```bash
pgbench -i -s 1000 <db>              # 初始化；规模因子决定数据集大小，要大到超过 shared_buffers
pgbench -c 16 -j 8 -T 300 <db>       # 读写混合（TPC-B 类），每笔事务都提交 → 直接压 fsync
pgbench -c 32 -j 8 -T 300 -S <db>    # -S 只读，压的是缓存命中与 CPU，不碰 fsync
```

`<多盘服务器>` 的 SSD 镜像上，按 [PostgreSQL 的数据布局与参数](#pg-tuning) 那组配置实测：

```
读写（TPC-B，16 连接）:  11,523 TPS，延迟 1.39 ms
只读（32 连接）:        331,931 TPS，延迟 0.096 ms
```

读写那个 11,523 TPS 就是 fsync 延迟的直接体现——0.089 ms 的提交延迟才撑得起这个数。同一套配置放到 `<NAS>` 上（fsync 143 ms），理论上限大约每秒 7 笔。两者相差三个数量级，而**容器与原生的差别在这个尺度下根本看不见**——这也是下一章的出发点。

## <a id="container"></a>容器：Docker 与原生部署的 I/O 路径

「用 Docker 跑还是 `apt` 装的原生跑更快」是个常问的问题，答案是**几乎没区别**，前提是数据别放错地方。这一章讲清楚为什么，以及容器化真正要付的代价在哪。

### <a id="volume-vs-overlay"></a>数据卷与 overlayfs 的分工

Docker 的存储分两层：

- **容器可写层**走 overlayfs（写时复制），确实慢，但那是给临时文件用的
- **数据卷**（无论 named volume 还是 bind mount）是宿主机文件系统上的普通目录，**直接绕过 overlayfs**

数据库的数据目录一定挂在卷上，所以走的是第二条路，和原生装读写同一块盘没有本质差别。

> 顺带澄清两个容易混的名词：**named volume** 是 Docker 自己管、放在它的 data-root 下；**bind mount** 是你指定宿主机的某个路径挂进去。两者都不过 overlayfs，性能上没区别，区别只在谁负责管理生命周期。详见 [Docker 文档 · Bind mounts](https://docs.docker.com/engine/storage/bind-mounts/)。

### <a id="container-costs"></a>容器化的代价清单

容器化真正的代价在别处，和 I/O 路径无关：

| 项目 | 情况 |
|---|---|
| 磁盘 I/O | ≈ 原生 |
| 网络 | 默认 bridge 有 NAT 开销；内部服务走环回或自定义网络时可忽略 |
| 共享内存 | 容器默认 `/dev/shm` 只有 64 MB，**数据库会撞墙**，要显式调大 |
| 内核级调优 | HugePages 之类在容器里配置更麻烦（不是做不到） |
| 大版本升级 | 换镜像 tag **不会**自动升级数据目录，仍需 `pg_upgrade` 或 dump/restore |
| 关闭时限 | 默认 10 秒就 SIGKILL，不够 PG 干净关闭，会导致下次启动走崩溃恢复 |

前两条里那个 64 MB 的 `/dev/shm` 是真会咬人的——本次实测中建向量索引时直接报 `could not resize shared memory segment`，索引没建成。这两项在 compose 里各一行就好：

```yaml
shm_size: "2gb"           # 默认 64MB，并行查询和建索引会撞墙
stop_grace_period: 2m     # 默认 10 秒，给 PG 留够时间做关闭前的 checkpoint
```

### <a id="tiering-design"></a>SSD 与 HDD 混用的分层设计

`<多盘服务器>` 同时有 2 片 SSD（快、容量小）和 8 片 HDD（慢、容量大）。想「容量吃 HDD、速度吃 SSD」，PostgreSQL 侧的抓手是 **tablespace**——把不同的表 / 索引落到不同的挂载点上。

目标形态：

- **PGDATA 整体放 SSD**。里面装着系统表、`pg_wal`、`pg_xact` 和临时文件，全是小块随机写加 fsync 密集的东西，一寸都不该放机械盘。
- **HDD 上开一个 tablespace，只收冷数据**——只读的、靠大块顺序扫描的历史表：

  ```sql
  CREATE TABLESPACE cold_data LOCATION '/srv/pg_cold';
  ALTER TABLE big_archive SET TABLESPACE cold_data;
  ```

- **表体和索引可以分开放**。索引查找是典型随机读，最吃 SSD；把表体放 HDD、索引留在默认 tablespace（SSD）往往是性价比最高的一刀：

  ```sql
  CREATE INDEX idx_archive_ts ON big_archive (created_at) TABLESPACE pg_default;
  ```

- **每个 tablespace 单独告诉规划器介质代价**，否则规划器会拿 SSD 的假设去规划 HDD 上的表：

  ```sql
  ALTER TABLESPACE cold_data SET (random_page_cost = 4, effective_io_concurrency = 2);
  ```

- **临时文件别往 HDD 放**。大排序 / 哈希溢出写的是随机块，`temp_tablespaces` 指到机械盘等于把最痛的负载送去最慢的地方，留在 SSD。

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

本次**没有做同机 Docker vs 原生的 A/B 对照**，所以「两者性能相同」这条是机理推断加侧面印证，不是直接实测：

- **机理**：数据卷不过 overlayfs，容器进程读写的是宿主文件系统上的同一批 inode，路径上只多了 namespace 与 cgroup 的记账。
- **侧面印证**：容器里跑出的 pgbench 读写 11,523 TPS，与该 SSD 的 fsync 延迟（0.089 ms）推出的上限吻合，没观察到额外损耗（见 [pgbench 端到端复核](#pgbench)）。
- **外部佐证**：Felter 等人用 fio 系统比较过原生、Docker 与 KVM 的块 I/O，结论是走数据卷的 Docker 与原生基本持平（[An Updated Performance Comparison of Virtual Machines and Linux Containers, ISPASS 2015](https://doi.org/10.1109/ISPASS.2015.7095802)）。

置信度：高。真正会咬人的从来不是 I/O 路径，而是[上面那张代价清单](#container-costs)里的默认值——尤其 64 MB 的 `/dev/shm`。相比之下，换一块盘带来的差距在下一章。

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

**这解释了一次真实事故**：这个库的容器被强制移除后触发崩溃恢复，WAL redo 阶段约 56 秒正常跑完，随后进入 `checkpoint starting: end-of-recovery immediate wait`，二十多分钟看起来像死机。它最终自己跑完了，日志给出精确耗时：

```
checkpoint complete: wrote 1514626 buffers (24.1%); ...
write=675.878 s, sync=727.911 s, total=1406.334 s;
sync files=79, longest=565.499 s, average=9.186 s
```

150 万个脏页远超缓存容量，于是每一笔都在等盘：**单个文件的 fsync 最长 565 秒**，整个 checkpoint **1406 秒**。

事故里更值钱的是诊断层面的教训——**当时判定为「卡死」，这个判断是错的**：

- checkpointer 进程长期处于 `Ds`（不可中断磁盘睡眠）、CPU 恒 0%，`docker stats` 的 BlockIO 字节计数器连续 21 分钟分毫不变。**这组证据无法区分「真卡死」和「单次操作巨慢但仍在推进」**——在任何有限长的观测窗口里，两者表现完全一样。
- 观察窗口必须和怀疑的**单次操作耗时量级**匹配。怀疑卡在一次 fsync，而这套存储单次 fsync 可以要 9 分钟，那 21 分钟的窗口在统计上根本不够长。
- 所以**别去二次强杀正在 fsync 的 PostgreSQL**——只会让它再崩一次，进入同样的恢复循环。要实锤，去看逐次更新的底层计数（如 `/proc/<pid>/io` 的 `rchar` / `wchar`），或者干脆等日志吐出精确耗时。

> 完整排查过程与当时的错误推理记录见 `mess` skill 的 NAS / iSCSI 已知坑章节。

也就是说，2.22 ms 那个数字如果被当成选型依据，会低估真实提交延迟整整两个数量级。

### <a id="media-benchmark"></a>后端横向实测

同一套 fio 参数（8K 块）下三套存储的对比：

| 指标 | 企业级 SATA SSD<br>（2 片 RAID1） | 大容量 HDD 阵列<br>（8 片 RAID50） | `<NAS>` iSCSI<br>（千兆网） |
|---|---|---|---|
| **fsync 延迟** | **0.089 ms** | 7.4 ms | **143 ms**（随机写下） |
| 同步提交吞吐 | 3,550 /s | 109 /s | ~7 /s |
| 随机写 IOPS | 39,448 | 1,446 | 646 |
| 随机读 IOPS | 89,285 | —（缓存污染） | 1,462 |
| 顺序读 | 572 MB/s | **1,214 MB/s** | 106 MB/s |
| 顺序写 | — | — | 34 MB/s |

用 fsync 延迟这一列排序，差距是压倒性的：SSD 比 `<NAS>` 快 **1600 倍**，比 HDD 阵列快 **83 倍**。对照[容器那一章](#container-measured)的结论——换介质带来的是三个数量级，换部署方式带来的是测不出来。

两个反直觉的点：

- **HDD 阵列的顺序读（1,214 MB/s）是 SSD（572 MB/s）的两倍多**——八盘并发的带宽优势。但这个数对数据库没用，正是[数据库敏感的 I/O 指标](#io-metrics)那节要防的误判。
- **`<NAS>` 的随机读 IOPS（1,462）比本地 HDD 阵列（1,446）还略高**——盘数和缓存配置的差异，网络存储不必然更差。

真正拉开差距的始终是 fsync 那一行。

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

- **数据目录放 SSD**，这是最重要的一条。如果容量放不下，就按[SSD 与 HDD 混用的分层设计](#tiering-design)做 tablespace 分层：
  - 必须放 SSD：`pg_wal`（每次提交都写）、所有索引、向量索引、频繁 join 的热表
  - 可以放 HDD：只读的、大块顺序扫描的冷数据
- **WAL 和数据放同一块 SSD 完全可以**。「WAL 单独放一块盘」是机械盘时代的做法，目的是避免磁头来回寻道；SSD 没有寻道，这条不再适用。
- **别把数据库放在带校验 RAID 的机械盘阵列上**，尤其在[缓存保护模块坏掉](#identify-media)的情况下。

**参数怎么跟着盘调：**

```
# SSD
random_page_cost = 1.1          # 随机读几乎和顺序读一样便宜
effective_io_concurrency = 200  # 能同时压很多请求
```

`random_page_cost` 是告诉查询规划器「随机读比顺序读贵多少倍」。默认值 4 是给机械盘的；SSD 上设成 1.1，规划器才敢用索引而不是傻乎乎全表扫。设错了不会报错，只会让它一直选错执行计划。混用介质时按 tablespace 单独覆盖，写法见[分层设计](#tiering-design)。

**内存参数按机器实配，别照抄。** `<多盘服务器>`（125 GiB 内存 / 48 线程）上实测跑得不错的一组：

```
shared_buffers = 32GB              # 约 1/4 内存
effective_cache_size = 96GB        # 不是真分配，是告诉规划器「系统大概能缓存多少」
maintenance_work_mem = 4GB         # 建索引、VACUUM 用；建大索引时临时调大
work_mem = 128MB                   # ⚠️ 这是每个排序/哈希节点的量
max_wal_size = 32GB
```

`work_mem` 那条要特别当心：它是**每个排序或哈希节点、每个并行工作进程**各用一份。100 个连接 × 几个节点 × 并行度，理论峰值能到几十 GB。保守做法是全局设小（16–32 MB），需要大内存的分析查询单独 `SET LOCAL` 调高。

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
