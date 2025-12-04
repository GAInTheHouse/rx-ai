#!/bin/bash

# One-time setup script for Rx-AI API with Conda

echo "📦 Setting up Rx-AI API with Conda..."
echo ""

# Environment name
ENV_NAME="rx-ai"

# Check if conda is installed
if ! command -v conda &> /dev/null; then
    echo "❌ Conda is not installed!"
    echo "Please install Miniconda or Anaconda first:"
    echo "https://docs.conda.io/en/latest/miniconda.html"
    exit 1
fi

# Create conda environment
echo "🔧 Creating conda environment: ${ENV_NAME} with Python 3.11..."
conda create -n ${ENV_NAME} python=3.11 -y

# Activate environment
echo "✅ Activating environment..."
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate ${ENV_NAME}

# Install dependencies
echo "📥 Installing Python packages from requirements.txt..."
pip install -r requirements.txt

# Check for .env file
echo ""
if [ ! -f .env ]; then
    echo "⚠️  Creating .env file template..."
    echo "OPENAI_API_KEY=your_openai_api_key_here" > .env
    echo "✏️  Please edit .env and add your OpenAI API key"
else
    echo "✅ .env file already exists"
fi

echo ""
echo "🎉 Setup complete!"
echo ""
echo "To start the API server:"
echo "  ./start_api.sh"
echo ""
echo "Or manually:"
echo "  conda activate ${ENV_NAME}"
echo "  python api.py"
echo ""

