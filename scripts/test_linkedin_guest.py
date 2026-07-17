import requests
from bs4 import BeautifulSoup
import urllib.parse

keyword = "Java Software Engineer"
location = "India"
# f_TPR=r86400 means past 24 hours
url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={urllib.parse.quote(keyword)}&location={urllib.parse.quote(location)}&f_TPR=r86400&start=0"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9"
}

print(f"Querying LinkedIn Guest API: {url}")
try:
    response = requests.get(url, headers=headers, timeout=20)
    print(f"Status Code: {response.status_code}")
    print(f"Response length: {len(response.text)}")
    
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # LinkedIn Guest Search returns a list of <li> items representing jobs
    items = soup.find_all('li')
    print(f"Found {len(items)} job items in response!")
    
    for item in items[:5]:
        title_el = item.find('h3', class_='base-search-card__title')
        company_el = item.find('h4', class_='base-search-card__subtitle')
        location_el = item.find('span', class_='job-search-card__location')
        link_el = item.find('a', class_='base-card__full-link')
        
        title = title_el.get_text(strip=True) if title_el else "Unknown Title"
        company = company_el.get_text(strip=True) if company_el else "Unknown Company"
        loc = location_el.get_text(strip=True) if location_el else "India"
        link = link_el.get('href') if link_el else None
        
        # Link has query parameters, we can clean it
        if link:
            link = link.split('?')[0]
            
        print(f"\n- Job: {title}\n  Company: {company}\n  Location: {loc}\n  Link: {link}")
        
        # Test description parsing
        if link:
            print("  Fetching description...")
            desc_resp = requests.get(link, headers=headers, timeout=15)
            if desc_resp.status_code == 200:
                desc_soup = BeautifulSoup(desc_resp.text, 'html.parser')
                desc_el = desc_soup.find(class_='show-more-less-html__markup') or desc_soup.find(class_='description__text')
                if desc_el:
                    description = desc_el.get_text(separator="\n", strip=True)
                    print(f"  Description length: {len(description)}")
                    print(f"  First 200 chars of description: {description[:200]}...")
                else:
                    print("  Failed to locate description element in HTML.")
            else:
                print(f"  Failed to fetch description page, status: {desc_resp.status_code}")
        break
        
except Exception as e:
    print(f"Error: {e}")
