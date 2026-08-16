# Copilot CLI 疑难杂症

> 本页记录 Copilot CLI 中低频、依赖特定会话历史才会出现的问题。这里的 provider 指模型协议适配器，例如 Anthropic Messages 和 OpenAI Responses；它不是 MCP server。

## <a id="mcp-namespace-roundtrip"></a>跨 provider 回放 MCP 调用

> 2026-08-15 | GitHub Copilot CLI 1.0.81-0 | OpenAI Responses API | 本机事件、wire log 与 native runtime 隔离重放

### 症状

- MCP 工具此前已经连续调用成功，server 仍在线，配置也没有变化。
- 会话切换模型或恢复后，发送任何新消息都立即失败：

  ```text
  CAPIError: 400 Missing namespace for function_call 'portal-remote_exec'.
  It does not exist in the default namespace.
  Round-trip the model's function_call item with its namespace field included.
  ```

- 错误发生在模型开始生成内容之前，MCP server 没收到新调用。
- 新会话通常正常；坏会话此后每轮都报同一个 400。

这个组合容易把排查带向 MCP 工具名、server 配置或具体模型。实际问题在 Copilot CLI 对既有会话历史的转换。

### 排查关键转折

#### 对照持久化事件与 wire 请求

同一条 MCP 调用在持久化的 `assistant.message` 事件里信息完整：

```json
{
  "toolCallId": "toolu_...",
  "name": "portal-remote_exec",
  "mcpServerName": "portal",
  "mcpToolName": "remote_exec"
}
```

但 Copilot CLI 发给 OpenAI Responses API 的历史项变成：

```json
{
  "type": "function_call",
  "call_id": "toolu_...",
  "name": "portal-remote_exec"
}
```

缺少的正是：

```json
{
  "namespace": "portal"
}
```

同一请求里，原本由 OpenAI Responses 产生的 `call_*` 历史项带有 `"namespace": "portal"`，而由 Anthropic 产生的 `toolu_*` 历史项全部没有。由此可以排除 MCP server：请求尚未到达工具执行阶段，字段是在 CLI 内部重建历史时丢失的。

#### 沿 app.js 找到切模重写入口

1.0.81-0 的 `app.js` 在模型变化或 session resume 后调用 native runtime：

```text
sessionProjectionRewriteChatHistoryForModelJson(
  sessionId,
  targetModel.supports.customTools === true,
  targetModel.supports.toolCallIdStyle
)
```

故障目标模型的实际配置是 `customTools=true`，没有设置 `toolCallIdStyle`。这说明需要复现的不是任意猜测组合，而是 `(true, undefined)` 这一条真实路径。

#### 直接重放 native runtime

`runtime.node` 是 stripped Rust 二进制，没有可读的完整上游源码，但保留了 N-API 导出和内嵌源码模块名。用它自己的导出在隔离进程中执行：

1. `sessionReplaceEventsSyncJson` 载入故障发生前的真实事件；
2. `sessionProjectionChatMessagesJson` 读取事件投影得到的通用 chat history；
3. `sessionProjectionRewriteChatHistoryForModelJson(sessionId, true, undefined)` 执行真实切模重写；
4. 再读一次投影结果。

结果如下：

| 调用来源 | 持久化事件 | 投影后的 assistant message |
|---|---|---|
| OpenAI Responses `call_*` | `mcpServerName: "portal"` | 有 `serverTools.functionCallNamespaces[callId] = "portal"` |
| Anthropic `toolu_*` | `mcpServerName: "portal"` | 有 `tool_calls`，但完全没有 `serverTools` |

执行真实的 `(true, undefined)` 重写后，这个差异保持不变。二进制内嵌的相关 Rust 模块名包括：

- `src/runtime/src/session/event_projection.rs`
- `src/runtime/src/session/conversation_state.rs`
- `src/runtime/src/model/anthropic_conversion.rs`
- `src/runtime/src/model/responses_transport.rs`

这不是只看报错反推：事件投影和切模重写函数均由故障版本自己的 native runtime 执行，能够稳定复现缺字段状态。

### 根因

Copilot CLI 的通用 `assistant.message` 事件已经在每个 MCP tool request 上保存：

```text
toolCallId + mcpServerName + mcpToolName
```

但 native 事件投影在处理 Anthropic 消息时，只把请求转成普通 `tool_calls`，没有同步构造：

```text
serverTools.functionCallNamespaces[toolCallId] = mcpServerName
```

OpenAI Responses 消息本身会携带这张映射，所以同会话中早先的 `call_*` 正常；Anthropic 消息没有 OpenAI 专用 envelope，投影器又没有从 provider-neutral 的 `mcpServerName` 补齐映射，于是跨 provider 回放时信息丢失。

Responses transport 随后只能把这些调用当成 default namespace 下的普通 function。CAPI 已把 `remote_exec` 注册在 `portal` namespace，看到扁平名 `portal-remote_exec` 却没有 namespace 字段，便拒绝整个请求。模型切换只是让历史进入另一种 wire format 的触发条件，不是模型本身的错误。

### 修复验证

在内存中的事件副本上，对每条 `assistant.message` 执行：

```text
for toolRequest in toolRequests:
    if toolRequest.mcpServerName:
        functionCallNamespaces[toolRequest.toolCallId] =
            toolRequest.mcpServerName
```

保留原来的 `serverTools.provider`；不存在 envelope 时，再按该消息原 provider 创建。把修复后的事件重新交给同一版 native runtime，并再次执行 `(true, undefined)` 切模重写：

- 8 条 Anthropic assistant message 被补齐；
- 共修复 9 个 MCP 调用；
- 13 个 `portal-remote_exec` 历史调用最终全部能按 call ID 找到 `"portal"`；
- 缺失数为 0。

因此可靠的上游修复应放在事件投影层：无论调用来自哪个模型协议，只要 `toolRequest.mcpServerName` 存在，就建立 namespace 映射。若 `toolCallIdStyle` 重写了 call ID，还必须同步重写映射的 key。Responses serializer 再增加一次 fallback 可以防御旧会话，但不能代替投影层保存完整语义。

### 现有会话恢复

修改前必须退出持有该 session 的 Copilot CLI 进程，并备份 `events.jsonl`。然后只处理满足以下条件的事件：

1. `type == "assistant.message"`；
2. `toolRequests` 中存在 `toolCallId` 和 `mcpServerName`；
3. `serverTools.functionCallNamespaces` 缺少该 call ID。

把缺失项合并进去，不覆盖已有映射，也不改 `toolRequests`、tool result 或 call ID。修复后重新 resume；若 CLI 仍在运行时直接改文件，它可能用内存状态或后续 flush 覆盖修改。

### 教训

- **扁平工具名不是 namespace。** `portal-remote_exec` 只是客户端显示名；Responses API 仍要求独立的 `"namespace": "portal"`。
- **事件里有字段，不代表 wire 上仍有。** 排查 agent harness 要同时看持久化事件、内存投影和最终请求，单看任何一层都可能误判。
- **模型切换常是协议转换触发器。** 只有旧 provider 产生的特定历史项出错时，应先查跨 wire-format 回放，而不是把问题归因于新模型。
- **闭源 native runtime 仍可做代码级验证。** stripped 二进制若导出了纯转换函数，可以用真实事件隔离重放，比只读错误栈或猜 minified JavaScript 更可靠。
