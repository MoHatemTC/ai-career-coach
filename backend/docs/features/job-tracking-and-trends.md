# Job Tracking & Market Trend Analysis

> Sprint 3 · Task 9

Two related capabilities built on top of the Sprint 2 data layer:

1. **Job Tracking** — a per-user pipeline that records where each job sits in a
   user's personal funnel, backed by a current-state table and an append-only
   audit log.
2. **Market Trend Analysis** — read-only aggregate intelligence computed
   directly over the `jobs` table the Wuzzuf scraper populates.

---

## Part 1 — Job Tracking

### The six states

Every `(user, job)` pair occupies exactly one state at a time:

| State | Meaning |
|---|---|
| `reviewed` | The user opened the job — the **default entry state**. |
| `saved` | Bookmarked for later. |
| `shortlisted` | Seriously considering applying. |
| `applied` | Application submitted. |
| `rejected` | Rejected by the company, or dropped by the user. |
| `ignored` | The user dismissed the job as irrelevant. |

These are defined once as `TrackingStatus` in
[`app/models/job_tracking.py`](../../app/models/job_tracking.py) and reused by the
schema, service, and API layers.

### State machine

The pipeline is **permissive and user-driven**: any state may transition to any
other state. A user can re-save a job, move it back from `shortlisted` to
`saved`, un-ignore it, and so on — there is no fixed DAG, because real users move
jobs around their funnel non-linearly.

The single invariant is **idempotency**: receiving the *same* status the pair
already holds is a no-op (see below).

```
              (first contact)
   ┌──────────────────────────────────┐
   │                                   ▼
 (none) ──▶ reviewed ⇄ saved ⇄ shortlisted ⇄ applied ⇄ rejected
                  └────────────▶ ignored ◀────────────┘
   (any state may move to any other state; same → same is ignored)
```

### Two tables

| Table | Role |
|---|---|
| `job_tracking` | **Current state.** One row per `(user_id, job_id)` — enforced by `UniqueConstraint("user_id", "job_id")`. `status` is overwritten in place on each transition. |
| `job_tracking_events` | **Append-only audit log.** One row per *real* transition, recording `from_status` (NULL on first contact) → `to_status` and a `created_at` timestamp. Rows are never updated or deleted. |

Why two tables? The current-state table answers "where is this job now?" in a
single indexed lookup, while the event log answers "how did it get there?"
without bloating the hot table. This mirrors the existing split between
`job_matches` (current result, UNIQUE per pair) and `logs` (immutable event
trail).

### Duplicate-transition handling

Handled at the **service layer** in
[`job_tracking_service.track_job`](../../app/services/job_tracking_service.py):

- **No existing row** → create the tracking row and write one event with
  `from_status = NULL`.
- **Existing row, same status** → **silently ignored**: the row is returned
  unchanged and **no event is written**. No error is raised.
- **Existing row, different status** → update `status` + `updated_at` and append
  one event `from_status → to_status`.

So sending `saved` twice in a row produces exactly **one** tracking row and
**one** event. But `saved → shortlisted → saved` is three genuine transitions
and produces three events — the no-op rule only applies to identical
consecutive states.

### API endpoints

All under `/api/v1/tracking`. This app has no auth layer yet (consistent with
the existing job endpoints), so the acting user is supplied explicitly.

#### `PUT /api/v1/tracking/jobs/{job_id}`

Record or transition a job's status. Idempotent.

**Body:**
```json
{ "user_id": 1, "status": "saved" }
```
`status` defaults to `"reviewed"` if omitted.

**Response `200`:**
```json
{
  "id": 12,
  "user_id": 1,
  "job_id": 7,
  "status": "saved",
  "created_at": "2026-06-25T17:00:00Z",
  "updated_at": "2026-06-25T17:05:00Z"
}
```
**`404`** if `job_id` does not exist.

#### `GET /api/v1/tracking/jobs/{job_id}?user_id=1`

Current tracking state for the pair. **`404`** if the pair is not tracked.

#### `GET /api/v1/tracking?user_id=1&status=saved`

List a user's tracked jobs (newest-updated first). `status` is an optional
filter.

```json
{ "items": [ /* JobTrackingOut */ ], "total": 3 }
```

#### `GET /api/v1/tracking/jobs/{job_id}/history?user_id=1`

The append-only transition history for the pair, oldest first. **`404`** if the
pair is not tracked.

```json
{
  "job_id": 7,
  "user_id": 1,
  "events": [
    { "id": 1, "user_id": 1, "job_id": 7, "from_status": null, "to_status": "reviewed", "created_at": "..." },
    { "id": 2, "user_id": 1, "job_id": 7, "from_status": "reviewed", "to_status": "applied", "created_at": "..." }
  ]
}
```

---

## Part 2 — Market Trend Analysis

Read-only aggregations over the `jobs` table, exposed under `/api/v1/trends`.
Each metric is a **single focused query** in
[`app/services/market_trend_service.py`](../../app/services/market_trend_service.py).

| Endpoint | Metric | How it's computed |
|---|---|---|
| `GET /trends/companies?limit=10` | Top hiring companies | `GROUP BY company` |
| `GET /trends/experience-levels` | Junior / mid / senior split | `GROUP BY experience_level` |
| `GET /trends/work-types` | Remote / hybrid / on-site | `GROUP BY work_mode` |
| `GET /trends/categories?limit=10` | Top job categories | Unnest `work_roles`, `GROUP BY` |
| `GET /trends/countries` | Postings per MENA country | `GROUP BY country_code` |
| `GET /trends/job-types` | Full-time / part-time / ... | Unnest `job_types`, `GROUP BY` |
| `GET /trends/posting-volume` | Posting volume over time | `GROUP BY date_trunc('month', posted_date)` |
| `GET /trends/skills?limit=20` | Top skills in demand | Join `job_skills` → `skills`, `GROUP BY` |
| `GET /trends/salaries` | Salary min/avg/max per currency | `GROUP BY salary_currency, salary_period` |
| `GET /trends` | Combined overview | All metrics in one response |

Most metrics return `[{ "label": "...", "count": N }, ...]` (posting volume uses
`period`; salaries return the `SalaryStatOut` shape).

> **Schema note.** Earlier this feature reconstructed `work_mode`, `category`,
> and skills at query time (a `CASE` over `location`/`description`, a 13-branch
> `CASE` over `title`, and a 60-char length filter over the `required_skills`
> JSONB array). The Wuzzuf ingestion pipeline now captures these as real
> structured columns (`work_mode`, `work_roles`, `country_code`, `job_types`,
> the salary block) and canonicalizes skills into the normalized `skills` /
> `job_skills` tables, so every metric is now a plain `GROUP BY` / join — no
> heuristics. See [`docs/erd.md`](../erd.md).

### Skills aggregation

Skills are canonicalized at ingestion (lowercased, synonym-mapped, with Arabic
requirement *sentences* dropped — see
[`app/services/skills/canonicalizer.py`](../../app/services/skills/canonicalizer.py))
and stored in the normalized `skills` / `job_skills` tables. `jobs.required_skills`
remains as a denormalized lowercase cache for the matching engine. `top_skills`
joins the link table so counts are clean and synonym-free:

```sql
SELECT s.name AS label, COUNT(*) AS count
FROM job_skills js
JOIN skills s ON s.id = js.skill_id
GROUP BY s.name
ORDER BY count DESC, label ASC
LIMIT :limit;
```

### Salary aggregation

`salary_stats` groups by **`(salary_currency, salary_period)`** and reports
`count`, `min`, `max`, and `avg` over postings with a visible salary
(`salary_hidden = false`). Currency and period are part of the grouping key
because values across them are not comparable — Wuzzuf quotes salaries in EGP,
USD, SAR, QAR, and AED regardless of the job's country (a UAE job may pay EGP),
and periods mix `Per Month` and `Per Hour`. No FX normalization is applied; raw
values are reported as collected.

---

## File map

| File | Purpose |
|---|---|
| [`app/models/job_tracking.py`](../../app/models/job_tracking.py) | `JobTrackingTable`, `JobTrackingEventTable`, `TrackingStatus` enum |
| [`app/schemas/job_tracking.py`](../../app/schemas/job_tracking.py) | Pydantic v2 request/response schemas |
| [`app/services/job_tracking_service.py`](../../app/services/job_tracking_service.py) | State machine + audit log |
| [`app/services/market_trend_service.py`](../../app/services/market_trend_service.py) | Market-trend aggregation queries |
| [`app/services/skills/`](../../app/services/skills/) | Skill canonicalizer + alias map + link repository |
| [`app/api/v1/job_tracking.py`](../../app/api/v1/job_tracking.py) | `/tracking` and `/trends` routers |
| [`tests/services/test_job_tracking_service.py`](../../tests/services/test_job_tracking_service.py) | Test suite |
| `alembic/versions/b9f20459bfce_*.py` | Migration for the two new tables |

---

## Running the migration

The two tables ship as Alembic migration `b9f20459bfce` (down-revision
`360fbe5a45e2`). Apply it with:

```bash
docker compose up -d          # PostgreSQL must be running
uv run alembic upgrade head    # or: make migrate
```

The migration creates `job_tracking` and `job_tracking_events`, their indexes,
the `(user_id, job_id)` unique constraint, and a native `trackingstatus` enum.
`alembic downgrade -1` drops all of them (including the enum type), so the
upgrade/downgrade round-trip is repeatable.

## Running the tests

```bash
docker compose up -d
uv run pytest tests/services/test_job_tracking_service.py -v
# or the whole suite:
uv run pytest -q
```

The tests use the shared async `async_session` fixture (a real PostgreSQL test
database, per the repo's documented testing convention) so they exercise the
real UNIQUE constraint and the append-only event table. Coverage includes: state
transitions, silent duplicate handling, 404 behaviour (unknown job / untracked
pair), the full `reviewed → saved → shortlisted → applied → rejected` lifecycle,
and the market-trend aggregations over the structured columns and the normalized
skills tables.
