"""Synthetic, made-up test data. No NFL data.

Builds one fictional pass play (teams HOM and AWY, season 2000) that moves
right to left, so normalizing must flip it, and has a two-frame sensor gap,
so the gap filler runs. It goes through the real pipeline stages and is
written as fixtures for the Swift tests (decode, interpolation, catalog), so
both sides of the file format are tested against one file.

    python -m all22 fixtures          # (re)write the committed fixtures
    python -m all22 fixtures --check  # fail if they are stale (CI)
"""

from __future__ import annotations

import json
import math
import sqlite3
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from . import catalog, checks, config, pack
from .derive import derive
from .grid import build_play
from .model import Play, PlayInput
from .normalize import normalize

SWIFT_FIXTURES = config.ROOT / "app" / "PlaybackCore" / "Tests" / "PlaybackCoreTests" / "Fixtures"
GAME = {"id": "2000010100", "season": 2000, "week": 1, "date": "2000-01-01", "home": "HOM",
        "away": "AWY", "home_name": "Home Team", "away_name": "Away Team"}
N_FRAMES = 40
SNAP, THROW, ARRIVE, CATCH, CONTACT, TACKLE = 11, 25, 33, 34, 36, 38  # source frame ids

# (key, team, jersey, position, waypoints [(frame, x, y)]), offense attacking toward -x.
ROSTER = [
    ("90001", "away", 7, "QB", [(1, 65.0, 26.65), (SNAP, 65.0, 26.65), (16, 67.0, 26.65)]),
    ("90002", "away", 22, "RB", [(1, 65.2, 24.65), (SNAP, 65.2, 24.65), (24, 61.0, 19.0)]),
    ("90003", "away", 11, "WR", [(1, 61.0, 40.0), (SNAP, 61.0, 40.0), (ARRIVE, 45.6, 40.0),
                                 (TACKLE, 42.6, 38.0)]),
    ("90004", "away", 15, "WR", [(1, 61.5, 34.0), (SNAP, 61.5, 34.0), (26, 52.0, 30.0)]),
    ("90005", "away", 81, "WR", [(1, 61.0, 14.0), (SNAP, 61.0, 14.0), (28, 49.0, 16.0)]),
    ("90006", "away", 88, "TE", [(1, 61.0, 30.5), (SNAP, 61.0, 30.5), (24, 55.0, 32.0)]),
    ("90007", "away", 60, "C", [(1, 60.5, 26.65), (SNAP, 60.5, 26.65), (21, 61.5, 26.65)]),
    ("90008", "away", 64, "G", [(1, 60.6, 25.35), (SNAP, 60.6, 25.35), (21, 61.6, 25.3)]),
    ("90009", "away", 66, "G", [(1, 60.6, 27.95), (SNAP, 60.6, 27.95), (21, 61.6, 28.0)]),
    ("90010", "away", 72, "T", [(1, 60.7, 24.05), (SNAP, 60.7, 24.05), (21, 61.9, 23.5)]),
    ("90011", "away", 76, "T", [(1, 60.7, 29.25), (SNAP, 60.7, 29.25), (21, 61.9, 29.8)]),
    ("90012", "home", 90, "DE", [(1, 59.0, 23.0), (SNAP, 59.0, 23.0), (21, 61.2, 23.2)]),
    ("90013", "home", 93, "DT", [(1, 59.0, 25.8), (SNAP, 59.0, 25.8), (21, 60.9, 25.6)]),
    ("90014", "home", 95, "DT", [(1, 59.0, 27.5), (SNAP, 59.0, 27.5), (21, 60.9, 27.7)]),
    ("90015", "home", 97, "DE", [(1, 59.0, 30.3), (SNAP, 59.0, 30.3), (21, 61.2, 30.1)]),
    ("90016", "home", 50, "OLB", [(1, 55.0, 24.5), (SNAP, 55.0, 24.5), (24, 52.0, 22.0)]),
    ("90017", "home", 52, "ILB", [(1, 55.0, 29.0), (SNAP, 55.0, 29.0), (24, 52.0, 31.0)]),
    ("90018", "home", 24, "CB", [(1, 58.0, 40.5), (SNAP, 58.0, 40.5), (ARRIVE, 44.0, 40.0),
                                 (TACKLE, 42.8, 38.4)]),
    ("90019", "home", 25, "CB", [(1, 58.0, 13.5), (SNAP, 58.0, 13.5), (28, 50.0, 15.0)]),
    ("90020", "home", 26, "CB", [(1, 56.0, 34.5), (SNAP, 56.0, 34.5), (26, 51.5, 31.0)]),
    ("90021", "home", 31, "FS", [(1, 48.0, 20.0), (SNAP, 48.0, 20.0), (TACKLE, 44.0, 33.0)]),
    ("90022", "home", 33, "SS", [(1, 48.0, 33.0), (SNAP, 48.0, 33.0), (TACKLE, 43.5, 37.0)]),
]
GAP = ("90021", 20, 21)  # this player's sensor drops out for two frames
EVENTS = {SNAP: "ball_snap", THROW: "pass_forward", ARRIVE: "pass_arrived",
          CATCH: "pass_outcome_caught", CONTACT: "first_contact", TACKLE: "tackle"}


def _path(waypoints) -> np.ndarray:
    frames = np.arange(1, N_FRAMES + 1)
    fs = [w[0] for w in waypoints] + [N_FRAMES + 1]
    xs = [w[1] for w in waypoints] + [waypoints[-1][1]]
    ys = [w[2] for w in waypoints] + [waypoints[-1][2]]
    return np.stack([np.interp(frames, fs, xs), np.interp(frames, fs, ys)], axis=1)


def _speed_dir(xy: np.ndarray):
    d = np.diff(xy, axis=0, append=xy[-1:])
    s = np.hypot(d[:, 0], d[:, 1]) * config.FRAME_RATE
    ang = (np.degrees(np.arctan2(d[:, 0], d[:, 1])) + 360.0) % 360.0
    return np.round(s, 2), np.round(ang, 2)


def synthetic_input() -> tuple[PlayInput, dict]:
    paths = {key: _path(wp) for key, _, _, _, wp in ROSTER}
    qb, wr = paths["90001"], paths["90003"]
    ball = np.empty((N_FRAMES, 2))
    for f in range(1, N_FRAMES + 1):
        i = f - 1
        if f <= SNAP:
            ball[i] = (60.0, 26.65)
        elif f <= SNAP + 2:
            t = (f - SNAP) / 2
            ball[i] = (60.0 + (qb[i, 0] - 60.0) * t, 26.65 + (qb[i, 1] - 26.65) * t)
        elif f <= THROW:
            ball[i] = qb[i]
        elif f <= ARRIVE:
            t = (f - THROW) / (ARRIVE - THROW)
            a, b = qb[THROW - 1], wr[ARRIVE - 1]
            ball[i] = a + (b - a) * t
        else:
            ball[i] = wr[i]
    rows = []
    for key, team, jersey, pos, _ in ROSTER + [("ball", None, None, None, None)]:
        xy = ball if key == "ball" else paths[key]
        xy = np.round(xy, 2)
        s, d = _speed_dir(xy)
        for f in range(1, N_FRAMES + 1):
            i = f - 1
            x, y, sp, dr = xy[i, 0], xy[i, 1], s[i], d[i]
            if key == GAP[0] and GAP[1] <= f <= GAP[2]:
                x = y = sp = dr = math.nan
            rows.append({"frame": f, "key": key, "team": team, "x": x, "y": y, "s": sp,
                         "dir": math.nan if key == "ball" else dr, "o": math.nan,
                         "event": EVENTS.get(f)})
    tracking = pd.DataFrame(rows)
    roster = {key: {"name": f"Player {jersey}", "jersey": jersey, "position": pos, "team": team,
                    "nfl_id": int(key)} for key, team, jersey, pos, _ in ROSTER}
    play = {
        "game_id": GAME["id"], "play_id": 1, "quarter": 2, "clock_seconds": 450, "down": 2,
        "yards_to_go": 6, "possession": "AWY", "defense_team": "HOM", "yardline_side": None,
        "yardline_number": 50, "score_before": {"home": 10, "away": 7},
        "score_after": {"home": 10, "away": 7}, "special_teams": None,
        "description": "SYNTHETIC TEST PLAY, not real data: #7 pass short left to #11 for 17 yards",
        "play_direction": None, "synthetic": True, "edition_name": "Synthetic test data",
        "charted": {"formation": {"value": "SHOTGUN", "source": "Synthetic"},
                    "box": {"value": 6, "source": "Synthetic"}},
    }
    official = {"play_type": "pass", "complete_pass": 1, "yards_gained": 17.0, "touchdown": 0,
                "receiver_jersey_number": 11, "qtr": 2, "quarter_seconds_remaining": 450,
                "down": 2, "ydstogo": 6, "epa": 1.25, "wpa": 0.031, "wp": 0.52,
                "desc": play["description"]}
    inp = PlayInput(edition="synthetic", game=GAME, play=play, tracking=tracking, roster=roster,
                    sources={"synthetic": "made-up data"})
    return inp, official


def build_synthetic(mutate=None, official_count: int = 1) -> Play:
    """Run the synthetic play through stages 2-5; `mutate(inp, official)` injects faults."""
    inp, official = synthetic_input()
    if mutate:
        mutate(inp, official)
    play = build_play(inp)
    play.official = official if official_count else None
    normalize(play)
    checks.run_hard(play, official_count)
    if play.status != "dropped":
        derive(play)
        checks.run_soft(play)
    return play


def _team(abbr, name=None):
    from .teams import team_info
    return team_info(abbr, name)


def expected(head: dict, rec: np.ndarray) -> dict:
    samples = []
    # ball at the start, QB at the snap, the receiver at the catch, the two
    # gap-filled records of player #31, and a cornerback mid-route.
    picks = [(0, 0), (head["keyFrames"]["snap"], 1), (head["keyFrames"]["catch"], 3),
             (GAP[1] - 1, 21), (GAP[2] - 1, 21), (30, 18)]
    for f, e in picks:
        r = rec[f, e]
        samples.append({"frame": int(f), "entity": int(e), "x": int(r["x"]), "y": int(r["y"]),
                        "s": int(r["s"]), "dir": int(r["dir"]), "o": int(r["o"]),
                        "flags": int(r["flags"])})
    return {"id": head["id"], "frames": int(rec.shape[0]), "entities": int(rec.shape[1]),
            "samples": samples, "keyFrames": head["keyFrames"], "ball": head["ball"],
            "situation": head["situation"], "clock": head["clock"],
            "callouts": {k: [c["label"] for c in v] for k, v in head["callouts"].items()},
            "status": head["checks"]["status"]}


def generate(out_dir: Path) -> None:
    play = build_synthetic()
    with tempfile.TemporaryDirectory() as tmp:
        path, head = pack.write(play, Path(tmp), _team)
        data = path.read_bytes()
    _, rec = pack.decode(data)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "synthetic-play.a22").write_bytes(data)
    (out_dir / "synthetic-expected.json").write_text(json.dumps(expected(head, rec), indent=2) + "\n")
    catalog.write(out_dir / "synthetic-catalog.sqlite",
                  [catalog.row(head, "plays/synthetic-play.a22")],
                  {"edition": "synthetic", "edition_name": "Synthetic test data", "plays": 1})


def _catalog_rows(path: Path):
    con = sqlite3.connect(path)
    try:
        return con.execute("SELECT * FROM plays ORDER BY id").fetchall()
    finally:
        con.close()


def main(check: bool = False) -> int:
    if not check:
        generate(SWIFT_FIXTURES)
        print(f"Wrote synthetic fixtures to {SWIFT_FIXTURES.relative_to(config.ROOT)}")
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        fresh = Path(tmp)
        generate(fresh)
        problems = []
        h1, r1 = pack.read_play(fresh / "synthetic-play.a22")
        try:
            h2, r2 = pack.read_play(SWIFT_FIXTURES / "synthetic-play.a22")
            if h1 != h2 or not np.array_equal(r1, r2):
                problems.append("synthetic-play.a22")
        except FileNotFoundError:
            problems.append("synthetic-play.a22 (missing)")
        for name in ("synthetic-expected.json",):
            committed = SWIFT_FIXTURES / name
            if not committed.exists() or committed.read_text() != (fresh / name).read_text():
                problems.append(name)
        committed_db = SWIFT_FIXTURES / "synthetic-catalog.sqlite"
        if not committed_db.exists() or _catalog_rows(committed_db) != _catalog_rows(fresh / "synthetic-catalog.sqlite"):
            problems.append("synthetic-catalog.sqlite")
    if problems:
        print("Stale fixtures: " + ", ".join(problems) + ". Run `make fixtures`.", file=sys.stderr)
        return 1
    print("Fixtures are up to date.")
    return 0
