#!/usr/bin/env python3
"""
Scraper de indices economicos para Juarez Beltran S.A.

Fuentes:
  - ICL: API oficial del BCRA (estadisticas v4.0, idVariable 40). Sin captcha,
         sin autenticacion. Trae TODOS los dias (fines de semana incluidos) y
         los valores a futuro que el BCRA ya publico (hasta el 16 del mes
         siguiente, ventana que se renueva el 17 de cada mes).
  - IPC: fuente primaria = Excel de series historicas del INDEC
         (sh_ipc_divisiones.xls, hoja "Variacion mensual IPC Nacional", fila
         "Nivel general" del total nacional). Respaldo = datos.gob.ar serie
         145.3_INGNACUAL_DICI_M_38.
         En ambos casos: variacion mensual redondeada a 1 decimal (= boletin
         INDEC) y acumulada en indice base 100 desde ene-2017.

Salida (data/):
  - icl.json     {meta, data:[{fecha:"dd/mm/yyyy", valor}]}
  - ipc.json     {meta, data:[{fecha:"yyyy-mm", indice_ipc}]}
  - status.json  estado de cada fuente; la pagina lo lee para avisar si algo fallo

Uso:
  python scraper.py            corre todo
  python scraper.py --debug    ademas imprime que hojas/filas encontro en el Excel del INDEC

El script nunca termina con error: si una fuente falla, deja los datos
anteriores y lo registra en status.json.
"""

import io
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests

DEBUG = "--debug" in sys.argv

# ── Configuracion ──
DATA_DIR = Path(__file__).parent / "data"
ICL_FILE = DATA_DIR / "icl.json"
IPC_FILE = DATA_DIR / "ipc.json"
STATUS_FILE = DATA_DIR / "status.json"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "*/*",
}

# ICL
BCRA_API = "https://api.bcra.gob.ar/estadisticas/v4.0/monetarias"
ICL_ID_VARIABLE = 40          # "Indice para Contratos de Locacion (ICL)"
ICL_DIAS_ATRAS = 60           # re-pedimos los ultimos 60 dias por si el BCRA corrige
ICL_DIAS_ADELANTE = 45        # cubre la ventana publicada a futuro (hasta el 16 del mes siguiente)

# IPC
# La pagina publica del IPC (indec.gob.ar/indec/web/Nivel4-Tema-3-5-31) arma los
# links por ajax desde este fragmento; ahi aparecen los archivos de nombre fijo.
INDEC_IPC_FRAGMENT = "https://www.indec.gob.ar/Nivel4/Tema/3/5/31"
INDEC_FTP_BASE = "https://www.indec.gob.ar/ftp/cuadros/economia/"
INDEC_XLS_FIJO = "sh_ipc_divisiones.xls"     # Nivel general y divisiones, serie completa
INDEC_XLS_RE = re.compile(r"sh_ipc[\w\-]*\.xlsx?", re.IGNORECASE)
DATOS_GOB_URL = "https://apis.datos.gob.ar/series/api/series/?ids=145.3_INGNACUAL_DICI_M_38&limit=5000&format=json"
IPC_PRIMER_MES = "2017-01"    # arranque del indice base 100 (= serie de datos.gob.ar)

MESES_ES = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12,
}


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def dbg(msg):
    if DEBUG:
        print(f"    [debug] {msg}")


# ══════════════════════════════════════════════════════════
#  Archivos
# ══════════════════════════════════════════════════════════

def load_json(filepath, default):
    if filepath.exists():
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"  ! No se pudo leer {filepath.name}: {e}")
    return default


def save_json(filepath, data):
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    n = len(data.get("data", [])) if isinstance(data, dict) and "data" in data else ""
    print(f"  ✓ Guardado {filepath.name}" + (f" ({n} registros)" if n != "" else ""))


def iso_to_ddmmyyyy(fecha_iso):
    y, m, d = fecha_iso[:10].split("-")
    return f"{d}/{m}/{y}"


def sort_key_fecha(fecha_str):
    if "/" in fecha_str:
        dd, mm, yyyy = fecha_str.split("/")
        return f"{yyyy}-{mm}-{dd}"
    return fecha_str


# ══════════════════════════════════════════════════════════
#  Status (lo lee index.html)
# ══════════════════════════════════════════════════════════

def load_status():
    st = load_json(STATUS_FILE, {})
    for k in ("icl", "ipc"):
        st.setdefault(k, {"ok": None, "fuente": None, "ultimo_ok": None, "ultimo_dato": None, "error": None})
    return st


def short_err(e, n=160):
    e = str(e or "error desconocido").replace("\n", " ")
    return e if len(e) <= n else e[:n] + "…"


def set_status(st, key, ok, fuente, ultimo_dato=None, error=None, respaldo=False):
    s = st[key]
    s["ok"] = ok
    s["fuente"] = fuente
    s["respaldo"] = respaldo
    s["error"] = None if ok else short_err(error)
    s["ultimo_intento"] = now_str()
    if ok:
        s["ultimo_ok"] = now_str()
    if ultimo_dato:
        s["ultimo_dato"] = ultimo_dato
    return s


# ══════════════════════════════════════════════════════════
#  ICL — API BCRA v4.0 (idVariable 40)
# ══════════════════════════════════════════════════════════

def fetch_icl_api(desde, hasta):
    """Devuelve {"dd/mm/yyyy": valor}. Lanza excepcion si la API no responde bien."""
    url = f"{BCRA_API}/{ICL_ID_VARIABLE}"
    params = {"desde": desde, "hasta": hasta, "limit": 1000}
    print(f"  ICL API: GET {desde} → {hasta}")
    r = requests.get(url, params=params, headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()
    if data.get("status") != 200:
        raise RuntimeError(f"status {data.get('status')} {data.get('errorMessages', '')}")
    results = {}
    for serie in data.get("results", []):
        if serie.get("idVariable") != ICL_ID_VARIABLE:
            continue
        for d in serie.get("detalle", []):
            valor = d.get("valor")
            if valor is None:
                continue
            results[iso_to_ddmmyyyy(d["fecha"])] = round(float(valor), 2)
    if not results:
        raise RuntimeError("la API respondio sin registros para el rango")
    fechas = sorted(results, key=sort_key_fecha)
    print(f"  ICL API: {len(results)} registros ({fechas[0]} → {fechas[-1]})")
    return results


def update_icl(st):
    print("\n═══ Actualizando ICL ═══")
    existing = load_json(ICL_FILE, {"data": []})
    by_date = {e["fecha"]: e["valor"] for e in existing.get("data", [])}

    now = datetime.now()
    desde = (now - timedelta(days=ICL_DIAS_ATRAS)).strftime("%Y-%m-%d")
    hasta = (now + timedelta(days=ICL_DIAS_ADELANTE)).strftime("%Y-%m-%d")
    try:
        new_data = fetch_icl_api(desde, hasta)
    except Exception as e:
        print(f"  ✗ ICL API error: {e}")
        last = max(by_date, key=sort_key_fecha) if by_date else None
        set_status(st, "icl", False, "BCRA API v4.0", ultimo_dato=last, error=str(e))
        print("  Manteniendo icl.json anterior")
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

    sorted_data = [{"fecha": f, "valor": v} for f, v in sorted(by_date.items(), key=lambda x: sort_key_fecha(x[0]))]
    save_json(ICL_FILE, {
        "meta": {
            "fuente": "BCRA API estadisticas v4.0, idVariable 40 (ex serie 7988)",
            "descripcion": "Indice para Contratos de Locacion (ICL)",
            "frecuencia": "diaria",
            "ultima_actualizacion": now_str(),
        },
        "data": sorted_data,
    })
    set_status(st, "icl", True, "BCRA API v4.0", ultimo_dato=sorted_data[-1]["fecha"])
    return len(sorted_data)


# ══════════════════════════════════════════════════════════
#  IPC — fuente primaria: Excel INDEC
# ══════════════════════════════════════════════════════════

def indec_candidate_urls():
    """
    1) Lee el fragmento ajax de la pagina del IPC y toma los links sh_ipc*.xls,
       con 'divisiones' primero (es el que tiene Nivel general + divisiones).
    2) Siempre agrega el nombre fijo conocido como respaldo.
    """
    urls = []
    try:
        r = requests.get(INDEC_IPC_FRAGMENT, headers=HEADERS, timeout=30)
        r.raise_for_status()
        found = sorted(set(m.group(0) for m in INDEC_XLS_RE.finditer(r.text)))
        dbg(f"links en pagina INDEC: {found}")
        found.sort(key=lambda n: (0 if "division" in n.lower() else 1, n))
        urls = [INDEC_FTP_BASE + n for n in found]
    except Exception as e:
        print(f"  INDEC pagina: no se pudo leer ({e}); uso el nombre fijo")
    fijo = INDEC_FTP_BASE + INDEC_XLS_FIJO
    if fijo not in urls:
        urls.append(fijo)
    return urls


def download_indec_xls(urls):
    """Devuelve (url, bytes) del primer Excel real que encuentre."""
    for u in urls:
        try:
            r = requests.get(u, headers=HEADERS, timeout=60)
            ct = r.headers.get("Content-Type", "")
            head = r.content[:8]
            is_xls = head.startswith(b"\xd0\xcf\x11\xe0")      # OLE2 (.xls)
            is_xlsx = head.startswith(b"PK")                    # zip (.xlsx)
            dbg(f"{u} → HTTP {r.status_code}, {len(r.content)} bytes, ct={ct}, xls={is_xls}, xlsx={is_xlsx}")
            if r.status_code == 200 and (is_xls or is_xlsx):
                print(f"  INDEC: descargado {u.rsplit('/', 1)[-1]} ({len(r.content) // 1024} KB)")
                return u, r.content
        except Exception as e:
            dbg(f"{u} → error {e}")
    raise RuntimeError("no se pudo descargar el Excel sh_ipc_divisiones.xls del INDEC")


def _norm(s):
    s = str(s).strip().lower()
    return (s.replace("á", "a").replace("é", "e").replace("í", "i")
             .replace("ó", "o").replace("ú", "u").replace("ñ", "n"))


def _cell_to_month(v, datemode=0):
    """Convierte una celda de encabezado a 'yyyy-mm' o None."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return f"{v.year:04d}-{v.month:02d}"
    if isinstance(v, (int, float)):
        # numero de serie Excel (ej. 42736 = 2017-01-01)
        if 30000 < float(v) < 80000:
            try:
                import xlrd
                d = xlrd.xldate.xldate_as_datetime(float(v), datemode)
                return f"{d.year:04d}-{d.month:02d}"
            except Exception:
                return None
        return None
    s = _norm(v)
    m = re.match(r"^(\d{4})-(\d{2})", s)              # 2017-01
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    m = re.match(r"^([a-z]{3})[a-z]*[\s\-/\.]*(\d{2,4})$", s)   # ene-17 / enero 2017
    if m and m.group(1) in MESES_ES:
        yy = int(m.group(2))
        if yy < 100:
            yy += 2000
        return f"{yy:04d}-{MESES_ES[m.group(1)]:02d}"
    return None


def load_sheets(content):
    """Devuelve lista de (nombre_hoja, filas) donde filas = lista de listas de valores."""
    sheets = []
    if content.startswith(b"PK"):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
        for ws in wb.worksheets:
            rows = [list(r) for r in ws.iter_rows(values_only=True)]
            sheets.append((ws.title, rows, 0))
    else:
        import xlrd
        wb = xlrd.open_workbook(file_contents=content)
        for ws in wb.sheets():
            rows = []
            for i in range(ws.nrows):
                row = []
                for j in range(ws.ncols):
                    c = ws.cell(i, j)
                    if c.ctype == xlrd.XL_CELL_DATE:
                        row.append(xlrd.xldate.xldate_as_datetime(c.value, wb.datemode))
                    else:
                        row.append(c.value)
                rows.append(row)
            sheets.append((ws.name, rows, wb.datemode))
    return sheets


def parse_indec_variaciones(content):
    """
    Busca la hoja de variacion mensual (cobertura nacional), la fila de fechas y
    la fila 'Nivel general' del bloque 'Total nacional'.
    Devuelve [(yyyy-mm, var_pct_1dec), ...] ordenado.
    """
    sheets = load_sheets(content)
    dbg("hojas: " + ", ".join(n for n, _, _ in sheets))

    # candidatas: nombre con 'variac' y 'mensual'; si ninguna, todas
    cand = [s for s in sheets if "variac" in _norm(s[0]) and "mensual" in _norm(s[0])]
    if not cand:
        cand = sheets

    for name, rows, datemode in cand:
        # fila de fechas: la que mas meses parseables tenga (>= 12)
        best_hdr, best_months = None, {}
        for i, row in enumerate(rows[:60]):
            months = {}
            for j, v in enumerate(row):
                ym = _cell_to_month(v, datemode)
                if ym:
                    months[j] = ym
            if len(months) >= 12 and len(months) > len(best_months):
                best_hdr, best_months = i, months
        if best_hdr is None:
            dbg(f"hoja '{name}': sin fila de fechas")
            continue
        dbg(f"hoja '{name}': fila de fechas = {best_hdr} ({len(best_months)} meses, "
            f"{min(best_months.values())} → {max(best_months.values())})")

        # bloque nacional: primera fila con 'total nacional' / 'nacional' en alguna celda
        # (despues del header); luego la primera 'nivel general' que siga
        start = best_hdr + 1
        nac = None
        for i in range(best_hdr, len(rows)):
            txt = " ".join(_norm(v) for v in rows[i] if isinstance(v, str))
            if "total nacional" in txt or txt.strip() == "nacional":
                nac = i
                break
        # En el Excel del INDEC la fila "Total nacional" ES la fila de fechas, y
        # antes de los datos hay un titulo "Nivel general y divisiones COICOP"
        # sin numeros: por eso se exige que la fila tenga valores numericos.
        search_from = nac if nac is not None else start
        ng, serie = None, []
        for i in range(search_from, len(rows)):
            if not any(isinstance(v, str) and "nivel general" in _norm(v) for v in rows[i]):
                continue
            vals = []
            for j, ym in best_months.items():
                v = rows[i][j] if j < len(rows[i]) else None
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    vals.append((ym, float(v)))
            if len(vals) >= 12:
                ng, serie = i, vals
                break
            dbg(f"hoja '{name}': fila {i} dice 'Nivel general' pero sin valores (titulo), sigo")
        if ng is None:
            dbg(f"hoja '{name}': sin fila 'Nivel general' con datos")
            continue
        dbg(f"hoja '{name}': bloque nacional fila {nac}, 'Nivel general' fila {ng}, {len(serie)} valores")
        serie.sort()
        # ¿viene en fraccion (0.019) o en porcentaje (1.9)?
        if max(abs(v) for _, v in serie) < 1.0:
            serie = [(ym, v * 100) for ym, v in serie]
        serie = [(ym, round(v, 1)) for ym, v in serie]
        dbg(f"hoja '{name}': ultimos 4 → {serie[-4:]}")
        return serie

    raise RuntimeError("no se pudo ubicar la serie 'Nivel general' / total nacional en el Excel")


def fetch_ipc_indec():
    """[(yyyy-mm, var_pct)] desde el Excel del INDEC. Lanza excepcion si falla."""
    print("  IPC INDEC: buscando Excel de series historicas...")
    url, content = download_indec_xls(indec_candidate_urls())
    serie = parse_indec_variaciones(content)
    return serie, url.rsplit("/", 1)[-1]


# ══════════════════════════════════════════════════════════
#  IPC — respaldo: datos.gob.ar
# ══════════════════════════════════════════════════════════

def fetch_ipc_datosgob():
    """[(yyyy-mm, var_pct)] desde datos.gob.ar. Lanza excepcion si falla."""
    print("  IPC datos.gob.ar: consultando serie de variaciones...")
    r = requests.get(DATOS_GOB_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()
    serie = []
    for entry in data.get("data", []):
        if entry[1] is None:
            continue
        serie.append((entry[0][:7], round(entry[1] * 100, 1)))
    if not serie:
        raise RuntimeError("serie vacia")
    serie.sort()
    return serie


# ══════════════════════════════════════════════════════════
#  IPC — armado del indice
# ══════════════════════════════════════════════════════════

def acumular(serie):
    """Variaciones [(ym, pct)] → [{"fecha": ym, "indice_ipc": acum}] base 100 desde IPC_PRIMER_MES."""
    acum = 100.0
    out = []
    for ym, var in serie:
        if ym < IPC_PRIMER_MES:
            continue
        acum = acum * (1 + var / 100)
        out.append({"fecha": ym, "indice_ipc": round(acum, 2)})
    return out


def update_ipc(st):
    print("\n═══ Actualizando IPC ═══")
    existing = load_json(IPC_FILE, {"data": []})

    primaria, respaldo = None, None
    err_primaria = err_respaldo = None

    try:
        primaria, archivo = fetch_ipc_indec()
        print(f"  IPC INDEC: {len(primaria)} meses, ultimo {primaria[-1][0]} = {primaria[-1][1]}%  ({archivo})")
    except Exception as e:
        err_primaria = str(e)
        print(f"  ✗ IPC INDEC: {e}")

    try:
        respaldo = fetch_ipc_datosgob()
        print(f"  IPC datos.gob.ar: {len(respaldo)} meses, ultimo {respaldo[-1][0]} = {respaldo[-1][1]}%")
    except Exception as e:
        err_respaldo = str(e)
        print(f"  ✗ IPC datos.gob.ar: {e}")

    # Control cruzado: si las dos fuentes responden, avisar si difieren en algun mes comun
    if primaria and respaldo:
        dp, dr = dict(primaria), dict(respaldo)
        diffs = [(m, dp[m], dr[m]) for m in sorted(set(dp) & set(dr)) if abs(dp[m] - dr[m]) > 0.05]
        if diffs:
            print(f"  ! INDEC y datos.gob.ar difieren en {len(diffs)} mes(es): {diffs[:5]}")
        else:
            print(f"  ✓ INDEC y datos.gob.ar coinciden en {len(set(dp) & set(dr))} meses comunes")

    if primaria:
        serie, fuente, usa_respaldo = primaria, "INDEC (sh_ipc_divisiones.xls)", False
    elif respaldo:
        serie, fuente, usa_respaldo = respaldo, "datos.gob.ar (respaldo)", True
    else:
        prev = (existing.get("data") or [{}])[-1].get("fecha")
        set_status(st, "ipc", False, "INDEC + datos.gob.ar", ultimo_dato=prev,
                   error=f"INDEC: {short_err(err_primaria, 70)} | datos.gob.ar: {short_err(err_respaldo, 70)}")
        print("  Manteniendo ipc.json anterior")
        return len(existing.get("data", []))

    ipc_data = acumular(serie)
    # Nunca pisar con menos datos de los que ya habia
    prev_last = (existing.get("data") or [{}])[-1].get("fecha", "")
    if ipc_data and ipc_data[-1]["fecha"] < prev_last:
        print(f"  ! La fuente devolvio hasta {ipc_data[-1]['fecha']} pero ya teniamos {prev_last}; mantengo el archivo anterior")
        set_status(st, "ipc", True, fuente, ultimo_dato=prev_last, respaldo=usa_respaldo)
        st["ipc"]["error"] = None
        return len(existing.get("data", []))

    save_json(IPC_FILE, {
        "meta": {
            "fuente": fuente,
            "descripcion": "IPC Nivel General Nacional, variaciones mensuales (1 decimal = boletin INDEC) acumuladas base 100",
            "frecuencia": "mensual",
            "ultima_actualizacion": now_str(),
        },
        "data": ipc_data,
    })
    s = set_status(st, "ipc", True, fuente, ultimo_dato=ipc_data[-1]["fecha"], respaldo=usa_respaldo)
    if usa_respaldo:
        s["error"] = short_err(err_primaria)   # informativo; ok=True porque hay datos
    return len(ipc_data)


# ══════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════

def main():
    print(f"Scraper Juarez Beltran — {now_str()}" + ("  [debug]" if DEBUG else ""))
    print(f"Directorio de datos: {DATA_DIR}")
    st = load_status()
    icl_count = update_icl(st)
    ipc_count = update_ipc(st)
    st["actualizado"] = now_str()
    save_json(STATUS_FILE, st)
    print(f"\n═══ Resumen ═══")
    print(f"  ICL: {icl_count} registros · {'OK' if st['icl']['ok'] else 'FALLO: ' + str(st['icl']['error'])}")
    print(f"  IPC: {ipc_count} registros · {'OK' if st['ipc']['ok'] else 'FALLO: ' + str(st['ipc']['error'])}"
          + (f" · fuente {st['ipc']['fuente']}" if st['ipc']['ok'] else ""))
    print("  ✓ Completado")


if __name__ == "__main__":
    main()
