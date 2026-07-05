# Career Coach

An AI-powered system that helps users build profiles, discover jobs, and get personalized career recommendations.

## Roadmap

### Week 1: Profile & CV
- CV upload flow
- Collect career preferences
- Generate structured user profile (JSON)

### Week 2: Job Collection Pipeline
- Connect to job sources
- Clean and normalize job data
- Remove duplicate jobs

### Week 3: AI Matching & Recommendations
- Match jobs with user profile
- Generate match scores + explanations
- Suggest missing skills

### Week 4: Application Support & Demo
- CV tailoring suggestions
- Cover letter draft (human-reviewed)
- Search Automation & Notifications (see [docs/features/search-automation-and-notifications.md](docs/features/search-automation-and-notifications.md))
- Final demo + GitHub preparation

## Setup

### Installing uv

uv is a fast Python package installer and resolver. Follow the instructions below based on your operating system:

**Windows (PowerShell):**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**macOS/Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

For more information and alternative installation methods, visit the [official uv documentation](https://docs.astral.sh/uv/getting-started/installation).

### Prerequisites

- [uv](https://docs.astral.sh/uv/) — Python dependency manager (see above)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) — runs the PostgreSQL + pgvector database
- `make` — optional, but every command below has a one-line `make` shortcut

### Installing Make

The project ships a `Makefile` that wraps every common task. `make` is
pre-installed on macOS and Linux. On Windows, install it with one of:

**Windows (Chocolatey):**
```powershell
choco install make
```

**Windows (Scoop):**
```powershell
scoop install make
```

**Windows (winget):**
```powershell
winget install ezwinports.make
```

> Don't want to install `make`? Every target is just a thin wrapper — you can
> run the underlying `uv` / `docker` commands directly (shown below each step).

### Project Setup

```bash
# Clone the repo
git clone https://github.com/atef199/career-coach.git
cd career-coach
```

Create your environment file from the template and fill in the values:

```bash
cp .env.example .env   # then edit .env with your Postgres credentials
```

**First-time setup** — installs dependencies, starts the database container,
and applies all migrations:

```bash
make setup
```

<details>
<summary>Without make</summary>

```bash
uv sync                       # install dependencies
docker compose up -d          # start PostgreSQL + pgvector
uv run alembic upgrade head   # create the schema
```
</details>

## Running the App

The schema is owned by **Alembic migrations** — the app no longer creates
tables at startup, so make sure the database is up and migrated (`make setup`,
or `make db-up && make migrate`) before launching.

**On Windows** — use the module entrypoint, not the `uvicorn` CLI:

```bash
make run
# or directly:
uv run python -m app.main
```

> **Why not `uvicorn app.main:app` on Windows?** The `uvicorn` CLI binds a
> `ProactorEventLoop` before `app.main` is imported, and the psycopg3 async
> driver can't run on it. Running the module lets `app/main.py` inject a
> `SelectorEventLoop` first. This only affects local Windows development.

**On macOS / Linux** — the `uvicorn` CLI is fine:

```bash
make run-uvicorn
# or directly:
uv run uvicorn app.main:app --reload --port 8000
```

The API is then available at <http://localhost:8000>, with interactive docs at
<http://localhost:8000/docs>.

## Running the Tests

The test suite needs the database container running; it creates and tears down
its own isolated test database per run.

```bash
make test
# or directly:
uv run pytest
```

The default run **excludes** integration tests — those that call a live LiteLLM
proxy. To run them, set the `TEST_LITELLM_*` values in `.env` (see
`.env.example`) and use:

```bash
make test-integration
# or directly:
uv run pytest -m integration
```

## Database & Migrations

| Task | Make | Direct command |
| --- | --- | --- |
| Start the database | `make db-up` | `docker compose up -d` |
| Stop the database | `make db-down` | `docker compose down` |
| Apply migrations | `make migrate` | `uv run alembic upgrade head` |
| Create a migration | `make migration name="add x"` | `uv run alembic revision --autogenerate -m "add x"` |
| Reset the database | `make db-reset` | `uv run python -m scripts.reset_db` |

After changing any model under `app/models/`, generate a migration with
`make migration name="..."`, review the generated file in `alembic/versions/`,
then apply it with `make migrate`.