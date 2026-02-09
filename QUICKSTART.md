# Quick Start Guide

Get ZarchTalk running in 10 minutes!

## 1. Clone and Install (2 min)

```bash
cd zarchtalk
pip install -r requirements.txt
```

## 2. Configure (3 min)

```bash
cp .env.example .env
nano .env  # or your preferred editor
```

**Minimum required settings:**
```ini
TWILIO_ACCOUNT_SID=ACxxxxx...
TWILIO_AUTH_TOKEN=xxxxx...
TWILIO_PHONE_NUMBER=+1234567890

OLLAMA_HOST=http://192.168.1.100:11434  # Your Ollama machine
KOKORO_TTS_HOST=http://192.168.1.101:8000  # Your TTS machine

AUDIO_OUTPUT_DIR=/var/www/audio/reminders
AUDIO_BASE_URL=https://audio.yourdomain.com/reminders

CALENDAR_SHEET_ID=1ABC...xyz
```

## 3. Google Sheets Setup (2 min)

1. Download service account credentials from Google Cloud Console
2. Save as `credentials.json` in zarchtalk directory
3. Share your calendar sheet with service account email
4. Format sheet with columns: Date | Event Name | Time | Location | Description | Priority

## 4. Add Test Contact (1 min)

```bash
python manage_contacts.py
```

Select option 1, add your own phone number as a test contact.

## 5. Test Everything (1 min)

```bash
python test_setup.py
```

Fix any failures before proceeding.

## 6. Run! (1 min)

```bash
python scheduler.py
```

## Test voice calls

1. **Webhook must be running** and reachable by Twilio at `WEBHOOK_BASE_URL` (e.g. `https://zarchbot.zarchstuff.com`).  
   - If using systemd: `sudo systemctl status zarchbot-webhook`  
   - Or run locally: `python webhook.py` (set `WEBHOOK_HOST=0.0.0.0` if Twilio hits this machine).

2. **Twilio configuration**  
   In Twilio Console → Phone Numbers → your number → Voice & Fax:  
   - **A call comes in**: Webhook, `https://your-domain/webhook/voice`  
   - HTTP POST.

3. **Call the number**  
   Dial your Twilio phone number from your phone. You should hear the next-event intro (or a cached variation), then “Do you have any questions?”, then you can speak a question or say “no” to hang up.

4. **Optional: pre-generate intros**  
   Run the scheduler once so it refreshes cached intro variations:  
   `python -c "from scheduler import scheduler; scheduler.check_and_send_reminders()"`  
   Then call again to hear one of the pre-generated intros.

## First Reminder Test

Add a test event to your Google Sheet:
- Date: Tomorrow
- Event Name: Test Event
- Time: 12:00 PM
- Location: Test Location
- Priority: normal

Wait for next check cycle (or set `CHECK_INTERVAL_MINUTES=1` for faster testing).

## Troubleshooting

**"Configuration error"**: Fill out all required fields in .env

**"Google Sheets authentication failed"**: Make sure credentials.json exists and sheet is shared

**"Twilio connection failed"**: Check account SID and auth token

**"TTS service not reachable"**: Verify Kokoro container is running

**"Ollama error"**: Ensure Ollama is running with model loaded

## Applio (optional): more natural voice

On the TTS host (e.g. 192.168.0.20), only two ports are used: **8880** (Kokoro) and **6006** (Applio). Set `KOKORO_TTS_HOST=http://192.168.0.20:8880` and optionally run Kokoro output through **Applio** (voice conversion at port 6006). In `.env`:

```ini
APPLIO_HOST=http://192.168.0.20:6006
```

Install the client: `pip install gradio_client`. The app will use Kokoro first, then send the MP3 to Applio if the host is set. If Applio is down or the API doesn’t match, it falls back to Kokoro-only.

**Warmer, friendlier sound:** If the voice feels a bit cold, in Applio's inference tab try a slightly warmer voice model, or add a touch of **Reverb** in the post-processing effects—it softens the tone without changing the words.

## Next Steps

1. Add real contacts: `python manage_contacts.py`
2. Populate calendar sheet with events
3. Adjust settings:
   - `CHECK_INTERVAL_MINUTES` - how often to check for events
   - `REMINDER_LEAD_TIME_HOURS` - how far in advance to remind
4. Set up as systemd service (see README for details)

## Production Checklist

- [ ] All contacts have proper consent
- [ ] Phone numbers in E.164 format (+country code)
- [ ] Audio directory writable by application
- [ ] Nginx serving audio files correctly
- [ ] Cloudflare SSL configured
- [ ] Test SMS and voice calls
- [ ] Monitor first few runs
- [ ] Set up log rotation
- [ ] Configure backup for database

## Need Help?

Check the full README.md for detailed documentation!
