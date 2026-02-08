"""
Twilio integration for SMS and voice calls
Handles sending reminders via Twilio
"""
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse
from config import config

class TwilioHandler:
    def __init__(self):
        self.account_sid = config.TWILIO_ACCOUNT_SID
        self.auth_token = config.TWILIO_AUTH_TOKEN
        self.from_number = config.TWILIO_PHONE_NUMBER
        self.client = Client(self.account_sid, self.auth_token)
    
    def send_sms(self, to_number, message):
        """
        Send SMS message
        
        Args:
            to_number: Recipient phone number (E.164 format)
            message: Message text
        
        Returns:
            Twilio message SID or None on failure
        """
        
        try:
            message_obj = self.client.messages.create(
                body=message,
                from_=self.from_number,
                to=to_number
            )
            
            print(f"SMS sent to {to_number}: {message_obj.sid}")
            return message_obj.sid
        
        except Exception as e:
            print(f"Error sending SMS to {to_number}: {e}")
            return None
    
    def make_voice_call(self, to_number, audio_url, repeat_count=1):
        """
        Make voice call with audio
        
        Args:
            to_number: Recipient phone number (E.164 format)
            audio_url: Public URL to audio file
            repeat_count: Number of times to repeat the message (default 1)
        
        Returns:
            Twilio call SID or None on failure
        """
        
        try:
            # Create TwiML response
            response = VoiceResponse()
            
            # Optional greeting
            response.pause(length=1)
            
            # Play the message
            for _ in range(repeat_count):
                response.play(audio_url)
                if repeat_count > 1:
                    response.pause(length=1)
            
            # Optional closing
            response.pause(length=1)
            
            # Make the call
            call = self.client.calls.create(
                twiml=str(response),
                to=to_number,
                from_=self.from_number
            )
            
            print(f"Voice call initiated to {to_number}: {call.sid}")
            return call.sid
        
        except Exception as e:
            print(f"Error making voice call to {to_number}: {e}")
            return None
    
    def make_voice_call_with_url(self, to_number, twiml_url):
        """
        Make voice call using TwiML URL (alternative approach)
        
        Args:
            to_number: Recipient phone number
            twiml_url: URL that returns TwiML
        
        Returns:
            Twilio call SID or None on failure
        """
        
        try:
            call = self.client.calls.create(
                url=twiml_url,
                to=to_number,
                from_=self.from_number
            )
            
            print(f"Voice call initiated to {to_number}: {call.sid}")
            return call.sid
        
        except Exception as e:
            print(f"Error making voice call to {to_number}: {e}")
            return None
    
    def get_message_status(self, message_sid):
        """Get status of sent SMS"""
        try:
            message = self.client.messages(message_sid).fetch()
            return message.status
        except Exception as e:
            print(f"Error fetching message status: {e}")
            return None
    
    def get_call_status(self, call_sid):
        """Get status of voice call"""
        try:
            call = self.client.calls(call_sid).fetch()
            return call.status
        except Exception as e:
            print(f"Error fetching call status: {e}")
            return None
    
    def send_reminder(self, to_number, message_text, audio_url=None, priority='normal'):
        """
        Send reminder based on priority
        
        Args:
            to_number: Recipient phone number
            message_text: Message text
            audio_url: URL to audio file (for voice)
            priority: 'normal', 'urgent', or 'critical'
        
        Returns:
            Dict with SMS and/or voice SIDs
        """
        
        result = {
            'sms_sid': None,
            'voice_sid': None
        }
        
        # Normal priority: SMS only
        if priority == 'normal':
            result['sms_sid'] = self.send_sms(to_number, message_text)
        
        # Urgent: SMS + voice
        elif priority == 'urgent':
            result['sms_sid'] = self.send_sms(to_number, message_text)
            if audio_url:
                result['voice_sid'] = self.make_voice_call(to_number, audio_url, repeat_count=1)
        
        # Critical: Voice first, then SMS
        elif priority == 'critical':
            if audio_url:
                result['voice_sid'] = self.make_voice_call(to_number, audio_url, repeat_count=2)
            result['sms_sid'] = self.send_sms(to_number, message_text)
        
        return result
    
    def test_connection(self):
        """Test Twilio connection by fetching account info"""
        try:
            account = self.client.api.accounts(self.account_sid).fetch()
            print(f"Connected to Twilio account: {account.friendly_name}")
            return True
        except Exception as e:
            print(f"Twilio connection test failed: {e}")
            return False
    
    def validate_phone_number(self, phone_number):
        """
        Validate phone number format
        Twilio requires E.164 format: +[country code][number]
        """
        if not phone_number:
            return False
        
        # Basic validation
        if phone_number.startswith('+') and len(phone_number) >= 10:
            return True
        
        return False

# Create Twilio handler instance
twilio_handler = TwilioHandler()
