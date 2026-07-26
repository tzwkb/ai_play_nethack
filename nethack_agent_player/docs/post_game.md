# Post-game

Triggered when `[GAME OVER]` appears in state.

## Steps

1. Read `/tmp/nethack_gameover` for the final state
2. Analyze: cause of death, depth reached, key mistakes
3. Save lessons to memory:

```python
from scripts.memory import Memory

memory = Memory("nethack_memory.json")
memory.save({
    "game_id": "<session id>",
    "turns": <total turns>,
    "depth": <final dlvl>,
    "cause": "<what killed you or why you stopped>",
    "lessons": [
        "<specific lesson 1>",
        "<specific lesson 2>",
    ],
})
```

`game_id` 相同时 `save()` 更新原记录，不重复追加。精确删除旧教训使用
`memory.delete_lesson(text)`。

4. If a new rule should apply to all future runs → update the relevant `docs/` file
5. At the start of the next run: `memory.load(last_n=5)` to recall past lessons

## Memory path

`nethack_memory.json` is in the project root.
