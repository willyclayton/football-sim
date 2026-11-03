"""The 2025 adapter against made-up files in the 2025 layout.

This proves the adapter's code path end to end; it can't prove the real files
match the documented schema. Running `make bundle EDITION=bdb2025` on the real
download does that, and the adapter stops with the exact mismatch if not.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from all22 import checks
from all22.derive import derive
from all22.editions.bdb2025 import BDB2025
from all22.fixtures import GAME, synthetic_input
from all22.grid import build_play
from all22.normalize import normalize

GAME_ID = int(GAME["id"])


def write_2025_files(folder, drop_column=None):
    inp, official = synthetic_input()
    rows = []
    for r in inp.tracking.itertuples(index=False):
        if r.key == "ball":
            nfl_id, club, name, jersey = math.nan, "football", "football", math.nan
        else:
            ro = inp.roster[r.key]
            nfl_id, club, name, jersey = int(r.key), "HOM" if ro["team"] == "home" else "AWY", ro["name"], ro["jersey"]
        rows.append({"gameId": GAME_ID, "playId": 1, "nflId": nfl_id, "displayName": name,
                     "frameId": r.frame, "frameType": "SNAP" if r.event == "ball_snap" else "AFTER_SNAP",
                     "time": "", "jerseyNumber": jersey, "club": club, "playDirection": "left",
                     "x": r.x, "y": r.y, "s": r.s, "a": 0.0, "dis": 0.0, "o": 90.0, "dir": r.dir,
                     "event": r.event})
    tracking = pd.DataFrame(rows)
    if drop_column:
        tracking = tracking.drop(columns=[drop_column])
    tracking.to_csv(folder / "tracking_week_1.csv", index=False)
    pd.DataFrame([{"gameId": GAME_ID, "season": 2000, "week": 1, "gameDate": "01/01/2000",
                   "gameTimeEastern": "13:00:00", "homeTeamAbbr": "HOM", "visitorTeamAbbr": "AWY",
                   "homeFinalScore": 10, "visitorFinalScore": 7}]).to_csv(folder / "games.csv", index=False)
    pd.DataFrame([{"gameId": GAME_ID, "playId": 1, "playDescription": inp.play["description"],
                   "quarter": 2, "down": 2, "yardsToGo": 6, "possessionTeam": "AWY",
                   "defensiveTeam": "HOM", "yardlineSide": "", "yardlineNumber": 50,
                   "gameClock": "07:30", "preSnapHomeScore": 10, "preSnapVisitorScore": 7,
                   "offenseFormation": "SHOTGUN", "receiverAlignment": "3x1",
                   "pff_passCoverage": "Cover-3", "pff_manZone": "Zone", "playAction": False}]
                 ).to_csv(folder / "plays.csv", index=False)
    pd.DataFrame([{"nflId": int(k), "height": "6-1", "weight": 200, "birthDate": "", "collegeName": "",
                   "position": v["position"], "displayName": v["name"]} for k, v in inp.roster.items()]
                 ).to_csv(folder / "players.csv", index=False)
    pd.DataFrame([{"gameId": GAME_ID, "playId": 1, "nflId": int(k), "inMotionAtBallSnap": False}
                  for k in inp.roster]).to_csv(folder / "player_play.csv", index=False)
    return official


def test_adapter_runs_end_to_end(tmp_path):
    official = write_2025_files(tmp_path)
    inputs = list(BDB2025(raw_dir=tmp_path).iter_plays())
    assert len(inputs) == 1
    play = build_play(inputs[0])
    play.official = official
    normalize(play)
    checks.run_hard(play, 1)
    derive(play)
    checks.run_soft(play)
    assert play.status == "ship", [c.to_json() for c in play.checks if c.result == "fail"]
    assert play.derived["directionMethod"] == "source"  # playDirection, not inferred
    assert not play.notes  # and the player positions agree with it
    offense = {c.key: c for c in play.callouts["offense"]}
    defense = {c.key: c for c in play.callouts["defense"]}
    assert offense["receiver_set"].value == "3x1"  # derived agrees with receiverAlignment
    assert offense["formation"].label == "Shotgun"
    assert defense["coverage"].label == "Cover 3 · zone"
    assert play.derived["motionCompare"] == {"derived": False, "charted": False}


def test_schema_mismatch_names_the_missing_column(tmp_path):
    write_2025_files(tmp_path, drop_column="playDirection")
    with pytest.raises(SystemExit) as err:
        BDB2025(raw_dir=tmp_path).check_files()
    assert "playDirection" in str(err.value)
