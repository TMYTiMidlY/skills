# Lean 4 / Lake 工具链与 CI 疑难杂症

> 本页记录 Lean 4 / Lake 项目（以 qatlas-lean-lib，Lean 4.30.0 + Mathlib/Physlib 为背景）在验证、缓存、CI 中遇到的低频问题。共同教训：**Lean 的正确性检查很贵，但真正烧时间的常常是检查器自己写的重复工作；缓存与诊断的"输出口径"比命令退出码更需要逐字理解。**

## <a id="lean-module-names-perf"></a>全库公理扫描莫名要 6～13 分钟：`header.moduleNames` 每次调用都重建数组

> 2026-09-28 | Lean 4.30.0，`~776,815` 个环境声明、318 个正式模块 | 私有计时变体插桩（逐 `collectAxioms`/`ppExpr`/筛选分段计时）+ 镜像内 Lean 源码取证

### 症状

- 全库公理/题答审计 wall 767s，其中 `collectAxioms` 实际只占 0.094s——闭包计算不背锅。
- 单一基础模块的局部检查（111 个项目声明）也要 386s，慢得不成比例；导入基线（imports-only）却只有约 11s。

### 探测手段

复制审计脚本为计时变体，保持同样输入、同样输出顺序，仅在循环里累积分段耗时；imports-only 驱动对照加载成本。分项后：环境筛选 392s + 题答模块筛选 83s，公理闭包与类型匹配都接近零。`docker top` 显示单核 100% CPU，是计算不是 IO。

### 根因

Lean 4.30 源码里 `Environment.header.moduleNames` **不是缓存字段**，定义是 `header.modules.map (·.module)`。审计对每个常量调 `env.header.moduleNames[idx]`，等于对 776,815 个常量各重建一遍完整模块名数组——O(声明数 × 模块数)。题答检查另有一处：对每个常量在一个 146 元素的 `Array Name` 上 `contains` 线性查找。

### 解法

- 同索引直接取：`env.header.modules[idx.toNat]!.module`，判定/输出完全一致。
- membership 改 `Std.HashSet Name`（仅替换查询，不迭代该集合，候选顺序不变）。
- 效果：两处筛选 392.4+82.9s → 7.0+3.3s；全量 6,826 条 DECL、73 条 CLAIM 与原输出逐项一致。
- **写 Lean 元程序遍历环境前，先查该 getter 是不是 cached 字段**；必要时缓存到循环外而不是信任它"看起来像个字段"。

## <a id="lean-example-sorry-diagnostics"></a>删掉"重复 elaborate"后匿名 `example ... sorry` 静默漏检

> 2026-09-28 | Lake/Lean 4.30，增量构建 + 缓存重播 | 锁定 Lean 源码 `Lean/Elab/MutualDef.lean` 取证 + 冷/暖两轮真实 Lean 负例

### 症状

局部检查从"Lake build + 逐文件 `lake env lean` 再检查"精简为一次 Lake 图后，写入 `example : False := by sorry` 的目标**仍能通过**：Lake exit 0，审计也找不到任何违规。

### 根因

Lean 中匿名 `example` 在 `withoutModifyingEnv` 里求值，**不会留在 `.olean` 里**：构建只剩一条 warning 诊断，公理扫描面对的环境根本没有这个声明。原来的"每个源码再 `lean` 一遍"恰好把它挡住，删掉后出现了真实盲区。

### 解法

- 不恢复重复编译；改为捕获唯一一次 `lake build` 的 stdout+stderr（**先打印、再 `check_returncode()`、再扫诊断**），用与全库相同的 sorry 诊断正则识别。
- **必须覆盖缓存重播**：`Replayed` 行意味着诊断从缓存重播而非重新编译，第二次构建源文件没变也必须拒绝。
- `QATLAS_RECEIPTS=1` 时 stdout/stderr 分通道，合并再扫，别只扫一边。
- 教训：named theorem 的 sorry 负例不等于覆盖了 example；**对"删除重复检查"类优化，负例集要专门包含"只在诊断流存在的失败"**。

## <a id="lean-claim-base-env-leak"></a>CI 里 fixture 报 `base revision ... is not available; fetch full history`，本地怎么都复现不了

> 2026-09-28 | GitHub Actions + 自造临时 Git fixture 仓库 | `gh api .../jobs/<id>/logs` 取证 + 同环境变量本地容器复现

### 症状

云端原生自测中，临时小仓库里运行检查入口直接失败：冻结基准检查找不到提交。真正的全库检查还没开始。本地同一条测试全绿。

### 根因

workflow 在 job 级 `env:` 设了 `QATLAS_CLAIM_BASE=<PR base sha>`（冻结题目比较基准）。容器与自测逐层继承，最终 fixture 里的独立小仓库也被迫用它当基准——小仓库的历史里当然没有主仓库的提交。**凡是 job env 传入的变量，嵌套的临时仓库/子进程默认全看得见。**

### 解法

- fixture 显式传 `--base <自己的 HEAD>`，**同时故意保留外来的同名环境变量**，把这层污染本身纳入回归。
- 本地复现此类 CI 失败时，先把 workflow 的 job env 原样注入容器再跑，别在"干净"环境里测 CI 用例。

## <a id="observer-stdout-pollution"></a>性能观测 wrapper 往 stdout 打日志，把 Mathlib cache 下载打炸

> 2026-09-28 | 官方 bootstrap + 自建 curl/tar 观测 wrapper | 逐字节 stdout/stderr 一致性预检

### 症状

为空环境准备做计时，用 wrapper 包住 `curl` 记录事件后，bootstrap 在看似下载成功的阶段失败；第一轮 800+ 秒成果全部作废。

### 根因

Mathlib 的 `Cache/IO.lean` 直接解析 `curl --version` 输出的**首词**判断版本；wrapper 先往 stdout 打了一行 `MEASURE {...}` JSON，版本探测拿到的首词是 `MEASURE`。

### 解法

- 观测代码只写独立 events 文件，**绝不改被测命令的 stdout/stderr 字节流**；启动前先跑 `curl --version` 等命令的字节级一致性预检（stdout、stderr、exit code 三方全等）再进入长任务。
- 通用教训：第三方代码解析工具输出文本时（版本探测、进度行、首行表头），任何 wrapper/tee/前缀注入都是行为变更。

## <a id="lake-no-build-upstream-stale"></a>`--no-build` 报 `target is out-of-date and needs to be rebuilt`：是固定依赖缓存不完整，不是项目缓存失效；以及"审计是慢不是挂"

> 2026-09-28 | Lake `--no-cache --no-build build <全部目标>`，独立验证副本 | 按 target 名归因 + 只读挂载归因 + `docker top` 分辨慢/挂

### 症状

- 恢复的验证副本做全目标 `--no-build` 检查报 out-of-date；以为项目缓存失效。
- 去掉 `--no-build` 实跑又在只读依赖处报 `read-only file system`。

### 根因（两次失败原因不同）

- 第一次：缺失的 target 是 `QuantumInfo.Channels.Dual` 等 **Physlib 上游模块**——本机固定依赖缓存不完整，与项目 `.lake/build` 无关。按 target 名字归因：`QuantumInfo.*`/`Mathlib.*` 是上游，`QuantumAlgorithm.*`/`Tests.*` 才是项目。
- 第二次：上游目标需要补编译，而依赖按设计只读挂载——**缺的上游模块要在私有可写副本里补齐**，不能改共享缓存也不能伪造就绪。
- 另注意：全库审计 ~13 分钟、单核 100% CPU、RSS ~4 GiB 是常态，`docker top` 确认 CPU time 在涨就是"慢"不是"挂"，别提前 kill 再花一轮冷编译。

### 读 Lake 输出的口径（同一坑的另一半）

- `lake --no-cache` **只禁远程 cache 下载，不关闭本地增量**；要"不许编译"必须加 `--no-build`。
- 日志里的 jobs 总数是**构建图规模**，不是本次重编数量；实际重编看 `] Built <module>` 行。
- `Replayed` 是历史诊断重播；项目源码已有的存量 warning 会反复出现但不失败——严格与否取决于目标库的 `warningAsError` 配置，不是出现 warning 字样就失败。

## <a id="gh-log-readonly-cache"></a>`gh run view --log` 报 `read-only file system`：改走 API 直接取日志

> 2026-09-27 | 受限环境，gh CLI | 错误指向 `~/.cache/gh/run-log-*.zip`

### 症状

`gh run view <id> --log` 直接失败：`failed to get run log: creating cache entry: open /home/<user>/.cache/gh/...: read-only file system`。

### 解法

```sh
gh api --allow-escape-sequences repos/<owner>/<repo>/actions/jobs/<job_id>/logs
```

日志带 ANSI 转义时要加 `--allow-escape-sequences`，否则 API 命令会以另一种方式拒绝输出。数据落盘后就地 grep，不要再依赖 gh 的本地缓存。

## <a id="shared-worktree-stage-mixup"></a>多 agent 共享同一工作区：交接方重做自己提交时，你的改动会"回到未暂存区"

> 2026-09-27~28 | 同一 gitdir 上 lead + 多名 teammate 并行改不重叠文件 | `git status`/`git diff --cached` 对账

### 症状

自己的改动明明记得处理过，`git status` 却显示它们躺在未暂存区；另一批文件则被别人的提交带走了。

### 根因与解法

- teammate 首次提交误卷了你的暂存改动，reset 重做后，**被卷的改动以"未暂存"形态回到你的工作区**——不是丢失，是易读错的状态。
- 约定：任何人 commit 前只看 `git diff --cached`（暂存区才是提交边界）；不用 `git add .`/全树 add；新建目录的文件要先 `git add` 跟踪，否则按 Git 文件清单算的构建指纹/CI 目标根本看不见它（status 里的 `A` 是"已暂存"不是"已提交"）。
- 交接消息里**点名文件清单与实际 HEAD**，别引用一个后来可能被改写的缩写哈希。
