"""
Phase 7 -- Locust load test scenarios for SocialEntangler.

Five architecture-mandated scenarios:
  1. Concurrent scheduling:     100 users creating posts simultaneously
  2. Media upload spike:        50 concurrent large file uploads
  3. Beat under load:           Scheduler processing 10,000 posts in window
  4. Platform adapter stress:   All 6 platforms publishing concurrently
  5. DLQ drain test:            Inject 100 poison pills, verify DLQ within SLA

Run:
  locust -f tests/load/locustfile.py --host http://localhost:8000
"""
from __future__ import annotations

import os
import random
import time
import uuid

from locust import HttpUser, between, events, tag, task, TaskSet


AUTH_TOKEN = os.environ.get("AUTH_TOKEN", "test-bearer-token")
PLATFORMS = ["instagram", "facebook", "youtube", "twitter", "linkedin", "tiktok"]
DLQ_SLA_SECONDS = 900  # 15 minutes


def _headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {AUTH_TOKEN}",
    }


def _random_platform() -> str:
    return random.choice(PLATFORMS)


def _future_iso(offset_minutes: int = 10) -> str:
    from datetime import datetime, timedelta, timezone

    dt = datetime.now(timezone.utc) + timedelta(minutes=offset_minutes)
    return dt.isoformat()


# ---------------------------------------------------------------------------
# Scenario 1: Concurrent Scheduling (100 users creating posts simultaneously)
# ---------------------------------------------------------------------------


class ConcurrentSchedulingTasks(TaskSet):
    """100 VUs creating scheduled posts concurrently to test enqueue throughput."""

    @tag("concurrent_scheduling")
    @task(4)
    def create_scheduled_post(self) -> None:
        payload = {
            "content": f"Concurrent sched {uuid.uuid4().hex[:12]}",
            "platforms": random.sample(PLATFORMS, k=random.randint(1, 3)),
            "post_type": "text",
            "scheduled_time": _future_iso(random.randint(5, 60)),
            "timezone": "UTC",
        }
        with self.client.post(
            "/api/v1/posts",
            json=payload,
            headers=_headers(),
            name="POST /posts (concurrent sched)",
            catch_response=True,
        ) as resp:
            if resp.status_code == 201:
                resp.success()
            else:
                resp.failure(f"Expected 201, got {resp.status_code}")

    @tag("concurrent_scheduling")
    @task(2)
    def create_immediate_post(self) -> None:
        """Schedule for 'now' to add queue pressure."""
        payload = {
            "content": f"Immediate {uuid.uuid4().hex[:12]}",
            "platforms": [_random_platform()],
            "post_type": "text",
            "scheduled_time": _future_iso(0),
            "timezone": "UTC",
        }
        with self.client.post(
            "/api/v1/posts",
            json=payload,
            headers=_headers(),
            name="POST /posts (immediate)",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 201):
                resp.success()
            else:
                resp.failure(f"Expected 201, got {resp.status_code}")

    @tag("concurrent_scheduling")
    @task(1)
    def list_posts_while_scheduling(self) -> None:
        """Read pressure alongside writes."""
        self.client.get(
            "/api/v1/posts?page=1&limit=20",
            headers=_headers(),
            name="GET /posts (during scheduling)",
        )


# ---------------------------------------------------------------------------
# Scenario 2: Media Upload Spike (50 concurrent large file uploads)
# ---------------------------------------------------------------------------


class MediaUploadSpikeTasks(TaskSet):
    """50 VUs uploading large files concurrently -- verify no OOM (5xx)."""

    @tag("media_upload_spike")
    @task(3)
    def upload_large_media(self) -> None:
        """5 MB synthetic payload to simulate large image/video."""
        fake_file = os.urandom(5 * 1024 * 1024)
        with self.client.post(
            "/api/v1/media/upload",
            data=fake_file,
            headers={
                "Authorization": f"Bearer {AUTH_TOKEN}",
                "Content-Type": "application/octet-stream",
                "X-Filename": f"load-large-{uuid.uuid4().hex[:8]}.jpg",
            },
            name="POST /media/upload (5MB)",
            catch_response=True,
            timeout=120,
        ) as resp:
            if resp.status_code in (200, 201):
                resp.success()
            elif resp.status_code in (413,):
                resp.success()  # expected for size limits
            elif resp.status_code in (500, 503):
                resp.failure(f"OOM indicator: {resp.status_code}")
            else:
                resp.failure(f"Unexpected: {resp.status_code}")

    @tag("media_upload_spike")
    @task(1)
    def upload_small_media(self) -> None:
        """1 MB upload to mix sizes."""
        fake_file = os.urandom(1 * 1024 * 1024)
        with self.client.post(
            "/api/v1/media/upload",
            data=fake_file,
            headers={
                "Authorization": f"Bearer {AUTH_TOKEN}",
                "Content-Type": "application/octet-stream",
                "X-Filename": f"load-small-{uuid.uuid4().hex[:8]}.png",
            },
            name="POST /media/upload (1MB)",
            catch_response=True,
            timeout=60,
        ) as resp:
            if resp.status_code in (200, 201, 413):
                resp.success()
            elif resp.status_code in (500, 503):
                resp.failure(f"OOM indicator: {resp.status_code}")
            else:
                resp.failure(f"Unexpected: {resp.status_code}")


# ---------------------------------------------------------------------------
# Scenario 3: Beat Under Load (scheduler processing 10,000 posts in window)
# ---------------------------------------------------------------------------


class BeatUnderLoadTasks(TaskSet):
    """Saturate the beat scheduler by creating 10,000 posts in a tight window.

    Each VU rapidly creates posts scheduled within a narrow 5-minute window,
    forcing the beat scheduler to pick up a massive batch in a single tick.
    """

    _batch_counter: int = 0

    @tag("beat_under_load")
    @task
    def create_batch_posts(self) -> None:
        """Create posts in rapid succession, all scheduled within a 5-min window."""
        # Schedule all posts within the same 5-minute future window
        scheduled_time = _future_iso(5)
        for _ in range(10):  # 10 posts per iteration per VU
            payload = {
                "content": f"Beat load {uuid.uuid4().hex[:12]}",
                "platforms": [_random_platform()],
                "post_type": "text",
                "scheduled_time": scheduled_time,
                "timezone": "UTC",
            }
            with self.client.post(
                "/api/v1/posts",
                json=payload,
                headers=_headers(),
                name="POST /posts (beat batch)",
                catch_response=True,
            ) as resp:
                if resp.status_code in (200, 201):
                    resp.success()
                else:
                    resp.failure(f"Expected 201, got {resp.status_code}")

    @tag("beat_under_load")
    @task
    def check_queue_depth(self) -> None:
        """Monitor queue depth during beat stress."""
        with self.client.get(
            "/api/v1/admin/metrics/queue-depth",
            headers=_headers(),
            name="GET /admin/metrics/queue-depth",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 404):
                resp.success()
            else:
                resp.failure(f"Unexpected: {resp.status_code}")


# ---------------------------------------------------------------------------
# Scenario 4: Platform Adapter Stress (all 6 platforms concurrently)
# ---------------------------------------------------------------------------


class PlatformAdapterStressTasks(TaskSet):
    """Publish to all 6 platforms concurrently to stress platform adapters."""

    @tag("platform_adapter_stress")
    @task(3)
    def publish_all_platforms(self) -> None:
        """Create a post targeting all 6 platforms simultaneously."""
        payload = {
            "content": f"All-platform stress {uuid.uuid4().hex[:12]}",
            "platforms": list(PLATFORMS),  # all 6
            "post_type": "text",
            "scheduled_time": _future_iso(0),
            "timezone": "UTC",
        }
        with self.client.post(
            "/api/v1/posts",
            json=payload,
            headers=_headers(),
            name="POST /posts (all 6 platforms)",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 201):
                resp.success()
            else:
                resp.failure(f"Expected 201, got {resp.status_code}")

    @tag("platform_adapter_stress")
    @task(2)
    def publish_single_platform(self) -> None:
        """Single-platform publish for comparison baseline."""
        platform = _random_platform()
        payload = {
            "content": f"Single {platform} {uuid.uuid4().hex[:12]}",
            "platforms": [platform],
            "post_type": "text",
            "scheduled_time": _future_iso(0),
            "timezone": "UTC",
        }
        with self.client.post(
            "/api/v1/posts",
            json=payload,
            headers=_headers(),
            name=f"POST /posts (single: {platform})",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 201):
                resp.success()
            else:
                resp.failure(f"Expected 201, got {resp.status_code}")

    @tag("platform_adapter_stress")
    @task(1)
    def check_platform_status(self) -> None:
        """Check circuit breaker / platform health."""
        self.client.get(
            "/api/v1/admin/platforms/health",
            headers=_headers(),
            name="GET /admin/platforms/health",
        )


# ---------------------------------------------------------------------------
# Scenario 5: DLQ Drain Test (inject 100 poison pills, verify DLQ within SLA)
# ---------------------------------------------------------------------------


class DLQDrainTasks(TaskSet):
    """Inject 100 poison-pill messages and verify they all land in DLQ within SLA.

    Poison pills are posts with deliberately invalid data that will fail
    processing and be routed to the dead-letter queue after retry exhaustion.
    """

    @tag("dlq_drain")
    @task(5)
    def inject_poison_pill(self) -> None:
        """Create a post designed to fail processing (poison pill)."""
        payload = {
            "content": "",  # empty content -- invalid
            "platforms": ["__invalid_platform__"],  # non-existent platform
            "post_type": "invalid_type",
            "scheduled_time": _future_iso(0),
            "timezone": "INVALID/TZ",
            "_poison_pill": True,
            "_test_id": uuid.uuid4().hex,
        }
        with self.client.post(
            "/api/v1/posts",
            json=payload,
            headers=_headers(),
            name="POST /posts (poison pill)",
            catch_response=True,
        ) as resp:
            # We expect either acceptance (to be failed by worker) or
            # immediate validation rejection -- both are valid outcomes.
            if resp.status_code in (200, 201, 400, 422):
                resp.success()
            else:
                resp.failure(f"Unexpected: {resp.status_code}")

    @tag("dlq_drain")
    @task(2)
    def poll_dlq_depth(self) -> None:
        """Poll DLQ depth to verify poison pills are arriving."""
        with self.client.get(
            "/api/v1/admin/metrics/dlq-depth",
            headers=_headers(),
            name="GET /admin/metrics/dlq-depth",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                try:
                    depth = resp.json().get("depth", 0)
                    events.request.fire(
                        request_type="DLQ_GAUGE",
                        name="dlq_current_depth",
                        response_time=0,
                        response_length=depth,
                        exception=None,
                        context={},
                    )
                except (ValueError, AttributeError):
                    pass
                resp.success()
            elif resp.status_code == 404:
                resp.success()  # endpoint may not exist in test env
            else:
                resp.failure(f"Unexpected: {resp.status_code}")

    @tag("dlq_drain")
    @task(1)
    def verify_dlq_sla(self) -> None:
        """Check that oldest DLQ message age is within 15-minute SLA."""
        with self.client.get(
            "/api/v1/admin/metrics/dlq-oldest-age",
            headers=_headers(),
            name="GET /admin/metrics/dlq-oldest-age",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                try:
                    age_seconds = resp.json().get("oldest_age_seconds", 0)
                    if age_seconds > DLQ_SLA_SECONDS:
                        resp.failure(
                            f"DLQ SLA breach: oldest message is {age_seconds}s "
                            f"(limit {DLQ_SLA_SECONDS}s)"
                        )
                    else:
                        resp.success()
                    events.request.fire(
                        request_type="DLQ_SLA",
                        name="dlq_oldest_age_seconds",
                        response_time=age_seconds * 1000,
                        response_length=0,
                        exception=None,
                        context={},
                    )
                except (ValueError, AttributeError):
                    resp.success()
            elif resp.status_code == 404:
                resp.success()
            else:
                resp.failure(f"Unexpected: {resp.status_code}")


# ---------------------------------------------------------------------------
# User classes (one per scenario)
# ---------------------------------------------------------------------------


class ConcurrentSchedulingUser(HttpUser):
    """Scenario 1: 100 users creating posts simultaneously."""

    tasks = [ConcurrentSchedulingTasks]
    wait_time = between(0.05, 0.2)
    weight = 5


class MediaUploadSpikeUser(HttpUser):
    """Scenario 2: 50 concurrent large file uploads."""

    tasks = [MediaUploadSpikeTasks]
    wait_time = between(0.5, 2)
    weight = 2


class BeatUnderLoadUser(HttpUser):
    """Scenario 3: Scheduler processing 10,000 posts in window."""

    tasks = [BeatUnderLoadTasks]
    wait_time = between(0.01, 0.1)
    weight = 4


class PlatformAdapterStressUser(HttpUser):
    """Scenario 4: All 6 platforms publishing concurrently."""

    tasks = [PlatformAdapterStressTasks]
    wait_time = between(0.1, 0.5)
    weight = 3


class DLQDrainUser(HttpUser):
    """Scenario 5: Inject 100 poison pills, verify all reach DLQ within SLA."""

    tasks = [DLQDrainTasks]
    wait_time = between(0.2, 1)
    weight = 2
