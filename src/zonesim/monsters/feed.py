"""Поедание трупов монстрами. Основано на §13.5 ТЗ."""

from __future__ import annotations

from zonesim.combat.loot import Corpse


__all__ = ["Corpse", "FeedManager"]


class FeedManager:
    """Поедание трупов монстрами. (§13.5)"""

    def process_feeding(
        self,
        monsters_in_sector: list,
        available_corpses: list[Corpse],
        hour: int,
        rng_values: list[float] = None,
    ) -> list[dict]:
        """
        Обрабатывает поедание трупов монстрами в секторе.
        Один труп обрабатывается за действие.
        Конкурирующие группы — инициатива.
        """
        rng_values = rng_values or []
        results = []

        for i, monster in enumerate(monsters_in_sector):
            if not available_corpses:
                break

            # Шанс поедания
            feed_chance = 70.0  # базовый шанс
            if rng_values and i < len(rng_values):
                if rng_values[i] * 100 < feed_chance:
                    corpse = available_corpses.pop(0)
                    corpse.status = "consumed"

                    results.append({
                        "monster_id": monster.id,
                        "species": monster.species.value if hasattr(monster, 'species') else "unknown",
                        "corpse_id": corpse.id,
                        "corpse_type": corpse.original_entity_type,
                        "consumed_hour": hour,
                    })

        return results

    def can_consume(self, monster_species: str, corpse: Corpse) -> bool:
        """
        Проверяет, может ли монстр данного вида съесть труп.
        """
        if corpse.status != "available":
            return False

        # Монстры едят всё, что могут
        return True

    def get_consumption_reward(self, corpse: Corpse) -> dict:
        """
        Возвращает результат поедания: труп исчезает, снаряжение портится.
        (§11.8, §7.11)
        """
        return {
            "corpse_destroyed": True,
            "items_corrupted": len(corpse.monster_parts),
            "note": "оставшиеся вещи утрачены полностью",
        }
