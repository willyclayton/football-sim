"""Pipeline tests on synthetic, made-up plays (no NFL data needed; these run in CI).

Each fault test injects one problem into an otherwise clean play and checks
that exactly the right check catches it.
"""

from __future__ import annotations

import json
import math
import sqlite3

import numpy as np
import pytest

from all22 import catalog, config, fixtures, pack, reviews
from all22.derive import parse_personnel, short_name
from all22.fixtures import CATCH, SNAP, TACKLE, THROW, build_synthetic
from all22.model import FLAG_FILLED
from all22.normalize import flip


def result(play, check_id):
    c = play.check(check_id)
    return None if c is None else c.result


def labels(play, side):
    return [c.label for c in play.callouts[side]]


# --- clean play --------------------------------------------------------------

def test_clean_play_ships():
    p = build_synthetic()
    assert p.status == "ship"
    assert p.flipped, "the synthetic offense attacks -x, so it must be flipped"
    assert result(p, "positions_present") == "fixed"  # its two-frame sensor gap
    for cid in ("joined", "frames_contiguous", "full_roster", "snap_present",
                "events_in_order", "plausible_speed", "yards_agree", "ball_sensor_agrees"):
        assert result(p, cid) == "pass", cid


def test_gap_is_filled_and_flagged():
    p = build_synthetic()
    e = next(i for i, ent in enumerate(p.entities) if ent.key == fixtures.GAP[0])
    for f in (fixtures.GAP[1] - 1, fixtures.GAP[2] - 1):
        assert p.flags[f, e] & FLAG_FILLED
        assert not math.isnan(p.x[f, e])
    assert not p.flags[fixtures.GAP[1] - 2, e] & FLAG_FILLED


def test_flip_is_exact_and_reversible():
    p = build_synthetic()
    x, y, d = p.x.copy(), p.y.copy(), p.dir.copy()
    flip(p)
    flip(p)
    assert np.allclose(x, p.x, equal_nan=True)
    assert np.allclose(y, p.y, equal_nan=True)
    assert np.allclose(d % 360, p.dir % 360, equal_nan=True)


def test_offense_attacks_plus_x_after_normalizing():
    p = build_synthetic()
    snap = p.derived["keyFrames"]["snap"]
    off = np.nanmean(p.x[snap, p.players("offense")])
    dfn = np.nanmean(p.x[snap, p.players("defense")])
    assert off < dfn


# --- hard checks drop the play -------------------------------------------------

def _drop_player(inp, official):
    inp.tracking = inp.tracking[inp.tracking["key"] != "90010"]


def _long_gap(inp, official):
    t = inp.tracking
    m = (t["key"] == "90018") & t["frame"].between(18, 26)
    t.loc[m, ["x", "y"]] = np.nan


def _missing_frame(inp, official):
    inp.tracking = inp.tracking[inp.tracking["frame"] != 20]


def _too_fast(inp, official):
    t = inp.tracking
    t.loc[(t["key"] == "90003") & (t["frame"] == 30), "s"] = 12.5


def _out_of_order(inp, official):
    t = inp.tracking
    t.loc[t["frame"] == THROW, "event"] = None
    t.loc[t["frame"] == CATCH + 1, "event"] = "pass_forward"


def _no_snap(inp, official):
    t = inp.tracking
    t.loc[t["event"] == "ball_snap", "event"] = None


@pytest.mark.parametrize("mutate,check_id", [
    (_drop_player, "full_roster"),
    (_long_gap, "positions_present"),
    (_missing_frame, "frames_contiguous"),
    (_too_fast, "plausible_speed"),
    (_out_of_order, "events_in_order"),
    (_no_snap, "snap_present"),
])
def test_hard_check_drops_play(mutate, check_id):
    p = build_synthetic(mutate)
    assert result(p, check_id) == "fail"
    assert p.status == "dropped"


def test_unjoined_play_is_dropped():
    p = build_synthetic(official_count=0)
    assert result(p, "joined") == "fail"
    assert p.status == "dropped"


def test_dropout_after_whistle_is_trimmed_not_dropped():
    def late_dropout(inp, official):
        t = inp.tracking
        t.loc[(t["key"] == "90012") & (t["frame"] >= TACKLE + 1), ["x", "y"]] = np.nan

    p = build_synthetic(late_dropout)
    assert result(p, "positions_present") == "fixed"
    assert p.window[1] == TACKLE - 1  # the frame before the dropout (0-based index of frame 38)
    assert p.status == "ship"


def test_dropout_before_whistle_is_not_trimmed():
    def dropout(inp, official):
        t = inp.tracking
        t.loc[(t["key"] == "90012") & (t["frame"] >= TACKLE - 8), ["x", "y"]] = np.nan

    p = build_synthetic(dropout)
    assert result(p, "positions_present") == "fail"


# --- soft checks flag the play ----------------------------------------------

def test_yardage_disagreement_flags_then_review_ships():
    def wrong_yards(inp, official):
        official["yards_gained"] = 25.0

    p = build_synthetic(wrong_yards)
    assert result(p, "yards_agree") == "fail"
    assert p.status == "flagged"
    p.review = {"status": "reviewed", "date": "2026-11-03", "note": "checked"}
    assert p.status == "ship"
    p.review = {"status": "dropped", "date": "2026-11-03", "note": "bad"}
    assert p.status == "dropped"


def test_stray_ball_sensor_flags():
    def stray(inp, official):
        t = inp.tracking
        t.loc[(t["key"] == "ball") & (t["frame"] >= TACKLE - 1), "y"] = 5.0

    p = build_synthetic(stray)
    assert result(p, "ball_sensor_agrees") == "fail"
    assert p.status == "flagged"


# --- derived calls -----------------------------------------------------------

def test_callouts():
    p = build_synthetic()
    assert labels(p, "offense") == ["11 personnel", "Shotgun", "3x1 trips right"]
    assert labels(p, "defense") == ["Nickel", "6 in the box", "Rushers not charted",
                                    "Coverage not charted"]
    personnel = p.callouts["offense"][0]
    assert personnel.badge == "derived" and personnel.detail.startswith("1 RB, 1 TE, 3 WR")


def test_ball_rides_with_qb_then_receiver():
    p = build_synthetic()
    segs = p.derived["ball"]
    held = [s for s in segs if s["mode"] == "held"]
    assert [p.entities[s["holder"]].jersey for s in held] == [7, 11]
    throw = next(s for s in segs if s["mode"] == "flight" and s["from"] == THROW - 1)
    assert throw["to"] == CATCH - 1
    assert throw["apex"] == pytest.approx(config.GRAVITY_YD * 0.9 ** 2 / 8, abs=1e-3)
    # Segments tile the window with no gaps or overlaps.
    assert segs[0]["from"] == 0 and segs[-1]["to"] == p.window[1] - p.window[0]
    assert all(a["to"] + 1 == b["from"] for a, b in zip(segs, segs[1:]))


def test_clock_starts_at_snap():
    p = build_synthetic()
    assert p.derived["clock"] == {"startFrame": SNAP - 1, "secondsAtStart": 450}


def test_carrier_is_the_official_receiver():
    p = build_synthetic()
    assert p.entities[p.derived["carrier"]].jersey == 11
    assert p.derived["carrierSource"] == "official jersey"


@pytest.mark.parametrize("text,expected", [
    ("1 RB, 2 TE, 2 WR", {"RB": 1, "TE": 2, "WR": 2}),
    ("6 OL, 2 RB, 2 TE, 0 WR", {"OL": 6, "RB": 2, "TE": 2, "WR": 0}),
    ("3 DL, 2 LB, 6 DB", {"DL": 3, "LB": 2, "DB": 6}),
    (None, None),
])
def test_parse_personnel(text, expected):
    assert parse_personnel(text) == expected


@pytest.mark.parametrize("full,short", [
    ("De'Anthony Thomas", "d.thomas"),
    ("Odell Beckham Jr.", "o.beckham"),
    ("Laurent Duvernay-Tardif", "l.duvernay-tardif"),
])
def test_short_name(full, short):
    assert short_name(full) == short


# --- pack, catalog, reviews ----------------------------------------------------

def test_pack_round_trip_is_lossless(tmp_path):
    p = build_synthetic()
    path, head = pack.write(p, tmp_path, fixtures._team)
    assert result(p, "source_match") == "pass"
    h, rec = pack.read_play(path)
    assert h == head
    a, b = p.window
    assert rec.shape == (b - a + 1, len(p.entities))
    assert np.array_equal(rec["x"], np.round(p.x[a:b + 1] * 100).astype(np.int16))
    assert np.array_equal(rec["y"], np.round(p.y[a:b + 1] * 100).astype(np.int16))
    assert (rec["o"] == pack.U16_MISSING).all()  # no facing in this data
    assert (rec["dir"][:, 0] == pack.U16_MISSING).all()  # nor a ball direction


def test_header_is_strict_json(tmp_path):
    p = build_synthetic()
    path, _ = pack.write(p, tmp_path, fixtures._team)
    raw = path.read_bytes()
    hlen = int.from_bytes(raw[8:12], "little")

    def reject(token):
        raise ValueError(token)

    json.loads(raw[12:12 + hlen], parse_constant=reject)


def test_tampered_record_fails_source_match(tmp_path):
    p = build_synthetic()
    data = pack.encode(pack.header(p, fixtures._team), pack.records(p))
    assert pack.source_match(p, data).result == "pass"
    p.x[15, 5] += 0.5  # what a pipeline bug would look like
    data = pack.encode(pack.header(p, fixtures._team), pack.records(p))
    assert pack.source_match(p, data).result == "fail"


def test_catalog_row(tmp_path):
    p = build_synthetic()
    _, head = pack.write(p, tmp_path, fixtures._team)
    db = tmp_path / "catalog.sqlite"
    catalog.write(db, [catalog.row(head, "plays/x.a22")], {"edition": "synthetic"})
    con = sqlite3.connect(db)
    row = con.execute("SELECT offense, defense, personnel, receiver_set, package, status, yards "
                      "FROM plays").fetchone()
    con.close()
    assert row == ("AWY", "HOM", "11 personnel", "3x1 trips right", "Nickel", "ship", 17)


def test_reviews_round_trip(tmp_path):
    ledger = tmp_path / "reviews.csv"
    reviews.record("2000010100-1", "reviewed", "matches broadcast", path=ledger)
    entry = reviews.load(ledger)["2000010100-1"]
    assert entry["status"] == "reviewed" and entry["note"] == "matches broadcast"
    with pytest.raises(SystemExit):
        reviews.record("2000010100-1", "maybe", path=ledger)


def test_swift_fixtures_are_up_to_date():
    assert fixtures.main(check=True) == 0
