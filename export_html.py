#!/usr/bin/env python3
"""Build a single self-contained, offline HTML snapshot of the dashboard.

  python3 export_html.py            # refresh FRED data first, then export
  python3 export_html.py --no-fetch # export from the current web/data/data.json

Output: Macro_Dashboard_<YYYY-MM-DD>.html (date of the data snapshot, Central time).
CSS, JS, Chart.js + date adapter and the data are all inlined; the page makes no network calls.
"""
import argparse, json, os, re, subprocess, sys, datetime as dt
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(ROOT, "web")


def read(rel):
    with open(os.path.join(WEB, rel), encoding="utf-8") as f:
        return f.read()


def script_safe(js):
    # prevent an inline script from being terminated early by '</script' or '<!--'
    return js.replace("</script", "<\\/script").replace("<!--", "<\\!--")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--out", help="output path (default: Macro_Dashboard_<date>.html in this folder)")
    a = ap.parse_args()
    if not a.no_fetch:
        subprocess.run([sys.executable, os.path.join(ROOT, "fetch_data.py")], check=True)

    data = json.loads(read("data/data.json"))
    gen_ct = dt.datetime.fromisoformat(data["generated_utc"]).astimezone(ZoneInfo("America/Chicago"))
    html = read("index.html")

    css = read("style.css")
    html = html.replace('<link rel="stylesheet" href="style.css">', f"<style>\n{css}\n</style>")
    for lib in ["vendor/chart.umd.min.js", "vendor/chartjs-adapter-date-fns.bundle.min.js"]:
        tag = f'<script src="{lib}"></script>'
        assert tag in html, tag
        html = html.replace(tag, f"<script>/* {lib} */\n{script_safe(read(lib))}\n</script>")
    data_js = "window.__MACRO_DATA__ = " + script_safe(json.dumps(data, separators=(",", ":"))) + ";"
    alloc_path = os.path.join(WEB, "data", "alloc.json")
    if os.path.exists(alloc_path):
        with open(alloc_path, encoding="utf-8") as f:
            data_js += "\nwindow.__ALLOC_DATA__ = " + script_safe(f.read().strip()) + ";"
    alloc_tag = '<script src="alloc.js"></script>'
    if alloc_tag in html:
        html = html.replace(alloc_tag, "")
    app_tag = '<script src="app.js"></script>'
    assert app_tag in html
    alloc_js = f"<script>\n{script_safe(read('alloc.js'))}\n</script>\n" if os.path.exists(os.path.join(WEB, "alloc.js")) else ""
    html = html.replace(app_tag, f"<script>\n{data_js}\n</script>\n{alloc_js}<script>\n{script_safe(read('app.js'))}\n</script>")
    html = html.replace("<title>Macro Dashboard · US Financials</title>",
                        f"<title>Macro Dashboard · US Financials · snapshot {gen_ct:%Y-%m-%d %H:%M} CT</title>")
    # sanity: no remaining external references
    leftovers = re.findall(r'(?:src|href)="(?!data:|#)[^"]+"', html)
    assert not leftovers, leftovers

    out = a.out or os.path.join(ROOT, f"Macro_Dashboard_{gen_ct:%Y-%m-%d}.html")
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(html)
    os.replace(tmp, out)
    print(f"Wrote {out} ({os.path.getsize(out)/1e6:.2f} MB), snapshot {gen_ct:%Y-%m-%d %I:%M %p} CT")


if __name__ == "__main__":
    main()
