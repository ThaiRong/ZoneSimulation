from zonesim.simulation.engine import SimulationEngine
from zonesim.persistence.serialization import state_to_dict
import hashlib, json, sys, datetime

CHECKPOINT_HOURS = [0, 24, 120, 240, 480]

def _json_default(o):
    if isinstance(o, datetime.datetime):
        return o.isoformat()
    if isinstance(o, set):
        return sorted(o)
    return str(o)

def _sha256_full_state(state):
    full_dict = state_to_dict(state)
    serialized = json.dumps(
        full_dict,
        ensure_ascii=False,
        sort_keys=True,
        default=_json_default,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

# Load baseline
bl = {}
with open('tests/_baseline/engine_state_seed42.json') as f:
    bl = json.load(f)

print("Checking checkpoints for seed=42:", flush=True)
for cp in CHECKPOINT_HOURS:
    bl_sha = bl.get('checkpoints', {}).get(str(cp), {}).get('sha256', '')
    eng = SimulationEngine(seed=42, save_directory=None)
    for _ in range(cp):
        eng.simulate_hour()
    cur_sha = _sha256_full_state(eng.state)
    match = "OK" if cur_sha == bl_sha else "MISMATCH"
    print(f"  hour {cp:4d}: bl={bl_sha[:20] or 'N/A'}  cur={cur_sha[:20] or 'N/A'}  {match}", flush=True)
