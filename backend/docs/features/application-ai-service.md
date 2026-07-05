# Application AI Service

The Application AI Service generates **CV-tailoring suggestions** and a **cover-letter
draft** for a candidate against a specific job. Materials are only useful *before*
a user applies, so they are produced when a job first enters **SHORTLISTED** (or on
demand), persisted to `job_matches`, and read back via the tracking API.

---

## Architecture

Orchestrated with **LangGraph** as a two-LLM-stage pipeline:

```
START → [job_resolution_node] → [cv_tailoring_node] → [cover_letter_node] → END
              ↓ (error)               ↓ (error)
              END                     END
```

- **`job_resolution_node`** — uses the `job_description` passed in the request
  (callers pass `job.description` directly). Falls back to `session.get(JobTable, job_id)`
  if a description isn't supplied.
- **`cv_tailoring_node`** — builds the prompt via `PromptBuilder.build_cv_tailoring_messages`
  (`cv_tailoring.md`) and returns a structured `CVTailoringResult`.
- **`cover_letter_node`** — consumes the CV result + job description
  (`PromptBuilder.build_cover_letter_messages`, `cover_letter.md`) → `CoverLetterResult`.

> There is **no** content-moderation or PII-scrubbing node — job descriptions are
> scraped from trusted sources, and the profile is the user's own data. Both nodes
> use the shared `LLMServiceRegistry.acomplete(..., response_format=...)` pattern.

### Observability
- **Langfuse**: nodes are decorated with `@observe()` (no-op unless Langfuse keys are set).
- **Prometheus**: `application_ai_requests_total{status}` and
  `llm_call_duration_seconds{stage}` for `cv_tailoring` / `cover_letter`.
- **Audit log**: the `cover_letter` stage writes `started` / `success` rows (and an
  `error` row on failure) to the `logs` table.

---

## How materials get generated

There are two entry points; both load the profile from the DB and persist the
result to `job_matches` via the shared `upsert_job_match` helper (so a real
`match_score` is never clobbered).

### 1. Automatic — on entry to SHORTLISTED
`PUT /api/v1/tracking/jobs/{job_id}` transitioning **into** `shortlisted`
schedules generation as a FastAPI **BackgroundTask** *after* the response is sent
(`generate_application_materials_task`). It:
- runs only on the **first** entry into SHORTLISTED, and is idempotent (skips if
  materials already exist for the pair),
- opens its own DB session,
- is fire-and-forget — the client polls the read endpoint (below) for the result.

### 2. Manual / regenerate — `POST /api/v1/applications/`
Runs the pipeline synchronously for a real `(user_id, job_id)` and returns the
materials directly. Body:

```json
{ "user_id": 1, "job_id": 42 }
```

The candidate profile is built from `UserTable` server-side
(`CandidateProfile.from_user`) — the caller does **not** send a profile.

Response (`ApplicationResponse`):

```json
{
  "candidate_id": 1,
  "job_id": 42,
  "cv_tailoring": {
    "tailored_summary": "...",
    "highlighted_skills": ["Python", "FastAPI"],
    "missing_skills": ["Kubernetes"],
    "bullet_point_suggestions": ["..."]
  },
  "cover_letter": { "draft_content": "Dear Hiring Manager, ...", "tone_analysis": "..." },
  "status": "Draft - Awaiting Human Approval",
  "disclaimer": "AI-generated content. A human-in-the-loop review is required before use."
}
```

### Reading the materials
`GET /api/v1/tracking/jobs/{job_id}/application-materials?user_id=…` returns the
persisted `cv_tailoring_suggestion` / `cover_letter_draft`.

---

## Error handling (`POST /applications/`)

| Status | Condition |
|---|---|
| `200 OK` | Pipeline completed; materials persisted |
| `404 Not Found` | `user_id` or `job_id` does not exist |
| `422 Unprocessable Entity` | Pipeline `ValueError` (e.g. LLM returned invalid structured data) |
| `500 Internal Server Error` | Unexpected pipeline failure |

Failures also write an `error` row (with `metadata.stage="cover_letter"`) to `logs`.

---

## Responsible AI

- **No hallucination** — the prompts forbid inventing skills/experience the
  candidate doesn't have.
- **Missing skills are segregated** into `missing_skills` so they're never claimed
  in the CV/cover letter.
- **Bias-free tone** enforced in the cover-letter prompt.
- **Human-in-the-loop** — every output is marked a draft awaiting human approval
  (`status` + `disclaimer`).

---

## Roadmap

Generation currently uses FastAPI `BackgroundTasks` (in-process, best-effort — lost
on restart). Planned: a **Celery + Redis** broker for durable, retryable async
tasks (materials generation, job ingestion + embedding, backfills).

---

## Testing

`tests/services/test_application_ai_service.py` covers the service (2-call pipeline,
job resolution from DB, LLM-failure paths, empty-skills). `tests/services/test_applications_endpoint.py`
covers `POST /applications` (persist + read-back, 404s).

```bash
uv run pytest tests/services/test_application_ai_service.py tests/services/test_applications_endpoint.py -v
```
