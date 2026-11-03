"""Per-play validation report: build/report/validation.md and validation.json."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from . import config

HARD = [
    ("joined", "Joined to official play-by-play", "Every tracked play matches one official play"),
    ("frames_contiguous", "Frames contiguous", "No gaps in the 10-per-second frame count"),
    ("full_roster", "Full roster every frame", "11 offense, 11 defense and the ball"),
    ("positions_present", "Positions present",
     "No blank coordinates; gaps up to 0.5 s filled, dropouts after the whistle trimmed"),
    ("snap_present", "Snap event present", "Scrimmage plays have a tagged snap; kickoffs a kick"),
    ("events_in_order", "Events in order", "Snap before throw before arrival"),
    ("plausible_speed", "Plausible speed", f"No player over {config.MAX_PLAYER_SPEED:g} yd/s"),
    ("source_match", "Matches the source file",
     "After packing, unpacking and un-flipping, every value equals the source"),
]
SOFT = [
    ("yards_agree", "Yards agree",
     f"Carrier's advance to the whistle within {config.YARDS_TOLERANCE:g} yds of official yards"),
    ("ball_sensor_agrees", "Ball sensor agrees",
     f"Ball within {config.BALL_TO_CARRIER_MAX:g} yds of its carrier at the whistle"),
]
SPEC_SAMPLE = {  # the spec's own run on the same 177 plays, for comparison
    "joined": "177 of 177", "frames_contiguous": "177 of 177", "full_roster": "176 of 177",
    "positions_present": "172 of 177", "snap_present": "163 of 177",
    "events_in_order": "177 of 177", "plausible_speed": "177 of 177; fastest 10.6 yd/s",
    "source_match": "not run",
    "yards_agree": "36 of 41; 28 within 1 yd; worst 3.1", "ball_sensor_agrees": "39 of 41",
}
WHAT_TO_CHECK = {
    "yards_agree": "Compare the carrier's end spot on video with the official yardage",
    "ball_sensor_agrees": "Check the ball's path on video; the app shows it in the carrier's hands",
}


def _clock(sec) -> str:
    if sec is None:
        return ""
    return f"{int(sec) // 60}:{int(sec) % 60:02d}"


def _sit(s: dict) -> str:
    q = s.get("quarter")
    parts = [f"Q{q}" if q else "", _clock(s.get("clock"))]
    if s.get("down"):
        parts.append(f"{s['down']}&{s.get('ytg')}")
    return " ".join(p for p in parts if p)


def write(summaries: list[dict], meta: dict, out_dir: Path = config.REPORT_OUT) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "validation.json").write_text(json.dumps({"meta": meta, "plays": summaries},
                                                        indent=1, default=str))
    n = len(summaries)
    status = Counter(s["status"] for s in summaries)
    reviewed = sum(1 for s in summaries if s["status"] == "ship" and s["review"] == "reviewed")
    lines = [
        f"# Validation report: {meta['edition_name']}",
        "",
        f"Built {meta['built']} by pipeline {meta['pipeline']}. "
        f"Generated from the raw files; regenerate with `make bundle`.",
        "",
        "## Summary",
        "",
        "| Plays tracked | Ship | of which video-reviewed | Awaiting video review | Dropped |",
        "| --- | --- | --- | --- | --- |",
        f"| {n} | {status['ship']} | {reviewed} | {status['flagged']} | {status['dropped']} |",
        "",
        "## Hard checks (a failure drops the play)",
        "",
        "| Check | Rule | Pass | Repaired | Fail | Spec's run on the sample game |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    sample = meta["edition"] == "bdb2019-sample"
    for cid, name, rule in HARD:
        c = Counter(r for s in summaries for (i, r, _) in s["checks"] if i == cid)
        spec = SPEC_SAMPLE.get(cid, "") if sample else ""
        lines.append(f"| {name} | {rule} | {c['pass']} | {c['fixed']} | {c['fail']} | {spec} |")
    lines += ["", "Repaired means the check passed after a recorded repair; the play's info "
              "screen says what was done.", "",
              "## Soft checks (a failure holds the play for video review)", "",
              "| Check | Rule | Pass | Flagged | Not applicable | Spec's run on the sample game |",
              "| --- | --- | --- | --- | --- | --- |"]
    for cid, name, rule in SOFT:
        c = Counter(r for s in summaries for (i, r, _) in s["checks"] if i == cid)
        spec = SPEC_SAMPLE.get(cid, "") if sample else ""
        lines.append(f"| {name} | {rule} | {c['pass']} | {c['fail']} | {c['n/a']} | {spec} |")
    gaps = sorted(s["yardsGap"] for s in summaries if s.get("yardsGap") is not None)
    if gaps:
        lines += ["", f"Yards: {len(gaps)} runs and catches checked; "
                  f"{sum(g <= 1 for g in gaps)} within 1 yd, "
                  f"{sum(g <= config.YARDS_TOLERANCE for g in gaps)} within "
                  f"{config.YARDS_TOLERANCE:g} yds; worst gaps "
                  + ", ".join(f"{g:.1f}" for g in gaps[-3:]) + " yds."]

    lines += ["", "## Derived calls vs charted labels", "",
              "Derived rules run on tracked positions and roster positions; charted labels "
              "are the edition's or nflverse's. Agreement is measured wherever both exist.", "",
              "| Call | Agree | Compared | Rate |", "| --- | --- | --- | --- |"]
    disagreements = []
    for key, name in (("personnel", "Offensive personnel"), ("package", "Defensive package (DB count)"),
                      ("receiver_set", "Receiver set"), ("motion", "Motion at the snap")):
        pairs = [(s["key"], s["agreement"][key]) for s in summaries
                 if s.get("agreement", {}).get(key) is not None]
        if not pairs:
            lines.append(f"| {name} | - | 0 | no charted label in this edition |")
            continue
        ok = sum(1 for _, (d, c) in pairs if d == c)
        lines.append(f"| {name} | {ok} | {len(pairs)} | {ok / len(pairs):.0%} |")
        disagreements += [f"- {k} {name}: derived {d!r}, charted {c!r}" for k, (d, c) in pairs if d != c]
    if disagreements:
        lines += ["", "Disagreements:", ""] + disagreements[:60]

    dirs = [s["passSide"] for s in summaries if s.get("passSide")]
    if dirs:
        ok = sum(1 for said, seen in dirs if said == seen)
        lines += ["", "## Orientation sanity check", "",
                  f"Passes the official description calls left or right: the ball arrived on "
                  f"that side in {ok} of {len(dirs)} ({ok / len(dirs):.0%}). A mirrored field "
                  "would score near zero."]

    flagged = [s for s in summaries if s["status"] == "flagged"]
    lines += ["", "## Awaiting video review", ""]
    if flagged:
        lines += ["Compare each with the broadcast, then record the verdict:",
                  "`make review PLAY=<id> VERDICT=reviewed NOTE=\"...\"` "
                  "(or `VERDICT=dropped`).", "",
                  "| Play | Situation | Description | Flagged by | What to check |",
                  "| --- | --- | --- | --- | --- |"]
        for s in flagged:
            failed = [(i, d) for (i, r, d) in s["checks"] if r == "fail"]
            lines.append(f"| {s['key']} | {_sit(s['situation'])} | {(s['description'] or '')[:90]} | "
                         + "; ".join(d for _, d in failed) + " | "
                         + "; ".join(WHAT_TO_CHECK.get(i, "") for i, _ in failed) + " |")
    else:
        lines.append("None.")

    dropped = [s for s in summaries if s["status"] == "dropped"]
    lines += ["", "## Dropped", ""]
    if dropped:
        lines += ["| Play | Situation | Description | Why |", "| --- | --- | --- | --- |"]
        for s in dropped:
            why = "; ".join(f"{i}: {d}" for (i, r, d) in s["checks"] if r == "fail")
            if s["review"] == "dropped":
                why = (why + "; " if why else "") + "dropped at video review"
            lines.append(f"| {s['key']} | {_sit(s['situation'])} | {(s['description'] or '')[:90]} | {why} |")
    else:
        lines.append("None.")

    repaired = [(s["key"], d) for s in summaries for (i, r, d) in s["checks"] if r == "fixed"]
    notes = [(s["key"], note) for s in summaries for note in s["notes"]]
    if repaired or notes:
        lines += ["", "## Repairs and notes", ""]
        lines += [f"- {k}: {d}" for k, d in repaired]
        lines += [f"- {k}: {note}" for k, note in notes]

    lines += ["", "## Inputs", "", "| File | SHA-256 |", "| --- | --- |"]
    lines += [f"| {f} | `{h}` |" for f, h in sorted(meta["sources"].items())]
    path = out_dir / "validation.md"
    path.write_text("\n".join(lines) + "\n")
    return path
