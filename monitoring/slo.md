# SocialEntangler SLO Definitions

## Service Level Objectives

| SLO | Target | Measurement Window | Alert Threshold |
|-----|--------|--------------------|-----------------|
| Publish success rate | ≥ 99% | 7-day rolling | < 90% for 5m |
| API availability (5xx) | < 1% | 30-day rolling | > 1% for 3m |
| API P99 latency | ≤ 500ms | 24-hour rolling | P99 > 2s for 5m |
| Scheduling drift | ≤ 30s | per-post | > 60s (alert) |
| Webhook delivery | ≥ 99.5% | 7-day rolling | N/A (best-effort) |
| DLQ depth | = 0 | real-time | > 0 for 2m |
| Media processing time | ≤ 120s P95 | 24-hour rolling | P95 > 300s |

## Error Budget

Error budget = 100% - SLO target × measurement window

| SLO | Monthly error budget |
|-----|---------------------|
| Publish success 99% | 7.2 hours downtime |
| API availability 99% | 7.2 hours |
| API latency 500ms P99 | ~21.6 hours of slow requests |

## Burn Rate Alerts

Fast burn (page immediately): consumes 2% of monthly budget in 1 hour.
Slow burn (ticket): consumes 5% of monthly budget in 6 hours.

These map to the Prometheus alert rules in `monitoring/prometheus/alerts.yml`.

## Measurement

All SLOs are tracked via Prometheus queries and surfaced in the Grafana
"SocialEntangler — Platform Overview" dashboard (uid: `se-platform-overview`).

Error budget tracking is manual for now (Phase 5.8 baseline).
Automated error budget dashboards are planned for Phase 9.
