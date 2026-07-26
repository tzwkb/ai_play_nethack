import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.env import MAP_COLS, MAP_ROWS, NLEEnv
from scripts.memory import Memory
from scripts.postgame import extract_depth_and_cause


def make_obs(hp=5, hpmax=66, depth=5, player=(63, 8), monsters=None, message=""):
    tty = [bytearray(b" " * MAP_COLS) for _ in range(24)]
    px, py = player
    tty[py + 1][px] = ord("@")
    for symbol, x, y in monsters or []:
        tty[y + 1][x] = ord(symbol)
    blstats = [0] * 27
    blstats[0], blstats[1] = px, py
    blstats[10], blstats[11], blstats[12] = hp, hpmax, depth
    return {
        "tty_chars": tty,
        "blstats": blstats,
        "message": bytearray(message.encode()),
        "inv_strs": [bytearray() for _ in range(55)],
        "inv_letters": [0] * 55,
    }


def make_env(obs):
    env = NLEEnv.__new__(NLEEnv)
    env._obs = obs
    env._map_cache = [[" "] * MAP_COLS for _ in range(MAP_ROWS)]
    env._prev_hp = None
    env._last_damage = 0
    env._major_hit_until = -1
    env._current_depth = None
    env._known_hazards = {}
    env._item_knowledge = {}
    env.turn = 0
    env.history = []
    env.log_dir = None
    env.verbose = False
    return env


def test_wait_is_blocked_with_visible_hostile_at_critical_hp():
    env = make_env(make_obs(monsters=[("M", 62, 8)]))
    reason = env.check_action_safety("wait:8")
    assert "visible hostile" in reason


def test_critical_hp_blocks_non_survival_actions():
    env = make_env(make_obs(monsters=[]))
    assert env.check_action_safety("eat")
    assert env.check_action_safety("pickup")
    assert env.check_action_safety("goto:10,10")
    assert env.check_action_safety("drink:r")
    assert env.check_action_safety("drink")
    assert env.check_action_safety("zap:q:east")
    assert env.check_action_safety("east") == ""


def test_identified_healing_is_allowed_in_critical_danger():
    obs = make_obs(monsters=[])
    obs["inv_strs"][0] = bytearray(b"a potion of healing")
    obs["inv_letters"][0] = ord("r")
    env = make_env(obs)
    assert env.check_action_safety("drink:r") == ""


def test_triggered_trap_is_persisted_and_rejected_as_target():
    obs = make_obs(
        hp=14,
        player=(62, 9),
        message="Click! You trigger a rolling boulder trap! You are hit by a boulder!",
    )
    env = make_env(obs)
    env._update_map_cache(obs)
    assert env._known_hazards[(5, 62, 9)] == "rolling boulder trap"
    _, reason = env.navigate_to(62, 10)
    assert reason == "known_hazard"


def test_gameover_uses_last_live_depth_and_clean_cause():
    gameover = """
Turn 1995 | Dlvl:0 | HP:0/0 | AC:0 | XP:0 | Gold:0
Agent-Bar-Hum-Mal-Neu died in The Gnomish Mines on
level 5. Killed by a gnome mummy.
[GAME OVER] reward=0.0
"""
    live = "Turn 1994 | Dlvl:5 | HP:1/66 | AC:8 | XP:6 | Gold:130"
    assert extract_depth_and_cause(gameover, live) == (5, "Killed by a gnome mummy.")


def test_item_observation_marks_non_healing_appearance():
    env = make_env(make_obs(hp=10, message="You feel rather strange."))
    note = env.record_item_use("drink", "a bubbly potion", 10)
    assert "no immediate HP recovery" in note
    assert env._item_knowledge["bubbly potion"]["uses"] == 1


def test_major_hit_keeps_safety_lock_active_across_renders():
    env = make_env(make_obs(hp=50, hpmax=100))
    env.turn = 10
    env._prev_hp = 80
    env._status_warnings(env._obs)
    assert env._danger_level() == "critical"
    env._status_warnings(env._obs)
    assert env._danger_level() == "critical"


def test_memory_save_upserts_by_game_id(tmp_path):
    memory = Memory(str(tmp_path / "memory.json"))
    memory.save({"game_id": "g1", "turns": 10, "lessons": ["remove me", "keep me"]})
    memory.save({"game_id": "g1", "turns": 12, "cause": "test"})
    assert '"turns": 12' in (tmp_path / "memory.json").read_text()
    assert (tmp_path / "memory.json").read_text().count('"game_id": "g1"') == 1
    assert memory.delete_lesson("remove me") == 1
    text = (tmp_path / "memory.json").read_text()
    assert "remove me" not in text
    assert "keep me" in text
