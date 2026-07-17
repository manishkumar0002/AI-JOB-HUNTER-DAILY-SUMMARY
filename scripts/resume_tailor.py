"""
AI Resume Tailoring Engine
Analyzes a job description against the user's parsed resume
and generates specific, actionable suggestions to improve ATS score.
Uses local Ollama (gemma2:2b) — no internet required.
"""
import re
import json
import requests
from scripts.logger import log_info, log_error
from scripts.database import get_db_session, Job, ResumeVersion

OLLAMA_HOST = "http://ollama:11434"
OLLAMA_MODEL = "gemma2:2b"


def _call_ollama(prompt: str) -> str:
    """Sends a prompt to local Ollama and returns the response text."""
    try:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=90,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except Exception as e:
        log_error(f"Ollama call failed in resume tailor: {e}", "ResumeTailor")
        return ""


def _clean_json(text: str) -> dict:
    """Extract and parse JSON from Ollama response."""
    try:
        # Find JSON block
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            return json.loads(match.group())
    except Exception:
        pass
    return {}


def generate_tailoring_suggestions(job_id: int) -> dict:
    """
    Main entry point. Given a job ID, fetches the job description
    and latest resume, then uses Ollama to generate tailoring suggestions.

    Returns a dict with:
    - current_ats_score
    - potential_ats_score
    - missing_keywords: list of keywords to add
    - skills_to_highlight: list of skills to bring forward
    - suggested_summary: a suggested resume summary line
    - project_suggestions: what to mention in projects section
    - quick_wins: list of easy changes with high impact
    """
    db = next(get_db_session())
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return {"error": "Job not found"}

        resume = db.query(ResumeVersion).order_by(ResumeVersion.id.desc()).first()
        if not resume:
            return {"error": "No resume found. Please upload your resume first."}

        job_desc = (job.description or "")[:3000]
        resume_skills = resume.parsed_skills or ""
        resume_experience = resume.parsed_experience or ""
        resume_projects = resume.parsed_projects or ""
        resume_education = resume.parsed_education or ""
        resume_keywords = resume.parsed_keywords or ""
        current_ats = job.ats_score or 0

        log_info(f"Generating tailoring suggestions for Job {job_id}: '{job.title}' at '{job.company_name}'", "ResumeTailor")

        prompt = f"""You are an expert ATS resume optimizer. Analyze this job description vs the candidate's resume and give VERY SPECIFIC tailoring suggestions.

JOB TITLE: {job.title}
COMPANY: {job.company_name}

JOB DESCRIPTION:
{job_desc}

CANDIDATE'S CURRENT RESUME DATA:
Skills: {resume_skills}
Experience: {resume_experience}
Projects: {resume_projects}
Education: {resume_education}
Keywords: {resume_keywords}

Current ATS Score: {current_ats}%

Analyze carefully and return ONLY valid JSON (no extra text) in this exact format:
{{
  "potential_ats_score": <estimated score after tailoring, integer 0-100>,
  "missing_keywords": ["keyword1", "keyword2", "keyword3"],
  "skills_to_add": ["skill1", "skill2"],
  "skills_to_highlight": ["skill from resume to bring forward"],
  "suggested_summary": "Write a 2-sentence professional summary tailored to this job",
  "project_suggestions": "Specific advice on what to mention in projects section for this job",
  "quick_wins": [
    "Quick win 1: specific action",
    "Quick win 2: specific action",
    "Quick win 3: specific action"
  ],
  "cover_letter_hint": "One key point to mention in cover letter/email"
}}

Be specific. Use actual keywords from the job description. Only suggest realistic changes."""

        raw_response = _call_ollama(prompt)
        suggestions = _clean_json(raw_response)

        if not suggestions:
            # Fallback: basic keyword analysis without Ollama
            suggestions = _basic_keyword_analysis(job_desc, resume_skills, resume_keywords, current_ats)

        suggestions["current_ats_score"] = current_ats
        suggestions["job_title"] = job.title
        suggestions["company_name"] = job.company_name
        suggestions["job_id"] = job_id

        log_info(f"Tailoring suggestions generated. Potential ATS: {suggestions.get('potential_ats_score', '?')}%", "ResumeTailor")
        return suggestions

    except Exception as e:
        log_error(f"Resume tailoring failed for job {job_id}: {e}", "ResumeTailor")
        return {"error": str(e)}
    finally:
        db.close()


def _basic_keyword_analysis(job_desc: str, resume_skills: str, resume_keywords: str, current_ats: int) -> dict:
    """
    Fallback: simple keyword gap analysis without Ollama.
    Extracts tech keywords from job description and compares with resume.
    """
    TECH_KEYWORDS = [
        "java", "spring boot", "spring", "microservices", "kafka", "rest api",
        "restful", "sql", "mysql", "postgresql", "mongodb", "redis", "docker",
        "kubernetes", "git", "aws", "azure", "hibernate", "jpa", "maven",
        "gradle", "junit", "react", "angular", "javascript", "typescript",
        "node.js", "python", "ci/cd", "jenkins", "linux", "agile", "scrum",
        "oops", "data structures", "algorithms",
    ]

    job_lower = job_desc.lower()
    resume_lower = (resume_skills + " " + resume_keywords).lower()

    missing = []
    present = []
    for kw in TECH_KEYWORDS:
        if kw in job_lower:
            if kw not in resume_lower:
                missing.append(kw.title())
            else:
                present.append(kw.title())

    potential = min(current_ats + len(present) * 2, 95)

    return {
        "potential_ats_score": potential,
        "missing_keywords": missing[:8],
        "skills_to_add": missing[:4],
        "skills_to_highlight": present[:4],
        "suggested_summary": f"Motivated Java developer with experience in {', '.join(present[:3])}. Passionate about building scalable backend solutions.",
        "project_suggestions": f"Add projects that demonstrate: {', '.join(missing[:3])}",
        "quick_wins": [
            f"Add '{missing[0]}' to your Skills section" if missing else "Expand your skills section",
            "Quantify your project impact (e.g., 'reduced response time by 40%')",
            "Add relevant keywords from job description in your summary",
        ],
        "cover_letter_hint": f"Mention your experience with {', '.join(present[:2])} and eagerness to learn {missing[0] if missing else 'new technologies'}",
    }
