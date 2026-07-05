# AI Job Matching & Recommendations

Matching runs against the **real** Postgres schema (`UserTable`, `JobTable`,
`JobMatchTable`) with `pgvector`. There are two surfaces:

1. **Recommendations** — discover and rank jobs for a user
   (`GET /api/v1/recommendations/{user_id}`).
2. **Single-pair analysis** — score/explain one `(user, job)` and persist it
   (`POST /api/v1/matches/analyze`), plus an ephemeral scorer (`POST /api/v1/matches/`).

Embeddings are local: **`BAAI/bge-base-en-v1.5`, 768-dim**, cosine similarity, model
+ dim pinned as constants in `app/core/embeddings.py` (see the embeddings note in
[`erd.md`](../erd.md)).

---

## Recommendations — hybrid retrieval

`recommend_jobs_for_user` (`app/services/job_recommendation_service.py`):

1. **Candidate text** — `build_candidate_text(user)` combines facts (skills, tools,
   career level, experience) with the user's preferences (desired roles, job titles,
   categories) and is embedded with the bge query prefix.
2. **Keyword pre-filter (GIN)** — restrict to jobs sharing ≥N of the user's skills
   via `required_skills @> [...]` (served by `idx_jobs_required_skills_gin`), plus the
   `experience_level` and (if set) `workplace_settings → work_mode` preference filter.
3. **Vector ranking (HNSW)** — order the pre-filtered set by
   `embedding <=> candidate` cosine distance (`idx_jobs_embedding_hnsw`).
4. **Blend + LLM re-rank** — take a small shortlist, blend semantic distance with
   keyword overlap, then re-rank the top few with the LLM matcher.

Preferences come from `PATCH /users/{id}/preferences` (not the CV). If unset,
retrieval gracefully falls back to skills/tools/career level.

---

## Single-pair analysis

### `POST /api/v1/matches/analyze` (persisted)
`MatchService.analyze(user_id, job_id)` loads the user + job, runs an LLM gap
analysis with structured output (`MatchAnalysis`), and **upserts** into
`job_matches` on `uq_job_matches_user_job`. Returns the stored row (`JobMatchOut`):

```json
{ "user_id": 1, "job_id": 42 }
```

### `POST /api/v1/matches/` (ephemeral)
A LangGraph two-stage scorer (`pre_filter_node` vector distance → `llm_evaluation_node`
rubric) that returns a `JobMatchResponse` without persisting. Takes a
`CandidateProfile` in the body; used for one-off scoring.

The rubric weights Hard Skills 40 / Experience 30 / Soft Skills 20 / Logistics 10
for a 0–100 score — defined inline in the `app/ai/prompts/job_matching.md` system
prompt (the authoritative source the LLM actually receives).

---

## Data types (real schema)

| Field | Type |
|---|---|
| `users.id`, `jobs.id`, `job_matches.id` | `INTEGER` (auto-increment PK) |
| list fields (`skills`, `required_skills`, …) | `JSONB` |
| `jobs.embedding` | `vector(768)` (nullable; populated at ingest + backfill) |

> Earlier drafts of this feature used an in-memory `MockDB` with `uuid` ids and
> 1536-dim embeddings. That mock layer is gone — matching now uses the real async
> Postgres schema.

---

## Structured output (`/matches/analyze` → `job_matches`)

`MatchAnalysis` maps 1:1 onto the table columns: `match_score` (0–100),
`match_explanation`, `missing_skills`, `cv_tailoring_suggestion`,
`cover_letter_draft`.

---

## Sample usage

```bash
# 1. Set preferences (drives recommendations)
curl -X PATCH "http://localhost:8000/api/v1/users/1/preferences" \
     -H "Content-Type: application/json" \
     -d '{"desired_roles":["ai engineer"],"workplace_settings":["remote"]}'

# 2. Get ranked recommendations
curl "http://localhost:8000/api/v1/recommendations/1"

# 3. Analyze one (user, job) pair and persist it
curl -X POST "http://localhost:8000/api/v1/matches/analyze" \
     -H "Content-Type: application/json" \
     -d '{"user_id":1,"job_id":42}'
```

---

## Guardrails & limitations

- **Advisory only / HITL** — scores are LLM-generated; every result carries a
  draft/disclaimer status and needs human review.
- **Observability** — the `matching` stage writes `started`/`success` (and `error`)
  rows to the `logs` table.
- **Bias & hallucination** — mitigated via the rubric prompt; human oversight
  recommended. Avoid logging raw CV text / full profiles — log ids + scores.
