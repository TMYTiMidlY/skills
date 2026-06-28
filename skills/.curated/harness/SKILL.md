---
name: harness
description: Agent harness / runtime architecture knowledge hub. Use when debugging or designing Copilot CLI / Copilot SDK / Claude Code / Codex harnesses, MCP/tool injection, session storage/export, extension-host vs SDK-client vs CLI-subprocess control, JSON-RPC plugin protocols, or programmatic coding-agent orchestration.
---

# Harness

Use this skill for agent runtime and harness questions: how a coding agent is launched, controlled, extended, connected to tools, resumed, cancelled, and observed.

## Scope

- Copilot CLI internals, SDK entry points, MCP config injection, session/export behavior, and reverse-engineering notes.
- Claude Code and Codex runtime models when comparing harness tradeoffs.
- Designing a daemon/orchestrator that programmatically drives coding agents.
- Choosing between CLI subprocess, SDK client, extension-host, JSON-RPC, and HTTP/webhook integration styles.

## References

- [Copilot CLI runtime notes](references/copilot-cli.md): process model, shell/tool env, permissions, terminal behavior, Git auth, retry patch, and in-flight steering.
- [Copilot discovery, instructions, hooks, and skills](references/copilot-discovery.md): walk-up behavior, custom instructions, hooks, and skill loading.
- [Copilot MCP configuration](references/copilot-mcp.md): `.mcp.json`, config precedence, env interpolation pitfalls, and per-run MCP profile injection.
- [Copilot SDK and programmatic harnesses](references/copilot-sdk.md): `CopilotClient`, `RuntimeConnection`, `joinSession()`, protocol facts, and client-vs-extension distinction.
- [Copilot sessions and exports](references/copilot-sessions.md): resume IDs, session-state, and `/share html` export internals.
- [Agent harness architecture patterns](references/harness-patterns.md): CLI subprocess, SDK client, extension host, JSON-RPC, and HTTP/webhook tradeoffs.
- [Claude Code harness notes](references/claude-code.md) and [Codex harness notes](references/codex.md): placeholders for cross-harness comparisons.

## Boundary

General local software operations still belong in `software`. This skill owns coding-agent runtime/harness internals and cross-harness architecture comparisons.
