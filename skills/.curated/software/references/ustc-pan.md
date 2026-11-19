# 科大云盘（USTC pan）

科大云盘是中国科学技术大学基于 Seafile 的校园网盘。网页端使用学校统一身份认证（SSO）。在无图形界面的环境中，可用 WebDAV 访问自己的资料库，也可通过已有分享链接下载文件。客户端和 WebDAV 的配置说明见 [科大云盘用户手册](https://pan.ustc.edu.cn/doc/install/)。

> 账号、WebDAV 密码、分享密码、rclone remote 名等部署事实随各环境记录，不在本文固化。

## <a id="access-channels"></a>访问通道与认证模型

同一份文件开有几扇互相独立的门，认证方式各不相同，可用性差别很大：

| 通道 | 认证 | headless 可用性 |
|---|---|---|
| 网页端（自研 Vue SPA 壳 + Seahub 后端） | 统一身份认证 SSO | 需浏览器，供人使用 |
| Seafile 同步客户端（GUI `seafile-applet` / CLI `seaf-cli`） | GUI 走 SSO，CLI 走 `/api2/auth-token/` | GUI 需显示与浏览器，CLI 在实测部署上无法登录（见 [同步客户端的登录流程](#seaf-cli-dead-end)） |
| WebDAV（`https://pan.ustc.edu.cn/seafdav/`） | 独立 WebDAV 密码 | 可用，配 rclone（见 [WebDAV 配 rclone](#webdav-rclone)） |
| 分享链接（`/share/index/<token>`） | 分享密码（可选），匿名 | 可用，API 直取直链（见[分享链接的匿名下载 API](#share-api)） |

WebDAV 用户名形如 `<学号或工号>@auth.local`，密码要在网页端设置的「WebDAV 密码」处单独生成，与统一身份认证密码是两套；出现 401 时先回网页端核对 / 重置 WebDAV 密码，不要拿统一身份认证密码去试。

## <a id="seaf-cli-dead-end"></a>同步客户端的登录流程

官方桌面客户端 AppImage 用 `--appimage-extract` 解开后就是标准 Seafile 客户端三件套：GUI `seafile-applet`（Qt）、同步引擎 `seaf-daemon`、命令行 `seaf-cli`（Python）。headless 跑 `seaf-cli` 本身没问题——补三个环境变量（`PATH+=usr/bin`、`LD_LIBRARY_PATH+=usr/lib`、`PYTHONPATH+=usr/lib/python3.8/site-packages`）后，其 Python 绑定是纯 Python，系统 Python 3.12 可直接运行，`init → start → status → stop` 实测全通。卡死在登录一步，且是服务端配置所致，换环境重试也没用：

- `seaf-cli` 的 `get_token` 写死 `POST /api2/auth-token/` 换 token（2026-06 对 USTC_Drive 1.1.9 AppImage 解包实读，非上游源码推断）。实测该端点对 POST 直接 **301 改道**到 `/api/` 落地页（还从 https 降级成 http），跟过去是 **405 + text/html**——密码校验之前就被改道，用假密码复现同样结果，与凭据对错无关。
- 整个 `/api2` 命名空间都被 SSO 影子化（`/api2/ping/` 也被接管页拦截）。所以给 `seaf-cli download -a <token>` 手动喂 token 也救不回来：token 无处可取（换 token 的 API 关了），且后续要打的 `/api2/repos/` 在同一命名空间里。
- GUI 客户端能登录是走了另一条路：Shibboleth SSO（解包二进制中的 `ShibLoginDialog`、`api2/client-sso-link/`、`client-sso-via-local-browser` 字符串），要弹本地浏览器完成统一身份认证再把 token 收回来。这套流程只在 Qt GUI + daemon 里实现，Python 写的 `seaf-cli` 没有。

> 解包探测的坑：探测时 `export` 的 `LD_LIBRARY_PATH` 指向 AppImage 的 `usr/lib`，会让系统 `curl` 加载其中捆绑的不兼容 `libcurl`，报 `undefined symbol: curl_global_trace`。在跨调用保持环境的粘性 shell（如 portal 的 bash 会话）里尤其注意，切回普通命令前 `unset LD_LIBRARY_PATH PYTHONPATH` 并重置 `PATH`。

结论：该部署上 headless 同步客户端是死路，文件交互走 WebDAV 或分享 API。

## <a id="webdav-rclone"></a>WebDAV 配 rclone

WebDAV 是该部署留给无人值守场景的门，rclone 以 `webdav` 类型接入即可。`rclone.conf` 关键字段：

```ini
[<remote名>]
type = webdav
url = https://pan.ustc.edu.cn/seafdav/
vendor = other
user = <学号或工号>@auth.local
pass = <rclone obscure 编码后的密码>
```

- **多账号**：每个账号配置独立 remote。跨账号复制通常经本机下载并上传。使用支持服务端操作的同一 remote 时，复制或移动可由 WebDAV 的 `COPY` 或 `MOVE` 完成，具体取决于后端和命令。[rclone 服务端复制说明](https://rclone.org/docs/#server-side-copy)
- **`obscure` 的语义**：可逆混淆而非加密——AES-CTR 用程序内嵌的固定密钥（全平台全设备相同），随机 IV 只让每次编码结果不同，`rclone reveal` 任何机器上都能还原。所以配置文件的实际保护只有文件权限（600）；把 obscure 串对外分享时按明文对待。需要真加密用 `rclone config encryption set` 给整个配置加主密码，代价是每次使用要解锁。
- **大批量传输**：加 `--timeout 60s --low-level-retries 5 --transfers 4` 更稳。实测（2026-06，当时测量链路）单流下载稳定在 ~53 MB/s（9 GB zip 用时 172s），与 WebDAV 页面自己的「慢」警告并不冲突——那说的是把它当文件系统挂载（davfs2）时的按需请求开销，纯 `rclone copy` 的 GET 不受影响。
- 官方页面推荐的 Linux 命令行方案 davfs2（`apt install davfs2` + `mount -t davfs`）需要 sudo 且网络抖动时挂载点整体卡死；按需挂载的场景 `rclone mount` 可替代。

## <a id="share-api"></a>分享链接的匿名下载 API

在 2026-06 的部署观察中，`/share/index/<token>` 页面通过下列接口取回分享详情。`share_id` 是分享链接的 token，有密码保护时还需传 `password`。通过受控客户端在进程内读取凭据并编码查询参数。

```text
GET /api/v1/share/get_share_detail?share_id=<token>&password=<分享密码>
```

> 分享密码在查询字符串里，临时下载直链本身也有访问权限。把两者留在受控客户端内，避免出现在命令行参数、会话输出和代理访问日志中。检查响应时只输出所需的状态或文件元数据。

- **无需任何账号**即返回 JSON：分享者、资料库、路径、过期信息，以及文件列表——每项带 `name`、`size`、`download_link`（指向 seafhttp 的直链）。
- `download_link` 是**一次性短时 token**：每次下载前重新调 `get_share_detail` 刷新再下，不要缓存复用。
- 直链支持 **Range 请求**：可先拉头几 MB 验证文件类型（`curl -r 0-3145727`）再决定整包下载。
- 同链路实测下载 ~52 MB/s，与 WebDAV GET 一致。
- 同在 `/api/v1` 下的 `get_shared_list` 不是这条路（返回 401）：那是登录用户管理自己分享列表的接口，访客路径只走 `get_share_detail`。


## <a id="macos-zip"></a>ZIP 文件名编码与解压

部分旧 ZIP 的文件名使用 UTF-8 或 GBK，却缺少 UTF-8 标志位。Python 的 `zipfile` 默认用 CP437 读取未标记的名称，可反向恢复原始字节。以下示例先尝试 UTF-8，再尝试 GBK，两种都不匹配时保留 CP437 原名。两种编码都能解码的名称需要依据来源核对。使用独占的空目录或尚不存在的目标路径，解析后的写入路径须落在该目录内，遇到重名文件会停止。

```python
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath


def member_name(info):
    name = info.orig_filename
    if info.flag_bits & 0x800:
        return name
    raw = name.encode("cp437")
    for encoding in ("utf-8", "gbk"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return name


root = Path("<目标目录>").resolve()
root.mkdir(parents=True, exist_ok=True)
if any(root.iterdir()):
    raise ValueError("请使用空的目标目录")

with zipfile.ZipFile("<ZIP 路径>") as archive:
    for info in archive.infolist():
        name = member_name(info)
        path = PurePosixPath(name)
        target = root.joinpath(*path.parts).resolve()
        if (not path.parts or path.is_absolute() or ".." in path.parts
                or "\\" in name or "\x00" in name
                or target == root or not target.is_relative_to(root)):
            raise ValueError(f"ZIP 条目路径不安全：{name!r}")
        if "__MACOSX" in path.parts or path.name.startswith("._"):
            continue
        if stat.S_ISLNK(info.external_attr >> 16):
            raise ValueError(f"ZIP 条目是符号链接：{name!r}")
        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target.open("xb") as output:
                shutil.copyfileobj(source, output)
```

解压后和云盘列表核对文件数量及总字节数，统计时排除跳过的 macOS 元数据。[Python ZIP 文件名编码说明](https://docs.python.org/3.12/library/zipfile.html#zipfile.ZipFile)
