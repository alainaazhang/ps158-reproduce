# Wealth by parents’ education in the United States

This project reproduces the POLISCI 158 workshop’s wealth-by-education figure
from survey data, covering 1989–2025. The figures show net worth for two
education groups and the ratio between them, in an Economist-inspired style:

- **Mean:** `figures/wealth_gap.png` and `.svg`.
- **Median variation:** `figures/wealth_gap_median.png` and `.svg`.

## Data and definitions

Data come from the Federal Reserve’s [Survey of Consumer Finances (SCF)](https://www.federalreserve.gov/econres/scfindex.htm),
using the **CSV Summary Extract Public Data** for each three-year survey wave.
The latest released survey when this project was made was **2025**.

We include **families with a child at home** (`KIDS > 0`), including adult
children. Education refers to the **family reference person**, not both
parents: bachelor’s degree or higher (`EDCL = 4`) versus high school/GED or
less (`EDCL = 1 or 2`). Some-college/associate’s families are excluded.

Net worth (`NETWORTH`) is assets minus debts, including zero and negative
values. All amounts are in **2025 dollars**, already adjusted by the Fed;
the scripts do not adjust inflation again. Estimates pool all five imputations
using `WGT`, which already includes division by five. Medians use the point
where cumulative survey weight reaches 50% within each group.

## Rerun

From the project directory, with Python 3 and internet access:

```sh
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install requests numpy pandas matplotlib openpyxl
python3 get_data.py
python3 plot.py --statistic mean
python3 plot.py --statistic median
```

The downloader discovers the latest released wave, saves source archives under
`data/raw/`, and writes summary CSVs and `data/manifest.json` with source URLs
and hashes. Cached archives are reused; `python3 get_data.py --refresh`
downloads them again. Plot outputs are saved under `figures/`.

## Checks and limitations

```sh
python3 validate_data.py
```

This additional check currently targets the **2025 release**. It reproduces
91 comparable mean estimates in the Fed’s public historical tables to within
$4.99 (rounding to $10), and uses 999 replicate weights plus imputation
variation to calculate approximate 95% confidence intervals. Results and
source-cell references are saved under `data/validation/`.

The 2025 college-with-children mean is about **$2.29 million**, with an
approximate 95% interval of **$2.07–$2.51 million**. This interval does not
apply to the median. Neither figure displays confidence intervals. These
are descriptive comparisons of different samples over time, without age
adjustment; they do not establish that education causes wealth differences.
