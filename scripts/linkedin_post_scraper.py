import re
import time
import urllib.parse
import requests
from bs4 import BeautifulSoup
from scripts.logger import log_info, log_error, log_warning

# LinkedIn post search keywords targeting fresher job posts
POST_KEYWORDS = [
    "hiring fresher java developer india",
    "we are hiring 0-2 years experience software engineer india",
    "job opening fresher software engineer bangalore",
    "associate software engineer hiring india",
    "graduate trainee developer india hiring",
    "intern software developer india apply",
    "java full stack fresher hiring india",
    "entry level software engineer india opening",
]

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

# Patterns to detect a post is about hiring/jobs
HIRING_PATTERNS = [
    r'\bhiring\b', r'\bwe.?re.hiring\b', r'\bjob.opening\b', r'\bopen.position\b',
    r'\bjoin.our.team\b', r'\bapply.now\b', r'\bwe.are.looking\b', r'\bopportunity\b',
    r'\bapplications.open\b', r'\bexciting.opportunity\b', r'\bcareers\b',
    r'\brecruiting\b', r'\bfresher\b', r'\binternship\b', r'\bgraduate.trainee\b',
]
HIRING_RE = re.compile('|'.join(HIRING_PATTERNS), re.IGNORECASE)

# Experience level filters — skip if clearly senior
SENIOR_RE = re.compile(
    r'\b(5|6|7|8|9|10)\+?\s*(years?|yrs?)\b|\bsenior\b|\bstaff\b|\bprincipal\b|\blead\b|\bmanager\b',
    re.IGNORECASE
)

def _scrape_linkedin_posts_for_keyword(keyword: str) -> list:
    """
    Uses LinkedIn Guest content search to fetch posts matching the keyword.
    Returns list of raw post dicts with text, author, and any links found.
    """
    posts = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    encoded_kw = urllib.parse.quote(keyword)
    # Use LinkedIn public search (posts/updates tab)
    url = f"https://www.linkedin.com/search/results/content/?keywords={encoded_kw}&origin=SWITCH_SEARCH_VERTICAL&sortBy=date_posted"
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        if resp.status_code != 200:
            log_warning(f"LinkedIn Posts search returned {resp.status_code} for '{keyword}'", "PostScraper")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")

        # Attempt to find post containers
        post_containers = soup.find_all("div", class_=re.compile(r'(feed-shared-update|search-content|update-components)'))
        if not post_containers:
            # fallback: grab all paragraph-style text blocks
            post_containers = soup.find_all("p")

        for container in post_containers[:15]:
            text = container.get_text(separator=" ", strip=True)
            if len(text) < 60:
                continue
            if HIRING_RE.search(text):
                emails = list(set(EMAIL_REGEX.findall(text)))
                # Find any URLs in the container
                links = [a.get("href") for a in container.find_all("a", href=True) if "linkedin.com/jobs" in a.get("href", "") or "apply" in a.get("href", "").lower()]
                posts.append({
                    "text": text[:2000],
                    "recruiter_email": ", ".join(emails) if emails else None,
                    "apply_url": links[0] if links else None,
                    "keyword": keyword,
                })
    except Exception as e:
        log_error(f"LinkedIn post scraper exception for '{keyword}': {e}", "PostScraper")
    return posts


def _extract_job_info_from_post(post: dict) -> dict | None:
    """
    Parse a raw LinkedIn post dict into a structured job dict.
    Returns None if the post doesn't look like a job opening.
    """
    text = post.get("text", "")

    # Skip if mentions senior/high experience requirement
    if SENIOR_RE.search(text):
        return None

    # Try to extract job title
    title = None
    title_patterns = [
        r'(?:hiring|looking for|opening for|position[:\s]+|role[:\s]+)\s*[:\-]?\s*([A-Za-z ]{5,50}(?:developer|engineer|intern|trainee|analyst|associate))',
        r'([A-Za-z ]{3,40}(?:developer|engineer|intern|trainee|analyst|associate))\s*(?:position|role|opening|vacancy)',
    ]
    for pat in title_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            title = m.group(1).strip().title()
            break

    if not title:
        title = "Software Engineer / Developer (LinkedIn Post)"

    # Try to extract location
    location = "India"
    location_patterns = [
        r'\b(bangalore|bengaluru|pune|mumbai|hyderabad|chennai|noida|gurugram|gurgaon|kolkata|indore|delhi|remote)\b'
    ]
    for pat in location_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            location = m.group(1).title()
            break

    # Extract company from "at <Company>" or "@<Company>"
    company = "Unknown (LinkedIn Post)"
    company_patterns = [
        r'@([A-Za-z0-9 &\-\.]{3,40})',
        r'\bat\s+([A-Za-z0-9 &\-\.]{3,40})\b',
    ]
    for pat in company_patterns:
        m = re.search(pat, text)
        if m:
            candidate = m.group(1).strip()
            if len(candidate) > 2 and candidate.lower() not in ("us", "our", "the", "a", "an"):
                company = candidate
                break

    return {
        "title": title,
        "company_name": company,
        "location": location,
        "description": text,
        "recruiter_email": post.get("recruiter_email"),
        "apply_url": post.get("apply_url") or f"https://www.linkedin.com/search/results/content/?keywords={urllib.parse.quote(post.get('keyword','hiring'))}&sortBy=date_posted",
        "platform": "LinkedIn Post",
        "source_type": "linkedin_post",
        "experience": "0-2 Years",
    }


async def scrape_linkedin_posts() -> list:
    """
    Main entry point: scrape LinkedIn posts for fresher job opportunities.
    Returns list of structured job dicts ready to insert into DB.
    """
    log_info("Starting LinkedIn Posts scraper...", "PostScraper")
    all_jobs = []
    seen_companies = set()

    for keyword in POST_KEYWORDS[:6]:  # limit to avoid rate limiting
        posts = _scrape_linkedin_posts_for_keyword(keyword)
        log_info(f"Found {len(posts)} hiring posts for keyword: '{keyword}'", "PostScraper")
        for post in posts:
            job = _extract_job_info_from_post(post)
            if job:
                # Deduplicate by company+title combo
                key = f"{job['company_name'].lower()}_{job['title'].lower()[:20]}"
                if key not in seen_companies:
                    seen_companies.add(key)
                    all_jobs.append(job)
        time.sleep(3)  # polite delay between keyword queries

    log_info(f"LinkedIn Posts scraper complete. Found {len(all_jobs)} job posts.", "PostScraper")
    return all_jobs
