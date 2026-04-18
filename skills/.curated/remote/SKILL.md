---
name: remote
description: 通过 SSH 远程操作已知 VPS/服务器/远程机器时使用；负责连接确认、远程命令执行、sudo 脚本上传、复杂文件修改等操作规范。
---

# Remote

## 核心操作模式

### 确认目标服务器

用户说"在XX上操作"时，先去 `~/.ssh/config` 找是否有匹配的 Host 别名。如果找不到，**不要继续操作**，直接问用户：是不是名字说错了、是不是想表达别的意思、还是需要先添加 SSH 配置。确认了才能往下走。

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

### 执行远程命令

通过 `ssh <name> <command>` 执行远程操作，`<name>` 是 `~/.ssh/config` 中的 Host 别名。

需要 sudo 的命令，将命令写入本地 `/tmp` 下的脚本，scp 到服务器，然后通过 `ssh -t <name> "sudo bash /tmp/<script>.sh"` 执行（`-t` 强制分配伪终端，使 sudo 能正常读取密码）。

脚本开头加 `exec > >(tee /tmp/<name>.log) 2>&1`，用户看终端的同时留下日志；跑完 agent 自己 `scp` 拉回读，不要让用户手贴。

### 复杂文件修改

当需要做非平凡的文件编辑时，不要尝试通过 ssh 内联 sed/awk，而是：

1. 复制到本地临时目录：`scp <name>:/remote/path/file /tmp/file`
2. 在本地用 Read/Edit 工具修改
3. 复制回远程：`scp /tmp/file <name>:/remote/path/file`

对于简单的追加或单行替换，可以直接 ssh 执行。

## 边界

VPS 初始化、新服务器配置、Caddy/EasyTier/BBR/error-pages 安装、网络质量检测等服务器维护内容由 `vps-maintenance` skill 维护。
