# 📅 AI Appointment Booking System

A simple appointment booking system that understands natural language. Just tell it what you want to do with your appointments!

## Features ✨

- **Natural language**: Talk normally - "Book me Tuesday at 3 PM" or "Schedule for tomorrow"
- **Email confirmations**: Get notified for every booking with calendar invites
- **Google Calendar sync**: Appointments appear in your calendar automatically
- **Flexible time formats**: Works with "2 PM" or "14:00"
- **Smart date parsing**: Understands "today", "tomorrow", "next Monday", etc.
- **Indian timezone**: Everything in IST
- **Simple email login**: No passwords needed

## Quick Setup 🚀

### 1. Start the environment
```bash
source myenv/bin/activate
pip install -r requirements.txt
```

### 2. Add your API keys
Copy the example environment file and add your credentials:
```bash
cp .env.example .env
```

Then edit `.env` with your actual API keys:
```
OPENAI_API_KEY=your_openai_api_key
SENDGRID_API_KEY=your_sendgrid_api_key
FROM_EMAIL=your_email@domain.com
GOOGLE_CREDENTIALS_JSON=./creds/google_creds.json
```

### 3. Run it
```bash
uvicorn main:app --port 8001
```
*Note: If you want auto-reload during development, you can add `--reload` flag*

### 4. Use it
Open http://localhost:8001 in your browser

## How to Use 💬

Use natural language through the web interface:

- "Schedule appointment for john@example.com tomorrow at 2 PM"
- "Book me next Tuesday at 3 PM for consultation"
- "Show my appointments" 
- "Reschedule my appointment from today to next Friday at 4 PM"
- "Cancel my appointment tomorrow"

## Project Files 📁

```
├── main.py              # Main server
├── tools.py             # Appointment logic
├── requirements.txt     # Dependencies
├── .env                 # API keys
├── creds/              # Google credentials
├── static/             # Web interface
└── myenv/              # Virtual environment
```

## What It Does 📧

**Google Calendar Primary Storage**: All appointments are stored in your Google Calendar - no local database needed! This ensures appointments persist across restarts and are accessible anywhere.

**Email Confirmations**: Automatic emails with calendar invites (.ics files) for all appointment actions:
- **Booking**: Confirmation email + calendar invite file
- **Rescheduling**: Updated appointment email + new calendar invite
- **Cancellation**: Cancellation notice + removal .ics file that automatically deletes the appointment from client's calendar apps

**Calendar Integration**: 
- Real-time sync with Google Calendar in IST timezone
- Smart cancellation that removes appointments from both our system AND client's personal calendars
- Works with Outlook, Apple Calendar, Google Calendar, and other .ics-compatible apps
- No duplicate appointments - everything stored in one place

**AI Processing**: Uses OpenAI GPT-4o-mini to understand natural language

## API 🛣️

- `GET /` - Web interface
- `POST /api/chat` - Natural language appointment requests
