import os
import json
import requests
from sqlalchemy.orm import Session
from scripts.database import ResumeVersion, Job
from scripts.logger import log_info, log_error, log_warning

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma2:2b")

def get_latest_resume_version(db: Session) -> dict:
    """
    Retrieves the latest parsed resume version from the database.
    """
    version_record = db.query(ResumeVersion).order_by(ResumeVersion.id.desc()).first()
    if not version_record:
        raise ValueError("No parsed resume versions found in the database. Please parse the resume first.")
        
    return {
        "skills": json.loads(version_record.parsed_skills or "[]"),
        "experience": json.loads(version_record.parsed_experience or "[]"),
        "projects": json.loads(version_record.parsed_projects or "[]"),
        "education": json.loads(version_record.parsed_education or "[]"),
        "keywords": json.loads(version_record.parsed_keywords or "[]")
    }

def calculate_ats_match(resume_details: dict, job_title: str, company_name: str, job_description: str) -> dict:
    """
    Scores a job description against the resume details using Ollama.
    """
    if not job_description or len(job_description.strip()) < 50:
        log_warning(f"Job description too short or empty for '{job_title}' at '{company_name}'. Rating low.", "ATSMatcher")
        return {
            "ats_score": 0,
            "skill_match": 0,
            "missing_skills": [],
            "confidence_score": 100,
            "priority": "Low"
        }

    # Format the prompt
    prompt = f"""
You are an expert ATS (Applicant Tracking System) matching engine.
Compare the Candidate's Resume Details with the Job Description.

Candidate Resume Details:
- Skills: {', '.join(resume_details.get('skills', []))}
- Experience Summary: {json.dumps(resume_details.get('experience', []))}
- Keywords: {', '.join(resume_details.get('keywords', []))}

Job Description:
- Title: {job_title}
- Company: {company_name}
- Full Description:
{job_description}

Evaluate the alignment and output a valid JSON object with the following keys:
- "ats_score": Integer (0 to 100) representing the candidate's general match for the job.
- "skill_match": Integer (0 to 100) representing the percentage of technologies required by the job that the candidate possesses.
- "missing_skills": List of strings representing important skills/technologies mentioned in the job description that the candidate lacks.
- "confidence_score": Integer (0 to 100) representing your confidence in this analysis.
- "priority": String ("High", "Medium", "Low") where:
  - "High" is for ATS score >= 80 and matching core software engineering principles.
  - "Medium" is for ATS score between 60 and 79.
  - "Low" is for ATS score < 60.

Output only valid JSON. Do not include any explanation, code fences (e.g. ```json), or metadata.
"""

    url = f"{OLLAMA_HOST}/api/generate"
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "format": "json",
        "stream": False,
        "options": {
            "temperature": 0.1
        }
    }

    try:
        response = requests.post(url, json=payload, timeout=90)
        response.raise_for_status()
        result_json = response.json()
        response_text = result_json.get("response", "").strip()
        
        parsed_result = json.loads(response_text)
        
        # Validate critical keys in JSON response and apply fallbacks if missing
        return {
            "ats_score": int(parsed_result.get("ats_score", 0)),
            "skill_match": int(parsed_result.get("skill_match", 0)),
            "missing_skills": parsed_result.get("missing_skills", []),
            "confidence_score": int(parsed_result.get("confidence_score", 50)),
            "priority": parsed_result.get("priority", "Low")
        }
        
    except Exception as e:
        log_error(f"Error matching job '{job_title}' at '{company_name}' with Ollama: {e}", "ATSMatcher")
        # Default safe fallback values in case of parser/network errors
        return {
            "ats_score": 0,
            "skill_match": 0,
            "missing_skills": [],
            "confidence_score": 0,
            "priority": "Low"
        }

def match_job_id(db: Session, job_id: int) -> bool:
    """
    Extracts the latest resume, matches it against a specific Job in the DB, and updates that Job's score columns.
    """
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            log_error(f"Job with ID {job_id} not found for matching.", "ATSMatcher")
            return False
            
        resume_details = get_latest_resume_version(db)
        log_info(f"Running ATS matcher for Job ID {job.id}: '{job.title}' at '{job.company_name}'...", "ATSMatcher")
        
        match_results = calculate_ats_match(
            resume_details=resume_details,
            job_title=job.title,
            company_name=job.company_name,
            job_description=job.description
        )
        
        # Update DB fields
        job.ats_score = match_results["ats_score"]
        job.skill_match = match_results["skill_match"]
        job.missing_skills = ", ".join(match_results["missing_skills"])
        job.confidence_score = match_results["confidence_score"]
        job.priority = match_results["priority"]
        
        db.commit()
        log_info(f"ATS Match complete. Score: {job.ats_score}, Priority: {job.priority}", "ATSMatcher")
        return True
        
    except Exception as e:
        db.rollback()
        log_error(f"Failed to match and update job {job_id}: {e}", "ATSMatcher")
        return False
