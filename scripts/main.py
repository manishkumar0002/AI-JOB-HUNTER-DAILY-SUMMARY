import os
import datetime
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import List, Optional
from shutil import copyfileobj

from scripts.database import get_db_session, Job, ResumeVersion
from scripts.logger import log_info, log_error, log_warning, log_performance
from scripts.resume_parser import extract_text_from_pdf, parse_resume_with_ollama, save_resume_version
from scripts.company_scraper import run_scraper_pipeline
from scripts.ats_matcher import match_job_id
from scripts.excel_generator import generate_daily_excel
from scripts.telegram import send_telegram_summary
from scripts.whatsapp import send_whatsapp_summary
from scripts.email_sender import send_email_report

app = FastAPI(
    title="AI Job Hunter API Service",
    description="FastAPI service handling job scraping, resume parsing, ATS scoring, and serving the interactive dashboard UI.",
    version="1.1.0"
)

# Request schemas
class ParseResumeRequest(BaseModel):
    filename: Optional[str] = None

class UpdateStatusRequest(BaseModel):
    status: str

class UpdateNotesRequest(BaseModel):
    notes: str

class IngestJobRequest(BaseModel):
    title: str
    company_name: str
    location: Optional[str] = "India"
    description: Optional[str] = None
    apply_url: str
    recruiter_email: Optional[str] = None
    platform: Optional[str] = "n8n"
    source_type: Optional[str] = "linkedin_post"
    experience: Optional[str] = "0-2 Years"

# Health check
@app.get("/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.datetime.utcnow().isoformat()}

# --- REST APIs FOR WEB DASHBOARD ---

# 1. Fetch Stats
@app.get("/api/stats")
def get_stats(db: Session = Depends(get_db_session)):
    try:
        time_threshold = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
        total_jobs = db.query(Job).count()
        live_jobs = db.query(Job).filter(Job.created_at >= time_threshold).count()
        applied = db.query(Job).filter(Job.status == "Applied").count()
        interviews = db.query(Job).filter(Job.status == "Interview Scheduled").count()
        rejected = db.query(Job).filter(Job.status == "Rejected").count()
        not_match = db.query(Job).filter(Job.status == "Not Match").count()
        offer = db.query(Job).filter(Job.status == "Offer Received").count()
        avg_score = db.query(func.avg(Job.ats_score)).scalar() or 0
        return {
            "total_jobs": total_jobs,
            "live_jobs": live_jobs,
            "applied": applied,
            "interviews": interviews,
            "rejected": rejected,
            "not_match": not_match,
            "offer_received": offer,
            "average_ats_score": round(float(avg_score), 1)
        }
    except Exception as e:
        log_error(f"Failed to fetch stats: {e}", "WorkerAPI")
        raise HTTPException(status_code=500, detail=str(e))

# 2a. Fetch LIVE Jobs (last 24 hours)
@app.get("/api/jobs/live")
def get_live_jobs(source: Optional[str] = None, search: Optional[str] = None, db: Session = Depends(get_db_session)):
    """Returns jobs scraped in the last 24 hours (active/live feed)."""
    try:
        time_threshold = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
        query = db.query(Job).filter(Job.created_at >= time_threshold)
        if source and source.lower() != "all":
            query = query.filter(Job.source_type == source)
        if search:
            query = query.filter(
                (Job.title.ilike(f"%{search}%")) |
                (Job.company_name.ilike(f"%{search}%")) |
                (Job.location.ilike(f"%{search}%"))
            )
        jobs = query.order_by(Job.ats_score.desc().nullslast(), Job.created_at.desc()).all()
        return jobs
    except Exception as e:
        log_error(f"Failed to fetch live jobs: {e}", "WorkerAPI")
        raise HTTPException(status_code=500, detail=str(e))

# 2b. Fetch ARCHIVE Jobs (older than 24 hours)
@app.get("/api/jobs/archive")
def get_archive_jobs(status: Optional[str] = None, search: Optional[str] = None, db: Session = Depends(get_db_session)):
    """Returns jobs older than 24 hours for tracking and follow-up."""
    try:
        time_threshold = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
        query = db.query(Job).filter(Job.created_at < time_threshold)
        if status and status.lower() not in ("all", ""):
            query = query.filter(Job.status == status)
        if search:
            query = query.filter(
                (Job.title.ilike(f"%{search}%")) |
                (Job.company_name.ilike(f"%{search}%")) |
                (Job.location.ilike(f"%{search}%"))
            )
        jobs = query.order_by(Job.ats_score.desc().nullslast(), Job.created_at.desc()).all()
        return jobs
    except Exception as e:
        log_error(f"Failed to fetch archive jobs: {e}", "WorkerAPI")
        raise HTTPException(status_code=500, detail=str(e))

# 2c. Fetch All Jobs (combined, for backwards compat)
@app.get("/api/jobs")
def get_jobs(status: Optional[str] = None, search: Optional[str] = None, db: Session = Depends(get_db_session)):
    try:
        query = db.query(Job)
        if status and status.lower() != "all":
            query = query.filter(Job.status == status)
        if search:
            query = query.filter(
                (Job.title.ilike(f"%{search}%")) |
                (Job.company_name.ilike(f"%{search}%")) |
                (Job.location.ilike(f"%{search}%"))
            )
        jobs = query.order_by(Job.ats_score.desc().nullslast(), Job.created_at.desc()).all()
        return jobs
    except Exception as e:
        log_error(f"Failed to fetch jobs: {e}", "WorkerAPI")
        raise HTTPException(status_code=500, detail=str(e))

# 3. Update Status
@app.put("/api/jobs/{job_id}/status")
def update_job_status(job_id: int, payload: UpdateStatusRequest, db: Session = Depends(get_db_session)):
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job listing not found")
            
        job.status = payload.status
        if payload.status == "Applied" and not job.date_applied:
            job.date_applied = datetime.datetime.utcnow()
            
        db.commit()
        log_info(f"Updated status of Job {job_id} to '{payload.status}'", "WorkerAPI")
        return {"status": "success", "job_id": job_id, "new_status": payload.status}
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        log_error(f"Failed to update job status: {e}", "WorkerAPI")
        raise HTTPException(status_code=500, detail=str(e))

# 4. Update Notes
@app.put("/api/jobs/{job_id}/notes")
def update_job_notes(job_id: int, payload: UpdateNotesRequest, db: Session = Depends(get_db_session)):
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job listing not found")
            
        job.notes = payload.notes
        db.commit()
        log_info(f"Updated notes for Job {job_id}", "WorkerAPI")
        return {"status": "success", "job_id": job_id, "notes": payload.notes}
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        log_error(f"Failed to update job notes: {e}", "WorkerAPI")
        raise HTTPException(status_code=500, detail=str(e))

# 5. Ingest Job (from n8n / YouTube / any external source)
@app.post("/api/jobs/ingest")
def ingest_job(payload: IngestJobRequest, db: Session = Depends(get_db_session)):
    """Universal job ingestion endpoint — n8n, YouTube, LinkedIn posts all POST here."""
    try:
        from scripts.database import Company
        from scripts.duplicate_detector import is_duplicate, add_hash
        
        if is_duplicate(db, payload.company_name, payload.title, payload.location or "", payload.apply_url):
            return {"status": "duplicate", "message": "Job already exists in database"}
        
        company = db.query(Company).filter(Company.name.ilike(payload.company_name)).first()
        if not company:
            company = Company(name=payload.company_name)
            db.add(company)
            db.commit()
            db.refresh(company)
        
        add_hash(db, payload.company_name, payload.title, payload.location or "", payload.apply_url)
        
        new_job = Job(
            title=payload.title,
            company_id=company.id,
            company_name=payload.company_name,
            location=payload.location or "India",
            description=payload.description or "",
            experience=payload.experience or "0-2 Years",
            platform=payload.platform or "n8n",
            source_type=payload.source_type or "linkedin_post",
            apply_url=payload.apply_url,
            recruiter_email=payload.recruiter_email,
            posted_date=datetime.datetime.utcnow(),
            status="Not Applied",
        )
        db.add(new_job)
        db.commit()
        db.refresh(new_job)
        log_info(f"Ingested job '{payload.title}' at '{payload.company_name}' via {payload.platform}", "WorkerAPI")
        return {"status": "success", "job_id": new_job.id, "title": new_job.title}
    except Exception as e:
        db.rollback()
        log_error(f"Job ingest failed: {e}", "WorkerAPI")
        raise HTTPException(status_code=500, detail=str(e))

# 6. AI Resume Tailoring
@app.post("/api/jobs/{job_id}/tailor")
def tailor_resume_for_job(job_id: int):
    """Generates AI-powered resume tailoring suggestions for a specific job."""
    try:
        from scripts.resume_tailor import generate_tailoring_suggestions
        suggestions = generate_tailoring_suggestions(job_id)
        if "error" in suggestions:
            raise HTTPException(status_code=404, detail=suggestions["error"])
        return {"status": "success", "suggestions": suggestions}
    except HTTPException as he:
        raise he
    except Exception as e:
        log_error(f"Resume tailoring endpoint failed: {e}", "WorkerAPI")
        raise HTTPException(status_code=500, detail=str(e))

# 5. Fetch Resume Details
@app.get("/api/resume")
def get_resume_details(db: Session = Depends(get_db_session)):
    try:
        latest = db.query(ResumeVersion).order_by(ResumeVersion.id.desc()).first()
        if not latest:
            return {"status": "empty", "message": "No resume versions parsed yet."}
        return {
            "status": "success",
            "version": latest.version,
            "file_path": latest.file_path,
            "parsed_skills": latest.parsed_skills,
            "parsed_experience": latest.parsed_experience,
            "parsed_projects": latest.parsed_projects,
            "parsed_education": latest.parsed_education,
            "parsed_keywords": latest.parsed_keywords,
            "created_at": latest.created_at
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 6. Upload Resume
@app.post("/api/resume/upload")
def upload_resume(file: UploadFile = File(...), db: Session = Depends(get_db_session)):
    if not file.filename.endswith(".pdf") and not file.filename.endswith(".txt"):
        raise HTTPException(status_code=400, detail="Only PDF and plain TXT resumes are supported.")
        
    resumes_dir = "/app/resumes"
    if not os.path.exists(resumes_dir):
        os.makedirs(resumes_dir, exist_ok=True)
        
    ext = ".pdf" if file.filename.endswith(".pdf") else ".txt"
    file_path = os.path.join(resumes_dir, f"resume{ext}")
    
    try:
        with open(file_path, "wb") as buffer:
            copyfileobj(file.file, buffer)
            
        log_info(f"Uploaded resume to {file_path}. Initiating parser pipeline...", "WorkerAPI")
        
        # Set filename context and parse
        os.environ["RESUME_FILENAME"] = f"resume{ext}"
        parse_res = parse_resume(db=db)
        
        return {
            "status": "success",
            "filename": file.filename,
            "parsed_version": parse_res.get("version")
        }
    except Exception as e:
        log_error(f"Resume upload/parse failure: {e}", "WorkerAPI")
        raise HTTPException(status_code=500, detail=str(e))

# 7. Excel Download
@app.get("/api/reports/download")
def download_excel_report():
    try:
        reports_dir = "/app/reports"
        if not os.path.exists(reports_dir):
            raise HTTPException(status_code=404, detail="Reports directory does not exist.")
            
        # Get files matching Jobs_*.xlsx
        files = [os.path.join(reports_dir, f) for f in os.listdir(reports_dir) if f.startswith("Jobs_") and f.endswith(".xlsx")]
        if not files:
            raise HTTPException(status_code=404, detail="No Excel reports available. Run the scraping pipeline first.")
            
        # Select the newest file
        newest_file = max(files, key=os.path.getmtime)
        return FileResponse(
            newest_file, 
            filename=os.path.basename(newest_file),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        log_error(f"Failed to download report: {e}", "WorkerAPI")
        raise HTTPException(status_code=500, detail=str(e))


# --- PIPELINE ENDPOINTS ---

# Parse Resume API
@app.post("/resume/parse")
def parse_resume(payload: ParseResumeRequest = None, db: Session = Depends(get_db_session)):
    filename = (payload.filename if payload else None) or os.getenv("RESUME_FILENAME", "resume.pdf")
    resumes_dir = "/app/resumes"
    
    # Try pdf or text fallback
    pdf_path = os.path.join(resumes_dir, filename)
    if not os.path.exists(pdf_path):
        # Check if txt exists
        filename_txt = filename.replace(".pdf", ".txt")
        pdf_path = os.path.join(resumes_dir, filename_txt)
        
    if not os.path.exists(pdf_path):
        log_error(f"Resume file not found at {pdf_path}", "WorkerAPI")
        raise HTTPException(status_code=404, detail=f"Resume file not found at {pdf_path}")
        
    try:
        start_time = datetime.datetime.now()
        text = extract_text_from_pdf(pdf_path) if pdf_path.endswith(".pdf") else open(pdf_path, 'r', encoding='utf-8').read()
        parsed_data = parse_resume_with_ollama(text)
        version_rec = save_resume_version(db, pdf_path, parsed_data)
        
        duration = (datetime.datetime.now() - start_time).total_seconds()
        log_performance(f"Parsed resume version {version_rec.version} in {duration:.2f}s")
        
        return {
            "status": "success",
            "version": version_rec.version,
            "skills_count": len(parsed_data.get("skills", [])),
            "experience_count": len(parsed_data.get("experience", []))
        }
    except Exception as e:
        log_error(f"Resume parsing failure: {e}", "WorkerAPI")
        raise HTTPException(status_code=500, detail=str(e))

# Scrape Jobs API
@app.post("/jobs/scrape")
async def scrape_jobs(db: Session = Depends(get_db_session)):
    try:
        start_time = datetime.datetime.now()
        latest_resume = db.query(ResumeVersion).order_by(ResumeVersion.id.desc()).first()
        if not latest_resume:
            log_warning("No parsed resume found. Match scores will be empty.", "WorkerAPI")

        scraped_jobs = await run_scraper_pipeline(db)
        duration = (datetime.datetime.now() - start_time).total_seconds()
        log_performance(f"Scraped {len(scraped_jobs)} jobs in {duration:.2f}s")
        
        return {
            "status": "success",
            "jobs_scraped": len(scraped_jobs)
        }
    except Exception as e:
        log_error(f"Job scraping failure: {e}", "WorkerAPI")
        raise HTTPException(status_code=500, detail=str(e))

# Match Jobs API
@app.post("/jobs/ats-match")
def ats_match_jobs(db: Session = Depends(get_db_session)):
    try:
        start_time = datetime.datetime.now()
        time_threshold = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
        unscored_jobs = db.query(Job).filter(
            Job.ats_score.is_(None),
            Job.created_at >= time_threshold
        ).all()
        
        if not unscored_jobs:
            return {"status": "success", "jobs_matched": 0, "message": "No unscored jobs found."}
            
        matched_count = 0
        for job in unscored_jobs:
            success = match_job_id(db, job.id)
            if success:
                matched_count += 1
                
        duration = (datetime.datetime.now() - start_time).total_seconds()
        log_performance(f"ATS Matched {matched_count} jobs in {duration:.2f}s")
        
        return {
            "status": "success",
            "jobs_matched": matched_count
        }
    except Exception as e:
        log_error(f"ATS Matching failure: {e}", "WorkerAPI")
        raise HTTPException(status_code=500, detail=str(e))

# Generate Excel Report API
@app.post("/reports/excel")
def generate_report(db: Session = Depends(get_db_session)):
    try:
        start_time = datetime.datetime.now()
        excel_path = generate_daily_excel(db)
        
        duration = (datetime.datetime.now() - start_time).total_seconds()
        log_performance(f"Generated daily Excel in {duration:.2f}s")
        
        return {
            "status": "success",
            "excel_path": excel_path,
            "filename": os.path.basename(excel_path)
        }
    except Exception as e:
        log_error(f"Excel generation failure: {e}", "WorkerAPI")
        raise HTTPException(status_code=500, detail=str(e))

# Send Alerts API
@app.post("/notifications/send")
def send_notifications(db: Session = Depends(get_db_session)):
    try:
        time_threshold = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
        jobs = db.query(Job).filter(Job.created_at >= time_threshold).all()
        
        total_jobs = len(jobs)
        high_prio = sum(1 for j in jobs if j.priority == "High")
        
        highest_ats = 0
        highest_ats_company = "N/A"
        highest_ats_title = "N/A"
        
        top_companies = set()
        for j in jobs:
            top_companies.add(j.company_name)
            if j.ats_score and j.ats_score > highest_ats:
                highest_ats = j.ats_score
                highest_ats_company = j.company_name
                highest_ats_title = j.title
                
        today_str = datetime.date.today().strftime("%Y_%m_%d")
        reports_dir = os.getenv("REPORTS_DIR", "/app/reports")
        excel_path = os.path.join(reports_dir, f"Jobs_{today_str}.xlsx")
        
        summary_data = {
            "date": datetime.date.today().strftime("%Y-%m-%d"),
            "total_jobs": total_jobs,
            "high_priority": high_prio,
            "highest_ats": highest_ats,
            "highest_ats_company": highest_ats_company,
            "highest_ats_title": highest_ats_title,
            "excel_path": excel_path,
            "top_companies": list(top_companies)[:5]
        }
        
        tg_success = send_telegram_summary(summary_data)
        wa_success = send_whatsapp_summary(summary_data)
        email_success = send_email_report(summary_data)
        
        return {
            "status": "success",
            "notifications": {
                "telegram": tg_success,
                "whatsapp": wa_success,
                "email": email_success
            }
        }
    except Exception as e:
        log_error(f"Notification dispatch failure: {e}", "WorkerAPI")
        raise HTTPException(status_code=500, detail=str(e))

# Run pipeline
@app.post("/pipeline/run")
async def run_pipeline(db: Session = Depends(get_db_session)):
    log_info("Pipeline run initiated.", "Pipeline")
    results = {}
    
    # 1. Parse Resume if file exists
    try:
        res = parse_resume(db=db)
        results["parse_resume"] = res
    except Exception as e:
        results["parse_resume"] = {"status": "failed", "error": str(e)}
        log_warning(f"Pipeline step 1 failed: {e}", "Pipeline")
        
    # 2. Scrape Jobs
    try:
        res = await scrape_jobs(db=db)
        results["scrape_jobs"] = res
    except Exception as e:
        results["scrape_jobs"] = {"status": "failed", "error": str(e)}
        log_error(f"Pipeline step 2 critical failure: {e}", "Pipeline")
        raise HTTPException(status_code=500, detail=f"Pipeline aborted. Scraping failed: {e}")
        
    # 3. Match Jobs
    try:
        res = ats_match_jobs(db=db)
        results["ats_match"] = res
    except Exception as e:
        results["ats_match"] = {"status": "failed", "error": str(e)}
        log_warning(f"Pipeline step 3 failed: {e}", "Pipeline")
        
    # 4. Excel report
    try:
        res = generate_report(db=db)
        results["excel_report"] = res
    except Exception as e:
        results["excel_report"] = {"status": "failed", "error": str(e)}
        log_warning(f"Pipeline step 4 failed: {e}", "Pipeline")
        
    # 5. Send alerts
    try:
        res = send_notifications(db=db)
        results["notifications"] = res
    except Exception as e:
        results["notifications"] = {"status": "failed", "error": str(e)}
        log_warning(f"Pipeline step 5 failed: {e}", "Pipeline")
        
    log_info("Pipeline run complete.", "Pipeline")
    return {"status": "success", "steps": results}


# --- FRONTEND ROUTING & MOUNTING ---

# Serve index.html at root
@app.get("/", response_class=HTMLResponse)
def read_root():
    index_path = "/app/scripts/static/index.html"
    if not os.path.exists(index_path):
        return """
        <html>
            <body style="font-family: Arial, sans-serif; text-align: center; padding-top: 100px; background-color: #0f172a; color: #f1f5f9;">
                <h1>🤖 AI Job Hunter API Service</h1>
                <p style="color: #94a3b8;">Frontend static UI files not found at /app/scripts/static/index.html.</p>
                <p>Check logs and verify folder mount paths inside your Docker Compose.</p>
            </body>
        </html>
        """
    with open(index_path, "r", encoding="utf-8") as file:
        return file.read()

# Mount Static Files (CSS, JS)
static_dir = "/app/scripts/static"
if not os.path.exists(static_dir):
    os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")
