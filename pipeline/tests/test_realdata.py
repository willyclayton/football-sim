"""End-to-end run on the real sample game. Skipped unless `make download` has run,
so CI (which never holds NFL data) skips it."""

from __future__ import annotations

import pytest

from all22 import build, config, pack

SAMPLE = config.RAW / "bdb2019_sample" / "tracking_gameId_2017090700.csv"
pytestmark = pytest.mark.skipif(not SAMPLE.exists(), reason="sample game not downloaded")


@pytest.fixture(scope="module")
def built():
    return build.run("bdb2019-sample", copy_to_app=False, log=lambda *a: None)


def test_counts(built):
    assert built["plays"] == 177
    assert built["dropped"] == 1  # play 3486: one player's sensor missing all play
    assert built["ship"] + built["flagged"] == 176


def test_play_938_matches_the_spec_example(built):
    head, rec = pack.read_play(config.PLAYS_OUT / "bdb2019-sample" / "2017090700-938.a22")
    off = [c["label"] for c in head["callouts"]["offense"]]
    dfn = [c["label"] for c in head["callouts"]["defense"]]
    assert off[:3] == ["12 personnel", "Shotgun", "2x2"]
    assert dfn[:3] == ["Dime", "6 in the box", "3 rushers"]
    assert head["situation"]["down"] == 3 and head["situation"]["yardsToGo"] == 7
    assert head["situation"]["clockSeconds"] == 190
    assert head["outcome"]["touchdown"] is True
    assert all(c["result"] == "pass" for c in head["checks"]["hard"])


def test_every_shipped_play_matches_its_source(built):
    import json
    report = json.loads((config.REPORT_OUT / "validation.json").read_text())
    for p in report["plays"]:
        if p["status"] != "dropped":
            match = [r for (i, r, _) in p["checks"] if i == "source_match"]
            assert match == ["pass"], p["key"]


def test_orientation_sanity(built):
    import json
    report = json.loads((config.REPORT_OUT / "validation.json").read_text())
    sides = [p["passSide"] for p in report["plays"] if p.get("passSide")]
    assert len(sides) >= 20
    assert all(said == seen for said, seen in sides)
