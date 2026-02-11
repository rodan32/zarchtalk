"""
Shared phrase sets for TTS pre-generation (ack, intro, any_questions, goodbye, fallback).
Used by webhook and scheduler so pre-generated audio is populated and used everywhere.
"""
from question_handler import FALLBACK_RESPONSES

# Short ack phrases played after user speaks (one chosen at random when serving a call)
ACK_PHRASES = (
    "Sure, let me check.",
    "One sec.",
    "Let me look.",
    "Hang on.",
    "One moment.",
)
ACK_PHRASE = ACK_PHRASES[0]  # fallback if no cached ack
GOODBYE_PHRASE = "Thanks for calling, goodbye."


def get_ack_phrases_for_tts():
    """Return list of ack phrases for tts.refresh_prepared_acks()."""
    return list(ACK_PHRASES)

ANY_QUESTIONS_PHRASES = (
    "Do you have any questions?",
    "Got any questions?",
    "Any questions?",
    "Questions for me?",
)
ANY_OTHER_QUESTIONS_PHRASES = (
    "Do you have any other questions?",
    "Any other questions?",
    "Anything else?",
    "Something else you'd like to know?",
)


def get_phrase_sets_for_tts():
    """Return dict of phrase set name -> list of texts for tts.refresh_prepared_phrases()."""
    return {
        "any_questions": list(ANY_QUESTIONS_PHRASES),
        "any_other_questions": list(ANY_OTHER_QUESTIONS_PHRASES),
        "goodbye": [GOODBYE_PHRASE],
        "fallback": list(FALLBACK_RESPONSES),
    }
