#!/usr/bin/env python3
"""Применение B4 рефакторинга: удаление 15 методов из engine.py + обновление вызовов."""
import re

REPO = r"C:\Users\WinBug\ZoneSimulation"

# ===================== engine.py =====================
engine_path = rf"{REPO}\src\zonesim\simulation\engine.py"

with open(engine_path, encoding='utf-8') as f:
    engine = f.read()

# 1. Заменить self._emission_active(hour) → emission_active(self.state, hour)
engine = re.sub(
    r'self\._emission_active\(hour\)',
    'emission_active(self.state, hour)',
    engine
)

# 2. Заменить self._mark_group_emission_exposed(group, hour) → mark_group_emission_exposed(self.state, group, hour)
engine = re.sub(
    r'self\._mark_group_emission_exposed\(group, hour\)',
    'mark_group_emission_exposed(self.state, group, hour)',
    engine
)

# 3. Заменить self._stale_shelter_occupied_knowledge(shelter_id, hour) → stale_shelter_occupied_knowledge(self.state, shelter_id, hour)
engine = re.sub(
    r'self\._stale_shelter_occupied_knowledge\(shelter_id, hour\)',
    'stale_shelter_occupied_knowledge(self.state, shelter_id, hour)',
    engine
)

# 4. Удалить _conditional_trader_is_active (full body)
engine = re.sub(
    r'\n    def _conditional_trader_is_active\(self\) -> bool:.*?(?=\n    def _schedule_conditional_trader)',
    '',
    engine,
    flags=re.DOTALL
)

# 5. Удалить _conditional_trader_can_sleep
engine = re.sub(
    r'\n    def _conditional_trader_can_sleep\(self\) -> bool:.*?(?=\n    def _conditional_trader_base_sector)',
    '',
    engine,
    flags=re.DOTALL
)

# 6. Удалить _conditional_trader_base_sector
engine = re.sub(
    r'\n    def _conditional_trader_base_sector\(self\) -> int \| None:.*?(?=\n    def _emission_active\b)',
    '',
    engine,
    flags=re.DOTALL
)

# 7. Удалить _emission_active
engine = re.sub(
    r'\n    def _emission_active\(self, hour: int\) -> bool:.*?(?=\n    def _emission_known\b)',
    '',
    engine,
    flags=re.DOTALL
)

# 8. Удалить _emission_known
engine = re.sub(
    r'\n    def _emission_known\(self, hour: int\) -> bool:.*?(?=\n    def _schedule_conditional_trader\b)',
    '',
    engine,
    flags=re.DOTALL
)

# 9. Удалить блок delegate методов (emission/shelter)
engine = re.sub(
    r'\n    # --- Выброс.*?# --- Находки: срок жизни',
    '\n    # --- Выброс (§12.7) — все функции перенесены в anomalies/emission.py\n\n    # --- Находки: срок жизни',
    engine,
    flags=re.DOTALL
)

# 10. Удалить _group_can_create_shelter
engine = re.sub(
    r'\n    def _group_can_create_shelter\(self, group: HumanGroup, members: list\[HumanNPC\]\) -> bool:\s+return group_can_create_shelter\(self\.state, group, members\)',
    '',
    engine,
    flags=re.DOTALL
)

with open(engine_path, 'w', encoding='utf-8') as f:
    f.write(engine)

print("engine.py updated", flush=True)

# ===================== phase05_movement.py =====================
p5_path = rf"{REPO}\src\zonesim\simulation\phases\phase05_movement.py"
with open(p5_path, encoding='utf-8') as f:
    p5 = f.read()

# Add import
p5 = p5.replace(
    'from zonesim.needs.sleep import STAMINA_COST_MOVEMENT, update_stamina',
    'from zonesim.anomalies.emission import emission_active\nfrom zonesim.needs.sleep import STAMINA_COST_MOVEMENT, update_stamina'
)
# Replace calls
p5 = p5.replace('engine._emission_active(hour)', 'emission_active(state, hour)')

with open(p5_path, 'w', encoding='utf-8') as f:
    f.write(p5)
print("phase05_movement.py updated", flush=True)

# ===================== phase04_intentions.py =====================
p4_path = rf"{REPO}\src\zonesim\simulation\phases\phase04_intentions.py"
with open(p4_path, encoding='utf-8') as f:
    p4 = f.read()

# Add import
p4 = p4.replace(
    'from zonesim.anomalies.emission import emission_known',
    'from zonesim.anomalies.emission import emission_active, emission_known'
)
# Replace call
p4 = p4.replace('engine._emission_active(hour)', 'emission_active(state, hour)')

with open(p4_path, 'w', encoding='utf-8') as f:
    f.write(p4)
print("phase04_intentions.py updated", flush=True)

# ===================== phase08_environment.py =====================
p8_path = rf"{REPO}\src\zonesim\simulation\phases\phase08_environment.py"
with open(p8_path, encoding='utf-8') as f:
    p8 = f.read()

# Add import
p8 = p8.replace(
    'from zonesim.anomalies.migration import check_anomaly_migration',
    'from zonesim.anomalies.migration import check_anomaly_migration, anomaly_move_candidates'
)
# Replace call
p8 = p8.replace('engine._anomaly_move_candidates(anomaly)', 'anomaly_move_candidates(state, anomaly)')

with open(p8_path, 'w', encoding='utf-8') as f:
    f.write(p8)
print("phase08_environment.py updated", flush=True)

# ===================== test_mechanics04.py =====================
t1_path = rf"{REPO}\tests\test_mechanics04.py"
with open(t1_path, encoding='utf-8') as f:
    t1 = f.read()

# Add imports
t1 = t1.replace(
    'from zonesim.anomalies.emission import is_emission_active, apply_emission_exposure',
    'from zonesim.anomalies.emission import is_emission_active, apply_emission_exposure, process_emission_schedule\nfrom zonesim.anomalies.migration import move_all_anomalies'
)
# Replace calls
t1 = t1.replace('engine._apply_emission_exposure(hour)', 'apply_emission_exposure(engine.state, hour)')
t1 = t1.replace('engine._move_all_anomalies(hour)', 'move_all_anomalies(engine.state, hour)')
t1 = t1.replace('engine._process_emission_schedule(hour)', 'process_emission_schedule(engine.state, hour)')
t1 = t1.replace(
    'engine._process_emission_schedule(engine.state.emission_end_hour)',
    'process_emission_schedule(engine.state, engine.state.emission_end_hour)'
)

with open(t1_path, 'w', encoding='utf-8') as f:
    f.write(t1)
print("test_mechanics04.py updated", flush=True)

# ===================== test_emission_shelter_assault.py =====================
t2_path = rf"{REPO}\tests\test_emission_shelter_assault.py"
with open(t2_path, encoding='utf-8') as f:
    t2 = f.read()

# Add imports
t2 = t2.replace(
    'from zonesim.world.shelter import process_emission_shelter_assault, stale_shelter_occupied_knowledge',
    'from zonesim.world.shelter import process_emission_shelter_assault, stale_shelter_occupied_knowledge, create_shelter_occupied_knowledge\nfrom zonesim.anomalies.emission import apply_emission_exposure'
)
# Replace calls
t2 = t2.replace('engine._apply_emission_exposure(state.time.hour)', 'apply_emission_exposure(state, state.time.hour)')
t2 = t2.replace('engine._create_shelter_occupied_knowledge(shelter_id, sector_id, mg_id, hour)', 'create_shelter_occupied_knowledge(state, shelter_id, sector_id, mg_id, hour)')
t2 = t2.replace('engine._create_shelter_occupied_knowledge(shelter_id, sector_id, mg_id, state.time.hour)', 'create_shelter_occupied_knowledge(state, shelter_id, sector_id, mg_id, state.time.hour)')
t2 = t2.replace('engine._create_shelter_occupied_knowledge(shelter_id, sector_id, 0, state.time.hour)', 'create_shelter_occupied_knowledge(state, shelter_id, sector_id, 0, state.time.hour)')

with open(t2_path, 'w', encoding='utf-8') as f:
    f.write(t2)
print("test_emission_shelter_assault.py updated", flush=True)

# ===================== emission.py =====================
e_path = rf"{REPO}\src\zonesim\anomalies\emission.py"
with open(e_path, encoding='utf-8') as f:
    e = f.read()

# Fix import in broadcast_emission_warning
e = e.replace(
    'from zonesim.knowledge import KnowledgeBase, KnowledgeType',
    'from zonesim.knowledge.fact import KnowledgeBase, KnowledgeType'
)
# Add EntityStatus import
e = e.replace(
    'def broadcast_emission_warning(state, hour: int) -> None:\n    from zonesim.knowledge.fact import KnowledgeBase, KnowledgeType',
    'def broadcast_emission_warning(state, hour: int) -> None:\n    from zonesim.knowledge.fact import KnowledgeBase, KnowledgeType\n    from zonesim.world.entity import EntityStatus'
)

with open(e_path, 'w', encoding='utf-8') as f:
    f.write(e)
print("emission.py updated", flush=True)

print("\nAll files updated successfully!", flush=True)
