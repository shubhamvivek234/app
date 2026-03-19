# Phase 0-A Progress — Security & Infrastructure Baseline

Implementation Plan v3.0 reference: Stage 0, Phase 0-A
Architecture v2.9 reference: Sec 10.1, 12.2, 15.2, 24.1–24.5
Estimated duration: 1–2 days

---

## Tasks

- [ ] **VPC isolation — Redis and MongoDB must never have public IPs**
  - GCP VPC configured
  - Redis port 6379 accessible only from private subnet
  - MongoDB Atlas Private Endpoint enabled
  - Verified: `nmap` from external host shows all ports closed

- [ ] **HTTP security headers middleware**
  - `api/middleware/security_headers.py` created
  - Content-Security-Policy injected on all responses
  - HSTS (max-age=31536000; includeSubDomains; preload) injected
  - X-Frame-Options: DENY
  - X-Content-Type-Options: nosniff
  - Referrer-Policy: strict-origin-when-cross-origin
  - Test: `curl -I https://api.yourdomain.com/api/v1/health` shows all headers

- [ ] **CORS explicit allowlist — never wildcard**
  - `allow_origins` is a list of explicit domains, not `['*']`
  - `localhost:3000` only present via env var in dev mode
  - Test: OPTIONS request from `https://evil.com` returns no ACAO header

- [ ] **TLS everywhere: Cloudflare Full Strict + HSTS preload**
  - Cloudflare SSL mode set to Full (Strict)
  - HTTP → HTTPS redirect at load balancer
  - TLS 1.0 and 1.1 disabled at Cloudflare
  - Test: `curl -I http://api.yourdomain.com` returns 301

- [ ] **Secret scanning: TruffleHog pre-commit + GitHub Secret Scanning**
  - TruffleHog installed as git pre-commit hook
  - GitHub Secret Scanning enabled on repository
  - `.gitignore` updated with: `.env*`, `*.pem`, `*.key`, `*service-account*.json`, `*adminsdk*.json`
  - Test: commit a fake token string — hook must block it

- [ ] **Non-root Docker containers, distroless base images**
  - `USER 1001` in all Dockerfiles
  - Base image: `gcr.io/distroless/python3-debian12`
  - K8s pod specs: `runAsNonRoot: true`, `runAsUser: 1001`, `readOnlyRootFilesystem: true`, `allowPrivilegeEscalation: false`
  - Test: `docker run --rm <image> whoami` returns `nonroot`

- [ ] **Pydantic type enforcement audit on all API endpoints**
  - Every POST/PUT/PATCH endpoint uses a typed Pydantic `BaseModel`
  - `EmailStr` on email fields
  - `Field(min_length=1, max_length=2000)` on content fields
  - Test: send `{"content": {"malicious": "obj"}}` where string expected → 422

- [ ] **Same-region deployment + spot workers + GCP budget alerts**
  - All services (API, workers, Redis, GCS bucket) in same GCP region (e.g., `us-central1`)
  - Spot instance node pool created for Celery workers
  - Budget alerts configured at 50%, 80%, 100%
  - GCS lifecycle rules set: `/quarantine/` objects age > 1 day → delete

---

## Implementation Notes

(fill in as you work)

---

## Test Results

```bash
# Run security tests after completing this phase
pytest tests/security/ -v

# Expected: all pass
```

---

## Done When

All checkboxes above are ticked AND `pytest tests/security/ -v` passes.
Update CLAUDE.md: set Phase to 0-B, move 0-A tasks to "Last Session Completed".
