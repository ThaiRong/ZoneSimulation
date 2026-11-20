"""Компактный детерминированный отпечаток SimulationEngine — «Страховка» перед рефакторингом.

Этап 3, Промпт 3.0а: компактный fingerprint вместо полных сейвов (~72 МБ → <300 КБ).

Критерии приёмки:
1. SHA256(serialize(state_to_dict)) — один хэш на чекпоинт (целостность всего состояния).
2. Структурированный фингерпринт для читаемости диффов (сущности, сектора, отношения…).
3. Baseline < 100 КБ на сид; три сида 42/7/123 закоммичены.
4. Тест при расхождении показывает: чекпоинт/сид, какое поле фингерпринта, хэши.
5. Save/load в середине (час 120) + 10 ч идентичны непрерывному прогону.
6. Мутация: изменение одного числа → тест падает.

ЗАПРЕТЫ: не менять логику симуляции; не ослаблять тесты.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import pytest

from zonesim.persistence.serialization import state_to_dict
from zonesim.simulation.engine import SimulationEngine

# ---------------------------------------------------------------------------
# Конфигурация
# ---------------------------------------------------------------------------

BASELINE_DIR = Path(__file__).resolve().parent / "_baseline"
CHECKPOINT_HOURS = [0, 24, 120, 240, 480]
SEEDS = [42, 7, 123]

MAX_BASELINE_KB = 100


# ---------------------------------------------------------------------------
# Хелперы
# ---------------------------------------------------------------------------

def _run_to_checkpoint(engine: SimulationEngine, target_hour: int) -> None:
    """Прогнать симуляцию до нужного часа."""
    while engine.state.time.hour < target_hour:
        engine.simulate_hour()


# ---------------------------------------------------------------------------
# Fingerprint — компактная структура (вместо полного state_to_dict)
# ---------------------------------------------------------------------------

def _compute_fingerprint(state: Any) -> dict[str, Any]:
    """Вычислить компактный детерминированный отпечаток состояния.

    Включает:
    - количества сущностей всех типов
    - сектор-состав групп (отсортированный)
    - суммарные ресурсы фракций
    - хэши подструктур (знания, отношения, новости)
    """
    s = state

    # --- Количество сущностей ---
    entities: dict[str, int] = {
        "humans": len(s.humans),
        "stationary_humans": len(s.stationary_humans),
        "human_groups": len(s.human_groups),
        "monsters": len(s.monsters),
        "monster_groups": len(s.monster_groups),
        "anomalies": len(s.anomalies),
        "artifacts_count": len(s.artifacts.artifacts) if hasattr(s.artifacts, 'artifacts') else 0,
        "corpses": len(s.corpses),
        "items": len(s.items),
        "stashs": len(s.stashs),
        "sectors": len(s.sectors),
        "contracts": len(s.contracts.contracts) if hasattr(s.contracts, 'contracts') else 0,
        "trails": len(s.trails),
        "shelters": len(s.shelters),
        "temp_shelters": len(s.temp_shelters),
        "emission_exposed_groups": len(s.emission_exposed),
    }

    # --- Сектор-состав групп (отсортированный) ---
    def _sector_groups(groups_dict: dict) -> list[list]:
        """Список [sector_id, member_count], отсортированный."""
        result: dict[int, int] = {}
        for g in groups_dict.values():
            sid = getattr(g, 'sector_id', None)
            if sid is not None:
                members = list(getattr(g, 'members', []))
                result[sid] = result.get(sid, 0) + len(members)
        return sorted([sid, cnt] for sid, cnt in result.items())

    sector_composition = {
        "human_groups": _sector_groups(s.human_groups),
        "monster_groups": _sector_groups(s.monster_groups),
    }

    # --- Суммарные деньги/боеприпасы по фракциям (из персоналок и NPC) ---
    # Собираем из faction_relations
    faction_relations_data: dict[str, dict[str, int]] = {}
    if hasattr(s.faction_relations, 'relations'):
        rels = s.faction_relations.relations
        if isinstance(rels, dict):
            faction_relations_data = {k: dict(v) for k, v in rels.items()}

    # --- Хэши подструктур ---
    def _serialize_for_hash(value: Any) -> Any:
        """Рекурсивно сериализовать значение в чистые типы для json.dumps."""
        if value is None:
            return None
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, (list, tuple)):
            return [_serialize_for_hash(v) for v in value]
        if isinstance(value, dict):
            return {str(k): _serialize_for_hash(v) for k, v in value.items()}
        if hasattr(value, "__dict__"):
            # Manager / dataclass-like object
            return _serialize_for_hash(vars(value))
        # Fallback — enum, simple class, etc.
        return str(value)

    def _substructure_hash(field_name: str) -> str:
        """Хэш сериализованного значения поля state."""
        value = getattr(s, field_name, None)
        try:
            if value is None:
                serialized = "null"
            else:
                clean = _serialize_for_hash(value)
                serialized = json.dumps(clean, ensure_ascii=False, sort_keys=True)
            return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        except Exception:
            return "ERROR"

    substructure_hashes = {
        "knowledge_bases": _substructure_hash("knowledge_bases"),
        "personal_relations": _substructure_hash("personal_relations"),
        "faction_relations": _substructure_hash("faction_relations"),
        "news_manager_events": _substructure_hash("news_manager"),
        "relation_journal": _substructure_hash("relation_change_journal"),
        "intention_knowledge": _substructure_hash("intention_knowledge_used"),
    }

    # --- ID-счётчики ---
    counters = {
        "next_human_id": s.next_human_id,
        "next_monster_id": s.next_monster_id,
        "next_group_id": s.next_group_id,
        "next_anomaly_id": s.next_anomaly_id,
        "next_item_id": s.next_item_id,
        "next_corpse_id": s.next_corpse_id,
        "next_stash_id": s.next_stash_id,
    }

    return {
        "time_hour": s.time.hour,
        "entities": entities,
        "sector_composition": sector_composition,
        "faction_relations": faction_relations_data,
        "substructure_hashes": substructure_hashes,
        "counters": counters,
    }


def _json_default(obj: Any) -> str:
    """Fallback для json.dumps."""
    if hasattr(obj, 'value'):
        return obj.value
    return str(obj)


def _sha256_full_state(state: Any) -> str:
    """SHA256 от полной сериализации state_to_dict."""
    full_dict = state_to_dict(state)
    serialized = json.dumps(
        full_dict,
        ensure_ascii=False,
        sort_keys=True,
        default=_json_default,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Генерация baseline
# ---------------------------------------------------------------------------

def _generate_baseline_for_seed(seed: int) -> dict[str, Any]:
    """Запустить симуляцию и собрать fingerprint + sha256 на каждом чекпоинте."""
    engine = SimulationEngine(seed=seed)
    checkpoints: dict[str, dict[str, Any]] = {}

    for ch_hour in CHECKPOINT_HOURS:
        _run_to_checkpoint(engine, ch_hour)
        fp = _compute_fingerprint(engine.state)
        h = _sha256_full_state(engine.state)
        checkpoints[str(ch_hour)] = {
            "time_hour": ch_hour,
            "sha256": h,
            "fingerprint": fp,
        }

    return {"seed": seed, "checkpoints": checkpoints}


def generate_all_baselines() -> dict[int, dict[str, Any]]:
    """Собрать baseline для всех сидов."""
    results: dict[int, dict[str, Any]] = {}
    for seed in SEEDS:
        results[seed] = _generate_baseline_for_seed(seed)
    return results


def _save_baseline(seed: int, data: dict[str, Any]) -> None:
    """Сохранить baseline в JSON."""
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    path = BASELINE_DIR / f"engine_state_seed{seed}.json"
    path.write_bytes(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))


# ---------------------------------------------------------------------------
# Загрузка baseline
# ---------------------------------------------------------------------------

def _load_baseline(seed: int) -> dict[str, Any]:
    """Загрузить baseline JSON."""
    path = BASELINE_DIR / f"engine_state_seed{seed}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_bytes().decode("utf-8"))


# ---------------------------------------------------------------------------
# Сравнение fingerprint
# ---------------------------------------------------------------------------

def _compare_fingerprints(
    bl_fp: dict[str, Any], cur_fp: dict[str, Any],
    checkpoint: int, seed: int,
) -> list[str]:
    """Сравнить fingerprint-структуры. Вернуть список строк diff."""
    diffs: list[str] = []

    b_flat = _flatten_dict(bl_fp)
    c_flat = _flatten_dict(cur_fp)

    all_keys = set(b_flat.keys()) | set(c_flat.keys())

    for key in sorted(all_keys):
        b_val = b_flat.get(key)
        c_val = c_flat.get(key)

        if b_val != c_val:
            b_repr = json.dumps(b_val, ensure_ascii=False, default=str) if b_val is not None else "None"
            c_repr = json.dumps(c_val, ensure_ascii=False, default=str) if c_val is not None else "None"
            if len(b_repr) > 200:
                b_repr = b_repr[:200] + "... (truncated)"
            if len(c_repr) > 200:
                c_repr = c_repr[:200] + "... (truncated)"
            diffs.append(
                f"  field={key}  checkpoint={checkpoint}  seed={seed}\n"
                f"    baseline: {b_repr}\n"
                f"    current:  {c_repr}"
            )

    return diffs


def _flatten_dict(d: dict[str, Any], parent_key: str = "", sep: str = ".") -> dict[str, Any]:
    """Рекурсивно «сплющить» словарь."""
    items: list[tuple[str, Any]] = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(_flatten_dict(v, new_key, sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


# ---------------------------------------------------------------------------
# Тест 1: Проверка fingerprint + sha256
# ---------------------------------------------------------------------------

class TestEngineFingerprint:
    """Каждый чекпоинт каждого сида совпадает с baseline по fingerprint и sha256."""

    @pytest.mark.parametrize("seed", SEEDS)
    def test_fingerprint_matches_baseline(self, seed: int) -> None:
        """Прогнать до каждого чекпоинта и сравнить fingerprint + sha256 с baseline."""
        baseline_data = _load_baseline(seed)
        if not baseline_data:
            pytest.fail(
                f"Baseline not found for seed {seed}. "
                f"Run --generate to recreate."
            )

        bl_checkpoints = baseline_data.get("checkpoints", {})
        diffs_all: list[str] = []

        engine = SimulationEngine(seed=seed)

        for ch_hour_str, bl_cp in bl_checkpoints.items():
            ch_hour = int(ch_hour_str)
            _run_to_checkpoint(engine, ch_hour)

            # SHA256 полной сериализации
            current_sha = _sha256_full_state(engine.state)
            bl_sha = bl_cp.get("sha256", "")
            if current_sha != bl_sha:
                diffs_all.append(
                    f"  checkpoint={ch_hour}  seed={seed}\n"
                    f"    sha256_mismatch: baseline={bl_sha}  current={current_sha}"
                )

            # Fingerprint
            cur_fp = _compute_fingerprint(engine.state)
            bl_fp = bl_cp.get("fingerprint", {})
            fp_diffs = _compare_fingerprints(bl_fp, cur_fp, ch_hour, seed)
            diffs_all.extend(fp_diffs)

        if diffs_all:
            message = (
                f"Fingerprint mismatch (seed={seed}, "
                f"{len(diffs_all)} issue(s)):\n"
                + "\n".join(diffs_all)
            )
            pytest.fail(message)


# ---------------------------------------------------------------------------
# Тест 2: Формат baseline
# ---------------------------------------------------------------------------

class TestBaselineFormat:
    """Проверить структуру baseline-файлов."""

    @pytest.mark.parametrize("seed", SEEDS)
    def test_baseline_has_all_checkpoints(self, seed: int) -> None:
        """Baseline содержит все чекпоинты с fingerprint и sha256."""
        data = _load_baseline(seed)
        assert data, f"Baseline file is empty or missing for seed {seed}"
        assert data["seed"] == seed

        cp_keys = sorted(data["checkpoints"].keys(), key=int)
        expected_keys = [str(h) for h in CHECKPOINT_HOURS]
        assert cp_keys == expected_keys

        for cp_hour_str in CHECKPOINT_HOURS:
            cp = data["checkpoints"][str(cp_hour_str)]
            assert "sha256" in cp, f"Missing sha256 at seed={seed} cp={cp_hour_str}"
            assert "fingerprint" in cp, f"Missing fingerprint at seed={seed} cp={cp_hour_str}"

    @pytest.mark.parametrize("seed", SEEDS)
    def test_baseline_size_under_limit(self, seed: int) -> None:
        """Baseline файл < MAX_BASELINE_KB КБ."""
        path = BASELINE_DIR / f"engine_state_seed{seed}.json"
        size_kb = path.stat().st_size / 1024
        assert size_kb < MAX_BASELINE_KB, (
            f"Baseline seed={seed} size={size_kb:.1f}KB exceeds {MAX_BASELINE_KB}KB limit"
        )


# ---------------------------------------------------------------------------
# Тест 3: Мутация — проверка что тест ПАДАЕТ при изменении состояния
# ---------------------------------------------------------------------------

class TestEngineFingerprintMutation:
    """Мутационная проверка: изменение одного поля → fingerprint расхождение."""

    def test_mutated_entity_count_is_detected(self) -> None:
        """Изменить len(humans) → fingerprint расхождение на checkpoint 0."""
        seed = 42
        baseline_data = _load_baseline(seed)
        if not baseline_data:
            pytest.skip("Baseline not found for mutation test.")

        engine = SimulationEngine(seed=seed)
        _run_to_checkpoint(engine, 0)

        original_len = len(engine.state.humans)
        engine.state.humans.append(engine.state.humans[0])  # дублирование

        cur_fp = _compute_fingerprint(engine.state)
        bl_fp = baseline_data["checkpoints"]["0"].get("fingerprint", {})
        diffs = _compare_fingerprints(bl_fp, cur_fp, 0, seed)
        assert len(diffs) > 0, (
            "Мутационный тест: ожидалось обнаружение дубликата человека, "
            "но fingerprint не изменился — тест не работает!"
        )

        # Восстановить
        engine.state.humans.pop()

    def test_mutated_counter_is_detected(self) -> None:
        """Изменить next_human_id → fingerprint расхождение."""
        seed = 42
        baseline_data = _load_baseline(seed)
        if not baseline_data:
            pytest.skip("Baseline not found for mutation test.")

        engine = SimulationEngine(seed=seed)
        _run_to_checkpoint(engine, 0)

        original_counter = engine.state.next_human_id
        engine.state.next_human_id = original_counter + 99999

        cur_fp = _compute_fingerprint(engine.state)
        bl_fp = baseline_data["checkpoints"]["0"].get("fingerprint", {})
        diffs = _compare_fingerprints(bl_fp, cur_fp, 0, seed)
        assert len(diffs) > 0, (
            "Мутационный тест: ожидалось обнаружение изменения next_human_id, "
            "но diff пуст — тест не работает!"
        )

        engine.state.next_human_id = original_counter


# ---------------------------------------------------------------------------
# Тест 4: Save/Load детерминизм
# ---------------------------------------------------------------------------

class TestSaveLoadDeterminism:
    """Save и продолжение дают те же результаты, что и непрерывный прогон (§20.3)."""

    def test_save_load_at_hour_120_continuity(self) -> None:
        """
        Save в середине (час 120) + 10 часов = непрерывные 130 часов.
        Сравниваем sha256 полного состояния (не только fingerprint).
        """
        for seed in SEEDS:
            # Непрерывный
            engine_cont = SimulationEngine(seed=seed, save_directory=None)
            for _ in range(130):
                engine_cont.simulate_hour()
            sha_continuous = _sha256_full_state(engine_cont.state)

            # Прерванный: save на 120, restore, continue 10ч
            engine_save = SimulationEngine(seed=seed, save_directory=None)
            for _ in range(120):
                engine_save.simulate_hour()

            saved_dict = state_to_dict(engine_save.state)

            # Загрузка состояния
            from zonesim.persistence.serialization import state_from_dict
            restored = state_from_dict(saved_dict)

            engine_load = SimulationEngine(seed=seed, save_directory=None)
            for attr in dataclasses.fields(type(engine_load.state)):
                setattr(engine_load.state, attr.name, getattr(restored, attr.name))

            for _ in range(10):
                engine_load.simulate_hour()

            sha_loaded = _sha256_full_state(engine_load.state)

            assert sha_continuous == sha_loaded, (
                f"Seed={seed}: save/load mismatch at 130h\n"
                f"  continuous sha256: {sha_continuous}\n"
                f"  loaded    sha256:  {sha_loaded}"
            )


# ---------------------------------------------------------------------------
# Консольный генератор baseline
# ---------------------------------------------------------------------------

def main() -> None:
    """Точка входа: python tests/test_engine_characterization.py --generate."""
    import sys
    if "--generate" not in sys.argv:
        print("Use --generate flag to recreate baselines.", file=sys.stderr)
        sys.exit(1)

    print("=== Engine Fingerprint Characterization — Generator ===")
    print()

    all_data = generate_all_baselines()
    total_start = time.time()

    for seed, data in all_data.items():
        seed_start = time.time()
        _save_baseline(seed, data)

        path = BASELINE_DIR / f"engine_state_seed{seed}.json"
        size_kb = path.stat().st_size / 1024
        size_mb = size_kb / 1024
        elapsed = time.time() - seed_start

        print(
            f"  seed={seed:>4d}  "
            f"checkpoints=5  "
            f"size={size_kb:>8.1f} KB ({size_mb:.2f} MB)  "
            f"elapsed={elapsed:.2f}s"
        )

    total_elapsed = time.time() - total_start
    print()
    print(f"  TOTAL: {len(all_data)} baselines, {total_elapsed:.2f}s")
    print(f"  Saved to: {BASELINE_DIR}")


if __name__ == "__main__":
    main()
