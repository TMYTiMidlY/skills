# Codex 云端应用连接与本地 GitHub 身份

## <a id="shared-chatgpt-github-connector"></a>共享 ChatGPT 订阅下的 GitHub Connector 身份归属排查

> 2026-11 实测；Linux 多用户开发机，Codex CLI `0.170.0`；通过本机 rollout 事件流、进程环境与认证状态只读取证。本文使用匿名占位符：两个独立 Linux 系统用户分别记为 `<user-a>`（操作者 A）与 `<user-b>`（协作者 B），仓库记为 `<org>/<repo>`，云端连接标识记为 `link_<id>` 与 `connector_<id>`。

### <a id="symptom-split-identity"></a>Git 提交与 GitHub 操作的身份记录

同一台 Linux 开发机上有两个独立的系统用户 `<user-a>` 与 `<user-b>`，各自拥有独立的家目录、Git 身份配置与 GitHub CLI（`gh`）登录凭据。协作期间，远端仓库 `<org>/<repo>` 陆续出现一组身份归属矛盾的单据与合并记录：

- 针对 `<user-b>` 在途开发分支发起的子 PR、CI 通过后的自动合并以及关联新建 Issue，在 GitHub 平台上的创建者（`user.login`）与合并执行者（`merged_by`）全部显示为 `<user-a>`。
- 点开这批 PR 的提交记录，所有 Git commit 的 `author` 与 `committer` 姓名、邮箱却全部是 `<user-b>`；从本地产生提交到远端开出附带 `<user-b>` 本地校验输出的 PR 仅隔二三十秒，CI 变绿后十余秒即完成合并。
- 操作者 A 最初怀疑是自己名下某个后台会话越界修改了 `<user-b>` 的分支；但在 `<user-b>` 终端现场执行 `gh auth status` 与 `gh api user --jq .login`，返回的又是完全正常的 `<user-b>` 自身账号，且 `<user-b>` 同期创建的另一些 PR 身份也正常显示为 `<user-b>`。

### <a id="detours-and-falsification"></a>本地会话与凭据排查

#### <a id="detour-operator-runaway-session"></a>操作者 A 的后台会话

第一反应是排查 `<user-a>` 本机是否有遗留的无人值守会话在后台轮询并操作 `<user-b>` 的分支。全量检索 `/home/<user-a>/.codex/sessions` 等本地会话存档与存活进程后，虽定位到了 `<user-a>` 另一终端窗格正常发起的主线 PR，但发往 `<user-b>` 在途分支的那批子 PR、合并动作与新建 Issue 在 `<user-a>` 的全部会话日志中均为 **0 命中**。

Git 提交由 `<user-b>` 本机产生后约 30 秒即开出 PR，PR 描述也带有 `<user-b>` 本地环境的校验输出。排查据此转向 `<user-b>` 的工作环境，随后从会话日志确认请求来源。

#### <a id="detour-local-gh-env"></a>协作者 B 的 `gh` 凭据与环境变量

第二层假设是 `<user-b>` 的终端或守护进程通过 `GH_TOKEN`、`GITHUB_TOKEN` 或 `GH_CONFIG_DIR` 使用了 `<user-a>` 的凭据。核查时经授权只读检查 `/home/<user-b>/.config/gh/hosts.yml`、Git 凭据配置和 `<user-b>` 存活进程的 `/proc/<pid>/environ`，报告仅记录变量是否存在及凭据比对结果。

- `/home/<user-b>/.config/gh/hosts.yml` 中仅存有 `<user-b>` 自己的令牌；
- 所有存活进程环境中均无 `GH_TOKEN`、`GITHUB_TOKEN` 或 `GH_CONFIG_DIR` 覆盖。

`gh auth status` 与 `gh api user --jq .login` 核实的是本地 `gh` 的账号。要确认涉事操作具体走哪条路径，还需查看该操作的调用记录。

### <a id="rollout-and-auth-evidence"></a>rollout 工具调用与 ChatGPT 账户标识

转向检索 `/home/<user-b>/.codex/sessions/` 下的会话记录 `rollout-*.jsonl`，直接定位到涉事单据的真实调用事件：这批建单与合并并非本地 shell 命令，而是由模型发起的内置 `McpToolCall` 调用：

- 服务名：`codex_apps`（应用 `GitHub`）
- 实际调用的工具名：
  - `mcp__codex_apps__github_create_pull_request`
  - `mcp__codex_apps__github_merge_pull_request`
  - `mcp__codex_apps__github_create_issue`
- 调用元数据统一指向同一条云端授权连接：`link_<id>`（`connector_<id>`）。

随后在内存中只读比对 `/home/<user-a>/.codex/auth.json` 与 `/home/<user-b>/.codex/auth.json` 中的 `account_id` 及用户 ID 哈希，两者逐字节完全一致。

> Codex CLI `0.170.0` 默认启用 `apps`。启用时，非隔离会话会注册 `codex_apps` MCP 服务，通过 ChatGPT 认证访问云端 `/ps/mcp`。本案的本地取证范围是 `auth.json` 中的 ChatGPT 账户标识和 rollout 中的云端连接标识。见 [`apps` 的默认设置](https://github.com/openai/codex/blob/rust-v0.170.0/codex-rs/features/src/lib.rs#L1723-L1728)、[`codex_apps` 注册条件](https://github.com/openai/codex/blob/rust-v0.170.0/codex-rs/core/src/mcp.rs#L500-L523)和 [`/ps/mcp` 的端点与认证配置](https://github.com/openai/codex/blob/rust-v0.170.0/codex-rs/codex-mcp/src/mcp/mod.rs#L674-L706)。

### <a id="dual-channel-routing"></a>本地 GitHub CLI 与云端连接的凭据来源

`<user-a>` 与 `<user-b>` 在各自独立的 Linux 账户下共用了同一个 ChatGPT 订阅账号登录 Codex CLI，而该 ChatGPT 账号此前已在 OpenAI 云端绑定了 `<user-a>` 的个人 GitHub Connector。由此导致 `<user-b>` 的同一个 Codex 会话内部并存两条身份不同的执行通道：

| 操作路径 | 触发方式 | 实际使用的凭据来源 | GitHub 记录的操作者 |
| --- | --- | --- | --- |
| 本地 `gh` CLI | 模型通过本地 shell 执行 `gh pr create` | `<user-b>` 的本地 `gh` 凭据 | `<user-b>` |
| 云端 `codex_apps` GitHub 工具 | 模型直接调用 `mcp__codex_apps__github_*` 内置工具 | OpenAI 服务端托管的共享 ChatGPT 账号云端连接 `link_<id>` | `<user-a>` |

`git commit` 单独记录本地 Git 配置中的作者与提交者。在本案中，模型先在 `<user-b>` 的环境中提交代码，再用云端工具创建和合并 PR，因此 Git 提交与 GitHub 操作分别记录了两个账号。

### <a id="remediation-and-isolation"></a>GitHub 连接撤销与 Codex 会话隔离

按是否需要停用共享账号的连接，以及是否继续共用 ChatGPT 账号选择处置方式。

1. **撤销共享账号的 GitHub 连接**
   经共享账号和连接的管理者授权，在 ChatGPT 网页端进入 `Settings → Apps`，选择 `GitHub` 并执行 `Disconnect`。也可由 `<user-a>` 在 GitHub 的 `Settings → Applications → Authorized GitHub Apps` 撤销对应的账号授权。确认连接已断开后，如需核对存量会话，用只读查询检查该连接是否仍可访问。若仍可访问，先停用该会话中的 GitHub 写操作并复查连接。见 [GitHub 应用授权的查看和撤销](https://docs.github.com/en/apps/using-github-apps/reviewing-and-revoking-authorization-of-github-apps)。

   > 影响范围：云端连接按 ChatGPT 账号维度绑定，断开操作会同步影响同一 ChatGPT 账号下其他仍依赖该云端 GitHub 连接的会话。

2. **为协作者 B 禁用 Codex 云端应用**
   由 `<user-b>` 在本次会话使用的 Codex 配置中更新 `[features]` 表，保留配置文件原有的属主和访问权限。本案使用 `/home/<user-b>/.codex/config.toml`。见 [`features.apps` 配置定义](https://github.com/openai/codex/blob/rust-v0.170.0/codex-rs/core/config.schema.json#L7887-L7921)。

   ```toml
   [features]
   apps = false
   ```

   单次命令行启动也可显式传入 `--disable apps`。写入配置后，在 `<user-b>` 环境下执行以下命令核实特性状态已变为 `false`：

   ```bash
   codex features list
   ```

   重开会话后，确认工具列表中已无 `codex_apps`，再运行 `gh api user --jq .login` 核对本地 `gh` 的账号。两项均符合预期后，通过本地 `gh` 执行已获授权的 GitHub 操作。若结果有出入，先核对会话实际加载的配置和 `gh` 登录状态。

   > 生效时机：已启动的 `codex app-server` 守护进程与存量终端会话在启动阶段已完成工具列表装配，修改 `config.toml` 后须重开会话（或重启对应的 `app-server` 进程）才会对模型工具路由生效。若双方无需共享订阅席位，为 `<user-b>` 配置独立的 `CODEX_HOME` 登录各自的 ChatGPT 账号即可从源头解耦。
