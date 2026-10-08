"""Game-by-game college football history from James Howell's historical scores database.

Each program page lists every game it played in seasons Howell rates, with date, site,
opponent, result, score and (for postseason games) the bowl name. It fills the pre-2001
gap left by cfbfastR, and doubles as an independent source for the data audit.
"""

from __future__ import annotations

import datetime as dt
import html
import logging
import os
import re
import time
from dataclasses import dataclass

import httpx

from .ncaaf_history import HISTORY_CACHE_DIR

log = logging.getLogger(__name__)

SCORES_URL = "https://www.jhowell.net/cf/scores/{page}.htm"
CACHE_TTL_SECONDS = 30 * 24 * 60 * 60

SCORE_PAGES = {
    "UTAH": "Utah",
    "BYU": "BrighamYoung",
    "MICH": "Michigan",
    "OSU": "OhioState",
    "BAMA": "Alabama",
    "AUB": "Auburn",
    "TEX": "Texas",
    "OU": "Oklahoma",
}
OPPONENT_CODES = {
    "Utah": "UTAH", "Brigham Young": "BYU", "Michigan": "MICH", "Ohio State": "OSU",
    "Alabama": "BAMA", "Auburn": "AUB", "Texas": "TEX", "Oklahoma": "OU",
}


@dataclass(frozen=True, slots=True)
class HistoricalGame:
    team: str
    season: int
    order: int
    date: str
    week: int
    opponent: str
    result: str
    points_for: int
    points_against: int
    postseason_name: str

    @property
    def is_bowl(self) -> bool:
        name = self.postseason_name
        return "Bowl" in name or name.startswith(("BCS", "College Football Playoff"))


_games: dict[str, list[HistoricalGame]] = {}


def _page_text(code: str) -> str:
    page = SCORE_PAGES[code]
    path = os.path.join(HISTORY_CACHE_DIR, "howell", f"{page}.htm")
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < CACHE_TTL_SECONDS:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    try:
        response = httpx.get(SCORES_URL.format(page=page), timeout=60.0, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPError:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as handle:
                return handle.read()
        raise
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(response.text)
    return response.text


def _week(season: int, date: str, previous: int) -> int:
    """Week of the season counted from August 1, so every program shares one calendar."""
    match = re.fullmatch(r"(\d{1,2})/(\d{1,2})", date)
    if not match:
        return previous + 1
    month, day = int(match.group(1)), int(match.group(2))
    try:
        played = dt.date(season if month >= 7 else season + 1, month, day)
    except ValueError:
        return previous + 1
    return max(1, (played - dt.date(season, 8, 1)).days // 7 + 1)


def parse_page(code: str, text: str) -> list[HistoricalGame]:
    games: list[HistoricalGame] = []
    parts = re.split(r"<a name=(\d{4})>", text)
    for year, body in zip(parts[1::2], parts[2::2]):
        season = int(year)
        week = 0
        for row in re.findall(r"<tr>(.*?)</tr>", body, re.S):
            cells = [
                html.unescape(re.sub(r"<[^>]+>", "", cell)).strip()
                for cell in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
            ]
            if len(cells) < 6 or cells[3] not in ("W", "L", "T"):
                continue
            try:
                points_for, points_against = int(cells[4]), int(cells[5])
            except ValueError:
                continue
            opponent = re.sub(r"\s*\([^)]*\)\s*$", "", cells[2]).lstrip("*").strip()
            week = _week(season, cells[0], week)
            games.append(HistoricalGame(
                team=code,
                season=season,
                order=len(games),
                date=cells[0],
                week=week,
                opponent=OPPONENT_CODES.get(opponent, opponent),
                result=cells[3],
                points_for=points_for,
                points_against=points_against,
                postseason_name=cells[7] if len(cells) > 7 else "",
            ))
    return games


def load_historical_games(team_codes: tuple[str, ...]) -> dict[str, list[HistoricalGame]]:
    """Team code -> every game on that program's page (empty if the page is unavailable)."""
    for code in team_codes:
        if code in _games or code not in SCORE_PAGES:
            continue
        try:
            _games[code] = parse_page(code, _page_text(code))
        except Exception as exc:  # noqa: BLE001 - season-level records remain as a fallback
            log.warning("Could not load historical scores for %s: %s", code, exc)
            _games[code] = []
    return {code: _games.get(code, []) for code in team_codes}
