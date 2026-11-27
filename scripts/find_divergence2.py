from zonesim.simulation.engine import SimulationEngine
import hashlib, json

def _sha256_full_state(state):
    """Точная копия из test_engine_characterization.py."""
    from zonesim.persistence import SaveManager
    mgr = SaveManager(None)
    snap = mgr._make_state_snapshot(state)
    raw = json.dumps(snap, sort_keys=True, default=str).encode()
    return hashlib.sha256(raw).hexdigest()

# Load baseline
bl = {}
with open('tests/_baseline/engine_state_seed42.json') as f:
    bl = json.load(f)

print("Checking checkpoints:", flush=True)
for cp in ['1', '2', '4', '8', '16', '32', '64', '120']:
    bl_sha = bl.get('checkpoints', {}).get(cp, {}).get('sha256', '')
    eng = SimulationEngine(seed=42, save_directory=None)
    for _ in range(int(cp)):
        eng.simulate_hour()
    cur_sha = _sha256_full_state(eng.state)
    match = "OK" if cur_sha == bl_sha else "MISMATCH"
    print(f"  hour {cp:4s}: bl={bl_sha[:16] or 'N/A'}  cur={cur_sha[:16] or 'N/A'}  {match}", flush=True)
