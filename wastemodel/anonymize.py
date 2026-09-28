"""
Replace every ingredient and dish name in a workbook with a neutral ID
(ING-001, DISH-001), consistently across all sheets, while keeping the
structure the model needs: categories, operational roles, prices, recipe
shares, and the links between discards, ingredients, and dishes.

Formatting is preserved because the workbook is edited in place with openpyxl.
"""
import re

import numpy as np
import openpyxl

from . import config
from .pipeline import _key

REDACTED = "[REDACTED]"
QTY = re.compile(r"\s*(\(\d+x\))\s*$")
WEIGHT = re.compile(r"^(?P<name>.*?)\s*(?P<w>\[\d*\.?\d+\])\s*$")


def _parts(cell):
    return [p.strip() for p in str(cell).split("|")] if cell else []


def _col(ws, header):
    for c in ws[1]:
        if c.value and str(c.value).strip() == header:
            return c.column
    raise KeyError(f"{ws.title}: no column '{header}'")


def _rows(ws):
    return [r for r in range(2, ws.max_row + 1) if ws.cell(r, 1).value not in (None, "")]


def build_maps(wb, seed=0):
    """Name -> ID maps. IDs are assigned in a shuffled order so they reveal
    nothing (not even alphabetical position)."""
    prices, menu, log = wb[config.PRICE_SHEET], wb[config.MENU_SHEET], wb[config.DISCARD_SHEET]
    ing, dish = {}, {}

    p_item, p_dishes = _col(prices, "Food Item"), _col(prices, "Dishes")
    m_dish, m_ings = _col(menu, "Menu Item"), _col(menu, "Ingredients")
    for r in _rows(prices):
        ing.setdefault(_key(prices.cell(r, p_item).value), None)
        for part in _parts(prices.cell(r, p_dishes).value):
            m = WEIGHT.match(part)
            dish.setdefault(_key(m.group("name") if m else part), None)
    for r in _rows(menu):
        dish.setdefault(_key(menu.cell(r, m_dish).value), None)
        for part in _parts(menu.cell(r, m_ings).value):
            ing.setdefault(_key(QTY.sub("", part)), None)
    l_item = _col(log, "Food Item")
    for r in range(2, log.max_row + 1):
        if log.cell(r, l_item).value:
            ing.setdefault(_key(log.cell(r, l_item).value), None)

    rng = np.random.default_rng(seed)
    for names, prefix in ((ing, "ING"), (dish, "DISH")):
        order = rng.permutation(len(names))
        for n, name in zip(order, list(names)):
            names[name] = f"{prefix}-{n + 1:03d}"
    return ing, dish


def anonymize_workbook(src, dst, seed=0):
    wb = openpyxl.load_workbook(src)
    ing, dish = build_maps(wb, seed)
    to_ing = lambda name: ing[_key(name)]
    to_dish = lambda name: dish[_key(name)]

    log = wb[config.DISCARD_SHEET]
    for row in log.iter_rows(min_row=2, max_col=6):           # data columns must be plain values
        for cell in row:
            if isinstance(cell.value, str) and cell.value.startswith("="):
                raise ValueError(f"{log.title}!{cell.coordinate} holds a formula; replace it with its value")
    c = _col(log, "Food Item")
    for r in range(2, log.max_row + 1):
        if log.cell(r, c).value:
            log.cell(r, c).value = to_ing(log.cell(r, c).value)

    prices = wb[config.PRICE_SHEET]
    c_item, c_dishes = _col(prices, "Food Item"), _col(prices, "Dishes")
    for r in _rows(prices):
        prices.cell(r, c_item).value = to_ing(prices.cell(r, c_item).value)
        parts = []
        for part in _parts(prices.cell(r, c_dishes).value):
            m = WEIGHT.match(part)
            parts.append(f"{to_dish(m.group('name'))} {m.group('w')}" if m else to_dish(part))
        prices.cell(r, c_dishes).value = " | ".join(parts) or None

    menu = wb[config.MENU_SHEET]
    c_dish, c_ings = _col(menu, "Menu Item"), _col(menu, "Ingredients")
    for r in _rows(menu):
        menu.cell(r, c_dish).value = to_dish(menu.cell(r, c_dish).value)
        parts = []
        for part in _parts(menu.cell(r, c_ings).value):
            q = QTY.search(part)
            parts.append(to_ing(QTY.sub("", part)) + (f" {q.group(1)}" if q else ""))
        menu.cell(r, c_ings).value = " | ".join(parts)

    # Interchangeable groups travel with the data, under their new IDs
    groups = {}
    if config.INTERCHANGEABLE_SHEET in wb.sheetnames:
        old = wb[config.INTERCHANGEABLE_SHEET]
        for g, name in old.iter_rows(min_row=2, max_col=2, values_only=True):
            if g is not None and name:
                groups.setdefault(g, []).append(name)
        del wb[config.INTERCHANGEABLE_SHEET]
    else:
        groups = dict(enumerate(config.INTERCHANGEABLE, start=1))
    sub = wb.create_sheet(config.INTERCHANGEABLE_SHEET)
    sub.append(["Group", "Item"])
    for g, group in groups.items():
        for name in group:
            if _key(name) in ing:
                sub.append([g, to_ing(name)])

    # Example cells on the Keys sheet name real dishes; so can the descriptions
    if "Keys" in wb.sheetnames:
        keys = wb["Keys"]
        known = sorted((n for n in list(ing) + list(dish) if " " in n), key=len, reverse=True)  # multi-word names only; single words like "sauce" are generic
        for row in keys.iter_rows():
            for cell in row:
                if isinstance(cell.value, str):
                    text = cell.value
                    for name in known:
                        text = re.sub(re.escape(name), REDACTED, text, flags=re.IGNORECASE)
                    cell.value = text
        example_cols = set()
        for row in keys.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and "example" in cell.value.lower():
                    example_cols.add((cell.column, cell.row))
        for col, header_row in example_cols:
            for r in range(header_row + 1, keys.max_row + 1):
                cell = keys.cell(r, col)
                if cell.value is None or (isinstance(cell.value, str) and cell.value.isupper()):
                    break
                cell.value = REDACTED

    for name in ("MISCOMMUNICATION", "Archetypes (Python)"):
        if name in wb.sheetnames:
            del wb[name]
    # File metadata can carry names and emails
    props = wb.properties
    props.creator = props.lastModifiedBy = config.COMPANY_ALIAS
    props.title = props.subject = props.description = props.keywords = None
    wb.calculation.fullCalcOnLoad = True
    wb.save(dst)
    return len(ing), len(dish)
