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


known_companies = [
    "Google", "Microsoft", "Amazon", "Adobe", "Oracle", "SAP", "IBM", "Infosys", "TCS", "Accenture", 
    "Capgemini", "Cognizant", "L&T", "Mphasis", "Hexaware", "Persistent", "Zensar", "Razorpay", 
    "Freshworks", "Zoho", "PhonePe", "Swiggy", "Zomato", "CRED", "Groww", "Meesho", "BrowserStack", 
    "Postman", "Chargebee", "Juspay", "Lenskart", "Slice", "Open Financial", "Darwinbox", "MoEngage", 
    "CleverTap", "Whatfix", "Exotel", "RazorThink", "Haptik", "Ola", "Rapido", "Zendesk", 
    "ThoughtWorks", "Cummins", "Amdocs", "ITC Infotech", "Medi-Tech", "MakeMyTrip", "Nagarro", 
    "KPIT", "Cyient", "Mastercard", "NVIDIA", "Intel", "Qualcomm", "Cisco", "VMware", "Atlassian"
]


def _parse_jobs_from_description(video: dict, description: str) -> list:
    """
    Parses a YouTube video description and extracts ALL external job links.
    For each link, resolves the matching company and job title from surrounding lines.
    """
    title = video.get("title", "")
    full_text = f"{title}\n{description}"

    if not _is_india_job(full_text):
        return []

    # Find all URLs in description
    all_urls = re.findall(r'https?://[^\s\)\]\"\'\>]+', description)

    # Filter out social/channel/course promotion links
    social_domains = [
        "youtube.com", "youtu.be", "instagram.com", "facebook.com", "twitter.com", "x.com", 
        "telegram.me", "t.me", "linkedin.com/in/", "linkedin.com/company/", "github.com",
        "whatsapp.com", "chat.whatsapp.com", "play.google.com", "apple.co", "subscribe", 
        "course", "playlist", "tutorial", "skillsagency.com/java-course"
    ]

    unique_urls = []
    for url in all_urls:
        url_clean = re.sub(r'[.,;:]+$', '', url)
        url_lower = url_clean.lower()
        if not any(domain in url_lower for domain in social_domains):
            if url_clean not in unique_urls:
                unique_urls.append(url_clean)

    if not unique_urls:
        return []

    # Extract emails
    emails = list(set(EMAIL_REGEX.findall(full_text)))
    recruiter_email = ", ".join(emails) if emails else None

    jobs = []
    lines = description.split('\n')

    for url in unique_urls:
        # Find the line containing this URL
        line_idx = -1
        for idx, line in enumerate(lines):
            if url in line:
                line_idx = idx
                break

        context_lines = []
        if line_idx != -1:
            if line_idx > 0:
                context_lines.append(lines[line_idx - 1])
            context_lines.append(lines[line_idx])

        context_text = " ".join(context_lines)

        # Exclude senior roles based on context text
        if SENIOR_RE.search(context_text):
            continue

        # 1. Determine company name
        company = None
        for kc in known_companies:
            if re.search(rf'\b{re.escape(kc)}\b', context_text, re.IGNORECASE):
                company = kc
                break

        if not company and line_idx != -1:
            current_line = lines[line_idx]
            match = re.search(
                r'^\s*(?:\d+[\.\-\)]\s*)?([A-Za-z0-9\s&]+?)(?:\s*(?:apply|link|registration|form|sde|role|hiring|job|careers?|recruitment|here))*\s*[:\-–—]\s*https?', 
                current_line, re.IGNORECASE
            )
            if match:
                c_cand = match.group(1).strip()
                c_cand = re.sub(r'^\s*[\*\-#•]+\s*', '', c_cand)
                if len(c_cand) > 2 and len(c_cand) < 40 and not any(w in c_cand.lower() for w in ["apply", "link", "click"]):
                    company = c_cand

        if not company:
            title_company_match = re.search(r'(?:at|@|company)[:\s]+([A-Za-z0-9 &\-\.]{3,40})', title, re.IGNORECASE)
            if title_company_match:
                company = title_company_match.group(1).strip()
            else:
                company = "Various (YouTube)"

        # 2. Determine job title
        job_title = None
        title_match = re.search(
            r'([A-Za-z ]{5,60}(?:developer|engineer|intern|trainee|analyst|associate))',
            context_text, re.IGNORECASE
        )
        if title_match:
            job_title = title_match.group(1).strip().title()
        else:
            job_title = "Software Engineer"

        # 3. Determine location
        location = "India"
        loc_match = INDIA_RE.search(context_text + " " + title)
        if loc_match:
            location = loc_match.group(1).title()

        jobs.append({
            "title": job_title[:200],
            "company_name": company,
            "location": location,
            "description": f"Extracted from YouTube Video: {title}\n\nContext lines:\n{context_text[:1000]}",
            "recruiter_email": recruiter_email,
            "apply_url": url,
            "platform": "YouTube",
            "source_type": "youtube",
            "experience": "0-2 Years",
            "posted_date": None,
        })

    return jobs


async def scrape_youtube_hiring_videos() -> list:
    """
    Main entry: searches YouTube for India fresher hiring videos and
    extracts ALL job apply links from their descriptions.
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
            snippet_jobs = _parse_jobs_from_description(video, video.get("snippet", ""))
            if snippet_jobs and any(j.get("recruiter_email") for j in snippet_jobs):
                all_jobs.extend(snippet_jobs)
                continue

            # Fetch full description for better extraction
            desc = _fetch_video_description(vid)
            if desc:
                jobs = _parse_jobs_from_description(video, desc)
                all_jobs.extend(jobs)
            time.sleep(1.5)  # polite delay

        time.sleep(3)

    log_info(f"YouTube scraper complete. Found {len(all_jobs)} India hiring opportunities.", "YouTubeScraper")
    return all_jobs

