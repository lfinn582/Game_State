from curl_cffi import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import random
import os

# --- CONFIGURATION ---
url = "https://fbref.com/en/comps/11/2021-2022/schedule/2021-2022-Serie-A-Scores-and-Fixtures"
output_file = 'SeriaA/SerieA_links_2022.csv'

# Ensure the directory exists so it doesn't error out
os.makedirs(os.path.dirname(output_file), exist_ok=True)

def scrape_with_retry(url, max_retries=3):
    """Tries to scrape a URL, pauses and retries if blocked."""
    for attempt in range(max_retries):
        try:
            print(f"Fetching (Attempt {attempt+1}): {url}")
            # Safari impersonation is good for bypassing basic TLS fingerprinting
            response = requests.get(url, impersonate="safari15_3", timeout=20)
            
            if response.status_code == 200:
                return response
            elif response.status_code in [403, 429]:
                wait_time = 60 + random.uniform(5, 15)
                print(f"!!! Blocked ({response.status_code}). Waiting {wait_time:.1f}s...")
                time.sleep(wait_time)
            else:
                print(f"Error Status: {response.status_code}")
                return None
        except Exception as e:
            print(f"Connection Error: {e}. Retrying...")
            time.sleep(10)
    return None

# --- MAIN EXECUTION ---
response = scrape_with_retry(url)

if response:
    soup = BeautifulSoup(response.content, 'html.parser')
    match_links = []
    
    # FBRef uses 'match_report' for the link column
    report_cells = soup.find_all('td', {'data-stat': 'match_report'})
    
    for cell in report_cells:
        link_tag = cell.find('a')
        # Check if link exists; sometimes it's text like "Head-to-Head" for future games
        if link_tag and 'Match Report' in link_tag.text:
            href = link_tag.get('href')
            full_link = f"https://fbref.com{href}"
            match_links.append(full_link)

    if match_links:
        # Remove duplicates while preserving order
        match_links = list(dict.fromkeys(match_links))
        
        print(f"Success! Found {len(match_links)} match report links.")
        df = pd.DataFrame(match_links, columns=['Match_URL'])
        df.to_csv(output_file, index=False)
        print(f"Links saved to '{output_file}'.")
    else:
        print("Error: Found 0 links. Check if the season is currently in progress or if the HTML stat name changed.")
else:
    print("Failed to retrieve the page after all retries.")
