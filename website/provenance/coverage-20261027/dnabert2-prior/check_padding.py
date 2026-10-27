"""Independent non-vacuous padding audit; does not change evaluated predictions."""
import json, sys, hashlib
from pathlib import Path
import numpy as np
import torch
from transformers import AutoModelForMaskedLM

R = Path('/scratch/project_465003339/ajeppese/bend-dnabert2-prior-20261027')
M = Path('/scratch/project_465003339/ajeppese/gimbench-gtex-extra-20260923/extra-models-direct/models--zhihan1996--DNABERT-2-117M/snapshots/b5d88cda421f106afef78cd286200a5b5b8f6fea')
torch.set_num_threads(6)
torch.backends.cuda.matmul.allow_tf32 = False
torch.backends.cudnn.allow_tf32 = False
model, loading = AutoModelForMaskedLM.from_pretrained(M, trust_remote_code=True, local_files_only=True, torch_dtype=torch.float32, use_safetensors=True, output_loading_info=True)
assert not any(loading.get(k) for k in ['missing_keys', 'unexpected_keys', 'mismatched_keys', 'error_msgs'])
sys.modules[model.__class__.__module__].flash_attn_qkvpacked_func = None
model = model.cuda().eval().requires_grad_(False)
data = np.load(R/'queries.npz', allow_pickle=False)
order = np.argsort(data['token_lengths'])
indices = order[[0, 40, 100, 200]]
short = int(data['token_lengths'][indices].max())
full = data['input_ids'].shape[1]
assert short < full

@torch.inference_mode()
def score(width):
    ids = torch.tensor(data['input_ids'][indices, :width], device='cuda')
    mask = torch.tensor(data['attention_mask'][indices, :width], device='cuda')
    output = model(input_ids=ids, attention_mask=mask, token_type_ids=torch.zeros_like(ids))
    z = output.logits[torch.arange(len(indices),device='cuda'), torch.tensor(data['mask_positions'][indices],device='cuda')].double()
    bases = z[:, torch.tensor(data['base_ids'],device='cuda')]
    return torch.log_softmax(bases,-1).cpu().numpy(), (torch.logsumexp(bases,-1)-torch.logsumexp(z,-1)).cpu().numpy()

q1,m1 = score(short)
q2,m2 = score(full)
checks = {'log_probability_max_abs_difference':float(np.max(np.abs(q1-q2))), 'log_vocabulary_mass_max_abs_difference':float(np.max(np.abs(m1-m2)))}
assert max(checks.values()) < 1e-4, checks
report = {'status':'passed','indices':indices.tolist(),'trimmed_width':short,'padded_width':full, 'checks':checks, 'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'protocol_sha256':hashlib.sha256((R/'PROTOCOL.json').read_bytes()).hexdigest(), 'evaluated_predictions_sha256':hashlib.sha256((R/'predictions.parquet').read_bytes()).hexdigest()}
(R/'padding-audit.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2),flush=True)
