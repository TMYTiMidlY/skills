# 自动发版：Commitizen、semantic-release 与 Registry OIDC

自动发版先要选定**版本号的真相源**，再谈 CI。常见的两种模型：

| 模型 | 版本号由谁决定 | 版本文件 / tag 的角色 | 典型工具 |
|---|---|---|---|
| **配置文件为真相源** | 人或显式 bump 命令 | 配置文件先改，tag 跟随配置版本 | Commitizen |
| **Git 历史为真相源** | CI 分析上个 tag 之后的 Conventional Commits | tag 是发布结果；`package.json` 是 prepare 阶段写回的产物 | semantic-release |

二者都能自动生成 CHANGELOG 和 GitHub Release，但心智模型相反：

- Commitizen：**先 bump，再发布**。
- semantic-release：**先合入提交，CI 决定要不要 bump / bump 到哪**。

不要一边让 Commitizen 手工改版本、一边又让 semantic-release 自己推导同一个包的版本；两个写入者会争夺真相源。

Commitizen 的 PEP 440、prerelease、手改 CHANGELOG 与 `pre_bump_hooks` 细节见同目录的
[commitizen.md](commitizen.md)；本文聚焦跨语言的发布架构与可直接套用的 CI。

## <a id="commitizen-config-version"></a>Commitizen：配置文件为版本真相源

### QuantumAtlas 的配置形态

QuantumAtlas 把 PEP 621 的 `[project].version` 作为唯一版本字段，Commitizen 通过
`version_provider = "pep621"` 读写它：

```toml
[project]
name = "example-project"
version = "0.1.0"

[tool.commitizen]
name = "cz_conventional_commits"
tag_format = "v$version"
version_scheme = "pep440"
version_provider = "pep621"
update_changelog_on_bump = true
major_version_zero = true
```

> 该结构来自 QuantumAtlas 锁定版本的
> [`pyproject.toml`](https://github.com/IAI-USTC-Quantum/QuantumAtlas/blob/e12d415ac198dd0b831c44496dd1bd69cc541c97/pyproject.toml#L1-L3)
> 与
> [`[tool.commitizen]`](https://github.com/IAI-USTC-Quantum/QuantumAtlas/blob/e12d415ac198dd0b831c44496dd1bd69cc541c97/pyproject.toml#L54-L60)。

这里的关键不是 TOML 语法，而是**只留一个可写版本字段**：

- 仓库 checkout 存在时，运行时优先读 `pyproject.toml`。
- 安装后没有源码配置文件时，回退到 distribution metadata。
- 测试显式断言运行时版本 = `[project].version`，并锁定 Commitizen 配置。

> 版本优先级见 QuantumAtlas
> [`atlas/__init__.py`](https://github.com/IAI-USTC-Quantum/QuantumAtlas/blob/e12d415ac198dd0b831c44496dd1bd69cc541c97/atlas/__init__.py#L14-L33)，
> 配置契约见
> [`tests/test_cli.py`](https://github.com/IAI-USTC-Quantum/QuantumAtlas/blob/e12d415ac198dd0b831c44496dd1bd69cc541c97/tests/test_cli.py#L20-L36)。

日常提交只写 Conventional Commits；发版时运行：

```bash
# 只预演，不改文件 / commit / tag
uv run --with commitizen cz bump --dry-run

# 真正 bump：
# 1) 更新 [project].version
# 2) 增量更新 CHANGELOG.md
# 3) 创建 bump commit
# 4) 创建 v$version annotated tag
uv run --with commitizen cz bump
```

`update_changelog_on_bump = true` 走增量 CHANGELOG：已发布版本段的手改会保留。不要用裸
`cz changelog` 重写已有的人工内容。

### 配置版本驱动 GitHub Release

发布 workflow 不重新推导版本，而是**读配置文件里的版本**，验证对应 tag，然后从已提交的
CHANGELOG 抽取本版本段作为 GitHub Release 正文：

```yaml
name: Tag and publish release

on:
  workflow_dispatch:
  push:
    branches: [main]
    paths:
      - pyproject.toml
      - CHANGELOG.md

permissions:
  contents: write

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: main
          fetch-depth: 0
          fetch-tags: true

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Read version from pyproject.toml
        id: version
        run: |
          VERSION="$(
            python -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])'
          )"
          echo "version=$VERSION" >> "$GITHUB_OUTPUT"
          echo "tag=v$VERSION" >> "$GITHUB_OUTPUT"

      - name: Validate tag position
        id: tag
        run: |
          set -euo pipefail
          TAG="${{ steps.version.outputs.tag }}"
          HEAD_SHA="$(git rev-parse HEAD)"
          if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
            test "$(git rev-list -n 1 "$TAG")" = "$HEAD_SHA"
            echo "exists=true" >> "$GITHUB_OUTPUT"
          else
            echo "exists=false" >> "$GITHUB_OUTPUT"
          fi

      - name: Build distributions
        run: |
          python -m pip install build
          python -m build

      - name: Extract this version from CHANGELOG
        run: |
          VERSION="${{ steps.version.outputs.version }}"
          awk -v version="$VERSION" '
          BEGIN { found=0 }
          /^## / {
            if (found) exit
            if ($0 ~ version) found=1
          }
          found { print }
          ' CHANGELOG.md > /tmp/changelog.txt
          test -s /tmp/changelog.txt || echo "Version $VERSION" > /tmp/changelog.txt

      - name: Create release tag
        if: steps.tag.outputs.exists == 'false'
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git tag -a "${{ steps.version.outputs.tag }}" \
            -m "Release ${{ steps.version.outputs.tag }}"
          git push origin "${{ steps.version.outputs.tag }}"

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        with:
          tag_name: ${{ steps.version.outputs.tag }}
          body_path: /tmp/changelog.txt
          files: |
            dist/*.tar.gz
            dist/*.whl
          generate_release_notes: true
```

QuantumAtlas 的已验证实现见锁定的
[`release.yml`](https://github.com/IAI-USTC-Quantum/QuantumAtlas/blob/e12d415ac198dd0b831c44496dd1bd69cc541c97/.github/workflows/release.yml#L30-L109)：

- `body_path` 原样展示 Commitizen 已写入、可人工润色的本版本 CHANGELOG 段。
- `generate_release_notes: true` 再附加 GitHub 推导的 commit / PR 列表。
- tag 与配置版本不一致时 fail closed，不从一个偶然 tag 反向覆盖配置文件。

## <a id="semantic-release-model"></a>semantic-release：Git 历史为版本真相源

semantic-release 是 Node / npm 生态里最接近 Commitizen 的自动发版编排器，但它把显式
`cz bump` 搬进 CI：

1. 找上一个 release tag。
2. 读取此后全部 commit。
3. 按 Conventional Commits 选**最高** release type。
4. 算出下一个 SemVer。
5. 生成 release notes。
6. 执行 prepare 插件（写 CHANGELOG / `package.json`、构建产物、提交 release commit）。
7. 创建并推送 tag。
8. 执行 publish 插件（npm、GitHub Release 等）。

核心在 tag 前执行 `verifyConditions`，没有可发布提交时则正常退出；真正有 release 时，
`generateNotes → prepare → tag/push → publish → success`。

> 生命周期顺序见
> [`semantic-release@v25.0.8`](https://github.com/semantic-release/semantic-release/blob/v25.0.8/index.js#L104-L186)
> 与
> [发布阶段](https://github.com/semantic-release/semantic-release/blob/v25.0.8/index.js#L198-L221)。

### 提交到版本号的映射

默认 Conventional Commit 映射：

| 最高级提交 | 版本变化 |
|---|---|
| `fix:` / `perf:` | patch：`0.1.0 → 0.1.1` |
| `feat:` | minor：`0.1.0 → 0.2.0` |
| `!` 或 `BREAKING CHANGE:` | major：`0.1.0 → 1.0.0` |
| 只有 `docs:` / `ci:` / `chore:` / 普通 `refactor:` / `test:` | 不发布 |

> 默认规则锁
> [`@semantic-release/commit-analyzer@v13.0.1`](https://github.com/semantic-release/commit-analyzer/blob/v13.0.1/lib/default-release-rules.js#L6-L33)；
> 分析器遍历所有 commit、保留最高 release type，见
> [`index.js`](https://github.com/semantic-release/commit-analyzer/blob/v13.0.1/index.js#L28-L88)。

因此：

- 一次 push / merge 带 20 个 commit，仍然**最多只发一个版本**；CHANGELOG / Release notes 汇总全部相关 commit。
- 多次独立 push 会产生多个 workflow run；各 run 重新从最新 tag 计算。
- `major_version_zero = true` 是 Commitizen 的行为；semantic-release 默认遇 breaking 就升
  `1.0.0`。还不想离开 `0.x` 时，不要随意写 breaking，或显式自定义 release rules。
- tag 是 semantic-release 的**产物**，不是触发器。推荐由 `push` 到发布分支触发，让工具自己打 tag。

### 配置文件与 CLI 优先级

semantic-release 用 cosmiconfig 搜索 `release` 配置（常见为 `.releaserc*`、
`release.config.*` 或 `package.json` 对应字段），然后用 CLI / API 参数覆盖配置文件：

```js
let options = { ...config, ...cliOptions };
```

> 查找与优先级见
> [`lib/get-config.js`](https://github.com/semantic-release/semantic-release/blob/v25.0.8/lib/get-config.js#L17-L26)；
> 默认分支、tag 格式与默认插件见
> [同文件](https://github.com/semantic-release/semantic-release/blob/v25.0.8/lib/get-config.js#L62-L84)。

这与 Commitizen 的“配置文件版本优先”不同：semantic-release 的配置文件描述**规则**，
具体版本仍由“上个 tag + commits”决定。

### 插件分工

| 插件 | 作用 |
|---|---|
| `@semantic-release/commit-analyzer` | commits → patch / minor / major / no release |
| `@semantic-release/release-notes-generator` | commits → `nextRelease.notes` |
| `@semantic-release/changelog` | 把 notes 写入 `CHANGELOG.md` |
| `@semantic-release/npm` | prepare 时写 `package.json` version；publish 时运行 `npm publish` |
| `@semantic-release/exec` | 在生命周期中运行自定义构建（如 Bun 多平台二进制） |
| `@semantic-release/git` | 把 `package.json` / CHANGELOG 等提交回发布分支 |
| `@semantic-release/github` | 建 GitHub Release、显示 notes、上传二进制 / checksum |

`@semantic-release/npm` 在 prepare 阶段运行 `npm version --no-git-tag-version`，publish 阶段
直接执行 `npm publish`：

> 见
> [`prepare.js`](https://github.com/semantic-release/npm/blob/v13.1.5/lib/prepare.js#L10-L27)
> 与
> [`publish.js`](https://github.com/semantic-release/npm/blob/v13.1.5/lib/publish.js#L17-L34)。

插件数组顺序很重要：先让 npm plugin 写入新版本，再构建会把版本号嵌入二进制；最后才由
git plugin 提交这些生成文件。

## <a id="npm-bootstrap"></a>npm 包的首次发布

Trusted Publisher 是**包级设置**。全新的包还没有 Settings 页面，因此第一次创建包不能先配
OIDC；最干净的引导方式是人在本机通过 npm CLI 的浏览器登录 + 2FA 发布一次。

### 准备 package.json

至少确认：

```json
{
  "name": "<package-name>",
  "version": "0.1.0",
  "license": "MIT",
  "repository": {
    "type": "git",
    "url": "git+https://github.com/<owner>/<repo>.git"
  },
  "files": ["dist/<entry>.mjs"],
  "bin": {
    "<command>": "dist/<entry>.mjs"
  }
}
```

- `npm view <package-name> version` 返回 404 才表示未占用。
- `repository.url` 要与后续 Trusted Publisher 的 GitHub 仓库一致。
- `LICENSE`、README、入口文件、`files` / `bin` 都在首发前确认。

### 浏览器登录与首发

```bash
# npm v9+ 默认 auth-type=web；显式写出更清楚
npm login --auth-type=web
npm whoami

pnpm test
pnpm build
npm pack --dry-run

# unscoped public 包；scoped public 包也需要 --access public
npm publish --access public
```

npm 官方把这条叫 **web authentication**：CLI 打开浏览器，用户在网页使用安全密钥 /
TOTP 完成认证；它不是 CI 的 OIDC Trusted Publishing。

> `auth-type` 默认值与可选项见 npm v11 的
> [`npm-login`](https://github.com/npm/documentation/blob/9864f7a0fe8740bab99508db53cabe8aa4b6cb86/content/cli/v11/commands/npm-login.mdx#L80-L85)，
> 浏览器 + 安全密钥流程见
> [2FA 登录文档](https://github.com/npm/documentation/blob/9864f7a0fe8740bab99508db53cabe8aa4b6cb86/content/getting-started/setting-up-your-npm-user-account/accessing-npm-using-2fa.mdx#L38-L60)。

临时 `NPM_TOKEN` 只作为无法进行本机首发时的引导备用，不是首选；包创建后应尽快切到 OIDC，
并撤销不再使用的发布 token。

### 建立版本基线

如果仓库已有大量 `feat:` / `fix:` / breaking 历史，但首发版本是 `0.1.0`，先在首发对应 commit
打种子 tag：

```bash
git tag -a v0.1.0 -m "0.1.0 baseline"
git push origin v0.1.0
git push origin main
```

tag 要先于 main 推送，让首次 semantic-release run 看见基线；否则它会把全部历史当作待发布
commits；只要存在任意可发布 commit，**无 prior tag 的首次自动版本固定为 `1.0.0`**，与 commit
最终分析成 patch / minor / major 无关。已有 `0.x` 基线后，breaking commit 才是另一条升
`1.0.0` 的路径。

### 初始 CHANGELOG 与 GitHub Release 的 bootstrap

“本机 `npm publish` + seed tag”只完成了**包与版本基线**，不会自动补出这个历史版本的
CHANGELOG 或 GitHub Release：

- semantic-release 是**只向前**的：它只分析上个 release tag 之后的 commits。
- seed tag 已声明“此前内容都属于 `0.1.0`”，所以下一次 run 不会倒推 `0.1.0` notes。
- Git tag 和 GitHub Release 是两种对象；push tag 不等于创建 Release。

因此首版通常还要做一次**发布元数据 bootstrap**：

1. 在 main 的 `CHANGELOG.md` 手写初始版本段（功能、安装、已知限制）。
2. 从 seed tag 对应源码构建初始附件。
3. 为既有 tag 创建 GitHub Release，正文使用该 CHANGELOG 段，并上传 artifacts / checksum。
4. 验证后删除一次性 workflow；此后只保留 semantic-release 的正式 workflow。

不要为了把后补的 CHANGELOG 塞进 tag 而重写已经发布的 seed tag：npm `0.1.0` 与 tag 的源码
关联应保持不变。CHANGELOG 可以在 tag 之后补进 main，GitHub Release 仍指向原 tag。

下面是一次性 bootstrap workflow。它把 main 当**发布元数据来源**，把输入 tag 当**源码与构建
来源**，避免后续 CI / 文档提交混入首版二进制：

```yaml
name: bootstrap initial GitHub Release

on:
  workflow_dispatch:
    inputs:
      tag:
        description: Existing seed tag, for example v0.1.0
        required: true
        type: string

permissions:
  contents: write

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      # main：读取后来补写的 CHANGELOG。
      - uses: actions/checkout@v4
        with:
          ref: main
          path: metadata

      # seed tag：构建与已发布 npm 版本对应的源码。
      - uses: actions/checkout@v4
        with:
          ref: ${{ inputs.tag }}
          path: source

      - uses: pnpm/action-setup@v4
        with:
          # 两个 checkout 都在子目录，仓库根没有 packageManager 字段可供自动发现。
          version: 10

      - uses: actions/setup-node@v4
        with:
          node-version: 24

      - uses: oven-sh/setup-bun@v2
        with:
          bun-version: latest

      - name: Build tag artifacts
        working-directory: source
        run: |
          pnpm install --frozen-lockfile
          pnpm test
          pnpm run binaries
          cd dist
          sha256sum \
            <command>-linux-x64 \
            <command>-darwin-x64 \
            <command>-darwin-arm64 \
            <command>-windows-x64.exe \
            <command>.mjs \
            > SHA256SUMS.txt

      - name: Extract changelog section
        env:
          TAG: ${{ inputs.tag }}
        run: |
          VERSION="${TAG#v}"
          awk -v version="$VERSION" '
          /^## / {
            if (found) exit
            if ($0 ~ version) found=1
          }
          found { print }
          ' metadata/CHANGELOG.md > /tmp/release-notes.md
          test -s /tmp/release-notes.md

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          tag_name: ${{ inputs.tag }}
          body_path: /tmp/release-notes.md
          generate_release_notes: true
          files: |
            source/dist/<command>-linux-x64
            source/dist/<command>-darwin-x64
            source/dist/<command>-darwin-arm64
            source/dist/<command>-windows-x64.exe
            source/dist/<command>.mjs
            source/dist/SHA256SUMS.txt
```

如果 tag 版本的旧构建链已经无法在当前 runner 上运行，可以像已验证的 `asmgr v0.1.0`
bootstrap 那样从 main 构建，但要先用 `git diff <tag>..HEAD -- <runtime-paths...>` 证明运行时
源码与 tag 一致；不能仅凭“版本号没变”就上传当前 HEAD 的二进制。

## <a id="npm-trusted-publisher"></a>npm Trusted Publisher 与 OIDC

包创建后，在 npmjs.com 的包 Settings → Trusted Publisher → GitHub Actions 填：

| 字段 | 值 |
|---|---|
| Organization or user | `<github-owner>` |
| Repository | `<repo>` |
| Workflow filename | `release.yml`（只填文件名） |
| Environment | `npmjs` |
| Allowed actions | `npm publish` |
| Allow `npm stage publish` | 不启用（当前流水线直接发布） |

npm 会把 GitHub 签发的短期 OIDC JWT 中的 repository / workflow / environment claims 与这张
白名单比对，再换一张短期 publish token；仓库里不需要 `NPM_TOKEN`。

> npm 对字段、Allowed actions 与运行要求的定义见锁定的
> [Trusted Publisher 文档](https://github.com/npm/documentation/blob/9864f7a0fe8740bab99508db53cabe8aa4b6cb86/content/packages-and-modules/securing-your-code/trusted-publishers.mdx#L5-L17)
> 和
> [GitHub Actions 字段](https://github.com/npm/documentation/blob/9864f7a0fe8740bab99508db53cabe8aa4b6cb86/content/packages-and-modules/securing-your-code/trusted-publishers.mdx#L37-L48)。

### GITHUB_TOKEN 与 OIDC id-token

| 凭据 | 用途 |
|---|---|
| `secrets.GITHUB_TOKEN` | GitHub Actions 自动给每个 run 的临时 GitHub API / git 凭据；semantic-release 用它推 tag / release commit、建 GitHub Release、评论 issue / PR |
| OIDC id-token | `id-token: write` 允许 job 向 GitHub OIDC 端点申请的签名身份断言；npm 验签并换短期发布权 |

`@semantic-release/npm@13.1.5` 会先尝试 OIDC；交换成功就通过 auth verify，失败才回退到传统
token auth：

> 分支逻辑见
> [`verify-auth.js`](https://github.com/semantic-release/npm/blob/v13.1.5/lib/verify-auth.js#L83-L92)，
> GitHub id-token 获取与 npm token exchange 见
> [`token-exchange.js`](https://github.com/semantic-release/npm/blob/v13.1.5/lib/trusted-publishing/token-exchange.js#L31-L45)。

实际 `npm publish` 仍由 npm CLI 执行，因此 release runner 保持 npm CLI ≥ 11.5.1。npm
Trusted Publishing 要求 Node ≥ 22.14；semantic-release@25 的范围更精确：
`^22.14.0 || >=24.10.0`（不含 Node 23 与早期 Node 24），所以最省心是最新 Node 24。
GitHub / npm 官方只支持云托管 runner 的 Trusted Publishing。

### GitHub Environment：Settings 实体与 YAML 引用

下面两处是**同一个 Environment**：

- Repository Settings → Environments → `npmjs`：Environment 实体，可配置审批、分支 / tag
  限制、environment secrets / variables。
- workflow 的 `environment: npmjs`：job 引用该实体；环境名也进入 OIDC claims，必须与 npm
  Trusted Publisher 的 Environment 字段一致。

```yaml
jobs:
  release:
    environment: npmjs
```

如果 `npmjs` 尚不存在，第一次运行这个 workflow 会自动创建同名 Environment；普通 workflow
创建的环境**没有**保护规则或 secrets。只有想加审批、deployment branch 限制或环境 secret 时，
才需要进入 Settings 继续配置。

> 自动创建与默认无保护规则 / secrets 的语义见 GitHub Docs 锁定版本的
> [`manage-environments.md`](https://github.com/github/docs/blob/43ffdaddfbc0e3a789dae85f927b42f195bed054/content/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments.md#L92-L95)；
> 环境分支限制与 secrets 的配置入口见
> [同文件](https://github.com/github/docs/blob/43ffdaddfbc0e3a789dae85f927b42f195bed054/content/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments.md#L73-L95)。

### 普通发布与 staged publishing

Trusted Publisher 的 Allowed actions 可以是 `npm publish`、`npm stage publish` 或两者。

- `npm publish`：CI 成功后版本立即公开；semantic-release 当前走这条。
- `npm stage publish`：先进入 Staged Packages；维护者再用 2FA 审核批准才公开。

`@semantic-release/npm@13.1.5` 的 publish plugin 硬编码执行 `npm publish`，所以把 Trusted
Publisher 配成 stage-only 会让当前 semantic-release 发布失败；要用 staged publishing，需自定义
publish 插件 / 命令，并接受每版人工审批。

> staged publishing 的审核语义与“包必须已存在”见 npm
> [锁定文档](https://github.com/npm/documentation/blob/9864f7a0fe8740bab99508db53cabe8aa4b6cb86/content/packages-and-modules/securing-your-code/staged-publishing.mdx#L5-L29)，
> 2FA 批准与 Trusted Publisher 配合见
> [同文件](https://github.com/npm/documentation/blob/9864f7a0fe8740bab99508db53cabe8aa4b6cb86/content/packages-and-modules/securing-your-code/staged-publishing.mdx#L86-L117)。

OIDC 跑通后，可在 Publishing access 选择 “Require two-factor authentication and disallow
tokens”，再撤销旧 automation token；Trusted Publisher 不受“disallow tokens”影响。
npm 还会为公共仓库 + 公共包的 Trusted Publishing 自动生成 provenance。

> token 收紧与 provenance 见 npm
> [Trusted Publisher 安全建议](https://github.com/npm/documentation/blob/9864f7a0fe8740bab99508db53cabe8aa4b6cb86/content/packages-and-modules/securing-your-code/trusted-publishers.mdx#L218-L248)。

## <a id="semantic-release-template"></a>semantic-release + npm OIDC + Bun 完整模板

下面以“单一 npm CLI 包 + Bun 四平台二进制”为例。把 `<package-name>`、`<command>`、
`<owner>/<repo>` 和产物文件名统一替换。

### package.json

```json
{
  "name": "<package-name>",
  "version": "0.1.0",
  "license": "MIT",
  "type": "module",
  "bin": {
    "<command>": "dist/<command>.mjs"
  },
  "files": [
    "dist/<command>.mjs"
  ],
  "repository": {
    "type": "git",
    "url": "git+https://github.com/<owner>/<repo>.git"
  },
  "packageManager": "pnpm@10.11.0",
  "scripts": {
    "build": "node scripts/bundle.mjs",
    "binaries": "node scripts/build-binaries.mjs",
    "prepare": "node scripts/bundle.mjs",
    "test": "vitest run",
    "release": "semantic-release"
  },
  "devDependencies": {
    "@semantic-release/changelog": "^6.0.3",
    "@semantic-release/exec": "^7.0.3",
    "@semantic-release/git": "^10.0.1",
    "semantic-release": "^25.0.8"
  }
}
```

用 `semantic-release@25`，让其传递依赖自然解析到带 Trusted Publishing 支持的
`@semantic-release/npm@13`；不要在 `semantic-release@24` 上强行 override 旧的 npm plugin。

### scripts/build-binaries.mjs

```js
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

const command = "<command>";
const bundle = resolve(`dist/${command}.mjs`);

// 先刷新 Node 单文件 bundle；它应已经把第三方依赖内联。
execFileSync(process.execPath, ["scripts/bundle.mjs"], { stdio: "inherit" });

const targets = [
  ["bun-linux-x64", `${command}-linux-x64`],
  ["bun-darwin-x64", `${command}-darwin-x64`],
  ["bun-darwin-arm64", `${command}-darwin-arm64`],
  ["bun-windows-x64", `${command}-windows-x64.exe`]
];

for (const [target, output] of targets) {
  execFileSync(
    "bun",
    ["build", "--compile", `--target=${target}`, bundle, "--outfile", `dist/${output}`],
    { stdio: "inherit" }
  );
}
```

### .releaserc.json

```json
{
  "branches": ["main"],
  "plugins": [
    "@semantic-release/commit-analyzer",
    "@semantic-release/release-notes-generator",
    [
      "@semantic-release/changelog",
      {
        "changelogFile": "CHANGELOG.md"
      }
    ],
    "@semantic-release/npm",
    [
      "@semantic-release/exec",
      {
        "prepareCmd": "pnpm run binaries && cd dist && sha256sum <command>-linux-x64 <command>-darwin-x64 <command>-darwin-arm64 <command>-windows-x64.exe <command>.mjs > SHA256SUMS.txt"
      }
    ],
    [
      "@semantic-release/git",
      {
        "assets": ["package.json", "CHANGELOG.md"],
        "message": "chore(release): ${nextRelease.version} [skip ci]\n\n${nextRelease.notes}"
      }
    ],
    [
      "@semantic-release/github",
      {
        "assets": [
          { "path": "dist/<command>-linux-x64", "label": "Linux x64" },
          { "path": "dist/<command>-darwin-x64", "label": "macOS Intel" },
          { "path": "dist/<command>-darwin-arm64", "label": "macOS Apple Silicon" },
          { "path": "dist/<command>-windows-x64.exe", "label": "Windows x64" },
          { "path": "dist/<command>.mjs", "label": "Node bundle" },
          { "path": "dist/SHA256SUMS.txt", "label": "SHA256SUMS.txt" }
        ]
      }
    ]
  ]
}
```

这套顺序产生：

1. 自动推导版本与 release notes。
2. `CHANGELOG.md` 写入同一份 notes。
3. `package.json` 更新为新版本。
4. Bun 构建四平台二进制 + checksum。
5. release commit 回推 main（`[skip ci]` 防自触发）。
6. tag、npm publish、GitHub Release（正文 = release notes，附件 = binaries / bundle / checksum）。

### .github/workflows/release.yml

```yaml
name: release

on:
  push:
    branches: [main]
  workflow_dispatch: {}

concurrency:
  group: release
  # 发布不能中途取消；新 run 排队，轮到时从最新 tag 重新计算。
  cancel-in-progress: false

# 顶层最小权限；只在发布 job 内提权。
permissions:
  contents: read

jobs:
  release:
    permissions:
      contents: write
      issues: write
      pull-requests: write
      id-token: write
    runs-on: ubuntu-latest
    environment: npmjs

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          persist-credentials: false

      - uses: pnpm/action-setup@v4

      - uses: actions/setup-node@v4
        with:
          # Node 24 保证满足 semantic-release@25 / npm Trusted Publishing 要求。
          node-version: 24

      - uses: oven-sh/setup-bun@v2
        with:
          bun-version: latest

      - run: pnpm install --frozen-lockfile
      - run: pnpm test

      - name: Release
        run: npx semantic-release
        env:
          # GitHub API / git push；npm 发布走 OIDC，不配 NPM_TOKEN。
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

npm Trusted Publisher 必须与模板对应：

```text
Organization/user: <owner>
Repository: <repo>
Workflow filename: release.yml
Environment: npmjs
Allowed actions: npm publish
```

### 分支保护与 release commit

`@semantic-release/git` 会直接向发布分支回推 `package.json` + CHANGELOG release commit。
若 main 要求所有变更必须经 PR，默认 `GITHUB_TOKEN` 可能被规则拦截。三种模型任选其一：

- main 允许发布 bot 直接回推。
- 给发布身份配置规则例外。
- 不使用 `@semantic-release/git`，让版本 / CHANGELOG 只存在于 tag、npm 包与 GitHub Release。

不要开启严格 PR 保护后仍假定 release commit 能自然通过。

### concurrency

上面的完整模板启用了 `concurrency`。它不是 semantic-release 的要求（官方自身的 v25
workflow 没有这一段），而是 GitHub Actions 层的发布串行化保险：

```yaml
concurrency:
  group: release
  cancel-in-progress: false
```

只有短时间内多次独立 push / dispatch 发生重叠时才有价值：

- 无 concurrency：两个 run 可能同时从同一个旧 tag 算出同一版本，随后争抢 tag / npm version。
- 有 concurrency：同 group 同时只跑一个；`false` 表示新 run 排队，不中断正在 publish 的 run。
- 排队的 run 真正开始时会重新 checkout、读取最新 tag，因此不会沿用排队前的版本判断。
- 一次 push 带很多 commit 本来就只有一个 run；`concurrency` 只处理**多个 workflow run
  在时间上重叠**的问题。
- 单人、低频仓库可以省略；一旦允许连续 merge / push / 手动 dispatch，启用它的代价很低，
  能避免“npm 已发布但 tag / GitHub Release 另一半失败”的半发布状态。

官方 push-to-branch、最小权限形态可对照
[`semantic-release@v25.0.8` 自身 workflow](https://github.com/semantic-release/semantic-release/blob/v25.0.8/.github/workflows/release.yml#L1-L35)；
其中并没有 concurrency。

## <a id="release-verification"></a>验证发布链路

### 无 release 的认证探针

推一个只有 `ci:` / `docs:` 的变更：

- workflow 会运行。
- semantic-release 先执行 `verifyConditions`（包括 npm OIDC）。
- commit analyzer 返回 no release，正常成功退出。

因此“Release 步骤成功、但没有 tag / Release / 新 npm version”可证明：

- workflow /权限 / `GITHUB_TOKEN` 基本可用。
- npm Trusted Publisher 的 repo / workflow / environment claims 能通过 OIDC verify。

但它**不能**证明真正 publish 路径：Bun 构建、CHANGELOG 写入、release commit、tag、npm 新版本、
GitHub Release 附件仍要等一次 `fix:` / `feat:` 发版验证。

semantic-release 源码先 `verifyConditions`、后 `analyzeCommits`，见
[`index.js`](https://github.com/semantic-release/semantic-release/blob/v25.0.8/index.js#L104-L180)。

### 首次真正自动发版的检查表

下一次推 `fix:`（patch）或 `feat:`（minor）后同时核对：

- `CHANGELOG.md` 新增对应版本段。
- main 有 `chore(release): X.Y.Z [skip ci]`（若用了 git plugin）。
- 新 tag 指向 release commit。
- npm `view <package> version` 返回新版本。
- GitHub Release 正文有自动 notes。
- Release 附件包含四平台二进制、Node bundle、`SHA256SUMS.txt`。
- npm 包页面显示 provenance。

初始版本做完上面的 bootstrap 后，后续不再手写版本号、CHANGELOG 段、tag 或 GitHub
Release。只要下列前提成立，semantic-release 会在**同一个 run** 自动完成：

1. Conventional Commit 中至少有一条 `fix:` / `feat:` / breaking change。
2. release job 能推 main 与 tag（使用 `@semantic-release/git` 时尤其如此）。
3. npm Trusted Publisher 的 owner / repo / workflow / environment 与 OIDC claims 一致。
4. npm CLI、Node、Bun、测试与构建命令成功。
5. `.releaserc` 中 changelog → npm → exec → git → github 的插件与资产路径保持有效。

自动结果包括：推导版本、生成 release notes、更新 CHANGELOG、写 `package.json` 版本、构建
Bun 产物、提交 release commit、打 tag、发布 npm、创建 GitHub Release 并上传附件。配置与
插件生命周期已确定；但每个仓库的**首次真实自动版本**仍应按本检查表验收一次，之后才算
端到端闭环。

### 常见失败

| 现象 | 优先检查 |
|---|---|
| `ENEEDAUTH` / OIDC exchange 失败 | npm Trusted Publisher 的 owner / repo / workflow filename / environment 大小写与 YAML 是否完全一致；job 是否 `id-token: write` |
| no release | 上个 tag 后是否只有 `docs:` / `ci:` / `chore:`；这不是失败 |
| 直接跳 `1.0.0` | 无种子 tag，或出现 breaking commit |
| npm publish 失败但 OIDC verify 成功 | runner 的 npm CLI 是否 ≥ 11.5.1；Allowed action 是否错误地只开了 stage publish |
| release commit push 被拒 | main 分支保护是否禁止 bot 直推 |
| npm 成功但 GitHub Release 缺附件 | `prepareCmd` 是否真的生成与 `assets[].path` 完全一致的文件 |
| environment 自动出现但没有审批 | YAML 只会自动创建空 Environment；保护规则 / reviewers 要在 Settings 另配 |
