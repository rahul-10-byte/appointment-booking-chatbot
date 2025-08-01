import os
import json
from typing import Optional
from fastapi import FastAPI, Request # type: ignore
from fastapi.staticfiles import StaticFiles # type: ignore
from fastapi.responses import FileResponse # type: ignore
from fastapi.middleware.cors import CORSMiddleware # type: ignore
from pydantic import BaseModel # type: ignore
from dotenv import load_dotenv # type: ignore
from openai import OpenAI # type: ignore
from tools import check_availability, schedule_appointment, modify_appointment, send_email, send_appointment_confirmation, get_user_appointments, cancel_appointment, reschedule_appointment

load_dotenv()
app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Serve the main page
@app.get("/")
async def read_index():
    return FileResponse('static/index.html')

class Message(BaseModel):
    role: str
    content: Optional[str] = None
    name: Optional[str] = None
    arguments: Optional[dict] = None

@app.post("/api/chat")
async def chat_endpoint(messages: list[Message]):
    messages_dict = [msg.dict(exclude_none=True) for msg in messages]
    
    tools = [
        {
            "type": "function",
            "function": {
                "name": "check_availability",
                "parameters": {
                    "type": "object",
                    "properties": {"date": {"type": "string"}},
                    "required": ["date"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "schedule_appointment",
                "description": "Schedule a new appointment. Supports relative dates like 'today', 'tomorrow', 'next Monday', etc. and flexible time formats like '3 PM', '15:00', '9am'.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "date": {
                            "type": "string", 
                            "description": "Date for the appointment. Can be relative like 'today', 'tomorrow', 'next Monday' or specific like '2025-08-15', 'Aug 15', etc."
                        },
                        "time": {
                            "type": "string",
                            "description": "Time for the appointment. Supports formats like '3 PM', '15:00', '9am', '14:30', etc."
                        },
                        "purpose": {"type": "string"},
                        "client_name": {"type": "string"},
                        "client_email": {"type": "string"}
                    },
                    "required": ["date", "time", "purpose", "client_name", "client_email"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "modify_appointment",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "appointment_id": {"type": "string"},
                        "new_date": {"type": "string"},
                        "new_time": {"type": "string"}
                    },
                    "required": ["appointment_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "send_email",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "to": {"type": "string"},
                        "subject": {"type": "string"},
                        "body": {"type": "string"}
                    },
                    "required": ["to", "subject", "body"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_user_appointments",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "client_email": {"type": "string"}
                    },
                    "required": ["client_email"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "cancel_appointment",
                "description": "Cancel an existing appointment. Supports relative dates like 'today', 'tomorrow', 'next Monday', etc.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "client_email": {"type": "string"},
                        "date": {
                            "type": "string",
                            "description": "Date of the appointment to cancel. Can be relative like 'today', 'tomorrow' or specific like '2025-08-15'"
                        },
                        "time": {
                            "type": "string",
                            "description": "Time of the appointment to cancel. Supports formats like '3 PM', '15:00', etc."
                        }
                    },
                    "required": ["client_email", "date", "time"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "reschedule_appointment",
                "description": "Reschedule an existing appointment. Supports relative dates like 'today', 'tomorrow', 'next Monday', etc.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "client_email": {"type": "string"},
                        "old_date": {
                            "type": "string",
                            "description": "Current date of the appointment. Can be relative like 'today', 'tomorrow' or specific like '2025-08-15'"
                        },
                        "old_time": {
                            "type": "string", 
                            "description": "Current time of the appointment. Supports formats like '3 PM', '15:00', etc."
                        },
                        "new_date": {
                            "type": "string",
                            "description": "New date for the appointment. Can be relative like 'today', 'tomorrow' or specific like '2025-08-15'"
                        },
                        "new_time": {
                            "type": "string",
                            "description": "New time for the appointment. Supports formats like '3 PM', '15:00', etc."
                        }
                    },
                    "required": ["client_email", "old_date", "old_time", "new_date", "new_time"]
                }
            }
        }
    ]
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages_dict,  # type: ignore
        tools=tools,  # type: ignore
        tool_choice="auto"
    )
    
    msg = response.choices[0].message
    if msg.tool_calls:
        # Add the assistant's message with tool calls to the conversation
        messages_dict.append({
            "role": "assistant",
            "content": msg.content,
            "tool_calls": [
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments
                    }
                }
                for tool_call in msg.tool_calls
            ]
        })
        
        # Add tool responses
        for tool_call in msg.tool_calls:
            fn = tool_call.function.name
            args = json.loads(tool_call.function.arguments)
            tool_result = eval(f"{fn}(**args)")
            messages_dict.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(tool_result)
            })

        followup = client.chat.completions.create(
            model="gpt-4o-mini", 
            messages=messages_dict  # type: ignore
        )
        return followup.choices[0].message
    
    return msg
