#!/usr/bin/env python3
"""
Scraper de indices economicos para Juarez Beltran S.A.

Fuentes:
  - ICL: API oficial del BCRA (estadisticas v4.0, idVariable 40). Sin captcha,
         sin autenticacion. Trae TODOS los dias (fines de semana incluidos) y
         los valores a futuro que el BCRA ya publico (hasta el 16 del mes
         siguiente, ventana que se renueva el 17 de cada mes).
  - IPC: datos.gob.ar serie 145.3_INGNACUAL_DICI_M_38 (redondeado a 1 decimal = boletin INDEC)
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

import requests

# ── Configuracion ──
DATA_DIR = Path(__file__).parent / "data"
ICL_FILE = DATA_DIR / "icl.json"
IPC_FILE = DATA_DIR / "ipc.json"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

BCRA_API = "https://api.bcra.gob.ar/estadisticas/v4.0/monetarias"
ICL_ID_VARIABLE = 40          # "Indice para Contratos de Locacion (ICL)"
ICL_DIAS_ATRAS = 60           # re-pedimos los ultimos 60 dias por si el BCRA corrige
ICL_DIAS_ADELANTE = 45        # cubre la ventana publicada a futuro (hasta el 16 del mes siguiente)


def load_existing(filepath):
    if filepath.exists():
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"data": []}


def save_json(filepath, data):
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  ✓ Guardado {filepath} ({len(data.get('data', []))} registros)")


def iso_to_ddmmyyyy(fecha_iso):
    y, m, d = fecha_iso[:10].split("-")
    return f"{d}/{m}/{y}"


def sort_key_fecha(fecha_str):
    if "/" in fecha_str:
        dd, mm, yyyy = fecha_str.split("/")
        return f"{yyyy}-{mm}-{dd}"
    return fecha_str


# ══════════════════════════════════════════════════════════
#  ICL — API BCRA v4.0 (idVariable 40)
# ══════════════════════════════════════════════════════════

def fetch_icl_api(desde, hasta):
    """
    Devuelve {"dd/mm/yyyy": valor} con todos los dias publicados en el rango.
    La API devuelve como maximo 1000 registros por llamada; para 105 dias sobra.
    """
    url = f"{BCRA_API}/{ICL_ID_VARIABLE}"
    params = {"desde": desde, "hasta": hasta, "limit": 1000}
    results = {}
    print(f"  ICL API: GET {desde} → {hasta}")
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=30)
        r.raise_for_status()
        data = r.json()
        if data.get("status") != 200:
            print(f"  ICL API: status inesperado {data.get('status')} {data.get('errorMessages', '')}")
            return results
        for serie in data.get("results", []):
            if serie.get("idVariable") != ICL_ID_VARIABLE:
                continue
            for d in serie.get("detalle", []):
                valor = d.get("valor")
                if valor is None:
                    continue
                results[iso_to_ddmmyyyy(d["fecha"])] = round(float(valor), 2)
        if results:
            fechas = sorted(results, key=sort_key_fecha)
            print(f"  ICL API: {len(results)} registros ({fechas[0]} → {fechas[-1]})")
        else:
            print("  ICL API: sin registros en el rango")
    except Exception as e:
        print(f"  ICL API error: {e}")
    return results


def update_icl():
    print("\n═══ Actualizando ICL ═══")
    existing = load_existing(ICL_FILE)
    by_date = {}
    for entry in existing.get("data", []):
        by_date[entry["fecha"]] = entry["valor"]

    now = datetime.now()
    desde = (now - timedelta(days=ICL_DIAS_ATRAS)).strftime("%Y-%m-%d")
    hasta = (now + timedelta(days=ICL_DIAS_ADELANTE)).strftime("%Y-%m-%d")
    new_data = fetch_icl_api(desde, hasta)

    if not new_data:
        print("  Sin datos nuevos, manteniendo archivo existente")
        return len(by_date)

    added = updated = 0
    for fecha, valor in new_data.items():
        if fecha not in by_date:
            by_date[fecha] = valor
            added += 1
        elif abs(by_date[fecha] - valor) > 0.001:
            by_date[fecha] = valor
            updated += 1

    print(f"  Nuevos: {added}, Actualizados: {updated}, Total: {len(by_date)}")
    sorted_data = [
        {"fecha": f, "valor": v}
        for f, v in sorted(by_date.items(), key=lambda x: sort_key_fecha(x[0]))
    ]
    result = {
        "meta": {
            "fuente": "BCRA API estadisticas v4.0, idVariable 40 (ex serie 7988)",
            "descripcion": "Indice para Contratos de Locacion (ICL)",
            "frecuencia": "diaria",
            "ultima_actualizacion": now.strftime("%Y-%m-%d %H:%M:%S")
        },
        "data": sorted_data
    }
    save_json(ICL_FILE, result)
    return len(sorted_data)


# ══════════════════════════════════════════════════════════
#  IPC — datos.gob.ar (variaciones redondeadas = boletin INDEC)
# ══════════════════════════════════════════════════════════

def fetch_ipc():
    """
    Obtiene variaciones mensuales IPC desde datos.gob.ar serie 145.3_INGNACUAL_DICI_M_38.
    Redondea a 1 decimal para coincidir con el boletin oficial del INDEC.
    Acumula en indice base 100.
    """
    url = "https://apis.datos.gob.ar/series/api/series/?ids=145.3_INGNACUAL_DICI_M_38&limit=5000&format=json"
    print("  IPC: consultando datos.gob.ar (variaciones)...")
    results = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        data = r.json()

        # Parsear y redondear a 1 decimal (= boletin INDEC)
        variaciones = []
        for entry in data.get("data", []):
            fecha_str = entry[0]  # "2017-01-01"
            valor = entry[1]
            if valor is None:
                continue
            fecha = fecha_str[:7]  # "2017-01"
            var_pct = round(valor * 100, 1)  # 0.0258... → 2.6
            variaciones.append((fecha, var_pct))

        # Acumular indice base 100
        acum = 100.0
        for fecha, var in variaciones:
            acum = acum * (1 + var / 100)
            results.append({
                "fecha": fecha,
                "indice_ipc": round(acum, 2)
            })

        print(f"  IPC: {len(results)} meses")
        if results:
            last = results[-1]
            print(f"  Ultimo: {last['fecha']} (indice: {last['indice_ipc']})")
    except Exception as e:
        print(f"  IPC error: {e}")
    return results


def update_ipc():
    print("\n═══ Actualizando IPC ═══")
    ipc_data = fetch_ipc()
    if not ipc_data:
        print("  Sin datos IPC, manteniendo archivo existente")
        existing = load_existing(IPC_FILE)
        return len(existing.get("data", []))

    result = {
        "meta": {
            "fuente": "INDEC via datos.gob.ar (variaciones redondeadas = boletin oficial)",
            "serie": "145.3_INGNACUAL_DICI_M_38",
            "descripcion": "IPC Nivel General Nacional, variaciones acumuladas base 100",
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
