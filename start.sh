#!/usr/bin/env bash
# Start (or restart) the dashboard server in the background.
cd "$(dirname "$0")"
PORT="${PORT:-8050}"
pkill -f "serve.py --port $PORT" 2>/dev/null
mkdir -p logs
nohup setsid python3 serve.py --port "$PORT" --refresh-hours "${REFRESH_HOURS:-4}" >> logs/server.log 2>&1 < /dev/null &
echo $! > logs/server.pid
sleep 1
echo "Dashboard: http://localhost:$PORT  (pid $(cat logs/server.pid), log logs/server.log)"
