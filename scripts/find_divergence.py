from zonesim.simulation.engine import SimulationEngine
import hashlib, json, sys

def sha_quick(state):
    raw = json.dumps({
        'h': state.time.hour,
        'humans': len(state.humans),
        'monsters': len(state.monsters),
        'anomalies': len(state.anomalies),
        'groups': len(state.human_groups),
    }, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()

# Load baseline
bl = {}
with open('tests/_baseline/engine_state_seed42.json') as f:
    bl = json.load(f)
bl_120 = bl.get('checkpoints', {}).get('120', {}).get('sha256', '')
print(f'BL 120: {bl_120[:20]}...', flush=True)

# Run to 120
eng = SimulationEngine(seed=42, save_directory=None)
for i in range(120):
    eng.simulate_hour()
cur = sha_quick(eng.state)
print(f'CUR 120: {cur[:20]}...', flush=True)
print(f'MATCH: {cur == bl_120}', flush=True)

# Binary search for divergence
lo, hi = 0, 120
while hi - lo > 1:
    mid = (lo + hi) // 2
    eng2 = SimulationEngine(seed=42, save_directory=None)
    for _ in range(mid):
        eng2.simulate_hour()
    cur_mid = sha_quick(eng2.state)
    # Get baseline for mid
    bl_mid = bl.get('checkpoints', {}).get(str(mid), {}).get('sha256', '')
    if cur_mid == bl_mid or bl_mid == '':
        lo = mid
    else:
        hi = mid

print(f'Divergence around hour {lo}-{hi}', flush=True)
