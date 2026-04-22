---
name: docker-maintenance
description: 在 Hermes Docker 后端或类似受限 Docker 容器内做环境探测、写入路径判断、安装受限工具（如 gh CLI）、生成 SSH key 等维护操作时使用。重点是识别"宿主 vs 容器 vs WSL"、绕过只读 overlay、在没有浏览器时完成外部认证。
---

# Docker 维护

## 何时使用

AI 运行环境疑似在容器里、需要在容器内装工具 / 配置认证 / 诊断写入失败等场景。不是给 host 侧用的（host 侧维护看 `vps-maintenance`）。

## 容器感知

先搞清楚自己在哪，错误地把容器当宿主会踩很多坑。

- `uname -a` **不够用**：WSL2 也会显示 `microsoft-standard-WSL2`，不能据此判断是容器。
- 判据看这两个：
  - `/proc/1/cgroup` 在容器里通常是 `0::/` 或带 `docker/containerd` 字样。
  - `mount | grep ' / '` 看到 `overlay` 就是容器。
- Hermes Docker 后端的文件系统布局：`~/.hermes/` 在容器里是**只读 overlay 挂载**，直接写入会报 `Read-only file system`。可写路径优先选 `/workspace`（若启用了 cwd 挂载）或 `/root` 下的数据盘位置。**遇到写失败先问"我是不是在只读挂载下"，别盲目重试**。

## 网络

Hermes Docker 容器默认放通外网（可直连 `google.com`、GitHub 等）。若 curl 200 正常但 apt 一直失败，多半是镜像源对 apt 加了限制，别去怀疑基础网络。

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
