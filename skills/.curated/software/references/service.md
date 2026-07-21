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

## 用户级 systemd 服务（`systemctl --user`）与 linger 常驻

system 级服务放 `/etc/systemd/system/`、由 PID 1 的 system manager 托管，跟机器生命周期走；**user 级服务**放 `~/.config/systemd/user/`、由每个用户自己的 `systemd --user` 实例（user manager）托管，用 `systemctl --user …` / `journalctl --user -u <unit>` 操作。不需要 root，unit 里能用 `%h`（家目录）这类 specifier，适合“归属某个普通用户、又不想写进系统单元”的服务（mkdocs 文档站、rclone 挂载、个人 agent 等）。

**核心坑：user manager 的生命周期默认绑在 login session 上。** SSH 登录 → 拉起该用户的 `systemd --user` 及其 user units；**最后一个 session 退出 → user manager 连同所有 user units 一起被杀**；机器重启后若没人登录该用户，服务也不自启。表现就是“人一登出 / 断开 SSH，服务就挂；重启后不拉起”。

**解法：`loginctl enable-linger <user>`。** linger 直译“逗留 / 滞留”——让该用户的 user manager 在**没有任何 login session 时也继续赖着运行**（开机即被 `systemd-logind` 预启动、登出也不回收），user units 才能 7×24 常驻并开机自启。

```bash
sudo loginctl enable-linger <user>     # 开启（需 root）
loginctl show-user <user> -p Linger    # 校验 → Linger=yes
sudo loginctl disable-linger <user>    # 关闭
```

底层就是在 `/var/lib/systemd/linger/` 下放一个以用户名命名的空文件当标记，logind 据此在开机时预启动该用户的 manager。

**没 sudo 开不了 linger 时**（WSL 内、受限账号等）：只能在该用户 session 活着时跑，session 一断服务就停；重进 session 后服务随 `default.target` 自动起——rclone@ 在 WSL 里的这种处理见 [mount.md](mount.md)。

**user service vs system service 怎么选**：要 root 能力、与登录完全无关、开机必起 → 直接写 system service（不碰 linger）；归属某普通用户、要用其 `~` 下的运行时 / 凭据、又要求登出后仍在跑 → user service + `enable-linger`。
