# Agent harness architecture patterns

A harness is the layer that owns an agent runtime: it starts or attaches to the agent, injects context/tools, observes events, handles cancellation, and persists state. Pick the shape by control needs, not by which transport is fashionable.

## CLI subprocess one-shot

Examples: `subprocess.run(["copilot", "-p", ...])`, shelling out to Codex/Claude/Copilot for one prompt.

- Strengths: easiest to build, works with existing CLIs, no protocol integration.
- Failure modes: cold-start per run, weak streaming/abort semantics, hard to inspect internal state, awkward multi-session orchestration.

Use it for scripts and low-frequency automation, not for an always-on orchestrator.

## SDK client / app-server style

Examples: Copilot `CopilotClient` with `RuntimeConnection`, or an app-server style runtime that a controller attaches to.

- Strengths: orchestrator owns runtime lifecycle, can create/resume sessions, subscribe to events, switch models, and abort turns.
- Failure modes: tighter coupling to SDK protocol versions; more responsibility for auth, capability isolation, and process cleanup.

Use it when the harness is a product component rather than a shell wrapper.

## Extension-host style

Examples: VS Code extensions, Copilot SDK `joinSession()`, Zotero plugins.

- Strengths: host owns lifecycle and UI; extension contributes commands, tools, hooks, or panels inside the host’s permission model.
- Failure modes: extension cannot assume full process control; API surface is constrained by what the host injects.

Use it when the user is already inside a host application and the feature should feel native to that host.

## JSON-RPC single connection

Examples: Language Server Protocol and Copilot SDK internals via `vscode-jsonrpc`.

- Strengths: one bidirectional channel for requests, notifications, events, cancellation, capability negotiation, and versioning.
- Failure modes: schema/version compatibility matters; long-lived connection health becomes part of reliability engineering.

Use it for tight host/plugin cooperation where HTTP endpoints plus webhooks would split control, data, and events across too many mechanisms.

## HTTP/webhook microservice style

- Strengths: easy to curl, deploy, scale, and debug with commodity tooling.
- Failure modes: often worse for rich host/plugin cooperation; cancellation, streaming, backpressure, and capability negotiation usually need extra side channels.

Use it for coarse service boundaries, not as the default plugin ABI for a single local harness.

## Case-study note

For one recent QA ↔ qatlas-lean design, the chosen direction was “all JSON-RPC single connection, plugin zero HTTP, browser content via host/core relay.” That is a useful case study: it optimizes tight host/plugin control and avoids HTTP side channels. It is not a universal rule; a simpler CLI subprocess or HTTP boundary can still be correct for smaller or looser integrations.
