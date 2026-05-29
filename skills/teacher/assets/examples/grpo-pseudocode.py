# pseudocode — illustrative, not runnable
# Concept: GRPO (Group Relative Policy Optimization)
#
# B = batch (prompts), G = sampled completions per prompt, T = token length
# π_θ   = policy being trained
# π_old = snapshot of π_θ at sampling time (frozen during this update)
# π_ref = frozen base model (used only for the KL penalty)

# --- compare with PPO ---
# PPO:   advantage_t = reward - V(s_t)             # needs a learned critic V(s)
# GRPO:  advantage_i = (r_i - mean(r)) / std(r)    # baseline is the group itself

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

# Broadcast completion-level advantage to every token of its completion.
# This is why advantage is the same across all tokens of one completion —
# GRPO assumes "this completion was good/bad" applies uniformly to its tokens.
A_t = A.unsqueeze(-1)                                 # [B, G, 1] → broadcasts to [B, G, T]

# Clipped surrogate objective — identical in shape to PPO:
ratio   = exp(log_pi - log_pi_old)                    # [B, G, T]
clipped = clip(ratio, 1 - eps, 1 + eps)               # [B, G, T]
pg_loss = -minimum(ratio * A_t, clipped * A_t).mean()

# KL penalty toward ref policy — keeps π_θ from drifting too far from base.
# k3 estimator: non-negative, low-variance, used in DeepSeekMath paper.
kl_penalty = (exp(log_pi_ref - log_pi) - (log_pi_ref - log_pi) - 1).mean()

loss = pg_loss + beta * kl_penalty
