"""
Charts built from pipeline results.

Private charts (summary, details) show dollars and pounds, normalized per week.
Public charts (public_overview, public_details) show only shares, counts, and
anonymized IDs, so they can be published without the underlying totals.
"""
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

from . import config
from .pipeline import DONATION_TIERS

INK, MUTED, GRID = "#1F2933", "#7B8794", "#E4E7EB"
RED, GREEN, AMBER, BLUE = "#D64545", "#2F9E6E", "#E8A33D", "#3E6FA8"
TIER_COLORS = dict(zip(DONATION_TIERS, [GREEN, "#57B38A", "#8CCBAE", BLUE, AMBER, RED]))
money = mticker.FuncFormatter(lambda x, _: f"${x:,.0f}")
pct = mticker.FuncFormatter(lambda x, _: f"{x:.0%}")
DONATION_NOTE = ("*Potential donatability is the author's estimate: general acceptance criteria shared by two "
                 "regional food-recovery organizations, with the author's judgment applied to items those criteria "
                 "did not explicitly cover.\nMenu value is reconstructed from publicly listed menu prices and "
                 "estimated ingredient shares; it is not drawn from the operation's financial records.")

plt.rcParams.update({
    "font.family": "DejaVu Sans", "axes.edgecolor": GRID, "axes.labelcolor": INK,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False,
    "axes.spines.right": False, "axes.titleweight": "bold", "axes.titlesize": 14,
    "axes.titlelocation": "left", "axes.titlepad": 12, "axes.axisbelow": True,
})


def _kpis(fig, res):
    e, w = res["events"], res["weeks"]
    donatable = e["tier"].isin(DONATION_TIERS[:4])
    kpis = [
        (f"${e['revenue_mid'].sum() / w:,.0f}", "menu value discarded / week", RED),
        (f"{e['lbs'].sum() / w:,.0f} lbs", "food discarded / week", INK),
        (f"{e.loc[donatable, 'revenue_mid'].sum() / e['revenue_mid'].sum():.0%}",
         "of it donatable with process changes", GREEN),
        (f"${res['scenarios']['tax_benefit_per_week'].iloc[-1]:,.0f}",
         "potential tax benefit / week", BLUE),
    ]
    for i, (big, label, color) in enumerate(kpis):
        x = 0.06 + i * 0.235
        fig.text(x, 0.845, big, fontsize=30, fontweight="bold", color=color)
        fig.text(x, 0.815, label, fontsize=11, color=MUTED)


def summary(res):
    """Single-page overview sized for a LinkedIn post / portfolio."""
    e, s, w = res["events"], res["scenarios"], res["weeks"]
    fig = plt.figure(figsize=(16, 9), facecolor="white")
    fig.text(0.06, 0.94, config.PROJECT_TITLE,
             fontsize=24, fontweight="bold", color=INK)
    fig.text(0.06, 0.905, f"{config.data_label()}  ·  {len(e):,} discard events over {w:.0f} weeks  ·  "
             "values in menu dollars, averaged per week", fontsize=12, color=MUTED)
    _kpis(fig, res)
    gs = fig.add_gridspec(1, 2, left=0.16, right=0.97, top=0.72, bottom=0.08, wspace=0.25)

    # What's standing between each discard and a donation?
    ax = fig.add_subplot(gs[0, 0])
    tiers = (e.groupby("tier")["revenue_mid"].sum() / w).reindex(DONATION_TIERS[::-1])
    ax.barh(tiers.index, tiers.values, color=[TIER_COLORS[t] for t in tiers.index])
    for i, v in enumerate(tiers.values):
        ax.text(v, i, f"  ${v:,.0f}", va="center", fontsize=11, color=INK)
    ax.set_title("What would it take to donate it?")
    ax.xaxis.set_major_formatter(money)
    ax.set_xlim(0, tiers.max() * 1.25)
    ax.grid(axis="x", color=GRID)

    # Cumulative donation scenarios
    ax = fig.add_subplot(gs[0, 1])
    x = np.arange(len(s))
    ax.bar(x, s["revenue_value_per_week"], color=GREEN, alpha=0.35, label="Menu value donated")
    ax.bar(x, s["tax_benefit_per_week"], color=GREEN, label=f"Est. tax benefit ({config.TAX_RATE:.0%} rate)")
    for i, r in s.iterrows():
        ax.text(i, r["revenue_value_per_week"], f"${r['revenue_value_per_week']:,.0f}\n{r['lbs_per_week']:,.0f} lbs",
                ha="center", va="bottom", fontsize=10, color=INK)
        ax.text(i, r["tax_benefit_per_week"] / 2, f"${r['tax_benefit_per_week']:,.0f}",
                ha="center", va="center", fontsize=10, color="white", fontweight="bold")
    ax.set_xticks(x, s["scenario"], fontsize=10)
    ax.set_title("Each operational change unlocks more")
    ax.yaxis.set_major_formatter(money)
    ax.set_ylim(0, s["revenue_value_per_week"].max() * 1.22)
    ax.legend(frameon=False, loc="upper left")
    ax.grid(axis="y", color=GRID)
    return fig


def details(res):
    """Supporting charts: where waste comes from and when it happens."""
    e, s, w = res["events"], res["scenarios"], res["weeks"]
    fig, axes = plt.subplots(2, 2, figsize=(16, 10), facecolor="white")
    fig.suptitle("Where the Waste Comes From", fontsize=22, fontweight="bold", color=INK, x=0.06, ha="left")
    fig.text(0.06, 0.925, config.data_label(), fontsize=12, color=MUTED)
    fig.subplots_adjust(hspace=0.4, wspace=0.4, left=0.14, right=0.96, top=0.86)

    ax = axes[0, 0]
    top = (e.groupby("item")["revenue_mid"].sum() / w).nlargest(8).sort_values()
    ax.barh(top.index, top.values, color=BLUE)
    ax.set_title("Top items by weekly value lost")
    ax.xaxis.set_major_formatter(money)
    ax.grid(axis="x", color=GRID)

    ax = axes[0, 1]
    cats = (e.groupby("primary_category")["revenue_mid"].sum() / w).nlargest(6).sort_values()
    ax.barh(cats.index, cats.values, color=BLUE)
    ax.set_title("Top categories by weekly value lost")
    ax.xaxis.set_major_formatter(money)
    ax.grid(axis="x", color=GRID)

    ax = axes[1, 0]
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    by_date = e.groupby("date")["revenue_mid"].sum()
    dow = by_date.groupby(by_date.index.day_name()).mean().reindex(days, fill_value=0)
    ax.bar([d[:3] for d in days], dow.values,
           color=[RED if v > dow.mean() else MUTED for v in dow.values])
    ax.axhline(dow.mean(), color=INK, ls="--", lw=1)
    ax.set_title("Average value lost per logged day (red = above average)")
    ax.yaxis.set_major_formatter(money)
    ax.grid(axis="y", color=GRID)

    # Freezer payback, using only the added tax benefit from freezing
    ax = axes[1, 1]
    extra = s.loc[s["scenario"] == "+ Freezing (All)", "tax_benefit_per_week"].iloc[0] - \
        s.loc[s["scenario"] == "Donate As-Is", "tax_benefit_per_week"].iloc[0]
    weeks = np.arange(0, 157)
    ax.plot(weeks, weeks * extra, color=GREEN, lw=3, label="Cumulative added tax benefit")
    ax.axhline(config.FREEZER_COST, color=RED, ls="--", label=f"Freezer cost (${config.FREEZER_COST:,})")
    if extra > 0:
        payback = config.FREEZER_COST / extra
        ax.set_title(f"Freezer payback: ~{payback / 52:.1f} years on tax benefit alone")
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"Yr {x / 52:.0f}"))
    ax.set_xticks([0, 52, 104, 156])
    ax.yaxis.set_major_formatter(money)
    ax.legend(frameon=False, loc="lower right")
    ax.grid(color=GRID)
    return fig


# ------------------------------------------------------------ public charts ---
def _label(e, item):
    cat = e.loc[e["item"] == item, "primary_category"].iloc[0]
    return f"{item} ({cat})"


def public_overview(res):
    e, s, sc = res["events"], res["scenarios"], res["scale"]
    total, lbs = e["revenue_mid"].sum(), e["lbs"].sum()
    fig = plt.figure(figsize=(16, 9), facecolor="white")
    fig.text(0.06, 0.94, config.PROJECT_TITLE, fontsize=24, fontweight="bold", color=INK)
    fig.text(0.06, 0.905, f"Independent analysis of {sc['observations']:,} discard observations across "
             f"{sc['shifts']} shifts ({sc['weeks']:.0f} weeks) at a multi-concept restaurant operation "
             f"({config.COMPANY_ALIAS})  ·  dollar and weight totals redacted", fontsize=12, color=MUTED)
    as_is = e.loc[e["tier"] == "As-Is", "revenue_mid"].sum() / total
    kpis = [
        (f"{sc['observations']:,}", "discard observations logged", INK),
        (f"{sc['ingredients_priced']}", "ingredients priced by hand", BLUE),
        (f"{sc['dishes_mapped']} / {sc['ingredient_dish_links']}", "dishes / ingredient links mapped", BLUE),
        (f"~{as_is:.0%}*", "of est. value potentially donatable as-is", GREEN),
    ]
    for i, (big, label, color) in enumerate(kpis):
        x = 0.06 + i * 0.235
        fig.text(x, 0.815, big, fontsize=30, fontweight="bold", color=color)
        fig.text(x, 0.785, label, fontsize=11, color=MUTED)

    gs = fig.add_gridspec(1, 2, left=0.16, right=0.97, top=0.69, bottom=0.17, wspace=0.25)
    ax = fig.add_subplot(gs[0, 0])
    tiers = (e.groupby("tier")["revenue_mid"].sum() / total).reindex(DONATION_TIERS[::-1], fill_value=0)
    ax.barh(tiers.index, tiers.values, color=[TIER_COLORS[t] for t in tiers.index])
    for i, v in enumerate(tiers.values):
        ax.text(v, i, f"  {v:.0%}", va="center", fontsize=11, color=INK)
    ax.set_title("What would it take to donate it?*  (share of est. value)")
    ax.xaxis.set_major_formatter(pct)
    ax.set_xlim(0, tiers.max() * 1.25)
    ax.grid(axis="x", color=GRID)

    ax = fig.add_subplot(gs[0, 1])
    x = np.arange(len(s))
    val, wt = s["revenue_value"] / total, s["lbs"] / lbs
    ax.bar(x - 0.2, val, 0.4, color=GREEN, label="Share of estimated menu value")
    ax.bar(x + 0.2, wt, 0.4, color="#8CCBAE", label="Share of discarded weight")
    for i in range(len(s)):
        ax.text(i - 0.2, val.iloc[i], f"{val.iloc[i]:.0%}", ha="center", va="bottom", fontsize=10, color=INK)
        ax.text(i + 0.2, wt.iloc[i], f"{wt.iloc[i]:.0%}", ha="center", va="bottom", fontsize=10, color=INK)
    ax.set_xticks(x, s["scenario"], fontsize=10)
    ax.set_title("Potentially recoverable, as each practice is added*")
    ax.yaxis.set_major_formatter(pct)
    ax.set_ylim(0, 1)
    ax.legend(frameon=False, loc="upper left")
    ax.grid(axis="y", color=GRID)
    fig.text(0.06, 0.03, DONATION_NOTE, fontsize=9, color=MUTED)
    return fig


def public_details(res):
    e, prices = res["events"], res["prices"]
    total = e["revenue_mid"].sum()
    fig, axes = plt.subplots(2, 2, figsize=(16, 10), facecolor="white")
    fig.suptitle(f"{config.PROJECT_TITLE}: Methodology and Composition", fontsize=22,
                 fontweight="bold", color=INK, x=0.06, ha="left")
    fig.subplots_adjust(hspace=0.45, wspace=0.45, left=0.16, right=0.96, top=0.88, bottom=0.1)

    ax = axes[0, 0]
    conf = prices["confidence"].value_counts().sort_index()
    ax.bar([f"{c:g}" for c in conf.index], conf.values, color=BLUE)
    for i, v in enumerate(conf.values):
        ax.text(i, v, f"{v}", ha="center", va="bottom", fontsize=10, color=INK)
    ax.set_title(f"Pricing confidence across {len(prices)} ingredients")
    ax.set_xlabel("Confidence rating (5 = exact menu match)")
    ax.grid(axis="y", color=GRID)

    ax = axes[0, 1]
    top = (e.groupby("item")["revenue_mid"].sum() / total).nlargest(8).sort_values()
    ax.barh([_label(e, i) for i in top.index], top.values, color=BLUE)
    for i, v in enumerate(top.values):
        ax.text(v, i, f"  {v:.1%}", va="center", fontsize=10, color=INK)
    ax.set_title("Top items by share of est. value (anonymized)")
    ax.xaxis.set_major_formatter(pct)
    ax.set_xlim(0, top.max() * 1.25)
    ax.grid(axis="x", color=GRID)

    ax = axes[1, 0]
    from .pipeline import food_group_shares
    cats = food_group_shares(e).droplevel("group")["value"].nlargest(6).sort_values()
    ax.barh(cats.index, cats.values, color=BLUE)
    for i, v in enumerate(cats.values):
        ax.text(v, i, f"  {v:.0%}", va="center", fontsize=10, color=INK)
    ax.set_title("Share of est. value by food category")
    ax.xaxis.set_major_formatter(pct)
    ax.set_xlim(0, cats.max() * 1.25)
    ax.grid(axis="x", color=GRID)

    ax = axes[1, 1]
    reasons = (e.groupby("reason")["revenue_mid"].sum() / total).nlargest(4).sort_values()
    ax.barh(reasons.index.str.strip("[]").str.title(), reasons.values, color=BLUE)
    for i, v in enumerate(reasons.values):
        ax.text(v, i, f"  {v:.0%}", va="center", fontsize=10, color=INK)
    ax.set_title("Share of est. value by discard reason")
    ax.xaxis.set_major_formatter(pct)
    ax.set_xlim(0, reasons.max() * 1.25)
    ax.grid(axis="x", color=GRID)
    return fig


def food_groups(res):
    """Share of estimated value vs. share of weight, by food group, plus the
    category detail inside the largest group. Percentages only."""
    from .pipeline import food_group_shares
    shares = food_group_shares(res["events"])
    groups = shares.groupby(level="group").sum().sort_values("value")
    top = groups.index[-1]
    fig = plt.figure(figsize=(16, 9), facecolor="white")
    fig.text(0.06, 0.94, "What was discarded, by food group", fontsize=24, fontweight="bold", color=INK)
    g = groups.loc[top]
    note = (": value per pound, not just volume, drives the economic cost of waste."
            if g["value"] > g["weight"] else ".")
    fig.text(0.06, 0.895, f"{top} made up ~{g['value']:.0%} of estimated value and ~{g['weight']:.0%} of weight{note}",
             fontsize=13, color=MUTED)
    gs = fig.add_gridspec(1, 2, left=0.17, right=0.97, top=0.8, bottom=0.12, wspace=0.45, width_ratios=[1.2, 1])

    ax = fig.add_subplot(gs[0, 0])
    y = np.arange(len(groups))
    ax.barh(y + 0.2, groups["value"], 0.4, color=BLUE, label="Share of estimated value")
    ax.barh(y - 0.2, groups["weight"], 0.4, color="#9DB8D9", label="Share of weight")
    for i, (v, w) in enumerate(zip(groups["value"], groups["weight"])):
        ax.text(v, i + 0.2, f"  {v:.0%}", va="center", fontsize=10, color=INK)
        ax.text(w, i - 0.2, f"  {w:.0%}", va="center", fontsize=10, color=MUTED)
    ax.set_yticks(y, groups.index, fontsize=11)
    ax.set_title("Food groups: value vs. weight")
    ax.xaxis.set_major_formatter(pct)
    ax.set_xlim(0, groups[["value", "weight"]].max().max() * 1.2)
    ax.legend(frameon=False, loc="lower right")
    ax.grid(axis="x", color=GRID)

    ax = fig.add_subplot(gs[0, 1])
    detail = shares.loc[top].sort_values("value")
    ax.barh(detail.index, detail["value"], color=BLUE)
    for i, v in enumerate(detail["value"]):
        ax.text(v, i, f"  {v:.0%}", va="center", fontsize=10, color=INK)
    ax.set_title(f"Inside {top} (share of total est. value)")
    ax.xaxis.set_major_formatter(pct)
    ax.set_xlim(0, detail["value"].max() * 1.25)
    ax.grid(axis="x", color=GRID)
    fig.text(0.06, 0.03, "Items listed under two food categories are split evenly between them. "
             "Estimated value is reconstructed from publicly listed menu prices; weight is counted units "
             "times catalog unit weights.", fontsize=9, color=MUTED)
    return fig
