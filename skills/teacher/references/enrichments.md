# Enrichments

The six-part spine (intuition → example → walkthrough → trap → pointers → test questions) is universal. Some concepts have characteristics that benefit from extra structure layered on top: canonical formulas, designed-on-purpose components, famous cousins, dependency chains, classic misconceptions, charts, and invariants the concept guarantees. Eight optional enrichments handle these.

**Scope:** the framework was originally tuned for DL/ML concepts, which is where the heaviest enrichment use lives. But several enrichments fit broader CS naturally: data structures (state tracking as trace, design rationale, cousin matrix, prereqs, invariants), distributed protocols (state tracking as participant state, design rationale, sequence-diagram visualization, invariants), complex algorithms (state tracking as trace, design rationale, invariants). Use the decision checklist at the bottom — fire what the concept's nature warrants, skip the rest.

**Cardinal rules:**

1. Enrichments are **concept-driven, not concept-default**. Run through the decision checklist when designing a lesson; only fire what its trigger condition warrants.
2. Plain language features (closures, generators, channels, ownership) usually fire **zero** enrichments. They get a clean six-layer lesson.
3. If you're unsure whether an enrichment fits, **skip it**. Padding hurts more than missing helps.
4. **Hard cap: 5 enrichments per lesson.** If you've got 6+ candidates, you're padding — pick the most load-bearing five.

---

## Math tier

**When:** the concept has a canonical mathematical formula that practitioners actually write down and reason about. Attention has `softmax(QKᵀ/√d)V` — that formula is part of literacy in the field. Complexity classes have `O(n log n)`. Distributions have parametric forms. Closures don't have a formula. Skip when there is no canonical math, or when the math is literally identical to the code (e.g. dot product is just `sum(a*b)` — no separate math tier needed).

**How:** keep the intuition as one sentence. Then, **either as a second paragraph in the intuition section, or as its own block between intuition and example**, insert a math block. The example code then mirrors the math line-by-line — the reader can read the code AS the formula realized in code.

The reader gets to stop at whichever tier resonates:

- Beginners stop at the intuition.
- Theory-leaning readers stop at the formula.
- Practitioners want all three to triangulate.

### Good — attention (DL)

> **Intuition:** Each token decides which other tokens to listen to, weighted by relevance. The output is a weighted average of values.
>
> **Math:** $\text{Attention}(Q, K, V) = \text{softmax}\!\left(\frac{QK^\top}{\sqrt{d_k}}\right) V$, where $Q, K, V \in \mathbb{R}^{T \times d_k}$. The product $QK^\top$ is a $[T \times T]$ similarity matrix; `softmax` row-normalizes it into a probability distribution over keys; the weighted sum over $V$ produces the output.
>
> **Code:** (3 lines of PyTorch that match the formula 1:1)

The math block establishes shapes and operations *before* the code introduces variable names. The reader can map each math symbol to a code line.

### Good — quicksort (non-ML)

> **Intuition:** Pick a pivot, split into "smaller than pivot" and "larger than pivot," sort each side recursively.
>
> **Math (complexity):** $T(n) = 2T(n/2) + O(n)$ for balanced pivots → $O(n \log n)$ average. Worst case $T(n) = T(n-1) + O(n) = O(n^2)$ for already-sorted input with naïve pivot choice.

For algorithms, the "math tier" is often the recurrence and Big-O analysis — not a closed-form formula but a quantitative claim about behavior.

### Bad

- Inventing a formula that doesn't exist in the literature. If you can't cite where the formula appears (paper, textbook), don't write it.
- Adding a math block when the math IS the code (e.g. softmax — just write the code).
- A math tier longer than 3 lines. Past 3 lines you're writing a textbook chapter.

---

## State tracking

**Already mandatory in Mode B** per [`code-style-for-teaching.md`](code-style-for-teaching.md) §10. This enrichment names what's being tracked, which differs by domain:

| Mode B flavor | What state to track |
|---|---|
| **DL architectures / training algorithms** | Tensor shapes on every line where shape changes |
| **Distributed protocols / state machines** | Participant state at each step (`leader.term`, `follower.commitIndex`) |
| **Complex algorithms / data structures** | Data state at trace milestones (`arr = [3, 1, 4, 1, 5]` → `[3, 1, 1]` after partition) |

The principle is the same in all three: **the reader is trying to mentally execute the code, and they need the state at key checkpoints to do that**. Without the annotations, every reader re-derives the state themselves — which is the work you should be doing for them.

### Good — DL (attention)

```python
Q = x @ W_q                # [B, T, d]
scores = Q @ K.transpose(-2, -1)   # [B, T, T]   ← attention's defining shape
weights = scores.softmax(dim=-1)   # [B, T, T]   row-wise probabilities
out = weights @ V                  # [B, T, d]
```

### Good — protocol (Raft AppendEntries)

```
leader  ──[term=5, prev=12, entries=[e13,e14]]──►  follower
        ◄──[term=5, success=true, matchIdx=14]──── 

leader state:    commitIndex 12 → 14 (quorum reached on e14)
follower state:  log [..., e12] → [..., e12, e13, e14]
                 commitIndex 12 → 14 (after next heartbeat)
```

### Good — algorithm (union-find with path compression)

```python
def find(x):
    # invariant: every node either points to itself or to its root
    if parent[x] != x:
        parent[x] = find(parent[x])   # path compression
    return parent[x]

# trace on parent = [0, 0, 1, 2, 3]:  (chain: 4 → 3 → 2 → 1 → 0)
# find(4):  parent[4]=3, recurse → find(3) returns 0, then parent[4] = 0
# find(3):  parent[3]=2, recurse → find(2) returns 0, then parent[3] = 0
# find(2):  parent[2]=1, recurse → find(1) returns 0, then parent[2] = 0
# find(1):  parent[1]=0, recurse → find(0) returns 0
# find(0):  parent[0]=0, return 0
# after:    parent = [0, 0, 0, 0, 0]   all flattened to point at root
```

### Bad

- Code in Mode B without **any** state annotations. The block is broken, not "stylistically off."
- Annotating every line including trivial ones. Annotate where state changes, not where it's preserved.
- Mixing two state types in the same block (e.g. shape annotations alongside data trace) — pick the one that's the lesson.

---

## Design rationale — why this design, not other plausible ones

**When:** the concept involves designed-on-purpose choices that have been argued for in the literature, AND those choices are commonly questioned by learners. Attention divides by √d — that's a choice. LayerNorm normalizes across features instead of batch — that's a choice. TCP retransmits after a timeout — that's a choice. Binary search uses `lo + (hi - lo) / 2` carefully — that's a choice (overflow!).

Skip when the concept has no design choices worth questioning (e.g. "tensor broadcasting" is mostly mechanics).

**How:** insert a short block after the walkthrough and before the trap, titled "Design choices" or "为什么这么设计". 2–3 bullets max. Each bullet states one decision + what would break if you changed it.

### Good — attention (DL)

> **Design choices:**
> - **Why divide by `√d_k`:** without it, dot products grow with `d_k`. Large values push softmax into saturation (almost all weight on one token), gradients vanish, training stalls. Dividing keeps variance ≈ 1 regardless of head dimension.
> - **Why softmax, not raw weights:** softmax forces weights to sum to 1, making "attention" a probability distribution. Hardmax (just pick top-1) loses gradient flow to the unselected keys; raw weights have no scale guarantee.
> - **Why three separate projections Q, K, V from the same x:** so the same token can play different roles — "asker" (Q), "answerer" (K), "content carrier" (V) — across heads. Sharing all three would collapse expressiveness.

Each bullet ends with "what would break if you didn't" — that's what makes it stick.

### Good — TCP retransmit (non-ML)

> **Design choices:**
> - **Why exponential backoff on retry:** linear backoff doesn't react to congestion; without backing off the sender amplifies a congestion event by re-sending. Exponential gives the network room to drain.
> - **Why duplicate-ACK fast retransmit (without waiting for timeout):** RTO is conservative (seconds); waiting wastes throughput when the loss is single-packet. 3 dup-ACKs is the heuristic that a packet was lost, not just reordered.
> - **Why cumulative ACK, not selective:** simpler receiver state, but the sender has to retransmit everything past the gap. SACK extension fixes this.

### Bad

- Listing choices that aren't actually choices ("why use floats" — they had to).
- More than 3 bullets. Past 3 it becomes trivia.
- Restating the walkthrough in different words. The walkthrough is "what each line does"; design rationale is "why this and not the alternative."

---

## Cousin matrix

**When:** the concept has one or more famous cousins that learners routinely conflate or compare. The list is short and stable across fields:

| Domain | Concept | Famous cousin(s) |
|---|---|---|
| Normalization | BatchNorm | LayerNorm, GroupNorm, RMSNorm |
| Recurrence | LSTM | GRU |
| Optimization | Adam | SGD, SGD+momentum, AdamW |
| Generative | VAE | GAN, Diffusion |
| Regularization | L1 | L2 |
| Architecture | Encoder-only | Decoder-only, Encoder-decoder |
| Activation | ReLU | GELU, SwiGLU, Mish |
| RL | GRPO | PPO, DPO |
| Sparsity | MoE (sparse) | Dense ensemble |
| Network | TCP | UDP, QUIC |
| Indexing | B+ tree | Hash index, LSM tree |
| Concurrency | Mutex | Semaphore, RWLock, Spinlock |
| Consistency | Strong | Eventual, Causal |
| Compilation | AOT | JIT, Interpretation |

**How:** present as a small comparison table, 3–5 rows max. Place it in the pointers section (replacing or augmenting the standard pointer bullets). Each row is one comparison axis (where they differ behaviorally), not one feature.

### Good — BatchNorm vs LayerNorm (DL)

| | BatchNorm | LayerNorm |
|---|---|---|
| Normalizes across | batch dim | feature dim |
| Depends on batch size | yes (breaks at B=1) | no |
| Train ≠ inference | yes (running stats) | no |
| Where it shines | CNNs, ResNet | Transformers, RNNs |
| Why Transformers use LN | variable-length sequences make batch stats noisy and unfair | n/a |

### Good — TCP vs UDP (non-ML)

| | TCP | UDP |
|---|---|---|
| Connection | yes (3-way handshake) | no (fire and forget) |
| Reliability | guaranteed delivery + ordering | none |
| Congestion control | yes (CWND, slow start) | application's problem |
| Header overhead | 20+ bytes | 8 bytes |
| Use when | accuracy > latency (HTTP, SSH) | latency > accuracy (DNS, video, games) |

### Bad

- Tables longer than 5 rows. The point is contrast, not exhaustiveness.
- "vs" pairs that aren't actually famous. If practitioners don't routinely compare them, the table teaches nothing.
- Comparing across mismatched axes (e.g. comparing optimizers and normalizations).

---

## Prerequisites + variants

**When:** the concept sits in a clear dependency chain. Attention requires dot-product similarity + softmax. Multi-head attention extends attention. Flash attention is a memory-efficient implementation. B+ trees require BST + balancing concepts and lead to LSM trees. These dependencies are real, named, and useful to surface.

Skip when the concept is roughly standalone or its dependencies are too generic to be useful (matrix multiplication, gradients).

**How:** replace the standard pointer bullets with a directional structure. Use `←` for prerequisites (what you need to know first) and `→` for variants/extensions (what builds on this).

### Good — attention (DL)

> **Where this sits:**
>
> ```
> ← Prerequisites
>   - dot-product similarity (cosine intuition)
>   - softmax (turning real scores into a probability distribution)
>
> → Variants and extensions
>   - multi-head attention: run h attentions in parallel, then concat
>   - flash attention: same math, tiled into SRAM-sized blocks for memory efficiency
>   - cross-attention: Q from one sequence, K and V from another
>   - linear attention: replace softmax with a kernel to avoid the [T, T] matrix
> ```

### Good — B+ tree (non-ML)

> **Where this sits:**
>
> ```
> ← Prerequisites
>   - binary search tree (BST invariant)
>   - tree balancing (why height matters for disk reads)
>
> → Variants and extensions
>   - B-tree (data in internal nodes too; B+ stores data only in leaves)
>   - LSM tree (writes are sequential; reads merge across levels)
>   - fractal tree (B+ with buffered writes)
> ```

### Bad

- Padding the prerequisite list with everything tangential ("you need to know matrix multiplication" — everyone does).
- More than 3–4 items per direction. Past that the list isn't a map, it's an obstacle.

---

## Misconception list

**When:** the concept has multiple famous misunderstandings — not just one canonical trap, but a small cluster of wrong beliefs people actually hold. Dropout is a classic case (at least three common misconceptions). Embeddings is another ("it's just a lookup" — actually a learned dense representation with structure). Mutex (people often think it stops other code from running, not just other accesses to the same lock).

Use the standard single-snippet trap when there's one dominant misconception. Switch to a list when there are 2–4 equally common ones.

**How:** replace the trap's single snippet with a numbered list. Each item: one wrong belief + one short correction.

### Good — dropout misconceptions

> **Common misconceptions:**
>
> 1. **"Dropout is also applied at inference."** No — at inference dropout is disabled and the network sees full activations. (Training scales by `1/(1-p)` so expected values match the eval path.)
> 2. **"Dropout prevents overfitting by randomly removing weights."** Not weights — *activations*. Weights persist across batches; their input signals are sometimes zero.
> 3. **"Higher dropout is always more regularization."** Up to a point. Too high and the network can't learn — gradient variance explodes. Typical values: 0.1–0.5.

### Bad

- Inventing misconceptions ("what if someone thought attention was a convolution?" — nobody thinks that).
- More than 4 items. If you're at 5, two of them are probably restatements.
- Misconceptions that are really just the intuition phrased differently. Each item must be a *wrong belief practitioners actually hold*.

---

## Visualization

**When:** a chart or diagram conveys what 200 words of prose cannot. Common cases:

- **Heatmaps** (attention weights, gradient norms, cache hit patterns)
- **State machines** (TCP connection states, async future lifecycle, actor states)
- **Sequence diagrams** (Raft AppendEntries, OAuth flow, multi-stage request/response)
- **Loss landscapes** (1D / 2D cuts showing optimization terrain)
- **Receptive field diagrams** (what a CNN kernel sees, what tokens an attention head attends to)
- **Embedding spaces** (PCA / t-SNE of learned vectors)
- **Tree / graph structures** (B+ tree before/after split, DAG of operations)

**How:** include the visualization as a markdown image, ASCII diagram, SVG, or — when the host agent can render images — directly. One chart per lesson at most. Place near the example (illustrating the code) or near the trap (illustrating the failure mode).

### Good — state machine (TCP, ASCII)

```
   CLOSED ──open──► LISTEN ──SYN──► SYN_RCVD ──ACK──► ESTABLISHED
                                                          │
   CLOSED ◄──ACK── TIME_WAIT ◄──FIN── (...) ◄───FIN──────┘
```

### Good — sequence diagram (OAuth)

```
client ──── request_auth ────►  server
       ◄──── auth_code ──────
       ──── code + secret ──►
       ◄──── access_token ───
       ─── api(access_token) ►
       ◄──── data ──────────
```

### Bad

- Generating a chart for the sake of it. If shape annotations + code already convey the structure, skip the chart.
- Charts so complex they need their own walkthrough. Then the chart is a sub-lesson, not a visualization.
- ASCII art so noisy it harms readability — if you can't draw it cleanly in 10 lines, drop it.

---

## Invariants

**When:** the concept is built around stated invariants — conditions that must hold before and after each operation. Common in:

- **Data structures**: heap invariant (parent ≤ children), BST invariant, red-black tree's 5 properties, union-find rank, B+ tree's "all leaves at same depth"
- **Distributed systems**: Raft's 5 safety properties, linearizability, causal consistency
- **Type systems**: subject reduction, parametricity
- **Concurrency**: lock invariants, monitor invariants

Skip when the concept has no formal guarantees worth stating (a single API call, a one-off algorithm without persistent state).

**How:** insert a block between the walkthrough and the trap. List 2–3 invariants the concept guarantees, with one line each on **what breaks if the invariant fails**. The "what breaks" is what distinguishes invariants from design rationale — design rationale says *why this was chosen*, invariants say *what this guarantees you and why it matters*.

### Good — min-heap

> **Invariants this concept guarantees:**
>
> 1. **Heap property:** for every node, `parent.value ≤ left.value` and `parent.value ≤ right.value`. Breaks → `extract_min` returns the wrong value (no longer the minimum).
> 2. **Complete-tree shape:** all levels filled left-to-right except possibly the last. Breaks → the array-indexed parent/child math (`2i+1`, `2i+2`) becomes incorrect; operations corrupt the heap.
>
> The two together imply every operation is `O(log n)`: shape gives height = log n; heap property restricts how far an element can be out of place after insert/extract.

### Good — Raft (non-ML)

> **Invariants this concept guarantees:**
>
> 1. **Election safety:** at most one leader per term. Breaks → split-brain, conflicting commits, data loss.
> 2. **Leader append-only:** a leader never overwrites or deletes entries in its own log. Breaks → committed entries could be lost.
> 3. **Log matching:** if two logs contain an entry with the same index and term, all preceding entries match. Breaks → the consistency check used during AppendEntries fails; the protocol can't make progress.

### Bad

- Listing invariants that are just restatements of how the data structure is built. The invariant should be a *consequence* worth checking, not "well, it's a tree."
- More than 3 invariants. If you have 4+, you're listing properties, not load-bearing guarantees.
- Confusing invariants with design rationale. Invariants are *what holds*; design rationale is *why we chose this design*. They often appear in the same concept (heap has both), but they answer different questions.

---

## Decision checklist

Run this sequence when designing a lesson. Each "yes" adds one enrichment; "no" means skip.

1. **Mode B selected** (architecture, training algorithm, kernel concept, distributed protocol, or complex algorithm/data structure)? → state tracking is implied on, in the flavor matching the concept's domain.
2. **Does the concept have a canonical formula** (or Big-O recurrence)? → math tier.
3. **Does the concept have 2+ designed-on-purpose choices** worth justifying? → design rationale.
4. **Does the concept have one or more famous "vs" cousins**? → cousin matrix.
5. **Does the concept sit in a clear dependency chain** (named prereqs and variants)? → prerequisites + variants.
6. **Does the concept have 2+ classic misconceptions** of roughly equal prevalence? → misconception list; otherwise the trap stays single-snippet.
7. **Would a chart or diagram save 200 words of prose**? → visualization.
8. **Is the concept built around stated invariants** it guarantees? → invariants.

**Hard cap:** no lesson uses more than 5 enrichments. If you're at 6+, you're padding. Pick the most load-bearing five.

**Hard floor:** if zero enrichments fire, the concept gets a plain six-part lesson. That's normal — most language features and simple algorithms land here.

---

## Reference: which enrichments fire for which concepts

A calibration map. New concepts not on the list should follow the decision checklist above.

### Heavy enrichment (4–5 modules fire)

- **Self-attention / Multi-head attention** — math, state-tracking (shapes), design, cousin (vs cross-attention), prereqs+variants, visualization. The maximalist DL case.
- **BatchNorm / LayerNorm** — math, state-tracking, design, cousin (BN vs LN), prereqs+variants, misconceptions.
- **Adam optimizer** — math, design (momentum + adaptive lr), cousin (vs SGD), misconceptions.
- **MoE** — state-tracking, design, cousin (vs dense FFN), prereqs+variants, misconceptions (load imbalance).
- **GRPO** — state-tracking, design, cousin (vs PPO), prereqs+variants (← PPO, → DPO).
- **Raft consensus** — state-tracking (participant state), design, prereqs+variants, visualization (sequence diagram), invariants (5 safety properties). The maximalist non-ML case.
- **B+ tree** — state-tracking (data trace through insert/split), design (why fanout, why leaf-only data), cousin (vs hash, LSM), prereqs+variants, invariants (all leaves same depth).
- **Red-black tree** — state-tracking, design, invariants (5 properties), cousin (vs AVL).

### Medium (2–3 modules fire)

- **Dropout** — design (why scale), misconceptions (3+ common ones).
- **Residual connections** — math, design (why add not concat), prereqs+variants (DenseNet variant).
- **Softmax (with temperature)** — math, design (temperature behavior).
- **Cross-entropy loss** — math, design (why -log, why mean).
- **Embedding layer** — design (learned, not lookup), misconceptions (multiple common ones).
- **Quicksort** — math (recurrence), state-tracking (trace), design (pivot choice).
- **TCP congestion control** — design (why exponential backoff), cousin (vs UDP), visualization (state diagram).
- **Mutex / locking** — cousin (vs semaphore, RWLock), misconceptions (multiple common ones about what it guarantees), invariants (under correct use).

### Light (0–1 modules fire)

- **Tensor broadcasting** — only state-tracking.
- **`@torch.no_grad()`** — none. Plain six-part lesson.
- **Gradient accumulation** — maybe design (why divide by accumulation steps).
- **Closures** — none. Plain six-part lesson.
- **Generators** — none.
- **Activation functions overview** — only cousin matrix (of ReLU/GELU/SwiGLU).

The pattern: concepts that are **mechanisms** (broadcasting, closures, generators) get few enrichments. Concepts that are **designed-on-purpose components** (attention, BN, Raft, B+ tree) get many. **Stretch a concept past its weight class and the lesson bloats**; under-serve a load-bearing concept and the reader leaves confused.
