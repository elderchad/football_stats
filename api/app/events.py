"""Notable events (titles, arrivals, relocations, landmark seasons) placed on the walks.

Every event has a priority: 1 is shown as soon as the chart loads, 2 once the user has
zoomed in a little, and 3 only when zoomed in close.
"""

from __future__ import annotations

from .data import REGULAR_SEASON, Game
from .quarterbacks import QUARTERBACKS

AFL_FRANCHISES = frozenset({"BUF", "NE", "NYJ", "TEN", "DEN", "KC", "LAC", "LV", "MIA", "CIN"})

# Champions decided by standings, before the first championship game in 1933.
STANDINGS_CHAMPIONS = {
    1920: "AKR", 1921: "CHI", 1922: "CBD", 1923: "CBD", 1925: "ARI", 1926: "FYJ",
    1927: "NYG", 1928: "PRV", 1929: "GB", 1930: "GB", 1931: "GB", 1932: "CHI",
}

RELOCATIONS: dict[str, tuple[tuple[int, str], ...]] = {
    "DET": ((1934, "Moves to Detroit"),),
    "WAS": ((1937, "Moves to Washington"),),
    "LAR": ((1946, "Moves to Los Angeles"), (1995, "Moves to St. Louis"), (2016, "Returns to Los Angeles")),
    "ARI": ((1960, "Moves to St. Louis"), (1988, "Moves to Arizona")),
    "LAC": ((1961, "Moves to San Diego"), (2017, "Returns to Los Angeles")),
    "KC": ((1963, "Moves to Kansas City"),),
    "LV": ((1982, "Moves to Los Angeles"), (1995, "Returns to Oakland"), (2020, "Moves to Las Vegas")),
    "IND": ((1984, "Moves to Indianapolis"),),
    "TEN": ((1997, "Moves to Tennessee"),),
}

# Anchors: "game" = the step of that week, "start"/"end" = first/last step of the season.
GAME, START, END = "game", "start", "end"


def roman(value: int) -> str:
    numerals = (
        (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
        (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
    )
    out = ""
    for number, numeral in numerals:
        while value >= number:
            out += numeral
            value -= number
    return out


def title_game_event(game: Game, team: str) -> dict | None:
    """Kind, label and priority for a title game from ``team``'s point of view."""
    if game.game_type == "SB":
        name = f"Super Bowl {roman(game.season - 1965)}"
    elif game.game_type == "CON" and game.season < 1970:
        league = "AFL" if team in AFL_FRANCHISES and game.season >= 1960 else "NFL"
        name = f"{league} Championship"
    else:
        return None
    if game.winner is None:
        return None
    won = game.winner == team
    # Before the Super Bowl existed, the league championship game crowned the champion.
    is_final = game.game_type == "SB" or game.season < 1966
    return {
        "kind": "title" if won and is_final else "runnerup" if not won else "conference",
        "label": f"{'Won' if won else 'Lost'} {name}",
        "priority": 1 if won and is_final else 2,
    }


def franchise_events(games: list[Game]) -> list[dict]:
    events: list[dict] = []
    teams_by_season: dict[int, set[str]] = {}
    regular: dict[tuple[int, str], list[int]] = {}
    post_losses: set[tuple[int, str]] = set()
    titles: set[tuple[int, str]] = set()

    for game in games:
        teams_by_season.setdefault(game.season, set()).update((game.home, game.away))
        for team in (game.home, game.away):
            if game.game_type == REGULAR_SEASON:
                record = regular.setdefault((game.season, team), [0, 0, 0])
                record[0 if game.winner == team else 1 if game.loser == team else 2] += 1
            elif game.loser == team:
                post_losses.add((game.season, team))
            event = title_game_event(game, team)
            if event:
                events.append({"team": team, "season": game.season, "week": game.week,
                               "anchor": GAME, **event})
                if event["kind"] == "title":
                    titles.add((game.season, team))

    for season, team in STANDINGS_CHAMPIONS.items():
        if team in teams_by_season.get(season, set()):
            titles.add((season, team))
            events.append({"team": team, "season": season, "week": None, "anchor": END,
                           "kind": "title", "label": "NFL champions", "priority": 1})

    for (season, team), (wins, losses, ties) in regular.items():
        played = wins + losses + ties
        if played < 8:
            continue
        record = f"{wins}-{losses}" + (f"-{ties}" if ties else "")
        if losses == 0:
            perfect = ties == 0 and (season, team) in titles and (season, team) not in post_losses
            events.append({
                "team": team, "season": season, "week": None, "anchor": END,
                "kind": "season",
                "label": "Perfect season" if perfect else f"Unbeaten regular season ({record})",
                "priority": 1 if perfect else 2,
            })
        elif wins == 0:
            events.append({"team": team, "season": season, "week": None, "anchor": END,
                           "kind": "season", "label": f"Winless season ({record})", "priority": 3})

    for team, moves in RELOCATIONS.items():
        for season, label in moves:
            if team in teams_by_season.get(season, set()):
                events.append({"team": team, "season": season, "week": None, "anchor": START,
                               "kind": "move", "label": label, "priority": 2})

    for qb in QUARTERBACKS:
        for stint in qb.stints:
            if stint.team in teams_by_season.get(stint.start, set()):
                events.append({"team": stint.team, "season": stint.start, "week": None,
                               "anchor": START, "kind": "arrival",
                               "label": f"{qb.name} arrives", "priority": 2})
            if stint.end is not None and stint.team in teams_by_season.get(stint.end, set()):
                events.append({"team": stint.team, "season": stint.end, "week": None,
                               "anchor": END, "kind": "departure",
                               "label": f"{qb.name}'s last season", "priority": 3})
    return events


def place_events(events: list[dict], steps: list[dict], team_key: str = "team") -> list[dict]:
    """Map season/week anchored events onto step indexes of a built walk."""
    by_week: dict[tuple[int, int], int] = {}
    first: dict[int, int] = {}
    last: dict[int, int] = {}
    for index, step in enumerate(steps):
        by_week[(step["season"], step["week"])] = index
        first.setdefault(step["season"], index)
        last[step["season"]] = index

    placed = []
    for event in events:
        season = event["season"]
        if season not in first:
            continue
        if event["anchor"] == START:
            index = first[season]
        elif event["anchor"] == GAME:
            index = by_week.get((season, event["week"]), last[season])
        else:
            index = last[season]
        placed.append({
            "step": index,
            "series": event[team_key],
            "kind": event["kind"],
            "label": f"{season} · {event['label']}",
            "priority": event["priority"],
        })
    return placed
