"""Панели сектора и сущности. (§25, этап 5)"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QListWidget, QPlainTextEdit, QVBoxLayout, QWidget

from zonesim.anomalies.core import AnomalyStatus
from zonesim.monsters.behavior import species_value
from zonesim.world.entity import EntityStatus, EntityType

STATUS_LABELS = {
    EntityStatus.ACTIVE: "активен",
    EntityStatus.SLEEPING: "спит",
    EntityStatus.UNCONSCIOUS: "без сознания",
    EntityStatus.PRISONER: "в плену",
    EntityStatus.DEAD: "погиб",
    EntityStatus.EXILED: "покинул Зону",
}


def sector_contents(state, sector_id: int) -> list[tuple[str, str, int]]:
    """Содержимое сектора: список (подпись, kind, id) для панели и тестов."""
    entries: list[tuple[str, str, int]] = []
    shelter = next(
        (s for s in state.shelters.values() if s.sector_id == sector_id), None,
    )
    if shelter is not None:
        status = (
            f"занято монстрами до часа {shelter.occupied_until}"
            if shelter.is_occupied else "свободно"
        )
        entries.append((f"Укрытие (вместимость {shelter.capacity}, {status})", "shelter", shelter.id))
    if any(a.sector_id == sector_id for a in state.anomalies.values()):
        entries.append(("Стационарный персонал базы", "base", sector_id))
    for anomaly in state.anomalies.values():
        if anomaly.sector_id != sector_id:
            continue
        status = "активна" if anomaly.status == AnomalyStatus.ACTIVE else "разрушена"
        entries.append((
            f"Аномалия {anomaly.id} [{anomaly.anomaly_type.value}] {status}, "
            f"устойчивость {anomaly.stability}",
            "anomaly", anomaly.id,
        ))
    for npc in state.stationary_humans:
        if npc.sector_id != sector_id:
            continue
        role = "торговец" if npc.stationary_role == "trader" else "охранник"
        entries.append((
            f"{role.capitalize()} {npc.name} ({npc.faction}) — {STATUS_LABELS[npc.status]}",
            "npc", npc.id,
        ))
    for group in state.human_groups.values():
        if group.sector_id != sector_id:
            continue
        entries.append((f"Группа людей {group.id} — «{group.intention}»", "group", group.id))
    for npc in state.humans:
        if npc.sector_id != sector_id:
            continue
        entries.append((
            f"{npc.name} ({npc.faction}) — {STATUS_LABELS[npc.status]}, "
            f"здоровье {npc.health}/{npc.max_health}, выносл. {int(npc.stamina)}",
            "npc", npc.id,
        ))
    for group in state.monster_groups.values():
        if group.sector_id != sector_id:
            continue
        entries.append((
            f"Группа монстров {group.id} [{group.species}] — «{group.intention}»",
            "monster_group", group.id,
        ))
    for corpse in state.corpses:
        if corpse.sector_id != sector_id or corpse.status != "available":
            continue
        entries.append((f"Труп ({corpse.original_entity_type}) — находка", "corpse", corpse.id))
    return entries


def entity_description(state, kind: str, entity_id: int) -> str:
    """Текстовое описание сущности для панели и тестов."""
    if kind == "shelter":
        shelter = state.shelters.get(entity_id)
        if shelter is None:
            return "Укрытие не найдено"
        return (
            f"Стационарное укрытие {shelter.id}\n"
            f"Сектор: {shelter.sector_id}\n"
            f"Вместимость: {shelter.capacity}\n"
            f"Состояние: {shelter.condition}\n"
            f"Занято: {shelter.occupied_by if shelter.is_occupied else 'нет'}"
        )
    if kind == "anomaly":
        anomaly = state.anomalies.get(entity_id)
        if anomaly is None:
            return "Аномалия не найдена"
        blocked = anomaly.blocks_trail or "нет"
        return (
            f"Аномалия {anomaly.id} [{anomaly.anomaly_type.value}]\n"
            f"Сектор: {anomaly.sector_id} · статус: {anomaly.status.value}\n"
            f"Устойчивость: {anomaly.stability} · скрытность: {anomaly.concealment}\n"
            f"Урон: {anomaly.damage_min}–{anomaly.damage_max}\n"
            f"Таймер артефакта: {anomaly.artifact_timer} · тропа: {blocked}"
        )
    if kind == "npc":
        npc = next(
            (n for n in state.humans + state.stationary_humans if n.id == entity_id), None,
        )
        if npc is None:
            return "NPC не найден"
        weapon = state.items.get(npc.equipped_weapon_id)
        armor = state.items.get(npc.equipped_armor_id)
        lines = [
            f"{npc.name} ({npc.faction}) — {STATUS_LABELS[npc.status]}",
            f"Сектор: {npc.sector_id} · группа: {npc.group_id}",
            f"Здоровье: {npc.health}/{npc.max_health} · выносливость: {int(npc.stamina)}/{npc.max_stamina}",
            f"Атака {npc.attack} · защита {npc.defense} · внимательность {npc.attentiveness} · храбрость {npc.bravery}",
            f"Оружие: {weapon.name if weapon else 'нет'} (урон {npc.weapon_damage})",
            f"Броня: {armor.name if armor else 'нет'} (коэфф. {npc.armor_value:.2f})",
            f"Деньги: {npc.money} · намерение: {npc.intention}",
        ]
        if npc.artifacts:
            lines.append(f"Артефакты: {npc.artifacts}")
        return "\n".join(lines)
    if kind == "group":
        group = state.human_groups.get(entity_id)
        if group is None:
            return "Группа не найдена"
        members = [n for n in state.humans if n.id in group.members]
        lines = [
            f"Группа людей {group.id} — «{group.intention}»",
            f"Сектор: {group.sector_id} · лидер: {group.leader_id}",
            f"Состав ({len(members)}): "
            + ", ".join(f"{n.name} [{STATUS_LABELS[n.status]}]" for n in members),
        ]
        if group.prisoners:
            lines.append(f"Пленные: {group.prisoners}")
        return "\n".join(lines)
    if kind == "monster_group":
        group = state.monster_groups.get(entity_id)
        if group is None:
            return "Группа монстров не найдена"
        monsters = [m for m in state.monsters if m.id in group.members]
        lines = [
            f"Группа монстров {group.id} [{group.species}] — «{group.intention}»",
            f"Сектор: {group.sector_id}",
            f"Состав ({len(monsters)}):",
        ]
        for monster in monsters:
            lines.append(
                f"  {monster.id}: {STATUS_LABELS[monster.status]}, "
                f"здоровье {monster.health}/{monster.max_health}"
            )
        return "\n".join(lines)
    if kind == "corpse":
        corpse = next((c for c in state.corpses if c.id == entity_id), None)
        if corpse is None:
            return "Труп не найден"
        return (
            f"Труп {corpse.id} ({corpse.original_entity_type})\n"
            f"Сектор: {corpse.sector_id} · создан в час {corpse.created_hour}\n"
            f"Статус: {corpse.status} · деньги: {corpse.money} · предметов: {len(corpse.items)}"
        )
    return "Неизвестный тип сущности"


class SectorPanel(QWidget):
    """Содержимое выбранного сектора; двойной клик — описание сущности."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.title = QLabel("Сектор не выбран")
        self.list = QListWidget()
        self.list.setMinimumHeight(120)
        self._engine = None
        self._entries: list[tuple[str, str, int]] = []

        layout = QVBoxLayout(self)
        layout.addWidget(self.title)
        layout.addWidget(self.list)

    def set_engine(self, engine) -> None:
        self._engine = engine

    def show_sector(self, sector_id: int) -> None:
        if self._engine is None:
            return
        self._entries = sector_contents(self._engine.state, sector_id)
        self.title.setText(f"Сектор {sector_id}")
        self.list.clear()
        for label, _kind, _eid in self._entries:
            self.list.addItem(label)

    def selected_entity(self) -> tuple[str, int] | None:
        row = self.list.currentRow()
        if row < 0 or row >= len(self._entries):
            return None
        return self._entries[row][1], self._entries[row][2]


class EntityPanel(QWidget):
    """Описание выбранной сущности."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        layout = QVBoxLayout(self)
        layout.addWidget(self.text)

    def show_entity(self, state, kind: str, entity_id: int) -> None:
        self.text.setPlainText(entity_description(state, kind, entity_id))
