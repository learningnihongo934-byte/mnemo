import itertools

import torch

from mnemo.model import Mnemo, ModelConfig, grow, growth_schedule


@torch.no_grad()
def _max_rel_diff(a, b):
    return float((a - b).abs().max() / a.abs().max().clamp_min(1e-9))


def test_growth_preserves_function():
    torch.manual_seed(0)
    small = Mnemo(ModelConfig(vocab_size=500, d_model=256, n_layers=2))
    # Perturb so norms/weights aren't at their defaults.
    for p in small.parameters():
        p.data += 0.05 * torch.randn_like(p)
    idx = torch.randint(0, 500, (2, 40))
    before = small.full_logits(idx)

    big = grow(small, ModelConfig(vocab_size=500, d_model=512, n_layers=5))
    after = big.full_logits(idx)
    assert big.num_params() > small.num_params()
    assert _max_rel_diff(before, after) < 1e-3

    # And growing twice in a row still holds.
    bigger = grow(big, ModelConfig(vocab_size=500, d_model=768, n_layers=7))
    assert _max_rel_diff(before, bigger.full_logits(idx)) < 1e-3


def test_grown_model_learns_in_new_capacity():
    torch.manual_seed(0)
    small = Mnemo(ModelConfig(vocab_size=100, d_model=256, n_layers=1))
    big = grow(small, ModelConfig(vocab_size=100, d_model=512, n_layers=2))
    idx = torch.randint(0, 100, (2, 16))
    _, loss = big(idx[:, :-1], idx[:, 1:])
    loss.backward()
    new_layer = big.blocks[1]
    assert new_layer.attn.wo.weight.grad.abs().sum() > 0
    assert big.tok_emb.weight.grad[:, 256:].abs().sum() > 0


def test_kv_cache_matches_full_forward():
    torch.manual_seed(0)
    m = Mnemo(ModelConfig(vocab_size=300, d_model=256, n_layers=2)).eval()
    idx = torch.randint(0, 300, (1, 30))
    full = m.full_logits(idx)
    caches = [dict() for _ in m.blocks]
    m(idx[:, :20], caches=caches, start_pos=0)
    m(idx[:, 20:29], caches=caches, start_pos=20)  # chunked prefill path
    last, _ = m(idx[:, 29:30], caches=caches, start_pos=29)
    assert _max_rel_diff(full[0, -1], last[0, -1]) < 1e-4


def test_generate_and_schedule():
    m = Mnemo(ModelConfig(vocab_size=300, d_model=256, n_layers=1)).eval()
    out = list(m.generate([1, 2, 3], max_new_tokens=10))
    assert len(out) == 10
    stages = list(itertools.islice(growth_schedule(32000), 8))
    sizes = [c.param_count() for c in stages]
    assert sizes == sorted(sizes)
    assert sizes[5] > 1_000_000_000  # the 6th stage is the 1B+ model
