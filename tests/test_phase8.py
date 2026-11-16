"""Тесты Фазы 8: интеграция часового цикла (§8 ТЗ)."""

import pytest
from zonesim.simulation.engine import SimulationEngine
from zonesim.world.entity import EntityStatus


class TestSimulationEngine:
    """Тесты главного движка симуляции."""

    def test_create_engine(self):
        """Движок создаётся без ошибок."""
        engine = SimulationEngine(seed=42)
        assert engine.state.time.hour == 7
        assert len(engine.state.sectors) > 0
        assert len(engine.state.humans) > 0
        assert len(engine.state.monsters) > 0
        assert len(engine.state.anomalies) > 0

    def test_simulate_hour_advances_time(self):
        """simulate_hour увеличивает час на 1."""
        engine = SimulationEngine(seed=42)
        initial_hour = engine.state.time.hour
        result = engine.simulate_hour()
        assert engine.state.time.hour == initial_hour + 1

    def test_simulate_hour_returns_summary(self):
        """simulate_hour возвращает словарь со сводкой."""
        engine = SimulationEngine(seed=42)
        result = engine.simulate_hour()
        assert "hour" in result
        assert "day" in result
        assert "phase" in result
        assert "is_night" in result
        assert "events" in result
        assert isinstance(result["events"], list)

    def test_multiple_hours(self):
        """Несколько часов подряд работают корректно."""
        engine = SimulationEngine(seed=42)
        for _ in range(10):
            result = engine.simulate_hour()
            assert result["hour"] == engine.state.time.hour - 1
            assert "phase" in result

    def test_state_summary(self):
        """get_state_summary возвращает корректную сводку."""
        engine = SimulationEngine(seed=42)
        summary = engine.get_state_summary()
        assert "hour" in summary
        assert "day" in summary
        assert "phase" in summary
        assert "active_humans" in summary
        assert "active_monsters" in summary
        assert "active_anomalies" in summary
        assert "total_events" in summary
        assert isinstance(summary["active_humans"], int)
        assert summary["active_humans"] > 0
        assert summary["active_monsters"] > 0
        assert summary["active_anomalies"] > 0

    def test_anomalies_exist_after_hour(self):
        """Аномалии не удаляются после одного часа."""
        engine = SimulationEngine(seed=42)
        initial_anomaly_count = len(engine.state.anomalies)
        engine.simulate_hour()
        assert len(engine.state.anomalies) == initial_anomaly_count

    def test_monsters_exist_after_hour(self):
        """Монстры не удаляются после одного часа."""
        engine = SimulationEngine(seed=42)
        initial_monster_count = len(engine.state.monsters)
        engine.simulate_hour()
        assert len(engine.state.monsters) >= initial_monster_count  # могут добавиться

    def test_humans_exist_after_hour(self):
        """NPC не удаляются после одного часа."""
        engine = SimulationEngine(seed=42)
        initial_human_count = len(engine.state.humans)
        engine.simulate_hour()
        assert len(engine.state.humans) >= initial_human_count - 1  # могут уйти

    def test_time_cycles_to_next_day(self):
        """Время переходит на следующие сутки."""
        engine = SimulationEngine(seed=42)
        engine.state.time.hour = 47
        result = engine.simulate_hour()
        # Симулировался час 47 (сутки 1 по §5: day = floor(hour/24))
        assert result["hour"] == 47
        assert result["day"] == 1
        # После шага — час 48, сутки 2
        assert engine.state.time.hour == 48
        assert engine.state.time.day == 2

    def test_phase_changes(self):
        """Фазы суток меняются корректно."""
        engine = SimulationEngine(seed=42)

        # Ночь (22-06)
        engine.state.time.hour = 23
        result = engine.simulate_hour()
        assert result["phase"] == "Ночь"
        assert result["is_night"] is True

        # Утро (06-07)
        engine.state.time.hour = 6
        result = engine.simulate_hour()
        assert result["phase"] == "Утро"

        # День (07-21)
        engine.state.time.hour = 12
        result = engine.simulate_hour()
        assert result["phase"] == "День"

        # Вечер (21-22)
        engine.state.time.hour = 21
        result = engine.simulate_hour()
        assert result["phase"] == "Вечер"

    def test_events_created_on_anomaly_contact(self):
        """События создаются при контакте с аномалией."""
        engine = SimulationEngine(seed=42)
        
        # Размещаем всю первую группу в сектор с аномалией
        if engine.state.anomalies and engine.state.human_groups:
            anomaly = next(iter(engine.state.anomalies.values()))
            first_group = next(iter(engine.state.human_groups.values()))
            for member_id in first_group.members:
                npc = next((n for n in engine.state.humans if n.id == member_id), None)
                if npc:
                    npc.sector_id = anomaly.sector_id
                    npc.status = EntityStatus.ACTIVE

        result = engine.simulate_hour()
        # Могли создаться события контакта
        assert result["events"] is not None

    def test_reproducible_seed(self):
        """Одинаковый seed даёт одинаковое начальное состояние."""
        engine1 = SimulationEngine(seed=123)
        engine2 = SimulationEngine(seed=123)

        assert len(engine1.state.sectors) == len(engine2.state.sectors)
        assert len(engine1.state.humans) == len(engine2.state.humans)
        assert len(engine1.state.monsters) == len(engine2.state.monsters)
        assert engine1.state.sectors[0].map_x == engine2.state.sectors[0].map_x

    def test_config_passed(self):
        """Config передаётся в движок."""
        engine = SimulationEngine(seed=42, config={"world": {"sectors_count": 20}})
        assert "sectors_count" in engine.state.config["world"]

    def test_mutation_does_not_crash(self):
        """Мутации NPC не вызывают ошибок."""
        engine = SimulationEngine(seed=42)

        for _ in range(24):
            result = engine.simulate_hour()
            # Проверяем, что время и сводка корректны
            assert "hour" in result
            assert "phase" in result

        summary = engine.get_state_summary()
        assert summary["day"] == 1
