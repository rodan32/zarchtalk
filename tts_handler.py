"""
TTS handler for Kokoro TTS integration
Converts text to speech for voice reminders
"""
import requests
import os
from datetime import datetime
import hashlib
from config import config

class TTSHandler:
    def __init__(self):
        self.tts_host = config.KOKORO_TTS_HOST
        self.audio_output_dir = config.AUDIO_OUTPUT_DIR
        self.audio_base_url = config.AUDIO_BASE_URL
        
        # Ensure output directory exists
        os.makedirs(self.audio_output_dir, exist_ok=True)
    
    def text_to_speech(self, text, recipient_phone=None):
        """
        Convert text to speech using Kokoro TTS
        
        Args:
            text: Text to convert
            recipient_phone: Optional phone number for unique filename
        
        Returns:
            Tuple of (local_path, public_url) or (None, None) on failure
        """
        
        try:
            # Create unique filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            phone_hash = hashlib.md5(recipient_phone.encode()).hexdigest()[:8] if recipient_phone else 'unknown'
            filename = f"reminder_{timestamp}_{phone_hash}.mp3"
            
            local_path = os.path.join(self.audio_output_dir, filename)
            public_url = f"{self.audio_base_url}/{filename}"
            
            # Call Kokoro TTS API
            # Adjust this based on your Kokoro container's API
            response = requests.post(
                f"{self.tts_host}/generate",
                json={
                    "text": text,
                    "voice": "default",  # Adjust based on available voices
                    "speed": 1.0,
                    "format": "mp3"
                },
                timeout=30
            )
            
            if response.status_code == 200:
                # Save audio file
                with open(local_path, 'wb') as f:
                    f.write(response.content)
                
                print(f"Generated TTS audio: {filename}")
                return local_path, public_url
            else:
                print(f"TTS generation failed: {response.status_code}")
                return None, None
        
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
    
    def cleanup_old_files(self, days_old=7):
        """
        Clean up audio files older than specified days
        
        Args:
            days_old: Delete files older than this many days
        """
        
        try:
            now = datetime.now()
            
            for filename in os.listdir(self.audio_output_dir):
                filepath = os.path.join(self.audio_output_dir, filename)
                
                if not os.path.isfile(filepath):
                    continue
                
                # Get file age
                file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
                age_days = (now - file_time).days
                
                if age_days > days_old:
                    os.remove(filepath)
                    print(f"Deleted old audio file: {filename}")
        
        except Exception as e:
            print(f"Error cleaning up old files: {e}")
    
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
