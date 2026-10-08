import unittest
from unittest.mock import patch

from app.data import Game
from app.qb_records import build_qb_records, build_qb_td_int, build_qb_timeline
from app.records import build_records


class QuarterbackRecordsTests(unittest.TestCase):
    def setUp(self):
        self.games = [
            Game(2007, 1, "REG", "NE", "NYJ", 30, 10, "Tom Brady", "Chad Pennington"),
            Game(2008, 1, "REG", "NE", "KC", 17, 10, "Tom Brady", "Damon Huard"),
            Game(2008, 2, "REG", "NE", "NYJ", 19, 10, "Matt Cassel", "Brett Favre"),
            Game(2009, 1, "REG", "NE", "BUF", 25, 24, "Tom Brady", "Trent Edwards"),
        ]

    def test_games_exclude_other_starters(self):
        walk = build_qb_records(self.games, ["brady"], "all")["series"][0]
        self.assertEqual(walk["seasons"].count(2008), 1)
        self.assertEqual(walk["wins"], 3)
        timeline = build_qb_timeline(self.games, ["brady"], "all", "games")
        series = timeline["series"][0]
        self.assertEqual(series["games"], 3)
        self.assertEqual(series["final"], walk["final"])
        self.assertEqual(series["values"][timeline["seasons"].index(2008)], 2)

    def test_passing_totals_are_at_labelled_season_end(self):
        rows = [
            {"season": season, "week": 1, "season_type": "REG", "team": "NE", "td": td, "int": ints}
            for season, td, ints in [(2007, 3, 1), (2008, 0, 0), (2009, 2, 1)]
        ]
        with patch("app.qb_records.get_qb_game_stats", return_value={"brady": rows}):
            for metric, expected in [("td", [3, 3, 5]), ("int", [1, 1, 2]), ("td_int", [2, 2, 3])]:
                timeline = build_qb_timeline(self.games, ["brady"], "all", metric)
                series = timeline["series"][0]
                self.assertEqual([series["values"][timeline["seasons"].index(season)]
                                  for season in (2007, 2008, 2009)], expected)
                walk = build_qb_td_int(self.games, ["brady"], "all", metric)["series"][0]
                self.assertEqual(walk["final"], series["final"])

    def test_comeback_stats_extend_annual_coverage(self):
        games = [Game(2025, 15, "REG", "IND", "SEA", 18, 16, "Philip Rivers", "Sam Darnold")]
        rows = [{"season": 2025, "week": 15, "season_type": "REG", "team": "IND", "td": 1, "int": 1}]
        with patch("app.qb_records.get_qb_game_stats", return_value={"rivers": rows}):
            annual = build_qb_timeline(games, ["rivers"], "regular", "td")["series"][0]
            walk = build_qb_td_int(games, ["rivers"], "regular", "td")["series"][0]
            self.assertEqual(annual["final"], 1)
            self.assertEqual(annual["final"], walk["final"])
            self.assertEqual(annual["games"], walk["games"])

    def test_mvp_markers_use_last_regular_game_and_annual_season(self):
        games = self.games + [Game(2007, 20, "SB", "NE", "NYG", 14, 17, "Tom Brady", "Eli Manning")]
        walk = build_qb_records(games, ["brady"], "all")["series"][0]
        medals = [event for event in walk["events"] if event["kind"] == "mvp"]
        self.assertEqual(len(medals), 1)
        self.assertEqual(medals[0]["x"], 1)
        self.assertIn("2007", medals[0]["label"])
        timeline = build_qb_timeline(games, ["brady"], "all", "games")["series"][0]
        self.assertEqual([event["x"] for event in timeline["events"] if event["kind"] == "mvp"], [2007])

    def test_passing_mvp_markers_do_not_move_to_playoffs(self):
        rows = [
            {"season": 2007, "week": week, "season_type": kind, "team": "NE", "td": 1, "int": 0}
            for week, kind in [(17, "REG"), (20, "POST")]
        ]
        with patch("app.qb_records.get_qb_game_stats", return_value={"brady": rows}):
            for metric in ("td", "int", "td_int"):
                walk = build_qb_td_int(self.games, ["brady"], "all", metric)["series"][0]
                self.assertEqual([event["x"] for event in walk["events"] if event["kind"] == "mvp"], [1])
                timeline = build_qb_timeline(self.games, ["brady"], "all", metric)["series"][0]
                self.assertEqual([event["x"] for event in timeline["events"] if event["kind"] == "mvp"], [2007])


class FranchiseRecordsTests(unittest.TestCase):
    def test_defunct_line_ends_without_losing_final_record(self):
        games = [
            Game(1920, 1, "REG", "AKR", "CHI", 7, 0),
            Game(1920, 2, "REG", "CHI", "GB", 7, 0),
            Game(1921, 1, "REG", "CHI", "GB", 7, 0),
        ]
        payload = build_records(games, 1920, 1921, "all")
        series = {entry["team"]: entry for entry in payload["series"]}
        self.assertEqual(series["AKR"]["values"], [1, None, None])
        self.assertEqual(series["AKR"]["final"], 1)
        self.assertEqual(series["CHI"]["values"], [-1, 0, 1])


if __name__ == "__main__":
    unittest.main()