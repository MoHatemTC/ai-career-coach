from pydantic import BaseModel, Field
from typing import List


class RoleBenchmark(BaseModel):
    must_have_skills: List[str] = Field(
        description=(
            "Strictly required conceptual or technical skills. "
            "Do not include specific tools or frameworks here."
        )
    )
    nice_to_have_skills: List[str] = Field(
        description="Optional or bonus skills mentioned as 'nice to have'."
    )
    required_tools: List[str] = Field(
        description=(
            "Specific software, frameworks, or platforms explicitly required "
            "(e.g., 'Python', 'FastAPI', 'Docker')."
        )
    )
    minimum_years: int = Field(
        ge=0,
        strict=True,
        description=(
            "The absolute minimum years of experience required. "
            "If stated as a range (e.g., 3-5), use the lowest number. "
            "If not specified, return 0."
        ),
    )
    seniority_level: str = Field(
        description=(
            "The seniority level implied or stated "
            "(e.g., 'Junior', 'Mid-Level', 'Senior', 'Staff'). "
            "Infer based on the text if not explicitly stated."
        )
    )
    common_responsibilities: List[str] = Field(
        description="A concise list of the day-to-day tasks."
    )
