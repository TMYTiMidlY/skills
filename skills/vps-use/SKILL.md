---
name: vps-use
description: 通过 SSH 远程操作 VPS 服务器。用户提到在某个服务器/VPS/机器上做任何操作（配置、安装、检查、调试等）时触发。
---

# VPS 远程操作

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

需要 sudo 的命令无法通过 ssh 非交互执行。将命令写入本地 `/tmp` 下的脚本，scp 到服务器，然后提示用户执行 `sudo bash /tmp/<script>.sh`。

脚本开头加 `exec > >(tee /tmp/<name>.log) 2>&1`，用户看终端的同时留下日志；跑完 agent 自己 `scp` 拉回读，不要让用户手贴。

### 复杂文件修改

当需要做非平凡的文件编辑时，不要尝试通过 ssh 内联 sed/awk，而是：

1. 复制到本地临时目录：`scp <name>:/remote/path/file /tmp/file`
2. 在本地用 Read/Edit 工具修改
3. 复制回远程：`scp /tmp/file <name>:/remote/path/file`

对于简单的追加或单行替换，可以直接 ssh 执行。

### 多用户共享服务的端口分配

如果一个 systemd 服务需要为多个用户各跑一份实例，可以用模板单元（`@` service）。在 `ExecStart` 中用用户 UID 动态计算端口避免冲突。

**先用 `id -u <主用户>` 查 UID 作为偏移基准**，不要想当然填 1000——部分发行版/镜像的首个普通用户 UID 是 1001 或其他值。查到之后把它填进下面公式的偏移项：

```ini
[Unit]
Description=MyService for %i

[Service]
User=%i
ExecStart=/bin/sh -c 'exec /usr/bin/myservice --port $((BASE_PORT + $(id -u %i) - <主用户 UID>))'
```

其中 `BASE_PORT` 替换为实际的基准端口号，`%i` 是实例名（即用户名）。启用方式：`systemctl enable --now myservice@username`。

## 用户名规则

参考文档中的 `<USERNAME>` 需要替换为实际用户名。确定方式：

- 如果用户明确指定了用户名，使用指定的
- 如果当前用户是 `MY.Tan` 或 `timidly`，默认使用 `timidly`
- 其他情况询问用户

## 重要原则

严格按照参考文档中写明的步骤执行。如果文档中没有写某个操作的具体流程，先询问用户意见，不要自行发挥。

## 配置新 VPS

有两种 setup，如果用户没有明确指定，需要询问：

- **base-setup**：基础安全配置（防火墙、用户、SSH加固），初始化时需完成全部流程 → [references/base-setup.md](references/base-setup.md)
- **extra-setup**：额外安装，必须先完成 base-setup。包含以下内容，各项之间无依赖，按需安装 → [references/extra-setup.md](references/extra-setup.md)
  - SSH 密钥 passphrase 与 ssh-agent：密钥安全与免密缓存（本地机器配置）
  - SSH RemoteForward 代理转发：将本地代理端口暴露到 VPS
  - BBR 拥塞控制：改善网络吞吐
  - EasyTier：虚拟组网，支持 P2P / 中继 / 出口节点模式
  - Caddy：反向代理，含 caddy-security 扩展和 GitHub OAuth 配置
  - error-pages：自定义错误页面服务，配合 Caddy 使用

## 质量检测

网络与 IP 质量评估，以及历史服务器信息与费用对比 → [references/quality-check.md](references/quality-check.md)

- 带宽测试（iperf3）、延迟测试（mtr）
- IP/DNS/WebRTC 泄漏检测（browserleaks.com）
- IP 风险评估（ping0.cc）、多节点延迟（itdog.cn）
- 历史服务器记录：DigitalOcean / RackNerd / LisaHost / EdgeNAT 的配置、费用与测试数据
