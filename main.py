import os
import json
import base64
import warnings
import asyncio
import shutil
import tempfile

from pathlib import Path
from dotenv import load_dotenv

from google import genai

from fastapi import FastAPI, Request, File, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from google import genai

# NEW: Import your tool functions to be used directly
from fir_agent import tools
from fir_agent.agent import root_agent

warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

#
# ADK Streaming
#

# Load Gemini API Key
load_dotenv()

APP_NAME = "FIR Agent"

# NEW: Create a directory for file uploads
UPLOADS_DIR = Path("uploads")
UPLOADS_DIR.mkdir(exist_ok=True)


# (SSE/ADK removed)


# NEW: An async generator to read from the transcription queue
async def client_queue_sse(client_queue: asyncio.Queue):
    """Yields messages from the client-facing queue."""
    while True:
        message = await client_queue.get()
        yield f"data: {json.dumps(message)}\n\n"
        print(f"[TRANSCRIPTION TO CLIENT]: {message}")


# NEW: An async generator that merges two event streams into one
async def merge_streams(stream1, stream2):
    """Merges two asynchronous streams of data."""
    task1 = asyncio.create_task(stream1.__anext__())
    task2 = asyncio.create_task(stream2.__anext__())

    while True:
        done, pending = await asyncio.wait(
            [task1, task2], return_when=asyncio.FIRST_COMPLETED
        )

        for task in done:
            try:
                result = task.result()
                yield result
                # Schedule the next item from the stream that just yielded
                if task is task1:
                    task1 = asyncio.create_task(stream1.__anext__())
                else: # task is task2
                    task2 = asyncio.create_task(stream2.__anext__())
            except StopAsyncIteration:
                # One of the streams has finished
                if task is task1:
                    task1 = None
                else: # task is task2
                    task2 = None
        
        if not task1 and not task2:
            break
        # If one task is done, wait for the other
        elif not task1:
            yield await task2
            async for item in stream2: yield item
            break
        elif not task2:
            yield await task1
            async for item in stream1: yield item
            break



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

active_sessions = {}

# Store conversation history for context
conversation_history = []
extracted_info = {}

# CHANGED: This endpoint now handles file uploads for a specific session
@app.post("/upload/{user_id}")
async def upload_file(user_id: str, file: UploadFile = File(...)):
    """Uploads a file, parses it, and sends the content to the agent."""

    file_path = UPLOADS_DIR / file.filename
    try:
        # Save the uploaded file temporarily
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Parse the document using your tool function
        print(f"Parsing document: {file_path}")
        parsed_text = tools.parse_document(str(file_path))

        if parsed_text.startswith("Error:"):
            print(f"Failed to parse document: {parsed_text}")
            return {"success": False, "message": parsed_text}, 400
        
        # Add document content to conversation history
        document_message = f"I have uploaded a document ({file.filename}). Here is the content: {parsed_text}"
        conversation_history.append({"role": "user", "content": document_message})
        
        print(f"[CLIENT TO AGENT]: Parsed content from {file.filename}")
        return {"success": True, "parsed_content": parsed_text}

    except Exception as e:
        return {"success": False, "message": str(e)}, 500
    finally:
        # Clean up the saved file
        if os.path.exists(file_path):
            os.remove(file_path)


@app.get("/")
async def root():
    """Serves the index.html"""
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

# Commented out session-based endpoint since we're using simple chat
# @app.post("/send/{user_id}")
# async def send_message_endpoint(user_id: str, request: Request):
#     """HTTP endpoint for client to agent communication"""
#     pass


# New: Endpoint to accept uploaded recorded audio (no SSE/live required)
@app.post("/transcribe_audio")
async def transcribe_audio_endpoint(audio_file: UploadFile = File(...)):
    """Accepts a recorded audio file, transcribes it via Gemini, and returns the text."""

    # Save to a temporary file
    try:
        # Preserve original extension when saving to temp for better type inference
        orig_suffix = Path(audio_file.filename).suffix or ".webm"
        with tempfile.NamedTemporaryFile(delete=False, suffix=orig_suffix) as tmp:
            content = await audio_file.read()
            tmp.write(content)
            tmp_path = tmp.name

        # Use tools.transcribe_audio_file to get transcription
        transcription = tools.transcribe_audio_file(tmp_path)

        # Clean up temp file
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

        if isinstance(transcription, str) and transcription.startswith("Error:"):
            return JSONResponse({"success": False, "message": transcription}, status_code=500)

        return {"success": True, "transcription": transcription, "filename": audio_file.filename}

    except Exception as e:
        return JSONResponse({"success": False, "message": str(e)}, status_code=500)


# New: Enhanced chat endpoint with conversation context and information extraction
@app.post("/chat")
async def chat_endpoint(request: Request):
    global conversation_history, extracted_info
    
    body = await request.json()
    user_text = body.get("message", "").strip()
    if not user_text:
        return JSONResponse({"error": "Empty message"}, status_code=400)

    try:
        # Add user message to conversation history
        conversation_history.append({"role": "user", "content": user_text})
        
        client = genai.Client()
        
        # Build conversation context
        system_prompt = (
            "You are 'Saathi', a helpful, empathetic Digital FIR Assistant for Indian Police. "
            "Your role is to guide users step-by-step to collect all required information for filing an FIR. "
            "Be conversational, empathetic, and ask for missing information systematically. "
            "Format your responses using markdown for better readability - use **bold** for important points, "
            "- bullet points for lists, and proper spacing for clarity. "
            "Required information: complainant name, address, phone, incident date/time, location, "
            "nature of complaint, and detailed description."
        )
        
        # Prepare conversation for the model
        messages = [{"role": "user", "parts": [{"text": system_prompt}]}]
        
        # Add conversation history
        for msg in conversation_history[-10:]:  # Keep last 10 messages for context
            messages.append({"role": "user" if msg["role"] == "user" else "model", 
                           "parts": [{"text": msg["content"]}]})
        
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=messages,
        )
        
        response_text = getattr(resp, "text", "")
        
        # Add assistant response to conversation history
        conversation_history.append({"role": "assistant", "content": response_text})
        
        # Extract information from the conversation
        extracted_data = await extract_information_from_conversation()
        
        return {
            "text": response_text,
            "extracted_info": extracted_data
        }
        
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# Information extraction function
async def extract_information_from_conversation():
    """Extract structured information from conversation history."""
    global conversation_history, extracted_info
    
    try:
        # Get recent conversation context
        recent_conversation = conversation_history[-5:] if len(conversation_history) > 5 else conversation_history
        conversation_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in recent_conversation])
        
        client = genai.Client()
        extraction_prompt = f"""
        Based on the following conversation, extract FIR information and return it as JSON. 
        Only include fields that are clearly mentioned. Use null for missing information.
        
        Conversation:
        {conversation_text}
        
        Extract and return JSON with these fields:
        {{
            "complainant_name": "full name if mentioned",
            "complainant_address": "address if mentioned", 
            "complainant_phone": "phone number if mentioned",
            "incident_date": "date/time if mentioned (in YYYY-MM-DDTHH:MM format)",
            "incident_location": "location if mentioned",
            "nature_of_complaint": "type of complaint if mentioned",
            "incident_description": "detailed description if mentioned",
            "accused_details": "accused person details if mentioned",
            "witnesses": "witness information if mentioned",
            "property_loss": "property loss details if mentioned",
            "evidence_description": "evidence details if mentioned"
        }}
        
        Return only valid JSON, no other text.
        """
        
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[{"role": "user", "parts": [{"text": extraction_prompt}]}],
        )
        
        response_text = getattr(resp, "text", "").strip()
        
        # Clean up response to get just JSON
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        response_text = response_text.strip()
        
        try:
            extracted_data = json.loads(response_text)
            # Update global extracted_info with non-null values
            for key, value in extracted_data.items():
                if value and value != "null" and str(value).strip():
                    extracted_info[key] = value
            return extracted_info
        except json.JSONDecodeError:
            print(f"Failed to parse extracted JSON: {response_text}")
            return extracted_info
            
    except Exception as e:
        print(f"Error in information extraction: {e}")
        return extracted_info


# Get current extracted information
@app.get("/get_extracted_info")
async def get_extracted_info():
    """Returns currently extracted information for form auto-fill."""
    global extracted_info
    return {"extracted_info": extracted_info}


# New: FIR submission endpoint
@app.post("/submit_fir")
async def submit_fir_endpoint(request: Request):
    """Accepts FIR form data and uploads it to GCP storage."""
    try:
        fir_data = await request.json()
        
        # Validate required fields
        required_fields = [
            "complainant_name", "complainant_address", "complainant_phone",
            "incident_date", "incident_location", "incident_description", "nature_of_complaint"
        ]
        
        missing_fields = []
        for field in required_fields:
            if not fir_data.get(field, "").strip():
                missing_fields.append(field)
        
        if missing_fields:
            return JSONResponse(
                {"success": False, "message": f"Missing required fields: {', '.join(missing_fields)}"},
                status_code=400
            )
        
        # Upload to GCP
        upload_result = tools.upload_fir_to_gcp(fir_data)
        
        if upload_result.startswith("Success:"):
            return {"success": True, "message": upload_result}
        else:
            return JSONResponse({"success": False, "message": upload_result}, status_code=500)
            
    except Exception as e:
        return JSONResponse({"success": False, "message": str(e)}, status_code=500)