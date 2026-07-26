# Changelog

## v5.4.0 (2026-07-26) — survival safety layer
- Added an execution-level critical-danger lock. Unsafe waiting, searching, looting,
  eating, unknown item use, and non-retreat bulk navigation are refused unless the
  caller explicitly uses `force:`.
- Added per-turn `safe_wait:N`, exact non-pet monster metadata, actionable retreat
  advice, persistent trap coordinates, and hazard-aware BFS navigation.
- Added per-run item-effect observations so repeated appearances retain observed
  healing/non-healing evidence without leaking randomized mappings across games.
- Removed the hardcoded Valkyrie startup choice. Character selection now remains
  pending until `agent_helper.py --choose <character>` is called.
- Fixed game-over depth/cause extraction using the last live state. Memory records
  now upsert by `game_id` and support exact lesson deletion.
- Added `pray`, 8 safety/post-game regression tests, and live NLE smoke coverage.

## v5.3.1 (2026-06-10) — skill-wide quality cleanup
- **Deleted dead files** (zero refs): `scripts/_write_env.py` (390-line env.py generator that silently drifts), `play.py.bak`, `scripts/env.py.bak`, `restart_tmux.py` + `start_game.sh` (WSL/tmux, hardcoded `/mnt/c/...`), committed `__pycache__/`. Added `.gitignore`.
- **Removed dead code**: `env.py` `reset()` (broken — undefined `state` + blocking `input()`), `detect_mode()` (superseded by `_active_prompt`), `render_debug()`; unused `monster_db` import in play.py; duplicate import in `scripts/__init__.py`; the `detect_mode` test assertion.
- **Fixed stale docs**: README rewritten (the in-process `env.reset()` example never matched the real IPC flow; broken `references/` link, wrong char format, wrong macOS install). `metadata.json` 3.0.0→5.3.1 + accurate description. `agent_helper.py` docstring de-WSL'd; **`zap:f,north`→`zap:f:north`** (comma form is rejected by play.py) in docstring + SKILL.md.
- **De-duplicated v5.3.0 docs**: SKILL.md quick-ref now points to exploration.md §Navigation pitfalls instead of restating it; reconciled the new "don't push boulders" rule with the existing push-boulder step.
- Verified: all `.py` compile, `metadata.json` parses, `tests/test_env_actions.py` passes, `scripts` imports.
- **Noted (not applied — load-bearing, needs a live game to test):** the goto/pathing root causes — `navigate_to` re-plans every step instead of following a cached path; boulders are hard-coded walkable; passability is glyph-heuristic instead of `obs['glyphs']`; `unexplored gaps (go here!)`/`ACTION:` hints aren't BFS-verified. Plus medium dedups: forked direction tables (env/play/agent_helper), item_db≈monster_db, agent_helper regex vs state_parser.

## v5.3.0 (2026-06-10) — lessons from a Dlvl-3 run
- **Navigation pitfalls** documented (exploration.md + SKILL.md): `goto:` is unreliable in twisty corridors / across room↔corridor seams (returns `It's a wall`, routes backwards) and breaks after a boulder move → fall back to `walk:`/manual steps; `goto` reliable only inside one room / straight corridors. Added `item_on_path` stop reason.
- **`unexplored gaps (go here!)` and the `SITUATION` hint are heuristic — often solid stone**; trust `Passable moves`/`Unexplored neighbors`. Map ASCII is off-by-one vs `Features:` coords → trust Features.
- **Pet thrashing** ("swap places"/"in the way"/"picks up gold") interrupts every move — re-issue or step into pet; don't over-think.
- **Wand engrave-ID** added (multi_step.md): `keys:E`→wand; message table; "glows, then fades" = directional non-elemental wand. **ESC at a direction prompt wastes a charge** — cancel at item-selection instead. Secret-door-detection is non-directional.
- **Don't push boulders without reason** (can wall you in, corrupts pathing).
- **Unidentified item heuristics** (knowledge.md): magic-cloak appearances safe to wear; gloves may be gauntlets of fumbling (don't wear); fixed-name helm safe vs plumed/etched = opposite-alignment risk; lichen corpse never rots (always grab).
- **macOS `.venv` can go missing** → rebuild note in setup.md (recompiles NetHack ~3–5 min; needs bison/flex PATH + CFLAGS).

## v5.2.0 (2026-04-20)
- Fixed `send_keys` IndexError: chars now resolved via `env.unwrapped.actions`, not `ord()`
- Added `/tmp/nethack_ready` IPC sync signal — eliminates blind-wait race condition
- Fixed `wiki.py` Cloudflare bypass: full browser UA + Accept headers + mirror fallback
- Expanded `monsters.json` 7→24 entries; `items.json` 7→21 entries
- Added `scripts/dump_actions.py` utility to print all NLE action indices
- Documented doorway two-step mechanic, diagonal block on door tile
- Added stairs search escalation protocol
- Added Windows IPC write pattern (UTF-8, no echo)

## v5.1.0 (2026-04-20)
- Added character selection phase via `/tmp/nethack_charselect` IPC

## v5.0.0 (2026-04-20)
- Added `send_keys()` for multi-step interactions
- Atomic file IPC via `os.replace`
- `try/finally` gameover guarantee in `play.py`
- Melee rule with explicit exceptions
- Internal map tracking rule

## v4.0.0 (2026-04-19)
- Rewritten in English
- Anti-loop rules, door exploration, `<` vs `>` clarification, last-action context guide

## v3.0.0 (2026-04-19)
- Refactored, removed translation layer, direct TTY rendering
