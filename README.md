# Skills

这是一个 Agent Skills 仓库，收集我常用的一些技能包，方便给 AI 增加文档处理、前端设计和办公文件处理能力。

## 可用的 Skills

- `docx`：处理 Word 文档，包括编辑、批注、接受修订和校验。
- `pdf`：处理 PDF，包括表单分析、字段提取、填写和图片转换。
- `xlsx`：处理 Excel 文件，包括重算和基础校验。
- `pptx`：处理 PowerPoint，包括清理、加页、缩略图和结构处理。
- `frontend-design`：生成更有设计感的前端界面与页面方案。
- `doc-coauthoring`：用于结构化文档协作与共同编写流程。
- `qiuzhi-skill-creator`：用于创建和打包新的 skill。

## AGENTS.md

[AGENTS.md](AGENTS.md) 里放的是一个我自己常用的 AI 全局规则，主要是我常用的执行偏好，对 GitHub Copilot CLI 和 GitHub Copilot in VS Code 完美适用。例如：

- Python 环境优先级
- 遇到不明确情况时优先 askQuestion
- Git 提交相关约束
- tools、skills 和 subagents 的使用习惯

如果你想让 Claude Code 或其他基于 Claude 的工具也遵循相同的规则，可以通过软链接实现：

```bash
ln -s AGENTS.md CLAUDE.md
```

这样 CLAUDE.md 会指向 AGENTS.md，保持规则统一，只需维护一份文件。

## 使用 Vercel Labs 的 `skills` 命令行工具安装 skills

- 安装本仓库 skills：`bunx skills add TMYTiMidlY/skills`
- 查看可安装内容：`bunx skills add TMYTiMidlY/skills --list`
- 更新已安装 skills：`npx skills update`
- 常用选项：`-g` 全局安装，`--skill <name>` 安装指定 skill，`-y` 跳过确认。

## 使用方式

- 每个 skill 目录下都有一个 `SKILL.md`，用于说明这个 skill 适合解决什么问题。
- 如果某个 skill 带有 `scripts/` 目录，通常表示里面附带了可直接运行的脚本。
- 如果你想自己做一个新 skill，可以参考 `qiuzhi-skill-creator`。

## 许可

各个 skill 可能有不同的许可证，请分别查看对应目录中的 `LICENSE` 或 `LICENSE.txt`。
