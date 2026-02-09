"""
Database management for contacts and consent tracking
Uses SQLite for simplicity
"""
import sqlite3
from datetime import datetime
from config import config

class Database:
    def __init__(self, db_path=None):
        self.db_path = db_path or config.DATABASE_PATH
        self.init_database()
    
    def get_connection(self):
        """Get database connection"""
        return sqlite3.connect(self.db_path)
    
    def init_database(self):
        """Initialize database tables"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Contacts table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone_number TEXT UNIQUE NOT NULL,
                contact_type TEXT NOT NULL,  -- 'youth' or 'parent'
                sms_consent BOOLEAN DEFAULT 0,
                voice_consent BOOLEAN DEFAULT 0,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Unanswered questions (voice/SMS) for periodic report to admin
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS unanswered_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transcript TEXT NOT NULL,
                source TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Reminders sent log
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reminders_sent (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_id INTEGER NOT NULL,
                reminder_type TEXT NOT NULL,  -- 'sms' or 'voice'
                priority TEXT NOT NULL,  -- 'normal', 'urgent', 'critical'
                message_text TEXT,
                event_name TEXT,
                event_date TEXT,
                status TEXT,  -- 'sent', 'delivered', 'failed'
                twilio_sid TEXT,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (contact_id) REFERENCES contacts (id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def add_contact(self, name, phone_number, contact_type='youth', 
                   sms_consent=True, voice_consent=True, notes=None):
        """Add a new contact"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO contacts (name, phone_number, contact_type, 
                                    sms_consent, voice_consent, notes)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (name, phone_number, contact_type, sms_consent, voice_consent, notes))
            
            conn.commit()
            contact_id = cursor.lastrowid
            return contact_id
        except sqlite3.IntegrityError:
            print(f"Contact with phone number {phone_number} already exists")
            return None
        finally:
            conn.close()
    
    def get_all_contacts(self, consent_type=None):
        """Get all contacts, optionally filtered by consent type"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if consent_type == 'sms':
            cursor.execute('SELECT * FROM contacts WHERE sms_consent = 1')
        elif consent_type == 'voice':
            cursor.execute('SELECT * FROM contacts WHERE voice_consent = 1')
        else:
            cursor.execute('SELECT * FROM contacts')
        
        contacts = cursor.fetchall()
        conn.close()
        
        return contacts
    
    def get_contact_by_phone(self, phone_number):
        """Get contact by phone number"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM contacts WHERE phone_number = ?', (phone_number,))
        contact = cursor.fetchone()
        conn.close()
        
        return contact
    
    def log_reminder(self, contact_id, reminder_type, priority, message_text, 
                    event_name, event_date, status='sent', twilio_sid=None):
        """Log a sent reminder"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO reminders_sent (contact_id, reminder_type, priority, 
                                       message_text, event_name, event_date, 
                                       status, twilio_sid)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (contact_id, reminder_type, priority, message_text, 
              event_name, event_date, status, twilio_sid))
        
        conn.commit()
        conn.close()
    
    def update_reminder_status(self, twilio_sid, status):
        """Update reminder status based on Twilio callback"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE reminders_sent 
            SET status = ? 
            WHERE twilio_sid = ?
        ''', (status, twilio_sid))
        
        conn.commit()
        conn.close()
    
    def get_reminder_history(self, contact_id=None, limit=50):
        """Get reminder history, optionally for specific contact"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if contact_id:
            cursor.execute('''
                SELECT r.*, c.name, c.phone_number 
                FROM reminders_sent r
                JOIN contacts c ON r.contact_id = c.id
                WHERE r.contact_id = ?
                ORDER BY r.sent_at DESC
                LIMIT ?
            ''', (contact_id, limit))
        else:
            cursor.execute('''
                SELECT r.*, c.name, c.phone_number 
                FROM reminders_sent r
                JOIN contacts c ON r.contact_id = c.id
                ORDER BY r.sent_at DESC
                LIMIT ?
            ''', (limit,))
        
        history = cursor.fetchall()
        conn.close()
        
        return history

    def log_unanswered_question(self, transcript: str, source: str = "voice"):
        """Record a question we couldn't answer (fallback response was used)."""
        if not transcript or not str(transcript).strip():
            return
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO unanswered_questions (transcript, source) VALUES (?, ?)",
                (str(transcript).strip()[:500], source),
            )
            conn.commit()
        finally:
            conn.close()

    def get_pending_unanswered_questions(self):
        """Return list of (id, transcript, source, created_at) for unreported questions."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, transcript, source, created_at FROM unanswered_questions ORDER BY created_at"
        )
        rows = cursor.fetchall()
        conn.close()
        return rows

    def delete_unanswered_questions(self, ids=None):
        """Delete reported questions. If ids is None, delete all."""
        conn = self.get_connection()
        cursor = conn.cursor()
        if ids:
            placeholders = ",".join("?" * len(ids))
            cursor.execute(f"DELETE FROM unanswered_questions WHERE id IN ({placeholders})", ids)
        else:
            cursor.execute("DELETE FROM unanswered_questions")
        conn.commit()
        conn.close()


# Create database instance
db = Database()
