"""Download SCF public summary extracts, 1989 through the latest released wave.

Run: python3 get_data.py [--refresh]
Requires: requests, pandas, numpy. Outputs live in data/ beside this script.

Education is that of the reference person, not both partners or their parents.
Families with KIDS>0 are included: at least one resident child of the reference
person or spouse/partner, with no under-18 restriction. EDCL=3 (some college/
associate's) is excluded. NETWORTH is assets minus debts, including housing and business
equity. Dollar amounts are already adjusted by the Fed; do not deflate again.
The pooled point estimates use all five implicates and the supplied WGT,
which already incorporates the division by five. No standard errors are
estimated: those require the survey's replicate weights and imputation rules.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
from urllib.parse import urljoin
import zipfile

import numpy as np
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parent
INDEX = "https://www.federalreserve.gov/econres/scfindex.htm"
MACRO = "https://www.federalreserve.gov/econres/files/bulletin.macro.txt"
GROUPS = {"college": [4], "high_school_or_less": [1, 2]}


def fetch(url):
    with requests.Session() as session:
        session.mount("https://", HTTPAdapter(max_retries=Retry(
            total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])))
        response = session.get(url, timeout=(20, 120))
        response.raise_for_status()
        return response.content


def weighted_median(values, weights):
    """Inverse weighted empirical CDF at 0.5; retain zero/negative wealth."""
    order = np.argsort(values, kind="stable")
    values, weights = np.asarray(values)[order], np.asarray(weights)[order]
    return float(values[np.searchsorted(np.cumsum(weights), weights.sum() / 2)])


def load_wave(year, base_year, raw, refresh):
    page_url = INDEX if year == base_year else f"https://www.federalreserve.gov/econres/scf_{year}.htm"
    page_path = raw / f"scf_{year}.html"
    if refresh or not page_path.exists():
        page_path.write_bytes(fetch(page_url))
    page = page_path.read_text(encoding="utf-8-sig")
    # Refuse to silently mix extracts from different inflation vintages.
    plain = re.sub(r"<[^>]+>", " ", page)
    if not re.search(rf"inflation.adjusted\s+to\s+{base_year}\s+dollars", plain, re.I):
        raise ValueError(f"Cannot confirm {base_year}-dollar units on {page_url}")
    links = re.findall(r'href=["\']([^"\']+)["\']', page, re.I)
    candidates = [urljoin(page_url, link) for link in links
                  if re.search(rf"scfp{year}excel\.zip$", link, re.I)]
    if len(set(candidates)) != 1:
        raise ValueError(f"Expected one CSV summary-extract link on {page_url}")
    url = candidates[0]
    path = raw / f"scfp{year}excel.zip"
    if refresh or not path.exists():
        payload = fetch(url)
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            if archive.testzip() is not None:
                raise ValueError(f"Corrupt archive: {url}")
        path.write_bytes(payload)
    payload = path.read_bytes()
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith(".csv")]
        if len(names) != 1:
            raise ValueError(f"Expected one CSV in {path}")
        frame = pd.read_csv(archive.open(names[0]))
    frame.columns = frame.columns.str.upper()
    id_col = "X1" if year == 1989 else "Y1"
    columns = [id_col, "WGT", "EDCL", "NETWORTH", "KIDS"]
    frame = frame[columns].rename(columns={id_col: "IMPLICATE_ID"})
    if frame.isna().any().any() or not np.isfinite(frame.to_numpy()).all():
        raise ValueError(f"Missing or non-finite data in {year}")
    if not frame.EDCL.isin([1, 2, 3, 4]).all() or not (frame.WGT > 0).all():
        raise ValueError(f"Invalid education or weights in {year}")
    if not (frame.KIDS.ge(0) & frame.KIDS.eq(frame.KIDS.astype(int))).all():
        raise ValueError(f"Invalid resident child counts in {year}")
    ids = frame.IMPLICATE_ID.astype("int64")
    if not (ids == frame.IMPLICATE_ID).all() or ids.duplicated().any():
        raise ValueError(f"Invalid implicate IDs in {year}")
    counts = frame.groupby(ids // 10).size()
    if not counts.eq(5).all() or set(ids % 10) != {1, 2, 3, 4, 5}:
        raise ValueError(f"Expected five implicates per family in {year}")
    rows = []
    for group, codes in GROUPS.items():
        subset = frame.loc[frame.EDCL.isin(codes) & frame.KIDS.gt(0)]
        if subset.empty:
            raise ValueError(f"Empty group: {year} {group}")
        rows.append(dict(year=year, group=group, dollar_year=base_year,
                         median_net_worth=weighted_median(subset.NETWORTH, subset.WGT),
                         mean_net_worth=float(np.average(subset.NETWORTH, weights=subset.WGT)),
                         weighted_families=float(subset.WGT.sum()),
                         sample_families=int((subset.IMPLICATE_ID.astype("int64") // 10).nunique()),
                         implicate_records=len(subset)))
    metadata = dict(year=year, page_url=page_url, download_url=url,
                    sha256=hashlib.sha256(payload).hexdigest(),
                    records=len(frame), families=len(counts))
    print(f"{year}: {len(counts):,} families", flush=True)
    return rows, metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="Download archives again")
    args = parser.parse_args()
    index = fetch(INDEX).decode("utf-8-sig")
    match = re.search(r"The\s+(20\d{2})\s+Survey of Consumer Finances", index)
    if match is None:
        raise ValueError("Cannot identify the latest survey on the Fed index")
    latest = int(match.group(1))
    if (latest - 1989) % 3:
        raise ValueError(f"Unexpected survey year: {latest}")
    data = ROOT / "data"
    raw = data / "raw" / f"vintage_{latest}"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "scfindex.html").write_text(index)
    (raw / "bulletin.macro.txt").write_bytes(fetch(MACRO))
    years = list(range(1989, latest + 1, 3))
    with ThreadPoolExecutor(max_workers=4) as pool:
        waves = list(pool.map(lambda year: load_wave(year, latest, raw, args.refresh), years))
    summary = pd.DataFrame([row for rows, _ in waves for row in rows])
    summary.to_csv(data / "wealth_by_education.csv", index=False)
    wide = summary.pivot(index="year", columns="group", values="mean_net_worth")
    gap = pd.DataFrame({"college_mean": wide.college,
                        "high_school_or_less_mean": wide.high_school_or_less})
    gap["mean_gap"] = wide.college - wide.high_school_or_less
    gap["mean_ratio"] = wide.college / wide.high_school_or_less.replace(0, np.nan)
    gap["dollar_year"] = latest
    gap.to_csv(data / "wealth_gap.csv")
    manifest = dict(retrieved_utc=datetime.now(timezone.utc).isoformat(),
                    index_url=INDEX, definitions_url=MACRO, latest_survey=latest,
                    dollar_year=latest, years=years, groups=GROUPS,
                    estimator="Pooled five-implicate weighted mean; sum(NETWORTH*WGT)/sum(WGT)",
                    population="SCF families with KIDS>0, grouped by reference-person education",
                    child_definition="Resident child of reference person or spouse/partner; no age restriction",
                    uncertainty="Point estimates only; no replicate-weight standard errors",
                    sources=[metadata for _, metadata in waves])
    (data / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(gap.to_string(float_format=lambda x: f"{x:,.2f}"))


if __name__ == "__main__":
    main()
