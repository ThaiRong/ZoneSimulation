"""Игровое время и фазы суток. Основано на §5 ТЗ."""

from __future__ import annotations

import random
from enum import Enum


class PhaseOfDay(str, Enum):
    NIGHT = "Ночь"
    MORNING = "Утро"
    DAY = "День"
    EVENING = "Вечер"


class GameTime:
    """Управление игровым временем."""

    def __init__(self, start_hour: int = 7):
        self.hour: int = start_hour

    @property
    def day(self) -> int:
        return self.hour // 24

    @property
    def current_phase(self) -> PhaseOfDay:
        h = self.hour % 24
        if 22 <= h < 24 or 0 <= h < 6:
            return PhaseOfDay.NIGHT
        if 6 <= h < 7:
            return PhaseOfDay.MORNING
        if 7 <= h < 21:
            return PhaseOfDay.DAY
        # 21 <= h < 22
        return PhaseOfDay.EVENING

    def is_night(self) -> bool:
        return self.current_phase == PhaseOfDay.NIGHT

    def advance(self) -> None:
        """Перематывает время на 1 час (один шаг)."""
        self.hour += 1

    def __repr__(self) -> str:
        return f"GameTime(hour={self.hour}, day={self.day}, phase={self.current_phase.value})"


class SeededRNG:
    """Обёртка для воспроизводимого генератора случайных чисел. §20.3"""

    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed)

    def random(self) -> float:
        return self.rng.random()

    def randint(self, a: int, b: int) -> int:
        return self.rng.randint(a, b)

    def choice(self, seq):
        return self.rng.choice(seq)

    def shuffle(self, x):
        self.rng.shuffle(x)

    def gauss(self, mu: float, sigma: float) -> float:
        return self.rng.gauss(mu, sigma)

    def uniform(self, a: float, b: float) -> float:
        return self.rng.uniform(a, b)

    def clamp(self, value: float, min_val: float, max_val: float) -> float:
        return max(min_val, min(value, max_val))
