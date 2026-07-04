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

## `systemctl reload` 失败 ≠ 服务挂了

很多守护进程（Caddy、nginx 等）的 `systemctl reload` 是"加载新配置文件、热替换运行态"。关键行为：**reload 时如果新配置校验不通过，reload 会失败退出，但服务进程本身不会停——它继续用内存里已加载的旧配置运行**。所以看到 `Job for xxx.service failed`（reload 失败）先别慌，服务大概率还在正常服务旧配置，线上没断。

实践建议：改这类服务的配置后，① 先用工具自带的校验命令 dry-run（如 `caddy validate --adapter caddyfile --config <file>`、`nginx -t`）确认新配置能过再 reload；② reload 失败后按报错修好配置文件重新 reload，不要盲目 `restart`——`restart` 会真正停掉进程再起，如果新配置有错，`restart` 反而会让服务起不来、真的断服（比 reload 失败更糟）。

## 改端口/地址类配置：`sed` 全局替换会误伤子串

用 `sed 's|:80|:8001|g'` 这种**无锚定**的全局替换去改配置里的端口号，会把所有包含 `:80` 子串的地方一起改坏——`:8080` 变成 `:80801`、`:8022` 变成 `:80122` 之类，而且改完往往不报错、直到 reload 校验时才炸（如 Caddy 报 `invalid start port ... value out of range`）。改端口/IP 这类"短数字字符串"时：优先用能定位到具体行/字段的方式（指定行号 `sed '275s|...|...|'`、或匹配更长的唯一上下文），改完**必带一步 diff 复核**（`diff` 原文件和改后文件，确认只动了预期的那一处），再校验、再 reload。
