# Job Application Multi-Agent System

A sequential multi-agent system that automates job application processing using Kafka for data ingestion.

## Architecture Overview

```
┌─────────────────┐     ┌─────────────┐     ┌───────────────────┐     ┌────────────────────┐
│   DroidRun      │────▶│   Kafka     │────▶│  CV Customizer    │────▶│  Cover Letter &    │
│ (Android Auto)  │     │   Topics    │     │     Agent         │     │  Gmail Draft Agent │
└─────────────────┘     └─────────────┘     └───────────────────┘     └────────────────────┘
                                                     │                          │
                                                     ▼                          ▼
                                            ┌───────────────┐          ┌───────────────┐
                                            │ Job Folder    │          │ Gmail Draft   │
                                            │ - cv.pdf      │          │ Ready to Send │
                                            │ - job_details │          └───────────────┘
                                            └───────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────────┐
│  INDEPENDENT: Profile Updater Agent                                                     │
│  ┌──────────────┐     ┌──────────────────┐     ┌─────────────────────────────────────┐ │
│  │  Your CV     │────▶│ Profile Updater  │────▶│ user_profile.yaml + experience.md  │ │
│  │ (PDF/DOCX/   │     │     Agent        │     │ + motivations.md (auto-updated)    │ │
│  │  TEX/TXT)    │     │                  │     │ + LaTeX base templates              │ │
│  └──────────────┘     └──────────────────┘     └─────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

## Agents

### Agent 1: CV Customizer Agent
- Consumes job data from Kafka (supports multiple schemas from different platforms)
- Customizes LaTeX CV based on job requirements
- Creates job-specific folder with CV, job details, and user context

### Agent 2: Cover Letter & Gmail Draft Agent
- Activates after Agent 1 completes all Kafka messages
- Creates motivation letter based on job requirements
- Generates Gmail draft with CV and cover letter attached
- Language detection: French for France, unless English required

### Profile Updater Agent (Independent)
- **Runs separately** - not part of the main flow
- Multiple input modes:
  - **Initial Setup**: Provide your LaTeX CVs (EN/FR) as base templates
  - **Full Update**: Process any CV format (PDF, DOCX, TXT, MD, TEX)
  - **Incremental Update**: Add certifications, skills, experience via text
- Automatically updates all profile files
- Stores your LaTeX CVs as base templates for future customization
- Supports French and English
- Backs up all files before changes

## Quick Start

```bash
# Install dependencies
./setup.sh

# OPTION 1: Initial setup with your LaTeX CVs (recommended)
./update_profile.sh --cv-en my_cv_english.tex --cv-fr my_cv_french.tex

# OPTION 2: Update from any CV format
./update_profile.sh --cv your_cv.pdf

# OPTION 3: Add new certification/skill incrementally
./update_profile.sh --add "Add AWS Solutions Architect certification 2026"

# Or configure manually
nano config/user_profile.yaml
nano data/user/motivations.md
nano data/user/experience.md

# Start the job application agents
./start.sh

# Stop the agents
./stop.sh                  # Graceful stop (finish current job)
./stop.sh --force          # Force stop immediately
./stop.sh --status         # Check if running
```

## Profile Updater - All Options

### Initial Setup (LaTeX CVs as Base Templates)

When you first set up the project, provide your LaTeX CVs. They will be:
1. Used to extract your profile information
2. Stored as base templates for future job-specific customization

```bash
# Both English and French CVs
./update_profile.sh --cv-en cv_english.tex --cv-fr cv_french.tex

# Add motivation letter examples too
./update_profile.sh \
  --cv-en cv_english.tex \
  --cv-fr cv_french.tex \
  --letter-en motivation_letter_en.tex \
  --letter-fr motivation_letter_fr.tex

# Just English CV
./update_profile.sh --cv-en my_cv.tex
```

### Full CV Update (Any Format)

When you have a new CV in any format:

```bash
# From a PDF
./update_profile.sh --cv my_new_cv.pdf

# From a Word document
./update_profile.sh --cv resume.docx

# From a LaTeX file (also saved as base template)
./update_profile.sh --cv cv_updated.tex

# Auto-detect from uploads folder
cp my_cv.pdf uploads/
./update_profile.sh
```

### Incremental Updates (Text Commands)

When you just need to add something small:

```bash
# Add a certification
./update_profile.sh --add "Add AWS Solutions Architect certification obtained January 2026"

# Add a new skill
./update_profile.sh --add "Add Kubernetes and Terraform to skills"

# Add new experience
./update_profile.sh --add "Add new job: Senior Developer at TechCorp from March 2025, working on cloud infrastructure"

# Update contact info
./update_profile.sh --add "Update phone number to +33 6 12 34 56 78"

# Partial LaTeX snippet
./update_profile.sh --add "\item AWS Solutions Architect - Amazon (2026)"
```

The agent will:
1. Parse your update request using LLM
2. Merge with existing profile (doesn't replace everything)
3. Update YAML/MD files
4. Update your LaTeX base templates (if they exist)
5. Sync to project templates

## LLM Configuration

Configure LLM models in [config/config.yaml](config/config.yaml).

### Same Model for All Agents (Default)

```yaml
llm:
  provider: "ollama"  # or "openai"
  model: "llama3.2"   # Used by all agents
  base_url: "http://localhost:11434"
  temperature: 0.7
  max_tokens: 4096
```

### Different Model Per Agent

You can use different models for each agent - useful when you want faster models for some tasks and better quality for others:

```yaml
llm:
  provider: "ollama"
  model: "llama3.2"   # Default fallback
  base_url: "http://localhost:11434"
  
  # Per-agent customization
  agents:
    cv_customizer:
      enabled: true        # Enable custom model
      model: "llama3.2"    # Fast model for CV edits
    cover_letter:
      enabled: true
      model: "qwen2.5:32b" # Better model for writing
    profile_updater:
      enabled: true
      model: "llama3.2"    # Fast for parsing
```

**Examples:**
- Fast processing: Use `llama3.2` or `mistral` for all agents
- Quality writing: Use `qwen2.5:32b` or `deepseek-r1:32b` for cover_letter
- Mixed: Fast for cv_customizer, quality for cover_letter

## Stopping the Agents

The system supports graceful and force shutdown:

### Graceful Stop (Recommended)
Finishes the current job before stopping. Progress is saved and can be resumed.

```bash
./stop.sh              # or ./stop.sh --graceful
# Or press Ctrl+C once in the terminal running the agents
```

### Force Stop
Stops immediately, even if a job is in progress. The interrupted job will resume on next start.

```bash
./stop.sh --force
# Or press Ctrl+C twice in the terminal
```

### Check Status
```bash
./stop.sh --status     # Shows if agents are running and stop state
```

**Note:** After stopping, you can simply run `./start.sh` to resume processing from where it left off.

## Configuration

See `config/config.yaml` for Kafka, LLM, and Gmail settings.

## Requirements

- Python 3.10+
- Kafka broker
- Local LLM (Ollama) or API-based LLM
- LaTeX distribution (pdflatex)
- Gmail API credentials

## License

MIT
