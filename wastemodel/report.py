"""
Full text report of the analysis, step by step.

Private mode shows dollars, pounds, and real names.
Public mode is run on the anonymized workbook, so names are already IDs,
and every dollar or pound total is replaced with a share of the total.
"""
from . import config
from .pipeline import DONATION_TIERS, food_group_shares

W = 90
RED = "[REDACTED]"


def _rule(title=None, char="="):
    if not title:
        return char * W
    return f"\n{char * W}\n{title.center(W)}\n{char * W}"


def _step(n, total, text):
    return f"\n[{n}/{total}] {text}"


class Report:
    def __init__(self, res, public):
        self.r, self.public = res, public
        self.e = res["events"]
        self.total_value = self.e["revenue_mid"].sum()
        self.total_lbs = self.e["lbs"].sum()
        self.lines = []

    def add(self, *lines):
        self.lines.extend(lines)

    # Numbers are shown as dollars/pounds privately, shares publicly
    def money(self, v):
        return f"{v / self.total_value:.1%}" if self.public else f"${v:,.2f}"

    def lbs(self, v):
        return f"{v / self.total_lbs:.1%}" if self.public else f"{v:,.1f} lbs"

    def build(self):
        r, e, sc, d = self.r, self.e, self.r["scale"], self.r["diagnostics"]
        prices, menu = r["prices"], r["menu"]
        mode = "Public (anonymized, shares only)" if self.public else "Full detail"
        self.add(_rule(), f"{config.PROJECT_TITLE.upper()} - ANALYSIS REPORT".center(W),
                 f"Mode: {mode}".center(W), f"Data: {config.data_label()}".center(W), _rule())

        self.add(_step(1, 9, "Loading discard log..."),
                 f"      {sc['observations']:,} discard observations across {sc['shifts']} shifts "
                 f"(~{sc['weeks']:.0f} weeks)",
                 f"      {sc['items_discarded']} distinct items discarded")
        if not self.public:
            self.add(f"      Observation window: {e['date'].min():%b %d, %Y} to {e['date'].max():%b %d, %Y}")

        conf = prices["confidence"].value_counts().sort_index(ascending=False)
        roles = prices["role"].value_counts()
        self.add(_step(2, 9, "Loading price catalog..."),
                 f"      {sc['ingredients_priced']} ingredients priced", "")
        self.table(["Price confidence rating", "Ingredients"],
                   [[f"{k:g}" + ("  (exact menu match)" if k == 5 else ""), v] for k, v in conf.items()],
                   [34, 14], indent=6)
        self.add("")
        self.table(["Operational role", "Ingredients"], [[k, v] for k, v in roles.items()],
                   [34, 14], indent=6)

        self.add(_step(3, 9, "Loading menu anchors..."),
                 f"      {sc['dishes_mapped']} dishes, {sc['ingredient_dish_links']} ingredient-to-dish links")

        self.add(_step(4, 9, "Calculating confidence-based price estimates (low / mid / high)..."),
                 f"      Generated estimates for {d['estimates']} ingredients")
        if d["excluded_low_confidence"]:
            self.add(f"      Excluded as too uncertain: {', '.join(d['excluded_low_confidence'])}")

        self.add(_step(5, 9, "Applying dish-weighted price caps..."),
                 f"      Menu-based cap available for {d['cap_available']} ingredients",
                 f"      {d['capped_below_price']} estimates lowered to stay within their dishes' menu prices")

        self.add(_step(6, 9, "Verifying dish totals against menu prices..."))
        if not d["scaled_dishes"]:
            self.add("      All dishes within menu price")
        else:
            self.add("      Dishes whose high estimates exceeded the menu price were scaled down:", "")
            if self.public:
                self.table(["Dish", "Scaled to"],
                           [[dish, f"{scale:.1%}"] for dish, _, _, scale in d["scaled_dishes"]],
                           [34, 14], indent=6)
            else:
                self.table(["Dish", "High estimate", "Menu price", "Scaled to"],
                           [[dish, f"${high:,.2f}", f"${price:,.2f}", f"{scale:.1%}"]
                            for dish, high, price, scale in d["scaled_dishes"]],
                           [34, 16, 16, 14], indent=6)

        cogs = (e["food_cost"].sum() / self.total_value) if self.total_value else 0
        self.add(_step(7, 9, "Estimating food cost (category COGS assumptions)..."),
                 f"      Blended food cost: {cogs:.1%} of estimated menu value")

        self.add(_step(8, 9, "Valuing discards..."),
                 f"      Valued {len(e):,} of {sc['observations']:,} observations")
        for item in r["unmatched_items"]:
            self.add(f"  ! Skipped '{item}': not in price catalog")
        if len(r["bad_refs"]):
            self.add(f"  ! {len(r['bad_refs'])} dish references need review")
        if self.public:
            self.add(f"      Estimated menu value associated with discards: ${RED}",
                     f"      Discarded weight:                              {RED} lbs")
        else:
            self.add(f"      Estimated menu value associated with discards: ${self.total_value:,.2f}",
                     f"        (confidence range ${e['revenue_low'].sum():,.2f} to ${e['revenue_high'].sum():,.2f})",
                     f"      Discarded weight (units x catalog unit weights): {self.total_lbs:,.1f} lbs")

        self.add(_step(9, 9, "Classifying recoverability..."))
        self.table(["Recovery tier", "Obs.", self.value_hdr, self.weight_hdr],
                   [[tier, len(t := e[e["tier"] == tier]), self.money(t["revenue_mid"].sum()),
                     self.lbs(t["lbs"].sum())] for tier in DONATION_TIERS],
                   [34, 8, 24, 24])

        self.scenarios()
        self.tax()
        self.top_items()
        self.food_groups()
        self.reasons()
        self.add("", _rule(char="-"),
                 "Notes",
                 "  Obs. = number of discard observations (log entries).",
                 "  Potential donatability is the author's estimate, based on general acceptance criteria",
                 "  shared by regional food-recovery organizations plus judgment for items not covered.",
                 "  Estimated value is reconstructed from publicly listed menu prices, not from",
                 "  financial records.")
        return "\n".join(self.lines)

    # ------------------------------------------------------------ helpers ---
    @property
    def value_hdr(self):
        return "Share of est. value" if self.public else "Est. value"

    @property
    def weight_hdr(self):
        return "Share of weight" if self.public else "Weight"

    def table(self, headers, rows, widths, indent=0):
        """Every table in the report uses this, so they all line up the same way:
        first column left-aligned, the rest right-aligned, a rule under the header."""
        pad = " " * indent
        def line(cells):
            first, rest = str(cells[0]), cells[1:]
            return pad + first[:widths[0] - 1].ljust(widths[0]) + "".join(
                str(c).rjust(w) for c, w in zip(rest, widths[1:]))
        self.add(line(headers), pad + "-" * (sum(widths)))
        self.add(*(line(r) for r in rows))

    # ----------------------------------------------------------- sections ---
    def scenarios(self):
        s = self.r["scenarios"]
        self.add(_rule("RECOVERY SCENARIOS (cumulative: each adds one practice)"))
        if self.public:
            self.add("Value and food cost are shares of total estimated menu value; weight is a share",
                     "of total discarded weight.", "")
        self.table(["Scenario", "Obs.", self.value_hdr,
                    "Share: food cost" if self.public else "Est. food cost", self.weight_hdr],
                   [[f"{i + 1}. {row['scenario']}", int(row["events"]), self.money(row["revenue_value"]),
                     self.money(row["food_cost"]), self.lbs(row["lbs"])] for i, row in s.iterrows()],
                   [25, 6, 22, 19, 18])

    def tax(self):
        self.add(_rule("TAX TREATMENT (IRC Section 170(e)(3) enhanced deduction)"),
                 "Deduction = lesser of (cost + half the markup) or (2 x cost). Deductions reduce",
                 f"taxable income; the benefit shown assumes a {config.TAX_RATE:.0%} combined rate and enough",
                 "taxable income to use it. Illustrative only, not tax advice.", "")
        s = self.r["scenarios"]
        if self.public:
            self.table(["Scenario", "Deduction", "Illustrative benefit", "Net cost"],
                       [[f"{i + 1}. {row['scenario']}", RED, RED, RED] for i, row in s.iterrows()],
                       [28, 18, 24, 20])
            return
        self.table(["Scenario", "Est. food cost", "Deduction", "Benefit", "Net cost"],
                   [[f"{i + 1}. {row['scenario']}", f"${row['food_cost']:,.2f}", f"${row['deduction']:,.2f}",
                     f"${row['tax_benefit']:,.2f}", f"${row['food_cost'] - row['tax_benefit']:,.2f}"]
                    for i, row in s.iterrows()],
                   [28, 17, 15, 15, 15])
        self.add("", "Net cost = estimated food cost of donated items minus the illustrative tax benefit.")

    def top_items(self, n=20):
        e = self.e
        by_item = e.groupby("item").agg(value=("revenue_mid", "sum"), cost=("food_cost", "sum"),
                                         lbs=("lbs", "sum"), units=("qty", "sum"),
                                         servings=("servings_lost", "sum"),
                                         category=("primary_category", "first"))
        tu, ts = by_item["units"].sum(), by_item["servings"].sum()

        self.add(_rule(f"TOP {n} ITEMS BY ESTIMATED VALUE"))
        top = by_item.nlargest(n, "value")
        if self.public:
            self.table(["Rank  Item      Category", self.value_hdr, self.weight_hdr],
                       [[f"{k:<6}{item:<10}{row['category']}", self.money(row["value"]), self.lbs(row["lbs"])]
                        for k, (item, row) in enumerate(top.iterrows(), 1)],
                       [46, 22, 22])
        else:
            self.table(["Rank  Item", "Est. value", "Est. food cost", "Weight"],
                       [[f"{k:<6}{item}", f"${row['value']:,.2f}", f"${row['cost']:,.2f}", f"{row['lbs']:,.1f} lbs"]
                        for k, (item, row) in enumerate(top.iterrows(), 1)],
                       [46, 14, 16, 14])

        self.add(_rule("MOST COMMONLY DISCARDED (BY QUANTITY)"))
        top = by_item.nlargest(n, "units")
        if self.public:
            self.table(["Rank  Item      Category", "Share of units", "Share of servings"],
                       [[f"{k:<6}{item:<10}{row['category']}", f"{row['units'] / tu:.1%}", f"{row['servings'] / ts:.1%}"]
                        for k, (item, row) in enumerate(top.iterrows(), 1)],
                       [46, 22, 22])
        else:
            self.table(["Rank  Item", "Units", "Servings"],
                       [[f"{k:<6}{item}", f"{row['units']:,.1f}", f"{row['servings']:,.0f}"]
                        for k, (item, row) in enumerate(top.iterrows(), 1)],
                       [46, 22, 22])
        self.add("", "Units are the containers or portions logged; servings = units x servings per unit.")

    def food_groups(self):
        shares = food_group_shares(self.e)
        groups = shares.groupby(level="group").sum().sort_values("value", ascending=False)
        self.add(_rule("BY FOOD GROUP AND CATEGORY"),
                 "Groups are in capitals, with their categories indented beneath. Items listed under",
                 "two categories are split evenly between them.", "")
        rows = []
        for group, row in groups.iterrows():
            rows.append([group.upper(), f"{row['value']:.1%}", f"{row['weight']:.1%}"])
            for cat, c in shares.loc[group].sort_values("value", ascending=False).iterrows():
                rows.append([f"    {cat}", f"{c['value']:.1%}", f"{c['weight']:.1%}"])
        self.table(["Food group / category", "Share of est. value", "Share of weight"], rows, [46, 22, 22])

    def reasons(self):
        self.add(_rule("BY DISCARD REASON"))
        by = self.e.groupby("reason").agg(n=("item", "size"), value=("revenue_mid", "sum"), lbs=("lbs", "sum"))
        by.index = by.index.str.strip("[] ").str.capitalize()
        self.table(["Discard reason", "Obs.", self.value_hdr, self.weight_hdr],
                   [[reason, int(row["n"]), self.money(row["value"]), self.lbs(row["lbs"])]
                    for reason, row in by.sort_values("value", ascending=False).iterrows()],
                   [34, 8, 24, 24])


def build_report(res, public=False):
    return Report(res, public).build()
