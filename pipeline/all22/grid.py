"""Turn one play's tracking rows into dense (frame x entity) arrays."""

from __future__ import annotations

import numpy as np

from .model import (DEFENSE_ORDER, OFFENSE_ORDER, Entity, Play, PlayInput,
                    position_group)


def _sort_key(e: Entity):
    order = OFFENSE_ORDER if e.side == "offense" else DEFENSE_ORDER
    rank = order.index(e.group) if e.group in order else len(order)
    return (0 if e.side == "offense" else 1, rank,
            e.jersey if e.jersey is not None else 999, e.key)


def build_play(inp: PlayInput) -> Play:
    tr = inp.tracking
    game, meta = inp.game, inp.play
    offense_team = "home" if meta["possession"] == game["home"] else "away"

    players = []
    for key in tr.loc[tr["key"] != "ball", "key"].unique():
        r = inp.roster.get(key, {})
        team = r.get("team")
        players.append(Entity(
            key=key, kind="player", team=team,
            side="offense" if team == offense_team else "defense",
            nfl_id=r.get("nfl_id"), name=r.get("name"), jersey=r.get("jersey"),
            position=r.get("position"), group=position_group(r.get("position")),
        ))
    players.sort(key=_sort_key)
    entities = [Entity(key="ball", kind="ball")] + players
    index = {e.key: i for i, e in enumerate(entities)}

    frames = np.sort(tr["frame"].unique()).astype(int)
    fidx = {int(f): i for i, f in enumerate(frames)}
    F, E = len(frames), len(entities)
    arr = {name: np.full((F, E), np.nan) for name in ("x", "y", "s", "dir", "o")}
    present = np.zeros((F, E), dtype=bool)

    fi = tr["frame"].map(fidx).to_numpy()
    ei = tr["key"].map(index).to_numpy()
    for name in arr:
        arr[name][fi, ei] = tr[name].to_numpy(dtype=float)
    present[fi, ei] = True

    duplicates = int(tr.duplicated(subset=["frame", "key"]).sum())

    ev = tr.dropna(subset=["event"])
    events = []
    for frame, names in ev.groupby("frame")["event"]:
        for name in dict.fromkeys(names):  # distinct, in order
            events.append((fidx[int(frame)], str(name)))
    events.sort()

    play = Play(
        key=f"{meta['game_id']}-{meta['play_id']}",
        edition=inp.edition, game=game, meta=meta, entities=entities,
        source_frames=frames, x=arr["x"], y=arr["y"], s=arr["s"], dir=arr["dir"], o=arr["o"],
        present=present, flags=np.zeros((F, E), dtype=np.uint16), events=events,
        offense_team=offense_team, sources=dict(inp.sources),
    )
    if duplicates:
        play.notes.append(f"{duplicates} duplicate tracking rows ignored")
    play.window = (0, F - 1)
    play.raw = {name: a.copy() for name, a in arr.items()}
    return play
