"""
Shared question handling for the webhook.
Interpret user speech/text via LLM and return answer text.
Optional: run responses through LLM to sound more natural when spoken.
"""
import json
import random


def _naturalize_for_voice(text: str) -> str:
    """Rewrite response text so it sounds natural when read aloud. Returns original on failure."""
    if not text or not text.strip():
        return text
    try:
        from config import config
        if not getattr(config, "NATURALIZE_RESPONSES", True):
            return text
        import ollama
        client = ollama.Client(host=config.OLLAMA_HOST)
        prompt = """This will be read aloud on a brief church youth calendar voice call. Rewrite it so it sounds warm and conversational—like a friendly volunteer giving a quick update, not a robot. Keep the same facts and length (1–3 short sentences). Don't be bubbly or over the top; just a little warmth and ease. Output ONLY the rewritten sentence(s), nothing else.

Text to rewrite:
"""
        response = client.chat(
            model=config.OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt + text.strip()}],
        )
        out = (response.get("message") or {}).get("content") or ""
        out = out.strip()
        if out and len(out) < 500 and not out.lower().startswith("i'm sorry"):
            return out
    except Exception:
        pass
    return text


def interpret_question_with_llm(transcript: str) -> dict | None:
    """Send question to Ollama, get intent + params as JSON."""
    try:
        import ollama
        from config import config
        client = ollama.Client(host=config.OLLAMA_HOST)
        prompt = """Classify this calendar question and return ONLY valid JSON, no other text.
Valid intents: next_n_events, event_in_weeks, events_in_month, check_event, who_made, unknown

IMPORTANT: "next 3 events" = list of three upcoming events. "activity in 3 weeks" = the single event happening about 3 weeks from now.

Examples:
- "what are the next 3 events?" -> {"intent":"next_n_events","n":3}
- "what activity do we have in 3 weeks?" -> {"intent":"event_in_weeks","weeks":3}
- "anything in 2 weeks?" -> {"intent":"event_in_weeks","weeks":2}
- "anything in April?" -> {"intent":"events_in_month","month":"april"}
- "is Summer Camp on the schedule?" -> {"intent":"check_event","event_name":"summer camp"}
- "who made this app?" -> {"intent":"who_made"}

Question: """
        response = client.chat(
            model=config.OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt + transcript}],
        )
        text = response["message"]["content"].strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            text = text[start:end]
        data = json.loads(text)
        if isinstance(data, dict) and "intent" in data:
            return data
    except Exception:
        pass
    return None


def _get_snarky_creator_response() -> str:
    """Ask LLM for a snarky but church-appropriate easter egg response."""
    try:
        import ollama
        from config import config
        client = ollama.Client(host=config.OLLAMA_HOST)
        prompt = """Generate one brief, snarky but church-appropriate response for when someone asks who made this phone app.

Facts: Brother Zach Cochran made it (Zach, not Mickey Cochran). He built it for the Deacons. It's a fun easter egg.

Requirements:
- Self-deprecating, light humor
- Church-appropriate and SFW
- 1-2 sentences, under 30 words
- Sound natural when read aloud (voice call)
- No quotes, no preamble—just the response

Generate ONLY the response, nothing else:"""
        response = client.chat(
            model=config.OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response["message"]["content"].strip()
        for c in ('"', "'"):
            if text.startswith(c) and text.endswith(c):
                text = text[1:-1]
        if text and len(text) < 200:
            return text
    except Exception:
        pass
    return "Brother Cochran—Zach, not Mickey. He built this thing. If it's weird, that's on him."


# Semi-snarky but church-friendly nudges when the calendar is empty (encourage updating it)
_CALENDAR_EMPTY_NUDGES = (
    "Maybe give your class or quorum president a nudge to update it!",
    "If you're in the know, tell your president to add it to the sheet!",
    "Call your class or quorum president and kindly suggest they update it!",
)


def _calendar_empty_response(context: str) -> str:
    """Return a warm but gently nudge-y response when there's nothing on the calendar for the given context."""
    nudge = random.choice(_CALENDAR_EMPTY_NUDGES)
    # context is e.g. "for around 3 weeks from now" or "for the next week" or "in April yet"
    return _naturalize_for_voice(f"Nothing on the calendar {context}. {nudge}")


def _is_unnamed_event(e: dict) -> bool:
    """True if the event has no real name (placeholder / unnamed). Same nudge as empty calendar."""
    name = (e.get("name") or "").strip().lower()
    if not name:
        return True
    placeholders = ("unnamed", "tbd", "todo", "tba", "none", "pending", "event")
    if name in placeholders:
        return True
    if name.startswith("unnamed") or name == "event":
        return True
    return False


def _format_combined_event(e: dict) -> str | None:
    """If event name indicates a combined activity, return a more descriptive sentence."""
    import re
    from datetime import date, timedelta
    name = (e.get("name") or "").strip()
    if not name or "combined" not in name.lower():
        return None
    time_str = e.get("time") or "TBD"
    # Format date: if this week, just day name; otherwise day name + date
    event_date = e["date"]
    today = date.today()
    days_since_monday = today.weekday()
    week_start = today - timedelta(days=days_since_monday)
    week_end = week_start + timedelta(days=6)
    if week_start <= event_date <= week_end:
        date_str = event_date.strftime("%A")
    else:
        date_str = event_date.strftime("%A, %B %d")
    # Strip "Combined" and any following dash/colon from the name for the activity part
    rest = re.sub(r"^combined\s*[-–—:\s]*", "", name, flags=re.I).strip()
    if not rest:
        rest = name
    else:
        rest = rest[0].lower() + rest[1:] if len(rest) > 1 else rest.lower()
        return f"The next event is a combined activity, {rest}, on {date_str} at {time_str}."


def _format_next_event_date_natural(event_date, time_str: str, reference_date=None):
    """
    Human-friendly date/time for the next event: "today at 3:00", "tomorrow at 5:15",
    "this afternoon at 2:00", "Wednesday at 6:00", "Wednesday, February 11 at 6:00".
    reference_date defaults to today; used so crossing midnight triggers intro refresh.
    """
    from datetime import date, timedelta
    ref = reference_date or date.today()
    time_str = (time_str or "TBD").strip()
    delta = (event_date - ref).days
    if delta == 0:
        day_part = "today"
    elif delta == 1:
        day_part = "tomorrow"
    elif delta < 0:
        day_part = event_date.strftime("%A, %B %d")
    else:
        # This week: just day name
        days_since_monday = ref.weekday()
        week_start = ref - timedelta(days=days_since_monday)
        week_end = week_start + timedelta(days=6)
        if week_start <= event_date <= week_end:
            day_part = event_date.strftime("%A")
        else:
            day_part = event_date.strftime("%A, %B %d")
    # Optional: "this afternoon" / "this evening" for today/tomorrow
    try:
        t = time_str.upper().replace(".", "")
        if "PM" in t or "AM" in t:
            hour_str = t.split(":")[0]
            hour = int("".join(c for c in hour_str if c.isdigit()) or 0)
            if "PM" in t and hour != 12:
                hour += 12
            if "AM" in t and hour == 12:
                hour = 0
            if delta == 0 and hour >= 12 and hour < 17:
                return f"this afternoon at {time_str}"
            if delta == 0 and hour >= 17:
                return f"this evening at {time_str}"
            if delta == 0 and hour < 12:
                return f"this morning at {time_str}"
            if delta == 1 and hour >= 12 and hour < 17:
                return f"tomorrow afternoon at {time_str}"
            if delta == 1 and hour >= 17:
                return f"tomorrow evening at {time_str}"
            if delta == 1 and hour < 12:
                return f"tomorrow morning at {time_str}"
        else:
            pass  # fall through to day_part + at time_str
    except Exception:
        pass
    return f"{day_part} at {time_str}"


def get_next_event_intro_signature(reference_date=None):
    """
    Return a signature tuple for the current "next event" so the scheduler can detect
    when to refresh intros: (name, date_iso, time, location, reference_date_iso).
    Crossing into a new day (reference_date) counts as change so "today"/"tomorrow" refresh.
    Returns None if no upcoming event.
    """
    try:
        from datetime import date
        from sheets_reader import sheets
        ref = reference_date or date.today()
        upcoming = sheets.get_upcoming_events(days_ahead=90)
        if not upcoming:
            return None
        e = upcoming[0]
        return (
            (e.get("name") or "").strip(),
            e["date"].isoformat(),
            (e.get("time") or "").strip(),
            (e.get("location") or "").strip(),
            ref.isoformat(),
        )
    except Exception:
        return None


def _get_next_event_text() -> str:
    try:
        from datetime import date
        from sheets_reader import sheets
        upcoming = sheets.get_upcoming_events(days_ahead=90)
        if not upcoming:
            return _naturalize_for_voice("No upcoming events.")
        e = upcoming[0]
        if _is_unnamed_event(e):
            return _calendar_empty_response("for the next bit—someone forgot to name it")
        combined_text = _format_combined_event(e)
        if combined_text:
            return _naturalize_for_voice(combined_text)
        event_date = e["date"]
        time_str = e.get("time") or "TBD"
        location = (e.get("location") or "").strip()
        when = _format_next_event_date_natural(event_date, time_str)
        if location:
            raw = f"The next event is {e['name']}, {when}, at {location}."
        else:
            raw = f"The next event is {e['name']}, {when}."
        return _naturalize_for_voice(raw)
    except Exception:
        return "Sorry, we couldn't look up events right now. Check the calendar for what's coming up."


def _get_next_event_date_time_short() -> str:
    """Return just the date and time of the next event, e.g. 'Wednesday, February 11 at 5:15.' for repeating after the intro."""
    try:
        from datetime import date, timedelta
        from sheets_reader import sheets
        upcoming = sheets.get_upcoming_events(days_ahead=90)
        if not upcoming:
            return _naturalize_for_voice("No upcoming events on the calendar.")
        e = upcoming[0]
        if _is_unnamed_event(e):
            return _calendar_empty_response("for the next bit—someone forgot to name it")
        event_date = e["date"]
        today = date.today()
        days_since_monday = today.weekday()
        week_start = today - timedelta(days=days_since_monday)
        week_end = week_start + timedelta(days=6)
        if week_start <= event_date <= week_end:
            date_str = event_date.strftime("%A")
        else:
            date_str = event_date.strftime("%A, %B %d")
        time_str = e.get("time") or "TBD"
        raw = f"It's on {date_str} at {time_str}."
        return _naturalize_for_voice(raw)
    except Exception:
        return "Sorry, we couldn't look up the calendar right now."


def _get_next_n_events_text(n: int) -> str:
    try:
        from sheets_reader import sheets
        upcoming = sheets.get_upcoming_events(days_ahead=90)
        named = [e for e in upcoming if not _is_unnamed_event(e)]
        if not named:
            return _naturalize_for_voice("There are no upcoming events.")
        events = named[:n]
        parts = []
        for e in events:
            date_str = e["date"].strftime("%A, %B %d")
            time_str = e.get("time") or "TBD"
            parts.append(f"{e['name']} on {date_str} at {time_str}")
        raw = "The next " + str(n) + " events: " + ". ".join(parts)
        return _naturalize_for_voice(raw)
    except Exception:
        return "Sorry, we couldn't look up events right now."


def _get_event_in_weeks_text(weeks: int) -> str:
    """Return activity (or a few) falling in the window around N weeks from now. Uses same friendly phrasing as next-event (e.g. combined activities)."""
    try:
        from datetime import date, timedelta
        from sheets_reader import sheets
        if weeks < 1 or weeks > 12:
            return _naturalize_for_voice("I can only look up about 1 to 12 weeks ahead.")
        today = date.today()
        # Window: full week around N weeks out (e.g. 3 weeks = days 18–24)
        start = today + timedelta(days=weeks * 7 - 3)
        end = today + timedelta(days=weeks * 7 + 3)
        upcoming = sheets.get_upcoming_events(days_ahead=365)
        in_window = [e for e in upcoming if start <= e["date"] <= end]
        named_in_window = [e for e in in_window if not _is_unnamed_event(e)]
        if not named_in_window:
            return _calendar_empty_response(f"for around {weeks} weeks from now")
        # Up to 3 events; use combined-activity phrasing when applicable (same as next-event intro)
        parts = []
        for e in named_in_window[:3]:
            combined_text = _format_combined_event(e)
            if combined_text:
                rest = combined_text.replace("The next event is ", "").strip()
                parts.append(rest)
            else:
                date_str = e["date"].strftime("%A, %B %d")
                time_str = e.get("time") or "TBD"
                parts.append(f"{e['name']} on {date_str} at {time_str}")
        if len(parts) == 1:
            raw = f"In about {weeks} weeks: {parts[0]}."
        else:
            raw = f"In about {weeks} weeks we have: " + ". ".join(parts) + "."
        return _naturalize_for_voice(raw)
    except Exception:
        return "Sorry, we couldn't look up events right now."


def _get_next_week_events_text() -> str:
    try:
        from sheets_reader import sheets
        upcoming = sheets.get_upcoming_events(days_ahead=7)
        named = [e for e in upcoming if not _is_unnamed_event(e)]
        if not named:
            return _calendar_empty_response("for the next week")
        parts = []
        for e in named[:5]:
            date_str = e["date"].strftime("%A, %B %d")
            time_str = e.get("time") or "TBD"
            parts.append(f"{e['name']} on {date_str} at {time_str}")
        raw = "Next week: " + ". ".join(parts)
        return _naturalize_for_voice(raw)
    except Exception:
        return "Sorry, we couldn't look up events right now."


def _get_events_in_month_text(month_name: str) -> str:
    months = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
              "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12}
    try:
        from sheets_reader import sheets
        month_num = months.get(month_name.lower(), None)
        if month_num is None:
            return get_fallback_response()
        upcoming = sheets.get_upcoming_events(days_ahead=365)
        in_month = [e for e in upcoming if e["date"].month == month_num]
        named_in_month = [e for e in in_month if not _is_unnamed_event(e)]
        if not named_in_month:
            return _calendar_empty_response(f"in {month_name.capitalize()} yet")
        parts = []
        for e in named_in_month[:5]:
            date_str = e["date"].strftime("%A, %B %d")
            time_str = e.get("time") or "TBD"
            parts.append(f"{e['name']} on {date_str} at {time_str}")
        raw = f"In {month_name.capitalize()}: " + ". ".join(parts)
        return _naturalize_for_voice(raw)
    except Exception:
        return "Sorry, we couldn't look up events right now."


def _check_event_on_schedule(search_term: str) -> str:
    try:
        from sheets_reader import sheets
        upcoming = sheets.get_upcoming_events(days_ahead=365)
        term = search_term.lower()
        matches = [e for e in upcoming if term in e["name"].lower()]
        if not matches:
            return _naturalize_for_voice(f"{search_term} isn't on the schedule yet.")
        e = matches[0]
        date_str = e["date"].strftime("%A, %B %d")
        time_str = e.get("time") or "TBD"
        raw = f"Yes, {e['name']} is on the schedule. It's on {date_str} at {time_str}."
        return _naturalize_for_voice(raw)
    except Exception:
        return "Sorry, we couldn't look up events right now."


def answer_from_intent(intent_data: dict | None) -> str | None:
    """Turn parsed intent into answer text."""
    if not intent_data or intent_data.get("intent") == "unknown":
        return None
    intent = intent_data.get("intent", "")
    if intent == "next_n_events":
        n = intent_data.get("n", 3)
        if not isinstance(n, int) or n < 1 or n > 10:
            n = 3
        return _get_next_n_events_text(n)
    if intent == "event_in_weeks":
        weeks = intent_data.get("weeks", 1)
        if isinstance(weeks, (int, float)):
            weeks = int(weeks)
        else:
            weeks = 1
        return _get_event_in_weeks_text(weeks)
    if intent == "events_in_month":
        month = intent_data.get("month", "")
        if month:
            return _get_events_in_month_text(str(month).lower())
    if intent == "check_event":
        name = intent_data.get("event_name", "")
        if name:
            return _check_event_on_schedule(str(name))
    if intent == "who_made":
        return _get_snarky_creator_response()
    return None


FALLBACK_RESPONSES = (
    "Sorry, we're still learning. We can answer simple questions about the calendar.",
    "I'm still learning. Try asking about upcoming events or what's on the calendar.",
    "I'm not sure about that one yet. Ask me about the next few events or what's coming up!",
    "Still learning here. I'm best at things like what's next, or what's in a few weeks.",
)


def get_fallback_response() -> str:
    """Return a random 'still learning' style response when we don't recognize the question."""
    return random.choice(FALLBACK_RESPONSES)


# Backward compatibility for code that imports the single default
FALLBACK_RESPONSE = FALLBACK_RESPONSES[0]


def handle_question(transcript: str) -> str | None:
    """Handle questions. Returns response text or None for unrecognized."""
    if not transcript or not str(transcript).strip():
        return None
    q = str(transcript).strip().lower()

    intent_data = interpret_question_with_llm(transcript)
    try:
        from config import config
        if getattr(config, "DEBUG_MODE", False) and intent_data is not None:
            print(f"[zarchbot] LLM intent: {intent_data!r} for transcript: {transcript[:80]!r}")
    except Exception:
        pass
    if intent_data:
        answer = answer_from_intent(intent_data)
        if answer:
            try:
                from config import config
                if getattr(config, "DEBUG_MODE", False):
                    print(f"[zarchbot] Using LLM answer (intent={intent_data.get('intent')})")
            except Exception:
                pass
            return answer
    try:
        from config import config
        if getattr(config, "DEBUG_MODE", False):
            print(f"[zarchbot] No LLM answer (intent={intent_data!r}), using keyword fallbacks")
    except Exception:
        pass

    # "What's the date of that activity?" / "When is it?" — repeat the next event's date/time
    if any(phrase in q for phrase in ("date of that", "date of the activity", "when is it", "when is that", "what day is it", "what day is that", "what's the date", "when's that")):
        return _get_next_event_date_time_short()

    if "next" in q and any(x in q for x in ["3", "three", "few", "several"]):
        n = 3
        if "5" in q or "five" in q:
            n = 5
        elif "2" in q or "two" in q:
            n = 2
        return _get_next_n_events_text(n)

    # "in 5 weeks" / "activity in 3 weeks" — check for week + number BEFORE generic "next week"
    # so "what's the activity in 5 weeks?" doesn't get misrouted to "next week" (next 7 days)
    week_tokens = [(1, ["1", "one"]), (2, ["2", "two"]), (3, ["3", "three"]), (4, ["4", "four"]),
                   (5, ["5", "five"]), (6, ["6", "six"]), (7, ["7", "seven"]), (8, ["8", "eight"])]
    if "week" in q:
        for w, tokens in week_tokens:
            if any(t in q for t in tokens):
                return _get_event_in_weeks_text(w)
    if "next week" in q:
        return _get_next_week_events_text()

    if any(m in q for m in ["january", "february", "march", "april", "may", "june",
                            "july", "august", "september", "october", "november", "december"]):
        for month in ["january", "february", "march", "april", "may", "june",
                      "july", "august", "september", "october", "november", "december"]:
            if month in q:
                return _get_events_in_month_text(month)

    if "on the schedule" in q or "on schedule" in q:
        rest = q.replace("on the schedule", "").replace("on schedule", "").strip()
        rest = rest.replace("is ", "").replace("are ", "").strip().rstrip("?.")
        if rest and len(rest) > 2:
            return _check_event_on_schedule(rest)

    for phrase in ["summer camp", "ice skating", "tubing", "games", "planning", "kickoff"]:
        if phrase in q:
            return _check_event_on_schedule(phrase)

    if "who" in q and ("made" in q or "created" in q or "built" in q):
        return _get_snarky_creator_response()
    if "silly app" in q:
        return _get_snarky_creator_response()

    return None


def get_next_event_text() -> str:
    """Get time, date, and title of the next upcoming event."""
    return _get_next_event_text()


# Greeting prefixes for pre-generated voice intros (used when refreshing intro cache)
_INTRO_GREETINGS = (
    "Hi there, neighbor! ",
    "Hey! ",
    "Hi! Just a quick heads-up—",
)


def get_next_event_intro_variations(count: int = 3) -> list[str]:
    """
    Return up to `count` natural-language variations of the next-event intro
    (different greetings + same event info). Used to pre-generate TTS so callers
    hear a ready intro without delay.
    """
    core = _get_next_event_text()
    if not core or not core.strip():
        return []
    # Optional: lowercase first letter after "Just a quick heads-up—" for one variation
    core_cap = core.strip()
    core_lo = core_cap[0].lower() + core_cap[1:] if len(core_cap) > 1 else core_cap
    variations = []
    for i, greeting in enumerate(_INTRO_GREETINGS[:count]):
        rest = core_lo if "quick heads-up" in greeting else core_cap
        variations.append(f"{greeting}{rest}")
    return variations


def get_current_event():
    """Return the event currently in progress (started, within duration), or None. Deacons-focused for now."""
    try:
        from config import config
        from sheets_reader import sheets
        duration = getattr(config, "CURRENT_EVENT_DURATION_HOURS", 3)
        return sheets.get_current_event(duration_hours=duration)
    except Exception:
        return None


def _get_during_event_intro_text(current_event, next_event_after) -> str:
    """Build a brief during-event line for TTS (keep it short for callers in a hurry)."""
    from datetime import date
    location = (current_event.get("location") or "").strip() or "the church"
    event_date = current_event["date"]
    ref = date.today()
    delta = (event_date - ref).days
    if delta == 0:
        when_word = "today"
    elif delta == 1:
        when_word = "tomorrow"
    else:
        when_word = event_date.strftime("%A")
    if not next_event_after:
        return _naturalize_for_voice(f"We're at {location} {when_word}.")
    name = (next_event_after.get("name") or "").strip()
    if _is_unnamed_event(next_event_after):
        name = "the next activity"
    raw = f"We're at {location} {when_word}. Next up: {name}."
    return _naturalize_for_voice(raw)


def _get_event_to_prewarm_during_for():
    """
    Return (current_or_upcoming_event, event_after) for during-event message pre-warm.
    Either we're in an event now, or the next upcoming event starts within PREWARM_HOURS_BEFORE.
    Returns (None, None) if neither applies.
    """
    try:
        from datetime import datetime, timedelta
        from config import config
        from sheets_reader import sheets
        prewarm_hours = getattr(config, "DURING_EVENT_PREWARM_HOURS_BEFORE", 1) or 0
        current = get_current_event()
        if current:
            upcoming = sheets.get_upcoming_events(days_ahead=90)
            current_start = current["datetime"]
            next_after = None
            for e in upcoming:
                if e["datetime"] > current_start:
                    next_after = e
                    break
            return current, next_after
        if prewarm_hours <= 0:
            return None, None
        upcoming = sheets.get_upcoming_events(days_ahead=90)
        if not upcoming:
            return None, None
        now = datetime.now()
        window_end = now + timedelta(hours=prewarm_hours)
        next_event = upcoming[0]
        if next_event["datetime"] > window_end:
            return None, None
        event_after = upcoming[1] if len(upcoming) > 1 else None
        return next_event, event_after
    except Exception:
        return None, None


def get_during_event_intro_text() -> str:
    """
    Return a single "we're at X tonight; next activity is Y" line for on-the-fly TTS.
    Empty string if no event in progress and not within pre-warm window. Use when prepared during_event audio isn't ready yet.
    """
    event, next_after = _get_event_to_prewarm_during_for()
    if not event:
        return ""
    try:
        return _get_during_event_intro_text(event, next_after) or ""
    except Exception:
        return ""


def get_during_event_intro_variations(count: int = 2) -> list[str]:
    """
    Return up to `count` variations of the "we're at X tonight; next activity is Y" intro.
    Used when an event is in progress or when the next event starts within PREWARM_HOURS_BEFORE (so it's ready when the event begins).
    """
    text = get_during_event_intro_text()
    if not text or not text.strip():
        return []
    return [text] * count if count > 0 else []


def get_during_event_intro_signature(reference_date=None):
    """
    Signature for scheduler: (event_id, next_event_id, ref_iso) or None.
    When this changes, refresh during-event pre-warm. Includes both "in progress" and "starts within PREWARM_HOURS_BEFORE" cases.
    """
    try:
        from datetime import date
        ref = reference_date or date.today()
        event, next_after = _get_event_to_prewarm_during_for()
        if not event:
            return None
        cur_id = f"{event.get('name','')}_{event['date'].isoformat()}_{event.get('time','')}"
        nxt_id = f"{next_after.get('name','')}_{next_after['date'].isoformat()}_{next_after.get('time','')}" if next_after else ""
        return (cur_id, nxt_id, ref.isoformat())
    except Exception:
        return None
