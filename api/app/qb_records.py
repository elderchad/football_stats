"""Cumulative win/loss walks for a quarterback's team across his career."""

from __future__ import annotations

from .data import REGULAR_SEASON, Game
from .events import title_game_event
from .qb_stats import STATS_START_SEASON, get_qb_game_stats
from .quarterbacks import QUARTERBACKS, Quarterback
from .records import game_type_allowed, week_label
from .teams import TEAMS


def _super_bowl_team_weeks(games: list[Game]) -> set[tuple[int, int, str]]:
    return {
        (game.season, game.week, team)
        for game in games
        if game.game_type == "SB"
        for team in (game.home, game.away)
    }


def _passing_row_allowed(
    row: dict,
    game_mode: str,
    super_bowl_team_weeks: set[tuple[int, int, str]],
) -> bool:
    if game_mode == "superbowls":
        return (row["season"], row["week"], row["team"]) in super_bowl_team_weeks
    if game_mode == "all":
        return row["season_type"] in ("REG", "POST")
    if game_mode == "playoffs":
        return row["season_type"] == "POST"
    return row["season_type"] == REGULAR_SEASON


def _title_games(games: list[Game]) -> dict[tuple[int, str], list[Game]]:
    """(season, team) -> Super Bowl and pre-merger championship games."""
    found: dict[tuple[int, str], list[Game]] = {}
    for game in games:
        if game.game_type == "SB" or (game.game_type == "CON" and game.season < 1970):
            for team in (game.home, game.away):
                found.setdefault((game.season, team), []).append(game)
    return found


def _event(x: int, season: int, kind: str, label: str, priority: int) -> dict:
    return {"x": x, "kind": kind, "label": f"{season} · {label}", "priority": priority}


def last_start_seasons(games: list[Game]) -> dict[str, int]:
    """Latest season in which each named quarterback started a game."""
    latest: dict[str, int] = {}
    for game in games:
        for name in (game.home_qb, game.away_qb):
            if name:
                key = name.casefold()
                if game.season > latest.get(key, 0):
                    latest[key] = game.season
    return latest


def _resolved_stints(qb: Quarterback, latest: dict[str, int]) -> list[tuple[str, int, int]]:
    fallback = latest.get(qb.name.casefold())
    resolved = []
    for stint in qb.stints:
        end = stint.end if stint.end is not None else (fallback or stint.start)
        if end >= stint.start:
            resolved.append((stint.team, stint.start, end))
    return resolved


def list_quarterbacks(games: list[Game]) -> list[dict]:
    latest = last_start_seasons(games)
    data_floor = min((g.season for g in games), default=1999)

    entries = []
    for qb in QUARTERBACKS:
        stints = _resolved_stints(qb, latest)
        if not stints:
            continue
        primary = max(stints, key=lambda s: s[2] - s[1])[0]
        entries.append(
            {
                "id": qb.id,
                "name": qb.name,
                "status": qb.status,
                "entered": qb.entered,
                "first_season": max(min(s[1] for s in stints), data_floor),
                "last_season": max(s[2] for s in stints),
                "truncated": min(s[1] for s in stints) < data_floor,
                "teams": [{"team": t, "start": a, "end": b} for t, a, b in stints],
                "color": TEAMS.get(primary, {}).get("color", "#888888"),
            }
        )
    entries.sort(key=lambda entry: (entry["entered"], entry["name"]))
    return entries


def build_qb_records(
    games: list[Game],
    qb_ids: list[str] | None,
    game_mode: str,
) -> dict:
    wanted = set(qb_ids) if qb_ids else None
    latest = last_start_seasons(games)
    scoped = [g for g in games if game_type_allowed(g.game_type, game_mode)]

    series = []
    for qb in QUARTERBACKS:
        if wanted is not None and qb.id not in wanted:
            continue
        stints = _resolved_stints(qb, latest)
        if not stints:
            continue

        career = sorted(
            dict.fromkeys(
                game
                for game in scoped
                for team, start, end in stints
                if start <= game.season <= end and team in (game.home, game.away)
            ),
            key=lambda g: (g.season, g.week),
        )
        if not career:
            continue

        team_of: dict[int, str] = {}
        for team, start, end in stints:
            for season in range(start, end + 1):
                team_of[season] = team

        values: list[int] = [0]
        labels: list[str] = ["Career start"]
        seasons: list[int] = [career[0].season]
        wins = losses = ties = 0
        total = 0
        events: list[dict] = []
        previous_team: str | None = None

        for game in career:
            team = team_of[game.season]
            if game.is_tie:
                ties += 1
            elif game.winner == team:
                wins += 1
                total += 1
            else:
                losses += 1
                total -= 1
            values.append(total)
            labels.append(week_label(game.season, game.week, game.game_type))
            seasons.append(game.season)

            step = len(values) - 1
            if previous_team is not None and team != previous_team:
                events.append(_event(step, game.season, "arrival", f"Joins {team}", 2))
            previous_team = team
            title = title_game_event(game, team)
            if title:
                events.append(_event(step, game.season, title["kind"], title["label"], title["priority"]))
            if game.winner == team and wins % 50 == 0:
                events.append(_event(step, game.season, "milestone", f"{wins}th team win", 3))

        primary = max(stints, key=lambda s: s[2] - s[1])[0]
        series.append(
            {
                "id": qb.id,
                "name": qb.name,
                "status": qb.status,
                "color": TEAMS.get(primary, {}).get("color", "#888888"),
                "values": values,
                "labels": labels,
                "seasons": seasons,
                "wins": wins,
                "losses": losses,
                "ties": ties,
                "final": total,
                "events": events,
            }
        )

    return {
        "series": series,
        "max_steps": max((len(s["values"]) for s in series), default=0),
        "game_mode": game_mode,
    }


def build_qb_td_int(
    games: list[Game],
    qb_ids: list[str] | None,
    game_mode: str,
    metric: str = "td_int",
) -> dict:
    """Cumulative passing touchdowns, interceptions, or their difference."""
    latest_season = max((g.season for g in games), default=STATS_START_SEASON)
    stats = get_qb_game_stats(latest_season)
    wanted = set(qb_ids) if qb_ids else None
    super_bowl_team_weeks = _super_bowl_team_weeks(games)
    super_bowls = {
        (game.season, game.week, team): game
        for game in games if game.game_type == "SB"
        for team in (game.home, game.away)
    }
    data_floor_truncated = {
        qb.id for qb in QUARTERBACKS if min(s.start for s in qb.stints) < STATS_START_SEASON
    }

    series = []
    for qb in QUARTERBACKS:
        if wanted is not None and qb.id not in wanted:
            continue
        rows = stats.get(qb.id)
        if not rows:
            continue
        rows = [
            row for row in rows
            if _passing_row_allowed(row, game_mode, super_bowl_team_weeks)
        ]
        if not rows:
            continue

        values = [0]
        labels = ["Debut"]
        total = touchdowns = interceptions = 0
        events: list[dict] = []
        previous_team: str | None = None
        for row in rows:
            touchdowns += row["td"]
            interceptions += row["int"]
            contribution = {
                "td": row["td"],
                "int": row["int"],
                "td_int": row["td"] - row["int"],
            }[metric]
            total += contribution
            values.append(total)
            labels.append(f"{row['season']} Wk {row['week']}")

            step = len(values) - 1
            if previous_team is not None and row["team"] != previous_team:
                events.append(_event(step, row["season"], "arrival", f"Joins {row['team']}", 2))
            previous_team = row["team"]
            game = super_bowls.get((row["season"], row["week"], row["team"]))
            title = title_game_event(game, row["team"]) if game else None
            if title:
                events.append(_event(step, row["season"], title["kind"], title["label"], title["priority"]))
            if (
                metric == "td"
                and qb.id not in data_floor_truncated
                and touchdowns // 100 > (touchdowns - row["td"]) // 100
            ):
                events.append(_event(
                    step, row["season"], "milestone",
                    f"{touchdowns // 100 * 100}th passing TD"
                    + (" (incl. playoffs)" if game_mode == "all" else ""),
                    2,
                ))

        primary = max(_resolved_stints(qb, {}), key=lambda s: s[2] - s[1])[0]
        series.append(
            {
                "id": qb.id,
                "name": qb.name,
                "status": qb.status,
                "color": TEAMS.get(primary, {}).get("color", "#888888"),
                "values": values,
                "labels": labels,
                "touchdowns": touchdowns,
                "interceptions": interceptions,
                "games": len(rows),
                "first_season": rows[0]["season"],
                "final": total,
                "events": events,
            }
        )

    return {
        "series": series,
        "max_steps": max((len(s["values"]) for s in series), default=0),
        "game_mode": game_mode,
        "metric": metric,
        "stats_start_season": STATS_START_SEASON,
    }


def build_qb_timeline(
    games: list[Game],
    qb_ids: list[str] | None,
    game_mode: str,
    metric: str,
) -> dict:
    """Aggregate each selected QB metric by season across the full league timeline."""
    latest_season = max((game.season for game in games), default=1920)
    seasons = list(range(1920, latest_season + 1))
    wanted = set(qb_ids) if qb_ids else None
    latest_starts = last_start_seasons(games)
    super_bowl_team_weeks = _super_bowl_team_weeks(games)
    title_games = _title_games(games)

    team_games: dict[tuple[int, str], list[Game]] = {}
    if metric == "games":
        for game in games:
            if game_type_allowed(game.game_type, game_mode):
                team_games.setdefault((game.season, game.home), []).append(game)
                team_games.setdefault((game.season, game.away), []).append(game)

    season_stats: dict[tuple[str, int], dict[str, int]] = {}
    if metric != "games":
        for qb_id, rows in get_qb_game_stats(latest_season).items():
            for row in rows:
                if not _passing_row_allowed(row, game_mode, super_bowl_team_weeks):
                    continue
                totals = season_stats.setdefault(
                    (qb_id, row["season"]), {"games": 0, "td": 0, "int": 0}
                )
                totals["games"] += 1
                totals["td"] += row["td"]
                totals["int"] += row["int"]

    series = []
    for qb in QUARTERBACKS:
        if wanted is not None and qb.id not in wanted:
            continue
        stints = _resolved_stints(qb, latest_starts)
        if not stints:
            continue

        first_career_season = min(start for _, start, _ in stints)
        career_end_season = max(end for _, _, end in stints)
        first_data_season = (
            first_career_season
            if metric == "games"
            else max(first_career_season, STATS_START_SEASON)
        )
        if metric != "games" and career_end_season < STATS_START_SEASON:
            first_data_season = None

        team_by_season = {
            season: team
            for team, start, end in stints
            for season in range(start, min(end, latest_season) + 1)
        }
        values: list[int | None] = [None] * len(seasons)
        totals = {"games": 0, "td": 0, "int": 0}
        cumulative = 0

        for index, season in enumerate(seasons):
            team = team_by_season.get(season)

            if metric == "games":
                if first_career_season <= season <= career_end_season and not team:
                    values[index] = cumulative
                    continue
                if not team:
                    continue
                played = team_games.get((season, team), [])
                net = sum(
                    1 if game.winner == team else -1 if game.loser == team else 0
                    for game in played
                )
                totals["games"] += len(played)
                cumulative += net
                values[index] = cumulative
                continue

            if (
                first_data_season is None
                or season < first_data_season
                or season > career_end_season
            ):
                continue
            stats = season_stats.get((qb.id, season), {"games": 0, "td": 0, "int": 0})
            totals["games"] += stats["games"]
            totals["td"] += stats["td"]
            totals["int"] += stats["int"]
            cumulative += {
                "td": stats["td"],
                "int": stats["int"],
                "td_int": stats["td"] - stats["int"],
            }[metric]
            values[index] = cumulative

        primary = max(stints, key=lambda stint: stint[2] - stint[1])[0]
        events: list[dict] = []
        for position, (team, start, end) in enumerate(sorted(stints, key=lambda s: s[1])):
            if position:
                events.append(_event(start, start, "arrival", f"Joins {team}", 2))
            for season in range(start, min(end, latest_season) + 1):
                for game in title_games.get((season, team), []):
                    title = title_game_event(game, team)
                    if title:
                        events.append(_event(season, season, title["kind"], title["label"], title["priority"]))
        series.append(
            {
                "id": qb.id,
                "name": qb.name,
                "status": qb.status,
                "color": TEAMS.get(primary, {}).get("color", "#888888"),
                "values": values,
                "games": totals["games"],
                "touchdowns": totals["td"],
                "interceptions": totals["int"],
                "final": cumulative,
                "first_season": first_data_season,
                "events": events,
            }
        )

    return {
        "seasons": seasons,
        "series": series,
        "metric": metric,
        "game_mode": game_mode,
        "stats_start_season": STATS_START_SEASON,
    }

