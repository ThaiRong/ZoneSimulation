"""Проверки интерфейса наблюдателя (offscreen-режим Qt)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

# PySide6 может быть установлен, но не импортироваться из-за отсутствующих
# системных библиотек Qt (например, libEGL.so.1 в headless-среде).
# Поэтому ловим и ImportError тоже, чтобы тесты пропускались, а не падали при сборе.
try:
    from PySide6.QtWidgets import QApplication
except ImportError as exc:  # pragma: no cover - окружение без графических библиотек
    pytest.skip(f"PySide6 недоступен: {exc}", allow_module_level=True)

from zonesim.ui.journal import filter_events
from zonesim.ui.main_window import MainWindow
from zonesim.ui.panels import entity_description, sector_contents


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def window(qapp, tmp_path):
    win = MainWindow(seed=42, saves_dir=tmp_path)
    yield win
    if win._running:
        win._toggle_run()
    win.close()


class TestMainWindow:
    def test_constructs(self, window, qapp):
        assert window.windowTitle().startswith("Симуляция Зоны")
        assert window.engine.state.time.hour == 7  # стартовое время суток
        window.show()
        qapp.processEvents()  # прокраска карты и журнала в offscreen-режиме

    def test_tick_updates_time_and_journal(self, window):
        start = window.engine.state.time.hour
        window._tick()
        assert window.engine.state.time.hour == start + 1
        assert f"час {start + 1}" in window.time_label.text()
        assert window.journal.table.rowCount() > 0

    def test_run_toggle(self, window):
        window._toggle_run()
        assert window._running
        window._toggle_run()
        assert not window._running

    def test_sector_selection_shows_contents(self, window):
        sector_id = next(iter(window.engine.state.sectors))
        window._show_sector(sector_id)
        assert window.sector_panel.title.text() == f"Сектор {sector_id}"
        assert window.sector_panel.list.count() == len(
            sector_contents(window.engine.state, sector_id)
        )

    def test_entity_details(self, window):
        state = window.engine.state
        npc = next(n for n in state.humans)
        text = entity_description(state, "npc", npc.id)
        assert npc.name in text and npc.faction in text

    def test_save_load_roundtrip(self, window, tmp_path):
        window._tick()
        window._tick()
        window.slot_combo.setCurrentText("manual")
        window._save()
        saved_hour = window.engine.state.time.hour
        window._tick()
        assert window.engine.state.time.hour == saved_hour + 1
        window._load()
        assert window.engine.state.time.hour == saved_hour
        assert (tmp_path / "manual.sqlite").exists()


class TestJournalFilter:
    def test_filter_by_type_and_importance(self):
        from zonesim.relations.news import NewsManager

        news = NewsManager()
        news.create_event(hour=1, minute=0, sector_id=1, event_type="combat",
                          participants=[], result="x", importance=60, summary="а")
        news.create_event(hour=2, minute=0, sector_id=1, event_type="research",
                          participants=[], result="y", importance=10, summary="б")
        events = list(news.events)
        assert len(filter_events(events, "все", 0)) == 2
        assert len(filter_events(events, "combat", 0)) == 1
        assert len(filter_events(events, "все", 50)) == 1


class TestSectorContents:
    def test_lists_everything_present(self, window):
        state = window.engine.state
        base = next(s for s in state.sectors.values() if s.is_faction_start)
        labels = [label.lower() for label, _k, _i in sector_contents(state, base.id)]
        assert any("охранник" in label or "торговец" in label for label in labels)
