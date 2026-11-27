import subprocess

result = subprocess.run(
    ['git', 'show', '2d481f7:src/zonesim/simulation/engine.py'],
    capture_output=True, encoding='utf-8', cwd='C:\\Users\\WinBug\\ZoneSimulation'
)
lines = result.stdout.splitlines()
for i, line in enumerate(lines[85:105], start=86):
    print(f'{i}: {line}')
