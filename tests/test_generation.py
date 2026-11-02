"""Тесты генерации мира. Основано на §23.1 ТЗ."""

import pytest
from zonesim.core.config import GameConfig
from zonesim.core.time import SeededRNG
from zonesim.generation.worldgen import generate_world
from zonesim.world.sector import get_distance, is_connected


class TestWorldGeneration:
    def test_basic_generation(self):
        result = generate_world(seed=42, config={"world": {"sectors_count": 10, "mobile_humans_count": 5, "monsters_count": 5, "anomalies_count": 5}})
        
        assert len(result["sectors"]) == 10
        assert len(result["humans"]) == 5
        assert len(result["monsters"]) == 5
        assert len(result["anomalies"]) == 5

    def test_graph_connected(self):
        result = generate_world(seed=42)
        assert is_connected(result["sectors"]) is True

    def test_reproducible_seed(self):
        r1 = generate_world(seed=123)
        r2 = generate_world(seed=123)
        
        assert len(r1["sectors"]) == len(r2["sectors"])
        # Сравним координаты первых секторов для проверки полной воспроизводимости
        assert r1["sectors"][0].map_x == r2["sectors"][0].map_x
        assert r1["sectors"][0].map_y == r2["sectors"][0].map_y

    def test_min_start_distance(self):
        result = generate_world(seed=42, config={"world": {"sectors_count": 30}})
        starts = [sid for sid, s in result["sectors"].items() if s.is_faction_start]
        
        assert len(starts) >= 3
        for i in range(len(starts)):
            for j in range(i + 1, len(starts)):
                dist = get_distance(result["sectors"], starts[i], starts[j])
                assert dist is not None and dist >= 4, f"Расстояние между стартами {starts[i]} и {starts[j]} меньше 4 ({dist})"

    def test_no_anomalies_at_starts(self):
        result = generate_world(seed=42)
        start_ids = {sid for sid, s in result["sectors"].items() if s.is_faction_start}
        
        anomaly_starts = {a.sector_id for a in result["anomalies"]}
        assert len(anomaly_starts.intersection(start_ids)) == 0
