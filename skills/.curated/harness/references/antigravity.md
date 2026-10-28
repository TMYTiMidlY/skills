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

### 双账号隔离（已验证方案）

agy 不提供只重定向自身数据目录的环境变量（不像 Codex 有 `CODEX_HOME` 只改工具数据路径、不影响 git/SSH 等其他 `$HOME` 引用）。**唯一已验证的隔离方式是整个替换 `HOME`**——这意味着 git、SSH、工具配置也跟着换，需要额外软链回来。二进制中的 `ANTIGRAVITY_APP_DATA_DIR`、`ANTIGRAVITY_GEMINI_DIR`、`JETSKI_APP_DATA_DIR` 属于插件子命令入口，不改变主 CLI 数据目录。

在 `.bashrc` 中定义包装函数（类似 `codex-gth`）：

```bash
agy-alt() {
    HOME="$HOME/.agy-homes/<account>" command agy "$@"
}
```

函数只在加载过 `.bashrc` 的交互 shell 里存在；非交互调用（agent、`ssh <host> <command>`）解析不到它。把同样的逻辑写成 `~/.local/bin/agy-<name>` 可执行脚本，对所有调用方可见：实例名取自脚本名，复制改名即得新实例；脚本内每次启动幂等补链（目标存在且链接位置为空才建），免除一次性手工铺链。包装内同时 unset `GEMINI_DIR` / `JETSKI_APP_DATA_DIR`，并把 `XDG_CONFIG_HOME` 等四个 XDG 变量指向实例 HOME 下，避免调用方环境里的绝对路径穿透隔离。

> 🔬 排查多账号入口先分清 shell 形态：非交互 `ssh <host> 'type agy-<name>'` 报 not found 不代表入口不存在（`.bashrc` 的交互守卫提前 return），换 `bash -ic` 再验。（2026-10-28 两台 Linux 实测）

隔离 HOME 内部结构（`~/.agy-homes/<account>/`）：

| 路径 | 类型 | 说明 |
|---|---|---|
| `.gemini/antigravity-cli/antigravity-oauth-token` | 独立文件 | 该账号的凭据，**不能软链** |
| `.gemini/antigravity-cli/settings.json` | 软链 → 真实 HOME | 共享主题、默认模型 |
| `.gemini/config` | 软链 → 真实 HOME | 共享 MCP、skills、projects |
| `.gitconfig` / `.ssh` / `.config` | 软链 → 真实 HOME | 共享 git 身份和工具配置 |
| `conversations/` / `brain/` / `implicit/` 等 | 软链 → 真实 HOME | 共享会话历史和压缩数据 |

这样两个入口各自刷新各自凭据、不互相覆盖，同时共享全部历史和配置；2026-10-28 升级后还需按下节屏蔽 keyring，否则两边凭据仍会串到同一条 keyring 记录。

> 并发写 `conversation_summaries.db`（SQLite WAL 模式）在正常使用下安全；避免从两个入口同时打开同一会话即可。

`conversation_summaries.db` 的软链有两种实测可用的形态：只链 `.db`（实例目录不出现 `-wal`/`-shm`，日志文件落在真实文件所在目录），或 `.db`、`-wal`、`-shm` 三者都链（实例内显式指向同一物理库与锁文件）。后者把"共享同一个库"在目录层面表达得直白，脚本幂等补链时三者一起处理最省心。

> 🔬 同一账号先在完全隔离的旧布局登录、再迁到共享布局后，旧实例目录会残留一份仍然有效的 token。迁移后先在新入口确认登录可用且账号一致，再删除旧实例目录。（2026-10-28 实测）

### keyring 优先与实例隔离（2026-10-28 升级后）

🔬 2026-10-29 实测：agy 自动升级（`bin/`、`builtin/` 目录 2026-10-28 14:16 更新）后鉴权改为 ChainedAuth、**优先 keyring**——真实 HOME 的 `antigravity-oauth-token` 不再生成。Secret Service 走 D-Bus、按 Linux 用户共享，**与 HOME 无关**，上述整体替换 HOME 的隔离对它完全失效：两个实例共用同一条 keyring 凭据，一边切换账号另一边数十秒内跟着变（日志证据：真实 HOME 浏览器登录后 40 秒，另一实例启动即 `ChainedAuth: authenticated via keyring (effective: keyring)`、同一账号；二进制含 `github.com/zalando/go-keyring`）。

**修复（已验证）**：实例 wrapper 内把会话总线指向不存在的地址：

```bash
export DBUS_SESSION_BUS_ADDRESS="unix:path=$H/.cache/agy-no-keyring/bus"
```

要点：

- **不能只 `unset`**——godbus 在变量缺失时回退 `$XDG_RUNTIME_DIR/bus`，真实会话总线仍可达，keyring 照常工作，屏蔽即失效。
- 连接立即失败（`connect: no such file or directory`），不是等 keyring 超时；触发二进制内置回退：日志出现 `Failed to load stored token from keyring, falling back to file` / `Failed to save token to keyring, falling back to file`，token 落回实例文件，HOME 隔离恢复生效。
- 实例中残留的过期文件 token 会被 refresh 自动复活（实测 2026-10-28 的旧 token 于 10-29 直接刷新成功、恢复实例自有账号），无需重新登录；真实 HOME 的 agy 不动，继续走 keyring，两边账号彻底独立。
- 残留共享点：`plugin-secrets.json` 存于 `$XDG_CONFIG_HOME/antigravity/`；若实例 `.config` 是整目录软链，插件密钥仍两边共享（与账号登录无关；介意时把 `.config` 改为真实目录＋按需软链）。

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
