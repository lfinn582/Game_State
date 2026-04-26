"""
fetch_laliga_data.py
====================
Fetches La Liga match data from football-data.org v4 API and outputs a CSV
matching the schema of Final_LaLiga_DataSet_2024.csv, with these changes:
  - Match_URL column REMOVED
  - Yellow Card added as a new Event_Type
  - Odds_Home_Win, Odds_Draw, Odds_Away_Win added from the API's odds object
 
Dependencies are installed automatically on first run.
 
Usage:
    python fetch_laliga_data.py
    python fetch_laliga_data.py --season 2024 --output laliga_2024.csv --matchday 1
 
La Liga competition code on football-data.org: PD
"""

# ── Auto-install dependencies ─────────────────────────────────────────────────
import pandas as pd
import requests
import time
import argparse
import subprocess
import sys


def _ensure(package: str, import_name: str = None):
    try:
        __import__(import_name or package)
    except ImportError:
        print(f"Installing {package}...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet", package])


_ensure("requests")
_ensure("pandas")

# ── Standard imports ──────────────────────────────────────────────────────────

# ── Configuration — set your API key here ────────────────────────────────────
# ← paste your football-data.org key
API_KEY = "YOUR_API_KEY_HERE"
BASE_URL = "https://api.football-data.org/v4"
COMPETITION = "PD"  # La Liga (Primera Division)
RATE_LIMIT_S = 6  # lower if in paid tier
# Year of season you want to collect (this is the year the season starts)
YEAR = 2023

# Maps API card/event strings to your original Event_Type vocabulary
EVENT_TYPE_MAP = {
    "GOAL":            "Goal",
    "OWN_GOAL":        "Own Goal",
    "YELLOW_CARD":     "Yellow Card",
    "RED_CARD":        "Red Card",
    "YELLOW_RED_CARD": "Red Card",   # second yellow treated as red
    "SUBSTITUTION":    "Substitution",
}

# ── Helpers ───────────────────────────────────────────────────────────────────


def api_get(url: str, params: dict = None) -> dict:
    """GET with automatic rate-limit retry and error checking."""
    headers = {"X-Auth-Token": API_KEY}
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 429:
        print("  Rate limited — waiting 60 s...")
        time.sleep(60)
        response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    return response.json()


def fetch_matches(season: int) -> list[dict]:
    """Return all La Liga match stubs for a given season start year."""
    data = api_get(
        f"{BASE_URL}/competitions/{COMPETITION}/matches", {"season": season})
    matches = data.get("matches", [])
    print(f"  Fetched {len(matches)} matches for season {season}")
    return matches


def fetch_match_detail(match_id: int) -> dict:
    """Return full match detail: lineups, goals, cards, subs, odds."""
    return api_get(f"{BASE_URL}/matches/{match_id}")


def build_game_id(season: int, matchday: int, match_index: int) -> int:
    """
    Recreate the original Game_ID format: LYYYYMMII
      L = league number
      YYYY = season year
      MM   = zero-padded matchday
      II   = zero-padded match index within that matchday (1-based)
    """
    return int(f"1{season}{matchday:02d}{match_index:02d}")


def classify_sub(position: str | None) -> str:
    """
    Map a player's position string from the API to Offensive / Defensive / Neutral.

    Offensive  — forwards and wingers
    Defensive  — goalkeepers and defenders
    Neutral    — midfielders and anything unrecognised
    """
    if not position:
        return "Neutral"
    pos = position.lower()
    if any(p in pos for p in ("forward", "winger", "striker", "centre-forward", "attacking")):
        return "Offensive"
    if any(p in pos for p in ("goalkeeper", "back", "defender", "defensive")):
        return "Defensive"
    return "Neutral"   # central/attacking midfield, unknown


def build_bench_position_map(match: dict) -> dict[str, str]:
    """
    Return {player_name: position} for every player on either bench,
    using the homeTeam.bench and awayTeam.bench arrays from the match detail.
    """
    position_map: dict[str, str] = {}
    for side_key in ("homeTeam", "awayTeam"):
        team = match.get(side_key) or {}
        for player in (team.get("bench") or []) + (team.get("lineup") or []):
            name = player.get("name")
            pos = player.get("position")
            if name:
                position_map[name] = pos
    return position_map


def parse_events(match: dict, game_id: int, season: int, matchday: int) -> list[dict]:
    """
    Convert a full match detail object into event rows matching the CSV schema.

    Scores are tracked as running totals (0-0 at kick-off, incrementing on each
    goal) so each row reflects the scoreline at the moment of the event.

    Substitutions are classified Offensive / Defensive / Neutral based on the
    position of the player coming ON, looked up from the bench/lineup data.
    """
    rows = []

    # Running score — starts 0-0 and increments on goals (not set from fullTime)
    running_home_score = 0
    running_away_score = 0

    # Final score used only for the Final Result note
    final_home = (match.get("score") or {}).get(
        "fullTime", {}).get("home") or 0
    final_away = (match.get("score") or {}).get(
        "fullTime", {}).get("away") or 0

    # Running counters — updated before each event row is appended
    counters = {
        "Home_Red_Count":        0,
        "Away_Red_Count":        0,
        "Home_Yellow_Count":     0,
        "Away_Yellow_Count":     0,
        "Home_Sub_Count":        0,
        "Away_Sub_Count":        0,
        # minute of first red/second-yellow; None if none yet
        "Home_First_Red_Time":   None,
        "Away_First_Red_Time":   None,
    }

    # Odds — sourced directly from the football-data.org match object
    odds = match.get("odds") or {}
    odds_home = odds.get("homeWin")
    odds_draw = odds.get("draw")
    odds_away = odds.get("awayWin")

    goals = match.get("goals") or []
    bookings = match.get("bookings") or []
    substitutions = match.get("substitutions") or []
    home_team_id = (match.get("homeTeam") or {}).get("id")

    # Position lookup built from bench + lineup data for sub classification
    bench_positions = build_bench_position_map(match)

    def team_side(team_obj: dict) -> str:
        if not team_obj:
            return None
        return "Home" if team_obj.get("id") == home_team_id else "Away"

    def make_row(minute, side, event_type, p1, pos1, p2, pos2, note) -> dict:
        return {
            "Game_ID":              game_id,
            "Season":               season,
            "Matchweek":            matchday,
            "Game_Type":            "League",
            "Time":                 minute,
            "Team":                 side,
            "Home_Score":           running_home_score,
            "Away_Score":           running_away_score,
            "Home_Red_Count":       counters["Home_Red_Count"],
            "Away_Red_Count":       counters["Away_Red_Count"],
            "Home_Yellow_Count":    counters["Home_Yellow_Count"],
            "Away_Yellow_Count":    counters["Away_Yellow_Count"],
            "Home_First_Red_Time":  counters["Home_First_Red_Time"],
            "Away_First_Red_Time":  counters["Away_First_Red_Time"],
            "Home_Sub_Count":       counters["Home_Sub_Count"],
            "Away_Sub_Count":       counters["Away_Sub_Count"],
            "Event_Type":           event_type,
            "Player_1":             p1,
            "Pos_1":                pos1,
            "Player_2":             p2,
            "Pos_2":                pos2,
            "Note":                 note,
            "Odds_Home_Win":        odds_home,
            "Odds_Draw":            odds_draw,
            "Odds_Away_Win":        odds_away,
        }

    # All events must be emitted in chronological order so the running score
    # is correct when stamped onto each row. Sort all three lists by minute
    # then interleave them together before processing.
    def event_minute(e: dict) -> int:
        return e.get("minute") or 0

    all_events = (
        [("goal",    g) for g in sorted(goals,         key=event_minute)] +
        [("booking", b) for b in sorted(bookings,      key=event_minute)] +
        [("sub",     s) for s in sorted(substitutions, key=event_minute)]
    )
    all_events.sort(key=lambda x: event_minute(x[1]))

    for kind, evt in all_events:

        # ── Goals & Own Goals ─────────────────────────────────────────────────
        if kind == "goal":
            own = evt.get("type") == "OWN_GOAL"
            etype = "Own Goal" if own else "Goal"
            side = team_side(evt.get("team"))

            # Increment the running score BEFORE stamping the row so the row
            # shows the scoreline after the goal (consistent with original data)
            if own:
                if side == "Home":
                    running_away_score += 1   # own goal benefits the other side
                else:
                    running_home_score += 1
            else:
                if side == "Home":
                    running_home_score += 1
                else:
                    running_away_score += 1

            scorer = evt.get("scorer") or {}
            assist = evt.get("assist") or {}
            rows.append(make_row(
                minute=event_minute(evt),
                side=side,
                event_type=etype,
                p1=scorer.get("name"),
                pos1=None,
                p2=assist.get("name") or None,
                pos2=None,
                note=etype,
            ))

        # ── Bookings (Yellow / Red / Second Yellow) ───────────────────────────
        elif kind == "booking":
            card = evt.get("card", "")
            etype = EVENT_TYPE_MAP.get(card, card)
            side = team_side(evt.get("team"))
            minute = event_minute(evt)

            if card == "YELLOW_CARD":
                if side == "Home":
                    counters["Home_Yellow_Count"] += 1
                elif side == "Away":
                    counters["Away_Yellow_Count"] += 1

            if "RED" in card:   # RED_CARD or YELLOW_RED_CARD (second yellow)
                if side == "Home":
                    counters["Home_Red_Count"] += 1
                    if counters["Home_First_Red_Time"] is None:
                        counters["Home_First_Red_Time"] = minute
                elif side == "Away":
                    counters["Away_Red_Count"] += 1
                    if counters["Away_First_Red_Time"] is None:
                        counters["Away_First_Red_Time"] = minute

            rows.append(make_row(
                minute=minute,
                side=side,
                event_type=etype,
                p1=(evt.get("player") or {}).get("name"),
                pos1=None,
                p2=None,
                pos2=None,
                note=etype,
            ))

        # ── Substitutions ─────────────────────────────────────────────────────
        elif kind == "sub":
            side = team_side(evt.get("team"))
            p_on = (evt.get("playerIn") or {}).get("name")
            p_off = (evt.get("playerOut") or {}).get("name")

            # Classify by the position of the player coming ON
            position = bench_positions.get(p_on)
            # Offensive / Defensive / Neutral
            sub_type = classify_sub(position)

            if side == "Home":
                counters["Home_Sub_Count"] += 1
            elif side == "Away":
                counters["Away_Sub_Count"] += 1

            rows.append(make_row(
                minute=event_minute(evt),
                side=side,
                event_type="Substitution",
                p1=p_on,
                pos1=position,
                p2=p_off,
                pos2=None,
                note="Substitution",
            ))

    # ── Final Result ──────────────────────────────────────────────────────────
    # Use final score from API for the result row (guards against data gaps)
    running_home_score = final_home
    running_away_score = final_away
    rows.append(make_row(90, None, "Final Result", None, None, None, None,
                         f"{final_home}-{final_away}"))

    return rows


# ── Main ──────────────────────────────────────────────────────────────────────

COLUMNS = [
    "Game_ID", "Season", "Matchweek", "Game_Type", "Time", "Team",
    "Home_Score", "Away_Score",
    "Home_Red_Count", "Away_Red_Count",
    "Home_Yellow_Count", "Away_Yellow_Count",
    "Home_First_Red_Time", "Away_First_Red_Time",
    "Home_Sub_Count", "Away_Sub_Count",
    # Match_URL intentionally omitted
    "Event_Type", "Player_1", "Pos_1", "Player_2", "Pos_2", "Note",
    "Odds_Home_Win", "Odds_Draw", "Odds_Away_Win",
]


def main():
    parser = argparse.ArgumentParser(
        description="Fetch La Liga data from football-data.org v4")
    parser.add_argument("--season",   type=int, default=YEAR,
                        help="Season start year (default: 2024)")
    parser.add_argument("--output",   default=f"serie_a_data_{str(YEAR)}.csv",
                        help="Output CSV path (default: laliga_data.csv)")
    parser.add_argument("--matchday", type=int, default=None,
                        help="Single matchday to fetch (optional)")
    args = parser.parse_args()

    # Allow key to be overridden without editing the file
    if API_KEY == "YOUR_API_KEY_HERE":
        key = input("Enter your football-data.org API key: ").strip()
        if not key:
            sys.exit("No API key provided — exiting.")
        globals()["API_KEY"] = key

    print(f"\n{'='*55}")
    print(f"  La Liga Data Fetcher — football-data.org v4")
    print(f"  Season: {args.season}  |  Competition: {COMPETITION}")
    print(f"{'='*55}\n")

    print("→ Fetching match list...")
    matches = fetch_matches(args.season)

    if args.matchday:
        matches = [m for m in matches if m.get("matchday") == args.matchday]
        print(
            f"  Filtered to matchday {args.matchday}: {len(matches)} matches")

    all_rows: list[dict] = []
    matchday_counters: dict[int, int] = {}

    for match in matches:
        mid = match["id"]
        matchday = match.get("matchday", 0)
        status = match.get("status", "")

        if status != "FINISHED":
            print(f"  Skipping match {mid} (status: {status})")
            continue

        matchday_counters[matchday] = matchday_counters.get(matchday, 0) + 1
        game_id = build_game_id(args.season, matchday,
                                matchday_counters[matchday])

        print(
            f"  Fetching match {mid} | GW{matchday} | ID→{game_id} ...", end=" ", flush=True)
        try:
            detail = fetch_match_detail(mid)
            rows = parse_events(detail, game_id, args.season, matchday)
            all_rows.extend(rows)
            print(f"{len(rows)} events")
        except Exception as e:
            print(f"ERROR: {e}")

        time.sleep(RATE_LIMIT_S)

    df = pd.DataFrame(all_rows, columns=COLUMNS)
    df = df.sort_values(by=['Game_ID', 'Time'])
    df.reset_index(drop=True, inplace=True)
    df.to_csv(args.output, index=False)

    print(f"\n✓ Done — {len(df)} rows written to: {args.output}")
    print(f"  Columns: {list(df.columns)}\n")


if __name__ == "__main__":
    main()
