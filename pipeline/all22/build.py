"""Runs stages 2-8 for one edition: join, normalize, validate, derive, pack,
catalog, report, and copy the bundle into the app."""

from __future__ import annotations

import datetime as dt
import re
import shutil
from pathlib import Path

import numpy as np

from . import __version__, catalog, checks, config, editions, pack, report, reviews
from .derive import derive, parse_personnel
from .grid import build_play
from .model import Play
from .normalize import normalize
from .official import OfficialData
from .teams import team_info


def _agreement(play: Play) -> dict:
    """(derived, charted) pairs wherever a derived call has a charted counterpart."""
    out = {}
    if play.meta.get("special_teams"):
        return out
    meta_charted = play.meta.get("charted", {})

    def charted(key):
        return meta_charted.get(key) or play.labels.get(key)

    def callout(side, key):
        return next((c for c in play.callouts.get(side, []) if c.key == key), None)

    pc, ch = callout("offense", "personnel"), charted("personnel_offense")
    chp = parse_personnel(ch["value"]) if ch else None
    if pc and chp:
        out["personnel"] = (f"{pc.value['RB']}{pc.value['TE']}",
                            f"{chp.get('RB', 0)}{chp.get('TE', 0)}")
    pk, chd = callout("defense", "package"), charted("personnel_defense")
    chdp = parse_personnel(chd["value"]) if chd else None
    if pk and chdp:
        out["package"] = (pk.value, chdp.get("DB", 0))
    rs, ra = callout("offense", "receiver_set"), charted("receiver_alignment")
    if rs and ra:
        out["receiver_set"] = (rs.value, str(ra["value"]))
    mc = play.derived.get("motionCompare") or {}
    if mc.get("charted") is not None:
        out["motion"] = (mc["derived"], mc["charted"])
    return out


def _pass_side(play: Play):
    """('left' | 'right' said by the description, side the ball arrived on)."""
    desc = play.meta.get("description") or ""
    m = re.search(r"pass (?:short|deep) (left|right)", desc)
    kf = play.derived.get("keyFrames", {})
    t, arr = kf.get("throw"), kf.get("arrival")
    if not m or t is None or arr is None:
        return None
    snap = kf.get("snap") or play.window[0]
    dy = play.y[arr, 0] - np.nanmedian(play.y[max(play.window[0], snap - 10):snap + 1, 0])
    if np.isnan(dy) or abs(dy) < 2.0:
        return None
    return (m.group(1), "left" if dy > 0 else "right")


def summarize(play: Play, file_name) -> dict:
    sit = play.derived.get("situation") or {}
    m = play.meta
    return {
        "key": play.key,
        "file": file_name,
        "status": play.status,
        "review": play.review.get("status"),
        "description": m.get("description"),
        "situation": {"quarter": sit.get("quarter") or m.get("quarter"),
                      "clock": sit.get("clockSeconds") if sit else m.get("clock_seconds"),
                      "down": sit.get("down") if sit else m.get("down"),
                      "ytg": sit.get("yardsToGo") if sit else m.get("yards_to_go")},
        "checks": [(c.id, c.result, c.detail) for c in play.checks],
        "notes": list(play.notes),
        "agreement": _agreement(play) if play.callouts else {},
        "passSide": _pass_side(play) if play.derived.get("keyFrames") else None,
        "yardsGap": play.derived.get("yardsGap"),
        "ballGap": play.derived.get("ballGap"),
    }


def run(edition_id: str, review_queue: bool = True, copy_to_app: bool = True,
        limit: int | None = None, log=print) -> dict:
    ed = editions.get(edition_id)
    ed.check_files()
    log(f"Building {ed.name}")
    official = OfficialData(ed.nflverse_seasons)
    ledger = reviews.load()

    out_dir = config.PLAYS_OUT / edition_id
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    summaries, rows, sources = [], [], dict(official.sources)
    file_hashes: dict[str, str] = {}
    for i, inp in enumerate(ed.iter_plays()):
        if limit is not None and i >= limit:
            break
        inp.play["edition_name"] = ed.name
        file_hashes.update(inp.sources)
        play = build_play(inp)
        gid, pid = play.meta["game_id"], play.meta["play_id"]
        play.official, count = official.official(gid, pid)
        play.labels = official.labels(gid, pid)
        if play.key in ledger:
            play.review = dict(ledger[play.key])
        normalize(play)
        checks.run_hard(play, count)
        path = None
        if play.status != "dropped":
            derive(play)
            checks.run_soft(play)
            path, head = pack.write(play, out_dir, team_info)
            if path is not None and (play.status == "ship" or review_queue):
                rows.append(catalog.row(head, f"plays/{path.name}"))
        summaries.append(summarize(play, path.name if path else None))
        if (i + 1) % 500 == 0:
            log(f"  {i + 1} plays")

    for name, digest in file_hashes.items():
        sources[name] = digest
    meta = {"edition": edition_id, "edition_name": ed.name, "pipeline": __version__,
            "built": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "sources": sources}
    catalog_path = config.BUILD / "catalog" / f"{edition_id}.sqlite"
    catalog.write(catalog_path, rows, {"edition": edition_id, "edition_name": ed.name,
                                       "pipeline": __version__, "built": meta["built"],
                                       "plays": len(rows)})
    report_path = report.write(summaries, meta)

    shipped = sum(1 for s in summaries if s["status"] == "ship")
    flagged = sum(1 for s in summaries if s["status"] == "flagged")
    dropped = sum(1 for s in summaries if s["status"] == "dropped")
    log(f"  {len(summaries)} plays: {shipped} ship, {flagged} awaiting video review, {dropped} dropped")
    log(f"  report: {report_path.relative_to(config.ROOT)}")

    if copy_to_app:
        bundle(out_dir, catalog_path, rows, log=log)
    return {"plays": len(summaries), "ship": shipped, "flagged": flagged, "dropped": dropped,
            "bundled": len(rows), "report": str(report_path)}


def bundle(plays_dir: Path, catalog_path: Path, rows: list[dict], log=print) -> None:
    """Stage 8: copy the catalog and every cataloged play into app/PlayData."""
    dest = config.APP_PLAYDATA
    dest.mkdir(parents=True, exist_ok=True)
    for child in dest.iterdir():
        if child.name == "README.md":
            continue
        shutil.rmtree(child) if child.is_dir() else child.unlink()
    (dest / "plays").mkdir()
    for r in rows:
        shutil.copy2(plays_dir / Path(r["file"]).name, dest / r["file"])
    shutil.copy2(catalog_path, dest / "catalog.sqlite")
    size = sum(p.stat().st_size for p in dest.rglob("*") if p.is_file())
    log(f"  bundled {len(rows)} plays into {dest.relative_to(config.ROOT)} ({size / 1e6:.1f} MB)")
