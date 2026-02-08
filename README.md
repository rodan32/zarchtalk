# ZarchTalk

Automated SMS and voice reminder system for church youth groups using local LLM and TTS.

## Architecture

- **Ollama** - Local LLM for generating personalized messages
- **Kokoro TTS** - Text-to-speech for voice reminders
- **Twilio** - SMS and voice call delivery
- **Google Sheets** - Calendar/event management
- **SQLite** - Contact and consent tracking

## Setup

### 1. Prerequisites

- Python 3.8+
- Ollama running locally with a model (e.g., llama2)
- Kokoro TTS container running
- Twilio account with phone number
- Google Sheets API credentials
- Nginx with Cloudflare for audio hosting

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configuration

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env` with your actual values:

```ini
# Twilio
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_PHONE_NUMBER=+1234567890

# Ollama (adjust if different)
OLLAMA_HOST=http://192.168.1.100:11434
OLLAMA_MODEL=llama2

# TTS (adjust to your Kokoro container)
KOKORO_TTS_HOST=http://192.168.1.101:8000
AUDIO_OUTPUT_DIR=/var/www/audio/reminders
AUDIO_BASE_URL=https://audio.yourdomain.com/reminders

# Google Sheets
GOOGLE_SHEETS_CREDENTIALS_FILE=credentials.json
CALENDAR_SHEET_ID=your_sheet_id_here
CALENDAR_SHEET_NAME=Calendar

# Optional
DEBUG_MODE=False
TEST_PHONE_NUMBER=+1234567890
```

### 4. Google Sheets Setup

1. Create a Google Cloud project
2. Enable Google Sheets API
3. Create a service account
4. Download credentials as `credentials.json` in project root
5. Share your calendar sheet with the service account email

**Sheet Format:**

| Date       | Event Name           | Time  | Location      | Description            | Priority |
|------------|----------------------|-------|---------------|------------------------|----------|
| 2024-03-15 | Youth Group Meeting  | 7:00 PM | Church Hall   | Weekly meeting         | normal   |
| 2024-03-20 | Service Project      | 9:00 AM | Downtown      | Community service      | urgent   |

**Priority levels:**
- `normal` - SMS only
- `urgent` - SMS + voice call
- `critical` - Voice call first, then SMS

### 5. Add Contacts

Use the contact management script:

```bash
python manage_contacts.py
```

Or add manually via Python:

```python
from database import db

db.add_contact(
    name="John Doe",
    phone_number="+12345678901",
    contact_type="youth",  # or "parent"
    sms_consent=True,
    voice_consent=True
)
```

### 6. Test Setup

Run the test script to verify all components:

```bash
python test_setup.py
```

This will test:
- Configuration
- Database
- Google Sheets connection
- Ollama message generation
- TTS service
- Twilio connection

### 7. Run Scheduler

```bash
python scheduler.py
```

The scheduler will:
- Check for events every hour (configurable)
- Send reminders 24 hours before events (configurable)
- Generate personalized messages via Ollama
- Send SMS and/or voice calls based on priority
- Log all reminders to database

## Usage

### Running Continuously

```bash
python scheduler.py
```

### Running Once (Testing)

```python
from scheduler import scheduler
scheduler.run_once()
```

### Managing Contacts

```bash
python manage_contacts.py
```

### Viewing Logs

```python
from database import db

# Recent reminders
history = db.get_reminder_history(limit=20)

# For specific contact
contact = db.get_contact_by_phone("+12345678901")
history = db.get_reminder_history(contact_id=contact[0])
```

## Cost Estimate

For 20 contacts, 6-8 reminders per month:

- **SMS only:** ~$1.27/month
- **Voice only:** ~$2.16/month
- **Both:** ~$3.43/month
- **Phone number:** ~$2/month
- **Total:** ~$4-5/month

## Nginx Configuration

```nginx
server {
    listen 443 ssl;
    server_name audio.yourdomain.com;
    
    # SSL config via Cloudflare
    
    location /reminders/ {
        alias /var/www/audio/reminders/;
        add_header Cache-Control "no-cache, no-store, must-revalidate";
        add_header Access-Control-Allow-Origin "*";
    }
}
```

## Troubleshooting

### Ollama Connection Issues
- Verify Ollama is running: `curl http://localhost:11434/api/tags`
- Check model is downloaded: `ollama list`
- Test generation: `ollama run llama2 "test"`

### TTS Not Working
- Check Kokoro container is running
- Verify API endpoint format matches your container
- Test manually: `curl http://localhost:8000/health`

### Twilio Errors
- Verify credentials are correct
- Check phone number format (E.164: +1234567890)
- Ensure Twilio account is not trial (or add verified numbers)

### Google Sheets Access
- Verify service account has access to sheet
- Check sheet ID is correct
- Ensure credentials.json is valid

## File Structure

```
zarchtalk/
├── config.py              # Configuration management
├── database.py            # SQLite contact/log database
├── sheets_reader.py       # Google Sheets integration
├── message_gen.py         # Ollama message generation
├── tts_handler.py         # Kokoro TTS integration
├── twilio_handler.py      # Twilio SMS/voice handling
├── scheduler.py           # Main orchestration loop
├── test_setup.py          # Component testing
├── manage_contacts.py     # Contact management utility
├── requirements.txt       # Python dependencies
├── .env                   # Configuration (create from .env.example)
├── credentials.json       # Google Sheets credentials
└── zarchtalk.db          # SQLite database (auto-created)
```

## License

MIT License - feel free to modify for your needs!
