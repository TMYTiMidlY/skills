# git-pages —— 给 Git forge 补静态站托管（GitHub Pages 替代品）

> 一句话：Forgejo / Gitea 本身**没有**原生 Pages 功能，[git-pages](https://codeberg.org/git-pages/git-pages)（官网 [git-pages.org](https://git-pages.org/)，0BSD（0-clause BSD）许可，Go，作者 Catherine 'whitequark'）是一个**单独部署、配合 forge 使用**的服务：一次 HTTP 请求或 git push 就能发布静态站，内容存进它自己的存储（文件系统或 S3），**不挂靠可公开浏览的 git 分支**，所以能做"路径不可猜"的分享。Codeberg 官方的 `*.codeberg.page` 现在就是用它跑的。

**本文分两大部分**，按你的身份选：

- **[Part 1](#part-1--用-codeberg-官方-pages零运维最快上手)** —— 你只想**用 Codeberg 官方托管**：建仓库、怎么推、怎么访问、绑自定义域名。零运维。
- **[Part 2](#part-2--自建forgejogitea--自部署-git-pages)** —— 你**自建了 Forgejo/Gitea**，想给它配一套自己的 Pages：装 git-pages、反代（Caddyfile）、选一种推送/鉴权方案（deploy token / forge OAuth / 边缘 Bearer …）。

背景概念在最前面（3 分钟），鉴权源码剖析、HTTP API、参考源码位置在附录。

---

## 背景速览

### 从 Codeberg Pages 说起：它的后端 git-pages 你也能自建

**Codeberg Pages** 是非营利代码托管平台 [Codeberg](https://codeberg.org/) 给用户提供的静态站托管服务，相当于"Codeberg 版的 GitHub Pages"（Codeberg 跑的是 **Forgejo**——Gitea 的社区硬分叉，这段背景见本 skill 的 [git-server.md「同源与现状」](git-server.md#同源与现状)）。对本文来说最关键的一点是：**Codeberg Pages 的后端是开源的 `git-pages`，同一套服务你能照搬到自己的 Forgejo/Gitea 上自建**（就是 Part 2 要做的事）。要真正理解怎么部署、以及官方托管的一些行为差异，得先把常被混为一谈的三个名字分清：

- **Pages Server v2** —— 旧后端**代码库**（仓库 [`Codeberg/pages-server`](https://codeberg.org/Codeberg/pages-server)，EUPL-1.2）。2024-11 起进入维护模式，见置顶 issue [#399 "We will not accept new features!"](https://codeberg.org/Codeberg/pages-server/issues/399)；仓库首页写着 "This code is in maintenance mode… **Codeberg Pages itself is in the process of migrating to the new git-pages server**"。
- **git-pages** —— 新后端**代码库**，v2 的官方继任者。[官方文档](https://docs.codeberg.org/codeberg-pages/) 原文："Codeberg Pages **has recently migrated** from the legacy v2 codebase to the newer git-pages codebase"、"**Since December 2025**, Codeberg offers a new Pages service based on git-pages… It is free/libre open source software."
- **Codeberg Pages** —— Codeberg 面向用户的**服务品牌**（不是代码库）。今天它 = **git-pages（新迁移的站点）+ 老 v2（未迁移的存量站点）并存**，底层跑在 git-pages 上。迁移是**单向、要用户主动推一次才生效**的软切换（[迁移文档](https://docs.codeberg.org/codeberg-pages/migrating-from-pages-v2/)："your old v2 Pages deployment will continue working indefinitely"）。

一句话理顺三者关系：**代码库这条线是 Pages Server v2 → git-pages 的新旧更替**（git-pages 的"前身"就是 v2）；而 **Codeberg Pages 是 Codeberg 面向用户的服务品牌、不是任何一个代码库**——它自始至终是同一个服务，只是把底层后端从 v2 换成了 git-pages。所以今天的 codeberg.page = 跑在 git-pages 上的新站 + 尚未迁移的 v2 存量站并存。（Codeberg 未公布 codeberg.page 托管了多少仓库/站点，官方唯一量化数字是平台总量"[50,000+ 用户](https://blog.codeberg.org/the-hardest-scaling-issue.html)"，该博文发于 2023-01，如今应更多。）

**从 v2 迁到 git-pages 有几处 breaking change**，迁移前值得先知道（均据[迁移文档](https://docs.codeberg.org/codeberg-pages/migrating-from-pages-v2/)）：

- **内容不再自动拉取**。v2 会替你把仓库内容取过去发布；git-pages 改成推送模型——**每次更新后你必须主动"推一下"**（配一个 webhook，或用 Forgejo Actions）它才会更新（原文 "Content is no longer fetched automatically"）。
- **`raw.codeberg.page` 取消**。先一句话交代 **CORS（Cross-Origin Resource Sharing，跨源资源共享）**：浏览器默认按"同源策略"拦截跨源读取——跑在 `https://a.com` 页面里的 JS 用 `fetch()` 去读 `https://b.com` 的文件会被浏览器拦掉，除非 `b.com` 在**响应头**里加一句 `Access-Control-Allow-Origin` 明确放行（这个头只能由被读取的一方 `b.com` 来设、请求方设不了）。v2 为此单独提供一个 `raw.codeberg.page` 裸内容域名，凡经它取的响应**一律带上 `Access-Control-Allow-Origin: *`**（源码 [pages-server `handler.go`](https://codeberg.org/Codeberg/pages-server/src/branch/main/server/handler/handler.go)：请求 host 命中 `AllowedCorsDomains` 就写死 `*` + `Access-Control-Allow-Methods: GET, HEAD`，`raw.codeberg.page` 正是这个允许域）——等于"经这个域名取的东西，**任何**外部站点都能跨源读"，一个不分来源、全站无差别放开的开关。git-pages 取消了这个域名，**改由站点作者在自己站点根的 `_headers` 文件里、按路径自行声明要不要发 CORS 头、对哪个源开**（Netlify 风格 `_headers`，见附录 B）——从"一个裸域名对所有源无差别放开"收回成"作者自己精确控制哪条路径、放行哪个源"（原文 "CORS headers are now directly set on your page and this workaround is no longer necessary"）。
- **不能再用 `/仓库/@分支` 直接翻任意 repo/branch**。v2 允许 `用户名.codeberg.page/仓库/@分支/…` 直接访问任意仓库任意分支的文件——等于把整个 forge 当免费 CDN，是个常见滥用向量；git-pages 改为**只服务你显式部署过的那个站点**，`/仓库/@分支` 这种直接访问任意 repo/branch 的老方式随之弃用（原文 "Serving arbitrary resources from Codeberg was a common abuse vector"）。

迁移本身是**零停机、单向软切换**：老 v2 站点无限期继续可用（"your old v2 Pages deployment will continue working indefinitely"），一旦你改用任一新发布方式，该站从此改由 git-pages 服务（想确认切没切，看 HTTP 响应头 `Server`：`pages-server` 是老后端、`git-pages` 是新后端）。也正因为 v2 有这些设计缺陷（含上面那个被滥用的访问方式），**新站点如今一律建在 git-pages 上、v2 只维护存量**——存量用户不受影响。

### 免费与配额：Codeberg Pages 和 GitHub Pages 都免费，差别在配额透明度

真正的区别不在收费（都免费），而在**配额是否公开**、以及**私有站要不要钱**——不宜笼统说"谁限制更少"，因为 Codeberg 根本没公布数字，无从比大小（下表把能查到的角度都列上，未公开的直接标未公开）：

| 维度 | [GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages) | Codeberg Pages（git-pages）|
|---|---|---|
| 收费 | 免费 | 免费 |
| 私有仓库发布 Pages | 需 Pro/Team/Enterprise 付费计划 | 不分公开/私有、无付费分级 |
| 配额是否公开 | ✅ 明文：站点 1GB、带宽 100GB/月（软限）、构建 10 次/小时——[limits 文档](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits) | ❌ 未公布具体数字，只有"合理使用 / 反滥用"口径 |
| 自定义域名 + HTTPS | ✅ 免费、自动签证书 | ✅ 免费、自动签证书（DNS 记录授权，见 §1.4）|
| 站点公开性 | 公开，**即使仓库私有也公开**（[配置发布源文档](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)的 warning）| 公开；官方托管**无内建访问控制**（自建 git-pages 可加，见 Part 2）|
| 后端能否自托管 | ❌ 专有 | ✅ git-pages 开源（0BSD），可自建（Part 2）|
| 运营方 | GitHub / Microsoft（商业公司）| Codeberg e.V.（柏林注册非营利协会，纯捐款）|

### 发布模型：从分支拉取 vs 推到 Pages 存储

这是 git-pages 与 GitHub Pages 最本质、也最容易被搞混的一处差别，单独讲清楚。

**git-pages：推送式，且"发布"与"源码托管"是分开的两件事。** git-pages 把**发布**（deploy，把构建好的产物交出去）和**源码托管**（source control，git 仓库存源文件）拆成两件事：你把产物**主动推**给 git-pages（HTTP `PUT`/`PATCH`、webhook `POST`，或官方 CLI / Forgejo Action，见附录 B 的 HTTP API），它存进自己的私有存储（文件系统或 S3），**中间不经过任何可对外浏览的 git 仓库**。两个直接后果：

- **内容不会被自动拉取**：git-pages 不轮询你的仓库，每次更新都要主动"推一下"（webhook / Action）才生效（[迁移文档](https://docs.codeberg.org/codeberg-pages/migrating-from-pages-v2/) "Content is no longer fetched automatically"）。
- **路径可以做到"不可猜"**：私有存储没有"列目录 / 列所有站点"接口，路径不泄露就无从枚举——和"S3 桶不开 listing、只靠随机 key"是同一套逻辑。注意这**不是**签名 / 限时的 presigned URL：路径一旦泄露内容即公开，"降低被撞见的概率" ≠ 访问控制，真要保护敏感内容仍需鉴权。前提是别把同一份内容**也**挂在一个公开可浏览的 git 分支上，否则 forge 文件浏览器照样能翻到（这正是后面几个"从分支发布"的工具做不到不可猜路径的原因）。

**GitHub Pages：有两种"发布源"可切换（[配置发布源](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)）。** 在 Settings → Pages → Source 里二选一，可逆无感切换：

- **Deploy from a branch（从分支部署）**：选一个分支 + 目录（仓库根 `/` 或 `/docs`），推到该分支就自动发布；官方原话是"不需要控制构建过程"时推荐这种（会自动跑 Jekyll 构建）。内容**就是**一个 git 分支 → 属于"分支 / 拉取式"，和 Codeberg v2、下面两个 gitea-pages 同类。
- **GitHub Actions**：想自定义构建、或不想专门留一个放产物的分支时用；由 workflow 把产物打成 artifact 再 deploy，更接近 git-pages 的"推送式"（产物直接交给 Pages、不落在可浏览分支）。官方给了常见场景的 workflow 模板。

> 说明：上面这"两种发布源"只是**发布方式**层面的区分，不代表 GitHub 内部真有两套独立后端。另外，[配置发布源文档](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)（就是这一段引用的那篇 GitHub 官方文档）页面里有一个显式的 **Warning 提示框**，明确写着：**GitHub Pages 站点一旦发布就在公网公开可见，哪怕它的源码仓库是私有的**（原文 "GitHub Pages sites are publicly available on the internet, even if the repository for the site is private"）——所以别把敏感内容留在用来发布的那个仓库里。

**两种模型对照：**

| 维度 | git-pages（推送式）| GitHub Pages |
|---|---|---|
| 发布源 | 只有一种：`PUT`/`PATCH`/webhook/CLI/Action 主动推产物 | 两种可切：Deploy from a branch（分支源）/ GitHub Actions |
| 产物与源码的关系 | **分离**：产物进 Pages 私有存储，可不挂公开分支 | 分支源＝产物就是某分支；Actions＝产物打成 artifact、不落分支 |
| 是否自动发布 | 否，必须 webhook/Action 触发 | 分支源＝推到分支即自动发；Actions＝workflow 触发 |
| 构建在哪 | 你自己在 CI 里构建，git-pages 只收产物 | 分支源可自动跑 Jekyll；Actions＝你自定义构建 |
| "不可猜路径" | ✅ 私有存储、无 listing | ❌ 站点公开、URL 规则固定；私有仓库的站点仍公开可见 |
| 佐证 | [迁移文档](https://docs.codeberg.org/codeberg-pages/migrating-from-pages-v2/)、[README HTTP API](https://codeberg.org/git-pages/git-pages/src/branch/main/README.md)（`PUT`/`PATCH`/`POST`/`DELETE`）| [配置发布源文档](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site) |

### 同类工具横向对比（自建场景，共 4 个）

Codeberg 官方在用的是 **git-pages**（[docs.codeberg.org/codeberg-pages](https://docs.codeberg.org/codeberg-pages/) 明写 "served using a deployment of git-pages"）。另外三个是跟 Codeberg 无关、给**自建 Gitea/Forgejo** 用的第三方项目，能力跨度极大——从"4 个环境变量的极简静态托管"（deadnews）到"带 JS 动态路由 + 反代 + OAuth 的准应用服务器"（d7z）都有。下表把各家实测能力直接摊进来（✓/✗ 按当前 `main` 源码核验，非道听途说）：

| 维度 | [**git-pages**](https://codeberg.org/git-pages/git-pages) 🏆 | [d7z-project/gitea-pages](https://github.com/d7z-project/gitea-pages) | [deadnews/gitea-pages](https://github.com/deadnews/gitea-pages) | [MexHigh/Forge-Pages](https://github.com/MexHigh/Forge-Pages) |
|---|---|---|---|---|
| 许可 | 0BSD | Apache-2.0 | MIT | AGPL-3.0 |
| Star / 最新 release | 424★ · v0.9.1 | 17★ · v0.0.2 | 8★ · v1.0.1 | 2★ · 无 release（GitHub 是[MIRROR]）|
| 语言 / 依赖体量 | Go，独立后端 | Go，**重**（goja + goja_nodejs + websocket + lru + afero + gitea SDK）| Go，**极轻**（仅 gitea SDK 依赖，仅几百行核心代码，distroless 静态镜像）| Go，轻（oauth2 + scs + yaml）|
| 定位 | 通用、可横向扩展、官方生产级 | homelab 全功能"准应用服务器" | 极简静态托管 | 小众自托管，卖点是 OAuth2 私有页 |
| 内容怎么进来（发布模型）| **推**产物到 Pages 存储（`PUT`/`PATCH`/webhook/CLI/Action），不必挂公开分支 | 从 `gh-pages` **分支**经 Gitea API 读 | 从 `gh-pages` **分支**经 Gitea API 读 | **推** `POST /deploy`（tar.gz），不必挂公开分支 |
| 发布鉴权（**谁能推**站点，写侧）| DNS challenge / forge token / wildcard / `PAGES_INSECURE`（四选一，§2.4）| 靠 forge 本身的 repo 写权限（谁能推 `gh-pages` 分支谁就能发）| 靠 forge 本身的 repo 写权限（同左）| workflow token（如 `${{ forgejo.token }}`）校验对该 repo 的写权限 |
| 静态托管 | ✓ | ✓ | ✓ | ✓ |
| JS 动态路由 | ✗ | ✓ **Goja 引擎**（按路由挂 JS handler）| ✗ | ✗ |
| 反向代理 | ✗ | ✓ 按路由反代到上游 | ✗ | ✗ |
| WebSocket / SSE | ✗ | ✓ JS realtime（shared/version event，示例 `js_ws`/`js_sse`）| ✗ | ✗ |
| 自定义域名 | ✓（DNS 记录授权）| ✓（CNAME alias，写在 `.pages.yaml`）| ✗ | ✓（`<owner>` 子域名，需通配 DNS）|
| 私有页 / 访问控制（**谁能看**已发布站，读侧）| ✗ **无登录鉴权**：只有 `_headers` 里的 `Basic-Auth` 伪头，且 README/源码明说"**非安全特性**、明文存储、仅防搜索引擎收录"（`src/headers.go:241`）——真正的"别人看不看得到"靠下面那行"不可猜路径" | ✓ **Gitea OAuth 登录**：`.pages.yaml` 里 `private: true` 的站会要求登录，按当前用户对该 repo 的 read 权限放行 | ✗ 无：服务端 token 读得到的仓库，谁都能看 | ✓ **Forgejo/Gitea OAuth2**（`protect` 参数 / `.protect` 文件）：仅对该 repo 有 read/pull 权限者可见 |
| 缓存 | 产物即存储 | **TTL 缓存**（meta/blob/dir，默认约 1min，后端 memory/redis），自动刷新非重启 | **无缓存**，每请求实时读 Gitea API | 产物存本地 fs |
| 存储后端 | 文件系统 / **S3** | memory/local/etcd/badger/**S3**/overlay + redis（blob 缓存）| 无（实时读 Gitea）| 本地文件系统 |
| 路径可否不可猜（obscurity，**不是**访问控制）| ✅ 私有存储、无 listing | ❌ 内容在公开分支，forge 可翻 | ❌ 同左 | ◑ `additional_base_path` 可加随机段，且产物不挂公开分支 |
| 生命周期 | `Expires:` 头 + `DELETE` | 无站点 TTL | 无站点 TTL | `DELETE`（无 TTL）|
| 配置复杂度 | `config.toml` | `config.yaml` + 分支内 `.pages.yaml`（面大）| **4 个环境变量**（极简）| `config.yml` + 通配 DNS |

（star / license / release 核验于 2026-07-04：git-pages `GET codeberg.org/api/v1/repos/git-pages/git-pages` = 424★、许可见 [LICENSE.txt](https://codeberg.org/git-pages/git-pages/raw/branch/main/LICENSE.txt) + README 明写 `0-clause BSD`（**该 API 不返回 license 字段**）、release v0.9.1；`GET api.github.com/repos/d7z-project/gitea-pages` = 17★ Apache-2.0、release v0.0.2；`.../deadnews/gitea-pages` = 8★ MIT、release v1.0.1；`.../MexHigh/Forge-Pages` = 2★ AGPL-3.0、description 带 `[MIRROR]`、无 release，正身在作者自建 Forgejo [code.leon.wtf](https://code.leon.wtf/leon/Forge-Pages)。数字会随时间浮动。能力列据各仓库当前 `main` 的 README/config/源码核验。）

> **表里三行"鉴权/隐私"别混，它们管的是不同的事**（这也是本表最容易看拧的地方）：
> - **发布鉴权（写侧）** = "谁能把站点推上去"；
> - **访问控制（读侧）** = "谁能看已发布的站点"，这才是**私有页**；
> - **不可猜路径** = 一种**弱隐私**手段（security-through-obscurity，靠 URL 难猜），**不是**访问控制——路径一旦泄露内容即公开。
>
> 三者正交。关键结论：**git-pages 的写侧很强（DNS challenge / forge token…），但读侧没有真正的登录鉴权**——它对"别人能不能看"只给两样：不可猜路径，和 `_headers` 的 `Basic-Auth` 伪头（官方明说非安全、明文、仅防爬虫）。**要"登录才能看"的真·私有页，得用 d7z 或 Forge-Pages 的 forge OAuth**（deadnews 则完全没有）。所以上面"访问控制"和"不可猜路径"两行不矛盾：前者是真鉴权、后者是 obscurity，git-pages 只有后者。

各家一句话取舍：

- **deadnews/gitea-pages**——最省心的极简派：4 个环境变量（`GITEA_PAGES_SERVER/TOKEN/BRANCH/ADDR`）、单静态二进制 distroless 镜像、无缓存每次实时读 Gitea，适合"就是发点静态 HTML、推到 `gh-pages` 就行"。代价：**无鉴权**（服务端 token 能读到的仓库谁都能通过它访问，别直接裸暴露公网）、无自定义域名、无任何动态能力。（社区也有博客正因需求简单而选它、而非功能更全的 d7z。）
- **d7z-project/gitea-pages**——比名字看着强得多，其实是个**准应用服务器**：`.pages.yaml` 里按路由挂 Goja JS 处理器 / 反向代理 / 模板 / 重定向 / 屏蔽，另带 WebSocket、SSE、受限 `fetch`、按 repo 隔离的 KV 存储，私有页走 Gitea OAuth；存储/缓存后端可选 memory/local/etcd/badger/S3/overlay + redis。想要"静态站 + 少量动态 / 鉴权"时它最全。代价：配置面大、依赖重。
- **Forge-Pages**——四个里唯一和 git-pages 一样"推产物、不挂公开分支"的第三方项目（`POST /deploy` + tar.gz）；用 workflow token（如 `${{ forgejo.token }}`）校验对仓库的写权限，`additional_base_path` 给"一仓多版本 / PR 预览"各自独立路径（也是"`owner/repo/<随机>`"不可猜路径的官方实现），私有页走 OAuth2。URL 布局是 `https://<owner>.<base>/<repo>/*`，需要为子域名配通配 DNS。
- **共同前提（两个 gitea-pages）**：它们的内容都是一个 **git 分支**——只要仓库公开，forge 文件浏览器（`/owner/repo/src/branch/gh-pages/…`）就能绕过 Pages 层翻到，所以做不到 git-pages 那种"不可猜路径"（见上"发布模型"）。
  - 顺带澄清 `gh-pages` 这个名字：它只是二者**沿用了 GitHub Pages 的默认分支名**（`gh` = GitHub），纯粹是命名惯例、**与 GitHub 平台本身无关**——那个分支就躺在你自己的 Gitea/Forgejo 仓库里。而且**可配**：deadnews 用环境变量 `GITEA_PAGES_BRANCH`、d7z 用 `config.yaml` 的 `page.default_branch`，默认都是 `gh-pages`（Codeberg 官方 git-pages 则另用 `pages` 分支）。

---

# Part 1 · 用 Codeberg 官方 Pages（零运维，最快上手）

面向"直接用 codeberg.org 托管"的普通用户。三种发布方式，任选一种；官方入口文档 [docs.codeberg.org/codeberg-pages](https://docs.codeberg.org/codeberg-pages/)。

## 1.1 建仓库

在你自己账号（或组织）下建一个公开仓库；站点从名为 `pages` 的分支发布（也可设为默认分支）。特殊约定：

- 仓库叫 **`pages`** → 站点在 `https://<用户名>.codeberg.page/`（用户主站）。
- 仓库叫别的名 `myrepo` → 站点在 `https://<用户名>.codeberg.page/myrepo/`（项目站）。

## 1.2 三种发布方式

### (a) 手动推 `pages` 分支 + webhook（最朴素，适合手写 HTML）

把静态文件推到 `pages` 分支，再配一个 webhook 通知 git-pages 来取（[官方步骤](https://docs.codeberg.org/codeberg-pages/)）：

1. 仓库 **Settings → Webhooks → Add webhook → Forgejo** 类型。
2. **Target URL** 填站点地址：`https://<用户名>.codeberg.page/`（用户站）或 `https://<用户名>.codeberg.page/<仓库名>/`（项目站）。
3. **Branch filter** 填 `pages`。
4. 保存。以后每次推 `pages` 分支就自动发布。

> 为什么要 webhook：git-pages 是 push 模型，**不会自动轮询你的仓库**（[迁移文档](https://docs.codeberg.org/codeberg-pages/migrating-from-pages-v2/) "Content is no longer fetched automatically"）——webhook 就是那个"推一下"的触发器。

### (b) Forgejo Actions + 官方 Action（推荐，适合静态站生成器）

如果你用 Hugo/MkDocs/Jekyll 等生成器，用官方 [git-pages/action](https://codeberg.org/git-pages/action) 最省事。在 `.forgejo/workflows/publish.yaml` 里，构建完加一步（[官方示例](https://docs.codeberg.org/codeberg-pages/forgejo-actions/)）：

```yaml
- uses: https://codeberg.org/git-pages/action@v2
  with:
    site: 'https://${{ forge.repository_owner }}.codeberg.page/repository-name/'
    token: ${{ forge.token }}     # Forgejo Actions 自动注入，git-pages 自动认
    source: _site/                # 生成器产物目录
  # 只在 main 分支发布，避免草稿/功能分支被发出去：
  if: ${{ forge.ref == 'refs/heads/main' }}
```

`site` 里的 `repository-name` 换成你的仓库名；仓库也叫 `pages` 时可省略、直接发 `https://用户名.codeberg.page/`。`token` 是 Forgejo Actions 的 [automatic token](https://forgejo.org/docs/next/user/actions/basic-concepts/#automatic-token)，git-pages 自动识别为"该 workflow 有权发这个站"，**无需你手动建密钥**。

### (c) git-pages-cli 手推（本地/脚本一次性发）

官方 CLI [git-pages-cli](https://codeberg.org/git-pages/git-pages-cli)（`go install codeberg.org/git-pages/git-pages-cli@latest` 或下 release 二进制）可以从本地目录直接发。发到 codeberg.page 的 `<用户名>/<repo>` 站点需要一个 forge access token（见 §2.4 方案 B 的建 token 步骤）：

```bash
git-pages-cli https://用户名.codeberg.page/repo/ --token <forge-token> --upload-dir ./_site
```

## 1.3 访问：URL 规则

发布后的访问地址（[codeberg.page 首页](https://codeberg.page/)）：

```
https://<用户名>.codeberg.page[/<仓库名>][/@<分支>]
```

- `https://alice.codeberg.page/` —— 用户主站（仓库 `pages`）。
- `https://alice.codeberg.page/myrepo/` —— 项目站。
- ~~用 `@` 指定分支：`https://alice.codeberg.page/@develop/README.md`~~ —— **这是旧 v2 行为，git-pages 已弃用**：[迁移文档](https://docs.codeberg.org/codeberg-pages/migrating-from-pages-v2/)明确 "Direct access to repos and branches is no longer possible… `/repository/@branch`"。（不过 codeberg.page 首页 URL 模板至今仍印着 `[/@BRANCH]`，Codeberg 自己的文档没对齐——别依赖它。）
- 用户名/仓库名带点号（`.`）会撞 Let's Encrypt 通配证书，改用 `https://pages.codeberg.org/user.name/`（[troubleshooting](https://docs.codeberg.org/codeberg-pages/troubleshooting/)）。

## 1.4 自定义域名（绑自己买的域名）

不想用 `*.codeberg.page` 就绑自己的域名。**新版 git-pages 用 DNS 记录本身做授权，`.domains` 文件已不再需要**（[自定义域名文档](https://docs.codeberg.org/codeberg-pages/using-custom-domain/)）。加一条指向 Codeberg 的记录（三选一）：

| 场景 | 记录类型 | 值 |
|---|---|---|
| 子域名（推荐） | `CNAME` | `codeberg.page.` |
| 裸域名 / 已有其他记录 | `ALIAS`（或 Cloudflare 的 flattened CNAME） | `codeberg.page.` |
| 都不支持时 | `A` + `AAAA` | `217.197.84.141` / `2a0a:4580:103f:c0de::2` |

坑：① 有 [CAA 记录](https://letsencrypt.org/docs/caa/) 的必须显式放行 Let's Encrypt，否则签证书失败；② 你的域名开了 DNSSEC 而 `codeberg.page` 没签，得改用 A/AAAA。均见[自定义域名文档](https://docs.codeberg.org/codeberg-pages/using-custom-domain/)。

**别忘了第二步——授权 TXT**（[自定义域名文档](https://docs.codeberg.org/codeberg-pages/using-custom-domain/) "Step 2: Configure Git-pages authorization"）：上面的 CNAME/A 只把流量导到 Codeberg，**还要再加一条 TXT 证明"这个仓库有权发布到这个域名"**，否则部署被拒。按发布方式二选一（值都填仓库的 HTTPS clone URL；每个要用的子域名如 `www` 各加一条）：

- 手推 `pages` 分支 / webhook：`_git-pages-repository.yourdomain.com.  TXT  "https://codeberg.org/<用户名>/<仓库>.git"`（**不需 token**）。
- Forgejo Actions：`_git-pages-forge-allowlist.yourdomain.com.  TXT  "https://codeberg.org/<用户名>/<仓库>.git"`。

## 1.5 404 页与重定向

站点根放这些文件即可自定义行为（[高级用法文档](https://docs.codeberg.org/codeberg-pages/advanced-usage/)）：

- **`404.html`** —— 自定义 404 页。
- **`_redirects`** —— 每行 `from  to  [status]`（`#` 注释）。status：`200`=不改 URL 取另一路径内容（SPA 回退）、`301`=永久跳、`302`=临时跳。例：

  ```
  /example        https://example.com/   301   # 单条跳转
  /*              /index.html            200   # SPA：所有路径回退到 index
  /articles/*     /posts/:splat          302   # 带 :splat 保留通配部分
  ```

---

# Part 2 · 自建：Forgejo/Gitea + 自部署 git-pages

面向"自己有 Forgejo/Gitea，想配一套自己域名的 Pages"的管理员。

**先分清两个角色**：**你（管理员）** 把 git-pages 当一个新增服务部署一次（2.1–2.3），这台 forge 才"有了 Pages 能力"；之后**仓库用户**用哪种方式推，取决于你在 2.4 选的鉴权方案——用户侧体验和 Codeberg 用户一样（Part 1）。

## 2.1 装 git-pages（不止 Docker）

[官方 CI](https://codeberg.org/git-pages/git-pages/src/branch/main/.forgejo/workflows/ci.yaml) 产出 **4 个平台预编译二进制**（Go 静态编译、零依赖），发布在 [Codeberg Releases](https://codeberg.org/git-pages/git-pages/releases)（`GET .../releases/latest` 核验：最新 v0.9.1，linux-amd64 约 30MB）：

```
git-pages.linux-amd64 / git-pages.linux-arm64 / git-pages.darwin-arm64 / git-pages.windows-amd64.exe
```

安装选项：**① 二进制直下**（最轻，适合资源紧的机器）→ 丢进 `/usr/local/bin/`；**② Docker** `codeberg.org/git-pages/git-pages:latest`；**③ Nix** 仓库根有 `flake.nix`（`nix run`）；**④ 源码** `go install codeberg.org/git-pages/git-pages@latest`（需 Go ≥ 1.25，见 `go.mod`）。

**关键：standalone vs supervisord**——看 [Dockerfile](https://codeberg.org/git-pages/git-pages/src/branch/main/Dockerfile) 结尾：

```dockerfile
CMD ["git-pages"]        # 默认 standalone：只跑 git-pages，纯 HTTP :3000，不带 TLS
# CMD ["supervisord"]    # 可选：supervisord 同时拉起 git-pages + 打包的 Caddy(ACME)
```

**只要你前面已经有 Caddy/nginx 做边缘 TLS，就用默认的 standalone**——让边缘反代把域名转到 git-pages 的 `:3000`，别让它自带的 Caddy 再抢 80/443（`conf/supervisord.conf` + `conf/Caddyfile` 那套 on_demand_tls + certmagic-s3 只在没有别的反代时才用）。

## 2.2 config.toml + S3 后端

启动参数（`src/main.go`）：`-config`（默认 `config.toml`）、`-secrets`（默认 `$CREDENTIALS_DIRECTORY/secrets.toml`——**原生适配 systemd `LoadCredential`**，密钥只挂给这个服务的私有运行时目录，不落持久化明文）、`-no-config`（全用环境变量）。

> ⚠️ git-pages **不自带 systemd unit**（仓库里只有 Dockerfile + supervisord，没有 `.service`），自建要**自己写一个**——按**系统 service** 装（`/etc/systemd/system/git-pages.service`、`WantedBy=multi-user.target`、固定 `User=` 跑），不是 user service。写 unit 时注意：`LoadCredential=` 需要 **systemd ≥ 247**（`$CREDENTIALS_DIRECTORY` 才由它注入）。老发行版（如 systemd 239 的 RHEL8 / Anolis / Alibaba Cloud Linux 3 系）会**静默忽略** `LoadCredential`——`$CREDENTIALS_DIRECTORY` 为空、`-secrets` 落到默认路径读不到密钥 → S3 后端 `Access Denied` 起不来。回退：unit 用**固定** `User=<svc>`（别用 `DynamicUser`），`secrets.toml` 属主设成该用户、权限 `0600`，`ExecStart` 里**显式** `-secrets /etc/git-pages/secrets.toml`，绕开 LoadCredential。

> release 二进制常**落后 `main`**：照 `main` 的 `config.example.toml` 写的键（本文示例含少量 `main` 才有的项）在旧 release 上会被拒为 `unknown keys`。落盘前先跑一遍 `git-pages -config <file> -print-config` 验证——能解析就打印 effective 配置，非法键会被逐条点名。

关键段（**改自** [`conf/config.example.toml`](https://codeberg.org/git-pages/git-pages/src/branch/main/conf/config.example.toml)，此处示意 S3 后端；注意 example 里 `[storage]` 默认是 `type = 'fs'`、S3 为 non-default 段）：

```toml
[server]
pages   = 'tcp/localhost:3000'   # 站点服务口（反代打这里）
caddy   = 'tcp/localhost:3001'   # on-demand-tls 询问口；不用自带 Caddy 时设 "-" 关掉
metrics = 'tcp/localhost:3002'

[storage]
type = 's3'                      # 或 'fs'（[storage.fs] root='./data'）

[storage.s3]                     # 接任意 S3 兼容存储（RustFS/MinIO/Garage…）
endpoint          = '<host:port>'
access-key-id     = '...'        # 建议改放 secrets.toml，别写这里
secret-access-key = '...'
bucket            = 'git-pages'
region            = 'us-east-1'
insecure          = true         # 自建 endpoint 走明文 HTTP（RustFS/MinIO 本地口）必须开；
                                 # 默认按 https 连，连 http 端口会静默报 Access Denied（backend_s3.go: Secure = !insecure）

[limits]
max-site-size    = '128M'
allow-expiration = false         # 想用 Expires: 头做过期，打开这个
allow-basic-auth = false
```

`secrets.toml`（chmod 600，只放密钥；systemd `LoadCredential` 会挂进来）：

```toml
[storage.s3]
access-key-id     = 'AKxxxx'
secret-access-key = 'xxxxxx'
```

## 2.3 边缘反代：Caddyfile 模板

git-pages 跑 standalone、监听 `:3000`（`config.default.toml` 绑 `tcp/localhost:3000` 仅本机；官方 Docker 镜像的 `config.docker.toml` 绑 `tcp/:3000` = 容器内所有接口，靠不发布端口来隔离），由你现有的 Caddy 顶在前面做 TLS + 反代。两种写法：

**(a) 单个固定域名 + 真证书（有公网 DNS 指过来）**：

```caddyfile
pages.example.com {
    reverse_proxy 127.0.0.1:3000
}
```

**(b) 通配 / on-demand（一个 Caddy 服务多个 pages 子域名）**——git-pages 自己也提供 on-demand 询问口，让 Caddy 只给"已发布的站"签证书：

```caddyfile
{
    on_demand_tls {
        permission http http://127.0.0.1:3001   # git-pages 的 caddy 口，问它该不该签
    }
}

*.pages.example.com {
    tls { on_demand }
    reverse_proxy 127.0.0.1:3000
}
```

> 通配块**按 Host/SNI 路由**、与别的站共用 Caddy 的 `:443`（不占独立端口，靠 Host 分流）；**不写 `authorize with`**——pages 本就是公开静态站、不设登录墙。`permission` 那支把"该不该为这个域名签证书"外包给 git-pages 的 caddy 口（`[server].caddy`，默认 `:3001`），只对**它确实在服务的站**答应，天然挡住"野域名来握手就触发签证书"。

> 注意首次 HTTPS 发布的鸡生蛋问题：git-pages **在站点发布前无法为该域名申请证书**（[git-pages-cli 文档](https://codeberg.org/git-pages/git-pages-cli)）。首发要么走明文 HTTP，要么用 CLI 的 `--server <已有证书的域名>` 指一个 git-pages 已经有证书的 host 中转。

### 2.3.1 要改哪些 DNS 记录（自建速查）

`<域名>` = 你的站点根域（如 `example.com`）、`<edge>` = 边缘反代服务器的公网 IP、`<host>` = 完整站点域名（如 `alice.pages.<域名>` 或自定义域名本身）。按你选的模式加：

| 场景 | 要加的记录 | 说明 |
|---|---|---|
| **通配多租户**（方案 C，最常用） | `*.pages.<域名>`　A/AAAA → `<edge>`（或 CNAME 到边缘主机名） | 让任意 `<user>.pages.<域名>` 都解析到边缘；**forge-wildcard 鉴权不需要任何 TXT** |
| **单域名固定站** | `pages.<域名>`　A/AAAA/CNAME → `<edge>` | 一个站一条即可 |
| **DNS Challenge（方案 A）** | 上面那条 + `_git-pages-challenge.<host>`　TXT = CLI `--challenge` 算出的哈希 | 口令可多条 TXT |
| **Forge Allowlist（方案 B）/ 免 token Repository Allowlist（rule 3）** | 上面那条 + `_git-pages-forge-allowlist.<host>` 或 `_git-pages-repository.<host>`　TXT = 仓库 clone URL（可多条） | 只授权根 / `.index` 站 |
| **自定义域名接到某租户** | `<自定义域名>` CNAME → 边缘 + 上面对应的授权 TXT | Part 1.4 是 Codeberg 托管版，自建同理 |

> 为什么方案 C 只要一条通配记录、不要 TXT：它的鉴权靠请求带的 forge token 现问 forge API（见下 2.4 方案 C），DNS 只负责"把域名解析到边缘"。**只有 DNS Challenge / Allowlist 那几种**才另加 `_git-pages-*` TXT。有 DNS 服务商 API（如 Spaceship）时，通配记录 + 这些 TXT 都能脚本化下发——**前提是那把 API key 对`<域名>`本身有 DNS 写权限**（key 若只授权了别的域名，改这个域名会 404 `SOA ... not found`）。

## 2.4 选一种"谁能推"的鉴权方案

**归档直传 / 删除**类请求（tar/zip 的 PUT/PATCH、DELETE）的鉴权入口是 `authorizeDNSChallengeOrForgeWithToken`（[`src/auth.go`](https://codeberg.org/git-pages/git-pages/src/branch/main/src/auth.go)），**按顺序**尝试 `PAGES_INSECURE → DNS Challenge → Forge Wildcard → Forge DNS Allowlist`，第一个通过即放行。挑一种即可：

> 注意：**推 git 仓库 / webhook**（PUT body 为仓库 URL、POST webhook）走的是另一个函数 `AuthorizeUpdateFromRepository`，多一种**免 token、免 forge API** 的方式——在 `_git-pages-repository.<域名>` TXT 里列出允许的 clone URL 即可（[README Authorization 第 3 条](https://codeberg.org/git-pages/git-pages/src/branch/main/README.md)，见附录 A ⑥）。想"webhook 推 `pages` 分支就发布"、又不想建任何密钥的自建场景，这条最省事。下面的方案表对照的是归档直传路径。

| 方案 | 密钥类型 | 要不要 DNS | 要不要 forge API | 适合 |
|---|---|---|---|---|
| **A. DNS Challenge** | 自签口令（你随便定） | 1 条 TXT | 否 | 单站、脚本发、最简单 |
| **B. Forge Token + DNS Allowlist** | forge access token | 1 条 TXT | 是 | 想复用 forge 账号权限、能按账号撤销（"deploy token"） |
| **C. Forge Wildcard** | forge token（含 CI 自动 token） | 通配解析 | 是 | 一个域名后缀、无数用户各发各站（多租户） |
| **D. 边缘 Bearer + `PAGES_INSECURE`** | 你在 Caddy 里定的 Bearer | 否 | 否 | 不想碰 DNS，安全全押在反代上 |

### 方案 A · DNS Challenge（自签口令，最简单）

本质是"把一个 Bearer 口令的合法性证明放进 DNS"。手动算比较烦，**用官方 CLI 一条命令生成口令 + 现成 TXT 记录**（[git-pages-cli](https://codeberg.org/git-pages/git-pages-cli)）：

```bash
git-pages-cli https://pages.example.com --challenge
# 输出：password: 28a616f4-...（口令，自己收好）
#       _git-pages-challenge.pages.example.com. 3600 IN TXT "a59ecb..."（把这条加到 DNS）
```

把那条 TXT 加到 DNS 后，以后发布带上口令即可：

```bash
git-pages-cli https://pages.example.com --password <口令> --upload-dir ./_site
# 或裸 curl：
curl https://pages.example.com/ -X PUT --data-binary @site.tar.gz \
  -H 'Content-Type: application/x-tar+gzip' -H 'Authorization: Pages <口令>'
```

**口令可以设多个**：`net.LookupTXT` 返回该名下**所有** TXT，命中任意一条即通过（`authorizeDNSChallenge`，见附录 A ②）——同名挂多条 TXT = 多个口令，适合轮换或多发布者。口令别名 `--password-file` / `GIT_PAGES_PASSWORD` 环境变量，避免进 argv。

> 与 Let's Encrypt 的 DNS-01 challenge **不是一回事**：LE 是实时一次性验证域名控制权；这里是永久 TXT，每次发布现查现比。

### 方案 B · Forge Access Token + DNS Allowlist（复用 forge 账号权限，即"deploy token"）

不自己造口令，而是**用 forge 的 access token 当发布凭据**，git-pages 去问 forge"这 token 对这仓库有没有 push 权限"。

1. 在 Forgejo 建 token（[git-pages-cli 文档](https://codeberg.org/git-pages/git-pages-cli)）：**Settings → Applications → Access tokens**，权限勾 **user: Read** + **repository: Read and write**，生成，复制那串十六进制。
2. DNS 加一条 allowlist 记录，把域名和仓库绑定：
   ```
   _git-pages-forge-allowlist.pages.example.com.  TXT  "https://git.example.com/user/repo.git"
   ```
   （可加多条 TXT 绑多个仓库。）
3. 发布带 token：
   ```bash
   git-pages-cli https://pages.example.com --token <forge-token> --upload-dir ./_site
   # CI 里更常用 forge 的自动 token：见方案 C / 官方 action
   ```

**好处**：复用 forge 账号体系，撤销某人权限只需在 forge 改，不用换口令。**代价**：多一个"必须活着的 forge API"运行时依赖；源码 `if projectName != ".index"` 写死——**只能授权根/索引站点，不能给子项目单独授权**（`authorizeForgeDNSAllowlist`，见附录 A ④）。token 别名 `GIT_PAGES_TOKEN` 环境变量。

### 方案 C · Forge Wildcard（多租户：一个域名后缀，无数用户各发各站）

这就是 Codeberg 给每个用户发 `<用户名>.codeberg.page` 的机制，要在 `config.toml` 配 `[[wildcard]]` 段（[`conf/config.example.toml`](https://codeberg.org/git-pages/git-pages/src/branch/main/conf/config.example.toml)）：

```toml
[[wildcard]]
domain        = "pages.example.com"
clone-url     = "https://git.example.com/<user>/<project>.git"
index-repo    = "pages"
authorization = "forgejo"
```

请求进来时 git-pages 按 **host 子域名标签 = 用户名** + **路径首段 = 项目名** 套 `clone-url` 模板**现算**仓库：**根路径 `/`**（用户主站）→ 项目名取 `.index` → 用 `index-repo`（如 `pages`）→ 仓库 `<user>/pages`；**`/<项目>/`**（项目站）→ 仓库 `<user>/<项目>`；分支取 `index-repo-branch`（项目站默认 `pages`）。例：`alice.pages.example.com/` → `alice/pages`，`alice.pages.example.com/proj/` → `alice/proj`。算出仓库后再拿请求带的 forge token 核权限（`authorizeForgeWildcard` + `src/wildcard.go`，见附录 A ③）。CI 里用官方 [git-pages/action](https://codeberg.org/git-pages/action) 时，Forgejo Actions 的自动 token 就够（无需手建 token），还支持 PR 预览站（`<用户>.preview.pages.example.com/site@<PR号>/`）。单站场景**别用它**——它要求"后缀前恰好多一段子域名"，固定单域名套不上。

> **多 forge 并存 + 排序坑（实测 v0.9.1，与 gitea/github 各自联动均已跑通）**：可以配多个 `[[wildcard]]` 段，让不同 forge 各自多租户（如 forgejo 用 `pages.example.com`、gitea 用 `gitea.pages.example.com`）。但**若一个 domain 是另一个的后缀，务必把更长/更具体的排在前面**——否则短后缀那段会先匹配到长后缀租户的 host：实测 v0.9.1 把"host 去掉 domain 后缀"的**整段前缀**当 user（如 `alice.gitea.pages.example.com` 落到 `pages.example.com` 段时被当成 user=`alice.gitea`），clone-url 算错、鉴权失败。
>
> **GitHub 做多租户**要单独说：GitHub 不认 gogs 兼容 API（`authorization` 不能设成任何 forge），只能走 **rule 4（Wildcard Match content，见附录 D）**——`[[wildcard]]` 的 `authorization` **留空**，然后 `POST` 一个 GitHub push webhook（body 含 `repository.clone_url` + `ref`，头 `X-GitHub-Event: push`、`Content-Type: application/json`），git-pages 按模板匹配 clone-url（**免 token、免 forge API**）后现克隆该**公开** repo 的对应分支。实测 git-pages 能从公网直接 clone GitHub 公开库并发布。

### 方案 D · 边缘 Bearer + `PAGES_INSECURE`（不碰 DNS，安全押在反代上）

`PAGES_INSECURE=1` 让 git-pages **无条件放行**所有到达它的请求（[README](https://codeberg.org/git-pages/git-pages/src/branch/main/README.md)，`authorizeInsecure`）。配合 git-pages 只监听 `127.0.0.1` + Caddy 只对带正确 `Authorization: Bearer <token>` 的写请求放行，就成了"Caddy 是唯一关卡"：

```caddyfile
pages.example.com {
    @write method PUT PATCH POST DELETE
    @noauth not header Authorization "Bearer <你的token>"
    handle @write {
        handle @noauth { respond 403 }
    }
    reverse_proxy 127.0.0.1:3000
}
```

**代价**：安全**单点**押在"Caddy 配置写对 + git-pages 永不暴露公网"上——Caddy 一旦漏配或 git-pages 意外监听公网，`PAGES_INSECURE` 谁来都放行，没有第二道防线。方案 A/B 则即使 Caddy 出错，git-pages 自己那道 DNS 校验仍独立生效。**生产慎用，仅在你完全掌控反代时用**。

## 2.5 怎么推（三种客户端）

- **裸 curl**：`curl https://pages.example.com/ -X PUT --data-binary @site.tar.gz -H 'Content-Type: application/x-tar+gzip' -H 'Authorization: Pages <口令>'`（方案 A）。body 也可是 `application/zip`。
- **git-pages-cli**：`--upload-dir <目录>` / `--upload-git <仓库URL>` / `--delete` / `--dry-run`（只验权不落盘）/ `--expires 14`（临时站，需服务端开 `allow-expiration`）。
- **Forgejo Action** `git-pages/action@v2`：CI 里最省事，`with: { site, token: ${{ forge.token }}, source }`（[action 文档](https://codeberg.org/git-pages/action)）。

## 2.6 生命周期

- **过期**：发布带 `Expires: <HTTP-date>` 头（或 CLI `--expires <天>`），需 `config.toml` 开 `allow-expiration`；过期站由定时任务 `git-pages -site-expire` 清（[README](https://codeberg.org/git-pages/git-pages/src/branch/main/README.md)）。
- **下线**：`DELETE`（或 CLI `--delete`，或 PUT 空 body）——站点变得不可访问，数据保留一段不确定时间后彻底清除。
- **管理员直删（不走 HTTP 鉴权，本机跑）**：`git-pages -config … -secrets … -delete-site <ref>`（`ref` 形如 `域名` 或 `域名/.index`）。⚠️ `-delete-site` 是 `main` 里较新加的，**release 二进制可能没有**（实测 v0.9.1 即无，`-help` 也不列它——又一个"release 落后 main"的例子）。这种情况改用 `git-pages … -update-site <ref> <空.tar>` 代替：**空 tar 归档 = 删除**（日志出 `ok: deleted`）。注意那个空文件要带 `.tar` 后缀（git-pages 靠扩展名判 content-type，喂 `/dev/null` 会报 "cannot determine content type")。适合"没 `-delete-site` 又不方便走 HTTP DELETE"（HTTP 下线要过 `AuthorizeDeletion` 鉴权，一个没有 forge-token / DNS-challenge 的裸租户站未必删得掉）的场景。

---

# 附录 A · 鉴权机制源码剖析（`src/auth.go`）

[`src/auth.go`](https://codeberg.org/git-pages/git-pages/src/branch/main/src/auth.go) 里发布鉴权分两条代码路径：**归档直传 / 删除**走 `AuthorizeUpdateFromArchive` / `AuthorizeDeletion` → `authorizeDNSChallengeOrForgeWithToken`（下面 ①–④ 按序尝试）；**推仓库 URL / webhook** 走 `AuthorizeUpdateFromRepository`（另一组机制，见 ⑥）。README 的 Authorization 段对内容更新其实列了 8 条规则，本附录①–④只覆盖归档路径那几条。上面 2.4 是"怎么用"，这里是"源码怎么判"。

### ① Development Mode（`PAGES_INSECURE=1`）
`authorizeInsecure`：环境变量置真则无条件放行（[README 第 1 条](https://codeberg.org/git-pages/git-pages/src/branch/main/README.md)）。对应 方案 D。

### ② DNS Challenge（推荐，单站首选）
`authorizeDNSChallenge`：
```go
challengeHostname := fmt.Sprintf("_git-pages-challenge.%s", host)
actualChallenges, _ := net.LookupTXT(challengeHostname)          // 该名下全部 TXT
expectedChallenge := sha256(host + " " + param)                  // param = 你传的口令
if !slices.Contains(actualChallenges, expectedChallenge) { 拒绝 } // 命中任意一条即可
```
支持 `Authorization: Pages <口令>` 或 `Authorization: Basic base64("Pages:<口令>")`（非 Forgejo forge 用）。多 TXT = 多口令。对应 方案 A。

### ③ Forge Wildcard（依赖 `[[wildcard]]` 配置段）
`[[wildcard]]` 是 TOML 的**数组表**（可多段）。`authorizeForgeWildcard` + `src/wildcard.go` 的 `Matches`（要求"后缀前恰好多一段"，多出的当用户名）/ `ApplyTemplate`（套 clone-url 现算仓库）→ 拿 `Forge-Authorization` token 问 forge API 权限。**每次请求现算归属，不预登记**。对应 方案 C。

### ④ Forge DNS Allowlist（不需要 `[[wildcard]]`）
`authorizeForgeDNSAllowlist` → `authorizeDNSAllowlist`：查 `_git-pages-forge-allowlist.<域名>` 的 TXT，**每条值 = 仓库 clone URL**（逐条 `url.Parse`，只收绝对 URL；可多条）。再 `authorizeGogsUser` 拿 token 问 forge：先 `FetchGogsAuthorizedUser` 查 token 是谁、是 owner 直接放行，否则 `CheckGogsRepositoryPushPermission` 查协作者权限（函数名 "Gogs" 是历史遗留，Gitea/Forgejo/Gogs API 兼容）。`if projectName != ".index"` 写死——只授权根站点。对应 方案 B。

### ⑤ 元数据检索
`AuthorizeMetadataRetrieval`：保护"能枚举站点内容"的接口（`/.git-pages/manifest.json`、`manifest.pb` 等）。除 DNS challenge 外，wildcard 站点在**没设 Basic-Auth 时**也可能经 `authorizeWildcardMatchHost` 放行 metadata——即这类站点的目录清单未必私密。

### ⑥ 推仓库 URL / webhook 路径（`AuthorizeUpdateFromRepository`）
与归档路径不同：先 `authorizeDNSAllowlist(r, "git-pages-repository")` 查 `_git-pages-repository.<域名>` 的 TXT（每条 = 允许的 clone URL，**不需要 token、不问 forge API**，是自建 webhook 场景最省事的一种）；再 `authorizeWildcardMatchSite`（webhook 通配匹配）。这条路径对应 README Authorization 段里归档路径没覆盖的规则。

---

# 附录 B · HTTP API 速查（[README](https://codeberg.org/git-pages/git-pages/src/branch/main/README.md)）

| 方法 | 作用 |
|---|---|
| `GET`/`HEAD` | 按 host + 可选 project name 选站返回文件；`/.git-pages/health`、`/.git-pages/manifest.json`、`/.git-pages/manifest.pb`（稳定二进制清单）、`/.git-pages/archive.tar` 为保留接口 |
| `PUT` | 全量发布：body 为仓库 URL（浅克隆）或 tar/tar+gzip/tar+zstd/zip 归档；空 body = `DELETE` |
| `PATCH` | 增量合并：tar 归档 merge；char device(0,0)=whiteout 删除标记；`Atomic: yes/no`；输掉竞态返回 `409` 重试 |
| `POST` | body 为 Forgejo/Gitea/Gogs/GitHub webhook payload；仅 `refs/heads/pages` 生效 |
| `DELETE` | 下线站点 |

特殊头/文件：`Expires: <HTTP-date>`（配 `allow-expiration`）、`Dry-Run: yes`（只验权不落盘）；站点根 Netlify 风 `_redirects` / `_headers`（`_headers` 里 `Basic-Auth:` 伪头**明文存储、非安全特性**，仅防搜索引擎）。所有更新原子生效。两个"不支持"原因不同：**SHA-256 Git 哈希**是暂时受 [go-git 限制](https://github.com/go-git/go-git/issues/706)（将来会自动获得）；**Git LFS** 是**有意不支持**（单厂商规格、无稳定 Go API、有反射型 HTTP DoS 滥用风险）。

---

# 附录 C · 参考源码位置

把仓库克隆到本地读源码（`git clone --depth 1 https://codeberg.org/git-pages/git-pages.git`）。关键文件：`src/auth.go`（内容更新鉴权 8 条规则，见附录 D）、`src/pages.go`（`putPage`/`patchPage`/`postPage`/`deletePage` 的 HTTP 通道分发）、`src/wildcard.go`（通配匹配）、`src/main.go`（启动参数）、`Dockerfile`（standalone vs supervisord）、`conf/config.example.toml`（含 Codeberg 自己的 wildcard 配置）、`.forgejo/workflows/ci.yaml`（4 平台 release）。相关仓库：[git-pages](https://codeberg.org/git-pages/git-pages) / [git-pages-cli](https://codeberg.org/git-pages/git-pages-cli) / [action](https://codeberg.org/git-pages/action)。

---

# 附录 D · 与 git forge 配合机制总表（ingest × 鉴权）

把"内容怎么进来"和"凭什么放行"两个正交轴各列一张表，是 §2.4 / §2.5 与附录 A/B 的**交叉汇总**——补上前面分散各处、以及"哪条机制配哪个 forge（尤其 GitHub）"这个没单独点名的维度。判断依据来自 `src/auth.go` / `src/pages.go` 与 [README Authorization 段](https://codeberg.org/git-pages/git-pages/src/branch/main/README.md)（内容更新的鉴权在 README 里正好是 **8 条按序尝试的规则**）。

## D.1 内容进来：5 个 HTTP wire 通道

git-pages 的"入口"按 **HTTP 方法 + body 类型**分（`ServePages` 的方法分发，`src/pages.go`）。`git-pages-cli` 和官方 Action 都**不是独立通道**，而是**驱动这些通道的客户端**（Action 本身是 cli 的 wrapper）。

| HTTP 通道 | body | 干什么 | 谁驱动 | 鉴权入口（见 D.2）|
|---|---|---|---|---|
| **PUT**（仓库 URL）| clone URL 文本 | 服务端**浅克隆**（`depth=1`、单分支）后全量替换 | curl / `cli --upload-git` | `AuthorizeUpdateFromRepository` |
| **PUT**（归档）| tar / tar+gzip / tar+zstd / **zip** | 全量替换 | curl / `cli --upload-dir` / Action | `AuthorizeUpdateFromArchive` |
| **PATCH**（归档）| tar / tar+gzip / tar+zstd（**无 zip**）| 增量合并（char device(0,0)=whiteout 删；`Atomic:` 头）| `cli --upload-dir --path` / Action `path:` | `AuthorizeUpdateFromArchive` |
| **POST**（webhook）| Forgejo/Gitea/Gogs/**GitHub** push payload | 按事件头（`X-*-Event`）触发，仅处理**授权分支**（通常 `pages`；wildcard index 站点可配 `index-repo-branch`）| forge webhook | `AuthorizeUpdateFromRepository` |
| **DELETE**（或空 body PUT）| — | 下线站点 | curl / `cli --delete` | `AuthorizeDeletion` |

> 关键纠缠点：`cli --upload-git` **不在本地 clone**，只是把仓库 URL 当 body PUT 上去、由服务端克隆——和"PUT 仓库 URL"是**同一个通道**（`git-pages-cli/main.go:312`：`http.NewRequest("PUT", …, url)`）。而 PUT-仓库-URL 走的 `AuthorizeUpdateFromRepository` **只认 DNS Challenge / repository allowlist**，PUT 时压根不读 `Forge-Authorization`（`src/auth.go:441` 的 allowlist 分支限 PUT/POST、`:454` 的 wildcard-match 限 POST）——所以 `--upload-git --token X` 里的 token 会被静默忽略；forge-token 鉴权只在**归档**（PUT/PATCH archive）路径上有意义。

## D.2 凭什么放行：README 的 7 条鉴权规则（+ 默认拒绝）

内容更新鉴权 README 列了 **8 条按序尝试**的规则（`src/auth.go` 逐条对应）。真正"配合 git-server"的差异全在**`调 forge API?` 和 `对 GitHub`** 两列（前面正文没单独汇总过）。

| # | 规则（README）| 触发方法 | 载体 | 调 forge API? | 对 GitHub | 关键限制 |
|---|---|---|---|---|---|---|
| 1 | Development Mode | 任意 | `PAGES_INSECURE=1`（§2.4 方案 D 的"边缘 Bearer"是 **Caddy 层**附加约定，git-pages 代码里无对应实现）| 否 | ✓ | 无条件放行，生产禁用 |
| 2 | DNS Challenge | PUT/PATCH/DELETE/POST | `_git-pages-challenge.<host>` TXT + 口令（`Authorization: Pages <口令>`，或 Basic `Base64("Pages:<口令>")`——给**发不了自定义头的 GitHub/Gogs**）| 否 | ✓ | 绝对权限；PUT/POST 限分支 `pages` |
| 3 | DNS Allowlist（repo）| PUT / POST | `_git-pages-repository.<host>` TXT 列 clone URL | **否、免 token** | ✓ | **仅根 / `.index` 站**；**不能 DELETE** |
| 4 | Wildcard Match（content）| **仅 POST**(webhook) | `[[wildcard]]` 配置 + webhook payload | **否** | ✓（webhook 收 GitHub payload）| 只走 webhook，REST 不行 |
| 5 | Forge Auth（wildcard）| PUT/PATCH/DELETE | `[[wildcard]]` + `Forge-Authorization` 头 | **是**（Gogs/Gitea/Forgejo 兼容 API）| ✗ | 多租户；archive 路径 |
| 6 | Forge Auth（wildcard, preview）| PUT/PATCH/DELETE | `[[wildcard]].preview-domain` + token，走 `/api/v1/actions/run` | **是** | ✗ | **仅 Forgejo 16+、需 feature flag**；PR 预览站 |
| 7 | Forge Auth（DNS allowlist）| PUT/PATCH/DELETE | `_git-pages-forge-allowlist.<host>` TXT + `Forge-Authorization` 头 | **是**（同上）| ✗ | **仅根 / `.index` 站** |
| 8 | Default Deny | — | — | — | — | 其余一律拒 |

对照 §2.4 的四方案：**方案 A** = 规则 2，**方案 B** = 规则 7，**方案 C** = 规则 5，**方案 D** = 规则 1，另有免 token 的 **repository allowlist** = 规则 3。规则 4（wildcard-match、免 forge API）和规则 6（preview、仅 Forgejo）§2.4 没展开——分别是"多租户但只走 webhook、不需 token"和"Forgejo PR 预览站"两种少见场景。

**两条"仅根站"限制同源**：规则 3 与规则 7 都调用同一个 `authorizeDNSAllowlist(r, scope)`（`src/auth.go:200`），`.index`-only 检查（`if projectName != ".index"`，行 218）写在该共享函数里，所以两者都**只授权根 / 索引站点、不能给 `/子项目/` 单独授权**（附录 A④ 只在方案 B 下点了这条，其实规则 3 同受此限）。

**对 GitHub 一句话**：能"发布"（规则 2 DNS-challenge / 规则 3 repo-allowlist / 规则 4 webhook 都收 GitHub payload），但**不能复用 GitHub 的权限校验**——规则 5/6/7 的 forge-token 走的是 Gogs/Gitea/Forgejo 兼容 API（`src/forge_api.go` 的 `makeGogsAPIRequest` 打 `/api/v1/…`，无任何 GitHub 代码路径），GitHub 的 API 不兼容这套。
