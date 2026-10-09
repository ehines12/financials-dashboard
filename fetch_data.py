#!/usr/bin/env python3
"""Pull macro series from FRED (public no-key CSV endpoint) into web/data/data.json.

- Idempotent: rewrites the JSON atomically each run (temp file + rename).
- Robust: each series is fetched independently with retries. If one fails, the
  previous copy of that series (if any) is kept and flagged as stale; the rest
  of the dashboard still updates.
- Derived series (YoY %, monthly changes, GDP growth) and summary tiles are
  computed here so the page only renders.
Usage:  python3 fetch_data.py            (from anywhere)
"""
import csv, io, json, os, subprocess, sys, time, datetime as dt
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "web", "data", "data.json")
START = "2000-01-01"
URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={start}"
CT = ZoneInfo("America/Chicago")

# id -> (title, units, frequency label, group)
SERIES = {
    # Rates / curve
    "DFF": ("Fed funds effective rate", "%", "Daily", "Rates"),
    "SOFR": ("SOFR", "%", "Daily", "Rates"),
    "DGS3MO": ("3M Treasury", "%", "Daily", "Rates"),
    "DGS6MO": ("6M Treasury", "%", "Daily", "Rates"),
    "DGS1": ("1Y Treasury", "%", "Daily", "Rates"),
    "DGS2": ("2Y Treasury", "%", "Daily", "Rates"),
    "DGS3": ("3Y Treasury", "%", "Daily", "Rates"),
    "DGS5": ("5Y Treasury", "%", "Daily", "Rates"),
    "DGS7": ("7Y Treasury", "%", "Daily", "Rates"),
    "DGS10": ("10Y Treasury", "%", "Daily", "Rates"),
    "DGS20": ("20Y Treasury", "%", "Daily", "Rates"),
    "DGS30": ("30Y Treasury", "%", "Daily", "Rates"),
    "T10Y2Y": ("10Y minus 2Y (2s10s)", "%", "Daily", "Rates"),
    "T10Y3M": ("10Y minus 3M", "%", "Daily", "Rates"),
    # Credit
    "BAMLH0A0HYM2": ("ICE BofA US High Yield OAS", "%", "Daily", "Credit"),
    "BAMLC0A0CM": ("ICE BofA US Corporate (IG) OAS", "%", "Daily", "Credit"),
    "BAMLC0A4CBBB": ("ICE BofA BBB US Corporate OAS", "%", "Daily", "Credit"),
    "BAA10Y": ("Moody's Baa yield minus 10Y Treasury", "%", "Daily", "Credit"),
    "AAA10Y": ("Moody's Aaa yield minus 10Y Treasury", "%", "Daily", "Credit"),
    # Bank balance sheet (H.8, weekly, SA, $bn)
    "TOTLL": ("Loans & leases, all commercial banks", "$bn", "Weekly", "Banks"),
    "DPSACBW027SBOG": ("Deposits, all commercial banks", "$bn", "Weekly", "Banks"),
    "TOTCI": ("C&I loans, all commercial banks", "$bn", "Weekly", "Banks"),
    "CREACBW027SBOG": ("CRE loans, all commercial banks", "$bn", "Weekly", "Banks"),
    "CCLACBW027SBOG": ("Credit card & revolving loans, all commercial banks", "$bn", "Weekly", "Banks"),
    "DPSSCBW027SBOG": ("Deposits, small domestically chartered banks", "$bn", "Weekly", "Banks"),
    "LLBSCBW027SBOG": ("Loans & leases, small domestically chartered banks", "$bn", "Weekly", "Banks"),
    "DPSLCBW027SBOG": ("Deposits, large domestically chartered banks", "$bn", "Weekly", "Banks"),
    "LLBLCBW027SBOG": ("Loans & leases, large domestically chartered banks", "$bn", "Weekly", "Banks"),
    # Deposit mix: H.8 weekly (commercial banks, SA, $bn)
    "LTDACBW027SBOG": ("H.8 Large time deposits, all commercial banks", "$bn", "Weekly", "DepMix"),
    "ODSACBW027SBOG": ("H.8 Other deposits (ex large time), all commercial banks", "$bn", "Weekly", "DepMix"),
    "LTDLCBW027SBOG": ("H.8 Large time deposits, large domestic banks", "$bn", "Weekly", "DepMix"),
    "ODSLCBW027SBOG": ("H.8 Other deposits, large domestic banks", "$bn", "Weekly", "DepMix"),
    "LTDSCBW027SBOG": ("H.8 Large time deposits, small domestic banks", "$bn", "Weekly", "DepMix"),
    "ODSSCBW027SBOG": ("H.8 Other deposits, small domestic banks", "$bn", "Weekly", "DepMix"),
    # Deposit mix: H.6 monthly (all depository institutions, SA, $bn)
    "DEMDEPSL": ("H.6 Demand deposits", "$bn", "Monthly", "DepMix"),
    "MDLM": ("H.6 Other liquid deposits (savings, MMDA, OCDs; from May 2020)", "$bn", "Monthly", "DepMix"),
    "SAVINGSL": ("H.6 Savings deposits incl. MMDA (discontinued Apr 2020)", "$bn", "Monthly", "DepMix"),
    "OCDSL": ("H.6 Other checkable deposits (discontinued Apr 2020)", "$bn", "Monthly", "DepMix"),
    "STDSL": ("H.6 Small-denomination time deposits", "$bn", "Monthly", "DepMix"),
    "RMFSL": ("H.6 Retail money market funds", "$bn", "Monthly", "DepMix"),
    # Credit quality (quarterly, SA %)
    "DRALACBS": ("Delinquency rate, all loans", "%", "Quarterly", "Quality"),
    "DRCCLACBS": ("Delinquency rate, credit cards", "%", "Quarterly", "Quality"),
    "DRCRELEXFACBS": ("Delinquency rate, CRE (ex farmland)", "%", "Quarterly", "Quality"),
    "CORALACBS": ("Net charge-off rate, all loans", "%", "Quarterly", "Quality"),
    "DRTSCILM": ("SLOOS: net % tightening C&I standards (large/mid firms)", "%", "Quarterly", "Quality"),
    # Housing
    "MORTGAGE30US": ("30Y fixed mortgage rate (Freddie Mac PMMS)", "%", "Weekly", "Housing"),
    "HOUST": ("Housing starts (SAAR, thousands)", "k units", "Monthly", "Housing"),
    # Macro
    "UNRATE": ("Unemployment rate", "%", "Monthly", "Macro"),
    "PAYEMS": ("Nonfarm payrolls (thousands)", "k", "Monthly", "Macro"),
    "CPIAUCSL": ("CPI-U, all items (index)", "index", "Monthly", "Macro"),
    "PCEPILFE": ("Core PCE price index", "index", "Monthly", "Macro"),
    "GDPC1": ("Real GDP (chained 2017 $bn, SAAR)", "$bn", "Quarterly", "Macro"),
    "ICSA": ("Initial jobless claims (SA)", "claims", "Weekly", "Macro"),
    # Markets
    "VIXCLS": ("CBOE VIX", "index", "Daily", "Markets"),
}

# Non-FRED sources: id -> (title, units, freq, group, source label)
EXTRA = {
    "MOVE": ("ICE BofA MOVE index (Treasury implied vol)", "index", "Daily", "Markets",
             "Yahoo Finance chart API (^MOVE)"),
    "KRE_CLOSE": ("KRE closing price", "$", "Daily", "Positioning", "Yahoo Finance chart API (KRE)"),
    "KRE_SO": ("KRE shares outstanding", "shares", "Daily", "Positioning",
               "State Street (SSGA) KRE NAV history file"),
    "KRE_SI_SHARES": ("KRE short interest (shares)", "shares", "Semi-monthly", "Positioning",
                      "FINRA consolidated short interest API"),
    "KRE_ADV": ("KRE average daily volume (FINRA, per report)", "shares", "Semi-monthly", "Positioning",
                "FINRA consolidated short interest API"),
    "KRE_DTC": ("KRE days to cover (FINRA)", "days", "Semi-monthly", "Positioning",
                "FINRA consolidated short interest API"),
}
ACCUMULATE = {"KRE_SI_SHARES", "KRE_ADV", "KRE_DTC"}  # merge with stored history (FINRA window may roll)
FINRA_URL = "https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest"
SSGA_URL = "https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/navhist-us-en-kre.xlsx"
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")
YAHOO = "https://{host}.finance.yahoo.com/v8/finance/chart/{sym}?period1={p1}&period2={p2}&interval=1d&events=history"
ET = ZoneInfo("America/New_York")


def http_get(url):
    # FRED's CDN stalls requests with unfamiliar user agents; a curl-style UA works.
    # Fall back to the curl binary if urllib fails for any reason.
    try:
        req = Request(url, headers={"User-Agent": "curl/8.5.0", "Accept": "*/*"})
        with urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8")
    except Exception:
        out = subprocess.run(["curl", "-sfL", "--max-time", "40", url],
                             capture_output=True, text=True, check=True)
        return out.stdout


def fetch_one(sid, retries=3):
    last_err = None
    for attempt in range(retries):
        try:
            text = http_get(URL.format(sid=sid, start=START))
            rows = list(csv.reader(io.StringIO(text)))
            if not rows or len(rows[0]) < 2 or rows[0][1].strip() != sid:
                raise ValueError(f"unexpected header: {rows[0] if rows else 'empty'}")
            obs, missing = [], 0
            for row in rows[1:]:
                if len(row) < 2:
                    continue
                try:
                    obs.append([row[0], float(row[1])])
                except ValueError:
                    missing += 1  # '.' or blank = missing (e.g. market holidays)
            if not obs:
                raise ValueError("no numeric observations")
            return obs, None, {"missing": missing}
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {e}"
            time.sleep(2 * (attempt + 1))
    return None, last_err, {}


def fetch_yahoo(symbol, lo, hi, period1=946684800, min_rows=1000, retries=3):
    """Daily closes from Yahoo Finance's public chart API (no key; needs a browser UA)."""
    from urllib.parse import quote
    last_err = None
    for attempt in range(retries):
        host = "query1" if attempt % 2 == 0 else "query2"
        url = YAHOO.format(host=host, sym=quote(symbol), p1=period1, p2=int(time.time()))
        try:
            try:
                req = Request(url, headers={"User-Agent": BROWSER_UA, "Accept": "application/json"})
                with urlopen(req, timeout=30) as r:
                    text = r.read().decode("utf-8")
            except Exception:
                text = subprocess.run(["curl", "-sfL", "--max-time", "40", "-A", BROWSER_UA, url],
                                      capture_output=True, text=True, check=True).stdout
            res = json.loads(text)["chart"]["result"][0]
            meta = res["meta"]
            if meta.get("symbol") != symbol or meta.get("dataGranularity") != "1d":
                raise ValueError(f"unexpected meta: {meta.get('symbol')} {meta.get('dataGranularity')}")
            tz = ZoneInfo(meta.get("exchangeTimezoneName") or "America/New_York")
            closes = res["indicators"]["quote"][0]["close"]
            obs, missing, seen = [], 0, set()
            for t, v in zip(res["timestamp"], closes):
                ds = dt.datetime.fromtimestamp(t, tz).date().isoformat()
                if v is None:
                    missing += 1; continue
                if ds in seen:
                    continue
                seen.add(ds); obs.append([ds, round(float(v), 2)])
            obs.sort()
            # keep only completed sessions: drop today's bar until 17:00 ET
            now_et = dt.datetime.now(ET)
            dropped_partial = False
            if obs and obs[-1][0] == now_et.date().isoformat() and now_et.hour < 17:
                obs.pop(); dropped_partial = True
            if len(obs) < min_rows:
                raise ValueError(f"too few observations ({len(obs)})")
            bad = [o for o in obs if not (lo <= o[1] <= hi)]
            if bad:
                raise ValueError(f"implausible values, e.g. {bad[:3]}")
            mt = meta.get("regularMarketTime")
            info = {"missing": missing, "dropped_partial_today": dropped_partial,
                    "source_market_time_ct": dt.datetime.fromtimestamp(mt, CT).strftime("%Y-%m-%d %I:%M %p CT") if mt else None,
                    "source_market_price": meta.get("regularMarketPrice")}
            return obs, None, info
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {e}"
            time.sleep(3 * (attempt + 1))
    return None, last_err, {}


def fetch_move():
    return fetch_yahoo("^MOVE", 20, 400)


def fetch_finra_kre(retries=3):
    """KRE short interest reports from FINRA's public consolidated short interest dataset (no key)."""
    body = json.dumps({"limit": 5000, "compareFilters": [
        {"compareType": "EQUAL", "fieldName": "symbolCode", "fieldValue": "KRE"}]}).encode()
    last_err = None
    for attempt in range(retries):
        try:
            req = Request(FINRA_URL, data=body, method="POST",
                          headers={"Accept": "application/json", "Content-Type": "application/json",
                                   "User-Agent": "curl/8.5.0"})
            with urlopen(req, timeout=40) as r:
                recs = json.loads(r.read().decode("utf-8"))
            if not isinstance(recs, list):
                raise ValueError(f"unexpected response: {str(recs)[:200]}")
            recs = [x for x in recs if x.get("symbolCode") == "KRE"]
            if len(recs) < 12:
                raise ValueError(f"too few KRE reports ({len(recs)})")
            by_date = {}
            for x in recs:
                q = x.get("currentShortPositionQuantity")
                if q is None or not (1e6 <= q <= 5e8):
                    raise ValueError(f"implausible SI {q} on {x.get('settlementDate')}")
                by_date[x["settlementDate"]] = x  # one record per settlement date
            ds = sorted(by_date)
            si = [[k, float(by_date[k]["currentShortPositionQuantity"])] for k in ds]
            adv = [[k, float(by_date[k]["averageDailyVolumeQuantity"])] for k in ds
                   if by_date[k].get("averageDailyVolumeQuantity")]
            dtc = [[k, float(by_date[k]["daysToCoverQuantity"])] for k in ds
                   if by_date[k].get("daysToCoverQuantity") is not None]
            info = {"revised_reports": sum(1 for k in ds if by_date[k].get("revisionFlag")),
                    "market": sorted({by_date[k].get("marketClassCode") for k in ds})}
            return {"KRE_SI_SHARES": (si, None, info), "KRE_ADV": (adv, None, {}), "KRE_DTC": (dtc, None, {})}
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {e}"
            time.sleep(3 * (attempt + 1))
    return {k: (None, last_err, {}) for k in ("KRE_SI_SHARES", "KRE_ADV", "KRE_DTC")}


def fetch_ssga_kre_so(retries=3):
    """KRE daily shares outstanding from State Street's public NAV-history workbook."""
    last_err = None
    for attempt in range(retries):
        try:
            import openpyxl
            data = subprocess.run(["curl", "-sfL", "--max-time", "60", "-A", BROWSER_UA, SSGA_URL],
                                  capture_output=True, check=True).stdout
            if data[:2] != b"PK":
                raise ValueError("not an xlsx file")
            wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
            ws = wb.worksheets[0]
            out = {}
            for r in ws.iter_rows(values_only=True):
                if not r or r[0] is None or len(r) < 3:
                    continue
                try:
                    ds = dt.datetime.strptime(str(r[0]).strip(), "%d-%b-%Y").date().isoformat()
                except ValueError:
                    continue
                if isinstance(r[2], (int, float)):
                    out[ds] = float(r[2])
            obs = sorted([k, v] for k, v in out.items())
            if len(obs) < 1000:
                raise ValueError(f"too few rows ({len(obs)})")
            bad = [o for o in obs[-750:] if not (1e6 <= o[1] <= 1e9)]
            if bad:
                raise ValueError(f"implausible shares outstanding, e.g. {bad[:2]}")
            return obs, None, {}
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {e}"
            time.sleep(3 * (attempt + 1))
    return None, last_err, {}


def d(s):
    return dt.date.fromisoformat(s)


def value_on_or_before(obs, target):
    """Latest observation with date <= target (obs sorted ascending)."""
    lo, hi, ans = 0, len(obs) - 1, None
    while lo <= hi:
        mid = (lo + hi) // 2
        if d(obs[mid][0]) <= target:
            ans = obs[mid]; lo = mid + 1
        else:
            hi = mid - 1
    return ans


def minus_years(date, n=1):
    try:
        return date.replace(year=date.year - n)
    except ValueError:  # Feb 29
        return date.replace(year=date.year - n, day=28)


def yoy(obs, tol_days=3):
    out = []
    for date_s, v in obs:
        prior = value_on_or_before(obs, minus_years(d(date_s)) + dt.timedelta(days=tol_days))
        if prior and prior[1] and (d(date_s) - d(prior[0])).days >= 360:
            out.append([date_s, round((v / prior[1] - 1) * 100, 3)])
    return out


def diff(obs, scale=1.0):
    return [[obs[i][0], round((obs[i][1] - obs[i - 1][1]) * scale, 3)] for i in range(1, len(obs))]


def qoq_saar(obs):
    return [[obs[i][0], round(((obs[i][1] / obs[i - 1][1]) ** 4 - 1) * 100, 3)] for i in range(1, len(obs))]


def spread(a, b):
    bmap = {}
    for dd, v in b:
        bmap[dd] = v
    out = []
    for dd, v in a:  # align b on-or-before a's date (weekly vs daily)
        p = value_on_or_before(b, d(dd))
        if p and (d(dd) - d(p[0])).days <= 5:
            out.append([dd, round(v - p[1], 3)])
    return out


def merge_obs(old, new):
    m = {k: v for k, v in (old or [])}
    m.update({k: v for k, v in (new or [])})
    return sorted([k, v] for k, v in m.items())


def combine(fn, *series_list):
    """Apply fn to values on dates present in every series (exact date match)."""
    maps = [dict(x) for x in series_list]
    if not maps or any(not m for m in maps):
        return []
    dates = sorted(set.intersection(*(set(m) for m in maps)))
    out = []
    for k in dates:
        v = fn(*(m[k] for m in maps))
        if v is not None:
            out.append([k, round(v, 4)])
    return out


def at_or_before(obs, date_s, max_days):
    p = value_on_or_before(obs, d(date_s)) if obs else None
    if p and (d(date_s) - d(p[0])).days <= max_days:
        return p
    return None


def contribution(comp, total, tol_days=3):
    """Contribution of a component to total YoY growth, in pp: (C_t - C_t-1y) / T_t-1y * 100."""
    tmap = dict(total)
    out = []
    for date_s, v in comp:
        prior = value_on_or_before(comp, minus_years(d(date_s)) + dt.timedelta(days=tol_days))
        if not prior or (d(date_s) - d(prior[0])).days < 360:
            continue
        tp = tmap.get(prior[0])
        if tp:
            out.append([date_s, round((v - prior[1]) / tp * 100, 3)])
    return out


# Change conventions (used by tiles and the summary table):
#   bp  = (latest - prior) * 100   for % series (rates, yields, spreads, unemployment, delinquency, YoY growth)
#   pct = relative % change         for level series ($bn, payrolls, claims, starts, price indices, GDP)
#   pts = latest - prior            for indices (VIX, MOVE) and SLOOS net % tightening
#   k   = latest - prior (thousands) for monthly payroll change
# Prior = the observation ON OR BEFORE the lookback date. Horizons shorter than the series' own
# frequency (1W for monthly; 1W and 1M for quarterly) are shown as a dash.
# polarity: +1 rising is good, -1 rising is bad, 0 neutral (colouring only)
TILES = [
    ("DFF", "Fed funds (eff.)", "bp", 0, "pct2"),
    ("SOFR", "SOFR", "bp", 0, "pct2"),
    ("DGS2", "2Y Treasury", "bp", 0, "pct2"),
    ("DGS10", "10Y Treasury", "bp", 0, "pct2"),
    ("T10Y2Y", "2s10s curve", "bp", 0, "bp"),
    ("T10Y3M", "3m10y curve", "bp", 0, "bp"),
    ("BAMLH0A0HYM2", "HY OAS", "bp", -1, "bp"),
    ("BAMLC0A0CM", "IG OAS", "bp", -1, "bp"),
    ("BAMLC0A4CBBB", "BBB OAS", "bp", -1, "bp"),
    ("VIXCLS", "VIX", "pts", -1, "num2"),
    ("MOVE", "MOVE (Tsy vol)", "pts", -1, "num2"),
    ("KRE_SI_NOTIONAL", "KRE short interest ($)", "pct", 0, "bn2"),
    ("MORTGAGE30US", "30Y mortgage", "bp", 0, "pct2"),
    ("DPSACBW027SBOG", "Bank deposits", "pct", 1, "tn"),
    ("TOTLL", "Bank loans & leases", "pct", 1, "tn"),
    ("DPSSCBW027SBOG", "Small-bank deposits", "pct", 1, "tn"),
    ("H6_DDA_SHARE", "DDA share (H.6)", "bp", 1, "pct2"),
    ("H6_STD_SHARE", "Small time dep. share (H.6)", "bp", -1, "pct2"),
    ("LTD_SHARE_ALL", "Large time dep. share (H.8)", "bp", -1, "pct2"),
    ("UNRATE", "Unemployment", "bp", -1, "pct1"),
    ("ICSA", "Initial claims", "pct", -1, "k"),
    ("CPI_YOY", "CPI YoY", "bp", 0, "pct2"),
    ("COREPCE_YOY", "Core PCE YoY", "bp", 0, "pct2"),
]

# Summary table: (section, series key, display name, change unit, polarity)
SUMMARY = [
    ("Rates & Curve", "DFF", "Fed funds effective", "bp", 0),
    ("Rates & Curve", "SOFR", "SOFR", "bp", 0),
    ("Rates & Curve", "DGS3MO", "3M Treasury", "bp", 0),
    ("Rates & Curve", "DGS6MO", "6M Treasury", "bp", 0),
    ("Rates & Curve", "DGS1", "1Y Treasury", "bp", 0),
    ("Rates & Curve", "DGS2", "2Y Treasury", "bp", 0),
    ("Rates & Curve", "DGS3", "3Y Treasury", "bp", 0),
    ("Rates & Curve", "DGS5", "5Y Treasury", "bp", 0),
    ("Rates & Curve", "DGS7", "7Y Treasury", "bp", 0),
    ("Rates & Curve", "DGS10", "10Y Treasury", "bp", 0),
    ("Rates & Curve", "DGS20", "20Y Treasury", "bp", 0),
    ("Rates & Curve", "DGS30", "30Y Treasury", "bp", 0),
    ("Rates & Curve", "T10Y2Y", "2s10s (10Y − 2Y)", "bp", 0),
    ("Rates & Curve", "T10Y3M", "3m10y (10Y − 3M)", "bp", 0),
    ("Credit Spreads", "BAMLH0A0HYM2", "ICE BofA HY OAS", "bp", -1),
    ("Credit Spreads", "BAMLC0A0CM", "ICE BofA IG OAS", "bp", -1),
    ("Credit Spreads", "BAMLC0A4CBBB", "ICE BofA BBB OAS", "bp", -1),
    ("Credit Spreads", "BAA10Y", "Moody's Baa − 10Y", "bp", -1),
    ("Credit Spreads", "AAA10Y", "Moody's Aaa − 10Y", "bp", -1),
    ("Bank Deposits & Loans", "DPSACBW027SBOG", "Deposits, all commercial banks", "pct", 1),
    ("Bank Deposits & Loans", "DPSLCBW027SBOG", "Deposits, large domestic banks", "pct", 1),
    ("Bank Deposits & Loans", "DPSSCBW027SBOG", "Deposits, small domestic banks", "pct", 1),
    ("Bank Deposits & Loans", "TOTLL", "Loans & leases, all commercial banks", "pct", 1),
    ("Bank Deposits & Loans", "LLBLCBW027SBOG", "Loans & leases, large domestic banks", "pct", 1),
    ("Bank Deposits & Loans", "LLBSCBW027SBOG", "Loans & leases, small domestic banks", "pct", 1),
    ("Bank Deposits & Loans", "TOTCI", "C&I loans", "pct", 1),
    ("Bank Deposits & Loans", "CREACBW027SBOG", "CRE loans", "pct", 1),
    ("Bank Deposits & Loans", "CCLACBW027SBOG", "Credit card & revolving loans", "pct", 1),
    ("Bank Deposits & Loans", "DPSACBW027SBOG_YOY", "Deposit growth YoY, all banks", "bp", 1),
    ("Bank Deposits & Loans", "DPSLCBW027SBOG_YOY", "Deposit growth YoY, large banks", "bp", 1),
    ("Bank Deposits & Loans", "DPSSCBW027SBOG_YOY", "Deposit growth YoY, small banks", "bp", 1),
    ("Bank Deposits & Loans", "TOTLL_YOY", "Loan growth YoY, all banks", "bp", 1),
    ("Bank Deposits & Loans", "LLBLCBW027SBOG_YOY", "Loan growth YoY, large banks", "bp", 1),
    ("Bank Deposits & Loans", "LLBSCBW027SBOG_YOY", "Loan growth YoY, small banks", "bp", 1),
    ("Bank Deposits & Loans", "TOTCI_YOY", "C&I loan growth YoY", "bp", 1),
    ("Bank Deposits & Loans", "CREACBW027SBOG_YOY", "CRE loan growth YoY", "bp", 1),
    ("Bank Deposits & Loans", "CCLACBW027SBOG_YOY", "Card loan growth YoY", "bp", 1),
    ("Deposit Mix", "LTDACBW027SBOG", "H.8 Large time deposits, all banks", "pct", 0),
    ("Deposit Mix", "ODSACBW027SBOG", "H.8 Other deposits, all banks", "pct", 1),
    ("Deposit Mix", "LTDLCBW027SBOG", "H.8 Large time deposits, large banks", "pct", 0),
    ("Deposit Mix", "ODSLCBW027SBOG", "H.8 Other deposits, large banks", "pct", 1),
    ("Deposit Mix", "LTDSCBW027SBOG", "H.8 Large time deposits, small banks", "pct", 0),
    ("Deposit Mix", "ODSSCBW027SBOG", "H.8 Other deposits, small banks", "pct", 1),
    ("Deposit Mix", "LTD_SHARE_ALL", "H.8 Large time share of deposits, all banks", "bp", -1),
    ("Deposit Mix", "LTD_SHARE_LARGE", "H.8 Large time share, large banks", "bp", -1),
    ("Deposit Mix", "LTD_SHARE_SMALL", "H.8 Large time share, small banks", "bp", -1),
    ("Deposit Mix", "LTDACBW027SBOG_YOY", "H.8 Large time deposit growth YoY", "bp", 0),
    ("Deposit Mix", "ODSACBW027SBOG_YOY", "H.8 Other deposit growth YoY", "bp", 1),
    ("Deposit Mix", "DEMDEPSL", "H.6 Demand deposits", "pct", 1),
    ("Deposit Mix", "OLD_SPLICED", "H.6 Other liquid deposits (savings/MMDA/OCD)", "pct", 1),
    ("Deposit Mix", "STDSL", "H.6 Small-denomination time deposits", "pct", 0),
    ("Deposit Mix", "H6_TOTAL", "H.6 Total (DDA + other liquid + small time)", "pct", 1),
    ("Deposit Mix", "RMFSL", "H.6 Retail money market funds", "pct", -1),
    ("Deposit Mix", "H6_DDA_SHARE", "H.6 DDA share of deposits", "bp", 1),
    ("Deposit Mix", "H6_OLD_SHARE", "H.6 Other liquid share of deposits", "bp", 0),
    ("Deposit Mix", "H6_STD_SHARE", "H.6 Small time share of deposits", "bp", -1),
    ("Deposit Mix", "RMF_PCT_DEP", "H.6 Retail MMF as % of deposits", "bp", -1),
    ("Deposit Mix", "H6_TOTAL_YOY", "H.6 Total deposit growth YoY", "bp", 1),
    ("Credit Quality", "DRALACBS", "Delinquency rate, all loans", "bp", -1),
    ("Credit Quality", "DRCCLACBS", "Delinquency rate, credit cards", "bp", -1),
    ("Credit Quality", "DRCRELEXFACBS", "Delinquency rate, CRE (ex farmland)", "bp", -1),
    ("Credit Quality", "CORALACBS", "Net charge-off rate, all loans", "bp", -1),
    ("Credit Quality", "DRTSCILM", "SLOOS net % tightening C&I", "pts", -1),
    ("Housing", "MORTGAGE30US", "30Y mortgage rate", "bp", 0),
    ("Housing", "MORT_SPREAD", "30Y mortgage − 10Y Treasury", "bp", 0),
    ("Housing", "HOUST", "Housing starts (SAAR)", "pct", 1),
    ("Labor & Inflation", "UNRATE", "Unemployment rate", "bp", -1),
    ("Labor & Inflation", "PAYEMS", "Nonfarm payrolls (level)", "pct", 1),
    ("Labor & Inflation", "PAYEMS_CHG", "Nonfarm payrolls, monthly change", "k", 1),
    ("Labor & Inflation", "ICSA", "Initial jobless claims", "pct", -1),
    ("Labor & Inflation", "CPIAUCSL", "CPI-U index", "pct", 0),
    ("Labor & Inflation", "CPI_YOY", "CPI-U YoY", "bp", 0),
    ("Labor & Inflation", "PCEPILFE", "Core PCE price index", "pct", 0),
    ("Labor & Inflation", "COREPCE_YOY", "Core PCE YoY", "bp", 0),
    ("Labor & Inflation", "GDPC1", "Real GDP (level)", "pct", 1),
    ("Labor & Inflation", "GDP_QOQ", "Real GDP growth, QoQ SAAR", "bp", 1),
    ("Labor & Inflation", "GDP_YOY", "Real GDP growth, YoY", "bp", 1),
    ("Market Stress", "VIXCLS", "VIX", "pts", -1),
    ("Market Stress", "MOVE", "MOVE (Treasury implied vol)", "pts", -1),
    ("Positioning", "KRE_SI_NOTIONAL", "KRE short interest, notional ($bn)", "pct", 0),
    ("Positioning", "KRE_SI_SHARES", "KRE short interest, shares", "pct", 0),
    ("Positioning", "KRE_SI_PCT_SO", "KRE SI as % of shares outstanding", "bp", 0),
    ("Positioning", "KRE_DTC", "KRE days to cover (FINRA)", "days", 0),
    ("Positioning", "KRE_CLOSE", "KRE closing price", "pct", 1),
]

PERIOD_DAYS = {"Daily": 1, "Weekly": 7, "Semi-monthly": 14, "Monthly": 28, "Quarterly": 90}
HORIZONS = [("1w", 7), ("1m", 30), ("3m", 91), ("1y", 365)]


def minus_months(date, n=1):
    y, m = divmod(date.year * 12 + date.month - 1 - n, 12)
    m += 1
    import calendar
    return date.replace(year=y, month=m, day=min(date.day, calendar.monthrange(y, m)[1]))


def minus_month(date):
    return minus_months(date, 1)


def lookback(date, h):
    return {"1w": date - dt.timedelta(days=7), "1m": minus_months(date, 1),
            "3m": minus_months(date, 3), "1y": minus_years(date)}[h]


def change(obs, unit, h, freq):
    """Change vs the observation on or before the lookback date (None = not meaningful/unavailable)."""
    hdays = dict(HORIZONS)[h]
    latest = obs[-1]
    basis = None
    if freq == "Semi-monthly" and h == "1w":
        prior, basis = (obs[-2] if len(obs) > 1 else None), "prior report"
    elif hdays < PERIOD_DAYS.get(freq, 1):
        return None
    else:
        prior = value_on_or_before(obs, lookback(d(latest[0]), h))
    if not prior or prior[0] == latest[0]:
        return None
    a, b = latest[1], prior[1]
    if unit == "bp":
        val = (a - b) * 100
    elif unit == "pct":
        val = (a / b - 1) * 100 if b else None
    else:  # pts, k, days
        val = a - b
    out = {"value": None if val is None else round(val, 3), "vs_date": prior[0], "vs_value": b}
    if basis:
        out["basis"] = basis
    return out


def build_tiles(series):
    tiles = []
    for key, label, unit, pol, fmt in TILES:
        s = series.get(key)
        if not s or not s.get("data"):
            tiles.append({"key": key, "label": label, "missing": True}); continue
        obs = s["data"]
        tiles.append({
            "key": key, "label": label, "unit": unit, "polarity": pol, "fmt": fmt,
            "latest": obs[-1][1], "asof": obs[-1][0], "freq": s.get("freq"),
            "stale": s.get("stale", False), "source": s.get("source", "FRED"),
            "hs": ["1w", "1m", "3m", "1y"] if s.get("freq") == "Semi-monthly" else ["1w", "1m", "1y"],
            "chg": {h: change(obs, unit, h, s.get("freq")) for h in ("1w", "1m", "3m", "1y")},
            "extra": TILE_EXTRA[key](series) if key in TILE_EXTRA else None,
        })
    return tiles


def _kre_extra(series):
    rep = series.get("KRE_SI_SHARES", {}).get("data") or []
    if not rep:
        return None
    k = rep[-1][0]
    parts = [f"{rep[-1][1] / 1e6:,.2f}M sh"]
    pr = dict(series.get("KRE_SI_PRICE", {}).get("data") or [])
    if k in pr:
        parts.append(f"@ ${pr[k]:.2f}")
    dtc = dict(series.get("KRE_DTC", {}).get("data") or [])
    if k in dtc:
        parts.append(f"{dtc[k]:.2f} days to cover")
    pso = dict(series.get("KRE_SI_PCT_SO", {}).get("data") or [])
    if k in pso:
        parts.append(f"{pso[k]:.1f}% of shs out")
    return " · ".join(parts)


TILE_EXTRA = {"KRE_SI_NOTIONAL": _kre_extra}


def fmt_level(v, units):
    if v is None:
        return ""
    if units == "%":
        return f"{v:.2f}%"
    if units == "$bn":
        return f"${v:,.2f}bn" if abs(v) < 100 else f"${v:,.1f}bn"
    if units == "shares":
        return f"{v / 1e6:,.2f}M"
    if units == "days":
        return f"{v:.2f}"
    if units == "$":
        return f"${v:,.2f}"
    if units in ("k", "k units"):
        return f"{v:,.0f}k"
    if units == "claims":
        return f"{v:,.0f}"
    return f"{v:,.2f}"


def fmt_change(c, unit):
    if not c or c.get("value") is None:
        return "–"
    v = c["value"]
    sign = "+" if v > 0 else ("−" if v < 0 else "±")
    a = abs(v)
    if unit == "k":
        txt = f"{sign}{a:,.0f}k"
    elif unit == "bp":
        txt = f"{sign}{a:,.0f} bp"
    elif unit == "pct":
        txt = f"{sign}{a:.2f}%"
    else:
        txt = f"{sign}{a:.2f}"
    return txt + (" (prior rpt)" if c.get("basis") == "prior report" else "")


UNIT_LABEL = {"bp": "bp", "pct": "% chg", "pts": "pts", "k": "k (diff)", "days": "days"}


def build_summary(series):
    rows = []
    for section, key, name, unit, pol in SUMMARY:
        s = series.get(key)
        if not s or not s.get("data"):
            rows.append({"section": section, "id": key, "name": name, "missing": True,
                         "change_unit": UNIT_LABEL[unit]}); continue
        obs = s["data"]
        chg = {h: change(obs, unit, h, s.get("freq")) for h, _ in HORIZONS}
        rows.append({
            "section": section, "id": key, "name": name, "units": s.get("units"), "freq": s.get("freq"),
            "source": s.get("source", "FRED"), "stale": s.get("stale", False),
            "latest": obs[-1][1], "latest_fmt": fmt_level(obs[-1][1], s.get("units")), "asof": obs[-1][0],
            "unit": unit, "change_unit": UNIT_LABEL[unit], "polarity": pol,
            "chg": chg, "chg_fmt": {h: fmt_change(c, unit) for h, c in chg.items()},
        })
    return rows


def write_summary_csv(rows, path):
    cols = ["section", "series_id", "series", "source", "frequency", "units", "latest", "latest_display", "as_of",
            "change_unit", "chg_1w", "chg_1m", "chg_3m", "chg_1y",
            "vs_date_1w", "vs_date_1m", "vs_date_3m", "vs_date_1y", "basis_1w", "stale"]
    tmp = path + ".tmp"
    with open(tmp, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            if r.get("missing"):
                w.writerow([r["section"], r["id"], r["name"]] + [""] * 16 + ["missing"]); continue
            c = r["chg"]
            w.writerow([r["section"], r["id"], r["name"], r["source"], r["freq"], r["units"], r["latest"],
                        r["latest_fmt"], r["asof"], r["change_unit"]]
                       + [("" if not c[h] else c[h]["value"]) for h, _ in HORIZONS]
                       + [("" if not c[h] else c[h]["vs_date"]) for h, _ in HORIZONS]
                       + [("prior_report" if c["1w"] and c["1w"].get("basis") else ("1w" if c["1w"] else ""))]
                       + [r["stale"]])
    os.replace(tmp, path)


GAP_LIMIT = {"Daily": 7, "Weekly": 10, "Semi-monthly": 20, "Monthly": 35, "Quarterly": 95}


def gap_info(obs, freq):
    """Largest spacing between consecutive observations; flags gaps beyond normal holiday spacing."""
    worst, at = 0, None
    for i in range(1, len(obs)):
        g = (d(obs[i][0]) - d(obs[i - 1][0])).days
        if g > worst:
            worst, at = g, obs[i - 1][0]
    return {"max_gap_days": worst, "max_gap_after": at, "gap_flag": worst > GAP_LIMIT.get(freq, 7)}


CURVE = [("3M", "DGS3MO"), ("6M", "DGS6MO"), ("1Y", "DGS1"), ("2Y", "DGS2"), ("3Y", "DGS3"),
         ("5Y", "DGS5"), ("7Y", "DGS7"), ("10Y", "DGS10"), ("20Y", "DGS20"), ("30Y", "DGS30")]


def build_curve(series):
    have = [(t, series[k]["data"]) for t, k in CURVE if series.get(k, {}).get("data")]
    if not have:
        return None
    # anchor = most recent date for which the 10Y (or first available tenor) has data
    anchor_obs = dict(have).get("10Y") or have[0][1]
    anchor = d(anchor_obs[-1][0])
    out = {"tenors": [t for t, _ in have], "curves": []}
    for label, target in [("Latest", anchor),
                          ("1 month ago", anchor - dt.timedelta(days=30)),
                          ("1 year ago", minus_years(anchor))]:
        pts, dates = [], set()
        for t, obs in have:
            p = value_on_or_before(obs, target)
            pts.append(p[1] if p else None)
            if p: dates.add(p[0])
        out["curves"].append({"label": label, "date": max(dates) if dates else None, "values": pts})
    return out


def main():
    prev = {}
    if os.path.exists(OUT):
        try:
            with open(OUT) as f:
                prev = json.load(f).get("series", {})
        except Exception:
            prev = {}

    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {sid: ex.submit(fetch_one, sid) for sid in SERIES}
        futs["MOVE"] = ex.submit(fetch_move)
        futs["KRE_CLOSE"] = ex.submit(fetch_yahoo, "KRE", 5, 500, 1136073600)  # from 2006
        futs["KRE_SO"] = ex.submit(fetch_ssga_kre_so)
        f_finra = ex.submit(fetch_finra_kre)
        results = {k: f.result() for k, f in futs.items()}
        results.update(f_finra.result())

    catalog = {sid: (*v, "FRED") for sid, v in SERIES.items()}
    catalog.update(EXTRA)
    series, status = {}, []
    for sid, (title, units, freq, group, source) in catalog.items():
        obs, err, info = results[sid]
        meta = {"id": sid, "title": title, "units": units, "freq": freq, "group": group, "source": source}
        if obs and sid in ACCUMULATE and prev.get(sid, {}).get("data"):
            before = len(obs)
            obs = merge_obs(prev[sid]["data"], obs)
            info = {**info, "kept_from_previous_runs": len(obs) - before}
        if obs:
            series[sid] = {**meta, "data": obs, "stale": False}
            status.append({"id": sid, "source": source, "ok": True, "rows": len(obs), "first": obs[0][0],
                           "last": obs[-1][0], **info, **gap_info(obs, freq)})
        elif sid in prev and prev[sid].get("data"):
            series[sid] = {**prev[sid], **meta, "stale": True}
            pdat = prev[sid]["data"]
            status.append({"id": sid, "source": source, "ok": False, "stale_kept": True, "error": err,
                           "rows": len(pdat), "first": pdat[0][0], "last": pdat[-1][0], **gap_info(pdat, freq)})
        else:
            status.append({"id": sid, "source": source, "ok": False, "stale_kept": False, "error": err})

    def add(key, title, units, freq, group, data, src):
        if data:
            series[key] = {"id": key, "title": title, "units": units, "freq": freq, "group": group,
                           "data": data, "derived_from": src,
                           "stale": any(series.get(s, {}).get("stale") for s in src),
                           "source": derived_source(src)}

    def derived_source(src):
        srcs = sorted({series[x].get("source", "FRED") for x in src if x in series})
        if all(x.startswith("FRED") for x in srcs):
            return "FRED (derived)"
        return "Derived: " + " + ".join(x.split(" (")[0] for x in srcs)

    g = lambda k: series.get(k, {}).get("data") or []
    for k in ["TOTLL", "DPSACBW027SBOG", "TOTCI", "CREACBW027SBOG", "CCLACBW027SBOG",
              "DPSSCBW027SBOG", "LLBSCBW027SBOG", "DPSLCBW027SBOG", "LLBLCBW027SBOG"]:
        if g(k):
            add(k + "_YOY", series[k]["title"] + " — YoY %", "%", "Weekly", "Banks", yoy(g(k)), [k])
    add("CPI_YOY", "CPI-U YoY %", "%", "Monthly", "Macro", yoy(g("CPIAUCSL")), ["CPIAUCSL"])
    add("COREPCE_YOY", "Core PCE YoY %", "%", "Monthly", "Macro", yoy(g("PCEPILFE")), ["PCEPILFE"])
    add("PAYEMS_CHG", "Nonfarm payrolls, monthly change (k)", "k", "Monthly", "Macro", diff(g("PAYEMS")), ["PAYEMS"])
    add("GDP_QOQ", "Real GDP growth, QoQ SAAR %", "%", "Quarterly", "Macro", qoq_saar(g("GDPC1")), ["GDPC1"])
    add("GDP_YOY", "Real GDP growth, YoY %", "%", "Quarterly", "Macro", yoy(g("GDPC1")), ["GDPC1"])
    # ---- Deposit mix: H.8 (weekly, commercial banks)
    for k in ["LTDACBW027SBOG", "ODSACBW027SBOG"]:
        if g(k):
            add(k + "_YOY", series[k]["title"] + " — YoY %", "%", "Weekly", "DepMix", yoy(g(k)), [k])
    share = lambda a, b: (a / b * 100) if b else None
    add("LTD_SHARE_ALL", "H.8 Large time deposits as % of deposits, all commercial banks", "%", "Weekly", "DepMix",
        combine(share, g("LTDACBW027SBOG"), g("DPSACBW027SBOG")), ["LTDACBW027SBOG", "DPSACBW027SBOG"])
    add("LTD_SHARE_LARGE", "H.8 Large time deposits as % of deposits, large domestic banks", "%", "Weekly", "DepMix",
        combine(share, g("LTDLCBW027SBOG"), g("DPSLCBW027SBOG")), ["LTDLCBW027SBOG", "DPSLCBW027SBOG"])
    add("LTD_SHARE_SMALL", "H.8 Large time deposits as % of deposits, small domestic banks", "%", "Weekly", "DepMix",
        combine(share, g("LTDSCBW027SBOG"), g("DPSSCBW027SBOG")), ["LTDSCBW027SBOG", "DPSSCBW027SBOG"])
    add("H8_CONTRIB_LTD", "H.8 Contribution to deposit YoY: large time (pp)", "pp", "Weekly", "DepMix",
        contribution(g("LTDACBW027SBOG"), g("DPSACBW027SBOG")), ["LTDACBW027SBOG", "DPSACBW027SBOG"])
    add("H8_CONTRIB_OTHER", "H.8 Contribution to deposit YoY: other deposits (pp)", "pp", "Weekly", "DepMix",
        contribution(g("ODSACBW027SBOG"), g("DPSACBW027SBOG")), ["ODSACBW027SBOG", "DPSACBW027SBOG"])
    # ---- Deposit mix: H.6 (monthly, all depository institutions)
    old_pre = combine(lambda a, b: a + b, g("SAVINGSL"), g("OCDSL"))
    mdlm = g("MDLM")
    if mdlm:
        first_m = mdlm[0][0]
        add("OLD_SPLICED", "H.6 Other liquid deposits (savings+OCD before May 2020, MDLM after)", "$bn", "Monthly",
            "DepMix", [o for o in old_pre if o[0] < first_m] + mdlm, ["MDLM", "SAVINGSL", "OCDSL"])
    add("H6_TOTAL", "H.6 Deposits: demand + other liquid + small time", "$bn", "Monthly", "DepMix",
        combine(lambda a, b, c: a + b + c, g("DEMDEPSL"), g("OLD_SPLICED"), g("STDSL")),
        ["DEMDEPSL", "MDLM", "SAVINGSL", "OCDSL", "STDSL"])
    for k, nm in [("DEMDEPSL", "DDA"), ("OLD_SPLICED", "OLD"), ("STDSL", "STD")]:
        add(f"H6_{nm}_SHARE", f"H.6 {series.get(k, {}).get('title', k)} — share of deposits", "%", "Monthly", "DepMix",
            combine(share, g(k), g("H6_TOTAL")), [k, "H6_TOTAL"])
        add(f"H6_CONTRIB_{nm}", f"H.6 Contribution to deposit YoY: {nm} (pp)", "pp", "Monthly", "DepMix",
            contribution(g(k), g("H6_TOTAL")), [k, "H6_TOTAL"])
    for k in ["DEMDEPSL", "OLD_SPLICED", "STDSL", "RMFSL", "H6_TOTAL"]:
        if g(k):
            add(k + "_YOY", series[k]["title"] + " — YoY %", "%", "Monthly", "DepMix", yoy(g(k)), [k])
    add("RMF_PCT_DEP", "H.6 Retail money market funds as % of deposits", "%", "Monthly", "DepMix",
        combine(share, g("RMFSL"), g("H6_TOTAL")), ["RMFSL", "H6_TOTAL"])
    # ---- KRE short interest: notional = SI shares x KRE close on settlement date
    si, close, so = g("KRE_SI_SHARES"), g("KRE_CLOSE"), g("KRE_SO")
    price_rows, notional, pct_so, reports = [], [], [], []
    dtc_m, adv_m = dict(g("KRE_DTC")), dict(g("KRE_ADV"))
    for i, (k, q) in enumerate(si):
        p = at_or_before(close, k, 4)
        o = at_or_before(so, k, 4)
        if p:
            price_rows.append([k, p[1]]); notional.append([k, round(q * p[1] / 1e9, 4)])
        if o:
            pct_so.append([k, round(q / o[1] * 100, 3)])
        reports.append({"date": k, "si_shares": q, "chg_pct": round((q / si[i - 1][1] - 1) * 100, 2) if i else None,
                        "price": p[1] if p else None, "price_date": p[0] if p else None,
                        "notional_bn": round(q * p[1] / 1e9, 4) if p else None,
                        "dtc": dtc_m.get(k), "adv": adv_m.get(k),
                        "shares_out": o[1] if o else None, "pct_so": round(q / o[1] * 100, 2) if o else None})
    add("KRE_SI_PRICE", "KRE close used for each settlement date", "$", "Semi-monthly", "Positioning",
        price_rows, ["KRE_CLOSE", "KRE_SI_SHARES"])
    add("KRE_SI_NOTIONAL", "KRE short interest, notional (SI shares x close on settlement date)", "$bn",
        "Semi-monthly", "Positioning", notional, ["KRE_SI_SHARES", "KRE_CLOSE"])
    add("KRE_SI_PCT_SO", "KRE short interest as % of shares outstanding", "%", "Semi-monthly", "Positioning",
        pct_so, ["KRE_SI_SHARES", "KRE_SO"])
    if g("MORTGAGE30US") and g("DGS10"):
        add("MORT_SPREAD", "30Y mortgage minus 10Y Treasury", "%", "Weekly", "Housing",
            spread(g("MORTGAGE30US"), g("DGS10")), ["MORTGAGE30US", "DGS10"])

    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "generated_utc": now.isoformat(timespec="seconds"),
        "generated_ct": now.astimezone(CT).strftime("%Y-%m-%d %I:%M %p %Z"),
        "source": "FRED (fredgraph.csv); MOVE & KRE prices: Yahoo Finance chart API; KRE short interest: FINRA; KRE shares outstanding: State Street",
        "start": START,
        "status": status,
        "tiles": build_tiles(series),
        "summary": build_summary(series),
        "kre_si_reports": reports,
        "curve": build_curve(series),
        "series": series,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f, separators=(",", ":"))
    os.replace(tmp, OUT)
    write_summary_csv(payload["summary"], os.path.join(os.path.dirname(OUT), "summary.csv"))

    ok = sum(1 for s in status if s["ok"])
    print(f"[{payload['generated_ct']}] {ok}/{len(status)} series fetched OK -> {OUT}")
    # Financials Time Allocation panel (separate file; its failure never breaks the macro data)
    if os.environ.get("SKIP_ALLOC") != "1":
        try:
            p = subprocess.run([sys.executable, os.path.join(ROOT, "fetch_alloc.py")],
                               capture_output=True, text=True, timeout=900)
            print((p.stdout + p.stderr).strip())
        except Exception as e:  # noqa: BLE001
            print(f"  alloc panel refresh failed: {e} (previous alloc.json kept)")
    for s in status:
        if not s["ok"]:
            print(f"  FAILED {s['id']}: {s.get('error')} (kept previous: {s.get('stale_kept')})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
