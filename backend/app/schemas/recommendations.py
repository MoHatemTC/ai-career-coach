from pydantic import BaseModel
from typing import List, Optional

class JobDetails(BaseModel):
    id: int
    title: str
    company: str
    location: str
    url: Optional[str] = None

class RecommendationItem(BaseModel):
    job: JobDetails
    total_score: int
    explanation: str
    strengths: List[str]
    missing_skills: List[str]
    vector_distance: float

class RecommendationResponse(BaseModel):
    user_id: int
    recommendations: List[RecommendationItem]
