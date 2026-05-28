"""
Test 3: probar admin-ajax.php y captcha del BCRA para obtener datos ICL serie.
"""
import requests
import cloudscraper
import json
import re
import urllib3
urllib3.disable_warnings()

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

# Primero cargar la pagina para obtener cookies y nonces
print("=== Paso 1: Cargar pagina y extraer nonce/tokens ===")
scraper = cloudscraper.create_scraper()
r = scraper.get("https://www.bcra.gob.ar/principales-variables-datos/?serie=7988", timeout=30)
print(f"Status: {r.status_code}")

# Buscar nonces, tokens, security values
nonces = re.findall(r'["\'](?:nonce|_wpnonce|security)["\']:\s*["\']([^"\']+)["\']', r.text)
print(f"Nonces encontrados: {nonces}")

# Buscar TODAS las URLs con admin-ajax
ajax_refs = re.findall(r'["\']([^"\']*admin-ajax[^"\']*)["\']', r.text)
print(f"Admin-ajax refs: {ajax_refs}")

# Buscar api_url variable
api_url_match = re.findall(r'api_url["\']?\s*[:=]\s*["\']([^"\']+)["\']', r.text)
print(f"api_url: {api_url_match}")

# Buscar action names para admin-ajax
actions = re.findall(r'action["\']?\s*[:=]\s*["\']([^"\']+)["\']', r.text)
print(f"Actions: {sorted(set(actions))}")

# Buscar todo lo que tenga "serie" o "7988" en contexto
print("\n=== Paso 2: Contexto de 'serie' y '7988' en scripts ===")
scripts = re.findall(r'<script[^>]*>(.*?)</script>', r.text, re.DOTALL)
for i, s in enumerate(scripts):
    if ("7988" in s or "serie" in s.lower() or "api_url" in s.lower()) and len(s) > 50:
        # Mostrar lineas relevantes
        for line in s.split('\n'):
            line = line.strip()
            if any(kw in line.lower() for kw in ['serie', '7988', 'api_url', 'ajax', 'fetch', 'endpoint', 'action']):
                print(f"  Script#{i}: {line[:200]}")

# Test 3: Probar captcha endpoint
print("\n=== Paso 3: Probar /api/captcha/variables.php ===")
try:
    # GET primero
    r2 = scraper.get("https://www.bcra.gob.ar/api/captcha/variables.php", timeout=15)
    print(f"GET Status: {r2.status_code} | CT: {r2.headers.get('content-type','?')} | Len: {len(r2.text)}")
    if r2.status_code == 200 and len(r2.text) < 2000:
        print(f"Body: {r2.text[:500]}")
    
    # POST con serie
    r3 = scraper.post("https://www.bcra.gob.ar/api/captcha/variables.php", 
                       data={"serie": "7988", "desde": "2026-05-01", "hasta": "2026-06-28"},
                       timeout=15)
    print(f"POST Status: {r3.status_code} | CT: {r3.headers.get('content-type','?')} | Len: {len(r3.text)}")
    if len(r3.text) < 2000:
        print(f"Body: {r3.text[:500]}")
except Exception as e:
    print(f"Error: {e}")

# Test 4: Probar admin-ajax con acciones comunes
print("\n=== Paso 4: Probar admin-ajax.php ===")
ajax_url = "https://www.bcra.gob.ar/wp-admin/admin-ajax.php"
test_payloads = [
    {"action": "get_variable_data", "serie": "7988", "desde": "2026-05-01", "hasta": "2026-06-28"},
    {"action": "get_series_data", "serie": "7988", "desde": "2026-05-01", "hasta": "2026-06-28"},
    {"action": "principales_variables", "serie": "7988", "desde": "2026-05-01", "hasta": "2026-06-28"},
    {"action": "variables_datos", "serie": "7988", "desde": "2026-05-01", "hasta": "2026-06-28"},
    {"action": "divi_ajax_filter", "serie": "7988"},
]
for payload in test_payloads:
    try:
        r4 = scraper.post(ajax_url, data=payload, timeout=15)
        status_info = f"Status: {r4.status_code} | Len: {len(r4.text)}"
        if r4.status_code == 200 and r4.text != "0" and len(r4.text) > 5:
            print(f"  {payload['action']}: {status_info} >>> RESPUESTA: {r4.text[:300]}")
        else:
            print(f"  {payload['action']}: {status_info} | Body: {r4.text[:50]}")
    except Exception as e:
        print(f"  {payload['action']}: Error: {e}")

# Test 5: Buscar si hay un JS externo que tenga la logica
print("\n=== Paso 5: JS externos que pueden tener la logica ===")
js_files = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', r.text)
for js in js_files:
    if 'variable' in js.lower() or 'serie' in js.lower() or 'datos' in js.lower() or 'custom' in js.lower() or 'main' in js.lower() or 'app' in js.lower():
        print(f"  {js}")

# Listar TODOS los JS para no perder nada
print("\nTodos los JS externos:")
for js in js_files:
    if 'bcra.gob.ar' in js:
        print(f"  {js}")
