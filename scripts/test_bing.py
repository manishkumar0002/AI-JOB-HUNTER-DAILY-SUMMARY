import requests
from bs4 import BeautifulSoup
import urllib.parse

query = 'site:linkedin.com inurl:posts "hiring" AND ("Java" OR "Full Stack" OR "Software Engineer") AND ("fresher" OR "intern" OR "0-2 years") AND "India"'
search_url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
}

print(f"Querying: {search_url}")
try:
    response = requests.get(search_url, headers=headers, timeout=20)
    print(f"Status Code: {response.status_code}")
    print(f"Response length: {len(response.text)}")
    
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Print page title
    print(f"Page Title: {soup.title.string if soup.title else 'No Title'}")
    
    anchors2 = soup.find_all('a')
    li_links = []
    for a in anchors2:
        href = a.get('href')
        if href and 'linkedin.com' in href:
            li_links.append(href)
    print(f"Found {len(li_links)} LinkedIn links:")
    for link in li_links:
        print(f" - {link}")
    
except Exception as e:
    print(f"Error: {e}")
