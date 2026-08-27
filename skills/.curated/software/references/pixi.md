# pixi（conda-forge 的跨语言环境管理器）

[pixi](https://pixi.sh/) 使用笔记。本篇只讲 **pixi 自身的操作模型**——全局环境怎么组织、命令怎么被暴露出来、升级 / 查包 / 临时跑各用什么。下面的说法据本机实测，版本 `pixi 0.65.0`（2026-08-01）。

具体踩坑另有出处：`pixi global install go` 的 cgo 编译器坑见 [go.md](go.md#cgo-pitfall)；pixi 在包管理器全景里的定位与 conda / uv 的分工见 [package-managers.md](package-managers.md#env-manager)；用 pixi 补齐用户态系统库（`LD_LIBRARY_PATH`、`pixi exec` 临时跑、pixi 项目 `[pypi-dependencies]` 三种方案）见 `browser-use` skill 的浏览器依赖章节。

## `pixi global` 是清单驱动的

真相源不是"你敲过哪些安装命令"，而是一份清单：`~/.pixi/manifests/pixi-global.toml`。`pixi global list` 第一行就写明了这点（`Global environments as specified in '…'`）。

清单结构（实测节选）：

```toml
version = 1

[envs.worktrunk]
channels = ["conda-forge"]
dependencies = { worktrunk = "*" }
exposed = { wt = "wt" }

[envs.go]
channels = ["conda-forge"]
dependencies = { go = "*" , c-compiler = "*" }
exposed = { go = "go", gofmt = "gofmt" }
```

三个字段各管一件事：`dependencies` 是这个环境里装什么，`exposed` 是把哪些命令放到 `~/.pixi/bin`，`channels` 默认 conda-forge。**手改清单后用 `pixi global sync` 对齐**已安装环境——这是"想装的东西不方便用子命令表达"时的正规入口（如把某个环境的 `exposed` 清空、只当库源用）。

`pixi global` 的子命令按"改清单的哪一部分"分：`install`/`uninstall` 管环境整体，`add`/`remove` 管某环境的依赖，`expose` 管命令暴露，`sync` 让磁盘追上清单，`list`/`tree` 只读查看。

## 一个包默认一个环境

`pixi global install <包>` 会新建一个**同名环境**只装这一个包。要把多个包塞进同一个环境，用 `-e/--environment <环境名>`：

```bash
pixi global install --environment go c-compiler   # 加进已存在的 go 环境，不新建
```

这是修 conda-forge 版 go 的 cgo 坑的正统办法（[go.md](go.md#cgo-pitfall)），也是"装一堆库给别的程序当依赖用"的做法——库包往往会顺带暴露一堆用不上的命令，这时把该环境的 `exposed` 清空再 `sync`。

## `~/.pixi/bin` 里放的是 trampoline，不是软链

排障时容易被这点误导：`~/.pixi/bin/wt`、`~/.pixi/bin/pandoc` 这些**不是**指向环境里真实二进制的符号链接，`readlink` 什么也读不到。实测它们是**同一个 trampoline 二进制的硬链接**（本机 23 个暴露命令的 `ls -l` 显示同样的大小、链接数 23），真正指向哪里写在旁边的 JSON 里：

```jsonc
// ~/.pixi/bin/trampoline_configuration/wt.json
{
  "exe": "/home/<用户>/.pixi/envs/worktrunk/bin/wt",
  "path_diff": "/home/<用户>/.pixi/envs/worktrunk/bin",
  "env": { "CONDA_PREFIX": "…/envs/worktrunk", "CONDA_SHLVL": "1" }
}
```

于是三件事有了解释：命令能带着 `CONDA_PREFIX` 和环境自己的 `PATH` 跑（不用先 activate）；查"这个命令到底是哪个环境的"要看那份 JSON 而不是 `readlink`；`~/.pixi/bin` 只要进了 `PATH`（本机是 rc 文件里一行 `export PATH="$HOME/.pixi/bin:$PATH"`），所有全局环境的入口就一并接上了。

真实二进制在 `~/.pixi/envs/<环境名>/bin/`；脚本、systemd 单元里要写绝对路径时，两条路径都能用，但 `~/.pixi/bin/<命令>` 更稳（换环境名不受影响）。

## 升级用 `update`，`upgrade` 已被移除

```
$ pixi global upgrade worktrunk
Error:   × `pixi global upgrade` has been removed, and will be re-added in future releases
  ╰─▶ You can call `pixi global update` for most use cases
```

改用 `pixi global update <环境名>`（省略参数则全量），成功时输出形如 `✔ Updated package worktrunk=0.66.0 -> 0.71.0 in environment worktrunk.`。注意参数是**环境名**而不是包名——两者默认同名，只有在用 `-e` 把多个包塞进同一环境时才会分叉。

## 装之前先 `pixi search`

`pixi search <包>` 直接查 conda-forge 有没有、最新版本多少，输出里带 `Version`/`Build`/`Size`/`License`/`Subdir`。它能一次性回答两个常见问题：**这个工具能不能用 pixi 装**（conda-forge 没有就得换 `uv`/`cargo`/发行版包），以及**pixi 渠道的版本落后官方多少**（差得多就得掂量是不是改走上游安装脚本）。

## 不想留常驻环境就用 `pixi exec`

`pixi exec` 把包装进**临时**环境跑一次性命令，不写全局清单、不在当前目录留 `pixi.toml`/`.pixi/`：

```bash
pixi exec -s <包A> -s <包B> -- <命令>
pixi clean cache --exec        # 清掉这些临时环境
```

定位上等价于 `uv run --with`，区别是它只接 conda matchspec、不接 PyPI 包。
