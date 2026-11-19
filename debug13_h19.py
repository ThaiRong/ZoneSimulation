"""Debug #13 at hour 19."""
from zonesim.simulation.engine import SimulationEngine
from zonesim.simulation.invariants import InvariantViolation, assert_world_invariants
from zonesim.world.entity import EntityStatus

log = []
def L(msg):
    log.append(msg)
    print(msg, flush=True)

try:
    e = SimulationEngine(seed=42)
    for i in range(25):
        try:
            e.simulate_hour()
        except InvariantViolation as ex:
            L(f"FAIL at iteration {i}, hour={e.state.time.hour}: {ex}")
            break
        
        if e.state.time.hour in (18, 19):
            L(f"\n=== Hour {e.state.time.hour} ===")
            for npc in e.state.humans:
                if npc.id == 13:
                    group = e.state.human_groups.get(npc.group_id)
                    if group:
                        L(f"NPC 13: status={npc.status} comfort={group.comfort} group_id={group.id}")
                        L(f"  sector={npc.sector_id} faction={npc.faction}")
                        # Check comfort conditions
                        can_rest = group.is_comfort_sleep_possible(
                            {n.id: n for n in e.state.humans},
                            {n.id: n for n in e.state.stationary_humans},
                            e.state.shelters,
                            e.state.temp_shelters,
                            e.state.sectors,
                            npc.sector_id,
                            npc.faction,
                        )
                        L(f"  is_comfort={can_rest}")
                        
                        # Check each condition
                        sid = npc.sector_id
                        faction = npc.faction
                        
                        # 1. Base
                        for sid2, s in e.state.sectors.items():
                            if sid2 == sid and getattr(s, "is_faction_start", False):
                                ctrl = getattr(s, "controller_faction", None)
                                L(f"  cond1_base: sid={sid2} start=True ctrl={ctrl} faction={faction} match={ctrl is None or ctrl == faction}")
                        
                        # 2. Temp shelters
                        temp_in_sector = [s for s in e.state.temp_shelters.values() if s.sector_id == sid]
                        L(f"  temp_shelters in sector {sid}: {len(temp_in_sector)}")
                        for ts in temp_in_sector:
                            L(f"    ts id={ts.id} active={ts.is_active} participant_count={ts.participant_count}")
                        
                        # 3. StormShelter
                        storm_in_sector = [s for s in e.state.shelters.values() if type(s).__name__ == "StormShelter" and s.sector_id == sid]
                        L(f"  StormShelter in sector {sid}: {len(storm_in_sector)}")
                        
                        # 4. Guard
                        guards = [n for n in e.state.stationary_humans if n.stationary_role == "guard" and n.status == EntityStatus.ACTIVE and n.sector_id == sid]
                        L(f"  Guards in sector {sid}: {len(guards)}")
                        
                        # 5. Guard schedule
                        for entry in group.guard_schedule:
                            L(f"    guard_schedule entry: npc_id={entry.get('npc_id')} start={entry.get('start_hour')} end={entry.get('end_hour')}")
                    break
            
            if e.state.time.hour == 18:
                errors = assert_world_invariants(e.state)
                inv13 = [x for x in errors if '#13' in x]
                L(f"  Invariant #13 errors: {len(inv13)}")
                for err in inv13[:3]:
                    L(f"    {err}")

except Exception as ex:
    import traceback
    L(f"EXCEPTION: {ex}")
    L(traceback.format_exc())

with open(r'C:\Users\WinBug\ZoneSimulation\debug13_h19.txt', 'w') as f:
    f.write('\n'.join(log))
