"""Stage 5: everything computed from tracked positions with fixed rules.

* key frames (snap, throw, arrival, catch, contact, tackle, whistle)
* the ball carrier, matched to the official play-by-play by jersey number
* who holds the ball when, and the throw's arc (the data is 2D, so height
  is synthesized from flight time; the path itself is tracked)
* the game clock's start frame
* pre-snap callouts with badges (derived rules + charted labels)
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Optional

import numpy as np

from . import config
from .checks import ARRIVAL_EVENTS, OUTCOME_EVENTS, THROW_EVENTS
from .model import (CHARTED, DERIVED, ELIGIBLE_GROUPS, OFFICIAL, TRACKED,
                    Callout, Play)
from .normalize import KICK_EVENTS, SNAP_EVENTS, los_to_goal, start_frame

FORMATIONS = {
    "SHOTGUN": "Shotgun", "SINGLEBACK": "Singleback", "EMPTY": "Empty", "I_FORM": "I-formation",
    "PISTOL": "Pistol", "JUMBO": "Jumbo", "WILDCAT": "Wildcat", "ACE": "Ace",
}
QB_LOCATION = {"S": "Shotgun", "U": "Under center", "P": "Pistol"}
PACKAGES = {4: "Base", 5: "Nickel", 6: "Dime", 7: "Quarter"}
ST_UNITS = {
    "kickoff": ("Kickoff team", "Kick return"),
    "punt": ("Punt team", "Punt return"),
    "field_goal": ("Field goal unit", "Field goal block"),
    "extra_point": ("Extra point unit", "Extra point block"),
}
SUFFIXES = {"JR", "JR.", "SR", "SR.", "II", "III", "IV", "V"}


# ----------------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------------

def _num(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(f) else f


def short_name(full: Optional[str]) -> Optional[str]:
    """'De'Anthony Thomas' -> 'd.thomas', the play-by-play's style."""
    if not full:
        return None
    parts = [p for p in full.replace(",", " ").split() if p.upper() not in SUFFIXES]
    if len(parts) < 2:
        return full.lower()
    return f"{parts[0][0]}.{parts[-1]}".lower()


def pbp_name(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    t = str(text).strip()
    return re.sub(r"\s+", "", t).lower()


def parse_personnel(text) -> Optional[dict]:
    """'1 RB, 2 TE, 2 WR' -> {'RB': 1, 'TE': 2, 'WR': 2}."""
    if not text or not isinstance(text, str):
        return None
    out: Counter = Counter()
    for m in re.finditer(r"(\d+)\s*([A-Z]{1,3})", text.upper()):
        out[m.group(2)] += int(m.group(1))
    return dict(out) or None


def side_word(lateral: float) -> str:
    # Offense attacks +x; looking downfield, +y is its left.
    return "left" if lateral > 0 else "right"


# ----------------------------------------------------------------------------
# Key frames and carrier
# ----------------------------------------------------------------------------

def key_frames(play: Play) -> dict:
    s = start_frame(play)
    after = -1 if s is None else s
    k = {
        "start": play.window[0],
        "snap": play.frame_of(*SNAP_EVENTS),
        "kick": play.frame_of(*KICK_EVENTS) or play.frame_of("punt", "field_goal_attempt",
                                                              "extra_point_attempt"),
        "handoff": play.frame_of("handoff", after=after),
        "throw": play.frame_of(*THROW_EVENTS, after=after),
        "arrival": play.frame_of(*ARRIVAL_EVENTS, after=after),
        "catch": play.frame_of("pass_outcome_caught", "pass_outcome_touchdown", after=after),
        "outcome": play.frame_of(*OUTCOME_EVENTS, after=after),
        "received": play.frame_of("kick_received", "punt_received", after=after),
        "contact": play.frame_of("first_contact", after=after),
        "tackle": play.frame_of("tackle", after=after),
        "whistle": play.derived.get("whistleFrame"),
        "end": play.window[1],
    }
    return k


def _by_jersey(play: Play, side: str, jersey) -> Optional[int]:
    j = _num(jersey)
    if j is None:
        return None
    hits = [i for i in play.players(side) if play.entities[i].jersey == int(j)]
    return hits[0] if len(hits) == 1 else None


def _by_name(play: Play, side: Optional[str], name) -> Optional[int]:
    want = pbp_name(name)
    if not want:
        return None
    hits = [i for i in play.players(side) if short_name(play.entities[i].name) == want]
    return hits[0] if len(hits) == 1 else None


def _nearest(play: Play, frame: int, candidates: list, exclude=()) -> Optional[int]:
    bx, by = play.x[frame, 0], play.y[frame, 0]
    if np.isnan(bx) or not candidates:
        return None
    best, best_d = None, np.inf
    for i in candidates:
        if i in exclude:
            continue
        d = np.hypot(play.x[frame, i] - bx, play.y[frame, i] - by)
        if d < best_d:
            best, best_d = i, d
    return best


def _flag(v) -> bool:
    n = _num(v)
    return bool(n) if n is not None else False


def identify_carrier(play: Play, kf: dict) -> None:
    """The player holding the ball at the whistle, from the official play-by-play.

    The soft checks only judge runs and completed passes without fumbles or
    laterals: there the official yardage is the carrier's own advance.
    """
    o = play.official or {}
    pt = o.get("play_type")
    st = play.meta.get("special_teams")
    carrier, source, checkable, note = None, None, False, None
    fumble_or_lateral = _flag(o.get("fumble")) or play.frame_of("lateral", "fumble") is not None

    if st in ("kickoff", "punt"):
        name = o.get("kickoff_returner_player_name") or o.get("punt_returner_player_name")
        carrier = _by_name(play, "defense", name)
        source = "official name" if carrier is not None else None
        if carrier is None and kf.get("received") is not None:
            carrier = _nearest(play, kf["received"], play.players("defense"))
            source = "nearest to the ball" if carrier is not None else None
        note = "Returns are not scored by the yardage check"
    elif _flag(o.get("interception")):
        carrier = _by_name(play, "defense", o.get("interception_player_name"))
        source = "official name" if carrier is not None else None
        note = "Interception: official yards are not the carrier's advance"
    elif pt == "run":
        carrier = _by_jersey(play, "offense", o.get("rusher_jersey_number"))
        source = "official jersey"
        if carrier is None:
            carrier = _by_name(play, "offense", o.get("rusher_player_name"))
            source = "official name"
        checkable = carrier is not None and not fumble_or_lateral
    elif pt == "pass" and _flag(o.get("complete_pass")):
        carrier = _by_jersey(play, "offense", o.get("receiver_jersey_number"))
        source = "official jersey"
        if carrier is None:
            carrier = _by_name(play, "offense", o.get("receiver_player_name"))
            source = "official name"
        checkable = carrier is not None and not fumble_or_lateral
    elif pt == "pass" and _flag(o.get("sack")):
        carrier = _by_jersey(play, "offense", o.get("passer_jersey_number"))
        source = "official jersey"
        note = "Sacks are not scored by the yardage check"
    if carrier is None:
        source = None
    if fumble_or_lateral and note is None:
        note = "Fumble or lateral: the official yards are not one carrier's advance"
    if note is None and not checkable:
        note = "Not a run or completed pass"
    play.derived.update(carrier=carrier, carrierSource=source, carrierCheckable=checkable,
                        carrierNote=None if checkable else note)


# ----------------------------------------------------------------------------
# Ball possession and arc
# ----------------------------------------------------------------------------

def _apex(frames: int) -> float:
    t = frames / config.FRAME_RATE
    return round(config.GRAVITY_YD * t * t / 8.0, 3)


def _snap_receiver(play: Play, s: int) -> Optional[int]:
    st = play.meta.get("special_teams")
    off = play.players("offense")
    if st in ("punt", "field_goal", "extra_point"):
        # The punter takes punt snaps and usually holds for kicks.
        punters = [i for i in off if play.entities[i].position == "P"]
        if len(punters) == 1:
            return punters[0]
    qbs = [i for i in off if play.entities[i].group == "QB"]
    if play.frame_of("snap_direct") is None and len(qbs) == 1:
        return qbs[0]
    probe = min(s + 5, play.window[1])
    return _nearest(play, probe, [i for i in off if play.entities[i].group != "OL"])


def ball_segments(play: Play, kf: dict) -> list:
    """Who holds the ball when. Modes: tracked (sensor position), held (in a
    player's hands), flight (sensor path with a synthesized arc)."""
    a, b = play.window
    F = play.n_frames
    holder = np.full(F, -1, dtype=int)
    mode = np.array(["tracked"] * F, dtype=object)
    height = np.full(F, config.GROUND_HEIGHT)
    flights = []  # (f0, f1, z0, z1)
    o = play.official or {}
    off, dfn = play.players("offense"), play.players("defense")

    def hold(f0, f1, who):
        if who is None or f0 > f1:
            return
        holder[f0:f1 + 1] = who
        mode[f0:f1 + 1] = "held"
        height[f0:f1 + 1] = config.CARRY_HEIGHT

    def fly(f0, f1, z0, z1):
        if f0 >= f1:
            return
        holder[f0:f1 + 1] = -1
        mode[f0:f1 + 1] = "flight"
        flights.append((f0, f1, z0, z1))

    def loose(f0, f1):
        if f0 > f1:
            return
        holder[f0:f1 + 1] = -1
        mode[f0:f1 + 1] = "tracked"
        height[f0:f1 + 1] = config.GROUND_HEIGHT

    st = play.meta.get("special_teams")
    s = kf["snap"]
    carrier = play.derived.get("carrier")

    if st == "kickoff":
        k = play.frame_of(*KICK_EVENTS)
        if k is None:
            return []
        end_flight = play.frame_of("kick_received", "kickoff_land", "touchback", "out_of_bounds",
                                   "fair_catch", after=k)
        if end_flight is not None:
            received = play.frame_of("kick_received", after=k - 1) == end_flight
            fly(k, end_flight, config.GROUND_HEIGHT,
                config.CATCH_HEIGHT if received else config.GROUND_HEIGHT)
            later = play.frame_of("kick_received", after=end_flight - 1)
            if later is not None:
                loose(end_flight + 1, later - 1)
                returner = carrier if carrier is not None else _nearest(play, later, dfn)
                hold(later, b, returner)
            else:
                loose(end_flight + 1, b)
    elif s is not None:
        receiver = _snap_receiver(play, s)
        r = s
        if receiver is not None:
            dist = [np.hypot(play.x[f, 0] - play.x[f, receiver], play.y[f, 0] - play.y[f, receiver])
                    for f in range(s, min(s + config.SNAP_RECEIPT_MAX_FRAMES, b) + 1)]
            close = [i for i, d in enumerate(dist) if d <= config.SNAP_RECEIPT_DISTANCE]
            r = s + (close[0] if close else int(np.nanargmin(dist)) if dist else 0)
            r = max(r, s + 1) if r < b else r
            fly(s, r, config.GROUND_HEIGHT, config.CARRY_HEIGHT)
        current, cursor = receiver, r
        # Walk the possession events in order.
        for f, name in play.events:
            if f <= s or f > b:
                continue
            if name == "handoff":
                hold(cursor, f, current)
                new = carrier if (carrier is not None and o.get("play_type") == "run"
                                  and carrier != current) else _nearest(
                    play, min(f + 2, b), off, exclude=(current,))
                current, cursor = new, f
            elif name in THROW_EVENTS:
                hold(cursor, f, current)
                arrival = play.frame_of(*ARRIVAL_EVENTS, after=f)
                outcome = play.frame_of(*OUTCOME_EVENTS, after=f - 1)
                outcome_name = next((n for i, n in play.events if i == outcome and n in OUTCOME_EVENTS),
                                    None) if outcome is not None else None
                caught = outcome_name in ("pass_outcome_caught", "pass_outcome_touchdown",
                                          "pass_outcome_interception")
                # A caught ball flies until the catch; an incomplete one until it arrives.
                end = outcome if caught else (arrival if arrival is not None else outcome)
                end = b if end is None else min(end, b)
                fly(f, end, config.PASS_RELEASE_HEIGHT, config.CATCH_HEIGHT)
                if outcome_name in ("pass_outcome_caught", "pass_outcome_touchdown"):
                    catcher = carrier if (carrier is not None and play.entities[carrier].side == "offense") \
                        else _nearest(play, end, off, exclude=(current,))
                    current, cursor = catcher, end
                elif outcome_name == "pass_outcome_interception":
                    picker = carrier if carrier is not None else _nearest(play, end, dfn)
                    current, cursor = picker, end
                else:  # incomplete: the ball drops and is dead
                    loose(end + 1, b)
                    current, cursor = None, b + 1
                    break
            elif name in ("punt", "field_goal_attempt", "extra_point_attempt"):
                hold(cursor, f, current)
                after_kick = play.frame_of("punt_received", "punt_land", "fair_catch", "out_of_bounds",
                                           "touchback", "punt_downed", "field_goal", "field_goal_missed",
                                           "field_goal_blocked", "extra_point", "extra_point_missed",
                                           "extra_point_blocked", after=f)
                land = b if after_kick is None else after_kick
                caught = play.frame_of("punt_received", "fair_catch", after=f) == land
                z0 = config.PUNT_CONTACT_HEIGHT if name == "punt" else config.GROUND_HEIGHT
                fly(f, land, z0, config.CATCH_HEIGHT if caught else config.GROUND_HEIGHT)
                later = play.frame_of("punt_received", after=land - 1) if name == "punt" else None
                if later is not None:
                    loose(land + 1, later - 1)
                    returner = carrier if carrier is not None else _nearest(play, later, dfn)
                    current, cursor = returner, later
                else:
                    loose(land + 1, b)
                    current, cursor = None, b + 1
                    break
            elif name in ("fumble", "qb_strip_sack"):
                hold(cursor, f, current)
                rec = play.frame_of("fumble_offense_recovered", "fumble_defense_recovered", after=f)
                if rec is None:
                    loose(f + 1, b)
                    current, cursor = None, b + 1
                    break
                loose(f + 1, rec - 1)
                current, cursor = _nearest(play, rec, play.players()), rec
            elif name == "lateral":
                hold(cursor, f, current)
                to = _nearest(play, min(f + 5, b), off, exclude=(current,))
                fly(f, min(f + 5, b), config.CARRY_HEIGHT, config.CARRY_HEIGHT)
                current, cursor = to, min(f + 5, b)
        if cursor <= b:
            hold(cursor, b, current)

    # Compress per-frame state into segments over the window.
    segs = []
    f = a
    flight_at = {}
    for f0, f1, z0, z1 in flights:
        for i in range(f0, f1 + 1):
            flight_at[i] = (f0, f1, z0, z1)
    while f <= b:
        if mode[f] == "flight":
            f0, f1, z0, z1 = flight_at[f]
            seg = {"from": max(f0, a) - a, "to": min(f1, b) - a, "mode": "flight",
                   "z0": round(z0, 2), "z1": round(z1, 2), "apex": _apex(f1 - f0)}
            segs.append(seg)
            f = min(f1, b) + 1
            continue
        g = f
        while g + 1 <= b and mode[g + 1] == mode[f] and holder[g + 1] == holder[f]:
            g += 1
        seg = {"from": f - a, "to": g - a, "mode": str(mode[f])}
        if mode[f] == "held":
            seg["holder"] = int(holder[f])
        else:
            seg["z0"] = round(float(height[f]), 2)
        segs.append(seg)
        f = g + 1
    return segs


# ----------------------------------------------------------------------------
# Callouts
# ----------------------------------------------------------------------------

def _charted(play: Play, key: str) -> Optional[dict]:
    """A charted label from the edition first, then nflverse."""
    return play.meta.get("charted", {}).get(key) or play.labels.get(key)


def _reference(play: Play, f: int) -> tuple[float, float]:
    """Where the ball sits at the snap; the center stands in if the sensor strays."""
    bx, by = play.x[f, 0], play.y[f, 0]
    centers = [i for i in play.players("offense") if play.entities[i].position == "C"]
    if centers:
        c = centers[0]
        cx, cy = play.x[f, c], play.y[f, c]
        if np.isnan(bx) or np.hypot(bx - cx, by - cy) > 2.0:
            return cx + 0.5, cy
    return bx, by


def receiver_set(play: Play, f: int) -> dict:
    ref_x, ref_y = _reference(play, f)
    receivers, backs = [], []
    for i in play.players("offense"):
        e = play.entities[i]
        if e.group not in ELIGIBLE_GROUPS:
            continue
        depth = ref_x - play.x[f, i]
        lat = play.y[f, i] - ref_y
        if depth > config.BACKFIELD_MIN_DEPTH and abs(lat) < config.BACKFIELD_MAX_WIDTH:
            backs.append(i)
        else:
            receivers.append((i, depth, lat))
    left = [r for r in receivers if r[2] > 0]
    right = [r for r in receivers if r[2] <= 0]
    hi, lo = max(len(left), len(right)), min(len(left), len(right))
    strong = "left" if len(left) > len(right) else "right"
    notation = f"{hi}x{lo}"
    label = notation
    if not backs:
        label = f"Empty {notation}"
    elif hi == 3:
        label = f"{notation} trips {strong}" if lo else f"Trips {strong}"
    elif hi >= 4:
        label = f"{notation} quads {strong}"
    groups = []
    for side, rs in (("left", left), ("right", right)):
        detached = [r for r in rs if abs(r[2]) >= config.DETACHED_MIN_WIDTH]
        found = None
        for i in range(len(detached)):
            for j in range(i + 1, len(detached)):
                for k in range(j + 1, len(detached)):
                    trio = [detached[i], detached[j], detached[k]]
                    lats = [t[2] for t in trio]
                    deps = [t[1] for t in trio]
                    pts = [(play.x[f, t[0]], play.y[f, t[0]]) for t in trio]
                    dmax = max(np.hypot(p[0] - q[0], p[1] - q[1]) for p in pts for q in pts)
                    if (max(lats) - min(lats) <= config.BUNCH_MAX_SPREAD
                            and dmax <= config.BUNCH_MAX_DISTANCE
                            and max(deps) - min(deps) >= config.BUNCH_MIN_DEPTH_SPREAD):
                        found = f"Bunch {side}"
        if not found:
            for i in range(len(detached)):
                for j in range(i + 1, len(detached)):
                    r1, r2 = detached[i], detached[j]
                    if (abs(r1[2] - r2[2]) <= config.STACK_MAX_LATERAL
                            and abs(r1[1] - r2[1]) >= config.STACK_MIN_DEPTH_GAP):
                        found = f"Stack {side}"
        if found:
            groups.append(found)
    return {"notation": notation, "label": label, "backs": len(backs), "groups": groups,
            "left": len(left), "right": len(right)}


def build_callouts(play: Play, kf: dict) -> dict:
    offense, defense, after = [], [], []
    st = play.meta.get("special_teams")
    if st:
        unit_o, unit_d = ST_UNITS.get(st, ("Special teams", "Return team"))
        offense.append(Callout("unit", unit_o, OFFICIAL, source="Official play type", value=st))
        defense.append(Callout("unit", unit_d, OFFICIAL, source="Official play type", value=st))
        return {"offense": offense, "defense": defense, "afterSnap": after}

    snap = kf["snap"] if kf["snap"] is not None else play.window[0]
    off_groups = Counter(play.entities[i].group for i in play.players("offense"))
    rb, te, wr, ol = off_groups["RB"], off_groups["TE"], off_groups["WR"], off_groups["OL"]
    detail = f"{rb} RB, {te} TE, {wr} WR"
    extra = [f"{n} {g}" for g, n in off_groups.items() if g not in ("RB", "TE", "WR", "OL", "QB")]
    if ol != 5:
        extra.insert(0, f"{ol} OL")
    if extra:
        detail += " · " + ", ".join(extra)
    offense.append(Callout("personnel", f"{rb}{te} personnel", DERIVED, detail=detail,
                           source="Roster positions of the 11 on the field",
                           value={"RB": rb, "TE": te, "WR": wr}))

    form = _charted(play, "formation")
    qb_loc = _charted(play, "qb_location")
    if form:
        v = str(form["value"]).upper()
        offense.append(Callout("formation", FORMATIONS.get(v, v.title()), CHARTED,
                               source=form["source"], value=v))
    elif qb_loc:
        v = str(qb_loc["value"]).upper()
        offense.append(Callout("formation", QB_LOCATION.get(v, v), CHARTED,
                               source=qb_loc["source"], value=v))
    else:
        offense.append(Callout("formation", "Formation not charted", CHARTED, missing=True))

    rs = receiver_set(play, snap)
    offense.append(Callout("receiver_set", rs["label"], DERIVED,
                           detail=f"{rs['left']} receivers left, {rs['right']} right, "
                                  f"{rs['backs']} in the backfield at the snap",
                           source="Positions at the snap", value=rs["notation"]))
    for g in rs["groups"]:
        offense.append(Callout("bunch_stack", g, DERIVED, source="Positions at the snap "
                               "(thresholds not yet tuned against charted labels)", value=g))

    motion_events = [n for f, n in play.events if f <= snap and n in ("man_in_motion", "shift")]
    # Measure 0.2 s before the snap: by rule only the man in motion may be moving then,
    # while at the snap frame itself everyone is starting to move.
    pre = max(snap - 2, play.window[0])
    movers = []
    for i in play.players("offense"):
        e = play.entities[i]
        if e.group in ("OL", "QB"):
            continue
        sp, d = play.s[pre, i], play.dir[pre, i]
        if not np.isnan(sp) and sp >= config.MOTION_MIN_SPEED:
            lateral = abs(sp * np.cos(np.radians(d))) if not np.isnan(d) else 0.0
            movers.append((sp, lateral, i))
    if movers:
        sp, lateral, i = max(movers)
        e = play.entities[i]
        kind = "Jet motion" if lateral >= config.JET_MIN_SPEED else "Motion"
        offense.append(Callout("motion", f"{kind}: #{e.jersey}" if e.jersey is not None else kind,
                               DERIVED, detail=f"{e.name} moving {sp * 2.045:.0f} mph just before the snap",
                               source="Speed and direction 0.2 s before the snap", value=kind))
    elif motion_events:
        name = "Shift" if "shift" in motion_events and "man_in_motion" not in motion_events else "Motion"
        offense.append(Callout("motion", name, TRACKED, source="Event tagged in the tracking data",
                               value=name))
    charted_motion = _charted(play, "motion")
    play.derived["motionCompare"] = {
        "derived": bool(movers) or bool(motion_events),
        "charted": None if charted_motion is None else bool(_flag(charted_motion["value"])),
    }

    def_groups = Counter(play.entities[i].group for i in play.players("defense"))
    db, lb, dl = def_groups["DB"], def_groups["LB"], def_groups["DL"]
    package = PACKAGES.get(db, "Heavy" if db < 4 else "Prevent")
    defense.append(Callout("package", package, DERIVED, detail=f"{dl} DL, {lb} LB, {db} DB",
                           source="Roster positions of the 11 on the field", value=db))

    box = _charted(play, "box") or _charted(play, "ftn_box")
    if box:
        defense.append(Callout("box", f"{int(box['value'])} in the box", CHARTED,
                               source=box["source"], value=int(box["value"])))
    else:
        defense.append(Callout("box", "Box not charted", CHARTED, missing=True))

    is_pass = (play.official or {}).get("play_type") == "pass"
    rushers = _charted(play, "rushers") or _charted(play, "ftn_rushers")
    if rushers:
        blitz = _charted(play, "blitzers")
        label = f"{int(rushers['value'])} rushers"
        if blitz and _num(blitz["value"]):
            label += f", {int(blitz['value'])} blitzing"
        defense.append(Callout("pressure", label, CHARTED, source=rushers["source"],
                               value=int(rushers["value"])))
    elif is_pass:
        defense.append(Callout("pressure", "Rushers not charted", CHARTED, missing=True))

    cov, mz = _charted(play, "coverage"), _charted(play, "man_zone")
    if cov or mz:
        parts = []
        if cov:
            parts.append(str(cov["value"]).replace("_", " ").replace("COVER", "Cover").title()
                         .replace("Cover-", "Cover "))
        if mz:
            parts.append(str(mz["value"]).replace("_COVERAGE", "").replace("_", " ").lower())
        defense.append(Callout("coverage", " · ".join(parts), CHARTED,
                               source=(cov or mz)["source"], value=parts[0]))
    else:
        defense.append(Callout("coverage", "Coverage not charted", CHARTED, missing=True))

    for key, label in (("play_action", "Play action"), ("rpo", "RPO"), ("screen", "Screen"),
                       ("trick_play", "Trick play")):
        c = _charted(play, key)
        if c and _flag(c["value"]):
            after.append(Callout(key, label, CHARTED, source=c["source"], value=True))
    for name, label in (("play_action", "Play action"), ("pass_shovel", "Shovel pass"),
                        ("run_pass_option", "RPO")):
        if play.frame_of(name) is not None and not any(c.label == label for c in after):
            after.append(Callout(name, label, TRACKED, source="Event tagged in the tracking data",
                                 value=True))
    return {"offense": offense, "defense": defense, "afterSnap": after}


# ----------------------------------------------------------------------------
# Situation, clock and stats
# ----------------------------------------------------------------------------

def situation(play: Play, kf: dict) -> dict:
    m, o = play.meta, play.official or {}
    to_goal = los_to_goal(m)
    los_official = None if to_goal is None else config.GOAL_LINE_RIGHT - to_goal
    # The ball's spot: its median position over the last second before the snap
    # (or kick). At the snap frame itself the ball is already moving.
    ref_frame = kf["snap"] if kf["snap"] is not None else play.frame_of(*KICK_EVENTS)
    ball_x = np.nan
    if ref_frame is not None:
        lo = max(play.window[0], ref_frame - config.FRAME_RATE)
        spots = play.x[lo:ref_frame, 0] if ref_frame > lo else play.x[ref_frame:ref_frame + 1, 0]
        if not np.all(np.isnan(spots)):
            ball_x = float(np.nanmedian(spots))
    if not np.isnan(ball_x) and (los_official is None or abs(ball_x - los_official) <= 3.0):
        los_x, los_source = float(round(ball_x, 2)), TRACKED
    else:
        los_x, los_source = los_official, OFFICIAL
    if los_official is not None and not np.isnan(ball_x) and abs(ball_x - los_official) > 1.5:
        play.notes.append(f"Ball sensor at the snap is {abs(ball_x - los_official):.1f} yds "
                          "from the official spot")
    play.derived["losOfficialX"] = los_official if los_official is not None else los_x
    st = m.get("special_teams")
    ytg = _num(o.get("ydstogo")) if o.get("ydstogo") is not None else m.get("yards_to_go")
    down = _num(o.get("down")) if o.get("down") is not None else m.get("down")
    goal_to_go = bool(_flag(o.get("goal_to_go"))) or (to_goal is not None and ytg is not None
                                                       and to_goal <= ytg)
    ltg = None
    if not st and ytg and los_x is not None and down:
        ltg = config.GOAL_LINE_RIGHT if goal_to_go else min(los_x + ytg, config.GOAL_LINE_RIGHT)
    side, number = m.get("yardline_side"), m.get("yardline_number")
    yardline = "50" if number == 50 else (f"{side} {number}" if side and number is not None else None)
    quarter = _num(o.get("qtr")) or m.get("quarter")
    clock = _num(o.get("quarter_seconds_remaining"))
    clock = m.get("clock_seconds") if clock is None else clock
    return {
        "quarter": int(quarter) if quarter else None,
        "clockSeconds": int(clock) if clock is not None else None,
        "down": int(down) if down and not st else None,
        "yardsToGo": int(ytg) if ytg and not st else None,
        "goalToGo": goal_to_go if not st else False,
        "possession": m.get("possession"),
        "offense": play.offense_team,
        "yardline": yardline,
        "losX": los_x,
        "losSource": los_source,
        "lineToGainX": ltg,
        "scoreBefore": m.get("score_before"),
    }


def clock(play: Play, kf: dict, sit: dict) -> dict:
    st = play.meta.get("special_teams")
    a = play.window[0]
    start = None
    if st == "kickoff":
        start = kf["received"]
    elif st != "extra_point":
        start = kf["snap"]
    return {"startFrame": None if start is None else start - a,
            "secondsAtStart": sit.get("clockSeconds")}


def stats(play: Play, kf: dict) -> dict:
    a, b = play.window
    s = kf["snap"] if kf["snap"] is not None else (kf["kick"] or a)
    w = kf["whistle"] if kf["whistle"] is not None else b
    idx = play.players()
    sp = play.s[s:w + 1, idx]
    out = {"duration": round((b - a + 1) / config.FRAME_RATE, 1)}
    if sp.size and not np.all(np.isnan(sp)):
        f, j = np.unravel_index(np.nanargmax(sp), sp.shape)
        e = play.entities[idx[j]]
        out["topSpeedMph"] = round(float(sp[f, j]) * 3600 / 1760, 1)
        out["topSpeedName"] = e.name
    t, arr = kf["throw"], kf["arrival"] or kf["outcome"]
    if t is not None and arr is not None:
        d = np.hypot(play.x[arr, 0] - play.x[t, 0], play.y[arr, 0] - play.y[t, 0])
        if not np.isnan(d):
            out["airYards"] = round(float(d), 1)
            out["airDownfield"] = round(float(play.x[arr, 0] - play.x[t, 0]), 1)
    return out


def derive(play: Play) -> None:
    kf = key_frames(play)
    play.derived["keyFrames"] = kf
    sit = situation(play, kf)
    identify_carrier(play, kf)
    play.derived["situation"] = sit
    play.derived["clock"] = clock(play, kf, sit)
    play.derived["ball"] = ball_segments(play, kf)
    play.callouts = build_callouts(play, kf)
    play.derived["stats"] = stats(play, kf)
