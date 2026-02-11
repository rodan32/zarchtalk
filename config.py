"""
Configuration management for ZarchTalk
Loads environment variables and provides configuration access
"""
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Application configuration"""
    
    # Twilio
    TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
    TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')
    
    # Ollama
    OLLAMA_HOST = os.getenv('OLLAMA_HOST', 'http://localhost:11434')
    OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'llama2')
    # Run calendar/answer text through LLM to sound more natural (set false to skip if slow)
    NATURALIZE_RESPONSES = os.getenv('NATURALIZE_RESPONSES', 'true').lower() == 'true'
    
    # Whisper (STT for incoming calls)
    WHISPER_HOST = os.getenv('WHISPER_HOST', 'http://192.168.0.40:8000')
    
    # TTS — on 192.168.0.20 only Kokoro (8880) and Applio (6006) are used
    KOKORO_TTS_HOST = os.getenv('KOKORO_TTS_HOST', 'http://localhost:8000')  # Kokoro: e.g. http://192.168.0.20:8880
    KOKORO_VOICE = os.getenv('KOKORO_VOICE', 'af_heart')  # or blended e.g. "af_heart+am_fenrir"
    KOKORO_SPEED = float(os.getenv('KOKORO_SPEED', '1.0'))
    AUDIO_OUTPUT_DIR = os.getenv('AUDIO_OUTPUT_DIR', './audio_files')
    AUDIO_BASE_URL = os.getenv('AUDIO_BASE_URL')
    # Optional: different TTS service (natural speech/style). If set, used instead of Kokoro. Not used on 192.168.0.20.
    ENHANCED_TTS_HOST = os.getenv('ENHANCED_TTS_HOST', '')
    ENHANCED_TTS_STYLE = os.getenv('ENHANCED_TTS_STYLE', 'moderate')  # minimal, moderate, casual
    # Applio: optional voice conversion after Kokoro (port 6006 on 192.168.0.20)
    APPLIO_HOST = os.getenv('APPLIO_HOST', '')  # e.g. http://192.168.0.20:6006
    
    # Google Sheets
    GOOGLE_SHEETS_CREDENTIALS_FILE = os.getenv('GOOGLE_SHEETS_CREDENTIALS_FILE', 'credentials.json')
    CALENDAR_SHEET_ID = os.getenv('CALENDAR_SHEET_ID')
    CALENDAR_SHEET_NAME = os.getenv('CALENDAR_SHEET_NAME', 'Calendar')
    SHEETS_CACHE_PATH = os.getenv('SHEETS_CACHE_PATH', './sheets_cache.json')
    SHEETS_CACHE_TTL_MINUTES = int(os.getenv('SHEETS_CACHE_TTL_MINUTES', 15))
    
    # Database
    DATABASE_PATH = os.getenv('DATABASE_PATH', './zarchtalk.db')
    
    # Scheduling
    CHECK_INTERVAL_MINUTES = int(os.getenv('CHECK_INTERVAL_MINUTES', 60))
    REMINDER_LEAD_TIME_HOURS = int(os.getenv('REMINDER_LEAD_TIME_HOURS', 24))
    AUDIO_CLEANUP_DAYS = int(os.getenv('AUDIO_CLEANUP_DAYS', '7'))  # Delete audio files older than this
    SCHEDULER_STATE_PATH = os.getenv('SCHEDULER_STATE_PATH', './scheduler_state.json')  # Intro signature + optional weekly run
    # At go-live: set BLOCK_UNTIL_WARM=1 so scheduler finishes intro + ack/phrase pre-warm before entering main loop (30–40 min)
    BLOCK_UNTIL_WARM = os.getenv('BLOCK_UNTIL_WARM', 'false').lower() in ('1', 'true', 'yes')
    
    # Webhook (for Twilio action URLs)
    WEBHOOK_BASE_URL = os.getenv('WEBHOOK_BASE_URL', 'https://zarchbot.zarchstuff.com')
    APP_CREATOR = os.getenv('APP_CREATOR', "Brother Cochran—Zach, not Mickey. He built this thing in his spare time. Yes, this is what he does for fun. If it breaks or says something weird, you know exactly who to blame.")

    # Unanswered-questions report (weekly Saturday: email + SMS to admin)
    UNANSWERED_REPORT_EMAIL_TO = os.getenv('UNANSWERED_REPORT_EMAIL_TO', 'elzarcho@gmail.com')
    UNANSWERED_REPORT_SMS_TO = os.getenv('UNANSWERED_REPORT_SMS_TO', '+12067452073')
    UNANSWERED_REPORT_SMTP_HOST = os.getenv('UNANSWERED_REPORT_SMTP_HOST', 'smtp.gmail.com')
    UNANSWERED_REPORT_SMTP_PORT = int(os.getenv('UNANSWERED_REPORT_SMTP_PORT', '587'))
    UNANSWERED_REPORT_SMTP_USER = os.getenv('UNANSWERED_REPORT_SMTP_USER', '')
    UNANSWERED_REPORT_SMTP_PASSWORD = os.getenv('UNANSWERED_REPORT_SMTP_PASSWORD', '')
    UNANSWERED_REPORT_SMTP_FROM = os.getenv('UNANSWERED_REPORT_SMTP_FROM', '')  # defaults to user if not set
    
    # Debug/Testing
    DEBUG_MODE = os.getenv('DEBUG_MODE', 'False').lower() == 'true'
    TEST_PHONE_NUMBER = os.getenv('TEST_PHONE_NUMBER')
    
    @classmethod
    def validate(cls):
        """Validate required configuration is present"""
        required = [
            ('TWILIO_ACCOUNT_SID', cls.TWILIO_ACCOUNT_SID),
            ('TWILIO_AUTH_TOKEN', cls.TWILIO_AUTH_TOKEN),
            ('TWILIO_PHONE_NUMBER', cls.TWILIO_PHONE_NUMBER),
            ('AUDIO_BASE_URL', cls.AUDIO_BASE_URL),
            ('CALENDAR_SHEET_ID', cls.CALENDAR_SHEET_ID),
        ]
        
        missing = [name for name, value in required if not value]
        
        if missing:
            raise ValueError(f"Missing required configuration: {', '.join(missing)}")
        
        return True

# Create config instance
config = Config()
