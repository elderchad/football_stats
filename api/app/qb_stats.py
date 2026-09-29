"""Per-game passing stats (touchdowns and interceptions) for the tracked quarterbacks.

nflverse publishes one weekly player-stats file per season from 1999 onwards. Each file
is filtered down to the quarterbacks we care about and cached; completed seasons are
kept forever, the current season is refreshed on the normal cache interval.
"""

from __future__ import annotations

import csv
import gzip
import io
import logging
import os
import threading
import time

import httpx

from .quarterbacks import QUARTERBACKS
from .teams import normalize

log = logging.getLogger(__name__)

STATS_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/stats_player/"
    "stats_player_week_{season}.csv.gz"
)
STATS_START_SEASON = 1999
STATS_CACHE_DIR = os.environ.get("QB_STATS_CACHE_DIR", "/data/qb_stats")
CURRENT_SEASON_TTL = int(os.environ.get("GAMES_CACHE_TTL_SECONDS", str(12 * 60 * 60)))

_TRACKED = {qb.name.casefold(): qb.id for qb in QUARTERBACKS}

_lock = threading.Lock()
_stats: dict[str, list[dict]] | None = None


def _season_path(season: int) -> str:
    return os.path.join(STATS_CACHE_DIR, "v2", f"{season}.csv")


def _fetch_season(season: int) -> list[dict]:
    url = STATS_URL.format(season=season)
    log.info("Downloading %s", url)
    response = httpx.get(url, timeout=120.0, follow_redirects=True)
    response.raise_for_status()
    text = gzip.decompress(response.content).decode("utf-8")

    rows: list[dict] = []
    for row in csv.DictReader(io.StringIO(text)):
        if (row.get("position") or "").strip().upper() != "QB":
            continue  # e.g. a cornerback who shares a tracked QB's name
        qb_id = _TRACKED.get((row.get("player_display_name") or "").strip().casefold())
        if not qb_id:
            continue
        try:
            rows.append(
                {
                    "qb_id": qb_id,
                    "season": int(row["season"]),
                    "week": int(row["week"]),
                    "season_type": (row.get("season_type") or "REG").strip().upper(),
                    "team": normalize(row.get("team") or ""),
                    "td": int(float(row.get("passing_tds") or 0)),
                    "int": int(float(row.get("passing_interceptions") or 0)),
                }
            )
        except (KeyError, ValueError):
            continue
    return rows


FIELDS = ("qb_id", "season", "week", "season_type", "team", "td", "int")


def _load_season(season: int, is_current: bool) -> list[dict]:
    path = _season_path(season)
    fresh = os.path.exists(path) and (
        not is_current or time.time() - os.path.getmtime(path) < CURRENT_SEASON_TTL
    )
    if fresh:
        with open(path, encoding="utf-8", newline="") as handle:
            return [
                {**row, "season": int(row["season"]), "week": int(row["week"]),
                 "td": int(row["td"]), "int": int(row["int"])}
                for row in csv.DictReader(handle)
            ]

    try:
        rows = _fetch_season(season)
    except Exception as exc:  # noqa: BLE001 - a missing season should not break the rest
        log.warning("Could not load %s passing stats: %s", season, exc)
        return []

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def get_qb_game_stats(latest_season: int) -> dict[str, list[dict]]:
    """qb_id -> per-game passing lines, ordered by season and week."""
    global _stats
    with _lock:
        if _stats is not None:
            return _stats

        by_qb: dict[str, list[dict]] = {}
        for season in range(STATS_START_SEASON, latest_season + 1):
            for row in _load_season(season, is_current=season == latest_season):
                by_qb.setdefault(row["qb_id"], []).append(row)

        for rows in by_qb.values():
            rows.sort(key=lambda row: (row["season"], row["week"]))

        _stats = by_qb
        log.info("Loaded passing stats for %d quarterbacks", len(by_qb))
        return _stats
