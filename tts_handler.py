"""
TTS handler for Kokoro TTS integration.
Converts text to speech for voice reminders.
Optional: run Kokoro output through Applio for more natural-sounding voice.
For a warmer, friendlier sound: in Applio's UI use a warmer voice model,
or add a little Reverb in the inference post-processing settings.
"""
import logging
import os
import requests
import tempfile
import random
from datetime import datetime
import hashlib
from config import config

# Timeout for enhanced TTS and Applio (same host often). Long enough for inference, not forever.
ENHANCED_APPLIO_TIMEOUT = 30

class TTSHandler:
    def __init__(self):
        self.tts_host = config.KOKORO_TTS_HOST
        self.voice = config.KOKORO_VOICE
        self.speed = config.KOKORO_SPEED
        self.audio_output_dir = config.AUDIO_OUTPUT_DIR
        self.audio_base_url = config.AUDIO_BASE_URL
        self.enhanced_host = (config.ENHANCED_TTS_HOST or "").strip().rstrip("/")
        self.enhanced_style = getattr(config, "ENHANCED_TTS_STYLE", "moderate") or "moderate"
        self.applio_host = (config.APPLIO_HOST or "").strip().rstrip("/")
        os.makedirs(self.audio_output_dir, exist_ok=True)
        self._ack_prefix = "ack"
        self._intro_prefix = "intro"
        self._intro_count = 3  # intro_0, intro_1, intro_2
        self._phrase_prefix = "phrase"

    def refresh_prepared_acks(self, phrases: list[str]) -> None:
        """
        Pre-generate TTS for multiple short ack phrases and save as ack_0.*, ack_1.*, etc.
        Call weekly from scheduler; webhook uses get_prepared_ack() to play a random one.
        """
        import shutil
        for i, phrase in enumerate(phrases):
            if not (phrase and phrase.strip()):
                continue
            path, _ = self.text_to_speech(phrase.strip(), recipient_phone="ack")
            if not path or not os.path.isfile(path):
                continue
            ext = os.path.splitext(path)[1].lstrip(".")
            dest = os.path.join(self.audio_output_dir, f"{self._ack_prefix}_{i}.{ext}")
            try:
                shutil.copy2(path, dest)
                if path != dest:
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                for other in ("mp3", "wav"):
                    if other != ext:
                        other_path = os.path.join(self.audio_output_dir, f"{self._ack_prefix}_{i}.{other}")
                        if os.path.isfile(other_path):
                            try:
                                os.remove(other_path)
                            except OSError:
                                pass
            except Exception as e:
                print(f"Failed to cache ack {i}: {e}")

    def get_prepared_ack(self, phrase: str | None = None) -> tuple[str | None, str | None]:
        """
        Return (local_path, public_url) for a pre-generated ack. If phrase is None (default),
        returns a random cached ack from refresh_prepared_acks(). If phrase is given, returns
        that specific cached ack if present, or generates and returns it once (backward compat).
        """
        # Collect all cached ack_0, ack_1, ...
        candidates = []
        for f in os.listdir(self.audio_output_dir):
            if not f.startswith(self._ack_prefix + "_"):
                continue
            base, ext = os.path.splitext(f)
            if ext.lstrip(".").lower() not in ("mp3", "wav"):
                continue
            try:
                idx = int(base.split("_", 2)[1])
            except (IndexError, ValueError):
                continue
            path = os.path.join(self.audio_output_dir, f)
            if os.path.isfile(path):
                url = f"{self.audio_base_url}/{base}{ext}"
                candidates.append((path, url))
        if candidates:
            return random.choice(candidates)
        # No cache: if phrase given, generate once
        if phrase and phrase.strip():
            path, url = self.text_to_speech(phrase.strip(), recipient_phone="ack")
            if path and url and os.path.isfile(path):
                import shutil
                ext = os.path.splitext(path)[1].lstrip(".")
                ack_path = os.path.join(self.audio_output_dir, f"{self._ack_prefix}_0.{ext}")
                try:
                    shutil.copy2(path, ack_path)
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                    return ack_path, f"{self.audio_base_url}/{self._ack_prefix}_0.{ext}"
                except Exception:
                    return path, url
        return None, None

    def refresh_prepared_intros(self, intro_texts: list[str], max_retries: int = 2) -> None:
        """
        Pre-generate TTS for 2–3 next-event intro variations and save as intro_0.*, intro_1.*, etc.
        Call this when the sheet/calendar is refreshed so callers get a ready intro without TTS delay.
        Retries each index up to max_retries times if TTS returns no file (e.g. transient Applio/Kokoro errors).
        """
        import shutil
        for i, text in enumerate(intro_texts):
            if i >= self._intro_count or not (text and text.strip()):
                continue
            path = None
            for attempt in range(max_retries + 1):
                path, _ = self.text_to_speech(text, recipient_phone="intro")
                if path and os.path.isfile(path):
                    break
                if attempt < max_retries:
                    print(f"Intro {i} TTS attempt {attempt + 1} failed, retrying...")
            if not path or not os.path.isfile(path):
                print(f"Failed to generate intro {i} after {max_retries + 1} attempt(s)")
                continue
            ext = os.path.splitext(path)[1].lstrip(".")
            dest = os.path.join(self.audio_output_dir, f"{self._intro_prefix}_{i}.{ext}")
            try:
                shutil.copy2(path, dest)
                if path != dest:
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                # Remove other extensions for this index so only one intro_N.* exists
                for other in ("mp3", "wav"):
                    if other != ext:
                        other_path = os.path.join(self.audio_output_dir, f"{self._intro_prefix}_{i}.{other}")
                        if os.path.isfile(other_path):
                            try:
                                os.remove(other_path)
                            except OSError:
                                pass
            except Exception as e:
                print(f"Failed to cache intro {i}: {e}")

    def generate_intro_to_path(self, text: str, output_base_path: str, max_retries: int = 2) -> str | None:
        """
        Generate intro TTS and write to output_base_path + extension (e.g. .../intro_0_regen1.mp3).
        Returns the path to the written file, or None on failure. Used to produce candidate
        versions for QA so we can keep the best of original + 2 regens.
        """
        import shutil
        if not (text and text.strip()):
            return None
        path = None
        for attempt in range(max_retries + 1):
            path, _ = self.text_to_speech(text.strip(), recipient_phone="intro")
            if path and os.path.isfile(path):
                break
            if attempt < max_retries:
                print(f"Intro TTS attempt {attempt + 1} failed, retrying...")
        if not path or not os.path.isfile(path):
            return None
        ext = os.path.splitext(path)[1].lstrip(".")
        base = output_base_path.rstrip(".mp3").rstrip(".wav").rstrip(".")
        dest = base + "." + ext
        try:
            shutil.copy2(path, dest)
            if path != dest:
                try:
                    os.remove(path)
                except OSError:
                    pass
            return dest if os.path.isfile(dest) else None
        except Exception:
            return None

    def refresh_prepared_intro_at_index(self, index: int, text: str, max_retries: int = 2) -> bool:
        """
        Re-generate and cache a single intro at the given index (0-based). Used when QA
        suggests re-recording for naturalness. Returns True if cached successfully.
        """
        import shutil
        if index < 0 or index >= self._intro_count or not (text and text.strip()):
            return False
        out_base = os.path.join(self.audio_output_dir, f"{self._intro_prefix}_{index}")
        path = self.generate_intro_to_path(text.strip(), out_base, max_retries)
        if not path or not os.path.isfile(path):
            print(f"Failed to re-generate intro {index} after {max_retries + 1} attempt(s)")
            return False
        ext = os.path.splitext(path)[1].lstrip(".")
        dest = os.path.join(self.audio_output_dir, f"{self._intro_prefix}_{index}.{ext}")
        try:
            if path != dest:
                shutil.copy2(path, dest)
            for other in ("mp3", "wav"):
                if other != ext:
                    other_path = os.path.join(self.audio_output_dir, f"{self._intro_prefix}_{index}.{other}")
                    if os.path.isfile(other_path):
                        try:
                            os.remove(other_path)
                        except OSError:
                            pass
            return True
        except Exception as e:
            print(f"Failed to cache intro {index}: {e}")
            return False

    def get_prepared_intro(self) -> tuple[str | None, str | None]:
        """
        Return (local_path, public_url) for a random pre-generated next-event intro,
        or (None, None) if none are cached. Use when answering a call to avoid TTS delay.
        """
        candidates = []
        for i in range(self._intro_count):
            for ext in ("mp3", "wav"):
                path = os.path.join(self.audio_output_dir, f"{self._intro_prefix}_{i}.{ext}")
                if os.path.isfile(path):
                    url = f"{self.audio_base_url}/{self._intro_prefix}_{i}.{ext}"
                    candidates.append((path, url))
                    break
        if not candidates:
            return None, None
        path, url = random.choice(candidates)
        return path, url

    def get_prepared_intro_at_index(self, index: int) -> tuple[str | None, str | None]:
        """Return (path, url) for the intro at the given index (0-based), or (None, None)."""
        i = index % self._intro_count
        for ext in ("mp3", "wav"):
            path = os.path.join(self.audio_output_dir, f"{self._intro_prefix}_{i}.{ext}")
            if os.path.isfile(path):
                url = f"{self.audio_base_url}/{self._intro_prefix}_{i}.{ext}"
                return path, url
        return None, None

    def get_prepared_intro_paths(self) -> list[tuple[int, str]]:
        """Return list of (index, path) for cached intro audio so callers can align paths with intro_texts by index."""
        result = []
        for i in range(self._intro_count):
            for ext in ("mp3", "wav"):
                path = os.path.join(self.audio_output_dir, f"{self._intro_prefix}_{i}.{ext}")
                if os.path.isfile(path):
                    result.append((i, path))
                    break
        return result

    def refresh_prepared_phrases(self, phrases_dict: dict[str, list[str]]) -> None:
        """
        Pre-generate TTS for phrase sets (any_questions, any_other_questions, fallback, goodbye)
        so they all use the same af_heart/natural pipeline. Call at webhook startup.
        """
        import shutil
        for set_name, texts in phrases_dict.items():
            if not texts:
                continue
            safe_name = "".join(c if c.isalnum() or c == "_" else "_" for c in set_name)
            for i, text in enumerate(texts):
                if not (text and text.strip()):
                    continue
                path, _ = self.text_to_speech(text.strip(), recipient_phone=f"phrase_{set_name}")
                if not path or not os.path.isfile(path):
                    continue
                ext = os.path.splitext(path)[1].lstrip(".")
                dest = os.path.join(self.audio_output_dir, f"{self._phrase_prefix}_{safe_name}_{i}.{ext}")
                try:
                    shutil.copy2(path, dest)
                    if path != dest:
                        try:
                            os.remove(path)
                        except OSError:
                            pass
                    for other in ("mp3", "wav"):
                        if other != ext:
                            other_path = os.path.join(self.audio_output_dir, f"{self._phrase_prefix}_{safe_name}_{i}.{other}")
                            if os.path.isfile(other_path):
                                try:
                                    os.remove(other_path)
                                except OSError:
                                    pass
                except Exception as e:
                    print(f"Failed to cache phrase {set_name}[{i}]: {e}")

    def get_prepared_phrase(self, set_name: str) -> tuple[str | None, str | None]:
        """
        Return (local_path, public_url) for a random pre-generated phrase in the set,
        or (None, None) if none cached. set_name e.g. 'any_questions', 'fallback', 'goodbye'.
        """
        safe_name = "".join(c if c.isalnum() or c == "_" else "_" for c in set_name)
        prefix = f"{self._phrase_prefix}_{safe_name}_"
        candidates = []
        for f in os.listdir(self.audio_output_dir):
            if f.startswith(prefix) and os.path.isfile(os.path.join(self.audio_output_dir, f)):
                path = os.path.join(self.audio_output_dir, f)
                ext = os.path.splitext(f)[1].lstrip(".")
                url = f"{self.audio_base_url}/{f}"
                candidates.append((path, url))
        if not candidates:
            return None, None
        return random.choice(candidates)

    def get_prepared_phrase_at_index(self, set_name: str, index: int) -> tuple[str | None, str | None]:
        """Return (path, url) for the phrase at the given index in the set, or (None, None). Never raises."""
        try:
            safe_name = "".join(c if c.isalnum() or c == "_" else "_" for c in set_name)
            prefix = f"{self._phrase_prefix}_{safe_name}_"
            candidates = []
            for f in sorted(os.listdir(self.audio_output_dir)):
                if f.startswith(prefix) and os.path.isfile(os.path.join(self.audio_output_dir, f)):
                    path = os.path.join(self.audio_output_dir, f)
                    url = f"{self.audio_base_url}/{f}"
                    candidates.append((path, url))
            if not candidates:
                return None, None
            return candidates[int(index) % len(candidates)]
        except Exception:
            return None, None

    def _applio_convert(self, source_mp3_path: str) -> str | None:
        """
        Run Kokoro audio through Applio (Gradio) for more natural voice.
        Returns local path to converted audio file, or None on failure.
        """
        if not self.applio_host:
            return None
        try:
            from gradio_client import Client
            client = Client(self.applio_host)
            # Applio inference tab: first input is the audio file.
            # Default predict uses the first API; result is downloaded to a local path.
            result = client.predict(source_mp3_path)
            if result is None:
                return None
            out_path = None
            if isinstance(result, str) and (os.path.isfile(result) or result.startswith("http")):
                out_path = result
            elif isinstance(result, (list, tuple)) and len(result) > 0:
                out_path = result[0]
            if out_path and isinstance(out_path, str):
                if out_path.startswith("http"):
                    r = requests.get(out_path, timeout=ENHANCED_APPLIO_TIMEOUT)
                    if r.status_code == 200:
                        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                            f.write(r.content)
                            return f.name
                elif os.path.isfile(out_path):
                    return out_path
            return None
        except Exception as e:
            logging.getLogger(__name__).warning("Applio conversion failed (using Kokoro only): %s", e)
            return None

    def _try_enhanced_tts(self, text: str) -> tuple[str | None, str | None]:
        """Use enhanced TTS (natural speech, style) if ENHANCED_TTS_HOST is set. Returns (local_path, public_url) or (None, None)."""
        if not self.enhanced_host:
            return None, None
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            phone_hash = hashlib.md5(b"webhook").hexdigest()[:8]
            # filename/extension set below after we see actual response format
            local_path = None
            r = requests.post(
                f"{self.enhanced_host}/v1/audio/speech",
                json={
                    "text": text,
                    "voice": self.voice,
                    "style": self.enhanced_style,
                    "enhance": True,
                },
                timeout=ENHANCED_APPLIO_TIMEOUT,
            )
            if r.status_code != 200 or not r.content:
                return None, None
            # Use correct extension: service may return MP3 despite Content-Type audio/wav
            if r.content[:3] == b"ID3" or (len(r.content) >= 2 and r.content[0:2] == b"\xff\xfb"):
                ext = "mp3"
            elif r.content[:4] == b"RIFF":
                ext = "wav"
            else:
                ct = r.headers.get("Content-Type", "").split(";")[0].strip().split("/")[-1]
                ext = "mp3" if ct == "mpeg" else "wav" if ct == "wav" else "wav"
            filename = f"reminder_{timestamp}_{phone_hash}.{ext}"
            local_path = os.path.join(self.audio_output_dir, filename)
            with open(local_path, "wb") as f:
                f.write(r.content)
            public_url = f"{self.audio_base_url}/{filename}"
            return local_path, public_url
        except Exception as e:
            logging.getLogger(__name__).warning("Enhanced TTS failed (falling back to Kokoro): %s", e)
            return None, None

    def text_to_speech(self, text, recipient_phone=None):
        """
        Convert text to speech. Uses enhanced TTS if ENHANCED_TTS_HOST is set (natural speech),
        else Kokoro. Optionally runs result through Applio for voice conversion.

        Returns:
            Tuple of (local_path, public_url) or (None, None) on failure
        """
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            phone_hash = hashlib.md5((recipient_phone or "unknown").encode()).hexdigest()[:8]
            filename = f"reminder_{timestamp}_{phone_hash}.mp3"
            local_path = os.path.join(self.audio_output_dir, filename)
            public_url = f"{self.audio_base_url}/{filename}"

            # Prefer enhanced TTS (natural pauses, style) when configured
            if self.enhanced_host:
                enhanced_path, enhanced_url = self._try_enhanced_tts(text)
                if enhanced_path and enhanced_url:
                    print(f"Generated TTS audio (enhanced): {os.path.basename(enhanced_path)}")
                    return enhanced_path, enhanced_url

            # Kokoro TTS (OpenAI-compatible /v1/audio/speech)
            response = requests.post(
                f"{self.tts_host}/v1/audio/speech",
                json={
                    "model": "tts-1",
                    "input": text,
                    "voice": self.voice,
                    "response_format": "mp3",
                    "speed": self.speed,
                    "stream": True,
                },
                timeout=60,
                stream=True,
            )
            if response.status_code != 200:
                print(f"TTS generation failed: {response.status_code}")
                return None, None

            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            # Optional: Applio voice conversion for more natural sound
            if self.applio_host:
                converted = self._applio_convert(local_path)
                if converted and os.path.isfile(converted):
                    import shutil
                    shutil.copy2(converted, local_path)
                    if converted != local_path and converted.startswith(tempfile.gettempdir()):
                        try:
                            os.remove(converted)
                        except OSError:
                            pass
                    print(f"Generated TTS audio (Kokoro + Applio): {filename}")
                else:
                    print(f"Generated TTS audio (Kokoro): {filename}")
            else:
                print(f"Generated TTS audio: {filename}")
            return local_path, public_url
        except Exception as e:
            print(f"Error generating TTS: {e}")
            return None, None
    
    def text_to_speech_alternative_api(self, text, recipient_phone=None):
        """
        Alternative TTS implementation if your Kokoro API differs
        Adjust the endpoint and parameters based on your setup
        """
        
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            phone_hash = hashlib.md5(recipient_phone.encode()).hexdigest()[:8] if recipient_phone else 'unknown'
            filename = f"reminder_{timestamp}_{phone_hash}.wav"
            
            local_path = os.path.join(self.audio_output_dir, filename)
            public_url = f"{self.audio_base_url}/{filename}"
            
            # Alternative API format - adjust as needed
            params = {
                'text': text,
                'voice_id': 'default',
                'output_format': 'wav'
            }
            
            response = requests.get(
                f"{self.tts_host}/tts",
                params=params,
                timeout=30
            )
            
            if response.status_code == 200:
                with open(local_path, 'wb') as f:
                    f.write(response.content)
                
                print(f"Generated TTS audio: {filename}")
                return local_path, public_url
            else:
                return None, None
        
        except Exception as e:
            print(f"Error generating TTS: {e}")
            return None, None
    
    def cleanup_old_files(self, days_old: int | None = None) -> int:
        """
        Clean up audio files older than specified days. Skips cached ack/intro
        files so they are only removed when stale and regenerated.

        Args:
            days_old: Delete files older than this many days (default from config).

        Returns:
            Number of files deleted.
        """
        if days_old is None:
            days_old = getattr(config, "AUDIO_CLEANUP_DAYS", 7)
        deleted = 0
        try:
            now = datetime.now()
            # Keep these; they are overwritten by scheduler/webhook and should not be removed by age
            keep_prefixes = (self._ack_prefix + "_", self._intro_prefix + "_", self._phrase_prefix + "_")
            for filename in os.listdir(self.audio_output_dir):
                filepath = os.path.join(self.audio_output_dir, filename)
                if not os.path.isfile(filepath):
                    continue
                if any(filename.startswith(p) for p in keep_prefixes):
                    continue
                file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
                if (now - file_time).days > days_old:
                    os.remove(filepath)
                    deleted += 1
                    print(f"Deleted old audio file: {filename}")
        except Exception as e:
            print(f"Error cleaning up old files: {e}")
        return deleted
    
    def test_tts_connection(self):
        """Test if TTS service is accessible"""
        try:
            response = requests.get(f"{self.tts_host}/health", timeout=5)
            return response.status_code == 200
        except:
            try:
                # Try alternative health check endpoint
                response = requests.get(self.tts_host, timeout=5)
                return response.status_code in [200, 404]  # 404 might mean no health endpoint but service is up
            except:
                return False

# Create TTS handler instance
tts = TTSHandler()
