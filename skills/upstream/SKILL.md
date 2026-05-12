---
name: upstream
description: Prepare a high-signal handoff from Codex to a slower web-only reasoning model such as GPT-5.4 Pro or GPT-5.2 Pro, then resume local execution after the reply comes back. Use when the user wants deep planning, brainstorming, or architecture review that benefits from a Pro model, but Codex must first gather repository context, existing files, prior artifacts, environment details, and local smoke-test evidence.
---

# Upstream

## Overview

Use this skill to split work into two phases:

1. Codex gathers evidence locally and compresses it into a handoff packet.
2. The web Pro model reasons on that packet while Codex stays responsible for execution, validation, and reality-checking.

The point is not to dump the entire repo into the web app. The point is to send a compact, evidence-backed brief that gives the Pro model enough context to think well without wasting its slow response budget.

Default to Codex built-in tools for context collection. Use the helper script only when it is the fastest way to produce a compact snapshot or clipboard-ready packet.

## Workflow

### 1. Understand the real ask

Start by rewriting the user's request into an operational problem statement:

- target outcome
- constraints
- what is ambiguous
- what must be verified locally
- what kind of help is actually needed from the Pro model

Do not hand off work that Codex should just do directly. Use the Pro model only for the part that truly benefits from deeper planning, synthesis, or brainstorming.

### 2. Collect local evidence first

Inspect the real workspace before drafting the handoff:

- relevant files and directories
- existing docs, tickets, reviews, logs, notes, or experiment artifacts
- repository state and branch status
- runtime and environment details
- commands that are likely to matter later

Prefer direct evidence over assumptions. Summarize code from the actual files, not from memory.

Prefer built-in reads first:

- inspect specific files directly
- list the relevant directories
- check git status or branch when it matters
- probe the runtime with small targeted commands

Use the helper script only when a quick workspace snapshot would help, when many focus paths need a compact summary, or when the user wants clipboard-ready output:

```bash
python3 scripts/collect_handoff_context.py --root /path/to/repo
```

If you already know the high-value files, use repeated `--focus path` flags to narrow the output:

```bash
python3 scripts/collect_handoff_context.py \
  --root /path/to/repo \
  --focus README.md \
  --focus src \
  --focus tests
```

If the user wants a ready-to-paste packet copied into the terminal clipboard, add `--copy`.
Use `--quiet` if you want clipboard-only behavior without echoing the same payload to stdout.

```bash
python3 scripts/collect_handoff_context.py \
  --root /path/to/repo \
  --focus README.md \
  --copy \
  --quiet
```

Read [references/handoff-template.md](references/handoff-template.md) before composing the final packet.

### 3. Run only cheap local validation

The web Pro model cannot execute commands. Codex must do the minimum validation needed to ground the handoff:

- smoke tests
- lints
- one representative command path
- environment probes
- reproduction steps for the current bug or limitation

Keep this scoped. Do not burn time on full validation before the Pro model has even helped shape the plan, unless the user explicitly asks for that.

For each command you run, keep:

- exact command
- whether it passed or failed
- the one-line conclusion
- the most relevant output excerpt or error

### 4. Build the Pro-model handoff packet

Produce a compact packet with these sections:

1. Problem statement
2. Goal and success criteria
3. Constraints and non-goals
4. What Codex already verified locally
5. Key files and their roles
6. Current hypotheses or tradeoffs
7. Specific questions for the Pro model
8. Required response format

Use the template in [references/handoff-template.md](references/handoff-template.md).

Do not paste giant files. Summarize aggressively and include only short excerpts when necessary.

### 5. Ask the Pro model for thinking, not execution

Frame the web prompt so the Pro model does what it is good at:

- compare options
- propose architectures
- identify blind spots
- sequence a plan
- challenge assumptions
- design experiments

Do not ask it to claim it ran tests, inspected files it has not seen, or validated behavior it cannot observe.

### 6. Resume in Codex after the Pro reply

Once the user brings back the Pro-model answer:

- treat it as a proposal, not as truth
- map every recommendation to local files and constraints
- reject parts that conflict with observed code or test evidence
- execute the good parts locally
- run the real validation here

Then give the user a grounded conclusion:

- what from the Pro reply is worth keeping
- what was incorrect or unsupported
- what you changed or plan to change next

## Output Standard

When this skill is active, default to three deliverables:

1. `Local findings`
2. `Pro handoff packet`
3. `Post-reply execution plan`

If the user only asked for preparation, stop after the first two.

## Guardrails

- Do not ask the Pro model to browse fake context or infer missing repository facts.
- Do not offload command execution or testing to the Pro model.
- Do not bloat the handoff with low-signal logs or whole-file dumps.
- Do not accept the Pro reply uncritically; validate it against the real workspace.
- Do not overwrite the user's current plan if the local evidence contradicts the Pro recommendation.
- Do not run the helper script automatically when a few direct built-in tool reads are enough.
