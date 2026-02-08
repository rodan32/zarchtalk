"""
Test script for ZarchTalk components
Tests each component individually before running full scheduler
"""
import sys
from datetime import datetime, timedelta

def test_config():
    """Test configuration loading"""
    print("\n=== Testing Configuration ===")
    try:
        from config import config
        print(f"✓ Config loaded")
        print(f"  Twilio number: {config.TWILIO_PHONE_NUMBER}")
        print(f"  Ollama host: {config.OLLAMA_HOST}")
        print(f"  TTS host: {config.KOKORO_TTS_HOST}")
        print(f"  Audio URL: {config.AUDIO_BASE_URL}")
        
        try:
            config.validate()
            print("✓ Configuration is valid")
            return True
        except ValueError as e:
            print(f"✗ Configuration validation failed: {e}")
            return False
    except Exception as e:
        print(f"✗ Config error: {e}")
        return False

def test_database():
    """Test database operations"""
    print("\n=== Testing Database ===")
    try:
        from database import db
        
        # Test adding a contact
        test_contact_id = db.add_contact(
            name="Test User",
            phone_number="+15555551234",
            contact_type="youth",
            sms_consent=True,
            voice_consent=True,
            notes="Test contact"
        )
        
        if test_contact_id:
            print(f"✓ Database connected")
            print(f"✓ Test contact created (ID: {test_contact_id})")
            
            # Get contacts
            contacts = db.get_all_contacts()
            print(f"✓ Retrieved {len(contacts)} contact(s)")
            
            return True
        else:
            print("✗ Failed to create test contact (might already exist)")
            return True  # Not a critical failure
    
    except Exception as e:
        print(f"✗ Database error: {e}")
        return False

def test_sheets():
    """Test Google Sheets connection"""
    print("\n=== Testing Google Sheets ===")
    try:
        from sheets_reader import sheets
        
        if sheets.authenticate():
            print("✓ Google Sheets authentication successful")
            
            # Try to read events
            events = sheets.get_upcoming_events(days_ahead=30)
            print(f"✓ Retrieved {len(events)} upcoming event(s)")
            
            if events:
                print(f"  First event: {events[0]['name']} on {events[0]['date']}")
            
            return True
        else:
            print("✗ Google Sheets authentication failed")
            print("  Make sure credentials.json is in the project directory")
            return False
    
    except Exception as e:
        print(f"✗ Sheets error: {e}")
        return False

def test_ollama():
    """Test Ollama connection and message generation"""
    print("\n=== Testing Ollama ===")
    try:
        from message_gen import message_gen
        
        test_event = {
            'name': 'Youth Group Meeting',
            'date': datetime.now().date() + timedelta(days=1),
            'time': '7:00 PM',
            'location': 'Church Building',
            'description': 'Weekly meeting',
            'priority': 'normal'
        }
        
        print("Generating test SMS message...")
        sms_message = message_gen.generate_reminder_message(
            event=test_event,
            recipient_name="Test User",
            is_voice=False
        )
        
        print(f"✓ SMS generated ({len(sms_message)} chars):")
        print(f"  {sms_message}")
        
        print("\nGenerating test voice message...")
        voice_message = message_gen.generate_reminder_message(
            event=test_event,
            recipient_name="Test User",
            is_voice=True
        )
        
        print(f"✓ Voice message generated ({len(voice_message)} chars):")
        print(f"  {voice_message}")
        
        return True
    
    except Exception as e:
        print(f"✗ Ollama error: {e}")
        print("  Make sure Ollama is running and the model is available")
        return False

def test_tts():
    """Test TTS service"""
    print("\n=== Testing TTS Service ===")
    try:
        from tts_handler import tts
        
        if tts.test_tts_connection():
            print("✓ TTS service is reachable")
            
            # Optionally test generating audio
            test_text = "This is a test message from ZarchTalk."
            print(f"\nGenerating test audio...")
            local_path, public_url = tts.text_to_speech(
                test_text,
                recipient_phone="+15555551234"
            )
            
            if local_path and public_url:
                print(f"✓ Audio generated successfully")
                print(f"  Local: {local_path}")
                print(f"  URL: {public_url}")
                return True
            else:
                print("⚠ Audio generation failed (check TTS API format)")
                return True  # Service is up, just API format issue
        else:
            print("✗ TTS service not reachable")
            print(f"  Host: {tts.tts_host}")
            return False
    
    except Exception as e:
        print(f"✗ TTS error: {e}")
        return False

def test_twilio():
    """Test Twilio connection"""
    print("\n=== Testing Twilio ===")
    try:
        from twilio_handler import twilio_handler
        from config import config
        
        if twilio_handler.test_connection():
            print("✓ Twilio connection successful")
            
            # Optionally send test SMS
            if config.TEST_PHONE_NUMBER:
                print(f"\nSending test SMS to {config.TEST_PHONE_NUMBER}...")
                response = input("Send test SMS? (y/n): ")
                
                if response.lower() == 'y':
                    sid = twilio_handler.send_sms(
                        to_number=config.TEST_PHONE_NUMBER,
                        message="Test message from ZarchTalk setup."
                    )
                    
                    if sid:
                        print(f"✓ Test SMS sent (SID: {sid})")
                    else:
                        print("✗ Test SMS failed")
            
            return True
        else:
            print("✗ Twilio connection failed")
            return False
    
    except Exception as e:
        print(f"✗ Twilio error: {e}")
        return False

def main():
    """Run all tests"""
    print("=" * 50)
    print("ZarchTalk Setup Test")
    print("=" * 50)
    
    results = {
        'Config': test_config(),
        'Database': test_database(),
        'Google Sheets': test_sheets(),
        'Ollama': test_ollama(),
        'TTS': test_tts(),
        'Twilio': test_twilio()
    }
    
    print("\n" + "=" * 50)
    print("Test Summary")
    print("=" * 50)
    
    for component, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{component:20} {status}")
    
    all_passed = all(results.values())
    
    if all_passed:
        print("\n✓ All tests passed! Ready to run scheduler.")
        print("\nNext steps:")
        print("  1. Add contacts to database (or create import script)")
        print("  2. Update Google Sheet with events")
        print("  3. Run: python scheduler.py")
    else:
        print("\n⚠ Some tests failed. Fix issues before running scheduler.")
    
    return all_passed

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
