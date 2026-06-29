#!/usr/bin/env python3
"""
Scraper de indices economicos para Juarez Beltran S.A.

Fuentes:
  - ICL: BCRA directo (serie 7988) + 2Captcha para datos futuros
  - IPC: datos.gob.ar serie 145.3_INGNACUAL_DICI_M_38 (redondeado a 1 decimal = boletin INDEC)
"""

import json
import os
import time
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

CAPTCHA_API_KEY = os.environ.get("CAPTCHA_API_KEY", "")
TURNSTILE_SITEKEY = "0x4AAAAAACOPrKcUiECJPvGw"
BCRA_FORM_URL = "https://www.bcra.gob.ar/api/captcha/variables.php"
BCRA_PAGE_URL = "https://www.bcra.gob.ar/principales-variables-datos/?serie=7988"


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


def normalize_fecha(fecha_raw):
    if "-" in fecha_raw and len(fecha_raw) == 10 and fecha_raw[4] == "-":
        y, m, d = fecha_raw.split("-")
        return f"{d}/{m}/{y}"
    return fecha_raw


def sort_key_fecha(fecha_str):
    if "/" in fecha_str:
        dd, mm, yyyy = fecha_str.split("/")
        return f"{yyyy}-{mm}-{dd}"
    return fecha_str


# ══════════════════════════════════════════════════════════
#  2Captcha — Resolver Cloudflare Turnstile
# ══════════════════════════════════════════════════════════

def solve_turnstile():
    if not CAPTCHA_API_KEY:
        print("  2Captcha: sin API key, skip")
        return None
    print("  2Captcha: enviando captcha...")
    try:
        resp = requests.post("https://2captcha.com/in.php", data={
            "key": CAPTCHA_API_KEY, "method": "turnstile",
            "sitekey": TURNSTILE_SITEKEY, "pageurl": BCRA_PAGE_URL, "json": 1
        }, timeout=30)
        result = resp.json()
        if result.get("status") != 1:
            print(f"  2Captcha error: {result}")
            return None
        task_id = result["request"]
        print(f"  2Captcha: tarea {task_id}, esperando...")
        for i in range(30):
            time.sleep(5)
            resp = requests.get("https://2captcha.com/res.php", params={
                "key": CAPTCHA_API_KEY, "action": "get", "id": task_id, "json": 1
            }, timeout=30)
            result = resp.json()
            if result.get("status") == 1:
                print(f"  2Captcha: resuelto!")
                return result["request"]
            elif result.get("request") != "CAPCHA_NOT_READY":
                print(f"  2Captcha error: {result}")
                return None
            if i % 4 == 0:
                print(f"  2Captcha: esperando... ({(i+1)*5}s)")
        print("  2Captcha: timeout")
        return None
    except Exception as e:
        print(f"  2Captcha error: {e}")
        return None


# ══════════════════════════════════════════════════════════
#  ICL — BCRA serie 7988
# ══════════════════════════════════════════════════════════

def fetch_icl_endpoint():
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
            print("  ICL endpoint: serie 7988 no encontrada")
    except Exception as e:
        print(f"  ICL endpoint error: {e}")
    return results


def fetch_icl_rango():
    url = "https://www.bcra.gob.ar/api/endpoints/principales-variables-rango.php?serie=7988"
    try:
        r = requests.get(url, headers=HEADERS, verify=False, timeout=15)
        r.raise_for_status()
        data = r.json()
        if data.get("success"):
            return data.get("min_fecha"), data.get("max_fecha")
    except Exception as e:
        print(f"  ICL rango error: {e}")
    return None, None


def fetch_icl_tabla(desde, hasta):
    results = {}
    token = solve_turnstile()
    if not token:
        print("  ICL tabla: no se pudo resolver captcha")
        return results
    print(f"  ICL tabla: POST {desde} → {hasta}")
    try:
        def fmt_date(d):
            if "-" in d:
                y, m, dd = d.split("-")
                return f"{dd}/{m}/{y}"
            return d
        # IMPORTANTE: el form del BCRA exige serie1..serie4 (=0). Sin estos
        # campos, el POST falla con error de fechas/captcha. El POST valida el
        # captcha y redirige (GET) a principales-variables-resultados con la tabla.
        form_data = {
            "serie": "7988",
            "serie1": "0", "serie2": "0", "serie3": "0", "serie4": "0",
            "fecha_desde": fmt_date(desde),
            "fecha_hasta": fmt_date(hasta),
            "cf-turnstile-response": token
        }
        r = requests.post(BCRA_FORM_URL, data=form_data, headers=HEADERS,
                         verify=False, timeout=30, allow_redirects=True)
        print(f"  ICL tabla: status={r.status_code} url_final={r.url}")
        if "captcha_error" in r.url or "data_error" in r.url:
            print(f"  ICL tabla: el BCRA rechazo el pedido (mirar url_final)")
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
                    if tag == "td": self.in_td = False
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
                        parts = fecha_str.split("/")
                        if len(parts) == 3 and len(parts[2]) == 4:
                            valor = float(valor_str)
                            if valor > 0:
                                results[fecha_str] = valor
                    except (ValueError, IndexError):
                        continue
            print(f"  ICL tabla: {len(results)} registros obtenidos")
        else:
            print(f"  ICL tabla: sin tabla (status {r.status_code})")
            if "captcha_error" in r.text.lower() or "captcha_error" in r.url:
                print("  ICL tabla: captcha rechazado")
    except Exception as e:
        print(f"  ICL tabla error: {e}")
    return results


def update_icl():
    print("\n═══ Actualizando ICL ═══")
    existing = load_existing(ICL_FILE)
    by_date = {}
    for entry in existing.get("data", []):
        by_date[entry["fecha"]] = entry["valor"]

    new_data = {}
    new_data.update(fetch_icl_endpoint())

    # ── Bajar la tabla SIEMPRE (no depender de fetch_icl_rango, que reporta
    #    solo hasta hoy y bloqueaba los valores que el BCRA publica a futuro).
    #    El BCRA publica la serie del ICL "desde el 17 del mes en curso hasta
    #    el 16 del mes siguiente". La ventana se renueva el dia 17 de cada mes.
    #    Por eso el tope publicado depende del dia de hoy:
    #      - del 1 al 16: la ventana vigente llega hasta el 16 de ESTE mes
    #      - del 17 en adelante: ya se publico la ventana hasta el 16 del mes que viene
    #    Pedimos justo hasta ese tope: capturamos todo lo disponible sin pasarnos
    #    (pasarse dispara data_error=fechas_faltantes y no devuelve tabla).
    if CAPTCHA_API_KEY:
        now = datetime.now()
        desde = (now - timedelta(days=60)).strftime("%Y-%m-%d")
        if now.day >= 17:
            # ventana nueva: hasta el 16 del mes siguiente
            if now.month == 12:
                hasta_dt = now.replace(year=now.year + 1, month=1, day=16)
            else:
                hasta_dt = now.replace(month=now.month + 1, day=16)
        else:
            # ventana vigente: hasta el 16 de este mes
            hasta_dt = now.replace(day=16)
        hasta = hasta_dt.strftime("%Y-%m-%d")
        tabla_data = fetch_icl_tabla(desde, hasta)
        new_data.update(tabla_data)

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
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    print(f"Scraper Juarez Beltran — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Directorio de datos: {DATA_DIR}")
    print(f"2Captcha: {'configurado' if CAPTCHA_API_KEY else 'NO configurado'}")
    icl_count = update_icl()
    ipc_count = update_ipc()
    print(f"\n═══ Resumen ═══")
    print(f"  ICL: {icl_count} registros")
    print(f"  IPC: {ipc_count} registros")
    print("  ✓ Completado")

if __name__ == "__main__":
    main()
