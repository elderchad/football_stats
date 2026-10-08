"""Published season records used before game-level cfbfastR coverage begins."""

from __future__ import annotations

import logging
import os
import re
import time
from urllib.parse import quote

import httpx

log = logging.getLogger(__name__)

HISTORY_CACHE_DIR = os.environ.get("NCAAF_HISTORY_CACHE_DIR", "/data/ncaaf_history")
MEDIAWIKI_URL = (
    "https://en.wikipedia.org/w/api.php?action=parse&page={page}"
    "&prop=wikitext&format=json"
)

TEAM_HISTORY_PAGES = {
    "MICH": "List of Michigan Wolverines football seasons",
    "OSU": "List of Ohio State Buckeyes football seasons",
    "BAMA": "List of Alabama Crimson Tide football seasons",
    "AUB": "List of Auburn Tigers football seasons",
    "TEX": "List of Texas Longhorns football seasons",
    "OU": "List of Oklahoma Sooners football seasons",
}

RIVALRY_HISTORY_PAGES = {
    "holy-war": "Holy War (BYU–Utah)",
    "the-game": "Michigan–Ohio State football rivalry",
    "iron-bowl": "Iron Bowl",
    "red-river": "Red River Rivalry",
}

TEAM_ALIASES = {
    "BYA": "BYU", "BYU": "BYU", "UTAH": "UTAH",
    "MICHIGAN": "MICH", "OHIO STATE": "OSU",
    "ALABAMA": "BAMA", "AUBURN": "AUB",
    "TEXAS": "TEX", "OKLAHOMA": "OU",
}

_UTAH = "1892:0-1-0 1894:1-2-0 1895:0-1-0 1896:3-2-0 1897:1-5-0 1898:2-1-0 1899:2-1-0 1900:2-1-0 1901:3-1-0 1902:5-2-1 1903:3-4-0 1904:7-1-0 1905:6-2-0 1906:4-1-0 1907:4-2-0 1908:3-2-1 1909:4-1-0 1910:4-2-0 1911:5-1-1 1912:5-1-1 1913:2-4-1 1914:3-3-0 1915:5-2-0 1916:3-2-0 1917:2-4-0 1919:5-2-0 1920:1-5-1 1921:3-2-1 1922:7-1-0 1923:4-3-0 1924:3-4-1 1925:6-2-0 1926:7-0-0 1927:3-3-1 1928:5-0-2 1929:7-0-0 1930:8-0-0 1931:7-2-0 1932:6-1-1 1933:5-3-0 1934:5-3-0 1935:4-3-1 1936:6-3-0 1937:5-3-0 1938:7-1-2 1939:6-1-2 1940:7-2-0 1941:6-0-2 1942:6-3-0 1943:0-7-0 1944:5-2-1 1945:4-4-0 1946:8-3-0 1947:8-1-1 1948:8-1-1 1949:2-7-1 1950:3-4-3 1951:7-4-0 1952:6-3-1 1953:8-2-0 1954:4-7-0 1955:6-3-0 1956:5-5-0 1957:6-4-0 1958:4-7-0 1959:5-5-0 1960:7-3-0 1961:6-4-0 1962:4-5-1 1963:4-6-0 1964:9-2-0 1965:3-7-0 1966:5-5-0 1967:4-7-0 1968:3-7-0 1969:8-2-0 1970:6-4-0 1971:3-8-0 1972:6-5-0 1973:7-5-0 1974:1-10-0 1975:1-10-0 1976:3-8-0 1977:3-8-0 1978:8-3-0 1979:6-6-0 1980:5-5-1 1981:8-2-1 1982:5-6-0 1983:5-6-0 1984:6-5-1 1985:8-4-0 1986:2-9-0 1987:5-7-0 1988:6-5-0 1989:4-8-0 1990:4-7-0 1991:7-5-0 1992:6-6-0 1993:7-6-0 1994:10-2-0 1995:7-4-0 1996:8-4-0 1997:6-5-0 1998:7-4-0 1999:9-3-0 2000:4-7-0"
_BYU = "1922:1-5-0 1923:2-5-0 1924:2-3-1 1925:3-3-0 1926:1-5-1 1927:2-4-1 1928:3-3-1 1929:5-3-0 1930:5-2-4 1931:4-4-0 1932:8-1-0 1933:5-4-0 1934:4-5-0 1935:4-4-0 1936:4-5-0 1937:6-3-0 1938:4-3-1 1939:5-2-2 1940:2-4-2 1941:4-3-2 1942:2-5-0 1946:5-4-1 1947:3-7-0 1948:5-6-0 1949:0-11-0 1950:4-5-1 1951:6-3-1 1952:4-6-0 1953:2-7-1 1954:1-8-0 1955:1-9-0 1956:2-7-1 1957:5-3-2 1958:6-4-0 1959:3-7-0 1960:3-8-0 1961:2-8-0 1962:4-6-0 1963:2-8-0 1964:3-6-1 1965:6-4-0 1966:8-2-0 1967:6-4-0 1968:2-8-0 1969:6-4-0 1970:3-8-0 1971:5-6-0 1972:7-4-0 1973:5-6-0 1974:7-4-1 1975:6-5-0 1976:9-3-0 1977:9-2-0 1978:9-4-0 1979:11-1-0 1980:12-1-0 1981:11-2-0 1982:8-4-0 1983:11-1-0 1984:13-0-0 1985:11-3-0 1986:8-5-0 1987:9-4-0 1988:9-4-0 1989:10-3-0 1990:10-3-0 1991:8-3-2 1992:8-5-0 1993:6-6-0 1994:10-3-0 1995:7-4-0 1996:14-1-0 1997:6-5-0 1998:9-5-0 1999:8-4-0 2000:6-6-0"
_UTAH_BOWLS = "1938:W 1964:W 1992:L 1993:L 1994:W 1996:L 1999:W"
_BYU_BOWLS = "1974:L 1976:L 1978:L 1979:L 1980:W 1981:W 1982:L 1983:W 1984:W 1985:L 1986:L 1987:L 1988:W 1989:L 1990:L 1991:T 1992:L 1993:L 1994:W 1996:W 1998:L 1999:L"


def _records(value: str) -> dict[int, tuple[int, int, int]]:
    result = {}
    for item in value.split():
        season, record = item.split(":")
        wins, losses, ties = map(int, record.split("-"))
        result[int(season)] = (wins, losses, ties)
    return result


def _bowls(value: str) -> dict[int, tuple[str, ...]]:
    return {int(item.split(":")[0]): (item.split(":")[1],) for item in value.split()}


SEASON_RECORDS = {"UTAH": _records(_UTAH), "BYU": _records(_BYU)}
BOWL_OUTCOMES = {"UTAH": _bowls(_UTAH_BOWLS), "BYU": _bowls(_BYU_BOWLS)}
CHAMPIONSHIPS: dict[str, dict[int, str]] = {}
SEASON_LIST_PAGES = {
    **TEAM_HISTORY_PAGES,
    "UTAH": "List of Utah Utes football seasons",
    "BYU": "List of BYU Cougars football seasons",
}


def _cached_wikitext(page: str) -> str:
    os.makedirs(HISTORY_CACHE_DIR, exist_ok=True)
    path = os.path.join(HISTORY_CACHE_DIR, re.sub(r"[^A-Za-z0-9]+", "_", page) + ".txt")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    text = _fetch_wikitext(page)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return text


class PageNotFound(Exception):
    """The wiki has no such page."""


def _fetch_wikitext(page: str) -> str:
    """Wikipedia rate-limits bursts of requests, so retry with a growing pause."""
    for attempt in range(5):
        response = httpx.get(
            MEDIAWIKI_URL.format(page=quote(page)),
            headers={"User-Agent": "FootballRecordWalk/1.0"},
            timeout=60.0,
        )
        if response.status_code == 429:
            time.sleep(1.5 * 2**attempt)
            continue
        response.raise_for_status()
        payload = response.json()
        if "parse" not in payload:
            raise PageNotFound(page)
        return payload["parse"]["wikitext"]["*"]
    raise RuntimeError(f"Wikipedia kept rate-limiting requests for {page!r}")


def _parse_seasons(
    text: str,
) -> tuple[dict[int, tuple[int, int, int]], dict[int, tuple[str, ...]]]:
    records: dict[int, tuple[int, int, int]] = {}
    bowls: dict[int, tuple[str, ...]] = {}
    for block in text.split("{{CFB Yearly Record Entry")[1:]:
        year_match = re.search(r"\|\s*year\s*=.*?\|(\d{4})\]\]", block, re.S)
        overall_line = next((line for line in block.splitlines() if "overall" in line), "")
        value = overall_line.split("=", 1)[-1].replace("–", "-")
        record_match = re.search(r"(\d+)-(\d+)(?:-(\d+))?", value)
        if not year_match or not record_match:
            continue
        season = int(year_match.group(1))
        records[season] = (
            int(record_match.group(1)),
            int(record_match.group(2)),
            int(record_match.group(3) or 0),
        )
        bowl_match = re.search(r"\|\s*bowloutcome\s*=\s*([^\n|}]*)", block)
        bowl_line = next((line for line in block.splitlines() if "bowlname" in line), "")
        bowl_name = bowl_line.split("=", 1)[-1]
        markers = re.findall(r"'''([WLT])'''", bowl_name)
        primary = bowl_match.group(1).strip()[:1].upper() if bowl_match else ""
        if re.match(r"\s*'''[WLT]'''", bowl_name):
            outcomes = tuple(markers)  # every game, including the first, is marked inline
        else:
            outcomes = tuple(([primary] if primary else []) + markers)
        if outcomes:
            bowls[season] = outcomes
    if records:
        return records, bowls

    for block in text.split("\n|-\n"):
        lines = [
            line.strip() for line in block.splitlines()
            if line.startswith(("|", "!")) and line.strip() != "|-"
        ]
        if len(lines) < 7:
            continue
        year_match = re.search(r"\|(\d{4})\]\]", lines[0])
        overall = [re.search(r"\d+", line) for line in lines[-6:-3]]
        if not year_match or not overall[0] or not overall[1]:
            continue
        season = int(year_match.group(1))
        records[season] = tuple(int(match.group()) if match else 0 for match in overall)
        outcome_cell = lines[-3].upper()
        outcomes = tuple(
            "W" if value == "WON" else "L" if value == "LOST" else "T"
            for value in re.findall(r"\b(WON|LOST|TIED)\b", outcome_cell)
        )
        if outcomes:
            bowls[season] = outcomes
    return records, bowls


def _parse_championships(text: str) -> dict[int, str]:
    """Season -> "national" or "conference" for title seasons in a season list."""
    titles: dict[int, str] = {}
    for block in text.split("{{CFB Yearly Record Entry")[1:]:
        year_match = re.search(r"\|\s*year\s*=.*?\|(\d{4})\]\]", block, re.S)
        kind = re.search(r"\|\s*championship\s*=\s*(national|conference)", block)
        if year_match and kind:
            titles[int(year_match.group(1))] = kind.group(1)
    if titles:
        return titles

    # Manual tables mark the team cell: † national champions, * conference champions.
    for block in text.split("\n|-\n"):
        lines = [line.strip() for line in block.splitlines() if line.startswith(("|", "!"))]
        if len(lines) < 2:
            continue
        year_match = re.search(r"\|(\d{4})\]\]", lines[0])
        if not year_match:
            continue
        if "†" in lines[1]:
            titles[int(year_match.group(1))] = "national"
        elif "*" in lines[1]:
            titles[int(year_match.group(1))] = "conference"
    return titles


def load_championships(team_codes: tuple[str, ...]) -> dict[str, dict[int, str]]:
    for code in team_codes:
        if code in CHAMPIONSHIPS:
            continue
        page = SEASON_LIST_PAGES.get(code)
        if not page:
            continue
        try:
            CHAMPIONSHIPS[code] = _parse_championships(_cached_wikitext(page))
        except Exception as exc:  # noqa: BLE001 - charts work without event markers
            log.warning("Could not load %s championships: %s", code, exc)
    return CHAMPIONSHIPS


def load_team_histories(team_codes: tuple[str, ...]) -> None:
    for code in team_codes:
        if code in SEASON_RECORDS:
            continue
        page = TEAM_HISTORY_PAGES.get(code)
        if not page:
            continue
        try:
            records, bowls = _parse_seasons(_cached_wikitext(page))
            SEASON_RECORDS[code] = records
            BOWL_OUTCOMES[code] = bowls
        except Exception as exc:  # noqa: BLE001 - other rivalries remain usable
            log.warning("Could not load %s history: %s", code, exc)


def _plain_wiki(value: str) -> str:
    value = re.sub(r"\[\[(?:[^\]|]+\|)?([^\]]+)\]\]", r"\1", value)
    value = re.sub(r"\{\{[^|{}]+\|([^{}]+)\}\}", r"\1", value)
    value = re.sub(r"(?:No\.\s*\d+|#\d+|†|\*)", "", value, flags=re.I)
    return " ".join(value.split()).strip().upper()


def _team_code(value: str) -> str | None:
    plain = _plain_wiki(value)
    return next((code for alias, code in TEAM_ALIASES.items() if alias in plain), None)


def load_head_to_head(rivalry_id: str) -> list[tuple[int, int, str | None, str, str]]:
    """Return season, order, winner (or None), and both team codes."""
    page = RIVALRY_HISTORY_PAGES[rivalry_id]
    try:
        text = _cached_wikitext(page)
    except Exception as exc:  # noqa: BLE001 - modern game rows can still be served
        log.warning("Could not load %s rivalry history: %s", rivalry_id, exc)
        return []

    results: list[tuple[int, int, str | None, str, str]] = []
    order_by_season: dict[int, int] = {}
    for line in text.splitlines():
        plain = re.sub(r"\[\[(?:[^\]|]+\|)?([^\]]+)\]\]", r"\1", line)
        plain = re.sub(r"\[https?://\S+\s+([^\]]+)\]", r"\1", plain)
        if not re.match(r"^\|\s*(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d+", plain):
            continue
        fields = [field.strip() for field in plain.split("|")[1:]]
        if len(fields) < 6:
            continue
        year_match = re.search(r"(18|19|20)\d{2}", fields[0])
        first, second = _team_code(fields[2]), _team_code(fields[4])
        first_score = re.search(r"\d+", fields[3])
        second_score = re.search(r"\d+", fields[5])
        if not year_match or not first or not second or not first_score or not second_score:
            continue
        season = int(year_match.group())
        score1, score2 = int(first_score.group()), int(second_score.group())
        winner = None if score1 == score2 else (first if score1 > score2 else second)
        order = order_by_season.get(season, 0)
        order_by_season[season] = order + 1
        results.append((season, order, winner, first, second))
    exceptions = {
        "the-game": [
            (1950, 0, "MICH", "MICH", "OSU"),
            (1969, 0, "MICH", "MICH", "OSU"),
            (1973, 0, None, "MICH", "OSU"),
        ],
        "iron-bowl": [(1972, 0, "AUB", "BAMA", "AUB")],
    }
    existing = {(season, frozenset((first, second))) for season, _, _, first, second in results}
    results.extend(
        entry for entry in exceptions.get(rivalry_id, [])
        if (entry[0], frozenset((entry[3], entry[4]))) not in existing
    )
    results.sort(key=lambda item: (item[0], item[1]))
    return results
