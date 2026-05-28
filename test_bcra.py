"""
Test: ver que devuelve el formulario web del BCRA para ICL datos futuros.
"""
import cloudscraper
import requests

# Test 1: Endpoint PHP (valor del dia)
print("=== Test 1: Endpoint PHP ===")
try:
    r = requests.get(
        "https://www.bcra.gob.ar/api/endpoints/principales-variables-ultimas.php",
        headers={"User-Agent": "Mozilla/5.0"},
        verify=False, timeout=30
    )
    print(f"Status: {r.status_code}")
    import json
    data = r.json()
    serie = data.get("series", {}).get("7988")
    print(f"ICL hoy: {serie}")
    # Ver que otras series hay
    print(f"Series disponibles: {list(data.get('series', {}).keys())[:10]}")
except Exception as e:
    print(f"Error: {e}")

# Test 2: Formulario web con cloudscraper
print("\n=== Test 2: Formulario web BCRA (cloudscraper) ===")
try:
    scraper = cloudscraper.create_scraper()
    url = "https://www.bcra.gob.ar/principales-variables-datos/?serie=7988&desde=2026-05-01&hasta=2026-06-28"
    print(f"URL: {url}")
    r = scraper.get(url, timeout=30)
    print(f"Status: {r.status_code}")
    print(f"Content-Type: {r.headers.get('content-type', '?')}")
    print(f"Length: {len(r.text)}")
    
    # Buscar tabla
    if "<table" in r.text.lower():
        print(">>> CONTIENE TABLA <<<")
        # Extraer fragmento alrededor de la tabla
        idx = r.text.lower().find("<table")
        print(r.text[idx:idx+1000])
    else:
        print(">>> NO contiene tabla <<<")
        # Mostrar parte del contenido para diagnosticar
        print("Primeros 1500 chars:")
        print(r.text[:1500])
except Exception as e:
    print(f"Error: {e}")

# Test 3: Probar URL alternativa del BCRA
print("\n=== Test 3: API BCRA variables ===")
try:
    # Probar si hay endpoint de serie historica
    url = "https://www.bcra.gob.ar/api/endpoints/principales-variables-historico.php?serie=7988&desde=2026-05-01&hasta=2026-06-28"
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, verify=False, timeout=30)
    print(f"Status: {r.status_code}")
    print(f"Content-Type: {r.headers.get('content-type', '?')}")
    if r.status_code == 200:
        print(r.text[:1000])
except Exception as e:
    print(f"Error: {e}")

# Test 4: Probar endpoint que lista todas las variables
print("\n=== Test 4: Listar endpoints BCRA ===")
try:
    urls_to_try = [
        "https://www.bcra.gob.ar/api/endpoints/principales-variables.php",
        "https://www.bcra.gob.ar/api/endpoints/principales-variables-serie.php?serie=7988",
        "https://www.bcra.gob.ar/api/endpoints/principales-variables-serie.php?serie=7988&desde=2026-05-01&hasta=2026-06-28",
    ]
    for url in urls_to_try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, verify=False, timeout=15)
        print(f"\n{url}")
        print(f"  Status: {r.status_code} | Length: {len(r.text)}")
        if r.status_code == 200 and len(r.text) < 2000:
            print(f"  Body: {r.text[:500]}")
        elif r.status_code == 200:
            print(f"  Body (first 500): {r.text[:500]}")
except Exception as e:
    print(f"Error: {e}")
