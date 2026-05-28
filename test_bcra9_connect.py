"""
Test 9: Conectarse a Chrome ya abierto con remote debugging.

INSTRUCCIONES:
1. Cerra todos los Chrome
2. Abri CMD y corré:
   "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
3. En otra CMD corré: python test_bcra9_connect.py
"""
import asyncio

async def main():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        print("=== Conectando a Chrome existente (port 9222) ===")
        try:
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        except Exception as e:
            print(f"Error conectando: {e}")
            print("\nAsegurate de:")
            print('1. Cerrar TODOS los Chrome')
            print('2. Abrir Chrome con: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --remote-debugging-port=9222')
            print('3. Despues correr este script en otra terminal')
            return

        # Usar el contexto existente (con cookies, sesion, etc)
        contexts = browser.contexts
        if not contexts:
            print("No hay contextos, creando uno...")
            context = await browser.new_context()
        else:
            context = contexts[0]

        page = await context.new_page()
        url = "https://www.bcra.gob.ar/principales-variables-datos/?serie=7988"
        print(f"Navegando a: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)

        await page.wait_for_timeout(5000)
        await page.fill("#fecha_desde", "2026-05-01")
        await page.fill("#fecha_hasta", "2026-06-16")
        print("Fechas llenadas.")

        # Esperar a que Turnstile cargue y se resuelva
        print("Esperando Turnstile...")
        for i in range(30):
            await page.wait_for_timeout(1000)
            status = await page.evaluate("""
                () => {
                    // Buscar cualquier elemento de Turnstile
                    const cf = document.querySelector('.cf-turnstile');
                    const iframe = document.querySelector('.cf-turnstile iframe, iframe[src*="turnstile"]');
                    const input = document.querySelector('[name="cf-turnstile-response"]');
                    const resolved = input && input.value.length > 0;
                    return {
                        widget: !!cf,
                        iframe: !!iframe,
                        input: !!input,
                        resolved: resolved,
                        inputVal: input ? input.value.substring(0,10) : 'none'
                    };
                }
            """)
            if status['resolved']:
                print(f"  Turnstile resuelto en {i+1}s!")
                break
            if i % 5 == 0:
                print(f"  {i+1}s: widget={status['widget']} iframe={status['iframe']} input={status['input']}")

        # Esperar un poco más y luego submit
        await page.wait_for_timeout(2000)
        
        print("Submitting...")
        await page.locator('button[type="submit"], input[type="submit"]').first.click()

        print("Esperando tabla...")
        await page.wait_for_timeout(10000)

        table = page.locator("table")
        if await table.count() > 0:
            print(">>> TABLA ENCONTRADA <<<")
            rows = await table.first.locator("tr").all()
            print(f"Filas: {len(rows)}")
            all_data = []
            for row in rows:
                cells = await row.locator("td, th").all()
                texts = [await c.inner_text() for c in cells]
                if texts:
                    print(f"  {'  |  '.join(texts)}")
                    all_data.append(texts)
            import json
            with open("bcra_tabla_raw.json", "w", encoding="utf-8") as f:
                json.dump(all_data, f, ensure_ascii=False, indent=2)
            print(f"\nGuardado bcra_tabla_raw.json ({len(all_data)} filas)")
        else:
            print("No hay tabla")
            await page.screenshot(path="bcra_resultado2.png")
            print(f"URL: {page.url}")
            print("Screenshot: bcra_resultado2.png")

        # NO cerrar el browser (es el Chrome del usuario)
        print("Listo (Chrome queda abierto)")

asyncio.run(main())
