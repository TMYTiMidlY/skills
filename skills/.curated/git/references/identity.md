# gh 认证 vs git 提交身份：两套"身份"别混

一句话：**`gh auth login` 配的是"你怎么连上 GitHub"（登录认证 / 传输凭据，用于 clone/pull/push），`git config user.name`/`user.email` 配的是"提交写谁的名字"（作者身份）。两者互不相干——`gh` 不会把登录账户自动转成 Git 的提交姓名和邮箱。** 这是一个反复咬人的易混点：明明 `gh auth login` 走完了、`gh auth status` 也绿了，一提交却仍报 `Author identity unknown`。结论基于 gh 2.x + git 2.4x。

## 两套身份各管什么

| | `gh auth login` | `git config user.name` / `user.email` |
|---|---|---|
| 管什么 | GitHub **登录认证**：拿到并存放 token / 凭据 | 每条 commit 的**作者身份** |
| 用在哪 | clone / pull / push（连网络那一下） | 写进 commit 对象的 `author` / `committer` 字段 |
| 存哪 | 系统凭据库或 gh 的 `hosts.yml`；HTTPS 下经 **credential helper** 喂给 git | `~/.gitconfig`（`--global`）或仓库 `.git/config`（`--local`） |
| 谁要求 | git 传输层（推拉时才用） | Git 本身；GitHub 官方明确要**单独**设 |

GitHub 官方文档把这点说得很直白：**"The Git username is not the same as your GitHub username"**，改提交身份要用 `git config`（[Setting your username in Git](https://docs.github.com/en/get-started/git-basics/setting-your-username-in-git)）。所以 `gh` 登录只解决"能不能推上去"，从不碰"推上去的提交署谁的名"。

## `gh auth login` 那两个易混提示

初次 `gh auth login` 交互里会问两个都和"身份"沾边、但**都不是** `user.name/email` 的问题：

```
? What is your preferred protocol for Git operations on this host?  HTTPS / SSH
? Authenticate Git with your GitHub credentials?  Yes / No
```

- 第一个 = 选 git 走 HTTPS 还是 SSH（对应 flag `--git-protocol {https|ssh}`，见 [gh auth login](https://cli.github.com/manual/gh_auth_login)）。
- 第二个里的 **"credentials" 指传输用的 token / 凭据助手（credential helper），不是提交姓名邮箱**。选 `Yes` 只会往 git 配置里写一条 credential helper（`/usr/bin/gh` 部分随安装位置而异）：

```
credential.https://github.com.helper = !/usr/bin/gh auth git-credential
```

这条等价于事后单独跑 `gh auth setup-git`——官方对它的定义就是 *"configures `git` to use GitHub CLI as a credential helper"*（[gh auth setup-git](https://cli.github.com/manual/gh_auth_setup-git)；credential helper 概念见 [gitcredentials(7)](https://git-scm.com/docs/gitcredentials)）。**它只让 `git push` 能借用 gh 的 token，完全不设置 `user.name/email`。**

## `gh api user` 能查账户，但不会喂给 commit

登录后确实能查到账户信息：

```
gh api user --jq '{login, id, name, email}'
```

但两个坑：① `email` 常因隐私设置返回 `null`（GitHub 默认允许隐藏真实邮箱）；② **查到的结果不会自动流进 Git 的提交身份**——它只是 API 返回值，跟 `git config` 是两条互不相通的管道。想拿它当来源，也得你手动 `git config` 写进去。

## 结论 / 排障

- **不一定要 `--global`**：可以只在某仓库里 `git config user.name/user.email`（即 `--local`，写进该仓库 `.git/config`），**本地配置覆盖全局**。官方两种写法都给了（[username 文档](https://docs.github.com/en/get-started/git-basics/setting-your-username-in-git)）。
- **各层级都没设 → `gh` 不会补**：系统 / 全局 / 本地任何一层都没同时有 `user.name` 和 `user.email`，Git 提交时仍会 fatal：
  ```
  Author identity unknown
  *** Please tell me who you are.
  fatal: unable to auto-detect email address (got '<user>@<host>.(none)')
  ```
  `gh` 登录得再干净也不会替你填这两项。
- **重新 `gh auth`（login / refresh）只修失效 token**，不解决、也不重新生成提交身份。判据很简单：push 报 401/403 → 重新认证有用；报 `Author identity unknown` → 重新认证没用，得 `git config`。
- **推荐默认**：全局设一个姓名 + GitHub 的 **noreply 邮箱**（形如 `ID+username@users.noreply.github.com`），既能正常署名、又不泄露真实邮箱（[Setting your commit email address](https://docs.github.com/en/account-and-profile/how-tos/email-preferences/setting-your-commit-email-address)、[noreply 格式参考](https://docs.github.com/en/account-and-profile/reference/email-addresses-reference#your-noreply-email-address)）。保留一份"全局姓名 + noreply 邮箱"通常就是最省心的稳态。

## 相关

- 精准提交 / 暂存 / 丢弃 / amend（提交**内容**层面，不是身份）见 [surgery.md](surgery.md)。
- 跨设备 git 镜像见 [mirror.md](mirror.md)；自建 Forgejo / Gitea 的 SSH / token 认证见 [forge.md](forge.md)。
- 官方文档：[Setting your username in Git](https://docs.github.com/en/get-started/git-basics/setting-your-username-in-git)、[Setting your commit email address](https://docs.github.com/en/account-and-profile/how-tos/email-preferences/setting-your-commit-email-address)、[gh auth setup-git](https://cli.github.com/manual/gh_auth_setup-git)、[gh auth login](https://cli.github.com/manual/gh_auth_login)、[gitcredentials(7)](https://git-scm.com/docs/gitcredentials)。
