> 本文是 `reference/code-signing.md` 的中文翻译副本，随上游同步需重译；行为以英文原文为准。

# 代码签名政策

本页介绍 Worktrunk 的**代码签名政策**。其中说明了签名对象、所用证书、签名流水线的工作方式，以及每个版本由谁授权发布。本文既用于向用户记录这一流程，也用于满足 [SignPath Foundation](https://signpath.org/) 开源代码签名计划的透明度要求。

## 签名为何重要

Worktrunk 的 Windows 二进制文件（`wt.exe` 和 `git-wt.exe`）是小型原生可执行文件。Microsoft Defender 的机器学习启发式检测经常把这种形态的未签名原生可执行文件标记为通用威胁（例如 `Trojan:Win32/Wacatac.B!ml`）——这是一种由*缺少可信签名*引起的误报，并非代码中的任何内容所致。有效的 [Authenticode](https://learn.microsoft.com/en-us/windows-hardware/drivers/install/authenticode) 签名能为 Defender 云端提供可供信任的已签名对象，从而阻止这类误报。对 Windows 构件签名是持久的解决办法。

macOS 和 Linux 发布构件、crates.io 源码分发包以及 `cargo install` 构建不受此政策影响——`cargo install` 会在本地从源码编译，绝不会下载预构建构件。

## 签名证书

> 免费代码签名由 [SignPath.io](https://signpath.io/) 提供，证书由 [SignPath Foundation](https://signpath.org/) 提供。

证书的私钥在 SignPath 的硬件安全模块（HSM）上生成并保存；任何维护者都不会持有私钥。签名只能通过 SignPath 的服务完成，该服务由 Worktrunk 的发布流水线调用。

## 签名对象

- `wt.exe` 和 `git-wt.exe`——每个 [GitHub Release](https://github.com/max-sixty/worktrunk/releases) 中 `x86_64-pc-windows-msvc` 发布归档所包含、并通过 [winget](https://github.com/microsoft/winget-pkgs) 分发（`winget install max-sixty.worktrunk`）的 Windows 二进制文件。`git-wt.exe` 是作为 git 子命令构建的同一个程序。

除此之外，此政策不对任何其他内容签名。已签名构件只包含从本仓库构建的代码；其中捆绑的任何第三方库均未经修改。

## 构建与签名流水线

1. 每个版本都通过向 [`max-sixty/worktrunk`](https://github.com/max-sixty/worktrunk) 推送版本 tag 来触发。不会从任何其他来源构建版本。
2. [`release` workflow](https://github.com/max-sixty/worktrunk/blob/main/.github/workflows/release.yaml) 使用 [cargo-dist](https://axodotdev.github.io/cargo-dist/)，在 GitHub 托管的 runner 上仅从带 tag 的提交构建各平台二进制文件。
3. Windows 二进制文件通过 [SignPath GitHub Action](https://github.com/SignPath/github-action-submit-signing-request) 提交给 SignPath 签名。签名后的二进制文件会返回 workflow，并发布到发布归档中。
4. 构建可从公开源码复现：workflow、工具链固定配置（[`rust-toolchain.toml`](https://github.com/max-sixty/worktrunk/blob/main/rust-toolchain.toml)）和发布配置（[`dist-workspace.toml`](https://github.com/max-sixty/worktrunk/blob/main/dist-workspace.toml)）都在本仓库中追踪。

## 项目角色

Worktrunk 遵循 SignPath 的团队模型：

| 角色 | 职责 | 人员 |
|------|----------------|-----|
| **作者** | 提交代码并为版本打 tag 的可信开发者 | [@max-sixty](https://github.com/max-sixty) |
| **审查者** | 在可信集合之外的贡献能够发布之前对其进行审查 | [@max-sixty](https://github.com/max-sixty) |
| **批准者** | 授权每个版本的签名请求 | [@max-sixty](https://github.com/max-sixty) |

所有拥有签名权限的维护者都在其 GitHub 和 SignPath 账户上使用多因素身份验证。

## 发布批准

每个签名请求在应用证书之前都需要由批准者**手动批准**——签名绝不会完全自动化。只有在批准者确认构件是从本仓库中带 tag 的提交构建之后，版本才会得到签名。

## 隐私

Worktrunk 是一款本地优先的命令行工具。它不进行遥测，不收集分析数据，也不传输用户数据。仅当用户运行的命令需要网络访问时才会联网（例如为 `wt list --full` 获取 CI 状态）；[FAQ](https://worktrunk.dev/faq/) 和内联文档准确说明了联网时机。签名后的二进制文件不会增加任何形式的数据收集。

## 报告问题

如果你认为已签名的 Worktrunk 二进制文件遭到篡改，或者官方发布构件触发了防病毒软件检测，请[提交 issue](https://github.com/max-sixty/worktrunk/issues)。如果怀疑是 Defender 误报，也可以通过 [Windows Defender submission portal](https://www.microsoft.com/en-us/wdsi/filesubmission) 向 Microsoft 报告该文件（选择 *“I believe this file is safe”*），这会为所有用户更正云端定义。
