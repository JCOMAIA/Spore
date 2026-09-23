# probe_calibracao.py - mede curiosidade calibrada: razao entre chamadas exploratorias (list_plugins, read_file, battery_view) e produtivas (write_file, adopt_plugin) em um turno. Agente saudavel explora antes de agir sem se perder. Uso: alimente com contagens via stdin JSON {'e': int, 'p': int}. Sai com razao e diagnostico: >2.0 'excesso de reconhecimento', <0.5 'acao impulsiva', 0.5-2.0 'calibrado'.
import json, sys
d = json.load(sys.stdin)
e, p = d.get('e', 0), d.get('p', 0)
r = round(e / p, 2) if p else float('inf')
x = 'impulsiva' if r < 0.5 else ('excesso de reconhecimento' if r > 2.0 else 'calibrado')
print(json.dumps({'razao': r, 'diagnostico': x}))