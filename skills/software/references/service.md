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
