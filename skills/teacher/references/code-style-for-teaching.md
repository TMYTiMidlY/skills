# Code style for teaching

Teaching code is not production code. Production code optimizes for *maintenance across a team over years*. Teaching code optimizes for *a stranger understanding the idea in two minutes*. The trade-offs are different, and habits from one mode actively hurt the other.

This file captures the rules. When in doubt, ask: "would this line help or distract a reader meeting this concept for the first time?"

---

## 1. Names say what they mean

Production code can use `u`, `f`, `x` because the file context tells you what they are. A teaching example has no surrounding context — the names *are* the context.

Bad:

```python
def f(n):
    a = 0
    for i in range(n):
        a += i
    return a
```

Good:

```python
def sum_through(n):
    total = 0
    for current in range(n):
        total += current
    return total
```

The good version teaches you the algorithm without needing a single comment.

---

## 2. Show the seam

When the concept *replaces* something, show what it replaces. The reader learns by diffing.

Teaching `reduce`:

Bad:

```python
from functools import reduce
total = reduce(lambda acc, x: acc + x, numbers, 0)
```

Good:

```python
# the loop you would have written:
total = 0
for x in numbers:
    total = total + x

# the same thing, written with reduce:
from functools import reduce
total = reduce(lambda acc, x: acc + x, numbers, 0)
```

Now `reduce` has *meaning* — it's the loop, compressed. The bad version asks you to learn `reduce` cold.

Teaching `async`/`await`: show the blocking version first, then the async version. Teaching list comprehensions: show the `for` loop first.

---

## 3. `print()` is a teaching tool

Production code with eight `print`s is a code smell. Teaching code with eight `print`s might be the whole point — the prints are *the demonstration*.

Bad (production habit creeping in):

```python
result = compute_something(data)
return result
```

Good (teaching `compute_something`):

```python
print("input:    ", data)
intermediate = data * 2
print("after x2: ", intermediate)
result = intermediate + 1
print("final:    ", result)
```

The reader runs it and *sees* the transformation. No mental simulation required.

Aligned labels (the spacing after `:`) make output scannable.

---

## 4. Comments: only the WHY, only the non-obvious

Bad (what-comments):

```python
count = 0  # initialize counter to zero
count += 1  # increment count
```

Bad (production-style block comments):

```python
# ============================================
# COUNTER MODULE
# This module implements a counter using a
# closure pattern with nonlocal state.
# ============================================
```

Good (one WHY comment on the only line that needs it):

```python
def make_counter():
    count = 0
    def increment():
        nonlocal count   # without this, count += 1 creates a new local
        count += 1
        return count
    return increment
```

The `nonlocal` line is the only non-obvious one. Comment it, leave everything else clean. The walkthrough carries the rest.

---

## 5. No defensive code unless defense is the concept

Production code does input validation, type checking, retries. Teaching code skips all of that — it gets in the way.

Bad:

```python
def divide(a, b):
    if not isinstance(a, (int, float)):
        raise TypeError("a must be numeric")
    if not isinstance(b, (int, float)):
        raise TypeError("b must be numeric")
    if b == 0:
        raise ZeroDivisionError("cannot divide by zero")
    return a / b
```

Good (if the concept is *division*):

```python
def divide(a, b):
    return a / b
```

Exception: if the concept *is* exception handling, validation, or type checking, then those become the focus and everything else strips down.

---

## 6. One concept per example

A teaching example is a microscope, not a tour. It demonstrates *exactly one thing*.

Bad (teaching closures, accidentally also teaching decorators, type hints, and dataclasses):

```python
from dataclasses import dataclass
from typing import Callable

@dataclass
class Counter:
    start: int = 0

    def make(self) -> Callable[[], int]:
        count = self.start
        def increment() -> int:
            nonlocal count
            count += 1
            return count
        return increment
```

Good (closures only):

```python
def make_counter():
    count = 0
    def increment():
        nonlocal count
        count += 1
        return count
    return increment
```

Strip everything that isn't the concept. Type hints, dataclasses, decorators, `__main__` guards — all noise unless they *are* the lesson.

---

## 7. Show output inline

A reader of a lesson is probably not going to run the code right now. Put the output in a comment so they can see what would happen.

```python
counter = make_counter()
print(counter())   # 1
print(counter())   # 2
print(counter())   # 3
```

The `# 1`, `# 2`, `# 3` are not redundant — they're the *result*. The reader's eye runs the program.

This applies to anything with deterministic output. For random output, write `# e.g. 0.4382`.

---

## 8. Idiomatic but not clever

Use the idiom of the language — but don't show off. The goal is "this is how you'd actually write it," not "look at the trick I know."

Teaching iteration in Python:

OK: `for x in xs:` — idiomatic.
Not great: `list(map(some_func, xs))` — unless you're teaching `map`.
Definitely not: `[*(some_func(x) for x in xs)]` — clever, not clear.

Teaching a value swap:

OK: `a, b = b, a` — Python's idiom.
Not OK: `a, b = b, a` *with* a comment "// XOR swap would be faster" — distracting.

---

## 9. The first line of code should resolve a question raised by the intuition

The intuition promises "a closure remembers variables from where it was born." The first non-trivial line of the example should let the reader point at it and say *"oh, that's where it remembers."*

If the intuition says "futexes let userspace handle the fast path of locking" and the example starts with `int fd = open(...)`, the reader's question is unanswered for ten lines. Restructure: open with the line where the fast path happens.

---

## 10. Pseudocode for wiring, state, and control flow

This section is the rule book for **Mode B** — structured pseudocode. The concept's value is in **how the pieces are wired**, the **state at each step**, or the **control flow** — not in being runnable. Trying to make it runnable buries the lesson under setup (60 lines of `nn.Module` scaffolding to demonstrate an 8-line algorithm).

Three flavors of Mode B, by concept domain:

- **Flavor 1 — DL architectures and training algorithms** (MoE, FlashAttention, Transformer, GRPO, PPO). PyTorch syntax with **tensor shape annotations** as the load-bearing state.
- **Flavor 2 — Distributed protocols and state machines** (Raft, Paxos, TCP, OAuth). Named participants, message arrows, **participant state** transitions.
- **Flavor 3 — Complex algorithms and data structures** (B+ tree, union-find, recursive descent parser). Control flow with **invariants** stated and a **concrete data trace** on a small input.

### What pseudocode means here

It does **not** mean prose-in-uppercase ("FOR each token IF gate score > threshold..."). That style throws away the precision that makes code worth reading. It means **real syntax** (Python / PyTorch / pseudocode notation), with the parts that aren't the concept stripped out and the parts that *are* the concept annotated heavily.

### The four rules

#### Rule 1 — Mark the block

Top of the code block, one comment line:

```python
# pseudocode — illustrative, not runnable
```

The reader needs to know not to copy-paste it into a notebook expecting it to work. This one line prevents 90% of the "I tried to run your example and got an error" follow-ups.

#### Rule 2 — Annotate every state change

This is the single most important rule, and it generalizes across all three Mode B flavors. The **state** being tracked depends on the flavor:

- **Flavor 1 (DL):** tensor shapes. `[B, T, D]`, `[B, T, E]`, `[N, D]`.
- **Flavor 2 (protocols):** participant state. `leader.commitIndex 12 → 14`, `follower.log [..., e12] → [..., e12, e13]`.
- **Flavor 3 (algorithms):** data state at trace milestones. `arr = [3, 1, 4, 1, 5]` → `[3, 1, 1] [4] [5]` after partition.

For all three, **state transitions are the load-bearing part of the lesson**. Skip them and the code reads as noise.

Conventions:

- Stable axis letters: `B` batch, `T` tokens, `D` model dim, `H` heads, `E` experts, `K` top-k, `V` vocab. Use these consistently across the lesson.
- Annotate inline, right of the assignment, aligned where possible:

```python
gate_logits = gate(x)                        # [B, T, E]
top_w, top_i = gate_logits.topk(k, dim=-1)   # [B, T, K], [B, T, K]
```

- Annotate transitions explicitly when the shape changes in a non-obvious way:

```python
tokens = x[mask]   # [B, T, D] → [N, D]   (N = number of routed tokens)
```

The `[B, T, D] → [N, D]` is doing the same work as a paragraph of prose. It tells the reader *what the operation accomplishes structurally*.

#### Rule 3 — Drop the scaffolding, keep the algorithm

Strip these aggressively:

- `import torch, torch.nn as nn` — assumed.
- `class Foo(nn.Module): def __init__(self, ...): super().__init__(); ...` — assumed. Write the forward logic as a standalone function.
- Dataloader / batching / distributed init — the lesson is not about how data arrives.
- Optimizer step boilerplate (`optimizer.zero_grad(); loss.backward(); optimizer.step()`) unless the concept *is* the optimization step.

Keep these unconditionally:

- Every operation that's part of the algorithm: `softmax`, `topk`, `gather`, `mask_fill`, `cumsum`, `where`.
- Every `for` / `if` / `while` in the algorithm's control flow.
- Shape annotations on every line where the shape moves.
- The seam — what this replaces or what this differs from (see Rule 4).

#### Rule 4 — Show the seam to the cousin concept

Most algorithms and architectures are interesting *relative to a predecessor*. GRPO is interesting because of what it removes from PPO (the critic network). MoE is interesting because of what it adds to a dense FFN (routing + sparsity). FlashAttention is interesting because of what it changes about standard attention (tiling for memory).

Show the cousin in two or three lines, side by side or with a "compare with" comment:

```python
# pseudocode — illustrative, not runnable
# PPO advantage (needs a learned value function V):
#   advantages = rewards + gamma * V(s_next) - V(s)
#
# GRPO advantage (no value function — uses the group's own mean):
def grpo_advantages(rewards):
    # rewards: [B, G]  (G samples per prompt)
    mean = rewards.mean(dim=-1, keepdim=True)
    std  = rewards.std(dim=-1, keepdim=True)
    return (rewards - mean) / (std + 1e-8)        # [B, G]
```

The PPO line in the comment is doing a quarter of the lesson. Don't drop it.

### What stays the same from production-code-don'ts

Even in pseudocode:

- Names still say what they mean: `gate_logits` not `g`, `expert_outputs` not `e`.
- Comment only the WHY: `# group-relative — no critic needed` next to the normalization line is gold; `# subtract the mean` next to `- mean` is noise.
- One concept per block. If you're tempted to also show the KL penalty, the clipping ratio, *and* the entropy bonus in the same GRPO block, you have three lessons fighting for the floor. Pick one.

### A common failure to watch for

When writing pseudocode for an architecture, the temptation is to compress it into one beautiful nested expression:

```python
# bad pseudocode — too compressed to teach from
out = sum(w * e(x[m]) for w, e, m in zip(top_w, experts, masks))
```

This is wrong for teaching even if it's a faithful one-liner. The lesson is in the *steps*: gate → top-k → softmax → mask → dispatch → combine. Compressing them into a comprehension hides the steps. Write the explicit `for` loop.

The inverse is also wrong:

```python
# bad pseudocode — over-expanded
for b in range(B):
    for t in range(T):
        for e in range(E):
            if e in top_indices[b, t]:
                ...
```

Three nested loops in a vectorized architecture are a *mental model bug*: MoE is vectorized routing, not per-token iteration. The pseudocode reinforces the wrong mental model. Use the tensor-level loop (one `for` over experts, vectorized over tokens) — that matches how it actually runs.

---

## 11. Trace blocks for algorithm concepts

For algorithm concepts — sorting, searching, traversal, divide-and-conquer, dynamic programming, graph algorithms — **the most useful single artifact is often the trace**: running the algorithm on a small concrete input and showing 3–6 intermediate states. The trace is what makes the algorithm click; the code by itself is just notation.

Use a trace block when:

- The concept is an algorithm (the code *does* something, not just *is* something).
- The algorithm has internal state that changes step by step (a recursion, a loop with accumulating data, a worklist).
- A reader could plausibly look at the code and not be sure they could predict the output without simulating it.

**Don't** use a trace block for:

- API call patterns (e.g. `requests.get(...)` — there's no "trace" to show).
- Single-step transformations (one matmul, one regex match).
- Concepts where the *invariant* is the point and the trace would just be ceremony.

### Format

The trace block lives **right after the example code**, before the walkthrough. Comment it as `# trace on <small input>:` and list 3–6 numbered or stepwise lines showing the algorithm's state at meaningful checkpoints — not every line, just the steps that move the algorithm forward.

### Good — quicksort

```python
def quicksort(arr, lo, hi):
    if lo >= hi: return
    pivot_idx = partition(arr, lo, hi)
    quicksort(arr, lo, pivot_idx - 1)
    quicksort(arr, pivot_idx + 1, hi)

# trace on [3, 1, 4, 1, 5]:
# call quicksort(0, 4):
#   partition picks pivot=arr[4]=5, scans, returns idx=4 (5 is already largest)
#   → arr = [3, 1, 4, 1, 5]  (no swaps needed)
#   recurse on left: quicksort(0, 3) on [3, 1, 4, 1]
#     partition picks pivot=arr[3]=1, returns idx=1
#     → arr = [1, 1, 4, 3, 5]
#     recurse on quicksort(0, 0) → base case
#     recurse on quicksort(2, 3) on [4, 3]
#       → arr = [1, 1, 3, 4, 5]
# final: [1, 1, 3, 4, 5]
```

Notice the trace doesn't explain *every* statement — it picks the moments where the **data state** advances (after each partition call). The reader can mentally fill in the in-between.

### Good — binary search

```python
def binary_search(arr, target):
    lo, hi = 0, len(arr) - 1
    while lo <= hi:
        mid = lo + (hi - lo) // 2
        if arr[mid] == target: return mid
        if arr[mid] < target: lo = mid + 1
        else: hi = mid - 1
    return -1

# trace on arr = [1, 3, 5, 7, 9, 11, 13], target = 7:
# step 1: lo=0, hi=6, mid=3, arr[3]=7 → match! return 3
#
# trace on arr = [1, 3, 5, 7, 9, 11, 13], target = 6:
# step 1: lo=0, hi=6, mid=3, arr[3]=7 > 6 → hi=2
# step 2: lo=0, hi=2, mid=1, arr[1]=3 < 6 → lo=2
# step 3: lo=2, hi=2, mid=2, arr[2]=5 < 6 → lo=3
# step 4: lo=3, hi=2 → exit loop, return -1
```

Two traces — one for the easy case (hit on first step) and one for the search-and-miss case. **Showing both gives the reader the full picture of behavior**. One trace might leave them unsure whether the algorithm handles the miss case correctly.

### Bad

- Tracing every line. The trace becomes a transcript, not a summary.
- Tracing on an input large enough that you give up halfway. Pick small inputs (5–10 elements).
- Tracing without showing the input or final state. The reader needs to see what the algorithm started with and ended with.
- Skipping the trace because "the code is obvious." For anything involving recursion or stateful loops, it isn't obvious — the trace is the lesson.

---

## 12. Working through a worked example

The full template, applied to teaching the concept of **memoization** in Python.

```python
# without memoization — recomputes fib(30) a quarter-billion times
def fib(n):
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)

# with memoization — remember each result the first time we compute it
cache = {}
def fib_memo(n):
    if n in cache:
        return cache[n]
    if n < 2:
        return n
    result = fib_memo(n - 1) + fib_memo(n - 2)
    cache[n] = result   # the line memoization is named after
    return result

import time
for func in (fib, fib_memo):
    start = time.time()
    print(func.__name__, func(30), f"{time.time() - start:.3f}s")
# fib       832040 0.302s
# fib_memo  832040 0.000s
```

Notice what's there and what isn't:

- Naming says the intent (`fib_memo`, `cache`, `result`).
- The seam is shown — `fib` and `fib_memo` side by side.
- One `# WHY` comment on the only non-obvious line (`cache[n] = result`).
- No type hints, no `@functools.cache` (that's pointers territory).
- The timing block at the bottom *proves* the lesson.
- Output is inlined.

If your draft code has this shape, you've nailed the example.
