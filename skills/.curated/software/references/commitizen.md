# Commitizen（cz）

[commitizen](https://commitizen-tools.github.io/commitizen/) 按 Conventional Commit
消息算出下一个版本号、打 tag、生成 `CHANGELOG.md`。典型发版链路：本地 `cz bump`（改版本号
+ 写 `CHANGELOG` + bump commit + 打 annotated tag）→ push tag → tag 触发 CI 构建并发布到
PyPI（**cz 只管版本号与 tag，不负责发布**）。几处容易踩：Python 的版本号规范（PEP 440，
不是 SemVer）、手改 `CHANGELOG` 会不会被下次 bump 冲掉、prerelease 与正式段的关系。

## 版本号规范：PEP 440（alpha / beta / rc / dev / post）

Python 包的版本号走 [PEP 440](https://peps.python.org/pep-0440/)，不是 SemVer。公开版本号
形如 `[N!]N(.N)*[{a|b|rc}N][.postN][.devN]`：

- **release 段** `X.Y.Z`：正式版本。
- **pre-release** `aN` / `bN` / `rcN`：alpha / beta / release candidate。PEP 440 会**归一化**
  别名——`alpha`→`a`、`beta`→`b`、`c`/`pre`/`preview`→`rc`。所以规范形是 `1.2.0a0`、
  `1.2.0b1`、`1.2.0rc2`（**不是** SemVer 的 `1.2.0-alpha.1` 那种连字符点号写法）。
- **post-release** `.postN`：排在 `X.Y.Z` **之后**的小修（打包元数据修正等，代码没变）。
  `1.2.0.post1` > `1.2.0`。
- **dev-release** `.devN`：排在同级一切**之前**，可挂在任意段上（`1.2.0a1.dev1 < 1.2.0a1`）。
- **epoch** `N!` 与 **local** `+xyz` 少用；local 版本 PyPI 不接受。

排序（同一 release 内）：`1.2.0.dev0 < 1.2.0a0 < 1.2.0b0 < 1.2.0rc0 < 1.2.0 < 1.2.0.post0
< 1.2.1`。

**最关键的下游后果：预发布默认装不到。** `pip install pkg` 会**跳过**预发布，除非 `--pre`、
或用精确的 `==X.Y.Za0`、或写一个只匹配预发布的 specifier；PyPI / GitHub 的 "latest" 也不会
指向预发布。所以 alpha 是"上架了、但要显式点名才拿得到"的状态——正合"发出去让 CI 验、但不
污染正式用户"的用途。

commitizen 侧映射：`cz bump --prerelease alpha|beta|rc`（简写 `-pr`）把 `X.Y.Z` 递进到下一个
版本的 `a0` / `b0` / `rc0`，再跑一次递增 `aN`；`--devrelease N` 出 `.devN`。config 里
`version_scheme` 选 `pep440`（默认）/ `semver` / `semver2`——Python 包用 `pep440` 才出上面
这套规范形。〔置信度：版本形态与排序来自 PEP 440；cz flag 来自 CLI help（cz 4.16.4）。〕

## 手改 CHANGELOG.md 是否安全

**`cz bump` 保留手改；裸 `cz changelog` 抹掉手改。**

- 裸 `cz changelog`（不带 flag）从 commit message **整篇重生成**——它自己的 `--help`
  就写着 *"Generate changelog (note that it will overwrite existing files)"*。任何不在
  commit message 里的手写文字全没。
- `cz changelog --incremental` 只为"比文件顶部已有版本更新的 commit"生成条目并
  **prepend** 到顶，从那个版本往下的内容**逐字保留**。`--help` 明说：
  *"useful if the changelog has been manually modified."*
- `[tool.commitizen]` 里设了 `update_changelog_on_bump = true` 时，`cz bump` 的
  changelog 步骤走的**就是 incremental**——所以 bump 从不冲掉对已发布版本段的手改。

实测（cz 4.16.4）：把文件截到只剩某旧版本段、在里面塞一个 commit message 里绝不存在的
哨兵注释，再对副本分别跑两种模式。`--incremental` → 哨兵存活、且新版本段被 prepend 到它
上面；裸 `cz changelog` → 哨兵消失（整篇按 commit 重写）。〔置信度：高，直接复现〕

实用规则：

- 放心手改过去的 `## vX.Y.Z` 段，`cz bump` 会保留。
- **绝不在有手改历史的仓库里跑裸 `cz changelog`**——要么 `--incremental`，要么直接让
  `cz bump` 代劳。
- 保持 `## vX.Y.Z` 版本头原样（形态随 `tag_format`）——incremental 靠找到最顶部那个头来
  决定"从哪往下逐字保留"。

## prerelease 会独占一个 changelog 段

`cz bump --prerelease alpha` 产出 PEP 440 预发布号（`X.Y.Z` → `X.Y.Za0`、再 `a1`…），
并按至此的 commit 生成它自己的 `## vX.Y.Za0` 段。

之后转正（`cz bump` 到 `X.Y.Z`）时，cz 会 prepend 一个**新的** `## vX.Y.Z` 段，里面
**只含预发布 tag 之后的 commit**——常常只有 docs/chore，即近乎空段，因为功能 commit 都在
预发布段里。两种拿到完整正式 notes 的办法：

- `--merge-prerelease`（或 config `changelog_merge_prerelease = true`）：`--help` 说
  *"Collect all changes from prereleases into the next non-prerelease"*——把预发布的所有
  改动收进正式段。但它是**从 commit message 重生成**，所以对预发布段做的手改润色不会被带
  过来，会重新按 commit 推导。
- 或手写正式段：incremental bump 下你手写的 `## vX.Y.Z` 段会被保留，可把预发布段润色好的
  文字**上提**进正式段。

〔置信度：一版本一段、`--merge-prerelease` 语义来自 CLI help（cz 4.16.4）；
`--merge-prerelease` 与"已手改过的预发布段"在 incremental 下的确切交互**未实测**，依赖前先
验证。〕

## pre_bump_hooks 在版本文件写入之后才跑

`pre_bump_hooks`（拿 lint / 测试当发版闸门）**在 cz 已经把新版本写进版本文件 +
`CHANGELOG.md` 之后、做 bump commit 和 tag 之前**才跑。所以 hook **失败**会中止 bump，
此时版本文件处于**已改**（`pyproject.toml` / lockfile / changelog 里已是新版本号）但
**无 bump commit、无 tag** 的半途状态。〔置信度：高，cz 4.16.4 实见——一个失败的 pytest
hook 把文件留在新版本号且无 tag。〕

恢复：把这些被改的文件丢弃（`git restore` / `git stash`）回到 bump 前状态，修好起因，重跑
`cz bump`。因为还没 commit、没 tag，**什么都没发出去**——闸门起了作用。

让 hook 稳一点：用不依赖 console-script 解析的方式调测试/lint 工具（如 `python -m pytest`
而非裸 `pytest`），这样闸门只在真失败时挡、而不是被"找不到可执行文件"的 spawn error 误挡。

## tag 触发的自动发版 CI

`cz bump` 只在本地产出 bump commit + tag，**发布交给 CI**：push 上去的 tag 触发一个 workflow
去 build + 建 GitHub Release + 发 PyPI。典型 GitHub Actions 形态（省略了 artifact 上传/下载等
常规步骤）：

```yaml
on:
  push:
    tags:
      - 'v*'          # 用 v*，别用 v*.*.*：后者会漏掉 4 段的 PEP 440 tag
                      # （vX.Y.Z.devN / vX.Y.Z.postN）
jobs:
  build:
    steps:
      - uses: actions/checkout@v4
      - run: python -m build            # 出 sdist + wheel

  github-release:
    needs: build
    steps:
      # 1) 从 tag 判定 stable vs prerelease：只有纯 vN.N.N 算正式，
      #    带 a/b/rc/dev/post 的一律标 prerelease，免得抢走 "Latest" 徽章
      - id: classify
        run: |
          if [[ "$GITHUB_REF_NAME" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
            echo "pre=false" >> "$GITHUB_OUTPUT"
          else
            echo "pre=true"  >> "$GITHUB_OUTPUT"
          fi
      # 2) 从提交的 CHANGELOG.md 里 awk 切出本 tag 那一段当 release body
      - uses: softprops/action-gh-release@v1
        with:
          body_path: /tmp/section.md
          prerelease: ${{ steps.classify.outputs.pre }}
          generate_release_notes: true   # 在你的 body 下面再追加自动 commit/PR 列表

  pypi:
    needs: build
    permissions: { id-token: write }     # OIDC trusted publishing，无需 API token
    steps:
      - uses: pypa/gh-action-pypi-publish@release/v1
        with:
          skip-existing: true            # 重跑不因"版本已存在"而失败
```

几个要点：

- **changelog 抽取 vs 重生成**：从提交的 CHANGELOG **抽取**对应 tag 段（如 `awk` 切
  `## v<version>`）会原样发布你手写的文字；在 CI 里**重生成** changelog 则不会。若脚本只抽
  顶部那个匹配段，发布的就是**转正的 `## vX.Y.Z` 段**、不是它下面的预发布段——所以正式段必须
  有真内容（呼应「prerelease 会独占一个 changelog 段」）。⚠️ 朴素的子串匹配（`$0 ~ "4.0.0"`）
  会误中预发布行 `v4.0.0a0`（含子串 `4.0.0`）；靠"正式段被 prepend 在上面、先命中"兜住，或把
  匹配锚死到行首整串。
- **prerelease 分类**照搬 PEP 440：tag 带 `a/b/rc/dev/post` → GitHub Release 标 prerelease，
  与 §版本号规范 里"预发布默认不是 latest"一致。`.postN` 严格说是正式后的清理版，简化当
  prerelease 处理通常无妨。
- **PyPI 不可变**：某个 `X.Y.Z` 一旦上架**不能覆盖**，只能 yank（且 yank 也回不到原状）。
  `skip-existing` 只是让重跑不报错，不等于能改内容。所以坏版本 = 发下一个号、不是原地修——
  这也是先发 alpha 让 CI 跑通、装下来 smoke 一遍再转正的理由。
- **谁触发**：`cz bump` push tag 后 CI 自动起飞；tag 一上 origin 就等于按下发布键，push 前把
  版本号 / CHANGELOG 段 / tag 名核一遍（不可逆）。

〔置信度：该流水线形态与各步行为在本环境实跑验证过一轮（build → 抽取 changelog → 建 GH
Release → 发 PyPI）；具体 action 版本 / 字段按你的仓库为准。〕
