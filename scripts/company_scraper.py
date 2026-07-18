import os
import re
import time
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


def _dork_search(board_or_company_name: str, domain_filter: str, query: str, is_board: bool = False) -> list:
    """
    Performs Bing search queries for fresher jobs targeting a specific board or company domain.
    """
    import urllib.parse
    from bs4 import BeautifulSoup
    import requests
    import re
    
    search_url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    }
    
    jobs = []
    SENIOR_FILTER_RE = re.compile(
        r'\b([3-9]|10|\d{2})\+?\s*(years?|yrs?)\b|\bsenior\b|\blead\b|\bstaff\b|\bprincipal\b|\bmanager\b',
        re.IGNORECASE
    )
    try:
        log_info(f"Dorking '{board_or_company_name}' on Bing with query: '{query}'...", "Scraper")
        response = requests.get(search_url, headers=headers, timeout=15)
        if response.status_code != 200:
            return []
            
        soup = BeautifulSoup(response.text, 'html.parser')
        results = soup.find_all('li', class_='b_algo')
        
        seen_urls = set()
        for r in results:
            a = r.find('a')
            if not a:
                continue
            href = a.get('href')
            if href and href.startswith('http') and domain_filter in href:
                href_clean = href.split('?')[0].split('#')[0].strip()
                if href_clean in seen_urls:
                    continue
                seen_urls.add(href_clean)
                
                title_text = a.get_text(separator=" ", strip=True)
                title_lower = title_text.lower()
                
                if SENIOR_FILTER_RE.search(title_lower):
                    continue
                    
                ROLE_NOUNS = ["developer", "engineer", "intern", "trainee", "analyst", "associate", "programmer", "specialist"]
                if not any(noun in title_lower for noun in ROLE_NOUNS):
                    continue
                    
                skip_keywords = ["services", "insights", "expertise", "about", "contact", "news", "press", "media", "blog", 
                                 "solutions", "privacy", "investors"]
                if any(kw in href_clean.lower() or kw in title_lower for kw in skip_keywords):
                    continue
                    
                cleaned_title = title_text.split("Job")[0].split("Recruitment")[0].split("Hiring")[0].strip()
                cleaned_title = re.sub(r'\s*\|\s*.*$', '', cleaned_title)
                if len(cleaned_title) < 5:
                    cleaned_title = "Software Engineer"
                    
                # Resolve final URL to handle redirects
                final_url = href_clean
                try:
                    head_resp = requests.head(href_clean, headers=headers, timeout=8, allow_redirects=True)
                    if head_resp.status_code == 200:
                        final_url = head_resp.url
                except Exception:
                    pass
                    
                if not is_board:
                    company_name = board_or_company_name
                else:
                    company_name = "Various"
                    comp_match = re.search(r'(?:at|@|company|in)[:\s]+([A-Za-z0-9 &\-\.]{3,40})', title_text, re.IGNORECASE)
                    if comp_match:
                        company_name = comp_match.group(1).strip()
                    else:
                        parts = title_text.split(" - ")
                        if len(parts) > 1:
                            company_name = parts[1].strip()
                            
                jobs.append({
                    "title": cleaned_title[:200],
                    "company_name": company_name[:200],
                    "location": "India",
                    "description": f"Discovered on {board_or_company_name} via search engine dorking. Title: {title_text}",
                    "recruiter_email": None,
                    "apply_url": final_url,
                    "platform": board_or_company_name,
                    "source_type": "job_board" if is_board else "career_page",
                    "experience": "0-2 Years",
                })
                
        if not jobs:
            # Fallback scan of all anchors
            anchors = soup.find_all('a')
            for a in anchors:
                href = a.get('href')
                if href and href.startswith('http') and domain_filter in href:
                    href_clean = href.split('?')[0].split('#')[0].strip()
                    if href_clean in seen_urls:
                        continue
                    seen_urls.add(href_clean)
                    
                    title_text = a.get_text(separator=" ", strip=True)
                    title_lower = title_text.lower()
                    
                    if SENIOR_FILTER_RE.search(title_lower):
                        continue
                    ROLE_NOUNS = ["developer", "engineer", "intern", "trainee", "analyst", "associate", "programmer", "specialist"]
                    if not any(noun in title_lower for noun in ROLE_NOUNS):
                        continue
                    skip_keywords = ["services", "insights", "expertise", "about", "contact", "news", "press", "media", "blog", 
                                     "solutions", "privacy", "investors"]
                    if any(kw in href_clean.lower() or kw in title_lower for kw in skip_keywords):
                        continue
                        
                    cleaned_title = title_text.split("Job")[0].split("Recruitment")[0].split("Hiring")[0].strip()
                    cleaned_title = re.sub(r'\s*\|\s*.*$', '', cleaned_title)
                    if len(cleaned_title) < 5:
                        cleaned_title = "Software Engineer"
                        
                    final_url = href_clean
                    try:
                        head_resp = requests.head(href_clean, headers=headers, timeout=8, allow_redirects=True)
                        if head_resp.status_code == 200:
                            final_url = head_resp.url
                    except Exception:
                        pass
                        
                    if not is_board:
                        company_name = board_or_company_name
                    else:
                        company_name = "Various"
                        comp_match = re.search(r'(?:at|@|company|in)[:\s]+([A-Za-z0-9 &\-\.]{3,40})', title_text, re.IGNORECASE)
                        if comp_match:
                            company_name = comp_match.group(1).strip()
                            
                    jobs.append({
                        "title": cleaned_title[:200],
                        "company_name": company_name[:200],
                        "location": "India",
                        "description": f"Discovered on {board_or_company_name} via search engine dorking. Title: {title_text}",
                        "recruiter_email": None,
                        "apply_url": final_url,
                        "platform": board_or_company_name,
                        "source_type": "job_board" if is_board else "career_page",
                        "experience": "0-2 Years",
                    })
    except Exception as e:
        log_error(f"Failed search dorking for {board_or_company_name}: {e}", "Scraper")
        
    return jobs


async def scrape_other_job_boards() -> list:
    """
    Scrapes various job boards (Wellfound, YCombinator, Naukri, Indeed, Instahyre) via search engine dorking on Bing.
    """
    log_info("Starting Other Job Boards dorking scraper...", "Scraper")
    
    queries = [
        {"name": "Naukri", "filter": "naukri.com", "query": 'site:naukri.com "Software Engineer" OR "Developer" "India" "fresher" OR "0-1 year"'},
        {"name": "Indeed", "filter": "indeed.com", "query": 'site:indeed.com/viewjob OR site:indeed.com/rc/clk "Software Engineer" "India" "fresher"'},
        {"name": "Wellfound", "filter": "wellfound.com", "query": 'site:wellfound.com/jobs "Software Engineer" "India" "fresher" OR "0-2 years"'},
        {"name": "YCombinator", "filter": "ycombinator.com", "query": 'site:ycombinator.com/jobs "Software Engineer" "India" "fresher" OR "intern"'},
        {"name": "Instahyre", "filter": "instahyre.com", "query": 'site:instahyre.com/jobs "Software Engineer" "India" "fresher" OR "0-2 years"'}
    ]
    
    all_jobs = []
    seen_urls = set()
    
    for q in queries:
        jobs = _dork_search(q["name"], q["filter"], q["query"], is_board=True)
        for job in jobs:
            apply_url = job["apply_url"]
            if apply_url not in seen_urls:
                seen_urls.add(apply_url)
                all_jobs.append(job)
        time.sleep(2)
        
    log_info(f"Other Job Boards scraper complete. Found {len(all_jobs)} jobs.", "Scraper")
    return all_jobs


async def run_linkedin_jobs_pipeline(db: Session) -> list:
    log_info("Starting LinkedIn Jobs scraping pipeline...", "Scraper")
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

    saved = _save_jobs_to_db(db, linkedin_jobs, "LinkedIn")
    log_info(f"LinkedIn Jobs complete. Saved {saved} new jobs.", "Scraper")
    return linkedin_jobs


async def run_linkedin_posts_pipeline(db: Session) -> list:
    log_info("Starting LinkedIn Posts scraping pipeline...", "Scraper")
    try:
        from scripts.linkedin_post_scraper import scrape_linkedin_posts
        post_jobs = await scrape_linkedin_posts()
        post_jobs_new = [j for j in post_jobs if not is_duplicate(db, j["company_name"], j["title"], j.get("location", ""), j["apply_url"])]
        saved = _save_jobs_to_db(db, post_jobs_new, "LinkedIn Post")
        log_info(f"LinkedIn Posts complete. Saved {saved} new jobs.", "Scraper")
        return post_jobs_new
    except Exception as e:
        log_error(f"LinkedIn Post scraper failed: {e}", "Scraper")
        return []


async def run_youtube_pipeline(db: Session) -> list:
    log_info("Starting YouTube scraping pipeline...", "Scraper")
    try:
        from scripts.youtube_scraper import scrape_youtube_hiring_videos
        yt_jobs = await scrape_youtube_hiring_videos()
        yt_jobs_new = [j for j in yt_jobs if not is_duplicate(db, j["company_name"], j["title"], j.get("location", ""), j["apply_url"])]
        saved = _save_jobs_to_db(db, yt_jobs_new, "YouTube")
        log_info(f"YouTube complete. Saved {saved} new jobs.", "Scraper")
        return yt_jobs_new
    except Exception as e:
        log_error(f"YouTube scraper failed: {e}", "Scraper")
        return []


async def run_google_companies_pipeline(db: Session) -> list:
    log_info("Starting Google Company Search scraping pipeline...", "Scraper")
    try:
        from scripts.career_page_scraper import scrape_google_company_jobs
        google_jobs = await scrape_google_company_jobs()
        google_jobs_new = [j for j in google_jobs if not is_duplicate(db, j["company_name"], j["title"], j.get("location", ""), j["apply_url"])]
        saved = _save_jobs_to_db(db, google_jobs_new, "Google Search")
        log_info(f"Google Company Search complete. Saved {saved} new jobs.", "Scraper")
        return google_jobs_new
    except Exception as e:
        log_error(f"Google Company Search scraper failed: {e}", "Scraper")
        return []


async def run_other_boards_pipeline(db: Session) -> list:
    log_info("Starting Other Job Boards scraping pipeline...", "Scraper")
    try:
        other_jobs = await scrape_other_job_boards()
        other_jobs_new = [j for j in other_jobs if not is_duplicate(db, j["company_name"], j["title"], j.get("location", ""), j["apply_url"])]
        saved = _save_jobs_to_db(db, other_jobs_new, "Job Board")
        log_info(f"Other Job Boards complete. Saved {saved} new jobs.", "Scraper")
        return other_jobs_new
    except Exception as e:
        log_error(f"Other Job Boards scraper failed: {e}", "Scraper")
        return []


async def run_scraper_pipeline(db: Session) -> list:
    """
    Orchestrates the full scraping pipeline sequentially to coordinate runs.
    """
    log_info("Running full coordinated scraping pipeline sequentially...", "Scraper")
    all_jobs = []
    
    all_jobs.extend(await run_linkedin_jobs_pipeline(db))
    all_jobs.extend(await run_linkedin_posts_pipeline(db))
    all_jobs.extend(await run_google_companies_pipeline(db))
    all_jobs.extend(await run_youtube_pipeline(db))
    all_jobs.extend(await run_other_boards_pipeline(db))
    
    return all_jobs

