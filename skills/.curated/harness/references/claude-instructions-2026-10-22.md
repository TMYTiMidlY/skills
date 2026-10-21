# Claude Code 指令发现文档节选（2026-10-22）

本页保存官方在线文档中与共享规则安装直接相关的节选。采集日期为 2026-10-22；来源页没有版本化地址，原文后续可能更新。以下是文档证据，不代表对所有 Claude 运行环境的实测。

## <a id="user-instructions"></a>用户级入口

官方 memory 文档的指令位置表列出：

> **User instructions** — `~/.claude/CLAUDE.md` — Personal preferences for all projects.

官方目录文档说明配置根目录可重定位：

> If you set `CLAUDE_CONFIG_DIR`, every `~/.claude` path on this page lives under that directory instead.

> 来源：[指令位置](https://code.claude.com/docs/en/memory#choose-where-to-put-claude-md-files)、[Claude 配置目录](https://code.claude.com/docs/en/claude-directory)。

## <a id="shared-file"></a>共享正文与软链接

官方 memory 文档在跨工具共享文件的章节中写道：

> If you don't need Claude-specific content, a symlink also works:
>
> ```bash
> ln -s AGENTS.md CLAUDE.md
> ```

这是同目录文件名兼容示例。跨项目安装仍需把入口放在用户级发现位置；Windows 的文件 symlink 权限与 Git 的 `core.symlinks` 会影响创建和检出。该页还限定了网络路径链接，以及 Cowork 中指向工作目录外的用户级链接；选择安装方案时应一并核对这些限制。

> 来源：[跨编码工具共享文件](https://code.claude.com/docs/en/memory#share-one-file-with-other-coding-tools)、[外部路径与 Cowork 限制](https://code.claude.com/docs/en/memory#import-additional-files)。
