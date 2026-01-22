#!/bin/bash
# Enhanced Profile Updater Script
# Supports multiple update modes:
#   - Initial setup with LaTeX CVs and motivation letters
#   - Full CV update from any format
#   - Incremental updates via text commands

set -e

echo "=============================================="
echo "  Profile Updater Agent (Enhanced)"
echo "=============================================="

cd "$(dirname "$0")"

# Activate virtual environment
if [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "Virtual environment not found. Run ./setup.sh first."
    exit 1
fi

# Parse arguments
CV_FILE=""
CV_EN=""
CV_FR=""
LETTER_EN=""
LETTER_FR=""
ADD_TEXT=""
DEBUG=""

show_help() {
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Update Modes:"
    echo ""
    echo "  Initial Setup (LaTeX CVs as base templates):"
    echo "    $0 --cv-en cv_english.tex --cv-fr cv_french.tex"
    echo "    $0 --cv-en cv.tex --letter-en letter.tex"
    echo ""
    echo "  Full CV Update (any format):"
    echo "    $0 --cv my_cv.pdf"
    echo "    $0 --cv-file resume.docx"
    echo "    $0                          # Looks in uploads/ folder"
    echo ""
    echo "  Incremental Update (text command):"
    echo "    $0 --add 'Add AWS Solutions Architect certification 2026'"
    echo "    $0 --add 'Add new job: Senior Dev at TechCorp since 2025'"
    echo "    $0 --add 'Add Python, Kubernetes to skills'"
    echo ""
    echo "Options:"
    echo "  --cv, --cv-file PATH    Path to CV file (PDF, DOCX, TXT, MD, TEX)"
    echo "  --cv-en PATH            English LaTeX CV (saved as base template)"
    echo "  --cv-fr PATH            French LaTeX CV (saved as base template)"
    echo "  --letter-en PATH        English motivation letter example"
    echo "  --letter-fr PATH        French motivation letter example"
    echo "  --add, --add-text TEXT  Incremental update command"
    echo "  --debug                 Enable debug logging"
    echo "  --help, -h              Show this help"
    echo ""
    echo "Supported formats: PDF, DOCX, TXT, MD, TEX (LaTeX)"
    echo ""
    echo "This agent will:"
    echo "  1. Extract/update information from your input"
    echo "  2. Update config/user_profile.yaml"
    echo "  3. Update data/user/experience.md"
    echo "  4. Update data/user/motivations.md"
    echo "  5. Store LaTeX CVs as base templates in data/user/templates/"
    echo "  6. Backup previous files to data/backups/"
    echo ""
    exit 0
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --cv|--cv-file)
            CV_FILE="$2"
            shift 2
            ;;
        --cv-en)
            CV_EN="$2"
            shift 2
            ;;
        --cv-fr)
            CV_FR="$2"
            shift 2
            ;;
        --letter-en)
            LETTER_EN="$2"
            shift 2
            ;;
        --letter-fr)
            LETTER_FR="$2"
            shift 2
            ;;
        --add|--add-text)
            ADD_TEXT="$2"
            shift 2
            ;;
        --debug)
            DEBUG="--debug"
            shift
            ;;
        --help|-h)
            show_help
            ;;
        *)
            # Assume it's the CV file if no flag
            if [ -z "$CV_FILE" ] && [ -f "$1" ]; then
                CV_FILE="$1"
            fi
            shift
            ;;
    esac
done

# Build command
CMD="python -m src.main --update-profile $DEBUG"

# Determine mode and build command
if [ -n "$CV_EN" ] || [ -n "$CV_FR" ]; then
    echo "Mode: Initial Setup (LaTeX CVs as base templates)"
    
    if [ -n "$CV_EN" ]; then
        if [ ! -f "$CV_EN" ]; then
            echo "Error: English CV not found: $CV_EN"
            exit 1
        fi
        echo "  English CV: $CV_EN"
        CMD="$CMD --cv-en \"$CV_EN\""
    fi
    
    if [ -n "$CV_FR" ]; then
        if [ ! -f "$CV_FR" ]; then
            echo "Error: French CV not found: $CV_FR"
            exit 1
        fi
        echo "  French CV: $CV_FR"
        CMD="$CMD --cv-fr \"$CV_FR\""
    fi
    
    if [ -n "$LETTER_EN" ]; then
        if [ ! -f "$LETTER_EN" ]; then
            echo "Error: English letter not found: $LETTER_EN"
            exit 1
        fi
        echo "  English Letter: $LETTER_EN"
        CMD="$CMD --letter-en \"$LETTER_EN\""
    fi
    
    if [ -n "$LETTER_FR" ]; then
        if [ ! -f "$LETTER_FR" ]; then
            echo "Error: French letter not found: $LETTER_FR"
            exit 1
        fi
        echo "  French Letter: $LETTER_FR"
        CMD="$CMD --letter-fr \"$LETTER_FR\""
    fi

elif [ -n "$ADD_TEXT" ]; then
    echo "Mode: Incremental Update"
    echo "  Adding: $ADD_TEXT"
    CMD="$CMD --add-text \"$ADD_TEXT\""

elif [ -n "$CV_FILE" ]; then
    echo "Mode: Full CV Update"
    if [ ! -f "$CV_FILE" ]; then
        echo "Error: CV file not found: $CV_FILE"
        exit 1
    fi
    echo "  CV File: $CV_FILE"
    CMD="$CMD --cv-file \"$CV_FILE\""

else
    echo "Mode: Auto (looking in uploads/ folder)"
fi

echo ""

# Run the profile updater
eval $CMD

echo ""
echo "=============================================="
echo "  Profile Update Complete!"
echo "=============================================="
echo ""
echo "Updated files:"
echo "  - config/user_profile.yaml"
echo "  - data/user/experience.md"
echo "  - data/user/motivations.md"
if [ -n "$CV_EN" ] || [ -n "$CV_FR" ]; then
    echo "  - data/user/templates/*.tex (your base templates)"
    echo "  - templates/cv_*.tex (project templates updated)"
fi
echo ""
echo "Previous files backed up to: data/backups/"
echo ""
