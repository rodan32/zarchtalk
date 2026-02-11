"""
Intro QA: after the scheduler generates TTS intro variations, run them through
Whisper (transcribe) then Ollama (compare intended vs heard) to review clarity.
Optional: only runs when WHISPER_HOST is set.
"""
import os
import requests


def transcribe_audio(whisper_host: str, audio_path: str, timeout: int = 30) -> str | None:
    """
    Send audio file to Whisper and return transcript text.
    Tries OpenAI-compatible /v1/audio/transcriptions then /transcribe.
    """
    host = (whisper_host or "").strip().rstrip("/")
    if not host or not os.path.isfile(audio_path):
        return None
    try:
        with open(audio_path, "rb") as f:
            file_data = f.read()
    except OSError:
        return None
    filename = os.path.basename(audio_path)
    # Try OpenAI-style endpoint first
    for path, use_json in [
        ("/v1/audio/transcriptions", True),
        ("/transcribe", False),
    ]:
        url = f"{host}{path}"
        try:
            if use_json:
                # OpenAI: multipart file, model, response_format
                files = {"file": (filename, file_data)}
                data = {"model": "whisper-1", "response_format": "text"}
                r = requests.post(url, files=files, data=data, timeout=timeout)
            else:
                files = {"file": (filename, file_data)}
                r = requests.post(url, files=files, timeout=timeout)
            if r.status_code != 200:
                continue
            text = r.text.strip()
            if r.headers.get("content-type", "").startswith("application/json"):
                try:
                    text = (r.json().get("text") or "").strip()
                except Exception:
                    pass
            if text and len(text) < 10000:
                return text
        except Exception:
            continue
    return None


def review_with_ollama(intended: str, heard: str, ollama_host: str, model: str) -> tuple[str | None, bool, int]:
    """
    Ask Ollama to compare intended script vs what Whisper heard. Returns (review_text, should_regenerate, rating).
    rating is 1-5 (1=perfectly natural and clear, 5=very unclear or awkward). Default 3 if parse fails.
    """
    if not intended or not heard or not (ollama_host or "").strip():
        return None, False, 3
    prompt = """We generated a short voice intro for a church youth calendar line. It strings together a greeting, an event name, and when/where (e.g. "today at 3:00", "Wednesday at the church"). We intended to say this:

INTENDED:
"""
    prompt += intended.strip() + """

When we played the TTS and ran speech-to-text (Whisper), it heard this:

HEARD:
"""
    prompt += heard.strip() + """

In 1-3 short sentences: (1) Is the meaning the same? (2) Does the way the greeting, event name, time, and place are strung together sound natural or awkward? (3) Any specific wording to change for clarity or flow when spoken?
Then on the next line write exactly: REGENERATE: yes   or   REGENERATE: no   (yes if we should re-record this intro to sound more natural or fix clarity; no if it's fine as-is).
Then on the next line write exactly: RATING: 1   or   RATING: 2   or   RATING: 3   or   RATING: 4   or   RATING: 5   (1=perfectly natural and clear, 5=very unclear or awkward).
Reply only with the review and those two lines, no other preamble."""

    try:
        import ollama
        client = ollama.Client(host=ollama_host.strip().rstrip("/"))
        response = client.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        out = (response.get("message") or {}).get("content") or ""
        out = out.strip()
        if not out or len(out) > 700:
            return None, False, 3
        lower = out.lower()
        should_regenerate = "regenerate: yes" in lower
        rating = 3
        for r in (1, 2, 3, 4, 5):
            if f"rating: {r}" in lower:
                rating = r
                break
        # Strip REGENERATE and RATING lines for display
        review = out
        for line in ("REGENERATE: yes", "REGENERATE: no", "regenerate: yes", "regenerate: no"):
            review = review.replace(line, "").strip()
        for r in range(1, 6):
            for prefix in ("RATING:", "rating:"):
                review = review.replace(f"{prefix} {r}", "").strip()
        return review or out, should_regenerate, rating
    except Exception:
        return None, False, 3


def run_single_intro_qa(
    audio_path: str,
    intended_text: str,
    whisper_host: str,
    ollama_host: str,
    ollama_model: str,
) -> tuple[str | None, int]:
    """
    Run QA (Whisper + Ollama) on a single intro audio file. Returns (review_text, rating 1-5).
    Use when comparing multiple versions (original + regens) to keep the best.
    """
    if not (whisper_host and whisper_host.strip()) or not os.path.isfile(audio_path) or not (intended_text and intended_text.strip()):
        return None, 3
    heard = transcribe_audio(whisper_host, audio_path)
    if not heard:
        return None, 3
    review, _, rating = review_with_ollama(intended_text, heard, ollama_host, ollama_model)
    return review, rating


def run_intro_qa(
    intro_audio_paths: list[str],
    intro_texts: list[str],
    whisper_host: str,
    ollama_host: str,
    ollama_model: str,
) -> tuple[list[int], dict[int, int]]:
    """
    For each intro: transcribe with Whisper, then have Ollama compare intended vs heard.
    Logs results to stdout. Returns (indices_to_regenerate, ratings_by_index).
    ratings_by_index has rating 1-5 for every intro we evaluated (1=best, 5=worst).
    Skips if whisper_host is empty.
    """
    indices_to_regenerate: list[int] = []
    ratings_by_index: dict[int, int] = {}
    if not (whisper_host and whisper_host.strip()):
        return indices_to_regenerate, ratings_by_index
    n = min(len(intro_audio_paths), len(intro_texts))
    if n == 0:
        return indices_to_regenerate, ratings_by_index
    print("[Intro QA] Running Whisper → Ollama review on intro variations...")
    for i in range(n):
        path = intro_audio_paths[i]
        intended = intro_texts[i]
        if not path or not os.path.isfile(path) or not (intended and intended.strip()):
            continue
        heard = transcribe_audio(whisper_host, path)
        if not heard:
            print(f"  Intro {i}: Whisper transcription failed or empty")
            continue
        review, should_regenerate, rating = review_with_ollama(intended, heard, ollama_host, ollama_model)
        ratings_by_index[i] = rating
        if review:
            print(f"  Intro {i}: {review} (rating={rating})")
        else:
            print(f"  Intro {i}: (Ollama review skipped or failed) (rating={rating})")
        if should_regenerate:
            indices_to_regenerate.append(i)
            print(f"  Intro {i}: → will re-generate up to 2x and keep best of 3")
    print("[Intro QA] Done.")
    return indices_to_regenerate, ratings_by_index
