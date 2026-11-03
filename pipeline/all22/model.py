"""In-memory shapes shared by every stage.

An edition adapter turns its raw files into `PlayInput`s. `grid.build_play`
turns one of those into a `Play`: dense (frame x entity) arrays with NaN where
the source has no value. Every later stage reads and annotates the `Play`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import pandas as pd

# Badges, exactly as the spec's table, plus "model" for EPA and win probability,
# which are statistical model outputs rather than official play-by-play.
TRACKED, OFFICIAL, DERIVED, CHARTED, MODEL, ANIMATED, SIMULATED = (
    "tracked", "official", "derived", "charted", "model", "animated", "simulated")

# Per-record flags in the packed frames (see docs/play-format.md).
FLAG_MISSING = 1 << 0  # no position at all (should never ship)
FLAG_FILLED = 1 << 1  # position interpolated across a short sensor gap
FLAG_NO_DIR = 1 << 2
FLAG_NO_ORIENTATION = 1 << 3
FLAG_NO_SPEED = 1 << 4

POSITION_GROUPS = {
    "QB": "QB",
    "RB": "RB", "FB": "RB", "HB": "RB",
    "WR": "WR",
    "TE": "TE",
    "T": "OL", "G": "OL", "C": "OL", "OT": "OL", "OG": "OL", "OL": "OL",
    "DE": "DL", "DT": "DL", "NT": "DL", "DL": "DL",
    "OLB": "LB", "ILB": "LB", "MLB": "LB", "LB": "LB",
    "CB": "DB", "FS": "DB", "SS": "DB", "S": "DB", "DB": "DB",
    "K": "ST", "P": "ST", "LS": "ST",
}
OFFENSE_ORDER = ["QB", "RB", "WR", "TE", "OL", "ST", "DL", "LB", "DB", None]
DEFENSE_ORDER = ["DL", "LB", "DB", "ST", "QB", "RB", "WR", "TE", "OL", None]
ELIGIBLE_GROUPS = {"RB", "WR", "TE"}


def position_group(position: Optional[str]) -> Optional[str]:
    if position is None or (isinstance(position, float) and np.isnan(position)):
        return None
    return POSITION_GROUPS.get(str(position).upper())


@dataclass
class Entity:
    key: str  # "ball" or the player's nflId
    kind: str  # "ball" | "player"
    team: Optional[str] = None  # "home" | "away"
    side: Optional[str] = None  # "offense" | "defense"
    nfl_id: Optional[int] = None
    name: Optional[str] = None
    jersey: Optional[int] = None
    position: Optional[str] = None
    group: Optional[str] = None

    def to_json(self) -> dict:
        if self.kind == "ball":
            return {"kind": "ball"}
        return {
            "kind": "player", "team": self.team, "side": self.side, "nflId": self.nfl_id,
            "name": self.name, "jersey": self.jersey, "position": self.position,
            "group": self.group,
        }


@dataclass
class Callout:
    key: str
    label: str
    badge: str
    detail: Optional[str] = None
    source: Optional[str] = None
    missing: bool = False
    value: Any = None  # machine-readable value for the catalog and agreement report

    def to_json(self) -> dict:
        out = {"key": self.key, "label": self.label, "badge": self.badge, "missing": self.missing}
        if self.detail:
            out["detail"] = self.detail
        if self.source:
            out["source"] = self.source
        return out


@dataclass
class CheckResult:
    id: str
    name: str
    kind: str  # "hard" | "soft"
    result: str  # "pass" | "fail" | "fixed" (passed after a documented repair) | "n/a"
    detail: str = ""

    @property
    def failed(self) -> bool:
        return self.result == "fail"

    def to_json(self) -> dict:
        return {"id": self.id, "name": self.name, "kind": self.kind, "result": self.result,
                "detail": self.detail}


@dataclass
class PlayInput:
    """What an edition adapter yields for one tracked play."""

    edition: str
    game: dict  # id, season, week, date, home/away abbr and display names
    play: dict  # play-level fields from the edition (situation and charted labels)
    tracking: pd.DataFrame  # columns: frame, key, team, x, y, s, dir, o, event
    roster: dict  # key -> {name, jersey, position}
    sources: dict = field(default_factory=dict)  # file name -> sha256


@dataclass
class Play:
    key: str  # "<gameId>-<playId>"
    edition: str
    game: dict
    meta: dict
    entities: list
    source_frames: np.ndarray  # source frame id for each row
    x: np.ndarray  # (F, E) float64, NaN = missing
    y: np.ndarray
    s: np.ndarray
    dir: np.ndarray
    o: np.ndarray
    present: np.ndarray  # (F, E) bool: the source had a row for this entity and frame
    flags: np.ndarray  # (F, E) uint16
    events: list  # [(frame index, name)], in order
    offense_team: Optional[str] = None  # "home" | "away"
    official: Optional[dict] = None
    labels: dict = field(default_factory=dict)  # charted labels from nflverse
    sources: dict = field(default_factory=dict)
    flipped: bool = False
    window: tuple = (0, 0)  # inclusive frame range that ships
    checks: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    derived: dict = field(default_factory=dict)
    callouts: dict = field(default_factory=dict)
    review: dict = field(default_factory=lambda: {"status": "unreviewed", "date": None, "note": None})
    raw: Optional[dict] = None  # untouched copies of x, y, s, dir, o for the source-match check

    @property
    def n_frames(self) -> int:
        return self.x.shape[0]

    def frame_of(self, *names: str, after: int = -1) -> Optional[int]:
        """First frame index after `after` tagged with any of `names`."""
        for f, name in self.events:
            if f > after and name in names:
                return f
        return None

    def players(self, side: Optional[str] = None) -> list:
        return [i for i, e in enumerate(self.entities)
                if e.kind == "player" and (side is None or e.side == side)]

    def check(self, check_id: str) -> Optional[CheckResult]:
        return next((c for c in self.checks if c.id == check_id), None)

    @property
    def status(self) -> str:
        if any(c.failed and c.kind == "hard" for c in self.checks):
            return "dropped"
        if self.review.get("status") == "dropped":
            return "dropped"
        if any(c.failed and c.kind == "soft" for c in self.checks):
            return "ship" if self.review.get("status") == "reviewed" else "flagged"
        return "ship"
