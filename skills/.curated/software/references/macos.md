# macOS 小问题集锦

专门收纳 macOS 桌面日常使用中遇到的小问题及解决办法：推荐应用、应用无法打开的权限修复、外置存储隐藏文件的阻止与清理等。

## 推荐应用

### VMware Fusion

macOS 虚拟机软件，支持在 Intel / Apple Silicon Mac 上运行 Windows、Linux 等系统。已对所有用户免费（包括商业用途），从 [VMware 官网](https://www.vmware.com/products/desktop-hypervisor/workstation-and-fusion) 下载。

### Mounty + macFUSE

在 macOS 上读写 NTFS 格式的外置硬盘/U盘。

- [Mounty](https://mounty.app/)：菜单栏小工具，自动检测 NTFS 卷并以读写模式重新挂载
- macOS Ventura 起系统移除了内置 NTFS 读写支持，Mounty 2 改为基于第三方驱动，需安装三个组件：

```bash
brew install --cask macfuse
brew install gromgit/fuse/ntfs-3g-mac
brew install --cask mounty
```

首次启动需要在「系统设置 → 隐私与安全性」中信任 macFUSE（签名者 Benjamin Fleischer）和 ntfs-3g 驱动，可能需要重启

## 应用无法打开（权限 / Gatekeeper）

从网上下载的应用可能无法运行（无执行权限或被 Gatekeeper 隔离），修复：

```bash
chmod +x /Applications/<App>.app/Contents/MacOS/<Binary>
sudo xattr -d com.apple.quarantine /Applications/<App>.app
```

- `chmod +x`：添加执行权限
- `xattr -d com.apple.quarantine`：移除 Gatekeeper 隔离标记

## 外置存储上的 macOS 隐藏文件

macOS 会在插入的 USB/SD 卡/外置硬盘上自动生成多个隐藏文件和目录：

| 文件/目录 | 用途 |
|-----------|------|
| `.DS_Store` | Finder 文件夹元数据（图标位置、排序方式等） |
| `.Spotlight-V100` | Spotlight 搜索索引数据库 |
| `.Trashes` | 废纸篓（未清空就弹出的已删除文件会留在这里，隐形占用空间） |
| `.fseventsd` | 文件系统事件日志（弹出后一般为空，影响不大） |

### 阻止生成

在外置存储**根目录**创建以下占位文件，阻止 macOS 写入（插入 Mac 之前做）：

```bash
touch /Volumes/<disk>/.metadata_never_index       # 阻止 Spotlight 索引
touch /Volumes/<disk>/.Trashes                     # 阻止废纸篓（用文件占位，阻止系统创建同名目录）
mkdir -p /Volumes/<disk>/.fseventsd && touch /Volumes/<disk>/.fseventsd/no_log  # 阻止文件事件日志
```

> `.DS_Store` 无法通过占位方式阻止，只能事后清理或在网络存储上禁用。

### 阻止在网络存储上生成 DS_Store

```bash
defaults write com.apple.desktopservices DSDontWriteNetworkStores -bool TRUE
```

需登出再登入生效。恢复则将 `TRUE` 改为 `FALSE`。

### 批量清理

```bash
find . -type f \( -name ".DS_Store" -o -name "._.DS_Store" \) -delete -print 2>&1 | grep -v "Permission denied"
```

参考：
- [Apple 官方：调整 SMB 浏览行为](https://support.apple.com/en-us/102064)
- [.Trashes, .fseventsd, and .Spotlight-V100 详解](http://blog.hostilefork.com/trashes-fseventsd-and-spotlight-v100/)
