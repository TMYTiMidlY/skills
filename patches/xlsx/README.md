# xlsx 本地补丁

`series` 记录补丁应用顺序，路径相对 `skills/xlsx/`，兼容 quilt 的 `-p1` 路径约定。`skills/xlsx/` 保持补丁应用后的成品状态；上游同步时按 graft-skill 的补丁流程重放，`grafted-skills.json` 继续记录上游同步基线。

## 补丁内容

[0001-merged-cell-formatting.patch](0001-merged-cell-formatting.patch) 在 `SKILL.md` 的编辑流程后补充合并单元格处理：左上角样式设置、既有矩形外框的重建、合并布局变更，以及保存文件与重载结果的分别核对。

## 行为验证

使用 Python 3.13.13、openpyxl 3.1.5、普通 `Workbook` 和默认 `load_workbook`，通过 `BytesIO` 保存并重载。17 个场景、2555 项断言通过；检查覆盖四条边的每个单元格及颜色，同时对照内存对象、工作表和样式 XML、重载对象。

| 场景 | 观察 |
|---|---|
| 合并前后设置左上角样式 | 两种顺序均可保存并重载字体、对齐和边框；边缘格的首次 XML 表示可能不同 |
| 既有细线边框改为双线 | 只改左上角后，覆盖格的旧细线仍写入 XML；调用 `format()` 保留已有边框样式 |
| 覆盖格的字体和对齐 | 赋值进入保存的 XML；重载时覆盖格被重新构造，恢复默认字体和对齐 |
| 仅清除左上角边框 | 旧右下角的右边和底边可在重载时补回左上角，随后传播到对应边缘格 |
| 重建统一矩形外框 | 清除覆盖格边框、设置左上角目标边框、调用 `format()` 后，内存、XML 和重载结果一致；适用于明确要整体重建的外框 |
| 变更合并范围 | 覆盖格的旧内容随合并移除；旧左上角、新左上角和新右下角的状态影响重建结果 |

复测时可用一个多行多列矩形范围，分别设置合并前后样式、旧框替换、覆盖格单独样式、清框及合并区间变更；每次保存后先检查 XML，再重载核对所有边缘格。此验证仅覆盖文件结构和 openpyxl 行为，视觉效果需由目标办公软件检查。

> 对应源码：[合并区域处理](https://foss.heptapod.net/openpyxl/openpyxl/-/blob/3.1.5/openpyxl/worksheet/merge.py#L73-133)、[边框属性相加](https://foss.heptapod.net/openpyxl/openpyxl/-/blob/3.1.5/openpyxl/descriptors/serialisable.py#L215-228)、[覆盖格重建](https://foss.heptapod.net/openpyxl/openpyxl/-/blob/3.1.5/openpyxl/worksheet/worksheet.py#L594-638)。
