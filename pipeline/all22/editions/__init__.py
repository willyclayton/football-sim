"""Edition adapters: each Big Data Bowl release has its own file layout and
column names. An adapter hides that and yields `PlayInput`s in one shape.

Canonical play fields (dict keys of `PlayInput.play`):
    game_id, play_id, quarter, clock_seconds, down, yards_to_go,
    possession, defense_team, yardline_side, yardline_number,
    score_before {home, away}, score_after {home, away} or None,
    special_teams (None, "kickoff", "punt", "field_goal", "extra_point", ...),
    description, play_direction (None, "left", "right"),
    charted: {label: {"value": ..., "source": "..."}}
"""

from __future__ import annotations

from .bdb2019 import BDB2019Sample
from .bdb2025 import BDB2025

EDITIONS = {e.id: e for e in (BDB2019Sample, BDB2025)}


def get(edition_id: str):
    try:
        return EDITIONS[edition_id]()
    except KeyError:
        raise SystemExit(f"Unknown edition {edition_id!r}; choose from {sorted(EDITIONS)}")
