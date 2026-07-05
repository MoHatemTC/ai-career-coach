from json import JSONDecodeError

from pydantic import ValidationError

from app.ai.registry import get_registry
from app.services.llm.cv_parser_state import CVParserState
from app.models.jobs import UserProfile
async def parse_cv(state:CVParserState):
    prompt = f"""
You are an expert CV parser.

Your task is to extract structured candidate profile data from the CV text.

Important:
The parsed output is only a suggested extraction and must be reviewed by a human before it is saved or treated as final.

Take care since you may find extra spaces between characters of a single word.
Therefore, be careful because you may encounter split words.

Return the data according to the provided schema.

Rules:
- Use only information explicitly found in the CV.
- Do not invent missing information.
- If a field is missing, return null.
- If a list has no items, return an empty list.
- Extract skills, completed_courses,projects and certifications as lists.
- For skills, extract the name of the skill.
- For completed_courses, extract the name of the course.
- For projects, extract the name of the project.
- For certifications, extract the name of the certification.
- For experience, preserve job title, company name. Ex: Junior Software Engineer, Google
- For education, preserve degree, field of study. Ex: bachelor computer science
- For the education degree you should use bachelor only.
- Calculate the years of experience (in years) rounded to the nearest year. If the user has no experience, set it to 0.
- All text must be in lower case
- If the user did not specify the career level return junior as default.
- the career level should be one of these "junior", "mid", "senior".
- Return preferred_location if the user wrote the city and his country. Ex: alexandria, egypt.

Do NOT infer intent or preferences from the CV. Career preferences (desired
roles, target job titles, remote/hybrid/on-site preference, job categories) are
collected separately from the user via the profile endpoint and must not be
guessed here.

CV Text:
{state['raw_text']}
"""

    try:
        parsed_response = await get_registry().acomplete(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert CV parser. "
                        "Return only valid JSON matching the required schema. "
                        "The output must be treated as a suggestion that requires human review."
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            response_format=UserProfile,
            temperature=0,
        )

        return {
            "parsed_cv": parsed_response
        }
    except (JSONDecodeError, ValidationError, ValueError) as e:
        return {'parsed_cv': {
            "message": "CV parsing failed because the model returned invalid structured data. Please try again or enter the profile manually.",
            "requires_human_review": True,
            "parse_status": "failed",
            "suggested_profile": None,
            "errors": [str(e)]
        }}

    except Exception as e:
        return{'parsed_cv':{
            "message": "CV parsing service is currently unavailable. Please try again later or enter the profile manually.",
            "requires_human_review": True,
            "parse_status": "failed",
            "suggested_profile": None,
            "errors": [str(e)]
        }}