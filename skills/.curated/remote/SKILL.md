---
name: remote
description: 当用户要在远端 SSH 主机上做任何操作（读/改文件、跑命令等）时唯一入口。管控模式选择与安全规则，禁止绕过本 skill 直接调用 portal_* MCP 工具。
---

# Remote

## 何时触发

用户提到远端 / SSH / 服务器 / VPS / host 上的任何操作——"在 `<host>` 上 ..."、"远端 ..."、"去服务器 ..." 等。**禁止**直接调用 `portal_*` 工具，必须先走本 skill。

## 入口流程

### 1. 确认 host

查 `~/.ssh/config` 找 Host 别名。找不到就停下来问用户：名字错了？还是需要先加 SSH 配置？

### 2. 选模式

默认走 **MCP**。以下情况走 **Plain**：

- 需要交互式 sudo（弹密码）
- 目标文件属于其他用户或需要 root 权限
- portal MCP 工具不可用（当前工具列表里没有 `portal_read` 等）→ 按 [references/install.md](references/install.md) 引导安装

### 3. 模式隔离（核心规则）

选定模式后**只用该模式的工具**，不可混用：

| 模式 | 允许 | 禁止 |
|---|---|---|
| MCP | 18 个 `portal_*` 工具（read / patch / grep / glob / bash / bash_close / bash_status / cleanup_tmps + transfer / tunnel_open / tunnel_close / tunnel_list / multi_exec / playbook / host / ping / audit / check） | bash 里的 ssh/scp 做远端操作 |
| Plain | bash 里的 `ssh` / `scp` | **所有** `portal_*` MCP 工具 |

混用会破坏安全模型：MCP 的 hash 并发校验被绕过，或 plain 的 sudo 流程被打断。

## 模式详情

- **MCP 模式**（默认）→ [references/mcp-mode.md](references/mcp-mode.md)
  核心：18 个 portal_* 工具速查（8 core + 10 高层）；写前必读拿 hash；patch 事务性；bash session cwd 有粘性。**首次使用前必读。**
- **Plain 模式**（兜底）→ [references/plain-mode.md](references/plain-mode.md)
  核心：agent 准备脚本和文件，sudo 让用户执行 `ssh -t`。Win 上 plain 模式无 ControlMaster，性能差。

## 边界

- **VPS 初始化 / Caddy / EasyTier / BBR / error-pages**：交给 `vps-maintenance` skill。
- **多机 fleet 编排**（上百台并发）：用 `portal_multi_exec(mode="parallel")` 或 `portal_playbook(group_tag=...)`。
- **需要 sudo 又想自动化**：让用户先跑 `sudo true` 续命计时器（5 分钟内 MCP 可用 `sudo -n`），否则走 Plain。
