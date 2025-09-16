
import json
from google.cloud import speech
import docx
import PyPDF2
import os

def parse_document(file_path: str) -> str:
    """
    Parses a document (PDF or DOCX) and returns the text content.

    Args:
        file_path (str): The path to the document file.

    Returns:
        str: The text content of the document.
    """
    if not os.path.exists(file_path):
        return f"Error: File not found at {file_path}"

    try:
        if file_path.endswith(".pdf"):
            with open(file_path, "rb") as f:
                pdf_reader = PyPDF2.PdfReader(f)
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text()
                return text
        elif file_path.endswith(".docx"):
            doc = docx.Document(file_path)
            return "\n".join([paragraph.text for paragraph in doc.paragraphs])
        else:
            return "Error: Unsupported file type. Please upload a PDF or DOCX file."
    except Exception as e:
        return f"Error parsing document: {e}"

def parse_speech(audio_data: bytes) -> str:
    """
    Transcribes audio data to text using Google Cloud Speech-to-Text.

    Args:
        audio_data (bytes): The audio data to transcribe.

    Returns:
        str: The transcribed text.
    """
    try:
        client = speech.SpeechClient()
        audio = speech.RecognitionAudio(content=audio_data)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
            language_code="en-US",
        )
        response = client.recognize(config=config, audio=audio)
        if response.results:
            return response.results[0].alternatives[0].transcript
        else:
            return "Could not transcribe audio."
    except Exception as e:
        return f"Error during speech recognition: {e}"

def validate_data(
    complainant_name: str,
    complainant_address: str,
    complainant_phone: str,
    incident_date: str,
    incident_location: str,
    incident_description: str,
    nature_of_complaint: str,
) -> str:
    """
    Validates the user-provided details against the FIR template.

    Args:
        complainant_name (str): Full name of the person filing the complaint.
        complainant_address (str): Complete address of the complainant.
        complainant_phone (str): Contact phone number of the complainant.
        incident_date (str): Date and time when the incident occurred.
        incident_location (str): Exact location where the incident took place.
        incident_description (str): Detailed description of the incident.
        nature_of_complaint (str): Type of complaint (theft, assault, fraud, etc.).

    Returns:
        str: A message indicating if the data is valid or what fields are missing.
    """
    with open("fir_template.json") as f:
        template = json.load(f)
    
    required_fields = template["required_fields"]
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

    for field, details in required_fields.items():
        if not user_details.get(field):
            missing_fields.append(field)

    if not missing_fields:
        return "All required information has been provided. The FIR can be filed."
    else:
        return f"The following information is missing: {', '.join(missing_fields)}"
