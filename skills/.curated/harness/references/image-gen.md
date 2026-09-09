# Codex 订阅生图接入

本篇重点说明 DSH 或脚本怎样通过 CLIProxyAPI（CPA）使用 Codex 订阅生成、编辑图片：先区分操作和输入，再说明调用路径、遮罩和图片参数，随后介绍 DSH／脚本怎样连接 CPA，并给出请求写法和并发处理说明。公共 OpenAI Images API 只作明确标注的对照，其参数规范不自动成为订阅端点的承诺。

Codex 内置工具的启用条件、请求构造、思考程度和耗时统计见 [Codex 生图运行时](codex.md#image-runtime)；登录材料的读取、刷新和跨程序复用见[订阅登录凭据](codex.md#subscription-auth)。参考素材准备、构图、定向修订和透明拆图的方法见 docs-writer skill 的 GPT Image 生图经验。

## <a id="image-operations"></a>图片生成和编辑

生成和编辑描述要完成的操作；JSON 和 multipart 描述怎样组织请求数据。先确定操作，再按所用接口选择提交方式，不能从上传格式推断图片能力。

### <a id="operation-generate"></a>根据文字生成图片

不提供参考图，只用文字描述需要的画面，例如“画一个浅色背景上的绿色茶壶”。在本篇所核 Images 接口中，这类请求使用 `/images/generations`；文字、图片模型和输出选项放在请求参数中。

### <a id="operation-edit"></a>以已有图片为输入进行编辑

提供已有图片，再描述如何修改或参考它，例如“把茶壶改成橙色，保留背景”。在所核 Codex 内置工具中，只要带参考图就构造 `/images/edits` 请求；这不意味着只能局部涂改，也不意味着输出的其他像素一定不变。

用户可以把“参考这张图重新画一张”称为生成新图，而接口将它归入编辑。文档中的操作名称以输入和请求路径为准，不把日常语言与接口分类强行等同。

> [Codex 生成和编辑分支](https://github.com/openai/codex/blob/9caddc5cf5bf4df5f114498e23bece90eaedb37b/codex-rs/ext/image-generation/src/tool.rs#L419-L487)根据是否带参考图选择请求。其他服务如何划分操作，应查看各自接口。

### <a id="reference-roles"></a>参考图片在任务中的作用

参考图、编辑目标和遮罩承担不同职责。多图任务应在提示词中说明各张图的用途，而不是只上传一组图片。

| 输入 | 用途 | 提示词需要说明什么 |
|---|---|---|
| 待编辑原图 | 提供要修改的画面 | 修改什么、保留什么 |
| 其他参考图 | 提供风格、人物、物体或构图参考 | 每张参考图承担的角色，哪些特征需要采用 |
| 遮罩 | 表达希望修改的区域 | 区域内应如何变化，以及整体画面要求 |

遮罩不是额外的风格参考图，也不是每次编辑都必填。仅通过文字要求修改某个对象，与另行提供遮罩，是不同的输入控制方式。

## <a id="routes"></a>Codex 订阅生图的调用路径

对外都叫“图片接口”的组件，内部可能请求专用 Images 端点、调用 Responses 中的图片工具，或启动整个 Codex Agent。接入前应确认实际路径，而不是只看接口名称。

### <a id="routes-images"></a>直接调用订阅 Images 端点

调用链是“应用 → 图片客户端或代理 → Codex 订阅 Images 端点 → 图片结果”。所核路径为 `/backend-api/codex/images/generations` 和 `/backend-api/codex/images/edits`。

这一图片请求本身不需要启动 Codex CLI、app-server 或额外的文字编排模型。调用方负责准备参数和处理结果，身份可以由已有宿主或代理提供。

> [Codex ImagesClient](https://github.com/openai/codex/blob/73a1148c9c775c2a4616ce5096291740a00ed68a/codex-rs/codex-api/src/endpoint/images.rs#L35-L79)使用 JSON POST。这些订阅路径与公共 `api.openai.com/v1/images/*` 是不同入口。

### <a id="routes-responses"></a>通过订阅 Responses 调用图片工具

调用链是“应用 → Responses 适配器 → 主模型调用 `image_generation` → 适配器提取图片”。它可以只使用 HTTP、不启动本地 Codex，但仍包含主模型编排。

顶层模型和图片工具模型属于不同参数层。应用需要处理 Responses 的事件或最终结果，不能把整个响应当作 Images 接口的图片数组。

> [Sub2API 图片请求构造](https://github.com/Wei-Shaw/sub2api/blob/98d86915becae9fe9491a91ffc6defd5235c8d2b/backend/internal/service/openai_images_responses.go#L358-L444)展示了顶层主模型及图片工具参数的分别设置；这只是该版本的实现案例。

### <a id="routes-agent"></a>通过 Codex Agent 执行图片任务

应用通过 CLI、SDK 或 MCP 包装启动或连接 Codex，由它理解任务、组织提示词、调用内置图片工具并检查结果。一次外层调用可能包含多次生图。

这种接入可以复用 Agent 的任务处理能力，也会带入其运行过程。外层总耗时不等于图片服务耗时，具体区别见 [Codex 思考程度](codex.md#image-reasoning)和[生图计时边界](codex.md#image-timing)。

### <a id="routes-public-api"></a>公共 OpenAI API

公共 Images API 使用 `https://api.openai.com/v1/images/generations` 生成图片，使用 `/v1/images/edits` 编辑图片；公共 Responses API 则由顶层语言模型调用 `image_generation` 工具。选择图像模型、填写输出参数和提供图片输入时，分别遵循对应接口。

公共 API 使用 API 凭据和独立计费。Codex 订阅任务切换到此入口前应取得用户同意；SDK 只是请求客户端，实际身份和计费路径取决于目标地址及所用凭据。调用 CPA 的写法见 [CPA Python 客户端](#cpa-sdk)。

下面以产品参考图为输入，展示公共 Images API 的单图透明编辑。显式指定官方地址，避免 `OPENAI_BASE_URL` 环境变量改变请求目标；`OPENAI_API_KEY` 由运行环境提供。

```python
import os
from openai import OpenAI

client = OpenAI(
    base_url="https://api.openai.com/v1",
    api_key=os.environ["OPENAI_API_KEY"],
    max_retries=0,
    timeout=180.0,
)
with open("<PRODUCT_REFERENCE_PNG>", "rb") as source:
    result = client.images.edit(
        model="gpt-image-2",
        image=source,
        prompt="提取产品，保留外形、比例和标签文字；背景完全透明，不绘制棋盘格。",
        size="2048x1152",
        quality="high",
        background="transparent",
        output_format="png",
        n=1,
    )
```

此例只展示请求写法，未执行生图验收。结果按 [图片内容校验](#artifact-validation) 解码检查，再按 [文件保存](#artifact-persistence) 保留原始输出。参数被拒绝或返回尺寸、透明度不符时，应报告实际结果；180 秒是客户端等待上限。

> 来源：[公共 Images API](https://developers.openai.com/api/reference/resources/images)、[GPT Image 参数说明](https://developers.openai.com/api/docs/guides/image-prompting?model=gpt-image-2.5)。示例使用 GPT Image 2；其他模型按各自支持的参数调整。

## <a id="edit-inputs"></a>图片输入的提交方式

JSON 和 multipart 是数据组织方式，不是两种编辑算法。生成请求也常用 JSON；编辑请求因为要携带图片，才更容易遇到图片引用和文件上传之间的选择。某个接口是否同时接受两种方式，必须单独确认。

### <a id="edit-images-json"></a>使用 JSON 提交参数和图片引用

JSON 用字段表达文字、选项和图片引用。图片可以表示为 URL、文件 ID，或含有完整编码数据的 data URL；具体允许哪些引用形式由接口决定。

例如 `data:image/png;base64,<图片编码>` 的前缀说明数据格式，后半段是图片字节的 base64 编码。它不需要图片已经公开托管在网站上。base64 是编码而非加密，数据体积约为原字节数的 4/3，也不会提高画质。

> [Codex 编辑请求结构](https://github.com/openai/codex/blob/9caddc5cf5bf4df5f114498e23bece90eaedb37b/codex-rs/codex-api/src/images.rs#L18-L36)使用 `images[].image_url`；base64 定义见 [RFC 4648](https://www.rfc-editor.org/rfc/rfc4648.html#section-4)。字段名 `image_url` 不表示内容一定是远程网页地址。

### <a id="edit-cpa-conversion"></a>使用 multipart 提交参数和图片文件

multipart/form-data 在同一条请求中分别放入文字字段和文件内容。应用直接上传原图或遮罩，不必先将它们手工编码到 JSON 中；多个 part 也不等于多个并行任务。

使用 HTTP 客户端构建 multipart 时，由客户端生成 boundary，也就是各部分的分隔标识。不要手工填写与请求体不一致的 `Content-Type`。CPA 收到文件后仍可能将它转换为下游 JSON，因此外部上传格式不一定等于上游实际收到的格式。

> 格式定义见 [RFC 7578](https://www.rfc-editor.org/rfc/rfc7578.html#section-4)；CPA 转换实现见[文件和字段处理](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/internal/runtime/executor/codex_openai_images.go#L527-L590)。

### <a id="edit-responses-input"></a>不同接口的图片字段

下面按入口区分字段，不能把某一行的写法直接搬到另一行。

| 入口 | 原图或参考图的表达 | 需要分清的层次 |
|---|---|---|
| Codex 内置工具 | `referenced_image_paths` 或 `num_last_images_to_include` | 这是主模型选择参考图的工具参数，不是 HTTP 请求体 |
| 所核 Codex Images 请求 | `images: [{"image_url": "…"}]` | 执行器构造下游 JSON |
| CPA 的 JSON 请求 | `images` 数组 | 所核原生分支保留主体，主要规范模型和流式字段 |
| CPA 的 multipart 请求 | `image` 或重复的 `image[]` 文件字段 | 该版本优先选择 `image[]`，不将两种文件字段合并 |
| 公共 Images JSON 接口 | `images` 中的 `image_url` 或 `file_id` 引用 | 由公共 API 的身份、文件和参数契约决定是否有效 |
| Responses 图片输入 | 消息中的 `input_image` 等内容块 | 需使用该适配器的消息及工具格式，不整包照搬 Images JSON |

> [Codex 工具参数](codex.md#image-request)、[公共 Images 编辑接口](https://developers.openai.com/api/reference/resources/images/methods/edit)、[CPA 文件选择](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/internal/runtime/executor/codex_openai_images.go#L921-L953)、[Sub2API 输入转换](https://github.com/Wei-Shaw/sub2api/blob/98d86915becae9fe9491a91ffc6defd5235c8d2b/backend/internal/service/openai_images_responses.go#L367-L444)。公共接口同时支持 JSON 和 multipart；某个 SDK 只暴露文件参数，不足以否定另一种协议入口。

## <a id="edit-masks"></a>遮罩参数（mask）

遮罩是一张与待编辑原图对应的辅助图片，用来表达希望修改的区域。它需要同时满足所用接口的输入要求，并配合文字描述；不能只上传一张黑白图就假定所有入口都理解相同含义。

### <a id="mask-purpose"></a>遮罩的作用

公共 OpenAI Images 接口用遮罩的完全透明区域指示需要编辑的位置。例如希望替换照片中央的茶壶，可在遮罩对应位置留出透明区域，同时用 prompt 说明替换成什么，以及其他画面应如何保留。

遮罩并不是像素级的修改锁。官方指南明确说明 GPT Image 的遮罩作为提示引导，模型可能不精确遵守其形状；不透明区域也不能据此获得逐像素不变保证。`background="transparent"` 则控制输出背景，是另一个参数，不能代替 mask。

> 透明区语义见 [Python SDK v3.10.0 的 mask 定义](https://github.com/openai/openai-python/blob/v3.10.0/src/openai/types/image_edit_params.py#L58-L64)；效果边界见[官方遮罩编辑指南](https://developers.openai.com/api/docs/guides/image-generation#edit-an-image-using-a-mask)。上述是公共 API 的说明，不能当成订阅端点已经验收的效果保证。

### <a id="mask-creation"></a>遮罩的制作和透明通道

alpha 通道记录透明度。在这里采用的公共 API 语义下：

| 遮罩像素 | 表达的区域 | 容易混淆的地方 |
|---|---|---|
| alpha 为 0，完全透明 | 希望编辑的区域 | 与 RGB 是黑色还是白色无关 |
| alpha 为 255，完全不透明 | 未指定为编辑的区域 | 不等于输出该处像素必定不变 |
| 部分透明 | 介于两者之间的输入 | 不据此推断统一的阈值或精确混合比例 |

手工制作时，新建与原图同尺寸、带透明通道的画布，先填为不透明，再将目标区域删除成真正透明，最后导出保留 alpha 的 PNG。只涂黑或涂白不会自动产生透明度；将 RGB 图片转换成 RGBA，也不会自动把黑色变透明。

下面用 Pillow 演示中心矩形遮罩的制作。它只创建本地文件，不调用图片服务；输入应是已经准备好的 PNG 原图，输出路径应尚不存在。

```python
from pathlib import Path
from PIL import Image

with Image.open("<ORIGINAL_PNG>") as image:
    width, height = image.size
mask = Image.new("RGBA", (width, height), (255, 255, 255, 255))
mask.paste((0, 0, 0, 0),
           (width // 4, height // 4, 3 * width // 4, 3 * height // 4))
with Path("<MASK_PNG>").open("xb") as output:
    mask.save(output, format="PNG")
```

这里中心半宽、半高的矩形是透明区，其他位置不透明。如果已有黑白区域图，需要显式把灰度值写入 alpha，例如 `rgba.putalpha(grayscale)`；这才会让灰度 0 对应透明，而不是依赖 RGB 颜色本身。提交前应检查遮罩文件大小和 alpha 分布，避免整张意外全透明或全不透明。

> [官方遮罩制作说明](https://developers.openai.com/api/docs/guides/image-generation#mask-requirements)包含将灰度写入 alpha 的示例。此处矩形示例使用二值透明度，不假定模型对部分透明像素有精确的区域执行规则。

### <a id="mask-dimensions"></a>原图与遮罩的对应要求

遮罩的宽、高对应原图像素坐标，不是希望生成的输出尺寸。只调整原图大小而不同时处理遮罩，会让区域错位；输出 `size` 的选择也不能代替这项对应关系。

公共资料的文件大小口径并不完全一致，需要保留来源区别：

| 来源 | 遮罩要求 | 适用说明 |
|---|---|---|
| Python SDK v3.10.0 参数定义 | 有效 PNG、小于 4 MB、与输入图尺寸一致；多图时作用于第一张 | 同一文件另将 GPT 输入图描述为 PNG／WebP／JPG、每张小于 50 MB；不能把输入图和遮罩限制混写 |
| 2026-09-10 查阅的官方指南 | 原图和遮罩同格式、同尺寸、小于 50 MB，遮罩需要 alpha | 动态指南与上述 SDK 的大小描述存在差异，不能拼成一个已证实的统一上限 |

下面的 CPA 示例采用同尺寸 PNG 原图和 PNG 遮罩，并要求遮罩小于 4 MB，使示例落在这两份说明的约束交集中。其他组合应按实际入口核对；这不表示订阅后端已被验证采用相同上限。

多图任务中，公共 Images 的遮罩对应第一张输入图，因此应先放待编辑原图，再放其他参考图。CPA 可以保留或构造输入数组，但字段转发不证明订阅后端执行相同语义；基础遮罩效果未验证前，不应直接扩展为复杂多图任务。

> [SDK 输入图要求](https://github.com/openai/openai-python/blob/v3.10.0/src/openai/types/image_edit_params.py#L15-L26)、[SDK 遮罩要求](https://github.com/openai/openai-python/blob/v3.10.0/src/openai/types/image_edit_params.py#L58-L64)、[指南中的 Mask requirements](https://developers.openai.com/api/docs/guides/image-generation#mask-requirements)。旧 DALL·E 2 的正方形输入要求不能套给全部 GPT Image 模型。

### <a id="mask-support"></a>不同接口的遮罩支持

遮罩参数必须沿实际调用分支核对：工具是否暴露、代理怎样转换、远端是否接受，是不同问题。

| 入口 | 参数或处理方式 | 能确定的边界 |
|---|---|---|
| 所核 Codex 内置工具 | 没有独立 mask 参数 | 不能在 `image_gen.imagegen` 参数中直接补一个 mask；文字指定区域也不是同一项输入能力 |
| 公共 Images JSON | 顶层 `mask: {"image_url": "…"}` 或 `mask: {"file_id": "…"}`，两者选一 | `image_url` 可使用 URL 或 base64 data URL；文件 ID 需满足公共 API 的文件契约 |
| 公共 Images multipart | 单独的 `mask` 文件部分 | 不把遮罩当成另一张 `image[]` 参考图 |
| CPA 原生 Images 的 JSON 分支 | 保留 `mask.image_url`、`mask.file_id` 等主体字段 | 透传不是确认订阅后端支持 file ID 或精确遮罩编辑 |
| CPA 原生 Images 的 multipart 分支 | 取第一个 `mask` 文件，转为 data URL 写入 `mask.image_url` | 不合并多个遮罩，也不自动将黑白 RGB 转为 alpha |
| 所核 CPA 的另一条 Responses 适配分支 | 将 `mask.image_url` 转为工具的 `input_image_mask.image_url` | 不是原生 Images 分支；不能将该分支对 file ID 的处理泛化到所有 CPA 请求 |

CPA 的上述文件转换读取字节并进行 base64 编码，没有完整解码校验 PNG、alpha、原图与遮罩宽高一致或公共规范中的文件大小限制。multipart 解析的内存阈值也不等于图片文件大小规范。调用方应先准备正确的文件，再看实际后端结果。

> [Codex 工具参数](codex.md#image-request)、[公共编辑接口](https://developers.openai.com/api/reference/resources/images/methods/edit)、[CPA 原生 JSON 准备](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/internal/runtime/executor/openai_compat_executor.go#L769-L781)、[multipart 转换](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/internal/runtime/executor/codex_openai_images.go#L527-L590)、[文件编码](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/internal/runtime/executor/codex_openai_images.go#L921-L953)、[Responses 适配](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/internal/runtime/executor/codex_openai_images.go#L745-L824)。

### <a id="mask-validation"></a>局部编辑结果的检查

先检查遮罩是否确实带 alpha、透明区域是否对齐，再检查生成图片中的目标修改和非目标区域变化。若需要严格保持其他像素，应将“像素完全不变”列为独立验收条件，而不能从 prompt 写了“保留”或请求带 mask 推导出来。

CPA 仓库中的转换测试使用模拟服务和测试字节，只证明字段转换的预期行为。本文保留的真实订阅验收没有覆盖 mask；后面的[原图和遮罩请求示例](#cpa-edit-mask)用于说明参数写法，不声称已经完成真实区域编辑验收。

> [CPA 转换测试](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/internal/runtime/executor/codex_openai_images_test.go#L181-L317)不能代替订阅后端的真实效果测试。

## <a id="model-parameters"></a>图片模型及输出参数

图片模型、尺寸和质量要按实际入口设置。模型公开能力、工具暴露参数、客户端发出的值以及服务端实际结果，应分别说明。

### <a id="model-identifiers"></a>公共 API 的 GPT Image 2.5 型号

OpenAI 于 2026-09-08 公布 ChatGPT Images 2.5，并宣布覆盖 ChatGPT、ChatGPT Work 和 Codex 各档位。公共 API 提供以下型号：

| 模型 | 官方定位 | 日期快照 |
|---|---|---|
| `gpt-image-2.5-flare` | 较快的日常图片生成 | `gpt-image-2.5-flare-2026-09-08` |
| `gpt-image-2.5-sunburst` | 注重精细创作和编辑控制 | `gpt-image-2.5-sunburst-2026-09-08` |

截至 2026-09-10，Codex 稳定版 0.153.4、近期核对的 alpha 版本和当日主线，内置工具仍填写 `gpt-image-2`。这只能说明客户端名称，不能确认订阅后端映射到哪一种模型；也不能把公共 API 的 2.5 名称直接替换进所有代理入口。

> [官方公告](https://openai.com/index/introducing-chatgpt-images-2-5/)、[模型枚举](https://github.com/openai/openai-openapi/blob/21cb7e98d8166a691a0eb8679a90419eb816cf35/openapi.json#L26415-L26443)、[Flare](https://developers.openai.com/api/docs/models/gpt-image-2.5-flare)、[Sunburst](https://developers.openai.com/api/docs/models/gpt-image-2.5-sunburst)。Codex 的具体版本、请求字段及公告与客户端门控的差异见[请求构造](codex.md#image-request)和[启用条件](codex.md#image-availability)。

### <a id="public-size"></a>图片尺寸

公共 GPT Image 2／2.5 支持独立 `size="WIDTHxHEIGHT"`。所核公共参数说明要求两边为 16 的倍数、比例介于 1:3 和 3:1；2.5 指南还列出单边不超过 3840、总像素 655,360–8,294,400，超过 `2560×1440` 总像素量属于实验范围。

`1920×1080` 中的 1080 不是 16 的倍数；`2048×1152` 满足上述比例和倍数要求。严格交付 `1920×1080` 时，可在生成后明确缩放，并将原始尺寸与交付尺寸分开记录。

所核 Codex 内置工具没有独立尺寸参数，执行器固定补入 `size:"auto"`，画幅意图只能由主模型写入 prompt。CPA 原生分支则可以保留调用方填写的 size，但仍需核对远端是否遵从。

> [SDK 尺寸定义](https://github.com/openai/openai-python/blob/v3.10.0/src/openai/types/image_generate_params.py#L104-L130)、[公共生成指南](https://developers.openai.com/api/docs/guides/image-generation#size-and-quality-options)、[Codex 请求构造](codex.md#image-request)。这些公共约束不能未经验证就成为订阅端点的硬限制。

### <a id="public-quality"></a>图片质量档位

图片 quality 与 Codex 主模型的 reasoning effort 不同。调高外层思考程度不会自动把图片请求改为高质量，间接影响见 [Codex 思考程度](codex.md#image-reasoning)。

| 入口 | 所核质量控制 |
|---|---|
| 公共 GPT Image 2 | `low`、`medium`、`high`、`auto` |
| 公共 GPT Image 2.5 | 上述选项，以及 `xhigh`、`max` |
| Codex 内置工具 | 没有独立 quality 形参，执行器发送 `auto` |
| CPA 原生 JSON 分支 | 保留调用方字段，不保证订阅后端接受或遵从全部档位 |

> [公共质量枚举](https://github.com/openai/openai-openapi/blob/21cb7e98d8166a691a0eb8679a90419eb816cf35/openapi.json#L26449-L26476)。官方 API-key fallback 脚本还有自身的参数和本地校验，见 [fallback 入口](codex.md#image-api-fallback)；其旧限制不等于公共模型能力上限。

### <a id="public-background"></a>背景和输出格式

公共 API 的 `background` 可设为 `auto`、`opaque` 或支持时的 `transparent`，分别表示自动选择、不透明背景和透明背景。`output_format` 支持 PNG、JPEG、WebP；透明输出使用 PNG 或 WebP。返回文件仍需检查实际 alpha，参数名和预览外观均不能代替验证。

OpenAI 的 2026-08-20 更新日志为 GPT Image 2 增加了透明背景预览支持，覆盖 Images API 和 Responses API 生图工具；GPT Image 2.5 指引也包含透明输出。旧版客户端或脚本可能仍拒绝这一组合，具体见 [fallback 本地校验](codex.md#image-api-fallback)。

> 来源：[2026-08-20 API 更新日志](https://developers.openai.com/api/docs/changelog)、[公共图像输出选项](https://developers.openai.com/api/docs/guides/image-prompting?model=gpt-image-2.5)。订阅代理是否接受或遵从这些选项，需按实际分支验证。

### <a id="public-input-fidelity"></a>参考图保真参数

GPT Image 2 以高保真方式处理输入图片，调用时省略早期模型使用的 `input_fidelity` 参数。输入保真、输出 `quality` 和外层推理强度分别作用于不同环节，迁移模型时不要直接复用旧参数组合。

> 来源：[GPT Image 2 参数说明](https://developers.openai.com/api/docs/guides/image-prompting?model=gpt-image-2)。参数支持范围随模型变化；高保真输入也不保证所有元素或像素保持不变。

### <a id="subscription-output"></a>请求参数和实际输出的核对

请求值说明客户端发出了什么，响应元数据说明服务端报告了什么，原始图片解码结果才说明真实格式、尺寸和透明通道。文件名、模型别名或 prompt 中的“4K”不能替代实际检查。

留存的 2026-09-09 独立 HTTP 验收中，订阅 Images 请求填写 `gpt-image-2`、显式 `size=1024x1024`，实际 PNG 为 `1254×1254`；其中一次编辑指定 `quality=low`，响应报告 `medium`。另有 2026-07-14 的 Codex Desktop 用户报告，将 `1024×1024` 写在 prompt 中，六次成功输出均为 `1254×1254`。前者是显式参数比较，后者是自然语言要求，两者不能混为同一种测试。

> 前者依据当日留存的脱敏验收记录；后者见 [Codex Desktop 用户报告](https://github.com/openai/codex/issues/33050)。这些有限观察不能确定实际模型映射、证明模型做不到目标尺寸，或代表当前 2.5 的参数遵从程度；也未进行同条件的画质或性能比较。

## <a id="component-examples"></a>订阅生图接入项目的对照

这些项目都涉及订阅生图，但提供给调用方的接口不同。下表用于理解现成服务、程序包和宿主插件的区别，不是安装清单或项目排名；选用 CPA 时，不需要再安装其余项目。具体的 DSH／脚本操作继续看[通过 CPA 接入](#components)。

| 项目及所核版本 | 怎样使用 | 订阅图片的实际调用 | 生成 | 编辑输入 | 登录由谁处理 |
|---|---|---|---|---|---|
| CPA v7.2.155，`7fac6b15` | 运行服务，脚本或 DSH 的连接工具向它发送 HTTP 请求 | 指定模型走专用 Images 请求，另有 Responses 分支 | 支持 | 可接收 JSON 图片引用或 multipart 文件上传 | CPA 使用其配置的认证来源；接入前明确刷新责任 |
| openai-oauth，`ec7dab2f` | Node.js 软件包，供程序调用现成函数；另有开发服务器 | 专用 Images 请求 | 支持 | 所核对外编辑入口要求 multipart | 可读取 Codex 文件并提供刷新选项；共享授权需协调 |
| pi-gpt-image，`181adf16` | 安装到 pi 中，由 pi 使用插件工具 | 专用 Images 请求 | 支持 | 所核插件没有编辑工具 | 向 pi 取得宿主管理的订阅身份 |
| Sub2API，`98d86915` | 运行网关，调用其 HTTP 接口 | 所核 OAuth 图片分支通过 Responses 的主模型调用图片工具 | 支持 | 有生成和编辑的请求转换 | 网关管理账户认证 |

> 源码：[CPA 图片分支](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/internal/runtime/executor/codex_openai_images.go#L84-L120)、[openai-oauth 图片入口](https://github.com/EvanZhouDev/openai-oauth/blob/ec7dab2fcd8dab9da970a7a2b5dc34046c94905e/packages/openai-oauth/src/images.ts#L4-L39)、[pi 工具及认证](https://github.com/drgnchan/pi-gpt-image/blob/181adf16902eae2bc69a348ef588e58fb905b72b/extensions/index.ts#L74-L158)、[Sub2API 请求转换](https://github.com/Wei-Shaw/sub2api/blob/98d86915becae9fe9491a91ffc6defd5235c8d2b/backend/internal/service/openai_images_responses.go#L358-L444)。表中的支持范围来自所核源码，不表示已对每个项目完成真实生成、编辑或全部参数测试。

接入成本和验证程度另行比较，避免把“有这个功能”和“已经可靠跑通”混为一谈。

| 项目 | 接入时的主要条件或限制 | 许可证 | 验证范围 |
|---|---|---|---|
| CPA | 需要运行实例、配置身份并连接调用方；并发行为需区分独立实例、Home 和插件 | MIT | 有指定条件下的生成及两种提交方式的编辑实测，见[历史记录](#cpa-observations) |
| openai-oauth | 与 Node.js 环境及认证处理衔接；库支持 Request.signal，但所核 Node 适配器没有把下游断开接入该信号 | Apache-2.0 | 阅读源码，未完成应用集成或真实生图验收 |
| pi-gpt-image | 与 pi 的工具、认证和附件接口绑定；不是供任意脚本直接调用的独立图片服务 | MIT | 阅读源码，未进行真实图片调用 |
| Sub2API | 包含完整网关功能，还需处理主模型和图片工具的参数及事件；不能当成只转发图片的轻量服务 | LGPL-3.0 | 阅读图片转换源码，未进行真实图片调用 |

> [openai-oauth 的 Node 请求适配](https://github.com/EvanZhouDev/openai-oauth/blob/ec7dab2fcd8dab9da970a7a2b5dc34046c94905e/packages/openai-oauth/src/shared.ts#L138-L216)；许可证见 [CPA](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/LICENSE#L1-L22)、[openai-oauth](https://github.com/EvanZhouDev/openai-oauth/blob/ec7dab2fcd8dab9da970a7a2b5dc34046c94905e/LICENSE#L1-L25)、[pi-gpt-image](https://github.com/drgnchan/pi-gpt-image/blob/181adf16902eae2bc69a348ef588e58fb905b72b/LICENSE#L1-L21)、[Sub2API](https://github.com/Wei-Shaw/sub2api/blob/98d86915becae9fe9491a91ffc6defd5235c8d2b/LICENSE#L1-L24)。软件许可不代替上游服务条款；有 SDK 或源码，也不证明可以低成本抽出独立图片模块。

<a id="component-routes"></a><a id="component-maintenance"></a>
这些是版本化的比较记录。升级或替换时，核对实际请求路径、相关修复、测试及发布包对应关系；star 和提交数量只作线索，不代替功能与维护质量判断。下文仍以 CPA 为具体操作主线，不展开其他项目的安装和开发教程。

## <a id="components"></a>DSH 和脚本通过 CPA 使用订阅生图

CPA 负责使用已配置的 Codex 订阅身份请求画图；DSH 或脚本负责提交画图要求、原图和其他参数，再取得返回的图片。这里的图片服务地址，就是接收生成或编辑请求的 HTTP 网址，不是另一个需要开发的应用。

```text
脚本 ──────────────────→ CPA → Codex 订阅图片服务
DSH → 调用 CPA 的生图插件或 MCP 工具 ─┘
                    ← 返回图片 ←
```

先完成 [CPA 配置和启动](#cpa-config)，再连接调用方。CPA 的调用 key 交给脚本或相应插件／MCP server；上游订阅凭据由 CPA 按已配置的认证方式使用，两种凭据不能混填。

### <a id="component-interfaces"></a>脚本通过 CPA 生成和编辑图片

脚本可以使用 curl 或 Python HTTP 客户端，将请求发送到 CPA：不带原图时调用[生成接口](#cpa-generate)，带原图时调用[编辑接口](#cpa-edit)。然后读取响应中的图片数据，解码并保存。

如果使用[官方 Python 客户端](#cpa-sdk)，它在这里仍然只是帮脚本向 CPA 发送 HTTP 请求。需要配置 CPA 的服务地址和调用 key；不需要在脚本中启动 Codex Agent，也不是绕过 CPA 改为直接调用另一套服务。

### <a id="component-plugins"></a>DSH 通过生图插件调用 CPA

使用支持自定义图片服务地址的 DSH 生图插件时，将它的图片请求目标设为 CPA，并填写 CPA 的调用 key。生成时由插件发送文字要求；编辑时还需要把 DSH 中选中的原图转换成 CPA 接受的图片数据或文件。

能否这样配置、服务地址是否需要包含 `/v1`、如何选取附件，都取决于具体插件版本。不能因为文本模型已经接上 CPA，就认为图片工具也会自动使用相同配置；只支持某家服务登录的插件，也未必能改接 CPA。

> DSH 的模型、工具和插件配置关系见 [DSH 运行时](dsh.md)。这里说明插件需要承担的连接工作，不表示任意生图插件都具备这些能力，也不表示已有插件已经完成这条链路的实测。

### <a id="component-mcp"></a>DSH 通过 MCP 工具调用 CPA

另一种连接方式是在 DSH 中启用一个调用 CPA 的生图 MCP server。它向 DSH 提供生成和编辑工具，收到要求后发送对应的 CPA HTTP 请求，再把结果作为图片或可取得的文件返回。

这个 MCP server 需要实际实现 CPA 调用；仅启动 CPA 不会让 DSH 自动出现这些工具，也不是启动 Codex 自带的 MCP server 就会改走 CPA。应配置并检查 CPA 地址、调用 key、原图输入和图片返回方式，再确认 DSH 中工具可见、生成及编辑都能完成。

> [MCP 工具结果](mcp.md#tool-result-blocks)说明客户端如何处理返回内容。MCP 这一层负责把 DSH 的工具调用接到 CPA，不需要再启动完整 Codex Agent 来执行相同的图片请求。

## <a id="lifecycle"></a>图片请求的运行管理

应用需要控制的是一次任务从提交到交付的过程。这里保留接入所需的基本区别，CPA 的具体行为见[并发处理](#cpa-concurrency)和[错误诊断](#cpa-errors)。

### <a id="lifecycle-timeout"></a>请求超时

明确超时覆盖认证读取、上传、等待响应、解码和保存中的哪些阶段。只取消网络请求的定时器，不能终止一个不接受取消的认证读取；客户端停止等待也不等于上游停止生成。

### <a id="lifecycle-cancel"></a>请求取消

取消应释放应用的等待任务、连接和并发槽位。不要因为本地调用已结束，就保证远端任务没有执行或没有消耗额度。

### <a id="lifecycle-replay"></a>失败后的重试

先区分请求确定未执行与结果不确定。超时或断流可能发生在图片已经生成之后；SDK、代理、认证刷新和外层 Agent 的重发应分别控制，不能将所有错误都当成可无条件重试。

### <a id="lifecycle-concurrency"></a>并发请求和排队

并发上限控制同时执行的请求数，队列安排尚未执行的任务。需要排队时，明确等待上限、取消及重启后是否保留；单个请求的 `n` 是出图张数，不是多个 HTTP 请求的并发数。

### <a id="lifecycle-async"></a>异步任务的结果恢复

先返回任务 ID 的接口不自动意味着持久化。应用应确认完成结果保存多久、重启后能否查询，以及重复提交是否有去重机制；同步调用断线后“再试一次”不属于结果恢复。

## <a id="artifacts"></a>图片结果的处理

收到成功状态后，还需确认图片真实有效、调用方能取得它，并区分原图与后处理文件。

### <a id="artifact-validation"></a>图片内容的校验

检查有效图片条目，严格解码 base64，再用图像库确认格式、宽高和完整可解码性。base64 有效或 PNG 文件头正确都不足以单独证明图片完整；按应用资源预算限制字节数和像素数，最后检查视觉要求。

### <a id="artifact-return"></a>向调用方返回图片

根据应用接口返回图片数据、可读取路径、附件或下载链接。文件路径必须对接收者有意义，缩略图也不能代替原图；Agent 客户端的差异见 [MCP 结果内容块](mcp.md#tool-result-blocks)。

### <a id="artifact-persistence"></a>图片文件的保存

保存到明确目录，避免意外覆盖，说明临时链接或附件的有效期。发生缩放、裁剪或重编码时，分别保留原始尺寸和交付尺寸，不把后处理结果宣称为模型原生输出。

## <a id="cpa"></a>使用 CLIProxyAPI 提供图片接口

本章针对 CPA v7.2.155、提交 `7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974`。示例将外部应用接入一个 CPA 实例，由它使用已配置的 Codex 订阅身份；执行生成或编辑会消耗对应账户的图片额度。

### <a id="cpa-version"></a>版本和模型路由

截至 2026-09-10，CPA 官方最新稳定版和主线仍与上述版本相同。所核原生分支精确匹配规范化后的 `gpt-image-1.5`／`gpt-image-2`，不是所有 `gpt-image-*` 前缀。

不能仅把示例名称改为 `gpt-image-2.5-flare` 或 `gpt-image-2.5-sunburst`，就认定仍进入同一个原生分支。通过别名、其他 provider 或 Responses 是否能调用，需要分别追踪；原生分支失败也不自动回退 Responses。

> [发布版本](https://github.com/router-for-me/CLIProxyAPI/releases/tag/v7.2.155)、[模型匹配](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/internal/runtime/executor/codex_openai_images.go#L643-L667)、[原生分支选择](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/internal/runtime/executor/codex_openai_images.go#L84-L87)。这些是对应版本的源码行为，不是对所有 CPA 配置的统一判断。

### <a id="cpa-config"></a><a id="cpa-checks"></a>实例配置和启动

先按 [Codex 凭据复用](codex.md#auth-sharing)准备 CPA 专属认证目录。CPA 的本机调用 key 与上游订阅令牌不是一回事；不要把 `auth-dir` 指向原始 Codex 登录目录来代替格式适配。

以下是基础模板，替换占位符，并选用空闲端口：

```yaml
host: "127.0.0.1"
port: 8317
auth-dir: "<CPA_AUTH_DIR>"
api-keys:
  - "<CPA_LOCAL_KEY>"
```

启动命令为：

```bash
"<CPA_BINARY>" -config "<CPA_CONFIG_FILE>"
```

确认启动信息中的版本、配置和监听地址。下面各例假定 `CPA_BASE_URL` 为不含 `/v1` 的服务地址，例如 `http://127.0.0.1:8317`，`CPA_LOCAL_KEY` 已注入当前进程环境。可先用不生成图片的模型列表请求确认连接和调用认证：

```bash
printf 'Authorization: Bearer %s\n' "$CPA_LOCAL_KEY" |
  curl --silent --show-error --fail-with-body --max-time 10 \
    -H @- "$CPA_BASE_URL/v1/models"
```

模型列表可读取不证明订阅账户具备生图权限。启动还会读取工作目录中的 `.env`，应知道实际使用了什么环境；停止时只结束自己启动的实例。

若使用“独立扁平凭据、仅访问令牌和账户 ID、无其他刷新来源”的方式，令牌到期仍需原持有者刷新后同步。是否可长期自动更新，要按实际认证来源判断，不在图片调用章节重复展开。

> [启动参数](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/cmd/server/main.go#L95-L111)、[配置加载](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/internal/config/config_load.go#L64-L81)。示例配置值不等于省略字段后的运行时默认值。

### <a id="cpa-parameters"></a>图片请求参数

生成和编辑共享部分输出参数，编辑另外携带原图及可选遮罩。

| 参数 | 用途 | 所核 CPA 原生分支的边界 |
|---|---|---|
| `model`、`prompt` | 模型名称和文字要求 | 示例显式指定 `gpt-image-2`；prompt 需要非空 |
| `n` | 单次请求希望返回几张图片 | 示例为 1；不是并发上限，也不是该分支唯一允许的本地值 |
| `size`、`quality`、`background` | 输出尺寸、质量及背景设置 | 可保留调用方字段，不等于后端一定遵从 |
| `images` | JSON 中的原图／参考图列表 | 不将 Codex 内置工具的五张限制直接套成 CPA 的硬限制 |
| `image`／`image[]` | multipart 文件字段 | 优先使用 `image[]`，不与 `image` 文件合并 |
| `mask` | 编辑区域的辅助图片 | 写法见[提交原图和遮罩](#cpa-edit-mask)，实际效果未包含在历史验收中 |
| `response_format`、`stream` | 结果格式和流式选项 | 所核原生分支可处理／转发相关字段；本章示例采用非流式并读取 `b64_json` |

原生准备层主要规范模型和 stream，并保留主体；共用处理还可能附加缓存等元数据。file ID、多图、遮罩和其他选项能透传，不代表其远端上传、引用及生成链路均已验证。

> [生成入口](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/sdk/api/handlers/openai/openai_images_handlers.go#L599-L654)、[编辑原生提前路由](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/sdk/api/handlers/openai/openai_images_handlers.go#L891-L940)、[透传测试源码](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/internal/runtime/executor/codex_openai_images_test.go#L181-L317)。不能拿后续其他分支的拒绝规则描述已经提前返回的原生请求。

### <a id="cpa-generate"></a>生成图片

不带参考图时，调用生成端点。将下面请求保存为 `generate.json`；low 仅用于展示该参数，不是所有任务的推荐档位。

```json
{
  "model": "gpt-image-2",
  "prompt": "生成一张简洁插画：浅色背景上的绿色茶壶，没有文字。",
  "n": 1,
  "size": "auto",
  "quality": "low"
}
```

```bash
printf 'Authorization: Bearer %s\n' "$CPA_LOCAL_KEY" |
  curl --silent --show-error --fail-with-body --max-time 180 \
    -H @- -H 'Content-Type: application/json' \
    "$CPA_BASE_URL/v1/images/generations" \
    --data-binary @generate.json --output response.json
```

这会发起一次生图。`response.json` 是响应数据，不能直接改名当图片；继续按[响应处理](#cpa-response)提取并校验结果。

### <a id="cpa-edit"></a>编辑已有图片

提供原图并描述修改要求时，调用 `/v1/images/edits`。下面两种提交方式完成的是同一类操作，区别在于原图怎样装入请求，并不是编辑算法或画质档位不同。

#### <a id="cpa-edit-json"></a>使用 JSON 提交请求

读取原图的实际字节，编码为 base64 data URL，再与文字要求一起保存为 `edit.json`。MIME 应与真实文件格式对应，不要原样发送占位符。

```json
{
  "model": "gpt-image-2",
  "prompt": "将茶壶改成橙色，保留背景和构图。",
  "images": [{"image_url": "data:image/png;base64,<ORIGINAL_BASE64>"}],
  "n": 1,
  "size": "auto",
  "quality": "low"
}
```

```bash
printf 'Authorization: Bearer %s\n' "$CPA_LOCAL_KEY" |
  curl --silent --show-error --fail-with-body --max-time 180 \
    -H @- -H 'Content-Type: application/json' \
    "$CPA_BASE_URL/v1/images/edits" \
    --data-binary @edit.json --output response.json
```

#### <a id="cpa-edit-multipart"></a>使用 multipart 上传文件

直接上传原图文件，由 CPA 转为下游图片引用；HTTP 客户端负责生成 multipart 的 Content-Type 和 boundary。

```bash
printf 'Authorization: Bearer %s\n' "$CPA_LOCAL_KEY" |
  curl --silent --show-error --fail-with-body --max-time 180 \
    -H @- "$CPA_BASE_URL/v1/images/edits" \
    -F 'model=gpt-image-2' \
    -F 'prompt=将茶壶改成橙色，保留背景和构图。' \
    -F 'image[]=@<ORIGINAL_FILE>' \
    -F 'n=1' -F 'size=auto' -F 'quality=low' \
    --output response.json
```

这里不手工设置 JSON Content-Type。多图可使用重复的同名文件字段，但其顺序、用途及后端支持应另外验证；不要混用 `image` 和 `image[]` 后误以为两组都被采用。

#### <a id="cpa-edit-mask"></a>提交原图和遮罩

先按[遮罩制作](#mask-creation)准备文件，并确认[尺寸和格式](#mask-dimensions)。下面展示 CPA 已核转换路径的请求写法，**不表示订阅后端的 mask 功能已经真实验收**。

JSON 请求将 `mask` 放在顶层，与 `images` 并列，不把它作为另一张参考图塞入数组：

```json
{
  "model": "gpt-image-2",
  "prompt": "将遮罩指定区域的茶壶替换为橙色花瓶，保留其他画面。",
  "images": [{"image_url": "data:image/png;base64,<ORIGINAL_BASE64>"}],
  "mask": {"image_url": "data:image/png;base64,<MASK_BASE64>"},
  "n": 1,
  "size": "auto",
  "quality": "low"
}
```

将其保存到前面的 `edit.json` 后，使用同一个 JSON 提交命令。采用 multipart 时，原图放在 `image[]`，遮罩放在单独的 `mask` 文件字段：

```bash
printf 'Authorization: Bearer %s\n' "$CPA_LOCAL_KEY" |
  curl --silent --show-error --fail-with-body --max-time 180 \
    -H @- "$CPA_BASE_URL/v1/images/edits" \
    -F 'model=gpt-image-2' \
    -F 'prompt=将遮罩指定区域的茶壶替换为橙色花瓶，保留其他画面。' \
    -F 'image[]=@<ORIGINAL_PNG>' -F 'mask=@<MASK_PNG>' \
    -F 'n=1' -F 'size=auto' -F 'quality=low' \
    --output response.json
```

一个请求只提供一种遮罩来源。该版本只取首个 mask 文件，不合成多个遮罩；还支持将 `mask[image_url]`／`mask[file_id]` 表单字段映射到 JSON，但不会替调用方执行“引用二选一”校验。混用文件与引用可能留下同时存在的字段，不能依赖它自动消除冲突。file ID 透传也不代表 CPA 已提供可用的订阅文件上传流程。

> [CPA 遮罩文件处理](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/internal/runtime/executor/codex_openai_images.go#L545-L590)、[表单引用映射](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/internal/runtime/executor/codex_openai_images.go#L631-L640)。JSON 和 multipart 示例均不启用 curl 重试或重定向；180 秒只限制调用方等待，不是 CPA 或上游的完整执行期限。

### <a id="cpa-sdk"></a>使用官方 Python 客户端调用

将官方客户端的 `base_url` 指向 CPA，`api_key` 填写 CPA 的本机 key。调用官方 SDK 不意味着自动转为公共 API 计费；它仍向配置的 CPA 地址发送请求。

以下示例需要已有 `openai` 和 Pillow 环境，只发起一次文件式编辑。依赖安装转用 `software` skill，不向系统 Python 写入依赖。

```python
import base64
import os
from io import BytesIO
from pathlib import Path
from openai import OpenAI
from PIL import Image

client = OpenAI(
    base_url=os.environ["CPA_BASE_URL"].rstrip("/") + "/v1",
    api_key=os.environ["CPA_LOCAL_KEY"],
    max_retries=0,
    timeout=180.0,
)
with open("<ORIGINAL_FILE>", "rb") as original:
    result = client.images.edit(
        model="gpt-image-2", image=original,
        prompt="将主体改成橙色，保留背景和构图。",
        n=1, size="auto", quality="low",
    )
if not result.data or not result.data[0].b64_json:
    raise ValueError("响应没有有效的 b64_json 图片")
raw = base64.b64decode(result.data[0].b64_json, validate=True)
with Image.open(BytesIO(raw)) as image:
    image.verify()
with Image.open(BytesIO(raw)) as image:
    image.load()
    print(image.format, image.size, image.mode)
with Path("<OUTPUT_FILE>").open("xb") as output:
    output.write(raw)
```

根据实际格式选择输出文件扩展名，`xb` 防止覆盖。应用还需按自己的资源预算限制数据大小；上例的解码检查发生在 SDK 已取得响应之后，不是网络接收阶段的硬上限。通过 SDK 提交遮罩时也需显式传入相应文件参数，并沿用前面的能力边界。

### <a id="cpa-concurrency"></a>CPA 对并发请求的处理

先区分独立运行、Home 模式和启用扩展的实例。这里的在途请求指已经发出、尚未完成的请求。v7.2.155 的默认独立内置图片路径允许多个 HTTP 请求并行推进，没有把所有图片任务放进一个统一的串行队列；这不等于无限吞吐或保证上游不会限流。

每个请求选择认证后进入执行器，选择过程的锁不覆盖整个生图网络阶段。同一账号也可能同时处理多个请求：round-robin 是轮换选账号，fill-first 是优先选可用列表前项，都不是“等这个账号上一张画完再分配”的机制。

> [图片请求进入执行路径](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/sdk/api/handlers/handlers_execution.go#L36-L97)、[认证选择后调用执行器](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/sdk/cliproxy/auth/conductor_execution.go#L489-L566)、[调度返回认证](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/sdk/cliproxy/auth/scheduler.go#L1185-L1211)、[直接 HTTP 调用](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/internal/runtime/executor/codex_openai_images.go#L318-L349)。这是指定路径的源码推论，没有并发压力实测。

几个容易误认成并发控制的参数，实际作用如下：

| 配置或参数 | 控制的内容 | 不代表什么 |
|---|---|---|
| `routing.strategy` | 账号选择策略，如 round-robin、weighted-round-robin、fill-first | 不是每账号在途请求上限 |
| `routing.session-affinity` | 会话与账号的选择关系 | 不是为该会话预留唯一执行槽位 |
| `request-retry` | 额外重试轮次 | 不是同时执行的任务数 |
| `max-retry-credentials` | 每轮尝试的凭据数量 | 设为 1 也不意味着只能同时处理一张图 |
| `max-retry-interval` | 重试轮间允许的冷却等待 | 等待不等于 FIFO 或持久任务队列；非正值也不禁止无需等待的重试 |
| 图片请求的 `n` | 该请求希望返回几张图 | 不等于 HTTP 请求并发数，也不能据此推断上游内部怎样并行 |

遇到 429 等失败时，CPA 可以按错误和配置将认证／模型标记为暂不可用，进行候选切换或当前请求内的等待。这些行为不提供后台任务 ID、排队公平性或重启后的任务恢复，也不是提前防止同账号并发的限流器。

> [配置说明](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/config.example.yaml#L144-L177)、[路由配置](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/config.example.yaml#L215-L238)、[冷却等待判定](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/sdk/cliproxy/auth/conductor_selection.go#L1170-L1246)。示例 YAML 的值不能当成省略配置后的所有默认值。

Home 模式将凭据调度交给 Home 统一管理，是独立运行之外的一种部署方式。它可以对凭据／模型进行并发准入控制，相关配置由 Home 下发，本地同名值会被忽略。达到其限额时，受信的 Home 准入错误为 `credential_concurrency_exceeded`／HTTP 429，manager 不自动重试这种 busy 错误；这也不是图片专用的持久队列。

不要把 `credential-concurrency.max-limit` 误当成独立实例的“最多同时生图数量”，也不要用本地 YAML 覆盖 Home 策略。实际限制应在 Home 中核对。动态插件还可介入路由、调度或执行；启用插件、SDK 自定义组件或外部网关时，需另外确认它们是否提供限流，不能套用默认内置路径的结论。

> [Home 配置来源](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/config.example.yaml#L52-L76)、[Home 准入错误](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/sdk/cliproxy/auth/home_concurrency.go#L23-L40)、[不重试 busy 错误](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/sdk/cliproxy/auth/conductor_selection.go#L1179-L1186)、[默认关闭的插件配置](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/config.example.yaml#L80-L105)、[插件调度分支](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/sdk/cliproxy/auth/conductor_selection.go#L1910-L1919)。

如果外部应用需要确定的总在途请求上限或可靠排队，可在应用或网关中设置有界工作队列，同时安排等待取消和失败重试预算。它控制的是应用向 CPA 发出的请求数，不自动等于每个上游账号的并发上限；已有 Home 或插件限制时，应与其配合。这里没有经实测确定的通用最佳并发数，不预设所有部署必须串行或固定为某个数值。

### <a id="cpa-response"></a>图片响应的处理

先检查 HTTP 和业务错误，再从 `data[].b64_json` 严格解码图片；若收到 `data[].url`，先分清 data URI 与 HTTPS 下载链接，再按实际读取方式处理。原生非流式分支直接返回上游成功体，不重新保证所有字段都存在。

size、quality、background 和 usage 可保留为服务端报告值，但不能代替文件检查或直接推算订阅扣减。多条结果应逐项处理；没有有效图片时不能只报告“HTTP 200”。

> [原生响应转发](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/internal/runtime/executor/codex_openai_images.go#L360-L376)。不能拿 Responses 分支的 URL 转换推断原生响应一定返回 data URI。

### <a id="cpa-errors"></a>错误响应的诊断

先判断错误来自应用、CPA 的调用认证、凭据加载还是上游请求，再决定是否重试。

| 现象 | 重点核对 |
|---|---|
| 401／403 | 本机 key 与上游订阅身份是否混用，令牌时效、权限和实际端点 |
| 400 或参数错误 | 操作端点、请求格式、模型路由、图片和遮罩字段 |
| 429 | 上游额度、暂时冷却，还是 Home 并发准入；按具体来源处理 |
| 超时、断流、5xx | 请求进行到哪一步，是否已经生成但结果未取回 |
| 200 但无有效图像 | 图片条目、编码、实际解码及结果交付 |

若要减少重发，可显式配置 `request-retry: 0`、`max-retry-credentials: 1`、`max-retry-interval: 0`，但它们不是“关闭所有自动重发”：还要检查凭据覆盖、401 后的刷新重发及 HTTP 重定向。所核 Go HTTP client 未配置专门的 CheckRedirect，307／308 配合可重放 POST 仍可能重新提交；前置反向代理不能替上游客户端决定这一行为。

> [重试执行](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/sdk/cliproxy/auth/conductor_execution.go#L132-L158)、[HTTP client](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/internal/runtime/executor/helps/proxy_helpers.go#L28-L61)、[POST 请求准备](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/internal/runtime/executor/codex_executor_request.go#L136-L149)、[401 更新后重发](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/sdk/cliproxy/auth/conductor_execution.go#L576-L584)。这些是版本化源码结论，不是已经执行过的错误注入测试。

### <a id="cpa-observations"></a>实测记录

2026-09-09 的历史验收使用官方 v7.2.155 包，核对了下载校验和构建提交。实例采用独立配置和凭据目录，仅提供访问令牌及账户 ID，未配置 refresh token 或其他刷新来源；原登录文件前后哈希相同。

| 操作 | 请求条件 | 历史结果 |
|---|---|---|
| 生成图片 | JSON 请求，`gpt-image-2`、`n=1`、`size=auto`、`quality=low` | HTTP 200，真实 PNG，已检查视觉内容 |
| 编辑图片 | 相同输出参数；用 JSON 提交单张参考图 | HTTP 200，语义修改达到测试要求 |
| 编辑图片 | 相同输出参数；用 multipart 上传单张参考图 | HTTP 200，语义修改达到测试要求 |
| 实例准入检查 | 未提供本机 key；管理入口按测试条件禁用 | 模型路由 401，管理路由 404 |

当时还限制了账户候选和额外重试，采用非流式调用；临时实例及材料已清理。这里保留测试条件，不将它作为通用部署配置。

> 这组验收没有覆盖 mask、多参考图组合、`n>1`、file ID、1.5／2.5、其他尺寸或质量、流式、长期续期及并发压力；没有验证编辑区域之外逐像素不变，也没有进行同条件性能比较。对应路径见[原生执行器](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/internal/runtime/executor/codex_openai_images.go#L318-L376)。

## <a id="verification"></a>生图接入的验证

验证只需围绕应用真正使用的操作和边界展开，不必每次重新消耗额度运行全套测试。

### <a id="verification-evidence"></a>验证证据的分类

源码证明实现怎样处理，mock 证明模拟条件下的程序行为，真实调用证明指定账户和参数下的实际结果。读到测试文件不等于已经运行测试，一次成功也不证明所有选项或长期稳定性。

### <a id="verification-checklist"></a>功能验收检查表

| 应用需要的能力 | 最小检查重点 |
|---|---|
| 生成 | 实际请求走预期路径，返回图片可解码并可取得 |
| 编辑 | 原图提交正确，修改和保留要求分别检查 |
| 遮罩 | alpha、尺寸和对应原图正确，单独确认区域效果 |
| 特殊输入或模型 | 多图、file ID、透明、流式、新模型分别标明是否验证 |
| 并发和取消 | 多请求实际行为、限流来源、等待取消及任务归属明确 |
| 错误和结果处理 | 畸形输入不误报为上游已执行；不确定结果不盲目重发；输出不过度占用资源或覆盖旧文件 |

先做本地格式和模拟检查，需要真实生成时再取得相应授权。保留脱敏的入口、版本、参数和结果；升级或改变接入方式后，只复验受影响的部分。
