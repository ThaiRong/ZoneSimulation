from zonesim.simulation.engine import SimulationEngine
import hashlib, json, traceback, sys

try:
    eng = SimulationEngine(seed=42, save_directory=None)
    for i in range(10):
        eng.simulate_hour()
    print('OK 10 hours', flush=True)
    for i in range(10, 120):
        eng.simulate_hour()
    print('OK 120 hours', flush=True)
except Exception as e:
    traceback.print_exc()
