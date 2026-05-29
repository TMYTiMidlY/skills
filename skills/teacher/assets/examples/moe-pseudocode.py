# pseudocode — illustrative, not runnable
# Concept: Mixture of Experts (MoE) forward pass with top-K routing
#
# B = batch, T = tokens, D = model dim, E = num experts, K = experts activated per token
# Each `expert` is a small FFN: Linear(D, D_hidden) → activation → Linear(D_hidden, D)
# `gate` is a single Linear(D, E) — cheap.

# --- compare with a dense FFN ---
# dense_ffn(x) = W2(activation(W1(x)))    # every parameter touched on every token
# moe(x):       only K of E experts run on each token  → ~K/E of the FLOPs, all of the parameters in memory

def moe_forward(x, experts, gate, k=2):
    # x: [B, T, D]

    # 1. Gating: score every (token, expert) pair.
    gate_logits = gate(x)                                 # [B, T, E]    Linear(D, E)

    # 2. Top-K routing: pick the K best experts per token.
    top_w, top_i = gate_logits.topk(k, dim=-1)            # [B, T, K], [B, T, K]
    top_w = top_w.softmax(dim=-1)                         # gating weights sum to 1 per token

    # 3. Dispatch → compute → combine.
    out = zeros_like(x)                                   # [B, T, D]
    for expert_id, expert in enumerate(experts):
        # mask = True wherever this expert is in any of the K slots for that token
        mask = (top_i == expert_id).any(dim=-1)           # [B, T]
        if not mask.any():
            continue
        tokens  = x[mask]                                 # [B, T, D] → [N, D]   N = # routed tokens
        weights = top_w[(top_i == expert_id)]             # [N]                  this expert's gating weight per token
        out[mask] += weights.unsqueeze(-1) * expert(tokens)   # weighted accumulate back into out

    return out                                            # [B, T, D]
