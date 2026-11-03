"""Stage 4: hard checks drop a play; soft checks flag it for video review.

Hard checks (a failure drops the play):
  joined             every tracked play matches exactly one official play
  frames_contiguous  no gaps in the 10-per-second frame count
  full_roster        11 offensive players, 11 defensive players and the ball
  positions_present  no blank coordinates inside the play window
  snap_present       scrimmage plays have a tagged snap (kickoffs: a kick)
  events_in_order    snap before throw before arrival, and so on
  plausible_speed    no player over 11 yd/s (about 22.5 mph)

Two repairs are allowed, and both are recorded on the play:
  * an interior sensor gap of up to 0.5 s is filled by straight-line
    interpolation and every filled record is flagged FILLED;
  * a sensor dropout that starts after the whistle (or ends before the
    snap) is trimmed from the window, since it is outside the play.

Soft checks (see run_soft) need the derived ball carrier.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from . import config
from .model import FLAG_FILLED, CheckResult, Play
from .normalize import KICK_EVENTS, SNAP_EVENTS, start_frame

THROW_EVENTS = ("pass_forward", "pass_shovel", "autoevent_passforward")
ARRIVAL_EVENTS = ("pass_arrived",)
OUTCOME_EVENTS = ("pass_outcome_caught", "pass_outcome_incomplete", "pass_outcome_interception",
                  "pass_outcome_touchdown")
END_EVENTS = (
    "tackle", "out_of_bounds", "touchdown", "pass_outcome_incomplete", "pass_outcome_touchdown",
    "qb_sack", "fair_catch", "qb_kneel", "qb_spike", "qb_slide", "touchback", "field_goal",
    "field_goal_missed", "field_goal_blocked", "extra_point", "extra_point_missed",
    "extra_point_blocked", "safety", "punt_downed",
)


def whistle_frame(play: Play) -> Optional[int]:
    s = start_frame(play)
    return play.frame_of(*END_EVENTS, after=-1 if s is None else s)


def _runs(mask: np.ndarray):
    """Yield (start, end) index pairs of consecutive True values."""
    i, n = 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j + 1 < n and mask[j + 1]:
                j += 1
            yield i, j
            i = j + 1
        else:
            i += 1


def _angle_lerp(a: float, b: float, t: float) -> float:
    if np.isnan(a) or np.isnan(b):
        return np.nan
    d = ((b - a + 180.0) % 360.0) - 180.0
    return round((a + d * t) % 360.0, 2)


def _fill(play: Play, e: int, r0: int, r1: int) -> None:
    """Straight-line fill of records r0..r1 for entity e from the frames on either side."""
    a, b = r0 - 1, r1 + 1
    for f in range(r0, r1 + 1):
        t = (f - a) / (b - a)
        for arr in (play.x, play.y, play.s):
            if not (np.isnan(arr[a, e]) or np.isnan(arr[b, e])):
                arr[f, e] = round(arr[a, e] + (arr[b, e] - arr[a, e]) * t, 2)
        play.dir[f, e] = _angle_lerp(play.dir[a, e], play.dir[b, e], t)
        play.o[f, e] = _angle_lerp(play.o[a, e], play.o[b, e], t)
        play.flags[f, e] |= FLAG_FILLED


def set_window(play: Play) -> None:
    """Choose the frames that ship: line set (or a capped pre-snap) through whistle + 1.5 s."""
    F = play.n_frames
    s = start_frame(play)
    a = 0
    if s is not None:
        line_set = play.frame_of("line_set")
        if line_set is not None and line_set <= s and s - line_set <= config.MAX_PRESNAP_FRAMES:
            a = line_set
        else:
            a = max(0, s - config.MAX_PRESNAP_FRAMES)
    w = whistle_frame(play)
    b = F - 1 if w is None else min(F - 1, w + config.TAIL_FRAMES)
    play.window = (a, b)
    play.derived["whistleFrame"] = w


def check_positions(play: Play) -> CheckResult:
    name = "Positions present"
    valid = play.present & ~np.isnan(play.x) & ~np.isnan(play.y)
    s, w = start_frame(play), play.derived.get("whistleFrame")
    a, b = play.window
    filled, trimmed_tail, trimmed_head = 0, 0, 0
    for _ in range(4):  # trimming can expose new edges; settle in a few passes
        new_a, new_b, problems = a, b, []
        for e in range(len(play.entities)):
            missing = ~valid[a:b + 1, e]
            for r0, r1 in _runs(missing):
                r0, r1 = r0 + a, r1 + a
                interior = r0 > a and r1 < b
                if interior and r1 - r0 + 1 <= config.MAX_FILL_FRAMES:
                    continue  # short interior gap: filled once the window settles
                if w is not None and r0 > w:
                    new_b = min(new_b, r0 - 1)  # dropout after the whistle: trim the tail
                elif s is not None and r1 < s:
                    new_a = max(new_a, r1 + 1)  # dropout before the snap: trim the head
                else:
                    who = play.entities[e].name or play.entities[e].key
                    problems.append(f"{who} missing frames {r0}-{r1}")
        if problems:
            return CheckResult("positions_present", name, "hard", "fail", "; ".join(problems[:3]))
        if (new_a, new_b) == (a, b):
            break
        trimmed_tail += b - new_b
        trimmed_head += new_a - a
        a, b = new_a, new_b
    play.window = (a, b)

    problems = []
    for e in range(len(play.entities)):
        for r0, r1 in _runs(~valid[a:b + 1, e]):
            r0, r1 = r0 + a, r1 + a
            length = r1 - r0 + 1
            who = play.entities[e].name or play.entities[e].key
            if length > config.MAX_FILL_FRAMES:
                problems.append(f"{who} missing {length} frames ({r0}-{r1})")
            else:
                _fill(play, e, r0, r1)
                filled += length
    if problems:
        return CheckResult("positions_present", name, "hard", "fail", "; ".join(problems[:3]))
    parts = []
    if filled:
        parts.append(f"{filled} records filled across short sensor gaps")
    if trimmed_tail:
        parts.append(f"{trimmed_tail} frames after the whistle trimmed (sensor dropout)")
    if trimmed_head:
        parts.append(f"{trimmed_head} frames before the snap trimmed (sensor dropout)")
    if parts:
        return CheckResult("positions_present", name, "hard", "fixed", "; ".join(parts))
    return CheckResult("positions_present", name, "hard", "pass", "Every position present")


def check_roster(play: Play) -> CheckResult:
    off, dfn = len(play.players("offense")), len(play.players("defense"))
    want = config.PLAYERS_PER_SIDE
    ball = any(e.kind == "ball" for e in play.entities) and play.present[:, 0].any()
    ok = off == want and dfn == want and ball
    detail = f"{off} offense, {dfn} defense, ball {'tracked' if ball else 'missing'}"
    return CheckResult("full_roster", "Full roster every frame", "hard",
                       "pass" if ok else "fail", detail)


def check_joined(play: Play, count: int) -> CheckResult:
    ok = count == 1
    detail = ("Matched one official play" if ok else
              "No official play found" if count == 0 else f"{count} official plays match")
    return CheckResult("joined", "Joined to official play-by-play", "hard",
                       "pass" if ok else "fail", detail)


def check_frames(play: Play) -> CheckResult:
    f = play.source_frames
    ok = len(f) > 0 and np.array_equal(f, np.arange(f[0], f[0] + len(f)))
    detail = f"{len(f)} frames" if ok else "Gaps in the frame count"
    return CheckResult("frames_contiguous", "Frames contiguous", "hard",
                       "pass" if ok else "fail", detail)


def check_snap(play: Play) -> CheckResult:
    if play.meta.get("special_teams") == "kickoff":
        f = play.frame_of(*KICK_EVENTS)
        return CheckResult("snap_present", "Snap event present", "hard",
                           "pass" if f is not None else "fail",
                           "Kickoff: kick tagged" if f is not None else "Kickoff without a kick event")
    f = play.frame_of(*SNAP_EVENTS)
    if f is None:
        return CheckResult("snap_present", "Snap event present", "hard", "fail", "No snap tagged")
    name = next(n for i, n in play.events if i == f and n in SNAP_EVENTS)
    return CheckResult("snap_present", "Snap event present", "hard", "pass", f"Tagged {name}")


def check_order(play: Play) -> CheckResult:
    s = start_frame(play)
    chain = [("start", s), ("throw", play.frame_of(*THROW_EVENTS)),
             ("arrival", play.frame_of(*ARRIVAL_EVENTS)), ("outcome", play.frame_of(*OUTCOME_EVENTS))]
    present = [(n, f) for n, f in chain if f is not None]
    problems = [f"{n2} before {n1}" for (n1, f1), (n2, f2) in zip(present, present[1:]) if f2 < f1]
    for name in ("handoff", "punt", "pass_forward", "lateral"):
        f = play.frame_of(name)
        if f is not None and s is not None and f < s:
            problems.append(f"{name} before the start")
    for recv, kick in (("kick_received", "kickoff"), ("punt_received", "punt")):
        fr, fk = play.frame_of(recv), play.frame_of(kick)
        if fr is not None and fk is not None and fr < fk:
            problems.append(f"{recv} before {kick}")
    w = play.derived.get("whistleFrame")
    if w is not None and s is not None and w < s:
        problems.append("whistle before the start")
    if problems:
        return CheckResult("events_in_order", "Events in order", "hard", "fail", "; ".join(problems))
    return CheckResult("events_in_order", "Events in order", "hard", "pass",
                       " < ".join(n for n, _ in present) or "No ordered events")


def check_speed(play: Play) -> CheckResult:
    a, b = play.window
    idx = play.players()
    sp = play.s[a:b + 1, idx]
    if np.all(np.isnan(sp)):
        return CheckResult("plausible_speed", "Plausible speed", "hard", "fail", "No speeds")
    top = float(np.nanmax(sp))
    f, j = np.unravel_index(np.nanargmax(sp), sp.shape)
    who = play.entities[idx[j]].name or "?"
    ok = top <= config.MAX_PLAYER_SPEED
    detail = f"Fastest {top:.2f} yd/s ({top * 2.04545:.1f} mph), {who}"
    return CheckResult("plausible_speed", "Plausible speed", "hard", "pass" if ok else "fail", detail)


def run_hard(play: Play, official_count: int) -> None:
    play.checks.append(check_joined(play, official_count))
    play.checks.append(check_frames(play))
    play.checks.append(check_roster(play))
    set_window(play)
    play.checks.append(check_positions(play))
    play.checks.append(check_snap(play))
    play.checks.append(check_order(play))
    play.checks.append(check_speed(play))


# ----------------------------------------------------------------------------
# Soft checks
# ----------------------------------------------------------------------------

def run_soft(play: Play) -> None:
    """Needs derive.py to have set derived['carrier'], ['carrierCheckable'] and ['losOfficialX']."""
    carrier = play.derived.get("carrier")
    w = play.derived.get("whistleFrame")
    official = play.official or {}
    checkable = play.derived.get("carrierCheckable")
    if not checkable or carrier is None or w is None or official.get("yards_gained") is None:
        why = play.derived.get("carrierNote") or "Not a run or completion with a tagged whistle"
        play.checks.append(CheckResult("yards_agree", "Yards agree", "soft", "n/a", why))
        play.checks.append(CheckResult("ball_sensor_agrees", "Ball sensor agrees", "soft", "n/a", why))
        return
    los = play.derived["losOfficialX"]
    cx = min(play.x[w, carrier], config.GOAL_LINE_RIGHT)
    advance = cx - los
    official_yds = float(official["yards_gained"])
    gap = abs(advance - official_yds)
    play.derived["yardsGap"] = round(gap, 2)
    play.checks.append(CheckResult(
        "yards_agree", "Yards agree", "soft",
        "pass" if gap <= config.YARDS_TOLERANCE else "fail",
        f"Tracked advance {advance:.1f} yds vs official {official_yds:.0f} (gap {gap:.1f})"))
    bx, by = play.x[w, 0], play.y[w, 0]
    if np.isnan(bx) or np.isnan(by):
        play.checks.append(CheckResult("ball_sensor_agrees", "Ball sensor agrees", "soft", "fail",
                                       "No ball position at the whistle"))
        return
    d = float(np.hypot(bx - play.x[w, carrier], by - play.y[w, carrier]))
    play.derived["ballGap"] = round(d, 2)
    play.checks.append(CheckResult(
        "ball_sensor_agrees", "Ball sensor agrees", "soft",
        "pass" if d <= config.BALL_TO_CARRIER_MAX else "fail",
        f"Ball sensor {d:.1f} yds from the carrier at the whistle"))
