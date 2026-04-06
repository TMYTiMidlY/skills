---
name: vps-use
description: 通过 SSH 远程操作 VPS 服务器。当用户提到"在服务器上"、"在某台机器上操作"、"初始化 VPS"、"配置服务器"时触发。
---

# VPS 远程操作

## 核心操作模式

### 执行远程命令

通过 `ssh <name> <command>` 执行远程操作，`<name>` 是 `~/.ssh/config` 中的 Host 别名。

需要 sudo 的命令无法通过 ssh 非交互执行，此时直接给出要在服务器上运行的命令，让用户手动执行。

### 复杂文件修改

当需要做非平凡的文件编辑时，不要尝试通过 ssh 内联 sed/awk，而是：

1. 复制到本地临时目录：`scp <name>:/remote/path/file /tmp/file`
2. 在本地用 Read/Edit 工具修改
3. 复制回远程：`scp /tmp/file <name>:/remote/path/file`

对于简单的追加或单行替换，可以直接 ssh 执行。

### 前置检查

每次开始远程操作前：

1. 确认 `SSH_AUTH_SOCK` 已设置（某些环境不会 source `~/.bashrc`）：

```bash
[ -z "$SSH_AUTH_SOCK" ] && export SSH_AUTH_SOCK=/run/user/$(id -u)/ssh-agent.socket
```

2. 确认本地 SSH config 包含连接复用配置（ControlMaster）：

```bash
grep -q "ControlMaster" ~/.ssh/config && echo "OK" || echo "MISSING: 需要配置 SSH 复用"
```

如果缺失，提醒用户在 `~/.ssh/config` 的 `Host *` 下添加：

```
Host *
    ControlMaster auto
    ControlPath ~/.ssh/sockets/%r@%h-%p
    ControlPersist 10m
```

## 配置新 VPS

有两种 setup，如果用户没有明确指定，需要询问：

- **base-setup**：基础安全配置（防火墙、用户、SSH加固）→ [references/base-setup.md](references/base-setup.md)
- **extra-setup**：额外安装（ssh-agent、各种服务等），必须先完成 base-setup → [references/extra-setup.md](references/extra-setup.md)
