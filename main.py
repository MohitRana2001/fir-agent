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

from fir_agent import tools
from fir_agent.agent import root_agent

warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

load_dotenv()
APP_NAME = "FIR Agent"
UPLOADS_DIR = Path("uploads")
UPLOADS_DIR.mkdir(exist_ok=True)
async def client_queue_sse(client_queue: asyncio.Queue):
    """Yields messages from the client-facing queue."""
    while True:
        message = await client_queue.get()
        yield f"data: {json.dumps(message)}\n\n"
        print(f"[TRANSCRIPTION TO CLIENT]: {message}")


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
                if task is task1:
                    task1 = asyncio.create_task(stream1.__anext__())
                else:
                    task2 = asyncio.create_task(stream2.__anext__())
            except StopAsyncIteration:
                if task is task1:
                    task1 = None
                else:
                    task2 = None
        
        if not task1 and not task2:
            break
        elif not task1:
            yield await task2
            async for item in stream2: yield item
            break
        elif not task2:
            yield await task1
            async for item in stream1: yield item
            break

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

conversation_history = []
extracted_info = {}

@app.post("/upload/{user_id}")
async def upload_file(user_id: str, file: UploadFile = File(...)):
    """Uploads a file, parses it, and sends the content to the agent."""

    file_path = UPLOADS_DIR / file.filename
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        print(f"Parsing document: {file_path}")
        parsed_text = tools.parse_document(str(file_path))

        if parsed_text.startswith("Error:"):
            print(f"Failed to parse document: {parsed_text}")
            return {"success": False, "message": parsed_text}, 400
        
        document_message = f"I have uploaded a document ({file.filename}). Here is the content: {parsed_text}"
        conversation_history.append({"role": "user", "content": document_message})
        
        print(f"[CLIENT TO AGENT]: Parsed content from {file.filename}")
        return {"success": True, "parsed_content": parsed_text}

    except Exception as e:
        return {"success": False, "message": str(e)}, 500
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


@app.get("/")
async def root():
    """Serves the index.html"""
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

@app.post("/transcribe_audio")
async def transcribe_audio_endpoint(audio_file: UploadFile = File(...)):
    """Accepts a recorded audio file, transcribes it via Gemini, and returns the text."""

    try:
        orig_suffix = Path(audio_file.filename).suffix or ".webm"
        with tempfile.NamedTemporaryFile(delete=False, suffix=orig_suffix) as tmp:
            content = await audio_file.read()
            tmp.write(content)
            tmp_path = tmp.name

        transcription = tools.transcribe_audio_file(tmp_path)

        try:
            os.unlink(tmp_path)
        except Exception:
            pass

        if isinstance(transcription, str) and transcription.startswith("Error:"):
            return JSONResponse({"success": False, "message": transcription}, status_code=500)

        return {"success": True, "transcription": transcription, "filename": audio_file.filename}

    except Exception as e:
        return JSONResponse({"success": False, "message": str(e)}, status_code=500)

@app.post("/chat")
async def chat_endpoint(request: Request):
    global conversation_history, extracted_info
    
    body = await request.json()
    user_text = body.get("message", "").strip()
    if not user_text:
        return JSONResponse({"error": "Empty message"}, status_code=400)

    try:
        conversation_history.append({"role": "user", "content": user_text})
        
        client = genai.Client()
        system_prompt = (
            "You are 'Saathi', a helpful, empathetic Digital FIR Assistant for Indian Police. "
            "Your role is to guide users step-by-step to collect all required information for filing an FIR. "
            "Be conversational, empathetic, and ask for missing information systematically. "
            "Format your responses using markdown for better readability. "
            "After your conversational response, you MUST include a separator '---JSON---' followed by a valid JSON object "
            "containing the information you have gathered from the conversation so far. "
            "The JSON object should have the following fields: "
            "complainant_name, complainant_address, complainant_phone, incident_date, incident_location, "
            "nature_of_complaint, incident_description, accused_details, witnesses, property_loss, evidence_description. "
            "If a value is not yet known, use null."
        )
        
        messages = [{"role": "user", "parts": [{"text": system_prompt}]}]
        
        for msg in conversation_history[-10:]: 
            messages.append({"role": "user" if msg["role"] == "user" else "model", "parts": [{"text": msg["content"]}]})
        
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=messages,
        )
        
        full_response_text = getattr(resp, "text", "")
        
        response_parts = full_response_text.split("---JSON---")
        response_text = response_parts[0].strip()
        
        if len(response_parts) > 1:
            json_string = response_parts[1].strip()
            try:
                if json_string.startswith("```json"):
                    json_string = json_string[7:]
                if json_string.endswith("```"):
                    json_string = json_string[:-3]
                json_string = json_string.strip()
                
                extracted_data = json.loads(json_string)
                for key, value in extracted_data.items():
                    if value and value != "null" and str(value).strip():
                        extracted_info[key] = value
            except json.JSONDecodeError:
                print(f"Failed to parse extracted JSON: {json_string}")
        
        conversation_history.append({"role": "assistant", "content": response_text})
        
        return {
            "text": response_text,
            "extracted_info": extracted_info 
        }
        
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# Get current extracted information
@app.get("/get_extracted_info")
async def get_extracted_info():
    """Returns currently extracted information for form auto-fill."""
    global extracted_info
    return {"extracted_info": extracted_info}

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