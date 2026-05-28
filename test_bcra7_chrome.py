"""
Test 7: Usar Chrome real del sistema (no Chromium de Playwright)
para que Turnstile lo reconozca como browser legitimo.
"""
import asyncio
import sys

async def main():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        print("=== Lanzando Chrome real del sistema ===")
        # Usar Chrome instalado en el sistema
        browser = await p.chromium.launch(
            headless=False,
            channel="chrome",  # Usa Chrome real, no Chromium
        )
        page = await browser.new_page()

        url = "https://www.bcra.gob.ar/principales-variables-datos/?serie=7988"
        print(f"Navegando a: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        print(f"Titulo: {await page.title()}")

        # Esperar formulario
        print("Esperando formulario...")
        await page.wait_for_timeout(3000)

        # Llenar fechas
        await page.fill("#fecha_desde", "2026-05-01")
        await page.fill("#fecha_hasta", "2026-06-16")
        print("Fechas llenadas")

        # Esperar Turnstile - con Chrome real deberia auto-resolverse
        print("Esperando Turnstile (hasta 30s)...")
        resolved = False
        for i in range(30):
            await page.wait_for_timeout(1000)
            turnstile_ok = await page.evaluate("""
                () => {
                    const input = document.querySelector('[name="cf-turnstile-response"]');
                    if (input && input.value.length > 0) return 'resolved';
                    const checkbox = document.querySelector('.cf-turnstile iframe');
                    if (checkbox) return 'present';
                    return 'not_found';
                }
            """)
            if turnstile_ok == 'resolved':
                print(f"  Turnstile resuelto en {i+1}s!")
                resolved = True
                break
            if i % 5 == 0:
                print(f"  Status: {turnstile_ok} ({i+1}s)")

        if not resolved:
            print("  Turnstile NO se resolvio automaticamente.")
            print("  Haciendo click en el checkbox manualmente...")
            # Intentar click en el iframe de Turnstile
            try:
                frame = page.frame_locator(".cf-turnstile iframe")
                checkbox = frame.locator("input[type='checkbox'], .mark")
                if await checkbox.count() > 0:
                    await checkbox.first.click()
                    print("  Click en checkbox hecho, esperando 10s...")
                    await page.wait_for_timeout(10000)
                else:
                    print("  No encontre checkbox dentro del iframe")
                    # Intentar click directo en el widget
                    widget = page.locator(".cf-turnstile")
                    if await widget.count() > 0:
                        box = await widget.first.bounding_box()
                        if box:
                            # Click en el centro del widget
                            await page.mouse.click(box['x'] + box['width']/2, box['y'] + box['height']/2)
                            print(f"  Click en widget ({box['x']:.0f}, {box['y']:.0f}), esperando 10s...")
                            await page.wait_for_timeout(10000)
            except Exception as e:
                print(f"  Error clickeando: {e}")

        # Re-chequear Turnstile
        final_check = await page.evaluate("""
            () => {
                const input = document.querySelector('[name="cf-turnstile-response"]');
                return input ? input.value.substring(0, 20) + '...' : 'NO RESPONSE';
            }
        """)
        print(f"  Turnstile response: {final_check}")

        # Submit
        print("Clickeando submit...")
        submit = page.locator('button[type="submit"], input[type="submit"]')
        if await submit.count() > 0:
            await submit.first.click()
        else:
            await page.evaluate("document.querySelector('form').submit()")

        # Esperar respuesta - puede redirigir
        print("Esperando respuesta...")
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=30000)
        except:
            pass
        await page.wait_for_timeout(5000)

        print(f"URL: {page.url}")

        # Buscar tabla
        table = page.locator("table")
        count = await table.count()
        if count > 0:
            print(f">>> TABLA ENCONTRADA ({count} tablas) <<<")
            rows = await table.first.locator("tr").all()
            print(f"Total filas: {len(rows)}")
            for row in rows[:20]:
                cells = await row.locator("td, th").all()
                texts = [await c.inner_text() for c in cells]
                if texts:
                    print(f"  {'  |  '.join(texts)}")
            if len(rows) > 20:
                # Ultimas 5
                print(f"  ... ({len(rows) - 20} filas mas) ...")
                for row in rows[-5:]:
                    cells = await row.locator("td, th").all()
                    texts = [await c.inner_text() for c in cells]
                    if texts:
                        print(f"  {'  |  '.join(texts)}")
        else:
            print("No se encontro tabla en la pagina resultado")
            await page.screenshot(path="bcra_resultado.png")
            # Guardar HTML
            html = await page.content()
            with open("bcra_resultado.html", "w", encoding="utf-8") as f:
                f.write(html)
            print("Guardados bcra_resultado.png y bcra_resultado.html")

        await browser.close()

asyncio.run(main())
