"""
Build a synthetic, anonymized, shareable copy of the private workbook.

The real workbook stays in data/private/ (git-ignored). This copy keeps every
sheet's structure and formatting (color-coded rows, tables, the Keys sheet),
but:
  - every ingredient and dish name is replaced with a neutral ID,
  - discard rows are resampled onto new dates with scrambled quantities,
  - prices and weights are randomly perturbed.
No real names, dates, or figures are published.

Usage:  python scripts/make_sample_data.py
"""
from datetime import datetime, timedelta
import sys
import tempfile
from pathlib import Path

import numpy as np
import openpyxl
from openpyxl.styles import PatternFill

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from wastemodel import config  # noqa: E402
from wastemodel.anonymize import anonymize_workbook  # noqa: E402

SRC, DST = config.PRIVATE_WORKBOOK, config.SAMPLE_WORKBOOK
rng = np.random.default_rng(42)


def jitter(value, pct):
    return value * rng.uniform(1 - pct, 1 + pct)


def scramble_discards(ws):
    rows = [r for r in range(2, ws.max_row + 1) if ws.cell(r, 2).value]
    real = [[ws.cell(r, c).value for c in range(2, 7)] for r in rows]     # item..conditions
    picks = rng.integers(0, len(real), len(rows))
    start = datetime(2025, 3, 3)
    n_shifts = len({ws.cell(r, 1).value for r in rows})         # same number of shifts as the real log
    shift_days = rng.choice(49, size=min(n_shifts, 49), replace=False)
    dates = sorted(start + timedelta(days=int(d)) for d in rng.choice(shift_days, len(rows)))
    no_fill = PatternFill(fill_type=None)
    for r, pick, date in zip(rows, picks, dates):
        item, qty, reason, donatable, conditions = real[pick]
        qty = float(qty) if isinstance(qty, (int, float)) else 1.0
        ws.cell(r, 1).value = date
        ws.cell(r, 2).value = item
        ws.cell(r, 3).value = max(0.5, round(jitter(qty, 0.4) * 2) / 2)
        ws.cell(r, 4).value = reason
        ws.cell(r, 5).value = donatable
        ws.cell(r, 6).value = conditions
        for c in range(1, 7):                  # drop one-off manual highlights;
            ws.cell(r, c).fill = no_fill       # the color-coding rules stay
        ws.row_dimensions[r].height = None     # rows get shuffled, so reset custom heights
    return len(rows)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        anon = Path(tmp) / "anon.xlsx"
        anonymize_workbook(SRC, anon, seed=1)
        wb = openpyxl.load_workbook(anon)

    n = scramble_discards(wb["Discard Log"])

    prices = wb["Price Data"]
    for r in range(2, prices.max_row + 1):
        for col, pct, digits in ((2, 0.10, 1), (4, 0.15, 2)):   # weight, price per serving
            cell = prices.cell(r, col)
            if isinstance(cell.value, (int, float)):
                cell.value = round(jitter(cell.value, pct), digits)

    menu = wb["Menu Anchors"]
    for r in range(2, menu.max_row + 1):
        cell = menu.cell(r, 2)
        if isinstance(cell.value, (int, float)):
            cell.value = round(np.floor(jitter(cell.value, 0.10)) + 0.99, 2)

    wb.calculation.fullCalcOnLoad = True       # Excel refreshes the revenue column on open
    DST.parent.mkdir(parents=True, exist_ok=True)
    wb.save(DST)
    print(f"Wrote {DST.relative_to(ROOT)}: {n} synthetic, anonymized discard rows")


if __name__ == "__main__":
    main()
