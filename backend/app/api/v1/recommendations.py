from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession
from app.db.connection import get_session
from app.services.job_recommendation_service import recommend_jobs_for_user
from app.schemas.recommendations import RecommendationResponse
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/{user_id}", response_model=RecommendationResponse, status_code=status.HTTP_200_OK)
async def get_recommendations(user_id: int, session: AsyncSession = Depends(get_session)):
    """
    Returns a ranked list of recommended jobs for a specific user, powered by the AI matching engine.
    """
    try:
        ranked_jobs = await recommend_jobs_for_user(user_id, session)
        return RecommendationResponse(
            user_id=user_id,
            recommendations=ranked_jobs
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as e:
        logger.error(f"Failed to fetch recommendations for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while computing recommendations: {str(e)}"
        )
