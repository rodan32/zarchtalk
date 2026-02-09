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
    
    # Whisper (STT for incoming calls)
    WHISPER_HOST = os.getenv('WHISPER_HOST', 'http://192.168.0.40:8000')
    
    # TTS
    KOKORO_TTS_HOST = os.getenv('KOKORO_TTS_HOST', 'http://localhost:8000')
    KOKORO_VOICE = os.getenv('KOKORO_VOICE', 'af_sarah')  # or "af_heart+am_fenrir" for blended
    KOKORO_SPEED = float(os.getenv('KOKORO_SPEED', '1.0'))
    AUDIO_OUTPUT_DIR = os.getenv('AUDIO_OUTPUT_DIR', './audio_files')
    AUDIO_BASE_URL = os.getenv('AUDIO_BASE_URL')
    
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
    
    # Webhook (for Twilio action URLs)
    WEBHOOK_BASE_URL = os.getenv('WEBHOOK_BASE_URL', 'https://zarchbot.zarchstuff.com')
    APP_CREATOR = os.getenv('APP_CREATOR', "Brother Cochran—Zach, not Mickey. He built this thing in his spare time. Yes, this is what he does for fun. If it breaks or says something weird, you know exactly who to blame.")

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
