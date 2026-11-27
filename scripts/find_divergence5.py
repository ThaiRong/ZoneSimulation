from zonesim.simulation.engine import SimulationEngine
import hashlib, json, datetime

def _json_default(o):
    if isinstance(o, datetime.datetime):
        return o.isoformat()
    if isinstance(o, set):
        return sorted(o)
    return str(o)

def _sha256_full_state(state):
    from zonesim.persistence.serialization import state_to_dict
    full_dict = state_to_dict(state)
    serialized = json.dumps(
        full_dict,
        ensure_ascii=False,
        sort_keys=True,
        default=_json_default,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

# Загружаем baseline
bl = {}
with open('tests/_baseline/engine_state_seed42.json') as f:
    bl = json.load(f)

# Генерируем состояние
eng = SimulationEngine(seed=42, save_directory=None)
print(f"After init: hour={eng.state.time.hour}", flush=True)
h0_sha = _sha256_full_state(eng.state)
bl_h0 = bl.get('checkpoints', {}).get('0', {}).get('sha256', '')
print(f"  hour 0: bl={bl_h0[:20]}  cur={h0_sha[:20]}  MATCH={h0_sha == bl_h0}", flush=True)

# Запускаем час 1
eng.simulate_hour()
h1_sha = _sha256_full_state(eng.state)
print(f"  hour 1: cur={h1_sha[:20]}", flush=True)

# Показываем ключевые поля
s = eng.state
print(f"  humans={len(s.humans)} monsters={len(s.monsters)} groups={len(s.human_groups)}", flush=True)
print(f"  stationary_humans={len(s.stationary_humans)} items={len(s.items)}", flush=True)
print(f"  next_human_id={s.next_human_id} next_monster_id={s.next_monster_id}", flush=True)
print(f"  next_item_id={s.next_item_id} next_corpse_id={s.next_corpse_id}", flush=True)
