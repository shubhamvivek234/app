# SocialEntangler — Mistake Log

> Claude Code reads this file at EVERY session start, immediately after CLAUDE.md.
> When you make a mistake or are corrected by the developer, add an entry here.
> Never delete entries — mark them RESOLVED when the root cause is fixed.
> The goal: make each mistake exactly once.

---

## How to Add a Mistake Entry

When you are corrected, catch yourself writing wrong code, or a test fails
because of a pattern error — stop and add an entry immediately using this format:

```markdown
### M-<next_number>  [OPEN]  <category>
**Date:** YYYY-MM-DD
**What I did wrong:** One sentence. Specific, not vague.
**Why it was wrong:** Why this causes a real problem (data loss, bug, security issue).
**What to check BEFORE writing this type of code again:**
- Concrete pre-check (grep command, doc section, or question to answer)
**Correct pattern:**
\`\`\`python
# The right way to do it
\`\`\`
**File/line where mistake occurred:** path/to/file.py:line_number
```

---

## Categories

- `RULE_VIOLATION` — Broke one of the 12 Absolute Rules in SKILL.md
- `WRONG_PATTERN` — Used a code pattern that is incorrect for this codebase
- `MISSED_EDGE_CASE` — Forgot to handle an EC# from the architecture doc
- `TEST_GAP` — Wrote code without a required test, or wrote a test that doesn't actually cover the case
- `SCHEMA_ERROR` — Queried MongoDB without tenant isolation, missing projection, wrong field
- `EFFICIENCY` — Wasted time re-reading files, re-deriving context, or solving already-solved problems

---

## Open Mistakes — Fix These Before Moving On

> This section is auto-filtered: only OPEN entries appear here.
> When all mistakes in a phase are RESOLVED, this section is empty.

*(none yet — first session)*

---

## All Mistakes (Full Log)

*(entries added here as they occur)*

---

## Resolved Mistakes

*(moved here when root cause is permanently fixed)*

---

## Session Start Check

Run this at the start of every session to see open mistakes relevant to
what you're about to work on:

```bash
# Show all open mistakes
grep -A2 "\[OPEN\]" MISTAKES.md

# Show mistakes in a specific category
grep -A2 "\[OPEN\].*RULE_VIOLATION" MISTAKES.md

# Count how many open mistakes exist
grep -c "\[OPEN\]" MISTAKES.md || echo "0 open mistakes"
```

If there are open RULE_VIOLATION mistakes: re-read that rule in SKILL.md
before writing any code.

If there are open MISSED_EDGE_CASE mistakes: re-read the relevant EC section
in the Implementation Plan before writing similar code.

---

## Mistake Patterns to Watch — Pre-Seeded From Architecture Review

These are known mistake patterns for this codebase. They are pre-logged as
WATCH entries (not mistakes you made yet, but patterns that are commonly
wrong). Treat them as warnings when writing the relevant code.

### W-1  [WATCH]  RULE_VIOLATION
**Pattern:** Accessing `response['id']` or `response['container_id']` directly
after a platform API call that returned HTTP 200.
**Why dangerous:** Instagram, Facebook, TikTok return errors inside HTTP 200
bodies (EC20). Direct key access will KeyError or silently process a failed
response as success.
**Pre-check before writing any platform response parsing:**
```bash
grep -n "response\['" platform_adapters/*.py  # should return 0 results
```
**Correct pattern:** Always `data.get('id')` — never `data['id']`.

---

### W-2  [WATCH]  RULE_VIOLATION
**Pattern:** Writing a `while True: check_status(); sleep(5)` loop inside a
Celery task to poll Instagram/YouTube container processing status.
**Why dangerous:** This blocks the worker thread for up to 2.5 minutes (EC12).
One video upload starves all other posts from being processed.
**Pre-check:**
```bash
grep -n "while\|time.sleep\|asyncio.sleep" celery_tasks/publish_tasks.py
# Any sleep > 1s inside a task body is almost certainly wrong
```
**Correct pattern:** `raise self.retry(countdown=10)` — releases the worker
immediately and returns in 10 seconds.

---

### W-3  [WATCH]  SCHEMA_ERROR
**Pattern:** Writing `db.posts.find_one({"_id": post_id})` or any MongoDB
query that doesn't include `workspace_id` or `user_id` as the first filter.
**Why dangerous:** Breaks multi-tenant isolation. One user can theoretically
access another user's post if they know the post_id (Rule 6).
**Pre-check:**
```bash
grep -n "find_one\|find(" celery_tasks/*.py api/routers/*.py | grep -v "workspace_id\|user_id"
# Every result here is a potential tenant isolation bug
```
**Correct pattern:**
```python
post = await db.posts.find_one({"workspace_id": workspace_id, "_id": post_id})
```

---

### W-4  [WATCH]  RULE_VIOLATION
**Pattern:** Calling `blob.make_public()` or generating permanent public GCS URLs.
**Why dangerous:** Makes all uploaded media permanently world-readable. A
URL in anyone's hands gives permanent access — no expiry, no revocation.
**Pre-check:**
```bash
grep -rn "make_public" . --include="*.py"
# Should return ZERO results in production code
```
**Correct pattern:**
```python
signed_url = blob.generate_signed_url(expiration=timedelta(hours=48), method="GET", version="v4")
```

---

### W-5  [WATCH]  RULE_VIOLATION
**Pattern:** Setting `shutting_down` check after the task's main logic, or
forgetting it entirely.
**Why dangerous:** K8s sends SIGTERM during deployment. Worker mid-API-call
gets killed. Task re-queues. New worker calls platform API again. User gets
a duplicate post (maps to Rule 7 and EC1).
**Pre-check:**
```bash
# Every task must have shutting_down as the FIRST operation
grep -n "def " celery_tasks/publish_tasks.py | head -20
# Then check each function starts with: if shutting_down: raise self.retry(...)
```

---

### W-6  [WATCH]  MISSED_EDGE_CASE
**Pattern:** Writing token refresh code without a distributed Redis lock.
**Why dangerous:** Two workers refreshing the same expired token simultaneously
will call the platform's refresh API twice. The first response invalidates
the second. One worker's token becomes invalid mid-job (EC18).
**Pre-check:**
```bash
grep -n "refresh_token\|token_expiry" platform_adapters/*.py | grep -v "lock\|SET NX"
# Any refresh call without a preceding lock acquisition is EC18 waiting to happen
```

---

### W-7  [WATCH]  TEST_GAP
**Pattern:** Writing a Celery task without writing a unit test for its
failure path (not just its happy path).
**Why dangerous:** The failure path (DLQ routing, retry countdown, notification
creation) is where bugs live. Happy path tests give false confidence.
**Pre-check:** Before marking any task as "done", confirm tests exist for:
- The task with a PERMANENT error (must not retry)
- The task with a TRANSIENT error (must retry with correct countdown)
- The task with `shutting_down=True` (must re-queue, not fail)
