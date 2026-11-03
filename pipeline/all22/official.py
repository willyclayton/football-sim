"""Stage 2 inputs: official play-by-play and charted labels from nflverse.

Play-by-play facts (down, distance, clock, yards, result) carry the Official
badge. EPA and win probability come from nflverse's models: badge Model.
Participation (formation, personnel, box, rushers, coverage) and FTN charting
(motion, play action, RPO, screen, blitzers) carry the Charted badge.

Big Data Bowl `gameId` + `playId` match nflverse `old_game_id` + `play_id`.
"""

from __future__ import annotations

import math
from typing import Optional

import pandas as pd

from . import config
from .download import sha256_of

PBP_COLUMNS = {
    "game_id", "old_game_id", "play_id", "season", "week", "home_team", "away_team",
    "posteam", "defteam", "qtr", "quarter_seconds_remaining", "time", "down", "ydstogo",
    "yardline_100", "goal_to_go", "play_type", "desc", "yards_gained", "epa", "wpa", "wp",
    "touchdown", "td_team", "pass_touchdown", "rush_touchdown", "return_touchdown",
    "complete_pass", "incomplete_pass", "interception", "sack", "fumble", "fumble_lost",
    "safety", "penalty", "penalty_yards", "penalty_team", "field_goal_result",
    "extra_point_result", "two_point_conv_result", "kick_distance", "return_yards",
    "touchback", "air_yards", "yards_after_catch", "pass_length", "pass_location",
    "run_location", "passer_player_name", "receiver_player_name", "rusher_player_name",
    "passer_jersey_number", "rusher_jersey_number", "receiver_jersey_number",
    "kickoff_returner_player_name", "punt_returner_player_name", "interception_player_name",
    "punt_fair_catch", "kickoff_fair_catch", "qb_kneel", "qb_spike", "qb_scramble",
    "total_home_score", "total_away_score", "drive", "special_teams_play",
}

PARTICIPATION_SOURCE = "nflverse participation (NGS and FTN data)"
FTN_SOURCE = "FTN Data charting via nflverse"


def _clean(v):
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if hasattr(v, "item"):  # numpy scalar
        v = v.item()
        if isinstance(v, float) and math.isnan(v):
            return None
    return v


def _flag(v) -> bool:
    v = _clean(v)
    if v is None:
        return False
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "t", "yes")
    return bool(v)


class OfficialData:
    """Lookup of official play-by-play and charted labels for one or more seasons."""

    def __init__(self, seasons: list[int]):
        self.pbp: dict[tuple[str, int], dict] = {}
        self.pbp_counts: dict[tuple[str, int], int] = {}
        self.participation: dict[tuple[str, int], dict] = {}
        self.ftn: dict[tuple[str, int], dict] = {}
        self.sources: dict[str, str] = {}
        for season in seasons:
            self._load_season(season)

    def _load_season(self, season: int) -> None:
        nfl = config.RAW / "nflverse"
        pbp_path = nfl / f"play_by_play_{season}.csv.gz"
        if not pbp_path.exists():
            raise SystemExit(f"Missing {pbp_path}; run `make download` first.")
        pbp = pd.read_csv(pbp_path, usecols=lambda c: c in PBP_COLUMNS, low_memory=False)
        pbp = pbp[pbp["old_game_id"].notna() & pbp["play_id"].notna()]
        for rec in pbp.to_dict("records"):
            k = (str(int(rec["old_game_id"])), int(rec["play_id"]))
            self.pbp_counts[k] = self.pbp_counts.get(k, 0) + 1
            self.pbp[k] = {key: _clean(v) for key, v in rec.items()}
        self.sources[pbp_path.name] = sha256_of(pbp_path)

        part_path = nfl / f"pbp_participation_{season}.csv"
        if part_path.exists():
            part = pd.read_csv(part_path, low_memory=False)
            for rec in part.to_dict("records"):
                if _clean(rec.get("old_game_id")) is None:
                    continue
                k = (str(int(rec["old_game_id"])), int(rec["play_id"]))
                self.participation[k] = {key: _clean(v) for key, v in rec.items()}
            self.sources[part_path.name] = sha256_of(part_path)

        ftn_path = nfl / f"ftn_charting_{season}.csv"
        if ftn_path.exists():
            ftn = pd.read_csv(ftn_path, low_memory=False)
            by_nflverse = {(r["game_id"], int(r["play_id"])): k for k, r in self.pbp.items()
                           if r.get("game_id") is not None}
            for rec in ftn.to_dict("records"):
                k = by_nflverse.get((rec.get("nflverse_game_id"), _clean(rec.get("nflverse_play_id"))))
                if k is not None:
                    self.ftn[k] = {key: _clean(v) for key, v in rec.items()}
            self.sources[ftn_path.name] = sha256_of(ftn_path)

    # ------------------------------------------------------------------
    def official(self, game_id: str, play_id: int) -> tuple[Optional[dict], int]:
        k = (game_id, play_id)
        return self.pbp.get(k), self.pbp_counts.get(k, 0)

    def labels(self, game_id: str, play_id: int) -> dict:
        """Charted labels as {label: {"value", "source"}}."""
        out: dict[str, dict] = {}
        k = (game_id, play_id)
        p = self.participation.get(k)
        if p:
            for label, col in (("formation", "offense_formation"),
                               ("personnel_offense", "offense_personnel"),
                               ("personnel_defense", "defense_personnel"),
                               ("box", "defenders_in_box"),
                               ("rushers", "number_of_pass_rushers"),
                               ("coverage", "defense_coverage_type"),
                               ("man_zone", "defense_man_zone_type"),
                               ("route", "route")):
                v = _clean(p.get(col))
                if v is not None:
                    if isinstance(v, float) and v.is_integer():
                        v = int(v)
                    out[label] = {"value": v, "source": PARTICIPATION_SOURCE}
        f = self.ftn.get(k)
        if f:
            for label, col in (("qb_location", "qb_location"), ("motion", "is_motion"),
                               ("play_action", "is_play_action"), ("screen", "is_screen_pass"),
                               ("rpo", "is_rpo"), ("blitzers", "n_blitzers"),
                               ("ftn_rushers", "n_pass_rushers"), ("ftn_box", "n_defense_box"),
                               ("no_huddle", "is_no_huddle"), ("trick_play", "is_trick_play")):
                v = _clean(f.get(col))
                if v is not None:
                    out[label] = {"value": v, "source": FTN_SOURCE}
        return out


def result_text(o: dict) -> str:
    """Short official result, e.g. 'Complete, 7 yds' or 'Punt, 59 yds, return 8'."""
    pt = o.get("play_type")
    yds = _clean(o.get("yards_gained"))
    yds_i = int(yds) if yds is not None else None

    def yd(n):
        return f"{n} yd" if abs(n) == 1 else f"{n} yds"

    if _flag(o.get("safety")):
        base = "Safety"
    elif _flag(o.get("touchdown")):
        if _flag(o.get("return_touchdown")):
            base = "Return touchdown"
        elif _flag(o.get("interception")):
            base = "Pick-six"
        else:
            base = "Touchdown"
    elif _flag(o.get("interception")):
        base = "Interception"
    elif _flag(o.get("fumble_lost")):
        base = "Fumble lost"
    elif pt == "pass":
        if _flag(o.get("sack")):
            base = f"Sack, {yd(yds_i)}" if yds_i is not None else "Sack"
        elif _flag(o.get("complete_pass")):
            base = f"Complete, {yd(yds_i)}" if yds_i is not None else "Complete"
        elif _flag(o.get("qb_scramble")):
            base = f"Scramble, {yd(yds_i)}" if yds_i is not None else "Scramble"
        else:
            base = "Incomplete"
    elif pt == "run":
        base = f"Run, {yd(yds_i)}" if yds_i is not None else "Run"
    elif pt == "punt":
        dist = _clean(o.get("kick_distance"))
        base = f"Punt, {yd(int(dist))}" if dist is not None else "Punt"
        if _flag(o.get("punt_fair_catch")):
            base += ", fair catch"
        elif _flag(o.get("touchback")):
            base += ", touchback"
        elif _clean(o.get("return_yards")):
            base += f", return {int(o['return_yards'])}"
    elif pt == "kickoff":
        if _flag(o.get("touchback")):
            base = "Kickoff, touchback"
        elif _clean(o.get("return_yards")) is not None:
            base = f"Kickoff, return {yd(int(o['return_yards']))}"
        else:
            base = "Kickoff"
    elif pt == "field_goal":
        res = (o.get("field_goal_result") or "").replace("_", " ")
        dist = _clean(o.get("kick_distance"))
        base = f"Field goal {res}".strip() + (f", {yd(int(dist))}" if dist is not None else "")
    elif pt == "extra_point":
        base = f"Extra point {(o.get('extra_point_result') or '').replace('_', ' ')}".strip()
    elif pt == "qb_kneel":
        base = "Kneel"
    elif pt == "qb_spike":
        base = "Spike"
    elif pt == "no_play":
        base = "No play"
    else:
        base = str(pt or "Play").replace("_", " ").capitalize()
    if _flag(o.get("penalty")) and pt != "no_play":
        base += " · penalty"
    return base


def play_type(o: Optional[dict], special_teams: Optional[str]) -> str:
    if special_teams:
        return special_teams
    if not o:
        return "unknown"
    pt = o.get("play_type")
    if pt == "pass" and _flag(o.get("sack")):
        return "sack"
    if pt == "pass" and _flag(o.get("qb_scramble")):
        return "scramble"
    return str(pt or "unknown")
