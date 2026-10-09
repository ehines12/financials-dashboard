#!/usr/bin/env python3
"""Print the Financials Time Allocation 'where to look' score table as markdown (for the Friday report).

Reads web/data/alloc.json (built by fetch_alloc.py). Values are printed exactly as computed.
Usage: python3 allocation_table.py [--perf] [--path web/data/alloc.json]
"""
import argparse
import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
COMP = [("rel_perf", "Rel. perf"), ("positioning", "Positioning"),
        ("macro_beta_shift", "Macro-beta shift"), ("technical_stretch", "Tech. stretch")]


def f2(v):
    return "–" if v is None else f"{v:.2f}"


def sgn(v, d=2, suf=""):
    if v is None:
        return "–"
    return f"{v:+.{d}f}{suf}".replace("-", "−")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default=os.path.join(ROOT, "web", "data", "alloc.json"))
    ap.add_argument("--perf", action="store_true", help="also print the 1M relative-performance rank table")
    a = ap.parse_args()
    with open(a.path, encoding="utf-8") as fh:
        A = json.load(fh)
    settle = next((p.get("settle") for p in A["positioning"] if p["id"] == "XLF"), None)
    print(f"**Financials time allocation: where to look** (prices through {A['price_asof']}; "
          f"FINRA SI settlement {settle or 'n/a'}; built {A['generated_ct']})\n")
    print("| # | Group | Score | " + " | ".join(n for _, n in COMP) + " | Why look |")
    print("|---:|---|---:|" + "---:|" * len(COMP) + "---|")
    for s in A["scores"]:
        comps = " | ".join(f2(s["components"].get(k)) for k, _ in COMP)
        print(f"| {s['rank']} | {s['label']} | {f2(s['score'])} | {comps} | {s['reason']} |")
    print("\n_Score = equal-weight mean of |z| components (each capped at 3): 21-day return vs XLF; "
          "short-interest days-to-cover level and 1M change; 3M shift in 6M macro betas relative to the peer median; "
          "200DMA gap and realized vol. Higher = more unusual, not a buy/sell signal._")
    if A.get("stale") or A.get("failures"):
        print(f"\n_Data issues: STALE {', '.join(A.get('stale') or []) or 'none'}; "
              f"failures: {'; '.join(A.get('failures') or []) or 'none'}._")
    if a.perf:
        print("\n| Rank | Group | 1M TR | 1M vs XLF | 3M vs XLF | YTD vs XLF |")
        print("|---:|---|---:|---:|---:|---:|")
        rows = sorted((p for p in A["perf"] if not p["bench"]), key=lambda p: p.get("rank_1m") or 99)
        for p in rows:
            print(f"| {p['rank_1m']} | {p['label']} | {sgn(p['ret']['1m'], 2, '%')} | {sgn(p['rel_xlf']['1m'], 2, 'pp')} | "
                  f"{sgn(p['rel_xlf']['3m'], 2, 'pp')} | {sgn(p['rel_xlf']['ytd'], 2, 'pp')} |")
        for p in A["perf"]:
            if p["bench"]:
                print(f"| bench | {p['label']} | {sgn(p['ret']['1m'], 2, '%')} | | | |")
    bask = [g for g in A["groups"] if g["basket"]]
    if bask:
        print("\n_Illustrative equal-weight baskets: " + "; ".join(f"{g['label']}: {', '.join(g['members'])}" for g in bask) + "._")


if __name__ == "__main__":
    main()
