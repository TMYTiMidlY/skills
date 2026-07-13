# MCP 工具名如何暴露给模型：五家客户端横向对照

一个 MCP server 声明了工具 `foo`，客户端把它塞进模型可见的 tool 列表时，是原样叫
`foo`，还是加 server 名做命名空间（`<server>-foo` / `<server>__foo` /
`mcp__<server>__foo` …）？本篇只聚焦 **tool-name 的前缀 / 命名空间化**：分隔符是什么、
前缀串从哪来（客户端 MCP 配置里的 **server key** vs server 自己在 `initialize` 握手里
声明的 name）、碰撞行为、截断 / 净化（sanitize）规则，以及其它 MCP 暴露层的坑。

**为什么这事要紧**：常有人给 MCP 工具名硬加 server 名当前缀（`portal_exec` /
`myserver_search`），理由是"防撞名"。但如果客户端**本来就**按 server 命名空间化，那这个
自加前缀就是纯 **stutter（口吃）**——`portal` server 的 `portal_exec` 在客户端里会变成
`portal-portal_exec` / `mcp__portal__portal_exec`。到底撞不撞、要不要自带前缀，取决于**每家
客户端是否已经加、以及前缀取自哪里**。下面把五家逐一核实。

## 五家一致：都加 server 前缀、取自 config key

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

## 准确度约定（本篇遵循 harness skill 惯例）

- **Codex**、**Gemini CLI**：真开源 → 每条行为都给**官方源码 file:line ＋ 常量原文**，附
  commit/HEAD。可直接照抄核实。
- **Copilot CLI**、**Claude Code**、**Cursor**：闭源 / minified 分发 → 行为**不能**当源码
  级事实陈述。每条标注**验证方法**（live MCP server 实测 exposed 工具名 / 官方文档逐字 /
  社区观测）并就地标不确定度。引用前自己再核。

---

## Copilot CLI —— `<key>-<tool>`，连字符，取 config key

**验证方法**：live 实测。Copilot CLI 1.0.69，`~/.copilot/mcp-config.json` 里注册了 5 个
server，直接读 CLI 暴露给模型的工具注册表（tool-search / 工具清单）比对 key 与 tool 名。
闭源 SEA 二进制（本机 `~/.local/bin/copilot` 是 ~150MB Node SEA，无散装 `app.js`），故以
**运行时观测**为准，不做字节级逆向——观测本身即 harness 约定认可的首选验证法
（"live MCP server + inspect exposed tool names"）。

**格式：`<config-key>-<tool-name>`，分隔符是连字符 `-`，无 `mcp` 字面标记。**

实测对照（同一 session，5 个 server 全部命中同一规律）：

| config key（`mcpServers` 下） | server 内部声明名 | 原始工具名 | 模型可见名 |
|---|---|---|---|
| `portal` | `portal-mcp-server`（FastMCP 名） | `portal_exec` | `portal-portal_exec` |
| `github-mcp-server` | —（HTTP） | `get_me` | `github-mcp-server-get_me` |
| `gitea` | — | `list_my_repos` | `gitea-list_my_repos` |
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

## Claude Code —— `mcp__<key>__<tool>`，双下划线，取 config key

**验证方法**：官方文档逐字（`code.claude.com/docs`）＋ 社区观测佐证。Claude Code 闭源 /
minified，模型确实"看到"这串名字属**文档 + 行为观测**（hook 按 `tool_name` 触发、权限对话
显示该名、`allowedTools` 按该名门控），非源码级——高置信但标注为 doc-derived / observed。

**格式：`mcp__<serverName>__<toolName>`，`mcp` 字面前缀 ＋ 两处双下划线 `__`。**

- **分隔符 `__`（双下划线）**：`mcp` 与 server 名之间、server 名与 tool 名之间都是 `__`。
  官方 Agent SDK MCP 页原文："MCP tools follow the naming pattern
  `mcp__<server-name>__<tool-name>`"，例 `github` server 的 `list_issues` →
  `mcp__github__list_issues`。
- **前缀取 config key**：官方 custom-tools 页明写"The key in `mcpServers` becomes the
  `{server_name}` segment"；permissions 页"server name **as configured in Claude Code**"。
  即 `claude mcp add <name> …` 的 `<name>` 或 `.mcp.json` / `~/.claude.json` 里 `mcpServers`
  的 key——不是握手声明名。置信度高。
- **净化 / 长度**：Anthropic API 侧工具名硬约束
  `^[a-zA-Z0-9_-]{1,64}$`（`platform.claude.com/.../define-tools`）→ 拼好的全名须 ≤64 字符，
  `mcp__…__` 本身吃掉 7 字符。server key 里的 `-`、`_` 官方例子里**原样保留**
  （`mcp__brave-search__…`）。**普通 server 的非法字符净化规则文档未覆盖**（gap）；
  **plugin 打包的 server 才有明文净化**：`mcp__plugin_<plugin>_<server>__<tool>`，
  "任何 `[A-Za-z0-9_-]` 之外的字符替换为 `_`"（注意 plugin 段内用单 `_`，仅外层用 `__`）。
- **权限接口即间接实锤**：`allowedTools` / `--disallowedTools` / `permissions` 全按该前缀名
  操作——`mcp__github__*`（整台 server）、`mcp__github__create_issue`（单个）、`mcp__*`
  （所有 MCP 工具）。这套 glob 只在字面 `mcp__<server>__` 前缀后才接受通配。
- 注意：`mcp__server__tool`（双下划线）是 **Claude Code / Agent SDK 专属**；直连 Messages
  API / Agent Skills 那套用 `ServerName:tool_name`（冒号）——别混（官方 issue #18763 确认过
  这处文档不一致）。

---

## Codex —— `mcp__<key>__<tool>`，双下划线，取 config key（源码级）

**验证方法**：真开源 `openai/codex`（Apache-2.0，Rust `codex-rs/`），下列均为源码 file:line
＋ 常量原文，基线 `main` HEAD `927004c0`（引用前自己再核 SHA，混淆无关、行号会漂）。

**格式：`mcp__{server_key}__{tool_name}`，默认开。**Codex 走 OpenAI **Responses API 的
namespace 机制**——注册一个名为 `mcp__{key}` 的 namespace 对象、内含名为 `{tool}` 的
function，API 侧合成 `mcp__{key}__{tool}` 呈现给模型，回调时把两段**作为独立字段**返回。

- **分隔符 `__`**：三处源文件各自定义同一常量
  `const MCP_TOOL_NAME_DELIMITER: &str = "__";`（`codex-rs/codex-mcp/src/mcp/mod.rs`、
  `codex-rs/codex-mcp/src/tools.rs`、`codex-rs/core/src/tools/handlers/mcp.rs:29-30`），
  字面前缀 `const MCP_TOOL_NAME_PREFIX: &str = "mcp";` / `LEGACY_MCP_TOOL_NAME_PREFIX = "mcp__"`。
- **前缀取 config key**：`codex-rs/codex-mcp/src/rmcp_client.rs` 里
  `callable_namespace: server_name.to_string()`——`server_name` 是
  `McpConnectionManager` 按 `[mcp_servers.<KEY>]` 表键传入的**配置 key**，非握手声明名。
- **默认前缀开关**：`config/mod.rs` 的 `prefix_mcp_tool_names()` = `!Feature::NonPrefixedMcpToolNames`，
  该 feature 默认 **off** → 默认带 `mcp__`。即便打开该 feature，也只去掉 `mcp__` 字面，
  namespace 仍是 `{server_key}`，全名变 `{server_key}__{tool}`——**server key 前缀永远在**，
  只是 `mcp__` 标记可选。（feature 见 `codex-rs/features/src/lib.rs`；引入于 commit `ff7513cd`。）
- **净化**：`sanitize_responses_api_tool_name()`（`codex-mcp/src/mcp/mod.rs`）把
  **非 `[A-Za-z0-9_]` 一律替 `_`**——注意注释说 API 允许 `-`，但代码只放行
  `is_ascii_alphanumeric() || c == '_'`，**连字符也被替成 `_`**（单测钉死：
  `"Some-Server"` → `"Some_Server"`，且不小写化）。
- **长度 / 截断**：`const MAX_TOOL_NAME_LENGTH: usize = 64;`（`tools.rs`）。`namespace + "__" + tool ≤ 64`；超长或撞名 → **截断后接 12 位 SHA1 hash 后缀**（`fit_callable_parts_with_hash`，
  hash 源含 `server_name\0namespace\0connector_id\0callable_name\0tool.name` 保证稳定唯一）。
- **反向映射无字符串切分**：Responses API 直接回 `{namespace, name}` 两字段，
  `router.rs` 组 `ToolName::new(namespace, name)` 进 `ToolRegistry` 查；`mcp__` 前缀与净化纯
  表现层，实际发往 MCP server 的仍是**原始 config key ＋ 原始 tool 名**。

---

## Gemini CLI —— `mcp_<key>_<tool>`，单下划线，取 config key（源码级）

**验证方法**：真开源 `google-gemini/gemini-cli`（TypeScript），下列 file:line ＋ 常量原文，
基线 HEAD `b31b755b`（2026-07 核，行号会漂）。

**格式：`mcp_<serverConfigKey>_<toolName>`，总是命名空间化（无"撞名才加"回退）。**

- **常量**（`packages/core/src/tools/mcp-tool.ts`）：
  `export const MCP_QUALIFIED_NAME_SEPARATOR = '_';`、`export const MCP_TOOL_PREFIX = 'mcp_';`。
  `DiscoveredMCPTool` 构造器无条件
  `` `generateValidName(`${serverName}_${serverToolName}`)` ``，装配函数
  `formatMcpToolName()` 返回 `` `${MCP_TOOL_PREFIX}${serverName}_${toolName}` ``。单测钉死模型
  可见名：`expect(declarations[0].name).toBe('mcp_my-server_my-tool')`
  （`tool-registry.test.ts`）。
- **前缀取 config key**：`mcp-client.ts` 的 `discoverMcpTools()` 用
  `Object.entries(mcpServers)` 的 **key**（`mcpServerName`）传入；`mcp-client-manager.ts` 亦
  按 key 实例化。非握手声明名。（特例：`--mcpServerCommand` 起的 server 硬编码 key `'mcp'`。）
- **净化 / 长度**（`generateValidName()`，同文件）：`MAX_FUNCTION_NAME_LENGTH = 64`；
  ①确保 `mcp_` 前缀；②`replace(/[^a-zA-Z0-9_\-.:]/g, '_')`——**允许 `-`、`.`、`:`**，其余替
  `_`（比 Codex 宽）；③首字符须字母或 `_`，否则补 `_`；④超 63（`64-1` 安全余量）→
  `first30 + '...' + last30` 截成恰好 63。
- **坑**：`parseMcpToolName` 用 `^([^_]+)_(.+)$` 切——取 `mcp_` 之后**第一个 `_` 前**为 server
  名。config key 若含 `_`（`my_server`）会被切错 → 执行不受影响（注册表按全名查），但按
  `mcp_server_*` 写的策略通配会失配。
- **wire 上用原始名**：命名空间名只给 LLM 看；实际调 MCP server 发的是裸 `serverToolName`
  （`DiscoveredMCPToolInvocation.execute()` 里 `name: this.serverToolName`）。

---

## Cursor —— `<key>-<tool>`，连字符，取 config key（闭源，文档口径）

**验证方法**：闭源，无 file:line。以官方文档（`cursor.com/docs`）为准，全部标注证据级别；
分隔符仅有单个官方样例支撑，标注为**推断**。

- **加前缀（文档口径）**：Cloud Agent capabilities 文档原文
  "Depending on your MCP client, tool names may include a server prefix (for example,
  `cursor-cloud-run-info`)"，底层裸工具是 `run-info` 等。[官方文档]
- **分隔符 `-`（单例推断）**：server `cursor-cloud` ＋ tool `run-info` → `cursor-cloud-run-info`
  → 推断格式 `<key>-<tool>`，无 `mcp` 字面标记。**仅此一例**，第二例未在公开文档找到；且该拼名
  同样 `-` 不可逆切分（key、tool 两侧都含 `-`），Cursor 内部应按已知 server 名反查。[推断]
- **前缀取 config key（明文）**：permissions 参考页
  "The server name is the key you used in `mcp.json` (e.g. `"github"`, `"linear"`)"。[官方文档]
  但注意：allowlist 用 `server:tool`（**冒号**，大小写不敏感），与呈给模型的
  function 声明名 `server-tool`（连字符）是**两套表示**——冒号形态不合
  `^[a-zA-Z0-9_-]{1,64}$`，不可能是 function 名。hooks matcher 另用 `MCP:<tool_name>`。
- **净化 / 长度**：公开文档**未覆盖**。[gap]
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
（OpenAI/Anthropic/Vertex 三家 API 工具名史上限一致）。

**对『工具名要不要自带 server 名前缀』的结论**：**不要**。五家客户端都已按 config key 命名
空间化，工具名再自带一个 server 名就是 stutter（`portal` server 的 `portal_exec` →
`portal-portal_exec` / `mcp__portal__portal_exec` / `mcp_portal_portal_exec`）。

- 想**防撞、且自描述**：加一个**语义**词干（描述工具"干什么"）比加"server 名"更值——语义前缀在
  裸拼派（Copilot/Cursor）那种不可逆、模型只看一坨扁平串的场景下，帮模型理解；而 server 名那层
  客户端已经免费给了。
- **一台 server 内部的 meta / 杂项工具**（注册表、策略 dry-run、本地日志之类）**不需要**再叠
  server 名前缀：客户端的 `<key>-`／`mcp__<key>__` 已经把它和别家 server 的同名工具隔开了；
  同 server 内工具名本就唯一。裸名或**贴合各自语义**的词干即可，别硬套一个统一 server 前缀
  （尤其别给"本地"语义的工具套"remote"这种会误导的前缀）。

（portal 具体应用：`portal_exec`→`remote_exec` 后各客户端呈现 `portal-remote_exec` /
`mcp__portal__remote_exec` / `mcp_portal_remote_exec`，stutter 消除、`remote_` 语义自描述保留；
`host`/`check`/`audit`/`close_shell`/`local_exec` 这些非"远程执行"语义的 meta 工具可裸名或按各自
语义命名，不必强加 `remote_`/`portal_`。）

## 来源

- **Copilot CLI**：live 实测，Copilot CLI 1.0.69，`~/.copilot/mcp-config.json` ＋ CLI 暴露工具名
  （2026-07 观测）。闭源 SEA，以运行时观测为准。
- **Claude Code**：`code.claude.com/docs` — `agent-sdk/mcp#tool-naming-convention`、
  `agent-sdk/custom-tools`、`permissions`（§MCP / Tool name wildcards）、`hooks`（Match MCP tools）、
  `mcp#plugin-provided-mcp-servers`；API 约束 `platform.claude.com/.../tool-use/define-tools`
  （`^[a-zA-Z0-9_-]{1,64}$`）。闭源，doc-derived / observed。
- **Codex**：`openai/codex` `main` HEAD `927004c0` — `codex-rs/codex-mcp/src/mcp/mod.rs`
  （`MCP_TOOL_NAME_DELIMITER` / `sanitize_responses_api_tool_name` / `qualified_mcp_tool_name_prefix`）、
  `codex-mcp/src/tools.rs`（`MAX_TOOL_NAME_LENGTH=64` / hash 截断）、
  `codex-mcp/src/rmcp_client.rs`（`callable_namespace=server_name`）、
  `core/src/tools/handlers/mcp.rs:29-30`、`core/src/tools/router.rs`、
  `core/src/config/mod.rs`（`prefix_mcp_tool_names`）、`features/src/lib.rs`
  （`NonPrefixedMcpToolNames`，commit `ff7513cd`）。开源，file:line。
- **Gemini CLI**：`google-gemini/gemini-cli` HEAD `b31b755b` —
  `packages/core/src/tools/mcp-tool.ts`（`MCP_TOOL_PREFIX='mcp_'` / `MCP_QUALIFIED_NAME_SEPARATOR='_'`
  / `generateValidName` / `formatMcpToolName` / `parseMcpToolName`）、
  `packages/core/src/tools/mcp-client.ts`（`Object.entries(mcpServers)`）、
  `mcp-client-manager.ts`、`tool-registry.test.ts`（`mcp_my-server_my-tool`）。开源，file:line。
- **Cursor**：`cursor.com/docs` — `cloud-agent/capabilities`（`cursor-cloud-run-info` 例）、
  `reference/permissions`（"key you used in `mcp.json`"）、`hooks`（`MCP:<tool_name>`）。
  闭源，doc-derived / 单例推断。
