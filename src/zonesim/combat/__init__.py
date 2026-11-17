"""Главная боевая петля. Связывает раунды, отступление, сдачу и последствия (§11)."""

from __future__ import annotations

from dataclasses import dataclass, field

from zonesim.combat.base import (
    Combatant,
    CombatBase,
    CombatResult,
    CombatRound,
    select_targets,
)
from zonesim.combat.base import (
    CombatFactory as CombatFactory,
)
from zonesim.combat.loot import EquipmentManager
from zonesim.combat.retreat import (
    calculate_enemy_power_ratio,
    calculate_retreat_chance,
    calculate_retreat_score,
    resolve_retreat,
    should_attempt_retreat,
)
from zonesim.combat.surrender import SurrenderManager
from zonesim.combat.unconscious import (
    calculate_unconscious_chance,
    provide_medical_help,
    resolve_unconscious_check,
)


@dataclass
class BattleResult:
    """Результат всего столкновения."""

    outcome: str
    rounds_fought: int
    attacker_survivors: list[int]
    defender_survivors: list[int]
    attacker_dead: list[int]
    defender_dead: list[int]
    attacker_unconscious: list[int]
    defender_unconscious: list[int]
    attacker_prisoners: list[int]
    defender_prisoners: list[int]
    attacker_retreated: list[int]
    defender_retreated: list[int]
    attacker_surrendered: list[int]
    defender_surrendered: list[int]
    equipment_wear: list[dict] = field(default_factory=list)
    corpses: list[dict] = field(default_factory=list)
    medical_help: dict = field(default_factory=dict)
    value_damage: list[dict] = field(default_factory=list)
    battle_log: list[dict] = field(default_factory=list)
    attacker_retreat_sector: int | None = None
    defender_retreat_sector: int | None = None


class CombatSystem:
    """Автоматический бой с предбоевым отступлением и лимитом в десять раундов."""

    MAX_ROUNDS_DEFAULT = 10
    PRE_COMBAT_RETREAT_BONUS = 20.0

    def __init__(
        self,
        attackers: list[Combatant],
        defenders: list[Combatant],
        sectors: dict[int, object] | None = None,
        max_rounds: int = MAX_ROUNDS_DEFAULT,
        attacker_has_shelter: bool = False,
        defender_has_shelter: bool = False,
        attacker_is_monster: bool = False,
        defender_is_monster: bool = False,
        attacker_ambush: bool = False,
        defender_ambush: bool = False,
        battle_sector_id: int = 0,
        relation: int = 0,
        attacker_bonus: float = 0.1,
        defender_bonus: float = 0.1,
    ):
        self.attackers = attackers
        self.defenders = defenders
        self.sectors = sectors or {}
        self.max_rounds = max(1, min(max_rounds, self.MAX_ROUNDS_DEFAULT))
        self.attacker_shelter = attacker_has_shelter
        self.defender_shelter = defender_has_shelter
        # бонус защищающейся стороны: обычное укрытие 0.1, укрепление базы 0.7
        self.attacker_bonus = attacker_bonus
        self.defender_bonus = defender_bonus
        self.attacker_is_monster = attacker_is_monster
        self.defender_is_monster = defender_is_monster
        self.attacker_ambush = attacker_ambush
        self.defender_ambush = defender_ambush
        self.battle_sector_id = battle_sector_id
        self.relation = relation

        self.battle_log: list[dict] = []
        self.rounds_fought = 0
        self.medical_help: dict = {}
        self.equipment_wear: list[dict] = []
        self._start_health = {
            c.id: c.health / c.max_health if c.max_health > 0 else 0.0
            for c in attackers + defenders
        }
        self._damage_received = {c.id: 0 for c in attackers + defenders}
        self._failed_retreat = {"attacker": False, "defender": False}
        self._retreat_sectors: dict[str, int] = {}

    @staticmethod
    def _active(combatants: list[Combatant]) -> list[Combatant]:
        return [
            c for c in combatants
            if c.is_alive and not c.unconscious and not c.surrendered and not c.is_retreating
        ]

    def _side(self, side: str) -> list[Combatant]:
        return self.attackers if side == "attacker" else self.defenders

    def _enemy(self, side: str) -> list[Combatant]:
        return self.defenders if side == "attacker" else self.attackers

    def fight(self, rng_func) -> BattleResult:
        """Выполняет бой с воспроизводимым источником случайных чисел."""
        self.rounds_fought = 0
        self.battle_log = []

        if self._check_retreat_phase("attacker", rng_func):
            return self._compile_result()
        if self._check_retreat_phase("defender", rng_func):
            return self._compile_result()

        while self.rounds_fought < self.max_rounds:
            if not self._active(self.attackers) or not self._active(self.defenders):
                break

            self._consume_ammo(self.attackers)
            self._consume_ammo(self.defenders)
            attack_rounds = self._resolve_phase("attacker", rng_func)
            defense_rounds = self._resolve_phase("defender", rng_func)
            self.rounds_fought += 1

            for entry in attack_rounds + defense_rounds:
                entry["round"] = self.rounds_fought
            self.battle_log.extend(attack_rounds + defense_rounds)
            self._apply_round_damage(attack_rounds, defense_rounds)
            self._check_zero_health(rng_func)

            for combatant in self.attackers + self.defenders:
                combatant.attack_penalty = 1.0
                combatant.defense_penalty = 1.0
            self._failed_retreat = {"attacker": False, "defender": False}

            if self._check_retreat_phase("attacker", rng_func):
                break
            if self._check_retreat_phase("defender", rng_func):
                break

            self._check_surrender_phase("attacker", rng_func)
            self._check_surrender_phase("defender", rng_func)

        self._apply_medical_help(rng_func)
        self._apply_equipment_wear(rng_func)
        for combatant in self.attackers + self.defenders:
            combatant.stamina = max(0.0, combatant.stamina - 5.0)
        return self._compile_result()

    def _consume_ammo(self, combatants: list[Combatant]) -> None:
        for combatant in self._active(combatants):
            if combatant.is_human and combatant.ammo > 0:
                combatant.ammo -= 1

    def _resolve_phase(self, side: str, rng_func) -> list[dict]:
        attackers = self._side(side)
        defenders = self._enemy(side)
        is_monster = self.attacker_is_monster if side == "attacker" else self.defender_is_monster
        ambush = self.attacker_ambush if side == "attacker" else self.defender_ambush
        shelter = self.defender_shelter if side == "attacker" else self.attacker_shelter
        results = []
        targets = select_targets(attackers, defenders, is_monster=is_monster)
        for attacker, defender in targets:
            result = CombatRound(
                attacker=attacker,
                defender=defender,
                ambush_bonus=ambush and self.rounds_fought == 0,
                shelter_bonus=(
                    (self.defender_bonus if side == "attacker" else self.attacker_bonus)
                    if shelter else 0.0
                ),
            ).resolve(rng_func)
            results.append(result)
        return results

    def _apply_round_damage(self, attack_rounds: list[dict], defense_rounds: list[dict]) -> None:
        for rounds, attackers, defenders in (
            (attack_rounds, self.attackers, self.defenders),
            (defense_rounds, self.defenders, self.attackers),
        ):
            attacker_map = {c.id: c for c in attackers}
            defender_map = {c.id: c for c in defenders}
            for entry in rounds:
                attacker = attacker_map[entry["attacker_id"]]
                defender = defender_map[entry["defender_id"]]
                if attacker.is_alive and defender.is_alive:
                    defender.health = max(0, defender.health - entry["damage"])
                    self._damage_received[defender.id] += entry["damage"]

    def _check_zero_health(self, rng_func) -> None:
        for combatant in self.attackers + self.defenders:
            if combatant.health > 0 or not combatant.is_alive or combatant.unconscious:
                continue
            if not combatant.is_human:
                combatant.is_alive = False
                continue
            chance = calculate_unconscious_chance(self._start_health[combatant.id])
            if resolve_unconscious_check(rng_func(), chance) == "unconscious":
                combatant.unconscious = True
            else:
                combatant.is_alive = False

    def _check_retreat_phase(self, side: str, rng_func) -> bool:
        combatants = self._side(side)
        alive = self._active(combatants)
        enemies = self._active(self._enemy(side))
        if not alive or not enemies:
            return False

        pre_combat = self.rounds_fought == 0
        if pre_combat and not all(c.is_human for c in alive):
            return False

        enemy_ambush = self.defender_ambush if side == "attacker" else self.attacker_ambush
        if enemy_ambush and self.rounds_fought == 1:
            return False

        avg_health = sum(c.health / c.max_health for c in alive) / len(alive)
        loss_share = (len(combatants) - len(alive)) / len(combatants)
        own_power = CombatBase.calculate_group_bp(alive)
        enemy_power = CombatBase.calculate_group_bp(enemies)
        power_ratio = calculate_enemy_power_ratio(enemy_power, own_power)
        avg_bravery = sum(c.bravery for c in alive) / len(alive)
        score = calculate_retreat_score(avg_health, power_ratio, avg_bravery, loss_share)

        if not should_attempt_retreat(score, is_overwhelming=power_ratio > 2.0):
            return False

        chance = calculate_retreat_chance(
            speed_ratio=self._speed_ratio(side),
            escape_att=round(sum(c.attentiveness for c in alive) / len(alive)),
            pursuer_att=round(sum(c.attentiveness for c in enemies) / len(enemies)),
            shelter_bonus=(
                (self.attacker_bonus if side == "attacker" else self.defender_bonus)
                if (self.attacker_shelter if side == "attacker" else self.defender_shelter)
                else 0.0
            ),
        )
        if pre_combat:
            chance = min(95.0, chance + self.PRE_COMBAT_RETREAT_BONUS)
        result = resolve_retreat(
            retreat_score=score,
            retreat_chance=chance,
            rng_value=rng_func(),
            current_sector_id=self.battle_sector_id,
            sectors=self.sectors,
            has_shelter=self.attacker_shelter if side == "attacker" else self.defender_shelter,
            ambush=enemy_ambush and self.rounds_fought == 1,
        )
        self.battle_log.append({
            "type": "retreat",
            "side": side,
            "round": self.rounds_fought,
            "pre_combat": pre_combat,
            "chance": chance,
            **result,
        })
        if result["success"]:
            for combatant in alive:
                combatant.is_retreating = True
            self._retreat_sectors[side] = result["new_sector_id"]
            return True

        if result.get("reason") == "failed":
            self._failed_retreat[side] = True
            for combatant in alive:
                combatant.attack_penalty = 0.9
                combatant.defense_penalty = 0.8
        return False

    def _speed_ratio(self, side: str) -> float:
        own = self._side(side)
        enemy = self._enemy(side)

        def speed(combatants):
            return max((2.0 if c.species == "TerritorialPredator" else 1.0) for c in combatants)

        return speed(own) / speed(enemy)

    def _check_surrender_phase(self, side: str, rng_func) -> None:
        if not self._failed_retreat[side]:
            return
        combatants = self._active(self._side(side))
        enemies = self._active(self._enemy(side))
        if not combatants or not enemies:
            return
        if not all(c.is_human for c in combatants + enemies):
            return

        health = sum(c.health / c.max_health for c in combatants) / len(combatants)
        bravery = sum(c.bravery for c in combatants) / len(combatants)
        ratio = calculate_enemy_power_ratio(
            CombatBase.calculate_group_bp(enemies),
            CombatBase.calculate_group_bp(combatants),
        )
        if not SurrenderManager.can_surrender(True, True, bravery, health, ratio, self.relation):
            return
        if rng_func() >= 0.3:
            return

        outcome = SurrenderManager.determine_outcome(
            surrendering_count=len(combatants),
            captor_count=len(enemies),
            relation=self.relation,
            captor_faction=enemies[0].faction,
            target_faction=combatants[0].faction,
            bravery=bravery,
            rng_value=rng_func(),
        )
        for index in outcome["captured"]:
            combatants[index].surrendered = True
        for index in outcome["killed"]:
            combatants[index].is_alive = False
            combatants[index].health = 0
        for index in outcome["released"]:
            combatants[index].is_retreating = True
            self._retreat_sectors[side] = self.battle_sector_id
        self.battle_log.append({
            "type": "surrender",
            "side": side,
            "round": self.rounds_fought,
            "outcome": outcome["outcome"].value,
            "participants": [c.id for c in combatants],
        })

    def _apply_medical_help(self, rng_func) -> None:
        attackers_active = self._active(self.attackers)
        defenders_active = self._active(self.defenders)
        winners = []
        losers = []
        if attackers_active and not defenders_active:
            winners, losers = self.attackers, self.defenders
        elif defenders_active and not attackers_active:
            winners, losers = self.defenders, self.attackers

        helped_ids = set()
        unconscious = [c for c in winners if c.is_alive and c.unconscious]
        if unconscious and all(c.is_human for c in winners):
            medicines = sum(c.medicines for c in winners + losers)
            result = provide_medical_help(
                unconscious_ids=[c.id for c in unconscious],
                available_medicines=medicines,
                unconscious_state={c.id: 0 for c in unconscious},
                max_healths={c.id: c.max_health for c in unconscious},
                rng_value=rng_func(),
            )
            self.medical_help = result
            by_id = {c.id: c for c in unconscious}
            for entry in result["helped"]:
                combatant = by_id[entry["id"]]
                combatant.health = entry["new_health"]
                combatant.unconscious = False
                helped_ids.add(combatant.id)
            to_consume = result["medicines_used"]
            for combatant in winners + losers:
                used = min(combatant.medicines, to_consume)
                combatant.medicines -= used
                to_consume -= used

        # Проигравшие бессознательные люди стабилизируются собственными
        # медикаментами, если победители не намерены добить (§11.10).
        # Монстры добивают безжалостно; люди — только при крайней вражде.
        winners_are_monsters = bool(winners) and not winners[0].is_human
        winners_hateful = (
            bool(winners)
            and all(c.is_human for c in winners)
            and self.relation <= -60
        )
        execute_losers = winners_are_monsters or winners_hateful
        stabilized_ids = set()
        if not execute_losers:
            for combatant in losers:
                if not (combatant.is_human and combatant.unconscious and combatant.medicines > 0):
                    continue
                combatant.medicines -= 1
                combatant.health = max(
                    1, int(combatant.max_health * (0.15 + 0.10 * rng_func())),
                )
                combatant.unconscious = False
                stabilized_ids.add(combatant.id)

        for combatant in self.attackers + self.defenders:
            if (
                combatant.unconscious
                and combatant.id not in helped_ids
                and combatant.id not in stabilized_ids
            ):
                combatant.unconscious = False
                combatant.is_alive = False
                combatant.health = 0

    def _apply_equipment_wear(self, rng_func) -> None:
        self.equipment_wear = []
        for combatant in self.attackers + self.defenders:
            old_condition = combatant.weapon_condition
            wear = EquipmentManager.apply_weapon_wear(old_condition, True, rng_func())
            combatant.weapon_condition = wear.new_condition
            self.equipment_wear.append({
                "id": combatant.id,
                "name": combatant.name,
                "item_type": "weapon",
                "old_condition": old_condition,
                "new_condition": wear.new_condition,
                "destroyed": wear.destroyed,
            })
            damage_received = self._damage_received[combatant.id]
            if combatant.is_human and damage_received > 0:
                old_armor = combatant.armor_condition
                armor_wear = EquipmentManager.apply_armor_damage(
                    old_armor, damage_received, rng_func()
                )
                combatant.armor_condition = armor_wear.new_condition
                self.equipment_wear.append({
                    "id": combatant.id,
                    "name": combatant.name,
                    "item_type": "armor",
                    "old_condition": old_armor,
                    "new_condition": armor_wear.new_condition,
                    "destroyed": armor_wear.destroyed,
                })

    def _compile_result(self) -> BattleResult:
        attackers_active = self._active(self.attackers)
        defenders_active = self._active(self.defenders)
        attacker_retreated = [c.id for c in self.attackers if c.is_retreating]
        defender_retreated = [c.id for c in self.defenders if c.is_retreating]
        attacker_surrendered = [c.id for c in self.attackers if c.surrendered]
        defender_surrendered = [c.id for c in self.defenders if c.surrendered]

        if attacker_retreated:
            outcome = CombatResult.ATTACKER_RETREATED
        elif defender_retreated:
            outcome = CombatResult.DEFENDER_RETREATED
        elif attacker_surrendered and not attackers_active:
            outcome = CombatResult.ATTACKER_SURRENDERED
        elif defender_surrendered and not defenders_active:
            outcome = CombatResult.DEFENDER_SURRENDERED
        elif attackers_active and not defenders_active:
            outcome = CombatResult.ATTACKER_WINS
        elif defenders_active and not attackers_active:
            outcome = CombatResult.DEFENDER_WINS
        else:
            outcome = CombatResult.DRAW

        return BattleResult(
            outcome=outcome.value,
            rounds_fought=self.rounds_fought,
            attacker_survivors=[c.id for c in attackers_active],
            defender_survivors=[c.id for c in defenders_active],
            attacker_dead=[c.id for c in self.attackers if not c.is_alive],
            defender_dead=[c.id for c in self.defenders if not c.is_alive],
            attacker_unconscious=[c.id for c in self.attackers if c.unconscious],
            defender_unconscious=[c.id for c in self.defenders if c.unconscious],
            attacker_prisoners=attacker_surrendered,
            defender_prisoners=defender_surrendered,
            attacker_retreated=attacker_retreated,
            defender_retreated=defender_retreated,
            attacker_surrendered=attacker_surrendered,
            defender_surrendered=defender_surrendered,
            equipment_wear=self.equipment_wear,
            corpses=[
                {"entity_id": c.id, "sector_id": self.battle_sector_id}
                for c in self.attackers + self.defenders if not c.is_alive
            ],
            medical_help=self.medical_help,
            battle_log=self.battle_log,
            attacker_retreat_sector=self._retreat_sectors.get("attacker"),
            defender_retreat_sector=self._retreat_sectors.get("defender"),
        )
