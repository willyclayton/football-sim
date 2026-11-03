"""Stage 1: download raw files into data/raw (never committed).

The official sample game is pinned to a commit and its checksums are fixed
here, so a changed file fails loudly. nflverse releases are rebuilt from time
to time, so their checksums are recorded in data/raw/nflverse/LOCK.json on
first download and reported when they change.

Kaggle editions need your login and acceptance of the competition rules, so
they are downloaded with the official `kaggle` CLI (see README).
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from . import config

SAMPLE_COMMIT = "9ad0b4b2ea36697e29e44e2399512cc1ce70358c"
SAMPLE_BASE = f"https://raw.githubusercontent.com/nfl-football-ops/Big-Data-Bowl/{SAMPLE_COMMIT}"
NFLVERSE_BASE = "https://github.com/nflverse/nflverse-data/releases/download"


@dataclass(frozen=True)
class RemoteFile:
    url: str
    dest: str  # relative to data/raw
    sha256: str | None = None  # pinned when the source is immutable


SAMPLE_FILES = [
    RemoteFile(f"{SAMPLE_BASE}/Data/games.csv", "bdb2019_sample/games.csv",
               "f5bbd13d9c711c07e3d4a5b674eb25c1f5f9ced099729337bfd366b5229199ed"),
    RemoteFile(f"{SAMPLE_BASE}/Data/players.csv", "bdb2019_sample/players.csv",
               "f83b569774d9511ab684a7569e3a7e277a85e5d317c8af96f05d5d0b7c637ca1"),
    RemoteFile(f"{SAMPLE_BASE}/Data/plays.csv", "bdb2019_sample/plays.csv",
               "0f4c57478d129065119a2a24e243e913cf3fce626b1307720675d1ef55b3623c"),
    RemoteFile(f"{SAMPLE_BASE}/Data/tracking_gameId_2017090700.csv",
               "bdb2019_sample/tracking_gameId_2017090700.csv",
               "30e0de5a213093011d16f7c0893fb6108284cb82be155b5e1bb14de754319f9b"),
]


def nflverse_files(season: int, ftn: bool = False) -> list[RemoteFile]:
    files = [
        RemoteFile(f"{NFLVERSE_BASE}/pbp/play_by_play_{season}.csv.gz",
                   f"nflverse/play_by_play_{season}.csv.gz"),
        RemoteFile(f"{NFLVERSE_BASE}/pbp_participation/pbp_participation_{season}.csv",
                   f"nflverse/pbp_participation_{season}.csv"),
    ]
    if ftn:  # FTN charting starts in 2022
        files.append(RemoteFile(f"{NFLVERSE_BASE}/ftn_charting/ftn_charting_{season}.csv",
                                f"nflverse/ftn_charting_{season}.csv"))
    return files


KAGGLE_COMPETITIONS = {"bdb2025": "nfl-big-data-bowl-2025"}


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _fetch(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "all22-pipeline"})
    with urllib.request.urlopen(req, timeout=300) as resp, open(tmp, "wb") as out:
        shutil.copyfileobj(resp, out)
    tmp.replace(dest)


def ensure(files: list[RemoteFile], force: bool = False, log=print) -> dict[str, str]:
    """Download missing files and verify checksums. Returns {dest: sha256}."""
    lock_path = config.RAW / "nflverse" / "LOCK.json"
    lock = json.loads(lock_path.read_text()) if lock_path.exists() else {}
    digests: dict[str, str] = {}
    for rf in files:
        dest = config.RAW / rf.dest
        if force or not dest.exists():
            log(f"  downloading {rf.dest}")
            _fetch(rf.url, dest)
        digest = sha256_of(dest)
        if rf.sha256 and digest != rf.sha256:
            raise SystemExit(
                f"Checksum mismatch for {rf.dest}: expected {rf.sha256}, got {digest}. "
                "The pinned source changed; delete the file and investigate before rebuilding."
            )
        if rf.dest.startswith("nflverse/"):
            old = lock.get(rf.dest)
            if old and old != digest:
                log(f"  note: {rf.dest} changed since it was first recorded (nflverse rebuilt it)")
            lock[rf.dest] = digest
        digests[rf.dest] = digest
    if lock:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text(json.dumps(lock, indent=2, sort_keys=True))
    return digests


def download_sample(force: bool = False, log=print) -> dict[str, str]:
    log("Big Data Bowl sample game (KC at NE, 2017 week 1) and nflverse 2017 labels")
    return ensure(SAMPLE_FILES + nflverse_files(2017), force=force, log=log)


def download_kaggle(edition: str, log=print) -> None:
    """Fetch a Kaggle edition with the official CLI, then nflverse labels for its season."""
    comp = KAGGLE_COMPETITIONS[edition]
    dest = config.RAW / edition
    if not any(dest.glob("tracking_week_*.csv")):
        if shutil.which("kaggle") is None:
            raise SystemExit(
                f"The {edition} files are not in {dest} and the kaggle CLI is not installed.\n"
                f"1. Sign in at kaggle.com, open https://www.kaggle.com/competitions/{comp}/rules "
                "and accept the rules (read them: they limit how the data may be used).\n"
                "2. pip install kaggle, and put your API token in ~/.kaggle/kaggle.json.\n"
                f"3. Rerun this command, or download the zip by hand and unzip it into {dest}."
            )
        dest.mkdir(parents=True, exist_ok=True)
        log(f"  kaggle competitions download -c {comp}")
        subprocess.run(["kaggle", "competitions", "download", "-c", comp, "-p", str(dest)],
                       check=True)
        for z in dest.glob("*.zip"):
            log(f"  unzipping {z.name}")
            with zipfile.ZipFile(z) as zf:
                zf.extractall(dest)
            z.unlink()
    ensure(nflverse_files(2022, ftn=True), log=log)


def main(edition: str, force: bool = False) -> int:
    if edition == "bdb2019-sample":
        download_sample(force=force)
    elif edition in KAGGLE_COMPETITIONS:
        download_kaggle(edition)
    else:
        print(f"Unknown edition {edition}", file=sys.stderr)
        return 2
    return 0
