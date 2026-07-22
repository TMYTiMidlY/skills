# Service / systemd

## 多用户 systemd 模板

### 实例名与运行用户

同一项服务需要为多个用户各运行一份时，可以使用模板单元（`@` service）。`%i` 是模板实例名；若实例名直接采用用户名，`User=%i` 就会让每个实例以对应用户运行：

```ini
[Unit]
Description=MyService for %i

[Service]
User=%i
ExecStart=/usr/bin/myservice
```

实例通过用户名启用：

```bash
systemctl enable --now myservice@<user>
```

### 按 UID 分配端口

多用户实例可以在 `ExecStart` 中按 UID 动态计算端口，避免冲突：

```text
port = base_port + user_uid - base_uid
```

**先用 `id -u <主用户>` 查询 `base_uid`，不要想当然填 `1000`**；部分发行版或镜像的首个普通用户 UID 是 `1001` 或其他值。把查询结果填入偏移项：

```ini
[Service]
User=%i
ExecStart=/bin/sh -c 'exec /usr/bin/myservice --port $((BASE_PORT + $(id -u %i) - <主用户 UID>))'
```

其中 `BASE_PORT` 替换为实际基准端口，`%i` 仍是实例用户名。

### Specifier 的解析上下文

`%i` 来自模板实例名，适合传用户名；`%u` / `%U` 的语义不同：它们表示**运行 service manager 的用户 / UID**，不是 unit 中 `User=` 指定的运行用户。system-level unit 由 PID 1 的 system manager 解析，因此 `%u=root`、`%U=0`。这一点见 Ubuntu 24.04（systemd 255）的 [`systemd.unit` Specifiers](https://manpages.ubuntu.com/manpages/noble/man5/systemd.unit.5.html#specifiers)。

所以下面的写法不会得到实例用户 UID：

```ini
[Service]
User=%i
Environment=RUNTIME_DIR=/tmp/myservice-%U
```

无论实例属于哪个用户，`RUNTIME_DIR` 都会先被 system manager 展开成 `/tmp/myservice-0`。若该目录归 root 且权限为 `0700`，普通用户进程会报 `Permission denied`。

需要实例用户 UID 时，在 `ExecStart` 的 shell 中按 `%i` 查询：

```ini
[Service]
User=%i
ExecStart=/bin/sh -c 'uid=$(id -u %i); exec /usr/bin/myservice --runtime-dir "/tmp/myservice-$uid"'
```

如果程序本身会根据当前进程 UID、HOME 或 XDG runtime 选择安全目录，通常无需覆盖该目录。

## systemd 凭据注入

服务读取 S3 key、API token 一类密钥时，可以用 `LoadCredential=` 避免把明文写进 unit 文件或世界可读的配置。systemd 会把凭据文件只挂给该服务的私有运行时目录；路径由 `$CREDENTIALS_DIRECTORY` 提供，通常位于 `/run/credentials/<unit>/`，权限为 `0400`、仅该服务可读，进程退出后消失，不会在运行时目录留下持久化明文：

```ini
[Service]
LoadCredential=secrets.toml:/etc/myservice/secrets.toml
ExecStart=/usr/local/bin/myservice -secrets ${CREDENTIALS_DIRECTORY}/secrets.toml
```

`LoadCredential=` 需要 **systemd ≥ 247**，`$CREDENTIALS_DIRECTORY` 也由该版本开始注入。老发行版（如 systemd 239 的 RHEL8、Anolis 或 Alibaba Cloud Linux 3 系）会**静默忽略**这行：变量为空，程序按默认路径找不到密钥，可能表现为“配置看似正确却读不到密钥”，例如 S3 后端启动时报 `Access Denied`。

老 systemd 可退回固定服务账号与文件权限：

- unit 使用固定的 `User=<svc>`；不要启用 `DynamicUser=yes`，否则凭据文件属主无法稳定对应；
- 凭据文件归该用户所有，权限设为 `0600`；
- `ExecStart` 显式传绝对路径，例如 `-secrets /etc/myservice/secrets.toml`，不依赖 `$CREDENTIALS_DIRECTORY`。

`git-pages` 就采用这套接口：`-secrets` 默认读取 `$CREDENTIALS_DIRECTORY/secrets.toml`，原生适配 systemd 凭据机制。

## 用户级服务与 linger

system 级服务放在 `/etc/systemd/system/`，由 PID 1 的 system manager 托管，跟随机器生命周期。用户级服务放在 `~/.config/systemd/user/`，由每个用户自己的 `systemd --user` 实例（user manager）托管，通过 `systemctl --user …` 和 `journalctl --user -u <unit>` 操作。它不需要 root，unit 中也能使用 `%h`（家目录）等 specifier，适合归属某个普通用户、需要其 HOME 下运行时或凭据的服务，例如 mkdocs 文档站、rclone 挂载或个人 agent。

默认情况下，user manager 的生命周期绑定 login session：SSH 登录会拉起该用户的 `systemd --user` 及其 units；最后一个 session 退出时，user manager 和所有 user units 一起停止。机器重启后若无人登录，该用户的服务也不会启动。典型症状是“登出或 SSH 断开后服务停止，重启后不自启”。

`loginctl enable-linger <user>` 会让 user manager 在没有 login session 时继续运行，由 `systemd-logind` 开机预启动、登出后不回收，因此 user units 可以常驻并开机自启：

```bash
sudo loginctl enable-linger <user>
loginctl show-user <user> -p Linger    # Linger=yes
sudo loginctl disable-linger <user>
```

底层标记是 `/var/lib/systemd/linger/` 下以用户名命名的空文件，logind 据此在开机时预启动该用户的 manager。

没有 sudo 权限时（如 WSL 内或受限账号），无法开启 linger：服务只能在该用户 session 存活期间运行，session 结束就停止；再次进入 session 后，可随 `default.target` 自动启动。rclone@ 在 WSL 中的这种处理见 [mount.md](mount.md)。

选择时按生命周期和权限判断：

- 需要 root 能力、与登录完全无关、开机必须启动：使用 system service；
- 归属普通用户、依赖其 HOME 下的运行时或凭据，并要求登出后仍运行：使用 user service 并启用 linger。
