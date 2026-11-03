"""Command line: python -m all22 <command>  (run from the pipeline/ folder)."""

from __future__ import annotations

import argparse
import json
import sys

from . import config

DEFAULT_EDITION = "bdb2019-sample"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="all22", description="All-22 Play Viewer data pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("download", help="download raw files into data/raw (never committed)")
    d.add_argument("--edition", default=DEFAULT_EDITION)
    d.add_argument("--force", action="store_true", help="download again even if present")

    for name, helptext in (("build", "validate, derive, pack, catalog and report"),
                           ("bundle", "download if needed, then build and copy into the app")):
        b = sub.add_parser(name, help=helptext)
        b.add_argument("--edition", default=DEFAULT_EDITION)
        b.add_argument("--no-review-queue", action="store_true",
                       help="leave plays awaiting video review out of the app")
        b.add_argument("--limit", type=int, help="only the first N plays (quick runs)")
        if name == "build":
            b.add_argument("--no-app", action="store_true", help="don't copy into app/PlayData")

    r = sub.add_parser("review", help="list plays awaiting video review, or record a verdict")
    r.add_argument("play", nargs="?", help="play id, e.g. 2017090700-938")
    r.add_argument("verdict", nargs="?", choices=["reviewed", "dropped"])
    r.add_argument("note", nargs="?", default="")

    f = sub.add_parser("fixtures", help="write the synthetic test fixtures")
    f.add_argument("--check", action="store_true", help="fail if committed fixtures are stale")

    s = sub.add_parser("show", help="print a built play's header")
    s.add_argument("play")
    s.add_argument("--edition", default=DEFAULT_EDITION)

    args = ap.parse_args(argv)

    if args.cmd == "download":
        from .download import main as download_main
        return download_main(args.edition, force=args.force)

    if args.cmd in ("build", "bundle"):
        from . import build
        if args.cmd == "bundle":
            from .download import main as download_main
            rc = download_main(args.edition)
            if rc:
                return rc
        build.run(args.edition, review_queue=not args.no_review_queue,
                  copy_to_app=not getattr(args, "no_app", False), limit=args.limit)
        return 0

    if args.cmd == "review":
        from . import reviews
        if args.play and args.verdict:
            entry = reviews.record(args.play, args.verdict, args.note)
            print(f"{args.play}: {entry['status']} on {entry['date']}. Rebuild with `make bundle`.")
            return 0
        report = config.REPORT_OUT / "validation.json"
        if not report.exists():
            print("No report yet; run `make bundle` first.", file=sys.stderr)
            return 1
        plays = json.loads(report.read_text())["plays"]
        flagged = [p for p in plays if p["status"] == "flagged"]
        if not flagged:
            print("Nothing awaiting video review.")
        for p in flagged:
            why = "; ".join(d for (_, res, d) in p["checks"] if res == "fail")
            print(f"{p['key']}  {p['description']}\n    {why}")
        return 0

    if args.cmd == "fixtures":
        from . import fixtures
        return fixtures.main(check=args.check)

    if args.cmd == "show":
        from .pack import read_play
        head, rec = read_play(config.PLAYS_OUT / args.edition / f"{args.play}.a22")
        print(json.dumps(head, indent=2))
        print(f"frames: {rec.shape[0]} x {rec.shape[1]} entities")
        return 0
    return 2
