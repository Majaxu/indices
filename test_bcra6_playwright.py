"""
Test 6b: Playwright para obtener tabla ICL con datos futuros del BCRA.
"""
import asyncio
import sys

async def main():
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("pip install playwright && playwright install chromium")
        sys.exit(1)

    async with async_playwright() as p:
        print("=== Lanzando browser ===")
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        url = "https://www.bcra.gob.ar/principales-variables-datos/?serie=7988"
        print(f"Navegando a: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        print(f"Titulo: {await page.title()}")

        # Esperar que cargue el form
        print("Esperando formulario...")
        await page.wait_for_timeout(5000)

        # Llenar fechas
        print("Llenando fechas...")
        try:
            await page.fill("#fecha_desde", "2026-05-01")
            print("  fecha_desde OK")
        except:
            print("  fecha_desde: intentando con locator...")
            inputs = page.locator("input[type='date']")
            count = await inputs.count()
            print(f"  Encontrados {count} inputs date")
            if count >= 2:
                await inputs.nth(0).fill("2026-05-01")
                await inputs.nth(1).fill("2026-06-16")
                print("  Fechas llenadas via locator")

        try:
            await page.fill("#fecha_hasta", "2026-06-16")
            print("  fecha_hasta OK")
        except:
            pass

        # Esperar que Turnstile se resuelva solo
        print("Esperando Turnstile (hasta 15s)...")
        for i in range(15):
            await page.wait_for_timeout(1000)
            # Verificar si el checkbox de Turnstile se marco
            turnstile_response = await page.evaluate("""
                () => {
                    const input = document.querySelector('[name="cf-turnstile-response"]');
                    return input ? input.value.length > 0 : false;
                }
            """)
            if turnstile_response:
                print(f"  Turnstile resuelto en {i+1}s!")
                break
            if i % 3 == 0:
                print(f"  Esperando... ({i+1}s)")

        # Submit
        print("Buscando boton submit...")
        submit = page.locator('button[type="submit"], input[type="submit"], .et_pb_button')
        count = await submit.count()
        print(f"  Encontrados {count} botones")
        
        if count == 0:
            # Intentar buscar cualquier boton en el form
            submit = page.locator("form button, form input[type='submit']")
            count = await submit.count()
            print(f"  Busqueda ampliada: {count} botones")

        if count > 0:
            print("  Clickeando submit...")
            await submit.first.click()
        else:
            print("  No encontre boton, intentando submit del form...")
            await page.evaluate("document.querySelector('form').submit()")

        # Esperar respuesta
        print("Esperando respuesta (15s)...")
        await page.wait_for_timeout(15000)

        # Buscar tabla
        print("Buscando tabla...")
        table = page.locator("table")
        count = await table.count()
        if count > 0:
            print(f">>> TABLA ENCONTRADA ({count} tablas) <<<")
            rows = await table.first.locator("tr").all()
            print(f"Total filas: {len(rows)}")
            for row in rows[:25]:
                cells = await row.locator("td, th").all()
                texts = [await c.inner_text() for c in cells]
                if texts:
                    print(f"  {'  |  '.join(texts)}")
            if len(rows) > 25:
                print(f"  ... y {len(rows) - 25} filas mas")
                # Mostrar ultimas 5
                for row in rows[-5:]:
                    cells = await row.locator("td, th").all()
                    texts = [await c.inner_text() for c in cells]
                    if texts:
                        print(f"  {'  |  '.join(texts)}")
        else:
            print("No se encontro tabla")
            await page.screenshot(path="bcra_resultado.png")
            print("Screenshot guardado en bcra_resultado.png")
            # Ver URL actual
            print(f"URL actual: {page.url}")

        await browser.close()
        print("\n=== Fin ===")

asyncio.run(main())
