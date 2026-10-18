"""Speed test: one timed training step per brain size. Run: .venv/bin/python scripts/benchmark.py [stages...]
Default stages 0 1 2 3 (12M-210M). Add 5 for the 1B model (needs lots of free RAM; close other apps)."""
import os, sys; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sys, time, itertools, torch
from mnemo.model import Mnemo, growth_schedule
from mnemo.trainer import hyper_for, LionSR, _param_groups
from mnemo.config import total_ram_bytes
budget=0.6*total_ram_bytes(); dev=torch.device("mps")
for i in map(int, sys.argv[1:] or ["0", "1", "2", "3"]):
    cfg=next(itertools.islice(growth_schedule(32000),i,None)); hp=hyper_for(cfg,budget)
    m=Mnemo(cfg).to(dev, torch.bfloat16 if hp.lowmem else torch.float32); m.grad_checkpoint=hp.lowmem or cfg.d_model>=1024
    opt=LionSR(_param_groups(m,1.0),lr=hp.lr) if hp.lowmem else torch.optim.AdamW(_param_groups(m,0.1),lr=hp.lr)
    for k in range(2):
        if k==1: torch.mps.synchronize(); t=time.time()
        x=torch.randint(0,32000,(hp.micro_batch,hp.seq_len+1),device=dev)
        _,loss=m(x[:,:-1],x[:,1:]); loss.backward(); opt.step(); opt.zero_grad(set_to_none=True)
    torch.mps.synchronize(); dt=time.time()-t
    print(f"{m.num_params()/1e6:>6.0f}M  {'bf16+Lion' if hp.lowmem else 'fp32+AdamW'}  {hp.micro_batch*hp.seq_len/dt:>7.0f} tok/s  mem {torch.mps.driver_allocated_memory()/1e9:.1f}GB", flush=True)
    del m,opt,x,loss; torch.mps.empty_cache()
