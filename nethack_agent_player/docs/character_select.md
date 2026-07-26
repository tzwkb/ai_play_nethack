# Character Selection

Triggered when `play.py` starts without a character argument.

## Flow

1. `play.py` writes `/tmp/nethack_charselect` (JSON with all options)
2. Read it, decide, write choice to `/tmp/nethack_charselect_response`
3. `play.py` creates the env and writes initial state to `/tmp/nethack_state`

```python
import json, os

with open("/tmp/nethack_charselect") as f:
    options = json.load(f)

choice = decide_from_options(options)  # no hardcoded default

with open("/tmp/nethack_charselect_response.tmp", "w") as f:
    f.write(choice)
os.replace("/tmp/nethack_charselect_response.tmp", "/tmp/nethack_charselect_response")
```

If `/tmp/nethack_charselect` does not exist, `play.py` was started with a hardcoded character — skip this phase.

## Format

`<role>-<race>-<gender>-<alignment>` e.g. `wiz-hum-mal-neu`, `val-hum-fem-neu`

Invalid combos are auto-corrected by NetHack.

## Strategy

1. Check `memory.load()` — past lessons may favor a specific role
2. Choose freely for the current run; no role/race/gender/alignment is hardcoded
3. Use past lessons to adjust tactics, not to force a specific role
4. Fragile roles need an explicit early survival plan; Tourist remains a high-risk pick

When `agent_helper.py --start` is used without a character, it prints the available
options and leaves selection pending. Complete it with:

```bash
python3 agent_helper.py --choose bar-hum-mal-neu
```

## Role quick ref

| Code | Role | Strength |
|------|------|----------|
| val | Valkyrie | high HP, strong fighter, female only |
| wiz | Wizard | magic, fragile, starts with kitten |
| hea | Healer | self-heal, starts with potions |
| bar | Barbarian | high HP, strong melee |
| ran | Ranger | ranged, starts with bow + large cat |
| rog | Rogue | stealth, traps |
| pri | Priest | divine magic |
| kni | Knight | mounted, lawful only |
| mon | Monk | unarmed, neutral only |
| sam | Samurai | swordsman, lawful |
| arc | Archeologist | item-finding, pick-axe |
| cav | Caveman | tough, starts with large dog |
| tou | Tourist | weak start, avoid |
