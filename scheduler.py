"""
Main scheduler for ZarchTalk
Periodically checks for events needing reminders and sends them.
Ack and phrase sets refresh weekly; intros refresh only when next event or date threshold changes.
"""
import json
import os
import time
import schedule
from datetime import datetime, timedelta, date
from config import config
from database import db
from sheets_reader import sheets
from message_gen import message_gen
from question_handler import get_next_event_intro_variations, get_next_event_intro_signature
from phrase_sets import get_phrase_sets_for_tts, get_ack_phrases_for_tts
from tts_handler import tts
from twilio_handler import twilio_handler
from intro_qa import run_intro_qa, run_single_intro_qa
from report_unanswered import send_unanswered_report

class ReminderScheduler:
    def __init__(self):
        self.last_check = {}  # Track last check time for each event
        self.debug = config.DEBUG_MODE
        self._state_path = getattr(config, "SCHEDULER_STATE_PATH", "./scheduler_state.json")
        # Don't send outbound reminders until initial pre-warm (ack + phrase) is done; we always accept incoming traffic
        self._prewarm_done = False

    def _load_intro_signature(self):
        """Load last intro signature from state file for change detection."""
        try:
            if os.path.isfile(self._state_path):
                with open(self._state_path) as f:
                    data = json.load(f)
                sig = data.get("last_intro_signature")
                if sig and isinstance(sig, list) and len(sig) == 5:
                    return tuple(sig)
        except Exception:
            pass
        return None

    def _save_intro_signature(self, sig):
        """Persist intro signature so we only refresh when event or reference date changes."""
        try:
            data = {}
            if os.path.isfile(self._state_path):
                with open(self._state_path) as f:
                    data = json.load(f)
            data["last_intro_signature"] = list(sig)
            with open(self._state_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Could not save scheduler state: {e}")

    def _run_intro_qa_and_regen(self, intro_texts: list):
        """Run QA on prepared intros; for those with feedback, regen up to 2x and keep best of 3."""
        try:
            indexed_paths = tts.get_prepared_intro_paths()
            if not indexed_paths:
                return
            paths = [p for i, p in indexed_paths if i < len(intro_texts)]
            texts = [intro_texts[i] for i, p in indexed_paths if i < len(intro_texts)]
            if not paths or len(texts) != len(paths):
                return
            indices_to_regenerate, ratings_by_index = run_intro_qa(
                paths, texts,
                config.WHISPER_HOST, config.OLLAMA_HOST, config.OLLAMA_MODEL,
            )
            audio_dir = tts.audio_output_dir
            path_by_index = {i: p for i, p in indexed_paths if i < len(intro_texts)}
            for idx in indices_to_regenerate:
                if idx >= len(intro_texts):
                    continue
                text = intro_texts[idx]
                rating_orig = ratings_by_index.get(idx, 5)
                orig_path = path_by_index.get(idx)
                if not orig_path or not os.path.isfile(orig_path):
                    continue
                candidates = [(rating_orig, 0, orig_path)]
                p1 = tts.generate_intro_to_path(text, os.path.join(audio_dir, f"intro_{idx}_regen1"))
                if p1 and os.path.isfile(p1):
                    _, r1 = run_single_intro_qa(p1, text, config.WHISPER_HOST, config.OLLAMA_HOST, config.OLLAMA_MODEL)
                    candidates.append((r1, 1, p1))
                p2 = tts.generate_intro_to_path(text, os.path.join(audio_dir, f"intro_{idx}_regen2"))
                if p2 and os.path.isfile(p2):
                    _, r2 = run_single_intro_qa(p2, text, config.WHISPER_HOST, config.OLLAMA_HOST, config.OLLAMA_MODEL)
                    candidates.append((r2, 2, p2))
                candidates.sort(key=lambda x: (x[0], x[1]))
                best_rating, best_id, best_path = candidates[0]
                if best_id != 0:
                    import shutil
                    ext = os.path.splitext(best_path)[1].lstrip(".")
                    final = os.path.join(audio_dir, f"intro_{idx}.{ext}")
                    shutil.copy2(best_path, final)
                    for other in ("mp3", "wav"):
                        if other != ext:
                            op = os.path.join(audio_dir, f"intro_{idx}.{other}")
                            if os.path.isfile(op):
                                try:
                                    os.remove(op)
                                except OSError:
                                    pass
                    print(f"Intro {idx}: kept regen{best_id} (rating {best_rating})")
                else:
                    print(f"Intro {idx}: kept original (rating {best_rating})")
                for base in (f"intro_{idx}_regen1", f"intro_{idx}_regen2"):
                    for ext in ("mp3", "wav"):
                        to_remove = os.path.join(audio_dir, f"{base}.{ext}")
                        if os.path.isfile(to_remove):
                            try:
                                os.remove(to_remove)
                            except OSError:
                                pass
        except Exception as e:
            print(f"Intro QA/regen failed: {e}")

    def _refresh_ack_and_phrase_sets(self):
        """Low-priority weekly refresh: ack phrases and phrase sets (any_questions, goodbye, fallback)."""
        try:
            tts.refresh_prepared_acks(get_ack_phrases_for_tts())
            print("Refreshed ack phrases (weekly)")
        except Exception as e:
            print(f"Ack refresh skipped: {e}")
        try:
            tts.refresh_prepared_phrases(get_phrase_sets_for_tts())
            print("Refreshed phrase sets (weekly)")
        except Exception as e:
            print(f"Phrase refresh skipped: {e}")

    def check_and_send_reminders(self):
        """Main task: find events needing reminders. Intro pregen only when next event or date threshold changed."""
        print(f"\n[{datetime.now()}] Checking for events needing reminders...")
        
        # Intro prewarm only when upcoming event or "today"/"tomorrow" threshold changed.
        # Run in background so we don't block the main loop for 30+ min (TTS + QA + regen x3).
        try:
            ref = date.today()
            current_sig = get_next_event_intro_signature(reference_date=ref)
            last_sig = self._load_intro_signature()
            if current_sig is not None and current_sig != last_sig:
                intro_texts = get_next_event_intro_variations(count=3)
                if intro_texts:
                    def _do_intro_refresh_and_qa():
                        try:
                            print("Intro refresh + QA started (background)...")
                            tts.refresh_prepared_intros(intro_texts)
                            self._save_intro_signature(current_sig)
                            print(f"Refreshed {len(intro_texts)} intro variation(s) (event or date threshold changed)")
                            if getattr(config, "WHISPER_HOST", ""):
                                self._run_intro_qa_and_regen(intro_texts)
                            print("Intro refresh + QA finished (background).")
                        except Exception as e:
                            print(f"Intro refresh + QA failed: {e}")
                    import threading
                    threading.Thread(target=_do_intro_refresh_and_qa, daemon=True).start()
                    print("Intro refresh + QA running in background (main loop continues).")
        except Exception as e:
            print(f"Intro pre-generation skipped: {e}")
        
        # Get events needing reminders
        events = sheets.get_events_needing_reminder(
            lead_time_hours=config.REMINDER_LEAD_TIME_HOURS
        )
        
        if not events:
            print("No events need reminders at this time.")
            return
        
        if not self._prewarm_done:
            print(f"Found {len(events)} event(s) needing reminders; skipping outbound send until pre-warm complete (incoming traffic is always accepted).")
            return
        
        print(f"Found {len(events)} event(s) needing reminders")
        
        for event in events:
            # Create unique event ID
            event_id = f"{event['name']}_{event['date']}"
            
            # Check if we've already sent reminder for this event
            if event_id in self.last_check:
                time_since_last = datetime.now() - self.last_check[event_id]
                if time_since_last.total_seconds() < 3600:  # Don't resend within 1 hour
                    print(f"Skipping {event['name']} - already reminded recently")
                    continue
            
            print(f"\nProcessing reminder for: {event['name']}")
            self.send_event_reminders(event)
            
            # Mark as checked
            self.last_check[event_id] = datetime.now()
    
    def send_event_reminders(self, event):
        """Send reminders for a specific event to all contacts"""
        
        priority = event.get('priority', 'normal')
        
        # Determine which contacts to send to based on priority
        if priority in ['urgent', 'critical']:
            sms_contacts = db.get_all_contacts(consent_type='sms')
            voice_contacts = db.get_all_contacts(consent_type='voice')
        else:
            sms_contacts = db.get_all_contacts(consent_type='sms')
            voice_contacts = []
        
        print(f"Sending to {len(sms_contacts)} SMS contacts")
        if voice_contacts:
            print(f"Sending to {len(voice_contacts)} voice contacts")
        
        # Generate audio if needed for voice calls
        audio_url = None
        if voice_contacts:
            print("Generating voice audio...")
            sample_name = sms_contacts[0][1] if sms_contacts else "there"  # name is index 1
            voice_message = message_gen.generate_reminder_message(
                event, 
                sample_name, 
                is_voice=True
            )
            
            local_path, audio_url = tts.text_to_speech(
                voice_message,
                recipient_phone="sample"
            )
            
            if not audio_url:
                print("Failed to generate audio, skipping voice calls")
                voice_contacts = []
        
        # Send to all contacts
        all_contacts = set()
        for contact in sms_contacts:
            all_contacts.add(contact)
        for contact in voice_contacts:
            all_contacts.add(contact)
        
        for contact in all_contacts:
            contact_id = contact[0]
            name = contact[1]
            phone = contact[2]
            sms_consent = contact[4]
            voice_consent = contact[5]
            
            print(f"  Sending to {name} ({phone})...")
            
            # Generate personalized message
            message_text = message_gen.generate_reminder_message(
                event,
                name,
                is_voice=False
            )
            
            # Determine what to send
            should_send_voice = voice_consent and priority in ['urgent', 'critical'] and audio_url
            should_send_sms = sms_consent
            
            # Send via Twilio
            result = twilio_handler.send_reminder(
                to_number=phone,
                message_text=message_text,
                audio_url=audio_url if should_send_voice else None,
                priority=priority
            )
            
            # Log to database
            if result['sms_sid']:
                db.log_reminder(
                    contact_id=contact_id,
                    reminder_type='sms',
                    priority=priority,
                    message_text=message_text,
                    event_name=event['name'],
                    event_date=str(event['date']),
                    status='sent',
                    twilio_sid=result['sms_sid']
                )
            
            if result['voice_sid']:
                db.log_reminder(
                    contact_id=contact_id,
                    reminder_type='voice',
                    priority=priority,
                    message_text=message_text,
                    event_name=event['name'],
                    event_date=str(event['date']),
                    status='sent',
                    twilio_sid=result['voice_sid']
                )
            
            # Small delay between sends to avoid rate limits
            time.sleep(1)
        
        print(f"Completed reminders for {event['name']}")

    def _cleanup_audio(self):
        """Remove old TTS audio files; keeps cached ack and intro files."""
        try:
            n = tts.cleanup_old_files(days_old=config.AUDIO_CLEANUP_DAYS)
            if n:
                print(f"Cleaned up {n} old audio file(s)")
        except Exception as e:
            print(f"Audio cleanup failed: {e}")

    def _send_unanswered_report(self):
        """Email admin a list of questions we couldn't answer (if configured)."""
        try:
            if send_unanswered_report():
                print("Sent unanswered-questions report by email")
        except Exception as e:
            print(f"Unanswered report failed: {e}")
    
    def run_continuous(self):
        """Run the scheduler continuously"""
        print("ZarchTalk Reminder Scheduler Starting...")
        print(f"Check interval: {config.CHECK_INTERVAL_MINUTES} minutes")
        print(f"Lead time: {config.REMINDER_LEAD_TIME_HOURS} hours")
        
        # Validate config
        try:
            config.validate()
            print("✓ Configuration valid")
        except ValueError as e:
            print(f"✗ Configuration error: {e}")
            return
        
        # Test connections
        print("\nTesting connections...")
        
        if sheets.authenticate():
            print("✓ Google Sheets connected")
        else:
            print("✗ Google Sheets connection failed")
        
        if twilio_handler.test_connection():
            print("✓ Twilio connected")
        else:
            print("✗ Twilio connection failed")
        
        if tts.test_tts_connection():
            print("✓ TTS service connected")
        else:
            print("⚠ TTS service connection failed (voice reminders may not work)")
        
        # Schedule the check
        schedule.every(config.CHECK_INTERVAL_MINUTES).minutes.do(
            self.check_and_send_reminders
        )
        # Clean up old audio files daily (keeps ack/intro cache, removes old reminder_* etc.)
        schedule.every().day.at("03:00").do(self._cleanup_audio)
        # Weekly report: unanswered questions by email + SMS (Saturday 8 AM)
        schedule.every().saturday.at("08:00").do(self._send_unanswered_report)
        # Weekly low-priority: ack phrases and phrase sets (Sunday 2 AM)
        schedule.every().sunday.at("02:00").do(self._refresh_ack_and_phrase_sets)

        # Run once immediately (reminders + intro refresh if event changed)
        print("\nRunning initial check...")
        self.check_and_send_reminders()
        # Populate ack/phrase cache in background so we don't peg CPU at startup (then weekly)
        def _startup_ack_phrase():
            try:
                self._refresh_ack_and_phrase_sets()
                self._prewarm_done = True
                print("Startup ack/phrase refresh finished. Pre-warm complete; scheduler may now send reminders.")
            except Exception as e:
                print(f"Initial ack/phrase refresh skipped: {e}")
                self._prewarm_done = True  # Allow sends anyway so we don't block outbound forever on failure
        import threading
        threading.Thread(target=_startup_ack_phrase, daemon=True).start()
        
        # Then run on schedule (main loop is just sleep + run_pending; CPU use is during job runs)
        print(f"\nScheduler running. Press Ctrl+C to stop.")
        
        try:
            while True:
                schedule.run_pending()
                time.sleep(60)
        except KeyboardInterrupt:
            print("\n\nScheduler stopped by user")
    
    def run_once(self):
        """Run a single check (useful for testing)"""
        print("Running single reminder check...")
        
        try:
            config.validate()
        except ValueError as e:
            print(f"Configuration error: {e}")
            return
        
        self.check_and_send_reminders()
        print("\nSingle check complete.")

# Create scheduler instance
scheduler = ReminderScheduler()

if __name__ == '__main__':
    # Run continuously when executed directly
    scheduler.run_continuous()
