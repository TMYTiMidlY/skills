# Worked example: Mixture of Experts (MoE)

> **Prompt:** "试试 MoE"
> **Mode:** B (pseudocode)
> **Language:** Chinese
> **Sidecar code:** `/tmp/moe-pseudocode.py` (also frozen below as `moe-pseudocode.py`)

This is the full skill output for the MoE eval, captured as a regression reference. Note how the test questions are labeled simply "测试题" (not "interview"), and how the pseudocode block traces the shape transitions `[B, T, D] → [B, T, E] → [B, T, K] → [N, D] → [B, T, D]` — the load-bearing part of any MoE explanation.

---

## 直觉

想要一个**容量更大**的 FFN 层（更多参数 → 学到更多东西），但又不想每次推理都摸到所有参数。MoE 的解法：开 E 个独立的小 FFN（"experts"），加一个路由器（gate），**每个 token 只跑其中 K 个 expert**。

一句话：**MoE 把"一个胖 FFN"换成"很多瘦 FFN + 一个路由器"，参数总量上去了（容量大），但每个 token 只激活 K/E 的算力 —— 拿大模型的容量，不付大模型的 FLOPs。**

## 例子 · 结构化伪代码

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

完整伪代码写在 `/tmp/moe-pseudocode.py`（也归档于 `assets/examples/moe-pseudocode.py`），方便在编辑器里看高亮和拷贝。

## 拆解

**(1) Gating —— router 是个最便宜的部件**

```python
gate_logits = gate(x)                                  # [B, T, D] → [B, T, E]
```

`gate` 就是一个 `Linear(D, E)` —— 比任何一个 expert 都小得多（expert 内部有 `D × D_hidden` 矩阵，gate 只有 `D × E`）。它的任务是给每个 token 出 E 个分数，表示"你应该被哪个 expert 处理"。**整个 MoE 里"决定路由"的部分总成本几乎为零**，这是 MoE 能省 FLOPs 的前提。

**(2) Top-K routing —— 稀疏性的来源**

```python
top_w, top_i = gate_logits.topk(k, dim=-1)             # [B, T, E] → [B, T, K]
top_w = top_w.softmax(dim=-1)
```

对每个 token 取 K 个分数最高的 expert（典型 K=2，Switch Transformer 用 K=1）。`top_i` 是它们的索引，`top_w` 是它们的权重（softmax 后归一化）。**这一行就是 MoE 的"稀疏激活"**：本来 gate 输出了 E 个分数，但我们只用其中 K 个 —— 剩下 E−K 个 expert 这个 token 不会跑。

**(3) Dispatch → 计算 → Combine**

```python
for expert_id, expert in enumerate(experts):
    mask = (top_i == expert_id).any(dim=-1)            # [B, T]
    tokens  = x[mask]                                  # [B, T, D] → [N, D]
    weights = top_w[(top_i == expert_id)]              # [N]
    out[mask] += weights.unsqueeze(-1) * expert(tokens)
```

外循环是**对 expert** 的，不是对 token 的（这一点非常重要 —— 如果你写成对 token 的循环，那就成了顺序处理，丢掉了向量化）。对每个 expert，`mask` 挑出"被路由到它的 token"，把它们扁平化成 `[N, D]` 一次过 expert，再按 gating 权重加回到 `out` 的对应位置。

**关键 shape 转换**：`[B, T, D] → [N, D]`（dispatch）→ expert 计算 → `[N, D]` → 加权 → `[B, T, D]`（combine）。整个 MoE 层进来是 `[B, T, D]`，出去还是 `[B, T, D]` —— 它是一个可插拔的层，对外接口跟 dense FFN 没区别。

## 陷阱

**错的印象**：MoE 是"多个 expert 输出做加权平均的 ensemble"。

```python
# 错的理解：
out = sum(gate_weight[e] * experts[e](x) for e in range(E))
# 这是 dense MoE —— 每个 expert 都对每个 token 跑一遍。E=8 时算力是 dense FFN 的 8 倍。
```

实际：**sparse routing**。每个 token 只激活 K 个 expert，其余 E−K 个对它完全不跑。

差别决定了 MoE 的价值命题：**参数量 ~E 倍，FLOPs ~K 倍**。如果是 dense ensemble，FLOPs 也 ~E 倍 —— 那就跟一个更大的 FFN 没区别，MoE 就毫无意义。**稀疏性才是 MoE 的核心，不是 ensemble。**

## 延伸 · 往下走

— **Auxiliary load-balancing loss**：训练时 gate 可能"塌缩"到永远选同几个 expert（详见测试题 Q3）。Switch / GShard 论文里加了一个辅助 loss 推 gate 输出更均匀。
— **Expert capacity / token dropping**：每个 expert 有最大 token 容量；超过就丢掉（或重路由到次优 expert）。容量太小信号丢；太大显存浪费。
— **Switch Transformer (K=1) vs Mixtral / GShard (K=2)**：K=1 算力更省、训练更不稳；K=2 是当前主流权衡点。

## 测试题

> **1.** 一个 8 expert、K=2 的 MoE 层，跟一个 hidden size 同 expert 的 dense FFN 相比：**参数量**是几倍？**推理 FLOPs**是几倍？为什么这两个不是同一个比例？
>
> > Hint: 参数都驻留显存，但每个 token 只激活 K 个 expert。

> **2.** 看伪代码第 21 行 `tokens = x[mask]`。`x` 进来是 `[B, T, D]`，`mask` 是 `[B, T]` 的 bool。`tokens` 出来是什么形状？为什么 batch 和 token 两个维度合并了？
>
> > Hint: bool 索引会扁平化所有为 True 的位置。

> **3.** 训练一个 8-expert top-2 MoE，监控发现某个 expert 处理了 70% 的 token，另一个只有 1%。这是什么问题？为什么会自发产生？业界用什么 loss term 防止？这个 loss 的设计大致长什么样（提示 gate 输出的分布需要被推向什么）？
>
> > Hint: 是个正反馈循环 —— 好的 expert 更容易被 gate 选 → 它训练得更好 → 更容易被选。
