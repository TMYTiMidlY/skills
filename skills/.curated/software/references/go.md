# Go 工具链：装 CLI、去中心化模块、依赖解析，与 conda-forge go 的 cgo 坑

> 面向"用过 pip / npm、第一次认真看 Go 怎么装工具、怎么拉依赖"的人。最反直觉的一点：**Go 没有 PyPI / npm 那样的中央包索引**——包的"名字"本身就是"去哪找它"的地址。本篇讲清四件事：① 这套去中心化生态怎么运作；② 原生怎么装一个 Go 写的 CLI（`go install` / `go run`）；③ 导入路径怎么解析成仓库、版本怎么选；④ 用 `pixi global install go` 装的 go 为什么一构建 cgo 就报「找不到 C 编译器」、怎么治。下面的说法据 Go 官方 [模块参考 `go.dev/ref/mod`](https://go.dev/ref/mod) 与本机 `go help <topic>`（`go1.26.3`）。

## 没有中央仓库：导入路径就是仓库地址（去中心化）

习惯了 `pip install <名字>` / `npm install <名字>` 会以为 Go 也有个中心站点收包、按名字下载。**没有**。Go 的模块生态是去中心化的：

- **模块（module）与包（package）**：模块是一起发布、版本化、分发的一组包，根目录有个 `go.mod` 声明**模块路径**（module path）；**包路径** = 模块路径 + 模块内子目录。例：模块 `golang.org/x/net`，其 `html/` 子目录的包路径是 `golang.org/x/net/html`。
- **import 路径 = 源码位置**。`github.com/spf13/cobra`、`gitea.com/gitea/gitea-mcp`、`codeberg.org/goern/forgejo-mcp/v2` 这些既是导入路径、也是真实的 git 仓库地址。`go` 命令直接去那个 VCS host（GitHub / Gitea / Codeberg / 自建）`git clone` 拉源码——**没有"上传到某个 registry"这一步**。
- **module proxy 是缓存、不是注册中心**。默认 `GOPROXY=https://proxy.golang.org,direct`（[官方](https://proxy.golang.org)）：proxy 只是**首次被请求时**去源仓库惰性抓取并缓存的镜像，任何人都没"发布"到它；`,direct` 是回退——proxy 没有就直接 git 拉源。所以模块能活在**任意** git host 上，这正是 gitea-mcp 在 `gitea.com`、forgejo-mcp 在 `codeberg.org` 却都能 `go install` 的原因。
- **"发版" = 打一个 git tag**。语义化版本（`v1.2.3`）就是仓库里的 git tag，`@latest` 解析成最新的语义化 tag。没有审核、没有上传、没有"包名注册"环节（[Module version numbering](https://go.dev/ref/mod#versions)）。
- **校验靠 checksum database**，不靠中心仓库信任。`go.sum` + `sum.golang.org`（[官方](https://sum.golang.org)）记录每个模块版本的哈希，防篡改；这是完整性机制，不是"平台"。
- **主版本进路径**：`v2+` 要在 import 路径带 `/v2`、`/v3` 后缀（semantic import versioning，[官方](https://go.dev/ref/mod#major-version-suffixes)）——所以 forgejo-mcp 的装法是 `codeberg.org/goern/forgejo-mcp/v2@latest`，少了 `/v2` 会找错模块。

> 副作用两面：好处是没有名字抢注、可完全自建自控、迁移 host 只改路径；代价是模块可用性理论上依赖源 host 在线（被 proxy 缓存缓解），且没有一个"官方唯一平台"背书——判断某个包是否官方，只能看它挂在哪个组织的仓库下（例：gitea-mcp 在官方 `gitea.com/gitea` 组织下 = 第一方；Forgejo 侧无第一方 MCP，详见 [git-server.md](git-server.md) 第四部分）。`pkg.go.dev` 是文档/搜索索引（爬 proxy），也**不是**准入门槛。全文末尾有一张 Go / PyPI / npm 的对照表。

## 装一个 Go 写的 CLI：`go install` / `go run`

Go 写的 CLI 工具，标准装法是**从源码编译**（需要本机有 Go 工具链），不是下预编译二进制。两条命令（[官方 go install](https://go.dev/ref/mod#go-install)）：

```bash
go install <module-path>[/cmd]@<version>   # 编译并把二进制装进 $GOBIN，持久留用
go run     <module-path>[/cmd]@<version>   # 编译到临时目录、跑完即弃，不落二进制
```

带 `@version` 后缀时的关键语义（`go help install`）：

- **忽略当前目录及任何父目录的 `go.mod`**，在 module-aware 模式下独立解析——所以**装工具不会污染你当前项目的依赖**。
- 参数必须指向 **main 包**（能产出可执行文件），且同一次调用里所有参数同模块、同版本。
- 不使用 vendor 目录。

无 `@version`（如 `go install ./...`）时才在"当前主模块"上下文里跑。**Go 1.16 起**约定变了：`go get` 不再负责装二进制、也不再默认改依赖；**装工具统一用 `go install pkg@version`**，`go get` 现在只管 `go.mod` 里的依赖增删。

**版本选择器**（`@` 后面）：

| 写法 | 含义 |
| --- | --- |
| `@latest` | 最新的**语义化 tag**（不含预发布） |
| `@v1.2.3` | 精确某个 tag |
| `@v1.2` / `@v1` | 该前缀下最新 |
| `@<commit>` / `@<branch>` | 具体 commit / 分支（生成 pseudo-version 如 `v0.0.0-<date>-<hash>`） |
| `@none` | 卸载（仅在 `go get` 语境） |

**装到哪**：`$(go env GOBIN)`；未设 `GOBIN` 则 `$(go env GOPATH)/bin`（默认 `~/go/bin`）。想装到别处（例如放进已在 `PATH` 里的 `~/.local/bin`）临时指定：

```bash
GOBIN=~/.local/bin go install <module-path>@latest
```

**判别一个二进制是"从 proxy 装"还是"本地 clone build"**（`go version -m <binary>` 看内嵌 build 元数据）：

- **从 module proxy 装**（`go install …@version`）：显示 `mod  <path>  <version>  h1:<hash>`（带 proxy 哈希），**无 `vcs.*` 行**。这是"干净"构建。
- **本地 git 工作树里 `go build` / `go install .`**：Go 会打 `build vcs.revision=…`、`build vcs.time=…`、`build vcs.modified=true/false`；工作树有未提交改动时版本尾巴带 `+dirty`（如 `v1.3.0+dirty`）。

> 这条在排查"这个二进制到底哪来的、是不是官方 release"时很有用：`+dirty` / 有 `vcs.modified=true` = 某人在本地改过源码编的，不是 proxy 上的干净版本。

**`go install …@version` 遇 `replace` 指令会失败**：`replace`（把某依赖重定向到 fork 或本地路径）**只对"主模块"生效**（[官方 replace](https://go.dev/ref/mod#go-mod-file-replace)）。而 `go install pkg@version` 是在**没有主模块**的模块感知模式下构建目标模块，它不应用目标 `go.mod` 里的 `replace`；若该模块**靠** `replace` 才能正确构建（例如依赖指向一个 fork），远程 `go install` 就解析不到、构建失败。解法是改用 `git clone` 后在仓库内 `go install .`（此时该仓库是主模块，`replace` 生效），或等作者去掉 `replace`。（forgejo-mcp 历史上就因此坏过，后来去掉 `replace` 已修，见 [git-server.md](git-server.md) 第四部分脚注。）

## 从导入路径怎么找到仓库（解析机制）

工具链拿到一个非标准库导入路径后，按下面顺序定位源码（`go help importpath`）：

1. **已知代码托管站**有内建规则，直接推导仓库：`github.com/…`、`bitbucket.org/…`、`hub.jazz.net/git/…`、`launchpad.net/…` 等。
2. **显式带 VCS 后缀**：`example.org/repo.git/foo/bar` 明确表示"`example.org/repo` 这个 Git 仓库的 `foo/bar` 目录"（支持 `.git` / `.hg` / `.bzr` / `.svn` / `.fossil`）。
3. **自定义域名（vanity import path）**：既不是已知站、又没 VCS 后缀时，工具链对 `https://<路径>?go-get=1` 发一个 HTTP GET，在返回 HTML 的 `<head>` 里找一个 `<meta>` 标签：

   ```html
   <meta name="go-import" content="import-prefix vcs repo-root">
   ```

   例：拉 `example.org/pkg/foo` → 请求 `https://example.org/pkg/foo?go-get=1` → 若含 `<meta name="go-import" content="example.org git https://code.org/r/p/exproj">`，工具链会**再验证** `https://example.org/?go-get=1`（prefix）也有同样 tag，然后从 Git 仓库 `https://code.org/r/p/exproj` 拉代码。这就是 `golang.org/x/...` 这类"体面导入路径"能重定向到实际托管地的原理。
   - **Go 1.25+** 认第 4 段 `subdir`（`content="prefix vcs repo-root subdir"`），允许模块根在仓库的子目录里；此时 VCS tag 要带 `subdir/` 前缀（如 `subdir/v1.2.3`）。
   - `vcs` 取 `mod`（`content="example.org mod https://code.org/moduleproxy"`）表示"这些路径走这个**模块代理**取"，优先于 VCS 方式。
4. **import path checking**：源码里 `package foo // import "canonical/path"` 这种 import comment 会强制只能用规范路径引用；模块模式下它已被 `go.mod` 的 `module` 声明取代、不再检查。

> 一句话回答"go install 是读特定文件还是有中央平台"：**都不是**——它把**导入路径当成 URL**去 VCS（或经代理）取源码，`proxy.golang.org` 只是挡在前面的缓存/校验层，不是你发布的目标索引。

## 版本号与最小版本选择（MVS）

- 版本形如 `v1.12.3`，遵循 [SemVer 2.0](https://semver.org/spec/v2.0.0.html)：major 破坏兼容、minor 加功能、patch 修 bug；可带预发布后缀 `-rc.1` 或构建元数据 `+meta`（[ref/mod](https://go.dev/ref/mod)）。
- **major ≥ 2 必须在模块路径尾部带 `/vN` 后缀**（`example.com/mod/v2`）——同一仓库的不同大版本被当**不同模块**、可在一次构建里共存。这是 Go 特有的 "semantic import versioning"。
- **伪版本（pseudo-version）**：给没打 tag 的具体 commit 用，形如 `v0.0.0-20260627181231-7d0c66d223ab`（`vX.Y.Z-<UTC时间戳>-<12位commit>`；前缀依"最近的 tag"分三种变体）。
- **MVS（最小版本选择，Minimal Version Selection）**：构建时 Go 选"能同时满足所有 `require` 的**最低**版本"，而不是自动取最新——依赖因此可复现、可预测（和 npm/pip 倾向解析到最新兼容版不同）（[ref/mod](https://go.dev/ref/mod#minimal-version-selection)）。

## `go.mod` / `go.sum` / 模块缓存

- **`go.mod`**：`module` 声明本模块路径、`go` 指定语言版本、`require` / `replace` / `exclude` 管依赖。
- **`go.sum`**：记录每个依赖版本的**加密校验和**（模块内容、`go.mod` 各一条），拉取时逐条比对防被偷换。它不是 lockfile（版本锁在 `require` + MVS 里），而是完整性清单。
- 下载的模块解包进**模块缓存** `$GOPATH/pkg/mod`（只读、跨项目共享）。

## 代理与校验：GOPROXY / GOSUMDB / GOPRIVATE

本机默认（`go env`）：`GOPROXY=https://proxy.golang.org,direct`、`GOSUMDB=sum.golang.org`。

- **GOPROXY**：模块代理就是"任何能响应特定 GET 请求的 web 服务"，连 `file:///` 都行（`go help goproxy`）。默认先走公共镜像 `proxy.golang.org`，取不到再 `direct`（回落到直接 VCS clone）；设 `off` 则禁止联网取模块。
- **GOSUMDB**：公共校验和数据库 `sum.golang.org`，第一次见到某模块版本时用它交叉核验校验和（防上游事后篡改 tag 内容）。
- **私有模块**（`go help private`）：`GOPRIVATE=*.corp.example.com,rsc.io/private`（`path.Match` glob 前缀列表）把匹配的模块标记为私有——**不走公共代理、不查公共 sumdb**（直接 VCS 拉、只信本地 `go.sum`）。更细粒度用 `GONOPROXY` / `GONOSUMDB` 分别覆盖"是否走代理""是否查 sumdb"。

**墙内环境必换国内镜像**。默认的 `proxy.golang.org` / `sum.golang.org` 都是 Google 域名，在国内**直连不通**——现象是 `go install` / `go mod download` 卡住后报 `dial tcp …:443: i/o timeout`（本 session 在一台墙内机器上就这么失败的，换代理后 22s 装完两个 mcp）。国内事实主流是 **`goproxy.cn`**（[七牛云 Qiniu 维护](https://goproxy.cn)，CDN 无限速、支持代理 `sum.golang.org` 校验库）；备选 `goproxy.io`、`goproxy.baidu.com`（后者上游就挂着 goproxy.cn）。配法（末尾 `,direct` = 代理没有就回源直连，别丢）：

```bash
go env -w GOPROXY=https://goproxy.cn,direct     # 持久写进 ~/.config/go/env
# 校验库(sum.golang.org 也是 Google 域名)墙内同样连不上，二选一：
go env -w GOSUMDB=sum.golang.google.cn          # 用 Google 的中国镜像域名继续做校验(推荐，仍是真校验)
# 或关掉校验库(下下策，只在实在连不上且信任源时)：go env -w GOSUMDB=off
# 私有/自建源(不想过公共 proxy 和 sumdb)：go env -w GOPRIVATE=git.example.com,codeberg.org/yourorg
```

> `goproxy.cn` 支持[代理 checksum database](https://golang.org/design/25530-sumdb#proxying-a-checksum-database)，所以多数情况设了 `GOPROXY` 就够、`go.sum` 校验照常走；只有当 `sum.golang.org` 本身连不上导致校验超时才需要再设 `GOSUMDB=sum.golang.google.cn`（Google 官方在中国的镜像域名，仍是真校验、不是关掉校验）。

## <a id="cgo-pitfall"></a>`pixi global install go` 的 cgo 坑（conda-forge go 包）

**现象**：用 `pixi global install go`（拉的是 [conda-forge 的 go 包](https://github.com/conda-forge/go-feedstock)）装好 go 后，任何需要 cgo 的构建一上来就报：

```
cgo: C compiler "x86_64-conda-linux-gnu-cc" not found: exec: "x86_64-conda-linux-gnu-cc": executable file not found in $PATH
```

**根因**：conda-forge 编 Go 时，把默认 C 编译器 `DefaultCC=x86_64-conda-linux-gnu-cc`（及 `DefaultCXX=…-c++`、`CGO_ENABLED=1`）**编译期烧进了 `go` 二进制本身**，约定 cgo 走 conda 自己的工具链。但 `pixi global install go` 只装了 go、**没带那个编译器包**，于是那个内建默认的编译器名在 `PATH` 里根本不存在。

**关键：这跟"用没用 conda""pixi 项目激活"都无关**——常被误判成环境变量泄漏。判别：

```bash
echo "${CC:-<unset>}"                       # shell 里 CC 是 unset（不是实时激活来的）
ls ~/.config/go/env                         # go 的 env 文件根本不存在（不是它写的）
go env CC CXX                               # 却返回 x86_64-conda-linux-gnu-cc / …-c++
strings "$(which go)" | grep conda-linux-gnu-cc   # 能在 go 二进制里直接搜到 → 内建默认
```

四者叠加即可确认：**是那个 `go` 二进制的编译期内建默认**，不是任何实时环境。

**修法**（按推荐度）：

1. **正统：把配套编译器装进同一个 pixi 环境**——让内建默认的 `x86_64-conda-linux-gnu-cc` 真实存在：
   ```bash
   pixi global install --environment go c-compiler
   ```
   conda-forge 的 `c-compiler` 元包会拉来 `gcc_linux-64`，正好提供 `x86_64-conda-linux-gnu-cc`；`--environment go` 表示"加进名为 `go` 的现有全局环境作依赖"，其可执行文件不对外 expose。装完 `go env CC` 会从「裸名」变成 `…/.pixi/envs/go/bin/x86_64-conda-linux-gnu-cc` 全路径（= 被找到了），`CGO_ENABLED=1` 的 cgo 构建即通过。
2. **备选：把 Go 指回系统编译器**（脱离 conda-forge 工具链体系，但简单）：
   ```bash
   go env -w CC=/usr/bin/cc CXX=/usr/bin/g++   # 写进 ~/.config/go/env，覆盖内建默认；go env -u CC CXX 撤销
   ```
3. **临时绕过**（仅纯 Go 项目、根本用不到 cgo 时）：`CGO_ENABLED=0 go install …`。治标——一旦装的东西真需要 cgo 就不行。

> 换成非 conda-forge 的 go（官方 tarball、发行版包管理器的 go）通常 `DefaultCC` 是普通的 `cc`/`gcc`，不踩这个坑；这是 conda-forge 打包约定特有的。

## 一句话对照

| | Go modules | PyPI (pip) | npm |
|---|---|---|---|
| 包索引 | **无中央索引**，导入路径即仓库地址（可自建 host）| 中央 index（名字 ≠ 位置）| 中央 registry |
| 包名 | 全 URL 路径，**天生全局唯一**（不抢注、不撞名）| 中心命名空间（会抢注/撞名）| 中心命名空间 |
| 发布 | push 一个 git tag（不上传产物）| `twine upload` 传产物 | `npm publish` |
| proxy 的角色 | `proxy.golang.org` 是**缓存镜像**（惰性抓取），非注册中心 | —— | —— |
| 装工具 | `go install pkg@ver` | `pipx install` | `npm i -g` |
| 版本选择 | MVS（取最低可行、可复现）| 解析器（倾向最新兼容）| 语义范围 + lockfile |
| 完整性 | `go.sum` + `sum.golang.org` | hash（可选）| `package-lock` + registry |
| 大版本共存 | `/vN` 路径后缀，可共存 | 不可 | 不可 |
