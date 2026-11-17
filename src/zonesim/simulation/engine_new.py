    def _group_can_create_shelter(self, group: HumanGroup, members: list[HumanNPC]) -> bool:
        """Проверяет наличие набора для убежища и кулдаун (§7.10).

        Нерасходный предмет: базово есть у всех людей, не тратится.
        Кулдаун на уровне группы: не чаще одного убежища за 12 часов.
        Не создаём, если уже есть активное убежище группы в этом секторе.
        """
        # Проверка: хотя бы один NPC имеет набор
        has_kit = any(
            self.state.items.get(item_id) and self.state.items[item_id].type is ItemType.SHELTER_KIT
            for npc in members
            for item_id in npc.inventory
        )
        if not has_kit:
            return False

        # Кулдаун на уровне группы
        if self.state.time.hour - group.last_shelter_hour < 12:
            return False

        # Не создаём, если уже есть активное убежище группы в этом секторе
        for shelter in self.state.temp_shelters.values():
            if shelter.owner_group_id == group.id and shelter.sector_id == group.sector_id:
                if not shelter.destroyed:
                    return False

        return True

    def _process_create_shelter(self, group: HumanGroup, hour: int) -> bool:
        """Создаёт временное убежище (§7.10)."""
        members = self._active_members(group)
        if not members:
            return False

        # Проверка набора (дублирует _group_can_create_shelter для безопасности)
        has_kit = any(
            self.state.items.get(item_id) and self.state.items[item_id].type is ItemType.SHELTER_KIT
            for npc in members
            for item_id in npc.inventory
        )
        if not has_kit:
            return False

        # Создать Shelter — материал не расходуется
        shelter_id = self.state.next_shelter_id
        self.state.next_shelter_id += 1
        shelter = Shelter(
            id=shelter_id,
            sector_id=group.sector_id,
            owner_group_id=group.id,
            owner_faction=members[0].faction if members else "",
            created_hour=hour,
            last_used_hour=hour,
            quality=50,
        )
        shelter.add_group(group.id, [m.id for m in members if m.status == EntityStatus.ACTIVE])
        self.state.temp_shelters[shelter_id] = shelter

        # Кулдаун на уровне группы: запретить группе создавать убежища ещё 12 часов
        group.last_shelter_hour = hour

        self.state.news_manager.create_event(
            hour=hour, minute=0, sector_id=group.sector_id,
            event_type="shelter_created",
            participants=[m.id for m in members[:1]],
            result="created",
            importance=30,
            summary=f"Группа {group.id} создала временное убежище в секторе {group.sector_id}",
            details={"shelter_id": shelter_id, "sector_id": group.sector_id},
        )
        return True
