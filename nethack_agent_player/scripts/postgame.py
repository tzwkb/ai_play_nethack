import re

from . import state_parser


def extract_depth_and_cause(state_text, last_live_state=""):
    parsed = state_parser.parse_state(state_text)
    last_live = state_parser.parse_state(last_live_state) if last_live_state else None
    depth = parsed.dlvl if parsed.dlvl > 0 else (
        last_live.dlvl if last_live and last_live.dlvl > 0 else 1)

    flattened = ' '.join(line.strip() for line in state_text.splitlines())
    match = re.search(r'(killed by|slain by)\s+([^.]*)\.?', flattened, re.IGNORECASE)
    if match:
        cause = '{} {}.'.format(match.group(1).capitalize(), match.group(2).strip())
    else:
        match = re.search(r'\b(starved|poisoned)\b', flattened, re.IGNORECASE)
        cause = match.group(1).capitalize() + '.' if match else 'unknown'
    return depth, cause
