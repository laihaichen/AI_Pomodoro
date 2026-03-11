"""game.models — Data structures for the narrative engine."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

# 7 fixed tier keys — order matches fate_category() in move.py
TIER_KEYS = [
    "FAIL", "NEG_HIGH", "NEG_MID", "NEG_LOW",
    "POS_LOW", "POS_MID", "POS_HIGH",
]

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
GAME_STATE_FILE = DATA_DIR / "game_state.json"


@dataclass
class TurnRecord:
    """One turn of story history."""
    age: int
    fate_value: int
    fate_tier: str                         # e.g. "POS_MID"
    story_text: str
    event_registry: dict[str, str]         # 7 slots
    intervention_used: Optional[dict] = None   # {zone, event_text}
    destiny_used: Optional[str] = None         # zone key


@dataclass
class GameState:
    """Persistent game state saved to game_state.json."""
    story_type: str = ""
    character_name: str = ""
    generation: int = 1
    main_line_failed: bool = False
    pending_destiny: Optional[str] = None      # zone key if destiny card queued
    history: list[dict] = field(default_factory=list)

    # ── persistence ──────────────────────────────────────────────────────

    @classmethod
    def load(cls) -> "GameState":
        if GAME_STATE_FILE.exists():
            try:
                raw = json.loads(GAME_STATE_FILE.read_text(encoding="utf-8"))
                return cls(
                    story_type=raw.get("story_type", ""),
                    character_name=raw.get("character_name", ""),
                    generation=raw.get("generation", 1),
                    main_line_failed=raw.get("main_line_failed", False),
                    pending_destiny=raw.get("pending_destiny"),
                    history=raw.get("history", []),
                )
            except Exception:
                pass
        return cls()

    def save(self) -> None:
        GAME_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        GAME_STATE_FILE.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── helpers ───────────────────────────────────────────────────────────

    def latest_event_registry(self) -> Optional[dict[str, str]]:
        """Return event_registry from the most recent turn, or None."""
        if self.history:
            return self.history[-1].get("event_registry")
        return None

    def append_turn(self, record: TurnRecord) -> None:
        self.history.append(asdict(record))
        self.save()

    def replace_last_turn(self, record: TurnRecord) -> None:
        """Replace the last turn (for rerun)."""
        if self.history:
            self.history[-1] = asdict(record)
        else:
            self.history.append(asdict(record))
        self.save()
