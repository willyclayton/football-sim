# All-22 Play Viewer

A personal iPhone app that replays real NFL plays: all 22 players and the ball at
their tracked positions, with pre-snap callouts, routes, the throw and the game
clock. Every fact on screen carries a source badge (Tracked, Official, Derived,
Charted, Model), and a play ships only after passing the checks below.

**Data rule:** the tracking data belongs to the NFL and was released for the Big
Data Bowl. None of it is committed here: raw files, packed plays and the catalog
are gitignored, CI runs on made-up test data only, and the app is for your own
phone (no App Store, nothing hosted). Read each Kaggle competition's rules before
downloading.

## Status

| Milestone | State |
| --- | --- |
| 1. Data spike | Done. Every sample-game play plays back in 2D, not just play 938 |
| 2. Validator | Done. Hard and soft checks, per-play report, review ledger |
| 3. Animation spike | Not started. Needs a rigged player model (see Next) |
| 4. 3D field and all 22 | Not started |
| 5. Callouts | Done on the sample game. Derived vs charted agreement is measured |
| 6. Full data | 2025-edition adapter written and tested on made-up files; not yet run on the real download |
| 7. Browse and Top plays | A searchable play list only |
| 8. Live mode | Not started |

The Swift code has not been compiled yet: it was written in a Linux container.
CI compiles it on a macOS runner and runs its tests on every push.

## Quick start (on your Mac)

Needs Xcode 26 (the app targets iOS 17 and later), Python 3.9 or newer, and `make`.

```sh
make bundle               # download the sample game, check and pack its plays into app/PlayData
open app/All22.xcodeproj  # set your team under Signing & Capabilities, pick your iPhone, Run
```

`make bundle` creates a virtualenv in `.venv`, downloads the official sample game
(KC at NE, 2017 week 1) from the NFL's public repo plus nflverse labels, and
writes `build/report/validation.md`. A free Apple ID can install to your phone
from Xcode, but the app expires after 7 days; TestFlight needs a paid developer
account. After re-running `make bundle`, use Product > Clean Build Folder so Xcode
copies the new plays.

## What the app does today

- **Play list**: plays by game and quarter, searchable by player, team, formation
  or result. Plays awaiting video review sit apart at the bottom.
- **Viewer** (landscape): a top-down field drawn at the display's refresh rate.
  Positions are smoothed between the 10-per-second samples using each player's
  measured speed and direction.
  - Callout chips (offense and defense, each label badged) show at the start and
    fade at the snap.
  - Scorebug with the game clock counting down from the snap.
  - Scrubber with snap, throw, catch, contact and tackle markers; 0.25x to 2x,
    frame step and loop.
  - Overlays: route trails, the throw's tracked path, line of scrimmage and line
    to gain, names, speeds in mph, and receiver separation at the catch.
  - Tap a player for speed, top speed and distance run; double-tap to follow.
  - Cameras: the play's area, full field, follow the ball, or pinch and drag.
  - A light haptic on the catch and the tackle.
- **Play info**: the official description, every callout with its badge and
  source, every check with its result, and the review status.

## Results on the sample game

From `build/report/validation.md` (177 tracked plays):

| | Count |
| --- | --- |
| Ship | 167 |
| Awaiting video review | 9 |
| Dropped | 1 (play 3486: one defender untracked the whole play) |

Compared with the spec's own run on the same game:

- **Positions present**: all 5 sensor dropouts start after the whistle, so those
  frames are trimmed instead of the play being dropped. That keeps, among others,
  the 75-yard Tyreek Hill touchdown.
- **Snap event**: the spec's run counted 13 kickoffs and 1 direct snap (to Kelce,
  play 701) as missing snaps. Kickoffs are now checked for a kick event, and
  `snap_direct` counts as a snap.
- **Yards agree**: 98 runs and catches checked instead of 41, because carriers
  are matched to the official play-by-play by jersey number. 96 are within 2 yds
  and 82 within 1 yd. Flagged: play 777 (pushed out of bounds, 2.9 yds) and play
  3261, where the ball sensor is frozen all play and the official carrier ends
  4.6 yds behind the line on a play scored +1.
- **Ball sensor agrees**: 8 flagged, four of them on New England's first drive.
- **New hard check, "Matches the source file"**: every packed play is unpacked,
  un-flipped and compared value by value with the raw CSV. 176 of 176 match exactly.
- **Derived vs charted**: offensive personnel 138 of 138 and defensive package 138
  of 138 agree. The 2017 data has no charted receiver set, motion or coverage
  ("not charted" in the app).
- **Orientation**: on the 30 passes the description calls left or right, the ball
  landed on that side 30 times, so the field is not mirrored.

Play 938 shows exactly the spec's example: *12 personnel · Shotgun · 2x2* and
*Dime · 6 in the box · 3 rushers*, plus *Coverage not charted*.

## Video review

Plays that fail a soft check are held back until you compare them with the broadcast:

```sh
make review                                                          # list them, with what to check
make review PLAY=2017090700-777 VERDICT=reviewed NOTE="spot matches"  # or VERDICT=dropped
make bundle                                                          # rebuild with the verdict
```

Verdicts live in `reviews/reviews.csv`: play ids, dates and your notes, no NFL data.

## Choices that differ from the spec

| Spec | Built | Why |
| --- | --- | --- |
| x, y as 16-bit decimeters; angles and speed 8-bit | Every field 16-bit in the source's own hundredths | Same order of size (about 13 KB of frames per play), and lossless, so "positions match the source" is checked exactly |
| Convert to meters in the pipeline | Yards in the file; the app converts | The file stays identical to the source units; 3D can convert once |
| Dropouts drop the play | Dropouts after the whistle are trimmed | They're outside the play; interior gaps up to 0.5 s are filled and flagged, longer ones still drop it |
| Receiver set: receivers more than 4 yds outside the ball | Eligibles not in the backfield, counted per side | Inline tight ends sit about 4 yds out, so the literal rule flips on them. This counts the way coaches do |
| Motion from tagged events | Tagged events, plus anyone moving faster than 2.5 yd/s 0.2 s before the snap | The 2017 tags are sparse. The threshold is untuned until the 2025 motion labels exist |
| EPA and win probability as Official | Badge **Model** | They are model estimates, not official stats |
| Flagged plays don't ship | Bundled into a separate "Awaiting video review" section | So you can review them in the app next to the broadcast. `--no-review-queue` leaves them out |
| iOS 26 | Runs on iOS 17 and later, built with Xcode 26 | Nothing in 2D needs iOS 26. Raise it when 3D does |

## Next

1. **Push and CI.** The first push compiles the Swift code on macOS; fix whatever it finds.
2. **Real data (milestone 6).** Accept the rules at kaggle.com/competitions/nfl-big-data-bowl-2025,
   put your API token in `~/.kaggle/kaggle.json`, then run `make bundle EDITION=bdb2025`. The
   adapter checks every column first and names any mismatch; paste that back to Claude.
   Then retune the receiver-set and motion thresholds against `receiverAlignment` and
   `inMotionAtBallSnap`, and freeze them.
3. **Animation spike (milestone 3).** Choose one rigged football player (USDZ) and the Mixamo
   clips (both need your accounts), then drive one real track in RealityKit.

## Layout

```
pipeline/            Python pipeline (python -m all22 ...), tests in pipeline/tests
  all22/editions/    one adapter per Big Data Bowl edition (2017 sample, 2025)
docs/play-format.md  the .a22 play file, shared by Python and Swift
app/All22/           SwiftUI app
app/PlaybackCore/    Swift package: decoding, interpolation, ball, clock, catalog (+ tests)
app/PlayData/        filled by make bundle (gitignored)
reviews/reviews.csv  your video-review verdicts
```

## Tests

```sh
make test                                   # pipeline: synthetic fault tests, plus the real game when downloaded
swift test --package-path app/PlaybackCore  # Swift: decodes the same synthetic play file
```

The Swift tests read `app/PlaybackCore/Tests/PlaybackCoreTests/Fixtures`, made-up
plays the pipeline writes with `make fixtures`. CI fails if they drift from the pipeline.
