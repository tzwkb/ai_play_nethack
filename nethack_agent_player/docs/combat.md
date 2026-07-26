# Combat

## Default stance by role

| Role | Default | Exception |
|------|---------|-----------|
| Wizard / Healer / Priest | avoid melee | see below |
| Valkyrie / Barbarian / Caveman | melee OK | flee if outnumbered |
| Others | avoid if possible | — |

## Melee exceptions (wizard/healer/priest)

Melee is acceptable when ANY of these apply:
- 1-tile-wide corridor and pet cannot reach the enemy
- Single low-threat enemy (grid bug, jackal) AND HP > 60%
- Surrounded with no escape route

## HP thresholds

| HP | Action |
|----|--------|
| < 30% + clearly dangerous enemy (dragon, demon, high-XP monster) | flee toward `<` or narrow `#` corridor |
| < 20% | use healing potion if available |
| < 10% | use best healing available, pray if no potions |

Below 25% HP, the safety lock overrides normal aggression. Do not wait, search,
loot, eat, test unknown consumables, or explore. Prefer identified healing/escape,
the known upstairs, or movement that increases distance. Fight only when no safer
action exists.

## Tactics

- `safe_wait:N` is the normal rest action and stops when danger changes
- Never wait while a hostile is visible
- Funnel enemies into corridors — fight one at a time, never in open rooms
- Diagonal movement to dodge grid bugs (they only move cardinally)
- **Floating eye** (`e`): NEVER melee — paralyzes you. Use wand or let pet handle.
- **Gas spore** (`e`): NEVER melee — explodes on death. Flee immediately.
- **Nymph** (`n`): steals items. Flee on sight.

## Pet management

- Do NOT attack your pet (kitten `f`, little dog `d`)
- Pet blocking path → **move in the pet's direction to swap places** ("You swap places with your kitten") — do NOT wait
- `wait` is only needed when you want the pet to act first (draw aggro), not to unblock it
- Pet fights for you — stay behind it when possible
