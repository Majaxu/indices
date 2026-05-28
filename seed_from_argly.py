#!/usr/bin/env python3
"""
Script seed: genera datos ICL iniciales desde Argly como backup,
por si el BCRA no responde en la primera corrida.
Correr UNA vez localmente para poblar data/icl.json con historico.

Uso: python seed_from_argly.py
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import requests

DATA_DIR = Path(__file__).parent / "data"
ICL_FILE = DATA_DIR / "icl.json"

HEADERS = {"User-Agent": "Mozilla/5.0"}
PROXY = "https://corsproxy.io/?"


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    desde = f"{now.year - 2}-01-01"
    hasta = f"{now.year}-12-31"

    url = f"https://api.argly.com.ar/v1/icl?desde={desde}&hasta={hasta}"
    print(f"Consultando Argly: {url}")

    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        argly_data = r.json()
    except Exception:
        print("Intento directo fallo, probando con proxy CORS...")
        r = requests.get(PROXY + url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        argly_data = r.json()

    # Argly devuelve: {"data": [{"fecha": "01/05/2026", "valor": 32.13}, ...]}
    entries = []
    seen = set()
    for d in argly_data.get("data", []):
        fecha = d["fecha"]
        valor = float(d["valor"])
        if fecha not in seen:
            entries.append({"fecha": fecha, "valor": valor})
            seen.add(fecha)

    # Ordenar por fecha
    def sort_key(entry):
        dd, mm, yyyy = entry["fecha"].split("/")
        return f"{yyyy}-{mm}-{dd}"

    entries.sort(key=sort_key)

    result = {
        "meta": {
            "fuente": "BCRA serie 7988 (via Argly seed)",
            "descripcion": "Indice para Contratos de Locacion (ICL)",
            "frecuencia": "diaria",
            "ultima_actualizacion": now.strftime("%Y-%m-%d %H:%M:%S"),
            "nota": "Datos iniciales via Argly, las actualizaciones posteriores son directas del BCRA"
        },
        "data": entries
    }

    with open(ICL_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"✓ Guardado {ICL_FILE} con {len(entries)} registros ICL")
    print(f"  Rango: {entries[0]['fecha']} → {entries[-1]['fecha']}")


if __name__ == "__main__":
    main()
