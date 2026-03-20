# Runbook: Queue Depth Spike

**Grafana alert:** `queue_depth > 500 AND increasing`
**Severity:** High
**On-call action required:** Yes

---

## Symptoms

- Grafana alert fires: queue depth > 500 and growing
- Users report posts not publishing on time
- DLQ count may also be rising

---

## Diagnosis (do these in order, stop when you find the cause)

```bash
# 1. Which queue is spiking?
redis-cli -h redis-queue LLEN celery  # default queue
redis-cli -h redis-queue LLEN high_priority
redis-cli -h redis-queue LLEN media_processing

# 2. How many workers are running?
kubectl get pods -l app=celery-worker

# 3. Are workers processing or stuck?
kubectl logs -l app=celery-worker --tail=50 | grep "Task\|ERROR\|WARN"

# 4. Is there a platform outage causing retries to pile up?
# Check circuit breaker states:
redis-cli -h redis-cache GET circuit:instagram:state
redis-cli -h redis-cache GET circuit:youtube:state
redis-cli -h redis-cache GET circuit:tiktok:state

# 5. Is maintenance_mode accidentally on?
redis-cli -h redis-cache GET feature_flag:maintenance_mode

# 6. Is Redis queue memory near limit?
redis-cli -h redis-queue INFO memory | grep used_memory_human
```

---

## Resolution

### Cause: Not enough workers (most common)

```bash
# Scale workers up immediately
kubectl scale deployment celery-worker --replicas=15

# Watch queue drain
watch -n5 "redis-cli -h redis-queue LLEN celery"

# Scale back down after queue clears (KEDA will handle this automatically
# once you've let it catch up — just give it 5 minutes)
```

### Cause: Platform outage (circuit breaker should have opened)

```bash
# Check which platform is causing retries
kubectl logs -l app=celery-worker --tail=200 | grep "platform_error" | sort | uniq -c

# If circuit breaker didn't open automatically, open it manually:
redis-cli -h redis-cache SET circuit:instagram:state open EX 600

# This stops workers from hammering the platform.
# Half-open probe happens automatically after 5 minutes.
```

### Cause: maintenance_mode accidentally on

```bash
redis-cli -h redis-cache SET feature_flag:maintenance_mode off EX 300
```

### Cause: Media processing backlog (media_processing queue spiked)

```bash
# Scale media workers specifically
kubectl scale deployment celery-media-worker --replicas=5

# Check if uploads are hitting backpressure (503s):
kubectl logs -l app=api-server --tail=100 | grep "503\|queue_full"
```

---

## After Resolution

1. Scale workers back to normal (or let KEDA handle it)
2. Note cause and resolution in CLAUDE.md under "Known Issues"
3. Check DLQ for any jobs that were permanently failed during the spike
4. Write a post-mortem if the spike caused user impact > 15 minutes

---

## Related

- Architecture v2.9, Section 20.1 (Circuit Breakers)
- Architecture v2.9, Section 15.4 (Redis HA)
- Feature flag: `maintenance_mode`
