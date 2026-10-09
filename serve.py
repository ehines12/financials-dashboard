#!/usr/bin/env python3
"""Tiny static server for the macro dashboard + scheduled FRED refresh.

  python3 serve.py [--port 8050] [--refresh-hours 4]

- Serves ./web on 127.0.0.1/0.0.0.0:<port>
- Re-runs fetch_data.py every --refresh-hours (and at startup if data is older than that)
- POST /api/refresh triggers a fetch now; GET /api/status returns refresh state
"""
import argparse, json, os, subprocess, sys, threading, time
from functools import partial
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

ROOT = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(ROOT, "web")
DATA = os.path.join(WEB, "data", "data.json")
LOCK = threading.Lock()
STATE = {"running": False, "last_run_epoch": None, "last_exit": None, "last_output": ""}
MANUAL_COOLDOWN_S = 600          # public link: manual refresh at most once per 10 minutes
LAST_MANUAL = {"t": 0.0}
MANUAL_LOCK = threading.Lock()


def run_fetch():
    if not LOCK.acquire(blocking=False):
        return False
    try:
        STATE["running"] = True
        p = subprocess.run([sys.executable, os.path.join(ROOT, "fetch_data.py")],
                           capture_output=True, text=True, timeout=600)
        STATE.update(last_exit=p.returncode, last_output=(p.stdout + p.stderr)[-4000:])
        print(p.stdout.strip(), p.stderr.strip(), flush=True)
    except Exception as e:  # noqa: BLE001
        STATE.update(last_exit=-1, last_output=str(e))
    finally:
        STATE["running"] = False
        STATE["last_run_epoch"] = time.time()
        LOCK.release()
    return True


def scheduler(hours):
    while True:
        age = time.time() - os.path.getmtime(DATA) if os.path.exists(DATA) else 1e12
        if age >= hours * 3600 and not STATE["running"]:
            run_fetch()
        time.sleep(300)


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        if self.path.startswith("/data/") or self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/status"):
            return self._json({k: STATE[k] for k in ("running", "last_run_epoch", "last_exit")}
                          | {"manual_cooldown_s": MANUAL_COOLDOWN_S,
                             "manual_available_in_s": max(0, int(MANUAL_COOLDOWN_S - (time.time() - LAST_MANUAL["t"])))})
        return super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/refresh"):
            with MANUAL_LOCK:
                now = time.time()
                wait = MANUAL_COOLDOWN_S - (now - LAST_MANUAL["t"])
                if STATE["running"]:
                    return self._json({"started": False, "running": True, "reason": "refresh already running"})
                if wait > 0:
                    return self._json({"started": False, "running": False, "reason": "rate limited",
                                       "retry_after_s": int(wait) + 1}, code=429)
                LAST_MANUAL["t"] = now
                STATE["running"] = True  # mark before thread starts to block races
            threading.Thread(target=run_fetch, daemon=True).start()
            return self._json({"started": True, "running": True})
        self.send_error(404)

    def list_directory(self, path):  # no directory listings on the public link
        self.send_error(403, "Directory listing disabled")
        return None

    def log_message(self, fmt, *args):
        msg = fmt % args
        if "/api/" in msg or "code 4" in msg or "code 5" in msg:
            super().log_message("%s", msg)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8050)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--refresh-hours", type=float, default=4)
    a = ap.parse_args()
    threading.Thread(target=scheduler, args=(a.refresh_hours,), daemon=True).start()
    srv = ThreadingHTTPServer((a.host, a.port), partial(Handler, directory=WEB))
    print(f"Macro dashboard on http://localhost:{a.port}  (auto-refresh every {a.refresh_hours}h)", flush=True)
    srv.serve_forever()
