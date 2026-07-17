import requests
from bs4 import BeautifulSoup
import urllib.parse

query = 'site:greenhouse.io "Backend Developer" "India"'
search_url = f"https://lite.duckduckgo.com/lite/?q={urllib.parse.quote(query)}"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
}

print(f"Querying DuckDuckGo Lite: {search_url}")
try:
    response = requests.get(search_url, headers=headers, timeout=20)
    print(f"Status Code: {response.status_code}")
    print(f"Response length: {len(response.text)}")
    
    soup = BeautifulSoup(response.text, 'html.parser')
    print(f"Title: {soup.title.string if soup.title else 'No Title'}")
    
    # In DDG Lite, results are inside table rows. We look for external links
    anchors = soup.find_all('a')
    external_links = []
    for a in anchors:
        href = a.get('href')
        if href and href.startswith('http') and 'duckduckgo' not in href and 'google' not in href:
            external_links.append(href)
            
    print(f"Found {len(external_links)} external links:")
    for link in external_links[:10]:
        print(f" - {link}")
        
except Exception as e:
    print(f"Error: {e}")
