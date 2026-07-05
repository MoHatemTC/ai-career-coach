# AI Career Coach: Matching Rubric

This document defines the strategy for matching a user's CV/Profile against job postings.

## Scoring Criteria & Derivation Rules (0 - 100 points)

The LLM will calculate the `match_score` based on the following weighted dimensions. Use these explicit point allocations to derive the final score:

### 1. Hard Skills Fit (Max 40 points)
- **Full Match (40 pts):** Candidate possesses all mandatory technical skills and core tools.
- **Partial Match (20-39 pts):** Missing 1-2 core skills, but possesses highly transferable skills (e.g., knows React, job asks for Vue).
- **Poor Match (0-19 pts):** Missing the majority of mandatory core technical skills.

### 2. Experience Level Fit (Max 30 points)
- **Full Match (30 pts):** Total years of relevant domain experience meets or exceeds the requirement.
- **Partial Match (15-29 pts):** Experience is slightly below the requirement (e.g., 2 years instead of 3), or experience is high but in an adjacent domain.
- **Poor Match (0-14 pts):** Experience is far below the requirement or completely irrelevant.

### 3. Soft Skills & Domain Knowledge (Max 20 points)
- **Full Match (20 pts):** Explicit evidence of required leadership, communication, or industry domain knowledge.
- **Partial Match (10-19 pts):** Implicit or vague evidence of soft skills.
- **Poor Match (0-9 pts):** No evidence of requested soft skills.

### 4. Career Preferences & Logistics (Max 10 points)
- **Full Match (10 pts):** Explicit alignment with job model (e.g., remote) and career trajectory.
- **Mismatch (0 pts):** Explicit conflict (e.g., candidate wants remote, job is strictly on-site).

**Final Score Calculation:**
`Total Match Score = (Hard Skills Points) + (Experience Points) + (Soft Skills Points) + (Preferences Points)`

## Missing Skills Identification
Any mandatory skill listed in the job description that is missing from the candidate's profile should be explicitly listed in the `missing_skills` array.

## Recommendations
The `recommendation` section should provide concrete, actionable steps. For example: "Take a course in Docker to cover the containerization requirement," or "Highlight your leadership experience more prominently."
