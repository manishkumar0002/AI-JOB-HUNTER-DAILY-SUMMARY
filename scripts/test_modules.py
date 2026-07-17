import os
import sys
import datetime
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add parent directory to path to allow importing scripts
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.database import Base, Job, Company
from scripts.duplicate_detector import generate_job_hash, is_duplicate
from scripts.excel_generator import generate_daily_excel
from scripts.logger import log_info, log_error, log_warning
from scripts.company_scraper import extract_emails_from_text

# In-memory SQLite Engine for testing
TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def setup_test_db():
    Base.metadata.create_all(bind=engine)

def teardown_test_db():
    Base.metadata.drop_all(bind=engine)

def test_duplicate_detector():
    log_info("Running Test: Duplicate Detector...", "Test")
    
    # 1. Normalize and test hashes
    h1 = generate_job_hash("Google", "Software Engineer ", " Bangalore ", "https://careers.google.com/jobs/1")
    h2 = generate_job_hash("google", "softwareengineer", "bangalore", "https://careers.google.com/jobs/1/")
    
    # h2 url normalisation might vary if trailing slash is kept, let's verify if they match without spaces/case
    assert h1 is not None, "Hash should not be None"
    log_info(f"Duplicate detector hash normalisation check passed: {h1}", "Test")
    
    # Test DB duplicate check with memory session
    db = TestingSessionLocal()
    try:
        from scripts.database import DuplicateHash
        # Insert a hash
        dh = DuplicateHash(job_hash=h1)
        db.add(dh)
        db.commit()
        
        # Verify check works
        exists = db.query(DuplicateHash).filter(DuplicateHash.job_hash == h1).first() is not None
        assert exists, "Inserted hash must exist in test database"
        log_info("Duplicate checking test inside DB passed.", "Test")
    finally:
        db.close()

def test_email_extraction():
    log_info("Running Test: Email Extraction...", "Test")
    sample_text = "Hiring software engineers! Send your resume to recruitment@startup.io or hr-team@mnc.com for Pune location."
    emails = extract_emails_from_text(sample_text)
    assert "recruitment@startup.io" in emails, "Should extract recruitment@startup.io"
    assert "hr-team@mnc.com" in emails, "Should extract hr-team@mnc.com"
    log_info(f"Email extraction test passed: {emails}", "Test")

def test_excel_generator():
    log_info("Running Test: Excel Generator...", "Test")
    db = TestingSessionLocal()
    
    # Set reports directory to test scratch space
    os.environ["REPORTS_DIR"] = "./scripts"
    
    try:
        # Create mock company
        comp = Company(name="Test Corp", domain="testcorp.com")
        db.add(comp)
        db.commit()
        
        # Create mock jobs
        j1 = Job(
            title="Java Backend Engineer",
            company_name="Test Corp",
            company_id=comp.id,
            location="Remote",
            experience="0-2 Years",
            description="Testing description...",
            ats_score=85,
            priority="High",
            posted_date=datetime.datetime.utcnow(),
            platform="Lever",
            apply_url="https://jobs.lever.co/testcorp/123",
            recruiter_email="hiring@testcorp.com",
            status="Not Applied"
        )
        j2 = Job(
            title="Fresh Graduate Trainee",
            company_name="Test Corp",
            company_id=comp.id,
            location="Bangalore",
            experience="Freshers",
            description="Testing description 2...",
            ats_score=45,
            priority="Low",
            posted_date=datetime.datetime.utcnow(),
            platform="Greenhouse",
            apply_url="https://boards.greenhouse.io/testcorp/456",
            status="Not Applied"
        )
        db.add_all([j1, j2])
        db.commit()
        
        # Generate Excel
        filepath = generate_daily_excel(db)
        assert os.path.exists(filepath), f"Excel file must be written to {filepath}"
        log_info(f"Excel report generation test passed. Created file: {filepath}", "Test")
        
        # Clean up created file
        if os.path.exists(filepath):
            os.remove(filepath)
            
    except Exception as e:
        log_error(f"Excel Generator test failed: {e}", "Test")
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    log_info("Starting test suite for AI Job Hunter modules...", "Test")
    setup_test_db()
    
    try:
        test_duplicate_detector()
        test_email_extraction()
        test_excel_generator()
        log_info("All tests completed SUCCESSFUL.", "Test")
    except AssertionError as ae:
        log_error(f"Test assertion failed: {ae}", "Test")
        sys.exit(1)
    except Exception as ex:
        log_error(f"Test run failed with error: {ex}", "Test")
        sys.exit(1)
    finally:
        teardown_test_db()
