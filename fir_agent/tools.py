import json
import os
import textract
from google.cloud import speech
from google.api_core import exceptions as google_exceptions
from google.genai.types import Blob

# This function is completely replaced to support .doc, .docx, and .pdf
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
        # textract handles various file types automatically
        text_bytes = textract.process(file_path)
        # Decode bytes to a UTF-8 string, ignoring errors
        text = text_bytes.decode('utf-8', errors='ignore')
        if not text.strip():
            return "Error: Could not extract any text from the document. It might be empty or an image-based file."
        return text
    except textract.exceptions.ExtensionNotSupported:
        return "Error: Unsupported file type. Please upload a PDF, DOCX, or DOC file."
    except Exception as e:
        return f"Error parsing document: {e}"

# This function is updated with better error handling
def parse_speech(audio_data: Blob) -> str:
    """
    Transcribes audio data to text using Google Cloud Speech-to-Text.
    NOTE: Ensure your environment is authenticated with Google Cloud.
    Set the GOOGLE_APPLICATION_CREDENTIALS environment variable.

    Args:
        audio_data (Blob): The audio blob to transcribe.

    Returns:
        str: The transcribed text.
    """
    try:
        client = speech.SpeechClient()
        audio = speech.RecognitionAudio(content=audio_data.data)
        # The sample rate must match the audio recorded on the client-side (16000Hz)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
            language_code="en-US",
        )
        response = client.recognize(config=config, audio=audio)
        if response.results:
            return response.results[0].alternatives[0].transcript
        else:
            # This can happen if the audio is silent or unintelligible
            return ""
    except google_exceptions.PermissionDenied as e:
        print(f"GCP PERMISSION DENIED: {e}")
        return "Error: Speech recognition permission denied. Check API key and credentials."
    except google_exceptions.InvalidArgument as e:
        print(f"GCP INVALID ARGUMENT: {e}")
        return "Error: Invalid audio data sent for speech recognition."
    except Exception as e:
        print(f"SPEECH RECOGNITION ERROR: {e}")
        return f"Error during speech recognition: {e}"

# (validate_data function remains unchanged)
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
        return "All required information has been provided. The FIR can be filed."
    else:
        return f"The following information is missing: {', '.join(missing_fields)}"