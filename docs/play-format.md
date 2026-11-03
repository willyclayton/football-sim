# Play file format (`.a22`, version 1)

One file per play, written by `pipeline/all22/pack.py` and read by
`app/PlaybackCore/Sources/PlaybackCore/PlayFile.swift`. Both sides are tested
against the same synthetic file
(`app/PlaybackCore/Tests/PlaybackCoreTests/Fixtures/synthetic-play.a22`).

## Layout

All integers are little-endian.

| Offset | Size | Field |
| --- | --- | --- |
| 0 | 4 | Magic `A22P` |
| 4 | 2 | Format version, `1` |
| 6 | 2 | Reserved, `0` |
| 8 | 4 | Header length `H` |
| 12 | `H` | Header, UTF-8 JSON |
| 12 + `H` | 4 | Frames block length `B` |
| 16 + `H` | `B` | Frames block |

The frames block is raw DEFLATE (RFC 1951, no zlib header) when
`header.frames.encoding` is `"deflate"`. Inflated, it holds
`frames.count × entities.length` records, frame-major: all entities of frame 0,
then frame 1, and so on. Entity order is the header's `entities` array; entity 0
is always the ball.

## Record (12 bytes)

| Field | Type | Unit | Missing |
| --- | --- | --- | --- |
| x | int16 | 0.01 yd | -32768 |
| y | int16 | 0.01 yd | -32768 |
| s (speed) | uint16 | 0.01 yd/s | 65535 |
| dir (direction of motion) | uint16 | 0.01 degree | 65535 |
| o (facing) | uint16 | 0.01 degree | 65535 |
| flags | uint16 | bits below | |

The source data has two decimals, so these units are lossless: the pipeline
proves it for every play by unpacking, un-flipping and comparing with the raw
file (check `source_match`).

Flags: `1` position missing (never shipped), `2` filled across a short sensor gap
(straight-line interpolation, up to 0.5 s), `4` no direction, `8` no facing,
`16` no speed.

## Coordinates

Normalized so the offense (for kicks, the kicking team) always attacks toward +x.

- x: 0 to 120 yards along the field. End zones are 0 to 10 and 110 to 120; the
  goal line being attacked is x = 110.
- y: 0 to 53.3 yards across. Looking downfield, +y is the offense's left.
- Angles are degrees clockwise from +y, so velocity is
  `(s * sin(dir), s * cos(dir))`.

The app converts yards to meters for its 3D scene (1 yd = 0.9144 m).

## Timing

`frames.rate` frames per second (10). Frame indices in the header (events, key
frames, ball segments, clock) are 0-based indices into this file's frames. Frame 0
is line set when tagged, otherwise the first tracked frame (at most 10 s before
the snap). The file ends 1.5 s after the whistle.

To draw between frames, use cubic Hermite interpolation of x and y with tangents
from speed and direction (`s * sin(dir)`, `s * cos(dir)`, scaled by the frame
interval). That gives smooth 60 or 120 fps motion through the measured points.
Fall back to linear where direction is missing (the ball, flag `4`).

## Header

```jsonc
{
  "format": "all22-play", "version": 1,
  "id": "2017090700-938",              // gameId-playId
  "synthetic": false,                  // true only for made-up test data
  "edition": {"id": "bdb2019-sample", "name": "..."},
  "game": {"id", "season", "week", "date",
           "home": {"abbr", "name", "primaryColor", "secondaryColor", "textColor"},
           "away": {...}},
  "situation": {"quarter", "clockSeconds", "down", "yardsToGo", "goalToGo",
                "possession", "offense": "home|away", "yardline": "NE 7",
                "losX", "losSource": "tracked|official", "lineToGainX",
                "scoreBefore": {"home", "away"}},
  "outcome": {"description", "type", "result", "yards", "touchdown",
              "scoreAfter", "epa", "wpa", "winProbability"},
  "frames": {"count", "rate", "encoding", "recordSize", "sourceStartFrame", "orientation"},
  "entities": [{"kind": "ball"},
               {"kind": "player", "team", "side": "offense|defense", "nflId",
                "name", "jersey", "position", "group"}],
  "events": [{"frame", "name", "label", "marker", "haptic"}],
  "keyFrames": {"start", "snap", "kick", "handoff", "throw", "arrival", "catch",
                "outcome", "received", "contact", "tackle", "whistle", "end"},
  "clock": {"startFrame", "secondsAtStart"},  // startFrame null: clock doesn't run
  "ball": {"segments": [...]},                // see below
  "carrier": 5,                               // entity holding the ball at the whistle
  "callouts": {"offense": [...], "defense": [...], "afterSnap": [...]},
  "checks": {"status": "ship|flagged", "hard": [...], "soft": [...], "notes": [...]},
  "review": {"status": "unreviewed|reviewed|dropped", "date", "note"},
  "stats": {"duration", "topSpeedMph", "topSpeedName", "airYards", "airDownfield"},
  "provenance": {"pipelineVersion", "sources": {"file": "sha256"}, "flipped", "direction"}
}
```

`epa`, `wpa` and `winProbability` are model estimates (badge Model), not
official statistics.

### Ball segments

The tracked ball sensor is the weakest part of the 2017 data, so the ball is drawn
from segments that tile the file's frames with no gaps:

| `mode` | Position | Height |
| --- | --- | --- |
| `tracked` | ball sensor x, y | `z0` (yards) |
| `held` | the `holder` entity's x, y | carry height (1 yd) |
| `flight` | ball sensor x, y | `z0 + (z1 - z0)u + 4·apex·u(1-u)`, `u` from 0 to 1 across the segment |

`apex = g·T²/8` for flight time `T`: the height of a free-flying ball above the
straight line from release to catch. Height is synthesized (badge Derived); the
path is tracked.

### Callouts

```jsonc
{"key": "personnel", "label": "12 personnel", "badge": "derived",
 "missing": false, "detail": "1 RB, 2 TE, 2 WR", "source": "Roster positions ..."}
```

A missing label is shown as given (for example "Coverage not charted") with
`missing: true`, never guessed.

### Badges

| Badge | Means |
| --- | --- |
| `tracked` | NFL Next Gen Stats sensor data |
| `official` | NFL play-by-play |
| `derived` | Fixed rules applied to tracked positions |
| `charted` | Labels coded by people (FTN, PFF, NFL) |
| `model` | Statistical model estimates (EPA, win probability) |
| `animated` | Body poses the app adds (3D, later) |
| `simulated` | Live-mode estimates; never in replays |

### Checks

Each entry is `{"id", "name", "kind": "hard|soft", "result", "detail"}`, where
`result` is `pass`, `fixed` (passed after a recorded repair), `fail` or `n/a`.
Plays that fail a hard check are never written. A soft failure ships only after
video review (`review.status == "reviewed"`).
