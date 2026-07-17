import hashlib
from sqlalchemy.orm import Session
from scripts.database import DuplicateHash
from scripts.logger import log_info, log_error

def generate_job_hash(company: str, title: str, location: str, apply_url: str) -> str:
    """
    Generates a unique MD5 hash for a job based on normalized attributes.
    """
    # Normalize inputs: strip whitespace, lowercase, and remove special characters where appropriate
    norm_company = "".join(company.lower().split())
    norm_title = "".join(title.lower().split())
    norm_location = "".join(location.lower().split()) if location else ""
    norm_url = "".join(apply_url.lower().split()) if apply_url else ""
    
    combined = f"{norm_company}|{norm_title}|{norm_location}|{norm_url}"
    return hashlib.md5(combined.encode('utf-8')).hexdigest()

def is_duplicate(db: Session, company: str, title: str, location: str, apply_url: str) -> bool:
    """
    Checks if a job already exists in the duplicate_hashes table without inserting it.
    """
    job_hash = generate_job_hash(company, title, location, apply_url)
    try:
        exists = db.query(DuplicateHash).filter(DuplicateHash.job_hash == job_hash).first() is not None
        return exists
    except Exception as e:
        log_error(f"Error checking duplicate hash: {e}", "DuplicateDetector")
        return False

def add_hash(db: Session, company: str, title: str, location: str, apply_url: str) -> bool:
    """
    Saves a job hash into the duplicate_hashes table to mark it as parsed.
    Returns True if successfully added, False otherwise.
    """
    job_hash = generate_job_hash(company, title, location, apply_url)
    try:
        # Check if it was inserted in the meantime
        exists = db.query(DuplicateHash).filter(DuplicateHash.job_hash == job_hash).first()
        if not exists:
            new_hash = DuplicateHash(job_hash=job_hash)
            db.add(new_hash)
            db.commit()
            return True
        return False
    except Exception as e:
        db.rollback()
        log_error(f"Error adding duplicate hash: {e}", "DuplicateDetector")
        return False
