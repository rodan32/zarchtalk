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
from tts_handler import tts
from twilio_handler import twilio_handler

class ReminderScheduler:
    def __init__(self):
        self.last_check = {}  # Track last check time for each event
        self.debug = config.DEBUG_MODE
    
    def check_and_send_reminders(self):
        """Main function to check for events and send reminders"""
        print(f"\n[{datetime.now()}] Checking for events needing reminders...")
        
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
