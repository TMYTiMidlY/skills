# Synology DSM Container Manager 已知坑

> Synology DSM 自家魔改 docker 的怪异行为。跟上游 docker / docker-compose 不一致的部分集中在这。

## DSM Container Manager: `failed to initialize logging driver: database is blocked` (短时间多次 recreate 触发)

### 症状

短时间内（5-10 min 内）对同一个项目做多次 `recreate` / `stop+start` 操作后，再次尝试启动容器报：

```
failed to initialize logging driver: database is blocked
```

容器状态卡在 stopped / 启动失败循环。**单独的 docker 命令、`docker compose ps` 等正常运行。**

### 误导路径

容易误判：
1. ❌ 以为是**自家应用**（如 RustFS / Postgres）的内部数据库 lock —— 去翻应用源码搜 "database is blocked"，0 匹配
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

> ⚠️ **绝对不要 "卸载 Container Manager"**：bind mount (在 `/volume1/docker/` 下) 安全，但 **named volume**（在 `/volume1/@docker/volumes/`，属套件管辖）**有丢的风险**。停用 → 启用 跟卸载不一样，前者绝对安全。

### 预防

短时间内**不要**做密集 recreate 操作。试探性 compose 改动建议：

1. 先把所有候选方案列全（B/D/...）
2. 一次性选定方向
3. 一次 recreate 验证

避免"改 → recreate → 看结果 → 改回 → recreate → 再改 → recreate"这种密集循环触发。

### 关键词

`failed to initialize logging driver`、`database is blocked`、`DSM Container Manager`、`Synology docker`、`json-file driver`、`SQLite WAL lock`、`短时间多次 recreate`、`/var/packages/ContainerManager`、`/volume1/@docker`、`logging driver` (docker daemon 概念,不是应用日志)、`停用启用 Container Manager`
