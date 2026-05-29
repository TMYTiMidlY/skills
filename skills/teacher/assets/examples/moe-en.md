# Worked example: Mixture of Experts (MoE)

> **Prompt:** "I keep seeing 'Mixture of Experts' in model papers. explain how MoE actually works — what does 'routing' mean here?"
> **Mode:** B (pseudocode, Flavor 1 — DL architecture)
> **Language:** English
> **Enrichments fired:** state tracking (shapes), design rationale, cousin matrix (vs dense FFN), prerequisites + variants (← FFN, → Switch / Mixtral) — 4 of 8
> **Sidecar code:** [`moe-pseudocode.py`](moe-pseudocode.py)

Full skill output frozen as a regression reference. Note the shape transitions `[B, T, D] → [B, T, E] → [B, T, K] → [N, D] → [B, T, D]` traced through the example — the load-bearing part of any MoE explanation.

---

## Intuition

You want a **higher-capacity** FFN layer (more parameters → more learnable) without paying for those parameters on every token at inference. MoE's answer: open E independent small FFNs (the "experts"), add a routing network (the gate), and **let each token activate only K of the E experts**.

One sentence: **MoE replaces "one fat FFN" with "many small FFNs + a router," so total parameters scale up (capacity), but each token still pays only K/E of the FLOPs — big-model capacity at small-model compute.**

## Example — structured pseudocode

```python
# pseudocode — illustrative, not runnable
# B = batch, T = tokens, D = model dim, E = num experts, K = experts per token

# --- compare with a dense FFN ---
# dense_ffn(x) = W2(activation(W1(x)))    # every parameter touched on every token
# moe(x):       only K of E experts run on each token  → ~K/E of the FLOPs

def moe_forward(x, experts, gate, k=2):
    # x: [B, T, D]

    # 1. Gating: score every (token, expert) pair.
    gate_logits = gate(x)                              # [B, T, E]    Linear(D, E)

    # 2. Top-K routing: pick the K best experts per token.
    top_w, top_i = gate_logits.topk(k, dim=-1)         # [B, T, K], [B, T, K]
    top_w = top_w.softmax(dim=-1)                      # weights sum to 1 per token

    # 3. Dispatch → compute → combine.
    out = zeros_like(x)                                # [B, T, D]
    for expert_id, expert in enumerate(experts):
        mask = (top_i == expert_id).any(dim=-1)        # [B, T]
        if not mask.any():
            continue
        tokens  = x[mask]                              # [B, T, D] → [N, D]
        weights = top_w[(top_i == expert_id)]          # [N]
        out[mask] += weights.unsqueeze(-1) * expert(tokens)

    return out                                         # [B, T, D]
```

Full pseudocode also frozen at [`moe-pseudocode.py`](moe-pseudocode.py) for editor viewing.

## Walkthrough

**(1) Gating — the router is the cheapest part**

```python
gate_logits = gate(x)                                  # [B, T, D] → [B, T, E]
```

The `gate` is just a `Linear(D, E)` — much smaller than any single expert (an expert has a `D × D_hidden` matrix; the gate has only a `D × E` matrix). Its job: score each token against each expert. **The whole "routing decision" component costs almost nothing**, which is the precondition that makes MoE's FLOPs savings possible.

**(2) Top-K routing — where sparsity comes from**

```python
top_w, top_i = gate_logits.topk(k, dim=-1)             # [B, T, E] → [B, T, K]
top_w = top_w.softmax(dim=-1)
```

For each token, pick the K highest-scoring experts (typical: K=2; Switch Transformer uses K=1). `top_i` are their indices, `top_w` their gating weights (softmax-normalized). **This single line is the source of MoE's sparse activation**: the gate emitted E scores per token, but only K of them get used — the remaining E−K experts won't see this token.

**(3) Dispatch → compute → combine**

```python
for expert_id, expert in enumerate(experts):
    mask = (top_i == expert_id).any(dim=-1)            # [B, T]
    tokens  = x[mask]                                  # [B, T, D] → [N, D]
    weights = top_w[(top_i == expert_id)]              # [N]
    out[mask] += weights.unsqueeze(-1) * expert(tokens)
```

The outer loop is **over experts**, not over tokens (this matters — if you wrote it as a loop over tokens, you'd serialize processing and lose vectorization). For each expert, the `mask` selects "tokens routed to it," flattens them into `[N, D]`, runs the expert once on the whole batch of routed tokens, and accumulates the weighted output back into the right positions of `out`.

**Key shape transitions**: `[B, T, D] → [N, D]` (dispatch) → expert compute → `[N, D]` → weighted accumulate → `[B, T, D]` (combine). The MoE layer takes `[B, T, D]` in and produces `[B, T, D]` out — externally it's a drop-in replacement for a dense FFN.

## Trap

**Wrong intuition:** "MoE is an ensemble of experts whose outputs are averaged."

```python
# Wrong understanding:
out = sum(gate_weight[e] * experts[e](x) for e in range(E))
# This is dense MoE — every expert runs on every token. With E=8 that's 8× the FLOPs of a single FFN.
```

**Actually: sparse routing.** Each token activates only K experts; the other E−K experts don't run on it at all.

The difference decides MoE's value proposition: **parameters scale ~E×, FLOPs scale only ~K×**. If it were dense ensembling, FLOPs would also scale E× — making MoE pointless, just a fatter FFN. **Sparsity is the core of MoE, not ensembling.**

## Pointers — where this sits

```
← Prerequisites
  - dense FFN layer (the thing MoE replaces, one per Transformer block)
  - softmax (turning gate scores into normalized weights)

→ Variants and extensions
  - Switch Transformer (K=1): more compute savings, less stable training
  - Mixtral / GShard (K=2): the current mainstream tradeoff point
  - Shared-expert MoE: a "shared" expert that always runs + K routed experts (DeepSeek-MoE)
  - Auxiliary load-balancing loss: extra term to prevent gate collapse (see test question 3)
  - Expert capacity / token dropping: cap how many tokens any expert can take per batch
```

## Test questions

> **1.** For an MoE layer with 8 experts and K=2, compared with a dense FFN of the same hidden size per expert: what's the **parameter** ratio? What's the **inference FLOPs** ratio? Why aren't these the same?
>
> > Hint: parameters all live in memory, but each token only activates K experts.

> **2.** Look at the example, line 21: `tokens = x[mask]`. `x` came in as `[B, T, D]`, `mask` is a bool of shape `[B, T]`. What's the output shape of `tokens`? Why did the batch and token dimensions collapse together?
>
> > Hint: bool indexing flattens all positions where the mask is True.

> **3.** During training of an 8-expert top-2 MoE, you observe that one expert handles 70% of tokens while another handles only 1%. What's the problem? Why does it arise spontaneously? What loss term does the field use to prevent it, and what is the loss roughly trying to push the gate's output distribution toward?
>
> > Hint: this is a positive feedback loop — a stronger expert gets picked more → trains better → gets picked even more.
