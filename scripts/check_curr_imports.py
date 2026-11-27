with open('src/zonesim/simulation/engine.py', encoding='utf-8') as f:
    for i, line in enumerate(f, start=1):
        if 'emission' in line.lower() or 'migration' in line.lower():
            print(f'{i}: {line.rstrip()}')
