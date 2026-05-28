"""
Test 2: explorar endpoints BCRA para encontrar datos futuros del ICL.
"""
import requests
import json

HEADERS = {"User-Agent": "Mozilla/5.0"}
import urllib3
urllib3.disable_warnings()

# Test 1: El endpoint ultimas.php devuelve series limitadas.
# Pero la serie 7988 SI responde. Probemos si hay un endpoint de serie historica.
print("=== Test 1: principales-variables-ultimas con detalle ===")
r = requests.get("https://www.bcra.gob.ar/api/endpoints/principales-variables-ultimas.php",
                  headers=HEADERS, verify=False, timeout=30)
data = r.json()
print(f"Keys en response: {list(data.keys())}")
print(f"Tipo de 'series': {type(data.get('series'))}")
# Ver si 7988 tiene mas campos
serie7988 = data.get("series", {}).get("7988")
print(f"Serie 7988 completa: {json.dumps(serie7988, indent=2)}")

# Test 2: Probar variantes del endpoint con parametros
print("\n=== Test 2: Probar endpoints con parametros ===")
endpoints = [
    "https://www.bcra.gob.ar/api/endpoints/principales-variables-ultimas.php?serie=7988",
    "https://www.bcra.gob.ar/api/endpoints/principales-variables-ultimas.php?id=7988",
    "https://www.bcra.gob.ar/api/endpoints/principales-variables-ultimas.php?serie=7988&desde=2026-05-01&hasta=2026-06-28",
    "https://www.bcra.gob.ar/api/endpoints/principales-variables-datos.php?serie=7988&desde=2026-05-01&hasta=2026-06-28",
    "https://www.bcra.gob.ar/api/endpoints/principales-variables-datos.php",
    "https://www.bcra.gob.ar/api/endpoints/variables-serie.php?serie=7988",
    "https://www.bcra.gob.ar/api/endpoints/serie.php?serie=7988",
]
for url in endpoints:
    try:
        r = requests.get(url, headers=HEADERS, verify=False, timeout=15)
        body = r.text[:300] if len(r.text) < 500 else r.text[:300] + "..."
        print(f"\n{url}")
        print(f"  Status: {r.status_code} | CT: {r.headers.get('content-type','?')[:40]} | Len: {len(r.text)}")
        if r.status_code == 200 and 'json' in r.headers.get('content-type',''):
            print(f"  JSON: {body}")
        elif r.status_code != 404 and len(r.text) < 500:
            print(f"  Body: {body}")
    except Exception as e:
        print(f"\n{url}\n  Error: {e}")

# Test 3: Ver si el formulario web carga datos via AJAX (buscar en el HTML)
print("\n=== Test 3: Buscar AJAX endpoints en HTML del formulario ===")
import cloudscraper
scraper = cloudscraper.create_scraper()
r = scraper.get("https://www.bcra.gob.ar/principales-variables-datos/?serie=7988&desde=2026-05-01&hasta=2026-06-28", timeout=30)
# Buscar URLs de API, fetch, ajax, $.get, $.post, etc
import re
# Buscar endpoints en scripts
scripts = re.findall(r'<script[^>]*>(.*?)</script>', r.text, re.DOTALL)
api_patterns = []
for s in scripts:
    # URLs con /api/ o fetch( o $.ajax o .php
    urls = re.findall(r'["\']([^"\']*(?:api|\.php|fetch|endpoint|serie|variable)[^"\']*)["\']', s, re.IGNORECASE)
    if urls:
        api_patterns.extend(urls)
    # tambien wp-json, admin-ajax
    urls2 = re.findall(r'["\']([^"\']*(?:wp-json|admin-ajax|wp-admin)[^"\']*)["\']', s, re.IGNORECASE)
    if urls2:
        api_patterns.extend(urls2)

print(f"Encontradas {len(api_patterns)} URLs en scripts:")
for u in sorted(set(api_patterns)):
    print(f"  {u}")

# Test 4: Buscar el endpoint especifico que genera la tabla
print("\n=== Test 4: Buscar data-url, action, form action en HTML ===")
forms = re.findall(r'<form[^>]*action=["\']([^"\']+)["\']', r.text, re.IGNORECASE)
data_urls = re.findall(r'data-(?:url|src|endpoint)=["\']([^"\']+)["\']', r.text, re.IGNORECASE)
print(f"Forms action: {forms}")
print(f"Data URLs: {data_urls}")

# Buscar cualquier referencia a "7988" o "serie" en el JS
for i, s in enumerate(scripts):
    if "7988" in s or "serie" in s.lower():
        print(f"\n--- Script #{i} contiene 'serie' o '7988' (primeros 800 chars) ---")
        print(s[:800])
