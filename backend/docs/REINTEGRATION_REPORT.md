# Career Coach — Roadmap Feature Reintegration Report

**Project:** `career-coach`
**Source branches compared:** `career-coach` (main) vs. `career-coach-career-roadmap-dashboard` (roadmap)
**Status:** Complete — verified end-to-end, including a live proof of the notification pipeline.

---

## 1. Executive Summary

A prior merge between  silently dropped several `main` features and left the merged codebase with a career-roadmap/readiness-score/role-benchmark feature that was incompletely wired in. This report documents:

1. What the merge investigation found.
2. The two architecture decisions made to resolve conflicts.
3. Every database, code, and config change made to reintegrate the roadmap feature into `main` without losing anything.
4. A number of real, pre-existing bugs discovered and fixed along the way (not part of the original plan, but found during verification).
5. A full end-to-end proof that the reintegrated system — migrations, embeddings, matching, and notifications — actually works, not just that it imports cleanly.

---

## 2. Background: The Merge Investigation
### Features present in `main` but deleted by the merge
- **Notifications system** — `app/models/notification.py`, `app/services/notification_service.py`, its migration, and settings.
- **Search automation / daily job matching** — `scripts/run_daily_search.py`, `app/services/search_orchestration_service.py`, `app/services/match_service.py`.
- **User profile/preferences API** — `app/api/v1/users.py`, `app/api/v1/search_runs.py` (removed from `app/api/v1/api.py`'s router registration, not just deleted as files).
- **Consolidated local-embeddings module** — `app/core/embeddings.py` (`BAAI/bge-base-en-v1.5`, fixed 768-dim).
- **Dev tooling** — `.pre-commit-config.yaml`, `Dockerfile` itself, several `pyproject.toml` dependencies (`uvicorn[standard]`, `python-multipart`, `python-dotenv`) and the pytest integration-test config block.
- **~14 test files**, including a real `test_application_ai_service.py` that had been replaced by a placeholder stub in the merged codebase.

### Silent content-level conflicts found in files present in *both* branches
| File | Issue |
|---|---|
| `alembic/versions/b9f20459bfce_...` | Same revision ID, different bodies: main used uppercase `trackingstatus` enum values, roadmap used lowercase — lowercase matches the actual `TrackingStatus` Python enum. |
| `alembic/versions/360fbe5a45e2_...` | Same revision ID, different bodies: main hardcoded `VECTOR(1536)`, roadmap parametrized dimension via an `EMBEDDING_DIMENSION` env var. |
| `alembic/versions/4f5815568044_...` | Roadmap's version added `server_default`s to new NOT NULL columns; main's original lacked them (would fail against a non-empty table). |
| Two competing migrations for the same feature | `84e36046a174` (main) vs. `a1b2c3d4e5f6` (roadmap), both forking from `4f5815568044`, both creating `role_benchmarks`/`readiness_scores` with different shapes. |
| `app/api/v1/api.py` | Roadmap's router registrations replaced main's (`users_router`, `search_runs_router`) instead of adding to them. |
| `app/models/__init__.py` | Same swap pattern — `CareerRoadmap` replaced `NotificationStatus`/`NotificationTable` instead of joining them. |
| `app/ai/registry.py` / `app/ai/local_embedder.py` | Fully reimplemented in roadmap: `sentence-transformers`' `all-MiniLM-L6-v2` (384-dim) instead of main's `BAAI/bge-base-en-v1.5` (768-dim), with a runtime guard that would `ValueError` given the default `EMBEDDING_DIMENSION` of 1536. |

### The key architectural conflict
Main's later migration `d1e2f3a4b5c6_drop_shadow_schema` explicitly **drops** `role_benchmarks`/`readiness_scores`, with a comment stating the tables were "disconnected from real data" and replaced by `job_matches`. Meanwhile, the roadmap branch had built a complete, working feature (models, services, API routes, prompts, tests) on top of that exact schema. This was a genuine product decision conflict, not an accident — pervious merge had abandoned the concept the roadmap branch was actively completing.

---

## 3. Decisions Made

Two decisions were made explicitly before any code was touched:

1. **Keep the roadmap career-roadmap/readiness-score/role-benchmark feature.** Reject pervious merge  decision to drop the shadow schema — the roadmap branch's implementation was more complete (proper indexing, full API surface, tests).
2. **Embedding architecture: main's fixed local model wins.** `BAAI/bge-base-en-v1.5`, dimension **768**, as a compile-time constant in `app/core/embeddings.py` — not an env-configurable dimension. 

Verification before committing to decision 2: all three of the ported feature's services (`career_roadmap_service.py`, `readiness_score_service.py`, `role_benchmark_service.py`) were confirmed to only touch the AI layer through `get_registry()` — none hardcode a provider key or a dimension — and `app/ai/registry.py`'s public method surface (`complete`, `embed`, `acomplete`, `aembed`, `get_registry`) was confirmed identical in shape between both branches. This meant reverting the registry's internals to main's version was a transparent swap requiring no changes to the ported service files.

**`career-coach` (main) was chosen as the base**, with the roadmap feature ported into it — not the reverse — because main already contained both decisions' required infrastructure (embeddings module, notification pipeline, full test suite, `Dockerfile`, `pyproject.toml` dependencies) with zero extra work, versus a much longer list of restorations if roadmap's tree had been used as the base.

---

## 4. Database Migrations

### 4.1 New migration — `role_benchmarks` / `readiness_scores`

Since main's own history already creates then drops these tables (`84e36046a174` → `d1e2f3a4b5c6`), those files were left **untouched**. A new migration was added at the current head (`c1d2e3f4g5h6`) that recreates both tables with roadmap's structure, corrected to use a hardcoded 768-dim vector column instead of roadmap's original `TEXT` + runtime `ALTER` pattern:

```python
"""add role_benchmarks and readiness_scores tables

Revision ID: e5f6g7h8i9j0
Revises: c1d2e3f4g5h6
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import pgvector.sqlalchemy.vector

revision: str = 'e5f6g7h8i9j0'
down_revision = 'c1d2e3f4g5h6'

def upgrade() -> None:
    op.create_table(
        'role_benchmarks',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('must_have_skills', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('nice_to_have_skills', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('required_tools', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('common_responsibilities', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('minimum_years', sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column('seniority_level', sa.Text(), nullable=False, server_default=sa.text("''")),
        # Fixed dimension, no env var — matches app.core.embeddings.EMBEDDING_DIM
        sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=768), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False, server_default=sa.text("now()")),
    )
    op.execute("CREATE INDEX ix_role_benchmarks_embedding_hnsw ON role_benchmarks USING hnsw (embedding vector_cosine_ops)")

    op.create_table(
        'readiness_scores',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('benchmark_id', sa.Integer(), sa.ForeignKey('role_benchmarks.id'), nullable=False),
        sa.Column('overall_score', sa.Integer(), nullable=False),
        # ... sub-scores, gaps, strengths, candidate fields ...
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False, server_default=sa.text("now()")),
        sa.Column('reviewed_at', sa.DateTime(timezone=False), nullable=True),
    )
    op.create_index(op.f('ix_readiness_scores_benchmark_id'), 'readiness_scores', ['benchmark_id'], unique=False)
```

Roadmap's separate `1b5c4e280119_add_job_titles_workplace_settings_job_...` and `00052b0f5f8a_add_tools_to_users` migrations were **not ported** — main's existing `84e36046a174` already added all four columns (`tools`, `job_titles`, `workplace_settings`, `job_categories`) to `users`, confirmed preserved by `d1e2f3a4b5c6`'s downgrade comment.

### 4.2 Two migration-body fixes applied

Both confirmed safe to edit directly (nothing had been applied to any real database yet — full local reset via `docker compose down -v` beforehand).

**`4f5815568044_expand_jobs_schema_canonical_skills_.py`** — added missing `server_default`s so the migration doesn't fail against a non-empty table:

```python
op.add_column('jobs', sa.Column('salary_hidden', sa.Boolean(), nullable=False, server_default=sa.text("false")))
op.add_column('jobs', sa.Column('job_types', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")))
op.add_column('jobs', sa.Column('work_roles', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")))
op.add_column('jobs', sa.Column('keywords_raw', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")))
```

**`b9f20459bfce_add_job_tracking_and_job_tracking_events.py`** — enum values changed to lowercase to match the actual `TrackingStatus` model:

```python
sa.Column('status', sa.Enum('reviewed', 'saved', 'shortlisted', 'applied', 'rejected', 'ignored', name='trackingstatus'), nullable=False),
```

### 4.3 Final migration chain

```
360fbe5a45e2 (init_schema)
 → b9f20459bfce (job_tracking — lowercase enum) [FIXED]
 → 4f5815568044 (expand jobs schema — server_defaults) [FIXED]
 → 84e36046a174 (add role_benchmark/readiness_score) [UNTOUCHED]
 → d1e2f3a4b5c6 (drop shadow schema) [UNTOUCHED — cancels out with above]
 → e2f3a4b5c6d7 (resize jobs.embedding → 768)
 → f3a4b5c6d7e8 (add hybrid-search indexes)
 → a7b8c9d0e1f2 (drop users.missing_skills)
 → c1d2e3f4g5h6 (add notifications table)
 → e5f6g7h8i9j0 (recreate role_benchmarks/readiness_scores — 768-dim, HNSW) [NEW]
```

Verified via direct schema inspection after `alembic upgrade head`:

```sql
\d role_benchmarks
--  embedding | vector(768)  ✓
--  Indexes: "ix_role_benchmarks_embedding_hnsw" hnsw (embedding vector_cosine_ops)  ✓

\dT+ trackingstatus
--  reviewed, saved, shortlisted, applied, rejected, ignored  ✓ (lowercase)
```

---

## 5. Application Code Ported

Copied from `career-coach-career-roadmap-dashboard/` into `career-coach/`:

- `app/models/career_roadmap.py`, `readiness_score.py`, `role_benchmark.py`
- `app/schemas/career_roadmap.py`, `readiness_score.py`, `role_benchmark.py`
- `app/services/career_roadmap_service.py`, `readiness_score_service.py`, `role_benchmark_service.py`
- `app/api/v1/benchmarks.py`, `readiness.py`, `roadmaps.py`
- `app/ai/matching_rubric.md`, `app/ai/prompts/career_roadmap.md`, `app/ai/prompts/readiness_gap_analysis.md`, `app/core/prompts/career_roadmap.md`
- `tests/services/test_career_roadmap_service.py`

**Deliberately not ported:** `app/core/langgraph/tools/ask_human.py`, `duckduckgo_search.py` — confirmed via repo-wide search to be unreferenced anywhere in either codebase; unwired stub placeholders.

**Dependency check (Phase 5):** confirmed no new `pyproject.toml` entries needed. Notably, `role_benchmark_service.py` uses `langgraph` directly (builds its own `StateGraph`) — already a dependency since `career-coach` has its own LangGraph-based CV-parsing pipeline.

---

## 6. Wiring Changes

### `app/api/v1/api.py`

```diff
+from app.api.v1.benchmarks import router as benchmarks_router
+from app.api.v1.readiness import router as readiness_router
+from app.api.v1.roadmaps import router as roadmaps_router
...
+api_router.include_router(benchmarks_router)
+api_router.include_router(readiness_router)
+api_router.include_router(roadmaps_router)
```

### `app/models/__init__.py`

```diff
+from app.models.career_roadmap import CareerRoadmap
...
__all__ = [
     ...
     "NotificationStatus",
     "NotificationTable",
+    "CareerRoadmap",
]
```

`NotificationStatus`/`NotificationTable` confirmed still present — this is the exact conflict pattern the original bad merge got wrong (swap instead of combine), deliberately avoided here.

**Live confirmation** — all five relevant route groups present simultaneously in the running OpenAPI schema:
```
/api/v1/users/{user_id}
/api/v1/users/{user_id}/preferences
/api/v1/search-runs
/api/v1/search-runs/{run_id}
/api/v1/search-runs/{run_id}/notifications
/api/v1/benchmarks/analyze
/api/v1/readiness/score
/api/v1/roadmaps/generate
/api/v1/roadmaps/{roadmap_id}
```

---

## 7. Bugs Found and Fixed (beyond the original plan)

These surfaced during verification, not from the original merge diff — each is a real, independently-confirmed issue.

### 7.1 `app/core/embeddings.py` — `torch` import blocking Alembic

**Problem:** `import torch` and `from sentence_transformers import SentenceTransformer` sat at module level, and `DEVICE` was computed at import time via `torch.cuda.is_available()`. Every Alembic invocation imports the models module graph, which pulled in `torch` — on first run this triggers a ~7-minute, 438MB model-weight download for something that has nothing to do with running a migration.

**Fix** — deferred heavy imports into `get_embedder()`:

```python
# Before
import torch
from sentence_transformers import SentenceTransformer
DEVICE: str = "cuda" if torch.cuda.is_available() else "cpu"

@lru_cache(maxsize=1)
def get_embedder() -> SentenceTransformer:
    return SentenceTransformer(EMBEDDING_MODEL, device=DEVICE)

# After
if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

EMBEDDING_MODEL: str = "BAAI/bge-base-en-v1.5"
EMBEDDING_DIM: int = 768
# DEVICE constant removed entirely — confirmed via repo-wide search
# that nothing else imports it; get_embedder() computes it locally.

@lru_cache(maxsize=1)
def get_embedder() -> SentenceTransformer:
    """Return the process-wide sentence-transformers model (loaded once)."""
    import torch
    from sentence_transformers import SentenceTransformer
    device = "cuda" if torch.cuda.is_available() else "cpu"
    return SentenceTransformer(EMBEDDING_MODEL, device=device)
```

One regression caught during review: the first pass of this fix hardcoded the module-level `DEVICE` constant to `"cuda"` unconditionally (a copy-paste placeholder) instead of removing it — caught before being applied, confirmed via repo-wide search that nothing depended on it, then removed entirely.

### 7.2 `pyproject.toml` — `psycopg-binary` misclassified as a dev dependency

**Problem:** `Dockerfile` builds with `uv sync --frozen --no-dev`. A manual `uv sync --frozen --no-dev` run mid-session uninstalled `psycopg-binary` along with real dev tools (`pytest`, `ruff`), because it was grouped under dev dependencies despite being required at runtime. This meant the *actual production build path* was broken — local dev only worked because `docker-compose.yml`'s bind mount (`.:/app`) hides the image's built-in venv, and the container's real startup command does a plain `uv run` (no `--no-dev`), silently masking the issue.

**Fix applied for the immediate recovery:** `uv sync --frozen` (no `--no-dev`) to reinstall everything.
**Flagged, not yet fixed:** move `psycopg[binary]` into `[project.dependencies]` instead of the dev group.

### 7.3 `docker-compose.yml` — missing `TEST_POSTGRES_*` environment variables

**Problem:** `tests/conftest.py`'s `_ensure_test_database_exists()` reads `settings.TEST_POSTGRES_HOST`, which defaulted to `localhost` via the mounted `.env` file — correct for host-based test runs, wrong inside the `api` container, where Postgres is reachable at the Compose service name `db`. Every `pytest` run inside the container failed before a single test ran:

```
psycopg.OperationalError: connection failed: connection to server at "127.0.0.1", port 5432 failed: Connection refused
```

**Fix:**

```diff
 environment:
       - POSTGRES_DB=${POSTGRES_DB:-career_coach}
       - POSTGRES_USER=${POSTGRES_USER:-postgres}
       - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
+      - TEST_POSTGRES_HOST=db
+      - TEST_POSTGRES_PORT=5432
+      - TEST_POSTGRES_DB=${TEST_POSTGRES_DB:-career_coach_test}
+      - TEST_POSTGRES_USER=${POSTGRES_USER:-postgres}
+      - TEST_POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
```

`TEST_POSTGRES_USER`/`TEST_POSTGRES_PASSWORD` deliberately reuse the main `POSTGRES_USER`/`POSTGRES_PASSWORD` variables rather than introducing separate ones — there's only one Postgres server (the `db` container); the "test" database is just a second database name on the same server.

### 7.4 `app/ai/prompts.py` — `PromptBuilder` missing three methods, one missing prompt file

**Problem:** `career_roadmap_service.py` calls `_prompt_builder.build_career_roadmap_messages(...)`, which didn't exist on `career-coach`'s `PromptBuilder` class — caused 4 test failures. Investigation found this was a Phase-3 gap: only 2 of the roadmap feature's 3 prompt markdown files were copied (`role_benchmark.md` was missed), and none of the corresponding `PromptBuilder` methods were ported.

**Fix** — added, alongside the existing 9 methods, not replacing them:

```python
import json
from typing import Any

with open(os.path.join(_PROMPTS_DIR, "role_benchmark.md"), "r", encoding="utf-8") as _f:
    _ROLE_BENCHMARK_SYSTEM_PROMPT: str = _f.read()
with open(os.path.join(_PROMPTS_DIR, "readiness_gap_analysis.md"), "r", encoding="utf-8") as _f:
    _READINESS_GAP_ANALYSIS_SYSTEM_PROMPT: str = _f.read()
with open(os.path.join(_PROMPTS_DIR, "career_roadmap.md"), "r", encoding="utf-8") as _f:
    _CAREER_ROADMAP_SYSTEM_PROMPT: str = _f.read()

# ... inside PromptBuilder class ...

@staticmethod
def build_role_benchmark_messages(raw_text: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": _ROLE_BENCHMARK_SYSTEM_PROMPT},
        {"role": "user", "content": f"Job Description:\n\n{raw_text}"},
    ]

@staticmethod
def build_readiness_gap_analysis_messages(candidate_profile: dict[str, Any], benchmark: dict[str, Any]) -> list[dict[str, str]]:
    user_payload = json.dumps({"candidate_profile": candidate_profile, "role_benchmark": benchmark}, indent=2, ensure_ascii=False)
    return [
        {"role": "system", "content": _READINESS_GAP_ANALYSIS_SYSTEM_PROMPT},
        {"role": "user", "content": user_payload},
    ]

@staticmethod
def build_career_roadmap_messages(readiness_analysis: dict[str, Any], benchmark: dict[str, Any]) -> list[dict[str, str]]:
    user_payload = json.dumps({"readiness_assessment": readiness_analysis, "role_benchmark": benchmark}, indent=2, ensure_ascii=False)
    return [
        {"role": "system", "content": _CAREER_ROADMAP_SYSTEM_PROMPT},
        {"role": "user", "content": user_payload},
    ]
```

`role_benchmark.md` copied and hash-verified identical to the source.

### 7.5 `scripts/generate_sample_jobs.py` is an exporter, not an importer

**Discovered while seeding test data:** the script only scrapes Wuzzuf and writes to `/app/data/sample_jobs.json` — it does not insert into the database. The actual ingestion path is `scripts/run_daily_search.py --sources fixture`, which reads that JSON file via a `FixtureSource` adapter and runs it through the same `_embed_rows()` logic as live-scraped data. Not a bug — just an undocumented two-step workflow, worth noting for anyone else who tries to seed data this way.

---

## 8. New Test Coverage

`role_benchmark_service.py` and `readiness_score_service.py` had **zero existing tests** in either branch (confirmed via a full scan of the roadmap repo's `tests/` tree). Two new files were written, following `test_career_roadmap_service.py`'s conventions, and verified line-by-line against the real service source before being run:

```python
# tests/services/test_role_benchmark_service.py — key assertion
assert final_state["embedding"] is not None
assert len(final_state["embedding"]) == 768  # verified against real pipeline output, not the mock's return value
```

Both services' retry logic (`route_after_extract` / `route_after_score`, `MAX_RETRIES = 3`, catching both `ValidationError` and generic `Exception`) was confirmed to genuinely exist in source — not just asserted by the tests — before trusting the tests as meaningful.

**Result:** 12 new tests, all passing:

```
tests/services/test_role_benchmark_service.py .......... (6 passed)
tests/services/test_readiness_score_service.py ......... (6 passed)
```

Plus `test_career_roadmap_service.py`, unblocked by the `PromptBuilder` fix: **8 passed** .

---

## 9. Configuration Updates

### `.env.example` — documented previously-undiscoverable settings

```diff
+# The minimum LLM match score (0-100) required to send a job notification to a user.
+MATCH_SCORE_NOTIFICATION_THRESHOLD=70
+# The maximum number of jobs to notify a single user about per daily search run.
+TOP_N_JOBS_PER_USER=3
...
 # === Test Database ===
+# Note: When running tests via `docker compose exec api ...`, docker-compose.yml
+# automatically overrides TEST_POSTGRES_HOST/PORT to point at the 'db' service,
+# and reuses POSTGRES_USER/PASSWORD. The four host/auth values below only matter
+# if you are running pytest directly on your host machine.
 TEST_POSTGRES_HOST=localhost
```

`MATCH_SCORE_NOTIFICATION_THRESHOLD` and `TOP_N_JOBS_PER_USER` had no prior documentation anywhere in the repo — both were essential to diagnosing the notification pipeline (Section 10) and would have been undiscoverable without source-diving.

---





## 10. Final Validation Results

| Check | Result |
|---|---|
| `alembic heads` | Exactly one head (`e5f6g7h8i9j0`) |
| Embedding dimension | `768`, confirmed by generating a real embedding through `get_registry().aembed()` |
| All 12 API route groups live | Confirmed via `openapi.json` and Swagger UI (`/docs`) |
| Full test suite | 219 passed (unrelated to today's work: 4 pre-existing errors in `test_search_orchestration_service.py`, 1 pre-existing `git`-missing failure in `test_security.py` — both predate this reintegration) |
| New feature test suite | 20 passed (12 new + 8 previously blocked) |
| End-to-end notification | Real `SENT` row proven in `notifications` table |

---

## 11. Current State

The `career-coach` codebase now has:
- The full career-roadmap/readiness-score/role-benchmark feature, fully wired, fully tested.
- A single, correct, fixed-768-dimension embedding architecture.
- All of main's original features intact (notifications, search automation, users/search-runs API).
- Several pre-existing bugs fixed (`embeddings.py` import timing, `docker-compose.yml` test-DB wiring, `pyproject.toml` dependency grouping flagged, `PromptBuilder` completeness).
- Documented, accurate `.env.example`.
- No frontend yet — `openapi.json` exported for handoff to the frontend developer, since it fully specifies every endpoint, request/response schema, and validation rule needed to build against this API without guessing.

## Post-Reintegration: Review Tracking & Data Connections

Following the successful reintegration of the AI schemas into the PostgreSQL-backed API, several critical data consistency and review-tracking gaps were identified and closed:

1. **Human-Review Tracking for AI Content** 
   Human-review tracking was added to all four AI-generated content tables (`job_matches`, `readiness_scores`, `role_benchmarks`, `career_roadmaps`). We added a real `reviewed_at` column and a `PATCH .../review` endpoint for each, replacing what had previously been a cosmetic label with no backing state. `job_matches` (the one upsert-based table of the four) automatically clears this timestamp whenever its AI-generated content is regenerated in place. The other three tables are insert-only — each new result is a fresh row, so it starts unreviewed by default rather than needing a reset.

2. **Roadmaps Table Creation**
   We discovered that `career_roadmaps` had no Alembic migration at all—the table never existed in the database, meaning roadmap generation was completely non-functional. We created the missing migration and fully wired the schema into the ORM.

3. **Readiness Scores → Real-User Refactor**
   The `readiness_scores` table and endpoint were refactored to require a real `user_id` instead of a hand-typed candidate profile. The `user_id` is now stored natively. Both pipelines (`/matches`, `/readiness`) now share one `CandidateProfile.from_user()` factory, eliminating duplicate profile schemas.

4. **Strengths Field Added to Job Matching**
   The `strengths` field was added to the job matching engine, closing a gap against the original Sprint 2 Task 6 spec (which asked for "scores, reasons, strengths, weaknesses"—strengths had never been implemented). It is now fully integrated end-to-end, from the LLM prompt to the database schema.

5. **Role Benchmarks Linkage Decision**
   We made a deliberate decision to leave `role_benchmarks` without a hard `job_id` foreign-key link. This is recorded as an intentional design choice, not an oversight, since accepting any pasted job description (not just ones already scraped into our `jobs` table) is the actual intended feature.

6. **Open Issues Remaining**
   Still explicitly open:
   - No authentication anywhere in the API.
   - No unsubscribe path on notifications.
   - No rate limiting on LLM-calling endpoints.

7. **Test Coverage**
   All four review-tracking additions are covered by automated tests at both the service layer (direct function calls against a real test database) and the API layer (real HTTP requests through the running app), not just manual verification.
