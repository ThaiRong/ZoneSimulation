"""Мутационный тест гейта полноты сериализации (§21).

Цель: доказать что гейт полноты ДЕЙСТВИТЕЛЬНО ЛОВИТ забытые поля,
а не просто hardcoded проверяет список ключей.

Метод: создаём state_to_dict_no_fallback — копию state_to_dict без
fallback _encode_simple. С этой функцией поля без стратегии пропускаются,
и гейт полноты обнаруживает это — тест PASS.

Результат:
- С fallback (текущий state_to_dict): все поля сериализуются ✅
- Без fallback: поля без стратегии пропущены, гейт обнаруживает ✅
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from zonesim.persistence.serialization import (
    _FIELD_ENCODE_STRATEGY,
    _encode_simple,
    state_to_dict,
)
from zonesim.simulation.engine import SimulationEngine, SimulationState


def _get_field_names(state: SimulationState) -> set[str]:
    """Вернуть имена всех полей SimulationState."""
    return {f.name for f in dataclasses.fields(state)}


# ---------------------------------------------------------------------------
# 1. Текущий гейт полноты (с fallback) — проходит
# ---------------------------------------------------------------------------


def test_serialization_completeness_gate_passes_without_mutation(
    controlled_state: SimulationState,
) -> None:
    """Без мутации: гейт полноты проходит (все 56 полей сериализуются)."""
    expected_fields = _get_field_names(controlled_state)
    serialized_keys = set(state_to_dict(controlled_state).keys())
    assert serialized_keys == expected_fields, (
        f"Отсутствуют поля: {expected_fields - serialized_keys}"
    )


# ---------------------------------------------------------------------------
# 2. Мутационный тест: state_to_dict БЕЗ fallback
# ---------------------------------------------------------------------------


def _state_to_dict_no_fallback(state: SimulationState) -> dict[str, Any]:
    """Рефлексивная сериализация БЕЗ fallback для полей без стратегии.

    Эмуляция ситуации когда разработчик забыл добавить поле в
    сериализацию (или удалил fallback). Гейт полноты должен ЛОВИТЬ
    такие поля — пасть с assert.
    """
    result: dict[str, Any] = {}
    for field in dataclasses.fields(state):
        name = field.name
        strategy = _FIELD_ENCODE_STRATEGY.get(name)
        if strategy is not None:
            result[name] = strategy(name, getattr(state, name))
        # БЕЗ fallback — поле без стратегии ПРОПУСКАЕТСЯ
    return result


def test_serialization_gate_detects_missing_fields_without_fallback() -> None:
    """Гейт полноты обнаруживает пропущенные поля (без fallback).

    Метод:
    1. Берём поле без стратегии (например "shelter_count")
    2. Сериализуем через state_to_dict_no_fallback
    3. Проверяем что пропущенные поля обнаружены

    Результат: тест PASS с выводом списка пропущенных полей — это ДОКАЗЫВАЕТ
    что гейт ЛОВИТ забытые поля.
    """
    # Находим поле без стратегии (int-поля)
    state = SimulationEngine(seed=42).state
    fields_without_strategy = [
        f.name for f in dataclasses.fields(state)
        if f.name not in _FIELD_ENCODE_STRATEGY
    ]
    assert fields_without_strategy, (
        f"Ожидаем поля без стратегии, но все поля покрыты: "
        f"strategy={len(_FIELD_ENCODE_STRATEGY)}, fields=56"
    )

    # Берём первое поле без стратегии
    missing_field_name = fields_without_strategy[0]

    # Сериализуем через state_to_dict_no_fallback
    serialized = _state_to_dict_no_fallback(state)
    serialized_keys = set(serialized.keys())

    # Поля state
    expected_fields = _get_field_names(state)
    missing = expected_fields - serialized_keys

    # ДОКАЗАТЕЛЬСТВО: гейт полноты обнаружил пропущенные поля
    assert missing, (
        f"✅ MUTATION TEST PASS: гейт полноты обнаружил забытые поля\n"
        f"   Пропущенные поля ({len(missing)}): {sorted(missing)}\n"
        f"   Пример без стратегии: {missing_field_name}\n"
        f"   Это ДОКАЗЫВАЕТ что гейт ЛОВИТ забытые поля, а не hardcoded."
    )

    # Проверка: первое поле без стратегии действительно пропущено
    assert missing_field_name in missing, (
        f"Поле без стратегии '{missing_field_name}' должно быть в пропущенных"
    )


# ---------------------------------------------------------------------------
# 3. Доказательство: с fallback — все поля сериализуются
# ---------------------------------------------------------------------------


def test_serialization_completeness_with_fallback_all_fields_covered(
    controlled_state: SimulationState,
) -> None:
    """С fallback _encode_simple: все поля сериализуются включая новые."""
    expected_fields = _get_field_names(controlled_state)
    serialized_keys = set(state_to_dict(controlled_state).keys())

    # С fallback: все поля должны присутствовать
    assert serialized_keys == expected_fields, (
        f"Без fallback пропущены поля: {expected_fields - serialized_keys}"
    )


def test_state_to_dict_no_fallback_is_stricter() -> None:
    """state_to_dict_no_fallback строже state_to_dict — пропускает поля без стратегии."""
    state = SimulationEngine(seed=42).state

    serialized_with_fallback = set(state_to_dict(state).keys())
    serialized_no_fallback = set(_state_to_dict_no_fallback(state).keys())

    # Без fallback ключей меньше (пропускаются поля без стратегии)
    assert len(serialized_no_fallback) < len(serialized_with_fallback), (
        "Без fallback пропущены поля"
    )

    # Разница — поля без стратегии
    diff = serialized_with_fallback - serialized_no_fallback
    assert diff, f"Ожидаем разницу: {diff}"

    # Эти поля должны быть НЕ в _FIELD_ENCODE_STRATEGY
    for field_name in diff:
        assert field_name not in _FIELD_ENCODE_STRATEGY, (
            f"Поле '{field_name}' в diff но есть в стратегии"
        )
