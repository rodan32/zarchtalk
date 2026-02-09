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


def review_with_ollama(intended: str, heard: str, ollama_host: str, model: str) -> str | None:
    """
    Ask Ollama to compare intended script vs what Whisper heard. Returns review text or None.
    """
    if not intended or not heard or not (ollama_host or "").strip():
        return None
    prompt = """We generated a short voice intro for a church youth calendar line. We intended to say this:

INTENDED:
"""
    prompt += intended.strip() + """

When we played the TTS and ran speech-to-text (Whisper), it heard this:

HEARD:
"""
    prompt += heard.strip() + """

In 1-2 short sentences: Is the meaning the same? Any wording we should change for clarity when spoken?
Reply only with the review, no preamble."""

    try:
        import ollama
        client = ollama.Client(host=ollama_host.strip().rstrip("/"))
        response = client.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        out = (response.get("message") or {}).get("content") or ""
        return out.strip() if out and len(out) < 500 else None
    except Exception:
        return None


def run_intro_qa(
    intro_audio_paths: list[str],
    intro_texts: list[str],
    whisper_host: str,
    ollama_host: str,
    ollama_model: str,
) -> None:
    """
    For each intro: transcribe with Whisper, then have Ollama compare intended vs heard.
    Logs results to stdout. Skips if whisper_host is empty.
    """
    if not (whisper_host and whisper_host.strip()):
        return
    n = min(len(intro_audio_paths), len(intro_texts))
    if n == 0:
        return
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
        review = review_with_ollama(intended, heard, ollama_host, ollama_model)
        if review:
            print(f"  Intro {i}: {review}")
        else:
            print(f"  Intro {i}: (Ollama review skipped or failed)")
    print("[Intro QA] Done.")
