# Tavotto（论文图可视化编辑器：安装与本地运行）

Tavotto 在浏览器里可视化编辑 matplotlib 画出的论文图：改动以 override 保存在图库旁、源脚本一字节不动，导出前按期刊规范预检，PDF/PNG 走矢量。本篇记录安装、systemd 常驻、应用侧接入约束与会话恢复；公网统一认证、代理凭据管理与上游会话代持转用 `network` skill。功能全貌见[官方中文 README](https://github.com/Tavotto/Tavotto/blob/v0.15.0/README.zh-CN.md)。

> AGPL-3.0-only：自用与内部分发不受限；架成他人可网络访问的服务需向这些用户提供源码。

## <a id="runtime-shape"></a>运行形态

浏览器模式是一个本地 Flask 服务：监听地址固定为 `127.0.0.1`，默认端口 `5089`，无 `--host` 参数；前端构建产物随 wheel 内置，装完即用、不需要 Node。一个"项目" = 一个图库目录（matplotlib 脚本与其 PDF 产物同目录）；服务进程可同时端着多个项目，文件 watcher 只盯当前打开着的目录。常用启动参数为 `--figures <目录>`（启动即打开某图库；缺省恢复最近项目）、`--port`、`--no-browser`。渲染 worker 会真实执行图库里的 `.py`，应使用普通用户运行，后端保持本机私有；受控公网入口的条件见 [反向代理接入约束](#proxy-access)。

它自带一层会话认证：启动时打印带 `#dnonce=` 的落地 URL（fragment 不进请求行与访问日志），浏览器兑换成 HttpOnly + SameSite=Strict 的 cookie。**会话 token 只存进程内存，服务一重启全部作废**；服务端只保留最近 8 枚已兑换的 token，继续兑换还可能挤出旧的代持会话。浏览器 cookie 的 Max-Age 为 30 天，不代表代理持有的 token 必定存活或在第 30 天自动失效。

> 会话列表的保留与校验见 [SessionState](https://github.com/Tavotto/Tavotto/blob/62eb7f7a8746e99ce6ed59e1086ce79cb7509508/src/tavotto/security.py#L75-L143)，浏览器 Max-Age 与 cookie 签发见 [cookie 配置](https://github.com/Tavotto/Tavotto/blob/62eb7f7a8746e99ce6ed59e1086ce79cb7509508/src/tavotto/security.py#L147-L176)。

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
User=<user>
Group=<group>
Environment=HOME=<user-home>
ExecStart=<user-home>/.local/bin/tavotto --no-browser
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

将 `<user>`、`<group>`、`<user-home>` 替换为实际服务账户；可执行文件以该用户的安装位置为准。显式设置 HOME 便于核对数据目录归属，不依赖启动 shell。升级时先以服务用户执行 `uv tool upgrade tavotto`，成功后由管理员重启 `tavotto.service`，再按 [重启后的恢复](#restart-recovery)更新会话。

本机浏览器可打开当前启动输出的 `#dnonce=` 链接；已有实例需新链接时，用下节的本机凭据调用 `/api/session/relaunch`，把返回的 nonce 放进 `http://127.0.0.1:<port>/#dnonce=<nonce>`。该 relaunch nonce 有效期 5 分钟、兑换一次即失效；只交给授权的本机浏览器，不写进公开日志。

## <a id="proxy-access"></a>反向代理接入约束

公网统一认证、Cookie 注入/剥离、代理凭据存放和更新方式转用 `network` skill 的上游会话代持主题。本应用额外要求：后端收到的 Host 必须严格等于 `127.0.0.1:<port>`；若请求带 Origin，必须等于 `http://127.0.0.1:<port>`。公网域名不能直接透传给这道守卫，否则在会话校验前就会得到 403。

在上游仅本机可达、入口已独立认证授权并覆盖全站的前提下，已记录的代理适配是在 `reverse_proxy` 内增加以下应用专属差异：

```caddyfile
header_up Host 127.0.0.1:<port>
header_up -Origin
```

Origin 的删除只适用于这个受控入口：它移除了后端对原始浏览器来源的校验，不能代替入口侧的跨站请求防护。源码也接受匹配的本机 Origin，但成对改写方式未在此部署记录中验证。兑换和后续请求使用同一个实际端口；cookie 名固定为 `tavotto_session`。

> Host/Origin 的判定与 403 响应见 [会话守卫](https://github.com/Tavotto/Tavotto/blob/62eb7f7a8746e99ce6ed59e1086ce79cb7509508/src/tavotto/security.py#L197-L217)，cookie 名见 [会话常量](https://github.com/Tavotto/Tavotto/blob/62eb7f7a8746e99ce6ed59e1086ce79cb7509508/src/tavotto/security.py#L49-L54)。

## <a id="restart-recovery"></a>Tavotto 重启后的恢复

重启后内存会话清零，代持 cookie 随之失效；上游受保护接口返回 401，页面提示“会话未建立或已失效”。入口 OAuth 独立于这次会话失效，磁盘项目也不会因会话清零而被删除。恢复流程是以服务用户读取当前凭据文件 → `/api/session/relaunch` 换 nonce → `/api/session/bootstrap` 换 cookie → 验证受保护接口 → 交给代理更新。

本机凭据位于服务用户实际数据目录的 `session/port-<port>.json`，不是当前管理员 HOME 下的同名文件。下面只执行应用侧兑换和验证：替换路径与端口，输出文件须不存在、父目录须受保护；真实凭据不经参数或标准输出传递。

```bash
SESSION_FILE="<服务用户数据目录>/session/port-5089.json" \
COOKIE_FILE="<受保护输出目录>/tavotto.cookie" PORT=5089 \
uv run --no-project python - <<'PY'
import json, os, urllib.request
from http.cookies import SimpleCookie

base = "http://127.0.0.1:" + str(int(os.environ["PORT"]))
with open(os.environ["SESSION_FILE"], encoding="utf-8") as f:
    secret = json.load(f)["secret"]
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

def post(path, body):
    return opener.open(urllib.request.Request(
        base + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}), timeout=10)

with post("/api/session/relaunch", {"secret": secret}) as response:
    nonce = json.load(response)["nonce"]
with post("/api/session/bootstrap", {"nonce": nonce}) as response:
    cookie = SimpleCookie()
    cookie.load(response.headers["Set-Cookie"])
token = cookie["tavotto_session"].value
request = urllib.request.Request(base + "/api/session/ping",
    headers={"Cookie": "tavotto_session=" + token})
with opener.open(request, timeout=10) as response:
    if response.status != 200 or json.load(response).get("ok") is not True:
        raise RuntimeError("session validation failed")
fd = os.open(os.environ["COOKIE_FILE"], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as f:
    f.write(token + "\n")
print("会话验证通过，已写入受保护输出文件")
PY
```

输出文件只含 cookie 值，不含 `tavotto_session=` 前缀。将名称和值交给 `network` skill 的上游会话代持流程保存并应用；兑换失败时不覆盖正在使用的代理凭据。以相同后端地址不带 cookie 或带无效 cookie 请求 `/api/session/ping` 应得到 401，再检查公网未认证被阻挡、授权后接口恢复。`/api/version` 是公开探测接口，返回 200 不能证明会话有效。

> 凭据位置见 [session_file_path](https://github.com/Tavotto/Tavotto/blob/62eb7f7a8746e99ce6ed59e1086ce79cb7509508/src/tavotto/engine/session_client.py#L40-L45)，nonce 请求见 [relaunch_nonce](https://github.com/Tavotto/Tavotto/blob/62eb7f7a8746e99ce6ed59e1086ce79cb7509508/src/tavotto/engine/session_client.py#L100-L121)。`/api/session/ping` 经过 [会话守卫](https://github.com/Tavotto/Tavotto/blob/62eb7f7a8746e99ce6ed59e1086ce79cb7509508/src/tavotto/security.py#L192-L217)，而 `/api/version` 属于 [公开路径](https://github.com/Tavotto/Tavotto/blob/62eb7f7a8746e99ce6ed59e1086ce79cb7509508/src/tavotto/security.py#L61-L73)。
