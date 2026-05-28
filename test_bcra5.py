"""
Test 5: probar el endpoint de rango y el POST del captcha.
"""
import requests
import cloudscraper
import json
import re
import urllib3
urllib3.disable_warnings()

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

scraper = cloudscraper.create_scraper()

# Paso 1: Endpoint de rango - nos dice hasta cuando hay datos
print("=== Paso 1: Rango de fechas disponibles ===")
rango_url = "https://www.bcra.gob.ar/api/endpoints/principales-variables-rango.php?serie=7988"
r = requests.get(rango_url, headers=HEADERS, verify=False, timeout=15)
print(f"Status: {r.status_code}")
print(f"Body: {r.text[:500]}")

# Paso 2: POST al captcha - ver que devuelve sin captcha valido
print("\n=== Paso 2: POST a captcha/variables.php ===")
# Primero cargar la pagina para obtener cookies
r0 = scraper.get("https://www.bcra.gob.ar/principales-variables-datos/?serie=7988", timeout=30)
print(f"Cookies: {dict(scraper.cookies)}")

# POST con datos del form
form_data = {
    "serie": "7988",
    "fecha_desde": "2026-06-01",
    "fecha_hasta": "2026-06-16",
}
r2 = scraper.post("https://www.bcra.gob.ar/api/captcha/variables.php", 
                   data=form_data, timeout=30)
print(f"POST Status: {r2.status_code} | Len: {len(r2.text)}")
# Ver si la respuesta tiene tabla
if "<table" in r2.text.lower():
    print(">>> CONTIENE TABLA <<<")
    idx = r2.text.lower().find("<table")
    print(r2.text[idx:idx+2000])
else:
    print("No contiene tabla")
    if "captcha" in r2.text.lower():
        print("Menciona captcha en la respuesta")
    if "error" in r2.text.lower():
        errors = re.findall(r'(?:error|alert|warning)[^<]*<[^>]*>([^<]+)', r2.text, re.IGNORECASE)
        print(f"Errores encontrados: {errors[:5]}")
    for pattern in ['captcha_error', 'data_error', 'recaptcha', 'g-recaptcha', 'hcaptcha', 'turnstile', 'cf-turnstile']:
        if pattern in r2.text.lower():
            print(f"  Found: {pattern}")
    print(f"Primeros 1000 chars: {r2.text[:1000]}")

# Paso 3: Ver si el formulario usa recaptcha, hcaptcha o turnstile
print("\n=== Paso 3: Tipo de captcha ===")
captcha_types = {
    'recaptcha': r'(?:recaptcha|grecaptcha|g-recaptcha)',
    'hcaptcha': r'(?:hcaptcha|h-captcha)',
    'turnstile': r'(?:turnstile|cf-turnstile)',
    'captcha_img': r'(?:captcha.*img|img.*captcha)',
}
for name, pattern in captcha_types.items():
    matches = re.findall(pattern, r0.text, re.IGNORECASE)
    if matches:
        print(f"  {name}: {len(matches)} matches")
        keys = re.findall(r'(?:sitekey|data-sitekey|site_key)["\']?\s*[:=]\s*["\']([^"\']+)', r0.text, re.IGNORECASE)
        if keys:
            print(f"    Sitekeys: {keys}")

# Paso 4: Probar svc-index con headers de referer del BCRA
print("\n=== Paso 4: svc-index con referer ===")
svc_headers = {
    **HEADERS,
    "Referer": "https://www.bcra.gob.ar/principales-variables-datos/?serie=7988",
    "Origin": "https://www.bcra.gob.ar",
}
test_paths = [
    "/principales-variables",
    "/principales-variables/7988",
    "/principales-variables?serie=7988",
    "/serie/7988",
    "/datos?serie=7988",
    "/v1/datos/principales-variables/7988",
    "/estadisticascambiarias/v1.0/Cotizaciones",
]
for path in test_paths:
    url = f"https://svc-index.bcra.gob.ar{path}"
    try:
        r = requests.get(url, headers=svc_headers, verify=False, timeout=10)
        body_preview = r.text[:200] if len(r.text) < 300 else r.text[:200] + "..."
        print(f"  {path} -> {r.status_code} | {body_preview}")
    except Exception as e:
        print(f"  {path} -> Error: {e}")
