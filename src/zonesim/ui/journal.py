"""Журнал событий с фильтрами. (§25, этап 5)"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QPlainTextEdit,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


def filter_events(events, event_type: str, min_importance: int):
    """Чистая функция фильтрации для тестирования."""
    result = []
    for event in events:
        if event_type != "все" and event.event_type != event_type:
            continue
        if event.importance < min_importance:
            continue
        result.append(event)
    return result


class JournalWidget(QWidget):
    """Таблица событий + фильтры + детали выбранной записи."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._events = []

        self.type_filter = QComboBox()
        self.type_filter.addItem("все")
        self.importance_filter = QSpinBox()
        self.importance_filter.setRange(0, 100)
        self.importance_filter.setValue(0)
        self.importance_filter.setPrefix("важность ≥ ")

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["час", "мин", "тип", "итог", "сводка"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setColumnWidth(0, 50)
        self.table.setColumnWidth(1, 36)
        self.table.setColumnWidth(2, 150)
        self.table.setColumnWidth(3, 150)

        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumBlockCount(2000)

        filters = QHBoxLayout()
        filters.addWidget(self.type_filter)
        filters.addWidget(self.importance_filter)
        filters.addStretch(1)

        body = QSplitter(Qt.Vertical)
        body.addWidget(self.table)
        body.addWidget(self.details)

        layout = QVBoxLayout(self)
        layout.addLayout(filters)
        layout.addWidget(body)

        self.type_filter.currentTextChanged.connect(self._refill)
        self.importance_filter.valueChanged.connect(self._refill)
        self.table.itemSelectionChanged.connect(self._show_details)

    def refresh(self, state) -> None:
        """Обновляет список событий и фильтр типов."""
        events = list(state.news_manager.events)
        self._events = events
        current = self.type_filter.currentText()
        types = sorted({e.event_type for e in events})
        self.type_filter.blockSignals(True)
        self.type_filter.clear()
        self.type_filter.addItem("все")
        self.type_filter.addItems(types)
        index = self.type_filter.findText(current)
        self.type_filter.setCurrentIndex(max(index, 0))
        self.type_filter.blockSignals(False)
        self._refill()

    def _filtered(self):
        return filter_events(
            self._events,
            self.type_filter.currentText(),
            self.importance_filter.value(),
        )

    def _refill(self) -> None:
        filtered = self._filtered()
        self.table.setRowCount(len(filtered))
        for row, event in enumerate(filtered):
            values = (
                str(event.hour),
                str(event.minute),
                event.event_type,
                str(event.result),
                event.summary,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column < 4:
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, column, item)
        self.table.scrollToBottom()

    def _show_details(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        event = self._filtered()[rows[0].row()]
        lines = [
            f"Час {event.hour}:{event.minute:02d} · {event.event_type} · {event.result}",
            f"Сектор: {event.sector_id} · важность {event.importance}",
            f"Участники: {event.participants}",
            "",
            event.summary,
            "",
            "Детали:",
        ]
        for key, value in sorted(event.details.items()):
            lines.append(f"  {key}: {value}")
        self.details.setPlainText("\n".join(lines))
