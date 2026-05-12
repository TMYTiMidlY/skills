---
name: remote
description: 在 ~/.ssh/config 已有 Host 别名的远端机器上做读 / 改 / 跑命令时使用。两种模式：MCP 模式（默认，hash 防冲突的 remote_read/remote_patch、远端 ripgrep 的 remote_grep/remote_glob、持久 cwd+env 的 remote_bash）和 Plain 模式（直接 ssh/scp 拼字符串，主要给交互式 sudo 与 ssh-remote-mcp 未注册的环境兜底）。
---

# Remote

## 何时触发

用户说"在 `<host>` 上 ..."、"去远端 ..."、"远端 grep / 改 / 跑 ..."、"在 `<host>` 上装 / 改 / 起服务"等任何操作发生在远端机器的请求。

**先确认 host**：去 `~/.ssh/config` 找匹配的 Host 别名。如果找不到，**不要继续**，直接问用户：是不是名字说错了、是不是想表达别的意思、还是需要先添加 SSH 配置。

## 选模式

| 场景 | 模式 |
|---|---|
| 普通文件读 / 改 / 搜索 / 跑命令 | **MCP** |
| 需要 cwd 在多次命令间保留 | **MCP**（remote_bash 自动持久） |
| 需要并发安全（多 agent / 用户同时改同一文件） | **MCP**（hash 校验） |
| 需要交互式 sudo（弹密码） | **Plain** |
| 装包 / 改 /etc / systemd / 改其他用户的文件 | **Plain**（agent 准备脚本，用户自己跑 `ssh -t`） |
| ssh-remote-mcp 未注册到当前项目 | **Plain** |
| 一次性查个东西、不需要 cwd 持久 | 任意（plain 更轻） |

判断 "MCP 是否可用"：在 cwd 下跑 `copilot mcp list`，看 Workspace servers 里是否有 `ssh-remote`。没有的话先按 [references/install.md](references/install.md) 引导用户安装。

## 各模式详细工作流

- **MCP 模式（默认）**：完整工具速查、关键不变量、5 条强制安全规则、3 个典型工作流见 [references/mcp-mode.md](references/mcp-mode.md)。**第一次用 MCP 模式前必须读一遍**，安全规则错了会污染远端文件。
- **Plain 模式**：前置检查（SSH_AUTH_SOCK、ControlMaster）、sudo 脚本上传与回收、本地↔远端文件搬运策略见 [references/plain-mode.md](references/plain-mode.md)。
- **首次安装 ssh-remote-mcp**：把 `mcp-config.example.json` 拷成项目级 `.mcp.json` 的指引见 [references/install.md](references/install.md)。

## 边界

- **新装服务器 / 配 Caddy / EasyTier / BBR / error-pages**：交给 `vps-maintenance` skill。
- **多机 fleet 编排**（上百台并发）：直接用上游 ssh-shell-mcp 的 `ssh_parallel` / `ssh_rolling`，不在本 skill 范围。
- **真要 sudo 但又想自动化**：要么让用户在自己终端先跑一次 `sudo true` 给 sudo 缓存计时器续命（5 分钟内 MCP 可用 `sudo -n`），要么干脆走 Plain 模式。
