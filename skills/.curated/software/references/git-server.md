# 自建 Git 服务：Forgejo / Gitea 双栈（内网 WSL2 机 + 公网 git-SSH + CI runner）

> 本文同时覆盖 **Forgejo** 与 **Gitea**——两者是同源硬分叉，配置项、数据布局、CLI 子命令绝大部分逐字一致。**公共的部分讲一次，行为/默认值不同的地方单独标注**（差异速查见「第一部分」两张表，正文遇到时再就地点名）。
>
> 下文的部署是在 **Forgejo** 上实测的；每一步都给出 Gitea 等价做法。因为二者高度同构，整套流程换成 Gitea 通常只需改三处：**镜像名**（`codeberg.org/forgejo/forgejo` ↔ `gitea/gitea`）、**env 前缀**（`FORGEJO__` ↔ `GITEA__`，注意 `GITEA__` 在两家都通，见「第二部分」）、**runner**（`forgejo-runner` ↔ `act_runner`）。
>
> 用占位符代替具体主机/IP/用户名，换台机器按自己环境替换：
>
> - `<server>` / `<cli>`：跑的是哪家——容器即 Forgejo 或 Gitea，`<cli>` 即容器内的 `forgejo` 或 `gitea` 二进制（子命令同名）。
> - `<内网机>`：`<server>` 实际运行的机器（本部署是团队后端机：Windows host + 内嵌 WSL2 Ubuntu + Docker Desktop，在 EasyTier mesh 内，无独立公网 IP）。
> - `<MESH_IP>`：`<内网机>` 的 mesh IP（relay 的目的地址）。
> - `<MESH_SSH_PORT>`：`<内网机>` 上 sshd 监听、relay 连进去的端口（按你内网机实际填，本部署是 2222；地位同 `<MESH_IP>`，环境相关）。
> - `<user>`：`<内网机>` 上的部署/运维用户（在 docker 组，免 sudo 跑 docker）。
> - `<入口VPS>`：唯一有公网 IP 的机器，做公网入口（本部署是一台 RHEL 系、未备案的云 VPS）。
> - `<PUBLIC_IP>`：`<入口VPS>` 的公网入口地址，**可以是 IP，也可以是域名**（本部署后来改用了域名）。web 入口与 SSH 入口还能拆到不同主机（下文称 `<WEB_HOST>` / `<SSH_HOST>`）；最简单的单机情形里三者就是同一个值。
> - `<SSH_PORT>`：git-over-SSH 对外端口。两种方案取值不同（见 ④）：**relay 方案**复用标准 **22**；**内置 SSH 方案**用一个**专用端口**（22 留给入口机自己的运维 sshd，本部署用的是 222）。
>
> 其余端口 3000 / 2376 是设计固定值，按原样保留即可。

---

# 第一部分 · 选型：Forgejo vs Gitea

## 同源与现状

二者 **2024-02 硬分叉**（共同祖先 commit `6992ef98`），功能高度重叠——Actions CI、~24 种包仓库、PR/Issue/Wiki/Projects、Mermaid/asciinema、色盲主题都各有。本文 clone 两边完整源码 `git grep` 实查（撰写时 HEAD：**Forgejo `v16.0.0-dev`** / **Gitea `v1.27.0-dev`**），逐条核对了下面的差异。

- **Forgejo** 是 Gitea 的社区硬分叉，非营利的 **Codeberg** 平台就跑它（[codeberg.org](https://codeberg.org/)）。自建可得到和 Codeberg 同款软件。**GPLv3+**（强 copyleft，二次开发须开源）。
- **Gitea** 是被分叉的原项目，**MIT**（宽松，可闭源分发），背后有 Gitea Ltd 商业公司。
- **2025–2026 一批 FOSS 项目从 GitHub 迁向 Codeberg(Forgejo)**：标杆是 Zig 语言 2025-11 迁过去（[codeberg.org/ziglang/zig](https://codeberg.org/ziglang/zig)，仓库 `created 2025-11-25`、`original_url` 指向原 GitHub 仓可佐证）。社区讨论里逃离 GitHub 的常见原因是 Actions/可用性不稳、平台劣化、强推 AI、价值观分歧（这些是社区舆论，未逐条核证）。GitLab、sourcehut 是另两个去向。
- **对自建的意义**：两家都能让 CI 完全跑在自己机器上（Forgejo + `forgejo-runner` / Gitea + `act_runner`），不受第三方平台掉线影响。

## 差异速查（一）· 功能有无

> 「✅/❌」指**当前源码**里有没有这条功能的真实现（区别于残桩）。每行给源码依据，可自行 `git grep` 复核。

| 功能 | Forgejo | Gitea | 源码依据（2026-06 实查各自 HEAD） |
| --- | --- | --- | --- |
| License | **GPLv3+** | **MIT** | 各自仓库根 `LICENSE` |
| 联邦化 ActivityPub（跨实例关注 / star） | ✅ 真实现，admin 带 Federation 管理页 | ❌ 仅 `NotImplemented` 桩 | F：`routers/api/v1/api.go` 挂 `/activitypub`、`misc/nodeinfo.go`（注释"for federation"）；G：`routers/api/v1/activitypub/person.go` 全返回 `http.StatusNotImplemented`(501) |
| 存储配额 Quota（按用户/组织限额） | ✅ 有 | ❌ 无 | F：`models/quota/`、`modules/setting/quota.go`；G：无 `models/quota`、无 `[quota]` |
| 内容举报 / 审核 Moderation | ✅ 有 | ❌ 无 | F：`services/moderation/reporting.go`、`modules/setting/moderation.go`、`/report_abuse` 路由；G：均无 |
| `.glb`/`.gltf` 3D 模型预览 | ✅ 有（Google **`@google/model-viewer`** web component） | ✅ 有（**`online-3d-viewer`**，经外部 markup 渲染器注册） | F：`package.json` 依赖 `@google/model-viewer`、模板 `<lazy-webc tag="model-viewer">`；G：`web_src/js/render/plugins/frontend-viewer-3d.ts` + `modules/markup/external/external.go` 注册 `*.glb`/`*.gltf`。**两家都有、实现不同** |
| Jupyter `.ipynb` 渲染 | ❌ 无 | ✅ 有 | G：`modules/markup/jupyter/jupyter.go`（注册 `*.ipynb` 渲染器）；F：无 `modules/markup/jupyter` |
| Git LFS over SSH（`git-lfs-transfer` 纯 SSH 协议） | ❌ 仅残留 | ✅ 有 | G：`modules/lfstransfer/` 实现 + `modules/git/cmdverb.go` `CmdVerbLfsTransfer="git-lfs-transfer"`；F：仅测试串里出现 |
| 包仓库独有生态 | **ALT Linux** | **Terraform** | `modules/packages/` 两家目录仅差此二者：F 多 `services/packages/alt/` + `/api/packages/.../alt` 路由；G 多 `modules/packages/terraform/` |
| 前端构建链 | Webpack + npm | Vite + pnpm | F：`webpack.config.js`、`package.json` 无 `packageManager`；G：`vite.config.ts`、`package.json` `"packageManager":"pnpm@..."` |

## 差异速查（二）· 行为 / 默认值

> 这些**功能两家都有**，但同一个开关取值不同、或命名不同、或一家多一段逻辑——配置时最容易踩。

| 维度 | Forgejo | Gitea | 源码依据 |
| --- | --- | --- | --- |
| 配置 **env 前缀** | `FORGEJO__` **或** `GITEA__`（双通，后者向后兼容） | **仅** `GITEA__` | `modules/setting/config_env.go:17`：F=`"^(FORGEJO\|GITEA)__"` / G=`"GITEA__"` |
| 默认 **session cookie 名** | `session` | `i_like_gitea` | `modules/setting/session.go:37`（各自 `MustString(...)`） |
| 默认 **「记住我」cookie 名** | `persistent` | `gitea_incredible` | `modules/setting/security.go`（`COOKIE_REMEMBER_NAME`） |
| `USE_COMPAT_SSH_URI` 默认 | **`true`**（→ `ssh://` 形式） | **`false`**（→ scp-like 短地址） | `modules/setting/repository.go`：F=`MustBool(true)` / G=`MustBool()`（零值 false） |
| `ComposeSSHCloneURL` 的 `(DOER_USERNAME)` | ❌ 无 | ✅ 有（clone URL 用户名换成当前登录名） | `models/repo/repo.go`：G 多一个 `doer` 形参 + `DOER_USERNAME` 分支 |
| 内置**密码登录**开关 | `[service] ENABLE_INTERNAL_SIGNIN`（默认 `true`） | `[service] ENABLE_PASSWORD_SIGNIN_FORM`（默认 `true`） | `modules/setting/service.go`：命名不同、语义对应 |
| Actions **日志 REST API** | per-job 文本 **+** per-run zip | **仅** per-job 文本 | `routers/api/v1/repo/`：F=`repoGetActionJobLogs`+`repoGetActionRunLogs`；G=仅 `downloadActionsRunJobLogs` |
| `DEFAULT_ACTIONS_URL`（`uses:` 不带 host） | `https://data.forgejo.org` | `https://github.com` | `modules/setting/actions.go` |
| Actions job **状态枚举** | 1–7（…7=Blocked） | 1–**8**（多 `8=Cancelling`） | `models/actions/status.go` |
| 官方 **runner** | **forgejo-runner**（镜像 `data.forgejo.org/forgejo/runner`） | **act_runner**（镜像 `gitea/act_runner`，独立项目） | 两个独立仓库 |

> **两家相同、易被误以为有差异的几项**（实查均一致，正文按公共处理）：`SESSION_LIFE_TIME` 默认 **86400**（1 天）、`LOGIN_REMEMBER_DAYS` 默认 **31**（旧资料常说 Gitea 是 7，**已过时**——当前两家源码都 31，见 `modules/setting/security.go`）、OAuth 登录都不触发「记住我」、Actions 都**默认启用**、非 rootless 数据目录都是 `/data`、`serv`/`keys`/`admin auth add-oauth`/`actions generate-runner-token` 子命令都同名。

## 一句话选型

> 要**联邦化 / 配额 / 审核 / ALT 包仓** → **Forgejo**；要 **Jupyter 渲染 / SSH 传 LFS / Terraform 包仓** → **Gitea**；要**闭源二次开发**只能 **Gitea(MIT)**（Forgejo 是 GPLv3+）。其余日常功能基本对等，下文部署对两者通用。

---

# 第二部分 · 通用底座（两家通用，先讲一次）

下面这些在 Forgejo 和 Gitea 上**完全一致**，是后面部署步骤反复用到的公共约定，先集中讲清楚，正文不再重复。

## 镜像、rootless 与数据布局

官方镜像都分两种（[Forgejo docker.md](https://forgejo.org/docs/latest/admin/installation/docker/) / Gitea README 指向 Docker Hub）：

| | 非 rootless（本部署用这个） | rootless（`-rootless` 后缀） |
| --- | --- | --- |
| Forgejo 镜像 | `codeberg.org/forgejo/forgejo:15`（或 `:16`） | `…/forgejo:15-rootless` |
| Gitea 镜像 | `gitea/gitea:1.24`（Docker Hub） | `gitea/gitea:1.24-rootless` |
| 容器内身份 | 以 root 启动再降权到 `git` | 全程不以 root 跑（需配 `user: 1000:1000`，SSH 映射到 `:2222`） |
| 数据目录 | **`/data`**（`GITEA_CUSTOM=/data/gitea`，git 仓库在 `/data/git/repositories/`） | `/var/lib/gitea` |
| `app.ini` 路径 | **`/data/gitea/conf/app.ini`**（两家一致） | F：`/var/lib/gitea/.../conf/app.ini`；**G：`/etc/gitea/app.ini`**（rootless 下两家此处不同） |

源码依据：非 rootless `GITEA_CUSTOM=/data/gitea` 见两家 `Dockerfile`；rootless `GITEA_APP_INI` 差异见两家 `Dockerfile.rootless`。**注意数据目录、`GITEA_CUSTOM` 这些环境变量名两家都带 `GITEA` 前缀**（Forgejo 沿用未改名），别被名字误导。

**为什么用非 rootless**：本部署跑在 Docker Desktop / WSL2 + bind mount 下，rootless 镜像常因宿主目录属主/权限重映射出问题（官方文档专门提醒过这类权限坑）；而本部署只把 `./data` 一个目录挂进容器、不碰宿主敏感路径，root 容器的额外风险很小。

> **别和 "rootless Docker" 混了——这是两个不同的层：**
> - **镜像 rootless**（本节说的 `-rootless` 后缀）：只管**容器内 app 进程**用 uid 1000 还是容器 root，**不改变**你启动容器要不要权限——两种镜像都一样 `docker compose up`。
> - **引擎 rootless**（rootless Docker / Podman）：让 docker 守护进程以**普通用户**跑，**用它无需 root 或 `docker` 组**。这才是决定"要不要 sudo"的层，也是多租户 / 拿不到 root 的共享机给你的模式。
>
> 所以 rootless **镜像**的安全收益主要在 **rootful 引擎**上才明显（本部署即此：在 `docker` 组 ≈ 有 root，容器内 root = 宿主/VM 的 root，这时换 rootless 镜像才算纵深防御）。而在 **rootless 引擎**下，连非 rootless 镜像的容器 root 也被 user namespace 重映射成普通 uid，宿主已被引擎保护，镜像选哪个更无所谓。本部署是**单租户 + rootful 引擎 + 自己人才在 docker 组**，故这层纵深防御省得起。

**挂载路径必须匹配镜像类型**：非 rootless 就写 `./data:/data`。最容易踩的坑是给非 rootless 镜像错写成 `./data:/var/lib/gitea`——容器根本不读这个路径，会自己在 `/data` 上挂一个 **docker 匿名卷**：数据看着正常，其实落在匿名卷里，`docker compose down -v` 或换 compose 就丢、也难备份。自查：

```
docker inspect <server> --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{println}}{{end}}'
```

要能看到 `… -> /data`；且宿主 `./data` 里应有 `git/ gitea/ ssh/` 三块，空的就是挂错了（修复见「关键坑 · 数据落进匿名卷」）。

## 配置注入：env 前缀 + CLI 子命令对照

**env → app.ini 注入**：两家容器入口都跑 `environment-to-ini`，把 `<PREFIX>__<SECTION>__<KEY>=<值>` 写进 `app.ini` 的 `[<section>]`。关键差异（`modules/setting/config_env.go:17`）：

- **Gitea 只认 `GITEA__`**；
- **Forgejo 认 `FORGEJO__` 和 `GITEA__` 两者**（正则 `^(FORGEJO|GITEA)__`，`GITEA__` 是向后兼容）。

> ⇒ **想让同一份 compose 在两家都能用，env 全用 `GITEA__` 前缀即可**（它在 Forgejo 上也生效）。本文 compose 示例用 `FORGEJO__`（Forgejo 版更地道）；跑 Gitea 时把前缀换成 `GITEA__`，或干脆一开始就写 `GITEA__`。section / key 名两家逐字一致，无需改。

> ⚠️ **env 是权威源，每次启动覆盖 `app.ini`**：容器入口每次启动都用这些 env 重新生成 `app.ini`，所以**手改 `app.ini` 不持久**——下次启动即被覆盖回 env 的值。改配置（如 `[server]` 的 `ROOT_URL` / `DOMAIN`）必须改 compose 的 `environment:`，再 `docker compose up -d <svc>` **重建**容器生效；`docker compose restart` 不重建容器、不重读 `environment`，对改过的 env **不生效**。

**CLI 子命令对照**（容器内 `docker exec -u git <server> <cli> …`，`<cli>` = `forgejo` 或 `gitea`，子命令同名）：

| 用途 | 命令（`<cli>` = forgejo / gitea） | 出处 |
| --- | --- | --- |
| SSH 查公钥（内部） | `<cli> keys …` | 两家 `cmd/keys.go` |
| SSH 跑 git transport（内部） | `<cli> serv <key> …` | 两家 `cmd/serv.go` |
| 加 OAuth 登录源 | `<cli> admin auth add-oauth --name … --provider … --key … --secret …` | 两家 `cmd/admin_auth_oauth.go` |
| 生成 runner 注册 token | `<cli> actions generate-runner-token` | F `cmd/forgejo/actions.go` / G `cmd/actions.go` |

`serv` / `keys` 是官方 SSH 直连模式内部就在调的原生子命令（④ 的 relay 方案把它们"借"出来跨机用）。

---

# 第三部分 · 部署 runbook（双栈）

## 目标与难点

`<内网机>` 用 docker compose 跑 `<server>`，但它没有公网 IP；唯一的公网落点是 `<入口VPS>`。要在不破坏 `<入口VPS>` 自身运维的前提下，把三件事透到内网：

- `ssh <user>@<PUBLIC_IP>` → 仍是 `<入口VPS>` 自己的运维 shell（**不能被破坏**）。
- `git clone` 透到内网 `<server>`（端口随方案：**A 用一个专用端口、B 复用标准 22**，见 ④）。
- web UI + git-over-HTTPS → 经边缘 Caddy 反代（`https://<PUBLIC_IP>:3000/`；本部署 VPS 未备案，只能用 IP + `tls internal` 自签证书，client 需 `-k`）。

git-SSH 的难点全在「入口机的 22 已经是它自己的运维 sshd」这一条上，两套方案各自绕开它：

- **方案 A（本部署在用）**：git 走一个**专用端口**，入口机对该端口做**无脑 TCP 转发**（不碰 sshd），git 落到 `<server>` 内置 SSH server。最简单；代价是 clone URL 带端口（`ssh://…:<port>/`）。
- **方案 B**：要 git 也复用**标准 22**（clone URL 不带端口、像 GitHub）。靠 **SSH passthrough + 跨机 relay**：入口机 sshd 按**登录用户名**分流——`git` 用户的请求经 relay 转进容器，其它用户走全局默认 shell，完全不受影响。

> 内置 SSH server、`serv`/`keys` 子命令、relay 的所有逻辑 Forgejo 和 Gitea **完全一致**（同名命令、同 `--config /data/gitea/conf/app.ini` 路径）；下面 ④ 的脚本把 `<cli>` 换成 `forgejo`/`gitea` 即可，无其它改动。

## 整体架构

`<server>` 本体 + web + CI 都在内网 `<内网机>` 的 docker 里（①②⑤），唯一的公网落点是 `<入口VPS>`。**web/HTTPS 统一走 ② 的边缘 Caddy 反代**；**git-over-SSH 有两套方案、二选一**（④）——下面两张图分别是它们的链路（运维 shell、web 都不受影响）。

**方案 A：内置 SSH + dumb TCP 转发（本部署在用，更简单）**——入口机只做一层无脑 TCP 转发，git 落到 `<server>` 自己的内置 SSH server。

```mermaid
flowchart LR
    C[client]

    subgraph VPS["#60;入口VPS#62; 公网落点"]
        FWD2["socat 专用端口<br/>(dumb TCP 转发)"]
        CADDY[边缘 Caddy]
    end

    subgraph NEI["#60;内网机#62; WSL2 + docker (无公网IP)"]
        FG[(#60;server#62; 容器<br/>内置 SSH server)]
        RUN[runner + DinD]
    end

    C -- "ssh git@ 专用端口" --> FWD2
    C -- "https :3000" --> CADDY

    FWD2 -- "TCP 原样转发" --> FG
    CADDY -- "reverse_proxy" --> FG
    FG --> RUN
```

**方案 B：公网 SSH relay（复用 22，clone URL 无端口短地址）**——入口机 sshd 按登录名分流，`git@` 经 relay 查 key / 跑 git，`<user>@` 仍是正常运维 shell。

```mermaid
flowchart LR
    C[client]

    subgraph VPS["#60;入口VPS#62; 公网落点"]
        SSHD[sshd :22]
        CADDY[边缘 Caddy]
    end

    subgraph NEI["#60;内网机#62; WSL2 + docker (无公网IP)"]
        FWD["git 用户 forced cmd"]
        FG[(#60;server#62; 容器)]
        RUN[runner + DinD]
    end

    C -- "ssh git@ :22" --> SSHD
    C -- "ssh #60;user#62;@ :22" --> SSHD
    C -- "https :3000" --> CADDY

    SSHD -- "git 用户: AuthorizedKeysCommand" --> FWD
    SSHD -. "其它用户: 全局默认 (不动)" .-> OPS[运维 shell]
    CADDY -- "reverse_proxy" --> FG
    FWD -- "docker exec #60;server#62; keys/serv" --> FG
    FG --> RUN
```

> 两方案里"转发/relay 这一跳"（`<入口VPS>` → `<内网机>`）都走 EasyTier mesh，不经公网。

**方案 B 的两步**（方案 A 没有这套——内置 server 直接查库、连入口机都不碰）：`git clone git@<PUBLIC_IP>:…` 实际分两步，都由 `<入口VPS>` 的脚本经 relay 转发到内网、再 `docker exec` 进容器：

1. **查 key**：sshd 的 `AuthorizedKeysCommand` 当场问"这把公钥是谁的"→ relay → `docker exec <server> <cli> keys` 查数据库 → 返回一行带 forced command 的 `authorized_keys`。
2. **跑 git**：那行 forced command → relay → `docker exec -i <server> <cli> serv key-N` 收发 git 数据。

> **方案 B：为什么网页端加一把 SSH key，公网入口机马上就认得？** 因为入口机的 `git` 用户**没有** `authorized_keys` 文件——sshd 配的是 `AuthorizedKeysCommand`，每次连接**当场**经 relay 查数据库里的公钥表（网页端加的 key 正存在这里）。key 始终只在 `<server>` 数据库里，**从不拷到入口机**。

下面按 ①内网机服务本体 → ②web 入口 → ③登录/会话 → ④git-SSH（二选一）→ ⑤CI 的顺序部署。

## ① 内网机：服务本体 + PostgreSQL

`<内网机>` 上建个目录（本部署是 `~/forgejo/`，路径随意），放下面的 `docker-compose.yml`。这份文件**一次写全**，含后面 ⑤ 要用的 `docker-in-docker` / `runner` 两个容器（先只起 `server` `db`，runner 要注册后再起）。其中 `server`+`db` 来自官方 [docker.md](https://forgejo.org/docs/latest/admin/installation/docker/) 的 PostgreSQL 示例，`docker-in-docker`+`runner` 来自官方 [Actions runner 文档](https://forgejo.org/docs/latest/admin/actions/installation/docker/)：

```yaml
networks:
  forgejo:
    external: false

volumes:
  docker_certs:

services:
  server:
    image: codeberg.org/forgejo/forgejo:15
    container_name: forgejo
    environment:
      - USER_UID=1000
      - USER_GID=1000
      - FORGEJO__database__DB_TYPE=postgres
      - FORGEJO__database__HOST=db:5432
      - FORGEJO__database__NAME=forgejo
      - FORGEJO__database__USER=forgejo
      - FORGEJO__database__PASSWD=${POSTGRES_PASSWORD}
      - FORGEJO__server__DOMAIN=<WEB_HOST>
      - FORGEJO__server__ROOT_URL=https://<WEB_HOST>/
      - FORGEJO__server__HTTP_PORT=3000
      - FORGEJO__server__SSH_DOMAIN=<SSH_HOST>
      - FORGEJO__server__SSH_PORT=22
      - FORGEJO__server__START_SSH_SERVER=false
      - FORGEJO__server__DISABLE_SSH=false
      - FORGEJO__service__DISABLE_REGISTRATION=true
      - FORGEJO__security__INSTALL_LOCK=true
      - FORGEJO__session__COOKIE_NAME=forgejo_<unique>
    restart: unless-stopped
    networks:
      - forgejo
    volumes:
      - ./data:/data
      - /etc/timezone:/etc/timezone:ro
      - /etc/localtime:/etc/localtime:ro
    ports:
      - "127.0.0.1:3000:3000"
    depends_on:
      - db

  db:
    image: postgres:14
    container_name: forgejo-db
    restart: unless-stopped
    environment:
      - POSTGRES_USER=forgejo
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - POSTGRES_DB=forgejo
    networks:
      - forgejo
    volumes:
      - ./postgres:/var/lib/postgresql/data

  docker-in-docker:
    image: data.forgejo.org/oci/docker:dind
    container_name: forgejo-dind
    hostname: docker
    privileged: true
    restart: unless-stopped
    environment:
      - DOCKER_TLS_CERTDIR=/certs
    networks:
      - forgejo
    volumes:
      - docker_certs:/certs
      - ./dind:/var/lib/docker

  runner:
    image: data.forgejo.org/forgejo/runner:12
    container_name: forgejo-runner
    restart: unless-stopped
    depends_on:
      - server
      - docker-in-docker
    environment:
      - DOCKER_HOST=tcp://docker:2376
      - DOCKER_CERT_PATH=/certs/client
      - DOCKER_TLS_VERIFY=1
    networks:
      - forgejo
    volumes:
      - ./runner:/data
      - docker_certs:/certs
    command: forgejo-runner --config /data/config.yml daemon
```

> **跑 Gitea 的等价 compose**：把 `server.image` 换成 `gitea/gitea:1.24`、env 前缀 `FORGEJO__`→`GITEA__`（section/key 不变；也可直接保留 `GITEA__`，它在 Forgejo 上也通，见第二部分），`runner` 换 `gitea/act_runner`（注册命令见 ⑤）。`db` / `docker-in-docker` 不用动；`docker-in-docker` 也可改用 Docker Hub 的 `docker:dind`。其余字段逐字一致。

换机要改的值：

- **`ROOT_URL` / `SSH_DOMAIN` / `DOMAIN` 三者含义不同**，都可填 IP 或**域名**（本部署用的就是域名，且 web 与 SSH 还指向不同主机）；别一股脑填同一个值。理解关键：**"网页 URL""HTTPS clone 地址""SSH clone 地址"是三件事，但只有第一件是功能性的，后两件本质是展示**——
  - **`ROOT_URL`（功能性，最重要）** = 网页对外地址。浏览器地址栏、页面/邮件里生成的所有链接、**GitHub OAuth 回调的 base**（回调 = `<ROOT_URL>/user/oauth2/<name>/callback`）都用它；**HTTPS clone 地址不是独立配置项，而是由它派生**（`<ROOT_URL><owner>/<repo>.git`）。所以"改 HTTPS clone 显示"≡"改 `ROOT_URL`"，而改 `ROOT_URL` 会连带影响 web 访问和 OAuth。它必须和浏览器**实际**访问方式逐字一致：经边缘域名 + 443 就写 `https://<WEB_HOST>/`；边缘在非标端口上自签（如 `:3000`）就写 `https://<WEB_HOST>:3000/`。改了它，GitHub OAuth App 的回调 URL 要同步改。
  - **`SSH_DOMAIN`（+ `SSH_PORT`，纯展示）** = 只决定仓库页「Clone」框里 SSH 地址显示成 `git@<SSH_DOMAIN>:…`（端口取 `SSH_PORT`、形式见下「scp-like vs ssh://」）。**实际 SSH 连到哪，由 `<SSH_HOST>` 的 DNS + 入口机那一跳决定，`<server>` 不参与**——所以它可以指向和 web **完全不同的主机**（本部署 web 走一台边缘、SSH 直连另一台境内机，就是靠这里拆开的）。单独改它只动仓库页显示、不影响连通。`SSH_PORT` 是展示端口；和内置 SSH server 的真实监听口 `SSH_LISTEN_PORT` 是两回事——**relay 方案**（④ B）`START_SSH_SERVER=false`、用不到 `SSH_LISTEN_PORT`，`SSH_PORT=22` 只为展示；**内置方案**（④ A）`START_SSH_SERVER=true`、`SSH_PORT` 填专用端口、`SSH_LISTEN_PORT` 填容器内高端口。
  - **`DOMAIN`（默认值种子）** = 仅在 `ROOT_URL` / `SSH_DOMAIN` 没显式设时，拿它推默认值（`ROOT_URL` 默认 `{PROTOCOL}://{DOMAIN}:{HTTP_PORT}/`，`SSH_DOMAIN` 默认取 `DOMAIN`）。两者都显式写了时，`DOMAIN` 基本不再单独起作用；填成 web host 保持整洁即可。
- `START_SSH_SERVER` / `DISABLE_SSH`：选哪条 git-SSH 路线（见 ④ 二选一）。**relay 方案**（B）`START_SSH_SERVER=false`（关掉内置 server，容器不监听 SSH，git transport 由 relay + `<cli> serv` 承担）；**内置方案**（A）`START_SSH_SERVER=true`（起内置 server，另配 `SSH_PORT` / `SSH_LISTEN_PORT` 与端口发布，见 ④ 方案 A）。两者都要 `DISABLE_SSH=false` 才保留 SSH 克隆能力。**这 4 个 key（`START_SSH_SERVER` / `DISABLE_SSH` / `SSH_PORT` / `SSH_LISTEN_PORT`）两家同名同义**，默认 `SSH_PORT=22`、`StartBuiltinServer=false`（源码 `modules/setting/ssh.go`）。
- `COOKIE_NAME` 设成一个**独特名**（见「关键坑 · cookie 改名」）。
- `POSTGRES_PASSWORD` 放同目录 `.env`（`POSTGRES_PASSWORD=...`，权限 600），compose 用 `${POSTGRES_PASSWORD}` 引用。
- 镜像 tag `forgejo:15` 里的 `15` 会自动跟最新 15.x；Gitea 同理用 `gitea/gitea:1.24` 跟 1.24.x。Forgejo `:16` 带 ⑤ 的 per-run zip 日志 API（撰写时 16 仍在 dev）。

起服务：`docker compose up -d server db`，再 `curl -I http://127.0.0.1:3000/` 应得 200。

### SSH 克隆地址形式：scp-like vs `ssh://`（`USE_COMPAT_SSH_URI`）

Web 上「Clone」按钮给的 SSH 地址有两种写法，由 `[repository] USE_COMPAT_SSH_URI` + `SSH_PORT` 共同决定。生成逻辑就三个分支（两家源码 `models/repo/repo.go` 的 `ComposeSSHCloneURL`，逐字一致）：

| 条件 | 生成形式 |
|---|---|
| `SSH_PORT != 22` | `ssh://git@<host>:<port>/<owner>/<repo>.git`（带端口，只能 `ssh://`） |
| `SSH_PORT == 22` 且 `USE_COMPAT_SSH_URI = true` | `ssh://git@<host>/<owner>/<repo>.git`（无端口的 `ssh://`） |
| `SSH_PORT == 22` 且 `USE_COMPAT_SSH_URI = false` | `git@<host>:<owner>/<repo>.git`（**scp-like**，即 GitHub 那种） |

**想要 GitHub 那种 scp-like 短形式** → 显式设 `USE_COMPAT_SSH_URI=false`（本部署经 compose 注入）：

```yaml
- FORGEJO__repository__USE_COMPAT_SSH_URI=false   # Gitea 默认就是 false，无需设；Forgejo 默认 true 必须显式关
```

改完 `docker compose up -d server` 重建容器即可；可用 `docker exec -u git <server> grep -i USE_COMPAT_SSH_URI /data/gitea/conf/app.ini` 确认落盘，再查 API `ssh_url` 字段验证生成形式。

**为什么默认形式两家相反、这名字为什么叫「compat」**（源码 `modules/setting/repository.go`）：

- **Forgejo 默认 `true`**（`Repository.UseCompatSSHURI = sec.Key("USE_COMPAT_SSH_URI").MustBool(true)`）——所以**开箱即 `ssh://` 形式**，即便 22 端口、即便没写这一行。
- **Gitea 默认 `false`**（`MustBool()` 无参、取零值 false → scp-like）。两个项目默认值相反，**从 Gitea 迁到 Forgejo 会"莫名其妙变形式"**。
- **「compat」=「兼容早期 Gitea 的展示行为」**：这个开关由 Gitea [PR #2356](https://github.com/go-gitea/gitea/pull/2356)（2017-08 合入）引入。早期 Gitea **一直只用 `ssh://` 显式 URI**；后来把默认改成了 scp-like 短形式（更贴近 GitHub 习惯），于是加这个开关让你能**强制切回旧的 `ssh://` 形式**——"compat" 指的就是兼容这套老的 `ssh://` URI 展示，名字和直觉相反（compat 反而是 `ssh://`，不是 scp-like）。

> 两种写法在 22 端口下**功能完全等价**，落到同一个仓库。区别只在：scp-like 语法**无法表达端口**——所以一旦 `SSH_PORT != 22`，无论 `USE_COMPAT_SSH_URI` 设什么都只会给带端口的 `ssh://` 形式。本部署若 web 与 SSH 分流到不同入口（如 web 走域名经边缘反代、SSH 直连另一台），`SSH_DOMAIN` 单独指向 SSH 入口、`SSH_PORT=22` 保持，配 `USE_COMPAT_SSH_URI=false` 即得 `git@<ssh-host>:<owner>/<repo>.git`。

**源码核实（2026-06，对照 [go-gitea/gitea](https://github.com/go-gitea/gitea) + [forgejo/forgejo](https://codeberg.org/forgejo/forgejo) 当前源码）**：上表三分支两家**逐字一致**，都出自 `models/repo/repo.go` 的 `ComposeSSHCloneURL`——`if setting.SSH.Port != 22` 时强制走带端口 `ssh://`（源码注释原文 `// non-standard port, it must use full URI`），22 端口才在 `UseCompatSSHURI` 上二选一；IPv6 host 自动包 `[]`。所以"是 Gitea 还是 Forgejo"**只影响默认值、不影响分支判断**。Gitea 还自带单元测试 `models/repo/repo_test.go` 的 `TestComposeSSHCloneURL`，把结果钉成行为契约，可直接当真值表照搬：

| `SSH.Domain` | `SSH.Port` | `UseCompatSSHURI` | 断言输出 |
|---|---|---|---|
| `domain` | 22 | `false` | `git@domain:user/repo.git` |
| `domain` | 22 | `true` | `ssh://git@domain/user/repo.git` |
| `domain` | 123 | `false` | `ssh://git@domain:123/user/repo.git` |
| `domain` | 123 | `true` | `ssh://git@domain:123/user/repo.git`（与上行**相同** → 非 22 端口下开关失效）|
| `::1` | 22 | `false` | `git@[::1]:user/repo.git`（IPv6 host 自动包 `[]`）|
| `::1` | 123 | `false` | `ssh://git@[::1]:123/user/repo.git` |

**默认值的精确出处**（决定 app.ini 不写这条时取什么）——两家都在 `modules/setting/repository.go`，**写法不同、结果相反**：

| | ini 解析行 | 缺省值 |
|---|---|---|
| **Forgejo** | `Repository.UseCompatSSHURI = sec.Key("USE_COMPAT_SSH_URI").MustBool(true)` | **`true`**（`ssh://`）|
| **Gitea** | `... .MustBool()`（**无参**，取零值；结构体默认也是 `false`）| **`false`**（scp-like）|

**Gitea 独有的 `(DOER_USERNAME)` 变体**（和本部署的 SSH 反代/relay 架构相关）：Gitea 的签名是 `ComposeSSHCloneURL(doer, owner, repo)`，比 Forgejo 的 `ComposeSSHCloneURL(owner, repo)` 多收一个 `doer`——当 `SSH_USER`（`setting.SSH.User`）设成字面量 `(DOER_USERNAME)` 时，clone 地址里的 SSH 用户名替换成**当前登录用户名**（给"按用户预先准备公钥"的 SSH 反代用），拿不到 doer 时回落内置用户。Forgejo 没有这个分支（`models/repo/repo.go` 无 `DOER_USERNAME`，单元测试也只有 Gitea 测了这两条变体）。

## ② web 公网入口：Caddy 反代 + 默认中文

web UI + git-over-HTTPS 经 `<入口VPS>` 的边缘 Caddy 反代到 `<内网机>:3000`。`<server>` 容器只把 3000 发布到 `127.0.0.1:3000`（compose 里的 `ports: "127.0.0.1:3000:3000"`），不直接对外，对外只经 Caddy。Caddy → `<内网机>` 的具体链路（mesh / Windows portproxy / wslrelay / WSL→容器端口形态）是通用 WSL/Docker 网络问题，见 `network` skill 的「WSL / Docker 服务暴露（入站）」。

把整站默认语言设成简体中文：在 Caddy 里 `<server>` 的 `reverse_proxy` 子块加 `header_up Accept-Language "zh-CN"`，压过浏览器的 `Accept-Language`。未登录/未设语言的用户即默认中文；用户在右下角切过语言后会写 cookie，cookie 优先级更高、记住其选择。（中文 i18n、`Accept-Language` 优先级逻辑两家一致。）

## ③ 登录、注册与会话

下面这些开关 Forgejo / Gitea **绝大多数同名同义**，仅「内置密码登录开关」命名不同——就地标注。本部署经 compose `FORGEJO__<section>__<KEY>` 注入（Gitea 换 `GITEA__`）。

### 登录与注册控制（OAuth / 禁密码 / 禁注册）

- `[service] DISABLE_REGISTRATION = true` —— 关掉自助注册（没人能填表开新账号）。两家同。
- **关掉内置密码登录、只剩外部认证源（GitHub OAuth 等）**——**这条两家开关名不同**（`modules/setting/service.go`）：
  - **Forgejo**：`[service] ENABLE_INTERNAL_SIGNIN = false`（默认 `true`）。
  - **Gitea**：无 `ENABLE_INTERNAL_SIGNIN`；对应开关是 `[service] ENABLE_PASSWORD_SIGNIN_FORM = false`（默认 `true`，另有 `ENABLE_PASSKEY_AUTH` 管 passkey）。
- `[service] REQUIRE_SIGNIN_VIEW = true` —— **登录才可见**：未登录连公开仓库 / issue / 代码都看不到。默认 `false`（公开内容匿名可读）；**面向真实用户、不想裸奔的服务建议开 `true`**。两家同。
- `[oauth2_client] ENABLE_AUTO_REGISTRATION = true` —— 新 OAuth 用户**自动建号**（用户名取自 `[oauth2_client] USERNAME`，默认 GitHub nickname），免关联、免密码。默认 `false`。两家同。

OAuth 登录源用 CLI 加（等价 Web「站点管理 → 认证源」，**不在 `/api/v1`**，两家同名子命令 `admin auth add-oauth`）：

```bash
docker exec -u git <server> <cli> admin auth add-oauth \
  --name github --provider github --key <CLIENT_ID> --secret <CLIENT_SECRET>
```

GitHub OAuth App 回调填 `<ROOT_URL>/user/oauth2/<name>/callback`（`<name>` 要和 `--name` 一致）。

**准入门槛**：`DISABLE_REGISTRATION=true` 且未开自动注册（`[oauth2_client] ENABLE_AUTO_REGISTRATION` 默认 false）时，陌生 GitHub 账号首次登录会被要求「关联到已有账号」——必须输入一个**已有账号的用户名+密码**才能绑进来；没有已有账号密码的陌生人光有 GitHub 进不来。一个 GitHub 身份只能绑一个账号（`external_login_user.external_id` 唯一），关联只能本人走一次 OAuth 完成，CLI / admin 无法代绑。

**开 / 不开自动注册的取舍**：`ENABLE_AUTO_REGISTRATION=true` = **任何** GitHub 账号登录即自动建号、纯 OAuth 自助进（配合关掉内置密码登录就完全不维护用户名+密码）。但公网实例等于**全世界 GitHub 用户都能进来**建号、占 CI 算力，而 GitHub OAuth 无 org/team claim 可用 `--required-claim` 卡白名单（挡不住陌生人）。所以：

> - **公开社区** → 开 `ENABLE_AUTO_REGISTRATION=true`，这么配合理。
> - **私有 / 小团队** → **千万别开**，维持 `DISABLE_REGISTRATION=true` + auto-registration 关 + admin 预先建好号 + 成员手动关联，才挡得住陌生人。

> ⚠️ 关掉内置密码登录（Forgejo `ENABLE_INTERNAL_SIGNIN=false` / Gitea `ENABLE_PASSWORD_SIGNIN_FORM=false`）**前，所有要用 web 的账号都得先绑好 OAuth**。坑在于 `link_account`（关联已有账号）页复用登录页同一个 `signin_inner` 模板、用户名密码框被同一个条件（Forgejo `{{if .EnableInternalSignIn}}`）包着——一旦关掉，**没绑的账号连「GitHub 登录 → 输密码关联」这条补绑路也断了**（关联页同样没有密码框），只能临时把开关改回 `true` 开个窗口补绑、或 admin 改 DB 伪造绑定。admin 自己尤其要先绑，否则直接把自己锁在 web 外。

### 登录维持时间：`SESSION_LIFE_TIME` vs `LOGIN_REMEMBER_DAYS`（含"老是掉登录"根治）

两个**完全独立**的机制，别混（源码 `modules/setting/{session,security}.go`、`routers/web/auth/`、`models/auth/session.go`，**两家逻辑与默认值一致**）：

| | `[session] SESSION_LIFE_TIME` | `[security] LOGIN_REMEMBER_DAYS` |
|---|---|---|
| 管的东西 | **当前会话**（"我现在是登录态"）的服务端寿命 | **「记住我」长效 cookie**（`persistent`，存 DB 的 LTA token） |
| cookie | `COOKIE_NAME`，只存 session id；**无 Max-Age = 浏览器会话 cookie** | `COOKIE_REMEMBER_NAME`，**带 Max-Age = N 天的持久 cookie** |
| 默认 | 86400s = **1 天**（两家同） | **31 天**（两家同；旧资料说 Gitea 7 已过时，当前两家源码都 `MustInt(31)`） |
| 过期方式 | **滑动**：每次请求把 `Expiry` 刷成当前时间，最后一次活动后再过 `SESSION_LIFE_TIME` 才失效（≈"闲置超时"，正是 GitHub 的"用着就不掉"） | session 没了（过期/被清/存储丢）时，`autoSignIn` 读这个 cookie → 查 DB 验证 → **静默重建一个新 session**，免密码 |
| 何时设置 | 登录即建 | **仅密码登录且勾选「记住此设备」时**才写 |
| 扛重启吗 | 看 `PROVIDER`：`memory` 重启即清空（全员掉登录）；`db`/`file` 才扛得住 | 扛：它直查 DB 用户表，与 session 存储无关 |

> 默认 `COOKIE_REMEMBER_NAME` 两家不同：**Forgejo `persistent`、Gitea `gitea_incredible`**（`modules/setting/security.go`）。机制一样，只是 cookie 名。

**一句话区别**：`SESSION_LIFE_TIME` 是"当前这次登录能闲置多久"；`LOGIN_REMEMBER_DAYS` 是"掉了之后还能免密自动登回来多久"。前者是前线，后者是后备网。

**关键坑 —— OAuth 登录不触发 remember-me**（两家都如此）：`handleOAuth2SignIn`（GitHub OAuth 登录路径）只 `updateSession` 设 uid，**从不调 `SetLTACookie`**（密码登录路径 `handleSignInFull` 才调，Forgejo 是 `SetSSOLTACookie`/`SetLTACookie`、Gitea 是 `SetLTACookie`，源码 `routers/web/auth/{oauth,auth}.go`）——所以走 GitHub OAuth 进来的用户**根本不会有 `persistent` cookie**，`LOGIN_REMEMBER_DAYS` 对他们形同虚设（它只对密码登录 + 勾「记住我」生效，如本地 admin）。**OAuth 实例的登录维持 = 只看 `SESSION_LIFE_TIME` + session 存储是否持久。**

**要达到"几天不掉、用着自动续、像 GitHub"——按下面配（compose 注入 `FORGEJO__<section>__<KEY>` / Gitea 换 `GITEA__`）**：

```yaml
- FORGEJO__session__PROVIDER=db              # 关键!! 会话存进 Postgres,容器重启不再清登录
- FORGEJO__session__SESSION_LIFE_TIME=2592000 # 30 天(秒);滑动,即"闲置 30 天才掉"
- FORGEJO__session__GC_INTERVAL_TIME=86400    # 过期会话清理频率,无关寿命
- FORGEJO__security__LOGIN_REMEMBER_DAYS=30   # 仅对密码登录的「记住我」有效(OAuth 用户无感)
```

- **默认 `PROVIDER=memory` 是"老是掉登录"的头号元凶**：每次 `docker compose up`/重建容器，内存里所有会话全没，全员被登出。**改成 `db` 是治本**（用现有 Postgres，自动建 `session` 表，重启/重建都不掉）。`file`（落 `/data/gitea/sessions`，本部署 `./data` 已 bind mount）同样扛重启，但 `db` 更干净，首选。
- 改这几项要 `docker compose up -d server` 重建容器生效——**切 `memory`→`db` 这一下会把现存内存会话清掉、全员需再登录一次**，之后才稳。
- session cookie 无 Max-Age（两家都没暴露这个开关），**理论上彻底关掉浏览器会丢**；但现代浏览器的"恢复上次标签页"会把会话 cookie 带回来，体感上不掉。OAuth 实例没有 remember-me 这层后备，要更强的"关浏览器也不掉"只能靠浏览器自身的会话恢复。

## ④ git-over-SSH：内置 SSH 还是 relay（二选一）

git 的 SSH 传输有两条独立路线，**二选一**即可，web/HTTPS（②）不受影响。**这一节的内置 server、`serv`/`keys`、relay 逻辑 Forgejo / Gitea 完全一致**，脚本里 `<cli>` 换成 `forgejo`/`gitea` 即可。先看取舍再往下做：

| 维度 | 方案 A：内置 SSH + dumb TCP 转发 | 方案 B：公网 SSH relay |
|---|---|---|
| 入口 VPS 角色 | 纯 TCP 转发（一个 socat 单元），**完全不碰 sshd** | sshd 按登录名 `git` 分流 + 两个 relay 脚本 |
| 用哪个端口 | 一个**专用端口** `<SSH_PORT>`（入口机 22 留给运维 sshd） | 复用标准 **22** |
| clone URL | `ssh://git@<SSH_HOST>:<SSH_PORT>/owner/repo.git`（带端口） | `git@<SSH_HOST>:owner/repo.git`（scp-like 短地址，像 GitHub） |
| 入口机要装啥 | 只一个 socat 转发单元 | `git` 用户 + `AuthorizedKeysCommand` + 两个脚本 + relay 私钥 |
| 公钥怎么认 | 内置 server 直接查自己数据库 | 入口机每次连接经 relay 现查容器 `<cli> keys` |
| 复杂度 / 维护面 | 低 | 高（多机、多脚本、有 ControlMaster 等坑） |
| 什么时候选 | 能接受非 22 端口、想最简单直接 | clone URL 必须走标准 22 / 要 GitHub 式无端口短地址 |

> 两方案都要 `DISABLE_SSH=false`。区别只在 `START_SSH_SERVER`（A=`true` 起内置 server；B=`false`，git transport 由 relay + `<cli> serv` 承担）和入口机那一跳怎么搭。上面 ① 的 compose 是按 B 写的，选 A 就按「方案 A」改那几个 `FORGEJO__server__*` 并多发布一个端口。

### 方案 A：内置 SSH server + 入口机 dumb TCP 转发

最省事的一条：`<server>` 跑**自己的内置 SSH server**，入口 VPS 只做一层**无脑 TCP 端口转发**——不碰 sshd、不查 key、不装任何 forgejo/gitea 二进制。因为入口机的 22 已经是它自己的运维 sshd，这套用一个**专用端口** `<SSH_PORT>`（如 222 / 2222）。

**`<server>` 容器**：在 ① 的 compose 上改这几个环境变量（两家同名）——

```yaml
      - FORGEJO__server__START_SSH_SERVER=true        # 起内置 SSH server
      - FORGEJO__server__SSH_PORT=<SSH_PORT>          # 对外展示 + clone URL 用的端口
      - FORGEJO__server__SSH_LISTEN_PORT=<容器内端口>  # 容器内真实监听口（高端口，见下）
      - FORGEJO__server__SSH_DOMAIN=<SSH_HOST>        # clone URL 里显示的主机
      - FORGEJO__server__DISABLE_SSH=false
```

ports 里把内置 server 发布出来（发布到本机回环，对外由入口机转发；WSL 场景见下）：

```yaml
    ports:
      - "127.0.0.1:3000:3000"
      - "127.0.0.1:<SSH_PORT>:<容器内端口>"
```

要点：

- **`SSH_PORT`（展示）≠ `SSH_LISTEN_PORT`（容器内真实监听）**：容器以非 root（`USER_UID=1000`）跑、绑不了 <1024 的口，所以 `SSH_LISTEN_PORT` 用高端口（如 2222），再把它 publish 成 host 的 `<SSH_PORT>`。
- **`SSH_PORT != 22` ⇒ clone URL 自动是带端口的 `ssh://git@<SSH_HOST>:<SSH_PORT>/...`**（`USE_COMPAT_SSH_URI` 在非 22 下失效，见上「scp-like vs ssh://」真值表）。想要无端口 scp-like 短地址，要么走方案 B 的 22，要么你有一台**专门的 SSH 入口主机、其 22 空着**——那就把 `<SSH_PORT>` 设 22、转发该主机的 22。
- **主机密钥**：内置 server 用 `<data>/ssh/ssh_host_*`。容器以 uid 1000 跑，这些 key 必须能被 uid 1000 读——若原来是 `root:root 600`，`docker exec -u root <server> chown -R 1000:1000 /data/ssh` 修一下，否则 server 起不来。容器日志出现 `SSH server started on :<容器内端口>` 即成功。

**入口 VPS：一个 dumb TCP 转发（systemd + socat）**，把公网 `<SSH_PORT>` 原样转到内网机同端口，全程不碰 sshd：

```ini
# /etc/systemd/system/forgejo-ssh-forward.service
[Unit]
Description=TCP forward :<SSH_PORT> -> built-in SSH on <内网机>:<SSH_PORT>
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/socat -d -d TCP-LISTEN:<SSH_PORT>,fork,reuseaddr,keepalive TCP:<内网机地址>:<SSH_PORT>,keepalive
Restart=on-failure
RestartSec=2s
DynamicUser=yes
AmbientCapabilities=CAP_NET_BIND_SERVICE      # 仅当 <SSH_PORT> < 1024 才需要
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
```

`systemctl enable --now forgejo-ssh-forward`，再放行云防火墙/安全组的 `<SSH_PORT>` 入站。**验收**：从任意公网机 `ssh -p <SSH_PORT> -T git@<SSH_HOST>` 应回 `<server>` 的 `Permission denied (publickey)`（没登记 key 时）或欢迎语（登记了 key）；`ssh -v` 里出现 `remote software version Go` 说明确实打到了内置 server（OpenSSH 会显示 `OpenSSH_...`，借此区分是不是打串到运维 sshd）。公钥在网页端登记即可（内置 server 直接查库，无需碰入口机）。

**内网机在 WSL2（NAT）+ Windows 入口的特例**：`<内网机地址>` 要填 Windows 宿主的网卡 IP（mesh / LAN），WSL 内的容器端口得经 Windows `netsh portproxy` + wslrelay 才能从宿主 IP 进。这条链路有个 **SSH 专属坑**，详见 `network` skill 的「WSL/Docker 服务暴露（入站）」：

> 这条链路经 Windows `netsh portproxy` + wslrelay。docker 发布 `0.0.0.0:<SSH_PORT>:<容器内端口>` 或 `127.0.0.1:<…>` 均可（实测无差别）；portproxy **`connectaddress=127.0.0.1`**（走 wslrelay、**不漂移**，别用会随 WSL 重启变化的 eth0 IP）。wslrelay 有个全双工死锁坑（WSL #10688）：仅"双向同时大流量 + 程序不积极收 socket"才触发，git-over-SSH / HTTP 实测不中招、与发布地址无关，详见 `network` skill 的「全双工大流量下 wslrelay 死锁」。

### 方案 B：公网 SSH relay（sshd 分流 + 中转脚本）

整套的核心，三部分：`<入口VPS>` 的 sshd 分流、`<入口VPS>` 的两个中转脚本、`<内网机>` 的 authorized_keys 内联转发。

#### (a) `<入口VPS>` sshd：给 git 用户单独分流

先建一个本机 `git` 用户（`useradd git`，家目录放 relay 私钥，见 (b)）。在 `<入口VPS>` 的 `sshd_config` 末尾加一段 `Match User git`——只影响登录名 `git`，全局配置和其它用户完全不动：

```
# >>> git-relay BEGIN
# 把登录用户 git 限制为"只能走 git transport（经 relay 到内网）"
Match User git
    AuthorizedKeysCommand /usr/local/bin/forgejo-authkeys %u %t %k
    AuthorizedKeysCommandUser git
    AuthorizedKeysFile none
    PasswordAuthentication no
    KbdInteractiveAuthentication no
    X11Forwarding no
    AllowTcpForwarding no
    PermitTTY no
# <<< git-relay END
```

- `AuthorizedKeysCommand` 让 sshd 每次连接**动态查 key**（不读静态文件，故 `AuthorizedKeysFile none`），`%u %t %k` = 用户名 / key 类型 / key blob。
- `AuthorizedKeysCommandUser git`：这条查询命令以 `git` 身份跑。
- 改 sshd 要稳：先备份 → `sshd -t` 校验通过 → `systemctl reload sshd`（reload 不断现有连接，配错也不会立刻锁死你）。SSH 服务名因发行版而异（见「关键坑 · 发行版差异」）。云厂商的 VNC / 串口控制台是改坏时的最后兜底。

#### (b) `<入口VPS>` 两个中转脚本

这两个脚本**就是单机部署里 `<cli> keys` / `<cli> serv` 两个功能的"跨机版"**：单机部署时 sshd 直接调容器二进制的这俩子命令；这里 VPS 上没有 forgejo/gitea 二进制，于是用两个 shell 脚本把请求经 relay 转给内网机容器里的 `<cli> keys` / `<cli> serv` 执行。脚本本身只做 ssh 转发——**VPS 不需要任何 forgejo/gitea 二进制**，公网那台越干净越安全。

`/usr/local/bin/forgejo-authkeys`（sshd 查 key 时调，把 `keys` 请求经 relay 转给内网，再把内网返回的 key id 拼成一行带 forced command 的 authorized_keys 回给 sshd）：

```bash
#!/usr/bin/env bash
# VPS sshd 的 AuthorizedKeysCommand（以 git 身份跑，参数 = %u %t %k）。
# = 单机部署里 `<cli> keys` 的跨机版：把 (类型,公钥) 经 relay 转给内网机
#   容器查，再把返回的 key-N 改写成一行指向本机 forgejo-serv 的 authorized_keys。
set -uo pipefail
RELAY="ssh -i /home/git/.ssh/relay_key -p <MESH_SSH_PORT> -o IdentitiesOnly=yes -o ControlMaster=no -o ControlPath=none -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=8 <user>@<MESH_IP>"
keyid="$($RELAY "keys ${2:-} ${3:-}" 2>/dev/null | grep -m1 -oE 'key-[0-9]+')" || exit 0   # 查不到 / relay 失败 → 干净拒绝
printf 'command="/usr/local/bin/forgejo-serv %s",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty,restrict %s %s\n' "$keyid" "$2" "$3"
```

`/usr/local/bin/forgejo-serv`（上面拼出的 forced command 的目标；把客户端真正的 git 命令 base64 后经 relay 转给内网的 `serv`）：

```bash
#!/usr/bin/env bash
# 上面那行 authorized_keys 的 forced command（参数 = key-N）。
# = 单机部署里 `<cli> serv` 的跨机版：把客户端真正的 git 命令
#   （在 $SSH_ORIGINAL_COMMAND 里）base64 后经 relay 转给内网机容器执行。
set -uo pipefail
exec ssh -i /home/git/.ssh/relay_key -p <MESH_SSH_PORT> \
  -o IdentitiesOnly=yes -o ControlMaster=no -o ControlPath=none \
  -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=8 \
  <user>@<MESH_IP> "serv ${1:?keyid} $(printf '%s' "${SSH_ORIGINAL_COMMAND:-}" | base64 -w0)"
```

两脚本 `chmod 755`、root 拥有。relay 私钥 `/home/git/.ssh/relay_key`（600、git 拥有）+ 预填 `known_hosts`。git 命令必须 base64：它含空格和引号，跨两跳 SSH + shell 会被切碎，base64 成一个整块最稳。那串 `-o ControlMaster=no …` 见「关键坑 · ControlMaster」。（脚本名沿用 `forgejo-*` 仅是文件名，跑 Gitea 时内容里把内网那端的 `<cli>` 换成 `gitea` 即可，见 (c)。）

#### (c) `<内网机>`：authorized_keys 内联转发

relay 的另一端落在 `<内网机>` 的 `<user>`（用它当 relay 端点，免 sudo）。在 `<user>` 的 `~/.ssh/authorized_keys` 里给 relay 公钥加**一行 forced command**，把 relay 请求 dispatch 成对容器的 `docker exec`（下例 `<server>`=容器名、`<cli>`=`forgejo`/`gitea`）：

```
command="/usr/bin/bash -c 'set -- $SSH_ORIGINAL_COMMAND; a=${1:-}; if [ \"$a\" = keys ]; then exec docker exec -u git <server> <cli> keys -e git -u git -t \"$2\" -k \"$3\" --config /data/gitea/conf/app.ini; elif [ \"$a\" = serv ]; then exec docker exec -i -u git -e SSH_ORIGINAL_COMMAND=\"$(printf %s \"$3\" | base64 -d)\" <server> <cli> serv \"$2\" --config /data/gitea/conf/app.ini; else echo \"relay: bad action\" >&2; exit 1; fi'",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty,restrict ssh-ed25519 <relay-pubkey> git-relay@<入口VPS>
```

- `<内网机>` 收到的请求要递进容器，靠 `docker exec`（只能在容器外的宿主上跑，所以这段逻辑在宿主、不在容器里）。
- **一把 key 承载两种操作**：`set -- $SSH_ORIGINAL_COMMAND` 拆出 action，`keys` / `serv` 两路分别 `docker exec`，其它输入一律 `relay: bad action` 拒绝。这个 dispatch 去不掉——请求是动态的、藏在 `$SSH_ORIGINAL_COMMAND` 里，没法写死成一条裸命令。
- `serv` 那路 `docker exec` **必须带 `-i`**（保留 stdin），否则 push 会挂死（见「关键坑」）。
- **直接内联进 `command=` 而不另放脚本**：省一个文件、改 key 时一处可见。`command=` 外层是双引号、内部只能用 `\"` 转义双引号，所以主体用单引号包 `bash -c '...'`（主体内不含单引号才成立）。`<cli> serv` / `<cli> keys` 是 Forgejo/Gitea 的原生子命令（官方 SSH 直连模式内部也是调它们），这里把它们"借"出来用。注意 `--config /data/gitea/conf/app.ini` 这个路径两家都对（非 rootless 镜像统一 `GITEA_CUSTOM=/data/gitea`）。

**验收**：把客户端公钥加到某个账户后，`ssh <user>@<PUBLIC_IP>` 仍是运维 shell、`git clone git@<PUBLIC_IP>:user/repo.git` 能拉到仓库即通。

## ⑤ CI：Actions runner（DinD 隔离）

Actions 在**两家当前源码里都默认启用**（`modules/setting/actions.go` 结构体 `Enabled: true`，无需改 `app.ini`；Forgejo 官方文档另注「As of Forgejo v1.21, Actions is enabled by default」）。服务本体不跑 job，靠独立的 runner——**Forgejo 用 `forgejo-runner`、Gitea 用 `act_runner`**（两个独立项目）。① 的 compose 已含两个容器：

- `docker-in-docker`（`data.forgejo.org/oci/docker:dind` 或 Docker Hub `docker:dind`，privileged，hostname 必须是 `docker`）：**独立的 docker daemon 跑在容器里**，job 容器都在它里面起、与宿主 docker 隔离。TLS 证书经 `docker_certs` 卷共享。
- `runner`（Forgejo `data.forgejo.org/forgejo/runner:12` / Gitea `gitea/act_runner`）：`DOCKER_HOST=tcp://docker:2376` 指向 DinD。

> 用 **DinD + TLS（2376）** 而非官方 [runner docker 文档](https://forgejo.org/docs/latest/admin/actions/installation/docker/) 最简示例的明文 `2375 --tls=false`：privileged 的 DinD 守护进程 ≈ 近乎宿主 root 的能力，明文 2375 无认证、同网络任何容器都能控制它；TLS 让只有持 `docker_certs` 证书的 runner 连得上。带 TLS 的多容器写法对应官方 runner 仓库的 [`examples/docker-compose`](https://code.forgejo.org/forgejo/runner/src/branch/main/examples/docker-compose)。

注册三步（命令两家平行，仅 `<cli>` 与 runner 二进制名不同）：

1. **生成 token**（全局 runner token，admin 级，两家同名子命令）：
   ```
   docker exec -u git <server> <cli> actions generate-runner-token
   ```
   （web 界面拿的 secret 与 CLI token 不是一回事；自动化用 CLI token。）
2. **注册**（创建 `./runner/.runner`）。instance URL 用**容器内部地址** `http://forgejo:3000`（HTTP 明文走 compose 网络，避开公网自签 TLS）：
   ```
   # Forgejo:
   docker compose run --rm runner forgejo-runner register --no-interactive \
     --instance http://forgejo:3000 --token <TOKEN> --name dind-<host> \
     --labels "docker:docker://data.forgejo.org/oci/node:20-bookworm,ubuntu-latest:docker://data.forgejo.org/oci/node:20-bookworm"
   # Gitea 等价：runner 二进制换 act_runner、镜像换公共 node 即可：
   #   docker compose run --rm runner act_runner register --no-interactive \
   #     --instance http://gitea:3000 --token <TOKEN> --name dind-<host> \
   #     --labels "ubuntu-latest:docker://node:20-bookworm"
   ```
   label 形如 `name:docker://image`：把 `ubuntu-latest` 映射到一个 node 镜像，这样 `runs-on: ubuntu-latest` 能用、`actions/checkout`（需 node 运行时）也跑得起来。
3. **配置 + 启动**：`docker compose run --rm runner <runner-bin> generate-config > runner/config.yml`，把 `container.network` 改成 `"host"`（见下），再 `docker compose up -d docker-in-docker runner`。

> **`uses:` 不带 host 时去哪拉公共 action**（`DEFAULT_ACTIONS_URL`，两家默认不同）：**Forgejo → `https://data.forgejo.org`**、**Gitea → `https://github.com`**（源码 `modules/setting/actions.go`）。即同一份 workflow 里 `uses: actions/checkout@v4`，Forgejo 默认去 data.forgejo.org 找镜像、Gitea 默认去 github.com；要改用别处可设 `[actions] DEFAULT_ACTIONS_URL`。工作流文件目录也不同：Forgejo 认 `.forgejo/workflows/` **和** `.gitea/workflows/`、`.github/workflows/`；Gitea 认 `.gitea/workflows/` 和 `.github/workflows/`。

### runner 网络的关键设计

job 容器跑在 **DinD 的独立 daemon** 里，DinD 的网络命名空间默认解析不到宿主 compose 网络上的 `forgejo`/`gitea`。解法：

- DinD 容器挂到服务的 compose 网络（compose 项目名前缀，本部署是 `forgejo_forgejo`）→ DinD 能解析 `forgejo:3000`。
- runner config `container.network: "host"` → job 容器共享 DinD 的 netns → job 内 `actions/checkout` 能从 `http://forgejo:3000`（Gitea 则 `http://gitea:3000`）clone（内部 HTTP，无 TLS 验证问题）。

> **host vs bridge（为什么不能用默认）**：这是 **docker 套娃的两层网络**——job 容器由 **DinD 内层 docker daemon** 创建、待在内层 bridge（实测 `172.17.0.0/16`），而服务容器在**外层 compose** 网络（实测 `172.20.0.0/16`），两层互不相通。用默认 `network: ""`（自动建网）或 `bridge`，job 待在内层 bridge 只能 NAT **向外**出公网、却**够不到内部服务**（clone 失败；装了 Mihomo/Clash 之类的机器上服务名还会被兜底解析成连不通的 fake-ip `198.18.x`，看着"解析成功"实则连不上）。`host` 让 job 共享 **DinD 容器自己的 netns**，而 DinD 本身在外层 compose 里 → job 借它的身份才直连得上服务。代价：job 与 DinD 共享网络栈、隔离略松，换来内部直连。**设置点就是 `runner/config.yml` 的 `container.network: "host"`**（`generate-config` 默认 `""`，需手改，即上面第 3 步）。

runner 日志里会看到 `task N repo is <repo> https://data.forgejo.org http://forgejo:3000`：前者是 `DEFAULT_ACTIONS_URL`（`uses:` 不带 host 时去拉公共 action 的源），后者是内部实例地址。

### 验收

push 一个最小 workflow（`.forgejo/workflows/ci.yml` 或 `.gitea/workflows/ci.yml`，`on: [push]` + 几个 `run: echo`）到任一启用了 Actions 的仓库：

```
docker logs forgejo-runner            # task N picked up
docker exec forgejo-db psql -U forgejo -t -c \
  "select id,name,status from action_run_job order by id desc limit 1;"
```

`action_run_job.status` 枚举（源码 `models/actions/status.go`）：`1=Success 2=Failure 3=Cancelled 4=Skipped 5=Waiting 6=Running 7=Blocked`——**Gitea 比 Forgejo 多一个 `8=Cancelling`**（取消中的中间态）。首跑会慢（DinD 内首次拉 node 镜像），状态 6→1 即通。

### 资源 / 并发

- 并发：runner config `runner.capacity`（默认 1，同时几个 job）。
- CPU / 内存 / 文件系统配额：给 `docker-in-docker` 和 job 容器加 docker 资源限制（compose `deploy.resources` 或 runner config `container.options` 注入 `--cpus` / `--memory`）。资源充裕默认不设限。
- DinD 的 `/var/lib/docker` 用 `./dind` bind mount 持久化，避免每次重启重拉镜像。

### 查看 / 拉取 action 运行日志

**先按版本判断走哪条路**——能用 REST API 就别碰服务器文件：

| 平台 / 版本 | 看 action 日志的办法 |
| --- | --- |
| **Gitea ≥ v1.24**（含当前 v1.27-dev） | ✅ Token REST API（**仅 per-job 文本**，无 per-run zip）：swagger `downloadActionsRunJobLogs`，`routers/api/v1/repo/actions_run.go` |
| **Forgejo ≥ v16** | ✅ Token REST API（**per-job 文本 + per-run zip 都有**）：`repoGetActionJobLogs` + `repoGetActionRunLogs`，`routers/api/v1/repo/action.go`（[PR #12666](https://codeberg.org/forgejo/forgejo/pulls/12666)，随 v16 发布） |
| **Forgejo ≤ v15** | ❌ 无 REST 日志端点：基本**只能网页端**交互看（带 token 的 CLI/脚本走不通），或进 docker / 读服务器文件 |

> 旧版笔记说"REST API 没有下载日志正文的端点"——那只对 **Forgejo ≤v15** 成立，**v16 已打破**（Gitea 自 v1.24 更早有 per-job）。**per-run 打包 zip 目前是 Forgejo v16 独有，Gitea 当前源码只有 per-job**（`routers/api/v1` 里搜不到 per-run zip 路由）。

#### 路 1：REST API（Forgejo ≥v16 / Gitea ≥v1.24，推荐——一个 PAT 搞定，不进服务器）

带一个对该仓库有**读权限**的 PAT（`Authorization: token <PAT>`）即可，全程在任意机器上跑：

```bash
# 1) 由 run 反查 job_id（两家都有）
curl -H "Authorization: token <PAT>" \
  https://<your-host>/api/v1/repos/<owner>/<repo>/actions/runs/<run_id>/jobs
# 2) 单个 job 的纯文本日志（Forgejo & Gitea 都有这条）
curl -H "Authorization: token <PAT>" \
  https://<your-host>/api/v1/repos/<owner>/<repo>/actions/jobs/<job_id>/logs
# 3) 整个 run 打包 zip（仅 Forgejo ≥v16；Gitea 无此端点）
curl -H "Authorization: token <PAT>" -L -o run-logs.zip \
  https://<your-host>/api/v1/repos/<owner>/<repo>/actions/runs/<run_id>/logs
```

实测（Forgejo `16.0-test`，本机走公网 + PAT、**未在服务器上执行任何代码**）：per-job 返回 `200 text/plain`，支持 `?step=N` 取单步、`Range: bytes=a-b` 返回 `206` 分段；per-run 返回 `200 application/zip`（`PK` 头）。Gitea 侧 per-job 是 swagger operation `downloadActionsRunJobLogs`，返回日志 blob。注意实例若开 `REQUIRE_SIGNIN_VIEW`，连 `/api/v1/version` 都要带 token（匿名 403）。

**运行中也能看、不必等跑完**：实测在 job `status=running` 期间反复打 per-job logs 端点，会返回**已产出的部分日志**且随执行增长（一次 34s 的 run：t=5s 已有 50 行、边跑边长到 79 行，完成瞬间补齐到 209 行）。但它是 **runner 周期性 flush 的缓冲分块、不是逐行实时**——有几秒延迟，且最冗长那一步的输出可能压到收尾才刷出来。要做"tail -f"式跟随就配 `Range: bytes=<上次偏移>-` 每次只取增量。（Forgejo v15 及以前这些都没有：脱离浏览器看不了，只能进容器边 `tail` 边 `zstd -dc` 那个 `.log.zst`。）

> 升级 Forgejo v15→v16 是一次性 DB 迁移、**不支持降级**：换 image 前先 `docker exec <db> pg_dump -U <user> -Fc <db> > db.dump` + 备份 `./data`（含 `gitea/conf/app.ini` 里的 `SECRET_KEY`）。正式版 `codeberg.org/forgejo/forgejo:16` 出来前要尝鲜，可用预发布 `codeberg.org/forgejo-experimental/forgejo:16.0`（main 的 nightly，已带本 API；迁移只动 DB，不碰 `./data/ssh` 与 repo）。

#### 路 2：兜底（没有 token API 时，如 Forgejo ≤v15）

- **Web UI**（`/{owner}/{repo}/actions/runs/{run_index}/jobs/{job_index}`）是 **web 端点，只认登录 session cookie，不认 API token**——带 `Authorization: token` 访问 web 路径会被当成匿名，私有仓库对匿名返回 **404**（不泄露存在性）。所以"直接 curl raw-log URL"对**公开**仓库成立，对**私有**仓库得先模拟登录拿 cookie（GET 取 `_csrf` → POST `/user/login` → 存 cookie，还要过可能的 2FA），脆。登录用户用浏览器交互看日志则一直没问题。两家 web 端点行为一致。

- **读服务器端日志文件**（脚本化最稳，但需进机器/容器）：日志按 job 落在 `<data>/gitea/actions_log/<owner>/<repo>/<NN>/<task_id>.log.zst`，**zstd 压缩**。**`<NN>` 是 `%02x`（`task_id mod 256` 的两位十六进制）目录**——源码 `models/actions/task.go` 的 `logFileName` 拼的就是 `fmt.Sprintf("%s/%02x/%d.log", repoFullName, taskID%256, taskID)`，两家逐字一致。所以 `task_id=2 → 02/2.log.zst`、`task_id=123 → 7b/123.log.zst`（123 = 0x7b，**不是十进制 `12/`**）、`task_id=300 → 2c/300.log.zst`（300 mod 256 = 44 = 0x2c）。这条相对路径直接存在 `action_task.log_filename` 字段。容器是 alpine、**不带 zstd**，在宿主或带 zstd 的环境解：

  ```bash
  # 由 repo 反查最近一次 job 的日志相对路径
  docker exec forgejo-db psql -U forgejo -d forgejo -At -c \
    "SELECT t.log_filename FROM action_task t JOIN repository r ON r.id=t.repo_id \
     WHERE r.lower_name='<repo>' ORDER BY t.id DESC LIMIT 1;"   # -> <owner>/<repo>/NN/<id>.log.zst

  # 解压 + 去掉 ANSI 颜色码（宿主有 zstd 时）
  zstd -dc "<data>/gitea/actions_log/<owner>/<repo>/NN/<id>.log.zst" | sed 's/\x1b\[[0-9;]*m//g'
  # 无 zstd：python3 -c 'import zstandard,sys; sys.stdout.buffer.write(zstandard.ZstdDecompressor().decompress(open(sys.argv[1],"rb").read(), max_output_size=50_000_000))' <file>
  ```

> `action_run.index`（仓库内 run 序号，= Web URL 里的 `{run_index}`）与全局 `action_run.id` 不是一回事；按 repo 反查日志走 `action_task` 表最直接。`action_run_job.status` 枚举见上节验收。表名、`log_filename` 字段、路径公式两家一致。

## 关键坑

### ControlMaster 复用绕过 relay（最隐蔽，仅方案 B）

`<内网机>` 的 `~/.ssh/config` 若有 `Host * ControlMaster auto`，会让任何 ssh 调用**复用已存在的 master 连接**，从而绕过 `-i relay_key`（用默认 key）、绕过 forced command（落到普通 shell），relay 行为完全错乱且难排查。所以 relay 方向的 ssh 必须显式禁用 mux：`-o ControlMaster=no -o ControlPath=none -o IdentitiesOnly=yes -o BatchMode=yes`（④(b) 的两个脚本已内置）。

### serv 必须流式透传 stdin（仅方案 B）

git 的 `upload-pack` / `receive-pack` 是双向流。④(c) 里 `serv` 那路 `docker exec` **必须带 `-i`**，否则 push（receive-pack）会挂死。`keys` 那路无所谓。

### 入口机发行版差异（仅方案 B）

下面几点取决于 `<入口VPS>` 是什么发行版（本部署恰好是 RHEL 系，`ID_LIKE="rhel fedora centos anolis"`）：

- **SSH 服务名**：RHEL 系是 `sshd`（`systemctl reload sshd`）；Debian/Ubuntu 的 systemd unit 反而叫 `ssh.service`（`sshd.service` 只是 alias）——反直觉，reload 前先 `systemctl list-units '*ssh*'` 确认。二进制和配置两边都是 `sshd` / `sshd_config`。
- **sshd_config 结构**：本部署入口机主文件无 `Include`、无 `/etc/ssh/sshd_config.d/`，故 `Match` 段直写主文件末尾；很多发行版有 `sshd_config.d/` drop-in 目录，那就优先放 drop-in。无论哪种，改前用 `sshd -T` 看**有效合并配置**。（`/etc/ssh/ssh_config` 的 `Include` 是**客户端**配置，与 sshd 无关。）
- **SELinux / AppArmor**：本部署 SELinux 是 Disabled，`/usr/local/bin/` 自定义脚本无 label 顾虑；若你的机器 SELinux enforcing，自定义路径脚本可能被拦（需合适 context / `restorecon`），AppArmor 同理留意。

### cookie 改名（登录 500）

同一个公网 IP / 域名上若先后跑过别的 Gitea/Forgejo 实例，浏览器会按**域名/IP（不分端口）**残留旧 session cookie。**默认 cookie 名两家不同**（`modules/setting/session.go:37`）：**Gitea 默认 `i_like_gitea`、Forgejo 默认 `session`**——`session` 这个名字尤其通用，和同主机别的 app 撞的概率更高。新实例接管后拿到一个长度不符的旧 cookie（如旧 Gitea 残留的 64 字符 `i_like_gitea`）去换新 session id，长度校验失败 → `RegenerateSession: invalid 'sid' ... 64 != 16` → `POST /user/login` **500**（密码其实是对的，这步在密码验证通过之后才执行）。无痕窗口/换浏览器正常就是这个特征。**根治：① 的 compose 里把 `COOKIE_NAME` 设成一个独特名**（和默认的 `i_like_gitea` / `session` 都脱钩，也避免同主机多实例互撞），recreate 容器即可（无需用户清浏览器）。

### 数据落进匿名卷 → 迁回 bind mount

若 data 挂错（见「第二部分 · 挂载路径必须匹配镜像类型」）、数据落进了匿名卷，迁回：① `docker compose stop server` ② `docker cp <server>:/data/. ./data/`（`docker cp` 走 docker API，能跨 Docker Desktop 的 VM 边界）③ 改 compose 挂载为 `./data:/data` ④ `docker compose up -d server` ⑤ 验证宿主 `./data` 有数据、不是全新装、loopback 200 ⑥ 旧匿名卷 dangling 后 `docker volume rm <id>`（**别用 `docker volume prune`**，会误删同机其它项目的 dangling 卷）。
