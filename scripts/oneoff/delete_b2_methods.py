import re
from pathlib import Path

engine_path = Path('src/zonesim/simulation/engine.py')
code = engine_path.read_text(encoding='utf-8')

method_names = [
    '_roll_trail_blockages', '_group_in_shelter', '_shelter_targets',
    '_is_group_emission_sheltered', '_emergency_medkit', '_sell_loot',
    '_use_medkit_charge', '_rest_heal', '_process_create_shelter',
    '_check_and_journal_relations', '_group_can_capture', '_group_can_destroy',
    '_give_artifact', '_set_unconscious_or_dead', '_create_item',
    '_roll_trail_blockage', '_shelter_sector_ids', '_sync_npc_from_items',
]

lines = code.splitlines(True)

method_positions = []
for method in method_names:
    for i, line in enumerate(lines):
        if f'def {method}(' in line and line.startswith('    def '):
            start = i
            end = i + 1
            while end < len(lines):
                l = lines[end]
                if l.startswith('    def ') or l.startswith('class '):
                    break
                if l.startswith('    @property'):
                    end += 1
                    continue
                end += 1
            method_positions.append((start, end, method))
            break

print(f"Found {len(method_positions)} methods:")
for start, end, name in sorted(method_positions, key=lambda x: x[0]):
    print(f"  {name}: lines {start+1}-{end} ({end-start} lines)")

for start, end, name in sorted(method_positions, key=lambda x: -x[0]):
    lines[start:end] = []

new_code = ''.join(lines)
engine_path.write_text(new_code, encoding='utf-8')
print(f"\nDeleted {len(method_positions)} methods. New line count: {len(new_code.splitlines())}")
