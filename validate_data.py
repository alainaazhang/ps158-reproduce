"""Validate SCF means and compute approximate 95% confidence intervals.

Run after get_data.py: python3 validate_data.py
Dependencies: numpy, pandas, openpyxl.

The Fed codebook's MEANIT procedure uses the variance of 999 bootstrap
estimates on implicate 1 (ddof=1), plus 6/5 times the variance of the five
implicate estimates (ddof=1). Effective replicate weights are WT1B * MM,
with missing values set to zero. Recompute each subgroup's denominator in
every replicate. Intervals below use pooled means +/- 1.96 * combined SE;
they are approximate normal intervals, not intervals for individual families.
Sources and hashes are recorded with the results in data/validation/.
"""

import hashlib
import json
from pathlib import Path
import zipfile
from urllib.request import urlopen

import numpy as np
import pandas as pd
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "validation"
BASE = "https://www.federalreserve.gov/econres/files/"


def source(name):
    path = OUT / name
    if not path.exists():
        with urlopen(BASE + name, timeout=180) as response:
            path.write_bytes(response.read())
    return path


def extract(year):
    path = ROOT / "data" / "raw" / "vintage_2025" / f"scfp{year}excel.zip"
    with zipfile.ZipFile(path) as z:
        return pd.read_csv(z.open(next(n for n in z.namelist() if n.lower().endswith('.csv'))))


def public_table_check():
    name = "scf2025_tables_public_real_historical.xlsx"
    table = pd.read_excel(source(name), sheet_name="Table 4", header=None)
    populations = {
        "All families": lambda d: pd.Series(True, index=d.index),
        "No high school diploma": lambda d: d.EDCL.eq(1),
        "High school diploma": lambda d: d.EDCL.eq(2),
        "Some college": lambda d: d.EDCL.eq(3),
        "College degree": lambda d: d.EDCL.eq(4),
        "Single with child(ren)": lambda d: d.FAMSTRUCT.eq(1),
        "Couple with child(ren)": lambda d: d.FAMSTRUCT.eq(4),
    }
    records = []
    for year in range(1989, 2026, 3):
        data = extract(year)
        # Each year's median heading is followed by its mean column.
        year_col = next(c for c in table.columns if table.iloc[2, c] == year)
        col = year_col + 1
        assert table.iloc[3, col] == "Mean"
        for label, mask in populations.items():
            row = table.index[table[0].astype(str).str.strip().eq(label)].item()
            selected = data.loc[mask(data)]
            computed = float(np.average(selected.NETWORTH, weights=selected.WGT))
            published = float(table.iloc[row, col]) * 1000
            records.append(dict(year=year, population=label, computed=computed,
                                published=published, difference=computed-published,
                                source=name, sheet="Table 4",
                                cell=f"{get_column_letter(col+1)}{row+1}"))
    result = pd.DataFrame(records)
    result.to_csv(OUT / "published_table_checks.csv", index=False)
    return result


def intervals():
    data = extract(2025)
    data["implicate"] = data.Y1.astype(int) % 10
    with zipfile.ZipFile(source("scf2025rw1s.zip")) as z:
        rep = pd.read_stata(z.open(next(n for n in z.namelist() if n.endswith('.dta'))))
    rep.columns = rep.columns.str.upper()
    first = data.loc[data.implicate.eq(1)].merge(rep, on="Y1", how="left", validate="one_to_one", indicator=True)
    assert first._merge.eq("both").all() and len(first) == len(rep)
    w = first[[f"WT1B{i}" for i in range(1, 1000)]].fillna(0).to_numpy()
    m = first[[f"MM{i}" for i in range(1, 1000)]].fillna(0).to_numpy()
    weights = np.maximum(w, 0) * np.maximum(m, 0)
    assert np.isfinite(weights).all() and (weights.sum(axis=0) > 0).all()
    groups = {
        "college_with_children": lambda d: d.EDCL.eq(4) & d.KIDS.gt(0),
        "high_school_or_less_with_children": lambda d: d.EDCL.isin([1, 2]) & d.KIDS.gt(0),
        "all_college": lambda d: d.EDCL.eq(4),
        "all_families": lambda d: pd.Series(True, index=d.index),
    }
    results = {}
    for label, select in groups.items():
        sub = data.loc[select(data)]
        point = float(np.average(sub.NETWORTH, weights=sub.WGT))
        estimates = [float(np.average(g.NETWORTH, weights=g.WGT))
                     for _, g in sub.groupby("implicate")]
        assert len(estimates) == 5
        chosen = select(first).to_numpy()
        rw = weights[chosen]
        denominator = rw.sum(axis=0)
        assert (denominator > 0).all()
        replicate_estimates = (first.loc[chosen, "NETWORTH"].to_numpy() @ rw) / denominator
        sampling = float(np.var(replicate_estimates, ddof=1))
        imputation = float(np.var(estimates, ddof=1))
        se = float(np.sqrt(sampling + 1.2 * imputation))
        moe = 1.96 * se
        results[label] = dict(mean=point, standard_error=se, margin_of_error_95=moe,
                              lower_95=point-moe, upper_95=point+moe,
                              first_implicate_sample_families=int(chosen.sum()),
                              unique_sample_families=int(sub.YY1.nunique()),
                              sampling_variance=sampling, imputation_variance=imputation,
                              implicate_means=estimates, mean_of_implicate_means=float(np.mean(estimates)),
                              replicates=999)
    # The target estimate must agree with the plotted data.
    chart = pd.read_csv(ROOT / "data" / "wealth_gap.csv").set_index("year")
    assert np.isclose(results["college_with_children"]["mean"], chart.loc[2025, "college_mean"])
    return results


def main():
    OUT.mkdir(exist_ok=True)
    checks = public_table_check()
    cis = intervals()
    source("codebk2025.txt")
    internal = pd.read_excel(source("scf2025_tables_internal_real_historical.xlsx"),
                             sheet_name="Table 4", header=None)
    row = internal.index[internal[0].astype(str).str.strip().eq("College degree")].item()
    col = next(c for c in internal.columns if internal.iloc[2, c] == 2025) + 1
    report_college = float(internal.iloc[row, col]) * 1000
    se_table = pd.read_excel(source("2025_tables1_2_stderrs.xlsx"),
                             sheet_name="Table 2", header=None)
    se_row = se_table.index[se_table[0].astype(str).str.strip().eq("All families")].item()
    published_all_family_se = float(se_table.iloc[se_row, 8]) * 1000
    worst = checks.iloc[checks.difference.abs().argmax()].to_dict()
    # The public tables are rounded to $10. Exceeding that rounding error
    # is reported explicitly rather than silently treating the check as passed.
    passed = bool(checks.difference.abs().le(5.01).all())
    results = dict(year=2025, dollar_year=2025, method=__doc__,
                   published_comparisons=len(checks),
                   all_match_within_5_dollars=passed, largest_difference=worst,
                   internal_table_all_college_mean=report_college,
                   internal_table_cell=f"Table 4!{get_column_letter(col+1)}{row+1}",
                   standard_error_benchmark=dict(
                       public_data_computed=cis["all_families"]["standard_error"],
                       internal_data_published=published_all_family_se,
                       cell=f"Table 2!I{se_row+1}",
                       note="Different public/confidential data; not an exact-equality test."
                   ),
                   intervals=cis,
                   sources=[dict(file=p.name, url=BASE+p.name,
                                 sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                            for p in OUT.iterdir() if p.suffix in ['.xlsx', '.zip', '.txt']])
    (OUT / "validation_results.json").write_text(json.dumps(results, indent=2)+"\n")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
