# Pro Handoff Template

Use this template when preparing a prompt for a web-only Pro model.

Keep the packet compact. The Pro model is slow, and it only sees what you paste.

## Packet

```text
You are helping with a complex engineering/research planning task.

Task:
[One paragraph stating the real problem.]

Goal:
[What a good answer must achieve.]

Constraints:
- [constraint]
- [constraint]

Non-goals:
- [non-goal]

Local evidence gathered by Codex:
- Files reviewed:
  - [path]: [1-line role]
  - [path]: [1-line role]
- Environment:
  - [runtime/tooling fact]
  - [runtime/tooling fact]
- Smoke tests or probes:
  - `[command]` -> [pass/fail], [1-line conclusion]
  - `[command]` -> [pass/fail], [1-line conclusion]
- Existing artifacts:
  - [log/checkpoint/doc/review and why it matters]

Current hypotheses or options:
- [option A]
- [option B]

What I need from you:
1. [question]
2. [question]
3. [question]

Response requirements:
- Base your reasoning only on the context above.
- Call out assumptions explicitly.
- Do not claim to have run tests or inspected files beyond what is shown.
- Prioritize concrete tradeoffs and an execution order.
- End with a short recommended plan.
```

## Return Shape To Ask For

Ask the Pro model to answer in this shape:

```text
1. Best interpretation of the problem
2. Main risks or blind spots
3. Comparison of options
4. Recommended plan
5. Assumptions that need local verification
6. Questions that remain unresolved
```

## After The Reply Comes Back

Codex should convert the reply into:

1. accepted recommendations
2. rejected recommendations with reasons
3. concrete file or command changes
4. real validation steps to run locally
