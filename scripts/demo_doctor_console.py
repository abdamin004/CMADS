"""Scripted demo of the CMADS doctor console using Playwright.

Walks through one patient deterministically so the presenter can
narrate without forgetting where to click:

  Patient browser  →  Overview tab  →  Input tab (+ raw JSON)
                  →  Reasoning tab (per-agent inspection)
                  →  Differential tab  →  Treatment tab
                  →  Similar cases tab

Each step pauses for a few seconds so a live audience can read the
screen. Defaults to a headed Chromium window (you see the browser);
pass --record to capture an MP4 of the run instead.

Setup
-----
The script needs Playwright and a Chromium binary:

    pip install playwright
    playwright install chromium

Prereqs
-------
The doctor console must be running locally:

    make doctor-console-api        # backend on :8010
    make doctor-console-web        # frontend on :5173

Usage
-----
    python3 scripts/demo_doctor_console.py
    python3 scripts/demo_doctor_console.py --uuid <patient-uuid>
    python3 scripts/demo_doctor_console.py --result-set multi_level
    python3 scripts/demo_doctor_console.py --record demo.webm
    python3 scripts/demo_doctor_console.py --fast    # halve every pause
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Patient + result-set defaults: a DIRECT-match Essential hypertension run
# with a treatment plan. Override with --uuid / --result-set.
DEFAULT_URL = "http://127.0.0.1:5173"
DEFAULT_RESULT_SET = "multi_level"
DEFAULT_UUID = "04ad2732-b952-4fbb-d2c6-aa6c25f9462f"

# Pause durations (seconds). Tuned for a live demo where the presenter
# needs ~6 seconds to read a typical panel; --fast halves them.
DEFAULT_PAUSES = {
    "browser_ready": 2.5,
    "after_patient_click": 4.0,
    "after_tab_click": 4.5,
    "after_json_toggle": 6.0,
    "after_agent_click": 5.0,
    "after_section_click": 3.0,
    "between_steps": 1.2,
    "final_hold": 6.0,
}


def _arg_parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url", default=DEFAULT_URL,
                   help="doctor console base URL")
    p.add_argument("--result-set", default=DEFAULT_RESULT_SET,
                   help="result-set id (e.g. multi_level, mas_results)")
    p.add_argument("--uuid", default=DEFAULT_UUID,
                   help="patient UUID to demo")
    p.add_argument("--fast", action="store_true",
                   help="halve all pauses (useful when iterating on the script)")
    p.add_argument("--record", type=str, default=None,
                   help="path to record video (e.g. demo.webm)")
    p.add_argument("--headless", action="store_true",
                   help="run without a visible window (use with --record)")
    return p.parse_args()


async def _pause(seconds: float, fast: bool) -> None:
    await asyncio.sleep(seconds * (0.5 if fast else 1.0))


async def run_demo(args: argparse.Namespace) -> int:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("ERROR: playwright not installed.")
        print("  pip install playwright && playwright install chromium")
        return 1

    url = f"{args.url}/?r={args.result_set}&p={args.uuid}"
    pauses = DEFAULT_PAUSES
    fast = args.fast

    print(f"== CMADS doctor-console demo ==")
    print(f"   URL:         {url}")
    print(f"   Patient:     {args.uuid}")
    print(f"   Result-set:  {args.result_set}")
    print(f"   Headless:    {args.headless}")
    if args.record:
        print(f"   Recording:   {args.record}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=args.headless,
            args=["--start-maximized"],
        )
        context_kwargs = {"viewport": {"width": 1440, "height": 900}}
        if args.record:
            rec_dir = Path(args.record).parent or Path(".")
            rec_dir.mkdir(parents=True, exist_ok=True)
            context_kwargs["record_video_dir"] = str(rec_dir)
            context_kwargs["record_video_size"] = {"width": 1440, "height": 900}
        context = await browser.new_context(**context_kwargs)
        page = await context.new_page()

        # 1. Open the console — URL-state pre-selects result-set + patient,
        #    so the workspace renders the patient detail directly.
        print("\n[1/8] Opening doctor console...")
        await page.goto(url, wait_until="networkidle")
        await _pause(pauses["browser_ready"], fast)

        # Belt-and-braces: also click the patient row in the browser, so
        # the audience sees the selection happen visibly.
        row_selector = f'[data-patient-uuid="{args.uuid}"]'
        if await page.locator(row_selector).count():
            print(f"[2/8] Clicking patient row {args.uuid[:12]}...")
            await page.locator(row_selector).first.scroll_into_view_if_needed()
            await _pause(pauses["between_steps"], fast)
            await page.locator(row_selector).first.click()
            await _pause(pauses["after_patient_click"], fast)
        else:
            print(f"[2/8] Patient row not found in sidebar; "
                  f"relying on URL preselect.")

        # 3. Overview tab is the default landing — pause so the audience
        #    sees the at-a-glance summary.
        print("[3/8] Overview tab — match outcome, primary diagnosis, signposts.")
        await _scroll_to_anchor(page, "tab-body-overview")
        await _pause(pauses["after_tab_click"], fast)

        # 4. Input tab — show what enters the system.
        print("[4/8] Input tab — what the agents see.")
        await page.locator('[data-demo-anchor="tab-input"]').click()
        await _pause(pauses["after_tab_click"], fast)
        await _scroll_to_anchor(page, "patient-input")
        await _pause(pauses["between_steps"], fast)

        # 4b. Toggle raw input JSON so the audience sees the literal
        #     ehr_case.json + lab_case.json the agents receive.
        json_toggle = page.locator('[data-demo-anchor="patient-input-json-toggle"]')
        if await json_toggle.count():
            print("       toggling raw input JSON...")
            await json_toggle.click()
            await _scroll_to_anchor(page, "patient-input-json")
            await _pause(pauses["after_json_toggle"], fast)
            # Close it again before moving on, so the next tab opens to a tidy view.
            await json_toggle.click()
            await _pause(pauses["between_steps"], fast)

        # 5. Reasoning tab — walk through agents in execution order.
        print("[5/8] Reasoning tab — per-agent narratives.")
        await page.locator('[data-demo-anchor="tab-reasoning"]').click()
        await _pause(pauses["after_tab_click"], fast)

        agent_order = [
            "ehr_analyst",
            "lab_interpreter",
            "diagnostic_reasoning",
            "clinical_reviewer",
            "final_diagnosis",
        ]
        for agent_id in agent_order:
            # AgentFlow's nodes don't have a stable data-attr yet; we click
            # by text content (the agent label). Fall back gracefully if
            # the click target isn't found.
            label_map = {
                "ehr_analyst": "EHR Analyst",
                "lab_interpreter": "Lab Interpreter",
                "diagnostic_reasoning": "Diagnostic Reasoning",
                "clinical_reviewer": "Clinical Reviewer",
                "final_diagnosis": "Diagnostic Refiner",
            }
            label = label_map[agent_id]
            node = page.get_by_text(label, exact=True).first
            if await node.count():
                print(f"       agent: {label}")
                try:
                    await node.click(timeout=2500)
                    await _pause(pauses["after_agent_click"], fast)
                    # Expand-all so the audience sees the full breakdown.
                    expand = page.locator(".narrative-expand-toggle")
                    if await expand.count():
                        await expand.first.click()
                        await _pause(pauses["after_section_click"], fast)
                        # Collapse back to the calm default state.
                        await expand.first.click()
                        await _pause(pauses["between_steps"], fast)
                except Exception as e:  # noqa: BLE001
                    print(f"         (skip — couldn't click {label}: {e})")

        # 6. Differential tab — the final ranked top-5.
        print("[6/8] Differential tab — final top-5 differential.")
        await page.locator('[data-demo-anchor="tab-differential"]').click()
        await _pause(pauses["after_tab_click"], fast)

        # 7. Treatment tab — NICE plan (DIRECT only; gracefully handles
        #    INDIRECT/MISS where the plan is the structured skip).
        print("[7/8] Treatment tab — NICE plan + assumptions/warnings.")
        await page.locator('[data-demo-anchor="tab-treatment"]').click()
        await _pause(pauses["after_tab_click"], fast)

        # 8. Similar cases — Tier-4 case-based memory neighbours.
        print("[8/8] Similar cases tab — Tier-4 case-based neighbours.")
        await page.locator('[data-demo-anchor="tab-similar"]').click()
        await _pause(pauses["after_tab_click"], fast)
        await _pause(pauses["final_hold"], fast)

        # Cleanly stop recording before closing.
        await context.close()
        await browser.close()

        if args.record:
            # Playwright drops the recorded webm into the context's
            # record_video_dir with an auto-generated name; move it to
            # the path the user passed.
            recorded = sorted(Path(args.record).parent.glob("*.webm"),
                              key=lambda p: p.stat().st_mtime)
            if recorded:
                final = Path(args.record)
                recorded[-1].rename(final)
                print(f"\nRecording saved → {final}")

    print("\nDone.")
    return 0


async def _scroll_to_anchor(page, anchor: str) -> None:
    """Scroll the element with data-demo-anchor=<anchor> into view."""
    selector = f'[data-demo-anchor="{anchor}"]'
    if await page.locator(selector).count():
        try:
            await page.locator(selector).first.scroll_into_view_if_needed(timeout=1500)
        except Exception:  # noqa: BLE001
            pass


def main() -> None:
    args = _arg_parse()
    try:
        rc = asyncio.run(run_demo(args))
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        sys.exit(130)
    sys.exit(rc)


if __name__ == "__main__":
    main()
