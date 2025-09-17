import json
import os
import textract
from google import genai
from google.genai.types import GenerateContentConfig, Part
from dotenv import load_dotenv

load_dotenv()

def parse_document(file_path: str) -> str:
    """
    Parses a document (PDF, DOCX, DOC) and returns the text content.

    Args:
        file_path (str): The path to the document file.

    Returns:
        str: The text content of the document.
    """
    if not os.path.exists(file_path):
        return f"Error: File not found at {file_path}"

    try:
        text_bytes = textract.process(file_path)
        text = text_bytes.decode('utf-8', errors='ignore')
        if not text.strip():
            return "Error: Could not extract any text from the document. It might be empty or an image-based file."
        return text
    except textract.exceptions.ExtensionNotSupported:
        return "Error: Unsupported file type. Please upload a PDF, DOCX, or DOC file."
    except Exception as e:
        return f"Error parsing document: {e}"

def transcribe_audio_file(file_path: str) -> str:
    """Transcribes an audio file and returns the text."""
    try:
        client = genai.Client()
        print(f"Transcribing audio file: {file_path}")

        with open(file_path, "rb") as f:
            audio_bytes = f.read()

        audio_file_part = Part.from_data(data=audio_bytes, mime_type="audio/pcm")

        prompt = "Transcribe this audio recording of a complainant giving a statement for a First Information Report (FIR)."

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                prompt,
                audio_file_part,
            ],
        )
        
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
