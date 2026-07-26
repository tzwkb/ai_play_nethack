import sys
import os
import time
import json
import re

sys.path.insert(0, os.path.dirname(__file__))
from scripts import create_env
from scripts.memory import Memory
from scripts import state_parser
from scripts import item_db
from scripts.postgame import extract_depth_and_cause

CHAR_OPTIONS = {
    "roles": {
        "arc": "Archeologist — finds items easily, starts with pick-axe and food rations",
        "bar": "Barbarian — strong melee, high HP, starts with two-handed sword",
        "cav": "Caveman — tough primitive fighter, starts with club and large dog",
        "hea": "Healer — can heal self, starts with healing potions and scalpel",
        "kni": "Knight — mounted combat, high AC, lawful only",
        "mon": "Monk — unarmed specialist, fast movement, neutral only",
        "pri": "Priest — divine magic, starts with mace and holy water",
        "ran": "Ranger — ranged combat, starts with bow, arrows, and large cat",
        "rog": "Rogue — stealth and traps, starts with dagger and cloak",
        "sam": "Samurai — skilled swordsman, lawful, starts with katana",
        "tou": "Tourist — starts with gold and items but weak early game",
        "val": "Valkyrie — strong fighter, female only, recommended for beginners",
        "wiz": "Wizard — powerful magic, fragile, starts with spellbook and kitten",
    },
    "races": {
        "hum": "Human — balanced stats, compatible with all roles",
        "elf": "Elf — magic affinity, infravision, sleep resistance, lower max STR",
        "dwa": "Dwarf — high STR/CON, infravision; only arc/bar/cav/hea/kni/ran/val",
        "gno": "Gnome — small, infravision, magic resistance; only arc/hea/ran/rog/wiz",
        "orc": "Orc — high STR, poison resistance; only bar/ran/rog/wiz",
    },
    "genders": {
        "mal": "Male",
        "fem": "Female (required for Valkyrie)",
    },
    "alignments": {
        "law": "Lawful — disciplined, better item bonuses from gods",
        "neu": "Neutral — balanced, flexible",
        "cha": "Chaotic — fewer restrictions, can do more things",
    },
    "format": "<role>-<race>-<gender>-<alignment>",
    "examples": ["wiz-hum-mal-neu", "val-hum-fem-neu", "bar-orc-mal-cha", "hea-gno-fem-neu"],
    "note": "Invalid combos (e.g. val-hum-mal) are auto-corrected by NetHack. Choose freely for the current run; no role is the default.",
}

def _select_character():
    tmp = "/tmp/nethack_charselect.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(CHAR_OPTIONS, f, ensure_ascii=False, indent=2)
    os.replace(tmp, "/tmp/nethack_charselect")

    while not os.path.exists("/tmp/nethack_charselect_response"):
        time.sleep(0.05)

    try:
        os.rename("/tmp/nethack_charselect_response", "/tmp/nethack_charselect_response.tmp")
    except FileNotFoundError:
        return None
    with open("/tmp/nethack_charselect_response.tmp", "r", encoding="utf-8") as f:
        choice = f.read().strip()
    os.remove("/tmp/nethack_charselect_response.tmp")
    try:
        os.remove("/tmp/nethack_charselect")
    except FileNotFoundError:
        pass
    return choice or None

character = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('--') else None
display_mode = '--display' in sys.argv
if character is None:
    character = _select_character()
env = create_env(character=character)
memory = Memory(os.path.join(os.path.dirname(__file__), "nethack_memory.json"))

# bypass input() in reset
obs, _ = env.env.reset()
env._obs = obs
env.turn = 0
env.history = []
state = env.render(obs)
last_live_state = state

# Generate session ID for per-game log files
session_id = time.strftime('%Y%m%d_%H%M%S')
with open("/tmp/nethack_session_id", "w", encoding="utf-8") as f:
    f.write(session_id)

# Inject past lessons at the top of initial state
past_lessons = memory.load(last_n=5)
if past_lessons:
    state = past_lessons + "\n\n---\n\n" + state

with open("/tmp/nethack_state", "w", encoding="utf-8") as f:
    f.write(state)
open("/tmp/nethack_ready", "w").close()

def _display_live(last_action=None):
    content = env.render_live(last_action=last_action)
    sys.stdout.write('\033[2J\033[H' + content + '\n')
    sys.stdout.flush()

if display_mode:
    _display_live()

def _write_state(state):
    try:
        os.remove("/tmp/nethack_ready")
    except FileNotFoundError:
        pass
    tmp = "/tmp/nethack_state.tmp"
    state = '[PLAY_V3]\n' + state
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(state)
    os.replace(tmp, "/tmp/nethack_state")
    open("/tmp/nethack_ready", "w").close()

def _extract_death_info(state_text, last_live_state=""):
    """Parse gameover state to extract identified items, depth, cause."""
    parsed = state_parser.parse_state(state_text)
    depth, cause = extract_depth_and_cause(state_text, last_live_state)

    # Extract identified items from inventory
    identified = []
    for slot, desc in parsed.inventory.items():
        # Skip gold
        if slot == '$':
            continue
        # Check if item appears identified: contains "potion of", "scroll of", "wand of", "ring of", etc.
        lowered = desc.lower()
        for keyword in ('potion of', 'scroll of', 'wand of', 'ring of', 'spellbook of',
                        'amulet of', 'armor', 'weapon', 'food ration', 'pancake'):
            if keyword in lowered:
                # Extract the name: remove leading articles and quantity
                name = desc.strip()
                # Remove leading "a/an/uncursed/blessed/cursed/2/3..."
                name = re.sub(r'^(\d+\s+)?(an?\s+)?(uncursed|blessed|cursed\s+)?', '', name, count=1, flags=re.IGNORECASE)
                name = name.strip()
                if name:
                    identified.append(name)
                    # Save to local DB
                    category = "unknown"
                    if 'potion' in lowered:
                        category = "potion"
                    elif 'scroll' in lowered:
                        category = "scroll"
                    elif 'wand' in lowered:
                        category = "wand"
                    elif 'ring' in lowered:
                        category = "ring"
                    elif 'armor' in lowered or 'shield' in lowered or 'mail' in lowered:
                        category = "armor"
                    elif 'sword' in lowered or 'dagger' in lowered or 'weapon' in lowered:
                        category = "weapon"
                    elif 'food' in lowered or 'pancake' in lowered or 'ration' in lowered:
                        category = "food"
                    item_db.save_item(name, category, effect="", notes="Identified at death")
                break

    return depth, cause, identified


def _signal_gameover(state, last_live_state=""):
    depth, cause, identified = _extract_death_info(state, last_live_state)
    lessons = []
    if identified:
        lessons.append("Identified items at death: " + ", ".join(identified[:5]))
    memory.save({
        "game_id": session_id,
        "turns": env.turn,
        "depth": depth,
        "cause": cause,
        "lessons": lessons,
    })
    tmp = "/tmp/nethack_gameover.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(state)
    os.replace(tmp, "/tmp/nethack_gameover")

try:
    while True:
        if os.path.exists("/tmp/nethack_action"):
            tmp_action = "/tmp/nethack_action.tmp"
            action_path = "/tmp/nethack_action"
            try:
                os.rename(action_path, tmp_action)
            except FileNotFoundError:
                time.sleep(0.05)
                continue
            with open(tmp_action, "r", encoding="utf-8") as f:
                action = f.read().strip()
            os.remove(tmp_action)

            try:
                item_use = None
                forced = action.startswith("force:")
                if forced:
                    action = action[len("force:"):].strip()
                safety_reason = env.check_action_safety(action)
                if safety_reason and not forced:
                    state = "[SAFETY BLOCK] {}\nUse force:<action> only after explicit risk review.\n{}".format(
                        safety_reason, env.render())
                    _write_state(state)
                    if display_mode:
                        _display_live(action)
                    continue
                for item_action in ("drink", "read", "zap"):
                    prefix = item_action + ":"
                    if action.startswith(prefix):
                        slot = action[len(prefix):].split(":", 1)[0].strip()
                        item_use = (
                            item_action,
                            env._inventory().get(slot, ""),
                            int(env._obs['blstats'][10]),
                        )
                        break
                if action.startswith("keys:"):
                    raw = action[len("keys:"):]
                    keys = []
                    for part in re.split(r'[,\s]+', raw.strip()):
                        if part:
                            keys.append(int(part) if part.isdigit() else part)
                    state = env.send_keys(keys)
                elif action.startswith("goto:"):
                    try:
                        parts = action[len("goto:"):].split(",")
                        tx, ty = int(parts[0].strip()), int(parts[1].strip())
                    except (ValueError, IndexError):
                        state = "[ERROR] goto format: goto:x,y"
                        _write_state(state)
                        continue
                    state, reason = env.navigate_to(tx, ty)
                    state = "[GOTO] stopped: {} at ({},{})\n".format(reason, tx, ty) + state
                elif (action.startswith("search:") or action.startswith("wait:")
                      or action.startswith("safe_wait:")):
                    try:
                        act_name, n_str = action.split(":", 1)
                        if act_name == "safe_wait":
                            act_name = "wait"
                        n = max(1, int(n_str.strip()))
                    except (ValueError, IndexError):
                        state = "[ERROR] format: search:N or wait:N"
                        _write_state(state)
                        continue
                    state, executed, reason = env.repeat_action(act_name, n)
                    state = "[{}:{}] stopped after {} turn(s): {}\n".format(
                        act_name.upper(), n, executed, reason) + state
                elif action.startswith("kick:"):
                    parts = action[len("kick:"):].split(":")
                    direction = parts[0].strip()
                    max_kicks = 1
                    if len(parts) > 1:
                        try:
                            max_kicks = max(1, int(parts[1].strip()))
                        except ValueError:
                            pass
                    kicks = 0
                    last_reason = ""
                    for _ in range(max_kicks):
                        state, reason = env.kick(direction)
                        kicks += 1
                        last_reason = reason
                        msg = bytes(env._obs['message']).decode('utf-8', errors='ignore').strip('\x00').strip()
                        # Stop if door opened (message changes from WHAMMM!!!)
                        if "WHAMMM" not in msg and msg:
                            break
                        if '[GAME OVER]' in state:
                            break
                    state = "[KICK:{}] {} kick(s): {}\n".format(direction, kicks, last_reason) + state
                elif action.startswith("drink:"):
                    slot = action[len("drink:"):].strip()
                    state = env.menu_select('q', slot)
                    state = "[DRINK:{}]\n".format(slot) + state
                elif action.startswith("read:"):
                    slot = action[len("read:"):].strip()
                    state = env.menu_select('r', slot)
                    state = "[READ:{}]\n".format(slot) + state
                elif action.startswith("zap:"):
                    parts = action[len("zap:"):].split(":")
                    if len(parts) != 2:
                        state = "[ERROR] zap format: zap:<slot>:<direction>"
                        _write_state(state)
                        continue
                    slot, direction = parts[0].strip(), parts[1].strip().lower()
                    dir_map = {'north': 'k', 'south': 'j', 'east': 'l', 'west': 'h',
                               'northeast': 'u', 'southeast': 'n', 'southwest': 'b', 'northwest': 'y',
                               'ne': 'u', 'se': 'n', 'sw': 'b', 'nw': 'y',
                               'up': 'k', 'down': 'j', 'left': 'h', 'right': 'l'}
                    dkey = dir_map.get(direction)
                    if not dkey:
                        state = "[ERROR] unknown direction: {}. Use north/south/east/west/ne/se/sw/nw".format(direction)
                        _write_state(state)
                        continue
                    state = env.menu_select('z', slot, trailing=[dkey])
                    state = "[ZAP:{}:{}]\n".format(slot, direction) + state
                elif action.startswith("wield:"):
                    slot = action[len("wield:"):].strip()
                    state = env.menu_select('w', slot)
                    state = "[WIELD:{}]\n".format(slot) + state
                elif action.startswith("wear:"):
                    slot = action[len("wear:"):].strip()
                    state = env.menu_select('W', slot)
                    state = "[WEAR:{}]\n".format(slot) + state
                elif action.startswith("takeoff:"):
                    slot = action[len("takeoff:"):].strip()
                    state = env.menu_select('T', slot)
                    state = "[TAKEOFF:{}]\n".format(slot) + state
                elif action.startswith("drop:"):
                    slot = action[len("drop:"):].strip()
                    state = env.menu_select('d', slot)
                    state = "[DROP:{}]\n".format(slot) + state
                elif action.startswith("puton:"):
                    slot = action[len("puton:"):].strip()
                    state = env.menu_select('P', slot)
                    state = "[PUTON:{}]\n".format(slot) + state
                elif action.startswith("remove:"):
                    slot = action[len("remove:"):].strip()
                    state = env.menu_select('R', slot)
                    state = "[REMOVE:{}]\n".format(slot) + state
                else:
                    state = env.step(action)
            except Exception as e:
                import traceback
                err = traceback.format_exc()
                state = "[CRASH] action={} error={}\n{}\n".format(action, e, err)
                try:
                    state += env.render()
                except Exception:
                    pass

            if item_use and "[CRASH]" not in state:
                observation = env.record_item_use(*item_use)
                if observation:
                    state = "[ITEM OBSERVATION] {}\n{}".format(observation, state)
            _write_state(state)
            if "[GAME OVER]" not in state:
                last_live_state = state
            if display_mode:
                _display_live(action)
            if "[GAME OVER]" in state:
                _signal_gameover(state, last_live_state)
                break
        time.sleep(0.05)
finally:
    env.close()
