# MinerU VLM 转录的静默错误与 PDF 层对照法

背景：MinerU 云端 VLM 精准解析（`mineru-open-sdk`，保留 full.md + JSON + images）
批量转录论文库后，需要评估转录质量。表面上 full.md 干净、公式成 LaTeX、表格成
HTML，看不出毛病——问题恰恰是**错误不显眼**。以下四类误识全部通过与 PDF 文本层
（`pdftotext`）对照坐实，不是印象。

## 症状：full.md 检索命中率异常、逐字引用对不上

- `grep 10240` 零命中，但文中确实有这个数；
- `grep efficient` 命中不全，漏掉大量实际存在的词；
- 引用转录文字做逐字核对时，与 PDF 原文对不上，且错处"看起来像是对的"。

## 根因：四类系统性误识

### 1. ff/ffi 连字丢一个 f（量最大、最系统）

全库统计（115 篇 full.md）：`eficient` ×1650、`diferent` ×1751、`suficient` ×376。
对照坐实：Fowler 2012 的 PDF 文本层 `sufficiently` ×10、`suficiently` ×0——
错在 VLM，不在原文。发现路径：grep 词频异常 → 怀疑转写 → pdftotext 同文对照。
影响：单词检索会漏；逐字引用必错。

### 2. LaTeX 数学环境内数字被逐字符加空格

`$N_x = 1 0 2 4 0$`、`$3 . 9 7$`、`$5 1 8 6$`（PDF 层是 `10240`、`3.97`）。
发现路径：搜 `3.97` 落空，搜 `3 . 9 7` 才中——第一反应以为是漏转，细看是
VLM 给数学 token 间插了空格。影响：**精确 grep 数字/公式全部失效**，检索前必须
归一化数学环境空格（本案例回核公式断言时第一轮全落空即此原因）。

### 3. 弯引号被误认成上标 66/99

Fowler FIG.5 图注：转录为 `marked by $^{66}\mathrm{E}^{99}\mathrm{s}$`，
PDF 文本层字节级是 `“E”s`（`cat -A` 可见 U+201C/U+201D 的 UTF-8 序列）。
经典印刷引号形似上标 66/99，旧 OCR 时代把这当笑谈，VLM 这里反向复现——
而且错成了"更像公式"的形态，反而更隐蔽。发现路径：读图注时觉得
"上标 66/99 的 E"语义不通 → cat -A 看字节。

### 4. 游离字符混入行内公式

Lee–Moser 2015：转录 `$\tau_w pis$ the mean wall shear stress`，
PDF 层是 `τw is`（没有 p）。疑似相邻字符被吞进数学环境。

## 方法论（可复用的部分）

- **失败方向不对称**：pdftotext 错得张扬（乱码，一眼可辨），MinerU 错得沉默
  （貌似合理）。两者互补，谁也不能单独当权威：
  - PDF 嵌入文本层（pdftotext 读到的）是**拼写层**的 ground truth——对原生
    数字版 PDF 成立；
  - MinerU 是**结构层**（公式→LaTeX、表格、标题层级、图片抽取）的最佳来源。
- 逐字引用一律回对 PDF 原件；对 full.md 做数字/公式检索前先归一化空格、
  单词检索容忍 ff 丢字（或反查 PDF 层交叉确认）。
- 旧扫描件自带的 OCR 层本身有错（如 1972 年 PRL 的 "tbe Navier–Stokes"）时，
  pdftotext 照单全收、VLM 视觉重识别反而纠对——嵌入层读取器 vs 图像重识别，
  架构决定失败方向，属正常发挥而非意外。
- 排查模板：怀疑某处错 → `pdftotext <同一 PDF> -` 抽同区域对照 → 引号/不可见
  字符类差异用 `cat -A` 看字节。

## 同批联网坑（简记）

- `no_proxy` 末尾字面量 `[::1]` → SDK 的 httpx 直接
  `InvalidURL: Invalid port: ':1]'`（带方括号 IPv6 字面量被当 URL 解析）；
  剥掉方括号即好。curl 不受影响，只有把 no_proxy 条目喂给 httpx 的路径炸。
- 本地代理 127.0.0.1:7890：curl 走代理正常，SDK 的长连接/上传腿反复
  `SSL: UNEXPECTED_EOF_WHILE_READING`；整批摘掉 `http(s)_proxy/all_proxy` 
  直连后一次全过。出现"curl 通但 Python SDK 断"先怀疑代理而非服务端。

## 关键词

`full.md grep 不中`、`eficient`、`diferent`、`suficient`、`1 0 2 4 0`、
`MinerU 错字`、`引号 66 99`、`ff 连字丢 f`、`VLM 静默错误`、`pdftotext 对照`、
`no_proxy [::1] InvalidURL`、`curl 通但 SDK SSL 断`
