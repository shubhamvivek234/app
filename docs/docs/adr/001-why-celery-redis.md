# ADR 001 — Why Celery + Redis Instead of APScheduler

Date: 2024-01-01
Status: Accepted
Deciders: Engineering team

---

## Context

SocialEntangler needs to schedule posts across 6 social media platforms for
10,000–30,000+ monthly users. The original implementation used APScheduler
running inside the FastAPI process.

Problems with APScheduler at scale:
- Runs inside FastAPI process — a server restart loses ALL pending jobs
- Single-threaded — one video upload blocks every other post for 2+ minutes
- No independent scaling — cannot add more scheduling capacity without
  adding API server capacity
- No retry mechanism — failures require manual intervention
- No dead letter queue — permanently failed jobs are silently dropped
- No rate limiting — nothing prevents platform API bans

---

## Decision

Replace APScheduler with Celery 5 + Redis 7.

- **Celery Beat** (replicas:1, K8s Deployment) replaces the APScheduler
  polling loop. State stored in Redis — survives restarts.
- **Celery Workers** (separate K8s pods, KEDA autoscaling) replace the
  inline FastAPI task execution. Scale independently from the API.
- **Redis** serves as both the message broker and the result backend,
  meaning one infrastructure dependency handles both roles.

---

## Alternatives Considered

**ARQ (async job queue for Python/asyncio)**
- Pros: fully async, simpler
- Cons: much smaller ecosystem, fewer production deployments, no Beat equivalent

**BullMQ (Node.js)**
- Pros: excellent, battle-tested at scale
- Cons: requires Node.js runtime alongside Python — adds operational overhead,
  different language in same codebase

**RQ (Redis Queue)**
- Pros: simple, pure Python
- Cons: no Beat equivalent, no priority queues, no fan-out support

**Celery was chosen because:**
- Industry-standard Python task queue with 10+ years of production use
- Celery Beat is a mature, standalone scheduler with Redis-backed state
- Workers scale independently as separate Kubernetes pods
- Built-in exponential backoff retry and dead letter queue routing
- Redis as broker + backend = one dependency, not two

---

## Consequences

Positive:
- Server restarts no longer lose pending jobs
- Workers autoscale based on queue depth (KEDA)
- Platform publishing is isolated — one platform failure cannot block others
- Exponential backoff prevents thundering herd on platform outages
- Dead letter queue makes permanently failed jobs visible in admin panel

Negative:
- Redis is now a critical dependency — Redis outage = no publishing
  (mitigated by Redis Sentinel/Cluster in Stage 5)
- More complex local development setup (Docker Compose required)
- Workers need separate K8s deployment and monitoring

---

## References

- Architecture v2.9, Section 4: Job Queue & Worker Architecture
- Implementation Plan v3.0, Stage 1: Core Queue Infrastructure
