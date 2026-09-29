"""Turns game results into cumulative win/loss walk lines."""

from __future__ import annotations

from dataclasses import dataclass, field

from .data import POSTSEASON_TYPES, REGULAR_SEASON, Game
from .events import franchise_events, place_events

GAME_MODES = ("all", "regular", "playoffs", "superbowls")

_events_cache: tuple[int, list[dict]] | None = None


def _cached_franchise_events(games: list[Game]) -> list[dict]:
    global _events_cache
    if _events_cache is None or _events_cache[0] != id(games):
        _events_cache = (id(games), franchise_events(games))
    return _events_cache[1]


def game_type_allowed(game_type: str, mode: str) -> bool:
    if mode == "superbowls":
        return game_type == "SB"
    if mode == "all":
        return game_type == REGULAR_SEASON or game_type in POSTSEASON_TYPES
    if mode == "playoffs":
        return game_type in POSTSEASON_TYPES
    return game_type == REGULAR_SEASON


@dataclass
class Step:
    season: int
    week: int
    label: str


@dataclass
class Series:
    team: str
    values: list[int | None] = field(default_factory=list)
    game_steps: list[int] = field(default_factory=list)
    game_results: list[int] = field(default_factory=list)
    wins: int = 0
    losses: int = 0
    ties: int = 0


def week_label(season: int, week: int, game_type: str) -> str:
    if game_type == REGULAR_SEASON:
        return f"{season} Wk {week}"
    pretty = {"WC": "Wild Card", "DIV": "Divisional", "CON": "Conf Champ", "SB": "Super Bowl"}
    return f"{season} {pretty.get(game_type, game_type)}"


def build_records(
    games: list[Game],
    start_season: int,
    end_season: int,
    game_mode: str,
) -> dict:
    scoped = [
        g
        for g in games
        if start_season <= g.season <= end_season and game_type_allowed(g.game_type, game_mode)
    ]
    if not scoped:
        return {"steps": [], "series": [], "events": []}

    buckets: dict[tuple[int, int], list[Game]] = {}
    for game in scoped:
        buckets.setdefault((game.season, game.week), []).append(game)

    ordered_keys = sorted(buckets)
    steps = [
        Step(season, week, week_label(season, week, buckets[(season, week)][0].game_type))
        for season, week in ordered_keys
    ]

    teams = sorted({t for g in scoped for t in (g.home, g.away)})
    series = {team: Series(team=team) for team in teams}
    current: dict[str, int] = {}

    for step_index, key in enumerate(ordered_keys):
        for game in buckets[key]:
            winner, loser = game.winner, game.loser
            for team in (game.home, game.away):
                current.setdefault(team, 0)
                series[team].game_steps.append(step_index)
                series[team].game_results.append(
                    1 if winner == team else -1 if loser == team else 0
                )
            if winner and loser:
                current[winner] += 1
                current[loser] -= 1
                series[winner].wins += 1
                series[loser].losses += 1
            else:
                series[game.home].ties += 1
                series[game.away].ties += 1

        for team in teams:
            series[team].values.append(current.get(team))

    step_dicts = [{"season": s.season, "week": s.week, "label": s.label} for s in steps]
    team_set = set(teams)
    return {
        "steps": step_dicts,
        "events": place_events(
            [e for e in _cached_franchise_events(games) if e["team"] in team_set], step_dicts
        ),
        "series": [
            {
                "team": s.team,
                "values": s.values,
                "game_steps": s.game_steps,
                "game_results": s.game_results,
                "wins": s.wins,
                "losses": s.losses,
                "ties": s.ties,
                "final": s.values[-1],
            }
            for s in series.values()
        ],
    }
