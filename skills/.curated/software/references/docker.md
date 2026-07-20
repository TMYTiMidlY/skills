# Docker（安装 + 多用户共用）

Ubuntu 上装 Docker Engine 的**官方推荐方式**、怎么让多个非 root 用户共用、以及 docker 组的安全取舍。命令据 [docs.docker.com/engine/install/ubuntu](https://docs.docker.com/engine/install/ubuntu/) 与 [linux-postinstall](https://docs.docker.com/engine/install/linux-postinstall/)，版本随文标注（本文实操于 2026-07，Docker Engine 29.6.2 / Ubuntu 24.04）。

## 装哪套：apt 仓库法 vs `get.docker.com` 便捷脚本

Docker 官方给了两条常见路径，**首装生产 / 长期机器优先 apt 仓库法**：

- **apt 仓库法（推荐）**：把 Docker 官方 apt 源加进系统，再 `apt-get install docker-ce …`。好处是后续 `apt upgrade` 跟着官方源升级、版本可控可回滚、与系统包管理一致。
- **便捷脚本 `curl -fsSL https://get.docker.com | sh`**：官方明确说它**只适合快速搭个测试 / 开发环境**、不建议用于生产——非交互、装的组件不完全可控、也不利于审计（= 跑一段未审阅的远程脚本，取舍见 [package-managers.md](package-managers.md) 的 `curl|sh` 一节）。

下面走 apt 仓库法。

## 官方 apt 仓库法（Ubuntu）

**为什么这么写**：新版文档用 **`signed-by` 指定 keyring**（GPG 公钥单独放 `/etc/apt/keyrings/`、只给这一个源背书），取代已废弃的全局 `apt-key`——避免"一个源的 key 能给所有源背书"的问题。仓库行里的 `$(dpkg --print-architecture)`（架构，如 amd64）和 `$(. /etc/os-release && echo "$VERSION_CODENAME")`（发行版代号，如 noble）都动态取，换机器 / 架构不用改。

```bash
# 1) 先卸掉发行版自带的旧包（官方前置步骤；装过 docker.io 之类会冲突。没装也无害，幂等）
for pkg in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do
  sudo apt-get remove -y "$pkg"
done

# 2) 装前置 + 加官方 GPG key（modern keyring 方式）
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# 3) 加仓库（arch + codename 动态取）
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update

# 4) 装 Engine + CLI + containerd + buildx + compose 插件（官方推荐的完整五件套）
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

装完 `docker.service` / `docker.socket` / `containerd.service` 会**自动 enable**（deb 包 postinst 建好 systemd symlink），开机自启。验证：

```bash
sudo systemctl is-enabled docker && sudo systemctl is-active docker   # enabled / active
sudo docker run --rm hello-world                                       # 打印 "Hello from Docker!"
docker compose version && docker buildx version                        # 插件到位
```

> Debian 把源里的 `ubuntu`→`debian` 即可；RHEL/Fedora/CentOS（dnf）、Arch 等各有官方页，套路一样（加官方源 + 装 docker-ce）。

## 多用户共用：docker 组

Docker daemon 以 root 跑，对外只暴露一个 Unix socket `/var/run/docker.sock`，属主 `root:docker`。**只要在 `docker` 组里就能读写这个 socket = 免 sudo 用 docker**。`docker` 组由 docker-ce 包安装时**自动建好**，不用手动 `groupadd`。

```bash
sudo usermod -aG docker <用户名>     # -aG = append 到附加组；别漏 -a，否则会把用户踢出其它附加组
# usermod 一次只认一个登录名，多个用户逐个加：
for u in alice bob; do sudo usermod -aG docker "$u"; done
getent group docker                  # 确认成员：docker:x:<gid>:alice,bob
```

## 组变更何时生效：现有会话要重登，`sg`/`newgrp` 可免登验证

**坑**：`usermod -aG` 改的是**组数据库**（`/etc/group`），但**已登录的会话不会自动更新自己的进程组**——用户当前 shell / SSH 会话是加组*之前*建立的，`id -nG` 里看不到 docker，直接 `docker ps` 会 `permission denied`。

- **正解**：让用户**登出再登录**（或重连 SSH），新登录会话才带上 docker 组。
- **不重登临时激活**：`newgrp docker`（开个带新组的子 shell）或 `sg docker -c "命令"`（**s**witch **g**roup，只给这一条命令拿 docker 当活动组）。二者都直接读组数据库，所以*当前会话*也能立刻用——**同时也是不重登、验证"加组是否生效"的手段**：

```bash
# 以目标用户身份、不重登，验证非 root 能否摸到 socket：
sg docker -c "docker version"                 # 能打印 Server 版本即通
sg docker -c "docker run --rm hello-world"
```

区分两个 `id`：`id -nG <user>` 查的是组**数据库**（加完组立刻显示 docker，但不代表当前会话已生效）；`id -nG`（无参、查当前进程）才反映**当前会话**的真实组——两者不一致就说明"库里加了、会话还没生效、需重登"。

## 安全：进 docker 组 ≈ 免密 root（重要取舍）

**docker 组权限等价 root。** daemon 以 root 跑，组内用户能直接：

```bash
docker run -v /:/host -it alpine chroot /host   # 把宿主根挂进容器，秒变宿主 root
```

无需 sudo、无需密码、也不留 sudo 审计。Docker 官方 post-install 页明确写了 "the `docker` group grants root-level privileges"。

**所以：**
- **可信开发机 / 单人或小团队工作站**：加 docker 组是官方文档里的标准便利做法，普遍且合理。
- **给本来就是 sudoer 的用户加**：不提升权限上限（他们本就能拿 root），风险不变。
- **给非 sudoer 加 = 变相发 root**：多租户 / 生产 / 不完全信任的用户要谨慎。更严格的替代——
  - **Rootless Docker**（daemon 以普通用户跑，隔离最好）；
  - **保留 `sudo docker`**（有密码门 + 审计）；
  - **细粒度 sudoers 规则**只放行特定 docker 子命令。

## 本次 HFNL 实操记录（2026-07-19）

- **机器**：HFNL（`10.144.18.100`），Ubuntu 24.04.1 LTS（noble），x86_64；装前无任何 docker/containerd 包。
- **装法**：上面的官方 apt 仓库法，一字不差。
- **装到的版本**：Docker Engine **29.6.2**、containerd.io 2.2.6、buildx 0.35.0、compose v5.3.1；`docker.service` enabled + active，`hello-world` 通过。
- **多用户**：机器有 3 个普通用户（`network` uid 1000、`timidly` uid 1001、`agony` uid 1002），**都已在 sudo 组**。按要求把 **`timidly`、`agony`** 加进 docker 组（`docker:x:983:timidly,agony`），**`network` 未加**（用户明确排除）。
- **验证**：以 `timidly` 非 root、`sg docker -c "docker run --rm hello-world"` 通过；已提醒两位用户其现有会话需重登（或 `newgrp docker`）才自动带上 docker 组。
- **远程执行**：全程经 portal MCP（`remote_exec` + `use_sudo`）在 HFNL 上跑；sudo 口令走 `portal sudo set HFNL` 带外缓存、不进对话。
