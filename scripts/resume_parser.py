import os
import json
import re
import requests
from pypdf import PdfReader
from sqlalchemy.orm import Session
from scripts.database import ResumeVersion
from scripts.logger import log_info, log_error, log_warning

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma2:2b")

def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extracts plain text from a PDF file.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"Resume file not found at: {pdf_path}")
        
    try:
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text.strip()
    except Exception as e:
        log_error(f"Failed to extract text from PDF {pdf_path}: {e}", "ResumeParser")
        raise e

def parse_resume_with_ollama(resume_text: str) -> dict:
    """
    Uses local Ollama LLM to extract structured JSON from raw resume text.
    """
    prompt = f"""
You are an expert ATS (Applicant Tracking System) parser. Analyze the following resume text and extract the key information into a structured JSON object.

The output MUST be a valid JSON object with the following keys and structure:
{{
  "skills": ["List", "of", "skills"],
  "experience": [
    {{
      "role": "Job Title",
      "company": "Company Name",
      "duration": "Duration (e.g. Jan 2022 - Present)",
      "description": "Short description of duties and impact"
    }}
  ],
  "projects": [
    {{
      "title": "Project Title",
      "description": "Short summary of the project",
      "technologies": ["Tech1", "Tech2"]
    }}
  ],
  "education": [
    {{
      "degree": "Degree (e.g. B.Tech)",
      "field": "Field of Study (e.g. Computer Science)",
      "institution": "University/College Name",
      "year": "Graduation Year (e.g. 2024)"
    }}
  ],
  "keywords": ["List", "of", "ATS", "keywords", "technologies", "methodologies"]
}}

Resume Text:
---
{resume_text}
---
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
        log_info(f"Sending resume text to Ollama model '{OLLAMA_MODEL}'...", "ResumeParser")
        response = requests.post(url, json=payload, timeout=90)
        response.raise_for_status()
        result_json = response.json()
        response_text = result_json.get("response", "").strip()
        
        # Parse the JSON response
        parsed_data = json.loads(response_text)
        return parsed_data
        
    except requests.exceptions.RequestException as req_err:
        log_error(f"Ollama request error: {req_err}", "ResumeParser")
        raise req_err
    except json.JSONDecodeError as json_err:
        log_error(f"Ollama returned invalid JSON: {json_err}. Raw response: {response_text}", "ResumeParser")
        # Attempt fallback regex extraction or throw
        raise json_err
    except Exception as e:
        log_error(f"Unexpected error during resume parsing: {e}", "ResumeParser")
        raise e

def save_resume_version(db: Session, file_path: str, parsed_data: dict) -> ResumeVersion:
    """
    Saves a new parsed resume version into the PostgreSQL database.
    """
    try:
        # Check if there are existing versions to increment version string
        count = db.query(ResumeVersion).count()
        version_str = f"v{count + 1}.0"
        
        new_version = ResumeVersion(
            version=version_str,
            file_path=file_path,
            parsed_skills=json.dumps(parsed_data.get("skills", [])),
            parsed_experience=json.dumps(parsed_data.get("experience", [])),
            parsed_projects=json.dumps(parsed_data.get("projects", [])),
            parsed_education=json.dumps(parsed_data.get("education", [])),
            parsed_keywords=json.dumps(parsed_data.get("keywords", []))
        )
        
        db.add(new_version)
        db.commit()
        db.refresh(new_version)
        log_info(f"Saved resume version {version_str} into database.", "ResumeParser")
        return new_version
    except Exception as e:
        db.rollback()
        log_error(f"Failed to save resume version to DB: {e}", "ResumeParser")
        raise e
