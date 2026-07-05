# Search Automation and Notifications

This document describes the design and usage of the automated search layer implemented in Sprint 4 (Task 13).

## Overview

The automation layer handles running job collection pipelines, matching candidate jobs against users, and recording notifications for top matches. It is designed to be triggered either manually via a REST endpoint or systematically via a scheduled script (e.g. a cron job).

## Components

- **Search Orchestration Service**: (`app/services/search_orchestration_service.py`) Orchestrates the entire flow. It fetches jobs from defined sources, inserts new unique jobs, scores them for all or specified users, and then generates notifications for the top matches above a threshold.
- **Notification Service**: (`app/services/notification_service.py`) and **Notification Table**: (`app/models/notification.py`). Records a notification row `(user_id, job_id, search_run_id, status)`. Currently, status is `SENT` or `SKIPPED` (if the user has no email). It guards against duplicates via database constraints (`IntegrityError`) and pre-checks, ensuring users never receive duplicate notifications for the same job.
- **Run Metadata**: Executions of the orchestration logic emit tracking metrics and save execution outcomes into the `LogTable` under the `search_run` stage.

## Manual Trigger (REST API)

You can trigger a search manually via the `POST /api/v1/search-runs` endpoint.

Example payload:
```json
{
  "user_ids": [12, 47],
  "sources": ["wuzzuf"],
  "notify": true
}
```

Other endpoints under `/api/v1/search_runs` allow you to inspect historical runs, check metadata (e.g., duplicates skipped, jobs inserted), and see which specific notifications were generated in a given run.

## Scheduled/Daily Automation

For periodic (e.g. daily) automation, a headless script `scripts/run_daily_search.py` is provided. It bypasses the HTTP layer and can be wired into a cron scheduler.

Usage examples:
```bash
python -m scripts.run_daily_search
python -m scripts.run_daily_search --sources fixture wuzzuf
python -m scripts.run_daily_search --user-id 12 --dry-run
```

## Testing and Edge Cases

Tests located in `tests/services/test_search_orchestration_service.py` cover:
- **Happy Path**: Successfully fetching, matching, and notifying.
- **Duplicate Prevention**: Running the search twice yields zero new notifications the second time.
- **Resilience**: Simulated ranking failures for one user do not halt the notification process for other valid users.
- **Edge Cases**: Users without emails skip the `SENT` process and are marked `SKIPPED`.
