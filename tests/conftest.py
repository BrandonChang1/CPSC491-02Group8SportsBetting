import copy
import json
from pathlib import Path

import pytest

from data.collection import espn

FIXTURES = Path(__file__).with_name("fixtures")


@pytest.fixture
def summary():
    return json.loads((FIXTURES / "espn_summary.json").read_text())


@pytest.fixture
def espn_responses(monkeypatch):
    payloads = {
        name: json.loads((FIXTURES / f"espn_{name}.json").read_text())
        for name in ["gamelog", "summary", "teams", "roster"]
    }

    def fake_request(base, path, **params):
        if path == "teams":
            return copy.deepcopy(payloads["teams"])
        if path.endswith("/roster"):
            return copy.deepcopy(payloads["roster"])
        if path.endswith("/gamelog"):
            assert path == "athletes/3975/gamelog"
            assert params["season"] == 2025
            return copy.deepcopy(payloads["gamelog"])
        if path == "summary":
            assert params["event"] == "401705764"
            return copy.deepcopy(payloads["summary"])
        raise AssertionError(f"Unexpected ESPN request: {path}")

    espn.get_teams.cache_clear()
    espn.get_players.cache_clear()
    espn.game_summary.cache_clear()
    monkeypatch.setattr(espn, "request_json", fake_request)
    yield payloads
    espn.get_teams.cache_clear()
    espn.get_players.cache_clear()
    espn.game_summary.cache_clear()
