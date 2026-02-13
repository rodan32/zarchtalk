"""
Webhook server for incoming Twilio voice calls and SMS.
Twilio POSTs here when someone calls or texts the configured number.
Returns TwiML to handle the response. Uses Kokoro for TTS; optional Applio for more natural voice.
LLM (Ollama) interprets questions for flexible intent handling.
"""
import json
import logging
import os
import random
import urllib.parse
from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse, Gather
from twilio.twiml.messaging_response import MessagingResponse

from question_handler import (
    handle_question as _handle_question,
    get_next_event_text as _get_next_event_text,
    get_current_event as _get_current_event,
    get_during_event_intro_text as _get_during_event_intro_text,
    get_fallback_response,
    FALLBACK_RESPONSES,
)
from phrase_sets import (
    ACK_PHRASES,
    GOODBYE_PHRASE,
    ANY_QUESTIONS_PHRASES,
    ANY_OTHER_QUESTIONS_PHRASES,
    get_phrase_sets_for_tts,
)

app = Flask(__name__)


# Round-robin state file so intro and "any questions" cycle (less robotic)
_ROUNDROBIN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".webhook_roundrobin.json")
_ROUNDROBIN_DEFAULTS = {"intro": 0, "any_questions": 0, "any_other_questions": 0}


def _next_roundrobin(key: str, count: int) -> int:
    """Return next index 0..count-1 for key, cycling. Gunicorn-safe: uses file lock for multi-worker."""
    if count <= 0:
        return 0
    try:
        fd = None
        try:
            import fcntl
            fd = open(_ROUNDROBIN_FILE, "a+")
            fd.seek(0)
            try:
                fcntl.flock(fd.fileno(), fcntl.LOCK_EX)
            except (OSError, AttributeError):
                pass
            raw = fd.read()
            state = json.loads(raw) if raw.strip() else dict(_ROUNDROBIN_DEFAULTS)
            idx = state.get(key, 0) % count
            state[key] = state.get(key, 0) + 1
            fd.seek(0)
            fd.truncate()
            fd.write(json.dumps(state))
            fd.flush()
            return idx
        finally:
            if fd is not None:
                try:
                    import fcntl
                    fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
                except (OSError, AttributeError):
                    pass
                fd.close()
    except Exception:
        return random.randint(0, count - 1) if count else 0


# Phrases that mean "no more questions" / goodbye (substring match for flexible speech)
_NO_MORE_SUBSTRINGS = (
    "no question", "no thanks", "no thank you", "goodbye", "good bye", " bye",
    "that's all", "that is all", "we're good", "we are good", "i'm good", "i am good",
    "all good", "all set", "nothing else", "no more",
)

def _is_no_more_questions(transcript: str) -> bool:
    """True if the user is declining more questions / saying goodbye (no need to run LLM)."""
    if not transcript or not transcript.strip():
        return False
    s = transcript.strip().lower()
    # Exact matches
    if s in ("no", "nope", "nah", "no thanks", "no thank you", "that's all", "that is all",
             "goodbye", "good bye", "bye", "we're good", "we are good", "i'm good", "i am good",
             "all good", "all set", "nothing else", "no questions", "no more", "no more questions"):
        return True
    if s.startswith("no,") or s.startswith("no "):
        rest = s[3:].strip()
        if not rest or rest in ("thanks", "thank you", "thank you very much"):
            return True
    # Short reply containing any "no more questions" / goodbye phrase (e.g. "no questions, bye")
    if len(s) <= 80:
        for phrase in _NO_MORE_SUBSTRINGS:
            if phrase in s:
                return True
    if s in ("thanks", "thank you") or (len(s) < 25 and "thank" in s):
        return True
    return False


def _is_repeat_request(transcript: str) -> bool:
    """True if the user is asking to repeat the last thing (intro or previous answer)."""
    if not transcript or not transcript.strip():
        return False
    s = transcript.strip().lower().rstrip("?.!")
    if s in ("repeat", "again", "what", "what was that", "say that again", "can you repeat", "could you repeat", "can you repeat that", "could you repeat that"):
        return True
    if "repeat" in s and len(s) < 60:
        return True
    if "say that again" in s or "say again" in s:
        return True
    return False


def _tts_play(resp_or_gather, text):
    """Play text using our TTS pipeline (af_heart / enhanced / Applio). Returns True if played, False otherwise."""
    if not text or not str(text).strip():
        return False
    try:
        from tts_handler import tts
        _, url = tts.text_to_speech(text, "webhook")
        if url:
            resp_or_gather.play(url)
            return True
    except Exception:
        pass
    return False


def _play_prepared_or_tts(resp_or_gather, phrase_set: str, fallback_text: str):
    """Play a random cached phrase from the set (af_heart natural) if available, else _tts_play(fallback_text). Returns True if played."""
    try:
        from tts_handler import tts
        _, url = tts.get_prepared_phrase(phrase_set)
        if url:
            resp_or_gather.play(url)
            return True
    except Exception:
        pass
    return _tts_play(resp_or_gather, fallback_text)


def _play_prepared_phrase_at_index(resp_or_gather, phrase_set: str, index: int, allow_tts: bool = True):
    """Play the phrase at index (round-robin) for set; fallback to text if no cache. Never raises.
    If allow_tts is False, use Say only when no cache (avoids blocking first request on TTS or broken phrase URL)."""
    fallbacks = {
        "any_questions": ANY_QUESTIONS_PHRASES,
        "any_other_questions": ANY_OTHER_QUESTIONS_PHRASES,
        "goodbye": (GOODBYE_PHRASE,),
        "fallback": tuple(FALLBACK_RESPONSES),
    }
    try:
        texts = fallbacks.get(phrase_set, ())
        if not texts:
            return
        idx = int(index) % len(texts)
        fallback_text = texts[idx]
    except Exception:
        fallback_text = "Do you have any questions?"
    try:
        from tts_handler import tts
        _, url = tts.get_prepared_phrase_at_index(phrase_set, index)
        if url:
            resp_or_gather.play(url)
            return
    except Exception:
        pass
    if allow_tts and _tts_play(resp_or_gather, fallback_text):
        return
    try:
        resp_or_gather.say(fallback_text, voice="alice")
    except Exception:
        pass


def _ensure_intro_played(resp, intro_text: str):
    """Last-resort: if our TTS failed, use Twilio Say so the caller always hears what's coming next (core task)."""
    if not intro_text or not intro_text.strip():
        return
    try:
        resp.say(intro_text.strip(), voice="alice")
    except Exception:
        pass


@app.route("/webhook/voice", methods=["GET", "POST"])
def voice_incoming():
    """Handle incoming voice call. Announce next event (core task: kids hear what's coming next), then Gather."""
    from config import config
    base_url = config.WEBHOOK_BASE_URL.rstrip("/")

    resp = VoiceResponse()
    # Optional short pause so the phone's audio path is ready (avoids first words being cut off)
    lead_in = getattr(config, "WEBHOOK_LEAD_IN_PAUSE_SECONDS", 0) or 0
    if lead_in > 0:
        resp.pause(length=lead_in)
    intro_played = False
    intro_text = ""
    try:
        from tts_handler import tts
        # If an event is in progress, prefer "We're at the church tonight! Our next activity is..."
        if _get_current_event():
            _, during_url = tts.get_prepared_during_event()
            if during_url:
                resp.play(during_url)
                intro_played = True
            else:
                during_text = _get_during_event_intro_text()
                if during_text:
                    intro_played = _tts_play(resp, during_text)
        if not intro_played:
            intro_idx = _next_roundrobin("intro", 3)
            _, intro_url = tts.get_prepared_intro_at_index(intro_idx)
            if intro_url:
                resp.play(intro_url)
                intro_played = True
            else:
                _, intro_url = tts.get_prepared_intro()
                if intro_url:
                    resp.play(intro_url)
                    intro_played = True
                else:
                    intro_text = _get_next_event_text()
                    intro_played = _tts_play(resp, intro_text)
    except Exception:
        try:
            from tts_handler import tts as _tts
            _, intro_url = _tts.get_prepared_intro()
            if intro_url:
                resp.play(intro_url)
                intro_played = True
            else:
                intro_text = _get_next_event_text()
                intro_played = _tts_play(resp, intro_text)
        except Exception:
            try:
                intro_text = _get_next_event_text()
                intro_played = _tts_play(resp, intro_text)
            except Exception:
                intro_text = "Check the calendar for upcoming activities."
    if not intro_played and intro_text:
        _ensure_intro_played(resp, intro_text)
    gather = Gather(
        input="speech",
        action=f"{base_url}/webhook/voice/gather",
        method="POST",
        timeout=5,
        speech_timeout="auto",
    )
    try:
        aq_idx = _next_roundrobin("any_questions", len(ANY_QUESTIONS_PHRASES))
        _play_prepared_phrase_at_index(gather, "any_questions", aq_idx)
    except Exception:
        try:
            _play_prepared_or_tts(gather, "any_questions", random.choice(ANY_QUESTIONS_PHRASES))
        except Exception:
            gather.say("Do you have any questions?", voice="alice")
    resp.append(gather)
    _play_prepared_or_tts(resp, "goodbye", GOODBYE_PHRASE)
    resp.hangup()
    return Response(str(resp), mimetype="application/xml")


@app.route("/webhook/voice/gather", methods=["GET", "POST"])
def voice_gather():
    """Handle user speech after Gather. On error we log full traceback and re-raise so the root cause is visible."""
    logging.getLogger(__name__).info("voice_gather: request received")
    try:
        return _voice_gather_impl()
    except Exception:
        logging.exception("voice_gather failed (re-raising to get 500 and traceback in logs)")
        raise


def _voice_gather_impl():
    from config import config
    base_url = config.WEBHOOK_BASE_URL.rstrip("/")
    resp = VoiceResponse()
    transcript = (request.values.get("SpeechResult") or "").strip()
    last_reply = request.values.get("last_reply", "")
    try:
        if last_reply:
            last_reply = urllib.parse.unquote(last_reply)
    except Exception:
        last_reply = ""

    if transcript:
        if _is_no_more_questions(transcript):
            _play_prepared_or_tts(resp, "goodbye", GOODBYE_PHRASE)
            resp.hangup()
            return Response(str(resp), mimetype="application/xml")
        if _is_repeat_request(transcript):
            if last_reply:
                _tts_play(resp, last_reply)
                try:
                    lp = urllib.parse.quote(str(last_reply)[:1500])
                except Exception:
                    lp = ""
                gather = Gather(
                    input="speech",
                    action=f"{base_url}/webhook/voice/gather" + (f"?last_reply={lp}" if lp else ""),
                    method="POST",
                    timeout=5,
                    speech_timeout="auto",
                )
                try:
                    aq_idx = _next_roundrobin("any_other_questions", len(ANY_OTHER_QUESTIONS_PHRASES))
                    _play_prepared_phrase_at_index(gather, "any_other_questions", aq_idx)
                except Exception:
                    gather.say("Anything else?", voice="alice")
                resp.append(gather)
            else:
                try:
                    from tts_handler import tts
                    intro_idx = _next_roundrobin("intro", 3)
                    _, intro_url = tts.get_prepared_intro_at_index(intro_idx)
                    if intro_url:
                        resp.play(intro_url)
                    else:
                        intro_text = _get_next_event_text()
                        _tts_play(resp, intro_text)
                except Exception:
                    _tts_play(resp, _get_next_event_text())
                gather = Gather(
                    input="speech",
                    action=f"{base_url}/webhook/voice/gather",
                    method="POST",
                    timeout=5,
                    speech_timeout="auto",
                )
                try:
                    aq_idx = _next_roundrobin("any_questions", len(ANY_QUESTIONS_PHRASES))
                    _play_prepared_phrase_at_index(gather, "any_questions", aq_idx)
                except Exception:
                    gather.say("Do you have any questions?", voice="alice")
                resp.append(gather)
            _play_prepared_or_tts(resp, "goodbye", GOODBYE_PHRASE)
            resp.hangup()
            return Response(str(resp), mimetype="application/xml")
        # Ask question -> ack and redirect to process
        try:
            from tts_handler import tts
            ack_path, ack_url = tts.get_prepared_ack()
            if ack_url:
                resp.play(ack_url)
            else:
                _tts_play(resp, random.choice(ACK_PHRASES))
        except Exception:
            _tts_play(resp, ACK_PHRASES[0])
        try:
            process_url = f"{base_url}/webhook/voice/gather/process?t={urllib.parse.quote(transcript)}"
        except Exception:
            process_url = f"{base_url}/webhook/voice/gather/process?t="
        resp.redirect(process_url, method="GET")
        return Response(str(resp), mimetype="application/xml")

    _play_prepared_or_tts(resp, "goodbye", GOODBYE_PHRASE)
    resp.hangup()
    return Response(str(resp), mimetype="application/xml")


@app.route("/webhook/voice/gather/process", methods=["GET"])
def voice_gather_process():
    """Process question (LLM + handlers), return answer TTS + Gather loop. On error we log and re-raise for root cause."""
    try:
        return _voice_gather_process_impl()
    except Exception:
        logging.exception("voice_gather_process failed (re-raising to get 500 and traceback in logs)")
        raise


def _voice_gather_process_impl():
    from config import config
    base_url = config.WEBHOOK_BASE_URL.rstrip("/")
    try:
        transcript = request.args.get("t", "").strip()
        if transcript:
            try:
                transcript = urllib.parse.unquote(transcript)
            except Exception:
                pass
    except Exception:
        transcript = ""

    resp = VoiceResponse()
    if _is_no_more_questions(transcript):
        _play_prepared_or_tts(resp, "goodbye", GOODBYE_PHRASE)
        resp.hangup()
        return Response(str(resp), mimetype="application/xml")

    reply = _handle_question(transcript) or get_fallback_response()
    if not reply:
        reply = get_fallback_response()
    if reply in FALLBACK_RESPONSES:
        # Don't log repeat-like requests as unanswered (they're handled by replay, not as a real question)
        if not _is_repeat_request(transcript):
            try:
                from database import db
                db.log_unanswered_question(transcript, "voice")
            except Exception:
                pass
    reply_played = _play_prepared_or_tts(resp, "fallback", reply) if reply in FALLBACK_RESPONSES else _tts_play(resp, reply)
    if not reply_played and reply:
        try:
            resp.say(str(reply)[:5000], voice="alice")
        except Exception:
            pass

    try:
        last_reply_param = urllib.parse.quote(str(reply)[:1500]) if reply else ""
    except Exception:
        last_reply_param = ""
    action_url = f"{base_url}/webhook/voice/gather"
    if last_reply_param:
        action_url = f"{action_url}?last_reply={last_reply_param}"
    gather = Gather(
        input="speech",
        action=action_url,
        method="POST",
        timeout=5,
        speech_timeout="auto",
    )
    try:
        aq_idx = _next_roundrobin("any_other_questions", len(ANY_OTHER_QUESTIONS_PHRASES))
        _play_prepared_phrase_at_index(gather, "any_other_questions", aq_idx)
    except Exception:
        try:
            _play_prepared_or_tts(gather, "any_other_questions", random.choice(ANY_OTHER_QUESTIONS_PHRASES))
        except Exception:
            gather.say("Anything else?", voice="alice")
    resp.append(gather)
    _play_prepared_or_tts(resp, "goodbye", GOODBYE_PHRASE)
    resp.hangup()
    return Response(str(resp), mimetype="application/xml")


@app.route("/webhook/sms", methods=["GET", "POST"])
def sms_incoming():
    """Handle incoming SMS. Core task: send next event info (or a safe fallback)."""
    resp = MessagingResponse()
    try:
        text = _get_next_event_text()
    except Exception:
        text = "Check the calendar for upcoming activities."
    resp.message(text or "Check the calendar for upcoming activities.")
    return Response(str(resp), mimetype="application/xml")


@app.route("/webhook/cleanup/audio", methods=["GET"])
def cleanup_audio():
    """Remove old TTS audio files (keeps cached ack/intro). Optional ?days=7. Returns JSON."""
    try:
        from tts_handler import tts
        from config import config
        days = request.args.get("days", type=int)
        if days is not None and (days < 1 or days > 365):
            return {"ok": False, "error": "days must be 1–365"}, 400
        deleted = tts.cleanup_old_files(days_old=days if days is not None else config.AUDIO_CLEANUP_DAYS)
        return {"ok": True, "deleted": deleted}
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500


@app.route("/webhook/health", methods=["GET"])
def health():
    """Health check for the webhook server."""
    return {"status": "ok"}, 200


# Prewarm (ack + phrases) runs in the scheduler service so webhook workers don't all run TTS at startup.
# First call after deploy may use on-demand TTS until scheduler has run once.

if __name__ == "__main__":
    port = int(os.getenv("WEBHOOK_PORT", "5000"))
    host = os.getenv("WEBHOOK_HOST", "127.0.0.1")
    app.run(host=host, port=port, debug=False)
