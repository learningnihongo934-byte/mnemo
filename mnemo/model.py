"""Mnemo's brain: a decoder-only transformer that starts tiny and grows.

Architecture: RMSNorm, rotary position embeddings (RoPE), grouped-query
attention, SwiGLU MLP, tied input/output embeddings. Head size is fixed at 64,
so the model can be widened (more heads, wider MLP) and deepened (more layers)
with `grow()`, which is *function preserving*: the grown model produces the
same outputs as the small one, so nothing learned is lost, and training simply
continues with more capacity.

Context: RoPE has no learned position table, so the model accepts sequences up
to `max_context` (100k tokens by default). How well it *uses* long context
depends on the sequence lengths it has trained on.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, asdict, replace

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.checkpoint import checkpoint

HEAD_DIM = 64
KV_GROUP = 4  # query heads per key/value head


def _ffn_hidden(d_model: int) -> int:
    h = int(8 * d_model / 3)
    return ((h + 63) // 64) * 64


@dataclass
class ModelConfig:
    vocab_size: int = 32000
    d_model: int = 256
    n_layers: int = 6
    ffn_hidden: int = 0  # 0 = derived from d_model
    max_context: int = 100_000
    rope_theta: float = 1_000_000.0
    norm_eps: float = 1e-5

    def __post_init__(self):
        if self.d_model % (HEAD_DIM * KV_GROUP) and self.d_model % HEAD_DIM:
            raise ValueError("d_model must be a multiple of 64")
        if not self.ffn_hidden:
            self.ffn_hidden = _ffn_hidden(self.d_model)

    @property
    def n_heads(self) -> int:
        return self.d_model // HEAD_DIM

    @property
    def n_kv_heads(self) -> int:
        return max(1, self.n_heads // KV_GROUP)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def param_count(self) -> int:
        d, h, L = self.d_model, self.ffn_hidden, self.n_layers
        kv = self.n_kv_heads * HEAD_DIM
        attn = d * d * 2 + d * kv * 2
        mlp = 3 * d * h
        return self.vocab_size * d + L * (attn + mlp + 2 * d) + d


class RMSNorm(nn.Module):
    def __init__(self, dim: int, eps: float):
        super().__init__()
        # eps is a buffer because growth rescales it (see grow()).
        self.register_buffer("eps", torch.tensor(float(eps)))
        self.weight = nn.Parameter(torch.ones(dim))

    def forward(self, x):
        xf = x.float()
        xf = xf * torch.rsqrt(xf.pow(2).mean(-1, keepdim=True) + self.eps.float())
        return xf.to(x.dtype) * self.weight


class Rotary:
    """Cached cos/sin tables for RoPE, extended on demand."""

    def __init__(self, theta: float):
        self.theta = theta
        self.cos = self.sin = None

    def get(self, start: int, length: int, device, dtype):
        end = start + length
        if self.cos is None or self.cos.shape[0] < end or self.cos.device != device:
            n = max(end, 2048 if self.cos is None else self.cos.shape[0] * 2)
            inv = 1.0 / (self.theta ** (torch.arange(0, HEAD_DIM, 2, device=device).float() / HEAD_DIM))
            t = torch.arange(n, device=device).float()
            freqs = torch.outer(t, inv)
            emb = torch.cat([freqs, freqs], dim=-1)
            self.cos, self.sin = emb.cos(), emb.sin()
        return self.cos[start:end].to(dtype), self.sin[start:end].to(dtype)


def _rope(x, cos, sin):
    x1, x2 = x.chunk(2, dim=-1)
    rotated = torch.cat([-x2, x1], dim=-1)
    return x * cos + rotated * sin


class Attention(nn.Module):
    def __init__(self, cfg: ModelConfig):
        super().__init__()
        self.n_heads, self.n_kv = cfg.n_heads, cfg.n_kv_heads
        self.wq = nn.Linear(cfg.d_model, self.n_heads * HEAD_DIM, bias=False)
        self.wk = nn.Linear(cfg.d_model, self.n_kv * HEAD_DIM, bias=False)
        self.wv = nn.Linear(cfg.d_model, self.n_kv * HEAD_DIM, bias=False)
        self.wo = nn.Linear(self.n_heads * HEAD_DIM, cfg.d_model, bias=False)

    def forward(self, x, cos, sin, cache=None):
        B, T, _ = x.shape
        q = self.wq(x).view(B, T, self.n_heads, HEAD_DIM).transpose(1, 2)
        k = self.wk(x).view(B, T, self.n_kv, HEAD_DIM).transpose(1, 2)
        v = self.wv(x).view(B, T, self.n_kv, HEAD_DIM).transpose(1, 2)
        q, k = _rope(q, cos, sin), _rope(k, cos, sin)

        past = 0
        if cache is not None:
            if cache.get("k") is not None:
                past = cache["k"].shape[2]
                k = torch.cat([cache["k"], k], dim=2)
                v = torch.cat([cache["v"], v], dim=2)
            cache["k"], cache["v"] = k, v

        group = self.n_heads // self.n_kv
        if group > 1:
            k = k.repeat_interleave(group, dim=1)
            v = v.repeat_interleave(group, dim=1)

        if past == 0:
            out = F.scaled_dot_product_attention(q, k, v, is_causal=T > 1)
        elif T == 1:
            out = F.scaled_dot_product_attention(q, k, v)
        else:  # chunked prefill on top of an existing cache
            S = k.shape[2]
            mask = torch.ones(T, S, dtype=torch.bool, device=x.device).tril(diagonal=past)
            out = F.scaled_dot_product_attention(q, k, v, attn_mask=mask)
        out = out.transpose(1, 2).reshape(B, T, self.n_heads * HEAD_DIM)
        return self.wo(out)


class MLP(nn.Module):
    def __init__(self, cfg: ModelConfig):
        super().__init__()
        self.w1 = nn.Linear(cfg.d_model, cfg.ffn_hidden, bias=False)
        self.w3 = nn.Linear(cfg.d_model, cfg.ffn_hidden, bias=False)
        self.w2 = nn.Linear(cfg.ffn_hidden, cfg.d_model, bias=False)

    def forward(self, x):
        return self.w2(F.silu(self.w1(x)) * self.w3(x))


class Block(nn.Module):
    def __init__(self, cfg: ModelConfig):
        super().__init__()
        self.norm1 = RMSNorm(cfg.d_model, cfg.norm_eps)
        self.attn = Attention(cfg)
        self.norm2 = RMSNorm(cfg.d_model, cfg.norm_eps)
        self.mlp = MLP(cfg)

    def forward(self, x, cos, sin, cache=None):
        x = x + self.attn(self.norm1(x), cos, sin, cache)
        return x + self.mlp(self.norm2(x))


class Mnemo(nn.Module):
    def __init__(self, cfg: ModelConfig):
        super().__init__()
        self.cfg = cfg
        self.tok_emb = nn.Embedding(cfg.vocab_size, cfg.d_model)
        self.blocks = nn.ModuleList(Block(cfg) for _ in range(cfg.n_layers))
        self.norm_f = RMSNorm(cfg.d_model, cfg.norm_eps)
        self.rotary = Rotary(cfg.rope_theta)
        self.grad_checkpoint = False
        self._init_weights()

    def _init_weights(self):
        out_std = 0.02 / math.sqrt(2 * self.cfg.n_layers)
        for name, p in self.named_parameters():
            if p.dim() == 2:
                std = out_std if name.endswith(("wo.weight", "w2.weight")) else 0.02
                nn.init.normal_(p, mean=0.0, std=std)

    def num_params(self) -> int:
        return sum(p.numel() for p in self.parameters())

    def forward(self, idx, targets=None, caches=None, start_pos: int = 0):
        B, T = idx.shape
        x = self.tok_emb(idx)
        cos, sin = self.rotary.get(start_pos, T, idx.device, x.dtype)
        for i, block in enumerate(self.blocks):
            cache = caches[i] if caches is not None else None
            if self.grad_checkpoint and self.training and cache is None:
                x = checkpoint(block, x, cos, sin, use_reentrant=False)
            else:
                x = block(x, cos, sin, cache)
        x = self.norm_f(x)
        if targets is None:
            return F.linear(x[:, -1:, :], self.tok_emb.weight), None
        logits = F.linear(x, self.tok_emb.weight)
        loss = F.cross_entropy(logits.float().reshape(-1, logits.size(-1)), targets.reshape(-1), ignore_index=-1)
        return logits, loss

    def full_logits(self, idx):
        """Logits at every position (used by tests and evaluation)."""
        x = self.tok_emb(idx)
        cos, sin = self.rotary.get(0, idx.shape[1], idx.device, x.dtype)
        for block in self.blocks:
            x = block(x, cos, sin)
        return F.linear(self.norm_f(x), self.tok_emb.weight)

    @torch.no_grad()
    def generate(self, prompt_ids, max_new_tokens=200, temperature=0.8, top_k=50, top_p=0.95,
                 repetition_penalty=1.15, stop_ids=(), should_stop=None):
        """Yield new token ids one at a time, using a KV cache."""
        device = self.tok_emb.weight.device
        limit = self.cfg.max_context - max_new_tokens
        ids = list(prompt_ids)[-max(1, limit):]
        caches = [dict() for _ in self.blocks]

        # Prefill in chunks so a 100k-token prompt doesn't need a giant attention matrix.
        pos = 0
        logits = None
        while pos < len(ids):
            budget = int(1.5e8 / (max(1, pos + 1) * self.cfg.n_heads))
            chunk = max(64, min(2048, budget))
            piece = torch.tensor([ids[pos:pos + chunk]], device=device)
            logits, _ = self(piece, caches=caches, start_pos=pos)
            pos += piece.shape[1]

        recent = ids[-256:]
        for _ in range(max_new_tokens):
            if should_stop and should_stop():
                return
            logit = logits[0, -1].float()
            if repetition_penalty != 1.0 and recent:
                seen = torch.tensor(sorted(set(recent)), device=device)
                vals = logit[seen]
                logit[seen] = torch.where(vals > 0, vals / repetition_penalty, vals * repetition_penalty)
            if temperature <= 0:
                nxt = int(torch.argmax(logit))
            else:
                logit = logit / temperature
                if top_k:
                    kth = torch.topk(logit, min(top_k, logit.numel())).values[-1]
                    logit[logit < kth] = -float("inf")
                probs = F.softmax(logit, dim=-1)
                if top_p < 1.0:
                    sp, si = torch.sort(probs, descending=True)
                    cut = torch.cumsum(sp, dim=0) - sp > top_p
                    sp[cut] = 0
                    probs = torch.zeros_like(probs).scatter_(0, si, sp)
                nxt = int(torch.multinomial(probs / probs.sum(), 1))
            if nxt in stop_ids:
                return
            yield nxt
            recent = (recent + [nxt])[-256:]
            if pos >= self.cfg.max_context:
                return
            logits, _ = self(torch.tensor([[nxt]], device=device), caches=caches, start_pos=pos)
            pos += 1


# ----------------------------------------------------------------------------
# Growth
# ----------------------------------------------------------------------------

@torch.no_grad()
def grow(old: Mnemo, new_cfg: ModelConfig) -> Mnemo:
    """Return a bigger model that computes exactly the same function as `old`.

    New residual dimensions start at zero, new heads / MLP units / layers feed
    into the residual stream through zero-initialised output weights, and
    norms are rescaled to cancel the extra zero dimensions. New input-side
    weights are random, so the added capacity receives gradients immediately.
    """
    oc = old.cfg
    if new_cfg.d_model < oc.d_model or new_cfg.n_layers < oc.n_layers or new_cfg.ffn_hidden < oc.ffn_hidden:
        raise ValueError("grow() can only make the model bigger")
    if new_cfg.vocab_size != oc.vocab_size:
        raise ValueError("vocabulary must stay the same")

    dev = old.tok_emb.weight.device
    dtype = old.tok_emb.weight.dtype
    new = Mnemo(new_cfg).to(device=dev, dtype=dtype)
    d0, d1 = oc.d_model, new_cfg.d_model
    norm_scale = math.sqrt(d0 / d1)

    new.tok_emb.weight.zero_()
    new.tok_emb.weight[:, :d0] = old.tok_emb.weight

    def grow_norm(dst: RMSNorm, src: RMSNorm):
        # Zero-padding the residual shrinks mean(x^2) by d0/d1; scaling eps by the
        # same factor and the weight by sqrt(d0/d1) cancels that exactly.
        dst.eps.copy_(src.eps * (d0 / d1))
        dst.weight.fill_(float(src.weight.mean()) * norm_scale)
        dst.weight[:d0] = src.weight * norm_scale

    def grow_in_out(dst: nn.Linear, src: nn.Linear):
        """Linear reading the residual stream: copy old block, keep the rest random."""
        o, i = src.weight.shape
        dst.weight[:o, :i] = src.weight

    def grow_to_residual(dst: nn.Linear, src: nn.Linear):
        """Linear writing into the residual stream: copy old block, zero the rest."""
        o, i = src.weight.shape
        dst.weight.zero_()
        dst.weight[:o, :i] = src.weight

    grow_norm(new.norm_f, old.norm_f)

    # Spread new identity layers evenly between the old ones.
    n_new = new_cfg.n_layers - oc.n_layers
    per_slot = [0] * oc.n_layers
    for j in range(n_new):
        per_slot[(j * oc.n_layers) // n_new] += 1
    layout = []  # old layer index, or None for a new identity layer
    for i in range(oc.n_layers):
        layout.append(i)
        layout.extend([None] * per_slot[i])

    for dst, src_idx in zip(new.blocks, layout):
        if src_idx is None:  # brand-new layer: make it an exact identity
            dst.attn.wo.weight.zero_()
            dst.mlp.w2.weight.zero_()
            continue
        src = old.blocks[src_idx]
        grow_norm(dst.norm1, src.norm1)
        grow_norm(dst.norm2, src.norm2)
        grow_in_out(dst.attn.wq, src.attn.wq)
        grow_in_out(dst.attn.wk, src.attn.wk)
        grow_in_out(dst.attn.wv, src.attn.wv)
        grow_to_residual(dst.attn.wo, src.attn.wo)
        grow_in_out(dst.mlp.w1, src.mlp.w1)
        grow_in_out(dst.mlp.w3, src.mlp.w3)
        grow_to_residual(dst.mlp.w2, src.mlp.w2)

    new.grad_checkpoint = old.grad_checkpoint
    return new


def growth_schedule(vocab_size: int):
    """Endless list of stages. Each is (d_model, n_layers); width and depth alternate."""
    stages = [(256, 6), (512, 8), (768, 12), (1024, 16), (1536, 20), (2048, 22)]
    for d, L in stages:
        yield ModelConfig(vocab_size=vocab_size, d_model=d, n_layers=L)
    d, L = stages[-1]
    while True:
        L += 4
        yield ModelConfig(vocab_size=vocab_size, d_model=d, n_layers=L)
        d += 512
        yield ModelConfig(vocab_size=vocab_size, d_model=d, n_layers=L)
