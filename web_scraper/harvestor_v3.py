from curl_cffi import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import random
import os

# --- CONFIGURATION ---
# Starting with the requested 2020-2021 Serie A URL
url = "https://fbref.com/en/comps/11/2020-2021/schedule/2020-2021-Serie-A-Scores-and-Fixtures"
output_file = 'SerieA/SerieA_links_2021.csv'

# Ensure directory exists
os.makedirs(os.path.dirname(output_file), exist_ok=True)

def scrape_with_retry(target_url, max_retries=5):
    """Stealthy scrape using Chrome 120 impersonation and adaptive delays."""
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Upgrade-Insecure-Requests": "1"
    }

    with requests.Session() as session:
        for attempt in range(max_retries):
            try:
                # Initial jitter to avoid bot-like instant requests
                time.sleep(random.uniform(4, 8))
                
                print(f"Fetching (Attempt {attempt+1}/{max_retries}): {target_url}")
                
                response = session.get(
                    target_url, 
                    headers=headers, 
                    impersonate="chrome120", 
                    timeout=30
                )

                if response.status_code == 200:
                    return response
                
                elif response.status_code in [403, 429]:
                    # Increase wait time exponentially on blocks
                    wait_time = (120 * (attempt + 1)) + random.uniform(10, 30)
                    print(f"!!! Blocked ({response.status_code}). Cooling down for {wait_time/60:.1f} mins...")
                    time.sleep(wait_time)
                else:
                    print(f"Unexpected status: {response.status_code}")
                    return None

            except Exception as e:
                print(f"Connection error: {e}. Retrying in 30s...")
                time.sleep(30)
                
    return None

# --- MAIN EXECUTION ---
response = scrape_with_retry(url)

if response:
    soup = BeautifulSoup(response.content, 'html.parser')
    match_links = []
    
    # Locate match report cells in the schedule table
    report_cells = soup.find_all('td', {'data-stat': 'match_report'})
    
    for cell in report_cells:
        link_tag = cell.find('a')
        # FBRef uses "Match Report" text for links to completed match data
        if link_tag and 'Match Report' in link_tag.text:
            href = link_tag.get('href')
            match_links.append(f"https://fbref.com{href}")

    if match_links:
        # Deduplicate while keeping chronological order
        match_links = list(dict.fromkeys(match_links))
        
        print(f"Success! Found {len(match_links)} match report links.")
        df = pd.DataFrame(match_links, columns=['Match_URL'])
        df.to_csv(output_file, index=False)
        print(f"File saved: {output_file}")
    else:
        print("No links found. Check if the table structure on FBRef has changed.")
else:
    print("Could not bypass security. Try running again in an hour.")
