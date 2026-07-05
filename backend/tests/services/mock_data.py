from app.schemas.matching import CandidateProfile

# Pre-defined integer IDs for predictable testing (DB primary keys are integers).
TARGET_JOB_ID = 1
CANDIDATE_ID = 2

# --- Mock Candidates for Different Scoring Scenarios ---

# 1. Perfect Match Candidate
# Meets all hard skills, experience, soft skills, and logistics.
PERFECT_CANDIDATE = CandidateProfile(
    name="Grace Hopper",
    contact={"email": "grace@example.com"},
    skills=["Python", "FastAPI", "PostgreSQL", "LLM Orchestration", "Leadership", "Communication"],
    experience_years=6,
    education=["MSc Computer Science"],
    preferences={"remote": True, "timezone": "EST"}
)

# 2. Partial Match Candidate
# Good experience, but missing some key hard skills (e.g., FastAPI, LLM).
PARTIAL_CANDIDATE = CandidateProfile(
    name="Ada Lovelace",
    contact={"email": "ada@example.com"},
    skills=["Python", "Django", "MySQL", "Communication"],
    experience_years=5,
    education=["BSc Computer Science"],
    preferences={"remote": True, "timezone": "PST"}
)

# 3. Poor Match Candidate
# Completely different domain, low experience, logistics mismatch.
POOR_CANDIDATE = CandidateProfile(
    name="Alan Turing",
    contact={"email": "alan@example.com"},
    skills=["Java", "Spring Boot", "Oracle"],
    experience_years=1,
    education=["Bootcamp Certificate"],
    preferences={"remote": False, "timezone": "GMT"}
)

# --- Mock Job Data ---
MOCK_JOB_DATA = {
    "job_id": TARGET_JOB_ID,
    "title": "Senior AI Backend Engineer",
    "description": (
        "We are looking for a Senior AI Backend Engineer to orchestrate LLM pipelines. "
        "Must have 5+ years of experience. Mandatory skills: Python, FastAPI, PostgreSQL, and LLM Orchestration. "
        "Requires strong leadership and communication skills. Must be open to 100% remote work."
    ),
    "embedding": [0.01] * 1536
}

# --- Mock Application AI Data ---
MOCK_CV_TAILORING_RESULT = {
    "tailored_summary": "Highly motivated Software Engineer with 5+ years of experience specializing in Python, FastAPI, and PostgreSQL. Proven track record in orchestrating LLM pipelines and leading cross-functional remote teams.",
    "highlighted_skills": [
        "Python",
        "FastAPI",
        "PostgreSQL",
        "LLM Orchestration",
        "Leadership",
        "Communication"
    ],
    "missing_skills": [],
    "bullet_point_suggestions": [
        "Rephrase 'Worked on backend services' to 'Designed and implemented scalable backend services using FastAPI and PostgreSQL.'",
        "Highlight specific metrics for LLM integration, e.g., 'Reduced latency in LLM orchestration pipeline by 20%.'"
    ]
}

MOCK_COVER_LETTER_RESULT = {
    "draft_content": "Dear Hiring Manager,\n\nI am writing to express my strong interest in the Senior AI Backend Engineer position at your company. With over 5 years of experience building robust backends using Python, FastAPI, and PostgreSQL, alongside my recent focus on LLM Orchestration, I am confident in my ability to immediately contribute to your engineering team.\n\nThroughout my career, I have consistently demonstrated strong leadership and communication skills, effectively collaborating in 100% remote environments. I am particularly drawn to your company's innovative work in AI and am eager to bring my technical expertise and problem-solving mindset to your team.\n\nThank you for your time and consideration. I look forward to discussing how my skills and experiences align with your needs.\n\nSincerely,\n[Your Name]",
    "tone_analysis": "Professional, confident, and enthusiastic, highlighting relevant technical skills and cultural fit for a remote environment."
}

MOCK_APPLICATION_RESPONSE = {
    "candidate_id": CANDIDATE_ID,
    "job_id": TARGET_JOB_ID,
    "cv_tailoring": MOCK_CV_TAILORING_RESULT,
    "cover_letter": MOCK_COVER_LETTER_RESULT,
    "status": "Draft - Awaiting Human Approval",
    "disclaimer": "AI-generated content. A human-in-the-loop review is required before use."
}
