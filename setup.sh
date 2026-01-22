#!/bin/bash
# Setup Script for Job Application Agents

set -e

echo "=============================================="
echo "  Setting up Job Application Agents"
echo "=============================================="

cd "$(dirname "$0")"

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Create directories
echo "Creating directories..."
mkdir -p data/jobs
mkdir -p data/user
mkdir -p data/processed
mkdir -p logs
mkdir -p config

# Copy example files if they don't exist
if [ ! -f ".env" ]; then
    echo "Creating .env file..."
    cp .env.example .env
fi

echo ""
echo "=============================================="
echo "  Setup Complete!"
echo "=============================================="
echo ""
echo "Next steps:"
echo "1. Edit config/config.yaml with your settings"
echo "2. Edit config/user_profile.yaml with your profile"
echo "3. Add your Gmail credentials to config/gmail_credentials.json"
echo "4. Edit data/user/motivations.md and data/user/experience.md"
echo "5. Run: ./start.sh"
echo ""
