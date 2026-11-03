"""Stage 3: flip every play so the offense moves left to right (toward +x).

The flip is exact and reversible: x' = 120 - x, y' = 53.3 - y, angles + 180.
All source values have two decimals, so the packed hundredths stay lossless.
Units stay in yards here; the app converts to meters for its 3D scene.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from . import config
from .model import Play

SNAP_EVENTS = ("ball_snap", "snap_direct", "autoevent_ballsnap")
KICK_EVENTS = ("kickoff", "onside_kick", "free_kick")


def start_frame(play: Play) -> Optional[int]:
    return play.frame_of(*SNAP_EVENTS) if play.meta.get("special_teams") != "kickoff" \
        else play.frame_of(*KICK_EVENTS)


def los_to_goal(meta: dict) -> Optional[float]:
    """Yards from the line of scrimmage to the goal line the possession team attacks."""
    side, number = meta.get("yardline_side"), meta.get("yardline_number")
    if number is None:
        return None
    if number == 50 or side is None:
        return 50.0
    return float(100 - number) if side == meta.get("possession") else float(number)


def infer_direction(play: Play) -> tuple[str, str]:
    """('right' or 'left', how it was decided) for the possession team's attack."""
    given = play.meta.get("play_direction")
    f = start_frame(play)
    f = 0 if f is None else f
    off, dfn = play.players("offense"), play.players("defense")
    geo = None
    if off and dfn:
        mo, md = np.nanmean(play.x[f, off]), np.nanmean(play.x[f, dfn])
        if not (np.isnan(mo) or np.isnan(md)):
            geo = "right" if mo < md else "left"
    if given in ("left", "right"):
        if geo and geo != given:
            play.notes.append(f"source play direction {given} disagrees with player positions")
        return given, "source"
    yl = None
    to_goal = los_to_goal(play.meta)
    ball_x = play.x[f, 0]
    if to_goal is not None and not np.isnan(ball_x):
        right_x = config.GOAL_LINE_RIGHT - to_goal
        left_x = 10.0 + to_goal
        # Near midfield both spots are within the ball sensor's noise; don't vote there.
        if abs(right_x - left_x) > 6.0:
            yl = "right" if abs(ball_x - right_x) <= abs(ball_x - left_x) else "left"
    if geo and yl and geo != yl:
        play.notes.append("direction from player positions and from the yard line disagree; "
                          "used player positions")
    if geo:
        return geo, "player positions"
    if yl:
        return yl, "yard line"
    return "right", "unknown"


def flip(play: Play) -> None:
    play.x = np.round(config.FIELD_LENGTH - play.x, 2)
    play.y = np.round(config.FIELD_WIDTH - play.y, 2)
    play.dir = np.round((play.dir + 180.0) % 360.0, 2)
    play.o = np.round((play.o + 180.0) % 360.0, 2)
    play.flipped = not play.flipped


def normalize(play: Play) -> None:
    direction, how = infer_direction(play)
    play.derived["sourceDirection"] = direction
    play.derived["directionMethod"] = how
    if direction == "left":
        flip(play)
