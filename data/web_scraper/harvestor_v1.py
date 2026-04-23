# Webscraper Harvestor File, collects urls from fbref
from curl_cffi import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import random
# --- CONFIGURATION --
# 1. URL for the 2021-2022 Season
url = "https://fbref.com/en/comps/11/2021-2022/schedule/2021-2022-Serie-A-Scores-and-Fixtures"

# 2. Output File for 2021-2022 Links (save end year)
output_file = 'SeriaA/SerieA_links_2022.csv'

# --------------------
def scrape_with_retry(url, max_retries=3):
    """Tries to scrape a URL, pauses and retries if blocked."""
    for attempt in range(max_retries):
        try:
            print(f"Fetching (Attempt {attempt+1}): {url}")
            # UPDATED: Use 'safari15_3' to match your Worker script
            response = requests.get(url, impersonate="safari15_3", timeout=15)
            if response.status_code == 200:
                return response
            elif response.status_code in [403, 429]:
                # If blocked, wait 60 seconds and try again
                print(f"   !!! Blocked (403/429). Waiting 60s before Retry...")
                time.sleep(60 + random.uniform(1, 10))
            else:
                print(f"   Error: {response.status_code}")
                return None
        except Exception as e:
            print(f"   Connection Error: {e}. Retrying...")
            time.sleep(10)
    print(f"   Failed after {max_retries} attempts.")
    return None

# --- MAIN EXECUTION --
response = scrape_with_retry(url)
if response and response.status_code == 200:
    soup = BeautifulSoup(response.content, 'html.parser')
    # Find the links
    match_links = []
    report_cells = soup.find_all('td', {'data-stat': 'match_report'})
    for cell in report_cells:
        link_tag = cell.find('a')
        if link_tag and link_tag.text == "Match Report":
            href = link_tag.get('href')
            full_link = f"https://fbref.com{href}"
            match_links.append(full_link)
    # Save to CSV
    if len(match_links) > 0:
        print(f"Success! Found {len(match_links)} matches.")
        df = pd.DataFrame(match_links, columns=['Match_URL'])
        df.to_csv(output_file, index=False)
        print(f"Links saved to '{output_file}'. Check your folder!")
    else:
        print("Error: Found 0 links. The page might have loaded but the structure is different.")
else:
    print("Could not retrieve links even after retries.")