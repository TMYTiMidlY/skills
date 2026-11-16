# Antigravity CLI / Desktop / SDK（agy）

Google Antigravity 的终端 CLI（`agy`）与桌面版（Antigravity App / IDE），共用同一后端引擎。另有独立产品线的 Python SDK（`pip install google-antigravity`），认证与计费和 CLI 完全不同，见下文 [Python SDK](#sdk)。CLI 为 Go 编译的闭源二进制，GitHub 仓库 [google-antigravity/antigravity-cli](https://github.com/google-antigravity/antigravity-cli) 仅含 issue tracker 和 CHANGELOG，无源码。

## CLI 能力

**安装**：`curl -fsSL https://antigravity.google/cli/install.sh | bash`，二进制在 `~/.local/bin/agy`。

**模型**：通过 `agy models` 或 `/model` 选择，包含 Gemini 4 Argon / 3.8 Flash、Claude Opus / Sonnet 5.5、GPT-OSS 120B。每模型支持 low / medium / high 推理档位。

**常用旗标**：

| 旗标 | 作用 |
|---|---|
| `--print` / `-p` | 单次非交互执行 |
| `--conversation <id>` | 恢复指定会话 |
| `--model <name>` | 指定模型 |
| `--mode auto` | 自动审批模式（安全命令不询问） |
| `--output-format stream-json` | 机器可读输出 |
| `--gemini_dir <path>` | **隐藏旗标**：指定 `.gemini` 目录（绝对路径直接生效，相对路径相对于 `$HOME`）；多账号用法见[鉴权存储与多账号](#multi-account) |
| `--app_data_dir <rel>` | **隐藏旗标**：指定相对于 `.gemini` 根的应用数据子目录名（默认 `"antigravity-cli"`）；隔离时的取值约束见[鉴权存储与多账号](#multi-account) |

**关键斜杠命令**：`/context` 查看上下文用量、`/compact` 手动压缩、`/resume` 列出并恢复会话、`/usage` 查看额度、`/plan` 规划模式。

## <a id="full-access"></a>权限体系与 full access 配置

权限由**两套相互独立的系统**组成，都要设置才完全不问：

1. **工具权限（tool permissions）**：`read_file` / `write_file` / `command` / `read_url` / `execute_url` / `mcp`（IDE 侧另有 `unsandboxed`）六类动作，按 `action(target)` 规则匹配（路径前缀、命令 token 前缀、`regex:` 前缀、`*` 通配），分 Allow / Deny / Ask 三个列表；`/permissions` 面板管理。全局面板等价物是 `settings.json` 的 `toolPermission` 预设：`request-review`（默认，write/bash/web 都确认）、`strict`（所有非只读都确认）、`proceed-in-sandbox`（沙箱内自动放行、出沙箱仍问）、`always-proceed`（从不询问，对应 IDE 权限预设 **Turbo**：无沙箱、命令不受限、MCP/Web 放行）。
2. **执行模式（execution modes）**：管文件编辑的 diff 确认，`Shift+Tab` 循环或 `agentMode` 键持久化。`default` 逐个弹 diff，`accept-edits` 自动接受文件编辑，`plan` 只读规划。

持久化 full access（官方键，写入 `~/.gemini/antigravity-cli/settings.json`）：

```json
{
  "toolPermission": "always-proceed",
  "agentMode": "accept-edits",
  "allowNonWorkspaceAccess": true
}
```

`allowNonWorkspaceAccess` 解除文件读写限于 workspace 根的限制；单次全量放行用 `--dangerously-skip-permissions`。Turbo / always-proceed 意味着无沙箱、无人工把关，破坏性操作直接执行；回退档位按需选 `proceed-in-sandbox` + `/permissions` 细粒度 allow 规则（如 `command(git)`）。权限规则的匹配细节（前缀匹配何时降级为全行精确匹配、write 隐含 read）见官方 [Permissions](https://antigravity.google/docs/permissions/) 文档。

## <a id="multi-account"></a>鉴权存储与多账号

### 存储位置

登录凭据是一个 JSON 文件：

```text
~/.gemini/antigravity-cli/antigravity-oauth-token
```

包含 `token.access_token`、`token.refresh_token`、`token.expiry` 和 `id_token`（含账号邮箱）。文件权限 600。WSL 环境下自动走文件存储（日志显示 "Using file-based token storage because WSL environment detected"）；有桌面密钥环的系统走 Secret Service（`service=gemini, username=antigravity`）。**2026-10-28 升级后有 Secret Service 的桌面默认优先 keyring**，`antigravity-oauth-token` 不再落盘，多实例 HOME 隔离对它失效——见下面「keyring 优先与实例隔离」。

**整个登录态就这一个文件**——复制它即可在别处恢复登录，已实测验证（含 refresh token 自动续期）。会话数据库、配置、缓存均不是恢复鉴权所必需。

### 并行进程覆盖问题

多个 agy 进程共用同一凭据文件时，各自在内存中持有不同账号的凭据，token 刷新后写回同一文件，**最后写入者决定下一个新进程读到哪个账号**。`--conversation` 只选会话，不绑定鉴权。

已运行进程不受磁盘文件替换影响——必须退出旧进程才能彻底切换。

### 双账号隔离（已验证根治方案：内置隐藏旗标 `--gemini_dir`，严禁替换 `HOME`）

🔬 2026-11-12 二进制逆向与实测核实：

- **内置隐藏旗标 `--gemini_dir`**：虽然 `agy` 的环境变量 `ANTIGRAVITY_APP_DATA_DIR` / `ANTIGRAVITY_GEMINI_DIR` / `JETSKI_APP_DATA_DIR` 仅用于插件子命令，且 `agy --help` 看不到数据目录参数，但逆向 `main.init.1`（`0xa5c299f`）证实二进制在全局 `flag.CommandLine` 上原生注册了两个旗标（仅被 `main.hideFlagsForExternal` 从 `--help` 面板隐藏）：
  1. `--gemini_dir`（默认 `".gemini"`）：`"Path where Gemini files are stored. If absolute path, will set directly, otherwise relative to home directory"`
  2. `--app_data_dir`（默认 `"antigravity-cli"`）：`"Path where application data is stored, relative to GeminiDir"`
- **全链路生效验证**：
  - `main.main` 在分发子命令（`models`、`mcp`、`plugin`、`agents`、`remote-control` 等，预扫描 `--help` 时亦自动跳过 `-` 前缀旗标）、启动 TUI / `--print`（`entrypoints.launchCLI` → `resolveGeminiDirPath` → `backend.NewServerBackend` → `auth.NewCLITokenStorage`）及启动语言服务（`language_server.setUpFS` → `local.SetGeminiDir`）之前统一执行 `flag.CommandLine.Parse`；甚至 `agy` 内部派生子进程（如后台 updater / remote-agent，`0xa25f733`、`0xa570a40`）也会自动透传 `--gemini_dir=<val>`。
  - **为什么只传 `--gemini_dir` 而保持 `--app_data_dir` 默认值 `"antigravity-cli"`**：`conversation_summaries.db` 表含 `app_data_dir` 列，检索历史会话时固定过滤 `WHERE app_data_dir = ?`（默认值为 `'antigravity-cli'`）。只重定向 `--gemini_dir="$real_home/.agy-homes/$name/.gemini"` 并保持 `app_data_dir` 为 `"antigravity-cli"`，多账号实例即可通过软链无缝共享全部历史会话。
- **为什么严禁再用替换 `HOME` 的旧方案**：
  - 旧方案把 `HOME` 改写成 `~/.agy-homes/<name>`，会导致 `agy` 及其 `run_command` 派生的全部子进程（`trash-put`、`lake`、`elan`、`uv`、`git`、`ssh`、`codex` 等）把假 `HOME` 当成用户家目录：不仅 `trash-put` 会在 `~/.agy-homes/<name>/.local/share/Trash` 下产生普通终端 `trash-list` / `trash-empty`（含 `--all-users`）完全看不见的**隐形影子回收站**（实测漏掉 16 个旧克隆共 **55 GB**），还会造成 `.cache`（实测冗余 **22 GB**）、`.elan` 等缓存翻倍；靠逐个补顶层软链或覆写 `XDG_*` 只是围堵症状。
  - 改用 `--gemini_dir` 后，**全程不修改 `$HOME`**（且通过 `export HOME="${HOME%%/.agy-homes/*}"` 自动纠正可能残留的旧面板环境），从根源上消除一切假 `HOME` 派生问题，无需在实例目录下软链任何顶层点文件，也无需覆写 `XDG_*`。

在 `.bashrc` 中定义多账号实例包装函数（或写成 `~/.local/bin/agy-<name>` 可执行脚本，对非交互 `ssh <host> <cmd>` 与子进程均可见）：

```bash
_agy_instance() (
  set -euo pipefail
  name="$1"; shift
  real_home="${HOME%%/.agy-homes/*}"
  bin="$real_home/.local/bin/agy"
  gdir="$real_home/.agy-homes/$name/.gemini"
  # 首次启动自动幂等铺齐 .gemini 下的共享软链，绝不触碰 $HOME
  mkdir -p "$gdir/antigravity-cli"
  [ -e "$gdir/config" ] || [ -L "$gdir/config" ] || ln -s "$real_home/.gemini/config" "$gdir/config"
  for rule in AGENTS.md GEMINI.md; do
    if [ -e "$real_home/.agents/$rule" ] && [ ! -e "$gdir/$rule" ] && [ ! -L "$gdir/$rule" ]; then
      ln -s "$real_home/.agents/$rule" "$gdir/$rule"
    fi
    if [ -L "$gdir/$rule" ] && [ ! -e "$gdir/$rule" ]; then
      printf '[agy-instance] warning: broken symlink %s\n' "$gdir/$rule" >&2
    fi
  done
  for gitem in annotations brain conversations conversation_summaries.db conversation_summaries.db-shm conversation_summaries.db-wal history.jsonl implicit jetski_state.pbtxt mcp presence; do
    if [ ! -e "$gdir/antigravity-cli/$gitem" ] && [ ! -L "$gdir/antigravity-cli/$gitem" ]; then
      ln -s "$real_home/.gemini/antigravity-cli/$gitem" "$gdir/antigravity-cli/$gitem"
    fi
  done
  export HOME="$real_home"
  export DBUS_SESSION_BUS_ADDRESS="unix:path=$gdir/agy-no-keyring-bus"
  unset GEMINI_DIR JETSKI_APP_DATA_DIR 2>/dev/null || true
  exec "$bin" "--gemini_dir=$gdir" "$@"
)
```

> 🔬 排查多账号入口先分清 shell 形态：若只定义在 `.bashrc` 中，非交互 `ssh <host> 'type agy-<name>'` 报 not found 不代表入口不存在（`.bashrc` 的交互守卫提前 return），换 `bash -ic` 再验。（2026-10-28 两台 Linux 实测）

实例 `.gemini` 内部结构（`~/.agy-homes/<account>/.gemini/`）：

| 路径 | 类型 | 说明 |
|---|---|---|
| `antigravity-cli/antigravity-oauth-token` | 独立文件 | 该账号的凭据，**不能软链** |
| `antigravity-cli/settings.json` | 独立文件或软链 | 各账号可独立保存默认模型（`/model`）与 `trustedWorkspaces`；`agy` 保存设置时走临时文件原子 rename |
| `config` | 软链 → `~/.gemini/config` | 共享 `mcp_config.json`、`hooks.json`、skills、projects；二进制内 `fs.ConfigDir` 将 `<geminiDir>` 拼接 `"config"`（不固定指向真实 `$HOME`），因此多账号共享 `config/skills` 与 MCP 等配置依赖此软链 |
| `AGENTS.md` / `GEMINI.md` | 软链或独立文件 | 不在 `config` 子目录内，需在各隔离 `.gemini` 根下单独补齐（分别链接到 `~/.agents/AGENTS.md` 与 `~/.agents/GEMINI.md`；实体存在才补链，已有入口保持原样）；同目录下 `AGENTS.md` 与 `GEMINI.md` 若同时存在会累积加载 |
| `antigravity-cli/{conversations,brain,implicit,presence,annotations,history.jsonl,jetski_state.pbtxt,mcp,conversation_summaries.db*}` | 软链 → `~/.gemini/antigravity-cli/…` | 共享会话历史、压缩数据、MCP schema 与活跃锁（`presence` 必须共享以通过 Ovis `/proc/<pid>/fd` realpath 校验） |

> **旧版假 `HOME` 实例目录的存量清理**：若机器曾跑过改写 `HOME="$h"` 的旧版包装，先检查 `~/.agy-homes/<account>/.local/share/Trash/{files,info}` 是否残留影子回收站条目（按 FreeDesktop 重名规则追加 `_1`、`_2`，将 `files/<name>` 与 `info/<name>.trashinfo` 成对同卷 `rename` 合并回 `~/.local/share/Trash/`），并将旧版仍在运行的进程过渡期内的顶层目录（`.local`、`.cache` 等）合并回真实 `HOME`。

这样每个账号入口各自刷新各自的 `antigravity-oauth-token`、不互相覆盖，同时 `$HOME` 保持真实家目录不变、共享全部会话历史与唯一回收站；2026-10-28 升级后还需按下节屏蔽 keyring，否则两边凭据仍会串到同一条 keyring 记录。

> 并发写 `conversation_summaries.db`（SQLite WAL 模式）在正常使用下安全；避免从两个入口同时打开同一会话即可。

`conversation_summaries.db` 的软链有两种实测可用的形态：只链 `.db`（实例目录不出现 `-wal`/`-shm`，日志文件落在真实文件所在目录），或 `.db`、`-wal`、`-shm` 三者都链（实例内显式指向同一物理库与锁文件）。后者把"共享同一个库"在目录层面表达得直白，脚本幂等补链时三者一起处理最省心。

> 🔬 同一账号先在完全隔离的旧布局登录、再迁到共享布局后，旧实例目录会残留一份仍然有效的 token。迁移后先在新入口确认登录可用且账号一致，再删除旧实例目录。（2026-10-28 实测）

### keyring 优先与实例隔离（2026-10-28 升级后）

🔬 2026-10-29 实测：agy 自动升级（`bin/`、`builtin/` 目录 2026-10-28 14:16 更新）后鉴权改为 ChainedAuth、**优先 keyring**——默认实例的 `antigravity-oauth-token` 不再生成。Secret Service 走 D-Bus、按 Linux 用户共享，**与 `--gemini_dir` 路径无关**，仅靠重定向目录对它完全失效：两个实例共用同一条 keyring 凭据，一边切换账号另一边数十秒内跟着变（日志证据：默认实例浏览器登录后 40 秒，另一实例启动即 `ChainedAuth: authenticated via keyring (effective: keyring)`、同一账号；二进制含 `github.com/zalando/go-keyring`）。

**修复（已验证）**：实例 wrapper 内把会话总线指向不存在的地址：

```bash
export DBUS_SESSION_BUS_ADDRESS="unix:path=$gdir/agy-no-keyring-bus"
```

要点：

- **不能只 `unset`**——godbus 在变量缺失时回退 `$XDG_RUNTIME_DIR/bus`，真实会话总线仍可达，keyring 照常工作，屏蔽即失效。
- 连接立即失败（`connect: no such file or directory`），不是等 keyring 超时；触发二进制内置回退：日志出现 `Failed to load stored token from keyring, falling back to file` / `Failed to save token to keyring, falling back to file`，token 落回 `--gemini_dir` 下的 `antigravity-cli/antigravity-oauth-token` 文件，账号隔离即生效。
- 实例中残留的过期文件 token 会被 refresh 自动复活（实测 2026-10-28 的旧 token 于 10-29 直接刷新成功、恢复实例自有账号），无需重新登录；默认 `agy` 不动，继续走 keyring，两边账号彻底独立。
- 残留共享点：`plugin-secrets.json` 存于 `$XDG_CONFIG_HOME/antigravity/`（与账号登录无关）。

第三方切换工具（[agyw](https://github.com/tranquocthong/agy-switcher)、[agy-cli-manager](https://github.com/zcop/agy-cli-manager)、[agyswap](https://pypi.org/project/agyswap-cli/)）均为全局切换型——切换前须退出所有 agy 进程，不支持并行。

## <a id="customization-discovery"></a>配置、Rules 与 Skills 发现

> 以下边界以官方[配置发现文档](https://antigravity.google/docs/customization-discovery)、[Rules 文档](https://antigravity.google/docs/rules)为准，并结合 `1.5.8` CLI 二进制静态分析与本机实测补充；涉及 Desktop / App 专属交互（如 `manual` 触发与 UI 开关）以官方文档为准，未在 Desktop 运行时实测。

### 作用域与目录遍历边界

- **工作区侧**：从当前目录向上遍历至 Git 仓库根（`.git` 所在目录；若当前目录不在 Git 仓库内，则只扫描工作区当前目录本身），探测各层的 `.agents/` 与 `.gemini/`，以及工作区各级 `AGENTS.md` / `GEMINI.md`。**不向仓库外继续上溯，也不向下扫描未打开的子目录**；单层目录下的 `skills/<name>/SKILL.md` 仅向下探测一层。
- **个人全局侧**：默认环境下，CLI 后端 `globalCustomizationDirs` 仅枚举三个配置根——`~/.gemini/antigravity-cli`、`~/.gemini` 与 `~/.gemini/config`。**`~/.agents/` 不在全局扫描列表中**：项目级 `<dir>/.agents/skills/` 可被原生发现，但用户级 `~/.agents/skills/` 不会被 Antigravity 自动发现。

### Skills 发现、兼容性与优先级

- **用户级共享 `skills` 接入**：要在 Antigravity 中复用全局 `~/.agents/skills/`，推荐软链到 `~/.gemini/config/skills`：
  ```bash
  mkdir -p ~/.gemini/config
  ln -s ../../.agents/skills ~/.gemini/config/skills
  ```
  `~/.gemini/config/skills` 同时被 CLI 与 App 侧个人配置根识别、优先让位给工作区项目技能。不建议直接放入 `~/.gemini/antigravity-cli/skills/` 或 `~/.gemini/skills/`，否则会反客为主压过工作区同名技能。
- **覆盖优先级（高到低）**：
  1. CLI 专用全局目录 `~/.gemini/antigravity-cli/skills/` 与 `~/.gemini/skills/`（CLI 侧高优入口，可覆盖工作区技能及清单 `exclude` 排除项）
  2. 仓库 `.gemini/config.json` 中的 `personal_customization_dir`
  3. 工作区规则与技能（越接近当前目录优先级越高；受清单 `exclude` 等配置过滤）
  4. 个人全局（`~/.gemini/config/`；受清单过滤）
  5. 内置技能（built-in）
- **元数据与刷新**：官方[配置发现文档](https://antigravity.google/docs/customization-discovery)将 `SKILL.md` 的 `description` 标为必填、`name` 标为可选（缺省时回退目录名）；但 `1.5.8` 的 `convertSkillPath` 存在 `RequireName` 校验分支，且跨工具仓库通常要求两者齐全。文件增改在下一轮次自动生效；若要在**当前交互式 CLI 会话内**即时刷新 `/skills` 与斜杠补全，执行 `/skills reload`。
- **内置技能分层门控**（🔬 `1.5.8` 实测样本）：`builtin/skills/` 磁盘目录共存 **14** 个 `SKILL.md`；Language Server RPC `GetAllSkills` 返回 **13** 个（受门控隐藏的内置技能未返回）；主会话系统提示实际注入 `<skills>` 为 **5** 个（通过 `builtin.RegisterGated`、特性旗标、当前角色与 `WithModeFilter` 按模式裁剪）。

### Rules 发现、触发与上下文预算

- **累积加载与 realpath 去重**：来自不同作用域（全局、仓库各级）的已发现规则**累积合并**生效，不会因为高优先级规则存在而整体屏蔽低优先级规则；同一 `~/.gemini` 下的 `AGENTS.md` 与 `GEMINI.md` 亦会累积注入。发现阶段按 `EvalSymlinks` 解析后的物理路径（realpath）去重，不同路径的两个独立常规文件即便内容完全相同也不会在加载时合并去重（引用内联展开也不等同于发现去重）。
- **普通指令 vs `rules/*.md`**：直接放置的 `AGENTS.md` 与 `GEMINI.md` 视为普通 Markdown 并以 `always_on` 注入（YAML frontmatter 被忽略）。`.agents/rules/*.md` 与 `.gemini/rules/*.md` 则要求有效 `trigger`：
  - `always_on`：每轮注入规则正文
  - `model_decision`：需提供 `description`，仅以摘要供模型按需调用
  - `glob`：按路径模式匹配触发；`1.5.8` 二进制同时兼容 `globs` 与单数 `glob` 字段
  - `manual`：手动 `@` 触发（官方标注为 App/IDE 侧交互能力）
- **清单注册与 `@` 引用差异**：通过 `rules.json` 可显式登记更深层子目录或目录外规则文件并保留其 `trigger`。规则正文中，`@[label](path)` 会在单文件大小校验之前内联展开目标文件内容；裸写 `@path` 仅改写引用路径提示，不在加载阶段内联文件内容。
- **双阈值保护**（`1.5.8` 静态分析）：单文件（含 `@[label](path)` 展开后文本）存在 **24,000 字节**硬上限；全部非内置规则共用 **20,000 token** 全局聚合预算（`defaultRulesBudget`），超出后按体积从大到小将规则文件降级为仅保留路径指针（不再内联全文），仅内置插件自带规则豁免此预算裁剪。

## <a id="context-compaction"></a>上下文压缩

### 压缩阈值与历史裁剪

压缩阈值并非客户端写死的固定常量，而是随构建版本、模型与服务端实验档（Unleash）变化：较早的 60 条会话样本均在 250K–270K 输入 token 附近触发压缩并降至 15K–30K；2026-11-16 核查的长会话则在 step 2274 增长至 509,066 输入 token 后，才于 step 2277 生成 `CHECKPOINT`、step 2278 回落至 42,200 token。排查具体会话时以实际日志记录为准。

> 旧构建 `1.4.8` 内嵌的 `CASCADE_USE_EXPERIMENT_CHECKPOINTER` 默认档参数为 `max_token_limit: 256000`、`token_threshold: 50000`、`max_overhead_ratio: 0.15`，同时存在 `claude-1m_840k`（`max_token_limit: 840000`）灰度变体，实际生效档位由服务端按账号与模型下发。CLI 无 `settings.json` 键、环境变量或旗标可改；仅 [Python SDK](#sdk) 提供独立的 `CompactionConfig(token_threshold=...)`。

客户端存在两种历史丢弃路径：压缩（compaction）写入 `CHECKPOINT` 步骤并生成散文摘要；预截断（truncation）在请求发送前直接裁剪早期历史且不留标记。Desktop 端另有 Claude 200K 窗口模型未触发压缩即直接报 `prompt is too long` 终止会话的历史样本，排查时需区分产品端与构建版本。

### 系统规则与对话内角色

已发现的全局规则由独立的系统提示构建链路在每轮组装注入；用户在对话中临时指定的角色与运行期读取的技能正文则留在历史消息内参与压缩。长会话应将角色激活状态、任务归属与未处理事项保存在外部可恢复记录中，在压缩或重启后按记录重读所需技能。

2026-11-16 对本地会话 SQLite 数据库的实测核对了 `CHECKPOINT` 2277 之后落盘的模型输入：

| 检查对象 | 实测结果 |
|---|---|
| `gen_metadata.idx=935` | `last_step_index=2440`，系统提示 55,699 字节，其中 `<user_rules>` 段 17,471 字节 |
| 当时两份全局规则源文件原始大小 | `AGENTS.md` 11,936 字节、`GEMINI.md` 5,186 字节；各自去除首尾空白后的全文均逐字包含于 `<user_rules>` |
| 技能正文 | `superagent/SKILL.md` 当时为 8,143 字节，全文未进入系统提示；技能列表仅含名称、路径与简介 |
| `CHECKPOINT` 与恢复步骤 | step 2277 摘要保留了已激活的协作前台身份与职责；step 2278 重新调用读取技能，step 2280 返回完整正文 |

本样本中，全局规则全文在上下文压缩后仍被完整重注入，本次漏更台账或越界直接编辑不能归因于全局规则被压缩抹除；其他会话仍需核对[规则预算](#customization-discovery)与实际模型输入。相比之下，对话内动态指定的角色和已读技能正文依赖摘要承接（技能目录持续可见仅代表可发现、不代表正文仍在上下文内），后续压缩仍可能丢失激活细节，需靠显式状态记录兜底恢复。

> 只读复核方法：打开 `~/.gemini/antigravity-cli/conversations/<id>.db` 读取 `gen_metadata` 最新完整行，其 `data` 列为 protobuf（外层 field 1 为 `GeneratorMetadata`，内层 field 1 为 `system_prompt`、field 20 为 custom metadata），提取 `<user_rules>` 与源文件正文逐字比对，勿仅检索文件名。同日跨过第二次 `CHECKPOINT` 2468 后复查，最新完整记录滚动至 `idx=1019`（`last_step_index=2669`），系统提示 56,583 字节、`<user_rules>` 段仍为 17,471 字节且两份全局规则全文逐字在列；而早先的 `idx=935` / `938` 旧行已被留存清理裁剪至 1,182 字节——旧记录缺失大段文本系事后裁剪所致，不能倒推当时未注入。上述结论基于本地 SQLite 落盘的模型输入，未对照紧邻压缩前后的两次完整 HTTP 请求；排查规则失效时仍应按“文件存在 → 规则被发现 → 预算内全文注入 → 模型实际遵循”逐层核对。

二进制实现上，规则组装与压缩摘要展开相互独立：`UserRulesSection.Content` 负责构建规则段，`checkpointStepToChatMessages` / `formatCheckpointStep` 负责将 `CHECKPOINT` 转为历史消息；`skillAccumulator.Accumulate` 记录技能元数据；本样本的技能正文经重新读取恢复。

> 本节及下文 CLI 机制的静态符号与虚拟地址均基于 2026-11-16 核查的 Linux x86-64 PIE 二进制（SHA-256 `39816d49d5ab92229952987225c23ea3fed7580699dcb4a444e0388e0ac1ce43`，ELF Build ID `cf2bdcfab1a7d961f5deb61d239908f8`），经 Go `pclntab` 符号恢复与反汇编交叉核实：`UserRulesSection.Content` `0x8f81820`、`checkpointStepToChatMessages` `0x88c9200`、`formatCheckpointStep` `0x88c9620`、`skillAccumulator.Accumulate` `0x865d2e0`、`PruneGeneratorMetadata` `0x7996d40`。客户端升级后虚拟地址会偏移，需重新定位。

## <a id="goal-and-schedule"></a>CLI 目标与定时调度

### `/goal` 与停止审计

`/goal` 命令展开长程目标提示词，并通过 `goalAccumulator.Accumulate` / `processGoalSteps` 维护会话的 `active_goal` 状态。每当回合准备结束时，内建 `GoalStopHook` 会审计当前目标是否完成并驱动模型继续推进，直至输出 `GOAL_COMPLETE` 或 `GOAL_CANCELLED` 标记；该命令在系统提示中的可见性受 `goal_stop` 配置门控。

CLI 还会从输入末尾向前查找斜杠命令：除句首解析外，`/` 前须为 Unicode 空白，命令名按 Unicode 空白切分并精确匹配，因此 `提醒 /goal` 或引用正文里的 ` /goal ` 都可触发，后面仍可跟其他文字。`提醒/goal` 本身不满足这一后缀边界，但解析器会跳过它继续查找更早的有效命令，引用和代码块也没有 Markdown 豁免。只讨论名称可写 `goal`；紧包的行内代码 `` `/goal` `` 在这条明文解析路径中不会命中，代码围栏内独立成行的 `/goal` 则仍可命中。

> 本构建静态依据：`handleUserInput` 在 `0xa5b8ed4` / `0xa5b8f15` 分别调用 `ParseLeading` / `ParseSuffix`；后者 `0xa5713c0` 经 `strings.LastIndex`（`0xa571400`）、`utf8.DecodeLastRuneInString`（`0xa571429`）与 `unicode.IsSpace`（`0xa571440`）检查边界，不合格或名称未匹配时继续向前查找。`splitToken` `0xa570d80` 同样以 `unicode.IsSpace` 切分，`parseSystemSlashCommand` `0xa60e540` 对名称作等长与字节精确比较；TUI 高亮另用正则 `(^|\s)(/[^\s]+)`。上述边界针对明文输入，已选中的结构化 Slash Command 条目会直接进入 `processGoalSteps`，需在输入框中另外移除。

对于在途的原生子代理与后台任务，Hook 通过检查 `AgentState` 的 `DependentsFullyIdle` 提供等待保护——下级依赖尚未空闲时直接放行结束当前回合，避免空转催促。但“等待外部人工回复或审批”未必被登记为内部依赖，若为开放式等待挂上长期不完结的 `/goal`，容易在每次停顿时反复触发续跑审计。`/goal` 适合完成标准明确、可自主收束的任务；外部审批与状态验收仍应交给独立门禁处理。

> 静态分析依据（对应前述构建）：`processGoalSteps` `0x8659da0`、`GetActiveGoalState` `0x865aa20`；oneharness `NewGoalStopHook` 闭包 `0x8e900a0` 在 `0x8e901ad` / `0x8e901b6` 检查 `found` 与 `DependentsFullyIdle`（旧 executor 闭包 `0xa01e220` 含同族保护），反汇编中未见硬编码的最大续跑轮数上限。命令用法参考官方 [Goal 文档](https://antigravity.google/docs/commands/goal)。

`/compact` 为手动压缩入口。当前构建的内置命令表不含 `/loop`；若环境中存在同名技能或工作流，需与原生斜杠命令区分。

### `schedule` 消息与生命周期

`schedule` 工具支持一次性定时器（timer）与周期性任务（cron），`/schedule` 斜杠命令用于引导模型调用该工具。具体参数以会话实际下发的工具 schema 为准：

| 参数 | 含义 |
|---|---|
| `DurationSeconds` / `CronExpression` | 一次性等待秒数 / 标准五字段 cron 表达式，二者互斥 |
| `Prompt` | 触发时作为高优先级通知投递给模型的提示词 |
| `MaxIterations` | cron 最大触发次数，缺省不限 |
| `TimerCondition` | timer 提前取消条件：`never`、`any` 或指定发送方 ID |
| `IsDaemon` | cron 是否在当前主任务收束后继续保留运行 |
| `ExactTiming` | 按指定时刻精确触发；普通周期轮询默认附加随机 jitter |

cron 每次触发都会经内部消息 Hub 向当前会话投递高优先级 `Prompt` 并唤醒模型推理。`IsDaemon` 仅延长后台任务在当前会话内的存活期，既不具备“外部无变化则跳过唤醒”的预过滤能力，也不构成跨 CLI 进程退出的系统级常驻服务；代码中的 `SuppressCompletionNotification` 仅抑制后台任务自身的结束通知，不影响每次 cron 触发主动投递的 `Prompt`。

需要低噪声盯盘外部状态（如轮询远端评论或 CI 变化）时，应由外部普通脚本先比对游标或指纹，仅在检测到实质变化时再唤醒会话；若要求跨 CLI 退出持久运行，需交由独立守护进程或外部自动化服务托管并单独验收。

> 实现与日志依据：oneharness 入口为 `ScheduleTool.Execute` `0x9026700`，其 `continueCron` `0x90286c0` 与 Cortex `handleCron` `0xa00f860` 两条发送路径向 `Client.Send` `0x80ef900` 传入优先级 `3`（`MESSAGE_PRIORITY_HIGH`），再经 `Hub.Send` `0x80f11e0` 与 `DeliverMessages` `0x8618020` 注入会话；会话日志 step 581–584 实测印证一次性 timer 启动后台任务、结束当轮并在到期后收到高优先级唤醒消息（cron 触发、重启恢复及消息竞争时序尚未动态验证）。命令用法参考官方 [Schedule 文档](https://antigravity.google/docs/commands/schedule)。

## <a id="cli-hooks"></a>CLI Hooks

### 配置发现与事件

CLI 从工作区、全局配置根与已安装插件中发现 `hooks.json`，默认全局入口为 `~/.gemini/config/hooks.json`，按命名 Hook 合并生效；`settings.json` 中的同名键并非该机制的配置入口。内置说明位于安装目录的 `agy-customizations/docs/hooks.md`，以下契约基于前述构建反汇编与内置文档核对：

| 事件 | 触发时机与典型用途 |
|---|---|
| `SessionStart` | 新会话初始化（上下文压缩后的恢复需结合 `PreInvocation` 覆盖） |
| `PreToolUse` | 工具执行前拦截，按工具名与参数放行或拒绝 |
| `PostToolUse` | 工具执行完成后记录结果或触发审计 |
| `PreInvocation` | 每次调用模型前读取本地可信状态并注入短提示 |
| `PostInvocation` | 单次模型调用返回后处理（此时流式文本通常已向终端输出） |
| `Stop` | 执行循环准备结束当前回合时审计未尽事项，决定放行或续跑 |

> 注册链路：`sharedfragment.wrapMixinWithJSONHooks` `0xa0230a0` → `jsonhook.WrapMixinWithJSONHooks` `0x8a74ba0`；`NewCallerFromHooks` `0x8a735a0` 仅注册上表六类事件（未包含 `UserPromptSubmit`）；CLI 侧配置加载入口为 `ReadAllHooks` `0xa223020` 与 `Store.ReloadHooks` `0xa5b6180`。在线说明见官方 [Hooks 文档](https://antigravity.google/docs/hooks)；编写脚本时须按 Antigravity 自有的事件名与 JSON 协议实现，不能直接照搬其他宿主的退出码约定。

### 拒绝、注入与继续协议

`command` 类型 Hook 从 `stdin` 读取 camelCase JSON，向 `stdout` 输出结构化决策 JSON。在 `PreToolUse` 中拒绝越界工具调用返回：

```json
{"decision":"deny","reason":"当前登记的前台会话应将此项修改派给执行者。"}
```

在 `PreInvocation` 中向当次模型输入注入简短状态消息，使用如下嵌套结构：

```json
{"injectSteps":[{"systemMessage":{"systemMessage":"当前角色及未处理事项，取自可信会话状态。"}}]}
```

在 `Stop` 中阻止回合结束并要求补齐收尾动作，可返回 `{"decision":"continue","reason":"尚有待核回执"}`；实现时应结合输入中的 `continuationActive` 限制最大续跑次数，并为取消、报错、在途异步依赖及等待人工回复留出正常结束分支。由于 `PreInvocation` 仅在模型即将被调用时触发，会话空闲期间的外部事件感知仍需配合外部监听机制。

> 协议细节与边界：`applyPreToolHooks` `0x8a6d4c0` 在 `0x8a6d98b` 比对 `"deny"` 并在 `0x8a6dad6` 构造拒绝错误；Hook 进程报错时存在记录日志后放行继续的分支，未见“退出码 `2` 即阻断”的特殊处理，因此拦截逻辑必须稳定输出合法 JSON，并在上线前实测脚本异常或超时时的默认行为。内置文档当前正式支持 `command` Hook（`prompt` Hook 受 `enable-generative-hooks` 实验门控）。此外，`processModelStream` `0x89167a0` 在流式阶段已创建并更新可供显示的响应，随后才进入 `stepPostInvocation` `0x890dfe0` 与 `stepStopHooks` `0x890e760`——`Stop` 适合追回漏做的台账或回执动作，若业务要求“对账完成前绝不向终端吐出完成宣告”，则需在外层控制消息发送或缓冲输出。

### 前台与子代理的配置边界

原生 `invoke_subagent` 默认继承父级的配置发现结果，全局 `hooks.json` 因而同样会在子代理调用工具时触发。若要仅限制协作前台而不误伤后台执行子代理，Hook 脚本应查询外部可信注册表精确比对当前 `conversationId`，并结合已登记角色与 `parentConversationId` 排除下级会话——切勿单独按 `rootConversationId` 过滤，因为该字段覆盖整棵会话树，会把同树的后台子代理一并拦截。

> 静态赋值依据：`InvokeSubagentHandler.inheritedCascadeConfig` `0x9ff61a0` 调用 `InheritSubagentCascadeConfig` `0x879d5a0`，且 `Manager.getJSONHooks` `0x8aa9240` 默认将 `inheritUser` 置为 `true` 聚合用户级 Hooks（自定义 agent 定义可显式覆盖该继承项）。`BuildHookArgsCommon` `0x8a6a1c0` 在 `0x8a6a31d`–`0x8a6a35b` 填入 `parentConversationId`、在 `0x8a6a378`–`0x8a6a3b5` 填入 `rootConversationId`（赋值依据为静态代码，真实 payload 及 `callerContext` 填充尚未动态核实）；正式部署自定义限域脚本前，建议先打印一次真实 `stdin` payload 核对各字段与 `callerContext` 的实际取值。

工具匹配器应覆盖当前构建实际下发的工具名（如 CLI 中的 `edit_file`、`write_file`），也可先用通配规则接入再在脚本内按工具名和 `realpath` 规范化路径做细粒度放行（防范相对路径或软链绕过）。注意仅拦截文件编辑工具并不能封堵 `run_command`（shell）、MCP 等其他写入通道；需要严格限制前台写面时，应将所有实际可写工具统一纳入检查。

> 工具名来源：core provider `0x8e94500` 直接将工具调用上下文的 `Name` 写入 `HookToolCall.Name`，再经 `Caller.CallHook` `0x8a73140` / `MatchesToolName` `0x8a78ba0` 匹配（内置文档中按旧 step 类型推导工具名的说法仅供参考，应以实际下发名称为准）。上线门禁前建议逐项实测：普通未登记会话不受影响、前台越界写操作被准确拒绝、同树子代理正常读写、旁路通道与脚本故障行为符合预期。

## <a id="sdk"></a>Python SDK

`pip install google-antigravity`（Apache-2.0，0.x 早期阶段），自带约 131 MB 的 `localharness` 静态二进制，与 CLI 同族引擎。模型后端认证只有三条路：

| 后端 | 凭据 | 说明 |
|---|---|---|
| Gemini Developer API | `GEMINI_API_KEY` 或 `LocalAgentConfig(api_key=...)` | AI Studio 申请，按 token 计量，有免费额度 |
| Vertex AI | `vertex=True` + GCP `project`/`location`（ADC） | GCP 按量 |
| 任意 OpenAI 兼容端点 | `LocalOpenAIAgentConfig(model=..., base_url=...)` | Ollama / LM Studio / 网关均可，不经过 Google 账号 |

**CLI 的订阅 OAuth token 不能复用给 SDK**。🔬 0.1.22 实测：默认 `LocalAgentConfig()` 无 key 启动直接 `ValueError: A Gemini API key is required`，校验发生在 Python 层、二进制未启动；把 `app_data_dir` 指到 CLI 数据目录（内含 `antigravity-oauth-token`）同样报错，token 文件不被读取；SDK 全部 `.py` 源码 grep `login|oauth` 零命中，localharness proto 无 auth 字段。二进制里的 OAuth 符号属于 MCP server 登录，不是模型后端认证。

`LocalAgentConfig` 能力面：自定义 Python 函数工具、声明式策略（`policy.allow/deny/ask_user`）、hooks、triggers（定时注入）、MCP server、skills、subagents、`compaction_config`、结构化输出、会话持久化（`save_dir` + `conversation_id` 续聊）、流式（`response.thoughts` / `response.tool_calls`）。🔬 抓包验证：harness 给模型下发 **14 个内置工具与 CLI 同族**（`view_file`、`write_to_file`、`replace_file_content`、`run_command`、`define_subagent`、`invoke_subagent`、`manage_subagents`、`manage_task`、`read_url_content`、`search_web`、`generate_image`、`schedule`、`send_message`、`run_workflow`），系统提示同为 Antigravity 身份——agent 核心能力与 CLI 同源，非阉割。无凭据即可端到端验证：本地起返回固定 `chat.completion`（含 `tool_calls`）的 OpenAI 兼容 mock 服务，`LocalOpenAIAgentConfig` 指向它，可验证 agent loop、工具真实执行与结果回传全链路。

CLI 有而 SDK 没有的：订阅配额计费、TUI（`/diff`、`/context`）、Remote Control、marketplace 插件分发、服务端实验（如 claude-1m 大窗口档）。

## <a id="session-storage"></a>会话数据与本地保留上限

| 路径 | 内容 |
|---|---|
| `~/.gemini/antigravity-cli/conversations/<id>.db` | 完整对话轨迹（SQLite，`steps` + `gen_metadata` 表，仅保存在本地） |
| `~/.gemini/antigravity-cli/conversation_summaries.db` | 会话摘要索引（标题、步数、修改时间、工作区；云端状态同步仅覆盖此类摘要元数据，不包含完整对话正文） |
| `~/.gemini/antigravity-cli/brain/<id>/` | 会话产物、`scratch/` 及 `.system_generated/logs/transcript*.jsonl`（每步 API 调用的 token 计数与内容，目录独立于 `.db` 留存） |
| `~/.gemini/antigravity-cli/history.jsonl` | 交互式终端提交过的用户提问原文（追加记录，不受 `.db` 淘汰影响） |

查看历史会话的上下文用量：读 `transcript.jsonl` 最后一条有 `input_tokens` 的记录，`input_tokens + cache_read_tokens` 即为当时的上下文大小。恢复会话用 `agy --conversation=<id>` 或在 TUI 中 `/resume`。

### 本地轨迹淘汰与批处理隔离

每次启动新 `agy` 实例时，客户端按文件修改时间排序清理 `conversations/` 目录，只保留最新的 500 个 `<id>.db` 文件。后台频繁调用一次性 `agy -p`（如自动润色、审阅或批处理脚本）时，每次调用都会新建会话并触发清理，数日内即可将闲置长会话挤出保留范围。高频 `agy -p` 任务应在同一账号下指定专用 `--gemini_dir`（复用原账号凭据与 `config`，保持独立的 `conversations/` 目录），将短命批处理会话与主力交互历史隔离；此处隔离的是会话留存目录，账号保持不变。

> 🔬 `1.5.8` / `1.5.9` 二进制逆向与实测：清理逻辑位于 `trajectorystore.(*Manager).PruneAll`，500 条上限写死在二进制内，无 `settings.json` 键、环境变量或旗标可改；`UnifiedStateSyncClient` 云端同步仅覆盖 `conversation_summaries.db` 对应的标题与步数摘要，无法从云端恢复已被清理的完整对话。

### 已淘汰会话的残余恢复

当目标会话的 `<id>.db` 已被清理、`--conversation=<id>` 无法恢复时，仍可从三处残余抢救上下文：

1. **`history.jsonl`**：永久保留所有交互式终端敲入过的用户提问原文。
2. **`brain/<id>/` 目录**：部分会话的产物目录与 `.system_generated/logs/transcript_full.jsonl` 独立留存，可直接读取完整步骤日志。
3. **尚未关闭的原终端进程**：只要持有该会话的旧 `agy` 终端进程仍在运行，完整对话历史仍在进程内存中；关闭窗口前先在原窗口内要求其导出总结落盘即可保住内容。
