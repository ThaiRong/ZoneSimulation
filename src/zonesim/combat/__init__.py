"""Главная боевая петля. Связывает base, retreat, surrender, unconscious, loot. Основано на §11 ТЗ."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from zonesim.combat.base import (
    BattleLog, Combatant, CombatDefense, CombatFactory, CombatRound,
    CombatBase, select_targets, CombatResult,
)
from zonesim.combat.retreat import (
    calculate_retreat_score, resolve_retreat, should_attempt_retreat,
    calculate_enemy_power_ratio,
)
from zonesim.combat.surrender import SurrenderManager, SurrenderOutcome
from zonesim.combat.unconscious import (
    calculate_unconscious_chance, resolve_unconscious_check,
    provide_medical_help, check_injury,
)
from zonesim.combat.loot import EquipmentManager, Corpse, LootType


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


class CombatSystem:
    """Главная боевая система. (§11)"""

    MAX_ROUNDS_DEFAULT = 999  # больше 5, без жёсткого ограничения

    def __init__(
        self,
        attackers: list[Combatant],
        defenders: list[Combatant],
        sectors: dict[int, object] | None = None,
        max_rounds: int = 999,
        attacker_has_shelter: bool = False,
        defender_has_shelter: bool = False,
        attacker_is_monster: bool = False,
        defender_is_monster: bool = False,
        attacker_ambush: bool = False,
        defender_ambush: bool = False,
        battle_sector_id: int = 0,
    ):
        self.attackers = attackers
        self.defenders = defenders
        self.sectors = sectors or {}
        self.max_rounds = max_rounds
        self.attacker_shelter = attacker_has_shelter
        self.defender_shelter = defender_has_shelter
        self.attacker_is_monster = attacker_is_monster
        self.defender_is_monster = defender_is_monster
        self.attacker_ambush = attacker_ambush
        self.defender_ambush = defender_ambush
        self.battle_sector_id = battle_sector_id

        self.battle_log: list[dict] = []
        self.rounds_fought: int = 0

    def fight(self, rng_func) -> BattleResult:
        """
        Выполняет бой. (§11)
        rng_func: callable() -> float для воспроизводимой случайности.
        """
        self.rounds_fought = 0

        while self.rounds_fought < self.max_rounds:
            # Проверяем живых
            alive_attackers = [a for a in self.attackers if a.is_alive and not a.unconscious and not a.surrendered]
            alive_defenders = [d for d in self.defenders if d.is_alive and not d.unconscious and not d.surrendered]

            if not alive_attackers or not alive_defenders:
                break

            # Фаза атаки атакующих
            attack_rounds = self._resolve_phase(
                self.attackers, self.defenders,
                self.attacker_ambush,
                self.defender_shelter,
                self.defender_ambush,
                "attacker",
                rng_func,
            )
            self.battle_log.extend(attack_rounds)

            # Фаза атаки защищающихся
            defense_rounds = self._resolve_phase(
                self.defenders, self.attackers,
                self.defender_ambush,
                self.attacker_shelter,
                self.attacker_ambush,
                "defender",
                rng_func,
            )
            self.battle_log.extend(defense_rounds)

            self.rounds_fought += 1

            # Применение урона
            for r in attack_rounds:
                for attacker in self.attackers:
                    if attacker.id == r["attacker_id"]:
                        for defender in self.defenders:
                            if defender.id == r["defender_id"]:
                                defender.health -= r["damage"]
                                if defender.health <= 0:
                                    defender.health = 0

            for r in defense_rounds:
                for defender in self.defenders:
                    if defender.id == r["attacker_id"]:
                        for attacker in self.attackers:
                            if attacker.id == r["defender_id"]:
                                attacker.health -= r["damage"]
                                if attacker.health <= 0:
                                    attacker.health = 0

            # Проверка здоровья 0 (ДО отступления — при health=0 монстр мёртв, человек — бессознателен)
            self._check_zero_health(rng_func)

            # Проверка отступления после раунда
            attacker_retreat = self._check_retreat_phase(
                "attacker", rng_func,
            )
            defender_retreat = self._check_retreat_phase(
                "defender", rng_func,
            )

            if attacker_retreat:
                self.attackers[0].is_retreating = True
                break
            if defender_retreat:
                self.defenders[0].is_retreating = True
                break

            # Проверка сдачи
            self._check_surrender_phase(rng_func)

        return self._compile_result()

    def _resolve_phase(
        self,
        attacking_combatants: list[Combatant],
        defending_combatants: list[Combatant],
        ambush: bool,
        shelter_bonus: bool,
        defender_ambush: bool,
        phase_name: str,
        rng_func,
    ) -> list[dict]:
        """Решает фазу атак одной из сторон."""
        rounds: list[dict] = []
        targets = select_targets(
            attacking_combatants, defending_combatants,
            is_monster=(phase_name == "attacker" and self.attacker_is_monster),
        )

        for atk, def_ in targets:
            if not atk.is_alive or atk.unconscious:
                continue
            round_result = CombatRound(
                attacker=atk,
                defender=def_,
                ambush_bonus=ambush,
                shelter_bonus=0.1 if shelter_bonus else 0.0,
            ).resolve(rng_func())
            rounds.append(round_result)

        return rounds

    def _check_retreat_phase(
        self, side: str,
        rng_func,
    ) -> bool:
        """Проверяет, пытается ли сторона отступить после раунда."""
        if side == "attacker":
            combatants = self.attackers
            is_monster = self.attacker_is_monster
            ambush_active = self.defender_ambush
        else:
            combatants = self.defenders
            is_monster = self.defender_is_monster
            ambush_active = self.attacker_ambush

        alive = [c for c in combatants if c.is_alive and not c.unconscious and not c.surrendered]
        if not alive:
            return False

        # Считаем average health share и loss share
        avg_health = sum(c.health / c.max_health for c in alive) / len(alive) if alive else 0
        total_before = len(combatants)
        losses = total_before - len(alive)
        loss_share = losses / total_before if total_before > 0 else 0

        enemy_power = sum(
            c.attack * c.health / c.max_health for c in (self.defenders if side == "attacker" else self.attackers)
            if c.is_alive and not c.unconscious
        )
        own_power = sum(
            c.attack * c.health / c.max_health for c in alive
        )
        power_ratio = enemy_power / own_power if own_power > 0 else 2.0

        # Avg bravery
        avg_bravery = sum(c.bravery for c in alive) / len(alive) if alive else 50

        retreat_score = calculate_retreat_score(
            health_share=avg_health,
            enemy_power_ratio=power_ratio,
            bravery=avg_bravery,
            loss_share=loss_share,
        )

        if should_attempt_retreat(retreat_score, is_overwhelming=power_ratio > 2.0):
            result = resolve_retreat(
                retreat_score=retreat_score,
                retreat_chance=50.0,
                rng_value=rng_func(),
                current_sector_id=self.battle_sector_id,
                sectors=self.sectors,
                has_shelter=alive[0] in (self.attackers if side == "attacker" else self.defenders)
                              and (self.attacker_shelter if side == "attacker" else self.defender_shelter),
                ambush=ambush_active,
            )
            if result.get("success"):
                # Перемещение
                for c in alive:
                    if result.get("new_sector_id"):
                        pass  # в полной версии обновляем sector_id
                return True

        return False

    def _check_surrender_phase(self, rng_func) -> None:
        """Проверяет сдачу после раунда. (§11.9)"""
        alive_attackers = [a for a in self.attackers if a.is_alive and not a.unconscious]
        alive_defenders = [d for d in self.defenders if d.is_alive and not d.unconscious]

        if not alive_attackers or not alive_defenders:
            return

        atk = alive_attackers[0]
        def_ = alive_defenders[0]

        if atk.is_human and def_.is_human:
            atk_health_share = atk.health / atk.max_health if atk.max_health > 0 else 0
            enemy_ratio = (sum(d.attack * d.health / d.max_health for d in alive_defenders)) / \
                          max(sum(a.attack * a.health / a.max_health for a in alive_attackers), 1)

            if SurrenderManager.can_surrender(
                attacker_is_human=True,
                defender_is_human=True,
                bravery=atk.attack,
                health_share=atk_health_share,
                power_ratio=enemy_ratio,
            ):
                if rng_func() < 0.3:  # 30% шанс предложить сдачу
                    atk.surrendered = True

    def _check_zero_health(self, rng_func) -> None:
        """Проверяет здоровье 0 и применяет механику unconscious. (§11.10)"""
        for c in self.attackers + self.defenders:
            if c.health <= 0 and c.is_alive and not c.unconscious:
                if c.is_human:
                    # humans: check unconscious chance
                    # При первом достижении 0
                    start_health = c.max_health  # для упрощения
                    start_share = start_health / c.max_health if c.max_health > 0 else 0.5
                    chance = calculate_unconscious_chance(start_share)
                    outcome = resolve_unconscious_check(rng_func(), chance)
                    if outcome == "unconscious":
                        c.unconscious = True
                        c.health = 0
                else:
                    # Монстры при health 0 → труп
                    c.is_alive = False

    def _compile_result(self) -> BattleResult:
        """Собирает итоговый результат боя."""
        attacker_wear = []
        defender_wear = []

        for atk in self.attackers:
            wear = EquipmentManager.apply_weapon_wear(100, True, 0.5)
            attacker_wear.append({
                "id": atk.id,
                "name": atk.name,
                "old_condition": 100,
                "new_condition": wear.new_condition,
                "destroyed": wear.destroyed,
            })

        for def_ in self.defenders:
            wear = EquipmentManager.apply_weapon_wear(100, True, 0.5)
            defender_wear.append({
                "id": def_.id,
                "name": def_.name,
                "old_condition": 100,
                "new_condition": wear.new_condition,
                "destroyed": wear.destroyed,
            })

        attacker_dead = [a.id for a in self.attackers if not a.is_alive]
        defender_dead = [d.id for d in self.defenders if not d.is_alive]

        attacker_unconscious = [a.id for a in self.attackers if a.unconscious]
        defender_unconscious = [d.id for d in self.defenders if d.unconscious]

        attacker_surrendered = [a.id for a in self.attackers if a.surrendered]
        defender_surrendered = [d.id for d in self.defenders if d.surrendered]

        if self.defenders:
            outcome = CombatResult.ATTACKER_WINS if defender_dead else CombatResult.DRAW
        else:
            outcome = CombatResult.ATTACKER_WINS

        return BattleResult(
            outcome=outcome,
            rounds_fought=self.rounds_fought,
            attacker_survivors=[a.id for a in self.attackers if a.is_alive and not a.unconscious and not a.surrendered],
            defender_survivors=[d.id for d in self.defenders if d.is_alive and not d.unconscious and not d.surrendered],
            attacker_dead=attacker_dead,
            defender_dead=defender_dead,
            attacker_unconscious=attacker_unconscious,
            defender_unconscious=defender_unconscious,
            attacker_prisoners=attacker_surrendered,
            defender_prisoners=defender_surrendered,
            attacker_retreated=[a.id for a in self.attackers if a.is_retreating],
            defender_retreated=[d.id for d in self.defenders if d.is_retreating],
            attacker_surrendered=attacker_surrendered,
            defender_surrendered=defender_surrendered,
            equipment_wear=attacker_wear + defender_wear,
            battle_log=self.battle_log,
        )
