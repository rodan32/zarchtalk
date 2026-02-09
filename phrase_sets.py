"""
Shared phrase sets for TTS pre-generation (ack, intro, any_questions, goodbye, fallback).
Used by webhook and scheduler so pre-generated audio is populated and used everywhere.
"""
from question_handler import FALLBACK_RESPONSES

ACK_PHRASE = "Sure, let me check."
GOODBYE_PHRASE = "Thanks for calling, goodbye."

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
