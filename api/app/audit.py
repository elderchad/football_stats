"""Data-completeness audit.

Every check compares the data the charts are built from against either a structural
expectation (schedule length, one game per team per week) or a second, separately
published source. Results are reported as pass / warn / fail with the offending rows.
"""

from __future__ import annotations

import csv
import datetime as dt
import gzip
import io
import logging
import os
import threading
from collections import Counter, defaultdict

import httpx

from .data import (
    HISTORICAL_CACHE_PATH,
    HISTORICAL_TTL_SECONDS,
    HISTORICAL_URLS,
    REGULAR_SEASON,
    Game,
    _read_source,
    get_games,
)
from .ncaaf import NCAAF_START_SEASON, NCAAF_TEAMS, RIVALRIES, get_ncaaf_games
from .ncaaf_history import (
    BOWL_OUTCOMES,
    SEASON_RECORDS,
    TEAM_HISTORY_PAGES,
    _cached_wikitext,
    _parse_seasons,
    load_head_to_head,
    load_team_histories,
)
from .ncaaf_scores import load_historical_games
from .qb_records import build_qb_records, build_qb_td_int, build_qb_timeline
from .qb_stats import STATS_CACHE_DIR, STATS_START_SEASON, get_qb_game_stats
from .quarterbacks import QUARTERBACKS
from .teams import normalize

log = logging.getLogger(__name__)

MAX_DETAILS = 60
STANDINGS_URL = "https://raw.githubusercontent.com/nflverse/nfldata/master/data/standings.csv"
SEASON_TOTALS_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/stats_player/"
    "stats_player_{kind}_{season}.csv.gz"
)
ELO_OVERLAP = (1999, 2022)

# Published career passing totals (regular season unless noted) for QBs whose whole
# career sits inside nflverse coverage, as (TD, INT, through season). Peyton Manning
# excludes his 1998 rookie season (26 TD / 28 INT), which predates the 1999 data floor;
# Rivers is compared through 2020, before his 2025 comeback.
PUBLISHED_CAREER_TOTALS: dict[tuple[str, str], tuple[int, int, int]] = {
    ("brady", "REG"): (649, 212, 2022),
    ("brady", "POST"): (88, 40, 2022),
    ("brees", "REG"): (571, 243, 2020),
    ("roethlisberger", "REG"): (418, 211, 2021),
    ("emanning", "REG"): (366, 244, 2019),
    ("rivers", "REG"): (421, 209, 2020),
    ("luck", "REG"): (171, 83, 2018),
    ("pmanning", "REG"): (513, 223, 2015),
}

UTAH_BYU_HISTORY_PAGES = {
    "UTAH": "List of Utah Utes football seasons",
    "BYU": "List of BYU Cougars football seasons",
}

# Seasons where the published list shows the record after vacated wins; the charts use
# on-field results, so compare against those instead.
ON_FIELD_RECORDS = {("OSU", 2010): (12, 1, 0)}

_lock = threading.Lock()
_report: dict | None = None


def _check(
    check_id: str,
    title: str,
    scope: str,
    checked: int,
    issues: list[str],
    warn_only: bool = False,
    note: str = "",
) -> dict:
    status = "pass" if not issues else ("warn" if warn_only else "fail")
    return {
        "id": check_id,
        "title": title,
        "scope": scope,
        "status": status,
        "checked": checked,
        "issue_count": len(issues),
        "issues": issues[:MAX_DETAILS],
        "note": note,
    }


def _error(check_id: str, title: str, scope: str, exc: Exception) -> dict:
    log.exception("Audit check %s failed", check_id)
    return {
        "id": check_id,
        "title": title,
        "scope": scope,
        "status": "error",
        "checked": 0,
        "issue_count": 1,
        "issues": [f"Check could not run: {exc}"],
        "note": "",
    }


def _complete_seasons(games: list[Game]) -> set[int]:
    """Seasons whose Super Bowl (or pre-1966 title game) has been played."""
    latest = max(g.season for g in games)
    with_sb = {g.season for g in games if g.game_type == "SB"}
    return {season for season in {g.season for g in games} if season < latest or season in with_sb}


def _expected_regular_games(season: int, team: str) -> int | None:
    if season < 1961:
        return None  # schedule lengths varied by team and league
    if season == 1982:
        return 9
    if season == 1987:
        return 15
    if season == 2022 and team in ("BUF", "CIN"):
        return 16  # the week 17 game was declared no contest
    if season <= 1977:
        return 14
    if season <= 2020:
        return 16
    return 17


def _expected_playoff_games(season: int) -> int | None:
    if season < 1978:
        return None
    if season == 1982:
        return 15
    if season <= 1989:
        return 9  # one wild-card game per conference
    if season <= 2019:
        return 11
    return 13


# --------------------------------------------------------------------------- NFL


def _nfl_structure(games: list[Game]) -> list[dict]:
    complete = _complete_seasons(games)
    results = []

    counts = Counter(games)
    duplicates = [
        f"{g.season} wk {g.week} {g.away} @ {g.home} {g.away_score}-{g.home_score} appears {n}x"
        for g, n in counts.items() if n > 1
    ]
    results.append(_check(
        "nfl_duplicates", "No duplicate NFL games", "1920-present", len(games), duplicates,
    ))

    slots: Counter = Counter()
    for g in games:
        if g.season < 1999:
            continue  # earlier weeks are clustered from dates, not published week numbers
        for team in (g.home, g.away):
            slots[(g.season, g.week, g.game_type, team)] += 1
    conflicts = [
        f"{season} wk {week} ({game_type}): {team} has {n} games"
        for (season, week, game_type, team), n in sorted(slots.items()) if n > 1
    ]
    results.append(_check(
        "nfl_week_conflicts", "No team plays twice in the same week", "1999-present",
        len(slots), conflicts,
    ))

    regular: Counter = Counter()
    for g in games:
        if g.game_type == REGULAR_SEASON:
            regular[(g.season, g.home)] += 1
            regular[(g.season, g.away)] += 1
    length_issues = []
    checked = 0
    for (season, team), played in sorted(regular.items()):
        expected = _expected_regular_games(season, team)
        if expected is None or season not in complete:
            continue
        checked += 1
        if played != expected:
            length_issues.append(f"{season} {team}: {played} regular-season games, expected {expected}")
    results.append(_check(
        "nfl_schedule_length", "Every team has a full regular season", "1961-last complete season",
        checked, length_issues,
    ))

    playoffs: Counter = Counter(g.season for g in games if g.game_type != REGULAR_SEASON)
    playoff_issues = []
    checked = 0
    for season in sorted(complete):
        expected = _expected_playoff_games(season)
        if expected is None:
            continue
        checked += 1
        if playoffs.get(season, 0) != expected:
            playoff_issues.append(f"{season}: {playoffs.get(season, 0)} playoff games, expected {expected}")
    super_bowls = Counter(g.season for g in games if g.game_type == "SB")
    for season in sorted(s for s in complete if s >= 1966):
        if super_bowls.get(season, 0) != 1:
            playoff_issues.append(f"{season}: {super_bowls.get(season, 0)} Super Bowls, expected 1")
    results.append(_check(
        "nfl_playoffs", "Every playoff bracket is complete", "1966-last complete season",
        checked, playoff_issues,
    ))
    return results


def _game_key(season: int, post: bool, team_a: str, score_a: int, team_b: str, score_b: int):
    return (season, post, tuple(sorted(((team_a, score_a), (team_b, score_b)))))


def _describe_key(key) -> str:
    season, post, ((team_a, score_a), (team_b, score_b)) = key
    return f"{season} {'playoff' if post else 'regular'}: {team_a} {score_a} - {team_b} {score_b}"


def _nfl_cross_source(games: list[Game]) -> dict:
    first, last = ELO_OVERLAP
    text = _read_source(HISTORICAL_URLS, HISTORICAL_CACHE_PATH, HISTORICAL_TTL_SECONDS)
    elo: Counter = Counter()
    for row in csv.DictReader(io.StringIO(text)):
        if not row.get("score1") or not row.get("score2"):
            continue
        season = int(row["season"])
        if not first <= season <= last:
            continue
        elo[_game_key(
            season, bool((row.get("playoff") or "").strip()),
            normalize(row["team1"]), int(float(row["score1"])),
            normalize(row["team2"]), int(float(row["score2"])),
        )] += 1

    nflverse: Counter = Counter(
        _game_key(g.season, g.game_type != REGULAR_SEASON, g.home, g.home_score, g.away, g.away_score)
        for g in games if first <= g.season <= last
    )
    issues = [f"Only in nflverse: {_describe_key(k)}" for k in sorted(nflverse - elo)]
    issues += [f"Only in FiveThirtyEight: {_describe_key(k)}" for k in sorted(elo - nflverse)]
    return _check(
        "nfl_cross_source", "nflverse matches FiveThirtyEight game-for-game",
        f"{first}-{last}", sum(nflverse.values()), issues,
        note="Two independently maintained datasets; every game, score and playoff flag must agree.",
    )


def _nfl_standings(games: list[Game]) -> dict:
    response = httpx.get(STANDINGS_URL, timeout=60.0, follow_redirects=True)
    response.raise_for_status()

    computed: dict[tuple[int, str], list[int]] = defaultdict(lambda: [0, 0, 0])
    for g in games:
        if g.game_type != REGULAR_SEASON:
            continue
        for team in (g.home, g.away):
            record = computed[(g.season, team)]
            if g.is_tie:
                record[2] += 1
            elif g.winner == team:
                record[0] += 1
            else:
                record[1] += 1

    seasons = _complete_seasons(games)
    issues = []
    checked = 0
    for row in csv.DictReader(io.StringIO(response.text)):
        season, team = int(row["season"]), normalize(row["team"])
        published = [int(row["wins"]), int(row["losses"]), int(row["ties"] or 0)]
        if season not in seasons or published == [0, 0, 0]:
            continue
        checked += 1
        ours = computed.get((season, team), [0, 0, 0])
        if ours != published:
            issues.append(
                f"{season} {team}: computed {'-'.join(map(str, ours))}, "
                f"standings {'-'.join(map(str, published))}"
            )
    return _check(
        "nfl_standings", "Computed team records match published standings",
        "2002-last complete season", checked, issues,
    )


# --------------------------------------------------------------------------- QBs


def _season_totals(season: int, kind: str, names: dict[str, str]) -> dict[str, tuple[int, int]]:
    path = os.path.join(STATS_CACHE_DIR, "season_totals_v2", f"{kind}_{season}.csv")
    if not os.path.exists(path):
        response = httpx.get(
            SEASON_TOTALS_URL.format(kind=kind, season=season), timeout=120.0, follow_redirects=True
        )
        response.raise_for_status()
        text = gzip.decompress(response.content).decode("utf-8")
        rows = []
        for row in csv.DictReader(io.StringIO(text)):
            if (row.get("position") or "").strip().upper() != "QB":
                continue
            qb_id = names.get((row.get("player_display_name") or "").strip().casefold())
            if qb_id:
                rows.append({
                    "qb_id": qb_id,
                    "td": int(float(row.get("passing_tds") or 0)),
                    "int": int(float(row.get("passing_interceptions") or 0)),
                })
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=("qb_id", "td", "int"))
            writer.writeheader()
            writer.writerows(rows)
    with open(path, encoding="utf-8", newline="") as handle:
        return {row["qb_id"]: (int(row["td"]), int(row["int"])) for row in csv.DictReader(handle)}


def _qb_checks(games: list[Game]) -> list[dict]:
    latest_season = max(g.season for g in games)
    stats = get_qb_game_stats(latest_season)
    names = {qb.name.casefold(): qb.id for qb in QUARTERBACKS}
    results = []

    # 1. Every modern-era QB is found in the stats feed, in every season he started.
    missing = []
    checked = 0
    starts_by_season: dict[str, set[int]] = defaultdict(set)
    for g in games:
        for name in (g.home_qb, g.away_qb):
            if name and name.casefold() in names:
                starts_by_season[names[name.casefold()]].add(g.season)
    for qb in QUARTERBACKS:
        seasons = {s for s in starts_by_season.get(qb.id, set()) if s >= STATS_START_SEASON}
        if not seasons:
            continue
        stat_seasons = {row["season"] for row in stats.get(qb.id, [])}
        checked += len(seasons)
        for season in sorted(seasons - stat_seasons):
            missing.append(f"{qb.name}: started games in {season} but has no passing rows")
    results.append(_check(
        "qb_coverage", "Passing stats exist for every season a QB started",
        f"{STATS_START_SEASON}-present", checked, missing,
    ))

    # 2. Weekly rows add up to nflverse's official season totals.
    weekly: dict[tuple[str, int, str], list[int]] = defaultdict(lambda: [0, 0])
    for qb_id, rows in stats.items():
        for row in rows:
            kind = "POST" if row["season_type"] == "POST" else "REG"
            weekly[(qb_id, row["season"], kind)][0] += row["td"]
            weekly[(qb_id, row["season"], kind)][1] += row["int"]
    total_issues = []
    checked = 0
    complete = _complete_seasons(games)
    for season in range(STATS_START_SEASON, latest_season + 1):
        if season not in complete:
            continue
        for kind in ("reg", "post"):
            try:
                totals = _season_totals(season, kind, names)
            except httpx.HTTPError as exc:
                total_issues.append(f"{season} {kind}: season totals unavailable ({exc})")
                continue
            keys = {qb_id for (qb_id, s, k) in weekly if s == season and k == kind.upper()} | set(totals)
            for qb_id in sorted(keys):
                checked += 1
                ours = tuple(weekly.get((qb_id, season, kind.upper()), (0, 0)))
                published = totals.get(qb_id, (0, 0))
                if ours != published:
                    total_issues.append(
                        f"{qb_id} {season} {kind}: weekly sum {ours[0]} TD / {ours[1]} INT, "
                        f"season file {published[0]} TD / {published[1]} INT"
                    )
    results.append(_check(
        "qb_season_totals", "Weekly TD/INT rows sum to official season totals",
        f"{STATS_START_SEASON}-last complete season", checked, total_issues,
    ))

    # 3. Career totals match published career figures.
    career_issues = []
    for (qb_id, kind), (td, ints, through) in PUBLISHED_CAREER_TOTALS.items():
        ours = [0, 0]
        for (row_qb, season, row_kind), (row_td, row_int) in weekly.items():
            if row_qb == qb_id and row_kind == kind and season <= through:
                ours[0] += row_td
                ours[1] += row_int
        if ours != [td, ints]:
            career_issues.append(
                f"{qb_id} {kind} through {through}: data {ours[0]} TD / {ours[1]} INT, "
                f"published {td} TD / {ints} INT"
            )
    results.append(_check(
        "qb_career_totals", "Career TD/INT match published career totals",
        "Retired QBs fully inside 1999+", len(PUBLISHED_CAREER_TOTALS), career_issues,
    ))

    start_issues = []
    checked = 0
    walks = {series["id"]: series for series in build_qb_records(games, None, "all")["series"]}
    annual = {series["id"]: series for series in build_qb_timeline(games, None, "all", "games")["series"]}
    for qb in QUARTERBACKS:
        starts = [
            (game, team) for game in games
            for team, name in ((game.home, game.home_qb), (game.away, game.away_qb))
            if name.casefold() == qb.name.casefold()
        ]
        if not starts:
            continue
        expected = sum(
            1 if game.winner == team else -1 if game.loser == team else 0
            for game, team in starts
        )
        checked += 1
        walk = walks.get(qb.id, {})
        timeline = annual.get(qb.id, {})
        if (walk.get("wins", 0) + walk.get("losses", 0) + walk.get("ties", 0) != len(starts)
                or walk.get("final") != expected
                or timeline.get("games") != len(starts)
                or timeline.get("final") != expected):
            start_issues.append(f"{qb.name}: Games charts disagree with {len(starts)} named starts, net {expected}")
    results.append(_check(
        "qb_starts", "QB Games charts match actual starts",
        "1950-present", checked, start_issues,
        note="Injury-shortened starts count; games started by someone else do not. "
             "Pre-1950 starter names are unavailable and are not inferred from team stints.",
    ))
    view_issues = []
    checked = 0
    for mode in ("all", "regular", "playoffs", "superbowls"):
        for metric in ("td", "int", "td_int"):
            walks = build_qb_td_int(games, None, mode, metric)
            annual = {series["id"]: series for series in build_qb_timeline(games, None, mode, metric)["series"]}
            for series in walks["series"]:
                checked += 1
                timeline = annual.get(series["id"], {})
                if series["final"] != timeline.get("final") or series["games"] != timeline.get("games"):
                    view_issues.append(f"{series['name']} {mode} {metric}: passing views disagree")
    results.append(_check(
        "qb_view_consistency", "QB passing totals agree across game and season views",
        "1999-present, every metric and game mode", checked, view_issues,
    ))
    return results


# --------------------------------------------------------------------------- NCAAF


def _ncaaf_checks() -> list[dict]:
    games = get_ncaaf_games()
    today = dt.date.today()
    last_complete = today.year - (1 if today.month >= 2 else 2)  # bowls finish in January
    results = []

    load_team_histories(tuple(TEAM_HISTORY_PAGES))
    published: dict[str, dict[int, tuple[int, int, int]]] = {
        code: SEASON_RECORDS.get(code, {}) for code in TEAM_HISTORY_PAGES
    }
    page_errors = []
    for code, page in UTAH_BYU_HISTORY_PAGES.items():
        try:
            published[code], _ = _parse_seasons(_cached_wikitext(page))
        except Exception as exc:  # noqa: BLE001 - report instead of failing the audit
            page_errors.append(f"{code}: could not read '{page}' ({exc})")

    computed: dict[tuple[str, int], list[int]] = defaultdict(lambda: [0, 0, 0])
    for g in games:
        for team in NCAAF_TEAMS:
            if team not in (g.home, g.away):
                continue
            record = computed[(team, g.season)]
            if g.winner is None:
                record[2] += 1
            elif g.winner == team:
                record[0] += 1
            else:
                record[1] += 1

    issues = list(page_errors)
    checked = 0
    for team in NCAAF_TEAMS:
        for season in range(NCAAF_START_SEASON, last_complete + 1):
            reference = ON_FIELD_RECORDS.get((team, season)) or published.get(team, {}).get(season)
            ours = computed.get((team, season))
            if reference is None:
                if team in published:
                    issues.append(f"{team} {season}: no published season record to compare")
                continue
            checked += 1
            if ours is None or tuple(ours) != reference:
                shown = "-".join(map(str, ours)) if ours else "no games"
                issues.append(
                    f"{team} {season}: game data {shown}, published {'-'.join(map(str, reference))}"
                )
    results.append(_check(
        "ncaaf_season_records", "Game-level results add up to published season records",
        f"{NCAAF_START_SEASON}-{last_complete}", checked, issues,
        note="Ohio State's vacated 2010 season is compared on on-field results (12-1).",
    ))

    h2h_issues = []
    checked = 0
    for rivalry_id, rivalry in RIVALRIES.items():
        teams = set(rivalry["teams"])
        reference = Counter(
            (season, winner) for season, _, winner, first, second in load_head_to_head(rivalry_id)
            if NCAAF_START_SEASON <= season <= last_complete and {first, second} == teams
        )
        ours = Counter(
            (g.season, g.winner) for g in games
            if NCAAF_START_SEASON <= g.season <= last_complete and {g.home, g.away} == teams
        )
        checked += sum(reference.values())
        for season, winner in sorted((reference - ours).elements(), key=str):
            h2h_issues.append(f"{rivalry['name']} {season}: published winner {winner or 'tie'} missing from game data")
        for season, winner in sorted((ours - reference).elements(), key=str):
            h2h_issues.append(f"{rivalry['name']} {season}: game data winner {winner or 'tie'} not in published series")
    results.append(_check(
        "ncaaf_head_to_head", "Rivalry games match the published series results",
        f"{NCAAF_START_SEASON}-{last_complete}", checked, h2h_issues,
    ))
    return results


def _year_ranges(seasons: list[int]) -> str:
    ranges: list[str] = []
    for season in sorted(seasons):
        if ranges and season == int(ranges[-1].split("-")[-1]) + 1:
            ranges[-1] = f"{ranges[-1].split('-')[0]}-{season}"
        else:
            ranges.append(str(season))
    return ", ".join(ranges)


def _outcomes(counter: Counter) -> str:
    return "".join(sorted(counter.elements())) or "none"


def _ncaaf_history_checks() -> list[dict]:
    """Pre-2001 game-level coverage, checked against the published season and series data."""
    teams = tuple(NCAAF_TEAMS)
    load_team_histories(teams)
    history = load_historical_games(teams)
    today = dt.date.today()
    last_complete = today.year - (1 if today.month >= 2 else 2)
    results = []

    records: dict[tuple[str, int], list[int]] = defaultdict(lambda: [0, 0, 0])
    bowls: dict[tuple[str, int], Counter] = defaultdict(Counter)
    for team, team_games in history.items():
        for game in team_games:
            records[(team, game.season)]["WLT".index(game.result)] += 1
            if game.is_bowl:
                bowls[(team, game.season)][game.result] += 1

    coverage_issues = [f"{team}: historical scores page unavailable" for team in teams if not history[team]]
    checked = 0
    for team in teams:
        seasons = [s for s in SEASON_RECORDS.get(team, {}) if s < NCAAF_START_SEASON]
        checked += len(seasons)
        missing = [s for s in seasons if (team, s) not in records]
        if missing:
            coverage_issues.append(
                f"{team}: {len(missing)} of {len(seasons)} seasons are season totals only ({_year_ranges(missing)})"
            )
    results.append(_check(
        "ncaaf_game_coverage", "Every pre-2001 season has game-by-game results",
        f"program start-{NCAAF_START_SEASON - 1}", checked, coverage_issues, warn_only=True,
        note="Seasons listed here are missing from the historical scores database (mostly "
             "pre-1905 and seasons it does not rate), so the chart uses one season-total step.",
    ))

    record_issues = []
    bowl_issues = []
    checked = 0
    for team in teams:
        for season, published in sorted(SEASON_RECORDS.get(team, {}).items()):
            if season >= NCAAF_START_SEASON or (team, season) not in records:
                continue
            checked += 1
            ours = tuple(records[(team, season)])
            if ours != published:
                record_issues.append(
                    f"{team} {season}: game-by-game {'-'.join(map(str, ours))}, "
                    f"published {'-'.join(map(str, published))}"
                )
            expected = Counter(BOWL_OUTCOMES.get(team, {}).get(season, ()))
            if bowls[(team, season)] != expected:
                bowl_issues.append(
                    f"{team} {season}: bowl results {_outcomes(bowls[(team, season)])}, "
                    f"published {_outcomes(expected)}"
                )
    results.append(_check(
        "ncaaf_history_records", "Pre-2001 game results add up to published season records",
        f"program start-{NCAAF_START_SEASON - 1}", checked, record_issues, warn_only=True,
        note="Two independent sources; early-era differences are usually disputed games or "
             "later forfeits. Charts follow the game-by-game results.",
    ))
    results.append(_check(
        "ncaaf_history_bowls", "Pre-2001 bowl games match published bowl outcomes",
        f"program start-{NCAAF_START_SEASON - 1}", checked, bowl_issues, warn_only=True,
    ))

    h2h_issues = []
    checked = 0
    covered = {(team, season) for team, season in records}
    for rivalry_id, rivalry in RIVALRIES.items():
        first, second = rivalry["teams"]
        reference = Counter(
            (season, winner) for season, _, winner, a, b in load_head_to_head(rivalry_id)
            if season < NCAAF_START_SEASON and {a, b} == {first, second}
            and (first, season) in covered and (second, season) in covered
        )
        ours = Counter(
            (g.season, None if g.result == "T" else first if g.result == "W" else second)
            for g in history[first] if g.opponent == second and g.season < NCAAF_START_SEASON
            and (second, g.season) in covered
        )
        checked += sum(reference.values())
        for season, winner in sorted((reference - ours).elements(), key=str):
            h2h_issues.append(f"{rivalry['name']} {season}: series table winner {winner or 'tie'} not in game-by-game data")
        for season, winner in sorted((ours - reference).elements(), key=str):
            h2h_issues.append(f"{rivalry['name']} {season}: game-by-game winner {winner or 'tie'} not in series table")
    results.append(_check(
        "ncaaf_history_head_to_head", "Pre-2001 rivalry games match the published series tables",
        f"series start-{NCAAF_START_SEASON - 1}", checked, h2h_issues,
        note="Only seasons covered game-by-game for both programs are compared.",
    ))

    modern = get_ncaaf_games()
    synthetic = {(g.home, g.season) for g in modern if g.away.startswith("BOWL-")}
    result_issues = []
    score_issues = []
    checked = 0
    for team in teams:
        ours_games = [
            (g.season, g.home_score if g.home == team else g.away_score,
             g.away_score if g.home == team else g.home_score)
            for g in modern
            if team in (g.home, g.away) and NCAAF_START_SEASON <= g.season <= last_complete
            and not g.away.startswith("BOWL-")
        ]
        reference_games = [
            (g.season, g.points_for, g.points_against) for g in history[team]
            if NCAAF_START_SEASON <= g.season <= last_complete
            and not (g.is_bowl and (team, g.season) in synthetic)
        ]
        checked += len(reference_games)
        ours, reference = Counter(ours_games), Counter(reference_games)
        for season, pf, pa in sorted((reference - ours).elements()):
            score_issues.append(f"{team} {season}: {pf}-{pa} in historical scores, not in cfbfastR")
        for season, pf, pa in sorted((ours - reference).elements()):
            score_issues.append(f"{team} {season}: {pf}-{pa} in cfbfastR, not in historical scores")

        def outcome(season: int, pf: int, pa: int) -> tuple[int, str]:
            return season, "W" if pf > pa else "L" if pf < pa else "T"

        ours_results = Counter(outcome(*game) for game in ours_games)
        reference_results = Counter(outcome(*game) for game in reference_games)
        for season, result in sorted((reference_results - ours_results).elements()):
            result_issues.append(f"{team} {season}: a {result} in historical scores is missing from cfbfastR")
        for season, result in sorted((ours_results - reference_results).elements()):
            result_issues.append(f"{team} {season}: a {result} in cfbfastR is missing from historical scores")
    results.append(_check(
        "ncaaf_modern_cross_source", "cfbfastR matches the historical scores database game-for-game",
        f"{NCAAF_START_SEASON}-{last_complete}", checked, result_issues,
        note="Wins, losses and ties per season must agree. Bowl games reconstructed from "
             "published outcomes (no scores) are excluded.",
    ))
    results.append(_check(
        "ncaaf_modern_scores", "cfbfastR scores match the historical scores database",
        f"{NCAAF_START_SEASON}-{last_complete}", checked, score_issues, warn_only=True,
        note="Score-only differences do not change any chart; they flag typos in one source.",
    ))
    return results


# --------------------------------------------------------------------------- report

LIMITATIONS = [
    "NFL passing TD/INT exist only from 1999 (nflverse play-by-play era); earlier QBs "
    "have Games walks but no TD/INT lines.",
    "NFL quarterback names (used for the starts check) are only present from 1950.",
    "NFL 1920-1998 games come from a single source (FiveThirtyEight); only the 1999-2022 "
    "overlap can be cross-checked game-for-game against nflverse.",
    "NCAAF before 2001 is game-by-game from James Howell's historical scores database; "
    "seasons it does not cover (mostly pre-1905) fall back to one published season total "
    "(see the game-by-game coverage check).",
    "NCAAF bowl results for most seasons before 2023 come from the published histories, "
    "because cfbfastR schedules omit pre-2023 postseason games.",
    "The current, in-progress season is excluded from length and bracket checks.",
]


def _build() -> dict:
    games = get_games()
    checks: list[dict] = []
    checks += _nfl_structure(games)
    for check_id, title, scope, runner in (
        ("nfl_cross_source", "nflverse matches FiveThirtyEight game-for-game", "1999-2022", _nfl_cross_source),
        ("nfl_standings", "Computed team records match published standings", "2002-present", _nfl_standings),
    ):
        try:
            checks.append(runner(games))
        except Exception as exc:  # noqa: BLE001 - one broken source should not hide the rest
            checks.append(_error(check_id, title, scope, exc))
    try:
        checks += _qb_checks(games)
    except Exception as exc:  # noqa: BLE001
        checks.append(_error("qb", "Quarterback checks", "1999-present", exc))
    try:
        checks += _ncaaf_checks()
    except Exception as exc:  # noqa: BLE001
        checks.append(_error("ncaaf", "NCAAF checks", "2001-present", exc))
    try:
        checks += _ncaaf_history_checks()
    except Exception as exc:  # noqa: BLE001
        checks.append(_error("ncaaf_history", "NCAAF game-by-game history checks", "pre-2001", exc))

    summary = Counter(check["status"] for check in checks)
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "summary": {status: summary.get(status, 0) for status in ("pass", "warn", "fail", "error")},
        "checks": checks,
        "limitations": LIMITATIONS,
    }


def run_audit(refresh: bool = False) -> dict:
    global _report
    with _lock:
        if _report is None or refresh:
            _report = _build()
        return _report
