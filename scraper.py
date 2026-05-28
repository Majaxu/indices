#!/usr/bin/env python3
"""
Scraper de indices economicos para Juarez Beltran S.A.
Obtiene ICL (BCRA) e IPC (INDEC via datos.gob.ar) y guarda en data/*.json

Fuentes:
  - ICL diario: endpoint PHP interno del BCRA (serie 7988)
  - ICL historico/futuro: formulario web BCRA con 2Captcha para Turnstile
  - IPC: API datos.gob.ar serie 148.3_INIVELNAL_DICI_M_26
"""

import json
import os
import sys
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

# 2Captcha API key (desde variable de entorno o GitHub Secret)
CAPTCHA_API_KEY = os.environ.get("CAPTCHA_API_KEY", "")

# Turnstile sitekey del BCRA (descubierto en el HTML)
TURNSTILE_SITEKEY = "0x4AAAAAACOPrKcUiECJPvGw"
BCRA_FORM_URL = "https://www.bcra.gob.ar/api/captcha/variables.php"
BCRA_PAGE_URL = "https://www.bcra.gob.ar/principales-variables-datos/?serie=7988"


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
    """Normaliza fecha a formato dd/mm/yyyy."""
    if "-" in fecha_raw and len(fecha_raw) == 10 and fecha_raw[4] == "-":
        y, m, d = fecha_raw.split("-")
        return f"{d}/{m}/{y}"
    return fecha_raw


def sort_key_fecha(fecha_str):
    """Convierte fecha dd/mm/yyyy o yyyy-mm-dd a string ordenable."""
    if "/" in fecha_str:
        dd, mm, yyyy = fecha_str.split("/")
        return f"{yyyy}-{mm}-{dd}"
    return fecha_str


# ══════════════════════════════════════════════════════════
#  2Captcha — Resolver Cloudflare Turnstile
# ══════════════════════════════════════════════════════════

def solve_turnstile():
    """
    Resuelve Cloudflare Turnstile via 2Captcha.
    Devuelve el token o None si falla.
    """
    if not CAPTCHA_API_KEY:
        print("  2Captcha: sin API key, skip")
        return None

    print("  2Captcha: enviando captcha...")
    try:
        # Paso 1: enviar el captcha
        resp = requests.post("https://2captcha.com/in.php", data={
            "key": CAPTCHA_API_KEY,
            "method": "turnstile",
            "sitekey": TURNSTILE_SITEKEY,
            "pageurl": BCRA_PAGE_URL,
            "json": 1
        }, timeout=30)
        result = resp.json()

        if result.get("status") != 1:
            print(f"  2Captcha error: {result}")
            return None

        task_id = result["request"]
        print(f"  2Captcha: tarea {task_id}, esperando resolucion...")

        # Paso 2: polling hasta que se resuelva
        for i in range(30):  # max 150 segundos
            time.sleep(5)
            resp = requests.get("https://2captcha.com/res.php", params={
                "key": CAPTCHA_API_KEY,
                "action": "get",
                "id": task_id,
                "json": 1
            }, timeout=30)
            result = resp.json()

            if result.get("status") == 1:
                token = result["request"]
                print(f"  2Captcha: resuelto! (token: {token[:20]}...)")
                return token
            elif result.get("request") == "CAPCHA_NOT_READY":
                if i % 4 == 0:
                    print(f"  2Captcha: esperando... ({(i+1)*5}s)")
                continue
            else:
                print(f"  2Captcha error: {result}")
                return None

        print("  2Captcha: timeout")
        return None

    except Exception as e:
        print(f"  2Captcha error: {e}")
        return None


# ══════════════════════════════════════════════════════════
#  ICL — Indice para Contratos de Locacion (BCRA serie 7988)
# ══════════════════════════════════════════════════════════

def fetch_icl_endpoint():
    """
    Obtiene valor actual del ICL desde el endpoint PHP del BCRA.
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
            print("  ICL endpoint: serie 7988 no encontrada")
    except Exception as e:
        print(f"  ICL endpoint error: {e}")
    return results


def fetch_icl_rango():
    """
    Consulta el rango de fechas disponibles para el ICL.
    Devuelve (min_fecha, max_fecha) o (None, None).
    """
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
    """
    Obtiene datos ICL del formulario web del BCRA usando 2Captcha para Turnstile.
    Devuelve dict {fecha: valor}.
    """
    results = {}

    token = solve_turnstile()
    if not token:
        print("  ICL tabla: no se pudo resolver captcha")
        return results

    print(f"  ICL tabla: POST {desde} → {hasta}")
    try:
        # Convertir fechas de yyyy-mm-dd a dd/mm/yyyy para el form
        def fmt_date(d):
            if "-" in d:
                y, m, dd = d.split("-")
                return f"{dd}/{m}/{y}"
            return d

        form_data = {
            "serie": "7988",
            "fecha_desde": fmt_date(desde),
            "fecha_hasta": fmt_date(hasta),
            "cf-turnstile-response": token
        }

        r = requests.post(BCRA_FORM_URL, data=form_data, headers=HEADERS,
                         verify=False, timeout=30, allow_redirects=True)

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
                        parts = fecha_str.split("/")
                        if len(parts) == 3 and len(parts[2]) == 4:
                            valor = float(valor_str)
                            if valor > 0:
                                results[fecha_str] = valor
                    except (ValueError, IndexError):
                        continue

            print(f"  ICL tabla: {len(results)} registros obtenidos")
        else:
            print(f"  ICL tabla: sin tabla en respuesta (status {r.status_code})")
            # Verificar si hay error de captcha
            if "captcha_error" in r.text.lower() or "captcha_error" in r.url:
                print("  ICL tabla: captcha rechazado por el BCRA")

    except Exception as e:
        print(f"  ICL tabla error: {e}")

    return results


def should_fetch_full_table(existing_data):
    """
    Determina si hay que bajar la tabla completa del BCRA.
    Retorna True si:
      - Es dia 17+ del mes (BCRA publica nuevo ciclo)
      - El max_fecha del BCRA es mayor que nuestro ultimo dato
    """
    _, max_fecha = fetch_icl_rango()
    if not max_fecha:
        return False

    # Nuestro ultimo dato
    last_dates = sorted(existing_data.keys(), key=sort_key_fecha)
    if not last_dates:
        return True

    our_max = sort_key_fecha(last_dates[-1])  # yyyy-mm-dd
    bcra_max = max_fecha  # ya viene como yyyy-mm-dd

    if bcra_max > our_max:
        print(f"  BCRA tiene datos hasta {bcra_max}, nosotros hasta {our_max} → bajando tabla")
        return True
    else:
        print(f"  Datos al dia (BCRA max: {bcra_max}, nuestro: {our_max})")
        return False


def update_icl():
    """Actualiza icl.json mergeando datos nuevos con historico."""
    print("\n═══ Actualizando ICL ═══")
    existing = load_existing(ICL_FILE)

    by_date = {}
    for entry in existing.get("data", []):
        by_date[entry["fecha"]] = entry["valor"]

    # 1. Siempre: dato del dia via endpoint PHP
    new_data = {}
    new_data.update(fetch_icl_endpoint())

    # 2. Si hay datos nuevos en el BCRA que no tenemos: bajar tabla completa
    if CAPTCHA_API_KEY and should_fetch_full_table(by_date):
        _, max_fecha = fetch_icl_rango()
        if max_fecha:
            # Bajar desde hace 2 meses hasta max_fecha
            now = datetime.now()
            desde = (now - timedelta(days=60)).strftime("%Y-%m-%d")
            tabla_data = fetch_icl_tabla(desde, max_fecha)
            new_data.update(tabla_data)

    added = 0
    updated = 0
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
#  IPC — Indice de Precios al Consumidor (INDEC)
# ══════════════════════════════════════════════════════════

MESES_NOMBRE = [
    "", "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
]
MESES_MAP = {v: k for k, v in enumerate(MESES_NOMBRE) if v}


def fetch_ipc_datosgob():
    """
    Fuente 1: datos.gob.ar — historico completo de variaciones porcentuales.
    Devuelve dict {yyyy-mm: variacion_pct} con variaciones mensuales.
    """
    results = {}
    url = "https://apis.datos.gob.ar/series/api/series/?ids=148.3_INIVELNAL_DICI_M_26&limit=5000&format=json&representation_mode=percent_change"
    print("  IPC datos.gob.ar: consultando variaciones...")
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        data = r.json()
        for entry in data.get("data", []):
            if entry[1] is not None:
                fecha = entry[0][:7]  # "2017-01"
                results[fecha] = round(entry[1] * 100, 2)  # como porcentaje
        print(f"  IPC datos.gob.ar: {len(results)} meses")
    except Exception as e:
        print(f"  IPC datos.gob.ar error: {e}")
    return results


def fetch_ipc_indec():
    """
    Fuente 2: scraping directo del INDEC (como hace Argly).
    URL: https://www.indec.gob.ar/Nivel4/Tema/3/5/31
    Devuelve dict con el ultimo dato: {yyyy-mm: variacion_pct} o {} si falla.
    """
    import re
    url = "https://www.indec.gob.ar/Nivel4/Tema/3/5/31"
    print("  IPC INDEC directo: scrapeando...")
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        html = r.text

        # Extraer variacion: "variación de X,X%"
        match_var = re.search(r"variación de ([\d,]+)%", html)
        if not match_var:
            print("  IPC INDEC: no se encontro variacion en el HTML")
            return {}
        variacion = float(match_var.group(1).replace(",", "."))

        # Extraer mes: "registró en abril"
        match_mes = re.search(r"registró en ([a-záéíóúñ]+)", html, re.IGNORECASE)
        if not match_mes:
            print("  IPC INDEC: no se encontro mes")
            return {}
        mes_nombre = match_mes.group(1).lower()
        mes_num = MESES_MAP.get(mes_nombre)
        if not mes_num:
            print(f"  IPC INDEC: mes '{mes_nombre}' no reconocido")
            return {}

        # Extraer anio de la fecha de publicacion: "dd/mm/yy"
        match_fecha = re.search(r'card-titulo3.*?(\d{1,2}/\d{1,2}/(\d{2}))', html, re.DOTALL)
        if match_fecha:
            anio_pub = 2000 + int(match_fecha.group(2))
            # Si el mes es diciembre, el dato es del anio anterior
            anio = anio_pub - 1 if mes_num == 12 else anio_pub
        else:
            # Fallback: usar anio actual
            anio = datetime.now().year
            if mes_num == 12:
                anio -= 1

        fecha = f"{anio}-{mes_num:02d}"
        print(f"  IPC INDEC: {mes_nombre} {anio} = {variacion}%")
        return {fecha: variacion}

    except Exception as e:
        print(f"  IPC INDEC error: {e}")
        return {}


def update_ipc():
    """
    Actualiza ipc.json combinando datos.gob.ar (historico) + INDEC directo (ultimo dato).
    Guarda variaciones porcentuales mensuales y un indice acumulado base 100.
    """
    print("\n═══ Actualizando IPC ═══")

    # Cargar existente para mergear
    existing = load_existing(IPC_FILE)
    by_month = {}
    for entry in existing.get("data", []):
        by_month[entry["fecha"]] = entry.get("variacion_pct")

    # Fuente 1: datos.gob.ar (historico completo)
    datosgob = fetch_ipc_datosgob()
    for fecha, var in datosgob.items():
        by_month[fecha] = var

    # Fuente 2: INDEC directo (ultimo dato, puede ser mas reciente)
    indec = fetch_ipc_indec()
    for fecha, var in indec.items():
        if fecha not in by_month:
            print(f"  IPC: dato nuevo del INDEC: {fecha} = {var}%")
        by_month[fecha] = var

    if not by_month:
        print("  Sin datos IPC")
        return len(existing.get("data", []))

    # Construir indice acumulado base 100
    sorted_months = sorted(by_month.keys())
    indice_acum = {}
    prev_val = 100.0
    # El primer mes no tiene "anterior", arranca en 100
    for m in sorted_months:
        var = by_month[m]
        if var is not None:
            prev_val = prev_val * (1 + var / 100)
        indice_acum[m] = round(prev_val, 2)

    # Armar data final
    ipc_data = []
    for m in sorted_months:
        y, mm = m.split("-")
        mes_num = int(mm)
        ipc_data.append({
            "fecha": m,
            "anio": int(y),
            "mes": mes_num,
            "nombre_mes": MESES_NOMBRE[mes_num],
            "indice_ipc": indice_acum[m],
            "variacion_pct": by_month[m]
        })

    print(f"  IPC total: {len(ipc_data)} meses")
    if ipc_data:
        last = ipc_data[-1]
        print(f"  Ultimo: {last['nombre_mes']} {last['anio']} = {last['variacion_pct']}% (indice: {last['indice_ipc']})")

    result = {
        "meta": {
            "fuente": "INDEC (directo + datos.gob.ar)",
            "descripcion": "IPC Nivel General Nacional, variaciones mensuales + indice acumulado base 100",
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
