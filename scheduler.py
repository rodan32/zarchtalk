"""
Main scheduler for ZarchTalk
Periodically checks for events needing reminders and sends them
"""
import time
import schedule
from datetime import datetime, timedelta
from config import config
from database import db
from sheets_reader import sheets
from message_gen import message_gen
from question_handler import get_next_event_intro_variations
from phrase_sets import get_phrase_sets_for_tts
from tts_handler import tts
from twilio_handler import twilio_handler
from intro_qa import run_intro_qa
from report_unanswered import send_unanswered_report

class ReminderScheduler:
    def __init__(self):
        self.last_check = {}  # Track last check time for each event
        self.debug = config.DEBUG_MODE
    
    def check_and_send_reminders(self):
        """Main task: find events needing reminders and send them. Intro pregen/QA are best-effort."""
        print(f"\n[{datetime.now()}] Checking for events needing reminders...")
        
        # Best-effort: pre-load intro TTS so callers get a ready "what's next" (failures don't block reminders)
        try:
            intro_texts = get_next_event_intro_variations(count=3)
            if intro_texts:
                tts.refresh_prepared_intros(intro_texts)
                print(f"Refreshed {len(intro_texts)} intro variation(s)")
                # Pre-generate all phrase prompts (any_questions, any_other_questions, goodbye, fallback) so every prompt uses cache
                try:
                    tts.refresh_prepared_phrases(get_phrase_sets_for_tts())
                    print("Refreshed phrase sets (any_questions, any_other_questions, goodbye, fallback)")
                except Exception as e:
                    print(f"Phrase refresh skipped: {e}")
                # Optional: Whisper transcribe + Ollama review (compare intended vs heard)
                if getattr(config, "WHISPER_HOST", ""):
                    try:
                        indexed_paths = tts.get_prepared_intro_paths()  # [(index, path), ...]
                        if indexed_paths:
                            # Align paths with texts by index (e.g. if intro_1 missing, intro_2 path pairs with text[2])
                            paths = [p for i, p in indexed_paths if i < len(intro_texts)]
                            texts = [intro_texts[i] for i, p in indexed_paths if i < len(intro_texts)]
                            if paths and len(texts) == len(paths):
                                run_intro_qa(
                                    paths,
                                    texts,
                                    config.WHISPER_HOST,
                                    config.OLLAMA_HOST,
                                    config.OLLAMA_MODEL,
                                )
                    except Exception as e:
                        print(f"Intro QA skipped: {e}")
        except Exception as e:
            print(f"Intro pre-generation skipped: {e}")
        
        # Get events needing reminders
        events = sheets.get_events_needing_reminder(
            lead_time_hours=config.REMINDER_LEAD_TIME_HOURS
        )
        
        if not events:
            print("No events need reminders at this time.")
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

        # Run once immediately
        print("\nRunning initial check...")
        self.check_and_send_reminders()
        
        # Then run on schedule
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
