"""
Webhook server for incoming Twilio voice calls and SMS.
Twilio POSTs here when someone calls or texts the configured number.
Returns TwiML to handle the response. Uses Kokoro blended voice for TTS.
LLM (Ollama) interprets questions for flexible intent handling.
"""
import json
import os
import urllib.parse
from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse, Gather
from twilio.twiml.messaging_response import MessagingResponse

app = Flask(__name__)

FALLBACK_RESPONSE = "Sorry, we're still learning. We can answer simple questions about the calendar."

ACK_PHRASE = "Sure, let me check."


def _interpret_question_with_llm(transcript):
    """
    Send question to Ollama, get intent + params as JSON.
    Returns dict like {intent, n, month, event_name} or None on failure.
    """
    try:
        import ollama
        from config import config
        client = ollama.Client(host=config.OLLAMA_HOST)
        prompt = """Classify this calendar question and return ONLY valid JSON, no other text.
Valid intents: next_n_events, events_in_month, check_event, who_made, unknown

Examples:
- "what are the next 3 events?" -> {"intent":"next_n_events","n":3}
- "anything in April?" -> {"intent":"events_in_month","month":"april"}
- "is Summer Camp on the schedule?" -> {"intent":"check_event","event_name":"summer camp"}
- "who made this app?" -> {"intent":"who_made"}

Question: """
        response = client.chat(
            model=config.OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt + transcript}],
        )
        text = response["message"]["content"].strip()
        # Extract JSON (handle markdown, extra text)
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


def _get_snarky_creator_response():
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
        # Strip quotes/preamble
        for c in ('"', "'"):
            if text.startswith(c) and text.endswith(c):
                text = text[1:-1]
        if text and len(text) < 200:
            return text
    except Exception:
        pass
    return "Brother Cochran—Zach, not Mickey. He built this thing. If it's weird, that's on him."


def _answer_from_intent(intent_data):
    """Turn parsed intent into answer text. Returns None if unknown."""
    if not intent_data or intent_data.get("intent") == "unknown":
        return None
    intent = intent_data.get("intent", "")
    if intent == "next_n_events":
        n = intent_data.get("n", 3)
        if not isinstance(n, int) or n < 1 or n > 10:
            n = 3
        return _get_next_n_events_text(n)
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


def _tts_play(resp_or_gather, text):
    """Add TTS via Kokoro blended voice; fall back to Twilio Say if TTS fails."""
    try:
        from tts_handler import tts
        _, url = tts.text_to_speech(text, "webhook")
        if url:
            resp_or_gather.play(url)
            return
    except Exception:
        pass
    resp_or_gather.say(text, voice="alice")


def _get_next_event_text():
    """Get time, date, and title of the next upcoming event."""
    try:
        from sheets_reader import sheets
        upcoming = sheets.get_upcoming_events(days_ahead=90)
        if not upcoming:
            return "No upcoming events."
        e = upcoming[0]
        date_str = e["date"].strftime("%A, %B %d")
        time_str = e.get("time") or "TBD"
        return f"The next event is {e['name']} on {date_str} at {time_str}."
    except Exception:
        return "Sorry, we couldn't look up events right now."


def _get_next_n_events_text(n):
    """Get the next n events."""
    try:
        from sheets_reader import sheets
        upcoming = sheets.get_upcoming_events(days_ahead=90)
        if not upcoming:
            return f"There are no upcoming events."
        events = upcoming[:n]
        parts = []
        for e in events:
            date_str = e["date"].strftime("%A, %B %d")
            time_str = e.get("time") or "TBD"
            parts.append(f"{e['name']} on {date_str} at {time_str}")
        return "The next " + str(n) + " events: " + ". ".join(parts)
    except Exception:
        return "Sorry, we couldn't look up events right now."


def _get_next_week_events_text():
    """Get events for the next 7 days."""
    try:
        from sheets_reader import sheets
        upcoming = sheets.get_upcoming_events(days_ahead=7)
        if not upcoming:
            return "Nothing on the calendar for the next week."
        parts = []
        for e in upcoming[:5]:
            date_str = e["date"].strftime("%A, %B %d")
            time_str = e.get("time") or "TBD"
            parts.append(f"{e['name']} on {date_str} at {time_str}")
        return "Next week: " + ". ".join(parts)
    except Exception:
        return "Sorry, we couldn't look up events right now."


def _get_events_in_month_text(month_name):
    """Get events in a given month (e.g. 'april')."""
    months = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
              "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12}
    try:
        from sheets_reader import sheets
        month_num = months.get(month_name.lower(), None)
        if month_num is None:
            return FALLBACK_RESPONSE
        upcoming = sheets.get_upcoming_events(days_ahead=365)
        in_month = [e for e in upcoming if e["date"].month == month_num]
        if not in_month:
            return f"There are no activities scheduled in {month_name.capitalize()} yet."
        parts = []
        for e in in_month[:5]:
            date_str = e["date"].strftime("%A, %B %d")
            time_str = e.get("time") or "TBD"
            parts.append(f"{e['name']} on {date_str} at {time_str}")
        return f"In {month_name.capitalize()}: " + ". ".join(parts)
    except Exception:
        return "Sorry, we couldn't look up events right now."


def _check_event_on_schedule(search_term):
    """Check if an event matching the search term is on the schedule."""
    try:
        from sheets_reader import sheets
        upcoming = sheets.get_upcoming_events(days_ahead=365)
        term = search_term.lower()
        matches = [e for e in upcoming if term in e["name"].lower()]
        if not matches:
            return f"{search_term} isn't on the schedule yet."
        e = matches[0]
        date_str = e["date"].strftime("%A, %B %d")
        time_str = e.get("time") or "TBD"
        return f"Yes, {e['name']} is on the schedule. It's on {date_str} at {time_str}."
    except Exception:
        return "Sorry, we couldn't look up events right now."


def _handle_question(transcript):
    """
    Handle questions. Try LLM interpretation first, then keyword matching.
    Returns response text or None for unrecognized.
    """
    if not transcript or not str(transcript).strip():
        return None
    q = str(transcript).strip().lower()

    # Try LLM first (caller may skip this if we're in the async process step)
    intent_data = _interpret_question_with_llm(transcript)
    if intent_data:
        answer = _answer_from_intent(intent_data)
        if answer:
            return answer

    # Fall back to keyword matching
    # "What are the next 3 events?" / "next 3" / "next few"
    if "next" in q and any(x in q for x in ["3", "three", "few", "several"]):
        n = 3
        if "5" in q or "five" in q:
            n = 5
        elif "2" in q or "two" in q:
            n = 2
        return _get_next_n_events_text(n)

    # "What's happening next week?" / "what's next week"
    if "next week" in q or ("what" in q and "week" in q) or ("happening" in q and "week" in q):
        return _get_next_week_events_text()

    # "Is there an activity scheduled in April yet?" / "anything in April"
    if any(m in q for m in ["january", "february", "march", "april", "may", "june",
                            "july", "august", "september", "october", "november", "december"]):
        for month in ["january", "february", "march", "april", "may", "june",
                      "july", "august", "september", "october", "november", "december"]:
            if month in q:
                return _get_events_in_month_text(month)

    # "Is Summer Camp on the schedule?" / "Summer Camp"
    if "on the schedule" in q or "on schedule" in q:
        # Extract likely event name - e.g. "is summer camp on the schedule" -> "summer camp"
        rest = q.replace("on the schedule", "").replace("on schedule", "").strip()
        rest = rest.replace("is ", "").replace("are ", "").strip().rstrip("?.")
        if rest and len(rest) > 2:
            return _check_event_on_schedule(rest)

    # Search for event name (e.g. "summer camp", "tubing")
    for phrase in ["summer camp", "ice skating", "tubing", "games", "planning", "kickoff"]:
        if phrase in q:
            return _check_event_on_schedule(phrase)

    # "Who made this app?" / "who created" / "silly app"
    if "who" in q and ("made" in q or "created" in q or "built" in q):
        return _get_snarky_creator_response()
    if "silly app" in q:
        return _get_snarky_creator_response()

    return None


@app.route("/webhook/voice", methods=["GET", "POST"])
def voice_incoming():
    """
    Handle incoming voice call. Announce next event (Kokoro), then Gather for questions.
    """
    from config import config
    base_url = config.WEBHOOK_BASE_URL.rstrip("/")

    resp = VoiceResponse()
    text = _get_next_event_text()
    _tts_play(resp, text)
    gather = Gather(
        input="speech",
        action=f"{base_url}/webhook/voice/gather",
        method="POST",
        timeout=5,
        speech_timeout="auto",
    )
    gather.say("Do you have any questions?", voice="alice")
    resp.append(gather)
    resp.say("Thanks for calling, goodbye.", voice="alice")
    resp.hangup()
    return Response(str(resp), mimetype="application/xml")


@app.route("/webhook/voice/gather", methods=["GET", "POST"])
def voice_gather():
    """
    Handle user speech after Gather. Return immediate ack + Redirect to process.
    """
    from config import config
    base_url = config.WEBHOOK_BASE_URL.rstrip("/")

    transcript = request.values.get("SpeechResult", "").strip()
    resp = VoiceResponse()

    if transcript:
        # Immediate ack so user hears something while LLM runs
        resp.say(ACK_PHRASE, voice="alice")
        process_url = f"{base_url}/webhook/voice/gather/process?t={urllib.parse.quote(transcript)}"
        resp.redirect(process_url, method="GET")
        return Response(str(resp), mimetype="application/xml")

    resp.say("Thanks for calling, goodbye.", voice="alice")
    resp.hangup()
    return Response(str(resp), mimetype="application/xml")


@app.route("/webhook/voice/gather/process", methods=["GET"])
def voice_gather_process():
    """
    Process question (LLM + handlers), return answer TTS + Gather loop.
    """
    from config import config
    base_url = config.WEBHOOK_BASE_URL.rstrip("/")

    transcript = request.args.get("t", "").strip()
    transcript = urllib.parse.unquote(transcript) if transcript else ""

    resp = VoiceResponse()
    reply = _handle_question(transcript) or FALLBACK_RESPONSE
    _tts_play(resp, reply)

    gather = Gather(
        input="speech",
        action=f"{base_url}/webhook/voice/gather",
        method="POST",
        timeout=5,
        speech_timeout="auto",
    )
    gather.say("Do you have any other questions?", voice="alice")
    resp.append(gather)
    resp.say("Thanks for calling, goodbye.", voice="alice")
    resp.hangup()
    return Response(str(resp), mimetype="application/xml")


@app.route("/webhook/sms", methods=["GET", "POST"])
def sms_incoming():
    """
    Handle incoming SMS. Twilio POSTs here with From, To, Body, etc.
    Returns TwiML. Responds with time, date, and title of next event.
    """
    resp = MessagingResponse()
    text = _get_next_event_text()
    resp.message(text)
    return Response(str(resp), mimetype="application/xml")


@app.route("/webhook/health", methods=["GET"])
def health():
    """Health check for the webhook server."""
    return {"status": "ok"}, 200


if __name__ == "__main__":
    port = int(os.getenv("WEBHOOK_PORT", "5000"))
    app.run(host="127.0.0.1", port=port, debug=False)
