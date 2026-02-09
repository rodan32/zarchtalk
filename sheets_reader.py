"""
Google Sheets integration for calendar events
Reads event data from Google Sheets using get_all_values() to handle sheets
with non-standard headers. Parses and caches to JSON for the scheduler.
"""
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import json
import os
from config import config

# Column header mappings (sheet header -> our field)
HEADER_MAP = {
    'date': ['date', 'Date'],
    'name': ['activity', 'event name', 'event'],
    'time': ['time', 'Time'],
    'location': ['location', 'Location'],
    'description': ['notes', 'description', 'Description', 'Notes'],
    'priority': ['priority', 'Priority'],
}

DATE_FORMATS = ['%B %d, %Y', '%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y', '%d/%m/%Y', '%b %d, %Y']
TIME_FORMATS = ['%I:%M %p', '%I:%M%p', '%H:%M', '%H:%M:%S']


class SheetsReader:
    def __init__(self):
        self.sheet_id = config.CALENDAR_SHEET_ID
        self.sheet_name = config.CALENDAR_SHEET_NAME
        self.credentials_file = config.GOOGLE_SHEETS_CREDENTIALS_FILE
        self.cache_path = config.SHEETS_CACHE_PATH
        self.cache_ttl = timedelta(minutes=config.SHEETS_CACHE_TTL_MINUTES)
        self.client = None
        self.sheet = None

    def authenticate(self):
        """Authenticate with Google Sheets API (read-only)"""
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets.readonly',
            'https://www.googleapis.com/auth/drive.readonly'
        ]
        try:
            creds = Credentials.from_service_account_file(
                self.credentials_file,
                scopes=scopes
            )
            self.client = gspread.authorize(creds)
            self.sheet = self.client.open_by_key(self.sheet_id).worksheet(self.sheet_name)
            return True
        except Exception as e:
            print(f"Authentication failed: {e}")
            return False

    def _find_header_row(self, rows):
        """Find row index containing Date, Activity (or Event Name), etc."""
        for i, row in enumerate(rows):
            row_lower = [str(c).strip().lower() for c in row]
            if 'date' in row_lower and ('activity' in row_lower or 'event' in row_lower or 'event name' in row_lower):
                return i
        return None

    def _build_column_indices(self, header_row):
        """Map header names to column indices."""
        indices = {}
        for col_idx, cell in enumerate(header_row):
            val = str(cell).strip().lower()
            if not val:
                continue
            for field, aliases in HEADER_MAP.items():
                if val in [a.lower() for a in aliases]:
                    indices[field] = col_idx
                    break
        return indices

    def _parse_date(self, s):
        """Parse date string with multiple format support."""
        if not s or not str(s).strip():
            return None
        s = str(s).strip()
        for fmt in DATE_FORMATS:
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                continue
        return None

    def _parse_time(self, s):
        """Parse time string (12h or 24h)."""
        if not s or not str(s).strip():
            return datetime.strptime('12:00', '%H:%M').time()
        s = str(s).strip()
        for fmt in TIME_FORMATS:
            try:
                return datetime.strptime(s, fmt).time()
            except ValueError:
                continue
        return datetime.strptime('12:00', '%H:%M').time()

    def _fetch_and_parse_events(self):
        """Fetch raw rows, parse into normalized event dicts. No cache."""
        if not self.sheet:
            if not self.authenticate():
                return []

        try:
            rows = self.sheet.get_all_values()
            if not rows:
                return []

            header_idx = self._find_header_row(rows)
            if header_idx is None:
                print("Could not find header row (Date, Activity/Event)")
                return []

            header_row = rows[header_idx]
            col = self._build_column_indices(header_row)
            if 'date' not in col or 'name' not in col:
                print("Missing required columns: Date and Activity/Event Name")
                return []

            events = []
            for row in rows[header_idx + 1:]:
                try:
                    date_str = row[col['date']] if col.get('date') is not None and col['date'] < len(row) else ''
                    if not date_str or not str(date_str).strip():
                        continue

                    event_date = self._parse_date(date_str)
                    if not event_date:
                        continue

                    name = row[col['name']] if col['name'] < len(row) else 'Unnamed Event'
                    time_str = row[col['time']] if col.get('time') is not None and col['time'] < len(row) else '12:00'
                    location = row[col['location']] if col.get('location') is not None and col['location'] < len(row) else ''
                    description = row[col['description']] if col.get('description') is not None and col['description'] < len(row) else ''
                    priority = row[col['priority']] if col.get('priority') is not None and col['priority'] < len(row) else 'normal'

                    event_time = self._parse_time(time_str)
                    event_datetime = datetime.combine(event_date, event_time)

                    events.append({
                        'datetime': event_datetime,
                        'date': event_date,
                        'time': time_str,
                        'name': str(name).strip() or 'Unnamed Event',
                        'description': str(description).strip(),
                        'location': str(location).strip(),
                        'priority': str(priority).strip().lower() or 'normal',
                    })
                except Exception as e:
                    print(f"Error parsing row: {e}")
                    continue

            return events
        except Exception as e:
            print(f"Error reading sheet: {e}")
            return []

    def _load_cache(self):
        """Load events from cache if fresh."""
        if not os.path.exists(self.cache_path):
            return None
        try:
            with open(self.cache_path) as f:
                data = json.load(f)
            cached_at = datetime.fromisoformat(data['cached_at'])
            if datetime.now() - cached_at > self.cache_ttl:
                return None
            # Reconstruct datetime objects
            events = []
            for e in data['events']:
                events.append({
                    'datetime': datetime.fromisoformat(e['datetime']),
                    'date': datetime.fromisoformat(e['date']).date(),
                    'time': e['time'],
                    'name': e['name'],
                    'description': e.get('description', ''),
                    'location': e.get('location', ''),
                    'priority': e.get('priority', 'normal'),
                })
            return events
        except Exception:
            return None

    def _save_cache(self, events):
        """Save events to cache as JSON-serializable."""
        try:
            data = {
                'cached_at': datetime.now().isoformat(),
                'events': [
                    {
                        'datetime': e['datetime'].isoformat(),
                        'date': e['date'].isoformat(),
                        'time': e['time'],
                        'name': e['name'],
                        'description': e.get('description', ''),
                        'location': e.get('location', ''),
                        'priority': e.get('priority', 'normal'),
                    }
                    for e in events
                ]
            }
            with open(self.cache_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Could not save cache: {e}")

    def _get_all_events(self):
        """Get all parsed events, from cache if fresh else fetch."""
        cached = self._load_cache()
        if cached is not None:
            return cached
        events = self._fetch_and_parse_events()
        if events:
            self._save_cache(events)
        return events

    def get_upcoming_events(self, days_ahead=7):
        """Get upcoming events within the window."""
        events = self._get_all_events()
        today = datetime.now().date()
        cutoff = today + timedelta(days=days_ahead)
        upcoming = [e for e in events if today <= e['date'] <= cutoff]
        upcoming.sort(key=lambda x: x['datetime'])
        return upcoming

    def get_events_needing_reminder(self, lead_time_hours=24):
        """Get events whose start time is within the next lead_time_hours."""
        events = self._get_all_events()
        now = datetime.now()
        window_end = now + timedelta(hours=lead_time_hours)
        to_remind = [e for e in events if now <= e['datetime'] <= window_end]
        to_remind.sort(key=lambda x: x['datetime'])
        return to_remind


# Create sheets reader instance
sheets = SheetsReader()
