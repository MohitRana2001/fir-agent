import os
import google.generativeai as genai
from google.generativeai.types import GenerateContentConfig
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_cors import CORS

# Load environment variables from a .env file
load_dotenv()

# --- Gemini API Configuration ---
# Make sure your GOOGLE_API_KEY is set in your .env file
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# --- Flask App Initialization ---
app = Flask(__name__)
# Enable Cross-Origin Resource Sharing (CORS) to allow browser requests
CORS(app)

@app.route('/transcribe', methods=['POST'])
def transcribe_audio():
    """
    Receives an audio file, sends it to Gemini for transcription,
    and returns the result.
    """
    # 1. Check if an audio file was sent
    if 'audio_file' not in request.files:
        return jsonify({"error": "No audio file provided"}), 400
    
    audio_file = request.files['audio_file']
    
    # 2. Upload the local file to the Gemini API
    # This is the key step: uploading the file from your server's memory/disk
    # The API will automatically detect the MIME type, but you can specify it.
    print(f"Uploading file: {audio_file.filename}...")
    gemini_file = genai.upload_file(
        path=audio_file,
        display_name="My Recorded Audio"
    )
    print(f"Completed upload: {gemini_file.name}")

    # 3. Generate content using the uploaded file
    model = genai.GenerativeModel(model_name="models/gemini-1.5-flash")
    
    prompt = """
    Transcribe the interview, in the format of timecode, speaker, caption.
    Use speaker A, speaker B, etc. to identify speakers.
    """
    
    # Pass the uploaded file to the model
    response = model.generate_content(
        [prompt, gemini_file],
        # Required to enable timestamp understanding for audio-only files
        generation_config=GenerateContentConfig(temperature=0),
    )

    # 4. Clean up the uploaded file from the Gemini server after use
    print(f"Deleting uploaded file: {gemini_file.name}")
    genai.delete_file(gemini_file.name)
    
    # 5. Return the transcription text in a JSON response
    return jsonify({"transcription": response.text})

if __name__ == '__main__':
    # Run the Flask app on localhost, port 5000
    app.run(debug=True, port=5000)