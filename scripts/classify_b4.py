import ast
import subprocess
import sys

with open('src/zonesim/simulation/engine.py', 'r', encoding='utf-8') as f:
    engine_tree = ast.parse(f.read())

result = subprocess.run(['git', 'show', '2d481f7:src/zonesim/simulation/engine.py'],
                       capture_output=True, text=True, cwd='.', encoding='utf-8')
base_tree = ast.parse(result.stdout)

def count_ops(node):
    return len([n for n in ast.walk(node) if isinstance(n, ast.stmt)])

methods = [
    'conditional_trader_is_active','conditional_trader_can_sleep','conditional_trader_base_sector',
    'emission_active','emission_known',
    'process_emission_schedule','broadcast_emission_warning',
    'anomaly_move_candidates','move_all_anomalies',
    'mark_group_emission_exposed','apply_emission_exposure',
    'process_shelter_occupation','create_shelter_occupied_knowledge',
    'process_emission_shelter_assault','stale_shelter_occupied_knowledge',
    'group_can_create_shelter',
]

for name in methods:
    mname = f'_{name}'
    cur = [n for n in ast.walk(engine_tree) if isinstance(n, ast.FunctionDef) and n.name == mname]
    base = [n for n in ast.walk(base_tree) if isinstance(n, ast.FunctionDef) and n.name == mname]
    cf = cur[0] if cur else None
    bf = base[0] if base else None
    status = 'IN_ENGINE' if cf else 'REMOVED'
    ops_cur = count_ops(cf) if cf else 0
    ops_base = count_ops(bf) if bf else 0
    print(f'{mname:45s} {status:12s} ops_cur={ops_cur:3d} ops_base={ops_base:3d}', flush=True)
