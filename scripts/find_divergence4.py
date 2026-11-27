from zonesim.simulation.engine import SimulationEngine
from zonesim.persistence.serialization import state_to_dict
import hashlib, json, datetime

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

# Binary search between 0 and 24
lo, hi = 0, 24
while hi - lo > 1:
    mid = (lo + hi) // 2
    eng = SimulationEngine(seed=42, save_directory=None)
    for _ in range(mid):
        eng.simulate_hour()
    cur_sha = _sha256_full_state(eng.state)
    bl_sha = bl.get('checkpoints', {}).get(str(mid), {}).get('sha256', '')
    if cur_sha == bl_sha:
        lo = mid
    else:
        hi = mid

print(f"First divergence: after hour {lo}, checked hour {hi}", flush=True)

# Print details for both
for h in [lo, hi]:
    eng = SimulationEngine(seed=42, save_directory=None)
    for _ in range(h):
        eng.simulate_hour()
    cur_sha = _sha256_full_state(eng.state)
    bl_sha = bl.get('checkpoints', {}).get(str(h), {}).get('sha256', '')
    match = "OK" if cur_sha == bl_sha else "MISMATCH"
    print(f"  hour {h:3d}: bl={bl_sha[:20] or 'N/A'}  cur={cur_sha[:20] or 'N/A'}  {match}", flush=True)
