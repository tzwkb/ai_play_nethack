import json
import os
from datetime import datetime


class Memory:
    def __init__(self, path="./nethack_memory.json"):
        self.path = path

    def load(self, last_n=5):
        if not os.path.exists(self.path):
            return ""
        with open(self.path, encoding='utf-8') as f:
            data = json.load(f)
        games = data.get("games", [])[-last_n:]
        if not games:
            return ""
        lines = ["Past lessons:"]
        for g in games:
            lines.append(f"- Depth {g.get('depth',1)}, Turn {g.get('turns',0)}: {g.get('cause','unknown')}")
            for lesson in g.get("lessons", []):
                lines.append(f"  * {lesson}")
        return '\n'.join(lines)

    def save(self, record):
        if os.path.exists(self.path):
            with open(self.path, encoding='utf-8') as f:
                data = json.load(f)
        else:
            data = {"games": []}
        record.setdefault("date", datetime.now().strftime("%Y-%m-%d"))
        game_id = record.get("game_id")
        if game_id:
            for index, existing in enumerate(data["games"]):
                if existing.get("game_id") == game_id:
                    merged = dict(existing)
                    merged.update(record)
                    data["games"][index] = merged
                    break
            else:
                data["games"].append(record)
        else:
            data["games"].append(record)
        self._write(data)

    def delete_lesson(self, lesson_text):
        if not os.path.exists(self.path):
            return 0
        with open(self.path, encoding='utf-8') as f:
            data = json.load(f)
        removed = 0
        for game in data.get("games", []):
            lessons = game.get("lessons", [])
            kept = [lesson for lesson in lessons if lesson != lesson_text]
            removed += len(lessons) - len(kept)
            game["lessons"] = kept
        if removed:
            self._write(data)
        return removed

    def _write(self, data):
        tmp = self.path + ".tmp"
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)
