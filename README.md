# AI Career Coach

AI-powered career coaching and job-matching platform. A **FastAPI** backend (job
collection, CV parsing, AI match analysis, recommendations, market trends,
application-material generation) paired with a **Next.js 16** frontend.

```
ai-career-coach/
├── backend/    # FastAPI + SQLModel + PostgreSQL/pgvector + LangGraph/LiteLLM
└── frontend/   # Next.js 16 (App Router) + React 19 + Zustand + Recharts
```

The frontend talks to the backend exclusively through `frontend/src/lib/api/*`,
which target the backend's `/api/v1` surface. The base URL is configurable via
`NEXT_PUBLIC_API_URL` (defaults to `http://localhost:8000/api/v1`).

---

## Prerequisites

- **Docker + Docker Compose** (recommended — brings up PostgreSQL w/ pgvector, runs migrations, starts the API)
- or a local **PostgreSQL 16 + pgvector**, **Python 3.11+** with [uv](https://docs.astral.sh/uv/), and **Node.js 20+**
- A **LiteLLM** endpoint + API key for the AI features (CV parsing, match analysis, recommendations)

---

## 1. Backend

### Option A — Docker (recommended)

```bash
cd backend
cp .env.example .env            # fill in LITELLM_* and POSTGRES_* values
docker compose up --build       # starts Postgres + API, applies Alembic migrations
```

API is then live at **http://localhost:8000** — interactive docs at
`http://localhost:8000/docs`, health at `http://localhost:8000/api/v1/health`.

### Option B — Local (no Docker)

```bash
cd backend
cp .env.example .env            # point POSTGRES_* at your local Postgres
uv sync                         # install deps (Linux) — see note below
uv run alembic upgrade head     # apply migrations
uv run python -m app.main       # start dev server on :8000 (Windows-safe entrypoint)
# production: uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

> **Note:** `uv.lock` is resolved for `sys_platform == 'linux'`. On Windows/macOS,
> use Docker (Option A), or regenerate the lock for your platform with
> `uv lock` before `uv sync`.

### Backend tests

The suite requires a running PostgreSQL (a separate test DB is created automatically):

```bash
cd backend
make test          # or: uv run pytest        (unit + endpoint tests)
make test-int      # or: uv run pytest -m integration   (hits live LiteLLM)
```

---

## 2. Frontend

```bash
cd frontend
cp .env.example .env.local      # set NEXT_PUBLIC_API_URL if the API isn't on localhost:8000
npm install
npm run dev                     # http://localhost:3000
```

Production build:

```bash
npm run build && npm start
```

CORS for `http://localhost:3000` is already configured on the backend via
`CORS_ALLOWED_ORIGINS` in `backend/.env`.

---

## Frontend → Backend API map

| Frontend module (`frontend/src/lib/api`) | Backend route (`/api/v1`) |
|------------------------------------------|---------------------------|
| `users.ts` · `cvApi.upload`              | `POST /cv` |
| `users.ts` · `usersApi.getProfile`       | `GET /users/{id}` |
| `users.ts` · `usersApi.updatePreferences`| `PATCH /users/{id}/preferences` |
| `jobs.ts` · `jobsApi.list`               | `GET /jobs` |
| `tracking.ts` · `trackingApi.*`          | `GET/PUT /tracking`, `/tracking/jobs/{id}[/history,/application-materials]` |
| `trends.ts` · `trendsApi.*`              | `GET /trends`, `GET /trends/skills` |
| `recommendations.ts` · `recommendationsApi.get` | `GET /recommendations/{id}` |
| `recommendations.ts` · `matchesApi.analyze` | `POST /matches/analyze` |
| `applications.ts` · `applicationsApi.generate` | `POST /applications/` |

---

## License

See [backend/LICENSE](backend/LICENSE).
