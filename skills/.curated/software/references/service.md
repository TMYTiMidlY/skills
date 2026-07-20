# Service / systemd

## 多用户共享服务的端口分配

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

## systemd LoadCredential 注入密钥

服务要读 S3 key、API token 这类密钥时，别把明文写进 unit 文件或世界可读的配置。systemd 的 `LoadCredential=` 能把一个凭据文件**只挂给这个服务的私有运行时目录**（`$CREDENTIALS_DIRECTORY`，通常在 `/run/credentials/<unit>/` 下，`0400`、仅该服务可读、进程退出即消失、不落持久化明文）：

```ini
[Service]
LoadCredential=secrets.toml:/etc/myservice/secrets.toml
ExecStart=/usr/local/bin/myservice -secrets ${CREDENTIALS_DIRECTORY}/secrets.toml
```

**版本门槛**：`LoadCredential=` 需要 **systemd ≥ 247**（`$CREDENTIALS_DIRECTORY` 由它注入）。老发行版（如 systemd 239 的 RHEL8 / Anolis / Alibaba Cloud Linux 3 系）会**静默忽略**这行——`$CREDENTIALS_DIRECTORY` 为空、程序按默认路径找密钥找不到，表现成"配置看着对却读不到密钥"的怪问题（例如 S3 后端启动直接 `Access Denied`）。

**老 systemd 的回退**（不用 `LoadCredential` / `DynamicUser`，靠固定账号 + 文件权限兜底）：
- unit 里用**固定** `User=<svc>`（别用 `DynamicUser=yes`，否则凭据文件属主对不上）；
- 凭据文件属主设成该用户、权限 `0600`；
- `ExecStart` 里**显式**传绝对路径 `-secrets /etc/myservice/secrets.toml`，不依赖 `$CREDENTIALS_DIRECTORY`。

（`git-pages` 就是这套：`-secrets` 默认读 `$CREDENTIALS_DIRECTORY/secrets.toml`，原生适配 systemd 凭据机制。）
