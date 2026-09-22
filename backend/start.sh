#!/bin/bash
# Container entrypoint: scheduler (background) + uvicorn (foreground).
# All sensitive configuration comes from environment variables — see .env.example.
set -euo pipefail

# /var/log is not writable by the non-root appuser; use /app/data instead
# (writable, and survives alongside the SQLite file if you mount it).
SCHEDULER_LOG="/app/data/scheduler.log"
mkdir -p /app/data

SCHEDULER_PID=""

cleanup() {
    # Kill the scheduler if this script exits without exec'ing uvicorn
    # (e.g. uvicorn is missing and `exec` fails). Once `exec` succeeds the
    # shell is replaced and Docker tears down the PID namespace on stop.
    if [ -n "${SCHEDULER_PID}" ] && kill -0 "${SCHEDULER_PID}" 2>/dev/null; then
        echo "Stopping scheduler (PID ${SCHEDULER_PID})..."
        kill "${SCHEDULER_PID}" 2>/dev/null || true
        wait "${SCHEDULER_PID}" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

echo "Starting scheduler..."
python -u /app/run_scheduler.py >> "${SCHEDULER_LOG}" 2>&1 &
SCHEDULER_PID=$!
echo "Scheduler started (PID ${SCHEDULER_PID}), logging to ${SCHEDULER_LOG}"

# Give the scheduler a moment to boot, then print the first log lines so a
# freshly started container is debuggable from `docker logs` alone.
sleep 2
if [ -f "${SCHEDULER_LOG}" ]; then
    echo "--- scheduler log (first 20 lines) ---"
    head -n 20 "${SCHEDULER_LOG}" || true
    echo "--- end scheduler log ---"
fi

# workers=1 is required: the in-process rate limiter and the scheduler
# heartbeat both assume a single worker. Do not raise --workers without first
# moving that state to a shared store (e.g. Redis).
echo "Starting web server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 5000 --workers 1
