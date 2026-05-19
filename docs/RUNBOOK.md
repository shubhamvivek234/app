# SocialEntangler Operations Runbook

Canonical production stack:
- Compose file: `/opt/socialentagler/docker-compose.yml`
- Compatibility alias: `/opt/socialentagler/docker-compose.prod.yml`
- Backend deploy: `./scripts/deploy_backend.sh`
- Queue diagnostics: `./scripts/check_queue_health.sh`
- Runtime diagnostics: `./scripts/check_runtime_health.sh`

## Quick Reference

| Issue | First Step |
|-------|-----------|
| Backend 5xx / broken feature | Check Sentry first, then `docker compose logs --tail=200 api` |
| Posts not publishing | Check Sentry, then worker logs + queue depth |
| Redis unhealthy | `./scripts/check_queue_health.sh` and `docker compose ps` |
| Disk/log pressure | `./scripts/check_runtime_health.sh` and `docker system df` |
| Container restart loop | `docker compose ps` then `docker inspect <container>` |

## 1. Logging Model

- API, Celery workers, beat, nginx, and redis log to Docker `stdout/stderr`
- Docker log rotation is enabled with:
  - `driver: json-file`
  - `max-size: 25m`
  - `max-file: 7`
- Nginx logs to `/dev/stdout` and `/dev/stderr`
- API and workers emit structured JSON logs in production
- The frontend sends `X-Trace-ID` on API requests, and every API response echoes it back; use it to correlate nginx, API, and worker failures

## 2. Health Checks

```bash
curl http://127.0.0.1:8001/health
curl http://127.0.0.1:8001/ready
docker compose ps
./scripts/check_queue_health.sh
./scripts/check_runtime_health.sh
```

## 3. Sentry First

Use Sentry before tailing raw logs for:
- API exceptions
- Celery task crashes
- degraded warnings captured from OAuth, analytics, AI, and upload paths

Production envs should define:
- `SENTRY_DSN`
- `SENTRY_RELEASE`
- `SENTRY_TRACES_SAMPLE_RATE`
- `SENTRY_PROFILES_SAMPLE_RATE`
- `REACT_APP_SENTRY_DSN`
- `REACT_APP_SENTRY_RELEASE`

## 4. Trace ID Workflow

1. Copy the `X-Trace-ID` from the failing browser request or API response.
2. Search API logs:

```bash
docker compose logs --tail=500 api | rg '<trace-id>'
```

3. Search worker logs if the request enqueued work:

```bash
docker compose logs --tail=500 worker worker_video worker_media beat | rg '<trace-id>|<post_id>'
```

4. Search nginx logs if the request may not have reached the API:

```bash
docker compose logs --tail=300 nginx | rg '<trace-id>| 4[0-9][0-9] | 5[0-9][0-9] '
```

## 5. Common Incident Commands

### API / auth / OAuth

```bash
docker compose logs --tail=200 api
docker compose logs --tail=200 api | rg 'auth\\.|oauth\\.|trace_id'
```

### Publish pipeline

```bash
docker compose logs --tail=300 worker worker_video worker_media | rg 'publish\\.|pre_upload\\.|dlq'
./scripts/check_queue_health.sh
```

### Upload / media processing

```bash
docker compose logs --tail=300 api worker_media | rg 'upload\\.|media\\.'
```

### Analytics provider failures

```bash
docker compose logs --tail=300 api | rg 'analytics\\.|credits|permission|token'
```

## 6. Runtime / Disk / Log Pressure

```bash
./scripts/check_runtime_health.sh
docker system df
df -h
```

The runtime health script warns on:
- container restart spikes
- unhealthy services
- large Docker log files
- disk pressure on `/`

## 7. Safe Log Pruning

Do this only after confirming Docker rotation is active and no incident forensics are in progress.

```bash
docker compose down
docker system prune -f
docker compose up -d
```

Do not manually delete active container log files under Docker’s storage directory.

## 8. Failed Posts Incident

1. Check Sentry for `publish.*` errors.
2. Check worker health:

```bash
docker compose exec -T worker celery -A celery_workers.celery_app inspect ping
docker compose exec -T worker celery -A celery_workers.celery_app inspect active
docker compose exec -T worker celery -A celery_workers.celery_app inspect reserved
```

3. Check queue depth:

```bash
./scripts/check_queue_health.sh
```

4. Check retry / DLQ logs:

```bash
docker compose logs --tail=300 worker worker_video worker_media | rg 'publish\\.platform\\.|dlq'
```

5. Check platform-side issues:
- Meta permission errors
- X credits depleted
- LinkedIn access denied
- YouTube token refresh or analytics API disabled

## 9. Redis / Queue Recovery

```bash
docker compose exec -T redis redis-cli ping
docker compose exec -T redis redis-cli info memory
docker compose exec -T redis redis-cli --bigkeys
```

If Redis is degraded, restore it before retrying publish incidents.

## 10. Alerts To Configure

Use lightweight EC2/system + Sentry alerts for:
- API container restarting repeatedly
- worker / worker_video / worker_media restarting repeatedly
- Redis unhealthy
- EC2 disk usage threshold
- Sentry error spike

## 11. Verification After Deploy

```bash
docker compose --env-file backend/.env -f docker-compose.yml config >/dev/null
docker compose up -d --build
curl http://127.0.0.1:8001/health
./scripts/check_runtime_health.sh
```

## 12. Notes

- Keep high-volume provider success logs at `INFO` or lower only where necessary
- Repeated external failures should be searched by `failure_type`
- Never paste raw secrets, tokens, or headers into tickets or chat
