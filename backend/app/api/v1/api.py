"""
API v1 router — aggregates all sub-routers under /api/v1.

Sub-routers define their own prefix and tags, so they are
included here without overrides.
"""

import structlog
from fastapi import APIRouter

from app.api.v1.cvs import router as cv_router
from app.api.v1.jobs import router as jobs_router
from app.api.v1.job_tracking import (
    router as job_tracking_router,
    trends_router as market_trends_router,
)
from app.api.v1.applications import router as applications_router
from app.api.v1.matches import router as matches_router
from app.api.v1.recommendations import router as recommendations_router
from app.api.v1.search_runs import router as search_runs_router
from app.api.v1.users import router as users_router
from app.api.v1.benchmarks import router as benchmarks_router
from app.api.v1.readiness import router as readiness_router
from app.api.v1.roadmaps import router as roadmaps_router

logger = structlog.get_logger()

api_router = APIRouter()

api_router.include_router(jobs_router, prefix="/jobs", tags=["Jobs"])
api_router.include_router(job_tracking_router, prefix="/tracking", tags=["Job Tracking"])
api_router.include_router(market_trends_router, prefix="/trends", tags=["Market Trends"])
api_router.include_router(cv_router, prefix="/cv", tags=["CV Parser"])
api_router.include_router(applications_router)
api_router.include_router(matches_router)
api_router.include_router(users_router)
api_router.include_router(recommendations_router, prefix="/recommendations", tags=["Recommendations"])
api_router.include_router(search_runs_router, prefix="/search-runs", tags=["Search Automation"])
api_router.include_router(benchmarks_router)
api_router.include_router(readiness_router)
api_router.include_router(roadmaps_router)

@api_router.get("/health")
def health_check() -> dict[str, str]:
    """Shallow liveness probe — returns 200 if the process is up."""
    logger.info("health_check_called")
    return {"status": "healthy", "version": "1.0.0"}