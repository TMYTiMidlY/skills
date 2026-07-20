# uv（Python 包与环境管理器）

[uv](https://github.com/astral-sh/uv)（Astral 出品的快速 Python 包 / 虚拟环境管理器）使用与排障笔记。下面的说法据本机实测，版本随文标注。

## snap 版 uv 会让 systemd 服务日志"从 `-u` 里消失"

**现象**：一个 systemd 服务 `ExecStart=/snap/bin/uv run …`（uv 由 snap 安装），被 uv 拉起的应用（mkdocs / python 脚本等）明明在正常往 stderr 打日志，`journalctl --user -u <service>.service` 却**只有 systemd 自己的 `Started`/`Stopped`**，应用自己的输出**一行都看不到**——但服务确实在正常运行、正常输出。

**根因：journald 按进程当前的 cgroup 归属日志，而 snap 把应用挪出了服务的 cgroup。**

- `/snap/bin/<app>` 是个 snap 包装器（`readlink -f "$(which uv)"` 指向 `/usr/bin/snap`）。snap 应用启动时，snapd 把真正的进程**重新放进一个它自己的临时 scope**：`snap.<snap名>.<app>-<uuid>.scope`（挂在 `user@<uid>.service/app.slice` 下，而不是 `<service>.service` 下）。
- journald 给每条**流式**日志盖的 `_SYSTEMD_UNIT` / `_SYSTEMD_USER_UNIT`，取的是**写日志那一刻进程所在的 cgroup**。于是应用日志被归到那个 snap scope，不是你的服务单元。
- `journalctl -u <service>.service` = 按 `_SYSTEMD_USER_UNIT=<service>.service` 过滤 → **匹配不到**应用日志（它挂在 `snap.…scope` 名下）。能被 `-u` 查到的 `Started/Stopped`，是 **user manager 自己**发的、带 unit 引用的消息，不是应用输出。

**证据**（`journalctl -o verbose` 看任一条应用日志的字段，实测 `astral-uv` snap 0.11.21 / uv 拉起 mkdocs）：

```
_COMM=<app>
SYSLOG_IDENTIFIER=<你在 unit 里设的 SyslogIdentifier>
_SYSTEMD_CGROUP=/user.slice/user-<uid>.slice/user@<uid>.service/app.slice/snap.<snap>.<app>-<uuid>.scope
_SYSTEMD_USER_UNIT=snap.<snap>.<app>-<uuid>.scope        ← 不是 <service>.service
```

一条命令诊断：`journalctl --user -t <identifier> -o verbose -n1 | grep _SYSTEMD`。

**这正常吗？** 正常——这是 snap 沙箱/scope 机制的既定副作用，不是配置错，对**任何**由 systemd 单元启动的 snap 二进制都成立；**`classic` confinement 也照样重挪**（实测 `astral-uv` 是 classic，进程仍进 `snap.astral-uv.uv-<uuid>.scope`）。日志一条没丢，只是挂在 snap scope 的身份下。

**绕过（不改安装）**：按 **SyslogIdentifier** 查，而不是按 unit——前提是 unit 里设了 `SyslogIdentifier=<identifier>`：

```bash
journalctl --user -t <identifier> -n 50     # 看历史
journalctl --user -t <identifier> -f        # 实时跟随
```

`-t` 有效，是因为 SyslogIdentifier 是 systemd **建流时**就盖在每一行上的，snap 之后怎么挪 cgroup 都不影响它。

**治本（想让 `-u` 和 `systemctl status` 的 CGroup 视图也干净）**：让 `ExecStart` 跑一个**非 snap 的 uv**——官方 standalone 安装（[`astral.sh/uv`](https://docs.astral.sh/uv/getting-started/installation/) 的 install 脚本，装进 `~/.local/bin`）、或 pipx / cargo 装的 uv 都行。非 snap 的 uv 不重挪 scope，进程留在 `<service>.service` 的 cgroup 里，`-u` 与 `-t` 都好使。

> 一句话：**这不是 uv 的锅，是 snap 的锅**——任何 `ExecStart=` 指到一个 snap 包装器的 systemd 服务都会这样。要么按 `-t <identifier>` 查，要么把 ExecStart 换成非 snap 版。

## `uv run` 下 Python 日志会被块缓冲（加 `PYTHONUNBUFFERED=1`）

`uv run <script>` / `uv run <tool>` 起的 Python 进程，stdout/stderr 在**非 TTY**（systemd 服务、管道）下默认**块缓冲**：日志迟迟不落，进程一旦卡死 / 被 kill，缓冲区里的内容（往往正是要看的报错）直接丢失。

`uv run` 会把父进程环境**透传**给子进程，所以在 unit 里加一行即可让 Python 改成实时输出：

```ini
[Service]
Environment=PYTHONUNBUFFERED=1
```

实测：加之后子进程 `/proc/<pid>/environ` 里能看到 `PYTHONUNBUFFERED=1`（uv 透传成功），服务日志秒级进 journald（配合上一节按 `-t <identifier>` 查）。
