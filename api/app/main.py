from __future__ import annotations

import datetime as dt
import logging
import os
import threading

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .audit import run_audit
from .data import get_games
from .ncaaf import NCAAF_TEAMS, RIVALRIES, build_ncaaf_records, get_ncaaf_games
from .ncaaf_history import SEASON_RECORDS, load_head_to_head, load_team_histories
from .ncaaf_rankings import AP_POLL_START, build_rankings, get_season_rankings
from .qb_records import build_qb_records, build_qb_td_int, build_qb_timeline, list_quarterbacks
from .qb_stats import get_qb_game_stats
from .records import build_records
from .teams import TEAMS, describe

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

app = FastAPI(title="Football Record Walk API", version="1.0.0")

allowed_origins = [
    origin.strip()
    for origin in os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.on_event("startup")
def warm_cache() -> None:
    try:
        games = get_games()
    except Exception:  # noqa: BLE001 - keep serving /health so the pod can report the error
        logging.exception("Could not preload game data at startup")
        return

    latest = max((g.season for g in games), default=0)
    threading.Thread(
        target=get_qb_game_stats, args=(latest,), name="qb-stats-warmup", daemon=True
    ).start()
    threading.Thread(target=get_ncaaf_games, name="ncaaf-warmup", daemon=True).start()
    threading.Thread(target=_warm_rankings, name="rankings-warmup", daemon=True).start()


def _warm_rankings() -> None:
    for season in range(AP_POLL_START, dt.date.today().year + 1):
        try:
            get_season_rankings(season)
        except Exception:  # noqa: BLE001 - warm-up must never crash the worker
            logging.exception("Could not warm %s rankings", season)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/audit")
def audit(refresh: bool = False) -> dict:
    return run_audit(refresh)


@app.get("/api/teams")
def list_teams() -> list[dict]:
    games = get_games()
    appearances: dict[str, list[int]] = {}
    for game in games:
        for abbr in (game.home, game.away):
            span = appearances.setdefault(abbr, [game.season, game.season, 0])
            span[0] = min(span[0], game.season)
            span[1] = max(span[1], game.season)
            span[2] += 1

    entries = [
        {
            "abbr": abbr,
            **describe(abbr),
            "first_season": first,
            "last_season": last,
            "games": count,
        }
        for abbr, (first, last, count) in appearances.items()
    ]
    for abbr in TEAMS:
        if abbr not in appearances:
            entries.append(
                {"abbr": abbr, **describe(abbr), "first_season": 0, "last_season": 0, "games": 0}
            )
    entries.sort(key=lambda entry: (entry["defunct"], entry["abbr"]))
    return entries


@app.get("/api/seasons")
def seasons() -> dict:
    games = get_games()
    if not games:
        raise HTTPException(status_code=503, detail="Game data unavailable")
    all_seasons = sorted({g.season for g in games})
    return {"min": all_seasons[0], "max": all_seasons[-1], "seasons": all_seasons}


@app.get("/api/ncaaf/teams")
def ncaaf_teams(
    rivalry: str = Query(default="holy-war", pattern="^(holy-war|the-game|iron-bowl|red-river)$"),
) -> list[dict]:
    team_codes = RIVALRIES[rivalry]["teams"]
    return [
        {"abbr": abbr, "name": team["name"], "color": team["color"]}
        for abbr, team in NCAAF_TEAMS.items()
        if abbr in team_codes
    ]


@app.get("/api/ncaaf/rivalries")
def ncaaf_rivalries() -> list[dict]:
    return [
        {"id": rivalry_id, "name": rivalry["name"], "nickname": rivalry["nickname"]}
        for rivalry_id, rivalry in RIVALRIES.items()
    ]


@app.get("/api/ncaaf/seasons")
def ncaaf_seasons(
    rivalry: str = Query(default="holy-war", pattern="^(holy-war|the-game|iron-bowl|red-river)$"),
) -> dict:
    games = get_ncaaf_games()
    team_codes = tuple(RIVALRIES[rivalry]["teams"])
    load_team_histories(team_codes)
    seasons = sorted(
        {game.season for game in games if any(team in (game.home, game.away) for team in team_codes)}
        | {season for team in team_codes for season in SEASON_RECORDS.get(team, {})}
    )
    if not seasons:
        raise HTTPException(status_code=503, detail="NCAAF game data unavailable")
    return {"min": seasons[0], "max": seasons[-1], "seasons": seasons}


@app.get("/api/ncaaf/records")
def ncaaf_records(
    start_season: int | None = Query(default=None, ge=1870, le=2100),
    end_season: int | None = Query(default=None, ge=1870, le=2100),
    game_mode: str = Query(default="all", pattern="^(all|regular|bowl|head_to_head)$"),
    rivalry: str = Query(default="holy-war", pattern="^(holy-war|the-game|iron-bowl|red-river)$"),
) -> dict:
    games = get_ncaaf_games()
    team_codes = tuple(RIVALRIES[rivalry]["teams"])
    load_team_histories(team_codes)
    seasons = sorted(
        {game.season for game in games if any(team in (game.home, game.away) for team in team_codes)}
        | {season for team in team_codes for season in SEASON_RECORDS.get(team, {})}
        | {season for season, _, _, _, _ in load_head_to_head(rivalry)}
    )
    if not seasons:
        raise HTTPException(status_code=503, detail="NCAAF game data unavailable")
    start = start_season or seasons[0]
    end = end_season or seasons[-1]
    if start > end:
        raise HTTPException(status_code=400, detail="start_season must be <= end_season")
    return build_ncaaf_records(games, start, end, game_mode, rivalry)


@app.get("/api/ncaaf/rankings")
def ncaaf_rankings(
    start_season: int | None = Query(default=None, ge=1870, le=2100),
    end_season: int | None = Query(default=None, ge=1870, le=2100),
    rivalry: str = Query(default="holy-war", pattern="^(holy-war|the-game|iron-bowl|red-river)$"),
) -> dict:
    teams = tuple(RIVALRIES[rivalry]["teams"])
    latest = max((game.season for game in get_ncaaf_games()), default=AP_POLL_START)
    payload = build_rankings(
        teams,
        start_season or AP_POLL_START,
        end_season or latest,
        latest,
    )
    if not payload["steps"]:
        raise HTTPException(status_code=503, detail="AP Poll data unavailable")
    payload["rivalry_id"] = rivalry
    return payload


@app.get("/api/records")
def records(
    start_season: int | None = Query(default=None, ge=1920, le=2100),
    end_season: int | None = Query(default=None, ge=1920, le=2100),
    game_mode: str = Query(default="all", pattern="^(all|regular|playoffs|superbowls)$"),
) -> dict:
    games = get_games()
    if not games:
        raise HTTPException(status_code=503, detail="Game data unavailable")

    available = sorted({g.season for g in games})
    start = start_season or available[0]
    end = end_season or available[-1]
    if start > end:
        raise HTTPException(status_code=400, detail="start_season must be <= end_season")

    payload = build_records(games, start, end, game_mode)
    payload["start_season"] = start
    payload["end_season"] = end
    payload["game_mode"] = game_mode
    return payload


@app.get("/api/quarterbacks")
def quarterbacks() -> list[dict]:
    games = get_games()
    if not games:
        raise HTTPException(status_code=503, detail="Game data unavailable")
    return list_quarterbacks(games)


@app.get("/api/qb-records")
def qb_records(
    ids: str | None = Query(default=None, max_length=1000),
    game_mode: str = Query(default="all", pattern="^(all|regular|playoffs|superbowls)$"),
) -> dict:
    games = get_games()
    if not games:
        raise HTTPException(status_code=503, detail="Game data unavailable")

    wanted = [value for value in (ids or "").split(",") if value.strip()] or None
    return build_qb_records(games, wanted, game_mode)


@app.get("/api/qb-td-int")
def qb_td_int(
    ids: str | None = Query(default=None, max_length=1000),
    game_mode: str = Query(default="all", pattern="^(all|regular|playoffs|superbowls)$"),
    metric: str = Query(default="td_int", pattern="^(td|int|td_int)$"),
) -> dict:
    games = get_games()
    if not games:
        raise HTTPException(status_code=503, detail="Game data unavailable")

    wanted = [value for value in (ids or "").split(",") if value.strip()] or None
    return build_qb_td_int(games, wanted, game_mode, metric)


@app.get("/api/qb-timeline")
def qb_timeline(
    ids: str | None = Query(default=None, max_length=1000),
    game_mode: str = Query(default="all", pattern="^(all|regular|playoffs|superbowls)$"),
    metric: str = Query(default="games", pattern="^(games|td|int|td_int)$"),
) -> dict:
    games = get_games()
    if not games:
        raise HTTPException(status_code=503, detail="Game data unavailable")

    wanted = [value for value in (ids or "").split(",") if value.strip()] or None
    return build_qb_timeline(games, wanted, game_mode, metric)


# Single-image deployments (Render) serve the built front end from the API container.
STATIC_DIR = os.environ.get("STATIC_DIR", "")
if STATIC_DIR and os.path.isdir(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="web")
