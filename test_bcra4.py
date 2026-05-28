"""
Test 4: obtener el JS de la app y probar el endpoint svc-index.bcra.gob.ar
"""
import requests
import json
import re
import urllib3
urllib3.disable_warnings()

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# Paso 1: Descargar el JS de la app
print("=== Paso 1: Descargar principales-variables-datos-app.js ===")
js_url = "https://www.bcra.gob.ar/wp-content/themes/Divi-BCRA/js/principales-variables-datos-app.js?ver=1778264627"
r = requests.get(js_url, headers=HEADERS, verify=False, timeout=30)
print(f"Status: {r.status_code} | Len: {len(r.text)}")
js_code = r.text

# Guardar para referencia
with open("bcra_app.js", "w", encoding="utf-8") as f:
    f.write(js_code)
print("Guardado en bcra_app.js")

# Buscar endpoints, rutas, fetch calls
print("\n=== Paso 2: Buscar URLs y endpoints en el JS ===")
urls = re.findall(r'["\']([^"\']*(?:svc-index|api|serie|variable|endpoint)[^"\']*)["\']', js_code, re.IGNORECASE)
for u in sorted(set(urls)):
    print(f"  {u}")

# Buscar fetch/axios/$.get calls
print("\nFetch/request patterns:")
fetches = re.findall(r'(?:fetch|get|post|axios)\s*\(\s*["\']?([^"\')\s,]+)', js_code, re.IGNORECASE)
for f in sorted(set(fetches)):
    print(f"  {f}")

# Buscar rutas concatenadas con api_url
print("\nRutas concatenadas con api_url:")
routes = re.findall(r'api_url\s*\+\s*["\']([^"\']+)["\']', js_code)
for route in sorted(set(routes)):
    print(f"  {route}")

# Mostrar todo el JS si es corto, o las partes relevantes
if len(js_code) < 5000:
    print(f"\n=== JS completo ({len(js_code)} chars) ===")
    print(js_code)
else:
    print(f"\n=== Fragmentos relevantes del JS ({len(js_code)} chars total) ===")
    for line in js_code.split('\n'):
        line_s = line.strip()
        if any(kw in line_s.lower() for kw in ['api_url', 'fetch', 'serie', '7988', 'endpoint', 'svc-index', '/v1/', '/v2/', 'desde', 'hasta', 'captcha']):
            print(f"  {line_s[:250]}")

# Paso 3: Probar endpoints en svc-index.bcra.gob.ar
print("\n=== Paso 3: Probar svc-index.bcra.gob.ar ===")
base = "https://svc-index.bcra.gob.ar"
test_urls = [
    f"{base}/",
    f"{base}/v1/series/7988",
    f"{base}/v1/series/7988/datos?desde=2026-05-01&hasta=2026-06-28",
    f"{base}/series/7988",
    f"{base}/datos/series/7988",
    f"{base}/api/series/7988",
    f"{base}/principales-variables/7988",
]
for url in test_urls:
    try:
        r = requests.get(url, headers=HEADERS, verify=False, timeout=15)
        ct = r.headers.get('content-type', '?')[:40]
        print(f"\n{url}")
        print(f"  Status: {r.status_code} | CT: {ct} | Len: {len(r.text)}")
        if r.status_code == 200 and len(r.text) < 2000:
            print(f"  Body: {r.text[:500]}")
        elif r.status_code == 200:
            print(f"  Body (first 500): {r.text[:500]}")
        elif len(r.text) < 500:
            print(f"  Body: {r.text[:300]}")
    except Exception as e:
        print(f"\n{url}\n  Error: {e}")
