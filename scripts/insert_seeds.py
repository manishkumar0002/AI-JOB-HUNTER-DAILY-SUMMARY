import datetime
from sqlalchemy.orm import Session
from scripts.database import get_db_session, Job, Company
from scripts.ats_matcher import match_job_id
from scripts.logger import log_info, log_error

def seed_jobs():
    db = next(get_db_session())
    log_info("Seeding sample active fresher jobs...", "Seed")
    
    jobs_to_seed = [
        {
            "company_name": "Redwood Software",
            "title": "Associate Software Engineer (Java / Spring Boot)",
            "location": "Hyderabad, India",
            "description": "We are looking for an Associate Software Engineer to join our growing engineering team in Hyderabad. In this role, you will write clean, maintainable, and well-tested code using Java and Spring Boot to deliver scalable backend services and microservices. You will work with relational databases, REST APIs, and collaborate using Git version control. This is a junior role suitable for freshers graduating in 2026.",
            "platform": "Greenhouse",
            "apply_url": "https://boards.greenhouse.io/redwoodsoftware/jobs/4207901005",
            "recruiter_email": "careers.india@redwood.com"
        },
        {
            "company_name": "Conga",
            "title": "Associate Software Engineer",
            "location": "Ahmedabad, India",
            "description": "Conga is hiring an Associate Software Engineer to join our core development team. You will write code in Java and SQL databases. You will assist in debugging issues, building microservices, and writing unit tests. Candidates should have a B.Tech in IT or Computer Science with strong coding fundamentals, Java programming knowledge, and familiarity with Git.",
            "platform": "Greenhouse",
            "apply_url": "https://boards.greenhouse.io/conga/jobs/3810052",
            "recruiter_email": None
        },
        {
            "company_name": "Apollo.io",
            "title": "Software Engineer II - Backend",
            "location": "Remote, India",
            "description": "Apollo.io is looking for a backend engineer. You will work on scaling our data pipelines and backend web applications. Key technologies include Java, Python, and PostgreSQL databases. Strong system design, database optimization, and REST API experience are required.",
            "platform": "Greenhouse",
            "apply_url": "https://boards.greenhouse.io/apolloio/jobs/4012035",
            "recruiter_email": None
        }
    ]
    
    seeded_count = 0
    for jdata in jobs_to_seed:
        try:
            # 1. Company
            company = db.query(Company).filter(Company.name.ilike(jdata["company_name"])).first()
            if not company:
                company = Company(name=jdata["company_name"])
                db.add(company)
                db.commit()
                db.refresh(company)
                
            # Check duplicate
            existing = db.query(Job).filter(Job.apply_url == jdata["apply_url"]).first()
            if existing:
                log_info(f"Job '{jdata['title']}' already exists in DB. Skipping.", "Seed")
                continue
                
            new_job = Job(
                title=jdata["title"],
                company_id=company.id,
                company_name=company.name,
                location=jdata["location"],
                description=jdata["description"],
                experience="0-2 Years",
                posted_date=datetime.datetime.utcnow(),
                platform=jdata["platform"],
                apply_url=jdata["apply_url"],
                recruiter_email=jdata["recruiter_email"],
                status="Not Applied"
            )
            db.add(new_job)
            db.commit()
            db.refresh(new_job)
            seeded_count += 1
            log_info(f"Seeded '{jdata['title']}' at '{jdata['company_name']}'.", "Seed")
            
        except Exception as e:
            db.rollback()
            log_error(f"Error seeding job: {e}", "Seed")
            
    if seeded_count > 0 or db.query(Job).filter(Job.ats_score.is_(None)).count() > 0:
        log_info("Running ATS Matcher on jobs using Ollama...", "Seed")
        unscored = db.query(Job).filter(Job.ats_score.is_(None)).all()
        for job in unscored:
            match_job_id(db, job.id)
        log_info("ATS Matching complete!", "Seed")
    else:
        log_info("No new jobs seeded.", "Seed")

if __name__ == "__main__":
    seed_jobs()
