---
name: docker-maintenance
description: 在 Hermes 等受限 Docker 容器内做环境探测和维护时使用。核心是分清宿主、容器与 WSL 边界，在只读挂载或无浏览器条件下安全安装工具、认证并管理持久文件。
---

# Docker 维护

## 何时使用

AI 运行环境疑似在容器里、需要在容器内装工具 / 配置认证 / 诊断写入失败等场景。不是给 host 侧用的（host 侧维护看 `vps-maintenance`）。

## 容器感知

先分别确认运行环境和目标路径的挂载属性。识别出容器，不等于已经知道它有哪些权限、哪些目录可写，或哪些文件会持久保存。

| 观察 | 能说明什么 | 不能据此断定什么 |
|---|---|---|
| `uname -a` 包含 `microsoft-standard-WSL2` | 当前使用 WSL2 内核 | 无法区分 WSL2 本身和运行在其中的容器 |
| `/proc/1/cgroup` 为 `0::/` | 在当前 cgroup 视图中，PID 1 位于统一层级的根 | 宿主根 cgroup 和私有 cgroup namespace 都可能出现，不能单独证明是容器 |
| cgroup 路径包含 `docker` / `containerd` | 有运行时命名线索 | namespace、运行时和配置变化可能隐藏这些名称；没有名称不等于不是容器 |
| 根挂载使用 `overlay` | 根文件系统组合了上下层目录 | OverlayFS 是文件系统机制，不是容器身份证明；也不是所有容器都用它 |

> cgroup namespace 会改变 `/proc/<pid>/cgroup` 中可见的路径，见 [Linux 6.12 · cgroup namespace](https://www.kernel.org/doc/html/v6.12/admin-guide/cgroup-v2.html#namespace)。OverlayFS 的上下层语义见 [Linux 6.12 · Overlay Filesystem](https://www.kernel.org/doc/html/v6.12/filesystems/overlayfs.html)。

环境有 `systemd-detect-virt` 时，先用它收集容器线索，再结合当前平台提供的运行环境说明判断：

```bash
systemd-detect-virt --container
cat /proc/1/cgroup
findmnt --target / -o TARGET,FSTYPE,OPTIONS
```

`systemd-detect-virt` 未检出、命令不存在或执行失败时，保留“环境未确认”的结论，不直接当成宿主。嵌套环境中应区分容器和下层虚拟机，不根据内核名称跳过这一层。

> 检测范围、嵌套环境与退出状态见 [systemd 257 · systemd-detect-virt](https://www.freedesktop.org/software/systemd/man/257/systemd-detect-virt.html)。

写入失败时，检查**实际目标**所在的挂载，而不是只看根目录。以下命令中的目标应是已存在的目录；文件尚不存在时检查其父目录：

```bash
findmnt --target "$HOME" -o TARGET,SOURCE,FSTYPE,OPTIONS
id
```

`Read-only file system` 和 `Permission denied` 是不同问题：前者查目标挂载的只读属性，后者还要查用户身份、目录权限及访问控制。不要通过换路径、提权或重挂载绕过既定权限边界；先确定允许写入的位置。

在 Hermes Docker 后端曾遇到 `~/.hermes/` 只读的环境，但不能把它写成所有部署的固定布局。`/workspace`、`/root` 是否存在、可写、挂载到宿主或会随容器销毁，都以当前配置为准。容器内能写入某目录，并不证明该目录会持久化；持久化需要核对宿主侧的 volume / bind mount 或平台配置。

## 网络

容器是否能访问外网由实际网络模式、代理、DNS 和平台策略决定，不预设 Hermes Docker 一定直连。

某个 URL 返回 HTTP 200，只能证明当时那条请求成功，不能排除 apt 所用镜像域名、协议、代理或证书链的问题。按 apt 的实际错误继续分层：解析 / 连接 / TLS 错误查相应链路，HTTP 错误查对应源端点，签名错误查仓库密钥和发行版配置。没有对应证据时，不把故障归因于“镜像限制 apt”，也不通过关闭 TLS 或签名校验让安装勉强通过。

## 安装受限工具：以 gh CLI 为例

场景：`apt install gh` 拿不到包或源不信任。通用备选方案——直接下 release tarball。

流程：

1. 去 GitHub Releases 页查当前稳定版 tag（`v2.xx.y`）。
2. `curl -fsSL <release-tarball-url> -o /tmp/gh.tar.gz` 下载。
3. `tar -xzf` 到 `/tmp`。
4. `cp .../bin/gh /usr/local/bin/gh` 放进 PATH，`gh --version` 验证。

这套路也适用于其他 Go 单文件 CLI（`rclone`、`trivy`、`caddy` …）。

## 无浏览器场景下的 OAuth 认证（device flow）

容器里一般起不起浏览器。走 device flow：

```bash
gh auth login --hostname github.com --git-protocol ssh
# 输出里会给 one-time code + URL，到任何能开浏览器的机器上完成
```

登录成功后 token 落在 `~/.config/gh/hosts.yml`。在非持久化容器环境里，这类本地认证状态可能丢失；重要的话记得把这个路径持久化（或挂到数据盘）。

其他走 OAuth 的 CLI 基本都有类似 `--device-code` / `--headless` 的开关，首选它们而非 `--web`。

## SSH key 生成

```bash
ssh-keygen -t ed25519 -C "Hermes Docker" -f ~/.ssh/id_ed25519 -N ""
```

- `-t ed25519`：比 RSA 短、安全性足够。
- `-N ""`：无 passphrase，容器场景免 agent 解锁。有安全顾虑再单独起 `ssh-agent`。
- 生成后 `cat ~/.ssh/id_ed25519.pub` 贴到目标服务（GitHub/远端主机）。

在非持久化容器环境里，key 也可能随环境回收而丢失；要持久化就把 `~/.ssh/` 挂到数据盘，或者用 `docker_volumes` 把 host 的 `.ssh` 挂进来。

## 和其他 skill 的关系

- host 侧 VPS / 服务器维护 → `vps-maintenance`
- 通过 SSH 远程操作别的机器 → `remote`
- 本地软件 / CLI 一般使用与排障 → `software`
