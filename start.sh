#!/bin/bash
# Start Script for Job Application Agents
# This script runs the full pipeline sequentially

set -e

echo "=============================================="
echo "  Job Application Multi-Agent System"
echo "=============================================="

# Change to project directory
cd "$(dirname "$0")"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies if needed
if [ ! -f "venv/.installed" ]; then
    echo "Installing dependencies..."
    pip install -r requirements.txt
    touch venv/.installed
fi

# Check arguments
AGENT="all"
DEBUG=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --cv)
            AGENT="cv"
            shift
            ;;
        --cover-letter)
            AGENT="cover-letter"
            shift
            ;;
        --status)
            AGENT="status"
            shift
            ;;
        --debug)
            DEBUG="--debug"
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--cv|--cover-letter|--status] [--debug]"
            exit 1
            ;;
    esac
done

# Run the agents
if [ "$AGENT" = "status" ]; then
    echo "Checking job status..."
    python -m src.main --status $DEBUG
else
    echo "Starting agent: $AGENT"
    python -m src.main --agent "$AGENT" $DEBUG
fi

echo ""
echo "=============================================="
echo "  Done!"
echo "=============================================="
