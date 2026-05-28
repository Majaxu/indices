"""
Mergear datos futuros del BCRA (copiados manualmente) en icl.json existente.
Correr una sola vez.
"""
import json
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
ICL_FILE = DATA_DIR / "icl.json"

# Datos del BCRA copiados el 28/05/2026
nuevos_raw = """01/05/2026	32,13
02/05/2026	32,18
03/05/2026	32,22
04/05/2026	32,26
05/05/2026	32,31
06/05/2026	32,35
07/05/2026	32,40
08/05/2026	32,44
09/05/2026	32,48
10/05/2026	32,53
11/05/2026	32,57
12/05/2026	32,61
13/05/2026	32,66
14/05/2026	32,70
15/05/2026	32,75
16/05/2026	32,79
17/05/2026	32,82
18/05/2026	32,85
19/05/2026	32,88
20/05/2026	32,91
21/05/2026	32,94
22/05/2026	32,97
23/05/2026	33,00
24/05/2026	33,03
25/05/2026	33,06
26/05/2026	33,09
27/05/2026	33,12
28/05/2026	33,15
29/05/2026	33,18
30/05/2026	33,21
31/05/2026	33,24
01/06/2026	33,27
02/06/2026	33,31
03/06/2026	33,34
04/06/2026	33,37
05/06/2026	33,40
06/06/2026	33,43
07/06/2026	33,46
08/06/2026	33,49
09/06/2026	33,52
10/06/2026	33,55
11/06/2026	33,58
12/06/2026	33,61
13/06/2026	33,64
14/06/2026	33,67
15/06/2026	33,70
16/06/2026	33,74"""

# Parsear
nuevos = {}
for line in nuevos_raw.strip().split('\n'):
    fecha, valor = line.split('\t')
    nuevos[fecha.strip()] = float(valor.strip().replace(',', '.'))

# Cargar existente
with open(ICL_FILE, "r", encoding="utf-8") as f:
    existing = json.load(f)

by_date = {}
for entry in existing.get("data", []):
    by_date[entry["fecha"]] = entry["valor"]

print(f"Existentes: {len(by_date)}")

# Mergear
added = 0
updated = 0
for fecha, valor in nuevos.items():
    if fecha not in by_date:
        by_date[fecha] = valor
        added += 1
    elif abs(by_date[fecha] - valor) > 0.001:
        by_date[fecha] = valor
        updated += 1

print(f"Nuevos: {added}, Actualizados: {updated}, Total: {len(by_date)}")

# Ordenar
def sort_key(fecha_str):
    if "/" in fecha_str:
        dd, mm, yyyy = fecha_str.split("/")
        return f"{yyyy}-{mm}-{dd}"
    return fecha_str

sorted_data = [
    {"fecha": f, "valor": v}
    for f, v in sorted(by_date.items(), key=lambda x: sort_key(x[0]))
]

result = {
    "meta": {
        "fuente": "BCRA serie 7988",
        "descripcion": "Indice para Contratos de Locacion (ICL)",
        "frecuencia": "diaria",
        "ultima_actualizacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    },
    "data": sorted_data
}

with open(ICL_FILE, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print(f"✓ Guardado {ICL_FILE} con {len(sorted_data)} registros")
print(f"  Primer dato: {sorted_data[0]}")
print(f"  Ultimo dato: {sorted_data[-1]}")
