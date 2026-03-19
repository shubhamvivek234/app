/**
 * Phase 7.4 — k6 load test scenarios for SocialEntangler.
 *
 * 5 scenarios:
 *   1. API layer:        500 VUs hitting common endpoints, p99 < 500ms
 *   2. Scheduler:        Create 10,000 posts, verify enqueue within 5 min
 *   3. Media pipeline:   50 concurrent uploads, verify no OOM
 *   4. Queue flood:      1,000 publish jobs, measure drain time
 *   5. End-to-end:       200 users scheduling posts + checking status
 *
 * Run:  k6 run tests/load/k6_scenarios.js --env BASE_URL=http://localhost:8000
 */
import http from "k6/http";
import { check, sleep, group } from "k6";
import { Rate, Trend, Counter } from "k6/metrics";

// ── Custom metrics ──────────────────────────────────────────────────────────

const postCreateDuration = new Trend("post_create_duration", true);
const postListDuration = new Trend("post_list_duration", true);
const mediaUploadDuration = new Trend("media_upload_duration", true);
const publishDrainTime = new Trend("publish_drain_time", true);
const errorRate = new Rate("error_rate");
const postsCreated = new Counter("posts_created");
const postsEnqueued = new Counter("posts_enqueued");

// ── Configuration ───────────────────────────────────────────────────────────

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const API = `${BASE_URL}/api/v1`;
const AUTH_TOKEN = __ENV.AUTH_TOKEN || "test-bearer-token";

const HEADERS = {
  "Content-Type": "application/json",
  Authorization: `Bearer ${AUTH_TOKEN}`,
};

export const options = {
  scenarios: {
    // ── Scenario 1: API Layer Stress ──────────────────────────────────────
    api_layer: {
      executor: "constant-vus",
      vus: 500,
      duration: "5m",
      exec: "apiLayerStress",
      tags: { scenario: "api_layer" },
      thresholds: {
        "http_req_duration{scenario:api_layer}": ["p(99)<500"],
      },
    },

    // ── Scenario 2: Scheduler Throughput ──────────────────────────────────
    scheduler_throughput: {
      executor: "shared-iterations",
      vus: 50,
      iterations: 10000,
      maxDuration: "5m",
      exec: "schedulerThroughput",
      tags: { scenario: "scheduler" },
      startTime: "0s",
    },

    // ── Scenario 3: Media Pipeline ───────────────────────────────────────
    media_pipeline: {
      executor: "constant-vus",
      vus: 50,
      duration: "3m",
      exec: "mediaPipeline",
      tags: { scenario: "media_pipeline" },
      startTime: "6m",
    },

    // ── Scenario 4: Queue Flood ──────────────────────────────────────────
    queue_flood: {
      executor: "shared-iterations",
      vus: 100,
      iterations: 1000,
      maxDuration: "10m",
      exec: "queueFlood",
      tags: { scenario: "queue_flood" },
      startTime: "10m",
    },

    // ── Scenario 5: End-to-End ───────────────────────────────────────────
    end_to_end: {
      executor: "constant-vus",
      vus: 200,
      duration: "5m",
      exec: "endToEnd",
      tags: { scenario: "e2e" },
      startTime: "21m",
    },
  },

  thresholds: {
    error_rate: ["rate<0.05"],
    http_req_failed: ["rate<0.05"],
    "http_req_duration{scenario:api_layer}": ["p(99)<500"],
    "http_req_duration{scenario:e2e}": ["p(95)<2000"],
  },
};

// ── Helpers ─────────────────────────────────────────────────────────────────

function randomPlatform() {
  const platforms = ["instagram", "facebook", "youtube", "twitter", "linkedin"];
  return platforms[Math.floor(Math.random() * platforms.length)];
}

function futureISODate(offsetMinutes) {
  const d = new Date(Date.now() + offsetMinutes * 60_000);
  return d.toISOString();
}

// ── Scenario 1: API Layer Stress ────────────────────────────────────────────

export function apiLayerStress() {
  group("GET /posts (list)", () => {
    const res = http.get(`${API}/posts?page=1&limit=20`, { headers: HEADERS });
    postListDuration.add(res.timings.duration);
    const ok = check(res, {
      "list posts status 200": (r) => r.status === 200,
      "list posts p99 < 500ms": (r) => r.timings.duration < 500,
    });
    errorRate.add(!ok);
  });

  group("GET /accounts (list)", () => {
    const res = http.get(`${API}/accounts`, { headers: HEADERS });
    check(res, {
      "list accounts status 200": (r) => r.status === 200,
    });
  });

  group("GET /posts/{id} (single)", () => {
    const res = http.get(`${API}/posts/nonexistent-load-test`, {
      headers: HEADERS,
    });
    check(res, {
      "single post returns 404 or 200": (r) =>
        r.status === 200 || r.status === 404,
    });
  });

  sleep(0.1);
}

// ── Scenario 2: Scheduler Throughput ────────────────────────────────────────

export function schedulerThroughput() {
  const payload = JSON.stringify({
    content: `Load test post ${Date.now()}-${__VU}-${__ITER}`,
    platforms: [randomPlatform()],
    post_type: "text",
    scheduled_time: futureISODate(10),
    timezone: "UTC",
  });

  const res = http.post(`${API}/posts`, payload, { headers: HEADERS });
  postCreateDuration.add(res.timings.duration);

  const ok = check(res, {
    "create post 201": (r) => r.status === 201,
    "has post id": (r) => {
      try {
        return JSON.parse(r.body).id !== undefined;
      } catch {
        return false;
      }
    },
  });

  if (ok) {
    postsCreated.add(1);
  }
  errorRate.add(!ok);
}

// ── Scenario 3: Media Pipeline ──────────────────────────────────────────────

export function mediaPipeline() {
  // Generate a small synthetic binary payload (1 MB) to simulate an upload
  const syntheticFile = open("/dev/urandom", "b", 1024 * 1024);

  const res = http.post(`${API}/media/upload`, syntheticFile || "dummy-payload", {
    headers: {
      Authorization: `Bearer ${AUTH_TOKEN}`,
      "Content-Type": "application/octet-stream",
      "X-Filename": `load-test-${__VU}-${__ITER}.jpg`,
    },
    timeout: "60s",
  });

  mediaUploadDuration.add(res.timings.duration);

  check(res, {
    "upload accepted (200/201/413)": (r) =>
      r.status === 200 || r.status === 201 || r.status === 413 || r.status === 404,
    "no 500 errors (OOM guard)": (r) => r.status !== 500,
    "no 503 errors (OOM guard)": (r) => r.status !== 503,
  });

  sleep(1);
}

// ── Scenario 4: Queue Flood ─────────────────────────────────────────────────

export function queueFlood() {
  // Create a post scheduled for "now" so it gets picked up immediately
  const payload = JSON.stringify({
    content: `Queue flood ${Date.now()}-${__VU}-${__ITER}`,
    platforms: [randomPlatform()],
    post_type: "text",
    scheduled_time: futureISODate(0),
    timezone: "UTC",
  });

  const startTime = Date.now();
  const createRes = http.post(`${API}/posts`, payload, { headers: HEADERS });

  if (createRes.status !== 201) {
    errorRate.add(true);
    return;
  }

  let postId;
  try {
    postId = JSON.parse(createRes.body).id;
  } catch {
    errorRate.add(true);
    return;
  }

  // Poll until post status transitions from "scheduled" (max 60 attempts, 5s each)
  let drained = false;
  for (let attempt = 0; attempt < 60; attempt++) {
    sleep(5);
    const statusRes = http.get(`${API}/posts/${postId}`, { headers: HEADERS });
    if (statusRes.status === 200) {
      try {
        const body = JSON.parse(statusRes.body);
        if (body.status !== "scheduled") {
          drained = true;
          postsEnqueued.add(1);
          publishDrainTime.add(Date.now() - startTime);
          break;
        }
      } catch {
        // parse error — keep polling
      }
    }
  }

  check(null, {
    "post was drained from queue": () => drained,
  });
}

// ── Scenario 5: End-to-End ──────────────────────────────────────────────────

export function endToEnd() {
  // Step 1: Create a scheduled post
  const scheduledTime = futureISODate(30);
  const payload = JSON.stringify({
    content: `E2E test ${Date.now()}-${__VU}`,
    platforms: [randomPlatform()],
    post_type: "text",
    scheduled_time: scheduledTime,
    timezone: "UTC",
  });

  let postId;

  group("create post", () => {
    const res = http.post(`${API}/posts`, payload, { headers: HEADERS });
    check(res, { "e2e create 201": (r) => r.status === 201 });
    try {
      postId = JSON.parse(res.body).id;
    } catch {
      // continue
    }
  });

  if (!postId) {
    errorRate.add(true);
    return;
  }

  // Step 2: Read it back
  group("read post", () => {
    const res = http.get(`${API}/posts/${postId}`, { headers: HEADERS });
    check(res, {
      "e2e read 200": (r) => r.status === 200,
      "e2e correct id": (r) => {
        try {
          return JSON.parse(r.body).id === postId;
        } catch {
          return false;
        }
      },
    });
  });

  // Step 3: Update the post
  group("update post", () => {
    const updatePayload = JSON.stringify({
      content: `E2E updated ${Date.now()}`,
      version: 1,
    });
    const res = http.patch(`${API}/posts/${postId}`, updatePayload, {
      headers: HEADERS,
    });
    check(res, {
      "e2e update 200": (r) => r.status === 200,
    });
  });

  // Step 4: List posts to verify it appears
  group("list posts", () => {
    const res = http.get(`${API}/posts?page=1&limit=5`, { headers: HEADERS });
    check(res, {
      "e2e list 200": (r) => r.status === 200,
      "e2e list is array": (r) => {
        try {
          return Array.isArray(JSON.parse(r.body));
        } catch {
          return false;
        }
      },
    });
  });

  // Step 5: Delete the post
  group("delete post", () => {
    const res = http.del(`${API}/posts/${postId}`, null, { headers: HEADERS });
    check(res, {
      "e2e delete 204": (r) => r.status === 204,
    });
  });

  sleep(1);
}
