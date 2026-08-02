# Windows / WSL2 的内存模型

在 WSL2 上跑大内存作业时，"还剩多少内存可用"这个问题在三个位置有三个互不相同的答案：Linux 里的 `free`、Windows 看到的虚拟机工作集、以及作业调度器认的额度。三者口径不同、彼此看不见。本篇讲清这几层各自的语义、可配置项，以及怎么量出真实数字。

## <a id="guest-host"></a>guest / host / 物理内存

WSL2 是一台跑在 Windows 上的轻量虚拟机，因此同一台机器上有两层操作系统：

| 术语 | 指谁 |
|---|---|
| **host（宿主）** | Windows 本体，直接管理主板上真实的内存条 |
| **guest（客户机）** | WSL2 里的 Linux，是 Windows 里的一个进程，但自身以为是独立主机 |
| **物理内存** | 主板上真实插着的内存条，硬上限 |

guest 看到的"内存总量"是宿主开出的**额度**，不是内存条。guest 里 `free` 报的 total 由 `.wslconfig` 的 `memory=` 决定，与物理内存没有直接关系，可以配得比物理内存还大。

**所有 WSL2 发行版共用同一台虚拟机**（一个内核、一份内存额度）。Docker Desktop 的 `docker-desktop` 发行版和日常使用的发行版不是两台机器，是同一台虚拟机里的两个命名空间——虚拟机停止时两边一起停，Docker 引擎随之消失，此时 Docker 的 WSL integration 也会失效（它只是把 CLI 二进制挂载进来，虚拟机重启后自动重建）。判断 Docker 故障属于哪一层，先看发行版状态：

```powershell
wsl -l -v          # docker-desktop 为 Stopped 说明引擎不存在，问题在虚拟机层
```

## <a id="page-fault"></a>页与缺页

内存以**页**为单位管理（通常 4 KiB）。程序访问的是虚拟地址，CPU 需要查页表翻译成物理地址；若发现该页当前不在物理内存里（已被写到磁盘上），就触发一次**缺页（page fault）**中断交给内核：内核把这一页从磁盘读回内存、更新页表，然后 CPU 重新执行刚才那条指令。把页在内存与磁盘之间搬进搬出这件事称为**换页**。

整个过程对程序**完全透明**——它只是执行了一条普通的读指令，唯一能感知到的是这条指令特别慢。这也是 guest 察觉不到自己的内存已经躺在宿主磁盘上的原因：这套机制的设计目标就是让上层无感。

缺页本身不是问题，**缺页的频率**才决定代价。同样的机制，一小时触发一次和每秒触发几万次是两种完全不同的东西。

## <a id="storage-terms"></a>存储介质与虚拟磁盘术语

换页落到什么介质上，决定了上面那个"特别慢"到底有多慢。相关的几个名词：

- **NVMe**（Non-Volatile Memory Express）：直接挂在 PCIe 总线上的固态硬盘访问协议，取代为机械盘设计的 SATA/AHCI。特点是队列深度大、并发能力强、延迟在微秒量级。日常说的"NVMe 盘"就是走这套协议的 SSD。
- **VHD / VHDX**（Virtual Hard Disk）：微软的虚拟磁盘格式，本质是宿主文件系统上的**一个大文件**，被虚拟机当成一整块硬盘使用。VHDX 是后继格式，支持更大容量和动态扩展。WSL2 的根文件系统（`ext4.vhdx`）与 swap（`swap.vhdx`）都是这种。
- **页面文件（pagefile）**：Windows 自己的交换文件（`C:\pagefile.sys`），供宿主换页使用。它与 WSL 的 swap 是**两套独立机制**，前者归宿主，后者归 guest，互不替代，也不要为了给 WSL 腾空间去关掉它。

VHDX 有两个影响容量规划的性质：

- **动态扩展**：创建时占用很小，写入多少涨多少。所以"配置 120 GiB swap"不等于"立刻吃掉 120 GB 磁盘"。
- **不自动缩回**：释放后文件停在历史峰值，除非启用 `sparseVhd` 或手动 compact。

两者合起来意味着 swap 大小要按**能承受的磁盘峰值占用**来定，而不是按"反正用不到那么多"。默认 swap 落在 `%Temp%`（通常在系统盘），系统盘余量紧张时用 `swapFile` 显式挪到空间充裕的盘。

guest 的一次磁盘 I/O 要穿过 guest 块设备层 → VHDX → 宿主文件系统 → 物理盘，比裸盘多几层。顺序大块读写影响有限，**随机小 I/O 惩罚明显**——而换页恰好是随机小 I/O。各级访问延迟的量级：

| 情况 | 量级 | 相对倍数 |
|---|---|---|
| 页在物理内存中 | ~100 ns | 1× |
| 缺页，从 NVMe SSD 读回 | ~100 µs | ~10³ |
| 缺页，从 VHD 上的 swap 读回，且宿主同时在换页 | 毫秒 ~ 秒 | 10⁴ ~ 10⁷ |

> 前两行是通用量级；第三行为 WSL2 环境下的观察区间，受宿主负载影响很大，不是稳定基准。

## <a id="cap-vs-reservation"></a>内存上限、预留与超售

`.wslconfig` 里的 `memory=` 是**上限（cap）**，不是**预留（reservation）**：它表达"这台虚拟机最多能长到多大"，而不是"现在就从 Windows 划走这么多"。设置后 Windows 侧当场不会少一个字节，实际占用要等虚拟机真的长起来才出现。

Windows 的内存管理是**超售（overcommit）**的：先答应分配，等进程真正访问那块内存时才现掏物理页（按需分页）。物理内存不够时它不会拒绝，而是把较冷的页写进页面文件顶上；真到提交上限才开始拒绝分配。因此超售本身的直接后果是变慢，不是崩溃。

这里的记账口径是**提交量（commit charge）**——所有已经答应给出去的内存总和；能不能再答应，看的是**提交上限（commit limit）**：

```
提交上限 = 物理内存 + 页面文件大小
```

这么定的理由是，Windows 承诺的是"你要用的时候一定有地方放"，而不是"一定放在内存条里"——放不进内存就写进页面文件，同样算兑现承诺。所以上限自然是"内存能装的 + 磁盘能顶的"。例如物理内存 512 GiB、页面文件 238 GiB 的机器，提交上限为 750 GiB。读法：

```powershell
Get-Counter '\Memory\Committed Bytes', '\Memory\Commit Limit'
```

三个检查者各管各的一段，"虚拟机上限 + Windows 自身需求"这个和没有人负责：

| 检查者 | 检查什么 |
|---|---|
| WSL | 虚拟机是否 ≤ `memory=` 上限 |
| Windows 内存管理器 | 总提交量是否 ≤ 提交上限（物理内存 + 页面文件） |
| （无） | 虚拟机上限 + Windows 自身需求 是否 ≤ 物理内存 |

于是 Windows 那道检查的分母是提交上限而不是物理内存：虚拟机上限 480 GiB 加宿主自身 56 GiB 得 536 GiB，小于 750 GiB 便合法放行，而它已经超过 512 GiB 物理内存，超出部分要靠页面文件兜底。**提交上限管的是"承诺不超发"，物理内存管的是"承诺兑现得快不快"，只有前者有人查。**定 `memory=` 时应按物理内存减去宿主实测占用来算，这个和不交给任何自动机制把关。

虚拟机被换页时的恶化速度比普通进程被换页更快：guest 内核自己也在做内存管理，它认为是热页、要留在内存里的页，宿主可能恰好换到磁盘上；guest 做内存回收时扫描页表的动作又会逼宿主把刚换出的页读回来。两个内存管理器互相看不见对方的意图。

> 机制描述基于虚拟化通用原理（语义鸿沟 / double paging）。要在具体场景中坐实，需要在作业运行期间采样宿主侧性能计数器。

## <a id="swap-semantics"></a>swap 的适用场景与代价

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

## <a id="wslconfig-memory"></a>`.wslconfig` 的内存相关键

`.wslconfig` 位于 Windows 用户目录（`%UserProfile%\.wslconfig`），作用于**所有** WSL2 发行版。改动需要 `wsl --shutdown` 后重启才生效，因此调整前先停掉依赖虚拟机的服务（如 Docker Desktop）。

> 键的定义与默认值出自 [Microsoft Learn: Advanced settings configuration in WSL](https://github.com/MicrosoftDocs/WSL/blob/7b28cc1ee9b8ff672ada5e1c6c326d3573d703e5/WSL/wsl-config.md)（锁到该页元数据给出的 commit）。

| 键 | 默认值 | 说明 |
|---|---|---|
| `memory` | Windows 物理内存的 50% | 虚拟机内存上限。写法 `384GB` / `512MB`，省略单位按字节 |
| `swap` | **内存大小的 25%**，向上取整到 GB | 虚拟机 swap 大小，`0` 为禁用 |
| `swapFile` | `%Temp%\swap.vhdx` | swap 虚拟磁盘路径 |
| `processors` | 与 Windows 逻辑处理器数相同 | 分配给虚拟机的逻辑处理器数 |
| `autoMemoryReclaim`（`[experimental]` 段） | **`dropCache`** | 见下 |

`swap` 与 `autoMemoryReclaim` 的默认值都不是"关闭"：不写 `swap=` 会按 `memory` 的 25% 自动折算（`memory=480GB` 对应 120 GiB swap），不写 `autoMemoryReclaim` 时回收机制仍在工作。要控制这两项必须显式写出来。

`autoMemoryReclaim` 三个取值：

| 值 | 行为 |
|---|---|
| `disabled` | 关闭 WSL 的自动内存回收（Linux 自身在内存压力下仍会正常回收） |
| `gradual` | 缓慢、分批地回收缓存内存 |
| `dropCache` | 立即回收缓存内存；**默认值**，无法识别的取值也按此处理 |

> 实现细节出自 [WSL 官方博客 2023-09 更新](https://devblogs.microsoft.com/commandline/windows-subsystem-for-linux-september-2023-update/)（该版本引入此特性）：检测到 CPU 持续低负载约 5 分钟后开始回收；`gradual` 走 cgroup v2 的 `memory.reclaim` 分批释放。当前文档只保证"渐进"与"立即"这层语义，具体时间常数属实现细节。

它回收的是可回收缓存（文件页），且在 CPU 空闲后才动作，因此不能当作限制运行中进程内存用量的手段——那是 [内存限额的分层结构](#layered-limits) 里几层配置的职责。选 `dropCache` 换更快归还宿主内存，选 `gradual` 换更高的缓存命中率；被回收的缓存页对应的文件，进程下次访问需要重新读盘。

## <a id="guest-sysctl"></a>guest 侧内存 sysctl

这几个是 **Linux 内核参数**，在 guest 里配置，与 `.wslconfig` 无关。读法 `sysctl <名字>`，临时改 `sysctl -w`，持久化写进 `/etc/sysctl.d/`。

- **`vm.swappiness`**（Linux 默认 60，取值 0–200）：内存吃紧时，内核在"回收文件缓存"和"回收匿名内存（进程堆栈，必须先写进 swap）"之间的**倾向权重**，数值高偏向后者。它不是"最多用多少比例的 swap"。调低（如 10）能推迟颠簸，属于缓解手段——内存真到底时该用 swap 还是会用。

- **`vm.overcommit_memory`**：`0` 启发式判断、`1` 永不拒绝、`2` 按 `overcommit_ratio` 严格限额。WSL2 环境下取值为 `1`，且不来自 `/etc/sysctl.conf`、`/etc/sysctl.d/`、`/run/sysctl.d/`、`/usr/lib/sysctl.d/` 中的任何条目，是运行时设定的。含义是内核对内存申请永远说 yes，进程可以一路申请到把整个虚拟机撞满，申请阶段不会有任何报错。改成 `2` 能让程序拿到干净的"内存不足"错误并自行退出，代价是很多程序会乐观超额申请、可能被误伤。

## <a id="oom-livelock"></a>OOM killer 的触发条件与回收活锁

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

内核社区对"回收有没有进展"这个判据的局限有共识，**PSI（Pressure Stall Information，压力失速信息）**为此引入——它衡量"任务花了多少时间在等内存"，而不是"回收出了几页"。可用性检查：

```bash
cat /proc/pressure/memory     # 文件存在即内核支持 PSI
```

基于 PSI 的早期 OOM 守护进程（`systemd-oomd`、`earlyoom`、`nohang` 等）能在系统进入活锁前按压力阈值动手，把故障限制在进程级。这是活锁场景下唯一能及时生效的保护，配置时确认服务真的处于活动状态（`systemd-oomd` 在多数发行版随 systemd 装上，但默认不启用）：

```bash
systemctl is-active systemd-oomd
```

## <a id="accounting"></a>guest 与 host 的内存计量口径

**`free` 的 `used` 列刻意不含页缓存**（内核认为缓存随时可回收，不算真正占用），而宿主看到的是虚拟机的**全部**工作集，缓存也是实实在在的物理页。因此两侧对比要用 `MemTotal − MemFree`：

```bash
# guest 侧：含缓存的真实占用
awk '/MemTotal/{t=$2} /MemFree/{f=$2} END{printf "%.1f GiB\n", (t-f)/1048576}' /proc/meminfo
```

宿主侧对应的是 WSL 虚拟机进程（`vmmemWSL`，旧版本叫 `vmmem`）的工作集：

```powershell
"{0:N1} GiB" -f ((Get-Process vmmemWSL).WorkingSet64/1GB)
```

在 guest 内分配 30 GiB 匿名内存（逐页触碰以强制真实占用）并双侧同步采样，得到的对应关系：

| 阶段 | guest `MemTotal−MemFree` | host 虚拟机工作集 | 差值 |
|---|---:|---:|---:|
| 基线 | 42.1 GiB | 48.6 GiB | 6.5 |
| 分配 30 GiB | 72.1 GiB | 78.5 GiB | 6.4 |
| 持续占用 | 72.1 GiB | 78.5 GiB | 6.4 |
| 释放后 +5 s | 42.1 GiB | 57.8 GiB | 15.7 |
| 释放后 +30 s | 42.1 GiB | 48.9 GiB | 6.8 |

三条可复用的性质：

- **两侧按 1:1 同步**：分配 30.0 GiB，宿主侧增长 29.9 GiB。
- **存在恒定开销**：约 6.5 GiB 的固定差值来自虚拟机自身（内核、虚拟设备、hypervisor 结构），不随负载变化，读数时把它扣掉。
- **宿主侧退还有滞后**：guest 释放后 `MemFree` 立即恢复，宿主侧工作集约 30 秒后退回基线。作业跑完后要等半分钟再读宿主数字。

长时间读取大量日志或文件后，宿主侧虚拟机内存会持续上涨，这来自**页缓存**增长，属于可回收内存。判别方式是看 guest 的 `buff/cache` 是否同步增长——同步增长即为缓存，`used` 单独增长才是进程真实占用。

## <a id="slurm-memory"></a>Slurm 的内存限额与 cgroup 落点

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

## <a id="layered-limits"></a>内存限额的分层结构

把上面几层叠起来：

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

峰值必须**实测**，不能按矩阵规模外推。稀疏矩阵直接法（LU / Cholesky 分解）的内存主要来自**填充（fill-in）**——分解过程中产生的新非零元，而非原矩阵的非零元；填充量由消去顺序和图结构决定。作为量级参考：同样规模、同样解法器，仅因边界条件从非周期改为周期（网格拓扑从"盒"变成"环面"、分离子规模翻倍），非零元只增加约 1.3%，单进程峰值内存涨约 2.8 倍。做法是先用 1 个进程跑一遍量出峰值 RSS，再据此定并发数。

直接调用 `mpiexec` / `mpirun` 启动的进程不经过调度器，因此不受任何 cgroup 约束。要让限额覆盖到它们，二选一：

- 统一改走调度器（`srun` / `sbatch` 并显式写 `--mem`）；
- 无调度器场景下用 systemd 临时作用域给进程组套 cgroup 限制，例如通过 `systemd-run --scope` 指定 `MemoryMax` / `MemoryHigh` / `MemorySwapMax`。

在 guest 里跑轮询总 RSS 的看门狗脚本可以作为补充，但它读的是 guest 侧数字，看不见宿主是否正在为这台虚拟机换页。因此它的阈值按物理内存倒推着定，不按 guest 的 `free` 定。
