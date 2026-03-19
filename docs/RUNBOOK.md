# SocialEntangler Operations Runbook

## Quick Reference

| Issue | First Step |
|-------|-----------|
| Posts not publishing | Check Celery worker logs + Redis queue depth |
| Backend 500 errors | Check Sentry + `docker-compose logs api` |
| Redis memory full | `redis-cli info memory` -> increase maxmemory or flush cache DB |
| MongoDB slow queries | Check Atlas Performance Advisor |
| High CPU on workers | Scale workers: `docker-compose up -d --scale worker=4` |

---

## 1. Checking System Health

```bash
# Health endpoints
curl http://localhost:8001/health
curl http://localhost:8001/ready

# Docker (production)
docker-compose ps
docker-compose logs -f --tail=100 api
docker-compose logs -f --tail=100 worker

# Redis
redis-cli info server | grep uptime
redis-cli info memory | grep used_memory_human
redis-cli llen celery   # Celery queue depth

# Celery
celery -A celery_app inspect active    # Active tasks
celery -A celery_app inspect reserved  # Queued tasks
celery -A celery_app inspect ping      # Worker health

# Migrations
python -m migrations.runner status
```

---

## 2. Failed Posts Incident

**Symptom:** Users report posts not publishing, status stuck at "scheduled".

**Steps:**
1. Check Celery worker is running: `celery -A celery_app inspect ping`
2. Check Redis queue: `redis-cli llen celery` (should be < 100)
3. Check Beat is running: `docker-compose logs beat | tail -20`
4. Check for failed tasks in DLQ: `GET /api/dlq` endpoint
5. Check platform API status pages (Instagram, Facebook, YouTube status)
6. Check error notifications: `db.notifications.find({type: "error"}).sort({created_at:-1}).limit(10)`

**Resolution:**
- If worker stopped: `docker-compose restart worker`
- If Beat stopped: `docker-compose restart beat`
- If Redis is down: `brew services restart redis` (local) or failover to managed Redis
- If platform API is down: posts will auto-retry (3x, 5 min apart)

---

## 3. Redis Memory Alert (>70%)

```bash
redis-cli info memory
# Check maxmemory setting
redis-cli config get maxmemory
# Flush cache DB (DB 1) -- safe, cache is ephemeral
redis-cli -n 1 FLUSHDB
# Check large keys
redis-cli --bigkeys
```

---

## 4. Database Slow Queries

```bash
# Check MongoDB index usage
db.posts.getIndexes()
# Check slow queries (in Atlas UI: Performance Advisor)
# Run migration to add missing indexes:
python -m migrations.runner up
```

---

## 5. Scaling Workers

```bash
# Docker Compose
docker-compose up -d --scale worker=4

# Kubernetes
kubectl scale deployment socialentangler-worker --replicas=8
kubectl get hpa  # Check autoscaler status
```

---

## 6. Emergency: Rollback Deployment

```bash
# Docker Compose: revert to previous image tag
docker-compose pull  # or specify previous tag
docker-compose up -d

# Kubernetes
kubectl rollout undo deployment/socialentangler-api
kubectl rollout undo deployment/socialentangler-worker
```

---

## 7. Backup & Restore

```bash
# MongoDB backup (Atlas: use UI point-in-time restore)
# Local backup:
mongodump --uri=$MONGO_URL --out=/backup/$(date +%Y%m%d)

# Restore:
mongorestore --uri=$MONGO_URL /backup/20240101/

# Redis backup (AOF):
redis-cli BGSAVE
cp /var/lib/redis/dump.rdb /backup/redis-$(date +%Y%m%d).rdb
```

---

## 8. SSL Certificate Renewal

```bash
# If using Certbot with nginx:
certbot renew --nginx
nginx -s reload

# Check expiry:
echo | openssl s_client -connect yourdomain.com:443 2>/dev/null | openssl x509 -noout -dates
```

---

## 9. SLA Targets

| Metric | Target |
|--------|--------|
| API uptime | 99.5% monthly |
| Post publish latency | < 2 min from scheduled_time |
| API response time (p95) | < 500ms |
| Scheduled post success rate | > 95% |

---

## 10. Alerting Rules (Grafana)

Configure these alerts in Grafana Cloud:

| Alert | Condition | Severity |
|-------|-----------|----------|
| High error rate | >5% 5xx responses in 5min | Critical |
| Redis memory | >70% maxmemory | Warning |
| Celery queue depth | >200 pending tasks | Warning |
| Worker count | 0 active workers | Critical |
| Post failure rate | >10% posts failing | Warning |
| MongoDB connections | >80% pool size | Warning |
