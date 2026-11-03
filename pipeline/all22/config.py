"""Paths and the fixed thresholds every check and rule uses.

Thresholds live here, in one place, so a rule never drifts between runs:
the same positions always give the same call.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(os.environ.get("ALL22_ROOT", Path(__file__).resolve().parents[2]))
RAW = ROOT / "data" / "raw"
BUILD = ROOT / "build"
PLAYS_OUT = BUILD / "plays"
REPORT_OUT = BUILD / "report"
APP_PLAYDATA = ROOT / "app" / "PlayData"
REVIEWS_FILE = ROOT / "reviews" / "reviews.csv"

FRAME_RATE = 10  # tracking frames per second

# --- Hard checks -----------------------------------------------------------
MAX_PLAYER_SPEED = 11.0  # yd/s, about 22.5 mph; the ball is exempt
MAX_FILL_FRAMES = 5  # interior sensor gaps up to 0.5 s are interpolated and flagged
PLAYERS_PER_SIDE = 11

# --- Play window -----------------------------------------------------------
TAIL_FRAMES = 15  # keep 1.5 s after the whistle
MAX_PRESNAP_FRAMES = 100  # when line_set is missing, keep at most 10 s before the snap

# --- Soft checks -----------------------------------------------------------
YARDS_TOLERANCE = 2.0  # carrier's advance vs official yards
BALL_TO_CARRIER_MAX = 3.0  # ball sensor vs carrier at the whistle

# --- Derived pre-snap rules (frozen once tuned against charted labels) -----
BACKFIELD_MIN_DEPTH = 1.5  # yd behind the ball...
BACKFIELD_MAX_WIDTH = 4.0  # ...and within this many yd of it laterally = in the backfield
BUNCH_MAX_SPREAD = 3.0  # 3 receivers within this lateral spread...
BUNCH_MAX_DISTANCE = 4.0  # ...and pairwise distance, at least one off the line
BUNCH_MIN_DEPTH_SPREAD = 0.75
STACK_MAX_LATERAL = 1.25  # 2 receivers nearly in line...
STACK_MIN_DEPTH_GAP = 1.0  # ...one at least this far behind the other
DETACHED_MIN_WIDTH = 4.5  # bunch/stack only among receivers this far from the ball
JET_MIN_SPEED = 4.5  # yd/s lateral speed just before the snap for "jet motion"
MOTION_MIN_SPEED = 2.5  # yd/s (about 5 mph) just before the snap for "in motion"

# --- Ball model (height is synthesized; the path is tracked) ---------------
GRAVITY_YD = 10.725  # 9.807 m/s^2 in yd/s^2
PASS_RELEASE_HEIGHT = 2.0  # yd (6 ft)
CATCH_HEIGHT = 1.4
CARRY_HEIGHT = 1.0
GROUND_HEIGHT = 0.1
PUNT_CONTACT_HEIGHT = 0.7
SNAP_RECEIPT_MAX_FRAMES = 8  # the snap reaches its receiver within 0.8 s
SNAP_RECEIPT_DISTANCE = 1.0  # yd

# --- Field -----------------------------------------------------------------
FIELD_LENGTH = 120.0
FIELD_WIDTH = 53.3  # the source's own width; flipping with it keeps hundredths exact
GOAL_LINE_RIGHT = 110.0
