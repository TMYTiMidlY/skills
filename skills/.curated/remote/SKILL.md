---
name: remote
description: 当用户要在远端 SSH 主机上做任何操作（读/改文件、跑命令等）时唯一入口。管控模式选择与安全规则，禁止绕过本 skill 直接调用 portal_* MCP 工具。
---

# Remote

远端 SSH 主机的统一入口。本 skill 只走 portal MCP 这一条通道，强制安全约束、给出可复用的工作流。**禁止**绕过本 skill 直接调用 `portal_*` 工具。

## 通道：portal MCP

[`portal-mcp-server`](https://github.com/TMYTiMidlY/portal-mcp-server) 是个 MCP server——MCP client（Copilot CLI / Claude Code / Cursor / VS Code 等）启动时把它当子进程拉起，agent 通过 stdio 调用它暴露的 `portal_*` 工具。底层 SSH 引擎是 [asyncssh](https://github.com/ronf/asyncssh)（纯 Python 实现 SSHv2 协议），连接池放在自己进程内存里：所有工具共享同一条 TCP，第一次连接 ~200–500ms（auth dominated），之后每次调用 ~10–30ms（只开 channel）。带 hash-protected 文件编辑、跨调用粘性的 `bash -i`、SFTP、隧道、多机编排。

裸 `ssh` / `scp` 的通用知识（主机密钥 / known_hosts / `CheckHostIP` 与 asyncssh 等库对 IP 的处理差异、ControlMaster 连接复用、交互式 sudo、scp 编辑回写等）不在本 skill——见 `software` skill 的 SSH 章节。

## 何时触发

用户提到远端 / SSH / 服务器 / VPS / host 上的任何操作——"在 `<host>` 上 ..."、"远端 ..."、"去服务器 ..." 等。

## 入口流程

### 1. 确认 host

查 `~/.ssh/config` 找 Host 别名。找不到就停下来问用户：名字错了？还是需要先加 SSH 配置？

### 2. 确认 portal 可用

当前工具列表里有 `portal_*`（如 `portal_read`）就直接用。没有 → 按下面"安装缺失"处理。

### 2.1 安装缺失

安装 `portal-mcp-server` 时，先确认用户使用的 MCP host（Codex / Claude Code / Copilot CLI / Cursor / VS Code / Claude Desktop 等）和安装范围（当前项目级 / 用户全局级）。具体配置、包来源、命令参数、环境变量写法都以 [`portal-mcp-server` 官方 README](https://github.com/TMYTiMidlY/portal-mcp-server#%E6%8E%A5%E5%85%A5%E6%96%B9%E5%BC%8F) 的“接入方式 / Client integration”和“配置”章节为准；不要在本 skill 里硬编码，也不要凭旧记忆拼写。缺少 host、scope、`SSH_HOSTS_YAML` / `SSH_POLICIES_YAML` / `SSH_MCP_LOG_DIR` 等路径时先问用户。server key 建议保持 `portal`，因为它决定工具命名空间（如 Codex / Claude Code 的 `mcp__portal__portal_read`、Copilot CLI 的 `portal-portal_read`）。安装后通常要重启 MCP client / 新开会话再验证，已启动的 Codex / Claude / Copilot 会话一般不会热加载新 server。

### 3. 远端操作只走 portal_*（核心规则）

远端读写 / 跑命令一律用 `portal_*` 工具，**不要**在 bash 里用 `ssh` / `scp` 做同样的事——那会绕开 portal 的 hash 并发校验（`portal_patch` 的"写前先 read"门票）。portal 覆盖不了、必须裸 ssh 的少数场景（见 `software` skill 的 SSH 章节）属例外，但别和 portal 对同一文件混用。

---

## portal MCP 用法

### 关键不变量（理解后再用）

- **写之前必须先 read**：`portal_read` 返回 whole-file `file_hash`（SHA-256）和每段 `range_hash`；`portal_patch` 必须带回。中途别人改了文件，patch 会被服务端拒绝并返回 `current_file_hash`，远端文件原样不动。
- **patch 是事务的**：一次 `patches_json` 内多段全成或全败；服务端按 `start` 倒序 sort 后从下到上应用（避免行号漂移），紧接着检测 overlap（每个 upper.start 必须 > lower.end），任何 overlap 直接拒。写入走 `<path>.mcp_tmp.<12hex>` + `posix_rename` 原子替换，写完再 hash 校验一遍。
- **bash session 粘性**：第一次 `portal_bash` 自动建一个 `bash -i`，cwd / export / venv 跨调用保留；想清空 `portal_bash_close`。PTY echo + bracketed-paste + PS1/PS2/PROMPT_COMMAND 关掉以让 sentinel 完整工作；返回的 `output` 已 strip 掉残留 ANSI。**不返回 exit code**——需要的话自己 `; echo $?`。
- **文件 IO 与 bash 共用同一 SSH 连接**：asyncssh 进程内连接池每 host 最多 5 条 TCP，所有 `portal_*` 工具调用复用，不会因为多工具就开多条 TCP。
- **跨平台一致**：portal-mcp-server 不依赖 OS 级 `ControlMaster`（asyncssh 是纯 Python，pool 就是 dict），Windows 上和 Linux 同样的复用性能——这正是选 portal MCP 而非裸 ssh 的核心理由之一。
- **`~/.ssh/config` 别名自动解析**：第一次 `get_connection("<alias>")` 找不到注册时自动从 `~/.ssh/config` 读 HostName / User / Port / IdentityFile / ProxyJump，不需要重复登记。

### 工具分类与选用思想

18 个 `portal_*` 按职责分这几族。具体参数 / 返回字段不背——agent 看到的工具描述里都有；这里只讲**该用哪族**。

**核心 8（首选）**：

- **文件 IO**（`portal_read` / `portal_patch` / `portal_cleanup_tmps`）—— 远端文本编辑唯一入口。`read` 拿到的 `file_hash` + `range_hash` 是 `patch` 的"门票"，缺了就拒；中断后留下的 `*.mcp_tmp.*` 用 `cleanup_tmps` 收。**绝对不用 bash 里的 `cat > / sed -i / tee` 替代**——绕开 hash 即丢并发安全模型。
- **结构化搜索**（`portal_grep` / `portal_glob`）—— 首次连接探测一次 `rg` / `find` 是否在并缓存。`grep` 是 rg 优先 / `grep -rn` 兜底；`glob` 是 `rg --files | rg <pat>` 优先 / pattern 里含 `* ? [` 切 `find` / 无 rg 退纯 `find`。先在远端定位 `file:line`，再走文件 IO 族；不要 `portal_bash command="rg ..."` 这样跑——结构化输出（`{file,line,text}` / `{files[]}`）的好处就丢了。
- **粘性 shell**（`portal_bash` / `portal_bash_close` / `portal_bash_status`）—— 一个 host 共享一个 `bash -i`，cwd / env / venv 跨调用保留。设计上**一个 `portal_bash` 替代了上游 `ssh-shell-mcp` 的 ~20 个 thin-wrapper**（`ssh_ps` / `ssh_df` / `ssh_journalctl` / `ssh_docker` / `ssh_tmux_*` 等），不要去找"专门的 systemctl 工具"——直接 `portal_bash` 跑命令就行。

**高层 10**（按场景出场，**不**统一靠 mode 字段——只有 `portal_host` / `portal_transfer` / `portal_tunnel_open` / `portal_multi_exec` / `portal_audit` 这 5 个用 `action` / `direction` / `mode` / `view` 切语义；其它 5 个是普通定参工具）：

- **多机命令**：`portal_multi_exec`（`mode=parallel|rolling|broadcast`）—— 上百台并发的唯一正确入口。`hosts_json=[...]` 显式列表只需 `~/.ssh/config` 别名能解析；用 `group_tag=...` 按标签则**必须**先 `portal_host` 注册并打 tag（ssh config 别名拿不到 tag）。
- **结构化剧本**：`portal_playbook` —— 多步骤序列，按步过 policy gate，`on_error` 控制中止逻辑。**单机 (`host=...`) 和多机 (`group_tag=...`) 都支持**；比手写多次 `portal_bash` 多一层结构化保障，单机有需求也可以用。
- **二进制 / 整目录传输**：`portal_transfer`（`direction=upload|download|sync`）—— SFTP，`portal_patch` 不适用的所有场景（二进制、整目录、非文本）走它。
- **SSH 隧道**：`portal_tunnel_open`（`mode=local|reverse|socks`）+ `portal_tunnel_close` + `portal_tunnel_list` —— 端口转发 / 反向 / SOCKS5；用完记得 close。
- **健康 / 策略 / 审计**：`portal_ping`（单机或全 fleet 体检，无 host 参数则 ping 所有已注册主机）、`portal_check`（policy dry-run，只判不执行；默认 policy PERMISSIVE，返回 ALLOWED 不代表"安全"）、`portal_audit`（`view=snapshot|history|stats|policy` 四视图，看服务器内部状态）。
- **主机注册**：`portal_host`（`action=list|register|remove`）—— 只在需要打 tag 给 `multi_exec(group_tag=)` / `playbook(group_tag=)` 用时才登记；纯 ssh 别名走 `~/.ssh/config` 即可，不用注册。

**两条选用反射**：
1. 改远端文件 → `portal_read` → `portal_patch`，永远不要在 bash 里覆盖。
2. 跑远端命令 → 默认 `portal_bash`；多机才升级 `portal_multi_exec`；多步且要 policy 守关 / `on_error` 行为则用 `portal_playbook`（单机也可以）。

### 安全规则（强制）

1. **默认只可写远端 `/tmp/` 路径**。改用户家目录、项目代码目录、`/etc`、`/usr` 等任何非 `/tmp` 位置之前，**必须先问用户**并明确得到许可。server 端不强制——靠本 skill 在 prompt 层守住。
2. 真实项目目录上做实验，先建议复制到 `/tmp/<task-name>/` 沙箱，确认无误后让用户决定是否合并回真实路径。
3. patch 失败（hash mismatch）后**不要立刻覆盖式重试**——先 `portal_read` 看新 hash 和新内容，识别是不是别的 agent / 用户在并发改；是的话向用户汇报并等指示。
4. `portal_bash` cwd 是粘性的——执行任何命令前先 `pwd` 确认，不要假定还在上次目录（被 timeout 关 / 用户在另一会话里 close 都会重置）。
5. **改文件优先用 `portal_patch`**（带 hash 校验）；只在 portal_patch 不适用时（二进制、整目录、非文本）才用 `portal_transfer`。**绝对不要在 `portal_bash` 里用 `cat > file` / `sed -i` / `tee` 等命令直接覆盖远端文件**——这绕开了并发安全模型，多 agent 场景下会丢改动。
6. 默认 policy 是 PERMISSIVE（host_allowlist / command_blocklist 都空，只有 per-host rate limit）——`portal_check` 返回 ALLOWED 只代表"没规则拦"，不代表"安全"。机器级强制要在 `config/policies.yaml` 加 `command_blocklist` 规则。

---

## 边界

- **VPS 初始化 / Caddy / EasyTier / BBR / error-pages**：交给 `vps-maintenance` skill。
- **多机 fleet 编排**（上百台并发）：用 `portal_multi_exec(mode="parallel")` 或 `portal_playbook(group_tag=...)`。
- **需要 sudo 又想自动化**：让用户先跑 `sudo true` 续命计时器（短时间内 portal 可用 `sudo -n`）。裸 ssh 下交互式 sudo 的老式做法（`ssh -t` + 本地脚本 + scp）见 `software` skill 的 SSH 章节。

---

## 维护参考（claim → portal-mcp-server 源）

仅供未来重构时复核 portal MCP 相关说法用，不需要 agent 在每次调用时关注。

| 说法 | 来源 |
|---|---|
| 18 个 portal_* 工具 / 8 core + 10 高层划分 | [`README.md`](https://github.com/TMYTiMidlY/portal-mcp-server/blob/main/README.md) §"Why 18 tools instead of 70+"；`portal_mcp_server/cli.py:130-731`（`@mcp.tool` 装饰器逐个数得出） |
| asyncssh 纯 Python、无 OS socket 依赖 | `README.md` §"Why asyncssh"；`connection_manager.py:12, 282`（`asyncssh.connect`） |
| 进程内连接池每 host 最多 5 条 TCP | `connection_manager.py:60`（`pool_size: int = 5`） |
| `~/.ssh/config` 别名自动解析 | `connection_manager.py:213+`（`_lookup_ssh_config_alias`），`README.md:55` |
| Win OpenSSH 不支持 ControlMaster → Win 上 MCP 优势 | `README.md` §"Why MCP > plain ssh on Windows" |
| 第一次 ~200–500ms / 后续 ~10–30ms/次 | `README.md` §"SSH Connection Reuse Performance" 表与 100 次 echo pong 测试 |
| `portal_read` 返回 `content / file_hash / range_hash / total_lines` | `cli.py:566-583`，`remote_text_editor.py:272-273` |
| `portal_patch` hash 校验 + tmp + posix_rename | `remote_text_editor.py:14-24, 125-154`；`SECURITY.md` §"References & Algorithmic Provenance" |
| patch 倒序应用 + overlap 检测 | `remote_text_editor.py:10-13, 340-352` |
| `portal_bash` 返回 `{host, session_id, output}`，**无 exit_code** | `remote_bash.py:19, 112` |
| sentinel + PTY echo / PS1 / bracketed-paste 静音 | `remote_bash.py:8-16, 73-75` |
| 默认 policy 为 PERMISSIVE | `cli.py:477-485`（`portal_check` docstring） |
| `portal_bash` 走 `_gate(host, command)` 也过 blocklist | `cli.py:714` |
| 整体设计：8 core hash-protected + 10 mode-switching | `README.md:11`（attribution + 设计 diff） |
