"""Схема карты: сектора, рёбра, тропы, метки. (§25, этап 5)"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from zonesim.anomalies.core import AnomalyStatus
from zonesim.world.entity import EntityStatus

FACTION_COLORS = {
    "Бродяги": QColor(146, 102, 62),
    "Борзые": QColor(148, 52, 52),
    "Серая лига": QColor(96, 118, 148),
}
BASE_COLOR = QColor(58, 74, 58)
EMPTY_COLOR = QColor(70, 82, 70)
SELECT_COLOR = QColor(240, 200, 90)
NODE_RADIUS = 14


class MapWidget(QWidget):
    """Виджет карты-схемы: клик по сектору выбирает его."""

    sectorSelected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._engine = None
        self.selected_sector: int | None = None
        self.setMinimumSize(420, 420)
        self.setMouseTracking(False)

    def set_engine(self, engine) -> None:
        self._engine = engine
        self.update()

    def select_sector(self, sector_id: int | None) -> None:
        self.selected_sector = sector_id
        self.update()

    # --- геометрия ---

    def _bounds(self):
        sectors = self._engine.state.sectors.values()
        xs = [s.map_x for s in sectors]
        ys = [s.map_y for s in sectors]
        return min(xs), max(xs), min(ys), max(ys)

    def _to_scene(self) -> tuple[QPointF, float]:
        min_x, max_x, min_y, max_y = self._bounds()
        margin = 40.0
        w = max(self.width() - 2 * margin, 50.0)
        h = max(self.height() - 2 * margin, 50.0)
        span_x = max(max_x - min_x, 1.0)
        span_y = max(max_y - min_y, 1.0)
        scale = min(w / span_x, h / span_y)
        origin_x = (self.width() - span_x * scale) / 2 - min_x * scale
        origin_y = (self.height() - span_y * scale) / 2 - min_y * scale
        return QPointF(origin_x, origin_y), scale

    def _sector_pos(self, sector) -> QPointF:
        origin, scale = self._to_scene()
        return QPointF(
            origin.x() + sector.map_x * scale,
            origin.y() + sector.map_y * scale,
        )

    # --- рисование ---

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(28, 32, 30))
        if self._engine is None or not self._engine.state.sectors:
            painter.end()
            return
        state = self._engine.state
        trails = {tuple(sorted(pair)) for pair in state.trails}
        blocked = {
            tuple(sorted(a.blocks_trail))
            for a in state.anomalies.values()
            if a.status == AnomalyStatus.ACTIVE and a.blocks_trail
        }

        # рёбра
        for sector in state.sectors.values():
            p1 = self._sector_pos(sector)
            for nid in sector.neighbors:
                if nid < sector.id:
                    continue  # рисуем каждое ребро один раз
                other = state.sectors[nid]
                p2 = self._sector_pos(other)
                key = tuple(sorted((sector.id, nid)))
                if key in blocked:
                    painter.setPen(QPen(QColor(200, 70, 70), 2))
                elif key in trails:
                    painter.setPen(QPen(QColor(120, 160, 110), 1, Qt.DashLine))
                else:
                    painter.setPen(QPen(QColor(90, 100, 92), 1))
                painter.drawLine(p1, p2)

        # сектора
        for sector in state.sectors.values():
            center = self._sector_pos(sector)
            color = FACTION_COLORS.get(sector.controller_faction, EMPTY_COLOR)
            painter.setBrush(color)
            if sector.id == self.selected_sector:
                painter.setPen(QPen(SELECT_COLOR, 3))
            else:
                painter.setPen(QPen(QColor(20, 24, 22), 1))
            painter.drawEllipse(center, NODE_RADIUS, NODE_RADIUS)
            painter.setPen(QColor(230, 230, 225))
            painter.drawText(
                QRectF(center.x() - 20, center.y() - 8, 40, 16),
                Qt.AlignCenter, str(sector.id),
            )
            painter.setPen(QColor(180, 190, 180))
            painter.drawText(
                QRectF(center.x() - 26, center.y() + NODE_RADIUS, 52, 12),
                Qt.AlignCenter, self._marker_text(sector.id),
            )

        # шапка состояния
        hour = state.time.hour
        text = f"День {state.time.day} · час {hour}"
        if state.emission_start_hour >= 0 and state.emission_start_hour <= hour < state.emission_end_hour:
            painter.setPen(QColor(255, 120, 90))
            text += "  ·  ВЫБРОС"
        elif (
            state.emission_warning_hour >= 0
            and hour >= state.emission_warning_hour
            and state.emission_start_hour < 0
        ):
            painter.setPen(QColor(255, 200, 100))
            text += f"  ·  выброс ожидается к {state.next_emission_hour}"
        else:
            painter.setPen(QColor(210, 215, 210))
        painter.drawText(12, 20, text)
        painter.end()

    def _marker_text(self, sector_id: int) -> str:
        state = self._engine.state
        marks = []
        if any(s.sector_id == sector_id for s in state.shelters.values()):
            marks.append("У")
        if any(
            a.sector_id == sector_id and a.status == AnomalyStatus.ACTIVE
            for a in state.anomalies.values()
        ):
            marks.append("А")
        if any(
            n.sector_id == sector_id and n.stationary_role == "trader"
            and n.status == EntityStatus.ACTIVE
            for n in state.stationary_humans
        ):
            marks.append("Т")
        humans = sum(1 for n in state.humans + state.stationary_humans
                     if n.sector_id == sector_id and n.status != EntityStatus.DEAD)
        monsters = sum(1 for m in state.monsters
                       if m.sector_id == sector_id and m.status == EntityStatus.ACTIVE)
        if humans:
            marks.append(f"Л{humans}")
        if monsters:
            marks.append(f"М{monsters}")
        return " ".join(marks)

    # --- выбор ---

    def mousePressEvent(self, event) -> None:
        if self._engine is None:
            return
        click = event.position()
        best = None
        best_dist = NODE_RADIUS + 6
        for sector in self._engine.state.sectors.values():
            dist = (self._sector_pos(sector) - click).manhattanLength()
            if dist < best_dist:
                best = sector.id
                best_dist = dist
        if best is not None:
            self.selected_sector = best
            self.sectorSelected.emit(best)
            self.update()
