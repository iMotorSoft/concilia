from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any

from playwright.async_api import Page, async_playwright, expect


BASE_URL = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:3058/reconciliar")
DATA_DIR = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/SpendIQ/Doc/FCE/Conciliacion/SICOM")

CASES = [
    {
        "name": "Prueba 1 - Base.xlsx",
        "extracto": "11- Noviembre al 30.xlsx",
        "pilaga": "salida(261).xlsx",
        "sicom": "Base.xlsx",
        "expected": {
            "source_rows": "24 / 25",
            "lotes": "9",
            "extracto_lotes": "7 / 9",
            "extracto_amount": "48.570.180,00",
            "pilaga_rows": "22",
            "pilaga_amount": "42.140.180,00",
            "final_rows": "18",
            "final_amount": "40.570.180,00",
        },
    },
    {
        "name": "Prueba 2 - SICON CRUDO noviembre 2025.xlsx",
        "extracto": "11- Noviembre al 30.xlsx",
        "pilaga": "salida(261).xlsx",
        "sicom": "SICON CRUDO noviembre 2025.xlsx",
        "expected": {
            "source_rows": "484 / 507",
            "lotes": "105",
            "extracto_lotes": "77 / 105",
            "extracto_amount": "1.874.529.108,48",
            "pilaga_rows": "282",
            "pilaga_amount": "968.860.037,30",
            "final_rows": "213",
            "final_amount": "851.051.646,30",
        },
    },
    {
        "name": "Prueba 3 - Marzo 2026",
        "extracto": "2026_03-EXTRACTO.xlsx",
        "pilaga": "2026_03-PILAGA.xlsx",
        "sicom": "2026_03_SICON MARZO CRUDO.xlsx",
        "expected": {
            "source_rows": "371 / 376",
            "lotes": "112",
            "extracto_lotes": "77 / 112",
            "extracto_amount": "1.913.465.547,23",
            "pilaga_rows": "309",
            "pilaga_amount": "1.730.652.984,17",
            "final_rows": "255",
            "final_amount": "1.401.569.967,23",
        },
    },
]

WATCH_PATHS = (
    "/api/uploads/v2/ingest",
    "/api/ingest/confirm",
    "/api/reconcile_wizard/start",
    "/api/reconcile_wizard/runs/",
    "/api/reconcile/start",
    "/api/reconcile/summary/head",
    "/api/reconcile/summary/descomposicion",
    "/api/reconcile/details/",
)


def file_path(name: str) -> str:
    path = DATA_DIR / name
    if not path.exists():
        raise FileNotFoundError(path)
    return str(path)


def section_by_heading(page: Page, heading: str):
    return page.locator("section").filter(has=page.get_by_role("heading", name=heading)).last


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


async def wait_for_no_spinner(page: Page, timeout: int = 120_000) -> None:
    await expect(page.locator(".loading")).to_have_count(0, timeout=timeout)


async def upload_role(page: Page, button_name: str, heading: str, path: str) -> None:
    button = page.get_by_role("button", name=button_name)
    await expect(button).to_be_visible(timeout=20_000)
    dialog = page.locator("dialog[open]").last
    for attempt in range(2):
        await button.click()
        try:
            await expect(dialog).to_be_visible(timeout=10_000)
            break
        except Exception:
            if attempt == 1:
                raise
            await page.wait_for_timeout(1_000)
    await dialog.locator('input[type="file"]').set_input_files(path)
    await dialog.get_by_role("button", name=re.compile("Subir y analizar", re.I)).click()
    await expect(page.get_by_role("heading", name=heading)).to_be_visible(timeout=120_000)
    await wait_for_no_spinner(page)


async def confirm_card(page: Page, heading: str) -> None:
    card = section_by_heading(page, heading)
    await expect(card).to_be_visible(timeout=30_000)
    await card.get_by_role("button", name="Confirmar y procesar").click()
    await expect(card.get_by_text("Confirmado")).to_be_visible(timeout=120_000)
    await wait_for_no_spinner(page)
    await page.wait_for_timeout(1_000)


async def advance_wizard(page: Page) -> None:
    await page.get_by_role("button", name="Abrir asistente de conciliación").click()
    dialog = page.locator("dialog[open]").last
    await expect(dialog.get_by_text("Paso 1/3")).to_be_visible(timeout=120_000)
    await expect(dialog.get_by_text("Elegí el alcance")).to_be_visible(timeout=120_000)
    await page.wait_for_timeout(500)
    await dialog.locator("label").filter(has_text="Ventana por rango de fechas").click()
    await dialog.get_by_role("button", name="Continuar").click()

    try:
        await expect(dialog.get_by_text("Paso 2/3")).to_be_visible(timeout=10_000)
    except Exception:
        confirm = dialog.get_by_role("button", name=re.compile("Continuar igual|Confirmar selección", re.I))
        await expect(confirm).to_be_visible(timeout=30_000)
        await confirm.click()
        await expect(dialog.get_by_text("Paso 2/3")).to_be_visible(timeout=120_000)

    if await dialog.get_by_text("Definí ventana").is_visible():
        await dialog.get_by_role("button", name="Continuar").click()
    else:
        await expect(dialog.get_by_text("Seleccioná meses disponibles")).to_be_visible(timeout=120_000)
        checked_count = await dialog.locator('input[type="checkbox"]:checked').count()
        if checked_count == 0:
            await dialog.locator('input[type="checkbox"]:not([disabled])').first.check(force=True)
        await dialog.get_by_role("button", name="Continuar").click()
        confirm = dialog.get_by_role("button", name=re.compile("Continuar igual|Confirmar selección", re.I))
        if await confirm.is_visible():
            await confirm.click()
        try:
            await expect(dialog.get_by_text("Paso 3/3")).to_be_visible(timeout=5_000)
        except Exception:
            await expect(dialog.get_by_text("Definí ventana")).to_be_visible(timeout=120_000)
            await dialog.get_by_role("button", name="Continuar").click()

    await expect(dialog.get_by_text("Paso 3/3")).to_be_visible(timeout=120_000)
    await dialog.get_by_role("button", name="Confirmar e iniciar").click()


async def wait_results(page: Page, expected: dict[str, str]) -> dict[str, Any]:
    await expect(page.get_by_role("heading", name="Sumario de período")).to_be_visible(timeout=180_000)
    await expect(page.get_by_text("PILAGA con contraparte en extracto")).to_be_visible(timeout=180_000)
    await expect(page.get_by_role("heading", name="Cierre efectivo vía SICOM")).to_be_visible(timeout=180_000)
    await expect(page.get_by_text("SICOM: trazabilidad operativa y cierre bancario")).to_be_visible(timeout=180_000)
    await expect(page.get_by_text("Filas PILAGA con banco")).to_be_visible(timeout=180_000)
    await wait_for_no_spinner(page, timeout=180_000)

    sicom_card = page.locator(".card").filter(has_text="SICOM: trazabilidad operativa y cierre bancario").last
    final_card = page.locator("article").filter(has=page.get_by_role("heading", name="Cierre efectivo vía SICOM")).last
    sicom_text = normalize_text(await sicom_card.inner_text())
    final_text = normalize_text(await final_card.inner_text())
    values = await final_card.locator(".stat-value").all_inner_texts()

    required_fragments = [
        expected["source_rows"],
        expected["lotes"],
        expected["extracto_lotes"],
        expected["extracto_amount"],
        expected["pilaga_rows"],
        expected["pilaga_amount"],
    ]
    missing_sicom = [fragment for fragment in required_fragments if fragment not in sicom_text]
    missing_final = [
        fragment
        for fragment in (expected["final_rows"], expected["final_amount"])
        if fragment not in final_text
    ]
    if missing_sicom or missing_final:
        raise AssertionError({
            "missing_sicom_fragments": missing_sicom,
            "missing_final_fragments": missing_final,
            "sicom_text": sicom_text[:1600],
            "final_text": final_text[:1200],
        })

    return {
        "cierre_values": [v.strip() for v in values],
        "sicom_excerpt": sicom_text[:1600],
        "body_excerpt": final_text[:1200],
    }


async def run_case(browser, case: dict[str, str]) -> dict[str, Any]:
    context = await browser.new_context(viewport={"width": 1440, "height": 1000})
    page = await context.new_page()
    responses: list[dict[str, Any]] = []
    failures: list[str] = []

    def on_response(response):
        url = response.url
        if any(path in url for path in WATCH_PATHS):
            responses.append({"status": response.status, "url": url})

    def on_request_failed(request):
        url = request.url
        if any(path in url for path in WATCH_PATHS):
            failures.append(f"{request.failure}: {url}")

    page.on("response", on_response)
    page.on("requestfailed", on_request_failed)

    started = time.time()
    try:
        await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60_000)
        await expect(page.get_by_role("heading", name="Asistente de Conciliación")).to_be_visible(timeout=30_000)
        await page.wait_for_timeout(1_000)

        await upload_role(page, "Subir extracto", "Vista previa — Extracto", file_path(case["extracto"]))
        await confirm_card(page, "Vista previa — Extracto")

        await upload_role(page, "Subir contable", "Vista previa — Contable (PILAGA)", file_path(case["pilaga"]))
        await confirm_card(page, "Vista previa — Contable (PILAGA)")

        await upload_role(page, "Subir SICOM", "Vista previa — SICOM mensual", file_path(case["sicom"]))
        await confirm_card(page, "Vista previa — SICOM mensual")

        await advance_wizard(page)
        result_summary = await wait_results(page, case.get("expected") or {})

        bad = [r for r in responses if r["status"] >= 400 and "/events" not in r["url"]]
        if failures or bad:
            raise AssertionError({"request_failures": failures, "bad_responses": bad})

        return {
            "name": case["name"],
            "ok": True,
            "elapsed_sec": round(time.time() - started, 1),
            "responses": responses,
            **result_summary,
        }
    except Exception as exc:
        screenshot = Path("scripts") / f"e2e_sicom_failure_{re.sub(r'[^a-zA-Z0-9]+', '_', case['name']).strip('_')}.png"
        try:
            await page.screenshot(path=str(screenshot), full_page=True)
        except Exception:
            pass
        return {
            "name": case["name"],
            "ok": False,
            "elapsed_sec": round(time.time() - started, 1),
            "error": repr(exc),
            "screenshot": str(screenshot),
            "responses": responses,
            "failures": failures,
        }
    finally:
        await context.close()


async def main() -> int:
    async with async_playwright() as p:
        executable_path = (
            os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
            or shutil.which("google-chrome")
            or shutil.which("chromium-browser")
            or shutil.which("chromium")
        )
        launch_kwargs = {"headless": True}
        if executable_path:
            launch_kwargs["executable_path"] = executable_path
        browser = await p.chromium.launch(**launch_kwargs)
        results = []
        for case in CASES:
            print(f"RUN {case['name']}", flush=True)
            result = await run_case(browser, case)
            print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
            results.append(result)
        await browser.close()

    ok = all(item["ok"] for item in results)
    print("SUMMARY " + json.dumps({"ok": ok, "total": len(results), "passed": sum(1 for r in results if r["ok"])}, ensure_ascii=False), flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
