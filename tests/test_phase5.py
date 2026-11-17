"""Тесты Фазы 5: аномалии и монстры (§12, §13 ТЗ)."""

import pytest

from zonesim.anomalies.artifact import ArtifactManager
from zonesim.anomalies.core import Anomaly, AnomalyStatus, AnomalyType
from zonesim.anomalies.damage import (
    apply_anomaly_damage,
    calculate_avoid_chance,
)
from zonesim.anomalies.destroy import (
    attempt_destroy_anomaly,
    calculate_destroy_damage,
    get_anomaly_parts_after_destruction,
)
from zonesim.anomalies.migration import (
    calculate_anomaly_move_timer,
    check_anomaly_migration,
)
from zonesim.anomalies.research import (
    calculate_research_success,
    research_sector_for_anomalies,
)
from zonesim.monsters.behavior import Monster, MonsterSpecies
from zonesim.monsters.feed import Corpse, FeedManager
from zonesim.monsters.hunt import (
    calculate_hunt_chance,
    calculate_stalk_success,
    decide_hunt_action,
    should_pursue,
)
from zonesim.monsters.migration import (
    MONSTER_MAX_GROUPS_PER_DAY,
    MONSTER_SOFT_MAX,
    MONSTER_SOFT_MIN,
    MonsterMigrationManager,
)

# ==================== Anomaly Core Tests ====================

class TestAnomalyCore:
    """Тесты базовых моделей аномалий."""

    def test_create_from_type_subtle(self):
        rng = type('obj', (object,), {'random': lambda self: 0.5, 'randint': lambda self, a, b: 72})()
        a = Anomaly.create_from_type(1, 5, AnomalyType.SUBTLE, rng)
        assert a.anomaly_type == AnomalyType.SUBTLE
        assert a.concealment == 70

    def test_create_from_type_large(self):
        rng = type('obj', (object,), {'random': lambda self: 0.5, 'randint': lambda self, a, b: 72})()
        a = Anomaly.create_from_type(1, 5, AnomalyType.LARGE, rng)
        assert a.anomaly_type == AnomalyType.LARGE
        assert a.concealment == 20
        assert a.stability == 140

    def test_to_dict(self):
        a = Anomaly(1, 5, AnomalyType.VISIBLE, stability=80, concealment=30)
        d = a.to_dict()
        assert d["id"] == 1
        assert d["status"] == "active"
        assert d["safe_path"] is False


# ==================== Anomaly Damage Tests ====================

class TestAnomalyDamage:
    """Тесты воздействия аномалий (§12.2)."""

    def test_avoid_chance_formula(self):
        """P_avoid = clamp(50 + 0.7×(Att - Concealment) + Known + Path, 5, 98)."""
        p = calculate_avoid_chance(
            attentiveness=70,
            anomaly_concealment=30,
            known_bonus=20,
        )
        # 50 + 0.7*(70-30) + 20 = 50 + 28 + 20 = 98
        assert p == pytest.approx(98.0, abs=0.1)

    def test_avoid_chance_night_bonus(self):
        """Ночью concealment снижается на 20 → легче избежать."""
        day_chance = calculate_avoid_chance(50, 70, is_night=False)
        night_chance = calculate_avoid_chance(50, 70, is_night=True)
        # night_chance = 50 + 0.7*(50-(70-20)) = 50 + 0.7*0 = 50
        # day_chance = 50 + 0.7*(50-70) = 50 - 14 = 36
        assert night_chance >= day_chance

    def test_avoid_chance_clamped(self):
        """Шанс в диапазоне [5, 98]."""
        high = calculate_avoid_chance(100, 1, is_night=False)
        assert 5 <= high <= 98

        low = calculate_avoid_chance(1, 100, is_night=False)
        assert 5 <= low <= 98

    def test_avoid_group_penalty(self):
        """Группа с меньшей эффективной внимательностью."""
        single = calculate_avoid_chance(60, 50, is_group=False)
        group = calculate_avoid_chance(60, 50, is_group=True, group_size=4)
        # group: effective_att = 60 - 3*2 = 54
        assert group <= single

    def test_apply_anomaly_damage(self):
        a = Anomaly(1, 5, AnomalyType.VISIBLE, stability=80, damage_min=20, damage_max=40)
        result = apply_anomaly_damage(100, 100, a, 0.5)
        assert result["damage"] > 0
        assert result["survived"] is True

    def test_anomaly_hit_critical(self):
        a = Anomaly(1, 5, AnomalyType.SUBTLE, damage_min=5, damage_max=12)
        result = apply_anomaly_damage(10, 100, a, 0.9)
        assert result["damage"] > 0
        # При 10 HP может умереть
        assert result["new_health"] >= 0


# ==================== Anomaly Research Tests ====================

class TestAnomalyResearch:
    """Тесты исследования аномалий (§12.3)."""

    def test_research_success_high_att(self):
        result = calculate_research_success(80, AnomalyType.SUBTLE, rng_value=0.1)
        assert result in ("safe_path_found", "artifact_found", "position_type_found")

    def test_research_failure_low_att(self):
        result = calculate_research_success(20, AnomalyType.VISIBLE, rng_value=0.8)
        assert result in ("damage_taken", "no_new_info")

    def test_research_prior_knowledge_helps(self):
        with_knowledge = calculate_research_success(50, AnomalyType.SUBTLE, prior_knowledge=True, rng_value=0.5)
        without_knowledge = calculate_research_success(50, AnomalyType.SUBTLE, prior_knowledge=False, rng_value=0.5)
        rank = {"safe_path_found": 4, "artifact_found": 4, "position_type_found": 3,
                "damage_taken": 2, "no_new_info": 0}
        assert rank.get(with_knowledge, 0) >= rank.get(without_knowledge, 0)

    def test_research_sector_discovery(self):
        from zonesim.anomalies.core import Anomaly
        a = Anomaly(1, 5, AnomalyType.SUBTLE, concealment=70)
        npc = type('obj', (object,), {'attentiveness': 80, 'sector_id': 5, 'id': 1})()
        findings = research_sector_for_anomalies(npc, [a], 10, rng_value=0.1)
        assert len(findings) > 0
        assert findings[0]["discovered"] is True

    def test_research_sector_miss(self):
        from zonesim.anomalies.core import Anomaly
        a = Anomaly(1, 5, AnomalyType.SUBTLE, concealment=70)
        npc = type('obj', (object,), {'attentiveness': 20, 'sector_id': 5, 'id': 1})()
        findings = research_sector_for_anomalies(npc, [a], 10, rng_value=0.9)
        assert len(findings) == 0


# ==================== Anomaly Destroy Tests ====================

class TestAnomalyDestroy:
    """Тесты разрушения аномалий (§12.4)."""

    def test_calculate_destroy_damage(self):
        damage = calculate_destroy_damage(35, 100, 1.0, 50, 1)
        assert damage >= 1

    def test_attempt_destroy_success(self):
        a = Anomaly(1, 5, AnomalyType.SUBTLE, stability=40)
        result = attempt_destroy_anomaly(a, 35, 100, 1.0, 50, 1)
        assert result["success"] is True
        assert result["damage_dealt"] > 0

    def test_destroy_anomaly_complete(self):
        a = Anomaly(1, 5, AnomalyType.SUBTLE, stability=5)
        result = attempt_destroy_anomaly(a, 35, 100, 1.0, 50, 1)
        assert result["destroyed"] is True
        assert a.status == AnomalyStatus.DESTROYED

    def test_destroy_already_destroyed(self):
        a = Anomaly(1, 5, AnomalyType.SUBTLE, stability=0)
        a.status = AnomalyStatus.DESTROYED
        result = attempt_destroy_anomaly(a, 35, 100, 1.0, 50, 1)
        assert result["success"] is False

    def test_get_anomaly_parts(self):
        a = Anomaly(1, 5, AnomalyType.VISIBLE, stability=0)
        a.status = AnomalyStatus.DESTROYED
        parts = get_anomaly_parts_after_destruction(a)
        assert parts["part_type"] == "visible_parts"
        assert parts["quantity"] == 2


# ==================== Anomaly Artifact Tests ====================

class TestArtifactManager:
    """Тесты формирования артефактов (§12.5)."""

    def test_check_artifact_formation(self):
        am = ArtifactManager()
        a = Anomaly(1, 5, AnomalyType.VISIBLE, artifact_timer=1)
        result = am.check_artifact_formation(a, 0, rng_value=0.1)
        assert result["formed"] is True
        assert result["rarity"] in ("common", "uncommon", "rare")

    def test_artifact_no_formation(self):
        am = ArtifactManager()
        a = Anomaly(1, 5, AnomalyType.VISIBLE, artifact_timer=100)
        result = am.check_artifact_formation(a, 0, rng_value=0.5)
        assert result["formed"] is False
        assert "timer_remaining" in result

    def test_inactive_anomaly_no_formation(self):
        am = ArtifactManager()
        a = Anomaly(1, 5, AnomalyType.VISIBLE, artifact_timer=1, status=AnomalyStatus.DESTROYED)
        result = am.check_artifact_formation(a, 0, rng_value=0.1)
        assert result["formed"] is False
        assert result["reason"] == "anomaly_inactive"

    def test_retrieve_artifact(self):
        am = ArtifactManager()
        a = Anomaly(1, 5, AnomalyType.VISIBLE, artifact_timer=1)
        am.check_artifact_formation(a, 0, rng_value=0.1)
        artifact = am.artifacts[0]

        result = am.retrieve_artifact(artifact.id, a)
        assert result["success"] is True
        assert artifact.discovered is True

    def test_retrieve_wrong_anomaly(self):
        am = ArtifactManager()
        a1 = Anomaly(1, 5, AnomalyType.VISIBLE, artifact_timer=1)
        a2 = Anomaly(2, 6, AnomalyType.LARGE, artifact_timer=1)
        am.check_artifact_formation(a1, 0, rng_value=0.1)
        artifact = am.artifacts[0]

        result = am.retrieve_artifact(artifact.id, a2)
        assert result["success"] is False


# ==================== Anomaly Migration Tests ====================

class TestAnomalyMigration:
    """Тесты перемещения аномалий (§12.6)."""

    def test_migration_check(self):
        a = Anomaly(1, 5, AnomalyType.VISIBLE, move_timer=48)
        result = check_anomaly_migration(
            a, 100, move_interval=48, move_chance=0.25,
            sector_ids=[10, 11, 12],
            faction_start_ids={0, 1, 2},
            rng_value=0.1,
        )
        assert result["moved"] is True

    def test_migration_no_chance(self):
        a = Anomaly(1, 5, AnomalyType.VISIBLE, move_timer=48)
        result = check_anomaly_migration(
            a, 100, move_interval=48, move_chance=0.25,
            sector_ids=[10, 11],
            faction_start_ids={0},
            rng_value=0.9,
        )
        assert result["moved"] is False
        assert result.get("rng_failed") is True

    def test_migration_inactive(self):
        a = Anomaly(1, 5, AnomalyType.VISIBLE, status=AnomalyStatus.DESTROYED)
        result = check_anomaly_migration(a, 100, rng_value=0.1)
        assert result["moved"] is False

    def test_calculate_move_timer(self):
        a = Anomaly(1, 5, AnomalyType.VISIBLE, move_timer=24)
        timer = calculate_anomaly_move_timer(a)
        assert timer == 24  # 48 - 24

    def test_destroyed_anomaly_timer(self):
        a = Anomaly(1, 5, AnomalyType.VISIBLE, status=AnomalyStatus.DESTROYED)
        timer = calculate_anomaly_move_timer(a)
        assert timer == 0


# ==================== Monster Behavior Tests ====================

class TestMonsterBehavior:
    """Тесты моделей монстров (§13)."""

    def test_create_from_species(self):
        m = Monster.create_from_species(1, MonsterSpecies.TERRITORIAL_PREDATOR, 5, type('obj', (object,), {'random': lambda: 0.5})())
        assert m.species == MonsterSpecies.TERRITORIAL_PREDATOR
        assert m.base_attack if hasattr(m, 'base_attack') else m.attack == 50

    def test_species_params(self):
        m = Monster(1, MonsterSpecies.LARGE_MIGRATOR, 5)
        params = m.species_params
        assert params["species_power"] == 4.00
        assert params["max_group_size"] == 2

    def test_health_share(self):
        m = Monster(1, MonsterSpecies.TERRITORIAL_PREDATOR, 5, health=50, max_health=100)
        assert m.health_share == 0.5

    def test_to_dict(self):
        m = Monster(1, MonsterSpecies.SCAVENGER_PACK, 5)
        d = m.to_dict()
        assert d["id"] == 1
        assert d["status"] == "active"


# ==================== Monster Hunt Tests ====================

class TestMonsterHunt:
    """Тесты охоты монстров (§13.2-13.4)."""

    def test_hunt_chance_healthy_prey(self):
        m = Monster(1, MonsterSpecies.TERRITORIAL_PREDATOR, 5)
        chance = calculate_hunt_chance(m, 0.9, False, 0)
        assert chance < 50  # здоровая цель — низкий шанс

    def test_hunt_chance_weak_prey(self):
        m = Monster(1, MonsterSpecies.TERRITORIAL_PREDATOR, 5)
        chance = calculate_hunt_chance(m, 0.2, False, 0)
        assert chance > 50  # раненая цель — высокий шанс

    def test_hunt_night_bonus(self):
        m = Monster(1, MonsterSpecies.TERRITORIAL_PREDATOR, 5)
        day = calculate_hunt_chance(m, 0.5, False, 0, is_night=False)
        night = calculate_hunt_chance(m, 0.5, False, 0, is_night=True)
        assert night >= day

    def test_decide_hunt_no_targets(self):
        m = Monster(1, MonsterSpecies.TERRITORIAL_PREDATOR, 5)
        result = decide_hunt_action(m, [], 0.5)
        assert result["should_hunt"] is False

    def test_decide_hunt_with_targets(self):
        prey = type('obj', (object,), {'id': 1, 'health_share': 0.3})()
        m = Monster(1, MonsterSpecies.TERRITORIAL_PREDATOR, 5)
        result = decide_hunt_action(m, [prey], 0.1)
        assert result["should_hunt"] is True

    def test_stalk_success_decreases(self):
        chance_0 = calculate_stalk_success(type('obj', (object,), {'species': MonsterSpecies.SCAVENGER_PACK})(), 50, 0)
        chance_5 = calculate_stalk_success(type('obj', (object,), {'species': MonsterSpecies.SCAVENGER_PACK})(), 50, 5)
        assert chance_0 > chance_5

    def test_pursue_large_migrator(self):
        m = Monster(1, MonsterSpecies.LARGE_MIGRATOR, 5)
        # should_pursue возвращает True если цель нанёсла урон < 24 часов назад
        result = should_pursue(m, target_damaged_by=True, hours_since_damage=5)
        assert result is True

        result = should_pursue(m, target_damaged_by=True, hours_since_damage=30)
        assert result is False


# ==================== Monster Feed Tests ====================

class TestMonsterFeed:
    """Тесты поедания трупов (§13.5)."""

    def test_process_feeding(self):
        fm = FeedManager()
        monster = Monster(1, MonsterSpecies.SCAVENGER_PACK, 5)
        corpse = Corpse(1, 10, "human", 5, created_hour=10)
        corpses = [corpse]

        results = fm.process_feeding([monster], corpses, 20, rng_values=[0.1])
        assert len(results) > 0
        assert corpse.status == "consumed"

    def test_feeding_no_corpses(self):
        fm = FeedManager()
        monster = Monster(1, MonsterSpecies.SCAVENGER_PACK, 5)
        results = fm.process_feeding([monster], [], 20, rng_values=[0.1])
        assert len(results) == 0

    def test_can_consume_available(self):
        fm = FeedManager()
        corpse = Corpse(1, 10, "monster", 5, status="available")
        assert fm.can_consume("scavenger_pack", corpse) is True

    def test_can_consume_consumed(self):
        fm = FeedManager()
        corpse = Corpse(1, 10, "monster", 5, status="consumed")
        assert fm.can_consume("scavenger_pack", corpse) is False

    def test_consumption_reward(self):
        fm = FeedManager()
        corpse = Corpse(1, 10, "monster", 5, monster_parts=[{"name": "tooth"}])
        reward = fm.get_consumption_reward(corpse)
        assert reward["corpse_destroyed"] is True
        assert reward["items_corrupted"] == 1


# ==================== Monster Migration Tests ====================

class TestMonsterMigration:
    """Тесты миграции монстров (§13.6)."""

    def test_spawn_below_minimum(self):
        mm = MonsterMigrationManager()
        new_monsters = mm.check_and_spawn(
            active_monster_count=10,
            border_sectors=[10, 11, 12],
            faction_start_ids={0, 1, 2},
            hour=24,
            rng=type('obj', (object,), {
                'choice': lambda self, lst: lst[0],
                'randint': lambda self, a, b: 10000,
            })(),
        )
        assert len(new_monsters) > 0
        assert new_monsters[0].status.value == "Активен"
        assert mm.groups_today == 1

    def test_spawn_above_minimum(self):
        mm = MonsterMigrationManager()
        new_monsters = mm.check_and_spawn(
            active_monster_count=MONSTER_SOFT_MIN + 5,
            border_sectors=[10, 11],
            faction_start_ids={0},
            hour=48,
            rng=type('obj', (object,), {
                'choice': lambda self, lst: lst[0],
                'randint': lambda self, a, b: 10000,
            })(),
        )
        assert len(new_monsters) == 0

    def test_population_status(self):
        mm = MonsterMigrationManager()
        below = mm.get_population_status(MONSTER_SOFT_MIN - 5)
        assert below["status"] == "below_minimum"
        assert below["migration_enabled"] is True

        normal = mm.get_population_status(30)
        assert normal["status"] == "normal"

        above = mm.get_population_status(MONSTER_SOFT_MAX + 5)
        assert above["status"] == "above_maximum"

    def test_daily_group_limit(self):
        mm = MonsterMigrationManager()
        # Устанавливаем groups_today на лимит и last_day чтобы сброс не happened
        mm.groups_today = MONSTER_MAX_GROUPS_PER_DAY
        mm.last_day = 1  # hour=25 → day=1, last_day=1, сброс не произойдёт
        # Проверяем что лимит работает
        assert mm.groups_today == 3
        new_monsters = mm.check_and_spawn(
            active_monster_count=5,
            border_sectors=[10],
            faction_start_ids=set(),
            hour=25,  # day=1, same as last_day
            rng=type('obj', (object,), {
                'choice': lambda self, lst: lst[0],
                'randint': lambda self, a, b: 10000,
            })(),
        )
        assert len(new_monsters) == 0
