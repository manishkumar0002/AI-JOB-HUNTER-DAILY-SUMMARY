import re
import time
import requests
from bs4 import BeautifulSoup
from scripts.logger import log_info, log_error, log_warning

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

# Fresher/entry-level filter keywords
FRESHER_KEYWORDS = [
    'fresher', 'freshers', '0-2 years', '0-1 year', '0 - 2', '0 to 2',
    'graduate trainee', 'graduate engineer trainee', 'get ', 'junior',
    'entry level', 'entry-level', 'associate engineer', 'associate developer',
    'intern', 'internship', 'trainee', 'campus hire', 'campus recruitment',
    'no experience required', 'recent graduate',
]

# Patterns that indicate senior roles — skip these
SENIOR_RE = re.compile(
    r'\b([3-9]|10|\d{2})\+?\s*(years?|yrs?)\s*(of\s+)?experience\b|\bsenior\b|\bstaff\b|\bprincipal\b|\blead\b',
    re.IGNORECASE
)

# Indian tech company career pages — curated list
COMPANY_CAREER_PAGES = [
    # Tier 1 — Large Indian IT
    {"company": "Infosys", "url": "https://www.infosys.com/careers/apply.html", "location": "Pan India"},
    {"company": "TCS", "url": "https://ibegin.tcs.com/iBegin/", "location": "Pan India"},
    {"company": "Wipro", "url": "https://careers.wipro.com/careers-home/jobs", "location": "Pan India"},
    {"company": "HCL Technologies", "url": "https://www.hcltech.com/careers", "location": "Pan India"},
    {"company": "Tech Mahindra", "url": "https://careers.techmahindra.com/", "location": "Pan India"},
    {"company": "Cognizant", "url": "https://careers.cognizant.com/global/en/india-jobs", "location": "Pan India"},
    {"company": "Capgemini India", "url": "https://www.capgemini.com/in-en/careers/", "location": "Pan India"},
    {"company": "L&T Technology Services", "url": "https://www.ltts.com/careers", "location": "Pan India"},
    {"company": "Mphasis", "url": "https://careers.mphasis.com/", "location": "Pan India"},
    {"company": "Hexaware", "url": "https://hexaware.com/careers/", "location": "Pan India"},
    {"company": "Persistent Systems", "url": "https://www.persistent.com/careers/", "location": "Pune"},
    {"company": "Zensar Technologies", "url": "https://www.zensar.com/careers", "location": "Pune"},

    # Product / MNC India offices
    {"company": "SAP India", "url": "https://www.sap.com/india/about/careers.html", "location": "Bengaluru/Pune"},
    {"company": "Oracle India", "url": "https://www.oracle.com/in/corporate/careers/", "location": "Bengaluru/Hyderabad"},
    {"company": "Adobe India", "url": "https://www.adobe.com/careers/india.html", "location": "Bengaluru/Noida"},

    # Startups / New-age companies — Bengaluru
    {"company": "Razorpay", "url": "https://razorpay.com/jobs/", "location": "Bengaluru"},
    {"company": "Freshworks", "url": "https://www.freshworks.com/company/careers/", "location": "Bengaluru/Chennai"},
    {"company": "Zoho", "url": "https://www.zoho.com/careers.html", "location": "Chennai/Bengaluru"},
    {"company": "PhonePe", "url": "https://www.phonepe.com/en/careers.html", "location": "Bengaluru"},
    {"company": "Swiggy", "url": "https://careers.swiggy.com/", "location": "Bengaluru"},
    {"company": "Zomato", "url": "https://www.zomato.com/careers", "location": "Gurugram"},
    {"company": "CRED", "url": "https://careers.cred.club/", "location": "Bengaluru"},
    {"company": "Groww", "url": "https://groww.in/careers", "location": "Bengaluru"},
    {"company": "Meesho", "url": "https://meesho.io/careers", "location": "Bengaluru"},
    {"company": "BrowserStack", "url": "https://www.browserstack.com/careers", "location": "Mumbai/Bengaluru"},
    {"company": "Postman", "url": "https://www.postman.com/company/careers/", "location": "Bengaluru"},
    {"company": "Chargebee", "url": "https://www.chargebee.com/careers/", "location": "Chennai/Bengaluru"},
    {"company": "Juspay", "url": "https://juspay.in/careers", "location": "Bengaluru"},
    {"company": "Lenskart", "url": "https://www.lenskart.com/careers.html", "location": "Noida/Bengaluru"},
    {"company": "Slice", "url": "https://www.sliceit.com/careers", "location": "Bengaluru"},
    {"company": "Open Financial", "url": "https://open.money/careers", "location": "Bengaluru"},
    {"company": "Darwinbox", "url": "https://darwinbox.com/about-us/careers", "location": "Hyderabad"},
    {"company": "MoEngage", "url": "https://www.moengage.com/company/careers/", "location": "Bengaluru"},
    {"company": "CleverTap", "url": "https://clevertap.com/careers/", "location": "Mumbai"},
    {"company": "Whatfix", "url": "https://whatfix.com/about/careers/", "location": "Bengaluru"},
    {"company": "Exotel", "url": "https://exotel.com/careers/", "location": "Bengaluru"},
    {"company": "RazorThink", "url": "https://razorthink.com/careers/", "location": "Bengaluru"},
    {"company": "Haptik", "url": "https://www.haptik.ai/careers", "location": "Mumbai"},
    {"company": "Ola", "url": "https://www.olacabs.com/webview/careersNew", "location": "Bengaluru"},
    {"company": "Rapido", "url": "https://rapido.bike/careers", "location": "Bengaluru"},

    # Pune/Indore specific
    {"company": "Zendesk India", "url": "https://www.zendesk.com/jobs/", "location": "Pune"},
    {"company": "ThoughtWorks", "url": "https://www.thoughtworks.com/en-in/careers", "location": "Pune/Bengaluru"},
    {"company": "Cummins India", "url": "https://www.cummins.com/careers", "location": "Pune"},
    {"company": "Amdocs", "url": "https://www.amdocs.com/careers", "location": "Pune"},

    # Kolkata
    {"company": "ITC Infotech", "url": "https://www.itcinfotech.com/careers/", "location": "Kolkata"},
    {"company": "Wipro Kolkata", "url": "https://careers.wipro.com/careers-home/jobs?location=Kolkata", "location": "Kolkata"},

    # More Indore-based
    {"company": "Medi-Tech India", "url": "https://www.meditech.com/careers/", "location": "Indore"},
    {"company": "MakeMyTrip", "url": "https://careers.makemytrip.com/", "location": "Gurugram"},
    {"company": "Nagarro", "url": "https://www.nagarro.com/en/careers", "location": "Pan India"},
    {"company": "KPIT Technologies", "url": "https://www.kpit.com/careers/", "location": "Pune"},
    {"company": "Cyient", "url": "https://www.cyient.com/careers", "location": "Hyderabad"},
]


def _is_fresher_job(text: str, title: str = "") -> bool:
    """Check if this job listing mentions fresher/entry-level requirements."""
    combined = (text + " " + title).lower()
    for kw in FRESHER_KEYWORDS:
        if kw.lower() in combined:
            return True
    return False


def _scrape_career_page(company_info: dict) -> list:
    """
    Fetches a company's career page and extracts fresher job listings.
    Returns list of job dicts.
    """
    jobs = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }
    company = company_info["company"]
    url = company_info["url"]
    location = company_info.get("location", "India")

    try:
        resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        if resp.status_code not in (200, 301, 302):
            log_warning(f"Career page {url} returned {resp.status_code}", "CareerScraper")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        page_text = soup.get_text(separator=" ", strip=True).lower()

        # Check page has fresher/entry level content at all
        has_fresher_content = any(kw in page_text for kw in FRESHER_KEYWORDS)
        if not has_fresher_content:
            # Still try to scan job links even if not explicitly "fresher"
            pass

        # Try to find job listing elements — common patterns
        found_links = soup.find_all("a", href=True)
        for link in found_links:
            href = link.get("href", "").strip()
            text = link.get_text(separator=" ", strip=True)

            if len(text) < 5 or len(text) > 150:
                continue

            text_lower = text.lower()
            href_lower = href.lower()

            # Skip common generic subpaths/words
            skip_keywords = ["services", "insights", "expertise", "about", "contact", "news", "press", "media", "blog", 
                             "industries", "capabilities", "solutions", "partners", "events", "resources", "investors", 
                             "history", "culture", "overview", "team", "board", "client", "case-study", "privacy"]
            if any(kw in text_lower or kw in href_lower for kw in skip_keywords):
                continue

            # Check if this looks like a specific job role (not a general category)
            # Real junior job titles contain developer, engineer, intern, trainee, analyst, associate, programmer
            ROLE_NOUNS = ["developer", "engineer", "intern", "trainee", "analyst", "associate", "programmer", "specialist"]
            is_job_role = any(noun in text_lower for noun in ROLE_NOUNS)
            
            # The URL itself should look like a job listing page (not just the main career page)
            is_job_url = any(kw in href_lower for kw in ["job", "career", "opening", "position", "apply", "vacancy", "recruit"])

            if not (is_job_role and is_job_url):
                continue

            # Filter senior roles
            if SENIOR_RE.search(text):
                continue

            # Build absolute URL
            if href.startswith("http"):
                apply_url = href
            elif href.startswith("/"):
                from urllib.parse import urlparse
                parsed = urlparse(url)
                apply_url = f"{parsed.scheme}://{parsed.netloc}{href}"
            else:
                continue

            # Extract emails from surrounding context
            parent = link.parent
            parent_text = parent.get_text(separator=" ", strip=True) if parent else text
            emails = list(set(EMAIL_REGEX.findall(parent_text)))

            # Detect if fresher-relevant
            if _is_fresher_job(parent_text, text):
                jobs.append({
                    "title": text.strip().title(),
                    "company_name": company,
                    "location": location,
                    "description": parent_text[:1500] if len(parent_text) > 50 else f"Job opening at {company}. Visit: {apply_url}",
                    "recruiter_email": ", ".join(emails) if emails else None,
                    "apply_url": apply_url,
                    "platform": "Career Page",
                    "source_type": "career_page",
                    "experience": "0-2 Years",
                })

    except requests.exceptions.Timeout:
        log_warning(f"Timeout fetching career page for {company}: {url}", "CareerScraper")
    except Exception as e:
        log_error(f"Career page scraper error for {company}: {e}", "CareerScraper")

    return jobs


async def scrape_company_career_pages() -> list:
    """
    Main entry point: scrape all company career pages in the list.
    Returns deduplicated list of structured job dicts.
    """
    log_info(f"Starting Company Career Pages scraper ({len(COMPANY_CAREER_PAGES)} companies)...", "CareerScraper")
    all_jobs = []
    seen_urls = set()

    for company_info in COMPANY_CAREER_PAGES:
        log_info(f"Scraping career page: {company_info['company']} — {company_info['url']}", "CareerScraper")
        jobs = _scrape_career_page(company_info)

        for job in jobs:
            url = job.get("apply_url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_jobs.append(job)

        # Polite delay
        time.sleep(2)

    log_info(f"Career Pages scraper complete. Found {len(all_jobs)} job listings.", "CareerScraper")
    return all_jobs


def _dork_company_search(company_name: str, domain: str) -> list:
    """
    Performs a Bing search for fresher jobs at a specific company domain.
    """
    import urllib.parse
    
    # Clean domain
    base_domain = domain
    if domain.startswith("www."):
        base_domain = domain[4:]
        
    query = f'site:{base_domain} "Software" OR "Developer" OR "Engineer" AND ("fresher" OR "0-2 years" OR "Graduate" OR "Trainee" OR "Intern") AND "India"'
    search_url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    }
    
    jobs = []
    try:
        log_info(f"Dorking company '{company_name}' on domain '{base_domain}'...", "CareerScraper")
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
            if href and href.startswith('http') and base_domain in href:
                href_clean = href.split('?')[0].split('#')[0].strip()
                if href_clean in seen_urls:
                    continue
                seen_urls.add(href_clean)
                
                title_text = a.get_text(separator=" ", strip=True)
                title_lower = title_text.lower()
                
                if SENIOR_RE.search(title_lower):
                    continue
                    
                ROLE_NOUNS = ["developer", "engineer", "intern", "trainee", "analyst", "associate", "programmer", "specialist"]
                if not any(noun in title_lower for noun in ROLE_NOUNS):
                    continue
                    
                skip_keywords = ["services", "insights", "expertise", "about", "contact", "news", "press", "media", "blog", 
                                 "solutions", "privacy", "investors"]
                if any(kw in href_clean.lower() or kw in title_lower for kw in skip_keywords):
                    continue
                
                # Resolve link
                try:
                    head_resp = requests.head(href_clean, headers=headers, timeout=8, allow_redirects=True)
                    if head_resp.status_code == 200:
                        final_url = head_resp.url
                    else:
                        final_url = href_clean
                except Exception:
                    final_url = href_clean
                        
                jobs.append({
                    "title": title_text.strip().title() if len(title_text) > 5 else "Software Engineer",
                    "company_name": company_name,
                    "location": "India",
                    "description": f"Discovered via search engine query for {company_name} fresher jobs. Title: {title_text}",
                    "recruiter_email": None,
                    "apply_url": final_url,
                    "platform": "Google Search",
                    "source_type": "career_page",
                    "experience": "0-2 Years",
                })
                
        if not jobs:
            # Fallback scan of all anchors
            anchors = soup.find_all('a')
            for a in anchors:
                href = a.get('href')
                if href and href.startswith('http') and base_domain in href:
                    href_clean = href.split('?')[0].split('#')[0].strip()
                    if href_clean in seen_urls:
                        continue
                    seen_urls.add(href_clean)
                    
                    title_text = a.get_text(separator=" ", strip=True)
                    title_lower = title_text.lower()
                    
                    if SENIOR_RE.search(title_lower):
                        continue
                    ROLE_NOUNS = ["developer", "engineer", "intern", "trainee", "analyst", "associate", "programmer", "specialist"]
                    if not any(noun in title_lower for noun in ROLE_NOUNS):
                        continue
                    skip_keywords = ["services", "insights", "expertise", "about", "contact", "news", "press", "media", "blog", 
                                     "solutions", "privacy", "investors"]
                    if any(kw in href_clean.lower() or kw in title_lower for kw in skip_keywords):
                        continue
                        
                    final_url = href_clean
                    try:
                        head_resp = requests.head(href_clean, headers=headers, timeout=8, allow_redirects=True)
                        if head_resp.status_code == 200:
                            final_url = head_resp.url
                    except Exception:
                        pass
                        
                    jobs.append({
                        "title": title_text.strip().title() if len(title_text) > 5 else "Software Engineer",
                        "company_name": company_name,
                        "location": "India",
                        "description": f"Discovered via search engine query for {company_name} fresher jobs. Title: {title_text}",
                        "recruiter_email": None,
                        "apply_url": final_url,
                        "platform": "Google Search",
                        "source_type": "career_page",
                        "experience": "0-2 Years",
                    })
    except Exception as e:
        log_error(f"Failed search dorking for {company_name}: {e}", "CareerScraper")
        
    return jobs


async def scrape_google_company_jobs() -> list:
    """
    Main entry point: dork search engines for SDE fresher positions at each company.
    """
    from urllib.parse import urlparse
    log_info("Starting Google/Bing company dorking scraper...", "CareerScraper")
    all_jobs = []
    seen_urls = set()
    
    # Query up to 15 companies per run to avoid search engine blockages
    # Using a subset or checking list
    for company_info in COMPANY_CAREER_PAGES[:25]:
        company_name = company_info["company"]
        url = company_info["url"]
        
        parsed = urlparse(url)
        domain = parsed.netloc
        if not domain:
            continue
            
        jobs = _dork_company_search(company_name, domain)
        for job in jobs:
            apply_url = job["apply_url"]
            if apply_url not in seen_urls:
                seen_urls.add(apply_url)
                all_jobs.append(job)
                
        time.sleep(2.5)
        
    log_info(f"Google/Bing company dorking complete. Found {len(all_jobs)} jobs.", "CareerScraper")
    return all_jobs
