import pathlib, re, subprocess, sys, os, hashlib, dataclasses
ROOT = pathlib.Path(__file__).parent
BASE = "2d481f7"   # состояние ДО Батча 4

def run(*a):
    # КРИТИЧНО: кодировка и замена битых символов — для русской локали
    return subprocess.run(list(a), cwd=ROOT, capture_output=True,
                          encoding="utf-8", errors="replace").stdout

def git(*a): return run("git", "-C", str(ROOT), *a)

R=[]
def check(n, ok, d=""): R.append((n,"PASS" if ok else "FAIL",d))

# 1. HEAD
head = git("rev-parse","--short","HEAD").strip()
check("HEAD = 72f6b83", head == "72f6b83", head)
print("=== последние коммиты ===")
print(git("log","--oneline","-5"))

# 2. Размер движка
new = (ROOT/"src/zonesim/simulation/engine.py").read_text(encoding="utf-8")
n_new = len(new.splitlines())
old = git("show", f"{BASE}:src/zonesim/simulation/engine.py")
if old is None or not old.strip():
    print("ОШИБКА: не удалось получить базовый коммит", BASE)
    sys.exit(1)
n_old = len(old.splitlines())
check("engine.py уменьшился", n_new < n_old, f"{n_old} -> {n_new} (delta {n_old-n_new})")

# 3. Что реально удалено из engine (сравнение def-ов)
om = set(re.findall(r'^    def (_\w+)\(', old, re.M))
nm = set(re.findall(r'^    def (_\w+)\(', new, re.M))
removed = sorted(om - nm)
added = sorted(nm - om)
print(f"\n=== УДАЛЕНО из engine при Батче 4 ({len(removed)}) ===")
print("  " + ", ".join(removed) if removed else "  НИЧЕГО")
print(f"\n=== ДОБАВЛЕНО в engine ({len(added)}) ===")
print("  " + ", ".join(added) if added else "  ничего")
check("удалено ~16 методов", 12 <= len(removed) <= 20, f"удалено {len(removed)}")

# 4. Фактический состав Батча 4 из документации
plan = (ROOT/"docs/engine_services_plan.md").read_text(encoding="utf-8")
i = plan.find("Батч 4 — фактический состав")
seg = plan[i:i+4000] if i>=0 else ""
doc_methods = re.findall(r'\| \d+ \| `(_\w+)`', seg)
print(f"\n=== Состав Батча 4 по доку ({len(doc_methods)}) ===")
print("  " + ", ".join(doc_methods))
not_removed = [m for m in doc_methods if m in nm]
check("все методы состава удалены", not not_removed,
      f"остались: {', '.join(not_removed)}" if not_removed else "ок")

# 5. Есть ли функции в доменных модулях (для удалённых)
mods = {p: p.read_text(encoding="utf-8") for p in (ROOT/"src/zonesim").rglob("*.py")
        if "simulation/engine.py" not in str(p)}
missing_fn = []
for m in removed:
    fn = m.lstrip("_")
    if not any(re.search(rf'^def {fn}\b', t, re.M) for t in mods.values()):
        missing_fn.append(m)
check("у каждого удалённого есть функция в модуле", not missing_fn, str(missing_fn))

# 6. Дубликаты (метод в модуле И в engine)
dups = sorted({fn for t in mods.values() for fn in re.findall(r'^def (\w+)\(', t, re.M)
               if re.search(rf'^    def _{fn}\(', new, re.M)})
allowed = {"generate_world","known_anomaly_sectors"}
new_dups = [d for d in dups if d not in allowed]
check("нет новых дубликатов", not new_dups, str(new_dups) if new_dups else "ок")

# 7. Висячие вызовы удалённых методов
dang = []
for d in ["src","tests"]:
    for p in (ROOT/d).rglob("*.py"):
        for i,l in enumerate(p.read_text(encoding="utf-8").splitlines(),1):
            for m in removed:
                if re.search(rf'\.{m}\(', l): dang.append(f"{p.name}:{i} {m}")
check("нет висячих вызовов", not dang, "; ".join(dang[:5]) if dang else "ок")

# 8. Аудит расширен
a = (ROOT/"scripts/audit_service_move.py").read_text(encoding="utf-8")
check("аудит: есть BATCH_B4", "BATCH_B4" in a or '"B4"' in a)
check("аудит: B4_PRE_COMMIT = 2d481f7", "2d481f7" in a)
check("аудит: нет blanket-приёмки", "known_diff" not in a and "Любые расхождения" not in a)

# 9. baseline не изменён
exp = {"engine_state_seed42.json":"febae09ef46cc7ce",
       "engine_state_seed7.json":"681f47ddc8103918",
       "engine_state_seed123.json":"aec39f13625cae13"}
bad = [f for f,h in exp.items()
       if hashlib.sha256((ROOT/"tests/_baseline"/f).read_bytes()).hexdigest()[:16] != h]
check("baseline не изменён", not bad, "; ".join(bad) if bad else "ок")

# 10. Поля state
sys.path.insert(0, str(ROOT/"src")); os.chdir(ROOT)
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
os.environ.setdefault("PYTEST_DISABLE_PLUGIN_AUTOLOAD","1")
from zonesim.simulation.state import SimulationState
nf = len(dataclasses.fields(SimulationState))
check("полей state = 56", nf == 56, str(nf))

# 11. Прогоны
import pytest
print("\n=== характеристика ===")
rc1 = pytest.main(["tests/test_engine_characterization.py","-q","--tb=line","-p","no:cacheprovider"])
check("характеристика 12 passed", rc1 == 0, f"rc={rc1}")

print("=== аудит B4 ===")
rc2 = subprocess.run([sys.executable,"scripts/audit_service_move.py","--batch","B4"],
                     capture_output=True, encoding="utf-8", errors="replace",
                     cwd=ROOT).returncode
check("аудит --batch B4 зелёный", rc2 == 0, f"rc={rc2}")

print("\n=== ПРОВЕРКА БАТЧА 4 ===")
for nm_,st,d in R: print(f"[{st}] {nm_} | {d}")
