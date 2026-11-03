"""The video-review ledger (reviews/reviews.csv, committed).

A play flagged by a soft check ships only once you have compared it with the
broadcast and marked it reviewed. Marking it dropped keeps it out for good.
The ledger holds only play ids, your verdict, the date and your note.
"""

from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

from . import config

FIELDS = ["play", "status", "date", "note"]
STATUSES = ("reviewed", "dropped")


def load(path: Path = config.REVIEWS_FILE) -> dict[str, dict]:
    if not path.exists():
        return {}
    with open(path, newline="") as f:
        return {r["play"]: {"status": r["status"], "date": r["date"] or None, "note": r["note"] or None}
                for r in csv.DictReader(f) if r.get("play")}


def record(play_key: str, status: str, note: str = "", path: Path = config.REVIEWS_FILE) -> dict:
    if status not in STATUSES:
        raise SystemExit(f"status must be one of {STATUSES}")
    entries = load(path)
    entries[play_key] = {"status": status, "date": dt.date.today().isoformat(), "note": note or None}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for key in sorted(entries):
            e = entries[key]
            w.writerow({"play": key, "status": e["status"], "date": e["date"] or "",
                        "note": e["note"] or ""})
    return entries[play_key]
