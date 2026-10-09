#!/usr/bin/env python3
"""Per-source fetch summary for CI logs (and the GitHub Actions job summary)."""
import json, os, re
from collections import defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(ROOT, "web", "data", "data.json")))
A = json.load(open(os.path.join(ROOT, "web", "data", "alloc.json")))

def src_name(s):
    s = s or "FRED"
    for k in ("FRED", "Yahoo", "FINRA", "State Street"):
        if k in s:
            return k
    return s

rows = defaultdict(lambda: [0, 0, []])  # source -> [ok, failed, ids]
for s in D["status"]:
    k = src_name(s.get("source"))
    rows[(k, "macro data.json")][0 if s["ok"] else 1] += 1
    if not s["ok"]:
        rows[(k, "macro data.json")][2].append(s["id"])
cat = {"prices": "Yahoo", "short interest": "FINRA", "shares outstanding": "State Street"}
tot = {"Yahoo": None, "FINRA": None, "State Street": None}
stale = defaultdict(list)
for x in A.get("stale", []):
    m = re.match(r"^(\S+) (.+)$", x)
    if m and m.group(2) in cat:
        stale[cat[m.group(2)]].append(m.group(1))
lines = ["| Source | Panel | OK | Failed/STALE | Failed ids |", "|---|---|---:|---:|---|"]
for (k, panel), (ok, bad, ids) in sorted(rows.items()):
    lines.append(f"| {k} | {panel} | {ok} | {bad} | {', '.join(ids)} |")
for k in ("Yahoo", "FINRA", "State Street"):
    lines.append(f"| {k} | allocation alloc.json | see log line above | {len(stale[k])} | {', '.join(stale[k][:15])}{' …' if len(stale[k]) > 15 else ''} |")
other = [f for f in A.get("failures", []) if not re.search(r" (prices|short interest|shares outstanding):", f)]
out = (f"**Data built:** macro {D['generated_utc']} UTC · allocation {A['generated_ct']} · prices through {A['price_asof']}\n\n"
       + "\n".join(lines) + (f"\n\nOther allocation issues: {'; '.join(other)}" if other else ""))
print(out)
if os.environ.get("GITHUB_STEP_SUMMARY"):
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
        f.write(out + "\n")
