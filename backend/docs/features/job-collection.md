# Job Collection Pipeline

## Overview

The job collection pipeline fetches job postings from one or more external
sources, validates and normalises them, removes duplicates, and stores the
results in PostgreSQL.  It is designed to be **source-agnostic** — new
providers can be added without modifying the pipeline core.

---

## Setup

### Prerequisites

- Python 3.11+
- Docker (for PostgreSQL + pgvector)
- [uv](https://docs.astral.sh/uv/) package manager

### 1. Start the database

```bash
docker compose up -d
```

This launches a `pgvector/pgvector:pg17` container with credentials from `.env`:

```env
POSTGRES_USER=DB_USER
POSTGRES_PASSWORD=DB_PASSWORD
POSTGRES_DB=DB_NAME
POSTGRES_HOST=DB_HOST
POSTGRES_PORT=DB_PORT
```

### 2. Install dependencies

```bash
uv sync
```

### 3. Start the API

```bash
make dev
# or directly:
uv run uvicorn app.main:app --reload --port 8000
```

The schema is managed by Alembic migrations. Before first run, apply them:

```bash
uv run alembic upgrade head
```

This enables the `pgvector` extension and creates all tables. The app does
**not** create tables at startup — run the migration whenever models change.

### 4. Seed the database with sample jobs

```bash
# Via the API (server must be running)
curl -X POST http://localhost:8000/api/v1/jobs/collect \
     -H "Content-Type: application/json" \
     -d '{"sources": ["fixture"]}'
```

Or open the Swagger docs at `http://localhost:8000/docs` and use the
interactive "Try it out" button on `POST /api/v1/jobs/collect`.

### 5. Verify

```bash
curl http://localhost:8000/api/v1/jobs | python -m json.tool
```

---

## Architecture

```
                      ┌──────────────┐
                      │  API Layer   │  POST /api/v1/jobs/collect
                      │  (jobs.py)   │  GET  /api/v1/jobs
                      └──────┬───────┘
                             │
                             ▼
                  ┌─────────────────────┐
                  │  Collection Service  │  Orchestrates the pipeline
                  │  (job_collection_   │  for one or many sources
                  │   service.py)       │
                  └──────┬──────────────┘
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
    ┌──────────────────┐  ┌──────────────────┐
    │  Job Source       │  │  Deduplication    │
    │  Adapter          │  │  Service          │
    │  (BaseJobSource)  │  │  (job_dedup_     │
    │                   │  │   service.py)    │
    └──────────────────┘  └──────────────────┘
              │
      ┌───────┴────────┐
      ▼                ▼
  FixtureSource   WuzzufSource
  (fixture.py)    (wuzzuf.py)
   [fallback]      [live source]
```

### Data flow

1. **Fetch** — The source adapter calls `.fetch()` and returns `list[JobPosting]`.
   Each adapter owns its own normalisation (field mapping, level mapping, skill
   extraction).  The pipeline never sees raw source data.

2. **Deduplicate** — The deduplication service uses a **two-tier key** (in
   priority order): the source's stable `(source, external_id)` when present,
   otherwise a `content_hash` SHA-256 fallback over `title | company | posted_date`.
   It batch-queries the database (one round-trip per tier) and filters out jobs
   that already exist. See [Deduplication strategy](#deduplication-strategy).

3. **Insert, link skills, embed** — New jobs are converted via
   `JobPosting.to_job_table()` and added to the `jobs` table. After a flush (to
   assign primary keys) the pipeline links each job to canonical skill rows
   (`job_skills`) and generates a 768-dim semantic embedding
   (`BAAI/bge-base-en-v1.5`) so vector search works immediately — no NULL-embedding
   rows are left behind. All of this runs inside a per-source SAVEPOINT (see
   trade-off #7).

4. **Respond** — The pipeline returns a `CollectionResult` (or
   `BatchCollectionResult` for multi-source runs) with counts for fetched,
   inserted, duplicates, and errors.

---

## File map

| File | Purpose |
|---|---|
| `app/services/job_sources/base.py` | `BaseJobSource` abstract class — the contract for all sources |
| `app/services/job_sources/fixture.py` | `FixtureSource` — reads from `data/sample_jobs.json` |
| `app/services/job_sources/wuzzuf.py` | `WuzzufSource` — live async scraper for Wuzzuf's internal APIs |
| `app/services/job_deduplication_service.py` | Content-hash deduplication against the DB |
| `app/services/job_collection_service.py` | Pipeline orchestrator + source registry |
| `app/schemas/jobs.py` | Pydantic request/response schemas for the API |
| `app/api/v1/jobs.py` | FastAPI route handlers |
| `alembic/versions/` | Schema migrations (run `alembic upgrade head`) |
| `data/sample_jobs.json` | Fallback fixture dataset (119 real Wuzzuf jobs) |
| `tests/services/test_job_collection_service.py` | Test suite |

---

## API endpoints

### `POST /api/v1/jobs/collect`

Trigger the pipeline for one or more sources.

**Request body:**
```json
{
  "sources": ["fixture"]
}
```

**Response:**
```json
{
  "results": [
    {
      "source": "fixture",
      "fetched": 10,
      "inserted": 10,
      "duplicates": 0,
      "errors": 0
    }
  ],
  "total_inserted": 10,
  "total_duplicates": 0,
  "total_errors": 0
}
```

### `GET /api/v1/jobs`

List stored jobs.  Supports optional query parameters:

| Param | Type | Description |
|---|---|---|
| `source` | string | Filter by source name (`wuzzuf`, `bayt`, etc.) |
| `experience_level` | string | Filter by `junior`, `mid`, or `senior` |
| `limit` | int | Max results (default 50, max 200) |
| `offset` | int | Pagination offset (default 0) |

**Response:**
```json
{
  "jobs": [
    {
      "id": 1,
      "title": "AI Engineer",
      "company": "Breadfast",
      "location": "Cairo, Egypt",
      "description": "...",
      "required_skills": ["Python", "LangChain"],
      "experience_level": "mid",
      "source": "wuzzuf",
      "posted_date": "2025-06-01",
      "url": "https://wuzzuf.net/..."
    }
  ],
  "total": 10
}
```

### `GET /api/v1/jobs/sources`

List registered source adapters.

**Response:**
```json
{
  "sources": ["fixture"]
}
```

---

## Technical trade-offs

### 1. Normalisation inside each adapter vs. a separate normalisation service

**Choice:** Each `BaseJobSource` subclass owns its own normalisation.
`fetch()` returns `list[JobPosting]`, not raw dicts.

**Why:** Different sources have wildly different data shapes (Wuzzuf's
payload merged across three internal API endpoints vs. the fixture JSON
that already matches the schema). A single normaliser would need a growing
`if source == "wuzzuf": ... elif source == "bayt": ...`
chain — violating the Open/Closed Principle.  Keeping normalisation
co-located with the source means adding a new provider never touches
existing code.

**Trade-off:** The pipeline cannot inspect or log raw source data because
it only ever sees validated `JobPosting` objects. If a source returns
garbage, the adapter silently filters it via `_normalize() → None`.
Debugging ingestion issues requires looking at the adapter's own logs.

### 2. Async pipeline

**Choice:** `BaseJobSource.fetch()`, `deduplicate()`, and
`collect_from_source()` are all `async`. The `/api/v1/jobs` routes and the
DB layer (`AsyncSession` over the psycopg3 async driver) are async too.

**Why:** `WuzzufSource` does real network I/O — it fans out across Wuzzuf's
three internal API endpoints with `httpx.AsyncClient` + `asyncio.gather`,
so async lets those requests run concurrently instead of blocking. Sources
doing only local work (e.g. `FixtureSource`) simply `return` without
awaiting, so they pay no penalty for sharing the async contract.

**Trade-off:** Async raises the baseline cost — tests need
`pytest-asyncio`, callers need `await`, and on Windows the selector
event-loop policy must be set at import time because psycopg3's async
driver cannot run on the default ProactorEventLoop. This complexity is
justified the moment a network-bound source like Wuzzuf exists.

### 3. Two-tier dedup key: `(source, external_id)` then `content_hash`

**Choice:** The primary dedup key is the source's stable per-posting id,
`(source, external_id)` (e.g. the Wuzzuf UUID). Only when a source has no stable
id (the fixture) does the pipeline fall back to a `content_hash` =
`SHA-256(title | company | posted_date)`, all components normalized (lowercased,
whitespace-collapsed). When the company is hidden — every source normalizes a
hidden/missing employer to the `Confidential` sentinel — the company is dropped
from the hash and the unique job `url` is used instead. A row carries **either**
an `external_id` **or** a `content_hash`, never both: `to_job_table()` leaves
`content_hash` NULL whenever an `external_id` is present.

**Why the two tiers:** `external_id` is immune to cosmetic edits — a re-scraped
posting whose title or company changed is still recognized as the same job. The
hash fallback exists only for sources that expose no stable id. For that hash,
`title | company | posted_date` is the minimal set that identifies a listing:
including `description` would cause false negatives on wording differences across
boards; excluding `posted_date` would collide a role re-posted months later.

**Why the confidential fallback:** A hidden company carries no identifying
signal. If `Confidential` were left in the hash, two genuinely different
hidden-company roles with the same title and date would collide and the second
would be silently dropped (data loss). Falling back to the per-posting `url`
keeps distinct postings distinct while still deduping the same posting on
re-scrape.

**Trade-off:** The hash tier can still collide two genuinely different roles at
the same *named* company with identical titles and dates — rare for AI/data roles
in the MENA market, and only reachable by sources lacking an `external_id`. Adding
`location` to the hash input would reduce it further if needed.

### 4. Service-level dedup + DB-level UNIQUE constraint (defence in depth)

**Choice:** Duplicates are filtered by the deduplication service *and*
enforced at the DB by a `UNIQUE` constraint on each tier — `(source, external_id)`
and `content_hash`.

**Why:** The service-level check avoids wasting a DB round-trip for known
duplicates. The DB constraint catches any race conditions or bugs in the
service layer. Neither layer alone is sufficient — the service check is
an optimisation, the constraint is the safety net.

**Single source of truth:** The hash recipe lives in one place —
`JobPosting.compute_content_hash()`. Both the dedup service and
`to_job_table()` (which writes `content_hash` to the DB) call it, so the
service-level check and the stored value can never drift apart. Guarded by
`test_hash_matches_to_job_table_hash`.

### 5. Source registry (dict) vs. auto-discovery

**Choice:** Sources are registered manually in a `SOURCE_REGISTRY` dict
inside `job_collection_service.py`.

**Why:** Explicit is better than implicit. A developer can glance at the
dict and see every available source. Auto-discovery (e.g., scanning for
`BaseJobSource` subclasses) is fragile, makes import order matter, and
makes it easy to accidentally register a half-built adapter.

**Trade-off:** Adding a source requires editing two files (the adapter
module + the registry dict). This is intentional — it forces the developer
to make a conscious decision about when a source is ready for production.

### 6. Fixture fallback alongside the live Wuzzuf source

**Choice:** Two sources are registered: `WuzzufSource` (live scraper) and
`FixtureSource`, which reads a static JSON file of 119 real Wuzzuf postings.

**Why:** Wuzzuf is the real ingestion path, but live scraping can fail
(network, rate limits, markup changes) — which would be fatal during a
demo. The fixture provides a deterministic fallback so the full pipeline
(collection → dedup → storage → API → tests) always runs end-to-end without
external dependencies. The fixture data is a real Wuzzuf snapshot, so it
exercises the same normalisation paths as the live source.

**Trade-off:** The fixture data is static and will gradually go stale, and
it does not exercise live edge cases like rate-limiting, network timeouts,
or markup changes. Those are covered by `WuzzufSource`'s own tests, and the
snapshot can be regenerated as needed.

### 7. Per-source SAVEPOINTs + a single batch commit

**Choice:** Each source is processed inside its own SAVEPOINT
(`session.begin_nested()`), and `collect_from_sources()` issues a single
`session.commit()` after all sources have run.

**Why:** The nested transaction isolates each source's writes — its inserts,
skill links, and embeddings. If a later source fails at flush (e.g. a
`content_hash` UNIQUE violation), only that source's SAVEPOINT rolls back;
sources processed earlier keep their rows and their reported counts stay honest.
The single outer commit then persists exactly the sources that succeeded. This
is the data-loss fix for the old "one failure rolls back the whole batch"
behavior, guarded by `test_later_source_failure_preserves_earlier_rows`.

**Audit survives rollback:** the `job_ingest` log row for a failed source is
written to the *outer* transaction (after its SAVEPOINT is gone), so the audit
trail records the failure even though the job rows did not persist.

**Trade-off:** Partial success is now possible by design — a batch can commit
some sources while others rolled back. Callers must read the per-source
`CollectionResult` counts rather than assuming all-or-nothing. If the final outer
commit itself fails, everything is rolled back and the error is re-raised.

---

## Adding a new job source

1. **Create the adapter** in `app/services/job_sources/`:

```python
# app/services/job_sources/wuzzuf.py

from app.models import JobPosting
from app.services.job_sources.base import BaseJobSource

class WuzzufSource(BaseJobSource):
    source_name = "wuzzuf"

    async def fetch(self) -> list[JobPosting]:
        raw_jobs = await self._call_api()
        return [j for raw in raw_jobs if (j := self._normalize(raw))]

    def _normalize(self, raw: dict) -> JobPosting | None:
        # Map API fields → JobPosting schema
        ...

    async def _call_api(self) -> list[dict]:
        # Hit the Wuzzuf API (async httpx)
        ...
```

2. **Register it** in `app/services/job_collection_service.py`:

```python
from app.services.job_sources.wuzzuf import WuzzufSource

SOURCE_REGISTRY: dict[str, type[BaseJobSource]] = {
    "fixture":  FixtureSource,
    "wuzzuf":   WuzzufSource,   # ← add this line
}
```

3. **Add any config** (API keys, base URLs) to the settings package under
   `app/core/config/` (e.g. `settings.py`) and `.env`.

4. **Write tests** in `tests/services/test_job_collection_service.py`.

That's it — the pipeline, API, and deduplication will work automatically.

---

## Deduplication strategy

Dedup uses a **two-tier key** (priority order): the source's stable
`(source, external_id)` when present, else a `content_hash` fallback. Duplicates
are caught at two levels:

1. **Service level** — `deduplicate()` first collapses duplicates *within* the
   incoming batch, then splits jobs by tier and issues one query per tier:
   `(source, external_id)` pairs for id-bearing sources, and
   `SHA-256(title | company | posted_date)` hashes for the rest. Both components
   are normalized (lowercased, whitespace-collapsed); a hidden company falls back
   to the posting `url`.

2. **Database level** — `JobTable` carries a `UNIQUE` constraint on each tier
   (`(source, external_id)` and `content_hash`), so even if the service-level
   check misses a race condition, PostgreSQL rejects the insert. The hash recipe
   lives only in `JobPosting.compute_content_hash()`, so the service check and the
   stored value can never drift.

---

## Fallback dataset

`data/sample_jobs.json` contains 119 real job postings scraped from Wuzzuf.

This dataset is used:
- As a **demo-stability fallback** via `FixtureSource` when live scraping is unavailable
- As **seed data** for first-run bootstrapping
- In **tests** to verify the full pipeline end-to-end

---

## Running tests

```bash
# Ensure PostgreSQL is running
docker compose up -d

# Run the collection pipeline tests
uv run pytest tests/services/test_job_collection_service.py -v

# Run all tests
uv run pytest -v
```
