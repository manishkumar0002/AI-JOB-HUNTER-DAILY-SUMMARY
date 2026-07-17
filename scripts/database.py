import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

Base = declarative_base()

# Retrieve database connection parameters from environment
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "jobhunter_secure_password_123")
POSTGRES_DB = os.getenv("POSTGRES_DB", "job_hunter")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "db")

# If connecting container-to-container inside Docker network, use internal port 5432.
# If connecting from the host machine, use POSTGRES_PORT.
if POSTGRES_HOST == "db":
    POSTGRES_PORT = "5432"
else:
    POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")

# Construct DATABASE_URL
DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

# Create Engine
engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=20, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db_session():
    """Yields a database session and closes it once the request/process is complete."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ORM Models
class Log(Base):
    __tablename__ = 'logs'
    id = Column(Integer, primary_key=True, index=True)
    level = Column(String(20), nullable=False)
    message = Column(Text, nullable=False)
    module = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)

class Company(Base):
    __tablename__ = 'companies'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False)
    domain = Column(String(255))
    career_page_url = Column(String(1024))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    jobs = relationship("Job", back_populates="company")

class Job(Base):
    __tablename__ = 'jobs'
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    company_id = Column(Integer, ForeignKey('companies.id', ondelete='SET NULL'))
    company_name = Column(String(255), nullable=False)
    location = Column(String(255))
    description = Column(Text)
    experience = Column(String(100))
    skills = Column(Text)
    ats_score = Column(Integer)
    skill_match = Column(Integer)
    missing_skills = Column(Text)
    confidence_score = Column(Integer)
    priority = Column(String(20), default='Low')
    posted_date = Column(DateTime)
    platform = Column(String(100))
    source_type = Column(String(50), default='linkedin_jobs')  # linkedin_jobs | linkedin_post | career_page
    apply_url = Column(Text)
    recruiter_email = Column(String(255))
    status = Column(String(50), default='Not Applied')
    date_applied = Column(DateTime)
    notes = Column(Text)
    follow_up_date = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company = relationship("Company", back_populates="jobs")
    applications = relationship("Application", back_populates="job", cascade="all, delete-orphan")

class Application(Base):
    __tablename__ = 'applications'
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey('jobs.id', ondelete='CASCADE'))
    status = Column(String(50), nullable=False)
    notes = Column(Text)
    date_applied = Column(DateTime, default=datetime.utcnow)
    follow_up_date = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("Job", back_populates="applications")

class DuplicateHash(Base):
    __tablename__ = 'duplicate_hashes'
    id = Column(Integer, primary_key=True, index=True)
    job_hash = Column(String(64), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class ResumeVersion(Base):
    __tablename__ = 'resume_versions'
    id = Column(Integer, primary_key=True, index=True)
    version = Column(String(50), nullable=False)
    file_path = Column(String(1024), nullable=False)
    parsed_skills = Column(Text)
    parsed_experience = Column(Text)
    parsed_projects = Column(Text)
    parsed_education = Column(Text)
    parsed_keywords = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

class Skill(Base):
    __tablename__ = 'skills'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    category = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
