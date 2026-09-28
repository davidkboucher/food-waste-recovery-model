"""Every modeling assumption lives here, so results are easy to audit and change."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECT_TITLE = "Restaurant Food Waste & Recovery Model"
COMPANY_ALIAS = "Company_X"          # the operation is never named in public outputs

# Workbook to analyze. The sample is synthetic and anonymized, so the code runs
# for anyone. The real workbook lives in data/private/ and is never committed.
SAMPLE_WORKBOOK = ROOT / "data" / "sample" / "sample_workbook.xlsx"
PRIVATE_WORKBOOK = ROOT / "data" / "private" / "company_x.xlsx"
WORKBOOK = SAMPLE_WORKBOOK


DATA_LABEL = None   # set automatically in public mode (which runs on a temp copy)


def data_label():
    """Says which data a report or chart came from, so sample output is never
    mistaken for real results."""
    if DATA_LABEL:
        return DATA_LABEL
    if Path(WORKBOOK).resolve() == SAMPLE_WORKBOOK.resolve():
        return "SYNTHETIC SAMPLE DATA (scrambled; not real figures)"
    return "Real data"

OUTPUT_DIR = ROOT / "outputs"                 # full results (git-ignored)
PUBLIC_FIG_DIR = ROOT / "docs" / "figures"    # redacted, percentage-only figures

DISCARD_SHEET = "Discard Log"
PRICE_SHEET = "Price Data"
MENU_SHEET = "Menu Anchors"
INTERCHANGEABLE_SHEET = "Interchangeable"    # optional; overrides INTERCHANGEABLE below

GRAMS_PER_LB = 453.592

# Ingredients the kitchen uses interchangeably: a recipe that lists one counts
# for any of them. Normally read from the workbook's "Interchangeable" sheet
# (columns Group, Item); this list is only a fallback if that sheet is missing.
# Example: [["Item A (bulk)", "Item A (tin)"]]
INTERCHANGEABLE = []

# Price confidence (1-5 scale) -> +/- margin applied to the per-serving price.
# Items below the lowest threshold are excluded as too uncertain.
CONFIDENCE_MARGINS = [(5.0, 0.0), (4.5, 0.05), (4.0, 0.075), (3.5, 0.10),
                      (3.0, 0.125), (2.5, 0.15), (2.0, 0.20)]

# ASSUMPTION: typical cost of goods sold as a % of menu price, by food category
# (general industry ranges, not the operation's actual costs).
CATEGORY_COGS_PCT = {
    "Poultry": 30, "Red Meat": 35, "Seafood": 35, "Vegetables": 18,
    "Herbs & Garnishes": 10, "Sauces & Condiments": 18, "Dairy": 25,
    "Dairy Alternatives": 25, "Grains": 15, "Starches": 15,
    "Legumes": 18, "Plant Proteins": 22, "Fruits": 20,
    "Seasonings": 12, "Prepared Components": 25, "Mixed Proteins": 32,
}
DEFAULT_COGS_PCT = 25

# Broad food groups for reporting, built from the catalog's food categories.
# Items listed under two categories are split evenly between them.
FOOD_GROUPS = {
    "Proteins": ["Poultry", "Red Meat", "Seafood", "Plant Proteins", "Mixed Proteins"],
    "Grains & Starches": ["Grains", "Starches"],
    "Produce & Legumes": ["Vegetables", "Fruits", "Herbs & Garnishes", "Legumes"],
    "Dairy": ["Dairy", "Dairy Alternatives"],
    "Sauces & Seasonings": ["Sauces & Condiments", "Seasonings"],
    "Soups & Prepared": ["Soup", "Prepared Components"],
}

# ASSUMPTION: illustrative combined tax rate (21% federal + ~6% state). Not tax advice.
TAX_RATE = 0.27

# ASSUMPTION: one-time cost of added freezer capacity, for the payback estimate.
FREEZER_COST = 5_500
