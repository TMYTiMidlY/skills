# Lean 4 VS Code 扩展 Setup Guide（正文中译）

Lean 4 官方 VS Code 扩展（`leanprover.vscode-lean4`）首次启动时弹出 Setup Guide 向导，依次引导安装 Lean 工具链（Elan、Git 等）、创建或打开项目、选择学习文档和排障。向导各页的正文存放在扩展仓库的 `vscode-lean4/media/` 目录，共六个文件：

- [guide-installLean-windows.md](https://github.com/leanprover/vscode-lean4/blob/v0.0.240/vscode-lean4/media/guide-installLean-windows.md) —— 安装 Lean（Windows 页）
- [guide-installLean-linux.md](https://github.com/leanprover/vscode-lean4/blob/v0.0.240/vscode-lean4/media/guide-installLean-linux.md) —— 安装 Lean（Linux 页）
- [guide-installLean-mac.md](https://github.com/leanprover/vscode-lean4/blob/v0.0.240/vscode-lean4/media/guide-installLean-mac.md) —— 安装 Lean（macOS 页）
- [guide-setupProject.md](https://github.com/leanprover/vscode-lean4/blob/v0.0.240/vscode-lean4/media/guide-setupProject.md) —— 创建 / 打开项目
- [guide-documentation.md](https://github.com/leanprover/vscode-lean4/blob/v0.0.240/vscode-lean4/media/guide-documentation.md) —— 学习文档
- [guide-help.md](https://github.com/leanprover/vscode-lean4/blob/v0.0.240/vscode-lean4/media/guide-help.md) —— 问题与排障

以下是六页正文的完整中文翻译，每节末尾以引用块附英文原文；两版均核对自 v0.0.240（当前 master 与该 tag 逐字节一致）。

> 向导的外壳——左侧步骤栏、按钮、安装进度、版本检测结果——由扩展代码动态生成，不在这六个文件里；扩展的完整使用手册是独立的 [manual.md](https://github.com/leanprover/vscode-lean4/blob/v0.0.240/vscode-lean4/manual/manual.md)（约 75 KB），不属于向导。原文里 `command:` 开头的链接是 VS Code 内部命令，只在向导界面内可点，中译里此类链接或只保留文字、或改指对应的公开页面；`${elanStableChannel}` 是安装时运行时填充的工具链版本占位符。原文引用的两张截图（`open-local-project_show-setup_buttons.png`、`troubleshooting.png`）是 `media/` 目录下的本地图片，本文未内嵌，引用块中保留其原文行。

## <a id="install-windows"></a>安装 Lean —— Windows

### 将要安装的组件

点击**此链接**或本步骤的 “Install Lean” 按钮后，将自动安装以下组件：

- **Elan** —— Lean 的版本管理器，自动管理所有不同版本的 Lean，并确保打开项目时使用正确的版本。
- **Git** —— 常用的版本控制系统。Lean 用它来管理 Lean 形式化包和软件包的不同版本，也可用于 Lean 项目的协作开发。

已安装的组件将被跳过。

### 安装过程细节

自动安装将运行一个脚本来安装 Elan 和 Git。

在支持包管理器 **winget** 的较新 Windows 系统上，将执行以下脚本：

```powershell
# 使用 winget 安装 Git
winget install -e --id Git.Git --source winget --silent --accept-package-agreements --accept-source-agreements --disable-interactivity
# 下载 Elan 安装脚本（elan-init.ps1）并运行。Elan 将安装到 %USERPROFILE%\.elan
$installCode = (Invoke-WebRequest -Uri "https://elan.lean-lang.org/elan-init.ps1" -UseBasicParsing -ErrorAction Stop).Content
$installer = [ScriptBlock]::Create([System.Text.Encoding]::UTF8.GetString($installCode))
Set-ExecutionPolicy -ExecutionPolicy Unrestricted -Scope Process
& $installer -NoPrompt 1 -DefaultToolchain ${elanStableChannel}
```

在不支持 winget 的较旧 Windows 系统上，将改为执行以下脚本：

```powershell
# 从 git-for-windows 的 GitHub Releases 下载安装器并运行
$gitInstallerUrl = "https://github.com/git-for-windows/git/releases/download/v2.50.1.windows.1/Git-2.50.1-64-bit.exe"
$installDir = "%TEMP%\lean4-vscode-extension"
$gitInstallerLoc = "$installDir\GitInstaller.exe"
New-Item -ItemType Directory -Path $installDir -Force
Invoke-WebRequest -Uri $gitInstallerUrl -OutFile $gitInstallerLoc
& $gitInstallerLoc /VERYSILENT /NORESTART /SP-
# 下载 Elan 安装脚本（elan-init.ps1）并运行。Elan 将安装到 %USERPROFILE%\.elan
$installCode = (Invoke-WebRequest -Uri "https://elan.lean-lang.org/elan-init.ps1" -UseBasicParsing -ErrorAction Stop).Content
$installer = [ScriptBlock]::Create([System.Text.Encoding]::UTF8.GetString($installCode))
Set-ExecutionPolicy -ExecutionPolicy Unrestricted -Scope Process
& $installer -NoPrompt 1 -DefaultToolchain ${elanStableChannel}
```

### 受限环境

如果你处于受限环境（例如受管控的大学机房电脑），无法安装 Git 和 curl 且它们未预先安装，上述安装脚本可能失败。这种情况下目前没有办法在本地安装试用 Lean 4。如果你仍想体验，可以阅读 [Mathematics in Lean](https://leanprover-community.github.io/mathematics_in_lean/) 并用 [Gitpod 托管的在线 Lean 4 环境](https://gitpod.io/#/https://github.com/leanprover-community/mathematics_in_lean)做书里的练习（需要注册 GitHub 账号）；也可以玩[自然数游戏（NNG4）](https://adam.math.hhu.de/#/g/hhu-adam/NNG4)，或在浏览器里试用[单文件版 Lean 4](https://live.lean-lang.org/)。

> **原文 · [guide-installLean-windows.md](https://github.com/leanprover/vscode-lean4/blob/v0.0.240/vscode-lean4/media/guide-installLean-windows.md)：**
>
> ## Installed Components
> The following components are automatically installed when clicking [this link](command:lean4.setup.installLean) or the 'Install Lean' button associated with this step:
> - [Elan](https://github.com/leanprover/elan) is Lean's version manager and automatically manages all the different versions of Lean and ensures that the correct version is used when opening a project.
> - [Git](https://git-scm.com/) is a commonly used [Version Control System](https://en.wikipedia.org/wiki/Version_control) that is used by Lean to help manage different versions of Lean formalization packages and software packages. It can also be used to collaborate on Lean projects.
>
> Components that are already installed will be skipped.
>
> ## Installation Procedure Details
> The automatic installation will run a script to install Elan and Git.
>
> On newer Windows systems that support the package manager [winget](https://learn.microsoft.com/en-us/windows/package-manager/winget/), the following script will be executed:
> ```powershell
> # Install Git using `winget`.
> winget install -e --id Git.Git --source winget --silent --accept-package-agreements --accept-source-agreements --disable-interactivity
> # Download the Elan installation script at https://github.com/leanprover/elan/blob/master/elan-init.ps1 and run it. Elan will be installed to `%USERPROFILE%\.elan`.
> $installCode = (Invoke-WebRequest -Uri "https://elan.lean-lang.org/elan-init.ps1" -UseBasicParsing -ErrorAction Stop).Content
> $installer = [ScriptBlock]::Create([System.Text.Encoding]::UTF8.GetString($installCode))
> Set-ExecutionPolicy -ExecutionPolicy Unrestricted -Scope Process
> & $installer -NoPrompt 1 -DefaultToolchain ${elanStableChannel}
> ```
>
> On older Windows systems that do not support the package manager [winget](https://learn.microsoft.com/en-us/windows/package-manager/winget/), the following script will be executed instead:
> ```powershell
> # Install Git by downloading the installer from https://github.com/git-for-windows/git/releases/download/v2.50.1.windows.1/Git-2.50.1-64-bit.exe and running it.
> $gitInstallerUrl = "https://github.com/git-for-windows/git/releases/download/v2.50.1.windows.1/Git-2.50.1-64-bit.exe"
> $installDir = "%TEMP%\lean4-vscode-extension"
> $gitInstallerLoc = "$installDir\GitInstaller.exe"
> New-Item -ItemType Directory -Path $installDir -Force
> Invoke-WebRequest -Uri $gitInstallerUrl -OutFile $gitInstallerLoc
> & $gitInstallerLoc /VERYSILENT /NORESTART /SP-
> # Download the Elan installation script at https://github.com/leanprover/elan/blob/master/elan-init.ps1 and run it. Elan will be installed to `%USERPROFILE%\.elan`.
> $installCode = (Invoke-WebRequest -Uri "https://elan.lean-lang.org/elan-init.ps1" -UseBasicParsing -ErrorAction Stop).Content
> $installer = [ScriptBlock]::Create([System.Text.Encoding]::UTF8.GetString($installCode))
> Set-ExecutionPolicy -ExecutionPolicy Unrestricted -Scope Process
> & $installer -NoPrompt 1 -DefaultToolchain ${elanStableChannel}
> ```
>
> ## Restricted Environments
> If you are in a restricted environment where you cannot install Git or curl and they are not already installed, for example a restricted university computer, then the installation script above may fail. In this case, there is currently no way to try Lean 4 with a local installation. If you want to try out Lean 4 regardless, you can read [Mathematics in Lean](https://leanprover-community.github.io/mathematics_in_lean/) and do the exercises with [an online instance of Lean 4 hosted using Gitpod](https://gitpod.io/#/https://github.com/leanprover-community/mathematics_in_lean). Doing so requires creating a GitHub account. Alternatively, you can also [play the Natural Number Game](https://adam.math.hhu.de/#/g/hhu-adam/NNG4) or [try a single-file version of Lean 4 in your web browser](https://live.lean-lang.org/).

## <a id="install-linux"></a>安装 Lean —— Linux

### 将要安装的组件

点击**此链接**或本步骤的 “Install Lean” 按钮后，将自动安装以下组件：

- **Elan** —— Lean 的版本管理器，自动管理所有不同版本的 Lean，并确保打开项目时使用正确的版本。
- **Git** —— 常用的版本控制系统。Lean 用它管理形式化包和软件包的版本，也可用于协作开发。
- **curl** —— 小型数据传输工具。Lean 在管理形式化包和软件包时用它下载文件。

已安装的组件将被跳过。

### 安装过程细节

自动安装将运行一个脚本安装 Elan、Git 和 curl。用系统包管理器安装 Git 和 curl 需要**管理员权限**，安装过程中会提示你输入凭据。

在支持包管理器 `apt` 的系统（如 Debian、Ubuntu）上，将执行：

```bash
# 安装 Git 和 curl。pkexec 用于显示安全的图形化凭据输入框
ulimit -Sn 1024; pkexec bash -c 'export DEBIAN_FRONTEND=noninteractive; apt-get update -y && apt-get install -y git curl'
# 用 curl 下载 Elan 安装脚本（elan-init.sh）并用 sh 运行。Elan 将安装到 ~/.elan
curl "https://elan.lean-lang.org/elan-init.sh" -sSf | sh -s -- -y --default-toolchain leanprover/lean4:stable
```

在支持包管理器 `dnf` 的系统（如 Fedora）上，将执行：

```bash
# 安装 Git 和 curl。pkexec 用于显示安全的图形化凭据输入框
pkexec dnf install -y git curl
# 用 curl 下载 Elan 安装脚本（elan-init.sh）并用 sh 运行。Elan 将安装到 ~/.elan
curl "https://elan.lean-lang.org/elan-init.sh" -sSf | sh -s -- -y --default-toolchain leanprover/lean4:stable
```

在既不支持 `apt` 也不支持 `dnf` 的 Linux 系统上，Git 和 curl 无法自动安装。如果尚未安装，请用你系统的包管理器手动安装，重启 VS Code 后重试本步骤——一旦 Git 和 curl 就绪，版本管理器 Elan 就能用自动安装脚本装上了。

### 受限环境

受限环境与 Windows 页完全相同：受限环境下脚本可能失败，此时目前无法在本地安装试用 Lean 4，可改用 Gitpod 在线环境做《Mathematics in Lean》的练习、玩自然数游戏，或用浏览器单文件版；完整表述见下方原文。

> **原文 · [guide-installLean-linux.md](https://github.com/leanprover/vscode-lean4/blob/v0.0.240/vscode-lean4/media/guide-installLean-linux.md)：**
>
> ## Installed Components
> The following components are automatically installed when clicking [this link](command:lean4.setup.installLean) or the 'Install Lean' button associated with this step:
> - [Elan](https://github.com/leanprover/elan) is Lean's version manager and automatically manages all the different versions of Lean and ensures that the correct version is used when opening a project.
> - [Git](https://git-scm.com/) is a commonly used [Version Control System](https://en.wikipedia.org/wiki/Version_control) that is used by Lean to help manage different versions of Lean formalization packages and software packages. It can also be used to collaborate on Lean projects.
> - [curl](https://curl.se/) is a small tool to transfer data that is used by Lean to download files when managing Lean formalization packages and software packages.
>
> Components that are already installed will be skipped.
>
> ## Installation Procedure Details
> The automatic installation will run a script to install Elan, Git and curl. To install Git and curl using your package manager, it needs admin privileges, the credentials for which it will prompt for during the installation.
>
> On Linux systems that support the package manager `apt` (e.g. Debian or Ubuntu), the following script will be executed:
> ```bash
> # Install Git and curl. `pkexec` is used to display a secure graphical input for your credentials.
> ulimit -Sn 1024; pkexec bash -c 'export DEBIAN_FRONTEND=noninteractive; apt-get update -y && apt-get install -y git curl'
> # Download the Elan installation script at https://github.com/leanprover/elan/blob/master/elan-init.sh using `curl` and run it using `sh`. Elan will be installed to `~/.elan`.
> curl "https://elan.lean-lang.org/elan-init.sh" -sSf | sh -s -- -y --default-toolchain leanprover/lean4:stable
> ```
>
> On Linux systems that support the package manager `dnf` (e.g. Fedora), the following script will be executed:
> ```bash
> # Install Git and curl. `pkexec` is used to display a secure graphical input for your credentials.
> pkexec dnf install -y git curl
> # Download the Elan installation script at https://github.com/leanprover/elan/blob/master/elan-init.sh using `curl` and run it using `sh`. Elan will be installed to `~/.elan`.
> curl "https://elan.lean-lang.org/elan-init.sh" -sSf | sh -s -- -y --default-toolchain leanprover/lean4:stable
> ```
>
> On Linux systems that do not support either of the package managers `apt` and `dnf`, Git and curl cannot be installed automatically.
> If you do not have them installed yet, please install Git and curl using your system's package manager, restart VS Code and re-try this step - once Git and curl are installed, Lean's version manager Elan can be installed using the automatic installation script.
>
> ## Restricted Environments
> If you are in a restricted environment where you cannot install Git or curl and they are not already installed, for example a restricted university computer, then the installation script above may fail. In this case, there is currently no way to try Lean 4 with a local installation. If you want to try out Lean 4 regardless, you can read [Mathematics in Lean](https://leanprover-community.github.io/mathematics_in_lean/) and do the exercises with [an online instance of Lean 4 hosted using Gitpod](https://gitpod.io/#/https://github.com/leanprover-community/mathematics_in_lean). Doing so requires creating a GitHub account. Alternatively, you can also [play the Natural Number Game](https://adam.math.hhu.de/#/g/hhu-adam/NNG4) or [try a single-file version of Lean 4 in your web browser](https://live.lean-lang.org/).

## <a id="install-macos"></a>安装 Lean —— macOS

### 将要安装的组件

点击**此链接**或本步骤的 “Install Lean” 按钮后，将自动安装以下组件：

- **Elan** —— Lean 的版本管理器，自动管理所有不同版本的 Lean，并确保打开项目时使用正确的版本。
- **Apple Command Line Tools**（也称 “Xcode Command Line Tools”）—— 包含多种对使用编程语言有用的工具。Lean 尤其需要其中的 **Git**——常用的版本控制系统，Lean 用它管理形式化包和软件包的版本，Git 也可用于 Lean 项目的协作开发。

已安装的组件将被跳过。

### 安装过程细节

自动安装将运行以下脚本来安装 Elan 和 Apple Command Line Tools：

```bash
# 使用 softwareupdate 安装 Apple Command Line Tools
touch "/tmp/.com.apple.dt.CommandLineTools.installondemand.in-progress"
aclt_label="$(/usr/sbin/softwareupdate -l |
              grep -B 1 -E 'Command Line Tools' |
              awk -F'*' '/^ *\*/ {print $2}' |
              sed -e 's/^ *Label: //' -e 's/^ *//' |
              sort -V |
              tail -n1 |
              tr -d '\n')"
/usr/sbin/softwareupdate -i "$aclt_label"
# 用 curl 下载 Elan 安装脚本（elan-init.sh）并用 sh 运行。Elan 将安装到 ~/.elan
curl "https://elan.lean-lang.org/elan-init.sh" -sSf | sh -s -- -y --default-toolchain leanprover/lean4:stable
```

### 受限环境

受限环境与 Windows 页完全相同，完整表述见下方原文。

> **原文 · [guide-installLean-mac.md](https://github.com/leanprover/vscode-lean4/blob/v0.0.240/vscode-lean4/media/guide-installLean-mac.md)：**
>
> ## Installed Components
> The following components are automatically installed when clicking [this link](command:lean4.setup.installLean) or the 'Install Lean' button associated with this step:
> - [Elan](https://github.com/leanprover/elan) is Lean's version manager and automatically manages all the different versions of Lean and ensures that the correct version is used when opening a project.
> - [Apple Command Line Tools](https://developer.apple.com/xcode/resources/) (also known as 'Xcode Command Line Tools') includes several utility tools that are useful for working with a programming language. Lean in particular needs [Git](https://git-scm.com/) from Apple Command Line Tools, a commonly used [Version Control System](https://en.wikipedia.org/wiki/Version_control) that is used by Lean to help manage different versions of Lean formalization packages and software packages. Git can also be used to collaborate on Lean projects.
>
> Components that are already installed will be skipped.
>
> ## Installation Procedure Details
> The automatic installation will run the following script to install Elan and Apple Command Line Tools:
> ```bash
> # Install Apple Command Line Tools using `softwareupdate`.
> touch "/tmp/.com.apple.dt.CommandLineTools.installondemand.in-progress"
> aclt_label="$(/usr/sbin/softwareupdate -l |
>               grep -B 1 -E 'Command Line Tools' |
>               awk -F'*' '/^ *\*/ {print $2}' |
>               sed -e 's/^ *Label: //' -e 's/^ *//' |
>               sort -V |
>               tail -n1 |
>               tr -d '\n')"
> /usr/sbin/softwareupdate -i "$aclt_label"
> # Download the Elan installation script at https://github.com/leanprover/elan/blob/master/elan-init.sh using `curl` and run it using `sh`. Elan will be installed to `~/.elan`.
> curl "https://elan.lean-lang.org/elan-init.sh" -sSf | sh -s -- -y --default-toolchain leanprover/lean4:stable
> ```
>
> ## Restricted Environments
> If you are in a restricted environment where you cannot install Git or curl and they are not already installed, for example a restricted university computer, then the installation script above may fail. In this case, there is currently no way to try Lean 4 with a local installation. If you want to try out Lean 4 regardless, you can read [Mathematics in Lean](https://leanprover-community.github.io/mathematics_in_lean/) and do the exercises with [an online instance of Lean 4 hosted using Gitpod](https://gitpod.io/#/https://github.com/leanprover-community/mathematics_in_lean). Doing so requires creating a GitHub account. Alternatively, you can also [play the Natural Number Game](https://adam.math.hhu.de/#/g/hhu-adam/NNG4) or [try a single-file version of Lean 4 in your web browser](https://live.lean-lang.org/).

## <a id="setup-project"></a>设置项目

### 创建项目

下面是为你新建项目或下载项目的链接。创建或下载项目之后，将来可以点击右上角的 **∀ 符号**，选择 **'Open Project…' > 'Open Local Project…'**，再选中你创建的项目来重新打开它。**尽量避免在网络驱动器或被云存储同步的目录（如 OneDrive）中创建项目。**

完成项目创建并选择打开新项目会关闭本向导。之后可以点 ∀ 符号，选 **'Documentation…' > 'Show Setup Guide'** 重新打开。

想**新建**项目，点击以下之一：

- **创建新的独立项目** —— 独立项目不依赖任何其他 Lean 4 项目。适合想把 Lean 4 当通用编程语言使用、或做程序验证的场景。之后可以按[这里的说明](https://github.com/leanprover/lean4/blob/master/src/lake/README.md#adding-dependencies)修改新项目里的 `lakefile.lean` 来添加依赖；你也可以考虑把 [Lean 标准库](https://github.com/leanprover/std4)加入依赖列表。
- **用 Mathlib 创建新项目** —— 创建的项目将依赖 Lean 4 的数学库 **Mathlib**。适合想做数学形式化项目的场景。创建后想更新 Mathlib，可点 ∀ 符号，选 **'Project Actions…' > 'Update Dependency…'**。

想**打开现有**项目，点击以下之一：

- **下载现有项目** —— 适合想给其他 Lean 4 项目（比如 Mathlib）做贡献的场景。
- **打开本地现有项目** —— 适合别人（比如任课老师）把本地 Lean 4 项目提供给你的场景。

### 复杂项目配置

借助构建系统和包管理器 Lake，Lean 4 支持比上述更复杂的项目配置。详见 [Lean 4 GitHub 仓库中的 Lake 文档](https://github.com/leanprover/lean4/blob/master/src/lake/README.md)。

> **原文 · [guide-setupProject.md](https://github.com/leanprover/vscode-lean4/blob/v0.0.240/vscode-lean4/media/guide-setupProject.md)：**
>
> ## Creating a Project
> Below, you will find links that create new projects or download projects for you. After creating or downloading a project, you can re-open the project in the future by clicking the ∀-symbol in the top right, choosing 'Open Project…' > 'Open Local Project…' and selecting the project you created. If possible, you should avoid creating projects on network drives or in directories indexed by cloud storage, e.g. OneDrive.
> Completing the project creation process and choosing to open the new project will close this guide. You can re-open it later by clicking the ∀-symbol in the top right and selecting 'Documentation…' > 'Show Setup Guide'.
>
>   ![∀-symbol buttons](open-local-project_show-setup_buttons.png)
>
> If you want to create a new project, click on one of the following:
> - [Create a new standalone project](command:lean4.project.createStandaloneProject)  
>   Standalone projects do not depend on any other Lean 4 projects. This option is suitable if you want to use Lean 4 as a general-purpose programming language or for program verification.  
>   Dependencies can be added by modifying 'lakefile.lean' in the newly created project as described [here](https://github.com/leanprover/lean4/blob/master/src/lake/README.md#adding-dependencies). You may want to add [Lean's standard library](https://github.com/leanprover/std4) to the list of dependencies.
> - [Create a new project using Mathlib](command:lean4.project.createMathlibProject)  
>   The created project will depend on [Mathlib](https://github.com/leanprover-community/mathlib4), the math library of Lean 4. This option is suitable if you want to use Lean 4 for a math formalization project.  
>   To update Mathlib after creating the project, you can click the ∀-symbol in the top right and choose 'Project Actions…' > 'Update Dependency…'.
>
> If you want to open an existing project, click on one of the following:
> - [Download an existing project](command:lean4.project.clone)  
>   This option is suitable if you want to contribute to another Lean 4 project, like [Mathlib](https://github.com/leanprover-community/mathlib4).
> - [Open an existing local project](command:lean4.project.open)  
>   This option is suitable if you have been provided with a local Lean 4 project by someone else, like an instructor.
>
> ## Complex Project Setups
> Using its build system and package manager Lake, Lean 4 supports more complex project setups than the ones described above. You can find out more about Lake in the [Lean 4 GitHub repository](https://github.com/leanprover/lean4/blob/master/src/lake/README.md).

## <a id="documentation"></a>学习文档

### 书籍

想学 Lean 4 的话，根据你的背景从以下入门书中选一本。如果卡住或有疑问，点左侧底部的 “Questions and Troubleshooting” 步骤。

- **[Functional Programming in Lean](https://lean-lang.org/functional_programming_in_lean/)** —— 把 Lean 4 作为通用编程语言使用的标准入门书。适合所有想学“用 Lean 4 编程”的用户。
- **[Theorem Proving in Lean 4](https://lean-lang.org/theorem_proving_in_lean4/)** —— 面向计算机背景用户、把 Lean 4 用作交互式定理证明器的标准入门书。也适合高级用户作为自底向上的 Lean 4 入门。
- **[Mathematics in Lean](https://leanprover-community.github.io/mathematics_in_lean/)** —— 面向数学背景用户的定理证明标准入门书。也适合所有想学习 Mathlib（Lean 的数学库）基本用法的用户。
- **[The Lean Language Reference](https://lean-lang.org/doc/reference/latest/)** —— Lean 4 的参考手册。适合需要任何 Lean 4 特性的完整、精确描述的用户。

### 动手教程

想直接上手用 Lean 4 证明关于自然数的初等定理，可以玩**[自然数游戏](https://adam.math.hhu.de/#/g/leanprover-community/NNG4)**——它使用 Lean 4 的一种简化方言，在浏览器里在线游玩，无需本地安装。

### 在 VS Code 中使用 Lean 4

**[Lean 4 VS Code 扩展手册](https://github.com/leanprover/vscode-lean4/blob/v0.0.240/vscode-lean4/manual/manual.md)**涵盖了在 VS Code 中使用 Lean 4 的各类必备工具。即使你已经熟悉其他编程语言和 VS Code，手册中 “Interacting with Lean files” 一节的**前五小节**也可能对你很有帮助。手册讲解了多项 Lean 特有的关键功能，例如：如何处理多个 Lean 文件、如何使用 InfoView、如何输入 Unicode 字符。

### 其他资源

**官网** —— [Lean 官网](https://lean-lang.org/)提供 Lean 4 本身及 Lean 社区的更多资源信息。

**Lean 社区** —— [Lean 社区网站](https://leanprover-community.github.io/index.html)链接了许多此处未列出的学习资源，并提供 Mathlib 的介绍。

**Lean Zulip** —— [Lean Zulip](https://leanprover.zulipchat.com/) 是讨论所有 Lean 相关话题与问题的主论坛。

**Reservoir** —— [Reservoir](https://reservoir.lean-lang.org/) 索引所有公开的 Lean 包，并提供 Lean 版本兼容性、包的依赖与被依赖信息。

### 查找定义与定理

Lean 4 及其数学库 Mathlib 的完整 API 参考，可在 [Mathlib 文档页](https://leanprover-community.github.io/mathlib4_docs/)查阅。此外还有多个搜索引擎，帮你在 Lean 4 和 Mathlib 中查找定义与定理：

- **Loogle**：基于模式匹配的搜索引擎，按类型签名或标识符名称查找定义与定理。（向导原文中此条是指向 VS Code 内部命令 `lean4.loogle.search` 的链接，点击即调起扩展内置的 Loogle 搜索）
- **[LeanExplore](https://www.leanexplore.com/)** 与 **[LeanSearch](https://leansearch.net/)**：两个基于 AI 的搜索引擎，按自然语言描述查找定义与定理。

> **原文 · [guide-documentation.md](https://github.com/leanprover/vscode-lean4/blob/v0.0.240/vscode-lean4/media/guide-documentation.md)：**
>
> ## Books
> If you want to learn Lean 4, choose one of the following introductory books based on your background. If you are getting stuck or have any questions, click on the 'Questions and Troubleshooting' step at the bottom on the left side.
>
> - [Functional Programming in Lean](https://lean-lang.org/functional_programming_in_lean/)  
>   The standard introduction to using Lean 4 as a general-purpose programming language. Suited for all users who wish to learn how to use Lean 4 as a programming language.
> - [Theorem Proving in Lean 4](https://lean-lang.org/theorem_proving_in_lean4/)  
>   The standard introduction to using Lean 4 as an interactive theorem prover for users with a computer science background. Also suited for advanced users as a bottom-up introduction to Lean 4.
> - [Mathematics in Lean](https://leanprover-community.github.io/mathematics_in_lean/)  
>   The standard introduction to using Lean 4 as an interactive theorem prover for users with a mathematics background. Also suited for all users who wish to learn the basics of how to use [Mathlib](https://github.com/leanprover-community/mathlib4), Lean's math library.
> - [The Lean Language Reference](https://lean-lang.org/doc/reference/latest/)  
>   The reference manual of Lean 4. Suited for all users who need a comprehensive and precise description of any Lean 4 feature.
>
> ## Hands-On Tutorial
> If you want to dive right into using Lean 4 to prove elementary theorems about natural numbers, you can play the [Natural Number Game](https://adam.math.hhu.de/#/g/leanprover-community/NNG4), which uses a simplified dialect of Lean 4. It can be played online using your browser without a local installation.
>
> ## Using Lean 4 in VS Code
> The [Lean 4 VS Code extension manual](command:lean4.docs.showExtensionManual) covers all kinds of essential tools when working with Lean 4 in VS Code. Even if you are already familiar with other programming languages and VS Code in general, you may still find the first five subsections of the 'Interacting with Lean files' section in the manual to be very helpful. The manual covers several essential Lean-specific VS Code features, e.g. how to work with multiple Lean files, how to use the InfoView in VS Code and how to input Unicode characters.
>
> ## Additional Resources
> **Website**  
> [Lean's website](https://lean-lang.org/) provides information on further resources for Lean 4 itself and the Lean community.
>
> **Lean Community**  
> The [Lean community website](https://leanprover-community.github.io/index.html) links to several other helpful learning resources not listed here and provides an introduction to [Mathlib](https://github.com/leanprover-community/mathlib4), Lean's math library.
>
> **Lean Zulip**  
> The [Lean Zulip](https://leanprover.zulipchat.com/) is the primary forum of discussion for all topics and questions related to Lean.
>
> **Reservoir**  
> [Reservoir](https://reservoir.lean-lang.org/) indexes all public Lean packages and provides information on Lean version compatibility, package dependencies and package dependents.
>
> ## Finding Definitions and Theorems
> A complete API reference for Lean 4 and [Mathlib](https://github.com/leanprover-community/mathlib4), Lean's math library, can be found on the [Mathlib documentation page](https://leanprover-community.github.io/mathlib4_docs/).
>
> Additionally, there are multiple search engines that help you find definitions and theorems in Lean 4 and Mathlib:
>
> - [Loogle](command:lean4.loogle.search): A pattern-based search engine that finds definitions and theorems by type signature or by the names of their identifiers.
> - [LeanExplore](https://www.leanexplore.com/) and [LeanSearch](https://leansearch.net/): Two AI-based search engine that find definitions and theorems by a description in natural language.

## <a id="troubleshooting"></a>问题与排障

### 杀毒软件

有用户反馈，过于激进的杀毒软件会干扰某些 Lean 命令的全部安全网络连接，导致类似下面的错误：

```
curl: (35) schannel: next InitializeSecurityContext failed: Unknown error (0x80092012) - The revocation function was unable to check revocation for the certificate
```

如果遇到此问题，可以尝试**暂时禁用杀毒软件**，重新运行失败的命令，完成后再启用。如果不放心整体禁用，也可以只关闭通常引发此问题的具体功能——一般叫“加密连接扫描”或“HTTPS 扫描”。常见杀软的关闭方法：[Kaspersky](https://support.kaspersky.com/KESWin/11.6.0/en-US/175124.htm)、[AVG](https://support.avg.com/SupportArticleView?l=en&urlName=Use-AVG-Antivirus-HTTPS-scan&supportType=home)、[Avast](https://support.avast.com/en-us/article/use-antivirus-https-scan/#pc)。

### 收集 VS Code 输出

遇到 Lean 或本扩展的问题时，复制 **'Troubleshooting: Show Setup Information'** 和 **'Troubleshooting: Show Output'** 两个命令的输出，会对帮你排障的人很有帮助。运行方法：点击右上角 ∀ 符号，选择 'Show Setup Information' 和 'Show Output'。

### 在 Lean Zulip 提问

要在 [Lean Zulip](https://leanprover.zulipchat.com/) 发帖提问，按以下步骤：

1. [注册一个 Lean Zulip 账号](https://leanprover.zulipchat.com/register/)
2. [进入 #new-members 频道](https://leanprover.zulipchat.com/#narrow/stream/113489-new-members)
3. 点击页面底部的 **'New topic'** 按钮，输入主题标题，在消息框里描述你的问题或故障，点 Send 发送。

在 Zulip 上贴代码时，请把代码精简为**[最小工作示例（MWE）](https://leanprover-community.github.io/mwe.html)**——包含别人把代码复制粘贴到他们环境里所需的全部 import 和声明。同时请务必用**[三个反引号](https://github.com/leanprover-community/mathlib/wiki/Code-in-backticks)**包裹代码，这样代码才能正确高亮和排版。

> **原文 · [guide-help.md](https://github.com/leanprover/vscode-lean4/blob/v0.0.240/vscode-lean4/media/guide-help.md)：**
>
> ## Antivirus Software
> Some users have reported that overly aggressive antivirus software will interfere with all secure network connections in certain Lean commands, leading to errors like the following:
> ```
> curl: (35) schannel: next InitializeSecurityContext failed: Unknown error (0x80092012) - The revocation function was unable to check revocation for the certificate
> ```
> If you encounter this issue, you can try disabling your antivirus, re-run the command that failed and re-enable it afterwards. If you are uncomfortable with disabling your antivirus software altogether, you can also try disabling the specific antivirus feature that is typically causing these issues, commonly known as 'encrypted connection scanning' or 'HTTPS scanning'. You can disable HTTPS scanning as follows in certain common antivirus software: [Kaspersky](https://support.kaspersky.com/KESWin/11.6.0/en-US/175124.htm), [AVG](https://support.avg.com/SupportArticleView?l=en&urlName=Use-AVG-Antivirus-HTTPS-scan&supportType=home), [Avast](https://support.avast.com/en-us/article/use-antivirus-https-scan/#pc).
>
> ## Collecting VS Code Output
> If you are encountering an issue with Lean or this VS Code extension, copying the output from the 'Troubleshooting: Show Setup Information' and 'Troubleshooting: Show Output' commands can be helpful for others who are trying to help you.
> You can run these commands by clicking on the ∀-symbol in the top right and selecting 'Show Setup Information' and 'Show Output'.
>
>   ![Troubleshooting](troubleshooting.png)
>
> ## Asking Questions on the Lean Zulip Chat
>
> To post a question on the [Lean Zulip chat](https://leanprover.zulipchat.com/), you can follow these steps:
> 1. [Create a new Lean Zulip chat account](https://leanprover.zulipchat.com/register/).
> 2. [Visit the #new-members stream](https://leanprover.zulipchat.com/#narrow/stream/113489-new-members).
> 3. Click the 'New topic' button at the bottom of the page, enter a topic title, describe your question or issue in the message text box and click 'Send'.
>
> When posting code on the Lean Zulip chat, please reduce the code to a [minimal working example](https://leanprover-community.github.io/mwe.html) that includes all imports and declarations needed for others to copy and paste the code into their own development environment. Please also make sure to delimit the code by [three backticks](https://github.com/leanprover-community/mathlib/wiki/Code-in-backticks) so that the code is highlighted and formatted correctly.
