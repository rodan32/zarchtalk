"""
Message generation using Ollama
Creates personalized reminder messages
"""
import ollama
from config import config

class MessageGenerator:
    def __init__(self):
        self.host = config.OLLAMA_HOST
        self.model = config.OLLAMA_MODEL
        
        # Set the host for ollama client
        ollama.Client(host=self.host)
    
    def generate_reminder_message(self, event, recipient_name, is_voice=False):
        """
        Generate a personalized reminder message
        
        Args:
            event: Dict with event details (name, date, time, location, description)
            recipient_name: Name of the recipient
            is_voice: If True, optimize for voice delivery (shorter, clearer)
        
        Returns:
            Generated message text
        """
        
        # Build the prompt based on message type
        if is_voice:
            prompt = f"""Generate a brief, clear voice reminder message for a youth group event. 
Keep it under 30 seconds of speaking time (about 60-75 words).

Recipient: {recipient_name}
Event: {event['name']}
Date: {event['date']}
Time: {event.get('time', 'TBD')}
Location: {event.get('location', 'TBD')}
Description: {event.get('description', '')}

Requirements:
- Friendly and conversational tone
- Clear pronunciation (spell out abbreviations)
- Include all key details
- End with enthusiasm
- No special characters or emojis

Generate only the message text, no preamble."""
        
        else:  # SMS
            prompt = f"""Generate a friendly text message reminder for a youth group event.
Keep it concise (under 160 characters is ideal, max 300).

Recipient: {recipient_name}
Event: {event['name']}
Date: {event['date']}
Time: {event.get('time', 'TBD')}
Location: {event.get('location', 'TBD')}
Description: {event.get('description', '')}

Requirements:
- Casual, friendly tone appropriate for youth/parents
- Include key details (what, when, where)
- Can use common abbreviations
- End with a friendly note
- Emojis are okay but don't overdo it

Generate only the message text, no preamble."""
        
        try:
            response = ollama.chat(
                model=self.model,
                messages=[
                    {
                        'role': 'user',
                        'content': prompt
                    }
                ]
            )
            
            message = response['message']['content'].strip()
            
            # Clean up any markdown or formatting
            message = message.replace('**', '').replace('*', '')
            
            # Remove quotes if the model wrapped the message
            if message.startswith('"') and message.endswith('"'):
                message = message[1:-1]
            if message.startswith("'") and message.endswith("'"):
                message = message[1:-1]
            
            return message
        
        except Exception as e:
            print(f"Error generating message with Ollama: {e}")
            
            # Fallback to template-based message
            return self._fallback_message(event, recipient_name, is_voice)
    
    def _fallback_message(self, event, recipient_name, is_voice):
        """Fallback message if Ollama fails"""
        
        if is_voice:
            return f"""Hi {recipient_name}, this is a reminder about {event['name']} 
on {event['date']} at {event.get('time', 'TBD')}. 
The location is {event.get('location', 'to be determined')}. 
We're looking forward to seeing you there!"""
        else:
            time_str = event.get('time', 'TBD')
            location_str = event.get('location', 'TBD')
            return f"Hi {recipient_name}! Reminder: {event['name']} on {event['date']} at {time_str}. Location: {location_str}. See you there! 😊"
    
    def generate_urgent_message(self, event, recipient_name, urgency_reason, is_voice=False):
        """
        Generate an urgent message (cancellation, time change, etc.)
        
        Args:
            event: Event details
            recipient_name: Recipient name
            urgency_reason: Why this is urgent (e.g., "cancelled due to weather")
            is_voice: Voice or SMS
        """
        
        if is_voice:
            prompt = f"""Generate a brief, urgent voice message about a youth group event change.
Keep it under 20 seconds (about 40-50 words).

Recipient: {recipient_name}
Event: {event['name']}
Originally scheduled: {event['date']} at {event.get('time', 'TBD')}
Urgent reason: {urgency_reason}

Requirements:
- Start with "URGENT" or "Important update"
- State the change clearly and calmly
- Be direct but not alarming
- Provide next steps if applicable

Generate only the message text."""
        
        else:
            prompt = f"""Generate an urgent text message about a youth group event change.
Keep it under 200 characters.

Recipient: {recipient_name}
Event: {event['name']}
Originally scheduled: {event['date']} at {event.get('time', 'TBD')}
Urgent reason: {urgency_reason}

Requirements:
- Start with 🚨 or "URGENT:"
- Be clear and direct
- Include what they need to know/do

Generate only the message text."""
        
        try:
            response = ollama.chat(
                model=self.model,
                messages=[{'role': 'user', 'content': prompt}]
            )
            
            message = response['message']['content'].strip()
            message = message.replace('**', '').replace('*', '')
            
            if message.startswith('"') and message.endswith('"'):
                message = message[1:-1]
            
            return message
        
        except Exception as e:
            print(f"Error generating urgent message: {e}")
            
            if is_voice:
                return f"Important update for {recipient_name}. {event['name']} scheduled for {event['date']} has been {urgency_reason}. Please check for updates."
            else:
                return f"🚨 URGENT: {event['name']} on {event['date']} - {urgency_reason}. Check for updates!"

# Create message generator instance
message_gen = MessageGenerator()
