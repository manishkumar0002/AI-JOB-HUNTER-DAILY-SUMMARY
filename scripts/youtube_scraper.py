"""
YouTube Hiring Video Description Scraper
Searches YouTube for hiring/job posts in India and extracts
apply links, emails, and job details from video descriptions.
No API key required — uses YouTube's built-in search JSON.
"""
import re
import json
import time
import requests
import urllib.parse
from scripts.logger import log_info, log_error, log_warning

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
URL_REGEX = re.compile(r'https?://(?:www\.)?(?:linkedin\.com/jobs|indeed\.com|naukri\.com|instahyre\.com|internshala\.com|unstop\.com)[^\s\)\]]+')

# Skip jobs mentioning USA/abroad unless also India
ABROAD_RE = re.compile(r'\b(usa|united states|canada|uk|united kingdom|australia|germany|singapore)\b', re.IGNORECASE)
INDIA_RE = re.compile(r'\b(india|bangalore|bengaluru|pune|hyderabad|chennai|mumbai|noida|gurugram|delhi|kolkata|indore|remote)\b', re.IGNORECASE)

SENIOR_RE = re.compile(r'\b([3-9]|10|\d{2})\+?\s*(years?|yrs?)\s*(of\s+)?experience\b|\bsenior\b|\blead\b|\bstaff\b|\bprincipal\b', re.IGNORECASE)

SEARCH_QUERIES = [
    "hiring java developer freshers india 2025 apply",
    "java full stack fresher job india 2025",
    "software engineer intern hiring india bangalore 2025",
    "hiring 0-2 years experience java developer india",
    "spring boot developer fresher hiring india",
    "associate software engineer hiring india 2025",
    "java developer internship india apply now",
    "entry level software developer india hiring",
]


def _search_youtube(query: str) -> list:
    """
    Searches YouTube for videos matching the query and returns
    a list of video metadata dicts (title, videoId, description snippet).
    Uses YouTube's initial data JSON embedded in the HTML page.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}&sp=EgIIAQ%3D%3D"  # sp=EgIIAQ== = filter: uploaded today
    videos = []
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return []

        # Extract ytInitialData JSON
        match = re.search(r'var ytInitialData\s*=\s*(\{.+?\});\s*</script>', resp.text, re.DOTALL)
        if not match:
            match = re.search(r'ytInitialData\s*=\s*(\{.+?\});', resp.text, re.DOTALL)
        if not match:
            return []

        data = json.loads(match.group(1))

        # Navigate JSON to find video items
        contents = (
            data.get("contents", {})
            .get("twoColumnSearchResultsRenderer", {})
            .get("primaryContents", {})
            .get("sectionListRenderer", {})
            .get("contents", [])
        )

        for section in contents:
            items = section.get("itemSectionRenderer", {}).get("contents", [])
            for item in items:
                vr = item.get("videoRenderer", {})
                if not vr:
                    continue
                video_id = vr.get("videoId", "")
                title = ""
                runs = vr.get("title", {}).get("runs", [])
                if runs:
                    title = runs[0].get("text", "")
                desc_snippet = ""
                for snip in vr.get("detailedMetadataSnippets", []):
                    runs2 = snip.get("snippetText", {}).get("runs", [])
                    desc_snippet += " ".join(r.get("text", "") for r in runs2)

                if video_id and title:
                    videos.append({"video_id": video_id, "title": title, "snippet": desc_snippet})

    except Exception as e:
        log_error(f"YouTube search error for query '{query}': {e}", "YouTubeScraper")
    return videos[:8]  # max 8 per query


def _fetch_video_description(video_id: str) -> str:
    """
    Fetches a YouTube video page and extracts the full description text.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return ""
        # Extract description from ytInitialData
        match = re.search(r'var ytInitialData\s*=\s*(\{.+?\});\s*</script>', resp.text, re.DOTALL)
        if not match:
            return ""
        data = json.loads(match.group(1))
        # Navigate to description
        try:
            desc_runs = (
                data["contents"]["twoColumnWatchNextResults"]["results"]["results"]["contents"][1]
                ["videoSecondaryInfoRenderer"]["attributedDescription"]["content"]
            )
            return desc_runs
        except (KeyError, IndexError, TypeError):
            pass
        # Fallback: grab description snippet from metadata
        try:
            meta = data["microformat"]["playerMicroformatRenderer"]
            return meta.get("description", {}).get("simpleText", "")
        except Exception:
            return ""
    except Exception as e:
        log_error(f"Failed to fetch YT description for {video_id}: {e}", "YouTubeScraper")
        return ""


def _is_india_job(text: str) -> bool:
    """Returns True if the post is for India or remote (not exclusively abroad)."""
    has_abroad = ABROAD_RE.search(text)
    has_india = INDIA_RE.search(text)
    if has_india:
        return True
    if has_abroad and not has_india:
        return False
    return True  # assume India if no location mentioned


def _extract_apply_link(description: str) -> str | None:
    """Extracts only the actual direct job apply URL from description, ignoring social/promo links."""
    all_links = re.findall(r'https?://[^\s\)\]\"\'\>]+', description)
    
    # Filter out social/channel/course promotion links
    filtered_links = []
    social_domains = [
        "youtube.com", "youtu.be", "instagram.com", "facebook.com", "twitter.com", "x.com", 
        "telegram.me", "t.me", "linkedin.com/in/", "linkedin.com/company/", "github.com",
        "whatsapp.com", "chat.whatsapp.com", "play.google.com", "apple.co", "subscribe", 
        "course", "playlist", "tutorial", "skillsagency.com/java-course"
    ]
    for link in all_links:
        link_lower = link.lower()
        if not any(domain in link_lower for domain in social_domains):
            # Clean trailing punctuation
            link = re.sub(r'[.,;:]+$', '', link)
            filtered_links.append(link)

    # Step 1: Look for labeled links line-by-line
    lines = description.split('\n')
    for line in lines:
        line_lower = line.lower()
        if any(w in line_lower for w in ["apply", "register", "registration", "form", "link to", "job link", "apply here"]):
            urls = re.findall(r'https?://[^\s\)\]\"\'\>]+', line)
            for u in urls:
                cleaned_u = re.sub(r'[.,;:]+$', '', u)
                if cleaned_u in filtered_links:
                    return cleaned_u

    # Step 2: Look for high-priority domains (forms.gle, lever, greenhouse, unstop, etc.)
    priority_domains = ["forms.gle", "docs.google.com/forms", "lever.co", "greenhouse.io", 
                        "myworkdayjobs.com", "unstop.com", "internshala.com", "naukri.com", "linkedin.com/jobs"]
    for link in filtered_links:
        link_lower = link.lower()
        if any(domain in link_lower for domain in priority_domains):
            return link

    # Step 3: Look for links with bit.ly, tinyurl, linktr.ee, careers, jobs
    medium_domains = ["bit.ly", "tinyurl.com", "careers", "jobs", "apply", "form"]
    for link in filtered_links:
        link_lower = link.lower()
        if any(domain in link_lower for domain in medium_domains):
            return link

    # Step 4: Return first remaining link if any
    if filtered_links:
        return filtered_links[0]

    return None


def _parse_job_from_description(video: dict, description: str) -> dict | None:
    """
    Parses a YouTube video description into a structured job dict.
    Returns None if not a valid India entry-level job.
    """
    title = video.get("title", "")
    full_text = f"{title}\n{description}"

    if not _is_india_job(full_text):
        return None
    if SENIOR_RE.search(full_text):
        return None

    # Must look like a hiring post
    hiring_keywords = ["hiring", "we are hiring", "job opening", "apply", "fresher", "intern", "opportunity", "vacancy"]
    if not any(kw in full_text.lower() for kw in hiring_keywords):
        return None

    # Extract apply link
    apply_url = _extract_apply_link(description)
    if not apply_url:
        # If no apply link found in description, skip saving it to avoid incorrect URLs
        return None

    # Extract emails
    emails = list(set(EMAIL_REGEX.findall(full_text)))

    # Extract location
    location = "India"
    loc_match = INDIA_RE.search(full_text)
    if loc_match:
        location = loc_match.group(1).title()

    # Job title: try to extract from description, fallback to video title
    job_title = title.strip()
    title_match = re.search(
        r'(?:position|role|title)[:\s]+([A-Za-z ]{5,60}(?:developer|engineer|intern|trainee|analyst|associate))',
        full_text, re.IGNORECASE
    )
    if title_match:
        job_title = title_match.group(1).strip().title()

    # Company name
    company = "Unknown (YouTube)"
    company_match = re.search(r'(?:at|@|company)[:\s]+([A-Za-z0-9 &\-\.]{3,40})', full_text, re.IGNORECASE)
    if company_match:
        c = company_match.group(1).strip()
        if len(c) > 2:
            company = c

    return {
        "title": job_title[:200],
        "company_name": company,
        "location": location,
        "description": full_text[:3000],
        "recruiter_email": ", ".join(emails) if emails else None,
        "apply_url": apply_url,
        "platform": "YouTube",
        "source_type": "youtube",
        "experience": "0-2 Years",
        "posted_date": None,
    }


async def scrape_youtube_hiring_videos() -> list:
    """
    Main entry: searches YouTube for India fresher hiring videos and
    extracts job info from their descriptions.
    """
    log_info("Starting YouTube Hiring Description Scraper...", "YouTubeScraper")
    all_jobs = []
    seen_video_ids = set()

    for query in SEARCH_QUERIES[:5]:  # limit to 5 queries
        videos = _search_youtube(query)
        log_info(f"Found {len(videos)} videos for query: '{query}'", "YouTubeScraper")

        for video in videos:
            vid = video["video_id"]
            if vid in seen_video_ids:
                continue
            seen_video_ids.add(vid)

            # Try to parse from snippet first (faster)
            snippet_job = _parse_job_from_description(video, video.get("snippet", ""))
            if snippet_job and snippet_job.get("recruiter_email"):
                # Good enough from snippet alone
                all_jobs.append(snippet_job)
                continue

            # Fetch full description for better extraction
            desc = _fetch_video_description(vid)
            if desc:
                job = _parse_job_from_description(video, desc)
                if job:
                    all_jobs.append(job)
            time.sleep(1.5)  # polite delay

        time.sleep(3)

    log_info(f"YouTube scraper complete. Found {len(all_jobs)} India hiring opportunities.", "YouTubeScraper")
    return all_jobs
