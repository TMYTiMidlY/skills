# MCP 配置发现与工具名：五家客户端横向对照

同一台 MCP server 在不同 coding agent 客户端里会遇到两层问题：客户端从哪些配置源发现并合并它，用户怎样列出、修改和验证最终生效的 server；连接后，server 声明的工具 `foo` 又以什么名字暴露给模型。本篇对照 Copilot CLI、Claude Code、Codex、Gemini CLI、Cursor 的这两层行为。

配置发现决定“有哪些 server”，工具命名决定“模型看见什么 tool”。排查时先用客户端自己的列出 / 状态入口确认有效配置，不能只扫描一个用户配置文件：项目、插件 / 扩展、企业配置和单次运行覆盖都可能另外注入 server。

**为什么这事要紧**：常有人给 MCP 工具名硬加 server 名当前缀（`portal_exec` /
`myserver_search`），理由是"防撞名"。但如果客户端**本来就**按 server 命名空间化，那这个
自加前缀就是纯 **stutter（口吃）**——`portal` server 的 `portal_exec` 在客户端里会变成
`portal-portal_exec` / `mcp__portal__portal_exec`。到底撞不撞、要不要自带前缀，取决于**每家
客户端是否已经加、以及前缀取自哪里**。下面把五家逐一核实。

## 速览

| 客户端 | 加 server 前缀？ | 模型可见格式 | 分隔符 | 前缀取自 | 前缀来源实锤 |
|---|---|---|---|---|---|
| **Copilot CLI** | ✅ 总是 | `<key>-<tool>` | `-` 连字符 | **config key** | 实测：key `portal`（非 server 名 `portal-mcp-server`）→ `portal-portal_exec` |
| **Claude Code** | ✅ 总是 | `mcp__<key>__<tool>` | `__` ＋ `mcp__` 字面前缀 | **config key** | 官方文档明写"key in `mcpServers` becomes the server segment" |
| **Codex** | ✅ 默认 | `mcp__<key>__<tool>` | `__` ＋ `mcp__` 字面前缀 | **config key** | 源码：`callable_namespace = server_name`（`[mcp_servers.<KEY>]` 表键） |
| **Gemini CLI** | ✅ 总是 | `mcp_<key>_<tool>` | `_` ＋ `mcp_` 字面前缀 | **config key** | 源码：`Object.entries(mcpServers)` 的 key |
| **Cursor** | ✅（文档口径） | `<key>-<tool>` | `-` 连字符 | **config key**（`mcp.json`） | 官方文档：allowlist "server name is the key you used in `mcp.json`" |

**五家一致的两条硬结论**：

1. **全部都加 server 前缀**——没有一家把 MCP 工具名裸暴露给模型。所以"给工具名自带一个
   server 名前缀防撞"在这五家里**都是冗余 stutter**：客户端已经替你加了一层。
2. **前缀一律取『客户端配置里的 server key』**，**不是** server 自己在 MCP 握手里声明的
   name。这点五家零例外（Copilot 用 key `portal` 而非 FastMCP 声明名 `portal-mcp-server`
   是最干净的反证）。→ 想控制前缀长什么样，改的是**用户的配置 key**，改 server 内部
   `FastMCP("...")` 声明名没用。

分歧只在**表面装饰**：分隔符（`-` vs `_` vs `__`）、有没有 `mcp` 字面标记、以及净化 /
截断规则。详见各节。

## 准确度约定

各家源码开放度不同，本篇把证据类型和核对时间放在对应章节附近：

- **配置发现、枚举与修改**：优先采用厂商官方文档，并用 1810 已安装的 CLI 核对实际命令面；Codex 另挂锁到 commit SHA 的配置 loader / MCP CLI 源码，Gemini CLI 未安装则明确标出未做 live 验证。滚动文档按文中日期理解。
- **工具名装配**：Codex、Gemini CLI 真开源，行为挂锁到 commit SHA 的 file:line；Copilot CLI、Claude Code、Cursor 闭源 / minified，按 live MCP 观测或官方文档记录，并就地注明日期与未公开边界。

## <a id="config-discovery"></a>MCP 配置的发现、枚举与修改

这里的“发现”有两步：客户端先发现并合并 server 配置，再连接有效 server 并通过 MCP 的 `tools/list`、`prompts/list`、`resources/list` 等请求发现能力。各家的 `list` 命令对第二步做得并不一样，所以“配置已列出”不能一概等同于“server 已连接”。

从哪个目录运行命令也会改变结果。项目配置参与合并的客户端，都应在目标项目的实际工作目录里执行枚举命令；只在 home 目录执行，会漏掉仅对项目生效的 server。

| 客户端 | 持久配置的主要位置 | 枚举 / 状态入口 | 增删改入口 |
|---|---|---|---|
| **Copilot CLI** | `${COPILOT_HOME}/mcp-config.json`（默认 `~/.copilot/mcp-config.json`）、沿 cwd→git root 的 `.mcp.json` / `.github/mcp.json` | `copilot mcp list`、`copilot mcp get <name>`；两者可加 `--json`；交互态 `/mcp show` | `copilot mcp add/remove` 写用户配置；项目配置直接改对应 JSON；交互态 `/mcp add/edit/delete` |
| **Claude Code** | `~/.claude.json`（local / user scope）、项目根 `.mcp.json`（project scope） | `claude mcp list`、`claude mcp get <name>`；交互态 `/mcp` | `claude mcp add/remove` 的 `--scope` 选择 local / project / user，或改对应 JSON |
| **Codex** | `${CODEX_HOME}/config.toml`（默认 `~/.codex/config.toml`）、受信任项目的 `.codex/config.toml` | `codex mcp list`、`codex mcp get <name>`；两者可加 `--json`；运行中客户端 `/mcp` | `codex mcp add/remove` 只改用户配置；项目配置直接改 TOML；插件 server 通过插件管理 |
| **Gemini CLI** | `~/.gemini/settings.json`、项目根 `.gemini/settings.json`、系统 settings；均在 `mcpServers` 下 | `gemini mcp list`；交互态 `/mcp list`、`/mcp desc`、`/mcp schema` | `gemini mcp add/remove` 的 `--scope` 选择 project / user，或改 settings；`/mcp reload` 重新发现 |
| **Cursor** | `~/.cursor/mcp.json`、项目 / 父目录的 `.cursor/mcp.json` | `agent mcp list`、`agent mcp list-tools <id>`；交互态 `/mcp list` | 编辑 JSON 或在 Customize 管理；CLI 只提供 login / enable / disable，没有 add / remove |

### Copilot CLI

Copilot CLI 把多个来源按 server key 去重，优先级从高到低是：

1. 单次启动的 `--additional-mcp-config`；
2. 已安装插件提供的 MCP；
3. workspace 配置；
4. 用户配置 `${COPILOT_HOME}/mcp-config.json`。

workspace 配置从 cwd 向上扫描到 git root，每一级都检查 `.mcp.json` 和 `.github/mcp.json`；同目录两者同名时 `.mcp.json` 胜出，目录冲突时离 cwd 更近的定义胜出。项目目录未获 trust 时这些 workspace server 不加载。内置 GitHub MCP 不依赖上述文件，并且不能被同名自定义项覆盖。

`copilot mcp list` 按 user、workspace、plugin、builtin 分组并给出状态，`--json` 可供脚本读取；`copilot mcp get <name>` 同时列出 server 详情、工具和来源，环境变量与 header 默认遮蔽，只有显式 `--show-secrets` 才显示原值。交互态 `/mcp show` 提供同类检查入口。

`copilot mcp add` 和 `copilot mcp remove` 只写用户级 `mcp-config.json`；要改变 workspace 定义，应编辑命中的 `.mcp.json` / `.github/mcp.json`。`/mcp add` 保存后会在当前会话立即启动 server，无需重启。插件提供的 server 随插件安装 / 卸载而变；`--additional-mcp-config` 只活在本次进程。

**`github-mcp-server` 官方例子（本机 Docker）**：Copilot CLI 已内置 GitHub MCP；如果只想使用 GitHub 工具，无需再安装，在活动会话运行 `/mcp show github-mcp-server` 即可检查。明确要另接本机容器版时，GitHub 官方文档给出的非交互例子是：

```bash
copilot mcp add github --env GITHUB_PERSONAL_ACCESS_TOKEN=YOUR_GITHUB_PAT -- docker run -i --rm -e GITHUB_PERSONAL_ACCESS_TOKEN ghcr.io/github/github-mcp-server
copilot mcp get github
```

这会新增 config key `github`，与内置的 `github-mcp-server` 分开。GitHub 网页示例当前把选项写成 `-e`，但 1810 的 Copilot CLI `1.0.81-9` 实测报 `unknown option '-e'`；上面改用该版本支持的 `--env`。它的值会写入用户配置，只放最小权限 PAT，且不要提交该配置。完整说明见 [`github/github-mcp-server` 的 Copilot CLI 安装指南](https://github.com/github/github-mcp-server/blob/main/docs/installation-guides/install-copilot-cli.md)。

> 依据：[GitHub 官方 MCP 文档](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers)与[加载优先级](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference#mcp-server-loading-priority)（2026-08-26 核）；1810 实测 Copilot CLI `1.0.81-9` 的 `copilot mcp --help`、`list --help` 与 `get --help`。更细的 walk-up 与历史版本行为见 [Copilot CLI 配置发现](copilot-discovery.md)。

### Claude Code

Claude Code 有三个用户可选 scope：local 和 user 都存在 `~/.claude.json`，但 local 挂在当前项目路径下；project 存在项目根 `.mcp.json`。同名 server 不做字段级合并，而是整项选最高优先级来源：

1. local；
2. project；
3. user；
4. plugin；
5. claude.ai connector。

`claude mcp list` 会对获准 server 做健康检查，并把项目配置中尚未批准的条目标成 pending approval；`claude mcp get <name>` 给单项详情，运行中的 `/mcp` 还能显示工具数和连接状态。WebSocket server 不出现在 `claude mcp list`，需用 `get` 或 `/mcp` 检查。

`claude mcp add --scope <scope>` 和 `remove --scope <scope>` 修改对应来源；不写 `--scope` 时 add 默认 local，remove 会查找该项所在 scope。插件 MCP 写在插件根 `.mcp.json` 或 `plugin.json`，应通过插件安装 / 卸载管理；`/mcp` 的 toggle 只记录当前项目的启停选择，不删除定义。项目 `.mcp.json` 改动后若审批状态干扰验证，可用 `claude mcp reset-project-choices` 重置该项目的选择。

**`github-mcp-server` 官方例子（本机 Docker + OAuth）**：上游当前优先给出无需预先创建 PAT 的 OAuth 命令；在目标项目目录的普通终端运行：

```bash
claude mcp add github -e GITHUB_OAUTH_CALLBACK_PORT=8085 -- docker run -i --rm -p 127.0.0.1:8085:8085 -e GITHUB_OAUTH_CALLBACK_PORT ghcr.io/github/github-mcp-server
claude mcp get github
```

第一条把本机 Docker 进程注册为 `github`；server 首次启动时走浏览器登录，回调端口只绑定 loopback。默认 scope 是当前项目的 local；要跨项目使用，再按需加 `--scope user`。PAT 版本和无 Docker 的 binary 版本见 [`github/github-mcp-server` 的 Claude 安装指南](https://github.com/github/github-mcp-server/blob/main/docs/installation-guides/install-claude.md)。

> 依据：[Claude Code MCP 官方文档](https://code.claude.com/docs/en/mcp)（2026-08-26 核）；1810 实测 Claude Code `2.1.202` 的 `claude mcp --help` 与 `list --help`。Claude Code 闭源，scope 合并和 WebSocket 枚举边界按官方文档记录。

### Codex

Codex 把 MCP 放在普通 TOML 配置层的 `[mcp_servers.<key>]` 下。日常可见的来源是用户级 `${CODEX_HOME}/config.toml`、受信任项目的 `.codex/config.toml`、运行时 `-c key=value` 覆盖和插件 manifest；系统层位于 Linux / macOS 的 `/etc/codex/config.toml` 或 Windows 的 `%ProgramData%\OpenAI\Codex\config.toml`，企业配置还能提供或约束条目。项目层未获 trust 时会被发现但禁用。

当前开源 loader 还会读取 `${PWD}/config.toml`，并沿父目录查找 `.codex/config.toml`，再纳入 git root 的 `.codex/config.toml`；项目层整体高于用户层，运行时覆盖最高。TOML 层递归合并，所以只检查 `~/.codex/config.toml` 不能代表当前 cwd 的最终 MCP 集合。

`codex mcp list` / `get` 读取当前 cwd 的合并配置，并纳入插件提供的 server；默认表格给出 transport、启用和认证状态，但不会启动 STDIO server，也不是连接健康检查。`--json` 还会原样带出配置里的 `env`、`http_headers` 等字段，可能含凭据，不能未经清理直接贴进日志或对话。核验分两步：先在目标 cwd 运行 `codex mcp list` 看有效配置，再在新建或重启后的 TUI / IDE 里用 `/mcp` 看实际初始化状态。

`codex mcp add` / `remove` 当前只改用户级 `${CODEX_HOME}/config.toml`；项目级 server 要直接编辑项目 `.codex/config.toml`。插件 manifest 决定 transport，用户 TOML 只在 `[plugins."<plugin-id>".mcp_servers.<server>]` 下覆盖 enabled 和工具策略。桌面端或 IDE 从设置页保存后要按界面提示 Restart。

**`github-mcp-server` 官方例子**：上游给出的 Codex shell 命令连接 GitHub 托管的 HTTP server；启动 Codex 前须让 `GITHUB_PAT_TOKEN` 在其环境中可见：

```bash
codex mcp add github --url https://api.githubcopilot.com/mcp/ --bearer-token-env-var GITHUB_PAT_TOKEN
codex mcp get github
```

这不是本机 server。上游给本机 Docker 版提供的是 TOML 配置，没有另列等价的 `codex mcp add` 命令：

```toml
[mcp_servers.github]
command = "docker"
args = ["run", "-i", "--rm", "-p", "127.0.0.1:8085:8085", "-e", "GITHUB_OAUTH_CALLBACK_PORT", "ghcr.io/github/github-mcp-server"]
env = { GITHUB_OAUTH_CALLBACK_PORT = "8085" }
```

保存后重启 Codex，再用 `/mcp` 看连接和工具。完整说明见 [`github/github-mcp-server` 的 Codex 安装指南](https://github.com/github/github-mcp-server/blob/main/docs/installation-guides/install-codex.md)。

> 依据：[OpenAI MCP 官方文档](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)；`openai/codex@4ef836f` 的[配置层发现](https://github.com/openai/codex/blob/4ef836f883c38ba6d39e6920f335ce6452b7de33/codex-rs/config/src/loader/mod.rs#L103-L121)、[MCP 子命令与参数](https://github.com/openai/codex/blob/4ef836f883c38ba6d39e6920f335ce6452b7de33/codex-rs/cli/src/mcp_cmd.rs#L46-L98)、[list 的枚举边界](https://github.com/openai/codex/blob/4ef836f883c38ba6d39e6920f335ce6452b7de33/codex-rs/cli/src/mcp_cmd.rs#L627-L700)及[用户级写入](https://github.com/openai/codex/blob/4ef836f883c38ba6d39e6920f335ce6452b7de33/codex-rs/cli/src/mcp_cmd.rs#L349-L441)；1810 实测 Codex CLI `0.149.1`。

### Gemini CLI

Gemini CLI 把 server 定义放在各层 `settings.json` 的 `mcpServers`。持久配置从低到高是系统 defaults、用户 `~/.gemini/settings.json`、项目根 `.gemini/settings.json`、系统 override；Linux 的两个系统文件分别是 `/etc/gemini-cli/system-defaults.json` 和 `/etc/gemini-cli/settings.json`，Windows / macOS 使用官方文档列出的平台目录。同名 server 由更高层定义覆盖。Extension 也能提供 MCP，本地 settings 可覆盖其标量和环境字段，工具 allow / deny 列表按“更严格者生效”的规则合并。

`gemini mcp list` 会连接并显示所有有效 server 的配置摘要与状态；未受信任目录里的 STDIO server 不做连接测试，会显示 Disconnected。交互态 `/mcp list` 列 server / 工具，`desc` 加描述，`schema` 加参数 schema。

`gemini mcp add` 默认写项目 `.gemini/settings.json`，`--scope user` 改写用户文件；`remove` 同样按 scope 删除。持久 enable / disable 状态另存 `~/.gemini/mcp-server-enablement.json`，`--session` 才是不落盘的临时开关。手改 settings 后用 `/mcp reload` 重启 server 并重新发现工具；若改的是要求 restart 的全局 `mcp.allowed` / `mcp.excluded` 策略，则重启 CLI。

**`github-mcp-server` 官方例子**：上游对 Gemini CLI 的推荐入口是安装仓库自带 extension：

```bash
gemini extensions install https://github.com/github/github-mcp-server
```

该方式连接 GitHub 托管的 server，并要求环境或 `~/.gemini/.env` 中存在 `GITHUB_MCP_PAT`。若明确要本机 Docker 版，上游没有给 `gemini mcp add` 命令，而是要求把 Docker `command` / `args` 写进 `~/.gemini/settings.json`；见 [`github/github-mcp-server` 的 Gemini CLI 安装指南](https://github.com/github/github-mcp-server/blob/main/docs/installation-guides/install-gemini-cli.md)。

> 依据：[Gemini CLI MCP 官方文档](https://geminicli.com/docs/tools/mcp-server/)与[配置层文档](https://geminicli.com/docs/reference/configuration/)（2026-08-26 核）。1810 未安装 Gemini CLI，本节未做 live 验证；命令、路径和 trust 行为按官方文档记录。

### Cursor

Cursor Editor 与 Cursor CLI 共用 MCP 配置。用户级文件是 `~/.cursor/mcp.json`，项目配置是各目录的 `.cursor/mcp.json`；CLI 会从当前目录向父目录发现配置。Marketplace / plugin、团队分发和 Extension API 还可能动态提供 server，因此文件扫描不是完整清单。

`agent mcp list` 显示 server 名、连接状态、配置来源和 transport，`agent mcp list-tools <identifier>` 显示某台 server 的工具与参数；交互态 `/mcp list` 使用同一界面。当前 `agent mcp` 没有 add / remove：新增、改 transport 或删除定义要编辑 `mcp.json`，或在 Cursor 的 Customize 页面操作。`agent mcp enable` / `disable` 改的是本机批准 / 禁用状态，不改 JSON 定义。

Cursor CLI 文档把配置优先级概括为“project → global → nested”，同时说会自动发现父目录，但没有公开同名 server 横跨多个父目录时的字段合并算法。遇到重名时，以 `agent mcp list` 显示的 configuration source 和实际状态为准，不从文件顺序反推。手改文件后至少用新进程运行 `agent mcp list`；官方没有承诺当前会话热重载配置。更新自定义 server 的实现文件后，官方要求重启 Cursor。

**`github-mcp-server` 官方例子（本机 Docker + OAuth）**：Cursor CLI 没有 `agent mcp add`；上游安装指南要求把下面的 server 项写入 `~/.cursor/mcp.json`，保存后重启 Cursor：

```json
{
  "mcpServers": {
    "github": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-p", "127.0.0.1:8085:8085",
        "-e", "GITHUB_OAUTH_CALLBACK_PORT",
        "ghcr.io/github/github-mcp-server"
      ],
      "env": { "GITHUB_OAUTH_CALLBACK_PORT": "8085" }
    }
  }
}
```

随后用 `agent mcp list-tools github` 验证。PAT 和托管 HTTP 版本见 [`github/github-mcp-server` 的 Cursor 安装指南](https://github.com/github/github-mcp-server/blob/main/docs/installation-guides/install-cursor.md)。

> 依据：[Cursor MCP 配置文档](https://cursor.com/docs/mcp)与[Cursor CLI MCP 文档](https://cursor.com/docs/cli/mcp)（2026-08-26 核）；1810 实测 Cursor CLI `2026.08.11-e8db854` 的 `agent mcp --help`。Cursor 闭源，父目录重名合并的未公开部分保持未定。

---

## Copilot CLI

**验证方法**：live 实测（Copilot CLI 1.0.69）。`~/.copilot/mcp-config.json` 注册了 5 个
server，直接读该 session 里 CLI 暴露给模型的 MCP 工具清单，比对 config key 与最终工具名。
闭源 SEA 二进制（本机 `~/.local/bin/copilot` 是 ~150MB Node SEA，无散装 `app.js`），故以
**运行时观测**为准，不做字节级逆向——观测本身即首选验证法（live server + inspect exposed
工具名），比读混淆 bundle 更硬。

**格式：`<config-key>-<tool-name>`，分隔符是连字符 `-`，无 `mcp` 字面标记。**

本机某 session 实测样例（5 个 server 全部命中同一规律）：

| config key（`mcpServers` 下） | server 内部声明名 | 原始工具名 | 模型可见名 |
|---|---|---|---|
| `portal` | `portal-mcp-server`（FastMCP 名） | `portal_exec` | `portal-portal_exec` |
| `github-mcp-server` | —（HTTP） | `get_me` | `github-mcp-server-get_me` |
| `codex-image` | — | `codex-reply` | `codex-image-codex-reply` |

要点：

- **前缀 = config key，不是 server 声明名**。`portal` 那行最能说明问题：server 自己
  `FastMCP("portal-mcp-server")`，若用声明名前缀应是 `portal-mcp-server-portal_exec`；实测
  是 `portal-portal_exec` → 用的是配置 key `portal`。
- **无净化、原样拼接 → 分隔符不可逆**。key `codex-image` ＋ tool `codex-reply` 直接拼成
  `codex-image-codex-reply`；`_` 和 `-` 在 key、tool 两侧都**逐字保留**，不转义。于是光看
  最终名**无法机器切回** (key, tool)——`codex-image-codex-reply` 从哪切都合法。（客户端内部
  靠已知 key 集合反查，不是靠切分。）
- **无 `mcp` 家族字面前缀**（区别于 Claude/Codex/Gemini）——就 `key` ＋ `-` ＋ `tool`。
- **未见截断**：本 session 最长 `github-mcp-server-add_reply_to_pull_request_comment`
  ≈ 51 字符，未触发截断（OpenAI/Anthropic 侧工具名史上限 64）。>64 的行为本 session 无样本，
  未知。
- **`portal_` stutter 实锤**：`portal-portal_exec` 就是"客户端加的 server 前缀"叠"工具名
  自带的 server 前缀"，正是驱动 portal `portal_`→`remote_` 改名的现象。

---

## Claude Code

**验证方法**：官方文档逐字（`code.claude.com/docs`，2026-07 核）＋ 行为观测佐证。闭源 /
minified，模型"看到"这串名字属**文档 + 行为观测**（hook 按 `tool_name` 触发、权限对话显示
该名、`allowedTools` 按该名门控），非源码级——高置信但标 doc-derived / observed。

**格式：`mcp__<serverName>__<toolName>`，`mcp` 字面前缀 ＋ 两处双下划线 `__`。**

- **分隔符 `__`（双下划线）**：`mcp` 与 server 名之间、server 名与 tool 名之间都是 `__`。
  官方 [Agent SDK MCP 页](https://code.claude.com/docs/en/agent-sdk/mcp) 原文 "MCP tools
  follow the naming pattern `mcp__<server-name>__<tool-name>`"，例 `github` server 的
  `list_issues` → `mcp__github__list_issues`。
- **前缀取 config key**：[custom-tools 页](https://code.claude.com/docs/en/agent-sdk/custom-tools)
  明写 "The key in `mcpServers` becomes the `{server_name}` segment"；
  [permissions 页](https://code.claude.com/docs/en/permissions) "server name **as configured
  in Claude Code**"。即 `claude mcp add <name> …` 的 `<name>` 或 `.mcp.json` / `~/.claude.json`
  里 `mcpServers` 的 key——不是握手声明名。置信度高。
- **净化 / 长度**：Anthropic API 侧工具名硬约束 `^[a-zA-Z0-9_-]{1,64}$`
  （[define-tools](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools)）→
  拼好的全名须 ≤64 字符，`mcp__…__` 本身吃掉 7 字符。server key 里的 `-`、`_` 官方例子里
  **原样保留**（`mcp__brave-search__…`）。**普通 server 的非法字符净化规则文档未覆盖**（gap）；
  **plugin 打包的 server 才有明文净化**（[mcp 页 plugin 段](https://code.claude.com/docs/en/mcp)）：
  `mcp__plugin_<plugin>_<server>__<tool>`，"任何 `[A-Za-z0-9_-]` 之外的字符替换为 `_`"
  （注意 plugin 段内用单 `_`，仅外层用 `__`）。
- **权限接口即间接实锤**：`allowedTools` / `--disallowedTools` / `permissions` 全按该前缀名
  操作——`mcp__github__*`（整台 server）、`mcp__github__create_issue`（单个）、`mcp__*`
  （所有 MCP 工具）。这套 glob 只在字面 `mcp__<server>__` 前缀后才接受通配。
- 注意：`mcp__server__tool`（双下划线）是 **Claude Code / Agent SDK 专属**；直连 Messages
  API / Agent Skills 那套用 `ServerName:tool_name`（冒号）——别混（官方 issue
  [anthropics/claude-code#18763](https://github.com/anthropics/claude-code/issues/18763)
  确认过这处文档不一致）。

---

## Codex

**验证方法**：真开源 [`openai/codex`](https://github.com/openai/codex)（Apache-2.0，Rust
`codex-rs/`）。下列链接锁到 commit
[`927004c0`](https://github.com/openai/codex/tree/927004c06dc55565af17f0bc8eeb5e35fb990351)
（本篇核对时的 `main` 头），行号已在该 SHA 上逐一核实、点开即到。

**格式：`mcp__{server_key}__{tool_name}`，默认开。**Codex 走 OpenAI **Responses API 的
namespace 机制**——注册一个名为 `mcp__{key}` 的 namespace 对象、内含名为 `{tool}` 的
function，API 侧合成 `mcp__{key}__{tool}` 呈现给模型，回调时把两段**作为独立字段**返回。

- **分隔符 `__`**：常量
  [`MCP_TOOL_NAME_DELIMITER: &str = "__"` (mcp/mod.rs#L53-L55)](https://github.com/openai/codex/blob/927004c06dc55565af17f0bc8eeb5e35fb990351/codex-rs/codex-mcp/src/mcp/mod.rs#L53-L55)
  （同处 `MCP_TOOL_NAME_PREFIX: &str = "mcp"`），另在
  [tools.rs#L260-L261](https://github.com/openai/codex/blob/927004c06dc55565af17f0bc8eeb5e35fb990351/codex-rs/codex-mcp/src/tools.rs#L260-L261)
  与 [handlers/mcp.rs#L29-L30](https://github.com/openai/codex/blob/927004c06dc55565af17f0bc8eeb5e35fb990351/codex-rs/core/src/tools/handlers/mcp.rs#L29-L30)
  重复定义；字面前缀 `LEGACY_MCP_TOOL_NAME_PREFIX = "mcp__"`。装配函数
  [`qualified_mcp_tool_name_prefix` (mod.rs#L71)](https://github.com/openai/codex/blob/927004c06dc55565af17f0bc8eeb5e35fb990351/codex-rs/codex-mcp/src/mcp/mod.rs#L71)。
- **前缀取 config key**：
  [`callable_namespace: server_name.to_string()` (rmcp_client.rs#L755-L756)](https://github.com/openai/codex/blob/927004c06dc55565af17f0bc8eeb5e35fb990351/codex-rs/codex-mcp/src/rmcp_client.rs#L755-L756)——`server_name`
  是按 `[mcp_servers.<KEY>]` 表键传入的**配置 key**，非握手声明名。
- **默认前缀开关**：
  [`prefix_mcp_tool_names()` (config/mod.rs#L1618-L1619)](https://github.com/openai/codex/blob/927004c06dc55565af17f0bc8eeb5e35fb990351/codex-rs/core/src/config/mod.rs#L1618-L1619)
  = `!features.enabled(NonPrefixedMcpToolNames)`，该
  [feature (features/lib.rs#L166)](https://github.com/openai/codex/blob/927004c06dc55565af17f0bc8eeb5e35fb990351/codex-rs/features/src/lib.rs#L166)
  默认 **off** → 默认带 `mcp__`。即便打开它，也只去掉 `mcp__` 字面（见
  [`callable_namespace_with_prefix` (tools.rs#L311-L316)](https://github.com/openai/codex/blob/927004c06dc55565af17f0bc8eeb5e35fb990351/codex-rs/codex-mcp/src/tools.rs#L311-L316)），
  namespace 仍是 `{server_key}`，全名变 `{server_key}__{tool}`——**server key 前缀永远在**，
  只是 `mcp__` 标记可选。
- **净化**：
  [`sanitize_responses_api_tool_name` (mod.rs#L441)](https://github.com/openai/codex/blob/927004c06dc55565af17f0bc8eeb5e35fb990351/codex-rs/codex-mcp/src/mcp/mod.rs#L441)
  把**非 `[A-Za-z0-9_]` 一律替 `_`**——注意注释说 API 允许 `-`，但代码只放行
  `is_ascii_alphanumeric() || c == '_'`，**连字符也被替成 `_`**（单测钉死：`"Some-Server"` →
  `"Some_Server"`，且不小写化）。
- **长度 / 截断**：
  [`MAX_TOOL_NAME_LENGTH: usize = 64` (tools.rs#L261)](https://github.com/openai/codex/blob/927004c06dc55565af17f0bc8eeb5e35fb990351/codex-rs/codex-mcp/src/tools.rs#L261)。
  `namespace + "__" + tool ≤ 64`（[`unique_callable_parts` #L372](https://github.com/openai/codex/blob/927004c06dc55565af17f0bc8eeb5e35fb990351/codex-rs/codex-mcp/src/tools.rs#L372)）；
  超长或撞名 → **截断后接 12 位 SHA1 hash 后缀**
  （[`fit_callable_parts_with_hash` #L352](https://github.com/openai/codex/blob/927004c06dc55565af17f0bc8eeb5e35fb990351/codex-rs/codex-mcp/src/tools.rs#L352)，
  hash 源含 `server_name\0namespace\0connector_id\0callable_name\0tool.name` 保证稳定唯一）。
- **反向映射无字符串切分**：Responses API 直接回 `{namespace, name}` 两字段，
  [handlers/mcp.rs#L53](https://github.com/openai/codex/blob/927004c06dc55565af17f0bc8eeb5e35fb990351/codex-rs/core/src/tools/handlers/mcp.rs#L53)
  仅用 `{namespace}__{name}` 重建限定名做注册表匹配；`mcp__` 前缀与净化纯表现层，实际发往 MCP
  server 的仍是**原始 config key ＋ 原始 tool 名**。

---

## Gemini CLI

**验证方法**：真开源 [`google-gemini/gemini-cli`](https://github.com/google-gemini/gemini-cli)
（TypeScript）。链接锁到 commit
[`b31b755b`](https://github.com/google-gemini/gemini-cli/tree/b31b755bbf89303159f03a36fbb899c6f7e57511)
（本篇核对时的头），行号已核实。

**格式：`mcp_<serverConfigKey>_<toolName>`，总是命名空间化（无"撞名才加"回退）。**

- **常量**：
  [`MCP_QUALIFIED_NAME_SEPARATOR = '_'` (mcp-tool.ts#L32)](https://github.com/google-gemini/gemini-cli/blob/b31b755bbf89303159f03a36fbb899c6f7e57511/packages/core/src/tools/mcp-tool.ts#L32)、
  [`MCP_TOOL_PREFIX = 'mcp_'` (#L37)](https://github.com/google-gemini/gemini-cli/blob/b31b755bbf89303159f03a36fbb899c6f7e57511/packages/core/src/tools/mcp-tool.ts#L37)。
  `DiscoveredMCPTool` 构造器无条件对
  [`` `${serverName}_${serverToolName}` `` (#L184)](https://github.com/google-gemini/gemini-cli/blob/b31b755bbf89303159f03a36fbb899c6f7e57511/packages/core/src/tools/mcp-tool.ts#L184)
  调 `generateValidName`；装配函数
  [`formatMcpToolName` (#L82-L93)](https://github.com/google-gemini/gemini-cli/blob/b31b755bbf89303159f03a36fbb899c6f7e57511/packages/core/src/tools/mcp-tool.ts#L82-L93)
  返回 `` `${MCP_TOOL_PREFIX}${serverName}_${toolName}` ``。单测钉死模型可见名
  `mcp_my-server_my-tool`。
- **前缀取 config key**：
  [`discoverMcpTools` 里 `Object.entries(mcpServers)` (mcp-client.ts#L1115)](https://github.com/google-gemini/gemini-cli/blob/b31b755bbf89303159f03a36fbb899c6f7e57511/packages/core/src/tools/mcp-client.ts#L1115)
  的 **key**（`mcpServerName`）一路传到
  [`new DiscoveredMCPTool` (#L1369)](https://github.com/google-gemini/gemini-cli/blob/b31b755bbf89303159f03a36fbb899c6f7e57511/packages/core/src/tools/mcp-client.ts#L1369)。
  非握手声明名。（特例：`--mcpServerCommand` 起的 server 硬编码 key `'mcp'`。）
- **净化 / 长度**（[`generateValidName` (mcp-tool.ts#L593)](https://github.com/google-gemini/gemini-cli/blob/b31b755bbf89303159f03a36fbb899c6f7e57511/packages/core/src/tools/mcp-tool.ts#L593)）：
  [`MAX_FUNCTION_NAME_LENGTH = 64` (#L590)](https://github.com/google-gemini/gemini-cli/blob/b31b755bbf89303159f03a36fbb899c6f7e57511/packages/core/src/tools/mcp-tool.ts#L590)；
  ①确保 `mcp_` 前缀；②`replace(/[^a-zA-Z0-9_\-.:]/g, '_')`——**允许 `-`、`.`、`:`**，其余替
  `_`（比 Codex 宽）；③首字符须字母或 `_`，否则补 `_`；④超
  [`safeLimit = 64-1 = 63` (#L608)](https://github.com/google-gemini/gemini-cli/blob/b31b755bbf89303159f03a36fbb899c6f7e57511/packages/core/src/tools/mcp-tool.ts#L608)
  → `first30 + '...' + last30` 截成恰好 63。
- **坑**：[`parseMcpToolName` (#L54)](https://github.com/google-gemini/gemini-cli/blob/b31b755bbf89303159f03a36fbb899c6f7e57511/packages/core/src/tools/mcp-tool.ts#L54)
  用 `^([^_]+)_(.+)$` 切——取 `mcp_` 之后**第一个 `_` 前**为 server 名。config key 若含 `_`
  （`my_server`）会被切错 → 执行不受影响（注册表按全名查），但按 `mcp_server_*` 写的策略通配
  会失配。
- **wire 上用原始名**：命名空间名只给 LLM 看；实际调 MCP server 发的是裸 `serverToolName`
  （见 [mcp-tool.ts](https://github.com/google-gemini/gemini-cli/blob/b31b755bbf89303159f03a36fbb899c6f7e57511/packages/core/src/tools/mcp-tool.ts)
  的 `DiscoveredMCPToolInvocation.execute()`）。

---

## Cursor

**验证方法**：闭源，无源码。以官方文档（`cursor.com/docs`，2026-07 核）为准，逐条标证据级别；
分隔符仅有单个官方样例支撑，标注为**推断**。

**格式：`<config-key>-<tool-name>`，连字符 `-`，无 `mcp` 字面标记（文档口径 + 单例推断）。**

- **加前缀（文档口径）**：[Cloud Agent capabilities](https://cursor.com/docs/cloud-agent/capabilities)
  原文 "Depending on your MCP client, tool names may include a server prefix (for example,
  `cursor-cloud-run-info`)"，底层裸工具是 `run-info` 等。
- **分隔符 `-`（单例推断）**：server `cursor-cloud` ＋ tool `run-info` → `cursor-cloud-run-info`
  → 推断 `<key>-<tool>`，无 `mcp` 字面标记。**仅此一例**，第二例未在公开文档找到；且该拼名
  同样 `-` 不可逆切分（key、tool 两侧都含 `-`），Cursor 内部应按已知 server 名反查。
- **前缀取 config key（明文）**：[permissions 参考页](https://cursor.com/docs/reference/permissions)
  "The server name is the key you used in `mcp.json` (e.g. `"github"`, `"linear"`)"。但注意：
  allowlist 用 `server:tool`（**冒号**，大小写不敏感），与呈给模型的 function 声明名
  `server-tool`（连字符）是**两套表示**——冒号形态不合 `^[a-zA-Z0-9_-]{1,64}$`，不可能是
  function 名。[hooks](https://cursor.com/docs/hooks) matcher 另用 `MCP:<tool_name>`。
- **净化 / 长度**：公开文档**未覆盖**（gap）。
- **历史"~40 工具上限"**：当前文档未见；只说调用次数无限。[未证实 / 历史]

---

## 横向综合

**结构上分两派**（都取 config key、都加前缀，差在装饰）：

- **裸 `<key><分隔><tool>`、无 `mcp` 标记**：Copilot（`-`）、Cursor（`-`）。分隔符与名字里的字符
  同形 → 最终名**不可机器逆切**，靠已知 key 集合反查。
- **带 `mcp` 家族字面标记**：Claude Code / Codex（`mcp__…__`，双下划线，更强的分隔、撞的概率低）、
  Gemini（`mcp_…_`，单下划线，key 含 `_` 时反切会错）。

**净化 / 长度光谱**（松→紧）：Copilot / Cursor（观测：不净化 / 未文档化）< Claude Code（靠 API
64 字符正则，普通 server 净化未文档化，plugin 才明文净化）< Gemini（允许 `-.:`，余替 `_`，
63 截断 `首30…尾30`）< Codex（连 `-` 都替 `_`，64 上限，超长 SHA1 hash 截断）。上限锚点都在 64
（OpenAI / Anthropic / Vertex 三家 API 工具名史上限一致）。

**对『工具名要不要自带 server 名前缀』的取舍**：不要。五家客户端都已按 config key 命名
空间化，工具名再自带一个 server 名就是 stutter（`portal` server 的 `portal_exec` →
`portal-portal_exec` / `mcp__portal__portal_exec` / `mcp_portal_portal_exec`）。

- 想**防撞、且自描述**：加一个**语义**词干（描述工具"干什么"）比加"server 名"更值——语义前缀在
  裸拼派（Copilot / Cursor）那种不可逆、模型只看一坨扁平串的场景下，帮模型理解；而 server 名那层
  客户端已经免费给了。
- **一台 server 内部的 meta / 杂项工具**（注册表、策略 dry-run、本地日志之类）**不需要**再叠
  server 名前缀：客户端的 `<key>-`／`mcp__<key>__` 已经把它和别家 server 的同名工具隔开了；
  同 server 内工具名本就唯一。裸名或**贴合各自语义**的词干即可，别硬套一个统一 server 前缀
  （尤其别给"本地"语义的工具套 "remote" 这种会误导的前缀）。

（portal 具体应用：`portal_exec`→`remote_exec` 后各客户端呈现 `portal-remote_exec` /
`mcp__portal__remote_exec` / `mcp_portal_remote_exec`，stutter 消除、`remote_` 语义自描述保留；
`host`/`check`/`audit`/`close_shell`/`local_exec` 这些非"远程执行"语义的 meta 工具可裸名或按各自
语义命名，不必强加 `remote_`/`portal_`。）
