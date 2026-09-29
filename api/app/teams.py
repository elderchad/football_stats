"""Franchise metadata and abbreviation normalization."""

from __future__ import annotations

# Historical / alternate abbreviations mapped onto the franchise's current code.
ABBREV_ALIASES: dict[str, str] = {
    "OAK": "LV",
    "SD": "LAC",
    "STL": "LAR",
    "SL": "LAR",
    "LA": "LAR",
    "ARZ": "ARI",
    "BLT": "BAL",
    "CLV": "CLE",
    "HST": "HOU",
    "JAX": "JAX",
    "JAC": "JAX",
    "WSH": "WAS",
}

# abbrev -> (full name, conference, division, primary colour, secondary colour)
TEAMS: dict[str, dict[str, str]] = {
    "ARI": {"name": "Arizona Cardinals", "conference": "NFC", "division": "West", "color": "#97233F", "alt_color": "#000000"},
    "ATL": {"name": "Atlanta Falcons", "conference": "NFC", "division": "South", "color": "#A71930", "alt_color": "#000000"},
    "BAL": {"name": "Baltimore Ravens", "conference": "AFC", "division": "North", "color": "#241773", "alt_color": "#9E7C0C"},
    "BUF": {"name": "Buffalo Bills", "conference": "AFC", "division": "East", "color": "#00338D", "alt_color": "#C60C30"},
    "CAR": {"name": "Carolina Panthers", "conference": "NFC", "division": "South", "color": "#0085CA", "alt_color": "#101820"},
    "CHI": {"name": "Chicago Bears", "conference": "NFC", "division": "North", "color": "#0B162A", "alt_color": "#C83803"},
    "CIN": {"name": "Cincinnati Bengals", "conference": "AFC", "division": "North", "color": "#FB4F14", "alt_color": "#000000"},
    "CLE": {"name": "Cleveland Browns", "conference": "AFC", "division": "North", "color": "#311D00", "alt_color": "#FF3C00"},
    "DAL": {"name": "Dallas Cowboys", "conference": "NFC", "division": "East", "color": "#041E42", "alt_color": "#869397"},
    "DEN": {"name": "Denver Broncos", "conference": "AFC", "division": "West", "color": "#FB4F14", "alt_color": "#002244"},
    "DET": {"name": "Detroit Lions", "conference": "NFC", "division": "North", "color": "#0076B6", "alt_color": "#B0B7BC"},
    "GB": {"name": "Green Bay Packers", "conference": "NFC", "division": "North", "color": "#203731", "alt_color": "#FFB612"},
    "HOU": {"name": "Houston Texans", "conference": "AFC", "division": "South", "color": "#03202F", "alt_color": "#A71930"},
    "IND": {"name": "Indianapolis Colts", "conference": "AFC", "division": "South", "color": "#002C5F", "alt_color": "#A2AAAD"},
    "JAX": {"name": "Jacksonville Jaguars", "conference": "AFC", "division": "South", "color": "#006778", "alt_color": "#D7A22A"},
    "KC": {"name": "Kansas City Chiefs", "conference": "AFC", "division": "West", "color": "#E31837", "alt_color": "#FFB81C"},
    "LAC": {"name": "Los Angeles Chargers", "conference": "AFC", "division": "West", "color": "#0080C6", "alt_color": "#FFC20E"},
    "LAR": {"name": "Los Angeles Rams", "conference": "NFC", "division": "West", "color": "#003594", "alt_color": "#FFA300"},
    "LV": {"name": "Las Vegas Raiders", "conference": "AFC", "division": "West", "color": "#A5ACAF", "alt_color": "#000000"},
    "MIA": {"name": "Miami Dolphins", "conference": "AFC", "division": "East", "color": "#008E97", "alt_color": "#FC4C02"},
    "MIN": {"name": "Minnesota Vikings", "conference": "NFC", "division": "North", "color": "#4F2683", "alt_color": "#FFC62F"},
    "NE": {"name": "New England Patriots", "conference": "AFC", "division": "East", "color": "#002244", "alt_color": "#C60C30"},
    "NO": {"name": "New Orleans Saints", "conference": "NFC", "division": "South", "color": "#D3BC8D", "alt_color": "#101820"},
    "NYG": {"name": "New York Giants", "conference": "NFC", "division": "East", "color": "#0B2265", "alt_color": "#A71930"},
    "NYJ": {"name": "New York Jets", "conference": "AFC", "division": "East", "color": "#125740", "alt_color": "#000000"},
    "PHI": {"name": "Philadelphia Eagles", "conference": "NFC", "division": "East", "color": "#004C54", "alt_color": "#A5ACAF"},
    "PIT": {"name": "Pittsburgh Steelers", "conference": "AFC", "division": "North", "color": "#FFB612", "alt_color": "#101820"},
    "SEA": {"name": "Seattle Seahawks", "conference": "NFC", "division": "West", "color": "#002244", "alt_color": "#69BE28"},
    "SF": {"name": "San Francisco 49ers", "conference": "NFC", "division": "West", "color": "#AA0000", "alt_color": "#B3995D"},
    "TB": {"name": "Tampa Bay Buccaneers", "conference": "NFC", "division": "South", "color": "#D50A0A", "alt_color": "#34302B"},
    "TEN": {"name": "Tennessee Titans", "conference": "AFC", "division": "South", "color": "#0C2340", "alt_color": "#4B92DB"},
    "WAS": {"name": "Washington Commanders", "conference": "NFC", "division": "East", "color": "#5A1414", "alt_color": "#FFB612"},
}

# Franchises that no longer exist. Anything not listed here falls back to its raw code.
DEFUNCT_NAMES: dict[str, str] = {
    "AKR": "Akron Pros",
    "BBA": "Buffalo Bisons (AAFC)",
    "BCL": "Baltimore Colts (AAFC)",
    "BDA": "Brooklyn Dodgers (AAFC)",
    "BFF": "Buffalo All-Americans",
    "BKN": "Brooklyn Dodgers",
    "BYK": "Boston Yanks",
    "CBD": "Canton Bulldogs",
    "CLI": "Cleveland Indians",
    "COL": "Columbus Panhandles",
    "CRA": "Chicago Rockets (AAFC)",
    "CRP": "Card-Pitt",
    "DAY": "Dayton Triangles",
    "DTX": "Dallas Texans",
    "DUL": "Duluth Eskimos",
    "FYJ": "Frankford Yellow Jackets",
    "HAM": "Hammond Pros",
    "KCB": "Kansas City Blues",
    "LDA": "Los Angeles Dons (AAFC)",
    "MIL": "Milwaukee Badgers",
    "MNN": "Minneapolis Marines",
    "MSA": "Miami Seahawks (AAFC)",
    "NAA": "New York Yankees (AAFC)",
    "NYY": "New York Yanks",
    "PRV": "Providence Steam Roller",
    "PTB": "Pottsville Maroons",
    "RAC": "Racine Legion",
    "RCH": "Rochester Jeffersons",
    "RED": "Cincinnati Reds",
    "RII": "Rock Island Independents",
    "SIS": "Staten Island Stapletons",
    "STG": "Phil-Pitt Steagles",
    "TOL": "Toledo Maroons",
}

_DEFUNCT_PALETTE = (
    "#8D99AE", "#A98467", "#6D6875", "#7F5539", "#5C6B73",
    "#9A8C98", "#7D8491", "#8A7968", "#6B7A8F", "#94958B",
)


def describe(abbr: str) -> dict:
    """Display metadata for any abbreviation, including long-gone franchises."""
    if abbr in TEAMS:
        return {**TEAMS[abbr], "defunct": False}
    return {
        "name": DEFUNCT_NAMES.get(abbr, abbr),
        "conference": "",
        "division": "",
        "color": _DEFUNCT_PALETTE[sum(map(ord, abbr)) % len(_DEFUNCT_PALETTE)],
        "alt_color": "#2b2f3d",
        "defunct": True,
    }


def normalize(abbrev: str) -> str:
    """Map a raw abbreviation from the source data onto the current franchise code."""
    code = abbrev.strip().upper()
    return ABBREV_ALIASES.get(code, code)
