import json
import os
import time
from pathlib import Path
from google import genai
from google.genai.types import GenerateContentConfig
from dotenv import load_dotenv
from PyPDF2 import PdfReader
import docx
from google.cloud import storage
import uuid
from datetime import datetime

load_dotenv()

def parse_document(file_path: str) -> str:
    """Parses a document (PDF or DOCX) and returns the text content without textract."""
    if not os.path.exists(file_path):
        return f"Error: File not found at {file_path}"

    try:
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".pdf":
            text_parts = []
            with open(file_path, "rb") as f:
                reader = PdfReader(f)
                for page in reader.pages:
                    page_text = page.extract_text() or ""
                    if page_text:
                        text_parts.append(page_text)
            text = "\n".join(text_parts).strip()
            if not text:
                return "Error: Could not extract any text from the PDF. It might be scanned images."
            return text
        elif ext == ".docx":
            document = docx.Document(file_path)
            text = "\n".join(p.text for p in document.paragraphs).strip()
            if not text:
                return "Error: Could not extract any text from the DOCX."
            return text
        else:
            return "Error: Unsupported file type. Please upload a PDF or DOCX file."
    except Exception as e:
        return f"Error parsing document: {e}"

def transcribe_audio_file(file_path: str) -> str:
    """Transcribes an audio file and returns the text using Gemini file upload API."""
    try:
        client = genai.Client(api_key=os.getenv('GOOGLE_API_KEY'))
        print(f"Transcribing audio file: {file_path}")

        uploaded_file = client.files.upload(file=Path(file_path))
        print(f"Uploaded file '{uploaded_file.display_name}' as: {uploaded_file.name}")

        print("Waiting for file to be processed...")
        while uploaded_file.state.name == "PROCESSING":
            time.sleep(2)
            uploaded_file = client.files.get(name=uploaded_file.name)

        if uploaded_file.state.name == "FAILED":
            print(f"File processing failed: {uploaded_file.state}")
            return f"Error: File processing failed on the server."

        if uploaded_file.state.name != "ACTIVE":
            print(f"File is not active: {uploaded_file.state}")
            return f"Error: File could not be processed. State: {uploaded_file.state.name}"

        prompt = (
            "This audio contains an interview between an Investigating Officer (IO) and a complainant for a "
            "First Information Report (FIR). Your task is to provide a precise, verbatim transcription. "
            "Differentiate between the speakers by starting each line with either 'Investigating Officer:' or 'Complainant:'. "
            "The conversation may be multilingual; transcribe all speech accurately."
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[prompt, uploaded_file],
        )

        try:
            client.files.delete(name=uploaded_file.name)
        except Exception:
            pass

        print("Transcription successful.")
        return response.text
    except Exception as e:
        print(f"Error during transcription: {e}")
        return f"Error: {e}"

def validate_data(
    complainant_name: str = "",
    complainant_address: str = "",
    complainant_phone: str = "",
    incident_date: str = "",
    incident_location: str = "",
    incident_description: str = "",
    nature_of_complaint: str = "",
) -> str:
    """
    Validates the user-provided details against the FIR template.
    """
    try:
        with open("fir_template.json") as f:
            template = json.load(f)
    except FileNotFoundError:
        return "Error: fir_template.json not found."
    
    required_fields = template.get("required_fields", {})
    missing_fields = []

    user_details = {
        "complainant_name": complainant_name,
        "complainant_address": complainant_address,
        "complainant_phone": complainant_phone,
        "incident_date": incident_date,
        "incident_location": incident_location,
        "incident_description": incident_description,
        "nature_of_complaint": nature_of_complaint,
    }

    for field in required_fields:
        if not user_details.get(field):
            missing_fields.append(field)

    if not missing_fields:
        return "All required information has been provided."
    else:
        return f"The following information is missing: {', '.join(missing_fields)}"

def upload_fir_to_gcp(fir_data: dict) -> str:
    """Uploads FIR data to Google Cloud Storage bucket."""
    try:
        client = storage.Client()
        bucket_name = os.getenv('GCP_BUCKET_NAME', 'fir-submissions')
        bucket = client.bucket(bucket_name)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        fir_id = str(uuid.uuid4())[:8]
        filename = f"fir_{timestamp}_{fir_id}.json"
        
        fir_data['submission_id'] = fir_id
        fir_data['submitted_at'] = datetime.now().isoformat()
        fir_data['status'] = 'submitted'
        
        blob = bucket.blob(filename)
        blob.upload_from_string(
            json.dumps(fir_data, indent=2),
            content_type='application/json'
        )
        
        print(f"FIR uploaded successfully: {filename}")
        return f"Success: FIR uploaded with ID {fir_id}"
        
    except Exception as e:
        print(f"Error uploading to GCP: {e}")
        return f"Error: Failed to upload FIR - {str(e)}"
