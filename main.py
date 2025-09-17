import os
import json
import base64
import warnings
import asyncio
import shutil

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


# CHANGED: This function now also creates a client-facing queue for transcriptions
async def start_agent_session(user_id, is_audio=False):
    """Starts an agent session"""

    # Create a Runner
    runner = InMemoryRunner(
        app_name=APP_NAME,
        agent=root_agent,
    )

    # Create a Session
    session = await runner.session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
    )

    # Set response modality
    modality = "AUDIO" if is_audio else "TEXT"
    run_config = RunConfig(
        response_modalities=[modality],
        session_resumption=types.SessionResumptionConfig()
    )

    # Create a LiveRequestQueue for this session
    live_request_queue = LiveRequestQueue()

    # Start agent session
    live_events = runner.run_live(
        session=session,
        live_request_queue=live_request_queue,
        run_config=run_config,
    )
    # CHANGED: Return all three objects
    return live_events, live_request_queue


async def agent_to_client_sse(live_events):
    """Agent to client communication via SSE"""
    async for event in live_events:
        if event.turn_complete or event.interrupted:
            message = {
                "turn_complete": event.turn_complete,
                "interrupted": event.interrupted,
            }
            yield f"data: {json.dumps(message)}\n\n"
            print(f"[AGENT TO CLIENT]: {message}")
            continue

        part: Part = (
            event.content and event.content.parts and event.content.parts[0]
        )
        if not part:
            continue

        is_audio = part.inline_data and part.inline_data.mime_type.startswith("audio/pcm")
        if is_audio:
            audio_data = part.inline_data and part.inline_data.data
            if audio_data:
                message = {
                    "mime_type": "audio/pcm",
                    "data": base64.b64encode(audio_data).decode("ascii")
                }
                yield f"data: {json.dumps(message)}\n\n"
                print(f"[AGENT TO CLIENT]: audio/pcm: {len(audio_data)} bytes.")
                continue

        if part.text and event.partial:
            message = {
                "mime_type": "text/plain",
                "data": part.text
            }
            yield f"data: {json.dumps(message)}\n\n"
            print(f"[AGENT TO CLIENT]: text/plain: {message}")


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

# CHANGED: This endpoint now handles file uploads for a specific session
@app.post("/upload/{user_id}")
async def upload_file(user_id: str, file: UploadFile = File(...)):
    """Uploads a file, parses it, and sends the content to the agent."""
    if user_id not in active_sessions:
        return {"success": False, "message": "Session not found"}, 404

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
        
        # Send the extracted text to the agent
        prompt = f"The user has uploaded a document with the following content: {parsed_text}"
        content = Content(role="user", parts=[Part.from_text(text=prompt)])
        
        session_data = active_sessions[user_id]
        agent_queue = session_data["agent_queue"]
        agent_queue.send_content(content=content)
        
        print(f"[CLIENT TO AGENT]: Sent parsed content from {file.filename}")
        return {"success": True}

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


# CHANGED: This endpoint now manages the merged stream of agent and transcription events
@app.get("/events/{user_id}")
async def sse_endpoint(user_id: str, is_audio: str = "false"):
    """SSE endpoint for all client-facing communication"""

    # Start agent session
    live_events, agent_queue = await start_agent_session(user_id, is_audio == "true")

    # Store the queues for this user
    active_sessions[user_id] = {
        "agent_queue": agent_queue
    }

    print(f"Client #{user_id} connected via SSE, audio mode: {is_audio}")

    def cleanup():
        agent_queue.close()
        if user_id in active_sessions:
            del active_sessions[user_id]
        print(f"Client #{user_id} disconnected from SSE")

    async def event_generator():
        try:
            # Merge agent events and transcription events into a single stream
            agent_stream = agent_to_client_sse(live_events)
            async for data in agent_stream:
                yield data
        except Exception as e:
            print(f"Error in SSE stream: {e}")
        finally:
            cleanup()

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


# CHANGED: This endpoint now also handles speech-to-text transcription
@app.post("/send/{user_id}")
async def send_message_endpoint(user_id: str, request: Request):
    """HTTP endpoint for client to agent communication"""

    if user_id not in active_sessions:
        return {"error": "Session not found"}, 404
    
    session_data = active_sessions[user_id]
    agent_queue = session_data["agent_queue"]

    message = await request.json()
    mime_type = message["mime_type"]
    data = message["data"]

    if mime_type == "text/plain":
        content = Content(role="user", parts=[Part.from_text(text=data)])
        agent_queue.send_content(content=content)
        print(f"[CLIENT TO AGENT]: {data}")
    elif mime_type == "audio/pcm":
        decoded_data = base64.b64decode(data)
        agent_queue.send_realtime(Blob(data=decoded_data, mime_type=mime_type))
        print(f"[CLIENT TO AGENT]: audio/pcm: {len(decoded_data)} bytes")
    else:
        return {"error": f"Mime type not supported: {mime_type}"}

    return {"status": "sent"}