"""Plot SCF mean or median wealth in an Economist-inspired style.

Run python3 get_data.py, then python3 plot.py [--statistic mean|median].
Requires pandas and matplotlib. Mean outputs: figures/wealth_gap.png and .svg.
Median outputs: figures/wealth_gap_median.png and .svg.
"""

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.ticker import FuncFormatter, MultipleLocator
import pandas as pd

ROOT = Path(__file__).resolve().parent
BACKGROUND = "#F4F1EB"
INK = "#202020"
RED = "#E3120B"
BLUE = "#006B8F"
TEAL = "#48A6A7"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--statistic", choices=["mean", "median"], default="mean")
    args = parser.parse_args()
    statistic = args.statistic
    path = ROOT / "data" / "wealth_by_education.csv"
    if not path.exists():
        raise SystemExit("Run python3 get_data.py first.")
    summary = pd.read_csv(path)
    if summary.dollar_year.nunique() != 1:
        raise ValueError("Expected one dollar vintage")
    wide = summary.pivot(index="year", columns="group", values=f"{statistic}_net_worth")
    data = wide.rename(columns={"college": "college_value", "high_school_or_less": "high_school_value"}).reset_index()
    data["gap"] = data.college_value - data.high_school_value
    data["ratio"] = data.college_value / data.high_school_value.replace(0, float("nan"))
    data["dollar_year"] = int(summary.dollar_year.iloc[0])
    data = data.sort_values("year")
    base = int(data.dollar_year.iloc[0])
    first, last = data.iloc[0], data.iloc[-1]
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11,
                         "text.color": INK, "axes.labelcolor": INK,
                         "xtick.color": INK, "ytick.color": INK})
    fig, axes = plt.subplots(1, 2, figsize=(14, 8),
                             gridspec_kw={"width_ratios": [1.95, 1]})
    fig.patch.set_facecolor(BACKGROUND)
    fig.subplots_adjust(left=.065, right=.95, top=.70, bottom=.28, wspace=.24)
    fig.add_artist(Rectangle((.065, .925), .065, .016,
                            transform=fig.transFigure, facecolor=RED, edgecolor="none"))
    fig.text(.065, .865, "A widening wealth divide", fontsize=26, weight="bold")
    fig.text(.065, .815, "United States · Families with a child at home", fontsize=14)
    fig.text(.065, .777, f"{statistic.capitalize()} net worth by reference person’s education, {int(first.year)}–{int(last.year)}",
             fontsize=12, color="#525252")

    left, right = axes
    scale = 1e6 if statistic == "mean" else 1000
    unit = "millions" if statistic == "mean" else "thousands"
    left.set_title(f"Family wealth, {unit} of {base} dollars", loc="left", fontsize=12, pad=18)
    for column, label, color in [
        ("college_value", "Bachelor’s or higher", BLUE),
        ("high_school_value", "High school or less", TEAL),
    ]:
        left.plot(data.year, data[column] / scale, color=color, lw=3)
        left.plot(last.year, last[column] / scale, "o", color=color, ms=5)
        value = f"${last[column]/1e6:.2f}m" if last[column] >= 1e6 else f"${last[column]:,.0f}"
        left.text(last.year + 1.3, last[column] / scale,
                  f"{label}\n{value}", color=color, fontsize=10,
                  weight="bold", va="center", linespacing=1.6)
    left.set_xlim(first.year, last.year + 14)
    left.set_ylim(0, data[["college_value", "high_school_value"]].max().max() / scale * 1.12)
    left.yaxis.set_major_locator(MultipleLocator(.5 if statistic == "mean" else 100))
    left.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:.1f}" if statistic == "mean" else f"{x:.0f}"))

    right.set_title("College / high school or less, ratio", loc="left", fontsize=12, pad=18)
    right.plot(data.year, data.ratio, color=BLUE, lw=3)
    right.plot(last.year, last.ratio, "o", color=BLUE, ms=5)
    right.annotate(f"{last.ratio:.1f}×", (last.year, last.ratio),
                   xytext=(0, 15), textcoords="offset points", ha="center",
                   color=BLUE, weight="bold", fontsize=14)
    right.set_xlim(first.year, last.year + 3)
    right.set_ylim(0, data.ratio.max() * 1.15)
    right.yaxis.set_major_locator(MultipleLocator(2))
    right.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:.0f}"))
    for ax in axes:
        ax.set_facecolor(BACKGROUND)
        ax.set_xticks([1989, 2001, 2013, int(last.year)])
        ax.grid(axis="y", color="#C9C7C2", lw=.8)
        ax.set_axisbelow(True)
        ax.tick_params(axis="both", length=0, pad=10)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.axhline(0, color=INK, lw=1)

    fig.text(.065, .18,
             (f"The dollar gap grew from ${first.gap/1e6:.2f}m to ${last.gap/1e6:.2f}m."
              if statistic == "mean" else
              f"The dollar gap grew from ${first.gap:,.0f} to ${last.gap:,.0f}."),
             fontsize=15, weight="bold", parse_math=False)
    fig.text(.065, .105,
             "Families with at least one resident child, including adult children. Education is that of the reference person.\n"
             f"High school includes GED; some college/associate’s excluded. Survey-weighted {statistic}s pooling five imputations.\n"
             "Source: Federal Reserve, Survey of Consumer Finances, public summary extracts. No confidence intervals or age adjustment.",
             fontsize=10, color="#525252", va="center", linespacing=1.7)
    fig.text(.065, .025, "ECONOMIST-INSPIRED STYLE", color="#666666", fontsize=8)
    output = ROOT / "figures"
    output.mkdir(exist_ok=True)
    stem = "wealth_gap" if statistic == "mean" else "wealth_gap_median"
    for suffix in ["png", "svg"]:
        fig.savefig(output / f"{stem}.{suffix}", dpi=180, facecolor=BACKGROUND)
    plt.close(fig)
    print(output / f"{stem}.png")


if __name__ == "__main__":
    main()
