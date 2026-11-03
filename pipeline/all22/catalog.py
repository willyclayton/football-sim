"""Stage 7: one SQLite file listing every bundled play with filter fields."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE plays (
    id TEXT PRIMARY KEY,
    file TEXT NOT NULL,
    edition TEXT NOT NULL,
    season INTEGER, week INTEGER, game_id TEXT, play_id INTEGER, game_date TEXT,
    home TEXT, away TEXT, offense TEXT, defense TEXT,
    quarter INTEGER, clock INTEGER, down INTEGER, yards_to_go INTEGER, yardline TEXT,
    home_score INTEGER, away_score INTEGER,
    play_type TEXT, result TEXT, yards INTEGER, touchdown INTEGER,
    description TEXT,
    epa REAL, wpa REAL,
    personnel TEXT, formation TEXT, receiver_set TEXT, package TEXT, coverage TEXT,
    top_speed_mph REAL, top_speed_name TEXT, air_yards REAL, duration REAL,
    status TEXT NOT NULL,
    flags TEXT,
    reviewed_on TEXT
);
CREATE INDEX plays_order ON plays (season, week, game_id, quarter, clock DESC, play_id);
CREATE INDEX plays_offense ON plays (offense);
"""

COLUMNS = ["id", "file", "edition", "season", "week", "game_id", "play_id", "game_date",
           "home", "away", "offense", "defense", "quarter", "clock", "down", "yards_to_go",
           "yardline", "home_score", "away_score", "play_type", "result", "yards", "touchdown",
           "description", "epa", "wpa", "personnel", "formation", "receiver_set", "package",
           "coverage", "top_speed_mph", "top_speed_name", "air_yards", "duration", "status",
           "flags", "reviewed_on"]


def _callout(head: dict, side: str, key: str):
    for c in head["callouts"].get(side, []):
        if c["key"] == key and not c.get("missing"):
            return c["label"]
    return None


def row(head: dict, file_name: str) -> dict:
    g, sit, out = head["game"], head["situation"], head["outcome"]
    offense_abbr = sit.get("possession")
    defense_abbr = g["away"]["abbr"] if offense_abbr == g["home"]["abbr"] else g["home"]["abbr"]
    score = sit.get("scoreBefore") or {}
    failed = [c["id"] for c in head["checks"]["soft"] if c["result"] == "fail"]
    yards = out.get("yards")
    return {
        "id": head["id"], "file": file_name, "edition": head["edition"]["id"],
        "season": g["season"], "week": g["week"], "game_id": g["id"],
        "play_id": int(head["id"].split("-")[-1]), "game_date": g.get("date"),
        "home": g["home"]["abbr"], "away": g["away"]["abbr"],
        "offense": offense_abbr, "defense": defense_abbr,
        "quarter": sit.get("quarter"), "clock": sit.get("clockSeconds"), "down": sit.get("down"),
        "yards_to_go": sit.get("yardsToGo"), "yardline": sit.get("yardline"),
        "home_score": score.get("home"), "away_score": score.get("away"),
        "play_type": out.get("type"), "result": out.get("result"),
        "yards": int(yards) if yards is not None else None,
        "touchdown": 1 if out.get("touchdown") else 0,
        "description": out.get("description"),
        "epa": out.get("epa"), "wpa": out.get("wpa"),
        "personnel": _callout(head, "offense", "personnel"),
        "formation": _callout(head, "offense", "formation"),
        "receiver_set": _callout(head, "offense", "receiver_set"),
        "package": _callout(head, "defense", "package"),
        "coverage": _callout(head, "defense", "coverage"),
        "top_speed_mph": head["stats"].get("topSpeedMph"),
        "top_speed_name": head["stats"].get("topSpeedName"),
        "air_yards": head["stats"].get("airYards"),
        "duration": head["stats"].get("duration"),
        "status": head["checks"]["status"],
        "flags": ",".join(failed) or None,
        "reviewed_on": head["review"].get("date"),
    }


def write(path: Path, rows: list[dict], meta: dict) -> None:
    if path.exists():
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    try:
        con.executescript(SCHEMA)
        con.executemany("INSERT INTO meta (key, value) VALUES (?, ?)",
                        [(k, str(v)) for k, v in sorted(meta.items())])
        placeholders = ",".join("?" for _ in COLUMNS)
        con.executemany(f"INSERT INTO plays ({','.join(COLUMNS)}) VALUES ({placeholders})",
                        [[r.get(c) for c in COLUMNS] for r in rows])
        con.commit()
    finally:
        con.close()
