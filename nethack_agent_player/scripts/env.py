import os
import json
from collections import deque
from datetime import datetime

ACTION_MAP = {
    'north': 0, 'east': 1, 'south': 2, 'west': 3,
    'northeast': 4, 'southeast': 5, 'southwest': 6, 'northwest': 7,
    'ne': 4, 'se': 5, 'sw': 6, 'nw': 7,
    'n': 0, 'e': 1, 's': 2, 'w': 3,
    'wait': 18, 'search': 61, 'descend': 17, 'ascend': 16,
    'pickup': 50, 'eat': 30, 'drink': 53, 'open': 48, 'pray': 51,
}

_TILE_LABEL = {
    '.': 'floor', '#': 'corridor',
    '+': 'DOOR (closed) - move into it to open',
    '-': 'wall or open door — same char in NetHack; use _is_likely_door to tell',
    '|': 'wall or open door — same char in NetHack; use _is_likely_door to tell',
    '<': 'STAIRS UP - use action ascend',
    '>': 'STAIRS DOWN - use action descend',
    '$': 'gold - use pickup', '%': 'food - use pickup then eat',
    '@': 'player', '`': 'boulder', '_': 'altar',
    '{': 'fountain', chr(92): 'throne', '}': 'water/moat', '^': 'trap - avoid',
}

_HUNGER_LABEL = {0: 'Satiated', 1: 'Not Hungry', 2: 'Hungry',
                 3: 'Weak', 4: 'Fainting', 5: 'Starved'}
_ENCUMBRANCE_LABEL = {0: 'Unencumbered', 1: 'Burdened', 2: 'Stressed',
                      3: 'Strained', 4: 'Overtaxed', 5: 'Overloaded'}

BLSTATS = ['x', 'y', 'str_pct', 'str', 'dex', 'con', 'int', 'wis', 'cha',
           'score', 'hp', 'hpmax', 'depth', 'gold', 'energy', 'energymax',
           'ac', 'monster_level', 'xp', 'xplevel', 'time', 'hunger',
           'carrying_cap', 'dungeon_num', 'level_num', 'prop_mask']

_TERRAIN = set('.#|-+<>`_' + chr(92) + '{')
_TRANSIENT = set('@fndxjraBbCcDeEFgGhHiIJkKlLmMNoOpPqQRsStTuUvVwWXyYzZ&;:$%!' + chr(39) + '"()*,/?[]^~')
MONSTER_SYMS = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ&;:')
ITEM_SYMS = set('!"$%' + chr(39) + '()*,/?[' + chr(92) + ']^`{~')

MAP_ROWS = 21
MAP_COLS = 80

DIRS8 = [
    ('north', 0, -1), ('south', 0, 1), ('west', -1, 0), ('east', 1, 0),
    ('northwest', -1, -1), ('northeast', 1, -1),
    ('southwest', -1, 1), ('southeast', 1, 1),
]
DIRS4 = [(-1, 0), (1, 0), (0, -1), (0, 1)]


class NLEEnv:
    def __init__(self, character=None, log_dir=None):
        import gymnasium as gym
        import nle  # noqa: F401
        # allow_all_yn_questions=True: do NOT auto-ESC single-char prompts
        # (getobj "What do you want to wear/wield/quaff?" etc). Without it the
        # env auto-declines item-selection prompts -> "Never mind". --More--
        # pagination is still auto-handled because allow_all_modes stays False.
        kwargs = {'savedir': None, 'allow_all_yn_questions': True}
        if character:
            kwargs['character'] = character
            env_id = 'NetHack-v0'
        else:
            env_id = 'NetHackScore-v0'
        self.env = gym.make(env_id, **kwargs)
        self.log_dir = log_dir
        self.turn = 0
        self.history = []
        self._obs = None
        self.verbose = False
        self._map_cache = [[' '] * MAP_COLS for _ in range(MAP_ROWS)]
        self._prev_hp = None
        self._last_damage = 0
        self._major_hit_until = -1
        self._current_depth = None
        self._known_hazards = {}
        self._item_knowledge = {}

    def set_verbose(self, value):
        self.verbose = value

    def _flush_pending(self, max_presses=20):
        """Press space until no pagination prompt remains (--More--, -more-, etc.)."""
        PAGINATION_MARKERS = ('--More--', '-more-', 'Hit space to continue:', '(end)')
        for _ in range(max_presses):
            if self._obs is None:
                break
            tty = self._obs['tty_chars']
            has_pending = False
            for row in range(24):
                line = ''.join(chr(c) for c in tty[row]).rstrip()
                if any(marker in line for marker in PAGINATION_MARKERS):
                    has_pending = True
                    break
            if not has_pending:
                break
            obs, reward, done, truncated, _ = self.env.step(85)  # space
            self._obs = obs
            self.turn += 1
            if done or truncated:
                break

    def step(self, action_name):
        self._flush_pending()
        action_int = ACTION_MAP.get(action_name.lower())
        if action_int is None:
            return 'Unknown action: {}. Valid: {}'.format(action_name, list(ACTION_MAP))
        obs, reward, done, truncated, info = self.env.step(action_int)
        self._obs = obs
        self.turn += 1
        state = self.render(obs)
        self.history.append({'turn': self.turn, 'action': action_name, 'reward': reward})
        if done or truncated:
            state += '\n\n[GAME OVER] reward={:.1f}'.format(reward)
            if self.log_dir:
                self._save_log(reward)
        if self.verbose:
            print(state)
        return state

    def repeat_action(self, action_name, n):
        """Execute action_name up to n times with a per-turn safety check.
        Returns (final_state, turns_executed, stopped_reason).
        stopped_reason: 'done', 'interrupted', 'unsafe', 'game_over', 'unknown_action'
        """
        if ACTION_MAP.get(action_name.lower()) is None:
            return 'Unknown action: {}'.format(action_name), 0, 'unknown_action'
        executed = 0
        state = self.render()
        for _ in range(n):
            blocked = self.check_action_safety(action_name)
            if blocked:
                return state, executed, 'unsafe: {}'.format(blocked)
            before_hostiles = self._visible_hostiles(self._obs)
            before_hp = int(self._obs['blstats'][10])
            state = self.step(action_name)
            executed += 1
            if '[GAME OVER]' in state:
                return state, executed, 'game_over'
            msg = bytes(self._obs['message']).decode('utf-8', errors='ignore').strip('\x00').strip()
            if msg:
                return state, executed, 'interrupted'
            after_hostiles = self._visible_hostiles(self._obs)
            after_hp = int(self._obs['blstats'][10])
            if after_hp < before_hp:
                return state, executed, 'unsafe: HP decreased'
            if after_hostiles and (
                not before_hostiles
                or min(h['distance'] for h in after_hostiles)
                < min(h['distance'] for h in before_hostiles)
            ):
                return state, executed, 'unsafe: hostile appeared or moved closer'
        return state, executed, 'done'

    def _visible_hostiles(self, obs=None):
        """Return visible non-pet monsters with Chebyshev distance from the player."""
        obs = obs or self._obs
        if obs is None:
            return []
        b = obs['blstats']
        px, py = int(b[0]), int(b[1])
        hostiles = []
        glyphs = obs.get('glyphs')
        try:
            import nle.nethack as nh
        except ImportError:
            nh = None
        if glyphs is not None and nh is not None:
            rows, cols = glyphs.shape
            for y in range(rows):
                for x in range(cols):
                    if x == px and y == py:
                        continue
                    glyph = glyphs[y][x]
                    if not nh.glyph_is_monster(glyph) or nh.glyph_is_pet(glyph):
                        continue
                    symbol = chr(obs['tty_chars'][y + 1][x])
                    monster = nh.permonst(nh.glyph_to_mon(glyph))
                    hostiles.append({
                        'symbol': symbol,
                        'name': monster.mname,
                        'level': int(monster.mlevel),
                        'speed': int(monster.mmove),
                        'difficulty': int(monster.difficulty),
                        'x': x,
                        'y': y + 1,
                        'distance': max(abs(x - px), abs(y - py)),
                    })
            return hostiles
        chars = obs['tty_chars']
        for y in range(MAP_ROWS):
            for x in range(MAP_COLS):
                symbol = chr(chars[y + 1][x])
                if symbol in MONSTER_SYMS and not (x == px and y == py):
                    hostiles.append({
                        'symbol': symbol,
                        'name': self._MONSTER_NAMES.get(symbol, 'monster'),
                        'x': x,
                        'y': y + 1,
                        'distance': max(abs(x - px), abs(y - py)),
                    })
        return hostiles

    def _inventory(self, obs=None):
        obs = obs or self._obs
        result = {}
        if obs is None:
            return result
        for i in range(55):
            item = bytes(obs['inv_strs'][i]).decode(
                'utf-8', errors='ignore').strip('\x00').strip()
            if item:
                letter = chr(obs['inv_letters'][i]) if obs['inv_letters'][i] > 0 else '?'
                result[letter] = item
        return result

    @staticmethod
    def _item_appearance(description):
        text = description.lower().strip()
        prefixes = (
            'an uncursed ', 'a uncursed ', 'an blessed ', 'a blessed ',
            'an cursed ', 'a cursed ', 'uncursed ', 'blessed ', 'cursed ',
            'an ', 'a ',
        )
        for prefix in prefixes:
            if text.startswith(prefix):
                text = text[len(prefix):]
                break
        return text

    def record_item_use(self, action_name, description, hp_before):
        if not description or self._obs is None:
            return ''
        appearance = self._item_appearance(description)
        hp_after = int(self._obs['blstats'][10])
        message = bytes(self._obs['message']).decode(
            'utf-8', errors='ignore').strip('\x00').strip()
        observations = []
        if action_name == 'drink':
            if hp_after > hp_before:
                observations.append('restored {} HP'.format(hp_after - hp_before))
            else:
                observations.append('no immediate HP recovery observed')
        if message:
            observations.append('message: {}'.format(message))
        note = '; '.join(observations) or 'used; no explicit effect observed'
        existing = self._item_knowledge.get(appearance, {'uses': 0, 'notes': []})
        existing['uses'] += 1
        if note not in existing['notes']:
            existing['notes'].append(note)
        self._item_knowledge[appearance] = existing
        return '{} -> {}'.format(appearance, note)

    def _danger_level(self, obs=None):
        obs = obs or self._obs
        if obs is None:
            return 'normal'
        b = obs['blstats']
        hp, hpmax = int(b[10]), int(b[11])
        hostiles = self._visible_hostiles(obs)
        nearest = min((h['distance'] for h in hostiles), default=None)
        if hpmax > 0 and (
            hp / hpmax < 0.25
            or self.turn <= self._major_hit_until
            or (nearest is not None and nearest <= 3 and hp / hpmax < 0.50)
        ):
            return 'critical'
        if hpmax > 0 and (hp / hpmax < 0.50 or nearest is not None):
            return 'caution'
        return 'normal'

    def check_action_safety(self, action):
        """Return a blocking reason for unsafe actions, otherwise an empty string."""
        if self._obs is None:
            return ''
        action = action.strip().lower()
        hostiles = self._visible_hostiles(self._obs)
        if action.startswith(('wait', 'search')) and hostiles:
            nearest = min(h['distance'] for h in hostiles)
            return 'visible hostile at distance {}; reposition first'.format(nearest)
        if self._danger_level(self._obs) != 'critical':
            return ''
        if action.startswith(('wait', 'search', 'pickup', 'eat')):
            return 'critical danger permits only healing, escape, movement, prayer, or combat'
        if action in ('drink', 'read', 'zap'):
            return 'critical item use requires a named slot so its identity can be checked'
        if action.startswith('goto:'):
            try:
                tx, ty = (int(v.strip()) for v in action[5:].split(',', 1))
            except (ValueError, IndexError):
                return 'invalid goto target'
            known_up = self._known_stairs('<')
            if (tx, ty) not in known_up:
                return 'bulk navigation is locked in critical danger unless targeting known upstairs'
        if action.startswith(('drink:', 'read:', 'zap:')):
            slot = action.split(':', 1)[1].strip()
            if ':' in slot:
                slot = slot.split(':', 1)[0]
            item = self._inventory().get(slot, '').lower()
            identified = (
                'potion of ' in item
                or 'scroll of ' in item
                or 'wand of ' in item
            )
            if not identified:
                return 'unidentified consumable is not a reliable critical action'
        return ''

    def _known_stairs(self, symbol):
        result = []
        for y in range(MAP_ROWS):
            for x in range(MAP_COLS):
                if self._map_cache[y][x] == symbol:
                    result.append((x, y + 1))
        return result

    def kick(self, direction):
        """Kick in a direction: send kick command then direction key.
        direction: one of north/south/east/west/northeast/southeast/southwest/northwest
        Returns (final_state, stopped_reason).
        """
        # kick command (ASCII 4 = ^D), then a vi-key direction.
        # NLE actions' str() is just their value, so match the direction by the
        # vi-key ASCII (k/j/h/l/y/u/b/n) rather than 'CompassDirection.N'.
        VIKEY = {'north': 107, 'south': 106, 'east': 108, 'west': 104,
                 'northeast': 117, 'southeast': 110, 'southwest': 98, 'northwest': 121,
                 'ne': 117, 'se': 110, 'sw': 98, 'nw': 121}
        target = VIKEY.get(direction.lower())
        kick_idx = None
        dir_idx = None
        for i, a in enumerate(self.env.unwrapped.actions):
            v = getattr(a, 'value', None)
            if v == 4:   # Command.KICK (^D)
                kick_idx = i
            if target is not None and v == target:
                dir_idx = i
        if kick_idx is None:
            return 'kick not available in this env', 'unknown_action'
        if dir_idx is None:
            return 'unknown direction: {}'.format(direction), 'unknown_action'
        state = self.send_keys([kick_idx, dir_idx])
        if '[GAME OVER]' in state:
            return state, 'game_over'
        msg = bytes(self._obs['message']).decode('utf-8', errors='ignore').strip('\x00').strip()
        return state, 'interrupted' if msg else 'done'

    def navigate_to(self, tx, ty, on_step=None):
        b = self._obs['blstats']
        px, py = int(b[0]), int(b[1])
        depth = int(b[12])
        if (depth, tx, ty - 1) in self._known_hazards:
            return self.render(), 'known_hazard'
        # ty is display_y (1-based), BFS uses cache_row = display_y - 1
        # tx is column (0-based), same in both systems
        target_cache = {(tx, ty - 1)}

        DIR_DELTAS = {
            'north': (0, -1),
            'south': (0, 1),
            'east': (1, 0),
            'west': (-1, 0),
            'northeast': (1, -1),
            'southeast': (1, 1),
            'southwest': (-1, 1),
            'northwest': (-1, -1),
        }

        while True:
            b = self._obs['blstats']
            px, py = int(b[0]), int(b[1])

            # check arrival (compare cache coords)
            if px == tx and py == ty - 1:
                state = self.render()
                return state, 'arrived'

            # compute next step
            path, _ = self._bfs(px, py, target_cache)
            if not path:
                state = self.render()
                return state, 'no_path'

            action = path[0]

            # check for items/traps on the next step (but not at the final target)
            if action in DIR_DELTAS:
                dx, dy = DIR_DELTAS[action]
                nx, ny_cache = px + dx, py + dy
                # skip check if this step lands exactly on the target
                if not (nx == tx and ny_cache == ty - 1):
                    tty_row = ny_cache + 1
                    if 1 <= tty_row <= 21 and 0 <= nx < MAP_COLS:
                        ch = chr(self._obs['tty_chars'][tty_row][nx])
                        if ch in ITEM_SYMS:
                            state = self.render()
                            return state, 'item_on_path'

            # execute one step
            state = self.step(action)

            if on_step:
                on_step(state)

            if '[GAME OVER]' in state:
                return state, 'game_over'

            # check for any message — stop and let AI decide
            msg = bytes(self._obs['message']).decode('utf-8', errors='ignore').strip('\x00').strip()
            if msg:
                return state, 'interrupted'

    def _char_to_idx(self, char):
        target = ord(char) if isinstance(char, str) else char
        for i, a in enumerate(self.env.unwrapped.actions):
            if hasattr(a, 'value') and a.value == target:
                return i
        return None

    def send_keys(self, keys):
        self._flush_pending()
        obs = reward = done = truncated = None
        for key in keys:
            if isinstance(key, str):
                idx = self._char_to_idx(key)
                if idx is None:
                    return '[ERROR] key not in NLE action space: {}'.format(key)
                key = idx
            elif isinstance(key, int) and key >= self.env.action_space.n:
                return '[ERROR] Action index {} out of range.'.format(key)
            obs, reward, done, truncated, _ = self.env.step(key)
            self.turn += 1
            self.history.append({'turn': self.turn, 'action': 'key:{}'.format(key), 'reward': reward})
            if done or truncated:
                break
        self._obs = obs
        state = self.render(obs)
        if done or truncated:
            state += '\n\n[GAME OVER] reward={:.1f}'.format(reward)
            if self.log_dir:
                self._save_log(reward)
        if self.verbose:
            print(state)
        return state

    # Full symbol translation table
    _MONSTER_NAMES = {'a': 'ant/other insect', 'b': 'bat', 'c': 'centipede', 'd': 'dog/canine', 'e': 'eye/sphere', 'f': 'cat/feline', 'g': 'gremlin', 'h': 'humanoid', 'i': 'imp/minor demon', 'j': 'jelly', 'k': 'kobold', 'l': 'leprechaun', 'm': 'mimic', 'n': 'nymph', 'o': 'orc', 'p': 'piercer', 'q': 'quadruped', 'r': 'rodent', 's': 'spider/arachnid', 't': 'trapper/lurker', 'u': 'unicorn', 'v': 'vortex', 'w': 'worm', 'x': 'xan/other insect', 'y': 'yellow light', 'z': 'zombie', 'A': 'angel', 'B': 'bat (large)', 'C': 'centaur', 'D': 'dragon', 'E': 'elemental', 'F': 'freezing sphere', 'G': 'gnome', 'H': 'giant humanoid', 'I': 'invisible stalker', 'J': 'jellyfish', 'K': 'ki-rin', 'L': 'lich', 'M': 'mummy', 'N': 'naga', 'O': 'ogre', 'P': 'pudding/ooze', 'Q': 'quantum mechanic', 'R': 'rust monster', 'S': 'snake', 'T': 'troll', 'U': 'umber hulk', 'V': 'vampire', 'W': 'wraith', 'X': 'xorn', 'Y': 'yeti', 'Z': 'zombie (large)', '&': 'demon', ';': 'sea monster', ':': 'lizard'}
    _ITEM_NAMES = {'!': 'potion (use drink)', '?': 'scroll (use read)', '/': 'wand (use zap)', '=': 'ring (use put on)', '"': 'amulet (use put on)', '[': 'armor (use wear)', ')': 'weapon (use wield)', '(': 'tool/misc item', '*': 'gem/rock', ',': 'food item (use eat)', '+': 'spellbook (use read)', '$': 'gold (use pickup)', '%': 'food (use pickup then eat)', '`': 'boulder/statue', '{': 'fountain', '^': 'trap - avoid', '_': 'altar'}

    def _symbol_legend(self, obs):
        chars = obs['tty_chars']
        b = obs['blstats']
        px, py = int(b[0]), int(b[1])
        seen = {}
        for r in range(1, 22):
            for c in range(MAP_COLS):
                ch = chr(chars[r][c])
                if ch in MONSTER_SYMS and ch not in seen:
                    seen[ch] = '{} = {} (MONSTER - fight by moving into it or flee)'.format(ch, self._MONSTER_NAMES.get(ch, 'monster'))
                elif ch in ITEM_SYMS and ch not in seen:
                    seen[ch] = '{} = {} (use pickup)'.format(ch, self._ITEM_NAMES.get(ch, 'item'))
                elif ch in _TILE_LABEL and ch not in ('.', '#', ' ', '@') and ch not in seen:
                    seen[ch] = '{} = {}'.format(ch, _TILE_LABEL[ch])
        if not seen:
            return ''
        return 'Symbol legend:\n  ' + '\n  '.join(seen.values())

    # Map cache

    def _update_map_cache(self, obs):
        chars = obs['tty_chars']
        b = obs['blstats']
        px, py = int(b[0]), int(b[1])
        depth = int(b[12])
        # Clear cache on level change to avoid cross-level stale data
        if self._current_depth is not None and depth != self._current_depth:
            self._map_cache = [[' '] * MAP_COLS for _ in range(MAP_ROWS)]
        self._current_depth = depth
        message = bytes(obs['message']).decode(
            'utf-8', errors='ignore').strip('\x00').strip().lower()
        trap_names = {
            'rolling boulder trap': 'rolling boulder trap',
            'pit': 'pit',
            'bear trap': 'bear trap',
            'arrow trap': 'arrow trap',
            'dart trap': 'dart trap',
            'falling rock trap': 'falling rock trap',
            'sleeping gas trap': 'sleeping gas trap',
            'rust trap': 'rust trap',
            'fire trap': 'fire trap',
            'teleportation trap': 'teleportation trap',
            'level teleporter': 'level teleporter',
            'magic trap': 'magic trap',
        }
        if 'trap' in message or 'you fall into a pit' in message:
            for marker, name in trap_names.items():
                if marker in message:
                    self._known_hazards[(depth, px, py)] = name
                    break
        for r in range(MAP_ROWS):
            for c in range(MAP_COLS):
                ch = chr(chars[r + 1][c])
                if ch in _TERRAIN:
                    self._map_cache[r][c] = ch
        cr = py
        if 0 <= cr < MAP_ROWS and 0 <= px < MAP_COLS:
            self._map_cache[cr][px] = '.'
        # Fill in floor under visible monsters/items so they don't appear as unexplored gaps
        for r in range(MAP_ROWS):
            for c in range(MAP_COLS):
                ch = chr(chars[r + 1][c])
                if ch in MONSTER_SYMS or ch in ITEM_SYMS:
                    if self._map_cache[r][c] == ' ':
                        self._map_cache[r][c] = '.'
    def _render_map_cache(self, obs):
        chars = obs['tty_chars']
        rows = []
        for r in range(MAP_ROWS):
            row = list(self._map_cache[r])
            for c in range(MAP_COLS):
                ch = chr(chars[r + 1][c])
                if ch in _TRANSIENT:
                    row[c] = ch
            rows.append('{:2d} {}'.format(r + 1, ''.join(row)))
        ruler_tens = '   ' + ''.join(str(c // 10) if c % 10 == 0 else ' ' for c in range(MAP_COLS))
        ruler_ones = '   ' + ''.join(str(c % 10) for c in range(MAP_COLS))
        return ruler_tens + '\n' + ruler_ones + '\n' + '\n'.join(rows)

    # BFS pathfinding

    def _bfs(self, sx, sy, targets):
        WALKABLE = set('.#<>+|-$%`_' + chr(92) + '{') | MONSTER_SYMS | ITEM_SYMS
        CORNER_PASSABLE = set('.#<>_$%`{' + chr(92)) | ITEM_SYMS
        visited = {(sx, sy)}
        q = deque([(sx, sy, [])])
        while q:
            cx, cr, path = q.popleft()
            if (cx, cr) in targets:
                return path, (cx, cr)
            for name, dx, dy in DIRS8:
                nx, nr = cx + dx, cr + dy
                if (nx, nr) in visited:
                    continue
                if not (0 <= nr < MAP_ROWS and 0 <= nx < MAP_COLS):
                    continue
                depth = int(self._obs['blstats'][12]) if self._obs is not None else self._current_depth
                if (depth, nx, nr) in self._known_hazards:
                    continue
                # Diagonal corner check: both orthogonal neighbors must be passable
                if dx != 0 and dy != 0:
                    tty = self._obs.get('tty_chars') if self._obs else None
                    c1 = chr(tty[cr + 1][cx + dx]) if tty is not None and 0 <= cx + dx < MAP_COLS else ' '
                    c2 = chr(tty[cr + dy + 1][cx]) if tty is not None and 0 <= cr + dy < MAP_ROWS else ' '
                    c1_ok = c1 in CORNER_PASSABLE or (c1 in '-|' and self._is_definitely_door(cx + dx, cr))
                    c2_ok = c2 in CORNER_PASSABLE or (c2 in '-|' and self._is_definitely_door(cx, cr + dy))
                    if not (c1_ok and c2_ok):
                        continue
                ch = self._map_cache[nr][nx]
                # targets are reachable even if unexplored (' ')
                if ch not in WALKABLE and ch != ' ':
                    continue
                if ch == ' ' and (nx, nr) not in targets:
                    continue  # don't path through unexplored unless it's the goal
                visited.add((nx, nr))
                q.append((nx, nr, path + [name]))
        return None, None

    # Room analysis

    def _is_likely_door(self, x, y):
        """Heuristic: a '-' door has wall-like north+south and connects walkable west+east.
        A '|' door has wall-like west+east and connects walkable north+south.
        This is used for passable-neighbor / room-exit checks (allows corridor connections)."""
        if not (0 <= y < MAP_ROWS and 0 <= x < MAP_COLS):
            return False
        ch = self._map_cache[y][x]
        PASSABLE = set('.#<>_`{' + chr(92))
        WALL_LIKE = set('|-#')
        if ch == '-':
            north = self._map_cache[y - 1][x] if y > 0 else ' '
            south = self._map_cache[y + 1][x] if y < MAP_ROWS - 1 else ' '
            west = self._map_cache[y][x - 1] if x > 0 else ' '
            east = self._map_cache[y][x + 1] if x < MAP_COLS - 1 else ' '
            if not (north in WALL_LIKE and south in WALL_LIKE):
                return False
            if west not in PASSABLE and east not in PASSABLE:
                return False
            if west == ' ' and east == ' ':
                return False
            return True
        elif ch == '|':
            west = self._map_cache[y][x - 1] if x > 0 else ' '
            east = self._map_cache[y][x + 1] if x < MAP_COLS - 1 else ' '
            north = self._map_cache[y - 1][x] if y > 0 else ' '
            south = self._map_cache[y + 1][x] if y < MAP_ROWS - 1 else ' '
            if not (west in WALL_LIKE and east in WALL_LIKE):
                return False
            if north not in PASSABLE and south not in PASSABLE:
                return False
            if north == ' ' and south == ' ':
                return False
            return True
        return False

    def _is_definitely_door(self, x, y):
        """Stricter check for global scanning: exclude wall corners (--- or ||| junctions)."""
        if not self._is_likely_door(x, y):
            return False
        ch = self._map_cache[y][x]
        if ch == '-':
            north = self._map_cache[y - 1][x] if y > 0 else ' '
            south = self._map_cache[y + 1][x] if y < MAP_ROWS - 1 else ' '
            # If north or south is another '-', it's a horizontal wall segment, not a door
            if north == '-' or south == '-':
                return False
        elif ch == '|':
            west = self._map_cache[y][x - 1] if x > 0 else ' '
            east = self._map_cache[y][x + 1] if x < MAP_COLS - 1 else ' '
            # If west or east is another '|', it's a vertical wall segment, not a door
            if west == '|' or east == '|':
                return False
        return True

    def _room_exits(self, px, py, obs=None):
        FLOOR = set('.<>_`{' + chr(92))
        cr0 = py
        if not (0 <= cr0 < MAP_ROWS and 0 <= px < MAP_COLS):
            return None
        if self._map_cache[cr0][px] not in FLOOR:
            return None
        room = set()
        stack = [(px, cr0)]
        while stack:
            cx, cr = stack.pop()
            if (cx, cr) in room or not (0 <= cr < MAP_ROWS and 0 <= cx < MAP_COLS):
                continue
            if self._map_cache[cr][cx] not in FLOOR:
                continue
            room.add((cx, cr))
            for dx, dy in DIRS4:
                stack.append((cx + dx, cr + dy))
        corridors, doors, open_doors, gaps = set(), set(), set(), set()
        for cx, cr in room:
            for dx, dy in DIRS4:
                nx, nr = cx + dx, cr + dy
                if not (0 <= nr < MAP_ROWS and 0 <= nx < MAP_COLS):
                    continue
                ch = self._map_cache[nr][nx]
                coord = (nx, nr + 1)
                if ch == '#':
                    corridors.add(coord)
                elif ch == '+':
                    doors.add(coord)
                elif ch in '|-':
                    if not self._is_definitely_door(nx, nr):
                        continue  # definitely wall, not a door
                    # Could be open door — check beyond to distinguish open vs unexplored
                    ex, er = nx + dx, nr + dy
                    if 0 <= er < MAP_ROWS and 0 <= ex < MAP_COLS:
                        beyond = self._map_cache[er][ex]
                        if beyond == ' ':
                            gaps.add(coord)
                        elif beyond in set('.#<>_`{' + chr(92)):
                            open_doors.add(coord)  # open door leading somewhere
                elif ch == ' ':
                    # If we can see this tile and it's not actually empty, don't treat as gap
                    if obs is not None:
                        tty_ch = chr(obs['tty_chars'][nr + 1][nx])
                        if tty_ch != ' ':
                            continue
                    gaps.add(coord)  # truly unexplored area adjacent to room
        return {'corridors': sorted(corridors), 'doors': sorted(doors), 'open_doors': sorted(open_doors), 'unexplored_gaps': sorted(gaps)}

    def _passable_neighbors(self, px, py, obs):
        PASSABLE = set('.#<>+$%`_' + chr(92) + '{') | MONSTER_SYMS | ITEM_SYMS
        CORNER_PASSABLE = set('.#<>_$%`{' + chr(92)) | ITEM_SYMS
        chars = obs['tty_chars']
        passable, unexplored = [], []
        for name, dx, dy in DIRS8:
            nx, ny = px + dx, py + dy
            tty_row = ny + 1
            if 1 <= tty_row <= 21 and 0 <= nx < MAP_COLS:
                # Diagonal corner check: both orthogonal neighbors must be passable
                if dx != 0 and dy != 0:
                    c1_tty = chr(chars[py + 1][px + dx]) if 0 <= px + dx < MAP_COLS else ' '
                    c2_tty = chr(chars[ny + 1][px]) if 1 <= ny + 1 <= 21 and 0 <= px < MAP_COLS else ' '
                    # Use map_cache for terrain, tty for monsters/items
                    c1 = c1_tty if c1_tty in MONSTER_SYMS or c1_tty in ITEM_SYMS else (self._map_cache[py][px + dx] if 0 <= px + dx < MAP_COLS else ' ')
                    c2 = c2_tty if c2_tty in MONSTER_SYMS or c2_tty in ITEM_SYMS else (self._map_cache[ny][px] if 0 <= ny < MAP_ROWS and 0 <= px < MAP_COLS else ' ')
                    c1_ok = c1 in CORNER_PASSABLE or (c1 in '-|' and self._is_definitely_door(px + dx, py))
                    c2_ok = c2 in CORNER_PASSABLE or (c2 in '-|' and self._is_definitely_door(px, py + dy))
                    if not (c1_ok and c2_ok):
                        continue
                # Target cell: prefer map_cache for terrain, tty for transient monsters/items
                ch_tty = chr(chars[tty_row][nx])
                ch = ch_tty if ch_tty in MONSTER_SYMS or ch_tty in ITEM_SYMS else self._map_cache[ny][nx]
                if ch in PASSABLE:
                    passable.append((name, nx, ny + 1, ch))
                elif ch in '|-':
                    if self._is_definitely_door(nx, ny):
                        passable.append((name, nx, ny + 1, ch))
                    else:
                        # wall, not passable
                        pass
                elif ch == ' ':
                    unexplored.append((name, nx, ny + 1))
        return passable, unexplored

    # Status helpers

    def _status_warnings(self, obs):
        b = obs['blstats']
        hp, hpmax = int(b[10]), int(b[11])
        hunger = int(b[21])
        encumbrance = int(b[22]) if len(b) > 22 else 0
        warnings = []
        if hpmax > 0:
            pct = hp / hpmax
            if pct < 0.25:
                warnings.append('WARNING: CRITICAL HP ({}/{}) - flee or heal immediately'.format(hp, hpmax))
            elif pct < 0.5:
                warnings.append('WARNING: Low HP ({}/{}) - consider retreating'.format(hp, hpmax))
        if hunger >= 2:
            warnings.append('WARNING: {} - eat food now'.format(_HUNGER_LABEL.get(hunger, 'hungry')))
        if encumbrance >= 2:
            warnings.append('WARNING: {} - drop items'.format(_ENCUMBRANCE_LABEL.get(encumbrance, 'encumbered')))
        self._last_damage = 0
        if self._prev_hp is not None and hp < self._prev_hp:
            self._last_damage = self._prev_hp - hp
            warnings.append('WARNING: Took {} damage this turn'.format(self._last_damage))
            if hpmax > 0 and self._last_damage >= max(1, int(hpmax * 0.20)):
                self._major_hit_until = max(self._major_hit_until, self.turn + 3)
        self._prev_hp = hp
        return warnings

    # Priority advisor

    def _priority(self, obs, stairs_down, stairs_up, monsters, items, unexplored_doors=None):
        b = obs['blstats']
        hp, hpmax = int(b[10]), int(b[11])
        hunger = int(b[21])
        px, py = int(b[0]), int(b[1])
        # Hard constraints: survival
        if self._danger_level(obs) == 'critical':
            hostiles = self._visible_hostiles(obs)
            threat = 'none visible'
            if hostiles:
                nearest = min(hostiles, key=lambda h: h['distance'])
                threat = '{} [{}]@({},{}) distance={}'.format(
                    nearest.get('name', 'monster'), nearest['symbol'],
                    nearest['x'], nearest['y'], nearest['distance'])
            inventory = self._inventory(obs)
            resources = []
            for slot, item in inventory.items():
                lowered = item.lower()
                if any(name in lowered for name in (
                    'potion of healing', 'potion of extra healing',
                    'potion of full healing', 'scroll of teleportation',
                )):
                    resources.append('{}={}'.format(slot, item))
            safe_moves = []
            for name, nx, ny, ch in self._passable_neighbors(px, py, obs)[0]:
                if ch in MONSTER_SYMS:
                    continue
                if (int(b[12]), nx, ny - 1) in self._known_hazards:
                    continue
                if hostiles:
                    old_dist = min(h['distance'] for h in hostiles)
                    new_dist = min(max(abs(nx - h['x']), abs(ny - h['y'])) for h in hostiles)
                    if new_dist <= old_dist:
                        continue
                safe_moves.append(name)
            parts = [
                'SITUATION: CRITICAL DANGER HP {}/{}; nearest hostile: {}'.format(
                    hp, hpmax, threat),
                'SAFE MOVES: {}'.format(', '.join(safe_moves) if safe_moves else 'none confirmed'),
                'KNOWN RESOURCES: {}'.format('; '.join(resources) if resources else 'none identified'),
            ]
            if stairs_up:
                parts.append('RETREAT TARGET: upstairs {}'.format(stairs_up[0]))
            parts.append('FORBIDDEN: wait/search/loot/eat/unknown consumables/unplanned exploration')
            return ' | '.join(parts)
        if hunger >= 3:
            food = [i for i in items if '%' in i]
            if food:
                coord = food[0].split('@')[1].strip().strip('()').split(',')
                try:
                    fx, fy = int(coord[0].strip()), int(coord[1].strip())
                    return 'SITUATION: Starving. Food visible. ACTION: goto:{},{}'.format(fx, fy)
                except Exception:
                    return 'SITUATION: Starving. Food visible at {}. Use pickup then eat.'.format(food[0])
            return 'SITUATION: Starving. Check inventory for food (eat action).'
        # Navigation suggestions with explicit goto commands
        exits = self._room_exits(px, py, obs)
        if stairs_down:
            stairs_cache = {(c, r - 1) for c, r in stairs_down}
            path, dest_cr = self._bfs(px, py + 1, stairs_cache)
            dest = (dest_cr[0], dest_cr[1] + 1) if dest_cr else stairs_down[0]
            if path:
                return 'SITUATION: Stairs down at {}. ACTION: goto:{},{}'.format(dest, dest[0], dest[1])
            return 'SITUATION: Stairs down at {} but no clear path. Explore corridors first.'.format(stairs_down[0])
        # Global unexplored open doors take priority over local room exits
        if unexplored_doors:
            t = unexplored_doors[0][0]
            return 'SITUATION: No stairs found. Unexplored door at {}. ACTION: goto:{},{}'.format(t, t[0], t[1])
        # No stairs yet - suggest exploration target
        if exits is None:
            hints = ['No stairs found, in corridor']
            if monsters:
                hints.append('{} monster(s) nearby'.format(len(monsters)))
            return 'SITUATION: {}. Explore to find rooms or stairs.'.format('. '.join(hints))
        if exits.get('unexplored_gaps'):
            t = exits.get('unexplored_gaps', [[]])[0]
            return 'SITUATION: No stairs found. Unexplored exit at {}. ACTION: goto:{},{}'.format(t, t[0], t[1])
        if exits.get('corridors'):
            t = exits.get('corridors', [[]])[0]
            return 'SITUATION: No stairs found. Corridor at {}. ACTION: goto:{},{}'.format(t, t[0], t[1])
        if exits.get('open_doors'):
            t = exits.get('open_doors', [[]])[0]
            return 'SITUATION: No stairs found. Open door at {}. ACTION: goto:{},{}'.format(t, t[0], t[1])
        if exits.get('doors'):
            t = exits.get('doors', [[]])[0]
            return 'SITUATION: No stairs found. Closed door at {}. ACTION: goto:{},{}'.format(t, t[0], t[1])
        hints = ['No stairs found, no obvious exits']
        if monsters:
            hints.append('{} monster(s) nearby'.format(len(monsters)))
        return 'SITUATION: {}. Use search near walls to find hidden doors.'.format('. '.join(hints))

    # Features

    def _map_features(self, obs):
        chars = obs['tty_chars']
        b = obs['blstats']
        px, py = int(b[0]), int(b[1])
        stairs_down, stairs_up, doors, monsters, items = [], [], [], [], []
        for r in range(MAP_ROWS):
            for c in range(MAP_COLS):
                ch = self._map_cache[r][c]
                coord = (c, r + 1)
                if ch == '>':
                    stairs_down.append(coord)
                elif ch == '<':
                    stairs_up.append(coord)
                elif ch == '+':
                    doors.append(coord)
        # Scan for open doors (-/|) that lead to unexplored areas
        unexplored_doors = []
        for r in range(MAP_ROWS):
            for c in range(MAP_COLS):
                ch = self._map_cache[r][c]
                if ch in '|-' and self._is_definitely_door(c, r):
                    for dx, dy, name in [(-1, 0, 'west'), (1, 0, 'east'), (0, -1, 'north'), (0, 1, 'south')]:
                        nx, ny = c + dx, r + dy
                        if 0 <= ny < MAP_ROWS and 0 <= nx < MAP_COLS:
                            if self._map_cache[ny][nx] == ' ':
                                unexplored_doors.append(((c, r + 1), name))
                                break
        for r in range(1, 22):
            for c in range(MAP_COLS):
                ch = chr(chars[r][c])
                coord = (c, r)
                if ch in MONSTER_SYMS:
                    monsters.append('{}@{}'.format(ch, coord))
                elif ch in ITEM_SYMS:
                    items.append('{}@{}'.format(ch, coord))
        lines = []
        for w in self._status_warnings(obs):
            lines.append(w)
        lines.append(self._priority(obs, stairs_down, stairs_up, monsters, items, unexplored_doors))
        lines.append('')
        cr = py
        terrain = ''
        if 0 <= cr < MAP_ROWS and 0 <= px < MAP_COLS:
            ch = self._map_cache[cr][px]
            terrain = 'corridor' if ch == '#' else 'room floor' if ch == '.' else ch
        lines.append('Player: ({},{}) on {}'.format(px, py + 1, terrain))
        lines.append('Stairs down(>): {}'.format(stairs_down if stairs_down else 'not found yet - keep exploring'))
        if stairs_up:
            lines.append('Stairs up(<): {}'.format(stairs_up))
        depth = int(b[12])
        hazards = [
            '({},{})={}'.format(x, y + 1, name)
            for (d, x, y), name in self._known_hazards.items()
            if d == depth
        ]
        if hazards:
            lines.append('Known hazards (AVOID): {}'.format(', '.join(hazards)))
        if monsters:
            lines.append('Monsters visible: {}'.format(' '.join(monsters)))
        hostiles = self._visible_hostiles(obs)
        if hostiles:
            lines.append('Hostile threats: {}'.format(' '.join(
                '{}@({},{}) dist={} lvl={} speed={} difficulty={}'.format(
                    h.get('name', h['symbol']), h['x'], h['y'], h['distance'],
                    h.get('level', '?'), h.get('speed', '?'), h.get('difficulty', '?'))
                for h in hostiles
            )))
        if items:
            lines.append('Items on floor: {}'.format(' '.join(items)))
        if self._item_knowledge:
            observations = []
            for appearance, knowledge in self._item_knowledge.items():
                observations.append('{} (uses={}): {}'.format(
                    appearance, knowledge['uses'], ' | '.join(knowledge['notes'][-2:])))
            lines.append('Session item observations: {}'.format('; '.join(observations)))
        passable, unexplored = self._passable_neighbors(px, py, obs)
        if passable:
            nb_strs = []
            for name, nx, ny, ch in passable:
                hazard = self._known_hazards.get((int(b[12]), nx, ny - 1))
                if hazard:
                    label = 'KNOWN HAZARD: {} - AVOID'.format(hazard)
                elif ch in _TILE_LABEL:
                    label = _TILE_LABEL[ch]
                elif ch in MONSTER_SYMS:
                    label = 'MONSTER({}) {}'.format(ch, NLEEnv._MONSTER_NAMES.get(ch, ''))
                elif ch in ITEM_SYMS:
                    label = 'item({}) {}'.format(ch, NLEEnv._ITEM_NAMES.get(ch, ''))
                else:
                    label = ch
                nb_strs.append('{}->({},{})[{}]'.format(name, nx, ny, label))
            lines.append('Passable moves: {}'.format(', '.join(nb_strs)))
        else:
            lines.append('Passable moves: none (surrounded or unexplored)')
        if unexplored:
            lines.append('Unexplored neighbors: {}'.format(
                ', '.join('{}->({},{})'.format(n, nx, ny) for n, nx, ny in unexplored)))
        exits = self._room_exits(px, py, obs)
        if exits:
            if exits.get('corridors'):
                lines.append('Room exits - corridors: {}'.format(exits['corridors']))
            if exits.get('doors'):
                door_details = []
                for x, y in exits['doors']:
                    ch = self._map_cache[y - 1][x] if 0 <= y - 1 < MAP_ROWS and 0 <= x < MAP_COLS else '?'
                    n = self._map_cache[y - 2][x] if 0 <= y - 2 < MAP_ROWS and 0 <= x < MAP_COLS else '?'
                    s = self._map_cache[y][x] if 0 <= y < MAP_ROWS and 0 <= x < MAP_COLS else '?'
                    w = self._map_cache[y - 1][x - 1] if 0 <= y - 1 < MAP_ROWS and x > 0 else '?'
                    e = self._map_cache[y - 1][x + 1] if 0 <= y - 1 < MAP_ROWS and x < MAP_COLS - 1 else '?'
                    door_details.append("({}, {}) ch='{}' N='{}' S='{}' W='{}' E='{}'".format(x, y, ch, n, s, w, e))
                lines.append('Room exits - closed doors (move into to open): {}'.format(', '.join(door_details)))
            if exits.get('open_doors'):
                od_details = []
                for x, y in exits['open_doors']:
                    ch = self._map_cache[y - 1][x] if 0 <= y - 1 < MAP_ROWS and 0 <= x < MAP_COLS else '?'
                    n = self._map_cache[y - 2][x] if 0 <= y - 2 < MAP_ROWS and 0 <= x < MAP_COLS else '?'
                    s = self._map_cache[y][x] if 0 <= y < MAP_ROWS and 0 <= x < MAP_COLS else '?'
                    w = self._map_cache[y - 1][x - 1] if 0 <= y - 1 < MAP_ROWS and x > 0 else '?'
                    e = self._map_cache[y - 1][x + 1] if 0 <= y - 1 < MAP_ROWS and x < MAP_COLS - 1 else '?'
                    od_details.append("({}, {}) ch='{}' N='{}' S='{}' W='{}' E='{}'".format(x, y, ch, n, s, w, e))
                lines.append('Room exits - open doors (walk through): {}'.format(', '.join(od_details)))
            if exits['unexplored_gaps']:
                lines.append('Room exits - unexplored gaps (go here!): {}'.format(exits['unexplored_gaps']))
            if not any(exits.values()):
                lines.append('Room exits: none found - try search near walls')
        # Summarize explored-but-distant points of interest from map_cache
        far_stairs_down, far_stairs_up, far_doors, far_corridors = [], [], [], []
        for r in range(MAP_ROWS):
            for c in range(MAP_COLS):
                ch = self._map_cache[r][c]
                coord = (c, r + 1)
                dist = abs(c - px) + abs(r - py)
                if dist < 3:
                    continue  # already covered by passable/exits
                if ch == '>':
                    far_stairs_down.append(coord)
                elif ch == '<':
                    far_stairs_up.append(coord)
                elif ch == '+':
                    far_doors.append(coord)
                elif ch == '#':
                    far_corridors.append(coord)
        if far_stairs_down:
            lines.append('Explored map - stairs down(>) at: {}'.format(far_stairs_down))
        if far_stairs_up:
            lines.append('Explored map - stairs up(<) at: {}'.format(far_stairs_up))
        if far_doors:
            lines.append('Explored map - doors(+) at: {}'.format(far_doors[:10]))
        if far_corridors:
            lines.append('Explored map - {} corridor tiles known (use map to navigate)'.format(len(far_corridors)))
        if unexplored_doors:
            lines.append('Known unexplored open doors (GO HERE): {}'.format(
                ', '.join('{}->{}'.format(coord, direction) for coord, direction in unexplored_doors[:5])))
        # Summarize known map features far from player
        far_stairs_down, far_stairs_up, far_doors, far_open_doors = [], [], [], []
        for r in range(MAP_ROWS):
            for c in range(MAP_COLS):
                ch = self._map_cache[r][c]
                if ch == ' ':
                    continue
                coord = (c, r + 1)
                dist = abs(c - px) + abs(r - py)
                if dist < 3:
                    continue  # already covered by passable/exits
                if ch == '>':
                    far_stairs_down.append(coord)
                elif ch == '<':
                    far_stairs_up.append(coord)
                elif ch == '+':
                    far_doors.append(coord)
                elif ch in '|-' and self._is_likely_door(c, r):
                    far_open_doors.append(coord)
        if far_stairs_down:
            lines.append('Known stairs down (elsewhere on map): {}'.format(far_stairs_down))
        if far_stairs_up:
            lines.append('Known stairs up (elsewhere on map): {}'.format(far_stairs_up))
        if far_doors:
            lines.append('Known closed doors (elsewhere on map): {}'.format(far_doors[:5]))
        if far_open_doors:
            lines.append('Known open doors (elsewhere on map): {}'.format(far_open_doors[:5]))
        legend = self._symbol_legend(obs)
        if legend:
            lines.append('')
            lines.append(legend)
        return '[ENV_V9] Features:\n  ' + '\n  '.join(lines)

    # Render

    def _active_prompt(self, obs):
        """Surface a getobj/menu/yn/direction prompt that obs['message'] does NOT
        capture (these live in tty rows 0-2, message buffer is often empty)."""
        tty = obs['tty_chars']
        markers = ('--More--', '-more-', '(end)', 'Hit space to continue')
        promptish = ('What do you want', 'In what direction', 'what direction',
                     'Really', '[yn', '[ynq', 'Pick up what', 'pick it up?', 'Continue?',
                     ' or ?]', '? [', 'Force its lock', 'For what do you wish',
                     'loot it?', 'Loot ', 'Take out', 'Put in')
        out = []
        for r in range(4):
            line = ''.join(chr(c) for c in tty[r]).rstrip()
            if any(m in line for m in markers) or any(p in line for p in promptish):
                s = line.strip()
                if s and s not in out:
                    out.append(s)
        return ' | '.join(out)

    def menu_select(self, cmd_key, slot, trailing=None):
        """Robustly drive a getobj command (W/q/r/w/T/P/R/d/z...).
        Press cmd_key; if a 'What do you want to..?' prompt appears, answer with
        `slot`; otherwise the command auto-selected the only candidate (NetHack
        skips the prompt when exactly one item qualifies) so we must NOT send slot
        (it would cascade into a stray command). Then send any `trailing` keys
        (e.g. a direction for zap)."""
        self._flush_pending()
        def _do(k):
            i = self._char_to_idx(k) if isinstance(k, str) else k
            if i is None:
                return None, '[ERROR] key not in NLE action space: {}'.format(k)
            o, r, d, t, _ = self.env.step(i)
            self.turn += 1
            self._obs = o
            return (o, r, d, t), None
        res, err = _do(cmd_key)
        if err:
            return err
        o, r, d, t = res
        if not (d or t) and slot:
            row0 = ''.join(chr(c) for c in o['tty_chars'][0]).lower()
            mbuf = bytes(o['message']).decode('utf-8', errors='ignore').lower()
            if 'what do you want to' in row0 or 'what do you want to' in mbuf:
                res, err = _do(slot)
                if err:
                    return err
                o, r, d, t = res
        if trailing and not (d or t):
            for k in trailing:
                res, err = _do(k)
                if err:
                    return err
                o, r, d, t = res
                if d or t:
                    break
        state = self.render(o)
        if d or t:
            state += '\n\n[GAME OVER] reward={:.1f}'.format(r)
            if self.log_dir:
                self._save_log(r)
        return state

    def render(self, obs=None):
        if obs is None:
            obs = self._obs
        b = obs['blstats']
        self._update_map_cache(obs)
        msg = bytes(obs['message']).decode('utf-8', errors='ignore').strip('\x00').strip()
        inv_lines = []
        for i in range(55):
            item = bytes(obs['inv_strs'][i]).decode('utf-8', errors='ignore').strip('\x00').strip()
            if item:
                letter = chr(obs['inv_letters'][i]) if obs['inv_letters'][i] > 0 else '?'
                inv_lines.append('{}) {}'.format(letter, item))
        inv_str = ('Inventory ({}): '.format(len(inv_lines)) + '  '.join(inv_lines)) if inv_lines else 'Inventory: empty'
        hunger_label = _HUNGER_LABEL.get(int(b[21]), str(b[21]))
        stats = ('Turn {} | Dlvl:{} | HP:{}/{} | AC:{} | XP:{} | Gold:{} | '
                 'Hunger:{} | Str:{} Dex:{} Con:{}').format(
            self.turn, int(b[12]), int(b[10]), int(b[11]), int(b[16]),
            int(b[19]), int(b[13]), hunger_label, int(b[3]), int(b[4]), int(b[5]))
        parts = [stats]
        if msg:
            parts.append('Message: {}'.format(msg))
        prompt = self._active_prompt(obs)
        if prompt:
            parts.append('PROMPT (game awaiting input — answer with keys:<letter> / keys:y / keys:27 to ESC): {}'.format(prompt))
        parts.append(self._map_features(obs))
        parts.append('Map (@ = you, # = corridor, + = door, > = stairs down, < = stairs up):\n' + self._render_map_cache(obs))
        parts.append(inv_str)
        return '\n'.join(parts)

    def render_live(self, last_action=None):
        obs = self._obs
        if obs is None:
            return ''
        b = obs['blstats']
        msg = bytes(obs['message']).decode('utf-8', errors='ignore').strip('\x00').strip()
        hunger_label = _HUNGER_LABEL.get(int(b[21]), str(b[21]))
        stats = 'Turn {} | Dlvl:{} | HP:{}/{} | AC:{} | XP:{} | Gold:{} | Hunger:{}'.format(
            self.turn, int(b[12]), int(b[10]), int(b[11]), int(b[16]), int(b[19]), int(b[13]), hunger_label)
        if last_action:
            stats += ' | >>> {}'.format(last_action)
        lines = ['{} NetHack AI {}'.format('-'*20, '-'*20), stats]
        if msg:
            lines.append('Msg: {}'.format(msg))
        lines.append('')
        lines.append(self._render_map_cache(obs))
        lines.append('')
        inv_lines = []
        for i in range(55):
            item = bytes(obs['inv_strs'][i]).decode('utf-8', errors='ignore').strip('\x00').strip()
            if item:
                letter = chr(obs['inv_letters'][i]) if obs['inv_letters'][i] > 0 else '?'
                inv_lines.append('{}) {}'.format(letter, item))
        if inv_lines:
            lines.append('Inventory: ' + '  '.join(inv_lines[:8]))
        return '\n'.join(lines)

    def _save_log(self, final_reward):
        os.makedirs(self.log_dir, exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        path = os.path.join(self.log_dir, 'game_{}.json'.format(ts))
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({'turns': self.turn, 'reward': final_reward, 'history': self.history}, f)

    def close(self):
        self.env.close()


def create_env(character=None, log_dir=None):
    return NLEEnv(character=character, log_dir=log_dir)
