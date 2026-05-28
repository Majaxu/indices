#!/usr/bin/env python3
"""
Scraper de indices economicos para Juarez Beltran S.A.
Obtiene ICL (BCRA) e IPC (INDEC via datos.gob.ar) y guarda en data/*.json

Fuentes:
  - ICL: endpoint PHP interno del BCRA (serie 7988)
  - ICL historico/futuro: formulario web BCRA con cloudscraper
  - IPC: API datos.gob.ar serie 148.3_INIVELNAL_DICI_M_26
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests

# ── Configuracion ──
DATA_DIR = Path(__file__).parent / "data"
ICL_FILE = DATA_DIR / "icl.json"
IPC_FILE = DATA_DIR / "ipc.json"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def load_existing(filepath):
    """Carga JSON existente o devuelve estructura vacia."""
    if filepath.exists():
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"data": []}


def save_json(filepath, data):
    """Guarda JSON con formato legible."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  ✓ Guardado {filepath} ({len(data.get('data', []))} registros)")


def normalize_fecha(fecha_raw):
    """Normaliza fecha a formato dd/mm/yyyy sin importar si viene como yyyy-mm-dd o dd/mm/yyyy."""
    if "-" in fecha_raw and len(fecha_raw) == 10 and fecha_raw[4] == "-":
        y, m, d = fecha_raw.split("-")
        return f"{d}/{m}/{y}"
    return fecha_raw


def sort_key_fecha(fecha_str):
    """Convierte fecha dd/mm/yyyy o yyyy-mm-dd a string ordenable yyyy-mm-dd."""
    if "/" in fecha_str:
        dd, mm, yyyy = fecha_str.split("/")
        return f"{yyyy}-{mm}-{dd}"
    return fecha_str


# ══════════════════════════════════════════════════════════
#  ICL — Indice para Contratos de Locacion (BCRA serie 7988)
# ══════════════════════════════════════════════════════════

def fetch_icl_endpoint():
    """
    Obtiene valor actual del ICL desde el endpoint PHP interno del BCRA.
    URL: https://www.bcra.gob.ar/api/endpoints/principales-variables-ultimas.php
    Devuelve dict {fecha: valor} con el dato del dia.
    """
    url = "https://www.bcra.gob.ar/api/endpoints/principales-variables-ultimas.php"
    results = {}
    try:
        r = requests.get(url, headers=HEADERS, verify=False, timeout=30)
        r.raise_for_status()
        data = r.json()
        serie = data.get("series", {}).get("7988")
        if serie:
            fecha = normalize_fecha(serie["fecha"])
            valor = float(serie["valor"])
            results[fecha] = valor
            print(f"  ICL endpoint: {fecha} = {valor}")
        else:
            print("  ICL endpoint: serie 7988 no encontrada en respuesta")
    except Exception as e:
        print(f"  ICL endpoint error: {e}")
    return results


def fetch_icl_historico():
    """
    Intenta obtener datos historicos + futuros del formulario web del BCRA.
    URL: https://www.bcra.gob.ar/principales-variables-datos/?serie=7988
    Usa cloudscraper para bypass de Cloudflare.
    Devuelve dict {fecha: valor}.
    """
    results = {}
    try:
        import cloudscraper
        scraper = cloudscraper.create_scraper()

        # Rango: 2 anios atras hasta fin de mes siguiente
        now = datetime.now()
        desde = (now - timedelta(days=730)).strftime("%Y-%m-%d")
        hasta_y = now.year + (1 if now.month == 12 else 0)
        hasta_m = (now.month % 12) + 1
        hasta = f"{hasta_y}-{hasta_m:02d}-28"

        url = f"https://www.bcra.gob.ar/principales-variables-datos/?serie=7988&desde={desde}&hasta={hasta}"
        print(f"  ICL historico: consultando {url}")
        r = scraper.get(url, timeout=30)

        if r.status_code == 200 and "<table" in r.text.lower():
            from html.parser import HTMLParser

            class TableParser(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.in_td = False
                    self.cells = []
                    self.current_row = []

                def handle_starttag(self, tag, attrs):
                    if tag == "td":
                        self.in_td = True
                        self.current_row.append("")

                def handle_endtag(self, tag):
                    if tag == "td":
                        self.in_td = False
                    elif tag == "tr" and self.current_row:
                        self.cells.append(self.current_row)
                        self.current_row = []

                def handle_data(self, data):
                    if self.in_td and self.current_row:
                        self.current_row[-1] += data.strip()

            parser = TableParser()
            parser.feed(r.text)

            for row in parser.cells:
                if len(row) >= 2:
                    fecha_str = normalize_fecha(row[0].strip())
                    valor_str = row[1].strip().replace(".", "").replace(",", ".")
                    try:
                        # Validar fecha dd/mm/yyyy
                        parts = fecha_str.split("/")
                        if len(parts) == 3 and len(parts[2]) == 4:
                            valor = float(valor_str)
                            if valor > 0:
                                results[fecha_str] = valor
                    except (ValueError, IndexError):
                        continue

            print(f"  ICL historico: {len(results)} registros obtenidos")
        else:
            print(f"  ICL historico: respuesta no contiene tabla (status {r.status_code})")

    except ImportError:
        print("  ICL historico: cloudscraper no disponible, skip")
    except Exception as e:
        print(f"  ICL historico error: {e}")

    return results


def update_icl():
    """Actualiza icl.json mergeando datos nuevos con historico."""
    print("\n═══ Actualizando ICL ═══")
    existing = load_existing(ICL_FILE)

    # Indexar existentes por fecha para evitar duplicados
    by_date = {}
    for entry in existing.get("data", []):
        by_date[entry["fecha"]] = entry["valor"]

    # Obtener nuevos datos
    new_data = {}
    new_data.update(fetch_icl_historico())
    new_data.update(fetch_icl_endpoint())  # endpoint tiene prioridad (mas reciente)

    added = 0
    updated = 0
    for fecha, valor in new_data.items():
        if fecha not in by_date:
            by_date[fecha] = valor
            added += 1
        elif by_date[fecha] != valor:
            by_date[fecha] = valor
            updated += 1

    print(f"  Nuevos: {added}, Actualizados: {updated}, Total: {len(by_date)}")

    # Ordenar por fecha
    sorted_data = [
        {"fecha": f, "valor": v}
        for f, v in sorted(by_date.items(), key=lambda x: sort_key_fecha(x[0]))
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
    save_json(ICL_FILE, result)
    return len(sorted_data)


# ══════════════════════════════════════════════════════════
#  IPC — Indice de Precios al Consumidor (INDEC)
# ══════════════════════════════════════════════════════════

def fetch_ipc():
    """
    Obtiene IPC Nivel General Nacional desde datos.gob.ar.
    Serie: 148.3_INIVELNAL_DICI_M_26 (base dic 2016 = 100, mensual)
    Tambien obtiene variacion porcentual mensual.
    """
    results = []

    # 1. Valores absolutos del indice
    url_abs = "https://apis.datos.gob.ar/series/api/series/?ids=148.3_INIVELNAL_DICI_M_26&limit=5000&format=json"
    print(f"  IPC absoluto: consultando datos.gob.ar")
    try:
        r = requests.get(url_abs, headers=HEADERS, timeout=30)
        r.raise_for_status()
        data = r.json()
        series = data.get("data", [])

        # 2. Variaciones porcentuales
        url_pct = "https://apis.datos.gob.ar/series/api/series/?ids=148.3_INIVELNAL_DICI_M_26&limit=5000&format=json&representation_mode=percent_change"
        r2 = requests.get(url_pct, headers=HEADERS, timeout=30)
        r2.raise_for_status()
        pct_data = r2.json()
        pct_map = {}
        for entry in pct_data.get("data", []):
            if entry[1] is not None:
                pct_map[entry[0]] = round(entry[1] * 100, 2)  # como porcentaje

        MESES = [
            "", "enero", "febrero", "marzo", "abril", "mayo", "junio",
            "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
        ]

        for entry in series:
            fecha_str = entry[0]  # "2017-01-01"
            valor = entry[1]
            if valor is None:
                continue
            y, m, _ = fecha_str.split("-")
            mes_num = int(m)
            results.append({
                "fecha": fecha_str[:7],  # "2017-01"
                "anio": int(y),
                "mes": mes_num,
                "nombre_mes": MESES[mes_num],
                "indice_ipc": round(valor, 2),
                "variacion_pct": pct_map.get(fecha_str)
            })

        print(f"  IPC: {len(results)} meses obtenidos")

    except Exception as e:
        print(f"  IPC error: {e}")

    return results


def update_ipc():
    """Actualiza ipc.json con datos frescos."""
    print("\n═══ Actualizando IPC ═══")

    ipc_data = fetch_ipc()

    if not ipc_data:
        print("  Sin datos IPC, manteniendo archivo existente")
        existing = load_existing(IPC_FILE)
        return len(existing.get("data", []))

    result = {
        "meta": {
            "fuente": "INDEC via datos.gob.ar",
            "serie": "148.3_INIVELNAL_DICI_M_26",
            "descripcion": "IPC Nivel General Nacional, base dic 2016 = 100",
            "frecuencia": "mensual",
            "ultima_actualizacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        },
        "data": ipc_data
    }
    save_json(IPC_FILE, result)
    return len(ipc_data)


# ══════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════

def main():
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    print(f"Scraper Juarez Beltran — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Directorio de datos: {DATA_DIR}")

    icl_count = update_icl()
    ipc_count = update_ipc()

    print(f"\n═══ Resumen ═══")
    print(f"  ICL: {icl_count} registros")
    print(f"  IPC: {ipc_count} registros")
    print("  ✓ Completado")


if __name__ == "__main__":
    main()
