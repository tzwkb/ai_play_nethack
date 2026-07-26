import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from env import ACTION_MAP, NLEEnv


def test_action_map_completeness():
    """All actions in ACTION_MAP should have valid NLE indices."""
    for name, idx in ACTION_MAP.items():
        assert isinstance(idx, int), f"Action {name} has non-int index: {idx}"
        assert idx >= 0, f"Action {name} has negative index: {idx}"


def test_direction_actions_present():
    """Basic movement actions must exist."""
    for d in ['north', 'south', 'east', 'west', 'northeast', 'southeast', 'southwest', 'northwest']:
        assert d in ACTION_MAP, f"Missing direction action: {d}"


def test_common_actions_present():
    """Essential gameplay actions must exist."""
    essential = ['wait', 'search', 'descend', 'ascend', 'pickup', 'eat', 'drink', 'open', 'pray']
    for a in essential:
        assert a in ACTION_MAP, f"Missing essential action: {a}"


def test_char_to_idx_without_env():
    """_char_to_idx requires an env instance, but we can at least verify the method exists."""
    # This is a smoke test — full test would need NLE env which is slow to start.
    assert hasattr(NLEEnv, '_char_to_idx')
    assert hasattr(NLEEnv, 'send_keys')
    assert hasattr(NLEEnv, 'step')
    assert hasattr(NLEEnv, '_flush_pending')


def test_navigate_method_exists():
    assert hasattr(NLEEnv, 'navigate_to')


def test_repeat_action_method_exists():
    assert hasattr(NLEEnv, 'repeat_action')


if __name__ == "__main__":
    test_action_map_completeness()
    test_direction_actions_present()
    test_common_actions_present()
    test_char_to_idx_without_env()
    test_navigate_method_exists()
    test_repeat_action_method_exists()
    print("All env_actions tests passed.")
