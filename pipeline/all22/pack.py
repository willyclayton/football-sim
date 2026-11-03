"""Stage 6: one file per play (format spec: docs/play-format.md).

    "A22P" | u16 version | u16 reserved | u32 header length | header JSON
           | u32 frames length | frames (raw DEFLATE of frame-major records)

Each record is 12 bytes, little-endian, in the source's own precision, so
packing is lossless: x, y as int16 hundredths of a yard; speed as uint16
hundredths of a yd/s; direction and facing as uint16 hundredths of a degree;
then uint16 flags. Missing values use the sentinels below.
"""

from __future__ import annotations

import json
import math
import struct
import zlib
from pathlib import Path

import numpy as np

from . import __version__, config
from .model import (FLAG_MISSING, FLAG_NO_DIR, FLAG_NO_ORIENTATION, FLAG_NO_SPEED,
                    CheckResult, Play)
from .official import result_text, play_type

MAGIC = b"A22P"
VERSION = 1
RECORD = np.dtype([("x", "<i2"), ("y", "<i2"), ("s", "<u2"), ("dir", "<u2"), ("o", "<u2"),
                   ("flags", "<u2")])
XY_MISSING = -32768
U16_MISSING = 0xFFFF

EVENT_LABELS = {
    "line_set": "Line set", "man_in_motion": "Motion", "shift": "Shift",
    "ball_snap": "Snap", "snap_direct": "Direct snap", "autoevent_ballsnap": "Snap",
    "handoff": "Handoff", "play_action": "Play action", "run": "Run",
    "pass_forward": "Throw", "pass_shovel": "Shovel", "autoevent_passforward": "Throw",
    "pass_arrived": "Arrival", "pass_outcome_caught": "Catch",
    "pass_outcome_incomplete": "Incomplete", "pass_outcome_interception": "Interception",
    "pass_outcome_touchdown": "Touchdown catch", "pass_tipped": "Tipped",
    "first_contact": "First contact", "tackle": "Tackle", "out_of_bounds": "Out of bounds",
    "touchdown": "Touchdown", "qb_sack": "Sack", "qb_strip_sack": "Strip sack",
    "fumble": "Fumble", "lateral": "Lateral", "kickoff": "Kick", "onside_kick": "Onside kick",
    "punt": "Punt", "kick_received": "Catch", "punt_received": "Catch", "fair_catch": "Fair catch",
    "kickoff_land": "Ball lands", "punt_land": "Ball lands", "touchback": "Touchback",
    "field_goal_attempt": "Kick", "field_goal": "Good", "field_goal_missed": "No good",
    "extra_point_attempt": "Kick", "extra_point": "Good", "qb_kneel": "Kneel",
}
MARKER_EVENTS = {
    "ball_snap", "snap_direct", "autoevent_ballsnap", "handoff", "pass_forward", "pass_shovel",
    "pass_outcome_caught", "pass_outcome_incomplete", "pass_outcome_interception",
    "pass_outcome_touchdown", "first_contact", "tackle", "out_of_bounds", "touchdown", "qb_sack",
    "fumble", "kickoff", "punt", "kick_received", "punt_received", "fair_catch", "touchback",
    "field_goal_attempt", "extra_point_attempt",
}
HAPTIC_EVENTS = {"pass_outcome_caught", "pass_outcome_touchdown", "pass_outcome_interception",
                 "kick_received", "punt_received", "tackle"}


def jsonable(v):
    """Plain JSON values only: numpy scalars unwrapped, NaN and inf become null."""
    if isinstance(v, dict):
        return {str(k): jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [jsonable(x) for x in v]
    if isinstance(v, np.generic):
        v = v.item()
    if isinstance(v, float):
        return None if (math.isnan(v) or math.isinf(v)) else round(v, 4)
    return v


def _quantize(a: np.ndarray, scale: float, missing: int, lo: int, hi: int) -> np.ndarray:
    q = np.round(a * scale)
    q = np.where(np.isnan(q), missing, np.clip(q, lo, hi))
    return q.astype(np.int64)


def records(play: Play) -> np.ndarray:
    a, b = play.window
    sl = slice(a, b + 1)
    rec = np.zeros(play.x[sl].shape, dtype=RECORD)
    rec["x"] = _quantize(play.x[sl], 100, XY_MISSING, -32767, 32767)
    rec["y"] = _quantize(play.y[sl], 100, XY_MISSING, -32767, 32767)
    rec["s"] = _quantize(play.s[sl], 100, U16_MISSING, 0, 65534)
    rec["dir"] = _quantize(play.dir[sl] % 360.0, 100, U16_MISSING, 0, 35999)
    rec["o"] = _quantize(play.o[sl] % 360.0, 100, U16_MISSING, 0, 35999)
    flags = play.flags[sl].copy()
    flags |= np.where(np.isnan(play.x[sl]) | np.isnan(play.y[sl]), FLAG_MISSING, 0).astype(np.uint16)
    flags |= np.where(np.isnan(play.s[sl]), FLAG_NO_SPEED, 0).astype(np.uint16)
    flags |= np.where(np.isnan(play.dir[sl]), FLAG_NO_DIR, 0).astype(np.uint16)
    flags |= np.where(np.isnan(play.o[sl]), FLAG_NO_ORIENTATION, 0).astype(np.uint16)
    rec["flags"] = flags
    return rec


def header(play: Play, team_info) -> dict:
    a, b = play.window
    o = play.official or {}
    d = play.derived
    g = play.game

    def rel(f):
        return None if f is None or not (a <= f <= b) else f - a

    events = [{"frame": f - a, "name": n, "label": EVENT_LABELS.get(n, n.replace("_", " ").capitalize()),
               "marker": n in MARKER_EVENTS, "haptic": n in HAPTIC_EVENTS}
              for f, n in play.events if a <= f <= b]
    kf = {k: rel(v) for k, v in d["keyFrames"].items()}
    kf["start"], kf["end"] = 0, b - a
    hard = [c.to_json() for c in play.checks if c.kind == "hard"]
    soft = [c.to_json() for c in play.checks if c.kind == "soft"]
    stats = d.get("stats", {})
    return jsonable({
        "format": "all22-play",
        "version": VERSION,
        "id": play.key,
        "synthetic": bool(play.meta.get("synthetic", False)),
        "edition": {"id": play.edition, "name": play.meta.get("edition_name")},
        "game": {
            "id": g["id"], "season": g["season"], "week": g["week"], "date": g.get("date"),
            "home": team_info(g["home"], g.get("home_name")),
            "away": team_info(g["away"], g.get("away_name")),
        },
        "situation": d["situation"],
        "outcome": {
            "description": play.meta.get("description") or o.get("desc"),
            "type": play_type(o, play.meta.get("special_teams")),
            "result": result_text(o) if o else None,
            "yards": o.get("yards_gained"),
            "touchdown": bool(o.get("touchdown")) if o.get("touchdown") is not None else None,
            "scoreAfter": play.meta.get("score_after"),
            "epa": o.get("epa"),
            "wpa": o.get("wpa"),
            "winProbability": o.get("wp"),
        },
        "frames": {
            "count": b - a + 1, "rate": config.FRAME_RATE, "encoding": "deflate",
            "recordSize": RECORD.itemsize, "sourceStartFrame": int(play.source_frames[a]),
            "orientation": bool(not np.all(np.isnan(play.o[a:b + 1]))),
        },
        "entities": [e.to_json() for e in play.entities],
        "events": events,
        "keyFrames": kf,
        "clock": d["clock"],
        "ball": {"segments": d["ball"]},
        "carrier": d.get("carrier"),
        "callouts": {k: [c.to_json() for c in v] for k, v in play.callouts.items()},
        "checks": {"status": play.status, "hard": hard, "soft": soft, "notes": play.notes},
        "review": play.review,
        "stats": stats,
        "provenance": {
            "pipelineVersion": __version__,
            "sources": play.sources,
            "flipped": play.flipped,
            "direction": d.get("directionMethod"),
        },
    })


def encode(head: dict, rec: np.ndarray) -> bytes:
    hb = json.dumps(head, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    comp = zlib.compressobj(9, zlib.DEFLATED, -15)  # raw DEFLATE, RFC 1951
    fb = comp.compress(np.ascontiguousarray(rec).tobytes()) + comp.flush()
    return (MAGIC + struct.pack("<HHI", VERSION, 0, len(hb)) + hb
            + struct.pack("<I", len(fb)) + fb)


def decode(data: bytes) -> tuple[dict, np.ndarray]:
    if data[:4] != MAGIC:
        raise ValueError("not an all22 play file")
    version, _, hlen = struct.unpack_from("<HHI", data, 4)
    if version != VERSION:
        raise ValueError(f"unsupported version {version}")
    head = json.loads(data[12:12 + hlen].decode("utf-8"))
    (flen,) = struct.unpack_from("<I", data, 12 + hlen)
    raw = data[16 + hlen:16 + hlen + flen]
    if head["frames"]["encoding"] == "deflate":
        raw = zlib.decompress(raw, -15)
    rec = np.frombuffer(raw, dtype=RECORD)
    n_entities = len(head["entities"])
    return head, rec.reshape(head["frames"]["count"], n_entities)


def read_play(path: Path) -> tuple[dict, np.ndarray]:
    return decode(Path(path).read_bytes())


def source_match(play: Play, data: bytes) -> CheckResult:
    """Decode the packed file, undo the flip, and compare every unfilled record
    with the raw source values. Proves packing and normalizing changed nothing."""
    _, rec = decode(data)
    a, b = play.window
    raw = play.raw
    sl = slice(a, b + 1)
    filled = (rec["flags"] & 2) != 0
    mismatches = 0
    for name, scale, missing in (("x", 100, XY_MISSING), ("y", 100, XY_MISSING),
                                 ("s", 100, U16_MISSING), ("dir", 100, U16_MISSING),
                                 ("o", 100, U16_MISSING)):
        got = rec[name].astype(float)
        got = np.where(rec[name] == missing, np.nan, got / scale)
        if play.flipped and name in ("x", "y"):
            got = (config.FIELD_LENGTH if name == "x" else config.FIELD_WIDTH) - got
        if play.flipped and name in ("dir", "o"):
            got = (got + 180.0) % 360.0
        want = raw[name][sl]
        if name in ("dir", "o"):
            want = want % 360.0
        both_nan = np.isnan(got) & np.isnan(want)
        close = np.abs(np.round(got * 100) - np.round(want * 100)) == 0
        if name in ("dir", "o"):  # 0 and 360 are the same angle
            close |= np.abs(np.round(got * 100) - np.round(want * 100)) == 36000
        ok = both_nan | close | filled
        mismatches += int((~ok).sum())
    n = (b - a + 1) * len(play.entities)
    if mismatches:
        return CheckResult("source_match", "Matches the source file", "hard", "fail",
                           f"{mismatches} values differ from the source after unpacking")
    return CheckResult("source_match", "Matches the source file", "hard", "pass",
                       f"All {n} records match the source exactly after unpacking and un-flipping")


def write(play: Play, out_dir: Path, team_info) -> tuple[Path | None, dict]:
    """Pack, verify against the source, and write.

    Returns (path, header); path is None when the play is dropped."""
    rec = records(play)
    probe = encode(header(play, team_info), rec)
    play.checks.append(source_match(play, probe))
    head = header(play, team_info)
    if play.status == "dropped":
        return None, head
    path = out_dir / f"{play.key}.a22"
    path.write_bytes(encode(head, rec))
    return path, head
