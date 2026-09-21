---
name: io
description: 定位内存、文件系统、挂载、存储介质或网络块存储造成的 I/O 与换页瓶颈时使用。核心是沿实际数据路径分层测量延迟和 IOPS，避免被缓存或顺序带宽误导。
---

# I/O

一次数据访问从"程序读某个字节"到"字节真的到手"，中间要穿过一串层：页在不在内存 → 换页落到哪个文件 → 那个文件在哪种文件系统上 → 底下是虚拟磁盘还是裸盘 → 介质是固态还是机械 → 是否还要过一段网络。**每一层各自加一份延迟，而症状永远只表现为"这条指令特别慢"。** 所以排查的第一步不是换更快的盘，是先定位在哪一层。

## 层次与延迟量级

这条路上有哪些层、每层加什么：两层操作系统（guest / host / 物理内存）、页与缺页机制、换页的三个落点（其中宿主换出虚拟机内存对 guest **完全隐形**，只能靠"延迟中位数不变但出现秒级尖峰、多进程同时冻结、guest 内核零消息"这组形状反推）、NVMe / VHDX / 页面文件的术语、容器的数据卷绕过 overlayfs 所以 I/O ≈ 原生。压轴是一张**贯通的延迟量级阶梯**（内存 ~100 ns → 缺页 ~100 µs → SSD fsync 0.089 ms → HDD 阵列 7.4 ms → 千兆 iSCSI 143 ms → 打穿缓存的 checkpoint 单文件 fsync 565 s；元数据面另有一列：CIFS ~3 ms/文件 → 9p ~10 ms/文件 → rclone 冷 `stat` 4–5 s），以及那句要点——**同一块物理盘，套的层不同能差几个数量级，差距来自层数与争用而非介质**。见 [references/layers.md](references/layers.md)。

## 内存额度、记账与回收

存储层次最上面那一层。上限（cap）不是预留（reservation）；宿主与 guest 两套同构的提交记账（commit charge / limit ↔ `Committed_AS` / `CommitLimit`，各自的公式各填各自那份后备存储），以及"虚拟机上限 + 宿主需求 ≤ 物理内存"这个**无人把关**的和；OOM killer 以"回收有无进展"为判据导致大 swap 下的回收活锁，与 PSI / 早期 OOM 守护进程的补位（只管得到 guest 内部）；swap 扩得了总容量、扩不了活跃工作集。配置侧含 `.wslconfig` 内存相关键的默认值陷阱（`swap` 缺省按 `memory` 的 25% 折算、`autoMemoryReclaim` 缺省 `dropCache`，两者叠加时基数连乘）、guest 侧 `vm.swappiness` / `vm.overcommit_memory`、两侧用量核对必须用 `MemTotal−MemFree`（`free` 的 `used` 不含缓存），以及 Slurm 侧 `RealMemory` / `DefMemPerNode` / `MaxMemPerNode` 与 `task/cgroup` 的协同（限制挂 job 层、叶子 task cgroup 显示 `max`，要逐级向上查）。见 [references/memory.md](references/memory.md)。

## 远端存储的接入方式

把远端目录挂成本地路径 = 在层次里插一层网络协议，数据面与元数据面要分别测量，缓存和批处理会影响实际往返次数。三条路的取舍（`drvfs`/9p 免 root 但最慢、内核 CIFS 要 root 但最快、rclone SMB FUSE 免 root 用于装不了 `cifs-utils` 的受限环境）、CIFS 凭据与 `mount.cifs` 参数与常见报错、**WSL2 NAT 下用 hostname 挂 CIFS 为什么扛不住 IP 漂移**（Windows 走 mDNS 出不了 NAT、WSL DNS 中继会读 Windows hosts，所以只是把硬编码从 fstab 挪到 hosts）、rclone 的 systemd user service 模板与挂载专有排障（`fusermount3` vs `fusermount`、`host=` 写 IP literal 导致 ~100 s 一轮重启、`MOUNT_DIR` 不存在导致 ~10 s 一轮，**用重启间隔区分根因**）、VFS cache 模式与磁盘占用，以及两条对 FUSE 和内核挂载都成立的通用纪律：`find`/`rg --no-ignore`/`du` 等 walk 类工具会一头扎进挂载点卡死（`-prune` / `--glob` 模板），挂载点里删文件用 `trash-put` 落到卷内 `.Trash-<UID>/` 而非跨 filesystem 拷贝。见 [references/mount.md](references/mount.md)。

## 存储后端：介质、阵列与网络链路

最底下那一层，也是差距最大的一层（三个数量级）。**硬 RAID 卡后面 `ROTA` 不可信**，要用 `storcli` 问介质类型与缓存保护模块（BBU 坏会静默降级 WriteThrough）；校验型 RAID 的写惩罚解释读写不对称；历史测试中不同写入条件下的同步读数相差约 64 倍，并记录了一次 checkpoint 单文件 fsync 565 秒的事故——附「`Ds` 状态 + BlockIO 计数器不变**无法区分**卡死与巨慢、观察窗口要匹配单次操作量级」的诊断纪律；SSD 镜像 / HDD 阵列 / 网络 LUN 横向实测（fsync 差 1600 倍而顺序带宽反向）；固态与机械混用时按负载形状分层的判据。网络段讲千兆 iSCSI 的完整链路构成与理论上限，**精简置备空洞读法**把网络与磁盘瓶颈分开（据此定出"顺序读卡网络、随机读卡磁盘、存储端 CPU 有 15 倍余量"），以及队列深度扫描（该次 fio 顺序读随并发增加约 36%，不据此给 `dd`/`hdparm` 统一归类或校正）。见 [references/backend.md](references/backend.md)。

## 测法与瓶颈归因

按工作负载选择同步延迟、随机 IOPS、顺序吞吐或元数据指标；区分缓冲 I/O、direct I/O 和持久化同步；在获准目录准备实际写入的数据，再核对 fio 引擎、实际队列深度及延迟分布。吞吐平台期只是定位线索，不单独证明带宽耗尽；具备有效掉电保护的缓存也不能一概视为“虚假刷盘”。测量流程、样例与历史结果的适用边界见 [references/benchmark.md](references/benchmark.md)。

## 边界

- **数据库自身**的参数与部署——PostgreSQL 的 tablespace 冷热分层语法、`random_page_cost` / `work_mem`、容器化代价清单（`/dev/shm` 64 MB、`stop_grace_period`）、pgbench、跨机迁移与 `pg_restore --exit-on-error`——见 `software` skill 的 PostgreSQL 存储工程章节。
- **对象存储客户端**（RustFS / SeaweedFS / MinIO `mc` 的版本语义、批量 op、HDD 后端表现）见 `software` skill 的对象存储章节。
- **systemd 通用坑**（`ExecStart` 第一项不展开 `$VAR`、user unit 不能依赖 system target、`enable-linger`）见 `software` skill 的 Service / systemd 章节。
- **一次 NAS / iSCSI 故障的完整排查过程**（换 IP 后登录死锁、TUN 代理导致端口探测假阳性、当时的错误推理）见 `mess` skill 的 NAS / iSCSI 已知坑章节。
