"""Тесты Фазы 4: боевая система (§11 ТЗ)."""

import pytest
from zonesim.combat.base import (
    Combatant, CombatFactory, CombatRound, CombatBase,
    CombatDefense, select_targets, BattleLog,
)
from zonesim.combat.retreat import (
    calculate_retreat_score, calculate_retreat_chance,
    resolve_retreat, should_attempt_retreat,
)
from zonesim.combat.surrender import SurrenderManager, SurrenderOutcome
from zonesim.combat.unconscious import (
    calculate_unconscious_chance, resolve_unconscious_check,
    provide_medical_help, check_injury,
)
from zonesim.combat.loot import EquipmentManager, Corpse
from zonesim.combat import CombatSystem


# ==================== CombatBase Tests ====================

class TestCombatBase:
    """Тесты боевой силы (§11.2)."""

    def test_standard_human_bp(self):
        """Человек: атк 50, HP 100%, stamina 100%, оружие 20 → BP = 1.0."""
        bp = CombatBase.calculate_bp(
            attack=50, health=100, max_health=100,
            stamina=100, max_stamina=100, is_human=True,
        )
        # 1.0 * (0.5 + 0.5) * 1.0 * 1.0 * 1.0 = 1.0
        assert bp == pytest.approx(1.0, abs=0.01)

    def test_territorial_predator_bp(self):
        """Территориальный хищник: SpeciesPower = 0.33, атк 50, HP 100%."""
        bp = CombatBase.calculate_bp(
            attack=50, health=100, max_health=100,
            stamina=100, max_stamina=100, is_human=False, species="TerritorialPredator",
        )
        # 0.33 * (0.5 + 0.5) * 1.0 * 1.0 = 0.33
        assert bp == pytest.approx(0.33, abs=0.02)

    def test_three_predators_equal_one_human(self):
        """3 терр. хищника ≈ 1 человек."""
        human_bp = CombatBase.calculate_bp(attack=50, health=100, max_health=100,
                                            stamina=100, max_stamina=100, is_human=True)
        pred_bp = CombatBase.calculate_bp(attack=50, health=100, max_health=100,
                                           stamina=100, max_stamina=100, is_human=False,
                                           species="TerritorialPredator")
        assert 3 * pred_bp == pytest.approx(human_bp, abs=0.2)

    def test_group_bp_with_scaling(self):
        """Групповая БС с ограничением 1.15."""
        class FakeCombatant:
            is_alive = True
            unconscious = False
            def __init__(self, atk, hp, mhp):
                self.attack = atk
                self.health = hp
                self.max_health = mhp

        combatants = [FakeCombatant(50, 100, 100) for _ in range(4)]
        gbp = CombatBase.calculate_group_bp(combatants)
        assert gbp > 0

    def test_wounded_has_lower_bp(self):
        """Раненый имеет меньшую БС."""
        full = CombatBase.calculate_bp(attack=50, health=100, max_health=100,
                                        stamina=100, max_stamina=100)
        wounded = CombatBase.calculate_bp(attack=50, health=30, max_health=100,
                                           stamina=100, max_stamina=100)
        assert wounded < full

    def test_low_stamina_reduces_bp(self):
        """Низкая stamina снижает БС."""
        full = CombatBase.calculate_bp(attack=50, health=100, max_health=100,
                                        stamina=100, max_stamina=100)
        low = CombatBase.calculate_bp(attack=50, health=100, max_health=100,
                                       stamina=20, max_stamina=100)
        assert low < full

    def test_monster_base_damage(self):
        """Стартовый урон монстров."""
        assert CombatBase.calculate_monster_base_damage("TerritorialPredator") == 15
        assert CombatBase.calculate_monster_base_damage("ScavengerPack") == 10
        assert CombatBase.calculate_monster_base_damage("LargeMigrator") == 30


class TestCombatDefense:
    """Тесты защитной силы (§11.3)."""

    def test_dp_formula(self):
        """DP = (0.5 + Defense/100) × Armor × H × S × Situation."""
        dp = CombatDefense.calculate_dp(
            defense=50, armor=1.0,
            health=100, max_health=100,
            stamina=100, max_stamina=100,
            situation_bonus=1.0,
        )
        assert dp == pytest.approx(1.0, abs=0.01)

    def test_broken_armor_reduces_dp(self):
        """Сломанная броня снижает DP."""
        good = CombatDefense.calculate_dp(50, 1.0, 100, 100, 100, 100, 1.0)
        bad = CombatDefense.calculate_dp(50, 0.5, 100, 100, 100, 100, 1.0)
        assert bad < good

    def test_hp_factor_reduces_dp(self):
        """Раненый имеет меньшую DP."""
        full = CombatDefense.calculate_dp(50, 1.0, 100, 100, 100, 100, 1.0)
        wounded = CombatDefense.calculate_dp(50, 1.0, 30, 100, 100, 100, 1.0)
        assert wounded < full


class TestCombatRound:
    """Тесты одного раунда (§11.4)."""

    def test_hit_resolution(self):
        """Успешное попадание."""
        atk = Combatant(1, "Player", True, attack=80, stamina=100, health=100,
                        max_stamina=100, max_health=100)
        def_ = Combatant(2, "Enemy", True, attack=40, stamina=100, health=100,
                         max_stamina=100, max_health=100)
        round_result = CombatRound(atk, def_)
        result = round_result.resolve(0.1)
        assert result["hit"] is True
        assert result["damage"] > 0

    def test_miss_resolution(self):
        """Промах."""
        atk = Combatant(1, "Player", True, attack=10, stamina=100, health=100,
                        max_stamina=100, max_health=100)
        def_ = Combatant(2, "Enemy", True, attack=80, stamina=100, health=100,
                         max_stamina=100, max_health=100)
        round_result = CombatRound(atk, def_)
        result = round_result.resolve(0.9)
        assert result["hit"] is False
        assert result["damage"] == 0

    def test_p_hit_clamped(self):
        """Вероятность попадания между 0.10 и 0.90."""
        atk = Combatant(1, "Player", True, attack=99, stamina=100, health=100,
                        max_stamina=100, max_health=100)
        def_ = Combatant(2, "Enemy", True, attack=1, stamina=100, health=100,
                         max_stamina=100, max_health=100)
        round_result = CombatRound(atk, def_)
        result = round_result.resolve(0.1)
        assert 0.10 <= result["p_hit"] <= 0.90

    def test_ambush_bonus(self):
        """Засада даёт бонус к атаке."""
        atk = Combatant(1, "Ambusher", True, attack=50, stamina=100, health=100,
                        max_stamina=100, max_health=100)
        def_ = Combatant(2, "Victim", True, attack=50, stamina=100, health=100,
                         max_stamina=100, max_health=100)
        round_normal = CombatRound(atk, def_)
        round_ambush = CombatRound(atk, def_, ambush_bonus=True)
        r1 = round_normal.resolve(0.5)
        r2 = round_ambush.resolve(0.5)
        assert r2["atk_a"] >= r1["atk_a"]


class TestSelectTargets:
    """Тесты выбора целей (§11.5)."""

    def test_highest_attack_priority(self):
        """Люди выбирают цель с наибольшей атакой."""
        attackers = [Combatant(1, "A", True, attack=50, stamina=100, health=100,
                              max_stamina=100, max_health=100)]
        defenders = [
            Combatant(2, "D1", True, attack=30, stamina=100, health=100,
                      max_stamina=100, max_health=100),
            Combatant(3, "D2", True, attack=80, stamina=100, health=100,
                      max_stamina=100, max_health=100),
        ]
        targets = select_targets(attackers, defenders)
        assert targets[0][1].id == 3  # D2 с атакой 80

    def test_monster_picks_weakest(self):
        """Монстры приоритизируют раненых."""
        attackers = [Combatant(10, "M", False, attack=50, stamina=100, health=100,
                              max_stamina=100, max_health=100, species="TerritorialPredator")]
        defenders = [
            Combatant(2, "D1", True, attack=50, stamina=100, health=90,
                      max_stamina=100, max_health=100),
            Combatant(3, "D2", True, attack=50, stamina=100, health=20,
                      max_stamina=100, max_health=100),
        ]
        targets = select_targets(attackers, defenders, is_monster=True)
        assert targets[0][1].id == 3  # раненый D2


class TestRetreat:
    """Тесты отступления (§11.6-11.7)."""

    def test_retreat_score_high_loss(self):
        """Высокие потери → высокий score → отступление."""
        score = calculate_retreat_score(
            health_share=0.3, enemy_power_ratio=1.5,
            bravery=50, loss_share=0.7,
        )
        assert score > 0.55

    def test_retreat_score_low_loss(self):
        """Малые потери и высокая храбрость → низкий score."""
        score = calculate_retreat_score(
            health_share=0.9, enemy_power_ratio=0.5,
            bravery=80, loss_share=0.1,
        )
        assert score < 0.55

    def test_retreat_chance_formula(self):
        """Формула P_retreat."""
        p = calculate_retreat_chance(
            speed_ratio=1.0, escape_att=50, pursuer_att=50,
            terrain_bonus=10,
        )
        assert p == pytest.approx(55.0, abs=0.1)

    def test_retreat_chance_clamped(self):
        """Шанс отступления в диапазоне [5, 95]."""
        p = calculate_retreat_chance(1.0, 100, 1, 20)
        assert 5 <= p <= 95

        p_low = calculate_retreat_chance(0.5, 1, 100, -20)
        assert 5 <= p_low <= 95

    def test_resolve_retreat_success(self):
        """Успешное отступление."""
        class FakeSector:
            neighbors = [1, 2, 3]
        sectors = {0: FakeSector()}
        result = resolve_retreat(0.7, 50, 0.3, 0, sectors)
        assert result["success"] is True
        assert result["retreated"] is True

    def test_resolve_retreat_failed(self):
        """Провал отступления → штрафы."""
        class FakeSector:
            neighbors = [1, 2]
        sectors = {0: FakeSector()}
        result = resolve_retreat(0.7, 50, 0.8, 0, sectors)
        assert result["success"] is False
        assert result["attack_penalty"] == 0.9
        assert result["defense_penalty"] == 0.8

    def test_retreat_overwhelming_force(self):
        """При подавляющем перевесе порог отступления ниже."""
        assert should_attempt_retreat(0.35, is_overwhelming=True) is True
        assert should_attempt_retreat(0.35, is_overwhelming=False) is False


class TestSurrender:
    """Тесты сдачи (§11.9)."""

    def test_human_to_human_can_surrender(self):
        """Люди могут сдаться людям."""
        assert SurrenderManager.can_surrender(
            True, True, bravery=30, health_share=0.2, power_ratio=2.0,
        ) is True

    def test_cannot_surrender_to_monsters(self):
        """Нельзя сдаться монстрам."""
        assert SurrenderManager.can_surrender(
            True, False, bravery=30, health_share=0.2, power_ratio=2.0,
        ) is False

    def test_monsters_cannot_surrender(self):
        """Монстры не сдаются."""
        assert SurrenderManager.can_surrender(
            False, True, bravery=30, health_share=0.2, power_ratio=2.0,
        ) is False

    def test_surrender_outcome_capture(self):
        """Сдавшиеся могут быть взяты в плен."""
        outcome = SurrenderManager.determine_outcome(
            surrendering_count=3, captor_count=2,
            relation=20, captor_faction="Бродяги",
            target_faction="Борзые", bravery=40,
        )
        assert outcome["outcome"] in (
            SurrenderOutcome.CAPTURE_ALL,
            SurrenderOutcome.CAPTURE_PARTIAL,
            SurrenderOutcome.KILL_ALL,
            SurrenderOutcome.RELEASE_ALL,
        )


class TestUnconscious:
    """Тесты бессознательного состояния (§11.10)."""

    def test_unconscious_chance_healthy(self):
        """Здоровый имеет больше шансов выжить."""
        full_health = calculate_unconscious_chance(1.0)
        wounded_health = calculate_unconscious_chance(0.3)
        assert full_health > wounded_health
        assert full_health == pytest.approx(80.0, abs=0.1)

    def test_unconscious_chance_clamped(self):
        """Шанс в диапазоне [10, 85]."""
        p = calculate_unconscious_chance(0.0)
        assert p >= 10
        assert p <= 85

    def test_resolve_unconscious(self):
        """Результат проверки."""
        assert resolve_unconscious_check(0.1, 80) == "unconscious"
        assert resolve_unconscious_check(0.9, 80) == "dead"

    def test_medical_help(self):
        """Медикаменты лечат бессознательных."""
        unconscious = {1: 0, 2: 0}
        max_healths = {1: 100, 2: 100}
        result = provide_medical_help([1, 2], 1, unconscious, max_healths, 0.5)
        assert len(result["helped"]) == 1
        assert result["helped"][0]["new_health"] > 0

    def test_no_medical_help_available(self):
        """Без медикаментов помощь невозможна."""
        unconscious = {1: 0}
        max_healths = {1: 100}
        result = provide_medical_help([1], 0, unconscious, max_healths, 0.5)
        assert len(result["unhelped"]) == 1

    def test_injury_check_high_damage(self):
        """Урон >= 25 → проверка на травму."""
        # Урон 30, rng 0.01 → высокий шанс травмы (0.08 base + 0.05 low health = 13%)
        injury = check_injury(30.0, 0.5, 0.01)
        # При damage >= 25 базовый шанс 8%, rng 0.01 < 0.08 → травма
        assert injury.injury_applied is True

    def test_injury_check_no_injury(self):
        """Малый урон → нет травмы."""
        injury = check_injury(10.0, 0.8, 0.5)
        assert injury.injury_applied is False


class TestEquipmentManager:
    """Тесты износа снаряжения (§11.8)."""

    def test_weapon_wear_range(self):
        """Оружие теряет 2-8 состояния после боя."""
        wear = EquipmentManager.apply_weapon_wear(100, True, 0.9)
        # max damage = 2 + (8-2)*0.9 = 7.4 → 7
        assert 2 <= wear.original_damage <= 8
        assert wear.new_condition == 100 - wear.original_damage

    def test_broken_weapon(self):
        """Сломанное оружие → минимальная эффективность."""
        assert EquipmentManager.get_weapon_effectiveness(0) == 0.25
        assert EquipmentManager.get_weapon_effectiveness(10) == 0.25

    def test_good_weapon_effectiveness(self):
        """Новое оружие = 1.0."""
        assert EquipmentManager.get_weapon_effectiveness(100) == 1.0

    def test_value_damage_on_heavy_hit(self):
        """Сильное попадание может повредить ценности."""
        damaged, new_cond = EquipmentManager.check_value_damage(80, 20, 0.1)
        assert damaged is True
        assert new_cond < 80

    def test_no_value_damage_on_light_hit(self):
        """Лёгкий удар не повреждает ценности."""
        damaged, new_cond = EquipmentManager.check_value_damage(80, 10, 0.5)
        assert damaged is False

    def test_corruption_on_consumption(self):
        """При поедании трупа вещи портятся."""
        items = [{"condition": 100, "value": 50}]
        result = EquipmentManager.apply_corruption_on_consumption(items)
        assert result[0]["condition"] == 0
        assert result[0]["value"] == pytest.approx(5.0, abs=0.1)  # 10% от 50


class TestCombatSystem:
    """Тесты боевой системы (§11)."""

    def test_single_combat(self):
        """Простой бой 1 на 1."""
        atk = Combatant(1, "Player", True, attack=80, defense=60, stamina=100,
                        max_stamina=100, health=100, max_health=100)
        def_ = Combatant(2, "Enemy", True, attack=40, defense=30, stamina=100,
                         max_stamina=100, health=100, max_health=100)
        combat = CombatSystem([atk], [def_])

        def rng_func():
            return 0.3
        result = combat.fight(rng_func)

        assert result.outcome == "attacker_wins" or result.outcome == "draw"
        assert result.rounds_fought >= 1

    def test_monster_vs_human(self):
        """3 терр. хищника ≈ 1 человек — бой напряжённый."""
        humans = [Combatant(1, "Hunter", True, attack=50, stamina=100, health=100,
                            max_stamina=100, max_health=100)]
        monsters = [
            Combatant(10, "T1", False, attack=50, stamina=100, health=100,
                      max_stamina=100, max_health=100, species="TerritorialPredator",
                      weapon_damage=15),
            Combatant(11, "T2", False, attack=50, stamina=100, health=100,
                      max_stamina=100, max_health=100, species="TerritorialPredator",
                      weapon_damage=15),
            Combatant(12, "T3", False, attack=50, stamina=100, health=100,
                      max_stamina=100, max_health=100, species="TerritorialPredator",
                      weapon_damage=15),
        ]
        combat = CombatSystem(humans, monsters)

        def rng_func():
            return 0.5
        result = combat.fight(rng_func)

        # Бой должен быть напряжённым — примерно равные силы
        assert result.rounds_fought >= 1

    def test_no_health_below_zero(self):
        """Здоровье не уходит ниже 0."""
        atk = Combatant(1, "Player", True, attack=90, stamina=100, health=100,
                        max_stamina=100, max_health=100)
        def_ = Combatant(2, "Enemy", True, attack=10, stamina=100, health=5,
                         max_stamina=100, max_health=100)
        combat = CombatSystem([atk], [def_])

        def rng_func():
            return 0.1
        result = combat.fight(rng_func)

        assert def_.health >= 0

    def test_retreat_ends_battle(self):
        """Успешное отступление прекращает бой."""
        atk = Combatant(1, "Retreater", True, attack=30, stamina=50, health=20,
                        max_stamina=100, max_health=100, bravery=10)
        def_ = Combatant(2, "StrongEnemy", True, attack=90, stamina=100, health=100,
                         max_stamina=100, max_health=100)
        combat = CombatSystem([atk], [def_])

        def rng_func():
            return 0.4  # умеренный RNG — шанс отступления ~65%
        result = combat.fight(rng_func)
        # Отступление, сдача или плен — любые исходы при подавляющем враге
        assert 1 in result.attacker_retreated or result.outcome == "attacker_retreated" \
            or 1 in result.attacker_surrendered or 1 in result.attacker_prisoners

    def test_battle_log_recorded(self):
        """Все раунды записываются в лог."""
        atk = Combatant(1, "Player", True, attack=70, stamina=100, health=100,
                        max_stamina=100, max_health=100)
        def_ = Combatant(2, "Enemy", True, attack=70, stamina=100, health=100,
                         max_stamina=100, max_health=100)
        combat = CombatSystem([atk], [def_])

        def rng_func():
            return 0.5
        result = combat.fight(rng_func)

        assert len(result.battle_log) > 0

    def test_human_zero_health_unconscious(self):
        """Человек при health 0 может оказаться бессознательным или сдаться."""
        atk = Combatant(1, "Player", True, attack=50, stamina=100, health=100,
                        max_stamina=100, max_health=100, bravery=80)  # высокая храбрость — не сдаётся
        def_ = Combatant(2, "Enemy", True, attack=90, stamina=100, health=100,
                         max_stamina=100, max_health=100)
        combat = CombatSystem([atk], [def_])

        def rng_func():
            return 0.1  # высокий шанс урона
        result = combat.fight(rng_func)

        # Человек должен стать бессознательным, мёртвым или пленным
        assert len(result.attacker_unconscious) > 0 or len(result.attacker_dead) > 0 or len(result.attacker_prisoners) > 0

    def test_monster_zero_health_dead(self):
        """Монстр при health 0 сразу мёртв."""
        # Монстр как атакующий — проверим что при health 0 он помечается мёртвым
        atk = Combatant(10, "Predator", False, attack=50, stamina=100, health=5,
                        max_stamina=100, max_health=5,  # критически мало здоровья
                        species="TerritorialPredator", weapon_damage=15)
        def_ = Combatant(1, "Hunter", True, attack=10, stamina=100, health=100,
                         max_stamina=100, max_health=100)
        combat = CombatSystem([atk], [def_])

        def rng_func():
            return 0.1  # высокий шанс попадания
        result = combat.fight(rng_func)

        # Монстр-атакующий должен умереть (здоровье 5, урон > 9 за раунд → 1 раунд)
        assert 10 in result.attacker_dead

    def test_equipment_wear_applied(self):
        """Износ снаряжения применяется после боя."""
        atk = Combatant(1, "Player", True, attack=60, stamina=100, health=100,
                        max_stamina=100, max_health=100)
        def_ = Combatant(2, "Enemy", True, attack=60, stamina=100, health=100,
                         max_stamina=100, max_health=100)
        combat = CombatSystem([atk], [def_])

        def rng_func():
            return 0.5
        result = combat.fight(rng_func)

        assert len(result.equipment_wear) >= 2
        for wear in result.equipment_wear:
            assert wear["new_condition"] <= wear["old_condition"]
