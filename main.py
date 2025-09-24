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
        with open("fir_template.json", "r") as f:
            fir_template_str = f.read()
            
        combined_input_for_ai = (
            f"Current FIR Data: {json.dumps(extracted_info)}\n"
            f"User Message: \"{user_text}\""
        )

        conversation_history.append({"role": "user", "content": combined_input_for_ai})
        
        client = genai.Client()
        system_prompt = (
            f"""
            ## Persona and Role:
            You are an AI Assistant for Indian Police Investigating Officers (IOs), designated as the 'FIR Drafting Assistant'. Your purpose is to efficiently and accurately fill out a First Information Report (FIR) JSON object based on the user's input.

            ## Core Workflow:
            1.  **Maintain State**: You are a stateful assistant. In every turn, you will be given the current state of the FIR data as a JSON object. Your primary job is to UPDATE this JSON with any new information found in the user's latest message. DO NOT forget or overwrite existing data unless the user explicitly corrects it.
            2.  **Extract Information**: Analyze the user's text to find details that match the fields in the provided JSON structure. You must be able to handle mixed languages (e.g., Hindi-English).
            3.  **Ask for Missing Required Fields**: After extraction, if any of the `required_fields` in the JSON are still `null`, you MUST ask the user for the missing information in a clear, bulleted list.
            4.  **Output Format**: Your response MUST be in two parts, separated by '---JSON---'.
                - Part 1: Your conversational text to the user (e.g., asking for missing info).
                - Part 2: The COMPLETE and UPDATED JSON object.

            ## Example Interaction:

            **User provides current data and a new message:**
            '''
            Current FIR Data: {{"district": null, "policeStation": null, "complainantName": "Rohan Sharma"}}
            User Message: "The incident happened in the district of Gurugram at the Cyber City police station."
            '''

            **Your Correct Output:**
            '''
            Thank you. I have updated the district and police station. To proceed, please provide the following required details:
            * firYear
            * firNo
            * firDate
            * complainantAddress
            * firContents
            ---JSON---
            {{
                "required_fields": {{
                    "district": "Gurugram",
                    "policeStation": "Cyber City",
                    "firYear": null,
                    "firNo": null,
                    "firDate": null,
                    "complainantName": "Rohan Sharma",
                    "complainantAddress": null,
                    "firContents": null
                }},
                "optional_fields": {{}}
            }}
            '''

            ## Final JSON Structure to be filled:
            Your final goal is to fill out this exact JSON structure. Do not add or remove keys.
            {fir_template_str}
            """
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
                nested_data = json.loads(json_string)
                flat_data = {}
                if 'required_fields' in nested_data and nested_data['required_fields']:
                    flat_data.update(nested_data['required_fields'])
                if 'optional_fields' in nested_data and nested_data['optional_fields']:
                    flat_data.update(nested_data['optional_fields'])

                for key, value in flat_data.items():
                    if value and value != "null" and str(value).strip():
                        extracted_info[key] = value

            except json.JSONDecodeError as e:
                print(f"Failed to parse or process extracted JSON: {e}")
                print(f"Problematic JSON string: {json_string}")
        
        conversation_history.append({"role": "assistant", "content": response_text})
        
        return {
            "text": response_text,
            "extracted_info": extracted_info 
        }
        
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

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
    #     required_fields = [
    #         "complainant_name", "complainant_address", "complainant_phone",
    #         "incident_date", "incident_location", "incident_description", "nature_of_complaint"
    #     ]
        
    #     missing_fields = []
    #     for field in required_fields:
    #         if not fir_data.get(field, "").strip():
    #             missing_fields.append(field)
        
    #     if missing_fields:
    #         return JSONResponse(
    #             {"success": False, "message": f"Missing required fields: {', '.join(missing_fields)}"},
    #             status_code=400
    #         )
        
        # Upload to GCP
        upload_result = tools.upload_fir_to_gcp(fir_data)
        
        if upload_result.startswith("Success:"):
            return {"success": True, "message": upload_result}
        else:
            return JSONResponse({"success": False, "message": upload_result}, status_code=500)
            
    except Exception as e:
        return JSONResponse({"success": False, "message": str(e)}, status_code=500)