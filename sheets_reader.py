"""
Google Sheets integration for calendar events
Reads event data from Google Sheets
"""
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
from config import config

class SheetsReader:
    def __init__(self):
        self.sheet_id = config.CALENDAR_SHEET_ID
        self.sheet_name = config.CALENDAR_SHEET_NAME
        self.credentials_file = config.GOOGLE_SHEETS_CREDENTIALS_FILE
        self.client = None
        self.sheet = None
    
    def authenticate(self):
        """Authenticate with Google Sheets API"""
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
    
    def get_upcoming_events(self, days_ahead=7):
        """
        Get upcoming events from the sheet
        Expected columns: Date, Event Name, Description, Priority (normal/urgent/critical)
        """
        if not self.sheet:
            if not self.authenticate():
                return []
        
        try:
            # Get all records
            records = self.sheet.get_all_records()
            
            upcoming_events = []
            today = datetime.now().date()
            cutoff_date = today + timedelta(days=days_ahead)
            
            for record in records:
                try:
                    # Parse date - adjust format as needed for your sheet
                    event_date_str = record.get('Date', '')
                    if not event_date_str:
                        continue
                    
                    # Try multiple date formats
                    event_date = None
                    for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y', '%d/%m/%Y']:
                        try:
                            event_date = datetime.strptime(event_date_str, fmt).date()
                            break
                        except ValueError:
                            continue
                    
                    if not event_date:
                        print(f"Could not parse date: {event_date_str}")
                        continue
                    
                    # Check if event is in our window
                    if today <= event_date <= cutoff_date:
                        upcoming_events.append({
                            'date': event_date,
                            'name': record.get('Event Name', 'Unnamed Event'),
                            'description': record.get('Description', ''),
                            'priority': record.get('Priority', 'normal').lower(),
                            'time': record.get('Time', ''),
                            'location': record.get('Location', '')
                        })
                
                except Exception as e:
                    print(f"Error processing record: {e}")
                    continue
            
            # Sort by date
            upcoming_events.sort(key=lambda x: x['date'])
            
            return upcoming_events
        
        except Exception as e:
            print(f"Error reading sheet: {e}")
            return []
    
    def get_events_needing_reminder(self, lead_time_hours=24):
        """
        Get events that need reminders sent
        Returns events happening within the lead time that haven't been reminded yet
        """
        if not self.sheet:
            if not self.authenticate():
                return []
        
        try:
            records = self.sheet.get_all_records()
            
            now = datetime.now()
            reminder_window_start = now
            reminder_window_end = now + timedelta(hours=lead_time_hours)
            
            events_to_remind = []
            
            for record in records:
                try:
                    event_date_str = record.get('Date', '')
                    event_time_str = record.get('Time', '00:00')
                    
                    if not event_date_str:
                        continue
                    
                    # Parse date
                    event_date = None
                    for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y', '%d/%m/%Y']:
                        try:
                            event_date = datetime.strptime(event_date_str, fmt).date()
                            break
                        except ValueError:
                            continue
                    
                    if not event_date:
                        continue
                    
                    # Parse time
                    try:
                        event_time = datetime.strptime(event_time_str, '%H:%M').time()
                    except:
                        event_time = datetime.strptime('12:00', '%H:%M').time()
                    
                    # Combine date and time
                    event_datetime = datetime.combine(event_date, event_time)
                    
                    # Check if event is in reminder window
                    if reminder_window_start <= event_datetime <= reminder_window_end:
                        # Check if already reminded (you'd track this in your DB)
                        events_to_remind.append({
                            'datetime': event_datetime,
                            'date': event_date,
                            'time': event_time_str,
                            'name': record.get('Event Name', 'Unnamed Event'),
                            'description': record.get('Description', ''),
                            'priority': record.get('Priority', 'normal').lower(),
                            'location': record.get('Location', '')
                        })
                
                except Exception as e:
                    print(f"Error processing record: {e}")
                    continue
            
            return events_to_remind
        
        except Exception as e:
            print(f"Error reading sheet: {e}")
            return []

# Create sheets reader instance
sheets = SheetsReader()
