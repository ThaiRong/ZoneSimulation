"""Боевая система: базовая сила, выбор целей, раунд. Основано на §11.2-11.5 ТЗ."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from zonesim.world.entity import EntityStatus, HumanNPC, Monster


class CombatResult(str, Enum):
    ATTACKER_WINS = "attacker_wins"
    DEFENDER_WINS = "defender_wins"
    ATTACKER_RETREATED = "attacker_retreated"
    DEFENDER_RETREATED = "defender_retreated"
    ATTACKER_SURRENDERED = "attacker_surrendered"
    DEFENDER_SURRENDERED = "defender_surrendered"
    DRAW = "draw"


@dataclass
class Combatant:
    """Участник боя."""
    id: int
    name: str
    is_human: bool
    attack: int = 50
    defense: int = 50
    stamina: float = 100
    max_stamina: float = 100
    health: int = 100
    max_health: int = 100
    species: str = "Human"
    weapon_damage: int = 20
    weapon_condition: int = 100
    armor_value: float = 1.0
    armor_condition: int = 100
    bravery: int = 50
    attentiveness: int = 50
    faction: str = ""
    ammo: int = 0
    medicines: int = 0
    attack_penalty: float = 1.0
    defense_penalty: float = 1.0
    is_alive: bool = True
    is_retreating: bool = False
    surrendered: bool = False
    unconscious: bool = False


class CombatFactory:
    """Создаёт Combatant из NPC/Monster."""

    @staticmethod
    def from_human(npc: HumanNPC) -> Combatant:
        return Combatant(
            id=npc.id,
            name=npc.name,
            is_human=True,
            attack=npc.attack,
            defense=npc.defense,
            stamina=npc.stamina,
            max_stamina=npc.max_stamina,
            health=npc.health,
            max_health=npc.max_health,
            bravery=npc.bravery,
            attentiveness=npc.attentiveness,
            faction=npc.faction,
            weapon_damage=getattr(npc, "weapon_damage", 20),
            weapon_condition=getattr(npc, "weapon_condition", 100),
            armor_value=getattr(npc, "armor_value", 1.0),
            armor_condition=getattr(npc, "armor_condition", 100),
            ammo=getattr(npc, "ammo", 0),
            medicines=getattr(npc, "medicines", 0),
        )

    @staticmethod
    def from_monster(monster: Monster) -> Combatant:
        species = monster.species.value if hasattr(monster.species, "value") else monster.species
        return Combatant(
            id=monster.id,
            name=str(species),
            is_human=False,
            attack=monster.attack,
            defense=monster.defense,
            stamina=monster.stamina,
            max_stamina=monster.max_stamina,
            health=monster.health,
            max_health=monster.max_health,
            species=species,
            weapon_damage=CombatBase.calculate_monster_base_damage(species),
            bravery=monster.bravery,
            attentiveness=monster.attentiveness,
        )


class CombatBase:
    """Базовая и групповая боевая сила. (§11.2)"""

    SPECIES_POWER = {
        "TerritorialPredator": 0.33,
        "ScavengerPack": 0.70,
        "LargeMigrator": 4.00,
    }

    @staticmethod
    def calculate_bp(
        attack: int = 50,
        health: int = 100,
        max_health: int = 100,
        stamina: float = 100,
        max_stamina: float = 100,
        is_human: bool = True,
        weapon_damage: int = 20,
        species: str = "Human",
    ) -> float:
        """
        Базовая боевая сила. (§11.2)
        Человек: BP = 1.0 × (0.5 + Attack/100) × Weapon × H × S
        Монстр: BP = SpeciesPower × (0.5 + Attack/100) × H × S
        """
        h = 0.35 + 0.65 * (health / max_health) if max_health > 0 else 0.35
        s = 0.50 + 0.50 * (stamina / max_stamina) if max_stamina > 0 else 0.50

        if is_human:
            weapon_factor = max(weapon_damage / 20.0, 0.25)  # 20 = стандарт, сломанное = 0.25
            return 1.0 * (0.5 + attack / 100.0) * weapon_factor * h * s
        else:
            sp = CombatBase.SPECIES_POWER.get(species, 0.33)
            return sp * (0.5 + attack / 100.0) * h * s

    @staticmethod
    def calculate_group_bp(combatants: list[Combatant]) -> float:
        """Групповая боевая сила. (§11.2)
        GBP = sum(BP) × (1 + 0.03 × (N - 1)), max 1.15.
        """
        total_bp = sum(c.attack * c.health / c.max_health for c in combatants if c.is_alive and not c.unconscious)
        n = len([c for c in combatants if c.is_alive and not c.unconscious])
        group_mult = min(1.0 + 0.03 * (n - 1), 1.15)
        return total_bp * group_mult

    @staticmethod
    def calculate_monster_base_damage(species: str) -> int:
        """Стартовый базовый урон монстров."""
        damage_map = {
            "TerritorialPredator": 15,
            "ScavengerPack": 10,
            "LargeMigrator": 30,
        }
        return damage_map.get(species, 20)


class CombatDefense:
    """Защитная сила. (§11.3)"""

    @staticmethod
    def calculate_dp(
        defense: int,
        armor: float = 1.0,
        health: int = 100,
        max_health: int = 100,
        stamina: float = 100,
        max_stamina: float = 100,
        situation_bonus: float = 1.0,
    ) -> float:
        """
        DP = (0.5 + Defense/100) × Armor × H × S × Situation.
        """
        h = 0.35 + 0.65 * (health / max_health) if max_health > 0 else 0.35
        s = 0.50 + 0.50 * (stamina / max_stamina) if max_stamina > 0 else 0.50
        return (0.5 + defense / 100.0) * armor * h * s * situation_bonus


class CombatRound:
    """Один раунд боя. (§11.4)"""

    def __init__(self, attacker: Combatant, defender: Combatant,
                 ambush_bonus: bool = False, shelter_bonus: float = 0.0,
                 retreating_penalty: float = 1.0):
        self.attacker = attacker
        self.defender = defender
        self.ambush_bonus = ambush_bonus
        self.shelter_bonus = shelter_bonus
        self.retreating_penalty = retreating_penalty

        self.atk_a: float = 0
        self.def_d: float = 0
        self.p_hit: float = 0
        self.damage: float = 0
        self.success: bool = False
        self.result: str = ""

    def resolve(self, rng_value: float) -> dict[str, Any]:
        """Выполняет атаку; callable даёт независимый бросок каждой проверке."""
        if callable(rng_value):
            rng_func = rng_value
        else:
            rng_func = lambda: rng_value

        atk_bp = self._calc_attack_bp(self.attacker)
        def_dp = CombatDefense.calculate_dp(
            defense=self.defender.defense,
            armor=self.defender.armor_value,
            health=self.defender.health,
            max_health=self.defender.max_health,
            stamina=self.defender.stamina,
            max_stamina=self.defender.max_stamina,
            situation_bonus=1.0 + self.shelter_bonus,
        ) * self.defender.defense_penalty

        attack_situation = 1.25 if self.ambush_bonus else 1.0
        if self.attacker.is_human and self.attacker.ammo <= 0:
            attack_situation *= 0.5
        self.atk_a = (
            atk_bp * (0.80 + 0.40 * rng_func()) * attack_situation
            * self.attacker.attack_penalty * self.retreating_penalty
        )
        self.def_d = def_dp * (0.80 + 0.40 * rng_func())

        denom = self.atk_a + self.def_d
        raw_p = 0.20 + 0.60 * (self.atk_a / denom) if denom > 0 else 0.20
        self.p_hit = max(0.10, min(raw_p, 0.90))
        self.success = rng_func() < self.p_hit

        if self.success:
            dmg_situ = 0.75 + 0.50 * (self.atk_a / denom) if denom > 0 else 0.75
            self.damage = round(
                self.attacker.weapon_damage * (0.85 + 0.30 * rng_func())
                * dmg_situ * 0.7
            )
            self.result = "hit"
        else:
            self.damage = 0
            self.result = "miss"

        return {
            "attacker_id": self.attacker.id,
            "defender_id": self.defender.id,
            "atk_a": round(self.atk_a, 2),
            "def_d": round(self.def_d, 2),
            "p_hit": round(self.p_hit, 3),
            "hit": self.success,
            "damage": self.damage,
        }

    def apply_damage(self) -> None:
        """Применяет урон к защитнику."""
        if self.success:
            self.defender.health -= self.damage
            if self.defender.health <= 0:
                self.defender.health = 0

    def _calc_attack_bp(self, combatant: Combatant) -> float:
        """Вычисляет BP атакующего. (§11.2)"""
        h = 0.35 + 0.65 * (combatant.health / combatant.max_health) if combatant.max_health > 0 else 0.35
        s = 0.50 + 0.50 * (combatant.stamina / combatant.max_stamina) if combatant.max_stamina > 0 else 0.50

        if combatant.is_human:
            weapon_factor = max(combatant.weapon_damage / 20.0, 0.25)
            condition_factor = max(0.25, combatant.weapon_condition / 100.0)
            return 1.0 * (0.5 + combatant.attack / 100.0) * weapon_factor * condition_factor * h * s
        else:
            sp = CombatBase.SPECIES_POWER.get(combatant.species, 0.33)
            return sp * (0.5 + combatant.attack / 100.0) * h * s


def select_targets(
    attacker_combatants: list[Combatant],
    defender_combatants: list[Combatant],
    is_monster: bool = False,
) -> list[tuple[Combatant, Combatant]]:
    """
    Выбор целей для атаки. (§11.5)
    Приоритеты: наибольшая угроза, раненый, носитель ценного имущества.
    """
    targets: list[tuple[Combatant, Combatant]] = []
    alive_defenders = [d for d in defender_combatants if d.is_alive and not d.unconscious and not d.surrendered]

    if is_monster:
        # Монстры приоритизируют: раненых, крупных, нанёсших урон
        alive_defenders.sort(key=lambda d: d.max_health / (d.health if d.health > 0 else 1), reverse=True)
    else:
        # Люди: наибольшую угрозу (высокая атака)
        alive_defenders.sort(key=lambda d: d.attack, reverse=True)

    active_attackers = [
        atk for atk in attacker_combatants
        if atk.is_alive and not atk.unconscious and not atk.surrendered and not atk.is_retreating
    ]
    for index, atk in enumerate(active_attackers):
        if alive_defenders:
            targets.append((atk, alive_defenders[index % len(alive_defenders)]))

    return targets


@dataclass
class BattleLog:
    """Журнал боя."""
    rounds: list[dict] = field(default_factory=list)
    result: str = ""
    survivors: list[int] = field(default_factory=list)
    casualties: list[int] = field(default_factory=list)
    retreating: list[int] = field(default_factory=list)
    surrendered: list[int] = field(default_factory=list)
    unconscious: list[int] = field(default_factory=list)
