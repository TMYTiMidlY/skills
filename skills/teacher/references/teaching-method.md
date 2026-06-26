# Teaching method · the five-layer spine in detail

This is the playbook for each part of the six-part spine. Use it when you're not sure whether a draft of the intuition, walkthrough, or trap is good enough. Each section has a "good" version and a "bad" version drawn from a real concept so the difference is concrete.

---

## Intuition

**Job:** Give the reader a *reason to care* before any code shows up. Frame the concept as a solution to a problem they could have felt themselves.

**Rules:**

- Lead with the problem, not the mechanism.
- One sentence, two if the concept genuinely needs both a *what* and a *why*. Never three.
- A metaphor is allowed if it doesn't collapse under one inch of scrutiny.
- Avoid jargon that is more obscure than the concept itself ("a referencing environment" is worse than "the variables it could see when it was born").

### Examples

**Concept: closure**

- Good: *"A closure is a function that remembers the variables from the place it was created — even after that place is gone."*
- Bad: *"A closure is a function paired with its lexical environment."* (defines a term using terms)
- Bad: *"Closures are like a backpack the function carries around with old toys in it."* (metaphor too cute, hides the actual mechanism)

**Concept: CAP theorem**

- Good: *"When a distributed system gets cut in half by a network failure, you have to choose: keep answering with possibly stale data, or stop answering until you're back in touch. You can't have both."*
- Bad: *"CAP states that of Consistency, Availability, and Partition tolerance, a distributed system can guarantee only two."* (true but doesn't say *why anyone would care*)

**Concept: GIL**

- Good: *"Python lets only one thread run Python bytecode at a time — so threads help with waiting (I/O) but not with computing (CPU)."*
- Bad: *"The Global Interpreter Lock is a mutex in CPython that serializes access to Python objects."* (correct, but answers no question)

---

## Example — runnable, or structured pseudocode

**Job:** Give the reader something concrete enough to *predict the behavior of* — either by running it themselves, or by reading the shape annotations and following the control flow.

There are two modes. The choice is governed by [SKILL.md](../SKILL.md)'s "Which form to pick" table; the per-mode rules are below.

### Mode A · Runnable example

**When:** language features, small algorithms, APIs. The concept fits in code that you can paste into a REPL.

**Rules:**

- 5–20 lines. If you're over 20, the example is doing too much.
- Runs as-is. No `# assume foo is defined`. No `// in a real app you would…`.
- Standard library only, unless the concept *is* the library.
- Naming carries weight. `make_counter` beats `f`. `seen_users` beats `s`.
- Show the seam. When teaching `reduce`, show the `for`-loop equivalent next to it — the reader needs to see what `reduce` *replaces*.
- One `print()` is fine. Three `print()`s with labels showing intermediate state is sometimes the whole point.

#### Examples — runnable

**Concept: closure**

Good:

```python
def make_counter():
    count = 0
    def increment():
        nonlocal count
        count += 1
        return count
    return increment

counter = make_counter()
print(counter())  # 1
print(counter())  # 2
print(counter())  # 3
```

Why: 11 lines, runs anywhere, `make_counter` and `increment` and `count` all name themselves, and the three `print`s prove the captured `count` survives across calls.

Bad:

```python
f = lambda: (lambda: 1)()
print(f())
```

Why: technically a closure, but it doesn't *demonstrate* the thing closures are useful for — surviving state across calls.

**Concept: GIL**

Good: two parallel snippets — one CPU-bound (threads don't help), one I/O-bound (threads do help) — with timing on each. The contrast *is* the lesson.

Bad: a single thread spinning a counter. Shows threads, not the GIL.

---

### Mode B · Structured pseudocode

**When:** the concept's value is in the wiring, state, or control flow — not in being runnable. Three flavors based on concept domain (full rules in [`code-style-for-teaching.md`](code-style-for-teaching.md) §10):

- **Flavor 1 — DL** (architectures, training algorithms, kernel concepts). PyTorch syntax + tensor shape annotations. Examples: MoE, GRPO, FlashAttention.
- **Flavor 2 — Protocols / state machines.** Named participants + message arrows + state transitions. Examples: Raft, TCP, OAuth.
- **Flavor 3 — Complex algorithms / data structures.** Code + stated invariants + concrete trace. Examples: B+ tree, union-find.

The common case across all three: the runnable form would drag in scaffolding (model + optimizer + dataloader, network setup, full database) that buries the concept.

**Rules:**

- Valid Python / PyTorch syntax. The reader's eye still reads it as code. **Never use natural-language pseudocode** (`FOR each token DO …`) — it forfeits the precision that made code worth using in the first place.
- Mark it: `# pseudocode — illustrative, not runnable` at the top of the block.
- Drop everything that isn't the concept: imports, `class Foo(nn.Module):` scaffolding, `def __init__`, distributed init, dataloader setup.
- **Annotate tensor shapes inline.** For architecture and algorithm concepts, the shape transitions *are* the lesson. `# [B, T, D] → [B, T, n_experts]` next to one line of code does more work than three sentences of prose.
- Keep control flow real. Every `for`, `if`, `mask = ...`, `topk(...)`, `softmax(...)`, `gather(...)` appears. That's the algorithm. Eliding it ("...then route to experts...") is failure.
- Reference unimplemented helpers by speaking name. `advantages = compute_grpo_advantages(rewards)` is fine — do not expand a helper unless the helper *is* the concept.
- Length budget loosens to 15–35 lines. Architecture diagrams in code are inherently longer than language features.

#### Examples — pseudocode

**Concept: Mixture of Experts (MoE) forward pass**

Good:

```python
# pseudocode — illustrative, not runnable
# B = batch, T = tokens, D = model dim, E = num experts, K = top-k experts per token

def moe_forward(x, experts, gate, k=2):
    # x: [B, T, D]
    gate_logits = gate(x)                       # [B, T, E]
    top_w, top_i = gate_logits.topk(k, dim=-1)  # [B, T, K], [B, T, K]
    top_w = top_w.softmax(dim=-1)               # weights sum to 1 per token

    out = zeros_like(x)                         # [B, T, D]
    for expert_id, expert in enumerate(experts):
        # mask of tokens routed to this expert (any of the K slots)
        mask = (top_i == expert_id).any(dim=-1)         # [B, T]
        if not mask.any():
            continue
        tokens = x[mask]                                # [N, D] — only routed tokens
        weight = top_w[top_i == expert_id]              # [N]    — gating weight for this expert
        out[mask] += weight.unsqueeze(-1) * expert(tokens)
    return out
```

Why: every shape comment is load-bearing. The reader sees `[B, T, D] → [B, T, E]` (gating) → `[B, T, K]` (top-k) → `[N, D]` (dispatched per expert) → back to `[B, T, D]` (combine). The *transformation of shapes* is the architecture. Helpers like `zeros_like` are speaking names, no expansion needed.

Bad — natural-language pseudocode:

```
FOR each token t in batch:
    compute gate scores over all experts
    pick top-k experts
    FOR each chosen expert e:
        compute e(t)
        weight by gate score
    sum the weighted outputs
```

Why bad: no shapes, no batching, doesn't show *how dispatch is vectorized*, can't be diffed against a real implementation. Reads as if MoE is a `for` loop over tokens — which is exactly the wrong mental model (it's vectorized routing, not per-token iteration).

Bad — trying to make it runnable:

```python
import torch, torch.nn as nn
class Expert(nn.Module):
    def __init__(self, d):
        super().__init__()
        self.fc = nn.Linear(d, d)
    def forward(self, x):
        return self.fc(x)
# ... 40 more lines of scaffolding ...
```

Why bad: 60 lines to demonstrate a 12-line idea. The reader's attention is now on `nn.Module` boilerplate instead of routing.

**Concept: GRPO advantage computation**

Good:

```python
# pseudocode — illustrative, not runnable
# G = group size (multiple completions per prompt)

def grpo_advantages(rewards):
    # rewards: [B, G] — G sampled completions per prompt
    mean = rewards.mean(dim=-1, keepdim=True)     # [B, 1]
    std  = rewards.std(dim=-1, keepdim=True)      # [B, 1]
    advantages = (rewards - mean) / (std + 1e-8)  # [B, G] — group-relative
    return advantages

# how it plugs into the policy gradient step:
# (compare with PPO: PPO uses a learned value baseline V(s);
#  GRPO uses the group's own mean — no critic network needed)
advantages = grpo_advantages(rewards)             # [B, G]
loss = -(advantages * log_probs).mean() + kl_penalty * kl(policy, ref)
```

Why: shows the *one thing* that makes GRPO different from PPO (group mean as baseline, no critic), with shapes that explain why "G" exists in the first place. The "how it plugs in" block shows the seam — critical for a concept whose value is *what it replaces*.

---

### Choosing between Mode A and Mode B

Don't try to please both. If the concept fits in 15 runnable lines, use Mode A — pseudocode is overkill and feels evasive. If the concept needs a 60-line scaffold to run, use Mode B — runnable will bury the lesson under setup.

If you're genuinely torn (rare), default to Mode B with a note: "the runnable version needs ~40 lines of model + optimizer setup, which would crowd out the algorithm. Here's the algorithm in pseudocode; ask if you want the full runnable version."

---

## Walkthrough

**Job:** Translate the code into a few labeled *purpose units* so the reader can predict what each section does without running it.

**Rules:**

- 2–4 segments per example block. More than 4 means the example is doing too much.
- Quote each segment first, then explain. Don't make the reader scroll back up.
- Explain *purpose*, not *syntax*. "This binds `count` to 0" is bad. "We need a place to store the count that survives between calls — `count = 0` is that place, sitting inside `make_counter`'s scope" is good.
- If a segment has a subtle line (e.g. `nonlocal count`), call it out — that's exactly where confusion lives.

### Example walkthrough — closure

> ```python
> def make_counter():
>     count = 0
> ```
>
> A factory. `count = 0` lives inside `make_counter`'s scope — not at module level — which is what makes each counter independent.
>
> ```python
>     def increment():
>         nonlocal count
>         count += 1
>         return count
>     return increment
> ```
>
> `increment` is defined *inside* `make_counter`, which means it can see `count`. `nonlocal` is the keyword that says "I want to *modify* the `count` from the enclosing scope, not create a new local one." Returning `increment` is the moment the closure is born: the function leaves the factory, but the link to `count` goes with it.
>
> ```python
> counter = make_counter()
> print(counter())  # 1
> print(counter())  # 2
> ```
>
> `make_counter` has already returned by the time we call `counter()` the first time — but `count` is still alive, because `increment` is holding it.

Notice the walkthrough never says "the `def` keyword defines a function." That's syntax noise. It says *why* each chunk is there.

---

## Trap

**Job:** Show the bug the concept exists to prevent, or the wrong intuition newcomers reach for. This is the layer that makes the concept feel *load-bearing* rather than arbitrary.

**Two flavors — pick whichever lands harder:**

### (a) Counterexample

"If closures didn't work this way, here's what would happen:"

```python
# imaginary world without closures
count = 0
def increment():
    count += 1   # NameError: count not captured
    return count
```

One snippet, one line of commentary. Done.

### (b) Common mistake

The version that *looks* right but isn't, and the explanation of why.

```python
funcs = [lambda: i for i in range(3)]
print([f() for f in funcs])  # [2, 2, 2]  — not [0, 1, 2]
```

> All three lambdas captured the *same* `i`, not its value at creation time. By the time you call them, the loop is done and `i == 2`. Fix: `lambda i=i: i` to bind eagerly.

This single trap teaches more than a paragraph on "late binding."

---

## Pointers — where to go from here

**Job:** Hand the reader a map, not a lesson.

**Rules:**

- 2–3 bullets. Not 5. Not 10.
- One line each. **Do not expand.** If you find yourself writing a second sentence, cut it.
- Each bullet should be either (a) a deeper layer of the same concept or (b) an adjacent concept the reader can now reach because of what they just learned.
- Linking words: "—" or just a name. Avoid "you should also study…" — that's a lecture voice.

### Example — after a closure lesson

> — Decorators are closures wearing a hat: a function that takes a function and returns a closure over it.
> — `nonlocal` (mutating) vs. just reading: closures can *read* enclosing variables without `nonlocal`; they need it only to reassign.
> — In JavaScript, every function is a closure. In Java, lambdas can only close over *effectively final* variables — same rule, different syntax.

Three pointers. The reader can pick one and ask a follow-up. That's the design.

---

## Test questions

**Job:** Convert the lesson from "I just read about X" into "I could answer if someone asked me about X." Real checks of understanding don't ask "explain X" — they ask sideways questions that probe whether you actually got it. The test-questions section simulates that.

A note on framing: present the section simply as "test questions" or just numbered questions. Don't label them as interview questions or set up an interview scenario — the phrasing of the questions themselves carries the externally-shaped quality, no scenery needed.

**Rules:**

- 2–3 questions. Not 1 (too thin), not 5 (becomes a quiz).
- Increasing difficulty across the questions: **recall/contrast → read the code/trace shapes → design/trap/debug**.
- Phrase as an examiner would — concrete, specific, sometimes adversarial. Not "do you understand monads?" but "show me a `for` loop that's a hidden monad."
- One `> Hint:` line per question — a pointer to where in the lesson the answer lives, not the answer itself. The hint should make the reader feel "oh, I know where to look," not "oh, the answer is X."
- **No answers given by default.** If the reader replies with an attempt, then walk through it.
- The kinds of questions vary slightly by domain but the structure does not:
  - Language features / algorithms / data structures → "predict the output," "modify the example," "trace the recursion."
  - ML architectures / training algorithms → "what's the shape after X," "what's the FLOPs cost," "what breaks if Y."
  - Systems / protocols → "what happens if message Z is lost," "what's the failure mode under partition."

### Why no answers up front

Giving the answer immediately defeats the purpose. The reader's eye will skim the answer and feel like they understood, without the mental work of trying to retrieve it themselves. Withholding the answer creates productive friction — the reader either knows it (great, validated), kind of knows it (great, surfaces the gap), or has no idea (great, now they can ask). All three outcomes are better than a passive read.

### Examples — good and bad

**Concept: closure**

Good:

> 1. Without using the word "scope," explain why this prints `2 2 2` instead of `0 1 2`:
>
>    ```python
>    funcs = [lambda: i for i in range(3)]
>    print([f() for f in funcs])
>    ```
>
>    > Hint: think about *when* `i` is read versus *when* it's written.
>
> 2. Rewrite `make_counter` so that two counters share the same underlying count (i.e., calling either one advances both). What changed and why?
>
>    > Hint: the captured variable has to live somewhere shared.
>
> 3. In Java, lambdas can only close over `final` (or effectively final) variables. Why does Python not need that restriction? What does Python pay for the flexibility?
>
>    > Hint: compare how the two languages represent captured variables.

Why good: Q1 reuses the trap as a question (a very common pattern). Q2 is "modify the example" — the reader has to actually internalize the structure to rewrite it. Q3 is the cross-language trade-off question that probes senior-level understanding. Hints point at *concepts*, not answers.

Bad:

> 1. What is a closure?
>
>    > Answer: A function that remembers its enclosing scope.
>
> 2. Are closures useful? Yes/No.

Why bad: Q1 is a recall question with the answer handed back — zero teaching value, and not a real interview phrasing. Q2 is binary and useless. No drill, no friction.

**Concept: GRPO**

Good:

> 1. In one sentence: what's the single component that GRPO removes from PPO, and what does it use as a substitute?
>
>    > Hint: think about what PPO needs to *train* in addition to the policy.
>
> 2. Look at the pseudocode. After `grpo_advantages(rewards)`, what's the shape of `A`? Why does the next line need `A.unsqueeze(-1)`?
>
>    > Hint: compare it with `log_pi`'s shape.
>
> 3. Suppose your reward model gives binary rewards (0 or 1) and you use G=4. In what fraction of training steps will at least one prompt have zero gradient signal? What two knobs could you turn to reduce that?
>
>    > Hint: zero gradient happens when all four samples have the same reward.

Why good: Q1 nails the recall/contrast layer ("what's the delta"). Q2 forces the reader back into the code and the shape transitions — verifies they actually read the example rather than skimmed it. Q3 is a trade-off question that tests whether the trap actually stuck.

Bad:

> 1. Explain GRPO. (yes, just like that, the whole thing)
> 2. Is GRPO better than PPO?
> 3. Code up GRPO in PyTorch.

Why bad: Q1 is a recall dump, not a probe. Q2 is unanswerable without context (better at what?). Q3 is a homework assignment, not a drill.

**Concept: Mixture of Experts**

Good:

> 1. In a top-2 MoE layer with 8 experts, what fraction of experts process any given token? What does that imply about FLOPs at inference time, compared to a dense layer of the same hidden size?
>
>    > Hint: count tokens per expert, then count parameters touched.
>
> 2. From the pseudocode, walk through the shape of `out` across the loop: where does it get allocated, where does it accumulate, where does it return.
>
>    > Hint: read the comments on `out`, `mask`, `tokens`, and the `+=` line.
>
> 3. Imagine training a top-2 MoE and observing that one expert is receiving 70% of the tokens. What's broken? What loss term is designed to prevent this, and roughly how does it work?
>
>    > Hint: load balancing isn't free — there's an auxiliary loss.

Why good: Q1 is the FLOPs question that MoE understanding usually pivots on. Q2 forces shape tracing through the dispatch/combine pattern. Q3 directly addresses the trap (load imbalance).

### Choosing the three questions

Use this allocation as a default:

| Difficulty | Source | Test |
|---|---|---|
| Q1 — recall / contrast | intuition + trap | Can they articulate what the concept is and what it isn't? |
| Q2 — read the code / trace | example + walkthrough | Can they read the example, or did they skim it? |
| Q3 — design / trap / debug | trap + pointers | Can they apply it to a situation that wasn't in the lesson? |

Q3 is the most valuable and the hardest to write — it must require the reader to *combine* something from the trap (a known failure mode) with something they have to reason about themselves. If Q3 can be answered by quoting one line from the lesson, it's actually a Q1.

### Why this layer is not “理解检查” by another name

The user explicitly said earlier they didn't want a "do you understand?" check. Test questions are not that. The difference:

- “理解检查” = a generic prompt aimed at the reader's confidence ("did this make sense?"). Subjective, low information.
- Test questions = a concrete, externally-shaped task ("here's the exact question someone could pose to check this"). Objective, high information, transferable.

The reader can choose to engage or not. If they read the questions and feel "yeah, I could answer all three" — that's a useful signal. If they read Q3 and think "no idea" — also a useful signal, and the hint tells them where to go.

---

## When a concept is too big for one lesson

Some concepts ("the transformer architecture", "how TCP works", "the borrow checker") cannot be done justice in one five-layer pass. The move is:

1. Name the sub-concepts up front: *"Transformers have three core pieces — attention, positional encoding, and feed-forward layers. We'll do attention first."*
2. Run the full five-layer lesson on the smallest sub-concept.
3. End with an offer: *"Want me to do positional encoding next?"*

Do not try to compress. A rushed lesson is worse than a partial one.

---

## What "good" looks like overall

Read the finished lesson back as if you knew nothing about the concept. Ask:

- Did the intuition make me want to read on?
- Could I paste the example and see it work?
- Does the walkthrough let me predict what each chunk does without reading the code again?
- Does the trap explain *why I'd ever need this*?
- Do the pointers give me one obvious next thing to ask about?

If all five are yes, ship it.
