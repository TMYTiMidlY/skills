# Tavotto（论文图可视化编辑器：安装与本地运行）

Tavotto 在浏览器里可视化编辑 matplotlib 画出的论文图：改动以 override 保存在图库旁、源脚本一字节不动，导出前按期刊规范预检，PDF/PNG 走矢量。本篇记录安装、systemd 常驻与重启后的恢复；公网入口（双层 Caddy、TLS 签发、会话代持）的模式与配置模板见 `network` skill 的 Caddy 文档。功能全貌见[官方中文 README](https://github.com/Tavotto/Tavotto/blob/v0.15.0/README.zh-CN.md)。

> AGPL-3.0-only：自用与内部分发不受限；架成他人可网络访问的服务需向这些用户提供源码。

## <a id="runtime-shape"></a>运行形态

浏览器模式是一个本地 Flask 服务：只绑 `127.0.0.1:5089`（写死、无 `--host` 参数），前端构建产物随 wheel 内置，装完即用、不需要 Node。一个"项目" = 一个图库目录（matplotlib 脚本与其 PDF 产物同目录）；服务进程可同时端着多个项目，文件 watcher 只盯当前打开着的目录。启动参数只有 `--figures <目录>`（启动即打开某图库；缺省恢复最近项目）、`--port`、`--no-browser`。渲染 worker 会真实执行图库里的 `.py`，因此绝不能用 root 跑，也不应把它暴露到本机之外。

它自带一层会话认证：启动时打印带 `#dnonce=` 的落地 URL（fragment 不进请求行与访问日志），浏览器兑换成 HttpOnly + SameSite=Strict 的 cookie（30 天）；**会话 token 只存进程内存，服务一重启全部作废**——这是刻意的安全设计（[security.py](https://github.com/Tavotto/Tavotto/blob/62eb7f7a8746e99ce6ed59e1086ce79cb7509508/src/tavotto/security.py)）。

## <a id="install"></a>安装（uv + systemd）

```bash
uv tool install "tavotto[worker]"    # [worker] 附带 matplotlib/numpy 渲染栈
```

systemd 系统服务 `/etc/systemd/system/tavotto.service`（普通用户运行、崩溃 5 秒自愈）：

```ini
[Unit]
Description=Tavotto web — 本地图库可视化编辑器 (127.0.0.1:5089)
After=network.target

[Service]
Type=simple
User=timidly
Group=timidly
Environment=HOME=/home/timidly
ExecStart=/home/timidly/.local/bin/tavotto --no-browser
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

`Environment=HOME` 必须写：系统服务默认没有 HOME，而数据目录 `~/.local/share/tavotto/` 依赖它。升级流程 `uv tool upgrade tavotto && sudo systemctl restart tavotto`，随后按[重启后的恢复](#restart-recovery)重铸会话。本机浏览器直连时用 `~/.local/bin/tavotto-link [proxy|local]` 换一枚一次性访问链接（5 分钟有效）。

## <a id="restart-recovery"></a>tavotto 重启后的恢复

重启（升级、崩溃自愈、服务器重启）后内存里的会话清零，公网代持的 cookie 随之失效——公网页面显示"会话未建立"的提示屏。GitHub 登录不受影响（Caddy 层独立），磁盘上的项目与版面零丢失。在服务器上整段执行即可：

```bash
sudo python3 - <<'EOF'
import json, os, urllib.request

base = "http://127.0.0.1:5089"
secret = json.load(open("/home/timidly/.local/share/tavotto/session/port-5089.json"))["secret"]

nonce = json.loads(urllib.request.urlopen(urllib.request.Request(
    base + "/api/session/relaunch",
    data=json.dumps({"secret": secret}).encode(),
    headers={"Content-Type": "application/json"})).read())["nonce"]

token = urllib.request.urlopen(urllib.request.Request(
    base + "/api/session/bootstrap",
    data=json.dumps({"nonce": nonce}).encode(),
    headers={"Content-Type": "application/json"})
).headers["Set-Cookie"].split("tavotto_session=")[1].split(";")[0]

with open("/etc/caddy/tavotto.env", "w") as f:
    f.write("TAVOTTO_SESSION=" + token + "\n")
os.chmod("/etc/caddy/tavotto.env", 0o600)
print("OK /etc/caddy/tavotto.env")
EOF
sudo systemctl restart caddy
```

流程：读本机凭据文件（0600，路径见 [session_client.py](https://github.com/Tavotto/Tavotto/blob/62eb7f7a8746e99ce6ed59e1086ce79cb7509508/src/tavotto/engine/session_client.py)）→ `/api/session/relaunch` 换一枚一次性 nonce（5 分钟有效）→ `/api/session/bootstrap` 兑换 cookie → 写入 `/etc/caddy/tavotto.env` → 重启 Caddy 加载新值。验证：`curl -s -o /dev/null -w '%{http_code}\n' -H 'Host: tavotto.hfnl.app.chenzhaoyun.com' http://10.144.18.100:18080/api/version` 未登录应得 302 跳登录门；已过 GitHub 认证的浏览器刷新页面即恢复。
