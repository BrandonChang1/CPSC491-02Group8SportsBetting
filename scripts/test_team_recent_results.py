import unittest
from datetime import date, datetime, timezone
from team_recent_results import collect_recent_records, seasons_for_today


class RecentResultsTests(unittest.TestCase):
    def test_season_transition(self):
        self.assertEqual(seasons_for_today(datetime(2026, 10, 19, tzinfo=timezone.utc)),
                         ['2026-27', '2025-26'])

    def test_deduplicates_ignores_future_and_counts_wins(self):
        rows = [
            {'TEAM_ABBREVIATION': 'BOS', 'GAME_ID': '1', 'WL': 'W', 'GAME_DATE': '2026-10-16'},
            {'TEAM_ABBREVIATION': 'BOS', 'GAME_ID': '1', 'WL': 'W', 'GAME_DATE': '2026-10-16'},
            {'TEAM_ABBREVIATION': 'BOS', 'GAME_ID': '2', 'WL': 'L', 'GAME_DATE': '2026-10-15'},
            {'TEAM_ABBREVIATION': 'BOS', 'GAME_ID': '3', 'WL': 'W', 'GAME_DATE': '2026-10-19'},
        ]
        self.assertEqual(collect_recent_records(rows, date(2026, 10, 19))['BOS'], {'games': 2, 'wins': 1})


if __name__ == '__main__':
    unittest.main()
