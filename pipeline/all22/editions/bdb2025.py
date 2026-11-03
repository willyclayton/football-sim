"""Big Data Bowl 2025 schema (2022 season, weeks 1-9). UNTESTED against the real files.

Written from the edition's published data description, as best known without
downloading it (Kaggle needs your login). Every file's columns are checked
before anything else runs, and a mismatch stops the build with the exact
missing columns, so a schema surprise fails loudly instead of quietly.

What this edition adds over the 2017 sample:
  * player facing (`o`) and acceleration (`a`)
  * frames before the snap (`frameType` BEFORE_SNAP / SNAP / AFTER_SNAP),
    with `line_set` tagged, so callouts can show from line set
  * the play direction (`playDirection`), so normalizing needs no inference
  * charted labels in plays.csv: offenseFormation, receiverAlignment,
    pff_passCoverage, pff_manZone, playAction, dropbackType, rushLocationType
  * per-player labels in player_play.csv: routeRan, inMotionAtBallSnap,
    shiftSinceLineset, motionSinceLineset, wasInitialPassRusher

Tracking files are large (one per week); they are read one week at a time
with only the needed columns.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Iterator

import numpy as np
import pandas as pd

from .. import config
from ..download import sha256_of
from ..model import PlayInput
from .bdb2019 import _int, _str, parse_clock

REQUIRED = {
    "games.csv": ["gameId", "season", "week", "gameDate", "homeTeamAbbr", "visitorTeamAbbr"],
    "plays.csv": ["gameId", "playId", "playDescription", "quarter", "down", "yardsToGo",
                  "possessionTeam", "defensiveTeam", "yardlineSide", "yardlineNumber", "gameClock",
                  "preSnapHomeScore", "preSnapVisitorScore"],
    "players.csv": ["nflId", "position", "displayName"],
    "tracking": ["gameId", "playId", "nflId", "displayName", "frameId", "jerseyNumber", "club",
                 "playDirection", "x", "y", "s", "dir", "o", "event"],
}
OPTIONAL_PLAY_LABELS = {
    # label -> plays.csv column
    "formation": "offenseFormation",
    "receiver_alignment": "receiverAlignment",
    "coverage": "pff_passCoverage",
    "man_zone": "pff_manZone",
    "box": "defendersInTheBox",
    "play_action": "playAction",
    "rpo": "pff_runPassOption",
}
LABEL_SOURCE = "Big Data Bowl 2025 plays.csv (NFL and PFF charting)"
PLAYER_PLAY_SOURCE = "Big Data Bowl 2025 player_play.csv"


def _missing(path: Path, required: list[str]) -> list[str]:
    cols = set(pd.read_csv(path, nrows=0).columns)
    return [c for c in required if c not in cols]


class BDB2025:
    id = "bdb2025"
    name = "Big Data Bowl 2025 (2022 season, weeks 1-9)"
    season = 2022
    has_orientation = True

    def __init__(self, raw_dir: Path | None = None):
        self.raw = raw_dir or (config.RAW / "bdb2025")

    @property
    def nflverse_seasons(self) -> list[int]:
        return [self.season]

    def tracking_files(self) -> list[Path]:
        return sorted(self.raw.glob("tracking_week_*.csv"),
                      key=lambda p: int("".join(ch for ch in p.stem if ch.isdigit()) or 0))

    def check_files(self) -> None:
        if not self.raw.exists() or not self.tracking_files():
            raise SystemExit(f"No Big Data Bowl 2025 tracking files in {self.raw}. "
                             "Run `make download EDITION=bdb2025` (needs your Kaggle login).")
        problems = []
        for name in ("games.csv", "plays.csv", "players.csv"):
            path = self.raw / name
            if not path.exists():
                problems.append(f"{name} is missing")
                continue
            miss = _missing(path, REQUIRED[name])
            if miss:
                problems.append(f"{name} lacks {', '.join(miss)}")
        miss = _missing(self.tracking_files()[0], REQUIRED["tracking"])
        if miss:
            problems.append(f"{self.tracking_files()[0].name} lacks {', '.join(miss)}")
        if problems:
            raise SystemExit("The 2025 files don't match the expected schema (this adapter is "
                             "untested against the real data):\n  " + "\n  ".join(problems)
                             + "\nPaste this message to Claude to update the adapter.")

    def iter_plays(self) -> Iterator[PlayInput]:
        self.check_files()
        games = pd.read_csv(self.raw / "games.csv").set_index("gameId")
        plays = pd.read_csv(self.raw / "plays.csv", low_memory=False).set_index(["gameId", "playId"])
        players = pd.read_csv(self.raw / "players.csv").set_index("nflId")
        positions = players["position"].to_dict()
        player_play = None
        pp_path = self.raw / "player_play.csv"
        if pp_path.exists():
            player_play = pd.read_csv(pp_path, low_memory=False).set_index(["gameId", "playId"]).sort_index()
        base_sources = {n: sha256_of(self.raw / n) for n in ("games.csv", "plays.csv", "players.csv")}

        usecols = REQUIRED["tracking"] + ["frameType"]
        for path in self.tracking_files():
            header = set(pd.read_csv(path, nrows=0).columns)
            tr_all = pd.read_csv(path, usecols=[c for c in usecols if c in header],
                                 dtype={"event": "object", "club": "object", "displayName": "object"})
            sources = dict(base_sources)
            sources[path.name] = sha256_of(path)
            for (game_id, play_id), rows in tr_all.groupby(["gameId", "playId"], sort=True):
                if (game_id, play_id) not in plays.index or game_id not in games.index:
                    continue
                g = games.loc[game_id]
                game = {
                    "id": str(int(game_id)), "season": int(g["season"]), "week": int(g["week"]),
                    "date": pd.to_datetime(g["gameDate"]).strftime("%Y-%m-%d"),
                    "home": str(g["homeTeamAbbr"]), "away": str(g["visitorTeamAbbr"]),
                    "home_name": None, "away_name": None,
                    "home_final": _int(g.get("homeFinalScore")),
                    "away_final": _int(g.get("visitorFinalScore")),
                }
                p = plays.loc[(game_id, play_id)]
                pp = None
                if player_play is not None and (game_id, play_id) in player_play.index:
                    pp = player_play.loc[[(game_id, play_id)]]
                yield self._play_input(game, int(play_id), p, rows, positions, pp, sources)

    def _play_input(self, game, play_id, p, rows, positions, pp, sources) -> PlayInput:
        rows = rows.rename(columns={"frameId": "frame", "displayName": "name", "jerseyNumber": "jersey"})
        is_ball = rows["club"].astype(str).str.lower().eq("football") | rows["nflId"].isna()
        rows["key"] = np.where(is_ball, "ball",
                               rows["nflId"].map(lambda v: "" if pd.isna(v) else str(int(v))))
        rows["team"] = np.where(is_ball, None,
                                np.where(rows["club"] == game["home"], "home", "away"))
        direction = rows["playDirection"].dropna()
        play_direction = str(direction.iloc[0]).lower() if len(direction) else None
        roster = {}
        for key, r in rows[~is_ball].groupby("key").first().iterrows():
            nfl_id = int(key)
            roster[key] = {"name": _str(r["name"]), "jersey": _int(r["jersey"]),
                           "position": _str(positions.get(nfl_id)), "team": r["team"],
                           "nfl_id": nfl_id}
        tracking = rows[["frame", "key", "team", "x", "y", "s", "dir", "o", "event"]].copy()
        tracking["event"] = tracking["event"].where(tracking["event"].notna(), None)

        charted = {}
        for label, col in OPTIONAL_PLAY_LABELS.items():
            v = p.get(col)
            if v is None or (isinstance(v, float) and math.isnan(v)) or v == "":
                continue
            if isinstance(v, (bool, np.bool_)):
                v = bool(v)
            elif isinstance(v, (float, np.floating)) and float(v).is_integer():
                v = int(v)
            charted[label] = {"value": v, "source": LABEL_SOURCE}
        if pp is not None and "inMotionAtBallSnap" in pp.columns:
            moving = pp["inMotionAtBallSnap"].fillna(False).astype(bool).any()
            charted["motion"] = {"value": bool(moving), "source": PLAYER_PLAY_SOURCE}

        possession = _str(p["possessionTeam"])
        description = _str(p["playDescription"]) or ""
        lower = description.lower()
        special = None
        if " kicks " in lower or "kickoff" in lower:
            special = "kickoff"
        elif " punts " in lower:
            special = "punt"
        elif "field goal" in lower:
            special = "field_goal"
        elif "extra point" in lower:
            special = "extra_point"
        return PlayInput(
            edition=self.id,
            game=game,
            play={
                "game_id": game["id"], "play_id": play_id, "quarter": _int(p["quarter"]),
                "clock_seconds": parse_clock(p["gameClock"]), "down": _int(p["down"]) or None,
                "yards_to_go": _int(p["yardsToGo"]), "possession": possession,
                "defense_team": _str(p.get("defensiveTeam")),
                "yardline_side": _str(p["yardlineSide"]), "yardline_number": _int(p["yardlineNumber"]),
                "score_before": {"home": _int(p["preSnapHomeScore"]), "away": _int(p["preSnapVisitorScore"])},
                "score_after": None, "special_teams": special, "description": description,
                "play_direction": play_direction if play_direction in ("left", "right") else None,
                "charted": charted,
            },
            tracking=tracking,
            roster=roster,
            sources=sources,
        )
