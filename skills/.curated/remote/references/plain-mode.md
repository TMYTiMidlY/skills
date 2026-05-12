# Plain 模式（sudo 与兜底）

> ⛔ **模式隔离**：进入 Plain 模式后，**禁止调用任何 portal MCP 工具**——包括 `portal_read`、`portal_patch`、`portal_bash`、`portal_transfer`、`portal_multi_exec` 等所有 `portal_*` 工具。所有远端操作只通过 bash 的 `ssh` / `scp` 完成。

> ⚠️ **Windows 兼容性差**：Windows OpenSSH 不支持 `ControlMaster`（依赖 Unix domain socket），plain 模式每次 `ssh host cmd` 都是新 TCP+auth（~300ms/次）。**Win 上强烈建议改用 MCP 模式**（asyncssh 进程内连接池跨平台一致）。

适用场景：交互式 sudo（弹密码）；改其它用户家目录文件；portal-mcp-server 未注册到当前项目。正常情况优先走 MCP 模式（参见 `mcp-mode.md`）。

## 前置检查

每次开始远端操作前：

1. 确认 `SSH_AUTH_SOCK` 已设置（某些环境不会 source `~/.bashrc`）：

```bash
[ -z "$SSH_AUTH_SOCK" ] && export SSH_AUTH_SOCK=/run/user/$(id -u)/ssh-agent.socket
```

2. 在 Linux / macOS / WSL 上确认本地 SSH config 有 `ControlMaster`（Win 跳过这步——上面已说明）：

```bash
grep -q "ControlMaster" ~/.ssh/config && echo "OK" || echo "MISSING"
```

缺失时提醒用户在 `~/.ssh/config` 的 `Host *` 下添加：

```text
Host *
    ControlMaster auto
    ControlPath ~/.ssh/sockets/%r@%h-%p
    ControlPersist 10m
```

## 执行远端命令（无 sudo）

```bash
ssh <name> "<command>"
```

## 需要 sudo 的命令（核心场景）

agent 在本地 `/tmp/` 写脚本，自己 `scp` 上传，**只让用户**执行最终的 `ssh -t`：

```bash
ssh -t <name> "sudo bash /tmp/<script>.sh"
```

`-t` 强制分配伪终端，使 sudo 能正常读取密码。**不要让用户跑 `scp`**——上传脚本、上传临时文件、拉取日志这些准备动作都该 agent 做。

脚本开头加 `exec > >(tee /tmp/<name>.log) 2>&1`，用户看终端的同时留下日志；跑完 agent 自己 `scp` 拉回读，不要让用户手贴。

## 复杂文件修改（无法用 MCP 时）

需要做非平凡编辑时**不要**通过 ssh 内联 sed/awk，而是：

1. 复制到本地临时目录：`scp <name>:/remote/path/file /tmp/file`
2. 在本地用 view/edit 工具修改
3. 复制回远程：`scp /tmp/file <name>:/remote/path/file`

简单的追加或单行替换可以直接 ssh 执行。

> 这套流程现在主要给 "MCP 还没注册" 或 "目标在别的用户家目录" 等场景兜底；正常情况下走 MCP 模式的 `portal_read` + `portal_patch` 比这个安全也方便。
