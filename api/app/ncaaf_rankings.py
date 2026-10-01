"""Weekly AP Poll rankings for the tracked college programs.

Wikipedia publishes one rankings article per season containing the full week-by-week AP
Poll table. Each poll is turned into a height: a team ranked #1 sits at 25, #25 sits at
1, and an unranked team sits at 0.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import re
import threading
import time

import httpx

from .ncaaf_history import HISTORY_CACHE_DIR

log = logging.getLogger(__name__)

AP_POLL_START = 1936
POLL_SIZE = 25
CACHE_DIR = os.path.join(HISTORY_CACHE_DIR, "rankings")
CURRENT_SEASON_TTL = int(os.environ.get("GAMES_CACHE_TTL_SECONDS", str(12 * 60 * 60)))
QUERY_URL = "https://en.wikipedia.org/w/api.php"

# Article titles changed as the NCAA renamed its divisions.
PAGE_PATTERNS = (
    "{season} NCAA Division I FBS football rankings",
    "{season} NCAA Division I-A football rankings",
    "{season} NCAA Division I football rankings",
    "{season} NCAA University Division football rankings",
    "{season} college football rankings",
)

# Poll display name -> our team code.
POLL_NAMES = {
    "Michigan": "MICH",
    "Ohio State": "OSU",
    "Alabama": "BAMA",
    "Auburn": "AUB",
    "Texas": "TEX",
    "Oklahoma": "OU",
    "Utah": "UTAH",
    "BYU": "BYU",
    "Brigham Young": "BYU",
}

_seasons: dict[int, dict[int, dict[str, int]] | None] = {}
_dates: dict[int, dict[int, str]] = {}
_finals: dict[int, int | None] = {}
_lock = threading.Lock()


def _sections(text: str) -> list[tuple[str, str]]:
    parts = re.split(r"^==+\s*(.+?)\s*==+\s*$", text, flags=re.M)
    return list(zip(parts[1::2], parts[2::2]))


def _heading_before(text: str, offset: int) -> str:
    headings = [m for m in re.finditer(r"^==+\s*(.+?)\s*==+\s*$", text, flags=re.M)
                if m.start() < offset]
    return headings[-1].group(1) if headings else ""


def _is_ap(heading: str) -> bool:
    return bool(re.match(r"\s*AP\b", heading, re.I))


def _pick_ap_block(text: str, blocks: list[tuple[int, str]]) -> str:
    """Prefer a table under an "AP Poll" heading; otherwise take the first one."""
    for offset, block in blocks:
        if _is_ap(_heading_before(text, offset)):
            return block
    return blocks[0][1] if blocks else ""


def _template_blocks(text: str) -> list[tuple[int, str]]:
    blocks = []
    for match in re.finditer(r"\{\{ColPollTable", text):
        end = text.find("\n}}", match.start())
        blocks.append((match.start(), text[match.start() : end if end > 0 else len(text)]))
    return blocks


def _grid_blocks(text: str) -> list[tuple[int, str]]:
    blocks = []
    for match in re.finditer(r"^\{\|", text, flags=re.M):
        end = text.find("\n|}", match.start())
        block = text[match.start() : end if end > 0 else len(text)]
        if re.search(r"^!\s*1\.", block, flags=re.M) and "Week 1" in block:
            blocks.append((match.start(), block))
    return blocks


def _team_name(value: str) -> str:
    value = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", value)
    value = re.sub(r"\[\[([^\]]*)\]\]", r"\1", value)
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"\{\{[^{}]*\}\}", "", value)
    value = value.split("(")[0]  # win-loss record and first-place votes
    value = value.replace("'''", "").replace("''", "").replace("т", "")
    return value.replace("&amp;", "&").strip(" *†‡\u00a0")


def _parse_template(block: str) -> tuple[dict[int, dict[str, int]], dict[int, str], int | None]:
    filled: set[int] = set()
    ranked: dict[int, dict[str, int]] = {}
    for week, rank, value in re.findall(r"\|\s*Week(\d+)-(\d+)\s*=([^\n]*)", block):
        if not value.strip():
            continue  # placeholder row for a poll that has not been released
        filled.add(int(week))
        code = POLL_NAMES.get(_team_name(value))
        if code and int(rank) <= POLL_SIZE:
            ranked.setdefault(int(week), {})[code] = int(rank)

    polls = {week: ranked.get(week, {}) for week in sorted(filled)}
    dates: dict[int, str] = {}
    for week, value in re.findall(r"\|\s*Week(\d+)Date\s*=([^\n]*)", block):
        label = _team_name(re.sub(r"<ref.*", "", value, flags=re.S)).strip()
        if label and int(week) in polls:
            dates[int(week)] = label

    header = re.search(r"\|\s*Week(\d+)\s*=[^\n]*\(Final\)", block)
    final = int(header.group(1)) if header else None
    return polls, dates, (final if final in polls else None)


def _cell_text(line: str) -> str:
    line = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", line)
    line = re.sub(r"\[\[([^\]]*)\]\]", r"\1", line)
    return _team_name(line.lstrip("|").split("|")[-1])


def _parse_grid(block: str) -> tuple[dict[int, dict[str, int]], dict[int, str], int | None]:
    """Older articles use a plain table: one row per rank, one column per poll."""
    header = next((line for line in block.splitlines() if "Week 1" in line), "")
    cells = header.split("!!")
    dates: dict[int, str] = {}
    final: int | None = None
    for index, cell in enumerate(cells, start=1):
        if "(Final)" in cell:
            final = index
        date = re.search(r"<br\s*/?>\s*([^!<]+)", cell)
        label = (date.group(1) if date else re.sub(r"<[^>]+>|!", " ", cell)).strip()
        if label:
            dates[index] = re.sub(r"\s+", " ", label)

    filled: set[int] = set()
    ranked: dict[int, dict[str, int]] = {}
    for row in re.split(r"^\|-.*$", block, flags=re.M):
        lines = [line for line in row.splitlines() if line.strip()]
        rank_match = next(
            (re.match(r"^!\s*(\d+)\.", line) for line in lines if line.startswith("!")), None
        )
        if not rank_match:
            continue
        rank = int(rank_match.group(1))
        for index, line in enumerate((l for l in lines if l.startswith("|")), start=1):
            name = _cell_text(line)
            if not name:
                continue
            filled.add(index)
            code = POLL_NAMES.get(name)
            if code and rank <= POLL_SIZE:
                ranked.setdefault(index, {})[code] = rank

    polls = {week: ranked.get(week, {}) for week in sorted(filled)}
    dates = {week: label for week, label in dates.items() if week in polls}
    return polls, dates, (final if final in polls else None)


def parse_rankings(text: str) -> tuple[dict[int, dict[str, int]], dict[int, str], int | None]:
    """Poll number -> {team code: rank}, poll number -> date label, and the final poll."""
    block = _pick_ap_block(text, _template_blocks(text))
    if block:
        return _parse_template(block)
    block = _pick_ap_block(text, _grid_blocks(text))
    return _parse_grid(block) if block else ({}, {}, None)


def _season_text(season: int) -> str:
    """Wikitext of whichever rankings article exists for this season."""
    path = os.path.join(CACHE_DIR, f"{season}.txt")
    # An in-progress season gains a poll every week, so its page is refetched.
    stale = season >= dt.date.today().year and (
        not os.path.exists(path) or time.time() - os.path.getmtime(path) > CURRENT_SEASON_TTL
    )
    if os.path.exists(path) and not stale:
        with open(path, encoding="utf-8") as handle:
            return handle.read()

    titles = "|".join(pattern.format(season=season) for pattern in PAGE_PATTERNS)
    params = {
        "action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main",
        "titles": titles, "redirects": "1", "format": "json", "formatversion": "2",
    }
    text = ""
    for attempt in range(5):
        response = httpx.get(
            QUERY_URL, params=params,
            headers={"User-Agent": "FootballRecordWalk/1.0"}, timeout=60.0,
        )
        if response.status_code == 429:
            time.sleep(1.5 * 2**attempt)
            continue
        response.raise_for_status()
        pages = response.json().get("query", {}).get("pages", [])
        candidates = [
            page["revisions"][0]["slots"]["main"]["content"]
            for page in pages if page.get("revisions")
        ]
        text = max((c for c in candidates if _has_poll(c)), key=len, default="")
        break
    else:
        raise RuntimeError(f"Wikipedia kept rate-limiting rankings requests for {season}")

    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return text


def _has_poll(text: str) -> bool:
    return bool(_template_blocks(text) or _grid_blocks(text))


def _load_season(season: int) -> dict[int, dict[str, int]] | None:
    try:
        text = _season_text(season)
    except Exception as exc:  # noqa: BLE001 - other seasons still load
        log.warning("Could not load %s rankings: %s", season, exc)
        return None
    if not text:
        return None
    polls, dates, final = parse_rankings(text)
    if not polls:
        return None
    _dates[season] = dates
    _finals[season] = final
    return polls


def get_season_rankings(season: int) -> dict[int, dict[str, int]] | None:
    with _lock:
        if season not in _seasons:
            _seasons[season] = _load_season(season)
        return _seasons[season]


def poll_date(season: int, poll: int) -> str:
    return _dates.get(season, {}).get(poll, "")


def height(rank: int | None) -> int:
    """#1 is the top of the chart; unranked sits on the baseline."""
    return 0 if rank is None else POLL_SIZE + 1 - rank


def build_rankings(
    teams: tuple[str, ...],
    start_season: int,
    end_season: int,
    latest_season: int,
) -> dict:
    steps: list[dict] = []
    values: dict[str, list[int]] = {team: [] for team in teams}
    stats = {
        team: {"polls": 0, "ranked": 0, "best": None, "weeks_at_1": 0, "final": 0}
        for team in teams
    }
    missing: list[int] = []

    for season in range(max(start_season, AP_POLL_START), min(end_season, latest_season) + 1):
        polls = get_season_rankings(season)
        if not polls:
            missing.append(season)
            continue
        ordered = sorted(polls)
        for poll in ordered:
            date = poll_date(season, poll)
            final = poll == _finals.get(season)
            steps.append({
                "season": season,
                "week": poll,
                "label": f"{season} " + ("Final" if final else date or f"Poll {poll}"),
            })
            for team in teams:
                rank = polls[poll].get(team)
                values[team].append(height(rank))
                entry = stats[team]
                entry["polls"] += 1
                if rank is not None:
                    entry["ranked"] += 1
                    entry["weeks_at_1"] += rank == 1
                    entry["best"] = rank if entry["best"] is None else min(entry["best"], rank)

    for team in teams:
        stats[team]["final"] = values[team][-1] if values[team] else 0

    return {
        "start_season": start_season,
        "end_season": end_season,
        "poll": "AP",
        "poll_size": POLL_SIZE,
        "steps": steps,
        "series": [{"team": team, "values": values[team], **stats[team]} for team in teams],
        "missing_seasons": missing,
        "first_poll_season": AP_POLL_START,
    }
