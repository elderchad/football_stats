"""Loads NFL game results and caches them on disk.

Two sources are stitched together:

* 1920-1998 comes from FiveThirtyEight's Elo dataset (read from the Internet Archive,
  since FiveThirtyEight shut down). It already normalises franchises onto their modern
  abbreviations and carries starting quarterback names from 1950.
* 1999-present comes from nflverse, which is still maintained and updated weekly.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import logging
import os
import threading
import time
from collections import defaultdict
from dataclasses import dataclass

import httpx

from .teams import normalize

log = logging.getLogger(__name__)

GAMES_URLS = (
    "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv",
    "http://www.habitatring.com/games.csv",
)

HISTORICAL_URLS = (
    "https://web.archive.org/web/2023id_/https://projects.fivethirtyeight.com/nfl-api/nfl_elo.csv",
    "https://web.archive.org/web/20230601000000id_/https://projects.fivethirtyeight.com/nfl-api/nfl_elo.csv",
)

MODERN_ERA_START = 1999

CACHE_PATH = os.environ.get("GAMES_CACHE_PATH", "/data/games.csv")
HISTORICAL_CACHE_PATH = os.environ.get("HISTORICAL_CACHE_PATH", "/data/nfl_elo.csv")
CACHE_TTL_SECONDS = int(os.environ.get("GAMES_CACHE_TTL_SECONDS", str(12 * 60 * 60)))
HISTORICAL_TTL_SECONDS = 365 * 24 * 60 * 60  # the archived file never changes

REGULAR_SEASON = "REG"
POSTSEASON_TYPES = ("WC", "DIV", "CON", "SB")
ELO_PLAYOFF_ROUNDS = {"w": "WC", "d": "DIV", "c": "CON", "s": "SB"}

_lock = threading.Lock()
_games: list["Game"] | None = None


@dataclass(frozen=True, slots=True)
class Game:
    season: int
    week: int
    game_type: str
    home: str
    away: str
    home_score: int
    away_score: int
    home_qb: str = ""
    away_qb: str = ""

    @property
    def is_tie(self) -> bool:
        return self.home_score == self.away_score

    @property
    def winner(self) -> str | None:
        if self.is_tie:
            return None
        return self.home if self.home_score > self.away_score else self.away

    @property
    def loser(self) -> str | None:
        if self.is_tie:
            return None
        return self.away if self.home_score > self.away_score else self.home


def _cache_is_fresh(path: str, ttl: int) -> bool:
    try:
        age = time.time() - os.path.getmtime(path)
    except OSError:
        return False
    return age < ttl


def _download(urls: tuple[str, ...]) -> str:
    last_error: Exception | None = None
    for url in urls:
        try:
            log.info("Downloading %s", url)
            response = httpx.get(url, timeout=120.0, follow_redirects=True)
            response.raise_for_status()
            if not response.text.lstrip().lower().startswith(("date,", "game_id,")):
                raise ValueError("response was not the expected CSV")
            return response.text
        except Exception as exc:  # noqa: BLE001 - try every mirror before failing
            log.warning("Failed to download from %s: %s", url, exc)
            last_error = exc
    raise RuntimeError("Could not download game data") from last_error


def _read_source(urls: tuple[str, ...], cache_path: str, ttl: int) -> str:
    if _cache_is_fresh(cache_path, ttl):
        with open(cache_path, encoding="utf-8") as handle:
            return handle.read()

    try:
        text = _download(urls)
    except RuntimeError:
        if os.path.exists(cache_path):
            log.warning("Download failed; falling back to stale cache at %s", cache_path)
            with open(cache_path, encoding="utf-8") as handle:
                return handle.read()
        raise

    os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
    with open(cache_path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    return text


def _parse_modern(text: str) -> list[Game]:
    games: list[Game] = []
    for row in csv.DictReader(io.StringIO(text)):
        home_score, away_score = row.get("home_score"), row.get("away_score")
        if not home_score or not away_score:
            continue  # game not played yet
        try:
            season = int(row["season"])
            if season < MODERN_ERA_START:
                continue
            games.append(
                Game(
                    season=season,
                    week=int(row["week"]),
                    game_type=(row.get("game_type") or REGULAR_SEASON).strip().upper(),
                    home=normalize(row["home_team"]),
                    away=normalize(row["away_team"]),
                    home_score=int(float(home_score)),
                    away_score=int(float(away_score)),
                    home_qb=(row.get("home_qb_name") or "").strip(),
                    away_qb=(row.get("away_qb_name") or "").strip(),
                )
            )
        except (KeyError, ValueError):
            continue
    return games


def _week_numbers(dates: list[dt.date]) -> dict[dt.date, int]:
    """Cluster a season's playing dates into weeks; pre-1999 rows have no week column."""
    weeks: dict[dt.date, int] = {}
    week = 0
    anchor: dt.date | None = None
    for date in sorted(dates):
        if anchor is None or (date - anchor).days >= 5:
            week += 1
            anchor = date
        weeks[date] = week
    return weeks


def _parse_historical(text: str) -> list[Game]:
    rows: list[tuple[dt.date, dict[str, str]]] = []
    by_season: dict[int, set[dt.date]] = defaultdict(set)

    for row in csv.DictReader(io.StringIO(text)):
        if not row.get("score1") or not row.get("score2"):
            continue
        try:
            season = int(row["season"])
            if season >= MODERN_ERA_START:
                continue
            date = dt.date.fromisoformat(row["date"])
        except (KeyError, ValueError):
            continue
        rows.append((date, row))
        by_season[season].add(date)

    week_lookup = {season: _week_numbers(list(dates)) for season, dates in by_season.items()}

    games: list[Game] = []
    for date, row in rows:
        season = int(row["season"])
        round_code = (row.get("playoff") or "").strip().lower()
        try:
            games.append(
                Game(
                    season=season,
                    week=week_lookup[season][date],
                    game_type=ELO_PLAYOFF_ROUNDS.get(round_code, REGULAR_SEASON),
                    home=normalize(row["team1"]),
                    away=normalize(row["team2"]),
                    home_score=int(float(row["score1"])),
                    away_score=int(float(row["score2"])),
                    home_qb=(row.get("qb1") or "").strip(),
                    away_qb=(row.get("qb2") or "").strip(),
                )
            )
        except (KeyError, ValueError):
            continue
    return games


def _load() -> list[Game]:
    games = _parse_modern(_read_source(GAMES_URLS, CACHE_PATH, CACHE_TTL_SECONDS))
    try:
        games += _parse_historical(
            _read_source(HISTORICAL_URLS, HISTORICAL_CACHE_PATH, HISTORICAL_TTL_SECONDS)
        )
    except RuntimeError:
        log.warning("Historical (pre-1999) data unavailable; serving the modern era only")

    games.sort(key=lambda g: (g.season, g.week))
    return games


def get_games(refresh: bool = False) -> list[Game]:
    global _games
    with _lock:
        if _games is None or refresh:
            _games = _load()
            log.info("Loaded %d completed games", len(_games))
        return _games
