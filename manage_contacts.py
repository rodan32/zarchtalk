"""
Contact management utility for ZarchTalk
Interactive CLI for adding, viewing, and managing contacts
"""
import sys
from database import db

def print_menu():
    """Print main menu"""
    print("\n" + "=" * 50)
    print("ZarchTalk Contact Management")
    print("=" * 50)
    print("1. Add new contact")
    print("2. View all contacts")
    print("3. View contact by phone")
    print("4. Update consent")
    print("5. View reminder history")
    print("6. Export contacts")
    print("7. Import contacts from CSV")
    print("0. Exit")
    print("=" * 50)

def add_contact():
    """Add a new contact interactively"""
    print("\n--- Add New Contact ---")
    
    name = input("Name: ").strip()
    if not name:
        print("Error: Name is required")
        return
    
    phone = input("Phone (E.164 format, e.g., +12345678901): ").strip()
    if not phone.startswith('+'):
        print("Error: Phone must start with + and country code")
        return
    
    contact_type = input("Type (youth/parent) [youth]: ").strip().lower() or "youth"
    if contact_type not in ['youth', 'parent']:
        print("Error: Type must be 'youth' or 'parent'")
        return
    
    sms_consent = input("SMS consent (y/n) [y]: ").strip().lower() or 'y'
    sms_consent = sms_consent == 'y'
    
    voice_consent = input("Voice consent (y/n) [y]: ").strip().lower() or 'y'
    voice_consent = voice_consent == 'y'
    
    notes = input("Notes (optional): ").strip() or None
    
    # Confirm
    print("\n--- Confirm ---")
    print(f"Name: {name}")
    print(f"Phone: {phone}")
    print(f"Type: {contact_type}")
    print(f"SMS: {'Yes' if sms_consent else 'No'}")
    print(f"Voice: {'Yes' if voice_consent else 'No'}")
    if notes:
        print(f"Notes: {notes}")
    
    confirm = input("\nAdd this contact? (y/n): ").strip().lower()
    
    if confirm == 'y':
        contact_id = db.add_contact(
            name=name,
            phone_number=phone,
            contact_type=contact_type,
            sms_consent=sms_consent,
            voice_consent=voice_consent,
            notes=notes
        )
        
        if contact_id:
            print(f"\n✓ Contact added successfully (ID: {contact_id})")
        else:
            print("\n✗ Failed to add contact (may already exist)")
    else:
        print("\nCancelled")

def view_all_contacts():
    """View all contacts"""
    print("\n--- All Contacts ---")
    
    contacts = db.get_all_contacts()
    
    if not contacts:
        print("No contacts found")
        return
    
    print(f"\nTotal: {len(contacts)} contact(s)\n")
    
    for contact in contacts:
        contact_id, name, phone, contact_type, sms, voice, notes, created, updated = contact
        print(f"ID: {contact_id}")
        print(f"  Name: {name}")
        print(f"  Phone: {phone}")
        print(f"  Type: {contact_type}")
        print(f"  SMS: {'✓' if sms else '✗'}  Voice: {'✓' if voice else '✗'}")
        if notes:
            print(f"  Notes: {notes}")
        print()

def view_contact_by_phone():
    """View contact details by phone number"""
    phone = input("\nEnter phone number: ").strip()
    
    contact = db.get_contact_by_phone(phone)
    
    if not contact:
        print(f"No contact found with phone: {phone}")
        return
    
    contact_id, name, phone, contact_type, sms, voice, notes, created, updated = contact
    
    print("\n--- Contact Details ---")
    print(f"ID: {contact_id}")
    print(f"Name: {name}")
    print(f"Phone: {phone}")
    print(f"Type: {contact_type}")
    print(f"SMS Consent: {'Yes' if sms else 'No'}")
    print(f"Voice Consent: {'Yes' if voice else 'No'}")
    if notes:
        print(f"Notes: {notes}")
    print(f"Created: {created}")
    print(f"Updated: {updated}")

def view_reminder_history():
    """View reminder history"""
    print("\n--- Reminder History ---")
    
    choice = input("View for specific contact? (y/n): ").strip().lower()
    
    if choice == 'y':
        phone = input("Enter phone number: ").strip()
        contact = db.get_contact_by_phone(phone)
        
        if not contact:
            print(f"No contact found with phone: {phone}")
            return
        
        contact_id = contact[0]
        history = db.get_reminder_history(contact_id=contact_id, limit=50)
    else:
        history = db.get_reminder_history(limit=50)
    
    if not history:
        print("No reminder history found")
        return
    
    print(f"\nShowing {len(history)} reminder(s)\n")
    
    for record in history:
        reminder_id, contact_id, reminder_type, priority, message, event, date, status, sid, sent_at, name, phone = record
        
        print(f"[{sent_at}] {name} ({phone})")
        print(f"  Event: {event} on {date}")
        print(f"  Type: {reminder_type.upper()}  Priority: {priority}  Status: {status}")
        print(f"  Message: {message[:60]}..." if len(message) > 60 else f"  Message: {message}")
        print()

def export_contacts():
    """Export contacts to CSV"""
    import csv
    from datetime import datetime
    
    filename = f"contacts_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    contacts = db.get_all_contacts()
    
    if not contacts:
        print("No contacts to export")
        return
    
    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['ID', 'Name', 'Phone', 'Type', 'SMS_Consent', 'Voice_Consent', 'Notes'])
        
        for contact in contacts:
            contact_id, name, phone, contact_type, sms, voice, notes, _, _ = contact
            writer.writerow([contact_id, name, phone, contact_type, sms, voice, notes or ''])
    
    print(f"\n✓ Exported {len(contacts)} contacts to {filename}")

def import_contacts():
    """Import contacts from CSV"""
    import csv
    
    filename = input("\nEnter CSV filename: ").strip()
    
    try:
        with open(filename, 'r') as f:
            reader = csv.DictReader(f)
            
            count = 0
            for row in reader:
                contact_id = db.add_contact(
                    name=row['Name'],
                    phone_number=row['Phone'],
                    contact_type=row.get('Type', 'youth'),
                    sms_consent=row.get('SMS_Consent', 'True').lower() in ['true', '1', 'yes'],
                    voice_consent=row.get('Voice_Consent', 'True').lower() in ['true', '1', 'yes'],
                    notes=row.get('Notes', None)
                )
                
                if contact_id:
                    count += 1
                    print(f"✓ Added: {row['Name']}")
                else:
                    print(f"✗ Skipped (exists): {row['Name']}")
            
            print(f"\n✓ Imported {count} contacts")
    
    except FileNotFoundError:
        print(f"Error: File '{filename}' not found")
    except Exception as e:
        print(f"Error importing: {e}")

def main():
    """Main menu loop"""
    while True:
        print_menu()
        
        choice = input("\nSelect option: ").strip()
        
        if choice == '1':
            add_contact()
        elif choice == '2':
            view_all_contacts()
        elif choice == '3':
            view_contact_by_phone()
        elif choice == '4':
            print("\nUpdate consent - Not yet implemented")
            print("Use: python -c \"from database import db; db.get_connection()...\"")
        elif choice == '5':
            view_reminder_history()
        elif choice == '6':
            export_contacts()
        elif choice == '7':
            import_contacts()
        elif choice == '0':
            print("\nGoodbye!")
            sys.exit(0)
        else:
            print("\nInvalid option")

if __name__ == '__main__':
    main()
