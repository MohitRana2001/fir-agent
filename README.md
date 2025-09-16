# Saathi - Digital FIR Assistant

A beautiful, modern web application for filing First Information Reports (FIR) using Google's Gemini AI agent.

## 🚀 Features

- **Modern UI**: Clean, responsive design with white/black/blue color scheme
- **Voice Support**: Real-time audio recording and transcription
- **File Upload**: Support for PDF and DOCX document parsing
- **Multi-language**: Adaptive language detection and response
- **Real-time Chat**: Server-Sent Events for instant communication

## 📋 Prerequisites

- Python 3.12+
- Google Gemini API Key
- Virtual environment (included)

## 🔧 Setup Instructions

### 1. Google API Key Setup

1. Visit [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Create or log in to your Google account
3. Generate a new API key
4. Copy the API key

### 2. Environment Configuration

Create a `.env` file in the project root:

```bash
# In the project directory
touch .env
```

Add your API key to the `.env` file:

```env
GOOGLE_API_KEY=your_actual_google_gemini_api_key_here
```

### 3. Run the Application

Use the convenient run script:

```bash
chmod +x run.sh
./run.sh
```

Or manually:

```bash
source venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 4. Access the Application

Open your browser and navigate to:

```
http://localhost:8000
```

## 🎯 Usage

1. **Text Chat**: Type messages in the input field and press Enter or click Send
2. **Voice Chat**: Click "Start Audio" to begin voice recording, "Stop Audio" to end
3. **File Upload**: Click the paperclip icon to upload PDF or DOCX documents
4. **Connection Status**: Monitor the connection indicator in the header

## 🔍 Troubleshooting

### Connection Issues

If you see "Connecting..." that never resolves:

1. **Check API Key**: Ensure `GOOGLE_API_KEY` is set in your `.env` file
2. **Verify Key**: Test your API key at [Google AI Studio](https://makersuite.google.com/app/apikey)
3. **Check Logs**: Look at the terminal output for error messages

### Common Error Messages

- `GOOGLE_API_KEY environment variable is not set`: Create `.env` file with your API key
- `Agent initialization timed out`: Usually indicates invalid or missing API key
- `Session not found`: The user session has expired, refresh the page

## 🏗️ Architecture

- **Backend**: FastAPI with Google ADK (Agent Development Kit)
- **Frontend**: Vanilla JavaScript with Lucide icons
- **AI Agent**: Google Gemini 2.0 Flash Experimental
- **Communication**: Server-Sent Events (SSE) for real-time updates

## 📁 Project Structure

```
fir-agent/
├── fir_agent/
│   ├── agent.py          # Agent configuration
│   └── tools.py          # Document parsing and validation tools
├── static/
│   ├── css/styles.css    # Modern UI styles
│   ├── js/app.js         # Frontend application logic
│   └── index.html        # Main HTML page
├── main.py               # FastAPI application
├── run.sh                # Convenient run script
└── requirements.txt      # Python dependencies
```

## 🤝 Support

If you encounter any issues:

1. Check the browser console for JavaScript errors
2. Review the terminal output for server errors
3. Ensure your Google API key has sufficient quota
4. Verify all dependencies are installed correctly

## 🎨 UI Features

- **Responsive Design**: Works on desktop, tablet, and mobile
- **Dark/Light Theme**: Automatic adaptation based on system preferences
- **Accessibility**: Screen reader support and keyboard navigation
- **Modern Icons**: Lucide React icons throughout the interface
- **Smooth Animations**: Subtle transitions and hover effects
