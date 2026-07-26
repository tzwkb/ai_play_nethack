# IPC Protocol

`play.py` and the agent communicate via files in `/tmp/`.

## Files

| File | Writer | Purpose |
|------|--------|---------|
| `/tmp/nethack_state` | play.py | current game state (rendered) |
| `/tmp/nethack_ready` | play.py | signals state is ready to read |
| `/tmp/nethack_action` | agent | action to execute |
| `/tmp/nethack_gameover` | play.py | final state on game over |
| `/tmp/nethack_charselect` | play.py | character options (session start) |
| `/tmp/nethack_charselect_response` | agent | chosen character (session start) |

## Recommended: use agent_helper.py (avoids PowerShell quoting hell)

```bash
# In WSL — one command per turn, no escaping needed:
python3 agent_helper.py north
python3 agent_helper.py search
python3 agent_helper.py keys:q,g
python3 agent_helper.py --read          # read state without acting
python3 agent_helper.py --start wiz-hum-mal-neu   # start play.py in tmux
python3 agent_helper.py --gameover      # read gameover state
```

From PowerShell, call into WSL once per turn:
```powershell
wsl -d Ubuntu -- python3 /mnt/c/Users/ASUS/Desktop/ai_play_nethack/nethack_agent_player/agent_helper.py north
```

## Manual turn cycle (Python)

```python
import os, time

def write_action(action: str):
    tmp = "/tmp/nethack_action.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(action)
    os.replace(tmp, "/tmp/nethack_action")  # atomic

def wait_ready(timeout=10):
    start = time.time()
    while not os.path.exists("/tmp/nethack_ready"):
        if time.time() - start > timeout:
            raise TimeoutError("play.py did not respond — process may have crashed")
        time.sleep(0.05)

def read_state() -> str:
    with open("/tmp/nethack_state", encoding="utf-8") as f:
        return f.read()

# Each turn:
write_action("north")
wait_ready()
state = read_state()
```

## CRITICAL: never use Windows echo

`echo "north" > file` writes UTF-16 LE with BOM. `play.py` reads `\xff\xfenorth` and fails silently.
Always use Python `open(..., encoding="utf-8")` or `agent_helper.py`.

## State format

```
Turn N | Dlvl:D | HP:h/H | AC:a | XP:x | Gold:g
Message: <last game message>
   0         1         2    ...   7
   0123456789012345678901234 ...
 1 [row 1 of explored map — accumulated, blank = unexplored]
 2 ...
[rows 1-21, each prefixed with tty row number]
Features:
  Player: (x,y)
  Stairs down(>): [(x,y)] or "not found yet"
  Monsters: sym@(x,y) ...
  Items: sym@(x,y) ...
  Passable moves: north->(x,y)[floor], east->(x,y)[corridor], ...
Inventory (N): a) item ...
```

## Action format

- Named action: `north`, `search`, `descend`, etc.
- Multi-step: `keys:q,g` (quaff item g) — see [multi_step.md](multi_step.md)
- Safe rest: `safe_wait:20` — rechecks HP and hostile distance every turn
- Explicit override: `force:<action>` — bypasses a reported safety block after risk review

