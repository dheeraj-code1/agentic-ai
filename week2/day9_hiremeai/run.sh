#!/usr/bin/env bash
# Start the backend, run the bot, then stop the backend.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PORT="${PORT:-8000}"

(cd "$ROOT/backend" && exec uv run uvicorn main:app --port "$PORT") &
BACKEND_PID=$!
trap 'kill $BACKEND_PID 2>/dev/null; wait $BACKEND_PID 2>/dev/null || true' EXIT

echo "Waiting for backend on port $PORT..."
for _ in $(seq 1 60); do
    if curl -s -o /dev/null "http://127.0.0.1:$PORT/docs"; then
        break
    fi
    if ! kill -0 $BACKEND_PID 2>/dev/null; then
        echo "Backend failed to start." >&2
        exit 1
    fi
    sleep 1
done

cd "$ROOT/bot"
CHAT_API_URL="http://127.0.0.1:$PORT/chat_naukari" \
SCORE_API_URL="http://127.0.0.1:$PORT/score" \
    uv run python main.py "$@"
