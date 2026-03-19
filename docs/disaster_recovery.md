# SocialEntangler Disaster Recovery Runbook

## Incident Severity Levels

| Level | Description | Response Time | Escalation |
|-------|-------------|---------------|------------|
| P0 | Complete outage — all posts failing | 15 min | Page on-call immediately |
| P1 | Partial outage — one platform failing | 1 hour | Slack #incidents |
| P2 | Degraded — high latency, queue backup | 4 hours | Ticket |
| P3 | Minor — single post failed | Next business day | Ticket |

---

## Runbook 1: DLQ Non-Empty (P1)

**Alert:** `DLQNotEmpty` fires when `socialentangler_dlq_depth > 0`

**Diagnosis:**
```bash
# Check DLQ contents
celery -A celery_workers.celery_app inspect reserved
# View dead-lettered task IDs
redis-cli -h redis-queue LRANGE dead_letter 0 -1
```

**Resolution:**
1. Identify the failing task from Sentry (filter by `celery.task.failure`)
2. Check the platform's status page (platform API outage?)
3. If platform outage: wait and retry. If code bug: hotfix + redeploy
4. Replay DLQ messages:
   ```bash
   celery -A celery_workers.celery_app call celery_workers.tasks.publish.publish_post \
     --kwargs '{"post_id": "...", "version": 1}'
   ```
5. Verify DLQ drains (alert should clear within 5 min)

---

## Runbook 2: Queue Depth > 500 (P1)

**Alert:** `QueueDepthHigh` or `QueueDepthCritical`

**Diagnosis:**
```bash
# Check current worker count
celery -A celery_workers.celery_app inspect active
# Check queue lengths
redis-cli -h redis-queue LLEN default
redis-cli -h redis-queue LLEN high_priority
```

**Resolution:**
1. Scale worker replicas:
   ```bash
   docker service scale socialentangler_worker=8   # double from default 4
   ```
2. If queue doesn't drain after 10 min, check for poison pills:
   ```bash
   redis-cli -h redis-cache KEYS "delivery_count:*" | xargs redis-cli MGET
   ```
3. For persistent slow tasks, increase `worker_max_tasks_per_child` or check for GIL contention

---

## Runbook 3: Publish Success Rate < 90% (P0)

**Alert:** `PublishSuccessRateLow`

**Diagnosis:**
```bash
# Which platform is failing?
# Query Prometheus:
# sum by (platform, outcome) (rate(socialentangler_publish_attempts_total[5m]))

# Check circuit breakers
redis-cli -h redis-cache KEYS "circuit:*:state"
```

**Resolution:**
1. Check platform circuit breaker states in Grafana "Circuit Breaker States" panel
2. If all platforms failing → check MongoDB/Redis connectivity (`/ready` endpoint)
3. If one platform failing → check their API status page + platform credentials
4. If circuit breaker is OPEN:
   - Wait for cooldown (5 min auto-reset to HALF_OPEN)
   - Or manually reset: `redis-cli -h redis-cache DEL circuit:{platform}:state`

---

## Runbook 4: MongoDB Connectivity Loss (P0)

**Symptoms:** `/ready` returns 503, all posts stuck in queued

**Resolution:**
1. Check MongoDB Atlas status page
2. Verify network connectivity from API container:
   ```bash
   docker exec api curl -s $MONGODB_URI
   ```
3. Check Motor pool exhaustion in logs (search for `motor pool`)
4. If Atlas: check IP allowlist hasn't blocked server IP
5. Restart API to refresh connection pool:
   ```bash
   docker service update --force socialentangler_api
   ```

---

## Runbook 5: Redis Queue Lost (P0)

**Symptoms:** Celery workers idle, Beat not enqueuing, posts stuck in scheduled

**CRITICAL:** Redis-queue uses `appendonly yes` + `appendfsync everysec`.
RDB snapshots are stored in `/data`. Redis restart should restore state.

**Resolution:**
1. Verify appendonly file is intact:
   ```bash
   docker exec redis-queue redis-cli DEBUG RELOAD
   ```
2. If data is corrupted, posts remain in `scheduled` status in MongoDB.
   Beat will re-enqueue on next 30s scan cycle — no manual intervention needed.
3. Verify Beat is running:
   ```bash
   docker service ps socialentangler_beat
   ```

---

## Runbook 6: Certificate / Secret Rotation

**For ENCRYPTION_KEY rotation:**
1. Generate new key: `python -c "from utils.encryption import generate_key; print(generate_key())"`
2. Add `ENCRYPTION_KEY_NEW` to environment
3. Run migration task to re-encrypt all tokens with new key
4. Swap `ENCRYPTION_KEY` → `ENCRYPTION_KEY_NEW`, remove old
5. Restart all services

**For Firebase credentials:**
1. Generate new service account key in Firebase console
2. Update `FIREBASE_ADMIN_SDK_JSON` path and restart API
3. Old key is valid for 24h — no rollback needed

---

## Runbook 7: Post-Incident Checklist

- [ ] Incident timeline documented in Notion
- [ ] Root cause identified
- [ ] Post-mortem shared with team within 48 hours
- [ ] Grafana dashboards verified (all panels showing data)
- [ ] Alert rules reviewed and tightened if needed
- [ ] Runbook updated with new learnings
- [ ] Error budget impact calculated (see monitoring/slo.md)
