import hashlib
import sys
from pathlib import Path

REPO = Path(r'C:\Users\WinBug\ZoneSimulation')

# Current baselines
print("=== Current Baselines ===")
for f in ['tests/_baseline/engine_state_seed42.json',
          'tests/_baseline/engine_state_seed7.json',
          'tests/_baseline/engine_state_seed123.json']:
    fp = REPO / f
    h = hashlib.sha256(fp.read_bytes()).hexdigest()[:16]
    print(f'{f}: {h}')

# Engine line count
engine = REPO / 'src/zonesim/simulation/engine.py'
lines = len(engine.read_text(encoding='utf-8').splitlines())
print(f"\n=== engine.py: {lines} lines ===")

# New module sizes
for f in ['src/zonesim/combat/medkit.py',
          'src/zonesim/combat/results.py',
          'src/zonesim/needs/healing.py',
          'src/zonesim/needs/artifact.py',
          'src/zonesim/economy/trader.py',
          'src/zonesim/actions/capture.py',
          'src/zonesim/actions/destroy.py',
          'src/zonesim/relations/journal.py',
          'src/zonesim/world/trails.py',
          'src/zonesim/world/groups.py',
          'src/zonesim/world/shelter.py',
          'src/zonesim/world/item.py',
          'src/zonesim/anomalies/emission.py']:
    fp = REPO / f
    lc = len(fp.read_text(encoding='utf-8').splitlines())
    print(f'  {f}: {lc} lines')

# SimulationState fields count
sys.path.insert(0, str(REPO / 'src'))
import dataclasses
from zonesim.simulation.state import SimulationState
fields = len(dataclasses.fields(SimulationState))
print(f'\n=== SimulationState fields: {fields} ===')
