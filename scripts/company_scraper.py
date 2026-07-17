import os
import re
import urllib.parse
import datetime
import asyncio
import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from scripts.database import Job, Company
from scripts.duplicate_detector import is_duplicate, add_hash
from scripts.logger import log_info, log_error, log_warning

# Environment Variables
JOB_KEYWORDS = os.getenv(
    "JOB_KEYWORDS",
    "Backend Developer,Software Engineer,Java Developer,Spring Boot Developer,Java Full Stack Developer,Associate Software Engineer,Graduate Engineer Trainee,Entry Level Software Engineer,Freshers"
).split(",")

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

def extract_emails_from_text(text: str) -> str:
    if not text:
        return None
    emails = list(set(EMAIL_REGEX.findall(text)))
    return ", ".join(emails) if emails else None


async def scrape_linkedin_guest(keyword: str, location: str) -> list:
    """Scrapes LinkedIn Guest API for job openings from the last 24 hours."""
    jobs = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    }
    for start in [0, 25]:
        url = (
            f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
            f"?keywords={urllib.parse.quote(keyword)}&location={urllib.parse.quote(location)}"
            f"&f_TPR=r86400&start={start}"
        )
        try:
            log_info(f"Querying LinkedIn Guest API for '{keyword}' ({location}) start={start}...", "Scraper")
            response = requests.get(url, headers=headers, timeout=20)
            if response.status_code != 200:
                log_warning(f"LinkedIn Guest search returned {response.status_code} for '{keyword}'", "Scraper")
                continue
            soup = BeautifulSoup(response.text, 'html.parser')
            for item in soup.find_all('li'):
                title_el = item.find('h3', class_='base-search-card__title')
                company_el = item.find('h4', class_='base-search-card__subtitle')
                location_el = item.find('span', class_='job-search-card__location')
                link_el = item.find('a', class_='base-card__full-link')
                title = title_el.get_text(strip=True) if title_el else None
                company = company_el.get_text(strip=True) if company_el else None
                loc = location_el.get_text(strip=True) if location_el else "India"
                link = link_el.get('href').split('?')[0] if link_el else None
                if title and company and link:
                    jobs.append({
                        "title": title,
                        "company_name": company,
                        "location": loc,
                        "apply_url": link,
                        "platform": "LinkedIn",
                        "source_type": "linkedin_jobs",
                    })
        except Exception as e:
            log_error(f"LinkedIn Guest Search exception for '{keyword}': {e}", "Scraper")
        await asyncio.sleep(2)
    return jobs


def fetch_linkedin_description(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            desc_el = soup.find(class_='show-more-less-html__markup') or soup.find(class_='description__text')
            if desc_el:
                return desc_el.get_text(separator="\n", strip=True)
    except Exception as e:
        log_error(f"Failed to fetch description from {url}: {e}", "Scraper")
    return ""


def _save_jobs_to_db(db: Session, job_list: list, source_label: str) -> int:
    """Save a list of job dicts to the DB. Returns count saved."""
    saved = 0
    for job_info in job_list:
        try:
            company = db.query(Company).filter(Company.name.ilike(job_info["company_name"])).first()
            if not company:
                company = Company(name=job_info["company_name"])
                db.add(company)
                db.commit()
                db.refresh(company)
            add_hash(db, job_info["company_name"], job_info["title"], job_info.get("location", ""), job_info["apply_url"])
            new_job = Job(
                title=job_info["title"],
                company_id=company.id,
                company_name=company.name,
                location=job_info.get("location", "India"),
                description=job_info.get("description", ""),
                experience="0-2 Years",
                skills=None,
                ats_score=None,
                skill_match=None,
                missing_skills=None,
                confidence_score=None,
                priority="Low",
                posted_date=job_info.get("posted_date", datetime.datetime.utcnow()),
                platform=job_info.get("platform", source_label),
                source_type=job_info.get("source_type", "linkedin_jobs"),
                apply_url=job_info["apply_url"],
                recruiter_email=job_info.get("recruiter_email"),
                status="Not Applied"
            )
            db.add(new_job)
            db.commit()
            db.refresh(new_job)
            saved += 1
        except Exception as e:
            db.rollback()
            log_error(f"Failed to save job '{job_info.get('title')}' to DB: {e}", "Scraper")
    return saved


async def run_scraper_pipeline(db: Session) -> list:
    """
    Orchestrates the full scraping pipeline:
    1. LinkedIn Guest Job Search API (last 24hrs)
    2. LinkedIn Post Scraper (startup hiring posts)
    3. Company Career Pages Scraper (~50 Indian companies)
    4. YouTube Hiring Video Description Scraper
    """
    log_info("Starting LinkedIn Guest API search pipeline...", "Scraper")
    all_scraped = []

    # ── SOURCE 1: LinkedIn Guest Job Search ──────────────────────────────────
    candidate_links = []
    seen_urls = set()
    for keyword in JOB_KEYWORDS[:5]:
        jobs = await scrape_linkedin_guest(keyword.strip(), "India")
        for job in jobs:
            if job["apply_url"] not in seen_urls:
                seen_urls.add(job["apply_url"])
                candidate_links.append(job)
    log_info(f"Gathered {len(candidate_links)} unique links from LinkedIn Guest Search.", "Scraper")

    linkedin_jobs = []
    for job_info in candidate_links:
        if is_duplicate(db, job_info["company_name"], job_info["title"], job_info["location"], job_info["apply_url"]):
            continue
        desc = fetch_linkedin_description(job_info["apply_url"])
        if not desc or len(desc.strip()) < 50:
            continue
        desc_lower = desc.lower() + " " + job_info["title"].lower()
        if re.search(r'\b(3|4|5|6|7|8|9|10)\+?\s*(years?|yrs?)\b', desc_lower):
            log_info(f"Skipping job '{job_info['title']}' at '{job_info['company_name']}' - detected mid/senior exp requirement.", "Scraper")
            continue
        job_info["description"] = desc
        job_info["recruiter_email"] = extract_emails_from_text(desc)
        job_info["posted_date"] = datetime.datetime.utcnow()
        linkedin_jobs.append(job_info)
        await asyncio.sleep(1.5)

    saved_linkedin = _save_jobs_to_db(db, linkedin_jobs, "LinkedIn")
    log_info(f"LinkedIn Jobs: {len(linkedin_jobs)} new entry-level jobs found, {saved_linkedin} saved.", "Scraper")
    all_scraped.extend(linkedin_jobs)

    # ── SOURCE 2: LinkedIn Post Scraper ──────────────────────────────────────
    try:
        from scripts.linkedin_post_scraper import scrape_linkedin_posts
        post_jobs = await scrape_linkedin_posts()
        post_jobs_new = [j for j in post_jobs if not is_duplicate(db, j["company_name"], j["title"], j.get("location", ""), j["apply_url"])]
        saved_posts = _save_jobs_to_db(db, post_jobs_new, "LinkedIn Post")
        log_info(f"LinkedIn Posts: {len(post_jobs_new)} new job posts found, {saved_posts} saved.", "Scraper")
        all_scraped.extend(post_jobs_new)
    except Exception as e:
        log_error(f"LinkedIn Post scraper failed: {e}", "Scraper")

    # ── SOURCE 3: Company Career Pages ───────────────────────────────────────
    try:
        from scripts.career_page_scraper import scrape_company_career_pages
        career_jobs = await scrape_company_career_pages()
        career_jobs_new = [j for j in career_jobs if not is_duplicate(db, j["company_name"], j["title"], j.get("location", ""), j["apply_url"])]
        saved_career = _save_jobs_to_db(db, career_jobs_new, "Career Page")
        log_info(f"Career Pages: {len(career_jobs_new)} new fresher jobs found, {saved_career} saved.", "Scraper")
        all_scraped.extend(career_jobs_new)
    except Exception as e:
        log_error(f"Career Page scraper failed: {e}", "Scraper")

    # ── SOURCE 4: YouTube Hiring Video Descriptions ───────────────────────────
    try:
        from scripts.youtube_scraper import scrape_youtube_hiring_videos
        yt_jobs = await scrape_youtube_hiring_videos()
        yt_jobs_new = [j for j in yt_jobs if not is_duplicate(db, j["company_name"], j["title"], j.get("location", ""), j["apply_url"])]
        saved_yt = _save_jobs_to_db(db, yt_jobs_new, "YouTube")
        log_info(f"YouTube: {len(yt_jobs_new)} new hiring opportunities found, {saved_yt} saved.", "Scraper")
        all_scraped.extend(yt_jobs_new)
    except Exception as e:
        log_error(f"YouTube scraper failed: {e}", "Scraper")

    log_info(f"Full scraping pipeline complete. Total new jobs: {len(all_scraped)}", "Scraper")
    return all_scraped


    all_scraped = []

    # ── SOURCE 1: LinkedIn Guest Job Search ──────────────────────────────────
    candidate_links = []
    seen_urls = set()
    for keyword in JOB_KEYWORDS[:5]:
        jobs = await scrape_linkedin_guest(keyword.strip(), "India")
        for job in jobs:
            if job["apply_url"] not in seen_urls:
                seen_urls.add(job["apply_url"])
                candidate_links.append(job)
    log_info(f"Gathered {len(candidate_links)} unique links from LinkedIn Guest Search.", "Scraper")

    # Process LinkedIn job listings
    linkedin_jobs = []
    for job_info in candidate_links:
        if is_duplicate(db, job_info["company_name"], job_info["title"], job_info["location"], job_info["apply_url"]):
            continue
        desc = fetch_linkedin_description(job_info["apply_url"])
        if not desc or len(desc.strip()) < 50:
            continue
        desc_lower = desc.lower() + " " + job_info["title"].lower()
        if re.search(r'\b(3|4|5|6|7|8|9|10)\+?\s*(years?|yrs?)\b', desc_lower):
            log_info(f"Skipping job '{job_info['title']}' at '{job_info['company_name']}' - detected mid/senior exp requirement.", "Scraper")
            continue
        job_info["description"] = desc
        job_info["recruiter_email"] = extract_emails_from_text(desc)
        job_info["posted_date"] = datetime.datetime.utcnow()
        linkedin_jobs.append(job_info)
        await asyncio.sleep(1.5)

    saved_linkedin = _save_jobs_to_db(db, linkedin_jobs, "LinkedIn")
    log_info(f"LinkedIn Jobs: {len(linkedin_jobs)} new entry-level jobs found, {saved_linkedin} saved.", "Scraper")
    all_scraped.extend(linkedin_jobs)

    # ── SOURCE 2: LinkedIn Post Scraper ──────────────────────────────────────
    try:
        from scripts.linkedin_post_scraper import scrape_linkedin_posts
        post_jobs = await scrape_linkedin_posts()
        # Filter duplicates
        post_jobs_new = []
        for job in post_jobs:
            if not is_duplicate(db, job["company_name"], job["title"], job.get("location", ""), job["apply_url"]):
                post_jobs_new.append(job)
        saved_posts = _save_jobs_to_db(db, post_jobs_new, "LinkedIn Post")
        log_info(f"LinkedIn Posts: {len(post_jobs_new)} new job posts found, {saved_posts} saved.", "Scraper")
        all_scraped.extend(post_jobs_new)
    except Exception as e:
        log_error(f"LinkedIn Post scraper failed: {e}", "Scraper")

    # ── SOURCE 3: Company Career Pages ───────────────────────────────────────
    try:
        from scripts.career_page_scraper import scrape_company_career_pages
        career_jobs = await scrape_company_career_pages()
        career_jobs_new = []
        for job in career_jobs:
            if not is_duplicate(db, job["company_name"], job["title"], job.get("location", ""), job["apply_url"]):
                career_jobs_new.append(job)
        saved_career = _save_jobs_to_db(db, career_jobs_new, "Career Page")
        log_info(f"Career Pages: {len(career_jobs_new)} new fresher jobs found, {saved_career} saved.", "Scraper")
        all_scraped.extend(career_jobs_new)
    except Exception as e:
        log_error(f"Career Page scraper failed: {e}", "Scraper")

    log_info(f"Full scraping pipeline complete. Total new jobs: {len(all_scraped)}", "Scraper")
    return all_scraped
