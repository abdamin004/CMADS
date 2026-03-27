"""
explore_synthea.py — Synthea batch_test output explorer
Clinical AI Data Lake — Bronze layer reconnaissance

Loads all CSV tables, prints schemas, row counts, and clinical
distributions. Saves top_conditions.png to the same directory.
"""

import os
import sys
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import matplotlib
matplotlib.use("Agg")           # headless — no display needed
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from pathlib import Path
from datetime import date

# ── Paths ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
CSV_DIR      = PROJECT_ROOT / "data" / "raw" / "batch_test" / "csv"
PLOT_OUT     = SCRIPT_DIR / "top_conditions.png"

SEP  = "=" * 70
SEP2 = "-" * 70

def banner(title: str) -> None:
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)

def sub(title: str) -> None:
    print(f"\n{SEP2}")
    print(f"  {title}")
    print(SEP2)

# ── 1. Load ALL CSVs ──────────────────────────────────────────────────────────
banner("1 · LOADING ALL CSV FILES")

csv_files = sorted(CSV_DIR.glob("*.csv"))
tables: dict[str, pd.DataFrame] = {}

for path in csv_files:
    df = pd.read_csv(path, low_memory=False)
    tables[path.stem] = df
    print(f"  ✓  {path.name:<35s}  {len(df):>8,} rows  ×  {df.shape[1]:>2} cols")

# ── 2. Schema (dtypes) for each table ─────────────────────────────────────────
banner("2 · SCHEMAS (dtypes per table)")

for name, df in tables.items():
    sub(f"Table: {name}")
    schema = pd.DataFrame({
        "dtype"     : df.dtypes.astype(str),
        "non_null"  : df.notna().sum(),
        "null_%"    : (df.isna().mean() * 100).round(1),
        "sample"    : [str(df[c].dropna().iloc[0])[:60] if df[c].notna().any() else "—"
                       for c in df.columns],
    })
    print(schema.to_string())

# ── 3. patients.csv deep-dive ─────────────────────────────────────────────────
banner("3 · PATIENTS — Age, Gender, Race")

pts = tables["patients"].copy()
today = date.today()

# Parse birth/death dates; compute age
pts["BIRTHDATE"] = pd.to_datetime(pts["BIRTHDATE"])
pts["DEATHDATE"] = pd.to_datetime(pts["DEATHDATE"], errors="coerce")
pts["end_date"]  = pts["DEATHDATE"].fillna(pd.Timestamp(today))
pts["age_years"] = ((pts["end_date"] - pts["BIRTHDATE"]).dt.days / 365.25).round(1)

sub("Age distribution")
bins   = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 120]
labels = ["0–9","10–19","20–29","30–39","40–49","50–59","60–69","70–79","80–89","90+"]
pts["age_band"] = pd.cut(pts["age_years"], bins=bins, labels=labels, right=False)
age_dist = pts["age_band"].value_counts().sort_index()
for band, n in age_dist.items():
    bar = "█" * int(n / max(age_dist) * 30)
    print(f"  {band:>6s}  {n:4d}  {bar}")

print(f"\n  Mean age : {pts['age_years'].mean():.1f} yrs")
print(f"  Median   : {pts['age_years'].median():.1f} yrs")
print(f"  Min      : {pts['age_years'].min():.1f} yrs")
print(f"  Max      : {pts['age_years'].max():.1f} yrs")

sub("Gender split")
gender = pts["GENDER"].value_counts()
for g, n in gender.items():
    pct = n / len(pts) * 100
    print(f"  {g}   {n:4d}  ({pct:.1f}%)")

sub("Race distribution")
race = pts["RACE"].value_counts()
for r, n in race.items():
    pct = n / len(pts) * 100
    bar = "█" * int(pct / 2)
    print(f"  {r:<25s}  {n:4d}  ({pct:5.1f}%)  {bar}")

sub("Ethnicity distribution")
eth = pts["ETHNICITY"].value_counts()
for e, n in eth.items():
    pct = n / len(pts) * 100
    print(f"  {e:<25s}  {n:4d}  ({pct:5.1f}%)")

# ── 4. conditions.csv — top 20 ────────────────────────────────────────────────
banner("4 · CONDITIONS — Top 20 by DESCRIPTION")

cond = tables["conditions"]
top_cond = cond["DESCRIPTION"].value_counts().head(20)
for i, (desc, n) in enumerate(top_cond.items(), 1):
    pct = n / len(cond) * 100
    print(f"  {i:2d}. {n:5,d} ({pct:4.1f}%)  {desc}")

# Active vs resolved
cond_active   = cond["STOP"].isna().sum()
cond_resolved = cond["STOP"].notna().sum()
print(f"\n  Active (no STOP date)  : {cond_active:,}")
print(f"  Resolved (has STOP)    : {cond_resolved:,}")

# Unique patients with any condition
print(f"  Unique patients        : {cond['PATIENT'].nunique():,}")

# Disease module targets
sub("Target disease module conditions")
targets = {
    "Diabetes / Metabolic Syndrome" : ["diabetes", "metabolic syndrome", "prediabetes", "hba1c", "neuropathy due to type 2"],
    "Chronic Kidney Disease"        : ["kidney disease", "renal", "microalbuminuria", "proteinuria due to type 2", "transplantation of kidney"],
    "Heart Failure / Cardiac"       : ["heart failure", "congestive", "coronary", "ischemic", "myocardial", "cardiomegaly"],
    "Hypertension"                  : ["hypertension", "hypertensive"],
}
for label, keywords in targets.items():
    hits = cond[cond["DESCRIPTION"].str.lower().str.contains("|".join(keywords), na=False)]
    unique_pts = hits["PATIENT"].nunique()
    print(f"\n  [{label}]  {len(hits):,} records  |  {unique_pts} patients")
    for desc, n in hits["DESCRIPTION"].value_counts().head(5).items():
        print(f"      {n:4d}  {desc}")

# ── 5. observations.csv — top 15 types + value ranges ────────────────────────
banner("5 · OBSERVATIONS — Top 15 types + value ranges")

obs = tables["observations"]
sub("Data type split")
print(obs["TYPE"].value_counts().to_string())

sub("Top 15 observation types (numeric) with value ranges")
obs_num = obs[obs["TYPE"] == "numeric"].copy()
obs_num["VALUE"] = pd.to_numeric(obs_num["VALUE"], errors="coerce")

top_loinc = obs_num["DESCRIPTION"].value_counts().head(15).index
stats = (
    obs_num[obs_num["DESCRIPTION"].isin(top_loinc)]
    .groupby("DESCRIPTION")["VALUE"]
    .agg(count="count", mean="mean", std="std", min="min", p25=lambda x: x.quantile(0.25),
         median="median", p75=lambda x: x.quantile(0.75), max="max")
    .sort_values("count", ascending=False)
)
# Also grab units
units = obs_num.groupby("DESCRIPTION")["UNITS"].agg(lambda x: x.mode().iloc[0] if x.notna().any() else "")
stats = stats.join(units)
pd.set_option("display.float_format", "{:.2f}".format)
pd.set_option("display.max_columns", 20)
pd.set_option("display.width", 120)
print(stats.to_string())

sub("Top 15 observation types (text/categorical) with value counts")
obs_txt = obs[obs["TYPE"].isin(["text", "boolean"])].copy()
top_txt_loinc = obs_txt["DESCRIPTION"].value_counts().head(15).index
for desc in top_txt_loinc:
    vals = obs_txt[obs_txt["DESCRIPTION"] == desc]["VALUE"].value_counts().head(5)
    n_total = len(obs_txt[obs_txt["DESCRIPTION"] == desc])
    print(f"\n  {desc}  [{n_total:,} records]")
    for v, cnt in vals.items():
        print(f"      {cnt:5,d}  {str(v)[:80]}")

# ── 6. medications.csv — top 15 ───────────────────────────────────────────────
banner("6 · MEDICATIONS — Top 15 most prescribed")

meds = tables["medications"]
top_meds = meds["DESCRIPTION"].value_counts().head(15)
for i, (desc, n) in enumerate(top_meds.items(), 1):
    pct = n / len(meds) * 100
    print(f"  {i:2d}. {n:5,d} ({pct:4.1f}%)  {desc}")

# Active vs stopped
meds_active = meds["STOP"].isna().sum()
meds_stopped = meds["STOP"].notna().sum()
print(f"\n  Active (no STOP)  : {meds_active:,}")
print(f"  Stopped           : {meds_stopped:,}")
print(f"  Unique patients   : {meds['PATIENT'].nunique():,}")

# ── 7. encounters.csv — type distribution ─────────────────────────────────────
banner("7 · ENCOUNTERS — Class & type distribution")

enc = tables["encounters"]
sub("Encounter class (ENCOUNTERCLASS)")
enc_class = enc["ENCOUNTERCLASS"].value_counts()
for cls, n in enc_class.items():
    pct = n / len(enc) * 100
    bar = "█" * int(pct / 1.5)
    print(f"  {cls:<22s}  {n:6,d}  ({pct:5.1f}%)  {bar}")

sub("Top 15 encounter descriptions (DESCRIPTION)")
enc_desc = enc["DESCRIPTION"].value_counts().head(15)
for i, (desc, n) in enumerate(enc_desc.items(), 1):
    pct = n / len(enc) * 100
    print(f"  {i:2d}. {n:5,d} ({pct:4.1f}%)  {desc}")

sub("Encounter cost summary (BASE_ENCOUNTER_COST)")
cost = enc["BASE_ENCOUNTER_COST"].describe()
print(cost.to_string())

# Avg encounters per patient
avg_enc = len(enc) / enc["PATIENT"].nunique()
print(f"\n  Unique patients          : {enc['PATIENT'].nunique():,}")
print(f"  Avg encounters/patient   : {avg_enc:.1f}")

# ── 8. Plot: top 10 conditions bar chart ─────────────────────────────────────
banner("8 · PLOT — Top 10 conditions → top_conditions.png")

top10 = cond["DESCRIPTION"].value_counts().head(10)

fig, ax = plt.subplots(figsize=(11, 6))
colors = plt.cm.Blues_r([i / 12 for i in range(10)])
bars = ax.barh(top10.index[::-1], top10.values[::-1], color=colors[::-1], edgecolor="white", linewidth=0.5)

for bar, val in zip(bars, top10.values[::-1]):
    ax.text(bar.get_width() + 10, bar.get_y() + bar.get_height() / 2,
            f"{val:,}", va="center", ha="left", fontsize=9, color="#333333")

ax.set_xlabel("Number of occurrences", fontsize=10)
ax.set_title("Top 10 Conditions — Synthea batch_test (121 patients)\nClinical AI Data Lake", fontsize=12, fontweight="bold")
ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.tick_params(axis="y", labelsize=8.5)
plt.tight_layout()
fig.savefig(PLOT_OUT, dpi=150, bbox_inches="tight")
plt.close()
print(f"  Saved → {PLOT_OUT}")

# ── 9. Summary table ──────────────────────────────────────────────────────────
banner("9 · SUMMARY — All tables")

print(f"\n  {'Table':<30s}  {'Rows':>10s}  {'Cols':>6s}  {'Null cols':>10s}")
print(f"  {'-'*30}  {'-'*10}  {'-'*6}  {'-'*10}")
for name, df in sorted(tables.items()):
    null_cols = (df.isna().any()).sum()
    print(f"  {name:<30s}  {len(df):>10,}  {df.shape[1]:>6}  {null_cols:>10}")

print(f"\n  Total tables : {len(tables)}")
print(f"  Total rows   : {sum(len(df) for df in tables.values()):,}")
print()
