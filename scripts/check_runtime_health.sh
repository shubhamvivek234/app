#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT_DIR/docker-compose.yml}"
DISK_WARN_PCT="${DISK_WARN_PCT:-80}"
MAX_RESTARTS="${MAX_RESTARTS:-5}"
MAX_LOG_BYTES="${MAX_LOG_BYTES:-536870912}"

cd "$ROOT_DIR"

failures=0
warn() {
  echo "[runtime-health][warn] $*" >&2
  failures=$((failures + 1))
}

info() {
  echo "[runtime-health] $*"
}

services=(api worker worker_video worker_media beat redis nginx)

info "compose file: $COMPOSE_FILE"
docker compose -f "$COMPOSE_FILE" ps
echo

disk_pct="$(df -P / | awk 'NR==2 {gsub(/%/, "", $5); print $5}')"
info "disk usage / = ${disk_pct}%"
if [[ -n "$disk_pct" ]] && (( disk_pct >= DISK_WARN_PCT )); then
  warn "disk usage is above threshold (${disk_pct}% >= ${DISK_WARN_PCT}%)"
fi

for service in "${services[@]}"; do
  container_id="$(docker compose -f "$COMPOSE_FILE" ps -q "$service" 2>/dev/null || true)"
  if [[ -z "$container_id" ]]; then
    warn "service '$service' is not running"
    continue
  fi

  status="$(docker inspect --format '{{.State.Status}}' "$container_id")"
  restarts="$(docker inspect --format '{{.RestartCount}}' "$container_id")"
  health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}}' "$container_id")"
  log_path="$(docker inspect --format '{{.LogPath}}' "$container_id")"
  log_size=0
  if [[ -n "$log_path" && -f "$log_path" ]]; then
    log_size="$(stat -f%z "$log_path" 2>/dev/null || stat -c%s "$log_path" 2>/dev/null || echo 0)"
  fi

  info "$(printf '%-12s status=%s health=%s restarts=%s log_size=%sB' "$service" "$status" "$health" "$restarts" "$log_size")"

  if [[ "$status" != "running" ]]; then
    warn "service '$service' is not running (status=$status)"
  fi
  if [[ "$health" != "healthy" && "$health" != "n/a" ]]; then
    warn "service '$service' health is $health"
  fi
  if [[ "$restarts" =~ ^[0-9]+$ ]] && (( restarts >= MAX_RESTARTS )); then
    warn "service '$service' restart count is high ($restarts >= $MAX_RESTARTS)"
  fi
  if [[ "$log_size" =~ ^[0-9]+$ ]] && (( log_size >= MAX_LOG_BYTES )); then
    warn "service '$service' docker log file is large (${log_size}B >= ${MAX_LOG_BYTES}B)"
  fi
done

echo
if (( failures > 0 )); then
  warn "runtime health check found $failures issue(s)"
  exit 1
fi

info "runtime health check passed"
