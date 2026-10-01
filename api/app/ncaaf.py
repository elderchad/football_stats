"""NCAAF game results for the teams exposed by this application."""

from __future__ import annotations

import csv
import datetime as dt
import io
import logging
import os
import threading
import time
from dataclasses import dataclass

import httpx

from .events import END, place_events
from .ncaaf_history import (
    BOWL_OUTCOMES,
    SEASON_RECORDS,
    load_championships,
    load_head_to_head,
    load_team_histories,
)
from .ncaaf_scores import load_historical_games

log = logging.getLogger(__name__)

NCAAF_START_SEASON = 2001
SCHEDULE_URL = (
    "https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/"
    "schedules/csv/cfb_schedules_{season}.csv"
)
CACHE_DIR = os.environ.get("NCAAF_CACHE_DIR", "/data/ncaaf")
CURRENT_SEASON_TTL = int(os.environ.get("GAMES_CACHE_TTL_SECONDS", str(12 * 60 * 60)))

NCAAF_TEAMS: dict[str, dict[str, str]] = {
    "UTAH": {"source_name": "Utah", "name": "Utah Utes", "color": "#CC0000"},
    "BYU": {"source_name": "BYU", "name": "BYU Cougars", "color": "#0062B8"},
    "MICH": {"source_name": "Michigan", "name": "Michigan Wolverines", "color": "#FFCB05"},
    "OSU": {"source_name": "Ohio State", "name": "Ohio State Buckeyes", "color": "#BB0000"},
    "BAMA": {"source_name": "Alabama", "name": "Alabama Crimson Tide", "color": "#9E1B32"},
    "AUB": {"source_name": "Auburn", "name": "Auburn Tigers", "color": "#F26522"},
    "TEX": {"source_name": "Texas", "name": "Texas Longhorns", "color": "#BF5700"},
    "OU": {"source_name": "Oklahoma", "name": "Oklahoma Sooners", "color": "#841617"},
}
_SOURCE_TO_CODE = {team["source_name"]: code for code, team in NCAAF_TEAMS.items()}

RIVALRIES: dict[str, dict[str, object]] = {
    "holy-war": {"name": "Utah vs. BYU", "nickname": "The Holy War", "teams": ("UTAH", "BYU")},
    "the-game": {"name": "Michigan vs. Ohio State", "nickname": "The Game", "teams": ("MICH", "OSU")},
    "iron-bowl": {"name": "Alabama vs. Auburn", "nickname": "The Iron Bowl", "teams": ("BAMA", "AUB")},
    "red-river": {"name": "Texas vs. Oklahoma", "nickname": "Red River Rivalry", "teams": ("TEX", "OU")},
}

_lock = threading.Lock()
_games: list["NcaafGame"] | None = None


@dataclass(frozen=True, slots=True)
class NcaafGame:
    season: int
    week: int
    game_type: str
    home: str
    away: str
    home_score: int
    away_score: int
    label: str = ""

    @property
    def winner(self) -> str | None:
        if self.home_score == self.away_score:
            return None
        return self.home if self.home_score > self.away_score else self.away

    @property
    def loser(self) -> str | None:
        if self.home_score == self.away_score:
            return None
        return self.away if self.home_score > self.away_score else self.home


# cfbfastR schedule files before 2023 omit postseason rows.
_HISTORICAL_BOWLS: tuple[NcaafGame, ...] = (
    NcaafGame(2001, 99, "bowl", "UTAH", "USC", 10, 6),
    NcaafGame(2001, 99, "bowl", "BYU", "Louisville", 10, 28),
    NcaafGame(2003, 99, "bowl", "UTAH", "Southern Miss", 17, 0),
    NcaafGame(2004, 99, "bowl", "UTAH", "Pittsburgh", 35, 7),
    NcaafGame(2005, 99, "bowl", "UTAH", "Georgia Tech", 38, 10),
    NcaafGame(2005, 99, "bowl", "BYU", "California", 28, 35),
    NcaafGame(2006, 99, "bowl", "UTAH", "Tulsa", 25, 13),
    NcaafGame(2006, 99, "bowl", "BYU", "Oregon", 38, 8),
    NcaafGame(2007, 99, "bowl", "UTAH", "Navy", 35, 32),
    NcaafGame(2007, 99, "bowl", "BYU", "UCLA", 17, 16),
    NcaafGame(2008, 99, "bowl", "UTAH", "Alabama", 31, 17),
    NcaafGame(2008, 99, "bowl", "BYU", "Arizona", 21, 31),
    NcaafGame(2009, 99, "bowl", "UTAH", "California", 37, 27),
    NcaafGame(2009, 99, "bowl", "BYU", "Oregon State", 44, 20),
    NcaafGame(2010, 99, "bowl", "UTAH", "Boise State", 3, 26),
    NcaafGame(2010, 99, "bowl", "BYU", "UTEP", 52, 24),
    NcaafGame(2011, 99, "bowl", "UTAH", "Georgia Tech", 30, 27),
    NcaafGame(2011, 99, "bowl", "BYU", "Tulsa", 24, 21),
    NcaafGame(2012, 99, "bowl", "BYU", "San Diego State", 23, 6),
    NcaafGame(2013, 99, "bowl", "BYU", "Washington", 16, 31),
    NcaafGame(2014, 99, "bowl", "UTAH", "Colorado State", 45, 10),
    NcaafGame(2014, 99, "bowl", "BYU", "Memphis", 48, 55),
    NcaafGame(2015, 99, "bowl", "UTAH", "BYU", 35, 28),
    NcaafGame(2016, 99, "bowl", "UTAH", "Indiana", 26, 24),
    NcaafGame(2016, 99, "bowl", "BYU", "Wyoming", 24, 21),
    NcaafGame(2017, 99, "bowl", "UTAH", "West Virginia", 30, 14),
    NcaafGame(2018, 99, "bowl", "UTAH", "Northwestern", 20, 31),
    NcaafGame(2018, 99, "bowl", "BYU", "Western Michigan", 49, 18),
    NcaafGame(2019, 99, "bowl", "UTAH", "Texas", 10, 38),
    NcaafGame(2019, 99, "bowl", "BYU", "Hawaii", 34, 38),
    NcaafGame(2020, 99, "bowl", "BYU", "UCF", 49, 23),
    NcaafGame(2021, 99, "bowl", "UTAH", "Ohio State", 45, 48),
    NcaafGame(2021, 99, "bowl", "BYU", "UAB", 28, 31),
    NcaafGame(2022, 99, "bowl", "UTAH", "Penn State", 21, 35),
    NcaafGame(2022, 99, "bowl", "BYU", "SMU", 24, 23),
)


def _cache_path(season: int) -> str:
    return os.path.join(CACHE_DIR, "v2", f"{season}.csv")


def _parse_source(text: str) -> list[NcaafGame]:
    games: list[NcaafGame] = []
    for row in csv.DictReader(io.StringIO(text)):
        home_code = _SOURCE_TO_CODE.get(row.get("home_team", ""))
        away_code = _SOURCE_TO_CODE.get(row.get("away_team", ""))
        if not home_code and not away_code:
            continue
        if not row.get("home_points") or not row.get("away_points"):
            continue
        try:
            games.append(
                NcaafGame(
                    season=int(row["season"]),
                    week=int(row["week"]),
                    game_type=(
                        "bowl" if row.get("season_type", "").lower() == "postseason"
                        else "regular"
                    ),
                    home=home_code or row["home_team"],
                    away=away_code or row["away_team"],
                    home_score=int(float(row["home_points"])),
                    away_score=int(float(row["away_points"])),
                )
            )
        except (KeyError, ValueError):
            continue
    return games


def _read_cache(path: str) -> list[NcaafGame]:
    with open(path, encoding="utf-8", newline="") as handle:
        return [
            NcaafGame(
                season=int(row["season"]),
                week=int(row["week"]),
                game_type=row["game_type"],
                home=row["home"],
                away=row["away"],
                home_score=int(row["home_score"]),
                away_score=int(row["away_score"]),
            )
            for row in csv.DictReader(handle)
        ]


def _load_season(season: int, current_season: int) -> list[NcaafGame]:
    path = _cache_path(season)
    fresh = os.path.exists(path) and (
        season < current_season or time.time() - os.path.getmtime(path) < CURRENT_SEASON_TTL
    )
    if fresh:
        return _read_cache(path)

    try:
        response = httpx.get(SCHEDULE_URL.format(season=season), timeout=60.0)
        response.raise_for_status()
        games = _parse_source(response.content.decode("utf-8-sig", errors="replace"))
    except Exception as exc:  # noqa: BLE001 - retain every available season
        log.warning("Could not load NCAAF schedule for %s: %s", season, exc)
        return _read_cache(path) if os.path.exists(path) else []

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        fields = ("season", "week", "game_type", "home", "away", "home_score", "away_score")
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: getattr(game, field) for field in fields} for game in games)
    return games


def get_ncaaf_games() -> list[NcaafGame]:
    global _games
    with _lock:
        if _games is not None:
            return _games
        current_season = dt.date.today().year
        load_team_histories(tuple(NCAAF_TEAMS))
        games = [
            game
            for season in range(NCAAF_START_SEASON, current_season + 1)
            for game in _load_season(season, current_season)
        ]
        existing_bowls = {
            (game.season, frozenset((game.home, game.away)))
            for game in games
            if game.game_type == "bowl"
        }
        games.extend(
            game
            for game in _HISTORICAL_BOWLS
            if (game.season, frozenset((game.home, game.away))) not in existing_bowls
        )
        existing_bowl_teams = {
            (game.season, team)
            for game in games
            if game.game_type == "bowl"
            for team in NCAAF_TEAMS
            if team in (game.home, game.away)
        }
        for team, seasons in BOWL_OUTCOMES.items():
            for season, outcomes in seasons.items():
                if season < NCAAF_START_SEASON or (season, team) in existing_bowl_teams:
                    continue
                for index, outcome in enumerate(outcomes):
                    opponent = f"BOWL-{team}-{index}"
                    home_score, away_score = (
                        (1, 0) if outcome == "W" else (0, 1) if outcome == "L" else (0, 0)
                    )
                    games.append(
                        NcaafGame(season, 99 + index, "bowl", team, opponent, home_score, away_score)
                    )
        games.sort(key=lambda game: (game.season, game.week))
        games = _historical_games() + games
        _games = games
        log.info("Loaded %d NCAAF games", len(games))
        return games


def _historical_games() -> list[NcaafGame]:
    """Pre-2001 games from the historical scores pages, de-duplicated across programs."""
    seen: set[tuple[int, int, frozenset[str], frozenset[int]]] = set()
    games: list[NcaafGame] = []
    for team_games in load_historical_games(tuple(NCAAF_TEAMS)).values():
        for game in team_games:
            if game.season >= NCAAF_START_SEASON:
                continue
            key = (game.season, game.week, frozenset((game.team, game.opponent)),
                   frozenset((game.points_for, game.points_against)))
            if key in seen:
                continue
            seen.add(key)
            games.append(NcaafGame(
                season=game.season,
                week=game.week,
                game_type="bowl" if game.is_bowl else "regular",
                home=game.team,
                away=game.opponent,
                home_score=game.points_for,
                away_score=game.points_against,
                label=game.postseason_name if game.is_bowl else _date_label(game.date),
            ))
    games.sort(key=lambda game: (game.season, game.week))
    return games


def _date_label(date: str) -> str:
    month, _, day = date.partition("/")
    try:
        return f"{dt.date(2000, int(month), 1):%b} {int(day)}"
    except ValueError:
        return date


def _mode_allowed(game: NcaafGame, mode: str) -> bool:
    return mode == "all" or game.game_type == mode


def _ncaaf_events(games: list[NcaafGame], teams: tuple[str, ...]) -> list[dict]:
    championships = load_championships(teams)
    events = []
    for team in teams:
        for season, kind in championships.get(team, {}).items():
            events.append({
                "team": team, "season": season, "week": None, "anchor": END,
                "kind": "title" if kind == "national" else "conference",
                "label": "National champions" if kind == "national" else "Conference champions",
                "priority": 1 if kind == "national" else 2,
            })

        records = {
            season: record for season, record in SEASON_RECORDS.get(team, {}).items()
            if season < NCAAF_START_SEASON
        }
        for game in games:
            if team in (game.home, game.away) and game.season >= NCAAF_START_SEASON:
                wins, losses, ties = records.get(game.season, (0, 0, 0))
                records[game.season] = (
                    wins + (game.winner == team),
                    losses + (game.loser == team),
                    ties + (game.winner is None),
                )
        for season, (wins, losses, ties) in records.items():
            if losses == 0 and wins >= 6:
                record = f"{wins}-0" + (f"-{ties}" if ties else "")
                events.append({
                    "team": team, "season": season, "week": None, "anchor": END,
                    "kind": "season", "label": f"Undefeated season ({record})", "priority": 2,
                })
    return events


def build_ncaaf_records(
    games: list[NcaafGame],
    start_season: int,
    end_season: int,
    game_mode: str,
    rivalry_id: str,
) -> dict:
    rivalry = RIVALRIES[rivalry_id]
    teams = tuple(rivalry["teams"])
    load_team_histories(teams)

    if game_mode == "head_to_head":
        return _build_head_to_head(games, start_season, end_season, rivalry_id, teams)

    scoped = [
        game for game in games
        if start_season <= game.season <= end_season
        and _mode_allowed(game, game_mode)
        and any(team in (game.home, game.away) for team in teams)
    ]
    buckets: dict[tuple[int, int, int], list[NcaafGame]] = {}
    for game in scoped:
        phase = 1 if game.game_type == "bowl" else 0
        buckets.setdefault((game.season, phase, game.week), []).append(game)

    values = {team: 0 for team in teams}
    stats = {team: {"wins": 0, "losses": 0, "ties": 0, "values": []} for team in teams}
    steps = []

    # Seasons missing from a program's own game-by-game page fall back to its season record.
    covered = {
        (team, game.season)
        for team, team_games in load_historical_games(teams).items()
        for game in team_games
    } | {(team, game.season) for game in games if game.season >= NCAAF_START_SEASON
         for team in (game.home, game.away)}
    fallback: dict[int, dict[str, tuple[int, int, int]]] = {}
    for team in teams:
        for season, record in SEASON_RECORDS.get(team, {}).items():
            if (
                start_season <= season <= min(end_season, NCAAF_START_SEASON - 1)
                and (team, season) not in covered
            ):
                fallback.setdefault(season, {})[team] = record
    for season in fallback:
        buckets.setdefault((season, 2, 0), [])

    for season, phase, week in sorted(buckets):
        if phase == 2:
            steps.append({"season": season, "week": 0, "label": f"{season} Season"})
            for team, (wins, losses, ties) in fallback[season].items():
                bowls = BOWL_OUTCOMES.get(team, {}).get(season, ())
                if game_mode == "regular" and bowls:
                    wins -= bowls.count("W")
                    losses -= bowls.count("L")
                    ties -= bowls.count("T")
                elif game_mode == "bowl":
                    wins, losses, ties = bowls.count("W"), bowls.count("L"), bowls.count("T")
                stats[team]["wins"] += wins
                stats[team]["losses"] += losses
                stats[team]["ties"] += ties
                values[team] += wins - losses
            for team in teams:
                stats[team]["values"].append(values[team])
            continue

        games_this_week = buckets[(season, phase, week)]
        first = games_this_week[0]
        steps.append({
            "season": season,
            "week": week,
            "label": f"{season} "
            + (first.label or ("Bowl" if first.game_type == "bowl" else f"Wk {week}")),
        })
        for game in games_this_week:
            for team in teams:
                if team not in (game.home, game.away) or (team, season) not in covered:
                    continue
                if game.winner is None:
                    stats[team]["ties"] += 1
                elif game.winner == team:
                    stats[team]["wins"] += 1
                    values[team] += 1
                else:
                    stats[team]["losses"] += 1
                    values[team] -= 1
        for team in teams:
            stats[team]["values"].append(values[team])

    return {
        "start_season": start_season,
        "end_season": end_season,
        "game_mode": game_mode,
        "rivalry_id": rivalry_id,
        "steps": steps,
        "events": place_events(_ncaaf_events(games, teams), steps),
        "series": [
            {"team": team, **stats[team], "final": values[team]}
            for team in teams
        ],
    }


def _build_head_to_head(
    games: list[NcaafGame],
    start_season: int,
    end_season: int,
    rivalry_id: str,
    teams: tuple[str, str],
) -> dict:
    entries: list[tuple[int, int, str | None]] = [
        (season, order, winner)
        for season, order, winner, first, second in load_head_to_head(rivalry_id)
        if season < NCAAF_START_SEASON
        and start_season <= season <= end_season
        and {first, second} == set(teams)
    ]
    modern = [
        game for game in games
        if game.season >= NCAAF_START_SEASON
        and start_season <= game.season <= end_season
        and {game.home, game.away} == set(teams)
    ]
    order_by_season: dict[int, int] = {}
    for game in sorted(modern, key=lambda item: (item.season, item.week)):
        order = order_by_season.get(game.season, 0)
        order_by_season[game.season] = order + 1
        entries.append((game.season, order, game.winner))
    entries.sort(key=lambda item: (item[0], item[1]))

    values = {team: 0 for team in teams}
    stats = {team: {"wins": 0, "losses": 0, "ties": 0, "values": []} for team in teams}
    steps = []
    for season, order, winner in entries:
        suffix = f" {order + 1}" if sum(1 for item in entries if item[0] == season) > 1 else ""
        steps.append({"season": season, "week": order, "label": f"{season} H2H{suffix}"})
        for team in teams:
            if winner is None:
                stats[team]["ties"] += 1
            elif winner == team:
                stats[team]["wins"] += 1
                values[team] += 1
            else:
                stats[team]["losses"] += 1
                values[team] -= 1
            stats[team]["values"].append(values[team])
    return {
        "start_season": start_season,
        "end_season": end_season,
        "game_mode": "head_to_head",
        "rivalry_id": rivalry_id,
        "steps": steps,
        "events": place_events(_ncaaf_events(games, teams), steps),
        "series": [{"team": team, **stats[team], "final": values[team]} for team in teams],
    }
