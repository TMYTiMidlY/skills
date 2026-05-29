# Worked example: GRPO

> **Prompt:** "explain GRPO — I've read the paper a few times and still don't get how it differs from PPO"
> **Mode:** B (pseudocode, Flavor 1 — DL training algorithm)
> **Language:** English
> **Enrichments fired:** state tracking (shapes), design rationale, cousin matrix (vs PPO), prerequisites + variants (← PPO, → DPO) — 4 of 8
> **Sidecar code:** [`grpo-pseudocode.py`](grpo-pseudocode.py)

Full skill output frozen as a regression reference. Note the PPO comparison threaded through the example and the trap (cousin matrix + design rationale); the prerequisite-and-variant block in the pointers section; the shape annotations on every tensor.

---

## Intuition

PPO trains a critic network `V` as a baseline to reduce variance — and that critic is expensive and hard to train. GRPO's insight: **sample multiple completions per prompt, and their mean reward is a natural baseline that you don't have to learn**. So GRPO ≈ "PPO with the critic replaced by the group's own mean."

## Example — structured pseudocode

```python
# pseudocode — illustrative, not runnable
# B = batch (prompts), G = sampled completions per prompt, T = token length
# π_θ = policy being trained, π_old = snapshot at sampling time, π_ref = frozen base

# --- compare with PPO ---
# PPO:   advantage_t = reward - V(s_t)            # needs a learned critic V(s)
# GRPO:  advantage_i = (r_i - mean(r)) / std(r)   # baseline is the group itself

def grpo_advantages(rewards):
    # rewards: [B, G]  — one scalar reward per completion
    mean = rewards.mean(dim=-1, keepdim=True)         # [B, 1]
    std  = rewards.std(dim=-1, keepdim=True)          # [B, 1]
    return (rewards - mean) / (std + 1e-8)            # [B, G]  one advantage per completion

# --- one training step ---
prompts     = sample_prompts(batch_size=B)            # [B]
completions = pi_old.sample(prompts, n=G)             # [B, G, T]
rewards     = reward_model(prompts, completions)      # [B, G]

A          = grpo_advantages(rewards)                 # [B, G]    completion-level
log_pi     = pi_theta.log_prob(completions)           # [B, G, T] token-level (current policy)
log_pi_old = pi_old.log_prob(completions)             # [B, G, T] frozen during this update
log_pi_ref = pi_ref.log_prob(completions)             # [B, G, T] frozen base model

# broadcast completion-level advantage to every token of its completion:
A_t = A.unsqueeze(-1)                                 # [B, G, 1] → broadcasts to [B, G, T]

# clipped surrogate objective (identical in shape to PPO):
ratio   = exp(log_pi - log_pi_old)                    # [B, G, T]
clipped = clip(ratio, 1 - eps, 1 + eps)               # [B, G, T]
pg_loss = -minimum(ratio * A_t, clipped * A_t).mean()

# KL penalty toward ref policy (keeps π_θ from drifting too far from base):
kl_penalty = (exp(log_pi_ref - log_pi) - (log_pi_ref - log_pi) - 1).mean()  # k3 estimator

loss = pg_loss + beta * kl_penalty
```

Full pseudocode also frozen at [`grpo-pseudocode.py`](grpo-pseudocode.py) for editor viewing.

## Walkthrough

**(1) Group sampling — where the "G" comes from**

```python
completions = pi_old.sample(prompts, n=G)             # [B, G, T]
rewards     = reward_model(prompts, completions)      # [B, G]
```

For each prompt, sample G completions (typical: G = 8 or 16). Reward is **completion-level** scalar — the whole completion gets one score, not per-token. Hence `rewards` shape is `[B, G]`, no T dimension. This step is the literal "Group" in the name.

**(2) Group-relative advantage — the core change**

```python
A = grpo_advantages(rewards)                          # [B, G]
```

Each completion's advantage = `(its reward − the mean reward over G completions for the same prompt) / std`. **In plain English: how much better or worse this answer is than other samples from the same prompt, z-scored.**

This is using the group itself as its own baseline. The `V(s)` that PPO had to train separately — gone.

**(3) Loss: PPO's shape + KL — "almost identical"**

```python
ratio   = exp(log_pi - log_pi_old)
clipped = clip(ratio, 1 - eps, 1 + eps)
pg_loss = -minimum(ratio * A_t, clipped * A_t).mean()
loss    = pg_loss + beta * kl_penalty
```

This block is **identical to PPO**: clipped surrogate objective and KL penalty. The only difference is where `A` came from (the previous block). That's why GRPO is often described as "PPO without the critic" — the loss shape didn't change, only the baseline's origin did.

Note the `A_t = A.unsqueeze(-1)` step: advantage is completion-level (`[B, G]`), but log_prob is token-level (`[B, G, T]`), so **every token of one completion shares the same advantage scalar**. This means GRPO operates at completion granularity, not token granularity — it assumes "this answer was good/bad" applies uniformly to every token of the answer.

## Trap

"GRPO is just PPO with the critic deleted" — **incomplete**. GRPO doesn't have no baseline; it swapped the baseline from "a learned V(s)" to "the group's mean reward." That swap has consequences:

```python
# Edge case: a group's rewards are all close to each other
rewards = [0.51, 0.50, 0.49, 0.50]    # G=4
mean    = 0.50
A       = [+1.4, 0, -1.4, 0]          # z-score looks fine
# But if the whole group is identical:
rewards = [0.50, 0.50, 0.50, 0.50]
A       = [0, 0, 0, 0]                # gradient signal completely vanishes — this step is wasted
```

PPO's critic gives an absolute "what is this state worth" estimate, so even when a group is tightly clustered, comparison against the global baseline still yields signal. GRPO can only sense **within-group relative differences** — zero in-group variance, zero learning signal.

**Practical implication:** the reward model must be designed so that G samples on one prompt are **meaningfully spread**. If reward is discrete (only 0 or 1, correct/incorrect), you need larger G to ensure each group has both a hit and a miss. This is why GRPO especially needs large G in domains like math and code where rewards are easily binarized.

## Pointers — where this sits

```
← Prerequisites
  - PPO (clipped surrogate, ratio + KL — GRPO inherits these unchanged)
  - reward modeling (the scalar reward function GRPO calls)

→ Variants and extensions
  - DPO: one more step down — drop the reward model entirely, train directly on preference pairs
  - REINFORCE: the simpler ancestor (no clipping, no KL, just policy gradient)
  - RLOO: a contemporary alternative also using group sampling but with leave-one-out baseline
```

The k3 KL estimator (`exp(δ) - δ - 1`) instead of plain `log_pi - log_pi_ref` is used because k3 is non-negative and low-variance. John Schulman has a short blog on k1/k2/k3 KL estimators; DeepSeekMath paper uses k3.

## Test questions

> **1.** In one sentence: what component does GRPO remove from PPO, and what does it use as a substitute?
>
> > Hint: think about what PPO needs to *train* in addition to the policy.

> **2.** Look at the pseudocode. After `grpo_advantages(rewards)`, what is the shape of `A`? Why does the next line need `A.unsqueeze(-1)` before multiplying with `log_pi`?
>
> > Hint: compare against the shape of `log_pi` and see what dimension is missing.

> **3.** Suppose your reward model emits binary rewards (0 or 1) with G=4. In what fraction of training steps will at least one prompt have zero gradient signal? What two knobs would you turn to mitigate this?
>
> > Hint: zero gradient happens when all four samples in a group have identical reward.
