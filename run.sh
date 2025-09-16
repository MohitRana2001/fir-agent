#!/bin/bash
# Script to run the Saathi FIR Agent application

# Activate virtual environment
source venv/bin/activate

# Run the application with uvicorn
uvicorn main:app --reload --host 0.0.0.0 --port 8000

echo "Saathi FIR Agent is running at http://localhost:8000"
