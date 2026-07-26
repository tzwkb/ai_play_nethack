#!/usr/bin/env python3
"""
NetHack Agent Helper — IPC wrapper for the play.py turn loop (runs under any python3).
Wraps the write→wait→read IPC cycle into a single clean call.

Usage:
    python3 agent_helper.py <action>
    python3 agent_helper.py keys:q,g
    python3 agent_helper.py walk:north    # walk until wall or message
    python3 agent_helper.py goto:x,y      # navigate to coordinates
    python3 agent_helper.py drink:f       # quaff potion in slot f
    python3 agent_helper.py read:e        # read scroll in slot e
    python3 agent_helper.py zap:f:north   # zap wand f northward
    python3 agent_helper.py wield:a       # wield weapon in slot a
    python3 agent_helper.py wear:c        # wear armor in slot c
    python3 agent_helper.py takeoff:c     # take off armor in slot c
    python3 agent_helper.py drop:d        # drop item in slot d
    python3 agent_helper.py kick:east     # kick in a direction
    python3 agent_helper.py kick:east:5   # kick up to 5 times (stops if door opens)
    python3 agent_helper.py --read        # just read current state
    python3 agent_helper.py --start <character>  # start play.py in tmux
    python3 agent_helper.py --choose <character> # answer pending character selection

Examples:
    python3 agent_helper.py north
    python3 agent_helper.py search
    python3 agent_helper.py keys:z,f,k
    python3 agent_helper.py walk:east
    python3 agent_helper.py drink:f
    python3 agent_helper.py zap:f:east
    python3 agent_helper.py wield:a
    python3 agent_helper.py kick:east:5
    python3 agent_helper.py --read
    python3 agent_helper.py --start wiz-hum-mal-neu
"""
import sys
import os
import time
import re
import shlex

# Logging
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(SCRIPT_DIR, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

_current_session = None
_current_log_file = None

def _get_log_file() -> str:
    """Return log file path for current session. Creates new file when session changes."""
    global _current_session, _current_log_file
    session_id = ""
    try:
        with open("/tmp/nethack_session_id", "r", encoding="utf-8") as f:
            session_id = f.read().strip()
    except FileNotFoundError:
        session_id = time.strftime('%Y%m%d_%H%M%S')
    if session_id != _current_session:
        _current_session = session_id
        _current_log_file = os.path.join(LOGS_DIR, f"nethack_{session_id}.log")
    return _current_log_file

def log_entry(action: str, state: str):
    """Append a concise entry to the game log for current session."""
    log_file = _get_log_file()
    # Extract key info from state
    lines = state.splitlines()
    header = ""
    msg = ""
    hp = ""
    pos = ""
    for line in lines:
        if line.startswith("Turn "):
            header = line.strip()
        elif line.startswith("Message: "):
            msg = line.replace("Message: ", "").strip()
        elif "HP:" in line and "AC:" in line:
            hp = line.strip()
        elif line.startswith("  Player: ("):
            pos = line.strip()
    entry = f"[{time.strftime('%H:%M:%S')}] ACTION={action} | {header} | {hp} | {pos}"
    if msg:
        entry += f" | MSG=\"{msg}\""
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(entry + "\n")


DIR_DELTAS = {
    'north': (0, -1),
    'south': (0, 1),
    'east': (1, 0),
    'west': (-1, 0),
    'northeast': (1, -1),
    'southeast': (1, 1),
    'southwest': (-1, 1),
    'northwest': (-1, -1),
    'ne': (1, -1),
    'se': (1, 1),
    'sw': (-1, 1),
    'nw': (-1, -1),
}


def parse_player_pos(state: str):
    m = re.search(r'Player:\s*\((\d+),\s*(\d+)\)', state)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


def parse_message(state: str):
    m = re.search(r'Message:\s*(.*)', state)
    if m:
        return m.group(1).strip()
    return ''


# map short aliases to full action names recognized by play.py
DIR_ACTION_NAMES = {
    'north': 'north',
    'south': 'south',
    'east': 'east',
    'west': 'west',
    'northeast': 'northeast',
    'southeast': 'southeast',
    'southwest': 'southwest',
    'northwest': 'northwest',
    'ne': 'northeast',
    'se': 'southeast',
    'sw': 'southwest',
    'nw': 'northwest',
}


def walk_direction(direction: str, max_steps: int = 100, timeout: float = 15.0):
    """Repeatedly move in one direction until wall, message, or game over."""
    direction = direction.lower()
    if direction not in DIR_DELTAS:
        print(f"[ERROR] Unknown direction: {direction}", file=sys.stderr)
        sys.exit(1)
    action_name = DIR_ACTION_NAMES[direction]
    dx, dy = DIR_DELTAS[direction]

    # get starting state
    state = read_state()
    start_pos = parse_player_pos(state)
    if start_pos is None:
        print("[ERROR] Could not parse player position.", file=sys.stderr)
        sys.exit(1)

    steps = 0
    while steps < max_steps:
        # check game over before acting
        if "[GAME OVER]" in state:
            print(state)
            print("\n[GAME OVER detected — run post-game analysis]", file=sys.stderr)
            return

        state = write_action(action_name, timeout=timeout)
        steps += 1

        msg = parse_message(state)
        pos = parse_player_pos(state)

        # stop on wall (position unchanged)
        if pos == start_pos:
            print(f"[WALK] stopped after {steps} step(s): blocked (position unchanged)")
            print(state)
            return

        # stop on any non-empty message
        if msg:
            print(f"[WALK] stopped after {steps} step(s): message='{msg}'")
            print(state)
            return

        start_pos = pos

    print(f"[WALK] stopped after {max_steps} step(s): max_steps reached")
    print(state)

STATE_FILE  = "/tmp/nethack_state"
ACTION_FILE = "/tmp/nethack_action"
READY_FILE  = "/tmp/nethack_ready"
GAMEOVER_FILE = "/tmp/nethack_gameover"
CHARSELECT_FILE = "/tmp/nethack_charselect"
CHARSELECT_RESP = "/tmp/nethack_charselect_response"

PLAY_PY = os.path.join(SCRIPT_DIR, "play.py")


def write_action(action: str, timeout: float = 15.0):
    """Write action atomically and wait for play.py to process it."""
    # remove stale ready signal
    try:
        os.remove(READY_FILE)
    except FileNotFoundError:
        pass

    tmp = ACTION_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(action)
    os.replace(tmp, ACTION_FILE)

    # wait for ready signal
    start = time.time()
    while not os.path.exists(READY_FILE):
        if time.time() - start > timeout:
            print("[TIMEOUT] play.py did not respond. Is it still running?", file=sys.stderr)
            sys.exit(1)
        time.sleep(0.05)

    state = read_state()
    log_entry(action, state)
    return state


def read_state() -> str:
    with open(STATE_FILE, encoding="utf-8") as f:
        return f.read()


def start_game(character: str = None):
    """Start play.py in a tmux session named 'nethack'."""
    for stale in (
        READY_FILE, ACTION_FILE, ACTION_FILE + ".tmp", GAMEOVER_FILE,
        GAMEOVER_FILE + ".tmp", CHARSELECT_FILE, CHARSELECT_FILE + ".tmp",
        CHARSELECT_RESP, CHARSELECT_RESP + ".tmp",
    ):
        try:
            os.remove(stale)
        except FileNotFoundError:
            pass
    bundled_python = os.path.join(SCRIPT_DIR, ".venv", "bin", "python")
    runtime = bundled_python if os.path.exists(bundled_python) else sys.executable
    cmd = "{} {}".format(shlex.quote(runtime), shlex.quote(PLAY_PY))
    if character:
        cmd += " " + shlex.quote(character)
    cmd += " --display"
    tmux_cmd = f"tmux new-session -d -s nethack '{cmd}' 2>/dev/null || tmux kill-session -t nethack && tmux new-session -d -s nethack '{cmd}'"
    os.system(tmux_cmd)
    print(f"Started play.py in tmux session 'nethack' (character={character or 'will prompt'})")

    # if no character given, handle charselect
    if not character:
        print("Waiting for character selection prompt...")
        deadline = time.time() + 30
        while not os.path.exists(CHARSELECT_FILE):
            if time.time() > deadline:
                print("[TIMEOUT] charselect file never appeared.", file=sys.stderr)
                sys.exit(1)
            time.sleep(0.1)
        import json
        with open(CHARSELECT_FILE) as f:
            opts = json.load(f)
        print(json.dumps(opts, ensure_ascii=False, indent=2))
        print("Character selection is pending; choose freely with --choose <character>.")
        return

    # wait for initial state
    deadline = time.time() + 30
    while not os.path.exists(READY_FILE):
        if time.time() > deadline:
            print("[TIMEOUT] Initial state never appeared.", file=sys.stderr)
            sys.exit(1)
        time.sleep(0.1)
    print(read_state())


def choose_character(character: str):
    if not os.path.exists(CHARSELECT_FILE):
        print("[ERROR] No character selection is pending.", file=sys.stderr)
        sys.exit(1)
    tmp = CHARSELECT_RESP + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(character)
    os.replace(tmp, CHARSELECT_RESP)
    deadline = time.time() + 30
    while not os.path.exists(READY_FILE):
        if time.time() > deadline:
            print("[TIMEOUT] Initial state never appeared.", file=sys.stderr)
            sys.exit(1)
        time.sleep(0.1)
    print(read_state())


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)

    if args[0] == "--read":
        print(read_state())
    elif args[0] == "--start":
        character = args[1] if len(args) > 1 else None
        start_game(character)
    elif args[0] == "--choose":
        if len(args) < 2:
            print("[ERROR] --choose requires <role>-<race>-<gender>-<alignment>.", file=sys.stderr)
            sys.exit(1)
        choose_character(args[1])
    elif args[0] == "--gameover":
        if os.path.exists(GAMEOVER_FILE):
            with open(GAMEOVER_FILE) as f:
                print(f.read())
        else:
            print("No gameover file found.")
    elif args[0].startswith("walk:"):
        direction = args[0].split(":", 1)[1]
        walk_direction(direction)
    elif args[0].startswith("goto:"):
        # Handle PowerShell comma-splitting: join remaining args back
        if len(args) == 1:
            action = args[0]
        else:
            action = args[0] + "," + ",".join(args[1:])
        state = write_action(action)
        print(state)
        if "[GAME OVER]" in state:
            print("\n[GAME OVER detected — run post-game analysis]", file=sys.stderr)
    else:
        action = args[0]
        state = write_action(action)
        print(state)
        if "[GAME OVER]" in state:
            print("\n[GAME OVER detected — run post-game analysis]", file=sys.stderr)


if __name__ == "__main__":
    main()
