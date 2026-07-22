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

**`resume-auto-cd` 行为** 📖🔬:resume 时若持久化 cwd 存在且是目录 → 自动 `cd` 进去;若缺失 → 打印 `warning: resume-auto-cd: ignoring persisted cwd '<path>': missing or not a directory`（或 `: not an absolute path`）,回退到启动目录,**能续、不致命**。对策二选一:在新机 `mkdir` 出那个 cwd,或按上表改写三处 cwd。环境变量 `COPILOT_DISABLE_RESUME_AUTO_CD=1`（或 `true`）可整体关掉;headless/`-p`/`--server`/`--acp` 模式本就跳过 auto-cd。

## <a id="mtime-prune"></a>时间、排序、mtime 与清理

- **文件 mtime 决定一切"时间/排序/陈旧"**（picker 时间列、picker 排序、`--continue` 选最新、prune 判陈旧）🔬。`touch -d` 改 mtime,picker 时间立刻跟着变;让 `workspace.yaml.updated_at` 或 DB `updated_at` 与 mtime 冲突,`--continue` 仍按 mtime 选、二者都翻不了盘 🔬。
- **`pruneOldSessions` 按文件 mtime 判陈旧、删整个会话目录** 📖:`cutoff = now − olderThanDays×24h`,`listSessions().filter(f => f.modifiedTime <= cutoff)`,`modifiedTime` 即文件 mtime。**但它不是后台自动 GC**:全 bundle 只有一个 `scope:"server"` 的 RPC `sessions.pruneOld`（`olderThanDays` 由调用方传入),没有开机/定时触发器,也没有 retention 设置项 🔬;默认 `includeNamed:false` → **有名字的会话受保护**。→ prune 只在"某次清理动作被显式触发"时发生。
- **⚠️ `cp -p` 是雷** 🧭:`cp -p`/`rsync -a` 保留旧 mtime,会让迁移来的会话 ① `--continue` 够不到、② picker 显示成"很久以前"、③ 一旦有人跑会话清理就可能被删。→ 迁移后把 mtime 设成"现在"（防清理、但 picker 时间显示成刚才）**或**设成原始 `updated_at`（picker 时间真实、但离清理 cutoff 更近）,二选一,别留 `cp -p` 的旧 mtime。
- **创建时间(btime)改不回** 📖:Linux 用户态只能改 atime/mtime（`utimensat`),没有 syscall 改 btime;唯一歪招是 root `debugfs -w -R 'set_inode_field <inode> crtime …'` 直接改块设备 inode（要 root、挂载盘上有风险、逐 inode 改,大批量不现实）。会话真正的创建时间不丢——在 `workspace.yaml.created_at` 和 DB `created_at` 里。picker 显示的"创建时间"是**文件 mtime**、不是 btime,所以 `stat` 看到的 Birth 是复制时刻纯属系统限制的展示层，不影响使用。
- **DB `created_at` 只对 `/chronicle` 有意义**,且 resume 自动回填时写的是 **resume 时刻**而非原始值 🔬 → 想让 `/chronicle` 里时间准,迁移时要**手动**把源 DB 行的原始 `created_at` 写进目标 DB（见下[迁移步骤](#copilot-steps)第 6 步）。

## <a id="copilot-home"></a>重定向配置目录（`COPILOT_HOME` / `--config-dir`）

Copilot 的配置目录解析优先级 = `--config-dir`（隐藏、标 deprecated）→ `COPILOT_HOME` → `~/.copilot` 📖;`session-state/` 和 `session-store.db` 都在解析出的这个目录下 🔬。用途:

- **隔离测试不污染真环境** 🔬:`COPILOT_HOME=/tmp/iso copilot --resume` 只看 `/tmp/iso` 下的会话,真 `~/.copilot` 不受影响。做迁移前的小样验证、或本文里这些实测,都靠它。
- 迁移时若不想写进真 `~/.copilot`,可把整套会话放进另一个目录并用 `COPILOT_HOME` 指过去。

## <a id="copilot-steps"></a>迁移一个 Copilot 会话（目标产物）

一次正确迁移完成后,目标机应达到的状态 + 达成它的典型手段:

1. **枚举定范围**:源机用 `session-store.db` 按 `cwd LIKE '<旧前缀>%'` 查,再扫所有 `workspace.yaml` 的 cwd 取并集（补上"有目录无 DB 行 / 有 DB 行无目录"）。
2. **定 cwd 映射**（`<旧home>/<旧cwd前缀>` → `<新home>/<新cwd前缀>`）并与用户确认。
3. **小样验证**（1~2 个会话,隔离 `COPILOT_HOME`):传输 → 改 cwd → 填 DB 行 → resume 实测。判据:bogus-id 报 `No session, task, or name matched`、真 id 能进（报 auth 或真复述）= 会话解析成功。
4. **传输整目录**（不是单文件):`rsync -aH --files-from=<id列表> <源>/session-state/ <目标>:/…/session-state/`;可 `--exclude rewind-snapshots` 瘦身。
5. **改写 cwd 三处**（见 [cwd 三处](#cwd-places)):`workspace.yaml` 的 `cwd:` + `events.jsonl` 的 `session.start.context.cwd`（含 `system.message` 内嵌）全部前缀替换。
6. **合并 DB 行**:把源 DB 的行 `INSERT OR REPLACE` 进目标 `session-store.db`（cwd 改写、**保留原始 `summary/created_at/updated_at`**，否则 `/chronicle` 里时间/名字丢）。
7. **设 mtime**（见 [mtime 与清理](#mtime-prune)):设成"现在"防清理,或设成原始 `updated_at` 让显示真实——二选一,别留 `cp -p` 旧值。
8. **验证**:真 id resume 能解析、picker 里名字/时间对、数量对得上。
9. **最后才删源**:确认目标是完整副本（`rsync -n` 干跑 0 差异）+ 留备份 + 用回收站删（可恢复）。

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
- **`trash-put` 跨卷失败**:回收站按 FreeDesktop 规范需与被删文件**同卷**;`/tmp`(tmpfs) 或独立卷上的文件删不进 home 卷的回收站,非 root 又无权在别处建回收站。同卷才能 trash;`trash-put` 同卷只是 rename、不清空回收站不真正释放空间。
- **家目录换到独立卷 / 搬成 `home.old`**:挂载点变化连带影响空间、trash、软链——搬前先 `df` 看清卷布局。
- **源上有活跃写入进程**:如文档服务在持续重生成文件(mtime 一直变),删源前必须先停;子进程脱离 systemd cgroup 成孤儿时 `systemctl stop` 杀不掉,得 `kill <PID>` 补刀。

## <a id="archive-vs-migrate"></a>归档 ≠ 迁移

想在另一台设备**续聊**,搬的是**原生 jsonl / 会话目录**;别指望从 exporter 产物反推。`/share html`、以及 dredge-up skill 的离线 HTML 报告,都是**有损只读**的渲染产物（明确丢弃 `system.message`、`hook.*`,事件链关系不保留），只为给人看,拿它反推回可 resume 的 jsonl 不现实。要"离线把会话存档成 HTML 给人看"用 dredge-up skill;要"跨机续聊"用本文。

## <a id="pty-verify"></a>交互式 TUI 的无头实测方法

验证 picker/resume 行为需要真开交互式 TUI（`-p`/headless 会跳过 `resume-auto-cd`、也没有 picker）。无头驱动它的可复现套路 🔬:

- 用 `pexpect`（`uv run` + PEP 723 内联依赖声明 `pexpect`）spawn `copilot --resume`,它自动处理 PTY 与**控制终端**;手写 `pty.openpty()` 时若 `os.setsid()` 后不补 `ioctl(fd, TIOCSCTTY)`,子进程拿不到控制终端、键盘输入进不去（表现为渲染一帧后卡死、发键无反应）。
- 首次在隔离 `COPILOT_HOME` 启动会弹**文件夹信任**对话框,挡在 picker 前;`expect` 到 "Do you trust" 后发回车（默认选中 "Yes"）放行。
- 会话是否"非空"、名字/时间显示,靠 `workspace.yaml`(name/times) + `events.jsonl`(至少一轮 user+assistant) 手搓即可构造;`session-store.db` 有意留空以验证"目录驱动、无需 DB 行"。
