"""Главное окно наблюдателя. (§25, этап 5)"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from zonesim.persistence.storage import SaveManager
from zonesim.simulation.engine import SimulationEngine
from zonesim.ui.journal import JournalWidget
from zonesim.ui.map_view import MapWidget
from zonesim.ui.panels import EntityPanel, SectorPanel

AUTOSAVE_SLOTS = ("autosave_0", "autosave_1", "autosave_2")
DEFAULT_SAVES_DIR = "saves"


class MainWindow(QMainWindow):
    def __init__(self, seed: int = 42, saves_dir: str | Path = DEFAULT_SAVES_DIR):
        super().__init__()
        self.setWindowTitle("Симуляция Зоны — наблюдатель")
        self.saves_dir = Path(saves_dir)
        self.saves_dir.mkdir(parents=True, exist_ok=True)
        self.engine = SimulationEngine(seed=seed, save_directory=self.saves_dir)
        self._running = False

        # --- виджеты ---
        self.map_widget = MapWidget()
        self.map_widget.set_engine(self.engine)
        self.journal = JournalWidget()
        self.sector_panel = SectorPanel()
        self.sector_panel.set_engine(self.engine)
        self.entity_panel = EntityPanel()

        tabs = QTabWidget()
        tabs.addTab(self.sector_panel, "Сектор")
        tabs.addTab(self.entity_panel, "Сущность")

        right = QSplitter(Qt.Orientation.Vertical)
        right.addWidget(self.journal)
        right.addWidget(tabs)

        body = QSplitter(Qt.Orientation.Horizontal)
        body.addWidget(self.map_widget)
        body.addWidget(right)
        body.setStretchFactor(0, 3)
        body.setStretchFactor(1, 2)

        # --- панель управления ---
        self.time_label = QLabel()
        self.tick_button = QPushButton("Час")
        self.run_button = QPushButton("Старт")
        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(0, 999999)
        self.seed_spin.setValue(seed)
        self.new_game_button = QPushButton("Новая игра")
        self.slot_combo = QComboBox()
        self.slot_combo.addItem("manual")
        self.slot_combo.addItems(AUTOSAVE_SLOTS)
        self.save_button = QPushButton("Сохранить")
        self.load_button = QPushButton("Загрузить")
        self.speed_spin = QSpinBox()
        self.speed_spin.setRange(1, 20)
        self.speed_spin.setValue(4)
        self.speed_spin.setSuffix(" час/с")

        controls = QHBoxLayout()
        controls.addWidget(self.time_label)
        controls.addWidget(self.tick_button)
        controls.addWidget(self.run_button)
        controls.addWidget(QLabel("seed:"))
        controls.addWidget(self.seed_spin)
        controls.addWidget(self.new_game_button)
        controls.addStretch(1)
        controls.addWidget(QLabel("слот:"))
        controls.addWidget(self.slot_combo)
        controls.addWidget(self.save_button)
        controls.addWidget(self.load_button)
        controls.addWidget(self.speed_spin)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(body, stretch=1)
        layout.addLayout(controls)
        self.setCentralWidget(central)
        self.resize(1200, 800)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

        self.tick_button.clicked.connect(self._tick)
        self.run_button.clicked.connect(self._toggle_run)
        self.new_game_button.clicked.connect(self._new_game)
        self.save_button.clicked.connect(self._save)
        self.load_button.clicked.connect(self._load)
        self.map_widget.sectorSelected.connect(self._show_sector)
        self.sector_panel.list.itemDoubleClicked.connect(self._show_selected_entity)
        self.sector_panel.list.itemClicked.connect(self._show_selected_entity)

        self.refresh_all()

    # --- игровой цикл ---

    def _tick(self) -> None:
        self.engine.simulate_hour()
        self.refresh_all()

    def _toggle_run(self) -> None:
        self._running = not self._running
        if self._running:
            self.run_button.setText("Пауза")
            self._timer.start(max(1000 // self.speed_spin.value(), 30))
        else:
            self.run_button.setText("Старт")
            self._timer.stop()

    def _new_game(self) -> None:
        if self._running:
            self._toggle_run()
        self.engine = SimulationEngine(
            seed=self.seed_spin.value(), save_directory=self.saves_dir,
        )
        self.map_widget.set_engine(self.engine)
        self.sector_panel.set_engine(self.engine)
        self.map_widget.select_sector(None)
        self.sector_panel.title.setText("Сектор не выбран")
        self.refresh_all()

    def _save(self) -> None:
        slot = self.slot_combo.currentText()
        self.engine.save(slot)
        self.statusBar().showMessage(f"Сохранено в слот «{slot}»", 5000)

    def _load(self) -> None:
        slot = self.slot_combo.currentText()
        try:
            self.engine = SimulationEngine.load(slot, self.saves_dir)
        except Exception as exc:  # SaveNotFoundError и прочие — сообщение пользователю
            QMessageBox.warning(self, "Загрузка", f"Не удалось загрузить слот «{slot}»:\n{exc}")
            return
        if self._running:
            self._toggle_run()
        self.engine.save_manager = SaveManager(self.saves_dir)
        self.map_widget.set_engine(self.engine)
        self.sector_panel.set_engine(self.engine)
        self.refresh_all()
        self.statusBar().showMessage(f"Загружен слот «{slot}»", 5000)

    # --- отображение ---

    def _show_sector(self, sector_id: int) -> None:
        self.sector_panel.show_sector(sector_id)

    def _show_selected_entity(self, _item=None) -> None:
        selected = self.sector_panel.selected_entity()
        if selected is None:
            return
        kind, entity_id = selected
        self.entity_panel.show_entity(self.engine.state, kind, entity_id)

    def refresh_all(self) -> None:
        state = self.engine.state
        hour = state.time.hour
        phase = state.time.current_phase.value if hasattr(state.time.current_phase, "value") else str(state.time.current_phase)
        text = f"День {state.time.day} · час {hour} · {phase}"
        if state.emission_start_hour >= 0 and state.emission_start_hour <= hour < state.emission_end_hour:
            text += "  ·  ВЫБРОС"
        self.time_label.setText(text)
        self.map_widget.update()
        self.journal.refresh(state)
        if self.map_widget.selected_sector is not None:
            self.sector_panel.show_sector(self.map_widget.selected_sector)
