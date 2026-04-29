"""Inject A/B comparison numbers into build_pptx.py and the markdown source.

Run after both 20-patient runs (memory OFF / ON) finish. Reads results via
compare_memory_ab.aggregate(), updates the placeholders in:

  - docs/progress_presentation/progress_presentation.md
        ("_baseline pending_" / "_experiment pending_" cells)
  - docs/progress_presentation/build_pptx.py
        (the ab_rows table on Slide 5: "—", "—" → real values)

Then prints the rebuild command. Idempotent: replaces previous values on
re-run, doesn't double-insert.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent

sys.path.insert(0, str(HERE))
from compare_memory_ab import _aggregate, BATCH, BASELINE, WITH_MEM  # noqa: E402

import json


def _pct(num: int, den: int) -> str:
    return "—" if den == 0 else f"{100 * num / den:.0f}%"


def _fmt_secs(seconds: float) -> str:
    return f"{seconds:.0f}s"


def main():
    uuids = json.loads(BATCH.read_text())
    base = _aggregate(BASELINE, uuids)
    mem = _aggregate(WITH_MEM, uuids)

    # Numbers we'll inject
    base_direct = f"{base['DIRECT']}/{base['n']} · {_pct(base['DIRECT'], base['n'])}"
    mem_direct = f"{mem['DIRECT']}/{mem['n']} · {_pct(mem['DIRECT'], mem['n'])}"
    base_found = _pct(base['found'], base['n'])
    mem_found = _pct(mem['found'], mem['n'])
    base_rank1 = _pct(base['rank1_when_found'], max(base['found'], 1))
    mem_rank1 = _pct(mem['rank1_when_found'], max(mem['found'], 1))
    base_time = _fmt_secs(base['duration_total_s'] / max(base['n'], 1))
    mem_time = _fmt_secs(mem['duration_total_s'] / max(mem['n'], 1))

    if base['n'] == 0 or mem['n'] == 0:
        print(
            f"WARNING: not enough data — baseline n={base['n']}, "
            f"memory-on n={mem['n']}. Aborting injection."
        )
        sys.exit(1)

    # ── Update the markdown source ──
    md_path = ROOT / "docs/progress_presentation/progress_presentation.md"
    md = md_path.read_text()
    md_new = re.sub(
        r"\| DIRECT match \|.*?\| .*? \|",
        f"| DIRECT match | {base_direct} | {mem_direct} |",
        md,
    )
    md_new = re.sub(
        r"\| Found rate \|.*?\| .*? \|",
        f"| Found rate | {base_found} | {mem_found} |",
        md_new,
    )
    md_new = re.sub(
        r"\| Avg time / patient \|.*?\| .*? \|",
        f"| Avg time / patient | {base_time} | {mem_time} |",
        md_new,
    )
    if md_new != md:
        md_path.write_text(md_new)
        print(f"updated {md_path.relative_to(ROOT)}")
    else:
        print(f"no markdown changes (already current)")

    # ── Update build_pptx.py ──
    py_path = ROOT / "docs/progress_presentation/build_pptx.py"
    py = py_path.read_text()
    new_rows = (
        '    ab_rows = [\n'
        '        ("Metric", "OFF", "ON"),\n'
        f'        ("DIRECT match", "{base_direct}", "{mem_direct}"),\n'
        f'        ("Found rate (D + I)", "{base_found}", "{mem_found}"),\n'
        f'        ("Avg time / patient", "{base_time}", "{mem_time}"),\n'
        f'        ("Rank-1 when found", "{base_rank1}", "{mem_rank1}"),\n'
        '    ]'
    )
    py_new = re.sub(
        r"    ab_rows = \[\n.*?\n    \]",
        new_rows,
        py,
        count=1,
        flags=re.DOTALL,
    )
    if py_new != py:
        py_path.write_text(py_new)
        print(f"updated {py_path.relative_to(ROOT)}")
    else:
        print(f"no build_pptx.py changes (already current)")

    print()
    print("Injected numbers:")
    print(f"  DIRECT (off → on):  {base_direct}  →  {mem_direct}")
    print(f"  Found  (off → on):  {base_found}  →  {mem_found}")
    print(f"  Rank-1 (off → on):  {base_rank1}  →  {mem_rank1}")
    print(f"  Time   (off → on):  {base_time}  →  {mem_time}")
    print()
    print("Rebuild .pptx:")
    print(f"  cd {HERE.relative_to(ROOT)} && python3 build_pptx.py")


if __name__ == "__main__":
    main()
