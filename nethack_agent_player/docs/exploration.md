# Exploration

## Doorway mechanics

Passing through a closed door `+` takes **two steps**:
1. Move into `+` tile → door opens, you are now ON the door tile
2. Move again in the same direction → you exit

While standing ON a door tile: **diagonal movement is blocked**. Only N/S/E/W work.
`@` covers the door symbol — use `Features: Player: (x,y)` to confirm your position.

## Map tracking (maintain every turn)

```python
visited   = set()   # (x,y) tiles you have stood on
dead_ends = set()   # (x,y) tiles confirmed impassable
known_stairs = None # (x,y) of > once seen

# Each turn:
x, y = parse_player_pos(state)  # from Features line
visited.add((x, y))

# On blocked move:
dead_ends.add(neighbor_in_direction(x, y, failed_direction))

# On seeing > in Features:
known_stairs = parse_stairs_down(state)
```

Prefer unvisited tiles when choosing direction.

## Stairs not found — escalating protocol

**EVERY level has a down-stair and is fully connected** — if you have explored all
rooms and all of their exits and still see `not found yet`, the stairs are behind a
**hidden passage/door**, not a corridor you missed. Don't keep re-walking known
corridors. If `Stairs↓(>): not found yet`:

1. Follow all unexplored `#` corridors and open all `+` doors
2. `search` (use `search:10`) at: **corridor dead-ends**, AND **room walls that face
   a large blank/unexplored region of the map** (the hidden door is usually on the
   side facing where the missing room must be). One spot rarely needs >10 searches;
   if 10 find nothing, move to the next candidate wall — don't grind one spot.
3. **Wand of secret door detection in inventory** → zap it (it is NON-directional:
   it asks NO "in what direction?"). If a silver/unknown wand *does* prompt for a
   direction, it is NOT secret door detection — see [multi_step.md](multi_step.md) for engrave-ID first.
4. **Scroll of magic mapping** → read it (reveals entire level)
5. **Potion of object detection** → drink it (shows all items including stairs)
6. Boulder blocking a *dead-end* corridor → push it (walk into it); stairs may be behind it. Otherwise leave boulders alone — pushing corrupts `goto` routing and can wall you in (§Navigation pitfalls).
7. Last resort: `search` 10+ times at dead-end corridor walls (hidden doors need multiple searches)

## Anti-loop rules

- Same direction 3+ turns with no position change → stop, pick a different direction
- Pacing east/west in same room → go north or south
- Revisiting same tiles → `search` near walls, then try a completely different direction

## Navigation pitfalls (learned 2026-06)

The pathing/parser have real quirks. Don't fight them blindly:

- **`goto:` fails in twisty corridors & across room↔corridor seams** — it returns
  `It's a wall` / `item_on_path` and does not move, or routes you *backwards*. It is
  reliable only *inside a single room* and on straight, fully-known corridors. After
  it stalls on the same target twice → use `walk:<dir>` for corridors, and **manual
  single steps** (`north`/`east`/diagonals) to cross a doorway/seam, then re-issue
  `goto` from the far side.
- **Moving a boulder breaks `goto`** — it then treats the boulder tile as passable and
  keeps routing you into the dead-end. After a boulder move, navigate manually until
  clear of it. Corollary: **don't push boulders without a concrete reason** — you can
  wall yourself into a 1-tile niche.
- **`Room exits - unexplored gaps (go here!)` is heuristic and is frequently SOLID
  STONE.** Same for the `SITUATION: ... ACTION: goto:` hint. Only `Passable moves`
  and `Unexplored neighbors` are engine-confirmed. Plan from those, not the gap list.
- **ASCII map is off-by-one vs `Features:` coords.** When the picture and the
  `Player:`/`Passable moves` lines disagree, **trust `Features:`**.
- **Pet thrashing**: a following pet stops `goto`/`walk` every turn with "swap places"
  / "is in the way" / "picks up a gold piece". This is normal — just re-issue (each
  call advances), or step into the pet once to put it behind you.
- **A room's top row can be a corridor walled off from the interior below it** — a
  tile that looks "in the room" may only connect along that row. If `south` says
  wall, walk the row to find where it opens down.
