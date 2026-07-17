-- AI Job Hunter PostgreSQL Schema Initialization

-- Create logs table first so other processes can log database operations
CREATE TABLE IF NOT EXISTS logs (
    id SERIAL PRIMARY KEY,
    level VARCHAR(20) NOT NULL,
    message TEXT NOT NULL,
    module VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create companies table
CREATE TABLE IF NOT EXISTS companies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    domain VARCHAR(255),
    career_page_url VARCHAR(1024),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create jobs table
CREATE TABLE IF NOT EXISTS jobs (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
    company_name VARCHAR(255) NOT NULL,
    location VARCHAR(255),
    description TEXT,
    experience VARCHAR(100),
    skills TEXT,
    ats_score INTEGER,
    skill_match INTEGER,
    missing_skills TEXT,
    confidence_score INTEGER,
    priority VARCHAR(20) DEFAULT 'Low', -- High, Medium, Low
    posted_date TIMESTAMP,
    platform VARCHAR(100),
    apply_url TEXT,
    recruiter_email VARCHAR(255),
    status VARCHAR(50) DEFAULT 'Not Applied', -- Not Applied, Applied, Assessment, Interview Scheduled, HR Round, Technical Round, Offer, Rejected, No Response, Follow-up
    date_applied TIMESTAMP,
    notes TEXT,
    follow_up_date TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create applications table for tracking status transitions (optional log)
CREATE TABLE IF NOT EXISTS applications (
    id SERIAL PRIMARY KEY,
    job_id INTEGER REFERENCES jobs(id) ON DELETE CASCADE,
    status VARCHAR(50) NOT NULL,
    notes TEXT,
    date_applied TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    follow_up_date TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create duplicate_hashes table to prevent scraping the same job twice
CREATE TABLE IF NOT EXISTS duplicate_hashes (
    id SERIAL PRIMARY KEY,
    job_hash VARCHAR(64) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create resume_versions table
CREATE TABLE IF NOT EXISTS resume_versions (
    id SERIAL PRIMARY KEY,
    version VARCHAR(50) NOT NULL,
    file_path VARCHAR(1024) NOT NULL,
    parsed_skills TEXT,       -- comma-separated or JSON string
    parsed_experience TEXT,   -- detailed text or JSON
    parsed_projects TEXT,     -- detailed text or JSON
    parsed_education TEXT,    -- detailed text or JSON
    parsed_keywords TEXT,     -- comma-separated
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create skills table
CREATE TABLE IF NOT EXISTS skills (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    category VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for quick lookups on hashes and status
CREATE INDEX IF NOT EXISTS idx_duplicate_hashes ON duplicate_hashes(job_hash);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_company_id ON jobs(company_id);
