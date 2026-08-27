# Windows / WSL2 的内存模型

在 WSL2 上跑大内存作业时，"还剩多少内存可用"这个问题在三个位置有三个互不相同的答案：Linux 里的 `free`、Windows 看到的虚拟机工作集、以及作业调度器认的额度。三者口径不同、彼此看不见。

全文分三部分：[概念](#concepts) 讲这几层各自的语义与相互关系，[WSL 与 Windows 侧的配置](#wsl-config) 讲 `.wslconfig` 与内核参数怎么定，[Slurm 侧的内存限额](#slurm-config) 讲调度器如何把额度真正落到进程上。

## <a id="concepts"></a>概念

### <a id="guest-host"></a>guest / host / 物理内存

WSL2 是一台跑在 Windows 上的轻量虚拟机，因此同一台机器上有两层操作系统：

| 术语 | 指谁 |
|---|---|
| **host（宿主）** | Windows 本体，直接管理主板上真实的内存条 |
| **guest（客户机）** | WSL2 里的 Linux，是 Windows 里的一个进程，但自身以为是独立主机 |
| **物理内存** | 主板上真实插着的内存条，硬上限 |

guest 看到的"内存总量"是宿主开出的**额度**，不是内存条。guest 里 `free` 报的 total 由 `.wslconfig` 的 `memory=` 决定，与物理内存没有直接关系，可以配得比物理内存还大。

**所有 WSL2 发行版共用同一台虚拟机**（一个内核、一份内存额度）。Docker Desktop 的 `docker-desktop` 发行版和日常使用的发行版不是两台机器，是同一台虚拟机里的两个命名空间——虚拟机停止时两边一起停，Docker 引擎随之消失，此时 Docker 的 WSL integration 也会失效（它只是把 CLI 二进制挂载进来，虚拟机重启后自动重建）。如果 Docker 出现故障，先看发行版状态：`wsl -l -v`。如果 docker-desktop 为 Stopped 说明引擎不存在，问题在虚拟机层。

### <a id="page-fault"></a>页、缺页与换页

内存以**页**为单位管理（通常 4 KiB）。程序访问的是虚拟地址，CPU 需要查页表翻译成物理地址；若发现该页当前不在物理内存里（已被写到磁盘上），就触发一次**缺页（page fault）**中断交给内核：内核把这一页从磁盘读回内存、更新页表，然后 CPU 重新执行刚才那条指令。把页在内存与磁盘之间搬进搬出这件事称为**换页**。

整个过程对程序**完全透明**——它只是执行了一条普通的读指令，唯一能感知到的是这条指令特别慢。这也是 guest 察觉不到自己的内存已经躺在宿主磁盘上的原因：这套机制的设计目标就是让上层无感。

缺页本身不是问题，**缺页的频率**才决定代价。同样的机制，一小时触发一次和每秒触发几万次是两种完全不同的东西。

### <a id="storage-terms"></a>存储介质与虚拟磁盘

换页最终要落到磁盘上，中间隔着几层，各层有各自的名词：

- **NVMe**（Non-Volatile Memory Express）：直接挂在 PCIe 总线上的固态硬盘访问协议，取代为机械盘设计的 SATA/AHCI。特点是队列深度大、并发能力强、延迟在微秒量级。日常说的"NVMe 盘"就是走这套协议的 SSD。
- **VHD / VHDX**（Virtual Hard Disk）：微软的虚拟磁盘格式，本质是宿主文件系统上的**一个大文件**，被虚拟机当成一整块硬盘使用。VHDX 是后继格式，支持更大容量和动态扩展。WSL2 的根文件系统（`ext4.vhdx`）与 swap（`swap.vhdx`）都是这种。
- **页面文件（pagefile）**：Windows 自己的交换文件（`C:\pagefile.sys`），供宿主换页使用。它与 WSL 的 swap 是**两套独立机制**，前者归宿主，后者归 guest，互不替代，也不要为了给 WSL 腾空间去关掉它。

VHDX 有两个影响容量规划的性质：

- **动态扩展**：创建时占用很小，写入多少涨多少。所以假设配置了 120 GiB swap，也不等于立刻吃掉 120 GB 磁盘。
- **不自动缩回**：释放后文件停在历史峰值，除非启用 `sparseVhd` 或手动 compact。

这意味着 swap 大小要按**能承受的磁盘峰值占用**来定，而不能随意分配。默认 swap 落在 `%Temp%`（通常在系统盘），系统盘余量紧张时用 `swapFile` 显式挪到空间充裕的盘。

### <a id="paging-paths"></a>三条换页路径

换出去的页落到哪里，在 WSL2 上有三个不同的答案。区别不在物理介质，而在**谁做的决定**和 **guest 能不能看见**：

| 路径 | 搬动的是哪些页 | 决定者 | 落到哪个文件 | guest 可见 |
|---|---|---|---|---|
| 文件页重新读回 | mmap 进来的可执行文件与共享库，以及被回收掉的页缓存 | guest 内核 | `ext4.vhdx`；`/mnt/c` 下的文件走 9p（`drvfs`）直达宿主文件系统 | 是，计入 major fault |
| 匿名页换出换入 | 进程堆栈等没有文件做后备的内存 | guest 内核 | `swap.vhdx` | 是，计入 swap in/out |
| 宿主换出虚拟机内存 | 虚拟机工作集里宿主认为冷的部分 | 宿主内核 | `pagefile.sys` | **否** |

第三条对 guest 完全隐形：guest 内核以为那一页好端端待在自己的物理内存里，访问时不产生 Linux 意义上的缺页，线程只是在虚拟化层里停住，等宿主把页取回来。所以 guest 侧 `/proc/vmstat` 的缺页与 swap 计数全都正常，唯一症状是"什么都没做但就是很慢"。

> 前两条路径的落点可以用命令查看，输出随 WSL 版本与配置而异。例如 `findmnt -no SOURCE,FSTYPE /mnt/c` 可能给出 `C:\  9p`，说明该挂载走 9p 协议直达宿主文件系统；`swapon --show` 列出的是 guest 侧的 swap 块设备（形如 `/dev/sdX`），`swap.vhdx` 是它在宿主上的对应文件名，guest 里看不到。第三条不可见源于虚拟化的两级地址转换——宿主那一级的缺页由硬件直接交给宿主内核处理，不经过 guest 内核，因而不进 guest 的任何计数；这是虚拟化通用原理，不是 WSL 特有行为。

**三条路径的物理终点是同一块盘。** `ext4.vhdx`、`swap.vhdx`、`pagefile.sys` 都是宿主 NTFS 卷上的文件，那个卷坐在物理盘（现代机器上通常是 NVMe SSD）上。虚拟磁盘、宿主文件系统、物理介质是同一条路上依次经过的三层。真正拉开延迟差距的是另外两件事：

- **层数**：guest 的一次磁盘 I/O 要穿过 guest 块设备层 → VHDX → 宿主文件系统 → 物理盘，比裸盘多几层。顺序大块读写影响有限，**随机小 I/O 惩罚明显**——而换页恰好是随机小 I/O。
- **竞争**：第三条路径与第二条可能同时发生——宿主按物理内存不足去换虚拟机的页，guest 按自己额度不足去换自己的匿名页，两个内存管理器互相看不见对方，各自独立动手。两股 I/O 落到同一块物理盘上排队，此时延迟由队列长度而不是介质决定，这是唯一能把微秒级拖到秒级的因素。

| 情况 | 量级 | 相对倍数 |
|---|---|---|
| 页在物理内存中 | ~100 ns | 1× |
| 缺页，固态盘无争用 | ~100 µs | ~10³ |
| 缺页，且宿主同时在换页、抢同一块盘 | 毫秒 ~ 秒 | 10⁴ ~ 10⁷ |

> 前两行是通用量级；第三行为 WSL2 环境下的观察区间，受宿主负载影响很大，不是稳定基准。

第一条路径与 swap 无关：内存充裕、swap 一页没写的时候它也在持续发生。`autoMemoryReclaim=dropCache` 主动丢掉的正是页缓存，代价就是这些文件页下次访问要重新读盘。

第三条 guest 看不见，只能从现象反推。两层的现象不同：

| 观察到的现象 | 更像哪一层 |
|---|---|
| 延迟中位数整体抬高，guest 内核有回收 / OOM 消息，swap 用量上涨 | guest 自己在换页或颠簸 |
| 延迟中位数不变、只有离散的秒级尖峰，多个互不相干的进程同时被冻住，guest 内核零消息 | 宿主在换出这台虚拟机 |

道理在于代价摊在哪里：guest 回收要持续扫描页表，开销分摊到所有操作上，中位数必然跟着抬；宿主换页是"平时全速运行、碰到被换走的页才整台停住"，只在最大值上留尖峰（带事件循环或心跳统计的服务最容易读出这个差别）。两者的旋钮不能互换——guest 侧颠簸调 [swap 容量与 `vm.swappiness`](#swap-semantics)，宿主换页只能调 [`memory=` 上限](#cap-vs-reservation) 或减少宿主上的其他占用，**guest 的 swap 配多大都够不到宿主那一层**。

> 这组判据从两层机制的代价分布反推，不是控制实验结论。要确认第三条正在发生，需在运行期间采样宿主侧的性能计数器。

### <a id="cap-vs-reservation"></a>内存上限、预留与超售

`.wslconfig` 里的 `memory=` 是**上限（cap）**，不是**预留（reservation）**：它表达"这台虚拟机最多能长到多大"，而不是"现在就从 Windows 划走这么多"。设置后 Windows 侧当场不会少一个字节，实际占用要等虚拟机真的长起来才出现。

Windows 的内存管理是**超售（overcommit）**的：先答应分配，等进程真正访问那块内存时才现掏物理页（按需分页）。物理内存不够时它不会拒绝，而是把较冷的页写进页面文件顶上；真到 [提交上限](#commit-accounting) 才开始拒绝分配。因此超售本身的直接后果是变慢，不是崩溃。

### <a id="commit-accounting"></a>提交量与提交上限

两层系统各有一套**提交记账**：记录"已经答应给出去多少内存"，以及"还能不能再答应"。两套术语同构、变量互不相干，先把名字对齐：

| | Windows（宿主） | Linux（WSL2 guest） |
|---|---|---|
| 已承诺总量 | system commit charge，计数器 `\Memory\Committed Bytes` | `Committed_AS`（AS = address space），见 `/proc/meminfo` |
| 上限 | system commit limit，计数器 `\Memory\Commit Limit` | `CommitLimit`，见 `/proc/meminfo` |
| 上限怎么算 | 物理内存 + 所有页面文件之和 | `SwapTotal` + `MemTotal` × `vm.overcommit_ratio` / 100（比例默认 50） |
| 承接私有页的后备存储 | 页面文件 `pagefile.sys` | swap 设备：guest 里是一块 `/dev/sdX` 块设备，宿主侧对应文件 `swap.vhdx` |
| 是否强制执行 | 始终执行 | 仅 [`vm.overcommit_memory`](#guest-sysctl) 取 `2` 时执行 |

两侧的后备存储处在**同一层次**：都只承接没有文件做后备的私有 / 匿名页；有文件后备的页两边都是回到原文件去，不占记账额度（内核文档的措辞是 "the file is the map not swap"）。Windows 侧从不用 "swap" 这个词，Linux 侧从不用"页面文件"，两边的公式各填各自的那一份。guest 的 `swap.vhdx` 属于 guest 那一层的记账；在 Windows 眼里它是宿主文件系统上的一个普通数据文件。

> Windows 侧术语与"上限 = 物理内存 + 所有页面文件之和"出自 [Microsoft Learn: Introduction to the page file](https://github.com/MicrosoftDocs/SupportArticles-docs/blob/263466baac8db65214c972c872454097957e069e/support/windows-client/performance/introduction-to-the-page-file.md)（锁到该页元数据给出的 commit）；Linux 侧出自内核文档 [Overcommit Accounting](https://www.kernel.org/doc/html/v6.12/mm/overcommit-accounting.html)（锁到 v6.12），"the file is the map not swap" 是其原文措辞。guest 侧那条公式已按 `/proc/meminfo` 的实际数值验算过。

宿主这一层的上限之所以这么算，是因为 Windows 承诺的是"你要用的时候一定有地方放"，而不是"一定放在内存条里"——放不进内存就写进页面文件，同样算兑现承诺，所以上限自然是"内存能装的 + 磁盘能顶的"。例如物理内存 512 GiB、页面文件 238 GiB 的机器，提交上限为 750 GiB。

> 两侧的数各有读法：Windows 侧 `Get-Counter '\Memory\Committed Bytes', '\Memory\Commit Limit'`；guest 侧 `grep -E 'MemTotal|SwapTotal|CommitLimit|Committed_AS' /proc/meminfo`，可据此把上表那条公式当场验算一遍。

WSL2 把 `vm.overcommit_memory` 设为 `1`（永不拒绝），因此 `CommitLimit` 照算不误却不生效，`Committed_AS` 超过它也不会有任何报错。**guest 侧默认没有"分配被拒绝"这道闸**，这是它比宿主更容易一路撞到内存耗尽的原因。

三个检查者各管各的一段，"虚拟机上限 + Windows 自身需求"这个和没有人负责：

| 检查者 | 检查什么 |
|---|---|
| WSL | 虚拟机是否 ≤ `memory=` 上限 |
| Windows 内存管理器 | 总提交量是否 ≤ 提交上限（物理内存 + 页面文件） |
| （无） | 虚拟机上限 + Windows 自身需求 是否 ≤ 物理内存 |

于是 Windows 那道检查的分母是提交上限而不是物理内存。沿用上面那台机器：若把虚拟机上限设成 480 GiB，加宿主自身某次实测的 56 GiB 得 536 GiB，小于提交上限 750 GiB 便合法放行，而它已经超过 512 GiB 物理内存，超出部分要靠页面文件兜底。**提交上限管的是"承诺不超发"，物理内存管的是"承诺兑现得快不快"，只有前者有人查。**

定 `memory=` 时应按物理内存减去宿主占用来算，这个和不交给任何自动机制把关。注意宿主占用是**随时在动的量**，取决于 Windows 那边此刻在跑什么，同一台机器隔天再量就能差出几 GiB。因此一次快照只够当参考下限，余量要按宿主的**峰值**留——否则平时看着安全，某次开了大程序就撞线。

宿主换出虚拟机内存（[三条换页路径](#paging-paths) 里的第三条）的恶化速度比换出普通进程更快：guest 内核自己也在做内存管理，它认为是热页、要留在内存里的页，宿主可能恰好换到磁盘上；guest 做内存回收时扫描页表的动作又会逼宿主把刚换出的页读回来。两个内存管理器互相看不见对方的意图。

> 机制描述基于虚拟化通用原理（语义鸿沟 / double paging）。要在具体场景中坐实，需要在作业运行期间采样宿主侧性能计数器。

### <a id="oom-livelock"></a>OOM killer 的判据与回收活锁

内核 OOM killer 的触发条件不是"内存满了"，而是——**尝试回收内存，但一页都回收不出来**。

这个判据在有 swap 存在时可能长期不成立：

```
内核：内存不够，回收一下
      → 往 swap 写出若干页 → 成功，有进展 → 不触发 OOM
进程：又要访问那些页
      → 缺页 → 从 swap 读回 → 内存又不够
内核：回收一下 → 又成功写出若干页 → 有进展 → 不触发 OOM
      ↻
```

每一轮内核都"成功"了，于是始终认为形势可控，而系统的有用功已趋近于零。这是**活锁**（livelock，与死锁的区别在于进程并未阻塞、一直在忙，只是不产出有效进展）。在虚拟磁盘上做 swap 会显著放大这个窗口，因为每轮回收都慢得多。

据此有两条配置取向：

- **swap 配小**，让故障停在"某个进程被 OOM 杀掉"而不是无限期活锁。
- **`memory=` 上限压到作业装不下的位置**，让 guest 自己先撞墙。上限若高到大作业刚好装得下，guest 全程感觉不到压力，任何 guest 侧保护都不会触发。

内核社区对"回收有没有进展"这个判据的局限有共识，**PSI（Pressure Stall Information，压力失速信息）**为此引入——它衡量"任务花了多少时间在等内存"，而不是"回收出了几页"。基于 PSI 的早期 OOM 守护进程（`systemd-oomd`、`earlyoom`、`nohang` 等）能在系统进入活锁前按压力阈值动手，把故障限制在进程级，是活锁场景下唯一能及时生效的保护。

> 内核是否支持 PSI，看 `/proc/pressure/memory` 是否存在；守护进程是否真的在跑，用 `systemctl is-active systemd-oomd` 确认——它在多数发行版随 systemd 一起装上，但默认不启用。

这类守护进程的作用范围**只到 guest 内部**。宿主换出这台虚拟机的内存时，guest 以为那些页好端端待在自己手里，PSI 读数是正常的，任何按压力阈值动作的守护进程都不会触发。换句话说，它防的是 guest 侧耗尽，防不住 [三条换页路径](#paging-paths) 里的第三条；那一层要靠把工作集压进宿主装得下的范围来防。

### <a id="swap-semantics"></a>swap 的适用场景与代价

进程**可以**使用 swap 里的数据，但任何一个瞬间，**只有位于物理内存中的部分能被 CPU 直接访问**——CPU 按字节寻址内存，硬盘是块设备，必须先把页读回内存。这是体系结构层面的界限。

由此产生两个必须分开看的量：

| | swap 的作用 |
|---|---|
| **总容量**（一共能持有多少数据） | 扩大了 |
| **活跃工作集**（同一时段能反复访问多少） | 没有帮助 |

所以 swap 更接近"内存的停车场"而不是"慢速内存"：车停在停车场里仍然属于你，但要开必须先取回车库。

划算与否只取决于**多久访问一次**：

- **冷页**（守护进程的初始化数据、错误处理路径、配置解析残留等分配后几乎不再碰的内存）：换出去腾内存，偶尔缺页一次的代价被摊薄到看不见。这是 swap 的本职工作。
- **热工作集超过物理内存**（典型如稀疏矩阵直接法分解，全量数据反复访问）：没有冷页可换，内核只能换热页，刚写出去下一秒又被要回来，进入**颠簸（thrashing）**。这种情况下 swap 不会让作业跑完，只会让它失败得更慢。

内核判断"哪些页是冷的"靠 LRU 近似（最近没访问的大概以后也少访问）。这个猜测对守护进程很准，对全量反复扫描的数值算法则系统性失效。因此 swap 容量按"要缓存多少冷页"来定，不要按"给大作业留多少余地"来定——后者是它做不到的事。

## <a id="wsl-config"></a>WSL 与 Windows 侧的配置

### <a id="layered-limits"></a>内存限额的分层结构

配置分布在三层，每层由不同的机制把关：

```
物理内存 ──── 留给 Windows（进程 + 内核 + 文件缓存 + 增长余量）
    └─ WSL 虚拟机（.wslconfig memory=）+ swap
          ├─ 非 Slurm 负载余量（容器、编辑器服务、守护进程）
          └─ Slurm 可调度（RealMemory）  ← cgroup 硬限制
                └─ 单作业默认额度（DefMemPerNode）
```

各层的定量依据：

- **留给 Windows 多少**：以实测为准。量法是把宿主进程按是否属于 WSL 虚拟机分组求和，再为增长和文件缓存留呼吸空间。
- **Slurm 拿多少**：`RealMemory` = 虚拟机内存 − 非 Slurm 负载余量。
- **单作业开多大并发**：`并发数 × 实测单进程峰值 × 安全系数 ≤ 作业额度`。

上面两层的配置在本部分讲，下面两层见 [Slurm 侧的内存限额](#slurm-config)。

### <a id="wslconfig-memory"></a>`.wslconfig` 的内存相关键

`.wslconfig` 位于 Windows 用户目录（`%UserProfile%\.wslconfig`），作用于**所有** WSL2 发行版。改动需要 `wsl --shutdown` 后重启才生效，因此调整前先停掉依赖虚拟机的服务（如 Docker Desktop）。

> 键的定义与默认值出自 [Microsoft Learn: Advanced settings configuration in WSL](https://github.com/MicrosoftDocs/WSL/blob/7b28cc1ee9b8ff672ada5e1c6c326d3573d703e5/WSL/wsl-config.md)（锁到该页元数据给出的 commit）。

| 键 | 默认值 | 说明 |
|---|---|---|
| `memory` | Windows 物理内存的 50% | 虚拟机内存上限。写法 `384GB` / `512MB`，省略单位按字节 |
| `swap` | **虚拟机内存上限（`memory` 的取值）的 25%**，向上取整到 GB | 虚拟机 swap 大小，`0` 为禁用 |
| `swapFile` | `%Temp%\swap.vhdx` | swap 虚拟磁盘路径 |
| `processors` | 与 Windows 逻辑处理器数相同 | 分配给虚拟机的逻辑处理器数 |
| `autoMemoryReclaim`（`[experimental]` 段） | **`dropCache`** | 见下 |

`swap` 与 `autoMemoryReclaim` 的默认值都不是"关闭"：不写 `swap=` 会按 `memory` 的 25% 自动折算（例如 `memory=480GB` 对应 120 GiB swap），不写 `autoMemoryReclaim` 时回收机制仍在工作。要控制这两项必须显式写出来。

两个默认值叠加时基数会连乘：`memory` 不写时是物理内存的 50%，`swap` 再取它的 25%，最终等于**物理内存的 12.5%**。例如一台 512 GiB 物理内存的机器两项都不配，拿到的是 256 GiB 虚拟机内存加 64 GiB swap。

> `swap` 默认值的基数在官方文档里有两种措辞：键表写 "25% of memory size on Windows"，同页示例注释写 "25% of available RAM"，两者基数不同。以前者为准——在一台配置了 `memory=480GB`、物理内存 512 GiB 的机器上，内核日志记录的 swap 设备为 `125829120k`，恰为 480 GiB 的 25%，而不是 512 GiB 的 25%。

`autoMemoryReclaim` 三个取值：

| 值 | 行为 |
|---|---|
| `disabled` | 关闭 WSL 的自动内存回收（Linux 自身在内存压力下仍会正常回收） |
| `gradual` | 缓慢、分批地回收缓存内存 |
| `dropCache` | 立即回收缓存内存；**默认值**，无法识别的取值也按此处理 |

> 实现细节出自 [WSL 官方博客 2023-09 更新](https://devblogs.microsoft.com/commandline/windows-subsystem-for-linux-september-2023-update/)（该版本引入此特性）：检测到 CPU 持续低负载约 5 分钟后开始回收；`gradual` 走 cgroup v2 的 `memory.reclaim` 分批释放。当前文档只保证"渐进"与"立即"这层语义，具体时间常数属实现细节。

它回收的是可回收缓存（文件页），且在 CPU 空闲后才动作，因此不能当作限制运行中进程内存用量的手段——那是 [内存限额的分层结构](#layered-limits) 里几层配置的职责。选 `dropCache` 换更快归还宿主内存，选 `gradual` 换更高的缓存命中率；被回收的缓存页对应的文件，进程下次访问需要重新读盘。

### <a id="guest-sysctl"></a>WSL 侧的 sysctl 参数

这几个是 **Linux 内核参数**，在 guest 里配置，与 `.wslconfig` 无关。`sysctl <名字>` 读当前值，`sysctl -w <名字>=<值>` 临时改（重启失效），持久化要写进 `/etc/sysctl.d/`。

- **`vm.swappiness`**（Linux 默认 60，取值 0–200）：内存吃紧时，内核在"回收文件缓存"和"回收匿名内存（进程堆栈，必须先写进 swap）"之间的**倾向权重**，数值高偏向后者。它不是"最多用多少比例的 swap"。调低（如 10）能推迟颠簸，属于缓解手段——内存真到底时该用 swap 还是会用。

- **`vm.overcommit_memory`**：`0` 启发式判断（明显离谱的申请才拒绝，Linux 默认）、`1` 永不拒绝、`2` 严格限额（即真正执行 [guest 侧的 `CommitLimit`](#commit-accounting)）。WSL2 环境下取值为 `1`，且不来自 `/etc/sysctl.conf`、`/etc/sysctl.d/`、`/run/sysctl.d/`、`/usr/lib/sysctl.d/` 中的任何条目，是运行时设定的。含义是内核对内存申请永远说 yes，进程可以一路申请到把整个虚拟机撞满，申请阶段不会有任何报错。改成 `2` 能让程序拿到干净的"内存不足"错误并自行退出，代价是很多程序会乐观超额申请、可能被误伤。

### <a id="accounting"></a>两侧内存用量的核对

两侧的数要可比，先得选对 guest 侧的口径。`/proc/meminfo` 里三个量的含义：

| 字段 | 含义 |
|---|---|
| `MemTotal` | 内核可支配的物理内存总量。guest 里就是虚拟机拿到的额度，比 `.wslconfig` 的 `memory=` 略小（内核自身预留掉一部分） |
| `MemFree` | 完全空着、一个字节都没装的页 |
| `MemAvailable` | 内核估计"还能拿给新进程用多少"，把可回收的缓存算作可用，但排除掉估计回收不动的部分 |

因此 **`MemTotal − MemFree` = 所有已经装了东西的页**，无论装的是进程数据还是文件缓存。这正是宿主眼里这台虚拟机占住的物理页数量，所以两侧可比。

而 `free` 的 `used` 列**刻意不含页缓存**（内核认为缓存随时可回收，不算真正占用），它算的是 `MemTotal − MemAvailable`。注意 `used` 也**不等于** `MemTotal − MemFree − buff/cache`——`MemAvailable` 还额外扣掉了那部分回收不动的缓存，两者会差出几 GiB。要含缓存的口径就直接相减，别拿 `used` 加 `buff/cache` 凑：

```bash
# guest 侧：含缓存的真实占用
awk '/MemTotal/{t=$2} /MemFree/{f=$2} END{printf "%.1f GiB\n", (t-f)/1048576}' /proc/meminfo
```

宿主侧对应的是 WSL 虚拟机进程（`vmmemWSL`，旧版本叫 `vmmem`）的工作集：

```powershell
"{0:N1} GiB" -f ((Get-Process vmmemWSL).WorkingSet64/1GB)
```

在某台机器上做过这样一次标定：在 guest 内分配 30 GiB 匿名内存（逐页触碰以强制真实占用），双侧同步采样。表中的绝对值取决于该机器的配置与当时负载，可复用的是各列之间的关系：

| 阶段 | guest `MemTotal−MemFree` | host 虚拟机工作集 | 差值 |
|---|---:|---:|---:|
| 基线 | 42.1 GiB | 48.6 GiB | 6.5 |
| 分配 30 GiB | 72.1 GiB | 78.5 GiB | 6.4 |
| 持续占用 | 72.1 GiB | 78.5 GiB | 6.4 |
| 释放后 +5 s | 42.1 GiB | 57.8 GiB | 15.7 |
| 释放后 +30 s | 42.1 GiB | 48.9 GiB | 6.8 |

三条可复用的性质：

- **两侧按 1:1 同步**：上例中 guest 分配 30.0 GiB，宿主侧增长 29.9 GiB。
- **存在恒定开销**：两侧存在一个不随负载变化的固定差值，来自虚拟机自身（内核、虚拟设备、hypervisor 结构），读数时把它扣掉。这个差值的大小随虚拟机规格而定，上例中约为 6.5 GiB，用之前先在空载时量一次。
- **宿主侧退还有滞后**：guest 释放后 `MemFree` 立即恢复，宿主侧工作集要过一阵才退回基线（上例约 30 秒）。作业跑完后别急着读宿主数字。

长时间读取大量日志或文件后，宿主侧虚拟机内存会持续上涨，这来自**页缓存**增长，属于可回收内存。判别方式是看 guest 的 `buff/cache` 是否同步增长——同步增长即为缓存，`used` 单独增长才是进程真实占用。

## <a id="slurm-config"></a>Slurm 侧的内存限额

### <a id="slurm-memory"></a>参数与 cgroup 落点

Slurm 要真正限制住作业内存，需要几处配置协同，缺一处就只是记账而没有强制力。

`slurm.conf` 相关键：

| 键 | 作用 |
|---|---|
| `SelectType=select/cons_tres` + `SelectTypeParameters=CR_CORE_MEMORY` | 让内存成为可消费资源参与调度，而不只是标签 |
| `TaskPlugin=task/cgroup,task/affinity` | 由 cgroup 落实限制 |
| `ProctrackType=proctrack/cgroup` | 用 cgroup 跟踪进程，防止逃逸 |
| `NodeName=... RealMemory=<MiB>` | 节点**声明**的可调度内存，是配置值而非探测值 |
| `PartitionName=... DefMemPerNode=<MiB>` | 作业未指定 `--mem` 时的默认额度 |
| `PartitionName=... MaxMemPerNode=<MiB>` | 单节点内存请求上限，超出直接拒绝 |

`cgroup.conf` 相关键：`ConstrainRAMSpace`、`ConstrainSwapSpace`（是否真的施加限制），`AllowedRAMSpace`、`AllowedSwapSpace`（相对请求量的百分比，后者设 `0` 表示禁止作业使用 swap）。

`DefMemPerNode` 的默认值是 `UNLIMITED`，含义是未写 `--mem` 的作业拿到整个节点的内存。把它设成一个明确的小值（如 16 GiB），能让"提交时忘写参数"表现为该作业失败，而不是占满节点。

`RealMemory` 要给节点上的非 Slurm 负载留余量——容器、编辑器远程服务、各类守护进程都在同一份内存里且不受 Slurm 管辖。余量按这些负载**全部启动之后**的占用估。

验证限制是否落地时，注意 cgroup 的层级：限制挂在 **job 层**，作业进程所在的叶子 task cgroup 显示为 `max`（Slurm 25.11 / 26.05，cgroup v2）：

```
/system.slice/slurmstepd.scope/job_<id>                       ← memory.max = 请求值
/system.slice/slurmstepd.scope/job_<id>/step_<n>              ← max
/system.slice/slurmstepd.scope/job_<id>/step_<n>/user         ← memory.max = 请求值
/system.slice/slurmstepd.scope/job_<id>/step_<n>/user/task_0  ← max
```

因此要从 `/proc/self/cgroup` 给出的路径**逐级向上**检查，而不是只看进程所在的叶子目录：

```bash
srun -N1 -n1 --mem=100M bash -lc '
  p=$(cut -d: -f3 /proc/self/cgroup)
  while [ "$p" != "/" ]; do
    [ -f "/sys/fs/cgroup$p/memory.max" ] && echo "$p = $(cat /sys/fs/cgroup$p/memory.max)"
    p=${p%/*}; [ -n "$p" ] || p=/
  done'
```

端到端的确认方式是提交刚好越界的作业：请求等于 `MaxMemPerNode` 应正常运行，多 1 GiB 应返回 `Requested node configuration is not available`。

### <a id="peak-measurement"></a>并发数与单进程实测峰值

峰值必须**实测**，不能按矩阵规模外推。稀疏矩阵直接法（LU / Cholesky 分解）的内存主要来自**填充（fill-in）**——分解过程中产生的新非零元，而非原矩阵的非零元；填充量由消去顺序和图结构决定。作为量级参考，某个算例中：同样规模、同样解法器，仅因边界条件从非周期改为周期（网格拓扑从"盒"变成"环面"、分离子规模翻倍），非零元只增加约 1.3%，单进程峰值内存却涨了约 2.8 倍。倍数本身不可搬用，可搬用的是结论——做法是先用 1 个进程跑一遍量出峰值 RSS，再据此定并发数。

### <a id="bypass-scheduler"></a>不经调度器启动的进程

直接调用 `mpiexec` / `mpirun` 启动的进程不经过调度器，因此不受任何 cgroup 约束。要让限额覆盖到它们，二选一：

- 统一改走调度器（`srun` / `sbatch` 并显式写 `--mem`）；
- 无调度器场景下用 systemd 临时作用域给进程组套 cgroup 限制，例如通过 `systemd-run --scope` 指定 `MemoryMax` / `MemoryHigh` / `MemorySwapMax`。

在 guest 里跑轮询总 RSS 的看门狗脚本可以作为补充，但它读的是 guest 侧数字，看不见宿主是否正在为这台虚拟机换页。因此它的阈值按物理内存倒推着定，不按 guest 的 `free` 定。

### <a id="config-example"></a>各层取值示例

把上面几层落成具体数值。以 512 GiB 物理内存、跑 MPI 数值作业的机器为例：

| 起因 | 该拧的旋钮 | 示例取值 |
|---|---|---|
| 虚拟机工作集逼近物理内存，宿主开始换出它 | `.wslconfig` 的 `memory=`，压到"物理内存 − 宿主实测占用"以内 | `memory=384GB`，留约 128 GiB 给 Windows |
| swap 建在虚拟磁盘上，且大到足以让内核长期判定"回收有进展"而不触发 OOM | `.wslconfig` 的 `swap=`，缩到只够缓存冷页 | `swap=32GB`；不显式写会按 `memory` 的 25% 折算成 96 GiB |
| 回收行为不确定，宿主内存归还时机不可控 | `.wslconfig` 的 `autoMemoryReclaim`，显式写出而非依赖默认 | `autoMemoryReclaim=dropCache` |
| 调度器认的额度大于虚拟机真正装得下的量，作业被放行后才撞墙 | `slurm.conf` 的 `RealMemory` 与 `MaxMemPerNode` | `RealMemory=286720`（280 GiB），给非 Slurm 负载留约 98 GiB |
| 作业不写 `--mem` 就独占整个节点 | `slurm.conf` 的 `DefMemPerNode` | `DefMemPerNode=16384` |
| 并发数 × 单进程峰值超出作业额度 | 并发数，按实测单进程峰值倒推 | 单进程实测峰值 47.8 GiB、额度 280 GiB 时取 4 路而非 8 路 |

生效方式不同：`.wslconfig` 要 `wsl --shutdown` 后重启虚拟机；`slurm.conf` 改完 `scontrol reconfigure` 热加载即可，改前留一份带时间戳的备份。改完 `memory=` 后按 [两侧内存用量的核对](#accounting) 那节的方法复核两侧数字，确认虚拟机上限加宿主实测占用确实落在物理内存以内。
