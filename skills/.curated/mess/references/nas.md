# NAS / Synology 相关已知坑

> 两类坑都记在这：① Synology DSM 自家魔改 docker 的怪异行为，跟上游 docker / docker-compose 不一致的部分；② NAS-backed 存储（iSCSI LUN / NFS / SMB）挂到其他宿主后，性能特征或故障模式跟本地盘不一样、容易被误判的情况。

## DSM Container Manager: `failed to initialize logging driver: database is blocked` (短时间多次 recreate 触发)

### 症状

短时间内（5-10 min 内）对同一个项目做多次 `recreate` / `stop+start` 操作后，再次尝试启动容器报：

```
failed to initialize logging driver: database is blocked
```

容器状态卡在 stopped / 启动失败循环。**单独的 docker 命令、`docker compose ps` 等正常运行。**

### 误导路径

容易误判：
1. ❌ 以为是**自家应用**（如 RustFS / Postgres）的内部数据库 lock —— 去翻应用源码搜 “database is blocked”，0 匹配
2. ❌ 以为是**应用 RocksDB / SQLite metadata** stale lock —— 去找 LOCK 文件清理
3. ❌ 以为是**最近改的 compose 文件**（init container / volume mount / chown）有副作用 —— 回滚 compose 也修不好

### 实际 root cause

`logging driver` 是 **docker daemon 自家术语**，指 docker 用来抓容器 stdout/stderr 的 driver（默认 `json-file`），写到 `/var/lib/docker/containers/<id>/<id>-json.log`。

`database is blocked` 是 **Synology DSM 魔改 docker** 用来跟踪 container 元数据的 SQLite 撞 WAL lock。短时间多次 recreate 让 sqlite WAL 没机会释放就被下一次操作覆盖，最终 daemon 拿不到 lock。

跟应用层（RustFS / Postgres / 任何业务容器）**完全无关**。跟你最近改的 compose / chown / bind mount **也无关**。

### 修法（按代价从轻到重）

1. **等 1-2 分钟后再试启动** —— sqlite WAL 自然释放（绝大多数情况这步搞定）
2. **DSM 控制面板 → 套件中心 → Container Manager → 停用 → 启用** —— 重启 docker daemon，强制释放所有 lock（~30s）
3. **DSM 重启**（不推荐，影响一切）

> ⚠️ **绝对不要 “卸载 Container Manager”**：bind mount (在 `/volume1/docker/` 下) 安全，但 **named volume**（在 `/volume1/@docker/volumes/`，属套件管辖）**有丢的风险**。停用 → 启用 跟卸载不一样，前者绝对安全。

### 预防

短时间内**不要**做密集 recreate 操作。试探性 compose 改动建议：

1. 先把所有候选方案列全（B/D/...）
2. 一次性选定方向
3. 一次 recreate 验证

避免“改 → recreate → 看结果 → 改回 → recreate → 再改 → recreate”这种密集循环触发。

### 关键词

`failed to initialize logging driver`、`database is blocked`、`DSM Container Manager`、`Synology docker`、`json-file driver`、`SQLite WAL lock`、`短时间多次 recreate`、`/var/packages/ContainerManager`、`/volume1/@docker`、`logging driver` (docker daemon 概念,不是应用日志)、`停用启用 Container Manager`

## Postgres 崩溃恢复卡在 checkpoint「像是死了」，其实是 NAS iSCSI LUN 上的 fsync 巨慢（不是真卡死）

> 2026-07-05 | Postgres 17 + pgvector（`qatlas-postgres` 容器）| PGDATA 挂在 NAS（Synology DSM 建 iSCSI Target/LUN）→ Windows iSCSI Initiator → `wsl --mount` 挂进 WSL2 为 `/dev/sdg` → `/mnt/qatlas-pg`（ext4）

> 记录原则：这次判断一度是错的（"卡死"），事后才发现只是慢。如实记录当时凭什么下的判断、以及这个判断方法本身的局限。

### 症状

- 因为处理另一件事（见上一条 Docker 内置 DNS 案例）被迫 `docker rm -f` 强制移除了这个 Postgres 容器，重建后触发崩溃恢复：WAL redo 阶段正常（约56秒，LSN 持续增长，日志有真实进度），之后进入 `checkpoint starting: end-of-recovery immediate wait`。
- 这一步之后看起来彻底不动了：
  - `docker top qatlas-postgres` 显示 checkpointer 进程长期处于 **`Ds`**（不可中断磁盘睡眠）状态，CPU 恒为 `0.00%`。
  - `docker stats` 的 **BlockIO 字节计数器**在相隔 20 秒、90 秒、10 分钟、直到最终 **21+ 分钟**的多次复测中，数值分毫不变（`153MB / 176kB` 恒定）。
  - `/mnt/qatlas-pg` 挂载本身当时查询（`df -h`、`ls`）响应迅速正常——不支持"整条 iSCSI 链路当前彻底断线"这么简单的解释。

### 排查关键转折（含一个错误判断）

- 基于上面的证据（`Ds` + 0%CPU + 计数器长时间不变），当时**判定为"真卡死"**：Linux 里 D 状态通常意味着进程卡在一个不会超时的内核态 I/O 系统调用上，SIGKILL 对它无效，一般只能等这个具体 I/O 请求最终返回，或用更底层手段（重启 WSL2/Docker Desktop）强制解除。这个推理本身没错，但**推出的结论（"真卡死"）后来被证明是错的**。
- 用户叫停（"不着急，别搞坏那边的东西"）后改为纯观察，不再做任何操作。等待期间去翻了另一个历史 session 的记录，发现这个库的 PGDATA 实际上跑在 NAS 提供的 iSCSI LUN 上，且历史上已经有过明确分析："纯粹卡在写路径 / WAL fsync——每次 commit 都要等网络存储 fsync 落盘，这是硬地板"，当时的库还有一张约 262M 行 / 49GB 的大表。
- 后续复查时，checkpoint **自己跑完了**。真实日志给出了铁证：
  ```
  checkpoint complete: wrote 1514626 buffers (24.1%); ...
  write=675.878 s, sync=727.911 s, total=1406.334 s;
  sync files=79, longest=565.499 s, average=9.186 s
  database system is ready to accept connections
  ```
  单个文件 fsync 最长耗时 **565 秒（9.4 分钟）**，总耗时 **1406 秒（23.4 分钟）**。

### 根因

不是卡死，是真的慢：`end-of-recovery` checkpoint 要把崩溃前的脏页全部刷盘并 fsync，而 PGDATA 落在 NAS-backed iSCSI 网络存储上，单个文件的 fsync 延迟可以长达 9 分钟以上。之前判断"卡死"所依赖的观测窗口（最长 21 分钟）**在统计学上根本不够长**——相对于"单次操作可能耗时 9 分钟"这个真实分布，21 分钟内"看起来没有变化"完全可能只是恰好卡在两次真实进度更新之间的采样间隙，不能反推"没有进展"。

### 解决 / 结果

什么都没做，纯等待。容器最终变回 `healthy`，`pg_isready` 确认 accepting connections，容器内 DNS（`getent hosts qatlas-postgres`）也恢复正常（说明它和上一条 Docker DNS 故障其实是同时叠加、但彼此独立的两件事）。

### 教训

- **`docker top` 的 `Ds` + `docker stats` 的 BlockIO 计数器不变，这个组合证据本质上无法区分"真卡死"和"单次操作巨慢但仍在推进"**——两种情况在任何有限长度的观测窗口内表现完全一样。唯一能实锤的办法是等它自己给出结果（进程状态变化、日志吐出精确耗时），或者去查更底层的、真正逐次更新的指标（比如 `/proc/<pid>/io` 里的 `rchar`/`wchar` 字节数，如果能拿到真实的容器内 PID 而不是 Docker Desktop VM 里不可见的 PID）。
- **数据库承载了已知的"大表 + 慢速网络存储"组合时，checkpoint/崩溃恢复耗时 20-30 分钟应视为正常范围**，不要看到"进程 D 状态 + 计数器没变"就直接判定故障、贸然二次强杀容器——二次强杀一个正在做 fsync 的 Postgres 只会让它再崩溃一次，进入同样的恢复循环。
- 遇到"看起来卡死"的场景，先查这个存储/数据库过去是否有过"写路径慢"的已知记录（本次是靠翻另一个历史 session 的 checkpoint 记录才想起来的），比自己从零建立假设快得多。
- 观察窗口要和怀疑的"单次操作耗时量级"匹配——怀疑"卡在一次 fsync"，就该敢于等到比"最坏情况下一次 fsync 需要的时间"更长，而不是几分钟就下结论。

### 关键词

`Postgres checkpoint 卡住`、`end-of-recovery checkpoint`、`Ds 状态`、`不可中断磁盘睡眠`、`docker stats BlockIO 不变`、`iSCSI LUN`、`NAS-backed 存储`、`WAL fsync 慢`、`wsl --mount`、`崩溃恢复耗时长`、`checkpoint complete sync=727s`、`误判为死锁`、`pg_isready`、`大表 + 慢速存储 checkpoint 正常耗时`
