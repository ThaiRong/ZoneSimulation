"""Тесты ядра времени и конфигурации. Основано на §5 ТЗ."""

from zonesim.core.time import GameTime, PhaseOfDay


class TestGameTime:
    def test_night_phase(self):
        t = GameTime(start_hour=23)
        assert t.current_phase == PhaseOfDay.NIGHT

        t = GameTime(start_hour=3)
        assert t.current_phase == PhaseOfDay.NIGHT

    def test_day_phase(self):
        t = GameTime(start_hour=12)
        assert t.current_phase == PhaseOfDay.DAY

    def test_morning_and_evening(self):
        t = GameTime(start_hour=6)
        assert t.current_phase == PhaseOfDay.MORNING

        t = GameTime(start_hour=21)
        assert t.current_phase == PhaseOfDay.EVENING

    def test_day_calculation(self):
        t = GameTime(start_hour=25)
        assert t.day == 1

    def test_advance(self):
        t = GameTime(start_hour=5)
        t.advance()
        assert t.hour == 6
        assert t.current_phase == PhaseOfDay.MORNING

    def test_is_night(self):
        t = GameTime(start_hour=22)
        assert t.is_night() is True

        t2 = GameTime(start_hour=14)
        assert t2.is_night() is False
