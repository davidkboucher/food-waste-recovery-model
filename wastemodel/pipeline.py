"""
Food waste & recovery analysis pipeline.

Load -> clean -> estimate prices -> value each discard -> classify donation
eligibility -> build donation scenarios -> estimate tax benefit.
"""
import re

import numpy as np
import pandas as pd

from . import config

DONATION_TIERS = [
    "As-Is",
    "Freeze (Required)",
    "Freeze (Recommended)",
    "Hot Hold + Temp Logs",
    "Weak Maybe",
    "Not Donatable",
]
FOOD_GROUP_OF = {cat: group for group, cats in config.FOOD_GROUPS.items() for cat in cats}
SCENARIOS = {  # cumulative: each scenario adds one more operational change
    "Donate As-Is": DONATION_TIERS[:1],
    "+ Freezing (Required)": DONATION_TIERS[:2],
    "+ Freezing (All)": DONATION_TIERS[:3],
    "+ Temp Logs": DONATION_TIERS[:4],
}


# ----------------------------------------------------------------- loading ---
def _read(sheet):
    df = pd.read_excel(config.WORKBOOK, sheet_name=sheet)
    return df.loc[:, ~df.columns.astype(str).str.startswith("Unnamed")]


def _key(name):
    """Normalize a name for matching: case, curly quotes, extra spaces."""
    name = str(name).replace("\u2019", "'").replace("\u2018", "'").lower()
    return re.sub(r"\s+", " ", name).strip()


_GROUPS = None


def _interchangeable():
    """Groups of interchangeable ingredients: from the workbook if it has an
    Interchangeable sheet (columns Group, Item), otherwise from config."""
    global _GROUPS
    if _GROUPS is None:
        try:
            df = pd.read_excel(config.WORKBOOK, sheet_name=config.INTERCHANGEABLE_SHEET)
            _GROUPS = df.groupby("Group")["Item"].apply(list).tolist()
        except ValueError:
            _GROUPS = config.INTERCHANGEABLE
    return _GROUPS


def _item_key(name):
    """Like _key, but interchangeable ingredients share one key, so either can
    fill the other's slot in a recipe."""
    key = _key(name)
    for group in _interchangeable():
        keys = [_key(g) for g in group]
        if key in keys:
            return keys[0]
    return key


def _split(value):
    """Split a pipe-delimited cell ('A | B | C') into a clean list."""
    if pd.isna(value) or not str(value).strip():
        return []
    return [part.strip() for part in str(value).split("|")]


def load_discards():
    df = _read(config.DISCARD_SHEET)
    df.columns = ["date", "item", "qty", "reason", "donatable", "conditions", "sheet_value"][: len(df.columns)]
    df["date"] = pd.to_datetime(df["date"], format="mixed", errors="coerce")
    df["qty"] = pd.to_numeric(df["qty"], errors="coerce")
    df = df.dropna(subset=["date", "item", "qty"])          # drops spreadsheet total/blank rows
    for col in ("item", "reason", "donatable", "conditions"):
        df[col] = df[col].fillna("").astype(str).str.strip()
    df["donatable"] = df["donatable"].str.title()            # 'no' -> 'No'
    return df.reset_index(drop=True)


def load_prices():
    df = _read(config.PRICE_SHEET).rename(columns={
        "Food Item": "item", "Unit Weight (grams)": "weight_g",
        "Servings per Unit": "servings", "Potential Revenue per Serving ($)": "price",
        "Price Confidence": "confidence", "Operational Role": "role",
        "Dishes": "dishes", "Food Category": "category",
    })
    df = df.dropna(subset=["item"])
    df["item"] = df["item"].str.strip()
    if "category" not in df:                                  # food cost % falls back to the default
        df["category"] = np.nan
    df = df.drop_duplicates("item", keep="first")
    return df.reset_index(drop=True)


def load_menu():
    """One row per (menu item, ingredient) with its share of the menu price."""
    df = _read(config.MENU_SHEET).dropna(subset=["Menu Item"])
    rows = []
    for _, r in df.iterrows():
        ings, pcts = _split(r["Ingredients"]), _split(r["% of Menu Price"])
        try:
            pcts = [float(p) for p in pcts]
        except ValueError:
            pcts = []
        if len(pcts) != len(ings):                            # fall back to an even split
            pcts = [1 / len(ings)] * len(ings) if ings else []
        for ing, pct in zip(ings, pcts):
            m = re.search(r"\((\d+)x\)", ing)
            rows.append({
                "dish": str(r["Menu Item"]).strip(),
                "dish_price": float(r["Menu Price ($)"]),
                "item": re.sub(r"\s*\(\d+x\)", "", ing).strip(),
                "share": pct,
                "per_dish_qty": int(m.group(1)) if m else 1,
            })
    return pd.DataFrame(rows)


# --------------------------------------------------------- price estimates ---
def _margin(conf):
    for threshold, margin in config.CONFIDENCE_MARGINS:
        if conf >= threshold:
            return margin
    return np.nan                                             # too uncertain to use


def estimate_prices(prices, menu):
    """Low/mid/high per-serving value, capped so no ingredient is worth more
    than its share of the dishes it actually goes into."""
    est = prices[["item", "price", "confidence"]].copy()
    est["margin"] = est["confidence"].apply(_margin)
    diag = {"excluded_low_confidence": sorted(est.loc[est["margin"].isna(), "item"])}
    est = est.dropna(subset=["margin"])
    est["low"] = est["price"] * (1 - est["margin"])
    est["mid"] = est["price"]
    est["high"] = est["price"] * (1 + est["margin"])

    # Dish-weighted cap: each dish reference looks like 'Dish Name [0.5]'
    refs = prices[["item", "dishes"]].assign(ref=prices["dishes"].apply(_split)).explode("ref").dropna(subset=["ref"]).reset_index(drop=True)
    parsed = refs["ref"].str.extract(r"^(?P<dish>.*?)\s*\[(?P<weight>\d*\.?\d+)\]$")
    refs = refs.join(parsed).dropna(subset=["dish"])
    refs["weight"] = refs["weight"].astype(float)
    refs["dish_key"], refs["item_key"] = refs["dish"].map(_key), refs["item"].map(_item_key)
    menu_k = menu.assign(dish_key=menu["dish"].map(_key), item_key=menu["item"].map(_item_key))
    refs = refs.merge(menu_k.drop(columns=["dish", "item"]), on=["dish_key", "item_key"], how="inner")
    refs["cap"] = refs["dish_price"] * refs["share"] / refs["per_dish_qty"]
    caps = refs.groupby("item").apply(
        lambda g: np.average(g["cap"], weights=g["weight"]), include_groups=False
    ).rename("cap")

    est = est.merge(caps, on="item", how="left")
    capped = est["cap"].notna() & (est["cap"] > 0)
    diag["cap_available"] = int(capped.sum())
    diag["capped_below_price"] = int((capped & (est["cap"] < est["price"])).sum())
    est.loc[capped, "mid"] = est.loc[capped, ["mid", "cap"]].min(axis=1)
    est.loc[capped, "high"] = est.loc[capped, ["high", "cap"]].min(axis=1)

    # If a dish's ingredients (at high estimates) exceed its menu price, scale down.
    high = est.set_index("item")["high"]
    dish_totals = menu.assign(h=menu["item"].map(high) * menu["per_dish_qty"]).groupby(["dish", "dish_price"])["h"].sum().reset_index()
    over = dish_totals[dish_totals["h"] > dish_totals["dish_price"]]
    diag["scaled_dishes"] = [(d["dish"], d["h"], d["dish_price"], d["dish_price"] / d["h"])
                             for _, d in over.iterrows()]
    for _, d in over.iterrows():
        scale = d["dish_price"] / d["h"]
        items = menu.loc[menu["dish"] == d["dish"], "item"]
        est.loc[est["item"].isin(items), "high"] *= scale

    # Keep the range ordered after capping/scaling: low <= mid <= high
    est["mid"] = est[["mid", "high"]].min(axis=1)
    est["low"] = est[["low", "mid"]].min(axis=1)
    diag["estimates"] = len(est)
    return est[["item", "low", "mid", "high"]].round(2), diag


def unmatched_dish_refs(prices, menu):
    """Data-quality check: dish references in the price sheet that don't line up
    with the menu sheet (typos, or the ingredient missing from that recipe)."""
    refs = prices[["item", "dishes"]].assign(ref=prices["dishes"].apply(_split)).explode("ref").dropna(subset=["ref"]).reset_index(drop=True)
    refs = refs.join(refs["ref"].str.extract(r"^(?P<dish>.*?)\s*\[")).dropna(subset=["dish"])
    menu_dishes = set(menu["dish"].map(_key))
    menu_pairs = set(zip(menu["dish"].map(_key), menu["item"].map(_item_key)))
    refs["problem"] = np.where(~refs["dish"].map(_key).isin(menu_dishes), "Dish not found on menu sheet",
                      np.where([(_key(d), _item_key(i)) not in menu_pairs for d, i in zip(refs["dish"], refs["item"])],
                               "Ingredient not listed in dish recipe", ""))
    return refs.loc[refs["problem"] != "", ["item", "dish", "problem"]].reset_index(drop=True)


def cogs_pct(prices):
    def avg(cats):
        vals = [config.CATEGORY_COGS_PCT[c] for c in _split(cats) if c in config.CATEGORY_COGS_PCT]
        return np.mean(vals) if vals else config.DEFAULT_COGS_PCT
    return prices.assign(cogs_pct=prices["category"].apply(avg))[["item", "cogs_pct", "category"]]


# ---------------------------------------------------------------- valuing ---
def value_discards(discards, prices, estimates):
    """Attach revenue value, food cost, and weight to every discard event."""
    ref = (prices[["item", "servings", "weight_g"]]
           .merge(estimates, on="item")
           .merge(cogs_pct(prices), on="item"))
    df = discards.merge(ref, on="item", how="left", indicator=True)
    unmatched = sorted(df.loc[df["_merge"] == "left_only", "item"].unique())
    df = df[df["_merge"] == "both"].drop(columns="_merge")

    df["servings_lost"] = df["qty"] * df["servings"]
    for level in ("low", "mid", "high"):
        df[f"revenue_{level}"] = df["servings_lost"] * df[level]
    df["food_cost"] = df["revenue_mid"] * df["cogs_pct"] / 100
    df["lbs"] = df["qty"] * df["weight_g"] / config.GRAMS_PER_LB
    df["primary_category"] = df["category"].apply(lambda c: (_split(c) or ["Other"])[0])
    df["food_group"] = df["primary_category"].map(FOOD_GROUP_OF).fillna("Other")
    df["tier"] = df.apply(classify, axis=1)
    return df.reset_index(drop=True), unmatched


def classify(row):
    """Which operational change (if any) would make this discard donatable."""
    don, reason, cond = row["donatable"].lower(), row["reason"].lower(), row["conditions"].lower()
    if don == "yes" and "expiring" in reason:
        return "As-Is"
    if don in ("yes", "strong maybe") and "freeze" in cond and "req" in cond:
        return "Freeze (Required)"
    if "freeze" in cond and "rec" in cond:
        return "Freeze (Recommended)"
    if "hot hold" in reason and "maybe" in don and "temp" in cond and "log" in cond:
        return "Hot Hold + Temp Logs"
    if don == "weak maybe":
        return "Weak Maybe"
    return "Not Donatable"


def food_group_shares(events):
    """Share of estimated value and of weight by food category and broad group.
    An item listed under several categories is split evenly among them."""
    df = events[["category", "revenue_mid", "lbs"]].copy()
    df["cat"] = df["category"].apply(lambda c: _split(c) or ["Other"])
    df["split"] = 1 / df["cat"].str.len()
    df = df.explode("cat")
    df["value"], df["weight"] = df["revenue_mid"] * df["split"], df["lbs"] * df["split"]
    lookup = {cat: group for group, cats in config.FOOD_GROUPS.items() for cat in cats}
    df["group"] = df["cat"].map(lookup).fillna("Other")
    out = df.groupby(["group", "cat"])[["value", "weight"]].sum()
    return out / out.sum()


# -------------------------------------------------------------- scenarios ---
def enhanced_deduction(revenue, cost):
    """IRC 170(e)(3) enhanced deduction for donated food inventory:
    the lesser of (cost + half the markup) or (2 x cost)."""
    return min(cost + 0.5 * (revenue - cost), 2 * cost)


def build_scenarios(events):
    weeks = max((events["date"].max() - events["date"].min()).days + 1, 1) / 7
    rows = []
    for name, tiers in SCENARIOS.items():
        s = events[events["tier"].isin(tiers)]
        rev, cost = s["revenue_mid"].sum(), s["food_cost"].sum()
        deduction = enhanced_deduction(rev, cost)
        rows.append({
            "scenario": name,
            "events": len(s),
            "lbs": s["lbs"].sum(),
            "revenue_value": rev,
            "food_cost": cost,
            "deduction": deduction,
            "tax_benefit": deduction * config.TAX_RATE,
        })
    out = pd.DataFrame(rows)
    for col in ("lbs", "revenue_value", "food_cost", "deduction", "tax_benefit"):
        out[f"{col}_per_week"] = out[col] / weeks
    return out.round(2), weeks


def run():
    global _GROUPS
    _GROUPS = None                               # re-read if the workbook changed
    discards = load_discards()
    prices = load_prices()
    menu = load_menu()
    estimates, diag = estimate_prices(prices, menu)
    events, unmatched = value_discards(discards, prices, estimates)
    scenarios, weeks = build_scenarios(events)
    return {"events": events, "scenarios": scenarios, "estimates": estimates,
            "unmatched_items": unmatched, "bad_refs": unmatched_dish_refs(prices, menu),
            "weeks": weeks, "prices": prices, "menu": menu, "diagnostics": diag,
            "scale": {
                "observations": len(discards),
                "shifts": discards["date"].nunique(),
                "weeks": weeks,
                "items_discarded": discards["item"].nunique(),
                "ingredients_priced": len(prices),
                "dishes_mapped": menu["dish"].nunique(),
                "ingredient_dish_links": len(menu),
            }}
