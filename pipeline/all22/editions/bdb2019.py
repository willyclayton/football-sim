"""Big Data Bowl 2019 schema: the official sample game in the NFL's public repo.

2017 season data. Positions, speed and direction are tracked; player facing
(`o`) is not in this edition, and neither is the play direction, which the
pipeline infers from the line of scrimmage.
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

ST_TYPES = {
    "Kickoff": "kickoff", "Punt": "punt", "Field Goal": "field_goal",
    "Extra Point": "extra_point", "Onside Kick": "kickoff",
}


def _int(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _str(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    s = str(v).strip()
    return s or None


def parse_clock(text) -> int | None:
    """'03:10:00' (this edition's MM:SS:00) or '03:10' -> 190 seconds."""
    t = _str(text)
    if not t:
        return None
    parts = t.split(":")
    try:
        return int(parts[0]) * 60 + int(parts[1])
    except (IndexError, ValueError):
        return None


class BDB2019Sample:
    id = "bdb2019-sample"
    name = "Big Data Bowl 2019 (official sample game)"
    season = 2017
    has_orientation = False

    def __init__(self, raw_dir: Path | None = None):
        self.raw = raw_dir or (config.RAW / "bdb2019_sample")

    @property
    def nflverse_seasons(self) -> list[int]:
        return [self.season]

    def tracking_files(self) -> list[Path]:
        return sorted(self.raw.glob("tracking_gameId_*.csv"))

    def check_files(self) -> None:
        missing = [n for n in ("games.csv", "plays.csv", "players.csv") if not (self.raw / n).exists()]
        if missing or not self.tracking_files():
            raise SystemExit(f"Sample game files missing in {self.raw}; run `make download` first.")

    def iter_plays(self) -> Iterator[PlayInput]:
        self.check_files()
        games = pd.read_csv(self.raw / "games.csv").set_index("gameId")
        plays = pd.read_csv(self.raw / "plays.csv")
        players = pd.read_csv(self.raw / "players.csv").set_index("nflId")
        positions = players["PositionAbbr"].to_dict()
        base_sources = {n: sha256_of(self.raw / n) for n in ("games.csv", "plays.csv", "players.csv")}

        for path in self.tracking_files():
            tr = pd.read_csv(path)
            game_id = int(tr["gameId"].iloc[0])
            g = games.loc[game_id]
            game = {
                "id": str(game_id),
                "season": int(g["season"]),
                "week": int(g["week"]),
                "date": pd.to_datetime(g["gameDate"], format="%m/%d/%Y").strftime("%Y-%m-%d"),
                "home": str(g["homeTeamAbbr"]),
                "away": str(g["visitorTeamAbbr"]),
                "home_name": _str(g.get("homeDisplayName")),
                "away_name": _str(g.get("visitorDisplayName")),
                "home_final": _int(g.get("HomeScore")),
                "away_final": _int(g.get("VisitorScore")),
            }
            sources = dict(base_sources)
            sources[path.name] = sha256_of(path)
            game_plays = plays[plays["gameId"] == game_id].set_index("playId")

            tr = tr.rename(columns={"frame.id": "frame", "displayName": "name",
                                    "jerseyNumber": "jersey"})
            tr["key"] = np.where(tr["team"] == "ball", "ball",
                                 tr["nflId"].map(lambda v: "" if pd.isna(v) else str(int(v))))
            tr["o"] = np.nan

            for play_id, rows in tr.groupby("playId", sort=True):
                if play_id not in game_plays.index:
                    continue
                p = game_plays.loc[play_id]
                rows = rows[["frame", "key", "team", "x", "y", "s", "dir", "o", "event",
                             "name", "jersey", "nflId"]].copy()
                rows.loc[rows["key"] == "ball", "team"] = None
                roster = {}
                for key, r in rows[rows["key"] != "ball"].groupby("key").first().iterrows():
                    nfl_id = int(key)
                    roster[key] = {"name": _str(r["name"]), "jersey": _int(r["jersey"]),
                                   "position": _str(positions.get(nfl_id)), "team": r["team"],
                                   "nfl_id": nfl_id}
                yield PlayInput(
                    edition=self.id,
                    game=game,
                    play=self._play_fields(game, int(play_id), p),
                    tracking=rows.drop(columns=["name", "jersey", "nflId"]),
                    roster=roster,
                    sources=sources,
                )

    def _play_fields(self, game: dict, play_id: int, p: pd.Series) -> dict:
        possession = _str(p["possessionTeam"])
        defense = game["away"] if possession == game["home"] else game["home"]
        src = "NFL play data (Big Data Bowl 2019 plays.csv)"
        charted = {}
        for label, col in (("formation", "offenseFormation"),
                           ("personnel_offense", "personnel.offense"),
                           ("personnel_defense", "personnel.defense"),
                           ("box", "defendersInTheBox"),
                           ("rushers", "numberOfPassRushers")):
            v = p.get(col)
            if v is not None and not (isinstance(v, float) and math.isnan(v)):
                charted[label] = {"value": int(v) if isinstance(v, float) else str(v), "source": src}
        st = ST_TYPES.get(_str(p.get("SpecialTeamsPlayType")) or "", None)
        return {
            "game_id": game["id"],
            "play_id": play_id,
            "quarter": _int(p["quarter"]),
            "clock_seconds": parse_clock(p["GameClock"]),
            "down": _int(p["down"]) or None,
            "yards_to_go": _int(p["yardsToGo"]),
            "possession": possession,
            "defense_team": defense,
            "yardline_side": _str(p["yardlineSide"]),
            "yardline_number": _int(p["yardlineNumber"]),
            "score_before": {"home": _int(p["HomeScoreBeforePlay"]),
                             "away": _int(p["VisitorScoreBeforePlay"])},
            "score_after": {"home": _int(p["HomeScoreAfterPlay"]),
                            "away": _int(p["VisitorScoreAfterPlay"])},
            "special_teams": st,
            "description": _str(p["playDescription"]),
            "play_direction": None,
            "pass_result": _str(p.get("PassResult")),
            "charted": charted,
        }
