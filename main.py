import os
import json
import base64
import warnings

from pathlib import Path
from dotenv import load_dotenv

from google.genai.types import (
    Part,
    Content,
    Blob,
)

from google.adk.runners import InMemoryRunner
from google.adk.agents import LiveRequestQueue
from google.adk.agents.run_config import RunConfig
from google.genai import types

from fastapi import FastAPI, Request, File, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from fir_agent.agent import root_agent

warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

#
# ADK Streaming
#

# Load Gemini API Key
load_dotenv()

APP_NAME = "FIR Agent"


class SimpleAgent:
    """A simple agent implementation that bypasses ADK complexity"""
    
    def __init__(self):
        import os
        from google.genai import Client
        
        self.api_key = os.getenv('GOOGLE_API_KEY')
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY environment variable is not set. Please add it to your .env file.")
        
        self.client = Client(api_key=self.api_key)
        self.welcome_sent = False
    
    async def process_message(self, message: str) -> str:
        """Process a user message and return a response"""
        try:
            # Send welcome message if this is the first interaction
            if not self.welcome_sent:
                self.welcome_sent = True
                return "Hello, I am Saathi, your digital assistant for filing an FIR. I understand this might be a difficult time, and I'm here to help you through the process step-by-step. To begin, could you please tell me about the incident you wish to report?"
            
            # Check if this is a document upload message
            if message.startswith("I have uploaded a document:"):
                # Extract and process document content
                return f"Thank you for uploading the document. I've reviewed the content and will use this information to help with your FIR. Based on the document, please let me know if there are any additional details you'd like to add or clarify about the incident."
            
            # System prompt for FIR agent
            system_prompt = """You are "Saathi," an intelligent and empathetic Digital FIR (First Information Report) Assistant for the Indian Police. 

Your goal is to guide users step-by-step through filing an FIR. Be friendly, empathetic, and professional.

Required information to collect:
- Complainant's full name
- Complainant's address  
- Complainant's phone number
- Date and time of the incident
- Location of the incident
- Nature/type of complaint (theft, assault, cybercrime, etc.)
- Detailed description of the incident

Ask for information gradually, not all at once. When you have all required information, say: "Thanks for providing all the details. Your information has been successfully collected for the FIR. Be assured, we will help you. The concerned authorities will be in touch."

Be conversational and empathetic. Ask follow-up questions to get complete details.
"""
            
            # Generate response using Gemini
            response = self.client.chats.generate_content(
                model="gemini-2.0-flash-exp",
                contents=[
                    {"role": "system", "parts": [{"text": system_prompt}]},
                    {"role": "user", "parts": [{"text": message}]}
                ]
            )
            
            return response.text
            
        except Exception as e:
            return f"I apologize, but I'm experiencing technical difficulties. Error: {str(e)}"

# Global agent instance
simple_agent = None

async def start_agent_session(user_id, is_audio=False):
    """Starts a simple agent session"""
    global simple_agent
    
    try:
        if simple_agent is None:
            simple_agent = SimpleAgent()
        
        # Return a mock live_events generator and a simple queue
        class SimpleQueue:
            def __init__(self):
                self.messages = []
                self.closed = False
            
            def send_content(self, content):
                if not self.closed:
                    self.messages.append(content.parts[0].text)
                    print(f"[QUEUE] Added text message: {content.parts[0].text[:50]}...")
            
            def send_realtime(self, blob):
                if not self.closed:
                    # For audio, we'll add a placeholder message
                    # In a full implementation, you'd transcribe the audio here
                    self.messages.append("[Audio message received - transcription not implemented]")
                    print(f"[QUEUE] Added audio message: {len(blob.data)} bytes")
            
            def close(self):
                self.closed = True
                print(f"[QUEUE] Queue closed")
        
        live_request_queue = SimpleQueue()
        
        # Create a simple async generator that yields welcome message
        async def simple_live_events():
            import asyncio
            
            # Send welcome message
            welcome_response = await simple_agent.process_message("")
            
            # Yield the welcome message
            yield type('Event', (), {
                'content': type('Content', (), {
                    'parts': [type('Part', (), {'text': welcome_response})()]
                })(),
                'partial': False,
                'turn_complete': True,  # Mark welcome as complete
                'interrupted': False
            })()
            
            print(f"[AGENT] Welcome message sent for user {user_id}")
            
            # Process any queued messages
            while not live_request_queue.closed:
                if live_request_queue.messages:
                    message = live_request_queue.messages.pop(0)
                    print(f"[AGENT] Processing message: {message}")
                    
                    response = await simple_agent.process_message(message)
                    print(f"[AGENT] Generated response: {response}")
                    
                    # Yield the response
                    yield type('Event', (), {
                        'content': type('Content', (), {
                            'parts': [type('Part', (), {'text': response})()]
                        })(),
                        'partial': False,
                        'turn_complete': True,
                        'interrupted': False
                    })()
                    
                    print(f"[AGENT] Response sent for user {user_id}")
                else:
                    await asyncio.sleep(0.1)
            
            print(f"[AGENT] Event loop ended for user {user_id}")
        
        return simple_live_events(), live_request_queue
        
    except Exception as e:
        raise ValueError(f"Failed to initialize simple agent: {str(e)}")


async def agent_to_client_sse(live_events):
    """Agent to client communication via SSE"""
    async for event in live_events:
        try:
            # If the turn complete or interrupted, send it
            if hasattr(event, 'turn_complete') and (event.turn_complete or event.interrupted):
                message = {
                    "turn_complete": event.turn_complete,
                    "interrupted": event.interrupted,
                }
                yield f"data: {json.dumps(message)}\n\n"
                print(f"[AGENT TO CLIENT]: {message}")
                continue

            # Read the Content and its first Part
            if hasattr(event, 'content') and event.content and hasattr(event.content, 'parts') and event.content.parts:
                part = event.content.parts[0]
                
                # Check if it's text
                if hasattr(part, 'text') and part.text:
                    message = {
                        "mime_type": "text/plain",
                        "data": part.text
                    }
                    yield f"data: {json.dumps(message)}\n\n"
                    print(f"[AGENT TO CLIENT]: text/plain: {part.text}")
            
            # Send turn complete after processing content
            if hasattr(event, 'turn_complete') and event.turn_complete:
                complete_message = {
                    "turn_complete": True,
                    "interrupted": False,
                }
                yield f"data: {json.dumps(complete_message)}\n\n"
                print(f"[AGENT TO CLIENT]: {complete_message}")
        
        except Exception as e:
            print(f"Error in agent_to_client_sse: {e}")
            error_message = {
                "error": True,
                "message": str(e)
            }
            yield f"data: {json.dumps(error_message)}\n\n"


#
# FastAPI web app
#

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path("static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Store active sessions
active_sessions = {}

@app.post("/upload_file")
async def upload_file(file: UploadFile = File(...)):
    """Uploads and parses a file."""
    try:
        # Save the uploaded file
        file_path = f"/tmp/{file.filename}"
        with open(file_path, "wb") as f:
            f.write(await file.read())
        
        # Parse the document using our tools
        from fir_agent.tools import parse_document
        document_content = parse_document(file_path)
        
        print(f"[FILE UPLOAD] Parsed document: {file.filename}")
        print(f"[FILE UPLOAD] Content length: {len(document_content)} characters")
        
        # Create a message with the document content
        message = f"I have uploaded a document: {file.filename}. Here is the content:\n\n{document_content}"
        
        # Find an active session to send this to
        # For now, use the most recent session
        if active_sessions:
            user_id = list(active_sessions.keys())[-1]  # Get the most recent session
            live_request_queue = active_sessions.get(user_id)
            
            if live_request_queue:
                # Create a mock content object
                class MockContent:
                    def __init__(self, text):
                        self.parts = [type('Part', (), {'text': text})()]
                
                live_request_queue.send_content(MockContent(message))
                print(f"[FILE UPLOAD] Sent to agent for user {user_id}")
                
                # Clean up the temp file
                import os
                try:
                    os.remove(file_path)
                except:
                    pass
                
                return {"success": True, "message": f"Document {file.filename} uploaded and processed"}
            else:
                return {"success": False, "message": "No active session found"}
        else:
            return {"success": False, "message": "No active sessions available"}

    except Exception as e:
        print(f"[FILE UPLOAD] Error: {e}")
        return {"success": False, "message": str(e)}


@app.get("/")
async def root():
    """Serves the index.html"""
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/events/{user_id}")
async def sse_endpoint(user_id: str, is_audio: str = "false"):
    """SSE endpoint for agent to client communication"""

    async def event_generator():
        try:
            # Start agent session
            live_events, live_request_queue = await start_agent_session(user_id, is_audio == "true")

            # Store the request queue for this user
            active_sessions[user_id] = live_request_queue

            print(f"Client #{user_id} connected via SSE, audio mode: {is_audio}")

            def cleanup():
                live_request_queue.close()
                if user_id in active_sessions:
                    del active_sessions[user_id]
                print(f"Client #{user_id} disconnected from SSE")

            try:
                async for data in agent_to_client_sse(live_events):
                    yield data
            except Exception as e:
                print(f"Error in SSE stream: {e}")
                # Send error message to client
                error_message = {
                    "error": True,
                    "message": str(e)
                }
                yield f"data: {json.dumps(error_message)}\n\n"
            finally:
                cleanup()

        except ValueError as e:
            print(f"Agent initialization failed: {e}")
            # Send error message to client
            error_message = {
                "error": True,
                "message": str(e),
                "suggestion": "Please check your Google API key configuration."
            }
            yield f"data: {json.dumps(error_message)}\n\n"
        except Exception as e:
            print(f"Unexpected error: {e}")
            error_message = {
                "error": True,
                "message": "Failed to start agent session",
                "details": str(e)
            }
            yield f"data: {json.dumps(error_message)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control"
        }
    )


@app.post("/send/{user_id}")
async def send_message_endpoint(user_id: str, request: Request):
    """HTTP endpoint for client to agent communication"""

    # Get the live request queue for this user
    live_request_queue = active_sessions.get(user_id)
    if not live_request_queue:
        return {"error": "Session not found"}

    # Parse the message
    message = await request.json()
    mime_type = message["mime_type"]
    data = message["data"]

    # Send the message to the agent
    if mime_type == "text/plain":
        content = Content(role="user", parts=[Part.from_text(text=data)])
        live_request_queue.send_content(content=content)
        print(f"[CLIENT TO AGENT]: {data}")
    elif mime_type == "audio/pcm":
        decoded_data = base64.b64decode(data)
        live_request_queue.send_realtime(Blob(data=decoded_data, mime_type=mime_type))
        print(f"[CLIENT TO AGENT]: audio/pcm: {len(decoded_data)} bytes")
    else:
        return {"error": f"Mime type not supported: {mime_type}"}

    return {"status": "sent"}
