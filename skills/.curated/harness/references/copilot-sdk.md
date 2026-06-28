# Copilot SDK and programmatic harnesses

Use this when deciding whether to drive Copilot through CLI subprocesses, the public SDK client, or an extension attached to a foreground session.

## Two entry points: client vs extension

Verified from the Copilot CLI `1.0.66-1` bundled SDK declarations and npm registry metadata.

`@github/copilot-sdk` and `@github/copilot-sdk/extension` are different surfaces:

| Entry point | Main API | Use it for | Ownership model |
|---|---|---|---|
| `@github/copilot-sdk` | `CopilotClient`, `RuntimeConnection`, `CopilotSession` | Programmatic control from a daemon/orchestrator | Your process owns or connects to a runtime, then creates/sends/resumes sessions |
| `@github/copilot-sdk/extension` | `joinSession()` | Copilot CLI extensions | The foreground Copilot CLI session owns the host process and injects the extension SDK |

Do not collapse these into “the SDK is only for extensions.” The extension entry point is for extensions; the root package is the programmatic runtime-control API.

## Runtime connection modes

`RuntimeConnection` factories observed in `copilot-sdk/types.d.ts`:

```ts
RuntimeConnection.forStdio({ path?: string, args?: readonly string[] })
RuntimeConnection.forTcp({ port?: number, connectionToken?: string, path?: string, args?: readonly string[] })
RuntimeConnection.forUri(url: string, { connectionToken?: string })
```

Design implication:

- `forStdio` is closest to “spawn one child runtime and speak JSON-RPC over stdio.”
- `forTcp` lets the SDK spawn a runtime server and connect to a socket.
- `forUri` connects to an already-running runtime; the SDK does not spawn a process in this mode.

The same declarations warn that CLI-like defaults are unsafe for server-based multi-user applications unless the app opts into an explicit, narrow capability set.

## Session control surface

`copilot-sdk/session.d.ts` exposes the core orchestration methods:

```ts
session.send(promptOrOptions)
session.sendAndWait(promptOrOptions, timeout?)
session.on(handler)
session.setModel(model, options?)
session.abort()
session.disconnect()
```

Important behavioral note from the declaration comments: `sendAndWait` timeout controls how long the caller waits for a response; it does **not** abort in-flight agent work. Use `abort()` when the orchestrator really wants to cancel the turn.

## Protocol and implementation facts

- `SDK_PROTOCOL_VERSION = 3` in `copilot-sdk/sdkProtocolVersion.d.ts` and the bundled implementation.
- The bundled implementation includes `vscode-jsonrpc@8.2.1`, so the SDK client/runtime relation is a JSON-RPC style single connection with typed requests/events.
- Copilot CLI help exposes `--acp` (“Start as Agent Client Protocol server”).
- The bundled `app.js` contains hidden/runtime server flags `--server`, `--ui-server`, and `--managed-server`; treat these as internal unless official docs say otherwise.
- Copilot CLI help exposes `--extension-sdk-path <directory>` for overriding the bundled `@github/copilot-sdk` injected into extension subprocesses.
- npm registry `dist-tags` checked during this refactor: `latest` was `1.0.4`, with `prerelease` and `unstable` tags also present. Re-check before pinning a version in user-facing instructions.

## Harness choice rule of thumb

- If the caller just needs a one-shot answer and can tolerate cold start, CLI subprocesses are simplest.
- If the caller needs streaming events, cancellation, session lifecycle, model switching, or multiple sessions, prefer `CopilotClient` and `RuntimeConnection`.
- If the caller is adding capabilities to a user’s active CLI session, write an extension with `joinSession()`.
