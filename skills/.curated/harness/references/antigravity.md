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
| `--gemini_dir <path>` | **隐藏旗标**（被 `main.hideFlagsForExternal` 从 `--help` 隐藏）：指定 `.gemini` 目录路径（绝对路径直接生效，相对路径相对于 `$HOME`），用于多账号隔离而不污染 `$HOME` |
| `--app_data_dir <rel>` | **隐藏旗标**：相对于 `GeminiDir` 的应用数据子目录名（默认 `"antigravity-cli"`；注意 `conversation_summaries.db` 按 `app_data_dir` 列过滤会话，多账号共享会话历史时应保持默认值 `"antigravity-cli"`，只改 `--gemini_dir`） |

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

## 鉴权存储与多账号

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
| `config` | 软链 → `~/.gemini/config` | 共享 `mcp_config.json`、`hooks.json`、skills、projects |
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

## 上下文压缩

**1M 模型实际只用到 ~256K**。上下文增长到 250K–270K 时自动压缩到 15K–30K，此后循环。阈值不是写死在客户端的字面量，而是服务端 feature flag（Unleash）按账号 / 模型下发的实验档；1.4.8 二进制内嵌的默认档 `CASCADE_USE_EXPERIMENT_CHECKPOINTER` 可见参数结构：`max_token_limit: 256000`（压缩器强制的上下文硬上限）、`token_threshold: 50000`、`max_overhead_ratio: 0.15`，另有 Claude 1M 灰度变体 `claude-1m_840k`（`max_token_limit: 840000`）——每个账号实际拿到哪档由服务端决定。CLI 侧无法通过 settings.json、环境变量或旗标修改；Python SDK 的 `CompactionConfig(token_threshold=...)` 是唯一可配位置（见 [Python SDK](#sdk)）。

**两种丢弃机制**：压缩（compaction）产生 CHECKPOINT 标记和散文摘要；预截断（truncation）在发送前静默裁剪早期历史，无任何标记。

**Desktop 版额外问题**：Claude 模型（200K 窗口）有时完全不触发压缩，直接报 `prompt is too long` 终止会话。

**缓解**：把关键决策和协议约束写入 `AGENTS.md` 或项目文档——系统规则每轮完整重注入，不受压缩影响。加入"修改文件前必须先读当前内容"的规则可降低压缩后"修复"已解决问题（Ghost Revert）的风险。

详细排查过程和社区证据见 `mess` skill 的 [antigravity-cli.md](../mess/references/antigravity-cli.md)。 🔬 本机 60 条会话实测，压缩峰值全部在 250K–270K 区间。

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

## 会话数据

| 路径 | 内容 |
|---|---|
| `~/.gemini/antigravity-cli/conversations/<id>.db` | 完整对话轨迹（SQLite，`steps` + `gen_metadata` 表） |
| `~/.gemini/antigravity-cli/brain/<id>/.system_generated/logs/transcript.jsonl` | 每条 API 调用的 token 计数和内容 |
| `~/.gemini/antigravity-cli/conversation_summaries.db` | 会话索引（标题、状态、workspace） |

查看历史会话的上下文用量：读 transcript.jsonl 最后一条有 `input_tokens` 的记录，`input_tokens + cache_read_tokens` 即为当时的上下文大小。恢复会话用 `agy --conversation=<id>` 或在 TUI 中 `/resume`。
