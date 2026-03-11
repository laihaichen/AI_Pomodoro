"""game.engine — Core narrative engine: read state → lookup → call AI → save."""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BASE))

from config import read_snippet, write_snippet, SNIPPETS, THEME_FILE  # noqa: E402
from game.models import GameState, TurnRecord, TIER_KEYS, GAME_STATE_FILE  # noqa: E402
from game.prompts import load_system_prompt, build_user_message  # noqa: E402

STORY_TODAY_FILE = _BASE / "data" / "story_today.txt"
API_CONFIG_FILE = _BASE / "api_config.json"

# ── generating flag (polled by frontend) ─────────────────────────────────────
_GENERATING_FLAG_FILE = _BASE / "data" / "story_generating.flag"


def _set_generating(on: bool) -> None:
    if on:
        _GENERATING_FLAG_FILE.write_text("1", encoding="utf-8")
    else:
        _GENERATING_FLAG_FILE.unlink(missing_ok=True)


def is_generating() -> bool:
    return _GENERATING_FLAG_FILE.exists()


def _load_api_config() -> dict:
    try:
        return json.loads(API_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ── AI call ──────────────────────────────────────────────────────────────────

def _call_gemini(system_prompt: str, user_message: str) -> dict:
    """Call Gemini API with structured JSON output. Returns parsed dict."""
    import google.generativeai as genai

    cfg = _load_api_config()
    api_key = cfg.get("gemini_api_key", "")
    model_name = cfg.get("gemini_model_lite", "gemini-2.0-flash")

    if not api_key or api_key.startswith("在此"):
        raise ValueError("请先在 api_config.json 中填写有效的 Gemini API Key")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name,
        system_instruction=system_prompt,
    )

    response = model.generate_content(
        user_message,
        generation_config=genai.types.GenerationConfig(
            response_mime_type="application/json",
            temperature=0.9,
            max_output_tokens=4096,
        ),
    )

    raw = response.text.strip()
    return json.loads(raw)


# ── validation ───────────────────────────────────────────────────────────────

def _validate_output(data: dict) -> str | None:
    """Return error message if output is invalid, else None."""
    if not isinstance(data, dict):
        return "output is not a dict"
    story = data.get("story_text")
    if not isinstance(story, str) or not story.strip():
        return "story_text missing or empty"
    registry = data.get("event_registry")
    if not isinstance(registry, dict):
        return "event_registry missing or not dict"
    for key in TIER_KEYS:
        val = registry.get(key)
        if not isinstance(val, str) or not val.strip():
            return f"event_registry[{key}] missing or empty"
    return None


# ── core turn logic ──────────────────────────────────────────────────────────

def run_turn() -> dict:
    """Execute one narrative turn. Called after move_workflow completes.

    Returns dict with {ok, age, fate_value, fate_tier, story_text, event_registry}
    """
    _set_generating(True)
    try:
        return _run_turn_inner()
    finally:
        _set_generating(False)


def _run_turn_inner() -> dict:
    # 1. Read current state from snippets
    age = int(read_snippet("current_prompt_count") or "0")
    fate_value = int(read_snippet("final_fate_value") or "0")
    fate_tier = read_snippet("foretold") or ""
    theme = ""
    try:
        theme = THEME_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        pass

    state = GameState.load()

    # Use theme as story_type if not set yet
    if not state.story_type and theme:
        state.story_type = theme
        state.save()

    is_first = (fate_tier == SNIPPETS["foretold"].default) or len(state.history) == 0

    # 2. Lookup event text from previous turn's event_registry
    event_text = None
    if not is_first:
        prev_registry = state.latest_event_registry()
        if prev_registry and fate_tier in prev_registry:
            event_text = prev_registry[fate_tier]

    # 3. Check for destiny card override
    destiny_override = None
    if state.pending_destiny:
        if fate_value <= -90:
            # FAIL overrides destiny card — card not consumed (already decremented)
            state.pending_destiny = None
            state.save()
        else:
            zone = state.pending_destiny
            prev_registry = state.latest_event_registry()
            if prev_registry and zone in prev_registry:
                destiny_override = prev_registry[zone]
                event_text = destiny_override
            state.pending_destiny = None
            state.save()

    # 4. Build prompt
    system_prompt = load_system_prompt()
    user_message = build_user_message(
        character_name=state.character_name,
        story_type=state.story_type,
        age=age,
        fate_value=fate_value,
        event_text=event_text,
        is_first_turn=is_first,
        history=state.history,
        destiny_override=destiny_override,
    )

    # 5. Call Gemini API (with retry)
    data = None
    last_error = None
    for attempt in range(3):
        try:
            data = _call_gemini(system_prompt, user_message)
            err = _validate_output(data)
            if err is None:
                break
            last_error = err
            data = None
        except Exception as exc:
            last_error = str(exc)
            data = None

    if data is None:
        return {"ok": False, "error": f"AI output validation failed: {last_error}"}

    # 6. Save to game_state.json
    record = TurnRecord(
        age=age,
        fate_value=fate_value,
        fate_tier=fate_tier,
        story_text=data["story_text"],
        event_registry=data["event_registry"],
        destiny_used=destiny_override,
    )
    state.append_turn(record)

    # 7. Append to story_today.txt
    try:
        with open(STORY_TODAY_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n--- {age}岁 ---\n{data['story_text']}\n")
    except Exception:
        pass

    return {
        "ok": True,
        "age": age,
        "fate_value": fate_value,
        "fate_tier": fate_tier,
        "story_text": data["story_text"],
        "event_registry": data["event_registry"],
    }


def rerun_turn() -> dict:
    """Re-generate the last turn's story with the same parameters."""
    state = GameState.load()
    if not state.history:
        return {"ok": False, "error": "没有可重新生成的故事"}

    _set_generating(True)
    try:
        last = state.history[-1]
        age = last["age"]
        fate_value = last["fate_value"]
        fate_tier = last["fate_tier"]

        # Lookup event text from the second-to-last turn
        event_text = None
        is_first = (age <= 1) or len(state.history) <= 1
        if not is_first and len(state.history) >= 2:
            prev_registry = state.history[-2].get("event_registry")
            if prev_registry and fate_tier in prev_registry:
                event_text = prev_registry[fate_tier]

        system_prompt = load_system_prompt()

        # Build history without the last turn
        history_without_last = state.history[:-1]

        user_message = build_user_message(
            character_name=state.character_name,
            story_type=state.story_type,
            age=age,
            fate_value=fate_value,
            event_text=event_text,
            is_first_turn=is_first,
            history=history_without_last,
        )

        data = None
        last_error = None
        for attempt in range(3):
            try:
                data = _call_gemini(system_prompt, user_message)
                err = _validate_output(data)
                if err is None:
                    break
                last_error = err
                data = None
            except Exception as exc:
                last_error = str(exc)
                data = None

        if data is None:
            return {"ok": False, "error": f"rerun failed: {last_error}"}

        record = TurnRecord(
            age=age,
            fate_value=fate_value,
            fate_tier=fate_tier,
            story_text=data["story_text"],
            event_registry=data["event_registry"],
        )
        state.replace_last_turn(record)

        return {
            "ok": True,
            "age": age,
            "fate_value": fate_value,
            "fate_tier": fate_tier,
            "story_text": data["story_text"],
            "event_registry": data["event_registry"],
        }
    finally:
        _set_generating(False)


def get_story_state() -> dict:
    """Return current story state for the frontend panel."""
    state = GameState.load()

    # Live snippet reads — always show real-time data
    age = read_snippet("current_prompt_count") or "0"
    fate_value = read_snippet("final_fate_value") or "0"
    foretold = read_snippet("foretold") or ""
    countcard = read_snippet("countcard") or "0"
    countinterventioncard = read_snippet("countinterventioncard") or "0"
    fortune = read_snippet("fortune_and_misfortune") or ""

    # Theme from file
    theme = ""
    try:
        theme = THEME_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        pass

    return {
        "story_type": state.story_type or theme,
        "character_name": state.character_name,
        "generation": state.generation,
        "main_line_failed": state.main_line_failed,
        "history": state.history,
        "generating": is_generating(),
        "age": age,
        "fate_value": fate_value,
        "foretold": foretold,
        "fortune": fortune,
        "countcard": countcard,
        "countinterventioncard": countinterventioncard,
        "pending_destiny": state.pending_destiny,
    }


def use_card(card_type: str, zone: str, event_text: str = "") -> dict:
    """Use an intervention or destiny card."""
    state = GameState.load()

    if zone not in TIER_KEYS:
        return {"ok": False, "msg": f"无效的区间：{zone}"}

    if card_type == "intervention":
        count = int(read_snippet("countinterventioncard") or "0")
        if count <= 0:
            return {"ok": False, "msg": "没有干预卡"}
        if not event_text.strip():
            return {"ok": False, "msg": "请提供自定义事件文本"}
        # Replace the slot in the latest turn's event_registry
        if not state.history:
            return {"ok": False, "msg": "还没有故事历史，无法使用干预卡"}
        state.history[-1]["event_registry"][zone] = event_text.strip()
        state.save()
        write_snippet("countinterventioncard", str(count - 1))
        return {"ok": True, "msg": f"干预卡已使用，{zone} 槽位已替换"}

    elif card_type == "destiny":
        count = int(read_snippet("countcard") or "0")
        if count <= 0:
            return {"ok": False, "msg": "没有宿命卡"}
        if not state.history:
            return {"ok": False, "msg": "还没有故事历史，无法使用宿命卡"}
        state.pending_destiny = zone
        state.save()
        write_snippet("countcard", str(count - 1))
        return {"ok": True, "msg": f"宿命卡已使用，下一轮将强制触发 {zone}"}

    return {"ok": False, "msg": f"未知卡牌类型：{card_type}"}
