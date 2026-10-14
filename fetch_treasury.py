"""Snapshot of CNBC/Tradeweb Treasury quotes -> web/data/treasury.json (fallback for the live strip).
Keeps the previous good quote per symbol if CNBC fails or omits one."""
import json, os, subprocess, datetime
SYMS = ["US1M","US3M","US6M","US1Y","US2Y","US5Y","US10Y","US20Y","US30Y"]
URL = ("https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol?symbols=" + "|".join(SYMS) +
       "&requestMethod=itv&noform=1&partnerId=2&fund=1&exthrs=1&output=json")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "data", "treasury.json")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129 Safari/537.36"

def num(s):
    try: return float(str(s).replace("%", "").replace("+", ""))
    except Exception: return None

old = {}
if os.path.exists(OUT):
    try: old = json.load(open(OUT)).get("quotes", {})
    except Exception: old = {}
quotes, ok = dict(old), 0
try:
    raw = subprocess.run(["curl", "-s", "--max-time", "20", "-A", UA, URL], capture_output=True, text=True, timeout=30).stdout
    for q in json.loads(raw)["FormattedQuoteResult"]["FormattedQuote"]:
        last, prev = num(q.get("last")), num(q.get("previous_day_closing"))
        if q.get("symbol") in SYMS and last is not None and q.get("last_time"):
            quotes[q["symbol"]] = {"last": last, "prev": prev, "time": q["last_time"], "name": q.get("shortName")}
            ok += 1
except Exception as e:
    print("treasury: CNBC fetch failed:", e)
quotes = {k: v for k, v in quotes.items() if k in SYMS}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump({"fetched": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
           "source": "CNBC/Tradeweb", "quotes": quotes}, open(OUT, "w"), indent=1)
print(f"treasury: {ok}/{len(SYMS)} live quotes, {len(quotes)} in snapshot")
