from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class CandidateProfile(BaseModel):
    """
    Schema for a candidate's profile, designed to be stored as JSONB.
    """
    name: str = Field(..., description="Full name of the candidate")
    contact: Dict[str, str] = Field(default_factory=dict, description="Contact information")
    skills: List[str] = Field(default_factory=list, description="List of technical and soft skills")
    tools: List[str] = Field(default_factory=list, description="Named technologies, frameworks, or platforms the candidate has hands-on experience with")
    experience_years: int = Field(0, description="Total years of experience")
    education: List[str] = Field(default_factory=list, description="Educational background")
    career_level: Optional[str] = Field(None, description="junior / mid / senior")
    certifications: List[str] = Field(default_factory=list, description="Professional certifications")
    projects: List[str] = Field(default_factory=list, description="Notable projects")
    completed_courses: List[str] = Field(default_factory=list, description="Completed courses")
    preferences: Dict[str, Any] = Field(default_factory=dict, description="Career preferences and logistics")

    @classmethod
    def from_user(cls, user: Any) -> "CandidateProfile":
        """Build a CandidateProfile from a UserTable row.

        Duck-typed (reads attributes, no import of the ORM model) to avoid an
        import cycle. Single source of truth for the (user -> profile) mapping,
        shared by the /applications endpoint and the SHORTLISTED background task.
        """
        return cls(
            name=user.name,
            contact={"email": user.email} if user.email else {},
            skills=user.skills,
            tools=user.tools,
            experience_years=user.years_of_experience,
            education=[user.education] if user.education else [],
            career_level=user.career_level,
            certifications=user.certifications,
            projects=user.projects,
            completed_courses=user.completed_courses,
            preferences=(
                {"preferred_location": user.preferred_location}
                if user.preferred_location
                else {}
            ),
        )

class MatchRequest(BaseModel):
    """
    Request payload to initiate a job match.
    """
    candidate_id: int = Field(..., description="Unique identifier of the candidate (User ID)")
    job_id: int = Field(..., description="Unique identifier of the target job")
    candidate_profile: CandidateProfile = Field(..., description="Parsed candidate profile")

class MatchScoreDetails(BaseModel):
    """
    Internal rubric scoring breakdown.
    """
    hard_skills_score: int = Field(..., ge=0, le=40, description="Hard Skills Fit (Max 40 points)")
    experience_score: int = Field(..., ge=0, le=30, description="Experience Level Fit (Max 30 points)")
    soft_skills_score: int = Field(..., ge=0, le=20, description="Soft Skills & Domain Knowledge (Max 20 points)")
    logistics_score: int = Field(..., ge=0, le=10, description="Career Preferences & Logistics (Max 10 points)")

class JobMatchResult(BaseModel):
    """
    The structured output expected from the LLM based on the scoring rubric.
    
    WARNING: This result is entirely AI-generated. It represents an initial algorithmic 
    analysis and drafting. Do not treat these scores or recommendations as definitive 
    decisions without human review.
    """
    score_details: MatchScoreDetails
    total_score: int = Field(..., ge=0, le=100, description="Sum of score details")
    explanation: str = Field(..., description="Detailed explanation of the derived score")
    strengths: List[str] = Field(default_factory=list, description="Key strengths and matching skills")
    missing_skills: List[str] = Field(default_factory=list, description="Required skills the candidate lacks (weaknesses)")
    recommendation: str = Field(..., description="Actionable advice for the candidate")

class JobMatchResponse(BaseModel):
    """
    The final response payload returned to the client.
    
    WARNING: Contains AI-generated scoring. A mandatory human-in-the-loop review 
    process must be completed before relying on these matches for hiring decisions.
    """
    job_id: int
    candidate_id: int
    result: JobMatchResult
    vector_distance: Optional[float] = Field(None, description="Pre-filtering vector distance score (e.g., L2)")
    status: str = Field(default="Draft - Awaiting Human Approval", description="Status of the generated content indicating it requires human review.")
    disclaimer: str = Field(default="AI-generated content. A human-in-the-loop review is required before use.", description="Responsible AI disclaimer regarding potential hallucinations.")
