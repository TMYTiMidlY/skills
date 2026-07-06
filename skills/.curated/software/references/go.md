# Go 工具链：原生装法、去中心化模块生态、pixi/conda-forge go 的 cgo 坑

> 三件事讲清楚：① Go **没有 PyPI/npm 那样的中心仓库**——import 路径就是源码地址；② 原生怎么装一个 Go 写的 CLI（`go install` / `go run`）；③ 用 `pixi global install go` 装的 go 为什么一构建 cgo 就报「找不到 C 编译器」，怎么治。

---

## 一、Go 没有 PyPI / npm 那样的中心仓库（去中心化，"平台"不存在）

习惯了 `pip install <名字>` / `npm install <名字>` 会以为 Go 也有个中心站点收包、按名字下载。**没有**。Go 的模块生态是去中心化的：

- **import 路径 = 源码位置**。`github.com/spf13/cobra`、`gitea.com/gitea/gitea-mcp`、`codeberg.org/goern/forgejo-mcp/v2` 这些既是导入路径、也是真实的 git 仓库地址。`go` 命令直接去那个 VCS host（GitHub / Gitea / Codeberg / 自建）`git clone` 拉源码——**没有"上传到某个 registry"这一步**。
- **module proxy 是缓存、不是注册中心**。默认 `GOPROXY=https://proxy.golang.org,direct`（[官方](https://proxy.golang.org)）：proxy 只是**首次被请求时**去源仓库惰性抓取并缓存的镜像，任何人都没"发布"到它；`,direct` 是回退——proxy 没有就直接 git 拉源。所以模块能活在**任意** git host 上，这正是 gitea-mcp 在 `gitea.com`、forgejo-mcp 在 `codeberg.org` 却都能 `go install` 的原因。
- **"发版" = 打一个 git tag**。语义化版本（`v1.2.3`）就是仓库里的 git tag，`@latest` 解析成最新的语义化 tag。没有审核、没有上传、没有"包名注册"环节（[Module version numbering](https://go.dev/ref/mod#versions)）。
- **校验靠 checksum database**，不靠中心仓库信任。`go.sum` + `sum.golang.org`（[官方](https://sum.golang.org)）记录每个模块版本的哈希，防篡改；这是完整性机制，不是"平台"。
- **主版本进路径**：`v2+` 要在 import 路径带 `/v2`、`/v3` 后缀（semantic import versioning，[官方](https://go.dev/ref/mod#major-version-suffixes)）——所以 forgejo-mcp 的装法是 `codeberg.org/goern/forgejo-mcp/v2@latest`，少了 `/v2` 会找错模块。

对照记忆：

| | PyPI / npm / crates.io | Go modules |
| --- | --- | --- |
| 有没有中心 registry | 有，按名字下载/上传 | **无**，import 路径即源码 URL |
| 包名 | 中心命名空间（会抢注、会撞名） | 全 URL 路径，**天生全局唯一** |
| 发布动作 | `twine upload` / `npm publish`（上传产物） | **推一个 git tag**（不上传任何东西） |
| proxy.golang.org 的角色 | —— | **缓存镜像**（惰性抓取），非注册中心 |
| 装到哪来的 | registry 服务器 | 直接从 VCS host（可自建） |

> 副作用两面：好处是没有名字抢注、可完全自建自控、迁移 host 只改路径；代价是模块可用性理论上依赖源 host 在线（被 proxy 缓存缓解），且没有一个"官方唯一平台"背书——判断某个包是否官方，只能看它挂在哪个组织的仓库下（例：gitea-mcp 在官方 `gitea.com/gitea` 组织下 = 第一方；Forgejo 侧无第一方 MCP，详见 [git-server.md](git-server.md) 第四部分）。`pkg.go.dev` 是文档/搜索索引（爬 proxy），也**不是**准入门槛。

---

## 二、原生装法：`go install` / `go run pkg@version`

Go 写的 CLI 工具，标准装法是**从源码编译**（需要本机有 Go 工具链），不是下预编译二进制。两条命令（[官方 go install](https://go.dev/ref/mod#go-install)）：

```bash
go install <module-path>[/cmd]@<version>   # 编译并把二进制装进 $GOBIN，持久留用
go run     <module-path>[/cmd]@<version>   # 编译到临时目录、跑完即弃，不落二进制
```

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

---

## 三、`pixi global install go` 的 cgo 坑（conda-forge go 包）

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
