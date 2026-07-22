# Copilot / Claude / Codex 会话跨机迁移与备份

把一个**还能被 CLI `--resume` 续聊**的会话从一台机器搬到另一台（换 home、换 cwd、换用户名），三家各自要搬什么、改什么、哪些字段真正影响行为。核心结论:**搬的是"原生会话状态文件",不是导出的报告**——exporter 产物（`/share html`、dredge-up 报告）是有损只读、不可 resume（见本文末[归档 ≠ 迁移](#archive-vs-migrate)）。

置信度标注:🔬 = 本机隔离环境实测（独立 `COPILOT_HOME`）｜📖 = 读源码（Codex 锁 commit、Copilot 锁 bundle 版本）｜🧭 = 现场迁移经验（一次 1000+ 会话 + 数十 G 项目的实操沉淀）。

## <a id="on-disk"></a>会话在磁盘上的形态（三家对照）

| Agent | 对话正文（真相源） | 中心索引 | 每会话布局 |
|---|---|---|---|
| **Copilot** | `~/.copilot/session-state/<id>/events.jsonl` | `~/.copilot/session-store.db`（SQLite，全量列表 + FTS） | 一个**目录**:还含 `workspace.yaml`、`session.db`(todo/inbox)、`checkpoints/`、`files/`、`research/`、`rewind-snapshots/` |
| **Claude** | `~/.claude/projects/<编码cwd>/<id>.jsonl` | 无中心 db | 一个 **jsonl 文件**;目录名 = cwd 把 `/`→`-` |
| **Codex** | `~/.codex/sessions/YYYY/MM/DD/rollout-<ts>-<uuid>.jsonl` | `~/.codex/state_N.sqlite` 的 `threads` 表（**派生索引**，`rollout_path` 指回 jsonl） | 一个 **jsonl 文件**，按日期分目录 |

- 三家的 `history.jsonl` 都只是**全局输入历史**，不是对话正文:Codex `{session_id,ts,text}` 🔬、Claude `{display,project,sessionId,…}` 🔬。
- **"只有 Copilot 双写"已过时**:最新 Codex 也是 jsonl + sqlite,只不过它的 sqlite 是可重建的派生索引（`state_db: Option<StateDbHandle>` 可选;doc 原话 *"Rollout JSONL files are the durable replay format and remain readable without SQLite … The SQLite state DB, when available, is the queryable metadata index"*）📖 [thread-store/src/local/mod.rs](https://github.com/openai/codex/blob/678157acaa819d5510adfe359abb5d0392cfe461/codex-rs/thread-store/src/local/mod.rs)。本机 `~/.codex/state_5.sqlite` 的 `threads` 表 637 行 vs 磁盘 631 个 rollout 文件 🔬。

### 每行 jsonl 的形状

- **Copilot** `{id, parentId, timestamp, type, data}`,`parentId` 串事件链（`session.start` 的 `parentId=null` 为根）🔬。类型含 `session.start / user.message / assistant.message / tool.execution_start|complete / system.message`;`system.message` = 完整系统提示，**内嵌 cwd**（详见 [cwd 三处](#cwd-places)）。
- **Claude** `{uuid, parentUuid, sessionId, cwd, gitBranch, version, message:{role,content[]}}` 🔬;`parentUuid` 串消息树（`isSidechain` 标分支）;`content` parts = `text / tool_use / tool_result / thinking` 四种。
- **Codex** `{timestamp, type, payload}` 🔬;首行 `type=session_meta`,payload 自带 `cwd / cli_version / base_instructions`（旧 `instructions` 字段已移到 TurnContext，`base_instructions` = 会话基线系统提示）📖 [protocol.rs `struct SessionMeta`](https://github.com/openai/codex/blob/678157acaa819d5510adfe359abb5d0392cfe461/codex-rs/protocol/src/protocol.rs#L3070)。→ Codex 自包含度最高。

## <a id="inventory"></a>迁移集合与完整性口径

Copilot 不能只按 DB 行或只按 `session-state/` 目录枚举。设:

- **D** = `workspace.yaml.cwd` 落在待迁前缀下的 session 目录；workspace 缺失/损坏时，再从 `events.jsonl` 的 `session.start.context.cwd` 补判;
- **R** = `session-store.db.sessions.cwd` 落在待迁前缀下的 DB 行;
- **真正迁移集合 M = D ∪ R**。项目目录已经不存在也不能排除——这正是最需要保住的历史会话。

| 类别 | 磁盘状态 | 能恢复什么 | 迁移口径 |
|---|---|---|---|
| D ∩ R，且有 `events.jsonl` | 目录 + 索引 + 对话 | 完整 resume | 必迁 |
| D ∩ R，但无 `events.jsonl` | 有名字/cwd 的空壳 | 无历史对话可复原 | 用户要求“一个不漏”时也迁 |
| D - R | 仅目录 | 有可读 `workspace.yaml` + events 就能 resume；只剩 events 时要保留原件并修复元数据 | 必须由目录扫描补出 |
| R - D | 仅 DB 行 | `/chronicle` 元数据；**没有本地会话目录就不能 resume** | 作为 DB-only 记录保留，别冒充完整会话 |

一次千级现场的并集是 1163 个:1140 个有目录（688 个有 events、452 个无 events），另有 23 个 DB-only；目录集合里又有 7 个不在 DB 中 🧭。这些数值不是通用常量，价值在于说明**四类确实都会出现**，不能拿任一单源计数代替并集。

迁移前应生成一份**不可变清单**，至少含 `id / source_kind / name / cwd / created_at / updated_at / has_events / has_workspace / has_session_db`；若用户说的 “session files” 包括会话产物，再记录 `files/ / checkpoints/ / research/` 是否存在及大小。之后所有校验都按这份 ID 集合做，不拿两机“此刻总数”硬比——源/目标只要继续使用 Copilot，就会新增目录、更新 `updated_at`，总数自然漂移 🧭。

云端 `/chronicle` 行也不能代替 D:云端与本地是两套 store、ID 可不同；只有本地 `session-state/<id>/` 才是可 resume 真身（见 [云端同步副本](#cloud-sync)）。

### <a id="session-directory-copy"></a>会话目录的完整搬运

只拷 `events.jsonl` 能恢复聊天正文，但不等于“完整 session files”。用户要求完整迁移时，按**整个 `<id>/` 目录**搬:

- `workspace.yaml`:名字、cwd、git root、云端挂钩;
- `session.db`:todo/inbox;
- `files/`:粘贴内容、附件或会话产物;
- `checkpoints/`、`research/`、`vscode.metadata.json`:对应功能的状态;
- `rewind-snapshots/`:体积常最大、只服务 `/rewind`，可按明确策略排除（与 resume 无关）。

**现场取舍实例** 🧭:一次千级会话迁移中，约 2.4 GiB 的 `rewind-snapshots/` 被**有意排除**，原件继续留在源端；目标端的会话列表、对话复原、cwd auto-cd 与继续续聊均不受影响。这个结果应记成“已确认排除项”，不能在验收时算作漏传。对应取舍是:

- 只要求跨机 resume:排除即可，并在迁移清单记录 `rewind_policy=excluded`、源端位置与总量;
- 要完整取证/冷备份:可另存成归档，但不要宣称目标机 `/rewind` 可直接使用;
- 要目标机继续执行历史 `/rewind`:仅复制目录不够——快照关联旧机器的文件与绝对路径，需单独验证路径重写和恢复语义，不能跟“会话可 resume”混为一项。

若随后永久删除源端而又没有冷归档，这部分历史文件撤销能力就会永久丢失；丢的是 `/rewind` 资料，不是聊天正文。用户口头说的 “rewind history” 在当前 Copilot 磁盘布局里对应的就是 `rewind-snapshots/`。

使用 `rsync --files-from` 时要显式保证目录递归；现场曾只得到顶层/少数文件而漏子目录内容 🧭。[rsync 3.2.7 手册](https://github.com/RsyncProject/rsync/blob/v3.2.7/rsync.1.md#L2367-L2400)明确写着:该模式下 `-a` **不隐含 `-r`**。稳妥做法是额外给 `-r`，清单写 session 目录相对路径，再按上面的子项数量复核 📖:

```bash
rsync -aHr --files-from=<session-id-list> \
  <source-config>/session-state/ \
  <target-config>/session-state/
```

## <a id="who-reads-what"></a>谁读哪份数据（Copilot 的 db / yaml / 文件 mtime 分工）

Copilot 迁移最反直觉的一点:**"名字"和"时间/排序"来自不同数据源,DB 几乎不参与**。下表每格都 🔬 实测（隔离 `COPILOT_HOME` + 手搓会话让 mtime/yaml/db 打架）:

| 行为 | 文件 mtime | `workspace.yaml` | `session-store.db` |
|---|---|---|---|
| picker 显示的**名字** | — | ✅ `name` 字段 | ❌ 表里根本没有 `name` 列（只有 `summary`） |
| picker 显示的**时间** | ✅ | ❌（不读 `updated_at`） | ❌ |
| picker 排序 / `--continue` 选谁 | ✅ | ❌ | ❌ |
| `pruneOldSessions` 判"陈旧" | ✅ | 仅 `includeNamed` 时读来做保护 | ❌ |
| `--resume=<id>` 能否续 | — | ✅（扫目录 + 读 workspace） | ❌ |
| `resume-auto-cd` 用的 cwd | — | ✅ `cwd` 字段 | ❌ |
| `/chronicle` 搜索及其时间 | ❌ | ❌ | ✅ **唯一吃 DB 的地方** |

**一句话:除了 `/chronicle`,Copilot 会话的"时间/排序/陈旧判定"全看文件 mtime,DB 和 yaml 的时间字段都不参与;`workspace.yaml` 只管名字和 cwd,`session-store.db` 只管 `/chronicle`。**

- **rename 存在哪**:用户 rename 会话时,名字写进 `workspace.yaml` 的 `name:`(+ `user_named: true`),**同时**在 DB 的 `summary` 列复制一份 🔬。但 picker 显示的是 `workspace.yaml` 的 `name`——手搓一个**没有任何 DB 行**的会话,picker 照样显示 workspace.yaml 里的名字 🔬。→ 想让迁移过去的 rename 在 picker 里正常显示,**必须搬 `workspace.yaml`**;只搬 DB 行没用（DB 连 `name` 列都没有）。
- **`session-store.db sessions` 表结构** 🔬:`id, cwd, repository, host_type, branch, summary, created_at, updated_at`（+ `search_index` fts5 虚表做全文搜索）。

## <a id="resume-resolution"></a>resume 的解析机制

**Copilot:目录驱动,不查 sqlite** 📖🔬。`--resume=<id>` 的解析器扫 `session-state/` 目录、逐个读 `workspace.yaml`,按 `id / mc_task_id / 前缀 / 名字` 匹配（bundle 里 `hgr` 用 `ps.directoryFilesWithMetadata()` 列目录 + `loadWorkspace()`;`findSessionByPrefix` 先查文件元数据再 `S.sessionFindByPrefix(home,…)`)。DB 行**不是** resume 的前提——手搓"只有目录、无 DB 行"的会话,`--resume=<id>` 成功续上并从 events.jsonl 完整复原对话 🔬。DB 行是 **resume 之后**才回填的,且回填的 `created_at` = **resume 时刻**（非原始）、`cwd` 可能为空 🔬。

**Codex:sqlite 可选,能扫文件名兜底** 📖。`read_thread` 先查 sqlite 元数据,查不到就 `resolve_rollout_path` → `find_rollout_path_by_id_from_filenames`——**递归扫 `sessions/` 目录树、按文件名里的 UUID 匹配**,无需 sqlite [read_thread.rs](https://github.com/openai/codex/blob/678157acaa819d5510adfe359abb5d0392cfe461/codex-rs/thread-store/src/local/read_thread.rs) / [list.rs `find_rollout_path_by_id_from_filenames`](https://github.com/openai/codex/blob/678157acaa819d5510adfe359abb5d0392cfe461/codex-rs/rollout/src/list.rs#L1493)。→ 迁移 Codex 会话只需把 rollout jsonl 丢进 `~/.codex/sessions/` 下（任意子目录,扫描会递归）,`codex resume <uuid>` 即能找到,sqlite 行随后回填。

**resume flag 三家** 🔬:`copilot -r/--resume[=value]`（+ `--continue` 续最近、`--session-id`）｜`claude -r/--resume [value]`（+ `-c/--continue`）｜`codex resume [--last]`（+ `codex fork`）📖 [cli/src/main.rs](https://github.com/openai/codex/blob/678157acaa819d5510adfe359abb5d0392cfe461/codex-rs/cli/src/main.rs#L180)。

## <a id="cwd-places"></a>cwd 迁移（Copilot）

同一个 cwd 藏在**三处**,迁移换目录时都要按前缀改写 🔬:

1. `workspace.yaml` 的 `cwd:` —— **唯一功能必需的一处**,`resume-auto-cd` 只读它。
2. `events.jsonl` 里 `session.start` 的 `data.context.cwd`,以及 `system.message` 正文里内嵌的 cwd —— 改这处是为了让复活的 agent 看到的**自身历史**一致（不至于以为还在旧路径）。
3. `session-store.db` 的 `sessions.cwd` 列 —— 给 `/chronicle` 和 picker 的 location 列显示用。

> ⚠️ `system.message` 里除 cwd 外还可能内嵌**会话目录绝对路径**（如旧 home 下的 `…/session-state/<id>/plan.md`），那不是 cwd、不在"三处"内,但也会残留旧 home 前缀,按需一并替换 🔬。

`workspace.yaml` 还有一个相邻的功能字段 `git_root:`，项目树随 cwd 一起换前缀时也要改；否则 cwd 已落在新机、Git 上下文却仍指旧机。`mc_task_id / mc_session_id / mc_last_event_id` 不属于路径字段，不应被 cwd 替换顺手改掉（它们的连带语义见 [云端同步副本](#cloud-sync)）。

**不要对整个 session 目录做“旧 home → 新 home”的无脑全文替换** 🧭。旧路径还会合法地出现在:

- `workspace.yaml.name`（例如首条消息形成的粘贴引用，本身就是会话名的一部分）;
- `events.jsonl` 的用户/助手消息、工具参数与工具输出（历史事实）;
- `session.db` 的 todo/inbox 文本;
- `files/` 里的粘贴正文。

这些文本保留旧路径才是忠实历史；改掉反而是篡改记录。迁移校验应解析并检查**功能字段**（`workspace.cwd/git_root`、`session.start.context.cwd`、已知 system context 路径、DB `sessions.cwd`），不能用 `grep -rl '<旧home>' session-state/` 必须等于 0 作为成功标准。一次迁移后的残留实测主要就是历史正文、todo 与名字，而功能 cwd 已全部正确 🧭。

**`resume-auto-cd` 行为** 📖🔬:resume 时若持久化 cwd 存在且是目录 → 自动 `cd` 进去;若缺失 → 打印 `warning: resume-auto-cd: ignoring persisted cwd '<path>': missing or not a directory`（或 `: not an absolute path`）,回退到启动目录,**能续、不致命**。对策二选一:在新机 `mkdir` 出那个 cwd,或按上表改写三处 cwd。环境变量 `COPILOT_DISABLE_RESUME_AUTO_CD=1`（或 `true`）可整体关掉;headless/`-p`/`--server`/`--acp` 模式本就跳过 auto-cd。

## <a id="mtime-prune"></a>时间、排序、mtime 与清理

- **文件 mtime 决定一切"时间/排序/陈旧"**（picker 时间列、picker 排序、`--continue` 选最新、prune 判陈旧）🔬。`touch -d` 改 mtime,picker 时间立刻跟着变;让 `workspace.yaml.updated_at` 或 DB `updated_at` 与 mtime 冲突,`--continue` 仍按 mtime 选、二者都翻不了盘 🔬。
- **`pruneOldSessions` 按文件 mtime 判陈旧、删整个会话目录** 📖:`cutoff = now − olderThanDays×24h`,`listSessions().filter(f => f.modifiedTime <= cutoff)`,`modifiedTime` 即文件 mtime。全 bundle 里这条可读 JS 路径只由 `scope:"server"` 的 RPC `sessions.pruneOld` 暴露（`olderThanDays` 由调用方传入),没有开机/定时触发器,也没有 retention 设置项 🔬;默认 `includeNamed:false` → 走**这条 RPC**时有名字的会话受保护。这个结论只约束可读到的 JS RPC，**不能证明不存在原生层、云端对账或本机外部程序触发的其它删除路径**。
- **另有一次未归因的目录消失实测** 🔬:一个带名字/summary、用 `cp -p` 搬入且保留旧 mtime 的会话，成功 resume 后在 Copilot 长时间空转约一小时期间从 `session-state/` 消失，DB 行仍在；三个隔离变体单次启动都存活，故不是简单的“每次启动 prune”。用户自建 restic 备份脚本与已知 timer 已排除，可读 JS 也解释不了，具体机制仍**不确定**（可能在不可读原生路径、云端同步对账或当时未发现的外部清理者）。→ 不要拿“named 受 JS RPC 保护”当保险；迁移先留不可变备份，live 副本用新 mtime 做存活观察，再按展示需求回设原始 mtime。
- **⚠️ `cp -p` 是雷** 🧭:`cp -p`/`rsync -a` 保留旧 mtime,会让迁移来的会话 ① `--continue` 够不到、② picker 显示成"很久以前"、③ 一旦有人跑会话清理就可能被删。→ 迁移后把 mtime 设成"现在"（防清理、但 picker 时间显示成刚才）**或**设成原始 `updated_at`（picker 时间真实、但离清理 cutoff 更近）,二选一,别留 `cp -p` 的旧 mtime。
- **创建时间(btime)改不回** 📖:Linux 用户态只能改 atime/mtime（`utimensat`),没有 syscall 改 btime;唯一歪招是 root `debugfs -w -R 'set_inode_field <inode> crtime …'` 直接改块设备 inode（要 root、挂载盘上有风险、逐 inode 改,大批量不现实）。会话真正的创建时间不丢——在 `workspace.yaml.created_at` 和 DB `created_at` 里。picker 显示的"创建时间"是**文件 mtime**、不是 btime,所以 `stat` 看到的 Birth 是复制时刻纯属系统限制的展示层，不影响使用。
- **DB `created_at` 只对 `/chronicle` 有意义**,且 resume 自动回填时写的是 **resume 时刻**而非原始值 🔬 → 想让 `/chronicle` 里时间准,迁移时要**手动**把源 DB 行的原始 `created_at` 写进目标 DB（见下[迁移步骤](#copilot-steps)第 6 步）。

### <a id="time-manifest"></a>迁移清单与时间索引

btime 不可回写、目标机 resume 又会继续改变 mtime/`updated_at`，所以删源前最好另存一份**切换时刻快照** 🧭:

- JSON 给机器核对与后续修复;
- TSV/CSV 给人直接排序查看;
- 每行至少留 `id / name / cwd / created_at / updated_at / has_events / source_kind`。

它不是第三份会话正文，只是校验与审计索引；正文仍以原生 session 目录为准。索引必须在首次目标 resume **之前**生成，之后目标 DB 时间变新是正常使用痕迹，不能再拿它反推源端原值。现场用这个索引同时解决了“stat Birth 是复制时间”“DB-only 没目录可设 mtime”“抽验 resume 改了少数会话时间”三类歧义 🧭。

## <a id="cloud-sync"></a>云端同步副本（`mc_*` 字段与删除的远端连带）

Copilot 会话除本地那套（目录 + `session-store.db`）外，**带 `mc_*` 的会话还可能**在 GitHub 云端有一份同步副本（内部叫 MC / mission-control task）；不是每个本地会话都有。它是**独立的第二份数据、session ID 与本地的不同**——本地 `~/.copilot/session-state/<id>/` 才是真正能 resume 的那份,云端副本供 github.com / 手机端查看。`/chronicle` 搜索是**云端 + 本地两套合并**的（那套搜索、以及"给 resume 用哪个 ID"的取舍见同目录 [copilot-cli.md](copilot-cli.md) 的 `/chronicle` 一节,不在这里重复）。

**两份的挂钩落在 `workspace.yaml`** 🧭:

```yaml
remote_steerable: false      # 能否从网页/手机远程操控（/remote 开关）；与"有没有云端副本"是两码事
mc_task_id: <mc-task-id>       # 云端 task ID —— 删云端时 deleteTask 用它
mc_session_id: <mc-session-id> # 云端 session ID
mc_last_event_id: <event-id>   # 已同步到的最后一个事件
```

**`/session delete` 分"只删本地"与"连云端一起删"**（Copilot bundle 1.0.72-1）📖:参数解析认 `--yes` / `--remote` / `--local-only` 三个 flag（`Mrr(e,new Set(["yes","remote","local-only"]))`）。

| 写法 | 本地目录 + DB 行 | 云端同步副本 |
|---|---|---|
| `--local-only` | 删 | **保留** |
| `--remote` | 删 | **删**（调 `deleteTask(mcTaskId)`,失败报 *"Failed to delete remote session"*） |

对有同步数据的会话交互删时会**弹菜单二选一**（提示 *"…delete the synced session data?"*）:`Delete local only` → `--local-only`;`Delete local and synced data` → `--remote`。所以默认不会偷偷删云端——要么显式传 `--remote`,要么菜单里选 "local and synced"。远端删除还需要当前登录态能调用云端 `deleteTask`；失败会明确报错，不会伪装成本地与云端都删成功 📖。

> ⚠️ **迁移把云端挂钩一起搬过来了,`--remote` 删会连累源机**:rsync `workspace.yaml` 是**逐字**搬的,`mc_task_id` / `mc_session_id` 跟着过来（cwd 改写只动 `cwd/git_root`、不碰 `mc_*`）。于是**源机本地副本 + 目标机本地副本从此指向同一个云端 task**（同一 GitHub 账号;实测两机的 `mc_task_id` 逐字相同 🧭）。连带后果:
> - 在**目标机**对这些会话 `--remote` 删 → 把那份**共享的云端 task 一起删了** → github.com / 手机端看到的没了,且**源机**本地副本的 `mc_task_id` 变悬空引用（源机本地 resume 仍能用,只是云端链接死了）。
> - 只想清目标机本地、别动云端和源机 → 用 `--local-only`（或菜单选 "Delete local only"）。
> - 带 `mc_task_id` 的会话占比可观（实测某批 1155 个 workspace.yaml 里 737 个带 🧭）——**批量删除脚本务必 `--local-only`**,别一把 `--remote` 连累云端。
> - 目标机 resume 时 bundle 打 *"Exporter: reattaching to existing session <mcSessionId>"* 📖,即续聊可能重新挂上**同一个**云端 session;是否真把新事件推到云端未独立验证（待验证），但足见"云端那份不是只读快照、会被新机续聊影响"。

## <a id="copilot-home"></a>重定向配置目录（`COPILOT_HOME` / `--config-dir`）

Copilot 的配置目录解析优先级 = `--config-dir`（隐藏、标 deprecated）→ `COPILOT_HOME` → `~/.copilot` 📖;`session-state/` 和 `session-store.db` 都在解析出的这个目录下 🔬。用途:

- **隔离测试不污染真环境** 🔬:`COPILOT_HOME=/tmp/iso copilot --resume` 只看 `/tmp/iso` 下的会话,真 `~/.copilot` 不受影响。做迁移前的小样验证、或本文里这些实测,都靠它。
- 迁移时若不想写进真 `~/.copilot`,可把整套会话放进另一个目录并用 `COPILOT_HOME` 指过去。

`COPILOT_HOME` 只改 **Copilot 配置根目录**，不改操作系统的 `$HOME`、进程 cwd、项目路径，也不会自动重写 `workspace.yaml`/events 里的旧用户名。它适合隔离验证，不是跨机路径映射的替代品 🔬。

## <a id="project-boundary"></a>项目树与会话状态的边界

项目文件和会话历史是两套独立数据:

| 对象 | 典型位置 | 删除另一方会怎样 |
|---|---|---|
| 项目树 | `<workspace-root>/…` | 删项目**不会**删 `~/.copilot` 会话；旧会话仍能 resume，只是 cwd 缺失时回退启动目录 |
| 本地会话 | `<copilot-home>/session-state/<id>/` + 中心索引 | 删会话**不会**删项目 checkout |
| 云端副本 | GitHub MC task | 只与 `mc_*` 挂钩；项目树是否存在不影响它 |

所以“项目已进回收站/已永久清空”不能推出“会话也不在了” 🧭。反过来，清理会话也不会释放项目树占用。迁移和清理都要把这三类对象分开列范围。

### <a id="project-cutover"></a>项目树的切换窗口

大项目适合“两阶段”搬运 🧭:

1. **传前勘定**:确认最终目标主机/用户/路径/挂载卷，检查可用空间要覆盖项目 + session + 增量余量 + 回收站占用；空间放不下“源 tar + 解包后副本”两份时，直接流式 rsync，别先落整包。
2. **在线首轮**:服务仍运行时先搬绝大多数数据，缩短停机窗口。
3. **静默尾轮**:停掉 watcher、文档服务、开发服务器和仍在写项目的 Copilot/编辑器，再跑增量 rsync。
4. **干跑验收**:`rsync -n` 应无待同步项；若只剩某个生成文件 mtime 持续变化，先找写入进程，别把它误判成传输丢文件。
5. **最后修链接**:所有 rsync 完成后再改绝对软链，否则下一轮 `-a` 会把目标改动覆盖回源样子。

长传的可恢复模板（变量替换成实际路径/主机）:

```bash
SRC='<source-dir>/'
DST='<user>@<target-host>:<target-dir>/'
ok=0
for attempt in $(seq 1 40); do
  if rsync -aH --partial --timeout=300 \
      -e 'ssh -o ServerAliveInterval=30 -o ServerAliveCountMax=6' \
      "$SRC" "$DST"; then
    ok=1
    break
  fi
  sleep 15
done
test "$ok" -eq 1
```

`-H` 用来保硬链接；若“完整”还包含 ACL/xattr，应按源文件系统与权限条件另加对应 rsync 选项，不能把 `-aH` 口头等同于所有文件系统元数据。目标 home 或挂载卷在传输中途变更时，之前的空间判断、软链修复与完整性结论全部作废:先确认新 home 与旧 home 的差集，再从源跑一次完整增量和干跑验收 🧭。

### <a id="symlink-classes"></a>软链接分类

| 链接目标 | 处理 |
|---|---|
| 旧**项目前缀**内的绝对链接 | 精确替换成新项目前缀 |
| 旧 home 里项目前缀之外的绝对链接 | 先保持原样并列为外部依赖；venv/uv Python 这类通常应重建环境，而不是猜新缓存路径 |
| 相对链接且源端已经悬空 | 记为源端基线；不是迁移回归，可按项目需要另行清理 |
| 目标机新出现的悬空链接 | 迁移回归；回查是否过宽替换或漏搬目标 |

验收时同时记录“源端断链基线”和“目标端断链”，不能只看目标数量。现场一次把整个旧 home 过宽替换后，断链数从 9 涨到 78；收窄到项目前缀后才恢复基线 🧭。

## <a id="copilot-steps"></a>迁移一个 Copilot 会话（目标产物）

一次正确迁移完成后,目标机应达到的状态 + 达成它的典型手段:

1. **枚举定范围**:源机用 `session-store.db` 按 `cwd LIKE '<旧前缀>%'` 查,再扫所有 `workspace.yaml` 的 cwd 取并集（补上"有目录无 DB 行 / 有 DB 行无目录"）。
2. **定 cwd 映射**（`<旧home>/<旧cwd前缀>` → `<新home>/<新cwd前缀>`）并与用户确认。
3. **小样验证**（1~2 个会话,隔离 `COPILOT_HOME`):传输 → 改 cwd → 填 DB 行 → resume 实测。判据:bogus-id 报 `No session, task, or name matched`、真 id 能进（报 auth 或真复述）= 会话解析成功。
4. **传输整目录**（不是单文件):`rsync -aHr --files-from=<id列表> <源>/session-state/ <目标>:/…/session-state/`;可 `--exclude rewind-snapshots` 瘦身（这里的显式 `-r` 不能省，见 [会话目录的完整搬运](#session-directory-copy)）。
5. **改写 cwd 三处**（见 [cwd 三处](#cwd-places)):`workspace.yaml` 的 `cwd:` + `events.jsonl` 的 `session.start.context.cwd`（含 `system.message` 内嵌）全部前缀替换。
6. **合并 DB 行**:把源 DB 的行 `INSERT OR REPLACE` 进目标 `session-store.db`（cwd 改写、**保留原始 `summary/created_at/updated_at`**，否则 `/chronicle` 里时间/名字丢）。
7. **设 mtime**（见 [mtime 与清理](#mtime-prune)):设成"现在"防清理,或设成原始 `updated_at` 让显示真实——二选一,别留 `cp -p` 旧值。
8. **验证**:真 id resume 能解析、picker 里名字/时间对、数量对得上。
9. **最后才删源**:确认目标是完整副本（`rsync -n` 干跑 0 差异）+ 留备份 + 用回收站删（可恢复）。

**DB 合并边界** 🧭:目标机通常已有自己的会话，不能拿源 `session-store.db` 整文件覆盖。用一个一致读取事务导出 M 中的选定行，再在目标用单事务合并（保留目标无关行、设置合理 `busy_timeout`）；源/目标若仍有 Copilot 进程写库，先退出或在最终切换时再导一次。`INSERT OR REPLACE` 前还要列出 ID 冲突——同 ID 通常是此前小样迁过的同一会话，但应核对而不是默认覆盖。

## <a id="verification"></a>迁移验收矩阵

“能看到一个会话”只证明解析器找到目录，不等于全量迁移完成。至少做六层校验:

| 层 | 判据 |
|---|---|
| 集合 | 目标覆盖清单 M 的全部 ID；分别核对完整、空壳、dir-only、DB-only，不能只报总数 |
| 目录 | `events.jsonl/workspace.yaml/session.db/files/checkpoints/research` 的存在数与源清单相符；明确记录被排除的 rewind |
| 元数据 | 名字、`user_named`、created/updated 原值、DB 行都在；目标原有会话未被覆盖 |
| 路径 | `workspace.cwd/git_root`、`session.start.context.cwd`、DB cwd 指向新前缀；历史正文出现旧路径不算失败 |
| 行为 | 至少抽验:有对话且 cwd 存在、cwd 已缺失、用户命名、带会话 files 的会话；让 agent 复述一条已知事实并检查实际 cwd |
| 环境 | resume 后实际跑一次工具；hook、Node/Python、Git、权限缺失会造成“记忆正常但工具不可用”，这不是会话正文丢失 |

登录前也能做解析冒烟:bogus ID 报 “No session/task/name matched”，真 ID 走到鉴权错误，说明目录解析成功；登录后再做真实复述，不能把“鉴权错误不同”当最终验收 🔬。目标开始使用后，总目录数、mtime 与 `updated_at` 会增长；后续审计应拿切换清单按 ID 对照，而不是拿今天的总数与迁移日总数比较 🧭。

项目树另做 `rsync -n`/文件数/体积/硬链接/软链接基线；对可疑单文件再用 checksum。会话数据与项目树两边都过关，才进入删源阶段。

## <a id="resume-history-visibility"></a>resume 后的历史可见性（落盘、内存、TUI、模型上下文）

resume 后终端“只看到一点历史”不等于迁移丢数据。至少分清四层:

| 层 | 真正回答的问题 | 判据 |
|---|---|---|
| `events.jsonl` 落盘事件链 | 原始会话事实还在不在 | JSON 全可解析、首条 `session.start`、ID 唯一、单根、所有 `parentId` 可解析、时间范围覆盖源会话 |
| resume 后内存 events/timeline | CLI 有没有读进来 | 新追加的 `session.resume.data.eventCount / eventsFileSizeBytes` 与 resume 前文件数量/大小相符 |
| TUI 终端渲染 | 屏幕能向上看到多少 | 受过滤、折叠、终端宽度换行和硬行数上限影响 |
| 模型上下文 | agent 当前真正能引用多少旧内容 | 受 context window、resume 重建策略、compaction/summary 影响；与 TUI、落盘文件都不是一回事 |

### TUI 的渲染行上限

Copilot CLI 1.0.73 的终端 renderer 里 `uZe=5e3`；`cZe(...)` 渲染完 timeline 后若超过 5000 行，就对 `lines / softWrapRows / contentSpans` 一起从开头 `slice(I)`，并把省略量记为 `droppedFromStart` 📖。这是**渲染行**而非 event 数:Markdown、工具输出和窄终端换行都会迅速吃完 5000 行，所以数 MB 的长会话 resume 后通常只显示尾段。

`Ctrl+O` 的官方快捷键说明是 `toggle all timeline`:它切换 timeline 类型/折叠可见性，但不会取消 `cZe` 的 5000 行上限 📖。PageUp 也无法找回已经从当前 render buffer 开头切掉的行。

想看全历史有两条不受 TUI 行数限制的路:

- `/share html` 从 `session.getTimelineEntries()` 取完整内存 timeline，再交给 HTML exporter，不走终端 5000 行 renderer;
- 离线直接把 `events.jsonl` 映射成 text/HTML；同时输出 entry 类型计数，作为迁移验收附件。

### 派生索引与对话正文

目标 `session-store.db` 只合并 `sessions` 元数据行时，`turns / search_index / checkpoints / session_files` 等派生表可能是 0。结果是 `/chronicle` 全文搜索不完整，但 `--resume` 仍从 session 目录 + `workspace.yaml` + `events.jsonl` 复原对话。**DB 搜不到、TUI 看不到、模型一时想不起、events 真缺失**是四种不同故障，不能互相替代诊断。

一次现场实测 🧭:一个 6.70 MB 长会话有 2241 条合法事件（单根、0 重复 ID、0 断链、无 compaction/truncate），最新 resume 自报先读入 2237 条既有 events；离线映射得到 828 条 timeline entries（含 23 条真人消息、99 条助手正文、108 条 reasoning、594 条工具事件），但 TUI 只能看到末段。这个组合应判定为**落盘完整 + 内存完整 + 终端截尾**，不是迁移损坏。

### 快速判定顺序

1. 先复制一份当前 session 目录作只读快照，防后续 resume 继续追加。
2. 查 events 的首尾时间、type 计数、JSON 错行、ID/parent 链、compaction/truncate 事件。
3. 对比每次 `session.resume` 自报的 `eventCount` 与实际行数；resume 事件本身会让行数继续增加，差几个尾部 warning/shutdown 属正常。
4. 离线渲染全部 entries，核对首条/末条真人消息；真人消息很少但 agent 工具事件很多时，TUI 的“对话看起来短”也可能只是会话本来就高度自动化。
5. 最后才查 TUI 过滤/5000 行上限、中央派生索引和模型 context；不要一看到屏幕短就从备份覆盖目标 events。

## <a id="cleanup-scope"></a>删除与回收站的作用域

| 动作 | 项目树 | 本地 session 目录/索引 | 云端副本 | 备注 |
|---|---|---|---|---|
| `trash-put <workspace-root>` | 移入回收站 | 不动 | 不动 | 同卷通常是 rename；未清回收站前不释放空间 |
| `/session delete <id> --local-only` | 不动 | 删除 | 保留 | 多机迁移后清某一台本地副本的安全选项 |
| 手工只 trash `session-state/<id>` | 不动 | 只删目录、可能留下 DB 残项 | 不动 | 不如原生命令一致，除非正在做修复 |
| `/session delete <id> --remote` | 不动 | 删除 | 删除共享 task | 会影响所有仍指向同一 `mc_task_id` 的设备 |
| `trash-rm <trash-item>` | 只影响已在 trash 的指定项 | 取决于该项是什么 | 不动 | 永久删除、不可恢复；不会“顺便”扫描其它目录 |

删源的稳妥顺序是:保留源 session 原件 → 目标通过 [验收矩阵](#verification) → 停写入者并做静默尾轮 → 项目树与会话分别确认作用域 → 先回收站、观察一段时间 → 再决定是否永久清除。若移除了源机 user service，先备份 unit；若为直连 rsync 临时加过 SSH key，迁移完成后移除 🧭。

### <a id="source-session-purge"></a>已迁源会话的彻底删除

一次可审计、可中断的删除应分成 **quarantine → trash-put → 独立只读核验 → trash-rm** 四层，而不是直接对 `session-state/*` 批量永久删除 🧭:

1. **冻结删除集合**:重新扫描源端 D ∪ R，与迁移时不可变 manifest 取交集；manifest 之后新建的源会话留在源端。目标每个交集 ID 必须再次通过目录/DB/关键文件核验，有缺口先补传。
2. **静默源端写入**:找出待删 ID 的活跃 Copilot 进程并按精确 PID 停止。不能只看命令行 `--resume`:从 picker 进入的进程没有这个 flag，可从 `/proc/<pid>/fd` 打开的 `session-state/<id>/session.db` 反查。进程退出还可能最后 flush 文件，停完后必须重扫集合和目录数。
3. **分清“可归因目录”与“物理目录”**:有些 DB-only 会话仍留一个只含 `vscode.metadata.json` 的微型目录，既没有 workspace 也没有 events，按 cwd 枚举看不见。删除与验收时应按冻结 ID 逐个 `isdir(session-state/<id>)` 再数一次，不能沿用 D 的目录数。
4. **建立同卷 quarantine**:在 `~/.copilot` 下建一个唯一命名容器；用 SQLite Online Backup API 保存整个删除前中心 DB，并放入 deletion plan、迁移 manifest、受影响行计数、逐目录 move log。把冻结 ID 对应的物理目录用同卷 rename 原子移进容器——不复制数 GiB 数据，也不碰其它 session。
5. **先 `trash-put` 容器**:只产生一对 `Trash/files/<name>` + `Trash/info/<name>.trashinfo`，恢复与永久清除都能以一个精确对象完成。确认 `.trashinfo` 解码后的 `Path=` 等于 quarantine 原绝对路径。
6. **事务清中心索引**:目录进入回收站后，在 live DB 里按 ID 删除所有带 `session_id` 的业务表，再删 `sessions.id`；不能只删 `sessions`。当前实测 schema 涉及 `turns / search_index / assistant_usage_events / checkpoints / forge_trajectory_events / session_files / session_refs / sessions`。目标机和云端不执行任何 delete API。
7. **第二套只读核验**:由独立审阅者从原始 plan 重算:目标副本完整、源目录为 0、上述所有 DB 表匹配行为 0、quarantine 内目录数/备份 DB/manifest/receipt 配齐、保留 ID 仍在、trashinfo 只命中一个对象。任何一项不符都停在 trash，先恢复或修复。
8. **精确永久清除**:只有核验明确 GO 后才运行 `trash-rm '<quarantine原绝对路径>'`。pattern 以 `/` 开头时匹配 trashinfo 中的**完整原路径**，比 basename 通配安全；随后确认 `files/` 与 `.trashinfo` 两半都消失。不要用 `trash-empty` 代替——它会清整个回收站。

一次现场结果 🧭:迁移 manifest 1164 个 ID，源端候选 1167 个，交集 1163 个；4 个切换后新增源会话被保留，1 个 manifest ID 在源端已无内容。删除前补齐了 1 个缺失目标目录、3 个元数据文件和 2 个仅含元数据的微型目录；最终 1163 个 ID = 1140 个物理目录 + 23 个纯 DB-only。单一 quarantine 约 5.67 GB，包含未迁移的 rewind 与完整 DB 备份；中心库共删除 `sessions 1163 / turns 9185 / search_index 11065 / usage 6225 / checkpoints 318 / trajectory 294 / session_files 1735 / session_refs 352` 行。永久清除 quarantine 后，源端 rewind 与这份恢复备份都不可逆消失，但目标会话正文、项目树和云端副本不受影响。

该现场由第二套只读核验明确给出 GO 后，才对 quarantine 原绝对路径执行 `trash-rm`；随后 `Trash/files` 与 `Trash/info` 两半均不存在，4 个保留 ID 仍各有目录 + DB 行，目标 manifest 的 1164 行 DB 全在、688 个对话 events 全在。这个末次核验比“命令退出码 0”更重要——永久删除成功和未误伤要分别证明 🧭。

### <a id="temporary-ssh-key-cleanup"></a>临时 SSH 公钥的收尾

迁移 key 应在 `authorized_keys` 行尾带唯一用途 marker。收尾时按 marker **恰好匹配一行**、写临时文件、校验总行数只减一、继承原权限后原子替换，再核 marker 为 0，并从源端用指定私钥复测。

复测仍能登录不一定代表删除失败:同一公钥指纹可能在迁移前就已有一条未标记授权。此时 marker 行已经删除，保留的是预存权限；不要为了“必须连不上”顺手删掉未标记的同指纹行。是否撤销设备的全部访问权是另一项授权，应单独决定 🧭。

## <a id="claude-codex-migrate"></a>Claude / Codex 迁移

单文件 jsonl,比 Copilot 好搬,但坑一样:

- **Claude**:拷 `<id>.jsonl` 到新机 `~/.claude/projects/<新编码cwd>/`。**目录名必须匹配新机 cwd 的编码**（`/`→`-`;实测 `/home/<u>/projects` → `-home-<u>-projects` 🔬,大小写与已有连字符原样保留;点/下划线等特殊字符是否也转 `-` 属已知坑,按目标实际路径核一下）。无中心 db,不用管索引。每行内嵌 `cwd/gitBranch`,同样有"记得聊过啥、一动手找不到文件"的陷阱。
- **Codex**:拷 `rollout-<ts>-<uuid>.jsonl` 到新机 `~/.codex/sessions/` 下任意子目录（`codex resume <uuid>` 递归扫文件名找,sqlite 行随后回填,见 [resume 解析](#resume-resolution)）。自包含度最高（`session_meta` 自带 `base_instructions + cwd`）。首行 `session_meta.cwd` 内嵌旧路径,跨机同样要留意。

## <a id="pitfalls"></a>踩坑清单（迁移现场，🧭 除非另标）

- **搬错粒度**:Copilot = 目录 + 中心 DB 行;Claude/Codex 的对话正文 = 单 jsonl（Codex 另有派生 sqlite 索引）。
- **cwd 只改一处**:三处不一致会残留、resume 报警——全改。
- **cwd 目录新机不存在**:resume 打 `ignoring persisted cwd … missing` 回退启动目录,`mkdir` 那目录后就自动 cd 进去 🔬。
- **以为要填 DB 行才有名字/时间**:❌ 不需要——`--resume` picker 目录驱动,名字来自 `workspace.yaml`、时间来自文件 mtime,无 DB 行照样显示 🔬。DB 行只为 `/chronicle`。
- **`cp -p` / `rsync -a` 带旧 mtime**:见 [mtime 与清理](#mtime-prune),`--continue` 够不到、picker 显示上古、清理时可能被删。
- **`rsync --files-from` 不递归**:`rewind-snapshots/` 等子目录内容不在清单里就不会过去;传完核对 `events.jsonl` 数量,别以为 rsync "都传了"。（`rewind-snapshots` 是 `/rewind` 的整文件备份、内含旧绝对路径、跨机无用、与 resume 无关,通常**可不搬**。）
- **符号链接两连坑**:(a) 绝对软链指向旧 home 会断,按前缀重指,但**只改目标前缀那段**,别把 `<旧home>/.local/...`（venv 的 uv-python 等）也一起改;(b) 后续再跑 rsync 会把改好的软链按源覆盖回去——**软链修复放在所有 rsync 之后**。
- **两机之间没免密**:直连 rsync 前先把公钥加进对方 `authorized_keys`;经跳板/中转工具时注意它可能只支持 client↔远端、不支持远端↔远端（否则大文件要过本机两趟）。
- **长传会断**:SSH 掉线致 rsync 卡死 → 重试循环 + `ServerAliveInterval` + `--timeout` + `--partial` 自愈续传。
- **目标机没登录**:resume 能解析,但要 `/login` 后才能真跑 🔬。
- **hook 跟着搬**:项目里 `.github/hooks/…` 引用的工具新机没装 → preToolUse fail-closed 禁掉 bash,对话/记忆正常但跑不了命令;需在新机装依赖或临时禁 hook。
- **用裸 SSH 误判 Node/npx 缺失**:NVM 常写在 `.bashrc` 的“仅交互 shell”分支后，`ssh host 'command -v node'` 与 login 非交互 shell都会报 missing，但人在交互终端启动的 Copilot 实际继承完整 NVM PATH。应在与 Copilot 相同的交互上下文跑 `node --version / npx --version`，并把 hook 的**原命令 + 输入**真执行一次；一次现场中裸 SSH 报缺失，而交互环境为 Node 26 + npx 11，原 safety-net hook 命令 exit 0 🧭。
- **`trash-put` 跨卷失败**:回收站按 FreeDesktop 规范需与被删文件**同卷**;`/tmp`(tmpfs) 或独立卷上的文件删不进 home 卷的回收站,非 root 又无权在别处建回收站。同卷才能 trash;`trash-put` 同卷只是 rename、不清空回收站不真正释放空间。
- **家目录换到独立卷 / 搬成 `home.old`**:挂载点变化连带影响空间、trash、软链——搬前先 `df` 看清卷布局。
- **源上有活跃写入进程**:如文档服务在持续重生成文件(mtime 一直变),删源前必须先停;子进程脱离 systemd cgroup 成孤儿时 `systemctl stop` 杀不掉,得 `kill <PID>` 补刀。
- **删会话时误连累云端**:迁移逐字搬 `workspace.yaml` 把 `mc_task_id` 带了过来,源/目标本地副本从此共享**同一个**云端 task;在目标机 `/session delete --remote` 会连那份共享云端副本一起删。只清本地用 `--local-only`（批量删尤其注意）——详见 [云端同步副本](#cloud-sync)。
- **把旧路径全文 grep 当失败**:名字、历史消息、工具输出、todo 本来就会提旧路径；只校验功能字段，别为了“0 残留”篡改历史。
- **把项目删除当成会话删除**:项目树与 `~/.copilot` 独立；项目进 trash 后源会话仍在，resume 只是 cwd 缺失。`trash-rm` 也只永久清掉已经在回收站里的那一项。
- **直接覆盖目标中心 DB**:会吞掉目标机原有会话，活跃写入时还可能拿到不一致副本；只合并迁移集合的行。
- **拿迁移后的动态总数对账**:目标 resume/新建、源继续使用都会让数量和时间漂移；按切换清单的 ID 集合验。
- **把 TUI 尾段当成历史丢失**:长会话会被终端 5000 渲染行上限截掉开头；先按 [历史可见性](#resume-history-visibility) 验 events 链和 resume 自报数量，再判断是否需要恢复。
- **误把 `COPILOT_HOME` 当路径重写**:它只换配置根，不会改 cwd、git root 或项目 checkout。
- **清源前只停 unit、不查进程**:livereload/开发服务器子进程可能已脱离 service cgroup；停 unit 后还要查相关进程和监听端口。移除服务前先备份 unit，跨机临时 SSH 公钥用完也应移除。

## <a id="archive-vs-migrate"></a>归档 ≠ 迁移

想在另一台设备**续聊**,搬的是**原生 jsonl / 会话目录**;别指望从 exporter 产物反推。`/share html`、以及 dredge-up skill 的离线 HTML 报告,都是**有损只读**的渲染产物（明确丢弃 `system.message`、`hook.*`,事件链关系不保留），只为给人看,拿它反推回可 resume 的 jsonl 不现实。要"离线把会话存档成 HTML 给人看"用 dredge-up skill;要"跨机续聊"用本文。

## <a id="pty-verify"></a>交互式 TUI 的无头实测方法

验证 picker/resume 行为需要真开交互式 TUI（`-p`/headless 会跳过 `resume-auto-cd`、也没有 picker）。无头驱动它的可复现套路 🔬:

- 用 `pexpect`（`uv run` + PEP 723 内联依赖声明 `pexpect`）spawn `copilot --resume`,它自动处理 PTY 与**控制终端**;手写 `pty.openpty()` 时若 `os.setsid()` 后不补 `ioctl(fd, TIOCSCTTY)`,子进程拿不到控制终端、键盘输入进不去（表现为渲染一帧后卡死、发键无反应）。
- 首次在隔离 `COPILOT_HOME` 启动会弹**文件夹信任**对话框,挡在 picker 前;`expect` 到 "Do you trust" 后发回车（默认选中 "Yes"）放行。
- 会话是否"非空"、名字/时间显示,靠 `workspace.yaml`(name/times) + `events.jsonl`(至少一轮 user+assistant) 手搓即可构造;`session-store.db` 有意留空以验证"目录驱动、无需 DB 行"。
