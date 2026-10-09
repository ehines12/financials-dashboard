# Financials dashboard (macro + financials time allocation)

Self-contained snapshot published to GitHub Pages by `.github/workflows/refresh-pages.yml`
(weekdays during US market hours, after the close, and Friday after the Fed H.8 release; also on demand via *Run workflow*).

* `fetch_data.py`: FRED macro series, MOVE (Yahoo), KRE short interest (FINRA) and shares outstanding (State Street) to `web/data/data.json`;
  then runs `fetch_alloc.py` (Financials Time Allocation panel) to `web/data/alloc.json`.
* `export_html.py --no-fetch --out _site/index.html`: inlines CSS/JS/Chart.js/data into one offline HTML file.
* `ci_summary.py`: per-source fetch status in the Actions log/job summary.
* `allocation_table.py` / `summary_table.py`: markdown tables for the weekly report.
* `cache/` and `web/data/`: seed copies used for history accumulation and STALE fallback when a source fails.
  The workflow keeps the latest copies in the Actions cache and commits the FINRA short-interest cache back to `main`.

Sources: FRED (St. Louis Fed), Yahoo Finance chart API (unofficial), FINRA consolidated short interest, State Street SPDR NAV history.
Informational only; not investment advice.
