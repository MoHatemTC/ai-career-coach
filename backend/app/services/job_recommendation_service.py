import logging
from typing import List, Dict, Any
# pyrefly: ignore [missing-import]
from sqlmodel import select
from sqlalchemy import cast, Integer, or_
from sqlmodel.ext.asyncio.session import AsyncSession
from app.models.jobs import UserTable, JobTable
from app.schemas.matching import MatchRequest, CandidateProfile, JobMatchResponse
from app.services.job_matching_service import JobMatchingService
from app.ai.registry import get_registry
from app.core.embeddings import build_candidate_text

logger = logging.getLogger(__name__)

# Candidates pulled from the vector/keyword pre-filter before LLM re-ranking.
_SHORTLIST_SIZE = 15
_LLM_EVAL_SIZE = 10

async def recommend_jobs_for_user(user_id: int, session: AsyncSession) -> List[dict]:
    """
    Core pipeline that discovers and ranks jobs for a candidate.
    
    1. Loads the user profile.
    2. Builds a soft-filtered shortlist of candidate jobs from the DB.
    3. Sorts candidates by semantic vector distance (pgvector pre-filter).
    4. Evaluates the top 10 candidates using the LLM matching engine.
    5. Returns ranked matches.
    """
    
    # Step 1: Load user profile
    user = await session.get(UserTable, user_id)
    if not user:
        raise ValueError(f"User with ID {user_id} not found.")

    # Convert UserTable to CandidateProfile schema for the matching engine
    candidate_profile = CandidateProfile(
        name=user.name,
        contact={"email": user.email} if user.email else {},
        skills=user.skills,
        tools=user.tools,
        experience_years=user.years_of_experience,
        education=[user.education] if user.education else [],
        preferences={"preferred_location": user.preferred_location} if user.preferred_location else {}
    )

    # Step 2 & 3: Hybrid retrieval — GIN keyword pre-filter + HNSW vector ranking.
    candidate_summary = build_candidate_text(user)
    registry = get_registry()
    try:
        vectors = await registry.aembed([candidate_summary])
        candidate_embedding = vectors[0]
    except Exception as e:
        logger.error(f"Failed to embed candidate summary for vector search: {e}")
        candidate_embedding = [0.0] * registry.embedding_dim

    skills = user.skills or []
    # Require at least N of the user's skills to appear in the job's
    # required_skills (JSONB @> containment, served by idx_jobs_required_skills_gin)
    # BEFORE the HNSW vector scan runs, so the ANN search only touches keyword-
    # relevant jobs. N relaxes to 1 for candidates with a single skill.
    min_overlap = 2 if len(skills) >= 2 else 1

    stmt = select(
        JobTable,
        JobTable.embedding.cosine_distance(candidate_embedding).label("distance"),
    ).where(JobTable.embedding.is_not(None))

    if user.career_level:
        stmt = stmt.where(JobTable.experience_level == user.career_level)

    # Preference filter: honor the user's work-mode preference when set, but keep
    # jobs whose work_mode is unknown (NULL) so we don't over-prune. Empty
    # preference = no filter (graceful degradation).
    if user.workplace_settings:
        stmt = stmt.where(
            or_(
                JobTable.work_mode.in_(user.workplace_settings),
                JobTable.work_mode.is_(None),
            )
        )

    if skills:
        overlap = sum(
            cast(JobTable.required_skills.contains([skill]), Integer) for skill in skills
        )
        stmt = stmt.where(overlap >= min_overlap)

    # HNSW-ordered semantic shortlist among the keyword-pre-filtered jobs.
    stmt = stmt.order_by("distance").limit(_SHORTLIST_SIZE)

    results = await session.exec(stmt)
    shortlist = results.all()  # list of (JobTable, float)

    if not shortlist:
        return []

    # Blended re-rank: semantic similarity (1 - cosine distance) + keyword overlap,
    # then take the top slice to hand to the (more expensive) LLM matcher.
    skill_set = {s.lower() for s in skills}

    def _keyword_overlap(job: JobTable) -> int:
        return len(skill_set & {s.lower() for s in (job.required_skills or [])})

    max_overlap = max((_keyword_overlap(j) for j, _ in shortlist), default=0) or 1
    shortlist.sort(
        key=lambda pair: (1.0 - float(pair[1])) * 0.7
        + (_keyword_overlap(pair[0]) / max_overlap) * 0.3,
        reverse=True,
    )
    shortlist = shortlist[:_LLM_EVAL_SIZE]

    # Step 4: Run LLM matcher on the shortlist
    matching_service = JobMatchingService(session=session)
    evaluated_jobs = []

    for job, distance in shortlist:
        match_request = MatchRequest(
            candidate_id=user.id,
            job_id=job.id,
            candidate_profile=candidate_profile
        )
        try:
            match_response = await matching_service.execute_match(match_request)
            
            evaluated_jobs.append({
                "job": {
                    "id": job.id,
                    "title": job.title,
                    "company": job.company,
                    "location": job.location,
                    "url": job.url
                },
                "total_score": match_response.result.total_score,
                "explanation": match_response.result.explanation,
                "strengths": match_response.result.strengths,
                "missing_skills": match_response.result.missing_skills,
                "vector_distance": distance
            })
        except Exception as e:
            logger.error(f"Failed to run matching for job {job.id}: {e}")

    # Step 5: Rank results by LLM score descending
    evaluated_jobs.sort(key=lambda x: x["total_score"], reverse=True)

    return evaluated_jobs
