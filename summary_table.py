#!/usr/bin/env python3
"""Print the dashboard's 'Summary of changes' table as Markdown (for a weekly report).

  python3 summary_table.py                    # all sections, from web/data/summary.csv
  python3 summary_table.py --section "Credit Spreads" --section "Market Stress"
  python3 summary_table.py --refresh          # run fetch_data.py first
  python3 summary_table.py --ids              # include series IDs

Changes use the observation on or before each lookback date: bp for % series, % change for level
series, points for VIX / MOVE / SLOOS, days for days-to-cover. A dash means not meaningful at the series
frequency or unavailable. For twice-monthly short-interest rows the 1W column is the change vs the prior report.
"""
import argparse, csv, os, subprocess, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(ROOT, "web", "data", "summary.csv")
H = ["1w", "1m", "3m", "1y"]


def fmt_chg(v, unit):
    if v in ("", None):
        return "–"
    v = float(v)
    s = "+" if v > 0 else ("−" if v < 0 else "±")
    a = abs(v)
    if unit == "bp":
        return f"{s}{a:,.0f} bp"
    if unit == "% chg":
        return f"{s}{a:.2f}%"
    if unit.startswith("k"):
        return f"{s}{a:,.0f}k"
    return f"{s}{a:.2f}"


def load(path=CSV):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def to_markdown(rows, sections=None, ids=False):
    out, cur = [], None
    for r in rows:
        if sections and r["section"] not in sections:
            continue
        if r["section"] != cur:
            cur = r["section"]
            out += ["", f"**{cur}**", "",
                    "| Series | Units | Latest | As of | Chg in | 1W | 1M | 3M | 1Y |",
                    "|---|---|---:|---|---|---:|---:|---:|---:|"]
        name = r["series"] + (f" (`{r['series_id']}`)" if ids else "")
        if r["stale"] == "True":
            name += " ⚠ stale"
        if r["stale"] == "missing":
            out.append(f"| {name} | | unavailable | | | – | – | – | – |"); continue
        unit = r["change_unit"]
        out.append(f"| {name} | {r['units']} | {r['latest_display']} | {r['as_of']} | {unit} | "
                   + " | ".join(fmt_chg(r[f'chg_{h}'], unit) + (" (prior rpt)" if h == "1w" and r.get("basis_1w") == "prior_report" and r[f'chg_{h}'] != "" else "")
                                for h in H) + " |")
    return "\n".join(out).strip()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--section", action="append")
    ap.add_argument("--ids", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    if a.refresh:
        subprocess.run([sys.executable, os.path.join(ROOT, "fetch_data.py")], check=True)
    print(to_markdown(load(), a.section, a.ids))
