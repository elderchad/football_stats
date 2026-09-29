"""Curated roster of Hall of Fame (and likely Hall of Fame) quarterbacks.

Each stint records the seasons a quarterback was his team's franchise starter. An
``end`` of ``None`` means "still active"; it is resolved against the game data so a
line never runs past the quarterback's last appearance.
"""

from __future__ import annotations

from dataclasses import dataclass

HOF = "hof"
LIKELY = "likely"


@dataclass(frozen=True, slots=True)
class Stint:
    team: str
    start: int
    end: int | None = None


@dataclass(frozen=True, slots=True)
class Quarterback:
    id: str
    name: str
    status: str
    entered: int
    stints: tuple[Stint, ...]


QUARTERBACKS: tuple[Quarterback, ...] = (
    Quarterback("baugh", "Sammy Baugh", HOF, 1937, (
        Stint("WAS", 1937, 1952),
    )),
    Quarterback("luckman", "Sid Luckman", HOF, 1939, (
        Stint("CHI", 1939, 1950),
    )),
    Quarterback("graham", "Otto Graham", HOF, 1946, (
        Stint("CLE", 1946, 1955),
    )),
    Quarterback("unitas", "Johnny Unitas", HOF, 1956, (
        Stint("IND", 1956, 1972), Stint("LAC", 1973, 1973),
    )),
    Quarterback("starr", "Bart Starr", HOF, 1956, (
        Stint("GB", 1956, 1971),
    )),
    Quarterback("dawson", "Len Dawson", HOF, 1957, (
        Stint("KC", 1962, 1975),
    )),
    Quarterback("tarkenton", "Fran Tarkenton", HOF, 1961, (
        Stint("MIN", 1961, 1966), Stint("NYG", 1967, 1971), Stint("MIN", 1972, 1978),
    )),
    Quarterback("namath", "Joe Namath", HOF, 1965, (
        Stint("NYJ", 1965, 1976), Stint("LAR", 1977, 1977),
    )),
    Quarterback("griese", "Bob Griese", HOF, 1967, (
        Stint("MIA", 1967, 1980),
    )),
    Quarterback("staubach", "Roger Staubach", HOF, 1969, (
        Stint("DAL", 1969, 1979),
    )),
    Quarterback("bradshaw", "Terry Bradshaw", HOF, 1970, (
        Stint("PIT", 1970, 1983),
    )),
    Quarterback("stabler", "Ken Stabler", HOF, 1970, (
        Stint("LV", 1970, 1979), Stint("TEN", 1980, 1981), Stint("NO", 1982, 1984),
    )),
    Quarterback("fouts", "Dan Fouts", HOF, 1973, (
        Stint("LAC", 1973, 1987),
    )),
    Quarterback("montana", "Joe Montana", HOF, 1979, (
        Stint("SF", 1979, 1992), Stint("KC", 1993, 1994),
    )),
    Quarterback("elway", "John Elway", HOF, 1983, (
        Stint("DEN", 1983, 1998),
    )),
    Quarterback("marino", "Dan Marino", HOF, 1983, (
        Stint("MIA", 1983, 1999),
    )),
    Quarterback("moon", "Warren Moon", HOF, 1984, (
        Stint("TEN", 1984, 1993), Stint("MIN", 1994, 1996), Stint("SEA", 1997, 1998),
        Stint("KC", 1999, 2000),
    )),
    Quarterback("young", "Steve Young", HOF, 1985, (
        Stint("TB", 1985, 1986), Stint("SF", 1987, 1999),
    )),
    Quarterback("kelly", "Jim Kelly", HOF, 1986, (
        Stint("BUF", 1986, 1996),
    )),
    Quarterback("aikman", "Troy Aikman", HOF, 1989, (
        Stint("DAL", 1989, 2000),
    )),
    Quarterback("favre", "Brett Favre", HOF, 1991, (
        Stint("GB", 1992, 2007), Stint("NYJ", 2008, 2008), Stint("MIN", 2009, 2010),
    )),
    Quarterback("warner", "Kurt Warner", HOF, 1998, (
        Stint("LAR", 1998, 2003), Stint("NYG", 2004, 2004), Stint("ARI", 2005, 2009),
    )),
    Quarterback("pmanning", "Peyton Manning", HOF, 1998, (
        Stint("IND", 1998, 2010), Stint("DEN", 2012, 2015),
    )),
    Quarterback("brady", "Tom Brady", LIKELY, 2000, (
        Stint("NE", 2000, 2019), Stint("TB", 2020, 2022),
    )),
    Quarterback("brees", "Drew Brees", LIKELY, 2001, (
        Stint("LAC", 2001, 2005), Stint("NO", 2006, 2020),
    )),
    Quarterback("roethlisberger", "Ben Roethlisberger", LIKELY, 2004, (
        Stint("PIT", 2004, 2021),
    )),
    Quarterback("emanning", "Eli Manning", LIKELY, 2004, (
        Stint("NYG", 2004, 2019),
    )),
    Quarterback("rivers", "Philip Rivers", LIKELY, 2004, (
        Stint("LAC", 2004, 2019), Stint("IND", 2020, 2020),
    )),
    Quarterback("rodgers", "Aaron Rodgers", LIKELY, 2005, (
        Stint("GB", 2005, 2022), Stint("NYJ", 2023, 2024), Stint("PIT", 2025, None),
    )),
    Quarterback("ryan", "Matt Ryan", LIKELY, 2008, (
        Stint("ATL", 2008, 2021), Stint("IND", 2022, 2022),
    )),
    Quarterback("stafford", "Matthew Stafford", LIKELY, 2009, (
        Stint("DET", 2009, 2020), Stint("LAR", 2021, None),
    )),
    Quarterback("newton", "Cam Newton", LIKELY, 2011, (
        Stint("CAR", 2011, 2019), Stint("NE", 2020, 2020), Stint("CAR", 2021, 2021),
    )),
    Quarterback("wilson", "Russell Wilson", LIKELY, 2012, (
        Stint("SEA", 2012, 2021), Stint("DEN", 2022, 2023), Stint("PIT", 2024, 2024),
        Stint("NYG", 2025, None),
    )),
    Quarterback("luck", "Andrew Luck", LIKELY, 2012, (
        Stint("IND", 2012, 2018),
    )),
    Quarterback("prescott", "Dak Prescott", LIKELY, 2016, (
        Stint("DAL", 2016, None),
    )),
    Quarterback("mahomes", "Patrick Mahomes", LIKELY, 2017, (
        Stint("KC", 2017, None),
    )),
    Quarterback("allen", "Josh Allen", LIKELY, 2018, (
        Stint("BUF", 2018, None),
    )),
    Quarterback("jackson", "Lamar Jackson", LIKELY, 2018, (
        Stint("BAL", 2018, None),
    )),
    Quarterback("burrow", "Joe Burrow", LIKELY, 2020, (
        Stint("CIN", 2020, None),
    )),
    Quarterback("herbert", "Justin Herbert", LIKELY, 2020, (
        Stint("LAC", 2020, None),
    )),
    Quarterback("hurts", "Jalen Hurts", LIKELY, 2020, (
        Stint("PHI", 2020, None),
    )),
)
