# MkDocs

MkDocs 把一组 Markdown 源文件转换成静态网站。它本身负责读取配置、组织页面、调用 Markdown 扩展、运行插件和渲染主题；最终产物只是 HTML、CSS、JavaScript、图片等静态文件，可以部署到任何静态文件服务器。

这篇文档先讲 MkDocs 的通用模型，再以 Material for MkDocs 作为主要示例主题。凡是只属于 Material 的能力都会明确标注。文中的核心行为按 [MkDocs 1.6.1](https://github.com/mkdocs/mkdocs/tree/bb7e8b62185b11d9f59bb7f50b13c15134f62f8a)、 [Material for MkDocs 9.7.6](https://github.com/squidfunk/mkdocs-material/tree/6c52ed6289b171a153875491f059a94819ec3e10) 和 [PyMdown Extensions 10.21.3](https://github.com/facelessuser/pymdown-extensions/tree/42628414c6591b1a1ce211157090783e3b2242d6) 核验；升级这些组件后，应重新验证涉及内部实现的结论。

## <a id="foundation"></a>从 Markdown 到网站

### 工作模型

一个 MkDocs 项目通常由三类输入组成：

```text
<project>/
├── mkdocs.yml          # 站点配置
├── docs/               # Markdown 与静态资源
│   ├── index.md
│   ├── guide.md
│   └── images/
└── pyproject.toml      # 可选：Python 与文档依赖
```

构建过程可以概括为：

```text
Markdown + 静态资源 + mkdocs.yml
                  │
                  ├─ Markdown 扩展：改变 Markdown 如何解析
                  ├─ 插件：参与文件、导航、页面与构建事件
                  └─ 主题：把页面内容放进 HTML 布局
                  │
                  ▼
               site/
```

几个容易混淆的概念：

| 名称          | 含义                                                         |
| ------------- | ------------------------------------------------------------ |
| `docs_dir`    | 源文件目录，默认是 `docs/`                                   |
| `site_dir`    | 构建产物目录，默认是 `site/`                                 |
| 页面源路径    | 相对 `docs_dir` 的 Markdown 路径，如 `guide/install.md`      |
| 页面 URL      | 主题和 `use_directory_urls` 共同生成的浏览器地址             |
| Markdown 扩展 | 改变 Markdown 语法或渲染规则的 Python-Markdown 扩展          |
| MkDocs 插件   | 参与构建生命周期、可读写页面、导航、文件和配置的 Python 组件 |
| 主题          | 页面 HTML、CSS、JavaScript 和布局模板                        |

MkDocs 的单页流水线依次读取 Markdown、触发 `page_markdown`、运行Python-Markdown、触发 `page_content`，再交给 Jinja 主题模板并写出 HTML。这解释了为什么宏插件、Markdown 扩展和后处理插件的顺序会改变最终结果。完整事件顺序见 [MkDocs 1.6.1 的页面构建源码](https://github.com/mkdocs/mkdocs/blob/bb7e8b62185b11d9f59bb7f50b13c15134f62f8a/mkdocs/commands/build.py#L147-L235)。

### `serve` 与 `build`

`mkdocs serve` 启动内置开发服务器：先构建站点，再监听源文件变化，重新构建并通知浏览器刷新。它使用临时 `site_dir`，主要用于边写边预览。官方入门文档也把它称为内置 dev-server，而不是生产静态服务器： [MkDocs 1.6.1 Getting Started](https://github.com/mkdocs/mkdocs/blob/bb7e8b62185b11d9f59bb7f50b13c15134f62f8a/docs/getting-started.md#L32-L58)。

`mkdocs build` 把完整静态站写入 `site_dir`。正式发布通常应部署这个目录，而不是把开发服务器直接当公开只读站。MkDocs 官方给出的通用部署方式也是把构建目录复制给任意静态托管服务： [Deploying your docs](https://github.com/mkdocs/mkdocs/blob/bb7e8b62185b11d9f59bb7f50b13c15134f62f8a/docs/user-guide/deploying-your-docs.md#L118-L139)。

```bash
# 开发预览
uv run --group docs mkdocs serve

# 正式静态构建
uv run --group docs mkdocs build --clean
```

`--dirty` 会保留旧产物并跳过部分未变化页面，适合临时加速开发；源码明确提醒它可能留下陈旧文件，并让导航或链接不准确，不应作为正式发布方式： [MkDocs 1.6.1 CLI](https://github.com/mkdocs/mkdocs/blob/bb7e8b62185b11d9f59bb7f50b13c15134f62f8a/mkdocs/__main__.py#L275-L290)。

### 最小项目

用 uv 管理文档依赖时，可以把它们放进独立 dependency group，使项目运行依赖与文档工具互不混杂：

```toml
[project]
name = "example-project"
version = "0.1.0"
requires-python = ">=3.10"

[dependency-groups]
docs = [
  "mkdocs==1.6.1",
  "mkdocs-material==9.7.6",
]
```

不使用 uv 时，也可以在单独虚拟环境中用 pip 安装同样的精确版本。关键不是具体包管理器，而是不要把文档工具无版本地装进系统 Python。

```bash
uv lock --check
uv sync --locked --group docs
uv run --no-sync mkdocs serve --livereload --no-strict
uv run --no-sync mkdocs build --clean
```

Poe the Poet、Just、Make等任务运行器可以把这些命令包装成短命令，但它们不是 MkDocs 或 uv 的必要组成部分。

最小 `mkdocs.yml`：

```yaml
site_name: Example Documentation

theme:
  name: material

plugins:
  - search
```

最小首页：

```markdown
# Example Documentation

欢迎阅读。

[打开指南](guide.md)
```

内部链接应指向 Markdown 源路径，而不是猜测构建后的 `.html` 路径。MkDocs 会根据目标页面和当前配置生成最终 URL，并参与链接校验。

### 配置的组织

#### 站点地址

`site_url` 是站点的正式 canonical URL，即页面希望浏览器和搜索引擎视为“唯一正式地址”的 URL。站点部署在子路径时，子路径也必须包含在内：

```yaml
site_url: https://docs.example.com/project/
```

它不只是 SEO 元数据。sitemap 是列出站内页面 URL 的 XML 文件，搜索引擎和部分前端功能会读取它。MkDocs 只有在页面拥有 canonical/absolute URL 时才会把页面写进默认 sitemap；未设置 `site_url` 的生产构建仍会生成 `sitemap.xml`，但 `<urlset>` 可能为空： [MkDocs sitemap 模板](https://github.com/mkdocs/mkdocs/blob/bb7e8b62185b11d9f59bb7f50b13c15134f62f8a/mkdocs/templates/sitemap.xml#L1-L11)。

路径或域名需要由部署环境决定时，可从环境变量注入：

```yaml
site_url: !ENV [DOCS_SITE_URL, ""]
```

空值适合普通本地构建；正式发布流水线应提供完整 URL。

#### 仓库与源码链接

```yaml
repo_name: Example Forge
repo_url: https://forge.example.com/owner/repository
edit_uri: _edit/main/docs/
```

主题支持时，`repo_url` 提供仓库入口，`edit_uri` 提供当前页面的源码编辑地址。路径规则由托管平台决定；自建 Forgejo/Gitea 不应照抄 GitHub 的 `edit/branch/...` 结构。MkDocs 还提供 `edit_uri_template`，可用 `{path}` 或 `{path_noext}` 构造地址： [MkDocs 1.6.1 配置文档](https://github.com/mkdocs/mkdocs/blob/bb7e8b62185b11d9f59bb7f50b13c15134f62f8a/docs/user-guide/configuration.md#L93-L195)。

Material 专属的 `content.action.edit` 与 `content.action.view` 只有在页面实际拥有对应 URL 时才有意义：

```yaml
theme:
  features:
    - content.action.edit
```

Forgejo/Gitea 的编辑路径通常使用 `_edit/<branch>/<path>`，仍应按目标实例实际 URL 核验。`content.action.view` 在 Material 9.7.6 只明确支持 GitHub；其他托管平台不要与 edit action 一起盲开。见 [Material 9.7.6 仓库操作配置](https://github.com/squidfunk/mkdocs-material/blob/6c52ed6289b171a153875491f059a94819ec3e10/docs/setup/adding-a-git-repository.md#L91-L133)。

#### strict 与 validation

`strict: true` 的准确语义是：构建期间记录到 WARNING 或 ERROR 时中止。它不会自动把所有 INFO 提升成 WARNING。MkDocs 1.6.1 的默认校验等级中，坏文件链接是 WARNING，但坏锚点、绝对链接和遗漏导航页面等多项检查默认仍是 INFO： [默认 validation 等级](https://github.com/mkdocs/mkdocs/blob/bb7e8b62185b11d9f59bb7f50b13c15134f62f8a/mkdocs/config/defaults.py#L169-L199)。

希望 strict 真正覆盖这些检查时，应显式提升等级：

```yaml
strict: true

validation:
  nav:
    omitted_files: warn
    not_found: warn
    absolute_links: warn
  links:
    not_found: warn
    absolute_links: warn
    unrecognized_links: warn
    anchors: warn
```

开发服务器通常会经历“新文件尚未提交”“导航改到一半”等暂态，可在命令行覆盖：

```bash
mkdocs serve --livereload --no-strict
mkdocs build --clean                  # 仍读取 strict: true
```

这种分工让开发预览保持可用，同时保留正式发布闸门。

#### 监听目录

MkDocs serve 默认监听 `docs_dir` 与配置文件。`watch` 适合加入位于 `docs_dir` 外、但会影响构建的宏、Hook 或模板：

```yaml
watch:
  - mkdocs_ext
  - theme_overrides
```

重复加入 `docs_dir` 通常没有必要。监听目录里的任何持续写入都可能触发全站重建；高频变化、又不需要 Markdown 处理的 HTML 报告，更适合由静态服务器直接提供。

#### 插件与 Hook

一旦显式配置 `plugins`，默认 `search` 不再自动补入，因此通常要自己保留：

```yaml
plugins:
  - search
  - macros
```

Hook 是相对 `mkdocs.yml` 的 Python 文件，通过普通函数参与插件事件：

```yaml
hooks:
  - mkdocs_ext/build_policy.py
```

serve 重建时 Hook 模块不会重新 import，模块级可变状态必须在每轮合适的事件中清空。官方说明见 [MkDocs 1.6.1 hooks 配置](https://github.com/mkdocs/mkdocs/blob/bb7e8b62185b11d9f59bb7f50b13c15134f62f8a/docs/user-guide/configuration.md#L809-L848)。

#### 配置继承

```yaml
INHERIT: base.yml
```

MkDocs 对 mapping 深合并，但普通 list 整体替换，不会追加。因此子配置中的 `theme.features`、传统 list 写法的 `plugins`、`markdown_extensions` 或 `nav` 可能把父配置整段覆盖。插件和扩展需要继承时，优先使用 mapping 语法；行为与示例见 [MkDocs 1.6.1 配置继承](https://github.com/mkdocs/mkdocs/blob/bb7e8b62185b11d9f59bb7f50b13c15134f62f8a/docs/user-guide/configuration.md#L1125-L1237)。

当开发站和静态发布站只有少量行为差异时，一份配置配合 Hook 或环境变量通常比复制两份长插件列表更不易漂移。

### 依赖与版本

文档依赖也应进入 lockfile。CI 镜像可以预装常用版本加速，但构建前仍应以 lockfile同步为准，避免“镜像里有一份、项目声明又是一份”的双重真相源。

如果扩展代码依赖第三方插件的内部方法、DOM 类名或精确 JavaScript 字符串，应使用精确版本：

```toml
docs = [
  "mkdocs-live-edit-plugin==0.4.1",
]
```

版本范围只适合依赖公开兼容接口的场景。

MkDocs 1.6.1 只要求 `click>=7.0`，因此 Click 这类传递依赖的兼容约束更适合写成 dependency constraint，而不是伪装成业务直接依赖。Click 8.3.x 曾让 MkDocs 的 `--livereload` 默认值解析错误；修复进入 Click 8.4.0： [Click 8.4.0 changelog](https://github.com/pallets/click/blob/8.4.0/CHANGES.rst#L80-L87)。

```toml
[tool.uv]
constraint-dependencies = ["click>=8.4.0"]
```

Material 团队在 2026 年公开说明 MkDocs 2.0 将破坏现有主题和插件兼容性。在升级核心大版本前，应先检查主题、插件和自定义 Hook，而不是只看 Python 依赖是否能解析： [Material 关于 MkDocs 2.0 的说明](https://squidfunk.github.io/mkdocs-material/blog/2026/02/18/mkdocs-2.0/)。

## <a id="authoring"></a>写作与页面组织

### 导航模型

导航决定侧栏、顶部菜单、上一页/下一页和页面层级。它与磁盘目录相关，但不等同：一个 Markdown 文件即使没有进入导航，也仍可能被构建并通过 URL 访问。

front matter 是 Markdown 文件开头由两行 `---` 包住的 YAML 元数据。常见组织方式有三种：

| 模式 | 顺序真相源 | 适合场景 | 编辑器兼容性 |
| --- | --- | --- | --- |
| 原生 `nav` | 根 `mkdocs.yml` | 站点较小、需要集中策展 | 多数工具认识；多人容易冲突 |
| `.pages` | 每个目录的元文件 | 大站点、目录负责人分治 | awesome-pages专属；移动页面要同步元文件 |
| front matter 权重 | 每个 Markdown 页面 | CMS/块编辑器创建页面、减少集中冲突 | 依赖权重插件；页面元数据更适合表单化 |

不要同时把多个系统都当最终排序权威。多个插件都在 `on_nav` 修改导航时，插件顺序会决定谁覆盖谁。

### 原生 `nav`

未配置 `nav` 时，MkDocs 根据文档路径自动生成嵌套导航。显式配置后，列表顺序就是导航顺序：

```yaml
nav:
  - 首页: index.md
  - 入门:
      - 安装: getting-started/install.md
      - 配置: getting-started/configuration.md
  - 外部资料: https://example.com/
```

路径相对 `docs_dir`。未列入显式导航的 Markdown 仍会被构建，但没有全局 previous/next，并按 `validation.nav.omitted_files` 记录日志： [MkDocs 1.6.1 nav 源码](https://github.com/mkdocs/mkdocs/blob/bb7e8b62185b11d9f59bb7f50b13c15134f62f8a/mkdocs/structure/nav.py#L130-L162)。

确实需要可访问但不进导航的页面，可以用 `not_in_nav` 声明意图：

```yaml
not_in_nav: |
  drafts/**
  internal-note.md
```

### 分散式 `.pages`

`mkdocs-awesome-pages-plugin` 2.x 允许每个目录放置 `.pages`：

```yaml
plugins:
  - search
  - awesome-pages
```

```yaml
# docs/guide/.pages
title: 使用指南
nav:
  - index.md
  - 安装: install.md
  - 配置: configuration.md
```

优点是目录结构和导航元数据放在一起，修改不同目录时较少冲突。代价是通用 CMS、WYSIWYG 编辑器和“新建页面”按钮通常不知道还要更新 `.pages`。

2.10.1 不支持通用 `weight` 字段；它使用 `.pages` 中的 `nav`、`order`、 `sort_type` 等配置： [awesome-pages 2.10.1 配置源码](https://github.com/lukasgeiter/mkdocs-awesome-nav/blob/da5ed8ee013fc3ff37aab17194c029d2a884ad04/mkdocs_awesome_pages_plugin/meta.py#L101-L144)。

该项目后续主线已更名为 `mkdocs-awesome-nav`，插件名和默认元文件也发生变化。锁定 2.x 时应阅读对应 tag，不要把主线 v3 语法混入旧项目： [v3 迁移说明](https://github.com/lukasgeiter/mkdocs-awesome-nav/blob/e0699c37d8e246f78cb15e99607e41edc9ac8b1c/docs/migration-v3.md#L1-L42)。

### front matter 权重

权重模式把顺序放进每个页面自己的 front matter：

```markdown
---
title: 安装
weight: 20
---

# 安装
```

例如 `mkdocs-nav-weight` 0.3.0 会读取 `weight`、`headless`、`retitled` 和 `empty`，递归排序后重建 previous/next： [nav-weight 0.3.0 实现](https://github.com/shu307/mkdocs-nav-weight/blob/0b55c5eee51d2befed5f7c0541fcb9d77a0657cb/mkdocs_nav_weight/nav_setter.py#L33-L109)。

```yaml
plugins:
  - search
  - mkdocs-nav-weight:
      default_page_weight: 1000
      index_weight: -10
```

依赖中也要使用包名：

```toml
docs = [
  "mkdocs-nav-weight==0.3.0",
]
```

其默认 `default_page_weight=0`；若显式页面使用正权重而未标记页面应排最后，就要把默认值设大： [默认配置](https://github.com/shu307/mkdocs-nav-weight/blob/0b55c5eee51d2befed5f7c0541fcb9d77a0657cb/mkdocs_nav_weight/__init__.py#L14-L26)。

权重模式对 CMS 友好，因为新建页面只需写自己的元数据，不必重写一个全局导航文件。但它把展示顺序和页面正文放在同一个文件中，纯内容修改也可能触发排序元数据冲突。

### 页面与目录首页

Material 专属的 `navigation.indexes` 允许 section 的第一个页面承担目录首页：

```yaml
theme:
  name: material
  features:
    - navigation.sections
    - navigation.indexes
```

目录首页通常命名为 `index.md`：

```text
docs/
└── guide/
    ├── index.md
    ├── install.md
    └── configuration.md
```

重命名、移动或删除页面时，至少检查：

```text
源文件相对链接
mkdocs.yml 的 nav
目录 .pages
front matter 权重
图片相对路径
跨页锚点
最近更新/历史索引
```

### Markdown 与 PyMdown

MkDocs 使用 Python-Markdown。Material 常与 PyMdown Extensions 搭配：

```yaml
markdown_extensions:
  - admonition
  - attr_list
  - footnotes
  - md_in_html
  - tables
  - toc:
      permalink: true
  - pymdownx.details
  - pymdownx.highlight
  - pymdownx.inlinehilite
  - pymdownx.superfences
  - pymdownx.tabbed:
      alternate_style: true
  - pymdownx.tasklist:
      custom_checkbox: true
```

只启用实际使用或明确计划使用的扩展。扩展越多不等于功能越强；它们可能改变相同标记的解析顺序，也会扩大 WYSIWYG round-trip 的兼容面。

#### Admonition 与 details

```markdown
!!! note "提示" 普通提示内容。

??? warning "默认折叠" 展开后显示。
```

标题行下面的内容必须缩进。围栏代码、列表和 tabs 嵌入 admonition 时，其缩进还要相对增加。

#### 内容标签页

```markdown
=== "Linux"

    Linux 内容。

=== "Windows"

    Windows 内容。
```

连续的 `=== "Title"` 组成一个 tab 组，内容缩进四格。`===!` 可强制开始新组， `===+` 可强制选中某项： [PyMdown 10.21.3 Tabbed](https://github.com/facelessuser/pymdown-extensions/blob/42628414c6591b1a1ce211157090783e3b2242d6/docs/src/markdown/extensions/tabbed.md#L26-L113)。

Tabbed 只生成 HTML 结构，最终视觉样式由主题负责。离开 Material 或对应 CSS 后，同一 Markdown 不一定仍显示为标签页。

#### 代码围栏与 SuperFences

普通 Markdown 围栏在列表、引用等嵌套结构中容易失效。SuperFences 允许围栏代码嵌套，但开闭围栏类型、长度和缩进必须匹配： [PyMdown 10.21.3 SuperFences](https://github.com/facelessuser/pymdown-extensions/blob/42628414c6591b1a1ce211157090783e3b2242d6/docs/src/markdown/extensions/superfences.md#L30-L100)。

```yaml
- pymdownx.superfences:
    custom_fences:
      - name: mermaid
        class: mermaid
        format: !!python/name:pymdownx.superfences.fence_code_format
```

自定义 formatter 出错时部分异常可能被扩展吞掉；复杂 custom fence 应有构建测试，而不是只看本地一次渲染。

#### Snippets

Snippets 把其他文件内容嵌进页面：

```markdown
--8<-- "src/example.py:important"
```

```yaml
- pymdownx.snippets:
    base_path:
      - .
    check_paths: true
```

`check_paths: true` 可以在引用不存在时尽早失败。把仓库根放进 `base_path` 会允许页面引用源码，但也扩大了文档构建可读取的范围；公开文档中不要误嵌私密配置。

### 数学公式

浏览器中的 LaTeX 数学通常分两步：

```text
Arithmatex 保护并标记 Markdown 中的数学文本
                         │
                         ▼
KaTeX 或 MathJax 在浏览器中把标记渲染成公式
```

Arithmatex 本身不绘制公式。Material 推荐启用通用输出：

```yaml
markdown_extensions:
  - pymdownx.arithmatex:
      generic: true
```

它可识别 `$...$`、`\(...\)`、`$$...$$`、`\[...\]` 等定界符；`smart_dollar` 会要求美元定界符紧邻非空白字符，减少货币文本误判： [Arithmatex 10.21.3](https://github.com/facelessuser/pymdown-extensions/blob/42628414c6591b1a1ce211157090783e3b2242d6/docs/src/markdown/extensions/arithmatex.md#L8-L32)。

#### KaTeX

KaTeX 体积较轻、渲染较快，但支持的是 LaTeX 数学语法子集。初始化脚本：

```javascript
document$.subscribe(({ body }) => {
  renderMathInElement(body, {
    delimiters: [
      { left: "$$", right: "$$", display: true },
      { left: "$", right: "$", display: false },
      { left: "\\(", right: "\\)", display: false },
      { left: "\\[", right: "\\]", display: true },
    ],
    ignoredTags: ["script", "noscript", "style", "textarea", "pre", "code"],
  });
});
```

Material 专属的 `document$` 会在首次加载及 instant navigation 注入新页面后发出事件，因此公式不会只在第一次完整加载时渲染： [Material document$](https://github.com/squidfunk/mkdocs-material/blob/6c52ed6289b171a153875491f059a94819ec3e10/docs/customization.md#L37-L75)。

```yaml
extra_javascript:
  - javascripts/katex.js
  - https://cdn.example.com/katex/<exact-version>/katex.min.js
  - https://cdn.example.com/katex/<exact-version>/contrib/auto-render.min.js

extra_css:
  - https://cdn.example.com/katex/<exact-version>/katex.min.css
```

不要使用 `@0`、`latest` 等滚动版本。更稳定的做法是下载经过验证的精确版本到 `docs/assets/vendor/katex/`，消除 CDN 可用性和跨版本变化。

#### MathJax

MathJax 支持更多 LaTeX 命令、MathML 与更丰富的输出配置，代价通常是体积和运行开销更高。Material 9.7.6 的初始化方式会在每次 `document$` 事件中清理旧缓存并重新typeset： [Material 数学集成](https://github.com/squidfunk/mkdocs-material/blob/6c52ed6289b171a153875491f059a94819ec3e10/docs/reference/math.md#L25-L68)。

```javascript
window.MathJax = {
  tex: {
    inlineMath: [["\\(", "\\)"]],
    displayMath: [["\\[", "\\]"]],
    processEscapes: true,
    processEnvironments: true,
  },
  options: {
    ignoreHtmlClass: ".*|",
    processHtmlClass: "arithmatex",
  },
};

document$.subscribe(() => {
  MathJax.startup.output.clearCache();
  MathJax.typesetClear();
  MathJax.texReset();
  MathJax.typesetPromise();
});
```

选择 KaTeX 还是 MathJax，主要看公式语法覆盖、无障碍要求、资源体积和渲染速度，而不是“哪个名字更流行”。

### 图片与图表

图片路径相对当前 Markdown 源文件：

```markdown
![示意图](images/architecture.webp)
```

页面移动后，相对图片路径也要一起修正。Material 的灯箱通常由独立插件完成，插件只增强展示，不改变图片的源路径语义。

Mermaid 的典型链路是：

`````text
SuperFences 把 ```` ```mermaid ```` 转成 class="mermaid" 的 HTML
Material 前端发现该节点并调用 Mermaid 运行时
`````

Material 9.7.6 会处理 instant navigation、字体和明暗主题： [Material Mermaid 配置](https://github.com/squidfunk/mkdocs-material/blob/6c52ed6289b171a153875491f059a94819ec3e10/docs/reference/diagrams.md#L14-L36)。如果主题已经提供 Mermaid 初始化，再增加一个只订阅 `document$` 但不做任何事的 JavaScript 文件没有价值。

## <a id="editing"></a>编辑方式

“在浏览器里编辑文档”可以指完全不同的东西。选工具前先分清：

| 名称           | 实际编辑对象                                        |
| -------------- | --------------------------------------------------- |
| 仓库编辑链接   | 跳到 Forge/Git 平台的源码编辑页                     |
| 整页源码编辑   | 在文档页面中打开整个 Markdown 文件的文本框          |
| WYSIWYG        | 把正文转换为 `contenteditable`，再序列化回 Markdown |
| 内容块编辑     | 把渲染块映射回源文件行范围，只修改对应块            |
| Git-backed CMS | 在独立管理界面编辑 Git 仓库中的内容并创建 commit    |

这些方案的困难不在“能否显示一个文本框”，而在能否保留 Markdown 原文、导航元数据、宏、数学公式和 Git 工作流。

### 本地编辑器与预览

最简单、保真度最高的路线仍是：

```text
本地编辑器修改 Markdown
        │
        ▼
mkdocs serve 自动重建
        │
        ▼
浏览器预览真实主题输出
```

它没有 HTML→Markdown 往返，不需要额外写 API，也不会改变宏或自定义扩展语法。缺点是作者必须能访问工作树和编辑器。

Material 的 repository action 介于本地编辑和 CMS 之间。它只提供当前源文件的编辑/查看链接，内容仍由 Git 平台编辑：

```yaml
repo_url: https://forge.example.com/owner/repository
edit_uri: _edit/main/docs/

theme:
  features:
    - content.action.edit
```

这是公开项目中常见、风险较低的入口，但编辑体验和 `_edit` 路径都由托管平台决定，应先在目标 Forge中打开一个真实文件核对。

### 浏览器整页源码编辑

[`mkdocs-live-edit-plugin` 0.4.1](https://github.com/EddyLuten/mkdocs-live-edit-plugin/releases/tag/v0.4.1) 在 `mkdocs serve` 时启动独立 WebSocket 服务，并把整个页面 Markdown 放进 textarea。它支持读取、保存、新建、重命名和删除页面： [README](https://github.com/EddyLuten/mkdocs-live-edit-plugin/blob/c722d2c1c06056e97fd1fa8919a354a46c6da949/README.md#L7-L18)。

```yaml
plugins:
  - search
  - live-edit:
      websockets_host: 127.0.0.1
      websockets_port: 8484
```

优点是它直接编辑宏展开前的原始 Markdown，不经过 HTML 反序列化。缺点是编辑范围仍是整个文件，且页面新建、改名、删除不会自动维护原生 `nav` 或 `.pages`。

0.4.1 不适合未经修补直接暴露：

- 前端硬编码 `ws://${hostname}:${port}`，HTTPS 页面会被浏览器作为混合内容阻断： [live-edit.js](https://github.com/EddyLuten/mkdocs-live-edit-plugin/blob/c722d2c1c06056e97fd1fa8919a354a46c6da949/live/live-edit.js#L3-L20)。
- 读取、写入、删除、创建和重命名都直接使用 `docs_dir / client_path`，没有解析后的目录 containment 检查： [plugin.py](https://github.com/EddyLuten/mkdocs-live-edit-plugin/blob/c722d2c1c06056e97fd1fa8919a354a46c6da949/live/plugin.py#L79-L192)。
- WebSocket 本身没有认证和 Origin 白名单。

因此默认只应绑定回环地址。公网使用时，后端至少要满足本文 [公网入口的安全契约](#public-edit-contract)，不能只在前面加一个反向代理就宣布安全。回环绑定只阻止其他主机直接连接，不阻止同一台浏览器打开的恶意网页向 `ws://127.0.0.1:8484` 发起连接；即使只在本机使用，服务端仍需校验 Origin并限制文件路径。

### 渲染页面编辑

#### WYSIWYG

[`mkdocs-live-wysiwyg-plugin` 0.4.6](https://github.com/samrocketman/mkdocs-live-wysiwyg-plugin/releases/tag/v0.4.6) 建立在 live-edit 之上，把 textarea 替换成 WYSIWYG/Markdown 双模式编辑器。它提供 Material正文内编辑、全屏 Focus Mode、表格、admonition、任务列表、图片和 Mermaid 工具： [README](https://github.com/samrocketman/mkdocs-live-wysiwyg-plugin/blob/15c03c0dc7288cdcee72fb6e0dd4b79e6fc59d65/README.md#L41-L82)。

```yaml
plugins:
  - live-edit
  - live-wysiwyg:
      autoload_wysiwyg: true
      api_port: 8485
```

插件顺序有意义：WYSIWYG 依赖 live-edit 已经创建的控件与 WebSocket。它还会启动第三个 HTTP API 端口，用于链接检查、文件操作和 Mermaid session： [配置说明](https://github.com/samrocketman/mkdocs-live-wysiwyg-plugin/blob/15c03c0dc7288cdcee72fb6e0dd4b79e6fc59d65/PLUGIN_CONFIG.md#L28-L43)。

WYSIWYG 的核心难题是 Markdown→HTML→Markdown 并不天然无损。例如围栏样式、列表符号、引用链接、表格空格和原始 HTML 都可能被规范化。该项目为常见结构做了多组预处理/后处理，但仍明确记录：

- 多行 inline code 会变成单行；
- 自定义 HTML 为避免严重损坏而只读。

见 [Known diff quirks](https://github.com/samrocketman/mkdocs-live-wysiwyg-plugin/blob/15c03c0dc7288cdcee72fb6e0dd4b79e6fc59d65/docs/diff-quirks.md#L1-L8)。

它只正式支持 Material，并继承 live-edit 的明文 WebSocket与路径安全问题。其 Python 依赖也没有锁定 live-edit 版本： [pyproject.toml](https://github.com/samrocketman/mkdocs-live-wysiwyg-plugin/blob/15c03c0dc7288cdcee72fb6e0dd4b79e6fc59d65/pyproject.toml#L1-L26)。

它的辅助 API还包含外链检查：服务端会对客户端给出的 URL直接执行 HTTP HEAD，没有过滤回环、私网、link-local或云 metadata地址： [api_server.py](https://github.com/samrocketman/mkdocs-live-wysiwyg-plugin/blob/15c03c0dc7288cdcee72fb6e0dd4b79e6fc59d65/mkdocs_live_wysiwyg_plugin/api_server.py#L930-L943)。把该 API暴露给远程用户前，应增加出站协议、DNS解析结果和目标IP白/黑名单，或禁用外链检查；否则认证用户可把服务器当作探测内网的请求代理。

同一 API默认返回 `Access-Control-Allow-Origin: *`，并提供目录重命名/删除、文件移动/ 删除等写接口： [CORS与路由](https://github.com/samrocketman/mkdocs-live-wysiwyg-plugin/blob/15c03c0dc7288cdcee72fb6e0dd4b79e6fc59d65/mkdocs_live_wysiwyg_plugin/api_server.py#L104-L123)、 [写接口分发](https://github.com/samrocketman/mkdocs-live-wysiwyg-plugin/blob/15c03c0dc7288cdcee72fb6e0dd4b79e6fc59d65/mkdocs_live_wysiwyg_plugin/api_server.py#L313-L329)。回环监听不能阻止浏览器中的其他网页向 localhost发跨源请求，因此远程或本地使用都应增加认证、精确 Origin/CORS和请求方法限制。

#### 内容块编辑

块编辑先解析 Markdown，为每个标题、段落、列表、代码块等记录源文件行范围，再把范围写进对应 HTML 元素。作者点击页面中的块时，只编辑那段原始 Markdown。

[`ishan-gaur/mkdocs-liveedit` 的固定快照](https://github.com/ishan-gaur/mkdocs-liveedit/commit/43a8db5ac0285ba1ea7316f32f644dc6590e3a5e) 就是这种实现。它会合并列表、admonition和 tab set，以保持“一个源块对应一个顶层HTML块”： [sourcemap.py](https://github.com/ishan-gaur/mkdocs-liveedit/blob/43a8db5ac0285ba1ea7316f32f644dc6590e3a5e/src/mkdocs_liveedit/sourcemap.py#L14-L119)。

这种方案避免整页 HTML round-trip，但映射依赖构建前后的块顺序一致。宏、snippets、includes 或其他插件若插入、删除、拆分 HTML 块，后续行范围就可能错位。项目自身也把这些列为限制： [README](https://github.com/ishan-gaur/mkdocs-liveedit/blob/43a8db5ac0285ba1ea7316f32f644dc6590e3a5e/README.md#L61-L65)。作者明确把 production use 列为 non-goal，且要求直接从 GitHub 安装： [README 开头](https://github.com/ishan-gaur/mkdocs-liveedit/blob/43a8db5ac0285ba1ea7316f32f644dc6590e3a5e/README.md#L1-L7)。

### Git-backed CMS

Git-backed CMS 不直接修改服务器工作树，而是通过 Git 托管平台 API 读取文件、提交变更并触发 CI：

```text
浏览器 CMS
    │ OAuth / PAT
    ▼
Forge API
    │ commit
    ▼
Git branch
    │ CI
    ▼
静态站
```

它的优势是每次保存都有作者、commit、权限和回滚记录。它通常有独立 `/admin/` 界面，而不是在真实 MkDocs 页面中直接点击段落编辑。

这里涉及三种认证术语：

| 术语 | 含义 |
| --- | --- |
| OAuth | 用户在 Forge中授权 CMS，CMS无需知道用户密码 |
| PKCE | 纯浏览器 OAuth使用一次性 verifier/challenge，避免必须保管客户端 secret |
| PAT | Personal Access Token，用户手工创建并交给 CMS 的长期 API token |

#### Sveltia CMS 与 Forgejo

下面按 [Sveltia CMS 0.179.0](https://github.com/sveltia/sveltia-cms/releases/tag/v0.179.0) 说明。该版本要求 Gitea ≥1.24 或 Forgejo ≥12： [版本常量](https://github.com/sveltia/sveltia-cms/blob/79ae5b4f08d52a69bb46b4b348883f6319801d1d/src/lib/services/backends/git/gitea/constants.js#L8-L20)。

最小入口可以放在静态站的 `admin/index.html`：

```html
<!doctype html>
<html lang="zh">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Documentation CMS</title>
  </head>
  <body>
    <script
      src="https://unpkg.com/@sveltia/cms@0.179.0/dist/sveltia-cms.js"
      type="module"
    ></script>
  </body>
</html>
```

上例精确锁定前端版本。更可控的部署应把该文件下载到自己的静态资源目录，并记录完整性哈希。

Sveltia兼容 Decap 风格配置。以下示例假定 `admin/config.yml`：

```yaml
backend:
  name: gitea
  repo: <owner>/<repository>
  branch: <docs-branch>
  api_root: https://<forge-domain>/api/v1
  base_url: https://<forge-domain>
  app_id: <oauth-application-id>
  auth_methods:
    - oauth

media_folder: docs/assets/uploads
public_folder: /assets/uploads

collections:
  - name: docs
    label: Documentation
    folder: docs
    create: true
    extension: md
    format: frontmatter
    fields:
      - name: title
        label: Title
        widget: string
        required: false
      - name: body
        label: Body
        widget: markdown
        sanitize_preview: true
        modes:
          - raw
          - rich_text
```

Sveltia 0.179.0 会警告并忽略 Decap 的 `nested` collection选项： [配置解析器](https://github.com/sveltia/sveltia-cms/blob/79ae5b4f08d52a69bb46b4b348883f6319801d1d/src/lib/services/config/parser/collections/index.js#L26-L32)。需要管理多层 docs树时，应按实际内容边界为各子目录定义 collection，或在升级到明确支持 nested collection 的版本后重新核验。

`public_folder: /assets/uploads` 会把根路径链接写进 Markdown。若站点部署在子路径，或将 `validation.links.absolute_links` 提升为 `warn`，应让 MkDocs把这种路径解释为相对 `docs_dir`：

```yaml
validation:
  links:
    absolute_links: relative_to_docs
```

另一种做法是不用根路径式 `public_folder`，但嵌套页面的正确相对路径会随页面目录变化，需要 CMS 或自定义组件负责计算。两种方案都应在真实子路径构建中验证。

`auth_methods: [oauth]` 隐藏 PAT 登录，适合希望统一身份管理的部署。需要应急或个人使用时也可以允许 `token`，但 PAT 会进入浏览器存储和 API 请求，应限制权限并设置清晰的撤销路径。Sveltia的 Forgejo/Gitea登录界面同时支持 OAuth PKCE 与 PAT： [sign-in.svelte](https://github.com/sveltia/sveltia-cms/blob/79ae5b4f08d52a69bb46b4b348883f6319801d1d/src/lib/components/entrance/sign-in.svelte#L36-L151)。

只允许 PAT 的最小变体：

```yaml
backend:
  name: gitea
  repo: <owner>/<repository>
  branch: <docs-branch>
  api_root: https://<forge-domain>/api/v1
  base_url: https://<forge-domain>
  auth_methods:
    - token
```

OAuth PKCE 的 redirect URL 是 CMS 当前页面的 `origin + pathname`。例如站点部署在 `/project/`，CMS入口是 `https://docs.example.com/project/admin/`，Forgejo OAuth application 也应登记这个带结尾斜杠的精确地址： [Sveltia 0.179.0 PKCE实现](https://github.com/sveltia/sveltia-cms/blob/79ae5b4f08d52a69bb46b4b348883f6319801d1d/src/lib/services/backends/git/shared/auth.js#L194-L235)。

Sveltia是纯浏览器 PKCE客户端，不持有 client secret。创建 Forgejo OAuth application 时应选择 **public client**，不要启用 confidential client。RFC 6749把无法安全保存凭据的浏览器应用定义为 public client； [RFC 6749 §2.1](https://datatracker.ietf.org/doc/html/rfc6749#section-2.1)。PKCE通过一次性的 verifier/challenge 保护 authorization code，不要求浏览器持有 client secret： [RFC 7636](https://datatracker.ietf.org/doc/html/rfc7636)。

Sveltia会把包含 access/refresh token 的用户对象持久化到浏览器 localStorage： [account.svelte.js](https://github.com/sveltia/sveltia-cms/blob/79ae5b4f08d52a69bb46b4b348883f6319801d1d/src/lib/services/user/account.svelte.js#L13-L24)。因此 CMS最好使用独立 origin，例如 `https://cms.example.com/`，不要与允许 raw HTML、第三方脚本或不可信作者内容的公开站共用 origin；否则同源存储型 XSS可读取仓库写令牌。 `sanitize_preview: true` 保护 CMS预览区，但不能修复同源其他页面上的 XSS。

`modes` 顺序为 `raw, rich_text` 时，复杂页面默认打开原始 Markdown；普通作者仍可手动切换富文本。对只含标准标题、段落、列表和图片的页面，可以使用 `rich_text, raw` 作为默认顺序。

保存时，Sveltia把多文件变化和提交消息发送到配置分支并返回 commit SHA： [Forgejo/Gitea commit 实现](https://github.com/sveltia/sveltia-cms/blob/79ae5b4f08d52a69bb46b4b348883f6319801d1d/src/lib/services/backends/git/gitea/commits.js#L47-L101)。

#### 自定义宏组件

若正文包含稳定、结构化的自定义宏，可以把它注册成 editor component，而不是让富文本解析器把宏当普通段落：

```html
<script type="module">
  const waitForCMS = setInterval(() => {
    if (!window.CMS) return;
    clearInterval(waitForCMS);

    window.CMS.registerEditorComponent({
      id: "artifact",
      label: "Artifact",
      fields: [
        { name: "slug", label: "Slug", widget: "string" },
        { name: "view", label: "View", widget: "string", required: false },
      ],
      pattern:
        /^\{\{\s*artifact\("(?<slug>[^"]+)"(?:,\s*view="(?<view>[^"]+)")?\)\s*\}\}$/,
      toBlock: ({ slug, view }) =>
        view
          ? `{{ artifact("${slug}", view="${view}") }}`
          : `{{ artifact("${slug}") }}`,
      toPreview: ({ slug, view }) =>
        `<strong>Artifact:</strong> ${slug}${view ? ` / ${view}` : ""}`,
    });
  }, 50);
</script>
```

`pattern` 必须只匹配完整、可逆的块，`toBlock` 必须稳定地产生原始语法。Sveltia的组件 API 要求 `id`、`label`、`pattern`、字段和序列化函数： [registerEditorComponent](https://github.com/sveltia/sveltia-cms/blob/79ae5b4f08d52a69bb46b4b348883f6319801d1d/src/lib/services/api/index.js#L103-L154)。

嵌套 tabs、任意 Jinja 模板和多层 admonition 不适合只靠一个大正则建模；这些页面应默认 raw mode。

#### CMS 与本地预览

CMS 提交发生在远端 Git 分支，本地开发工作树不会自动变化。不要让 webhook 对正在开发、有未提交文件的工作树执行自动 pull。

稳妥的两种模式：

```text
模式 A
CMS → Forgejo commit → CI build → Pages
本地工作树完全独立

模式 B
CMS → Forgejo commit → webhook/定时任务
                         │
                         ▼
                 独立、只读部署 clone
                 git fetch + merge --ff-only
                         │
                         ▼
                    MkDocs preview
```

模式 B 的部署 clone 必须保持干净，只允许 fast-forward，即本地分支没有独立提交、只把指针向前移动到远端已有 commit。Git webhook、部署分支和 CI 的具体实现属于 `git` skill 的范围。

Sveltia不会天然理解 awesome-pages 的 `.pages` 或带 Python YAML tag 的 `mkdocs.yml`。初期只让 CMS 管 Markdown 与上传资源；导航和构建配置留给代码评审。

#### Forgejo CORS

CMS 与 Forgejo 不同 origin 时，浏览器会执行 CORS检查。只注册 OAuth application 不足以让后续 API请求成功；Forgejo/Gitea还必须允许 CMS origin、`Authorization` header和所需 HTTP方法。

目标配置形态：

```ini
[cors]
ENABLED = true
ALLOW_DOMAIN = https://cms.example.com
METHODS = GET,HEAD,POST,PUT,PATCH,DELETE,OPTIONS
HEADERS = Content-Type,Authorization,User-Agent
ALLOW_CREDENTIALS = false
MAX_AGE = 10m
```

不要用 `ALLOW_DOMAIN = *` 承载仓库写 API。上例按 Gitea 1.24 的固定配置模板核对： [app.example.ini](https://github.com/go-gitea/gitea/blob/v1.24.0/custom/conf/app.example.ini#L1248-L1275)。Forgejo实例应对照自身版本确认字段；修改服务端配置、重载和防火墙属于 `vps-maintenance` skill。

可以先用预检请求验证：

```bash
curl -i -X OPTIONS https://<forge-domain>/api/v1/user \
  -H 'Origin: https://cms.example.com' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization'
```

响应应只允许预期 CMS origin，而不是返回通配符。

#### 其他 CMS 的边界

- Decap CMS 同样是独立 `/admin` Git CMS，并已有 Forgejo/Gitea backend；不是实际 MkDocs DOM 内编辑： [Decap README](https://github.com/decaporg/decap-cms/blob/bc76c05a80ab70d6b5c7cdaafc7d10cf56939c02/README.md#L15-L36)、 [Forgejo backend package](https://github.com/decaporg/decap-cms/blob/bc76c05a80ab70d6b5c7cdaafc7d10cf56939c02/packages/decap-cms-backend-forgejo/package.json#L1-L14)、 [Gitea backend package](https://github.com/decaporg/decap-cms/blob/bc76c05a80ab70d6b5c7cdaafc7d10cf56939c02/packages/decap-cms-backend-gitea/package.json#L1-L14)。
- Pages CMS 2.1.8 明确面向 GitHub repository；自托管还需要 PostgreSQL 和 GitHub App，不覆盖 Forgejo： [Pages CMS README](https://github.com/hunvreus/pagescms/blob/6f4e860a35d934406580287e7042e5e111e207a1/README.md#L1-L51)。
- TinaCMS 提供 Markdown/MDX/JSON/YAML 的数据层与 React visual editing，需要应用侧 schema/query/preview 集成，不是 MkDocs 即插即用插件： [TinaCMS README](https://github.com/tinacms/tinacms/blob/b636a220d8f88ef50dcd364ae1109e5bbbfb8ddc/README.md#L7-L25)。
- CloudCannon 提供托管式 visual editing，但其开源 Bookshop 组件明确列出的框架不含 MkDocs，不能因此宣称拥有 MkDocs 原生页面编辑： [Bookshop README](https://github.com/CloudCannon/bookshop/blob/c32e8f536073893cb5026c32b23cdc7364bec527/README.adoc#L18-L35)。

### 编辑方案对照

下面是 **2026-08-05** 的采用度快照，只反映当时状态。Stars、下载量和提交次数不能证明安全性或内容保真；它们只用于判断项目规模和维护形态。

| 项目 | 形态 | 快照版本 / 日期 | Stars / Forks | 近月下载 | 维护结构 |
| --- | --- | --- | --: | --: | --- |
| `mkdocs-live-edit-plugin` | 整页源码 | [0.4.1](https://github.com/EddyLuten/mkdocs-live-edit-plugin/releases/tag/v0.4.1) / 2026-03-05 | [37 / 9](https://api.github.com/repos/EddyLuten/mkdocs-live-edit-plugin) | [约846](https://pypistats.org/packages/mkdocs-live-edit-plugin) | 约6名代码贡献者；更新间隔较长 |
| `mkdocs-live-wysiwyg-plugin` | Material WYSIWYG | [0.4.6](https://github.com/samrocketman/mkdocs-live-wysiwyg-plugin/releases/tag/v0.4.6) / 2026-04-06 | [5 / 2](https://api.github.com/repos/samrocketman/mkdocs-live-wysiwyg-plugin) | [约418](https://pypistats.org/packages/mkdocs-live-wysiwyg-plugin) | 基本由1名作者开发，release bot提交很多 |
| `ishan-gaur/mkdocs-liveedit` | 内容块源码 | commit `43a8db5` / 2026-04-07 | [0 / 0](https://api.github.com/repos/ishan-gaur/mkdocs-liveedit) | 无PyPI | 作者明确不面向生产 |
| Sveltia CMS | Git CMS | [0.180.0](https://github.com/sveltia/sveltia-cms/releases/tag/v0.180.0) / 2026-08-05 | [约2.7k / 约180](https://api.github.com/repos/sveltia/sveltia-cms) | [固定窗口约3.7万](https://api.npmjs.org/downloads/point/2026-07-06:2026-08-05/%40sveltia%2Fcms) | 高频维护，核心提交高度集中于主维护者，外部PR作者较多 |
| Decap CMS | Git CMS | [3.15.1](https://github.com/decaporg/decap-cms/releases/tag/decap-cms%403.15.1) / 2026-07-24 | [约19k / 约3.1k](https://api.github.com/repos/decaporg/decap-cms) | 未在此快照统计 | 多年项目，外部社区规模较大 |

WYSIWYG 包依赖 live-edit，因此两者下载量并非独立用户数；CI、缓存和高频 release 也会放大 PyPI 下载。指标应与源码质量、issue响应和升级频率一起判断。

### 复杂语法的保真边界

在任何可视化编辑器中，先做“无修改保存”测试：

```text
打开页面
不修改内容
保存
检查 git diff
```

测试集至少包含：

```text
普通段落与列表
front matter
admonition 与 details
tabs
围栏代码及属性
数学公式
Mermaid
raw HTML
宏与模板表达式
snippets/includes
```

如果无修改保存已经产生大 diff，就不应让该编辑器处理这类页面。可采用：

- 普通页面 rich text，复杂页面 raw；
- 宏注册为可逆 editor component；
- raw HTML只读；
- 先在隔离工作区试验，再决定是否接入正式作者站。

## <a id="runtime"></a>开发站、常驻服务与公网入口

### 开发站与静态站

公开只读站和在线作者站的风险模型不同：

```text
公开只读站
Markdown → mkdocs build → site/ → 静态服务器

在线作者站
Markdown ↔ 编辑 API ↔ mkdocs serve
                    │
                    └─ 认证、授权、写入边界、并发与审计
```

前者没有写 API，攻击面主要在静态服务器和前端资源。后者允许浏览器修改源文件，必须额外考虑认证、路径校验、Origin、WebSocket、文件并发和导航一致性。

在 MkDocs 1.6.1 的 CLI、入门与部署文档中，正式发布路径是构建静态 `site/`，没有把 systemd 常驻 `mkdocs serve` 列为生产方案。常驻 serve 应描述为自定义开发/作者基础设施。

### 开发站与 Pages 行为分离

同一仓库常同时需要：

| 行为                 | 开发作者站           | 静态 Pages      |
| -------------------- | -------------------- | --------------- |
| 构建方式             | `serve`              | `build --clean` |
| livereload           | 开                   | 无              |
| strict               | 通常命令行覆盖为关闭 | 开              |
| 浏览器编辑           | 可选                 | 关闭            |
| `navigation.instant` | 编辑插件不兼容时关闭 | 可开启          |
| `site_url`           | 本地 serve URL       | 注入正式 URL    |
| 未提交文件           | 允许暂态             | 不应进入发布    |

Material 的 instant loading 先读取 `sitemap.xml`，只拦截 sitemap 中的站内 URL： [sitemap 集成](https://github.com/squidfunk/mkdocs-material/blob/6c52ed6289b171a153875491f059a94819ec3e10/src/templates/assets/javascripts/integrations/sitemap/index.ts#L94-L136)。生产构建没有 `site_url` 时 sitemap为空，instant退化为普通完整导航。

instant 会通过 XHR 获取新文档并替换页面区域。自定义 JavaScript不能只监听首次 `DOMContentLoaded`，而应订阅 Material 的 `document$`。某些编辑插件把带顶层 `const`/`let` 的脚本重新注入页面，二次执行会抛 `Identifier has already been declared`；这类插件在 serve 中应关闭 instant，不能只靠 CSS 掩盖。

一份配置配合 Hook 的基本模式：

```python
# mkdocs_ext/runtime_policy.py
_serving = False


def on_startup(*, command, dirty, **kwargs):
    global _serving
    _serving = command == "serve"


def on_config(config, **kwargs):
    if not _serving:
        return config

    features = list(config.theme.get("features") or [])
    config.theme["features"] = [
        feature
        for feature in features
        if not feature.startswith("navigation.instant")
    ]
    return config
```

```yaml
theme:
  name: material
  features:
    - navigation.instant
    - navigation.instant.progress
    - navigation.instant.prefetch

hooks:
  - mkdocs_ext/runtime_policy.py
```

静态 build 保留 features；serve 每次加载配置时由 Hook 摘掉它们。Hook 模块在整个 serve 生命周期中复用，因此 `on_startup` 保存的运行模式可跨重建使用。

正式 URL 由 CI 注入：

```yaml
site_url: !ENV [DOCS_SITE_URL, ""]
```

```bash
DOCS_SITE_URL="https://docs.example.com/project/" \
  mkdocs build --clean
```

### 普通常驻服务

一个归普通用户所有、依赖其工作树和 Python 环境的开发站，适合使用 user service。通用 user service、linger、specifier和日志缓冲原理见同 skill 的 [Service / systemd](service.md)。

目标 unit：

```ini
# ~/.config/systemd/user/mkdocs-preview.service
[Unit]
Description=MkDocs development preview

[Service]
Type=simple
WorkingDirectory=%h/<path-to-project>
Environment=PYTHONUNBUFFERED=1
ExecStart=%h/.local/bin/uv run --group docs mkdocs serve \
  --livereload \
  --no-strict \
  --dev-addr 127.0.0.1:<mkdocs-port>
Restart=on-failure
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
```

systemd 不会把反斜杠自动当 shell 续行；真实 unit 中应把 `ExecStart` 写成单行，或使用systemd允许的行尾反斜杠格式并确保下一行属于同一指令。可读性与兼容性优先时写单行：

```ini
ExecStart=%h/.local/bin/uv run --group docs mkdocs serve --livereload --no-strict --dev-addr 127.0.0.1:<mkdocs-port>
```

启用：

```bash
systemctl --user daemon-reload
systemctl --user enable --now mkdocs-preview.service
journalctl --user -u mkdocs-preview.service -f
```

需要在没有登录 session 时持续运行，检查 user manager 的 linger。不要在 user unit 中依赖 system manager 的 `network-online.target`；user manager看不到那个 target。

`PYTHONUNBUFFERED=1` 让 Python/MkDocs构建日志及时进入 journal。`stdbuf` 修改 libc stdio，对 CPython自己的 `io` 缓冲层无效。

#### serve 使用 `--no-strict`

开发中常有尚未提交的新页面。Git 时间插件可能为这些页面打印 WARNING并回退到当前构建时间。若 serve 沿用 `strict: true`，warning 会让热重建失败。

MkDocs LiveReloadServer用 `_wanted_epoch` 表示已开始构建的版本，用 `_visible_epoch` 表示最后一次完整成功构建。构建失败时只记录错误并继续等待，只有成功路径才推进 visible epoch： [MkDocs 1.6.1 LiveReload](https://github.com/mkdocs/mkdocs/blob/bb7e8b62185b11d9f59bb7f50b13c15134f62f8a/mkdocs/livereload/__init__.py#L203-L225)。普通页面请求会等待两个 epoch 相等： [请求等待源码](https://github.com/mkdocs/mkdocs/blob/bb7e8b62185b11d9f59bb7f50b13c15134f62f8a/mkdocs/livereload/__init__.py#L299-L302)。

因此可能出现：

```text
systemd 显示 active
端口仍在 LISTEN
最近一次重建因 WARNING + strict 失败
HTTP 请求一直等待成功构建
```

开发 serve 使用 `--no-strict` 可以保持预览可用；正式 `mkdocs build` 仍保持 `strict: true`。

#### livereload 静默关闭

MkDocs 1.6.1 把 `--livereload` 与 `--no-livereload` 写入同一个 Click 参数。Click 8.3.x 的共享参数默认值回归曾让未显式传 flag 时得到 `False`；此后 MkDocs会跳过watcher、额外 `watch` 路径和所有插件 `on_serve`： [MkDocs serve 分支](https://github.com/mkdocs/mkdocs/blob/bb7e8b62185b11d9f59bb7f50b13c15134f62f8a/mkdocs/commands/serve.py#L81-L100)、 [Click #3403](https://github.com/pallets/click/issues/3403)。

处置顺序：

```text
确认日志存在 “Watching paths for changes”
显式传 --livereload
约束 Click >=8.4.0
由 lockfile 固定实际版本
```

### 同域编辑网关

WebSocket 是浏览器与服务端之间保持打开的双向连接；WSS 是经过 TLS 加密的 WebSocket。浏览器的 origin 由协议、主机和端口共同组成。HTTPS 作者站中的页面、普通 livereload和编辑 WebSocket最好共用一个 origin：

```text
浏览器 https://<docs-domain>
          │
          ▼
外部 TLS / 认证网关
          │ 单一上游端口
          ▼
本机 HTTP 网关 :<gateway-port>
          ├─ /*                → MkDocs 127.0.0.1:<mkdocs-port>
          └─ /__docs_edit/*    → 编辑后端 127.0.0.1:<edit-port>
```

浏览器地址栏决定 `location.protocol`、Origin和混合内容策略。反向代理是接收客户端请求、再转发给内部后端的网关；它可以修改发给上游的请求头，但不能让公网 HTTPS 页面“认为自己是 localhost”。

本节给出的是完整的进程监督和路由模板，**不包含某个第三方编辑器的适配代码**。编辑后端本身必须已经：

```text
把浏览器客户端改成同域路径
通过固定路径提供WebSocket与可选REST API
满足下一节的文件与认证安全契约
```

未经适配的 `mkdocs-live-edit-plugin==0.4.1` 仍会连接 `ws://host:8484`，不能直接与下面模板组合成公网编辑站。

客户端应根据页面协议选择 WebSocket协议，并使用同域路径：

```javascript
const scheme = location.protocol === "https:" ? "wss:" : "ws:";
const socket = new WebSocket(`${scheme}//${location.host}/__docs_edit/ws`);
```

#### <a id="public-edit-contract"></a>安全契约

本机网关只能连接满足下列条件的编辑后端：

```text
所有路径先 resolve，再确认 relative_to(docs_dir)
只允许明确文件类型，例如 .md
拒绝绝对路径、..、NUL、反斜杠混淆和越界 symlink
写入使用临时文件 + 原子 replace
新建默认不覆盖已有文件
设置单次请求和页面大小上限
验证 WebSocket Origin
所有修改型HTTP接口要求已认证会话、精确Origin和不可预测CSRF token
修改型HTTP接口只接受预期Content-Type和方法，不返回通配符CORS
认证发生在编辑路径之前
错误文本不直接写入 innerHTML
并发保存能检测旧版本或冲突
审计谁在何时修改了什么
会代用户请求外部URL的API限制协议、解析后的IP和重定向目标，阻止SSRF访问私网/link-local/metadata地址
```

未经修补的 `mkdocs-live-edit-plugin==0.4.1` 不满足该契约，不能因为端口藏在反向代理后面就视为安全。

CSRF token可以阻止其他 origin借用户登录态发写请求，但无法抵御同源脚本。允许文档作者提交 raw HTML或 `<script>` 时，作者站渲染出的内容本身可能形成存储型 XSS，再以当前用户身份调用删除/移动接口。多名互不信任作者共用时，应使用独立 CMS origin和经过清理的预览，而不是让可执行文档内容与高权限写 API共用 origin。

#### 本机网关配置

以下 Caddy只承担内部 HTTP 路由，不负责公网 TLS和用户登录。`<gateway-bind-address>` 按部署关系选择：

```text
外部认证网关与本机网关在同一主机 → 127.0.0.1
外部认证网关在另一主机          → 专用私网/mesh地址，并用防火墙或ACL只允许认证网关
```

不要绑定 `0.0.0.0` 后只依赖“用户不知道端口”；否则客户端可绕过外层认证直接访问内部网关。

```caddyfile
{
    admin off
    auto_https off
    servers {
        protocols h1
    }
}

:<gateway-port> {
    bind tcp4/<gateway-bind-address>

    @editor path /__docs_edit /__docs_edit/*
    reverse_proxy @editor 127.0.0.1:<edit-port>

    # 仅在编辑器确实有独立API并已把客户端改为此同域路径时启用
    @editor_api path /__docs_api /__docs_api/*
    reverse_proxy @editor_api 127.0.0.1:<editor-api-port>

    reverse_proxy 127.0.0.1:<mkdocs-port>
}
```

Caddy `reverse_proxy` 会自动处理 WebSocket Upgrade，不需要手写 `Upgrade`/`Connection` header： [Caddy reverse proxy WebSocket](https://github.com/caddyserver/website/blob/9526ade5b764072e5d2f23a546a745b7615e2113/src/docs/markdown/caddyfile/directives/reverse_proxy.md#L397-L420)。

不需要独立 REST API 时删掉 `@editor_api` 两行。不要把随机端口直接暴露给浏览器；应将其改为固定同域路径。

WebSocket `stream_timeout` 会按连接年龄强制断开，包括仍正常工作的连接。只有客户端有可靠自动重连、且确实需要给僵尸连接设置硬上限时才添加。

#### 进程监督脚本

下例先启动 MkDocs和由其插件创建的编辑后端，确认回环端口就绪后再启动本机 Caddy。如果编辑器另起独立 REST API，还应增加对应端口常量、readiness检查和 Caddy路由。没有编辑后端时删除 `EDIT_PORT` 检查和相关路由。

```python
# scripts/mkdocs_gateway.py
from __future__ import annotations

import signal
import socket
import subprocess
import sys
import time
from http.client import HTTPConnection
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CADDYFILE = ROOT / "config" / "mkdocs-gateway.Caddyfile"
GATEWAY_BIND = "<gateway-bind-address>"
GATEWAY_PORT = <gateway-port>
MKDOCS_PORT = <mkdocs-port>
MKDOCS_HEALTH_PATH = "/"  # site_url 有子路径时改成 "/project/"
EDIT_PORT = <edit-port>


def ensure_port_free(host: str, port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError as error:
            raise RuntimeError(f"{host}:{port} is already in use") from error


def wait_for_port(process: subprocess.Popen, port: int, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"child exited before opening {port}: {process.returncode}"
            )
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.2)
    raise TimeoutError(f"port {port} did not open within {timeout:g}s")


def wait_for_http(
    process: subprocess.Popen,
    port: int,
    path: str,
    timeout: float,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"child exited before HTTP was ready: {process.returncode}"
            )
        connection = HTTPConnection("127.0.0.1", port, timeout=1)
        try:
            connection.request("HEAD", path)
            response = connection.getresponse()
            response.read()
            if 200 <= response.status < 400:
                return
        except OSError:
            pass
        finally:
            connection.close()
        time.sleep(0.2)
    raise TimeoutError(f"HTTP on {port} was not ready within {timeout:g}s")


def terminate(processes: list[subprocess.Popen]) -> None:
    for process in processes:
        if process.poll() is None:
            process.terminate()
    deadline = time.monotonic() + 10
    for process in processes:
        if process.poll() is not None:
            continue
        try:
            process.wait(timeout=max(0.1, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            process.kill()
    for process in processes:
        if process.poll() is None:
            process.wait()


def main() -> int:
    ensure_port_free(GATEWAY_BIND, GATEWAY_PORT)
    ensure_port_free("127.0.0.1", MKDOCS_PORT)
    ensure_port_free("127.0.0.1", EDIT_PORT)

    subprocess.run(
        [
            "/usr/bin/caddy",
            "validate",
            "--config",
            str(CADDYFILE),
            "--adapter",
            "caddyfile",
        ],
        cwd=ROOT,
        check=True,
    )

    mkdocs = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "mkdocs",
            "serve",
            "--livereload",
            "--no-strict",
            "--dev-addr",
            f"127.0.0.1:{MKDOCS_PORT}",
        ],
        cwd=ROOT,
    )
    processes = [mkdocs]

    def stop(_signum, _frame):
        terminate(processes)
        raise SystemExit(0)

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    try:
        wait_for_http(mkdocs, MKDOCS_PORT, MKDOCS_HEALTH_PATH, 60)
        wait_for_port(mkdocs, EDIT_PORT, 15)

        caddy = subprocess.Popen(
            [
                "/usr/bin/caddy",
                "run",
                "--config",
                str(CADDYFILE),
                "--adapter",
                "caddyfile",
            ],
            cwd=ROOT,
        )
        processes.append(caddy)

        while True:
            for process in processes:
                status = process.poll()
                if status is not None:
                    return status
            time.sleep(0.5)
    finally:
        terminate(processes)


if __name__ == "__main__":
    raise SystemExit(main())
```

脚本先确认端口未被其他进程占用，再用真实 HTTP请求确认 MkDocs就绪；这避免“端口本来就被无关服务监听，supervisor却误判启动成功并把流量代理过去”。编辑端口最好也使用协议级健康检查，例如完成 WebSocket握手并验证预期 greeting；上例只给通用 TCP检查，接入具体编辑器时应替换。

对应 user service：

```ini
# ~/.config/systemd/user/mkdocs-author.service
[Unit]
Description=MkDocs authenticated authoring service

[Service]
Type=simple
WorkingDirectory=%h/<path-to-project>
Environment=PYTHONUNBUFFERED=1
ExecStart=%h/.local/bin/uv run --locked --group docs python scripts/mkdocs_gateway.py
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
```

外部 TLS/认证网关把整个 `<docs-domain>` 转到 `<gateway-port>`，且认证必须发生在普通页面、编辑 WebSocket和辅助API之前。具体证书、OAuth、caddy-security或服务器加固由 `vps-maintenance` skill 负责；EasyTier、端口转发、WSL/宿主链路、来源ACL和路由由 `network` skill 负责。本文只定义上游契约。

#### 验收

```bash
# MkDocs与编辑后端应是回环；网关应是回环或受限私网地址
ss -ltnp | grep -E ':<gateway-port>|:<mkdocs-port>|:<edit-port>'

# 普通页面；地址使用实际 GATEWAY_BIND
curl -fsS http://<gateway-bind-address>:<gateway-port>/ >/dev/null

# 上游健康
curl -fsS http://127.0.0.1:<mkdocs-port>/ >/dev/null
```

编辑 API 还应有自动化安全测试：

```text
读取合法 docs/page.md → 成功
读取 ../config.toml → 403或协议级拒绝
读取 docs/中的越界symlink → 拒绝
写入非.md文件 → 拒绝
Origin=https://evil.example → WebSocket 1008或握手拒绝
未登录访问编辑路径 → 401/302，不应到达编辑后端
无修改保存 → git diff为空
```

### 公网入口的应用契约

公网入口只需理解以下应用层事实：

```text
静态只读站：只代理/托管 site/
作者站：认证覆盖页面、编辑WebSocket和辅助API
浏览器只访问一个HTTPS origin
所有内部后端绑定回环
外部只开放一个明确网关端口
```

隐藏 URL、非常用端口或“不告诉别人地址”都不是认证。若站点包含私密资料，必须由真正的身份验证控制访问。

## <a id="publishing"></a>发布、Git 历史与质量闸门

### 静态发布

`site/` 是生成物，不是内容真相源。正式发布应从干净的源工作树重新构建：

```bash
uv lock --check
uv sync --locked --group docs
DOCS_SITE_URL="https://docs.example.com/project/" \
  uv run --no-sync mkdocs build --clean
```

CI 中要区分两类依赖：

```text
runner镜像：预热缓存，减少安装时间
项目lockfile：版本真相源，决定实际构建环境
```

即使镜像预装了 MkDocs，也应从 lockfile同步；镜像漏包只应造成额外安装，不应造成“本地能建、CI提示插件不存在”。

普通 runner 的典型构建步骤：

```yaml
- name: Install documentation dependencies
  run: |
    uv lock --check
    uv sync --locked --group docs

- name: Build
  env:
    DOCS_SITE_URL: https://docs.example.com/project/
  run: uv run --no-sync mkdocs build --clean
```

`uv lock --check` 验证 lockfile 与项目声明一致；`uv sync --locked` 在不允许改动lockfile的前提下同步环境；`--no-sync` 让后续命令直接使用刚同步好的环境。三者语义可用 `uv lock --help` 和 `uv sync --help` 当场核验。`--frozen` 只表示不更新lockfile，不会证明它仍与项目声明一致。

若使用预热镜像中的独立 `/opt/mkdocs` 环境，必须明确声明这是 runner镜像契约，再从lockfile导出并同步到那个解释器；不要在通用示例中假定该路径存在。

具体 Forgejo Actions、发布 token、git-pages协议和分支操作属于 `git` skill。

发布后不要只相信上传命令的退出码。至少检查：

```bash
page="$(mktemp)"
trap 'rm -f "$page"' EXIT

curl -fsS https://docs.example.com/project/ > "$page"
grep -q '<title>Example Documentation' "$page"

curl -fsS https://docs.example.com/project/sitemap.xml \
  | grep -q '<loc>'

asset="$(
  sed -n 's/.*href="\([^"]*assets\/stylesheets\/main[^"]*\.css\)".*/\1/p' \
    "$page" |
  head -n 1
)"
test -n "$asset"
curl -fsS "https://docs.example.com/project/${asset#./}" >/dev/null
```

Material资源文件名带内容 hash，因此应从首页提取实际 CSS/JS 地址，而不是写死 `main.css`。

#### 未提交文件

`mkdocs build` 读取工作树，不只读取 Git commit。官方 `gh-deploy` 文档也明确提醒：未跟踪和未提交文件会进入发布产物： [MkDocs 部署说明](https://github.com/mkdocs/mkdocs/blob/bb7e8b62185b11d9f59bb7f50b13c15134f62f8a/docs/user-guide/deploying-your-docs.md#L17-L37)。

正式发布前应有独立检查：

```bash
test -z "$(git status --porcelain)" ||
  { echo "working tree is not clean" >&2; exit 1; }

test -z "$(
  git ls-files --others --ignored --exclude-standard -- docs/
)" || {
  echo "ignored files under docs/ would enter the build" >&2
  exit 1
}
```

`git status --porcelain` 默认不列 ignored文件，但 MkDocs仍会读取 `docs_dir` 中的ignored文件。最稳的发布环境是 CI新鲜 checkout；确实需要的 ignored派生物应由受控构建步骤显式生成或复制，而不是碰巧留在工作树。

这些检查和 MkDocs `strict` 是不同闸门：strict管构建日志，Git检查管输入是否已经进入版本历史。

### 页面修改时间

[`mkdocs-git-revision-date-localized-plugin` 1.5.3](https://github.com/timvink/mkdocs-git-revision-date-localized-plugin/releases/tag/v1.5.3) 可把 Git 创建/修改时间注入页面：

```yaml
plugins:
  - git-revision-date-localized:
      type: timeago
      timezone: Asia/Shanghai
      locale: zh
      enable_creation_date: true
      fallback_to_build_date: true
```

需要区分：

| 页面状态               | 插件显示                                     |
| ---------------------- | -------------------------------------------- |
| 已提交页面有工作区修改 | 最后一次提交时间                             |
| 新页面完全没有 Git log | 当前构建时间，并打印 no git logs             |
| Git不可用或命令失败    | 由 `fallback_to_build_date` 决定回退还是失败 |

“新页面无 Git log”分支不受 `fallback_to_build_date` 控制，而是直接回退当前时间并记录消息： [1.5.3 util.py](https://github.com/timvink/mkdocs-git-revision-date-localized-plugin/blob/30e58767a16cd9ec1dd2669f0bdc1af8630af18c/src/mkdocs_git_revision_date_localized_plugin/util.py#L177-L185)。

插件自己的 `strict` 决定这些消息是 WARNING还是 INFO；MkDocs全局 strict 再决定 WARNING是否中止构建： [插件日志等级](https://github.com/timvink/mkdocs-git-revision-date-localized-plugin/blob/30e58767a16cd9ec1dd2669f0bdc1af8630af18c/src/mkdocs_git_revision_date_localized_plugin/util.py#L66-L75)。

开发 serve 使用 `--no-strict` 可以容忍新页面；正式构建仍应要求页面进入 Git。

#### 重命名

`enable_git_follow: true` 会把 Git `--follow` 传给单文件历史查询，尝试跨重命名追踪。复杂迁移或浅克隆中可能出现“创建时间晚于/早于最后修改时间”的异常提示。若项目不需要跨重命名创建时间，可设置：

```yaml
enable_git_follow: false
```

先通过 `git log --follow -- <page>` 与 `git log -- <page>` 对照，再决定是否关闭，不要为了消除一条 warning盲改。

#### 浅克隆

CI只拉取最近 N 个提交时称为浅克隆，更早的历史不可见。Git可能把浅克隆边界当作根提交，导致老页面获得偏新的“创建时间”。历史展示需要多深，checkout就至少要拉多深：

```yaml
- uses: actions/checkout@v4
  with:
    fetch-depth: 400
```

需要绝对创建时间时使用完整历史：

```yaml
fetch-depth: 0
```

代价是 checkout时间和仓库传输量。

### 最近更新页面

“每页页脚显示自己的修改时间”与“列出全站最近修改的页面”是两个需求。

`mkdocs-git-latest-changes-plugin` 0.0.23 提供现成表格，但其实现：

1. `git ls-files` 列出目录里的所有跟踪文件；
2. 对每个文件执行一次 `git log --max-count=1`；
3. 收齐后排序；
4. 最后才应用 `history_limit`。

源码见 [git_adapter.py](https://github.com/tombreit/mkdocs-git-latest-changes-plugin/blob/19902ced1e4100b6cbaaeac9e8504c66e5a0ebeb/src/mkdocs_git_latest_changes_plugin/git_adapter.py#L119-L190)。

因此 `history_limit: 20` 不会减少 Git调用数；`limit_to_docs_dir` 也只限制目录，不会排除 PDF、CSV、图片和脚本。资源很多的文档仓库会被资产变更刷屏。

该版本还会持久执行：

```python
repo.config_writer().set_value("core", "quotepath", "false").release()
```

这会修改仓库 `.git/config`： [源码](https://github.com/tombreit/mkdocs-git-latest-changes-plugin/blob/19902ced1e4100b6cbaaeac9e8504c66e5a0ebeb/src/mkdocs_git_latest_changes_plugin/git_adapter.py#L84-L106)。

更适合“最近修改页面”的算法是一次遍历提交：

```bash
git -c core.quotepath=false log \
  --max-count=400 \
  --no-renames \
  --name-status \
  --date=iso-strict \
  --pretty=format:'%x1e%h%x1f%cI%x1f%s' \
  -- docs/
```

处理规则：

```text
按提交时间倒序读取记录
只接受 docs_dir 下以 .md 结尾的路径
跳过 D 删除记录
跳过磁盘上已不存在的路径
同一页面第一次出现时记录，后续忽略
收集到目标行数后停止
页面标题优先取 front matter title，其次取第一个 H1
生成相对 Markdown 链接，让 MkDocs参与死链校验
```

`--no-renames` 把重命名拆成删除旧路径和新增新路径；删除被跳过，新路径作为当前页面记录。命令级 `-c core.quotepath=false` 只影响本次进程，不污染仓库配置。

这种方法的复杂度约为扫描提交数，而不是“文件数 × 每个文件向后搜索的深度”。

只展示 Git记录的变化时：

- 未跟踪页面不出现；
- 已跟踪但未提交修改仍显示上次 commit；
- staged但从未提交的新页没有记录。

这正是“版本历史”与“当前工作区变化”的语义区别。

### 校验

一套实用的发布闸门：

```text
工作树必须干净
uv/包管理器使用 frozen lock
mkdocs build --clean
strict=true
重要 validation 项提升为 warn
snippets 检查路径
构建产物首页、sitemap和资源可访问
```

链接检查要区分：

```text
源页面不存在
目标锚点不存在
绝对链接
MkDocs无法识别的链接
页面未进入导航
```

它们默认不全是 WARNING，不能只写 `strict: true` 就认为所有问题已覆盖。

### 内容可见性

静态 Pages 的隐藏子路径不是认证。URL可能通过浏览器历史、Referer、分享按钮、日志、sitemap或误发链接泄漏。

不同需求对应不同措施：

| 需求                     | 合适机制              |
| ------------------------ | --------------------- |
| 不希望搜索引擎收录       | `noindex`、robots规则 |
| 不希望外链带出完整路径   | Referrer-Policy       |
| 不希望普通访问者读取     | 真正身份认证          |
| 临时、可撤销的单文件分享 | 带过期时间的签名 URL  |

`noindex` 不阻止知道 URL 的人访问。私密资料应从公开 Pages 构建中排除，或放到认证站。

Material 的 `search.share` 会提供搜索结果分享功能；站点路径本身具有保密含义时应关闭：

```yaml
theme:
  features:
    - search.suggest
    - search.highlight
    # 不启用 search.share
```

## <a id="maintenance"></a>诊断与维护

### 跨层诊断顺序

文档站不可用时，不要直接修改最外层代理。按数据路径逐层验证：

```text
浏览器
  ↓
外部 TLS / 认证入口
  ↓
组网或端口转发
  ↓
本机网关
  ↓
MkDocs HTTP / 编辑 WebSocket / 辅助 API
  ↓
源文件与 Git
```

每层用最小证据：

```bash
# 本机监听
ss -ltnp

# MkDocs后端
curl -fsS http://127.0.0.1:<mkdocs-port>/ >/dev/null

# 本机网关
curl -fsS http://127.0.0.1:<gateway-port>/ >/dev/null

# 服务状态和退出原因
systemctl --user status <unit>
journalctl --user -u <unit> --since "-10 min"

# 构建是否能独立完成
uv run --group docs mkdocs build --clean

# 工作树和依赖
git status --short
uv lock --check
```

出现端口 LISTEN不代表服务能返回页面；出现 systemd active也不代表最近一次 MkDocs 构建成功。

### 版本升级

升级前建立一个小型兼容矩阵：

```text
clean build
serve初始构建
文件变化后的livereload
Material instant navigation
数学公式与Mermaid重渲染
macros和自定义Hook
浏览器编辑读/写/拒绝越界
strict warning计数
Pages子路径
```

内部API补丁必须精确 pin。上游升级时若替换了 JavaScript字符串、DOM类名或方法签名，安全 Hook可能静默不再生效；测试应验证目标行为，而不是只验证 import成功。

### 构建性能

先量 clean build，再决定优化：

```bash
/usr/bin/time -f 'wall=%e user=%U sys=%S maxrss=%MKB' \
  uv run --group docs mkdocs build --clean
```

常见成本：

```text
搜索索引
Git逐文件历史查询
宏读取/计算
复现包压缩
大图片或报告复制
外部进程持续写入watch目录
每页内联大型编辑器JavaScript
```

高频更新、自包含的 HTML 报告如果不需要 Markdown渲染，可由静态服务器直接映射目录，不进入 `docs_dir` watcher，避免每次更新触发全站重建。

复现包等派生产物可按输入内容哈希缓存；没有输入变化时复用 ZIP，而不是每次 clean build 重新压缩。

### 配置清理

定期检查：

```text
主题 feature是否具备所需repo/site配置
Markdown扩展是否有实际语法使用
extra_javascript是否为空操作或重复初始化
字体、KaTeX、Mermaid等外部资源是否锁精确版本
watch是否重复包含docs_dir
插件顺序是否有两个组件同时改nav
CI镜像版本是否只是缓存而非真相源
注释是否仍描述当前架构
```

不要仅因为配置“没有报错”就保留。死 feature和过期注释会让下一次排障建立在错误心智模型上。
