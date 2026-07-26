# Multi-step Interactions

NetHack commands like quaff, zap, wield, put on require multiple keypresses.
Use `send_keys()` (Python) or `keys:` prefix (IPC).

## Command reference

| Command | Key | IPC shorthand | Example |
|---------|-----|---------------|---------|
| quaff potion | `q` | `drink:<slot>` | `drink:f` |
| read scroll | `r` | `read:<slot>` | `read:e` |
| zap wand | `z` | `zap:<slot>:<dir>` | `zap:f,north` |
| wield weapon | `w` | `wield:<slot>` | `wield:a` |
| wear armor | `W` | `wear:<slot>` | `wear:c` |
| take off armor | `T` | `takeoff:<slot>` | `takeoff:c` |
| put on ring | `P` | `puton:<slot>` | `puton:h` |
| remove ring | `R` | `remove:<slot>` | `remove:h` |
| drop item | `d` | `drop:<slot>` | `drop:d` |
| confirm/yes | `y` | — | `keys:y` |
| cancel | ESC | — | `keys:27` |

## Via IPC

```
keys:q,g        # quaff item g
keys:z,f,k      # zap wand f northward
keys:r,h        # read scroll h
keys:P,i        # put on ring i
```

## Vi-keys (direction chars for zap/throw/etc.)

| Direction | Key |
|-----------|-----|
| north | `k` |
| south | `j` |
| east | `l` |
| west | `h` |
| northeast | `u` |
| southeast | `n` |
| southwest | `b` |
| northwest | `y` |

## Wand usage

Zap wand of secret door detection in all 4 directions to reveal hidden doors:

```python
for direction in ['k', 'j', 'h', 'l']:
    state = env.send_keys(['z', wand_letter, direction])
```

## Troubleshooting

If `send_keys` returns `[ERROR] '...' not in NLE action space`:

```bash
# In WSL — prints all valid action indices and their chars:
python3 scripts/dump_actions.py
```

`send_keys` maps chars via `env.unwrapped.actions` — it does NOT use `ord()` directly.
Passing an out-of-range int also returns an error string instead of crashing.

## CRITICAL: item-selection prompts ("Never mind" bug) — fixed

Symptom: `wear:g` / `wield:a` / `drink:f` return `Message: Never mind.` and do
nothing; a following stray key cascades into `Invalid direction for 'g' prefix`.

Root cause (NLE 1.3.0, verified in source `nle/env/base.py`): by default the env
is built with `allow_all_yn_questions=False`. Every step then runs
`_perform_known_steps`, which **auto-ESCs any single-char prompt** (`in_yn_function`)
unless its message is in `SKIP_EXCEPTIONS` (eat / attack / direction). NetHack's
`getobj` ("What do you want to wear? [g or ?*]") is such a prompt, so it is
auto-declined → "Never mind" — *before* any item letter can be sent. Direction
prompts ("In what direction?") work because they ARE in SKIP_EXCEPTIONS.

Fix (already applied in `scripts/env.py`): create the env with
`allow_all_yn_questions=True`. getobj prompts then **pause** and accept the item
letter. `--More--` pagination is still auto-handled because `allow_all_modes`
stays `False`.

```python
self.env = gym.make(env_id, savedir=None, character=..., allow_all_yn_questions=True)
```

### Robust selection: `env.menu_select(cmd, slot, trailing=None)`

NetHack auto-selects when exactly ONE item qualifies (e.g. `T` with one worn
item) and shows NO prompt — sending the slot letter then becomes a stray command.
`menu_select` presses `cmd`, sends `slot` **only if** a "What do you want to..?"
prompt actually appears, then sends any `trailing` keys (a direction for `zap`).
All `wear/wield/drink/read/takeoff/drop/puton/remove/zap` IPC verbs route through it.

### Seeing prompts over IPC

`obs['message']` is usually EMPTY at a getobj prompt (the text lives in tty row 0),
so the state's `Message:` line goes stale. `render()` now adds a
`PROMPT (game awaiting input ...)` line surfacing the live tty prompt. When you
see it, answer with `keys:<letter>`, `keys:y`/`keys:n`, or `keys:27` (ESC).

This requires the env to be (re)created — restart `play.py` after changing the flag.

## `keys:` integers are ACTION INDICES, not ASCII

In `send_keys`, a **string** key is resolved via `_char_to_idx` (ASCII→index), but
an **int** key is passed straight to `env.step()` as an action INDEX. So `keys:y`
presses 'y', while `keys:43` runs action #43 — NOT ASCII 43. To send a command by
its index, look the index up first (the value↔index map differs from ASCII):

```python
# value 236 (M-l, loot) lives at action INDEX 43 → send keys:43, not keys:236
import gymnasium as gym, nle
e = gym.make('NetHack-v0', allow_all_yn_questions=True)
{getattr(a,'value',None): i for i,a in enumerate(e.unwrapped.actions)}
```

## Containers & extended commands (loot / force / kick)

Verified working over IPC (NLE 1.3.0, `allow_all_yn_questions=True`):

| Goal | Send | Then |
|------|------|------|
| Loot a container at your feet | `keys:43` (LOOT, value 236) | `keys:y` at "loot it? [ynq]" |
| Force a locked box's lock | `keys:36` (FORCE, value 230) | `keys:y` at "force its lock?" |
| Kick (e.g. locked door) | `keys:41,0` = KICK(^D idx41)+dir | north=0 e=1 s=2 w=3 / `kick:north` also works |

- Open a locked box at your feet: **wield an expendable weapon first** (`wield:b`
  dagger) — forcing with a blade can break it; don't risk the main weapon. Then
  `keys:36` → `keys:y`. Re-`wield:a` after.
- Large boxes are too heavy to carry — **never `pickup` them**; drop (`drop:<slot>`)
  and loot on the floor. They are often empty.
- Direction action indices (vi-keys): N=0 E=1 S=2 W=3 NE=4 SE=5 SW=6 NW=7.

## Identifying wands safely (engrave-test) + direction prompts

Never zap an unidentified wand at yourself or your pet (polymorph / cancellation /
teleport can wreck both). **Engrave-test first** — it's free and safe:

```
keys:E            # "What do you want to write with? [- a-z]"
keys:<wand-slot>  # e.g. keys:h
```

The engrave message classifies the wand:

| Engrave message | Wand is… |
|-----------------|----------|
| digs a hole / you fall through | **digging** (you descend — fine) |
| engraving burns / freezes / bolt | fire / cold / lightning / magic missile / striking / sleep / death (an **attack** wand — auto-IDs) |
| "the bugs … stop / slow down / speed up" | sleep / slow monster / speed monster |
| **"The wand glows, then fades."** | a **directional, non-elemental** wand: opening, locking, probing, undead turning, cancellation, polymorph, make invisible, or teleportation (not digging, not an attack wand) |
| "You write in the dust …" (no special effect) | a non-directional utility wand (light, secret door detection, …) |

**Directional vs not:** if zapping (`keys:z,<slot>`) shows `In what direction?`, the
wand is **directional** — so it is NOT secret door detection / light / magic mapping.
Combined with a "glows, then fades" engrave, you have a directional utility wand worth
keeping for emergencies; get a scroll of identify / price-ID to pin the exact type.

**⚠ ESC at a direction prompt WASTES a charge.** `keys:27` answers "In what
direction?" as a *strange direction* → "the wand glows and fades", charge gone, no
effect. To abort a zap, cancel at the *item-selection* prompt (before choosing the
wand), never at the direction prompt. Only zap when you actually intend to aim
(`zap:<slot>:<dir>` or `keys:z,<slot>,<vi-key>`).
