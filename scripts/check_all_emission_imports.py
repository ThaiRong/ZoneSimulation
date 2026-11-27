import subprocess

result = subprocess.run(
    ['git', 'show', '2d481f7:src/zonesim/simulation/engine.py'],
    capture_output=True, encoding='utf-8', cwd='C:\\Users\\WinBug\\ZoneSimulation'
)
for i, line in enumerate(result.stdout.splitlines(), start=1):
    if 'emission' in line.lower() or 'migration' in line.lower():
        print(f'{i}: {line}')
