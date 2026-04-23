from curl_cffi import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import random
import os

# --- CONFIGURATION ---
# Correct URL for 2020-2021 Serie A
target_url = "https://fbref.com"
# Optional "warm-up" URL to build cookies
home_url = "https://fbref.com/en/comps/11/2020-2021/2020-2021-Serie-A-Stats"

output_file = 'SerieA/SerieA_links_2021.csv'
os.makedirs(os.path.dirname(output_file), exist_ok=True)

def scrape_with_stealth(target_url, max_retries=3):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://google.com",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "cross-site",
        "Connection": "keep-alive",
    }

    with requests.Session() as session:
        # STEP 1: Warm up the session (Optional but recommended)
        print("Warming up session...")
        session.get(home_url, headers=headers, impersonate="chrome110")
        time.sleep(random.uniform(5, 10))

        # STEP 2: Request the target schedule page
        for attempt in range(max_retries):
            try:
                wait_time = random.uniform(20, 35)
                print(f"Waiting {wait_time:.1f}s... (Attempt {attempt+1})")
                time.sleep(wait_time)

                response = session.get(
                    target_url, 
                    headers=headers, 
                    impersonate="chrome110", 
                    timeout=30
                )

                if response.status_code == 200:
                    return response
                elif response.status_code == 403:
                    print("!!! Blocked (403). Try changing your IP/VPN.")
                    break 
                elif response.status_code == 429:
                    print("!!! Rate Limited (429). FBRef allows ~20 requests per minute.")
                    time.sleep(120)
            except Exception as e:
                print(f"Connection Error: {e}")
                time.sleep(10)
        return None

# --- EXECUTION ---
response = scrape_with_stealth(target_url)

if response:
    soup = BeautifulSoup(response.content, 'html.parser')
    match_links = []
    
    # Extract match report links
    report_cells = soup.find_all('td', {'data-stat': 'match_report'})
    for cell in report_cells:
        link_tag = cell.find('a')
        if link_tag and 'Match Report' in link_tag.text:
            href = link_tag.get('href')
            if href:
                match_links.append(f"https://fbref.com{href}")

    if match_links:
        match_links = list(dict.fromkeys(match_links))
        pd.DataFrame(match_links, columns=['Match_URL']).to_csv(output_file, index=False)
        print(f"Success! {len(match_links)} links saved to {output_file}")
    else:
        print("No match reports found. Check if the season is correctly selected.")
else:
    print("Could not retrieve the page.")