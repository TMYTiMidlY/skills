# Worked example: GRPO

> **Prompt:** "讲一下 GRPO，我看了几遍论文还是没搞懂它和 PPO 的区别"
> **Mode:** B (pseudocode)
> **Language:** Chinese
> **Sidecar code:** `/tmp/grpo-pseudocode.py` (also frozen below as `grpo-pseudocode.py`)

This is the full skill output for the GRPO eval, captured as a regression reference. The six-part structure, the shape annotations in the pseudocode, the comparison-with-PPO line, the trap framing, and the difficulty ladder of the test questions all match what `SKILL.md` and `references/teaching-method.md` prescribe.

---

## 直觉

PPO 训练时需要一个 critic 网络 V 来当 baseline 减方差 —— 这个 critic 既贵又难训。GRPO 的洞察是：**对同一个 prompt 多采几个 completion，这一组的 reward 均值就是天然的 baseline，根本不用学**。所以 GRPO ≈ "把 PPO 的 critic 换成同组采样的平均分"。

## 例子 · 结构化伪代码

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

完整伪代码同时写到了 `/tmp/grpo-pseudocode.py`（也归档于 `assets/examples/grpo-pseudocode.py`），方便在编辑器里看高亮和拷贝。

## 拆解

**(1) Group sampling —— "G" 的来源**

```python
completions = pi_old.sample(prompts, n=G)             # [B, G, T]
rewards     = reward_model(prompts, completions)      # [B, G]
```

每个 prompt 采样 G 个 completion（典型 G=8 或 16）。Reward 是 completion-level 的标量 —— 整个 completion 算一个分，不是 token 级的。所以 `rewards` 是 `[B, G]`，没有 T 维度。这一步是 GRPO 名字里 "Group" 的本体。

**(2) Group-relative advantage —— 核心改动**

```python
A = grpo_advantages(rewards)                          # [B, G]
```

每个 completion 的 advantage = `(它的 reward - 同 prompt 下 G 个 completion 的平均 reward) / std`。**翻译成人话：这个回答比同一个 prompt 下其他采样好/差多少（用 z-score 标准化）**。

这就是用同一组采样自己给自己当 baseline。PPO 那里需要单独训的 V(s) —— 没了。

**(3) 损失：PPO 的形状 + KL —— "几乎没变"**

```python
ratio   = exp(log_pi - log_pi_old)
clipped = clip(ratio, 1 - eps, 1 + eps)
pg_loss = -minimum(ratio * A_t, clipped * A_t).mean()
loss    = pg_loss + beta * kl_penalty
```

这一段**跟 PPO 一模一样**：clipped surrogate objective、KL penalty。区别只在 `A` 的来源（上一段）。这是为什么 GRPO 经常被描述成 "PPO without critic" —— 损失的形状没变，只是把 baseline 换了来源。

注意 `A_t = A.unsqueeze(-1)` 这一步：advantage 是 completion-level（`[B, G]`），log_prob 是 token-level（`[B, G, T]`），所以**同一个 completion 的每个 token 共享同一个 advantage 标量**。这意味着 GRPO 的信号粒度是 completion 级的，不是 token 级的 —— 它假设"这个回答好/坏"对回答里所有 token 都一视同仁。

## 陷阱

"GRPO 就是 PPO 把 critic 删了" —— **不完整**。GRPO 不是没 baseline，而是把 baseline 从"模型学的 V(s)"换成"同 prompt 下采样的 mean"。这个换法有后果：

```python
# 极端情况：一组采样的 reward 都差不多
rewards = [0.51, 0.50, 0.49, 0.50]    # G=4
mean    = 0.50
A       = [+1.4, 0, -1.4, 0]          # z-score 看起来还行
# 但如果整组都是 0.50：
rewards = [0.50, 0.50, 0.50, 0.50]
A       = [0, 0, 0, 0]                # 梯度信号完全消失 —— 这一步训练白做
```

PPO 的 critic 会给出绝对的"这个状态值多少"，所以即使一组采样都差不多，跟全局基准比还能有 signal。GRPO 只能感知**组内相对差异**，组内方差为零它就没饭吃了。

**实践含义**：reward model 的设计必须让同一 prompt 下的 G 个采样**有意义地分散**。如果 reward 是离散的（只有 0/1 / 对错），就要更大的 G 才能确保一组里既有对又有错。这就是为什么 GRPO 在数学/代码这类"答案可验证、reward 容易二值化"的场景里特别需要大 G。

## 延伸 · 往下走

— **KL 的 k3 estimator**：上面伪代码里 `exp(δ) - δ - 1` 而不是直接用 `log_pi - log_pi_ref`，是因为 k3 估计的 KL 是非负、低方差的。John Schulman 有一篇短 blog 专门讲 k1/k2/k3 三种 KL 估计，DeepSeekMath 论文也用这个。
— **G 怎么选**：太小（G=2）信号噪声大、advantage 退化；太大（G=32+）显存和算力线性涨且边际收益递减。论文里典型 G=16。
— **DPO**：再砍一刀 —— 连 reward model 都省了，直接用人类偏好对（chosen / rejected）做 contrastive loss。是"为了简化 RLHF 一路砍下去"的下一站。

## 测试题

> **1.** 一句话说清楚：GRPO 从 PPO 里去掉的是哪个组件？用什么替代了它？
>
> > Hint: 想想 PPO 除了 policy 之外还要训练什么。

> **2.** 看伪代码。`grpo_advantages(rewards)` 返回的 `A` 形状是什么？为什么下一行需要 `A.unsqueeze(-1)` 才能跟 `log_pi` 相乘？
>
> > Hint: 对比 `log_pi` 的形状，看看少了哪个维度。

> **3.** 假设你的 reward model 输出二值奖励（0 或 1），用 G=4。在多大比例的训练步里至少会有一个 prompt 完全没有梯度信号？你会调哪两个旋钮来缓解？
>
> > Hint: 梯度消失发生在四个采样的 reward 完全相同的时候。
