"""Охота монстров. Основано на §13.2-13.4 ТЗ."""

from __future__ import annotations

from zonesim.monsters.behavior import Monster, MonsterSpecies


def calculate_hunt_chance(
    predator: Monster,
    prey_health_share: float,
    prey_is_monster: bool,
    distance: int,
    is_night: bool = False,
    group_advantage: int = 0,
) -> float:
    """
    Шанс успешной охоты.
    Приоритеты по виду:
    -Territorial: раненые, численное преимущество, внезапность
    - Scavenger: засады, преследование раненых
    - Large: сильные цели, запоминание уронителя
    """
    base_chance = 30.0

    # Раненая цель — высокий приоритет
    if prey_health_share < 0.3:
        base_chance += 20
    elif prey_health_share < 0.6:
        base_chance += 10

    # Численное преимущество
    base_chance += group_advantage * 5

    # Дальность
    if distance == 0:
        base_chance += 15  # в одном секторе
    elif distance == 1:
        base_chance += 5

    species = predator.species.value if hasattr(predator.species, "value") else predator.species

    # Ночью — территориальные хищники лучше охотятся
    if is_night and species in (MonsterSpecies.TERRITORIAL_PREDATOR, "TerritorialPredator"):
        base_chance += 10

    # Крупные мигранты менее внимательны
    if species in (MonsterSpecies.LARGE_MIGRATOR, "LargeMigrator"):
        base_chance -= 10

    # Падьальщики избегают здоровых целей
    if species in (MonsterSpecies.SCAVENGER_PACK, "ScavengerPack") and not prey_is_monster:
        if prey_health_share > 0.7:
            base_chance -= 15

    return max(5.0, min(base_chance, 90.0))


def decide_hunt_action(
    monster: Monster,
    targets_in_sector: list,
    rng_value: float,
) -> dict:
    """
    Решает, будет ли монстр охотиться на цель в секторе.
    Возвращает: should_hunt, target_id, hunt_chance.
    """
    if not targets_in_sector:
        return {"should_hunt": False, "reason": "no_targets"}

    # Наилучшая цель — наиболее уязвимая
    best_target = max(
        targets_in_sector,
        key=lambda t: getattr(t, "health_share", 0.5),
    )
    prey_health_share = getattr(best_target, "health_share", 0.5)
    prey_is_monster = isinstance(best_target, Monster)

    # Проверка видовых приоритетов
    if monster.species == MonsterSpecies.TERRITORIAL_PREDATOR:
        # Предпочитает раненых
        if prey_health_share > 0.8 and not prey_is_monster:
            return {"should_hunt": False, "reason": "prey_too_healthy"}

    elif monster.species == MonsterSpecies.SCAVENGER_PACK:
        # Предпочитает слабые цели
        if prey_health_share > 0.6 and not prey_is_monster:
            return {"should_hunt": False, "reason": "prey_too_strong"}

    hunt_chance = calculate_hunt_chance(
        predator=monster,
        prey_health_share=prey_health_share,
        prey_is_monster=prey_is_monster,
        distance=0,
    )

    if rng_value * 100 < hunt_chance:
        return {
            "should_hunt": True,
            "target_id": best_target.id,
            "hunt_chance": hunt_chance,
        }

    return {"should_hunt": False, "hunt_chance": hunt_chance}


def calculate_stalk_success(
    predator: Monster,
    prey_attentiveness: int,
    hours_pursuing: int,
    max_pursuit_hours: int = 12,
) -> float:
    """
    Шанс успешного преследования следа.
    Падьальщики преследуют стартово до 12 часов.
    Крупные мигранты — до 24 часов.
    """
    if hours_pursuing >= max_pursuit_hours:
        return 0.0

    # Базовый шанс уменьшается со временем
    base_chance = 50 - hours_pursuing * 3

    # Внимательность жертвы снижает шанс
    base_chance -= (prey_attentiveness - 50) * 0.5

    return max(5.0, min(base_chance, 80.0))


def should_pursue(
    monster: Monster,
    target_damaged_by: bool,
    hours_since_damage: int,
    memory_hours: int = 24,
) -> bool:
    """
    Решает, преследовать ли существо, нанёсшее урон.
    Крупные мигранты запоминают на 24 часа.
    """
    if monster.species != MonsterSpecies.LARGE_MIGRATOR:
        return False

    if not target_damaged_by:
        return False

    if hours_since_damage >= memory_hours:
        return False

    # Шанс преследования снижается со временем
    persistence_chance = max(0, 100 - hours_since_damage * (100 / memory_hours))
    return True  # placeholder — caller должен бросить rng
