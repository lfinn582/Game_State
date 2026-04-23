from curl_cffi import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import random
import os

# --- CONFIGURATION ---
# Confirmed URL for 2020-2021 Serie A
url = "https://fbref.com/en/comps/11/2020-2021/schedule/2020-2021-Serie-A-Scores-and-Fixtures"
output_file = 'SerieA/SerieA_links_2021.csv'

os.makedirs(os.path.dirname(output_file), exist_ok=True)

def scrape_with_stealth(target_url, max_retries=3):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }

    with requests.Session() as session:
        for attempt in range(max_retries):
            try:
                # Essential: Wait 10-20 seconds BEFORE the first request to lower your "bot score"
                wait_time = random.uniform(10, 20)
                print(f"Waiting {wait_time:.1f}s to avoid 403... (Attempt {attempt+1})")
                time.sleep(wait_time)

                # Impersonate Chrome 120 to fix TLS/JA3 fingerprinting issues
                response = session.get(target_url, headers=headers, impersonate="chrome120", timeout=30)

                if response.status_code == 200:
                    return response
                elif response.status_code == 403:
                    print("!!! Still blocked (403). Try clearing your browser cookies or waiting 2 hours.")
                    time.sleep(60) # Short wait before retry
            except Exception as e:
                print(f"Error: {e}")
                time.sleep(10)
    return None

# --- EXECUTION ---
response = scrape_with_stealth(url)

if response:
    soup = BeautifulSoup(response.content, 'html.parser')
    match_links = []
    
    # Extract links from the 'match_report' data column
    report_cells = soup.find_all('td', {'data-stat': 'match_report'})
    for cell in report_cells:
        link_tag = cell.find('a')
        if link_tag and 'Match Report' in link_tag.text:
            match_links.append(f"https://fbref.com{link_tag.get('href')}")

    if match_links:
        match_links = list(dict.fromkeys(match_links))
        pd.DataFrame(match_links, columns=['Match_URL']).to_csv(output_file, index=False)
        print(f"Success! {len(match_links)} links saved to {output_file}")
    else:
        print("No match reports found on the page.")
else:
    print("Could not retrieve the page. Check your internet or IP status.")
