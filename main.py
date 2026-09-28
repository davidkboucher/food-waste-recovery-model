"""
Run the analysis.

    python main.py            full results (dollars, pounds, names) -> outputs/  (git-ignored)
    python main.py --public   anonymized, percentage-only figures   -> docs/figures/

By default this runs on the synthetic sample workbook, so anyone can run it.
Point config.WORKBOOK at data/private/ to run it on real data.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # find wastemodel/ from any working directory

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from wastemodel import config, dashboard, pipeline  # noqa: E402
from wastemodel.anonymize import anonymize_workbook  # noqa: E402
from wastemodel.export import write_results  # noqa: E402
from wastemodel.report import build_report  # noqa: E402


def save(fig, path):
    fig.savefig(path, dpi=200, facecolor="white")
    plt.close(fig)


def run_private():
    res = pipeline.run()
    out = config.OUTPUT_DIR
    out.mkdir(exist_ok=True)
    write_results(res, out / "results.xlsx")
    save(dashboard.summary(res), out / "dashboard_summary.png")
    save(dashboard.details(res), out / "dashboard_details.png")
    save(dashboard.food_groups(res), out / "food_groups.png")

    text = build_report(res)
    (out / "report.txt").write_text(text, encoding="utf-8")
    print(text)
    print(f"\nSaved report.txt, results.xlsx, and charts to {out}/")


def run_public():
    """Anonymize first, then chart only shares and counts."""
    label = config.data_label()
    if label.startswith("SYNTHETIC"):
        print("Note: --public is running on the synthetic sample. To rebuild the published\n"
              "figures, set WORKBOOK = PRIVATE_WORKBOOK in wastemodel/config.py first.\n")
    config.DATA_LABEL = label + (" (anonymized)" if not label.startswith("SYNTHETIC") else "")
    with tempfile.TemporaryDirectory() as tmp:
        anon = Path(tmp) / "anonymized.xlsx"
        anonymize_workbook(config.WORKBOOK, anon)
        config.WORKBOOK = anon
        res = pipeline.run()
    out = config.PUBLIC_FIG_DIR
    out.mkdir(parents=True, exist_ok=True)
    save(dashboard.public_overview(res), out / "public_overview.png")
    save(dashboard.public_details(res), out / "public_details.png")
    save(dashboard.food_groups(res), out / "public_food_groups.png")
    text = build_report(res, public=True)
    (out.parent / "analysis_report.txt").write_text(text, encoding="utf-8")
    print(text)
    print(f"\nSaved anonymized, percentage-only figures to {out}/ and report to {out.parent}/")


if __name__ == "__main__":
    run_public() if "--public" in sys.argv else run_private()
