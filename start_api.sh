#!/bin/bash

# Rx-AI API Startup Script

echo "🚀 Starting Rx-AI Questionnaire API..."
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  Warning: .env file not found!"
    echo "Create a .env file (copy from .env.example) and set your GCP details:"
    echo "GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/service-account.json"
    echo "GOOGLE_CLOUD_PROJECT=your-gcp-project-id"
    echo "GOOGLE_CLOUD_LOCATION=us-central1"
    echo ""
    exit 1
fi

# Environment name
ENV_NAME="rx-ai"

# Check if conda environment exists
if ! conda env list | grep -q "^${ENV_NAME} "; then
    echo "📦 Creating conda environment: ${ENV_NAME}"
    conda create -n ${ENV_NAME} python=3.11 -y
fi

# Activate conda environment
echo "🔧 Activating conda environment: ${ENV_NAME}"
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate ${ENV_NAME}

# Install/update dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

# Start the API
echo ""
echo "✅ Starting API server on http://localhost:8000"
echo "   Press Ctrl+C to stop"
echo ""
python api.py

