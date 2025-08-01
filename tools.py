import os
import random
import base64
from datetime import datetime, timedelta
from typing import Dict, Optional

import pytz
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition
from icalendar import Calendar, Event

load_dotenv()

CALENDAR_SCOPE = ['https://www.googleapis.com/auth/calendar']
TIMEZONE = pytz.timezone('Asia/Kolkata')

creds_file = os.getenv("GOOGLE_CREDENTIALS_JSON")
if creds_file and os.path.exists(creds_file):
    credentials = service_account.Credentials.from_service_account_file(creds_file, scopes=CALENDAR_SCOPE)
    calendar_service = build('calendar', 'v3', credentials=credentials)
    print("Google Calendar connected")
else:
    credentials = None
    calendar_service = None
    print("Google Calendar not configured")

APPOINTMENTS = {}

def check_availability(date: str) -> dict:
    """Check available appointment slots for a given date"""
    # First normalize the date to ensure it's in proper format
    normalized_date = normalize_date_format(date)
    
    booked_times = set()
    
    if calendar_service:
        try:
            time_min = f"{normalized_date}T00:00:00Z"
            time_max = f"{normalized_date}T23:59:59Z"
            
            events_result = calendar_service.events().list(
                calendarId=os.getenv("FROM_EMAIL", "primary"),
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            for event in events:
                if 'dateTime' in event['start']:
                    event_time = event['start']['dateTime']
                    if '+' in event_time:
                        dt = datetime.fromisoformat(event_time.replace('Z', '+00:00') if event_time.endswith('Z') else event_time)
                        dt = dt.astimezone(TIMEZONE)
                    else:
                        dt = datetime.fromisoformat(event_time)
                        if dt.tzinfo is None:
                            dt = TIMEZONE.localize(dt)
                        else:
                            dt = dt.astimezone(TIMEZONE)
                    
                    booked_times.add(dt.strftime("%H:%M"))
                    
        except Exception as e:
            print(f"Error fetching calendar events: {e}")
    
    available = []
    start_hour = datetime.fromisoformat(f"{normalized_date}T09:00")
    for i in range(16):
        slot = (start_hour + timedelta(minutes=30*i)).strftime("%H:%M")
        if slot not in booked_times:
            available.append(slot)
    
    return {
        "available_slots": available,
        "total_slots": 16,
        "booked_slots": len(booked_times),
        "calendar_integrated": calendar_service is not None
    }

def normalize_time_format(time_str: str) -> str:
    time_str = time_str.strip().upper()
    
    if 'AM' in time_str or 'PM' in time_str:
        try:
            time_str = time_str.replace(' ', '')
            time_part = time_str.replace('AM', '').replace('PM', '')
            
            if ':' in time_part:
                hours, minutes = time_part.split(':')
            else:
                hours, minutes = time_part, '00'
            
            hours = int(hours)
            minutes = int(minutes)
            
            if 'PM' in time_str and hours != 12:
                hours += 12
            elif 'AM' in time_str and hours == 12:
                hours = 0
            
            return f"{hours:02d}:{minutes:02d}"
        except (ValueError, IndexError):
            pass
    
    try:
        if ':' in time_str:
            hours, minutes = time_str.split(':')
            hours = int(hours)
            minutes = int(minutes)
            return f"{hours:02d}:{minutes:02d}"
        else:
            hours = int(time_str)
            return f"{hours:02d}:00"
    except (ValueError, IndexError):
        return time_str

def normalize_date_format(date_str: str) -> str:
    date_str = date_str.strip().lower()
    today = datetime.now(TIMEZONE)
    
    if date_str == 'today':
        return today.strftime("%Y-%m-%d")
    elif date_str == 'tomorrow':
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")
    elif date_str in ['day after tomorrow', 'day after', 'overmorrow']:
        return (today + timedelta(days=2)).strftime("%Y-%m-%d")
    elif date_str == 'next week':
        return (today + timedelta(days=7)).strftime("%Y-%m-%d")
    
    weekdays = {
        'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
        'friday': 4, 'saturday': 5, 'sunday': 6
    }
    
    for day_name, day_num in weekdays.items():
        if day_name in date_str:
            days_ahead = day_num - today.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            return (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    
    formats = [
        "%Y-%m-%d", "%m-%d-%Y", "%d-%m-%Y", "%B %d", "%b %d",
        "%d %B", "%d %b", "%m/%d/%Y", "%d/%m/%Y", "%m/%d", "%d/%m"
    ]
    
    for fmt in formats:
        try:
            parsed = datetime.strptime(date_str, fmt)
            if parsed.year == 1900:
                parsed = parsed.replace(year=today.year)
            if parsed.date() < today.date():
                parsed = parsed.replace(year=today.year + 1)
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            continue
    
    return date_str

def schedule_appointment(date: str, time: str, purpose: str, client_name: str, client_email: str) -> Dict:
    date = normalize_date_format(date)
    time = normalize_time_format(time)
    
    appt_id = str(random.randint(100, 999))
    
    calendar_event_id = None
    if calendar_service:
        try:
            start_dt = datetime.fromisoformat(f"{date}T{time}")
            start_dt = TIMEZONE.localize(start_dt)
            end_dt = start_dt + timedelta(minutes=30)
            
            event = {
                'summary': f"{purpose} - {client_name}",
                'start': {
                    'dateTime': start_dt.isoformat(),
                    'timeZone': 'Asia/Kolkata'
                },
                'end': {
                    'dateTime': end_dt.isoformat(),
                    'timeZone': 'Asia/Kolkata'
                },
                'description': f'Client: {client_name}\nEmail: {client_email}\nPurpose: {purpose}\nID: {appt_id}\n\nCreated: {datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")}'
            }
            
            user_email = os.getenv("FROM_EMAIL")
            created = calendar_service.events().insert(calendarId=user_email, body=event).execute()
            calendar_event_id = created.get('id')
            
        except Exception as e:
            print(f"Calendar error: {e}")
            return {
                "success": False,
                "error": f"Failed to create appointment: {str(e)}",
                "appointment_id": appt_id
            }
    
    email_result = send_appointment_confirmation(
        client_email=client_email,
        client_name=client_name,
        date=date,
        time=time,
        purpose=purpose,
        appointment_id=calendar_event_id or appt_id
    )
    
    return {
        "appointment_id": calendar_event_id or appt_id, 
        "confirmed_date": date,
        "confirmed_time": time,
        "original_date": date,
        "original_time": time,
        "client_name": client_name,
        "client_email": client_email,
        "email_confirmation": email_result,
        "google_calendar_id": calendar_event_id
    }

def modify_appointment(appointment_id: str, new_date: Optional[str] = None, new_time: Optional[str] = None) -> Dict:
    """Modify an appointment by its Google Calendar event ID"""
    
    if calendar_service is not None:
        try:
            user_email = os.getenv("FROM_EMAIL")
            event = calendar_service.events().get(calendarId=user_email, eventId=appointment_id).execute()
            
            if not event:
                return {"success": False, "error": "Appointment not found"}
            
            start = event.get('start', {})
            if 'dateTime' not in start:
                return {"success": False, "error": "Invalid appointment format"}
            
            nowtime_str = start['dateTime']
            if nowtime_str.endswith('Z'):
                nowtime = datetime.fromisoformat(nowtime_str.replace('Z', '+00:00'))
                nowtime_ist = nowtime.astimezone(TIMEZONE)
            else:
                nowtime = datetime.fromisoformat(nowtime_str)
                if nowtime.tzinfo is None:
                    nowtime_ist = TIMEZONE.localize(nowtime)
                else:
                    nowtime_ist = nowtime.astimezone(TIMEZONE)
            
            old_date = nowtime_ist.strftime("%Y-%m-%d")
            old_time = nowtime_ist.strftime("%H:%M")
            
            description = event.get('description', '')
            client_email = ""
            client_name = "Unknown"
            
            if "Email:" in description:
                try:
                    client_email = description.split("Email:")[1].split("\n")[0].strip()
                except:
                    pass
            
            if "Client:" in description:
                try:
                    client_name = description.split("Client:")[1].split("\n")[0].strip()
                except:
                    pass
            
            updated_date = new_date if new_date else old_date
            updated_time = new_time if new_time else old_time
            
            new_start_datetime = datetime.fromisoformat(f"{updated_date}T{updated_time}")
            new_start_datetime_ist = TIMEZONE.localize(new_start_datetime)
            new_end_datetime_ist = new_start_datetime_ist + timedelta(minutes=30)
            
            event['start'] = {
                'dateTime': new_start_datetime_ist.isoformat(),
                'timeZone': 'Asia/Kolkata'
            }
            event['end'] = {
                'dateTime': new_end_datetime_ist.isoformat(),
                'timeZone': 'Asia/Kolkata'
            }
            
            original_description = event.get('description', '')
            event['description'] = f"{original_description}\n\nModified via AI Assistant on {datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')} TIMEZONE"
            
            calendar_service.events().update(calendarId=user_email, eventId=appointment_id, body=event).execute()
            
            return {
                "success": True,
                "appointment_id": appointment_id, 
                "old_date": old_date,
                "old_time": old_time,
                "updated_date": updated_date, 
                "updated_time": updated_time,
                "client_name": client_name,
                "client_email": client_email
            }
            
        except Exception as e:
            print(f"Could not update calendar event: {e}")
            return {
                "success": False,
                "error": f"Failed to update Google Calendar: {str(e)}",
                "appointment_id": appointment_id
            }
    else:
        return {
            "success": False,
            "error": "Google Calendar not configured",
            "appointment_id": appointment_id
        }

def reschedule_appointment(client_email: str, old_date: str, old_time: str, new_date: str, new_time: str) -> Dict:
    """Reschedule an appointment by client email, old date/time, and new date/time"""
    client_email = client_email.lower().strip()
    
    normalized_old_date = normalize_date_format(old_date)
    normalized_new_date = normalize_date_format(new_date)
    normalized_old_time = normalize_time_format(old_time)
    normalized_new_time = normalize_time_format(new_time)
    
    rescheduled_appointments = []
    
    if calendar_service is not None:
        try:
            time_min = f"{old_date}T00:00:00Z"
            time_max = f"{old_date}T23:59:59Z"
            
            user_email = os.getenv("FROM_EMAIL")
            events_result = calendar_service.events().list(
                calendarId=user_email,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True
            ).execute()
            
            events = events_result.get('items', [])
            
            for event in events:
                description = event.get('description', '')
                start = event.get('start', {})
                
                if client_email in description.lower() and 'dateTime' in start:
                    try:
                        old_scheduled_datetime = datetime.fromisoformat(f"{old_date}T{old_time}:00")
                        old_scheduled_datetime_ist = TIMEZONE.localize(old_scheduled_datetime)
                        
                        event_datetime_str = start['dateTime']
                        if event_datetime_str.endswith('Z'):
                            event_datetime = datetime.fromisoformat(event_datetime_str.replace('Z', '+00:00'))
                            event_datetime_ist = event_datetime.astimezone(TIMEZONE)
                        else:
                            event_datetime = datetime.fromisoformat(event_datetime_str)
                            if event_datetime.tzinfo is None:
                                event_datetime_ist = TIMEZONE.localize(event_datetime)
                            else:
                                event_datetime_ist = event_datetime.astimezone(TIMEZONE)
                        
                        if (event_datetime_ist.date() == old_scheduled_datetime_ist.date() and 
                            event_datetime_ist.hour == old_scheduled_datetime_ist.hour):
                            
                            new_start_datetime = datetime.fromisoformat(f"{new_date}T{new_time}")
                            new_start_datetime_ist = TIMEZONE.localize(new_start_datetime)
                            new_end_datetime_ist = new_start_datetime_ist + timedelta(minutes=30)
                            
                            event['start'] = {
                                'dateTime': new_start_datetime_ist.isoformat(),
                                'timeZone': 'Asia/Kolkata'
                            }
                            event['end'] = {
                                'dateTime': new_end_datetime_ist.isoformat(),
                                'timeZone': 'Asia/Kolkata'
                            }
                            
                            event['description'] = f"{description}\n\nRescheduled via AI Assistant on {datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')} TIMEZONE\nMoved from {old_date} {old_time} to {new_date} {new_time}"
                            
                            calendar_service.events().update(calendarId=user_email, eventId=event['id'], body=event).execute()
                            
                            client_name = "Unknown"
                            if "Client:" in description:
                                try:
                                    client_name = description.split("Client:")[1].split("\n")[0].strip()
                                except:
                                    pass
                            
                            rescheduled_appointments.append({
                                "source": "google_calendar",
                                "appointment_id": event['id'],
                                "old_date": old_date,
                                "old_time": old_time,
                                "new_date": new_date,
                                "new_time": new_time,
                                "purpose": event.get('summary', 'No title').replace(f" - {client_name}", ""),
                                "client_name": client_name
                            })
                            break
                            
                    except Exception as parse_error:
                        print(f"Could not parse datetime for event rescheduling: {parse_error}")
                        continue
            
        except Exception as e:
            print(f"Could not reschedule Google Calendar event: {e}")
            return {
                "success": False,
                "error": f"Failed to reschedule appointment in Google Calendar: {str(e)}",
                "client_email": client_email,
                "old_date": old_date,
                "old_time": old_time,
                "new_date": new_date,
                "new_time": new_time
            }
    else:
        return {
            "success": False,
            "error": "Google Calendar not configured",
            "client_email": client_email,
            "old_date": old_date,
            "old_time": old_time,
            "new_date": new_date,
            "new_time": new_time
        }
    
    if rescheduled_appointments:
        email_result = None
        if rescheduled_appointments:
            first_appointment = rescheduled_appointments[0]
            client_name = first_appointment.get('client_name', 'Valued Client')
            purpose = first_appointment.get('purpose', 'Appointment')
            
            email_body = f"""
            <html>
              <body>
                <h2>Appointment Rescheduled</h2>
                <p>Dear {client_name},</p>
                <p>Your appointment has been successfully rescheduled:</p>
                <p><strong>Previous:</strong> {old_date} at {old_time}</p>
                <p><strong>New:</strong> {normalized_new_date} at {normalized_new_time}</p>
                <p><strong>Purpose:</strong> {purpose}</p>
                <p>📅 <strong>Updated Calendar Invite:</strong> A new calendar file (.ics) is attached to this email. Click on it to update the appointment in your calendar.</p>
                <p>If you have any questions, please don't hesitate to contact us.</p>
                <p>Best regards,<br>Appointment System</p>
              </body>
            </html>
            """
            
            appointment_id = first_appointment.get('appointment_id', 'RESCHEDULED')
            calendar_invite = create_calendar_invite(
                client_name=client_name,
                date=normalized_new_date,
                time=normalized_new_time,
                purpose=purpose,
                appointment_id=str(appointment_id)
            )
            
            email_result = send_email(
                to=client_email,
                subject=f"Appointment Rescheduled - {normalized_new_date} at {normalized_new_time}",
                body=email_body,
                calendar_invite=calendar_invite
            )
        
        return {
            "success": True,
            "message": f"rescheduled appointment(s) for {client_email}",
            "rescheduled_appointments": rescheduled_appointments,
            "client_email": client_email,
            "old_date": old_date,
            "old_time": old_time,
            "new_date": new_date,
            "new_time": new_time,
            "total_rescheduled": len(rescheduled_appointments),
            "email_confirmation": email_result
        }
    else:
        return {
            "success": False,
            "error": "No appointment found matching the specified criteria",
            "client_email": client_email,
            "old_date": old_date,
            "old_time": old_time,
            "new_date": new_date,
            "new_time": new_time
        }

def cancel_appointment(client_email: str, date: str, time: str) -> Dict:
    """Cancel an appointment by client email, date, and time"""
    client_email = client_email.lower().strip()
    
    date = normalize_date_format(date)
    time = normalize_time_format(time)
    
    cancelled_appointments = []
    
    if calendar_service is not None:
        try:
            time_min = f"{date}T00:00:00Z"
            time_max = f"{date}T23:59:59Z"
            
            user_email = os.getenv("FROM_EMAIL")
            events_result = calendar_service.events().list(
                calendarId=user_email,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True
            ).execute()
            
            events = events_result.get('items', [])
            
            for event in events:
                description = event.get('description', '')
                start = event.get('start', {})
                
                if client_email in description.lower() and 'dateTime' in start:
                    try:
                        scheduled_datetime = datetime.fromisoformat(f"{date}T{time}:00")
                        scheduled_datetime_ist = TIMEZONE.localize(scheduled_datetime)
                        
                        event_datetime_str = start['dateTime']
                        if event_datetime_str.endswith('Z'):
                            event_datetime = datetime.fromisoformat(event_datetime_str.replace('Z', '+00:00'))
                            event_datetime_ist = event_datetime.astimezone(TIMEZONE)
                        else:
                            event_datetime = datetime.fromisoformat(event_datetime_str)
                            if event_datetime.tzinfo is None:
                                event_datetime_ist = TIMEZONE.localize(event_datetime)
                            else:
                                event_datetime_ist = event_datetime.astimezone(TIMEZONE)
                        
                        if (event_datetime_ist.date() == scheduled_datetime_ist.date() and 
                            event_datetime_ist.hour == scheduled_datetime_ist.hour):
                            
                            calendar_service.events().delete(calendarId=user_email, eventId=event['id']).execute()
                            
                            client_name = "Unknown"
                            if "Client:" in description:
                                try:
                                    client_name = description.split("Client:")[1].split("\n")[0].strip()
                                except:
                                    pass
                            
                            cancelled_appointments.append({
                                "source": "google_calendar",
                                "appointment_id": event['id'],
                                "date": date,
                                "time": time,
                                "purpose": event.get('summary', 'No title').replace(f" - {client_name}", ""),
                                "client_name": client_name
                            })
                            break
                            
                    except Exception as parse_error:
                        print(f"Could not parse datetime for event comparison: {parse_error}")
                        continue
            
        except Exception as e:
            print(f"Could not cancel Google Calendar event: {e}")
            return {
                "success": False,
                "error": f"Failed to cancel appointment from Google Calendar: {str(e)}",
                "client_email": client_email,
                "requested_date": date,
                "requested_time": time
            }
    else:
        return {
            "success": False,
            "error": "Google Calendar not configured",
            "client_email": client_email,
            "requested_date": date,
            "requested_time": time
        }
    
    if cancelled_appointments:
        email_result = None
        if cancelled_appointments:
            first_appointment = cancelled_appointments[0]
            client_name = first_appointment.get('client_name', 'Valued Client')
            purpose = first_appointment.get('purpose', 'Appointment')
            
            email_body = f"""
            <html>
              <body>
                <h2>Appointment Cancelled</h2>
                <p>Dear {client_name},</p>
                <p>Your appointment has been successfully cancelled:</p>
                <p><strong>Date:</strong> {date}</p>
                <p><strong>Time:</strong> {time}</p>
                <p><strong>Purpose:</strong> {purpose}</p>
                <p>📅 <strong>Calendar Update:</strong> This appointment has been automatically removed from our system. A cancellation file (.ics) is attached to this email - click on it to automatically remove the appointment from your personal calendar apps (Outlook, Apple Calendar, Google Calendar, etc.).</p>
                <p><strong>🔄 What happens next:</strong></p>
                <ul>
                  <li>✅ Removed from our booking system</li>
                  <li>✅ Removed from our Google Calendar</li>
                  <li>📎 Click the attached .ics file to remove from your personal calendar</li>
                </ul>
                <p>If you need to reschedule or have any questions, please don't hesitate to contact us.</p>
                <p>Best regards,<br>Appointment System</p>
              </body>
            </html>
            """
            
            appointment_id = first_appointment.get('appointment_id', 'CANCELLED')
            cancellation_invite = create_cancellation_invite(
                client_name=client_name,
                date=date,
                time=time,
                purpose=purpose,
                appointment_id=str(appointment_id)
            )
            
            email_result = send_email(
                to=client_email,
                subject=f"Appointment Cancelled - {date} at {time}",
                body=email_body,
                calendar_invite=cancellation_invite
            )
        
        return {
            "success": True,
            "message": f"cancelled appointment(s) for {client_email}",
            "cancelled_appointments": cancelled_appointments,
            "client_email": client_email,
            "cancelled_date": date,
            "cancelled_time": time,
            "total_cancelled": len(cancelled_appointments),
            "email_confirmation": email_result
        }
    else:
        return {
            "success": False,
            "error": "No appointment found matching the specified criteria",
            "client_email": client_email,
            "requested_date": date,
            "requested_time": time
        }

def create_calendar_invite(client_name: str, date: str, time: str, purpose: str, appointment_id: str, status: str = "CONFIRMED") -> str:
    try:
        cal = Calendar()
        cal.add('prodid', '-//Appointment System//EN')
        cal.add('version', '2.0')
        cal.add('calscale', 'GREGORIAN')
        cal.add('method', 'REQUEST' if status == "CONFIRMED" else 'CANCEL')
        
        event = Event()
        
        appointment_dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
        start_time = TIMEZONE.localize(appointment_dt)
        end_time = start_time + timedelta(hours=1)
        
        event.add('summary', f'Appointment: {purpose}')
        event.add('dtstart', start_time)
        event.add('dtend', end_time)
        event.add('description', f'Appointment with {client_name}\nPurpose: {purpose}\nID: {appointment_id}')
        event.add('location', 'To be confirmed')
        event.add('uid', f'{appointment_id}@appointmentbookingsystem.com')
        event.add('priority', 5)
        event.add('status', status)
        event.add('sequence', 1 if status == "CANCELLED" else 0)
        
        from_email = os.getenv("FROM_EMAIL", "appointments@bookingsystem.com")
        event.add('organizer', f'mailto:{from_email}')
        event.add('attendee', f'mailto:{client_name.lower().replace(" ", ".")}@example.com')
        
        cal.add_component(event)
        return cal.to_ical().decode('utf-8')
        
    except Exception as e:
        print(f"Error creating calendar invite: {e}")
        return ""

def create_cancellation_invite(client_name: str, date: str, time: str, purpose: str, appointment_id: str) -> str:
    return create_calendar_invite(client_name, date, time, purpose, appointment_id, status="CANCELLED")

def send_email(to: str, subject: str, body: str, calendar_invite: Optional[str] = None) -> Dict:
    api_key = os.getenv("SENDGRID_API_KEY")
    from_email = os.getenv("FROM_EMAIL")
    
    if not api_key or not from_email:
        print("Email service not configured")
        return {"success": False, "error": "Email service not configured"}
    
    msg = Mail(from_email=from_email, to_emails=to, subject=subject, html_content=body)
    
    if calendar_invite:
        try:
            calendar_data = base64.b64encode(calendar_invite.encode()).decode()
            filename = "appointment_cancellation.ics" if "METHOD:CANCEL" in calendar_invite else "appointment.ics"
            
            attachment = Attachment(
                FileContent(calendar_data),
                FileName(filename),
                FileType("text/calendar"),
                Disposition("attachment")
            )
            msg.attachment = attachment
        except Exception as e:
            print(f"Failed to attach calendar: {e}")
    
    try:
        sg = SendGridAPIClient(api_key)
        response = sg.send(msg)
        print(f"Email sent to {to} - Status: {response.status_code}")
        return {
            "success": True, 
            "status_code": response.status_code,
            "recipient": to,
            "subject": subject,
            "real_email": True
        }
    except Exception as e:
        print(f"Failed to send email to {to}: {e}")
        return {
            "success": False, 
            "error": str(e),
            "recipient": to,
            "subject": subject,
            "real_email": False
        }

def send_appointment_confirmation(client_email: str, client_name: str, date: str, time: str, purpose: str, appointment_id: str) -> Dict:
    try:
        email_body = f"""
        <html>
          <body>
            <h2>Appointment Confirmation</h2>
            <p>Dear {client_name},</p>
            <p>Your appointment has been successfully scheduled:</p>
            <p><strong>Date:</strong> {date}</p>
            <p><strong>Time:</strong> {time}</p>
            <p><strong>Purpose:</strong> {purpose}</p>
            <p><strong>ID:</strong> {appointment_id}</p>
            <p>📅 A calendar file (.ics) is attached - click it to add to your calendar.</p>
            <p>Save this confirmation for your records. Contact us with your appointment ID for changes.</p>
            <p>We look forward to seeing you!</p>
            <p>Best regards,<br>Appointment System</p>
          </body>
        </html>
        """
        
        calendar_invite = create_calendar_invite(client_name, date, time, purpose, appointment_id)
        
        result = send_email(
            to=client_email,
            subject=f"Appointment Confirmation - {date} at {time}",
            body=email_body,
            calendar_invite=calendar_invite
        )
        
        return {
            "email_sent": result.get("success", False),
            "email_details": result,
            "recipient": client_email,
            "appointment_id": appointment_id
        }
        
    except Exception as e:
        return {
            "email_sent": False,
            "error": str(e),
            "recipient": client_email,
            "appointment_id": appointment_id
        }

def list_appointments(date: Optional[str] = None) -> Dict:
    """List all appointments from Google Calendar, optionally filtered by date"""
    appointments = []
    
    if calendar_service is not None and date:
        try:
            time_min = f"{date}T00:00:00Z"
            time_max = f"{date}T23:59:59Z"
            
            user_email = os.getenv("FROM_EMAIL")
            events_result = calendar_service.events().list(
                calendarId=user_email,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            for event in events:
                start = event.get('start', {})
                if 'dateTime' in start:
                    event_datetime_str = start['dateTime']
                    if event_datetime_str.endswith('Z'):
                        event_datetime = datetime.fromisoformat(event_datetime_str.replace('Z', '+00:00'))
                        event_datetime = event_datetime.astimezone(TIMEZONE)
                    else:
                        event_datetime = datetime.fromisoformat(event_datetime_str)
                        if event_datetime.tzinfo is None:
                            event_datetime = TIMEZONE.localize(event_datetime)
                        else:
                            event_datetime = event_datetime.astimezone(TIMEZONE)
                    
                    appointments.append({
                        "source": "google_calendar",
                        "appointment_id": event.get('id'),
                        "date": event_datetime.strftime("%Y-%m-%d"),
                        "time": event_datetime.strftime("%H:%M"),
                        "purpose": event.get('summary', 'No title')
                    })
                    
        except Exception as e:
            print(f"Could not fetch Google Calendar events: {e}")
    elif not date:
        all_appointments_result = get_all_appointments()
        appointments = all_appointments_result["all_appointments"]
    
    return {
        "appointments": appointments,
        "total_count": len(appointments),
        "date_filter": date
    }

def get_user_appointments(client_email: str) -> Dict:
    client_email = client_email.lower().strip()
    appointments = []
    now = datetime.now(TIMEZONE)
    
    if calendar_service:
        try:
            start_range = (now - timedelta(days=30)).isoformat()
            end_range = (now + timedelta(days=60)).isoformat()
            
            user_email = os.getenv("FROM_EMAIL")
            events = calendar_service.events().list(
                calendarId=user_email,
                timeMin=start_range,
                timeMax=end_range,
                singleEvents=True,
                orderBy='startTime',
                q=client_email
            ).execute()
            
            for event in events.get('items', []):
                start = event.get('start', {})
                description = event.get('description', '')
                if 'dateTime' in start and client_email in description.lower():
                    event_datetime_str = start['dateTime']
                    if event_datetime_str.endswith('Z'):
                        event_datetime = datetime.fromisoformat(event_datetime_str.replace('Z', '+00:00'))
                        event_datetime = event_datetime.astimezone(TIMEZONE)
                    else:
                        event_datetime = datetime.fromisoformat(event_datetime_str)
                        if event_datetime.tzinfo is None:
                            event_datetime = TIMEZONE.localize(event_datetime)
                        else:
                            event_datetime = event_datetime.astimezone(TIMEZONE)
                    
                    client_name = "Unknown"
                    if "Client:" in description:
                        try:
                            client_name = description.split("Client:")[1].split("\n")[0].strip()
                        except:
                            pass
                    
                    appointments.append({
                        "source": "google_calendar",
                        "appointment_id": event.get('id'),
                        "datetime_str": event_datetime.isoformat(),
                        "date": event_datetime.strftime("%Y-%m-%d"),
                        "time": event_datetime.strftime("%H:%M"),
                        "purpose": event.get('summary', 'No title').replace(f" - {client_name}", ""),
                        "client_name": client_name,
                        "client_email": client_email,
                        "is_upcoming": event_datetime > now
                    })
                    
        except Exception as e:
            print(f"Could not fetch Google Calendar events: {e}")
    else:
        print("Google Calendar not configured")
    
    appointments.sort(key=lambda x: x['datetime_str'])
    
    upcoming = [apt for apt in appointments if apt['is_upcoming']]
    previous = [apt for apt in appointments if not apt['is_upcoming']]
    
    return {
        "client_email": client_email,
        "all_appointments": appointments,
        "upcoming_appointments": upcoming,
        "previous_appointments": previous,
        "total_count": len(appointments),
        "upcoming_count": len(upcoming),
        "previous_count": len(previous)
    }

def get_all_appointments() -> Dict:
    """Get all appointments from Google Calendar"""
    appointments = []
    now = datetime.now(TIMEZONE)
    
    if calendar_service is not None:
        try:
            time_min = (now - timedelta(days=30)).isoformat()
            time_max = (now + timedelta(days=60)).isoformat()
            
            user_email = os.getenv("FROM_EMAIL")
            events_result = calendar_service.events().list(
                calendarId=user_email,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            for event in events:
                start = event.get('start', {})
                if 'dateTime' in start:
                    event_datetime_str = start['dateTime']
                    if event_datetime_str.endswith('Z'):
                        event_datetime = datetime.fromisoformat(event_datetime_str.replace('Z', '+00:00'))
                        event_datetime = event_datetime.astimezone(TIMEZONE)
                    else:
                        event_datetime = datetime.fromisoformat(event_datetime_str)
                        if event_datetime.tzinfo is None:
                            event_datetime = TIMEZONE.localize(event_datetime)
                        else:
                            event_datetime = event_datetime.astimezone(TIMEZONE)
                    
                    description = event.get('description', '')
                    client_name = "Unknown"
                    client_email = ""
                    
                    if "Client:" in description:
                        try:
                            client_name = description.split("Client:")[1].split("\n")[0].strip()
                        except:
                            pass
                    
                    if "Email:" in description:
                        try:
                            client_email = description.split("Email:")[1].split("\n")[0].strip()
                        except:
                            pass
                    
                    appointments.append({
                        "source": "google_calendar",
                        "appointment_id": event.get('id'),
                        "datetime": event_datetime,
                        "date": event_datetime.strftime("%Y-%m-%d"),
                        "time": event_datetime.strftime("%H:%M"),
                        "purpose": event.get('summary', 'No title').replace(f" - {client_name}", ""),
                        "client_name": client_name,
                        "client_email": client_email,
                        "is_upcoming": event_datetime > now
                    })
                    
        except Exception as e:
            print(f"Could not fetch Google Calendar events: {e}")
    else:
        print("Google Calendar not configured")
    
    appointments.sort(key=lambda x: x['datetime'])
    
    upcoming = [apt for apt in appointments if apt['is_upcoming']]
    previous = [apt for apt in appointments if not apt['is_upcoming']]
    
    return {
        "all_appointments": appointments,
        "upcoming_appointments": upcoming,
        "previous_appointments": previous,
        "total_count": len(appointments),
        "upcoming_count": len(upcoming),
        "previous_count": len(previous)
    }
