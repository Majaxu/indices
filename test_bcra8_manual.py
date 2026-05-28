"""
Test 8: Abrir Chrome, llenar las fechas, y dejar que VOS resuelvas el Turnstile.
Despues extrae la tabla automaticamente.
"""
import asyncio

async def main():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        print("=== Abriendo Chrome ===")
        browser = await p.chromium.launch(headless=False, channel="chrome")
        page = await browser.new_page()

        url = "https://www.bcra.gob.ar/principales-variables-datos/?serie=7988"
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)

        await page.wait_for_timeout(3000)
        await page.fill("#fecha_desde", "2026-05-01")
        await page.fill("#fecha_hasta", "2026-06-16")
        print("Fechas llenadas. Resolve el captcha y clickea Consultar.")
        print("Esperando hasta 120 segundos...")

        # Esperar a que aparezca una tabla (vos resolves el captcha)
        found = False
        for i in range(120):
            await page.wait_for_timeout(1000)
            count = await page.locator("table").count()
            if count > 0:
                print(f"\n>>> TABLA ENCONTRADA en {i+1}s <<<")
                found = True
                break
            # Tambien chequear si cambio de URL (redireccion post-submit)
            if "captcha_error" in page.url or "data_error" in page.url:
                print(f"\nError en URL: {page.url}")
                break
            if i % 10 == 0 and i > 0:
                print(f"  Esperando... ({i}s)")

        if found:
            table = page.locator("table")
            rows = await table.first.locator("tr").all()
            print(f"Total filas: {len(rows)}")
            all_data = []
            for row in rows:
                cells = await row.locator("td, th").all()
                texts = [await c.inner_text() for c in cells]
                if texts:
                    print(f"  {'  |  '.join(texts)}")
                    all_data.append(texts)
            
            # Guardar datos crudos
            import json
            with open("bcra_tabla_raw.json", "w", encoding="utf-8") as f:
                json.dump(all_data, f, ensure_ascii=False, indent=2)
            print(f"\nDatos guardados en bcra_tabla_raw.json ({len(all_data)} filas)")
        else:
            print("No se encontro tabla. Guardando screenshot...")
            await page.screenshot(path="bcra_resultado.png")

        await browser.close()

asyncio.run(main())
