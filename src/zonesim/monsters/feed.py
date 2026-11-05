"""Поедание трупов монстрами. Основано на §13.5 ТЗ."""

from __future__ import annotations

from zonesim.combat.loot import Corpse
from zonesim.monsters.behavior import species_value


__all__ = ["Corpse", "FeedManager"]


class FeedManager:
    """Поедание одного трупа за основное действие группы."""

    def process_feeding(
        self,
        monsters_in_sector: list,
        available_corpses: list[Corpse],
        hour: int,
        rng_values: list[float] = None,
    ) -> list[dict]:
        results = []
        rng_values = rng_values or []
        for index, monster in enumerate(monsters_in_sector):
            if not available_corpses:
                break
            chance = rng_values[index] if index < len(rng_values) else 0.0
            if chance * 100 < 70.0:
                corpse = available_corpses[0]
                result = self.consume(corpse, monster, hour)
                available_corpses.pop(0)
                results.append(result)
        return results

    def consume(self, corpse: Corpse, monster, hour: int, items: dict | None = None) -> dict:
        if not self.can_consume(species_value(monster), corpse):
            return {"success": False, "reason": "corpse_unavailable"}
        lost_items = list(corpse.items)
        if items is not None:
            for item_id in lost_items:
                items.pop(item_id, None)
        corpse.items.clear()
        corpse.monster_parts.clear()
        corpse.money = 0
        corpse.status = "consumed"
        corpse.consumed_by = monster.id
        corpse.consumed_hour = hour
        monster.stamina = min(monster.max_stamina, monster.stamina + 30)
        return {
            "success": True,
            "monster_id": monster.id,
            "species": species_value(monster),
            "corpse_id": corpse.id,
            "corpse_type": corpse.original_entity_type,
            "consumed_hour": hour,
            "lost_items": lost_items,
        }

    def can_consume(self, monster_species: str, corpse: Corpse) -> bool:
        return corpse.status == "available"

    def get_consumption_reward(self, corpse: Corpse) -> dict:
        return {
            "corpse_destroyed": True,
            "items_corrupted": len(corpse.items) + len(corpse.monster_parts),
            "note": "оставшиеся вещи утрачены полностью",
        }
