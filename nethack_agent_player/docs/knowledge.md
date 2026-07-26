# Knowledge Lookup

## Lookup order

1. Check local DB first (fast, offline)
2. If not found → `wiki_lookup` (network)
3. Save result to DB permanently

## Monster lookup

```python
from scripts import lookup_monster, save_monster, wiki_lookup

info = lookup_monster('newt')
if info is None:
    raw = wiki_lookup('newt')
    save_monster(name='newt', symbol='n', threat='low',
                 notes='Drains STR/DEX. Let pet handle.')
    info = lookup_monster('newt')
```

## Item lookup

```python
from scripts import lookup_item, save_item, wiki_lookup

info = lookup_item('potion of healing')
if info is None:
    raw = wiki_lookup('potion of healing')
    save_item(name='potion of healing', category='potion',
              effect='restores HP', notes='use when HP < 60%')
    info = lookup_item('potion of healing')

# Unidentified items (e.g. "blue potion"): do NOT save until identified.
# Use scroll of identify first.
```

## When to look up

| Trigger | Query |
|---------|-------|
| Unknown monster symbol | monster name from Message |
| Unknown map symbol `:` `^` `_` `{` | `fountain`, `trap`, `altar`, `fountain` |
| Unidentified item | identified name only |
| Unexpected message | the message text |
| Role strategy at start | `wizard`, `valkyrie`, etc. |

## Map symbols

| Symbol | Meaning | Symbol | Meaning |
|--------|---------|--------|---------|
| `@` | you | `>` | stairs down — goal |
| `#` | corridor | `<` | stairs up |
| `+` | closed door | `.` | floor |
| `\|` `-` | wall or open door | `f` | kitten (pet) |
| `$` | gold | `%` | food/corpse |
| `` ` `` | boulder | `n` `d` `j`... | monsters |

Unknown symbol → `wiki_lookup('symbol name')`.

## Symbol reference

| Symbol | Meaning | Action |
|--------|---------|--------|
| `:` | fountain / pool / grave | `wiki_lookup('fountain')` before stepping |
| `^` | trap | avoid; `wiki_lookup('trap')` |
| `_` | altar | `wiki_lookup('altar')` — useful or dangerous |
| `{` | fountain | same as `:` |
| `F` | lichen | very slow; can grab you; no stat drain |
| `e` | floating eye or gas spore | NEVER melee either — see combat.md |

## Unidentified item heuristics (wear / eat decisions)

Decide from the **appearance** before you have an ID:

| Item / appearance | Verdict |
|-------------------|---------|
| Cloak: *opera cloak / tattered cape / ornamental cope / piece of cloth* | Always a **magic cloak** (protection / invisibility / magic resistance / displacement) → **safe to wear unID'd** (+AC and/or a strong property; worst case cursed-but-beneficial). |
| Cloak: leather / oilskin / dwarvish / elven | Mundane, safe to wear. |
| Gloves: *riding / old / padded / fencing gloves* | May be **gauntlets of fumbling** (drops weapon mid-fight) → **carry, do NOT wear unID'd**. Price-ID at a shop or read identify first. |
| Helm: fixed-name *orcish helm / dwarvish iron helm / …* | Exactly that (small +AC) → safe to wear. |
| Helm: *plumed / etched / crested / visored helmet* | May be **helm of opposite alignment** (cursed, flips alignment) → don't wear unID'd. |
| Ring / amulet (any) | Never `puton` unID'd without BUC (altar / identify) — cursed ones stick, some are lethal. |
| **Lichen corpse** | **Never rots** → always `pickup` as emergency food; safe to eat. |

## After every lookup

- New monster → `save_monster(...)`
- New item → `save_item(...)`
- New symbol or mechanic → add row to this file
