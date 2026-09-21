# Tavotto（论文图可视化编辑器：部署与公网访问）

Tavotto 在浏览器里可视化编辑 matplotlib 画出的论文图：改动以 override 保存在图库旁、源脚本一字节不动，导出前按期刊规范预检，PDF/PNG 走矢量。本篇记录这台服务器的部署形态——uv 安装、systemd 常驻、双层 Caddy 公网入口与 GitHub OAuth、会话代持免 dnonce，以及重启后的恢复命令。功能全貌见[官方中文 README](https://github.com/Tavotto/Tavotto/blob/v0.15.0/README.zh-CN.md)。

> AGPL-3.0-only：自用与内部分发不受限；架成他人可网络访问的服务需向这些用户提供源码。

## <a id="runtime-shape"></a>运行形态

浏览器模式是一个本地 Flask 服务：只绑 `127.0.0.1:5089`（写死、无 `--host` 参数），前端构建产物随 wheel 内置，装完即用、不需要 Node。一个"项目" = 一个图库目录（matplotlib 脚本与其 PDF 产物同目录）；服务进程可同时端着多个项目，文件 watcher 只盯当前打开着的目录。启动参数只有 `--figures <目录>`（启动即打开某图库；缺省恢复最近项目）、`--port`、`--no-browser`。渲染 worker 会真实执行图库里的 `.py`，因此绝不能用 root 跑，也不应把它暴露到本机之外。

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

## <a id="public-chain"></a>公网访问链路（双层 Caddy + GitHub OAuth）

```text
浏览器 → Alibaba 边缘 VPS（公网 IP，TLS 终止）
       → 内网 Caddy 10.144.18.100:18080（routes.d 分片 + caddy-security）
       → authorize with admin_access（GitHub OAuth，仅 authp/admin 角色）
       → reverse_proxy 127.0.0.1:5089
```

边缘对 `*.hfnl.app.chenzhaoyun.com` 有泛域名直通块；tavotto 另加了显式站点块改用 **ZeroSSL EAB** 签发：Let's Encrypt 对注册域 `chenzhaoyun.com` 有 50 张 / 7 天的限额，签满后新域名首签收到 429、TLS 握手直接失败（症状是 `curl` 退出码 35 / fetch failed，而不是 HTTP 错误）。on-demand 签发的准入门卫跑在边缘本机 `127.0.0.1:9119`，按后缀放行 `*.app.chenzhaoyun.com`。边缘块位于 Alibaba 的 `/etc/caddy/Caddyfile`（改动前有 `Caddyfile.backup-tavotto-*` 备份）。

内网分片 `/etc/caddy/routes.d/50-tavotto.caddy`：

```caddyfile
@tavotto host tavotto.hfnl.app.chenzhaoyun.com
handle @tavotto {
	authorize with admin_access
	reverse_proxy 127.0.0.1:5089 {
		header_up Host 127.0.0.1:5089
		header_up -Origin
		header_up Cookie "tavotto_session={$TAVOTTO_SESSION}"
		header_down -Set-Cookie
	}
}
```

`Host` 必须改写成 `127.0.0.1:5089`、`Origin` 必须剥掉：tavotto 的会话守卫对 Host 做严格等值校验（只认这一种写法）、带 Origin 的请求要求严格同源，代理域名直透过不去、一律 403（[security.py](https://github.com/Tavotto/Tavotto/blob/62eb7f7a8746e99ce6ed59e1086ce79cb7509508/src/tavotto/security.py)）。

## <a id="session-hold"></a>会话代持（公网免 dnonce）

tavotto 自带一层会话认证：启动时打印带 `#dnonce=` 的落地 URL（fragment 不进请求行与访问日志），浏览器用它兑换一枚 HttpOnly + SameSite=Strict 的 cookie（有效期 30 天）。**会话 token 只存进程内存**，服务一重启全部作废——这是它的安全设计（ADR 0008，见上面 security.py 的模块注释），不是待修的缺陷。

公网侧不给用户发 dnonce：Caddy 过完 GitHub OAuth 后，代替浏览器携带一枚已兑换的会话 cookie 访问上游。`header_up Cookie` 整段覆盖浏览器的 Cookie 头（GitHub 等认证 cookie 留在 Caddy 层），`header_down -Set-Cookie` 剥离响应里的全部 Set-Cookie，公网浏览器永远拿不到 tavotto 会话。cookie 值放在 `/etc/caddy/tavotto.env`（600 root），经 drop-in `/etc/systemd/system/caddy.service.d/tavotto-env.conf` 的 `EnvironmentFile=` 进入 Caddy 进程环境。

> `{$VAR}` 在 Caddyfile 解析期展开、值来自 Caddy 进程环境——改完 env 文件必须 `systemctl restart caddy`，`reload` 不会重读；误写成 `{env.VAR}` 会把占位符原样发给上游、只会得到 401。

## <a id="restart-recovery"></a>tavotto 重启后的恢复

重启（升级、崩溃自愈、服务器重启）后内存里的会话清零，代持的 cookie 随之失效——公网页面显示"会话未建立"的提示屏。GitHub 登录不受影响（Caddy 层独立），磁盘上的项目与版面零丢失。在服务器上整段执行即可：

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

流程：读本机凭据文件（0600，路径见 [session_client.py](https://github.com/Tavotto/Tavotto/blob/62eb7f7a8746e99ce6ed59e1086ce79cb7509508/src/tavotto/engine/session_client.py)）→ `/api/session/relaunch` 换一枚一次性 nonce（5 分钟有效）→ `/api/session/bootstrap` 兑换 cookie → 写入 env 文件 → 重启 Caddy 加载新值。验证：`curl -s -o /dev/null -w '%{http_code}\n' -H 'Host: tavotto.hfnl.app.chenzhaoyun.com' http://10.144.18.100:18080/api/version` 未登录应得 302 跳登录门；已过 GitHub 认证的浏览器刷新页面即恢复。
